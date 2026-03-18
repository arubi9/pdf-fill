"""PDF-Fill MCP server — tools for document analysis and filling."""

from __future__ import annotations

import io
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image, Context

from pdf_fill.state import DocumentState
from pdf_fill.renderer import render_file, detect_format
from pdf_fill.drawing import (
    draw_text_on_image,
    draw_shape_on_image,
    draw_arrow_on_image,
    draw_highlight_on_image,
    erase_region_on_image,
    fill_checkbox_on_image,
    draw_path_on_image,
    color_fill_on_image,
    measure_text_bbox as _measure_text,
)
from pdf_fill.export import export_as_pdf, export_as_image
from pdf_fill.structure import extract_text_lines, classify_elements

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

# Global document state (one document at a time)
_state = DocumentState()
_clipboard = None


def _pil_to_mcp_image(img) -> Image:
    """Convert a PIL Image to an MCP Image for Claude to see."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Image(data=buf.getvalue(), format="png")


# --- Document management tools ---


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
def open_document(file_path: str) -> str:
    """Open a PDF, DOCX, or image file for editing.

    Returns page count, dimensions, and a structural analysis of the first page
    including detected questions, fields, checkboxes, headers, and answer areas
    with pixel-accurate bounding boxes.
    """
    global _state
    _state = DocumentState()
    pages, dims = render_file(file_path, return_dimensions=True)
    fmt = detect_format(file_path)
    _state.load_pages(pages, source_path=file_path, source_format=fmt,
                      page_dimensions=dims)

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


@mcp.tool()
def render_page(page_number: int = 0) -> Image:
    """Render a page as an image so you can see it.

    Page numbers are 0-indexed. Returns the page image.
    """
    _state.go_to_page(page_number)
    return _pil_to_mcp_image(_state.get_page())


@mcp.tool()
def get_canvas() -> Image:
    """Get the current working page with all edits applied."""
    return _pil_to_mcp_image(_state.get_page())


@mcp.tool()
def undo() -> str:
    """Undo the last drawing operation on the current page."""
    if _state.undo():
        return "Undone."
    return "Nothing to undo."


@mcp.tool()
def get_page_structure(page_number: int = 0) -> str:
    """Get the structural analysis of a page.

    Returns JSON with classified elements: questions (with answer areas),
    fields (with fill areas), checkboxes, headers, and plain text.
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

    for el in elements:
        bbox = el.get("bbox", [])
        if not bbox or len(bbox) < 4:
            continue

        if el["type"] == "question":
            page = draw_shape_on_image(
                page, "rectangle", bbox[0], bbox[1], bbox[2], bbox[3],
                outline_color="blue", stroke_width=1,
            )
            aa = el.get("answer_area", {}).get("bbox")
            if aa:
                page = draw_highlight_on_image(
                    page, aa[0], aa[1], aa[2], aa[3],
                    color="green", opacity=0.15,
                )
        elif el["type"] == "checkbox":
            page = draw_shape_on_image(
                page, "rectangle", bbox[0], bbox[1], bbox[2], bbox[3],
                outline_color="orange", stroke_width=2,
            )
        elif el["type"] == "field":
            fa = el.get("fill_area", bbox)
            page = draw_highlight_on_image(
                page, fa[0], fa[1], fa[2], fa[3],
                color="purple", opacity=0.15,
            )

    return _pil_to_mcp_image(page)


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
            fmt = "pdf"  # DOCX write-back not supported; export as PDF
        if fmt == "image":
            fmt = "png"

    if fmt == "pdf":
        export_as_pdf(pages, output_path, page_dimensions=_state.page_dimensions)
    else:
        export_as_image(pages, output_path)
    return f"Saved to {output_path}"


@mcp.tool()
def merge_documents(file_paths: str) -> str:
    """Merge multiple documents into the current working document.

    Args:
        file_paths: Comma-separated file paths to merge (appended after current pages)
    """
    paths = [p.strip() for p in file_paths.split(",")]
    all_pages = _state.get_all_pages()
    for path in paths:
        new_pages = render_file(path)
        all_pages.extend(new_pages)
    _state.load_pages(
        all_pages,
        source_path=_state.source_path or paths[0],
        source_format=_state.source_format or "pdf",
    )
    return f"Merged. Total pages: {_state.page_count}"


# --- Drawing tools ---


@mcp.tool()
def draw_text(
    x: float,
    y: float,
    text: str,
    font_size: int = 16,
    color: str = "black",
    align: str = "left",
) -> Image:
    """Draw text at (x, y) on the current page.

    Args:
        x: X coordinate (pixels from left)
        y: Y coordinate (pixels from top)
        text: The text to draw
        font_size: Font size in pixels
        color: Color name or hex (e.g. 'red', '#ff0000')
        align: Text alignment: 'left', 'center', 'right'
    """
    _state.save_snapshot()
    result = draw_text_on_image(_state.get_page(), x, y, text, font_size, color, align)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def draw_shape(
    shape: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    outline_color: str = "black",
    fill_color: str = "",
    stroke_width: int = 2,
) -> Image:
    """Draw a shape on the current page.

    Args:
        shape: 'rectangle', 'circle', or 'line'
        x1, y1: Top-left corner (or start point for line)
        x2, y2: Bottom-right corner (or end point for line)
        outline_color: Outline color
        fill_color: Fill color (empty string for no fill)
        stroke_width: Line thickness in pixels
    """
    _state.save_snapshot()
    fc = fill_color if fill_color else None
    result = draw_shape_on_image(
        _state.get_page(), shape, x1, y1, x2, y2, outline_color, fc, stroke_width
    )
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def draw_arrow(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str = "black",
    width: int = 2,
    head_size: int = 12,
    label: str = "",
) -> Image:
    """Draw an arrow from (x1,y1) to (x2,y2) with optional label.

    Args:
        x1, y1: Arrow start point
        x2, y2: Arrow end point (where the head is)
        color: Arrow color
        width: Shaft thickness
        head_size: Arrowhead size in pixels
        label: Optional text label near the midpoint
    """
    _state.save_snapshot()
    lb = label if label else None
    result = draw_arrow_on_image(
        _state.get_page(), x1, y1, x2, y2, color, width, head_size, lb
    )
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def draw_highlight(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    color: str = "yellow",
    opacity: float = 0.3,
) -> Image:
    """Draw a semi-transparent highlight overlay on a region.

    Args:
        x1, y1: Top-left corner
        x2, y2: Bottom-right corner
        color: Highlight color
        opacity: Transparency (0.0 = invisible, 1.0 = opaque)
    """
    _state.save_snapshot()
    result = draw_highlight_on_image(_state.get_page(), x1, y1, x2, y2, color, opacity)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def erase_region(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    fill_color: str = "white",
) -> Image:
    """White-out (erase) a rectangular region on the current page.

    Args:
        x1, y1: Top-left corner
        x2, y2: Bottom-right corner
        fill_color: Color to fill the erased region with (default white)
    """
    _state.save_snapshot()
    result = erase_region_on_image(_state.get_page(), x1, y1, x2, y2, fill_color)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def fill_checkbox(
    x: float,
    y: float,
    size: int = 20,
    style: str = "check",
    color: str = "black",
) -> Image:
    """Fill a checkbox or bubble at (x, y).

    Args:
        x, y: Center of the checkbox
        size: Size of the mark in pixels
        style: 'check' (checkmark), 'x' (cross), or 'fill' (filled circle)
        color: Mark color
    """
    _state.save_snapshot()
    result = fill_checkbox_on_image(_state.get_page(), x, y, size, style, color)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def draw_path(
    points: str,
    color: str = "black",
    width: int = 2,
    closed: bool = False,
) -> Image:
    """Draw a freeform path through a series of points.

    Args:
        points: Comma-separated x,y pairs. E.g. "10,20,50,60,100,30"
        color: Path color
        width: Line thickness
        closed: Whether to close the path (connect last point to first)
    """
    coords = [float(v) for v in points.split(",")]
    point_list = [(coords[i], coords[i + 1]) for i in range(0, len(coords) - 1, 2)]
    _state.save_snapshot()
    result = draw_path_on_image(_state.get_page(), point_list, color, width, closed)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def color_fill(
    x: int,
    y: int,
    fill_color: str = "red",
    tolerance: int = 30,
) -> Image:
    """Flood fill from (x, y) — like a paint bucket tool.

    Args:
        x, y: Starting point for the fill
        fill_color: Color to fill with
        tolerance: How similar neighboring pixels must be to get filled (0-255)
    """
    _state.save_snapshot()
    result = color_fill_on_image(_state.get_page(), x, y, fill_color, tolerance)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


# --- Table and region tools ---


@mcp.tool()
def fill_table_cell(
    row: int,
    col: int,
    text: str,
    table_x1: float = 0,
    table_y1: float = 0,
    table_x2: float = 0,
    table_y2: float = 0,
    rows: int = 1,
    cols: int = 1,
    font_size: int = 14,
    color: str = "black",
) -> Image:
    """Write text into a table cell by row/column index.

    If table bounds and grid size are provided, calculates cell position automatically.
    Otherwise, use analyze_table first to get cell coordinates, then use draw_text directly.

    Args:
        row: Row index (0-based)
        col: Column index (0-based)
        text: Text to write in the cell
        table_x1, table_y1: Top-left of the table region
        table_x2, table_y2: Bottom-right of the table region
        rows, cols: Number of rows and columns in the table
        font_size: Font size
        color: Text color
    """
    if table_x2 <= table_x1 or table_y2 <= table_y1:
        return _pil_to_mcp_image(_state.get_page())

    cell_w = (table_x2 - table_x1) / cols
    cell_h = (table_y2 - table_y1) / rows
    x = table_x1 + col * cell_w + 4  # 4px padding
    y = table_y1 + row * cell_h + 4

    _state.save_snapshot()
    result = draw_text_on_image(_state.get_page(), x, y, text, font_size, color)
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def copy_region(x1: float, y1: float, x2: float, y2: float) -> str:
    """Copy a rectangular region of the current page to clipboard.

    Args:
        x1, y1: Top-left corner
        x2, y2: Bottom-right corner
    """
    global _clipboard
    region = _state.get_page().crop((int(x1), int(y1), int(x2), int(y2)))
    _clipboard = region
    w, h = region.size
    return f"Copied region {w}x{h}px"


@mcp.tool()
def paste_region(x: float, y: float) -> Image:
    """Paste the previously copied region at (x, y).

    Args:
        x, y: Top-left corner where the region will be pasted
    """
    global _clipboard
    if _clipboard is None:
        return _pil_to_mcp_image(_state.get_page())
    _state.save_snapshot()
    result = _state.get_page().copy()
    result.paste(_clipboard, (int(x), int(y)))
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def add_stamp(
    image_path: str,
    x: float,
    y: float,
    width: float = 0,
    height: float = 0,
    opacity: float = 1.0,
) -> Image:
    """Add a stamp, signature, or watermark image overlay.

    Args:
        image_path: Path to the stamp/signature image (PNG with transparency recommended)
        x, y: Where to place the top-left corner
        width, height: Resize dimensions (0 = keep original)
        opacity: Transparency (0.0-1.0)
    """
    from PIL import Image as PILImage

    stamp = PILImage.open(image_path).convert("RGBA")
    if width > 0 and height > 0:
        stamp = stamp.resize((int(width), int(height)))
    if opacity < 1.0:
        alpha = stamp.split()[3]
        alpha = alpha.point(lambda p: int(p * opacity))
        stamp.putalpha(alpha)

    _state.save_snapshot()
    result = _state.get_page().copy().convert("RGBA")
    result.paste(stamp, (int(x), int(y)), stamp)
    result = result.convert("RGB")
    _state.set_page(result)
    return _pil_to_mcp_image(result)


@mcp.tool()
def replace_text(
    search_text: str,
    new_text: str,
    font_size: int = 16,
    color: str = "black",
    region_x1: float = 0,
    region_y1: float = 0,
    region_x2: float = 0,
    region_y2: float = 0,
) -> Image:
    """Find existing text via OCR and replace it with new text.

    Requires surya-ocr. Searches the full page or a specified region for search_text,
    erases that area, and draws new_text in its place.

    Args:
        search_text: Text to find on the page
        new_text: Replacement text
        font_size: Font size for the new text
        color: Color for the new text
        region_x1, region_y1, region_x2, region_y2: Optional region to limit search
    """
    try:
        from pdf_fill.analysis import ocr_page
    except ImportError:
        return _pil_to_mcp_image(_state.get_page())

    page = _state.get_page()
    text_lines = ocr_page(page)

    for line in text_lines:
        if search_text.lower() in line["text"].lower():
            bbox = line["bbox"]
            _state.save_snapshot()
            # Erase the old text
            result = erase_region_on_image(page, bbox[0], bbox[1], bbox[2], bbox[3])
            # Draw the new text at the same location
            result = draw_text_on_image(result, bbox[0], bbox[1], new_text, font_size, color)
            _state.set_page(result)
            return _pil_to_mcp_image(result)

    return _pil_to_mcp_image(page)


# --- Analysis tools ---


@mcp.tool()
def analyze_region(
    x1: float = 0,
    y1: float = 0,
    x2: float = 0,
    y2: float = 0,
    include_layout: bool = False,
) -> str:
    """Run OCR and optionally layout detection on the current page or a region.

    Returns JSON with detected text lines, bounding boxes, and confidence scores.
    If include_layout is True, also returns layout elements (headers, tables, images, etc.)

    Args:
        x1, y1, x2, y2: Region to analyze (0,0,0,0 = full page)
        include_layout: Whether to include layout detection results
    """
    try:
        from pdf_fill.analysis import ocr_page, analyze_layout
    except ImportError:
        return json.dumps(
            {"error": "surya-ocr not installed. Install with: pip install surya-ocr"}
        )

    page = _state.get_page()
    if x2 > x1 and y2 > y1:
        page = page.crop((int(x1), int(y1), int(x2), int(y2)))

    result = {"text_lines": ocr_page(page)}
    if include_layout:
        result["layout"] = analyze_layout(page)
    return json.dumps(result, indent=2)


@mcp.tool()
def analyze_table(
    x1: float = 0,
    y1: float = 0,
    x2: float = 0,
    y2: float = 0,
) -> str:
    """Detect table structure on the current page or a region.

    Returns JSON with cell positions, rows, columns, and any detected text.

    Args:
        x1, y1, x2, y2: Region containing the table (0,0,0,0 = full page)
    """
    try:
        from pdf_fill.analysis import analyze_tables
    except ImportError:
        return json.dumps(
            {"error": "surya-ocr not installed. Install with: pip install surya-ocr"}
        )

    page = _state.get_page()
    if x2 > x1 and y2 > y1:
        page = page.crop((int(x1), int(y1), int(x2), int(y2)))

    tables = analyze_tables(page)
    return json.dumps({"tables": tables}, indent=2)


def main():
    import argparse
    import os

    parser = argparse.ArgumentParser(description="PDF-Fill MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="Transport protocol (default: stdio, or set MCP_TRANSPORT env var)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "8000")),
        help="Port to listen on (default: 8000)",
    )
    args = parser.parse_args()

    mcp.settings.host = args.host
    mcp.settings.port = args.port

    # Disable DNS rebinding protection for remote deployments
    if args.transport != "stdio":
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
