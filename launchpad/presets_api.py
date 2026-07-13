"""Façade handed to preset modules' `run(ha)` entry point.

Presets talk only to this object — never to HAClient or the state cache
directly. Turning a light on/off optimistically updates the local cache
(for instant LED feedback) and fires the Home Assistant service call.
"""

from __future__ import annotations

from .ha_client import HAClient


class PresetHA:
    def __init__(self, ha: HAClient):
        self._ha = ha

    def all_lights(self) -> list[str]:
        return [e for e in self._ha.states if e.startswith("light.")]

    def is_on(self, entity_id: str) -> bool:
        return self._ha.state(entity_id) == "on"

    def turn_on(self, entity_id: str, **data) -> None:
        self._ha.set_local(entity_id, "on")
        self._ha.call("light", "turn_on", {"entity_id": entity_id, **data})

    def turn_off(self, entity_id: str) -> None:
        self._ha.set_local(entity_id, "off")
        self._ha.call("light", "turn_off", {"entity_id": entity_id})
