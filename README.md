# PDF/PPTX 텍스트 추출 방식 비교

PDF와 PPTX에서 글을 사람이 읽는 순서대로 뽑고, 매 쪽 반복되는 문구를 빼고, 쪽 제목을 따로 뽑습니다.
세 가지 방식의 결과를 before/after로 나란히 보여 주는 HTML 리포트를 만듭니다.

| 방식 | 내용 | 필요한 것 |
|---|---|---|
| A | 글자 좌표 규칙 (재귀 X-Y cut). PDF는 PyMuPDF와 pdfplumber 두 가지로 실행 | `requirements.txt` |
| B | Docling (레이아웃 분석 모델) | `requirements-docling.txt` + 모델 파일 |
| C | Docling의 영역·순서·분류 + A의 글자·규칙 | B와 같음 |

## 설치와 실행 (Windows, 배치파일)

1. 이 폴더를 통째로 PC에 둡니다.
2. `install.bat`을 더블클릭합니다. 전용 가상 환경(`.venv`)을 만들고 라이브러리를 설치합니다.
   Docling(B, C 방식)을 설치할지는 중간에 물어봅니다. 설치하지 않아도 A 방식은 쓸 수 있습니다.
3. `run.bat`을 더블클릭해 경로를 입력하거나, 자료를 `run.bat` 위로 끌어다 놓습니다. 폴더 하나, 파일 하나, 파일이나 폴더 여러 개 모두 됩니다. 수십 개가 넘으면 한 폴더에 모아 폴더를 놓으세요(한 번에 넘길 수 있는 경로 길이에 한도가 있습니다).
   끝나면 `out\index.html`이 브라우저로 열립니다.

Python 3.9 이상이 필요합니다(Docling은 3.10 이상). Python이 없으면 먼저 설치하되,
설치 화면에서 "Add python.exe to PATH"를 체크하세요.

### 인터넷이 막힌 PC에 설치하기

1. 인터넷이 되는 Windows PC에서 `download_wheels.bat`을 실행합니다. `wheels` 폴더에 설치 파일이 모입니다.
   두 PC의 Python 버전이 같아야 합니다(예: 둘 다 3.11).
2. 폴더 전체를 `wheels` 폴더와 함께 회사 PC로 옮긴 뒤 `install.bat`을 실행합니다.
   `wheels` 폴더가 있으면 인터넷 없이 그 안의 파일로 설치합니다.

## 직접 명령으로 실행하기

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-docling.txt
python compare.py 자료폴더 -o out
```

- 폴더 안의 `.pdf`, `.pptx`를 모두 처리하고 `out\index.html`을 만듭니다.
- Docling이 설치되어 있지 않으면 A 방식만 실행합니다. 일부러 빼려면 `--no-docling`.
- 이름이 같은 PPTX와 PDF(예: `보고.pptx`, `보고.pdf`)를 함께 넣으면 두 결과가 얼마나 같은지 비교하는
  `보고.pptx-vs-pdf.html`도 만듭니다. 방식을 고를 때 가장 중요한 근거입니다.
- `samples` 폴더의 샘플로 먼저 시험해 볼 수 있습니다: `run.bat samples`

### 인터넷이 안 되는 PC에서 Docling 쓰기

인터넷이 되는 PC에서 모델을 받아(약 670MB) 폴더째 옮긴 뒤 경로를 지정합니다.

```bat
.venv\Scripts\docling-tools models download layout tableformer -o docling_models
```

`docling_models` 폴더를 프로그램 폴더에 두면 `run.bat`이 자동으로 사용합니다.
직접 실행할 때는 `--docling-models docling_models`를 붙입니다.

### 옵션

| 옵션 | 뜻 |
|---|---|
| `--keywords "사내한,Draft"` | 항상 제거할 문구 추가 (기본: Confidential, 대외비, 사외비, Internal Use Only 등) |
| `--repeat-ratio 0.6` | 본문 한가운데의 글을 반복 문구로 볼 쪽 비율. 낮추면 더 많이 지움 |
| `--include-hidden` | PPTX의 숨긴 슬라이드도 포함 |
| `--no-images` | 리포트에 쪽 그림을 넣지 않음 (파일이 작아짐) |
| `--no-pdfplumber` | pdfplumber 비교 생략 |

## 리포트 보는 법

- **Before 열**: 아무 처리 없이 읽은 원문. 빨강 취소선은 제거된 문구, 초록은 제목으로 뽑힌 줄.
- **방식별 열**: 쪽 그림 위의 번호가 읽는 순서, 초록 상자가 제목. 아래에 제목, 본문, 제거한 문구와 이유.
- 위쪽 체크 상자로 열을 숨기거나 쪽 그림을 끌 수 있습니다.
- `*.json`에는 같은 결과가 자료로 들어 있습니다(쪽마다 `title`, `body`, `removed`).

## 알려진 한계

- **차트**: PDF에는 축 숫자와 값 레이블이 글자로 찍히지만 PPTX에서는 차트 제목·계열·항목만 읽습니다.
- **PDF의 줄바꿈**: PDF에는 문단 표시가 없어 자동 줄바꿈과 문단 끝을 좌표로 추정합니다.
  띄어쓰기 자리에서 줄이 넘어간 경우 띄어쓰기가 빠질 수 있습니다("계약을체결함").
  PDF를 만든 프로그램에 따라 정도가 다르므로 회사 자료로 꼭 확인하세요.
- **구형 .ppt, 스캔 PDF**는 지원하지 않습니다(.ppt는 .pptx로 저장 후 사용).
- 발표자 노트는 읽지 않습니다(PDF에 없는 내용).

## 라이선스 참고

PyMuPDF는 AGPL 또는 상용 라이선스입니다. 사내 도구로만 쓰는지, 배포하는지에 따라 확인이 필요합니다.
pdfplumber, python-pptx, Docling은 MIT 라이선스입니다.

## 구조

```
install.bat             설치 (가상 환경 + 라이브러리)
run.bat                 실행 (파일이나 폴더를 끌어다 놓으면 됨, 여러 개 가능)
download_wheels.bat     인터넷이 막힌 PC용 설치 파일 받기
compare.py              실행 프로그램
docparse/
  pdf_pymupdf.py        PDF 글자 읽기 (PyMuPDF)
  pdf_plumber.py        PDF 글자 읽기 (pdfplumber)
  pdf_common.py         글자 → 줄 → 블록, 표, 도형 상자
  pptx_reader.py        PPTX 읽기
  layout.py             읽는 순서(X-Y cut), 문단 합치기
  repeat.py             반복 문구 제거
  title.py              제목 추출
  pipeline.py           위 규칙을 순서대로 적용
  docling_method.py     Docling 단독(B), 결합(C)
  report.py             HTML 리포트
samples/                테스트용 샘플과 생성기
```
