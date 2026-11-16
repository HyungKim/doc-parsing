"""LLM에 넣는 프롬프트. 조각(역할, 사업 분야, 판단 기준 …)을 이어 붙여 여러 안을 만들고, 답에서 예/아니오와 그 확률을 읽는다.

프롬프트는 verify_prompts.txt에 있고 메모장으로 고칠 수 있다(없으면 기본 내용으로 새로 만든다).
바뀌지 않는 부분(역할, 기준, 예시, 답하는 방법)은 앞쪽(시스템 글)에, 글마다 달라지는 부분(주변 글, 판단할 글)은 뒤쪽에 둔다.
앞쪽이 같으면 Ollama가 그 부분을 다시 읽지 않아서 빠르다.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

AUTO_PARTS = ("판단 기준", "예시", "주변 글")     # 프로그램이 채우는 조각
SHORT_ANSWER = "답하는 방법"                      # 이 조각을 쓰는 안은 한 단어 답으로 보고 짧게 끊는다
SHORT_TOKENS = 6
LONG_TOKENS = 160
TEXT_LIMIT = 1200                                 # 판단할 글은 이 글자 수까지만 넣는다(넘으면 자른다)
CONTEXT_LIMIT = 600                               # 주변 글 전체의 글자 수
EXAMPLE_LIMIT = 200                               # 예시 하나의 글자 수

DEFAULT_TEXT = """# LLM 검증(verify.bat)에 쓰는 프롬프트입니다. 메모장으로 고친 뒤 화면을 새로 고치면 반영됩니다.
#
# [이름] 으로 시작하는 줄부터 다음 [이름] 전까지가 '조각' 하나입니다.
# 맨 아래 [안] 에는 조각을 어떤 순서로 이어서 프롬프트 하나를 만들지 적습니다.
#     기호 이름 = 조각 + 조각 + ...
#
# 아래 세 조각은 프로그램이 채웁니다.
#     판단 기준   screen_sentences.txt 의 + 문장과 - 문장 (이 파일에 [판단 기준] 조각을 적으면 적은 것을 씁니다)
#     예시        학습용 문서의 정답에서 뽑은 글, 예 3개와 아니오 3개 (이 파일에 [예시] 조각을 적으면 적은 것을 씁니다)
#     주변 글     판단할 글이 있는 쪽의 제목과 같은 덩어리의 다른 글 (글마다 다릅니다)
#
# [답하는 방법] 조각을 쓰는 안은 '예' 또는 '아니오' 한 단어만 받고 끊습니다(빠릅니다).
# 다른 이름의 조각으로 답하는 방법을 적은 안은 길게 받고, 답 안의 '판단: 예' 또는 '판단: 아니오'를 읽습니다.
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

[답하는 방법: 이유 먼저]
첫 줄에 그렇게 판단한 이유를 한 문장으로 적으세요.
둘째 줄에 '판단: 예' 또는 '판단: 아니오'를 적으세요.

[안]
A 짧은 질문 = 역할 + 답하는 방법
B 기준 = 역할 + 판단 기준 + 답하는 방법
C 사업 분야 = 역할 + 사업 분야 + 판단 기준 + 답하는 방법
D 예시 = 역할 + 사업 분야 + 판단 기준 + 예시 + 답하는 방법
E 주변 글 = 역할 + 사업 분야 + 판단 기준 + 답하는 방법 + 주변 글
F 이유 먼저 = 역할 + 사업 분야 + 판단 기준 + 답하는 방법: 이유 먼저
"""

# 안마다 무엇을 알아보려는 것인지(기본 안에만 붙는 설명)
PURPOSE = {
    "A": "설명 없이 어디까지 되나 (바닥선)",
    "B": "판단 기준을 적어 주면 나아지나",
    "C": "회사의 기술 분야를 알려 주면 나아지나",
    "D": "실제 정답 예시가 도움이 되나",
    "E": "줄 하나만으로 판단하기 어려운 글을 돕나",
    "F": "이유를 먼저 쓰게 하면 정확해지나, 시간은 얼마나 더 드나",
}


@dataclass
class Variant:
    key: str                      # A, B, …
    name: str                     # 짧은 질문, 기준, …
    parts: List[str] = field(default_factory=list)

    @property
    def long(self) -> bool:
        """한 단어 답이 아니라 길게 받는 안인가"""
        return SHORT_ANSWER not in self.parts

    @property
    def max_tokens(self) -> int:
        return LONG_TOKENS if self.long else SHORT_TOKENS

    @property
    def uses_context(self) -> bool:
        return "주변 글" in self.parts

    @property
    def uses_examples(self) -> bool:
        return "예시" in self.parts

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


def parse(text: str) -> Tuple[Dict[str, str], List[Variant]]:
    """프롬프트 파일의 글 → (조각 이름 → 글, 안 목록)"""
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
    variants: List[Variant] = []
    for line in plan:
        m = re.match(r"^(\S+)\s*(.*?)\s*=\s*(.+)$", line)
        if not m:
            raise ValueError("프롬프트 파일의 [안]에서 읽을 수 없는 줄: %s  (모양: 기호 이름 = 조각 + 조각)" % line)
        key, name, right = m.group(1), m.group(2).strip(), m.group(3)
        names = [" ".join(p.split()) for p in right.split("+") if p.strip()]
        for n in names:
            if n not in texts and n not in AUTO_PARTS:
                raise ValueError("프롬프트 파일의 안 '%s'에 적힌 조각 [%s] 이(가) 없습니다" % (key, n))
        if any(v.key == key for v in variants):
            raise ValueError("프롬프트 파일의 [안]에 기호 '%s'이(가) 두 번 나옵니다" % key)
        variants.append(Variant(key=key, name=name or key, parts=names))
    if not variants:
        raise ValueError("프롬프트 파일에 [안]이 없습니다. 파일을 지우고 다시 실행하면 기본 내용으로 새로 만듭니다.")
    return texts, variants


def load(path: Path) -> Tuple[Dict[str, str], List[Variant]]:
    return parse(read_text(path))


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


def examples_text(examples: List[dict]) -> str:
    """examples: [{"text", "label"}]. 예시가 없으면 빈 글"""
    if not examples:
        return ""
    shown = ["글: %s\n답: %s" % (clip(" ".join(e["text"].split()), EXAMPLE_LIMIT), "예" if e["label"] == 1 else "아니오")
             for e in examples]
    return "예시:\n" + "\n\n".join(shown)


def context_text(title: str, around: List[str], word: str) -> str:
    """주변 글. around: 같은 덩어리의 다른 줄(줄을 판단할 때) 또는 앞뒤 덩어리(덩어리를 판단할 때). word: 그것을 부르는 말"""
    lines = ["[참고: 판단할 글의 주변. 참고만 하고, 아래 '판단할 글'에 대해서만 답하세요]"]
    if title.strip():
        lines.append("쪽 제목: " + clip(" ".join(title.split()), 120))
    left = CONTEXT_LIMIT
    shown = []
    for t in around:
        t = " ".join(t.split())
        if not t or left <= 20:
            continue
        t = clip(t, min(left, 200))
        shown.append("- " + t)
        left -= len(t)
    if shown:
        lines.append(word + ":")
        lines.extend(shown)
    return "\n".join(lines) if len(lines) > 1 else ""


def system_prompt(variant: Variant, parts: Dict[str, str], criteria: str, examples: str) -> str:
    """안 하나의 앞쪽 글(글마다 바뀌지 않는 부분)."""
    pieces = []
    for name in variant.parts:
        if name == "주변 글":
            continue
        if name in parts:
            text = parts[name]
        elif name == "판단 기준":
            text = criteria
        else:
            text = examples
        if text.strip():
            pieces.append(text.strip())
    return "\n\n".join(pieces)


def user_prompt(variant: Variant, text: str, context: str = "") -> str:
    """안 하나의 뒤쪽 글(글마다 달라지는 부분)."""
    body = "[판단할 글]\n" + clip(text, TEXT_LIMIT)
    return context + "\n\n" + body if variant.uses_context and context else body


# ---------------------------------------------------------------- 답 읽기

_STRIP = " \t\r\n'\"‘’“”`*[]()<>:：.,-·"
_VERDICT = re.compile(r"판단\s*[:：]?\s*['\"‘“\[(*\s]*(예|네|아니오|아니요|아닙니다|아니|yes|no)", re.IGNORECASE)


def _side(token: str) -> Optional[int]:
    """토큰이 '예' 쪽인지(1) '아니오' 쪽인지(0). 어느 쪽도 아니면 None. '아니오'는 모델에 따라 '아'부터 쪼개져 나온다."""
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


def read_answer(content: str, logprobs: list, long: bool) -> dict:
    """LLM의 답에서 판단과 확률을 읽는다.

    반환: {"verdict": 1(예) | 0(아니오) | None(읽지 못함), "p": '예'일 확률 0~1 또는 None(확률을 못 받음), "reason": 이유(길게 받는 안)}
    """
    tokens = [str(e.get("token", "")) for e in logprobs or []]
    verdict: Optional[int] = None
    reason = ""
    at: Optional[int] = None                       # 답이 놓인 토큰의 번호
    if long:
        m = None
        for m in _VERDICT.finditer(content):
            pass
        if m:
            verdict = _word(m.group(1))
            reason = content[:m.start()]
        joined = "".join(tokens)
        m2 = None
        for m2 in _VERDICT.finditer(joined):
            pass
        if m2:
            start, pos = m2.start(1), 0
            for i, t in enumerate(tokens):
                if pos <= start < pos + len(t):
                    at = i
                    break
                pos += len(t)
        if verdict is None:                        # '판단:' 없이 답한 경우: 마지막 줄을 본다
            lines = [l for l in content.strip().splitlines() if l.strip()]
            if lines:
                verdict = _word(lines[-1]) if _word(lines[-1]) is not None else _word(lines[0])
                reason = "\n".join(lines[:-1]) if len(lines) > 1 else ""
        reason = re.sub(r"^\s*(이유|근거)\s*[:：]\s*", "", " ".join(reason.split()))[:300]
    else:
        verdict = _word(content)
        for i, t in enumerate(tokens):
            if t.strip(_STRIP):
                at = i
                break
    p = _prob(logprobs[at]) if at is not None and at < len(logprobs or []) else None
    if verdict is None and p is not None:
        verdict = 1 if p >= 0.5 else 0
    return {"verdict": verdict, "p": p, "reason": reason}
