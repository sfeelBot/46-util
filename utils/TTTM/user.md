# 사용자 요청사항 이력

---

## [REQ-001] 초기 프로그램 개발 요청
- **날짜**: 2026-06-06
- **요청자**: sfeel.lee@gmail.com

### 사용환경
- Python, PyQt, opencv-python

### 이미지 정보
- 16-bit (RAW) 1채널 이미지
- OpenCV imread 사용 금지 → numpy로 읽기 (little-endian)
- 기본 이미지 크기: 3072×3072

### 분석 방식
1. **각 이미지별 전처리**
   - Threshold 슬라이더(UI)를 통한 이진화
   - 이진화 후 특정 ROI 선택
   - 선택 ROI 내에서 Blob 선택
   - 해당 Blob의 마스크 추출

2. **분석 항목**
   - 두 이미지의 Blob 좌상단에서 N pixel(UI 지정) 아래의 Y 좌표 출력 및 차이
   - 두 이미지의 Blob 좌측 edge에서 이미지 x=0까지의 거리(pixel) 및 차이
   - 두 이미지의 Blob 픽셀 면적 및 차이
   - 두 마스크를 하나의 이미지에서 비교 표시

3. **코드 작성 방식**
   - 로그 기록 (에러 파악 용이)
   - 이미지 뷰어에서 전처리 변경사항 실시간 확인
   - 모든 파라미터는 GUI에서 숫자 또는 슬라이더로 조절
   - Git을 통한 버전 관리
   - BAT 파일로 동작 확인

4. **테스트 이미지**
   - 직접 생성 (실제 테스트 이미지 없음)
   - test.png 참조하여 3072×3072으로 리사이즈
   - 내부 검은 형태의 위치 및 크기를 조금씩 변경하여 2개 생성

### 구현 결과 (v1.0)
- [x] 16-bit RAW numpy 읽기
- [x] Threshold 슬라이더 (0-65535)
- [x] ROI 선택 (SpinBox + 드래그)
- [x] Blob 탐색 및 선택
- [x] Y 좌표 / 왼쪽 엣지 / 면적 분석 테이블
- [x] 오버레이 비교 다이얼로그
- [x] 로그 기록 (app.log)
- [x] Git 설정 (.gitignore, git_init.bat)
- [x] 환경 확인 BAT (check.bat)
- [x] 테스트 이미지 생성 (tests/create_test_images.py)

---

## [REQ-002] MD 문서 파일 관리 요청
- **날짜**: 2026-06-06
- **내용**: 작성 중인 코드를 MD 파일로 정리
  - `claude.md`: 사용자의 지침사항 정리
  - `ui.md`: UI 틀 및 변경사항 정리
  - `process.md`: 내부 background 로직 정리 및 변경사항 업데이트
  - `QA.md`: 버그 변경사항 정리
  - `user.md`: 사용자의 요청사항 기록

### 구현 결과
- [x] claude.md 생성
- [x] ui.md 생성
- [x] process.md 생성
- [x] QA.md 생성
- [x] user.md 생성 (이 파일)

---

## 요청사항 등록 양식

```
## [REQ-XXX] 제목
- **날짜**: YYYY-MM-DD
- **내용**: 요청 내용 상세

### 구현 결과
- [ ] 항목1
- [ ] 항목2
```
