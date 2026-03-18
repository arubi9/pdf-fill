import pytest
import pymupdf
from PIL import Image
from pdf_fill.export import export_as_pdf
from pdf_fill.drawing import draw_text_on_image

def test_export_preserves_original_page_dimensions(tmp_path):
    img = Image.new("RGB", (1700, 2200), "white")
    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out), page_dimensions=[(612.0, 792.0)])
    doc = pymupdf.open(str(out))
    page = doc[0]
    assert page.rect.width == pytest.approx(612.0, abs=1)
    assert page.rect.height == pytest.approx(792.0, abs=1)
    doc.close()

def test_export_roundtrip_preserves_content(tmp_path):
    img = Image.new("RGB", (1700, 2200), "white")
    for y in [280, 588, 945, 1095, 1496]:
        img = draw_text_on_image(img, 140, y, f"Answer at y={y}", font_size=16, color="blue")
    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out), page_dimensions=[(612.0, 792.0)])
    doc = pymupdf.open(str(out))
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    result = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()
    scale = result.size[1] / 2200
    for y in [280, 588, 945, 1095, 1496]:
        scaled_y = int(y * scale)
        # Check a band of rows around the expected position to account for
        # rounding and font baseline offsets after PDF re-rasterisation.
        has_non_white = any(
            result.getpixel((x, row)) != (255, 255, 255)
            for row in range(max(0, scaled_y - 5), min(result.size[1], scaled_y + 20))
            for x in range(130, 500)
        )
        assert has_non_white, f"Text at y={y} lost in roundtrip"

def test_export_fallback_to_pixel_dimensions(tmp_path):
    img = Image.new("RGB", (800, 600), "white")
    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out))
    doc = pymupdf.open(str(out))
    page = doc[0]
    assert page.rect.width == pytest.approx(800.0, abs=1)
    assert page.rect.height == pytest.approx(600.0, abs=1)
    doc.close()
