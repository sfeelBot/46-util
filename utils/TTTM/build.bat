@echo off
cd /d %~dp0

echo [1] PyInstaller로 빌드 시작...

py -m PyInstaller ^
  --name "RAW_Image_Comparator" ^
  --onefile ^
  --windowed ^
  --add-data "logger_setup.py;." ^
  --add-data "image_processor.py;." ^
  --add-data "image_panel.py;." ^
  --add-data "viewer_widget.py;." ^
  --add-data "overlay_dialog.py;." ^
  --hidden-import PyQt5.sip ^
  --hidden-import cv2 ^
  --hidden-import numpy ^
  main.py

echo.
if exist dist\RAW_Image_Comparator.exe (
    echo [OK] 빌드 성공: dist\RAW_Image_Comparator.exe
) else (
    echo [FAIL] 빌드 실패 - 위 로그 확인
)
pause
