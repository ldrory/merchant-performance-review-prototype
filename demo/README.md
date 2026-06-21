# Product demo (Remotion)

A short [Remotion](https://www.remotion.dev/) video: a terminal types `make decks`, then the
ACME performance-review deck "pops" and flips through its slides. The slides are recreated as
React components using the **real** brand theme, and the KPI charts are the **actual** product
output (rendered by `src/presentation/chart_generator.py`, not redrawn).

## Build & render

```bash
# 1. Generate the chart/logo assets from the product code (run from the repo root, needs the venv)
python demo/scripts/build_assets.py        # writes demo/public/charts/*.png + demo/public/logo.png

# 2. Install + render (from this demo/ folder)
cd demo
npm install
npm run studio          # interactive preview at http://localhost:3000
npm run render:mp4      # -> out/product-demo.mp4   (1080p H.264)
npm run render:gif      # -> out/product-demo.gif   (downscaled, for README embedding)
```

## Layout
- `src/scenes/Terminal.tsx` — the typing terminal.
- `src/scenes/Deck.tsx` — the slide-to-slide transitions.
- `src/components/` — `SlideFrame`, `Card`, and the 7 slide layouts.
- `src/data/deck.ts` — ACME deck content (extracted from the generated `.pptx`).
- `src/theme.ts` — brand palette mirrored from `src/presentation/theme.py`.
- `scripts/build_assets.py` — regenerates the chart PNGs into `public/`.

`node_modules/` and `out/` are gitignored; the curated clip lives at `docs/images/product-demo.gif`.
