"""Export PIL Images to PDF or image files."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image


def export_as_pdf(pages: list[Image.Image], output_path: str) -> str:
    """Save pages as a PDF file. Returns the output path."""
    doc = pymupdf.open()
    for img in pages:
        img_bytes = _pil_to_png_bytes(img)
        w, h = img.size
        page = doc.new_page(width=w, height=h)
        page.insert_image(pymupdf.Rect(0, 0, w, h), stream=img_bytes)
    doc.save(output_path)
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
