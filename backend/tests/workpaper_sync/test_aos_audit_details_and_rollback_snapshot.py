"""Task 6.5 判据（伴生件）：审计 details 追加字段 · 回滚快照完整性 · 新纯函数卫生。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 1.8 / 6.7 / 6.9 · design § Data Models（details 追加三行）

| 节 | 判据 | 要害 |
| --- | --- | --- |
| §4 | 追加三字段 + `event_type` **不**登记 schema | details 是真经 `append_audit_log` 组装出来的 |
| §5 | 回滚快照覆盖面 = 两口径并集 | 漏掉被跳过的 item ⇒ 它的原值再也拿不回来 |
| §6 | 四个新纯函数不碰 session / 不改入参 / 可 JSON 序列化 | —— |

🔴 **§1~§3 在主体 `test_aos_changed_items_and_audit_details.py`**（Task 6.4：`changed_item_count`
的来源源码锁 / 口径 / 新旧两口径逐值对照）。切口在 **§3 / §4 之间 = 6.4 与 6.5 的任务边界**，
原因是行数门禁（两半同文件 **1038** 行 > `.py` 上限 800）；**没有**拆开任何「判据函数 + 它的变异
反证」对。定向回归清单必须两份都在。

🔴 **工具 / 桩 / 计划建造器一律从主体与 `test_aos_adopt_plan_wiring.py` import，不另造第二份**，
且用**顶层模块名** —— 该目录无 `__init__.py`，pytest 走 `prepend`；写成 `tests.workpaper_sync.…`
会拿到第二个模块实例，`_plan` / `_delta` / `ITEM` 当场分家。

🔴 **变异一律进程内源码级**（`_source_mutant`：`inspect.getsource` → 换**唯一**锚点 → 在生产模块
`globals` 的**副本**里 `exec`），生产文件一字不改，也不用 `monkeypatch.setattr`（本域有并发会话）。
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
from app.services.workpaper_sync.adopt_overwrite_plan import OverwritePlan, SkipReason

from test_aos_adopt_plan_wiring import (  # noqa: E402
    _callee_name,
    _calls_named,
    _func_ast,
    _source_mutant,
)
from test_aos_changed_items_and_audit_details import (  # noqa: E402
    ITEM,
    _EVENT_TYPE,
    _NEW_PURE,
    _delta,
    _plan,
)

# ═══════════════════════════════════════════════════════════════════════════════
# §4 审计 details 的追加字段（Requirement 1.8 / 6.7）
#
# 🔴 判据落在**真经 `append_audit_log` 组装出来的那个 payload** 上，不是「service 里写了这几个
#    键」的源码匹配 —— 后者测不出「写了却被 schema 校验拒掉」「写了却没进 payload」这两类。
#    假 session 只替 DB（`_get_prev_hash` 自带 try/except 兜底），`append_audit_log` 本体是真的。
# ═══════════════════════════════════════════════════════════════════════════════

#: design § Data Models 逐字列出的三个追加字段。
_ADDED_DETAIL_FIELDS = ("rows_deleted_by_item", "plan_digest", "skipped_items")
#: 一个**已登记** schema 的 event_type（那条「未登记」判据的变异对照）。
_REGISTERED_EVENT_TYPE = "onlyoffice_callback_rejected"


class _AuditSession:
    """`append_audit_log` 的最小替身：它只用到 `execute` / `add` / `flush`。

    `_get_prev_hash` 自带 `except Exception: return GENESIS_HASH` ⇒ `execute` 返回一个
    `scalar_one_or_none() is None` 的空结果即可，不必假装会查审计链。
    """

    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushes = 0

    async def execute(self, statement: Any, params: Any = None) -> Any:
        class _Empty:
            def scalar_one_or_none(self) -> Any:
                return None

        return _Empty()

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    @property
    def details(self) -> dict[str, Any]:
        assert len(self.added) == 1, f"审计条目应恰 1 条，实得 {len(self.added)}"
        return dict(self.added[0].payload)


def _applied(
    plan: OverwritePlan, *, deleted: Mapping[str, tuple[str, ...]] | None = None
) -> Any:
    return AOA.AppliedOverwrite(
        plan=plan,
        rows_deleted_by_item=dict(deleted or {}),
        post_merge_ids={},
        ghost_dropped_by_item={},
        mismatches=[],
    )


def _record(
    *,
    applied: Any,
    before_snapshot: Mapping[str, str | None],
    changed_items: list[str],
    rollback_items: list[str],
    record_fn: Any = None,
) -> dict[str, Any]:
    """真跑 `_record_rollback_and_audit`（或它的变异体），返回落进审计 payload 的 details。"""
    session = _AuditSession()
    asyncio.run(
        (record_fn or ASR._record_rollback_and_audit)(
            session,
            project_id=uuid.uuid4(),
            wp_id="aos65-wp",
            entry_id="aos65-entry",
            substrate_sha="sha-aos65",
            before_snapshot=dict(before_snapshot),
            changed_items=list(changed_items),
            rollback_items=list(rollback_items),
            applied=applied,
        )
    )
    return session.details


def _sample_plan() -> OverwritePlan:
    """一份含「有变更 item + 被跳过 item」的计划（§4 / §5 共用）。"""
    return _plan(
        _delta(added=("a1",), deleted=("d1", "d2"), updated=("u1",)),
        _delta(item_id="AOS65-blind", table_key=None, reason=SkipReason.item_blind),
    )


class TestAuditDetailsAdditions:
    def test_pure_builder_yields_exactly_the_three_designed_fields(self) -> None:
        plan = _sample_plan()
        got = AOA.audit_details_for_applied(_applied(plan, deleted={ITEM: ("d1", "d2")}))
        assert set(got) == set(_ADDED_DETAIL_FIELDS), f"追加字段集合变了：{sorted(got)}"
        assert got["plan_digest"] == plan.digest
        assert got["rows_deleted_by_item"] == {ITEM: ["d1", "d2"]}
        assert got["skipped_items"] == [["AOS65-blind", "item_blind"]]

    def test_rows_deleted_by_item_is_sorted_and_json_ready(self) -> None:
        """多 item 时按 item 排序、值是 `list`（元组进不了 JSONB）。"""
        applied = _applied(
            _sample_plan(), deleted={"AOS65-z": ("z1",), "AOS65-a": ("a1", "a2")}
        )
        got = AOA.audit_details_for_applied(applied)["rows_deleted_by_item"]
        assert list(got) == ["AOS65-a", "AOS65-z"]
        assert all(isinstance(v, list) for v in got.values())
        assert json.loads(json.dumps(got, ensure_ascii=False)) == got

    def test_skipped_items_shares_one_caliber_with_the_wire_form(self) -> None:
        """🔴 审计 details 与响应 wire form 的 `skipped_items` 是**同一个投影函数**算的。"""
        plan = _sample_plan()
        assert (
            AOA.audit_details_for_applied(_applied(plan))["skipped_items"]
            == ASR._plan_wire_form(plan)["skipped_items"]
            == AOA.skipped_items_wire(plan)
        )
        # 源码锁：wire form 真的在调那个门面（不是各写一遍恰好相等）
        assert len(_calls_named(_func_ast("_plan_wire_form"), "skipped_items_wire")) == 1

    def test_assembled_details_carry_everything(self) -> None:
        """端到端（真 `append_audit_log` + 假 session）：落进 payload 的 details 逐字段核对。"""
        plan = _sample_plan()
        changed = AOA.changed_items_from_plan(plan)
        details = _record(
            applied=_applied(plan, deleted={ITEM: ("d1", "d2")}),
            before_snapshot={ITEM: "before-json", "AOS65-blind": "blind-json"},
            changed_items=changed,
            rollback_items=[ITEM, "AOS65-blind"],
        )
        assert details["event_type"] == _EVENT_TYPE, "event_type 被改了（禁复用别人的）"
        for field in _ADDED_DETAIL_FIELDS:
            assert field in details, f"details 里没有追加字段 {field}"
        assert details["plan_digest"] == plan.digest
        assert details["rows_deleted_by_item"] == {ITEM: ["d1", "d2"]}
        assert details["skipped_items"] == [["AOS65-blind", "item_blind"]]
        assert details["changed_item_count"] == len(changed) == 1
        assert details["changed_items"] == [ITEM]
        assert details["wp_id"] == "aos65-wp" and details["substrate_sha256"] == "sha-aos65"

    def test_event_type_is_deliberately_not_schema_registered(self) -> None:
        """🔴 **不得**为这三个字段给它登记 schema —— 登记后它们就变必填。

        变异对照：一个**已登记**的 event_type 在同一个表里必须查得到（否则本条什么都没在查）。
        """
        assert _EVENT_TYPE not in ALH.EVENT_TYPE_SCHEMAS
        assert _REGISTERED_EVENT_TYPE in ALH.EVENT_TYPE_SCHEMAS, (
            "变异对照失效：连已登记的 event_type 都查不到 ⇒ 上一条断言什么都没在查"
        )
        # 第二判据：它在 `audit_log_helper` 的源码里一次都不该出现（登记 schema 必然出现在那里）
        assert _EVENT_TYPE not in inspect.getsource(ALH)


# ═══════════════════════════════════════════════════════════════════════════════
# §5 回滚快照完整性（Requirement 6.9）
#
# 🔴 这是 6.4 换口径带出来的**连带约束**：`rollback_snapshot` 只存「有变更」的 item 的原值 ⇒
#    口径一变，能不能完整回滚就跟着变。plan 口径**看不见**被跳过的 item（它们的三清单恒空），
#    而 merge 照样改写了它们的 `remark` ⇒ 只按 plan 存快照，那些原值当场丢失。
# 🔴 判据不止「键在不在」，还要「存的值**就是**覆盖前那一份」—— 键在而值是 None 的快照还不了原。
# ═══════════════════════════════════════════════════════════════════════════════

BLIND = "AOS65-blind"
#: 覆盖前的两条原值（回滚要还原成它们）。
_BEFORE: Mapping[str, str | None] = {
    ITEM: '[{"rowId":"keep"},{"rowId":"stale"}]',
    BLIND: '{"answer":"覆盖前的原值"}',
}


def _two_item_calibers() -> tuple[list[str], list[str], list[str]]:
    """两条 item 的两个口径：`ITEM` 只被 plan 看见之外还变了字节，`BLIND` **只**被字节差集看见。"""
    plan = _plan(
        _delta(deleted=("stale",), updated=("keep",)),
        _delta(item_id=BLIND, table_key=None, reason=SkipReason.item_blind),
    )
    plan_changed = AOA.changed_items_from_plan(plan)
    snapshot_changed = ASR._diff_snapshots(
        dict(_BEFORE), {ITEM: '[{"rowId":"keep"}]', BLIND: '{"answer":"被 merge 改写了"}'}
    )
    return (
        plan_changed,
        snapshot_changed,
        AOA.rollback_snapshot_items(plan_changed=plan_changed, snapshot_changed=snapshot_changed),
    )


def judge_rollback_completeness(details: Mapping[str, Any], *, must_cover: tuple[str, ...]) -> list[str]:
    """`rollback_snapshot` 必须覆盖 `must_cover` 里的每个 item 且值等于覆盖前原值。"""
    snapshot = json.loads(str(details.get("rollback_snapshot") or "{}"))
    violations: list[str] = []
    for item in must_cover:
        if item not in snapshot:
            violations.append(
                f"{item} 不在 rollback_snapshot 里 —— 它被改写过而原值没留，再也恢复不了"
                "（Requirement 6.9）"
            )
        elif snapshot[item] != _BEFORE[item]:
            violations.append(f"{item} 存的不是覆盖前原值（实得 {snapshot[item]!r}）")
    return violations


#: §5 的三组变异：`(组名, 被变异函数, 锚点, 替换, 是否改 record 层)`
_RB_M1 = (
    "rollback_payload = {item: before_snapshot.get(item) for item in rollback_items}",
    "rollback_payload = {item: before_snapshot.get(item) for item in changed_items}",
)
_RB_UNION_ANCHOR = (
    "return sorted({*(str(x) for x in plan_changed), *(str(x) for x in snapshot_changed)})"
)


class TestRollbackSnapshotCompleteness:
    def test_union_covers_both_calibers(self) -> None:
        """前提实测：`ITEM` 两个口径都看得见，`BLIND` **只有**字节差集看得见。"""
        plan_changed, snapshot_changed, union = _two_item_calibers()
        assert plan_changed == [ITEM]
        assert snapshot_changed == [BLIND, ITEM]
        assert union == [BLIND, ITEM]

    def test_production_snapshot_covers_the_skipped_item(self) -> None:
        """对照组：生产实现下被跳过的 item 的原值也在快照里（Requirement 6.9）。"""
        plan_changed, _snapshot_changed, union = _two_item_calibers()
        details = _record(
            applied=_applied(_sample_plan(), deleted={ITEM: ("stale",)}),
            before_snapshot=_BEFORE,
            changed_items=plan_changed,
            rollback_items=union,
        )
        assert judge_rollback_completeness(details, must_cover=(ITEM, BLIND)) == []
        # 🔴 `changed_items` 仍是 plan 口径（不因为快照变宽而跟着变宽）
        assert details["changed_items"] == [ITEM] and details["changed_item_count"] == 1

    def test_mutant_snapshot_keyed_by_changed_items_loses_the_skipped_item(self) -> None:
        """🔴 变异 RB-M1（= 6.5 之前的写法）：快照按 `changed_items` 取键 ⇒ 被跳过的 item 丢了。"""
        plan_changed, _snapshot_changed, union = _two_item_calibers()
        mutant = _source_mutant(
            ASR._record_rollback_and_audit, old=_RB_M1[0], new=_RB_M1[1], module=ASR
        )
        details = _record(
            applied=_applied(_sample_plan(), deleted={ITEM: ("stale",)}),
            before_snapshot=_BEFORE,
            changed_items=plan_changed,
            rollback_items=union,
            record_fn=mutant,
        )
        got = judge_rollback_completeness(details, must_cover=(ITEM, BLIND))
        assert len(got) == 1 and BLIND in got[0], got
        # 变异生效断言：`ITEM` 仍在（证明红的是「少了 BLIND」不是「整个快照没了」）
        assert ITEM in json.loads(details["rollback_snapshot"])

    def test_mutant_union_collapsed_to_plan_only_loses_the_skipped_item(self) -> None:
        """变异 RB-M2：并集塌成 plan 一半 ⇒ 同一条原值在**另一层**丢掉。"""
        plan_changed, snapshot_changed, _union = _two_item_calibers()
        mutant = _source_mutant(
            AOA.rollback_snapshot_items,
            old=_RB_UNION_ANCHOR,
            new="return sorted({*(str(x) for x in plan_changed)})",
            module=AOA,
        )
        collapsed = mutant(plan_changed=plan_changed, snapshot_changed=snapshot_changed)
        assert collapsed == [ITEM], "变异没生效"
        details = _record(
            applied=_applied(_sample_plan(), deleted={ITEM: ("stale",)}),
            before_snapshot=_BEFORE,
            changed_items=plan_changed,
            rollback_items=collapsed,
        )
        got = judge_rollback_completeness(details, must_cover=(ITEM, BLIND))
        assert len(got) == 1 and BLIND in got[0], got

    def test_delete_side_item_is_covered_by_the_plan_half_alone(self) -> None:
        """🔴 「被删除侧改动的 item 一个都不能漏」—— 即便字节差集因任何原因没报它。

        🔴 **如实声明构造依据**：在 Task 6.3 的顺序下（prune 排在 `after_snapshot` 之前）删除侧的
        UPDATE 必然改字节 ⇒ 本轮**构造不出**「plan 报了删除而字节差集没报」的真实场景。故本条按
        **构造**判：把 `snapshot_changed` 置空，plan 那一半必须独立兜住它 —— 这正是并集里 plan
        那一半存在的理由（它不依赖任何观测仪器，而字节差集已被真库实测证明两向失真）。
        """
        plan_changed = AOA.changed_items_from_plan(_plan(_delta(deleted=("stale",))))
        assert plan_changed == [ITEM], "前提：只被删除侧改动的 item 在 plan 口径里看得见"
        applied = _applied(_sample_plan(), deleted={ITEM: ("stale",)})
        kept = AOA.rollback_snapshot_items(plan_changed=plan_changed, snapshot_changed=[])
        assert judge_rollback_completeness(
            _record(
                applied=applied,
                before_snapshot=_BEFORE,
                changed_items=plan_changed,
                rollback_items=kept,
            ),
            must_cover=(ITEM,),
        ) == []
        # 变异反证：并集塌成字节差集那一半 ⇒ 被删除侧改动的这条原值当场丢失
        mutant = _source_mutant(
            AOA.rollback_snapshot_items,
            old=_RB_UNION_ANCHOR,
            new="return sorted({*(str(x) for x in snapshot_changed)})",
            module=AOA,
        )
        collapsed = mutant(plan_changed=plan_changed, snapshot_changed=[])
        assert collapsed == [], "变异没生效"
        got = judge_rollback_completeness(
            _record(
                applied=applied,
                before_snapshot=_BEFORE,
                changed_items=plan_changed,
                rollback_items=collapsed,
            ),
            must_cover=(ITEM,),
        )
        assert len(got) == 1 and ITEM in got[0], got

    def test_mutant_union_collapsed_to_snapshot_only_breaks_the_superset_clause(self) -> None:
        """变异 RB-M3：并集塌成字节差集那一半 ⇒ 结构上不再覆盖 plan 侧。

        🔴 **如实声明**：这一向在本轮 5 个场景里丢掉的 item 其实什么都没变（幂等重采纳），
        所以它**不是**可恢复性缺陷，而是「并集必须真的是并集」这条结构性约束的破坏 ——
        判据按结构判，不假装它造成了数据丢失。
        """
        mutant = _source_mutant(
            AOA.rollback_snapshot_items,
            old=_RB_UNION_ANCHOR,
            new="return sorted({*(str(x) for x in snapshot_changed)})",
            module=AOA,
        )
        assert mutant(plan_changed=["only-in-plan"], snapshot_changed=["only-in-bytes"]) == [
            "only-in-bytes"
        ]
        assert AOA.rollback_snapshot_items(
            plan_changed=["only-in-plan"], snapshot_changed=["only-in-bytes"]
        ) == ["only-in-bytes", "only-in-plan"]


# ═══════════════════════════════════════════════════════════════════════════════
# §6 四个新纯函数的卫生
#
# 🔴 既有「service 只 flush 不 commit」判据（gates 文件 §9 / 删除侧文件 §4）扫的是模块 AST；
#    本节补的是**这四个新函数自己**：拿不到 session、不发语句、不改入参、产出可直接进 JSONB。
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewPureFunctionHygiene:
    @pytest.mark.parametrize("symbol", _NEW_PURE)
    def test_is_sync_and_session_free(self, symbol: str) -> None:
        fn = getattr(AOA, symbol)
        assert not inspect.iscoroutinefunction(fn), f"{symbol} 是协程 —— 它不该碰 IO"
        assert "session" not in inspect.signature(fn).parameters, f"{symbol} 收了 session"
        calls = {
            _callee_name(node)
            for node in ast.walk(ast.parse(inspect.getsource(fn)))
            if isinstance(node, ast.Call)
        }
        assert not calls & {"commit", "flush", "execute"}, f"{symbol} 里出现了事务/语句操作"

    @pytest.mark.parametrize("symbol", _NEW_PURE)
    def test_is_exported(self, symbol: str) -> None:
        assert symbol in AOA.__all__, f"{symbol} 不在 __all__ 里（伴生模块的对外面必须显式）"

    def test_builders_do_not_mutate_their_inputs(self) -> None:
        plan = _sample_plan()
        applied = _applied(plan, deleted={ITEM: ("d1", "d2")})
        digest_before = plan.digest
        first = AOA.audit_details_for_applied(applied)
        first["rows_deleted_by_item"][ITEM].append("偷偷加一条")
        assert AOA.audit_details_for_applied(applied) != first, "两次调用返回同一个可变对象"
        assert applied.rows_deleted_by_item == {ITEM: ("d1", "d2")}
        assert plan.digest == digest_before

    def test_details_are_strictly_json_serialisable(self) -> None:
        """🔴 `append_audit_log` 用 `default=str` 兜底 ⇒ 不可序列化的值会被静默转成字符串。

        details 要进 JSONB，所以这里**不带** `default` 地序列化一次 —— 真有枚举 / 元组漏转，
        这条会当场抛而不是让它伪装成一个可读的字符串躺进审计轨迹。
        """
        details = AOA.audit_details_for_applied(
            _applied(_sample_plan(), deleted={ITEM: ("d1",)})
        )
        assert json.loads(json.dumps(details, ensure_ascii=False, allow_nan=False)) == details

    def test_str_coercion_on_the_union(self) -> None:
        """并集口径对非 str 键做 `str()` 归一（审计 payload 的键必须是字符串）。"""
        assert AOA.rollback_snapshot_items(plan_changed=[1, "b"], snapshot_changed=("b", 2)) == [
            "1",
            "2",
            "b",
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# 指针：相邻判据在哪
# ═══════════════════════════════════════════════════════════════════════════════
#
# · §1~§3（Task 6.4）在主体 **`test_aos_changed_items_and_audit_details.py`**：
#   §1 `changed_item_count` 来源的 AST 源码锁（它同时是
#   `test_aos_adopt_plan_gates_and_wire_form.py` §9 那条最后棘轮 `xfail(strict=True)` 摘除后的
#   改写落点，与它成对的现状登记一并改写）· §2 口径（含**幽灵行计入**裁定）· §3 新旧两口径逐值对照
# · 计划**怎么来的** → `test_aos_adopt_plan_wiring.py`（§1~§4 / §10）
# · 计划算出来**之后**的校验门 / 错误码 / wire form / 事务纪律 →
#   `test_aos_adopt_plan_gates_and_wire_form.py`（§5~§9 / §11）
# · 删除侧应用 · 幽灵观测 · 复读比对 · router 500 映射 →
#   `test_aos_deletion_apply_and_verify.py`（§1~§5）
# · 共用工具箱（`_source_mutant` / AST 取件 / `_StubReader` / `_projection` / `_IDENTITY_KEY`）
#   在 `test_aos_adopt_plan_wiring.py`；计划建造器（`_delta` / `_plan`）与 `ITEM` / `_EVENT_TYPE` /
#   `_NEW_PURE` 在主体。本文件**只 import 不另造第二份**，也没有新造任何工具。
# · 本文件独有的桩是 `_AuditSession`（`append_audit_log` 的最小替身）与 `_record` / `_applied` /
#   `_sample_plan` —— 🔴 主体里没有用到它们，**不要因此以为是死代码**。
