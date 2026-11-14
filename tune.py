"""읽는 순서 기준값 시험.

방식 A가 읽는 순서를 정할 때 쓰는 기준값(docparse/layout.py)은 샘플로 정한 값이다.
이 스크립트는 실제 자료에서 그 값을 하나씩 바꿔 가며 순서를 다시 정해 보고,
지금 값일 때와 순서가 달라지는 쪽이 얼마나 되는지 세어 리포트(out/tune.html)로 만든다.

  달라지는 쪽이 거의 없다     → 지금 값이 그 자료에서도 안전하다
  바로 옆 값에서도 달라진다   → 그 쪽들을 보고 어느 순서가 맞는지 확인한다

바로 옆 값에서 달라지는 쪽은 지금 값과 바꾼 값에서 쪽을 어떻게 잘랐는지를 쪽 그림 위에 나란히 그려 준다.

글자를 읽고 덩어리로 묶는 일은 파일마다 한 번만 하고, 순서 정하기만 값마다 다시 한다.
읽는 방법은 compare.py와 같다(PDF는 pdfplumber, PPTX는 python-pptx).

사용법
  python tune.py 자료폴더
  python tune.py a.pdf b.pptx -o 결과폴더
"""
from __future__ import annotations

import argparse
import base64
import html
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from compare import collect, log
from docparse import layout, report
from docparse.pipeline import apply_rules

esc = html.escape

# (layout.py에 있는 이름, 설명, 단위, 시험할 값). 지금 값은 목록에 없어도 자동으로 끼워 넣는다.
PARAMS = [
    ("Y_MIN_GAP", "위아래로 자르는 데 필요한 여백", "pt", [0.1, 0.5, 1.0, 2.0, 4.0, 6.0, 10.0]),
    ("X_MIN_GAP", "좌우로 자르는 데 필요한 여백의 최소 보장", "pt", [2.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0]),
    ("X_GAP_RATIO", "좌우로 자르는 데 필요한 여백 (본문 글자 크기의 배수)", "배", [0.0, 0.3, 0.6, 1.0, 1.5, 2.5]),
    ("Y_PREFERENCE", "좌우 여백이 위아래 여백의 몇 배보다 넓어야 좌우로 자르는가", "배", [1.0, 1.2, 1.5, 2.0, 3.0]),
]
MAX_DETAIL = 40        # 값 하나당 순서를 펼쳐 보여 줄 쪽 수
MAX_LISTED = 60        # 값 하나당 쪽 번호만 나열할 때의 최대 개수


@dataclass
class PageCase:
    file: str            # 파일 이름
    report_file: str     # compare.py가 만드는 그 파일의 리포트 이름 (있으면 링크를 건다)
    page: int
    blocks: list         # 순서를 정할 덩어리들
    font: float          # 본문 글자 크기
    base: list           # 지금 기준값에서의 순서
    path: str = ""       # 파일 경로 (PDF면 쪽 그림을 그릴 때 쓴다)
    kind: str = ""       # pdf | pptx
    width: float = 1.0   # 쪽 크기(pt)
    height: float = 1.0


def values_of(name: str, values: List[float]) -> Tuple[List[float], float, List[float]]:
    """(시험할 값 전체, 지금 값, 지금 값의 바로 옆 값)"""
    current = float(getattr(layout, name))
    allv = sorted(set(float(v) for v in values) | {current})
    i = allv.index(current)
    near = [allv[j] for j in (i - 1, i + 1) if 0 <= j < len(allv)]
    return allv, current, near


def load(files: List[Path], include_hidden: bool) -> List[PageCase]:
    cases: List[PageCase] = []
    for f in files:
        kind = f.suffix.lower().lstrip(".")
        log("읽는 중: %s" % f)
        try:
            if kind == "pptx":
                from docparse import pptx_reader
                doc = pptx_reader.read(str(f), include_hidden=include_hidden)
            else:
                from docparse import pdf_plumber
                doc = pdf_plumber.read(str(f))
            order_log: list = []
            apply_rules(doc, order_log=order_log)
        except Exception as exc:
            log("  건너뜀(읽지 못함): %s: %s" % (type(exc).__name__, exc))
            continue
        size = {p.number: (p.width, p.height) for p in doc.pages}
        for number, blocks, font in order_log:
            w, h = size.get(number, (1.0, 1.0))
            cases.append(PageCase(f.name, "%s.%s.html" % (f.stem, kind), number, blocks, font,
                                  layout.xy_order(blocks, font), str(f), kind, w, h))
    return cases


def evaluate(cases: List[PageCase]) -> Dict[Tuple[str, float], list]:
    """기준값을 하나씩만 바꿔 순서를 다시 정한다. 반환: {(이름, 값): [(쪽 색인, 새 순서), ...]}"""
    base_ids = [[id(b) for b in c.base] for c in cases]
    out: Dict[Tuple[str, float], list] = {}
    for name, _, _, values in PARAMS:
        allv, current, _ = values_of(name, values)
        for v in allv:
            changed = []
            if v != current:
                setattr(layout, name, v)
                try:
                    for i, c in enumerate(cases):
                        if len(c.blocks) < 2:
                            continue
                        new = layout.xy_order(c.blocks, c.font)
                        if [id(b) for b in new] != base_ids[i]:
                            changed.append((i, new))
                finally:
                    setattr(layout, name, current)      # 다른 값 시험과 이후 실행에 영향이 없도록 되돌린다
            out[(name, v)] = changed
    return out


def fmt(v: float, unit: str) -> str:
    return ("%g" % v) + unit


def snippet(block) -> str:
    text = (getattr(block, "text", "") or "").strip().split("\n")[0]
    return text[:30] + ("…" if len(text) > 30 else "")


def traced(c: PageCase, name: Optional[str] = None, value: Optional[float] = None) -> Tuple[list, list]:
    """(읽는 순서, 자른 기록). name과 value를 주면 그 기준값만 바꿔서 다시 정한다."""
    trace: list = []
    if name is None:
        return layout.xy_order(c.blocks, c.font, trace), trace
    current = getattr(layout, name)
    setattr(layout, name, value)
    try:
        return layout.xy_order(c.blocks, c.font, trace), trace
    finally:
        setattr(layout, name, current)


def page_pictures(cases: List[PageCase], wanted: set) -> Dict[int, bytes]:
    """그림으로 보여 줄 쪽(cases의 색인)의 쪽 그림. PDF만 그릴 수 있다."""
    by_file: Dict[str, Dict[int, int]] = {}
    for i in wanted:
        if cases[i].kind == "pdf":
            by_file.setdefault(cases[i].path, {})[cases[i].page] = i
    out: Dict[int, bytes] = {}
    for path, pages in by_file.items():
        try:
            from docparse import pdf_plumber
            images = pdf_plumber.page_images(path, width=800, only=set(pages))
        except Exception as exc:
            log("  쪽 그림을 그리지 못함: %s: %s" % (type(exc).__name__, exc))
            continue
        for number, i in pages.items():
            if number - 1 < len(images) and images[number - 1]:
                out[i] = images[number - 1]
    return out


def _trace_key(t: dict) -> tuple:
    box = tuple(round(v) for v in t["box"])
    if t["kind"] == "cut":
        return ("cut", t["axis"], round(t["lo"]), round(t["hi"]), box)
    return (t["kind"], t.get("by_rows"), box)


def _what(t: dict) -> str:
    if t["kind"] == "cut":
        return "%s 잘랐습니다(여백 %s)" % ("좌우로" if t["axis"] == "x" else "위아래로", fmt(round(t["hi"] - t["lo"], 1), "pt"))
    if t["kind"] == "grid":
        return "격자로 보고 %s 순서로 읽었습니다" % ("가로 줄" if t.get("by_rows") else "세로 묶음")
    return "자를 여백이 없어 줄 단위로 읽었습니다"


def first_split(base_trace: list, new_trace: list) -> Optional[int]:
    """두 기록이 처음 달라지는 자리. 그 앞까지는 똑같이 잘랐으므로 그 자리의 두 기록은 같은 영역을 다룬다."""
    for k, (a, b) in enumerate(zip(base_trace, new_trace)):
        if _trace_key(a) != _trace_key(b):
            return k
    return None


def why_html(name: str, unit: str, current: float, v: float, a: dict, b: dict) -> str:
    """처음 달라지는 곳에서 여백이 얼마였고 두 값이 각각 어떻게 했는지."""
    gx, gy = a["gap_x"], a["gap_y"]
    gaps = "좌우 %s, 위아래 %s" % (fmt(round(gx, 1), "pt") if gx > 0 else "없음", fmt(round(gy, 1), "pt") if gy > 0 else "없음")
    if name == "Y_MIN_GAP":
        rule = "위아래로 자르려면 여백이 지금은 %s, 바꾼 값에서는 %s 이상이어야 합니다." % (fmt(current, unit), fmt(v, unit))
    elif name == "Y_PREFERENCE":
        ratio = " 이 영역은 좌우 여백이 위아래 여백의 %.2f배입니다." % (gx / gy) if gx > 0 and gy > 0 else ""
        rule = "좌우로 먼저 자르려면 좌우 여백이 위아래 여백의 지금은 %s, 바꾼 값에서는 %s보다 넓어야 합니다.%s" % (
            fmt(current, unit), fmt(v, unit), ratio)
    else:
        rule = "좌우로 자르려면 여백이 지금은 %s, 바꾼 값에서는 %s 이상이어야 합니다." % (
            fmt(round(a["need_x"], 1), "pt"), fmt(round(b["need_x"], 1), "pt"))
    return ("<p class=\"why\"><b>① 처음 달라지는 곳</b> · 이 영역에서 가장 넓은 여백은 %s입니다. %s<br>"
            "지금 값에서는 %s. %s일 때는 %s.</p>" % (esc(gaps), esc(rule), esc(_what(a)), fmt(v, unit), esc(_what(b))))


def _pct(x0: float, y0: float, x1: float, y1: float, c: PageCase) -> str:
    w, h = max(c.width, 1.0), max(c.height, 1.0)
    return "left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%" % (
        100 * x0 / w, 100 * y0 / h, 100 * max(x1 - x0, 0.0) / w, 100 * max(y1 - y0, 0.0) / h)


def cut_map(c: PageCase, order: list, trace: list, other: list, moved: set, first: Optional[int] = None) -> str:
    """쪽 그림 위에 덩어리 상자(번호 = 읽는 순서)와 자른 자리를 그린다.

    상대편에는 없는 자름은 빨간 띠(여백)와 굵은 선, 양쪽에 다 있는 자름은 회색 점선으로 그린다.
    first는 두 기록이 처음 달라지는 자리이고, 그 표시 앞에 ①을 붙인다.
    """
    w, h = max(c.width, 1.0), max(c.height, 1.0)
    clamp = lambda v: min(1.0, max(0.0, v))
    other_keys = {_trace_key(t) for t in other}
    parts = ["<div class=\"map\">"]
    for n, b in enumerate(order, 1):
        box = (clamp(b.x0 / w), clamp(b.y0 / h), clamp(b.x1 / w), clamp(b.y1 / h))
        parts.append(report._box_html(box, str(n), "mv" if id(b) in moved else ""))
    for k, t in enumerate(trace):
        diff = _trace_key(t) not in other_keys
        mark = "① " if k == first else ""
        x0, y0, x1, y1 = t["box"]
        if t["kind"] == "cut":
            gap = t["hi"] - t["lo"]
            mid = (t["lo"] + t["hi"]) / 2
            tip = "%d단계 · %s 자름 · 여백 %.1fpt" % (t["depth"] + 1, "좌우로" if t["axis"] == "x" else "위아래로", gap)
            if t["axis"] == "x":
                band, line, at = _pct(t["lo"], y0, t["hi"], y1, c), _pct(mid, y0, mid, y1, c), (mid, (y0 + y1) / 2)
            else:
                band, line, at = _pct(x0, t["lo"], x1, t["hi"], c), _pct(x0, mid, x1, mid, c), ((x0 + x1) / 2, mid)
            cls = "v" if t["axis"] == "x" else "h"
            if diff:
                parts.append("<span class=\"band\" style=\"%s\"></span>" % band)
                parts.append("<span class=\"cut %s diff\" style=\"%s\" title=\"%s\"></span>" % (cls, line, esc(tip)))
                parts.append("<span class=\"cl\" style=\"left:%.2f%%;top:%.2f%%\" title=\"%s\">%s여백 %s</span>" % (
                    100 * at[0] / w, 100 * at[1] / h, esc(tip), mark, fmt(round(gap, 1), "pt")))
            else:
                parts.append("<span class=\"cut %s\" style=\"%s\" title=\"%s\"></span>" % (cls, line, esc(tip)))
        elif diff:
            if t["kind"] == "grid":
                label = "격자 · 가로 줄 순서로 읽음" if t.get("by_rows") else "격자 · 세로 묶음 순서로 읽음"
            else:
                label = "자를 여백 없음 · 줄 단위로 읽음"
            parts.append("<span class=\"zone\" style=\"%s\"><em>%s%s</em></span>" % (_pct(x0, y0, x1, y1, c), mark, label))
    parts.append("</div>")
    return "".join(parts)


def compare_html(i: int, c: PageCase, name: str, unit: str, current: float, v: float, new: list, pictures: dict) -> str:
    """한 쪽의 '지금 값'과 '바꾼 값' 비교: 자른 자리 그림과 순서 목록을 나란히."""
    base_order, base_trace = traced(c)
    _, new_trace = traced(c, name, v)
    moved = {id(b) for k, b in enumerate(new) if k >= len(base_order) or base_order[k] is not b}
    first = first_split(base_trace, new_trace)
    why = why_html(name, unit, current, v, base_trace[first], new_trace[first]) if first is not None else ""
    cls = "pair pg%d" % i if i in pictures else "pair"
    return ("%s<div class=\"%s\" style=\"--ar:%.4f\">"
            "<div><b>지금 값 %s</b>%s%s</div><div><b>%s일 때</b>%s%s</div></div>" % (
                why, cls, c.width / max(c.height, 1.0),
                fmt(current, unit), cut_map(c, base_order, base_trace, new_trace, moved, first), order_list(c.base, new),
                fmt(v, unit), cut_map(c, new, new_trace, base_trace, moved, first), order_list(new, c.base)))


CSS = """
h2{font-size:16px;margin:26px 0 4px}
h3{font-size:14px;margin:16px 0 4px}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0;max-width:900px}
.ok{color:var(--tt-ink);font-weight:700}
.warn{color:var(--rm-ink);font-weight:700}
tr.cur td{font-weight:700}
tr.hit td{background:var(--df-bg)}
details{margin:4px 0;max-width:1100px}
summary{cursor:pointer}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:4px 0 10px}
.pair>div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px;min-width:0}
.pair b{font-size:12px;color:var(--mute)}
.pair ol{margin:4px 0;padding-left:28px}
.refs{font-size:13px;color:var(--mute)}
.pair .map{margin-top:4px}
.why{margin:6px 0 2px;padding:6px 10px;max-width:1100px;font-size:13px;background:var(--card);border:1px solid var(--line);border-left:3px solid #dc2626;border-radius:0 6px 6px 0}
.pair .map i{border-color:#6b7280;background:rgba(107,114,128,.08)}
.pair .map i b{background:#6b7280}
.pair .map i.mv{border-color:#d97706;background:rgba(217,119,6,.20)}
.pair .map i.mv b{background:#d97706}
.map .cut{position:absolute;pointer-events:auto}
.map .cut.h{border-top:1.5px dashed #6b7280;height:0}
.map .cut.v{border-left:1.5px dashed #6b7280;width:0}
.map .cut.h.diff{border-top:3px solid #dc2626;margin-top:-1.5px}
.map .cut.v.diff{border-left:3px solid #dc2626;margin-left:-1.5px}
.map .band{position:absolute;background:rgba(220,38,38,.22)}
.map .cl{position:absolute;transform:translate(-50%,-50%);background:#dc2626;color:#fff;font:700 10px/1.4 system-ui,sans-serif;padding:0 5px;border-radius:2px;white-space:nowrap;z-index:2}
.map .zone{position:absolute;border:2px dashed #dc2626;border-radius:3px}
.map .zone em{position:absolute;right:-2px;bottom:-2px;background:#dc2626;color:#fff;font:700 10px/1.4 system-ui,sans-serif;font-style:normal;padding:0 5px;border-radius:2px;white-space:nowrap}
.key span{display:inline-block;vertical-align:middle;margin:0 4px 0 10px}
.key .k1{width:22px;border-top:3px solid #dc2626}
.key .k2{width:22px;border-top:1.5px dashed #6b7280}
.key .k3{width:14px;height:10px;border:1.5px solid #d97706;background:rgba(217,119,6,.20)}
.key .k4{width:14px;height:10px;border:1.5px solid #6b7280;background:rgba(107,114,128,.08)}
button.all{font:inherit;font-size:12px;margin:0 6px 0 0;padding:2px 8px;cursor:pointer}
"""


def page_ref(c: PageCase, out_dir: Path) -> str:
    label = "%s · %d쪽" % (esc(c.file), c.page)
    if (out_dir / c.report_file).exists():
        return "<a href=\"%s#p%d\">%s</a>" % (esc(c.report_file), c.page, label)
    return label


def order_list(order: list, other: list) -> str:
    items = []
    for i, b in enumerate(order):
        moved = i >= len(other) or other[i] is not b
        items.append("<li>%s</li>" % ("<span class=\"d\">%s</span>" % esc(snippet(b)) if moved else esc(snippet(b))))
    return "<ol>%s</ol>" % "".join(items)


def conclusion(cases: List[PageCase], results: dict) -> Tuple[str, str, set, set]:
    """(판정 종류, 문장, 바로 옆 값에서 달라진 쪽, 어떤 값에서든 달라진 쪽)"""
    testable = sum(1 for c in cases if len(c.blocks) >= 2)
    near_pages, any_pages = set(), set()
    for name, _, _, values in PARAMS:
        allv, _, near = values_of(name, values)
        for v in allv:
            idx = {i for i, _ in results[(name, v)]}
            any_pages |= idx
            if v in near:
                near_pages |= idx
    if not testable:
        return "warn", "순서를 정할 덩어리가 둘 이상인 쪽이 없어 시험할 것이 없습니다.", near_pages, any_pages
    if not any_pages:
        return "ok", "어떤 값으로 바꿔도 읽는 순서가 같았습니다. 지금 기준값은 이 자료에서 안전합니다.", near_pages, any_pages
    if not near_pages:
        return "ok", ("지금 값의 바로 옆 값으로는 순서가 바뀌지 않았습니다. 지금 기준값은 이 자료에서 안전합니다. "
                      "멀리 떨어진 값에서만 %d쪽이 달라졌습니다." % len(any_pages)), near_pages, any_pages
    return "warn", ("지금 값의 바로 옆 값에서도 순서가 바뀌는 쪽이 %d쪽(시험한 쪽의 %.1f%%) 있습니다. "
                    "아래 '바로 옆 값에서 달라진 쪽'에서 어느 순서가 맞는지 확인해 주세요."
                    % (len(near_pages), 100.0 * len(near_pages) / testable)), near_pages, any_pages


def detailed_pages(results: dict) -> set:
    """그림으로 펼쳐 보여 줄 쪽(cases의 색인): 바로 옆 값에서 순서가 달라진 쪽, 값마다 MAX_DETAIL쪽까지."""
    shown = set()
    for name, _, _, values in PARAMS:
        _, _, near = values_of(name, values)
        for v in near:
            shown.update(i for i, _ in results[(name, v)][:MAX_DETAIL])
    return shown


def write_report(cases: List[PageCase], results: dict, out_dir: Path, n_files: int, pictures: Optional[dict] = None) -> Path:
    pictures = pictures or {}
    testable = sum(1 for c in cases if len(c.blocks) >= 2)
    kind, sentence, near_pages, any_pages = conclusion(cases, results)
    body = ["<style>%s</style>" % CSS]
    if pictures:                                   # 쪽 그림은 쪽마다 한 번만 싣고, 그 쪽을 보여 주는 곳에서 함께 쓴다
        body.append("<style>%s</style>" % "".join(
            ".pg%d{--pg:url('data:image/jpeg;base64,%s')}" % (i, base64.b64encode(img).decode("ascii"))
            for i, img in sorted(pictures.items())))
    body.append("<div class=\"box\"><p><span class=\"%s\">%s</span></p>"
                "<p class=\"legend\">시험한 자료: 파일 %d개 · %d쪽 (그중 순서를 정할 덩어리가 둘 이상인 쪽 %d쪽) · PDF는 pdfplumber, PPTX는 python-pptx로 읽음</p>"
                "<p class=\"legend\">기준값을 한 번에 하나씩만 바꾸고, 지금 값일 때와 읽는 순서가 달라진 쪽을 셉니다. "
                "글자 내용, 덩어리 나누기, 제목, 반복 문구 제거는 바꾸지 않습니다.</p></div>"
                % (kind, esc(sentence), n_files, len(cases), testable))

    for name, label, unit, values in PARAMS:
        allv, current, near = values_of(name, values)
        body.append("<h2>%s</h2><p class=\"legend\">지금 값: %s · 코드에서의 이름: %s</p>" % (esc(label), fmt(current, unit), esc(name)))
        body.append("<div class=\"wrap\"><table class=\"sum\"><tr><th>값</th><th>순서가 달라진 쪽</th><th>시험한 쪽 대비</th><th>비고</th></tr>")
        for v in allv:
            n = len(results[(name, v)])
            note = "지금 값" if v == current else ("바로 옆 값" if v in near else "")
            cls = "cur" if v == current else ("hit" if (v in near and n) else "")
            body.append("<tr%s><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td>%s</td></tr>" % (
                " class=\"%s\"" % cls if cls else "", fmt(v, unit), "-" if v == current else "%d쪽" % n,
                "-" if v == current or not testable else "%.1f%%" % (100.0 * n / testable), note))
        body.append("</table></div>")

    body.append("<h2>바로 옆 값에서 달라진 쪽</h2>")
    body.append("<p class=\"legend\">값을 조금만 바꿔도 순서가 바뀌는 쪽입니다. 왼쪽이 지금 값, 오른쪽이 바꾼 값일 때이고, "
                "쪽 그림 위의 번호가 읽는 순서입니다. 쪽을 어디서 잘랐는지가 선으로 그려져 있어 두 그림에서 달라진 곳을 바로 볼 수 있습니다.</p>")
    body.append("<p class=\"legend key\"><span class=\"k1\"></span>한쪽 그림에만 있는 자름(빨간 띠가 그때 쓴 여백, 숫자가 여백의 너비)"
                "<span class=\"k2\"></span>두 그림에 똑같이 있는 자름"
                "<span class=\"k3\"></span>순서가 달라진 덩어리<span class=\"k4\"></span>순서가 같은 덩어리</p>")
    body.append("<p class=\"legend\">쪽마다 위에 적힌 문장과 그림의 ①은 두 값의 결과가 처음 갈라지는 곳입니다. 그 뒤의 차이는 거기서 다르게 나뉜 결과입니다. "
                "빨간 점선 상자는 그 영역을 더 자르지 않고 한 번에 순서를 정한 곳입니다(격자로 보았거나, 자를 여백이 없어 줄 단위로 읽음). "
                "선 위에 마우스를 올리면 몇 번째 단계에서 어느 방향으로 잘랐는지 나옵니다. 그림 아래 목록의 <span class=\"d\">노랑</span>은 자리가 달라진 덩어리이고, "
                "파일 이름에 링크가 있으면 비교 리포트의 그 쪽으로 갑니다. PPTX는 쪽 그림이 없어 상자만 그립니다.</p>")
    body.append("<p class=\"legend\"><button class=\"all\" onclick=\"document.querySelectorAll('details.cmp').forEach(function(d){d.open=true})\">모두 펼치기</button>"
                "<button class=\"all\" onclick=\"document.querySelectorAll('details.cmp').forEach(function(d){d.open=false})\">모두 접기</button></p>")
    shown = False
    for name, label, unit, values in PARAMS:
        allv, current, near = values_of(name, values)
        for v in near:
            changed = results[(name, v)]
            if not changed:
                continue
            shown = True
            body.append("<h3>%s: %s → %s (%d쪽)</h3>" % (esc(label), fmt(current, unit), fmt(v, unit), len(changed)))
            opened = " open" if len(changed) <= 10 else ""          # 몇 쪽 안 되면 처음부터 펼쳐 둔다
            for i, new in changed[:MAX_DETAIL]:
                c = cases[i]
                body.append("<details class=\"cmp\"%s><summary>%s</summary>%s</details>"
                            % (opened, page_ref(c, out_dir), compare_html(i, c, name, unit, current, v, new, pictures)))
            if len(changed) > MAX_DETAIL:
                body.append("<p class=\"legend\">외 %d쪽은 생략했습니다.</p>" % (len(changed) - MAX_DETAIL))
    if not shown:
        body.append("<p class=\"legend\">없습니다.</p>")

    body.append("<h2>멀리 떨어진 값에서 달라진 쪽</h2>")
    body.append("<p class=\"legend\">지금 값에서 많이 벗어나야 바뀌는 쪽이라 참고용입니다.</p>")
    shown = False
    for name, label, unit, values in PARAMS:
        allv, current, near = values_of(name, values)
        for v in allv:
            changed = results[(name, v)]
            if v == current or v in near or not changed:
                continue
            shown = True
            refs = ", ".join(page_ref(cases[i], out_dir) for i, _ in changed[:MAX_LISTED])
            more = " 외 %d쪽" % (len(changed) - MAX_LISTED) if len(changed) > MAX_LISTED else ""
            body.append("<details><summary>%s: %s → %s (%d쪽)</summary><p class=\"refs\">%s%s</p></details>"
                        % (esc(label), fmt(current, unit), fmt(v, unit), len(changed), refs, more))
    if not shown:
        body.append("<p class=\"legend\">없습니다.</p>")

    path = out_dir / "tune.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(report._shell("읽는 순서 기준값 시험", "기준값을 바꿨을 때 읽는 순서가 달라지는 쪽", "", "".join(body)))
    return path


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")      # Windows 콘솔 한글 깨짐 방지
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="읽는 순서 기준값을 바꿔 가며 순서가 달라지는 쪽을 센다")
    ap.add_argument("inputs", nargs="+", help="PDF/PPTX 파일 또는 폴더")
    ap.add_argument("-o", "--out", default="out", help="리포트를 저장할 폴더 (기본: out)")
    ap.add_argument("--pdfplumber", action="store_true", help=argparse.SUPPRESS)     # 예전 옵션. 이제 항상 pdfplumber라 받기만 한다
    ap.add_argument("--include-hidden", action="store_true", help="PPTX의 숨긴 슬라이드도 포함")
    ap.add_argument("--no-images", action="store_true", help="리포트에 쪽 그림을 넣지 않음 (상자와 자른 선만 그림)")
    args = ap.parse_args(argv)

    files = collect(args.inputs)
    if not files:
        log("처리할 PDF/PPTX 파일이 없습니다.")
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = load(files, args.include_hidden)
    testable = sum(1 for c in cases if len(c.blocks) >= 2)
    log("순서를 다시 정하는 중: %d쪽" % testable)
    results = evaluate(cases)

    log("")
    for name, label, unit, values in PARAMS:
        allv, current, near = values_of(name, values)
        log("%s (지금 %s)" % (label, fmt(current, unit)))
        for v in allv:
            if v == current:
                continue
            log("  %8s : %4d쪽 달라짐%s" % (fmt(v, unit), len(results[(name, v)]), "   ← 바로 옆 값" if v in near else ""))
    log("")
    log(conclusion(cases, results)[1])
    pictures = {}
    if not args.no_images:
        wanted = detailed_pages(results)
        if wanted:
            log("쪽 그림을 그리는 중: %d쪽" % sum(1 for i in wanted if cases[i].kind == "pdf"))
            pictures = page_pictures(cases, wanted)
    path = write_report(cases, results, out_dir, len(files), pictures)
    log("완료: %s" % path.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
