# PDF/PPTX 텍스트 추출 (좌표 규칙 방식)

PDF와 PPTX에서 글을 사람이 읽는 순서대로 뽑고, 매 쪽 반복되는 문구를 빼고, 쪽 제목을 따로 뽑습니다.
처리 전(before)과 처리 후(after)를 나란히 보여 주는 HTML 리포트를 만듭니다.

- 글자의 좌표와 크기만으로 판단합니다(재귀 X-Y cut). AI 모델을 쓰지 않습니다.
- PDF는 PyMuPDF와 pdfplumber 두 가지로 읽어 결과를 나란히 보여 줍니다.
- 실행 중 인터넷에 접속하지 않습니다.

## 버전

| 버전 | 내용 | 받는 곳 |
|---|---|---|
| **2.0** (이 버전) | 좌표 규칙 방식만. Docling 없음 | `main` 브랜치, `v2.0` 태그 |
| 1.0-docling | 좌표 규칙(A), Docling(B), 결합(C) 세 방식 비교 | `with-docling` 브랜치, `v1.0-docling` 태그 |

두 버전은 서로 다른 폴더에 두고 따로 쓸 수 있습니다. 폴더마다 `install.bat`을 한 번씩 실행해야 합니다.

## 설치와 실행 (Windows, 배치파일)

1. 이 폴더를 통째로 PC에 둡니다.
2. `install.bat`을 더블클릭합니다. 이 폴더 안에 전용 가상 환경(`.venv`)을 만들고 라이브러리 세 개(PyMuPDF, pdfplumber, python-pptx)를 설치합니다.
3. `run.bat`을 더블클릭해 경로를 입력하거나, 자료를 `run.bat` 위로 끌어다 놓습니다. 폴더 하나, 파일 하나, 파일이나 폴더 여러 개 모두 됩니다. 수십 개가 넘으면 한 폴더에 모아 폴더를 놓으세요(한 번에 넘길 수 있는 경로 길이에 한도가 있습니다).
   끝나면 `out\index.html`이 브라우저로 열립니다.

Python 3.9 이상이 필요합니다. Python이 없으면 먼저 설치하되, 설치 화면에서 "Add python.exe to PATH"를 체크하세요.

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
python compare.py 자료폴더 -o out
```

- 폴더 안의 `.pdf`, `.pptx`를 모두 처리하고 `out\index.html`을 만듭니다.
- 이름이 같은 PPTX와 PDF(예: `보고.pptx`, `보고.pdf`)를 함께 넣으면 두 결과가 얼마나 같은지 비교하는
  `보고.pptx-vs-pdf.html`도 만듭니다.
- `samples` 폴더의 샘플로 먼저 시험해 볼 수 있습니다: `run.bat samples`

### 옵션

| 옵션 | 뜻 |
|---|---|
| `--keywords "사내한,Draft"` | 항상 제거할 문구 추가 (기본: Confidential, 대외비, 사외비, Internal Use Only 등) |
| `--repeat-ratio 0.6` | 본문 한가운데의 글을 반복 문구로 볼 쪽 비율. 낮추면 더 많이 지움 |
| `--include-hidden` | PPTX의 숨긴 슬라이드도 포함 |
| `--no-images` | 리포트에 쪽 그림을 넣지 않음 (파일이 작아짐) |
| `--no-pdfplumber` | pdfplumber 비교 생략 |

## 리포트 보는 법

- **Before 열**: 아무 처리 없이 읽은 원문. 번호 하나가 라이브러리가 따로 꺼낸 단위(PyMuPDF는 덩어리, pdfplumber는 줄, PPTX는 도형)이고, 쪽 그림의 회색 상자가 그 위치입니다. 빨강 취소선은 제거된 문구, 초록은 제목으로 뽑힌 줄.
- **A 열**: 좌표 규칙을 적용한 결과. 쪽 그림 위의 번호가 읽는 순서, 초록 상자가 제목. 아래에 제목, 본문, 제거한 문구와 이유.
  PDF는 `A-mu`(PyMuPDF로 읽음)와 `A-pl`(pdfplumber로 읽음) 두 열이 나옵니다. 적용하는 규칙은 같습니다.
- **일치율**: 쪽의 글을 한 줄로 이어 붙여 글자와 순서가 얼마나 같은지 본 값입니다. 띄어쓰기, 줄바꿈, 덩어리를 끊은 위치는 세지 않습니다.
- 위쪽 체크 상자로 열을 숨기거나 쪽 그림을 끌 수 있습니다.
- `*.json`에는 같은 결과가 자료로 들어 있습니다(쪽마다 `title`, `body`, `removed`).

## 읽는 순서 기준값 시험

읽는 순서를 정할 때 쓰는 기준값(예: 좌우로 자르려면 여백이 6pt 이상)은 샘플로 정한 값입니다.
실제 자료에서도 안전한지 확인하려면 자료를 `tune.bat` 위로 끌어다 놓습니다(직접 실행: `python tune.py 자료폴더`).

- 기준값을 하나씩 바꿔 가며 순서를 다시 정하고, 지금 값일 때와 순서가 달라지는 쪽을 세어 `out\tune.html`로 보여 줍니다.
- 바로 옆 값으로 바꿔도 순서가 같으면 지금 값이 그 자료에서 안전한 것입니다.
- 달라지는 쪽이 있으면 지금 순서와 바꾼 순서를 나란히 보여 주므로 어느 쪽이 맞는지 확인할 수 있습니다.
- 먼저 `run.bat`으로 같은 자료를 돌려 두면, 쪽 이름을 눌러 비교 리포트의 그 쪽으로 갈 수 있습니다.
- 기준값 자체는 `docparse/layout.py` 맨 위에 있습니다. 이 시험은 값을 바꿔 저장하지 않습니다.

## 알려진 한계

- **차트**: PDF에는 축 숫자와 값 레이블이 글자로 찍히지만 PPTX에서는 차트 제목·계열·항목만 읽습니다.
- **PDF의 줄바꿈**: PDF에는 문단 표시가 없어 자동 줄바꿈과 문단 끝을 좌표로 추정합니다.
  띄어쓰기 자리에서 줄이 넘어간 경우 띄어쓰기가 빠질 수 있습니다("계약을체결함").
  PDF를 만든 프로그램에 따라 정도가 다르므로 회사 자료로 꼭 확인하세요.
- **표**: 칸을 ` | `로 이어 한 행을 한 줄로 적습니다. 빈 칸은 건너뛰므로 빈 칸이 있는 행과 여러 단으로 된 머리글에서는 어느 열의 값인지 알 수 없습니다.
- **두 라이브러리의 차이**: 글자 상자 높이를 다르게 알려 주어, 줄 간격이 넓은 글에서 PyMuPDF는 한 덩어리로 묶고 pdfplumber는 줄마다 나눌 수 있습니다. pdfplumber는 쪽 바깥에 놓인 글도 읽습니다.
- **구형 .ppt, 스캔 PDF**는 지원하지 않습니다(.ppt는 .pptx로 저장 후 사용).
- 발표자 노트는 읽지 않습니다(PDF에 없는 내용).

## 라이선스 참고

PyMuPDF는 AGPL 또는 상용 라이선스입니다. 사내 도구로만 쓰는지, 배포하는지에 따라 확인이 필요합니다.
pdfplumber와 python-pptx는 MIT 라이선스입니다.

## 구조

```
install.bat             설치 (가상 환경 + 라이브러리)
run.bat                 실행 (파일이나 폴더를 끌어다 놓으면 됨, 여러 개 가능)
tune.bat                읽는 순서 기준값 시험 (파일이나 폴더를 끌어다 놓으면 됨)
download_wheels.bat     인터넷이 막힌 PC용 설치 파일 받기
compare.py              실행 프로그램
tune.py                 읽는 순서 기준값 시험
docparse/
  pdf_pymupdf.py        PDF 글자 읽기 (PyMuPDF)
  pdf_plumber.py        PDF 글자 읽기 (pdfplumber)
  pdf_common.py         글자 → 줄 → 블록, 표, 도형 상자
  pptx_reader.py        PPTX 읽기
  layout.py             읽는 순서(X-Y cut), 문단 합치기
  repeat.py             반복 문구 제거
  title.py              제목 추출
  pipeline.py           위 규칙을 순서대로 적용
  report.py             HTML 리포트
samples/                테스트용 샘플과 생성기
```
