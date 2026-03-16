"""Drawing operations on PIL Images."""

from __future__ import annotations

import math
from PIL import Image, ImageDraw, ImageFont
from pdf_fill.utils import parse_color


def _get_font(font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load a font at the given size. Falls back to default if no TTF available."""
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except (OSError, IOError):
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except (OSError, IOError):
            return ImageFont.load_default(size=font_size)


def draw_text_on_image(
    img: Image.Image,
    x: float,
    y: float,
    text: str,
    font_size: int = 16,
    color: str = "black",
    align: str = "left",
) -> Image.Image:
    """Draw text at (x, y) on a copy of the image."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    font = _get_font(font_size)
    draw.text((x, y), text, fill=parse_color(color)[:3], font=font, anchor=None, align=align)
    return result


def draw_shape_on_image(
    img: Image.Image,
    shape: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    outline_color: str = "black",
    fill_color: str | None = None,
    stroke_width: int = 2,
) -> Image.Image:
    """Draw a shape (rectangle, circle, line) on a copy of the image."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    outline = parse_color(outline_color)[:3]
    fill = parse_color(fill_color)[:3] if fill_color else None

    if shape == "rectangle":
        draw.rectangle([x1, y1, x2, y2], outline=outline, fill=fill, width=stroke_width)
    elif shape == "circle":
        draw.ellipse([x1, y1, x2, y2], outline=outline, fill=fill, width=stroke_width)
    elif shape == "line":
        draw.line([x1, y1, x2, y2], fill=outline, width=stroke_width)
    else:
        raise ValueError(f"Unknown shape: {shape}. Use 'rectangle', 'circle', or 'line'.")
    return result


def draw_arrow_on_image(
    img: Image.Image,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str = "black",
    width: int = 2,
    head_size: int = 12,
    label: str | None = None,
) -> Image.Image:
    """Draw an arrow from (x1,y1) to (x2,y2) with optional label."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    c = parse_color(color)[:3]

    draw.line([(x1, y1), (x2, y2)], fill=c, width=width)

    angle = math.atan2(y2 - y1, x2 - x1)
    left_x = x2 - head_size * math.cos(angle - math.pi / 6)
    left_y = y2 - head_size * math.sin(angle - math.pi / 6)
    right_x = x2 - head_size * math.cos(angle + math.pi / 6)
    right_y = y2 - head_size * math.sin(angle + math.pi / 6)
    draw.polygon([(x2, y2), (left_x, left_y), (right_x, right_y)], fill=c)

    if label:
        font = _get_font(12)
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        draw.text((mid_x, mid_y - 15), label, fill=c, font=font)

    return result


def draw_highlight_on_image(
    img: Image.Image,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str = "yellow",
    opacity: float = 0.3,
) -> Image.Image:
    """Draw a semi-transparent highlight overlay."""
    result = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rgba = parse_color(color)
    fill = (rgba[0], rgba[1], rgba[2], int(255 * opacity))
    draw.rectangle([x1, y1, x2, y2], fill=fill)
    result = Image.alpha_composite(result, overlay)
    return result.convert("RGB")


def erase_region_on_image(
    img: Image.Image,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    fill_color: str = "white",
) -> Image.Image:
    """White-out (erase) a rectangular region."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    draw.rectangle([x1, y1, x2, y2], fill=parse_color(fill_color)[:3])
    return result


def fill_checkbox_on_image(
    img: Image.Image,
    x: float,
    y: float,
    size: int = 20,
    style: str = "check",
    color: str = "black",
) -> Image.Image:
    """Fill a checkbox/bubble. Styles: 'check', 'x', 'fill'."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    c = parse_color(color)[:3]
    half = size // 2

    if style == "check":
        points = [
            (x - half + 2, y),
            (x - half + half // 2 + 2, y + half - 2),
            (x + half - 2, y - half + 2),
        ]
        draw.line(points, fill=c, width=max(2, size // 8))
    elif style == "x":
        draw.line([(x - half, y - half), (x + half, y + half)], fill=c, width=max(2, size // 8))
        draw.line([(x + half, y - half), (x - half, y + half)], fill=c, width=max(2, size // 8))
    elif style == "fill":
        draw.ellipse([x - half, y - half, x + half, y + half], fill=c)
    else:
        raise ValueError(f"Unknown checkbox style: {style}. Use 'check', 'x', or 'fill'.")
    return result


def draw_path_on_image(
    img: Image.Image,
    points: list[tuple[float, float]],
    color: str = "black",
    width: int = 2,
    closed: bool = False,
) -> Image.Image:
    """Draw a freeform path through a list of (x, y) points."""
    result = img.copy()
    draw = ImageDraw.Draw(result)
    c = parse_color(color)[:3]
    if len(points) < 2:
        return result
    coords = [(p[0], p[1]) for p in points]
    if closed:
        coords.append(coords[0])
    draw.line(coords, fill=c, width=width, joint="curve")
    return result


def color_fill_on_image(
    img: Image.Image,
    x: int,
    y: int,
    fill_color: str = "red",
    tolerance: int = 30,
) -> Image.Image:
    """Flood fill from (x, y) with the given color."""
    import cv2
    import numpy as np

    result = img.copy()
    arr = np.array(result)
    arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    fill_rgb = parse_color(fill_color)[:3]
    fill_bgr = (fill_rgb[2], fill_rgb[1], fill_rgb[0])

    mask = np.zeros((arr.shape[0] + 2, arr.shape[1] + 2), np.uint8)
    cv2.floodFill(arr_bgr, mask, (x, y), fill_bgr, (tolerance,) * 3, (tolerance,) * 3)

    arr_rgb = cv2.cvtColor(arr_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(arr_rgb)
