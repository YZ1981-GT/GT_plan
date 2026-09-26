"""D2 store 值等价判据 —— 统一路径 OO→HTML 的 store 镜像唯一判据（G4-2 迁移宿主）。

═══ 为什么这个文件存在 ═══

这三条判据原先住在 `backend/tests/test_d2_sync_durable_gate.py` 里，而那个文件同时
覆盖已退役的 `/d2-sync/*` router。G4-2 删 router 时如果把整个文件一起删掉，
`d2_store_value_equivalence` 会**失去全部覆盖** —— 而它并不是 legacy：统一路径的
`oo_to_html` 经 `d2_bidirectional_bridge.merge_projection_into_store_rows()` 在用它
做 checklist store 镜像（G4-1 §9.6 的 `store_mirrored` / `marker_visible` 就靠它）。

═══ 它锁的是什么缺陷 ═══

2026-09-06 D2-2 浏览器实测：回写把每一格都写成旧值，报告仍显示「1260 行 / 40320
个字段」全量成功 —— 因为原实现无条件写入并恒返 ``True``，那个数字其实是「遍历了
多少格」。审计师因此分不清「Excel 的编辑真回写了」与「把一模一样的值重写一遍」。

判据全在**行为**上（该判等就判等、该计数就计数），不查字符串是否存在。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from app.services.workpaper_sync import d2_bidirectional_bridge as B
from app.services.workpaper_sync import pilot_d2_large_json as P
from app.services.workpaper_sync.d2_store_value_equivalence import (
    assign_store_value,
    same_store_value,
)


# ═══════════════════════════════════════════════════════════════════
# 1. same_store_value：什么算「真变化」
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("existing", "incoming", "same"),
    [
        # 类型差异不是变化：store 存 int，xlsx 读回 float
        (5200, 5200.0, True),
        (0, 0.0, True),
        # 空值家族互等
        (None, "", True),
        ("", None, True),
        (None, "   ", True),
        # 真变化
        (0, 13571.99, False),
        ("", "GTPROBE-A1", False),
        (5200, 5201, False),
        # bool 不与数值并入（业务上是不同字段语义：勾选 vs 金额）
        (True, 1, False),
        (False, 0, False),
        (True, True, True),
        (False, False, True),
        # 文本
        ("非关联方", "非关联方", True),
        ("非关联方", "关联方", False),
    ],
)
def test_same_store_value(existing: Any, incoming: Any, same: bool) -> None:
    assert same_store_value(existing, incoming) is same


def test_bridge_reexports_the_same_object_not_a_copy() -> None:
    """桥里的 `_same_store_value` 必须是**转发别名**，不是第二份实现。

    🔴 判据用 `is` 而不是行为等价：若有人在桥里另写一份同名函数，行为一时相同、
    日后必然漂移，而「两份判据」正是本 spec 反复踩到的漂移源。
    """
    assert B._same_store_value is same_store_value


# ═══════════════════════════════════════════════════════════════════
# 2. _assign_store_value：只在真变化时写
# ═══════════════════════════════════════════════════════════════════


def test_assign_store_value_only_counts_real_change() -> None:
    """同值重写必须返回 False —— 否则 `rows_changed` 恒等于全量，假成功。"""
    row: dict[str, Any] = {"postPayment": 0}
    assert B._assign_store_value(row, "post_payment", 0) is False
    assert B._assign_store_value(row, "post_payment", 0.0) is False
    assert B._assign_store_value(row, "post_payment", 88888.77) is True
    assert row["postPayment"] == 88888.77
    # 未在契约映射里的字段不写
    assert B._assign_store_value(row, "不存在的字段", 1) is False


def test_assign_store_value_nested_path() -> None:
    """嵌套 store_key（账龄分段）也要遵守「只在真变化时写」。"""
    row: dict[str, Any] = {}
    # 第一次写入嵌套路径 = 变化
    assert B._assign_store_value(row, "aging_prior_within1", 100) is True
    assert row["agingPrior"]["within1"] == 100
    # 同值重写 = 不变
    assert B._assign_store_value(row, "aging_prior_within1", 100) is False
    assert B._assign_store_value(row, "aging_prior_within1", 100.0) is False


def test_assign_store_value_path_comes_from_the_contract_map_only() -> None:
    """字段 → store 路径**只**取契约映射，桥里不得自造前缀表。

    `_FIELD_TO_STORE` 是唯一映射；未登记字段一律不写（返回 False），
    不得回退成「按 snake→camel 猜一个键」——那会写到没人读的键上。
    """
    assert B._FIELD_TO_STORE.get("post_payment") == "postPayment"
    assert B._FIELD_TO_STORE.get("aging_prior_within1") == "agingPrior/within1"
    row: dict[str, Any] = {}
    assert B._assign_store_value(row, "postPayment", 1) is False, "只认契约里的 field_id"
    assert row == {}, "未登记字段一格都不该写"


def test_assign_store_value_direct_form_matches_the_bridge_wrapper() -> None:
    """纯函数直调与桥的包装必须给出同一结论（桥只多做一次映射解析）。"""
    via_bridge: dict[str, Any] = {}
    direct: dict[str, Any] = {}
    assert B._assign_store_value(via_bridge, "post_payment", 12.5) is True
    assert assign_store_value(direct, "postPayment", 12.5) is True
    assert via_bridge == direct


# ═══════════════════════════════════════════════════════════════════
# 3. merge_projection_into_store_rows：统一路径真正消费上面两条判据的地方
# ═══════════════════════════════════════════════════════════════════


@dataclass
class _FakeFieldValue:
    row_key: str
    value: Any
    is_protected: bool = False


class _FakeProjection:
    """最小 projection 替身：只实现 `stable_keys()` / `get()` 两个被消费的成员。"""

    def __init__(self, items: dict[str, _FakeFieldValue]) -> None:
        self._items = items

    def stable_keys(self) -> tuple[str, ...]:
        return tuple(self._items)

    def get(self, key: str) -> _FakeFieldValue | None:
        return self._items.get(key)


def _projection(*triples: tuple[str, str, Any, bool]) -> _FakeProjection:
    return _FakeProjection(
        {f"{P.ROWS_TABLE_KEY}/{row}/{field}": _FakeFieldValue(row, value, protected) for row, field, value, protected in triples}
    )


def test_merge_counts_only_real_changes_not_visited_cells() -> None:
    """`applied` 必须只数真变化，`visited` 数遍历量 —— 两者压成一个就是那次假成功。"""
    base = [
        {P.ROW_IDENTITY_STORE_KEY: "r1", "postPayment": 5200},
        {P.ROW_IDENTITY_STORE_KEY: "r2", "postPayment": 0},
    ]
    # r1 写回同值（int 5200 vs float 5200.0）；r2 带回真新值
    proj = _projection(
        ("r1", "post_payment", 5200.0, False),
        ("r2", "post_payment", 13571.99, False),
    )
    rows, applied, visited, touched = B.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert visited == 2, "两格都被遍历"
    assert applied == 1, "只有 r2 真变了 —— 同值重写不得计入"
    assert touched == {"r2"}
    assert rows[0]["postPayment"] == 5200, "r1 保持原值，不被同值覆盖成 float"
    assert rows[1]["postPayment"] == 13571.99


def test_merge_skips_protected_cells_and_preserves_unmanaged_keys() -> None:
    """protected 格不回写；store 行里的非受管键不得因一次回写被丢掉。"""
    base = [{P.ROW_IDENTITY_STORE_KEY: "r1", "postPayment": 1, "uiOnlyFlag": True}]
    proj = _projection(("r1", "post_payment", 999, True))
    rows, applied, visited, touched = B.merge_projection_into_store_rows(
        projection=proj, base_rows=base
    )
    assert (applied, visited, touched) == (0, 0, set()), "protected 格连遍历计数都不进"
    assert rows[0]["postPayment"] == 1, "protected 格不得覆盖 store"
    assert rows[0]["uiOnlyFlag"] is True, "非受管键必须原样保留"


def test_merge_appends_rows_that_only_exist_on_the_excel_side() -> None:
    """OO 侧新增行要进 store（否则结构化视图永远看不到新增）。"""
    proj = _projection(("rNew", "post_payment", 7, False))
    rows, applied, _visited, touched = B.merge_projection_into_store_rows(
        projection=proj, base_rows=[]
    )
    assert applied == 1 and touched == {"rNew"}
    assert rows == [{P.ROW_IDENTITY_STORE_KEY: "rNew", "postPayment": 7}]


def _oo_to_html_tree():
    import ast
    import pathlib

    source = pathlib.Path(B.__file__).with_name("oo_to_html.py").read_bytes().decode("utf-8")
    return ast.parse(source)


def test_unified_oo_to_html_really_wires_the_merge_function() -> None:
    """反向锁：统一 `oo_to_html` 必须**真的接线**本模块，否则以上判据全是死代码。

    🔴 判据形态踩过一次坑（本文件首跑）：`oo_to_html` 不是直接
    ``bridge.merge_projection_into_store_rows(...)``，而是先
    ``merge_rows_fn = bridge.merge_projection_into_store_rows`` 再调 ``merge_rows_fn(...)``
    —— 只看 Call 节点的函数名会 ANCHOR-MISS，把「接线正常」误判成「没接线」。
    故判据拆成两半，两半都必须成立：
      ① 存在把 `*.merge_projection_into_store_rows` 绑到本地名的赋值（绑定在）；
      ② 那个本地名真的被当函数调用过（不是绑了没人用）。
    删掉任一半都会打红，这正是「additive 注入即死代码」的反向锁。

    🔴 **锚点随注册表化迁移**（spec d1-sync-row-table-engine-and-d1-coverage Task 13）：
    原实现是 9 分支 `elif adapter_id == …` 链里逐家写
    ``merge_rows_fn = bridge.merge_projection_into_store_rows``；现改为注册表查表 +
    ``getattr(bridge, plan.merge_rows_fn)``。判据**意图不变**（绑定在 + 真被调用），
    只把「绑定」的形态从 Attribute 访问扩展到 `getattr(bridge, plan.merge_rows_fn)`。
    """
    import ast

    tree = _oo_to_html_tree()
    bound_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        # 形态 ①（历史）：bridge.merge_projection_into_store_rows
        if isinstance(value, ast.Attribute) and value.attr == "merge_projection_into_store_rows":
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound_names.add(target.id)
        # 形态 ②（注册表化后）：getattr(bridge, plan.merge_rows_fn)
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "getattr"
            and len(value.args) >= 2
            and isinstance(value.args[1], ast.Attribute)
            and value.args[1].attr in {"merge_rows_fn", "merge_state_fn"}
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound_names.add(target.id)
    assert bound_names, (
        "统一 oo_to_html 里没有把 merge 函数绑成可调用值（既无 bridge.merge_projection_into_store_rows "
        "也无 getattr(bridge, plan.merge_rows_fn)）—— OO 编辑只会推进 content_version 而 checklist "
        "store 仍是旧值，§9.6 的 store_mirrored / marker_visible 会静默回归"
    )
    invoked = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert bound_names & invoked, (
        f"merge 函数被绑到 {sorted(bound_names)} 但没有任何一个被调用 —— 绑了没人用等于死代码"
    )


def test_d2_branch_of_the_store_mirror_binds_this_bridge() -> None:
    """`d2.receivable_detail` 必须绑**本**桥，不得错绑成别的 pilot 的同名函数。

    四个 pilot（d2 / h1 / g7 / b60）的桥都有同名 `merge_projection_into_store_rows`，
    只判「有人绑了同名函数」会被别家顶替 —— 那正是本 spec 反复踩到的
    「判据数的是不变量而不是会被改动的那一侧」。

    🔴 **锚点随注册表化迁移**（spec d1-sync-row-table-engine-and-d1-coverage Task 13）：
    原实现在 `oo_to_html` 里有 `elif adapter_id == "d2.receivable_detail"` 分支；现改为
    `store_item_registry.STORE_MERGE_REGISTRY` 查表。判据意图不变（D2 必须绑到
    `d2_bidirectional_bridge`、取本桥的 store item 与合并函数），锚点换成注册表 —— 那才是
    现在「会被改动的那一侧」。
    """
    import importlib

    from app.services.workpaper_sync.store_item_registry import (
        STORE_MERGE_REGISTRY,
        store_merge_plan_or_skip,
    )

    plan = STORE_MERGE_REGISTRY.get("d2.receivable_detail")
    assert plan is not None, "注册表里没有 `d2.receivable_detail` 的 store merge plan"
    assert plan.provider_module == "d2_bidirectional_bridge", (
        f"D2 绑到了 {plan.provider_module!r} 而不是本桥 d2_bidirectional_bridge —— "
        "四家同名函数，错绑不会报错但会写错 store"
    )
    # 三态入口必须真能解析出它（不被 looks_like_adapter_id 或 unavailable 挡掉）
    resolved = store_merge_plan_or_skip("d2.receivable_detail")
    assert resolved is plan, "store_merge_plan_or_skip 未能解析出 D2 的 plan"

    # 本桥必须真的提供 plan 声明的那两个符号（防「注册表写了名、provider 没这个符号」）
    bridge = importlib.import_module(f"app.services.workpaper_sync.{plan.provider_module}")
    assert hasattr(bridge, "STORE_ITEM_ID"), "本桥缺 STORE_ITEM_ID"
    assert hasattr(bridge, plan.merge_rows_fn), f"本桥缺 {plan.merge_rows_fn}"
    assert bridge.STORE_ITEM_ID == "D2-detail-rows"
