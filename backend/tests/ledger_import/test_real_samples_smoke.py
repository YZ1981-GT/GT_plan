"""真实样本 smoke test — 防止识别回归（S6-10）。

每个样本只验证"表类型识别正确"，不走入库链路。
样本文件位于仓库根 `数据/` 目录，若缺失则 skip。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ledger_import.detector import detect_file_from_path
from app.services.ledger_import.identifier import identify

# 仓库根（backend 上一级）
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "数据"


def _identify_sheets(path: Path) -> list[tuple[str, str]]:
    """返回 [(sheet_name, table_type), ...]。"""
    fd = detect_file_from_path(str(path), path.name)
    results = []
    for sheet in fd.sheets:
        identified = identify(sheet)
        results.append((sheet.sheet_name, identified.table_type))
    return results


@pytest.mark.skipif(
    not (DATA_DIR / "和平物流25加工账-药品批发.xlsx").exists(),
    reason="real sample 数据/和平物流25加工账-药品批发.xlsx not present",
)
def test_heping_wuliu_balance_recognized():
    """和平物流余额表应识别为 balance（S6-9 L1 锁定修复）。"""
    path = DATA_DIR / "和平物流25加工账-药品批发.xlsx"
    results = _identify_sheets(path)

    sheet_names = {n: t for n, t in results}
    assert "余额表" in sheet_names, f"余额表 sheet 应存在, got: {list(sheet_names)}"
    assert sheet_names["余额表"] == "balance", (
        f"余额表 sheet 应识别为 balance（L1 强信号锁定），实际 {sheet_names['余额表']}"
    )


@pytest.mark.skipif(
    not (DATA_DIR / "YG36-重庆医药集团四川物流有限公司2025.xlsx").exists(),
    reason="real sample YG36 not present",
)
def test_yg36_recognized():
    """YG36 四川物流：含核算维度的余额表 + 序时账都应正确识别。"""
    path = DATA_DIR / "YG36-重庆医药集团四川物流有限公司2025.xlsx"
    results = _identify_sheets(path)
    types = [t for _, t in results]

    assert "balance" in types, f"应有 balance sheet, got: {results}"
    assert "ledger" in types, f"应有 ledger sheet, got: {results}"
