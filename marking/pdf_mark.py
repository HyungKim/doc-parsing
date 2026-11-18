"""PDF 사본에 형광 표시를 넣는다. pdfplumber와 함께 깔리는 pypdfium2만 쓴다(새로 설치할 것이 없다).

표시 방식 두 가지
    annot  형광펜 주석. 쪽의 내용은 건드리지 않고 그 위에 얹는다. PDF 프로그램에서 하나씩 지울 수 있고, 메모에 점수가 들어 있다.
    paint  쪽에 반투명 노란 칠을 직접 그려 넣는다. 주석을 보여 주지 않는 프로그램이나 인쇄에서도 그대로 보인다. 지울 수 없다.

자리는 쪽 크기 대비 0~1(왼쪽 위가 원점)로 받는다. 1단계가 쓰는 pdfplumber의 좌표와 같은 기준(MediaBox, 돌린 쪽은 돌린 뒤의 모양)이다.
"""
from __future__ import annotations

import ctypes
from pathlib import Path
from typing import Dict, List, Tuple

COLOR = (255, 230, 0)          # 형광 노랑
PAINT_ALPHA = 105              # paint 방식의 진하기 (0~255)
ANNOT_ALPHA = 150              # annot 방식의 진하기 (0~255). 표처럼 넓은 곳을 덮어도 아래 글이 잘 보이게 조금 옅게


def _wide(text: str):
    """PDFium이 받는 글(UTF-16LE, 끝에 0)."""
    raw = (text + "\x00").encode("utf-16-le")
    return ctypes.cast(ctypes.create_string_buffer(raw, len(raw)), ctypes.POINTER(ctypes.c_ushort))


def _to_page(u: float, v: float, media: Tuple[float, float, float, float], rotation: int) -> Tuple[float, float]:
    """보이는 쪽에서의 자리(u 오른쪽, v 아래쪽, 0~1) → PDF 안의 좌표(왼쪽 아래 원점)."""
    l, b, r, t = media
    w, h = r - l, t - b
    if rotation == 90:
        return l + v * w, b + u * h
    if rotation == 180:
        return r - u * w, b + v * h
    if rotation == 270:
        return r - v * w, t - u * h
    return l + u * w, t - v * h


def _media_box(page) -> Tuple[float, float, float, float]:
    """쪽의 크기 상자(왼쪽, 아래, 오른쪽, 위). 쪽에 직접 적혀 있지 않고 윗단계에서 물려받은 경우에도 맞는 값을 얻는다.

    PDFium은 물려받은 MediaBox를 읽지 못하고 기본값(612×792)을 돌려주므로, 그때는 쪽이 실제로 차지하는 상자를 쓴다.
    """
    box = None
    try:
        box = page.get_mediabox(fallback_ok=False)
    except Exception:
        box = None
    if not box:
        try:
            box = page.get_bbox()
        except Exception:
            box = None
    if not box:
        w, h = page.get_size()
        rotated = int(page.get_rotation()) % 180 == 90
        box = (0.0, 0.0, h if rotated else w, w if rotated else h)
    return tuple(float(v) for v in box)


def _corners(box, media, rotation: int):
    """상자의 네 모서리(보이는 쪽 기준 왼쪽 위, 오른쪽 위, 왼쪽 아래, 오른쪽 아래)를 PDF 좌표로."""
    x0, y0, x1, y1 = box
    return [_to_page(x0, y0, media, rotation), _to_page(x1, y0, media, rotation),
            _to_page(x0, y1, media, rotation), _to_page(x1, y1, media, rotation)]


def _clean_rows(rows) -> List[tuple]:
    out, seen = [], set()
    for r in rows:
        x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in r)
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4:
            continue
        key = (round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4))
        if key not in seen:
            seen.add(key)
            out.append((x0, y0, x1, y1))
    return out


def mark_pdf(src: Path, dst: Path, marks: list, method: str = "annot", author: str = "1차 걸러내기") -> dict:
    """marks: core.Mark 목록(page는 1부터). 반환: {"marks": 표시한 수, "pages": 표시가 들어간 쪽 수, "skipped": 쪽이 없어 넘긴 수}"""
    import pypdfium2 as pdfium
    import pypdfium2.raw as c

    if method not in ("annot", "paint"):
        raise ValueError("표시 방식을 알 수 없습니다: %s" % method)
    pdf = pdfium.PdfDocument(str(src))
    by_page: Dict[int, list] = {}
    for m in marks:
        by_page.setdefault(int(m.page), []).append(m)
    done = skipped = 0
    try:
        total = len(pdf)
        for number in sorted(by_page):
            if not 1 <= number <= total:
                skipped += len(by_page[number])
                continue
            page = pdf[number - 1]
            try:
                media = _media_box(page)
                rotation = int(page.get_rotation()) % 360
                painted = set()                     # 같은 자리(줄의 자리를 몰라 덩어리 전체로 대신한 것)는 한 번만
                for m in by_page[number]:
                    rows = [r for r in _clean_rows(m.rows) if r not in painted]
                    painted.update(rows)
                    if not rows:
                        continue
                    quads = [_corners(r, media, rotation) for r in rows]
                    if method == "annot":
                        a = c.FPDFPage_CreateAnnot(page.raw, c.FPDF_ANNOT_HIGHLIGHT)
                        if not a:
                            continue
                        xs = [p[0] for q in quads for p in q]
                        ys = [p[1] for q in quads for p in q]
                        c.FPDFAnnot_SetRect(a, c.FS_RECTF(min(xs), max(ys), max(xs), min(ys)))
                        for q in quads:
                            c.FPDFAnnot_AppendAttachmentPoints(a, c.FS_QUADPOINTSF(q[0][0], q[0][1], q[1][0], q[1][1],
                                                                                     q[2][0], q[2][1], q[3][0], q[3][1]))
                        c.FPDFAnnot_SetColor(a, c.FPDFANNOT_COLORTYPE_Color, COLOR[0], COLOR[1], COLOR[2], ANNOT_ALPHA)
                        c.FPDFAnnot_SetFlags(a, c.FPDF_ANNOT_FLAG_PRINT)
                        c.FPDFAnnot_SetStringValue(a, b"Contents", _wide(getattr(m, "note", "") or "검토 필요 · 점수 %.2f" % m.score))
                        c.FPDFAnnot_SetStringValue(a, b"T", _wide(author))
                        c.FPDFPage_CloseAnnot(a)
                    else:
                        for q in quads:
                            xs, ys = [p[0] for p in q], [p[1] for p in q]
                            o = c.FPDFPageObj_CreateNewRect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
                            c.FPDFPageObj_SetFillColor(o, COLOR[0], COLOR[1], COLOR[2], PAINT_ALPHA)
                            c.FPDFPageObj_SetBlendMode(o, b"Multiply")      # 글자 위에 겹쳐도 글자가 그대로 보이게
                            c.FPDFPath_SetDrawMode(o, c.FPDF_FILLMODE_ALTERNATE, 0)
                            c.FPDFPage_InsertObject(page.raw, o)
                    done += 1
                if method == "paint":
                    c.FPDFPage_GenerateContent(page.raw)
                else:
                    try:                            # 한 번 그려 보게 하면 주석의 모양이 파일에 함께 저장된다(어느 프로그램에서나 보이게)
                        page.render(scale=0.2)
                    except Exception:
                        pass
            finally:
                page.close()
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        pdf.save(str(dst))
    finally:
        pdf.close()
    return {"marks": done, "pages": len([n for n in by_page if 1 <= n <= total]), "skipped": skipped}
