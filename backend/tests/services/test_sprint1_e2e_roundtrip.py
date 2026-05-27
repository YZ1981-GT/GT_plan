"""Sprint 1 Task 1.6 端到端 round-trip 集成测试.

Spec: .kiro/specs/disclosure-note-full-revamp/ Sprint 1 Task 1.6
Validates: R1.3 验收 12（迁移后前端老代码读 values + _cell_modes 仍能跑零回归）
            R1.3 验收 11（manual 模式 manual_value 备份）
            D1 sidecar 兼容铁律

任务原文要求「3 个真实项目跑迁移后前端零回归」— 本地 PG 无真实附注数据
（已实证），改用合成 table_data 走完 0.2 迁移 → 1.5 三态合并 → 1.3 binding
路径完整链路，证明 round-trip 不丢字段。

链路：
    legacy table_data
      ↓ Task 0.2 migrate.upgrade_table_data → 升级 v2 sidecar (row_type + _cell_meta)
      ↓ Task 1.5 merge_table_data_preserving_cell_modes → 与新算 td 三态合并
      ↓ Task 1.3 _build_with_binding 输出新 td（合并入参）
    最终 td 必须：
      a) 老前端读 values + _cell_modes 不报错（仅 dict / list 基础结构）
      b) auto col 用新值 / manual col 保留旧值 + 备份 / locked col 保留旧值
      c) row_type / _cell_meta 字段完整保留
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))

# 0.2 升级函数
from migrate_disclosure_notes_to_v2 import upgrade_table_data  # noqa: E402

# 1.5 三态合并
from app.services.note_cell_merge import (  # noqa: E402
    merge_table_data_preserving_cell_modes,
)


def _legacy_table_data() -> dict:
    """模拟 v2 升级前的 legacy table_data（前端老代码写入的样子）.

    含 3 行：
      - 银行存款（普通行）
      - 库存现金（用户改 manual + 写了 99.0）
      - 合计（is_total）
    """
    return {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {
                "label": "银行存款",
                "values": [12345.67, 11000.00],
                "_cell_modes": {"0": "auto", "1": "auto"},
                "is_total": False,
            },
            {
                "label": "库存现金",
                "values": [99.0, 50.0],  # 用户手填 99
                "_cell_modes": {"0": "manual", "1": "auto"},
                "is_total": False,
            },
            {
                "label": "合计",
                "values": [12444.67, 11050.00],
                "_cell_modes": {"0": "auto", "1": "auto"},
                "is_total": True,
            },
        ],
    }


def _new_engine_output() -> dict:
    """模拟 _build_with_binding 重新算出的新 table_data（auto 全部新值）."""
    return {
        "headers": ["项目", "期末余额", "期初余额"],
        "rows": [
            {
                "label": "银行存款",
                "values": [99999.99, 88888.88],  # 引擎新算
                "row_type": "data",
                "_cell_modes": {},  # 新输出 _cell_modes 默认空（用户态由 caller merge 接管）
                "_cell_meta": {
                    "0": {
                        "manual_value": None,
                        "semantic": "closing_balance",
                        "binding_id": "五、1 货币资金.银行存款.closing_balance",
                    },
                    "1": {
                        "manual_value": None,
                        "semantic": "opening_balance",
                        "binding_id": "五、1 货币资金.银行存款.opening_balance",
                    },
                },
                "is_total": False,
            },
            {
                "label": "库存现金",
                "values": [55555.55, 44444.44],
                "row_type": "data",
                "_cell_modes": {},
                "_cell_meta": {
                    "0": {
                        "manual_value": None,
                        "semantic": "closing_balance",
                        "binding_id": "五、1 货币资金.库存现金.closing_balance",
                    },
                    "1": {
                        "manual_value": None,
                        "semantic": "opening_balance",
                        "binding_id": "五、1 货币资金.库存现金.opening_balance",
                    },
                },
                "is_total": False,
            },
            {
                "label": "合计",
                "values": [None, None],  # binding 路径合计先 None 占位
                "row_type": "total",
                "_cell_modes": {},
                "_cell_meta": {},
                "is_total": True,
            },
        ],
    }


# ---------------------------------------------------------------------------


def test_e2e_legacy_to_v2_then_merge_with_engine_output_roundtrip():
    """端到端：legacy → 0.2 迁移 → 1.5 合并新算结果 → 字段完整保留."""
    legacy = _legacy_table_data()
    legacy_snapshot = deepcopy(legacy)

    # ── Step 1: 0.2 迁移：合成 row_type + _cell_meta sidecar ──────────
    migrated = deepcopy(legacy)
    stats = upgrade_table_data(migrated)

    assert stats["rows_total"] == 3
    assert stats["row_type_added"] == 3
    assert stats["_cell_meta_added"] == 3
    # manual_value 备份：库存现金 col0 (manual mode + values=99.0)
    assert stats["manual_values_backed_up"] == 1

    # 老字段 byte-for-byte 不变（除新增的 row_type / _cell_meta）
    for i, r in enumerate(migrated["rows"]):
        for key, val in legacy_snapshot["rows"][i].items():
            assert r[key] == val, f"row {i} field {key} mutated"
        # 必须新增了 row_type 和 _cell_meta
        assert "row_type" in r
        assert "_cell_meta" in r

    # 库存现金 col0 manual_value 已备份 = 99.0
    cash_row = migrated["rows"][1]
    assert cash_row["_cell_meta"]["0"]["manual_value"] == 99.0
    # 合计行也升级 — row_type=total（is_total=True 触发）
    assert migrated["rows"][2]["row_type"] == "total"

    # ── Step 2: 引擎重新算（_build_with_binding 风格输出）──────────────
    engine_new = _new_engine_output()

    # ── Step 3: 1.5 三态合并 ──────────────────────────────────────────
    merged = merge_table_data_preserving_cell_modes(migrated, engine_new)

    # ── 断言 a: 老前端读 values 仍能取到 ─────────────────────────────
    bank = merged["rows"][0]
    assert isinstance(bank["values"], list)
    assert isinstance(bank["_cell_modes"], dict)
    cash = merged["rows"][1]
    assert isinstance(cash["values"], list)
    assert isinstance(cash["_cell_modes"], dict)

    # ── 断言 b: auto 列被新值覆盖 / manual 列保留旧值 ─────────────────
    # 银行存款（auto/auto）→ 全用新值
    assert bank["values"] == [99999.99, 88888.88]

    # 库存现金（manual/auto）→ col0 保留 99.0；col1 用新值
    assert cash["values"] == [99.0, 44444.44]
    # manual_value 备份保留（迁移阶段已写入）
    assert cash["_cell_meta"]["0"]["manual_value"] == 99.0
    # _cell_modes manual/auto 用户态保留
    assert cash["_cell_modes"]["0"] == "manual"
    assert cash["_cell_modes"]["1"] == "auto"

    # ── 断言 c: row_type 完整保留（new 优先 + old 兜底） ────────────────
    assert bank["row_type"] == "data"
    assert cash["row_type"] == "data"
    total_row = merged["rows"][2]
    assert total_row["row_type"] == "total"
    assert total_row["is_total"] is True

    # ── 断言 d: 老前端 sidecar 兼容铁律 ───────────────────────────────
    # 新增的 _cell_meta / row_type 是字段，不是替换
    for r in merged["rows"]:
        assert "values" in r
        assert "label" in r
        assert "_cell_modes" in r  # 用户态保留

    # ── 断言 e: 入参纯函数性 — legacy / engine_new 都没被改 ───────────
    assert legacy == legacy_snapshot

    # 引擎新输出 deepcopy 在 merge 内部完成，原对象不应变
    # （这条不适用于 migrated，因为我们就是为了测它；但 engine_new 应不变）
    engine_snap = _new_engine_output()
    assert engine_new == engine_snap


def test_e2e_locked_cell_value_preserved_through_full_pipeline():
    """端到端 locked：用户锁定的列穿过迁移 + 合并仍保留旧值."""
    legacy = {
        "headers": ["项目", "期末余额"],
        "rows": [
            {
                "label": "已锁定行",
                "values": [777.0],
                "_cell_modes": {"0": "locked"},
                "is_total": False,
            },
        ],
    }

    migrated = deepcopy(legacy)
    upgrade_table_data(migrated)

    # locked 不触发 manual_value 备份
    assert migrated["rows"][0]["_cell_meta"]["0"]["manual_value"] is None

    engine_new = {
        "headers": ["项目", "期末余额"],
        "rows": [{"label": "已锁定行", "values": [99999.0], "row_type": "data"}],
    }
    merged = merge_table_data_preserving_cell_modes(migrated, engine_new)

    # locked → 保留 old.values；_cell_meta.manual_value 仍是 None
    assert merged["rows"][0]["values"] == [777.0]
    assert merged["rows"][0]["_cell_meta"]["0"]["manual_value"] is None


def test_e2e_double_migrate_idempotent_after_merge():
    """0.2 迁移幂等：合并产生的 td 再跑一次 upgrade_table_data 不重复添加."""
    legacy = _legacy_table_data()
    migrated = deepcopy(legacy)
    upgrade_table_data(migrated)
    engine_new = _new_engine_output()
    merged = merge_table_data_preserving_cell_modes(migrated, engine_new)

    # 第二次跑 0.2 升级
    snapshot = deepcopy(merged)
    stats2 = upgrade_table_data(merged)

    assert stats2["row_type_added"] == 0  # 全部已 tagged
    assert stats2["_cell_meta_added"] == 0
    assert merged == snapshot, "二次升级不应再修改"


def test_e2e_old_legacy_row_kept_via_legacy_marker():
    """端到端：old 含一行 new 不存在 → merged 末尾追加 + _legacy_row=True."""
    legacy = {
        "headers": ["项目", "期末余额"],
        "rows": [
            {
                "label": "标准行",
                "values": [100.0],
                "_cell_modes": {"0": "auto"},
                "is_total": False,
            },
            {
                "label": "用户自添加行",
                "values": [555.0],
                "_cell_modes": {"0": "manual"},
                "is_total": False,
            },
        ],
    }
    migrated = deepcopy(legacy)
    upgrade_table_data(migrated)

    # 模拟引擎不识别"用户自添加行"
    engine_new = {
        "headers": ["项目", "期末余额"],
        "rows": [{"label": "标准行", "values": [200.0], "row_type": "data"}],
    }
    merged = merge_table_data_preserving_cell_modes(migrated, engine_new)

    # 用户自添加行被保留并标记
    assert len(merged["rows"]) == 2
    user_row = next(r for r in merged["rows"] if r["label"] == "用户自添加行")
    assert user_row["_legacy_row"] is True
    # values 保留（manual mode）
    assert user_row["values"] == [555.0]
