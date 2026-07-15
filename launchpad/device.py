"""Launchpad Mini MK3 device control (SysEx).

Programmer ('User') layout makes the whole surface use the documented note/CC
numbering — main grid 11-88, top row 91-99, right scene column 19-89 — which
is exactly what the app's default grid geometry (`layout.default_key_for_cell`)
assumes. Selecting it on connect keeps the physical device and the app in
agreement — or run the manage GUI's "Map layout" wizard to record the real
numbers a differently-configured unit emits.
"""

from __future__ import annotations

# Novation (00 20 29) · Launchpad Mini MK3 (02 0D) · programmer/live toggle (0E)
_LAYOUT_SELECT = [0x00, 0x20, 0x29, 0x02, 0x0D, 0x0E]
PROGRAMMER = 0x01
LIVE = 0x00

# Select-layout command (00): pick which page the surface shows. Values per the
# Mini MK3 programmer's reference. Custom modes expose only the 8x8 grid; the
# top CC row and scene column go dark. Programmer (0x7F) is the only full-surface
# layout. Session/DAW-faders are selectable only while the unit is in DAW mode.
_SELECT_LAYOUT = [0x00, 0x20, 0x29, 0x02, 0x0D, 0x00]
CUSTOM_1 = 0x04  # first custom tab (Drum Rack by factory default)
CUSTOM_2 = 0x05  # Keys by factory default
CUSTOM_3 = 0x06  # the device's "User"-labelled button by factory default
PROGRAMMER_LAYOUT = 0x7F


def pick_launchpad_port(names: list[str]) -> str | None:
    """Return the first Launchpad port from a list of port names.

    The whole app works off the device's *real* emitted numbers (no forced
    layout), so it simply uses the first port the OS exposes for the
    Launchpad — the same port keychecker reads — and the calibration wizard
    records whatever that port sends. In/out use this same rule so LED
    output and button input stay on one port.
    """
    return next((p for p in names if "launchpad" in p.lower()), None)


def layout_sysex(programmer: bool = True) -> list[int]:
    """SysEx payload (without the F0/F7 wrapper) selecting the layout.

    programmer=True -> 'User'/Programmer layout; False -> Live/Session.
    Pass to mido as: mido.Message("sysex", data=layout_sysex(...)).
    """
    return _LAYOUT_SELECT + [PROGRAMMER if programmer else LIVE]


def select_layout_sysex(layout: int) -> list[int]:
    """SysEx payload (without F0/F7) selecting a surface layout.

    Pass one of CUSTOM_1/CUSTOM_2/CUSTOM_3/PROGRAMMER_LAYOUT. Send via mido as:
    mido.Message("sysex", data=select_layout_sysex(...)).
    """
    return _SELECT_LAYOUT + [layout]
