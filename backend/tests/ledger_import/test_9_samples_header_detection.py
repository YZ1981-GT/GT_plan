"""F11 9 家样本 header 快照参数化测试（Sprint 10 Task 10.32-10.33）。

对 ``backend/tests/fixtures/header_snapshots.json`` 中每家样本跑
``detect_file_from_path`` + ``identify``，断言：
- ``data_start_row`` 与快照一致
- ``header_cells[:8]`` 与快照一致
- ``table_type`` 与快照一致

真实样本缺失时该家测试 skip（CI 模式下数据目录可能不可用）。

快照再生：``python scripts/_gen_header_snapshots.py``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "数据"
SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "header_snapshots.json"


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        return {}
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


_SNAPSHOT = _load_snapshot()

# 参数化：(company_name, expected_snapshot_dict)
_CASES = [
    pytest.param(name, data, id=name) for name, data in _SNAPSHOT.items()
]


@pytest.mark.parametrize("company,expected", _CASES)
def test_header_snapshot_stable(company: str, expected: dict):
    """每家样本的 header 识别结果应与快照一致。"""
    rel_path = expected["file"]
    path = DATA_DIR / rel_path
    if not path.exists():
        pytest.skip(f"Real sample missing: {path}")

    fd = detect_file_from_path(str(path), path.name)
    actual_sheets = {s.sheet_name: s for s in fd.sheets}

    for exp_sheet in expected["sheets"]:
        sheet_name = exp_sheet["sheet_name"]
        assert sheet_name in actual_sheets, (
            f"{company}: sheet {sheet_name!r} 丢失，实际 sheets={list(actual_sheets)}"
        )
        sheet = actual_sheets[sheet_name]
        idf = identify(sheet)

        # data_start_row 比对
        assert sheet.data_start_row == exp_sheet["data_start_row"], (
            f"{company} / {sheet_name}: data_start_row 不一致，"
            f"expected={exp_sheet['data_start_row']} actual={sheet.data_start_row}"
        )

        # header_cells 前 8 列比对
        actual_headers = (sheet.detection_evidence.get("header_cells") or [])[:8]
        assert actual_headers == exp_sheet["header_cells_first_8"], (
            f"{company} / {sheet_name}: header_cells[:8] 不一致\n"
            f"expected={exp_sheet['header_cells_first_8']}\n"
            f"actual={actual_headers}"
        )

        # table_type 比对
        assert idf.table_type == exp_sheet["table_type"], (
            f"{company} / {sheet_name}: table_type 不一致，"
            f"expected={exp_sheet['table_type']} actual={idf.table_type}"
        )


def test_snapshot_file_exists():
    """快照文件必须存在（CI 保护）。"""
    assert SNAPSHOT_PATH.exists(), (
        f"快照文件 {SNAPSHOT_PATH} 不存在，"
        "请运行 `python scripts/_gen_header_snapshots.py` 生成"
    )
    data = _load_snapshot()
    assert data, "快照文件内容为空"
