// render.mjs — capture explainer.html frame by frame and encode MP4 + GIF.
//
//   python assets/motion/export_data.py           # refresh the numbers
//   npm i playwright                               # once (any folder on NODE_PATH)
//   node assets/motion/render.mjs [--fps 30]       # needs ffmpeg on PATH (or $FFMPEG)
//
// Writes docs/media/<name>.mp4 (1280×720, H.264), a GIF preview and a poster
// frame; the page sets window.GIF = [start, length] and window.POSTER = t.
// The page draws a pure function of time, so the same data always gives the
// same video. Usage: node render.mjs [--fps 30] [--name explainer]
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..', '..');
const OUT = join(ROOT, 'docs', 'media');
const FFMPEG = process.env.FFMPEG || 'ffmpeg';
const arg = (k, d) => (process.argv.includes(k) ? process.argv[process.argv.indexOf(k) + 1] : d);
const fps = Number(arg('--fps', 30));
const name = arg('--name', 'explainer');

// tiny static server for explainer.html + data.json
const types = { '.html': 'text/html', '.json': 'application/json', '.js': 'text/javascript', '.css': 'text/css' };
const server = createServer(async (req, res) => {
  try {
    const f = join(HERE, decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, ''));
    res.writeHead(200, { 'content-type': types[extname(f)] || 'application/octet-stream' });
    res.end(await readFile(f));
  } catch { res.writeHead(404); res.end(); }
}).listen(0);
const url = `http://localhost:${server.address().port}/explainer.html`;

function ffmpeg(args) {
  const p = spawn(FFMPEG, ['-hide_banner', '-loglevel', 'error', '-y', ...args], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((ok, fail) => p.on('close', c => (c ? fail(new Error(`ffmpeg exit ${c}`)) : ok())));
  return { stdin: p.stdin, done };
}

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto(url);
await page.waitForFunction(() => window.ready);
const { duration, gifWin, posterT } = await page.evaluate(() => ({ duration: window.DURATION, gifWin: window.GIF, posterT: window.POSTER }));
const frames = Math.round(duration * fps);

const mp4 = join(OUT, `${name}.mp4`);
const enc = ffmpeg(['-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'slow', '-crf', '20',
  '-movflags', '+faststart', mp4]);
for (let i = 0; i < frames; i++) {
  await page.evaluate(t => window.render(t), i / fps);
  const png = await page.screenshot({ type: 'png' });
  if (!enc.stdin.write(png)) await new Promise(r => enc.stdin.once('drain', r));
  if (i % (fps * 10) === 0) process.stdout.write(`  ${Math.round(i / fps)} s / ${duration} s\n`);
}
enc.stdin.end();
await enc.done;

await page.evaluate(t => window.render(t), posterT);
await page.screenshot({ path: join(OUT, `${name}-poster.png`) });
await browser.close();
server.close();

// GIF preview of the page's chosen window, 640 px wide, 12 fps, own palette
const gif = join(OUT, `${name}-preview.gif`);
const filt = 'fps=12,scale=640:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=4';
await ffmpeg(['-ss', String(gifWin[0]), '-t', String(gifWin[1]), '-i', mp4, '-vf', filt, '-loop', '0', gif]).done;
console.log(`wrote ${mp4}\n      ${gif}\n      ${join(OUT, `${name}-poster.png`)}`);
