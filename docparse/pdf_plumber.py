"""pdfplumber로 PDF 글자를 읽는다."""
from __future__ import annotations

import math
from typing import List

import pdfplumber

from .model import Document, Page
from .pdf_common import BOLD_FONT, Ch, chars_to_blocks


def read(path: str) -> Document:
    doc = Document(path=str(path), kind="pdf")
    with pdfplumber.open(str(path)) as pdf:
        doc.info["producer"] = str((pdf.metadata or {}).get("Producer", ""))
        for pno, page in enumerate(pdf.pages, 1):
            out = Page(number=pno, width=float(page.width), height=float(page.height))
            try:
                out.before = page.extract_text() or ""
            except Exception:
                out.before = ""

            chars: List[Ch] = []
            height = float(page.height)
            for c in page.chars:
                m = c.get("matrix") or (1, 0, 0, 1, c["x0"], 0)
                a, b = float(m[0]), float(m[1])
                angle = math.degrees(math.atan2(-b, a))        # PDF는 y축이 위쪽이라 부호를 뒤집는다
                size = math.hypot(a, b) or float(c.get("size") or 0.0)
                font = c.get("fontname") or ""
                x0, x1 = float(c["x0"]), float(c["x1"])
                y0, y1 = float(c["top"]), float(c["bottom"])
                upright = abs(angle) < 3.0
                ox = x0 if upright else float(m[4])
                oy = (height - float(m[5])) if len(m) > 5 else y1
                if upright and not (y0 - size <= oy <= y1 + size):
                    oy = y1                                    # 기준점이 어긋난 PDF 대비
                chars.append(Ch(c.get("text", ""), x0, y0, x1, y1, ox, oy, size, font,
                                bool(BOLD_FONT.search(font)), angle))

            tables = []
            try:
                for tb in page.find_tables():
                    cells = [[tuple(cell) if cell else None for cell in row.cells] for row in tb.rows]
                    tables.append({"bbox": tuple(tb.bbox), "cells": cells})
            except Exception:
                pass

            rects = []
            try:
                shapes = list(page.rects) + list(page.curves)
                if len(shapes) <= 5000:
                    for r in shapes:
                        rects.append((float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"])))
            except Exception:
                pass
            out.blocks = chars_to_blocks(chars, tables, rects, out.width, out.height)
            doc.pages.append(out)
    return doc
