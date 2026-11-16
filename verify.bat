@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - LLM으로 한 번 더 검증하기 (이 창을 닫으면 끝납니다)

if not exist ".venv\Scripts\python.exe" goto :noinstall
set "PYTHONUTF8=1"
rem Ollama를 이 프로그램이 켜게 될 때 로컬 전용으로 켜지게 한다. 이미 켜져 있는 Ollama에는 영향을 주지 않는다.
set "OLLAMA_NO_CLOUD=1"

echo 검증하기 화면을 브라우저로 엽니다. 이 PC 안에서만 열리는 화면입니다.
echo 분류기가 검토가 필요하다고 본 글을 이 PC 안의 LLM, Ollama 에 다시 물어 봅니다.
echo 자료는 이 PC 밖으로 나가지 않습니다. 정답과 학습 결과는 읽기만 하고 바꾸지 않습니다.
echo 결과는 out\verify 폴더에 쌓입니다. 다 썼으면 이 창을 닫으세요.
echo.
".venv\Scripts\python.exe" verify.py %*
if errorlevel 1 goto :runfail
exit /b 0

:noinstall
echo [오류] 아직 설치되지 않았습니다. install.bat 과 install_screen.bat 을 먼저 실행해 주세요.
echo.
pause
exit /b 1

:runfail
echo.
echo [오류] 실행 중 문제가 생겼습니다. 위의 오류 내용을 확인해 주세요.
echo.
pause
exit /b 1
