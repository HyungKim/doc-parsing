@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 설치

echo ============================================================
echo   PDF / PPTX 텍스트 추출 프로그램 설치
echo ============================================================
echo.

set "PY="
call :try "py -3"
if not defined PY call :try "python"
if not defined PY goto :nopython

echo 사용할 Python:
%PY% --version
echo.

echo [1/2] 프로그램 전용 가상 환경을 준비합니다...
if exist ".venv\Scripts\python.exe" goto :venvok
%PY% -m venv .venv
if errorlevel 1 goto :fail
:venvok
set "VPY=.venv\Scripts\python.exe"

set "PIPOPT="
if exist "wheels\" set "PIPOPT=--no-index --find-links wheels"
if defined PIPOPT echo       wheels 폴더가 있어 인터넷 없이 설치합니다.

echo.
echo [2/2] 라이브러리를 설치합니다. pdfplumber, python-pptx
"%VPY%" -m pip install %PIPOPT% -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo   설치가 끝났습니다.
echo   run.bat 을 더블클릭하거나, 자료를 run.bat 위로 끌어다 놓으세요.
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo [오류] 설치에 실패했습니다. 위의 오류 내용을 확인해 주세요.
echo        인터넷이 막힌 PC라면 인터넷이 되는 PC에서 download_wheels.bat 을 실행해
echo        만들어진 wheels 폴더를 이 폴더에 넣은 뒤 다시 실행하면 됩니다.
echo        사내 전용 패키지 저장소가 있다면 PIP_INDEX_URL 환경 변수에 주소를 넣어 주세요.
echo.
pause
exit /b 1

:try
%~1 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%~1"
exit /b 0

:nopython
echo.
echo [오류] Python 3.9 이상을 찾지 못했습니다.
echo        Python을 설치한 뒤 다시 실행해 주세요.
echo        설치할 때 "Add python.exe to PATH" 항목을 체크해야 합니다.
echo.
pause
exit /b 1
