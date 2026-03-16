"""Shared utilities for color parsing and coordinate math."""

from __future__ import annotations

from PIL import ImageColor


def parse_color(color: str) -> tuple[int, int, int, int]:
    """Parse a color string to RGBA tuple. Supports names ('red'), hex ('#ff0000'), rgba."""
    if color.startswith("rgba("):
        parts = color[5:-1].split(",")
        return (int(parts[0]), int(parts[1]), int(parts[2]), int(float(parts[3]) * 255))
    try:
        rgb = ImageColor.getrgb(color)
        if len(rgb) == 3:
            return (*rgb, 255)
        return rgb
    except ValueError:
        return (0, 0, 0, 255)


def clamp_bbox(
    bbox: tuple[float, float, float, float], width: int, height: int
) -> tuple[int, int, int, int]:
    """Clamp bounding box to image dimensions."""
    x1 = max(0, min(int(bbox[0]), width))
    y1 = max(0, min(int(bbox[1]), height))
    x2 = max(0, min(int(bbox[2]), width))
    y2 = max(0, min(int(bbox[3]), height))
    return (x1, y1, x2, y2)
