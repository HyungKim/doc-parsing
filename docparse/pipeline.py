"""공통 후처리: 반복 문구 제거 → 문단 합치기 → 제목 추출 → 읽는 순서 정렬."""
from __future__ import annotations

import re
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


HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
MIN_CHARS = 5         # 띄어쓰기를 포함해 이 글자 수 이하인 줄은 출력에서 뺀다 (0이면 빼지 않는다)


def drop_reason(text: str, min_chars: int = MIN_CHARS, need_korean: bool = True) -> str:
    """이 줄을 출력에서 뺄 이유. 빼지 않을 줄이면 빈 글."""
    t = text.strip()
    if need_korean and not HANGUL.search(t):
        return "한글이 없는 줄"
    if min_chars and len(t) <= min_chars:
        return "%d자 이하의 짧은 줄" % min_chars
    return ""


def _span_box(lines, page) -> tuple:
    """여러 줄이 차지한 자리(쪽 크기 대비 0~1)."""
    w, h = max(page.width, 1.0), max(page.height, 1.0)
    clamp = lambda v: min(1.0, max(0.0, v))
    return (clamp(min(l.x0 for l in lines) / w), clamp(min(l.y0 for l in lines) / h),
            clamp(max(l.x1 for l in lines) / w), clamp(max(l.y1 for l in lines) / h))


def _norm_box(b: Block, page) -> tuple:
    w, h = max(page.width, 1.0), max(page.height, 1.0)
    clamp = lambda v: min(1.0, max(0.0, v))
    return (clamp(b.x0 / w), clamp(b.y0 / h), clamp(b.x1 / w), clamp(b.y1 / h))


def apply_rules(doc: Document, repeat_ratio: float = 0.6,
                extra_keywords=None, order_log: Optional[list] = None,
                min_chars: int = MIN_CHARS, need_korean: bool = True) -> List[PageOut]:
    """반복 문구 제거, 문단 합치기, 제목 추출, 줄 거르기, 읽는 순서 정렬을 차례로 적용한다.

    줄 거르기: 한글이 하나도 없는 줄(need_korean)과 min_chars자 이하의 짧은 줄을 출력에서 뺀다.
    제목과 표 안의 줄은 거르지 않는다(짧은 제목이 많고, 표의 행을 빼면 표가 깨진다). 한글이 전혀 없는 표는 통째로 뺀다.
    뺀 줄은 쪽마다 removed(문구와 이유)와 removed_boxes(자리)에 남긴다.

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
                if l.removed:
                    out.removed_boxes.append((_span_box([l], page), l.removed, l.text))
                if l.removed and (l.text, l.removed) not in seen:
                    seen.add((l.text, l.removed))
                    out.removed.append((l.text, l.removed))
            if b.role == "removed":
                continue
            b.line_groups = []                     # type: ignore[attr-defined]  적힌 줄마다 그 줄을 이룬 원래 줄들
            b.text = render_block(b, ctx, b.line_groups if b.kind == "text" else None)
            if b.text:
                live.append(b)

        title, reason = pick_title(live, page, body)
        out.title_reason = reason
        if title is not None:
            out.title = one_line(title.text)
            out.title_box = _norm_box(title, page)
        rest = [b for b in live if b is not title]
        # 줄 거르기: 한글이 없는 줄과 짧은 줄을 뺀다. 무엇을 어디서 뺐는지는 남긴다
        if need_korean or min_chars:
            for b in rest:
                if b.kind == "table":
                    if need_korean and not HANGUL.search(b.text):
                        out.removed.append((b.text, "한글이 없는 표"))
                        out.removed_boxes.append((_norm_box(b, page), "한글이 없는 표", one_line(b.text)))
                        b.text = ""
                    continue
                texts = b.text.split("\n")
                groups = getattr(b, "line_groups", None) or []
                keep = []
                for k, t in enumerate(texts):
                    why = drop_reason(t, min_chars, need_korean)
                    if not why:
                        keep.append(t)
                        continue
                    out.removed.append((t, why))
                    box = _span_box(groups[k], page) if len(groups) == len(texts) else _norm_box(b, page)
                    out.removed_boxes.append((box, why, t))
                b.text = "\n".join(keep)
            rest = [b for b in rest if b.text]
        # 돌려 쓴 글(축 제목, 옆면 주석)은 본문 흐름에 끼지 않도록 맨 뒤로 보낸다
        turned = [b for b in rest if b.lines and abs(b.lines[0].angle) >= 3.0]
        flat = [b for b in rest if not (b.lines and abs(b.lines[0].angle) >= 3.0)]
        if order_log is not None:
            order_log.append((page.number, flat, body))
        ordered = xy_order(flat, body) + sorted(turned, key=lambda b: (b.y0, b.x0))
        for b in ordered:
            ob = OutBlock(text=b.text, box=_norm_box(b, page), kind=b.kind)
            ob.over_table = b.kind == "text" and any(l.overlay for l in b.lines)
            ob.style_breaks = sum(1 for l in b.lines if l.style_break and not l.removed) if b.kind == "text" else 0
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
