"""PyMuPDF로 PDF 글자를 읽는다."""
from __future__ import annotations

import math
from typing import List

from .model import Document, Page
from .pdf_common import Ch, chars_to_blocks

try:
    import pymupdf
except ImportError:                                # 구버전은 fitz 라는 이름을 쓴다
    import fitz as pymupdf  # type: ignore

# PyMuPDF는 2.0부터 표 찾기(find_tables)에 내장 모델(onnxruntime)을 쓴다.
# 이 프로그램은 좌표 규칙만 쓰기로 했으므로 모델을 끄고, 그려진 선을 따라 표를 찾게 한다.
# 샘플에서는 결과가 같고 약 10배 빠르다. 1.x에는 이 스위치도 모델도 없어 아무 일도 하지 않는다.
MODEL_INSTALLED = False
try:
    _available = getattr(pymupdf, "_layout_available", None)
    MODEL_INSTALLED = bool(callable(_available) and _available())
    if hasattr(pymupdf, "_layout_enabled"):
        pymupdf._layout_enabled = False
except Exception:
    pass


def table_mode() -> str:
    """표를 어떻게 찾는지 리포트에 적을 말."""
    if MODEL_INSTALLED and getattr(pymupdf, "_layout_enabled", False):
        return "내장 모델 사용"
    return "선 규칙만 사용 (내장 모델은 %s)" % ("설치되어 있지만 끔" if MODEL_INSTALLED else "없음")


def _flags() -> int:
    base = getattr(pymupdf, "TEXTFLAGS_DICT", None)
    if base is None:
        return 0
    return base & ~getattr(pymupdf, "TEXT_PRESERVE_IMAGES", 0)


def page_images(path: str, width: int = 900) -> list:
    """리포트에 넣을 페이지 그림(JPEG). 추출 시간 측정과 분리하려고 따로 둔다."""
    out = []
    pdf = pymupdf.open(str(path))
    for page in pdf:
        try:
            zoom = width / max(page.rect.width, 1.0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            out.append(pix.tobytes("jpeg", jpg_quality=65))
        except Exception:
            out.append(None)
    pdf.close()
    return out


def page_count(path: str) -> int:
    pdf = pymupdf.open(str(path))
    n = len(pdf)
    pdf.close()
    return n


def read(path: str) -> Document:
    doc = Document(path=str(path), kind="pdf")
    pdf = pymupdf.open(str(path))
    doc.info["producer"] = (pdf.metadata or {}).get("producer", "")
    flags = _flags()
    for pno, page in enumerate(pdf, 1):
        rect = page.rect
        out = Page(number=pno, width=rect.width, height=rect.height)
        out.before = page.get_text()
        try:                                       # PyMuPDF가 한 덩어리로 묶어 준 단위(블록)와 그 위치
            pw, ph = max(rect.width, 1.0), max(rect.height, 1.0)
            for b in page.get_text("blocks"):
                if (len(b) < 7 or b[6] == 0) and b[4].strip():
                    out.before_units.append(b[4].rstrip("\n"))
                    out.before_boxes.append((b[0] / pw, b[1] / ph, b[2] / pw, b[3] / ph))
        except Exception:
            out.before_units, out.before_boxes = [], []

        chars: List[Ch] = []
        raw = page.get_text("rawdict", flags=flags) if flags else page.get_text("rawdict")
        for block in raw.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            for line in block.get("lines", []):
                dx, dy = line.get("dir", (1.0, 0.0))
                angle = math.degrees(math.atan2(dy, dx))
                for span in line.get("spans", []):
                    size = span.get("size", 0.0)
                    font = span.get("font", "")
                    bold = bool(span.get("flags", 0) & 16)
                    for ch in span.get("chars", []):
                        x0, y0, x1, y1 = ch["bbox"]
                        ox, oy = ch.get("origin", (x0, y1))
                        chars.append(Ch(ch["c"], x0, y0, x1, y1, ox, oy, size, font, bold, angle))

        tables = []
        try:
            for tb in page.find_tables().tables:
                cells = [[tuple(c) if c else None for c in row.cells] for row in tb.rows]
                tables.append({"bbox": tuple(tb.bbox), "cells": cells})
        except Exception:                          # 표 찾기 실패는 치명적이지 않다
            pass

        rects = []
        try:
            drawings = page.get_drawings()
            if len(drawings) <= 5000:
                for d in drawings:
                    r = d.get("rect")
                    if r is not None and (d.get("fill") is not None or d.get("color") is not None):
                        rects.append((r.x0, r.y0, r.x1, r.y1))
        except Exception:
            pass

        out.chars = chars                          # type: ignore[attr-defined]  결합 방식에서 다시 쓴다
        out.native_tables = tables                 # type: ignore[attr-defined]
        out.rects = rects                          # type: ignore[attr-defined]
        out.blocks = chars_to_blocks(chars, tables, rects, rect.width, rect.height)
        doc.pages.append(out)
    pdf.close()
    return doc
