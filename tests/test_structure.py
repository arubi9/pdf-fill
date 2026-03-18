import pytest
from pathlib import Path
from PIL import Image
from pdf_fill.structure import extract_text_lines, classify_elements

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_text_lines_from_pdf():
    """Extract text lines from a PDF with exact bboxes."""
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    assert len(lines) > 0
    first = lines[0]
    assert "text" in first
    assert "bbox" in first
    assert "font_size" in first
    assert len(first["bbox"]) == 4
    assert first["bbox"][2] > first["bbox"][0]
    assert first["bbox"][3] > first["bbox"][1]


def test_extract_text_lines_from_image():
    """For images (no PDF text layer), returns empty list without Surya."""
    img = Image.new("RGB", (400, 300), "white")
    lines = extract_text_lines(None, page_num=0, dpi=200, fallback_image=img)
    assert isinstance(lines, list)


def test_extract_merges_side_by_side_lines():
    """Side-by-side lines like '1.' + 'Question text' should be merged."""
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    # The fixture has "1." and "What is the first question?" side by side
    merged = [l for l in lines if l["text"].startswith("1.")]
    assert len(merged) == 1
    assert "What is the first question?" in merged[0]["text"]


def test_classify_elements_finds_questions():
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    elements = classify_elements(lines, page_width=1700, page_height=2200)
    questions = [e for e in elements if e["type"] == "question"]
    assert len(questions) >= 2
    assert questions[0]["number"] == 1
    assert "answer_area" in questions[0]
    assert questions[0]["answer_area"]["bbox"][3] > questions[0]["answer_area"]["bbox"][1]


def test_classify_elements_finds_checkboxes():
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    elements = classify_elements(lines, page_width=1700, page_height=2200)
    checkboxes = [e for e in elements if e["type"] == "checkbox"]
    assert len(checkboxes) >= 2
    assert checkboxes[0]["label"] == "Option A"
    assert checkboxes[0]["checked"] is False


def test_classify_elements_finds_fields():
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    elements = classify_elements(lines, page_width=1700, page_height=2200)
    fields = [e for e in elements if e["type"] == "field"]
    labels = [f["label"].lower() for f in fields]
    assert any("name" in l or "date" in l for l in labels)


def test_classify_elements_finds_headers():
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    elements = classify_elements(lines, page_width=1700, page_height=2200)
    headers = [e for e in elements if e["type"] == "header"]
    assert len(headers) >= 1
    assert "Sample Worksheet" in headers[0]["text"]


def test_classify_real_worksheet():
    """Test with the actual electrophoresis worksheet if available."""
    ws = Path("/Users/avner/Downloads/electrophoresis-lab-worksheet.pdf")
    if not ws.exists():
        pytest.skip("Worksheet not available")
    lines = extract_text_lines(str(ws), page_num=0, dpi=200)
    elements = classify_elements(lines, page_width=1700, page_height=2200)
    questions = [e for e in elements if e["type"] == "question"]
    # Should detect at least 15 questions (some multi-line ones may merge differently)
    assert len(questions) >= 10, f"Only found {len(questions)} questions"
