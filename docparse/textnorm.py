"""텍스트 정리 규칙. PDF와 PPTX 양쪽에 똑같이 적용해 결과 차이를 줄인다."""
from __future__ import annotations

import re
import unicodedata

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_SPACES = re.compile(r"[   -   　\t\x0b\x0c]")
_INVISIBLE = re.compile(r"[​-‏  ⁠﻿­]")
_PRIVATE = re.compile(r"[-�]")       # 기호 글꼴의 글머리 기호 등
_CONTROL = re.compile(r"[\x00-\x08\x0e-\x1f\x7f]")

# 자동 글머리 기호로 쓰이는 문자. PDF에는 찍히고 PPTX 텍스트에는 없으므로 양쪽 모두에서 뗀다.
_BULLET = re.compile(r"^\s*(?:[•◦▪▫■□●○◆◇▶▷►▸‣⁃∙·✓✔➢➤]\s*|[-–—]\s+)")
_BULLET_ONLY = re.compile(r"^\s*[•◦▪▫■□●○◆◇▶▷►▸‣⁃∙·✓✔➢➤\-–—]\s*$")
# 번호 목록의 시작: "1." "2)" "(3)" "가." "a)" "①" 등
_MARKER = re.compile(
    r"^\s*(?:\(?\d{1,2}[.)]|\(?[A-Za-z][.)]|\(?[가-하][.)]|[①-⑳]|[ⅰ-ⅹⅠ-Ⅹ]{1,4}[.)]|[IVX]{1,4}[.)]|[ivx]{1,4}[.)])(?:\s|$)"
)
_MARKER_ONLY = re.compile(
    r"^\s*(?:\(?\d{1,2}[.)]|\(?[A-Za-z][.)]|\(?[가-하][.)]|[①-⑳]|[ⅰ-ⅹⅠ-Ⅹ]{1,4}[.)]|[IVX]{1,4}[.)]|[ivx]{1,4}[.)])\s*$"
)


def clean(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    for k, v in _LIGATURES.items():
        if k in s:
            s = s.replace(k, v)
    s = _SPACES.sub(" ", s)
    s = _INVISIBLE.sub("", s)
    s = _PRIVATE.sub("", s)
    s = _CONTROL.sub("", s)
    s = re.sub(r" {2,}", " ", s)
    return s.strip()


_DASH_NUMBER = re.compile(r"^\s*[-–—]\s*\d+\s*[-–—]\s*$")     # "- 3 -" 같은 쪽 번호는 글머리 기호가 아니다


def strip_bullet(s: str) -> str:
    if _DASH_NUMBER.match(s):
        return s.strip()
    return _BULLET.sub("", s, count=1).strip()


def has_bullet(s: str) -> bool:
    return bool(_BULLET.match(s)) and not _DASH_NUMBER.match(s)


def is_bullet_only(s: str) -> bool:
    return bool(_BULLET_ONLY.match(s))


def has_marker(s: str) -> bool:
    return bool(_MARKER.match(s))


def is_marker_only(s: str) -> bool:
    return bool(_MARKER_ONLY.match(s))


def is_cjk(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch)
    return (
        0xAC00 <= o <= 0xD7A3      # 한글 음절
        or 0x1100 <= o <= 0x11FF   # 한글 자모
        or 0x3130 <= o <= 0x318F
        or 0x3040 <= o <= 0x30FF   # 가나
        or 0x4E00 <= o <= 0x9FFF   # 한자
        or 0x3400 <= o <= 0x4DBF
    )


def repeat_key(s: str) -> str:
    """반복 문구 비교용 열쇠. 숫자는 #으로 바꿔 쪽 번호처럼 숫자만 다른 것을 같게 본다."""
    s = unicodedata.normalize("NFKC", s).casefold()
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def compare_key(s: str) -> str:
    """방식 간/형식 간 일치율 계산용. 공백, 표 구분선, 글머리 기호 차이를 무시한다."""
    s = unicodedata.normalize("NFKC", s).casefold()
    s = s.replace("|", "")
    s = re.sub(r"\s+", "", s)
    return s


def one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()
