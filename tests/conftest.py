import pytest
from PIL import Image


@pytest.fixture
def blank_image():
    """100x100 white image."""
    return Image.new("RGB", (100, 100), "white")


@pytest.fixture
def blank_image_large():
    """800x600 white image."""
    return Image.new("RGB", (800, 600), "white")
