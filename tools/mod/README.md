# Randomized Mode for Mercs (Mega Drive)

An optional patch that adds a fourth line to the mode menu, **ORIGINAL RANDOMIZED MERCS**. It plays Original mode with the
party shuffled each new game: you start as a random one of Rifle, Burner, Launcher, Laser or Homing, and the tents hand out the
other four in a random order. Plain Original mode and Arcade mode behave exactly as in the original game.

It is a separate patch: the disassembly (`mercs.asm`) and your ROM file are never modified by the tools.

## For players: applying the patch

You need your own copy of the Mercs ROM (the 1,048,576-byte Mega Drive dump, SHA-256 `f56ddf669afe63920bff1df792773ef4b3c4440b3f1655b1a012f17bb2eef379`).

| File | What it is | SHA-256 |
|---|---|---|
| `mercs_randomized.ips` | the patch. Apply it to a **clean original ROM** with any IPS patcher (for example Lunar IPS or Floating IPS) | `e98e1784cd5761218546979a5bb8ebf49581f8ef094956209cded78fe622259b` |
| `mercs_randomized_invulnerable.ips` | the same plus invulnerability, **for testing only**. Use it *instead of* the normal patch, never on top of it | `ccd7a90a14ef80ef992dde1080b8ad5acefc962f0b62ba5616fad4b9795c8403` |

These are checksums of the `.ips` files, so you can confirm a download is the current version (`check.py` fails if they go stale).

Do not apply either patch to a ROM that is already patched. The patch also fixes the ROM's header checksum (the game verifies it at boot).

Playing it: on the mode screen choose the third line, ORIGINAL RANDOMIZED MERCS, and press START. The order is chosen when the game starts, from
how long you sat in the menus, so it differs from run to run. A continue keeps the same order.

## For developers: building

    python3 tools/mod/randomizer.py mercs.bin out.bin [--ips out.ips] [--invulnerable]
    python3 tools/mod/check.py mercs.bin          # regression check

Needs the m68k binutils (`apt install binutils-m68k-linux-gnu`). `randomizer.py` assembles `stubs.s`, writes the new code into unused ROM padding,
and applies the hooks; each hook site asserts the original bytes, so it only applies to the right ROM. The committed `.ips` files are rebuilt from
the same code (`check.py` fails if they are stale).

## How it works

* **The shuffle.** `PERM` (5 bytes at `$FFC3E0`) maps party slot to merc (0 Rifle, 1 Burner, 2 Launcher, 3 Laser, 4 Homing); `$FFC3E5` marks it valid.
  It is built lazily on first use: a Fisher-Yates over the game's RNG, seeded from `VBlank_Counter` (how long the player sat in the menus), the VDP HV
  counter, and a few warm-up RNG steps. The starting merc's weapon id (`$C352`/`$C65A`) is set at the same time and the weapon art reload is requested.
* **The gate.** `RMODE` (word at `$FFC3E8`) is set only when the new menu line is chosen with START and cleared when Arcade or Original is chosen, so
  nothing else changes. (An earlier build keyed on `Game_Mode == 3`, which missed Original mode's other difficulty value.)
* **Slot versus merc.** Dead flags (`Merc_Flags`) and the party-screen cursor stay keyed by party slot. Everything keyed by *who the merc is* goes
  through `PERM`: weapon id, sprite colours, level-cap and stat tables, panel layouts, portraits, the party-screen names and portraits, the tent
  dialogue panel and portrait, and the "X JOINED YOUR PARTY" line (Rifle has no stock line, so one is added).
* **Stat records.** The per-merc records (`$C370 + 14 x merc`: power, speed, life levels, medals, ...) follow the merc through `PERMREC` (5 words at
  `$FFC3F0`, replacing the ROM table `Merc_RecordAddrs`), so each merc keeps their own upgrades and the right maxima: Rifle 4 life-ups / 10 power / 5 speed,
  Burner 2/10/3, Launcher 5/10/2, Laser 4/4/4, Homing 2/3/3. The party screen's row scripts hard-code each slot's original merc (bar maxima, record
  pointers), so three hooks (`SiteB64`, `SiteQ`, `SiteX`) redirect them to the merc standing in that slot.
* **The menu.** A new text script and highlight table (`MenuScript`/`MenuHilite`), cursor wrap limits, START handling (`NewStart` replaces `sub_006536`)
  and next-state tables (`SiteN1/N2`) add the line.
* **Size and placement.** About 1.4 KB of new 68000 code in the `$FF` padding at `$FCFA0` (4,192 bytes free there), 36 hook sites.
* **Invulnerable build.** One extra hook replaces the head of `sub_00E278`, the per-frame `Player_Invuln_Timer` handler, and keeps the timer at `$7FFF`, so
  every damage check that respects the timer is skipped.

## Testing and results

`check.py mercs.bin` builds the patch, checks both `.ips` files are current, then boots the game three ways in the emulator: the new menu line (shuffle
valid, weapon id matches the starting merc, starting merc varies across menu timings), plain Original (no shuffle, Rifle start) and Arcade (no shuffle).
`test_start.py` prints the shuffle for a given menu timing (`DOWNS=n DELAY=n`). `tools/emu/round_select.py ... --randomized` starts any round on the new line.

Verified in the emulator:
* the starting merc varies; weapon id, sprite colours and shop panels follow it;
* tents in Mission 2 end to end and in rounds 4 and 6 (via the hidden round select): join header, shop panel, carrier panels and the party screen follow the shuffle;
* death: the dead slot is greyed on the party screen with the right names, and the replacement gets the right weapon id and colours;
* the invulnerable build survives 9,000 frames of random play in round 6, where the normal build loses its first merc after about 2,850.

Playtested by hand (with the invulnerable build) through the missions reached: the shuffle, menu entry, joins, party screen, stat caps and the join message
all worked, and no portrait distortion was seen.

### Fixed after the first playtests
* Party-screen cursor stuck on the bottom rows: the highlight frame is a palette entry per party *slot*, and an earlier hook had moved it to the merc's
  original row. The hook was removed.
* Wrong stat caps for joined mercs: the stat records and the party-screen bar scripts are now per merc (above).

## Known gaps
* **Revive item.** Buying the tent's revive item works (medals are deducted), but the actual revive on the carrier's death was not observed. The revive code is
  slot-based like the dead flags, so it should work.
* **Untested.** The tents in rounds 3, 5 and 7, the Original ending, and real hardware.
* **Harrier report (parked).** A playtest report that the Mission 1 Harrier never attacks if the player hides in a corner while it appears (started as Homing).
  Not reproduced: an emulator A/B (state saved when `ObjType_B4` spawns; idle, corner and corner+fire; original ROM versus the patched ROM with a forced Homing
  start) showed the Harrier moving and firing normally in every case, and its AI (`ObjType_B1`/`B3`) reads no merc or weapon variable. If it comes back: does it
  happen on the unpatched ROM, which corner, and does the player retreat before or after the boss sprite starts appearing?
* **Party-screen portrait palettes** follow the slot, not the merc, so a shuffled portrait could look slightly off (not observed in play).
