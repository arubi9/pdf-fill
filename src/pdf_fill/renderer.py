"""Convert PDF/DOCX/image files to PIL Images (one per page)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
RENDER_DPI = 200  # Resolution for PDF/DOCX rendering


def render_file(file_path: str, dpi: int = RENDER_DPI) -> list[Image.Image]:
    """Open a file and return a list of PIL Images (one per page)."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        return [Image.open(file_path).convert("RGB")]
    elif ext == ".pdf":
        return _render_pdf(file_path, dpi)
    elif ext in (".docx", ".doc"):
        return _render_docx(file_path, dpi)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def _render_pdf(file_path: str, dpi: int) -> list[Image.Image]:
    """Render each PDF page as a PIL Image."""
    doc = pymupdf.open(file_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages


def _render_docx(file_path: str, dpi: int) -> list[Image.Image]:
    """Convert DOCX to PDF via PyMuPDF's built-in conversion, then render."""
    doc = pymupdf.open(file_path)
    pages = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages


def detect_format(file_path: str) -> str:
    """Detect the document format from extension."""
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext == ".pdf":
        return "pdf"
    elif ext in (".docx", ".doc"):
        return "docx"
    else:
        return "unknown"
