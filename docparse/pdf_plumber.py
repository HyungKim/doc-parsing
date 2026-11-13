"""pdfplumber로 PDF 글자를 읽는다."""
from __future__ import annotations

import math
from typing import List

import pdfplumber

from .model import Document, Page
from .pdf_common import BOLD_FONT, Ch, chars_to_blocks


def _font_size(c: dict, m) -> float:
    """쪽 위에서의 글자 크기(pt).

    pdfminer의 matrix에는 글꼴 크기(Tf)가 들어 있지 않다. Mac(Quartz)이 만든 PDF는
    크기를 행렬 배율에 싣지만 Windows Office가 만든 PDF는 Tf에 실어서, 행렬 배율만 보면
    모든 글자가 1pt로 보인다. 글자 상자의 높이(= 글꼴 크기 × 배율)에서 구해야 두 경우 모두 맞다.
    """
    a, b = float(m[0]), float(m[1])
    scale = math.hypot(a, b)
    h = float(c.get("height") or 0.0)
    w = float(c.get("width") or 0.0)
    flat = float(c.get("size") or h)               # 눕지 않은 글자는 이것이 곧 글자 크기
    if scale <= 0:
        return flat
    cos, sin = abs(a) / scale, abs(b) / scale
    if sin < 0.26:                                 # 거의 수평
        return flat
    if cos < 0.26:                                 # 거의 수직: 상자의 가로가 글자 크기
        return w or flat
    # 비스듬한 글자: 상자에 글자 폭(adv)이 섞여 있어 그만큼 덜어 낸다.
    # 방향에 따라 pdfminer 버전과 무관하게 성립하는 변이 다르다.
    adv = float(c.get("adv") or 0.0) * scale
    est = (h - adv * sin) / cos if a * b > 0 else (w - adv * cos) / sin
    if 0.2 * min(w, h) <= est <= max(w, h):
        return est
    return min(w, h) or flat


def read(path: str) -> Document:
    doc = Document(path=str(path), kind="pdf")
    with pdfplumber.open(str(path)) as pdf:
        doc.info["producer"] = str((pdf.metadata or {}).get("Producer", ""))
        for pno, page in enumerate(pdf.pages, 1):
            out = Page(number=pno, width=float(page.width), height=float(page.height))
            # pdfplumber는 덩어리 정보 없이 줄 단위로만 준다. 줄마다 글과 위치를 함께 받는다.
            try:
                pw, ph = max(out.width, 1.0), max(out.height, 1.0)
                for ln in page.extract_text_lines():
                    text = ln.get("text") or ""
                    if not text.strip():
                        continue
                    out.before_units.append(text)
                    out.before_boxes.append((float(ln["x0"]) / pw, float(ln["top"]) / ph,
                                             float(ln["x1"]) / pw, float(ln["bottom"]) / ph))
                out.before = "\n".join(out.before_units)
            except Exception:                      # 줄 위치를 못 받으면 글만 남긴다
                try:
                    out.before = page.extract_text() or ""
                except Exception:
                    out.before = ""
                out.before_units = [line for line in out.before.split("\n") if line.strip()]
                out.before_boxes = []

            chars: List[Ch] = []
            height = float(page.height)
            for c in page.chars:
                m = c.get("matrix") or (1, 0, 0, 1, c["x0"], 0)
                a, b = float(m[0]), float(m[1])
                angle = math.degrees(math.atan2(-b, a))        # PDF는 y축이 위쪽이라 부호를 뒤집는다
                size = _font_size(c, m)
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
