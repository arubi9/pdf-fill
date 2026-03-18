"""Export PIL Images to PDF or image files."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image


def export_as_pdf(
    pages: list[Image.Image],
    output_path: str,
    page_dimensions: list[tuple[float, float]] | None = None,
) -> str:
    """Save pages as a PDF file. Returns the output path.

    Args:
        pages: List of PIL images to include as PDF pages.
        output_path: Destination file path for the PDF.
        page_dimensions: Optional list of (width, height) tuples in PDF points
            (72 per inch) for each page.  When provided, the PDF page is created
            at the given point size and the image is scaled to fit.  When *None*,
            the pixel dimensions of each image are used (backward compatible).
    """
    doc = pymupdf.open()
    for i, img in enumerate(pages):
        img_bytes = _pil_to_png_bytes(img)
        if page_dimensions is not None and i < len(page_dimensions):
            pw, ph = page_dimensions[i]
        else:
            pw, ph = float(img.size[0]), float(img.size[1])
        page = doc.new_page(width=pw, height=ph)
        page.insert_image(pymupdf.Rect(0, 0, pw, ph), stream=img_bytes)
    doc.save(output_path, deflate=True, deflate_images=True)
    doc.close()
    return output_path


def export_as_image(pages: list[Image.Image], output_path: str) -> str:
    """Save pages as image files. Multi-page creates numbered files."""
    path = Path(output_path)
    if len(pages) == 1:
        pages[0].save(output_path)
        return output_path

    stem = path.stem
    suffix = path.suffix or ".png"
    parent = path.parent
    paths = []
    for i, img in enumerate(pages):
        p = parent / f"{stem}_{i}{suffix}"
        img.save(str(p))
        paths.append(str(p))
    return ", ".join(paths)


def _pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
