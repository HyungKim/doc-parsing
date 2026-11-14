"""뽑은 글을 다음 모델(분류기 등)에 넣을 때 고를 수 있는 세 가지 단위.

    쪽      한 쪽의 제목과 본문을 통째로 입력 하나로
    덩어리  리포트에서 번호 하나로 보이는 글상자·문단 묶음·표를 입력 하나로
    줄      덩어리 안의 줄(문단 하나, 표라면 한 행) 하나를 입력 하나로

어느 단위가 맞는지는 다음 모델이 무엇을 분류하느냐에 달려 있어서, 세 가지를 모두 파일로 내고
나란히 비교하는 화면을 함께 만든다. 글 내용은 리포트의 After 열과 같고, 나누는 자리만 다르다.
비교 화면에는 지금의 결과 파일(이름.json)에 실제로 들어 있는 모양(쪽마다 title 하나, body 하나)도 함께 보여 준다.

표는 값마다 머리글을 붙여 풀어 쓴 모양을 쓴다(한 줄만 떼어 놓아도 뜻이 남는다). 풀어 쓰지 못한 표는
칸 구분 모양이다. 칸 구분 모양은 text_pipe에 함께 넣는다.
"""
from __future__ import annotations

import json
from typing import Dict, List

from .model import PageOut
from .report import _shell, esc

SHORT_CHARS = 10      # 이 글자 수 이하인 입력은 '짧은 입력'으로 센다(소제목처럼 혼자서는 뜻이 부족한 것)

UNIT_NAMES = [("page", "쪽 통째"), ("block", "덩어리 하나씩"), ("line", "줄 하나씩")]


def build_units(pages: List[PageOut]) -> Dict[str, List[dict]]:
    """쪽별 결과를 세 가지 단위의 입력 목록으로 바꾼다. 세 목록이 담는 글은 같다."""
    out: Dict[str, List[dict]] = {"page": [], "block": [], "line": []}
    for p in pages:
        pid = "p%d" % p.number
        whole = [p.title] if p.title else []
        if p.title:                                # 제목도 입력 하나로 넣어, 어느 단위에서도 빠지는 글이 없게 한다
            item = {"id": pid + "-t", "page": p.number, "block": 0, "kind": "title", "text": p.title}
            out["block"].append(dict(item, lines=1))
            out["line"].append(dict(item, line=1))
        for n, b in enumerate(p.blocks, 1):
            is_table = b.kind == "table"
            lines = [t for t in (b.flat_lines if (is_table and b.flat_lines) else b.text.split("\n")) if t.strip()]
            if not lines:
                continue
            text = "\n".join(lines)
            whole.append(text)
            base = {"page": p.number, "block": n, "kind": b.kind, "title": p.title}
            if b.over_table:
                base["over_table"] = True          # 표 위에 얹혀 있던 글(코멘트)
            if is_table:
                base["table_form"] = "flat" if b.flat_mode == "keyvalue" else "pipe"
            block = dict({"id": "%s-b%d" % (pid, n)}, **base, text=text, lines=len(lines))
            if is_table:
                block["text_pipe"] = b.text
            out["block"].append(block)
            for k, line in enumerate(lines, 1):
                out["line"].append(dict({"id": "%s-b%d-l%d" % (pid, n, k)}, **base, line=k, text=line))
        out["page"].append({"id": pid, "page": p.number, "title": p.title, "text": "\n".join(whole),
                            "blocks": len(p.blocks)})
    return out


def _stats(sizes: List[int]) -> dict:
    sizes = sorted(sizes)
    return {
        "count": len(sizes),
        "chars_median": sizes[len(sizes) // 2] if sizes else 0,
        "chars_min": sizes[0] if sizes else 0,
        "chars_max": sizes[-1] if sizes else 0,
        "short": sum(1 for s in sizes if s <= SHORT_CHARS),
    }


def summarize(units: Dict[str, List[dict]]) -> Dict[str, dict]:
    """단위마다 입력이 몇 개이고 길이가 어떤지."""
    return {key: _stats([len(u["text"]) for u in units[key]]) for key, _ in UNIT_NAMES}


def write_units_json(name: str, kind: str, pages: List[PageOut], out_path: str, version: str = "") -> Dict[str, List[dict]]:
    units = build_units(pages)
    data = {"file": name, "kind": kind, "version": version, "short_chars": SHORT_CHARS,
            "summary": summarize(units), "units": units}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return units


CSS = """
ol.ulist{list-style:none;margin:6px 0 0;padding:0}
ol.ulist li{border:1px solid var(--line);border-radius:6px;padding:5px 9px 6px;margin:0 0 6px;background:var(--card)}
ol.ulist li.short{background:var(--df-bg)}
.uid{font-size:11px;color:var(--mute);margin-bottom:2px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.uid code{font:inherit;font-weight:700;color:var(--acc)}
.col.before .uid code{color:var(--mute)}
.ktag{display:inline-block;padding:0 5px;border-radius:3px;font-size:10px;font-weight:700;color:#fff;background:var(--mute)}
.ktag.t{background:#17803f}
.ktag.b{background:#1f5fbf}
.ktag.o{background:#a15c00}
.nl{color:var(--rm-ink);font-size:11px;font-weight:700;margin-left:3px;user-select:none}
section.page>h2 small{font-weight:400;font-size:13px;color:var(--mute);margin-left:8px}
details.shape{margin:4px 0;max-width:1100px}
details.shape summary{cursor:pointer;font-size:13px}
details.shape pre{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:8px 10px;font:12px/1.5 ui-monospace,Consolas,monospace;overflow-x:auto;white-space:pre-wrap;word-break:break-word}
"""


def _item_html(u: dict) -> str:
    size = len(u["text"])
    tags = ""
    if u.get("kind") == "title":
        tags += "<span class=\"ktag t\">제목</span>"
    if u.get("kind") == "table":
        tags += "<span class=\"ktag b\">%s</span>" % ("표 · 풀어 쓴 모양" if u.get("table_form") == "flat" else "표 · 칸 구분")
    if u.get("over_table"):
        tags += "<span class=\"ktag o\">표 위에 얹힌 글</span>"
    return "<li%s><div class=\"uid\"><code>%s</code><span>%d자</span>%s</div><div class=\"txt\">%s</div></li>" % (
        " class=\"short\"" if size <= SHORT_CHARS else "", esc(u["id"]), size, tags, esc(u["text"]))


def _raw_html(p: PageOut) -> str:
    """지금의 결과 파일에 들어 있는 모양 그대로: title 하나와 body 하나. 줄바꿈 글자가 있는 자리를 표시한다."""
    body = esc(p.body).replace("\n", "<span class=\"nl\">\\n</span>\n")
    return ("<li><div class=\"uid\"><code>title</code><span>%d자</span></div><div class=\"txt\">%s</div></li>"
            "<li><div class=\"uid\"><code>body</code><span>%d자 · 줄바꿈 글자 %d개가 들어 있는 글 하나</span></div><div class=\"txt\">%s</div></li>" % (
                len(p.title), esc(p.title) if p.title else "<span class=\"sub\">(비어 있음)</span>",
                len(p.body), p.body.count("\n"), body))


def _json_text(value) -> str:
    return esc(json.dumps(value, ensure_ascii=False, indent=2))


def write_units_report(name: str, kind: str, pages: List[PageOut], units: Dict[str, List[dict]], out_path: str,
                       doc_file: str = "", json_file: str = "", units_file: str = "") -> None:
    """지금의 실제 출력과 세 가지 단위를 쪽마다 나란히 보여 주는 화면."""
    stats = summarize(units)
    raw = _stats([len(p.body) for p in pages])
    n_pages = max(len(pages), 1)
    rows = ["<style>%s</style>" % CSS]
    rows.append("<div class=\"wrap\"><table class=\"sum\"><tr><th>모양</th><th>들어 있는 파일</th><th>입력 개수</th><th>쪽당 평균</th>"
                "<th>글자 수 가운데값</th><th>가장 짧은 입력</th><th>가장 긴 입력</th><th>%d자 이하 입력</th></tr>" % SHORT_CHARS)
    table = [("지금 실제 출력 (쪽마다 body 하나)", "%s 의 pages[].body" % (json_file or "이름.json"), raw)]
    table += [(label, "%s 의 units.%s[]" % (units_file or "이름.units.json", key), stats[key]) for key, label in UNIT_NAMES]
    for label, where, s in table:
        rows.append("<tr><td>%s</td><td>%s</td><td class=\"n\">%d개</td><td class=\"n\">%.1f개</td><td class=\"n\">%d자</td>"
                    "<td class=\"n\">%d자</td><td class=\"n\">%d자</td><td class=\"n\">%d개 (%.0f%%)</td></tr>" % (
                        esc(label), esc(where), s["count"], s["count"] / n_pages, s["chars_median"], s["chars_min"], s["chars_max"],
                        s["short"], 100.0 * s["short"] / max(s["count"], 1)))
    rows.append("</table></div>")
    rows.append("<p class=\"legend\"><b>맨 왼쪽 열</b>은 지금 결과 파일에 실제로 들어 있는 모양입니다. 쪽마다 제목(title) 하나와 본문(body) 하나이고, "
                "body는 덩어리와 줄이 모두 줄바꿈 글자(<span class=\"nl\">\\n</span>)로 이어진 <b>글 하나</b>입니다. "
                "그대로 다음 모델에 넣으면 쪽 하나가 입력 하나가 되고, 어디까지가 한 덩어리인지는 이 글만으로는 알 수 없습니다.</p>")
    rows.append("<p class=\"legend\"><b>나머지 세 열</b>은 같은 글을 단위별로 나눈 것입니다. 상자 하나가 입력 하나입니다. "
                "<b>쪽 통째</b>는 제목과 본문 전체, <b>덩어리</b>는 리포트에서 번호 하나로 보이는 글상자·문단 묶음·표, "
                "<b>줄</b>은 덩어리 안의 한 줄(문단 하나, 표라면 한 행)입니다. 줄은 마침표로 자른 문장이 아니어서 한 줄에 문장이 여러 개일 수 있습니다.</p>")
    rows.append("<p class=\"legend\"><span class=\"d\">노랑</span> = %d자 이하의 짧은 입력(소제목처럼 혼자서는 뜻이 부족할 수 있는 것). "
                "세 열의 표는 값마다 머리글을 붙여 풀어 쓴 모양이고, 풀어 쓰지 못한 표만 칸 구분 모양입니다(맨 왼쪽 열의 body는 칸 구분 모양). "
                "상자 위의 이름(p4-b3-l2 = 4쪽 3번 덩어리 2번째 줄)은 파일에 있는 id입니다.</p>" % SHORT_CHARS)
    if doc_file:
        rows.append("<p class=\"legend\"><a href=\"%s\">before/after 리포트로 가기</a> · 쪽 번호 옆의 링크로 그 쪽의 배치 그림을 볼 수 있습니다.</p>" % esc(doc_file))

    # 파일에 실제로 적히는 모양을 그대로 보여 준다(내용이 있는 첫 쪽 기준)
    sample = next((p for p in pages if len(p.blocks) >= 2), pages[0] if pages else None)
    if sample is not None:
        n = sample.number
        rows.append("<h3 style=\"font-size:14px;margin:14px 0 4px\">파일에 실제로 적히는 모양 (%d쪽 기준)</h3>" % n)
        shapes = [
            ("지금 실제 출력 · %s" % (json_file or "이름.json"), {"page": n, "title": sample.title, "body": sample.body}),
            ("쪽 통째 · units.page 의 항목 하나", next((u for u in units["page"] if u["page"] == n), None)),
            ("덩어리 하나씩 · units.block 의 처음 두 항목", [u for u in units["block"] if u["page"] == n][:2]),
            ("줄 하나씩 · units.line 의 처음 세 항목", [u for u in units["line"] if u["page"] == n][:3]),
        ]
        for label, value in shapes:
            rows.append("<details class=\"shape\"><summary>%s</summary><pre>%s</pre></details>" % (esc(label), _json_text(value)))

    by_page: Dict[int, Dict[str, List[dict]]] = {}
    for key, _ in UNIT_NAMES:
        for u in units[key]:
            by_page.setdefault(u["page"], {}).setdefault(key, []).append(u)
    body = ["".join(rows)]
    for p in pages:
        link = " <small><a href=\"%s#p%d\">배치 그림 보기</a></small>" % (esc(doc_file), p.number) if doc_file else ""
        body.append("<section class=\"page\" id=\"p%d\"><h2>%d쪽%s</h2><div class=\"cols\">" % (p.number, p.number, link))
        body.append("<article class=\"col before\" data-col=\"raw\"><h3><span>지금 실제 출력</span><span class=\"badge\">글 1개</span></h3>"
                    "<ol class=\"ulist\">%s</ol></article>" % _raw_html(p))
        for key, label in UNIT_NAMES:
            items = by_page.get(p.number, {}).get(key, [])
            body.append("<article class=\"col after\" data-col=\"%s\"><h3><span>%s</span><span class=\"badge\">입력 %d개</span></h3>"
                        "<ol class=\"ulist\">%s</ol></article>" % (key, esc(label), len(items), "".join(_item_html(u) for u in items)))
        body.append("</div></section>")

    bar = ["<div class=\"bar\"><b>표시할 열</b><label><input type=\"checkbox\" data-col=\"raw\" checked> 지금 실제 출력</label>"]
    for key, label in UNIT_NAMES:
        bar.append("<label><input type=\"checkbox\" data-col=\"%s\" checked> %s</label>" % (key, esc(label)))
    bar.append("</div>")
    sub = "%s · %d쪽 · 다음 모델에 넣을 단위 비교" % (esc(kind.upper()), len(pages))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_shell(name + " · 입력 단위", sub, "".join(bar), "".join(body)))
