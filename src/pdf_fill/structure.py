"""Document structure detection: extract text, classify elements, find answer areas."""

from __future__ import annotations

import re
from PIL import Image

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
    # Try PyMuPDF text extraction for PDFs and DOCX (any format it can open)
    if source_path:
        ext = source_path.lower().rsplit(".", 1)[-1] if "." in source_path else ""
        if ext in ("pdf", "docx", "doc"):
            lines = _extract_from_pdf(source_path, page_num, dpi)
            if lines:
                return lines

    # Fallback to Surya OCR for scanned docs, images, or docs with no text layer
    if fallback_image is not None:
        return _extract_with_ocr(fallback_image)

    return []


def _extract_from_pdf(source_path: str, page_num: int, dpi: int) -> list[dict]:
    """Extract text from PDF/DOCX using PyMuPDF's text layer."""
    scale = dpi / 72.0

    # Old .doc format: convert to .docx first (same as renderer)
    if source_path.lower().endswith(".doc") and not source_path.lower().endswith(".docx"):
        import subprocess
        import tempfile
        try:
            tmp_docx = tempfile.mktemp(suffix=".docx")
            subprocess.run(
                ["textutil", "-convert", "docx", source_path, "-output", tmp_docx],
                check=True, capture_output=True,
            )
            source_path = tmp_docx
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    doc = pymupdf.open(source_path)
    try:
        if page_num >= len(doc):
            return []
        page = doc[page_num]
        data = page.get_text("dict")
    finally:
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
    # on the same Y coordinate). PyMuPDF splits these into separate line entries.
    # Uses a while-loop to handle 3+ fragments on the same line (not just pairs).
    merged = []
    i = 0
    while i < len(lines):
        current = dict(lines[i])
        while i + 1 < len(lines):
            nxt = lines[i + 1]
            vertical_overlap = (
                abs(current["bbox"][1] - nxt["bbox"][1]) < 10
                and abs(current["bbox"][3] - nxt["bbox"][3]) < 10
            )
            if vertical_overlap and current["bbox"][2] < nxt["bbox"][0]:
                current = {
                    "text": current["text"] + " " + nxt["text"],
                    "bbox": [
                        min(current["bbox"][0], nxt["bbox"][0]),
                        min(current["bbox"][1], nxt["bbox"][1]),
                        max(current["bbox"][2], nxt["bbox"][2]),
                        max(current["bbox"][3], nxt["bbox"][3]),
                    ],
                    "font_size": max(current["font_size"], nxt["font_size"]),
                    "is_bold": current["is_bold"] or nxt["is_bold"],
                }
                i += 1
            else:
                break
        merged.append(current)
        i += 1

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


_INSTRUCTION_VERBS = re.compile(
    r"^(use|simplify|evaluate|solve|find|write|prime|graph|perform|"
    r"factor|determine|which|how|what|compute|calculate|describe|"
    r"identify|explain|prove|reduce|convert|express|rewrite|show|list)\b",
    re.IGNORECASE,
)

_EXPRESSION_PATTERN = re.compile(
    r"^[^a-zA-Z]{0,5}[\d\w\s\+\-\*/=\(\)\[\]\{\}\^<>≤≥,.]+=$"
    r"|"
    r"^[\d\w\s\+\-\*/=\(\)\[\]\{\}\^<>≤≥,.]+\s*=\s*$"
)


def classify_elements(
    lines: list[dict],
    page_width: int,
    page_height: int,
) -> list[dict]:
    """Classify text lines into semantic elements.

    Returns list of elements with types:
    - 'question': numbered items (1. What is...) with answer_area
    - 'instruction': task prompts (Simplify..., Solve...) that group exercises
    - 'expression': math expressions/equations to solve (contain = sign)
    - 'field': fill-in blanks (Name:_______)
    - 'checkbox': [ ] Option patterns
    - 'header': bold text or larger font
    - 'text': everything else
    """
    elements: list[dict] = []
    avg_font = sum(l["font_size"] for l in lines) / max(len(lines), 1) if lines else 12.0
    skip_indices: set[int] = set()

    for i, line in enumerate(lines):
        if i in skip_indices:
            continue
        text = line["text"]
        bbox = line["bbox"]

        # --- Checkbox detection: "[ ] Label" patterns ---
        checkbox_matches = list(re.finditer(r'\[\s*\]\s*([^\[\]]+?)(?=\s*\[|$)', text))
        if checkbox_matches:
            for match in checkbox_matches:
                label = match.group(1).strip()
                char_offset = match.start() / max(len(text), 1)
                cb_x = bbox[0] + int((bbox[2] - bbox[0]) * char_offset)
                elements.append({
                    "type": "checkbox",
                    "label": label,
                    "checked": False,
                    "bbox": [cb_x, bbox[1], cb_x + (bbox[3] - bbox[1]), bbox[3]],
                    "text": match.group(0).strip(),
                })
            continue

        # --- Field detection: "Label:____" or "Label: ________" ---
        field_match = re.match(r'^(.+?):\s*[_]{3,}', text)
        if field_match:
            label = field_match.group(1).strip()
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

        # --- Numbered question detection: starts with number. ---
        question_match = re.match(r'^(\d+)\.\s*(.*)', text)
        if question_match:
            num = int(question_match.group(1))
            q_text = question_match.group(2).strip()

            next_top = page_height
            for j in range(i + 1, len(lines)):
                next_bbox = lines[j]["bbox"]
                gap = next_bbox[1] - bbox[3]
                if gap > 5:
                    next_top = next_bbox[1]
                    break

            answer_area = {
                "bbox": [bbox[0], bbox[3] + 2, max(bbox[2], page_width - bbox[0]), next_top - 2],
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
        if line["is_bold"] or line["font_size"] > avg_font * 1.3:
            elements.append({
                "type": "header",
                "text": text,
                "bbox": bbox,
            })
            continue

        # --- Instruction detection: imperative task prompts ---
        # "Simplify the following...", "Solve and graph...", "Find the slope..."
        # Also catches lines ending with ":" as instructions
        text_stripped = text.rstrip()
        if _INSTRUCTION_VERBS.match(text_stripped) or (
            text_stripped.endswith(":") and len(text_stripped) > 10
        ):
            # Absorb continuation lines (tiny vertical gap = same sentence wrapping)
            full_text = text
            last_bbox = list(bbox)
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                gap = nxt["bbox"][1] - last_bbox[3]
                # Continuation: small gap AND doesn't start with instruction verb or number
                if gap < 10 and not _INSTRUCTION_VERBS.match(nxt["text"].rstrip()) and not re.match(r'^\d+\.', nxt["text"]):
                    full_text += " " + nxt["text"]
                    last_bbox = [
                        min(last_bbox[0], nxt["bbox"][0]),
                        min(last_bbox[1], nxt["bbox"][1]),
                        max(last_bbox[2], nxt["bbox"][2]),
                        max(last_bbox[3], nxt["bbox"][3]),
                    ]
                    skip_indices.add(j)
                    j += 1
                else:
                    break
            text = full_text
            bbox = last_bbox

            # Collect exercises that follow this instruction until the next instruction/header
            exercise_bboxes = []
            for j in range(j, len(lines)):
                nxt = lines[j]
                nxt_text = nxt["text"].rstrip()
                # Stop at next instruction, header, or large gap section
                if _INSTRUCTION_VERBS.match(nxt_text):
                    break
                if nxt.get("is_bold") or nxt.get("font_size", 0) > avg_font * 1.3:
                    break
                exercise_bboxes.append(nxt["bbox"])

            # The work area spans from after this instruction to the last exercise
            if exercise_bboxes:
                work_area = {
                    "bbox": [
                        bbox[0],
                        bbox[3] + 2,
                        max(bbox[2], page_width - bbox[0]),
                        exercise_bboxes[-1][3] + 2,
                    ],
                }
            else:
                # No exercises found — answer area is whitespace below
                next_top = page_height
                for j in range(i + 1, len(lines)):
                    gap = lines[j]["bbox"][1] - bbox[3]
                    if gap > 5:
                        next_top = lines[j]["bbox"][1]
                        break
                work_area = {
                    "bbox": [bbox[0], bbox[3] + 2, max(bbox[2], page_width - bbox[0]), next_top - 2],
                }

            elements.append({
                "type": "instruction",
                "text": text,
                "bbox": bbox,
                "work_area": work_area,
            })
            continue

        # --- Expression detection: math with = sign, short ---
        if "=" in text and len(text) < 60:
            # Check it looks like a math expression (has operators or variables)
            has_math = bool(re.search(r'[\d\w]+\s*[+\-*/^=<>≤≥]', text))
            if has_math:
                # Answer area: to the right of = or below the expression
                eq_pos = text.rindex("=")
                char_ratio = (eq_pos + 1) / max(len(text), 1)
                answer_x = bbox[0] + int((bbox[2] - bbox[0]) * char_ratio)

                # Also compute space below for multi-line answers
                next_top = page_height
                for j in range(i + 1, len(lines)):
                    gap = lines[j]["bbox"][1] - bbox[3]
                    if gap > 5:
                        next_top = lines[j]["bbox"][1]
                        break

                elements.append({
                    "type": "expression",
                    "text": text,
                    "bbox": bbox,
                    "answer_area": {
                        "inline": [answer_x + 5, bbox[1], page_width - bbox[0], bbox[3]],
                        "below": [bbox[0], bbox[3] + 2, max(bbox[2], page_width - bbox[0]), next_top - 2],
                    },
                })
                continue

        # --- Default: plain text ---
        elements.append({
            "type": "text",
            "text": text,
            "bbox": bbox,
        })

    return elements
