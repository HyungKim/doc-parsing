"""표시하기의 계산 부분: 문서에서 글과 자리를 뽑고, 고른 모델·크기로 점수를 매기고, 표시할 것을 추린다.

학습·시험·평가(screen.py, label.py)와는 따로 돈다. 이 모듈은
    out 폴더의 문서 목록, 정답(labels), 분류기(labels/classifiers)를 읽기만 하고 고치지 않는다.
    새로 계산한 임베딩은 out/mark/cache 에만 적는다(걸러내기 쪽 저장소 out/screen/cache 는 읽기만 한다).

글을 뽑는 방법은 1단계(compare.py)의 기본 설정과 같아서, 같은 문서라면 학습 때와 똑같은 덩어리와 줄이 나온다.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from screening.items import DocItems, doc_from_units, text_key

# 넣는 크기. 비교 화면(걸러내기)의 '보는 방식'과 같은 세 가지
VIEWS = [("block", "덩어리로 넣음", "덩어리"), ("agg", "줄로 넣어 덩어리로 합침", "줄합침"), ("line", "줄로 넣음", "줄")]
VIEW_NAME = {k: name for k, name, _ in VIEWS}
VIEW_SHORT = {k: short for k, _, short in VIEWS}
STAGES = [("after", "학습한 분류기"), ("before", "기준 문장 (학습 전)")]

# 1단계(compare.py)의 기본 설정. 학습 때와 같은 글이 나오게 같은 값을 쓴다
RULES = {"repeat_ratio": 0.6, "extra_keywords": None, "min_chars": 5, "need_korean": True}


@dataclass
class Extracted:
    """문서 하나에서 뽑은 글과 그 자리."""
    path: Path
    name: str                                   # 보고서.pdf
    kind: str                                   # pdf | pptx
    doc: Optional[DocItems]                     # 덩어리와 줄(걸러내기와 같은 모양). 글이 없으면 None
    pages: list = field(default_factory=list)   # 1단계의 쪽별 결과(PageOut)
    aspect: float = 1.33                        # 쪽의 가로/세로
    block_box: Dict[str, tuple] = field(default_factory=dict)    # 덩어리 id → 자리 (쪽 크기 대비 0~1: x0, y0, x1, y1)
    line_rows: Dict[str, list] = field(default_factory=dict)     # 줄 id → 그 줄을 이룬 원래 줄들의 자리. 모르면 없음
    slide_numbers: List[int] = field(default_factory=list)       # PPTX: 쪽 번호(1부터) → 파일 안의 실제 슬라이드 번호
    titles: Dict[int, str] = field(default_factory=dict)         # 쪽 번호 → 제목

    @property
    def counts(self) -> dict:
        blocks = self.doc.blocks if self.doc else []
        return {"pages": len(self.pages), "blocks": len(blocks), "lines": sum(len(b.lines) for b in blocks)}


def extract(path: Path) -> Extracted:
    """PDF나 PPTX에서 글(덩어리, 줄)과 자리를 뽑는다. 1단계와 같은 규칙을 쓴다."""
    from docparse import units as units_mod
    from docparse.pipeline import apply_rules

    path = Path(path)
    kind = path.suffix.lower().lstrip(".")
    if kind == "pdf":
        from docparse import pdf_plumber
        doc = pdf_plumber.read(str(path))
    elif kind == "pptx":
        from docparse import pptx_reader
        doc = pptx_reader.read(str(path), include_hidden=False)
    else:
        raise ValueError("PDF나 PPTX 파일만 넣을 수 있습니다: %s" % path.name)
    pages = apply_rules(doc, **RULES)
    units = units_mod.build_units(pages)
    items = doc_from_units({"file": path.name, "kind": kind, "units": units}, "%s.%s.units.json" % (path.stem, kind))
    ex = Extracted(path=path, name=path.name, kind=kind, doc=items, pages=pages)
    if doc.pages:
        ex.aspect = doc.pages[0].width / max(doc.pages[0].height, 1.0)
    ex.slide_numbers = list(doc.info.get("slide_numbers", [])) if kind == "pptx" else []
    for p in pages:
        ex.titles[p.number] = p.title
        for n, b in enumerate(p.blocks, 1):
            bid = "p%d-b%d" % (p.number, n)
            ex.block_box[bid] = tuple(b.box)
            # 줄의 자리: PDF의 글 덩어리에서만 안다. PPTX는 글상자 안에서 줄이 어디에 놓이는지 알 수 없다
            rows = getattr(b, "line_rows", None) or []
            texts = b.text.split("\n")
            if kind != "pdf" or b.kind != "text" or len(rows) != len(texts):
                continue
            k = 0
            for j, t in enumerate(texts):          # 단위 파일(units.build_units)이 줄 번호를 매기는 방법과 같게 센다
                if not t.strip():
                    continue
                k += 1
                if rows[j]:
                    ex.line_rows["%s-l%d" % (bid, k)] = [tuple(r) for r in rows[j]]
    return ex


# ---------------------------------------------------------------- 분류기와 문턱

def classifier_file(labels_file: Path, model_key: str, unit: str) -> Path:
    return Path(labels_file).parent / "classifiers" / ("%s__%s.json" % (model_key, unit))


def load_classifier(labels_file: Path, model_key: str, unit: str) -> Optional[dict]:
    """학습해 둔 분류기(로지스틱 회귀의 가중치). 없거나 읽을 수 없으면 None"""
    path = classifier_file(labels_file, model_key, unit)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("coef") or "intercept" not in data:
        return None
    return data


def load_thresholds(labels_file: Path) -> dict:
    """학습할 때 남긴 문턱값(labels/classifiers/thresholds.json). 없으면 빈 것"""
    path = Path(labels_file).parent / "classifiers" / "thresholds.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def choices(cfg) -> dict:
    """화면에서 고를 수 있는 것들: 모델(파일이 있는 것만), 크기마다 분류기가 있는지, 학습 때 남긴 문턱."""
    from screening import models

    saved = load_thresholds(cfg.labels)
    same_title = abs(float(saved.get("title_weight", 0.0) or 0.0) - float(cfg.title_weight or 0.0)) < 1e-9
    out = []
    for spec in models.MODELS:
        if spec["kind"] != "embed":
            continue
        ready = models.is_ready(spec, cfg.models_dir)
        trained = {}
        for unit in ("block", "line"):
            c = load_classifier(cfg.labels, spec["key"], unit)
            trained[unit] = None if c is None else {"trained": c.get("trained", ""), "yes": c.get("yes"), "no": c.get("no")}
        thr = (saved.get("models") or {}).get(spec["key"]) or {} if same_title else {}
        out.append({"key": spec["key"], "label": spec["label"], "note": spec.get("note", ""), "ready": ready,
                    "trained": trained, "thresholds": thr})
    return {"models": out, "views": [{"key": k, "label": name} for k, name, _ in VIEWS],
            "stages": [{"key": k, "label": name} for k, name in STAGES],
            "target": saved.get("target"), "thresholds_made": saved.get("made", ""),
            "title_weight": float(cfg.title_weight or 0.0)}


# ---------------------------------------------------------------- 점수 매기기

class _TwoStores:
    """계산해 둔 임베딩을 걸러내기 쪽 저장소에서도 찾아 쓰되, 새로 계산한 것은 표시하기 쪽 저장소에만 적는다."""

    def __init__(self, own, shared):
        self.own, self.shared = own, shared

    def has(self, key: str) -> bool:
        return self.own.has(key) or self.shared.has(key)

    def get(self, key: str):
        return self.own.get(key) if self.own.has(key) else self.shared.get(key)

    def put(self, key: str, row) -> None:
        self.own.put(key, row)

    def save(self) -> None:
        self.own.save()


class Scorer:
    """고른 모델·크기·판단 방법으로 문서에 점수를 매긴다. 불러온 저장소는 들고 있다가 다시 쓴다."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._stores: Dict[str, _TwoStores] = {}

    def _store(self, spec: dict) -> _TwoStores:
        from screening import models
        if spec["key"] not in self._stores:
            meta = {"repo": spec["repo"], "max_len": self.cfg.max_len, "prefix": spec.get("prefix", "")}
            out = Path(self.cfg.out_dir)
            self._stores[spec["key"]] = _TwoStores(models.Store(out / "mark" / "cache" / (spec["key"] + ".npz"), meta),
                                                   models.Store(out / "screen" / "cache" / (spec["key"] + ".npz"), meta))
        return self._stores[spec["key"]]

    def score(self, ex: Extracted, model_key: str, view: str, stage: str, log: Callable[[str], None]) -> dict:
        """반환: {"block": {덩어리 id: 점수}, "line": {줄 id: 점수}, "new": 새로 계산한 글 수, "seconds": 초, "classifier": 분류기 정보}

        view가 block이면 덩어리 점수만, agg면 줄 점수와 그 최댓값인 덩어리 점수, line이면 줄 점수만 있다.
        쪽 제목 반영이 켜져 있으면(설정 파일의 title_weight) 걸러내기와 같은 식으로 제목 점수를 섞는다.
        """
        import numpy as np
        from screening import models
        from screening.sentences import load_sentences

        if view not in VIEW_NAME:
            raise ValueError("넣는 크기를 알 수 없습니다: %s" % view)
        if stage not in ("after", "before"):
            raise ValueError("판단 방법을 알 수 없습니다: %s" % stage)
        spec = models.MODEL_BY_KEY.get(model_key)
        if spec is None or spec["kind"] != "embed":
            raise ValueError("고를 수 없는 모델입니다: %s" % model_key)
        if ex.doc is None:
            return {"block": {}, "line": {}, "new": 0, "seconds": 0.0, "classifier": None}
        unit = "block" if view == "block" else "line"
        clf = None
        if stage == "after":
            clf = load_classifier(self.cfg.labels, model_key, unit)
            if clf is None:
                raise ValueError("%s 모델의 %s 분류기가 아직 없습니다. label.bat 에서 정답을 붙이고 '학습하고 결과 보기'를 먼저 해 주세요."
                                 % (spec["label"], "덩어리" if unit == "block" else "줄"))
        path = models.ensure_model(spec, self.cfg.models_dir, log, False)
        store = self._store(spec)
        items = [(b.id, b.text) for b in ex.doc.blocks] if unit == "block" else [(l.id, l.text) for b in ex.doc.blocks for l in b.lines]
        vecs, new, sec = models.embed(spec, path, [t for _, t in items], store, self.cfg.max_len, log)
        w = float(self.cfg.title_weight or 0.0)
        need_sentences = stage == "before" or w > 0
        svecs = positive = None
        if need_sentences:
            sents = load_sentences(self.cfg.sentences)
            positive = [s.positive for s in sents]
            svecs, new_s, sec_s = models.embed(spec, path, [s.text for s in sents], store, self.cfg.max_len, log)
            new, sec = new + new_s, sec + sec_s
        if stage == "after":
            coef = np.asarray(clf["coef"], dtype=np.float64)
            if len(items) and coef.shape[0] != vecs.shape[1]:
                raise ValueError("분류기와 모델의 크기가 맞지 않습니다(분류기 %d, 모델 %d). 다시 학습해 주세요." % (coef.shape[0], vecs.shape[1]))
            with np.errstate(all="ignore"):         # 일부 PC의 numpy가 곱셈에서 내는 뜻 없는 경고를 막는다(값은 같다)
                raw = vecs.astype(np.float64) @ coef + float(clf["intercept"]) if len(items) else np.zeros(0)
                scores = 1.0 / (1.0 + np.exp(-raw))
        else:
            scores = models.zero_shot_from_vectors(vecs, svecs, positive, spec["temp"])[0] if len(items) else np.zeros(0)
        by_id = {i: float(s) for (i, _), s in zip(items, scores)}
        if w > 0:                                   # 쪽 제목 반영: (1 - w) × 글 점수 + w × 제목 점수. 제목 점수는 늘 기준 문장으로 매긴다
            titles = sorted({t for t in ex.titles.values() if t})
            if titles:
                tvecs, new_t, sec_t = models.embed(spec, path, titles, store, self.cfg.max_len, log)
                new, sec = new + new_t, sec + sec_t
                tscore = dict(zip(titles, (float(v) for v in models.zero_shot_from_vectors(tvecs, svecs, positive, spec["temp"])[0])))
                page_of = {b.id: b.page for b in ex.doc.blocks}
                page_of.update({l.id: b.page for b in ex.doc.blocks for l in b.lines})
                for i in list(by_id):
                    t = tscore.get(ex.titles.get(page_of[i], ""))
                    if t is not None:
                        by_id[i] = (1.0 - w) * by_id[i] + w * t
        store.save()
        out = {"block": {}, "line": {}, "new": new, "seconds": sec,
               "classifier": None if clf is None else {"trained": clf.get("trained", ""), "yes": clf.get("yes"), "no": clf.get("no")}}
        if unit == "block":
            out["block"] = by_id
        else:
            out["line"] = by_id
            if view == "agg":
                for b in ex.doc.blocks:
                    vals = [by_id[l.id] for l in b.lines if l.id in by_id]
                    if vals:
                        out["block"][b.id] = max(vals)
        return out


# ---------------------------------------------------------------- 표시할 것 추리기

@dataclass
class Mark:
    page: int                 # 쪽 번호(뽑은 순서, 1부터)
    unit: str                 # block | line
    id: str
    block_id: str
    text: str
    score: float
    box: tuple                # 그 글이 든 덩어리의 자리
    rows: List[tuple]         # 형광 표시할 자리들. 줄의 자리를 알면 줄마다 하나씩, 모르면 덩어리 자리 하나
    exact: bool               # rows가 그 글의 자리를 정확히 가리키는가(False면 덩어리 전체로 대신한 것)
    table: bool = False


def _union(rows: List[tuple]) -> tuple:
    return (min(r[0] for r in rows), min(r[1] for r in rows), max(r[2] for r in rows), max(r[3] for r in rows))


def pick_marks(ex: Extracted, scores: dict, view: str, threshold: float) -> List[Mark]:
    """점수가 문턱 이상인 것. view가 line이면 줄을, 아니면 덩어리를 고른다. 쪽·읽는 순서대로."""
    out: List[Mark] = []
    if ex.doc is None:
        return out
    for b in ex.doc.blocks:
        box = ex.block_box.get(b.id) or (0.0, 0.0, 1.0, 1.0)
        if view == "line":
            for l in b.lines:
                s = scores["line"].get(l.id)
                if s is None or s < threshold:
                    continue
                rows = ex.line_rows.get(l.id)
                out.append(Mark(b.page, "line", l.id, b.id, l.text, s, box, list(rows) if rows else [box], bool(rows), b.kind == "table"))
        else:
            s = scores["block"].get(b.id)
            if s is None or s < threshold:
                continue
            rows: List[tuple] = []
            known = b.kind != "table" and bool(b.lines) and all(l.id in ex.line_rows for l in b.lines)
            if known:                               # 글이 있는 줄마다 칠해야 형광펜처럼 보인다
                for l in b.lines:
                    rows.extend(ex.line_rows[l.id])
            out.append(Mark(b.page, "block", b.id, b.id, b.text, s, box, rows if known else [box], True, b.kind == "table"))
    return out


def summary(ex: Extracted, scores: dict, view: str, threshold: float) -> dict:
    """문턱에서 '예'로 본 수와 전체 수."""
    unit = "line" if view == "line" else "block"
    vals = list(scores[unit].values())
    return {"unit": unit, "total": len(vals), "yes": sum(1 for v in vals if v >= threshold)}


def safe_threshold(value) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError("문턱은 0과 1 사이의 숫자여야 합니다")
    if math.isnan(v) or not 0.0 <= v <= 1.0:
        raise ValueError("문턱은 0과 1 사이의 숫자여야 합니다")
    return v


def out_stem(ex: Extracted, model_key: str, view: str, stage: str) -> str:
    """결과 파일 이름의 앞부분. 모델과 크기를 넣어, 여러 조합으로 만든 결과가 서로 덮어쓰지 않게 한다."""
    return "%s.%s.%s%s.marked" % (ex.path.stem, model_key, VIEW_SHORT[view], "" if stage == "after" else ".기준문장")


__all__ = ["Extracted", "Mark", "Scorer", "VIEWS", "VIEW_NAME", "STAGES", "choices", "extract", "pick_marks", "summary",
           "safe_threshold", "out_stem", "load_classifier", "load_thresholds", "text_key"]
