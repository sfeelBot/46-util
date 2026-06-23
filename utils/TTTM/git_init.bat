@echo off
cd /d %~dp0
echo Git 저장소 초기화 중...
git init
git add .gitignore
git add requirements.txt
git add *.py *.md
git add *.bat
git add tests\
echo.
git status
echo.
git commit -m "initial commit: 16-bit RAW image comparison app v1.0"
echo.
echo Git 초기화 완료.
pause
