"""Docling 방식(B)과 결합 방식(C = Docling의 영역·순서·분류 + A의 글자·규칙).

Docling이 설치되어 있지 않으면 이 모듈을 불러오는 쪽에서 B와 C를 건너뛴다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .layout import xy_order
from .model import Block, Document, OutBlock, PageOut
from .pdf_common import chars_to_blocks
from .textnorm import clean, one_line

TITLE_LABELS = ("title", "section_header")
FURNITURE_LABELS = ("page_header", "page_footer")
Box = Tuple[float, float, float, float]


def unavailable_reason() -> str:
    try:
        import docling  # noqa: F401
        return ""
    except Exception as exc:                      # 설치 안 됨, 의존 패키지 문제 등
        return "%s: %s" % (type(exc).__name__, exc)


@dataclass
class Region:
    order: int
    label: str
    furniture: bool
    box: Box                                      # 0~1 정규화, 원점 왼쪽 위
    kind: str = "text"                            # text | table
    text: str = ""
    rows: List[List[str]] = field(default_factory=list)
    cells: List[List[Optional[Box]]] = field(default_factory=list)


def _norm_box(bbox, width: float, height: float) -> Box:
    l, t, r, b = float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)
    if "BOTTOM" in str(getattr(bbox, "coord_origin", "")).upper():
        t, b = height - t, height - b
    x0, x1 = sorted((l / width, r / width))
    y0, y1 = sorted((t / height, b / height))
    return (x0, y0, x1, y1)


class DoclingRunner:
    """모델을 한 번만 불러와 여러 문서에 재사용한다."""

    def __init__(self, artifacts_path: Optional[str] = None):
        t0 = time.time()
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = False                       # 스캔본이 없으므로 OCR은 끈다(가장 큰 속도 차이)
        opts.do_table_structure = True
        if artifacts_path:
            opts.artifacts_path = artifacts_path  # 미리 받아 둔 모델 폴더(오프라인용)
        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
        try:
            self.converter.initialize_pipeline(InputFormat.PDF)
        except Exception:
            pass                                  # 미리 불러오기 실패 시 첫 변환 때 불러온다
        self.load_seconds = time.time() - t0

    def regions(self, path: str) -> Tuple[Dict[int, List[Region]], float]:
        from docling_core.types.doc import ContentLayer

        t0 = time.time()
        doc = self.converter.convert(str(path)).document
        out: Dict[int, List[Region]] = {}
        layers = {ContentLayer.BODY, ContentLayer.FURNITURE}
        for item, _level in doc.iterate_items(included_content_layers=layers, traverse_pictures=True):
            provs = getattr(item, "prov", None) or []
            if not provs:
                continue
            prov = provs[0]
            page = doc.pages.get(prov.page_no)
            if page is None or not page.size.width or not page.size.height:
                continue
            w, h = float(page.size.width), float(page.size.height)
            label = str(getattr(item.label, "value", item.label))
            layer = str(getattr(getattr(item, "content_layer", None), "value", ""))
            region = Region(order=0, label=label, furniture=(layer == "furniture" or label in FURNITURE_LABELS),
                            box=_norm_box(prov.bbox, w, h))
            data = getattr(item, "data", None)
            if label == "table" and data is not None and getattr(data, "table_cells", None) is not None:
                region.kind = "table"
                n_rows, n_cols = int(data.num_rows or 0), int(data.num_cols or 0)
                region.rows = [[""] * n_cols for _ in range(n_rows)]
                region.cells = [[None] * n_cols for _ in range(n_rows)]
                for cell in data.table_cells:
                    r, c = cell.start_row_offset_idx, cell.start_col_offset_idx
                    if not (0 <= r < n_rows and 0 <= c < n_cols):
                        continue
                    region.rows[r][c] = clean(cell.text or "")
                    if cell.bbox is not None:
                        region.cells[r][c] = _norm_box(cell.bbox, w, h)
                if not region.rows:
                    continue
            else:
                text = clean(getattr(item, "text", "") or "")
                if not text:
                    continue
                marker = getattr(item, "marker", "") or ""
                if getattr(item, "enumerated", False) and marker and not text.startswith(marker):
                    text = "%s %s" % (marker, text)
                region.text = text
            bucket = out.setdefault(prov.page_no, [])
            region.order = len(bucket)
            bucket.append(region)
        return out, time.time() - t0


# ---------------------------------------------------------------- B: Docling 단독

def alone(regions: Dict[int, List[Region]], page_map: List[int]) -> List[PageOut]:
    outs: List[PageOut] = []
    for i, source_no in enumerate(page_map, 1):
        out = PageOut(number=i)
        rs = regions.get(source_no, [])
        title = next((r for r in rs if r.kind == "text" and not r.furniture and r.label == "title"), None)
        if title is None:
            title = next((r for r in rs if r.kind == "text" and not r.furniture and r.label == "section_header"), None)
        if title is not None:
            out.title, out.title_reason, out.title_box = one_line(title.text), "Docling 분류", title.box
        for r in rs:
            if r is title:
                continue
            if r.kind == "table":
                text = "\n".join(x for x in (" | ".join(c for c in row if c) for row in r.rows) if x)
            else:
                text = r.text
            if not text:
                continue
            if r.furniture:
                out.removed.append((text, "Docling 머리글·바닥글 분류"))
            else:
                out.blocks.append(OutBlock(text=text, box=r.box, kind=r.kind))
        outs.append(out)
    return outs


# ---------------------------------------------------------------- C: 결합

def _area(box: Box) -> float:
    return max(box[2] - box[0], 0.0) * max(box[3] - box[1], 0.0)


def _find_region(regs: List[Region], cx: float, cy: float, pad: float = 0.006) -> Optional[Region]:
    hits = [r for r in regs if r.box[0] - pad <= cx <= r.box[2] + pad and r.box[1] - pad <= cy <= r.box[3] + pad]
    return min(hits, key=lambda r: _area(r.box)) if hits else None


def hybrid(base: Document, regions: Dict[int, List[Region]], page_map: List[int]) -> Document:
    """A 방식으로 읽은 문서(base)의 블록을 Docling 영역에 맞춰 나누고 Docling 순서로 늘어놓는다.

    - 글자와 글자 크기: A (PDF는 PyMuPDF, PPTX는 python-pptx)
    - 표의 칸 구조: Docling이 찾았으면 Docling, 아니면 A
    - 읽는 순서와 제목/머리글/바닥글 분류: Docling
    - Docling이 놓친 글자: A의 순서(X-Y cut)에서 바로 앞 블록 뒤에 끼워 넣는다
    이후 반복 문구 제거와 제목 확정은 A와 같은 규칙으로 처리한다.
    """
    for page, source_no in zip(base.pages, page_map):
        regs = regions.get(source_no, [])
        w, h = max(page.width, 1.0), max(page.height, 1.0)
        text_regs = [r for r in regs if r.kind == "text"]
        table_regs = [r for r in regs if r.kind == "table"]

        blocks = page.blocks
        chars = getattr(page, "chars", None)
        if chars is not None:                      # PDF: Docling의 표 구조로 다시 묶는다
            dl_tables = []
            for r in table_regs:
                cells = [[(c[0] * w, c[1] * h, c[2] * w, c[3] * h) if c else None for c in row] for row in r.cells]
                if any(c for row in cells for c in row):
                    b = r.box
                    dl_tables.append({"bbox": (b[0] * w, b[1] * h, b[2] * w, b[3] * h), "cells": cells})
            blocks = chars_to_blocks(chars, dl_tables or getattr(page, "native_tables", []),
                                     getattr(page, "rects", None), page.width, page.height)

        pieces: List[Block] = []
        keys: Dict[int, Optional[int]] = {}
        for block in blocks:
            if block.role == "removed":
                pieces.append(block)
                keys[id(block)] = None
                continue
            if block.kind == "table":
                cx, cy = (block.x0 + block.x1) / 2 / w, (block.y0 + block.y1) / 2 / h
                reg = _find_region(table_regs, cx, cy)
                pieces.append(block)
                keys[id(block)] = reg.order if reg else None
                continue
            run: List = []
            run_reg: Optional[Region] = None
            started = False

            def flush():
                if not run:
                    return
                piece = Block(lines=list(run), hint=block.hint)
                piece.fit_bbox()
                if len(run) == len(block.lines):            # 나뉘지 않았으면 원래 영역(도형 상자 등)을 유지
                    piece.x0, piece.y0, piece.x1, piece.y1 = block.x0, block.y0, block.x1, block.y1
                if run_reg is not None:
                    if run_reg.label in TITLE_LABELS and not piece.hint:
                        piece.hint = "title_label"
                    if run_reg.furniture:
                        for l in piece.lines:
                            l.removed = l.removed or "Docling 머리글·바닥글 분류"
                pieces.append(piece)
                keys[id(piece)] = run_reg.order if run_reg is not None else None

            for line in block.lines:
                reg = _find_region(text_regs, (line.x0 + line.x1) / 2 / w, (line.y0 + line.y1) / 2 / h)
                if started and reg is not run_reg:
                    flush()
                    run = []
                run_reg, started = reg, True
                run.append(line)
            flush()

        sizes = sorted(p.size for p in pieces if p.size > 0)
        rank = {id(b): i for i, b in enumerate(xy_order(pieces, sizes[len(sizes) // 2] if sizes else 12.0))}
        placed = sorted((p for p in pieces if keys[id(p)] is not None), key=lambda p: (keys[id(p)], rank[id(p)]))
        result = list(placed)
        previous: Optional[Block] = None
        for p in sorted(pieces, key=lambda p: rank[id(p)]):
            if keys[id(p)] is None:
                at = result.index(previous) + 1 if previous is not None and previous in result else 0
                result.insert(at, p)
            previous = p
        page.blocks = result
    return base
