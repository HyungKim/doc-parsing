"""표시 결과를 한 화면(HTML)으로: 무엇으로 골랐는지, '예'로 본 글이 어느 쪽 어디에 있는지, 문서 전체의 글과 점수.

원본 사본에 넣은 표시는 자리를 아는 만큼만 정확하지만(PPTX의 줄, 표 안의 줄은 덩어리 전체로 대신한다),
이 화면에서는 '예'로 본 줄을 글 그대로 정확히 칠해 보여 준다.
"""
from __future__ import annotations

import html
import time
from pathlib import Path
from typing import List, Optional

from .core import VIEW_NAME, Extracted


def esc(text) -> str:
    return html.escape(str(text), quote=True)


CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dee6;--acc:#1f5fbf;--hl:#fff3a0;--hl-ink:#5a4a00;--hl-edge:#d9a400;--box:#9aa5b5}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e6eaf0;--mute:#9aa5b5;--line:#343c48;--acc:#7fb0ff;--hl:#5a4d10;--hl-ink:#ffe98a;--hl-edge:#d9a400;--box:#6b7686}}
*{box-sizing:border-box}
body{margin:0;padding:18px 22px 60px;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:21px;margin:0 0 4px}
h2{font-size:17px;margin:26px 0 8px;padding-top:10px;border-top:1px solid var(--line)}
h2 small{font-weight:400;font-size:13px;color:var(--mute);margin-left:8px}
a{color:var(--acc)}
.sub{color:var(--mute);font-size:13px}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:10px 0;max-width:1100px}
.box p{margin:4px 0}
table.set{border-collapse:collapse;margin:6px 0}
table.set th,table.set td{text-align:left;padding:3px 14px 3px 0;vertical-align:top;font-size:14px}
table.set th{color:var(--mute);font-weight:400;white-space:nowrap}
.bar{position:sticky;top:0;z-index:5;background:var(--bg);padding:8px 0;border-bottom:1px solid var(--line);display:flex;gap:16px;flex-wrap:wrap;align-items:center;font-size:14px}
.pg{display:flex;gap:18px;align-items:flex-start;flex-wrap:wrap;max-width:1300px}
.map{position:relative;flex:0 0 260px;width:260px;background:var(--card);border:1px solid var(--line);border-radius:4px}
.map i{position:absolute;border:1px solid var(--box);border-radius:2px;font-style:normal;font-size:10px;color:var(--mute);line-height:1;padding:1px 2px;overflow:hidden}
.map i.y{background:var(--hl);border:1.5px solid var(--hl-edge);color:var(--hl-ink);font-weight:700}
.map i.r{border:0;border-radius:0;background:var(--hl-edge);opacity:.55;padding:0}
ol.bl{flex:1 1 520px;list-style:none;margin:0;padding:0;min-width:0}
ol.bl>li{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:6px 10px;margin:0 0 6px}
ol.bl>li.y{background:var(--hl);border-color:var(--hl-edge);color:var(--hl-ink)}
.hd{font-size:12px;color:var(--mute);display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:2px}
li.y>.hd{color:var(--hl-ink)}
.hd b{color:var(--acc)}
.sc{font-variant-numeric:tabular-nums;font-weight:700}
.tag{display:inline-block;padding:0 6px;border-radius:3px;font-size:11px;font-weight:700;background:var(--hl-edge);color:#fff}
.tag.g{background:var(--mute)}
.ln{display:flex;gap:8px;padding:1px 4px;border-radius:3px;white-space:pre-wrap;word-break:break-word}
.ln .sc{flex:0 0 38px;color:var(--mute);font-size:12px;padding-top:2px}
.ln.y{background:var(--hl);color:var(--hl-ink);outline:1px solid var(--hl-edge)}
.ln.y .sc{color:var(--hl-ink)}
.tx{white-space:pre-wrap;word-break:break-word}
body.only ol.bl>li:not(.has){display:none}
body.only .ln:not(.y).inl{display:none}
body.only section.none{display:none}
ul.toc{margin:4px 0;padding-left:20px}
ul.toc li{margin:1px 0}
"""

JS = """
document.getElementById('only').addEventListener('change',function(){document.body.classList.toggle('only',this.checked)});
"""


def _num(v: Optional[float]) -> str:
    return "-" if v is None else "%.2f" % v


def _pos(box) -> str:
    x0, y0, x1, y1 = box
    return "left:%.2f%%;top:%.2f%%;width:%.2f%%;height:%.2f%%" % (100 * x0, 100 * y0, 100 * max(x1 - x0, 0.004), 100 * max(y1 - y0, 0.004))


def write_page(ex: Extracted, scores: dict, view: str, threshold: float, marks: list, settings: dict, out_path: Path,
               made_files: List[dict], notes: List[str]) -> None:
    """settings: {"model", "stage", "classifier", "title_weight", "threshold_note", "method"}  made_files: [{"label", "href"}]"""
    by_line = view == "line"
    yes_ids = {m.id for m in marks}
    unit_word = "줄" if by_line else "덩어리"
    total = len(scores["line" if by_line else "block"])
    p = ["<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
         "<title>표시 결과 · %s</title><style>%s</style></head><body>" % (esc(ex.name), CSS),
         "<h1>표시 결과 · %s</h1>" % esc(ex.name),
         "<p class=\"sub\">학습해 둔 모델로 점수를 매겨, 문턱 이상인 %s을 '검토 필요(예)'로 표시했습니다 · 만든 때 %s</p>" % (unit_word, time.strftime("%Y-%m-%d %H:%M:%S"))]
    clf = settings.get("classifier")
    how = "기준 문장만 (학습 전)" if settings["stage"] == "before" else "학습한 분류기%s" % (
        " · %s에 학습 · 정답 예 %s개, 아니오 %s개" % (esc(clf.get("trained", "")), clf.get("yes", "?"), clf.get("no", "?")) if clf else "")
    p.append("<div class=\"box\"><p><b>'예'로 본 %s %d개</b> / 전체 %d개 (%.0f%%) · %d쪽 가운데 %d쪽에 있음</p>" % (
        unit_word, len(marks), total, 100.0 * len(marks) / max(total, 1), len(ex.pages), len({m.page for m in marks})))
    p.append("<table class=\"set\"><tr><th>모델</th><td>%s</td></tr><tr><th>넣는 크기</th><td>%s</td></tr><tr><th>판단 방법</th><td>%s</td></tr>"
             "<tr><th>문턱</th><td><b>%s</b> 이상이면 '예'%s</td></tr><tr><th>쪽 제목 반영</th><td>%s</td></tr></table>" % (
                 esc(settings["model"]), esc(VIEW_NAME[view]), how, _num(threshold),
                 " · %s" % esc(settings["threshold_note"]) if settings.get("threshold_note") else "",
                 "꺼짐" if not settings.get("title_weight") else "비율 %g" % settings["title_weight"]))
    if made_files:
        p.append("<p><b>표시한 파일</b>: %s</p>" % " · ".join(
            ("<a href=\"%s\">%s</a>" % (esc(f["href"]), esc(f["label"]))) if f.get("href") else esc(f["label"]) for f in made_files))
    for n in notes:
        p.append("<p class=\"sub\">%s</p>" % esc(n))
    p.append("</div>")

    # '예'가 있는 쪽으로 바로 가기
    pages_yes = {}
    for m in marks:
        pages_yes[m.page] = pages_yes.get(m.page, 0) + 1
    if pages_yes:
        p.append("<div class=\"box\"><p><b>'예'가 있는 쪽</b></p><ul class=\"toc\">%s</ul></div>" % "".join(
            "<li><a href=\"#pg%d\">%d쪽</a> · %s개%s</li>" % (n, n, c, " · %s" % esc(ex.titles.get(n) or "") if ex.titles.get(n) else "")
            for n, c in sorted(pages_yes.items())))
    p.append("<div class=\"bar\"><label><input type=\"checkbox\" id=\"only\"> '예'로 본 것만 보기</label>"
             "<span class=\"sub\">노란 바탕이 '예'로 본 %s입니다. 숫자는 점수(0~1)입니다. 왼쪽 그림은 그 쪽에서의 자리입니다.</span></div>" % unit_word)

    blocks_by_page = {}
    for b in (ex.doc.blocks if ex.doc else []):
        blocks_by_page.setdefault(b.page, []).append(b)
    marks_by_block = {}
    for m in marks:
        marks_by_block.setdefault(m.block_id, []).append(m)
    for page in ex.pages:
        blocks = blocks_by_page.get(page.number, [])
        count = pages_yes.get(page.number, 0)
        p.append("<section class=\"%s\" id=\"pg%d\"><h2>%d쪽%s<small>%s</small></h2><div class=\"pg\">" % (
            "" if count else "none", page.number, page.number, " · %s" % esc(page.title) if page.title else "",
            "'예' %d개" % count if count else "'예' 없음"))
        # 자리 그림
        parts = ["<div class=\"map\" style=\"aspect-ratio:%.4f\">" % max(ex.aspect, 0.2)]
        for b in blocks:
            box = ex.block_box.get(b.id)
            if not box:
                continue
            got = marks_by_block.get(b.id, [])
            whole = any((not m.exact) or m.unit == "block" for m in got)
            parts.append("<i class=\"%s\" style=\"%s\" title=\"%s\">%d</i>" % ("y" if whole else "", _pos(box), esc(b.text[:120]), b.number))
            if not whole:
                for m in got:                       # 줄의 자리를 아는 것은 그 줄만
                    for r in m.rows:
                        parts.append("<i class=\"r\" style=\"%s\"></i>" % _pos(r))
        parts.append("</div>")
        p.append("".join(parts))
        # 글
        p.append("<ol class=\"bl\">")
        for b in blocks:
            got = marks_by_block.get(b.id, [])
            block_yes = (not by_line) and b.id in yes_ids
            tags = ""
            if b.kind == "table":
                tags += "<span class=\"tag g\">표</span>"
            if block_yes:
                tags += "<span class=\"tag\">예</span>"
            elif got:
                tags += "<span class=\"tag\">예 %d줄</span>" % len(got)
            score = scores["block"].get(b.id)
            p.append("<li class=\"%s%s\"><div class=\"hd\"><b>%d</b>%s%s</div>" % (
                "y " if block_yes else "", "has" if got else "", b.number,
                "<span class=\"sc\">%s</span>" % _num(score) if score is not None else "", tags))
            if scores["line"]:
                for l in b.lines:
                    s = scores["line"].get(l.id)
                    p.append("<div class=\"ln%s%s\"><span class=\"sc\">%s</span><span>%s</span></div>" % (
                        " y" if (by_line and l.id in yes_ids) else "", " inl" if by_line else "", _num(s), esc(l.text)))
            else:
                p.append("<div class=\"tx\">%s</div>" % esc(b.text))
            p.append("</li>")
        if not blocks:
            p.append("<li class=\"sub\">뽑힌 글이 없는 쪽입니다.</li>")
        p.append("</ol></div></section>")
    p.append("<script>%s</script></body></html>" % JS)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("".join(p), encoding="utf-8")
