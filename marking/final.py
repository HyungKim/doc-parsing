"""최종 모델로 문서를 표시한다 (5.0부터 표시하기가 하는 일).

    ① 글 뽑기             PDF·PPTX → 덩어리 (1단계와 같은 규칙)
    ② 분류기               multilingual-e5-small + 학습해 둔 분류기. 덩어리마다 점수를 매겨 문턱 이상을 '예'로 본다
    ③ LLM                  분류기가 '예'로 본 덩어리를 이 PC의 Ollama(qwen3:8b · 프롬프트 안 C 사업 분야 · 생각 모드 끔)에 물어 '아니오'를 덜어 낸다
    ④ 표시한 파일 만들기    분류기 출력으로 표시한 사본, LLM까지 거친 결과로 표시한 사본, 요약 화면

단계마다 걸린 시간을 재서 요약 화면과 시간 기록(out/mark/times.html, times.csv)에 남긴다.
LLM의 답은 out/mark/cache/answers.jsonl 에 쌓아 두고, 모델·프롬프트·글이 모두 같으면 다시 묻지 않는다(도중에 멈춰도 이어서 받는다).
자료는 이 PC 밖으로 나가지 않는다: Ollama에는 127.0.0.1로만 말을 걸고, 이름에 cloud가 붙은 모델은 거부한다(verifying/ollama.py).
"""
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from screening.sentences import load_sentences
from verifying import core as vcore
from verifying import ollama, prompts
from verifying.core import FINAL

from . import core, times
from .page import write_page

METHODS = [("annot", "형광펜 주석 (지울 수 있음)"), ("paint", "쪽에 직접 칠하기 (어느 프로그램에서나 보임)")]
VIEW = FINAL["view"]              # 넣는 크기: 덩어리
STAGE = "after"                   # 학습한 분류기


def mark_dir(cfg) -> Path:
    return Path(cfg.out_dir) / "mark"


def answers_file(cfg) -> Path:
    return mark_dir(cfg) / "cache" / "answers.jsonl"


# ---------------------------------------------------------------- 분류기의 문턱

def saved_threshold(cfg) -> Optional[float]:
    """지난 학습에서 '예'의 90%(설정한 비율)를 찾던 문턱. 없거나 쪽 제목 설정이 그때와 다르면 None"""
    saved = core.load_thresholds(cfg.labels)
    if abs(float(saved.get("title_weight", 0.0) or 0.0) - float(cfg.title_weight or 0.0)) > 1e-9:
        return None
    got = (((saved.get("models") or {}).get(FINAL["classifier"]) or {}).get(VIEW) or {}).get(STAGE)
    return None if got is None else float(got)


def pick_threshold(cfg, mode: str = "", custom=None) -> tuple:
    """분류기의 문턱과 그 설명. mode: saved(지난 학습의 문턱) | half(0.5) | custom | ""(saved가 있으면 그것, 없으면 0.5)"""
    saved = saved_threshold(cfg)
    info = core.load_thresholds(cfg.labels)
    pct = int(round(100 * float(info.get("target") or 0.9)))
    if mode == "custom":
        return core.safe_threshold(custom), "직접 정한 문턱"
    if mode == "saved" and saved is None:
        raise ValueError("지난 학습에서 남긴 문턱이 없습니다. label.bat 에서 '학습하고 결과 보기'를 한 번 하면 생깁니다.")
    if mode == "saved" or (not mode and saved is not None):
        return saved, "지난 학습(%s)에서 '예'의 %d%%를 찾던 문턱" % (info.get("made", ""), pct)
    return 0.5, "0.5 (예와 아니오 가능성이 반반인 자리)"


# ---------------------------------------------------------------- LLM 준비

@dataclass
class Llm:
    """LLM에 묻는 방법. 실행 한 번에 한 번 준비한다."""
    model: dict                   # verifying.core.llm_entry 가 주는 항목 (name, id, digest, label, …)
    variant: prompts.Variant
    system: str                   # 앞쪽 글. 모든 덩어리에 같다
    version: str                  # Ollama 버전
    license: str
    prompts_file: Path
    sentences_file: Path

    @property
    def label(self) -> str:
        return "%s · 프롬프트 안 %s · 생각 모드 끔" % (self.model["name"], self.variant.label)


def prepare_llm(cfg, prompts_file: Path, log: Callable[[str], None]) -> Llm:
    """Ollama가 켜져 있는지, 모델을 받아 두었는지, 프롬프트 안 C가 있는지 확인하고 앞쪽 글을 만든다. 안 되면 ValueError(사용자에게 보일 글)"""
    state = ollama.ensure_running(log)
    if not state["ok"]:
        raise ValueError(state["error"])
    name = FINAL["llm"]
    try:
        m = vcore.llm_entry(ollama.models())
    except ollama.OllamaError as exc:
        text = str(exc)
        if "받지 않았습니다" in text:
            text = "'%s' 모델을 아직 받지 않았습니다. verify.bat 화면에서 '받기'를 누르거나 명령 창에서 ollama pull %s 를 실행해 주세요." % (name, name)
        raise ValueError(text)
    parts, v = prompts.load(prompts_file, FINAL["variant"])
    criteria = prompts.criteria_text(load_sentences(cfg.sentences))
    return Llm(model=m, variant=v, system=prompts.system_prompt(v, parts, criteria), version=state.get("version", ""),
               license=ollama.license_of(m["name"]), prompts_file=Path(prompts_file), sentences_file=Path(cfg.sentences))


def _left(seconds: float) -> str:
    return vcore._left(seconds)


def ask(llm: Llm, ex: core.Extracted, ids: List[str], answers: vcore.Answers, log: Callable[[str], None], stop=None,
        fresh: bool = False, tick: Optional[Callable[[int, int], None]] = None) -> dict:
    """ids(분류기가 '예'로 본 덩어리)를 차례로 LLM에 묻는다.

    반환: {"rows": {덩어리 id: 답}, "users": {덩어리 id: 뒤쪽 글}, "sec": 이 단계에 걸린 초, "load": 모델을 불러온 초,
           "new": 이번에 물은 수, "reused": 보관해 둔 답을 쓴 수, "stopped": 멈췄는가, "error": 실패한 까닭}
    fresh: 보관해 둔 답을 쓰지 않고 모두 다시 묻는다(걸린 시간을 잴 때). 새로 받은 답은 보관함에 적는다.
    """
    m = llm.model
    text = {b.id: b.text for b in ex.doc.blocks}
    rows: Dict[str, dict] = {}
    users: Dict[str, str] = {}
    out = {"rows": rows, "users": users, "sec": 0.0, "load": 0.0, "new": 0, "reused": 0, "stopped": False, "error": ""}
    t0 = time.perf_counter()
    spent = 0.0
    for n, bid in enumerate(ids):
        user = users[bid] = prompts.user_prompt(text[bid])
        key = vcore.answer_key(m["id"], m["digest"], llm.system, user, prompts.MAX_TOKENS)
        rec = None if fresh else answers.get(key)
        if rec is not None:
            out["reused"] += 1
        else:
            if stop is not None and stop.is_set():
                out["stopped"] = True
                break
            eta = " · 남은 시간 %s" % _left(spent / out["new"] * (len(ids) - n)) if out["new"] >= 3 else ""
            log("%s · LLM %d/%d번째 덩어리%s" % (ex.name, n + 1, len(ids), eta))
            handle = ollama.Call()
            if stop is not None:
                stop.call = handle
            try:
                if stop is not None and stop.is_set():
                    raise ollama.Cancelled()
                rec = vcore._ask(m, llm.system, user, handle)
            except ollama.Cancelled:               # 멈추기: 묻고 있던 글은 버리고 여기서 끝낸다
                out["stopped"] = True
                break
            except ollama.OllamaError as exc:
                out["error"] = str(exc)
                break
            finally:
                if stop is not None:
                    stop.call = None
            answers.put(key, rec)
            out["new"] += 1
            out["load"] += float(rec.get("load") or 0.0)
            spent += float(rec["sec"])
        rows[bid] = rec
        if tick:
            tick(n + 1, len(ids))
    out["sec"] = time.perf_counter() - t0
    return out


# ---------------------------------------------------------------- 문서 하나

def _stats(values: List[float]) -> dict:
    if not values:
        return {"sum": 0.0, "mean": None, "median": None, "min": None, "max": None}
    s = sorted(values)
    mid = len(s) // 2
    return {"sum": float(sum(s)), "mean": float(sum(s)) / len(s), "median": s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0,
            "min": s[0], "max": s[-1]}


def _copy(ex: core.Extracted, marks: list, target: Path, method: str, author: str, word: str, notes: List[str]) -> str:
    """표시한 사본 하나를 만든다. 반환: 만든 파일 이름(만들지 못했으면 빈 글). word: 안내 글에서 이 사본을 부르는 말"""
    try:
        if ex.kind == "pdf":
            from .pdf_mark import mark_pdf
            st = mark_pdf(ex.path, target, marks, method, author)
        else:
            from .pptx_mark import mark_pptx
            st = mark_pptx(ex.path, target, marks, ex.slide_numbers)
            notes.append("%s(PPTX): 글자에 형광펜 색을 넣은 덩어리 %d개, 표이거나 같은 글을 찾지 못해 덩어리 자리에 네모를 얹은 덩어리 %d개. "
                         "형광펜 색은 PowerPoint 2019 이상(또는 365)에서 보입니다." % (word, st["text"], st["fallback"]))
        if st.get("skipped"):
            notes.append("%s: 쪽을 찾지 못해 표시하지 못한 것 %d개" % (word, st["skipped"]))
        return target.name
    except Exception as exc:                        # 원본에 표시하지 못해도 요약 화면은 만든다
        notes.append("%s을(를) 만들지 못했습니다 (%s: %s). 요약 화면의 글에서는 볼 수 있습니다." % (word, type(exc).__name__, str(exc)[:200]))
        return ""


def run_document(scorer: core.Scorer, ex: core.Extracted, llm: Optional[Llm], answers: Optional[vcore.Answers], threshold: float,
                 threshold_note: str, method: str, log: Callable[[str], None], stop=None, fresh: bool = False,
                 scores: Optional[dict] = None, tick: Optional[Callable[[int, int], None]] = None) -> dict:
    """문서 하나를 최종 모델로 처리해 표시한 사본 두 개와 요약 화면을 만든다. llm이 None이면 분류기까지만 한다.

    반환(화면과 시간 기록이 읽는 모양): {"name", "counts", "files": {"classifier", "llm", "page"}, "notes", "timing", "llm": {…}, "scores"}
    """
    cfg = scorer.cfg
    threshold = core.safe_threshold(threshold)
    if method not in ("annot", "paint"):
        raise ValueError("표시 방식을 알 수 없습니다")
    out = mark_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    notes: List[str] = []

    # ② 분류기
    if scores is None or (fresh and not scores.get("fresh")):
        log("%s · 분류기 점수를 매기는 중…" % ex.name)
        scores = scorer.score(ex, FINAL["classifier"], VIEW, STAGE, log, fresh)
    marks_c = core.pick_marks(ex, scores, VIEW, threshold)
    for mk in marks_c:
        mk.note = "검토 필요 · 분류기 점수 %.2f" % mk.score
    total = len(scores["block"])

    # ③ LLM
    got = None
    marks_l: Optional[list] = None
    info = {"ran": False, "done": False, "stopped": False, "error": "", "why": "", "label": "", "rows": {}}
    if llm is None:
        info["why"] = "LLM 단계를 돌리지 않았습니다(분류기까지만 만들기를 고름)."
    elif not marks_c:
        info.update(ran=True, done=True, label=llm.label, why="분류기가 '예'로 본 덩어리가 없어 LLM에 물을 것이 없습니다.")
        marks_l = []
    else:
        got = ask(llm, ex, [mk.id for mk in marks_c], answers, log, stop, fresh, tick)
        info.update(ran=True, label=llm.label, rows=got["rows"], stopped=got["stopped"], error=got["error"],
                    done=len(got["rows"]) == len(marks_c))
        if info["done"]:
            marks_l = []
            for mk in marks_c:
                r = got["rows"][mk.id]
                if r["verdict"] == 0:              # LLM이 '아니오'라고 한 것만 덜어 낸다. 읽지 못한 답은 남긴다
                    continue
                said = "예" if r["verdict"] == 1 else "답을 읽지 못해 남김"
                prob = "" if r.get("p") is None else " (예일 확률 %.2f)" % r["p"]
                marks_l.append(dataclasses.replace(mk, note="검토 필요 · LLM %s%s · 분류기 점수 %.2f" % (said, prob, mk.score)))
        elif got["stopped"]:
            info["why"] = "멈춰서 LLM의 답을 %d개 가운데 %d개만 받았습니다. 받은 답은 보관되어 있어, 다시 만들면 이어서 받습니다." % (len(marks_c), len(got["rows"]))
        else:
            info["why"] = "LLM에 묻다가 실패했습니다: %s" % got["error"]

    # ④ 표시한 파일 만들기
    files = {"classifier": "", "llm": "", "page": "%s.%s.html" % (ex.path.stem, ex.kind)}
    t_c = t_l = 0.0
    if not marks_c:
        notes.append("분류기의 문턱(%.2f) 이상인 덩어리가 없어 표시한 사본은 만들지 않았습니다. 문턱을 낮춰 보세요." % threshold)
    else:
        log("%s · 표시한 파일을 만드는 중…" % ex.name)
        t0 = time.perf_counter()
        files["classifier"] = _copy(ex, marks_c, out / ("%s.%s" % (core.out_stem(ex, "분류기"), ex.kind)), method, "분류기", "분류기 표시 사본", notes)
        t_c = time.perf_counter() - t0
        loose = sum(1 for mk in marks_c if not mk.exact)
        if loose and ex.kind == "pdf":
            notes.append("자리를 정확히 알 수 없는 %d개는 그 글이 든 덩어리 전체에 표시했습니다." % loose)
    llm_target = out / ("%s.%s" % (core.out_stem(ex, "LLM"), ex.kind))
    if marks_l:
        t0 = time.perf_counter()
        files["llm"] = _copy(ex, marks_l, llm_target, method, "분류기 + LLM", "LLM 표시 사본", notes)
        t_l = time.perf_counter() - t0
    elif marks_l is not None and marks_c:
        notes.append("LLM이 '예'로 본 덩어리가 없어 LLM 표시 사본은 만들지 않았습니다.")
    for which, target in (("classifier", out / ("%s.%s" % (core.out_stem(ex, "분류기"), ex.kind))), ("llm", llm_target)):
        if not files[which] and target.exists():
            notes.append("폴더에 남아 있는 %s 은(는) 지난번에 만든 것입니다(이번에는 만들지 않았습니다)." % target.name)

    # 걸린 시간
    rows = info["rows"]
    asks = _stats([float(r["sec"]) for r in rows.values()])
    verdicts = [r["verdict"] for r in rows.values()]
    timing = {
        "extract": {"sec": float(ex.seconds), "pages": len(ex.pages), "blocks": total},
        "classify": {"sec": float(scores.get("wall") or 0.0), "compute": float(scores.get("seconds") or 0.0), "items": int(scores.get("items") or 0),
                     "new": int(scores.get("new_items") or 0),
                     "reused": max(0, int(scores.get("uniq") or 0) - int(scores.get("new_items") or 0)), "fresh": bool(scores.get("fresh"))},
        "llm": {"sec": 0.0 if got is None else float(got["sec"]), "load": 0.0 if got is None else float(got["load"]),
                "asked": len(rows), "to_ask": len(marks_c) if llm is not None else 0,
                "new": 0 if got is None else got["new"], "reused": 0 if got is None else got["reused"],
                "ask_sum": asks["sum"], "mean": asks["mean"], "median": asks["median"], "min": asks["min"], "max": asks["max"],
                "tok_in": (sum(r["in"] for r in rows.values()) / float(len(rows))) if rows else None,
                "tok_out": (sum(r["out"] for r in rows.values()) / float(len(rows))) if rows else None,
                "ran": info["ran"], "done": info["done"]},
        "write": {"sec": t_c + t_l, "classifier": t_c, "llm": t_l},
    }
    counts = {"pages": len(ex.pages), "blocks": total, "passed": len(marks_c),
              "llm_yes": sum(1 for v in verdicts if v == 1), "llm_no": sum(1 for v in verdicts if v == 0),
              "llm_unknown": sum(1 for v in verdicts if v is None), "kept": None if marks_l is None else len(marks_l)}
    res = {"name": ex.name, "kind": ex.kind, "made": time.strftime("%Y-%m-%d %H:%M:%S"), "threshold": threshold, "threshold_note": threshold_note,
           "method": method, "counts": counts, "files": files, "notes": notes, "timing": timing, "llm": info,
           "classifier": scores.get("classifier"), "title_weight": float(cfg.title_weight or 0.0), "fresh": bool(fresh)}
    t0 = time.perf_counter()
    write_page(ex, scores, res, marks_c, marks_l, llm, out / files["page"])
    timing["write"]["page"] = time.perf_counter() - t0
    timing["write"]["sec"] += timing["write"]["page"]
    timing["total"] = sum(timing[k]["sec"] for k in ("extract", "classify", "llm", "write"))
    write_page(ex, scores, res, marks_c, marks_l, llm, out / files["page"])     # 요약 화면을 만든 시간까지 넣어 다시 쓴다
    times.add(cfg, res, llm)
    return res


def public(res: dict) -> dict:
    """화면에 보낼 모양(LLM의 답 전체는 뺀다)."""
    out = dict(res)
    out["llm"] = {k: v for k, v in res["llm"].items() if k != "rows"}
    return out
