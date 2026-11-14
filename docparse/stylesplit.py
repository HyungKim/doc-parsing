"""한 줄 안에서 글자색과 크기가 모두 다른 조각을 다른 줄로 나누는 기준.

발표 자료에서는 본문 옆에 다른 색, 다른 크기로 코멘트나 부연 설명을 붙여 두는 일이 많다.
그대로 한 줄로 두면 서로 다른 내용이 한 입력에 섞이므로, 색도 다르고 크기도 다른 조각은 줄을 나눈다.
다만 다음은 나누지 않는다.
  - 문장 가운데에 끼어 있는 조각 (양옆 글의 모양이 같다. 강조한 숫자, 주석 번호 등)
  - 아주 짧은 조각 (떼어 내면 혼자서는 뜻이 없다)
색만 다르거나 크기만 다른 경우도 나누지 않는다.
PDF(글자 단위)와 PPTX(조각 run 단위)가 같은 기준을 쓴다.
"""
from __future__ import annotations

from typing import List, Tuple

SIZE_RATIO = 0.12     # 글자 크기가 이 비율보다 많이 다르면 다른 크기로 본다
COLOR_GAP = 0.08      # 색 성분(0~1)이 이보다 많이 다르면 다른 색으로 본다
MIN_CHARS = 4         # 보이는 글자가 이보다 적은 조각은 떼어 내지 않는다
DEFAULT = "default"   # PPTX에서 색을 따로 정하지 않은 글(테마의 기본 글자색)


def _rgb(color):
    """비교할 수 있는 RGB로. 회색(숫자 1개), CMYK(4개)도 받는다. 모르는 꼴은 그대로 둔다."""
    if isinstance(color, (list, tuple)):
        if len(color) == 1:
            return (color[0],) * 3
        if len(color) == 3:
            return tuple(color)
        if len(color) == 4:
            c, m, y, k = color
            return (1.0 - min(1.0, c + k), 1.0 - min(1.0, m + k), 1.0 - min(1.0, y + k))
    return color


def color_differs(a, b) -> bool:
    a, b = _rgb(a), _rgb(b)
    if a is None or b is None:
        return False                               # 색을 모르면 다르다고 하지 않는다
    if isinstance(a, tuple) and isinstance(b, tuple) and len(a) == len(b) == 3:
        return max(abs(x - y) for x, y in zip(a, b)) > COLOR_GAP
    # 기본 글자색과 검정에 가까운 색은 같은 것으로 본다(기본 글자색은 대개 검정 계열)
    dark = lambda v: v == DEFAULT or (isinstance(v, tuple) and len(v) == 3 and max(v) <= 0.25)
    if dark(a) and dark(b):
        return False
    return a != b


def size_differs(a: float, b: float) -> bool:
    return abs(a - b) > SIZE_RATIO * max(a, b, 1.0)


def both_differ(size_a: float, color_a, size_b: float, color_b) -> bool:
    """색도 다르고 크기도 다른가."""
    return size_differs(size_a, size_b) and color_differs(color_a, color_b)


def cut_points(pieces: List[Tuple[float, object, int]]) -> List[int]:
    """줄을 나눌 자리.

    pieces: 이웃끼리 색·크기가 모두 다른 조각들의 (글자 크기, 색, 보이는 글자 수)
    반환: 나눌 경계의 번호 목록. i는 i번 조각과 i+1번 조각 사이를 뜻한다.
    """
    n = len(pieces)
    if n < 2:
        return []

    def alike(i: int, j: int) -> bool:
        return not size_differs(pieces[i][0], pieces[j][0]) and not color_differs(pieces[i][1], pieces[j][1])

    keep = []
    for i in range(n - 1):
        if any(alike(i, j) for j in range(i + 2, n)):
            continue                               # 앞 조각의 모양이 뒤에서 다시 이어진다 → 사이의 조각은 문장 속 강조
        if any(alike(i + 1, j) for j in range(i)):
            continue                               # 뒤 조각의 모양이 앞에서 이미 나왔다 → 마찬가지
        keep.append(i)
    while keep:                                    # 너무 짧은 조각이 생기는 경계는 버린다
        edges = [-1] + keep + [n - 1]
        sizes = [sum(p[2] for p in pieces[a + 1:b + 1]) for a, b in zip(edges, edges[1:])]
        short = next((k for k, s in enumerate(sizes) if s < MIN_CHARS), None)
        if short is None:
            break
        keep.pop(short - 1 if short > 0 else 0)
    return keep
