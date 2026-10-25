"""Task 6.4 / 6.5 判据：`changed_item_count` 的来源 · 审计 details 追加字段 · 回滚快照完整性。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 1.8 / 3.6 / 6.7 / 6.9

| 节 | 判据 | 要害 |
| --- | --- | --- |
| §1 | `changed_item_count` 的来源（AST 源码锁，5 条子判据） | 实参必须是 `applied.plan`，不是 merge 前那份 |
| §2 | `changed_items_from_plan` 的口径（含**幽灵行计入**裁定） | 读裸 `rows_added`，不是 `added − ghost` |
| §3 | 新旧两口径**逐值对照**（5 场景，其中 2 场景不等） | 不等的那两处才说明换来源换掉了什么 |
| §4 | 审计 details 追加三字段 + `event_type` **不**登记 schema | details 是真经 `append_audit_log` 组装出来的 |
| §5 | 回滚快照覆盖面 = 两口径并集（Requirement 6.9） | 漏掉被跳过的 item ⇒ 它的原值再也拿不回来 |
| §6 | 四个新纯函数不碰 session / 不改入参 / 可 JSON 序列化 | —— |

🔴 **本文件是 §9 那条最后棘轮的改写落点**（`test_aos_adopt_plan_gates_and_wire_form.py` §9 末尾
留了指针）。原棘轮 `test_changed_item_count_comes_from_the_plan` 断言的是
`"_diff_snapshots" not in inspect.getsource(...)`：
* 6.4 落地会让它 **XPASS**，而 `strict=True` 使 XPASS 打红 ⇒ 必须摘掉；
* 与它成对的现状登记 `test_changed_item_count_still_comes_from_the_snapshot_diff`
  （断言 `changed = _diff_snapshots(...)` 在场）同时变成**假** ⇒ 必须一起改写。
两条改写后合起来回答「`changed_item_count` 到底从哪来」：§1 的 `judge_changed_item_count_source`
正面钉死来源是 plan，`test_the_snapshot_diff_only_feeds_the_rollback_coverage` 钉死
`_diff_snapshots` **仍在场但只喂回滚覆盖面**。🔴 **没有弱化**：原写法连「实参是哪份 plan」都表达
不了，而喂错 plan（merge 前那份）会让幽灵回喂的结果整个丢掉。

🔴 **判据一律 AST，禁文本 `in`**（平台铁律 ㉖）：文本匹配两向都会骗人 —— docstring / `#` 注释里
提一句 `_diff_snapshots` 就让「已改完」判成没改完（假阴，原棘轮正是这个形态），把调用点挪到
注释提及处之外又能让「没改」蒙过（假阳）。AST 里 docstring 是 `Expr(Constant)` 不产生 `Name`、
`#` 注释根本不进树 ⇒ 两向天然排除。

🔴 **变异一律进程内**：函数级用共用工具 `_source_mutant`（`inspect.getsource` → 换**唯一**锚点 →
在生产模块 `globals` 的**副本**里 `exec`）；AST 类判据用 `_mutated_fn_ast`（同样的唯一锚点纪律，
但只 `ast.parse` 不 `exec`）。生产文件一字不改，也**不用** `monkeypatch.setattr` —— 本域有并发
会话，窗口期内改共用模块的行为是真实风险。

🔴 **工具与桩从 `test_aos_adopt_plan_wiring.py` import，不另造第二份**，且用**顶层模块名** ——
该目录无 `__init__.py`，pytest 走 `prepend`；写成 `tests.workpaper_sync.…` 会拿到第二个模块实例。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import uuid
from typing import Any, Mapping

import pytest

from app.services import audit_log_helper as ALH
from app.services.workpaper_sync import adopt_overwrite_apply as AOA
from app.services.workpaper_sync import adopt_substrate_response as ASR
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlan,
    SkipReason,
)

from test_aos_adopt_plan_wiring import (  # noqa: E402
    _IDENTITY_KEY,
    _StubReader,
    _callee_name,
    _calls_named,
    _func_ast,
    _projection,
    _source_mutant,
    _stmt_index,
)

#: 被测函数名（AST 源码锁的宿主）与本任务新增的四个纯函数名。
_HOST = "compute_adopt_substrate"
_PLAN_CHANGED = "changed_items_from_plan"
_ROLLBACK_ITEMS = "rollback_snapshot_items"
_SNAPSHOT_DIFF = "_diff_snapshots"
_AUDIT_DETAILS = "audit_details_for_applied"
_RECORD = "_record_rollback_and_audit"
_NEW_PURE = (_PLAN_CHANGED, _ROLLBACK_ITEMS, "skipped_items_wire", _AUDIT_DETAILS)

#: `event_type` 沿用值（design § Data Models：**有意**不进 `EVENT_TYPE_SCHEMAS`）。
_EVENT_TYPE = "workpaper_sync_adopt_substrate"

ITEM = "AOS65-rows"
TABLE = "aos65_rows"
#: 🔴 行身份键从共用工具箱取（`_StubReader` 认的就是它）—— 本文件不另写一份字面量。
IDENTITY = _IDENTITY_KEY


# ═══════════════════════════════════════════════════════════════════════════════
# 工具：AST 级变异（唯一锚点 + 只 parse 不 exec）与计划建造器
# ═══════════════════════════════════════════════════════════════════════════════


def _mutated_fn_ast(func: Any, *, old: str, new: str) -> Any:
    """按**唯一**锚点改源码后重新 `ast.parse`，返回变异体的 `FunctionDef`。

    🔴 与 `_source_mutant` 同一条锚点纪律（命中须恰 1）—— 命中 0 次时 `str.replace` 静默变成
    空操作，变异体等于生产实现，红一次都打不出还全绿。
    🔴 只 parse 不 exec：本组判据全部是「源码结构」判据，exec 反而会把 import 副作用带进来。
    """
    src = inspect.getsource(func)
    hits = src.count(old)
    assert hits == 1, f"锚点 {old!r} 在 {func.__name__} 源码里命中 {hits} 次（须恰 1）"
    for node in ast.walk(ast.parse(src.replace(old, new))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func.__name__:
            return node
    raise AssertionError(f"变异后的源码里找不到 {func.__name__}")


def _delta(
    *,
    item_id: str = ITEM,
    table_key: str | None = TABLE,
    added: tuple[str, ...] = (),
    deleted: tuple[str, ...] = (),
    updated: tuple[str, ...] = (),
    ghost: tuple[str, ...] = (),
    section: str | None = None,
    reason: SkipReason | None = None,
) -> ItemOverwriteDelta:
    return ItemOverwriteDelta(
        item_id=item_id,
        table_key=table_key,
        row_section=section,
        rows_added=added,
        rows_deleted=deleted,
        rows_updated=updated,
        rows_ghost_dropped=ghost,
        skipped_reason=reason,
    )


def _plan(*deltas: ItemOverwriteDelta) -> OverwritePlan:
    return OverwritePlan(
        deltas=deltas,
        store_rows_by_table={TABLE: 1},
        substrate_rows_by_table={TABLE: 1},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# §1 `changed_item_count` 的来源（AST 源码锁）—— 原棘轮的改写落点（Requirement 3.6）
# ═══════════════════════════════════════════════════════════════════════════════


def _assigned_from(body: list[Any], callee: str) -> tuple[str, list[ast.Call]]:
    """`<name> = <callee>(...)` 的目标名与该 callee 的全部调用点（含嵌套）。"""
    calls = [c for stmt in body for c in _calls_named(stmt, callee)]
    names = [
        target.id
        for stmt in ast.walk(ast.Module(body=body, type_ignores=[]))
        if isinstance(stmt, ast.Assign) and _calls_named(stmt, callee)
        for target in stmt.targets
        if isinstance(target, ast.Name)
    ]
    return (names[0] if len(names) == 1 else ""), calls


def _dict_of_final_return(fn: Any) -> dict[str, Any]:
    """**真实执行**分支那个 `return {...}` 的键 → 值节点。

    🔴 定位方式 = `fn.body` 的**顶层** `Return` —— dry_run 那个 return 嵌在 `if dry_run:` 里，
    天然不在顶层；靠这条结构性事实区分两个 return，不数行号也不认注释。
    """
    returns = [s for s in fn.body if isinstance(s, ast.Return)]
    assert len(returns) == 1, f"顶层 return 应恰 1 个（真实执行分支），实得 {len(returns)}"
    node = returns[0].value
    assert isinstance(node, ast.Dict), "真实执行分支的返回值不是字面 dict"
    return {
        key.value: value
        for key, value in zip(node.keys, node.values)
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }


def judge_changed_item_count_source(fn: Any) -> list[str]:
    """五条子判据（返回违规清单，空 = 合规）。**纯函数**，变异可直接喂变异后的 AST。"""
    violations: list[str] = []
    try_at = _stmt_index(fn.body, lambda s: isinstance(s, ast.Try))
    body = fn.body[try_at].body if try_at >= 0 else []
    if try_at < 0:
        return ["定位失败：宿主里没有 try 块"]

    # 子判据 1 —— `changed` 由 plan 供出，且只有这一处算它
    plan_var, plan_calls = _assigned_from(body, _PLAN_CHANGED)
    if len(plan_calls) != 1 or not plan_var:
        violations.append(
            f"{_PLAN_CHANGED} 的调用点 {len(plan_calls)} 处 / 赋值目标 {plan_var!r}"
            "（须恰 1 处且赋给一个变量）"
        )
    # 子判据 2 —— 实参必须是 `applied.plan`（幽灵回喂之后那份），不是 merge 前的 `plan`
    if plan_calls:
        args = plan_calls[0].args
        got = ast.dump(args[0]) if args else "<无实参>"
        if not (
            len(args) == 1
            and isinstance(args[0], ast.Attribute)
            and args[0].attr == "plan"
            and isinstance(args[0].value, ast.Name)
            and args[0].value.id == "applied"
        ):
            violations.append(
                f"{_PLAN_CHANGED} 的实参不是 `applied.plan`（实得 {got}）—— merge 前那份 `plan` "
                "里 `rows_ghost_dropped` 恒空，喂它等于把幽灵回喂的结果整个丢掉"
            )
    # 子判据 3 —— 响应体的两个字段都取自同一个变量
    wire = _dict_of_final_return(fn)
    count = wire.get("changed_item_count")
    if not (
        isinstance(count, ast.Call)
        and _callee_name(count) == "len"
        and len(count.args) == 1
        and isinstance(count.args[0], ast.Name)
        and count.args[0].id == plan_var
    ):
        violations.append(
            f"changed_item_count 不是 `len({plan_var})`（实得 "
            f"{ast.dump(count) if count is not None else '<缺字段>'}）"
        )
    items = wire.get("changed_items")
    if not (isinstance(items, ast.Name) and items.id == plan_var):
        violations.append(f"changed_items 不是 `{plan_var}`（清单与计数必须同源）")
    return violations + _judge_diff_snapshots_role(fn, body, plan_var)


def _judge_diff_snapshots_role(fn: Any, body: list[Any], plan_var: str) -> list[str]:
    """子判据 4 / 5：`_diff_snapshots` 只许喂回滚覆盖面；两个变量不许对调。"""
    violations: list[str] = []
    union_var, union_calls = _assigned_from(body, _ROLLBACK_ITEMS)
    if len(union_calls) != 1 or not union_var:
        violations.append(
            f"{_ROLLBACK_ITEMS} 的调用点 {len(union_calls)} 处 / 赋值目标 {union_var!r}（须恰 1）"
        )
    all_diff = _calls_named(fn, _SNAPSHOT_DIFF)
    fed_to_union = [
        call
        for union in union_calls
        for kw in union.keywords
        if kw.arg == "snapshot_changed"
        for call in _calls_named(kw, _SNAPSHOT_DIFF)
    ]
    if not all_diff:
        violations.append(
            f"{_SNAPSHOT_DIFF} 在宿主里一处都没有 —— Requirement 6.9 需要它那一半："
            "被跳过的 item 在 plan 口径里看不见，只按 plan 存回滚快照会丢掉它们的原值"
        )
    elif len(all_diff) != len(fed_to_union):
        violations.append(
            f"{_SNAPSHOT_DIFF} 共 {len(all_diff)} 处调用，只有 {len(fed_to_union)} 处喂进 "
            f"{_ROLLBACK_ITEMS}(snapshot_changed=…) —— 其余那些流向不明，而它唯一被允许的用途"
            "就是回滚覆盖面（字节差集已被真库实测证明会漏报也会虚报，不得作为变更计数的来源）"
        )
    record = _calls_named(fn, _RECORD)
    passed = {
        kw.arg: kw.value.id
        for call in record
        for kw in call.keywords
        if isinstance(kw.value, ast.Name)
    }
    if passed.get("changed_items") != plan_var or passed.get("rollback_items") != union_var:
        violations.append(
            f"{_RECORD} 收到的是 changed_items={passed.get('changed_items')!r} / "
            f"rollback_items={passed.get('rollback_items')!r}，而 plan 口径是 {plan_var!r}、"
            f"并集口径是 {union_var!r} —— 两者对调会同时破坏 Requirement 3.6 与 6.9"
        )
    if union_var and plan_var and union_var == plan_var:
        violations.append("并集口径与 plan 口径是同一个变量 —— 并集被塌成了一半")
    return violations


#: §1 的五组变异：`(组名, 锚点, 替换, 违规文案必含的片段)`。
_S1_MUTANTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "M1_back_to_snapshot_diff",
        "changed = changed_items_from_plan(applied.plan)",
        "changed = _diff_snapshots(before_snapshot, after_snapshot)",
        _PLAN_CHANGED,
    ),
    (
        "M2_feeds_the_pre_merge_plan",
        "changed = changed_items_from_plan(applied.plan)",
        "changed = changed_items_from_plan(plan)",
        "applied.plan",
    ),
    (
        "M3_union_collapsed_to_plan_only",
        "        rollback_items = rollback_snapshot_items(\n"
        "            plan_changed=changed,\n"
        "            snapshot_changed=_diff_snapshots(before_snapshot, after_snapshot),\n"
        "        )",
        "        rollback_items = rollback_snapshot_items(\n"
        "            plan_changed=changed, snapshot_changed=()\n"
        "        )",
        "一处都没有",
    ),
    (
        "M4_two_calibers_swapped",
        "            changed_items=changed,\n            rollback_items=rollback_items,",
        "            changed_items=rollback_items,\n            rollback_items=changed,",
        "对调",
    ),
    (
        "M5_count_from_the_union",
        '"changed_item_count": len(changed),',
        '"changed_item_count": len(rollback_items),',
        "changed_item_count 不是",
    ),
)


class TestChangedItemCountComesFromThePlan:
    """§1 原棘轮的改写落点（`xfail` 已摘）。对照组 + 五组变异，逐组只打红它该打的那一条。"""

    def test_production_satisfies_every_clause(self) -> None:
        """对照组：生产实现下五条子判据全部成立。"""
        assert judge_changed_item_count_source(_func_ast(_HOST)) == []

    def test_the_snapshot_diff_only_feeds_the_rollback_coverage(self) -> None:
        """成对的那条现状登记改写后的形态：`_diff_snapshots` **仍在场**，但只喂回滚覆盖面。

        🔴 原文断言的是 `changed = _diff_snapshots(before_snapshot, after_snapshot)` 在场 ——
        6.4 落地后那句话变成假。改写方向不是删掉它，而是把它**换成新来源的正面断言**：
        `_diff_snapshots` 一处都不能少（Requirement 6.9 靠它兜住被跳过的 item），
        但它的产出一步都不许流进 `changed_item_count`。
        """
        fn = _func_ast(_HOST)
        body = fn.body[_stmt_index(fn.body, lambda s: isinstance(s, ast.Try))].body
        diff_calls = _calls_named(fn, _SNAPSHOT_DIFF)
        assert len(diff_calls) == 1, f"{_SNAPSHOT_DIFF} 调用点应恰 1 处，实得 {len(diff_calls)}"
        union_var, union_calls = _assigned_from(body, _ROLLBACK_ITEMS)
        fed = [
            call
            for kw in union_calls[0].keywords
            if kw.arg == "snapshot_changed"
            for call in _calls_named(kw, _SNAPSHOT_DIFF)
        ]
        assert fed == diff_calls, "那一处调用不是作为 snapshot_changed 实参出现的"
        assert union_var == "rollback_items"
        # 反面：它没有以任何形式出现在响应体里（响应体的两个字段都是 plan 变量）
        wire = _dict_of_final_return(fn)
        assert _calls_named(wire["changed_item_count"], _SNAPSHOT_DIFF) == []
        assert _calls_named(wire["changed_items"], _SNAPSHOT_DIFF) == []

    @pytest.mark.parametrize("name,old,new,needle", _S1_MUTANTS, ids=[m[0] for m in _S1_MUTANTS])
    def test_each_mutant_is_caught(self, name: str, old: str, new: str, needle: str) -> None:
        """逐组变异 ⇒ 判据必打红，且文案必含该组专属片段（红在别处不算它被抓到）。"""
        got = judge_changed_item_count_source(
            _mutated_fn_ast(ASR.compute_adopt_substrate, old=old, new=new)
        )
        assert got, f"{name} 没被抓到 —— 判据对这种实现是瞎的"
        assert any(needle in v for v in got), f"{name} 打红了，但红在别处：{got}"


# ═══════════════════════════════════════════════════════════════════════════════
# §2 `changed_items_from_plan` 的口径（Requirement 3.6）
#
# 🔴 本节的核心是**幽灵行计入**这条裁定：函数读的是裸 `rows_added`，不是
#    `rows_added − rows_ghost_dropped`。因为 `ghost ⊆ rows_added`（构造保证），两种写法只在
#    「全部新增身份都被幽灵门剔除」这个退化 item 上分叉 —— 而那个 item 的载荷**真的被改写过**
#    （design ADR-AOS-003 附注实测：`applied = 1`、语义相等、写回重序列化串）⇒ 算它有变更。
# ═══════════════════════════════════════════════════════════════════════════════

#: 三类行身份各自单独非空时都必须被算成「有变更」。
_ONE_CLASS_ONLY: tuple[tuple[str, dict[str, tuple[str, ...]]], ...] = (
    ("只有追加", {"added": ("a1",)}),
    ("只有删除", {"deleted": ("d1",)}),
    ("只有更新", {"updated": ("u1",)}),
)


class TestChangedItemsCaliber:
    @pytest.mark.parametrize("label,kwargs", _ONE_CLASS_ONLY, ids=[c[0] for c in _ONE_CLASS_ONLY])
    def test_any_single_class_counts(self, label: str, kwargs: dict[str, Any]) -> None:
        assert AOA.changed_items_from_plan(_plan(_delta(**kwargs))) == [ITEM], label

    def test_all_three_empty_does_not_count(self) -> None:
        """三清单全空 ⇒ 这个 item 的受管行集一行都没动。"""
        assert AOA.changed_items_from_plan(_plan(_delta())) == []

    def test_skipped_item_does_not_count(self) -> None:
        """被跳过的 item（`table_key` 为 None、三清单恒空）不进本口径 —— 它的可回滚性归 §5。"""
        plan = _plan(_delta(table_key=None, reason=SkipReason.item_blind))
        assert AOA.changed_items_from_plan(plan) == []
        assert plan.skipped_items == ((ITEM, SkipReason.item_blind),), "前提：它真的进了跳过清单"

    def test_ghost_only_item_still_counts(self) -> None:
        """🔴 裁定的落点：新增身份**全部**被幽灵门剔除的退化 item 仍算有变更。"""
        delta = _delta(added=("g1", "g2"), ghost=("g1", "g2"))
        assert set(delta.rows_ghost_dropped) == set(delta.rows_added), "前提：ghost 占满 added"
        assert not delta.rows_deleted and not delta.rows_updated, "前提：另两类为空"
        assert AOA.changed_items_from_plan(_plan(delta)) == [ITEM]

    def test_result_is_deduped_and_sorted(self) -> None:
        """同一 item 的多个分区 delta 只算一次；多个 item 按字典序。"""
        plan = _plan(
            _delta(item_id="AOS65-b", added=("a1",), section="S2"),
            _delta(item_id="AOS65-b", deleted=("d1",), section="S1"),
            _delta(item_id="AOS65-a", updated=("u1",)),
        )
        assert AOA.changed_items_from_plan(plan) == ["AOS65-a", "AOS65-b"]


#: §2 五组变异：`(组名, 锚点, 替换, 分辨用的 delta, 生产结果, 变异体结果)`。
#: 每组的 delta 都**只**在该组变异下分叉 —— 一个变异同时踩穿多条，红就只证明「判据能为假」。
_S2_MUTANTS: tuple[tuple[str, str, str, ItemOverwriteDelta, list[str], list[str]], ...] = (
    (
        "M1_ghost_subtracted_from_added",
        "if delta.rows_added or",
        "if (set(delta.rows_added) - set(delta.rows_ghost_dropped)) or",
        _delta(added=("g1",), ghost=("g1",)),
        [ITEM],
        [],
    ),
    (
        "M2_added_dropped_from_predicate",
        "if delta.rows_added or delta.rows_deleted or delta.rows_updated",
        "if delta.rows_deleted or delta.rows_updated",
        _delta(added=("a1",)),
        [ITEM],
        [],
    ),
    (
        "M3_deleted_dropped_from_predicate",
        "if delta.rows_added or delta.rows_deleted or delta.rows_updated",
        "if delta.rows_added or delta.rows_updated",
        _delta(deleted=("d1",)),
        [ITEM],
        [],
    ),
    (
        "M4_updated_dropped_from_predicate",
        "if delta.rows_added or delta.rows_deleted or delta.rows_updated",
        "if delta.rows_added or delta.rows_deleted",
        _delta(updated=("u1",)),
        [ITEM],
        [],
    ),
)


class TestChangedItemsCaliberMutants:
    @pytest.mark.parametrize(
        "name,old,new,delta,production,mutated", _S2_MUTANTS, ids=[m[0] for m in _S2_MUTANTS]
    )
    def test_each_predicate_term_carries_weight(
        self,
        name: str,
        old: str,
        new: str,
        delta: ItemOverwriteDelta,
        production: list[str],
        mutated: list[str],
    ) -> None:
        """逐项摘掉判据里的一个 term ⇒ 该 term 独占的那类 item 就漏了。"""
        plan = _plan(delta)
        mutant = _source_mutant(AOA.changed_items_from_plan, old=old, new=new, module=AOA)
        assert AOA.changed_items_from_plan(plan) == production, f"{name} 的对照组前提已变"
        assert mutant(plan) == mutated, f"{name} 变异没生效（变异体与生产同结果）"

    def test_dedup_is_not_incidental(self) -> None:
        """变异：集合推导换成列表推导 ⇒ 同一 item 的多个分区 delta 被数成多个。"""
        mutant = _source_mutant(
            AOA.changed_items_from_plan,
            old="{\n            delta.item_id\n            for delta in plan.deltas\n"
            "            if delta.rows_added or delta.rows_deleted or delta.rows_updated\n        }",
            new="[\n            delta.item_id\n            for delta in plan.deltas\n"
            "            if delta.rows_added or delta.rows_deleted or delta.rows_updated\n        ]",
            module=AOA,
        )
        plan = _plan(_delta(added=("a1",), section="S1"), _delta(deleted=("d1",), section="S2"))
        assert AOA.changed_items_from_plan(plan) == [ITEM]
        assert mutant(plan) == [ITEM, ITEM], "变异没生效 —— 去重不是集合推导带来的？"

    def test_production_module_is_not_polluted(self) -> None:
        """卫生判据：变异体与生产函数不是同一对象，且生产模块的绑定未被改写。"""
        mutant = _source_mutant(
            AOA.changed_items_from_plan,
            old="if delta.rows_added or",
            new="if False and delta.rows_added or",
            module=AOA,
        )
        assert mutant is not AOA.changed_items_from_plan
        assert mutant.__globals__ is not vars(AOA)
        assert AOA.changed_items_from_plan(_plan(_delta(added=("a1",)))) == [ITEM]
        assert ASR.changed_items_from_plan is AOA.changed_items_from_plan, (
            "service 里的那个不是伴生模块的同一对象 —— 同名不同源就是第二真源"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# §3 新旧两口径**逐值对照**（Requirement 3.6）
#
# 🔴 换来源这件事只有在「两者不等」的输入上才说明换掉了什么。本节固化 5 个场景，其中
#    **2 个不等**：S2（plan 多报）与 S4（plan 少报）。S4 那一向正是 Requirement 6.9 的连带
#    约束所在 —— 少报的那个 item 的原值会跟着从回滚快照里消失（判据在 §5）。
# ═══════════════════════════════════════════════════════════════════════════════


def _payload(*identities: str, compact: bool = True) -> str:
    """JSON 文本载荷。`compact=False` 模拟 `store_mirror` 写回的**带空格**形态。

    🔴 两种形态是 design ADR-AOS-003 附注的实测结论：前端写紧凑串、`store_mirror` 一律
    `json.dumps(..., ensure_ascii=False)`（带 `, ` 分隔符）⇒ 语义零净变化也会让字节差集报「变了」。
    """
    rows = [{IDENTITY: identity} for identity in identities]
    return json.dumps(rows, ensure_ascii=False, separators=(",", ":") if compact else None)


def _both_calibers(
    *,
    declared: tuple[str, ...],
    store_before: str | None,
    store_after: str | None,
    enumerable: bool = True,
    ghosts: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """同一输入下算出 `(旧口径, 新口径, 并集)`。旧 = 字节差集，新 = plan 三清单。"""
    reader = _StubReader(item_id=ITEM, declared_scopes=((TABLE, None),))
    inputs = ASR.AdoptPlanInputs(
        item_ids=(ITEM,),
        row_readers={ITEM: reader} if enumerable else {},
        skip_reasons={} if enumerable else {ITEM: SkipReason.item_blind},
        item_scopes={},
    )
    plan = ASR.compute_plan_for_adopt(
        baseline=_projection(**{TABLE: declared}),
        store_payloads={ITEM: store_before},
        plan_inputs=inputs,
        ghost_dropped_by_item=ghosts,
    )
    old = ASR._diff_snapshots({ITEM: store_before}, {ITEM: store_after})
    new = AOA.changed_items_from_plan(plan)
    return old, new, AOA.rollback_snapshot_items(plan_changed=new, snapshot_changed=old)


#: 5 个场景的实测对照表（逐值，探针 `_aos65p_calibers.py` 与本节两处一致）。
#: `(场景, 建造参数, 旧口径, 新口径, 并集)`
_CALIBER_TABLE: tuple[tuple[str, dict[str, Any], list[str], list[str], list[str]], ...] = (
    (
        "S1 删除侧独有改动（store 多一行、substrate 没有）",
        {"declared": ("keep",), "store_before": _payload("keep", "stale"),
         "store_after": _payload("keep")},
        [ITEM], [ITEM], [ITEM],
    ),
    (
        "S2 幂等重采纳（行集全等、字节一字未变）",
        {"declared": ("keep",), "store_before": _payload("keep"),
         "store_after": _payload("keep")},
        [], [ITEM], [ITEM],
    ),
    (
        "S3 幽灵行独占（新增身份全被剔除，merge 写回重序列化串）",
        {"declared": ("keep", "ghosty"), "store_before": _payload("keep"),
         "store_after": _payload("keep", compact=False), "ghosts": {ITEM: ("ghosty",)}},
        [ITEM], [ITEM], [ITEM],
    ),
    (
        "S4 被跳过的 item（不可枚举；merge 照样改写 remark）",
        {"declared": ("keep",), "store_before": _payload("keep"),
         "store_after": _payload("keep", "merged-by-provider"), "enumerable": False},
        [ITEM], [], [ITEM],
    ),
    (
        "S5 真新增 + 真删除",
        {"declared": ("keep", "fresh"), "store_before": _payload("keep", "stale"),
         "store_after": _payload("keep", "fresh")},
        [ITEM], [ITEM], [ITEM],
    ),
)

#: 两口径**不等**的场景（下标对齐 `_CALIBER_TABLE`）—— 本节的承重部分。
_DIVERGENT = ("S2", "S4")


class TestOldAndNewCalibersSideBySide:
    @pytest.mark.parametrize(
        "label,kwargs,old,new,union", _CALIBER_TABLE, ids=[c[0][:2] for c in _CALIBER_TABLE]
    )
    def test_each_scenario_matches_the_recorded_values(
        self,
        label: str,
        kwargs: dict[str, Any],
        old: list[str],
        new: list[str],
        union: list[str],
    ) -> None:
        got_old, got_new, got_union = _both_calibers(**kwargs)
        assert (got_old, got_new, got_union) == (old, new, union), label

    def test_exactly_two_scenarios_diverge(self) -> None:
        """🔴 反空转：若全部场景两口径都相等，本节等于什么都没测。"""
        diverged = [
            label[:2]
            for label, kwargs, _old, _new, _union in _CALIBER_TABLE
            if (lambda pair: pair[0] != pair[1])(_both_calibers(**kwargs)[:2])
        ]
        assert tuple(diverged) == _DIVERGENT, f"不等的场景集合变了：{diverged}"

    def test_the_union_is_never_smaller_than_either_side(self) -> None:
        """并集口径在**每个**场景上都同时覆盖两侧 —— 这是 §5 那条完整性判据的结构前提。"""
        for label, kwargs, _old, _new, _union in _CALIBER_TABLE:
            got_old, got_new, got_union = _both_calibers(**kwargs)
            assert set(got_union) >= set(got_old) | set(got_new), label

    def test_s2_is_the_direction_where_the_plan_over_reports(self) -> None:
        """S2 如实登记：字节**一字未变**而 plan 报有变更。

        哪个更如实？两者回答的是不同问题 —— 旧问「字节变没变」，新问「这次覆盖声明要覆盖哪些
        item 的受管行集」。S2 里 `rows_updated` 非空（`keep` 两侧都在）是**如实**的：覆盖确实
        把 substrate 的 `keep` 写进了 store，只是字段值恰好相同。Requirement 3.6 要的是后者
        （弹窗报的数与执行后报的数必须同源、可对账），而前者在 dry_run 那一趟根本取不到值
        ⇒ 它当不了响应字段的来源。
        """
        old, new, _union = _both_calibers(
            declared=("keep",),
            store_before=_payload("keep"),
            store_after=_payload("keep"),
        )
        assert old == [] and new == [ITEM]

    def test_s4_is_the_direction_that_threatens_requirement_6_9(self) -> None:
        """🔴 S4 如实登记：plan **看不见**被跳过的 item，而它的 `remark` 真的被 merge 改写了。

        这一向才是危险的：只按 plan 口径存回滚快照，这个 item 的原值当场丢失、被改写的内容
        再也拿不回来。处置 = 回滚覆盖面取并集（判据在 §5，含「漏掉这类 item ⇒ 打红」的变异）。
        """
        old, new, union = _both_calibers(
            declared=("keep",),
            store_before=_payload("keep"),
            store_after=_payload("keep", "merged-by-provider"),
            enumerable=False,
        )
        assert old == [ITEM] and new == [] and union == [ITEM]

# ═══════════════════════════════════════════════════════════════════════════════
# 指针：另一半在哪
# ═══════════════════════════════════════════════════════════════════════════════
#
# §4（审计 details 追加三字段 + `event_type` 不登记 schema）· §5（回滚快照完整性，
# Requirement 6.9）· §6（四个新纯函数的卫生）整组在 **`test_aos_audit_details_and_rollback_snapshot.py`**。
# 🔴 切分原因是行数门禁：两半同文件实测 **1038** 行 > `.py` 上限 800（域内第七次同样处置，
#    先例 `test_aos_property_out_of_scope_rows.py` / `…_out_of_scope_mutants.py` 等）。
# 🔴 切口选在 **§3 / §4 之间**，即 **Task 6.4 与 6.5 的任务边界** —— 不是按行数对半砍：
#    本文件承「`changed_item_count` 从哪来、口径是什么」（6.4），伴生件承「留痕与可回滚」（6.5）。
#    **没有**把任何一个判据函数与它的变异反证拆开：`judge_changed_item_count_source` 与它的 5 组
#    变异都在本文件，`judge_rollback_completeness` 与它的 4 组变异都在伴生件。
# 🔴 本文件同时是两份的**共用件**：`_delta` / `_plan` / `_mutated_fn_ast` / `ITEM` / `TABLE` /
#    `_EVENT_TYPE` / `_NEW_PURE` 由伴生件 import（**顶层模块名**，理由见本文件 docstring 末段）。
#    `_mutated_fn_ast` 只被本文件用到、`_AuditSession` / `_record` / `_applied` / `_sample_plan`
#    只被伴生件用到 —— 🔴 **不要因为「本文件没用到」就删**。
