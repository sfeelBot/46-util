# 46 util

이미지 처리용 유틸리티 모음 저장소. 새 util을 추가하거나 기존 util을 수정할 때는 [CLAUDE.md](CLAUDE.md)의 워크플로우를 따른다.

## 문서 안내

| 파일 | 용도 |
| --- | --- |
| [CLAUDE.md](CLAUDE.md) | 작업 워크플로우 규칙 (구현 전 확인 → 구현 → 검증 → push 확인) |
| [processing.md](processing.md) | util 전체 인덱스 (각 util이 어떤 프로그램인지 한눈에 보기) |
| [QA.md](QA.md) | util별 버그/이슈 인덱스 |

각 util의 상세 내용(알고리즘/사용법/버전/제약)과 버그 기록은 `utils/<util_name>/processing.md`, `utils/<util_name>/QA.md`에 있다.

## 환경 설정

Python 3.12 기준, 저장소 루트에 `.venv` 가상환경을 사용한다.

```bash
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## util 목록

자세한 설명은 [processing.md](processing.md) 참고.

### crop_locator

원본 이미지(bmp/png) 안에서 crop된 이미지(들)의 위치(x, y, w, h)를 찾는 PyQt5 GUI 도구.
Template matching → NMS로 상위 후보 추출 → score 높은 순으로 pixel-by-pixel 완전 일치 검사 방식으로 동작한다.
자세한 내용은 [utils/crop_locator/processing.md](utils/crop_locator/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\crop_locator\gui.py
```

### TTTM (RAW_Image_Comparator)

16-bit 단채널 RAW 이미지 2장을 Threshold/ROI/Blob 분석으로 비교하는 PyQt5 데스크탑 GUI (다른 작업 환경에서 이관됨).
자세한 내용은 [utils/TTTM/processing.md](utils/TTTM/processing.md) 참고.

```bash
.venv\Scripts\python.exe utils\TTTM\main.py
```
