@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title PDF-PPTX 추출 비교 - 학습 기록 보기

if not exist "out\screen\history.html" goto :none
start "" "out\screen\history.html"
exit /b 0

:none
echo 아직 학습 기록이 없습니다.
echo screen.bat 을 실행하거나 label.bat 화면에서 "학습하고 결과 보기"를 누르면 기록이 쌓입니다.
echo.
pause
exit /b 1
