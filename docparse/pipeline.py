"""공통 후처리: 반복 문구 제거 → 문단 합치기 → 제목 추출 → 읽는 순서 정렬."""
from __future__ import annotations

from typing import List, Optional

from . import tables
from .layout import analyze_wrap, estimate_right_edges, render_block, xy_order
from .model import Block, Document, OutBlock, PageOut
from .repeat import mark_repeats
from .textnorm import one_line
from .title import pick_title


def body_font_size(doc: Document) -> float:
    """문서 전체에서 글자 수 기준 가운데 크기 = 본문 글자 크기."""
    weighted = []
    for page in doc.pages:
        for b in page.blocks:
            if b.role == "removed":
                continue
            if b.kind == "table":
                # 표 안의 글도 본문이다. 빼면 표가 대부분인 문서에서 제목 글자가 본문 크기로 잡혀 제목을 못 찾는다.
                cells = getattr(b, "cell_lines", None)
                if cells is not None:
                    chars = sum(len(l.text) for row in cells for cell in row for l in cell)
                else:
                    chars = sum(len(c) for row in b.rows for c in row)
                if b.size > 0 and chars:
                    weighted.append((b.size, chars))
                continue
            if b.kind != "text":
                continue
            for l in b.lines:
                if l.size > 0 and not l.removed:
                    weighted.append((l.size, len(l.text)))
    if not weighted:
        return 12.0
    weighted.sort()
    half = sum(w for _, w in weighted) / 2.0
    acc = 0.0
    for size, w in weighted:
        acc += w
        if acc >= half:
            return size
    return weighted[-1][0]


def _norm_box(b: Block, page) -> tuple:
    w, h = max(page.width, 1.0), max(page.height, 1.0)
    clamp = lambda v: min(1.0, max(0.0, v))
    return (clamp(b.x0 / w), clamp(b.y0 / h), clamp(b.x1 / w), clamp(b.y1 / h))


def apply_rules(doc: Document, repeat_ratio: float = 0.6,
                extra_keywords=None, order_log: Optional[list] = None) -> List[PageOut]:
    """반복 문구 제거, 문단 합치기, 제목 추출, 읽는 순서 정렬을 차례로 적용한다.

    order_log에 목록을 주면 쪽마다 (쪽 번호, 순서를 정할 덩어리들, 본문 글자 크기)를 담아 준다.
    읽는 순서 기준값을 바꿔 가며 다시 정렬해 보는 시험(tune.py)에서 쓴다.
    """
    body = body_font_size(doc)
    mark_repeats(doc.pages, body, ratio=repeat_ratio, extra_keywords=extra_keywords)
    ctx = analyze_wrap(doc.pages)
    estimate_right_edges(doc.pages)
    outs: List[PageOut] = []
    for page in doc.pages:
        out = PageOut(number=page.number)
        live: List[Block] = []
        seen = set()
        for b in page.blocks:
            for l in b.lines:
                if l.removed and (l.text, l.removed) not in seen:
                    seen.add((l.text, l.removed))
                    out.removed.append((l.text, l.removed))
            if b.role == "removed":
                continue
            b.text = render_block(b, ctx)
            if b.text:
                live.append(b)

        title, reason = pick_title(live, page, body)
        out.title_reason = reason
        if title is not None:
            out.title = one_line(title.text)
            out.title_box = _norm_box(title, page)
        rest = [b for b in live if b is not title]
        # 돌려 쓴 글(축 제목, 옆면 주석)은 본문 흐름에 끼지 않도록 맨 뒤로 보낸다
        turned = [b for b in rest if b.lines and abs(b.lines[0].angle) >= 3.0]
        flat = [b for b in rest if not (b.lines and abs(b.lines[0].angle) >= 3.0)]
        if order_log is not None:
            order_log.append((page.number, flat, body))
        ordered = xy_order(flat, body) + sorted(turned, key=lambda b: (b.y0, b.x0))
        for b in ordered:
            ob = OutBlock(text=b.text, box=_norm_box(b, page), kind=b.kind)
            ob.over_table = b.kind == "text" and any(l.overlay for l in b.lines)
            if b.kind == "table":
                try:
                    info = tables.describe(b)
                except Exception:                  # 표 풀어 쓰기가 실패해도 기존 결과는 그대로 낸다
                    info = None
                if info is not None:
                    flat = info["flat"]
                    ob.flat, ob.flat_mode, ob.flat_reason = flat.text, flat.mode, flat.reason
                    ob.flat_lines = list(flat.lines)
                    ob.table = {"rows": info["rows"], "cols": info["cols"], "cells": info["cells"],
                                "head_rows": flat.head_rows, "label_cols": flat.label_cols}
            out.blocks.append(ob)
        outs.append(out)
    return outs
