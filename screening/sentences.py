"""정답 예시 없이 판단할 때(학습 전) 쓰는 기준 문장.

기준 문장은 screen_sentences.txt에 한 줄에 하나씩 적는다. 메모장으로 고칠 수 있다.
    + 로 시작하는 줄   특허출원 검토가 필요한 글을 나타내는 문장
    - 로 시작하는 줄   검토가 필요 없는 글을 나타내는 문장
    # 로 시작하는 줄과 빈 줄은 무시한다

글마다 "기준 문장들 가운데 어느 문장에 가장 가까운가"를 따져, + 문장 쪽으로 기운 정도를 0~1 점수로 낸다.
임베딩 모델은 글과 문장의 비슷한 정도로, 문장 판별 모델은 그 문장이 글에 대해 맞을 가능성으로 따진다.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

DEFAULT_TEXT = """# 1차 걸러내기의 기준 문장입니다. 정답 예시 없이 판단할 때(학습 전) 이 문장들을 씁니다.
# 메모장으로 고친 뒤 screen.bat을 다시 실행하면 반영됩니다.
#
#   + 로 시작하는 줄 : 특허출원 검토가 필요한 글을 나타내는 문장
#   - 로 시작하는 줄 : 검토가 필요 없는 글을 나타내는 문장
#   # 로 시작하는 줄과 빈 줄은 무시합니다.
#
# 문장은 "이 글은 ...한다." 꼴의 완전한 문장으로 적는 것이 좋습니다.
# + 문장과 - 문장이 각각 하나 이상 있어야 합니다.

+ 이 글은 새로운 기술적 구조, 장치, 방법 또는 알고리즘을 제안하거나 설명한다.
+ 이 글은 기존 기술의 문제를 해결하는 기술적 수단과 그 효과를 설명한다.
+ 이 글은 제품이나 공정의 성능을 높이는 새로운 설계나 기술 아이디어를 설명한다.

- 이 글은 일정, 조직, 인력, 비용, 매출 같은 일반적인 업무 현황을 설명한다.
- 이 글은 시장 동향이나 경쟁사 현황 같은 사업 환경을 설명한다.
- 이 글은 목차, 출처, 인사말처럼 구체적인 기술 내용이 없다.
"""


@dataclass
class Sentence:
    positive: bool           # + 문장인가
    text: str
    number: int = 0          # 같은 기호 안에서 몇 번째인가 (리포트에서 +1, -2 처럼 부른다)

    @property
    def name(self) -> str:
        return "%s%d" % ("+" if self.positive else "-", self.number)


def read_text(path: Path) -> str:
    """기준 문장 파일의 글을 그대로 읽는다. 파일이 없으면 기본 문장으로 새로 만든다."""
    path = Path(path)
    if not path.exists():
        path.write_text(DEFAULT_TEXT, encoding="utf-8")
    for enc in ("utf-8-sig", "cp949"):             # 메모장이 다른 인코딩으로 저장했을 때 대비
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("기준 문장 파일을 읽을 수 없습니다(인코딩): %s" % path)


def parse_sentences(raw: str) -> List[Sentence]:
    """기준 문장 글을 문장 목록으로 바꾼다. + 문장과 - 문장이 각각 하나 이상 있어야 한다."""
    out: List[Sentence] = []
    count = {True: 0, False: 0}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line[0] in "+＋":
            positive = True
        elif line[0] in "-－–—":
            positive = False
        else:
            continue                               # 기호가 없는 줄은 문장으로 보지 않는다
        text = line[1:].strip()
        if not text:
            continue
        count[positive] += 1
        out.append(Sentence(positive, text, count[positive]))
    if not count[True] or not count[False]:
        raise ValueError("+ 문장과 - 문장이 각각 하나 이상 있어야 합니다 (지금 + %d개, - %d개)" % (count[True], count[False]))
    return out


def load_sentences(path: Path) -> List[Sentence]:
    """기준 문장 파일을 읽는다. 파일이 없으면 기본 문장으로 새로 만든다."""
    try:
        return parse_sentences(read_text(path))
    except ValueError as exc:
        raise ValueError("기준 문장 파일(%s): %s" % (path, exc))
