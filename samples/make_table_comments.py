"""테스트용 샘플 PPTX 생성기: 표 위에 코멘트를 얹은 슬라이드.

PDF에는 '이 글자는 표의 것'이라는 표시가 없어서, 표 위에 얹은 글상자의 글이 칸의 글과 섞이기 쉽다.
이 샘플로 그 글을 표에서 제대로 떼어 내는지 확인한다(docparse/pdf_common.py의 find_overlays).

  1~5, 8~11   코멘트가 표에서 떨어져 표 다음에 따로 나와야 한다
  7, 13       지금 규칙으로는 가려내지 못한다(마지막 칸 안의 코멘트, 칸의 글과 같은 모양의 코멘트)
  12          빈 칸 하나에 들어간 코멘트는 그 칸의 글로 남는다
  6, 14       코멘트가 없는 표. 결과가 달라지면 안 된다

사용법:  python samples/make_table_comments.py   →  samples/table_comments.pptx
PDF는 PowerPoint에서 "PDF로 저장"해 samples/table_comments.pdf 로 만든다.
두 파일을 함께 돌리면 PPTX와 PDF 결과가 얼마나 같은지 비교 리포트가 나온다.
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUT = Path(__file__).parent / "table_comments.pptx"
FONT = "맑은 고딕"
RED, BLUE, GREEN, BLACK = RGBColor(0xD0, 0x10, 0x10), RGBColor(0x10, 0x50, 0xC8), RGBColor(0x0A, 0x7A, 0x3A), RGBColor(0, 0, 0)
TL, TT, CW, RH = 0.8, 1.7, 2.9, 0.7          # 표 왼쪽, 위, 열 너비, 행 높이 (인치)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
blank = prs.slide_layouts[6]


def write(tf, text, size, color=None, bold=False):
    tf.word_wrap = True
    for i, line in enumerate(text.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size, r.font.name, r.font.bold = Pt(size), FONT, bold
        if color is not None:
            r.font.color.rgb = color


def table(slide, rows, colors=None, merges=(), tight=False, cw=CW):
    R, C = len(rows), len(rows[0])
    shape = slide.shapes.add_table(R, C, Inches(TL), Inches(TT), Inches(cw * C), Inches(RH * R))
    for r in range(R):
        shape.table.rows[r].height = Inches(RH)
        for c in range(C):
            cell = shape.table.cell(r, c)
            p = cell.text_frame.paragraphs[0]
            if rows[r][c]:
                run = p.add_run()
                run.text = rows[r][c]
                run.font.size, run.font.name = Pt(16), FONT
                if colors and (r, c) in colors:
                    run.font.color.rgb = colors[(r, c)]
            if tight:                              # 안쪽 여백 0, 한 열 건너 오른쪽 정렬 → 옆 칸 글과 거의 붙는다
                cell.margin_left = cell.margin_right = 0
                p.alignment = PP_ALIGN.RIGHT if c % 2 == 0 else PP_ALIGN.LEFT
    for r0, c0, r1, c1 in merges:
        shape.table.cell(r0, c0).merge(shape.table.cell(r1, c1))


def comment(slide, text, left, top, width, height, color=RED, size=14, bold=True, outline=False):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    write(box.text_frame, text, size, color, bold)
    if outline:
        box.line.color.rgb = RED
        box.line.width = Pt(1.5)


def note_shape(slide, text, left, top, width, height, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    shp = slide.shapes.add_shape(shape, Inches(left), Inches(top), Inches(width), Inches(height))
    shp.fill.solid()
    shp.fill.fore_color.rgb = RGBColor(0xFF, 0xF2, 0xB3)
    shp.line.color.rgb = RED
    write(shp.text_frame, text, 14, RED, True)


def page(name, rows, source, build=None, before=None, **kw):
    slide = prs.slides.add_slide(blank)
    box = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.8))
    write(box.text_frame, name, 28, bold=True)
    if before:
        before(slide)                              # 표보다 먼저 그린다(표 아래에 깔린다)
    table(slide, rows, **kw)
    if build:
        build(slide)
    box = slide.shapes.add_textbox(Inches(0.8), Inches(6.6), Inches(11.7), Inches(0.4))
    write(box.text_frame, source, 11)


page("1. 코멘트가 여러 칸에 걸친 경우",
     [["구분", "2025년 실적", "2026년 계획", "2027년 전망"],
      ["설비 투자", "120억 원", "150억 원", "180억 원"],
      ["연구 개발", "80억 원", "95억 원", "110억 원"],
      ["해외 법인", "40억 원", "60억 원", "90억 원"],
      ["합계", "240억 원", "305억 원", "380억 원"]],
     "출처: 재무팀 내부 자료 (2026.1)",
     lambda s: comment(s, "※ 2027년 전망은 잠정치이며 3월 이사회에서 확정 예정", TL + CW + 1.2, TT + RH * 2 + 0.36, 6.4, 0.35))

page("2. 코멘트가 표 밖으로 걸친 경우",
     [["지역", "매출", "영업이익"],
      ["수도권", "5,200", "610"],
      ["영남권", "3,100", "280"],
      ["호남권", "1,450", "95"],
      ["해외", "2,800", "-120"]],
     "출처: 영업관리팀 집계 (단위: 백만 원)",
     lambda s: comment(s, "← 해외는 환율 영향으로 적자 전환 (원인 분석 중)", TL + CW * 2 + 1.5, TT + RH * 4 + 0.15, 6.0, 0.35, BLUE))

page("3. 코멘트가 한 칸 안에 들어간 경우",
     [["제품", "출시 시기", "목표 판매량", "담당"],
      ["알파", "2026년 3월", "12,000대", "1사업부"],
      ["베타", "2026년 7월", "8,500대", "2사업부"],
      ["감마", "2027년 1월", "20,000대", "1사업부"],
      ["델타", "미정", "미정", "신사업팀"]],
     "출처: 상품기획팀 로드맵 초안",
     lambda s: comment(s, "(일정 재검토)", TL + CW + 0.9, TT + RH * 2 + 0.34, 1.8, 0.33, BLUE, 12))

page("4. 색 채운 말풍선이 표를 덮은 경우",
     [["공정", "현재 수율", "목표 수율", "개선 과제"],
      ["전처리", "97.2%", "98.5%", "세정 조건 최적화"],
      ["증착", "94.8%", "97.0%", "챔버 교체 주기 단축"],
      ["식각", "96.1%", "98.0%", "레시피 표준화"],
      ["검사", "99.3%", "99.7%", "자동 판정 도입"]],
     "출처: 생산기술팀 월간 보고",
     lambda s: note_shape(s, "증착 공정이 병목\n2분기 내 설비 투자 결정 필요", TL + CW * 2 + 0.6, TT + RH * 2 + 0.3, 4.0, 0.95))

page("5. 두 줄 코멘트와 머리글 위 코멘트",
     [["부서", "정원", "현원", "충원 계획"],
      ["기획", "12명", "10명", "상반기 2명"],
      ["개발", "45명", "38명", "연중 7명"],
      ["영업", "30명", "31명", "없음"],
      ["지원", "15명", "13명", "하반기 2명"]],
     "출처: 인사팀 인력 운영 계획",
     lambda s: (comment(s, "개발 인력 충원이 가장 시급함\n경력직 위주로 채용 진행", TL + 1.6, TT + RH * 2 + 0.33, 5.0, 0.7, GREEN),
                comment(s, "※ 12월 말 기준", TL + CW * 3 + 1.0, TT + 0.36, 1.8, 0.3, RED, 11)))

page("6. 코멘트 없이 표 안에 색 글자만 있는 경우",
     [["항목", "1분기", "2분기", "증감"],
      ["매출액", "1,820", "1,760", "-60"],
      ["매출원가", "1,210", "1,150", "-60"],
      ["판관비", "380", "410", "+30"],
      ["영업이익", "230", "200", "-30"]],
     "출처: 분기 결산 자료 (단위: 억 원)",
     colors={(1, 3): RED, (2, 3): RED, (4, 3): RED, (3, 3): BLUE, (4, 0): BLUE, (4, 1): BLUE, (4, 2): BLUE})

page("7. 마지막 칸 안에만 들어간 코멘트",
     [["거래처", "계약액", "입금액", "미수금"],
      ["가나상사", "4,200", "4,200", "0"],
      ["다라물산", "3,650", "2,900", "750"],
      ["마바기업", "1,980", "1,980", "0"],
      ["합계", "9,830", "9,080", "750"]],
     "출처: 채권관리 대장 (단위: 만 원)",
     lambda s: comment(s, "(연말 회수 예정)", TL + CW * 3 + 0.7, TT + RH * 4 + 0.34, 2.0, 0.33, RED, 12))

page("8. 테두리 있는 네모 상자가 표를 덮은 경우",
     [["설비", "도입 연도", "가동률", "교체 계획"],
      ["1호기", "2014년", "72%", "2027년 교체"],
      ["2호기", "2017년", "85%", "유지"],
      ["3호기", "2020년", "91%", "유지"],
      ["4호기", "2023년", "94%", "증설 검토"]],
     "출처: 설비관리팀 자산 현황",
     lambda s: note_shape(s, "1호기 교체 예산 미반영\n경영회의 안건 상정 필요", TL + CW + 1.4, TT + RH + 0.25, 4.2, 0.95, MSO_SHAPE.RECTANGLE))

page("9. 테두리만 있는 글상자가 표 위에 있는 경우",
     [["교육 과정", "대상", "시간", "이수율"],
      ["정보보안", "전 직원", "2시간", "98%"],
      ["직무 전문", "팀장급", "16시간", "74%"],
      ["리더십", "임원", "8시간", "61%"],
      ["안전보건", "생산직", "4시간", "100%"]],
     "출처: 인재개발팀 교육 실적",
     lambda s: comment(s, "리더십 과정 이수율 저조 → 하반기 재실시", TL + CW + 0.5, TT + RH * 3 + 0.33, 5.6, 0.36, BLUE, 13, outline=True))

page("10. 코멘트가 표보다 먼저 그려진 경우",
     [["원재료", "단가", "사용량", "금액"],
      ["강판", "850", "1,200톤", "1,020"],
      ["알루미늄", "2,400", "300톤", "720"],
      ["수지", "1,100", "450톤", "495"],
      ["합계", "", "1,950톤", "2,235"]],
     "출처: 구매팀 원가 자료 (단위: 천 원, 백만 원)",
     before=lambda s: comment(s, "단가는 3분기 평균 기준임", TL + CW + 0.8, TT + RH * 2 + 0.36, 4.4, 0.33, GREEN, 13))

page("11. 합친 칸이 있는 표 위의 코멘트",
     [["구분", "국내", "", "해외", ""],
      ["", "매출", "이익", "매출", "이익"],
      ["가전", "310", "28", "190", "12"],
      ["부품", "220", "31", "405", "47"],
      ["서비스", "95", "22", "30", "4"]],
     "출처: 사업부별 손익 (단위: 억 원)",
     lambda s: comment(s, "해외 부품 이익률이 가장 높음", TL + 2.3 * 2 + 0.9, TT + RH * 3 + 0.36, 5.0, 0.33, RED, 13),
     merges=[(0, 0, 1, 0), (0, 1, 0, 2), (0, 3, 0, 4)], cw=2.3)

page("12. 빈 칸에 들어간 코멘트",
     [["과제", "담당", "진척률", "비고"],
      ["ERP 고도화", "IT팀", "80%", ""],
      ["물류 자동화", "SCM팀", "45%", ""],
      ["신규 채널", "", "", "착수 전"],
      ["품질 인증", "QA팀", "100%", "완료"]],
     "출처: 전사 과제 관리 현황",
     lambda s: (comment(s, "일정 지연", TL + CW * 3 + 0.1, TT + RH * 2 + 0.1, 1.6, 0.33, RED, 14),
                comment(s, "담당 부서 미정 (3월 중 확정)", TL + CW + 0.2, TT + RH * 3 + 0.12, 4.6, 0.33, BLUE, 13)))

page("13. 칸의 글과 같은 모양의 코멘트",
     [["지표", "목표", "실적", "달성률"],
      ["고객 만족도", "85점", "88점", "104%"],
      ["재구매율", "40%", "37%", "93%"],
      ["응답 시간", "30초", "42초", "71%"],
      ["불만 건수", "50건", "38건", "124%"]],
     "출처: 고객경험팀 분기 지표",
     lambda s: comment(s, "개선 필요", TL + CW * 3 + 1.2, TT + RH * 3 + 0.32, 1.5, 0.35, BLACK, 16, bold=False))

page("14. 옆 칸과 글이 붙는 빽빽한 표",
     [["품목", "코드", "수량", "단위", "단가", "통화"],
      ["볼트", "B-1001", "12,000", "개", "35", "원"],
      ["너트", "N-2002", "12,500", "개", "18", "원"],
      ["와셔", "W-3003", "24,000", "개", "7", "원"],
      ["스프링", "S-4004", "3,200", "개", "120", "원"]],
     "출처: 자재 마스터",
     tight=True, cw=1.6)

prs.save(str(OUT))
print("저장:", OUT)
