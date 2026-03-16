import pytest
from pathlib import Path
from PIL import Image
from pdf_fill.renderer import render_file

FIXTURES = Path(__file__).parent / "fixtures"


def test_render_png(tmp_path):
    img = Image.new("RGB", (200, 150), "blue")
    path = tmp_path / "test.png"
    img.save(path)
    pages = render_file(str(path))
    assert len(pages) == 1
    assert pages[0].size == (200, 150)


def test_render_jpg(tmp_path):
    img = Image.new("RGB", (200, 150), "green")
    path = tmp_path / "test.jpg"
    img.save(path)
    pages = render_file(str(path))
    assert len(pages) == 1


def test_render_pdf(tmp_path):
    """Create a simple 1-page PDF and render it."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hello PDF")
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()
    pages = render_file(str(pdf_path))
    assert len(pages) == 1
    assert pages[0].size[0] > 0


def test_render_unsupported(tmp_path):
    path = tmp_path / "test.xyz"
    path.write_text("not a doc")
    with pytest.raises(ValueError, match="Unsupported"):
        render_file(str(path))
