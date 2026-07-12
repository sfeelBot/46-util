"""filename_matching GUI의 핵심 로직 (GUI 비의존).

원본 파일명 -> (바코드 추출) -> 셀번호 -> 재료명 순으로 매핑하여
최종 파일명 `{material}_{cell}_{원본파일명}` 을 만들고,
그 결과를 다른 폴더로 복사(원본 보존)한다.

모든 경로/파일명은 한글을 포함할 수 있으므로 파일 입출력은 항상
UTF-8 로 처리한다 (Python 3 + Windows 는 경로 자체는 기본적으로
유니코드를 지원하므로 별도 인코딩 처리가 필요 없다).
"""
from __future__ import annotations

import csv
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# 원본 파일명 안의 "YYYY-MM-DD-바코드-" 패턴에서 바코드를 추출한다 (구형 파일명).
BARCODE_RE = re.compile(r"\d{4}-\d{2}-\d{2}-(\d+)-")

# 신형 파일명 안의 "Test#A8-0000008" 같은 저장번호 패턴을 추출한다.
STORAGE_RE = re.compile(r"Test#[AB]\d+-\d+")

STATUS_OK = "정상"
STATUS_NO_MATCH = "매칭실패"
STATUS_DUPLICATE = "중복"


# ============================================================
# 매핑 로드
# ============================================================
def load_barcode_cell_map(path: str | Path) -> dict[str, str]:
    """barcode -> cell 딕셔너리. csv 컬럼: barcode,cell"""
    mapping: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            barcode = (row.get("barcode") or "").strip()
            cell = (row.get("cell") or "").strip()
            if barcode and cell:
                mapping[barcode] = cell
    return mapping


def load_cell_material_map(path: str | Path) -> dict[str, str]:
    """cell -> material 딕셔너리. csv 컬럼: cell,material"""
    mapping: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cell = (row.get("cell") or "").strip()
            material = (row.get("material") or "").strip()
            if cell and material:
                mapping[cell] = material
    return mapping


def load_storage_cellbarcode_map(path: str | Path) -> dict[str, str]:
    """storage_number(예: Test#A8-0000008) -> cell_barcode(예: Test_2025_01_16_7632).

    csv 컬럼: storage_number,cell_barcode
    """
    mapping: dict[str, str] = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            storage_number = (row.get("storage_number") or "").strip()
            cell_barcode = (row.get("cell_barcode") or "").strip()
            if storage_number and cell_barcode:
                mapping[storage_number] = cell_barcode
    return mapping


# ============================================================
# 파일 스캔
# ============================================================
def discover_extensions(root: str | Path) -> list[str]:
    """root 하위(재귀)에 존재하는 모든 확장자를 소문자로 모아 정렬해서 반환한다."""
    exts: set[str] = set()
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext:
                exts.add(ext)
    return sorted(exts)


def scan_files(
    root: str | Path,
    extensions: set[str],
    exclude_dir: Optional[str | Path] = None,
) -> list[tuple[str, str]]:
    """root 하위(재귀)에서 extensions(소문자, '.' 포함)에 해당하는 파일을 찾는다.

    exclude_dir 아래 경로는 스캔 대상에서 제외한다(출력 폴더가 원본 폴더
    하위에 있을 때 결과물을 다시 읽어들이는 것을 막기 위함).

    반환: [(전체경로, root 기준 상대 디렉터리), ...]
    """
    root = str(root)
    exclude_abs = os.path.abspath(str(exclude_dir)) if exclude_dir else None
    results: list[tuple[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        abs_dirpath = os.path.abspath(dirpath)
        if exclude_abs and (
            abs_dirpath == exclude_abs or abs_dirpath.startswith(exclude_abs + os.sep)
        ):
            continue
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in extensions:
                results.append((os.path.join(dirpath, name), rel_dir))
    return results


# ============================================================
# 파일명 변환
# ============================================================
def compute_final_name(
    filename: str,
    barcode_cell_map: dict[str, str],
    cell_material_map: dict[str, str],
    storage_cellbarcode_map: Optional[dict[str, str]] = None,
) -> tuple[Optional[str], str, str]:
    """원본 파일명 -> 최종 변환명.

    바코드는 두 가지 방식 중 하나로 찾는다 (파일명 규칙이 시기별로 다르기 때문):
    1. 구형: 파일명에 "YYYY-MM-DD-바코드-" 패턴이 직접 있는 경우 (BARCODE_RE)
    2. 신형: 파일명에 "Test#A8-0000008" 같은 저장번호가 있고, storage_cellbarcode_map 으로
       Cell Barcode(예: Test_2025_01_16_7632)를 먼저 찾은 뒤 그 마지막 "_" 이후 숫자를 바코드로 사용

    반환: (최종파일명 또는 None, status, reason)
    """
    storage_cellbarcode_map = storage_cellbarcode_map or {}

    match = BARCODE_RE.search(filename)
    if match:
        barcode = match.group(1)
    else:
        storage_match = STORAGE_RE.search(filename)
        if not storage_match:
            return None, STATUS_NO_MATCH, "파일명에서 바코드 또는 저장번호 패턴을 찾을 수 없음"

        storage_number = storage_match.group(0)
        cell_barcode = storage_cellbarcode_map.get(storage_number)
        if cell_barcode is None:
            return None, STATUS_NO_MATCH, f"저장번호 {storage_number} 가 매핑표에 없음"

        barcode = cell_barcode.rsplit("_", 1)[-1]

    cell = barcode_cell_map.get(barcode)
    if cell is None:
        return None, STATUS_NO_MATCH, f"바코드 {barcode} 가 매핑표에 없음"

    material = cell_material_map.get(cell)
    if material is None:
        return None, STATUS_NO_MATCH, f"셀번호 {cell} 가 매핑표에 없음"

    final_name = f"{material}_{cell}_{filename}"
    return final_name, STATUS_OK, ""


@dataclass
class FileRow:
    src_path: str
    rel_dir: str  # 원본 root 기준 상대 디렉터리 ("" 이면 root 바로 아래)
    filename: str
    final_name: Optional[str]
    status: str
    reason: str
    checked: bool = True
    duplicate_key: Optional[str] = None  # 중복검사 이후 dest 경로 등의 키


def build_rows(
    root: str | Path,
    extensions: set[str],
    barcode_cell_map: dict[str, str],
    cell_material_map: dict[str, str],
    exclude_dir: Optional[str | Path] = None,
    storage_cellbarcode_map: Optional[dict[str, str]] = None,
) -> list[FileRow]:
    rows: list[FileRow] = []
    for src_path, rel_dir in scan_files(root, extensions, exclude_dir=exclude_dir):
        filename = os.path.basename(src_path)
        final_name, status, reason = compute_final_name(
            filename, barcode_cell_map, cell_material_map, storage_cellbarcode_map
        )
        rows.append(
            FileRow(
                src_path=src_path,
                rel_dir=rel_dir,
                filename=filename,
                final_name=final_name,
                status=status,
                reason=reason,
                checked=(status == STATUS_OK),
            )
        )
    return rows


# ============================================================
# 중복검사
# ============================================================
def find_duplicates(rows: list[FileRow], flatten: bool) -> dict[str, list[int]]:
    """checked=True, status==정상 인 행들 중 최종 목적지 경로가 같은 것들을 찾는다.

    flatten=True 면 final_name 만으로, False 면 (rel_dir, final_name) 으로 비교한다.
    반환: {키: [row index, ...]} (2개 이상인 것만 포함)
    dupliate 로 판정된 행은 status 를 STATUS_DUPLICATE 로 갱신하고,
    최초 정상 상태였던 행들은 이 함수 호출 전 상태로 되돌아갈 수 있도록
    별도 초기화는 호출자가 담당한다 (reset_duplicate_status 참고).
    """
    groups: dict[str, list[int]] = {}
    for idx, row in enumerate(rows):
        if not row.checked or row.status not in (STATUS_OK, STATUS_DUPLICATE):
            continue
        if row.final_name is None:
            continue
        key = row.final_name if flatten else f"{row.rel_dir}/{row.final_name}"
        groups.setdefault(key, []).append(idx)

    duplicates = {k: v for k, v in groups.items() if len(v) > 1}

    # 상태 갱신: 이번 검사에서 정상으로 재분류된 행은 STATUS_OK 로 복귀시킨다.
    dup_indices = {i for idxs in duplicates.values() for i in idxs}
    for idx, row in enumerate(rows):
        if row.status == STATUS_DUPLICATE and idx not in dup_indices:
            row.status = STATUS_OK
            row.reason = ""
        if idx in dup_indices:
            row.status = STATUS_DUPLICATE
            row.reason = "동일한 변환 결과 파일명이 여러 개 있음"

    return duplicates


# ============================================================
# 변환 실행
# ============================================================
class ConversionConflictError(Exception):
    def __init__(self, conflicts: list[str]):
        super().__init__("변환 대상 파일명이 충돌합니다.")
        self.conflicts = conflicts


def _dest_path(row: FileRow, output_dir: str, flatten: bool) -> str:
    if flatten:
        return os.path.join(output_dir, row.final_name)
    return os.path.join(output_dir, row.rel_dir, row.final_name)


def check_conflicts(rows: list[FileRow], output_dir: str, flatten: bool) -> list[str]:
    """실제 복사 전에 목적지 경로 충돌을 확인한다.

    - 선택된(checked) 행들끼리 목적지 경로가 겹치는 경우
    - 목적지에 이미 같은 이름의 파일이 존재하는 경우 (이전 실행 결과 등)
    둘 다 충돌로 취급하고, 충돌 목적지 경로 목록을 반환한다 (없으면 빈 리스트).
    """
    targets: dict[str, int] = {}
    conflicts: set[str] = set()

    for row in rows:
        if not row.checked or row.status != STATUS_OK or row.final_name is None:
            continue
        dest = _dest_path(row, output_dir, flatten)
        if dest in targets:
            conflicts.add(dest)
        else:
            targets[dest] = 1
        if os.path.exists(dest):
            conflicts.add(dest)

    return sorted(conflicts)


def convert_files(
    rows: list[FileRow],
    output_dir: str | Path,
    flatten: bool,
    progress_cb=None,
) -> dict:
    """checked=True, status==정상 인 행들을 output_dir 로 복사(원본 보존)한다.

    사전에 반드시 check_conflicts() 로 충돌이 없는지 확인해야 한다.
    충돌이 있는 상태로 호출하면 ConversionConflictError 를 던진다.
    progress_cb(done, total) 이 주어지면 파일 하나를 복사할 때마다 호출한다
    (대량 파일 복사 시 GUI 진행률 표시용).
    반환: 되돌리기에 사용할 로그 dict.
    """
    output_dir = str(output_dir)
    conflicts = check_conflicts(rows, output_dir, flatten)
    if conflicts:
        raise ConversionConflictError(conflicts)

    os.makedirs(output_dir, exist_ok=True)

    targets = [
        row for row in rows
        if row.checked and row.status == STATUS_OK and row.final_name is not None
    ]
    total = len(targets)

    entries = []
    for done, row in enumerate(targets, start=1):
        dest = _dest_path(row, output_dir, flatten)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(row.src_path, dest)
        entries.append({"src": row.src_path, "dst": dest})
        if progress_cb is not None:
            progress_cb(done, total)

    log = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "output_dir": output_dir,
        "flatten": flatten,
        "entries": entries,
    }
    return log


def save_log(log: dict, output_dir: str | Path) -> str:
    output_dir = str(output_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(output_dir, f"_conversion_log_{ts}.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return log_path


def undo_log(log_or_path) -> tuple[int, int]:
    """변환 로그(dict 또는 json 파일 경로)를 받아 그 로그로 생성된 결과 파일만 삭제한다.

    원본(src) 파일은 절대 건드리지 않는다. 반환: (삭제된 개수, 이미 없어서 건너뛴 개수)
    """
    if isinstance(log_or_path, (str, Path)):
        with open(log_or_path, "r", encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = log_or_path

    removed = 0
    missing = 0
    for entry in log.get("entries", []):
        dst = entry["dst"]
        if os.path.exists(dst):
            os.remove(dst)
            removed += 1
        else:
            missing += 1
    return removed, missing
