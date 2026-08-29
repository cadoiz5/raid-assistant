#!/usr/bin/env python3
"""
moves_window.py - the in-raid move order.

A strat file may carry a "[Moves]" section: one "Turn N" block per turn, and
under it up to four "P<n> - <what to click>" lines. This window shows that as a
turn x position table (mon name over the move). A checkbox on each P1..P4
header greys out that column (for positions you aren't playing); clicking a
turn's row greys it out (turn done).
"""

import os
import re
import tkinter as tk
from tkinter import ttk

from scan_window import HERE, STRATS, center_over, strat_names

POSITIONS = ["P1", "P2", "P3", "P4"]

try:
    with open(os.path.join(HERE, "data", "moves.txt"), encoding="utf-8") as _fh:
        _MOVES = sorted((ln.strip() for ln in _fh
                         if ln.strip() and not ln.startswith("#")),
                        key=len, reverse=True)
except OSError:
    _MOVES = []


def parse_moves(path):
    """-> [{'turn': 'Turn 1', 'actions': {'P1': '...', ...}}, ...] from the
    file's [Moves] section ([] if there isn't one)."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    turns, cur, in_moves = [], None, False
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        head = re.match(r"\[([^\]]+)\]$", s)
        if head:
            in_moves = head.group(1).strip().lower() == "moves"
            cur = None
            continue
        if not in_moves:
            continue
        if re.match(r"turn\b", s, re.I):
            cur = {"turn": s, "actions": {}}
            turns.append(cur)
        elif cur is not None:
            m = re.match(r"(P[1-4])\s*[-–:]\s*(.+)$", s)
            if m:
                cur["actions"][m.group(1)] = m.group(2).strip()
    return turns


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


class MovesWindow:
    def __init__(self, app, raid):
        self.app, self.raid = app, raid
        self.strats = strat_names(raid)
        self.strat = self.strats[0] if self.strats else None
        self.turns = []

        self.win = win = tk.Toplevel(app.root)
        win.title(f"{raid} · moves")
        win.transient(app.root)

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        checked = set(app.prefs.get("moves_cols") or POSITIONS)
        self.col_vars = {p: tk.BooleanVar(value=p in checked) for p in POSITIONS}

        if len(self.strats) > 1:
            top = ttk.Frame(frame)
            top.pack(fill="x")
            self.strat_var = tk.StringVar(value=self.strat)
            sb = ttk.Combobox(top, state="readonly", width=16,
                              textvariable=self.strat_var, values=self.strats)
            sb.pack(side="right")
            sb.bind("<<ComboboxSelected>>", self._change_strat)

        self.body = ttk.Frame(frame)
        self.body.pack(fill="both", expand=True, pady=(8, 0))
        self.table = None

        self.info = ttk.Label(frame, text="", foreground="#888")
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
        if self.turns:
            self.info.config(text=f"{len(self.turns)} turns   ·   strat: {self.strat}")
        else:
            self.info.config(text=f"No [Moves] table in {self.strat or 'this raid'}.")
        self._build_table()

    def _change_strat(self, _=None):
        self.strat = self.strat_var.get()
        self._reload()

    def _on_check(self):
        self.app.prefs.set("moves_cols",
                           [p for p in POSITIONS if self.col_vars[p].get()])
        self._paint()

    # ---- table ----
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
            self._painters.append((i, None, [(tl, "#000000")]))
            for c, p in enumerate(POSITIONS, start=1):
                mon, mv = split_action(turn["actions"].get(p, ""))
                cell = ttk.Frame(self.table, relief="solid", borderwidth=1,
                                 padding=(6, 3), cursor="hand2")
                nl = ttk.Label(cell, text=mon or "–", font=bold, cursor="hand2")
                ml = ttk.Label(cell, text=mv, foreground="#606060", cursor="hand2")
                nl.pack(anchor="w")
                ml.pack(anchor="w")
                cell.grid(row=i + 1, column=c, sticky="ew", padx=1, pady=1)
                self._painters.append((i, p, [(nl, "#000000"), (ml, "#606060")]))
                for w in (cell, nl, ml):
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
                lbl.configure(foreground="#bcbcbc" if muted else fg)
