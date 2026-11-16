"""结算后复核探针的**八条形态判据**守卫（V1~V8 逐条驱动否定侧）。

spec `frozen-contract-read-path-and-legacy-operation-settlement` 任务 9
Requirements: R3.4
Property: **Property 3**（「状态变了但内容没落地」不可能出现）

本文件是 `test_sync_operation_settlement_probe.py` 的姊妹篇：那边守「探针是只读的」
「报告结构 / 可重跑 / 对拍口径 / CLI 契约」，这边守**判据本身真的会红**。

🔴 为什么拆两个文件：`check_file_size.py` 的阈值是 800 行（`splitlines()` 口径），
合起来 982 行会超限，而 memory 铁律明确「超 800 行须拆分而非加白名单」。

🔴 为什么判据要**逐条**驱动否定侧：本仓踩过「分支存在但没有任何判据锁着它」的坑
（`_build_error_code_status` 的矛盾登记分支）。八条判据里任何一条的否定侧没被驱动，
把它的 `return Verdict(ok=False, …)` 改成 `ok=True` 就**不会**打红 —— 那等于判据不存在。
"""

from __future__ import annotations

from typing import Any

import pytest

from scripts.check import sync_settlement_facts as FACTS
from scripts.check import sync_settlement_review as RULES

__all__: list[str] = []


def _chain(**overrides: Any) -> FACTS.VersionChain:
    """一条「已正确落地」的版本链基线；用例按需覆盖单个字段。"""
    base: dict[str, Any] = {
        "application_id": "app-1",
        "application_state": "applied",
        "definition_bundle_id": "bundle-1",
        "base_version_id": "cv-base",
        "base_representation_id": "rep-base",
        "current_revision": 11,
        "base_content_version_revision": 4,
        "result_representation_id": "rep-result",
        "result_revision": 5,
        "merged_projection_sha256": "a" * 64,
        "entry_state_present": True,
        "entry_current_representation_id": "rep-result",
        "entry_representation_generation": 1,
        "result_representation_generation": 1,
        "result_content_version_revision": 5,
        "room_id": "room-1",
    }
    base.update(overrides)
    return FACTS.VersionChain(**base)


def _rollup(**overrides: Any) -> FACTS.ConflictRollup:
    base: dict[str, Any] = {
        "total": 0,
        "resolved": 0,
        "abandoned": 0,
        "superseded": 0,
        "unsettled": 0,
        "triplet_complete": 0,
        "resolution_pair_complete": 0,
        "resolved_without_value": (),
    }
    base.update(overrides)
    return FACTS.ConflictRollup(**base)


def _event(seq: int, frm: str | None, to: str) -> FACTS.TimelineEvent:
    return FACTS.TimelineEvent(
        sequence_no=seq,
        from_state=frm,
        to_state=to,
        stage="s",
        actor_type="system",
        actor_id=None,
        error_code=None,
        occurred_at=f"2026-01-01T00:00:0{seq}+00:00",
    )


def _timeline(*pairs: tuple[str | None, str]) -> tuple[FACTS.TimelineEvent, ...]:
    return tuple(_event(i, frm, to) for i, (frm, to) in enumerate(pairs, 1))


# ═══════════════════════════════════════════════════════════════════════════
# 二、八条形态判据**真的会红**（逐条驱动否定侧）
# ═══════════════════════════════════════════════════════════════════════════


class TestEveryVerdictIsRegisteredAndReachable:
    def test_the_registry_lists_eight_unique_rules(self) -> None:
        assert len(RULES.ALL_VERDICTS) == 8
        assert len(set(RULES.ALL_VERDICTS)) == 8, "判据 id 有重复"

    def test_build_verdicts_emits_exactly_the_registry(self) -> None:
        """产出的 id 必须**逐值等于**登记表 —— 防「登记了却不执行」。"""
        produced = RULES.build_verdicts(
            state="applied",
            direction="oo_to_html",
            rollup=_rollup(),
            chain=_chain(),
            timeline=_timeline((None, "created"), ("created", "applied")),
        )
        assert tuple(v.rule_id for v in produced) == RULES.ALL_VERDICTS


class TestV1TerminalNeedsMatchingEvent:
    """V1：终态必须有落进该终态的 event。"""

    def test_a_terminal_without_its_event_is_red(self) -> None:
        """裸 SQL 改 state 的形态：timeline 停在 conflict 而 current state 是 superseded。"""
        verdict = RULES.verdict_operation_terminal_has_matching_event(
            state="superseded",
            timeline=_timeline((None, "created"), ("created", "conflict")),
            is_terminal_state=True,
        )
        assert verdict.ok is False
        assert "没有任何 to_state=superseded" in verdict.detail
        assert "裸 SQL" in verdict.detail, "红的原因必须点明形态"

    def test_a_terminal_with_its_event_is_green(self) -> None:
        verdict = RULES.verdict_operation_terminal_has_matching_event(
            state="superseded",
            timeline=_timeline(
                (None, "created"), ("created", "conflict"), ("conflict", "superseded")
            ),
            is_terminal_state=True,
        )
        assert verdict.ok is True
        assert "第 3 条 event 落定" in verdict.detail

    def test_a_non_terminal_state_is_not_applicable(self) -> None:
        verdict = RULES.verdict_operation_terminal_has_matching_event(
            state="conflict",
            timeline=_timeline((None, "created"), ("created", "conflict")),
            is_terminal_state=False,
        )
        assert verdict.ok is True
        assert "非终态，不适用" in verdict.detail


class TestV2SequenceIsContiguous:
    def test_a_gap_is_red(self) -> None:
        broken = (_event(1, None, "created"), _event(3, "conflict", "superseded"))
        verdict = RULES.verdict_event_sequence_is_contiguous(broken)
        assert verdict.ok is False
        assert "[1, 3]" in verdict.detail

    def test_an_empty_timeline_is_red(self) -> None:
        verdict = RULES.verdict_event_sequence_is_contiguous(())
        assert verdict.ok is False
        assert "一条 event 都没有" in verdict.detail

    def test_a_contiguous_timeline_is_green(self) -> None:
        verdict = RULES.verdict_event_sequence_is_contiguous(
            _timeline((None, "created"), ("created", "conflict"))
        )
        assert verdict.ok is True


class TestV3AbandonTripletIsAllOrNothing:
    """V3：三列同生共死。"""

    def test_a_partial_triplet_is_red(self) -> None:
        """🔴 变异 m2（superseded 允许三列不全）必须让本条红。"""
        verdict = RULES.verdict_abandon_triplet_is_all_or_nothing(
            _rollup(total=3, abandoned=3, triplet_complete=1)
        )
        assert verdict.ok is False
        assert "只有 1 条三列齐备" in verdict.detail
        assert "ck_wpsc_abandon_triplet" in verdict.detail

    def test_a_complete_triplet_is_green(self) -> None:
        verdict = RULES.verdict_abandon_triplet_is_all_or_nothing(
            _rollup(total=3, abandoned=3, triplet_complete=3)
        )
        assert verdict.ok is True

    def test_no_abandonment_at_all_is_green(self) -> None:
        """三列全空是**合法态**（未作废）—— 不许把它判红。"""
        verdict = RULES.verdict_abandon_triplet_is_all_or_nothing(_rollup(total=24))
        assert verdict.ok is True
        assert "三列全空是合法态" in verdict.detail


class TestV4ResolutionPairIsAllOrNothing:
    def test_a_broken_pair_is_red(self) -> None:
        verdict = RULES.verdict_resolution_pair_is_all_or_nothing(
            _rollup(total=3, resolved=2, resolution_pair_complete=1)
        )
        assert verdict.ok is False
        assert "只有 1 条成对" in verdict.detail

    def test_a_resolution_without_value_is_red(self) -> None:
        """`resolved_at` 有但 `resolved_value` 空 —— 事后无法证明裁决落到哪个值。"""
        verdict = RULES.verdict_resolution_pair_is_all_or_nothing(
            _rollup(total=1, resolved=1, resolution_pair_complete=1, resolved_without_value=("c-1",))
        )
        assert verdict.ok is False
        assert "resolved_value" in verdict.detail

    def test_a_complete_resolution_is_green(self) -> None:
        verdict = RULES.verdict_resolution_pair_is_all_or_nothing(
            _rollup(total=1, resolved=1, resolution_pair_complete=1)
        )
        assert verdict.ok is True


class TestV5AppliedHasApplication:
    """V5：`oo_to_html` 的已落地终态必须有 application；`html_to_oo` 不适用。"""

    def test_oo_to_html_without_application_is_red(self) -> None:
        verdict = RULES.verdict_applied_has_application(
            state="applied",
            direction="oo_to_html",
            chain=_chain(application_id=None, application_state=None),
        )
        assert verdict.ok is False
        assert "没有 application_id" in verdict.detail

    def test_html_to_oo_without_application_is_green(self) -> None:
        """🔴 方向分型的关键：784 条真实 `applied` 的 `html_to_oo` 都没有 application。

        不做分型 = 784 条假红。
        """
        verdict = RULES.verdict_applied_has_application(
            state="applied", direction="html_to_oo", chain=_chain(application_id=None)
        )
        assert verdict.ok is True
        assert "Property 64" in verdict.detail

    def test_html_to_oo_without_room_is_red(self) -> None:
        """该方向的落地证据是 room —— 没有它就没有任何落地痕迹。"""
        verdict = RULES.verdict_applied_has_application(
            state="applied",
            direction="html_to_oo",
            chain=_chain(application_id=None, room_id=None),
        )
        assert verdict.ok is False
        assert "room_id" in verdict.detail

    def test_a_conflict_state_is_not_applicable(self) -> None:
        verdict = RULES.verdict_applied_has_application(
            state="conflict", direction="oo_to_html", chain=_chain(application_id=None)
        )
        assert verdict.ok is True


class TestV6AppliedHasNewRepresentation:
    """V6：已落地必须有新 representation 且 content revision 前进（任务原文的例子）。"""

    def test_no_result_representation_is_red(self) -> None:
        """🔴 变异 m1（applied 允许零新 representation）必须让本条红。"""
        verdict = RULES.verdict_applied_has_new_representation(
            state="applied",
            direction="oo_to_html",
            chain=_chain(
                result_representation_id=None,
                result_representation_generation=None,
                result_content_version_revision=None,
            ),
        )
        assert verdict.ok is False
        assert "result_representation_id 为空" in verdict.detail
        assert "状态变了但内容没落地" in verdict.detail

    def test_reusing_the_base_representation_is_red(self) -> None:
        verdict = RULES.verdict_applied_has_new_representation(
            state="applied", direction="oo_to_html", chain=_chain(result_representation_id="rep-base")
        )
        assert verdict.ok is False
        assert "没有新代际" in verdict.detail

    def test_a_missing_representation_row_is_red(self) -> None:
        """外键非空但行读不回来 —— 这正是「只查 operation 表」会漏掉的形态。"""
        verdict = RULES.verdict_applied_has_new_representation(
            state="applied",
            direction="oo_to_html",
            chain=_chain(result_representation_generation=None),
        )
        assert verdict.ok is False
        assert "行不存在" in verdict.detail

    def test_a_non_advancing_revision_is_red(self) -> None:
        verdict = RULES.verdict_applied_has_new_representation(
            state="applied",
            direction="oo_to_html",
            chain=_chain(result_content_version_revision=4, base_content_version_revision=4),
        )
        assert verdict.ok is False
        assert "没有前进" in verdict.detail

    def test_the_baseline_is_the_base_version_not_wp_content_revision(self) -> None:
        """🔴 基线口径的可证伪断言。

        现算真实数据：`0d79eaf5` 的 `current_revision`(wp.content_revision)=11 而
        `result_revision`=5、`base_version.revision`=4。若判据拿 `current_revision`
        当基线，它会红（5 <= 11）—— 而这是**正确实现**。

        本条把「必须用 base_content_version_revision」写成断言：造出那个真实形态，
        判据必须**绿**。
        """
        verdict = RULES.verdict_applied_has_new_representation(
            state="applied",
            direction="oo_to_html",
            chain=_chain(
                current_revision=11,
                base_content_version_revision=4,
                result_revision=5,
                result_content_version_revision=5,
            ),
        )
        assert verdict.ok is True, "拿 wp.content_revision 当基线会把这 4 条真实数据判成缺陷（假红）"
        assert "4 → 5" in verdict.detail

    def test_refresh_required_is_treated_as_landed(self) -> None:
        """`refresh_required` 也是「内容已写进库」的终态（`_apply_settled` 的另一分支）。"""
        assert RULES.is_landed_terminal("refresh_required") is True
        assert RULES.is_landed_terminal("applied") is True

    @pytest.mark.parametrize("state", ["duplicate", "rejected", "superseded", "conflict", "error"])
    def test_other_states_are_not_landed(self, state: str) -> None:
        """`duplicate` 也是终态但它不落地内容 —— 必须排除（`error` 可重试，非终态）。"""
        assert RULES.is_landed_terminal(state) is False

    def test_html_to_oo_is_not_applicable(self) -> None:
        verdict = RULES.verdict_applied_has_new_representation(
            state="applied", direction="html_to_oo", chain=_chain()
        )
        assert verdict.ok is True
        assert "不发布 representation" in verdict.detail


class TestV7SupersededCreatedNoRepresentation:
    """V7：作废终态不得造新内容，且必须三列齐备（任务原文第二个方向）。"""

    def test_superseded_with_partial_triplet_is_red(self) -> None:
        """🔴 变异 m2（superseded 允许三列不全）的另一半：本条独立成立。"""
        verdict = RULES.verdict_superseded_created_no_representation(
            state="superseded",
            rollup=_rollup(total=3, abandoned=3, triplet_complete=2),
            chain=_chain(application_id=None, result_representation_id=None),
        )
        assert verdict.ok is False
        assert "三列齐备的只有 2/3" in verdict.detail

    def test_superseded_with_a_new_representation_is_red(self) -> None:
        """「superseded 却新建了 representation」—— 与 V6 互斥的另一半。"""
        verdict = RULES.verdict_superseded_created_no_representation(
            state="superseded",
            rollup=_rollup(total=3, abandoned=3, triplet_complete=3),
            chain=_chain(),
        )
        assert verdict.ok is False
        assert "作废路径却产生了 result representation" in verdict.detail

    def test_superseded_with_untouched_rows_is_red(self) -> None:
        verdict = RULES.verdict_superseded_created_no_representation(
            state="superseded",
            rollup=_rollup(total=3, abandoned=2, triplet_complete=2, unsettled=1),
            chain=_chain(result_representation_id=None),
        )
        assert verdict.ok is False
        assert "只有 2/3 条冲突行被作废" in verdict.detail

    def test_superseded_with_no_conflicts_is_red(self) -> None:
        """没有可作废的对象 ⇒ 作废事实不可复核。"""
        verdict = RULES.verdict_superseded_created_no_representation(
            state="superseded", rollup=_rollup(), chain=_chain(result_representation_id=None)
        )
        assert verdict.ok is False
        assert "一条冲突行都没有" in verdict.detail

    def test_a_correct_abandon_is_green(self) -> None:
        verdict = RULES.verdict_superseded_created_no_representation(
            state="superseded",
            rollup=_rollup(total=24, abandoned=24, triplet_complete=24),
            chain=_chain(application_id=None, result_representation_id=None),
        )
        assert verdict.ok is True

    def test_the_abandon_terminal_is_read_from_the_service(self) -> None:
        """终态取值从任务 8 的常量现读 —— 不写字面量（两处会漂）。"""
        from app.services.workpaper_sync.conflict_abandon import ABANDON_TERMINAL_STATE

        assert RULES.is_abandon_terminal(ABANDON_TERMINAL_STATE.value) is True
        assert RULES.is_abandon_terminal("applied") is False


class TestV8AppliedHasNoOpenConflict:
    def test_open_conflicts_on_an_applied_operation_are_red_but_tagged(self) -> None:
        """🔴 判据照实判红，但带上已登记缺口 id —— 不因「已登记」而降级为绿。"""
        verdict = RULES.verdict_applied_has_no_open_conflict(
            state="applied",
            direction="oo_to_html",
            rollup=_rollup(total=108, superseded=54, unsettled=54),
        )
        assert verdict.ok is False
        assert verdict.known_gap == "legacy_oo_applied_unsettled_conflicts"
        assert "54/108" in verdict.detail

    def test_all_settled_is_green(self) -> None:
        verdict = RULES.verdict_applied_has_no_open_conflict(
            state="applied", direction="oo_to_html", rollup=_rollup(total=3, resolved=3)
        )
        assert verdict.ok is True

    def test_a_conflict_state_is_not_applicable(self) -> None:
        """冲突态本来就有未处理行 —— 不许把它判红。"""
        verdict = RULES.verdict_applied_has_no_open_conflict(
            state="conflict", direction="oo_to_html", rollup=_rollup(total=24, unsettled=24)
        )
        assert verdict.ok is True
        assert "正常形态" in verdict.detail
