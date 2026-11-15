"""학습 기록: 학습 상태가 바뀔 때마다 그때의 비교 화면을 따로 저장하고, 한 화면에서 찾아볼 수 있게 한다.

    out/screen/history.html                  기록 목록 (추이 그림, 지난번 대비 변화, 그때의 화면으로 가는 길)
    out/screen/history/003_20261115_140233/  그때의 비교 화면 (index.html 과 문서별 화면)
    out/screen/history/history.json          기록의 수치

정답, 기준 문장, 쪽 제목 비율, 시험용 문서, 모델, 문서 가운데 하나라도 달라진 채로 계산하면 새 기록이 쌓인다.
아무것도 바꾸지 않고 다시 계산하면 마지막 기록을 고쳐 쓴다. 프로그램은 지난 기록을 지우지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional, Tuple

from .run import VIEWS, Result


def folder(res: Result) -> Path:
    return res.out_dir / "screen" / "history"


def load(res: Result) -> List[dict]:
    path = folder(res) / "history.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save(res: Result, entries: List[dict]) -> None:
    folder(res).mkdir(parents=True, exist_ok=True)
    tmp = folder(res) / "history.tmp"
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(folder(res) / "history.json")


def _signature(res: Result) -> str:
    parts = {"labels": sorted(res.labels.items()), "sentences": [[s.positive, s.text] for s in res.sentences],
             "title": res.title_weight, "test": sorted(res.test_names), "models": [r.key for r in res.runs if r.ok],
             "docs": [[d.name, len(d.blocks)] for d in res.docs]}
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _pick(m: Optional[dict], stage: str) -> Optional[dict]:
    if m is None or m.get("auc") is None:
        return None
    return {"stage": stage, "auc": m["auc"], "pass": m["tuned"]["pass"], "yes": m["yes"], "no": m["no"]}


def _metrics(res: Result) -> dict:
    """모델 × 보는 방식마다: 교차 검증으로 잰 것(cv)과 시험 문서로 잰 것(test). 학습 후가 있으면 그것, 없으면 학습 전."""
    out: dict = {}
    for r in res.runs:
        if not r.ok:
            continue
        out[r.key] = {"label": r.spec["label"]}
        for view, _ in VIEWS:
            m = r.metrics.get(view) or {}
            t = m.get("test") or {}
            out[r.key][view] = {
                "cv": _pick(m.get("after"), "after") or _pick(m.get("before"), "before"),
                "test": _pick(t.get("after"), "after") or _pick(t.get("before"), "before")}
    return out


def prepare(res: Result) -> Tuple[List[dict], dict, bool]:
    """이번 계산을 기록에 올릴 자리를 정한다. 반환: (기록 전체, 이번 기록, 새로 쌓았는가)"""
    entries = load(res)
    sig = _signature(res)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    labels = list(res.labels.values())
    entry = {"sig": sig, "updated": now, "docs": len(res.docs),
             "labels": {"yes": sum(1 for v in labels if v == 1), "no": sum(1 for v in labels if v == 0)},
             "trained": res.trained_on(), "test": res.label_counts("test") if res.test_names else None,
             "test_docs": sorted(res.test_names), "title_weight": res.title_weight,
             "sentences": hashlib.sha1(json.dumps([[s.positive, s.text] for s in res.sentences], ensure_ascii=False).encode("utf-8")).hexdigest()[:12],
             "metrics": _metrics(res)}
    if entries and entries[-1].get("sig") == sig:     # 학습 상태가 그대로면 마지막 기록을 고쳐 쓴다
        entry.update({"n": entries[-1]["n"], "made": entries[-1]["made"], "dir": entries[-1]["dir"]})
        entries[-1] = entry
        return entries, entry, False
    n = (entries[-1]["n"] + 1) if entries else 1
    entry.update({"n": n, "made": now, "dir": "%03d_%s" % (n, time.strftime("%Y%m%d_%H%M%S"))})
    entries.append(entry)
    return entries, entry, True


def what_changed(prev: Optional[dict], cur: dict) -> List[str]:
    """바로 앞 기록과 견줘 달라진 것을 말로."""
    if prev is None:
        return ["처음 기록"]
    out = []
    dy, dn = cur["labels"]["yes"] - prev["labels"]["yes"], cur["labels"]["no"] - prev["labels"]["no"]
    if dy or dn:
        same = (prev.get("trained") or {}) == (cur.get("trained") or {})
        out.append("정답 %+d개 (예 %+d, 아니오 %+d)%s" % (dy + dn, dy, dn, " · 학습에 쓴 정답은 그대로(시험용 정답만 달라짐)" if same else ""))
    if cur.get("sentences") != prev.get("sentences"):
        out.append("기준 문장 바뀜")
    if cur.get("title_weight", 0) != prev.get("title_weight", 0):
        out.append("쪽 제목 비율 %g → %g" % (prev.get("title_weight", 0), cur.get("title_weight", 0)))
    if cur.get("test_docs") != prev.get("test_docs"):
        out.append("시험용 문서 %d개 → %d개" % (len(prev.get("test_docs") or []), len(cur.get("test_docs") or [])))
    if cur.get("docs") != prev.get("docs"):
        out.append("문서 %s개 → %s개" % (prev.get("docs"), cur.get("docs")))
    if sorted(k for k in cur["metrics"]) != sorted(k for k in prev["metrics"]):
        out.append("모델 바뀜")
    return out or ["정답의 내용이 바뀜"]
