"""D2-3 引用复用真实嵌套树，参与汇总的 NULL 不得伪装成零。"""
from decimal import Decimal
from uuid import uuid4

import pytest

from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.services.formula_engine import FormulaEvalError, WPExecutor
from tests.formula_integrity_support import add_wp
from tests.formula_integrity_support import integrity_world as integrity_world

SHEET = "坏账准备明细表D2-3"


async def parent(world, index, label="按单项评估计提", method=ProvisionMethod.INDIVIDUAL, **amounts):
    row = BadDebtDetailRow(id=uuid4(), wp_index_id=index.id, row_label=label,
                           provision_method=method.value, **amounts)
    world.db.add(row)
    await world.db.flush()
    return row


async def child(world, index, parent_id, label="明细", **amounts):
    row = BadDebtDetailRow(id=uuid4(), wp_index_id=index.id, parent_row_id=parent_id,
                           row_label=label, **amounts)
    world.db.add(row)
    await world.db.flush()
    return row


@pytest.mark.parametrize("value", [Decimal(0), Decimal("7.25")])
async def test_formula_integrity_d23_real_summary_and_parent_field(integrity_world, value):
    world = integrity_world
    index, _ = await add_wp(world, "D2", {})
    await parent(world, index, amount_f=value, amount_n=value)
    for field in ("本期计提合计", "单项评估计提.期末审定数"):
        actual = await WPExecutor.execute(world.db, world.project.id, "D2", SHEET, field, year=2025)
        assert actual == value


async def test_formula_integrity_d23_uses_child_sum_not_stored_parent(integrity_world):
    world = integrity_world
    index, _ = await add_wp(world, "D2", {})
    head = await parent(world, index, amount_f=Decimal("999"))
    await child(world, index, head.id, "甲", amount_f=Decimal("2.50"))
    await child(world, index, head.id, "乙", amount_f=Decimal("3.25"))
    await parent(world, index, label="其他", method=ProvisionMethod.OTHER, amount_f=Decimal("4"))
    total = await WPExecutor.execute(world.db, world.project.id, "D2", SHEET, "本期计提合计", year=2025)
    individual = await WPExecutor.execute(world.db, world.project.id, "D2", SHEET,
                                          "单项评估计提.本期计提", year=2025)
    assert total == Decimal("9.75")
    assert individual == Decimal("5.75")


@pytest.mark.parametrize("shape", ["parent", "child", "one_child_null"])
async def test_formula_integrity_d23_null_participant_must_fail(integrity_world, shape):
    world = integrity_world
    index, _ = await add_wp(world, "D2", {})
    head = await parent(world, index, amount_f=None if shape == "parent" else Decimal("99"))
    if shape != "parent":
        await child(world, index, head.id, "空数", amount_f=None)
    if shape == "one_child_null":
        await child(world, index, head.id, "有效数", amount_f=Decimal("17"))
    with pytest.raises(FormulaEvalError, match="来源数值为空"):
        await WPExecutor.execute(world.db, world.project.id, "D2", SHEET, "本期计提合计", year=2025)


@pytest.mark.parametrize("shape,reason", [
    ("missing", "底稿不存在"), ("other_code", "底稿不存在"),
    ("other_project", "底稿不存在"), ("deleted", "底稿不存在"),
    ("no_parent", "未录入坏账准备父行"), ("unknown_field", "未知或缺少金额字段"),
    ("parent_missing", "未找到引用父行"), ("ambiguous", "父行匹配存在歧义"),
    ("orphan", "明细行缺少所属父行"),
])
async def test_formula_integrity_d23_missing_or_ambiguous_never_chooses_first(integrity_world, shape, reason):
    world = integrity_world
    field = "本期计提合计"
    if shape != "missing":
        index, _ = await add_wp(world, "D3" if shape == "other_code" else "D2", {},
                                 project=world.other if shape == "other_project" else world.project,
                                 index_deleted=shape == "deleted")
        if shape not in ("no_parent",):
            await parent(world, index, label="组合甲", amount_f=Decimal("3"))
        if shape == "ambiguous":
            await parent(world, index, label="组合乙", method=ProvisionMethod.OTHER, amount_f=Decimal("5"))
            field = "组合.本期计提"
        if shape == "orphan":
            await child(world, index, uuid4(), amount_f=Decimal("9"))
    if shape == "unknown_field":
        field = "凭空猜的金额"
    if shape == "parent_missing":
        field = "不存在类别.本期计提"
    with pytest.raises(FormulaEvalError, match=reason):
        await WPExecutor.execute(world.db, world.project.id, "D2", SHEET, field, year=2025)
