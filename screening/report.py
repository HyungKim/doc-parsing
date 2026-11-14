"""걸러내기 비교 리포트(HTML). 인터넷 없이 브라우저로 바로 열린다.

    out/screen/index.html      기준 문장, 모델, 학습 전·후 수치, 덩어리 대 줄 비교, 문서 목록
    out/screen/이름.html       문서마다: 덩어리와 그 줄마다 모델 네 가지의 점수(학습 전 → 후)
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from docparse.report import _shell, esc

from .items import BlockItem, DocItems
from .run import VIEWS, ModelRun, Result

CSS = """
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0;max-width:1100px}
.box p{margin:4px 0}
h2{font-size:16px;margin:26px 0 6px}
h3.pg{font-size:14px;margin:18px 0 6px;color:var(--mute)}
code{background:var(--card);border:1px solid var(--line);border-radius:4px;padding:0 4px;font:12px ui-monospace,Consolas,monospace}
table.sum td.best{font-weight:700;color:var(--tt-ink)}
table.sum td.g{background:rgba(31,95,191,.06)}
table.sum td.up{color:var(--tt-ink);font-weight:700}
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
.viz{--s1:#2a78d6}
@media (prefers-color-scheme:dark){.viz{--s1:#3987e5}}
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
    flags = {
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
    def tip(r: ModelRun, unit: str, key: str) -> str:
        out = ("가장 가까운 기준 문장: " + names[r.best[unit][key]]) if key in r.best[unit] else ""
        if r.title_w:                              # 제목을 섞기 전의 글 점수와 제목 점수도 알려 준다
            s, t = r.score(unit, key), r.title_score(b.title)
            if s is not None and t is not None:
                out += " | 글 점수 %.2f, 제목 점수 %.2f → 섞은 점수 %.2f" % (s, t, (1 - r.title_w) * s + r.title_w * t)
        return out

    rows.append("<tr class=\"whole\"><td class=\"t\">덩어리로 넣음 (아래 줄을 모두 합친 글 하나)</td>%s</tr>" % "".join(
        _cell(v, a, tip(r, "block", b.key)) for r, (v, a) in zip(runs, whole)))
    if len(b.lines) > 1:
        rows.append("<tr class=\"whole sumrow\"><td class=\"t\">줄로 넣어 합침 (아래 줄 점수 가운데 가장 높은 값)</td>%s</tr>" % "".join(
            _cell(v, a) for v, a in merged))
    for l in b.lines:
        rows.append("<tr><td class=\"t\">%s %s</td>%s</tr>" % (
            _label(res.labels.get(l.key)), esc(l.text), "".join(
                _cell(r.line_score(b, l, "before"), r.line_score(b, l, "after"), tip(r, "line", l.key)) for r in runs)))
    return "<div class=\"blk\" data-label=\"%s\" data-split=\"%s\" data-unit=\"%s\" data-miss=\"%s\" data-wrong=\"%s\" data-title=\"%s\">%s<table class=\"sc\">%s</table></div>" % (
        "n" if label is None else str(label), flags["split"], flags["unit"], flags["miss"], flags["wrong"], flags["title"], head, "".join(rows))


def _title_line(runs: List[ModelRun], title: str) -> str:
    parts = []
    for r in runs:
        t = r.title_score(title)
        if t is not None:
            parts.append("%s <b>%s</b>" % (esc(r.spec["label"]), _num(t)))
    return "<div class=\"sub\" style=\"margin:-2px 0 6px\">제목 점수: %s</div>" % " · ".join(parts) if parts else ""


def write_doc(res: Result, doc: DocItems, path: Path) -> None:
    runs = [r for r in res.runs if r.ok]
    parts = ["<style>%s</style>" % CSS]
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
           "%s<span id=\"f-count\" class=\"sub\"></span></div>" % (
               "<label><input type=\"checkbox\" data-f=\"title\"> 제목 반영으로 판단이 바뀐 것</label>" if res.title_weight else ""))
    page = None
    for b in doc.blocks:
        if b.page != page:
            if page is not None:
                parts.append("</section>")
            page = b.page
            parts.append("<section class=\"pgs\"><h3 class=\"pg\">%d쪽%s · <a href=\"../%s#p%d\">추출 리포트에서 보기</a></h3>" % (
                page, " · 제목: " + esc(b.title) if b.title else "", esc(doc.report_file), page))
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


def _gain_cells(g: Optional[dict]) -> str:
    """개선 정도 칸 둘: 순위 정확도 변화(범위 포함), 같은 만큼 찾을 때의 통과 비율 변화."""
    if g is None:
        return "<td class=\"n\">-</td><td class=\"n\">-</td>"
    word = _gain_word(g)
    cls = "up" if g["sure"] else "down" if g["worse"] else "flat"
    first = "<td class=\"n %s\">%+.3f <small class=\"sub\">(%+.3f ~ %+.3f) %s</small></td>" % (
        cls, g["auc_gain"], g["auc_low"], g["auc_high"], word)
    pg = g["pass_gain"]
    cls2 = "up" if pg < -0.005 else "down" if pg > 0.005 else "flat"
    second = "<td class=\"n %s\">%s → %s <small class=\"sub\">(%s)</small></td>" % (
        cls2, _pct(g["pass_before"]), _pct(g["pass_after"]), "%+.0f%%p" % (100 * pg) if abs(pg) >= 0.005 else "같음")
    return first + second


def _headline(res: Result, runs: List[ModelRun]) -> str:
    """정답으로 잰 결과 가운데 가장 좋은 조합 한 줄."""
    best = None
    for r in runs:
        for view, name in VIEWS[:2]:               # 덩어리 단위로 잰 두 방식끼리만 견준다
            for when, wname in (("before", "학습 전"), ("after", "학습 후")):
                m = r.metrics.get(view, {}).get(when)
                if m is not None and m["auc"] is not None and (best is None or m["auc"] > best[0]):
                    best = (m["auc"], r.spec["label"], name, wname, m)
    if best is None:
        return ""
    return ("<p><b>지금까지 가장 좋은 조합</b>: %s · %s · %s (순위 정확도 %s, '예'의 %.0f%%를 찾는 문턱에서 통과 비율 %s)</p>" % (
        esc(best[1]), esc(best[2]), best[3], _num(best[0], 3), 100 * res.target, _pct(best[4]["tuned"]["pass"])))


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


def write_index(res: Result, path: Path, doc_files: dict, root: Path) -> None:
    c = res.counts()
    runs = [r for r in res.runs if r.ok]
    has_labels = (c["line_yes"] + c["line_no"]) > 0
    trained = any(r.after["block"] is not None or r.after["line"] is not None for r in runs)
    target = "%.0f%%" % (100 * res.target)
    p = ["<style>%s</style>" % CSS]

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
             "임베딩 모델은 글과 문장의 비슷한 정도로, 문장 판별 모델은 그 문장이 글에 대해 맞을 가능성으로 따집니다. "
             "오른쪽 숫자는 그 문장에 가장 가까웠던 덩어리의 수입니다(한 번도 뽑히지 않는 문장은 하는 일이 없는 문장입니다).</p>" % esc(str(res.sentences_file)))
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
    p.append("<h2>학습 전과 학습 후 비교</h2>")
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
        p.append("<tr><td><a href=\"%s\">%s</a></td><td class=\"n\">%d</td><td class=\"n\">%d</td><td class=\"n\">%d</td>%s<td><a href=\"../%s\">열기</a></td></tr>" % (
            esc(doc_files[d.name]), esc(d.name), len(d.blocks), len(lines), sum(1 for l in lines if l.key in res.labels), cells, esc(d.report_file)))
    p.append("</table></div>")
    p.append("<p class=\"legend\">항목마다의 점수는 <code>out/screen/scores.json</code>에, 학습시킨 분류기는 <code>%s</code> 폴더에 들어 있습니다. "
             "모델에는 글을 최대 %d토큰까지만 넣습니다(넘는 부분은 잘림).</p>" % (esc(str(res.labels_file.parent / "classifiers")), res.max_len))
    sub = "추출한 덩어리·줄 가운데 특허출원 검토가 필요한 것을 걸러 내는 모델 비교 · <a href=\"../index.html\">추출 결과 첫 화면</a>"
    Path(path).write_text(_shell("1차 걸러내기 비교", sub, "", "".join(p)), encoding="utf-8")


def write_all(res: Result, root: Path) -> Path:
    out = res.out_dir / "screen"
    out.mkdir(parents=True, exist_ok=True)
    doc_files = {d.name: d.units_file[:-len(".units.json")] + ".screen.html" for d in res.docs}
    for d in res.docs:
        write_doc(res, d, out / doc_files[d.name])
    write_index(res, out / "index.html", doc_files, root)
    return out / "index.html"
