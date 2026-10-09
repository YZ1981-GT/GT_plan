"""Task 6.3 的**行为**判据：删除侧应用 · 幽灵行观测 · 提交前复读比对。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 1.1 / 1.2 / 1.6 / 3.5 · ADR-AOS-001（后置 prune）

| 节 | 判据 | 要害 |
| --- | --- | --- |
| §1 | 幽灵观测口径 + `rows_ghost_dropped ⊆ rows_added` | 观测面取 `added ∪ updated`，否则 ⊆ 是恒真废话 |
| §2 | 复读比对比**身份集合** | 「删对个数但删错行」两侧计数相同、集合不同 |
| §3 | 删除侧**真落库**（假 session 观测发出的 SQL） | 零删除不发写 · 写 0 行即不符 |
| §4 | 应用模块的卫生 | 零 commit/flush · 不 import OO 路径那两个模块 |
| §5 | router 500 映射 + `except` **顺序**（源码锁） | 子类分支排在兜底之后永远进不去 |

🔴 另一条源码锁「删除侧在 merge **之后**」（`judge_deletion_after_mirror` 与它的 4 组变异）在
`test_aos_adopt_plan_gates_and_wire_form.py` **§11** —— 那边是 `compute_adopt_substrate` 的
判据主场。两个文件合起来才是 6.3 的完整判据面；定向回归清单必须两份都在。

🔴 **工具与桩从 `test_aos_adopt_plan_wiring.py` import，不另造第二份**，且用**顶层模块名** ——
该目录无 `__init__.py`，pytest 走 `prepend` 模式；写成 `tests.workpaper_sync.…` 会拿到第二个
模块实例，`_StubReader` / `_projection` / `_source_mutant` 当场分家。

🔴 **变异一律进程内源码级**（`inspect.getsource` → 换唯一锚点 → 在生产模块 `globals` 的**副本**
里 `exec`），生产文件一字不改。不用 `monkeypatch.setattr` —— 本域有并发会话，即便自动还原，
窗口期内也改了共用模块的行为。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
from typing import Any, Mapping

import pytest

from app.services.workpaper_sync import adopt_overwrite_apply as AOA
from app.services.workpaper_sync import adopt_substrate_response as ASR
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlan,
    OverwritePlanShapeError,
)

from test_aos_adopt_plan_wiring import (  # noqa: E402
    _IDENTITY_KEY,
    _ROUTER_PY,
    _StubReader,
    _projection,
    _source_mutant,
)

ITEM = "AOS63-rows"
TABLE = "aos63_rows"
SIBLING = "aos63_sibling_rows"
SECTION_FIELD = "aos63Section"


def _payload(*identities: str, section: str | None = None) -> str:
    """JSON 文本载荷（真库 `checklist_responses.remark` 的形态）。"""
    rows: list[dict[str, Any]] = []
    for identity in identities:
        row: dict[str, Any] = {_IDENTITY_KEY: identity}
        if section is not None:
            row[SECTION_FIELD] = section
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def _ids(payload: str) -> set[str]:
    return {str(row[_IDENTITY_KEY]) for row in json.loads(payload)}


def _plan_inputs(reader: Any, *, item_scopes: Mapping[str, Any] | None = None) -> Any:
    return ASR.AdoptPlanInputs(
        item_ids=(ITEM,),
        row_readers={ITEM: reader},
        skip_reasons={},
        item_scopes=dict(item_scopes or {}),
    )


def _plan(
    *,
    added: tuple[str, ...] = (),
    deleted: tuple[str, ...] = (),
    updated: tuple[str, ...] = (),
    section: str | None = None,
    table_key: str = TABLE,
) -> OverwritePlan:
    """一份手搓计划（§1 / §2 用）—— 只要三清单是本节要的形态即可。"""
    return OverwritePlan(
        deltas=(
            ItemOverwriteDelta(
                item_id=ITEM,
                table_key=table_key,
                row_section=section,
                rows_added=added,
                rows_deleted=deleted,
                rows_updated=updated,
            ),
        ),
        store_rows_by_table={table_key: len(deleted) + len(updated)},
        substrate_rows_by_table={table_key: len(added) + len(updated)},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# §1 幽灵行**观测**口径 + `rows_ghost_dropped ⊆ rows_added`（Requirement 1.6）
#
# 🔴 计划期恒空是裁定（预测幽灵 = 复现引擎判据 = 第二真源）⇒ 本节测的是**观测**：
#    「计划说该在场、merge 之后却不在」。⊆ 之所以**不是**恒真废话，是因为观测面取
#    `added ∪ updated`：落在 updated 侧的缺失被单独拎成违规，而不是一起塞进 ghost。
# ═══════════════════════════════════════════════════════════════════════════════


class TestGhostObservation:
    def test_missing_added_identity_becomes_a_ghost(self) -> None:
        """本次新增的身份 merge 之后不在场 ⇒ 幽灵行门剔除了它（合法差异，登记不报错）。"""
        plan = _plan(added=("a1", "a2"), updated=("u1",), deleted=("d1",))
        ghosts, violations = AOA.observe_ghost_dropped(
            plan, post_merge_ids={ITEM: {None: frozenset({"a1", "u1", "d1"})}}
        )
        assert ghosts == {ITEM: ("a2",)}
        assert violations == []

    def test_ghost_is_a_subset_of_rows_added(self) -> None:
        """⊆ 约束：观测出的每个幽灵身份都必须在 `rows_added` 里。"""
        plan = _plan(added=("a1", "a2"), updated=("u1",))
        ghosts, _violations = AOA.observe_ghost_dropped(
            plan, post_merge_ids={ITEM: {None: frozenset()}}
        )
        assert set(ghosts[ITEM]) <= set(plan.deltas[0].rows_added)
        assert set(ghosts[ITEM]) == {"a1", "a2"}

    def test_missing_updated_identity_is_a_violation_not_a_ghost(self) -> None:
        """🔴 ⊆ 的**牙**：已存在的行消失了不是幽灵 —— 引擎明写「已存在的行永不受影响」。"""
        plan = _plan(added=("a1",), updated=("u1",))
        ghosts, violations = AOA.observe_ghost_dropped(
            plan, post_merge_ids={ITEM: {None: frozenset({"a1"})}}
        )
        assert ghosts == {}, "把 updated 侧的缺失也当成幽灵，就是把 merge 删了行掩盖过去"
        assert len(violations) == 1 and "不是**本次新增" in violations[0]

    def test_nothing_missing_yields_nothing(self) -> None:
        plan = _plan(added=("a1",), updated=("u1",), deleted=("d1",))
        assert AOA.observe_ghost_dropped(
            plan, post_merge_ids={ITEM: {None: frozenset({"a1", "u1", "d1"})}}
        ) == ({}, [])

    def test_ghosts_are_observed_across_partitions(self) -> None:
        """🔴 被剔除的行**没有分区**（它根本不在载荷里）⇒ 观测必须按 item 聚合而非按分区找。"""
        plan = _plan(added=("a1",), updated=("u1",), section="S1")
        ghosts, violations = AOA.observe_ghost_dropped(
            plan, post_merge_ids={ITEM: {"S1": frozenset({"u1"}), "S2": frozenset({"x"})}}
        )
        assert ghosts == {ITEM: ("a1",)} and violations == []

    def test_mutant_observing_only_added_loses_the_subset_teeth(self) -> None:
        """变异：观测面缩成 `added - present` ⇒ updated 侧的缺失被静默放过 ⇒ ⊆ 断言失去意义。"""
        mutant = _source_mutant(
            AOA.observe_ghost_dropped,
            old="missing = (added | updated) - present",
            new="missing = added - present",
            module=AOA,
        )
        plan = _plan(added=("a1",), updated=("u1",))
        post = {ITEM: {None: frozenset({"a1"})}}
        assert len(AOA.observe_ghost_dropped(plan, post_merge_ids=post)[1]) == 1
        assert mutant(plan, post_merge_ids=post)[1] == [], "变异体仍报违规 ⇒ 变异没生效"


class TestGhostFeedbackIntoThePlan:
    """回喂：观测结果经 `ghost_dropped_by_item` 重算 ⇒ 幽灵落到各自分区（第二道独立拦在 compute）。"""

    @staticmethod
    def _recompute(ghosts: Mapping[str, tuple[str, ...]]) -> OverwritePlan:
        reader = _StubReader(item_id=ITEM, declared_scopes=((TABLE, None),))
        return ASR.compute_plan_for_adopt(
            baseline=_projection(**{TABLE: ("keep", "add")}),
            store_payloads={ITEM: _payload("keep", "stale")},
            plan_inputs=_plan_inputs(reader),
            ghost_dropped_by_item=dict(ghosts),
        )

    def test_planning_phase_is_empty_without_feedback(self) -> None:
        """不回喂 ⇒ 计划期恒空（裁定：不预测幽灵行）。"""
        delta = self._recompute({}).deltas[0]
        assert delta.rows_ghost_dropped == ()
        assert delta.rows_added == ("add",) and delta.rows_deleted == ("stale",)

    def test_observed_ghost_lands_in_the_delta(self) -> None:
        delta = self._recompute({ITEM: ("add",)}).deltas[0]
        assert delta.rows_ghost_dropped == ("add",)
        assert set(delta.rows_ghost_dropped) <= set(delta.rows_added)

    def test_ghost_outside_rows_added_is_rejected(self) -> None:
        """🔴 观测口径错了（幽灵不在 added 里）⇒ compute 侧当场抛，不得静默接受。"""
        with pytest.raises(OverwritePlanShapeError) as caught:
            self._recompute({ITEM: ("stale",)})
        assert "不在任何分区的 rows_added 里" in str(caught.value)


# ═══════════════════════════════════════════════════════════════════════════════
# §2 提交前复读比对（Requirement 3.5）—— 比**身份集合**，不比计数
#
# 两档期望集合（模块 docstring 第三节）：作用域内分区 = `(added − ghost) ∪ updated`
# （只由 plan 决定 ⇒ 这是对**计划**的独立交叉核，不是「prune 有没有照自己说的做」的自问自答）·
# 作用域外分区 = merge 之后观测到的那一份（逐元素原样）。
# ═══════════════════════════════════════════════════════════════════════════════

_IN_SCOPE = "S-in"
_OUT_SCOPE = "S-out"


def _sectioned_reader() -> Any:
    """一个带分区维度的 reader：`TABLE` 在作用域内、`SIBLING` 是兄弟分区。"""
    return _StubReader(
        item_id=ITEM,
        section_field=SECTION_FIELD,
        declared_scopes=((SIBLING, _OUT_SCOPE), (TABLE, _IN_SCOPE)),
    )


def _sectioned_payload(
    in_scope: tuple[str, ...], out_scope: tuple[str, ...]
) -> str:
    rows = [
        {_IDENTITY_KEY: identity, SECTION_FIELD: _IN_SCOPE} for identity in in_scope
    ] + [{_IDENTITY_KEY: identity, SECTION_FIELD: _OUT_SCOPE} for identity in out_scope]
    return json.dumps(rows, ensure_ascii=False)


class TestReadbackComparison:
    @staticmethod
    def _verify(plan: OverwritePlan, final: str, post: Mapping[str | None, frozenset[str]]):
        return AOA.verify_applied_plan(
            plan,
            final_payloads={ITEM: final},
            row_readers={ITEM: _sectioned_reader()},
            post_merge_ids={ITEM: post},
        )

    def test_matching_readback_is_silent(self) -> None:
        plan = _plan(added=("a1",), updated=("u1",), deleted=("d1",), section=_IN_SCOPE)
        post = {_IN_SCOPE: frozenset({"a1", "u1", "d1"}), _OUT_SCOPE: frozenset({"sib"})}
        assert self._verify(plan, _sectioned_payload(("a1", "u1"), ("sib",)), post) == []

    def test_right_count_but_wrong_row_is_caught(self) -> None:
        """🔴 本节的要害：删掉一条 declared 行、留下一条 undeclared 行 ⇒ **两侧计数相同**。"""
        plan = _plan(added=("a1",), updated=("u1",), deleted=("d1",), section=_IN_SCOPE)
        post = {_IN_SCOPE: frozenset({"a1", "u1", "d1"}), _OUT_SCOPE: frozenset({"sib"})}
        got = self._verify(plan, _sectioned_payload(("a1", "d1"), ("sib",)), post)
        assert len(got) == 1 and "多出 ['d1']" in got[0] and "缺失 ['u1']" in got[0]
        assert "计划期望 2 行、复读实得 2 行" in got[0], (
            f"两侧行数必须相同，否则这一例证不了「比集合不是比计数」，实得 {got}"
        )

    def test_sibling_partition_wiped_is_caught(self) -> None:
        """作用域外分区被删 ⇒ 打红（Requirement 1.2 / 1.4 最危险的失效形态）。"""
        plan = _plan(added=(), updated=("u1",), deleted=("d1",), section=_IN_SCOPE)
        post = {_IN_SCOPE: frozenset({"u1", "d1"}), _OUT_SCOPE: frozenset({"sib"})}
        got = self._verify(plan, _sectioned_payload(("u1",), ()), post)
        assert len(got) == 1 and _OUT_SCOPE in got[0] and "缺失 ['sib']" in got[0], got

    def test_ghost_row_is_a_known_legitimate_difference(self) -> None:
        """幽灵行**不**打红：期望集合已按 `(added − ghost) ∪ updated` 把它减掉。"""
        plan = OverwritePlan(
            deltas=(
                ItemOverwriteDelta(
                    item_id=ITEM,
                    table_key=TABLE,
                    row_section=_IN_SCOPE,
                    rows_added=("a1", "ghost"),
                    rows_updated=("u1",),
                    rows_ghost_dropped=("ghost",),
                ),
            ),
            store_rows_by_table={TABLE: 1},
            substrate_rows_by_table={TABLE: 3},
        )
        post = {_IN_SCOPE: frozenset({"a1", "u1"})}
        assert self._verify(plan, _sectioned_payload(("a1", "u1"), ()), post) == []
        # 反面：同一份计划下 ghost **真的在场**也算不符（它本该被门剔除掉）
        got = self._verify(plan, _sectioned_payload(("a1", "u1", "ghost"), ()), post)
        assert len(got) == 1 and "多出 ['ghost']" in got[0], got

    def test_empty_declared_table_means_the_partition_is_cleared(self) -> None:
        """声明为空元组 ⇒ 期望集合为空 ⇒ 库里还剩行就必须打红（Requirement 1.3 的执行侧）。"""
        plan = _plan(deleted=("d1", "d2"), section=_IN_SCOPE)
        post = {_IN_SCOPE: frozenset({"d1", "d2"})}
        assert self._verify(plan, _sectioned_payload((), ()), post) == []
        got = self._verify(plan, _sectioned_payload(("d1",), ()), post)
        assert len(got) == 1 and "多出 ['d1']" in got[0], got

    def test_mutant_comparing_counts_only_lets_the_wrong_row_through(self) -> None:
        """变异：比对换成只比**长度** ⇒ 「同数错行」静默放过 ⇒ 证明集合相等那条有牙。"""
        mutant = _source_mutant(
            AOA._diff_sections, old="if want == got:", new="if len(want) == len(got):", module=AOA
        )
        expected = {None: {"a1", "u1"}}
        actual = {None: {"a1", "d1"}}
        assert AOA._diff_sections(ITEM, expected=expected, actual=actual), "生产实现该打红"
        assert mutant(ITEM, expected=expected, actual=actual) == [], "变异没生效"

    def test_mutant_ignoring_out_of_scope_sections_lets_the_sibling_wipe_through(self) -> None:
        """变异：期望集合不以 merge 后快照为基准 ⇒ 兄弟分区被删也看不见。"""
        mutant = _source_mutant(
            AOA.verify_applied_plan,
            old="for section, ids in (post_merge_ids.get(item_id) or {}).items()",
            new="for section, ids in ()",
            module=AOA,
        )
        plan = _plan(added=(), updated=("u1",), deleted=("d1",), section=_IN_SCOPE)
        kwargs: dict[str, Any] = {
            "final_payloads": {ITEM: _sectioned_payload(("u1",), ())},
            "row_readers": {ITEM: _sectioned_reader()},
            "post_merge_ids": {ITEM: {_IN_SCOPE: frozenset({"u1", "d1"}), _OUT_SCOPE: frozenset({"sib"})}},
        }
        assert AOA.verify_applied_plan(plan, **kwargs), "生产实现该打红"
        assert mutant(plan, **kwargs) == [], "变异没生效"


# ═══════════════════════════════════════════════════════════════════════════════
# §3 删除侧**真落库**（假 session 观测真实发出的 SQL）
#
# 🔴 假 session 只替 DB，不替被测代码：`_snapshot_store` 的 SELECT 与删除侧的 UPDATE 都是
#    生产语句原样发出来的，本节观测的是「发了什么、写进去什么」。端点级真发 HTTP 归 Task 8.x，
#    真库对账归 Task 8.5 —— 本节不假装覆盖它们。
# ═══════════════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, *, value: Any = None, rowcount: int = 0) -> None:
        self._value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    """`checklist_responses` 的最小替身：SELECT 读 dict、UPDATE 写 dict 并记 rowcount。"""

    def __init__(self, store: dict[str, str | None], *, rowcount: int = 1) -> None:
        self.store = store
        self.rowcount = rowcount
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, statement: Any, params: Mapping[str, Any] | None = None) -> Any:
        sql = " ".join(str(statement).split())
        self.statements.append((sql, dict(params or {})))
        item = str((params or {}).get("item", ""))
        if sql.upper().startswith("SELECT"):
            return _FakeResult(value=self.store.get(item))
        self.store[item] = str((params or {})["val"])
        return _FakeResult(rowcount=self.rowcount)

    @property
    def writes(self) -> list[tuple[str, dict[str, Any]]]:
        return [pair for pair in self.statements if not pair[0].upper().startswith("SELECT")]


def _run_apply(
    *,
    pre_merge: str,
    post_merge: str,
    declared: tuple[str, ...],
    rowcount: int = 1,
    item_scopes: Mapping[str, Any] | None = None,
    reader: Any = None,
) -> tuple[Any, _FakeSession]:
    """算计划（用 pre-merge 载荷）→ 把库置成 post-merge 形态 → 跑删除侧。"""
    reader = reader or _StubReader(
        item_id=ITEM, declared_scopes=() if item_scopes else ((TABLE, None),)
    )
    baseline = _projection(**{TABLE: declared})
    inputs = _plan_inputs(reader, item_scopes=item_scopes)
    store_payloads = {ITEM: pre_merge}
    plan = ASR.compute_plan_for_adopt(
        baseline=baseline, store_payloads=store_payloads, plan_inputs=inputs
    )
    session = _FakeSession({ITEM: post_merge}, rowcount=rowcount)
    applied = asyncio.run(
        AOA.apply_overwrite_deletions(
            session,
            wp_id="aos63-wp",
            baseline=baseline,
            store_payloads=store_payloads,
            plan_inputs=inputs,
            plan=plan,
        )
    )
    return applied, session


class TestDeletionSideReallyWrites:
    def test_undeclared_row_is_pruned_and_written_back(self) -> None:
        applied, session = _run_apply(
            pre_merge=_payload("keep", "stale"),
            post_merge=_payload("keep", "stale", "add"),
            declared=("keep", "add"),
        )
        assert applied.rows_deleted_by_item == {ITEM: ("stale",)}
        assert len(session.writes) == 1, f"删除侧该发**恰 1** 条 UPDATE，实得 {session.writes}"
        sql, params = session.writes[0]
        assert sql.upper().startswith("UPDATE CHECKLIST_RESPONSES")
        assert params["wp"] == "aos63-wp" and params["item"] == ITEM
        assert _ids(params["val"]) == {"keep", "add"}, "写回的载荷不是剪枝后的行集"
        assert _ids(session.store[ITEM]) == {"keep", "add"}

    def test_nothing_to_delete_writes_nothing(self) -> None:
        """零删除 ⇒ 一条写都不发（连重序列化都不该发生）。"""
        applied, session = _run_apply(
            pre_merge=_payload("keep"),
            post_merge=_payload("keep", "add"),
            declared=("keep", "add"),
        )
        assert applied.rows_deleted_by_item == {}
        assert session.writes == []
        assert applied.mismatches == []

    def test_update_touching_zero_rows_is_a_mismatch(self) -> None:
        """🔴 「要删却写 0 行」必须 fail visible —— 计划报了删除而库里没删。"""
        applied, _session = _run_apply(
            pre_merge=_payload("keep", "stale"),
            post_merge=_payload("keep", "stale"),
            declared=("keep",),
            rowcount=0,
        )
        assert len(applied.mismatches) == 1 and "UPDATE 到 0 行" in applied.mismatches[0]

    def test_ghost_dropped_row_is_observed_from_the_database(self) -> None:
        """merge 之后 `add` 不在库里 ⇒ 观测成幽灵并回喂进最终计划。"""
        applied, _session = _run_apply(
            pre_merge=_payload("keep", "stale"),
            post_merge=_payload("keep", "stale"),
            declared=("keep", "add"),
        )
        assert applied.ghost_dropped_by_item == {ITEM: ("add",)}
        assert applied.plan.deltas[0].rows_ghost_dropped == ("add",)
        assert applied.mismatches == []

    def test_vanished_pre_existing_row_is_a_mismatch(self) -> None:
        """merge 之后连**已存在**的 `keep` 都没了 ⇒ 违规（不是幽灵）。"""
        applied, _session = _run_apply(
            pre_merge=_payload("keep", "stale"),
            post_merge=_payload("stale"),
            declared=("keep",),
        )
        assert applied.ghost_dropped_by_item == {}
        assert len(applied.mismatches) == 1 and "不是**本次新增" in applied.mismatches[0]

    def test_scope_override_items_can_delete(self) -> None:
        """🔴 `declared_scopes` 为空的那 3 条 item（D4-2 / D2-detail / H1-8 形态）也必须能删。

        它们的 scope 由 `AdoptPlanInputs.item_scopes` 从门面定义模块的 `ROWS_TABLE_KEY` 供入
        （Task 6.1）；而 `prune_undeclared_rows` 只读 `reader.declared_scopes` ⇒ 不套
        `_ScopedReader` 这层代理，删除侧会对这 3 条当场抛，而计划期明明算得出来。
        """
        applied, session = _run_apply(
            pre_merge=_payload("keep", "stale"),
            post_merge=_payload("keep", "stale"),
            declared=("keep",),
            item_scopes={ITEM: ((TABLE, None),)},
        )
        assert applied.rows_deleted_by_item == {ITEM: ("stale",)}
        assert _ids(session.store[ITEM]) == {"keep"}

    def test_scope_override_is_required_for_those_items(self) -> None:
        """反面：同一形态不给 `item_scopes` ⇒ 计划期就当场抛（证明上一例不是空转）。"""
        with pytest.raises(OverwritePlanShapeError):
            _run_apply(
                pre_merge=_payload("keep", "stale"),
                post_merge=_payload("keep", "stale"),
                declared=("keep",),
                reader=_StubReader(item_id=ITEM, declared_scopes=()),
            )

    def test_undeclared_table_is_not_touched_at_all(self) -> None:
        """作用域门：本次 projection 没声明这张表 ⇒ 一个字节都不碰（Requirement 1.2）。"""
        reader = _StubReader(item_id=ITEM, declared_scopes=((SIBLING, None),))
        baseline = _projection(**{TABLE: ("keep",)})
        inputs = _plan_inputs(reader)
        session = _FakeSession({ITEM: _payload("keep", "stale")})
        applied = asyncio.run(
            AOA.apply_overwrite_deletions(
                session,
                wp_id="aos63-wp",
                baseline=baseline,
                store_payloads={ITEM: _payload("keep", "stale")},
                plan_inputs=inputs,
                plan=ASR.compute_plan_for_adopt(
                    baseline=baseline,
                    store_payloads={ITEM: _payload("keep", "stale")},
                    plan_inputs=inputs,
                ),
            )
        )
        assert session.writes == [] and applied.rows_deleted_by_item == {}
        assert _ids(session.store[ITEM]) == {"keep", "stale"}

    def test_readback_after_apply_matches_the_final_plan(self) -> None:
        """端到端（假 DB）：删除侧写完 → 复读 → 与最终计划比对 ⇒ 相符。"""
        applied, session = _run_apply(
            pre_merge=_payload("keep", "stale"),
            post_merge=_payload("keep", "stale", "add"),
            declared=("keep", "add"),
        )
        got = AOA.verify_applied_plan(
            applied.plan,
            final_payloads={ITEM: session.store[ITEM]},
            row_readers={ITEM: _StubReader(item_id=ITEM, declared_scopes=((TABLE, None),))},
            post_merge_ids=applied.post_merge_ids,
        )
        assert got == [], got


# ═══════════════════════════════════════════════════════════════════════════════
# §4 应用模块的卫生（本轮**新增**的那个模块自己的约束）
#
# 🔴 既有 `test_aos_adopt_plan_gates_and_wire_form.py::TestTransactionDiscipline` 只扫
#    `adopt_substrate_response` 的 AST ⇒ 新模块在它的视野之外。本节把同一条铁律补上。
#    OO 路径隔离的完整判据（J1~J5）归 Task 7；本节只管「本轮新增的这个模块没碰那两侧」。
# ═══════════════════════════════════════════════════════════════════════════════


def _apply_module_ast() -> ast.Module:
    return ast.parse(inspect.getsource(AOA))


class TestApplyModuleHygiene:
    def test_no_commit_and_no_flush(self) -> None:
        """🔴 平台铁律：service 只 flush 不 commit —— 本模块连 flush 都不该有。

        事务边界是 `compute_adopt_substrate` 末尾那一处统一 commit；删除侧多提交一次，
        「不符即整体回滚」就只能回滚一半。
        """
        sites = [
            call.func.attr
            for call in ast.walk(_apply_module_ast())
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in ("commit", "flush")
        ]
        assert sites == [], f"应用模块出现了事务操作 {sites}"

    def test_does_not_touch_the_oo_execution_layer(self) -> None:
        """本模块不 import `store_mirror` / `oo_to_html`（ADR-AOS-001 的「OO 路径零改动」）。"""
        imported = {
            name.name if isinstance(node, ast.Import) else str(node.module or "")
            for node in ast.walk(_apply_module_ast())
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for name in (node.names or [])
        }
        blob = " ".join(sorted(imported))
        assert "store_mirror" not in blob and "oo_to_html" not in blob, blob
        # 变异对照：同一扫描器对**真的**被 import 的模块必须命中（否则它什么都没在数）
        assert "adopt_overwrite_plan" in blob

    def test_only_one_write_statement_and_it_is_an_update(self) -> None:
        """删除侧只有一条写语句且是 UPDATE —— INSERT 分支在删除侧永远不可达，不该存在。"""
        sql = " ".join(AOA._UPDATE_REMARK.split()).upper()
        assert sql.startswith("UPDATE CHECKLIST_RESPONSES")
        assert "WP_ID = :WP" in sql, "列名是 wp_id（不是 workpaper_id）"
        src = inspect.getsource(AOA)
        assert "INSERT INTO" not in src.upper()

    def test_plan_facade_is_the_one_from_the_service(self) -> None:
        """回喂重算走**同一个**计划门面（不直接调纯函数）⇒ ADR-AOS-003 对第二次计算同样成立。"""
        fn = next(
            node
            for node in ast.walk(_apply_module_ast())
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "apply_overwrite_deletions"
        )
        called = {
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "compute_plan_for_adopt" in called
        assert "compute_overwrite_plan" not in called, "绕过门面直接调纯函数 = 第二处算法"


# ═══════════════════════════════════════════════════════════════════════════════
# §5 源码锁：router 把 `AdoptPlanVerificationError` 映成 500，且分支排在兜底**之前**
#
# 🔴 本节是 `test_aos_adopt_plan_gates_and_wire_form.py` §9 第二条 `xfail(strict=True)`
#    摘除后的正面判据。原棘轮是纯文本 `split("except AdoptPlanVerificationError")[1][:300]`
#    里找 `status_code=500` —— 它**不查分支顺序**，而顺序恰恰是这条映射能否生效的全部：
#    该类是 `AdoptSubstrateError` 的子类，排在兜底之后**永远进不去**（会被静默映成 422）。
# 🔴 本节住在这里而不在 §11 旁边，是行数门禁所迫（两半同文件 802 行 > `.py` 上限 800）；
#    切口在两个 judge 之间 ⇒ 没有把任何「判据 + 它的变异反证」拆开，整组一起搬。
# 🔴 端点级真发 HTTP 归 Task 8.x；本节只防「映射漏接 / 排错位置被静默吞掉」。
# ═══════════════════════════════════════════════════════════════════════════════

#: 两个类名**取自类本身**（不写字面量）—— 判据盯的就是它们，名字改了要连带打红。
_VERIFY_ERROR = ASR.AdoptPlanVerificationError.__name__
_CATCH_ALL = ASR.AdoptSubstrateError.__name__


def _handler_names(handler: ast.ExceptHandler) -> list[str]:
    """一个 `except` 分支捕获的异常类名（元组形态也认全部）。"""
    if handler.type is None:
        return []
    return [node.id for node in ast.walk(handler.type) if isinstance(node, ast.Name)]


def judge_router_verification_mapping(tree: ast.Module) -> list[str]:
    """`AdoptPlanVerificationError` → 500 且分支排在兜底 `AdoptSubstrateError` **之前**。"""
    order: list[tuple[tuple[str, ...], tuple[int, ...]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "adopt_substrate":
            continue
        for block in (t for t in ast.walk(node) if isinstance(t, ast.Try)):
            for handler in block.handlers:
                codes = tuple(
                    int(kw.value.value)
                    for call in ast.walk(handler)
                    if isinstance(call, ast.Call)
                    and getattr(call.func, "id", "") == "HTTPException"
                    for kw in call.keywords
                    if kw.arg == "status_code" and isinstance(kw.value, ast.Constant)
                )
                order.append((tuple(_handler_names(handler)), codes))
    violations: list[str] = []
    mine = [i for i, (names, _c) in enumerate(order) if _VERIFY_ERROR in names]
    base = [i for i, (names, _c) in enumerate(order) if _CATCH_ALL in names]
    if not mine:
        violations.append(f"adopt_substrate 端点没有 {_VERIFY_ERROR} 的专属 except（实得 {order}）")
        return violations
    if order[mine[0]][1] != (500,):
        violations.append(f"{_VERIFY_ERROR} 的状态码是 {order[mine[0]][1]}（须恰 (500,)）")
    if base and mine[0] > base[0]:
        violations.append(
            f"{_VERIFY_ERROR} 分支（第 {mine[0]} 个）排在兜底 {_CATCH_ALL}（第 {base[0]} 个）"
            "**之后** —— 它是后者的子类，永远进不去，会被静默映成 422"
        )
    return violations


def _picked(block: ast.Try) -> list[ast.ExceptHandler]:
    return [h for h in block.handlers if _VERIFY_ERROR in _handler_names(h)]


class TestRouterMapsPlanVerificationTo500:
    @staticmethod
    def _tree() -> ast.Module:
        return ast.parse(_ROUTER_PY.read_bytes().decode("utf-8"))

    def test_production_satisfies_every_clause(self) -> None:
        assert judge_router_verification_mapping(self._tree()) == []

    def test_mutant_branch_removed_is_caught(self) -> None:
        """变异：摘掉该 except 分支 ⇒ 打红（「摘掉就打红」= 它真在数这个分支）。"""
        tree = self._tree()
        for block in (n for n in ast.walk(tree) if isinstance(n, ast.Try)):
            for handler in _picked(block):
                block.handlers.remove(handler)
        got = judge_router_verification_mapping(tree)
        assert len(got) == 1 and "没有" in got[0], got

    def test_mutant_wrong_status_code_is_caught(self) -> None:
        """变异：500 换成 422（= 落进兜底时的那个码）⇒ 打红。"""
        tree = self._tree()
        for block in (n for n in ast.walk(tree) if isinstance(n, ast.Try)):
            for handler in _picked(block):
                for call in ast.walk(handler):
                    if not isinstance(call, ast.Call):
                        continue
                    for kw in call.keywords:
                        if kw.arg == "status_code":
                            kw.value = ast.Constant(value=422)
        got = judge_router_verification_mapping(tree)
        assert len(got) == 1 and "(422,)" in got[0], got

    def test_mutant_branch_after_the_catch_all_is_caught(self) -> None:
        """变异：把该分支挪到兜底**之后** ⇒ 打红排序那一条。"""
        tree = self._tree()
        for block in (n for n in ast.walk(tree) if isinstance(n, ast.Try)):
            for handler in _picked(block):
                block.handlers.remove(handler)
                block.handlers.append(handler)
        got = judge_router_verification_mapping(tree)
        assert len(got) == 1 and "之后" in got[0], got

    def test_subclass_branch_after_the_catch_all_is_really_unreachable(self) -> None:
        """语言层实证：子类分支排在兜底之后**确实**永远进不去 —— 这是排序判据的**理由**。"""
        seen: list[str] = []
        try:
            raise ASR.AdoptPlanVerificationError("aos63")
        except ASR.AdoptSubstrateError:
            seen.append("兜底")
        except ASR.AdoptPlanVerificationError:  # pragma: no cover —— 正是要证它进不去
            seen.append("专属")
        assert seen == ["兜底"], seen
        assert issubclass(ASR.AdoptPlanVerificationError, ASR.AdoptSubstrateError)
