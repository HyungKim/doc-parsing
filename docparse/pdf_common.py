"""PDF 공통 처리: 글자 → 줄 → 블록.

PyMuPDF와 pdfplumber는 글자(문자, 좌표, 글꼴)만 뽑아 주고,
줄과 블록으로 묶는 규칙은 여기 한 곳에서 처리한다.
그래야 두 라이브러리의 차이가 '글자를 얼마나 정확히 뽑는가'로만 드러난다.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import List, Optional, Sequence

from .model import Block, Line
from .textnorm import clean, has_bullet, has_marker, is_bullet_only, is_marker_only, strip_bullet

SYMBOL_FONT = re.compile(r"wingdings|webdings|symbol|dingbats|marlett", re.I)
BOLD_FONT = re.compile(r"bold|black|heavy|[-_,]bd\b|semibold|demi", re.I)

SPACE_GAP = 0.15      # 글자 사이 간격이 글자 크기의 이 비율을 넘으면 띄어쓰기로 본다
SPLIT_GAP = 1.0       # 이 비율을 넘으면 서로 다른 덩어리(다른 단, 다른 칸)로 나눈다
MARKER_GAP = 3.0      # 글머리 기호/번호 뒤의 간격은 이만큼까지 같은 줄로 본다


class Ch:
    __slots__ = ("c", "x0", "y0", "x1", "y1", "ox", "oy", "size", "font", "bold", "angle")

    def __init__(self, c, x0, y0, x1, y1, ox, oy, size, font, bold, angle):
        self.c = c
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.ox = ox          # 글자 기준점(베이스라인 시작)
        self.oy = oy
        self.size = size
        self.font = font
        self.bold = bold
        self.angle = angle    # 도. 화면 기준 시계 방향이 +


def _dominant(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return Counter(round(v, 1) for v in values).most_common(1)[0][0]


def _segment_to_line(seg: List[Ch]) -> Optional[Line]:
    list_start = False
    # 기호 글꼴로 찍힌 글머리 기호(Wingdings의 l, n, ü 등)는 버린다
    while seg and (seg[0].c.isspace() or SYMBOL_FONT.search(seg[0].font or "")):
        if not seg[0].c.isspace():
            list_start = True
        seg = seg[1:]
    if not seg:
        return None

    parts: List[str] = []
    word_breaks: List[int] = []           # 띄어쓰기가 생긴 글자 위치
    for i, c in enumerate(seg):
        if i:
            p = seg[i - 1]
            gap = c.x0 - p.x1
            if gap > SPACE_GAP * max(p.size, c.size) and not p.c.isspace() and not c.c.isspace():
                parts.append(" ")
                word_breaks.append(i)
        if c.c.isspace():
            word_breaks.append(i)
        parts.append(c.c)
    raw = "".join(parts)
    trailing = raw[-1:].isspace()
    text = clean(raw)

    start = 0                              # 내용이 시작되는 글자 위치
    if has_bullet(text):
        list_start = True
        text = strip_bullet(text)
        start = 1
        while start < len(seg) and seg[start].c.isspace():
            start += 1
    elif has_marker(text):
        list_start = True
    if not text or is_bullet_only(text):
        return None
    body = seg[start:] if start < len(seg) else seg

    end = len(seg)
    for i in word_breaks:
        if i > start:
            end = i
            break
    first = body[0]
    last_of_word = seg[end - 1] if end - 1 >= start else first
    return Line(
        text=text,
        x0=first.x0,
        y0=min(c.y0 for c in body),
        x1=max(c.x1 for c in body if not c.c.isspace()) if any(not c.c.isspace() for c in body) else body[-1].x1,
        y1=max(c.y1 for c in body),
        size=_dominant([c.size for c in body if not c.c.isspace()] or [first.size]),
        bold=sum(1 for c in body if c.bold) * 2 > len(body),
        list_start=list_start,
        trailing_space=trailing,
        first_word_w=max(0.0, last_of_word.x1 - first.x0),
        first_char_w=max(0.0, first.x1 - first.x0),
    )


def _marker_like(seg: List[Ch]) -> bool:
    if len(seg) > 5:
        return False
    if SYMBOL_FONT.search(seg[0].font or ""):
        return True
    t = clean("".join(c.c for c in seg))
    return is_bullet_only(t) or is_marker_only(t)


def _upright_lines(chars: List[Ch]) -> List[Line]:
    chars = sorted(chars, key=lambda c: (c.oy, c.x0))
    rows: List[List[Ch]] = []
    base = size = 0.0
    for c in chars:
        if not rows or c.oy - base > max(1.0, 0.25 * min(size, c.size)):
            rows.append([])
            base, size = c.oy, c.size
        rows[-1].append(c)

    lines: List[Line] = []
    for row in rows:
        row.sort(key=lambda c: c.x0)
        seg: List[Ch] = []
        for c in row:
            if seg:
                p = seg[-1]
                w = max(c.x1 - c.x0, 0.1)
                if c.c == p.c and not c.c.isspace() and abs(c.x0 - p.x0) < 0.35 * w:
                    continue                       # 그림자 등으로 겹쳐 찍힌 같은 글자
                limit = (MARKER_GAP if _marker_like(seg) else SPLIT_GAP) * max(p.size, c.size)
                if c.x0 - p.x1 > limit:
                    line = _segment_to_line(seg)
                    if line:
                        lines.append(line)
                    seg = []
            seg.append(c)
        line = _segment_to_line(seg)
        if line:
            lines.append(line)
    return lines


def _rotated_lines(chars: List[Ch]) -> List[Line]:
    """기울어진 글자(워터마크, 세로 축 제목 등)를 줄로 묶는다."""
    lines: List[Line] = []
    groups = {}
    for c in chars:
        groups.setdefault(int(round(c.angle / 5.0)) * 5, []).append(c)
    for angle, cs in groups.items():
        rad = math.radians(angle)
        dx, dy = math.cos(rad), math.sin(rad)
        keyed = [(-c.ox * dy + c.oy * dx, c.ox * dx + c.oy * dy, c) for c in cs]
        keyed.sort(key=lambda t: (t[0], t[1]))
        rows: List[list] = []
        for perp, along, c in keyed:
            if not rows or perp - rows[-1][0][0] > 0.6 * c.size:
                rows.append([])
            rows[-1].append((perp, along, c))
        for row in rows:
            row.sort(key=lambda t: t[1])
            steps = sorted(b[1] - a[1] for a, b in zip(row, row[1:]))
            med = steps[len(steps) // 2] if steps else 0.0
            upright_turn = abs(abs(angle) - 90) < 5       # 정확히 세로로 돌린 글자는 글자 높이가 곧 진행 폭
            parts = []
            for i, (_, along, c) in enumerate(row):
                if i:
                    prev = row[i - 1][2]
                    step = along - row[i - 1][1]
                    if upright_turn:
                        gap = step - (prev.y1 - prev.y0)
                        if gap > SPACE_GAP * max(prev.size, c.size) and not prev.c.isspace() and not c.c.isspace():
                            parts.append(" ")
                    elif med > 0 and step > 1.8 * med and len(row) > 3:
                        parts.append(" ")
                parts.append(c.c)
            text = clean("".join(parts))
            if not text:
                continue
            only = [t[2] for t in row]
            lines.append(Line(
                text=text,
                x0=min(c.x0 for c in only), y0=min(c.y0 for c in only),
                x1=max(c.x1 for c in only), y1=max(c.y1 for c in only),
                size=_dominant([c.size for c in only]),
                bold=sum(1 for c in only if c.bold) * 2 > len(only),
                angle=float(angle), is_para=True,
            ))
    return lines


def build_lines(chars: List[Ch]) -> List[Line]:
    upright = [c for c in chars if abs(c.angle) < 3.0]
    rotated = [c for c in chars if abs(c.angle) >= 3.0]
    return _upright_lines(upright) + _rotated_lines(rotated)


def _x_overlap(a: Line, b: Line) -> float:
    return min(a.x1, b.x1) - max(a.x0, b.x0)


def group_blocks(lines: List[Line]) -> List[Block]:
    """세로로 붙어 있고 가로로 겹치는 줄들을 한 블록(문단 묶음)으로 합친다."""
    flat = [l for l in lines if abs(l.angle) < 3.0]
    tilted = [l for l in lines if abs(l.angle) >= 3.0]
    flat.sort(key=lambda l: (l.y0, l.x0))
    n = len(flat)
    below = [[] for _ in range(n)]
    above = [[] for _ in range(n)]
    for i in range(n):
        a = flat[i]
        ah = max(a.y1 - a.y0, 1.0)
        for j in range(i + 1, n):
            b = flat[j]
            big = max(a.size, b.size, 1.0)
            if b.y0 - a.y1 > 0.45 * big:
                if b.y0 - a.y1 > 2 * big:
                    break
                continue
            if b.y0 < a.y0 + 0.5 * ah:
                continue                           # 같은 줄에 나란히 있는 덩어리
            if max(a.size, b.size) > 1.6 * max(min(a.size, b.size), 0.1):
                continue
            if _x_overlap(a, b) < 0.5 * min(a.x1 - a.x0, b.x1 - b.x0):
                continue
            below[i].append(j)
            above[j].append(i)

    def nearest_row(i: int, cands: List[int], up: bool) -> List[int]:
        if not cands:
            return []
        if up:
            edge = max(flat[k].y1 for k in cands)
            return [k for k in cands if flat[k].y1 > edge - 0.5 * max(flat[k].y1 - flat[k].y0, 1.0)]
        edge = min(flat[k].y0 for k in cands)
        return [k for k in cands if flat[k].y0 < edge + 0.5 * max(flat[k].y1 - flat[k].y0, 1.0)]

    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        downs = nearest_row(i, below[i], up=False)
        if len(downs) != 1:
            continue                               # 아래에 여러 단이 나란히 있으면 합치지 않는다
        j = downs[0]
        if len(nearest_row(j, above[j], up=True)) != 1:
            continue
        parent[find(j)] = find(i)

    grouped = {}
    for i in range(n):
        grouped.setdefault(find(i), []).append(flat[i])
    blocks = []
    for ls in grouped.values():
        b = Block(lines=sorted(ls, key=lambda l: (l.y0, l.x0)))
        b.fit_bbox()
        blocks.append(b)
    for l in tilted:
        b = Block(lines=[l])
        b.fit_bbox()
        blocks.append(b)
    blocks.sort(key=lambda b: (b.y0, b.x0))
    return blocks


def split_tables(chars: List[Ch], tables: List[dict]):
    """표 칸 안의 글자를 따로 떼어 표 블록을 만든다.

    tables: [{"bbox": (x0,y0,x1,y1), "cells": [[칸 bbox 또는 None, ...], ...]}, ...]
    반환: (표 밖 글자, 표 블록 목록)
    """
    valid = []
    for t in tables:
        rows = t["cells"]
        if len(rows) < 2 or max((len(r) for r in rows), default=0) < 2:
            continue
        valid.append(t)
    if not valid:
        return chars, []

    rest: List[Ch] = []
    buckets = [dict() for _ in valid]
    for c in chars:
        placed = False
        if abs(c.angle) < 3.0:
            cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
            for ti, t in enumerate(valid):
                x0, y0, x1, y1 = t["bbox"]
                if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                    continue
                for ri, row in enumerate(t["cells"]):
                    for ci, cell in enumerate(row):
                        if cell and cell[0] <= cx <= cell[2] and cell[1] <= cy <= cell[3]:
                            buckets[ti].setdefault((ri, ci), []).append(c)
                            placed = True
                            break
                    if placed:
                        break
                break
        if not placed:
            rest.append(c)

    blocks: List[Block] = []
    for t, bucket in zip(valid, buckets):
        total = sum(1 for row in t["cells"] for cell in row if cell)
        if total == 0 or len(bucket) < max(2, 0.4 * total):
            for cs in bucket.values():             # 표로 보기 어려우면 일반 글자로 되돌린다
                rest.extend(cs)
            continue
        b = Block(kind="table")
        b.x0, b.y0, b.x1, b.y1 = t["bbox"]
        b.cell_lines = []                          # type: ignore[attr-defined]
        b.cell_right = []                          # type: ignore[attr-defined]
        sizes = []
        for ri, row in enumerate(t["cells"]):
            out_row, right_row = [], []
            for ci, cell in enumerate(row):
                ls = sorted(build_lines(bucket.get((ri, ci), [])), key=lambda l: (l.y0, l.x0))
                sizes.extend(l.size for l in ls)
                out_row.append(ls)
                pad = 7.2 + 0.25 * (ls[0].size if ls else 0.0)      # 칸 안쪽 여백 어림
                right_row.append(cell[2] - pad if cell else 0.0)
            b.cell_lines.append(out_row)           # type: ignore[attr-defined]
            b.cell_right.append(right_row)         # type: ignore[attr-defined]
        b.size = _dominant(sizes)
        blocks.append(b)
    return rest, blocks


def apply_shape_boxes(blocks: List[Block], rects, page_w: float, page_h: float) -> List[Block]:
    """글자를 감싸는 도형(색 채운 상자, 테두리 상자)이 있으면 그 도형을 블록의 영역으로 쓴다.

    PDF에서는 글자가 차지한 좁은 영역만 보이지만, 사람은 상자 단위로 읽는다.
    PPTX 쪽은 도형 상자를 그대로 쓰므로 이렇게 해야 두 형식의 배치 판단이 같아진다.
    한 상자 안에 세로로 쌓인 블록들은 같은 도형의 글이므로 하나로 합친다.
    """
    page_area = max(page_w * page_h, 1.0)
    usable = [r for r in rects
              if r[2] - r[0] >= 12 and r[3] - r[1] >= 10 and (r[2] - r[0]) * (r[3] - r[1]) <= 0.5 * page_area]
    if not usable:
        return blocks
    usable.sort(key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    texts = [b for b in blocks if b.kind == "text" and b.lines and abs(b.lines[0].angle) < 3.0]
    owner = {}
    for b in texts:
        for r in usable:                               # 넓이가 작은 것부터 → 가장 꼭 맞는 상자
            if r[0] - 2 <= b.x0 and r[1] - 2 <= b.y0 and b.x1 <= r[2] + 2 and b.y1 <= r[3] + 2:
                owner[id(b)] = r
                break
    by_rect = {}
    for b in texts:
        r = owner.get(id(b))
        if r is not None:
            by_rect.setdefault(r, []).append(b)
    out = [b for b in blocks if id(b) not in owner]
    for r, members in by_rect.items():
        members.sort(key=lambda b: (b.y0, b.x0))
        stacked = all(
            min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5 * min(a.x1 - a.x0, b.x1 - b.x0) and b.y0 >= a.y0 + 0.5 * (a.y1 - a.y0)
            for a, b in zip(members, members[1:])
        )
        small = (r[2] - r[0]) * (r[3] - r[1]) <= 0.25 * page_area
        if len(members) == 1 or (stacked and small):
            merged = Block(lines=[l for b in members for l in b.lines])
            merged.fit_bbox()
            merged.x0, merged.y0, merged.x1, merged.y1 = r
            merged.boxed = True                        # type: ignore[attr-defined]
            out.append(merged)
        else:
            out.extend(members)                        # 여러 덩어리가 흩어져 있는 큰 판은 건드리지 않는다
    return out


def chars_to_blocks(chars: List[Ch], tables: List[dict], rects=None, page_w: float = 0.0, page_h: float = 0.0) -> List[Block]:
    rest, table_blocks = split_tables(chars, tables)
    blocks = group_blocks(build_lines(rest))
    if rects and page_w and page_h:
        blocks = apply_shape_boxes(blocks, rects, page_w, page_h)
    blocks += table_blocks
    blocks.sort(key=lambda b: (b.y0, b.x0))
    return blocks
