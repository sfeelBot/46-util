"""폴더 구조(그룹 번호) 기반 crop 이미지 재명명 로직 (GUI 비의존).

GitHub 이슈 #5 대응: 일부 crop 원본 파일명에는 저장번호(`Test#A..`)가 이미
박혀 있지만, 그 값이 실제 셀 위치와 어긋나는 경우가 있다. 이 모듈은 그
값을 신뢰하지 않고 대신 폴더 구조를 신뢰한다:

    {그룹폴더}/cropped/{crop파일}

그룹폴더 이름이 숫자 N(예: "02", 앞 0은 무시. "35 (스크랩無)"처럼 뒤에
텍스트가 붙어도 앞의 숫자만 읽는다)이면, 그 그룹은 셀 인덱스
`[4N-3, 4N-2, 4N-1, 4N]` 4개를 담고 있고 cropped 폴더 안의 crop 1~4가
오름차순으로 이 4개 인덱스에 배정된다 (crop1 -> 4N-3, crop4 -> 4N).

계산된 셀 인덱스로 `storage_ab_defect_info.csv`의 "No" 컬럼을 조회해
올바른 A열_저장번호를 가져오고, crop 접미사(`_{idx}_x..y..w..h..`)를 뗀
베이스 파일명 안에서 (틀렸을 수 있는) 기존 `Test#A..` 패턴을 찾아 그
값으로 치환한다 (crop_remap.py 와 동일한 출력 형식). 베이스 파일명에
그 패턴이 아예 없으면 정확한 값을 앞에 붙인다.
"""
from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Optional

import core
import crop_remap  # CROP_SUFFIX_RE / STORAGE_RE 재사용

GROUP_NUMBER_RE = re.compile(r"^0*(\d+)")


def load_ab_map(path: str | Path) -> dict[int, str]:
    """storage_ab_defect_info.csv -> {No(셀 인덱스): A열_저장번호}"""
    mapping: dict[int, str] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            no = (row.get("No") or "").strip()
            a_storage = (row.get("A열_저장번호") or "").strip()
            if no and a_storage:
                mapping[int(no)] = a_storage
    return mapping


def extract_group_number(rel_dir: str) -> Optional[int]:
    """rel_dir(스캔 root 기준 상대경로)의 마지막 두 구성요소가
    '{그룹폴더}/cropped' 형태인지 확인하고, 맞으면 그룹번호(N)를 반환한다.
    (cropped 폴더 바로 아래에 있는 파일이 아니면 None)
    """
    parts = [p for p in re.split(r"[\\/]", rel_dir) if p]
    if len(parts) < 2 or parts[-1] != "cropped":
        return None
    m = GROUP_NUMBER_RE.match(parts[-2])
    if not m:
        return None
    return int(m.group(1))


def compute_remapped_filename(
    cropped_filename: str, rel_dir: str, ab_map: dict[int, str]
) -> tuple[Optional[str], str, str]:
    """crop 파일명 + (스캔 root 기준) 상대경로 -> (재구성된 파일명 또는 None, status, reason)"""
    group_number = extract_group_number(rel_dir)
    if group_number is None:
        return (
            None, core.STATUS_NO_MATCH,
            "폴더 구조가 '{그룹번호}/cropped/' 형태가 아님 (그룹번호를 찾을 수 없음)"
        )

    name, ext = os.path.splitext(cropped_filename)
    suffix_match = crop_remap.CROP_SUFFIX_RE.match(name)
    if not suffix_match:
        return None, core.STATUS_NO_MATCH, "image_cropper 출력 파일명 형식(_{ROI번호}_x..y..w..h..)이 아님"

    base = suffix_match.group("base")
    crop_index = int(suffix_match.group("idx"))
    if crop_index not in (1, 2, 3, 4):
        return None, core.STATUS_NO_MATCH, f"ROI 번호 {crop_index} 는 1~4 범위가 아님"

    cell_index = 4 * (group_number - 1) + crop_index
    a_storage = ab_map.get(cell_index)
    if a_storage is None:
        return (
            None, core.STATUS_NO_MATCH,
            f"셀 인덱스 {cell_index}(그룹 {group_number}, crop {crop_index})가 매핑표(No)에 없음"
        )

    # 베이스 파일명 안의 (틀렸을 수 있는) 기존 저장번호를 찾아 올바른 값으로 치환.
    # 패턴 자체가 없으면 앞에 붙인다.
    storage_match = crop_remap.STORAGE_RE.search(base)
    if storage_match:
        new_base = base[: storage_match.start()] + a_storage + base[storage_match.end() :]
    else:
        new_base = f"{a_storage}_{base}"

    new_filename = new_base + ext
    return new_filename, core.STATUS_OK, ""


def build_rows(
    root: str, extensions: set[str], ab_map: dict[int, str], exclude_dir: Optional[str] = None
) -> list[core.FileRow]:
    """core.FileRow 를 그대로 재사용 (final_name 자리에 재명명된 파일명을 넣는다).

    이렇게 하면 core.py 의 find_duplicates/check_conflicts/convert_files/
    save_log/undo_log 를 그대로 재사용할 수 있다.
    """
    rows: list[core.FileRow] = []
    for src_path, rel_dir in core.scan_files(root, extensions, exclude_dir=exclude_dir):
        filename = os.path.basename(src_path)
        new_filename, status, reason = compute_remapped_filename(filename, rel_dir, ab_map)
        rows.append(
            core.FileRow(
                src_path=src_path,
                rel_dir=rel_dir,
                filename=filename,
                final_name=new_filename,
                status=status,
                reason=reason,
                checked=(status == core.STATUS_OK),
            )
        )
    return rows
