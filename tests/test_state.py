import pytest
from PIL import Image
from pdf_fill.state import DocumentState


def test_create_empty_state():
    state = DocumentState()
    assert state.page_count == 0
    assert state.current_page is None


def test_load_pages():
    img = Image.new("RGB", (100, 100), "white")
    state = DocumentState()
    state.load_pages([img], source_path="test.png", source_format="png")
    assert state.page_count == 1
    assert state.current_page == 0
    assert state.get_page().size == (100, 100)


def test_undo():
    img = Image.new("RGB", (100, 100), "white")
    state = DocumentState()
    state.load_pages([img], source_path="test.png", source_format="png")
    state.save_snapshot()  # save before edit
    # Simulate an edit by replacing the page
    edited = Image.new("RGB", (100, 100), "red")
    state.set_page(edited)
    assert state.get_page().getpixel((50, 50)) == (255, 0, 0)
    state.undo()
    assert state.get_page().getpixel((50, 50)) == (255, 255, 255)


def test_undo_empty_stack():
    img = Image.new("RGB", (100, 100), "white")
    state = DocumentState()
    state.load_pages([img], source_path="test.png", source_format="png")
    assert state.undo() is False


def test_navigate_pages():
    pages = [Image.new("RGB", (100, 100), c) for c in ["white", "red", "blue"]]
    state = DocumentState()
    state.load_pages(pages, source_path="test.pdf", source_format="pdf")
    assert state.page_count == 3
    state.go_to_page(2)
    assert state.current_page == 2
    assert state.get_page().getpixel((50, 50)) == (0, 0, 255)
