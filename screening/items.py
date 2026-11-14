"""1단계(추출)가 만든 단위 파일(이름.units.json)을 읽어 2단계(걸러내기)가 다룰 항목으로 만든다.

항목은 두 가지 크기로 다룬다.
    덩어리  리포트에서 번호 하나로 보이는 글상자·문단 묶음·표
    줄      덩어리 안의 한 줄(문단 하나, 표라면 한 행)
덩어리는 자기 줄들을 품고 있어서, 같은 글을 덩어리로 넣었을 때와 줄로 넣었을 때의 결과를 나란히 비교할 수 있다.
쪽 제목은 따로 걸러낼 대상으로 삼지 않고 덩어리의 문맥(title)으로만 둔다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


def text_key(text: str) -> str:
    """글의 지문. 띄어쓰기와 줄바꿈 차이는 무시한다. 정답과 계산 결과를 이 값으로 찾는다.

    같은 글이면 어느 문서의 어느 자리에 있든 같은 값이라, 추출을 다시 해서 번호가 바뀌어도 정답이 유지된다.
    """
    return hashlib.sha1(" ".join(text.split()).encode("utf-8")).hexdigest()[:20]


@dataclass
class LineItem:
    uid: str                 # 문서 이름 # p4-b3-l2
    id: str                  # p4-b3-l2
    number: int              # 덩어리 안에서 몇 번째 줄인가
    text: str
    key: str = ""

    def __post_init__(self) -> None:
        self.key = self.key or text_key(self.text)


@dataclass
class BlockItem:
    uid: str                 # 문서 이름 # p4-b3
    id: str                  # p4-b3
    page: int
    number: int              # 그 쪽에서 몇 번째 덩어리인가
    kind: str                # text | table
    title: str               # 그 쪽의 제목 (문맥)
    text: str
    table_form: str = ""     # 표일 때: flat(풀어 쓴 모양) | pipe(칸 구분)
    over_table: bool = False
    lines: List[LineItem] = field(default_factory=list)
    key: str = ""

    def __post_init__(self) -> None:
        self.key = self.key or text_key(self.text)


@dataclass
class DocItems:
    name: str                # 보고.pdf
    kind: str                # pdf | pptx
    units_file: str          # 보고.pdf.units.json
    report_file: str         # 보고.pdf.html (1단계 리포트)
    blocks: List[BlockItem] = field(default_factory=list)

    @property
    def lines(self) -> List[LineItem]:
        return [l for b in self.blocks for l in b.lines]


def load_docs(out_dir: Path) -> List[DocItems]:
    """out 폴더의 단위 파일을 모두 읽는다."""
    docs: List[DocItems] = []
    for path in sorted(Path(out_dir).glob("*.units.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        units = data.get("units") or {}
        name = data.get("file") or path.name[:-len(".units.json")]
        doc = DocItems(name=name, kind=data.get("kind", ""), units_file=path.name,
                       report_file=path.name[:-len(".units.json")] + ".html")
        blocks: Dict[tuple, BlockItem] = {}
        for u in units.get("block", []):
            if u.get("kind") == "title" or not (u.get("text") or "").strip():
                continue
            b = BlockItem(uid="%s#%s" % (name, u["id"]), id=u["id"], page=int(u.get("page", 0)), number=int(u.get("block", 0)),
                          kind=u.get("kind", "text"), title=u.get("title", ""), text=u["text"],
                          table_form=u.get("table_form", ""), over_table=bool(u.get("over_table")))
            blocks[(b.page, b.number)] = b
            doc.blocks.append(b)
        for u in units.get("line", []):
            if u.get("kind") == "title" or not (u.get("text") or "").strip():
                continue
            b = blocks.get((int(u.get("page", 0)), int(u.get("block", 0))))
            if b is None:
                continue
            b.lines.append(LineItem(uid="%s#%s" % (name, u["id"]), id=u["id"], number=int(u.get("line", 0)), text=u["text"]))
        for b in doc.blocks:
            if not b.lines:                        # 줄 목록이 없는 덩어리는 덩어리 글을 줄로 나눠 채운다
                for k, t in enumerate([t for t in b.text.split("\n") if t.strip()], 1):
                    b.lines.append(LineItem(uid="%s-l%d" % (b.uid, k), id="%s-l%d" % (b.id, k), number=k, text=t))
        if doc.blocks:
            docs.append(doc)
    return docs
