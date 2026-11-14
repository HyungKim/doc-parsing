"""정답(사람이 붙인 예/아니오)을 읽고 쓰고, 분류기를 학습시키고, 결과를 수치로 잰다.

정답은 줄 단위로 붙인다. 덩어리의 정답은 그 줄들에서 따온다.
    줄 가운데 하나라도 '예'           → 덩어리도 '예'
    모든 줄이 '아니오'                → 덩어리도 '아니오'
    정답이 안 붙은 줄이 남아 있고 '예'가 없음 → 아직 모름
정답은 글의 지문(text_key)으로 적어 두므로 추출을 다시 해도 유지된다.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .items import BlockItem

MIN_EACH = 4          # 분류기를 학습시키려면 '예'와 '아니오'가 각각 이만큼은 있어야 한다


# ---------------------------------------------------------------- 정답 파일

def load_labels(path: Path) -> Dict[str, int]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {k: int(v["label"]) for k, v in (data.get("labels") or {}).items() if v.get("label") in (0, 1)}


def write_labels(path: Path, items: List[Tuple[str, Optional[int], str]]) -> int:
    """정답 여러 개를 한 번에 적거나(label 0/1) 지운다(label None). items: (글의 지문, 정답, 글).

    파일은 통째로 바꿔 써서 중간에 깨지지 않게 한다. 반환: 정답 개수
    """
    path = Path(path)
    data = {"version": 1, "labels": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                          # 깨진 파일은 덮어쓰지 않고 옆에 남겨 둔다
            path.replace(path.with_suffix(".broken-%s.json" % time.strftime("%Y%m%d-%H%M%S")))
            data = {"version": 1, "labels": {}}
    labels = data.setdefault("labels", {})
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for key, label, text in items:
        if label is None:
            labels.pop(key, None)
        else:
            labels[key] = {"label": int(label), "text": text, "updated": now}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return len(labels)


def write_label(path: Path, key: str, label: Optional[int], text: str = "") -> int:
    return write_labels(path, [(key, label, text)])


def block_label(block: BlockItem, labels: Dict[str, int]) -> Optional[int]:
    got = [labels.get(l.key) for l in block.lines]
    if any(v == 1 for v in got):
        return 1
    if got and all(v == 0 for v in got):
        return 0
    return None


# ---------------------------------------------------------------- 수치

def auc(y: np.ndarray, s: np.ndarray) -> Optional[float]:
    """순위 정확도: '예'인 것을 '아니오'인 것보다 높은 점수로 줄 세운 정도. 1이면 완벽, 0.5면 무작위."""
    pos = y == 1
    n_pos, n_neg = int(pos.sum()), int((y == 0).sum())
    if not n_pos or not n_neg:
        return None
    # 점수의 순위로 계산한다(같은 점수끼리는 평균 순위). 모든 쌍을 견주는 것과 값이 같고, 정답이 많아도 빠르다
    _, inverse, counts = np.unique(s, return_inverse=True, return_counts=True)
    ranks = (np.cumsum(counts) - (counts - 1) / 2.0)[inverse]
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def recall_threshold(y: np.ndarray, s: np.ndarray, target: float) -> Optional[float]:
    """'예' 가운데 target 비율 이상을 통과시키는 가장 높은 문턱값."""
    pos = np.sort(s[y == 1])[::-1]
    if not len(pos):
        return None
    need = max(1, int(math.ceil(target * len(pos) - 1e-9)))
    return float(pos[need - 1])


def at_threshold(y: np.ndarray, s: np.ndarray, everything: np.ndarray, thr: float) -> dict:
    passed = s >= thr
    tp = int((passed & (y == 1)).sum())
    return {
        "threshold": float(thr),
        "recall": tp / max(int((y == 1).sum()), 1),                 # 찾아낸 비율: '예' 가운데 통과한 것
        "precision": tp / max(int(passed.sum()), 1),                # 맞힌 비율: 통과한 것 가운데 '예'
        "pass": float((everything >= thr).mean()) if len(everything) else 0.0,   # 통과 비율: 전체 항목 가운데 통과한 것
    }


def measure(y: List[int], s: List[float], everything: List[float], target: float) -> Optional[dict]:
    """정답이 붙은 항목의 점수 s와 정답 y로 결과를 잰다. everything은 정답 유무와 상관없이 전체 항목의 점수."""
    y_, s_, all_ = np.asarray(y, dtype=int), np.asarray(s, dtype=float), np.asarray(everything, dtype=float)
    if not len(y_) or not (y_ == 1).any() or not (y_ == 0).any():
        return None
    thr = recall_threshold(y_, s_, target)
    return {"n": int(len(y_)), "yes": int((y_ == 1).sum()), "no": int((y_ == 0).sum()), "auc": auc(y_, s_),
            "half": at_threshold(y_, s_, all_, 0.5), "tuned": at_threshold(y_, s_, all_, thr)}


def gain(y: List[int], before: List[float], after: List[float], all_before: List[float], all_after: List[float],
         target: float, rounds: int = 1000) -> Optional[dict]:
    """학습 전 → 후의 개선 정도. 같은 항목들에 대해 매긴 두 점수를 짝지어 비교한다.

    순위 정확도 차이와 함께, 그 차이가 정답 표본에 따라 얼마나 흔들리는지(95% 범위)를 구한다.
    범위는 정답이 붙은 항목을 '예'와 '아니오'별로 다시 뽑기를 rounds번 되풀이해 얻는다(붓스트랩).
    범위 전체가 0보다 크면 표본이 달라져도 나아진 것이고, 0을 걸치면 우연일 수 있다.
    """
    y_, b_, a_ = np.asarray(y, dtype=int), np.asarray(before, dtype=float), np.asarray(after, dtype=float)
    if not len(y_) or not (y_ == 1).any() or not (y_ == 0).any():
        return None
    base, new = auc(y_, b_), auc(y_, a_)
    pos, neg = np.where(y_ == 1)[0], np.where(y_ == 0)[0]
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(rounds):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        diffs.append(auc(y_[idx], a_[idx]) - auc(y_[idx], b_[idx]))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    tb, ta = recall_threshold(y_, b_, target), recall_threshold(y_, a_, target)
    pb = float((np.asarray(all_before, dtype=float) >= tb).mean()) if len(all_before) else 0.0
    pa = float((np.asarray(all_after, dtype=float) >= ta).mean()) if len(all_after) else 0.0
    return {"auc_before": base, "auc_after": new, "auc_gain": new - base, "auc_low": float(lo), "auc_high": float(hi),
            "sure": bool(lo > 0), "worse": bool(hi < 0), "pass_before": pb, "pass_after": pa, "pass_gain": pa - pb}


# ---------------------------------------------------------------- 분류기 학습


def train(vectors: Dict[str, np.ndarray], labels: Dict[str, int], groups: Dict[str, str]) -> Tuple[Optional[dict], str]:
    """임베딩 벡터와 정답으로 분류기(로지스틱 회귀)를 학습시킨다.

    vectors: 글의 지문 → 벡터 (정답 유무와 상관없이 전체)
    labels:  글의 지문 → 0/1
    groups:  글의 지문 → 묶음 이름(같은 쪽의 글끼리는 시험과 학습에 나뉘어 들어가지 않게 한다)
    반환: ({"scores": 지문 → 점수, "model": 계수, "folds": 나눈 수}, 못 했을 때의 이유)
      정답이 붙은 글의 점수는 그 글을 빼고 학습시킨 분류기가 매긴 것이다(교차 검증). 그래야 학습 후 결과를 공정하게 잴 수 있다.
    """
    keys = [k for k in labels if k in vectors]
    y = np.array([labels[k] for k in keys], dtype=int)
    n_yes, n_no = int((y == 1).sum()), int((y == 0).sum())
    if n_yes < MIN_EACH or n_no < MIN_EACH:
        return None, "정답이 더 필요합니다 (예 %d개, 아니오 %d개. 각각 %d개 이상)" % (n_yes, n_no, MIN_EACH)
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

    X = np.stack([vectors[k] for k in keys])
    g = np.array([groups.get(k, k) for k in keys])
    folds = min(5, n_yes, n_no)

    def fit(xs: np.ndarray, ys: np.ndarray):
        return LogisticRegression(C=4.0, class_weight="balanced", max_iter=2000).fit(xs, ys)

    oof = np.full(len(keys), np.nan)
    splitters = []
    if len(set(g)) >= folds:
        splitters.append(lambda: StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=0).split(X, y, g))
    splitters.append(lambda: StratifiedKFold(n_splits=folds, shuffle=True, random_state=0).split(X, y))
    done = False
    for make in splitters:                         # 같은 쪽끼리 묶어 나누기가 안 되면 묶지 않고 나눈다
        oof[:] = np.nan
        try:
            for tr, te in make():
                if len(set(y[tr])) < 2:
                    raise ValueError("한쪽 정답만 있는 묶음")
                oof[te] = fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
        except ValueError:
            continue
        if not np.isnan(oof).any():
            done = True
            break
    if not done:
        return None, "정답이 한쪽으로 몰려 있어 나눠서 시험할 수 없습니다"

    final = fit(X, y)
    scores: Dict[str, float] = {}
    rest = [k for k in vectors if k not in labels]
    if rest:
        probs = final.predict_proba(np.stack([vectors[k] for k in rest]))[:, 1]
        scores.update({k: float(p) for k, p in zip(rest, probs)})
    scores.update({k: float(p) for k, p in zip(keys, oof)})
    model = {"coef": [round(float(v), 6) for v in final.coef_[0]], "intercept": float(final.intercept_[0]),
             "yes": n_yes, "no": n_no}
    return {"scores": scores, "model": model, "folds": folds}, ""
