@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 걸러내기 모델 비교

if not exist ".venv\Scripts\python.exe" goto :noinstall
set "PYTHONUTF8=1"

rem 파일이나 폴더를 끌어다 놓았으면 먼저 추출(run.bat 과 같은 일)을 한 뒤 걸러내기를 돌린다.
rem 그냥 실행하면 out 폴더에 이미 있는 추출 결과로 걸러내기만 돌린다.
set "SRCS="
set "COUNT=0"
set "ONE="
if "%~1"=="" goto :screen

:collect
if "%~1"=="" goto :extract
set "ONE=%~1"
if "%ONE:~-1%"=="\" set "ONE=%ONE:~0,-1%"
if not exist "%ONE%" goto :nosrc
set SRCS=%SRCS% "%ONE%"
set /a COUNT+=1
shift
goto :collect

:extract
echo.
echo [1단계] 문서 추출: %COUNT%개 (파일 또는 폴더)
echo.
".venv\Scripts\python.exe" compare.py %SRCS% -o out
if errorlevel 1 goto :runfail

:screen
echo.
echo [2단계] 걸러내기 모델 비교: out 폴더의 추출 결과 전체
echo         처음 계산하는 글은 시간이 걸립니다. 한 번 계산한 글은 다음부터 건너뜁니다.
echo.
".venv\Scripts\python.exe" screen.py out
if errorlevel 1 goto :runfail

echo.
echo 결과를 브라우저로 엽니다: out\screen\index.html
start "" "out\screen\index.html"
echo.
pause
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
