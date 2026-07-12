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
| y_axis_masker | [utils/y_axis_masker/QA.md](utils/y_axis_masker/QA.md) | 아직 기록된 이슈 없음 (초기 작성 2026-07-09, 하위폴더/누적로드/삭제 기능 서브에이전트 검증 통과) |
| github_sync_gui | [utils/github_sync_gui/QA.md](utils/github_sync_gui/QA.md) | robocopy ExitCode=16(공백 경로 인용 오류)·로그 인코딩 깨짐·GUI 블로킹(비동기화)·robocopy `/MIR`의 로컬 파일 삭제 등 수정 완료. 로그 삭제/시작프로그램 등록/exe 아이콘 실제 빌드로 검증 완료 (2026-07-09) |
| filename_matching | [utils/filename_matching/QA.md](utils/filename_matching/QA.md) | Windows 콘솔 한글 mojibake 수정, GitHub 이슈 #2(파일명 규칙 변경) 대응해 저장번호 매칭 단계 추가 + `barcode_cell_map.csv` 110→247행 확장, 매칭실패 파일 error 폴더 자동 복사, "Crop 이미지 재명명" 탭 추가(2탭 구조로 리팩터링). 서브에이전트 검증 5회 통과, 발견된 버그는 모두 배포 전 자체 발견·수정 (2026-07-12) |

---

새 util을 추가하거나 그 util에서 버그를 발견하면:
1. 해당 util 폴더의 `QA.md`에 상세 기록을 남긴다.
2. 위 표에 한 줄 비고를 추가/갱신한다.
