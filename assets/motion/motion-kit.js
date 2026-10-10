// motion-kit.js — helpers for code-drawn explainers.
//
// A video page defines build(data) (create the DOM once) and render(t)
// (style it for time t, a pure function), then calls
//   MK.start({ duration, build, render, gif: [start, length], poster: t })
// render.mjs captures the page frame by frame; opened in a browser it plays live.
const MK = (() => {
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const ease = x => (x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  /** eased 0→1 progress of t through [a, b] */
  const prog = (t, a, b) => ease(clamp((t - a) / (b - a)));
  /** scene opacity: fade in after `a`, out before `b` */
  const alpha = (t, [a, b], f = 0.7) => Math.min(prog(t, a, a + f), 1 - prog(t, b - f, b));
  const $ = id => document.getElementById(id);
  const NS = 'http://www.w3.org/2000/svg';
  function el(tag, attrs = {}, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    parent && parent.appendChild(e);
    return e;
  }
  function mix(a, b, w) {
    const p = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
    const [x, y] = [p(a), p(b)];
    return '#' + x.map((v, i) => Math.round(v + (y[i] - v) * clamp(w)).toString(16).padStart(2, '0')).join('');
  }
  const fmt = (x, d = 1) => (x == null ? '—' : x.toFixed(d));
  const signed = (x, d = 1) => (x > 0 ? '+' : x < 0 ? '−' : '') + Math.abs(x).toFixed(d);
  /** a value counting up from 0 with progress q */
  const count = (v, q, d = 0) => (v * q).toFixed(d);

  /** background grid, brand step line (id stepPath) and network mark (id mark) */
  function chrome(svg) {
    const g = el('g', { stroke: '#355C7D', 'stroke-opacity': 0.18 }, svg);
    for (let y = 80; y < 720; y += 80) el('path', { d: `M0 ${y}H1280` }, g);
    for (let x = 320; x < 1280; x += 320) el('path', { d: `M${x} 0V720` }, g);
    const s = el('g', { id: 'steps', fill: 'none', stroke: '#14B8A6', 'stroke-width': 3 }, svg);
    el('path', { id: 'stepPath', d: 'M900 690H1000V650H1100V610H1180V650H1280' }, s);
    const m = el('g', { id: 'mark', transform: 'translate(80 210) scale(1.6)' }, svg);
    m.innerHTML = `
      <g stroke="#355C7D" stroke-width="2.5"><line x1="52.5" y1="92.7" x2="89.4" y2="79.9"/><line x1="52.5" y1="92.7" x2="12.6" y2="97.4"/><line x1="67.7" y1="49.7" x2="89.4" y2="79.9"/><line x1="107.6" y1="14.7" x2="107.2" y2="49.6"/><line x1="89.4" y1="79.9" x2="107.2" y2="49.6"/></g>
      <g stroke="#14B8A6" stroke-width="4"><line x1="42.4" y1="25.1" x2="15.8" y2="60.7"/><line x1="42.4" y1="25.1" x2="67.7" y2="49.7"/><line x1="15.8" y1="60.7" x2="12.6" y2="97.4"/><line x1="67.7" y1="49.7" x2="107.6" y2="14.7"/></g>
      <g fill="#14B8A6"><rect x="34.4" y="17.1" width="16" height="16"/><rect x="7.8" y="52.7" width="16" height="16"/><rect x="59.7" y="41.7" width="16" height="16"/><rect x="99.6" y="6.7" width="16" height="16"/><rect x="4.6" y="89.4" width="16" height="16"/></g>
      <g fill="#081A2F" stroke="#F4F7FA" stroke-width="2.5"><rect x="46.5" y="86.7" width="12" height="12"/><rect x="83.4" y="73.9" width="12" height="12"/><rect x="101.2" y="43.6" width="12" height="12"/></g>`;
  }
  /** brand elements: mark visible with `brand` (0..1), step line drawn in at the start */
  function brand(t, b) {
    $('mark').style.opacity = b;
    $('steps').style.opacity = 0.35 + 0.65 * b;
    const p = $('stepPath'), L = p.getTotalLength();
    p.setAttribute('stroke-dasharray', L);
    p.setAttribute('stroke-dashoffset', L * (1 - prog(t, 0.3, 3)));
  }
  /** set opacity of every element whose id is a key of `scenes` */
  function scenes(t, sc) { for (const id in sc) { const e = $(id); if (e) e.style.opacity = alpha(t, sc[id]); } }

  /** a simple linear scale */
  const scale = (d0, d1, r0, r1) => v => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);
  /** SVG path through points [[x,y],…] drawn up to fraction q of its length (by index) */
  function partial(pts, q) {
    const n = pts.length - 1, upto = q * n;
    let d = '';
    for (let i = 0; i <= Math.ceil(upto) && i <= n; i++) {
      let [x, y] = pts[i];
      if (i > upto && i > 0) { const w = upto - (i - 1); x = pts[i - 1][0] + (x - pts[i - 1][0]) * w; y = pts[i - 1][1] + (y - pts[i - 1][1]) * w; }
      d += (d ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
    }
    return d;
  }

  function start({ duration, build, render, gif = [0, 12], poster = duration / 2 }) {
    fetch('data.json').then(r => r.json()).then(data => {
      build(data);
      render(0);
      Object.assign(window, { ready: true, render: t => render(clamp(t, 0, duration)), DURATION: duration,
                              GIF: gif, POSTER: poster });
      if (!navigator.webdriver) {
        const t0 = performance.now();
        const loop = () => { render(((performance.now() - t0) / 1000) % duration); requestAnimationFrame(loop); };
        requestAnimationFrame(loop);
      }
    });
  }
  return { clamp, ease, prog, alpha, $, el, mix, fmt, signed, count, chrome, brand, scenes, scale, partial, start };
})();
