"""걸러내기(2단계) 시험용 샘플 PPTX 생성기.

기술 아이디어를 적은 줄과 일정·예산·시장 같은 일반 업무 줄이 한 문서에 섞여 있다.
지어낸 내용이며, 걸러내기 모델과 정답 붙이는 화면이 도는지 확인하는 데 쓴다.

사용법:  python samples/make_tech_review.py   →  samples/tech_review.pptx
         python samples/make_tech_review.py --answers 파일.json   (시험용: 줄마다의 정답도 함께 적는다)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

OUT = Path(__file__).parent / "tech_review.pptx"

# (슬라이드 제목, [(줄, 특허출원 검토가 필요한가)])
SLIDES = [
    ("1. 개발 배경", [
        ("기존 광학 검사는 미세 결함을 놓치는 비율이 높아 재검사 비용이 늘고 있음", 0),
        ("3분기 검사 공정의 불량 유출 건수는 14건으로 전 분기보다 5건 증가함", 0),
        ("고객사는 2027년 양산 전까지 검출률 99.5% 이상을 요구함", 0),
    ]),
    ("2. 제안 구조", [
        ("파장이 서로 다른 조명 두 개를 번갈아 켜고 두 영상의 차이를 이용해 표면 결함과 내부 결함을 구분하는 구조를 제안함", 1),
        ("카메라와 조명 사이에 편광 필터를 회전시키는 구동부를 두어 반사광에 의한 noise를 줄임", 1),
        ("영상 취득 주기를 스테이지 이동 속도에 맞춰 자동으로 조절하는 동기화 회로를 추가함", 1),
    ]),
    ("3. 결함 판정 알고리즘", [
        ("정상 패턴을 학습한 autoencoder의 복원 오차를 이용해 결함 후보 영역을 먼저 추려 냄", 1),
        ("후보 영역만 고해상도로 다시 촬영해 분류 모델에 입력함으로써 처리 시간을 40% 줄임", 1),
        ("판정 문턱값을 제품 종류별 이력 데이터로 자동 보정하는 방법을 적용함", 1),
        ("알고리즘 검증은 12월 2주차까지 완료할 예정임", 0),
    ]),
    ("4. 개발 일정", [
        ("시제품 제작은 2027년 1월, 고객사 평가는 2027년 3월로 계획함", 0),
        ("양산 적용 목표는 2027년 6월임", 0),
        ("일정이 늦어지면 외주 가공 업체를 추가로 확보함", 0),
    ]),
    ("5. 예산 및 인력", [
        ("총 개발비는 18억 원이며 이 가운데 장비 구매가 11억 원임", 0),
        ("개발 인력은 기구 4명, 전장 3명, 소프트웨어 5명으로 구성함", 0),
        ("소프트웨어 인력 2명은 내년 상반기에 충원할 예정임", 0),
    ]),
    ("6. 진동 저감 방안", [
        ("스테이지 가감속 구간의 잔류 진동을 줄이기 위해 input shaping 필터를 구동 명령에 적용함", 1),
        ("카메라 지지대에 점탄성 damper를 넣고 고유 진동수를 구동 주파수 대역 밖으로 옮김", 1),
        ("진동 센서 신호를 feed-forward로 보정하여 영상 흔들림을 0.3 pixel 이하로 억제함", 1),
    ]),
    ("7. 경쟁사 동향", [
        ("A사는 2026년 하반기에 유사 장비를 출시했으며 가격은 당사 목표가보다 15% 높음", 0),
        ("B사는 유럽 고객사 두 곳과 공급 계약을 체결함", 0),
        ("국내 검사 장비 시장은 해마다 8% 성장할 것으로 전망됨", 0),
    ]),
    ("8. 데이터 처리 구조", [
        ("검사 영상을 장비 안의 edge 서버에서 1차 압축한 뒤 결함 영역만 원본 해상도로 중앙 서버에 전송함", 1),
        ("전송 대기열이 일정 길이를 넘으면 압축률을 단계적으로 높여 실시간성을 유지하는 방식을 사용함", 1),
        ("서버 증설 비용은 내년 예산에 반영함", 0),
    ]),
    ("9. 열 변형 보정", [
        ("오래 가동하면 렌즈 경통의 열팽창으로 초점이 어긋나는 문제를 온도 센서 값에 따른 초점 보정 table로 해결함", 1),
        ("보정 table은 장비별 calibration 단계에서 자동으로 만들어지고 주기적으로 갱신됨", 1),
        ("냉각 팬 소음에 대한 작업자 민원이 2건 접수됨", 0),
    ]),
    ("10. 소재 변경 검토", [
        ("스테이지 상판을 알루미늄에서 탄소섬유 복합재로 바꾸어 무게를 35% 줄이고 가속 성능을 높임", 1),
        ("복합재와 금속 프레임의 접합부에 열팽창 차이를 흡수하는 슬릿 구조를 적용함", 1),
        ("소재 단가는 기존의 2.1배이며 수량 할인을 협상하고 있음", 0),
    ]),
    ("11. Interface 개선", [
        ("Operator가 결함 image를 확인할 때 비슷한 결함 사례를 자동으로 검색해 함께 보여 주는 UI를 구현함", 1),
        ("Review 결과가 학습 data에 자동으로 반영되어 분류 model을 주기적으로 재학습함", 1),
        ("사용자 교육은 장비 입고 후 2주 안에 진행함", 0),
    ]),
    ("12. 향후 계획", [
        ("12월 경영회의에 중간 결과를 보고함", 0),
        ("고객사 방문 일정은 1월 중 확정함", 0),
        ("평가용 시료는 고객사에서 30매를 제공받기로 함", 0),
    ]),
]


def textbox(slide, x, y, w, h, lines, size=14, bold=False):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run()
        r.text = line
        r.font.size = Pt(size)
        r.font.bold = bold
        p.space_after = Pt(8)
    return box


def main():
    prs = Presentation()
    blank = prs.slide_layouts[6]
    cover = prs.slides.add_slide(blank)
    textbox(cover, 1.0, 2.6, 8, 1.0, ["차세대 검사 장비 개발 현황 보고"], size=30, bold=True)
    textbox(cover, 1.0, 3.8, 8, 0.5, ["설비개발팀 | 2026. 11."], size=14)
    for title, rows in SLIDES:
        slide = prs.slides.add_slide(blank)
        textbox(slide, 0.6, 0.4, 8.8, 0.7, [title], size=24, bold=True)
        textbox(slide, 0.6, 1.5, 8.8, 4.5, [text for text, _ in rows], size=15)
    prs.save(str(OUT))
    print("만듦:", OUT)
    if "--answers" in sys.argv:
        path = Path(sys.argv[sys.argv.index("--answers") + 1])
        path.write_text(json.dumps([[text, label] for _, rows in SLIDES for text, label in rows], ensure_ascii=False, indent=1), encoding="utf-8")
        print("정답:", path)


if __name__ == "__main__":
    main()
