#!/usr/bin/env python3
"""
sprites.py - species battle sprites for the GUI.

`sprite(species, size)` returns a Tk PhotoImage (kept alive in a module cache so
tkinter doesn't garbage-collect it out from under the widget) or None when the
sprite file is missing or Pillow isn't installed. Every caller must handle None
and fall back to text.

Files live in sprites/<species>.png, named the way scan_window._norm normalises
a species (lowercase, alphanumerics only): sprites/mrmime.png, sprites/farfetchd.png.
"""

import os
import re

try:
    from PIL import Image, ImageTk
except ImportError:  # Pillow is a hard dep elsewhere, but never crash the GUI over a sprite
    Image = ImageTk = None

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sprites")

_cache = {}   # (norm_name, size) -> PhotoImage | None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def sprite(species, size=40, muted=False):
    """PhotoImage for `species` scaled to size x size, or None. `muted=True`
    returns a dimmed greyscale version (used for done / unselected cells)."""
    key = (_norm(species), int(size), bool(muted))
    if key in _cache:
        return _cache[key]

    img = None
    path = os.path.join(DIR, key[0] + ".png")
    if ImageTk is not None and key[0] and os.path.isfile(path):
        try:
            im = Image.open(path).convert("RGBA")
            if im.size != (key[1], key[1]):
                im = im.resize((key[1], key[1]), Image.LANCZOS)
            if muted:
                alpha = im.getchannel("A").point(lambda a: a * 45 // 100)
                grey = im.convert("L").point(lambda v: v * 70 // 100)
                im = Image.merge("RGBA", (grey, grey, grey, alpha))
            img = ImageTk.PhotoImage(im)
        except Exception:
            img = None

    _cache[key] = img
    return img
