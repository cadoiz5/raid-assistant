#!/usr/bin/env python3
"""
breed_calc.py - the loosest IV ranges + the nature options you can breed a mon
with and still be able to EV-train it onto a strat slot's target stats.

Same maths as the "pokepaste maker" Breeding.txt (spread_solver_min), ported to
run off this project's committed data (no dex dump needed):

  For every IV combination inside the box there must exist *some* legal 6-stat
  EV spread - each stat 0..252, total <= 508 - that reaches the targets. A stat
  only ever needs *less* EV as its IV rises, so the whole box is buildable
  exactly when its all-lowest-IV corner fits in 508 EVs. pick_nature maximises
  box size (a boosting nature frees EVs and widens the other boxes); the "Not
  +SpD" style nature summary lists every nature the chosen box still works
  under.

recommend(species, bounds) is what the scan window calls for a not-yet-scanned
slot.
"""

from scan_window import BASE_STATS, NATURES

LEVEL = 100
EV_TOTAL = 508              # 127 x 4 - the exact budget the min-solver assumes
EV_STAT_CAP = 252
MAX_IV = 31
MAX_EV_STEPS = EV_STAT_CAP // 4          # 63 quarter-steps of IV + EV//4
BIG = 10 ** 6                            # stands in for "no upper bound"
TIER_WEIGHT = 1000                       # a better IV tier must outrank any width

SK = ["hp", "atk", "def", "spa", "spd", "spe"]
LABEL = {"hp": "HP", "atk": "Atk", "def": "Def",
         "spa": "SpA", "spd": "SpD", "spe": "Spe"}
_TITLE2SK = {"HP": "hp", "Atk": "atk", "Def": "def",
             "SpA": "spa", "SpD": "spd", "Spe": "spe"}
NEUTRAL = "Neutral"
MINUS_ATK_BOOSTERS = {"def": "Bold", "spa": "Modest", "spd": "Calm", "spe": "Timid"}


class _NoSolve(Exception):
    pass


def _nature_list():
    """[{'name','plus','minus'}] from scan_window.NATURES (index pairs into SK)."""
    out = []
    for name, (plus, minus) in NATURES.items():
        out.append({"name": name.title(),
                    "plus": SK[plus] if plus is not None else None,
                    "minus": SK[minus] if minus is not None else None})
    return out


NATURE_LIST = _nature_list()


# ---------------- stat maths (level 100, exact integer floor) ----------------
def _mult(nature, sk):
    if nature is None or sk == "hp":
        return (1, 1)
    if nature["plus"] == sk and nature["minus"] != sk:
        return (11, 10)
    if nature["minus"] == sk and nature["plus"] != sk:
        return (9, 10)
    return (1, 1)


def _stat_value(sk, base, d, mult):
    """d == IV + EV // 4."""
    if sk == "hp":
        return 2 * base + d + LEVEL + 10
    return (2 * base + d + 5) * mult[0] // mult[1]


def _valid_d_range(sk, base, lo, hi, mult):
    valid = [d for d in range(0, MAX_IV + MAX_EV_STEPS + 1)
             if lo <= _stat_value(sk, base, d, mult) <= hi]
    return (valid[0], valid[-1]) if valid else None


def _flexible_span(sk, base, lo, hi, mult):
    """(iv_lo, iv_hi, d_lo): the IVs that can reach [lo, hi] with *some* legal EV.
    d_lo is the lowest IV+EV//4 in range, so an IV needs 4*max(0, d_lo-iv) EV."""
    span = _valid_d_range(sk, base, lo, hi, mult)
    if span is None:
        return None
    d_lo, d_hi = span
    iv_hi = min(MAX_IV, d_hi)               # higher IVs cost no EV, always kept
    iv_lo = max(0, d_lo - MAX_EV_STEPS)     # lowest IV still able to reach d_lo
    return (iv_lo, iv_hi, d_lo) if iv_lo <= iv_hi else None


def _min_ev(d_lo, iv):
    return 4 * max(0, d_lo - iv)


def _stat_options(sk, base, lo, hi, mult):
    """(iv_lo, iv_hi, low-corner EV cost, tier, width) for every feasible box.
    tier 2 -> box holds 31, tier 1 -> holds 0, tier 0 -> neither."""
    span = _flexible_span(sk, base, lo, hi, mult)
    if span is None:
        return []
    lo_bound, iv_hi, d_lo = span
    opts = []
    for iv_lo in range(lo_bound, iv_hi + 1):
        tier = 2 if iv_hi == MAX_IV else 1 if iv_lo == 0 else 0
        opts.append((iv_lo, iv_hi, _min_ev(d_lo, iv_lo), tier, iv_hi - iv_lo + 1))
    return opts


# ---------------- box solving ----------------
def _solve_box(bases, targets, nature):
    """Maximise total IV-box size under the 508 low-corner EV budget, for one
    nature. Ties: keep the boosted stat and Speed tight (toward 31), then split
    the leftover width as evenly as possible."""
    pin = {"spe"}
    if nature and nature["plus"]:
        pin.add(nature["plus"])

    per_stat = {}
    for sk in SK:
        lo, hi = targets.get(sk, (0, BIG))
        opts = _stat_options(sk, bases[sk], lo, hi, _mult(nature, sk))
        if not opts:
            raise _NoSolve
        per_stat[sk] = opts

    dp = {0: (0, 0, 0, [])}   # ev_low_corner -> (score, -pin_width, -sum_sq, [opt])
    for sk in SK:
        pinned = sk in pin
        nxt = {}
        for used, (score, negpin, negsq, chosen) in dp.items():
            for opt in per_stat[sk]:
                iv_lo, iv_hi, cost, tier, width = opt
                total = used + cost
                if total > EV_TOTAL:
                    continue
                cand = (score + tier * TIER_WEIGHT + width,
                        negpin - (width if pinned else 0),
                        negsq - width * width,
                        chosen + [opt])
                best = nxt.get(total)
                if best is None or cand[:3] > best[:3]:
                    nxt[total] = cand
        if not nxt:
            raise _NoSolve
        dp = nxt

    score, negpin, negsq, chosen = max(dp.values(), key=lambda v: v[:3])
    solution = {sk: (o[0], o[1]) for sk, o in zip(SK, chosen)}
    return (score, negpin, negsq), solution


def _nature_tiers(natures):
    """Preference order for breaking an exact box-size tie: Neutral, Adamant,
    the -Atk boosters, then everything else."""
    by = {n["name"]: n for n in natures}
    t_adamant = [by["Adamant"]] if "Adamant" in by else []
    t_minus_atk = [by[MINUS_ATK_BOOSTERS[s]] for s in ("def", "spa", "spd", "spe")
                   if MINUS_ATK_BOOSTERS[s] in by]
    named = {n["name"] for n in t_adamant + t_minus_atk}
    t_rest = [n for n in natures if n["plus"] is not None and n["name"] not in named]
    return [[None], t_adamant, t_minus_atk, t_rest]


def _pick_nature(bases, targets, natures):
    """The nature that yields the largest IV box; earlier tier wins a size tie."""
    order = [n for tier in _nature_tiers(natures) for n in tier]
    best = None
    for priority, nature in enumerate(order):
        try:
            rank, solution = _solve_box(bases, targets, nature)
        except _NoSolve:
            continue
        key = (rank[0], -priority)
        if best is None or key > best[0]:
            best = (key, nature, solution)
    return None if best is None else (best[1], best[2])


def _compatible_mask(bases, targets, solution, natures):
    """Bit i set when the chosen box is still buildable under nature i <= 508 EVs."""
    mask = 0
    for i, nature in enumerate(natures):
        total, ok = 0, True
        for sk in SK:
            iv_lo, iv_hi = solution[sk]
            lo, hi = targets.get(sk, (0, BIG))
            span = _flexible_span(sk, bases[sk], lo, hi, _mult(nature, sk))
            if span is None or span[0] > iv_lo or iv_hi > span[1]:
                ok = False
                break
            total += _min_ev(span[2], iv_lo)
        if ok and total <= EV_TOTAL:
            mask |= 1 << i
    return mask


# ---------------- nature summary ("Timid, Hasty" or "Not +SpD") ----------------
_MAX_LISTED = 6


def _compatible_names(natures, mask):
    names = []
    for i, n in enumerate(natures):
        if mask & (1 << i):
            names.append(NEUTRAL if n["plus"] is None else n["name"])
    return sorted(set(names), key=lambda x: (x != NEUTRAL, names.index(x)))


def _describe_natures(natures, mask):
    names = _compatible_names(natures, mask)
    if not names:
        return "none"
    if len(names) <= _MAX_LISTED:
        return ", ".join(names)

    compatible = {n["name"] for i, n in enumerate(natures) if mask >> i & 1}
    banned = {}
    for side in ("plus", "minus"):
        banned[side] = [s for s in SK if s != "hp" and
                        all(n["name"] not in compatible
                            for n in natures if n[side] == s)]
    predicted = {n["name"] for n in natures
                 if n["plus"] not in banned["plus"]
                 and n["minus"] not in banned["minus"]}
    if predicted != compatible:
        return ", ".join(names)

    parts = []
    for s in SK:
        no_plus, no_minus = s in banned["plus"], s in banned["minus"]
        if no_plus and no_minus:
            parts.append("%s Neutral" % LABEL[s])
        elif no_plus:
            parts.append("Not +%s" % LABEL[s])
        elif no_minus:
            parts.append("Not -%s" % LABEL[s])
    return ", ".join(parts) if parts else "Any"


# ---------------- output ----------------
def _fmt_iv(lo, hi):
    if lo == 0 and hi == MAX_IV:
        return None
    if lo == hi:
        return str(lo)
    if hi == MAX_IV:
        return "%d+" % lo
    if lo == 0:
        return "%d-" % hi
    return "%d-%d" % (lo, hi)


def _iv_line(solution):
    parts = [(LABEL[s], t) for s in SK
             for t in [_fmt_iv(*solution[s])] if t is not None]
    return " / ".join("%s %s" % (v, k) for k, v in parts) if parts else "any"


def recommend(species, bounds, nature=None):
    """-> {'ivs': str, 'natures': str} for the loosest breedable box,
       or {'error': str}, or None when the species' base stats aren't known.

    If `nature` is given and can actually reach the targets, the box is solved
    for that nature (so the IV ranges are right for a mon you already have);
    otherwise the box-maximising nature is picked."""
    base_list = BASE_STATS.get(species)
    if not base_list:
        return None
    bases = {sk: base_list[i] for i, sk in enumerate(SK)}

    targets = {}
    for k, (lo, hi) in (bounds or {}).items():
        sk = _TITLE2SK.get(k)
        if sk:
            targets[sk] = (lo, BIG if hi == float("inf") else hi)

    picked = None
    if nature:
        nd = next((n for n in NATURE_LIST
                   if n["name"].lower() == str(nature).lower()), None)
        if nd:
            try:
                _, sol = _solve_box(bases, targets, nd)
                picked = (nd, sol)
            except _NoSolve:
                picked = None
    if picked is None:
        picked = _pick_nature(bases, targets, NATURE_LIST)
    if picked is None:
        return {"error": "no nature reaches every target within %d EVs" % EV_TOTAL}
    _, solution = picked
    mask = _compatible_mask(bases, targets, solution, NATURE_LIST)
    return {"ivs": _iv_line(solution), "natures": _describe_natures(NATURE_LIST, mask)}
