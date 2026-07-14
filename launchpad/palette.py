"""RGB for Launchpad Mini MK3 velocity colors (0-127).

Used only to draw swatches in the manage GUI. Exact color always comes from
the device itself (the manage app can light a pad to preview). These are the
actual palette RGBs from Novation's Launchpad Mini MK3 programmer reference,
so the on-screen swatches match the hardware instead of a saturated guess.
"""

from __future__ import annotations

# Launchpad Mini MK3 / X programmer-mode palette (index -> RGB), transcribed
# from Novation's reference. Index 0 is off; 1-127 are fixed colors.
_PALETTE: tuple[tuple[int, int, int], ...] = (
    (0, 0, 0), (28, 28, 28), (124, 124, 124), (252, 252, 252),
    (255, 77, 71), (255, 20, 0), (90, 1, 0), (25, 0, 0),
    (255, 189, 108), (255, 84, 0), (90, 29, 0), (39, 27, 0),
    (255, 255, 76), (253, 253, 0), (89, 89, 0), (25, 25, 0),
    (136, 255, 76), (84, 255, 0), (29, 89, 0), (20, 43, 0),
    (76, 255, 76), (0, 255, 0), (0, 89, 0), (0, 25, 0),
    (76, 255, 94), (0, 255, 25), (0, 89, 13), (0, 25, 2),
    (76, 255, 136), (0, 255, 85), (0, 89, 29), (0, 31, 18),
    (76, 255, 183), (0, 255, 153), (0, 89, 53), (0, 25, 18),
    (76, 195, 255), (0, 169, 255), (0, 65, 82), (0, 16, 25),
    (76, 136, 255), (0, 85, 255), (0, 29, 89), (0, 8, 25),
    (76, 76, 255), (0, 0, 255), (0, 0, 89), (0, 0, 25),
    (135, 76, 255), (84, 0, 255), (25, 0, 100), (15, 0, 48),
    (255, 76, 255), (255, 0, 255), (90, 0, 90), (25, 0, 25),
    (255, 76, 135), (255, 0, 84), (90, 1, 29), (34, 0, 19),
    (255, 21, 0), (153, 53, 0), (121, 81, 0), (67, 100, 0),
    (3, 57, 0), (0, 87, 53), (0, 84, 127), (0, 0, 255),
    (0, 69, 79), (37, 0, 204), (124, 124, 124), (32, 32, 32),
    (255, 20, 0), (189, 255, 45), (175, 237, 6), (100, 255, 9),
    (16, 139, 0), (0, 255, 135), (0, 169, 255), (0, 42, 255),
    (63, 0, 255), (122, 0, 255), (178, 26, 125), (64, 33, 0),
    (255, 74, 0), (136, 225, 6), (114, 255, 21), (0, 255, 0),
    (59, 255, 38), (89, 255, 113), (56, 255, 204), (91, 138, 255),
    (49, 81, 198), (135, 127, 233), (211, 29, 255), (255, 0, 93),
    (255, 127, 0), (185, 176, 0), (144, 255, 0), (131, 93, 7),
    (57, 43, 0), (20, 76, 16), (13, 80, 56), (21, 21, 42),
    (22, 32, 90), (105, 60, 28), (168, 0, 10), (222, 81, 61),
    (216, 106, 28), (255, 225, 38), (158, 225, 47), (103, 181, 15),
    (30, 30, 48), (220, 255, 107), (128, 255, 189), (154, 153, 255),
    (142, 102, 255), (64, 64, 64), (117, 117, 117), (224, 255, 255),
    (160, 0, 0), (53, 0, 0), (26, 208, 0), (7, 66, 0),
    (185, 176, 0), (63, 49, 0), (179, 95, 0), (75, 21, 2),
)


def rgb(velocity: int) -> tuple[int, int, int]:
    """Return the (r, g, b) 0-255 color for a Launchpad palette index."""
    v = max(0, min(127, int(velocity)))
    return _PALETTE[v]


def hex_color(velocity: int) -> str:
    r, g, b = rgb(velocity)
    return f"#{r:02x}{g:02x}{b:02x}"


def to_hex(rgb_tuple: tuple[int, int, int]) -> str:
    r, g, b = rgb_tuple
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def mix(fg: tuple[int, int, int], bg: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Blend fg toward bg by t in [0,1] (t=0 -> fg, t=1 -> bg)."""
    return tuple(int(f + (b - f) * t) for f, b in zip(fg, bg))  # type: ignore


def hex_mix(velocity: int, bg_hex: str, t: float) -> str:
    bg = tuple(int(bg_hex[i : i + 2], 16) for i in (1, 3, 5))
    return to_hex(mix(rgb(velocity), bg, t))  # type: ignore
