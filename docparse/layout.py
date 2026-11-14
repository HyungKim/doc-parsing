"""읽는 순서 정렬(재귀 X-Y cut)과 줄 → 문단 합치기."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .model import Block, Line, Page
from .textnorm import is_cjk

# 읽는 순서를 정하는 기준값. 샘플로 정한 값이라, 실제 자료에서 안전한지는 tune.py로 확인한다.
Y_PREFERENCE = 1.5     # 좌우로 자르려면 좌우 여백이 위아래 여백의 이 배수보다 넓어야 한다 (위아래 자르기 우대)
Y_MIN_GAP = 0.5        # 위아래로 자르는 데 필요한 여백(pt). 겹치지만 않으면 자른다는 뜻이고, 좌표의 소수점 오차만 걸러 낸다
X_MIN_GAP = 6.0        # 좌우로 자르는 데 필요한 여백(pt)의 최소 보장. 작은 글자와 상자 가장자리 오차 대비
X_GAP_RATIO = 0.6      # 좌우로 자르는 데 필요한 여백 = 본문 글자 크기의 이 배수(띄어쓰기 두 칸쯤)와 X_MIN_GAP 중 큰 값


def _min_x_gap(font_size: float) -> float:
    return max(X_MIN_GAP, X_GAP_RATIO * font_size)


# ---------------------------------------------------------------- 읽는 순서

def _best_gap(blocks: List[Block], lo: str, hi: str):
    items = sorted(blocks, key=lambda b: getattr(b, lo))
    best, cut = 0.0, 0
    reach = getattr(items[0], hi)
    for k in range(1, len(items)):
        gap = getattr(items[k], lo) - reach
        if gap > best:
            best, cut = gap, k
        reach = max(reach, getattr(items[k], hi))
    return best, items, cut


def _row_major(blocks: List[Block]) -> List[Block]:
    """여백으로 나눌 수 없을 때: 세로로 겹치는 것끼리 한 줄로 보고 왼쪽부터 읽는다."""
    items = sorted(blocks, key=lambda b: ((b.y0 + b.y1) / 2, b.x0))
    rows: List[List[Block]] = []
    for b in items:
        if rows:
            ref = rows[-1][0]
            overlap = min(ref.y1, b.y1) - max(ref.y0, b.y0)
            if overlap > 0.5 * min(ref.y1 - ref.y0, b.y1 - b.y0):
                rows[-1].append(b)
                continue
        rows.append([b])
    out: List[Block] = []
    for row in rows:
        out.extend(sorted(row, key=lambda b: b.x0))
    return out


def _bands(blocks: List[Block], lo: str, hi: str, min_gap: float) -> List[List[Block]]:
    items = sorted(blocks, key=lambda b: getattr(b, lo))
    bands = [[items[0]]]
    reach = getattr(items[0], hi)
    for b in items[1:]:
        if getattr(b, lo) - reach >= min_gap:
            bands.append([])
        bands[-1].append(b)
        reach = max(reach, getattr(b, hi))
    return bands


def _grid_order(blocks: List[Block], font_size: float):
    """줄과 칸이 깔끔하게 맞는 격자 배치를 알아본다(칸마다 블록이 하나 이하).

    2줄짜리 격자는 '머리글 + 내용' 카드가 옆으로 늘어선 것으로 보고 세로 묶음 단위로 읽는다.
    3줄 이상이고 칸의 글이 짧으면 표처럼 가로 줄 단위로 읽는다.
    반환: (읽는 순서, 가로 줄 단위로 읽었는가) 또는 격자가 아니면 None
    """
    rows = _bands(blocks, "y0", "y1", Y_MIN_GAP)
    cols = _bands(blocks, "x0", "x1", _min_x_gap(font_size))
    if len(rows) < 2 or len(cols) < 2:
        return None
    if any(len(row) < 2 for row in rows):
        return None                                    # 한 줄에 하나뿐인 블록은 격자의 일부가 아니다 → 먼저 떼어 낸다
    if len(rows) >= 3:
        gaps = [min(b.y0 for b in rows[i + 1]) - max(b.y1 for b in rows[i]) for i in range(len(rows) - 1)]
        if max(gaps) > 1.8 * max(min(gaps), 1.0):
            return None                                # 줄 간격이 들쭉날쭉하면 표가 아니라 카드 묶음 → 넓은 여백부터 자른다
    col_of = {id(b): c for c, col in enumerate(cols) for b in col}
    cells = {}
    for r, row in enumerate(rows):
        for b in row:
            key = (r, col_of[id(b)])
            if key in cells:
                return None
            cells[key] = b
    short = sum(1 for b in cells.values() if sum(len(l.text) for l in b.lines) <= 40 or b.kind == "table")
    table_like = len(rows) >= 3 and short >= 0.7 * len(cells)
    if table_like:
        order = [(r, c) for r in range(len(rows)) for c in range(len(cols))]
    else:                                              # 카드 묶음이나 글 단: 세로 묶음 단위로
        order = [(r, c) for c in range(len(cols)) for r in range(len(rows))]
    return [cells[k] for k in order if k in cells], table_like


def _extent(blocks: List[Block]) -> tuple:
    return (min(b.x0 for b in blocks), min(b.y0 for b in blocks), max(b.x1 for b in blocks), max(b.y1 for b in blocks))


def _pure(band: List[Block], lo: str, hi: str) -> bool:
    """띠 안의 블록이 모두 서로 겹치는가. 가로 띠라면 '옆으로 나란한 한 줄', 세로 띠라면 '한 줄로 쌓인 단'."""
    for i, a in enumerate(band):
        for b in band[i + 1:]:
            if getattr(a, hi) <= getattr(b, lo) + 0.5 or getattr(b, hi) <= getattr(a, lo) + 0.5:
                return False
    return True


def xy_order(blocks: List[Block], font_size: float, trace: Optional[list] = None, depth: int = 0) -> List[Block]:
    """재귀 X-Y cut. 가장 넓은 여백에서 둘로 나누고 각 조각에 같은 일을 반복한다.

    trace에 목록을 주면 어떻게 나눴는지를 차례로 담아 준다(결과에는 영향이 없다. tune.py가 그림으로 보여 주는 데 쓴다).
      {"kind": "cut", "axis": "x"|"y", "lo": 여백 시작, "hi": 여백 끝, ...}     그 여백에서 둘로 나눔
      {"kind": "grid", "by_rows": 가로 줄 단위인가, ...}                         격자로 보고 한 번에 정함
      {"kind": "rows", ...}                                                     자를 여백이 없어 줄 단위로 읽음
    공통 항목: "box" 나눈 영역, "depth" 몇 번째 단계, "gap_x"·"gap_y" 그 영역에서 가장 넓은 좌우·위아래 여백,
               "need_x" 좌우로 자르는 데 필요했던 여백

    어느 방향으로 자를지는 이렇게 정한다.
      1. 가로 줄로도 세로 단으로도 깔끔히 나뉘면 격자 → 격자 규칙(_grid_order)
      2. 가로 줄이 깔끔하면 위아래로 자른다
         (예: KPI 카드 4개 아래에 글상자 2개. PDF에서는 짧은 글의 영역이 좁게 잡혀
          좌우 여백이 실제보다 넓어 보이므로, 여백 너비만 비교하면 좌우로 잘못 가른다)
      3. 그 밖에는 여백 너비를 비교하되 위아래 자르기를 조금 우대한다
    """
    if len(blocks) <= 1:
        return list(blocks)
    min_x = _min_x_gap(font_size)
    gap_y, by_y, cut_y = _best_gap(blocks, "y0", "y1")
    gap_x, by_x, cut_x = _best_gap(blocks, "x0", "x1")
    # 여백이 0이면 자를 곳이 없다(한쪽 조각이 비어 끝나지 않는다). 기준값을 0으로 두어도 안전하도록 따로 확인한다.
    ok_y = gap_y > 0 and gap_y >= Y_MIN_GAP
    ok_x = gap_x > 0 and gap_x >= min_x
    note = None
    if trace is not None:
        note = {"box": _extent(blocks), "depth": depth, "gap_x": gap_x, "gap_y": gap_y, "need_x": min_x}
    if not ok_x and not ok_y:
        if note is not None:
            trace.append(dict(note, kind="rows"))
        return _row_major(blocks)

    axis = "y" if ok_y else "x"
    if ok_x and ok_y:
        rows_pure = all(len(r) == 1 or _pure(r, "y0", "y1") for r in _bands(blocks, "y0", "y1", Y_MIN_GAP))
        cols_pure = all(len(c) == 1 or _pure(c, "x0", "x1") for c in _bands(blocks, "x0", "x1", min_x))
        if rows_pure and cols_pure:
            grid = _grid_order(blocks, font_size)
            if grid is not None:
                if note is not None:
                    trace.append(dict(note, kind="grid", by_rows=grid[1]))
                return grid[0]
        if rows_pure:
            axis = "y"                                 # 가로 줄이 깔끔하면 줄 단위로 먼저 떼어 낸다
        else:
            axis = "x" if gap_x > Y_PREFERENCE * gap_y else "y"
    if axis == "x":
        first, second = by_x[:cut_x], by_x[cut_x:]
        lo, hi = max(b.x1 for b in first), second[0].x0
    else:
        first, second = by_y[:cut_y], by_y[cut_y:]
        lo, hi = max(b.y1 for b in first), second[0].y0
    if note is not None:
        trace.append(dict(note, kind="cut", axis=axis, lo=lo, hi=hi))
    return xy_order(first, font_size, trace, depth + 1) + xy_order(second, font_size, trace, depth + 1)


# ---------------------------------------------------------------- 문단 합치기
#
# PDF에는 "여기서 문단이 끝난다"는 표시가 없다. 줄이 바뀐 이유가 자동 줄바꿈인지(이어 붙여야 함)
# 문단이 끝나서인지(나눠야 함)를 다음 근거로 판단한다. 위에 있을수록 확실한 근거다.
#   1. 글머리 기호·번호로 시작하거나 글자 크기가 바뀌면 새 문단
#   2. 줄 끝에 공백 글자가 남아 있으면 자동 줄바꿈 (PDF를 만든 프로그램에 따라 남는다)
#   3. 글상자의 오른쪽 끝을 알면: 앞줄에 다음 글자(단어)가 들어갈 자리가 남았을 때만 새 문단
#      오른쪽 끝은 ① 글을 감싼 도형 ② 같은 지점까지 찬 줄이 둘 이상 ③ 문서 안에서 같은 왼쪽
#      시작점을 가진 다른 글상자 ④ 페이지 여백·옆 단의 시작점 순으로 찾는다
#   4. 아무 근거도 없으면 줄마다 따로 둔다 (서로 다른 항목이 붙는 것보다 덜 해롭다)

@dataclass
class WrapContext:
    trailing_seen: bool = False   # 이 PDF는 줄 끝 공백을 글자로 남기는가
    char_wrap: bool = True        # 한글이 단어 중간에서도 줄바꿈되는 문서인가


def _same_row(prev: Line, cur: Line) -> bool:
    return cur.y0 < prev.y0 + 0.5 * max(prev.y1 - prev.y0, 1.0)


def _new_paragraph(prev: Line, cur: Line, slack: float, char_wrap: bool = False) -> bool:
    """slack = 앞줄 끝에서 글상자 오른쪽 끝까지 남은 폭."""
    if cur.list_start:
        return True
    h = max(prev.size, 1.0)
    if abs(cur.size - prev.size) > 0.12 * h:
        return True
    if prev.trailing_space:
        return False
    if char_wrap and is_cjk(cur.text[:1]):
        return slack > cur.first_char_w + 0.1 * h
    return slack > cur.first_word_w + 0.3 * h


def _joiner(prev: Line, cur: Line, slack: float, ctx: WrapContext) -> str:
    if prev.trailing_space:
        return " "
    a, b = prev.text[-1:], cur.text[:1]
    if not (is_cjk(a) or is_cjk(b)):
        if a == "-" and len(prev.text) >= 2 and prev.text[-2].isalpha() and b.isalpha():
            return ""                      # long-|standing 처럼 붙임표에서 넘어간 경우
        return " "                         # 영문은 단어 중간에서 줄바꿈되지 않는다
    if ctx.trailing_seen:
        return ""                          # 줄 끝 공백이 없었으니 단어 중간에서 잘린 것
    if cur.first_char_w > 0 and slack >= 0.98 * cur.first_char_w:
        return " "                         # 글자 하나 들어갈 자리가 남았는데도 넘어갔다 → 띄어쓰기 자리
    return "" if ctx.char_wrap else " "


def _pdf_lines(lines: List[Line]) -> List[Line]:
    return [l for l in lines if not l.removed and not l.is_para]


def analyze_wrap(pages: List[Page]) -> WrapContext:
    trailing = joins = tight = 0
    for page in pages:
        for block in page.blocks:
            groups = [block.lines]
            for row in getattr(block, "cell_lines", []) or []:
                groups.extend(row)
            for group in groups:
                ls = _pdf_lines(group)
                if len(ls) < 2:
                    continue
                right = max(l.x1 for l in ls)
                for prev, cur in zip(ls, ls[1:]):
                    if prev.trailing_space and is_cjk(prev.text[-1:]):
                        trailing += 1                  # 한글 줄에서도 줄 끝 공백이 남는 PDF인지 본다
                    if _same_row(prev, cur) or _new_paragraph(prev, cur, right - prev.x1):
                        continue
                    if is_cjk(prev.text[-1:]) and is_cjk(cur.text[:1]) and cur.first_char_w > 0:
                        joins += 1
                        if (right - prev.x1) < cur.first_char_w:
                            tight += 1
    return WrapContext(trailing_seen=trailing >= 2,
                       char_wrap=True if joins < 4 else tight >= 0.75 * joins)


def estimate_right_edges(pages: List[Page]) -> None:
    """줄바꿈 판단에 쓸 '글상자 오른쪽 끝'을 블록마다 어림한다(위 설명의 3번).

    블록 자체의 근거가 약할수록(같은 지점까지 찬 줄이 적을수록) 주변에서 빌려 온다.
      - 같은 쪽에서 왼쪽 시작점이 같은 다른 블록이 뻗은 곳 (위아래로 쌓인 같은 단)
      - 같은 쪽에서 옆으로 나란한 블록의 폭 (3단 카드처럼 폭이 같은 단)
      - 다른 쪽에서 왼쪽 시작점이 같은 블록의 끝 (같은 서식의 슬라이드)
    어느 것도 옆 단의 시작점을 넘지 않는 범위에서만 쓴다.
    """
    infos = []
    lefts = []
    for pi, page in enumerate(pages):
        for block in page.blocks:
            if block.kind != "text" or block.role == "removed":
                continue
            ls = _pdf_lines(block.lines)
            if not ls:
                continue
            left, right = min(l.x0 for l in ls), max(l.x1 for l in ls)
            lefts.append(left)
            if getattr(block, "boxed", False):         # 글을 감싼 도형이 곧 글상자
                block.inner = (block.x0 + 7.2, block.x1 - 7.2)      # type: ignore[attr-defined]
                continue
            full = sum(1 for l in ls if l.x1 >= right - 1.2 * max(l.size, 1.0))
            tier = "single" if len(ls) < 2 else "strong" if full >= 3 else "weak" if full == 2 else "none"
            infos.append({"pi": pi, "page": page, "block": block, "left": left, "right": right, "tier": tier})
    lefts.sort()
    doc_left = lefts[len(lefts) // 20] if lefts else 0.0

    for info in infos:
        if info["tier"] in ("single", "strong"):
            continue
        page, block, left, right = info["page"], info["block"], info["left"], info["right"]
        size = max(block.size, 1.0)
        limit = page.width
        for other in page.blocks:
            if other is block or other.role == "removed":
                continue
            if other.x0 > right - 1.0 and min(other.y1, block.y1) - max(other.y0, block.y0) > 0:
                limit = min(limit, other.x0)
        cap = limit - size
        est = right
        for o in infos:
            if o["block"] is block or o["pi"] != info["pi"]:
                continue
            ob = o["block"]
            if abs(o["left"] - left) <= 1.5 * size and o["right"] <= cap:
                est = max(est, o["right"])             # 같은 단에 쌓인 블록
            overlap = min(ob.y1, block.y1) - max(ob.y0, block.y0)
            beside = ob.x0 >= block.x1 - 1.0 or ob.x1 <= block.x0 + 1.0
            if beside and overlap > 0.5 * min(ob.y1 - ob.y0, block.y1 - block.y0):
                reach = left + (o["right"] - o["left"])
                if reach <= cap:
                    est = max(est, reach)              # 옆으로 나란한 블록과 같은 폭
        if est <= right:
            cands = [o["right"] for o in infos
                     if o["pi"] != info["pi"] and o["tier"] in ("strong", "weak")
                     and abs(o["left"] - left) <= size and right < o["right"] <= cap]
            if cands:
                est = min(cands)                       # 다른 쪽의 같은 서식
        if est > right:
            block.right_hint = est                     # type: ignore[attr-defined]
            continue
        if info["tier"] == "none":
            touches = (
                abs((page.width - doc_left) - right) <= 1.5 * size             # 페이지 오른쪽 여백까지 참
                or (limit < page.width and right >= limit - 14.4 - 1.5 * size)  # 옆 단 바로 앞까지 참
            )
            if not touches:
                block.no_wrap = True                   # type: ignore[attr-defined]


def render_lines(lines: List[Line], ctx: WrapContext, right_hint: float = 0.0, no_wrap: bool = False,
                 inner=None) -> str:
    lines = [l for l in lines if not l.removed and l.text]
    if not lines:
        return ""
    if all(l.is_para for l in lines):
        return "\n".join(l.text for l in lines)
    right = max(max(l.x1 for l in lines), right_hint)
    centered = False
    if inner is not None:
        mid = (inner[0] + inner[1]) / 2
        centered = (all(abs((l.x0 + l.x1) / 2 - mid) <= 0.6 * max(l.size, 1.0) for l in lines)
                    and any(l.x0 > inner[0] + l.size for l in lines))

    def slack(prev: Line) -> float:
        if inner is not None and centered:
            return (inner[1] - inner[0]) - (prev.x1 - prev.x0)
        if inner is not None:
            return inner[1] - prev.x1
        return right - prev.x1

    out: List[str] = []
    prev = None
    for cur in lines:
        if prev is None or cur.is_para or prev.is_para:
            out.append(cur.text)
        elif _same_row(prev, cur):
            out[-1] += " " + cur.text
        else:
            s = slack(prev)
            cjk_join = is_cjk(prev.text[-1:]) or is_cjk(cur.text[:1])
            same_size = abs(cur.size - prev.size) <= 0.12 * max(prev.size, 1.0)
            if len(cur.text) <= 1 and not cur.list_start and same_size:
                # 한 글자뿐인 줄은 독립된 문단일 수 없다 → 앞줄에서 넘어온 꼬리
                out[-1] += ("" if cjk_join and not prev.trailing_space else " ") + cur.text
            elif _new_paragraph(prev, cur, s, ctx.char_wrap) or (
                    no_wrap and ctx.char_wrap and cjk_join and not prev.trailing_space):
                out.append(cur.text)
            else:
                out[-1] += _joiner(prev, cur, s, ctx) + cur.text
        prev = cur
    return "\n".join(out)


def render_block(block: Block, ctx: WrapContext) -> str:
    if block.kind == "table":
        cell_lines = getattr(block, "cell_lines", None)
        if cell_lines is not None:
            rights = getattr(block, "cell_right", None)
            block.rows = [
                [render_lines(cell, ctx, rights[r][c] if rights else 0.0).replace("\n", " ")
                 for c, cell in enumerate(row)]
                for r, row in enumerate(cell_lines)
            ]
        rows = [" | ".join(c for c in row if c) for row in block.rows]
        return "\n".join(r for r in rows if r)
    return render_lines(block.lines, ctx, getattr(block, "right_hint", 0.0), getattr(block, "no_wrap", False),
                        getattr(block, "inner", None))
