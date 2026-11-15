"""시험용 문서 목록(screen_test_docs.txt)과, 시험 문서로 잰 결과의 기록(out/screen/test_history.json).

시험용 문서는 정답을 붙여 두되 학습에는 쓰지 않고 채점에만 쓰는 문서다.
학습용 정답을 늘리거나 기준 문장·설정을 바꿀 때마다 같은 시험 문서로 재므로, 전과 후를 그대로 비교할 수 있다.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import List, Optional

KEEP_SNAPSHOTS = 40        # 기록은 이만큼까지만 남긴다
KEEP_SCORES = 8            # 글마다의 점수는 최근 이만큼의 기록에만 남긴다(나머지는 수치만)

DEFAULT_TEXT = """# 시험용 문서 목록입니다. 한 줄에 문서 이름 하나 (예: 보고서.pdf)
# 여기에 적힌 문서의 정답은 학습에 쓰지 않고 채점에만 씁니다.
# label.bat 화면의 '시험용 문서'에서 체크해도 이 파일에 적힙니다.
# 문서 이름은 out 폴더에 추출된 이름 그대로 적습니다. # 로 시작하는 줄과 빈 줄은 무시합니다.

"""


def read_test_docs(path: Path) -> List[str]:
    """시험용 문서 이름들. 파일이 없으면 설명만 적힌 빈 목록으로 새로 만든다."""
    path = Path(path)
    if not path.exists():
        path.write_text(DEFAULT_TEXT, encoding="utf-8")
    raw = None
    for enc in ("utf-8-sig", "cp949"):             # 메모장이 다른 인코딩으로 저장했을 때 대비
        try:
            raw = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if raw is None:
        raise ValueError("시험용 문서 목록을 읽을 수 없습니다(인코딩): %s" % path)
    names: List[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and line not in names:
            names.append(line)
    return names


def write_test_docs(path: Path, names: List[str]) -> None:
    seen: List[str] = []
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.append(n)
    Path(path).write_text(DEFAULT_TEXT + "".join(n + "\n" for n in seen), encoding="utf-8")


# ---------------------------------------------------------------- 기록

def signature(parts) -> str:
    """학습 상태의 지문. 이것이 같으면 같은 분류기라서 기록을 새로 쌓지 않고 마지막 것을 고쳐 쓴다."""
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def load_history(path: Path) -> List[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else []
    except Exception:
        return []
    return data if isinstance(data, list) else []


def save_history(path: Path, history: List[dict]) -> None:
    history = history[-KEEP_SNAPSHOTS:]
    for snap in history[:-KEEP_SCORES]:
        snap.pop("scores", None)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def add_snapshot(history: List[dict], snap: dict) -> List[dict]:
    """학습 상태가 마지막 기록과 같으면 그것을 고쳐 쓰고(처음 남긴 시각은 유지), 다르면 뒤에 붙인다."""
    if history and history[-1].get("sig") == snap["sig"]:
        snap["made"] = history[-1].get("made", snap["made"])
        history[-1] = snap
    else:
        history.append(snap)
    return history


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def previous_of(history: List[dict]) -> Optional[dict]:
    """지금 것(마지막) 바로 앞의 기록. 글마다의 점수가 남아 있는 것만."""
    return history[-2] if len(history) >= 2 and history[-2].get("scores") else None
