import pytest
from PIL import Image, ImageDraw

surya_available = True
try:
    import surya  # noqa: F401
    from pdf_fill.analysis import ocr_page, analyze_layout, analyze_tables
except ImportError:
    surya_available = False


@pytest.mark.skipif(not surya_available, reason="surya-ocr not installed")
def test_ocr_page():
    img = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Hello World", fill="black")
    results = ocr_page(img)
    assert isinstance(results, list)


@pytest.mark.skipif(not surya_available, reason="surya-ocr not installed")
def test_analyze_layout():
    img = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(img)
    draw.text((50, 50), "Title", fill="black")
    draw.rectangle([50, 100, 350, 180], outline="black")
    results = analyze_layout(img)
    assert isinstance(results, list)
