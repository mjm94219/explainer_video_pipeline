# Animation blocks

The blocks live in `blocks.html`, used by `main.py`.

The planner picks a block for each scene and fills in its parameters, and you can change any text by editing the scene's
`Scripts\onscreen_sNN.json`:

```json
{
  "animation": "compare",
  "heading": "SSD vs Hard drive",
  "animation_params": {
    "columns": [
      {"name": "SSD", "points": ["faster", "electrons"]},
      {"name": "Hard drive", "points": ["cheaper", "magnets"]}
    ],
    "caption": "Pick by speed or price"
  }
}
```

Save the file and re-run (`python main.py -R <project folder>`);
only that scene's animation is redone. A scene that names a block its page doesn't have falls back to `flow`.

To add a block, add an entry to the `blocks` list in the `animation-meta` JSON at the top of the page, and a function with the same name in `BLOCKS`.
The page is set in `config.py` (`EXPLAINER_BLOCKS_HTML`).

## Explainer blocks

| name | shows |
|---|---|
| `flow` | 3 to 5 labelled cards joined by arrows with a glowing pulse (general purpose, also the fallback) |
| `compare` | 2 or 3 columns side by side, each with a few short points |
| `steps` | a numbered list revealed one by one, then highlighted in turn |
| `stat` | 1 to 3 big numbers that count up |
| `bits` | smooth voltage wave turning into a square wave, then a scrolling stream of 1s and 0s |
| `cells` | SSD cells: electrons written into cells (1), empty cells (0), then a read scan |
| `ring` | spinning hard-drive platter with a ring of magnets (direction = 1 or 0) |
