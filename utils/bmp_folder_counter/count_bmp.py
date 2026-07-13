"""
상위 폴더 > 1단계 하위폴더(첫번째) > 2단계 하위폴더 구조에서,
1단계 하위폴더 중 이름순 정렬 기준 첫번째 폴더를 골라
그 안의 2단계 하위폴더별 bmp 파일 개수(재귀 포함)를 집계해 csv/md로 저장한다.

사용법:
    .venv\\Scripts\\python.exe utils\\bmp_folder_counter\\count_bmp.py "D:\\path\\to\\top_folder"
    (인자 없이 실행하면 경로를 input()으로 물어봄)
"""
import csv
import os
import sys


def list_subdirs(folder):
    return sorted(
        entry.name for entry in os.scandir(folder) if entry.is_dir()
    )


def count_bmp_recursive(folder):
    count = 0
    for _, _, files in os.walk(folder):
        for name in files:
            if name.lower().endswith(".bmp"):
                count += 1
    return count


def build_table(top_folder):
    if not os.path.isdir(top_folder):
        raise NotADirectoryError(f"폴더를 찾을 수 없습니다: {top_folder}")

    level1_dirs = list_subdirs(top_folder)
    if not level1_dirs:
        raise FileNotFoundError(f"1단계 하위폴더가 없습니다: {top_folder}")

    first_level1 = level1_dirs[0]
    first_level1_path = os.path.join(top_folder, first_level1)

    level2_dirs = list_subdirs(first_level1_path)

    rows = []
    total = 0
    for name in level2_dirs:
        cnt = count_bmp_recursive(os.path.join(first_level1_path, name))
        rows.append((name, cnt))
        total += cnt

    return first_level1, rows, total


def save_csv(path, first_level1, rows, total):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([f"1단계 폴더: {first_level1}"])
        writer.writerow(["하위폴더명", "bmp 개수"])
        for name, cnt in rows:
            writer.writerow([name, cnt])
        writer.writerow(["합계", total])


def save_md(path, first_level1, rows, total):
    lines = [
        f"# bmp 개수 집계 — 1단계 폴더: {first_level1}",
        "",
        "| 하위폴더명 | bmp 개수 |",
        "| --- | --- |",
    ]
    for name, cnt in rows:
        lines.append(f"| {name} | {cnt} |")
    lines.append(f"| **합계** | **{total}** |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def print_table(first_level1, rows, total):
    print(f"\n1단계 폴더: {first_level1}")
    if not rows:
        print("(2단계 하위폴더 없음)")
        return
    name_width = max(len("하위폴더명"), *(len(n) for n, _ in rows))
    print(f"{'하위폴더명'.ljust(name_width)}  bmp 개수")
    for name, cnt in rows:
        print(f"{name.ljust(name_width)}  {cnt}")
    print(f"{'합계'.ljust(name_width)}  {total}")


def main():
    if len(sys.argv) > 1:
        top_folder = sys.argv[1]
    else:
        top_folder = input("상위 폴더 경로를 입력하세요: ").strip().strip('"')

    first_level1, rows, total = build_table(top_folder)
    print_table(first_level1, rows, total)

    csv_path = os.path.join(top_folder, "bmp_count_result.csv")
    md_path = os.path.join(top_folder, "bmp_count_result.md")
    save_csv(csv_path, first_level1, rows, total)
    save_md(md_path, first_level1, rows, total)

    print(f"\n결과 저장됨:\n  {csv_path}\n  {md_path}")


if __name__ == "__main__":
    try:
        main()
    except (NotADirectoryError, FileNotFoundError) as e:
        print(f"오류: {e}")
        sys.exit(1)
