@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 걸러내기 모델 설치

echo ============================================================
echo   2단계(걸러내기 모델 비교)에 필요한 것을 설치합니다.
echo   라이브러리 약 1.5GB, 모델 파일 약 6GB를 이 폴더 안에 받습니다.
echo   이 폴더가 있는 드라이브에 8GB 이상 여유가 있어야 합니다.
echo   받는 데 시간이 걸립니다. 창을 닫지 말고 기다려 주세요.
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" goto :noinstall
set "VPY=.venv\Scripts\python.exe"
set "PYTHONUTF8=1"

rem 설치 중에 쓰는 임시 파일도 이 폴더 안에 둔다. C: 드라이브에 쌓이지 않게 한다.
if not exist ".tmp\" mkdir ".tmp"
set "TEMP=%~dp0.tmp"
set "TMP=%~dp0.tmp"

set "PIPOPT=--no-cache-dir"
if exist "wheels\torch*.whl" set "PIPOPT=--no-index --find-links wheels"
if exist "wheels\torch*.whl" echo       wheels 폴더가 있어 인터넷 없이 설치합니다.

echo [1/2] 라이브러리를 설치합니다. torch, transformers, sentence-transformers, scikit-learn
"%VPY%" -m pip install %PIPOPT% -r requirements-screen.txt
if errorlevel 1 goto :fail

echo.
echo [2/2] 모델 파일을 받습니다. models 폴더에 이미 있는 모델은 건너뜁니다.
"%VPY%" screen.py --download
if errorlevel 1 goto :modelfail

rmdir /s /q ".tmp" >nul 2>nul
echo.
echo ============================================================
echo   설치가 끝났습니다.
echo   screen.bat 을 실행하면 네 모델로 점수를 매기고 비교 화면을 엽니다.
echo   label.bat 을 실행하면 정답을 붙이는 화면이 열립니다.
echo ============================================================
echo.
pause
exit /b 0

:noinstall
echo [오류] 아직 설치되지 않았습니다. install.bat 을 먼저 실행해 주세요.
echo.
pause
exit /b 1

:fail
rmdir /s /q ".tmp" >nul 2>nul
echo.
echo [오류] 라이브러리 설치에 실패했습니다. 위의 오류 내용을 확인해 주세요.
echo        인터넷이 막힌 PC라면 인터넷이 되는 PC에서 download_screen.bat 을 실행해
echo        만들어진 wheels 폴더와 models 폴더를 이 폴더에 넣은 뒤 다시 실행하면 됩니다.
echo.
pause
exit /b 1

:modelfail
rmdir /s /q ".tmp" >nul 2>nul
echo.
echo [오류] 모델 파일을 모두 받지 못했습니다. 위의 오류 내용을 확인해 주세요.
echo        라이브러리는 설치되었습니다. 다시 실행하면 못 받은 모델만 이어서 받습니다.
echo        모델을 받는 곳(huggingface.co)이 막힌 PC라면 인터넷이 되는 PC에서
echo        download_screen.bat 을 실행해 만들어진 models 폴더를 이 폴더에 넣으면 됩니다.
echo.
pause
exit /b 1
