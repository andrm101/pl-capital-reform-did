# assets/motion — code-drawn explainer video

`explainer.html` draws every frame as a pure function of time, `render(t)`, from
`data.json`. `render.mjs` captures the page frame by frame with Playwright and
encodes it with ffmpeg. Opened in a browser, the page simply plays.

```bash
python assets/motion/export_data.py                  # numbers from data/dashboard/ and figures/
npm i playwright                                     # once (any folder on NODE_PATH)
node assets/motion/render.mjs --name pl-capital-explainer   # needs ffmpeg on PATH (or $FFMPEG)
```

Outputs go to `docs/media/`: the MP4 (1280×720, H.264), a 640 px GIF preview of
the impulse-response scene and a poster frame.

| Time (s) | Scene | Source |
|---|---|---|
| 0–6 | Title | — |
| 6–14 | 31 demoted vs 346 control cities | `summary.json` |
| 14–26 | Radom against its synthetic twin | `regions.json` (`counterfactualSeries`) |
| 26–38 | Local-projection response of ln population | `lp_irfs.json` |
| 38–48 | Five estimators, 95 % intervals | `sdid_estimates.json`, `figures/t04_robustness_summary.csv`, `summary.json` |
| 48–58 | City-by-city generalized synthetic control | `regions.json` (`gsc_att_avg_pct`) |
| 58–64 | Outro | `summary.json` |

`motion-kit.js` (helpers, brand chrome, playback) and `motion.css` are shared
with the other explainers in this portfolio.
