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
C_VALUE = 4.0         # 가중치가 커지는 것을 누르는 세기(클수록 덜 누름). 로지스틱 회귀와 선형 SVM에 같은 값을 쓴다
MAX_ITER = 2000       # 로지스틱 회귀가 가중치를 고쳐 가는 되풀이의 한도. 대개 수십 번 안에 스스로 멈춘다
CURVE_POINTS = 10     # '학습 과정'에 남기는, 되풀이마다 줄어드는 값의 점 수
CURVE_SECONDS = 3.0   # 학습 한 번이 이보다 오래 걸리면 줄어드는 과정은 다시 계산하지 않는다(시간을 아끼려고)


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


def measure(y: List[int], s: List[float], everything: List[float], target: float, boundary: float = 0.5) -> Optional[dict]:
    """정답이 붙은 항목의 점수 s와 정답 y로 결과를 잰다. everything은 정답 유무와 상관없이 전체 항목의 점수.

    boundary: 그 점수에서 '예'와 '아니오'를 가르는 기본 문턱. 0~1 점수는 0.5, 선형 SVM의 값은 0이다.
    """
    y_, s_, all_ = np.asarray(y, dtype=int), np.asarray(s, dtype=float), np.asarray(everything, dtype=float)
    if not len(y_) or not (y_ == 1).any() or not (y_ == 0).any():
        return None
    thr = recall_threshold(y_, s_, target)
    return {"n": int(len(y_)), "yes": int((y_ == 1).sum()), "no": int((y_ == 0).sum()), "auc": auc(y_, s_),
            "half": at_threshold(y_, s_, all_, boundary), "tuned": at_threshold(y_, s_, all_, thr)}


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
    """임베딩 벡터와 정답으로 분류기(로지스틱 회귀)를 학습시킨다. 견줘 보려고 선형 SVM도 함께 학습시킨다.

    vectors: 글의 지문 → 벡터 (정답 유무와 상관없이 전체)
    labels:  글의 지문 → 0/1
    groups:  글의 지문 → 묶음 이름(같은 쪽의 글끼리는 시험과 학습에 나뉘어 들어가지 않게 한다)
    반환: ({"scores": 지문 → 점수, "model": 계수, "folds": 나눈 수, "svm": 선형 SVM의 것 또는 None}, 못 했을 때의 이유)
      정답이 붙은 글의 점수는 그 글을 빼고 학습시킨 분류기가 매긴 것이다(교차 검증). 그래야 학습 후 결과를 공정하게 잴 수 있다.
      선형 SVM은 로지스틱 회귀와 똑같은 묶음으로 나눠 학습시킨다. 그 값은 0~1이 아니라 경계에서 떨어진 정도이고 0이 경계다.
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

    def fit(xs: np.ndarray, ys: np.ndarray, max_iter: int = MAX_ITER):
        return LogisticRegression(C=C_VALUE, class_weight="balanced", max_iter=max_iter).fit(xs, ys)

    oof = np.full(len(keys), np.nan)
    fold_iters: List[Optional[int]] = []           # 묶음마다 몇 번 되풀이하고 멈췄는가 ('학습 과정'에 남긴다)
    t_all = time.time()
    splits: list = []
    splitters = []
    if len(set(g)) >= folds:
        splitters.append(lambda: StratifiedGroupKFold(n_splits=folds, shuffle=True, random_state=0).split(X, y, g))
    splitters.append(lambda: StratifiedKFold(n_splits=folds, shuffle=True, random_state=0).split(X, y))
    done, grouped = False, False
    for which, make in enumerate(splitters):       # 같은 쪽끼리 묶어 나누기가 안 되면 묶지 않고 나눈다
        oof[:] = np.nan
        fold_iters = []
        try:
            splits = list(make())
            for tr, te in splits:
                if len(set(y[tr])) < 2:
                    raise ValueError("한쪽 정답만 있는 묶음")
                part = fit(X[tr], y[tr])
                fold_iters.append(_iters(part))
                oof[te] = part.predict_proba(X[te])[:, 1]
        except ValueError:
            continue
        if not np.isnan(oof).any():
            done, grouped = True, (len(splitters) == 2 and which == 0)
            break
    if not done:
        return None, "정답이 한쪽으로 몰려 있어 나눠서 시험할 수 없습니다"

    t_final = time.time()
    final = fit(X, y)
    final_seconds = time.time() - t_final
    seconds = time.time() - t_all
    scores: Dict[str, float] = {}
    rest = [k for k in vectors if k not in labels]
    if rest:
        probs = final.predict_proba(np.stack([vectors[k] for k in rest]))[:, 1]
        scores.update({k: float(p) for k, p in zip(rest, probs)})
    scores.update({k: float(p) for k, p in zip(keys, oof)})
    model = {"coef": [round(float(v), 6) for v in final.coef_[0]], "intercept": float(final.intercept_[0]),
             "yes": n_yes, "no": n_no}
    try:
        svm = _train_svm(X, y, keys, splits, vectors, rest)
        svm["model"].update({"yes": n_yes, "no": n_no})
    except Exception as exc:                       # 견주기용이라, 실패해도 본래 결과는 그대로 낸다
        svm = {"scores": None, "model": None, "params": None,
               "note": "선형 SVM을 학습시키지 못했습니다 (%s: %s)" % (type(exc).__name__, str(exc)[:120])}
    import sklearn
    # 실제로 적용된 설정값(라이브러리가 알려 주는 그대로). 화면의 '분류기 설정'에 쓴다
    info = {"sklearn": sklearn.__version__, "folds": folds, "grouped": grouped, "yes": n_yes, "no": n_no, "min_each": MIN_EACH,
            "logreg": _plain(final.get_params()), "svm": svm.get("params")}
    try:                                           # 학습 과정의 기록. 보여 주기용이라, 실패해도 학습 결과는 그대로 낸다
        info["process"] = _process(X, y, final, fold_iters, final_seconds, seconds, fit)
        if svm.get("iters") is not None:
            info["process"]["svm"] = {"iters": svm["iters"], "limit": svm.get("limit"),
                                      "converged": svm["iters"] < (svm.get("limit") or 0) and not svm.get("note")}
    except Exception as exc:
        info["process"] = None
        info["process_note"] = "%s: %s" % (type(exc).__name__, str(exc)[:120])
    return {"scores": scores, "model": model, "folds": folds, "svm": svm, "info": info}, ""


def _iters(clf) -> Optional[int]:
    """학습이 멈출 때까지 되풀이한 횟수(라이브러리가 알려 주는 값)."""
    got = getattr(clf, "n_iter_", None)
    if got is None:
        return None
    try:
        return int(np.max(got))
    except (TypeError, ValueError):
        return None


def class_weights(y: np.ndarray) -> Tuple[float, float]:
    """class_weight="balanced"가 정답마다 주는 무게: 전체 수 ÷ (2 × 그 정답의 수). 반환: ('아니오'의 무게, '예'의 무게)"""
    n, n_yes = len(y), int((y == 1).sum())
    n_no = n - n_yes
    return n / (2.0 * max(n_no, 1)), n / (2.0 * max(n_yes, 1))


def objective(X: np.ndarray, y: np.ndarray, coef: np.ndarray, intercept: float, c: float = C_VALUE) -> dict:
    """로지스틱 회귀가 줄이려는 값을 글 하나당으로 나타낸 것.

        목적 함수 값 = 평균 벌점 + 규제 몫
        평균 벌점 = Σ 무게 × -log(정답에 준 확률) ÷ Σ 무게          (무게를 반영한 로그 손실)
        규제 몫   = ½‖w‖² ÷ (C × Σ 무게)                            (가중치가 커진 만큼의 벌점. 절편은 넣지 않는다)
    라이브러리가 줄이는 값(½‖w‖² + C × Σ 무게 × 벌점)을 C × Σ 무게로 나눈 것이라, 가장 작아지는 자리는 같다.
    가중치가 모두 0일 때는 어느 글에나 확률 0.5를 주므로 평균 벌점이 log 2 = 0.693이다.
    """
    xs, w = np.asarray(X, dtype=np.float64), np.asarray(coef, dtype=np.float64)
    w_no, w_yes = class_weights(y)
    weights = np.where(y == 1, w_yes, w_no)
    z = xs @ w + float(intercept)
    sign = np.where(y == 1, 1.0, -1.0)
    with np.errstate(all="ignore"):
        loss = float((weights * np.logaddexp(0.0, -sign * z)).sum() / weights.sum())
    penalty = float(0.5 * (w @ w) / (c * weights.sum()))
    return {"loss": loss, "penalty": penalty, "objective": loss + penalty}


def _curve_steps(n: int, most: int = CURVE_POINTS) -> List[int]:
    """1번째부터 n번째 되풀이 가운데, 줄어드는 과정을 보여 줄 자리(앞쪽은 촘촘하게, 뒤쪽은 성기게). n번째는 넣지 않는다."""
    if n <= 1:
        return []
    if n - 1 <= most - 1:
        return list(range(1, n))
    steps, k = [], 1.0
    ratio = (n - 1) ** (1.0 / max(most - 2, 1))
    while len(steps) < most - 1 and int(round(k)) < n:
        v = int(round(k))
        if not steps or v > steps[-1]:
            steps.append(v)
        k = max(k * ratio, k + 1)
    return steps


def _process(X: np.ndarray, y: np.ndarray, final, fold_iters: List[Optional[int]], final_seconds: float, seconds: float, fit) -> dict:
    """학습 과정에서 정해지고 나타난 값. 신경망 학습의 epoch·loss에 견줄 수 있는 것을 모은다(학습 결과는 바꾸지 않는다).

    줄어드는 과정(curve)은 '되풀이 한도를 k번으로 줄여 다시 학습시킨 것'의 값이다. 이 계산법(lbfgs)은 늘 같은 길을 가므로,
    k번에서 끊은 결과가 곧 끝까지 간 학습의 k번째 자리다.
    """
    import warnings

    from sklearn.exceptions import ConvergenceWarning

    n, dim = int(X.shape[0]), int(X.shape[1])
    w_no, w_yes = class_weights(y)
    iters, limit = _iters(final), int(final.max_iter)
    coef, intercept = final.coef_[0], float(final.intercept_[0])
    start = objective(X, y, np.zeros(dim), 0.0)
    end = objective(X, y, coef, intercept)
    curve = [[0, round(start["objective"], 6)]]
    curve_note = ""
    if iters and final_seconds <= CURVE_SECONDS:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConvergenceWarning)
            for k in _curve_steps(iters):
                part = fit(X, y, k)
                curve.append([k, round(objective(X, y, part.coef_[0], float(part.intercept_[0]))["objective"], 6)])
    elif iters:
        curve_note = "학습 한 번이 %.1f초 걸려, 줄어드는 과정은 처음과 끝만 적었습니다" % final_seconds
    if iters:
        curve.append([iters, round(end["objective"], 6)])
    with np.errstate(all="ignore"):
        hit = float(((1.0 / (1.0 + np.exp(-(np.asarray(X, dtype=np.float64) @ coef + intercept))) >= 0.5) == (y == 1)).mean())
    return {"n": n, "dim": dim, "yes": int((y == 1).sum()), "no": int((y == 0).sum()),
            "weight_yes": round(w_yes, 4), "weight_no": round(w_no, 4),
            "iters": iters, "fold_iters": list(fold_iters), "limit": limit, "tol": float(final.tol),
            "converged": bool(iters is not None and iters < limit),
            "start": {k: round(v, 6) for k, v in start.items()}, "end": {k: round(v, 6) for k, v in end.items()},
            "curve": curve, "curve_note": curve_note,
            "norm": round(float(np.linalg.norm(coef)), 4), "intercept": round(intercept, 5), "train_hit": round(hit, 4),
            "seconds": round(float(seconds), 4), "final_seconds": round(float(final_seconds), 4), "fits": len(fold_iters) + 1}


def _plain(params: dict) -> dict:
    """설정값을 파일에 적을 수 있는 모양으로."""
    return {k: (v if isinstance(v, (int, float, str, bool)) or v is None else str(v)) for k, v in params.items()}


def _train_svm(X: np.ndarray, y: np.ndarray, keys: List[str], splits: list, vectors: Dict[str, np.ndarray], rest: List[str]) -> dict:
    """선형 SVM(힌지 손실, L2). 로지스틱 회귀와 같은 묶음, 같은 세기(C), 같은 '예'에 무게 더 주기로 학습시킨다."""
    import warnings

    from sklearn.exceptions import ConvergenceWarning
    from sklearn.svm import LinearSVC

    def fit(xs: np.ndarray, ys: np.ndarray):
        return LinearSVC(C=C_VALUE, loss="hinge", dual=True, class_weight="balanced", max_iter=50000, random_state=0).fit(xs, ys)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        oof = np.full(len(keys), np.nan)
        for tr, te in splits:
            oof[te] = fit(X[tr], y[tr]).decision_function(X[te])
        final = fit(X, y)
        scores: Dict[str, float] = {}
        if rest:
            scores.update({k: float(v) for k, v in zip(rest, final.decision_function(np.stack([vectors[k] for k in rest])))})
        scores.update({k: float(v) for k, v in zip(keys, oof)})
    note = "계산이 끝까지 수렴하지 않아 결과가 조금 덜 정확할 수 있습니다" if any(issubclass(w.category, ConvergenceWarning) for w in caught) else ""
    return {"scores": scores, "note": note, "params": _plain(final.get_params()), "iters": _iters(final), "limit": int(final.max_iter),
            "model": {"coef": [round(float(v), 6) for v in final.coef_[0]], "intercept": float(final.intercept_[0])}}
