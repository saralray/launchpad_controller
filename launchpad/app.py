"""Controller: owns runtime state and the MIDI event loop.

Wires together the config model, HAClient, MidiSurface, and preset dispatch.
Preserves the daemon's core behaviors: passive-mode safety, USB hot-plug
resilience (no exception escapes the loop), optimistic LED updates, and
rate-limited pad repaints.
"""

from __future__ import annotations

import importlib
import signal
import sys
import time
from pathlib import Path

from . import device
from .config import Config, Room, load_config
from .ha_client import HAClient
from .midi import MidiSurface
from .presets_api import PresetHA
from .settings import get_credentials

# entity states that count as "lit" for LED purposes
ON_STATES = ("on", "cool")

# minimum seconds between full pad repaints (~12.5 Hz)
PAD_REFRESH_INTERVAL = 0.08

# layout the Launchpad jumps to on (re)connect. CUSTOM_3 = the device's
# "User"-labelled tab (factory default); use device.PROGRAMMER_LAYOUT for the
# full-surface documented numbering.
STARTUP_LAYOUT = device.CUSTOM_3

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"


class Controller:
    def __init__(self, config: Config, ha: HAClient, midi: MidiSurface):
        self.config = config
        self.ha = ha
        self.midi = midi
        self.active_room: Room = self._initial_room()
        self.preset_ha = PresetHA(ha)
        self._last_update = 0.0

    def _initial_room(self) -> Room:
        """Start on the Presets room if the config has one, else the first."""
        for room in self.config.rooms:
            if "preset" in (room.name or "").lower():
                return room
        return self.config.rooms[0]

    # ---- LED painting --------------------------------------------------

    def _entity_on(self, entity_id: str) -> bool:
        return self.ha.state(entity_id) in ON_STATES

    def update_pads(self) -> None:
        if time.time() - self._last_update < PAD_REFRESH_INTERVAL:
            return
        self._last_update = time.time()

        # top-row room selectors: lit if any entity in the room is on
        for room in self.config.rooms:
            any_on = any(
                a.entity_ids
                and any(self._entity_on(e) for e in a.entity_ids)
                for a in room.actions
            )
            self.midi.set_pad(
                room.room_key,
                room.room_key_color_any_on if any_on else room.room_key_color_off,
                True,
            )

        # active room grid
        for act in self.active_room.actions:
            if act.entity_ids is None:
                self.midi.set_pad(act.key, act.on_color, False)
            else:
                on = any(self._entity_on(e) for e in act.entity_ids)
                self.midi.set_pad(
                    act.key, act.on_color if on else act.off_color, False
                )

    # ---- preset dispatch ----------------------------------------------

    def run_preset(self, name: str) -> None:
        try:
            importlib.import_module(f"presets.{name}").run(self.preset_ha)
        except Exception as e:
            print(f"❌ Preset error [{name}]: {e}")

    # ---- input handling ------------------------------------------------

    def _handle_message(self, msg) -> None:
        if msg.type == "control_change":
            for room in self.config.rooms:
                if room.room_key == msg.control:
                    self.active_room = room
                    self.update_pads()
            return

        if msg.type == "note_on" and msg.velocity > 0:
            for act in self.active_room.actions:
                if msg.note != act.key:
                    continue

                if act.is_preset:
                    self.run_preset(act.preset)
                    self.update_pads()
                    return

                self._toggle(act.entity_ids)
                self.update_pads()
                return

    def _toggle(self, entity_ids: list[str]) -> None:
        turning_on = not any(self._entity_on(e) for e in entity_ids)
        state = "on" if turning_on else "off"
        svc = "turn_on" if turning_on else "turn_off"
        for e in entity_ids:
            self.ha.set_local(e, state)
            self.ha.call(e.split(".")[0], svc, {"entity_id": e})

    # ---- main loop -----------------------------------------------------

    def run(self) -> None:
        self.midi.open()
        self.ha.refresh_states(force=True)
        self.ha.start_ws(self.update_pads)

        print("🚀 FAST Controller Started")
        self.update_pads()

        while True:
            if not self.midi.still_present():
                self.midi.open()
                self.update_pads()

            for msg in self.midi.iter_pending():
                self._handle_message(msg)

            time.sleep(0.01)


def main() -> None:
    url, token = get_credentials()
    ha = HAClient(url, token)
    midi = MidiSurface()
    midi.startup_layout = STARTUP_LAYOUT
    controller = Controller(load_config(CONFIG_PATH), ha, midi)

    def shutdown(sig, frame):
        print("🛑 Shutting down...")
        midi.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    controller.run()
