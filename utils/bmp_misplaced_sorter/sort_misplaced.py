"""
GitHub 이슈 #6 매칭표(storage_number_map.csv)를 기준으로,
상위폴더 안의 Test#... 폴더들에 잘못 들어간 bmp 파일을 찾아
상위폴더의 error/(원본 백업) 와 rename/<진짜 소속 폴더명>/(정리된 사본)으로 재배치한다.

매칭 규칙:
- storage_number_map.csv 의 "저장번호"가 실제 Test#... 폴더명이다.
- 같은 행의 "실제저장번호"가 비어있지 않으면, 그 폴더에 있어야 할 파일명의
  진짜 접두사는 "실제저장번호"이다 (비어있으면 폴더명 자신이 접두사).
- 어떤 폴더의 bmp 파일명이 자신의 기대 접두사로 시작하지 않으면 "잘못 들어간 파일"이다.
  이때 전체 매칭표를 뒤져서(기대 접두사 문자열이 가장 긴 것부터) 파일명이 어느 폴더의
  기대 접두사로 시작하는지 찾아 "진짜 소속 폴더"를 결정한다.

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

    error_dir = os.path.join(top_folder, "error")
    rename_dir = os.path.join(top_folder, "rename")

    log_rows = []
    count_normal = count_relocated = count_unrecognized = 0
    subfolders_processed = subfolders_skipped = 0

    top_subfolders = sorted(
        entry.name for entry in os.scandir(top_folder) if entry.is_dir()
    )

    for folder_name in top_subfolders:
        if folder_name not in expected_prefix_map:
            subfolders_skipped += 1
            continue
        subfolders_processed += 1

        own_expected_prefix = expected_prefix_map[folder_name]
        folder_path = os.path.join(top_folder, folder_name)

        for root, _, files in os.walk(folder_path):
            for filename in files:
                if not filename.lower().endswith(".bmp"):
                    continue

                if filename.startswith(own_expected_prefix):
                    count_normal += 1
                    continue

                src_path = os.path.join(root, filename)
                true_folder, matched_prefix = find_true_folder(filename, reverse_lookup)

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
