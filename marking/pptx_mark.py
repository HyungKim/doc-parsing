"""PPTX 사본에 표시를 넣는다. 이미 쓰고 있는 python-pptx만 쓴다.

    글상자의 글  글자에 형광펜 색을 넣는다(줄이면 그 줄, 덩어리면 그 덩어리의 줄들). 슬라이드에서 같은 글을 찾아 넣는다.
    표의 행      (5.1) 그 행의 칸에 든 글자에 형광펜 색을 넣는다. 표 전체에 네모를 얹지 않는다.
                 어느 표의 몇 번째 행·칸인지는 글을 뽑을 때 적어 둔 것(도형 번호와 행·열)으로 찾는다.
    찾지 못한 것  그 덩어리의 자리에 반투명 노란 네모를 얹는다. PowerPoint에서 골라서 지울 수 있다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

FILL = "FFE600"           # 네모의 색(형광 노랑)
FILL_ALPHA = "32000"      # 네모의 불투명도 32%
EDGE = (0xD9, 0xA4, 0x00)
HIGHLIGHT = "FFFF00"      # 글자 형광펜 색
BOX_NAME = "검토 표시"

# a:rPr 안에서 a:highlight 보다 앞에 와야 하는 것들(이 순서를 어기면 PowerPoint가 파일을 고치려 든다)
_BEFORE = ("ln", "noFill", "solidFill", "gradFill", "blipFill", "pattFill", "grpFill", "effectLst", "effectDag")


def _squeeze(text: str) -> str:
    return "".join(text.split())


def _paragraphs(slide) -> list:
    """슬라이드의 모든 문단(묶음 도형, 표 안 포함): [(글자를 붙인 것, 글자마다 몇 번째 run인가, run 목록)]"""
    from pptx.oxml.ns import qn
    out = []
    for p in slide._element.iter(qn("a:p")):
        runs, chars, owner = [], [], []
        for child in p:
            if child.tag not in (qn("a:r"), qn("a:fld")):
                continue
            t = child.find(qn("a:t"))
            text = _squeeze(t.text or "") if t is not None else ""
            runs.append(child)
            chars.append(text)
            owner.extend([len(runs) - 1] * len(text))
        whole = "".join(chars)
        if whole:
            out.append((whole, owner, runs))
    return out


def _set_highlight(run) -> None:
    from lxml import etree
    from pptx.oxml.ns import qn
    rpr = run.find(qn("a:rPr"))
    if rpr is None:
        rpr = etree.Element(qn("a:rPr"))
        run.insert(0, rpr)
    for old in rpr.findall(qn("a:highlight")):
        rpr.remove(old)
    hl = etree.Element(qn("a:highlight"))
    etree.SubElement(hl, qn("a:srgbClr")).set("val", HIGHLIGHT)
    pos = 0
    before = {qn("a:" + n) for n in _BEFORE}
    for i, child in enumerate(rpr):
        if child.tag in before:
            pos = i + 1
    rpr.insert(pos, hl)


def _highlight_text(paras: list, text: str) -> bool:
    """슬라이드에서 이 글과 같은 문단(또는 이 글을 품은 문단)을 찾아 글자에 형광펜 색을 넣는다. 찾았으면 True"""
    target = _squeeze(text)
    if len(target) < 2:
        return False
    hit = False
    for whole, owner, runs in paras:               # 1) 문단 전체가 이 글과 같은 것은 모두
        if whole == target:
            for r in runs:
                _set_highlight(r)
            hit = True
    if hit:
        return True
    for whole, owner, runs in paras:               # 2) 이 글이 문단의 일부인 것(한 문단이 여러 줄로 나뉘어 뽑힌 경우). 처음 하나만
        at = whole.find(target) if len(target) >= 4 else -1
        if at >= 0:
            for k in sorted(set(owner[at:at + len(target)])):
                _set_highlight(runs[k])
            return True
    for whole, owner, runs in paras:               # 3) 뽑을 때 앞에 번호가 붙은 줄("1. 내용"): 문단이 이 글의 뒷부분과 같은 것
        if len(whole) >= 4 and len(whole) * 2 >= len(target) and target.endswith(whole):
            for r in runs:
                _set_highlight(r)
            return True
    return False


def _highlight_cells(slide, shape_id: int, cells: list) -> bool:
    """도형 번호가 shape_id인 표에서 cells[(행, 열), …]의 글자에 형광펜 색을 넣는다. 하나라도 넣었으면 True"""
    from pptx.oxml.ns import qn
    for frame in slide._element.iter(qn("p:graphicFrame")):
        nv = frame.find(qn("p:nvGraphicFramePr"))
        pr = nv.find(qn("p:cNvPr")) if nv is not None else None
        if pr is None or pr.get("id") != str(shape_id):
            continue
        tbl = next(frame.iter(qn("a:tbl")), None)
        if tbl is None:
            continue
        trs = tbl.findall(qn("a:tr"))
        hit = False
        for r, c in cells:
            if not 0 <= r < len(trs):
                continue
            tcs = trs[r].findall(qn("a:tc"))
            if not 0 <= c < len(tcs):
                continue
            for p in tcs[c].iter(qn("a:p")):
                for child in p:
                    if child.tag not in (qn("a:r"), qn("a:fld")):
                        continue
                    t = child.find(qn("a:t"))
                    if t is not None and (t.text or "").strip():
                        _set_highlight(child)
                        hit = True
        return hit
    return False


def _add_box(slide, box, width: int, height: int, score: float) -> None:
    from lxml import etree
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Pt

    pad_x, pad_y = 0.004, 0.006                     # 글자에 딱 붙지 않게 조금 넓힌다
    x0, y0 = max(0.0, box[0] - pad_x), max(0.0, box[1] - pad_y)
    x1, y1 = min(1.0, box[2] + pad_x), min(1.0, box[3] + pad_y)
    if x1 - x0 < 1e-4 or y1 - y0 < 1e-4:
        return
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Emu(int(x0 * width)), Emu(int(y0 * height)),
                                   Emu(int((x1 - x0) * width)), Emu(int((y1 - y0) * height)))
    shape.name = "%s %.2f" % (BOX_NAME, score)
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(FILL)
    clr = shape._element.spPr.find(qn("a:solidFill")).find(qn("a:srgbClr"))
    if clr is not None:                             # 반투명하게(아래 글이 비쳐 보이게)
        etree.SubElement(clr, qn("a:alpha")).set("val", FILL_ALPHA)
    shape.line.color.rgb = RGBColor(*EDGE)
    shape.line.width = Pt(1.25)


def mark_pptx(src: Path, dst: Path, marks: list, slide_numbers: List[int]) -> dict:
    """marks: core.Mark 목록. slide_numbers: 쪽 번호(1부터) → 파일 안의 실제 슬라이드 번호(숨긴 슬라이드는 뽑을 때 빠진다).

    반환: {"marks": 표시한 수, "text": 글자에 형광펜을 넣은 것의 수, "rows": 그 가운데 표의 행, "boxes": 얹은 네모 수,
           "fallback": 네모로 대신한 것의 수, "held": 표시하지 않기로 한 줄인데 네모에 함께 덮인 줄 수, "skipped": 넘긴 수}
    """
    from pptx import Presentation

    prs = Presentation(str(src))
    slides = list(prs.slides)
    width, height = int(prs.slide_width), int(prs.slide_height)
    by_page: Dict[int, list] = {}
    for m in marks:
        by_page.setdefault(int(m.page), []).append(m)
    stats = {"marks": 0, "text": 0, "rows": 0, "boxes": 0, "fallback": 0, "held": 0, "skipped": 0}
    for number in sorted(by_page):
        index = (slide_numbers[number - 1] if 1 <= number <= len(slide_numbers) else number) - 1
        if not 0 <= index < len(slides):
            stats["skipped"] += len(by_page[number])
            continue
        slide = slides[index]
        paras = None
        boxed = set()
        for m in by_page[number]:
            if paras is None:
                paras = _paragraphs(slide)
            cells = getattr(m, "cells", None)
            if m.table and cells:                   # 표의 행: 그 행의 칸에 든 글자에만
                if _highlight_cells(slide, cells[0], cells[1]):
                    stats["text"] += 1
                    stats["rows"] += 1
                    stats["marks"] += 1
                    continue
            elif not m.table:
                # 글상자 안의 글은 글자에 형광펜 색을 넣는다(글상자의 크기는 어림한 값이라 네모를 얹으면 글과 어긋날 수 있다)
                picked = getattr(m, "texts", None)  # 표시하지 않는 규칙에 걸린 줄을 뺀 나머지. None이면 모든 줄
                texts = [m.text] if m.unit == "line" else (list(picked) if picked is not None else [t for t in m.text.split("\n") if t.strip()])
                found = [_highlight_text(paras, t) for t in texts]
                if found and all(found):
                    stats["text"] += 1
                    stats["marks"] += 1
                    continue
            stats["fallback"] += 1
            stats["held"] += int(getattr(m, "held", 0) or 0)
            if m.block_id not in boxed:             # 같은 덩어리에는 네모를 하나만
                boxed.add(m.block_id)
                _add_box(slide, m.box, width, height, m.score)
                stats["boxes"] += 1
            stats["marks"] += 1
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(dst))
    return stats
