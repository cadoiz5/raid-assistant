# raid-assistant

A personal tool for tracking PokeMMO raid teams. It OCRs a Pokemon summary card
from the game, turns it into a PokePaste, and checks scanned Pokemon against
per-raid "strat" constraints (species / item / ability / stat bounds / moves).

## Components

| File | What it does |
| --- | --- |
| `screenshot` | CLI: grab a screen region, OCR it, emit a PokePaste to the clipboard. Run `python screenshot`. Flags: `--image`, `--bbox x1,y1,x2,y2`, `--select-only`, `--scale`, `--debug`. |
| `app.py` | Main GUI. Coverage grid of the 6 raids x positions P1-P4, scoped to a "character" (a PokeMMO account). Run `python app.py`. |
| `scan_window.py` | Per-position scan window: scan 6 Pokemon, validate each against the loaded strat. |
| `build_lists.py` | Regenerates `data/` (reference name lists + `species_stats.json`) from PokeMMO's dex dump (`../dump/*.json`). |
| `data/` | Committed reference data the parser snaps to: `moves.txt`, `abilities.txt`, `items.txt`, `species.txt`, `species_stats.json`. |
| `samples/` | Real summary-card screenshots for testing (`sample*.png`). |
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
Rerun `python build_lists.py` only when the PokeMMO dex dump is refreshed.

## Local data (not committed)

- `prefs.json` - user preferences (currently just the capture region).
- `saves/` - your scanned teams, one folder per character.
