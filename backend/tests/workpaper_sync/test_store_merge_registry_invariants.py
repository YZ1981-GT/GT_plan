"""store 合并注册表的声明级不变量。

本文件钉住三类「声明与实际执行路径不一致」的缺陷 —— 它们都不会让任何现有测试变红，
只会在运行时静默吞掉数据或为永不执行的声明回滚整笔业务提交。

Spec: workpaper-writeback-data-loss-and-mirror-consistency-closure，design §8 残留 1 / 残留 2。
"""
from __future__ import annotations

import importlib
import inspect
import re

import pytest

from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY


def _bridge(plan):
    return importlib.import_module(f"app.services.workpaper_sync.{plan.provider_module}")


def _declared_store_ids(plan) -> tuple[str, ...]:
    bridge = _bridge(plan)
    all_ids_fn = getattr(bridge, "all_store_item_ids", None)
    if callable(all_ids_fn):
        return tuple(all_ids_fn())
    single = getattr(bridge, "STORE_ITEM_ID", None)
    ids = tuple(getattr(bridge, "STORE_ITEM_IDS", ()) or ())
    return ids or ((single,) if isinstance(single, str) else ())


def test_registry_is_not_empty_so_the_invariants_below_have_a_denominator() -> None:
    """分母保护：注册表塌成空时，下面三条会全部空转变绿。"""
    assert len(STORE_MERGE_REGISTRY) >= 50, len(STORE_MERGE_REGISTRY)
    assert any(plan.dedicated_items for plan in STORE_MERGE_REGISTRY.values())
    assert any(plan.merge_state_fn for plan in STORE_MERGE_REGISTRY.values())


def test_dedicated_items_implies_dual_store_fn() -> None:
    """`dedicated_items` 只被 `_mirror_dual_stores` 消费 —— 没有 `dual_store_fn` 就永不执行。

    但 `_resolve_dedicated_store_providers` 每次镜像都会校验它，而镜像跑在 `_commit_once` 内，
    所以这种声明会让「重命名一个永不被调用的函数」回滚整笔 OO→HTML 业务提交
    （K1-9 曾是全仓唯一一条）。
    """
    offenders = sorted(
        adapter_id
        for adapter_id, plan in STORE_MERGE_REGISTRY.items()
        if plan.dedicated_items and not plan.dual_store_fn
    )
    assert offenders == []


def test_every_dedicated_item_id_is_in_the_adapters_declared_store_ids() -> None:
    """dedicated 侧绕过了 `_INCLUDE_D4xx_*` 闸住的别名，必须靠这条不变量兜住。

    `_resolve_dedicated_store_providers` 直接从 owning module 取 `item_id_const`，
    不经过 bridge 侧条件导出的 `*_DICT` 别名；flag 翻 False 后 `STORE_ITEM_IDS` 会排除该 item
    而 dedicated 镜像照跑 ⇒ 两边口径分叉。这条让分叉当场打红而不是静默发生。
    """
    checked = 0
    offenders: list[str] = []
    for adapter_id, plan in sorted(STORE_MERGE_REGISTRY.items()):
        if not plan.dedicated_items:
            continue
        declared = set(_declared_store_ids(plan))
        for dedicated in plan.dedicated_items:
            module = importlib.import_module(
                f"app.services.workpaper_sync.{dedicated.provider_module}"
            )
            item_id = getattr(module, dedicated.item_id_const, None)
            checked += 1
            if item_id not in declared:
                offenders.append(f"{adapter_id}.{dedicated.item_id_const}={item_id!r}")
    assert checked >= 6, f"dedicated item 分母塌了：{checked}"
    assert offenders == []


# 单 store 的 rows 分支解码 base 时是 `if isinstance(parsed, list)`：dict 基线会留在 `[]`，
# 于是每次镜像把既有行与未受管标量整体清空重建。dict 形态必须走 state 分支。
_DICT_BASE_MARKERS = (
    "isinstance(base_state, Mapping)",
    "isinstance(base_rows, Mapping)",
    "dict(base_state)",
    "dict(base_rows)",
    "base_state=base_rows",
)


def test_dict_shaped_merges_are_not_wired_to_the_rows_branch() -> None:
    offenders: list[str] = []
    checked = 0
    for adapter_id, plan in sorted(STORE_MERGE_REGISTRY.items()):
        if plan.dual_store_fn or plan.merge_state_fn:
            continue
        bridge = _bridge(plan)
        # 🔴 必须按运行期属性解析：多个 provider 共用同一个 merge 函数、按 import 暴露，
        #    只扫模块级 `def` 会把 20 个判成「找不到」（第一版探针即如此误报）。
        fn = getattr(bridge, plan.merge_rows_fn, None)
        assert callable(fn), f"{adapter_id}: {plan.provider_module}.{plan.merge_rows_fn} 不可调用"
        source = inspect.getsource(fn)
        checked += 1
        hits = [m for m in _DICT_BASE_MARKERS if m in source]
        dict_delegate = [
            name for name in re.findall(r"return\s+(merge_[a-z0-9_]+)\(", source)
            if "rows" not in name
        ]
        if hits or dict_delegate:
            offenders.append(f"{adapter_id}（dict 迹象={hits} 委派={dict_delegate}）")
    assert checked >= 60, f"rows 分支分母塌了：{checked}"
    assert offenders == []


def test_k1_is_on_the_state_branch_and_its_merge_returns_the_state_tuple() -> None:
    """K1-9 的正向判据：载荷是 dict，必须走 state 分支，且 merge 返回 3 元组。"""
    plan = STORE_MERGE_REGISTRY["k1.baddebt_reversal_writeoff_check"]
    assert plan.merge_state_fn == "merge_k1_from_projection"
    assert plan.dedicated_items == ()
    assert plan.dual_store_fn is None

    bridge = _bridge(plan)
    merged, applied, visited = bridge.merge_k1_from_projection(
        projection=_EmptyProjection(), base_state={"note": "未受管标量", "tables": {}},
    )
    assert (applied, visited) == (0, 0)
    assert merged["note"] == "未受管标量", "state 分支必须保留未受管标量"


class _EmptyProjection:
    def stable_keys(self):
        return ()

    def get(self, _key):  # pragma: no cover - 空投影不会被取值
        return None


@pytest.mark.parametrize(
    "base_state, expected_rows",
    [
        ({"tables": {"reversal": [{"id": "r1", "a": "1"}], "writeoff": []}}, 1),
        ({"note": "x", "tables": {"reversal": [], "writeoff": [{"id": "w1"}]}}, 0),
    ],
)
def test_k1_merge_preserves_existing_rows_with_an_empty_projection(
    base_state: dict, expected_rows: int
) -> None:
    """空投影不得清空既有行 —— 这正是 rows 分支把 dict 基线降成 `[]` 时丢掉的东西。"""
    bridge = _bridge(STORE_MERGE_REGISTRY["k1.baddebt_reversal_writeoff_check"])
    merged, applied, _visited = bridge.merge_k1_from_projection(
        projection=_EmptyProjection(), base_state=base_state,
    )
    assert applied == 0
    assert len(merged["tables"]["reversal"]) == expected_rows
    for key, value in base_state.items():
        if key != "tables":
            assert merged[key] == value


# ─── 锁 helper 的往返次数与死锁安全（design §8 残留 3） ───────────────────────


class _FakeDialect:
    name = "postgresql"


class _FakeBind:
    dialect = _FakeDialect()


class _RecordingSession:
    """只记 SQL，不连库：验证往返形态（advisory 逐条、FOR UPDATE 合并一条）。"""

    def __init__(self) -> None:
        self.statements: list[str] = []
        self.params: list[dict] = []

    def get_bind(self):
        return _FakeBind()

    async def execute(self, statement, params=None):  # noqa: ANN001
        self.statements.append(" ".join(str(statement).split()))
        self.params.append(dict(params or {}))
        return None


@pytest.mark.asyncio
async def test_lock_helper_batches_for_update_but_keeps_advisory_per_item() -> None:
    """46 个 item 应是 46 条 advisory + 1 条 FOR UPDATE，而不是 92 条。

    advisory 必须逐条：死锁安全依赖「两条路径都按 item_id 升序逐个取锁」，
    而单条语句里对集合的函数求值顺序 PG 不保证 —— 合并会把往返换成偶发死锁。
    """
    from app.services.checklist_response_cas import acquire_checklist_response_write_locks

    session = _RecordingSession()
    item_ids = [f"D4-{i}-data" for i in range(46)]
    returned = await acquire_checklist_response_write_locks(session, "wp-1", item_ids)

    advisory = [s for s in session.statements if "pg_advisory_xact_lock" in s]
    for_update = [s for s in session.statements if "FOR UPDATE" in s]
    assert len(advisory) == 46, session.statements
    assert len(for_update) == 1, for_update
    assert "item_id = ANY(:item_ids)" in for_update[0]
    assert len(session.statements) == 47

    # 取锁顺序必须是 item_id 升序（去重后）。
    # 🔴 不能按 lock_key 字符串排序断言：key 形如
    # `checklist_response:{wp}:{len(item_id)}:{item_id}`，那个长度前缀是为了避免
    # 「a:b」与「a」+「:b」撞成同一把键，它会让 key 的字典序与 item_id 的字典序不同
    # （'…:9:D4-0-data' < '…:10:D4-10-data' 在 item_id 维度成立、在 key 维度不成立）。
    keys = [p["lock_key"] for p in session.params if "lock_key" in p]
    locked_item_ids = [key.split(":", 3)[3] for key in keys]
    assert locked_item_ids == sorted(set(item_ids))
    assert returned == tuple(sorted(set(item_ids)))


@pytest.mark.asyncio
async def test_lock_helper_emits_no_sql_for_empty_item_ids() -> None:
    from app.services.checklist_response_cas import acquire_checklist_response_write_locks

    session = _RecordingSession()
    assert await acquire_checklist_response_write_locks(session, "wp-1", []) == ()
    assert session.statements == []
