"""crop 이미지 재명명 로직 (GUI 비의존).

`image_cropper` util로 하나의 원본 이미지(내부에 물리적으로 4개 셀이 찍혀 있음)를
4등분 crop하면, 파일명이 `{원본파일명}_{ROI번호}_x{x}y{y}w{w}h{h}{확장자}` 형태가 된다
(image_cropper 의 출력 규칙, processing.md 참고).

원본파일명 안에는 그 4개 셀 중 "대표" 셀 하나의 저장번호(예: Test#A4-0000004)만
들어있으므로, ROI번호(crop 순서 1~4)를 이용해 나머지 3개 셀의 실제 저장번호를
역산한다: crop 1은 대표 저장번호 그대로, crop 2/3/4는 시리얼을 1씩 감소시킨다.
lane(A/B 뒤의 숫자)은 storage_cellbarcode_map.csv 와 동일하게 1~8 순환 규칙으로
재계산한다 (core.py 의 STORAGE_RE 형식과 호환).

재명명 결과는 crop 접미사(`_{idx}_x..y..w..h..`)를 제거하고 저장번호만 교체한,
"원래 개별 촬영이었다면 가졌을 파일명"이다. 이후 core.py 의 barcode->cell->material
파이프라인에 그대로 다시 입력할 수 있다.
"""
from __future__ import annotations

import os
import re
from typing import Optional

import core

# image_cropper 출력 파일명 규칙: {원본파일명}_{ROI번호}_x{x}y{y}w{w}h{h}
CROP_SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<idx>\d+)_x\d+y\d+w\d+h\d+$")

# 저장번호 패턴: Test#A8-0000008 (letter + lane숫자 + '-' + 시리얼숫자)
STORAGE_RE = re.compile(r"Test#(?P<letter>[AB])(?P<lane>\d+)-(?P<serial>\d+)")


def compute_remapped_filename(cropped_filename: str) -> tuple[Optional[str], str, str]:
    """crop 파일명 -> (재구성된 원본 스타일 파일명 또는 None, status, reason)"""
    name, ext = os.path.splitext(cropped_filename)
    suffix_match = CROP_SUFFIX_RE.match(name)
    if not suffix_match:
        return None, core.STATUS_NO_MATCH, "image_cropper 출력 파일명 형식(_{ROI번호}_x..y..w..h..)이 아님"

    base = suffix_match.group("base")
    crop_index = int(suffix_match.group("idx"))
    if crop_index not in (1, 2, 3, 4):
        return None, core.STATUS_NO_MATCH, f"ROI 번호 {crop_index} 는 1~4 범위가 아님"

    storage_match = STORAGE_RE.search(base)
    if not storage_match:
        return None, core.STATUS_NO_MATCH, "원본 파일명에서 저장번호(Test#A.. 형식) 패턴을 찾을 수 없음"

    serial_str = storage_match.group("serial")
    serial = int(serial_str)
    new_serial = serial - (crop_index - 1)
    if new_serial <= 0:
        return None, core.STATUS_NO_MATCH, f"계산된 시리얼 번호({new_serial})가 0 이하 (원본 시리얼/ROI번호 확인 필요)"

    letter = storage_match.group("letter")
    new_lane = ((new_serial - 1) % 8) + 1
    new_storage = f"Test#{letter}{new_lane}-{new_serial:0{len(serial_str)}d}"

    new_base = base[: storage_match.start()] + new_storage + base[storage_match.end() :]
    new_filename = new_base + ext
    return new_filename, core.STATUS_OK, ""


def build_rows(
    root: str, extensions: set[str], exclude_dir: Optional[str] = None
) -> list[core.FileRow]:
    """core.FileRow 를 그대로 재사용 (final_name 자리에 재명명된 파일명을 넣는다).

    이렇게 하면 core.py 의 find_duplicates/check_conflicts/convert_files/
    save_log/undo_log 를 그대로 재사용할 수 있다.
    """
    rows: list[core.FileRow] = []
    for src_path, rel_dir in core.scan_files(root, extensions, exclude_dir=exclude_dir):
        filename = os.path.basename(src_path)
        new_filename, status, reason = compute_remapped_filename(filename)
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
