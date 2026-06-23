# processing.md

`utils/` 폴더에 어떤 util(프로그램)들이 있는지 한눈에 보여주는 인덱스 문서. 각 util의 상세 내용(알고리즘/사용법/버전/제약)은 해당 util 폴더의 `processing.md`에 있다. 새 작업을 시작하기 전에 이 문서로 전체 목록을 먼저 확인한 뒤, 관련 util의 상세 문서를 읽는다. [CLAUDE.md](CLAUDE.md) 참고.

---

## util 목록

| util | 설명 | 상세 문서 |
| --- | --- | --- |
| crop_locator | 원본 이미지(bmp/png) 안에서 crop된 이미지(들)의 위치(x, y, w, h)를 template matching + NMS + pixel-by-pixel 검증으로 찾는 PyQt5 GUI 도구 | [utils/crop_locator/processing.md](utils/crop_locator/processing.md) |
| TTTM (RAW_Image_Comparator) | 16-bit 단채널 RAW 이미지 2장을 Threshold/ROI/Blob 분석으로 비교하는 PyQt5 데스크탑 GUI (다른 작업 환경에서 이관됨) | [utils/TTTM/processing.md](utils/TTTM/processing.md) |

---

새 util을 추가하거나 기존 util을 변경하면:
1. 해당 util 폴더의 `processing.md`(상세)를 작성/갱신한다.
2. 위 표에 한 줄 요약 + 링크를 추가/갱신한다.
