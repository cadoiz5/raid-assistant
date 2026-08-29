#!/usr/bin/env python3
"""
scan_window.py - the per-position scan window, opened from a grid cell in app.py.

Clicking "Heatran · P1" opens ScanWindow(app, "Heatran", "P1"):
  - loads the raid's strat (strats/Heatran/<strat>.txt) and its [P1] section
  - left:  the 6 team slots, each with a status glyph
             ○ not scanned   ✓ scanned & valid   ✗ scanned & invalid
             ...plus the "Set region" button below the list.
  - right: Capture + "Save edits" on one line, then the text box. Set the region
           once; a Capture then auto-saves into the selected slot's file,
           saves/<char>/<raid>/<Pn>.txt (one file per position, blank-line
           "N - ..." blocks). "Save edits" persists manual text-box edits.

Validation of a scanned slot against its strat entry (see strats/FORMAT.md):
  1. species matches exactly
  2. item matches exactly       (skipped if the strat pins no item)
  3. ability matches exactly     (skipped if strat pins none, or says "any")
  4. final stats satisfy the bounds   (N / N+ / N- / N-M)
  5. every strat move is present in the scanned move set
"""

import json
import os
import re
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "screenshot")
STRATS = os.path.join(HERE, "strats")

STATUS_GLYPH = {"none": "○", "scanned": "●", "valid": "✓", "invalid": "✗"}
STATS = ["HP", "Atk", "Def", "SpA", "SpD", "Spe"]
INF = float("inf")
EV_CAP = 510

# nature -> (index of the +10% stat, index of the -10% stat) in STATS; None = neutral
NATURES = {
    "hardy": (None, None), "lonely": (1, 2), "brave": (1, 5), "adamant": (1, 3),
    "naughty": (1, 4), "bold": (2, 1), "docile": (None, None), "relaxed": (2, 5),
    "impish": (2, 3), "lax": (2, 4), "timid": (5, 1), "hasty": (5, 2),
    "serious": (None, None), "jolly": (5, 3), "naive": (5, 4), "modest": (3, 1),
    "mild": (3, 2), "quiet": (3, 5), "bashful": (None, None), "rash": (3, 4),
    "calm": (4, 1), "gentle": (4, 2), "sassy": (4, 5), "careful": (4, 3),
    "quirky": (None, None),
}

try:
    with open(os.path.join(HERE, "species_stats.json"), encoding="utf-8") as _fh:
        BASE_STATS = json.load(_fh)  # {"Golduck": [hp, atk, def, spa, spd, spe], ...}
except (OSError, ValueError):
    BASE_STATS = {}


def run_script(*args):
    p = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                       text=True, encoding="utf-8", errors="replace", cwd=HERE)
    return p.stdout.strip(), p.stderr.strip(), p.returncode


def center_over(win, parent):
    """Position a Toplevel centered on the parent window."""
    win.update_idletasks()
    w = win.winfo_width() if win.winfo_width() > 1 else win.winfo_reqwidth()
    h = win.winfo_height() if win.winfo_height() > 1 else win.winfo_reqheight()
    x = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
    y = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# ---------------- strat files ----------------
def strat_names(raid):
    d = os.path.join(STRATS, raid)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".txt"))


def _parse_block(block):
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    m = re.match(r"(\d+)\s*-\s*(.+)", lines[0]) if lines else None
    if not m:
        return None
    species, _, item = m.group(2).partition("@")
    slot = {"num": int(m.group(1)), "species": species.strip(),
            "item": item.strip() or None, "ability": None,
            "bounds": {}, "moves": [], "raw": block.strip()}
    for ln in lines[1:]:
        if ln.lower().startswith("ability:"):
            slot["ability"] = ln.split(":", 1)[1].strip()
        elif ln.startswith("-"):
            slot["moves"].append(ln[1:].strip())
        elif re.search(r"\d.*\b(?:HP|Atk|Def|SpA|SpD|Spe)\b", ln):
            slot["bounds"].update(_parse_bounds(ln))
    return slot


def _parse_bounds(line):
    """'301 HP / 294+ Spe / 180-226 Def' -> {'HP': (301,301), 'Spe': (294,inf), ...}"""
    out = {}
    for entry in line.split("/"):
        m = re.match(r"\s*(\d+)\s*(\+|-\d+|-)?\s*(HP|Atk|Def|SpA|SpD|Spe)\s*$", entry)
        if not m:
            continue
        n, mod, stat = int(m.group(1)), m.group(2), m.group(3)
        if mod is None:
            out[stat] = (n, n)
        elif mod == "+":
            out[stat] = (n, INF)
        elif mod == "-":
            out[stat] = (0, n)
        else:  # "-226"
            out[stat] = (n, int(mod[1:]))
    return out


def _fmt_bound(lo, hi):
    if lo == hi:
        return str(lo)
    if hi == INF:
        return f"{lo}+"
    if lo == 0:
        return f"{hi}-"
    return f"{lo}-{hi}"


def parse_strat(path):
    """-> {'P1': [slot, ...], ...}  (slot dicts, one per numbered block)."""
    sections, cur, buf = {}, None, []

    def flush():
        if cur and buf:
            slot = _parse_block("\n".join(buf))
            if slot:
                sections.setdefault(cur, []).append(slot)
        buf.clear()

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.rstrip("\n")
            if s.strip().startswith("#"):
                continue
            header = re.match(r"\[(P[1-4])\]\s*$", s.strip())
            if header:
                flush()
                cur = header.group(1)
            elif not s.strip():
                flush()
            else:
                buf.append(s)
        flush()
    return sections


# ---------------- scanned paste ----------------
def _stat_line(s):
    """'8 HP / 16 Def / 252 Spe' -> {'HP': 8, 'Def': 16, 'Spe': 252}"""
    out = {}
    for part in s.split("/"):
        m = re.match(r"\s*(\d+)\s+([A-Za-z]+)", part)
        if m:
            out[m.group(2)] = int(m.group(1))
    return out


def parse_scan(block):
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    head = re.sub(r"^\d+\s*-\s*", "", lines[0]) if lines else ""
    name_part, _, item = head.partition("@")
    d = {"species": re.sub(r"\((?:M|F)\)", "", name_part).strip(),
         "item": item.strip() or None, "ability": None, "nature": None,
         "stats": {}, "evs": {}, "ivs": {}, "moves": []}
    for ln in lines[1:]:
        low = ln.lower()
        if low.startswith("ability:"):
            d["ability"] = ln.split(":", 1)[1].strip()
        elif low.startswith("stats:"):
            d["stats"] = _stat_line(ln.split(":", 1)[1])
        elif low.startswith("evs:"):
            d["evs"] = _stat_line(ln.split(":", 1)[1])
        elif low.startswith("ivs:"):
            d["ivs"] = _stat_line(ln.split(":", 1)[1])
        elif low.endswith(" nature"):
            d["nature"] = ln.rsplit(" ", 1)[0].strip()
        elif ln.startswith("-"):
            d["moves"].append(ln[1:].strip())
    return d


# ---------------- EV-fix suggestion ----------------
def _final_stat(base, iv, ev, mult):
    core = 2 * base + iv + ev // 4
    return core + 110 if mult is None else int((core + 5) * mult)


def _ev_window(base, iv, mult, lo, hi):
    """Smallest / largest EV (snapped to multiples of 4) whose final stat is in
    [lo, hi]. None if no EV 0..252 works."""
    feas = [e for e in range(0, 253) if lo <= _final_stat(base, iv, e, mult) <= hi]
    if not feas:
        return None
    ev_lo = -(-feas[0] // 4) * 4          # ceil to /4
    ev_hi = (feas[-1] // 4) * 4           # floor to /4
    return (ev_lo, ev_hi) if ev_lo <= ev_hi else (feas[0], feas[-1])


def suggest_evs(species, scan, bounds):
    """-> ('breed', None)          a bound can't be met by EVs (wrong nature/IV)
          ('ok', {stat: new_ev})   the EVs that should change
          None                     not enough data to compute
    Objective: fewest stats changed, then fewest total EV points moved.
    """
    base = BASE_STATS.get(species)
    nat = NATURES.get((scan.get("nature") or "").lower())
    if not base or nat is None:
        return None
    plus, minus = nat
    ivs, cur_ev = scan.get("ivs", {}), scan.get("evs", {})
    cur = {s: cur_ev.get(s, 0) for s in STATS}
    mult = lambda i: None if i == 0 else 1.1 if i == plus else 0.9 if i == minus else 1.0

    target, changed, windows = dict(cur), set(), {}
    for stat, (lo, hi) in bounds.items():
        i = STATS.index(stat)
        w = _ev_window(base[i], ivs.get(stat, 31), mult(i), lo, hi)
        if w is None:
            return ("breed", None)
        windows[stat] = w
        if cur[stat] < w[0]:
            target[stat] = w[0]
            changed.add(stat)
        elif cur[stat] > w[1]:
            target[stat] = w[1]
            changed.add(stat)

    excess = sum(target.values()) - EV_CAP
    if excess > 0:  # reclaim: unconstrained stats first (most EVs), then constrained to min
        for stat in sorted((s for s in STATS if s not in bounds), key=lambda s: -target[s]):
            take = min(target[stat], excess)
            if take:
                target[stat] -= take
                excess -= take
                changed.add(stat)
        for stat, (elo, _hi) in windows.items():
            if excess <= 0:
                break
            take = min(target[stat] - elo, excess)
            if take > 0:
                target[stat] -= take
                excess -= take
                changed.add(stat)
        if excess > 0:
            return ("breed", None)  # bounds genuinely can't fit in the EV budget

    return ("ok", {s: target[s] for s in changed})


def load_scans(path):
    """saves/<char>/<raid>/<Pn>.txt -> {slot_num: block_text}."""
    scans = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for block in re.split(r"\n\s*\n", fh.read().strip()):
                m = re.match(r"(\d+)\s*-\s*", block.strip())
                if m:
                    scans[int(m.group(1))] = block.strip()
    return scans


def validate(slot, block):
    """Return a list of failure strings ([] == valid)."""
    scan = parse_scan(block)
    # wrong species: nothing else matters until it's the right Pokemon
    if _norm(scan["species"]) != _norm(slot["species"]):
        return [f"species: want {slot['species']}, got {scan['species'] or '?'}"]
    fails = []
    if slot["item"] and _norm(scan["item"]) != _norm(slot["item"]):
        fails.append(f"item: want {slot['item']}, got {scan['item'] or 'none'}")
    if slot["ability"] and slot["ability"].strip().lower() != "any":
        if _norm(scan["ability"]) != _norm(slot["ability"]):
            fails.append(f"ability: want {slot['ability']}, got {scan['ability'] or '?'}")
    bad_stat = False
    for stat, (lo, hi) in slot["bounds"].items():
        val = scan["stats"].get(stat)
        if val is None:
            fails.append(f"{stat}: not scanned")
        elif not lo <= val <= hi:
            fails.append(f"{stat} {val}, need {_fmt_bound(lo, hi)}")
            bad_stat = True
    if bad_stat:
        sug = suggest_evs(slot["species"], scan, slot["bounds"])
        if sug and sug[0] == "breed":
            fails.append("→ can't fix with EVs — wrong breed")
        elif sug and sug[0] == "ok" and sug[1]:
            parts = []
            for s in STATS:
                if s in sug[1]:
                    d = sug[1][s] - scan.get("evs", {}).get(s, 0)
                    parts.append(f"{s} {sug[1][s]} ({d:+d})")
            fails.append("→ EVs: " + ", ".join(parts))
    scanned_moves = {_norm(m) for m in scan["moves"]}
    for mv in slot["moves"]:
        if _norm(mv) not in scanned_moves:
            fails.append(f"missing move: {mv}")
    return fails


def evaluate_position(raid, position, scan_path):
    """Grid-cell state for a (raid, position): one of
    'empty' / 'partial' / 'invalid' / 'valid'. Uses the raid's first strat."""
    scans = load_scans(scan_path)
    if not scans:
        return "empty"
    names = strat_names(raid)
    slots = []
    if names:
        slots = parse_strat(os.path.join(STRATS, raid, names[0] + ".txt")).get(position, [])
    by_num = {s["num"]: s for s in slots}
    any_invalid = any(by_num.get(n) and validate(by_num[n], block)
                      for n, block in scans.items())
    if any_invalid:
        return "invalid"
    if len(scans) >= (len(slots) or 6):
        return "valid"
    return "partial"


# ---------------- window ----------------
class ScanWindow:
    def __init__(self, app, raid, position):
        self.app = app
        self.raid = raid
        self.position = position
        self.active = None  # selected slot number

        self.strats = strat_names(raid)
        self.strat = self.strats[0] if self.strats else None
        self.scans = self._load_scans()

        self.win = win = tk.Toplevel(app.root)
        win.title(f"{raid} · {position}")
        win.transient(app.root)
        win.geometry("650x470")

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)

        top = ttk.Frame(frame)
        top.pack(fill="x")
        ttk.Label(top, text=f"{app.character}   ·   {raid}   ·   {position}",
                  font=("TkDefaultFont", 10, "bold")).pack(side="left")
        if len(self.strats) > 1:
            self.strat_var = tk.StringVar(value=self.strat)
            cb = ttk.Combobox(top, state="readonly", width=18, values=self.strats,
                              textvariable=self.strat_var)
            cb.pack(side="right")
            cb.bind("<<ComboboxSelected>>", self._change_strat)
        elif self.strat:
            ttk.Label(top, text=f"strat: {self.strat}", foreground="#888").pack(side="right")
        else:
            ttk.Label(top, text="no strat defined", foreground="#a00").pack(side="right")

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, pady=(8, 0))

        # left: slot list
        left = ttk.Frame(body)
        left.pack(side="left", fill="y")
        ttk.Label(left, text=f"Team ({position})").pack(anchor="w")
        self.listbox = tk.Listbox(left, height=6, width=20, activestyle="dotbox",
                                  font=("TkDefaultFont", 10), exportselection=False)
        self.listbox.pack(pady=(2, 6))
        self.listbox.bind("<<ListboxSelect>>", self._select)
        ttk.Button(left, text="Set region", command=self.set_region).pack(anchor="w")
        ttk.Label(left, text="○ not scanned\n✓ valid    ✗ invalid",
                  foreground="#888", font=("TkDefaultFont", 8)).pack(anchor="w", pady=(6, 0))

        ttk.Separator(body, orient="vertical").pack(side="left", fill="y", padx=10)

        # right: capture panel
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.target_lbl = ttk.Label(right, text="select a slot →", foreground="#666",
                                    font=("Consolas", 9), justify="left")
        self.target_lbl.pack(anchor="w")
        self.check_lbl = ttk.Label(right, text="", foreground="#888",
                                   font=("TkDefaultFont", 9), justify="left")
        self.check_lbl.pack(anchor="w", pady=(2, 6))

        bar = ttk.Frame(right)
        bar.pack(fill="x")
        self.capture_btn = ttk.Button(bar, text="Capture", command=self.capture,
                                      state="disabled")  # needs bbox + a selected slot
        self.capture_btn.pack(side="left")
        self.save_btn = ttk.Button(bar, text="Save edits", command=self.save,
                                   state="disabled")
        self.save_btn.pack(side="left", padx=6)
        self.region_lbl = ttk.Label(bar, text=self._region_text(), foreground="#888")
        self.region_lbl.pack(side="right")

        self.text = tk.Text(right, font=("Consolas", 10), wrap="none", height=10,
                            relief="solid", borderwidth=1, undo=True)
        self.text.pack(fill="both", expand=True, pady=(6, 6))
        self._baseline = ""  # text-box content that matches disk
        self.text.bind("<<Modified>>", self._on_text_change)

        self.status = ttk.Label(frame, text="", foreground="#888")
        self.status.pack(fill="x", pady=(6, 0))

        win.bind("<Escape>", lambda e: win.destroy())
        self._load_strat()
        self._refresh_list()
        center_over(win, app.root)

    # ---- strat / slots ----
    def _load_strat(self):
        self.slots = []
        if self.strat:
            path = os.path.join(STRATS, self.raid, self.strat + ".txt")
            self.slots = sorted(parse_strat(path).get(self.position, []),
                                key=lambda s: s["num"])
        if not self.slots:
            self.slots = [{"num": i, "species": f"Slot {i}", "item": None,
                           "ability": None, "bounds": {}, "moves": [],
                           "raw": f"(slot {i} — no strat)"} for i in range(1, 7)]

    def _slot_by_num(self, num):
        return next((s for s in self.slots if s["num"] == num), None)

    def _change_strat(self, _=None):
        self.strat = self.strat_var.get()
        self.active = None
        self.target_lbl.config(text="select a slot →")
        self.check_lbl.config(text="")
        self._set_text("")
        self._sync_capture_btn()
        self._load_strat()
        self._refresh_list()

    def _slot_status(self, num):
        if num not in self.scans:
            return "none"
        slot = self._slot_by_num(num)
        if not slot:
            return "scanned"
        return "valid" if not validate(slot, self.scans[num]) else "invalid"

    def _refresh_list(self):
        keep = self.active
        self.listbox.delete(0, "end")
        for s in self.slots:
            g = STATUS_GLYPH[self._slot_status(s["num"])]
            self.listbox.insert("end", f" {g}  {s['species']}")
        if keep is not None:
            for i, s in enumerate(self.slots):
                if s["num"] == keep:
                    self.listbox.selection_set(i)

    def _show_check(self, num):
        if num not in self.scans:
            self.check_lbl.config(text="", foreground="#888")
            return
        slot = self._slot_by_num(num)
        fails = validate(slot, self.scans[num]) if slot else []
        if fails:
            self.check_lbl.config(text="✗  " + "\n    ".join(fails), foreground="#c00")
        else:
            self.check_lbl.config(text="✓  valid", foreground="#080")

    def _sync_save_btn(self):
        dirty = (self.active is not None
                 and self.text.get("1.0", "end").strip() != self._baseline)
        self.save_btn.config(state="normal" if dirty else "disabled")

    def _on_text_change(self, _=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self._sync_save_btn()

    def _sync_capture_btn(self):
        ok = self.app.bbox and self.active is not None
        self.capture_btn.config(state="normal" if ok else "disabled")

    def _set_text(self, content):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self._baseline = self.text.get("1.0", "end").strip()
        self.text.edit_modified(False)
        self._sync_save_btn()

    # ---- saved scans (one file per position) ----
    def _scan_path(self):
        return self.app._paste_path(self.raid, self.position)

    def _load_scans(self):
        return load_scans(self.app._paste_path(self.raid, self.position))

    def _write_scans(self):
        path = self._scan_path()
        if self.scans:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n\n".join(self.scans[n] for n in sorted(self.scans)) + "\n")
        elif os.path.isfile(path):
            os.remove(path)

    # ---- helpers ----
    def _region_text(self):
        if not self.app.bbox:
            return "region: not set"
        x1, y1, x2, y2 = self.app.bbox
        return f"region: {x2 - x1}×{y2 - y1} @ {x1},{y1}"

    def _status(self, msg):
        self.status.config(text=msg)
        self.win.update_idletasks()

    def _show_capture(self, out, err):
        self._set_text(out or "(nothing recognised)")
        self._status(err.splitlines()[-1] if err else "captured")

    # ---- events ----
    def _select(self, _=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        slot = self.slots[sel[0]]
        self.active = slot["num"]
        self.target_lbl.config(text=re.sub(r"^\d+\s*-\s*", "", slot["raw"]))
        body = ""
        if self.active in self.scans:
            body = re.sub(r"^\s*\d+\s*-\s*", "", self.scans[self.active], count=1)
        self._set_text(body)
        self._sync_capture_btn()
        self._show_check(self.active)

    def set_region(self):
        self._status("drag a box around the card...")
        out, _err, code = run_script("--select-only")
        nums = [int(n) for n in re.findall(r"-?\d+", out)]
        if code != 0 or len(nums) != 4:
            self._status("region unchanged")
            return
        self.app.bbox = tuple(nums)
        self.app.prefs.set("scan_region", nums)
        self.region_lbl.config(text=self._region_text())
        self._sync_capture_btn()
        self._status("region set" + (" - pick a slot" if self.active is None else ""))

    def capture(self):
        if not self.app.bbox or self.active is None:
            return
        self._status("capturing...")
        out, err, _ = run_script("--bbox", ",".join(map(str, self.app.bbox)))
        self._show_capture(out, err)
        if out:
            self.save()  # auto-save the fresh scan into the selected slot

    def open_image(self):
        # no button for now - kept for later / manual use
        path = filedialog.askopenfilename(parent=self.win, filetypes=[
            ("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if not path:
            return
        self._status("reading...")
        out, err, _ = run_script("--image", path)
        self._show_capture(out, err)
        if out and self.active is not None:
            self.save()

    def save(self):
        if self.active is None:
            return
        n = self.active
        text = self.text.get("1.0", "end").strip()
        if text:
            first, *rest = text.splitlines()
            first = re.sub(r"^\s*\d+\s*-\s*", "", first.strip())
            self.scans[n] = "\n".join([f"{n} - {first}", *rest]).strip()
            self._status(f"saved  ·  {self._slot_by_num(n)['species']}")
        else:
            self.scans.pop(n, None)
            self._status("slot cleared")
        self._write_scans()
        self._baseline = self.text.get("1.0", "end").strip()
        self.text.edit_modified(False)
        self._refresh_list()
        self._show_check(n)
        self._sync_save_btn()
        self.app.refresh_grid()
