# raid-assistant

A personal tool for tracking PokeMMO raid teams. It OCRs a Pokemon summary card
from the game, turns it into a PokePaste, and checks scanned Pokemon against
per-raid "strat" constraints (species / item / ability / stat bounds / moves).

## Components

| File | What it does |
| --- | --- |
| `app.py` | Main GUI. Coverage grid of the 6 raids x positions P1-P4, scoped to a "character" (a PokeMMO account). Run `python app.py`. |
| `components/` | Everything else the app is built from (below). |
| `components/screenshot.py` | CLI: grab a screen region, OCR it, emit a PokePaste to the clipboard. Run `python components/screenshot.py`. Flags: `--image`, `--bbox x1,y1,x2,y2`, `--select-only`, `--scale`, `--debug`. |
| `components/scan_window.py` | Per-position scan window: scan 6 Pokemon, validate each against the loaded strat. |
| `components/moves_window.py` | The in-raid move-order table (opened by clicking a raid name). |
| `components/theme.py` | The GUI's dark theme (`theme.apply(root)`, called once at startup). |
| `components/updater.py` | Self-update: if run from a `git clone`, checks `origin/main` and fast-forwards. |
| `components/breed_calc.py` | Turns a strat slot's stat bounds into the loosest IV ranges + nature options to breed for (shown for not-yet-scanned slots). |
| `components/build_lists.py` | Regenerates `data/` (reference name lists + `species_stats.json`) from PokeMMO's dex dump (`../dump/*.json`). |
| `components/prefs.py` | Tiny JSON key/value store (`prefs.json` in the project root). |
| `components/sprites.py` | Loads a species' battle sprite from `sprites/`. |
| `data/` | Committed reference data the parser snaps to: `moves.txt`, `abilities.txt`, `items.txt`, `species.txt`, `species_stats.json`. |
| `samples/` | Real summary-card screenshots for testing (`sample*.png`). |
| `sprites/` | Front battle sprite per species (`<species>.png`, 96×96), from PokeMMO's sprite dump. |
| `strats/<Raid>/<Strat>.txt` | Constraint files for a raid strat (all 4 positions). Format: `strats/FORMAT.md`. |

## Setup

```
pip install -r requirements.txt
```

Plus the Tesseract OCR engine:

- Windows: https://github.com/UB-Mannheim/tesseract/wiki
- macOS: `brew install tesseract`
- Linux: `sudo apt install tesseract-ocr`

The script auto-detects Tesseract on `PATH` or in the usual
`Program Files\Tesseract-OCR` locations.

The `data/` reference lists are committed, so the tools work out of the box.
Rerun `python components/build_lists.py` only when the PokeMMO dex dump is refreshed.

## Updating

Install by cloning the repo (`git clone`). On start-up the app quietly checks
GitHub; when there are new commits the menu bar shows **↑ Update available** —
click it to fast-forward. It only applies a clean fast-forward, so local edits
and unpushed commits are never overwritten. Needs `git` on `PATH`; a zip
download just doesn't show the option.

## Local data (not committed)

- `prefs.json` - user preferences (currently just the capture region).
- `saves/` - your scanned teams, one folder per character.
