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
* Per-slot state (levels, dead flags, medals) stays keyed by slot; everything keyed by *who the merc is* goes through PERM:
  weapon id (`$C352`/`$C65A`, seeded for the starting merc), sprite colours, level-cap and stat tables, panel layouts,
  portraits, the party-screen names/portraits, and the tent dialogue panel/portrait (`dat_00CA82`/`dat_00CA3E`).
* The "X JOINED YOUR PARTY" line is remapped too (Rifle has no stock line, so one is added).
* New code (~850 bytes, `stubs.s`) lives in the unused `$FF` padding after the Z80 driver at `$FCFA0`; `randomizer.py`
  lists the 21 hook sites (each asserts the original bytes, so it only applies to the right ROM).

## Testing
`test_start.py` boots a ROM into Original Mission 1 and prints the shuffle (`DELAY=n` varies the menu dwell time);
`tools/emu/watch_spawns.py` (`LOAD_STATE`, `RAM_RANGE`, `explore`) drives the game to the Mission 2 tent.

## Known gaps
* The "JOINED YOUR PARTY" message remap is untested in play (the line never showed up in my emulator runs).
* Portrait palettes on the party screen follow the slot, not the merc, so a shuffled portrait can look slightly off.
* Tents were exercised in Mission 2 (full), and via the hidden round select (`tools/emu/round_select.py`) in rounds 4 and 6: join header,
  shop panel and carrier panels all followed the shuffle. Deaths/revives, rounds 3/5/7 tents and the ending are untested.
