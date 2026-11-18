"""표시 결과를 한 화면(HTML)으로: 덩어리가 단계마다 얼마나 줄었는지, 단계마다 걸린 시간, 최종 모델의 설정, 문서 전체의 글과 판단.

원본 사본 두 개(분류기 표시, LLM 표시)에 넣은 표시와 같은 내용을, 이 화면에서는 글 그대로 나란히 보여 준다.
    진한 노랑   LLM까지 '예'로 본 덩어리 (LLM 표시 사본에 표시된 것)
    옅은 테두리  분류기는 '예'로 봤지만 LLM이 '아니오'라고 한 덩어리 (분류기 표시 사본에만 표시된 것)
LLM 단계를 돌리지 않았으면 분류기가 '예'로 본 덩어리가 진한 노랑이다.
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
li.y .tag.o{color:var(--hl-ink)}
.tx{white-space:pre-wrap;word-break:break-word}
.why{font-size:12px;color:var(--mute);margin-top:3px}
li.y .why{color:var(--hl-ink)}
body.fc ol.bl>li:not(.c):not(.y){display:none}
body.fl ol.bl>li:not(.y){display:none}
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
    """덩어리가 단계마다 얼마나 줄었는지: 전체 → 분류기 '예' → LLM까지 '예'."""
    c = res["counts"]
    total = max(c["blocks"], 1)
    rows = [("문서의 덩어리 전체", c["blocks"], "all", "")]
    rows.append(("① 분류기가 '예'로 본 덩어리", c["passed"], "", "전체의 %s" % _pct(c["passed"], c["blocks"])))
    if c["kept"] is not None:
        rows.append(("② LLM까지 거쳐 남은 덩어리", c["kept"], "",
                     "전체의 %s · 분류기 '예'의 %s" % (_pct(c["kept"], c["blocks"]), _pct(c["kept"], c["passed"]))))
    p = ["<div class=\"fn\">"]
    for name, n, cls, note in rows:
        p.append("<span class=\"nm\">%s</span><span class=\"tr\"><i class=\"%s\" style=\"width:%.2f%%\" title=\"%s %d개\"></i></span>"
                 "<span class=\"v\"><b>%d개</b>%s</span>" % (name, cls, 100.0 * n / total, esc(name), n, n, " · %s" % note if note else ""))
    p.append("</div>")
    return "".join(p)


def _settings(res: dict, llm) -> str:
    """최종 모델의 설정: 지금 값, 누가 정했는지와 이유, 다른 선택."""
    clf = res.get("classifier") or {}
    rows = [
        ("분류기의 모델", "multilingual-e5-small" + (" · %s에 학습 · 정답 예 %s개, 아니오 %s개" % (esc(clf.get("trained", "")), clf.get("yes", "?"), clf.get("no", "?")) if clf else ""),
         "5.0에서 사용자가 정한 것. 다른 모델(bge-m3, KURE-v1)은 뺐습니다.", "-"),
        ("넣는 크기", "덩어리 (덩어리의 글 전체를 한 번에 넣음)", "5.0에서 사용자가 정한 것. 분류기에도 LLM에도 덩어리를 넣습니다.", "-"),
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
            ("LLM의 답을 쓰는 방법", "'아니오'라고 한 덩어리만 덜어 냄. 읽지 못한 답은 남김", "프로그램이 정한 것: 이 단계의 목적이 '예'를 놓치지 않는 것이라, 모를 때는 사람에게 넘깁니다.", "확률에 문턱 두기(없음)"),
            ("답 받는 방식", "'예/아니오' 한 단어(%d토큰까지) · 온도 0 · 한 번에 읽는 길이 %d토큰 · 판단할 글은 %d자까지" % (
                _max_tokens(), _num_ctx(), _text_limit()), "프로그램이 정한 것: 다시 돌려도 같은 답이 나오고, 긴 표가 통째로 들어가 느려지는 것을 막습니다.", "-"),
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


def write_page(ex: Extracted, scores: dict, res: dict, marks_c: list, marks_l: Optional[list], llm, out_path: Path) -> None:
    """res: final.run_document 가 만든 결과.  marks_c: 분류기가 '예'로 본 것.  marks_l: LLM까지 거쳐 남은 것(LLM을 끝까지 돌리지 못했으면 None)"""
    c, info, files = res["counts"], res["llm"], res["files"]
    two = marks_l is not None                      # LLM의 판단이 모두 있는가
    c_ids = {m.id for m in marks_c}
    l_ids = {m.id for m in marks_l} if two else set()
    strong = l_ids if two else c_ids               # 진한 노랑으로 칠할 덩어리
    rows = info.get("rows") or {}
    p = ["<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
         "<title>표시 결과 · %s</title><style>%s</style></head><body class=\"tm\">" % (esc(ex.name), CSS),
         "<h1>표시 결과 · %s</h1>" % esc(ex.name),
         "<p class=\"sub\">최종 모델로 표시했습니다: 분류기(multilingual-e5-small · 덩어리)%s · 만든 때 %s</p>" % (
             " → LLM(%s)" % esc(info["label"]) if info.get("label") else "", esc(res["made"]))]

    # 한눈에: 얼마나 줄었나, 만든 파일
    p.append("<div class=\"box\"><h3>덩어리가 단계마다 얼마나 줄었나</h3>%s" % _funnel(res))
    if info.get("why"):
        p.append("<p class=\"%s\">%s</p>" % ("err" if (info["stopped"] or info["error"]) else "sub", esc(info["why"])))
    if info["ran"] and info["done"] and c["passed"]:
        p.append("<p class=\"sub\">LLM의 답: '예' %d개 · '아니오' %d개%s. LLM이 '아니오'라고 한 %d개를 덜어 냈습니다.</p>" % (
            c["llm_yes"], c["llm_no"], " · 읽지 못한 답 %d개(덜어 내지 않고 남김)" % c["llm_unknown"] if c["llm_unknown"] else "", c["llm_no"]))
    p.append("<h3 style=\"margin-top:10px\">표시한 파일</h3><ul class=\"files\">")
    p.append("<li>① 분류기 출력으로 표시한 사본: %s</li>" % (
        "<a href=\"%s\"><b>%s</b></a> · %d개 표시" % (esc(files["classifier"]), esc(files["classifier"]), c["passed"]) if files["classifier"] else "만들지 않음"))
    p.append("<li>② LLM까지 거친 결과로 표시한 사본: %s</li>" % (
        "<a href=\"%s\"><b>%s</b></a> · %d개 표시" % (esc(files["llm"]), esc(files["llm"]), c["kept"] or 0) if files["llm"] else "만들지 않음"))
    p.append("</ul>")
    for n in res["notes"]:
        p.append("<p class=\"sub\">%s</p>" % esc(n))
    p.append("</div>")

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
    p.append("<span class=\"sub\"><span class=\"key\"><i class=\"y\"></i>%s</span>%s숫자는 분류기 점수(0~1)입니다.</span></div>" % (
        "LLM까지 '예' (LLM 표시 사본에 표시됨)" if two else "분류기가 '예'로 본 덩어리",
        "<span class=\"key\"><i class=\"c\"></i>분류기는 '예', LLM은 '아니오' (분류기 표시 사본에만 표시됨)</span>" if two else ""))

    blocks_by_page = {}
    for b in (ex.doc.blocks if ex.doc else []):
        blocks_by_page.setdefault(b.page, []).append(b)
    for page in ex.pages:
        blocks = blocks_by_page.get(page.number, [])
        kc, kl = pages_c.get(page.number, 0), pages_l.get(page.number, 0)
        note = "'예' 없음" if not kc else ("분류기 '예' %d개%s" % (kc, " · LLM까지 '예' %d개" % kl if two else ""))
        p.append("<section class=\"%s%s\" id=\"pg%d\"><h2>%d쪽%s<small>%s</small></h2><div class=\"pg\">" % (
            "" if kc else "nc ", "" if (kl if two else kc) else "nl", page.number, page.number, " · %s" % esc(page.title) if page.title else "", note))
        parts = ["<div class=\"map\" style=\"aspect-ratio:%.4f\">" % max(ex.aspect, 0.2)]
        for b in blocks:
            box = ex.block_box.get(b.id)
            if not box:
                continue
            cls = "y" if b.id in strong else ("c" if b.id in c_ids else "")
            parts.append("<i class=\"%s\" style=\"%s\" title=\"%s\">%d</i>" % (cls, _pos(box), esc(b.text[:120]), b.number))
        parts.append("</div>")
        p.append("".join(parts))
        p.append("<ol class=\"bl\">")
        for b in blocks:
            cls = "y" if b.id in strong else ("c" if b.id in c_ids else "")
            tags = "<span class=\"tag g\">표</span>" if b.kind == "table" else ""
            why = ""
            if b.id in c_ids:
                tags += "<span class=\"tag%s\">분류기 예</span>" % ("" if not two else " o")
                r = rows.get(b.id)
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
            score = scores["block"].get(b.id)
            p.append("<li class=\"%s\"><div class=\"hd\"><b>%d</b>%s%s</div><div class=\"tx\">%s</div>%s</li>" % (
                cls, b.number, "<span class=\"sc\">%s</span>" % _num(score) if score is not None else "", tags, esc(b.text),
                "<div class=\"why\">%s</div>" % why if why else ""))
        if not blocks:
            p.append("<li class=\"sub\">뽑힌 글이 없는 쪽입니다.</li>")
        p.append("</ol></div></section>")
    p.append("<script>%s</script></body></html>" % JS)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("".join(p), encoding="utf-8")
