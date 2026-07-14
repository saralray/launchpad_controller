"""Grid layout map: which button sits at which (row, col) position.

A "button" is identified by its MIDI *event*, not just a number: the same
numeric value can arrive as both a note_on and a control_change from two
different physical buttons (e.g. a scene-column button vs a main pad on
some layouts). So the map is keyed on `(is_cc, number)`, never number
alone.

The Mini MK3 *should* follow the documented X-Y layout (see `default_*`
below), but the actual events a unit emits depend on its layout mode
(Live vs Programmer) and firmware. Rather than trust the formula, the
manage GUI can run a calibration wizard: press each physical button, its
event is recorded against its grid position, and the result is persisted
to layout.json next to config.json.

Storage format (layout.json):
    {"cells": {"1,0": {"n": 81, "cc": false}, ...}}   # "row,col" -> event

Learned cells override the formula; cells left uncalibrated fall back to
it, so a partial map (e.g. only the 8x8 grid, leaving the top bar alone)
still places everything. An empty `Layout` is pure formula, so the app
works out of the box without any calibration.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAYOUT_PATH = PROJECT_ROOT / "layout.json"

GRID = 9

# an event is (is_cc, number): control_change vs note_on, plus the number
Event = tuple[bool, int]


def default_key_for_cell(r: int, c: int) -> Event | None:
    """Documented Mini MK3 X-Y layout: the (is_cc, number) at a cell.

    Top row = CC 91-99. Main 8x8 + right scene column = note_on
    (11-88 tens=row-from-bottom/ones=column; scene column ones=9, 19..89).
    """
    if r == 0 and 0 <= c <= 8:
        return (True, 91 + c)  # top CC row
    if 1 <= r <= 8 and c == 8:
        return (False, (9 - r) * 10 + 9)  # right scene column (note)
    if 1 <= r <= 8 and 0 <= c <= 7:
        return (False, (9 - r) * 10 + (c + 1))  # main grid (note)
    return None


def default_cell_for_key(is_cc: bool, number: int) -> tuple[int, int] | None:
    for r in range(GRID):
        for c in range(GRID):
            if default_key_for_cell(r, c) == (is_cc, number):
                return (r, c)
    return None


class Layout:
    """Bidirectional position<->event map with a formula fallback."""

    def __init__(self, cells: dict[tuple[int, int], Event] | None = None):
        self._cell_to_key: dict[tuple[int, int], Event] = dict(cells or {})
        self._key_to_cell: dict[Event, tuple[int, int]] = {
            k: rc for rc, k in self._cell_to_key.items()
        }

    @property
    def calibrated(self) -> bool:
        return bool(self._cell_to_key)

    def cell_for_number(self, number: int, is_cc: bool = False) -> tuple[int, int] | None:
        key = (is_cc, number)
        if key in self._key_to_cell:
            return self._key_to_cell[key]
        cell = default_cell_for_key(is_cc, number)
        if cell in self._cell_to_key:  # position was reassigned by calibration
            return None
        return cell

    def number_for_cell(self, r: int, c: int) -> int | None:
        if (r, c) in self._cell_to_key:
            return self._cell_to_key[(r, c)][1]
        key = default_key_for_cell(r, c)
        if key is None or key in self._key_to_cell:  # learned elsewhere
            return None
        return key[1]

    def key_for_cell(self, r: int, c: int) -> Event | None:
        if (r, c) in self._cell_to_key:
            return self._cell_to_key[(r, c)]
        return default_key_for_cell(r, c)

    def set_cell(self, r: int, c: int, number: int, is_cc: bool) -> None:
        # an event lives in exactly one position; drop any stale mapping
        key = (is_cc, number)
        old_cell = self._key_to_cell.pop(key, None)
        if old_cell is not None:
            self._cell_to_key.pop(old_cell, None)
        old_key = self._cell_to_key.get((r, c))
        if old_key is not None:
            self._key_to_cell.pop(old_key, None)
        self._cell_to_key[(r, c)] = key
        self._key_to_cell[key] = (r, c)

    def as_dict(self) -> dict[tuple[int, int], Event]:
        return dict(self._cell_to_key)


def load_layout(path: Path = LAYOUT_PATH) -> Layout:
    try:
        with open(path) as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return Layout()
    cells: dict[tuple[int, int], Event] = {}
    for key, val in (raw.get("cells") or {}).items():
        try:
            r, c = (int(x) for x in key.split(","))
            if isinstance(val, dict):  # current format
                cells[(r, c)] = (bool(val.get("cc", False)), int(val["n"]))
            else:  # legacy: bare number meant note_on
                cells[(r, c)] = (False, int(val))
        except (ValueError, TypeError, KeyError):
            continue
    return Layout(cells)


def save_layout(layout: Layout, path: Path = LAYOUT_PATH) -> None:
    cells = {
        f"{r},{c}": {"n": num, "cc": is_cc}
        for (r, c), (is_cc, num) in layout.as_dict().items()
    }
    with open(path, "w") as f:
        json.dump({"cells": cells}, f, indent=2)
        f.write("\n")
