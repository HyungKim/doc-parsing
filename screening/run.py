"""걸러내기 비교의 본체: 모델 네 가지 × 넣는 크기 두 가지(덩어리, 줄) × 학습 전·후의 점수를 모두 구한다."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from . import learn, models
from .items import BlockItem, DocItems, LineItem, load_docs, text_key
from .sentences import Sentence, load_sentences

VIEWS = [("block", "덩어리로 넣음"), ("agg", "줄로 넣어 덩어리로 합침"), ("line", "줄로 넣음")]
TITLE_WEIGHTS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]     # 제목을 반영할 때 나란히 견줘 보는 비율들


@dataclass
class ModelRun:
    spec: dict
    ok: bool = True
    error: str = ""
    new_items: int = 0                   # 이번에 새로 계산한 개수 (나머지는 지난 결과를 다시 씀)
    count_word: str = "개"               # 세는 말. 문장 판별 모델은 글과 기준 문장의 '쌍'을 센다
    seconds: float = 0.0
    # 글의 지문 → 점수.  before: 기준 문장만으로(학습 전), after: 정답으로 학습시킨 분류기(학습 후)
    before: Dict[str, Dict[str, float]] = field(default_factory=lambda: {"block": {}, "line": {}})
    after: Dict[str, Optional[Dict[str, float]]] = field(default_factory=lambda: {"block": None, "line": None})
    best: Dict[str, Dict[str, int]] = field(default_factory=lambda: {"block": {}, "line": {}})   # 가장 가까운 기준 문장
    train_note: Dict[str, str] = field(default_factory=lambda: {"block": "", "line": ""})
    metrics: Dict[str, Dict[str, Optional[dict]]] = field(default_factory=dict)   # 보는 방식 → {"before", "after"}
    # 쪽 제목 반영(옵션). title_w가 0이면 title_before는 비어 있고 점수는 글 점수 그대로다
    title_w: float = 0.0                 # 제목 점수를 섞는 비율
    title_before: Dict[str, float] = field(default_factory=dict)          # 제목의 지문 → 기준 문장으로 매긴 점수

    @property
    def key(self) -> str:
        return self.spec["key"]

    def _raw(self, unit: str, key: str, when: str) -> Tuple[Optional[float], str]:
        """글 점수와, 그 점수가 나온 단계(before | after)."""
        after = self.after.get(unit)
        if when != "before" and after is not None and key in after:
            return after[key], "after"
        if when == "after":
            return None, "after"
        return self.before[unit].get(key), "before"

    def score(self, unit: str, key: str, when: str = "latest") -> Optional[float]:
        """글 점수(제목 반영 없음). unit: block | line.  when: before | after | latest(학습 후가 있으면 그것, 없으면 학습 전)"""
        return self._raw(unit, key, when)[0]

    def title_score(self, title: str) -> Optional[float]:
        """쪽 제목에 매긴 점수. 학습 전이든 후든 기준 문장으로 매긴 점수를 쓴다.

        학습시킨 분류기로 제목에 점수를 매기는 것도 해 봤으나, 분류기는 문장으로 학습해서 짧은 제목에는
        기술적인 제목이라도 점수를 낮게 주었고(샘플에서 0.3~0.6), 그것을 섞으면 글 점수가 모두 끌려 내려갔다.
        """
        return self.title_before.get(text_key(title)) if title else None

    def mixed(self, unit: str, key: str, title: str, when: str = "latest", w: Optional[float] = None) -> Optional[float]:
        """제목을 반영한 점수 = (1 - w) × 글 점수 + w × 제목 점수.  w를 주지 않으면 설정된 비율, 0이면 글 점수 그대로."""
        s = self._raw(unit, key, when)[0]
        w = self.title_w if w is None else w
        if s is None or not w:
            return s
        t = self.title_score(title)
        return s if t is None else (1.0 - w) * s + w * t

    def block_score(self, b: BlockItem, when: str = "latest", w: Optional[float] = None) -> Optional[float]:
        return self.mixed("block", b.key, b.title, when, w)

    def line_score(self, b: BlockItem, l: LineItem, when: str = "latest", w: Optional[float] = None) -> Optional[float]:
        return self.mixed("line", l.key, b.title, when, w)

    def agg(self, block: BlockItem, when: str = "latest", w: Optional[float] = None) -> Optional[float]:
        """줄마다 매긴 점수를 덩어리로 합친 값: 줄 점수 가운데 가장 높은 것."""
        vals = [self.line_score(block, l, when, w) for l in block.lines]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None


@dataclass
class Result:
    out_dir: Path
    docs: List[DocItems]
    sentences: List[Sentence]
    sentences_file: Path
    labels_file: Path
    labels: Dict[str, int]
    block_labels: Dict[str, int]
    runs: List[ModelRun]
    target: float
    max_len: int
    models_dir: Path = Path("models")
    previous: Optional[dict] = None      # 기준 문장을 고치기 전의 문장과 점수 (고친 효과를 재는 데 쓴다)
    title_weight: float = 0.0            # 쪽 제목 점수를 섞는 비율 (0이면 반영하지 않음)
    titles: Dict[str, str] = field(default_factory=dict)      # 제목의 지문 → 제목 (반영할 때만 채운다)

    @property
    def blocks(self) -> List[BlockItem]:
        return [b for d in self.docs for b in d.blocks]

    def counts(self) -> dict:
        blocks = self.blocks
        lines = [l for b in blocks for l in b.lines]
        return {"docs": len(self.docs), "blocks": len(blocks), "lines": len(lines),
                "line_yes": sum(1 for l in lines if self.labels.get(l.key) == 1),
                "line_no": sum(1 for l in lines if self.labels.get(l.key) == 0),
                "block_yes": sum(1 for b in blocks if self.block_labels.get(b.key) == 1),
                "block_no": sum(1 for b in blocks if self.block_labels.get(b.key) == 0)}


def _sentence_sig(sentences: list) -> list:
    return [[bool(s["positive"]), " ".join(str(s["text"]).split())] for s in sentences]


def keep_previous(out_dir: Path, sentences: List[Sentence]) -> Optional[dict]:
    """기준 문장이 지난 실행과 달라졌으면 지난 실행의 문장과 학습 전 점수를 따로 남겨 둔다.

    남겨 둔 것은 문장을 다시 고칠 때까지 유지되어, 그동안 '고치기 전 → 지금'을 같은 정답으로 비교할 수 있다.
    """
    now = _sentence_sig([{"positive": s.positive, "text": s.text} for s in sentences])
    scores_path, keep_path = Path(out_dir) / "screen" / "scores.json", Path(out_dir) / "screen" / "before_edit.json"
    try:
        last = json.loads(scores_path.read_text(encoding="utf-8")) if scores_path.exists() else None
    except Exception:
        last = None
    if last and last.get("sentences") and _sentence_sig(last["sentences"]) != now:
        scores: Dict[str, Dict[str, Dict[str, float]]] = {}
        for d in last.get("docs", []):
            for b in d.get("blocks", []):
                for unit, item in [("block", b)] + [("line", l) for l in b.get("lines", [])]:
                    for m, v in (item.get("scores") or {}).items():
                        if v.get("before") is not None:
                            scores.setdefault(m, {"block": {}, "line": {}})[unit][item["key"]] = v["before"]
        keep = {"saved": last.get("made", ""), "sentences": last["sentences"], "scores": scores}
        keep_path.write_text(json.dumps(keep, ensure_ascii=False), encoding="utf-8")
    try:
        keep = json.loads(keep_path.read_text(encoding="utf-8")) if keep_path.exists() else None
    except Exception:
        keep = None
    if keep and _sentence_sig(keep.get("sentences") or []) != now:
        return keep
    return None


def run(out_dir: Path, root: Path, model_names: Optional[str], sentences_file: Path, labels_file: Path,
        target: float, max_len: int, download: bool, log: Callable[[str], None],
        models_dir: Optional[Path] = None, title_weight: float = 0.0) -> Result:
    docs = load_docs(out_dir)
    sentences = load_sentences(sentences_file)
    previous = keep_previous(out_dir, sentences)
    labels = learn.load_labels(labels_file)
    blocks = [b for d in docs for b in d.blocks]
    block_labels = {}
    for b in blocks:
        v = learn.block_label(b, labels)
        if v is not None:
            block_labels[b.key] = v

    # 같은 글은 한 번만 계산한다
    texts = {"block": {}, "line": {}}
    groups = {"block": {}, "line": {}}             # 글의 지문 → 그 글이 나온 문서와 쪽
    for d in docs:
        for b in d.blocks:
            texts["block"].setdefault(b.key, b.text)
            groups["block"].setdefault(b.key, "%s|%d" % (d.name, b.page))
            for l in b.lines:
                texts["line"].setdefault(l.key, l.text)
                groups["line"].setdefault(l.key, "%s|%d" % (d.name, b.page))
    titles: Dict[str, str] = {}                    # 쪽 제목 반영을 켰을 때만 제목에도 점수를 매긴다
    if title_weight:
        for b in blocks:
            if b.title.strip():
                titles.setdefault(text_key(b.title), b.title)
    every = {}
    for unit in ("block", "line"):
        every.update(texts[unit])
    keys = list(every)
    sent_texts = [s.text for s in sentences]
    positive = [s.positive for s in sentences]
    models_dir = Path(models_dir) if models_dir else models.default_models_dir(root)
    cache_dir = Path(out_dir) / "screen" / "cache"

    runs: List[ModelRun] = []
    for spec in models.pick_models(model_names):
        r = ModelRun(spec)
        runs.append(r)
        log("모델: %s" % spec["label"])
        try:
            path = models.ensure_model(spec, models_dir, log, download)
            meta = {"repo": spec["repo"], "max_len": max_len, "prefix": spec.get("prefix", "")}
            if spec["kind"] == "embed":
                store = models.Store(cache_dir / (spec["key"] + ".npz"), meta)
                vecs, new, sec = models.embed(spec, path, [every[k] for k in keys], store, max_len, log)
                svecs, new_s, sec_s = models.embed(spec, path, sent_texts, store, max_len, log)
                by_key = {k: vecs[i] for i, k in enumerate(keys)}
                if titles:
                    tvecs, new_t, sec_t = models.embed(spec, path, list(titles.values()), store, max_len, log)
                    score_t, _ = models.zero_shot_from_vectors(tvecs, svecs, positive, spec["temp"])
                    r.title_w, r.title_before = title_weight, {k: float(v) for k, v in zip(titles, score_t)}
                    new, sec = new + new_t, sec + sec_t
                store.save()
                r.new_items, r.seconds = new + new_s, sec + sec_s
                for unit in ("block", "line"):
                    ks = list(texts[unit])
                    if not ks:
                        continue
                    score, best = models.zero_shot_from_vectors(np.stack([by_key[k] for k in ks]), svecs, positive, spec["temp"])
                    r.before[unit] = {k: float(v) for k, v in zip(ks, score)}
                    r.best[unit] = {k: int(v) for k, v in zip(ks, best)}
                    # 학습 후: 정답으로 분류기를 학습시켜 다시 점수를 매긴다
                    unit_labels = block_labels if unit == "block" else {k: v for k, v in labels.items() if k in texts["line"]}
                    trained, why = learn.train({k: by_key[k] for k in ks}, unit_labels, groups[unit])
                    r.train_note[unit] = why
                    if trained is not None:
                        r.after[unit] = trained["scores"]
                        save_classifier(labels_file.parent / "classifiers" / ("%s__%s.json" % (spec["key"], unit)), spec, unit, trained)
            else:
                store = models.Store(cache_dir / (spec["key"] + ".npz"), meta)
                pairs, new, sec = models.nli(path, [every[k] for k in keys], sent_texts, store, max_len, log)
                if titles:
                    tpairs, new_t, sec_t = models.nli(path, list(titles.values()), sent_texts, store, max_len, log)
                    score_t, _ = models.zero_shot_from_nli(tpairs, positive)
                    r.title_w, r.title_before = title_weight, {k: float(v) for k, v in zip(titles, score_t)}
                    new, sec = new + new_t, sec + sec_t
                store.save()
                r.new_items, r.seconds, r.count_word = new, sec, "쌍"
                index = {k: i for i, k in enumerate(keys)}
                for unit in ("block", "line"):
                    ks = list(texts[unit])
                    if not ks:
                        continue
                    score, best = models.zero_shot_from_nli(pairs[[index[k] for k in ks]], positive)
                    r.before[unit] = {k: float(v) for k, v in zip(ks, score)}
                    r.best[unit] = {k: int(v) for k, v in zip(ks, best)}
                    r.train_note[unit] = "문장 판별 모델은 정답으로 학습시키지 않습니다(기준 문장만 씀)"
            if r.new_items:
                log("  새로 계산 %d%s, %.1f초 (1%s에 %.2f초)" % (r.new_items, r.count_word, r.seconds, r.count_word, r.seconds / r.new_items))
            else:
                log("  지난 계산 결과를 다시 씀")
        except models.ModelMissing as exc:
            r.ok, r.error = False, str(exc)
            log("  건너뜀: %s" % exc)
        except Exception as exc:                   # 한 모델이 실패해도 나머지는 계속한다
            r.ok, r.error = False, "%s: %s" % (type(exc).__name__, exc)
            log("  실패: %s" % r.error)

    res = Result(Path(out_dir), docs, sentences, Path(sentences_file), Path(labels_file), labels, block_labels, runs, target, max_len,
                 models_dir, previous, float(title_weight), titles)
    for r in runs:
        if r.ok:
            r.metrics = measure_all(res, r)
    return res


def _items(res: Result, r: ModelRun, view: str, when: str, w: Optional[float] = None) -> List[tuple]:
    """그 보는 방식의 항목마다 (정답, 점수). 항목 순서는 언제나 같아서 서로 짝지을 수 있다. w: 제목을 섞는 비율(없으면 설정값)"""
    blocks = res.blocks
    if view == "line":
        return [(res.labels.get(l.key), r.line_score(b, l, when, w)) for b in blocks for l in b.lines]
    if view == "block":
        return [(res.block_labels.get(b.key), r.block_score(b, when, w)) for b in blocks]
    return [(res.block_labels.get(b.key), r.agg(b, when, w)) for b in blocks]


def _measure(items: List[tuple], target: float) -> Optional[dict]:
    scored = [(y, s) for y, s in items if s is not None]
    return learn.measure([y for y, _ in scored if y is not None], [s for y, s in scored if y is not None],
                         [s for _, s in scored], target)


def _pair_gain(first: List[tuple], second: List[tuple], target: float) -> Optional[dict]:
    """같은 항목에 매긴 두 점수(앞 → 뒤)를 짝지어 개선 정도를 구한다."""
    pairs = [(y, x, z) for (y, x), (_, z) in zip(first, second) if x is not None and z is not None]
    labeled = [(y, x, z) for y, x, z in pairs if y is not None]
    return learn.gain([y for y, _, _ in labeled], [x for _, x, _ in labeled], [z for _, _, z in labeled],
                      [x for _, x, _ in pairs], [z for _, _, z in pairs], target)


def measure_all(res: Result, r: ModelRun) -> Dict[str, Dict[str, Optional[dict]]]:
    """보는 방식 세 가지 × 학습 전·후의 수치. 쪽 제목 반영을 켰으면 모든 수치는 제목을 반영한 점수로 잰다."""
    out: Dict[str, Dict[str, Optional[dict]]] = {}
    blocks = res.blocks
    lines = [l for b in blocks for l in b.lines]
    for view, _ in VIEWS:
        out[view] = {}
        has_after = r.after["line" if view != "block" else "block"] is not None
        before = _items(res, r, view, "before")
        after = _items(res, r, view, "after") if has_after else None
        out[view]["before"] = _measure(before, res.target)
        out[view]["after"] = _measure(after, res.target) if has_after else None
        # 개선 정도: 같은 항목에 매긴 학습 전 점수와 학습 후 점수를 짝지어 비교한다
        out[view]["gain"] = _pair_gain(before, after, res.target) if out[view]["after"] is not None else None

        # 기준 문장을 고친 효과: 고치기 전 문장으로 매긴 점수와 지금 문장으로 매긴 점수를 짝지어 비교한다
        # (둘 다 학습 전의 글 점수. 제목 반영은 넣지 않는다)
        out[view]["edit"] = None
        old = ((res.previous or {}).get("scores") or {}).get(r.key)
        if old:
            def old_score(item, view=view):
                if view == "block":
                    return old["block"].get(item.key)
                if view == "line":
                    return old["line"].get(item.key)
                vals = [old["line"].get(l.key) for l in item.lines]
                return max(vals) if vals and all(v is not None for v in vals) else None
            things = lines if view == "line" else blocks
            raw = _items(res, r, view, "before", 0.0)
            out[view]["edit"] = _pair_gain([(y, old_score(t)) for t, (y, _) in zip(things, raw)], raw, res.target)

        # 쪽 제목을 반영한 효과: 글 점수만(반영 전)과 제목을 섞은 점수(반영 후)를 짝지어 비교하고, 비율을 바꿔 가며 견준다
        out[view]["title"] = None
        if r.title_w and r.title_before:
            out[view]["title"] = {}
            for when in ("before", "after"):
                if when == "after" and not has_after:
                    out[view]["title"][when] = None
                    continue
                raw = _items(res, r, view, when, 0.0)
                sweep = []
                for w in sorted(set(TITLE_WEIGHTS) | {round(r.title_w, 4)}):
                    m = _measure(raw if not w else _items(res, r, view, when, w), res.target)
                    sweep.append({"w": w, "auc": m["auc"] if m else None, "pass": m["tuned"]["pass"] if m else None})
                out[view]["title"][when] = {"gain": _pair_gain(raw, before if when == "before" else after, res.target), "sweep": sweep}
    return out


def save_classifier(path: Path, spec: dict, unit: str, trained: dict) -> None:
    """학습시킨 분류기를 파일로 남긴다(다음 단계에서 그대로 쓸 수 있게)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"model": spec["key"], "repo": spec["repo"], "unit": unit, "prefix": spec.get("prefix", ""),
            "trained": time.strftime("%Y-%m-%d %H:%M:%S"), "folds": trained["folds"], **trained["model"]}
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_scores(res: Result, path: Path) -> None:
    """항목마다의 점수를 자료로 남긴다(정답 붙이는 화면과 다음 단계에서 쓴다)."""
    ok = [r for r in res.runs if r.ok]
    rnd = lambda v: None if v is None else round(v, 4)
    weighted = bool(res.title_weight)

    def both(get) -> dict:
        """모델마다 {"before", "after"}. get(모델, 단계) → 점수"""
        return {r.key: {"before": rnd(get(r, "before")), "after": rnd(get(r, "after"))} for r in ok}

    docs = []
    for d in res.docs:
        blocks = []
        for b in d.blocks:
            lines = []
            for l in b.lines:
                # scores 는 언제나 글 점수(제목 반영 없음). 제목을 반영한 점수는 final 에 따로 적는다
                item = {"id": l.id, "key": l.key, "label": res.labels.get(l.key), "text": l.text,
                        "scores": both(lambda r, when, l=l: r.score("line", l.key, when))}
                if weighted:
                    item["final"] = both(lambda r, when, l=l: r.line_score(b, l, when))
                lines.append(item)
            block = {"id": b.id, "page": b.page, "kind": b.kind, "key": b.key, "label": res.block_labels.get(b.key), "text": b.text,
                     "scores": both(lambda r, when: r.score("block", b.key, when)),
                     "scores_from_lines": both(lambda r, when: r.agg(b, when, 0.0) if when == "before" or r.after["line"] is not None else None)}
            if weighted:
                block["title"] = b.title
                block["title_scores"] = {r.key: rnd(r.title_score(b.title)) for r in ok}
                block["final"] = both(lambda r, when: r.block_score(b, when))
                block["final_from_lines"] = both(lambda r, when: r.agg(b, when) if when == "before" or r.after["line"] is not None else None)
            block["lines"] = lines
            blocks.append(block)
        docs.append({"file": d.name, "kind": d.kind, "blocks": blocks})
    data = {"made": time.strftime("%Y-%m-%d %H:%M:%S"), "title_weight": res.title_weight,
            "sentences": [{"name": s.name, "positive": s.positive, "text": s.text} for s in res.sentences],
            "models": [{"key": r.key, "label": r.spec["label"], "kind": r.spec["kind"], "ok": r.ok, "error": r.error,
                        "metrics": r.metrics} for r in res.runs],
            "target_recall": res.target, "docs": docs}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
