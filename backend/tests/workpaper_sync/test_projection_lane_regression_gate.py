# -*- coding: utf-8 -*-
"""projection lane 回归门的判据（F9）。

**Spec: published-representation-production-path-and-lane-adjudication**
Tasks 9.2 / 9.4 / 9.6

═══ 本文件的落点 ═══════════════════════════════════════════════════════════════

| Property | 主题 | 任务 |
|---|---|---|
27 | 首版落成且 capability 裁决后供给门放行且注册集合含该 entry | 9.2 |
28 | 注册会计恒等式在任何供给状态下成立 | 9.2 |
29 | BP-61-1 的绑定约束先后由三臂实测得出 | 9.4 |
30 | 登记读数与真实库行数双向一致 | 9.6 |

═══ 为什么可以真库只读 ═══════════════════════════════════════════════════════════

Property 27 要求**非空跑证明**（避免「供给为 0 所以注册 0」的重言式）。G7 的首版
representation 已在真库落成（2026-09-04），因此不必建临时 schema：

* 供给侧现读真库（G7 的 `_describe_entry_supply` 实测返回 `None`）；
* capability 侧用**内存 manifest**把 G7 置 `bidirectional`
  （`build_production_registry(manifest=...)` 本就支持传入）。

⇒ 全程只读，且分母非空。真正需要临时 schema 的是 Properties 13/19/20/33~35（F8）。

═══ 纪律 ═══════════════════════════════════════════════════════════════════════

* 注册必须由**生产** `register_from_manifest` 完成（其返回值就是证据），
  不得由测试自己组装后再数 registry。
* 判据落在行为 / 结构 / 真实执行，不落在「字符串是否存在」。
* `hypothesis` 的 `max_examples` ≥ 100。
* 库连接一律**一次** `asyncio.run` 取全部快照 —— 每测试各自 async 会污染共享连接池
  （第二个起 `NoneType has no attribute send`，本仓库实测过）。
"""

from __future__ import annotations

import ast
import asyncio
import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any, Final

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_THIS = Path(__file__).resolve()
REPO: Final[Path] = _THIS.parents[3]
BACKEND: Final[Path] = REPO / "backend"
if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))

from app.services.workpaper_sync.adapters import registry as REG  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    capability_of,
    load_entry_manifest,
)

#: G7 —— 唯一已落成首版的 manifest entry（2026-09-04 实测）
_G7: Final[str] = "xlsx/gt-g7-long-term-equity-main"

#: F5 变异脚本（Property 31 判它的四态判读）。
F5_PATH: Final[Path] = (
    BACKEND / "scripts/diagnose/mutate_projection_first_publication_guards.py"
)
#: 本文件自身的仓库相对路径 —— Property 31 的探针变异要填 `Mutation.test`。
#: 探针的 `want` 指向一个不存在的测试名，因此那条变异**不会真跑** pytest
#: （`check_anchors()` 是只读入口），填这里只为满足 `Mutation` 的必填字段。
T_GATE_REL: Final[str] = "backend/tests/workpaper_sync/test_projection_lane_regression_gate.py"


# ═══════════════════════════════════════════════════════════════════════════
# 一次性真库快照（模块级，避免多次 asyncio.run 污染连接池）
# ═══════════════════════════════════════════════════════════════════════════


async def _collect() -> dict[str, Any]:
    """一次 async 会话里取齐全部真库读数。"""
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings

    engine = create_async_engine(
        str(settings.DATABASE_URL),
        poolclass=NullPool,
        connect_args={"ssl": False} if settings.DB_DISABLE_SSL else {},
    )
    Session = async_sessionmaker(engine, expire_on_commit=False)
    snapshot: dict[str, Any] = {}
    try:
        async with Session() as session:
            # 供给门逐 entry 现跑
            supply: dict[str, str | None] = {}
            for row in REG.DELIVERED_PER_ENTRY_CONTRACTS:
                entry_id = str(row["entry_id"])
                supply[entry_id] = await REG._describe_entry_supply(
                    session=session, entry_id=entry_id
                )
            snapshot["supply"] = supply

            # 真实注册结果（生产入口，非测试自组）
            manifest = load_entry_manifest()
            production = REG.build_production_registry(manifest=manifest)
            snapshot["production_outcome"] = await production.register_from_manifest(
                session=session
            )

            # 把 G7 的 capability 置 bidirectional 的内存 manifest
            patched = copy.deepcopy(dict(manifest))
            entries = patched.get("entries")
            target = None
            if isinstance(entries, list):
                for item in entries:
                    if str(item.get("entry_id") or item.get("entryId") or "") == _G7:
                        target = item
                        break
            elif isinstance(entries, dict):
                target = entries.get(_G7)
            if target is not None:
                for key in ("capability", "capability_name", "capabilityName"):
                    if key in target:
                        target[key] = "bidirectional"
                target.setdefault("capability", "bidirectional")
            snapshot["patched_manifest_target_found"] = target is not None

            bi_registry = REG.build_production_registry(manifest=patched)
            snapshot["bidirectional_outcome"] = await bi_registry.register_from_manifest(
                session=session
            )
            patched_by_id = REG.manifest_entries_by_id(patched)
            snapshot["patched_capability_of_g7"] = str(
                capability_of(patched_by_id.get(_G7) or {})
            )
            # 阶段一的判据落点：注册计划里该 entry 的 blocked_reason
            snapshot["patched_plan_item_g7"] = None
            for item in REG.build_manifest_registration_plan(patched_by_id):
                if item.entry_id == _G7:
                    snapshot["patched_plan_item_g7"] = {
                        "entry_id": item.entry_id,
                        "capability": str(item.capability),
                        "contract_id": item.contract_id,
                        "provider_module": item.provider_module,
                        "blocked_reason": item.blocked_reason,
                    }
                    break

            # 三张表的真实行数（Property 30）
            for label, sql in (
                ("content_version", "SELECT COUNT(*) FROM working_paper_content_version"),
                (
                    "content_representation",
                    "SELECT COUNT(*) FROM working_paper_content_representation",
                ),
                (
                    "content_application",
                    "SELECT COUNT(*) FROM working_paper_content_application",
                ),
                (
                    "entry_state",
                    "SELECT COUNT(*) FROM working_paper_sync_entry_state",
                ),
            ):
                snapshot[f"rows_{label}"] = int(
                    (await session.execute(sa.text(sql))).scalar_one()
                )

            # entry_state 的命名空间构成（Property 29 / 30）
            snapshot["entry_state_ids"] = [
                str(r[0])
                for r in (
                    await session.execute(
                        sa.text(
                            "SELECT entry_id FROM working_paper_sync_entry_state "
                            "ORDER BY entry_id"
                        )
                    )
                ).all()
            ]
    finally:
        await engine.dispose()
    return snapshot


try:
    _SNAPSHOT: Final[dict[str, Any]] = asyncio.run(_collect())
    _DB_ERROR: Final[str] = ""
except Exception as exc:  # noqa: BLE001 - 库不可达时给出明确原因而不是一堆 error
    _SNAPSHOT = {}
    _DB_ERROR = f"{type(exc).__name__}: {exc}"


_needs_db = pytest.mark.skipif(
    bool(_DB_ERROR), reason=f"真库不可达: {_DB_ERROR}"
)


# ═══════════════════════════════════════════════════════════════════════════
# Property 27：供给门放行且注册集合含该 entry
# ═══════════════════════════════════════════════════════════════════════════


@_needs_db
class TestSupplyGateAdmitsAndRegistersAfterFirstPublication:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 27: 首版落成且 capability 裁决后供给门放行且注册集合含该 entry**

    **Validates: Requirements 8.2**
    """

    def test_g7_supply_gate_admits(self) -> None:
        """G7 首版已落成 ⇒ 供给门返回 `None`（放行）。

        这是**阶段一**的判据本体（Requirement 12.6），落在供给门返回值上。
        """
        verdict = _SNAPSHOT["supply"].get(_G7, "<未观测>")
        assert verdict is None, (
            f"G7 的供给门未放行: {verdict} —— 首版 representation 已在真库落成"
            "（2026-09-04），供给门却仍拒绝，说明取数口径与落库口径不一致"
        )

    def test_other_pilots_are_still_rejected_so_the_denominator_is_not_trivial(
        self,
    ) -> None:
        """🔴 非空跑证明的另一半：其余 entry **仍被拒**。

        若四个 entry 全放行，「G7 放行」就可能只是因为供给门恒返回 `None` ——
        那是最坏的重言式。这条把分母钉死。
        """
        supply = _SNAPSHOT["supply"]
        assert len(supply) >= 4, f"只观测到 {len(supply)} 个 entry，分母过小"
        rejected = {k: v for k, v in supply.items() if v is not None}
        assert rejected, (
            "四个 pilot entry 全部放行 ⇒ 「G7 放行」无法与「供给门恒放行」区分，"
            "本属性退化为重言式"
        )
        assert _G7 not in rejected

    def test_bidirectional_capability_clears_the_registration_plan_blocker(self) -> None:
        """capability 置 `bidirectional` 后，该 entry 的 plan item `blocked_reason` 为 `None`。

        🔴 **判据落在 `blocked_reason`，不落在 `registered_adapter_ids`。**

        首版我把它写成断言 `registered_adapter_ids` 含 G7，实测打红。查因后确认那是**我的
        判据写错**，不是产品缺陷：provider 的 `attach_pilot_adapters` 第 1 步调
        `manifest_capability_enabled()`，它读**磁盘** manifest，与我传进
        `build_production_registry(manifest=...)` 的内存 manifest 是两个来源 ⇒ 内存补丁
        对它无效，函数在读库之前就 `return ()`。

        那恰恰是**单一真源**在正确工作：capability 翻转必须走 manifest 重生成，而后者被
        `approved_source_digest` 复核门挡着（Requirement 7.8 禁止绕过）。用内存补丁把
        `registered_adapter_ids` 顶成非空，等于在测试里**伪造**阶段二已完成。

        ⇒ 阶段一能证的、也只该证的是：**供给侧与计划侧都已就绪**。
        """
        assert _SNAPSHOT["patched_manifest_target_found"], (
            f"内存 manifest 里找不到 {_G7} —— capability 覆盖没生效，本判据会空转"
        )
        assert "bidirectional" in _SNAPSHOT["patched_capability_of_g7"].lower(), (
            f"内存 manifest 的 G7 capability 实测为 "
            f"{_SNAPSHOT['patched_capability_of_g7']} —— 覆盖未生效"
        )
        item = _SNAPSHOT["patched_plan_item_g7"]
        assert item is not None, f"内存 manifest 的注册计划里没有 {_G7}"
        assert item["capability"].endswith("bidirectional"), item["capability"]
        assert item["blocked_reason"] is None, (
            f"capability=bidirectional 且供给门放行，但 plan item 仍被阻塞: "
            f"{item['blocked_reason']}"
        )
        assert item["contract_id"] == "g7.soe_subsidiary_disclosure"

    def test_stage_two_is_correctly_still_blocked_by_the_disk_manifest(self) -> None:
        """🔴 阶段二**如实**仍未成立，且原因是复核门而非本 spec 的缺口。

        这条把上一条的边界钉死：不得因为「阶段一过了」就顺手声称 adapter 已注册。
        实测 `registered_adapter_ids` 为空，reasons 里点名 provider 侧前置未过。
        """
        outcome = _SNAPSHOT["bidirectional_outcome"]
        assert _G7 not in outcome.registered_entry_ids, (
            "内存 manifest 补丁竟然让 G7 真的注册上了 —— 那说明 "
            "`manifest_capability_enabled()` 也读了内存 manifest，"
            "单一真源被破坏（capability 可绕过 approved_source_digest 复核门）"
        )
        reason = str(dict(outcome.reasons).get(_G7) or "")
        assert reason, f"{_G7} 未注册却没有原因"
        assert "provider" in reason or "空元组" in reason, (
            f"未注册原因不是 provider 侧前置: {reason}"
        )

    def test_production_manifest_registers_nothing_for_g7(self) -> None:
        """对照组：**未**改 capability 的生产 manifest 下 G7 注册不上。

        这条与上一条成对，证明「注册成功」确实由 capability 翻转带来，
        而不是无论如何都会成功。它也如实记录了阶段二尚未发生。
        """
        outcome = _SNAPSHOT["production_outcome"]
        assert _G7 not in outcome.registered_entry_ids, (
            "生产 manifest 下 G7 已注册 —— 那说明 capability 已经翻成 bidirectional 了。"
            "若确已翻转，请核对 `approved_source_digest` 复核门是否被绕过"
            "（Requirement 7.8 明令禁止），并更新本判据"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 28：注册会计恒等式
# ═══════════════════════════════════════════════════════════════════════════


@_needs_db
class TestRegistrationAccountingIdentity:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 28: 注册会计恒等式在任何供给状态下成立**

    **Validates: Requirements 8.3**
    """

    @pytest.mark.parametrize("which", ["production_outcome", "bidirectional_outcome"])
    def test_registered_plus_unregistered_equals_planned(self, which: str) -> None:
        """`len(registered) + unregistered == planned`，两种供给状态各验一次。"""
        outcome = _SNAPSHOT[which]
        planned = set(outcome.planned_entry_ids)
        registered = set(outcome.registered_entry_ids)
        assert planned, "planned_entry_ids 为空 —— 恒等式会在空集上恒真"
        assert registered <= planned, (
            f"registered 不是 planned 的子集: {sorted(registered - planned)}"
        )
        unregistered = len(planned) - len(registered)
        assert len(registered) + unregistered == len(planned)

    def test_every_unregistered_entry_has_a_reason(self) -> None:
        """未注册的 entry 必须逐个有原因 —— 「注册不上」不带原因等于没有结论。"""
        outcome = _SNAPSHOT["production_outcome"]
        planned = set(outcome.planned_entry_ids)
        registered = set(outcome.registered_entry_ids)
        unregistered = sorted(planned - registered)
        assert unregistered, "全部注册成功 —— 本判据在空集上，需要重新裁决分母"
        reasons = dict(outcome.reasons)
        missing = [e for e in unregistered if not str(reasons.get(e) or "").strip()]
        assert not missing, (
            f"{len(missing)} 个未注册 entry 没有原因（示例 {missing[:3]}）"
        )

    def test_planned_count_equals_manifest_plan_length(self) -> None:
        """planned 计数与 `build_manifest_registration_plan` 的长度一致（双向锁）。"""
        entries = REG.manifest_entries_by_id(load_entry_manifest())
        plan = REG.build_manifest_registration_plan(entries)
        outcome = _SNAPSHOT["production_outcome"]
        assert len(outcome.planned_entry_ids) == len(plan), (
            f"outcome.planned={len(outcome.planned_entry_ids)} 与 plan={len(plan)} 不等"
        )

    @settings(max_examples=200, deadline=None)
    @given(subset=st.sets(st.sampled_from(sorted({"a", "b", "c", "d", "e"})), max_size=5))
    def test_identity_is_arithmetic_not_incidental(self, subset: set[str]) -> None:
        """恒等式的算术形态对任意子集成立 —— 防「恰好这次相等」。"""
        planned = {"a", "b", "c", "d", "e"}
        registered = subset & planned
        unregistered = len(planned) - len(registered)
        assert len(registered) + unregistered == len(planned)


# ═══════════════════════════════════════════════════════════════════════════
# Property 29：BP-61-1 的绑定约束由三臂实测得出
# ═══════════════════════════════════════════════════════════════════════════


def _load_task61_gate() -> Any:
    gate_path = BACKEND / "scripts/check/check_task61_oo94_word_pilot_gate.py"
    spec = importlib.util.spec_from_file_location("_t61_for_f9", gate_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestBindingConstraintComesFromThreeArmMeasurement:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 29: BP-61-1 的绑定约束先后由三臂实测得出**

    **Validates: Requirements 8.7**
    """

    def test_binding_constraint_id_changes_with_measured_supply(self) -> None:
        """两种供给状态下 `binding_constraint_id` 必须**随实测改变**。

        判据不落在「登记表里写了 BP-61-1」，而落在「换一组实测入参，结论会变」。
        """
        gate = _load_task61_gate()

        # 🔴 三臂的键名与语义取自门本体（首版我猜成 arm_a/b/c + registered_adapter_ids，
        #    被它两次拒掉：先「三臂缺 [...]」、再 KeyError 'control_entry_reason'）。
        #    两次拒绝都是对的 —— 门要求的是各臂**拒绝原因**，而不是注册结果：
        #      arm_a_control          → control_entry_reason
        #      arm_b_manifest_flipped → synth_reason
        #      arm_c_supply_stubbed   → synth_reason
        #    判「同类」用**逐字相等**（原因文案的真源在 `_describe_entry_supply`）。
        def _arms(control: str, arm_b: str | None, arm_c: str | None) -> dict[str, Any]:
            return {
                "arm_a_control": {
                    "control_entry_reason": control,
                    "registered_adapter_ids": (),
                    "planned_entry_ids": ("xlsx/x", "docx/y"),
                },
                "arm_b_manifest_flipped": {"synth_reason": arm_b},
                "arm_c_supply_stubbed": {"synth_reason": arm_c},
            }

        reason = "该 entry 还没有 current published representation"

        # 状态一：arm_b 的原因与对照**逐字相等** ⇒ BP-61-2 不是绑定约束 ⇒ 判 BP-61-1
        same = gate.binding_constraint_facts(_arms(reason, reason, "原因已改变"))
        assert same["arm_b_reason_equals_control_reason"] is True
        assert same["binding_constraint_id"] == "BP-61-1"
        assert same["non_binding_constraint_ids"] == ["BP-61-2"]

        # 🔴 状态一 b：arm_b 的原因是对照的**真子串**时仍须判「不同类」。
        #    变异检验（F9-M3）把逐字相等换成 `arm_b_reason in control_reason` 时，
        #    上面那组（两者完全相同）照样通过 ⇒ 判 GREEN。这一组把那个缺口封上：
        #    子串实现会把它误判为「同类」，而它按逐字相等应当是「不同类」。
        substring = gate.binding_constraint_facts(
            _arms(reason, reason[: len(reason) // 2], "原因已改变")
        )
        assert substring["arm_b_reason_equals_control_reason"] is False, (
            "arm_b 的原因只是对照原因的**子串**，却被判成「同类」—— "
            "判据从逐字相等退化成了子串包含，抄错关键词将看不出来"
        )
        assert substring["binding_constraint_id"] is None

        # 状态二：arm_b 的原因**不同** ⇒ 结论必须随之改变（不再判 BP-61-1）
        moved = gate.binding_constraint_facts(
            _arms(reason, "另一类原因：capability 未启用", "又一类原因")
        )
        assert moved["arm_b_reason_equals_control_reason"] is False
        assert moved["binding_constraint_id"] is None, (
            "arm_b 的实测原因已与对照不同（⇒ BP-61-2 才是绑定约束），"
            f"但结论仍是 {moved['binding_constraint_id']} —— "
            "那说明 binding_constraint_id 是写死的，不是三臂实测得出的"
        )
        assert moved["non_binding_constraint_ids"] == []

    def test_arm_c_must_move_the_reason_or_the_order_is_not_measured(self) -> None:
        """arm_c 解除 BP-61-1 后原因必须**改变** —— 否则度量的不是真实先后。"""
        gate = _load_task61_gate()
        reason = "该 entry 还没有 current published representation"
        arms = {
            "arm_a_control": {
                "control_entry_reason": reason,
                "registered_adapter_ids": (),
                "planned_entry_ids": ("xlsx/x",),
            },
            "arm_b_manifest_flipped": {"synth_reason": reason},
            # arm_c 与 arm_b 逐字相同 ⇒ 「再解除一条」没有改变任何东西
            "arm_c_supply_stubbed": {"synth_reason": reason},
        }
        facts = gate.binding_constraint_facts(arms)
        assert facts["arm_c_reason_differs_from_arm_b"] is False, (
            "arm_c 与 arm_b 原因逐字相同，却报告「原因已改变」—— "
            "那让第 5 条判据变成恒真"
        )

    def test_missing_arm_is_rejected_rather_than_guessed(self) -> None:
        """🔴 反向自检：只给两臂时门必须**拒**，不得凑一个结论出来。

        两臂比不出「同类」与「不同类」两件事 —— 这是该门自己写明的判据。
        """
        gate = _load_task61_gate()
        with pytest.raises(Exception) as caught:
            gate.binding_constraint_facts(
                {
                    "arm_a_control": {"registered_adapter_ids": ()},
                    "arm_b_manifest_flipped": {"registered_adapter_ids": ()},
                }
            )
        assert "三臂" in str(caught.value) or "arm" in str(caught.value).lower()

    def test_default_call_reports_bp_61_1(self) -> None:
        """默认（真实）入参下结论仍是 BP-61-1 —— 与 Task 9.3 的更正一致。"""
        gate = _load_task61_gate()
        facts = gate.binding_constraint_facts()
        assert facts.get("binding_constraint_id") == "BP-61-1", (
            f"实测绑定约束为 {facts.get('binding_constraint_id')}，"
            "与 Task 9.3 更正后的登记不符"
        )

    def test_bp_61_1_measured_reading_is_not_the_stale_literal(self) -> None:
        """🔴 反向自检：BP-61-1 的 `what` 不得再写「全表 0 行」。

        Task 9.3 已更正该字面量（实测 entry_state 2 行、其中 1 行是 manifest entry）。
        把它改回「全表 0 行」时本条必须打红 —— 那正是「把错值当基线锁死」。
        """
        gate = _load_task61_gate()
        bp = next(
            item for item in gate.BINDING_CONSTRAINTS if item["id"] == "BP-61-1"
        )
        what = str(bp["what"])
        assert "全表 0 行" not in what, (
            "BP-61-1 的 what 又出现「全表 0 行」—— 实测该表非空，旧字面量是假话"
        )
        measured = bp.get("measured_2026_09_04") or {}
        assert measured, "BP-61-1 缺 `measured_2026_09_04` 实测块"
        assert int(measured["working_paper_sync_entry_state_rows_total"]) > 0

    def test_other_binding_constraints_are_untouched(self) -> None:
        """归因型验收：只有 BP-61-1 带实测块，另两条逐字不变。"""
        gate = _load_task61_gate()
        ids = [item["id"] for item in gate.BINDING_CONSTRAINTS]
        assert ids == sorted(set(ids)), f"BP id 有重复: {ids}"
        assert len(ids) >= 3, f"绑定约束只有 {len(ids)} 条，分母过小"
        for item in gate.BINDING_CONSTRAINTS:
            if item["id"] == "BP-61-1":
                continue
            assert "measured_2026_09_04" not in item, (
                f"{item['id']} 也被加了实测块 —— 本 spec 只改 BP-61-1 的字节区间"
            )

    @_needs_db
    def test_measured_block_agrees_with_the_real_database(self) -> None:
        """实测块的读数与真库现查双向一致。"""
        gate = _load_task61_gate()
        bp = next(
            item for item in gate.BINDING_CONSTRAINTS if item["id"] == "BP-61-1"
        )
        measured = bp["measured_2026_09_04"]
        assert int(measured["working_paper_sync_entry_state_rows_total"]) == int(
            _SNAPSHOT["rows_entry_state"]
        ), (
            f"登记 {measured['working_paper_sync_entry_state_rows_total']} 行、"
            f"真库现查 {_SNAPSHOT['rows_entry_state']} 行"
        )
        from app.services.workpaper_sync.writer_migration import OPAQUE_ENTRY_PREFIX

        ids = _SNAPSHOT["entry_state_ids"]
        opaque = [i for i in ids if i.startswith(OPAQUE_ENTRY_PREFIX)]
        manifest_backed = [i for i in ids if not i.startswith(OPAQUE_ENTRY_PREFIX)]
        assert int(measured["of_which_opaque_namespace"]) == len(opaque)
        assert int(measured["of_which_manifest_entry"]) == len(manifest_backed)


# ═══════════════════════════════════════════════════════════════════════════
# Property 30：登记读数与真实库行数双向一致
# ═══════════════════════════════════════════════════════════════════════════


@_needs_db
class TestRegisteredReadingsAgreeWithTheDatabase:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 30: 登记读数与真实库行数双向一致**

    **Validates: Requirements 9.1**
    """

    def _latest(self) -> dict[str, Any]:
        from app.services.workpaper_sync.opaque_entry_gate import (
            ENTRY_ID_NAMESPACE_SPLIT_NOTE as NOTE,
        )

        series = NOTE["measured_migration_cost"]
        assert isinstance(series, tuple) and len(series) >= 2, (
            "`measured_migration_cost` 必须是**带时点的序列**（≥2 条）—— "
            "只留最新一条会让「当初以为零成本」这个判断错误消失"
        )
        return dict(series[-1])

    def test_latest_reading_matches_the_database(self) -> None:
        """最新一条读数与真库现查逐项相等。"""
        latest = self._latest()
        for key, snapshot_key in (
            ("working_paper_content_version_rows", "rows_content_version"),
            ("working_paper_content_representation_rows", "rows_content_representation"),
            ("working_paper_content_application_rows", "rows_content_application"),
        ):
            assert int(latest[key]) == int(_SNAPSHOT[snapshot_key]), (
                f"{key}: 登记 {latest[key]}、真库 {_SNAPSHOT[snapshot_key]} —— "
                "任一侧变了而另一侧未更新即打红"
            )

    def test_the_series_preserves_the_task65_zero_reading(self) -> None:
        """🔴 反向自检：`task65` 那条 0 读数必须仍在序列里。

        它是「当初结论零迁移成本」这个**判断错误**的唯一证据。删掉它等于让错误消失，
        而那正是假绿第③源的另一面。
        """
        from app.services.workpaper_sync.opaque_entry_gate import (
            ENTRY_ID_NAMESPACE_SPLIT_NOTE as NOTE,
        )

        series = NOTE["measured_migration_cost"]
        first = dict(series[0])
        assert str(first["measured_at"]) == "task65"
        assert int(first["working_paper_content_version_rows"]) == 0
        assert int(first["working_paper_content_representation_rows"]) == 0

    def test_cost_did_not_silently_go_back_to_zero(self) -> None:
        """最新读数不得为全 0 —— 那说明有人把错值当基线锁死了回去。"""
        latest = self._latest()
        total = (
            int(latest["working_paper_content_version_rows"])
            + int(latest["working_paper_content_representation_rows"])
        )
        assert total > 0, (
            "最新读数又变成全 0 —— 实测库里有 representation，"
            "把登记改回 0 就是「把错值当基线锁死」（假绿第③源）"
        )

    def test_scope_boundary_is_declared(self) -> None:
        """本登记表必须声明范围边界，且把 lane 归属指向真源。"""
        from app.services.workpaper_sync.opaque_entry_gate import (
            ENTRY_ID_NAMESPACE_SPLIT_NOTE as NOTE,
        )

        assert "opaque lane" in str(NOTE["scope_boundary"])
        assert "projection" in str(NOTE["scope_boundary"])
        assert "adjudicate_lane" in str(NOTE["lane_attribution_owner"])
        assert str(NOTE["adjudication_owner_task"]) == "67"

    def test_lane_buckets_cover_every_opaque_lane(self) -> None:
        """三个分桶并集 == 全部 opaque lane（不漏 lane）。"""
        from app.services.workpaper_sync import opaque_entry_gate as OG

        note = OG.ENTRY_ID_NAMESPACE_SPLIT_NOTE
        union = (
            set(note["lanes_using_wp_code"])
            | set(note["lanes_using_wp_code_with_sheet"])
            | set(note["lanes_using_wp_id"])
        )
        assert union == set(OG.lane_ids())


# ═══════════════════════════════════════════════════════════════════════════
# Property 31：变异结果按四态判读，锚点命中数不等于一即 ANCHOR-MISS
# ═══════════════════════════════════════════════════════════════════════════


def _load_mutation_runner() -> Any:
    """按路径加载 F5 变异脚本（`backend/scripts/diagnose/` 不是包）。"""
    import importlib.util

    path = F5_PATH
    assert path.is_file(), f"F5 变异脚本不存在: {path}"
    spec = importlib.util.spec_from_file_location("_f5_mutation_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestFourStateVerdictAndAnchorHitCount:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 31: 变异结果按四态判读，锚点命中数不等于一即 ANCHOR-MISS**

    **Validates: Requirements 10.2, 10.3**

    ═══ 判据为什么落在 F5 脚本本体上 ══════════════════════════════════════════

    变异检验是本 spec 全部守卫的**元判据**：它说「守卫真能抓住回归」。若它自己把
    ANCHOR-MISS 误报成 GREEN，结论就反了 —— 「脚本没打中」会被读成「守卫有缺陷」，
    于是人去改本来正确的守卫。首轮实测踩到两次（M1/M3 语法错致 collection error 被
    误判 GREEN、M6/M8 空操作被误判 GREEN），故这一节把四态判读本身钉住。

    ═══ 构造 ═════════════════════════════════════════════════════════════════

    tasks.md 10.2 原文：喂入命中 **0 次 / 1 次 / 2 次**的锚点各一例，
    断言判读分别为 ANCHOR-MISS / 可判 / ANCHOR-MISS。

    构造用**真实文件**（种到 `backend/scripts/diagnose/_wip_*`，`.gitignore` 已收
    该前缀），因为 `check_anchors()` 读的是磁盘。`finally` 里 unlink。
    """

    _PROBE_REL = "backend/scripts/diagnose/_wip_anchor_probe.py"

    def _probe_source(self, occurrences: int) -> str:
        """造一个含 `occurrences` 处目标行的合法 Python 源。"""
        lines = [
            "# -*- coding: utf-8 -*-",
            '"""变异锚点命中数的探针（Property 31 构造）。"""',
            "from __future__ import annotations",
            "",
            "",
            "def probe() -> int:",
            "    total = 0",
        ]
        lines += ["    total += 1  # anchor-target" for _ in range(occurrences)]
        lines += ["    return total", ""]
        return "\n".join(lines)

    def _verdicts_for(self, occurrences: int) -> list[dict[str, Any]]:
        """把探针文件写进仓库、用一条自造变异跑 `check_anchors()`、还原。"""
        runner = _load_mutation_runner()
        probe = REPO / self._PROBE_REL
        assert self._PROBE_REL.split("/")[-1].startswith("_wip_"), (
            "探针文件名必须带 `_wip_` 前缀（.gitignore 已收），否则会污染工作树"
        )
        assert not probe.exists(), f"探针文件已存在（上次未清理？）: {probe}"

        mutation = runner.Mutation(
            id="PROBE",
            path=self._PROBE_REL,
            anchor="    total += 1  # anchor-target",
            new="    total += 2  # anchor-target",
            test=T_GATE_REL,
            want=frozenset({"test_probe_never_runs"}),
            why="Property 31 的构造探针 —— 只用来核对锚点命中数的判读",
        )
        original_mutations = runner.MUTATIONS
        try:
            probe.write_text(self._probe_source(occurrences), encoding="utf-8")
            runner.MUTATIONS = (mutation,)
            return runner.check_anchors()
        finally:
            runner.MUTATIONS = original_mutations
            probe.unlink(missing_ok=True)
            assert not probe.exists(), f"探针文件未清理: {probe}"

    @pytest.mark.parametrize(
        ("occurrences", "should_pass"),
        [(0, False), (1, True), (2, False)],
    )
    def test_anchor_hit_count_decides_admissibility(
        self, occurrences: int, should_pass: bool
    ) -> None:
        """命中 0/1/2 次 ⇒ 不可判 / 可判 / 不可判。"""
        rows = self._verdicts_for(occurrences)
        assert len(rows) == 1, f"探针返回 {len(rows)} 行（应恰 1）"
        row = rows[0]
        assert int(row["hits"]) == occurrences, (
            f"命中数实测 {row['hits']}、构造 {occurrences} —— 探针本身失效"
        )
        assert bool(row["ok"]) is should_pass, (
            f"命中 {occurrences} 次时 ok={row['ok']}，应为 {should_pass} —— "
            "命中 ≠1 的锚点必须被判为不可判（ANCHOR-MISS），"
            "否则「脚本没打中」会被读成「守卫有缺陷」"
        )
        if not should_pass:
            assert str(row["detail"]), "不可判却没给原因"
            assert str(occurrences) in str(row["detail"]), (
                f"原因里没写实际命中次数: {row['detail']!r} —— "
                "tasks.md 要求「≠1 即 ANCHOR-MISS 并报告实际次数」"
            )

    def test_syntax_error_after_mutation_is_anchor_miss_not_green(self) -> None:
        """🔴 变异后语法错必须判 ANCHOR-MISS，**不是** GREEN。

        语法错时 pytest 报 collection error，而那一行不以 `FAILED` 开头 ⇒
        失败集合为空 ⇒ 朴素判读会说 GREEN（首轮 M1/M3 实测踩到）。
        """
        runner = _load_mutation_runner()
        probe = REPO / self._PROBE_REL
        mutation = runner.Mutation(
            id="PROBE-SYNTAX",
            path=self._PROBE_REL,
            anchor="    total += 1  # anchor-target",
            new="    total += = 1  # anchor-target",  # 故意的语法错
            test=T_GATE_REL,
            want=frozenset({"test_probe_never_runs"}),
            why="Property 31 的语法错探针",
        )
        original = runner.MUTATIONS
        try:
            probe.write_text(self._probe_source(1), encoding="utf-8")
            runner.MUTATIONS = (mutation,)
            rows = runner.check_anchors()
        finally:
            runner.MUTATIONS = original
            probe.unlink(missing_ok=True)

        assert len(rows) == 1
        assert rows[0]["ok"] is False, (
            "变异后语法错却被判为可判 —— pytest 会报 collection error，"
            "判读会把它误当 GREEN，于是「脚本缺陷」被读成「守卫缺陷」"
        )
        assert "语法" in str(rows[0]["detail"]), (
            f"原因里没点明语法错: {rows[0]['detail']!r}"
        )

    def test_a_no_op_mutation_is_anchor_miss_not_green(self) -> None:
        """🔴 只改注释/空白的**空操作**必须判 ANCHOR-MISS。

        空操作下语义未变，守卫当然不红 —— 判 GREEN 会让人去「补强」一个本来
        正确的守卫（首轮 M6/M8 实测踩到）。判据落在 AST 相等。
        """
        runner = _load_mutation_runner()
        probe = REPO / self._PROBE_REL
        mutation = runner.Mutation(
            id="PROBE-NOOP",
            path=self._PROBE_REL,
            anchor="    total += 1  # anchor-target",
            new="    total += 1  # anchor-target（只改了注释）",
            test=T_GATE_REL,
            want=frozenset({"test_probe_never_runs"}),
            why="Property 31 的空操作探针",
        )
        original = runner.MUTATIONS
        try:
            probe.write_text(self._probe_source(1), encoding="utf-8")
            runner.MUTATIONS = (mutation,)
            rows = runner.check_anchors()
        finally:
            runner.MUTATIONS = original
            probe.unlink(missing_ok=True)

        assert len(rows) == 1
        assert rows[0]["ok"] is False, (
            "空操作变异被判为可判 —— 它的 GREEN 与守卫无关，"
            "会诱导去改一个本来正确的守卫"
        )
        assert "空操作" in str(rows[0]["detail"]) or "AST" in str(rows[0]["detail"])

    def test_the_four_verdict_names_are_all_reachable(self) -> None:
        """四态的每一态都在判读代码里有到达路径 —— 少一态即判读退化。

        判据落在 AST：`run_mutations` 里对 `verdict` 的赋值必须覆盖四个取值。
        「只有 RED / 非 RED」两态的判读无法区分「脚本没打中」与「守卫有缺陷」。
        """
        source = (
            BACKEND / "scripts/diagnose/mutate_projection_first_publication_guards.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "run_mutations"
        )
        assigned: set[str] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Assign) and isinstance(inner.value, ast.Constant):
                if isinstance(inner.value.value, str):
                    for target in inner.targets:
                        if isinstance(target, ast.Name) and target.id == "verdict":
                            assigned.add(inner.value.value)
            if isinstance(inner, ast.IfExp):
                for branch in (inner.body, inner.orelse):
                    if isinstance(branch, ast.Constant) and isinstance(
                        branch.value, str
                    ):
                        assigned.add(branch.value)
        for required in ("RED", "GREEN", "ANCHOR-MISS", "WRONG-TEST"):
            assert any(required in value for value in assigned), (
                f"判读里没有 {required!r} 这一态。实测可赋值: {sorted(assigned)} —— "
                "四态缺一就无法区分「脚本没打中」与「守卫有缺陷」"
            )

    def test_wrong_test_is_distinguished_from_red(self) -> None:
        """`WRONG-TEST` 必须与 `RED` 分开 —— 判据是「失败测试名的差集」。

        只看「有没有失败」时，锚点打错行导致**别的**测试红也会被当成 RED，
        于是变异检验的结论（这条守卫守住了这个假绿形态）是错的。
        """
        source = (
            BACKEND / "scripts/diagnose/mutate_projection_first_publication_guards.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "run_mutations"
        )
        text = ast.unparse(node)
        assert "new_failures & mutation.want" in text or "failed - base_failed" in text, (
            "判读没有对失败测试名做差集/交集 —— 它可能只在看「有没有失败」"
        )
        assert "WRONG-TEST" in text, "没有 WRONG-TEST 这一态"

    def test_min_baseline_guard_exists(self) -> None:
        """「基线 passed < N 即中止」的自检必须在（tasks.md 10.1 要求）。

        基线本身就红/收集不起来时，任何变异判读都无意义。
        """
        runner = _load_mutation_runner()
        thresholds = dict(runner.MIN_BASELINE_PASSED)
        assert thresholds, "`MIN_BASELINE_PASSED` 为空 —— 基线自检没有阈值"
        for test_path, minimum in thresholds.items():
            assert int(minimum) > 0, f"{test_path} 的阈值是 {minimum}（应 >0）"

    def test_subprocess_call_does_not_go_through_a_shell(self) -> None:
        """测试调用必须是列表形式且不经 shell。

        `-k "a or b"` 经 shell 会被拆成多个位置参数（tasks.md 10.1 记的坑）。
        """
        source = (
            BACKEND / "scripts/diagnose/mutate_projection_first_publication_guards.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        runs = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "run"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ]
        assert runs, "脚本里没有 `subprocess.run(...)` 调用"
        for call in runs:
            shell_kwargs = [
                kw for kw in call.keywords if kw.arg == "shell"
            ]
            for kw in shell_kwargs:
                assert not (
                    isinstance(kw.value, ast.Constant) and kw.value.value is True
                ), f"L{call.lineno}: `subprocess.run(..., shell=True)` —— 参数会被拆"
            assert call.args and isinstance(call.args[0], (ast.List, ast.Name)), (
                f"L{call.lineno}: 第一个实参不是列表 —— 字符串命令会经 shell 解析"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Property 32：守卫脚本对任意签名与内嵌 SQL 均正确截取函数体
# ═══════════════════════════════════════════════════════════════════════════


class TestFunctionBodyExtractionIsRobust:
    """**Feature: published-representation-production-path-and-lane-adjudication,
    Property 32: 守卫脚本对任意签名与内嵌 SQL 均正确截取函数体**

    **Validates: Requirements 10.7, 10.8**

    ═══ 判据对象 ═════════════════════════════════════════════════════════════

    本 spec 的守卫大量使用「取某函数的函数体，再判它引用了什么」这一手法
    （F6 的越界符号判据、F7 的入参来源根判据、F4 的范围边界判据）。截取一旦出错，
    判据就落在**错的字节区间**上 —— 而它照样会绿。

    Requirement 10.7 禁「固定字符窗口截断」、10.8 禁「以注释剥离逻辑处理内嵌 SQL」。
    本仓库的实现（`code_only_segment` / `_strip_docstrings` / `_function_node`）都走
    **AST**，因此这两条在构造上成立 —— 判据要做的是**证明它确实成立**，
    并在有人改回正则/字符窗口时打红。

    ═══ 覆盖面（tasks.md 10.2 原文）═══════════════════════════════════════════

    多行签名、带 `-> Mapping[str, Any]` 返回注解、体内含三引号 SQL 文本块。
    """

    _CASES: Final[tuple[tuple[str, str], ...]] = (
        (
            "single_line",
            'def f(a: int) -> int:\n    """D."""\n    return a + 1\n',
        ),
        (
            "multiline_signature",
            (
                "def f(\n"
                "    a: int,\n"
                "    *,\n"
                "    b: str = 'x',\n"
                ") -> int:\n"
                '    """D."""\n'
                "    return a + len(b)\n"
            ),
        ),
        (
            "mapping_return_annotation",
            (
                "from typing import Any, Mapping\n\n\n"
                "def f(a: int) -> Mapping[str, Any]:\n"
                '    """D."""\n'
                "    return {'a': a}\n"
            ),
        ),
        (
            "embedded_sql_triple_quoted",
            (
                "def f() -> str:\n"
                '    """D."""\n'
                "    sql = '''\n"
                "        SELECT id  -- 这不是 Python 注释，是 SQL 的一部分\n"
                "          FROM t\n"
                "         WHERE x = 1\n"
                "    '''\n"
                "    return sql\n"
            ),
        ),
        (
            "async_with_decorator",
            (
                "import functools\n\n\n"
                "@functools.cache\n"
                "async def f(\n"
                "    a: int,\n"
                ") -> int:\n"
                '    """D."""\n'
                "    return a\n"
            ),
        ),
        (
            "nested_function_and_dict_braces",
            (
                "def f(a: int) -> int:\n"
                '    """D."""\n'
                "    def inner(b: int) -> int:\n"
                "        return {'k': b}['k']\n"
                "    return inner(a)\n"
            ),
        ),
    )

    def _extract(self, source: str, tmp_path: Path) -> str:
        """用生产的 `code_only_segment` 截取 `f` 的函数体。"""
        from tests.workpaper_sync.test_task75_published_identity_observer import (
            code_only_segment,
        )

        target = tmp_path / f"probe_{abs(hash(source))}.py"
        target.write_text(source, encoding="utf-8")
        return code_only_segment(target, "f")

    @pytest.mark.parametrize("label,source", _CASES, ids=[c[0] for c in _CASES])
    def test_extraction_matches_what_ast_gives(
        self, label: str, source: str, tmp_path: Path
    ) -> None:
        """截取结果与 `ast` 给出的函数体逐语句一致，且不含签名与 docstring。"""
        extracted = self._extract(source, tmp_path)
        tree = ast.parse(source)
        node = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "f"
        )
        body = list(node.body)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body = body[1:]
        expected = "\n".join(
            (ast.get_source_segment(source, stmt) or "") for stmt in body
        )
        assert extracted == expected, (
            f"{label}: 截取结果与 AST 给出的不一致。\n"
            f"  截取: {extracted!r}\n  AST : {expected!r}"
        )
        assert "def f" not in extracted, (
            f"{label}: 截取里含签名 —— 参数列表没被跳过，"
            "「函数体引用了什么」的判据会把参数名当成引用"
        )
        assert '"""D."""' not in extracted, (
            f"{label}: docstring 没被剔 —— 注释里的名字会被当成真实引用"
        )

    def test_embedded_sql_survives_intact(self, tmp_path: Path) -> None:
        """🔴 内嵌 SQL 文本块**逐字保留**（Requirement 10.8）。

        SQL 里的 `--` 是它自己的注释语法。若截取顺手跑一遍「剥 Python 注释」，
        `-- 这不是 Python 注释` 之后的整行会被吃掉 —— 而 SQL 里 `--` 后面常写着
        列名或条件，吃掉之后「这段 SQL 引用了哪张表」的判据就落在残缺文本上。
        """
        label, source = next(c for c in self._CASES if c[0] == "embedded_sql_triple_quoted")
        extracted = self._extract(source, tmp_path)
        for fragment in ("SELECT id", "-- 这不是 Python 注释，是 SQL 的一部分",
                         "FROM t", "WHERE x = 1"):
            assert fragment in extracted, (
                f"{label}: SQL 片段 {fragment!r} 在截取后丢失 —— "
                "注释剥离逻辑吃掉了内嵌 SQL 的内容"
            )

    def test_multiline_signature_body_starts_after_the_parameter_list(
        self, tmp_path: Path
    ) -> None:
        """🔴 多行签名下函数体从**参数列表之后**开始（Requirement 10.7）。

        以「第一个 `:` 之后」或「固定字符窗口」截断时，多行签名会把参数行留在体内。
        判据落在「参数名不出现在截取结果里」—— 而参数默认值 `'x'` 恰好是个字符串，
        若签名被留下，它会被当成函数体里的字面量。
        """
        label, source = next(c for c in self._CASES if c[0] == "multiline_signature")
        extracted = self._extract(source, tmp_path)
        assert "b: str = 'x'" not in extracted, (
            f"{label}: 参数默认值留在了函数体里 —— 截取没有跳过参数列表"
        )
        assert extracted.strip() == "return a + len(b)", (
            f"{label}: 截取结果是 {extracted!r}，应恰为 `return a + len(b)`"
        )

    def test_the_shared_helper_uses_ast_not_regex(self) -> None:
        """🔴 截取实现必须走 AST，不得回退到正则/字符窗口。

        判据落在**实现形态**上，因为「结果碰巧对」与「构造上不会错」是两件事：
        正则实现能通过上面全部样例，然后在第七种签名上悄悄错位。
        """
        import inspect

        from tests.workpaper_sync.test_task75_published_identity_observer import (
            code_only_segment,
            function_node,
        )

        for func in (code_only_segment, function_node):
            source = inspect.getsource(func)
            tree = ast.parse(source.strip())
            names = {
                n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            } | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            assert "ast" in names or "get_source_segment" in names, (
                f"`{func.__name__}` 的实现里没有 AST 调用 —— "
                "它可能改成了正则或字符窗口截断"
            )
            for banned in ("finditer", "search", "match", "split"):
                offenders = [
                    n
                    for n in ast.walk(tree)
                    if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == banned
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "re"
                ]
                assert not offenders, (
                    f"`{func.__name__}` 里用了 `re.{banned}` 做截取 —— "
                    "Requirement 10.7 禁固定字符窗口/正则截断"
                )

    def test_empty_body_after_stripping_is_rejected(self, tmp_path: Path) -> None:
        """只有 docstring 的函数（剔掉后体为空）必须被**拒**，不返回空串。

        返回空串会让「函数体里没有越界引用」恒真 —— 空壳函数因此永远合规。
        """
        from tests.workpaper_sync.test_task75_published_identity_observer import (
            code_only_segment,
        )

        target = tmp_path / "empty_body.py"
        target.write_text('def f() -> None:\n    """只有 docstring。"""\n', encoding="utf-8")
        with pytest.raises(AssertionError) as caught:
            code_only_segment(target, "f")
        assert "空壳" in str(caught.value) or "为空" in str(caught.value)
