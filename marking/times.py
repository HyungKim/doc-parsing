"""걸린 시간: 단계별 시간을 보여 주는 막대와 표, 그리고 표시하기를 돌릴 때마다 쌓는 시간 기록.

    out/mark/times.jsonl    실행 기록(문서 하나에 한 줄). 프로그램은 이 기록을 지우지 않는다
    out/mark/times.html     기록을 한 화면으로 (최근 것이 위)
    out/mark/times.csv      같은 내용을 표로 (엑셀에서 열 수 있다. 시간은 초)

단계마다 색이 정해져 있고 화면마다 같다: 글 뽑기(파랑) · 분류기(주황) · LLM(초록) · 파일 만들기(회색).
표시하기에는 LLM 단계가 없고(글 뽑기 → 분류기 → 파일 만들기), LLM 검증의 결과 화면은 분류기와 LLM 두 단계를 같은 색으로 보여 준다.
"""
from __future__ import annotations

import csv
import html
import json
import time
from pathlib import Path
from typing import List, Optional

STAGES = [("extract", "글 뽑기"), ("classify", "분류기"), ("llm", "LLM"), ("write", "파일 만들기")]
INDEX = {k: n for n, (k, _) in enumerate(STAGES)}

# 막대의 색: 앞의 세 색은 어떤 순서로 이웃해도 색을 잘 가리지 못하는 눈에 구별되는 것을 확인한 색(밝은 바탕 / 어두운 바탕).
# 넷째(파일 만들기)는 색을 더 늘리면 구별이 어려워져서 회색으로 둔다.
CSS = """
.tm{--t0:#2a78d6;--t1:#eb6834;--t2:#1baf7a;--t3:var(--mute)}
@media (prefers-color-scheme:dark){.tm{--t0:#3987e5;--t1:#d95926;--t2:#199e70}}
.tbar2{display:flex;gap:2px;height:22px;max-width:760px;margin:6px 0 4px}
.tbar2 i{display:block;min-width:3px;height:100%;background:var(--c)}
.tbar2 i:first-child{border-radius:4px 0 0 4px}.tbar2 i:last-child{border-radius:0 4px 4px 0}
.tbar2 i:only-child{border-radius:4px}
.tbar2.s{height:12px;max-width:220px;margin:2px 0}
.t0{--c:var(--t0)}.t1{--c:var(--t1)}.t2{--c:var(--t2)}.t3{--c:var(--t3)}
.tkey{display:flex;gap:4px 18px;flex-wrap:wrap;font-size:13px;margin:2px 0 6px}
.tkey span{display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.tkey i{display:inline-block;width:12px;height:12px;border-radius:2px;background:var(--c)}
.tkey b{font-variant-numeric:tabular-nums}
table.tt{border-collapse:collapse;margin:6px 0;width:auto}
table.tt th,table.tt td{text-align:left;padding:4px 14px 4px 0;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}
table.tt th{color:var(--mute);font-weight:400;font-size:13px}
table.tt td.n,table.tt th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.tt td.k{white-space:nowrap}
table.tt td.k i{display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--c);margin-right:6px}
table.tt tr.sum td{font-weight:700;border-top:2px solid var(--line)}
table.tt td.d{color:var(--mute);font-size:13px}
"""


def esc(text) -> str:
    return html.escape(str(text), quote=True)


def fmt(seconds: Optional[float]) -> str:
    """걸린 시간을 읽기 쉬운 말로: 0.04초, 3.2초, 12초, 2분 05초, 1시간 02분"""
    if seconds is None:
        return "-"
    s = max(0.0, float(seconds))
    if 0 < s < 0.005:
        return "0.01초 미만"
    if s < 0.995:
        return "%.2f초" % s
    if s < 10:
        return "%.1f초" % s
    if s < 60:
        return "%d초" % int(round(s))
    if s < 3600:
        whole = int(round(s))
        return "%d분 %02d초" % (whole // 60, whole % 60)
    whole = int(round(s / 60.0))
    return "%d시간 %02d분" % (whole // 60, whole % 60)


def share(part: float, total: float) -> str:
    if total <= 0:
        return "-"
    p = 100.0 * part / total
    return "1% 미만" if 0 < p < 1 else "%d%%" % int(round(p))


def _stages(timing: dict) -> List[tuple]:
    """timing에 들어 있는 단계만, 정해진 순서로: (색 번호, 키, 이름, 초)"""
    return [(INDEX[k], k, name, float(timing[k]["sec"])) for k, name in STAGES if k in timing]


def total(timing: dict) -> float:
    return sum(sec for _, _, _, sec in _stages(timing))


def bar(timing: dict, small: bool = False) -> str:
    """단계별 시간을 한 줄 막대로. 칸의 너비가 걸린 시간에 비례한다."""
    all_sec = total(timing)
    if all_sec <= 0:
        return ""
    cells = ["<i class=\"t%d\" style=\"flex:%.4f 1 0\" title=\"%s %s (%s)\"></i>" % (n, sec / all_sec, name, fmt(sec), share(sec, all_sec))
             for n, _, name, sec in _stages(timing) if sec > 0]
    label = " · ".join("%s %s" % (name, fmt(sec)) for _, _, name, sec in _stages(timing))
    return "<div class=\"tbar2%s\" role=\"img\" aria-label=\"%s\">%s</div>" % (" s" if small else "", esc(label), "".join(cells))


def key(timing: dict) -> str:
    """막대 아래의 풀이: 단계 이름과 시간."""
    all_sec = total(timing)
    return "<div class=\"tkey\">%s<span>합계 <b>%s</b></span></div>" % ("".join(
        "<span><i class=\"t%d\"></i>%s <b>%s</b> (%s)</span>" % (n, name, fmt(sec), share(sec, all_sec))
        for n, _, name, sec in _stages(timing)), fmt(all_sec))


# ---------------------------------------------------------------- 표시하기의 단계별 표

def classify_note(cl: dict) -> str:
    """분류기 단계의 덧붙임: 새로 계산했는지, 보관해 둔 계산을 다시 썼는지, 모델을 불러오는 데 든 시간."""
    load = max(0.0, float(cl["sec"]) - float(cl["compute"]))        # 모델을 불러오는 데 든 시간(점수 계산을 뺀 나머지)
    if cl["reused"]:
        note = "새로 계산 %d개 · 보관해 둔 계산을 다시 쓴 것 %d개 → 그만큼 짧게 나옵니다" % (cl["new"], cl["reused"])
    else:
        note = "모두 새로 계산" + (" (보관해 둔 계산을 쓰지 않음)" if cl.get("fresh") else "")
    if cl["new"]:
        note += " · 모델을 불러오는 데 %s, 점수 계산에 %s" % (fmt(load), fmt(cl["compute"]))
    return note


def detail_rows(res: dict) -> List[tuple]:
    """표시하기의 단계마다: (색 번호, 이름, 한 일, 초, 하나에 걸린 시간, 덧붙임)"""
    t = res["timing"]
    ex, cl, wr = t["extract"], t["classify"], t["write"]
    word = "줄" if res["unit"] == "line" else "덩어리"
    rows = [(INDEX["extract"], "글 뽑기", "%d쪽에서 덩어리 %d개 · 줄 %d개" % (ex["pages"], ex["blocks"], ex["lines"]), ex["sec"],
             "1쪽에 %s" % fmt(ex["sec"] / ex["pages"]) if ex["pages"] else "-", "파일을 올렸을 때 잰 값")]
    scored = "%s %d개에 점수" % ("줄" if res["view"] != "block" else "덩어리", cl["items"])
    rows.append((INDEX["classify"], "분류기", "%s → '예'로 본 %s %d개" % (scored, word, res["yes"]), cl["sec"],
                 "글 하나에 %s (모델을 불러오는 시간 빼고)" % fmt(cl["compute"] / cl["new"]) if cl["new"] else "-", classify_note(cl)))
    made = (["표시한 사본 %s" % fmt(wr["copy"])] if res.get("marked") else []) + ["요약 화면 %s" % fmt(wr.get("page", 0.0))]
    rows.append((INDEX["write"], "파일 만들기", " · ".join(made), wr["sec"], "-", ""))
    return rows


def table(res: dict) -> str:
    """단계별 표(요약 화면에 넣는다)."""
    all_sec = total(res["timing"])
    p = ["<table class=\"tt\"><tr><th>단계</th><th>한 일</th><th class=\"n\">걸린 시간</th><th class=\"n\">비율</th><th>하나에 걸린 시간</th><th>덧붙임</th></tr>"]
    for k, (n, name, did, sec, one, note) in enumerate(detail_rows(res), 1):
        p.append("<tr><td class=\"k\"><i class=\"t%d\"></i>%d. %s</td><td>%s</td><td class=\"n\"><b>%s</b></td><td class=\"n\">%s</td><td>%s</td><td class=\"d\">%s</td></tr>" % (
            n, k, name, esc(did), fmt(sec), share(float(sec), all_sec), esc(one), esc(note)))
    p.append("<tr class=\"sum\"><td>합계</td><td></td><td class=\"n\">%s</td><td class=\"n\">100%%</td><td></td><td></td></tr></table>" % fmt(all_sec))
    return "".join(p)


def box(res: dict) -> str:
    """요약 화면에 넣는 '단계마다 걸린 시간' 상자."""
    t = res["timing"]
    return ("<div class=\"box tm\"><p><b>단계마다 걸린 시간</b></p>%s%s%s"
            "<p class=\"sub\">막대의 칸 너비가 걸린 시간에 비례합니다. 이 PC에서 이번에 실제로 잰 값입니다. 표시하기에는 LLM 단계가 없습니다"
            "(LLM에 걸리는 시간은 verify.bat 결과 화면의 '단계마다 걸린 시간'에 나옵니다). 실행마다의 기록은 <a href=\"times.html\">걸린 시간 기록</a>에 쌓입니다.</p></div>" % (
                bar(t), key(t), table(res)))


# ---------------------------------------------------------------- 실행 기록

def folder(cfg) -> Path:
    return Path(cfg.out_dir) / "mark"


def load(cfg) -> List[dict]:
    path = folder(cfg) / "times.jsonl"
    out = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def add(cfg, res: dict) -> None:
    """문서 하나의 실행을 기록에 더하고 화면과 표를 새로 쓴다."""
    t = res["timing"]
    rec = {"at": res["made"], "file": res["name"], "model": res["model"], "view": res["view_name"], "how": res["how"],
           "threshold": round(float(res["threshold"]), 4), "unit": res["unit"], "yes": res["yes"], "total": res["total"],
           "timing": {k: {a: (round(b, 3) if isinstance(b, float) else b) for a, b in t[k].items()} for k, _ in STAGES if k in t},
           "sum": round(total(t), 3), "fresh": bool(t["classify"].get("fresh"))}
    out = folder(cfg)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "times.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    write(cfg)


def _remark(r: dict) -> str:
    cl = r["timing"]["classify"]
    out = []
    if r.get("fresh"):
        out.append("처음부터 다시 계산")
    if cl.get("reused"):
        out.append("보관해 둔 계산 %d개 사용 → 분류기 시간이 그만큼 짧게 나옴" % cl["reused"])
    return " · ".join(out)


def write(cfg) -> None:
    recs = load(cfg)
    out = folder(cfg)
    head = ["때", "파일", "쪽", "덩어리", "줄", "모델", "넣는 크기", "판단 방법", "문턱", "점수 매긴 글", "'예'로 본 수",
            "글 뽑기(초)", "분류기(초)", "분류기: 모델 불러오기(초)", "분류기: 점수 계산(초)", "파일 만들기(초)", "합계(초)", "비고"]
    with open(out / "times.csv", "w", encoding="utf-8-sig", newline="") as f:       # 엑셀이 한글을 바로 읽도록 BOM을 붙인다
        w = csv.writer(f)
        w.writerow(head)
        for r in recs:
            t = r["timing"]
            ex, cl = t["extract"], t["classify"]
            w.writerow([r["at"], r["file"], ex["pages"], ex["blocks"], ex["lines"], r["model"], r["view"], r["how"], r["threshold"], cl["items"], r["yes"],
                        ex["sec"], cl["sec"], round(max(0.0, cl["sec"] - cl["compute"]), 3), cl["compute"], t["write"]["sec"], r["sum"], _remark(r)])
    page_css = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2330;--mute:#5d6878;--line:#d9dee6;--acc:#1f5fbf}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2229;--ink:#e6eaf0;--mute:#9aa5b5;--line:#343c48;--acc:#7fb0ff}}
*{box-sizing:border-box}
body{margin:0;padding:18px 22px 60px;background:var(--bg);color:var(--ink);font:15px/1.6 -apple-system,"Malgun Gothic","맑은 고딕",sans-serif}
h1{font-size:21px;margin:0 0 4px}
.sub{color:var(--mute);font-size:13px}
.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;margin:12px 0;overflow-x:auto}
a{color:var(--acc)}
"""
    shown = [(INDEX[k], name) for k, name in STAGES if k != "llm"]
    p = ["<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
         "<title>걸린 시간 기록</title><style>%s%s</style></head><body class=\"tm\">" % (page_css, CSS),
         "<h1>걸린 시간 기록</h1>",
         "<p class=\"sub\">표시하기(mark.bat)를 돌릴 때마다 문서 하나에 한 줄씩 쌓입니다. 최근 것이 위에 있습니다 · 고쳐 쓴 때 %s · "
         "같은 내용이 <a href=\"times.csv\">times.csv</a>에 있습니다(엑셀에서 열 수 있고, 시간은 초 단위).</p>" % time.strftime("%Y-%m-%d %H:%M:%S"),
         "<div class=\"box\"><div class=\"tkey\">%s</div>"
         "<p class=\"sub\">막대는 한 번의 실행에서 단계마다 걸린 시간의 비율입니다. 비고에 '보관해 둔 계산 사용'이 적힌 실행은 분류기 시간이 그만큼 짧게 나온 것입니다. "
         "처음 보는 문서에 걸리는 시간을 보려면 표시하기 화면에서 '보관해 둔 계산을 쓰지 않고 처음부터 다시 계산하기'에 체크하고 만드세요. "
         "LLM에 걸리는 시간은 여기가 아니라 verify.bat 결과 화면에 나옵니다.</p>" % "".join(
             "<span><i class=\"t%d\"></i>%s</span>" % (n, name) for n, name in shown)]
    if not recs:
        p.append("<p>아직 기록이 없습니다.</p></div>")
    else:
        p.append("<table class=\"tt\"><tr><th>때</th><th>파일</th><th>모델 · 넣는 크기</th><th class=\"n\">쪽</th><th class=\"n\">점수 매긴 글</th><th class=\"n\">'예'</th>"
                 "<th>단계별 비율</th><th class=\"n\">글 뽑기</th><th class=\"n\">분류기</th><th class=\"n\">파일 만들기</th><th class=\"n\">합계</th><th>비고</th></tr>")
        for r in reversed(recs):
            t = r["timing"]
            p.append("<tr><td class=\"k\">%s</td><td>%s</td><td>%s · %s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td>%s</td>"
                     "<td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\">%s</td><td class=\"n\"><b>%s</b></td><td class=\"d\">%s</td></tr>" % (
                         esc(r["at"]), esc(r["file"]), esc(r["model"]), esc(r["view"]), t["extract"]["pages"], t["classify"]["items"], r["yes"], bar(t, True),
                         fmt(t["extract"]["sec"]), fmt(t["classify"]["sec"]), fmt(t["write"]["sec"]), fmt(r["sum"]), esc(_remark(r))))
        p.append("</table></div>")
    p.append("</body></html>")
    (out / "times.html").write_text("".join(p), encoding="utf-8")
