"""能力解析器自测（advanced-query-linkage-closure 阶段 0；取代 `gold.py` 的固定项目 UUID）。

本文件回答两个问题，缺一个都会让「按能力动态选项目」变成看不见的空转：

1. **每条已登记的能力现在都能在共享库里解析出项目吗**？解析不出就当场失败并打印库内分布 ——
   这正是写死 UUID 时缺失的那一环（UUID 失效时用例只会拿空集跟空金标准互相印证）。
2. **解析是确定性的吗**？同一个库上连续解析必须给出同一个项目，否则用例会在"碰巧选了另一个"
   时表现不一致，复盘时无从归因。

另有两条反向断言，防判据空转：
- 能力目录里的每条都必须被本文件解析过（新增能力忘了登记会被抓到）；
- 一条**故意不可满足**的能力必须失败，证明 `resolve` 真的会报错而不是返回兜底值。
"""
from __future__ import annotations

import pytest

from tests.advanced_query_linkage.project_picks import CAPABILITIES, Capability, PickResolver

pytestmark = pytest.mark.pg_only


@pytest.mark.parametrize("capability", sorted(CAPABILITIES))
async def test_every_capability_resolves_to_a_live_project(picks: PickResolver, capability: str) -> None:
    pick = await picks.resolve(capability)
    cap = CAPABILITIES[capability]
    assert pick.metric > cap.require_gt, (pick, cap.require_gt)
    assert pick.name, pick
    # 解析结果打进报告，便于「这条用例这次落在哪个项目上」可追溯
    print(f"[pick] {capability} -> {pick}")


@pytest.mark.parametrize("capability", sorted(CAPABILITIES))
async def test_resolution_is_deterministic(picks: PickResolver, capability: str) -> None:
    """同库连续两次解析必须同一个项目（第二次走缓存，这里额外用一个新解析器绕过缓存）。"""
    first = await picks.resolve(capability)
    fresh = PickResolver(picks._engine)  # noqa: SLF001 —— 刻意绕过缓存，验的是 SQL 的确定性
    second = await fresh.resolve(capability)
    assert (first.id, first.audit_year) == (second.id, second.audit_year), (first, second)


async def test_unsatisfiable_capability_fails_loudly(picks: PickResolver) -> None:
    """反向断言：判据不可满足时必须失败（而不是返回兜底项目或空值）。

    这条用例是整个设计的安全阀 —— 如果 `resolve` 在无候选时静默返回点什么，
    上面那些「每条能力都能解析」就会在数据消失后继续全绿。
    """
    CAPABILITIES["__unsatisfiable_probe__"] = Capability(
        name="__unsatisfiable_probe__",
        description="故意不可满足：要求试算表行数 > 10 亿",
        metric_sql=(
            "SELECT count(*) FROM trial_balance t WHERE t.project_id = l.id AND NOT t.is_deleted"
        ),
        require_gt=1_000_000_000,
    )
    try:
        # 🔴 `pytest.fail` 抛的是 `Failed`，它继承 BaseException 而**不是** Exception ——
        # 写 `pytest.raises(Exception)` 抓不到，这条用例会以「失败」而不是「通过」告终。
        with pytest.raises(pytest.fail.Exception) as excinfo:
            await picks.resolve("__unsatisfiable_probe__")
        message = str(excinfo.value)
        assert "没有项目满足能力" in message, message
        assert "不要把这条用例改成跳过" in message, message
        assert "库内度量前 8 名" in message, message
    finally:
        CAPABILITIES.pop("__unsatisfiable_probe__", None)


def test_capability_catalog_is_fully_exercised() -> None:
    """反向断言：目录里的每条能力都被上面两个参数化用例覆盖（新增能力不会悄悄没人解析）。"""
    # 参数化直接取自 sorted(CAPABILITIES)，所以这里要验的是「目录非空且没有只声明不解析的占位」
    assert CAPABILITIES, "能力目录为空 ⇒ 上面的参数化用例会 0 例，判据空转"
    for name, cap in CAPABILITIES.items():
        assert name == cap.name, f"目录键 {name!r} 与 Capability.name {cap.name!r} 不一致"
        assert cap.description.strip(), f"{name} 缺判据说明（失败信息要靠它指路）"
        assert "l.id" in cap.metric_sql, f"{name} 的度量 SQL 没有按项目相关（缺 l.id）"
