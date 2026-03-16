import pytest
from PIL import Image
from pdf_fill.drawing import (
    draw_text_on_image,
    draw_shape_on_image,
    draw_arrow_on_image,
    draw_highlight_on_image,
    erase_region_on_image,
    fill_checkbox_on_image,
)


@pytest.fixture
def canvas():
    return Image.new("RGB", (400, 300), "white")


def test_draw_text(canvas):
    result = draw_text_on_image(canvas, 50, 50, "Hello", font_size=20, color="black")
    assert result.getpixel((51, 55)) != (255, 255, 255)


def test_draw_rectangle(canvas):
    result = draw_shape_on_image(canvas, "rectangle", x1=10, y1=10, x2=100, y2=80,
                                  outline_color="red", stroke_width=2)
    assert result.getpixel((10, 10)) == (255, 0, 0)


def test_draw_arrow(canvas):
    result = draw_arrow_on_image(canvas, x1=50, y1=50, x2=200, y2=150, color="blue", width=2)
    assert result.getpixel((125, 100)) != (255, 255, 255)


def test_draw_highlight(canvas):
    result = draw_highlight_on_image(canvas, x1=10, y1=10, x2=100, y2=80, color="yellow", opacity=0.3)
    pixel = result.getpixel((50, 40))
    assert pixel[0] > 200
    assert pixel[1] > 200
    assert pixel[2] < pixel[0]


def test_erase_region(canvas):
    result = draw_text_on_image(canvas, 50, 50, "Erase me", font_size=20, color="black")
    result = erase_region_on_image(result, x1=40, y1=40, x2=200, y2=80)
    assert result.getpixel((50, 55)) == (255, 255, 255)


def test_fill_checkbox(canvas):
    result = fill_checkbox_on_image(canvas, x=50, y=50, size=20, style="check", color="black")
    assert result.getpixel((53, 48)) != (255, 255, 255)
