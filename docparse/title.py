"""페이지 제목 고르기.

우선순위
  1. 구조 정보: PPTX의 제목 개체 틀
  2. 글꼴 규칙: 페이지 상단에서 본문보다 뚜렷이 큰 글자
  3. 글꼴 규칙: 표지·간지처럼 페이지에서 압도적으로 큰 글자
어느 것도 아니면 제목 없음으로 둔다(억지로 본문 첫 줄을 쓰지 않는다).
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .model import Block, Page
from .repeat import is_diagonal
from .textnorm import one_line

TOP_AREA = 0.30          # 블록의 윗변이 페이지 높이의 이 비율 안에 있으면 '상단'
BIGGER = 1.15            # 본문 글자보다 이만큼 커야 제목 후보
DOMINANT = 1.5           # 상단이 아니어도 이만큼 크면 제목으로 인정
MAX_LEN = 120


def _usable(b: Block) -> bool:
    if b.kind != "text" or b.hint in ("subtitle_ph", "chart", "smartart"):
        return False
    if b.lines and is_diagonal(b.lines[0].angle):
        return False
    t = one_line(b.text)
    if not (2 <= len(t) <= MAX_LEN):
        return False
    if _number_like(t):
        return False
    return b.text.count("\n") < 3


def _number_like(t: str) -> bool:
    """'87%', '5,530억', '10.1%' 같은 강조 숫자는 글자가 커도 제목이 아니다."""
    t = t.replace(" ", "")
    if not t or len(t) > 12:
        return False
    digits = sum(1 for ch in t if ch.isdigit())
    marks = sum(1 for ch in t if ch in ".,%+-/()~")
    return digits >= 1 and (digits + marks) >= 0.6 * len(t)


def pick_title(blocks: List[Block], page: Page, body_size: float) -> Tuple[Optional[Block], str]:
    placeholders = [b for b in blocks if b.hint == "title_ph" and b.text.strip()]
    if placeholders:
        return placeholders[0], "제목 개체 틀"
    cands = [b for b in blocks if _usable(b)]

    # 상단의 큰 글자 중 가장 위에 있는 것. 다만 가장 큰 글자의 70%에 못 미치는 작은 꼬리표는 건너뛴다.
    top = [b for b in cands if b.y0 <= TOP_AREA * page.height and b.size >= BIGGER * body_size]
    font_pick = None
    if top:
        biggest = max(b.size for b in top)
        font_pick = min((b for b in top if b.size >= 0.7 * biggest), key=lambda b: (b.y0, b.x0))

    if font_pick is not None:
        return font_pick, "글꼴 크기 (상단의 큰 글자)"

    if cands:
        best = max(cands, key=lambda b: (round(b.size, 1), -b.y0))
        rivals = [b for b in cands if b is not best and b.size >= 0.95 * best.size]
        if best.size >= DOMINANT * body_size and not rivals:
            return best, "글꼴 크기 (페이지에서 가장 큼)"
    return None, "제목 없음"
