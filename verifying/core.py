"""검증의 계산 부분: 분류기 점수로 통과한 글을 추리고, LLM에 물어 답을 모으고, 얼마나 나아졌는지 잰다.

학습·시험·평가(screen.py, label.py)와는 따로 돈다. 이 모듈은
    out 폴더의 문서 목록, 정답(labels), 분류기(labels/classifiers), 시험용 문서 목록을 읽기만 하고 고치지 않는다.
    분류기는 그때그때 파일에서 읽으므로, 다시 학습하면 다음 실행부터 새 분류기를 쓴다.
    LLM의 답은 out/verify/cache/answers.jsonl 에 쌓아 두고 다시 묻지 않는다(모델·프롬프트·글이 모두 같을 때).

재는 방법
    시험용 문서(학습에 쓰지 않은 문서)에서 정답이 붙은 글만 쓴다.
    분류기가 문턱 이상으로 본 글(통과한 글)을 LLM에 넣고, LLM이 '아니오'라고 한 글을 덜어낸다.
    덜어낸 '아니오'가 많고 잃은 '예'가 적을수록 좋다. 그런데 분류기의 문턱만 올려도 같은 일이 일어나므로,
    '예'를 같은 수만큼 남길 때 분류기 문턱만 올린 것보다 LLM이 얼마나 더 줄였는지를 함께 잰다.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional

import numpy as np

from marking import core as mcore
from screening import learn, testdocs
from screening.items import load_docs
from screening.sentences import load_sentences

from . import ollama, prompts

DEFAULT_CLASSIFIER = "me5-small"
DEFAULT_VIEW = "line"
# 화면에 늘 보여 주는 LLM. 첫 번째가 기본으로 켜진다. 받아 둔 다른 모델도 화면에서 고를 수 있다
# Qwen3.5는 넣지 않는다: 모델 구조상 글마다 프롬프트 전체를 다시 읽어서, 같은 지시문에 글만 바꿔 묻는 이 일에서는 몇 배 느리다.
# 4B는 이름에 instruct가 붙은 것을 쓴다. Ollama의 qwen3:4b는 늘 생각부터 하는 판이라 생각 모드를 끌 수 없다.
OFFERED_LLMS = [("qwen3:4b-instruct", "기본. Qwen3 4B · Apache 2.0 · 내려받기 약 2.5GB"),
                ("qwen3:8b", "선택. Qwen3 8B · Apache 2.0 · 내려받기 약 5.2GB · 더 크고 느림")]
DEFAULT_LLMS = [OFFERED_LLMS[0][0]]
DEFAULT_SAMPLE = 200
N_EXAMPLES = 3                # 프롬프트 예시: '예' 3개, '아니오' 3개
BOOT = 1000                   # 차이의 범위를 어림할 때 다시 뽑는 횟수
THR_MODES = [("test90", "시험 문서에서 '예'의 {pct}%를 찾는 문턱"), ("saved", "지난 학습에서 '예'의 {pct}%를 찾던 문턱"),
             ("half", "0.5"), ("custom", "직접 정하기")]


@dataclass
class Env:
    cfg: object                   # 걸러내기의 설정(screening.cli.Config)
    prompts_file: Path

    @property
    def out(self) -> Path:
        return Path(self.cfg.out_dir) / "verify"


@dataclass
class Setup:
    """화면에서 고른 것."""
    classifier: str = DEFAULT_CLASSIFIER
    view: str = DEFAULT_VIEW                  # block | agg | line
    thr_mode: str = "test90"
    threshold: Optional[float] = None         # thr_mode가 custom일 때
    llms: List[str] = field(default_factory=lambda: list(DEFAULT_LLMS))
    variants: List[str] = field(default_factory=list)       # 안의 기호. 비어 있으면 모두
    sample: int = DEFAULT_SAMPLE              # 0이면 전체
    with_rejected: bool = False               # 분류기가 떨어뜨린 글도 LLM에 넣어 본다


@dataclass
class Item:
    uid: str
    doc: str
    page: int
    unit: str                 # block | line
    key: str
    text: str
    title: str
    label: int                # 정답: 1 예, 0 아니오
    score: float              # 분류기 점수
    around: List[str] = field(default_factory=list)      # 주변 글
    passed: bool = True       # 분류기 문턱을 넘었는가
    order: int = 0            # 문서에 나온 순서


class Stopped(Exception):
    pass


# ---------------------------------------------------------------- 글과 분류기 점수

def load_data(env: Env, scorer: mcore.Scorer, classifier: str, view: str, log: Callable[[str], None]) -> dict:
    """시험용 문서에서 정답이 붙은 글과 그 분류기 점수를 모은다.

    시험용 문서에 '예'와 '아니오' 정답이 모두 있어야 한다. 없으면 정답이 붙은 모든 문서로 대신하고 그 사실을 알린다
    (그때는 분류기가 이미 본 글이 섞여서 분류기 쪽 수치가 실제보다 좋게 나온다).
    """
    cfg = env.cfg
    if view not in mcore.VIEW_NAME:
        raise ValueError("넣는 크기를 알 수 없습니다: %s" % view)
    docs = load_docs(cfg.out_dir)
    if not docs:
        raise ValueError("%s 폴더에 추출 결과(이름.units.json)가 없습니다. run.bat 으로 문서를 먼저 추출해 주세요." % cfg.out_dir)
    labels = learn.load_labels(cfg.labels)
    if not labels:
        raise ValueError("정답이 없습니다. label.bat 에서 정답을 붙이고 '학습하고 결과 보기'를 먼저 해 주세요.")
    unit = "line" if view == "line" else "block"
    wanted = set(testdocs.read_test_docs(cfg.test_docs))

    def label_of(b, l=None) -> Optional[int]:
        return labels.get(l.key) if l is not None else learn.block_label(b, labels)

    def things(d):
        for bi, b in enumerate(d.blocks):
            if unit == "line":
                for l in b.lines:
                    yield bi, b, l
            else:
                yield bi, b, None

    def counts(ds) -> tuple:
        got = [label_of(b, l) for d in ds for _, b, l in things(d)]
        return sum(1 for v in got if v == 1), sum(1 for v in got if v == 0)

    test = [d for d in docs if d.name in wanted]
    ty, tn = counts(test)
    part = "test" if ty and tn else "all"
    use = test if part == "test" else docs
    test_keys = {(l.key if l is not None else b.key) for d in test for _, b, l in things(d)}
    items: List[Item] = []
    for d in use:
        ex = SimpleNamespace(doc=d, titles={b.page: b.title for b in d.blocks})
        sc = scorer.score(ex, classifier, view, "after", log)
        for bi, b, l in things(d):
            y = label_of(b, l)
            s = sc["line"].get(l.id) if l is not None else sc["block"].get(b.id)
            if y is None or s is None:
                continue
            if l is not None:
                around = [o.text for o in b.lines if o is not l]
                items.append(Item(l.uid, d.name, b.page, "line", l.key, l.text, b.title, int(y), float(s), around, True, len(items)))
            else:
                around = [o.text for o in d.blocks[max(0, bi - 1):bi] + d.blocks[bi + 1:bi + 2] if o.page == b.page]
                items.append(Item(b.uid, d.name, b.page, "block", b.key, b.text, b.title, int(y), float(s), around, True, len(items)))
    if not any(it.label == 1 for it in items) or not any(it.label == 0 for it in items):
        raise ValueError("정답에 '예'와 '아니오'가 모두 있어야 잴 수 있습니다. label.bat 에서 정답을 더 붙여 주세요.")
    return {"docs": docs, "labels": labels, "unit": unit, "part": part, "test_names": [d.name for d in test],
            "use_names": [d.name for d in use], "test_keys": test_keys, "items": items}


def pick_threshold(env: Env, items: List[Item], classifier: str, view: str, mode: str, custom: Optional[float]) -> tuple:
    """분류기의 문턱과 그 설명. mode: test90 | saved | half | custom"""
    target = float(env.cfg.target)
    pct = int(round(target * 100))
    if mode == "custom":
        return mcore.safe_threshold(custom), "직접 정한 문턱"
    if mode == "half":
        return 0.5, "0.5 (예와 아니오 가능성이 반반인 자리)"
    if mode == "saved":
        saved = mcore.load_thresholds(env.cfg.labels)
        got = (((saved.get("models") or {}).get(classifier) or {}).get(view) or {}).get("after")
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


# ---------------------------------------------------------------- 프롬프트 예시

def pick_examples(env: Env, data: dict) -> List[dict]:
    """프롬프트에 넣을 예시(예 3, 아니오 3)를 학습용 문서의 정답에서 뽑는다. 시험용 문서에 나오는 글은 뽑지 않는다.

    한 번 뽑은 예시는 out/verify/examples.json 에 적어 두고 계속 쓴다(예시가 바뀌면 그 안의 답을 모두 다시 받아야 하므로).
    정답이 바뀌었거나 없어진 예시만 새로 채운다.
    """
    unit = data["unit"]
    labels = data["labels"]
    test = set(data["test_names"]) if data["part"] == "test" else set()
    pool: Dict[str, dict] = {}
    for d in data["docs"]:
        if d.name in test:
            continue
        for b in d.blocks:
            things = [(l.key, l.text, labels.get(l.key)) for l in b.lines] if unit == "line" else [(b.key, b.text, learn.block_label(b, labels))]
            for key, text, y in things:
                flat = " ".join(text.split())
                if y is None or key in data["test_keys"] or not 12 <= len(flat) <= 400:
                    continue
                pool.setdefault(key, {"key": key, "text": flat, "label": int(y)})
    path = env.out / "examples.json"
    saved = {}
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        saved = {}
    kept = [e for e in (saved.get(unit) or []) if e.get("key") in pool and pool[e["key"]]["label"] == e.get("label")]
    out: List[dict] = []
    for label in (1, 0):
        have = [pool[e["key"]] for e in kept if e["label"] == label][:N_EXAMPLES]
        used = {e["key"] for e in have}
        rest = sorted((e for e in pool.values() if e["label"] == label and e["key"] not in used), key=lambda e: _rank(e["key"]))
        out.append(have + rest[:N_EXAMPLES - len(have)])
    mixed = [e for pair in zip(out[0], out[1]) for e in pair] + out[0][len(out[1]):] + out[1][len(out[0]):]
    if [e["key"] for e in mixed] != [e.get("key") for e in (saved.get(unit) or [])]:
        saved[unit] = mixed
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=1), encoding="utf-8")
    return mixed


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
    """LLM에 묻기 직전까지: 글을 모으고, 문턱을 정하고, 넣을 글을 고르고, 안마다의 프롬프트를 만든다."""
    cfg = env.cfg
    data = data or load_data(env, scorer, setup.classifier, setup.view, log)
    thr, thr_note = pick_threshold(env, data["items"], setup.classifier, setup.view, setup.thr_mode, setup.threshold)
    chosen = choose(data["items"], thr, int(setup.sample or 0), bool(setup.with_rejected))
    parts, variants = prompts.load(env.prompts_file)
    if setup.variants:
        unknown = [k for k in setup.variants if not any(v.key == k for v in variants)]
        if unknown:
            raise ValueError("프롬프트 파일에 없는 안입니다: %s" % ", ".join(unknown))
        variants = [v for v in variants if v.key in setup.variants]
    criteria = prompts.criteria_text(load_sentences(cfg.sentences))
    examples = pick_examples(env, data) if any(v.uses_examples for v in variants) and "예시" not in parts else []
    if examples and data["part"] != "test":        # 시험용 문서가 없을 때: 예시로 쓴 글은 채점에서 뺀다
        used = {e["key"] for e in examples}
        chosen = [it for it in chosen if it.key not in used]
    ex_text = prompts.examples_text(examples)
    word = "같은 덩어리의 다른 줄" if data["unit"] == "line" else "앞뒤 덩어리"
    plans = []
    for v in variants:
        system = prompts.system_prompt(v, parts, criteria, ex_text)
        users = [prompts.user_prompt(v, it.text, prompts.context_text(it.title, it.around, word) if v.uses_context else "")
                 for it in chosen]
        plans.append({"variant": v, "system": system, "users": users})
    passed = [it for it in data["items"] if it.passed]
    docs_n = max(1, len(data["use_names"]))
    return {"data": data, "threshold": thr, "thr_note": thr_note, "chosen": chosen, "plans": plans, "examples": examples,
            "counts": {"labeled": len(data["items"]), "yes": sum(it.label for it in data["items"]),
                       "passed": len(passed), "passed_yes": sum(it.label for it in passed),
                       "chosen": len(chosen), "chosen_passed": sum(1 for it in chosen if it.passed),
                       "docs": len(data["use_names"]), "passed_per_doc": len(passed) / float(docs_n)}}


def todo_counts(prep: dict, llms: List[dict], answers: Answers) -> Dict[str, int]:
    """모델 × 안마다 아직 받지 않은 답의 수. llms: [{"name", "digest"}] (받지 않은 모델은 digest가 빈 글)"""
    out = {}
    for m in llms:
        for plan in prep["plans"]:
            v = plan["variant"]
            n = sum(1 for u in plan["users"]
                    if not m["digest"] or answers.get(answer_key(m["name"], m["digest"], plan["system"], u, v.max_tokens)) is None)
            out["%s|%s" % (m["name"], v.key)] = n
    return out


def run(env: Env, setup: Setup, scorer: mcore.Scorer, log: Callable[[str], None], stop=None, data: Optional[dict] = None,
        progress: Optional[Callable[[int, int], None]] = None) -> dict:
    """고른 모델 × 안으로 LLM에 묻고 결과를 모은다. 반환: 결과(리포트가 읽는 모양)

    stop: 멈추라는 신호(threading.Event).  progress(받은 수, 받을 수): 새로 받는 답의 진행 상황
    """
    state = ollama.ensure_running(log)
    if not state["ok"]:
        raise ValueError(state["error"])
    if not setup.llms:
        raise ValueError("LLM을 하나 이상 골라 주세요.")
    listed = ollama.models()
    llms = []
    for name in setup.llms:                        # 쓸 수 없는 모델이면 무거운 일을 하기 전에 알린다
        m = ollama.check_model(name, listed)
        llms.append(dict(m, license=ollama.license_of(m["name"])))
    log("분류기 점수를 모으는 중…")
    prep = prepare(env, setup, scorer, log, data)
    chosen = prep["chosen"]
    if not chosen:
        raise ValueError("LLM에 넣을 글이 없습니다(분류기 문턱을 넘은 글이 없음). 문턱을 낮춰 보세요.")
    answers = Answers(env.out / "cache" / "answers.jsonl")
    todo = todo_counts(prep, llms, answers)
    total, done = sum(todo.values()), 0
    if progress:
        progress(0, total)
    if not total:
        log("받아 둔 답을 그대로 씁니다(새로 물을 글이 없음).")
    got: Dict[str, list] = {}
    errors: Dict[str, str] = {}
    stopped = False
    last = None
    # 남은 시간 어림: 조합마다 지금까지 잰 시간의 평균을 쓴다. 아직 재지 않은 조합은 같은 종류(짧은 답/긴 답)의 평균으로 대신한다
    left_n = dict(todo)
    timing: Dict[str, list] = {}                   # 조합 → [걸린 초의 합, 개수]
    kinds = {"%s|%s" % (m["name"], plan["variant"].key): plan["variant"].long for m in llms for plan in prep["plans"]}
    for m in llms:                                 # 받아 둔 답의 시간도 어림에 쓴다
        for plan in prep["plans"]:
            v = plan["variant"]
            secs = [r["sec"] for u in plan["users"] for r in [answers.get(answer_key(m["name"], m["digest"], plan["system"], u, v.max_tokens))] if r]
            if secs:
                timing["%s|%s" % (m["name"], v.key)] = [float(sum(secs)), len(secs)]

    def eta() -> str:
        known = {c: t[0] / t[1] for c, t in timing.items() if t[1] >= 3}
        if not known:
            return ""
        by_kind = {}
        for c, sec in known.items():
            by_kind.setdefault(kinds.get(c, False), []).append(sec)
        every = sum(known.values()) / len(known)
        guess = lambda c: known.get(c) or (sum(by_kind[kinds[c]]) / len(by_kind[kinds[c]]) if by_kind.get(kinds.get(c)) else every)
        return " · 남은 시간 %s" % _left(sum(n * guess(c) for c, n in left_n.items() if n > 0))
    for m in llms:
        for plan in prep["plans"]:
            v = plan["variant"]
            cid = "%s|%s" % (m["name"], v.key)
            rows: List[Optional[dict]] = []
            for i, user in enumerate(plan["users"]):
                key = answer_key(m["name"], m["digest"], plan["system"], user, v.max_tokens)
                rec = answers.get(key)
                if rec is None and not stopped and cid not in errors:
                    if stop is not None and stop.is_set():
                        stopped = True
                    else:
                        if last and last != m["name"]:
                            ollama.unload(last)        # 메모리에 모델을 하나만 올려 둔다
                        last = m["name"]
                        log("%s · %s · %d/%d번째 글 (전체 %d/%d%s)" % (m["name"], v.label, i + 1, len(plan["users"]), done + 1, total, eta()))
                        try:
                            rec = _ask(m["name"], plan["system"], user, v)
                        except ollama.OllamaError as exc:
                            errors[cid] = str(exc)
                            left_n[cid] = 0
                            log("  실패: %s" % exc)
                        else:
                            answers.put(key, rec)
                            done += 1
                            left_n[cid] = left_n.get(cid, 1) - 1
                            t = timing.setdefault(cid, [0.0, 0])
                            t[0], t[1] = t[0] + rec["sec"], t[1] + 1
                            if progress:
                                progress(done, total)
                rows.append(rec)
            got[cid] = rows
    if last:
        ollama.unload(last)                            # 끝나면 메모리를 돌려준다
    return assemble(env, setup, prep, llms, got, errors, stopped, state)


def _ask(model: str, system: str, user: str, v: prompts.Variant) -> dict:
    t0 = time.time()
    try:
        out = ollama.chat(model, system, user, v.max_tokens)
    except ollama.OllamaError:
        time.sleep(2.0)                                # 한 번은 다시 해 본다
        t0 = time.time()
        out = ollama.chat(model, system, user, v.max_tokens)
    wall = time.time() - t0
    ans = prompts.read_answer(out["content"], out["logprobs"], v.long)
    sec = max(0.0, (out["total_s"] - out["load_s"]) if out["total_s"] else wall)      # 모델을 불러오는 시간은 뺀다
    return {"verdict": ans["verdict"], "p": None if ans["p"] is None else round(ans["p"], 5), "reason": ans["reason"],
            "content": out["content"][:400], "thought": bool(out["thinking"]) and not out["content"].strip(),
            "sec": round(sec, 3), "load": round(out["load_s"], 2), "in": out["in"], "out": out["out"],
            "at": time.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------------------------------------------------------- 수치

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
    """모델 × 안 하나의 결과를 잰다. 분류기가 통과시킨 글 가운데 답을 받은 것만 쓴다."""
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
    secs = np.array([r["sec"] for _, r in pairs], dtype=float)
    out.update(sec_mean=float(secs.mean()), sec_median=float(np.median(secs)), sec_total=float(secs.sum()),
               tok_in=float(np.mean([r["in"] for _, r in pairs])), tok_out=float(np.mean([r["out"] for _, r in pairs])))
    return out


def assemble(env: Env, setup: Setup, prep: dict, llms: List[dict], got: Dict[str, list], errors: Dict[str, str],
             stopped: bool, state: dict) -> dict:
    """리포트가 읽는 결과를 만든다(JSON으로 적을 수 있는 모양)."""
    from screening import models as smodels

    cfg, data, chosen = env.cfg, prep["data"], prep["chosen"]
    spec = smodels.MODEL_BY_KEY.get(setup.classifier) or {}
    clf = mcore.load_classifier(cfg.labels, setup.classifier, data["unit"]) or {}
    passed = [it for it in chosen if it.passed]
    y = np.array([it.label for it in passed])
    s = np.array([it.score for it in passed], dtype=float)
    combos = []
    for m in llms:
        for plan in prep["plans"]:
            v = plan["variant"]
            cid = "%s|%s" % (m["name"], v.key)
            rows = got.get(cid) or []
            combos.append({"id": cid, "llm": m["name"], "variant": v.key, "name": v.name,
                           "done": sum(1 for r in rows if r is not None), "total": len(rows),
                           "error": errors.get(cid, ""), "metrics": measure(chosen, rows)})
    return {
        "made": time.strftime("%Y-%m-%d %H:%M:%S"), "stopped": stopped, "ollama": state.get("version", ""),
        "setup": {"classifier": setup.classifier, "view": setup.view, "thr_mode": setup.thr_mode, "sample": int(setup.sample or 0),
                  "with_rejected": bool(setup.with_rejected), "llms": [m["name"] for m in llms],
                  "variants": [p["variant"].key for p in prep["plans"]]},
        "classifier": {"key": setup.classifier, "label": spec.get("label", setup.classifier), "view": setup.view,
                       "view_name": mcore.VIEW_NAME[setup.view], "unit": data["unit"], "trained": clf.get("trained", ""),
                       "yes": clf.get("yes"), "no": clf.get("no"), "threshold": prep["threshold"], "thr_note": prep["thr_note"],
                       "title_weight": float(cfg.title_weight or 0.0), "target": float(cfg.target)},
        "data": dict(prep["counts"], part=data["part"], docs_used=data["use_names"],
                     base_curve=_curve(y, s) if len(y) and (y == 1).any() else []),
        "llms": [{"name": m["name"], "digest": m["digest"], "params": m["params"], "quant": m["quant"],
                  "size": m["size"], "license": m.get("license", ""), "thinking": m["thinking"]} for m in llms],
        "variants": [{"key": p["variant"].key, "name": p["variant"].name, "parts": p["variant"].parts, "long": p["variant"].long,
                      "max_tokens": p["variant"].max_tokens, "system": p["system"], "sample_user": (p["users"] or [""])[0],
                      "purpose": prompts.PURPOSE.get(p["variant"].key, "")} for p in prep["plans"]],
        "examples": [{"text": e["text"], "label": e["label"]} for e in prep["examples"]],
        "items": [{"doc": it.doc, "page": it.page, "text": it.text[:1500], "label": it.label, "score": round(it.score, 4),
                   "passed": it.passed} for it in chosen],
        "answers": {cid: [None if r is None else {"v": r["verdict"], "p": r["p"], "why": r.get("reason", ""), "sec": r["sec"],
                                                  "raw": r.get("content", "") if r["verdict"] is None else ""}
                          for r in rows] for cid, rows in got.items()},
        "combos": combos,
        "prompts_file": str(env.prompts_file), "sentences_file": str(cfg.sentences),
    }


def best_combo(result: dict) -> Optional[dict]:
    """끝까지 돈 조합 가운데, 분류기 문턱만 올린 것보다 가장 많이 줄인 조합."""
    done = [c for c in result["combos"] if c["metrics"] and c["done"] == c["total"] and c["metrics"]["gain"] is not None]
    return max(done, key=lambda c: (c["metrics"]["gain"], -c["metrics"]["sec_mean"])) if done else None
