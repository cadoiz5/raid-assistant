#!/usr/bin/env python3
"""
moves_window.py - the in-raid move order.

A strat file may carry a "[Moves]" section: one "Turn N" block per turn, and
under it up to four "P<n> - <what to click>" lines. This window shows that as a
turn x position table, with a toggle to see every position or just one.
"""

import os
import re
import tkinter as tk
from tkinter import ttk

from scan_window import STRATS, center_over, strat_names

POSITIONS = ["P1", "P2", "P3", "P4"]


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


class MovesWindow:
    def __init__(self, app, raid):
        self.app, self.raid = app, raid
        self.strats = strat_names(raid)
        self.strat = self.strats[0] if self.strats else None

        self.win = win = tk.Toplevel(app.root)
        win.title(f"{raid} · moves")
        win.transient(app.root)
        win.geometry("620x420")

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=f"{raid}   ·   move order",
                  font=("TkDefaultFont", 10, "bold")).pack(side="left")

        self.view_var = tk.StringVar(
            value=app.prefs.get("moves_view") or "All positions")
        vb = ttk.Combobox(top, state="readonly", width=13, textvariable=self.view_var,
                          values=["All positions", *POSITIONS])
        vb.pack(side="right")
        vb.bind("<<ComboboxSelected>>", self._apply_view)

        if len(self.strats) > 1:
            self.strat_var = tk.StringVar(value=self.strat)
            sb = ttk.Combobox(top, state="readonly", width=16,
                              textvariable=self.strat_var, values=self.strats)
            sb.pack(side="right", padx=(0, 8))
            sb.bind("<<ComboboxSelected>>", self._change_strat)

        self.tree = ttk.Treeview(frame, columns=POSITIONS, show="tree headings",
                                 selectmode="none")
        self.tree.heading("#0", text="Turn")
        self.tree.column("#0", width=90, stretch=False, anchor="w")
        for p in POSITIONS:
            self.tree.heading(p, text=p)
            self.tree.column(p, width=120, anchor="w")
        self.tree.pack(fill="both", expand=True, pady=(8, 0))

        self.info = ttk.Label(frame, text="", foreground="#888")
        self.info.pack(fill="x", pady=(6, 0))

        win.bind("<Escape>", lambda e: win.destroy())
        self._load()
        self._apply_view()
        center_over(win, app.root)

    def _load(self):
        self.tree.delete(*self.tree.get_children())
        path = (os.path.join(STRATS, self.raid, self.strat + ".txt")
                if self.strat else None)
        turns = parse_moves(path) if path else []
        for t in turns:
            self.tree.insert("", "end", text=t["turn"],
                             values=tuple(t["actions"].get(p, "–")
                                          for p in POSITIONS))
        if not turns:
            self.info.config(text=f"No [Moves] table in {self.strat or 'this raid'}.")
        else:
            self.info.config(text=f"{len(turns)} turns   ·   strat: {self.strat}")

    def _change_strat(self, _=None):
        self.strat = self.strat_var.get()
        self._load()
        self._apply_view()

    def _apply_view(self, event=None):
        v = self.view_var.get()
        if event is not None:            # a real toggle, not the initial layout
            self.app.prefs.set("moves_view", v)
        self.tree["displaycolumns"] = (
            POSITIONS if v == "All positions" else (v,))
