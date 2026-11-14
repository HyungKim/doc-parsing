@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 정답 붙이기 (이 창을 닫으면 끝납니다)

if not exist ".venv\Scripts\python.exe" goto :noinstall
set "PYTHONUTF8=1"

echo 정답 붙이는 화면을 브라우저로 엽니다. 이 PC 안에서만 열리는 화면입니다.
echo 다 붙였으면 이 창을 닫으세요. 정답은 누를 때마다 저장됩니다.
echo.
".venv\Scripts\python.exe" label.py out
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
