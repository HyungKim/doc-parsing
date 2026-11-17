"""걸러내기 비교 리포트(HTML). 인터넷 없이 브라우저로 바로 열린다.

    out/screen/index.html      기준 문장, 모델, 학습 전·후 수치, 덩어리 대 줄 비교, 문서 목록
    out/screen/이름.html       문서마다: 덩어리와 그 줄마다 모델별 점수(학습 전 → 후)
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import numpy as np

from docparse.report import _shell, esc

from .items import BlockItem, DocItems
from . import learn
from .run import VIEWS, ModelRun, Result, _items, view_items

CSS = """
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0;max-width:1100px}
.box p{margin:4px 0}
h2{font-size:16px;margin:26px 0 6px}
h3.pg{font-size:14px;margin:18px 0 6px;color:var(--mute)}
code{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:0 4px;font:12px ui-monospace,Consolas,monospace}
table.sum td.best{font-weight:700;color:var(--tt-ink)}
table.sum td.g{background:rgba(31,95,191,.06)}
table.sum td.up{color:var(--tt-ink);font-weight:700}
table.sum.proc td,table.sum.proc th{white-space:nowrap}table.sum.proc small{color:var(--mute)}
table.sum td.down{color:var(--rm-ink);font-weight:700}
table.sum td.flat{color:var(--mute)}
table.sum th.grp{text-align:center}
.plus{color:#17803f;font-weight:700}
.minus{color:var(--rm-ink);font-weight:700}
.blk{background:var(--card);border:1px solid var(--line);border-radius:8px;margin:0 0 10px;overflow-x:auto}
.blk>.hd{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:6px 10px;border-bottom:1px solid var(--line);font-size:12px;color:var(--mute)}
.blk>.hd code{font-weight:700;color:var(--acc);border:0;background:none;padding:0}
table.sc{border-collapse:collapse;width:100%;font-size:13px}
table.sc th,table.sc td{border-top:1px solid var(--line);padding:4px 8px;vertical-align:top;text-align:left}
table.sc th{font-size:11px;color:var(--mute);font-weight:600;border-top:0;white-space:nowrap}
table.sc td.v{white-space:nowrap;text-align:center;font-variant-numeric:tabular-nums;width:118px}
table.sc td.v b{font-weight:700}
table.sc td.v small{color:var(--mute)}
table.sc tr.whole td{background-color:rgba(31,95,191,.05)}
table.sc tr.whole td.t,table.sc tr.sumrow td.t{font-size:12px;color:var(--mute)}
table.sc td.t{white-space:pre-wrap;word-break:break-word}
.lab{display:inline-block;padding:0 6px;border-radius:3px;font-size:11px;font-weight:700;color:#fff;white-space:nowrap}
.lab.y{background:#17803f}
.lab.n{background:#6b7280}
.lab.q{background:none;color:var(--mute);border:1px dashed var(--line);font-weight:400}
.tag2{display:inline-block;padding:0 5px;border-radius:3px;font-size:10px;font-weight:700;color:#fff;background:#1f5fbf}
.hide{display:none}
.steps{margin:4px 0 0;padding-left:22px}
.steps li{margin:2px 0}
details.box>summary{cursor:pointer}
table.sum.num td,table.sum.num th{white-space:nowrap}
.viz{--s1:#2a78d6;--s2:#eb6834}
@media (prefers-color-scheme:dark){.viz{--s1:#3987e5;--s2:#d95926}}
.note{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--acc);border-radius:6px;padding:8px 14px;margin:10px 0;max-width:1100px}
.note.old{border-left-color:#a15c00}
.trend{display:inline-block;vertical-align:top;margin:4px 18px 10px 0}
.trend h4{margin:0 0 2px;font-size:13px}
.trend svg text{fill:var(--mute);font-size:11px}
.trend svg text.lab{fill:var(--ink);font-size:11.5px}
.trend svg .grid{stroke:var(--line);stroke-width:1}
.trend svg .l1{stroke:var(--s1);fill:none;stroke-width:2}
.trend svg .l2{stroke:var(--s2);fill:none;stroke-width:2}
.trend svg .p1{fill:var(--s1);stroke:var(--card);stroke-width:1.5}
.trend svg .p2{fill:var(--s2);stroke:var(--card);stroke-width:1.5}
.key .sw1,.key .sw2{display:inline-block;width:16px;height:3px}
.key .sw1{background:var(--s1)}.key .sw2{background:var(--s2)}
table.sum td small.up{color:var(--tt-ink);font-weight:700}
table.sum td small.down{color:var(--rm-ink);font-weight:700}
table.sum tr.now td{background:rgba(31,95,191,.06)}
table.viz{border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:8px;margin:8px 0;font-size:13px}
table.viz th,table.viz td{padding:4px 10px;text-align:left;vertical-align:middle;white-space:nowrap}
table.viz th{color:var(--mute);font-weight:600;font-size:12px;border-bottom:1px solid var(--line)}
table.viz tr.first td{border-top:1px solid var(--line)}
table.viz td.n{text-align:right;font-variant-numeric:tabular-nums}
table.viz td.w{color:var(--mute)}
.axis{display:flex;justify-content:space-between;width:300px;margin:0 6px;font-weight:400}
.trk{position:relative;height:18px;width:300px;margin:0 6px}
.trk .gr{position:absolute;top:0;bottom:0;width:1px;background:var(--line)}
.trk .lnk{position:absolute;top:8px;height:2px;background:var(--s1)}
.trk .dot,.key .dot{width:10px;height:10px;border-radius:50%;border:2px solid var(--s1);background:var(--card)}
.trk .dot{position:absolute;top:4px;margin-left:-5px;box-shadow:0 0 0 2px var(--card)}
.trk .dot.a,.key .dot.a{background:var(--s1)}
.key{display:inline-flex;align-items:center;gap:5px;margin-right:14px}
.key .dot{display:inline-block}
svg.strip{display:block;margin:0 6px}
table.sum.set td{vertical-align:top;font-size:12.5px;line-height:1.5}
table.sum.set td:nth-child(1){white-space:nowrap}
table.sum.set td:nth-child(2),table.sum.set td:nth-child(3){min-width:120px}
table.sum.set td:nth-child(4),table.sum.set td:nth-child(5){min-width:240px}
table.sum.set td:nth-child(6){min-width:150px;color:var(--mute)}
svg.strip .base{fill:var(--bg)}
svg.strip .mid{stroke:var(--line);stroke-width:1}
svg.strip .pass{fill:var(--s1);opacity:.16}
svg.strip .no{fill:var(--mute)}
svg.strip .yes{fill:var(--s1)}
svg.strip .cut{stroke:var(--ink);stroke-width:1.5}
.key .tick{display:inline-block;width:3px;height:12px;background:var(--s1)}
.key .shade{display:inline-block;width:18px;height:10px;background:var(--mute);opacity:.5}
.key .passk{display:inline-block;width:18px;height:14px;background:var(--s1);opacity:.16;border-left:2px solid var(--ink)}
table.viz td.kind{color:var(--mute)}
table.viz tr.pick td.kind{color:var(--ink);font-weight:700}
"""

JS = """
(function(){
  var sel=document.getElementById('f-label'),boxes=document.querySelectorAll('input[data-f]');
  if(!sel)return;
  function apply(){
    var want=sel.value,need=[];
    boxes.forEach(function(b){if(b.checked)need.push(b.dataset.f)});
    document.querySelectorAll('.blk').forEach(function(el){
      var ok=(want==='all'||el.dataset.label===want);
      need.forEach(function(f){if(el.dataset[f]!=='1')ok=false});
      el.classList.toggle('hide',!ok);
    });
    document.querySelectorAll('section.pgs').forEach(function(s){
      s.classList.toggle('hide',!s.querySelector('.blk:not(.hide)'));
    });
    var n=document.querySelectorAll('.blk:not(.hide)').length;
    document.getElementById('f-count').textContent=n+'개 덩어리 표시';
  }
  sel.addEventListener('change',apply);
  boxes.forEach(function(b){b.addEventListener('change',apply)});
  apply();
})();
"""


def _num(v: Optional[float], digits: int = 2) -> str:
    return "-" if v is None else ("%." + str(digits) + "f") % v


def _pct(v: Optional[float]) -> str:
    return "-" if v is None else "%.0f%%" % (100 * v)


def _cell(before: Optional[float], after: Optional[float], tip: str = "") -> str:
    """점수 칸. 학습 후가 있으면 '전 → 후'로 적고, 최신 점수의 크기만큼 초록을 진하게 칠한다. 0.5 이상이면 굵게."""
    latest = after if after is not None else before
    if latest is None:
        return "<td class=\"v\">-</td>"
    shade = "background-color:rgba(23,128,63,%.2f)" % (0.42 * max(0.0, min(1.0, latest)))
    show = lambda v: ("<b>%s</b>" if v >= 0.5 else "%s") % _num(v)
    text = show(before) if after is None else "<small>%s →</small> %s" % (_num(before), show(after))
    return "<td class=\"v\" style=\"%s\"%s>%s</td>" % (shade, " title=\"%s\"" % esc(tip) if tip else "", text)


def _label(v: Optional[int], derived: bool = False) -> str:
    if v == 1:
        return "<span class=\"lab y\">정답 예</span>"
    if v == 0:
        return "<span class=\"lab n\">정답 아니오</span>"
    return "<span class=\"lab q\">정답 없음</span>"


def _decide(v: Optional[float]) -> Optional[bool]:
    return None if v is None else v >= 0.5


# ---------------------------------------------------------------- 문서별 상세

def _block_html(res: Result, runs: List[ModelRun], b: BlockItem) -> str:
    names = [s.name + " " + s.text for s in res.sentences]
    label = res.block_labels.get(b.key)
    whole = [(r.block_score(b, "before"), r.block_score(b, "after")) for r in runs]
    merged = [(r.agg(b, "before"), r.agg(b, "after") if r.after["line"] is not None else None) for r in runs]
    d_whole = [_decide(a if a is not None else v) for v, a in whole]
    d_merged = [_decide(a if a is not None else v) for v, a in merged]
    known = [d for d in d_whole if d is not None]
    # 쪽 제목을 반영해서 판단이 바뀌었는가 (반영을 켰을 때만)
    moved = bool(res.title_weight) and ([_decide(r.block_score(b, "latest", 0.0)) for r in runs] != d_whole or
                                        [_decide(r.agg(b, "latest", 0.0)) for r in runs] != d_merged)
    # 시험용 문서라면: 지난번 기록과 견줘 판단(문턱 0.5)이 바뀌었는가
    old = {}
    if res.test_prev and b.uid.rsplit("#", 1)[0] in res.test_names:
        old = res.test_prev.get("scores") or {}

    def was(r: ModelRun, unit: str, uid: str) -> Optional[float]:
        return ((old.get(r.key) or {}).get(unit) or {}).get(uid)

    def flipped(r: ModelRun) -> bool:
        pairs = [(was(r, "block", b.uid), r.block_score(b))] + [(was(r, "line", l.uid), r.line_score(b, l)) for l in b.lines]
        return any(x is not None and y is not None and (x >= 0.5) != (y >= 0.5) for x, y in pairs)

    flags = {
        "changed": "1" if old and any(flipped(r) for r in runs) else "0",
        "title": "1" if moved else "0",
        "split": "1" if known and len(set(known)) > 1 else "0",                              # 모델끼리 판단이 갈림
        "unit": "1" if any(x is not None and y is not None and x != y for x, y in zip(d_whole, d_merged)) else "0",   # 덩어리와 줄의 판단이 다름
        "miss": "1" if label == 1 and any(d is False for d in d_whole + d_merged) else "0",   # 정답 예인데 못 넘은 모델이 있음
        "wrong": "1" if label == 0 and any(d is True for d in d_whole + d_merged) else "0",   # 정답 아니오인데 넘긴 모델이 있음
    }
    head = "<div class=\"hd\"><code>%s</code>%s%s%s<span>줄 %d개</span></div>" % (
        esc(b.id), "<span class=\"tag2\">표</span>" if b.kind == "table" else "",
        "<span class=\"tag2\" style=\"background:#a15c00\">표 위에 얹힌 글</span>" if b.over_table else "",
        _label(label), len(b.lines))
    rows = ["<tr><th>글</th>%s</tr>" % "".join("<th>%s</th>" % esc(r.spec["label"]) for r in runs)]
    def tip(r: ModelRun, unit: str, key: str, uid: str = "") -> str:
        out = ("가장 가까운 기준 문장: " + names[r.best[unit][key]]) if key in r.best[unit] else ""
        if old and was(r, unit, uid) is not None:
            out += " | 지난번 기록의 점수 %.2f" % was(r, unit, uid)
        if r.title_w:                              # 제목을 섞기 전의 글 점수와 제목 점수도 알려 준다
            s, t = r.score(unit, key), r.title_score(b.title)
            if s is not None and t is not None:
                out += " | 글 점수 %.2f, 제목 점수 %.2f → 섞은 점수 %.2f" % (s, t, (1 - r.title_w) * s + r.title_w * t)
        return out

    rows.append("<tr class=\"whole\"><td class=\"t\">덩어리로 넣음 (아래 줄을 모두 합친 글 하나)</td>%s</tr>" % "".join(
        _cell(v, a, tip(r, "block", b.key, b.uid)) for r, (v, a) in zip(runs, whole)))
    if len(b.lines) > 1:
        rows.append("<tr class=\"whole sumrow\"><td class=\"t\">줄로 넣어 합침 (아래 줄 점수 가운데 가장 높은 값)</td>%s</tr>" % "".join(
            _cell(v, a) for v, a in merged))
    for l in b.lines:
        rows.append("<tr><td class=\"t\">%s %s</td>%s</tr>" % (
            _label(res.labels.get(l.key)), esc(l.text), "".join(
                _cell(r.line_score(b, l, "before"), r.line_score(b, l, "after"), tip(r, "line", l.key, l.uid)) for r in runs)))
    return "<div class=\"blk\" data-label=\"%s\" data-split=\"%s\" data-unit=\"%s\" data-miss=\"%s\" data-wrong=\"%s\" data-title=\"%s\" data-changed=\"%s\">%s<table class=\"sc\">%s</table></div>" % (
        "n" if label is None else str(label), flags["split"], flags["unit"], flags["miss"], flags["wrong"], flags["title"], flags["changed"], head, "".join(rows))


def _title_line(runs: List[ModelRun], title: str) -> str:
    parts = []
    for r in runs:
        t = r.title_score(title)
        if t is not None:
            parts.append("%s <b>%s</b>" % (esc(r.spec["label"]), _num(t)))
    return "<div class=\"sub\" style=\"margin:-2px 0 6px\">제목 점수: %s</div>" % " · ".join(parts) if parts else ""


def write_doc(res: Result, doc: DocItems, path: Path, up: str = "../") -> None:
    """up: 이 화면이 놓이는 폴더에서 추출 결과 폴더(out)까지 올라가는 길."""
    runs = [r for r in res.runs if r.ok]
    parts = ["<style>%s</style>" % CSS]
    is_test = doc.name in res.test_names
    if is_test:
        parts.append("<p class=\"legend\"><span class=\"tag2\" style=\"background:#7a3fb0\">시험용 문서</span> 이 문서의 정답은 학습에 쓰지 않고 채점에만 씁니다. "
                     "그래서 여기의 '학습 후' 점수는 분류기가 처음 보는 글에 매긴 점수입니다.%s</p>" % (
                         " 칸에 마우스를 올리면 지난번 기록의 점수가 나오고, 위의 '지난번과 판단이 바뀐 것'을 체크하면 바뀐 덩어리만 볼 수 있습니다." if res.test_prev else ""))
    parts.append("<p class=\"legend\">덩어리마다 표 하나입니다. 맨 윗줄이 <b>덩어리로 넣었을 때</b>의 점수, 그 아래가 <b>줄로 넣었을 때</b> 줄마다의 점수입니다. "
                 "숫자는 '특허출원 검토가 필요한 쪽'으로 기운 정도(0~1)이고, 0.5 이상이면 굵게 적었습니다. 칸이 진한 초록일수록 점수가 높습니다. "
                 "<small>0.31 →</small> 0.82 처럼 적힌 칸은 학습 전 → 학습 후입니다. 칸에 마우스를 올리면 가장 가까웠던 기준 문장이 나옵니다.</p>")
    if res.title_weight:
        parts.append("<p class=\"legend\"><b>쪽 제목 반영이 켜져 있습니다 (비율 %g).</b> 칸의 숫자는 글 점수 %.0f%%에 그 쪽의 제목 점수 %.0f%%를 섞은 값입니다. "
                     "쪽마다 제목 점수를 적어 두었고, 칸에 마우스를 올리면 섞기 전의 글 점수가 나옵니다.</p>" % (
                         res.title_weight, 100 * (1 - res.title_weight), 100 * res.title_weight))
    bar = ("<div class=\"bar\"><b>보기</b><label>정답 <select id=\"f-label\"><option value=\"all\">전체</option><option value=\"1\">예</option>"
           "<option value=\"0\">아니오</option><option value=\"n\">없음</option></select></label>"
           "<label><input type=\"checkbox\" data-f=\"split\"> 모델끼리 판단이 다른 것</label>"
           "<label><input type=\"checkbox\" data-f=\"unit\"> 덩어리로 넣을 때와 줄로 넣을 때 판단이 다른 것</label>"
           "<label><input type=\"checkbox\" data-f=\"miss\"> 놓친 것(정답 예인데 0.5 미만)</label>"
           "<label><input type=\"checkbox\" data-f=\"wrong\"> 잘못 잡은 것(정답 아니오인데 0.5 이상)</label>"
           "%s%s<span id=\"f-count\" class=\"sub\"></span></div>" % (
               "<label><input type=\"checkbox\" data-f=\"title\"> 제목 반영으로 판단이 바뀐 것</label>" if res.title_weight else "",
               "<label><input type=\"checkbox\" data-f=\"changed\"> 지난번과 판단이 바뀐 것</label>" if is_test and res.test_prev else ""))
    page = None
    for b in doc.blocks:
        if b.page != page:
            if page is not None:
                parts.append("</section>")
            page = b.page
            parts.append("<section class=\"pgs\"><h3 class=\"pg\">%d쪽%s · <a href=\"%s%s#p%d\">추출 리포트에서 보기</a></h3>" % (
                page, " · 제목: " + esc(b.title) if b.title else "", up, esc(doc.report_file), page))
            if res.title_weight and b.title:
                parts.append(_title_line(runs, b.title))
        parts.append(_block_html(res, runs, b))
    if page is not None:
        parts.append("</section>")
    parts.append("<script>%s</script>" % JS)
    sub = "<a href=\"index.html\">걸러내기 비교 첫 화면</a> · 덩어리 %d개 · 줄 %d개" % (len(doc.blocks), len(doc.lines))
    Path(path).write_text(_shell(doc.name + " · 걸러내기", sub, bar, "".join(parts)), encoding="utf-8")


# ---------------------------------------------------------------- 첫 화면

def _metric_cells(m: Optional[dict], best_auc: Optional[float], target: float) -> str:
    if m is None:
        return "<td class=\"n\">-</td>" * 4
    auc = m["auc"]
    cls = " best" if (auc is not None and best_auc is not None and abs(auc - best_auc) < 1e-9) else ""
    return ("<td class=\"n%s\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s <small class=\"sub\">(문턱 %s)</small></td>" % (
        cls, _num(auc, 3), _pct(m["half"]["recall"]), _pct(m["half"]["pass"]), _pct(m["tuned"]["pass"]), _num(m["tuned"]["threshold"])))


def _gain_word(g: dict) -> str:
    if g["sure"]:
        return "나아짐"
    if g["worse"]:
        return "나빠짐"
    if abs(g["auc_gain"]) < 5e-4 and abs(g["auc_low"]) < 5e-4 and abs(g["auc_high"]) < 5e-4:
        return "변화 없음"
    return "우연일 수 있음"


def _track(before: Optional[float], after: Optional[float]) -> str:
    """순위 정확도 0.5~1.0 눈금 위에 학습 전(빈 점)과 학습 후(찬 점)를 찍고 선으로 잇는다."""
    pos = lambda v: 100.0 * max(0.0, min(1.0, (v - 0.5) / 0.5))
    parts = ["<div class=\"trk\">"] + ["<i class=\"gr\" style=\"left:%d%%\"></i>" % x for x in (0, 50, 100)]
    if before is not None and after is not None:
        lo, hi = sorted((pos(before), pos(after)))
        parts.append("<i class=\"lnk\" style=\"left:%.1f%%;width:%.1f%%\"></i>" % (lo, hi - lo))
    if before is not None:
        parts.append("<i class=\"dot\" style=\"left:%.1f%%\" title=\"학습 전 %.3f\"></i>" % (pos(before), before))
    if after is not None:
        parts.append("<i class=\"dot a\" style=\"left:%.1f%%\" title=\"학습 후 %.3f\"></i>" % (pos(after), after))
    return "".join(parts) + "</div>"


def _glance(runs: List[ModelRun]) -> str:
    """한눈에 보기: 보는 방식 × 모델마다 순위 정확도가 학습 전 → 후로 얼마나 움직였는가."""
    rows = []
    for view, view_name in VIEWS:
        for k, r in enumerate(runs):
            mb, ma = r.metrics.get(view, {}).get("before"), r.metrics.get(view, {}).get("after")
            g = r.metrics.get(view, {}).get("gain")
            b, a = (mb or {}).get("auc"), (ma or {}).get("auc")
            if b is None:
                continue
            first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
            change = "%+.3f" % g["auc_gain"] if g else ("-" if a is None else "%+.3f" % (a - b))
            rows.append("<tr%s>%s<td>%s</td><td>%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\"><b>%s</b></td><td class=\"w\">%s</td></tr>" % (
                " class=\"first\"" if k == 0 else "", first, esc(r.spec["label"]), _track(b, a), _num(b, 3), _num(a, 3) if a is not None else "-",
                change, _gain_word(g) if g else ("학습시키지 않는 모델" if r.spec["kind"] == "nli" else "")))
    if not rows:
        return ""
    return ("<p class=\"legend viz\"><b>한눈에 보기 · 순위 정확도</b> &nbsp; <span class=\"key\"><i class=\"dot\"></i>학습 전 (기준 문장만)</span>"
            "<span class=\"key\"><i class=\"dot a\"></i>학습 후 (정답으로 학습)</span> 점이 오른쪽에 있을수록 좋습니다. 점에 마우스를 올리면 값이 나옵니다.</p>"
            "<div class=\"wrap\"><table class=\"viz\"><tr><th>보는 방식</th><th>모델</th><th><div class=\"axis\"><span>0.5 (무작위)</span><span>0.75</span><span>1.0 (완벽)</span></div></th>"
            "<th>학습 전</th><th>학습 후</th><th>변화</th><th></th></tr>%s</table></div>" % "".join(rows))


STRIP_W, STRIP_BINS = 320, 64


def _strip(items: Optional[List[tuple]], target: float, name: str) -> str:
    """정답이 붙은 글을 점수 순서대로(왼쪽이 낮은 점수) 늘어놓은 두 줄짜리 띠.

    윗줄은 정답이 '예'인 글(파란 금 하나씩), 아랫줄은 '아니오'인 글(그 자리에 몰린 만큼 진한 회색).
    세로선은 '예'의 target을 찾는 문턱이고, 그 오른쪽의 옅은 파란 바탕이 다음 단계로 넘어가는 부분이다.
    점수의 크기가 아니라 순서로 그리므로, 점수의 단위가 다른 분류기끼리도 그대로 견줄 수 있다.
    """
    got = [(y, s) for y, s in (items or []) if y is not None and s is not None]
    yes, no = [s for y, s in got if y == 1], [s for y, s in got if y == 0]
    if not yes or not no:
        return ""
    n = len(got)
    order = sorted(range(n), key=lambda i: got[i][1])
    pos = [0.0] * n                                # 순위 위치 0~1. 같은 점수끼리는 가운데 자리
    i = 0
    while i < n:
        j = i
        while j + 1 < n and got[order[j + 1]][1] == got[order[i]][1]:
            j += 1
        for k in range(i, j + 1):
            pos[order[k]] = ((i + j) / 2.0 + 0.5) / n
        i = j + 1
    bins = [0] * STRIP_BINS
    for k, (y, _) in enumerate(got):
        if y == 0:
            bins[min(STRIP_BINS - 1, int(pos[k] * STRIP_BINS))] += 1
    top = max(bins)
    cut = learn.recall_threshold(np.array([y for y, _ in got]), np.array([s for _, s in got], dtype=float), target)   # '예'의 target을 찾는 문턱
    cut_x = STRIP_W * sum(1 for _, s in got if s < cut) / n
    passed = sum(1 for _, s in got if s >= cut)
    w = STRIP_W / float(STRIP_BINS)
    found = sum(1 for y, s in got if y == 1 and s >= cut)
    parts = ["<svg class=\"strip\" width=\"%d\" height=\"24\" viewBox=\"0 0 %d 24\" role=\"img\">" % (STRIP_W, STRIP_W),
             "<title>%s: 정답 붙은 글 %d개(예 %d, 아니오 %d)를 점수 낮은 것부터 늘어놓음. 세로선 오른쪽으로 %d개(%.0f%%)가 통과하고, 그 안에 '예'가 %d개</title>" % (
                 esc(name), n, len(yes), len(no), passed, 100.0 * passed / n, found),
             "<rect class=\"base\" x=\"0\" y=\"1\" width=\"%d\" height=\"22\"/>" % STRIP_W,
             "<rect class=\"pass\" x=\"%.1f\" y=\"1\" width=\"%.1f\" height=\"22\"/>" % (cut_x, STRIP_W - cut_x)]
    for b, c in enumerate(bins):                   # 아랫줄: 아니오
        if c:
            parts.append("<rect class=\"no\" x=\"%.1f\" y=\"14\" width=\"%.1f\" height=\"8\" opacity=\"%.2f\"/>" % (b * w, w, 0.12 + 0.58 * c / top))
    width = 2.0 if len(yes) <= 150 else 1.2
    for k, (y, _) in enumerate(got):               # 윗줄: 예
        if y == 1:
            parts.append("<rect class=\"yes\" x=\"%.1f\" y=\"2\" width=\"%.1f\" height=\"9\"/>" % (pos[k] * STRIP_W - width / 2, width))
    parts.append("<line class=\"mid\" x1=\"0\" x2=\"%d\" y1=\"12.5\" y2=\"12.5\"/>" % STRIP_W)
    parts.append("<line class=\"cut\" x1=\"%.1f\" x2=\"%.1f\" y1=\"0\" y2=\"24\"/></svg>" % (cut_x, cut_x))
    return "".join(parts)


def _classifier_section(res: Result, runs: List[ModelRun], target: str) -> str:
    """분류기 종류 비교: 기준 문장만, 로지스틱 회귀, 선형 SVM을 같은 정답으로 견준다."""
    if not any((r.metrics.get(v, {}).get("svm")) for r in runs for v, _ in VIEWS):
        return ""
    kinds = [("before", "기준 문장만 (학습 전)", 0.5), ("logreg", "로지스틱 회귀", 0.5), ("svm", "선형 SVM", 0.0)]
    p = ["<h2>분류기 종류 비교 (로지스틱 회귀 대 선형 SVM)</h2>"]
    p.append("<p class=\"legend\">같은 정답을 같은 묶음으로 나눠 두 가지 분류기를 학습시키고 견줬습니다(세기와 '예'에 무게를 더 주는 설정도 같게). "
             "화면의 '학습 후' 점수는 <b>로지스틱 회귀</b>의 것이고, 선형 SVM은 견줘 보려고 함께 돌린 것입니다. "
             "이 부분은 쪽 제목 반영 없이 글 점수로만 잽니다.</p>")
    p.append("<p class=\"legend viz\"><b>띠 읽는 법</b>: 정답이 붙은 글을 점수가 낮은 것(왼쪽)부터 높은 것(오른쪽)까지 늘어놓았습니다. "
             "<span class=\"key\"><i class=\"tick\"></i>윗줄: 정답이 '예'인 글</span><span class=\"key\"><i class=\"shade\"></i>아랫줄: 정답이 '아니오'인 글 (진할수록 많음)</span>"
             "<span class=\"key\"><i class=\"passk\"></i>'예'의 %s를 찾는 문턱과, 그 문턱을 넘어 다음 단계로 가는 부분</span><br>"
             "<b>윗줄의 파란 금은 오른쪽에, 아랫줄의 회색은 왼쪽에 몰려 있을수록</b> 잘 가른 것입니다. "
             "<b>옅은 파란 바탕이 좁을수록</b> 놓치지 않으면서 많이 걸러 낸 것입니다. 띠에 마우스를 올리면 개수가 나옵니다.</p>" % target)
    p.append("<div class=\"wrap\"><table class=\"viz\"><tr><th>보는 방식</th><th>모델</th><th>분류기</th>"
             "<th><div class=\"axis\" style=\"width:%dpx\"><span>← 점수 낮음</span><span>점수 높음 →</span></div></th>"
             "<th>순위 정확도</th><th>%s 찾는 문턱<br>통과 비율</th></tr>" % (STRIP_W, target))
    for view, view_name in VIEWS:
        first_view = True
        for r in runs:
            rows = []
            for kind, kind_name, boundary in kinds:
                items = view_items(res, r, view, kind)
                if items is None:
                    continue
                scored = [(y, s) for y, s in items if s is not None]
                m = learn.measure([y for y, _ in scored if y is not None], [s for y, s in scored if y is not None],
                                  [s for _, s in scored], res.target, boundary)
                rows.append((kind, kind_name, _strip(items, res.target, kind_name), m))
            if not rows:
                continue
            best = max((m["auc"] for _, _, _, m in rows if m and m["auc"] is not None), default=None)
            for k, (kind, kind_name, strip, m) in enumerate(rows):
                lead = ""
                if k == 0:
                    if first_view:
                        lead += "<td rowspan=\"%d\"><b>%s</b></td>" % (sum(1 for x in runs for kd, _, _ in kinds if view_items(res, x, view, kd) is not None), esc(view_name))
                        first_view = False
                    lead += "<td rowspan=\"%d\">%s</td>" % (len(rows), esc(r.spec["label"]))
                top = m is not None and best is not None and m["auc"] is not None and abs(m["auc"] - best) < 1e-9
                p.append("<tr class=\"%s%s\">%s<td class=\"kind\">%s</td><td>%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td></tr>" % (
                    "first " if k == 0 else "", "pick" if top else "", lead, esc(kind_name), strip,
                    ("<b>%s</b>" if top else "%s") % _num(m["auc"], 3) if m else "-", _pct(m["tuned"]["pass"]) if m else "-"))
    p.append("</table></div>")
    p.append("<p class=\"legend\">띠는 정답이 붙은 글만 그린 것이고, 오른쪽의 통과 비율은 정답이 없는 글까지 포함한 전체에서 잰 것이라 조금 다를 수 있습니다. "
             "굵은 글씨는 그 모델·보는 방식에서 순위 정확도가 가장 높은 분류기입니다.</p>")
    # 수치로 견주기
    words = ("선형 SVM이 나음", "로지스틱 회귀가 나음", "차이를 가릴 수 없음", "차이 없음")
    p.append("<p class=\"legend\"><b>수치로 견주기</b>: 차이는 선형 SVM − 로지스틱 회귀입니다. 괄호의 범위 전체가 0보다 크면 선형 SVM이, 0보다 작으면 로지스틱 회귀가 낫고, "
             "0을 걸치면 지금 정답으로는 가릴 수 없습니다. '경계에서'는 분류기가 스스로 정한 경계(로지스틱 회귀는 0.5, 선형 SVM은 0)로 갈랐을 때입니다.</p>")
    p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th rowspan=\"2\">보는 방식</th><th rowspan=\"2\">모델</th>"
             "<th colspan=\"4\" class=\"grp\">로지스틱 회귀</th><th colspan=\"4\" class=\"grp\">선형 SVM</th><th colspan=\"2\" class=\"grp\">차이 (선형 SVM − 로지스틱 회귀)</th></tr>"
             "<tr>%s<th>순위 정확도 차이</th><th>%s 찾는 문턱<br>통과 비율 차이</th></tr>" % (
                 ("<th>순위 정확도</th><th>경계에서<br>찾아낸 비율</th><th>경계에서<br>통과 비율</th><th>%s 찾는 문턱<br>통과 비율</th>" % target) * 2, target))
    notes = []
    for view, view_name in VIEWS:
        shown = [r for r in runs if r.metrics.get(view, {}).get("svm")]
        for k, r in enumerate(shown):
            s = r.metrics[view]["svm"]
            aucs = [m["auc"] for m in (s["logreg"], s["svm"]) if m and m["auc"] is not None]
            best = max(aucs) if aucs else None
            first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(shown), esc(view_name)) if k == 0 else ""
            p.append("<tr>%s<td>%s</td>%s%s%s</tr>" % (
                first, esc(r.spec["label"]), _metric_cells(s["logreg"], best, res.target),
                _metric_cells(s["svm"], best, res.target).replace("<td class=\"n", "<td class=\"g n"), _gain_cells(s["gain"], words)))
    for r in runs:
        for unit, name in (("block", "덩어리"), ("line", "줄")):
            if r.svm_note[unit]:
                notes.append("%s · %s: %s" % (esc(r.spec["label"]), name, esc(r.svm_note[unit])))
    p.append("</table></div>")
    if notes:
        p.append("<p class=\"legend\">%s</p>" % "<br>".join(notes))
    p.append("<p class=\"legend\">선형 SVM의 값은 0~1 점수가 아니라 경계에서 떨어진 정도라서(0이 경계), 문턱값의 단위가 로지스틱 회귀와 다릅니다. "
             "순위 정확도와 통과 비율은 단위와 상관없이 견줄 수 있습니다. 학습시킨 선형 SVM은 <code>모델__단위__svm.json</code>으로 함께 저장됩니다.</p>")
    p.append(_settings_table(runs))
    p.append(_process_table(runs))
    return "".join(p)


def _settings_table(runs: List[ModelRun]) -> str:
    """분류기에 실제로 적용된 설정값과 그 뜻, 고른 이유, 다른 선택지."""
    info = {u: next((r.train_info[u] for r in runs if r.train_info[u]), None) for u in ("block", "line")}
    any_info = info["line"] or info["block"]
    if not any_info:
        return ""
    lr, svm = any_info.get("logreg") or {}, any_info.get("svm") or {}

    def penalty(params: dict) -> str:
        if not params:
            return "-"
        kind = params.get("penalty")
        if kind in (None, "deprecated"):           # 새 라이브러리는 섞는 비율(l1_ratio)로 나타낸다. 0이면 L2만
            ratio = params.get("l1_ratio") or 0
            kind = "l2" if not ratio else ("l1" if ratio == 1 else "l1과 l2를 섞음(%s)" % ratio)
        return str(kind).upper() if kind in ("l1", "l2") else str(kind)

    def weight_note() -> str:
        parts = []
        for u, name in (("block", "덩어리"), ("line", "줄")):
            if info[u] and info[u]["yes"]:
                parts.append("%s는 예 %d개, 아니오 %d개라 '예' 하나를 '아니오' %.1f개만큼" % (name, info[u]["yes"], info[u]["no"], info[u]["no"] / float(info[u]["yes"])))
        return " 지금 정답으로는 " + " / ".join(parts) + " 무겁게 봅니다." if parts else ""

    def fold_note() -> str:
        parts = []
        for u, name in (("block", "덩어리"), ("line", "줄")):
            if info[u]:
                parts.append("%s %d묶음%s" % (name, info[u]["folds"], "" if info[u]["grouped"] else "(쪽으로 묶지 못해 섞어 나눔)"))
        return ", ".join(parts)

    g = lambda params, key: "-" if not params or params.get(key) is None else str(params.get(key))
    rows = [
        ("분류기의 모양", "선형 (로지스틱 회귀)", "선형 (서포트 벡터 머신)" if svm else "-",
         "글의 숫자마다 가중치를 곱해 모두 더한 값으로 판단합니다. 두 분류기는 이 모양이 같고, 가중치를 정하는 기준만 다릅니다.",
         "이런 숫자 묶음은 뜻이 다른 글이 단순한 경계로 갈리도록 만들어져 있어, 정답이 적어도 잘 맞고 빠릅니다.",
         "가까운 예시 찾기, 나무 계열, 작은 신경망, 모델 자체를 더 학습시키기"),
        ("틀린 정도를 재는 기준", "로그 손실", ("힌지 손실 (loss=%s)" % g(svm, "loss")) if svm else "-",
         "로그 손실은 모든 예시를 조금씩 다 반영하고 0~1 점수를 냅니다. 힌지 손실은 경계 가까이에 있는 예시만 반영하고, 경계에서 떨어진 정도를 냅니다.",
         "두 분류기를 가르는 차이가 바로 이것입니다. 선형 SVM은 가장 기본이 되는 모양(힌지)으로 했습니다.",
         "선형 SVM의 제곱 힌지 손실(squared_hinge)"),
        ("벌점의 종류", penalty(lr), penalty(svm),
         "가중치가 커지는 것을 누르는 방식입니다. 붙인 예시만 외우지 않게 합니다. L2는 모든 가중치를 고르게 누릅니다.",
         "숫자 묶음은 숫자 하나하나가 뜻을 조금씩 나눠 갖고 있어, 일부만 남기는 L1보다 전부를 고르게 쓰는 L2가 맞습니다.",
         "L1(쓸모없는 가중치를 0으로 만듦), L1과 L2를 섞기, 벌점 없음"),
        ("벌점의 세기 (C)", g(lr, "C"), g(svm, "C"),
         "클수록 덜 누릅니다. 작으면 점수가 가운데로 몰리고, 너무 크면 붙인 예시를 외웁니다.",
         "길이를 1로 맞춘 숫자 묶음은 숫자 하나하나가 작아서, 라이브러리 기본값 1.0으로는 너무 세게 눌립니다. "
         "두 분류기에 같은 값을 써서 차이가 '틀린 정도를 재는 기준'에서만 나오게 했습니다. <b>회사 자료로 맞춘 값은 아닙니다.</b>",
         "0.25, 1, 16처럼 여러 값을 시험해 가장 좋은 것을 고르기"),
        ("정답별 무게 (class_weight)", g(lr, "class_weight"), g(svm, "class_weight"),
         "balanced는 드문 쪽의 예시 하나를 그만큼 무겁게 본다는 뜻입니다." + weight_note(),
         "'예'가 드물어서, 그대로 두면 전부 '아니오'라고만 해도 대부분 맞는 셈이 되어 '예'를 놓칩니다. 걸러내기는 놓치지 않는 것이 중요합니다.",
         "무게를 주지 않기, 무게를 직접 정하기"),
        ("기준값 (fit_intercept)", {"True": "있음", "False": "없음"}.get(g(lr, "fit_intercept"), "-"), {"True": "있음", "False": "없음"}.get(g(svm, "fit_intercept"), "-"),
         "가중치 말고 숫자 하나를 더 배워 점수 전체의 높낮이를 맞춥니다.",
         "없으면 경계가 정해진 한 점을 지나야 해서 불리합니다. 라이브러리 기본값입니다.", "없음"),
        ("푸는 방법", g(lr, "solver"), "liblinear (쌍대 좌표 하강, dual=%s)" % g(svm, "dual") if svm else "-",
         "가중치를 찾아가는 계산 방법입니다. 같은 문제면 답은 같고 속도만 다릅니다.",
         "로지스틱 회귀는 라이브러리 기본값이고, 선형 SVM은 힌지 손실에 쓸 수 있는 방법입니다.",
         "로지스틱 회귀: liblinear, saga, newton-cg"),
        ("되풀이 한도 / 멈추는 기준", "%s번 / %s" % (g(lr, "max_iter"), g(lr, "tol")), "%s번 / %s" % (g(svm, "max_iter"), g(svm, "tol")) if svm else "-",
         "계산을 되풀이하는 최대 횟수와, 변화가 이보다 작아지면 멈춘다는 기준입니다.",
         "중간에 끊기지 않고 끝까지 계산되도록 넉넉하게 잡았습니다(라이브러리 기본값은 100번, 1000번).", "-"),
        ("입력", "길이를 1로 맞춘 숫자 묶음 그대로", "같음" if svm else "-",
         "모델이 만든 숫자 묶음을 다른 변환 없이 넣습니다.",
         "길이를 맞춘 것으로 충분하고, 정답이 적을 때는 변환을 더하면 불안정해집니다.",
         "숫자마다 평균과 크기를 맞추기, 숫자 수를 줄이기(PCA)"),
        ("시험 방법", "최대 5묶음으로 나눠 돌아가며 시험. 이번에는 " + fold_note(), "로지스틱 회귀와 똑같은 묶음" if svm else "-",
         "정답이 붙은 글의 점수는 그 글을 빼고 학습시킨 분류기가 매깁니다. 같은 쪽의 글은 같은 묶음에 둡니다.",
         "자기가 본 정답을 맞히는 것으로 수치가 부풀지 않게 하려는 것입니다. 같은 쪽의 비슷한 글이 학습과 시험에 갈라 들어가는 것도 막습니다.",
         "문서 단위로 묶기, 시험용 문서를 따로 떼어 두기"),
        ("학습에 필요한 최소 정답", "'예'와 '아니오' 각각 %d개" % any_info.get("min_each", 4), "같음" if svm else "-",
         "이보다 적으면 학습시키지 않습니다.",
         "나눠서 시험하려면 묶음마다 양쪽 정답이 있어야 합니다. 수치를 믿으려면 이보다 훨씬 많아야 합니다.", "-"),
    ]
    body = "".join("<tr><td><b>%s</b></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        esc(a), esc(b), esc(c), esc(d), e, esc(f)) for a, b, c, d, e, f in rows)
    return ("<details class=\"box\" style=\"max-width:none\" open><summary><b>분류기 설정</b> · 실제로 적용된 값, 뜻, 고른 이유, 다른 선택지 (scikit-learn %s)</summary>"
            "<p class=\"legend\">값은 학습에 쓴 라이브러리가 알려 준 그대로입니다. 모델 세 가지와 덩어리·줄 단위에 모두 같은 설정을 씁니다. "
            "화면의 '학습 후' 점수에 쓰이는 것은 로지스틱 회귀입니다.</p>"
            "<div class=\"wrap\"><table class=\"sum set\"><tr><th>설정</th><th>로지스틱 회귀</th><th>선형 SVM</th><th>뜻</th><th>이 값을 고른 이유</th><th>다른 선택지</th></tr>%s</table></div></details>" % (
                esc(any_info.get("sklearn", "")), body))


def _curve_svg(curve: list, width: int = 220, height: int = 64) -> str:
    """되풀이할수록 목적 함수 값이 줄어드는 모양(작은 꺾은선). curve: [[되풀이 횟수, 값], …]"""
    pts = [(float(k), float(v)) for k, v in curve or []]
    if len(pts) < 2:
        return ""
    x_max = max(k for k, _ in pts) or 1.0
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = (hi - lo) or 1.0
    left, right, top, bottom = 4.0, 6.0, 6.0, 14.0
    sx = lambda k: left + (width - left - right) * k / x_max
    sy = lambda v: top + (height - top - bottom) * (hi - v) / span
    line = " ".join("%.1f,%.1f" % (sx(k), sy(v)) for k, v in pts)
    dots = "".join("<circle cx=\"%.1f\" cy=\"%.1f\" r=\"2.2\" fill=\"var(--acc)\"><title>%d번째: %.4f</title></circle>" % (sx(k), sy(v), int(k), v)
                   for k, v in pts)
    return ("<svg viewBox=\"0 0 %d %d\" width=\"%d\" height=\"%d\" role=\"img\" aria-label=\"되풀이할수록 줄어드는 목적 함수 값\">"
            "<line x1=\"%.1f\" y1=\"%.1f\" x2=\"%.1f\" y2=\"%.1f\" stroke=\"var(--line)\"/>"
            "<polyline points=\"%s\" fill=\"none\" stroke=\"var(--acc)\" stroke-width=\"1.6\"/>%s"
            "<text x=\"%.1f\" y=\"%d\" font-size=\"9\" fill=\"var(--mute)\">0번</text>"
            "<text x=\"%.1f\" y=\"%d\" font-size=\"9\" fill=\"var(--mute)\" text-anchor=\"end\">%d번</text></svg>" % (
                width, height, width, height, left, height - bottom + 1, width - right, height - bottom + 1, line, dots,
                left, height - 2, width - right, height - 2, int(x_max)))


def _process_table(runs: List[ModelRun]) -> str:
    """학습 과정: 가중치를 찾아가는 동안 정해지고 나타난 값. 신경망 학습의 epoch·loss에 견줄 수 있는 것."""
    rows = []
    notes = []
    for r in runs:
        for u, name in (("block", "덩어리"), ("line", "줄")):
            info = r.train_info[u] or {}
            pr = info.get("process")
            if not pr:
                if info.get("process_note"):
                    notes.append("%s · %s: 학습 과정을 기록하지 못했습니다 (%s)" % (esc(r.spec["label"]), name, esc(info["process_note"])))
                continue
            folds = ", ".join("-" if v is None else str(v) for v in pr.get("fold_iters") or [])
            stop = "스스로 멈춤" if pr["converged"] else "<b style=\"color:var(--rm-ink)\">한도에 닿음</b>"
            svm = pr.get("svm") or {}
            svm_text = "-" if not svm else "%s번 (한도 %s번%s)" % (svm.get("iters"), svm.get("limit"), "" if svm.get("converged") else ", 한도에 닿았거나 덜 수렴함")
            rows.append(
                "<tr><td><b>%s</b></td><td>%s</td><td class=\"n\">%d개<br><small>예 %d · 아니오 %d</small></td>"
                "<td class=\"n\">예 %.2f<br>아니오 %.2f</td>"
                "<td class=\"n\"><b>%s번</b><br><small>묶음마다 %s</small></td><td>%s<br><small>한도 %d번 · 기준 %s</small></td>"
                "<td class=\"n\">%.4f → <b>%.4f</b><br><small>끝 값 = 평균 벌점 %.4f + 규제 몫 %.4f</small></td><td>%s</td>"
                "<td class=\"n\">%s</td><td class=\"n\">%.2f<br><small>기준값 %+.3f</small></td><td class=\"n\">%.2f초<br><small>학습 %d번</small></td><td class=\"n\">%s</td></tr>" % (
                    esc(r.spec["label"]), name, pr["n"], pr["yes"], pr["no"], pr["weight_yes"], pr["weight_no"],
                    pr["iters"], folds or "-", stop, pr["limit"], pr["tol"],
                    pr["start"]["objective"], pr["end"]["objective"], pr["end"]["loss"], pr["end"]["penalty"],
                    _curve_svg(pr.get("curve")) or "-", _pct(pr.get("train_hit")), pr["norm"], pr["intercept"], pr["seconds"], pr.get("fits", 0), svm_text))
            if pr.get("curve_note"):
                notes.append("%s · %s: %s" % (esc(r.spec["label"]), name, esc(pr["curve_note"])))
    if not rows:
        return ""
    return ("<details class=\"box\" style=\"max-width:none\" open><summary><b>학습 과정</b> · 가중치를 찾아가는 동안 실제로 나타난 값 "
            "(신경망 학습의 epoch · batch · loss에 해당하는 것)</summary>"
            "<p class=\"legend\">분류기(로지스틱 회귀)의 가중치는 '목적 함수 값'을 가장 작게 만드는 값으로 정해집니다. "
            "<b>목적 함수 값 = 평균 벌점 + 규제 몫</b>입니다. 평균 벌점은 정답에 준 확률이 낮을수록 커지는 값(로그 손실)에 정답별 무게를 곱해 평균한 것이고, "
            "규제 몫은 가중치가 커진 만큼의 벌점(½‖w‖² ÷ (C × 무게의 합))입니다. 가중치가 모두 0인 처음에는 어느 글에나 0.5를 주므로 0.6931(= log 2)에서 시작합니다.</p>"
            "<p class=\"legend\"><b>되풀이</b> 한 번은 학습에 쓴 정답 <b>전체</b>로 가중치를 한 번 고치는 일입니다(신경망으로 치면 1 epoch, 묶음은 나누지 않음). "
            "몇 번 할지 미리 정하지 않고, 더 줄어들지 않으면(기울기가 기준보다 작아지면) 스스로 멈춥니다. 한도에 닿았다면 끝까지 줄이지 못한 것입니다. "
            "걸음의 크기(학습률)는 계산 방법(lbfgs)이 매번 스스로 정하고, 답이 하나뿐인 문제라 다시 학습해도 같은 가중치가 나옵니다.</p>"
            "<div class=\"wrap\"><table class=\"sum proc\"><tr><th>모델</th><th>넣는 크기</th><th>학습에 쓴 정답</th><th>정답별 무게</th><th>되풀이 횟수</th>"
            "<th>멈춘 까닭</th><th>목적 함수 값 (처음 → 끝)</th><th>줄어드는 모양</th><th>학습한 정답을 다시 맞힌 비율</th><th>가중치의 크기 ‖w‖</th><th>걸린 시간</th>"
            "<th>선형 SVM의 되풀이</th></tr>%s</table></div>"
            "<p class=\"legend\">· <b>정답별 무게</b>는 전체 수 ÷ (2 × 그 정답의 수)입니다(class_weight=balanced). '예' 하나를 틀린 벌점에 이 무게가 곱해집니다.<br>"
            "· <b>되풀이 횟수</b>의 큰 숫자는 저장하는 분류기(모든 학습용 정답으로 학습)의 것이고, '묶음마다'는 나눠서 시험할 때 묶음 하나를 빼고 학습한 것들의 횟수입니다.<br>"
            "· <b>줄어드는 모양</b>의 점에 마우스를 올리면 몇 번째 되풀이의 값인지 나옵니다. 되풀이 한도를 그 횟수로 줄여 다시 학습시킨 값이라, 끝까지 간 학습의 그 자리와 같습니다.<br>"
            "· <b>학습한 정답을 다시 맞힌 비율</b>은 이미 본 정답을 0.5 문턱으로 다시 맞힌 비율이라 높게 나옵니다. 성능은 위 표의 수치(그 글을 빼고 학습시킨 분류기의 점수)로 봐야 합니다.<br>"
            "· 이 표는 기록만 합니다. 학습 결과와 점수는 이 표가 없던 때와 같습니다. 같은 값이 실행 창과 <code>scores.json</code>의 <code>training_process</code>에도 남습니다.%s</p></details>" % (
                "".join(rows), "".join("<br>· " + n for n in notes)))


def _gain_cells(g: Optional[dict], words: Optional[tuple] = None) -> str:
    """개선 정도 칸 둘: 순위 정확도 변화(범위 포함), 같은 만큼 찾을 때의 통과 비율 변화.

    words: (나아졌을 때, 나빠졌을 때, 가릴 수 없을 때, 차이가 없을 때)의 말. 없으면 나아짐/나빠짐/우연일 수 있음/변화 없음
    """
    if g is None:
        return "<td class=\"n\">-</td><td class=\"n\">-</td>"
    word = _gain_word(g)
    if words:
        word = {"나아짐": words[0], "나빠짐": words[1], "우연일 수 있음": words[2], "변화 없음": words[3]}[word]
    cls = "up" if g["sure"] else "down" if g["worse"] else "flat"
    first = "<td class=\"n %s\">%+.3f <small class=\"sub\">(%+.3f ~ %+.3f) %s</small></td>" % (
        cls, g["auc_gain"], g["auc_low"], g["auc_high"], word)
    pg = g["pass_gain"]
    cls2 = "up" if pg < -0.005 else "down" if pg > 0.005 else "flat"
    second = "<td class=\"n %s\">%s → %s <small class=\"sub\">(%s)</small></td>" % (
        cls2, _pct(g["pass_before"]), _pct(g["pass_after"]), "%+.0f%%p" % (100 * pg) if abs(pg) >= 0.005 else "같음")
    return first + second


def _candidates(runs: List[ModelRun], views, basis: str) -> List[dict]:
    """가장 좋은 조합을 고를 후보: 모델 × 보는 방식 × 학습 전/후.  basis: test(시험 문서로 잰 값) | train(시험용이 아닌 문서로 잰 값)"""
    out = []
    for r in runs:
        for view, name in views:
            m = r.metrics.get(view) or {}
            src = (m.get("test") or {}) if basis == "test" else m
            for when, wname in (("before", "학습 전"), ("after", "학습 후")):
                got = src.get(when)
                if got is not None and got.get("auc") is not None:
                    out.append({"auc": got["auc"], "pass": got["tuned"]["pass"], "model": r.spec["label"], "view": name, "when": wname})
    return out


def _combo(c: dict, target: str) -> str:
    return "%s · %s · %s (순위 정확도 %s, %s 찾는 문턱에서 통과 비율 %s)" % (
        esc(c["model"]), esc(c["view"]), c["when"], _num(c["auc"], 3), target, _pct(c["pass"]))


def _headline(res: Result, runs: List[ModelRun]) -> str:
    """정답으로 잰 결과 가운데 가장 좋은 조합. 무엇으로 골랐는지를 함께 적는다.

    시험 문서로 잰 값이 있으면 그것으로 고른다(학습에 쓰지 않은 글이라 새 문서에서의 결과에 가장 가깝다).
    덩어리 단위(앞의 두 방식)와 줄 단위는 채점하는 대상이 달라 따로 고른다.
    순위 정확도가 가장 높은 것을 고르고, 통과 비율이 가장 낮은 조합이 그것과 다르면 함께 적는다.
    """
    target = "%.0f%%" % (100 * res.target)
    basis = "test" if res.test_names and _candidates(runs, VIEWS, "test") else "train"
    rows = []
    for group, views in (("덩어리 단위", VIEWS[:2]), ("줄 단위", VIEWS[2:])):
        cands = _candidates(runs, views, basis)
        if not cands:
            continue
        top = max(cands, key=lambda c: c["auc"])
        line = "<b>%s</b>: %s" % (group, _combo(top, target))
        others = [c for c in cands if c["model"] != top["model"]]
        if others:                                   # 다른 모델과 얼마나 벌어져 있는가
            nxt = max(others, key=lambda c: c["auc"])
            gap = top["auc"] - nxt["auc"]
            line += "<br><span class=\"sub\">다른 모델 가운데 가장 높은 것: %s · %s · %s %s (차이 %s%s)</span>" % (
                esc(nxt["model"]), esc(nxt["view"]), nxt["when"], _num(nxt["auc"], 3), _num(gap, 3),
                " — 차이가 작아 비슷한 것으로 보는 편이 안전합니다" if gap < 0.02 else "")
        low = min(cands, key=lambda c: c["pass"])
        if low["pass"] < top["pass"] - 1e-9:         # 통과 비율로 고르면 다른 조합이 나올 때
            line += "<br><span class=\"sub\">통과 비율이 가장 낮은 조합은 다릅니다: %s</span>" % _combo(low, target)
        rows.append("<li>%s</li>" % line)
    if not rows:
        return ""
    if basis == "test":
        how = "<b>시험 문서로 잰 값</b>으로 골랐습니다(학습에 쓰지 않은 글이라 새 문서에서의 결과에 가장 가깝습니다)."
    elif res.test_names:
        how = ("<b>시험용이 아닌 문서로 잰 값</b>으로 골랐습니다(시험용 문서에 '예'와 '아니오' 정답이 모두 있어야 시험 문서로 고를 수 있습니다. "
               "이 값은 같은 문서의 다른 글로 학습한 분류기가 매긴 것이라 실제보다 조금 좋게 나올 수 있습니다).")
    else:
        how = ("<b>정답이 붙은 문서 전체로 잰 값</b>으로 골랐습니다(시험용 문서를 정해 두면 그것으로 고릅니다. "
               "이 값은 같은 문서의 다른 글로 학습한 분류기가 매긴 것이라 실제보다 조금 좋게 나올 수 있습니다).")
    return ("<p><b>지금까지 가장 좋은 조합</b></p><ul class=\"steps\">%s</ul>"
            "<p class=\"sub\"><b>고른 방법</b>: %s 그 가운데 <b>순위 정확도가 가장 높은 조합</b>을 골랐습니다"
            "(통과 비율은 문턱 한 곳만 보는 값이라 정답이 적을 때 더 흔들립니다. 통과 비율로 고르면 다른 조합이 나올 때는 함께 적습니다). "
            "덩어리 단위와 줄 단위는 채점하는 대상이 달라 서로 견줄 수 없어 따로 적습니다. "
            "다른 모델과의 차이가 0.02보다 작으면 비슷하다고 적는데, 0.02는 회사 자료로 맞춘 값이 아니라 어림으로 둔 기준입니다.</p>" % ("".join(rows), how))


def _title_section(res: Result, runs: List[ModelRun], has_labels: bool, target: str) -> str:
    """쪽 제목을 반영한 효과: 반영 전 → 후의 개선 정도, 비율을 바꿨을 때의 수치, 제목마다의 점수."""
    w = res.title_weight
    p = ["<h2>쪽 제목을 반영한 효과 (반영 전 → 후)</h2>"]
    p.append("<p class=\"legend\">쪽 제목에 기준 문장으로 점수를 매겨(글의 학습 전 점수와 같은 방법. 학습 후에도 제목 점수는 이 값을 씁니다), "
             "그 쪽에 있는 덩어리와 줄의 점수에 섞었습니다. <b>최종 점수 = (1 − %g) × 글 점수 + %g × 제목 점수</b>. 제목이 없는 쪽은 글 점수 그대로입니다. "
             "<b>반영 전</b>은 글 점수만, <b>반영 후</b>는 섞은 점수이고, 같은 항목·같은 정답으로 짝지어 비교했습니다. 읽는 법은 위의 개선 정도와 같습니다.</p>" % (w, w))
    if not has_labels:
        p.append("<p class=\"legend\">정답을 붙이면 수치가 나옵니다.</p>")
    else:
        stages = [(when, name) for when, name in (("before", "학습 전"), ("after", "학습 후"))
                  if any(((r.metrics.get(v, {}).get("title") or {}).get(when)) for r in runs for v, _ in VIEWS)]
        # 반영 전 → 후
        p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th rowspan=\"2\">보는 방식</th><th rowspan=\"2\">모델</th>%s</tr><tr>%s</tr>" % (
            "".join("<th colspan=\"4\" class=\"grp\">%s 점수에 반영</th>" % name for _, name in stages),
            ("<th>순위 정확도<br>반영 전</th><th>순위 정확도<br>반영 후</th><th>순위 정확도 변화</th><th>%s 찾는 문턱<br>통과 비율 변화</th>" % target) * len(stages)))
        for view, view_name in VIEWS:
            for k, r in enumerate(runs):
                cells = ""
                for when, _ in stages:
                    g = ((r.metrics.get(view, {}).get("title") or {}).get(when) or {}).get("gain")
                    cells += "<td class=\"n\">%s</td><td class=\"n\">%s</td>%s" % (
                        _num(g["auc_before"], 3) if g else "-", _num(g["auc_after"], 3) if g else "-", _gain_cells(g))
                first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
                p.append("<tr>%s<td>%s</td>%s</tr>" % (first, esc(r.spec["label"]), cells))
        p.append("</table></div>")
        # 비율을 바꿨을 때
        p.append("<p class=\"legend\"><b>비율을 바꿨을 때</b>: 칸은 순위 정확도이고 괄호는 '예'의 %s를 찾는 문턱에서의 통과 비율입니다. "
                 "0이 반영하지 않은 것이고, <span class=\"plus\">초록 굵은 글씨</span>는 그 줄에서 순위 정확도가 가장 높은 칸, 테두리를 친 칸이 지금 쓰는 비율(%g)입니다.</p>" % (target, w))
        for when, name in stages:
            weights = None
            rows = []
            for view, view_name in VIEWS:
                for k, r in enumerate(runs):
                    sweep = ((r.metrics.get(view, {}).get("title") or {}).get(when) or {}).get("sweep")
                    first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
                    if not sweep:
                        rows.append("<tr>%s<td>%s</td><td class=\"n\" colspan=\"9\">-</td></tr>" % (first, esc(r.spec["label"])))
                        continue
                    weights = weights or [x["w"] for x in sweep]
                    aucs = [x["auc"] for x in sweep if x["auc"] is not None]
                    best = max(aucs) if aucs else None
                    cells = ""
                    for x in sweep:
                        style = " style=\"outline:2px solid var(--acc);outline-offset:-2px\"" if abs(x["w"] - w) < 1e-9 else ""
                        cls = " best" if x["auc"] is not None and best is not None and abs(x["auc"] - best) < 1e-9 else ""
                        cells += "<td class=\"n%s\"%s>%s <small class=\"sub\">(%s)</small></td>" % (cls, style, _num(x["auc"], 3), _pct(x["pass"]))
                    rows.append("<tr>%s<td>%s</td>%s</tr>" % (first, esc(r.spec["label"]), cells))
            if weights:
                p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th>%s 점수</th><th>모델</th>%s</tr>%s</table></div>" % (
                    name, "".join("<th>비율 %g%s</th>" % (x, " (반영 안 함)" if not x else "") for x in weights), "".join(rows)))
    # 제목마다의 점수
    count: dict = {}
    for b in res.blocks:
        if b.title.strip():
            count[b.title] = count.get(b.title, 0) + 1
    if count and runs:
        order = sorted(count, key=lambda t: -(runs[0].title_score(t) or 0))
        shown = order[:400]
        body = []
        for t in shown:
            cells = ""
            for r in runs:
                cells += _cell(r.title_score(t), None)
            body.append("<tr><td>%s</td><td class=\"n\">%d</td>%s</tr>" % (esc(t), count[t], cells))
        p.append("<details class=\"box\" style=\"max-width:none\"><summary>제목마다의 점수 보기 (%d가지%s)</summary>"
                 "<p class=\"legend\">%s가 매긴 점수가 높은 순서입니다. 점수가 높을수록 그 쪽의 글 점수를 올리고, 낮을수록 내립니다. "
                 "엉뚱한 점수가 붙은 제목이 많다면 기준 문장을 고치거나 비율을 낮추세요.</p>"
                 "<div class=\"wrap\"><table class=\"sc\" style=\"width:auto\"><tr><th>제목</th><th>덩어리 수</th>%s</tr>%s</table></div></details>" % (
                     len(order), ", 앞의 400가지만 표시" if len(order) > len(shown) else "", esc(runs[0].spec["label"]),
                     "".join("<th>%s</th>" % esc(r.spec["label"]) for r in runs), "".join(body)))
    return "".join(p)


def _test_section(res: Result, runs: List[ModelRun], target: str) -> str:
    """시험용 문서로 잰 결과: 학습 전·후, 지난번 기록과의 비교(그림·수치·판단이 바뀐 글), 기록."""
    if not res.test_names:
        return ""
    tc, trc = res.label_counts("test"), res.trained_on()
    p = ["<h2>시험 문서로 잰 결과</h2>"]
    p.append("<p class=\"legend\"><b>시험용 문서 %d개</b>: %s. 이 문서들의 정답(줄 기준 예 %d개, 아니오 %d개)은 학습에 쓰지 않고 채점에만 씁니다. "
             "분류기가 처음 보는 글로 재는 것이라, 실제로 새 문서에 썼을 때의 결과에 가장 가깝습니다. "
             "학습에 쓴 정답은 서로 다른 줄 기준 예 %d개, 아니오 %d개입니다(시험용 문서에도 똑같이 나오는 글은 학습에서 뺐습니다).</p>" % (
                 len(res.test_names), ", ".join(esc(n) for n in res.test_names), tc["line_yes"], tc["line_no"], trc["line_yes"], trc["line_no"]))
    tests = {(r.key, v): (r.metrics.get(v) or {}).get("test") or {} for r in runs for v, _ in VIEWS}
    if not any(t.get("before") for t in tests.values()):
        p.append("<p class=\"legend\"><b>아직 수치를 낼 수 없습니다.</b> 시험용 문서에도 정답을 붙여야 채점할 수 있습니다. "
                 "<code>label.bat</code> 화면에서 시험용 문서를 골라 '예'와 '아니오'가 모두 나오도록 붙여 주세요(덩어리는 '남은 줄 모두 아니오'로 끝까지).</p>")
        return "".join(p)

    # 그림: 학습 전 / (지난번) / 이번
    prev = res.test_prev
    p.append("<p class=\"legend viz\"><b>한눈에 보기</b>: 시험 문서의 정답 붙은 글을 점수가 낮은 것(왼쪽)부터 높은 것(오른쪽)까지 늘어놓았습니다. "
             "<span class=\"key\"><i class=\"tick\"></i>윗줄: 정답이 '예'인 글</span><span class=\"key\"><i class=\"shade\"></i>아랫줄: 정답이 '아니오'인 글</span>"
             "<span class=\"key\"><i class=\"passk\"></i>'예'의 %s를 찾는 문턱과 그것을 넘는 부분</span> "
             "파란 금은 오른쪽에, 회색은 왼쪽에 몰릴수록, 파란 바탕은 좁을수록 좋습니다.%s</p>" % (
                 target, " <b>지난번</b>은 학습 상태가 지금과 달랐던 마지막 기록(%s)입니다." % esc(prev.get("made", "")) if prev else ""))
    p.append("<div class=\"wrap\"><table class=\"viz\"><tr><th>보는 방식</th><th>모델</th><th>언제</th>"
             "<th><div class=\"axis\" style=\"width:%dpx\"><span>← 점수 낮음</span><span>점수 높음 →</span></div></th>"
             "<th>순위 정확도</th><th>%s 찾는 문턱<br>통과 비율</th></tr>" % (STRIP_W, target))
    for view, view_name in VIEWS:
        first_view = True
        per = 2 + (1 if prev else 0)
        for r in runs:
            t = tests[(r.key, view)]
            unit = "line" if view != "block" else "block"
            rows = [("기준 문장만 (학습 전)", _items(res, r, view, "before", None, "test"))]
            if prev:
                rows.append(("지난번", r.test_vs.get(view, {}).get("prev")))
            rows.append(("이번" + (" (학습 후)" if r.after[unit] is not None else " (학습 전과 같음)"), _items(res, r, view, "latest", None, "test")))
            for k, (name, items) in enumerate(rows):
                scored = [(y, s) for y, s in (items or []) if s is not None]
                m = learn.measure([y for y, _ in scored if y is not None], [s for y, s in scored if y is not None],
                                  [s for _, s in scored], res.target) if scored else None
                lead = ""
                if k == 0:
                    if first_view:
                        lead += "<td rowspan=\"%d\"><b>%s</b></td>" % (per * len(runs), esc(view_name))
                        first_view = False
                    lead += "<td rowspan=\"%d\">%s</td>" % (per, esc(r.spec["label"]))
                last = k == len(rows) - 1
                p.append("<tr class=\"%s%s\">%s<td class=\"kind\">%s</td><td>%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td></tr>" % (
                    "first " if k == 0 else "", "pick" if last else "", lead, esc(name), _strip(items, res.target, name) or "<span class=\"sub\">-</span>",
                    ("<b>%s</b>" if last else "%s") % _num(m["auc"], 3) if m else "-", _pct(m["tuned"]["pass"]) if m else "-"))
    p.append("</table></div>")

    # 수치: 학습 전 → 후 (시험 문서)
    p.append("<p class=\"legend\"><b>학습 전 → 학습 후 (시험 문서)</b>: 읽는 법은 아래 '학습 전과 학습 후 비교'와 같습니다. 선형 SVM은 견주기용입니다.</p>")
    p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th rowspan=\"2\">보는 방식</th><th rowspan=\"2\">모델</th><th rowspan=\"2\">시험 정답 수<br>(예/아니오)</th>"
             "<th colspan=\"4\" class=\"grp\">학습 전 (기준 문장만)</th><th colspan=\"4\" class=\"grp\">학습 후 (학습용 정답으로 학습)</th>"
             "<th colspan=\"2\" class=\"grp\">개선 정도 (학습 후 − 학습 전)</th><th rowspan=\"2\">선형 SVM<br>순위 정확도</th></tr><tr>%s<th>순위 정확도 변화</th><th>%s 찾는 문턱<br>통과 비율 변화</th></tr>" % (
                 "<th>순위 정확도</th><th>0.5 문턱<br>찾아낸 비율</th><th>0.5 문턱<br>통과 비율</th><th>%s 찾는 문턱<br>통과 비율</th>" % target * 2, target))
    for view, view_name in VIEWS:
        aucs = [m["auc"] for r in runs for m in (tests[(r.key, view)].get("before"), tests[(r.key, view)].get("after")) if m and m["auc"] is not None]
        best = max(aucs) if aucs else None
        for k, r in enumerate(runs):
            t = tests[(r.key, view)]
            mb, ma, sv = t.get("before"), t.get("after"), t.get("svm")
            first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
            p.append("<tr>%s<td>%s</td><td class=\"n\">%s</td>%s%s%s<td class=\"n\">%s</td></tr>" % (
                first, esc(r.spec["label"]), "%d / %d" % (mb["yes"], mb["no"]) if mb else "-", _metric_cells(mb, best, res.target),
                _metric_cells(ma, best, res.target).replace("<td class=\"n", "<td class=\"g n"), _gain_cells(t.get("gain")),
                _num(sv["auc"], 3) if sv else "-"))
    p.append("</table></div>")

    # 지난번 → 이번
    if prev:
        ptr, ntr = prev.get("train") or {}, trc
        notes = ["학습에 쓴 정답(서로 다른 줄): 예 %s → %d개, 아니오 %s → %d개" % (ptr.get("line_yes", "?"), ntr["line_yes"], ptr.get("line_no", "?"), ntr["line_no"])]
        now_snap = res.history[-1] if res.history else {}
        notes.append("기준 문장: " + ("바뀜" if prev.get("sentences") != now_snap.get("sentences") else "같음"))
        notes.append("쪽 제목 비율: %g → %g" % (prev.get("title_weight", 0), res.title_weight))
        if prev.get("test_docs") != now_snap.get("test_docs"):
            notes.append("시험용 문서 목록이 바뀜(두 번 모두에 있는 글만 견줌)")
        p.append("<h2 style=\"font-size:14px\">지난번 → 이번 (같은 시험 글, 같은 정답으로 견줌)</h2>")
        p.append("<p class=\"legend\">지난번 기록: %s · 달라진 것: %s.<br>같은 시험 글에 지난번 매긴 점수와 이번에 매긴 점수를 지금의 정답으로 짝지어 견줬습니다. "
                 "괄호의 범위 전체가 0보다 크면 <b>나아짐</b>, 0을 걸치면 <b>우연일 수 있음</b>입니다. "
                 "<b>판단이 바뀐 글</b>은 문턱 0.5로 본 통과 여부가 달라진 글 수이고, 맞게 바뀐 것과 틀리게 바뀐 것으로 나눴습니다.</p>" % (
                     esc(prev.get("made", "")), " · ".join(esc(n) for n in notes)))
        p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th>보는 방식</th><th>모델</th><th>순위 정확도<br>지난번</th><th>순위 정확도<br>이번</th>"
                 "<th>순위 정확도 변화</th><th>%s 찾는 문턱<br>통과 비율 변화</th><th>판단이 바뀐 글<br>(맞게 / 틀리게 / 정답 없음)</th></tr>" % target)
        for view, view_name in VIEWS:
            for k, r in enumerate(runs):
                t = tests[(r.key, view)]
                g, ch = t.get("vs_prev"), t.get("changed") or {}
                first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
                p.append("<tr>%s<td>%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td>%s<td class=\"n\">%s</td></tr>" % (
                    first, esc(r.spec["label"]), _num(g["auc_before"], 3) if g else "-", _num(g["auc_after"], 3) if g else "-", _gain_cells(g),
                    "<span class=\"plus\">%d</span> / <span class=\"minus\">%d</span> / %d" % (ch.get("better", 0), ch.get("worse", 0), ch.get("unknown", 0)) if ch else "-"))
        p.append("</table></div>")
        # 판단이 바뀐 글 목록
        for r in runs:
            body, count = [], 0
            for view, view_name in (("block", "덩어리"), ("line", "줄")):
                for c in (r.test_vs.get(view, {}).get("changed") or []):
                    count += 1
                    if len(body) >= 300:
                        continue
                    up = c["new"] >= 0.5
                    if c["label"] is None:
                        way = "<span class=\"sub\">정답 없음</span>"
                    elif up == (c["label"] == 1):
                        way = "<span class=\"plus\">맞게 바뀜</span>"
                    else:
                        way = "<span class=\"minus\">틀리게 바뀜</span>"
                    text = c["text"] if len(c["text"]) <= 160 else c["text"][:160] + "…"
                    body.append("<tr><td>%s</td><td>%s · %s</td><td>%s</td><td class=\"v\">%s → <b>%s</b> %s</td><td>%s</td><td class=\"t\">%s</td></tr>" % (
                        view_name, esc(c["doc"]), esc(c["id"]), _label(c["label"]), _num(c["old"]), _num(c["new"]),
                        "통과로" if up else "탈락으로", way, esc(text)))
            if count:
                p.append("<details class=\"box\" style=\"max-width:none\"><summary>%s: 지난번과 판단이 바뀐 글 %d개 보기%s</summary>"
                         "<div class=\"wrap\"><table class=\"sc\"><tr><th>단위</th><th>문서 · 번호</th><th>정답</th><th>지난번 → 이번</th><th>바뀐 방향</th><th>글</th></tr>%s</table></div></details>" % (
                             esc(r.spec["label"]), count, " (앞의 300개만 표시)" if count > 300 else "", "".join(body)))
        p.append("<p class=\"legend\">문서별 화면에서도 시험용 문서는 '지난번과 판단이 바뀐 것'을 체크해 그 덩어리만 볼 수 있습니다.</p>")
    else:
        p.append("<p class=\"legend\"><b>지난번 → 이번</b>: 아직 견줄 기록이 없습니다. 학습용 정답을 더 붙이거나 기준 문장·설정을 바꾼 뒤 다시 계산하면, "
                 "같은 시험 글로 잰 지난번과 이번의 차이(수치와 판단이 바뀐 글)가 여기에 나옵니다.</p>")

    # 기록
    if res.history:
        head = "".join("<th>%s<br>덩어리로 넣음</th><th>%s<br>줄로 넣음</th>" % (esc(r.spec["label"]), esc(r.spec["label"])) for r in runs)
        body = []
        for i, snap in enumerate(res.history):
            cells = ""
            for r in runs:
                for view in ("block", "line"):
                    m = ((snap.get("metrics") or {}).get(r.key) or {}).get(view)
                    cells += "<td class=\"n\">%s%s</td>" % (_num(m["auc"], 3) if m and m.get("auc") is not None else "-",
                                                             " <small class=\"sub\">전</small>" if m and m.get("stage") == "before" else "")
            tr, te = snap.get("train") or {}, snap.get("test") or {}
            same = i > 0 and snap.get("sentences") == res.history[i - 1].get("sentences")
            body.append("<tr><td>%s%s</td><td class=\"n\">%s / %s</td><td class=\"n\">%s / %s</td><td>%s</td><td class=\"n\">%g</td>%s</tr>" % (
                esc(snap.get("made", "")), " <b>(지금)</b>" if i == len(res.history) - 1 else "", tr.get("line_yes", "-"), tr.get("line_no", "-"),
                te.get("line_yes", "-"), te.get("line_no", "-"), "처음" if i == 0 else ("같음" if same else "바뀜"), snap.get("title_weight", 0), cells))
        p.append("<details class=\"box\" style=\"max-width:none\"%s><summary>기록: 학습 상태가 바뀔 때마다 시험 문서로 잰 순위 정확도 (%d번)</summary>"
                 "<p class=\"legend\">학습용 정답, 기준 문장, 쪽 제목 비율, 시험용 문서 가운데 하나라도 달라진 채로 계산하면 한 줄이 쌓입니다. "
                 "학습용 정답이 늘수록 숫자가 올라가는지 보세요. <small class=\"sub\">전</small>은 그때 분류기가 없어 학습 전 점수로 잰 것입니다. "
                 "시험 정답 수가 줄마다 다르면 그때그때의 정답으로 잰 것이라 서로 정확히 맞지는 않습니다(정확한 비교는 위의 '지난번 → 이번').</p>"
                 "<div class=\"wrap\"><table class=\"sum num\"><tr><th>계산한 때</th><th>학습에 쓴 정답<br>(서로 다른 줄: 예 / 아니오)</th><th>시험 정답<br>(줄: 예 / 아니오)</th>"
                 "<th>기준 문장</th><th>제목 비율</th>%s</tr>%s</table></div></details>" % (" open" if len(res.history) > 1 else "", len(res.history), head, "".join(body)))
    return "".join(p)


def write_index(res: Result, path: Path, doc_files: dict, root: Path, up: str = "../", note: str = "") -> None:
    """up: 이 화면이 놓이는 폴더에서 추출 결과 폴더(out)까지 올라가는 길.  note: 맨 위에 넣을 안내(학습 기록)"""
    c = res.counts()
    runs = [r for r in res.runs if r.ok]
    has_labels = (c["line_yes"] + c["line_no"]) > 0
    trained = any(r.after["block"] is not None or r.after["line"] is not None for r in runs)
    target = "%.0f%%" % (100 * res.target)
    p = ["<style>%s</style>" % CSS, note]

    # 지금 상태와 다음에 할 일
    p.append("<div class=\"box\"><p><b>문서 %d개 · 덩어리 %d개 · 줄 %d개</b> · 정답: 줄 기준 예 %d개, 아니오 %d개 (덩어리로 따지면 예 %d개, 아니오 %d개)</p>" % (
        c["docs"], c["blocks"], c["lines"], c["line_yes"], c["line_no"], c["block_yes"], c["block_no"]))
    if not has_labels:
        p.append("<p>아직 정답이 없어 <b>학습 전</b>(기준 문장만으로 매긴) 점수만 있습니다. 정확도 수치와 학습 후 결과를 보려면 아래 순서로 하세요.</p>")
    elif not trained:
        p.append("<p>정답이 있지만 분류기를 학습시키기에는 부족합니다(예와 아니오가 각각 4개 이상 필요). 정답을 더 붙인 뒤 다시 실행하세요.</p>")
    else:
        p.append("<p>정답으로 분류기를 학습시켰습니다. 아래 표에서 <b>학습 전과 학습 후</b>를 비교할 수 있습니다.</p>")
    if has_labels:
        p.append(_headline(res, runs))
    if res.test_names:
        tc = res.label_counts("test")
        p.append("<p><b>시험용 문서 %d개</b> (정답: 줄 기준 예 %d개, 아니오 %d개)는 학습에 쓰지 않고 채점에만 씁니다. 아래 '시험 문서로 잰 결과'를 먼저 보세요.</p>" % (
            len(res.test_names), tc["line_yes"], tc["line_no"]))
    if res.title_weight:
        p.append("<p><b>쪽 제목 반영: 켜짐</b> (비율 %g = 글 %.0f%%, 제목 %.0f%%). 이 화면의 점수와 수치는 제목을 반영한 값입니다. "
                 "반영 전과의 차이는 아래 '쪽 제목을 반영한 효과'에 있습니다.</p>" % (
                     res.title_weight, 100 * (1 - res.title_weight), 100 * res.title_weight))
    else:
        p.append("<p class=\"sub\">쪽 제목 반영: 꺼짐. 켜려면 <code>label.bat</code> 화면의 '쪽 제목 반영'에서 비율을 정하거나 "
                 "<code>screen_options.txt</code>의 <code>title_weight</code>를 고칩니다.</p>")
    p.append("<ol class=\"steps\"><li><code>label.bat</code>을 실행해 줄마다 예/아니오를 붙입니다(누를 때마다 저장됩니다).</li>"
             "<li>그 화면에서 <b>학습하고 결과 보기</b>를 누르면(또는 <code>screen.bat</code>을 다시 실행하면) 그 정답으로 분류기를 학습시키고 이 화면을 새로 만듭니다.</li>"
             "<li>기준 문장은 <code>label.bat</code> 화면의 '기준 문장 보기·고치기'에서 고치거나, <code>%s</code>를 메모장으로 고칩니다. "
             "고친 뒤 다시 계산하면 고치기 전과 비교한 수치가 아래에 나옵니다.</li></ol></div>" % esc(res.sentences_file.name))

    # 기준 문장
    p.append("<h2>기준 문장 (학습 전 판단에 쓰는 문장)</h2>")
    p.append("<p class=\"legend\">파일: <code>%s</code> · 글마다 이 문장들 가운데 어느 문장에 가장 가까운지를 따져, <span class=\"plus\">+</span> 문장 쪽으로 기운 정도를 0~1 점수로 냅니다. "
             "%s"
             "오른쪽 숫자는 그 문장에 가장 가까웠던 덩어리의 수입니다(한 번도 뽑히지 않는 문장은 하는 일이 없는 문장입니다).</p>" % (
                 esc(str(res.sentences_file)),
                 "임베딩 모델은 글과 문장의 비슷한 정도로, 문장 판별 모델은 그 문장이 글에 대해 맞을 가능성으로 따집니다. "
                 if any(r.spec["kind"] == "nli" for r in runs) else "글과 문장을 각각 숫자 묶음으로 바꿔 비슷한 정도로 따집니다. "))
    p.append("<div class=\"wrap\"><table class=\"sum\"><tr><th>이름</th><th>뜻</th><th>문장</th>%s</tr>" % "".join(
        "<th>%s</th>" % esc(r.spec["label"]) for r in runs))
    blocks = res.blocks
    for i, s in enumerate(res.sentences):
        cells = "".join("<td class=\"n\">%d</td>" % sum(1 for b in blocks if r.best["block"].get(b.key) == i) for r in runs)
        p.append("<tr><td class=\"%s\">%s</td><td>%s</td><td>%s</td>%s</tr>" % (
            "plus" if s.positive else "minus", esc(s.name), "검토 필요" if s.positive else "검토 불필요", esc(s.text), cells))
    p.append("</table></div>")

    # 모델
    p.append("<h2>모델</h2><div class=\"wrap\"><table class=\"sum\"><tr><th>모델</th><th>종류</th><th>설명</th><th>이번 실행</th><th>학습</th></tr>")
    for r in res.runs:
        if not r.ok:
            p.append("<tr><td>%s</td><td colspan=\"4\" class=\"err\">실행하지 못했습니다: %s</td></tr>" % (esc(r.spec["label"]), esc(r.error)))
            continue
        ran = ("새로 계산 %d%s · 1%s에 %.2f초" % (r.new_items, r.count_word, r.count_word, r.seconds / r.new_items)) if r.new_items else "지난 계산 결과를 다시 씀"
        if r.spec["kind"] == "nli":
            learned = "학습시키지 않음 (기준 문장만 씀)"
        else:
            learned = " / ".join("%s: %s" % (name, "학습함" if r.after[u] is not None else esc(r.train_note[u] or "정답 없음"))
                                 for u, name in (("block", "덩어리"), ("line", "줄")))
        p.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            esc(r.spec["label"]), "임베딩 + 분류기" if r.spec["kind"] == "embed" else "문장 판별", esc(r.spec["note"]), ran, learned))
    p.append("</table></div>")

    # 학습 전·후 수치
    p.append(_test_section(res, runs, target))
    p.append("<h2>학습 전과 학습 후 비교</h2>")
    if res.test_names:
        p.append("<p class=\"legend\">시험용 문서가 지정돼 있어, 여기부터 아래의 수치는 <b>시험용이 아닌 문서</b>로만 잰 것입니다(그 글을 빼고 학습시킨 분류기로 채점). "
                 "시험용 문서로 잰 결과는 바로 위에 있습니다.</p>")
    if not has_labels:
        p.append("<p class=\"legend\">정답을 붙이면 나옵니다.</p>")
    else:
        p.append("<p class=\"legend\"><b>순위 정확도</b>: 정답이 '예'인 것을 '아니오'인 것보다 높은 점수로 줄 세운 정도(1이면 완벽, 0.5면 무작위). 문턱값과 상관없는 수치라 모델끼리 비교하기 좋습니다. "
                 "<b>찾아낸 비율</b>: 정답이 '예'인 것 가운데 통과한 비율. <b>통과 비율</b>: 전체 항목 가운데 다음 단계로 넘어가는 비율(같은 만큼 찾아낸다면 낮을수록 잘 걸러 낸 것). "
                 "<b>%s 찾는 문턱에서의 통과 비율</b>: '예'의 %s 이상을 놓치지 않도록 문턱값을 낮췄을 때 통과하는 비율입니다. "
                 "학습 후 수치는 그 글을 빼고 학습시킨 분류기로 매긴 점수로 잰 것입니다(교차 검증). 굵은 초록은 그 보는 방식에서 순위 정확도가 가장 높은 칸입니다. "
                 "정답 수가 적으면 수치가 크게 흔들리니 '정답 수'를 함께 보세요.</p>" % (target, target))
        p.append("<p class=\"legend\"><b>개선 정도</b>는 같은 항목에 매긴 학습 전 점수와 학습 후 점수를 짝지어 잰 것입니다. "
                 "<b>순위 정확도 변화</b>의 괄호는 정답 표본을 다시 뽑아 1,000번 되풀이했을 때 차이가 놓이는 범위(95%%)입니다. "
                 "범위 전체가 0보다 크면 <span style=\"color:var(--tt-ink);font-weight:700\">나아짐</span>, 0을 걸치면 정답 수가 적어 "
                 "<span class=\"sub\">우연일 수 있음</span>으로 적습니다(정답을 더 붙이면 범위가 좁아집니다). <b>통과 비율 변화</b>는 '예'의 %s를 찾도록 문턱을 맞췄을 때 "
                 "다음 단계로 넘기는 양이 얼마나 줄었는지입니다(%%p는 퍼센트 값의 차이).</p>" % target)
        p.append(_glance(runs))
        p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th rowspan=\"2\">보는 방식</th><th rowspan=\"2\">모델</th><th rowspan=\"2\">정답 수<br>(예/아니오)</th>"
                 "<th colspan=\"4\" class=\"grp\">학습 전 (기준 문장만)</th><th colspan=\"4\" class=\"grp\">학습 후 (정답으로 학습)</th>"
                 "<th colspan=\"2\" class=\"grp\">개선 정도 (학습 후 − 학습 전)</th></tr>"
                 "<tr>%s<th>순위 정확도 변화</th><th>%s 찾는 문턱<br>통과 비율 변화</th></tr>" % (
                     "<th>순위 정확도</th><th>0.5 문턱<br>찾아낸 비율</th><th>0.5 문턱<br>통과 비율</th><th>%s 찾는 문턱<br>통과 비율</th>" % target * 2, target))
        for view, view_name in VIEWS:
            aucs = [m["auc"] for r in runs for m in (r.metrics.get(view, {}).get("before"), r.metrics.get(view, {}).get("after"))
                    if m is not None and m["auc"] is not None]
            best = max(aucs) if aucs else None
            for k, r in enumerate(runs):
                mb, ma = r.metrics.get(view, {}).get("before"), r.metrics.get(view, {}).get("after")
                n = "%d / %d" % (mb["yes"], mb["no"]) if mb else "-"
                first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
                p.append("<tr>%s<td>%s</td><td class=\"n\">%s</td>%s%s%s</tr>" % (
                    first, esc(r.spec["label"]), n, _metric_cells(mb, best, res.target),
                    _metric_cells(ma, best, res.target).replace("<td class=\"n", "<td class=\"g n"),
                    _gain_cells(r.metrics.get(view, {}).get("gain"))))
        p.append("</table></div>")
        p.append("<p class=\"legend\"><b>덩어리로 넣음</b>과 <b>줄로 넣어 덩어리로 합침</b>은 둘 다 덩어리 단위로 맞았는지를 재므로 서로 바로 비교할 수 있습니다"
                 "(어느 크기로 넣는 것이 나은지는 이 두 줄을 보세요). <b>줄로 넣음</b>은 줄 단위로 맞았는지를 잰 것입니다.</p>")

    # 분류기 종류 비교
    if has_labels:
        p.append(_classifier_section(res, runs, target))

    # 기준 문장을 고친 효과
    if res.previous:
        p.append("<h2>기준 문장을 고친 효과 (고치기 전 → 지금)</h2>")
        p.append("<p class=\"legend\">기준 문장을 고치기 전의 문장으로 매긴 점수와 지금 문장으로 매긴 점수를, <b>같은 항목·같은 정답</b>으로 짝지어 비교했습니다"
                 "(둘 다 학습 전의 글 점수. 쪽 제목 반영은 넣지 않고 잽니다). 읽는 법은 위 표의 개선 정도와 같습니다. 문장을 다시 고칠 때까지 이 비교가 유지됩니다.</p>")
        p.append("<details class=\"box\"><summary>고치기 전의 기준 문장 보기%s</summary><div class=\"wrap\"><table class=\"sum\">%s</table></div></details>" % (
            " (%s 실행)" % esc(res.previous.get("saved", "")) if res.previous.get("saved") else "",
            "".join("<tr><td class=\"%s\">%s</td><td>%s</td></tr>" % (
                "plus" if s.get("positive") else "minus", esc(s.get("name", "")), esc(s.get("text", ""))) for s in res.previous.get("sentences", []))))
        if not has_labels:
            p.append("<p class=\"legend\">정답을 붙이면 수치가 나옵니다.</p>")
        else:
            p.append("<div class=\"wrap\"><table class=\"sum num\"><tr><th>보는 방식</th><th>모델</th><th>순위 정확도<br>고치기 전</th><th>순위 정확도<br>지금</th>"
                     "<th>순위 정확도 변화</th><th>%s 찾는 문턱<br>통과 비율 변화</th></tr>" % target)
            for view, view_name in VIEWS:
                for k, r in enumerate(runs):
                    g = r.metrics.get(view, {}).get("edit")
                    first = "<td rowspan=\"%d\"><b>%s</b></td>" % (len(runs), esc(view_name)) if k == 0 else ""
                    p.append("<tr>%s<td>%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td>%s</tr>" % (
                        first, esc(r.spec["label"]), _num(g["auc_before"], 3) if g else "-", _num(g["auc_after"], 3) if g else "-", _gain_cells(g)))
            p.append("</table></div>")

    # 쪽 제목을 반영한 효과
    if res.title_weight:
        p.append(_title_section(res, runs, has_labels, target))

    # 덩어리 대 줄
    p.append("<h2>덩어리로 넣을 때와 줄로 넣을 때</h2>")
    p.append("<p class=\"legend\">같은 덩어리를 통째로 넣어 매긴 점수와, 줄마다 넣어 매긴 점수 가운데 가장 높은 값을 비교했습니다. 문턱 0.5로 판단이 갈린 덩어리 수입니다. "
             "어떤 덩어리인지는 문서별 화면에서 '덩어리로 넣을 때와 줄로 넣을 때 판단이 다른 것'을 체크하면 볼 수 있습니다.</p>")
    p.append("<div class=\"wrap\"><table class=\"sum\"><tr><th>모델</th><th>기준</th><th>둘 다 통과</th><th>덩어리로만 통과</th><th>줄로만 통과</th><th>둘 다 통과 못 함</th></tr>")
    for r in runs:
        for when, name in (("before", "학습 전"), ("after", "학습 후")):
            if when == "after" and (r.after["block"] is None or r.after["line"] is None):
                continue
            cnt = [0, 0, 0, 0]
            for b in blocks:
                x, y = r.block_score(b, when), r.agg(b, when)
                if x is None or y is None:
                    continue
                cnt[(0 if x >= 0.5 else 2) + (0 if y >= 0.5 else 1)] += 1
            p.append("<tr><td>%s</td><td>%s</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d</td></tr>" % (
                esc(r.spec["label"]), name, cnt[0], cnt[1], cnt[2], cnt[3]))
    p.append("</table></div>")

    # 문서 목록
    p.append("<h2>문서별 화면</h2><div class=\"wrap\"><table class=\"sum\"><tr><th>문서</th><th>덩어리</th><th>줄</th><th>정답 붙은 줄</th>%s<th>추출 리포트</th></tr>" % "".join(
        "<th>%s<br>0.5 이상 덩어리</th>" % esc(r.spec["label"]) for r in runs))
    for d in res.docs:
        lines = d.lines
        cells = "".join("<td class=\"n\">%d</td>" % sum(1 for b in d.blocks if (r.block_score(b) or 0) >= 0.5) for r in runs)
        p.append("<tr><td><a href=\"%s\">%s</a>%s</td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d</td>%s<td><a href=\"%s\">열기</a></td></tr>" % (
            esc(doc_files[d.name]), esc(d.name), " <span class=\"tag2\" style=\"background:#7a3fb0\">시험용</span>" if d.name in res.test_names else "",
            len(d.blocks), len(lines), sum(1 for l in lines if l.key in res.labels), cells, up + esc(d.report_file)))
    p.append("</table></div>")
    p.append("<p class=\"legend\">항목마다의 점수는 <code>out/screen/scores.json</code>에, 학습시킨 분류기는 <code>%s</code> 폴더에 들어 있습니다. "
             "모델에는 글을 최대 %d토큰까지만 넣습니다(넘는 부분은 잘림).</p>" % (esc(str(res.labels_file.parent / "classifiers")), res.max_len))
    sub = "추출한 덩어리·줄 가운데 특허출원 검토가 필요한 것을 걸러 내는 모델 비교 · <a href=\"%sindex.html\">추출 결과 첫 화면</a>" % up
    Path(path).write_text(_shell("1차 걸러내기 비교", sub, "", "".join(p)), encoding="utf-8")


def write_all(res: Result, root: Path, dest: Optional[Path] = None, up: str = "../", note: str = "") -> Path:
    """비교 화면을 만든다. dest: 놓을 폴더(없으면 out/screen).  up: 그 폴더에서 out까지 올라가는 길.  note: 첫 화면 맨 위의 안내"""
    out = Path(dest) if dest else res.out_dir / "screen"
    out.mkdir(parents=True, exist_ok=True)
    doc_files = {d.name: d.units_file[:-len(".units.json")] + ".screen.html" for d in res.docs}
    for d in res.docs:
        write_doc(res, d, out / doc_files[d.name], up)
    write_index(res, out / "index.html", doc_files, root, up, note)
    return out / "index.html"


# ---------------------------------------------------------------- 학습 기록

def _basis(entry: dict) -> str:
    """그 기록에서 볼 수치: 시험 문서로 잰 것이 있으면 그것(test), 없으면 교차 검증(cv)."""
    for m in (entry.get("metrics") or {}).values():
        for view, _ in VIEWS:
            if (m.get(view) or {}).get("test"):
                return "test"
    return "cv"


def _value(entry: dict, model: str, view: str, basis: str) -> Optional[dict]:
    return (((entry.get("metrics") or {}).get(model) or {}).get(view) or {}).get(basis)


def _trend_svg(entries: List[dict], model: str, basis: str) -> str:
    """기록마다의 순위 정확도를 이은 꺾은선. 파랑은 덩어리로 넣음, 주황은 줄로 넣음. 세로 눈금은 0.5~1.0"""
    w, h, left, right, top, bottom = 360, 150, 34, 96, 10, 22
    xs = lambda i: left + (0 if len(entries) == 1 else (w - left - right) * i / float(len(entries) - 1))
    ys = lambda v: top + (h - top - bottom) * (1.0 - max(0.0, min(1.0, (v - 0.5) / 0.5)))
    parts = ["<svg width=\"%d\" height=\"%d\" viewBox=\"0 0 %d %d\" role=\"img\">" % (w, h, w, h)]
    for v in (0.5, 0.75, 1.0):
        parts.append("<line class=\"grid\" x1=\"%d\" x2=\"%d\" y1=\"%.1f\" y2=\"%.1f\"/><text x=\"%d\" y=\"%.1f\" text-anchor=\"end\">%s</text>" % (
            left, w - right, ys(v), ys(v), left - 5, ys(v) + 4, ("%.2f" % v).rstrip("0").rstrip(".") if v != 0.5 else "0.5"))
    step = max(1, len(entries) // 8)
    for i, e in enumerate(entries):
        if i % step == 0 or i == len(entries) - 1:
            parts.append("<text x=\"%.1f\" y=\"%d\" text-anchor=\"middle\">#%d</text>" % (xs(i), h - 6, e["n"]))
    ends = []
    for cls, view, name in (("1", "block", "덩어리"), ("2", "line", "줄")):
        pts = [(xs(i), ys(v["auc"]), e["n"], v) for i, e in enumerate(entries) for v in [_value(e, model, view, basis)] if v]
        if len(pts) > 1:
            parts.append("<polyline class=\"l%s\" points=\"%s\"/>" % (cls, " ".join("%.1f,%.1f" % (x, y) for x, y, _, _ in pts)))
        for x, y, n, v in pts:
            parts.append("<circle class=\"p%s\" cx=\"%.1f\" cy=\"%.1f\" r=\"4\"><title>기록 #%d · %s로 넣음 · 순위 정확도 %.3f%s</title></circle>" % (
                cls, x, y, n, name, v["auc"], " (학습 전 점수)" if v.get("stage") == "before" else ""))
        if pts:
            ends.append([pts[-1][1], "%s %.3f" % (name, pts[-1][3]["auc"]), pts[-1][0]])
    ends.sort()
    if len(ends) == 2 and ends[1][0] - ends[0][0] < 13:      # 끝 이름표가 겹치지 않게 벌린다
        mid = (ends[0][0] + ends[1][0]) / 2.0
        ends[0][0], ends[1][0] = mid - 6.5, mid + 6.5
    for y, text, x in ends:
        parts.append("<text class=\"lab\" x=\"%.1f\" y=\"%.1f\">%s</text>" % (x + 9, y + 4, esc(text)))
    return "".join(parts) + "</svg>"


def write_history(res: Result, entries: List[dict], path: Path, changed) -> None:
    """학습 기록 화면. entries: 오래된 것부터.  changed(앞 기록, 이 기록) → 달라진 것의 말 목록"""
    latest = entries[-1]
    basis = _basis(latest)
    models = [(k, m.get("label", k)) for k, m in (latest.get("metrics") or {}).items()]
    p = ["<style>%s</style>" % CSS]
    p.append("<div class=\"note\"><b>학습 기록 %d번</b> · 정답, 기준 문장, 쪽 제목 비율, 시험용 문서, 모델, 문서 가운데 하나라도 달라진 채로 계산하면 한 번씩 쌓입니다. "
             "아무것도 바꾸지 않고 다시 계산하면 마지막 기록을 고쳐 씁니다. 지난 기록의 화면은 지워지지 않고 그대로 남습니다 "
             "(<code>out/screen/history</code> 폴더. 자리를 많이 차지하면 오래된 번호의 폴더를 직접 지워도 됩니다).</div>" % len(entries))
    # 추이 그림
    shown = [e for e in entries if _basis(e) == basis][-30:]
    p.append("<h2>순위 정확도의 추이</h2>")
    p.append("<p class=\"legend viz\">%s <span class=\"key\"><i class=\"sw1\"></i>덩어리로 넣음</span><span class=\"key\"><i class=\"sw2\"></i>줄로 넣음</span> "
             "가로는 기록 번호, 세로는 순위 정확도(1이면 완벽, 0.5면 무작위)입니다. <b>선이 위로 올라가면 나아진 것</b>입니다. 점에 마우스를 올리면 값이 나옵니다.%s</p>" % (
                 "<b>시험 문서로 잰 값</b>입니다(학습에 쓰지 않은 문서라 기록끼리 그대로 견줄 수 있습니다)." if basis == "test" else
                 "<b>교차 검증으로 잰 값</b>입니다. 정답이 늘면 채점하는 글도 함께 달라지므로 기록끼리의 비교는 대략적인 것입니다. "
                 "정확히 견주려면 시험용 문서를 정해 두세요(<code>label.bat</code> 화면의 문서 목록).",
                 " 최근 30번만 그렸습니다." if len([e for e in entries if _basis(e) == basis]) > 30 else ""))
    p.append("<div class=\"viz\">%s</div>" % "".join(
        "<div class=\"trend\"><h4>%s</h4>%s</div>" % (esc(label), _trend_svg(shown, key, basis)) for key, label in models))

    # 목록 (새것부터)
    p.append("<h2>기록 목록 (새것부터)</h2>")
    p.append("<p class=\"legend\">숫자는 순위 정확도이고, 그 아래 작은 글씨는 바로 앞 기록과의 차이와 '예'의 %.0f%%를 찾는 문턱에서의 통과 비율입니다. "
             "<b>그때의 화면</b>을 누르면 그 학습 때의 비교 화면 전체(문서별 점수 포함)가 그대로 열립니다. "
             "'잰 방법'이 앞 기록과 다르면 차이를 적지 않았습니다.</p>" % (100 * res.target))
    head = "".join("<th>%s<br>덩어리로 넣음</th><th>%s<br>줄로 넣음</th>" % (esc(label), esc(label)) for _, label in models)
    p.append("<div class=\"wrap\"><table class=\"sum\"><tr><th>기록</th><th>학습한 때</th><th>앞 기록과 달라진 것</th><th>정답<br>(예 / 아니오)</th>"
             "<th>학습에 쓴 정답<br>(서로 다른 줄)</th><th>잰 방법</th>%s<th>그때의 화면</th></tr>" % head)
    for i in range(len(entries) - 1, -1, -1):
        e, prev = entries[i], entries[i - 1] if i else None
        b = _basis(e)
        cells = ""
        for key, _ in models:
            for view in ("block", "line"):
                v = _value(e, key, view, b)
                if not v:
                    cells += "<td class=\"n\">-</td>"
                    continue
                old = _value(prev, key, view, b) if prev is not None and _basis(prev) == b else None
                delta = ""
                if old:
                    d = v["auc"] - old["auc"]
                    delta = "<small class=\"%s\">%s%+.3f</small> · " % ("up" if d > 0.0005 else "down" if d < -0.0005 else "sub", "▲" if d > 0.0005 else "▼" if d < -0.0005 else "", d)
                cells += "<td class=\"n\"><b>%s</b>%s<br>%s<small class=\"sub\">통과 %s</small></td>" % (
                    _num(v["auc"], 3), " <small class=\"sub\">전</small>" if v.get("stage") == "before" else "", delta, _pct(v["pass"]))
        tr = e.get("trained") or {}
        p.append("<tr%s><td class=\"n\" style=\"white-space:nowrap\"><b>#%d</b>%s</td><td>%s</td><td>%s</td><td class=\"n\">%d / %d</td><td class=\"n\">%s / %s</td><td>%s</td>%s"
                 "<td><a href=\"history/%s/index.html\"><b>열기</b></a></td></tr>" % (
                     " class=\"now\"" if i == len(entries) - 1 else "", e["n"], " <small class=\"sub\">지금</small>" if i == len(entries) - 1 else "",
                     esc(e.get("made", "")), "<br>".join(esc(x) for x in changed(prev, e)), e["labels"]["yes"], e["labels"]["no"],
                     tr.get("line_yes", "-"), tr.get("line_no", "-"), "시험 문서" if b == "test" else "교차 검증", cells, esc(e["dir"])))
    p.append("</table></div>")
    p.append("<p class=\"legend\"><small class=\"sub\">전</small>은 그때 분류기가 없어 학습 전 점수로 잰 것입니다. "
             "시험용 문서가 있을 때 같은 시험 글로 지난번과 이번을 정확히 견준 수치(범위 포함)와 판단이 바뀐 글 목록은 각 기록 화면의 '시험 문서로 잰 결과'에 있습니다.</p>")
    sub = "학습할 때마다의 결과를 모아 둔 곳 · <a href=\"index.html\">지금의 비교 화면</a> · <a href=\"../index.html\">추출 결과 첫 화면</a>"
    Path(path).write_text(_shell("학습 기록", sub, "", "".join(p)), encoding="utf-8")
