#!/usr/bin/env python3
"""
breed_calc.py - work out the nature / IV / EV spread a mon needs to satisfy a
strat slot's stat bounds. Kept in its own file because the breeding rules are
going to grow (per-stat / per-strat preferences, HP-IV handling, EV
efficiency, ...).

`recommend(species, bounds)` is the only entry point the GUI uses.
"""

from scan_window import (BASE_STATS, EV_CAP, NATURES, STATS, _final_stat,
                         _iv_window, _mult_fn, suggest_nature)

EV_MAX = 252


def _nature_effect(name):
    plus, minus = NATURES.get((name or "").lower(), (None, None))
    return "neutral" if plus is None else f"+{STATS[plus]} / -{STATS[minus]}"


def pick_nature(species, bounds):
    """The nature to breed for. Extension point for per-strat preferences."""
    return suggest_nature(species, bounds) or "Hardy"


def _min_ev(base_i, iv, mult_i, lo, hi):
    """Least EV (mult of 4) whose final stat lands in [lo, hi]; None if none of
    0..252 works with this IV."""
    feas = [e for e in range(0, EV_MAX + 1)
            if lo <= _final_stat(base_i, iv, e, mult_i) <= hi]
    return -(-feas[0] // 4) * 4 if feas else None


def recommend(species, bounds):
    """-> {'nature', 'nature_effect', 'ivs': {stat: (lo, hi)},
           'evs': {stat: int}, 'notes': [str]}   or None if not computable.

    ivs[stat] is the IV *window* that can satisfy the bound; hi == 31 means a
    normal perfect IV is fine, a lower hi means you must breed a sub-31 there.
    evs[stat] is the least EV that reaches the bound at the top of that window.
    """
    base = BASE_STATS.get(species)
    if not base or not bounds:
        return None

    nature = pick_nature(species, bounds)
    mult = _mult_fn(nature)
    ivs, evs, notes = {}, {}, []

    for stat in STATS:
        if stat not in bounds:
            continue
        lo, hi = bounds[stat]
        i = STATS.index(stat)
        window = _iv_window(base[i], mult(i), lo, hi)
        if window is None:
            notes.append(f"a {nature} {species} can't reach {stat} "
                         f"{_bound_txt(lo, hi)} at any IV/EV")
            continue
        ivs[stat] = window
        ev = _min_ev(base[i], window[1], mult(i), lo, hi)
        evs[stat] = ev if ev is not None else 0

    total = sum(evs.values())
    if total > EV_CAP:
        notes.append(f"constrained EVs already total {total} (cap {EV_CAP})")

    return {"nature": nature, "nature_effect": _nature_effect(nature),
            "ivs": ivs, "evs": evs, "notes": notes}


def _bound_txt(lo, hi):
    if lo == hi:
        return str(lo)
    if hi == float("inf"):
        return f"{lo}+"
    return f"{lo}-{hi}" if lo else f"{hi}-"


def fmt_ivs(ivs):
    """{'HP': (0,31), 'SpD': (0,28), 'Spe': (0,0)} -> '31 HP / 0-28 SpD / 0 Spe'."""
    out = []
    for s, (lo, hi) in ivs.items():
        if hi == 31:
            out.append(f"31 {s}")          # normal - breed a perfect IV
        elif lo == hi:
            out.append(f"{hi} {s}")         # must be exactly this
        else:
            out.append(f"{lo}-{hi} {s}")    # a forced sub-31 range
    return " / ".join(out) or "any"


def fmt_evs(evs):
    return " / ".join(f"{v} {s}" for s, v in evs.items() if v) or "0"
