# -*- coding: utf-8 -*-
"""`check_row_table_formula_columns_consistency.py` 门禁自测（缺陷② 的防复发）。

spec: d1-sync-row-table-engine-and-d1-coverage · 2026-09-28 实测缺陷② 修复
Requirements 1.2 / 6.6 / 7.4

═══ 红→绿的归因链 ═══

2026-09-28 全量实测：D1 有 8 个受管区把「只在 footer 出现的 SUM 列」填进了 `formula_columns`，
导致 **14 个** `editable` 字段的整个数据区被 `merge._protection` 判 `read_only_masked_cell`
⇒ OO 侧改动写不回 store（需求 1.5 在后端不可达，与 D4-1 修前同型）。
修 8 个声明 → 既存全仓守卫 `test_masked_cell_protection_is_cell_level.py` 从 2 red 转全绿。
本卡点把这条钉死。

═══ 为什么规则是「交集为空」而不是「恰等于 mode=formula 列集」═══

更严的「恰等于」版本在本仓库会产生 **10 处假阳**：`TEMPLATE_ONLY_FORMULA_COLUMNS_*` 形态
（I1-2 / I2-2 / I3-2 / I4-2 / I5-2×2 / I6-2 / F3-6 / F5-1 / J1-6）把「模板有列、store 侧是
前端重算的派生值」的列只放进 `formula_columns` 而**不进 field_specs** —— 完全正当。
本文件用**双向变异**钉住这一点：坏样本必红（`test_mutation_*`）+ 干净样本必不红
（`test_template_only_formula_columns_is_not_flagged`）。只做单向会把干净域判成缺陷域。

覆盖：
  1. 全仓现状通过（新增违规 0）。
  2. 变异反证 A：editable 列进 formula_columns ⇒ 必报，且报出字段名。
  3. 变异反证 B（反向）：列不在 field_specs 的 TEMPLATE_ONLY 形态 ⇒ 必不报。
  4. D1 本轮修的 8 个受管区逐个断言已合规（正面钉子，防回退）。
  5. KNOWN_GAPS 白名单纪律：只含 E1-6 一条、每条有归属 lane、且**真的仍在违规**
     （失效条目必须被门禁自己报出来）。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CHECK_PATH = (
    _BACKEND / "scripts" / "check" / "check_row_table_formula_columns_consistency.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_row_table_formula_columns_consistency", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _spec_with(field_specs, formula_columns):
    """构造一个最小可用的 RowTableSheetSpec（只为喂 check_spec，几何取合法值）。"""
    from app.services.workpaper_sync.phase5_row_table_sheet import (
        RowTableSheetSpec,
        StoreKind,
    )

    return RowTableSheetSpec(
        managed_sheet="合成表X-1",
        sheet_key="x1-managed",
        table_key="synthetic_rows",
        template_id="X1",
        table_name="GT_X1_ROWS",
        uuid_col="Z",
        first_data_row=10,
        last_data_row=20,
        footer_row=21,
        store_item_id="X1-rows",
        empty_payload="[]",
        row_identity_key="rowId",
        store_kind=StoreKind.rows,
        field_specs=tuple(field_specs),
        formula_columns=tuple(formula_columns),
        footer_marker="合计",
        error_label="合成表",
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 现状
# ═══════════════════════════════════════════════════════════════════════════


def test_repo_wide_has_no_new_violation() -> None:
    report = _load_module().run()
    assert report["ok"], (
        f"新增违规 {len(report['violations'])} 处 / "
        f"失效白名单 {report['stale_known_gaps']}；明细={report['violations']}"
    )
    # 分母必须是真的扫到了东西 —— 防止 spec 收集器悄悄返回空集导致恒绿。
    assert report["scanned_specs"] >= 100, (
        f"只扫到 {report['scanned_specs']} 个 RowTableSheetSpec，"
        "收集器可能坏了（现算全仓应 ≥100）—— 恒绿风险"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2~3. 双向变异
# ═══════════════════════════════════════════════════════════════════════════


def test_mutation_editable_column_in_formula_columns_is_flagged() -> None:
    """变异 A：把 editable 列填进 formula_columns（D1 修前的错法）⇒ 必报。"""
    mod = _load_module()
    bad = _spec_with(
        field_specs=[
            ("amount", "E", "editable", "amount", "amount", "金额", ""),
            ("memo", "F", "editable", "text", "memo", "备注", ""),
        ],
        formula_columns=["E"],  # 只在 footer 有 SUM，却填进来了
    )
    hit = mod.check_spec(bad)
    assert hit is not None, "editable 列进 formula_columns 必须被检出"
    assert hit["masked_editable"] == ["E"]
    assert hit["masked_editable_fields"] == ["E:amount"], (
        "报告须给出字段名而不只是列字母，否则排查时还得自己去翻 field_specs"
    )


def test_template_only_formula_columns_is_not_flagged() -> None:
    """变异 B（反向）：列**不在** field_specs 的 TEMPLATE_ONLY 形态 ⇒ 必不报。

    这条是防「规则过严」的那一侧。实测 I1-2 等 10 个受管区正属此形态
    （`TEMPLATE_ONLY_FORMULA_COLUMNS_I102` 注释原文：模板有列、store 侧是前端重算的
    派生值 ⇒ 只进 FORMULA_MASK），若规则用「恰等于 mode=formula 列集」会把它们全判成缺陷。
    """
    mod = _load_module()
    ok = _spec_with(
        field_specs=[
            ("amount", "C", "editable", "amount", "amount", "金额", ""),
        ],
        formula_columns=["H", "L", "M"],  # 三列都不在 field_specs 里
    )
    assert mod.check_spec(ok) is None, (
        "TEMPLATE_ONLY 形态（列不在 field_specs）是合法的，不得报"
    )


def test_formula_mode_column_in_formula_columns_is_not_flagged() -> None:
    """mode=formula 的列进 formula_columns 是 CS-13 的**要求**，不得报。"""
    mod = _load_module()
    ok = _spec_with(
        field_specs=[
            ("amount", "C", "editable", "amount", "amount", "金额", ""),
            ("total", "E", "formula", "amount", "total", "合计", ""),
        ],
        formula_columns=["E"],
    )
    assert mod.check_spec(ok) is None


# ═══════════════════════════════════════════════════════════════════════════
# 4. D1 本轮修的 8 个受管区 —— 正面钉子
# ═══════════════════════════════════════════════════════════════════════════


_D1_FIXED_TABLE_KEYS = (
    "endorse_discount_rows",
    "endorse_transfer_rows",
    "writeoff_reversal_rows",
    "writeoff_writeoff_rows",
    "pledge_check_rows",
    "inventory_count_rows",
    "sampling_vouching_rows",
    "sampling_specific_samples",
)


@pytest.mark.parametrize("table_key", _D1_FIXED_TABLE_KEYS)
def test_d1_fixed_regions_have_empty_formula_columns(table_key: str) -> None:
    """这 8 个区数据区逐格实测零公式 ⇒ formula_columns 必须为空。

    它们的 footer SUM 公式文本保留在各模块的 `FOOTER_SUM_TEMPLATES_*` 常量里作实测证据
    （materialize 不覆盖公式格、由 OO 重算，故不需要进 spec）。
    """
    from app.services.workpaper_sync import phase5_d1_expansion as EXP

    spec = next(
        (s for s in EXP.managed_row_table_specs() if s.table_key == table_key), None
    )
    assert spec is not None, f"{table_key} 不在 D1 受管清单里 —— 灰度开关被关了？"
    assert spec.formula_columns == (), (
        f"{table_key} 的 formula_columns 应为空（数据区零公式），实得 {spec.formula_columns}"
    )
    assert _load_module().check_spec(spec) is None


def test_d1_footer_sum_templates_are_preserved_as_evidence() -> None:
    """footer SUM 公式文本不得在收敛 formula_columns 时被删掉（证据不丢）。"""
    from app.services.workpaper_sync import phase5_d1_08_endorsement as D108
    from app.services.workpaper_sync import phase5_d1_10_inventory as D110
    from app.services.workpaper_sync import phase5_d1_12_pledge as D112
    from app.services.workpaper_sync import phase5_d1_13_sampling as D113
    from app.services.workpaper_sync import phase5_d1_16_writeoff as D116

    assert set(D108.FOOTER_SUM_TEMPLATES_DISCOUNT) == {"E", "F", "L", "M"}
    assert set(D108.FOOTER_SUM_TEMPLATES_TRANSFER) == {"E"}
    assert set(D116.FOOTER_SUM_TEMPLATES_REVERSAL) == {"E", "F"}
    assert set(D116.FOOTER_SUM_TEMPLATES_WRITEOFF) == {"C"}
    assert set(D112.FOOTER_SUM_TEMPLATES_D112) == {"H", "J"}
    assert set(D110.FOOTER_SUM_TEMPLATES_D110) == {"H"}
    assert set(D113.FOOTER_SUM_TEMPLATES_VOUCHING) == {"G", "H"}
    assert set(D113.FOOTER_SUM_TEMPLATES_SPECIFIC) == {"G"}
    # 占位符必须是 {last}（= last_data_row），不是数据区公式那套 {r}（= 逐行行号）——
    # 混用这两个占位符正是这次缺陷的概念根源。
    for tpl in (
        *D108.FOOTER_SUM_TEMPLATES_DISCOUNT.values(),
        *D116.FOOTER_SUM_TEMPLATES_REVERSAL.values(),
        *D113.FOOTER_SUM_TEMPLATES_VOUCHING.values(),
    ):
        assert "{last}" in tpl and "{r}" not in tpl, f"占位符用错：{tpl!r}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 白名单纪律
# ═══════════════════════════════════════════════════════════════════════════


def test_known_gaps_is_exactly_the_registered_one() -> None:
    """白名单只许有 E1-6 这一条；新增须同时改脚本与本判据（防顺手放行）。"""
    mod = _load_module()
    assert set(mod.KNOWN_GAPS) == {
        ("银行存款余额调节表E1-6", "reconciliation_rows"),
    }, f"白名单变了：{sorted(mod.KNOWN_GAPS)}"


def test_every_known_gap_states_its_owning_lane() -> None:
    """白名单每条必须写明归属 lane —— 没 owner 的缺口会永远躺着。"""
    mod = _load_module()
    for key, reason in mod.KNOWN_GAPS.items():
        assert "归属 lane" in reason, f"{key} 未写归属 lane"
        assert len(reason) > 80, f"{key} 的理由过短，说不清为什么本 spec 不修"


def test_stale_known_gap_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """反向断言：白名单里放一条**已合规**的条目 ⇒ 门禁必红并点名它失效。

    没有这条，白名单会变成「越积越长、没人敢删」的黑洞（需求㉕③ 的名单失效检查）。
    """
    mod = _load_module()
    monkeypatch.setitem(
        mod.KNOWN_GAPS, ("原值明细表（按客户）D1-3", "notes_receivable_detail_rows"), "归属 lane：合成的失效条目，用于反证。" + "x" * 80
    )
    report = mod.run()
    assert not report["ok"], "白名单含失效条目时门禁必须红"
    assert any("D1-3" in s for s in report["stale_known_gaps"]), report["stale_known_gaps"]


def test_registered_gap_is_still_really_violating() -> None:
    """E1-6 必须**真的仍在违规** —— 若它已被 E1 lane 修好，白名单该删。

    🔴 「已修好」与「本检出里没有这个受管区」必须分开（2026-09-28 实测）：
    E1-6 的 provider `phase5_e1_06_reconciliation.py` 是别 lane **尚未入库**的文件。
    开发者工作树上它在且仍违规（登记正确）；纯 HEAD 检出上它不存在，门把它归入
    `absent_known_gaps`。此时要求删白名单是错的 —— 删完等那条 lane 入库就成漏报。
    """
    key = ("银行存款余额调节表E1-6", "reconciliation_rows")
    report = _load_module().run()
    hit_keys = {(v["managed_sheet"], v["table_key"]) for v in report["known_gaps_hit"]}
    if key in hit_keys:
        return
    absent = set(report.get("absent_known_gaps") or ())
    if f"{key[0]} / {key[1]}" in absent:
        pytest.skip(
            "E1-6 的 provider 模块不在本检出（CI 上正常）—— 本条只在开发者工作树上"
            "有判定力；门已把它归入 absent_known_gaps 而不是判红"
        )
    raise AssertionError(
        "E1-6 已合规 ⇒ 请从 KNOWN_GAPS 删除该条（本判据同时保证白名单不含失效项）"
    )


def test_absent_gap_is_not_reported_as_stale() -> None:
    """门必须把 `absent_known_gaps` 与 `stale_known_gaps` 分开，且 absent 不判红。

    没有这条分离，纯 HEAD 检出会要求删掉一批**仍然有效**的登记。
    """
    report = _load_module().run()
    assert "absent_known_gaps" in report, "报告缺少 absent_known_gaps 分类"
    overlap = set(report["absent_known_gaps"]) & set(report["stale_known_gaps"])
    assert not overlap, f"同一条目同时被判 absent 与 stale：{sorted(overlap)}"
    if report["absent_known_gaps"] and not report["violations"]:
        assert report["ok"], (
            "仅有 absent 条目时不得判红 —— 那是别 lane 未入库，不是本门的缺陷："
            f"{report['absent_known_gaps']}"
        )
