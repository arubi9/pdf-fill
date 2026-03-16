"""Surya OCR and layout analysis wrappers. Requires surya-ocr optional dependency."""

from __future__ import annotations

from PIL import Image

# Lazy-load Surya to avoid import errors when not installed
_foundation_predictor = None
_recognition_predictor = None
_detection_predictor = None
_layout_predictor = None
_table_rec_predictor = None


def _ensure_ocr_predictors():
    global _foundation_predictor, _recognition_predictor, _detection_predictor
    if _recognition_predictor is None:
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor
        from surya.detection import DetectionPredictor
        _foundation_predictor = FoundationPredictor()
        _recognition_predictor = RecognitionPredictor(_foundation_predictor)
        _detection_predictor = DetectionPredictor()


def _ensure_layout_predictor():
    global _layout_predictor
    if _layout_predictor is None:
        from surya.layout import LayoutPredictor
        _layout_predictor = LayoutPredictor()


def _ensure_table_predictor():
    global _table_rec_predictor
    if _table_rec_predictor is None:
        from surya.table_rec import TableRecPredictor
        _table_rec_predictor = TableRecPredictor()


def ocr_page(img: Image.Image) -> list[dict]:
    """Run OCR on an image. Returns list of {text, bbox, confidence}."""
    _ensure_ocr_predictors()
    predictions = _recognition_predictor([img], det_predictor=_detection_predictor)
    results = []
    if predictions and hasattr(predictions[0], "text_lines"):
        for line in predictions[0].text_lines:
            results.append({
                "text": line.text,
                "bbox": list(line.bbox),
                "confidence": line.confidence,
            })
    return results


def analyze_layout(img: Image.Image) -> list[dict]:
    """Run layout detection. Returns list of {label, bbox, confidence}."""
    _ensure_layout_predictor()
    predictions = _layout_predictor([img])
    results = []
    if predictions:
        for item in predictions[0]:
            results.append({
                "label": getattr(item, "label", "unknown"),
                "bbox": list(getattr(item, "bbox", [])),
                "confidence": getattr(item, "confidence", 0),
            })
    return results


def analyze_tables(img: Image.Image) -> list[dict]:
    """Run table recognition. Returns table structures with cell bboxes."""
    _ensure_table_predictor()
    predictions = _table_rec_predictor([img])
    results = []
    if predictions:
        for table in predictions:
            results.append({
                "cells": [
                    {
                        "bbox": list(getattr(cell, "bbox", [])),
                        "row": getattr(cell, "row", 0),
                        "col": getattr(cell, "col", 0),
                        "text": getattr(cell, "text", ""),
                    }
                    for cell in getattr(table, "cells", [])
                ]
            })
    return results
