"""LLM 검증 비교 화면(HTML). 인터넷 없이 브라우저로 바로 열린다.

    out/verify/index.html              가장 최근 결과
    out/verify/runs/때/index.html      돌릴 때마다의 결과(지우지 않는다)
    out/verify/runs.json               지난 실행 목록
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from docparse.report import _shell, esc
from screening.report import CSS as SCREEN_CSS

from . import core, ollama, prompts

KEEP_RUNS = 60

CSS = """
.viz{--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a}
@media (prefers-color-scheme:dark){.viz{--s1:#3987e5;--s2:#d95926;--s3:#199e70}}
.c0{--c:var(--s1)}.c1{--c:var(--s2)}.c2{--c:var(--s3)}.c3{--c:var(--mute)}
table.cmp{border-collapse:collapse;background:var(--card);border:1px solid var(--line);margin:8px 0;font-size:13px}
table.cmp th,table.cmp td{padding:5px 10px;text-align:left;vertical-align:middle;white-space:nowrap;border-top:1px solid var(--line)}
table.cmp th{color:var(--mute);font-weight:600;font-size:12px;border-top:0;vertical-align:bottom;white-space:normal;min-width:56px}
table.cmp td.n{text-align:right;font-variant-numeric:tabular-nums}
table.cmp tr.pick td{background:rgba(31,95,191,.07)}
table.cmp tr.pick td:first-child{box-shadow:inset 3px 0 0 var(--acc)}
table.cmp td.bad{color:var(--rm-ink);font-weight:700}
table.cmp td.good{color:var(--tt-ink);font-weight:700}
table.cmp td small{color:var(--mute)}
.split{position:relative;display:flex;gap:2px;width:260px;height:16px}
.split i{display:block;height:16px;border-radius:2px;min-width:2px}
.split .ky,.key .ky{background:var(--s1)}
.split .kn,.key .kn{background:var(--mute)}
.split .rn,.key .rn{background:transparent;border:1.5px solid var(--mute);opacity:.55}
.split .ly,.key .ly{background:transparent;border:2px solid var(--s1)}
.split .tick{position:absolute;top:-4px;bottom:-4px;width:0;border-left:2px dashed var(--ink);border-radius:0;min-width:0}
.key i{display:inline-block;width:16px;height:11px;border-radius:2px}
.key .tk{display:inline-block;width:0;height:15px;border-left:2px dashed var(--ink)}
.tbar{display:inline-block;height:8px;background:var(--s1);border-radius:0 4px 4px 0;vertical-align:middle;margin-right:6px}
svg.plot text{fill:var(--mute);font-size:11px}
svg.plot text.lab{fill:var(--ink);font-size:11.5px;font-weight:700}
svg.plot .grid{stroke:var(--line);stroke-width:1}
svg.plot .base{stroke:var(--ink);fill:none;stroke-width:2}
svg.plot .pt{fill:var(--c);stroke:var(--card);stroke-width:2}
svg.plot .now{fill:var(--card);stroke:var(--ink);stroke-width:2}
.key .mk{display:inline-block;width:11px;height:11px;background:var(--c)}
.key .mk.s0{border-radius:50%}.key .mk.s2{transform:rotate(45deg) scale(.8)}
.key .ln{display:inline-block;width:18px;height:2px;background:var(--ink)}
.ctl{display:flex;gap:8px 18px;flex-wrap:wrap;align-items:center;margin:8px 0}
.ctl select{font:inherit;padding:2px 6px}
table.it{border-collapse:collapse;width:100%;max-width:1500px;background:var(--card);border:1px solid var(--line);font-size:13px}
table.it th,table.it td{border-top:1px solid var(--line);padding:4px 8px;vertical-align:top;text-align:left}
table.it th{font-size:11px;color:var(--mute);font-weight:600;white-space:nowrap;position:sticky;top:0;background:var(--card)}
table.it td.tx{white-space:pre-wrap;word-break:break-word;min-width:260px;cursor:pointer}
table.it td.c{white-space:nowrap;text-align:center}
table.it td.w{color:var(--mute);white-space:nowrap;font-size:12px}
table.it tr.rej td{background:rgba(120,120,120,.07)}
.chip{display:inline-block;min-width:74px;padding:0 6px;border-radius:3px;font-size:12px;font-variant-numeric:tabular-nums;border:1.5px solid transparent}
.chip.y{background:var(--s1);color:#fff}
.chip.n{border-color:var(--line);color:var(--mute)}
.chip.q{border-style:dashed;border-color:var(--mute);color:var(--mute)}
.chip.miss{border-color:var(--rm-ink);color:var(--rm-ink);font-weight:700}
.why{margin:4px 0 0;padding:4px 8px;border-left:3px solid var(--line);color:var(--mute);font-size:12px;white-space:normal}
.why b{color:var(--ink)}
table.two{border-collapse:collapse;background:var(--card);border:1px solid var(--line);font-size:13px;margin:6px 0}
table.two th,table.two td{border:1px solid var(--line);padding:5px 12px;text-align:right;font-variant-numeric:tabular-nums}
table.two th{color:var(--mute);font-weight:600;text-align:left}
pre.pr{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px 12px;font:12.5px/1.55 ui-monospace,Consolas,"Malgun Gothic",monospace;margin:6px 0}
"""

JS = r"""
(function(){
var R=window.VERIFY;if(!R)return;
var $=function(id){return document.getElementById(id)};
var esc=function(s){return String(s).replace(/[&<>"]/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})};
var llms=[],seen={};R.combos.forEach(function(c){if(!seen[c.llm]){seen[c.llm]=1;llms.push(c.llm)}});
var S={llm:llms[0],base:null,filter:"all",shown:150,open:{}};
function combos(){return R.combos.filter(function(c){return c.llm===S.llm})}
function ans(c,i){var a=R.ans[c.id];return a?a[i]:null}
function fill(){
  $("v-llm").innerHTML=llms.map(function(n){return '<option'+(n===S.llm?' selected':'')+'>'+esc(n)+'</option>'}).join("");
  var cs=combos();if(!S.base||!cs.some(function(c){return c.id===S.base}))S.base=(cs.filter(function(c){return c.id===R.best})[0]||cs[0]).id;
  $("v-base").innerHTML=cs.map(function(c){return '<option value="'+esc(c.id)+'"'+(c.id===S.base?' selected':'')+'>'+esc(c.v+" "+c.name)+'</option>'}).join("");
}
function match(i){
  var it=R.items[i],b=R.ans[S.base]?R.ans[S.base][i]:null,f=S.filter;
  if(f==="all")return true;
  if(f==="split"){var vs={};combos().forEach(function(c){var a=ans(c,i);if(a&&a.v!==null)vs[a.v]=1});return Object.keys(vs).length>1}
  if(!b)return false;
  var keep=b.v!==0;
  if(f==="lost")return it.y===1&&!keep&&it.ps;
  if(f==="removed")return it.y===0&&!keep&&it.ps;
  if(f==="left")return it.y===0&&keep&&it.ps;
  if(f==="kept")return it.y===1&&keep&&it.ps;
  if(f==="rescue")return !it.ps&&keep;
  return true;
}
function chip(a,it){
  if(!a)return '<span class="chip q" title="아직 받지 않은 답">–</span>';
  var p=a.p===null?"":" "+a.p.toFixed(2),tip=(a.why?a.why+" · ":"")+a.sec.toFixed(1)+"초";
  if(a.v===null)return '<span class="chip q" title="'+esc("읽지 못한 답: "+(a.raw||""))+'">? '+p+'</span>';
  var cls=a.v===1?"y":"n";if(it.y===1&&a.v===0)cls="n miss";
  return '<span class="chip '+cls+'" title="'+esc(tip)+'">'+(a.v===1?"예":"아니오")+p+'</span>';
}
function two(){
  var b=R.ans[S.base]||[],c=[[0,0,0,0],[0,0,0,0]],any=[false,false];
  R.items.forEach(function(it,i){var a=b[i];if(!a)return;var r=it.ps?0:1,k=a.v!==0?0:2;any[r]=true;c[r][k]++;if(it.y===1)c[r][k+1]++});
  var row=function(name,r){return '<tr><th>'+name+'</th>'+(any[r]?'<td>'+c[r][0]+'개 <small>(정답 예 '+c[r][1]+')</small></td><td>'+c[r][2]+'개 <small>(정답 예 '+c[r][3]+')</small></td>':'<td colspan="2" style="text-align:left;color:var(--mute)">LLM에 넣지 않음</td>')+'</tr>'};
  $("v-two").innerHTML='<table class="two"><tr><th></th><th>LLM이 예 (남김)</th><th>LLM이 아니오 (덜어냄)</th></tr>'+row("분류기가 예 (통과)",0)+row("분류기가 아니오 (탈락)",1)+'</table>';
}
function draw(){
  fill();two();
  var cs=combos(),rows=[],n=0;
  for(var i=0;i<R.items.length;i++){if(!match(i))continue;n++;if(n>S.shown)continue;
    var it=R.items[i],h='<tr class="'+(it.ps?"":"rej")+'"><td class="w">'+esc(it.d)+'<br>'+it.p+'쪽</td><td class="tx" data-i="'+i+'">'+esc(it.t);
    if(S.open[i]){cs.forEach(function(c){var a=ans(c,i);if(a&&(a.why||a.v===null))h+='<div class="why"><b>'+esc(c.v+" "+c.name)+'</b> '+esc(a.why||("읽지 못한 답: "+(a.raw||"")))+'</div>'})}
    h+='</td><td class="c"><span class="lab '+(it.y===1?"y":"n")+'">'+(it.y===1?"예":"아니오")+'</span></td><td class="c">'+(it.ps?'<b>'+it.s.toFixed(2)+'</b>':it.s.toFixed(2))+'</td>';
    cs.forEach(function(c){h+='<td class="c">'+chip(ans(c,i),it)+'</td>'});
    rows.push(h+'</tr>');}
  $("v-count").textContent=n+"개";
  $("v-table").innerHTML='<table class="it"><tr><th>문서 · 쪽</th><th>글 (누르면 이유를 펼침)</th><th>정답</th><th>분류기 점수</th>'+cs.map(function(c){return '<th title="'+esc(c.name)+'">'+esc(c.v)+' '+esc(c.name)+'</th>'}).join("")+'</tr>'+rows.join("")+'</table>'+
    (n>S.shown?'<p><button id="v-more">더 보기 ('+(n-S.shown)+'개 남음)</button></p>':'')+(n?'':'<p class="legend">해당하는 글이 없습니다.</p>');
}
document.addEventListener("change",function(e){var t=e.target;
  if(t.id==="v-llm"){S.llm=t.value;S.base=null;S.shown=150;draw()}
  if(t.id==="v-base"){S.base=t.value;S.shown=150;draw()}
  if(t.id==="v-filter"){S.filter=t.value;S.shown=150;draw()}});
document.addEventListener("click",function(e){var t=e.target;
  if(t.id==="v-more"){S.shown+=300;draw();return}
  var td=t.closest?t.closest("td.tx"):null;if(td){var i=td.getAttribute("data-i");S.open[i]=!S.open[i];draw()}});
draw();
})();
"""


def _pct(v: Optional[float], digits: int = 0) -> str:
    return "-" if v is None else ("%." + str(digits) + "f%%") % (100.0 * v)


def _time(seconds: float) -> str:
    if seconds < 60:
        return "%.1f초" % seconds if seconds < 10 else "%d초" % round(seconds)
    if seconds < 3600:
        return "%d분 %d초" % (seconds // 60, seconds % 60) if seconds < 600 else "%d분" % round(seconds / 60.0)
    return "%d시간 %d분" % (seconds // 3600, seconds % 3600 // 60)


def _split(m: dict) -> str:
    """글 n개가 어떻게 갈렸는지 보여 주는 띠: 남긴 것(지킨 예, 남은 아니오) | 덜어낸 것(덜어낸 아니오, 잃은 예). 점선은 분류기 문턱만 올렸을 때 남는 양."""
    n = float(m["n"])
    seg = lambda cls, v, tip: "<i class=\"%s\" style=\"flex:%d 0 0\" title=\"%s %d개\"></i>" % (cls, v, tip, v) if v else ""
    tick = ""
    if m["base_kept"] is not None:
        tick = "<i class=\"tick\" style=\"left:%.1f%%\" title=\"분류기 문턱만 올려 '예'를 %d개 남기면 %d개가 남음\"></i>" % (
            100.0 * m["base_kept"] / n, m["kept_yes"], m["base_kept"])
    return "<div class=\"split\">%s%s%s%s%s</div>" % (
        seg("ky", m["kept_yes"], "남긴 것 가운데 정답 '예'"), seg("kn", m["kept_no"], "남긴 것 가운데 정답 '아니오'"),
        seg("rn", m["removed_no"], "덜어낸 정답 '아니오'"), seg("ly", m["lost_yes"], "잃은 정답 '예'"), tick)


def _gain_text(m: dict) -> str:
    g = m["gain"]
    if g is None:
        return "-"
    rng = "" if m["gain_lo"] is None else " <small>(%+.0f ~ %+.0f)</small>" % (m["gain_lo"], m["gain_hi"])
    return "%+d개%s" % (g, rng)


def _verdict(m: dict) -> tuple:
    """(한 줄 판정, 종류). 종류: good | maybe | bad | none"""
    g = m["gain"]
    if g is None:
        return "LLM이 '예'를 하나도 남기지 않아 견줄 수 없습니다", "none"
    if g > 0 and m["gain_lo"] is not None and m["gain_lo"] > 0:
        return "분류기 문턱만 올리는 것보다 나았습니다", "good"
    if g > 0:
        return "분류기 문턱만 올리는 것보다 나아 보이지만, 글 수가 적어 우연일 수 있습니다", "maybe"
    if g == 0:
        return "분류기 문턱만 올리는 것과 같았습니다", "bad"
    return "분류기 문턱만 올리는 것보다 못했습니다", "bad"


def _headline(res: dict) -> str:
    c, d, st = res["classifier"], res["data"], res["setup"]
    word = "줄" if c["unit"] == "line" else "덩어리"
    where = "시험용 문서 %d개" % d["docs"] if d["part"] == "test" else "정답이 붙은 문서 %d개(시험용 문서가 없어 모든 문서를 씀)" % d["docs"]
    p = ["<div class=\"note\"><b>한눈에 보기</b><ul class=\"steps\">"]
    p.append("<li><b>잰 글</b>: %s에서 정답이 붙은 %s %d개('예' %d개) → 분류기(%s, %s, 문턱 %.2f)가 %d개를 통과시킴('예' %d개) → 그 가운데 %s를 LLM에 넣음.</li>" % (
        where, word, d["labeled"], d["yes"], esc(c["label"]), esc(c["view_name"]), c["threshold"], d["passed"], d["passed_yes"],
        "전부(%d개)" % d["chosen_passed"] if d["chosen_passed"] >= d["passed"] else "표본 %d개" % d["chosen_passed"]))
    best = core.best_combo(res)
    if best is None:
        p.append("<li>끝까지 돈 조합이 아직 없습니다. 아래 표에서 진행 상황을 볼 수 있습니다.</li>")
    else:
        m = best["metrics"]
        text, kind = _verdict(m)
        p.append("<li><b>가장 많이 줄인 조합</b>: %s · %s %s — %d개 가운데 <b>%d개만 남김</b>(%s 줄임). '아니오' %d개 가운데 %d개를 덜어냈고, '예' %d개 가운데 <b>%d개를 잃음</b>.</li>" % (
            esc(best["llm"]), esc(best["variant"]), esc(best["name"]), m["n"], m["kept"], _pct(1 - m["kept"] / float(m["n"])),
            m["no"], m["removed_no"], m["yes"], m["lost_yes"]))
        if m["gain"] is not None:
            p.append("<li><b>LLM을 붙일 값어치</b>: '예'를 똑같이 %d개 남기도록 분류기 문턱만 올리면 %d개가 남습니다. LLM은 %d개를 남겼으니 <b>%s</b> → %s.</li>" % (
                m["kept_yes"], m["base_kept"], m["kept"],
                "%d개 더 줄였습니다" % m["gain"] if m["gain"] > 0 else ("같습니다" if m["gain"] == 0 else "%d개 덜 줄였습니다" % -m["gain"]), esc(text)))
        else:
            p.append("<li><b>LLM을 붙일 값어치</b>: %s.</li>" % esc(text))
        p.append("<li><b>시간</b>: 글 하나에 %s. 문서 하나에 통과하는 글이 평균 %.0f개이므로 문서 하나에 약 %s.</li>" % (
            _time(m["sec_mean"]), d["passed_per_doc"], _time(m["sec_mean"] * d["passed_per_doc"])))
        done = [x for x in res["combos"] if x["metrics"] and x["done"] == x["total"]]
        safe = min(done, key=lambda x: (x["metrics"]["lost_yes"], -x["metrics"]["removed_no"], x["metrics"]["sec_mean"]))
        if safe["id"] != best["id"] and safe["metrics"]["lost_yes"] < m["lost_yes"]:
            s = safe["metrics"]
            p.append("<li><b>'예'를 가장 덜 잃은 조합</b>: %s · %s %s — %d개 가운데 %d개 남김, '예' %d개 가운데 %d개를 잃음, 분류기 문턱만 올린 것보다 %s. "
                     "놓치지 않는 것이 더 중요하면 이쪽을 보세요.</li>" % (
                         esc(safe["llm"]), esc(safe["variant"]), esc(safe["name"]), s["n"], s["kept"], s["yes"], s["lost_yes"],
                         "-" if s["gain"] is None else ("%d개 더 줄임" % s["gain"] if s["gain"] > 0 else ("같음" if s["gain"] == 0 else "%d개 덜 줄임" % -s["gain"]))))
    p.append("</ul><p class=\"legend\"><b>고른 방법</b>: 끝까지 돈 조합 가운데 '분류기 문턱만 올린 것보다 더 줄인 수'가 가장 큰 조합을 골랐습니다(같으면 빠른 쪽). "
             "LLM은 '아니오'를 덜어내지만 '예'도 조금 잃는데, 분류기 문턱을 올려도 같은 일이 일어납니다. 그래서 '예'를 같은 수만큼 남길 때 어느 쪽이 덜 남기는지로 견줍니다. "
             "괄호 안의 범위는 글을 다시 뽑아 %d번 재 본 95%% 범위이고, 범위가 0을 걸치면 차이가 우연일 수 있습니다.</p>" % core.BOOT)
    if res["stopped"]:
        p.append("<p class=\"legend\"><b>도중에 멈춘 결과입니다.</b> 받지 못한 답이 있는 조합은 받은 글만으로 쟀습니다. 다시 돌리면 이어서 받습니다.</p>")
    if d["part"] != "test":
        p.append("<p class=\"legend\"><b>주의</b>: 시험용 문서에 '예'와 '아니오' 정답이 모두 있지 않아, 정답이 붙은 모든 문서로 쟀습니다. "
                 "분류기가 이미 본 글이 섞여 있어 분류기 쪽 수치가 실제보다 좋게 나옵니다. label.bat 에서 시험용 문서를 정해 두면 공정하게 잴 수 있습니다.</p>")
    p.append("</div>")
    return "".join(p)


def _shape(x: float, y: float, k: int, cls: str, tip: str) -> str:
    """LLM마다 다른 모양의 점(색을 구별하기 어려워도 모양으로 알 수 있게)."""
    k = k % 4
    title = "<title>%s</title>" % esc(tip)
    if k == 0:
        return "<circle class=\"pt %s\" cx=\"%.1f\" cy=\"%.1f\" r=\"6\">%s</circle>" % (cls, x, y, title)
    if k == 1:
        return "<rect class=\"pt %s\" x=\"%.1f\" y=\"%.1f\" width=\"11\" height=\"11\">%s</rect>" % (cls, x - 5.5, y - 5.5, title)
    if k == 2:
        return "<rect class=\"pt %s\" x=\"%.1f\" y=\"%.1f\" width=\"10\" height=\"10\" transform=\"rotate(45 %.1f %.1f)\">%s</rect>" % (cls, x - 5, y - 5, x, y, title)
    return "<path class=\"pt %s\" d=\"M%.1f %.1fL%.1f %.1fL%.1f %.1fZ\">%s</path>" % (cls, x, y - 7, x + 6.5, y + 5, x - 6.5, y + 5, title)


def _plot(res: dict) -> str:
    """남긴 양(가로)과 지킨 '예'(세로). 선은 분류기 문턱만 올릴 때, 점은 LLM 조합. 선보다 왼쪽 위에 있는 점이 LLM이 나은 경우다."""
    base = res["data"].get("base_curve") or []
    done = [c for c in res["combos"] if c["metrics"]]
    if not base or not done:
        return ""
    W, H, L, R, T, B = 600, 360, 54, 22, 16, 44
    fx = lambda v: L + (W - L - R) * v
    fy = lambda v: H - B - (H - T - B) * v
    llms = res["setup"]["llms"]
    p = ["<svg class=\"plot\" width=\"%d\" height=\"%d\" viewBox=\"0 0 %d %d\" role=\"img\" aria-label=\"남긴 글의 비율과 지킨 예의 비율\">" % (W, H, W, H)]
    for g in (0, 0.25, 0.5, 0.75, 1.0):
        p.append("<line class=\"grid\" x1=\"%.1f\" x2=\"%.1f\" y1=\"%.1f\" y2=\"%.1f\"/>" % (fx(0), fx(1), fy(g), fy(g)))
        p.append("<line class=\"grid\" x1=\"%.1f\" x2=\"%.1f\" y1=\"%.1f\" y2=\"%.1f\"/>" % (fx(g), fx(g), fy(0), fy(1)))
        p.append("<text x=\"%.1f\" y=\"%.1f\" text-anchor=\"end\">%d%%</text>" % (fx(0) - 6, fy(g) + 4, g * 100))
        p.append("<text x=\"%.1f\" y=\"%.1f\" text-anchor=\"middle\">%d%%</text>" % (fx(g), fy(0) + 16, g * 100))
    p.append("<text x=\"%.1f\" y=\"%d\" text-anchor=\"middle\">남긴 글의 비율 (적을수록 사람이 볼 양이 줄어듦) →</text>" % (fx(0.5), H - 6))
    p.append("<text x=\"12\" y=\"%.1f\" text-anchor=\"middle\" transform=\"rotate(-90 12 %.1f)\">지킨 '예'의 비율 →</text>" % (fy(0.5), fy(0.5)))
    p.append("<polyline class=\"base\" points=\"%s\"><title>분류기 문턱만 올릴 때: 문턱을 올릴수록 왼쪽 아래로 내려감</title></polyline>" % " ".join(
        "%.1f,%.1f" % (fx(x), fy(y)) for x, y in base))
    groups = {}                                     # 같은 자리에 겹치는 점은 하나로 묶어 이름을 함께 적는다
    for c in done:
        m = c["metrics"]
        x, y = m["kept"] / float(m["n"]), (m["kept_yes"] / float(m["yes"]) if m["yes"] else 0.0)
        groups.setdefault((c["llm"], round(x, 4), round(y, 4)), []).append(c)
    hit = lambda a, b: a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
    taken = [(fx(x) - 8, fy(y) - 8, fx(x) + 8, fy(y) + 8) for (_, x, y) in groups]     # 점이 놓인 자리
    labels = []
    for (llm, x, y), cs in sorted(groups.items(), key=lambda kv: (kv[0][1], -kv[0][2])):
        k = llms.index(llm) if llm in llms else 0
        m = cs[0]["metrics"]
        tip = "%s · %s: %d개 가운데 %d개 남김, '예' %d개 가운데 %d개 지킴" % (llm, ", ".join(c["variant"] + " " + c["name"] for c in cs), m["n"], m["kept"], m["yes"], m["kept_yes"])
        p.append(_shape(fx(x), fy(y), k, "c%d" % min(k, 3), tip))
        text = "·".join(c["variant"] + ("*" if c["done"] < c["total"] else "") for c in cs)
        w, px, py = 8.0 * len(text) + 2, fx(x), fy(y)
        spots = [(10, -6), (10, 15), (-10, -6), (-10, 15), (10, -19), (10, 28), (-10, -19), (-10, 28), (24, 5), (-24, 5)]
        best_spot = None
        for dx, dy in spots:                        # 다른 점이나 글자와 겹치지 않는 첫 자리에 이름을 적는다
            x0 = px + dx if dx > 0 else px + dx - w
            box = (x0, py + dy - 11, x0 + w, py + dy + 2)
            if L <= box[0] and box[2] <= W - 2 and box[1] >= 2 and not any(hit(box, t) for t in taken):
                best_spot = (dx, dy, box)
                break
        dx, dy, box = best_spot or (10, -6, (px + 10, py - 17, px + 10 + w, py - 4))
        taken.append(box)
        labels.append("<text class=\"lab\" x=\"%.1f\" y=\"%.1f\" text-anchor=\"%s\">%s</text>" % (px + dx, py + dy, "start" if dx > 0 else "end", esc(text)))
    p.extend(labels)
    p.append("<circle class=\"now\" cx=\"%.1f\" cy=\"%.1f\" r=\"5\"><title>LLM 없이(분류기만): 통과한 글을 모두 남김</title></circle>" % (fx(1), fy(1)))
    p.append("<text x=\"%.1f\" y=\"%.1f\" text-anchor=\"end\">LLM 없이</text>" % (fx(1) - 9, fy(1) + 16))
    p.append("</svg>")
    keys = ["<span class=\"key\"><i class=\"ln\"></i> 분류기 문턱만 올릴 때</span>"]
    for k, name in enumerate(llms):
        keys.append("<span class=\"key c%d\"><i class=\"mk s%d\"></i> %s</span>" % (min(k, 3), k % 4, esc(name)))
    part = "<span class=\"key\">* 는 일부 글만 받은 조합(도중에 멈춤)</span>" if any(c["done"] < c["total"] for c in done) else ""
    return ("<div class=\"viz\">%s<p class=\"legend\">%s<span class=\"key\">글자는 프롬프트 안의 기호</span>%s</p></div>" % ("".join(p), "".join(keys), part))


def _summary(res: dict) -> str:
    d = res["data"]
    best = core.best_combo(res)
    top = max([c["metrics"]["sec_mean"] for c in res["combos"] if c["metrics"]] or [1.0]) or 1.0
    p = ["<div class=\"wrap viz\"><table class=\"cmp\"><tr><th>LLM</th><th>프롬프트 안</th><th>글이 갈린 모습</th><th>남긴 글</th><th>덜어낸 '아니오'</th>"
         "<th>잃은 '예'</th><th>분류기 문턱만 올리면</th><th>LLM이 더 줄인 수<br><small>(95% 범위)</small></th><th>글 하나에</th><th>문서 하나에</th>"
         "<th>토큰<br><small>입력 → 출력</small></th><th>비고</th></tr>"]
    for c in res["combos"]:
        m = c["metrics"]
        if not m:
            p.append("<tr><td>%s</td><td>%s %s</td><td colspan=\"10\" class=\"%s\">%s</td></tr>" % (
                esc(c["llm"]), esc(c["variant"]), esc(c["name"]), "bad" if c["error"] else "",
                esc("실패: " + c["error"]) if c["error"] else "아직 받은 답이 없습니다"))
            continue
        notes = []
        if c["done"] < c["total"]:
            notes.append("%d/%d개만 받음" % (c["done"], c["total"]))
        if c["error"]:
            notes.append("실패: " + c["error"][:60])
        if m["unknown"]:
            notes.append("읽지 못한 답 %d개(남긴 것으로 침)" % m["unknown"])
        if m["no_prob"]:
            notes.append("확률을 못 받은 답 %d개" % m["no_prob"])
        if m["thought"]:
            notes.append("생각만 하다 끊긴 답 %d개" % m["thought"])
        if m.get("no_think"):
            notes.append("생각 모드를 켰지만 생각 없이 답한 것 %d개(생각 모드가 없는 모델일 수 있음)" % m["no_think"])
        g = m["gain"]
        p.append("<tr%s><td>%s</td><td><b>%s</b> %s</td><td>%s</td><td class=\"n\"><b>%d</b> / %d <small>(%s)</small></td>"
                 "<td class=\"n\">%d / %d <small>(%s)</small></td><td class=\"n%s\">%d / %d</td><td class=\"n\">%s</td><td class=\"n%s\">%s</td>"
                 "<td class=\"n\"><i class=\"tbar\" style=\"width:%dpx\"></i>%s</td><td class=\"n\">%s</td><td class=\"n\">%.0f → %.0f</td><td><small>%s</small></td></tr>" % (
                     " class=\"pick\"" if best is not None and c["id"] == best["id"] else "",
                     esc(c["llm"]), esc(c["variant"]), esc(c["name"]), _split(m), m["kept"], m["n"], _pct(m["kept"] / float(m["n"])),
                     m["removed_no"], m["no"], _pct(m["removed_no"] / float(m["no"]) if m["no"] else None),
                     " bad" if m["lost_yes"] else "", m["lost_yes"], m["yes"],
                     "-" if m["base_kept"] is None else "%d개 남음" % m["base_kept"],
                     "" if g is None or g == 0 else (" good" if g > 0 else " bad"), _gain_text(m),
                     max(2, int(round(60 * m["sec_mean"] / top))), _time(m["sec_mean"]), _time(m["sec_mean"] * d["passed_per_doc"]),
                     m["tok_in"], m["tok_out"], esc(" · ".join(notes))))
    p.append("</table></div>")
    p.append("<p class=\"legend viz\"><span class=\"key\"><i class=\"ky\"></i> 남긴 것 가운데 정답 '예'</span><span class=\"key\"><i class=\"kn\"></i> 남긴 것 가운데 정답 '아니오'</span>"
             "<span class=\"key\"><i class=\"rn\"></i> 덜어낸 정답 '아니오' (잘 덜어냄)</span><span class=\"key\"><i class=\"ly\"></i> 잃은 정답 '예' (놓침)</span>"
             "<span class=\"key\"><i class=\"tk\"></i> 분류기 문턱만 올려 '예'를 같은 수만큼 남길 때 남는 양</span></p>"
             "<p class=\"legend\">띠에서 색이 찬 부분이 사람이 볼 양입니다. 찬 부분이 점선보다 왼쪽에서 끝나면 LLM이 분류기 문턱 올리기보다 더 줄인 것입니다. "
             "'문서 하나에'는 문서 하나에 통과하는 글의 평균 수(%.0f개)에 글 하나의 시간을 곱한 어림값입니다. 시간에는 모델을 처음 불러오는 시간이 빠져 있습니다.</p>" % d["passed_per_doc"])
    return "".join(p)


def _choices(res: dict) -> str:
    c = res["classifier"]
    pct = int(round(c["target"] * 100))
    rows = [
        ("LLM을 돌리는 곳", "이 PC의 Ollama %s, 주소 127.0.0.1" % esc(res["ollama"]),
         "회사 PC에 이미 있어 새로 설치할 것이 없습니다. 프록시를 거치지 않고, 이름에 cloud가 붙은 모델은 거부합니다.", "llama.cpp를 직접 실행"),
        ("분류기", "%s · %s · %s 학습" % (esc(c["label"]), esc(c["view_name"]), esc(c["trained"] or "?")),
         "저장해 둔 분류기를 그때그때 읽습니다. 다시 학습하면 다음 실행부터 새 분류기를 씁니다.", "다른 모델·크기는 화면에서 고름"),
        ("분류기 문턱", "%.4f — %s" % (c["threshold"], esc(c["thr_note"])),
         "걸러내기 비교 화면의 '%d%%를 찾는 문턱'과 같은 자리라서, 그 화면의 통과 수와 이어집니다." % pct, "지난 학습의 문턱, 0.5, 직접 정하기"),
        ("생각 모드", "기본은 끔", "켜면 답 하나에 수백 토큰을 더 써서 수십 배 느려집니다. 생각 모드가 있는 모델(Qwen3 8B)은 화면에서 '켠 것도 함께 돌리기'를 고르면 끈 것과 나란히 견줍니다. 켠 답의 확률은 생각이 끝난 뒤 답 자리에서 읽습니다.",
         "켠 것도 함께 돌려 정확도가 오르는지 보기(시간이 크게 듦)"),
        ("답 받는 방식", "'예/아니오' 한 단어 + 그 자리의 확률", "출력이 짧아 빠르고, 확률이 있어 순위로도 견줄 수 있습니다. 온도는 0이라 다시 돌려도 같은 답입니다.", "이유를 함께 받기(안 F)"),
        ("읽지 못한 답", "덜어내지 않고 남김", "이 단계의 목적은 '예'를 놓치지 않는 것이라, 모를 때는 사람에게 넘깁니다.", "덜어내기"),
        ("넣는 글의 길이", "판단할 글 %d자, 주변 글 %d자까지. 모델이 한 번에 읽는 길이 %d토큰" % (prompts.TEXT_LIMIT, prompts.CONTEXT_LIMIT, ollama.NUM_CTX),
         "긴 표가 통째로 들어가 시간이 늘어나는 것을 막습니다.", "더 길게(느려짐)"),
        ("프롬프트의 순서", "바뀌지 않는 부분(역할, 기준, 예시, 답하는 방법)을 앞에, 글마다 달라지는 부분을 뒤에",
         "Qwen3는 앞부분이 같으면 그 부분을 다시 읽지 않고 달라진 뒷부분만 읽어서 빠릅니다. Qwen3.5 같은 모델은 구조상 글마다 전체를 다시 읽어 입력 토큰이 많은 안일수록 느립니다(그래서 기본 모델에서 뺐습니다).",
         "여러 글을 묶어 한 번에 묻기(아직 없음)"),
        ("표본", "고정된 무작위 순서로 앞에서부터", "다시 돌려도 같은 글이 뽑히고, 표본을 늘리면 앞의 글이 그대로 들어 있어 받아 둔 답을 다시 씁니다.", "전부 돌리기"),
        ("프롬프트 예시(안 D)", "학습용 문서의 정답에서 예 %d개·아니오 %d개, 한 번 뽑으면 고정" % (core.N_EXAMPLES, core.N_EXAMPLES),
         "시험용 문서의 글을 예시로 쓰면 점수가 부풀려집니다. 예시가 바뀌면 답을 모두 다시 받아야 해서 고정해 둡니다.", "프롬프트 파일에 [예시] 조각을 직접 적기"),
        ("견주는 기준", "'예'를 같은 수만큼 남길 때 남는 글의 수", "LLM 없이 분류기 문턱만 올려도 '아니오'는 줄어듭니다. 그것보다 나아야 LLM을 붙일 값어치가 있습니다.", "덜어낸 수만 보기"),
    ]
    p = ["<details class=\"box\"><summary><b>고른 것과 그 이유</b> (묻지 않고 정한 값들)</summary><div class=\"wrap\"><table class=\"sum set\">"
         "<tr><th>무엇</th><th>지금 값</th><th>이유</th><th>다른 선택</th></tr>"]
    for a, b, why, alt in rows:
        p.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (a, b, why, alt))
    p.append("</table></div></details>")
    return "".join(p)


def _models(res: dict) -> str:
    p = ["<div class=\"wrap\"><table class=\"sum\"><tr><th>LLM</th><th>크기</th><th>줄인 방식</th><th>파일 크기</th><th>라이선스</th><th>생각 모드</th></tr>"]
    for m in res["llms"]:
        think = "켬 (답하기 전에 풀이를 씀, 최대 %d토큰)" % core.THINK_TOKENS if m.get("think") else ("끔 (있는 모델이지만 끄고 씀)" if m["thinking"] else "없는 모델")
        p.append("<tr><td>%s</td><td>%s</td><td>%s</td><td class=\"n\">%.1f GB</td><td>%s</td><td>%s</td></tr>" % (
            esc(m["name"]), esc(m["params"] or "-"), esc(m["quant"] or "-"), m["size"] / 1e9,
            esc(m["license"] or "모델에 적혀 있지 않음"), think))
    p.append("</table></div><p class=\"legend\">라이선스는 모델 파일에 적힌 값을 그대로 보여 준 것입니다.</p>")
    return "".join(p)


def _prompts(res: dict) -> str:
    p = ["<p class=\"legend\">프롬프트 파일: <code>%s</code> (메모장으로 고칠 수 있습니다) · 판단 기준은 <code>%s</code>에서 가져옵니다.</p>" % (
        esc(res["prompts_file"]), esc(res["sentences_file"]))]
    for v in res["variants"]:
        p.append("<details class=\"box\"><summary><b>%s %s</b> = %s%s</summary>" % (
            esc(v["key"]), esc(v["name"]), esc(" + ".join(v["parts"])), " — " + esc(v["purpose"]) if v["purpose"] else ""))
        p.append("<p class=\"legend\">앞쪽 글(모든 글에 똑같이 들어감) · 답은 %d토큰까지 받음</p><pre class=\"pr\">%s</pre>" % (v["max_tokens"], esc(v["system"])))
        p.append("<p class=\"legend\">뒤쪽 글(글마다 달라짐. 아래는 첫 번째 글의 경우)</p><pre class=\"pr\">%s</pre></details>" % esc(v["sample_user"]))
    return "".join(p)


def _runs_list(runs: List[dict], here: str, up: str) -> str:
    if not runs:
        return ""
    p = ["<h2>지난 실행</h2><div class=\"wrap\"><table class=\"sum\"><tr><th>때</th><th>분류기</th><th>LLM</th><th>프롬프트 안</th><th>넣은 글</th><th>가장 많이 줄인 조합</th><th></th></tr>"]
    for r in reversed(runs):
        p.append("<tr%s><td>%s</td><td>%s · %s</td><td>%s</td><td>%s</td><td class=\"n\">%s</td><td>%s</td><td><a href=\"%sruns/%s/index.html\">열기</a></td></tr>" % (
            " class=\"now\"" if r["stamp"] == here else "", esc(r["made"]), esc(r["classifier"]), esc(r["view"]), esc(", ".join(r["llms"])),
            esc(" ".join(r["variants"])), r["chosen"], esc(r.get("best", "-")), up, esc(r["stamp"])))
    p.append("</table></div><p class=\"legend\">돌릴 때마다의 화면을 <code>out/verify/runs</code>에 남겨 둡니다. 프로그램은 지난 결과를 지우지 않습니다.</p>")
    return "".join(p)


def render(res: dict, runs: List[dict], stamp: str, up: str) -> str:
    """up: 이 화면에서 out/verify 까지 올라가는 길 ('' 또는 '../../')"""
    c = res["classifier"]
    word = "줄" if c["unit"] == "line" else "덩어리"
    best = core.best_combo(res)
    data = {"items": [{"d": it["doc"], "p": it["page"], "t": it["text"], "y": it["label"], "s": it["score"], "ps": it["passed"]} for it in res["items"]],
            "combos": [{"id": x["id"], "llm": x["llm"], "v": x["variant"], "name": x["name"]} for x in res["combos"]],
            "ans": res["answers"], "best": best["id"] if best else ""}
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    p = ["<style>%s%s</style>" % (SCREEN_CSS, CSS), _headline(res)]
    p.append("<h2>남긴 양과 지킨 '예'</h2>")
    p.append("<p class=\"legend\">분류기를 통과한 글을 100%%로 놓고, 조합마다 얼마나 남겼는지(가로)와 그 안에 '예'를 얼마나 지켰는지(세로)를 찍었습니다. "
             "<b>선보다 왼쪽 위에 있는 점</b>은 분류기 문턱만 올리는 것보다 나은 조합입니다. 점 위에 마우스를 올리면 수치가 나옵니다.</p>")
    p.append(_plot(res))
    p.append("<h2>조합마다의 결과</h2>")
    p.append(_summary(res))
    p.append("<h2>분류기 출력과 LLM 출력 견주기</h2>")
    p.append("<p class=\"legend\">LLM에 넣은 %s마다 정답, 분류기 점수, 프롬프트 안마다의 LLM 판단을 나란히 놓았습니다. 칸의 숫자는 LLM이 본 '예'일 확률입니다. "
             "빨간 테두리는 정답이 '예'인데 LLM이 '아니오'라고 한 것(놓침)입니다.</p>" % word)
    filters = [("all", "모두"), ("lost", "LLM이 놓친 '예' (정답 예, LLM 아니오)"), ("left", "LLM이 못 덜어낸 '아니오' (정답 아니오, LLM 예)"),
               ("removed", "LLM이 덜어낸 '아니오'"), ("kept", "LLM이 지킨 '예'"), ("split", "프롬프트 안끼리 판단이 갈린 글")]
    if res["setup"]["with_rejected"]:
        filters.append(("rescue", "분류기는 떨어뜨렸는데 LLM은 '예'라고 한 글"))
    p.append("<div class=\"ctl\"><label>LLM <select id=\"v-llm\"></select></label><label>기준으로 볼 안 <select id=\"v-base\"></select></label>"
             "<label>보기 <select id=\"v-filter\">%s</select></label><span class=\"legend\" id=\"v-count\"></span></div>" % "".join(
                 "<option value=\"%s\">%s</option>" % (k, esc(n)) for k, n in filters))
    p.append("<div id=\"v-two\"></div>")
    if res["setup"]["with_rejected"] and res["setup"]["sample"]:
        p.append("<p class=\"legend\">표본으로 돌릴 때는 통과한 글과 떨어진 글에서 따로 뽑으므로, 위 표의 윗줄과 아랫줄의 크기 비는 실제 비와 다릅니다. 줄 안에서의 비율만 보세요.</p>")
    p.append("<div class=\"wrap\" id=\"v-table\"></div>")
    p.append("<h2>쓴 LLM</h2>")
    p.append(_models(res))
    p.append("<h2>프롬프트 전문</h2>")
    p.append(_prompts(res))
    p.append(_choices(res))
    p.append(_runs_list(runs, stamp, up))
    p.append("<script>window.VERIFY=%s;</script><script>%s</script>" % (blob, JS))
    sub = "분류기가 '검토 필요'로 본 %s을 이 PC 안의 LLM으로 한 번 더 걸러 본 결과 · %s · <a href=\"%s../index.html\">추출 결과 첫 화면</a>" % (
        word, esc(res["made"]), up)
    return _shell("LLM 검증 비교", sub, "", "".join(p))


def write(env: core.Env, res: dict) -> Path:
    """결과 화면을 적는다. 가장 최근 것은 out/verify/index.html, 이번 것은 out/verify/runs/때/ 에도 남긴다."""
    out = env.out
    out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    runs_file = out / "runs.json"
    try:
        runs = json.loads(runs_file.read_text(encoding="utf-8"))
        runs = runs if isinstance(runs, list) else []
    except Exception:
        runs = []
    best = core.best_combo(res)
    runs.append({"stamp": stamp, "made": res["made"], "classifier": res["classifier"]["label"], "view": res["classifier"]["view_name"],
                 "llms": res["setup"]["llms"], "variants": res["setup"]["variants"], "chosen": res["data"]["chosen_passed"],
                 "best": "-" if best is None else "%s · %s (%s)" % (best["llm"], best["variant"], _gain_text(best["metrics"]).split(" <")[0])})
    runs = runs[-KEEP_RUNS:]
    runs_file.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "runs" / stamp).mkdir(parents=True, exist_ok=True)
    (out / "runs" / stamp / "index.html").write_text(render(res, runs, stamp, "../../"), encoding="utf-8")
    (out / "index.html").write_text(render(res, runs, stamp, ""), encoding="utf-8")
    slim = {k: v for k, v in res.items() if k not in ("items", "answers")}
    (out / "result.json").write_text(json.dumps(slim, ensure_ascii=False, indent=1), encoding="utf-8")
    return out / "index.html"
