# processing.md

`utils/` 폴더에 어떤 util(프로그램)들이 있는지 한눈에 보여주는 인덱스 문서. 각 util의 상세 내용(알고리즘/사용법/버전/제약)은 해당 util 폴더의 `processing.md`에 있다. 새 작업을 시작하기 전에 이 문서로 전체 목록을 먼저 확인한 뒤, 관련 util의 상세 문서를 읽는다. [CLAUDE.md](CLAUDE.md) 참고.

---

## util 목록

| util | 설명 | 상세 문서 |
| --- | --- | --- |
| crop_locator | 원본 이미지(bmp/png) 안에서 crop된 이미지(들)의 위치(x, y, w, h)를 template matching + NMS + pixel-by-pixel 검증으로 찾는 PyQt5 GUI 도구 | [utils/crop_locator/processing.md](utils/crop_locator/processing.md) |
| TTTM (RAW_Image_Comparator) | 16-bit 단채널 RAW 이미지 2장을 Threshold/ROI/Blob 분석으로 비교하는 PyQt5 데스크탑 GUI (다른 작업 환경에서 이관됨) | [utils/TTTM/processing.md](utils/TTTM/processing.md) |
| raw_flipper | 폴더 내 이미지 파일(RAW/PNG/BMP 등)을 재귀 탐색하여 일괄 상하반전 후 동일한 폴더 구조로 결과 폴더에 저장하는 PyQt5 GUI 도구 | [utils/raw_flipper/processing.md](utils/raw_flipper/processing.md) |
| image_cropper | 폴더 내 이미지(JPG/PNG/BMP/TIFF/RAW 16-bit)에서 복수 ROI를 드래그/숫자입력/레퍼런스 이미지 파일명(XYWH) 로드로 지정해 크롭 저장하는 PyQt5 도구. ROI 개별 선택·재지정·삭제, 하위 폴더 포함 스캔(cropped 폴더 자동 제외)·확장자 체크박스 선택 후 목록 불러오기·목록 초기화·파일명/폴더 정렬 가능한 목록 지원. PyInstaller exe 빌드 스크립트 포함 | [utils/image_cropper/processing.md](utils/image_cropper/processing.md) |
| signal_noise_analyzer | 이미지 ROI를 이진화(threshold)하여 Signal / Noise1(σ_bg) / Noise2(bg_mean−bg_min)를 실시간 측정·저장하는 PyQt5 GUI 도구. 라인 프로파일, 폴더 탭, 결과 트리 제공 | [utils/signal_noise_analyzer/processing.md](utils/signal_noise_analyzer/processing.md) |
| y_axis_masker | 지정한 y좌표 아래 영역을 검정/흰색/가우시안 블러/선택영역 평균값/스포이드 색상으로 마스킹하는 PyQt5 GUI 도구. Before/After 줌 뷰어, 하위 폴더 포함 스캔·다중 폴더 누적, 폴더 일괄·체크 적용, 목록 삭제(원본 보존), 파일명 검색 지원 | [utils/y_axis_masker/processing.md](utils/y_axis_masker/processing.md) |
| github_sync_gui | 사내망 PC에서 GitHub 저장소를 zip 다운로드 방식으로 동기화하는 [tools/github_sync](tools/github_sync/README.md) 스크립트를 제어하는 PyQt5 GUI. 탭으로 여러 저장소를 각자 다른 폴더에 등록해 관리, 수동 동기화(실행 중 강제 취소 가능)/전체 동기화, 상태/로그 확인(삭제 가능), 경로 설정 제공. 시스템 트레이 상주, Windows 시작 시 자동 실행. exe 이름: `github-sync-feel.exe` | [utils/github_sync_gui/processing.md](utils/github_sync_gui/processing.md) |
| filename_matching | 이물검사 이미지 파일명 재가공 PyQt5 GUI (2탭 + 완전 독립 GUI 1개). 탭1: (바코드 또는 저장번호)→셀번호→재료명 변환, 매칭실패 파일은 error 폴더에 자동 백업. 탭2: image_cropper로 4등분한 crop 이미지를 원래 개별 저장번호 파일명으로 재명명(오름차순/내림차순 번호 매기기 옵션 제공). `gui_folder_remap.py`(gui.py/core.py 비의존 독립 실행): 파일명의 저장번호를 매핑표(`storage_ab_defect_info.csv`)와 직접 매칭해 `{이물정보}_{셀번호}_{원본파일명}`으로 재명명, 셀번호 미상(NULL) 행도 이물정보만으로 변환. 폴더 재귀 스캔·확장자 필터·최종명 미리보기·중복검사·우클릭 탐색기 열기·자유 리사이즈/셀 복사 테이블·비동기 일괄 변환(원본 보존, 복사만)·되돌리기(로그 기반) 공용 제공. 매핑표는 외부 CSV로 분리 | [utils/filename_matching/processing.md](utils/filename_matching/processing.md) |
| bmp_folder_counter | GUI 없는 단일 스크립트. 상위폴더 > 1단계 하위폴더(이름순 첫번째만) > 2단계 하위폴더 구조에서, 2단계 하위폴더별 bmp 파일 개수(재귀 포함, 대소문자 무시)를 집계해 csv/md 표로 저장 | [utils/bmp_folder_counter/processing.md](utils/bmp_folder_counter/processing.md) |
| bmp_rename_by_folder | GUI 없는 단일 스크립트. 상위폴더 안의 `Test#A5-0000013` 형식 하위폴더 전체를 대상으로, 각 하위폴더 안 bmp 파일명의 폴더명과 같은 형식 부분(prefix+숫자)을 실제 폴더명으로 일괄 치환(rename). 패턴 불일치/충돌 파일은 하위폴더별 error 폴더로 이동 + rename_log.csv 기록 | [utils/bmp_rename_by_folder/processing.md](utils/bmp_rename_by_folder/processing.md) |
| bmp_misplaced_sorter | GUI 없는 단일 스크립트. GitHub 이슈 #6 매칭표(동봉 storage_number_map.csv)를 기준으로 `Test#A[1-8]-0000NNN` 폴더에 잘못 들어간 bmp 파일을 찾아, 상위폴더의 error/(원본 백업)와 rename/<진짜 소속 폴더명>/(정리된 사본)으로 재배치 + sort_log.csv 기록 | [utils/bmp_misplaced_sorter/processing.md](utils/bmp_misplaced_sorter/processing.md) |
| folder_suffix_copier | 지정 폴더를 재귀 탐색해 파일(bmp/raw 기본, 스캔된 확장자 체크박스 선택)에 상위 폴더명들을 `_`로 이은 접미어를 붙인 사본을 만드는 PyQt5 GUI. 별도 출력 폴더 모으기/원본 옆 생성 선택, 변경 전→후 미리보기 테이블 + 로그창, 이름 충돌 시 번호 부여, 원본 보존(복사만) | [utils/folder_suffix_copier/processing.md](utils/folder_suffix_copier/processing.md) |
| feel_capture (필캡쳐) | 시스템 트레이 상주 화면 캡쳐/녹화 PyQt5 도구. 드래그 방식(화면 어둡게+선택영역만 밝게)과 영역(빨간 고정 박스, 이동/리사이즈/우클릭 프리셋) 2가지 캡쳐 모드, 클립보드 또는 타임스탬프 파일명 폴더 저장(png/jpg/bmp/webp/tiff + gif/mp4/avi 실제 녹화), 저장 시 리사이즈, 사용자 지정 전역 단축키(모드 토글식 녹화 시작/종료 포함), 멀티 모니터 지원. PyInstaller exe 빌드 + 아이콘 생성 스크립트 포함 | [utils/feel_capture/processing.md](utils/feel_capture/processing.md) |

---

새 util을 추가하거나 기존 util을 변경하면:
1. 해당 util 폴더의 `processing.md`(상세)를 작성/갱신한다.
2. 위 표에 한 줄 요약 + 링크를 추가/갱신한다.
