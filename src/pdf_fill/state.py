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
        self._structure_cache: dict[int, list[dict]] = {}

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
        self._structure_cache = {}
        if page_dimensions is not None:
            self.page_dimensions = list(page_dimensions)
        else:
            self.page_dimensions = [
                (float(p.width), float(p.height)) for p in pages
            ]

    def get_page(self, page_num: int | None = None) -> Image.Image:
        """Get the current (or specified) page image."""
        idx = page_num if page_num is not None else self._current_page
        if idx is None or idx < 0 or idx >= len(self._pages):
            raise IndexError(f"Invalid page number: {idx}")
        return self._pages[idx]

    def set_page(self, img: Image.Image, page_num: int | None = None) -> None:
        """Replace the current (or specified) page image."""
        idx = page_num if page_num is not None else self._current_page
        if idx is None or idx < 0 or idx >= len(self._pages):
            raise IndexError(f"Invalid page number: {idx}")
        self._pages[idx] = img
        self._structure_cache.pop(idx, None)

    def save_snapshot(self, page_num: int | None = None) -> None:
        """Save current page state to undo stack before an edit."""
        idx = page_num if page_num is not None else self._current_page
        if idx is None:
            return
        self._undo_stacks[idx].append(self._pages[idx].copy())

    def undo(self, page_num: int | None = None) -> bool:
        """Restore the previous page state. Returns False if nothing to undo."""
        idx = page_num if page_num is not None else self._current_page
        if idx is None or not self._undo_stacks[idx]:
            return False
        self._pages[idx] = self._undo_stacks[idx].pop()
        self._structure_cache.pop(idx, None)
        return True

    def go_to_page(self, page_num: int) -> None:
        """Switch to a different page."""
        if page_num < 0 or page_num >= len(self._pages):
            raise IndexError(f"Invalid page number: {page_num}")
        self._current_page = page_num

    def get_all_pages(self) -> list[Image.Image]:
        """Return all pages."""
        return list(self._pages)

    def get_structure(self, page_num: int) -> list[dict] | None:
        """Return cached structure for a page, or None if not cached."""
        return self._structure_cache.get(page_num)

    def set_structure(self, page_num: int, structure: list[dict]) -> None:
        """Cache structure analysis results for a page."""
        self._structure_cache[page_num] = structure
