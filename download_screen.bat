@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 걸러내기 설치 파일과 모델 내려받기

echo ============================================================
echo   인터넷이 막힌 PC에 옮겨 갈 것을 내려받습니다. 약 8GB.
echo     wheels 폴더  설치 파일 (1단계와 2단계 모두)
echo     models 폴더  모델 파일 네 가지
echo   이 파일은 인터넷이 되는 Windows PC에서 실행하세요.
echo   회사 PC와 Python 버전이 같아야 합니다. 예: 둘 다 3.11
echo ============================================================
echo.

set "PY="
call :try "py -3"
if not defined PY call :try "python"
if not defined PY goto :nopython

echo 사용할 Python:
%PY% --version
echo.
set "PYTHONUTF8=1"

echo [1/3] 설치 파일을 내려받습니다.
%PY% -m pip download -r requirements.txt -r requirements-screen.txt -d wheels
if errorlevel 1 goto :fail

echo.
echo [2/3] 모델을 받는 데 쓸 실행 환경을 준비합니다.
if exist ".venv\Scripts\python.exe" goto :venvok
%PY% -m venv .venv
if errorlevel 1 goto :fail
:venvok
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt -r requirements-screen.txt
if errorlevel 1 goto :fail

echo.
echo [3/3] 모델 파일을 받습니다.
".venv\Scripts\python.exe" screen.py --download
if errorlevel 1 goto :fail

echo.
echo ============================================================
echo   준비되었습니다.
echo   wheels 폴더와 models 폴더를 회사 PC의 프로그램 폴더에 넣은 뒤
echo   install.bat, install_screen.bat 을 차례로 실행하세요.
echo ============================================================
echo.
pause
exit /b 0

:fail
echo.
echo [오류] 내려받기에 실패했습니다. 위의 오류 내용을 확인해 주세요.
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
