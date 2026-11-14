"""before/after 비교 리포트(HTML 한 파일). 인터넷 없이 브라우저로 바로 열린다."""
from __future__ import annotations

import base64
import difflib
import html
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .model import MethodResult, PageOut
from .textnorm import compare_key, one_line

esc = html.escape


@dataclass
class DocRun:
    """문서 하나를 여러 방식으로 처리한 결과 묶음."""
    path: str
    name: str
    kind: str                                   # pdf | pptx
    befores: List[Tuple[str, str, List[str]]] = field(default_factory=list)   # (key, 이름, 쪽별 텍스트)
    before_units: Dict[str, List[List[str]]] = field(default_factory=dict)    # key → 쪽별 추출 단위 목록
    before_unit_names: Dict[str, str] = field(default_factory=dict)           # key → 번호 하나가 뜻하는 것
    before_boxes: Dict[str, List[list]] = field(default_factory=dict)         # key → 쪽별 단위 위치 목록

    def add_before(self, key: str, label: str, pages, unit_name: str) -> None:
        """읽기 단계가 남긴 원문(쪽별 글, 추출 단위, 단위 위치)을 Before 열로 등록한다."""
        self.befores.append((key, label, [p.before for p in pages]))
        self.before_units[key] = [list(p.before_units) for p in pages]
        self.before_boxes[key] = [list(p.before_boxes) for p in pages]
        self.before_unit_names[key] = unit_name
    methods: List[MethodResult] = field(default_factory=list)
    images: List[Optional[bytes]] = field(default_factory=list)
    aspect: float = 4 / 3
    notes: List[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        counts = [len(m.pages) for m in self.methods if m.pages] + [len(b[2]) for b in self.befores]
        return max(counts) if counts else 0


def similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def page_text(p: Optional[PageOut]) -> str:
    return "" if p is None else (p.title + "\n" + p.body).strip()


def _page(m: MethodResult, i: int) -> Optional[PageOut]:
    return m.pages[i] if i < len(m.pages) else None


CSS = """
:root{--bg:#f6f6f3;--card:#fff;--ink:#1d1f23;--mute:#6b7280;--line:#dcdcd6;--acc:#1f5fbf;
--rm-bg:#fde8e8;--rm-ink:#a12626;--tt-bg:#dcf3e2;--tt-ink:#17643a;--df-bg:#fff1c9;--box:#1f5fbf}
@media (prefers-color-scheme:dark){:root{--bg:#16181c;--card:#1f2228;--ink:#e7e8ea;--mute:#9aa1ad;--line:#343842;
--acc:#7fb0ff;--rm-bg:#4a2326;--rm-ink:#ffb3b3;--tt-bg:#1f4130;--tt-ink:#9fe0b8;--df-bg:#4a3d12;--box:#7fb0ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif}
header.top{padding:20px 24px 8px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--mute);font-size:13px}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:8px 24px;
display:flex;flex-wrap:wrap;gap:6px 16px;align-items:center;font-size:13px}
.bar label{white-space:nowrap;cursor:pointer}
.bar .sep{width:1px;height:18px;background:var(--line)}
main{padding:8px 24px 60px}
table.sum{border-collapse:collapse;background:var(--card);margin:10px 0 6px;font-size:13px}
table.sum th,table.sum td{border:1px solid var(--line);padding:5px 10px;text-align:left;vertical-align:top}
table.sum th{background:transparent;color:var(--mute);font-weight:600}
table.sum td.n{text-align:right;font-variant-numeric:tabular-nums}
.wrap{overflow-x:auto}
section.page{margin-top:26px;border-top:2px solid var(--line);padding-top:12px}
section.page>h2{font-size:16px;margin:0 0 8px}
.cols{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(300px,1fr);gap:10px;overflow-x:auto;align-items:start;padding-bottom:6px}
.col{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.col>h3{font-size:13px;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.col.before>h3{color:var(--mute)}
.col.after>h3{color:var(--acc)}
.badge{font-weight:400;font-size:12px;color:var(--mute);white-space:nowrap}
pre,.txt{white-space:pre-wrap;word-break:break-word;margin:0;font:inherit}
.ttl{border-left:3px solid var(--tt-ink);background:var(--tt-bg);color:var(--tt-ink);padding:4px 8px;margin:6px 0;border-radius:0 4px 4px 0}
.ttl small,.rm small{opacity:.8;font-size:12px;margin-left:6px}
.ttl.none{border-color:var(--line);background:transparent;color:var(--mute)}
ol.blocks{margin:6px 0 0;padding-left:26px}
ol.blocks li{margin:0 0 6px;padding-left:2px}
ol.blocks li::marker{color:var(--box);font-weight:700;font-size:12px}
ol.blocks li.tbl{border-left:3px solid var(--box);padding-left:8px;background:rgba(31,95,191,.05);border-radius:0 4px 4px 0}
ol.blocks li.tbl .txt::before{content:"표";display:inline-block;margin-right:6px;padding:0 5px;border-radius:3px;
background:var(--box);color:var(--card);font-size:11px;font-weight:700;vertical-align:1px}
.rm{margin-top:8px;border-top:1px dashed var(--line);padding-top:6px;font-size:13px;color:var(--rm-ink)}
.rm div{margin:1px 0}
.rm s{text-decoration-thickness:1px}
.raw span{display:block;min-height:1.2em}
ol.units{margin:6px 0 0;padding-left:30px}
ol.units li{margin:0 0 6px;padding-left:2px}
ol.units li::marker{color:var(--mute);font-weight:700;font-size:12px}
.unit{color:var(--mute);font-size:12px;margin:0 0 4px}
.raw .x{background:var(--rm-bg);color:var(--rm-ink);text-decoration:line-through}
.raw .t{background:var(--tt-bg);color:var(--tt-ink)}
.d{background:var(--df-bg)}
.map{position:relative;width:100%;aspect-ratio:var(--ar);background:var(--pg,none) center/100% 100% no-repeat,#fff;
border:1px solid var(--line);border-radius:4px;margin-bottom:8px;overflow:hidden}
.map i{position:absolute;border:1.5px solid var(--box);border-radius:2px;background:rgba(31,95,191,.07)}
.map i b{position:absolute;left:-1px;top:-1px;background:#1f5fbf;color:#fff;font:700 10px/1.3 system-ui,sans-serif;padding:0 4px;border-radius:2px}
.map i.t{border-color:#17803f;background:rgba(23,128,63,.10)}
.map i.t b{background:#17803f}
.col.before .map i{border-color:#6b7280;background:rgba(107,114,128,.10)}
.col.before .map i b{background:#6b7280}
body.nomap .map{display:none}
.err{color:var(--rm-ink)}
.legend{color:var(--mute);font-size:12px;margin:4px 0 0}
.legend span{padding:0 4px;border-radius:3px}
a{color:var(--acc)}
"""

JS = """
document.querySelectorAll('input[data-col]').forEach(function(cb){
  cb.addEventListener('change',function(){
    document.querySelectorAll('.col[data-col="'+cb.dataset.col+'"]').forEach(function(el){el.style.display=cb.checked?'':'none'});
  });
});
var mapToggle=document.getElementById('maps');
if(mapToggle){mapToggle.addEventListener('change',function(){document.body.classList.toggle('nomap',!mapToggle.checked)});}
"""


def _shell(title: str, sub: str, bar: str, body: str) -> str:
    return (
        "<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>%s</title><style>%s</style></head><body>"
        "<header class=\"top\"><h1>%s</h1><div class=\"sub\">%s</div></header>"
        "%s<main>%s</main><script>%s</script></body></html>"
    ) % (esc(title), CSS, esc(title), sub, bar, body, JS)


def _box_html(box, label: str, cls: str = "") -> str:
    x0, y0, x1, y1 = box
    return "<i%s style=\"left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%\"><b>%s</b></i>" % (
        " class=\"%s\"" % cls if cls else "", x0 * 100, y0 * 100, max(x1 - x0, 0.01) * 100, max(y1 - y0, 0.01) * 100, label)


def _map_html(p: PageOut) -> str:
    parts = ["<div class=\"map\">"]
    if p.title_box:
        parts.append(_box_html(p.title_box, "제목", "t"))
    for n, b in enumerate(p.blocks, 1):
        parts.append(_box_html(b.box, str(n)))
    parts.append("</div>")
    return "".join(parts)


def _unit_map_html(boxes: list) -> str:
    """Before 열용 배치 그림: 라이브러리가 따로 꺼낸 단위의 위치와 번호."""
    parts = ["<div class=\"map\">"]
    for n, box in enumerate(boxes, 1):
        if box:
            parts.append(_box_html(box, str(n)))
    parts.append("</div>")
    return "".join(parts)


def _after_col(m: MethodResult, p: Optional[PageOut], badge: str = "", other_key: Optional[str] = None,
               show_map: bool = True, col_id: Optional[str] = None, heading: Optional[str] = None) -> str:
    head = "<article class=\"col after\" data-col=\"%s\"><h3><span>%s</span><span class=\"badge\">%s</span></h3>" % (
        esc(col_id or m.key), esc(heading or m.label), badge)
    if m.error:
        return head + "<div class=\"err\">%s</div></article>" % esc(
            m.error if "건너뜀" in m.error else "실행하지 못했습니다: " + m.error)
    if p is None:
        return head + "<div class=\"sub\">이 쪽의 결과가 없습니다.</div></article>"

    def mark(text: str) -> str:
        """other_key 가 주어지면 상대편에 없는 줄을 노랗게 표시한다."""
        if other_key is None:
            return esc(text)
        out = []
        for line in text.split("\n"):
            k = compare_key(line)
            out.append("<span class=\"d\">%s</span>" % esc(line) if k and k not in other_key else esc(line))
        return "\n".join(out)

    parts = [head]
    if show_map:
        parts.append(_map_html(p))
    if p.title:
        parts.append("<div class=\"ttl\"><b>제목</b> %s<small>%s</small></div>" % (mark(p.title), esc(p.title_reason)))
    else:
        parts.append("<div class=\"ttl none\">제목 없음</div>")
    tables = sum(1 for b in p.blocks if b.kind == "table")
    if tables:
        parts.append("<div class=\"unit\">이 쪽에서 표로 인식한 덩어리 %d개</div>" % tables)
    parts.append("<ol class=\"blocks\">")
    for b in p.blocks:
        parts.append("<li%s><div class=\"txt\">%s</div></li>" % (" class=\"tbl\"" if b.kind == "table" else "", mark(b.text)))
    parts.append("</ol>")
    if p.removed:
        parts.append("<div class=\"rm\"><b>제거한 문구</b>")
        for text, reason in p.removed:
            parts.append("<div><s>%s</s><small>%s</small></div>" % (esc(one_line(text)), esc(reason)))
        parts.append("</div>")
    parts.append("</article>")
    return "".join(parts)


def _before_col(key: str, label: str, text: str, removed_keys: set, title_key: str,
                units: Optional[List[str]] = None, unit_name: str = "", boxes: Optional[list] = None) -> str:
    """처리 전 원문. units가 있으면 라이브러리가 따로 꺼낸 단위마다 번호를 붙이고,
    boxes가 있으면 같은 번호를 쪽 그림 위에도 표시한다."""
    parts = ["<article class=\"col before\" data-col=\"%s\"><h3><span>%s</span></h3>" % (esc(key), esc(label))]

    def lines_html(chunk: str) -> str:
        out = []
        for line in chunk.split("\n"):
            k = compare_key(line)
            cls = ""
            if k and (k in removed_keys or any(
                    (k in r and len(k) >= 4) or (r in k and len(r) >= 0.6 * len(k)) for r in removed_keys if len(r) >= 4)):
                cls = "x"
            elif k and title_key and k == title_key:
                cls = "t"
            out.append("<span class=\"%s\">%s</span>" % (cls, esc(line)) if cls else "<span>%s</span>" % esc(line))
        return "".join(out)

    if units:
        if boxes and len(boxes) == len(units) and any(boxes):
            parts.append(_unit_map_html(boxes))
        if unit_name:
            parts.append("<div class=\"unit\">번호 하나 = %s · %d개</div>" % (esc(unit_name), len(units)))
        parts.append("<ol class=\"raw units\">")
        for unit in units:
            parts.append("<li>%s</li>" % lines_html(unit))
        parts.append("</ol>")
    else:
        parts.append("<div class=\"raw\">%s</div>" % lines_html(text))
    parts.append("</article>")
    return "".join(parts)


def _toolbar(cols: List[Tuple[str, str]], maps: bool = True) -> str:
    parts = ["<div class=\"bar\"><b>표시할 열</b>"]
    for key, label in cols:
        parts.append("<label><input type=\"checkbox\" data-col=\"%s\" checked> %s</label>" % (esc(key), esc(label)))
    if maps:
        parts.append("<span class=\"sep\"></span><label><input type=\"checkbox\" id=\"maps\" checked> 배치 그림(번호 위치)</label>")
    parts.append("</div>")
    return "".join(parts)


def _page_style(run: DocRun, i: int) -> str:
    style = "--ar:%.4f" % run.aspect
    img = run.images[i] if i < len(run.images) else None
    if img:
        style += ";--pg:url('data:image/jpeg;base64,%s')" % base64.b64encode(img).decode("ascii")
    return style


def write_doc_report(run: DocRun, out_path: str) -> None:
    ref = next((m for m in run.methods if m.pages and not m.error), None)
    n = run.page_count

    def table_texts(p: Optional[PageOut]) -> List[str]:
        return [one_line(b.text) for b in p.blocks if b.kind == "table"] if p is not None else []

    rows = ["<div class=\"wrap\"><table class=\"sum\"><tr><th>방식</th><th>처리 시간</th><th>제목을 찾은 쪽</th>"
            "<th>제거한 문구</th><th>본문 글자 수</th><th>찾은 표</th><th>%s 결과와 일치율</th><th>비고</th></tr>" % esc(ref.key if ref else "-")]
    table_diffs = []
    for m in run.methods:
        if m.error:
            rows.append("<tr><td>%s</td><td colspan=\"7\" class=\"err\">%s</td></tr>" % (
                esc(m.label), esc(m.error if "건너뜀" in m.error else "실행하지 못했습니다: " + m.error)))
            continue
        sims = [similarity(compare_key(page_text(_page(m, i))), compare_key(page_text(_page(ref, i)))) for i in range(n)] if ref else []
        rows.append("<tr><td>%s</td><td class=\"n\">%.2f초</td><td class=\"n\">%d / %d</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d개</td><td class=\"n\">%s</td><td>%s</td></tr>" % (
            esc(m.label), m.seconds, sum(1 for p in m.pages if p.title), len(m.pages),
            sum(len(p.removed) for p in m.pages), sum(len(p.body) for p in m.pages),
            sum(len(table_texts(p)) for p in m.pages),
            "기준" if m is ref else ("%.1f%%" % (100 * sum(sims) / len(sims)) if sims else "-"), esc(m.note)))
        if ref is not None and m is not ref:
            pages = [i + 1 for i in range(n) if table_texts(_page(m, i)) != table_texts(_page(ref, i))]
            table_diffs.append((m, pages))
    rows.append("</table></div>")
    for m, pages in table_diffs:
        if pages:
            links = ", ".join("<a href=\"#p%d\">%d쪽</a>" % (i, i) for i in pages[:80]) + (" 외 %d쪽" % (len(pages) - 80) if len(pages) > 80 else "")
            rows.append("<p class=\"legend\"><b>표 인식이 %s와 다른 쪽</b> · %s: %s</p>" % (esc(ref.key), esc(m.label), links))
        else:
            rows.append("<p class=\"legend\"><b>표 인식이 %s와 다른 쪽</b> · %s: 없음</p>" % (esc(ref.key), esc(m.label)))
    rows.append("<p class=\"legend\">표로 인식한 덩어리는 왼쪽에 파란 줄과 '표' 꼬리표가 붙습니다. 일치율은 표의 칸 구분을 세지 않으므로, "
                "표 인식의 차이는 위의 '다른 쪽' 목록과 '찾은 표' 수로 확인하세요.</p>")
    rows.append("<p class=\"legend\">Before 열의 번호는 라이브러리가 따로 꺼내 준 단위입니다. 같은 번호 안의 줄은 한 덩어리로 나온 것이고, "
                "번호가 다르면 따로 나온 것입니다. 번호 순서가 곧 저장된 순서이고, 배치 그림의 회색 상자가 그 단위의 위치입니다.</p>")
    rows.append("<p class=\"legend\">Before 열 표시: <span style=\"background:var(--rm-bg);color:var(--rm-ink)\">빨강 취소선</span> = %s 방식이 제거한 문구, "
                "<span style=\"background:var(--tt-bg);color:var(--tt-ink)\">초록</span> = %s 방식이 고른 제목. "
                "일치율은 띄어쓰기와 줄바꿈을 무시하고 글자와 순서를 비교한 값입니다.</p>" % ((esc(ref.key),) * 2 if ref else ("-", "-")))
    for note in run.notes:
        rows.append("<p class=\"legend\">%s</p>" % esc(note))

    body = ["".join(rows)]
    for i in range(n):
        rp = _page(ref, i) if ref else None
        removed_keys = {compare_key(t) for t, _ in (rp.removed if rp else [])}
        removed_keys.discard("")
        title_key = compare_key(rp.title) if rp else ""
        ref_key = compare_key(page_text(rp))
        body.append("<section class=\"page\" id=\"p%d\" style=\"%s\"><h2>%d쪽</h2><div class=\"cols\">" % (i + 1, _page_style(run, i), i + 1))
        for key, label, texts in run.befores:
            per_page = run.before_units.get(key, [])
            box_pages = run.before_boxes.get(key, [])
            body.append(_before_col(key, label, texts[i] if i < len(texts) else "", removed_keys, title_key,
                                    per_page[i] if i < len(per_page) else None, run.before_unit_names.get(key, ""),
                                    box_pages[i] if i < len(box_pages) else None))
        for m in run.methods:
            p = _page(m, i)
            badge = ""
            if p is not None and m is not ref and not m.error and ref:
                badge = "%s와 %.0f%% 일치" % (esc(ref.key), 100 * similarity(compare_key(page_text(p)), ref_key))
            body.append(_after_col(m, p, badge))
        body.append("</div></section>")

    cols = [(k, l) for k, l, _ in run.befores] + [(m.key, m.label) for m in run.methods]
    sub = "%s · %d쪽 · before/after 비교" % (esc(run.kind.upper()), n)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_shell(run.name, sub, _toolbar(cols), "".join(body)))


# ---------------------------------------------------------------- PPTX ↔ PDF 일치 검증

def pair_stats(pptx: DocRun, pdf: DocRun) -> List[dict]:
    """같은 자료의 PPTX 결과와 PDF 결과가 얼마나 같은지 방식별로 계산한다."""
    stats = []
    by_key = {m.key: m for m in pptx.methods}
    for pm in pdf.methods:
        base_key = pm.key.split("-")[0]              # A-mu, A-pl → A
        xm = by_key.get(base_key)
        if xm is None or pm.error or xm.error:
            continue
        n = min(len(pm.pages), len(xm.pages))
        loose, strict, titles = [], [], 0
        for i in range(n):
            a, b = page_text(xm.pages[i]), page_text(pm.pages[i])
            loose.append(similarity(compare_key(a), compare_key(b)))
            strict.append(similarity(one_line(a), one_line(b)))
            if compare_key(xm.pages[i].title) == compare_key(pm.pages[i].title):
                titles += 1
        stats.append({"pdf": pm, "pptx": xm, "n": n, "loose": loose, "strict": strict, "titles": titles})
    return stats


def write_pair_report(pptx: DocRun, pdf: DocRun, out_path: str) -> List[dict]:
    stats = pair_stats(pptx, pdf)
    rows = ["<div class=\"wrap\"><table class=\"sum\"><tr><th>방식</th><th>평균 일치율<br>(띄어쓰기 무시)</th><th>평균 일치율<br>(띄어쓰기 포함)</th>"
            "<th>가장 낮은 쪽</th><th>제목이 같은 쪽</th></tr>"]
    for s in stats:
        n = s["n"] or 1
        worst = min(range(s["n"]), key=lambda i: s["loose"][i]) if s["n"] else 0
        rows.append("<tr><td>%s</td><td class=\"n\">%.1f%%</td><td class=\"n\">%.1f%%</td><td class=\"n\"><a href=\"#p%d\">%d쪽 (%.0f%%)</a></td><td class=\"n\">%d / %d</td></tr>" % (
            esc(s["pdf"].label), 100 * sum(s["loose"]) / n, 100 * sum(s["strict"]) / n,
            worst + 1, worst + 1, 100 * s["loose"][worst] if s["n"] else 0, s["titles"], s["n"]))
    rows.append("</table></div>")
    if len(pptx.methods[0].pages if pptx.methods else []) != len(pdf.methods[0].pages if pdf.methods else []):
        rows.append("<p class=\"legend err\">쪽 수가 다릅니다 (PPTX %d, PDF %d). 앞에서부터 순서대로 짝지어 비교했습니다.</p>" % (
            len(pptx.methods[0].pages), len(pdf.methods[0].pages)))
    rows.append("<p class=\"legend\"><span class=\"d\">노랑</span> = 상대편 결과에 없는 줄. 일치율은 제목과 본문을 합쳐 글자와 순서를 비교한 값입니다.</p>")

    body = ["".join(rows)]
    n = max((s["n"] for s in stats), default=0)
    for i in range(n):
        body.append("<section class=\"page\" id=\"p%d\" style=\"%s\"><h2>%d쪽</h2><div class=\"cols\">" % (i + 1, _page_style(pdf, i), i + 1))
        for s in stats:
            if i >= s["n"]:
                continue
            xp, pp = s["pptx"].pages[i], s["pdf"].pages[i]
            badge = "%.0f%% 일치" % (100 * s["loose"][i])
            key = s["pdf"].key
            body.append(_after_col(s["pptx"], xp, "PPTX", compare_key(page_text(pp)), show_map=False,
                                   col_id=key, heading=s["pdf"].label))
            body.append(_after_col(s["pdf"], pp, "PDF · " + badge, compare_key(page_text(xp)), show_map=False,
                                   col_id=key, heading=s["pdf"].label))
        body.append("</div></section>")
    cols = [(s["pdf"].key, s["pdf"].label) for s in stats]
    sub = "같은 자료의 PPTX와 PDF 결과가 얼마나 같은지 비교 · %d쪽" % n
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_shell(pptx.name + "  ↔  " + pdf.name, sub, _toolbar(cols, maps=False), "".join(body)))
    return stats


# ---------------------------------------------------------------- 목록, JSON

def write_index(entries: List[dict], out_path: str, footer: str = "") -> None:
    rows = ["<div class=\"wrap\"><table class=\"sum\"><tr><th>문서</th><th>쪽 수</th><th>방식별 처리 시간</th><th>PPTX ↔ PDF 일치율</th></tr>"]
    for e in entries:
        run: DocRun = e["run"]
        times = " · ".join("%s %.2f초" % (esc(m.key), m.seconds) if not m.error else "%s 실패" % esc(m.key) for m in run.methods)
        pair = ""
        if e.get("pair_file"):
            best = " · ".join("%s %.0f%%" % (esc(s["pdf"].key), 100 * sum(s["loose"]) / max(s["n"], 1)) for s in e["pair_stats"])
            pair = "<a href=\"%s\">비교 보기</a><br><span class=\"sub\">%s</span>" % (esc(e["pair_file"]), best)
        rows.append("<tr><td><a href=\"%s\">%s</a></td><td class=\"n\">%d</td><td>%s</td><td>%s</td></tr>" % (
            esc(e["file"]), esc(run.name), run.page_count, times, pair))
    rows.append("</table></div>")
    if footer:
        rows.append("<p class=\"legend\">%s</p>" % esc(footer))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_shell("문서 추출 방식 비교", "문서를 눌러 before/after를 확인하세요.", "", "".join(rows)))


def write_json(run: DocRun, out_path: str) -> None:
    data = {
        "file": run.name, "kind": run.kind,
        "before": {k: texts for k, _, texts in run.befores},
        "before_units": run.before_units,
        "methods": {
            m.key: {
                "label": m.label, "seconds": round(m.seconds, 3), "error": m.error,
                "pages": [{"page": p.number, "title": p.title, "title_reason": p.title_reason, "body": p.body,
                           "removed": [{"text": t, "reason": r} for t, r in p.removed]} for p in m.pages],
            } for m in run.methods
        },
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
