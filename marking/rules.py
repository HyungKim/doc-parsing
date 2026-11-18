"""표시하지 않는 규칙 (5.1). 프로그램 폴더의 mark_rules.txt 에서 읽는다. 메모장으로 고칠 수 있다.

    skip_title_words   쪽 제목에 이 말이 들어 있으면 그 쪽에는 표시하지 않는다
    skip_line_words    이 단어가 들어 있는 문장(줄 하나, 표라면 행 하나)에는 표시하지 않는다

규칙은 분류기가 점수를 매긴 뒤, LLM에 묻기 전에 적용한다. 규칙에 걸린 것은 두 사본 어디에도 표시하지 않고 LLM에도 묻지 않는다.
무엇을 왜 뺐는지는 요약 화면에 남긴다. 평가(verify.bat)와 학습(label.bat)에는 쓰지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

DEFAULT_TEXT = """# 표시하기(mark.bat)에서 '표시하지 않을 것'을 정합니다. 메모장으로 고친 뒤 다시 만들면 반영됩니다.
# 쉼표로 여러 개를 적을 수 있습니다. 등호 뒤를 비워 두면 그 규칙은 쓰지 않습니다.
#
# skip_title_words : 쪽 제목에 이 말이 들어 있으면 그 쪽에는 표시하지 않습니다.
#     띄어쓰기는 무시하고 견줍니다 (기술분류체계 = 기술 분류 체계).
#     쪽 제목은 프로그램이 뽑은 것입니다. 요약 화면의 'N쪽 · 제목'에서 볼 수 있습니다.
#
# skip_line_words : 이 단어가 들어 있는 문장에는 표시하지 않습니다.
#     문장 = 글 덩어리의 줄 하나, 표라면 행 하나.
#     글자가 그대로 들어 있으면 걸립니다 (책임 → 책임연구원, 제조물 책임 모두).
#
# 규칙에 걸린 것은 LLM에도 묻지 않습니다. 무엇을 뺐는지는 요약 화면의 '표시하지 않은 것'에 나옵니다.

skip_title_words = 기술분류체계
skip_line_words = 책임, 선임, 사원
"""


@dataclass
class Rules:
    title_words: List[str] = field(default_factory=list)
    line_words: List[str] = field(default_factory=list)
    file: Optional[Path] = None

    @property
    def any(self) -> bool:
        return bool(self.title_words or self.line_words)

    def title_hit(self, title: str) -> str:
        """쪽 제목에 걸리는 말. 없으면 빈 글. 띄어쓰기는 무시한다."""
        squeezed = "".join((title or "").split())
        for w in self.title_words:
            if "".join(w.split()) in squeezed:
                return w
        return ""

    def line_hit(self, text: str) -> str:
        """문장에 걸리는 단어. 없으면 빈 글. 글자가 그대로 들어 있는지만 본다."""
        for w in self.line_words:
            if w in (text or ""):
                return w
        return ""


def _words(value: str) -> List[str]:
    out: List[str] = []
    for w in value.replace("，", ",").split(","):
        w = w.strip().strip("'\"‘’“”").strip()
        if w and w not in out:
            out.append(w)
    return out


def read_rules(path: Path) -> Rules:
    """규칙 파일을 읽는다. 파일이 없으면 기본값으로 새로 만든다."""
    path = Path(path)
    if not path.exists():
        path.write_text(DEFAULT_TEXT, encoding="utf-8")
    text = None
    for enc in ("utf-8-sig", "cp949"):             # 메모장이 다른 인코딩으로 저장했을 때 대비
        try:
            text = path.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("규칙 파일을 읽을 수 없습니다(인코딩): %s" % path)
    rules = Rules(file=path)
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, value = (x.strip() for x in line.split("=", 1))
        if key == "skip_title_words":
            rules.title_words = _words(value)
        elif key == "skip_line_words":
            rules.line_words = _words(value)
    for w in rules.title_words + rules.line_words:
        if len("".join(w.split())) < 2:            # 한 글자는 너무 많은 글에 걸린다
            raise ValueError("규칙 파일(%s): '%s' 은(는) 너무 짧습니다. 두 글자 이상으로 적어 주세요." % (path.name, w))
    return rules


def no_rules() -> Rules:
    return Rules()


__all__ = ["Rules", "read_rules", "no_rules", "DEFAULT_TEXT"]
