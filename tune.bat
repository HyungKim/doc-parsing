@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 읽는 순서 기준값 시험

if not exist ".venv\Scripts\python.exe" goto :noinstall

rem 끌어다 놓은 파일과 폴더를 모두 모은다. 여러 개를 한꺼번에 놓아도 된다.
set "SRCS="
set "COUNT=0"
set "ONE="
if "%~1"=="" goto :ask

:collect
if "%~1"=="" goto :run
set "ONE=%~1"
if "%ONE:~-1%"=="\" set "ONE=%ONE:~0,-1%"
if not exist "%ONE%" goto :nosrc
set SRCS=%SRCS% "%ONE%"
set /a COUNT+=1
shift
goto :collect

:ask
echo 기준값을 시험할 PDF, PPTX 파일이나 폴더의 경로를 입력하세요.
echo 파일이나 폴더를 이 창으로 끌어다 놓아도 됩니다.
set /p "ONE=경로: "
if not defined ONE goto :noinput
set "ONE=%ONE:"=%"
if "%ONE:~-1%"=="\" set "ONE=%ONE:~0,-1%"
if not exist "%ONE%" goto :nosrc
set SRCS="%ONE%"
set "COUNT=1"

:run
set "PYTHONUTF8=1"

echo.
echo 시험할 자료: %COUNT%개 (파일 또는 폴더)
echo.
".venv\Scripts\python.exe" tune.py %SRCS% -o out
if errorlevel 1 goto :runfail

echo.
echo 결과를 브라우저로 엽니다: out\tune.html
start "" "out\tune.html"
echo.
pause
exit /b 0

:noinstall
echo [오류] 아직 설치되지 않았습니다. install.bat 을 먼저 실행해 주세요.
echo.
pause
exit /b 1

:noinput
echo [오류] 경로를 입력하지 않았습니다.
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
