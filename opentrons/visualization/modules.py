"""Module state dataclasses — pure Python, no MuJoCo dependency."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MagneticModuleState:
    engaged: bool = False
    height_mm: float = 0.0


@dataclass
class TemperatureModuleState:
    active: bool = False
    celsius: float = 23.0
    target_celsius: Optional[float] = None


@dataclass
class ThermocyclerState:
    lid_open: bool = True
    block_celsius: float = 23.0
    lid_celsius: float = 23.0
    profile_running: bool = False
    current_step: Optional[str] = None


@dataclass
class HeaterShakerState:
    latch_open: bool = True
    rpm: float = 0.0
    celsius: float = 23.0
    active: bool = False


@dataclass
class ProtocolState:
    """Full protocol state snapshot, updated by each event."""
    # Pipette
    pipette_vol: float = 0.0
    has_tip: bool = False
    has_air_gap: bool = False
    air_gap_vol: float = 0.0

    # Labware liquid volumes: slot_num -> well_name -> µL
    well_volumes: dict = field(default_factory=dict)

    # Modules
    magnetic: MagneticModuleState = field(default_factory=MagneticModuleState)
    temperature: TemperatureModuleState = field(default_factory=TemperatureModuleState)
    thermocycler: ThermocyclerState = field(default_factory=ThermocyclerState)
    heater_shaker: HeaterShakerState = field(default_factory=HeaterShakerState)

    # Protocol control
    elapsed_seconds: float = 0.0
    paused: bool = False
    step_count: int = 0

    def well_vol(self, slot: int, well: str) -> float:
        return self.well_volumes.get(slot, {}).get(well, 0.0)

    def add_to_well(self, slot: int, well: str, vol: float) -> None:
        if slot not in self.well_volumes:
            self.well_volumes[slot] = {}
        self.well_volumes[slot][well] = max(0.0, self.well_volumes[slot].get(well, 0.0) + vol)

    def apply_event(self, event: dict) -> None:
        """Update state from a single parsed run-log event."""
        etype = event.get("type")
        self.step_count += 1

        if etype == "pick":
            self.has_tip = True
            self.pipette_vol = 0.0
            self.has_air_gap = False

        elif etype == "drop":
            self.has_tip = False
            self.pipette_vol = 0.0
            self.has_air_gap = False

        elif etype == "aspirate":
            vol = float(event.get("volume", 0))
            slot = event.get("slot")
            well = event.get("well", "A1")
            self.pipette_vol += vol
            if slot:
                self.add_to_well(slot, well, -vol)

        elif etype == "dispense":
            vol = float(event.get("volume", 0))
            slot = event.get("slot")
            well = event.get("well", "A1")
            self.pipette_vol = max(0.0, self.pipette_vol - vol)
            if slot:
                self.add_to_well(slot, well, vol)
            if self.has_air_gap:
                self.has_air_gap = False

        elif etype == "mix":
            pass  # volume stays; mix is aspirate+dispense cycle in-well

        elif etype == "blow_out":
            self.pipette_vol = 0.0

        elif etype == "touch_tip":
            pass  # no volume change

        elif etype == "air_gap":
            vol = float(event.get("volume", 0))
            self.air_gap_vol = vol
            self.has_air_gap = True
            self.pipette_vol += vol

        elif etype == "delay":
            minutes = float(event.get("minutes", 0))
            seconds = float(event.get("seconds", 0))
            self.elapsed_seconds += minutes * 60 + seconds

        elif etype == "pause":
            self.paused = True

        elif etype == "resume":
            self.paused = False

        elif etype == "engage":
            self.magnetic.engaged = True
            self.magnetic.height_mm = float(event.get("height", 13.0))

        elif etype == "disengage":
            self.magnetic.engaged = False
            self.magnetic.height_mm = 0.0

        elif etype == "temp_set":
            self.temperature.active = True
            self.temperature.target_celsius = float(event.get("celsius", 23))
            self.temperature.celsius = self.temperature.target_celsius

        elif etype == "temp_deactivate":
            self.temperature.active = False
            self.temperature.celsius = 23.0
            self.temperature.target_celsius = None

        elif etype == "tc_open_lid":
            self.thermocycler.lid_open = True

        elif etype == "tc_close_lid":
            self.thermocycler.lid_open = False

        elif etype == "tc_block_temp":
            self.thermocycler.block_celsius = float(event.get("celsius", 23))

        elif etype == "tc_lid_temp":
            self.thermocycler.lid_celsius = float(event.get("celsius", 23))

        elif etype == "tc_execute_profile":
            self.thermocycler.profile_running = True
            self.thermocycler.current_step = event.get("step_label")

        elif etype == "tc_deactivate":
            self.thermocycler.profile_running = False

        elif etype == "hs_shake":
            rpm = float(event.get("rpm", 0))
            self.heater_shaker.rpm = rpm
            self.heater_shaker.active = rpm > 0

        elif etype == "hs_temp":
            self.heater_shaker.celsius = float(event.get("celsius", 23))

        elif etype == "hs_open_latch":
            self.heater_shaker.latch_open = True

        elif etype == "hs_close_latch":
            self.heater_shaker.latch_open = False

        elif etype == "hs_deactivate":
            self.heater_shaker.active = False
            self.heater_shaker.rpm = 0.0
