@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 실행

if not exist ".venv\Scripts\python.exe" goto :noinstall

set "SRC=%~1"
if defined SRC goto :havesrc
echo 비교할 PDF, PPTX 파일이 들어 있는 폴더 경로를 입력하세요.
echo 폴더를 이 창으로 끌어다 놓아도 됩니다.
set /p "SRC=폴더 경로: "
if not defined SRC goto :nosrc
:havesrc
set "SRC=%SRC:"=%"
if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"
if not exist "%SRC%" goto :nosrc

set "PYTHONUTF8=1"
set "MODELS="
if exist "docling_models\" set "MODELS=--docling-models docling_models"
if exist "docling_models\" set "HF_HUB_OFFLINE=1"

echo.
echo 처리할 자료: %SRC%
echo.
".venv\Scripts\python.exe" compare.py "%SRC%" -o out %MODELS%
if errorlevel 1 goto :runfail

echo.
echo 결과를 브라우저로 엽니다: out\index.html
start "" "out\index.html"
echo.
pause
exit /b 0

:noinstall
echo [오류] 아직 설치되지 않았습니다. install.bat 을 먼저 실행해 주세요.
echo.
pause
exit /b 1

:nosrc
echo [오류] 폴더를 찾지 못했습니다. 경로를 확인해 주세요.
echo.
pause
exit /b 1

:runfail
echo.
echo [오류] 실행 중 문제가 생겼습니다. 위의 오류 내용을 확인해 주세요.
echo.
pause
exit /b 1
