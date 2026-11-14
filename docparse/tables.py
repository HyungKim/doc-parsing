"""표를 글로 바꾸는 두 번째 모양: 행마다 머리글을 붙여 풀어 쓰기.

기존 모양은 칸을 ` | `로 이어 한 행을 한 줄로 적는다. 빈 칸이 있거나 머리글이 여러 단이면
값이 어느 열의 것인지 알 수 없게 된다. 풀어 쓰기는 값마다 행 머리글과 열 머리글을 붙인다.

    국내 > 제조 > 설비 투자 — 2026년 상반기 계획: 101, 2026년 상반기 실적: 102, …

머리글이 어디까지인지는 칸을 합친 모양으로 추정한다. 추정을 믿기 어려우면 풀어 쓰지 않고
` | ` 모양으로 물러서되, 빈 칸과 합친 칸의 자리를 채워 열이 어긋나지 않게 한다.

칸은 (행, 열, 세로로 합친 수, 가로로 합친 수, 글) 로 나타낸다. 합쳐진 칸은 시작 칸 하나다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

Cell = Tuple[int, int, int, int, str]

_NUM = re.compile(r"^[\s\d.,%+\-()~▲△]+$")
_YEAR = re.compile(r"^\s*(19|20)\d{2}\s*$")
EDGE_TOLERANCE = 3.0      # 칸 가장자리가 이 거리(pt) 안이면 같은 격자선으로 본다


@dataclass
class Flat:
    mode: str                                   # keyvalue: 풀어 씀 | pipe: 풀어 쓰지 않고 칸 구분으로 둠
    reason: str = ""                            # pipe일 때 그 이유
    caption: List[str] = field(default_factory=list)
    head_rows: int = 0                          # 열 머리글이 차지한 행 수
    label_cols: int = 0                         # 행 머리글이 차지한 열 수
    rows: List[Tuple[tuple, list]] = field(default_factory=list)     # [(행 경로, [(열 경로, 값)])]
    lines: List[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _numeric_like(text: str) -> bool:
    return bool(text.strip()) and bool(_NUM.match(text)) and not _YEAR.match(text)


def _cluster(values: List[float]) -> List[float]:
    values = sorted(values)
    groups = [[values[0]]]
    for v in values[1:]:
        if v - groups[-1][-1] <= EDGE_TOLERANCE:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def cells_from_boxes(boxes: list, texts: list) -> Tuple[int, int, List[Cell]]:
    """PDF: 칸 상자들의 가장자리로 격자를 되살리고, 상자가 걸친 범위로 합친 칸을 알아낸다.

    boxes[r][c]는 (x0, y0, x1, y1) 또는 None, texts[r][c]는 그 칸의 글.
    """
    found = [(b, texts[r][c] if r < len(texts) and c < len(texts[r]) else "")
             for r, row in enumerate(boxes) for c, b in enumerate(row) if b]
    if not found:
        return 0, 0, []
    xs = _cluster([b[0] for b, _ in found] + [b[2] for b, _ in found])
    ys = _cluster([b[1] for b, _ in found] + [b[3] for b, _ in found])
    near = lambda edges, v: min(range(len(edges)), key=lambda i: abs(edges[i] - v))
    cells: List[Cell] = []
    for b, text in found:
        c0, c1, r0, r1 = near(xs, b[0]), near(xs, b[2]), near(ys, b[1]), near(ys, b[3])
        if c1 > c0 and r1 > r0:
            cells.append((r0, c0, r1 - r0, c1 - c0, text))
    return len(ys) - 1, len(xs) - 1, cells


def _pipe(R: int, C: int, cells: List[Cell], reason: str, caption: Optional[List[str]] = None) -> Flat:
    """칸 구분 모양. 빈 칸은 자리를 남기고, 합친 칸은 걸친 자리마다 같은 글을 적어 열을 맞춘다."""
    grid = [["" for _ in range(C)] for _ in range(R)]
    whole = {}
    for r, c, rs, cs, text in cells:
        if c == 0 and cs >= C and rs == 1 and C > 1:
            whole[r] = text.strip()                      # 표 전체 폭 줄은 한 번만 적는다
            continue
        for rr in range(r, min(r + rs, R)):
            for cc in range(c, min(c + cs, C)):
                grid[rr][cc] = text.strip()
    lines = ["[표] " + t for t in (caption or []) if t]
    for r in range(R):
        if r in whole:
            if whole[r]:
                lines.append(whole[r])
        elif any(grid[r]):
            lines.append(" | ".join(grid[r]))
    return Flat("pipe", reason, caption=list(caption or []), lines=lines)


def flatten(R: int, C: int, cells: List[Cell]) -> Flat:
    if R < 2 or C < 2:
        return _pipe(R, C, cells, "행이나 열이 하나뿐인 표")

    # 1) 표 전체 폭을 차지하는 줄: 맨 위에 있으면 표 제목, 본문에 있으면 구분 줄
    full = {r: text for r, c, rs, cs, text in cells if c == 0 and cs >= C and rs == 1}
    ncap = 0
    while ncap in full:
        ncap += 1
    caption = [full[r].strip() for r in range(ncap) if full[r].strip()]
    section = {r - ncap: t.strip() for r, t in full.items() if r >= ncap}
    cells = [(r - ncap, c, rs, cs, t) for r, c, rs, cs, t in cells if r >= ncap]
    R -= ncap
    if R < 2:
        return _pipe(R, C, cells, "제목 줄을 빼면 본문이 없음", caption)
    work = [x for x in cells if x[0] not in section]
    origin = {(r, c): (rs, cs) for r, c, rs, cs, _ in work}

    # 2) 열 머리글이 차지한 행 수 H
    rs0, cs0 = origin.get((0, 0), (1, 1))
    H, L = (rs0, cs0) if (rs0 < R and cs0 < C) else (1, 1)       # 왼쪽 위 칸이 합쳐져 있으면 그 크기
    h = 1                                                         # 위쪽에 옆으로 합친 칸이 이어지는 동안 + 한 줄
    while h < R and any(r == h - 1 and cs > 1 and c >= L for r, c, rs, cs, _ in work):
        h += 1
    tall = [rs for r, c, rs, cs, _ in work if r == 0 and 1 < rs < R]
    if tall and (len(set(tall)) == 1 or max(tall) <= max(H, h)):  # 맨 윗줄에서 같은 높이로 내려온 칸 = 행 머리글 열의 이름
        H = max(H, max(tall))
    H = max(H, h)

    # 3) 행 머리글이 차지한 열 수 L
    l = 1                                                         # 본문 왼쪽에 아래로 합친 칸이 이어지는 동안 + 한 열
    while l < C and any(c == l - 1 and rs > 1 and r >= H for r, c, rs, cs, _ in work):
        l += 1
    lead = 0                                                      # 머리글 높이만큼 내려온 칸이 왼쪽에 연달아 있는 수
    while H > 1 and lead < C and origin.get((0, lead), (1, 1))[0] >= H:
        lead += 1
    if lead >= C:
        lead = 0
    L = max(L, l, lead)
    if R - H < 1 or C - L < 1:
        return _pipe(R, C, cells, "머리글을 빼면 값이 없음", caption)

    grid = {}
    for idx, (r, c, rs, cs, text) in enumerate(cells):
        if r in section:
            continue
        for rr in range(r, r + rs):
            for cc in range(c, c + cs):
                grid[(rr, cc)] = idx

    def path(indices) -> tuple:
        out, last = [], None
        for idx in indices:
            if idx is None or idx == last:
                continue
            last = idx
            if cells[idx][4].strip():
                out.append(cells[idx][4].strip())
        return tuple(out)

    col_paths = {c: path(grid.get((r, c)) for r in range(H)) for c in range(L, C)}
    missing = [c for c in col_paths if not col_paths[c]]
    if len(missing) * 2 > len(col_paths):
        return _pipe(R, C, cells, "열 머리글이 비어 있음", caption)
    for c in missing:
        col_paths[c] = ("%d번째 열" % (c + 1),)
    leaf = [col_paths[c][-1] for c in col_paths]
    if sum(1 for t in leaf if _numeric_like(t)) * 2 > len(leaf):
        return _pipe(R, C, cells, "첫 줄이 숫자여서 머리글이 없는 표로 봄", caption)

    # 4) 본문: 행 머리글의 빈 칸은 위 칸을 이어받는다(같은 상위 묶음 안에서만)
    res = Flat("keyvalue", caption=caption, head_rows=H, label_cols=L)
    res.lines.extend("[표] " + cap for cap in caption)
    context: tuple = ()
    prev: list = [None] * L
    for r in range(H, R):
        if r in section:
            context, prev = ((section[r],) if section[r] else ()), [None] * L
            if section[r]:
                res.lines.append(section[r])
            continue
        labels: list = []
        inherit, seen = True, None
        for c in range(L):
            idx = grid.get((r, c))
            text = cells[idx][4].strip() if idx is not None else ""
            if idx is not None and idx == seen:                   # 옆으로 합친 행 머리글(합계 등)은 한 번만
                labels.append(None)
                continue
            seen = idx
            if text:
                if prev[c] != text:
                    inherit = False                               # 상위 묶음이 바뀌면 아래 단은 이어받지 않는다
                labels.append(text)
            elif inherit and prev[c]:
                labels.append(prev[c])
            else:
                labels.append(None)
                inherit = False
        prev = labels
        rp = context + tuple(t for t in labels if t)
        vals = []
        for c in range(L, C):
            idx = grid.get((r, c))
            if idx is not None and cells[idx][4].strip():
                vals.append((col_paths[c], cells[idx][4].strip()))
        if not rp and not vals:
            continue
        res.rows.append((rp, vals))
        values = ", ".join("%s: %s" % (" ".join(cp), v) for cp, v in vals)
        res.lines.append(" — ".join(x for x in (" > ".join(rp), values) if x))
    return res


def describe(block) -> Optional[dict]:
    """표 블록(글이 정리된 뒤)에서 칸 구조와 풀어 쓴 결과를 만든다."""
    rows = getattr(block, "rows", None)
    if not rows:
        return None
    R, C = len(rows), max(len(r) for r in rows)
    spans = getattr(block, "cell_spans", None)                    # PPTX: 파일에 적힌 병합 정보
    boxes = getattr(block, "cell_boxes", None)                    # PDF: 칸 상자
    if spans is not None:
        cells = [(r, c, rs, cs, rows[r][c]) for r, c, rs, cs in spans if r < R and c < len(rows[r])]
    elif boxes is not None:
        R, C, cells = cells_from_boxes(boxes, rows)
    else:
        cells = [(r, c, 1, 1, rows[r][c]) for r in range(R) for c in range(len(rows[r]))]
    if not cells or R < 1 or C < 1:
        return None
    return {"rows": R, "cols": C, "cells": cells, "flat": flatten(R, C, cells)}
