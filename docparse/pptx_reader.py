"""python-pptx로 PPTX를 읽어 공통 구조로 바꾼다.

PDF로 저장했을 때 보이는 것과 같아지도록 다음을 맞춘다.
  - 숨긴 슬라이드, 숨긴 도형, 슬라이드 밖 도형은 뺀다
  - 그룹 안의 도형, 표, 차트, SmartArt의 글자도 읽는다
  - 자동 번호(1. 2. 3.)는 PDF처럼 글자로 붙인다
  - 슬라이드 마스터/레이아웃에 있는 문구는 '반복 문구'로 표시한다
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Tuple

from lxml import etree
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE, PP_PLACEHOLDER
from pptx.oxml.ns import qn

from .model import Block, Document, Line, Page
from .textnorm import clean, has_bullet, has_marker, is_cjk, strip_bullet

EMU = 12700.0
DGM = "{http://schemas.openxmlformats.org/drawingml/2006/diagram}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

TITLE_TYPES = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE, PP_PLACEHOLDER.VERTICAL_TITLE}
FURNITURE_TYPES = {PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.SLIDE_NUMBER,
                   PP_PLACEHOLDER.HEADER}

Xform = Callable[[float, float, float, float], Tuple[float, float, float, float]]


def _identity(x, y, w, h):
    return x, y, w, h


def _group_xform(grp, outer: Xform) -> Xform:
    xfrm = grp._element.find(qn("p:grpSpPr") + "/" + qn("a:xfrm"))
    if xfrm is None:
        return outer
    off, ext = xfrm.find(qn("a:off")), xfrm.find(qn("a:ext"))
    ch_off, ch_ext = xfrm.find(qn("a:chOff")), xfrm.find(qn("a:chExt"))
    if off is None or ext is None or ch_off is None or ch_ext is None:
        return outer
    ox, oy = float(off.get("x", 0)), float(off.get("y", 0))
    cx, cy = float(ch_off.get("x", 0)), float(ch_off.get("y", 0))
    sx = float(ext.get("cx", 1)) / (float(ch_ext.get("cx", 1)) or 1.0)
    sy = float(ext.get("cy", 1)) / (float(ch_ext.get("cy", 1)) or 1.0)

    def inner(x, y, w, h):
        return outer(ox + (x - cx) * sx, oy + (y - cy) * sy, w * sx, h * sy)

    return inner


# ---------------------------------------------------------------- 글자 크기

def _sz(node) -> Optional[float]:
    if node is not None and node.get("sz"):
        try:
            return int(node.get("sz")) / 100.0
        except ValueError:
            return None
    return None


def _list_style_size(lst, level: int) -> Optional[float]:
    if lst is None:
        return None
    node = lst.find(qn("a:lvl%dpPr" % (level + 1)))
    return _sz(node.find(qn("a:defRPr"))) if node is not None else None


def _body_pr_chain(shape):
    """도형 → 레이아웃 개체 틀 → 마스터 개체 틀 순서로 txBody 를 돌려준다."""
    cur = shape
    for _ in range(3):
        tx = cur._element.find(qn("p:txBody")) if cur is not None else None
        if tx is not None:
            yield tx
        try:
            cur = cur._base_placeholder
        except Exception:
            cur = None
        if cur is None:
            break


class _SizeResolver:
    def __init__(self, prs, slide):
        self.default_style = prs.part._element.find(qn("p:defaultTextStyle"))
        try:
            self.tx_styles = slide.slide_layout.slide_master._element.find(qn("p:txStyles"))
        except Exception:
            self.tx_styles = None

    def base(self, shape, level: int, ph_type) -> float:
        for tx in _body_pr_chain(shape):
            v = _list_style_size(tx.find(qn("a:lstStyle")), level)
            if v:
                return v
        if ph_type is not None and self.tx_styles is not None:
            if ph_type in TITLE_TYPES:
                tag = "p:titleStyle"
            elif ph_type in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.SUBTITLE, PP_PLACEHOLDER.OBJECT,
                             PP_PLACEHOLDER.VERTICAL_BODY, PP_PLACEHOLDER.VERTICAL_OBJECT):
                tag = "p:bodyStyle"
            else:
                tag = "p:otherStyle"
            v = _list_style_size(self.tx_styles.find(qn(tag)), level)
            if v:
                return v
        v = _list_style_size(self.default_style, level)
        return v or 18.0


def _font_scale(shape) -> float:
    body = shape._element.find(qn("p:txBody") + "/" + qn("a:bodyPr"))
    if body is not None:
        fit = body.find(qn("a:normAutofit"))
        if fit is not None and fit.get("fontScale"):
            try:
                return int(fit.get("fontScale")) / 100000.0
            except ValueError:
                pass
    return 1.0


def _anchor(shape) -> str:
    for tx in _body_pr_chain(shape):
        body = tx.find(qn("a:bodyPr"))
        if body is not None and body.get("anchor"):
            return body.get("anchor")
    return "t"


# ---------------------------------------------------------------- 자동 번호

_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _roman(n: int) -> str:
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                 (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


def _alpha(n: int) -> str:
    out = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


def _format_number(kind: str, n: int) -> str:
    if kind.startswith("circleNum"):
        return _CIRCLED[n - 1] if 1 <= n <= 20 else "(%d)" % n
    if kind.startswith("alphaLc"):
        core = _alpha(n)
    elif kind.startswith("alphaUc"):
        core = _alpha(n).upper()
    elif kind.startswith("romanLc"):
        core = _roman(n).lower()
    elif kind.startswith("romanUc"):
        core = _roman(n)
    else:
        core = str(n)
    if kind.endswith("ParenBoth"):
        return "(%s)" % core
    if kind.endswith("ParenR"):
        return "%s)" % core
    if kind.endswith("Plain"):
        return core
    return "%s." % core


# ---------------------------------------------------------------- 도형 읽기

def _wide_units(text: str) -> float:
    return sum(1.0 if is_cjk(ch) else 0.55 for ch in text)


def _is_hidden(shape) -> bool:
    for node in shape._element.iter(qn("p:cNvPr")):
        return node.get("hidden") in ("1", "true")
    return False


def _has_visible_box(shape) -> bool:
    """색을 채웠거나 테두리가 있는 도형인가(PDF에서 사각형으로 보이는 도형)."""
    el = shape._element
    sp_pr = el.find(qn("p:spPr"))
    if sp_pr is None:
        return False
    c_nv = next(iter(el.iter(qn("p:cNvSpPr"))), None)
    is_textbox = c_nv is not None and c_nv.get("txBox") in ("1", "true")
    styled = el.find(qn("p:style")) is not None and not is_textbox
    if sp_pr.find(qn("a:noFill")) is None:
        if any(sp_pr.find(qn(t)) is not None for t in ("a:solidFill", "a:gradFill", "a:pattFill", "a:blipFill")):
            return True
        if styled:
            return True
    ln = sp_pr.find(qn("a:ln"))
    if ln is not None:
        return ln.find(qn("a:noFill")) is None and (ln.find(qn("a:solidFill")) is not None or styled)
    return False


def _rotation(shape) -> float:
    try:
        r = float(shape.rotation or 0.0) % 360.0
    except Exception:
        return 0.0
    return r - 360.0 if r > 180.0 else r


class _SlideReader:
    def __init__(self, prs, slide, width: float, height: float):
        self.slide = slide
        self.w, self.h = width, height
        self.sizes = _SizeResolver(prs, slide)
        self.blocks: List[Block] = []

    def box(self, shape, xf: Xform) -> Optional[Tuple[float, float, float, float]]:
        try:
            l, t, w, h = shape.left, shape.top, shape.width, shape.height
        except Exception:
            return None
        if l is None or t is None or w is None or h is None:
            return None
        x, y, w2, h2 = xf(float(l), float(t), float(w), float(h))
        return x / EMU, y / EMU, (x + w2) / EMU, (y + h2) / EMU

    def walk(self, shapes, xf: Xform = _identity, removed_reason: str = "") -> None:
        for shape in shapes:
            try:
                self.read_shape(shape, xf, removed_reason)
            except Exception:
                continue                              # 도형 하나가 깨져도 나머지는 읽는다

    def read_shape(self, shape, xf: Xform, removed_reason: str) -> None:
        if _is_hidden(shape):
            return
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            self.walk(shape.shapes, _group_xform(shape, xf), removed_reason)
            return
        box = self.box(shape, xf)
        if box is None:
            box = (0.0, 0.0, self.w, self.h)
        x0, y0, x1, y1 = box
        if x1 <= 0 or y1 <= 0 or x0 >= self.w or y0 >= self.h:
            return                                    # 슬라이드 밖에 둔 도형

        block: Optional[Block] = None
        if getattr(shape, "has_table", False) and shape.has_table:
            block = self.table_block(shape)
        elif getattr(shape, "has_chart", False) and shape.has_chart:
            block = self.chart_block(shape)
        elif shape._element.tag == qn("p:graphicFrame"):
            block = self.smartart_block(shape)
        elif getattr(shape, "has_text_frame", False) and shape.has_text_frame:
            block = self.text_block(shape, box)
        if block is None:
            return
        if block.kind == "table" or block.hint in ("chart", "smartart"):
            block.x0, block.y0, block.x1, block.y1 = x0, y0, x1, y1
            for l in block.lines:
                l.x0, l.y0, l.x1, l.y1 = x0, y0, x1, y1
        if removed_reason:
            block.role, block.reason = "removed", removed_reason
            for l in block.lines:
                l.removed = removed_reason
        self.blocks.append(block)

    def text_block(self, shape, box) -> Optional[Block]:
        ph_type = None
        if shape.is_placeholder:
            try:
                ph_type = shape.placeholder_format.type
            except Exception:
                ph_type = None
        x0, y0, x1, y1 = box
        scale = _font_scale(shape)
        angle = _rotation(shape)
        boxed = _has_visible_box(shape)
        if abs(abs(angle) - 90) < 15:                      # 세로로 돌린 상자: 보이는 영역은 가로세로가 바뀐다
            cx, cy, hw, hh = (x0 + x1) / 2, (y0 + y1) / 2, (y1 - y0) / 2, (x1 - x0) / 2
            x0, x1, y0, y1 = cx - hw, cx + hw, cy - hh, cy + hh
        counters = {}
        paras = []
        for p in shape.text_frame.paragraphs:
            level = p.level or 0
            ppr = p._p.find(qn("a:pPr"))
            auto = ppr.find(qn("a:buAutoNum")) if ppr is not None else None
            raw = p.text.replace("\v", "\n")
            text = "\n".join(t for t in (clean(x) for x in raw.split("\n")) if t)
            if not text:
                continue
            listed = has_bullet(text)
            text = strip_bullet(text)
            if auto is not None:
                start = int(auto.get("startAt", "1") or 1)
                counters[level] = counters.get(level, start - 1) + 1
                for deeper in [k for k in counters if k > level]:
                    del counters[deeper]
                text = "%s %s" % (_format_number(auto.get("type", "arabicPeriod"), counters[level]), text)
                listed = True
            else:
                for same_or_deeper in [k for k in counters if k >= level]:
                    del counters[same_or_deeper]
            if not text:
                continue
            base = self.sizes.base(shape, level, ph_type)
            run_sizes = [(_sz(r._r.find(qn("a:rPr"))) or base) for r in p.runs] or [base]
            size = max(run_sizes) * scale
            bold = bool(p.runs) and all(r.font.bold is True for r in p.runs)
            paras.append((text, size, bold, listed or has_marker(text)))
        if not paras:
            return None

        # 글자가 실제로 차지하는 영역을 어림해 상자를 줄인다(PDF의 글자 영역과 비슷하게)
        # 채움/테두리가 있는 도형은 상자 자체가 눈에 보이는 영역이므로 그대로 둔다
        if not boxed and x1 - x0 > 30 and y1 - y0 > 15:    # 텍스트 상자의 기본 안쪽 여백
            x0, x1, y0, y1 = x0 + 7.2, x1 - 7.2, y0 + 3.6, y1 - 3.6
        usable = max(x1 - x0, 10.0)
        est = 0.0
        for text, size, _, _ in paras:
            for piece in text.split("\n"):
                est += max(1, math.ceil(_wide_units(piece) * size / usable)) * size * 1.2
        if not boxed and not shape.is_placeholder and abs(angle) < 3.0:
            widest = max(min(_wide_units(piece) * size, usable) for text, size, _, _ in paras for piece in text.split("\n"))
            if widest < usable * 0.9:
                algn = None
                for p in shape.text_frame.paragraphs:
                    ppr = p._p.find(qn("a:pPr"))
                    if ppr is not None and ppr.get("algn"):
                        algn = ppr.get("algn")
                        break
                if algn == "ctr":
                    mid = (x0 + x1) / 2
                    x0, x1 = mid - widest / 2, mid + widest / 2
                elif algn == "r":
                    x0 = x1 - widest
                else:
                    x1 = x0 + widest
        if not boxed and est < (y1 - y0) * 0.9 and abs(angle) < 3.0:
            anchor = _anchor(shape)
            if anchor == "ctr":
                mid = (y0 + y1) / 2
                y0, y1 = mid - est / 2, mid + est / 2
            elif anchor == "b":
                y0 = y1 - est
            else:
                y1 = y0 + est

        block = Block()
        for text, size, bold, listed in paras:
            block.lines.append(Line(text=text, x0=x0, y0=y0, x1=x1, y1=y1, size=size, bold=bold,
                                    angle=angle, is_para=True, list_start=listed))
        block.fit_bbox()
        if ph_type in TITLE_TYPES:
            block.hint = "title_ph"
        elif ph_type == PP_PLACEHOLDER.SUBTITLE:
            block.hint = "subtitle_ph"
        elif ph_type in FURNITURE_TYPES:
            block.role, block.reason = "removed", "바닥글·날짜·번호 개체 틀"
            for l in block.lines:
                l.removed = block.reason
        return block

    def table_block(self, shape) -> Optional[Block]:
        block = Block(kind="table")
        sizes = []
        spans = []                                 # (행, 열, 세로로 합친 수, 가로로 합친 수)
        for ri, row in enumerate(shape.table.rows):
            out = []
            for ci, cell in enumerate(row.cells):
                if cell.is_spanned:
                    out.append("")
                    continue
                if cell.is_merge_origin:
                    spans.append((ri, ci, cell.span_height, cell.span_width))
                else:
                    spans.append((ri, ci, 1, 1))
                parts = [strip_bullet(clean(p.text.replace("\v", " "))) for p in cell.text_frame.paragraphs]
                out.append(" ".join(t for t in parts if t))
                for p in cell.text_frame.paragraphs:
                    for r in p.runs:
                        v = _sz(r._r.find(qn("a:rPr")))
                        if v:
                            sizes.append(v)
            block.rows.append(out)
        if not any(any(c for c in r) for r in block.rows):
            return None
        block.size = max(sizes) if sizes else 14.0
        block.cell_spans = spans                   # type: ignore[attr-defined]
        return block

    def chart_block(self, shape) -> Optional[Block]:
        texts: List[str] = []
        try:
            chart = shape.chart
            if chart.has_title and chart.chart_title.has_text_frame:
                texts.append(clean(chart.chart_title.text_frame.text))
            series, cats = [], []
            for plot in chart.plots:
                for s in plot.series:
                    if s.name and str(s.name) not in series:
                        series.append(str(s.name))
                for c in plot.categories:
                    if str(c) not in cats:
                        cats.append(str(c))
            if series:
                texts.append(", ".join(series))
            if cats:
                texts.append(", ".join(cats))
        except Exception:
            pass
        texts = [t for t in texts if t]
        if not texts:
            return None
        block = Block(hint="chart")
        block.lines = [Line(text=t, x0=0, y0=0, x1=0, y1=0, size=10.0, is_para=True) for t in texts]
        return block

    def smartart_block(self, shape) -> Optional[Block]:
        data = shape._element.find(".//" + qn("a:graphicData"))
        if data is None or not (data.get("uri") or "").endswith("/diagram"):
            return None
        rel = data.find(DGM + "relIds")
        if rel is None or not rel.get(R_NS + "dm"):
            return None
        try:
            part = self.slide.part.related_part(rel.get(R_NS + "dm"))
            root = etree.fromstring(part.blob)
        except Exception:
            return None
        texts = []
        for pt in root.iter(DGM + "pt"):
            if pt.get("type") in ("pres", "parTrans", "sibTrans", "doc"):
                continue
            t = clean("".join(n.text or "" for n in pt.iter(qn("a:t"))))
            if t:
                texts.append(t)
        if not texts:
            return None
        block = Block(hint="smartart")
        block.lines = [Line(text=t, x0=0, y0=0, x1=0, y1=0, size=12.0, is_para=True) for t in texts]
        return block


def hidden_slide_numbers(path: str) -> List[int]:
    prs = Presentation(str(path))
    return [i for i, s in enumerate(prs.slides, 1) if s._element.get("show") in ("0", "false")]


def read(path: str, include_hidden: bool = False) -> Document:
    prs = Presentation(str(path))
    width, height = prs.slide_width / EMU, prs.slide_height / EMU
    doc = Document(path=str(path), kind="pptx")
    doc.info["slide_numbers"] = []
    doc.info["hidden"] = []
    for idx, slide in enumerate(prs.slides, 1):
        if slide._element.get("show") in ("0", "false"):
            doc.info["hidden"].append(idx)
            if not include_hidden:
                continue
        page = Page(number=len(doc.pages) + 1, width=width, height=height)
        doc.info["slide_numbers"].append(idx)

        # before: 가장 흔한 방식 그대로 — 도형을 저장 순서대로, 텍스트 틀만
        naive = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                t = shape.text_frame.text.replace("\v", "\n").strip()
                if t:
                    naive.append(t)
                    box = None
                    try:
                        x, y, w, h = shape.left, shape.top, shape.width, shape.height
                        if None not in (x, y, w, h) and width > 0 and height > 0:
                            box = (x / EMU / width, y / EMU / height, (x + w) / EMU / width, (y + h) / EMU / height)
                    except Exception:
                        box = None
                    page.before_boxes.append(box)
        page.before = "\n".join(naive)
        page.before_units = list(naive)            # 도형(글상자) 하나가 한 단위

        reader = _SlideReader(prs, slide, width, height)
        reader.walk(slide.shapes)
        try:
            layout = slide.slide_layout
            show_master = layout._element.get("showMasterSp") not in ("0", "false")
            sources = [layout] + ([layout.slide_master] if show_master else [])
            for src in sources:
                fixed = [s for s in src.shapes if not s.is_placeholder]
                reader.walk(fixed, removed_reason="슬라이드 마스터 문구")
        except Exception:
            pass
        page.blocks = reader.blocks
        doc.pages.append(page)
    return doc
