"""매 페이지 반복되는 문구(머리글, 바닥글, 쪽 번호, 워터마크, 보안 문구) 찾기.

세 가지 근거를 쓴다.
  1. 키워드: 줄 전체가 사실상 "Confidential", "대외비" 같은 보안 문구인 경우
  2. 위치 + 빈도: 여러 페이지의 같은 자리에 같은 글(숫자만 다른 것 포함)이 반복되는 경우
  3. 대각선 글자: 워터마크로 보고 더 낮은 빈도에서도 제거
본문 한가운데의 글은 훨씬 많은 페이지(기본 60%)에서 반복되어야만 지운다.
"""
from __future__ import annotations

import math
import re
from typing import List

from .model import Page
from .textnorm import one_line, repeat_key

KEYWORDS = re.compile(
    r"strictly\s+confidential|confidential|대\s*외\s*비|사\s*외\s*비|극\s*비|internal\s+use(\s+only)?"
    r"|proprietary|do\s+not\s+(distribute|copy|share)|all\s+rights\s+reserved|copyright"
    r"|무단\s*(전재|복제|배포)(\s*금지)?|[©ⓒ]",
    re.I,
)

TOP_ZONE = 0.12
BOTTOM_ZONE = 0.88


def is_diagonal(angle: float) -> bool:
    a = abs(angle) % 90.0
    return 10.0 < a < 80.0


def keyword_hit(text: str, in_margin: bool, extra=None) -> bool:
    t = one_line(text)
    if len(t) > 80:
        return False
    hit = bool(KEYWORDS.search(t)) or bool(extra and extra.search(t))
    if not hit:
        return False
    rest = KEYWORDS.sub(" ", t)
    if extra:
        rest = extra.sub(" ", rest)
    words = re.findall(r"[0-9A-Za-z가-힣]+", rest)
    return len(words) <= (4 if in_margin else 1)


def mark_repeats(pages: List[Page], body_size: float, ratio: float = 0.6, extra_keywords=None) -> None:
    n = len(pages)
    occurrences = {}
    for pi, page in enumerate(pages):
        for block in page.blocks:
            if block.kind != "text" or block.role == "removed" or block.hint == "title_ph":
                continue
            for line in block.lines:
                if line.removed or not line.text:
                    continue
                cx = (line.x0 + line.x1) / 2 / max(page.width, 1.0)
                cy = (line.y0 + line.y1) / 2 / max(page.height, 1.0)
                zone = "top" if cy < TOP_ZONE else "bottom" if cy > BOTTOM_ZONE else "body"
                diagonal = is_diagonal(line.angle)
                if keyword_hit(line.text, zone != "body" or diagonal, extra_keywords):
                    line.removed = "보안 문구"
                    continue
                key = repeat_key(line.text)
                if not key:
                    continue
                small = line.size <= body_size * 1.15
                relaxed = diagonal or (zone != "body" and small)
                occurrences.setdefault(key, []).append((pi, line, cx, cy, zone, relaxed, diagonal))

    if n < 2:
        _finish(pages)
        return
    strict_need = max(3, math.ceil(ratio * n)) if n >= 3 else None
    relaxed_need = max(3, math.ceil(0.2 * n)) if n >= 3 else 2

    for key, items in occurrences.items():
        if len({it[0] for it in items}) < 2:
            continue
        clusters: List[list] = []
        for it in items:                                   # 같은 자리끼리 묶기
            for cl in clusters:
                ref = cl[0]
                if abs(ref[2] - it[2]) <= 0.04 and abs(ref[3] - it[3]) <= 0.025:
                    cl.append(it)
                    break
            else:
                clusters.append([it])
        for zone in ("top", "bottom"):                     # 위/아래 여백에서는 가로 위치가 달라도 묶기
            in_zone = [it for it in items if it[4] == zone]
            if in_zone:
                clusters.append(in_zone)
        for cl in clusters:
            count = len({it[0] for it in cl})
            need = relaxed_need if all(it[5] for it in cl) else strict_need
            if need is None or count < need:
                continue
            what = "워터마크" if all(it[6] for it in cl) else "반복 문구"
            for it in cl:
                if not it[1].removed:
                    it[1].removed = "%s (%d/%d쪽)" % (what, count, n)
    _finish(pages)


def _finish(pages: List[Page]) -> None:
    for page in pages:
        for block in page.blocks:
            if block.kind == "text" and block.role != "removed" and block.lines \
                    and all(l.removed for l in block.lines):
                block.role = "removed"
                block.reason = block.lines[0].removed
