"""PDF 공통 처리: 글자 → 줄 → 블록.

pdfplumber에서는 글자(문자, 좌표, 글꼴)와 표의 칸 위치, 도형 상자만 받고,
줄과 블록으로 묶는 규칙은 여기 한 곳에서 처리한다.
PDF를 읽는 라이브러리가 바뀌어도 이 규칙은 그대로 쓸 수 있다.
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
    __slots__ = ("c", "x0", "y0", "x1", "y1", "ox", "oy", "size", "font", "bold", "angle", "color", "over")

    def __init__(self, c, x0, y0, x1, y1, ox, oy, size, font, bold, angle, color=None):
        self.color = color    # 글자색(같은지 비교하는 용도). 모르면 None
        self.over = False     # 표 위에 따로 얹힌 글로 보고 표에서 떼어 낸 글자
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
        overlay=any(c.over for c in seg),
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


TIGHT_GAP = 0.6       # 저장된 순서로 이어진 두 글자의 간격이 글자 크기의 이 비율 이하면 한 번에 찍은 글로 본다


def _same_run(p: Ch, c: Ch) -> bool:
    """c가 p 바로 뒤에, 같은 줄에서 빈틈 없이 이어 찍힌 글자인가."""
    if abs(p.angle) >= 3.0 or abs(c.angle) >= 3.0:
        return False
    if abs(c.oy - p.oy) > max(1.0, 0.25 * min(p.size, c.size)):
        return False
    big = max(p.size, c.size, 1.0)
    return -0.5 * big <= c.x0 - p.x1 <= TIGHT_GAP * big


def find_overlays(chars: List[Ch], home: list, tables: List[dict]) -> set:
    """표 칸에 들어간 글자 가운데 표의 글이 아니라 표 위에 따로 얹힌 글(코멘트 글상자 등)을 찾는다.

    PDF에는 '이 글자는 표의 것'이라는 표시가 없어서, 좌표만 보면 표 위에 얹은 글도 그 자리 칸의 글이 된다.
    그러면 코멘트가 칸 경계에서 잘려 칸마다 원래 글 뒤에 붙는다. 가려내는 단서는 두 가지다.

      저장 순서  표는 자기 글을 첫 칸부터 마지막 칸까지 차례로 한 번에 저장한다. 그 앞이나 뒤에
                 이미 지나간 칸 자리로 되돌아와 저장된 글은 다른 도형의 글이다.
      칸 경계    표의 글은 칸 안에 머문다. 빈틈 없이 이어진 글이 칸 경계나 표 가장자리를 넘으면 표의 글이 아니다.

    순서가 어긋난 글이라도 증거가 있을 때만 떼어 낸다. 증거는 (가) 경계를 넘었거나,
    (나) 표의 글이 이미 있는 칸에 그 글과 다른 색이나 크기로 덧찍힌 경우다.
    칸 순서대로 저장하지 않는 PDF에서는 순서로 판단하지 않으므로 이전과 같은 결과가 나온다.

    home[i]는 글자 i가 들어갈 (표 번호, 행, 열) 또는 None. 반환: 떼어 낼 글자의 순번 집합.
    """
    lifted: set = set()
    n = len(chars)
    run_of = [0] * n                               # 글자 → 한 번에 이어 찍힌 묶음 번호
    runs: List[List[int]] = []
    for i in range(n):
        if i and _same_run(chars[i - 1], chars[i]):
            runs[-1].append(i)
        else:
            runs.append([i])
        run_of[i] = len(runs) - 1

    for ti, t in enumerate(tables):
        idx = [i for i in range(n) if home[i] is not None and home[i][0] == ti]
        if not idx:
            continue
        x0, y0, x1, y1 = t["bbox"]

        def outside(i: int) -> bool:
            c = chars[i]
            if c.c.isspace():
                return False
            cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
            return not (x0 <= cx <= x1 and y0 <= cy <= y1)

        def style(i: int):
            return (chars[i].color, round(chars[i].size, 1))

        # 1) 표 가장자리를 넘는 글: 한 번에 찍힌 글의 일부는 표 안, 일부는 표 밖에 있다
        crosses = {}
        for i in idx:
            r = run_of[i]
            if r not in crosses:
                crosses[r] = any(outside(j) for j in runs[r])
            if crosses[r]:
                lifted.add(i)

        # 2) 저장 순서로 구간을 나눈다. 칸 순서가 뒤로 돌아가거나 표 밖 글자가 끼어들면 새 구간이다
        segs: List[List[int]] = []
        last_key, last_i = None, -1
        for i in idx:
            key = home[i][1:]
            if last_key is None or key < last_key or any(outside(j) for j in range(last_i + 1, i)):
                segs.append([])
            segs[-1].append(i)
            last_key, last_i = key, i
        if len(segs) < 2:
            continue
        seg_cells = [{home[i][1:] for i in seg} for seg in segs]
        main = max(range(len(segs)), key=lambda k: (len(seg_cells[k]), len(segs[k])))    # 칸을 가장 많이 거친 구간 = 표 자신의 글
        if len(seg_cells[main]) * 2 < len(set().union(*seg_cells)):
            continue                               # 칸 순서대로 저장된 표가 아니다. 순서로는 판단하지 않는다
        own = {}                                   # 칸 → 표 자신의 글이 쓴 글자 모양(색, 크기)
        for i in segs[main]:
            if i not in lifted:
                own.setdefault(home[i][1:], set()).add(style(i))
        for k, seg in enumerate(segs):
            if k == main:
                continue
            by_run = {}
            for i in seg:
                by_run.setdefault(run_of[i], []).append(i)
            proof = False
            for members in by_run.values():
                cells = {home[i][1:] for i in members}
                if len(cells) >= 2 or any(i in lifted for i in members):
                    proof = True                   # (가) 칸 경계나 표 가장자리를 넘었다
                    break
                cell = next(iter(cells))
                if cell in own and not ({style(i) for i in members} & own[cell]):
                    proof = True                   # (나) 표의 글이 있는 칸에 다른 모양의 글자로 덧찍혔다
                    break
            if proof:
                lifted.update(seg)
    return lifted


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
    home: list = [None] * len(chars)               # 글자마다 들어갈 (표 번호, 행, 열)
    for i, c in enumerate(chars):
        if abs(c.angle) < 3.0:
            cx, cy = (c.x0 + c.x1) / 2, (c.y0 + c.y1) / 2
            for ti, t in enumerate(valid):
                x0, y0, x1, y1 = t["bbox"]
                if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                    continue
                for ri, row in enumerate(t["cells"]):
                    for ci, cell in enumerate(row):
                        if cell and cell[0] <= cx <= cell[2] and cell[1] <= cy <= cell[3]:
                            home[i] = (ti, ri, ci)
                            break
                    if home[i] is not None:
                        break
                break
    lifted = find_overlays(chars, home, valid)     # 표 위에 얹힌 글은 칸에 넣지 않고 보통 글로 돌려보낸다
    for i, c in enumerate(chars):
        if home[i] is None or i in lifted:
            rest.append(c)
        else:
            buckets[home[i][0]].setdefault(home[i][1:], []).append(c)

    blocks: List[Block] = []
    for ti, (t, bucket) in enumerate(zip(valid, buckets)):
        total = sum(1 for row in t["cells"] for cell in row if cell)
        if total == 0 or len(bucket) < max(2, 0.4 * total):
            for cs in bucket.values():             # 표로 보기 어려우면 일반 글자로 되돌린다
                rest.extend(cs)
            continue
        for i in lifted:                           # 표로 남은 경우에만 '표 위에 얹힌 글'로 표시한다
            if home[i][0] == ti:
                chars[i].over = True
        b = Block(kind="table")
        b.x0, b.y0, b.x1, b.y1 = t["bbox"]
        b.cell_boxes = t["cells"]                  # type: ignore[attr-defined]  합친 칸을 알아내는 데 쓴다(tables.py)
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
