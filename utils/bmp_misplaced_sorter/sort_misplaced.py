"""
GitHub 이슈 #6 매칭표(storage_number_map.csv)를 기준으로,
상위폴더 안의 Test#... 폴더들에 잘못 들어간 bmp 파일을 찾아
상위폴더의 error/(원본 백업) 와 rename/<진짜 소속 폴더명>/(정리된 사본)으로 재배치한다.

매칭 규칙:
- storage_number_map.csv 의 "저장번호"가 각 셀의 정식(canonical) 폴더명이다.
- 같은 행의 "실제저장번호"가 비어있지 않으면, 촬영 시 그 값(예: Test#A1-0000137-6)으로
  이름 붙은 폴더가 실제로 디스크에 존재할 수 있다 (여러 셀을 한 세션으로 묶어 캡처한
  원본 폴더). 이런 폴더도 스캔 대상에 포함해야 한다.
- 모든 bmp 파일은, 전체 매칭표의 기대 접두사(실제저장번호 있으면 그 값, 없으면 저장번호
  자신, 문자열 긴 것부터 우선 매칭)로 파일명을 검사해 "진짜 소속 저장번호"를 알아낸다.
- 그 값이 파일이 실제로 들어있는 폴더명과 같으면 정상, 다르면(또는 매칭 자체가 안 되면)
  "잘못 들어간 파일"로 판정한다. 즉 폴더명이 저장번호 형식이든 실제저장번호 형식이든
  관계없이, 파일이 진짜 있어야 할 저장번호 폴더와 다르면 전부 재배치 대상이다.

사용법:
    .venv\\Scripts\\python.exe utils\\bmp_misplaced_sorter\\sort_misplaced.py "D:\\path\\to\\top_folder"
    (인자 없이 실행하면 경로를 input()으로 물어봄)
"""
import csv
import os
import shutil
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAP_CSV_PATH = os.path.join(SCRIPT_DIR, "storage_number_map.csv")


def load_expected_prefix_map(csv_path):
    mapping = {}
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            folder_name = row["저장번호"].strip()
            real_number = row["실제저장번호"].strip()
            expected_prefix = real_number if real_number else folder_name
            mapping[folder_name] = expected_prefix
    return mapping


def build_reverse_lookup(expected_prefix_map):
    # (expected_prefix, folder_name) 목록, 접두사 긴 순으로 정렬 (겹치는 접두사 오매칭 방지)
    pairs = [(prefix, folder) for folder, prefix in expected_prefix_map.items()]
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def find_true_folder(filename, reverse_lookup):
    for prefix, folder in reverse_lookup:
        if filename.startswith(prefix):
            return folder, prefix
    return None, None


def unique_dest_path(dest_dir, filename):
    dest_path = os.path.join(dest_dir, filename)
    if not os.path.exists(dest_path):
        return dest_path
    base, ext = os.path.splitext(filename)
    n = 1
    while True:
        candidate = os.path.join(dest_dir, f"{base}_dup{n}{ext}")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def main():
    if len(sys.argv) > 1:
        top_folder = sys.argv[1]
    else:
        top_folder = input("상위 폴더 경로를 입력하세요: ").strip().strip('"')

    if not os.path.isdir(top_folder):
        print(f"오류: 폴더를 찾을 수 없습니다: {top_folder}")
        sys.exit(1)

    expected_prefix_map = load_expected_prefix_map(MAP_CSV_PATH)
    reverse_lookup = build_reverse_lookup(expected_prefix_map)
    # 저장번호(canonical) 뿐 아니라, 촬영 세션이 실제저장번호 그대로 폴더명이 된 경우도 스캔 대상에 포함
    known_folder_names = set(expected_prefix_map.keys()) | {
        prefix for prefix, _ in reverse_lookup
    }

    error_dir = os.path.join(top_folder, "error")
    rename_dir = os.path.join(top_folder, "rename")

    log_rows = []
    count_normal = count_relocated = count_unrecognized = 0
    subfolders_processed = subfolders_skipped = 0

    top_subfolders = sorted(
        entry.name for entry in os.scandir(top_folder) if entry.is_dir()
    )

    for folder_name in top_subfolders:
        if folder_name in ("error", "rename"):
            continue
        if folder_name not in known_folder_names:
            subfolders_skipped += 1
            continue
        subfolders_processed += 1

        folder_path = os.path.join(top_folder, folder_name)

        for root, _, files in os.walk(folder_path):
            for filename in files:
                if not filename.lower().endswith(".bmp"):
                    continue

                true_folder, matched_prefix = find_true_folder(filename, reverse_lookup)

                if true_folder == folder_name:
                    count_normal += 1
                    continue

                src_path = os.path.join(root, filename)
                os.makedirs(error_dir, exist_ok=True)
                error_dest = unique_dest_path(error_dir, filename)
                shutil.move(src_path, error_dest)

                if true_folder is None:
                    count_unrecognized += 1
                    log_rows.append([folder_name, filename, "unrecognized", "", ""])
                    continue

                target_dir = os.path.join(rename_dir, true_folder)
                os.makedirs(target_dir, exist_ok=True)
                new_filename = true_folder + filename[len(matched_prefix):]
                target_path = os.path.join(target_dir, new_filename)

                if os.path.exists(target_path):
                    count_unrecognized += 1
                    log_rows.append([folder_name, filename, "error_conflict", true_folder, new_filename])
                    continue

                shutil.copy2(error_dest, target_path)
                count_relocated += 1
                log_rows.append([folder_name, filename, "relocated", true_folder, new_filename])

    log_path = os.path.join(top_folder, "sort_log.csv")
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["원래폴더", "원본파일명", "상태", "실제소속폴더", "결과파일명"])
        writer.writerows(log_rows)

    print(f"처리된 폴더 수: {subfolders_processed} (표에 없어 건너뜀: {subfolders_skipped})")
    print(f"정상: {count_normal}")
    print(f"재배치됨(rename/): {count_relocated}")
    print(f"미인식/충돌(error만): {count_unrecognized}")
    print(f"로그 저장됨: {log_path}")


if __name__ == "__main__":
    main()
