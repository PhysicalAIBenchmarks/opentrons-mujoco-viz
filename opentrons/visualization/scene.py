"""
WetLabScene — MuJoCo 3D scene for Opentrons OT-2 protocol visualisation.

Driven by parsed opentrons_simulate run-log events (see event_driver.py).
Liquid volumes are tracked analytically; MuJoCo handles gantry kinematics only.
"""
from __future__ import annotations

import pathlib
from typing import Optional

import numpy as np
import mujoco

from .modules import ProtocolState

XML_PATH = pathlib.Path(__file__).parent / "assets" / "ot2.xml"

SAFE_Z = -0.02
WORK_Z = -0.17

# Slot centre positions [x, y] in metres (deck origin = centre of slot-2 row)
# Row 1: y=-.170, Row 2: y=-.085, Row 3: y=0, Row 4: y=.085
SLOT_XY: dict[int, tuple[float, float]] = {
    1:  (-.152, -.170),
    2:  ( 0.00, -.170),
    3:  ( .152, -.170),
    4:  (-.152, -.085),
    5:  ( 0.00, -.085),
    6:  ( .152, -.085),
    7:  (-.152,  0.00),
    8:  ( 0.00,  0.00),
    9:  ( .152,  0.00),
    10: (-.152,  0.085),
    11: ( 0.00,  0.085),
    12: ( .152,  0.085),  # trash
}

# Gantry ctrl targets for common slot/well positions
# Derived: ctrl_x = slot_x, ctrl_y = slot_y - 0.17 + 0.095 = slot_y - 0.075
# (because y_head global y = 0.265 - 0.095 + j_y, we need j_y = slot_y - 0.17)
def _slot_ctrl_y(slot_y: float) -> float:
    return slot_y - 0.17


class WetLabScene:
    """
    MuJoCo scene for a single OT-2 protocol run.

    Parameters
    ----------
    xml_path:
        Path to the MJCF model. Defaults to the bundled assets/ot2.xml.
    render_w, render_h:
        Offscreen renderer dimensions.
    """

    RENDER_W = 960
    RENDER_H = 540
    PIPETTE_MAX = 1000.0

    def __init__(
        self,
        xml_path: Optional[pathlib.Path] = None,
        render_w: int = 960,
        render_h: int = 540,
    ):
        self.RENDER_W = render_w
        self.RENDER_H = render_h
        path = xml_path or XML_PATH
        self.model = mujoco.MjModel.from_xml_path(str(path))
        self.data = mujoco.MjData(self.model)
        self._renderer = mujoco.Renderer(self.model, self.RENDER_H, self.RENDER_W)

        # Actuator indices
        self._ax = self._act("act_x")
        self._ay = self._act("act_y")
        self._az = self._act("act_z")
        self._atc = self._act("act_tc_lid")

        # Geom indices
        def gid(name: str) -> int:
            return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_GEOM, name)

        self._g_pip_tip    = gid("pip_tip")
        self._g_pip_liquid = gid("pip_liquid")
        self._g_tip_A1     = gid("tip_A1")
        self._g_mag_bar    = gid("mag_bar")
        self._g_mag_led    = gid("mag_led")
        self._g_temp_led   = gid("temp_led")
        self._g_tc_lid     = gid("tc_lid")
        self._g_tc_led     = gid("tc_led")
        self._g_hs_latch   = gid("hs_latch")
        self._g_hs_led     = gid("hs_led")

        # Well geom indices (plate slot 2)
        self._g_wells: dict[str, int] = {}
        for row in "ABCDEFGH":
            name = f"w_{row}1"
            try:
                self._g_wells[name] = gid(name)
            except Exception:
                pass

        self.state = ProtocolState()
        self._move_to(0.0, _slot_ctrl_y(SLOT_XY[2][1]), SAFE_Z, steps=150)
        self._sync_visuals()

    def _act(self, name: str) -> int:
        return mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)

    # ── Gantry motion ─────────────────────────────────────────────────────────
    def _move_to(self, x: float, y: float, z: float, steps: int = 120) -> None:
        self.data.ctrl[self._ax] = x
        self.data.ctrl[self._ay] = y
        self.data.ctrl[self._az] = z
        for _ in range(steps):
            mujoco.mj_step(self.model, self.data)

    def move_to_slot(self, slot: int, well_offset_x: float = 0.0, work: bool = False, steps: int = 120) -> None:
        """Move pipette over a slot, optionally descending to working depth."""
        sx, sy = SLOT_XY.get(slot, (0.0, 0.0))
        ctrl_y = _slot_ctrl_y(sy)
        # Rise first
        cx, cy = self.data.ctrl[self._ax], self.data.ctrl[self._ay]
        self._move_to(cx, cy, SAFE_Z, steps=60)
        self._move_to(sx + well_offset_x, ctrl_y, SAFE_Z, steps=steps)
        if work:
            self._move_to(sx + well_offset_x, ctrl_y, WORK_Z, steps=60)

    # ── Visual sync ───────────────────────────────────────────────────────────
    def _sync_visuals(self) -> None:
        s = self.state

        # Pipette tip
        a = 1.0 if s.has_tip else 0.0
        self.model.geom_rgba[self._g_pip_tip][:] = [.95, .80, .10, a]
        self.model.geom_rgba[self._g_tip_A1][:] = [.95, .58, .05, 1.0 - a]

        # Liquid in tip
        la = min(s.pipette_vol / 200.0, 1.0) if s.pipette_vol > 0 else 0.0
        self.model.geom_rgba[self._g_pip_liquid][:] = [.00, .62, .92, la]

        # Plate well colours (slot 2)
        slot2 = s.well_volumes.get(2, {})
        for row_idx, row in enumerate("ABCDEFGH"):
            key = f"w_{row}1"
            if key in self._g_wells:
                vol = slot2.get(f"{row}1", 0.0)
                f = min(vol / 200.0, 1.0)
                if f > 0:
                    g = self.model.geom_rgba[self._g_wells[key]]
                    g[:] = [.02, .40 + .30 * f, .90, max(.4 * f, .15)]
                else:
                    self.model.geom_rgba[self._g_wells[key]][:] = [.06, .04, .13, 1.0]

        # Magnetic module
        if s.magnetic.engaged:
            self.model.geom_rgba[self._g_mag_bar][:] = [.20, .60, 1.0, 1.0]
            self.model.geom_rgba[self._g_mag_led][:] = [.20, .60, 1.0, 1.0]
        else:
            self.model.geom_rgba[self._g_mag_bar][:] = [.35, .35, .45, 1.0]
            self.model.geom_rgba[self._g_mag_led][:] = [.35, .35, .45, 1.0]

        # Temperature module LED (blue=cold <25, yellow=warming, red=hot >60)
        tc = s.temperature.celsius
        if not s.temperature.active:
            self.model.geom_rgba[self._g_temp_led][:] = [.35, .35, .45, 1.0]
        elif tc < 30:
            self.model.geom_rgba[self._g_temp_led][:] = [.20, .40, .90, 1.0]
        elif tc < 60:
            t = (tc - 30) / 30.0
            self.model.geom_rgba[self._g_temp_led][:] = [.20 + .75 * t, .40 - .15 * t, .90 - .80 * t, 1.0]
        else:
            self.model.geom_rgba[self._g_temp_led][:] = [.95, .25, .10, 1.0]

        # Thermocycler lid position
        if s.thermocycler.lid_open:
            self.data.ctrl[self._atc] = 0.055
        else:
            self.data.ctrl[self._atc] = 0.0
        for _ in range(80):
            mujoco.mj_step(self.model, self.data)

        # TC LED
        if s.thermocycler.profile_running:
            self.model.geom_rgba[self._g_tc_led][:] = [.95, .50, .10, 1.0]
        else:
            self.model.geom_rgba[self._g_tc_led][:] = [.35, .35, .45, 1.0]

        # Heater-shaker latch
        if s.heater_shaker.latch_open:
            self.model.geom_rgba[self._g_hs_latch][:] = [.10, .90, .35, 1.0]
        else:
            self.model.geom_rgba[self._g_hs_latch][:] = [.90, .20, .15, 1.0]

        # HS LED
        if s.heater_shaker.active:
            self.model.geom_rgba[self._g_hs_led][:] = [.10, .90, .35, 1.0]
        else:
            self.model.geom_rgba[self._g_hs_led][:] = [.35, .35, .45, 1.0]

    # ── Event application ─────────────────────────────────────────────────────
    def apply_event(self, event: dict, motion_steps: int = 100) -> list[np.ndarray]:
        """
        Apply one run-log event, animate the gantry, and return rendered frames.

        Parameters
        ----------
        event:
            Parsed run-log event dict. Keys depend on event type:
            - aspirate/dispense: type, volume, slot, well
            - pick/drop: type, slot (optional)
            - delay: type, minutes, seconds
            - engage/disengage: type, height (engage only)
            - temp_set: type, celsius
            - tc_open_lid / tc_close_lid / tc_block_temp / tc_execute_profile
            - hs_shake / hs_open_latch / hs_close_latch
        motion_steps:
            Physics steps per gantry move segment.

        Returns
        -------
        list of RGB frames (H×W×3 uint8)
        """
        frames: list[np.ndarray] = []
        etype = event.get("type", "")
        slot = event.get("slot")

        # Gantry moves for pipette events
        if etype in ("pick", "aspirate", "dispense", "mix", "blow_out", "touch_tip"):
            if slot and slot in SLOT_XY:
                self.move_to_slot(slot, work=True, steps=motion_steps)
                frames.append(self.render())
            self.state.apply_event(event)
            self._sync_visuals()
            frames.append(self.render())
            # Rise
            if slot and slot in SLOT_XY:
                sx, sy = SLOT_XY[slot]
                self._move_to(sx, _slot_ctrl_y(sy), SAFE_Z, steps=60)
        elif etype == "drop":
            if slot and slot in SLOT_XY:
                self.move_to_slot(slot, work=True, steps=motion_steps)
            self.state.apply_event(event)
            self._sync_visuals()
            frames.append(self.render())
            if slot and slot in SLOT_XY:
                sx, sy = SLOT_XY[slot]
                self._move_to(sx, _slot_ctrl_y(sy), SAFE_Z, steps=60)
        else:
            # Non-motion events (delay, module ops): apply + sync
            self.state.apply_event(event)
            self._sync_visuals()

        frames.append(self.render())
        return frames

    # ── Rendering ─────────────────────────────────────────────────────────────
    def render(self, camera: str = "iso") -> np.ndarray:
        """Render current scene, returns H×W×3 uint8."""
        cam_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
        if cam_id >= 0:
            self._renderer.update_scene(self.data, camera=camera)
        else:
            cam = mujoco.MjvCamera()
            cam.type = mujoco.mjtCamera.mjCAMERA_FREE
            cam.lookat[:] = [0.0, -0.05, 0.06]
            cam.distance = 1.0
            cam.azimuth = 140.0
            cam.elevation = -28.0
            self._renderer.update_scene(self.data, camera=cam)
        return self._renderer.render().copy()

    def render_with_hud(self, camera: str = "iso") -> np.ndarray:
        """Render with overlaid HUD showing pipette state and module status."""
        pixels = self.render(camera)
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(
                figsize=(self.RENDER_W / 100, self.RENDER_H / 100), dpi=100, facecolor="none"
            )
            ax.axis("off")
            ax.imshow(pixels)

            s = self.state
            # Pipette state (top-left)
            ax.text(
                12, 22,
                f"step {s.step_count}  tip={'ON' if s.has_tip else 'OFF'}  {s.pipette_vol:.0f}µL"
                f"  t={s.elapsed_seconds:.0f}s",
                color="#00d4ff", fontsize=8, fontfamily="monospace",
                transform=ax.transData,
            )
            # Module status (top-right)
            module_lines = []
            if s.magnetic.engaged:
                module_lines.append(f"MAG ↑{s.magnetic.height_mm:.0f}mm")
            if s.temperature.active:
                module_lines.append(f"TEMP {s.temperature.celsius:.0f}°C")
            if s.thermocycler.lid_open:
                module_lines.append("TC lid OPEN")
            elif s.thermocycler.profile_running:
                module_lines.append(f"TC running")
            if s.heater_shaker.active:
                module_lines.append(f"HS {s.heater_shaker.rpm:.0f}rpm")
            for i, line in enumerate(module_lines):
                ax.text(
                    self.RENDER_W - 180, 22 + i * 18,
                    line, color="#ffcc44", fontsize=8, fontfamily="monospace",
                    transform=ax.transData,
                )
            if s.paused:
                ax.text(
                    self.RENDER_W // 2, self.RENDER_H // 2,
                    "⏸ PAUSED", color="#ff4444", fontsize=20,
                    ha="center", va="center", fontfamily="monospace",
                    transform=ax.transData,
                )

            fig.tight_layout(pad=0)
            fig.canvas.draw()
            w, h = fig.canvas.get_width_height()
            frame = np.frombuffer(fig.canvas.buffer_rgba(), dtype=np.uint8).reshape(h, w, 4)[..., :3]
            plt.close(fig)
            return frame
        except Exception:
            return pixels

    def reset(self) -> None:
        """Reset physics, liquid state, and module state to initial."""
        mujoco.mj_resetData(self.model, self.data)
        self.state = ProtocolState()
        self.data.ctrl[self._ax] = 0.0
        self.data.ctrl[self._ay] = _slot_ctrl_y(SLOT_XY[2][1])
        self.data.ctrl[self._az] = SAFE_Z
        self.data.ctrl[self._atc] = 0.0
        for _ in range(200):
            mujoco.mj_step(self.model, self.data)
        self._sync_visuals()

    def close(self) -> None:
        self._renderer.close()

    def __enter__(self) -> "WetLabScene":
        return self

    def __exit__(self, *_) -> None:
        self.close()
