@echo off
cd /d %~dp0
echo 이미지 비교 분석 프로그램 실행 중...
py main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo 오류가 발생했습니다. app.log 파일을 확인하세요.
    pause
)
