"""Typed config model loaded from config.json.

An Action is either an *entity* action (`entity_ids` set — toggles Home
Assistant entities) or a *preset* action (`preset` set — dispatches to a
`presets/<name>.py` module). `service_data` is preserved from JSON but the
runtime does not currently apply it (matches historical behavior).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Action:
    key: int  # note_on number of the grid button
    on_color: int
    off_color: int
    entity_ids: list[str] | None = None
    preset: str | None = None
    service_data: dict | None = None

    @property
    def is_preset(self) -> bool:
        return self.preset is not None

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(
            key=d["key"],
            on_color=d.get("on_color", 21),
            off_color=d.get("off_color", 5),
            entity_ids=d.get("entity_ids"),
            preset=d.get("preset"),
            service_data=d.get("service_data"),
        )

    def to_dict(self) -> dict:
        d: dict = {"key": self.key}
        if self.entity_ids is not None:
            d["entity_ids"] = self.entity_ids
        if self.preset is not None:
            d["preset"] = self.preset
        if self.service_data is not None:
            d["service_data"] = self.service_data
        d["on_color"] = self.on_color
        d["off_color"] = self.off_color
        return d


@dataclass
class Room:
    name: str
    room_key: int  # control_change number of the top-row selector button
    actions: list[Action] = field(default_factory=list)
    room_key_color_any_on: int = 9
    room_key_color_off: int = 5
    room_key_color_on: int = 21  # present in JSON; not used by pad logic

    @classmethod
    def from_dict(cls, d: dict) -> "Room":
        return cls(
            name=d["name"],
            room_key=d["room_key"],
            actions=[Action.from_dict(a) for a in d.get("actions", [])],
            room_key_color_any_on=d.get("room_key_color_any_on", 9),
            room_key_color_off=d.get("room_key_color_off", 5),
            room_key_color_on=d.get("room_key_color_on", 21),
        )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "room_key": self.room_key,
            "room_key_color_on": self.room_key_color_on,
            "room_key_color_any_on": self.room_key_color_any_on,
            "room_key_color_off": self.room_key_color_off,
            "actions": [a.to_dict() for a in self.actions],
        }


@dataclass
class Config:
    rooms: list[Room]

    def to_dict(self) -> dict:
        return {"rooms": [r.to_dict() for r in self.rooms]}


def default_config() -> Config:
    return Config(
        rooms=[
            Room(
                name="Default Room",
                room_key=89,
                room_key_color_on=21,
                room_key_color_any_on=9,
                room_key_color_off=5,
                actions=[],
            )
        ]
    )


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        cfg = default_config()
        try:
            save_config(cfg, path)
        except Exception:
            pass
        return cfg
    try:
        with open(path) as f:
            data = json.load(f)
        rooms = [Room.from_dict(r) for r in data.get("rooms", [])]
        if not rooms:
            return default_config()
        return Config(rooms=rooms)
    except Exception:
        cfg = default_config()
        try:
            save_config(cfg, path)
        except Exception:
            pass
        return cfg


def save_config(config: Config, path: str | Path) -> None:
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=2)
        f.write("\n")

