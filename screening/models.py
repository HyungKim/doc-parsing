"""비교할 모델 네 가지를 내려받고 실행한다. 한 번 계산한 결과는 파일에 남겨 다시 계산하지 않는다.

    임베딩 모델       글을 숫자 묶음(벡터)으로 바꾼다. bge-m3, KURE-v1, multilingual-e5-small
    문장 판별 모델    글과 문장을 함께 받아 그 문장이 글에 대해 맞는지를 따진다. bge-m3-zeroshot-v2.0-c

모두 MIT 라이선스이고 PC 안에서만 돈다. 모델 파일은 처음 한 번 Hugging Face에서 내려받아 models 폴더에 둔다.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .items import text_key

MODELS = [
    {"key": "bge-m3", "label": "bge-m3", "repo": "BAAI/bge-m3", "kind": "embed", "prefix": "", "temp": 0.05,
     "size": "약 2.3GB", "note": "다국어 임베딩. 가장 무난한 기준"},
    {"key": "kure-v1", "label": "KURE-v1", "repo": "nlpai-lab/KURE-v1", "kind": "embed", "prefix": "", "temp": 0.05,
     "size": "약 2.3GB", "note": "bge-m3를 한국어로 더 학습한 임베딩"},
    {"key": "me5-small", "label": "multilingual-e5-small", "repo": "intfloat/multilingual-e5-small", "kind": "embed",
     "prefix": "query: ", "temp": 0.02, "size": "약 0.5GB", "note": "작고 빠른 다국어 임베딩"},
    {"key": "bge-m3-zeroshot", "label": "bge-m3-zeroshot-v2.0-c", "repo": "MoritzLaurer/bge-m3-zeroshot-v2.0-c", "kind": "nli",
     "size": "약 1.1GB", "note": "문장 판별 모델. 정답 예시로 학습시키지 않고 기준 문장만으로 판단. 글 하나를 기준 문장 수만큼 돌린다(쌍)"},
]
MODEL_BY_KEY = {m["key"]: m for m in MODELS}

# 내려받지 않을 파일: 다른 실행 방식용 사본과 그림 등 (용량만 차지한다)
SKIP = ["onnx/*", "openvino/*", "imgs/*", "*.onnx", "*.onnx_data", "*.jpg", "*.png", "*.webp", "*.h5", "*.ot", "*.msgpack",
        ".eval_results/*", "training_args.bin", "trainer_state.json", "colbert_linear.pt", "sparse_linear.pt", ".gitattributes"]


class ModelMissing(Exception):
    """모델 파일이 없고 내려받지도 못했다."""


def model_dir(spec: dict, models_dir: Path) -> Path:
    return Path(models_dir) / spec["key"]


def is_ready(spec: dict, models_dir: Path) -> bool:
    d = model_dir(spec, models_dir)
    return (d / "config.json").exists() and any((d / n).exists() for n in ("model.safetensors", "pytorch_model.bin"))


def ensure_model(spec: dict, models_dir: Path, log: Callable[[str], None], download: bool = True) -> Path:
    """모델 폴더를 돌려준다. 없으면 내려받는다."""
    d = model_dir(spec, models_dir)
    if is_ready(spec, models_dir):
        return d
    if not download:
        raise ModelMissing("모델 파일이 없습니다: %s" % d)
    log("  모델을 내려받습니다: %s (%s) → %s" % (spec["repo"], spec["size"], d))
    try:
        from huggingface_hub import HfApi, snapshot_download
        files = HfApi().list_repo_files(spec["repo"])
        skip = list(SKIP)
        if "model.safetensors" in files:           # 같은 가중치가 두 형식으로 있으면 하나만 받는다
            skip.append("pytorch_model.bin")
        snapshot_download(spec["repo"], local_dir=str(d), ignore_patterns=skip)
    except Exception as exc:
        raise ModelMissing("모델을 내려받지 못했습니다(%s: %s). 인터넷이 막힌 PC라면 인터넷이 되는 PC에서 download_models.bat으로 받은 "
                           "models 폴더를 이 폴더에 복사하세요." % (type(exc).__name__, str(exc)[:200]))
    if not is_ready(spec, models_dir):
        raise ModelMissing("내려받은 모델 폴더가 온전하지 않습니다: %s" % d)
    return d


# ---------------------------------------------------------------- 계산 결과 보관

class Store:
    """글의 지문(key) → 숫자 배열. 모델과 설정이 같을 때만 다시 쓴다."""

    def __init__(self, path: Path, meta: dict):
        self.path, self.meta = Path(path), meta
        self.index: Dict[str, int] = {}
        self.rows: List[np.ndarray] = []
        self.dirty = False
        if self.path.exists():
            try:
                with np.load(str(self.path), allow_pickle=False) as z:
                    if json.loads(str(z["meta"])) == meta:
                        keys, data = [str(k) for k in z["keys"]], z["data"]
                        self.index = {k: i for i, k in enumerate(keys)}
                        self.rows = [data[i] for i in range(len(keys))]
            except Exception:
                self.index, self.rows = {}, []

    def has(self, key: str) -> bool:
        return key in self.index

    def get(self, key: str) -> np.ndarray:
        return self.rows[self.index[key]]

    def put(self, key: str, row: np.ndarray) -> None:
        if key not in self.index:
            self.index[key] = len(self.rows)
            self.rows.append(np.asarray(row, dtype=np.float32))
            self.dirty = True

    def save(self) -> None:
        if not self.dirty or not self.rows:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        keys = sorted(self.index, key=self.index.get)
        tmp = self.path.with_suffix(".tmp.npz")
        np.savez(str(tmp), meta=json.dumps(self.meta, ensure_ascii=False), keys=np.array(keys), data=np.stack(self.rows))
        tmp.replace(self.path)
        self.dirty = False


def _progress(log: Callable[[str], None], done: int, total: int, t0: float) -> None:
    dt = max(time.time() - t0, 1e-6)
    log("    %d / %d  (1초에 %.1f개)" % (done, total, done / dt))


# ---------------------------------------------------------------- 임베딩 모델

def embed(spec: dict, path: Path, texts: List[str], cache: Store, max_len: int, log: Callable[[str], None]) -> Tuple[np.ndarray, int, float]:
    """글마다 벡터를 구한다(길이 1로 맞춤). 반환: (벡터들, 새로 계산한 개수, 계산에 걸린 초)"""
    keys = [text_key(t) for t in texts]
    todo = {}
    for k, t in zip(keys, texts):
        if not cache.has(k):
            todo.setdefault(k, t)
    seconds = 0.0
    if todo:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(str(path), device="cpu")
        model.float()                              # 절반 정밀도로 저장된 모델은 CPU에서 몇 배 느리다. 항상 32비트로 돌린다
        model.max_seq_length = max_len
        order = sorted(todo, key=lambda k: len(todo[k]))          # 길이가 비슷한 글끼리 묶으면 빠르다
        t0 = time.time()
        for a in range(0, len(order), 32):
            part = order[a:a + 32]
            vecs = model.encode([spec["prefix"] + todo[k] for k in part], batch_size=8, normalize_embeddings=True,
                                show_progress_bar=False, convert_to_numpy=True)
            for k, v in zip(part, vecs):
                cache.put(k, v)
            if (a // 32) % 5 == 4 or a + 32 >= len(order):
                _progress(log, min(a + 32, len(order)), len(order), t0)
                cache.save()
        seconds = time.time() - t0
        del model
    return np.stack([cache.get(k) for k in keys]) if keys else np.zeros((0, 1), dtype=np.float32), len(todo), seconds


# ---------------------------------------------------------------- 문장 판별 모델

def nli(path: Path, texts: List[str], sentences: List[str], cache: Store, max_len: int,
        log: Callable[[str], None]) -> Tuple[np.ndarray, int, float]:
    """(글, 문장) 쌍마다 '그 문장이 글에 대해 맞다' 쪽 값과 '아니다' 쪽 값을 구한다.

    반환: (글 수 × 문장 수 × 2 배열, 새로 계산한 쌍의 수, 계산에 걸린 초)
    """
    def pair_key(t: str, s: str) -> str:
        return text_key(t) + ":" + text_key(s)

    todo = {}
    for t in texts:
        for s in sentences:
            k = pair_key(t, s)
            if not cache.has(k):
                todo.setdefault(k, (t, s))
    seconds = 0.0
    if todo:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        tok = AutoTokenizer.from_pretrained(str(path))
        model = AutoModelForSequenceClassification.from_pretrained(str(path))
        model = model.float()                      # 이 모델은 절반 정밀도(16비트)로 저장돼 있어 그대로 돌리면 CPU에서 6배쯤 느리다
        model.eval()
        names = {str(k).lower(): int(v) for k, v in model.config.label2id.items()}
        yes = next((v for k, v in names.items() if k.startswith("entail")), 0)
        no = next((v for k, v in names.items() if k.startswith("contra")),
                  next((v for k, v in names.items() if k.startswith("not")), 1 if yes == 0 else 0))
        order = sorted(todo, key=lambda k: len(todo[k][0]))
        t0 = time.time()
        for a in range(0, len(order), 8):
            part = order[a:a + 8]
            enc = tok([todo[k][0] for k in part], [todo[k][1] for k in part], truncation="only_first", max_length=max_len,
                      padding=True, return_tensors="pt")
            with torch.inference_mode():
                logits = model(**enc).logits.float().numpy()
            for k, row in zip(part, logits):
                cache.put(k, np.array([row[yes], row[no]], dtype=np.float32))
            if (a // 8) % 20 == 19 or a + 8 >= len(order):
                _progress(log, min(a + 8, len(order)), len(order), t0)
                cache.save()
        seconds = time.time() - t0
        del model
    out = np.zeros((len(texts), len(sentences), 2), dtype=np.float32)
    for i, t in enumerate(texts):
        for j, s in enumerate(sentences):
            out[i, j] = cache.get(pair_key(t, s))
    return out, len(todo), seconds


# ---------------------------------------------------------------- 학습 전(기준 문장만으로) 점수

def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)


def zero_shot_from_vectors(item_vecs: np.ndarray, sent_vecs: np.ndarray, positive: List[bool], temp: float) -> Tuple[np.ndarray, np.ndarray]:
    """임베딩 모델: 글이 기준 문장들 가운데 + 문장 쪽에 얼마나 가까운가(0~1), 그리고 가장 가까운 문장의 번호."""
    sims = item_vecs @ sent_vecs.T
    probs = _softmax(sims / max(temp, 1e-6))
    return probs[:, np.array(positive)].sum(axis=1), sims.argmax(axis=1)


def zero_shot_from_nli(pairs: np.ndarray, positive: List[bool]) -> Tuple[np.ndarray, np.ndarray]:
    """문장 판별 모델: 기준 문장들 가운데 어느 문장이 가장 맞는지를 따져, + 문장 쪽 비중(0~1)과 가장 맞는 문장의 번호."""
    yes = pairs[:, :, 0]
    probs = _softmax(yes)
    return probs[:, np.array(positive)].sum(axis=1), yes.argmax(axis=1)


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-60.0, min(60.0, x))))


def default_models_dir(root: Path) -> Path:
    return Path(root) / "models"


def pick_models(names: Optional[str]) -> List[dict]:
    if not names:
        return list(MODELS)
    wanted = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in wanted if n not in MODEL_BY_KEY]
    if unknown:
        raise ValueError("모르는 모델 이름: %s (쓸 수 있는 이름: %s)" % (", ".join(unknown), ", ".join(MODEL_BY_KEY)))
    return [MODEL_BY_KEY[n] for n in wanted]
