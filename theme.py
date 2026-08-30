#!/usr/bin/env python3
"""
theme.py - one dark theme for the whole Raid Assistant GUI.

Call `theme.apply(root)` once, right after `tk.Tk()`, before building any
windows. It switches ttk to the 'clam' engine (the stock Windows themes ignore
colour settings) and points the classic widgets (Listbox / Text / Menu) at the
same palette via the option database, so every Toplevel opened afterwards is
dark too.

The colour constants are also imported directly by the windows that colour
text at runtime (check statuses, greyed-out move cells, ...).
"""

from tkinter import ttk

# --- palette ---------------------------------------------------------------
BG        = "#1e1e1e"   # window background
BG_ALT    = "#2a2a2b"   # buttons, menus, raised bits
FIELD     = "#2d2d2d"   # entry / listbox / text / tree background
BORDER    = "#3c3c3c"
FG        = "#d4d4d4"   # primary text
FG_DIM    = "#8a8a8a"   # hints, secondary text
ACCENT    = "#0e639c"
ACCENT_HI = "#1177bb"
SEL_BG    = "#094771"   # selected row / highlighted text

# status colours, tuned to read on the dark background
PASS      = "#4ec96a"
FAIL      = "#f2564d"
NA        = "#8a8a8a"
BLOCKED   = "#e0a33e"
MISSING   = "#c07de0"

# moves table
MOVE_FG    = "#9aa0a6"   # the move under the mon name
MUTED      = "#5a5a5a"   # a greyed-out (done / unchecked) cell
TOOLTIP_BG = "#3a3a3a"


def apply(root):
    root.configure(background=BG)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", background=BG, foreground=FG, fieldbackground=FIELD,
                    bordercolor=BORDER, lightcolor=BG, darkcolor=BG,
                    troughcolor=BG_ALT, arrowcolor=FG, insertcolor=FG,
                    focuscolor=ACCENT_HI)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("TLabelframe", background=BG, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=BG, foreground=FG)
    style.configure("TSeparator", background=BORDER)

    style.configure("TButton", background=BG_ALT, foreground=FG,
                    bordercolor=BORDER, focuscolor=BG_ALT, padding=(8, 3))
    style.map("TButton",
              background=[("pressed", ACCENT), ("active", ACCENT_HI),
                          ("disabled", BG)],
              foreground=[("disabled", FG_DIM)])

    style.configure("TCheckbutton", background=BG, foreground=FG, focuscolor=BG)
    style.map("TCheckbutton",
              background=[("active", BG)],
              foreground=[("disabled", FG_DIM)],
              indicatorcolor=[("selected", ACCENT_HI), ("!selected", FIELD)])

    style.configure("TMenubutton", background=BG, foreground=FG,
                    arrowcolor=FG, bordercolor=BORDER, padding=(6, 2))
    style.map("TMenubutton", background=[("active", BG_ALT)],
              foreground=[("disabled", FG_DIM)])
    style.configure("Gear.TMenubutton", font=("TkDefaultFont", 12))

    style.configure("TEntry", fieldbackground=FIELD, foreground=FG,
                    bordercolor=BORDER, insertcolor=FG)

    style.configure("TCombobox", fieldbackground=FIELD, foreground=FG,
                    background=BG_ALT, bordercolor=BORDER, arrowcolor=FG)
    style.map("TCombobox",
              fieldbackground=[("readonly", FIELD), ("disabled", BG)],
              foreground=[("disabled", FG_DIM)],
              selectbackground=[("readonly", FIELD)],
              selectforeground=[("readonly", FG)])

    style.configure("Treeview", background=FIELD, fieldbackground=FIELD,
                    foreground=FG, bordercolor=BORDER)
    style.map("Treeview",
              background=[("selected", SEL_BG)],
              foreground=[("selected", FG)])
    style.configure("Treeview.Heading", background=BG_ALT, foreground=FG,
                    bordercolor=BORDER)

    # classic Tk widgets don't read ttk styles - feed them the option database
    for pat, val in (
        ("*Listbox.background", FIELD),
        ("*Listbox.foreground", FG),
        ("*Listbox.selectBackground", SEL_BG),
        ("*Listbox.selectForeground", FG),
        ("*Listbox.highlightThickness", 0),
        ("*Listbox.borderWidth", 1),
        ("*Text.background", FIELD),
        ("*Text.foreground", FG),
        ("*Text.insertBackground", FG),
        ("*Text.selectBackground", SEL_BG),
        ("*Text.selectForeground", FG),
        ("*Text.highlightThickness", 0),
        ("*Menu.background", BG_ALT),
        ("*Menu.foreground", FG),
        ("*Menu.activeBackground", ACCENT_HI),
        ("*Menu.activeForeground", "#ffffff"),
        ("*Menu.selectColor", FG),
        ("*Menu.borderWidth", 0),
        ("*Toplevel.background", BG),
    ):
        root.option_add(pat, val)
