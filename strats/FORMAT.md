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

## Stat bounds

Each entry is `<number><modifier> <STAT>`, where STAT is one of
`HP Atk Def SpA SpD Spe`. Only the stats you list are checked.

| Written        | Means                                  |
|----------------|----------------------------------------|
| `301 HP`       | exactly 301                            |
| `294+ Spe`     | 294 or more                            |
| `226- Spe`     | 226 or less                            |
| `180-226 Spe`  | between 180 and 226 (inclusive)        |
