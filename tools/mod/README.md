# Randomized Mode (Original mode party shuffle)

A separate patch - the disassembly and the original ROM are untouched.

    python3 tools/mod/randomizer.py mercs.bin mercs_randomized.bin [--ips out.ips]

`mercs_randomized.ips` is the same patch prebuilt (apply to the 1 MB Mercs ROM with any IPS tool; it also fixes the header checksum).

## What it does
In **Original mode** (`Game_Mode == 3`) the five mercs are shuffled each new game (Fisher-Yates over the game's RNG, seeded
from the menu dwell time `VBlank_Counter` and the VDP HV counter). You start as `PERM[0]` and every tent that used to
hand out the next fixed merc (Burner, Launcher, Laser, Homing) hands out the next one in the shuffled order. Arcade mode
is unchanged.

## How
* `PERM` (5 bytes at `$FFC3E0`) maps party slot -> merc (0 Rifle, 1 Burner, 2 Launcher, 3 Laser, 4 Homing); `$FFC3E5`
  is the "valid" marker (cleared when the mode is chosen, so a new game reshuffles lazily on first use).
* Dead flags (`Merc_Flags`) and the party-screen cursor stay keyed by slot. Everything keyed by *who the merc is* goes
  through PERM: weapon id (`$C352`/`$C65A`, seeded for the starting merc), sprite colours, level-cap and stat tables, panel
  layouts, portraits, the party-screen names/portraits, and the tent dialogue panel/portrait (`dat_00CA82`/`dat_00CA3E`).
* The per-merc stat records (`$C370 + 14*merc`: power/speed/life levels, medals, ...) follow the merc: `PERMREC` (5 words
  at `$FFC3F0`) replaces the ROM slot->record table `dat_00BE62`, so each merc keeps their own upgrades and the right
  maxima (Rifle 4 life/10 power/5 speed, Burner 2/10/3, Launcher 5/10/2, Laser 4/4/4, Homing 2/3/3). The party screen's
  row scripts (`dat_00BE6C`) hard-code each slot's original merc's bar maxima and record pointers, so three hooks
  (`SiteB64`, `SiteQ`, `SiteX`) shift them to the merc standing in that slot.
* The "X JOINED YOUR PARTY" line is remapped too (Rifle has no stock line, so one is added).
* New code (~1.2 KB, `stubs.s`) lives in the unused `$FF` padding after the Z80 driver at `$FCFA0`; `randomizer.py`
  lists the 29 hook sites (each asserts the original bytes, so it only applies to the right ROM).

## Testing
`check.py mercs.bin` is the regression check (patch builds, IPS up to date, shuffle valid and varied in Original mode, Arcade unaffected).
`test_start.py` boots a ROM into Original Mission 1 and prints the shuffle (`DELAY=n` varies the menu dwell time);
`tools/emu/watch_spawns.py` (`LOAD_STATE`, `RAM_RANGE`, `explore`) drives the game to the Mission 2 tent.

## Behaviour notes
* It is always on in Original mode; there is no separate menu entry. Arcade mode is untouched (`check.py` verifies this).
* The shuffle happens once per new game; continues keep it. The randomness comes from how long you sit in the menus, so
  an emulator that replays identical inputs will get the same order every time.

## Verified (emulator)
* Starting merc varies; weapon id, sprite colours and shop panels follow it.
* Tents: Mission 2 end to end, and rounds 4 and 6 via the round select - join header, shop panel and carrier panels
  follow the shuffle.
* Death: the dead slot is greyed on the party screen with the right names, and the replacement gets the right weapon
  id and colours.

## Fixed after first playtest
* Party-screen cursor stuck on the bottom rows: the highlight frame is a palette entry per party *slot*; an earlier hook
  moved it to the merc's original row. Removed.
* Wrong stat caps (upgrade slots) for joined mercs: stat records and the party-screen bar scripts are now per merc (above).

## Known gaps
* Reported: the Mission 1 Harrier sometimes never attacks if the player hides in a corner while it appears (started as
  Homing). Not reproduced: its AI (`ObjType_B1`/`B3`) reads no merc or weapon variable and attacks normally in emulator
  runs with Homing, so it may be vanilla behaviour; needs an A/B on the unpatched ROM.
* The "X JOINED YOUR PARTY" line remap is untested in play (the line never appeared in any run, original ROM included).
* Buying the tent's revive item works (medals are deducted), but the actual revive on the carrier's death was not
  observed; the revive code is slot-based like the dead flags, so it should be fine.
* Party-screen portrait palettes follow the slot, not the merc, so a shuffled portrait can look slightly off.
* Rounds 3, 5 and 7 tents, and the ending, are untested. Not tried on real hardware.
