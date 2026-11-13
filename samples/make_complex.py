"""복잡한 테스트용 샘플 PPTX 생성기.

  complex_consulting.pptx : 16:9, 컨설팅 보고서형. 3단 카드, 2x2 매트릭스, 로드맵, 조직도,
                            병합 셀 표, 차트, 중첩 그룹, KPI 카드, 제목 없는 쪽, 좌우 표 등
  messy_report.pptx       : 4:3, 개체 틀을 전혀 쓰지 않고 텍스트 상자로만 만든 자료.
                            제목보다 큰 숫자, 왼쪽 세로 띠 제목, 겹친 상자, 계단식 배치,
                            상자로 만든 표, 영문 문단, 다양한 자동 번호 등

사용법:  python samples/make_complex.py
"""
from __future__ import annotations

import copy
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).parent
GRAY = (110, 110, 110)
NAVY = (20, 50, 110)


def tb(slide, x, y, w, h, text, size=12, bold=False, color=None, rot=0, align=None, fill=None, shape=False):
    if shape:
        box = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    else:
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(*fill)
    tf = box.text_frame
    tf.word_wrap = True
    lines = text if isinstance(text, list) else [text]
    for i, line in enumerate(lines):
        level = 0
        if isinstance(line, tuple):
            line, level = line
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = level
        if align:
            p.alignment = align
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size - 1.5 * level)
        r.font.bold = bold
        r.font.color.rgb = RGBColor(*(color or (30, 30, 30)))
    if rot:
        box.rotation = rot
    return box


def table(slide, x, y, w, h, rows, size=11, merges=()):
    gf = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(h))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = gf.table.cell(r, c)
            cell.text = val
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(size)
    for (r1, c1, r2, c2) in merges:
        gf.table.cell(r1, c1).merge(gf.table.cell(r2, c2))
    return gf


def autonum(paragraph, kind="arabicPeriod", start=None):
    pPr = paragraph._p.get_or_add_pPr()
    pPr.set("marL", "342900")
    pPr.set("indent", "-342900")
    attrs = {"type": kind}
    if start:
        attrs["startAt"] = str(start)
    pPr.append(pPr.makeelement(qn("a:buAutoNum"), attrs))


def to_master(prs, donor):
    el = copy.deepcopy(donor._element)
    donor._element.getparent().remove(donor._element)
    prs.slide_master.shapes._spTree.append(el)


# ====================================================================== 컨설팅 보고서형

def consulting():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    BLANK, TITLE_ONLY, CONTENT = prs.slide_layouts[6], prs.slide_layouts[5], prs.slide_layouts[1]
    state = {"n": 0}

    def new(layout=BLANK, crumb=None, title=None):
        s = prs.slides.add_slide(layout)
        state["n"] += 1
        if title is not None and layout is not BLANK:
            t = s.shapes.title
            t.left, t.top, t.width, t.height = Inches(0.5), Inches(0.55), Inches(12.3), Inches(0.8)
            t.text = title
            for p in t.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT
                for r in p.runs:
                    r.font.size = Pt(26)
                    r.font.bold = True
        if crumb:
            tb(s, 0.5, 0.15, 6, 0.3, crumb, size=10, color=GRAY)
        tb(s, 0.5, 7.08, 5, 0.3, "ⓒ 2026 ABC Corp. All rights reserved.", size=8, color=GRAY)
        tb(s, 5.4, 7.08, 2.5, 0.3, "Strictly Confidential", size=8, color=(170, 60, 60), align=PP_ALIGN.CENTER)
        tb(s, 11.8, 7.08, 1.0, 0.3, str(state["n"]), size=9, color=GRAY, align=PP_ALIGN.RIGHT)
        return s

    # 1. 표지 (개체 틀 없음)
    s = new()
    tb(s, 8.6, 6.2, 4.2, 0.4, "2026년 11월 13일 | 경영전략실", size=12, color=GRAY, align=PP_ALIGN.RIGHT)
    tb(s, 1.0, 3.6, 11, 0.6, "신사업 포트폴리오 재편 및 실행 로드맵", size=20, color=NAVY)
    tb(s, 1.0, 2.4, 11, 1.1, "중장기 성장 전략 수립 결과 보고", size=40, bold=True, color=NAVY)

    # 2. 목차
    s = new(TITLE_ONLY, title="목차")
    box = tb(s, 0.8, 1.7, 6.5, 3.5, ["시장 현황 및 시사점", "성장 전략 방향", "사업 포트폴리오 재편안", "실행 로드맵 및 조직", "투자 계획과 기대 효과"], size=18)
    for p in box.text_frame.paragraphs:
        autonum(p, "romanUcPeriod")
    tb(s, 8.0, 1.9, 4.6, 2.2, ["본 보고서는 2026년 3분기까지의 실적과 외부 시장 조사 결과를 바탕으로 작성되었으며, 수치는 잠정치임"], size=12, fill=(235, 240, 250), shape=True)

    # 3. 헤드라인 메시지 + 3단 카드 + 시사점 띠
    s = new(crumb="Ⅰ. 시장 현황 및 시사점 > 1. 국내 시장")
    tb(s, 0.5, 6.1, 12.3, 0.7, "시사점: 가격 경쟁에서 벗어나 서비스 결합형 상품으로 수익 구조를 바꿔야 하며, 이를 위한 플랫폼 투자가 선행되어야 함", size=13, bold=True, fill=(255, 243, 205), shape=True)
    cols = [
        ("시장 규모", ["2025년 국내 시장은 4.2조 원으로 전년 대비 1.8% 성장에 그침", "2028년까지 연평균 성장률은 1% 안팎으로 전망됨"]),
        ("경쟁 구도", ["상위 3개사 점유율이 68%로 과점 구조가 굳어짐", "후발 주자는 가격 인하로 대응하여 평균 판매가가 6% 하락함"]),
        ("고객 변화", ["기업 고객의 41%가 구독형 계약을 선호한다고 응답함", "구매 결정 주체가 구매팀에서 현업 부서로 이동하고 있음"]),
    ]
    for i in (2, 0, 1):                                    # 저장 순서를 섞는다
        head, body = cols[i]
        x = 0.5 + i * 4.15
        tb(s, x, 2.75, 3.95, 3.0, body, size=13)
        tb(s, x, 2.2, 3.95, 0.45, head, size=15, bold=True, fill=(220, 230, 245), shape=True)
    tb(s, 0.5, 0.6, 12.3, 1.3, "국내 시장은 성장이 정체된 가운데 상위 사업자 중심으로 재편되고 있어, 기존 방식의 점유율 확대 전략은 한계에 이름", size=22, bold=True, color=NAVY)

    # 4. 왼쪽 글 + 오른쪽 표 + 출처
    s = new(TITLE_ONLY, crumb="Ⅰ. 시장 현황 및 시사점 > 2. 해외 시장", title="해외 시장은 동남아를 중심으로 두 자릿수 성장이 이어지고 있음")
    table(s, 6.6, 1.8, 6.2, 3.2, [
        ["지역", "2025년 규모", "연평균 성장률", "주요 경쟁사"],
        ["동남아", "1.9조 원", "12.4%", "A사, B사"],
        ["인도", "1.1조 원", "15.0%", "C사"],
        ["유럽", "6.3조 원", "2.1%", "D사, E사, F사"],
        ["북미", "8.7조 원", "1.5%", "G사, H사"],
    ], size=12)
    tb(s, 0.5, 1.8, 5.8, 3.6, [
        "성장 지역",
        ("동남아와 인도는 제조업 투자 확대로 수요가 빠르게 늘고 있음", 1),
        ("현지 사업자의 기술 수준이 낮아 품질 경쟁력이 통함", 1),
        "성숙 지역",
        ("유럽과 북미는 규모는 크지만 성장률이 낮고 진입 장벽이 높음", 1),
        ("환경 규제 대응 비용이 매년 증가하고 있음", 1),
    ], size=14)
    tb(s, 0.5, 6.55, 9, 0.3, "출처: 글로벌 산업 리서치(2026.6), 당사 분석", size=9, color=GRAY)

    # 5. 2x2 매트릭스 + 세로 축 제목
    s = new(TITLE_ONLY, crumb="Ⅱ. 성장 전략 방향 > 1. 사업 평가", title="사업 매력도와 자사 역량 기준으로 4개 사업군을 재분류함")
    quad = [
        (1.6, 1.8, "육성 사업", ["구독형 유지보수 서비스", "산업용 센서 모듈"]),
        (7.2, 1.8, "핵심 사업", ["정밀 부품 A 라인", "해외 OEM 공급"]),
        (1.6, 4.1, "철수 검토", ["범용 부품 B 라인", "국내 대리점 직영 매장"]),
        (7.2, 4.1, "수익 회수", ["레거시 장비 교체 부품", "기술 라이선스"]),
    ]
    for x, y, head, items in reversed(quad):
        tb(s, x, y + 0.5, 5.3, 1.5, ["- " + t for t in items], size=13)
        tb(s, x, y, 5.3, 0.45, head, size=15, bold=True, fill=(225, 235, 225), shape=True)
    tb(s, 0.1, 3.4, 2.4, 0.4, "사업 매력도 (높음 ↑)", size=11, color=GRAY, rot=270)
    tb(s, 5.0, 6.45, 4.5, 0.3, "자사 역량 (높음 →)", size=11, color=GRAY, align=PP_ALIGN.CENTER)

    # 6. 로드맵: 도형으로 만든 격자
    s = new(TITLE_ONLY, crumb="Ⅳ. 실행 로드맵 및 조직 > 1. 단계별 일정", title="3단계에 걸쳐 2028년까지 포트폴리오 재편을 마무리함")
    phases = ["1단계 (2026)", "2단계 (2027)", "3단계 (2028)"]
    tracks = [
        ("사업 재편", ["범용 부품 라인 매각 협상", "센서 모듈 양산 체계 구축", "신규 사업 매출 비중 30% 달성"]),
        ("조직·인력", ["사업부제 전환", "해외 법인 현지 채용 확대", "성과 연동 보상 체계 정착"]),
        ("시스템", ["구독 플랫폼 1차 개발", "고객 데이터 통합", "예측 정비 서비스 출시"]),
    ]
    for r, (track, cells) in enumerate(tracks):
        y = 2.5 + r * 1.25
        for c in (2, 1, 0):
            tb(s, 2.6 + c * 3.5, y, 3.3, 1.05, cells[c], size=12, fill=(240, 240, 240), shape=True)
        tb(s, 0.5, y, 1.9, 1.05, track, size=13, bold=True, fill=(20, 50, 110), color=(255, 255, 255), shape=True)
    for c, ph in enumerate(phases):
        tb(s, 2.6 + c * 3.5, 1.85, 3.3, 0.5, ph, size=13, bold=True, align=PP_ALIGN.CENTER)

    # 7. 조직도
    s = new(TITLE_ONLY, crumb="Ⅳ. 실행 로드맵 및 조직 > 2. 추진 조직", title="대표이사 직속 추진단을 두고 3개 분과로 운영함")
    tb(s, 9.4, 4.0, 3.2, 0.9, ["시스템 분과", "구독 플랫폼, 데이터 통합"], size=11, shape=True, fill=(240, 240, 240))
    tb(s, 5.1, 4.0, 3.2, 0.9, ["조직 분과", "사업부제 전환, 보상 체계"], size=11, shape=True, fill=(240, 240, 240))
    tb(s, 0.8, 4.0, 3.2, 0.9, ["사업 분과", "매각·인수, 신사업 기획"], size=11, shape=True, fill=(240, 240, 240))
    tb(s, 5.1, 2.8, 3.2, 0.7, "전략 추진단 (단장: 전략실장)", size=12, bold=True, shape=True, fill=(220, 230, 245))
    tb(s, 5.1, 1.75, 3.2, 0.7, "대표이사", size=13, bold=True, shape=True, fill=(20, 50, 110), color=(255, 255, 255))
    tb(s, 9.0, 2.85, 3.6, 0.6, "자문: 외부 전문가 3인", size=11, color=GRAY)
    tb(s, 0.8, 5.4, 11.8, 0.8, "각 분과는 격주로 진행 상황을 추진단에 보고하고, 추진단은 월 1회 경영위원회에 안건을 상정함", size=13)

    # 8. 병합 셀이 있는 큰 표
    s = new(TITLE_ONLY, crumb="Ⅲ. 사업 포트폴리오 재편안 > 2. 사업별 계획", title="사업군별 매출 목표와 투자 규모")
    table(s, 0.5, 2.0, 12.3, 3.9, [
        ["사업군", "세부 사업", "매출 목표 (억 원)", "", "", "투자 (억 원)", "비고"],
        ["", "", "2026", "2027", "2028", "3년 합계", ""],
        ["핵심", "정밀 부품 A", "2,100", "2,250", "2,400", "320", "증설 1회 포함"],
        ["", "해외 OEM", "1,300", "1,520", "1,800", "210", "동남아 법인 설립 후 현지 생산으로 전환 예정"],
        ["육성", "구독 서비스", "120", "340", "720", "450", "플랫폼 개발비 포함"],
        ["", "센서 모듈", "80", "260", "610", "380", ""],
        ["합계", "", "3,600", "4,370", "5,530", "1,360", ""],
    ], size=11, merges=[(0, 2, 0, 4), (0, 0, 1, 0), (0, 1, 1, 1), (0, 6, 1, 6), (2, 0, 3, 0), (4, 0, 5, 0), (6, 0, 6, 1)])
    tb(s, 0.5, 1.5, 6, 0.4, "[표 3-2] 사업군별 3개년 계획", size=12, bold=True)
    tb(s, 0.5, 6.1, 12, 0.4, "※ 철수 검토 및 수익 회수 사업군은 별첨 참조. 금액은 연결 기준 잠정치임", size=10, color=GRAY)

    # 9. 차트 + 해설
    s = new(TITLE_ONLY, crumb="Ⅴ. 투자 계획과 기대 효과 > 1. 재무 효과", title="2028년 영업이익률은 현재의 두 배 수준으로 개선될 전망임")
    data = CategoryChartData()
    data.categories = ["2025", "2026", "2027", "2028"]
    data.add_series("매출 (억 원)", (3400, 3600, 4370, 5530))
    data.add_series("영업이익 (억 원)", (170, 215, 350, 560))
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.7), Inches(7.2), Inches(4.5), data)
    gf.chart.has_title = True
    gf.chart.chart_title.text_frame.text = "매출 및 영업이익 전망"
    gf.chart.has_legend = True
    gf.chart.plots[0].has_data_labels = True
    tb(s, 8.1, 1.9, 4.7, 3.8, [
        "영업이익률",
        ("2025년 5.0% → 2028년 10.1%", 1),
        "개선 요인",
        ("구독 서비스의 높은 마진 구조", 1),
        ("저수익 범용 부품 라인 정리", 1),
        ("해외 현지 생산에 따른 물류비 절감", 1),
    ], size=14)

    # 10. 중첩 그룹으로 만든 절차도 + 설명선
    s = new(TITLE_ONLY, crumb="Ⅲ. 사업 포트폴리오 재편안 > 3. 매각 절차", title="범용 부품 라인 매각은 4단계 절차로 진행함")
    outer = s.shapes.add_group_shape()
    steps = [("① 대상 확정", "자산 범위와 인력 승계 원칙 확정"), ("② 잠재 인수자 접촉", "국내외 5개사 대상 예비 협의"),
             ("③ 실사 및 협상", "가격과 고용 조건 협상"), ("④ 계약 및 이전", "이사회 승인 후 자산 이전")]
    for i in (3, 1, 0, 2):
        head, desc = steps[i]
        inner = outer.shapes.add_group_shape()
        d = inner.shapes.add_textbox(Inches(0.6 + i * 3.1), Inches(3.0), Inches(2.8), Inches(0.9))
        d.text_frame.word_wrap = True
        d.text_frame.text = desc
        d.text_frame.paragraphs[0].runs[0].font.size = Pt(12)
        h = inner.shapes.add_shape(1, Inches(0.6 + i * 3.1), Inches(2.1), Inches(2.8), Inches(0.7))
        h.text_frame.text = head
        h.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
    tb(s, 7.2, 4.5, 5.4, 1.2, ["유의 사항", "실사 기간 중 핵심 인력 이탈 방지를 위한 잔류 보상안을 사전에 마련해야 함"], size=12, fill=(255, 243, 205), shape=True)
    tb(s, 0.6, 4.5, 6.2, 1.2, "전체 일정은 약 9개월로 예상되며, 2026년 4분기 중 우선협상대상자 선정을 목표로 함", size=13)

    # 11. KPI 카드 + 아래 2단
    s = new(TITLE_ONLY, crumb="Ⅴ. 투자 계획과 기대 효과 > 2. 핵심 지표", title="핵심 성과 지표 (2028년 목표)")
    kpis = [("5,530억", "매출"), ("10.1%", "영업이익률"), ("30%", "신사업 매출 비중"), ("45%", "해외 매출 비중")]
    for i, (num, label) in enumerate(kpis):
        x = 0.5 + i * 3.1
        tb(s, x, 2.75, 2.9, 0.4, label, size=13, color=GRAY, align=PP_ALIGN.CENTER)
        tb(s, x, 1.8, 2.9, 0.9, num, size=34, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    tb(s, 6.9, 3.7, 5.9, 2.3, ["위험 요인", "- 매각 지연 시 투자 재원 확보에 차질", "- 구독 전환 속도가 예상보다 느릴 가능성"], size=13)
    tb(s, 0.5, 3.7, 5.9, 2.3, ["달성 조건", "- 2026년 내 구독 플랫폼 1차 출시", "- 동남아 법인의 현지 생산 조기 안정화"], size=13)

    # 12. 글이 많은 3단계 글머리 기호 (본문 개체 틀)
    s = new(CONTENT, crumb="Ⅱ. 성장 전략 방향 > 2. 전략 원칙", title="성장 전략의 세 가지 원칙")
    body = s.placeholders[1]
    body.left, body.top, body.width, body.height = Inches(0.5), Inches(1.6), Inches(12.3), Inches(4.9)
    tf = body.text_frame
    items = [
        ("선택과 집중: 모든 사업을 유지하는 대신 역량이 통하는 분야에 자원을 몰아 줌", 0),
        ("매력도와 역량이 모두 낮은 사업은 2027년까지 정리하고, 회수한 자원은 육성 사업에 재투자함", 1),
        ("정리 대상 선정 기준은 최근 3년 평균 ROIC 5% 미만", 2),
        ("제품에서 서비스로: Recurring revenue 비중을 높여 경기 변동에 덜 민감한 수익 구조를 만듦", 0),
        ("구독형 유지보수, predictive maintenance, 원격 진단을 하나의 상품으로 묶어 판매함", 1),
        ("국내에서 해외로: 성장 지역에 생산과 영업 거점을 직접 확보함", 0),
        ("1차 대상국은 베트남, 인도네시아, 태국이며 인도는 파트너십으로 진입함", 1),
    ]
    tf.text = items[0][0]
    for text, level in items[1:]:
        p = tf.add_paragraph()
        p.text, p.level = text, level
    for p in tf.paragraphs:
        for r in p.runs:
            r.font.size = Pt(18 - 2 * p.level)

    # 13. 제목 없는 쪽: 그림 설명만
    s = new(crumb="별첨")
    tb(s, 8.3, 2.0, 2.2, 0.5, "물류 거점", size=12, shape=True, fill=(240, 240, 240))
    tb(s, 1.2, 2.0, 2.2, 0.5, "본사 공장", size=12, shape=True, fill=(240, 240, 240))
    tb(s, 4.8, 3.6, 2.2, 0.5, "해외 법인", size=12, shape=True, fill=(240, 240, 240))
    tb(s, 3.6, 2.05, 4.5, 0.4, "완제품 주 3회 운송", size=10, color=GRAY, align=PP_ALIGN.CENTER)
    tb(s, 7.3, 3.65, 3, 0.4, "반제품 월 2회 선적", size=10, color=GRAY)

    # 14. 좌우 표 두 개
    s = new(TITLE_ONLY, crumb="별첨", title="별첨: 국내외 주요 거점 현황")
    table(s, 6.9, 2.2, 5.9, 2.0, [["해외 거점", "설립", "인원"], ["베트남 법인", "2026 예정", "40명"], ["태국 사무소", "2024", "12명"]], size=11)
    table(s, 0.5, 2.2, 5.9, 2.6, [["국내 거점", "기능", "인원"], ["본사 (서울)", "기획, 영업", "210명"], ["1공장 (창원)", "정밀 부품", "480명"], ["2공장 (구미)", "범용 부품", "350명"]], size=11)
    tb(s, 6.9, 1.75, 5, 0.35, "해외", size=13, bold=True)
    tb(s, 0.5, 1.75, 5, 0.35, "국내", size=13, bold=True)

    # 15. 맺음
    s = new()
    tb(s, 1.0, 3.0, 11.3, 1.0, "감사합니다", size=40, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    tb(s, 1.0, 4.2, 11.3, 0.5, "문의: 경영전략실 전략기획팀", size=14, color=GRAY, align=PP_ALIGN.CENTER)

    to_master(prs, tb(prs.slides[0], 11.6, 0.12, 1.4, 0.35, "ABC Corp.", size=11, bold=True, color=NAVY, align=PP_ALIGN.RIGHT))
    prs.save(HERE / "complex_consulting.pptx")
    print("saved complex_consulting.pptx")


# ====================================================================== 텍스트 상자로만 만든 자료

def messy():
    prs = Presentation()
    BLANK = prs.slide_layouts[6]
    total = 9
    state = {"n": 0}

    def new():
        s = prs.slides.add_slide(BLANK)
        state["n"] += 1
        tb(s, 3.5, 2.8, 5, 1.2, "CONFIDENTIAL", size=54, bold=True, color=(232, 232, 232), rot=-35)
        tb(s, 8.3, 0.15, 1.5, 0.4, "대외비", size=12, bold=True, color=(200, 30, 30), align=PP_ALIGN.CENTER)
        tb(s, 4.0, 7.05, 2, 0.3, "Page %d of %d" % (state["n"], total), size=9, color=GRAY, align=PP_ALIGN.CENTER)
        tb(s, 0.3, 7.05, 2, 0.3, "2026-11-13", size=9, color=GRAY)
        return s

    # 1. 표지: 큰 글이 여러 개
    s = new()
    tb(s, 0.8, 4.3, 8.4, 0.6, "Quarterly Business Review", size=24, color=GRAY)
    tb(s, 0.8, 5.2, 8.4, 0.5, "영업본부 | 3분기", size=16)
    tb(s, 0.8, 2.9, 8.4, 1.2, "2026년 3분기 영업 실적 검토", size=36, bold=True)

    # 2. 제목보다 큰 숫자가 본문에 있는 쪽
    s = new()
    tb(s, 5.3, 2.0, 4.2, 1.5, "87%", size=80, bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    tb(s, 5.3, 3.9, 4.2, 0.5, "연간 목표 대비 누적 달성률", size=14, align=PP_ALIGN.CENTER)
    tb(s, 0.5, 2.0, 4.5, 3.5, ["3분기 매출은 912억 원으로 분기 목표를 4% 초과함", "누적 매출은 2,610억 원이며 연간 목표 3,000억 원 달성이 유력함", "신규 고객 매출 비중은 18%로 전 분기보다 3%p 상승함"], size=15)
    tb(s, 0.5, 0.7, 9, 0.8, "3분기 실적 요약", size=28, bold=True)

    # 3. 왼쪽 세로 띠에 제목
    s = new()
    tb(s, 3.4, 4.0, 6.2, 2.4, ["수도권", "- 대형 고객 2곳 재계약으로 목표 초과", "지방", "- 제조업 경기 둔화로 신규 수주 감소"], size=15)
    tb(s, 3.4, 1.0, 6.2, 2.6, ["전체 수주액은 1,040억 원으로 전년 동기 대비 7% 증가했으나 지역별 편차가 큼", "수도권은 12% 증가, 지방은 3% 감소함"], size=15)
    tb(s, 0.4, 1.0, 2.6, 5.4, "지역별 수주 현황", size=26, bold=True, fill=(20, 50, 110), color=(255, 255, 255), shape=True)

    # 4. 높이가 다른 3단 + 아래 전체 폭 문단 + 단 위에 겹친 메모
    s = new()
    tb(s, 0.5, 5.6, 9, 1.0, "세 제품군 모두 원가 상승 압력을 받고 있어 4분기에는 가격 조정 협상이 불가피함", size=14, bold=True)
    tb(s, 6.7, 1.6, 2.9, 2.2, ["제품군 C", "매출 198억 원", "신제품 출시 지연"], size=13)
    tb(s, 0.5, 1.6, 2.9, 3.6, ["제품군 A", "매출 420억 원", "주력 고객의 증설로 수요 증가", "납기 지연 2건 발생", "재고 회전일 41일"], size=13)
    tb(s, 3.6, 1.6, 2.9, 2.9, ["제품군 B", "매출 294억 원", "경쟁사 가격 인하로 점유율 2%p 하락", "대체 소재 검토 중"], size=13)
    tb(s, 6.0, 4.0, 3.5, 1.0, "메모: 제품군 C의 출시 일정은 11월 말 재확정 예정", size=11, fill=(255, 243, 205), shape=True)
    tb(s, 0.5, 0.7, 9, 0.7, "제품군별 실적", size=28, bold=True)

    # 5. 계단식으로 조금씩 겹친 상자
    s = new()
    for i, text in reversed(list(enumerate(["1차: 고객 요구 접수", "2차: 기술 검토 및 견적", "3차: 계약 조건 협상", "4차: 수주 확정 및 생산 의뢰"]))):
        tb(s, 0.6 + i * 2.0, 1.8 + i * 1.0, 3.0, 1.15, text, size=14, fill=(230, 236, 246), shape=True)
    tb(s, 0.5, 0.7, 9, 0.7, "수주 진행 단계", size=28, bold=True)

    # 6. 텍스트 상자로 만든 표 (진짜 표가 아님)
    s = new()
    grid = [("구분", "목표", "실적", "달성률"), ("매출", "880억", "912억", "104%"), ("영업이익", "70억", "66억", "94%"), ("수주", "1,000억", "1,040억", "104%")]
    for r in reversed(range(len(grid))):
        for c in reversed(range(4)):
            tb(s, 0.8 + c * 2.1, 1.8 + r * 0.55, 2.0, 0.5, grid[r][c], size=13, bold=(r == 0))
    tb(s, 0.8, 4.4, 8.4, 1.2, "영업이익은 원자재 가격 상승분을 판매가에 반영하지 못해 목표에 미달함", size=14)
    tb(s, 0.5, 0.7, 9, 0.7, "목표 대비 실적", size=28, bold=True)

    # 7. 영문 문단
    s = new()
    tb(s, 0.5, 1.7, 9, 3.8, [
        "Overseas revenue grew 14 percent year over year, driven primarily by repeat orders from two long-standing customers in Vietnam and a newly signed distribution agreement in Indonesia.",
        "However, gross margin declined by 1.2 percentage points because freight costs remained elevated throughout the quarter and the weaker won only partially offset the increase.",
        "Management expects margins to recover in Q4 as the new local warehouse becomes fully operational.",
    ], size=15)
    tb(s, 0.5, 0.7, 9, 0.7, "Overseas Business Update", size=28, bold=True)

    # 8. 다양한 자동 번호와 줄바꿈
    s = new()
    box = tb(s, 5.2, 1.7, 4.4, 2.0, ["가격 조정 협상 착수", "신규 대리점 2곳 계약", "재고 감축 계획 수립"], size=14)
    for p in box.text_frame.paragraphs:
        autonum(p, "alphaLcParenR")
    box = tb(s, 0.5, 1.7, 4.4, 2.0, ["제품군 C 출시 일정 확정", "지방 영업 인력 재배치", "해외 창고 가동 점검"], size=14)
    for p in box.text_frame.paragraphs:
        autonum(p, "arabicPeriod", start=4)
    box = tb(s, 0.5, 4.2, 9, 1.4, "담당: 영업기획팀", size=14)
    para = box.text_frame.paragraphs[0]
    for extra in ("기한: 2026년 12월 15일", "보고: 월간 영업 회의"):     # 문단 안 줄바꿈(Shift+Enter)
        para.add_line_break()
        r = para.add_run()
        r.text = extra
        r.font.size = Pt(14)
    tb(s, 0.5, 0.7, 9, 0.7, "4분기 실행 과제", size=28, bold=True)

    # 9. 질의응답
    s = new()
    tb(s, 0.8, 3.0, 8.4, 1.2, "Q & A", size=54, bold=True, align=PP_ALIGN.CENTER)

    prs.save(HERE / "messy_report.pptx")
    print("saved messy_report.pptx")


if __name__ == "__main__":
    consulting()
    messy()
