"""PDF-Fill MCP server — tools for document analysis and filling."""

from __future__ import annotations

import io
from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image, Context

from pdf_fill.state import DocumentState
from pdf_fill.renderer import render_file, detect_format

mcp = FastMCP(
    "pdf-fill",
    instructions=(
        "Document analysis and filling server. Open a document with open_document, "
        "view pages with render_page, draw on them, then save with save_document."
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


@mcp.tool()
def open_document(file_path: str) -> str:
    """Open a PDF, DOCX, or image file for editing.

    Returns page count and dimensions of the first page.
    """
    global _state
    _state = DocumentState()
    pages = render_file(file_path)
    fmt = detect_format(file_path)
    _state.load_pages(pages, source_path=file_path, source_format=fmt)
    w, h = pages[0].size
    return f"Opened {Path(file_path).name}: {len(pages)} page(s), first page {w}x{h}px"


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


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
