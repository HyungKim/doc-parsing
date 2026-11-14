"""pdfplumber로 PDF 글자를 읽는다. 쪽 그림도 pdfplumber(안에서 pypdfium2를 씀)로 그린다."""
from __future__ import annotations

import io
import math
from typing import List

import pdfplumber

from .model import Document, Page
from .pdf_common import BOLD_FONT, Ch, chars_to_blocks


def page_images(path: str, width: int = 900, only=None) -> list:
    """리포트에 넣을 쪽 그림(JPEG). 추출 시간 측정과 분리하려고 따로 둔다.

    only에 쪽 번호(1부터) 모음을 주면 그 쪽만 그리고 나머지 자리는 None으로 둔다.
    """
    out = []
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            if only is not None and pno not in only:
                out.append(None)
                continue
            try:
                img = page.to_image(width=width, antialias=True).original
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="JPEG", quality=65)
                out.append(buf.getvalue())
            except Exception:                      # 그림은 참고용이라 못 그려도 넘어간다
                out.append(None)
    return out


def page_count(path: str) -> int:
    with pdfplumber.open(str(path)) as pdf:
        return len(pdf.pages)


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


def _color(value):
    """글자색을 서로 같은지 비교할 수 있는 값으로 바꾼다. 색 공간에 따라 숫자가 1개(회색), 3개(RGB), 4개(CMYK)로 온다."""
    if value is None:
        return None
    try:
        if isinstance(value, (list, tuple)):
            return tuple(round(float(v), 3) for v in value)
        return (round(float(value), 3),)
    except (TypeError, ValueError):
        return str(value)


RULE_MIN = 20.0       # 이보다 짧은 가로선은 표의 선으로 보지 않는다(pt)
END_TOLERANCE = 2.0   # 가로선들의 끝이 이 거리 안이면 같은 자리에서 끝난 것으로 본다(pt)


def _merge_spans(spans: list, tol: float = 2.0) -> list:
    out: list = []
    for a, b in sorted(spans):
        if out and a <= out[-1][1] + tol:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def open_side_lines(page) -> list:
    """양옆이 트인 표(바깥 세로선이 없는 표)를 위해, 가로선들이 끝나는 자리에 세로선을 보태 준다.

    pdfplumber는 선이 사방으로 닫힌 곳만 칸으로 본다. 보고서에 흔한 '양옆이 트인 표'는 맨 왼쪽 열과
    맨 오른쪽 열이 닫히지 않아, 칸에 바탕색도 없으면 그 열의 글이 표에서 빠져 따로 뽑힌다.
    가로선 여러 개가 같은 자리에서 끝나고, 그 안쪽에 세로선이 있는 높이 구간(= 열이 나뉜 표)에 한해
    그 끝자리에 세로선이 있는 것으로 쳐 준다. 이미 선이 있으면 보태지 않는다.
    반환: pdfplumber의 explicit_vertical_lines에 넘길 선 목록
    """
    try:
        edges = page.edges
    except Exception:
        return []
    # 표의 선은 직선이나 사각형으로 그려진다. 둥근 도형(말풍선 등)의 윤곽은 표의 선으로 보지 않는다.
    hs = [e for e in edges if e.get("orientation") == "h" and e["x1"] - e["x0"] >= RULE_MIN
          and e.get("object_type") != "curve_edge"]
    vs = [e for e in edges if e.get("orientation") == "v" and e["bottom"] - e["top"] > 1.0]
    straight = [v for v in vs if v.get("object_type") != "curve_edge"]
    if len(hs) < 2 or not straight:
        return []
    out = []
    for key in ("x0", "x1"):
        groups: list = []
        for e in sorted(hs, key=lambda e: e[key]):
            if groups and e[key] - groups[-1][-1][key] <= END_TOLERANCE:
                groups[-1].append(e)
            else:
                groups.append([e])
        for g in groups:
            tops = sorted({round(e["top"], 1) for e in g})
            if len(tops) < 2:
                continue
            x = sorted(e[key] for e in g)[len(g) // 2]
            lo, hi = min(e["x0"] for e in g), max(e["x1"] for e in g)
            inner = [(v["top"], v["bottom"]) for v in straight
                     if lo + 3.0 < v["x0"] < hi - 3.0 and v["bottom"] > tops[0] - 2.0 and v["top"] < tops[-1] + 2.0]
            for a, b in _merge_spans(inner):
                inside = [t for t in tops if a - 3.0 <= t <= b + 3.0]
                if len(inside) < 2:
                    continue
                top, bottom = inside[0], inside[-1]
                if any(e["x0"] < x - 3.0 and e["x1"] > x + 3.0 and top - 1.0 <= e["top"] <= bottom + 1.0 for e in hs):
                    continue                       # 다른 가로선이 이 자리를 지나간다. 표의 바깥 끝이 아니라 표 안에 놓인 도형이다
                have = _merge_spans([(max(v["top"], top), min(v["bottom"], bottom)) for v in vs
                                     if abs(v["x0"] - x) <= 3.0 and v["bottom"] > top and v["top"] < bottom])
                if sum(q - p for p, q in have) >= 0.9 * (bottom - top):
                    continue                       # 그 자리에 이미 세로선이 있다
                out.append({"object_type": "line", "x0": x, "x1": x, "top": top, "bottom": bottom,
                            "width": 0.0, "height": bottom - top})
    return out


def find_page_tables(page) -> list:
    """쪽에서 표를 찾아 [{"bbox", "cells"}]로 돌려준다. 양옆이 트인 표는 세로선을 보태서 찾는다."""
    tables = []
    try:
        extra = open_side_lines(page)
        for tb in (page.find_tables({"explicit_vertical_lines": extra}) if extra else page.find_tables()):
            cells = [[tuple(cell) if cell else None for cell in row.cells] for row in tb.rows]
            tables.append({"bbox": tuple(tb.bbox), "cells": cells})
    except Exception:                              # 표 찾기 실패는 치명적이지 않다
        pass
    return tables


def _shape_key(o: dict) -> tuple:
    return (round(float(o["x0"])), round(float(o["top"])), round(float(o["x1"])), round(float(o["bottom"])))


def overlay_boxes(page, chars: List[Ch], tables: list) -> set:
    """표 위에 얹힌 글을 감싼 상자(코멘트 상자의 테두리나 바탕)를 찾는다.

    이런 상자의 선은 표의 선과 만나 칸을 더 잘게 쪼갠다. 칸 구분 모양은 그대로 보여도
    칸 구조가 틀려져 풀어 쓴 모양이 엉뚱해지므로, 표를 찾을 때 이 상자는 빼야 한다.
    조건: 표 안에 놓였고, 떼어 낸 글(Ch.over)을 품고 있으며, 네 변 가운데 다른 선과 겹치는 변이
    하나 이하다(표의 칸 바탕은 이웃 칸이나 테두리선과 변을 함께 쓰므로 여기서 걸러진다).
    반환: 뺄 도형의 위치 값(_shape_key) 집합
    """
    lifted = [c for c in chars if c.over]
    if not lifted or not tables:
        return set()
    try:
        shapes = list(page.rects) + list(page.curves)
        straight = list(page.rects) + list(page.lines)
    except Exception:
        return set()
    if len(shapes) > 5000:
        return set()
    page_area = max(float(page.width) * float(page.height), 1.0)
    sides = []                                     # (도형 위치 값, 방향, 놓인 자리, 시작, 끝)
    for o in straight:
        k = _shape_key(o)
        x0, y0, x1, y1 = float(o["x0"]), float(o["top"]), float(o["x1"]), float(o["bottom"])
        if x1 - x0 >= 2.0:
            sides += [(k, "h", y0, x0, x1), (k, "h", y1, x0, x1)]
        if y1 - y0 >= 2.0:
            sides += [(k, "v", x0, y0, y1), (k, "v", x1, y0, y1)]

    def shared(k: tuple, way: str, at: float, a: float, b: float) -> bool:
        for k2, way2, at2, a2, b2 in sides:
            if k2 != k and way2 == way and abs(at2 - at) <= 1.5 and min(b, b2) - max(a, a2) >= 0.5 * min(b - a, b2 - a2):
                return True
        return False

    drop = set()
    for o in shapes:
        k = _shape_key(o)
        if k in drop:
            continue
        x0, y0, x1, y1 = float(o["x0"]), float(o["top"]), float(o["x1"]), float(o["bottom"])
        w, h = x1 - x0, y1 - y0
        if w < 12.0 or h < 8.0 or w * h > 0.5 * page_area:
            continue
        if not any(x0 - 2.0 <= (c.x0 + c.x1) / 2 <= x1 + 2.0 and y0 - 2.0 <= (c.y0 + c.y1) / 2 <= y1 + 2.0 for c in lifted):
            continue
        over_table = False
        for t in tables:
            tx0, ty0, tx1, ty1 = t["bbox"]
            cover = max(0.0, min(x1, tx1) - max(x0, tx0)) * max(0.0, min(y1, ty1) - max(y0, ty0))
            if cover >= 0.5 * w * h and w * h <= 0.6 * (tx1 - tx0) * (ty1 - ty0):
                over_table = True
                break
        if not over_table:
            continue
        common = sum([shared(k, "h", y0, x0, x1), shared(k, "h", y1, x0, x1), shared(k, "v", x0, y0, y1), shared(k, "v", x1, y0, y1)])
        if common <= 1:
            drop.add(k)
    return drop


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
                                bool(BOLD_FONT.search(font)), angle, _color(c.get("non_stroking_color"))))

            tables = find_page_tables(page)

            rects = []
            try:
                shapes = list(page.rects) + list(page.curves)
                if len(shapes) <= 5000:
                    for r in shapes:
                        rects.append((float(r["x0"]), float(r["top"]), float(r["x1"]), float(r["bottom"])))
            except Exception:
                pass
            out.blocks = chars_to_blocks(chars, tables, rects, out.width, out.height)

            # 표 위에 얹힌 상자가 표의 칸을 쪼갰으면, 그 상자를 빼고 표를 다시 찾는다
            boxes = overlay_boxes(page, chars, tables)
            if boxes:
                try:
                    clean = page.filter(lambda o: not (o.get("object_type") in ("rect", "curve") and _shape_key(o) in boxes))
                    again = find_page_tables(clean)
                except Exception:
                    again = []
                if again:
                    before = [c.over for c in chars]
                    for c in chars:
                        c.over = False
                    blocks = chars_to_blocks(chars, again, rects, out.width, out.height)
                    if any(c.over for c in chars):     # 다시 찾은 표에서도 얹힌 글이 가려졌을 때만 바꾼다
                        out.blocks = blocks
                    else:
                        for c, flag in zip(chars, before):
                            c.over = flag
            doc.pages.append(out)
    return doc
