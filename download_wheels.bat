@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 설치 파일 내려받기

echo ============================================================
echo   인터넷이 막힌 PC에 옮겨 갈 설치 파일을 내려받습니다.
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

echo [1/2] 기본 라이브러리를 내려받습니다...
%PY% -m pip download -r requirements.txt -d wheels
if errorlevel 1 goto :fail

echo.
echo [2/2] Docling 설치 파일 내려받기 여부를 선택합니다. 용량이 1~2GB입니다.
set "ANS=N"
set /p "ANS=      Docling 설치 파일도 받을까요? [y/N] "
if /i not "%ANS%"=="y" goto :done
%PY% -m pip download -r requirements-docling.txt -d wheels
if errorlevel 1 goto :fail

:done
echo.
echo ============================================================
echo   wheels 폴더가 준비되었습니다.
echo   프로그램 폴더 전체를 wheels 폴더와 함께 회사 PC로 옮긴 뒤
echo   install.bat 을 실행하세요.
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
