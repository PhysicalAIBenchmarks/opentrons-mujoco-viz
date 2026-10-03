"""
opentrons.visualization
=======================
MuJoCo 3D visualisation of Opentrons OT-2 protocols.

Quick start
-----------
    from opentrons.visualization import render_protocol, parse_simulate_output
    import subprocess

    result = subprocess.run(
        ["opentrons_simulate", "my_protocol.py"],
        capture_output=True, text=True,
    )
    events = parse_simulate_output(result.stdout)
    render_protocol(events, "run.mp4")

Or drive the scene directly:

    from opentrons.visualization import WetLabScene

    with WetLabScene() as scene:
        scene.apply_event({"type": "pick", "slot": 1})
        scene.apply_event({"type": "aspirate", "volume": 200, "slot": 3, "well": "A1"})
        frame = scene.render_with_hud()
"""

from .scene import WetLabScene, SLOT_XY
from .event_driver import render_protocol, render_protocol_from_simulate, parse_simulate_output
from .modules import (
    ProtocolState,
    MagneticModuleState,
    TemperatureModuleState,
    ThermocyclerState,
    HeaterShakerState,
)

__all__ = [
    "WetLabScene",
    "SLOT_XY",
    "render_protocol",
    "render_protocol_from_simulate",
    "parse_simulate_output",
    "ProtocolState",
    "MagneticModuleState",
    "TemperatureModuleState",
    "ThermocyclerState",
    "HeaterShakerState",
]

__version__ = "0.1.0"
