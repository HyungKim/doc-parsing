"""LLM에 넣는 프롬프트. 조각(역할, 사업 분야, 판단 기준, 답하는 방법)을 이어 붙여 프롬프트를 만들고, 답에서 예/아니오와 그 확률을 읽는다.

5.0부터 프롬프트는 안 C(사업 분야) 하나만 쓴다. 4.x에 있던 다른 안(A 짧은 질문, B 기준, D 예시, E 주변 글, F 이유 먼저)과
그 안들만 쓰던 기능(정답에서 예시 뽑기, 주변 글 넣기, 이유를 길게 받기)은 없앴다.

프롬프트는 verify_prompts.txt에 있고 메모장으로 고칠 수 있다(없으면 기본 내용으로 새로 만든다).
4.x에서 쓰던 파일도 그대로 읽는다: [안]의 C 줄과 그 줄에 적힌 조각만 쓰고, 다른 안의 줄은 읽지 않는다.
바뀌지 않는 부분(역할, 사업 분야, 기준, 답하는 방법)은 앞쪽(시스템 글)에, 글마다 달라지는 부분(판단할 글)은 뒤쪽에 둔다.
앞쪽이 같으면 Ollama가 그 부분을 다시 읽지 않아서 빠르다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CRITERIA_PART = "판단 기준"                        # 프로그램이 채우는 조각(screen_sentences.txt의 + 문장과 - 문장)
ANSWER_PART = "답하는 방법"                        # '예' 또는 '아니오' 한 단어로 답하게 하는 조각. 안에 꼭 있어야 한다
GONE_PARTS = ("예시", "주변 글")                   # 4.x에서 프로그램이 채우던 조각. 5.0부터는 채우지 않는다
MAX_TOKENS = 6                                    # 답은 한 단어만 받고 끊는다
TEXT_LIMIT = 1200                                 # 판단할 글은 이 글자 수까지만 넣는다(넘으면 자른다)

DEFAULT_TEXT = """# LLM에 넣는 프롬프트입니다(verify.bat, mark.bat). 메모장으로 고친 뒤 화면을 새로 고치면 반영됩니다.
#
# [이름] 으로 시작하는 줄부터 다음 [이름] 전까지가 '조각' 하나입니다.
# 맨 아래 [안] 에는 조각을 어떤 순서로 이어서 프롬프트를 만들지 적습니다.
#     기호 이름 = 조각 + 조각 + ...
#
# 5.0부터 프로그램은 [안] 의 C 줄 하나만 씁니다. 다른 기호의 줄이 있어도 읽지 않습니다.
#
# [판단 기준] 조각은 프로그램이 채웁니다: screen_sentences.txt 의 + 문장과 - 문장
# (이 파일에 [판단 기준] 조각을 적으면 적은 것을 씁니다)
#
# [답하는 방법] 조각은 꼭 있어야 합니다. 답은 '예' 또는 '아니오' 한 단어만 받고 끊습니다.
#
# 회사 이름이나 세부 기술을 더 적어도 됩니다. 이 파일은 이 PC에만 있고 깃허브에 올라가지 않습니다.
# # 로 시작하는 줄과 빈 줄은 무시합니다.

[역할]
당신은 전자부품 회사의 특허 담당자를 돕는 검토 보조입니다.
사내 기술 자료에서 뽑은 글 하나를 보고, 그 글이 '특허출원 검토가 필요한 내용'인지 판단합니다.

[사업 분야]
이 회사가 다루는 기술 분야:
- 광학: 스마트폰·차량용 카메라 모듈, 자동 초점·손떨림 보정 액추에이터, 3D 센싱 모듈, 렌즈
- 기판: 반도체 패키지 기판(FC-BGA, RF-SiP 등), 테이프 기판, 포토마스크
- 전장: 차량용 통신 모듈(5G·V2X), 레이더·라이다, 차량 조명, 모터·센서, 전력 변환 부품(DC-DC 컨버터, 배터리 관리, 충전)
- 공통: 소재, 공정·검사·설비 기술, 영상 처리·제어 같은 소프트웨어와 알고리즘
이 분야의 구조, 소재, 공정, 회로, 알고리즘에 관한 구체적인 내용은 짧은 글이어도 기술 내용으로 봅니다.

[답하는 방법]
'예' 또는 '아니오' 한 단어로만 답하세요.

[안]
C 사업 분야 = 역할 + 사업 분야 + 판단 기준 + 답하는 방법
"""


@dataclass
class Variant:
    key: str                      # C
    name: str                     # 사업 분야
    parts: List[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return "%s %s" % (self.key, self.name)


def read_text(path: Path) -> str:
    """프롬프트 파일의 글. 파일이 없으면 기본 내용으로 새로 만든다."""
    path = Path(path)
    if not path.exists():
        path.write_text(DEFAULT_TEXT, encoding="utf-8")
    for enc in ("utf-8-sig", "cp949"):             # 메모장이 다른 인코딩으로 저장했을 때 대비
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("프롬프트 파일을 읽을 수 없습니다(인코딩): %s" % path)


def parse(text: str, key: str) -> Tuple[Dict[str, str], Variant]:
    """프롬프트 파일의 글 → (조각 이름 → 글, 기호가 key인 안). [안]의 다른 줄은 읽지 않는다(4.x의 파일에 남아 있어도 된다)."""
    parts: Dict[str, List[str]] = {}
    plan: List[str] = []
    current: Optional[str] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*\[(.+?)\]\s*$", line)
        if m:
            current = " ".join(m.group(1).split())
            if current != "안":
                parts.setdefault(current, [])
            continue
        if current is None:
            continue
        if current == "안":
            if line.strip():
                plan.append(line.strip())
        else:
            parts[current].append(line)
    texts = {name: "\n".join(lines).strip() for name, lines in parts.items()}
    how = "파일의 [안]에 '%s 이름 = 조각 + 조각' 줄을 적거나, 파일을 지우고 다시 실행하면 기본 내용으로 새로 만듭니다." % key
    if not plan:
        raise ValueError("프롬프트 파일에 [안]이 없습니다. " + how)
    found: Optional[Variant] = None
    for line in plan:
        m = re.match(r"^(\S+)\s*(.*?)\s*=\s*(.+)$", line)
        if not m or m.group(1) != key:
            continue
        if found is not None:
            raise ValueError("프롬프트 파일의 [안]에 기호 '%s'이(가) 두 번 나옵니다" % key)
        names = [" ".join(p.split()) for p in m.group(3).split("+") if p.strip()]
        found = Variant(key=key, name=m.group(2).strip() or key, parts=names)
    if found is None:
        raise ValueError("프롬프트 파일의 [안]에 '%s' 줄이 없습니다. %s" % (key, how))
    for n in found.parts:
        if n in texts or n == CRITERIA_PART:
            continue
        if n in GONE_PARTS:
            raise ValueError("프롬프트 파일의 안 '%s'에 [%s] 조각이 적혀 있습니다. 5.0부터 프로그램이 이 조각을 채우지 않으니 "
                             "그 줄에서 '%s'을(를) 지우거나, 같은 이름의 조각을 파일에 직접 적어 주세요." % (key, n, n))
        raise ValueError("프롬프트 파일의 안 '%s'에 적힌 조각 [%s] 이(가) 없습니다" % (key, n))
    if ANSWER_PART not in found.parts:
        raise ValueError("프롬프트 파일의 안 '%s'에 [%s] 조각이 들어 있어야 합니다(답을 '예' 또는 '아니오' 한 단어로 받습니다)." % (key, ANSWER_PART))
    return texts, found


def load(path: Path, key: str) -> Tuple[Dict[str, str], Variant]:
    return parse(read_text(path), key)


# ---------------------------------------------------------------- 프로그램이 채우는 조각

def criteria_text(sentences: list) -> str:
    """기준 문장(screen_sentences.txt)을 프롬프트의 판단 기준으로 바꾼다."""
    yes = [s.text for s in sentences if s.positive]
    no = [s.text for s in sentences if not s.positive]
    lines = ["'예'로 판단하는 글:"] + ["- " + t for t in yes] + ["'아니오'로 판단하는 글:"] + ["- " + t for t in no]
    return "\n".join(lines)


def clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def system_prompt(variant: Variant, parts: Dict[str, str], criteria: str) -> str:
    """앞쪽 글(글마다 바뀌지 않는 부분)."""
    pieces = []
    for name in variant.parts:
        text = parts[name] if name in parts else criteria
        if text.strip():
            pieces.append(text.strip())
    return "\n\n".join(pieces)


def user_prompt(text: str) -> str:
    """뒤쪽 글(글마다 달라지는 부분)."""
    return "[판단할 글]\n" + clip(text, TEXT_LIMIT)


# ---------------------------------------------------------------- 답 읽기

_STRIP = " \t\r\n'\"‘’“”`*[]()<>:：.,-·"


def _side(token: str) -> Optional[int]:
    """토큰 하나가 '예' 쪽(1)인지 '아니오' 쪽(0)인지. 어느 쪽도 아니면 None"""
    t = token.strip(_STRIP).lower()
    if not t:
        return None
    if t.startswith("예") or t.startswith("네") or t in ("yes", "y"):
        return 1
    if t.startswith("아니") or t in ("아", "안", "no", "n"):
        return 0
    return None


def _word(text: str) -> Optional[int]:
    t = text.strip(_STRIP).lower()
    if t.startswith("예") or t.startswith("네") or t.startswith("yes"):
        return 1
    if t.startswith("아니") or t.startswith("아닙") or t.startswith("no"):
        return 0
    return None


def _prob(entry: dict) -> Optional[float]:
    """답 자리의 후보들에서 '예'일 확률: 예 쪽 확률의 합 ÷ (예 쪽 + 아니오 쪽)."""
    yes = no = 0.0
    for c in entry.get("top_logprobs") or []:
        side = _side(str(c.get("token", "")))
        try:
            p = math.exp(float(c.get("logprob")))
        except (TypeError, ValueError, OverflowError):
            continue
        if side == 1:
            yes += p
        elif side == 0:
            no += p
    return yes / (yes + no) if yes + no > 1e-9 else None


def read_answer(content: str, logprobs: list) -> dict:
    """LLM의 답에서 판단과 확률을 읽는다.

    반환: {"verdict": 1(예) | 0(아니오) | None(읽지 못함), "p": '예'일 확률 0~1 또는 None(확률을 못 받음)}
    판단은 답의 글자에서 읽는다. 글자로 읽지 못했을 때만 확률(0.5 이상이면 '예')로 대신한다.
    """
    verdict = _word(content)
    at: Optional[int] = None                       # 답이 놓인 토큰의 번호
    for i, e in enumerate(logprobs or []):
        if str(e.get("token", "")).strip(_STRIP):
            at = i
            break
    p = _prob(logprobs[at]) if at is not None else None
    if verdict is None and p is not None:
        verdict = 1 if p >= 0.5 else 0
    return {"verdict": verdict, "p": p}
