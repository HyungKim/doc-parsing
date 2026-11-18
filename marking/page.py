"""표시 결과를 한 화면(HTML)으로: 덩어리가 단계마다 얼마나 줄었는지, 단계마다 걸린 시간, 최종 모델의 설정, 문서 전체의 글과 판단.

원본 사본 두 개(분류기 표시, LLM 표시)에 넣은 표시와 같은 내용을, 이 화면에서는 글 그대로 나란히 보여 준다.
    진한 노랑   LLM까지 '예'로 본 덩어리 (LLM 표시 사본에 표시된 것)
    옅은 테두리  분류기는 '예'로 봤지만 LLM이 '아니오'라고 한 덩어리 (분류기 표시 사본에만 표시된 것)
LLM 단계를 돌리지 않았으면 분류기가 '예'로 본 덩어리가 진한 노랑이다.

5.1부터: 표는 행 하나씩 판단하므로 표 안에 행마다의 점수와 판단을 보여 준다. '표시하지 않는 규칙'에 걸려 뺀 것과,
표를 통째로 넣던 5.0 방식이었다면 어떻게 표시됐을지도 함께 보여 준다.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Optional

from . import times
from .core import Extracted


def esc(text) -> str:
    return html.escape(str(text), quote=True)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dee6;--acc:#1f5fbf;--hl:#fff3a0;--hl-ink:#5a4a00;--hl-edge:#d9a400;--box:#9aa5b5;--err:#a12626}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e6eaf0;--mute:#9aa5b5;--line:#343c48;--acc:#7fb0ff;--hl:#5a4d10;--hl-ink:#ffe98a;--hl-edge:#d9a400;--box:#6b7686;--err:#ffb3b3}}
*{box-sizing:border-box}
body{margin:0;padding:18px 22px 60px;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:21px;margin:0 0 4px}
h2{font-size:17px;margin:26px 0 8px;padding-top:10px;border-top:1px solid var(--line)}
h2 small{font-weight:400;font-size:13px;color:var(--mute);margin-left:8px}
h3{font-size:15px;margin:0 0 6px}
a{color:var(--acc)}
.sub{color:var(--mute);font-size:13px}
.err{color:var(--err);font-weight:700}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0;max-width:1100px;overflow-x:auto}
.box p{margin:4px 0}
table.set{border-collapse:collapse;margin:6px 0}
table.set th,table.set td{text-align:left;padding:4px 14px 4px 0;vertical-align:top;font-size:14px;border-bottom:1px solid var(--line)}
table.set th{color:var(--mute);font-weight:400;white-space:nowrap}
.fn{display:grid;grid-template-columns:max-content 1fr max-content;gap:6px 12px;align-items:center;max-width:760px;margin:6px 0}
.fn .nm{font-size:14px;white-space:nowrap}
.fn .tr{height:18px;background:var(--bg);border-radius:0 4px 4px 0;overflow:hidden}
.fn .tr i{display:block;height:100%;min-width:2px;background:var(--hl-edge);border-radius:0 4px 4px 0}
.fn .tr i.all{background:var(--box)}
.fn .v{font-variant-numeric:tabular-nums;font-size:14px;white-space:nowrap}
.files{margin:8px 0 2px;padding-left:20px}
.files li{margin:2px 0}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:6px 16px;flex-wrap:wrap;align-items:center;font-size:14px}
.bar label{cursor:pointer;white-space:nowrap}
.pg{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap;max-width:1300px}
.map{position:relative;flex:0 0 260px;width:260px;background:var(--card);border:1px solid var(--line);border-radius:4px}
.map i{position:absolute;border:1px solid var(--box);border-radius:2px;font-style:normal;font-size:10px;color:var(--mute);line-height:1;padding:1px 2px;overflow:hidden}
.map i.y{background:var(--hl);border:1.5px solid var(--hl-edge);color:var(--hl-ink);font-weight:700}
.map i.c{border:1.5px dashed var(--hl-edge);color:var(--ink);font-weight:700}
ol.bl{flex:1 1 520px;list-style:none;margin:0;padding:0;min-width:0}
ol.bl>li{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 10px;margin:0 0 6px}
ol.bl>li.y{background:var(--hl);border-color:var(--hl-edge);color:var(--hl-ink)}
ol.bl>li.c{border:1.5px dashed var(--hl-edge)}
.hd{font-size:12px;color:var(--mute);display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:2px}
li.y>.hd{color:var(--hl-ink)}
.hd b{color:var(--acc)}
li.y>.hd b{color:var(--hl-ink)}
.sc{font-variant-numeric:tabular-nums;font-weight:700}
.tag{display:inline-block;padding:0 6px;border-radius:3px;font-size:11px;font-weight:700;background:var(--hl-edge);color:#fff;white-space:nowrap}
.tag.g{background:var(--mute)}
.tag.o{background:transparent;color:var(--ink);border:1px dashed var(--hl-edge)}
.tag.r{background:transparent;color:var(--mute);border:1px solid var(--mute)}
li.y .tag.r{color:var(--hl-ink);border-color:var(--hl-ink)}
.sk{color:var(--mute)}
li.y .sk{color:var(--hl-ink);opacity:.7}
ol.rw{list-style:none;margin:6px 0 0;padding:0}
ol.rw>li{border:1px solid var(--line);border-radius:5px;padding:4px 8px;margin:0 0 4px;background:var(--card);color:var(--ink)}
ol.rw>li.y{background:var(--hl);border-color:var(--hl-edge);color:var(--hl-ink)}
ol.rw>li.c{border:1.5px dashed var(--hl-edge)}
ol.rw>li>.hd{color:var(--mute)}
ol.rw>li.y>.hd{color:var(--hl-ink)}
ol.bl>li.tb{background:var(--bg)}
body.fc ol.rw>li:not(.c):not(.y){display:none}
body.fl ol.rw>li:not(.y){display:none}
table.cmp{border-collapse:collapse;margin:6px 0}
table.cmp th,table.cmp td{text-align:left;padding:4px 14px 4px 0;vertical-align:top;font-size:14px;border-bottom:1px solid var(--line)}
table.cmp th{color:var(--mute);font-weight:400;font-size:13px}
table.cmp td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
ol.skl{margin:4px 0;padding-left:22px}
ol.skl li{margin:3px 0}
li.y .tag.o{color:var(--hl-ink)}
.tx{white-space:pre-wrap;word-break:break-word}
.why{font-size:12px;color:var(--mute);margin-top:3px}
li.y .why{color:var(--hl-ink)}
body.fc ol.bl>li:not(.c):not(.y){display:none}
body.fl ol.bl>li:not(.y){display:none}
body.fc ol.bl>li.tb,body.fl ol.bl>li.tb{background:var(--card)}
body.fc section.nc,body.fl section.nl{display:none}
ul.toc{margin:4px 0;padding-left:20px}
ul.toc li{margin:1px 0}
.key{display:inline-flex;align-items:center;gap:5px;margin-right:14px;white-space:nowrap}
.key i{display:inline-block;width:16px;height:12px;border-radius:2px}
.key i.y{background:var(--hl);border:1.5px solid var(--hl-edge)}
.key i.c{border:1.5px dashed var(--hl-edge)}
details.box>summary{cursor:pointer}
""" + times.CSS

JS = """
document.addEventListener('change',function(e){
  if(e.target.name!=='show')return;
  document.body.classList.remove('fc','fl');
  if(e.target.value)document.body.classList.add(e.target.value);
});
"""


def _num(v: Optional[float]) -> str:
    return "-" if v is None else "%.2f" % v


def _pos(box) -> str:
    x0, y0, x1, y1 = box
    return "left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%" % (100 * x0, 100 * y0, 100 * max(x1 - x0, 0.004), 100 * max(y1 - y0, 0.004))


def _pct(part: int, whole: int) -> str:
    return "%d%%" % int(round(100.0 * part / whole)) if whole else "-"


def _funnel(res: dict) -> str:
    """판단한 글이 단계마다 얼마나 줄었는지: 전체 → 분류기 '예' → (규칙으로 뺀 뒤) → LLM까지 '예'."""
    c = res["counts"]
    total = max(c["blocks"], 1)
    made = "글 덩어리 %d개" % c["text_blocks"] + (" + 표 %d개의 행 %d개" % (c["tables"], c["rows"]) if c["rows"] else "")
    rows = [("문서에서 판단한 글 전체", c["blocks"], "all", made)]
    rows.append(("분류기 점수가 문턱 이상", c["scored_yes"], "", "전체의 %s" % _pct(c["scored_yes"], c["blocks"])))
    if c["ruled"] or res["rules"]["title_words"] or res["rules"]["line_words"]:
        rows.append(("① '표시하지 않는 규칙'에 걸린 것을 뺀 뒤", c["passed"], "", "규칙으로 뺀 것 %d개 · 분류기 표시 사본에 표시한 수" % c["ruled"]))
    else:
        rows[-1] = ("① 분류기가 '예'로 본 것", c["passed"], "", "전체의 %s · 분류기 표시 사본에 표시한 수" % _pct(c["passed"], c["blocks"]))
    if c["kept"] is not None:
        rows.append(("② LLM까지 거쳐 남은 것", c["kept"], "",
                     "전체의 %s · ①의 %s · LLM 표시 사본에 표시한 수" % (_pct(c["kept"], c["blocks"]), _pct(c["kept"], c["passed"]))))
    p = ["<div class=\"fn\">"]
    for name, n, cls, note in rows:
        p.append("<span class=\"nm\">%s</span><span class=\"tr\"><i class=\"%s\" style=\"width:%.2f%%\" title=\"%s %d개\"></i></span>"
                 "<span class=\"v\"><b>%d개</b>%s</span>" % (esc(name), cls, 100.0 * n / total, esc(name), n, n, " · %s" % esc(note) if note else ""))
    p.append("</div>")
    return "".join(p)


def _said(v) -> str:
    return {1: "LLM '예' → LLM 표시 사본에도 표 전체", 0: "LLM '아니오' → 분류기 표시 사본에만 표 전체"}.get(v, "LLM의 답을 읽지 못함 → 두 사본 모두 표 전체") if v != "?" else "LLM의 답은 받아 둔 것이 없음"


def _changes(ex: Extracted, res: dict, c_ids: set, l_ids: set, two: bool) -> str:
    """5.1에서 달라진 것을 이 문서에서 보면: 표를 행으로 나눠 판단한 결과(5.0 방식과 나란히)와, 규칙으로 뺀 것."""
    c, rules, skips, old = res["counts"], res["rules"], res["skips"], res["tables"]
    thr = res["threshold"]
    p = ["<div class=\"box\"><h3>5.1에서 달라진 것 · 이 문서에서는</h3>"]

    # (가) 표
    tables = [b for b in (ex.doc.blocks if ex.doc else []) if b.kind == "table"]
    p.append("<p><b>(가) 표는 표 전체가 아니라 '예'로 본 행에만 표시</b></p>")
    if not tables:
        p.append("<p class=\"sub\">이 문서에는 표가 없습니다.</p>")
    else:
        old_yes = [b for b in tables if old.get(b.id, {}).get("yes")]
        p.append("<p class=\"sub\">표 %d개의 행 %d개를 하나씩 판단했습니다. 분류기와 문턱, LLM과 프롬프트는 글 덩어리와 같습니다. "
                 "표를 통째로 한 덩어리로 넣던 5.0 방식이었다면 표 %d개가 문턱 이상이라 <b>표 전체</b>에 표시됐을 것입니다(아래 표의 왼쪽).</p>" % (
                     len(tables), c["rows"], len(old_yes)))
        p.append("<table class=\"cmp\"><tr><th>쪽</th><th>표</th><th>행</th><th>5.0 방식: 표 전체를 한 덩어리로</th><th>5.1: 문턱 이상인 행</th>"
                 "<th>규칙으로 뺀 행</th><th>분류기 표시 사본</th>%s</tr>" % ("<th>LLM 표시 사본</th>" if two else ""))
        skipped_rows = {}
        for k in skips:
            if k["row"] and not k["line_id"]:
                skipped_rows[k["unit_id"]] = k
        for b in tables:
            o = old.get(b.id) or {}
            ids = [l.id for l in b.lines]
            n_c = sum(1 for i in ids if i in c_ids)
            n_l = sum(1 for i in ids if i in l_ids)
            n_s = sum(1 for i in ids if i in skipped_rows)
            before = "점수 %s → %s" % (_num(o.get("score")), "표시 안 함" if not o.get("yes") else "표 전체에 표시 · %s" % _said(o.get("llm")))
            if o.get("yes") and o.get("cut"):
                before += " (글이 길어 LLM에는 앞의 %d자만 들어감)" % _text_limit()
            p.append("<tr><td class=\"n\"><a href=\"#pg%d\">%d쪽</a></td><td>%d번</td><td class=\"n\">%d</td><td>%s</td><td class=\"n\">%d</td><td class=\"n\">%d</td>"
                     "<td class=\"n\"><b>행 %d개</b></td>%s</tr>" % (b.page, b.page, b.number, len(ids), esc(before), n_c + n_s, n_s, n_c,
                                                                  "<td class=\"n\"><b>행 %d개</b></td>" % n_l if two else ""))
        p.append("</table>")
        if any(o.get("llm") == "?" for o in old.values() if o.get("yes")):
            p.append("<p class=\"sub\">'받아 둔 것이 없음': 5.0 방식에서 LLM이 이 표에 뭐라고 답했을지는 새로 묻지 않았습니다. "
                     "5.0으로 같은 문서를 돌린 적이 있고 그때의 답이 <code>out\\mark\\cache</code>에 남아 있으면 여기에 나옵니다.</p>")

    # (나) 규칙
    p.append("<p style=\"margin-top:12px\"><b>(나) 표시하지 않는 규칙</b> <span class=\"sub\">%s</span></p>" % (
        "· <code>%s</code>에서 고칩니다" % esc(rules["file"]) if rules["file"] else ""))
    title_pages = sorted({k["page"] for k in skips if k["kind"] == "title"})
    hit_pages = sorted(n for n, t in ex.titles.items() if t and any("".join(w.split()) in "".join(t.split()) for w in rules["title_words"]))
    line_whole = [k for k in skips if k["kind"] == "line" and not k["line_id"]]
    line_part = [k for k in skips if k["kind"] == "line" and k["line_id"]]
    rows = []
    if rules["title_words"]:
        rows.append(("쪽 제목에 든 말 %s → 그 쪽에는 표시하지 않음" % " · ".join("'%s'" % esc(w) for w in rules["title_words"]),
                     "해당하는 쪽 %d쪽%s. 그 쪽에서 분류기 점수가 문턱 이상이던 것 <b>%d개</b>를 뺌" % (
                         len(hit_pages), " (%s)" % ", ".join("<a href=\"#pg%d\">%d쪽</a>" % (n, n) for n in hit_pages) if hit_pages else "",
                         sum(1 for k in skips if k["kind"] == "title"))))
    else:
        rows.append(("쪽 제목 규칙", "쓰지 않음(비어 있음)"))
    if rules["line_words"]:
        rows.append(("문장에 든 단어 %s → 그 문장에는 표시하지 않음" % " · ".join("'%s'" % esc(w) for w in rules["line_words"]),
                     "통째로 뺀 것 <b>%d개</b>(표의 행 %d개 · 모든 줄이 걸린 글 덩어리 %d개) · 덩어리는 남기고 그 줄에만 표시하지 않은 것 <b>%d줄</b>" % (
                         len(line_whole), sum(1 for k in line_whole if k["row"]), sum(1 for k in line_whole if not k["row"]), len(line_part))))
    else:
        rows.append(("문장 규칙", "쓰지 않음(비어 있음)"))
    p.append("<table class=\"cmp\"><tr><th>규칙</th><th>이번에 걸린 것</th></tr>%s</table>" % "".join("<tr><td>%s</td><td>%s</td></tr>" % r for r in rows))
    p.append("<p class=\"sub\">규칙은 분류기 점수가 문턱(%s) 이상인 것에만 적용해서 셉니다(문턱에 못 미친 것은 어차피 표시하지 않습니다). "
             "걸린 것은 두 사본 어디에도 표시하지 않고 LLM에도 묻지 않습니다. 문장 = 글 덩어리의 줄 하나, 표라면 행 하나. "
             "글 덩어리에서 일부 줄만 걸리면 판단은 덩어리 전체의 글로 하고, 걸린 줄에만 표시하지 않습니다.</p>" % _num(thr))
    if skips:
        p.append("<details><summary>규칙으로 뺀 것 %d개 보기 (규칙이 없었다면 분류기 표시 사본에 표시됐을 것)</summary><ol class=\"skl\">" % len(skips))
        for k in skips[:400]:
            what = "제목에 '%s'" % esc(k["word"]) if k["kind"] == "title" else "문장에 '%s'" % esc(k["word"])
            kind = "표의 행" if k["row"] else ("글 덩어리의 줄 하나" if k["line_id"] else "글 덩어리")
            p.append("<li><a href=\"#pg%d\">%d쪽</a> <span class=\"tag r\">%s</span> <span class=\"sub\">%s · 분류기 점수 %s</span><div class=\"tx\">%s</div></li>" % (
                k["page"], k["page"], what, kind, _num(k["score"]), esc(k["text"][:400])))
        if len(skips) > 400:
            p.append("<li class=\"sub\">… 나머지 %d개는 아래 쪽별 목록에서 볼 수 있습니다.</li>" % (len(skips) - 400))
        p.append("</ol></details>")
    p.append("</div>")
    return "".join(p)


def _settings(res: dict, llm) -> str:
    """최종 모델의 설정: 지금 값, 누가 정했는지와 이유, 다른 선택."""
    clf = res.get("classifier") or {}
    rows = [
        ("분류기의 모델", "multilingual-e5-small" + (" · %s에 학습 · 정답 예 %s개, 아니오 %s개" % (esc(clf.get("trained", "")), clf.get("yes", "?"), clf.get("no", "?")) if clf else ""),
         "5.0에서 사용자가 정한 것. 다른 모델(bge-m3, KURE-v1)은 뺐습니다.", "-"),
        ("넣는 크기", "글 덩어리는 덩어리 하나 · <b>표는 행 하나</b> (5.1)",
         "덩어리는 5.0에서 사용자가 정한 것. 표를 행으로 나눈 것은 5.1에서 '표는 해당 내용에만 표시'하려고 바꾼 것입니다. "
         "행에도 글 덩어리와 같은 분류기 · 같은 문턱 · 같은 LLM을 쓰기로 한 것은 프로그램이 정한 것입니다(행에 맞춰 따로 학습한 것이 아니고, 회사 자료로 확인한 것도 아닙니다).",
         "표 전체를 한 덩어리로(5.0) · 행에는 줄 단위로 학습한 분류기 쓰기(지금은 없음)"),
        ("표시하지 않는 규칙", "쪽 제목: %s<br>문장: %s" % (
            " · ".join("'%s'" % esc(w) for w in res["rules"]["title_words"]) or "없음", " · ".join("'%s'" % esc(w) for w in res["rules"]["line_words"]) or "없음"),
         "5.1에서 사용자가 정한 것%s. 분류기 뒤, LLM 앞에서 적용하고 걸린 것은 LLM에 묻지 않기로 한 것, 쪽 제목은 띄어쓰기를 무시하고 견주기로 한 것, "
         "문장을 '줄 하나(표는 행 하나)'로 본 것은 프로그램이 정한 것입니다." % (" · <code>%s</code>에서 고침" % esc(res["rules"]["file"]) if res["rules"]["file"] else ""),
         "규칙을 비워 두기 · 단어 더하기"),
        ("분류기의 문턱", "<b>%s</b> 이상이면 '예' — %s" % (_num(res["threshold"]), esc(res["threshold_note"])),
         "프로그램이 정한 기본값: 지난 학습에서 '예'의 90%를 찾던 문턱(없으면 0.5). 분류기는 넓게 잡고 LLM이 덜어 내는 흐름이라 덜 놓치는 쪽을 골랐습니다. 회사 자료로 맞춘 값은 아닙니다.",
         "0.5 · 직접 정하기 (표시하기 화면에서 고름)"),
        ("쪽 제목 반영", "꺼짐" if not res.get("title_weight") else "비율 %g" % res["title_weight"], "걸러내기 설정(screen_options.txt)을 그대로 따릅니다.", "-"),
    ]
    if llm is not None:
        m, v = llm.model, llm.variant
        rows += [
            ("LLM", "%s (%s %s · 라이선스 %s) · Ollama %s · 주소 127.0.0.1" % (esc(m["name"]), esc(m.get("params") or ""), esc(m.get("quant") or ""),
                                                                      esc(llm.license or "모델에 적혀 있지 않음"), esc(llm.version)),
             "5.0에서 사용자가 정한 것. 이 PC 안에서만 돌고, 이름에 cloud가 붙은 모델은 거부합니다. Qwen3 4B는 5.0부터 쓰지 않습니다.", "-"),
            ("프롬프트", "안 %s = %s" % (esc(v.label), esc(" + ".join(v.parts))),
             "5.0에서 사용자가 정한 것. 글은 <code>%s</code>, 판단 기준은 <code>%s</code>에서 읽습니다. 다른 안(A·B·D·E·F)은 5.0부터 쓰지 않습니다." % (
                 esc(llm.prompts_file.name), esc(llm.sentences_file.name)), "-"),
            ("생각 모드", "끔", "5.0에서 사용자가 정한 것.", "-"),
            ("LLM의 답을 쓰는 방법", "'아니오'라고 한 것만 덜어 냄. 읽지 못한 답은 남김", "프로그램이 정한 것: 이 단계의 목적이 '예'를 놓치지 않는 것이라, 모를 때는 사람에게 넘깁니다.", "확률에 문턱 두기(없음)"),
            ("답 받는 방식", "'예/아니오' 한 단어(%d토큰까지) · 온도 0 · 한 번에 읽는 길이 %d토큰 · 판단할 글은 %d자까지" % (
                _max_tokens(), _num_ctx(), _text_limit()), "프로그램이 정한 것: 다시 돌려도 같은 답이 나오고, 긴 글이 통째로 들어가 느려지는 것을 막습니다.", "-"),
        ]
    else:
        rows.append(("LLM", "돌리지 않음", esc(res["llm"].get("why") or ""), "-"))
    rows.append(("PDF에 표시하는 방식", "형광펜 주석" if res["method"] == "annot" else "쪽에 직접 칠하기", "표시하기 화면에서 고른 것.", "형광펜 주석 · 쪽에 직접 칠하기"))
    body = "".join("<tr><th>%s</th><td>%s</td><td>%s</td><td class=\"sub\">%s</td></tr>" % r for r in rows)
    return ("<details class=\"box\"><summary><b>최종 모델의 설정</b> · 지금 값, 정한 사람과 이유, 다른 선택</summary>"
            "<table class=\"set\"><tr><th>무엇</th><th>지금 값</th><th>정한 사람과 이유</th><th>다른 선택</th></tr>%s</table></details>" % body)


def _num_ctx() -> int:
    from verifying import ollama
    return ollama.NUM_CTX


def _text_limit() -> int:
    from verifying import prompts
    return prompts.TEXT_LIMIT


def _max_tokens() -> int:
    from verifying import prompts
    return prompts.MAX_TOKENS


def _verdict(uid: str, c_ids: set, rows: dict, info: dict, two: bool) -> tuple:
    """판단 단위 하나의 꼬리표와 덧붙임 글: (꼬리표 HTML, 덧붙임)"""
    tags, why = "", ""
    if uid not in c_ids:
        return tags, why
    tags += "<span class=\"tag%s\">분류기 예</span>" % ("" if not two else " o")
    r = rows.get(uid)
    if r is not None:
        prob = "" if r.get("p") is None else " %.2f" % r["p"]
        if r["verdict"] == 1:
            tags += "<span class=\"tag\">LLM 예%s</span>" % prob
        elif r["verdict"] == 0:
            tags += "<span class=\"tag g\">LLM 아니오%s</span>" % prob
        else:
            tags += "<span class=\"tag\">LLM의 답을 읽지 못해 남김</span>"
            why = "받은 답: %s" % esc((r.get("content") or "")[:200])
        if r.get("reason"):
            why = "LLM이 적은 이유: %s" % esc(r["reason"])
        why += (" · " if why else "") + "LLM이 답하는 데 %s" % times.fmt(r["sec"])
    elif info["ran"]:
        tags += "<span class=\"tag g\">LLM의 답을 받지 못함</span>"
    return tags, why


def _skip_tag(k: dict) -> str:
    return "<span class=\"tag r\">표시 안 함 · %s '%s'</span>" % ("제목에" if k["kind"] == "title" else "문장에", esc(k["word"]))


def write_page(ex: Extracted, scores: dict, res: dict, marks_c: list, marks_l: Optional[list], llm, out_path: Path) -> None:
    """res: final.run_document 가 만든 결과.  marks_c: 분류기가 '예'로 본 것(규칙에 걸린 것은 빠져 있다).
    marks_l: LLM까지 거쳐 남은 것(LLM을 끝까지 돌리지 못했으면 None).  표시의 id는 글 덩어리의 id, 표라면 행의 id다."""
    c, info, files = res["counts"], res["llm"], res["files"]
    two = marks_l is not None                      # LLM의 판단이 모두 있는가
    c_ids = {m.id for m in marks_c}
    l_ids = {m.id for m in marks_l} if two else set()
    strong = l_ids if two else c_ids               # 진한 노랑으로 칠할 것
    rows = info.get("rows") or {}
    skip_unit = {k["unit_id"]: k for k in res["skips"] if not k["line_id"]}       # 통째로 뺀 단위
    skip_line = {k["line_id"]: k for k in res["skips"] if k["line_id"]}           # 글 덩어리에서 그 줄에만 표시하지 않은 것
    row_scores = scores.get("row") or {}
    p = ["<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
         "<title>표시 결과 · %s</title><style>%s</style></head><body class=\"tm\">" % (esc(ex.name), CSS),
         "<h1>표시 결과 · %s</h1>" % esc(ex.name),
         "<p class=\"sub\">최종 모델로 표시했습니다: 분류기(multilingual-e5-small · 글 덩어리 하나씩, 표는 행 하나씩)%s · 만든 때 %s · 프로그램 5.1</p>" % (
             " → LLM(%s)" % esc(info["label"]) if info.get("label") else "", esc(res["made"]))]

    # 한눈에: 얼마나 줄었나, 만든 파일
    p.append("<div class=\"box\"><h3>판단한 글이 단계마다 얼마나 줄었나</h3>%s" % _funnel(res))
    if info.get("why"):
        p.append("<p class=\"%s\">%s</p>" % ("err" if (info["stopped"] or info["error"]) else "sub", esc(info["why"])))
    if info["ran"] and info["done"] and c["passed"]:
        p.append("<p class=\"sub\">LLM의 답: '예' %d개 · '아니오' %d개%s. LLM이 '아니오'라고 한 %d개를 덜어 냈습니다.</p>" % (
            c["llm_yes"], c["llm_no"], " · 읽지 못한 답 %d개(덜어 내지 않고 남김)" % c["llm_unknown"] if c["llm_unknown"] else "", c["llm_no"]))
    p.append("<h3 style=\"margin-top:10px\">표시한 파일</h3><ul class=\"files\">")
    p.append("<li>① 분류기 출력으로 표시한 사본: %s</li>" % (
        "<a href=\"%s\"><b>%s</b></a> · %d개 표시%s" % (esc(files["classifier"]), esc(files["classifier"]), c["passed"],
                                                      " (그 가운데 표의 행 %d개)" % c["passed_rows"] if c["passed_rows"] else "") if files["classifier"] else "만들지 않음"))
    p.append("<li>② LLM까지 거친 결과로 표시한 사본: %s</li>" % (
        "<a href=\"%s\"><b>%s</b></a> · %d개 표시%s" % (esc(files["llm"]), esc(files["llm"]), c["kept"] or 0,
                                                      " (그 가운데 표의 행 %d개)" % c["kept_rows"] if c.get("kept_rows") else "") if files["llm"] else "만들지 않음"))
    p.append("</ul>")
    for n in res["notes"]:
        p.append("<p class=\"sub\">%s</p>" % esc(n))
    p.append("</div>")

    # 5.1에서 달라진 것: 표는 행마다, 표시하지 않는 규칙
    p.append(_changes(ex, res, c_ids, l_ids, two))

    # 걸린 시간
    t = res["timing"]
    p.append("<div class=\"box\"><h3>단계마다 걸린 시간</h3>%s%s%s"
             "<p class=\"sub\">막대의 칸 너비가 걸린 시간에 비례합니다. 이 PC에서 이번에 실제로 잰 값입니다. 실행마다의 기록은 <a href=\"times.html\">걸린 시간 기록</a>에 쌓입니다.</p></div>" % (
                 times.bar(t), times.key(t), times.table(res)))
    p.append(_settings(res, llm))

    # '예'가 있는 쪽으로 바로 가기
    pages_c, pages_l = {}, {}
    for m in marks_c:
        pages_c[m.page] = pages_c.get(m.page, 0) + 1
        if m.id in l_ids:
            pages_l[m.page] = pages_l.get(m.page, 0) + 1
    if pages_c:
        p.append("<div class=\"box\"><p><b>'예'가 있는 쪽</b></p><ul class=\"toc\">%s</ul></div>" % "".join(
            "<li><a href=\"#pg%d\">%d쪽</a> · 분류기 '예' %d개%s%s</li>" % (
                n, n, k, " · LLM까지 '예' %d개" % pages_l.get(n, 0) if two else "", " · %s" % esc(ex.titles.get(n) or "") if ex.titles.get(n) else "")
            for n, k in sorted(pages_c.items())))
    p.append("<div class=\"bar\"><label><input type=\"radio\" name=\"show\" value=\"\" checked> 모두 보기</label>"
             "<label><input type=\"radio\" name=\"show\" value=\"fc\"> 분류기가 '예'로 본 것만</label>")
    if two:
        p.append("<label><input type=\"radio\" name=\"show\" value=\"fl\"> LLM까지 '예'로 본 것만</label>")
    p.append("<span class=\"sub\"><span class=\"key\"><i class=\"y\"></i>%s</span>%s숫자는 분류기 점수(0~1)입니다. 표는 행마다 점수가 있습니다.</span></div>" % (
        "LLM까지 '예' (LLM 표시 사본에 표시됨)" if two else "분류기가 '예'로 본 것",
        "<span class=\"key\"><i class=\"c\"></i>분류기는 '예', LLM은 '아니오' (분류기 표시 사본에만 표시됨)</span>" if two else ""))

    blocks_by_page = {}
    for b in (ex.doc.blocks if ex.doc else []):
        blocks_by_page.setdefault(b.page, []).append(b)

    def cls_of(ids) -> str:
        return "y" if any(i in strong for i in ids) else ("c" if any(i in c_ids for i in ids) else "")

    for page in ex.pages:
        blocks = blocks_by_page.get(page.number, [])
        kc, kl = pages_c.get(page.number, 0), pages_l.get(page.number, 0)
        ruled = sum(1 for k in res["skips"] if k["page"] == page.number)
        note = "'예' 없음" if not kc else ("분류기 '예' %d개%s" % (kc, " · LLM까지 '예' %d개" % kl if two else ""))
        if ruled:
            note += " · 규칙으로 표시하지 않은 것 %d개" % ruled
        p.append("<section class=\"%s%s\" id=\"pg%d\"><h2>%d쪽%s<small>%s</small></h2><div class=\"pg\">" % (
            "" if kc else "nc ", "" if (kl if two else kc) else "nl", page.number, page.number, " · %s" % esc(page.title) if page.title else "", note))
        parts = ["<div class=\"map\" style=\"aspect-ratio:%.4f\">" % max(ex.aspect, 0.2)]
        for b in blocks:
            box = ex.block_box.get(b.id)
            if not box:
                continue
            ids = [l.id for l in b.lines] if b.kind == "table" else [b.id]
            parts.append("<i class=\"%s\" style=\"%s\" title=\"%s\">%d</i>" % (cls_of(ids), _pos(box), esc(b.text[:120]), b.number))
        parts.append("</div>")
        p.append("".join(parts))
        p.append("<ol class=\"bl\">")
        for b in blocks:
            if b.kind == "table":                  # 표: 행마다 점수와 판단
                ids = [l.id for l in b.lines]
                o = (res.get("tables") or {}).get(b.id) or {}
                n_c, n_l = sum(1 for i in ids if i in c_ids), sum(1 for i in ids if i in l_ids)
                head = "행 %d개 가운데 분류기 '예' %d개%s" % (len(ids), n_c, " · LLM까지 '예' %d개" % n_l if two else "")
                old = "표 전체를 한 덩어리로 넣었다면(5.0 방식) 점수 %s → %s" % (
                    _num(o.get("score")), "표 전체에 표시" if o.get("yes") else "표시 안 함")
                p.append("<li class=\"tb %s\"><div class=\"hd\"><b>%d</b><span class=\"tag g\">표</span><span>%s</span></div>"
                         "<div class=\"why\" style=\"margin:0 0 4px\">%s</div><ol class=\"rw\">" % (cls_of(ids), b.number, esc(head), esc(old)))
                for l in b.lines:
                    tags, why = _verdict(l.id, c_ids, rows, info, two)
                    if l.id in skip_unit:
                        tags += _skip_tag(skip_unit[l.id])
                    sc = row_scores.get(l.id)
                    p.append("<li class=\"%s\"><div class=\"hd\">%s%s</div><div class=\"tx%s\">%s</div>%s</li>" % (
                        cls_of([l.id]), "<span class=\"sc\">%s</span>" % _num(sc) if sc is not None else "", tags,
                        " sk" if l.id in skip_unit else "", esc(l.text), "<div class=\"why\">%s</div>" % why if why else ""))
                p.append("</ol></li>")
                continue
            cls = cls_of([b.id])
            tags, why = _verdict(b.id, c_ids, rows, info, two)
            if b.id in skip_unit:
                tags += _skip_tag(skip_unit[b.id])
            score = scores["block"].get(b.id)
            if any(l.id in skip_line for l in b.lines):        # 일부 줄에만 표시하지 않은 덩어리: 줄마다 나눠 보여 준다
                body = "\n".join(
                    "<span class=\"sk\">%s</span> %s" % (esc(l.text), _skip_tag(skip_line[l.id])) if l.id in skip_line else esc(l.text) for l in b.lines)
            else:
                body = esc(b.text)
            p.append("<li class=\"%s\"><div class=\"hd\"><b>%d</b>%s%s</div><div class=\"tx%s\">%s</div>%s</li>" % (
                cls, b.number, "<span class=\"sc\">%s</span>" % _num(score) if score is not None else "", tags,
                " sk" if b.id in skip_unit else "", body, "<div class=\"why\">%s</div>" % why if why else ""))
        if not blocks:
            p.append("<li class=\"sub\">뽑힌 글이 없는 쪽입니다.</li>")
        p.append("</ol></div></section>")
    p.append("<script>%s</script></body></html>" % JS)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("".join(p), encoding="utf-8")
