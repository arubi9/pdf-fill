import pytest
from pathlib import Path
from PIL import Image
from pdf_fill.export import export_as_pdf, export_as_image


def test_export_single_page_pdf(tmp_path):
    img = Image.new("RGB", (612, 792), "white")
    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out))
    assert out.exists()
    assert out.stat().st_size > 0


def test_export_multi_page_pdf(tmp_path):
    pages = [Image.new("RGB", (612, 792), c) for c in ["white", "red"]]
    out = tmp_path / "out.pdf"
    export_as_pdf(pages, str(out))
    assert out.exists()
    import pymupdf
    doc = pymupdf.open(str(out))
    assert len(doc) == 2
    doc.close()


def test_export_as_png(tmp_path):
    img = Image.new("RGB", (400, 300), "blue")
    out = tmp_path / "out.png"
    export_as_image([img], str(out))
    assert out.exists()
    loaded = Image.open(out)
    assert loaded.size == (400, 300)


def test_export_multi_page_as_images(tmp_path):
    pages = [Image.new("RGB", (400, 300), c) for c in ["white", "red", "blue"]]
    out = tmp_path / "out.png"
    export_as_image(pages, str(out))
    assert (tmp_path / "out_0.png").exists()
    assert (tmp_path / "out_1.png").exists()
    assert (tmp_path / "out_2.png").exists()
