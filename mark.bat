@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 최종 모델로 검토 필요 표시하기 (이 창을 닫으면 끝납니다)

if not exist ".venv\Scripts\python.exe" goto :noinstall
set "PYTHONUTF8=1"
rem Ollama를 이 프로그램이 켜게 될 때 로컬 전용으로 켜지게 한다. 이미 켜져 있는 Ollama에는 영향을 주지 않는다.
set "OLLAMA_NO_CLOUD=1"

rem PDF, PPTX 파일을 끌어다 놓았으면 그 파일들을 올려 둔 채로 화면을 연다.
rem 그냥 실행하면 화면에서 파일을 고르거나 끌어다 놓는다.
set "SRCS="
set "ONE="

:collect
if "%~1"=="" goto :run
set "ONE=%~1"
if not exist "%ONE%" goto :nosrc
set SRCS=%SRCS% "%ONE%"
shift
goto :collect

:run
echo 표시하기 화면을 브라우저로 엽니다. 이 PC 안에서만 열리는 화면입니다.
echo 최종 모델로 PDF, PPTX 에서 검토가 필요하다고 본 글을 표시합니다.
echo   분류기 multilingual-e5-small, 덩어리 단위 - 그다음 LLM qwen3:8b, 프롬프트 안 C, 생각 모드 끔
echo 표시한 사본 두 개와 단계마다 걸린 시간이 나옵니다. 자료는 이 PC 밖으로 나가지 않습니다.
echo 정답과 학습 결과는 읽기만 하고 바꾸지 않습니다. 결과는 out\mark 폴더에 쌓입니다.
echo 다 썼으면 이 창을 닫으세요.
echo.
".venv\Scripts\python.exe" mark.py %SRCS%
if errorlevel 1 goto :runfail
exit /b 0

:noinstall
echo [오류] 아직 설치되지 않았습니다. install.bat 과 install_screen.bat 을 먼저 실행해 주세요.
echo.
pause
exit /b 1

:nosrc
echo [오류] 찾지 못한 경로입니다: "%ONE%"
echo.
pause
exit /b 1

:runfail
echo.
echo [오류] 실행 중 문제가 생겼습니다. 위의 오류 내용을 확인해 주세요.
echo.
pause
exit /b 1
