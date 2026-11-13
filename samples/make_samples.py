"""테스트용 샘플 PPTX 생성기.

실제 회사 자료에서 흔히 나오는 까다로운 경우를 일부러 넣는다.
  - 도형 저장 순서가 화면 순서와 다른 슬라이드
  - 제목 개체 틀 없이 텍스트 상자로 쓴 제목
  - 2단 구성, 비교 구성, 표, 그룹 도형, 자동 번호 목록
  - 매 슬라이드에 복사해 붙인 "Confidential" 문구, 쪽 번호, 대각선 워터마크
  - 슬라이드 마스터에 들어 있는 문구, 숨긴 슬라이드

사용법:  python samples/make_samples.py   →  samples/sample_deck.pptx
PDF는 PowerPoint에서 "PDF로 저장"해 samples/sample_deck.pdf 로 만든다.
"""
from __future__ import annotations

import copy
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

OUT = Path(__file__).parent / "sample_deck.pptx"


def textbox(slide, x, y, w, h, text, size=14, bold=False, color=None, rot=0):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        if color:
            r.font.color.rgb = RGBColor(*color)
    if rot:
        box.rotation = rot
    return box


def furniture(slide, page_no):
    """매 슬라이드에 '복사해 붙인' 반복 요소들."""
    textbox(slide, 0.3, 7.05, 4, 0.3, "Confidential – 대외비", size=9, color=(120, 120, 120))
    textbox(slide, 4.5, 7.05, 1, 0.3, f"- {page_no} -", size=9, color=(120, 120, 120))
    textbox(slide, 2.0, 3.0, 6, 1.2, "DRAFT", size=66, bold=True, color=(225, 225, 225), rot=-30)


def set_autonum(paragraph, kind="arabicPeriod"):
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("marL", "342900")
    pPr.set("indent", "-342900")
    bu = pPr.makeelement(qn("a:buAutoNum"), {"type": kind})
    pPr.append(bu)


def main():
    prs = Presentation()
    L_TITLE, L_CONTENT, L_TITLE_ONLY, L_BLANK = (prs.slide_layouts[i] for i in (0, 1, 5, 6))
    page = 0

    # 1. 표지
    s = prs.slides.add_slide(L_TITLE); page += 1
    s.shapes.title.text = "2026년 사업 추진 계획"
    s.placeholders[1].text = "전략기획팀 | 2026. 11."
    furniture(s, page)

    # 2. 제목 + 글머리 기호 본문 (자동 줄바꿈되는 긴 문단 포함)
    s = prs.slides.add_slide(L_CONTENT); page += 1
    s.shapes.title.text = "1. 추진 배경"
    tf = s.placeholders[1].text_frame
    tf.text = "국내 시장 성장률이 3년 연속 둔화되면서 기존 주력 제품의 매출 기여도가 빠르게 낮아지고 있어 신규 성장 동력 확보가 시급한 상황임"
    for text, level in [
        ("주력 제품 매출 비중: 2023년 72% → 2025년 58%", 1),
        ("경쟁사는 해외 매출 비중을 40% 이상으로 확대", 1),
        ("고객 요구가 단품 구매에서 구독형 서비스로 이동하고 있으며, 이에 대응하기 위한 조직과 시스템 정비가 필요함", 0),
        ("Confidential 정보 관리 체계도 함께 정비", 0),
    ]:
        p = tf.add_paragraph(); p.text = text; p.level = level
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = Pt(20 if p.level == 0 else 16)
    furniture(s, page)

    # 3. 텍스트 상자 제목 + 2단 (저장 순서: 오른쪽 단 → 왼쪽 단 → 제목)
    s = prs.slides.add_slide(L_BLANK); page += 1
    textbox(s, 5.2, 1.6, 4.3, 4.5, [
        "해외 사업",
        "동남아 3개국 법인 설립을 2026년 상반기까지 완료하고 현지 유통 파트너와 계약을 체결함",
        "하반기에는 유럽 시장 진출 타당성 조사를 진행함",
    ], size=16)
    textbox(s, 0.5, 1.6, 4.3, 4.5, [
        "국내 사업",
        "구독형 서비스를 2026년 1분기에 출시하고 연말까지 가입자 5만 명을 확보함",
        "기존 대리점 채널은 서비스 거점으로 전환함",
    ], size=16)
    textbox(s, 0.5, 0.4, 9, 0.9, "2. 사업별 추진 방향", size=30, bold=True)
    furniture(s, page)

    # 4. 비교 구성: 소제목 + 본문이 좌우로 나란히
    s = prs.slides.add_slide(L_TITLE_ONLY); page += 1
    s.shapes.title.text = "3. 운영 체계 개편"
    textbox(s, 5.2, 2.5, 4.3, 3, ["사업부별 책임 경영 체계로 전환", "의사결정 단계를 5단계에서 3단계로 축소"], size=16)
    textbox(s, 5.2, 1.8, 4.3, 0.5, "To-Be", size=20, bold=True)
    textbox(s, 0.5, 1.8, 4.3, 0.5, "As-Is", size=20, bold=True)
    textbox(s, 0.5, 2.5, 4.3, 3, ["기능 중심 조직으로 부서 간 협업이 느림", "의사결정에 평균 3주 소요"], size=16)
    furniture(s, page)

    # 5. 표
    s = prs.slides.add_slide(L_TITLE_ONLY); page += 1
    s.shapes.title.text = "4. 투자 계획"
    rows = [
        ["구분", "2026년", "2027년", "비고"],
        ["설비 투자", "120억 원", "150억 원", "신규 라인 1개 증설"],
        ["연구 개발", "80억 원", "95억 원", "구독 플랫폼 개발 포함"],
        ["해외 법인", "45억 원", "60억 원", "동남아 3개국"],
    ]
    gf = s.shapes.add_table(len(rows), 4, Inches(0.5), Inches(1.8), Inches(9), Inches(2.4))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = gf.table.cell(r, c)
            cell.text = val
            cell.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
    textbox(s, 0.5, 4.5, 9, 0.5, "※ 금액은 부가세 제외 기준이며 분기별 집행 계획은 별도 보고 예정", size=12)
    furniture(s, page)

    # 6. 그룹 도형으로 만든 절차도 (역순으로 추가)
    s = prs.slides.add_slide(L_TITLE_ONLY); page += 1
    s.shapes.title.text = "5. 추진 절차"
    steps = ["① 현황 진단", "② 과제 도출", "③ 실행 계획 수립", "④ 성과 점검"]
    shapes = []
    for i in reversed(range(4)):
        sh = s.shapes.add_shape(1, Inches(0.5 + i * 2.3), Inches(2.5), Inches(2.0), Inches(1.0))
        sh.text_frame.text = steps[i]
        sh.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
        shapes.append(sh)
    s.shapes.add_group_shape(shapes)
    textbox(s, 0.5, 4.2, 9, 1, "각 단계는 4주 단위로 진행하며 단계 종료 시 경영진 보고를 실시함", size=16)
    furniture(s, page)

    # 7. 자동 번호 목록 + 직접 입력한 번호
    s = prs.slides.add_slide(L_TITLE_ONLY); page += 1
    s.shapes.title.text = "6. 세부 일정"
    box = textbox(s, 0.5, 1.8, 9, 2, ["조직 개편안 확정", "구독 플랫폼 개발 착수", "해외 법인 설립 신청"], size=16)
    for p in box.text_frame.paragraphs:
        set_autonum(p)
    textbox(s, 0.5, 4.0, 9, 1.5, ["1) 분기별 점검 회의 운영", "2) 연말 종합 평가"], size=16)
    furniture(s, page)

    # 8. 같은 제목이 이어지는 슬라이드
    s = prs.slides.add_slide(L_TITLE_ONLY); page += 1
    s.shapes.title.text = "6. 세부 일정"
    textbox(s, 0.5, 1.8, 9, 2, ["- 3분기: 구독 서비스 2차 기능 출시", "- 4분기: 유럽 시장 조사 결과 보고"], size=16)
    furniture(s, page)

    # 9. 숨긴 슬라이드
    s = prs.slides.add_slide(L_TITLE_ONLY)
    s.shapes.title.text = "참고: 내부 검토용 메모"
    textbox(s, 0.5, 1.8, 9, 2, "이 슬라이드는 숨김 처리되어 발표와 PDF에 나오지 않음", size=16)
    s._element.set("show", "0")

    # 10. 맺음
    s = prs.slides.add_slide(L_BLANK); page += 1
    textbox(s, 1.5, 3.0, 7, 1.2, "감사합니다", size=44, bold=True)
    furniture(s, page)

    # 슬라이드 마스터에 문구 넣기 (슬라이드 도형 목록에는 안 나오지만 PDF에는 찍힘)
    donor = textbox(prs.slides[0], 6.5, 0.1, 3.3, 0.3, "ABC Corp. Internal Use Only", size=9, color=(120, 120, 120))
    el = copy.deepcopy(donor._element)
    donor._element.getparent().remove(donor._element)
    prs.slide_master.shapes._spTree.append(el)

    prs.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
