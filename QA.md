# QA.md

util별 버그/이슈를 모아보는 인덱스 문서. 상세 기록은 해당 util 폴더의 `QA.md`에 있다. [CLAUDE.md](CLAUDE.md) 참고.

---

## util별 QA 문서

| util | QA 문서 | 비고 |
| --- | --- | --- |
| crop_locator | [utils/crop_locator/QA.md](utils/crop_locator/QA.md) | 아직 기록된 이슈 없음 (서브에이전트 검증 통과, 2026-06-19) |
| TTTM (RAW_Image_Comparator) | [utils/TTTM/QA.md](utils/TTTM/QA.md) | 알려진 제한사항 있음 (2026-06-06, 이전 작업 환경에서 이관) |
| raw_flipper | [utils/raw_flipper/QA.md](utils/raw_flipper/QA.md) | 아직 기록된 이슈 없음 (서브에이전트 검증 통과, 2026-07-06) |
| image_cropper | [utils/image_cropper/QA.md](utils/image_cropper/QA.md) | 아직 기록된 이슈 없음 (초기 작성 2026-07-06) |
| signal_noise_analyzer | [utils/signal_noise_analyzer/QA.md](utils/signal_noise_analyzer/QA.md) | 아직 기록된 이슈 없음 (초기 작성 2026-07-06) |
| github_sync_gui | [utils/github_sync_gui/QA.md](utils/github_sync_gui/QA.md) | PowerShell 스크립트 BOM 인코딩 버그, LastRunTime 특수 날짜 버그 발견 후 수정 완료 (2026-07-09) |

---

새 util을 추가하거나 그 util에서 버그를 발견하면:
1. 해당 util 폴더의 `QA.md`에 상세 기록을 남긴다.
2. 위 표에 한 줄 비고를 추가/갱신한다.
