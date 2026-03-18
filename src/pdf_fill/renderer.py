"""Convert PDF/DOCX/image files to PIL Images (one per page)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
RENDER_DPI = 200  # Resolution for PDF/DOCX rendering


def render_file(
    file_path: str,
    dpi: int = RENDER_DPI,
    return_dimensions: bool = False,
) -> list[Image.Image] | tuple[list[Image.Image], list[tuple[float, float]]]:
    """Open a file and return a list of PIL Images (one per page).

    When *return_dimensions* is True, also return the original page dimensions
    (width, height) in PDF points (for PDFs/DOCX) or pixels (for images).
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        img = Image.open(file_path).convert("RGB")
        pages = [img]
        dims = [(float(img.width), float(img.height))]
    elif ext == ".pdf":
        pages, dims = _render_pdf(file_path, dpi)
    elif ext in (".docx", ".doc"):
        pages, dims = _render_docx(file_path, dpi)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    if return_dimensions:
        return pages, dims
    return pages


def _render_pdf(
    file_path: str, dpi: int
) -> tuple[list[Image.Image], list[tuple[float, float]]]:
    """Render each PDF page as a PIL Image and collect original dimensions."""
    doc = pymupdf.open(file_path)
    pages: list[Image.Image] = []
    dims: list[tuple[float, float]] = []
    for page in doc:
        dims.append((float(page.rect.width), float(page.rect.height)))
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages, dims


def _render_docx(
    file_path: str, dpi: int
) -> tuple[list[Image.Image], list[tuple[float, float]]]:
    """Render DOCX/DOC via PyMuPDF. For old .doc, convert to .docx first."""
    import subprocess
    import tempfile

    path = Path(file_path)

    # Old .doc format: try converting to .docx with macOS textutil or raise
    if path.suffix.lower() == ".doc":
        try:
            tmp_docx = Path(tempfile.mktemp(suffix=".docx"))
            subprocess.run(
                ["textutil", "-convert", "docx", str(path), "-output", str(tmp_docx)],
                check=True,
                capture_output=True,
            )
            file_path = str(tmp_docx)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise ValueError(
                f"Cannot open .doc file: {path.name}. "
                "Convert to .docx or .pdf first, or install LibreOffice."
            )

    doc = pymupdf.open(file_path)
    pages: list[Image.Image] = []
    dims: list[tuple[float, float]] = []
    for page in doc:
        dims.append((float(page.rect.width), float(page.rect.height)))
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages, dims


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
