# Strat file format

Path: `strats/<Raid>/<Strat name>.txt`  — e.g. `strats/Heatran/Cloud Five.txt`

One file per raid strat. A raid is 4 people (**P1–P4**), each bringing 6
Pokémon. This file holds the constraints for **all four positions** (up to
24 mons). A scan checks one person's 6 Pokémon against the constraints for
their position.

## Layout

```
[P1]

<mon block>

<mon block>

[P2]

<mon block>
...
```

- Section headers `[P1] [P2] [P3] [P4]`, each on its own line.
- Under a header: 6 mon blocks (slots 1–6), separated by blank lines.
- Lines starting with `#` are comments.
- List only the attributes you want to pin. Anything not listed is unrestricted
  (a slot with just a species line pins only that species; a position with no
  blocks constrains nothing).

## Mon block

```
1 - Golduck @ Sitrus Berry      slot number "N - ", then species (required).
                                "@ Item" optional.
Ability: Cloud Nine             optional — required ability.
301 HP / 238 SpD / 294+ Spe     optional — stat bounds, " / " separated.
- Water Sport                   optional — each listed move must be on the set.
- Knock Off
```

The leading `N - ` is the team slot (1–6). Later, two blocks with the same slot
number will mean "either of these is acceptable for that slot" (replacements).

To accept **any of several items**, separate them with `/` on the header line —
the Item check passes if the held item is any of them:

```
1 - Golduck @ Sitrus Berry / Aguav Berry / Figy Berry
```

## Stat bounds

Each entry is `<number><modifier> <STAT>`, where STAT is one of
`HP Atk Def SpA SpD Spe`. Only the stats you list are checked.

| Written        | Means                                  |
|----------------|----------------------------------------|
| `301 HP`       | exactly 301                            |
| `294+ Spe`     | 294 or more                            |
| `226- Spe`     | 226 or less                            |
| `180-226 Spe`  | between 180 and 226 (inclusive)        |

Stat bounds are read at **level 100** — every raid mon must be level 100
(checked automatically, no need to write it). If a scan is under 100 or is
still a pre-evolution, its stats are projected to level 100 for the check and
the report says to level up / evolve.

## What a scan is graded on

The scan window shows two groups of four checks, derived from the block above:

**Breed** (set when the mon is bred — a fail means re-breed, or re-roll for a
legendary):

| Check           | Passes when |
|-----------------|-------------|
| IVs             | the IVs are high enough to hit the stat bounds |
| Nature          | the scanned nature *can* reach the stat bounds |
| Hidden Ability  | pinned ability is the species' HA and the mon is on it / shows the HA diamond |
| Egg moves       | every pinned move that is egg-only for the line is present |

**Training** (adjustable later — a fail is a quick fix):

| Check    | Passes when |
|----------|-------------|
| Level    | the mon is level 100 and already its final form (else "evolve … / train to 100") |
| EVs      | the (projected) level-100 stats are all in range |
| Ability  | the mon is on the pinned ability (grey when the strat says `Any`) |
| Moveset  | every pinned non-egg move is present |
| Item     | the held item matches `@ Item` |

The IVs and Nature checks pass automatically whenever the scanned final
stats already sit inside the bounds — they only flag a problem when the
stats are out of range and re-breeding is the reason. A short moveset or a
mon with no item is only a problem if the strat pins something it's missing.

## `[Moves]` section — the in-raid move order

Optional. Add a `[Moves]` section (anywhere in the file) with one `Turn N`
block per turn, and under it up to four `P<n> - <what to click>` lines:

```
[Moves]

Turn 1
P1 - Golduck Water Sport
P2 - Swanna Lucky Chant
P3 - Infernape Captivate
P4 - Whimsicott Switcheroo

Turn 2
P1 - Golduck Knock Off
...
```

Clicking a raid's name in the main table opens this as a turn × position
table (mon name over the move). Each `P1..P4` header has a checkbox that
greys that column; clicking a turn's row greys it (turn done). The mon and
move are split automatically; write `P1 - Golduck: Water Sport` to be
explicit.

### Target

A move hits the boss by default. End the line with `Ad`, `Boss`, `Self`, or a
teammate `P1`–`P4` to say otherwise — it shows as `Captivate → Ad` in the
table. The target word may be wrapped in parens.

```
P1 - Golduck Water Sport        (on the boss)
P3 - Infernape Captivate Ad     (on the ad)
P2 - Claydol Psych Up P1        (on the P1 player)
P2 - Claydol Power Swap (Ad)    (parens are optional)
```

### Ad-dependent moves

If a turn's move depends on which **ad** spawned alongside the boss, put just
the mon on the `P<n> -` line and list one `* <Ad> <Move>` line per possible
ad (the `Ad`/`Boss`/`Self` target works here too). A dropdown (top right of
the window) picks the ad.

```
Turn 1
P1 - Golduck Water Sport        (fixed - same for every ad)
P3 - Infernape
* Charizard: Captivate Ad
* Magmortar: Captivate Ad
* Garchomp: Switcheroo Ad
* Golem: Switcheroo Ad
* Salamence: Scary Face Ad
```

The dropdown lists whatever ads appear in the section, in first-seen order,
and defaults to the first.

A check reads `–` when the block doesn't pin anything for it, and `⋯` when an
earlier breed check has to be fixed first.
