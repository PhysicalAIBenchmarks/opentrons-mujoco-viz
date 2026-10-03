# opentrons-mujoco-viz

MuJoCo 3D visualisation of Opentrons OT-2 protocols, driven by `opentrons_simulate` run logs.

```
pip install git+https://github.com/PhysicalAIBenchmarks/opentrons-mujoco-viz
```

## Quick start

```python
from opentrons.visualization import render_protocol, parse_simulate_output
import subprocess

# Run your protocol through opentrons_simulate
result = subprocess.run(
    ["opentrons_simulate", "my_protocol.py"],
    capture_output=True, text=True,
)

# Parse the text output into events
events = parse_simulate_output(result.stdout)

# Render to MP4 (or .gif)
render_protocol(events, "run.mp4", camera="iso", hud=True)
```

Or use the convenience wrapper:

```python
from opentrons.visualization import render_protocol_from_simulate

render_protocol_from_simulate("my_protocol.py", "run.mp4")
```

## Scene API

```python
from opentrons.visualization import WetLabScene

with WetLabScene() as scene:
    # Apply events one at a time
    scene.apply_event({"type": "pick",      "slot": 1, "well": "A1"})
    scene.apply_event({"type": "aspirate",  "volume": 200, "slot": 3, "well": "A1"})
    scene.apply_event({"type": "dispense",  "volume": 100, "slot": 2, "well": "A1"})
    scene.apply_event({"type": "engage",    "height": 13.0})
    scene.apply_event({"type": "tc_open_lid"})
    scene.apply_event({"type": "delay",     "minutes": 0, "seconds": 30})

    frame = scene.render_with_hud(camera="iso")  # numpy H×W×3
```

## Supported event types

| type | required keys | description |
|---|---|---|
| `pick` | `slot`, `well` | pick up tip |
| `drop` | — | drop/return tip |
| `aspirate` | `volume`, `slot`, `well` | aspirate |
| `dispense` | `volume`, `slot`, `well` | dispense |
| `mix` | `volume`, `repetitions` | in-well mix |
| `blow_out` | `slot`, `well` | blow out |
| `touch_tip` | — | touch tip |
| `air_gap` | `volume` | air gap |
| `delay` | `minutes`, `seconds` | protocol delay |
| `pause` | — | pause robot |
| `engage` | `height` | engage magnetic module |
| `disengage` | — | disengage magnetic module |
| `temp_set` | `celsius` | set temperature module |
| `temp_deactivate` | — | deactivate temperature module |
| `tc_open_lid` | — | open thermocycler lid |
| `tc_close_lid` | — | close thermocycler lid |
| `tc_block_temp` | `celsius` | set TC block temperature |
| `tc_lid_temp` | `celsius` | set TC lid temperature |
| `tc_execute_profile` | — | run TC profile |
| `tc_deactivate` | — | deactivate thermocycler |
| `hs_shake` | `rpm` | set heater-shaker speed |
| `hs_temp` | `celsius` | set heater-shaker temperature |
| `hs_open_latch` | — | open heater-shaker latch |
| `hs_close_latch` | — | close heater-shaker latch |
| `hs_deactivate` | — | deactivate heater-shaker |

## Architecture

```
opentrons/visualization/
├── __init__.py          # public API
├── scene.py             # WetLabScene — MuJoCo model + state + rendering
├── event_driver.py      # parse_simulate_output + render_protocol
├── modules.py           # pure-Python state dataclasses
├── generate_labware.py  # build OBJ meshes from Opentrons shared-data JSON
└── assets/
    └── ot2.xml          # MJCF: 11-slot deck + gantry + module geoms
```

**Physics**: MuJoCo 3.x position-controlled Cartesian gantry (X/Y/Z + TC lid).
Liquid volumes are tracked analytically — MuJoCo carries geometry only.

**Modules visualised**:
- Magnetic Module — bar colour and LED change on engage/disengage
- Temperature Module — LED gradient cold→hot (blue → red)
- Thermocycler — lid slides open/closed via MuJoCo actuator
- Heater-Shaker — latch colour (green=open, red=locked) + activity LED

## Namespace package

The module lives at `opentrons.visualization` — the same path it would occupy
if upstreamed to `Opentrons/opentrons`. The `opentrons/` directory uses
`pkgutil.extend_path` so it coexists with the installed `opentrons` package
in environments that have both.

**Install order matters**: install `opentrons` first, then this package.

## Roadmap

- [ ] Real labware geometry via `generate_labware.py` + `opentrons-shared-data`
- [ ] `MjSpec`-based procedural scene builder (no hand-authored XML)
- [ ] Correct gantry waypoints from `opentrons.motion_planning.get_waypoints`
- [ ] `DurationEstimator` integration for accurate elapsed time
- [ ] PR to `Opentrons/opentrons` adding `opentrons/visualization/`

## Related

- [Text2WetLab](https://github.com/PhysicalAIBenchmarks/Text2WetLab) — NL → wet lab robot protocol benchmark
- [opentrons_simulate](https://github.com/Opentrons/opentrons) — official Opentrons Python package

## License

Apache 2.0
