"""Grid geometry for the Launchpad Mini MK3.

Maps note/CC numbers to (row, col) cells using the documented X-Y layout,
with an optional per-unit calibration overlay recorded by the manage GUI's
"Map layout" wizard (persisted to layout.json).

NOTE: this file is a local reconstruction to make the package importable for
development/testing. It matches the API manage.py relies on.
"""

from __future__ import annotations

import json
from pathlib import Path

GRID = 9
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAYOUT_PATH = PROJECT_ROOT / "layout.json"


def _formula_cell(number: int, is_cc: bool):
    n = int(number)
    if is_cc:
        if 91 <= n <= 99:
            return (0, n - 91)
        return None
    tens, ones = divmod(n, 10)
    if 1 <= tens <= 8 and 1 <= ones <= 8:
        return (9 - tens, ones - 1)
    if 1 <= tens <= 8 and ones == 9:
        return (9 - tens, 8)
    return None


def _formula_number(r: int, c: int):
    if r == 0:
        return (91 + c, True)
    if c == 8:
        return ((9 - r) * 10 + 9, False)
    return ((9 - r) * 10 + (c + 1), False)


class Layout:
    def __init__(self, cells: dict | None = None):
        # {(r, c): (is_cc, number)} calibration overlay
        self._cells: dict[tuple[int, int], tuple[bool, int]] = dict(cells or {})

    def as_dict(self) -> dict[tuple[int, int], tuple[bool, int]]:
        return dict(self._cells)

    def set_cell(self, r: int, c: int, number: int, is_cc: bool) -> None:
        self._cells[(r, c)] = (bool(is_cc), int(number))

    def cell_for_number(self, number: int, is_cc: bool = False):
        for (r, c), (cc, num) in self._cells.items():
            if num == int(number) and bool(cc) == bool(is_cc):
                return (r, c)
        return _formula_cell(number, is_cc)

    def number_for_cell(self, r: int, c: int):
        if (r, c) in self._cells:
            return self._cells[(r, c)][1]
        res = _formula_number(r, c)
        return res[0] if res else None


def load_layout() -> Layout:
    try:
        raw = json.loads(LAYOUT_PATH.read_text())
        cells = {}
        for k, v in raw.items():
            r, c = (int(x) for x in k.split(","))
            cells[(r, c)] = (bool(v[0]), int(v[1]))
        return Layout(cells)
    except Exception:
        return Layout()


def save_layout(layout: Layout) -> None:
    raw = {f"{r},{c}": [cc, num] for (r, c), (cc, num) in layout.as_dict().items()}
    LAYOUT_PATH.write_text(json.dumps(raw, indent=2))
