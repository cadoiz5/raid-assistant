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
from tkinter import ttk, filedialog, messagebox

import theme

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "screenshot.py")
STRATS = os.path.join(HERE, "strats")

STATUS_GLYPH = {"none": "○", "scanned": "●", "valid": "✓", "invalid": "✗"}
STATUS_MARK = {"pass": "✓", "fail": "✗", "na": "–", "blocked": "⋯", "missing": "?"}
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
    with open(os.path.join(HERE, "data", "species_stats.json"), encoding="utf-8") as _fh:
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


try:
    with open(os.path.join(HERE, "data", "no_breed.txt"), encoding="utf-8") as _fh:
        # species whose IVs can't come from breeding; a legendary can re-roll its
        # IVs in-game, so tell the player which IVs to aim for instead of "wrong breed"
        NO_BREED = {_norm(ln) for ln in _fh if ln.strip() and not ln.startswith("#")}
except OSError:
    NO_BREED = set()

try:
    with open(os.path.join(HERE, "data", "evolutions.json"), encoding="utf-8") as _fh:
        EVOLUTIONS = json.load(_fh)  # {from: [{to, type, val, item}, ...]}
except (OSError, ValueError):
    EVOLUTIONS = {}

try:
    with open(os.path.join(HERE, "data", "species_abilities.json"), encoding="utf-8") as _fh:
        _AB = json.load(_fh)  # {species: [slot1, slot2, hidden-or-null]}
    SPECIES_ABILITIES = {_norm(k): [a for a in v if a] for k, v in _AB.items()}
    HIDDEN_ABILITY = {_norm(k): v[2] for k, v in _AB.items() if v[2]}
except (OSError, ValueError):
    SPECIES_ABILITIES, HIDDEN_ABILITY = {}, {}

try:
    with open(os.path.join(HERE, "data", "egg_moves.json"), encoding="utf-8") as _fh:
        EGG_MOVES = {_norm(k): {_norm(m) for m in v} for k, v in json.load(_fh).items()}
except (OSError, ValueError):
    EGG_MOVES = {}


def evo_path(frm, to):
    """List of evolution steps from `frm` up to `to`, or None if `to` isn't a
    later evolution of `frm`."""
    want = _norm(to)
    seen, queue = {_norm(frm)}, [(frm, [])]
    while queue:
        cur, path = queue.pop(0)
        for step in EVOLUTIONS.get(cur, []):
            if _norm(step["to"]) == want:
                return path + [step]
            if _norm(step["to"]) not in seen:
                seen.add(_norm(step["to"]))
                queue.append((step["to"], path + [step]))
    return None


def _evo_how(step):
    """Compact 'how to evolve' note for one step: 'Lvl 30' / 'Dawn Stone' / …"""
    if step.get("item"):
        return step["item"]
    t = step.get("type", "")
    if t.startswith("LEVEL") and isinstance(step.get("val"), int) and 1 <= step["val"] <= 100:
        return f"Lvl {step['val']}"
    if t.startswith("TRADE"):
        return "trade"
    if t.startswith("HAPPINESS"):
        return "friendship"
    return "level up"


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
            "item": [i.strip() for i in item.split("/") if i.strip()] or None,
            "ability": None, "bounds": {}, "moves": [], "raw": block.strip()}
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
            header = re.match(r"\[([^\]]+)\]\s*$", s.strip())
            if header:
                flush()
                sec = header.group(1)
                cur = sec if re.fullmatch(r"P[1-4]", sec) else None
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
         "level": None, "stats": {}, "evs": {}, "ivs": {}, "moves": []}
    d["has_ha"] = False
    for ln in lines[1:]:
        low = ln.lower()
        if low.startswith("ability:"):
            v = ln.split(":", 1)[1].strip()
            d["has_ha"] = bool(re.search(r"\(\s*ha\s*\)", v, re.I))
            d["ability"] = re.sub(r"\(\s*ha\s*\)", "", v, flags=re.I).strip()
        elif low.startswith("level:"):
            m = re.search(r"\d+", ln)
            d["level"] = int(m.group()) if m else None
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
    # drop impossible values from a row the OCR mislabelled (EVs landing in the
    # IVs line, etc.) so downstream maths doesn't choke on them
    d["ivs"] = {k: v for k, v in d["ivs"].items() if 0 <= v <= 31}
    d["evs"] = {k: v for k, v in d["evs"].items() if 0 <= v <= 252}
    return d


# ---------------- EV / IV / nature fix suggestions ----------------
def _final_stat(base, iv, ev, mult):
    core = 2 * base + iv + ev // 4
    return core + 110 if mult is None else int((core + 5) * mult)


def _mult_fn(nature):
    """nature name -> f(stat_index) giving the level-100 multiplier (None for HP).
    Returns None if the nature isn't recognised."""
    nat = NATURES.get((nature or "").lower())
    if nat is None:
        return None
    plus, minus = nat
    return lambda i: None if i == 0 else 1.1 if i == plus else 0.9 if i == minus else 1.0


def _project_stats(species, scan):
    """The level-100 stats `species` would have with this scan's IVs/EVs/nature -
    used when the scan is under level 100 or still a pre-evolution. {} if the
    base stats or nature aren't known."""
    base = BASE_STATS.get(species)
    mult = _mult_fn(scan.get("nature"))
    if not base or mult is None:
        return {}
    ivs, evs = scan.get("ivs", {}), scan.get("evs", {})
    return {s: _final_stat(base[i], ivs.get(s, 31), evs.get(s, 0), mult(i))
            for i, s in enumerate(STATS)}


def _exact_stat(base, iv, ev, sign, level=100):
    """PokeMMO stat by the exact integer formula. `sign`: None for HP, +1 for the
    nature-boosted stat, -1 for the hindered one, 0 otherwise. `level` defaults
    to 100 (where it collapses to core + 110 / (core + 5) * mult)."""
    scaled = (2 * base + iv + ev // 4) * level // 100
    if sign is None:
        return scaled + level + 10
    val = scaled + 5
    if sign > 0:
        return val * 11 // 10
    if sign < 0:
        return val * 9 // 10
    return val


def _scan_consistency(scan):
    """Recompute each shown stat from the scanned base / IV / EV / nature at the
    scanned level; if any disagree the OCR mangled a number (or the paste was
    hand-edited wrong). Returns "Final stats don't match EVs/IVs/Nature" or None.

    Only the stats the scan actually read an IV *and* a value for are checked;
    a missing EV counts as 0. Needs a recognised nature. Works at any level -
    the mon doesn't have to be 100."""
    base = BASE_STATS.get(scan.get("species"))
    nat = NATURES.get((scan.get("nature") or "").lower())
    if not base or nat is None:
        return None
    plus, minus = nat
    level = scan.get("level") or 100
    stats, ivs, evs = scan.get("stats") or {}, scan.get("ivs") or {}, scan.get("evs") or {}
    for i, s in enumerate(STATS):
        if s not in stats or s not in ivs:
            continue
        sign = None if i == 0 else 1 if i == plus else -1 if i == minus else 0
        if _exact_stat(base[i], ivs[s], evs.get(s, 0), sign, level) != stats[s]:
            return "Final stats don't match EVs/IVs/Nature"
    return None


def _stat_signs(nature):
    """[sign per STATS index] for a nature: None (HP), +1 boosted, -1 hindered, 0."""
    nat = NATURES.get((nature or "").lower())
    if nat is None:
        return None
    plus, minus = nat
    return [None if i == 0 else 1 if i == plus else -1 if i == minus else 0
            for i in range(len(STATS))]


def recompute_stats(scan):
    """The stats implied by the scanned base / IV / EV / nature at the scanned
    level. A stat whose IV wasn't read is left at its scanned value (can't
    recompute it); only if that's missing too is it computed at IV 31.
    -> {stat: value} or None if base stats / nature are unknown."""
    base = BASE_STATS.get(scan.get("species"))
    signs = _stat_signs(scan.get("nature"))
    if not base or signs is None:
        return None
    level = scan.get("level") or 100
    stats, ivs, evs = scan.get("stats") or {}, scan.get("ivs") or {}, scan.get("evs") or {}
    out = {}
    for i, s in enumerate(STATS):
        if s in ivs:
            out[s] = _exact_stat(base[i], ivs[s], evs.get(s, 0), signs[i], level)
        else:
            out[s] = stats.get(s, _exact_stat(base[i], 31, evs.get(s, 0), signs[i], level))
    return out


def solve_evs_for_stats(scan):
    """EVs that make base / IV / nature reproduce the scanned final stats. Only
    the stats that currently disagree are re-solved; the rest keep their scanned
    EV. -> {stat: ev} (all six) or None if a stat can't be hit within 0..252 or
    the total tops the EV cap."""
    base = BASE_STATS.get(scan.get("species"))
    signs = _stat_signs(scan.get("nature"))
    if not base or signs is None:
        return None
    level = scan.get("level") or 100
    stats, ivs = scan.get("stats") or {}, scan.get("ivs") or {}
    out = dict.fromkeys(STATS, 0)
    out.update({s: v for s, v in (scan.get("evs") or {}).items() if s in out})
    for i, s in enumerate(STATS):
        if s not in stats or s not in ivs:
            continue
        if _exact_stat(base[i], ivs[s], out[s], signs[i], level) == stats[s]:
            continue                       # this stat already lines up - leave it
        hit = next((ev for ev in range(0, 253, 4)
                    if _exact_stat(base[i], ivs[s], ev, signs[i], level) == stats[s]), None)
        if hit is None:
            return None
        out[s] = hit
    return out if sum(out.values()) <= EV_CAP else None


def _ev_window(base, iv, mult, lo, hi):
    """Smallest / largest EV (snapped to multiples of 4) whose final stat is in
    [lo, hi]. None if no EV 0..252 works."""
    feas = [e for e in range(0, 253) if lo <= _final_stat(base, iv, e, mult) <= hi]
    if not feas:
        return None
    ev_lo = -(-feas[0] // 4) * 4          # ceil to /4
    ev_hi = (feas[-1] // 4) * 4           # floor to /4
    return (ev_lo, ev_hi) if ev_lo <= ev_hi else (feas[0], feas[-1])


def _iv_budget_targets(base, mult, bounds, ivs):
    """When each bound is individually reachable but the scanned IVs jointly
    force more than 510 EV, raise IVs (toward 31, greediest EV-saving first)
    until the total fits. -> {stat: needed_iv} for the stats that had to go up,
    {} if the scanned IVs already fit, or None if even 31s across the board
    don't fit (that's the nature's problem, not the IVs')."""
    idx = {s: STATS.index(s) for s in bounds}

    def total(cur):
        t = 0
        for s, (lo, hi) in bounds.items():
            w = _ev_window(base[idx[s]], cur[s], mult(idx[s]), lo, hi)
            if w is None:
                return None
            t += w[0]
        return t

    cur = {s: ivs.get(s, 31) for s in bounds}
    t = total(cur)
    if t is None or t <= EV_CAP:
        return {}
    while t > EV_CAP:
        best = None
        for s in bounds:
            if cur[s] >= 31:
                continue
            nt = total({**cur, s: cur[s] + 1})
            if nt is not None and (best is None or t - nt > best[0]):
                best = (t - nt, s)
        if best is None:
            return None
        cur[best[1]] += 1
        t = total(cur)
    return {s: cur[s] for s in bounds if cur[s] > ivs.get(s, 31)}


def suggest_evs(species, scan, bounds):
    """-> ('breed', None)          a bound can't be met by EVs (wrong nature/IV)
          ('ok', {stat: new_ev})   the EVs that should change
          None                     not enough data to compute
    Objective: fewest stats changed, then fewest total EV points moved.
    """
    base = BASE_STATS.get(species)
    mult = _mult_fn(scan.get("nature"))
    if not base or mult is None:
        return None
    ivs, cur_ev = scan.get("ivs", {}), scan.get("evs", {})
    cur = {s: cur_ev.get(s, 0) for s in STATS}

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


def _iv_window(base, mult, lo, hi):
    """IV values (0..31) for which *some* EV 0..252 lands the final stat in
    [lo, hi]. None if no IV works (bound impossible for this base/nature)."""
    feas = [v for v in range(32)
            if _final_stat(base, v, 0, mult) <= hi and _final_stat(base, v, 252, mult) >= lo]
    return (feas[0], feas[-1]) if feas else None


def _min_total_ev(base, mult, bounds):
    """Least total EV to meet every bound, assuming IVs can be re-rolled freely.
    None if a bound is unreachable at all or the total blows the 510 cap."""
    total = 0
    for stat, (lo, hi) in bounds.items():
        i = STATS.index(stat)
        w = _iv_window(base[i], mult(i), lo, hi)
        if w is None:
            return None
        feas = [e for e in range(0, 253)
                if lo <= _final_stat(base[i], w[1], e, mult(i)) <= hi]
        if not feas:
            return None
        total += -(-feas[0] // 4) * 4
    return total if total <= EV_CAP else None


def suggest_nature(species, bounds, exclude=None):
    """Best re-roll nature for `bounds` (IVs assumed free), other than `exclude`.
    Ranked by: least total EV needed, then smallest stat given up to the -10%
    (neutral = nothing given up), then name for a stable pick. Returns a
    Title-case name, or None if nothing fits."""
    base = BASE_STATS.get(species)
    if not base:
        return None
    ranked = []
    for name, (plus, minus) in NATURES.items():
        if name == (exclude or "").lower():
            continue
        cost = _min_total_ev(base, _mult_fn(name), bounds)
        if cost is None:
            continue
        give_up = 0 if minus is None else base[minus]
        ranked.append((cost, give_up, name))
    ranked.sort()
    return ranked[0][2].title() if ranked else None


def _plus_stat(nature_name):
    """The stat a nature boosts (e.g. 'Spe'); None for a neutral nature / unknown."""
    n = NATURES.get((nature_name or "").lower())
    return STATS[n[0]] if n and n[0] is not None else None


def _ev_changes(new_evs, scan):
    """'HP 252 (+4), Spe 96 (+2)' - the EVs to set and the delta from the scan."""
    cur = scan.get("evs", {})
    return ", ".join(f"{s} {new_evs[s]} ({new_evs[s] - cur.get(s, 0):+d})"
                     for s in STATS if s in new_evs)


def _need_note(required, scanned_norm):
    """List the required moves the mon HAS, then ' -- need <the missing ones>'."""
    have = [m for m in required if _norm(m) in scanned_norm]
    miss = [m for m in required if _norm(m) not in scanned_norm]
    txt = ", ".join(have)
    if miss:
        txt = (txt + " -- " if txt else "") + "need " + ", ".join(miss)
    return txt, miss


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


def _chk(label, status, note=""):
    return {"label": label, "status": status, "note": note}


def check_slot(slot, block):
    """A structured report card for one scanned mon vs its strat slot:
        {species_ok, species_msg, evolve,
         breed:   [IVs, Nature, Hidden Ability, Egg moves],
         training:[Level, EVs, Ability, Moveset, Item]}
    each check = {label, status: pass|fail|na|blocked|missing, note}.
    'missing' (note "missing information") = the scan didn't capture that field.
    The Level check also carries the "must evolve first" case."""
    scan = parse_scan(block)
    want = slot["species"]
    bounds, req_moves = slot["bounds"], slot["moves"]
    r = {"scan": scan, "want": want, "species_ok": True, "species_msg": "",
         "evolve": None, "warn": _scan_consistency(scan),
         "breed": [], "training": []}

    steps = None
    if _norm(scan["species"]) != _norm(want):
        steps = evo_path(scan["species"], want) if scan["species"] else None
        if not steps:
            r["species_ok"] = False
            r["species_msg"] = f"want {want}, got {scan['species'] or '?'}"
            return r
        r["evolve"] = (f"evolve to {want} ("
                       + ", ".join(_evo_how(s) for s in steps) + ")")

    base = BASE_STATS.get(want)
    mult = _mult_fn(scan.get("nature"))
    legendary = _norm(want) in NO_BREED
    projected = steps is not None or (scan.get("level") not in (100, None))
    eff = _project_stats(want, scan) if projected else scan["stats"]
    reroll = "re-roll" if legendary else "breed"

    # does the mon, as it stands, already satisfy every stat bound?
    stats_pass = bool(bounds) and bool(eff) and all(
        eff.get(s) is not None and lo <= eff[s] <= hi
        for s, (lo, hi) in bounds.items())

    ivs_of = lambda: " / ".join(f"{scan.get('ivs', {}).get(s, 31)} {s}"
                                for s in STATS if s in bounds)

    # ---------- BREED ----------
    # Nature first - the IV and EV checks lean on it.
    nature = scan.get("nature")
    nat_ok = None
    if not bounds:
        c_nat = _chk("Nature", "na", "no stat bounds")
    elif not nature:
        c_nat = _chk("Nature", "missing", "missing information")
    elif stats_pass:
        c_nat, nat_ok = _chk("Nature", "pass", nature), True
    elif not base or mult is None:
        c_nat = _chk("Nature", "na", "nature not recognised")
    elif _min_total_ev(base, mult, bounds) is not None:
        c_nat, nat_ok = _chk("Nature", "pass", nature), True
    else:
        alt = suggest_nature(want, bounds, exclude=nature)
        plus = _plus_stat(alt)
        need_nat = (f"+{plus} Nature" if plus else
                    f"{alt} Nature" if alt else "a different nature")
        c_nat, nat_ok = _chk("Nature", "fail", f"{nature}, need {need_nat}"), False

    if not bounds:
        c_iv = _chk("IVs", "na", "no stat bounds")
    elif stats_pass:
        c_iv = _chk("IVs", "pass", ivs_of())
    elif not nature:
        c_iv = _chk("IVs", "blocked", "needs the nature")
    elif not base or mult is None:
        c_iv = _chk("IVs", "na", "nature not recognised")
    elif nat_ok is False:
        c_iv = _chk("IVs", "blocked", "fix the nature first")
    else:
        ivs, bad = scan.get("ivs", {}), {}
        for stat, (lo, hi) in bounds.items():
            i = STATS.index(stat)
            if _ev_window(base[i], ivs.get(stat, 31), mult(i), lo, hi) is None:
                bad[stat] = _iv_window(base[i], mult(i), lo, hi)
        # every bound reachable on its own, but do the low IVs together bust 510 EV?
        over = None if bad else _iv_budget_targets(base, mult, bounds, ivs)
        if bad:
            parts = [f"{s} {_fmt_bound(*w)}" if w else f"{s} impossible"
                     for s, w in bad.items()]
            c_iv = _chk("IVs", "fail", f"{reroll} for IV: " + ", ".join(parts))
        elif over:
            parts = [f"{s} {v}+" if v < 31 else f"{s} 31" for s, v in over.items()]
            c_iv = _chk("IVs", "fail", f"{reroll} for IV: " + ", ".join(parts)
                        + " — too low to EV-train within the 510 cap")
        else:
            c_iv = _chk("IVs", "pass", ivs_of())

    want_ab = (slot["ability"] or "").strip()
    pinned_ab = want_ab and want_ab.lower() != "any"
    ha = HIDDEN_ABILITY.get(_norm(want))
    on_ab = scan.get("ability")
    needs_ha = bool(pinned_ab and ha and _norm(want_ab) == _norm(ha))
    has_ha = bool(scan.get("has_ha")) or bool(ha and _norm(on_ab) == _norm(ha))
    if needs_ha and not on_ab and not scan.get("has_ha"):
        c_ha = _chk("Hidden Ability", "missing", "missing information")
    elif needs_ha:
        c_ha = _chk("Hidden Ability", "pass" if has_ha else "fail",
                    "Yes" if has_ha else "No")
    else:
        c_ha = _chk("Hidden Ability", "na", "Yes" if has_ha else "No")

    egg = EGG_MOVES.get(_norm(want), set())
    scanned_moves = {_norm(m) for m in scan["moves"]}
    req_egg = [m for m in req_moves if _norm(m) in egg]
    if not req_egg:
        c_egg = _chk("Egg moves", "na", "none")
    else:
        note, miss = _need_note(req_egg, scanned_moves)
        c_egg = _chk("Egg moves", "fail" if miss else "pass", note)

    r["breed"] = [c_iv, c_nat, c_ha, c_egg]

    # ---------- TRAINING ----------
    # Level also carries the "needs to evolve" case: "50 -> 100, evolve to X (Lvl 30)"
    lv = scan.get("level")
    if lv is None:
        c_lv = _chk("Level", "missing", "missing information")
    else:
        bits = ([f"{lv} -> 100"] if lv != 100 else []) + \
               ([r["evolve"]] if r["evolve"] else [])
        c_lv = _chk("Level", "pass", "100") if not bits \
            else _chk("Level", "fail", ", ".join(bits))

    if not bounds:
        c_ev = _chk("EVs", "na", "no stat bounds")
    elif stats_pass:
        c_ev = _chk("EVs", "pass", "in range" + (" at Lv100" if projected else ""))
    elif c_nat["status"] in ("fail", "missing") or c_iv["status"] in ("fail", "missing"):
        c_ev = _chk("EVs", "blocked", "fix breed first")
    elif not eff:
        c_ev = _chk("EVs", "missing", "missing information")
    elif all(eff.get(s) is not None and lo <= eff[s] <= hi
             for s, (lo, hi) in bounds.items()):
        c_ev = _chk("EVs", "pass", "in range" + (" at Lv100" if projected else ""))
    else:
        sug = suggest_evs(want, scan, bounds)
        c_ev = _chk("EVs", "fail",
                    _ev_changes(sug[1], scan) if sug and sug[0] == "ok" and sug[1]
                    else "no EV spread reaches the bounds")

    if not pinned_ab:
        c_ab = _chk("Ability", "na", on_ab or "not read")
    elif not on_ab:
        c_ab = _chk("Ability", "missing", "missing information")
    elif _norm(on_ab) == _norm(want_ab):
        c_ab = _chk("Ability", "pass", on_ab)
    else:
        tag = " (HA)" if (ha and _norm(want_ab) == _norm(ha)) else ""
        c_ab = _chk("Ability", "fail", f"{on_ab} -- need {want_ab}{tag}")

    need = [m for m in req_moves if _norm(m) not in egg]
    if not need:
        c_mv = _chk("Moveset", "na", "none required")
    else:
        note, miss = _need_note(need, scanned_moves)
        c_mv = _chk("Moveset", "fail" if miss else "pass", note)

    if not slot["item"]:
        c_it = _chk("Item", "na", scan.get("item") or "none")
    elif _norm(scan.get("item")) in {_norm(i) for i in slot["item"]}:
        c_it = _chk("Item", "pass", scan["item"])
    else:
        c_it = _chk("Item", "fail",
                    f"{scan.get('item') or 'no item'} -- need " + " or ".join(slot["item"]))

    r["training"] = [c_lv, c_ev, c_ab, c_mv, c_it]
    return r


def slot_ok(slot, block):
    """True when every applicable check passes (grid / list roll-up).
    A 'missing' check counts as not-ok - can't confirm what didn't scan."""
    r = check_slot(slot, block)
    if not r["species_ok"] or r["warn"]:
        return False
    return all(c["status"] not in ("fail", "missing")
               for c in r["breed"] + r["training"])


def validate(slot, block):
    """Back-compat: flat list of failure notes ([] == all good)."""
    r = check_slot(slot, block)
    if not r["species_ok"]:
        return [f"species: {r['species_msg']}"]
    out = [f"{c['label']}: {c['note']}" for c in r["breed"] + r["training"]
           if c["status"] in ("fail", "missing")]
    if r["warn"]:
        out.insert(0, r["warn"])
    return out


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
    any_invalid = any(by_num.get(n) and not slot_ok(by_num[n], block)
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
        self._notes = {}    # tree row id -> full check note

        self.strats = strat_names(raid)
        self.strat = self.strats[0] if self.strats else None
        self.scans = self._load_scans()

        self.win = win = tk.Toplevel(app.root)
        win.title(f"{raid} · {position}")
        win.transient(app.root)
        win.geometry("730x600")

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
            ttk.Label(top, text=f"strat: {self.strat}", foreground=theme.FG_DIM).pack(side="right")
        else:
            ttk.Label(top, text="no strat defined", foreground=theme.FAIL).pack(side="right")

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
        ttk.Label(left, text="○ not scanned   ✓ valid   ✗ invalid",
                  foreground=theme.FG_DIM, font=("TkDefaultFont", 8)).pack(anchor="w", pady=(6, 0))
        ttk.Label(left, text="✓ pass   ✗ fix   – n/a   ⋯ blocked   ? missing",
                  foreground=theme.FG_DIM, font=("TkDefaultFont", 8)).pack(anchor="w")

        ttk.Separator(body, orient="vertical").pack(side="left", fill="y", padx=10)

        # right: capture panel
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)

        self.target_lbl = ttk.Label(right, text="select a slot →", foreground=theme.FG_DIM,
                                    font=("Consolas", 9), justify="left")
        self.target_lbl.pack(anchor="w")
        self.banner = ttk.Label(right, text="", foreground=theme.FG_DIM,
                                font=("TkDefaultFont", 9), justify="left")
        self.banner.pack(anchor="w", pady=(2, 2))
        self._warn_slot = None  # slot num whose banner offers a "click to fix"
        self.banner.bind("<Button-1>", self._banner_click)

        self.tree = ttk.Treeview(right, columns=("v",), show="tree", height=12,
                                 selectmode="none")
        self.tree.column("#0", width=150, stretch=False, anchor="w")
        self.tree.column("v", width=360, anchor="w")
        self.tree.tag_configure("pass", foreground=theme.PASS)
        self.tree.tag_configure("fail", foreground=theme.FAIL)
        self.tree.tag_configure("na", foreground=theme.NA)
        self.tree.tag_configure("blocked", foreground=theme.BLOCKED)
        self.tree.tag_configure("missing", foreground=theme.MISSING)
        self.tree.tag_configure("group", font=("TkDefaultFont", 9, "bold"))
        self.tree.pack(fill="x", pady=(0, 6))
        self.tree.bind("<Button-1>", self._tree_click)

        bar = ttk.Frame(right)
        bar.pack(fill="x")
        self.capture_btn = ttk.Button(bar, text="Capture", command=self.capture,
                                      state="disabled")  # needs bbox + a selected slot
        self.capture_btn.pack(side="left")
        self.save_btn = ttk.Button(bar, text="Save edits", command=self.save,
                                   state="disabled")
        self.save_btn.pack(side="left", padx=6)
        self.region_lbl = ttk.Label(bar, text=self._region_text(), foreground=theme.FG_DIM)
        self.region_lbl.pack(side="right")

        self.text = tk.Text(right, font=("Consolas", 10), wrap="none", height=7,
                            relief="solid", borderwidth=1, undo=True)
        self.text.pack(fill="both", expand=True, pady=(6, 6))
        self._baseline = ""  # text-box content that matches disk
        self.text.bind("<<Modified>>", self._on_text_change)

        self.status = ttk.Label(frame, text="", foreground=theme.FG_DIM)
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
        self.banner.config(text="")
        self.tree.delete(*self.tree.get_children())
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
        return "valid" if slot_ok(slot, self.scans[num]) else "invalid"

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

    @staticmethod
    def _rollup(checks):
        st = {c["status"] for c in checks}
        if "fail" in st:
            return "✗"
        if "missing" in st:
            return "?"
        if "blocked" in st:
            return "⋯"
        return "–" if st == {"na"} else "✓"

    def _show_check(self, num):
        self.tree.delete(*self.tree.get_children())
        self._notes = {}
        self._warn_slot = None
        self.banner.config(cursor="")
        slot = self._slot_by_num(num)
        if slot is None:
            self.banner.config(text="")
            return
        if num not in self.scans:
            self._show_target(slot)
            return
        r = check_slot(slot, self.scans[num])
        if not r["species_ok"]:
            self.banner.config(text=f"✗  wrong Pokémon — {r['species_msg']}",
                               foreground=theme.FAIL)
            return

        extra = []
        if r["warn"]:
            extra.append("⚠ " + r["warn"] + "  (click to fix)")
            self._warn_slot = num
            self.banner.config(cursor="hand2")
        missing = [c["label"] for c in r["breed"] + r["training"]
                   if c["status"] == "missing"]
        if missing:
            extra.append("⚑ didn't scan: " + ", ".join(missing))
        ok = slot_ok(slot, self.scans[num])
        self.banner.config(
            text="      ".join([("✓ all checks pass" if ok else "✗ needs work")] + extra),
            foreground=theme.PASS if ok else (theme.MISSING if missing and not r["warn"]
                and not any(c["status"] == "fail" for c in r["breed"] + r["training"])
                else theme.FAIL))

        for group, checks in (("Breed", r["breed"]), ("Training", r["training"])):
            gid = self.tree.insert("", "end", open=True, tags=("group",),
                                   text=f"{self._rollup(checks)}  {group}", values=("",))
            for c in checks:
                note = c["note"]
                short = note if len(note) <= 62 else note[:59] + "…"
                iid = self.tree.insert(
                    gid, "end", tags=(c["status"],), values=(short,),
                    text=f"  {STATUS_MARK[c['status']]} {c['label']}")
                self._notes[iid] = f"{c['label']} — {note}" if note else c["label"]

    def _show_target(self, slot):
        """Not-scanned slot: the IV ranges / natures to breed for (same maths as
        the pokepaste-maker Breeding.txt)."""
        from breed_calc import recommend  # lazy - avoids an import cycle
        rec = recommend(slot["species"], slot["bounds"])

        ha = HIDDEN_ABILITY.get(_norm(slot["species"]))
        want_ab = (slot["ability"] or "").strip()
        is_ha = bool(want_ab and want_ab.lower() != "any"
                     and ha and _norm(want_ab) == _norm(ha))

        self.banner.config(text="not scanned — breed for:", foreground=theme.FG_DIM)
        gid = self.tree.insert("", "end", open=True, tags=("group",),
                               text="Target spread" + (" (HA)" if is_ha else ""),
                               values=("",))
        if not rec:
            self.tree.insert(gid, "end", tags=("na",), text="  IVs",
                             values=("base stats unknown",))
            return
        if rec.get("error"):
            iid = self.tree.insert(gid, "end", tags=("fail",), text="  ⚠",
                                   values=(rec["error"],))
            self._notes[iid] = rec["error"]
            return
        self.tree.insert(gid, "end", text="  IVs", values=(rec["ivs"],))
        self.tree.insert(gid, "end", text="  Nature", values=(rec["natures"],))
        egg = EGG_MOVES.get(_norm(slot["species"]), set())
        req_egg = [m for m in slot["moves"] if _norm(m) in egg]
        if req_egg:
            self.tree.insert(gid, "end", text="  Egg moves",
                             values=(", ".join(req_egg),))

    def _tree_click(self, ev):
        iid = self.tree.identify_row(ev.y)
        if iid in getattr(self, "_notes", {}):
            self._status(self._notes[iid])

    # ---- fixing an inconsistent scan ----
    def _banner_click(self, _ev=None):
        """The banner offers this when the scanned final stats don't match the
        IVs/EVs/nature: recompute the stats, or back-solve the EVs."""
        num = self._warn_slot
        if num is None or num not in self.scans:
            return
        scan = parse_scan(self.scans[num])
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label="Recompute the final stats from EVs / IVs / Nature",
                      command=lambda: self._fix_discrepancy(num, "stats"))
        ev_ok = solve_evs_for_stats(scan) is not None
        m.add_command(label=("Adjust the EVs to match the final stats"
                             if ev_ok else "Adjust the EVs to match  (not possible)"),
                      state="normal" if ev_ok else "disabled",
                      command=lambda: self._fix_discrepancy(num, "evs"))
        try:
            m.tk_popup(self.win.winfo_pointerx(), self.win.winfo_pointery())
        finally:
            m.grab_release()

    def _fix_discrepancy(self, num, how):
        scan = parse_scan(self.scans[num])
        if how == "stats":
            new = recompute_stats(scan)
            if not new:
                return
            before = scan.get("stats") or {}
            line = "Stats: " + " / ".join(f"{new[s]} {s}" for s in STATS)
            delta = ", ".join(f"{s} {before.get(s, '?')}→{new[s]}"
                              for s in STATS if before.get(s) != new[s])
            prefix, blurb = "stats:", "Recompute the final stats (unread IVs are taken as 31)?"
        else:
            new = solve_evs_for_stats(scan)
            if not new:
                return
            before = scan.get("evs") or {}
            parts = " / ".join(f"{new[s]} {s}" for s in STATS if new[s])
            line = "EVs: " + (parts or "0")
            delta = ", ".join(f"{s} {before.get(s, 0)}→{new[s]}"
                              for s in STATS if before.get(s, 0) != new[s])
            prefix, blurb = "evs:", "Set the EVs so they produce the scanned final stats?"
        if not messagebox.askyesno("Fix scan", f"{blurb}\n\n{delta or 'no change'}",
                                   parent=self.win):
            return
        self._replace_scan_line(num, prefix, line)

    def _replace_scan_line(self, num, prefix, new_line):
        """Swap the 'Prefix: …' line of scan block `num` (insert before the moves
        if absent), save, and refresh the view."""
        lines = self.scans[num].splitlines()
        for i, ln in enumerate(lines):
            if ln.strip().lower().startswith(prefix):
                lines[i] = new_line
                break
        else:
            at = next((i for i, ln in enumerate(lines)
                       if ln.strip().startswith("-")), len(lines))
            lines.insert(at, new_line)
        self.scans[num] = "\n".join(lines)
        self._write_scans()
        if self.active == num:
            body = re.sub(r"^\s*\d+\s*-\s*", "", self.scans[num], count=1)
            self._set_text(body)
        self._refresh_list()
        self._show_check(num)
        self.app.refresh_grid()
        self._status("scan updated")

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
            ("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")],
            initialdir=os.path.join(HERE, "samples"))
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
