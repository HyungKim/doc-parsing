"""모든 방식이 공유하는 중간 자료 구조.

PDF든 PPTX든 일단 이 형태(텍스트 + 좌표 + 글자 크기)로 바꾼 뒤
같은 규칙(순서 정렬, 반복 문구 제거, 제목 추출)을 적용한다.
좌표 단위는 포인트(1/72인치), 원점은 페이지 왼쪽 위.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class Line:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float = 0.0
    bold: bool = False
    angle: float = 0.0            # 글자 방향(도). 0이면 가로쓰기
    is_para: bool = False         # True면 이 줄이 이미 완성된 문단(PPTX)
    list_start: bool = False      # 글머리 기호나 번호로 시작한 줄
    trailing_space: bool = False  # PDF에서 줄 끝에 공백 글자가 있었는지
    first_word_w: float = 0.0     # 첫 단어의 너비(문단 경계 판단용)
    first_char_w: float = 0.0
    removed: str = ""             # 제거되었다면 그 이유


@dataclass
class Block:
    kind: str = "text"            # text | table
    lines: List[Line] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)   # 표일 때
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    size: float = 0.0
    bold: bool = False
    hint: str = ""                # title_ph, subtitle_ph, chart ...
    role: str = "body"            # body | title | removed
    reason: str = ""
    text: str = ""                # 최종 텍스트

    def fit_bbox(self) -> None:
        if self.lines:
            self.x0 = min(l.x0 for l in self.lines)
            self.y0 = min(l.y0 for l in self.lines)
            self.x1 = max(l.x1 for l in self.lines)
            self.y1 = max(l.y1 for l in self.lines)
            self.size = max(l.size for l in self.lines)
            self.bold = all(l.bold for l in self.lines)


@dataclass
class Page:
    number: int
    width: float
    height: float
    blocks: List[Block] = field(default_factory=list)
    before: str = ""              # 아무 처리 없이 읽은 텍스트
    before_units: List[str] = field(default_factory=list)   # 같은 글을 라이브러리가 따로 꺼내 준 단위별로 나눈 것
    before_boxes: list = field(default_factory=list)        # 단위별 위치 (x0, y0, x1, y1), 쪽 크기 대비 0~1. 모르면 None
    image: Optional[bytes] = None  # 페이지 이미지(JPEG), 있으면 리포트에 표시
    note: str = ""


@dataclass
class Document:
    path: str
    kind: str                     # pdf | pptx
    pages: List[Page] = field(default_factory=list)
    info: dict = field(default_factory=dict)


@dataclass
class OutBlock:
    text: str
    box: Tuple[float, float, float, float]   # 0~1 로 정규화한 x0, y0, x1, y1
    kind: str = "text"


@dataclass
class PageOut:
    number: int
    title: str = ""
    title_reason: str = "제목 없음"
    blocks: List[OutBlock] = field(default_factory=list)   # 읽는 순서대로(제목 제외)
    title_box: Optional[Tuple[float, float, float, float]] = None
    removed: List[Tuple[str, str]] = field(default_factory=list)   # (문구, 이유)

    @property
    def body(self) -> str:
        return "\n".join(b.text for b in self.blocks)


@dataclass
class MethodResult:
    key: str
    label: str
    pages: List[PageOut] = field(default_factory=list)
    seconds: float = 0.0
    error: str = ""
    note: str = ""
