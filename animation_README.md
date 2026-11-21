# Animations

Every animation is its own file next to `main.py`: `animation_flow.json`, `animation_bits.json`, and so on. `animator.html` is a generic engine that draws whatever those files say;
it has no animation of its own. `main.py` needs no changes when you add, remove or edit an animation.

The planner picks an animation for each scene and fills in its parameters. You can change any text by editing the scene's
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

Save the file and re-run (`python main.py -R <project folder>`); only that scene's animation is redone.
A scene that names an animation that has no `animation_<name>.json` file falls back to the planner's choice.

## Add, remove or change an animation (JSON only)

- **Remove:** delete its file. Or add `"hidden": true` to keep it usable by name but not offered to the planner.
- **Change what the planner knows:** edit `description` / `params`.
- **Change how it looks or moves:** edit its `setup`, `frame` and `tree` (below).
- **Add:** copy a file, name it `animation_<newname>.json`, set its `name` to match, and change it. No list needs updating.

## How an animation file is built

```json
{
  "name": "bullets",
  "description": "text the planner reads to decide when to use it",
  "params": {"items": "what the planner must fill in", "caption": "optional caption"},
  "setup": {"items": "list(P.items, ['One','Two','Three'], 5).map(String)"},
  "frame": {"k": "ease((t - T_IN) / 0.6)"},
  "tree": [
    {"tag": "div", "style": {"display": "flex", "flex-direction": "column", "gap": "2vh"},
     "children": [
       {"each": "items", "tag": "div", "class": "card", "text": "{{item}}",
        "style": {"--c": "{{COLORS[i % 5]}}"},
        "bind": {"style.opacity": "ease((t - T_IN - i * 0.5) / 0.5)"}}
     ]}
  ]
}
```

| field | meaning |
|---|---|
| `setup` | values computed once, in order (for example the cleaned-up list of items) |
| `frame` | values recomputed for every frame, in order (they can use `t`, the time in seconds) |
| `tree` | the things to draw, as nested nodes |

**Node fields**

| field | meaning |
|---|---|
| `tag` | `div`, `span`, `svg`, `g`, `rect`, `circle`, `line`, `path`, `polygon`, `text`, `tspan` ... (anything inside an `svg` is drawn as SVG). `fragment` groups children without drawing anything |
| `class` | ready-made look: `row`, `card`, `cap` (caption), `num`, `pt`, `link`, `sp`, `pulse` |
| `style`, `attrs` | fixed CSS and attributes. `{{ ... }}` inside a value is evaluated |
| `text` | fixed text (`{{ ... }}` allowed) |
| `bind` | updated every frame: `"style.opacity": "..."`, `"attr.cx": "..."`, `"text": "..."` |
| `vars` / `frame` | values for this node (and its children): `vars` once, `frame` every frame |
| `each` | draw this node once per item of a list (or `n` times for a number). Inside: `i` (index), `item` (or the name in `as`), and `index` renames `i` |
| `if` | draw this node only when the expression is true |
| `id` | name the node so other expressions can reach it as `refs.<id>[i]` |
| `children` | nodes inside this one |

**Available inside every expression:** `t` (seconds), `P` (the scene's parameters, for example `P.caption`), `V` (true in portrait),
`ease`, `clamp`, `lerp`, `T_IN`, `COLORS`, `list(v, default, max)`, `bitsOf(v, default, max)`, `num`, `decimals`,
`bob(t, i)`, `sheen(t, i)`, `mid(el, container)`, `Math`, plus everything you defined in `setup`, `frame` and `vars`.

Look at the existing `animation_*.json` files for working examples (`flow` for HTML and a travelling pulse, `bits` and `ring` for SVG).
A mistake in an expression is printed in the browser console as `[animator] error in ...` and that part is skipped.

## Animations included

| name | shows |
|---|---|
| `flow` | 3 to 5 labelled cards joined by arrows with a glowing pulse (general purpose) |
| `compare` | 2 or 3 columns side by side, each with a few short points |
| `steps` | a numbered list revealed one by one, then highlighted in turn |
| `stat` | 1 to 3 big numbers that count up |
| `bits` | smooth voltage wave turning into a square wave, then a scrolling stream of 1s and 0s |
| `cells` | SSD cells: electrons written into cells (1), empty cells (0), then a read scan |
| `ring` | spinning hard-drive platter with a ring of magnets (direction = 1 or 0) |
| `stack` | layers stacked top to bottom, each wider than the last, revealed one by one then highlighted (rankings, levels, memory hierarchy) |
| `meter` | horizontal bars that fill to different lengths, to compare speed or size at a glance |
| `cycle` | 3 or 4 steps in a loop with arrows going round and a travelling dot (anything that repeats) |
| `timeline` | events along a line, left to right (top to bottom in portrait), each with a time and a short note |
| `prosCons` | two columns, advantages with ticks and disadvantages with crosses |
| `bigtext` | one big phrase appearing word by word, with an optional highlighted word (key message, definition) |
| `grid` | a grid of 4 to 9 tiles that appear one by one and then light up in turn (parts, components, types) |
| `none` | nothing: the scene shows only its background and subtitles (not offered to the planner; use it by name, `"animation": "none"`) |
