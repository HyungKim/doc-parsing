"""PDF/PPTX 텍스트 추출 방식 비교 프로그램.

세 가지 방식의 결과를 before/after로 나란히 보여 주는 HTML 리포트를 만든다.
  A  좌표 규칙      : 글자 좌표로 읽는 순서를 정한다 (PDF는 PyMuPDF와 pdfplumber 두 가지로 실행)
  B  Docling        : 레이아웃 분석 모델
  C  A + Docling    : Docling의 영역·순서·분류에 A의 글자와 규칙을 결합

사용법
  python compare.py 자료폴더
  python compare.py a.pdf a.pptx -o 결과폴더
  python compare.py 자료폴더 --no-docling          (Docling 없이 A만)

이름이 같은 PPTX와 PDF(예: 보고.pptx, 보고.pdf)가 함께 있으면
두 결과가 얼마나 같은지 비교하는 리포트도 만든다.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Callable, List, Optional

from docparse import report
from docparse.model import MethodResult
from docparse.pipeline import apply_rules


def log(msg: str) -> None:
    print(msg, flush=True)


def timed(result: MethodResult, fn: Callable[[], list], extra_seconds: float = 0.0) -> MethodResult:
    t0 = time.time()
    try:
        result.pages = fn()
    except Exception as exc:
        result.error = "%s: %s" % (type(exc).__name__, exc)
        traceback.print_exc()
    result.seconds = time.time() - t0 + extra_seconds
    return result


class Options:
    def __init__(self, args):
        self.images = not args.no_images
        self.include_hidden = args.include_hidden
        self.rules = {"repeat_ratio": args.repeat_ratio, "extra_keywords": None}
        if args.keywords:
            words = [w.strip() for w in args.keywords.split(",") if w.strip()]
            if words:
                self.rules["extra_keywords"] = re.compile("|".join(re.escape(w) for w in words), re.I)
        self.plumber = not args.no_pdfplumber
        self.docling = None                       # DoclingRunner 또는 None
        self.docling_error = ""


def docling_methods(opts: Options, path: Path, page_map: List[int], read_base: Callable) -> List[MethodResult]:
    from docparse import docling_method as dm

    b = MethodResult("B", "B · Docling")
    c = MethodResult("C", "C · A + Docling 결합")
    if opts.docling is None:
        b.error = c.error = opts.docling_error or "Docling을 사용하지 않도록 실행했습니다."
        return [b, c]
    try:
        regions, seconds = opts.docling.regions(str(path))
    except Exception as exc:
        traceback.print_exc()
        b.error = c.error = "%s: %s" % (type(exc).__name__, exc)
        return [b, c]
    timed(b, lambda: dm.alone(regions, page_map), seconds)
    timed(c, lambda: apply_rules(dm.hybrid(read_base(), regions, page_map), keep_order=True, **opts.rules), seconds)
    c.note = "Docling 변환 시간 포함"
    return [b, c]


def run_pdf(path: Path, opts: Options) -> report.DocRun:
    from docparse import pdf_pymupdf

    run = report.DocRun(path=str(path), name=path.name, kind="pdf")
    holder = {}

    def a_pymupdf():
        holder["doc"] = pdf_pymupdf.read(str(path))
        run.add_before("before-mu", "Before · PyMuPDF 기본 추출", holder["doc"].pages,
                       "PyMuPDF가 한 덩어리로 묶어 준 글")
        return apply_rules(holder["doc"], **opts.rules)

    run.methods.append(timed(MethodResult("A-mu", "A · 좌표 규칙 (PyMuPDF)"), a_pymupdf))
    doc = holder.get("doc")
    if doc is not None and doc.pages:
        run.aspect = doc.pages[0].width / max(doc.pages[0].height, 1.0)
        if doc.info.get("producer"):
            run.notes.append("PDF를 만든 프로그램: %s" % doc.info["producer"])

    if opts.plumber:
        def a_plumber():
            from docparse import pdf_plumber
            d = pdf_plumber.read(str(path))
            run.add_before("before-pl", "Before · pdfplumber 기본 추출", d.pages,
                           "한 줄 (pdfplumber는 줄 단위로만 줌)")
            return apply_rules(d, **opts.rules)

        run.methods.append(timed(MethodResult("A-pl", "A · 좌표 규칙 (pdfplumber)"), a_plumber))

    n = len(doc.pages) if doc is not None else 0
    run.methods.extend(docling_methods(opts, path, list(range(1, n + 1)), lambda: pdf_pymupdf.read(str(path))))
    if opts.images:
        try:
            run.images = pdf_pymupdf.page_images(str(path))
        except Exception:
            run.images = []
    return run


def run_pptx(path: Path, opts: Options, include_hidden: bool) -> report.DocRun:
    from docparse import pptx_reader

    run = report.DocRun(path=str(path), name=path.name, kind="pptx")
    holder = {}

    def a_rules():
        holder["doc"] = pptx_reader.read(str(path), include_hidden=include_hidden)
        run.add_before("before", "Before · python-pptx 기본 추출", holder["doc"].pages,
                       "도형(글상자) 하나")
        return apply_rules(holder["doc"], **opts.rules)

    run.methods.append(timed(MethodResult("A", "A · 좌표 규칙 (python-pptx)"), a_rules))
    doc = holder.get("doc")
    page_map: List[int] = []
    if doc is not None:
        page_map = doc.info.get("slide_numbers", [])
        if doc.pages:
            run.aspect = doc.pages[0].width / max(doc.pages[0].height, 1.0)
        hidden = doc.info.get("hidden", [])
        if hidden:
            run.notes.append("숨긴 슬라이드 %s번은 %s." % (
                ", ".join(str(h) for h in hidden), "포함했습니다" if include_hidden else "제외했습니다 (PDF로 저장하면 빠지는 슬라이드)"))
    run.methods.extend(docling_methods(
        opts, path, page_map, lambda: pptx_reader.read(str(path), include_hidden=include_hidden)))
    return run


def collect(inputs: List[str]) -> List[Path]:
    files: List[Path] = []
    for item in inputs:
        p = Path(item)
        if p.is_dir():
            files.extend(sorted(q for q in p.rglob("*") if q.suffix.lower() in (".pdf", ".pptx") and not q.name.startswith("~$")))
        elif p.suffix.lower() in (".pdf", ".pptx"):
            files.append(p)
        elif p.suffix.lower() == ".ppt":
            log("건너뜀(구형 .ppt는 PowerPoint에서 .pptx로 저장한 뒤 넣어 주세요): %s" % p)
        else:
            log("건너뜀(지원하지 않는 형식): %s" % p)
    return files


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")      # Windows 콘솔 한글 깨짐 방지
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="PDF/PPTX 텍스트 추출 방식 비교 (before/after 리포트 생성)")
    ap.add_argument("inputs", nargs="+", help="PDF/PPTX 파일 또는 폴더")
    ap.add_argument("-o", "--out", default="out", help="리포트를 저장할 폴더 (기본: out)")
    ap.add_argument("--no-docling", action="store_true", help="Docling(B, C 방식)을 실행하지 않음")
    ap.add_argument("--docling-models", default=None, help="미리 받아 둔 Docling 모델 폴더 (인터넷이 안 되는 PC용)")
    ap.add_argument("--no-pdfplumber", action="store_true", help="pdfplumber 비교를 생략")
    ap.add_argument("--no-images", action="store_true", help="리포트에 페이지 그림을 넣지 않음")
    ap.add_argument("--include-hidden", action="store_true", help="PPTX의 숨긴 슬라이드도 포함")
    ap.add_argument("--repeat-ratio", type=float, default=0.6, help="본문 영역의 글을 반복 문구로 볼 페이지 비율 (기본 0.6)")
    ap.add_argument("--keywords", default="", help="항상 제거할 문구를 쉼표로 구분 (예: \"사내한,Draft\")")
    args = ap.parse_args(argv)

    files = collect(args.inputs)
    if not files:
        log("처리할 PDF/PPTX 파일이 없습니다.")
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    opts = Options(args)

    footer = ""
    if not args.no_docling:
        from docparse import docling_method as dm
        reason = dm.unavailable_reason()
        if reason:
            opts.docling_error = "Docling을 불러오지 못했습니다 (%s)" % reason
            log(opts.docling_error + " → A 방식만 실행합니다.")
        else:
            log("Docling 모델을 불러오는 중...")
            try:
                opts.docling = dm.DoclingRunner(args.docling_models)
                footer = "Docling 모델을 불러오는 데 %.1f초가 걸렸습니다(프로그램을 실행할 때마다 한 번, 문서별 처리 시간에는 포함하지 않음)." % opts.docling.load_seconds
                log("  완료 (%.1f초)" % opts.docling.load_seconds)
            except Exception as exc:
                traceback.print_exc()
                opts.docling_error = "Docling 모델을 불러오지 못했습니다 (%s: %s)" % (type(exc).__name__, exc)
                log(opts.docling_error)

    pdf_by_stem = {f.stem: f for f in files if f.suffix.lower() == ".pdf"}
    runs = {}
    entries = []
    for f in files:
        log("처리 중: %s" % f)
        if f.suffix.lower() == ".pdf":
            run = run_pdf(f, opts)
        else:
            include_hidden = args.include_hidden
            twin = pdf_by_stem.get(f.stem)
            if twin is not None and not include_hidden:
                # 짝이 되는 PDF의 쪽 수가 '숨긴 슬라이드 포함' 수와 같으면 숨긴 슬라이드도 읽는다
                try:
                    from docparse import pdf_pymupdf, pptx_reader
                    hidden = pptx_reader.hidden_slide_numbers(str(f))
                    from pptx import Presentation
                    total = len(Presentation(str(f)).slides)
                    if hidden and pdf_pymupdf.page_count(str(twin)) == total:
                        include_hidden = True
                except Exception:
                    pass
            run = run_pptx(f, opts, include_hidden)
        for m in run.methods:
            state = "%.2f초" % m.seconds
            if m.error:
                state = ("건너뜀" if opts.docling is None and m.key in ("B", "C") else "실패") + ": " + m.error
            log("  %-28s %s" % (m.label, state))
        name = "%s.%s.html" % (f.stem, run.kind)
        report.write_doc_report(run, str(out_dir / name))
        report.write_json(run, str(out_dir / ("%s.%s.json" % (f.stem, run.kind))))
        runs[(f.stem, run.kind)] = run
        entries.append({"run": run, "file": name})

    for e in entries:
        run = e["run"]
        stem = Path(run.path).stem
        if run.kind == "pptx" and (stem, "pdf") in runs:
            pair_name = "%s.pptx-vs-pdf.html" % stem
            e["pair_stats"] = report.write_pair_report(run, runs[(stem, "pdf")], str(out_dir / pair_name))
            e["pair_file"] = pair_name
            for s in e["pair_stats"]:
                log("  PPTX↔PDF 일치율 %-26s %.1f%%" % (s["pdf"].label, 100 * sum(s["loose"]) / max(s["n"], 1)))

    report.write_index(entries, str(out_dir / "index.html"), footer)
    log("완료: %s" % (out_dir / "index.html").resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
