"""2단계 설정 파일(screen_options.txt). 메모장으로 고치거나 정답 붙이는 화면에서 바꾼다.

    title_weight   쪽 제목 점수를 글 점수에 섞는 비율. 0이면 제목을 반영하지 않는다(기본).
"""
from __future__ import annotations

from pathlib import Path

MAX_TITLE_WEIGHT = 0.9

DEFAULT_TEXT = """# 2단계(걸러내기)의 설정입니다. 메모장으로 고친 뒤 screen.bat 을 다시 실행하면 반영됩니다.
# label.bat 화면의 '쪽 제목 반영'에서 바꿔도 이 파일에 적힙니다.
#
# title_weight : 쪽 제목의 점수를 그 쪽에 있는 덩어리와 줄의 점수에 섞는 비율 (0 ~ 0.9)
#     0 이면 제목을 반영하지 않습니다 (기본).
#     최종 점수 = (1 - title_weight) × 글 점수 + title_weight × 제목 점수
#     예: 0.3 이면 글 70%, 제목 30%
#     켜면 비교 화면에 '반영 전 → 후'의 수치 변화와, 비율을 바꿨을 때의 수치가 함께 나옵니다.

title_weight = 0
"""


def check_title_weight(value) -> float:
    try:
        w = float(value)
    except (TypeError, ValueError):
        raise ValueError("제목 반영 비율은 숫자여야 합니다 (예: 0.3)")
    if not 0.0 <= w <= MAX_TITLE_WEIGHT:
        raise ValueError("제목 반영 비율은 0 이상 %.1f 이하여야 합니다 (지금 %s)" % (MAX_TITLE_WEIGHT, value))
    return round(w, 4)


def _read(path: Path) -> str:
    path = Path(path)
    if not path.exists():
        path.write_text(DEFAULT_TEXT, encoding="utf-8")
    for enc in ("utf-8-sig", "cp949"):             # 메모장이 다른 인코딩으로 저장했을 때 대비
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("설정 파일을 읽을 수 없습니다(인코딩): %s" % path)


def read_options(path: Path) -> dict:
    """설정 파일을 읽는다. 파일이 없으면 기본값으로 새로 만든다."""
    out = {"title_weight": 0.0}
    for line in _read(path).splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        if key == "title_weight":
            try:
                out["title_weight"] = check_title_weight(value)
            except ValueError as exc:
                raise ValueError("설정 파일(%s): %s" % (path, exc))
    return out


def write_option(path: Path, key: str, value) -> None:
    """설정 하나를 바꿔 적는다. 설명 줄은 그대로 둔다."""
    lines, done = _read(path).splitlines(), False
    for i, line in enumerate(lines):
        body = line.split("#", 1)[0]
        if "=" in body and body.split("=", 1)[0].strip() == key:
            lines[i], done = "%s = %s" % (key, value), True
    if not done:
        lines.append("%s = %s" % (key, value))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
