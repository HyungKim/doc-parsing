"""표시한 결과물 만들기: 원본 사본(PDF, PPTX)과 요약 화면(HTML)을 out/mark 에 쓴다."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from . import core
from .page import write_page

METHODS = [("annot", "형광펜 주석 (지울 수 있음)"), ("paint", "쪽에 직접 칠하기 (어느 프로그램에서나 보임)")]


def mark_dir(cfg) -> Path:
    return Path(cfg.out_dir) / "mark"


def make(scorer: core.Scorer, ex: core.Extracted, model_key: str, view: str, stage: str, threshold: float,
         method: str, log: Callable[[str], None], scores: Optional[dict] = None, threshold_note: str = "") -> dict:
    """고른 조합으로 문서 하나를 표시한다. 반환: {"name", "yes", "total", "unit", "marked", "page", "notes"}

    marked: 표시한 원본 사본의 파일 이름(만들지 못했으면 빈 글), page: 요약 화면의 파일 이름. 둘 다 out/mark 안에 있다.
    """
    from screening import models

    cfg = scorer.cfg
    threshold = core.safe_threshold(threshold)
    if scores is None:
        scores = scorer.score(ex, model_key, view, stage, log)
    marks = core.pick_marks(ex, scores, view, threshold)
    info = core.summary(ex, scores, view, threshold)
    out = mark_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    stem = core.out_stem(ex, model_key, view, stage)
    notes, marked_name = [], ""
    if not marks:
        notes.append("문턱 이상인 글이 없어 표시한 사본은 만들지 않았습니다. 문턱을 낮추거나 다른 모델·크기를 골라 보세요.")
    else:
        target = out / ("%s.%s" % (stem, ex.kind))
        try:
            if ex.kind == "pdf":
                from .pdf_mark import mark_pdf
                st = mark_pdf(ex.path, target, marks, method)
                loose = sum(1 for m in marks if not m.exact)
                if loose:
                    notes.append("줄이 놓인 자리를 알 수 없는 %d줄(표 안의 줄 등)은 그 줄이 든 덩어리 전체에 표시했습니다. 정확한 줄은 아래 글에서 볼 수 있습니다." % loose)
            else:
                from .pptx_mark import mark_pptx
                st = mark_pptx(ex.path, target, marks, ex.slide_numbers)
                word = "줄" if view == "line" else "덩어리"
                notes.append("PPTX 표시: 글자에 형광펜 색을 넣은 %s %d개, 표이거나 같은 글을 찾지 못해 덩어리 자리에 네모를 얹은 %s %d개. "
                             "형광펜 색은 PowerPoint 2019 이상(또는 365)에서 보입니다." % (word, st["text"], word, st["fallback"]))
            if st.get("skipped"):
                notes.append("쪽을 찾지 못해 표시하지 못한 것 %d개" % st["skipped"])
            marked_name = target.name
        except Exception as exc:                    # 원본에 표시하지 못해도 요약 화면은 만든다
            notes.append("원본 사본에는 표시하지 못했습니다 (%s: %s). 아래 글에서는 볼 수 있습니다." % (type(exc).__name__, str(exc)[:200]))
    page_name = "%s.%s.html" % (stem, ex.kind)       # 이름이 같은 PDF와 PPTX의 화면이 서로 덮어쓰지 않게 종류를 붙인다
    made = [{"label": marked_name, "href": marked_name}] if marked_name else []
    settings = {"model": models.MODEL_BY_KEY[model_key]["label"], "stage": stage, "classifier": scores.get("classifier"),
                "title_weight": float(cfg.title_weight or 0.0), "threshold_note": threshold_note, "method": method}
    write_page(ex, scores, view, threshold, marks, settings, out / page_name, made, notes)
    return {"name": ex.name, "yes": info["yes"], "total": info["total"], "unit": info["unit"],
            "marked": marked_name, "page": page_name, "notes": notes}
