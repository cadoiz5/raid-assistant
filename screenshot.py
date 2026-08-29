#!/usr/bin/env python3
"""
screenshot.py - Select a region of your screen showing a Pokemon summary,
OCR it, and generate a PokePaste (copied to your clipboard).

Usage:
    python screenshot.py                    # interactive: drag a box on screen
    python screenshot.py --image shot.png   # parse an existing screenshot file
    python screenshot.py --debug            # also print the OCR rows / column split
    python screenshot.py --scale 4          # upscale factor for OCR (default 3)

Dependencies:
    pip install pillow pytesseract mss pyperclip
    Plus the Tesseract OCR engine itself:
      - Windows: https://github.com/UB-Mannheim/tesseract/wiki
      - macOS:   brew install tesseract
      - Linux:   sudo apt install tesseract-ocr

Reference lists (data/moves.txt, data/abilities.txt, data/items.txt,
data/species.txt) let the parser snap OCR text to real names. Build them from
PokeMMO's dex dump with:
    python build_lists.py
The script still runs without them, just with rawer output.
"""

import sys
import os
import re
import time
import shutil
import argparse

# Become DPI-aware BEFORE anything creates a window. On a scaled display
# (e.g. Windows at 125%), tkinter would otherwise report virtualized
# coordinates while mss grabs in real pixels - so the captured region
# would be shifted and the wrong part of the screen gets OCR'd.
if sys.platform == "win32":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ----------------------------- dependencies -----------------------------
def _die_missing(pkg, pipname=None):
    print(f"Missing dependency: {pkg}\n  pip install {pipname or pkg}", file=sys.stderr)
    sys.exit(1)


try:
    from PIL import Image, ImageFilter
except ImportError:
    _die_missing("PIL", "pillow")

try:
    import pytesseract
except ImportError:
    _die_missing("pytesseract")

# The Tesseract engine is a separate native program, not a pip package.
# If it isn't on PATH, look in the usual install locations.
if not shutil.which("tesseract"):
    for _cand in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        r"D:\Program Files\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.isfile(_cand):
            pytesseract.pytesseract.tesseract_cmd = _cand
            break


# ----------------------------- reference data -----------------------------
NATURES = {
    "hardy", "lonely", "brave", "adamant", "naughty", "bold", "docile", "relaxed",
    "impish", "lax", "timid", "hasty", "serious", "jolly", "naive", "modest",
    "mild", "quiet", "bashful", "rash", "calm", "gentle", "sassy", "careful",
    "quirky",
}

TYPE_WORDS = frozenset(
    "normal fire water electric grass ice fighting poison ground flying psychic "
    "bug rock ghost dragon dark steel fairy".split()
)

# Order the stats appear in on the card: HP / Atk / Def / SpA / SpD / Spe
STAT_LABELS = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]


class Ref:
    """A reference name list (moves / abilities / items / species) loaded from a
    txt file in the data/ folder - one name per line, '#' lines ignored. Build
    the files from PokeMMO's dex dump with `python build_lists.py`. Missing file
    => empty list => that snap is silently skipped."""

    def __init__(self, fname):
        self.names, self.lc, self.key = [], [], []
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", fname)
        try:
            with open(path, encoding="utf-8") as fh:
                for ln in fh:
                    ln = ln.strip()
                    if ln and not ln.startswith("#"):
                        self.names.append(ln)
                        self.lc.append(ln.lower())
                        self.key.append(re.sub(r"[^a-z0-9]", "", ln.lower()))
        except OSError:
            pass

    def __bool__(self):
        return bool(self.names)


MOVES = Ref("moves.txt")
ABILITIES = Ref("abilities.txt")
ITEMS = Ref("items.txt")
SPECIES = Ref("species.txt")


# ----------------------------- region selection -----------------------------
def select_region():
    """Fullscreen transparent overlay. Drag a box, release to confirm, Esc to cancel.
    Returns (x1, y1, x2, y2) in absolute screen coords, or None."""
    import tkinter as tk

    state = {"bbox": None}
    root = tk.Tk()
    root.attributes("-fullscreen", True)
    try:
        root.attributes("-alpha", 0.25)
    except tk.TclError:
        pass
    root.attributes("-topmost", True)
    root.configure(bg="black")

    canvas = tk.Canvas(root, cursor="cross", highlightthickness=0, bg="black")
    canvas.pack(fill="both", expand=True)

    start = {"x": 0, "y": 0}
    rect = {"id": None}

    def on_press(e):
        start["x"], start["y"] = e.x, e.y
        rect["id"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def on_drag(e):
        if rect["id"] is not None:
            canvas.coords(rect["id"], start["x"], start["y"], e.x, e.y)

    def on_release(e):
        x1, y1 = min(start["x"], e.x), min(start["y"], e.y)
        x2, y2 = max(start["x"], e.x), max(start["y"], e.y)
        ox, oy = root.winfo_rootx(), root.winfo_rooty()
        state["bbox"] = (x1 + ox, y1 + oy, x2 + ox, y2 + oy)
        root.destroy()

    def cancel(_=None):
        state["bbox"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", cancel)
    root.mainloop()
    return state["bbox"]


def capture(bbox):
    """Grab a screen region as a PIL image."""
    try:
        import mss
    except ImportError:
        _die_missing("mss")

    x1, y1, x2, y2 = bbox
    if x2 - x1 < 3 or y2 - y1 < 3:
        return None
    time.sleep(0.15)  # let the selection overlay finish closing before we grab
    factory = getattr(mss, "MSS", mss.mss)  # mss.mss() is deprecated in mss >= 10
    with factory() as sct:
        raw = sct.grab({"left": x1, "top": y1, "width": x2 - x1, "height": y2 - y1})
        return Image.frombytes("RGB", raw.size, raw.rgb)


# ----------------------------- OCR -----------------------------
def _prep(img, scale):
    g = img.convert("L")
    w, h = g.size
    g = g.resize((max(1, w * scale), max(1, h * scale)), Image.LANCZOS)
    return g.filter(ImageFilter.SHARPEN)


def ocr_rows(img, scale=3):
    """OCR into rows, keeping each word's x-position. A row is a list of
    (x0, x1, text, height) tuples, left to right. Keeping the layout lets us
    tell a left-column label / type-badge pill from the value beside it -
    OCR mangles the label text but not the geometry."""
    data = pytesseract.image_to_data(
        _prep(img, scale), config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )
    rows = {}
    for j, txt in enumerate(data["text"]):
        txt = txt.strip()
        if not txt:
            continue
        key = (data["block_num"][j], data["par_num"][j], data["line_num"][j])
        x0 = data["left"][j]
        rows.setdefault(key, []).append(
            (x0, x0 + data["width"][j], txt, data["height"][j]))
    return [sorted(r) for _, r in sorted(rows.items())]


# ----------------------------- parsing -----------------------------
def _ints(s):
    return [int(n) for n in re.findall(r"\d+", s)]


def _text(row):
    return " ".join(w[2] for w in row)


def _fuzzy(word, options, cutoff=0.7):
    import difflib
    m = difflib.get_close_matches(word.lower(), list(options), n=1, cutoff=cutoff)
    return m[0] if m else None


def _clean(s):
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 '\-.]+", " ", s)).strip()


def _field_value(row, label_pat):
    """Value of a 'Label: value' row. Skip the label word(s), then keep the
    leading run of Capitalised words - item/ability names are Title Case, so
    this trims trailing OCR junk from the sprite icon ('Choice Specs ty-',
    'Magic Bounce #')."""
    toks = [w[2] for w in row]
    i = 0
    while i < len(toks):
        alpha = re.sub(r"[^A-Za-z]", "", toks[i]).lower()
        # anchored: the label is at the start ("Ability"), not just contained
        # anywhere - otherwise "Adaptability" itself looks like the label
        if alpha and not re.match(label_pat, alpha):
            break
        i += 1
    val = []
    for tok in toks[i:]:
        if re.match(r"[A-Z][\w'.\-]*$", tok):
            val.append(tok)
        elif val:
            break
    if not val:  # OCR lower-cased the value - fall back to any word tokens
        val = [t for t in toks[i:] if re.search(r"[A-Za-z0-9]", t)]
    return _clean(" ".join(val))


def _snap(text, ref, cutoff=0.8):
    """Snap a value to the closest name in `ref`, ignoring spaces/punctuation
    and case ('magicbounce' -> 'Magic Bounce'). Unchanged if nothing is close
    enough or the list is empty."""
    import difflib
    key = re.sub(r"[^a-z0-9]", "", text.lower())
    if not key or not ref:
        return text
    hit = difflib.get_close_matches(key, ref.key, n=1, cutoff=cutoff)
    return ref.names[ref.key.index(hit[0])] if hit else text


# A real move word is Capitalised ("Knock", "U-turn"); a type badge OCRs
# lowercase ("dark") or garbled - so it is never a clean move word.
_MOVE_WORD = re.compile(r"^[A-Z][a-z]*(?:[-'][A-Za-z]+)*[.,]?$")


def _snap_move(text):
    """Turn a move row into a move name. With moves.txt loaded, every trailing
    slice of the row's words is matched against the list and the best hit wins
    - which drops the leading type badge for free ("dark Knock Off" -> the
    slice "Knock Off" matches exactly) and fixes OCR typos. Without the list,
    fall back to stripping a badge-ish leading token."""
    import difflib
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    if MOVES and toks:
        best, score = None, 0.0
        for i in range(len(toks)):
            cand = " ".join(toks[i:]).lower()
            hit = difflib.get_close_matches(cand, MOVES.lc, n=1, cutoff=0.7)
            if hit:
                # +bonus per word so "Rock Smash" beats the slice "Smash"
                r = difflib.SequenceMatcher(None, cand, hit[0]).ratio() + 0.03 * (len(toks) - i)
                if r > score:
                    best, score = MOVES.names[MOVES.lc.index(hit[0])], r
        if best:
            return best
    if len(toks) >= 2 and (toks[0].lower() in TYPE_WORDS or not _MOVE_WORD.match(toks[0])):
        toks = toks[1:]
    return _clean(" ".join(toks))


def parse(rows):
    """rows: output of ocr_rows(). PokeMMO's summary layout is fixed, so this
    leans on row *order* (the 3 six-number rows are always Stats/IVs/EVs) and
    on a move-name list, not on the label text - which OCR mangles."""
    texts = [_text(r) for r in rows]
    d = {
        "name": None, "gender": None, "level": None, "item": None,
        "ability": None, "nature": None, "evs": None, "ivs": None,
        "stats": None, "moves": [],
    }

    # --- name + level: the "Lv 100 <name>" row ---
    for t in texts:
        m = re.search(r"l[vy]l?\.?\s*(\d{1,3})\s+(\S.*)", t, re.I)
        if not m:
            continue
        d["level"] = int(m.group(1))
        rest = m.group(2)
        nm = re.match(r"[A-Za-z][A-Za-z .:'\u00e9\-]*", rest)
        matched = nm.group(0) if nm else ""
        d["name"] = _snap(_clean(matched), SPECIES, cutoff=0.82) or None
        # the trailing gender symbol mis-OCRs: female sign -> #/2/9/Q, male -> &/3/d/$
        tail = rest[len(matched):]
        if "\u2640" in rest or re.search(r"(?<!\d)[#Q29](?!\d)", tail):
            d["gender"] = "F"
        elif "\u2642" in rest or re.search(r"(?<!\d)[&$3d](?!\d)", tail):
            d["gender"] = "M"
        break

    # --- the three 6-number rows, top to bottom = Stats, IVs, EVs ---
    sixes = [v[:6] for v in (_ints(t) for t in texts) if len(v) >= 6]
    for key, vals in zip(("stats", "ivs", "evs"), sixes):
        d[key] = vals

    # --- nature: fuzzy-match a word anywhere ---
    for t in texts:
        for wd in re.findall(r"[A-Za-z]{4,}", t):
            hit = _fuzzy(wd, NATURES, cutoff=0.75)
            if hit:
                d["nature"] = hit.title()
                break
        if d["nature"]:
            break

    # --- ability + item: the labelled rows, by their (mangled) label word ---
    marking_i = None
    for i, t in enumerate(texts):
        head = re.sub(r"[^a-z]", "", t.lower())
        if d["ability"] is None and head[:4] in ("abil", "abli", "ablt", "abll"):
            d["ability"] = _snap(_field_value(rows[i], r"abil"), ABILITIES)
        elif d["item"] is None and ("held" in head[:11] or head[:4] == "item"):
            d["item"] = _snap(_field_value(rows[i], r"item|held|tem"), ITEMS, cutoff=0.82)
        elif re.match(r"mark|marc|nark", head):
            marking_i = i

    # --- moves: rows below "Markings" (or the last four) ---
    move_rows = rows[marking_i + 1:] if marking_i is not None else rows[-4:]
    moves = []
    for r in move_rows:
        solo = re.sub(r"[^a-z]", "", _text(r).lower())
        if len(r) == 1 and (solo in TYPE_WORDS or _fuzzy(solo, TYPE_WORDS, 0.8)):
            continue  # a stray badge that landed on its own line
        mv = _snap_move(_text(r))
        if mv and not re.match(r"(stat|iv|ev|mark|lv)\b", mv.lower()):
            moves.append(mv)
    d["moves"] = moves[:4]
    return d


# ----------------------------- output -----------------------------
def format_paste(d):
    head = d["name"] or "Unknown"
    if d["gender"] in ("M", "F"):
        head += f" ({d['gender']})"
    if d["item"]:
        head += f" @ {d['item']}"
    out = [head]

    if d["ability"]:
        out.append(f"Ability: {d['ability']}")
    if d["level"]:
        out.append(f"Level: {d['level']}")

    if d["evs"] and len(d["evs"]) == 6:
        parts = [f"{v} {STAT_LABELS[i]}" for i, v in enumerate(d["evs"]) if v > 0]
        if parts:
            out.append("EVs: " + " / ".join(parts))

    if d["nature"]:
        out.append(f"{d['nature']} Nature")

    if d["ivs"] and len(d["ivs"]) == 6:
        parts = [f"{v} {STAT_LABELS[i]}" for i, v in enumerate(d["ivs"]) if v != 31]
        if parts:
            out.append("IVs: " + " / ".join(parts))

    if d["stats"] and len(d["stats"]) == 6:
        parts = [f"{v} {STAT_LABELS[i]}" for i, v in enumerate(d["stats"])]
        out.append("Stats: " + " / ".join(parts))

    for mv in d["moves"]:
        out.append(f"- {mv}")

    return "\n".join(out)


def to_clipboard(text):
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        try:
            import tkinter as tk
            r = tk.Tk(); r.withdraw()
            r.clipboard_clear(); r.clipboard_append(text); r.update()
            r.destroy()
            return True
        except Exception:
            return False


# ----------------------------- main -----------------------------
def main():
    try:  # OCR junk in --debug output can be unencodable for a legacy console
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="Screen region -> PokePaste via OCR")
    ap.add_argument("--image", help="parse an existing screenshot instead of selecting")
    ap.add_argument("--scale", type=int, default=3, help="OCR upscale factor")
    ap.add_argument("--debug", action="store_true", help="print the OCR rows / column split")
    ap.add_argument("--select-only", action="store_true",
                    help="just pick a region, print 'x1 y1 x2 y2', and exit")
    ap.add_argument("--bbox", help="capture this region 'x1,y1,x2,y2' (skip picking)")
    args = ap.parse_args()

    if args.select_only:
        bbox = select_region()
        if not bbox:
            sys.exit(1)
        print(" ".join(str(n) for n in bbox))
        return

    if args.image:
        img = Image.open(args.image).convert("RGB")
    elif args.bbox:
        coords = [int(n) for n in re.findall(r"-?\d+", args.bbox)]
        if len(coords) != 4:
            print("--bbox needs 'x1,y1,x2,y2'", file=sys.stderr)
            sys.exit(2)
        img = capture(tuple(coords))
        if img is None:
            print("Region too small.")
            return
    else:
        bbox = select_region()
        if not bbox:
            print("Cancelled.")
            return
        img = capture(bbox)
        if img is None:
            print("Selection too small.")
            return

    rows = ocr_rows(img, scale=args.scale)
    if args.debug:
        print("----- OCR ROWS (word by word) -----")
        for r in rows:
            print("  " + "  |  ".join(w[2] for w in r))
        print("----------------------------------\n")

    d = parse(rows)
    paste = format_paste(d)
    print(paste)

    missing = [k for k in ("name", "ability", "nature", "evs", "ivs", "stats") if not d[k]]
    if missing:
        print(f"\n[!] Couldn't read: {', '.join(missing)} "
              f"- try --scale 4 or a tighter/cleaner crop.", file=sys.stderr)
    if to_clipboard(paste):
        print("(copied to clipboard)", file=sys.stderr)


if __name__ == "__main__":
    main()
