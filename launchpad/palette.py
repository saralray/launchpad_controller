"""Approximate RGB for Launchpad Mini MK3 velocity colors (0-127).

Used only to draw swatches in the manage GUI. Exact color always comes from
the device itself (the manage app can light a pad to preview). The ramp here
is a coarse approximation good enough for visual editing, with a few
hand-tuned entries for the indices the shipped config.json uses.
"""

from __future__ import annotations

# hand-tuned entries for common indices seen in config.json
_KNOWN: dict[int, tuple[int, int, int]] = {
    0: (20, 20, 20),     # off
    1: (60, 60, 60),     # dim white/grey
    5: (200, 200, 200),  # white
    9: (255, 170, 0),    # amber
    13: (255, 255, 0),   # yellow
    21: (0, 220, 0),     # green
    33: (0, 180, 255),   # cyan/blue
    54: (150, 0, 255),   # violet
}


def rgb(velocity: int) -> tuple[int, int, int]:
    """Return an (r, g, b) 0-255 approximation for a Launchpad color index."""
    v = max(0, min(127, int(velocity)))
    if v in _KNOWN:
        return _KNOWN[v]
    if v == 0:
        return (20, 20, 20)
    # coarse hue ramp across the palette so distinct indices look distinct
    import colorsys

    hue = (v * 0.021) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
    return (int(r * 255), int(g * 255), int(b * 255))


def hex_color(velocity: int) -> str:
    r, g, b = rgb(velocity)
    return f"#{r:02x}{g:02x}{b:02x}"
