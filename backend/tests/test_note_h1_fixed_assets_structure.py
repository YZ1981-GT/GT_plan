"""附注固定资产章节 columns 结构守卫（§五、22 上市 / §八、22 国企）。

锁定 `fix_note_h1_fixed_assets_structure.py` 的对齐结果，防 md 重建 / 并发会话回退：

- 两版章节存在且表数正确（上市 6 / 国企 5）；
- 每张表 `columns` 齐备、显式单级（`flat`）、无 `group`、`columns[0].label == headers[0]`；
- 列 key 逐字等于同步载荷（`h1DisclosureSyncPayload.ts`）的权威列 key —— 防 seed 路径
  与推送路径列键漂移；
- guidance 齐备；
- 反向自检：validate 能抓出「缺 columns」的坏结构（防守卫空转）。

spec: h1-fixed-assets-mapping-and-disclosure-alignment
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_FIX = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "fix" / "fix_note_h1_fixed_assets_structure.py"
)


def _load_fix():
    spec = importlib.util.spec_from_file_location("_fix_h1_struct", _FIX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = _load_fix()

# 权威列 key（逐字取自 h1DisclosureSyncPayload.ts 的 H1_SOE_COLUMNS / buildH1ListedColumns）
_EXPECTED_KEYS = {
    "listed": {
        "固定资产": ["label", "end_balance", "prior_balance"],
        "固定资产情况": [
            "label", "房屋及建筑物", "机器设备", "运输设备", "办公设备", "其他设备", "合计",
        ],
        "暂时闲置的固定资产情况": ["label", "cost", "dep", "impairment", "book_value", "remark"],
        "通过经营租赁租出的固定资产": ["label", "book_value"],
        "未办妥产权证书的固定资产情况": ["label", "book_value", "reason"],
        "固定资产清理": ["label", "end_balance", "prior_balance", "reason"],
    },
    "soe": {
        "固定资产": ["label", "end_carrying", "begin_carrying"],
        "固定资产情况": ["label", "begin", "increase", "decrease", "end"],
        "暂时闲置的固定资产情况": [
            "label", "original_cost", "accum_dep", "impairment", "carrying", "remark",
        ],
        "未办妥产权证书的固定资产情况": ["label", "carrying", "reason"],
        "固定资产清理": ["label", "end_carrying", "begin_carrying", "reason"],
    },
}


def _section(variant: str) -> dict:
    path, section_number, _ = FIX._TARGETS[variant]
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    sec = next(s for s in doc["sections"] if str(s.get("section_number")) == section_number)
    return sec


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_check_passes(variant: str):
    """脚本 --check 无欠账（columns/flat/guidance/表数齐备且对齐）。"""
    _changes, warnings, errs = FIX._runner(variant, dry_run=True, check=True)
    assert not errs, f"{variant} 结构欠账：{errs}"
    assert not warnings, f"{variant} 告警：{warnings}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_table_count(variant: str):
    sec = _section(variant)
    names = [str(t.get("name")) for t in sec.get("tables") or []]
    assert names == FIX.EXPECTED[variant], f"{variant} 表序/表名漂移：{names}"


@pytest.mark.parametrize("variant", ["listed", "soe"])
def test_columns_keys_match_sync_payload(variant: str):
    """seed 路径 columns key == 推送路径列 key（防两路径漂移）。"""
    sec = _section(variant)
    by_name = {str(t.get("name")): t for t in sec.get("tables") or []}
    for name, want_keys in _EXPECTED_KEYS[variant].items():
        tbl = by_name[name]
        cols = tbl.get("columns") or []
        keys = [c.get("key") for c in cols]
        assert keys == want_keys, f"{variant}/{name} 列 key 漂移：{keys} ≠ {want_keys}"
        # 单级：首列 flat + is_label，无任何 group，且无 _column_groups
        assert cols[0].get("is_label") and cols[0].get("flat"), f"{variant}/{name} 首列未 flat"
        assert all(not c.get("group") for c in cols), f"{variant}/{name} 混入 group（应为单级）"
        assert not tbl.get("_column_groups"), f"{variant}/{name} 残留 _column_groups"
        assert str(cols[0].get("label")) == str(tbl["headers"][0]), (
            f"{variant}/{name} columns[0].label ≠ headers[0]"
        )
        assert str(tbl.get("guidance") or "").strip(), f"{variant}/{name} 缺 guidance"


def test_reverse_self_check_catches_missing_columns():
    """反向自检：validate_section 必须能抓出「缺 columns」的坏结构（防守卫空转）。"""
    from _note_structure_kit import validate_section

    broken = {
        "tables": [{"name": "固定资产", "headers": ["项目", "期末余额"], "rows": [], "guidance": "x"}],
    }
    errs = validate_section(broken, ["固定资产"])
    assert any("缺 columns" in e for e in errs), f"validate 未抓出缺 columns：{errs}"
