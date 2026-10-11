# Rendering qte77's low-cost rigs with this viewer

Research note, 2026-10-11. Full survey of the four projects:
[Text2WetLab `docs/qte77-projects.md`](https://github.com/PhysicalAIBenchmarks/Text2WetLab/blob/claude/research-github-projects-yoz36a/docs/qte77-projects.md).

qte77 is building an open, sub-$1k self-driving lab. Two of its repos move liquid:

- [i3mega-pipettebot](https://github.com/qte77/i3mega-pipettebot): a stock Anycubic i3 Mega turned into a 3-axis gantry
  carrying an 8-channel DLAB dPette+. The host sends G-code, and the eight channels share one piston, so it works on
  whole columns. 208 tests pass, and it has been run on hardware.
- [so101-biolab-automation](https://github.com/qte77/so101-biolab-automation): SO-101 arms on LeRobot, with a tool dock,
  a syringe or electronic pipette and an eLabFTW client. 321 tests pass in stub mode; the hardware is untested.

Neither has a 3D view of a protocol run. so101 streams joint data to Rerun and Foxglove, and pipettebot plots its motion
profiles. Both would get a lot from what this package already does for the OT-2: an event log in, a video out.

## What carries over

The event schema in `event_driver.py` does not depend on the robot. `pick`, `aspirate`, `dispense`, `mix`, `blow_out`,
`drop` and `delay` with `slot`/`well`/`volume` describe a pipettebot run just as well as an OT-2 one. `WetLabScene` and
`modules.py` hold the state (tip, pipette volume, well volumes) separately from the MuJoCo model. The robot-specific
parts are the model and the slot geometry.

## What does not (gaps found while reading `scene.py`)

1. **The deck is fixed to the OT-2.** `SLOT_XY` holds the OT-2's 12 slot centres. The i3 deck is a 220 × 220 mm plate
   with four anchors (tip box, reservoir, a plate, a tip-release bar; see pipettebot `docs/deck-layout.md`), addressed in
   Marlin millimetres with Y=0 at the back.
2. **Moves ignore the well.** `apply_event` calls `move_to_slot(slot, …)` with no `well_offset_x`, so every well of a
   plate is drawn at the slot centre. For an 8-channel rig, the column is the information that matters.
3. **Only one column is coloured.** `_sync_visuals` colours wells `A1`–`H1` of slot 2 and nothing else, so a full-plate
   fill shows one column changing.
4. **One channel, fixed scale.** The tip-liquid indicator is a single geom, normalised to 200 µL.

None of these is wrong for the current OT-2 renders, but each would need fixing before another rig could use the
package.

## Proposed path, smallest first

1. **Address wells properly.** Compute the well offset from the SBS pitch (9 mm, A1 at 14.38/11.24 mm from the plate
   corner; so101 `plate.py` has the same constants) and colour all 96 wells of every plate slot. This is a pure OT-2
   improvement and a prerequisite for everything below.
2. **Make the deck a parameter.** Have `WetLabScene(deck=…)` take slot centres and a model XML, keeping `OT2_DECK` as
   the default. An `I3_DECK` could map pipettebot's anchors to pseudo-slots (1 = reservoir, 2 = plate, 10 = tip box,
   12 = release bar).
3. **Add a multichannel head.** Add `channels: int` to the pipette state. An 8-channel `aspirate`/`dispense` updates
   rows A–H of one column, which is the semantics pipettebot's `bot.py` documents.
4. **Add a log adapter.** pipettebot already tees its G-code stream to a file. A `parse_pipettebot_log()` next to
   `parse_simulate_output()` could rebuild events from `G1` targets matched to the deck anchors plus the dPette
   SUCK/BLOW calls, or the showcases could write the event JSON directly, which is simpler and more robust.

With 1–3 in place, Text2WetLab can render the same task's IR on the OT-2 and on the gantry side by side. Text2WetLab's
`eval/embodiment_fit.py` already says which tasks fit the gantry: AMPure and colony PCR are fully column-wise and are
blocked only by deck size.
