#!/usr/bin/env python3
"""
moves_window.py - the in-raid move order.

A strat file may carry a "[Moves]" section: one "Turn N" block per turn, and
under it up to four "P<n> - ..." lines. A line is either a fixed "Mon Move",
or just "Mon" followed by "* <Ad> <Move>" lines - one per possible spawn ad -
when that turn's move depends on which ad appeared alongside the boss. A
trailing "Ad" / "Boss" / "Self" is the move's target (default: the boss).

This window shows the table (mon name over the move). A checkbox on each
P1..P4 header greys that column; clicking a turn's row greys it (turn done);
if the strat has ad-dependent moves, a dropdown (top right) picks the ad.
"""

import os
import re
import tkinter as tk
from tkinter import ttk

import theme
import sprites
from scan_window import HERE, STRATS, center_over, evaluate_position, strat_names

POSITIONS = ["P1", "P2", "P3", "P4"]

try:
    with open(os.path.join(HERE, "data", "moves.txt"), encoding="utf-8") as _fh:
        _MOVES = sorted((ln.strip() for ln in _fh
                         if ln.strip() and not ln.startswith("#")),
                        key=len, reverse=True)
except OSError:
    _MOVES = []


def split_action(text):
    """'Golduck Water Sport' -> ('Golduck', 'Water Sport'). Honours an explicit
    ':' or ' - ', else peels a known move off the end, else splits on the
    first space."""
    if not text:
        return "", ""
    for sep in (" - ", " – ", ": "):
        if sep in text:
            mon, mv = text.split(sep, 1)
            return mon.strip(), mv.strip()
    low = text.lower()
    for mv in _MOVES:
        if low == mv.lower():
            return "", text
        if low.endswith(" " + mv.lower()):
            return text[:-len(mv)].strip(), text[-len(mv):].strip()
    parts = text.split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (text, "")


def _split_target(text):
    """'Captivate Ad' -> ('Captivate', 'Ad'); 'Psych Up (P2)' -> ('Psych Up', 'P2');
    'Water Sport' -> ('Water Sport', '').  A trailing Ad / Boss / Self / P1-P4 is the
    move's target; the parens around it are optional."""
    m = re.match(r"(.*?)\s+\(?(ad|boss|self|p[1-4])\)?$", text.strip(), re.I)
    if not m:
        return text.strip(), ""
    tgt = m.group(2).upper() if m.group(2)[0] in "pP" else m.group(2).capitalize()
    return m.group(1).strip(), tgt


def parse_moves(path):
    """-> [{'turn': 'Turn 1', 'actions': {'P1': act, ...}}, ...] from the file's
    [Moves] section. act = {'mon', 'move', 'target', 'by_ad': {ad: (move, target)}}."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    turns, cur, last, in_moves = [], None, None, False
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        head = re.match(r"\[([^\]]+)\]$", s)
        if head:
            in_moves = head.group(1).strip().lower() == "moves"
            cur = last = None
            continue
        if not in_moves:
            continue
        if re.match(r"turn\b", s, re.I):
            cur = {"turn": s, "actions": {}}
            turns.append(cur)
            last = None
        elif cur is None:
            continue
        elif s.startswith("*"):
            m = re.match(r"\*\s*([A-Za-z]+)[:\s]+(.+)$", s)
            if m and last:
                mv, tgt = _split_target(m.group(2))
                cur["actions"][last]["by_ad"][m.group(1).title()] = (mv, tgt)
        else:
            m = re.match(r"(P[1-4])\s*[-–:]\s*(.*)$", s)
            if m:
                rest, tgt = _split_target(m.group(2))
                mon, mv = split_action(rest)
                cur["actions"][m.group(1)] = {"mon": mon, "move": mv,
                                              "target": tgt, "by_ad": {}}
                last = m.group(1)
    return turns


class MovesWindow:
    def __init__(self, app, raid):
        self.app, self.raid = app, raid
        self.strats = strat_names(raid)
        self.strat = self.strats[0] if self.strats else None
        self.turns, self.ads = [], []

        self.win = win = tk.Toplevel(app.root)
        win.title(f"{raid} · moves")
        win.transient(app.root)

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        # default: the positions this character has a valid team for; a manual
        # tick set (per raid) overrides it once the player touches a checkbox.
        saved = app.prefs.get("moves_cols")
        saved = saved.get(raid) if isinstance(saved, dict) else None
        if saved is None:
            valid = [p for p in POSITIONS
                     if evaluate_position(raid, p, app._paste_path(raid, p)) == "valid"]
            saved = valid or POSITIONS
        checked = set(saved)
        self.col_vars = {p: tk.BooleanVar(value=p in checked) for p in POSITIONS}

        top = ttk.Frame(frame)
        top.pack(fill="x")

        self.ad_var = tk.StringVar()
        self.ad_lbl = ttk.Label(top, text="Ad")
        self.ad_cb = ttk.Combobox(top, state="readonly", width=13,
                                  textvariable=self.ad_var)
        self.ad_cb.bind("<<ComboboxSelected>>", self._on_ad)

        if len(self.strats) > 1:
            self.strat_var = tk.StringVar(value=self.strat)
            sb = ttk.Combobox(top, state="readonly", width=16,
                              textvariable=self.strat_var, values=self.strats)
            sb.pack(side="left")
            sb.bind("<<ComboboxSelected>>", self._change_strat)

        self.body = ttk.Frame(frame)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        self.table = None

        self.info = ttk.Label(frame, text="", foreground=theme.FG_DIM)
        self.info.pack(fill="x", pady=(8, 0))

        win.bind("<Escape>", lambda e: win.destroy())
        self._reload()
        center_over(win, app.root)

    # ---- data ----
    def _reload(self):
        path = (os.path.join(STRATS, self.raid, self.strat + ".txt")
                if self.strat else None)
        self.turns = parse_moves(path) if path else []
        self.done = set()  # turn indices ticked off during the raid
        self._refresh_ads()
        if self.turns:
            self.info.config(text=f"{len(self.turns)} turns   ·   strat: {self.strat}")
        else:
            self.info.config(text=f"No [Moves] table in {self.strat or 'this raid'}.")
        self._build_table()

    def _refresh_ads(self):
        seen = []
        for t in self.turns:
            for a in t["actions"].values():
                for ad in a["by_ad"]:
                    if ad not in seen:
                        seen.append(ad)
        self.ads = seen
        self.ad_cb.pack_forget()
        self.ad_lbl.pack_forget()
        if self.ads:
            self.ad_cb["values"] = self.ads
            cur = self.app.prefs.get("moves_ad")
            self.ad_var.set(cur if cur in self.ads else self.ads[0])
            self.ad_cb.pack(side="right")
            self.ad_lbl.pack(side="right", padx=(0, 4))

    def _change_strat(self, _=None):
        self.strat = self.strat_var.get()
        self._reload()

    def _on_ad(self, _=None):
        self.app.prefs.set("moves_ad", self.ad_var.get())
        self._build_table()

    def _on_check(self):
        cols = self.app.prefs.get("moves_cols")
        cols = dict(cols) if isinstance(cols, dict) else {}
        cols[self.raid] = [p for p in POSITIONS if self.col_vars[p].get()]
        self.app.prefs.set("moves_cols", cols)
        self._paint()

    # ---- table ----
    def _cell_text(self, act):
        """-> (mon, move-line) for the selected ad. The move line carries the
        target ('Captivate  → Ad') when it isn't the default boss."""
        if act is None:
            return "", ""
        if act["by_ad"]:
            mv, tgt = act["by_ad"].get(self.ad_var.get(), ("", ""))
        else:
            mv, tgt = act["move"], act["target"]
        return act["mon"], f"{mv}  → {tgt}" if tgt else mv

    def _build_table(self):
        if self.table is not None:
            self.table.destroy()
        self.table = ttk.Frame(self.body)
        self.table.pack(anchor="nw")

        bold = ("TkDefaultFont", 9, "bold")
        # (turn index, position or None, [(label, normal_fg), ...])
        self._painters = []

        ttk.Label(self.table, text="", width=7).grid(row=0, column=0, sticky="w")
        for c, p in enumerate(POSITIONS, start=1):
            ttk.Checkbutton(self.table, text=p, variable=self.col_vars[p],
                            command=self._on_check).grid(
                row=0, column=c, sticky="w", padx=1, pady=(0, 3))

        for i, turn in enumerate(self.turns):
            tl = ttk.Label(self.table, text=turn["turn"], anchor="nw")
            tl.grid(row=i + 1, column=0, sticky="nw", padx=(0, 8), pady=3)
            self._painters.append((i, None, [(tl, theme.FG)]))
            for c, p in enumerate(POSITIONS, start=1):
                mon, mv = self._cell_text(turn["actions"].get(p))
                cell = ttk.Frame(self.table, relief="solid", borderwidth=1,
                                 padding=(6, 3), cursor="hand2")
                clickable = [cell]
                img = sprites.sprite(mon, 40) if mon else None
                if img:
                    il = ttk.Label(cell, image=img, cursor="hand2")
                    il.image = img
                    il.pack(anchor="w")
                    clickable.append(il)
                nl = ttk.Label(cell, text=mon or "–", font=bold, cursor="hand2")
                ml = ttk.Label(cell, text=mv, foreground=theme.MOVE_FG, cursor="hand2")
                nl.pack(anchor="w")
                ml.pack(anchor="w")
                cell.grid(row=i + 1, column=c, sticky="ew", padx=1, pady=1)
                self._painters.append((i, p, [(nl, theme.FG), (ml, theme.MOVE_FG)]))
                for w in clickable + [nl, ml]:
                    w.bind("<Button-1>", lambda e, n=i: self._toggle_row(n))

        for c in range(1, len(POSITIONS) + 1):
            self.table.columnconfigure(c, weight=1, uniform="pos")

        self._paint()
        self.win.geometry("")  # shrink-wrap to the table

    def _toggle_row(self, i):
        self.done.symmetric_difference_update({i})
        self._paint()

    def _paint(self):
        for turn_i, pos, items in self._painters:
            muted = turn_i in self.done or (
                pos is not None and not self.col_vars[pos].get())
            for lbl, fg in items:
                lbl.configure(foreground=theme.MUTED if muted else fg)
