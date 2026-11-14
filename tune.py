"""읽는 순서 기준값 시험.

방식 A가 읽는 순서를 정할 때 쓰는 기준값(docparse/layout.py)은 샘플로 정한 값이다.
이 스크립트는 실제 자료에서 그 값을 하나씩 바꿔 가며 순서를 다시 정해 보고,
지금 값일 때와 순서가 달라지는 쪽이 얼마나 되는지 세어 리포트(out/tune.html)로 만든다.

  달라지는 쪽이 거의 없다     → 지금 값이 그 자료에서도 안전하다
  바로 옆 값에서도 달라진다   → 그 쪽들을 보고 어느 순서가 맞는지 확인한다

글자를 읽고 덩어리로 묶는 일은 파일마다 한 번만 하고, 순서 정하기만 값마다 다시 한다.
읽는 방법은 compare.py와 같다(PDF는 pdfplumber, PPTX는 python-pptx).

사용법
  python tune.py 자료폴더
  python tune.py a.pdf b.pptx -o 결과폴더
"""
from __future__ import annotations

import argparse
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
        for number, blocks, font in order_log:
            cases.append(PageCase(f.name, "%s.%s.html" % (f.stem, kind), number, blocks, font,
                                  layout.xy_order(blocks, font)))
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


def write_report(cases: List[PageCase], results: dict, out_dir: Path, n_files: int) -> Path:
    testable = sum(1 for c in cases if len(c.blocks) >= 2)
    kind, sentence, near_pages, any_pages = conclusion(cases, results)
    body = ["<style>%s</style>" % CSS]
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
    body.append("<p class=\"legend\">값을 조금만 바꿔도 순서가 바뀌는 쪽입니다. 왼쪽이 지금 순서, 오른쪽이 바꾼 값에서의 순서이고 "
                "<span class=\"d\">노랑</span>은 자리가 달라진 덩어리입니다. 파일 이름에 링크가 있으면 비교 리포트의 그 쪽으로 갑니다.</p>")
    shown = False
    for name, label, unit, values in PARAMS:
        allv, current, near = values_of(name, values)
        for v in near:
            changed = results[(name, v)]
            if not changed:
                continue
            shown = True
            body.append("<h3>%s: %s → %s (%d쪽)</h3>" % (esc(label), fmt(current, unit), fmt(v, unit), len(changed)))
            for i, new in changed[:MAX_DETAIL]:
                c = cases[i]
                body.append("<details><summary>%s</summary><div class=\"pair\"><div><b>지금 순서</b>%s</div>"
                            "<div><b>%s일 때</b>%s</div></div></details>"
                            % (page_ref(c, out_dir), order_list(c.base, new), fmt(v, unit), order_list(new, c.base)))
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
    path = write_report(cases, results, out_dir, len(files))
    log("완료: %s" % path.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
