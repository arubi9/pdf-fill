# Document Intelligence & QOL Improvements Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add document structure detection, smart coordinate mapping, and export quality fixes so Claude can fill PDFs with pinpoint accuracy — understanding what each element is (question, answer area, checkbox, table, field) and where exactly to place content.

**Architecture:** Hybrid text extraction — PyMuPDF for digital PDFs (exact character bboxes from the PDF text layer), Surya OCR fallback for scanned documents. A new `structure.py` module classifies extracted text into semantic elements (questions, fields, checkboxes, headers, tables) and computes answer areas from whitespace gaps. The `state.py` stores original PDF page dimensions so exports preserve quality. Coordinate system uses pixel coordinates at render DPI (200) throughout.

**Tech Stack:** Python 3.11+, PyMuPDF (text extraction + drawings + images), Pillow, existing MCP server infrastructure

---

## File Structure

```
src/pdf_fill/
├── server.py               # Modified: new tools (get_page_structure, render_page_annotated, measure_text)
├── state.py                # Modified: store original PDF page dimensions + structure cache
├── structure.py            # NEW: text extraction, element classification, answer area detection
├── renderer.py             # Modified: store page dimensions during render
├── export.py               # Modified: smart page dimensions on PDF export
├── drawing.py              # Modified: add measure_text_bbox helper
├── analysis.py             # Unchanged (Surya fallback)
├── utils.py                # Unchanged
└── __init__.py             # Unchanged
tests/
├── test_structure.py       # NEW: structure detection tests
├── test_export_quality.py  # NEW: export roundtrip quality tests
├── test_state.py           # Modified: test new page_dimensions field
├── conftest.py             # Modified: add PDF fixture helpers
└── fixtures/
    └── sample.pdf          # NEW: test PDF with questions, checkboxes, tables
```

---

## Chunk 1: State & Renderer — Store Original Page Dimensions

### Task 1: Extend DocumentState to Store Page Dimensions

**Files:**
- Modify: `src/pdf_fill/state.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Write failing test for page_dimensions**

```python
# tests/test_state.py — append these tests

def test_page_dimensions_stored():
    img = Image.new("RGB", (1700, 2200), "white")
    state = DocumentState()
    state.load_pages(
        [img],
        source_path="test.pdf",
        source_format="pdf",
        page_dimensions=[(612.0, 792.0)],
    )
    assert state.page_dimensions == [(612.0, 792.0)]


def test_page_dimensions_default_to_pixel_size():
    img = Image.new("RGB", (800, 600), "white")
    state = DocumentState()
    state.load_pages([img], source_path="test.png", source_format="image")
    assert state.page_dimensions == [(800.0, 600.0)]


def test_render_dpi_stored():
    img = Image.new("RGB", (1700, 2200), "white")
    state = DocumentState()
    state.load_pages(
        [img],
        source_path="test.pdf",
        source_format="pdf",
        render_dpi=200,
    )
    assert state.render_dpi == 200


def test_structure_cache():
    img = Image.new("RGB", (100, 100), "white")
    state = DocumentState()
    state.load_pages([img], source_path="test.png", source_format="image")
    assert state.get_structure(0) is None
    state.set_structure(0, {"elements": []})
    assert state.get_structure(0) == {"elements": []}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_state.py -v -k "dimensions or render_dpi or structure_cache"
```
Expected: FAIL — `load_pages` doesn't accept `page_dimensions`.

- [ ] **Step 3: Implement DocumentState changes**

```python
# src/pdf_fill/state.py — updated class
"""Document state management: pages, undo stack, metadata."""

from __future__ import annotations

from PIL import Image


class DocumentState:
    """Holds the working state of an open document."""

    def __init__(self) -> None:
        self._pages: list[Image.Image] = []
        self._undo_stacks: list[list[Image.Image]] = []
        self._current_page: int | None = None
        self.source_path: str | None = None
        self.source_format: str | None = None
        self.page_dimensions: list[tuple[float, float]] = []
        self.render_dpi: int = 200
        self._structure_cache: dict[int, dict | None] = {}

    @property
    def page_count(self) -> int:
        return len(self._pages)

    @property
    def current_page(self) -> int | None:
        return self._current_page

    def load_pages(
        self,
        pages: list[Image.Image],
        source_path: str,
        source_format: str,
        page_dimensions: list[tuple[float, float]] | None = None,
        render_dpi: int = 200,
    ) -> None:
        """Load pages into state."""
        self._pages = [p.copy() for p in pages]
        self._undo_stacks = [[] for _ in pages]
        self._current_page = 0 if pages else None
        self.source_path = source_path
        self.source_format = source_format
        self.render_dpi = render_dpi
        if page_dimensions:
            self.page_dimensions = list(page_dimensions)
        else:
            self.page_dimensions = [(float(p.size[0]), float(p.size[1])) for p in pages]
        self._structure_cache = {}

    def get_page(self, page_num: int | None = None) -> Image.Image:
        idx = page_num if page_num is not None else self._current_page
        if idx is None or idx < 0 or idx >= len(self._pages):
            raise IndexError(f"Invalid page number: {idx}")
        return self._pages[idx]

    def set_page(self, img: Image.Image, page_num: int | None = None) -> None:
        idx = page_num if page_num is not None else self._current_page
        if idx is None or idx < 0 or idx >= len(self._pages):
            raise IndexError(f"Invalid page number: {idx}")
        self._pages[idx] = img
        # Invalidate structure cache when page is edited
        self._structure_cache.pop(idx, None)

    def save_snapshot(self, page_num: int | None = None) -> None:
        idx = page_num if page_num is not None else self._current_page
        if idx is None:
            return
        self._undo_stacks[idx].append(self._pages[idx].copy())

    def undo(self, page_num: int | None = None) -> bool:
        idx = page_num if page_num is not None else self._current_page
        if idx is None or not self._undo_stacks[idx]:
            return False
        self._pages[idx] = self._undo_stacks[idx].pop()
        self._structure_cache.pop(idx, None)
        return True

    def go_to_page(self, page_num: int) -> None:
        if page_num < 0 or page_num >= len(self._pages):
            raise IndexError(f"Invalid page number: {page_num}")
        self._current_page = page_num

    def get_all_pages(self) -> list[Image.Image]:
        return list(self._pages)

    def get_structure(self, page_num: int) -> dict | None:
        return self._structure_cache.get(page_num)

    def set_structure(self, page_num: int, structure: dict) -> None:
        self._structure_cache[page_num] = structure
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_state.py -v
```
Expected: all tests PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/pdf_fill/state.py tests/test_state.py
git commit -m "feat: store page dimensions, render DPI, and structure cache in state"
```

---

### Task 2: Update Renderer to Extract Page Dimensions

**Files:**
- Modify: `src/pdf_fill/renderer.py`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_renderer.py — append

def test_render_pdf_returns_dimensions(tmp_path):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hello PDF")
    pdf_path = tmp_path / "test.pdf"
    doc.save(str(pdf_path))
    doc.close()
    pages, dims = render_file(str(pdf_path), return_dimensions=True)
    assert len(pages) == 1
    assert dims[0] == (612.0, 792.0)


def test_render_image_returns_pixel_dimensions(tmp_path):
    from PIL import Image
    img = Image.new("RGB", (400, 300), "blue")
    path = tmp_path / "test.png"
    img.save(path)
    pages, dims = render_file(str(path), return_dimensions=True)
    assert dims[0] == (400.0, 300.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_renderer.py -v -k "dimensions"
```

- [ ] **Step 3: Implement renderer changes**

Update `render_file` to accept `return_dimensions=True`. When True, return a tuple of `(pages, dimensions)`. When False (default), return just pages for backward compatibility.

```python
# src/pdf_fill/renderer.py
"""Convert PDF/DOCX/image files to PIL Images (one per page)."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
RENDER_DPI = 200


def render_file(
    file_path: str, dpi: int = RENDER_DPI, return_dimensions: bool = False
) -> list[Image.Image] | tuple[list[Image.Image], list[tuple[float, float]]]:
    """Open a file and return PIL Images (one per page).

    If return_dimensions=True, returns (pages, page_dimensions) where
    page_dimensions are the original PDF page sizes in points.
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        img = Image.open(file_path).convert("RGB")
        pages = [img]
        dims = [(float(img.size[0]), float(img.size[1]))]
    elif ext == ".pdf":
        pages, dims = _render_pdf(file_path, dpi)
    elif ext in (".docx", ".doc"):
        pages, dims = _render_docx(file_path, dpi)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    if return_dimensions:
        return pages, dims
    return pages


def _render_pdf(file_path: str, dpi: int) -> tuple[list[Image.Image], list[tuple[float, float]]]:
    doc = pymupdf.open(file_path)
    pages = []
    dims = []
    for page in doc:
        dims.append((page.rect.width, page.rect.height))
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages, dims


def _render_docx(file_path: str, dpi: int) -> tuple[list[Image.Image], list[tuple[float, float]]]:
    doc = pymupdf.open(file_path)
    pages = []
    dims = []
    for page in doc:
        dims.append((page.rect.width, page.rect.height))
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        pages.append(img)
    doc.close()
    return pages, dims


def detect_format(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    elif ext == ".pdf":
        return "pdf"
    elif ext in (".docx", ".doc"):
        return "docx"
    else:
        return "unknown"
```

- [ ] **Step 4: Run all renderer tests**

```bash
uv run pytest tests/test_renderer.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pdf_fill/renderer.py tests/test_renderer.py
git commit -m "feat: renderer returns original page dimensions"
```

---

### Task 3: Fix PDF Export to Use Original Page Dimensions

**Files:**
- Modify: `src/pdf_fill/export.py`
- Create: `tests/test_export_quality.py`

- [ ] **Step 1: Write failing test for smart export**

```python
# tests/test_export_quality.py
import pytest
import pymupdf
from PIL import Image
from pdf_fill.export import export_as_pdf
from pdf_fill.drawing import draw_text_on_image


def test_export_preserves_original_page_dimensions(tmp_path):
    """PDF export should use original page dimensions, not pixel dimensions."""
    img = Image.new("RGB", (1700, 2200), "white")
    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out), page_dimensions=[(612.0, 792.0)])
    doc = pymupdf.open(str(out))
    page = doc[0]
    assert page.rect.width == pytest.approx(612.0, abs=1)
    assert page.rect.height == pytest.approx(792.0, abs=1)
    doc.close()


def test_export_roundtrip_preserves_content(tmp_path):
    """Text drawn at various Y positions should survive PDF roundtrip."""
    img = Image.new("RGB", (1700, 2200), "white")
    # Draw text at positions that previously got lost
    for y in [280, 588, 945, 1095, 1496]:
        img = draw_text_on_image(img, 140, y, f"Answer at y={y}", font_size=16, color="blue")

    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out), page_dimensions=[(612.0, 792.0)])

    # Re-render and check text is present
    doc = pymupdf.open(str(out))
    page = doc[0]
    pix = page.get_pixmap(dpi=200)
    result = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    # Check that non-white pixels exist near each text position (scaled)
    scale = result.size[1] / 2200
    for y in [280, 588, 945, 1095, 1496]:
        scaled_y = int(y * scale)
        # Sample a horizontal strip
        has_non_white = False
        for x in range(130, 500):
            if scaled_y < result.size[1]:
                px = result.getpixel((x, scaled_y))
                if px != (255, 255, 255):
                    has_non_white = True
                    break
        assert has_non_white, f"Text at y={y} (scaled to {scaled_y}) was lost in roundtrip"


def test_export_fallback_to_pixel_dimensions(tmp_path):
    """When no page_dimensions provided, fall back to pixel size."""
    img = Image.new("RGB", (800, 600), "white")
    out = tmp_path / "out.pdf"
    export_as_pdf([img], str(out))
    doc = pymupdf.open(str(out))
    page = doc[0]
    assert page.rect.width == pytest.approx(800.0, abs=1)
    assert page.rect.height == pytest.approx(600.0, abs=1)
    doc.close()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_export_quality.py -v
```

- [ ] **Step 3: Implement export fix**

```python
# src/pdf_fill/export.py
"""Export PIL Images to PDF or image files."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image


def export_as_pdf(
    pages: list[Image.Image],
    output_path: str,
    page_dimensions: list[tuple[float, float]] | None = None,
) -> str:
    """Save pages as a PDF file.

    Args:
        pages: PIL Images to save
        output_path: Output file path
        page_dimensions: Original page sizes in PDF points (width, height).
            If provided, pages are created at these dimensions and images are
            scaled to fit. If None, pixel dimensions are used as points.
    """
    doc = pymupdf.open()
    for i, img in enumerate(pages):
        img_bytes = _pil_to_png_bytes(img)
        if page_dimensions and i < len(page_dimensions):
            w_pt, h_pt = page_dimensions[i]
        else:
            w_pt, h_pt = float(img.size[0]), float(img.size[1])
        page = doc.new_page(width=w_pt, height=h_pt)
        page.insert_image(pymupdf.Rect(0, 0, w_pt, h_pt), stream=img_bytes)
    doc.save(output_path, deflate=True, deflate_images=True)
    doc.close()
    return output_path


def export_as_image(pages: list[Image.Image], output_path: str) -> str:
    """Save pages as image files. Multi-page creates numbered files."""
    path = Path(output_path)
    if len(pages) == 1:
        pages[0].save(output_path)
        return output_path

    stem = path.stem
    suffix = path.suffix or ".png"
    parent = path.parent
    paths = []
    for i, img in enumerate(pages):
        p = parent / f"{stem}_{i}{suffix}"
        img.save(str(p))
        paths.append(str(p))
    return ", ".join(paths)


def _pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_export_quality.py tests/test_export.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/pdf_fill/export.py tests/test_export_quality.py
git commit -m "fix: export PDF with original page dimensions to prevent quality loss"
```

---

## Chunk 2: Document Structure Detection

### Task 4: Text Extraction with Hybrid Strategy

**Files:**
- Create: `src/pdf_fill/structure.py`
- Create: `tests/test_structure.py`
- Create: `tests/fixtures/sample.pdf`

- [ ] **Step 1: Create a test fixture PDF**

```python
# Run this to create tests/fixtures/sample.pdf
import pymupdf

doc = pymupdf.open()
page = doc.new_page(width=612, height=792)

# Header
page.insert_text((72, 50), "Sample Worksheet", fontsize=18, fontname="helv")
page.insert_text((400, 50), "Name:___________", fontsize=12)

# Questions with answer space
page.insert_text((36, 100), "1.", fontsize=12)
page.insert_text((72, 100), "What is the first question?", fontsize=12)

page.insert_text((36, 150), "2.", fontsize=12)
page.insert_text((72, 150), "Describe the second concept.", fontsize=12)

# Checkboxes
page.insert_text((72, 250), "[ ] Option A    [ ] Option B", fontsize=12)

# Blank field
page.insert_text((72, 300), "Date: _______________", fontsize=12)

# Table-like area (draw grid lines)
for y in [400, 430, 460, 490]:
    page.draw_line((72, y), (400, y))
for x in [72, 200, 300, 400]:
    page.draw_line((x, 400), (x, 490))
page.insert_text((75, 418), "Item", fontsize=10)
page.insert_text((205, 418), "Qty", fontsize=10)
page.insert_text((305, 418), "Price", fontsize=10)

doc.save("tests/fixtures/sample.pdf")
doc.close()
```

- [ ] **Step 2: Write failing tests for text extraction**

```python
# tests/test_structure.py
import pytest
from pathlib import Path
from PIL import Image
from pdf_fill.structure import extract_text_lines, classify_elements

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_text_lines_from_pdf():
    """Extract text lines from a PDF with exact bboxes."""
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    assert len(lines) > 0
    # Each line should have text, bbox (in pixel coords), font_size
    first = lines[0]
    assert "text" in first
    assert "bbox" in first
    assert "font_size" in first
    assert len(first["bbox"]) == 4
    # Bboxes should be in pixel coordinates (scaled from PDF points)
    assert first["bbox"][2] > first["bbox"][0]  # x2 > x1
    assert first["bbox"][3] > first["bbox"][1]  # y2 > y1


def test_extract_text_lines_from_image():
    """For images (no PDF text layer), returns empty list without Surya."""
    img = Image.new("RGB", (400, 300), "white")
    lines = extract_text_lines(None, page_num=0, dpi=200, fallback_image=img)
    # Without surya, should return empty
    assert isinstance(lines, list)


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
    # Should find "Name:___________" and "Date: _______________"
    assert len(fields) >= 1
    name_fields = [f for f in fields if "name" in f.get("label", "").lower() or "date" in f.get("label", "").lower()]
    assert len(name_fields) >= 1


def test_classify_elements_finds_headers():
    lines = extract_text_lines(str(FIXTURES / "sample.pdf"), page_num=0, dpi=200)
    elements = classify_elements(lines, page_width=1700, page_height=2200)
    headers = [e for e in elements if e["type"] == "header"]
    assert len(headers) >= 1
    assert "Sample Worksheet" in headers[0]["text"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_structure.py -v
```

- [ ] **Step 4: Implement structure.py — text extraction**

```python
# src/pdf_fill/structure.py
"""Document structure detection: extract text, classify elements, find answer areas."""

from __future__ import annotations

import re
from PIL import Image

# Try to import pymupdf for PDF text extraction
import pymupdf


def extract_text_lines(
    source_path: str | None,
    page_num: int = 0,
    dpi: int = 200,
    fallback_image: Image.Image | None = None,
) -> list[dict]:
    """Extract text lines with bounding boxes from a document.

    For PDFs: uses PyMuPDF's text layer (exact, fast).
    For images/scanned docs: falls back to Surya OCR if available.

    Returns list of dicts with keys:
        text: str, bbox: [x1, y1, x2, y2] in pixel coords at given DPI,
        font_size: float, is_bold: bool
    """
    if source_path and source_path.lower().endswith(".pdf"):
        lines = _extract_from_pdf(source_path, page_num, dpi)
        if lines:
            return lines

    # Fallback to Surya OCR for scanned docs or images
    if fallback_image is not None:
        return _extract_with_ocr(fallback_image)

    return []


def _extract_from_pdf(source_path: str, page_num: int, dpi: int) -> list[dict]:
    """Extract text from PDF using PyMuPDF's text layer."""
    scale = dpi / 72.0
    doc = pymupdf.open(source_path)
    if page_num >= len(doc):
        doc.close()
        return []

    page = doc[page_num]
    data = page.get_text("dict")
    doc.close()

    lines = []
    for block in data["blocks"]:
        if block["type"] != 0:  # skip image blocks
            continue
        for line in block["lines"]:
            text_parts = []
            min_x, min_y, max_x, max_y = float("inf"), float("inf"), 0.0, 0.0
            max_font_size = 0.0
            is_bold = False
            for span in line["spans"]:
                t = span["text"].strip()
                if t:
                    text_parts.append(t)
                    b = span["bbox"]
                    min_x = min(min_x, b[0])
                    min_y = min(min_y, b[1])
                    max_x = max(max_x, b[2])
                    max_y = max(max_y, b[3])
                    max_font_size = max(max_font_size, span["size"])
                    if span["flags"] & 16:  # bold flag
                        is_bold = True

            text = " ".join(text_parts)
            if text:
                lines.append({
                    "text": text,
                    "bbox": [
                        round(min_x * scale),
                        round(min_y * scale),
                        round(max_x * scale),
                        round(max_y * scale),
                    ],
                    "font_size": max_font_size,
                    "is_bold": is_bold,
                })

    # Merge side-by-side lines (e.g., "1." at x=100 and "Question text?" at x=200
    # on the same Y coordinate). PyMuPDF puts these in separate line entries.
    merged = []
    skip = set()
    for i, line in enumerate(lines):
        if i in skip:
            continue
        # Check if next line overlaps vertically (within 5px) = side-by-side
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            vertical_overlap = (
                abs(line["bbox"][1] - nxt["bbox"][1]) < 10
                and abs(line["bbox"][3] - nxt["bbox"][3]) < 10
            )
            if vertical_overlap and line["bbox"][2] < nxt["bbox"][0]:
                # Merge: combine text, expand bbox
                merged.append({
                    "text": line["text"] + " " + nxt["text"],
                    "bbox": [
                        min(line["bbox"][0], nxt["bbox"][0]),
                        min(line["bbox"][1], nxt["bbox"][1]),
                        max(line["bbox"][2], nxt["bbox"][2]),
                        max(line["bbox"][3], nxt["bbox"][3]),
                    ],
                    "font_size": max(line["font_size"], nxt["font_size"]),
                    "is_bold": line["is_bold"] or nxt["is_bold"],
                })
                skip.add(i + 1)
                continue
        merged.append(line)

    return merged


def _extract_with_ocr(img: Image.Image) -> list[dict]:
    """Fallback: use Surya OCR for scanned documents."""
    try:
        from pdf_fill.analysis import ocr_page
        ocr_results = ocr_page(img)
        return [
            {
                "text": r["text"],
                "bbox": r["bbox"],
                "font_size": 12.0,  # OCR can't detect font size
                "is_bold": False,
            }
            for r in ocr_results
        ]
    except ImportError:
        return []


def classify_elements(
    lines: list[dict],
    page_width: int,
    page_height: int,
) -> list[dict]:
    """Classify text lines into semantic elements.

    Returns list of elements with type: 'question', 'field', 'checkbox',
    'header', 'text'. Questions include an 'answer_area' bbox.
    """
    elements: list[dict] = []

    for i, line in enumerate(lines):
        text = line["text"]
        bbox = line["bbox"]

        # --- Checkbox detection: "[ ] Label" patterns ---
        checkbox_pattern = re.finditer(r'\[\s*\]\s*(\w[\w\s]*?)(?=\s*\[|$)', text)
        found_checkbox = False
        for match in checkbox_pattern:
            found_checkbox = True
            label = match.group(1).strip()
            # Approximate checkbox position within the line
            char_offset = match.start() / max(len(text), 1)
            cb_x = bbox[0] + int((bbox[2] - bbox[0]) * char_offset)
            elements.append({
                "type": "checkbox",
                "label": label,
                "checked": False,
                "bbox": [cb_x, bbox[1], cb_x + (bbox[3] - bbox[1]), bbox[3]],
                "text": match.group(0).strip(),
            })
        if found_checkbox:
            continue

        # --- Field detection: "Label:____" or "Label: ________" ---
        field_match = re.match(r'^(.+?):\s*[_]{3,}', text)
        if field_match:
            label = field_match.group(1).strip()
            # Find where the underscores start
            underscore_start = text.index("_")
            char_ratio = underscore_start / max(len(text), 1)
            field_x = bbox[0] + int((bbox[2] - bbox[0]) * char_ratio)
            elements.append({
                "type": "field",
                "label": label,
                "bbox": bbox,
                "fill_area": [field_x, bbox[1], bbox[2], bbox[3]],
                "text": text,
            })
            continue

        # --- Question detection: starts with number. ---
        # Handle side-by-side "N." + "question text" blocks (PyMuPDF splits them).
        # If this line is just "N." and next line overlaps vertically, merge them.
        question_match = re.match(r'^(\d+)\.\s*(.*)', text)
        if question_match:
            num = int(question_match.group(1))
            q_text = question_match.group(2).strip()

            # Compute answer area: space between this line's bottom and next element's top
            next_top = page_height  # default to page bottom
            for j in range(i + 1, len(lines)):
                next_bbox = lines[j]["bbox"]
                gap = next_bbox[1] - bbox[3]
                if gap > 5:  # meaningful gap = answer space
                    next_top = next_bbox[1]
                    break

            answer_area = {
                "bbox": [bbox[0], bbox[3] + 2, bbox[2], next_top - 2],
            }
            elements.append({
                "type": "question",
                "number": num,
                "text": q_text,
                "bbox": bbox,
                "answer_area": answer_area,
            })
            continue

        # --- Header detection: bold or larger font ---
        avg_font = sum(l["font_size"] for l in lines) / max(len(lines), 1)
        if line["is_bold"] or line["font_size"] > avg_font * 1.3:
            elements.append({
                "type": "header",
                "text": text,
                "bbox": bbox,
            })
            continue

        # --- Default: plain text ---
        elements.append({
            "type": "text",
            "text": text,
            "bbox": bbox,
        })

    return elements
```

- [ ] **Step 5: Create the test fixture PDF**

```bash
uv run python -c "
import pymupdf

doc = pymupdf.open()
page = doc.new_page(width=612, height=792)
page.insert_text((72, 50), 'Sample Worksheet', fontsize=18, fontname='helv')
page.insert_text((400, 50), 'Name:___________', fontsize=12)
page.insert_text((36, 100), '1.', fontsize=12)
page.insert_text((72, 100), 'What is the first question?', fontsize=12)
page.insert_text((36, 150), '2.', fontsize=12)
page.insert_text((72, 150), 'Describe the second concept.', fontsize=12)
page.insert_text((72, 250), '[ ] Option A    [ ] Option B', fontsize=12)
page.insert_text((72, 300), 'Date: _______________', fontsize=12)
for y in [400, 430, 460, 490]:
    page.draw_line((72, y), (400, y))
for x in [72, 200, 300, 400]:
    page.draw_line((x, 400), (x, 490))
page.insert_text((75, 418), 'Item', fontsize=10)
page.insert_text((205, 418), 'Qty', fontsize=10)
page.insert_text((305, 418), 'Price', fontsize=10)
doc.save('tests/fixtures/sample.pdf')
doc.close()
print('Created tests/fixtures/sample.pdf')
"
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_structure.py -v
```
Expected: all tests PASS. If any element classification tests fail, adjust the regex patterns or thresholds in `classify_elements`.

- [ ] **Step 7: Commit**

```bash
git add src/pdf_fill/structure.py tests/test_structure.py tests/fixtures/sample.pdf
git commit -m "feat: document structure detection with text extraction and element classification"
```

---

### Task 5: Add measure_text Helper to Drawing Module

**Files:**
- Modify: `src/pdf_fill/drawing.py`
- Modify: `tests/test_drawing.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_drawing.py — append

from pdf_fill.drawing import measure_text_bbox


def test_measure_text_bbox():
    bbox = measure_text_bbox("Hello World", font_size=16)
    assert bbox["width"] > 0
    assert bbox["height"] > 0
    assert bbox["width"] > bbox["height"]  # text is wider than tall


def test_measure_text_bbox_scales_with_font():
    small = measure_text_bbox("Hello", font_size=12)
    large = measure_text_bbox("Hello", font_size=24)
    assert large["width"] > small["width"]
    assert large["height"] > small["height"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_drawing.py -v -k "measure"
```

- [ ] **Step 3: Implement measure_text_bbox**

Add to `src/pdf_fill/drawing.py`:

```python
def measure_text_bbox(text: str, font_size: int = 16) -> dict:
    """Measure the bounding box of text without drawing it.

    Returns dict with keys: width, height (in pixels).
    """
    font = _get_font(font_size)
    bbox = font.getbbox(text)
    return {
        "width": bbox[2] - bbox[0],
        "height": bbox[3] - bbox[1],
    }
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_drawing.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/pdf_fill/drawing.py tests/test_drawing.py
git commit -m "feat: add measure_text_bbox helper"
```

---

## Chunk 3: Wire Everything to the MCP Server

### Task 6: Update open_document to Use Dimensions + Structure

**Files:**
- Modify: `src/pdf_fill/server.py`

- [ ] **Step 1: Update open_document**

Replace the `open_document` function in `server.py`:

```python
@mcp.tool()
def open_document(file_path: str) -> str:
    """Open a PDF, DOCX, or image file for editing.

    Returns page count, dimensions, and a structural analysis of the first page
    including detected questions, fields, checkboxes, headers, and answer areas.
    """
    global _state
    _state = DocumentState()
    pages, dims = render_file(file_path, return_dimensions=True)
    fmt = detect_format(file_path)
    _state.load_pages(pages, source_path=file_path, source_format=fmt,
                      page_dimensions=dims)

    # Auto-analyze first page structure
    w, h = pages[0].size
    structure = _analyze_page_structure(0)

    result = {
        "file": Path(file_path).name,
        "pages": len(pages),
        "page_size_px": f"{w}x{h}",
        "page_size_pt": f"{dims[0][0]:.0f}x{dims[0][1]:.0f}",
        "elements": structure,
    }
    return json.dumps(result, indent=2)
```

- [ ] **Step 2: Add helper function and new tools**

Add these to `server.py`:

```python
from pdf_fill.structure import extract_text_lines, classify_elements
from pdf_fill.drawing import measure_text_bbox as _measure_text


def _analyze_page_structure(page_num: int = 0) -> list[dict]:
    """Extract and classify page structure, with caching."""
    cached = _state.get_structure(page_num)
    if cached is not None:
        return cached

    page_img = _state.get_page(page_num)
    w, h = page_img.size
    lines = extract_text_lines(
        _state.source_path,
        page_num=page_num,
        dpi=_state.render_dpi,
        fallback_image=page_img,
    )
    elements = classify_elements(lines, page_width=w, page_height=h)
    _state.set_structure(page_num, elements)
    return elements


@mcp.tool()
def get_page_structure(page_number: int = 0) -> str:
    """Get the structural analysis of a page.

    Returns JSON with classified elements: questions (with answer areas),
    fields (with fill areas), checkboxes, headers, tables, and plain text.
    Each element includes pixel-accurate bounding boxes.

    Args:
        page_number: Page to analyze (0-indexed)
    """
    _state.go_to_page(page_number)
    elements = _analyze_page_structure(page_number)
    return json.dumps({"page": page_number, "elements": elements}, indent=2)


@mcp.tool()
def measure_text(text: str, font_size: int = 16) -> str:
    """Measure the pixel dimensions of text before drawing it.

    Use this to check if text will fit in an answer area before drawing.

    Args:
        text: The text to measure
        font_size: Font size in pixels
    """
    dims = _measure_text(text, font_size)
    return json.dumps(dims)


@mcp.tool()
def render_page_annotated(page_number: int = 0) -> Image:
    """Render a page with colored overlays showing detected elements.

    Questions = blue outlines, answer areas = green fills,
    checkboxes = orange outlines, fields = purple outlines.
    Useful for verifying structure detection before filling.

    Args:
        page_number: Page to render (0-indexed)
    """
    _state.go_to_page(page_number)
    page = _state.get_page().copy()
    elements = _analyze_page_structure(page_number)

    from pdf_fill.drawing import draw_shape_on_image, draw_highlight_on_image

    for el in elements:
        bbox = el.get("bbox", [])
        if not bbox or len(bbox) < 4:
            continue

        if el["type"] == "question":
            page = draw_shape_on_image(page, "rectangle", bbox[0], bbox[1], bbox[2], bbox[3],
                                       outline_color="blue", stroke_width=1)
            aa = el.get("answer_area", {}).get("bbox")
            if aa:
                page = draw_highlight_on_image(page, aa[0], aa[1], aa[2], aa[3],
                                               color="green", opacity=0.15)
        elif el["type"] == "checkbox":
            page = draw_shape_on_image(page, "rectangle", bbox[0], bbox[1], bbox[2], bbox[3],
                                       outline_color="orange", stroke_width=2)
        elif el["type"] == "field":
            fa = el.get("fill_area", bbox)
            page = draw_highlight_on_image(page, fa[0], fa[1], fa[2], fa[3],
                                           color="purple", opacity=0.15)

    return _pil_to_mcp_image(page)
```

- [ ] **Step 3: Update save_document to pass page dimensions**

```python
@mcp.tool()
def save_document(output_path: str, format: str = "auto") -> str:
    """Save the edited document.

    Args:
        output_path: Where to save the file
        format: 'pdf', 'png', or 'auto' (matches input format)
    """
    pages = _state.get_all_pages()
    if not pages:
        return "No document is open."

    fmt = format
    if fmt == "auto":
        fmt = _state.source_format or "png"
        if fmt == "docx":
            fmt = "pdf"
        if fmt == "image":
            fmt = "png"

    if fmt == "pdf":
        export_as_pdf(pages, output_path, page_dimensions=_state.page_dimensions)
    else:
        export_as_image(pages, output_path)
    return f"Saved to {output_path}"
```

- [ ] **Step 4: Verify server loads with new tools**

```bash
uv run python -c "
from pdf_fill.server import mcp
tools = list(mcp._tool_manager._tools.keys())
print(f'Total tools: {len(tools)}')
for t in sorted(tools):
    print(f'  - {t}')
"
```
Expected: 24 tools (21 original + get_page_structure + measure_text + render_page_annotated).

- [ ] **Step 5: Commit**

```bash
git add src/pdf_fill/server.py
git commit -m "feat: wire structure detection, measure_text, and annotated render to MCP server"
```

---

### Task 7: Update MCP Server Instructions

**Files:**
- Modify: `src/pdf_fill/server.py`

- [ ] **Step 1: Update the FastMCP instructions**

Replace the `instructions` parameter in the `FastMCP(...)` constructor:

```python
mcp = FastMCP(
    "pdf-fill",
    instructions=(
        "Document analysis and filling server. Workflow:\n"
        "1. open_document — opens file and returns structural analysis (questions, fields, checkboxes with pixel coords)\n"
        "2. render_page — see the page visually\n"
        "3. render_page_annotated — see detected elements highlighted (questions=blue, answers=green, checkboxes=orange)\n"
        "4. get_page_structure — get element coordinates for any page\n"
        "5. measure_text — check if text fits before drawing\n"
        "6. draw_text / fill_checkbox / draw_shape — draw using coordinates from structure analysis\n"
        "7. save_document — export with preserved quality\n\n"
        "IMPORTANT: Always use get_page_structure or open_document output to get exact coordinates. "
        "Never guess pixel positions. For questions, draw answers in the answer_area bbox. "
        "For fields, draw in the fill_area bbox. For checkboxes, use the checkbox center coordinates."
    ),
)
```

- [ ] **Step 2: Verify**

```bash
uv run python -c "from pdf_fill.server import mcp; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add src/pdf_fill/server.py
git commit -m "feat: update MCP instructions for structure-aware workflow"
```

---

## Chunk 4: End-to-End Verification

### Task 8: Run Full Test Suite and Deploy

- [ ] **Step 1: Run all tests**

```bash
uv run pytest tests/ -v
```
Expected: all tests PASS (existing + new).

- [ ] **Step 2: End-to-end test with the electrophoresis worksheet**

```bash
uv run python -c "
import json
from pdf_fill.renderer import render_file
from pdf_fill.structure import extract_text_lines, classify_elements

pages, dims = render_file('/Users/avner/Downloads/electrophoresis-lab-worksheet.pdf', return_dimensions=True)
lines = extract_text_lines('/Users/avner/Downloads/electrophoresis-lab-worksheet.pdf', page_num=0, dpi=200)
elements = classify_elements(lines, page_width=pages[0].size[0], page_height=pages[0].size[1])

questions = [e for e in elements if e['type'] == 'question']
fields = [e for e in elements if e['type'] == 'field']
checkboxes = [e for e in elements if e['type'] == 'checkbox']

print(f'Questions: {len(questions)}')
for q in questions:
    aa = q['answer_area']['bbox']
    print(f'  Q{q[\"number\"]}: \"{q[\"text\"][:50]}\" -> answer at y={aa[1]}-{aa[3]} ({aa[3]-aa[1]}px)')

print(f'Fields: {len(fields)}')
for f in fields:
    print(f'  {f[\"label\"]}: fill_area={f.get(\"fill_area\", \"n/a\")}')

print(f'Checkboxes: {len(checkboxes)}')
for c in checkboxes:
    print(f'  [{\"x\" if c[\"checked\"] else \" \"}] {c[\"label\"]} at {c[\"bbox\"]}')
"
```
Expected: detects all 17 questions with answer areas, the Name field, and checkboxes.

- [ ] **Step 3: Deploy updated server**

```bash
fly deploy
```

- [ ] **Step 4: Commit everything and push**

```bash
git add -A
git commit -m "feat: document intelligence with structure detection, smart export, and QOL tools"
git push
```

---

## Verification Checklist

- [ ] `uv run pytest tests/ -v` — all tests pass
- [ ] `open_document` returns structured element map with questions, fields, checkboxes
- [ ] `get_page_structure` returns accurate bboxes for all elements
- [ ] `render_page_annotated` shows colored overlays on detected elements
- [ ] `measure_text` returns correct width/height for text
- [ ] `save_document` preserves original PDF page dimensions (no quality loss)
- [ ] PDF roundtrip: text at all Y positions survives export and re-render
- [ ] Electrophoresis worksheet: all 17 questions detected with answer areas
- [ ] Server loads with 24 tools
- [ ] Deployed to Fly.io
