@echo off
cd /d %~dp0
echo ============================================
echo  환경 확인 및 테스트 이미지 생성
echo ============================================
echo.

echo [1] Python 버전 확인
py --version
if %ERRORLEVEL% NEQ 0 (
    echo Python Launcher(py)가 설치되어 있지 않습니다.
    pause & exit /b 1
)

echo.
echo [2] 필요 패키지 확인
py -c "import cv2, PyQt5, numpy; print('OK')"
if %ERRORLEVEL% NEQ 0 (
    echo 패키지가 설치되어 있지 않습니다. 설치 중...
    py -m pip install -r requirements.txt
)

echo.
echo [3] 테스트 이미지 생성
py tests\create_test_images.py
if %ERRORLEVEL% NEQ 0 (
    echo 테스트 이미지 생성 실패!
    pause & exit /b 1
)

echo.
echo [4] 생성된 RAW 파일 확인
dir *.raw

echo.
echo [5] 모듈 임포트 테스트
py -c "from logger_setup import setup_logger; from image_processor import read_raw, find_blobs; from viewer_widget import ViewerWidget; from image_panel import ImagePanel; print('module import OK')"
if %ERRORLEVEL% NEQ 0 (
    echo 모듈 임포트 실패! 코드를 확인하세요.
    pause & exit /b 1
)

echo.
echo ============================================
echo  모든 확인 완료. run.bat으로 앱을 실행하세요.
echo ============================================
pause
