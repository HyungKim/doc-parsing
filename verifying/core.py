"""검증의 계산 부분: 분류기 점수로 통과한 글을 추리고, LLM에 물어 답을 모으고, 얼마나 나아졌는지 잰다.

5.0부터 조합은 하나로 정해져 있다(아래 FINAL). 4.x에서 고르던 것(분류기 모델, 줄 단위로 넣기, Qwen3 4B,
생각 모드를 켠 것, 프롬프트 안 A·B·D·E·F)은 없앴다. 이 모듈은 그 한 조합이 정답과 얼마나 맞는지, 시간이 얼마나 걸리는지를 잰다.

학습·시험·평가(screen.py, label.py)와는 따로 돈다. 이 모듈은
    out 폴더의 문서 목록, 정답(labels), 분류기(labels/classifiers), 시험용 문서 목록을 읽기만 하고 고치지 않는다.
    분류기는 그때그때 파일에서 읽으므로, 다시 학습하면 다음 실행부터 새 분류기를 쓴다.
    LLM의 답은 out/verify/cache/answers.jsonl 에 쌓아 두고 다시 묻지 않는다(모델·프롬프트·글이 모두 같을 때).
    4.x에서 같은 조합(qwen3:8b · 안 C · 생각 모드 끔)으로 받아 둔 답도 그대로 쓴다.

재는 방법
    시험용 문서(학습에 쓰지 않은 문서)에서 정답이 붙은 덩어리만 쓴다.
    분류기가 문턱 이상으로 본 글(통과한 글)을 LLM에 넣고, LLM이 '아니오'라고 한 글을 덜어낸다.
    덜어낸 '아니오'가 많고 잃은 '예'가 적을수록 좋다. 그런데 분류기의 문턱만 올려도 같은 일이 일어나므로,
    '예'를 같은 수만큼 남길 때 분류기 문턱만 올린 것보다 LLM이 얼마나 더 줄였는지를 함께 잰다.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional

import numpy as np

from marking import core as mcore
from screening import learn, testdocs
from screening.items import load_docs
from screening.sentences import load_sentences

from . import ollama, prompts

# 5.0에서 정한 최종 모델. 표시하기(mark.bat)와 LLM 검증(verify.bat)이 이 조합 하나로만 돈다.
#   분류기 multilingual-e5-small · 넣는 크기 덩어리 · LLM qwen3:8b · 프롬프트 안 C(사업 분야) · 생각 모드 끔
# qwen3:8b는 생각 모드를 켜고 끌 수 있는 모델이라, 물을 때마다 끄라고 알려 준다(verifying/ollama.py의 chat).
FINAL = {"classifier": "me5-small", "view": "block", "llm": "qwen3:8b", "variant": "C", "think": False}
LLM_NOTE = "Qwen3 8B · Apache 2.0 · 내려받기 약 5.2GB · 생각 모드는 끄고 씀"
DEFAULT_SAMPLE = 200
BOOT = 1000                   # 차이의 범위를 어림할 때 다시 뽑는 횟수


@dataclass
class Env:
    cfg: object                   # 걸러내기의 설정(screening.cli.Config)
    prompts_file: Path

    @property
    def out(self) -> Path:
        return Path(self.cfg.out_dir) / "verify"


@dataclass
class Setup:
    """화면에서 고른 것. 조합(분류기 · 넣는 크기 · LLM · 프롬프트)은 FINAL로 정해져 있어서 여기에 없다."""
    thr_mode: str = "test90"
    threshold: Optional[float] = None         # thr_mode가 custom일 때
    sample: int = DEFAULT_SAMPLE              # 0이면 전체
    with_rejected: bool = False               # 분류기가 떨어뜨린 글도 LLM에 넣어 본다
    fresh: bool = False                       # 분류기 시간도 재기: 보관해 둔 계산을 쓰지 않고 점수를 다시 계산한다


@dataclass
class Item:
    """정답이 붙은 덩어리 하나."""
    uid: str
    doc: str
    page: int
    key: str
    text: str
    title: str
    label: int                # 정답: 1 예, 0 아니오
    score: float              # 분류기 점수
    passed: bool = True       # 분류기 문턱을 넘었는가
    order: int = 0            # 문서에 나온 순서


class Stop:
    """멈추라는 신호. 켜는 순간, 지금 LLM에 묻고 있는 요청도 끊는다(그 글이 끝나기를 기다리지 않는다)."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.call: Optional[ollama.Call] = None       # 지금 묻고 있는 요청

    def set(self) -> None:
        self._event.set()
        call = self.call
        if call is not None:
            call.cancel()

    def clear(self) -> None:
        self._event.clear()

    def is_set(self) -> bool:
        return self._event.is_set()


def llm_entry(listed: List[dict], strict: bool = True) -> dict:
    """최종 모델의 LLM(FINAL["llm"])을 Ollama의 모델 정보와 맞춘다.

    반환: {"id"(답을 보관하는 이름 = 모델 이름), "name", "label"(화면에 보이는 이름), "digest", "think": False, …}
    strict면 받지 않은 모델·클라우드 모델을 오류로 알린다. 아니면 받지 않은 모델도 digest가 빈 글인 채로 돌려준다.
    """
    name = FINAL["llm"]
    if strict:
        m = ollama.check_model(name, listed)
    else:
        m = ollama.find_model(name, listed) or {"name": name, "size": 0, "digest": "", "params": "", "quant": "",
                                                "thinking": True, "cloud": False}
    return dict(m, id=m["name"], think=False, label=m["name"])


def _key(m: dict, plan: dict, user: str) -> str:
    return answer_key(m["id"], m["digest"], plan["system"], user, prompts.MAX_TOKENS)


# ---------------------------------------------------------------- 글과 분류기 점수

def load_data(env: Env, scorer: mcore.Scorer, log: Callable[[str], None], fresh: bool = False) -> dict:
    """시험용 문서에서 정답이 붙은 덩어리와 그 분류기 점수를 모은다. 분류기 단계에 걸린 시간도 함께 잰다("timing").

    fresh: 보관해 둔 계산을 쓰지 않고 점수를 모두 다시 계산한다(분류기에 걸리는 시간을 잴 때). 점수는 같고 시간만 더 든다.

    시험용 문서에 '예'와 '아니오' 정답이 모두 있어야 한다. 없으면 정답이 붙은 모든 문서로 대신하고 그 사실을 알린다
    (그때는 분류기가 이미 본 글이 섞여서 분류기 쪽 수치가 실제보다 좋게 나온다).
    """
    cfg = env.cfg
    docs = load_docs(cfg.out_dir)
    if not docs:
        raise ValueError("%s 폴더에 추출 결과(이름.units.json)가 없습니다. run.bat 으로 문서를 먼저 추출해 주세요." % cfg.out_dir)
    labels = learn.load_labels(cfg.labels)
    if not labels:
        raise ValueError("정답이 없습니다. label.bat 에서 정답을 붙이고 '학습하고 결과 보기'를 먼저 해 주세요.")
    wanted = set(testdocs.read_test_docs(cfg.test_docs))
    label_of = lambda b: learn.block_label(b, labels)

    def counts(ds) -> tuple:
        got = [label_of(b) for d in ds for b in d.blocks]
        return sum(1 for v in got if v == 1), sum(1 for v in got if v == 0)

    test = [d for d in docs if d.name in wanted]
    ty, tn = counts(test)
    part = "test" if ty and tn else "all"
    use = test if part == "test" else docs
    items: List[Item] = []
    spent = {"sec": 0.0, "compute": 0.0, "items": 0, "new": 0, "uniq": 0}        # 분류기 단계에 걸린 시간(문서마다 더한다)
    for d in use:
        ex = SimpleNamespace(doc=d, titles={b.page: b.title for b in d.blocks})
        sc = scorer.score(ex, FINAL["classifier"], FINAL["view"], "after", log, fresh)
        for k, src in (("sec", "wall"), ("compute", "seconds"), ("items", "items"), ("new", "new_items"), ("uniq", "uniq")):
            spent[k] += sc.get(src) or 0
        for b in d.blocks:
            y = label_of(b)
            s = sc["block"].get(b.id)
            if y is None or s is None:
                continue
            items.append(Item(b.uid, d.name, b.page, b.key, b.text, b.title, int(y), float(s), True, len(items)))
    if not any(it.label == 1 for it in items) or not any(it.label == 0 for it in items):
        raise ValueError("정답에 '예'와 '아니오'가 모두 있어야 잴 수 있습니다. label.bat 에서 정답을 더 붙여 주세요.")
    timing = dict(spent, reused=max(0, spent["uniq"] - spent["new"]), docs=len(use), fresh=bool(fresh), at=time.strftime("%Y-%m-%d %H:%M:%S"))
    return {"unit": "block", "part": part, "test_names": [d.name for d in test], "use_names": [d.name for d in use],
            "items": items, "timing": timing}


def pick_threshold(env: Env, items: List[Item], mode: str, custom: Optional[float]) -> tuple:
    """분류기의 문턱과 그 설명. mode: test90 | saved | half | custom"""
    target = float(env.cfg.target)
    pct = int(round(target * 100))
    if mode == "custom":
        return mcore.safe_threshold(custom), "직접 정한 문턱"
    if mode == "half":
        return 0.5, "0.5 (예와 아니오 가능성이 반반인 자리)"
    if mode == "saved":
        saved = mcore.load_thresholds(env.cfg.labels)
        got = (((saved.get("models") or {}).get(FINAL["classifier"]) or {}).get(FINAL["view"]) or {}).get("after")
        if got is None:
            raise ValueError("지난 학습에서 남긴 문턱이 없습니다. label.bat 에서 '학습하고 결과 보기'를 한 번 하면 생깁니다.")
        return float(got), "지난 학습(%s)에서 학습용 문서의 '예' %d%%를 찾던 문턱" % (saved.get("made", ""), pct)
    y = np.array([it.label for it in items])
    s = np.array([it.score for it in items], dtype=float)
    thr = learn.recall_threshold(y, s, target)
    return float(thr), "이 글들에서 '예'의 %d%%를 찾는 문턱" % pct


def _rank(uid: str) -> str:
    return hashlib.sha1(uid.encode("utf-8")).hexdigest()


def choose(items: List[Item], thr: float, sample: int, with_rejected: bool) -> List[Item]:
    """LLM에 넣을 글. 통과한 글에서 sample개(0이면 전부)를 고르고, with_rejected면 떨어진 글에서도 같은 수를 고른다.

    고르는 순서는 글의 자리로 정해진 고정된 무작위 순서라서, 다시 돌려도 같은 글이 뽑히고
    표본을 200개에서 400개로 늘리면 앞의 200개가 그대로 들어 있다.
    """
    for it in items:
        it.passed = it.score >= thr
    take = lambda xs: xs if not sample or sample >= len(xs) else sorted(xs, key=lambda it: _rank(it.uid))[:sample]
    chosen = take([it for it in items if it.passed])
    if with_rejected:
        chosen = chosen + take([it for it in items if not it.passed])
    return sorted(chosen, key=lambda it: it.order)


# ---------------------------------------------------------------- LLM의 답 보관

class Answers:
    """받아 둔 답. 한 줄에 답 하나씩 덧붙여 적으므로, 도중에 멈춰도 그때까지의 답이 남는다."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, dict] = {}
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                        self.data[rec["k"]] = rec
                    except Exception:
                        continue

    def get(self, key: str) -> Optional[dict]:
        return self.data.get(key)

    def put(self, key: str, rec: dict) -> None:
        rec = dict(rec, k=key)
        self.data[key] = rec
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def answer_key(model: str, digest: str, system: str, user: str, max_tokens: int) -> str:
    """답을 보관하는 열쇠. 모델(파일의 지문까지) · 앞쪽 글 · 뒤쪽 글 · 답의 길이 · 읽는 길이가 모두 같아야 같은 답으로 본다."""
    raw = json.dumps([model, digest, system, user, max_tokens, ollama.NUM_CTX], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _left(seconds: float) -> str:
    if seconds < 90:
        return "약 %d초" % max(1, int(round(seconds)))
    if seconds < 5400:
        return "약 %d분" % int(round(seconds / 60.0))
    return "약 %d시간 %d분" % (int(seconds // 3600), int(seconds % 3600 // 60))


# ---------------------------------------------------------------- 준비와 실행

def prepare(env: Env, setup: Setup, scorer: mcore.Scorer, log: Callable[[str], None], data: Optional[dict] = None) -> dict:
    """LLM에 묻기 직전까지: 글을 모으고, 문턱을 정하고, 넣을 글을 고르고, 프롬프트를 만든다."""
    cfg = env.cfg
    data = data or load_data(env, scorer, log, bool(setup.fresh))
    thr, thr_note = pick_threshold(env, data["items"], setup.thr_mode, setup.threshold)
    chosen = choose(data["items"], thr, int(setup.sample or 0), bool(setup.with_rejected))
    parts, variant = prompts.load(env.prompts_file, FINAL["variant"])
    system = prompts.system_prompt(variant, parts, prompts.criteria_text(load_sentences(cfg.sentences)))
    plan = {"variant": variant, "system": system, "users": [prompts.user_prompt(it.text) for it in chosen]}
    passed = [it for it in data["items"] if it.passed]
    docs_n = max(1, len(data["use_names"]))
    return {"data": data, "threshold": thr, "thr_note": thr_note, "chosen": chosen, "plan": plan,
            "counts": {"labeled": len(data["items"]), "yes": sum(it.label for it in data["items"]),
                       "passed": len(passed), "passed_yes": sum(it.label for it in passed),
                       "chosen": len(chosen), "chosen_passed": sum(1 for it in chosen if it.passed),
                       "docs": len(data["use_names"]), "passed_per_doc": len(passed) / float(docs_n)}}


def todo_count(prep: dict, m: dict, answers: Answers) -> int:
    """아직 받지 않은 답의 수. m: llm_entry가 준 항목 (받지 않은 모델은 digest가 빈 글이라 모두 새로 물을 것으로 센다)"""
    plan = prep["plan"]
    return sum(1 for u in plan["users"] if not m["digest"] or answers.get(_key(m, plan, u)) is None)


def run(env: Env, setup: Setup, scorer: mcore.Scorer, log: Callable[[str], None], stop=None, data: Optional[dict] = None,
        progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """최종 모델의 LLM에 묻고 결과를 모은다. 반환: 결과(리포트가 읽는 모양)

    stop: 멈추라는 신호(Stop). 켜지면 묻고 있던 글도 바로 끊고, 그때까지 받은 답으로 결과를 만든다.
    progress(받은 수, 받을 수): 새로 받는 답의 진행 상황
    """
    state = ollama.ensure_running(log)
    if not state["ok"]:
        raise ValueError(state["error"])
    m = llm_entry(ollama.models())                 # 받지 않은 모델이면 무거운 일을 하기 전에 알린다
    m["license"] = ollama.license_of(m["name"])
    log("분류기 점수를 모으는 중…")
    prep = prepare(env, setup, scorer, log, data)
    chosen, plan = prep["chosen"], prep["plan"]
    if not chosen:
        raise ValueError("LLM에 넣을 글이 없습니다(분류기 문턱을 넘은 글이 없음). 문턱을 낮춰 보세요.")
    answers = Answers(env.out / "cache" / "answers.jsonl")
    total, done = todo_count(prep, m, answers), 0
    if progress:
        progress(0, total)
    if not total:
        log("받아 둔 답을 그대로 씁니다(새로 물을 글이 없음).")
    rows: List[Optional[dict]] = []
    error = ""
    stat = {"new": 0, "wall": 0.0, "load": 0.0}    # 이번 실행에서 새로 물은 수, 기다린 초, 모델을 불러온 초
    stopped = asked = False
    # 남은 시간 어림: 지금까지 잰 시간의 평균을 쓴다. 받아 둔 답의 시간도 함께 쓴다
    known = [r["sec"] for u in plan["users"] for r in [answers.get(_key(m, plan, u))] if r]
    seen = [float(sum(known)), len(known)]         # [걸린 초의 합, 개수]

    def eta() -> str:
        return " · 남은 시간 %s" % _left((total - done) * seen[0] / seen[1]) if seen[1] >= 3 else ""
    for i, user in enumerate(plan["users"]):
        key = _key(m, plan, user)
        rec = answers.get(key)
        if rec is None and not stopped and not error:
            if stop is not None and stop.is_set():
                stopped = True
            else:
                asked = True
                log("%s · %s · %d/%d번째 글 (새로 묻는 것 %d/%d%s)" % (m["label"], plan["variant"].label, i + 1, len(plan["users"]), done + 1, total, eta()))
                handle = ollama.Call()
                if stop is not None:
                    stop.call = handle
                t_ask = time.perf_counter()
                try:
                    if stop is not None and stop.is_set():
                        raise ollama.Cancelled()
                    rec = _ask(m, plan["system"], user, handle)
                except ollama.Cancelled:           # 멈추기: 묻고 있던 글은 버리고 여기서 끝낸다
                    stopped, rec = True, None
                except ollama.OllamaError as exc:
                    error = str(exc)
                    log("  실패: %s" % exc)
                else:
                    answers.put(key, rec)
                    done += 1
                    stat["new"] += 1
                    stat["wall"] += time.perf_counter() - t_ask
                    stat["load"] += float(rec.get("load") or 0.0)
                    seen[0], seen[1] = seen[0] + rec["sec"], seen[1] + 1
                    if progress:
                        progress(done, total)
                finally:
                    if stop is not None:
                        stop.call = None
        rows.append(rec)
    if stopped:
        log("멈췄습니다. 받은 답까지로 결과를 만듭니다…")
    if asked:
        ollama.unload(m["name"])                   # 끝나면 메모리를 돌려준다
    return assemble(env, setup, prep, m, rows, error, stopped, state, stat)


def _ask(m: dict, system: str, user: str, handle: Optional[ollama.Call] = None) -> dict:
    """글 하나를 묻는다(생각 모드 끔, 답은 한 단어). 반환: 보관하는 답 한 줄"""
    n, timeout = prompts.MAX_TOKENS, 900.0
    t0 = time.time()
    try:
        out = ollama.chat(m["name"], system, user, n, False, handle, timeout)
    except ollama.OllamaError:
        if handle is not None and handle.cancelled:
            raise ollama.Cancelled()
        time.sleep(2.0)                                # 한 번은 다시 해 본다
        t0 = time.time()
        out = ollama.chat(m["name"], system, user, n, False, handle, timeout)
    wall = time.time() - t0
    ans = prompts.read_answer(out["content"], out["logprobs"])
    sec = max(0.0, (out["total_s"] - out["load_s"]) if out["total_s"] else wall)      # 모델을 불러오는 시간은 뺀다
    return {"verdict": ans["verdict"], "p": None if ans["p"] is None else round(ans["p"], 5),
            "content": out["content"][:400],
            "thought": bool(out["thinking"]) and not out["content"].strip(),      # 생각 모드를 끄지 못하는 옛 Ollama에서 생각만 하다 끊긴 답
            "sec": round(sec, 3), "load": round(out["load_s"], 2), "in": out["in"], "out": out["out"],
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------- 수치

def prf(tp: float, fp: float, fn: float, tn: float) -> dict:
    """정답과 견준 네 칸의 수 → 정밀도 · 재현율 · F1 · 정확도.

        tp  정답 '예' · 판단 '예'  (맞은 예)          fp  정답 '아니오' · 판단 '예'  (틀린 예)
        fn  정답 '예' · 판단 '아니오'  (놓친 예)      tn  정답 '아니오' · 판단 '아니오'  (맞은 아니오)

        정밀도(precision) = tp ÷ (tp + fp)      '예'라고 한 것 가운데 진짜 '예'의 비율
        재현율(recall)    = tp ÷ (tp + fn)      진짜 '예' 가운데 '예'라고 찾아낸 비율
        F1                = 2 × 정밀도 × 재현율 ÷ (정밀도 + 재현율) = 2·tp ÷ (2·tp + fp + fn)
        정확도(accuracy)  = (tp + tn) ÷ 전체

    나눌 수가 0이면 그 값은 None이다(예: '예'라고 한 것이 하나도 없으면 정밀도를 정할 수 없다).
    F1은 진짜 '예'나 '예'라고 한 것이 하나라도 있으면 정해지고, 맞은 예가 없으면 0이다.
    """
    total = tp + fp + fn + tn
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "said_yes": tp + fp,
            "precision": tp / float(tp + fp) if tp + fp > 0 else None,
            "recall": tp / float(tp + fn) if tp + fn > 0 else None,
            "f1": 2.0 * tp / float(2 * tp + fp + fn) if 2 * tp + fp + fn > 0 else None,
            "accuracy": (tp + tn) / float(total) if total > 0 else None}


def _f1(y: np.ndarray, pred: np.ndarray) -> Optional[float]:
    tp = int((pred & (y == 1)).sum())
    fp = int((pred & (y == 0)).sum())
    fn = int((~pred & (y == 1)).sum())
    return 2.0 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn > 0 else None


def _prf_of(y: np.ndarray, pred: np.ndarray) -> dict:
    return prf(int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum()), int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum()))


def _boot_f1(y: np.ndarray, pred: np.ndarray, base: Optional[np.ndarray] = None) -> dict:
    """글을 다시 뽑아 BOOT번 재 본 F1의 95% 범위. base(견줄 판단)를 주면 F1 차이(pred − base)의 범위도 함께 낸다.

    글이 20개보다 적으면 재지 않는다(빈 것을 돌려준다).
    """
    n = len(y)
    out: dict = {}
    if n < 20:
        return out
    rng = np.random.RandomState(0)
    vals, diffs = [], []
    for _ in range(BOOT):
        idx = rng.randint(0, n, n)
        v = _f1(y[idx], pred[idx])
        if v is None:
            continue
        vals.append(v)
        if base is not None:
            b = _f1(y[idx], base[idx])
            if b is not None:
                diffs.append(v - b)
    if len(vals) >= BOOT // 2:
        out["f1_lo"], out["f1_hi"] = (float(x) for x in np.percentile(vals, [2.5, 97.5]))
    if len(diffs) >= BOOT // 2:
        out["gain_lo"], out["gain_hi"] = (float(x) for x in np.percentile(diffs, [2.5, 97.5]))
    return out


def classifier_only(items: List[Item], thr: float) -> dict:
    """LLM 없이 분류기만 쓸 때의 지표를 정답이 붙은 글 전체로 잰다. 두 가지 문턱으로 잰다.

        now   지금 문턱(LLM에 넘길 글을 고른 문턱)에서: 통과한 글을 모두 '예'로 볼 때
        best  F1이 가장 높아지는 문턱에서: 문턱만 조절해서 얻을 수 있는 가장 높은 F1.
              이 글들의 정답을 보고 고른 문턱이라 분류기에 유리하게 나온 값이다(새 문서에서는 이보다 낮을 수 있다).
    """
    y = np.array([it.label for it in items])
    s = np.array([it.score for it in items], dtype=float)
    now = _prf_of(y, s >= thr)
    now.update(threshold=float(thr), **_boot_f1(y, s >= thr))
    best, best_thr = None, None
    for t in np.unique(s):
        m = _prf_of(y, s >= t)
        if m["f1"] is not None and (best is None or m["f1"] > best["f1"] + 1e-12):
            best, best_thr = m, float(t)
    if best is not None:
        best["threshold"] = best_thr
    return {"n": len(items), "yes": int((y == 1).sum()), "now": now, "best": best}


def pipeline(items: List[Item], chosen: List[Item], rows: List[Optional[dict]], complete: bool) -> Optional[dict]:
    """분류기 + LLM 전체 흐름의 지표를 정답이 붙은 글 전체로 잰다.

    최종 판단 '예' = 분류기 문턱을 넘었고, LLM이 '아니오'라고 하지 않은 글(읽지 못한 답은 '예'로 남긴다).
    분류기가 떨어뜨린 정답 '예'는 LLM이 보지도 못했지만 전체 흐름에서는 놓친 것이므로 놓친 예(fn)에 넣는다.

    통과한 글을 모두 물었으면 그대로 센다(exact). 표본만 물었으면 물은 글의 결과를 통과한 글 전체의 크기로 늘려 어림한다
    (표본은 고정된 무작위 순서로 뽑으므로 치우치지 않는다). 도중에 멈춘 조합은 받은 글이 문서 앞쪽에 몰려 있어 재지 않는다.
    """
    answered = {it.uid: r for it, r in zip(chosen, rows) if it.passed and r is not None}
    passed = [it for it in items if it.passed]
    if not answered or not passed or not complete:
        return None
    asked = [it for it in passed if it.uid in answered]
    keep = lambda it: answered[it.uid]["verdict"] != 0
    kept_yes = sum(1 for it in asked if keep(it) and it.label == 1)
    kept_no = sum(1 for it in asked if keep(it) and it.label == 0)
    lost_yes = sum(1 for it in asked if not keep(it) and it.label == 1)
    removed_no = sum(1 for it in asked if not keep(it) and it.label == 0)
    missed_yes = sum(1 for it in items if not it.passed and it.label == 1)       # 분류기가 떨어뜨린 정답 '예'
    rejected_no = sum(1 for it in items if not it.passed and it.label == 0)
    exact = len(asked) == len(passed)
    f = len(passed) / float(len(asked))
    num = (lambda v: v) if exact else (lambda v: round(v * f, 1))
    out = prf(num(kept_yes), num(kept_no), num(lost_yes) + missed_yes, num(removed_no) + rejected_no)
    out.update(exact=exact, asked=len(asked), passed=len(passed), n=len(items), missed_yes=missed_yes, lost_yes=num(lost_yes))
    if exact:                                       # 범위는 모두 물었을 때만: 글 전체를 다시 뽑아 잰다
        y = np.array([it.label for it in items])
        base = np.array([it.passed for it in items], dtype=bool)
        final = np.array([it.passed and keep(it) for it in items], dtype=bool)
        out.update(_boot_f1(y, final, base))
    return out


def _base_kept(y: np.ndarray, s: np.ndarray, k: int) -> Optional[int]:
    """분류기의 문턱만 올려 '예'를 k개 남길 때 남는 글의 수."""
    pos = np.sort(s[y == 1])[::-1]
    if k <= 0 or not len(pos):
        return None
    return int((s >= pos[min(k, len(pos)) - 1]).sum())


def _curve(y: np.ndarray, s: np.ndarray) -> List[list]:
    """문턱을 움직일 때 (남긴 비율, 지킨 '예'의 비율)이 그리는 선."""
    n, yes = len(y), int((y == 1).sum())
    pts = []
    for thr in np.unique(s)[::-1]:
        keep = s >= thr
        pts.append([round(float(keep.sum()) / n, 4), round(float((keep & (y == 1)).sum()) / max(yes, 1), 4)])
    if len(pts) > 80:                              # 그림에 넣을 만큼만
        step = len(pts) / 80.0
        pts = [pts[int(i * step)] for i in range(80)] + [pts[-1]]
    return [[0.0, 0.0]] + pts


def measure(items: List[Item], rows: List[Optional[dict]]) -> Optional[dict]:
    """LLM 단계의 결과를 잰다. 분류기가 통과시킨 글 가운데 답을 받은 것만 쓴다."""
    pairs = [(it, r) for it, r in zip(items, rows) if it.passed and r is not None]
    if not pairs:
        return None
    y = np.array([it.label for it, _ in pairs])
    s = np.array([it.score for it, _ in pairs], dtype=float)
    kept = np.array([r["verdict"] != 0 for _, r in pairs])              # 읽지 못한 답은 덜어내지 않는다
    p = np.array([r["p"] if r["p"] is not None else (0.5 if r["verdict"] is None else float(r["verdict"])) for _, r in pairs])
    n, yes = len(y), int((y == 1).sum())
    no = n - yes
    kept_n, kept_yes = int(kept.sum()), int((kept & (y == 1)).sum())
    base = _base_kept(y, s, kept_yes)
    out = {"n": n, "yes": yes, "no": no, "kept": kept_n, "kept_yes": kept_yes, "kept_no": kept_n - kept_yes,
           "lost_yes": yes - kept_yes, "removed_no": no - (kept_n - kept_yes),
           # 정답과 같은 판단의 비율: (정답 예를 예로 + 정답 아니오를 아니오로) ÷ 전체.  base_acc: LLM 없이 모두 '예'로 둘 때
           "acc": (kept_yes + no - (kept_n - kept_yes)) / float(n), "base_acc": yes / float(n),
           "unknown": sum(1 for _, r in pairs if r["verdict"] is None), "no_prob": sum(1 for _, r in pairs if r["p"] is None),
           "thought": sum(1 for _, r in pairs if r.get("thought")),
           "base_kept": base, "gain": None if base is None else base - kept_n, "gain_lo": None, "gain_hi": None,
           "auc_llm": learn.auc(y, p) if yes and no else None, "auc_cls": learn.auc(y, s) if yes and no else None,
           "curve": _curve(y, p) if yes else []}
    if base is not None and n >= 20:               # 차이의 범위: 글을 다시 뽑아 1000번 재 본다
        rng = np.random.RandomState(0)
        diffs = []
        for _ in range(BOOT):
            idx = rng.randint(0, n, n)
            yy, ss, kk = y[idx], s[idx], kept[idx]
            b = _base_kept(yy, ss, int((kk & (yy == 1)).sum()))
            if b is not None:
                diffs.append(b - int(kk.sum()))
        if len(diffs) >= BOOT // 2:
            out["gain_lo"], out["gain_hi"] = (float(v) for v in np.percentile(diffs, [2.5, 97.5]))
    # LLM 단계만의 지표: 분류기가 통과시킨 글 안에서, LLM이 남긴 것을 '예'라고 한 것으로 본다
    stage = prf(kept_yes, kept_n - kept_yes, yes - kept_yes, no - (kept_n - kept_yes))
    stage.update(_boot_f1(y, kept, np.ones(n, dtype=bool)))        # 견주는 쪽: LLM 없이 모두 '예'
    out["stage"] = stage
    out["stage_base"] = prf(yes, no, 0, 0)                          # LLM 없이(통과한 글을 모두 '예'로) 둘 때
    secs = np.array([r["sec"] for _, r in pairs], dtype=float)
    out.update(sec_mean=float(secs.mean()), sec_median=float(np.median(secs)), sec_total=float(secs.sum()),
               sec_min=float(secs.min()), sec_max=float(secs.max()),
               tok_in=float(np.mean([r["in"] for _, r in pairs])), tok_out=float(np.mean([r["out"] for _, r in pairs])))
    return out


def assemble(env: Env, setup: Setup, prep: dict, m: dict, rows: List[Optional[dict]], error: str,
             stopped: bool, state: dict, stat: Optional[dict] = None) -> dict:
    """리포트가 읽는 결과를 만든다(JSON으로 적을 수 있는 모양). stat: 이번 실행에서 새로 물은 수와 기다린 시간

    조합이 하나뿐이어도 "llms" · "variants" · "combos"는 목록으로 둔다(4.x의 결과와 같은 모양이라 리포트와 지난 실행 목록이 그대로 읽는다).
    """
    from screening import models as smodels

    cfg, data, chosen, plan = env.cfg, prep["data"], prep["chosen"], prep["plan"]
    v = plan["variant"]
    spec = smodels.MODEL_BY_KEY.get(FINAL["classifier"]) or {}
    clf = mcore.load_classifier(cfg.labels, FINAL["classifier"], data["unit"]) or {}
    passed = [it for it in chosen if it.passed]
    y = np.array([it.label for it in passed])
    s = np.array([it.score for it in passed], dtype=float)
    baseline = classifier_only(data["items"], prep["threshold"])     # LLM 없이 분류기만 쓸 때(견줄 기준)
    cid = "%s|%s" % (m["id"], v.key)
    done = sum(1 for r in rows if r is not None)
    pipe = pipeline(data["items"], chosen, rows, bool(rows) and done == len(rows))
    if pipe is not None and pipe["f1"] is not None and baseline["now"]["f1"] is not None:
        pipe["f1_gain"] = pipe["f1"] - baseline["now"]["f1"]          # 분류기만 쓸 때보다 F1이 얼마나 달라졌나
    combo = {"id": cid, "llm": m["label"], "variant": v.key, "name": v.name, "done": done, "total": len(rows), "error": error,
             "metrics": measure(chosen, rows), "pipeline": pipe, "timing": dict(stat or {"new": 0, "wall": 0.0, "load": 0.0})}
    return {
        "made": time.strftime("%Y-%m-%d %H:%M:%S"), "stopped": stopped, "ollama": state.get("version", ""),
        "setup": {"classifier": FINAL["classifier"], "view": FINAL["view"], "thr_mode": setup.thr_mode, "sample": int(setup.sample or 0),
                  "with_rejected": bool(setup.with_rejected), "llms": [m["label"]], "variants": [v.key]},
        "classifier": {"key": FINAL["classifier"], "label": spec.get("label", FINAL["classifier"]), "view": FINAL["view"],
                       "view_name": mcore.VIEW_NAME[FINAL["view"]], "unit": data["unit"], "trained": clf.get("trained", ""),
                       "yes": clf.get("yes"), "no": clf.get("no"), "threshold": prep["threshold"], "thr_note": prep["thr_note"],
                       "title_weight": float(cfg.title_weight or 0.0), "target": float(cfg.target)},
        "data": dict(prep["counts"], part=data["part"], docs_used=data["use_names"],
                     base_curve=_curve(y, s) if len(y) and (y == 1).any() else []),
        "llms": [{"name": m["label"], "model": m["name"], "think": False, "digest": m["digest"], "params": m["params"], "quant": m["quant"],
                  "size": m["size"], "license": m.get("license", ""), "thinking": m["thinking"]}],
        "variants": [{"key": v.key, "name": v.name, "parts": v.parts, "max_tokens": prompts.MAX_TOKENS, "system": plan["system"],
                      "sample_user": (plan["users"] or [""])[0]}],
        "items": [{"doc": it.doc, "page": it.page, "text": it.text[:1500], "label": it.label, "score": round(it.score, 4),
                   "passed": it.passed} for it in chosen],
        "answers": {cid: [None if r is None else {"v": r["verdict"], "p": r["p"], "sec": r["sec"],
                                                  "raw": r.get("content", "") if r["verdict"] is None else ""} for r in rows]},
        "combos": [combo], "baseline": baseline, "timing": {"classifier": data.get("timing")},
        "prompts_file": str(env.prompts_file), "sentences_file": str(cfg.sentences),
    }


def best_f1_combo(result: dict) -> Optional[dict]:
    """전체 흐름(분류기 + LLM)의 지표가 나온 조합(끝까지 돌았을 때만). 5.0부터 조합은 하나다."""
    done = [c for c in result["combos"] if c.get("pipeline") and c["pipeline"]["f1"] is not None]
    return max(done, key=lambda c: (c["pipeline"]["f1"], c["pipeline"]["recall"] or 0.0, -c["metrics"]["sec_mean"])) if done else None


def best_combo(result: dict) -> Optional[dict]:
    """끝까지 돌았고 분류기 문턱만 올린 것과 견줄 수 있는 조합. 5.0부터 조합은 하나다."""
    done = [c for c in result["combos"] if c["metrics"] and c["done"] == c["total"] and c["metrics"]["gain"] is not None]
    return max(done, key=lambda c: (c["metrics"]["gain"], -c["metrics"]["sec_mean"])) if done else None
