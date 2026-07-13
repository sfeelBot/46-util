"""
상위폴더 안의 "Test#A5-0000013" 형식 하위폴더들을 전부 대상으로,
각 하위폴더 바로 안(재귀 X)의 bmp 파일명 앞부분(폴더명과 같은 형식:
prefix + 숫자, 예 "Test#A5-0000021")을 그 폴더의 실제 이름으로 치환한다.
나머지 뒷부분(예 "-14-000_14_C4_2026~~~~.bmp")은 그대로 유지한다.

패턴이 안 맞거나 치환 후 이름이 충돌하는 파일은 그 하위폴더 안의
error/ 폴더로 이동시키고 rename_log.csv에 사유를 남긴다.

사용법:
    .venv\\Scripts\\python.exe utils\\bmp_rename_by_folder\\rename_bmp.py "D:\\path\\to\\top_folder"
    (인자 없이 실행하면 경로를 input()으로 물어봄)
"""
import csv
import os
import re
import shutil
import sys

FOLDER_NAME_RE = re.compile(r"^(?P<prefix>.+-)(?P<number>\d+)$")


def parse_folder_name(folder_name):
    m = FOLDER_NAME_RE.match(folder_name)
    if not m:
        return None
    return m.group("prefix")


def process_subfolder(subfolder_path, folder_name, log_rows):
    prefix = parse_folder_name(folder_name)
    if prefix is None:
        log_rows.append([folder_name, "", "", "skip_folder", "폴더명이 'prefix-숫자' 형식이 아님"])
        return 0, 0, 0

    file_match_re = re.compile(r"^" + re.escape(prefix) + r"\d+")

    error_dir = os.path.join(subfolder_path, "error")
    renamed = skipped_no_change = errored = 0

    bmp_files = [
        entry.name for entry in os.scandir(subfolder_path)
        if entry.is_file() and entry.name.lower().endswith(".bmp")
    ]

    for filename in bmp_files:
        m = file_match_re.match(filename)
        if not m:
            os.makedirs(error_dir, exist_ok=True)
            shutil.move(os.path.join(subfolder_path, filename), os.path.join(error_dir, filename))
            log_rows.append([folder_name, filename, "", "error", "패턴 불일치"])
            errored += 1
            continue

        new_filename = folder_name + filename[m.end():]

        if new_filename == filename:
            log_rows.append([folder_name, filename, new_filename, "no_change", ""])
            skipped_no_change += 1
            continue

        new_path = os.path.join(subfolder_path, new_filename)
        if os.path.exists(new_path):
            os.makedirs(error_dir, exist_ok=True)
            shutil.move(os.path.join(subfolder_path, filename), os.path.join(error_dir, filename))
            log_rows.append([folder_name, filename, new_filename, "error", "치환 후 이름 충돌"])
            errored += 1
            continue

        os.rename(os.path.join(subfolder_path, filename), new_path)
        log_rows.append([folder_name, filename, new_filename, "renamed", ""])
        renamed += 1

    return renamed, skipped_no_change, errored


def main():
    if len(sys.argv) > 1:
        top_folder = sys.argv[1]
    else:
        top_folder = input("상위 폴더 경로를 입력하세요: ").strip().strip('"')

    if not os.path.isdir(top_folder):
        print(f"오류: 폴더를 찾을 수 없습니다: {top_folder}")
        sys.exit(1)

    subfolders = sorted(
        entry.name for entry in os.scandir(top_folder) if entry.is_dir()
    )

    log_rows = []
    total_renamed = total_no_change = total_error = 0

    for folder_name in subfolders:
        r, n, e = process_subfolder(os.path.join(top_folder, folder_name), folder_name, log_rows)
        total_renamed += r
        total_no_change += n
        total_error += e

    log_path = os.path.join(top_folder, "rename_log.csv")
    with open(log_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["하위폴더", "원본파일명", "결과파일명", "상태", "사유"])
        writer.writerows(log_rows)

    print(f"처리된 하위폴더 수: {len(subfolders)}")
    print(f"이름 변경: {total_renamed}")
    print(f"변경 없음(이미 일치): {total_no_change}")
    print(f"에러(패턴 불일치/충돌, error 폴더로 이동): {total_error}")
    print(f"로그 저장됨: {log_path}")


if __name__ == "__main__":
    main()
