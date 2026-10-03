"""
render_protocol — turn a parsed opentrons_simulate run log into an MP4/GIF.

The event format matches the output of runlog.py from Text2WetLab / Devin tasks.

Quick start
-----------
    from opentrons.visualization import render_protocol
    import subprocess, re

    result = subprocess.run(
        ["opentrons_simulate", "protocol.py"],
        capture_output=True, text=True,
    )
    events = parse_simulate_output(result.stdout)
    render_protocol(events, "protocol_run.mp4")
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np

from .scene import WetLabScene

# ── Run-log parser ─────────────────────────────────────────────────────────────
# Matches the text output format of `opentrons_simulate`.
WELL = r"well (\w+) of (.+) on (?:slot )?(\d+|Slot \d+)"

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("aspirate",  re.compile(r"Aspirating ([\d.]+) uL from " + WELL)),
    ("dispense",  re.compile(r"Dispensing ([\d.]+) uL into " + WELL)),
    ("mix",       re.compile(r"Mixing (\d+) times with a volume of ([\d.]+) uL")),
    ("blow_out",  re.compile(r"Blowing out at " + WELL)),
    ("touch_tip", re.compile(r"Touching tip")),
    ("pick",      re.compile(r"Picking up tip from (?:well (\w+) of .+ on (?:slot )?(\d+))")),
    ("pick_any",  re.compile(r"Picking up tip")),
    ("drop",      re.compile(r"(?:Dropping|Returning) tip")),
    ("delay",     re.compile(r"Delaying for (\d+) minutes and ([\d.]+) seconds")),
    ("pause",     re.compile(r"Pausing robot operation")),
    ("engage",    re.compile(r"Engaging Magnetic Module.*?at height ([\d.]+)")),
    ("engage2",   re.compile(r"Engaging Magnetic Module")),
    ("disengage", re.compile(r"Disengaging Magnetic Module")),
    ("temp_set",  re.compile(r"Setting Temperature Module temperature to ([\d.]+)")),
    ("temp_deactivate", re.compile(r"Deactivating Temperature Module")),
    ("tc_open",   re.compile(r"Opening Thermocycler lid")),
    ("tc_close",  re.compile(r"Closing Thermocycler lid")),
    ("tc_block",  re.compile(r"Setting Thermocycler block temperature to ([\d.]+)")),
    ("tc_lid_t",  re.compile(r"Setting Thermocycler lid temperature to ([\d.]+)")),
    ("tc_profile",re.compile(r"Executing Thermocycler profile")),
    ("tc_deact",  re.compile(r"Deactivating Thermocycler")),
    ("hs_shake",  re.compile(r"Setting Heater-Shaker speed to ([\d.]+) rpm")),
    ("hs_temp",   re.compile(r"Setting Heater-Shaker temperature to ([\d.]+)")),
    ("hs_open",   re.compile(r"Opening Heater-Shaker latch")),
    ("hs_close",  re.compile(r"Closing Heater-Shaker latch")),
    ("hs_deact",  re.compile(r"Deactivating Heater-Shaker")),
]


def parse_simulate_output(text: str) -> list[dict]:
    """
    Parse the text output of `opentrons_simulate` into a list of event dicts.

    Compatible with the Devin task runlog.py format used in Text2WetLab.
    """
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        matched = False
        for tag, pat in _PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            ev: dict = {"type": tag, "_raw": line}

            if tag == "aspirate":
                ev["type"] = "aspirate"
                ev["volume"] = float(m.group(1))
                ev["well"] = m.group(2)
                ev["slot"] = _slot(m.group(4))
            elif tag == "dispense":
                ev["type"] = "dispense"
                ev["volume"] = float(m.group(1))
                ev["well"] = m.group(2)
                ev["slot"] = _slot(m.group(4))
            elif tag == "mix":
                ev["type"] = "mix"
                ev["repetitions"] = int(m.group(1))
                ev["volume"] = float(m.group(2))
            elif tag == "blow_out":
                ev["type"] = "blow_out"
                ev["well"] = m.group(1)
                ev["slot"] = _slot(m.group(3))
            elif tag == "pick":
                ev["type"] = "pick"
                ev["well"] = m.group(1)
                ev["slot"] = _slot(m.group(2))
            elif tag == "pick_any":
                ev["type"] = "pick"
            elif tag == "drop":
                ev["type"] = "drop"
            elif tag == "delay":
                ev["type"] = "delay"
                ev["minutes"] = int(m.group(1))
                ev["seconds"] = float(m.group(2))
            elif tag == "pause":
                ev["type"] = "pause"
            elif tag == "engage":
                ev["type"] = "engage"
                ev["height"] = float(m.group(1))
            elif tag == "engage2":
                ev["type"] = "engage"
                ev["height"] = 13.0
            elif tag == "disengage":
                ev["type"] = "disengage"
            elif tag == "temp_set":
                ev["type"] = "temp_set"
                ev["celsius"] = float(m.group(1))
            elif tag == "temp_deactivate":
                ev["type"] = "temp_deactivate"
            elif tag == "tc_open":
                ev["type"] = "tc_open_lid"
            elif tag == "tc_close":
                ev["type"] = "tc_close_lid"
            elif tag == "tc_block":
                ev["type"] = "tc_block_temp"
                ev["celsius"] = float(m.group(1))
            elif tag == "tc_lid_t":
                ev["type"] = "tc_lid_temp"
                ev["celsius"] = float(m.group(1))
            elif tag == "tc_profile":
                ev["type"] = "tc_execute_profile"
            elif tag == "tc_deact":
                ev["type"] = "tc_deactivate"
            elif tag == "hs_shake":
                ev["type"] = "hs_shake"
                ev["rpm"] = float(m.group(1))
            elif tag == "hs_temp":
                ev["type"] = "hs_temp"
                ev["celsius"] = float(m.group(1))
            elif tag == "hs_open":
                ev["type"] = "hs_open_latch"
            elif tag == "hs_close":
                ev["type"] = "hs_close_latch"
            elif tag == "hs_deact":
                ev["type"] = "hs_deactivate"

            events.append(ev)
            matched = True
            break  # first matching pattern wins per line

    return events


def _slot(s: str) -> Optional[int]:
    m = re.search(r"(\d+)", str(s))
    return int(m.group(1)) if m else None


# ── Renderer ───────────────────────────────────────────────────────────────────

def render_protocol(
    events: list[dict],
    output_path: str | Path = "protocol_run.mp4",
    camera: str = "iso",
    fps: int = 12,
    frames_per_event: int = 4,
    hud: bool = True,
    xml_path: Optional[Path] = None,
    render_w: int = 960,
    render_h: int = 540,
) -> dict:
    """
    Render a parsed opentrons_simulate run log to an MP4 or GIF.

    Parameters
    ----------
    events:
        List of event dicts from parse_simulate_output().
    output_path:
        Destination file. Extension determines format (.mp4 or .gif).
    camera:
        Camera name: "iso", "side", "top", "front", or "deck".
    fps:
        Output frame rate.
    frames_per_event:
        Extra still frames captured after each event (for smooth playback).
    hud:
        Overlay HUD showing pipette state and module status.
    xml_path:
        Override MJCF path. Defaults to bundled assets/ot2.xml.
    render_w, render_h:
        Renderer dimensions.

    Returns
    -------
    dict with keys: output_path, frame_count, event_count, final_state
    """
    import imageio

    output_path = Path(output_path)
    render_fn = WetLabScene.render_with_hud if hud else WetLabScene.render

    with WetLabScene(xml_path=xml_path, render_w=render_w, render_h=render_h) as scene:
        frames: list[np.ndarray] = []
        frames.append(render_fn(scene, camera))

        for ev in events:
            new_frames = scene.apply_event(ev)
            frames.extend(new_frames)
            for _ in range(frames_per_event - 1):
                frames.append(render_fn(scene, camera))

        imageio.mimsave(str(output_path), frames, fps=fps)

        return {
            "output_path": str(output_path),
            "frame_count": len(frames),
            "event_count": len(events),
            "final_state": scene.state,
        }


def render_protocol_from_simulate(
    protocol_path: str | Path,
    output_path: str | Path = "protocol_run.mp4",
    camera: str = "iso",
    fps: int = 12,
    **kwargs,
) -> dict:
    """
    Run opentrons_simulate on a protocol file and render the result.

    Requires opentrons[extras] in the same environment, or opentrons_simulate
    available on PATH.
    """
    import subprocess

    result = subprocess.run(
        ["opentrons_simulate", str(protocol_path)],
        capture_output=True, text=True,
    )
    events = parse_simulate_output(result.stdout)
    return render_protocol(events, output_path=output_path, camera=camera, fps=fps, **kwargs)
