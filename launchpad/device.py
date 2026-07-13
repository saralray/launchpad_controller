"""Launchpad Mini MK3 device control (SysEx).

Programmer ('User') layout makes the whole surface use the documented note/CC
numbering — main grid 11-88, top row 91-99, right scene column 19-89 — which
is exactly what the app's grid geometry (`manage.cell_for_number`) assumes.
Selecting it on connect keeps the physical device and the app in agreement.
"""

from __future__ import annotations

# Novation (00 20 29) · Launchpad Mini MK3 (02 0D) · layout/mode select (0E)
_LAYOUT_SELECT = [0x00, 0x20, 0x29, 0x02, 0x0D, 0x0E]
PROGRAMMER = 0x01
LIVE = 0x00


def layout_sysex(programmer: bool = True) -> list[int]:
    """SysEx payload (without the F0/F7 wrapper) selecting the layout.

    programmer=True -> 'User'/Programmer layout; False -> Live/Session.
    Pass to mido as: mido.Message("sysex", data=layout_sysex(...)).
    """
    return _LAYOUT_SELECT + [PROGRAMMER if programmer else LIVE]
