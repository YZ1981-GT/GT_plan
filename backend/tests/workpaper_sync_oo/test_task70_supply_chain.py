# -*- coding: utf-8 -*-
"""任务 70 门 —— 首版供给链（S1~S9）真跑判据。

拆分自 `backend/tests/workpaper_sync_oo/test_task70_oo_scenario_gate.py`：宿主在
2026-11-05 补完 8 条「冻结阻塞态 → 现算 + 不变式」的重述后 1795 行 > pre-commit 行数门
whitelist 基线 1694 + 5%（1778）。照 `test_task70_census_lock.py` 的既有范式搬移 ——
判据本体原样搬，宿主的 fixtures 按路径加载复用，不抄第二份（抄第二份会让「宿主与本文件
对同一个门的认知」分叉）。
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any, Mapping  # noqa: F401  搬移来的签名用得到

import pytest  # noqa: F401  搬移来的用例可能用到

_HOST_PATH = Path(__file__).with_name("test_task70_oo_scenario_gate.py")
_spec = importlib.util.spec_from_file_location("_task70_supply_host", _HOST_PATH)
assert _spec is not None and _spec.loader is not None
_host = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _host
_spec.loader.exec_module(_host)

gate = _host.gate  # noqa: F811  fixture 需在本模块命名空间
report = _host.report  # noqa: F811  同上
live_db = _host.live_db  # noqa: F811  同上
prod = _host.prod  # noqa: F811  同上

# 搬移来的 AST 判据要用宿主的这两个接线（同样不抄第二份）
_load_gate = _host._load_gate
GATE_PATH = _host.GATE_PATH


class TestSupplyChainWalk:
    def test_every_step_was_really_executed(self, report: Mapping[str, Any]) -> None:
        """每一步都必须是**真实调用**，不是「读文档说它会失败」。"""
        walk = report["supply_chain_walk"]
        assert walk["step_count"] == walk["steps_really_executed"]
        assert walk["step_count"] >= 8
        for step in walk["steps"]:
            assert step["really_executed"] is True, f"{step['step']} 没有真跑"

    def test_first_hard_stop_is_the_capability_adjudication(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """S4（capability 裁决）必须是第一处硬阻塞（真跑 + 报告双侧）。

        🔴 顺序判据：把 S6（供给）排到 S4 之前会让「供给不足」先命中，于是「补上供给也不会
        自动放行」这条反事实臂永久不可达。
        """
        for walk in (live_db["supply_chain_walk"], report["supply_chain_walk"]):
            assert walk["first_hard_stop_step"] == "S4"
            assert "S4" in walk["blocked_step_ids"]
            # 🔴 原来还要求 "S6" 也在阻塞清单里 —— 那是环境产物（无 storage 副本 ⇒
            #    registered=0 ⇒ S6 必阻塞）。本条要证的是顺序不可交换（S4 先命中）。
            s6 = next(step for step in walk["steps"] if step["step"] == "S6")
            if "S6" in walk["blocked_step_ids"]:
                assert s6["blocked_by"], "S6 阻塞却没有具名原因"
            assert walk["blocked_step_ids"].index("S4") == 0, (
                f"S4 不是第一处硬阻塞（{walk['blocked_step_ids']}）⇒ 反事实臂不可达"
            )

    def test_capability_adjudication_really_raised_with_error_code(
        self, report: Mapping[str, Any]
    ) -> None:
        s4 = next(
            step for step in report["supply_chain_walk"]["steps"] if step["step"] == "S4"
        )
        assert s4["detail"]["error_type"] == "PilotSelectionError"
        assert s4["detail"]["error_code"] == "sync_pilot_selection_invalid"
        # 🔴 原来冻结了文案里的 "single_onlyoffice"（当时 manifest 的裁决值，现已 pending）。
        #    要证的是「这一层真的抛了可归因的码」，故改成「文案须点名当下的 capability 态」。
        message = s4["detail"]["message"]
        assert "capability=" in message, f"文案未点名 capability 态：{message[:160]}"
        tokens = ("pending", "single_onlyoffice", "single_html", "unreachable")
        assert any(t in message for t in tokens), f"capability 态不在词表内：{message[:160]}"

    def test_register_from_manifest_accounting_identity_holds(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """planned = registered + reasons + **failures** 必须逐条成立（Property 62）。

        两侧都查：报告只读产物对实现改动不敏感（教训 17），把 `accounting_identity_holds`
        写死成 True 时磁盘报告不会变。

        🔴 2026-11-05：原判据漏了 `failures` 这一项。registry 的三个集合各有独立来源
        （`registered_entry_ids` 实录 / `reasons` 供给不足 / `failures` typed 故障），
        等式是**三边之和**；只加前两项时，任何一条 entry 走到 typed failure（契约漂移 /
        观测器拒绝）就让等式恒假。实测 `assert 197 == (138 + 0)` —— 库里 59 条
        `artifact_publish_failed` 全落在 failures 里，原等式因此永远对不上，而它当时在
        `accounting_identity_holds` 恒 False 的报告上「红得理所当然」，没人追到这一层。
        """
        for source in (live_db["supply_chain_walk"], report["supply_chain_walk"]):
            s6 = next(step for step in source["steps"] if step["step"] == "S6")
            detail = s6["detail"]
            assert detail["accounting_identity_holds"] is True
            # 🔴 独立重算等式本身：只信 `accounting_identity_holds` 会让它被写死后无人察觉。
            assert detail["planned"] == (
                detail["unregistered_count"]
                + detail["failure_count"]
                + len(detail["registered_entry_ids"])
            )
            assert detail["planned"] > 0
            # 等式的三项都必须真被记下来（少记一项即回到「两边之和」那种恒假形态）
            assert detail["accounting_identity_formula"] == (
                "registered + reasons + failures == planned"
            )

        # 🔴 结构判据：该字段必须是**算出来**的比较表达式，不能是字面量。
        #    等式今天恰好成立 ⇒ 把它写死成 True 是**等价变异**，值层判据抓不到
        #    （M20 首轮实测 WRONG-TEST，教训 11：修取值来源而不是删变异）。
        source_text = _load_gate().strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source_text)
        walk = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "walk_supply_chain"
        )
        values = [
            value
            for node in ast.walk(walk)
            if isinstance(node, ast.Dict)
            for key, value in zip(node.keys, node.values)
            if isinstance(key, ast.Constant) and key.value == "accounting_identity_holds"
        ]
        assert values, "gate 里找不到 `accounting_identity_holds` 的赋值 —— 判据前提已漂移"
        for value in values:
            assert isinstance(value, ast.Compare), (
                "`accounting_identity_holds` 不是比较表达式而是"
                f" {type(value).__name__} —— 它被写死了，等式不再被真的计算"
            )

    def test_every_unregistered_entry_has_a_named_reason_or_typed_failure(
        self, report: Mapping[str, Any]
    ) -> None:
        """🔴 原判据冻结 `registered_entry_ids == []`，那是环境产物（storage 不入库 ⇒
        provider 整批 artifact_publish_failed）。补上副本后现算 32 条真注册成功。
        与环境无关的不变式是：没有 entry 被静默跳过（三集合之和 == planned）。
        """
        s6 = next(
            step for step in report["supply_chain_walk"]["steps"] if step["step"] == "S6"
        )
        detail = s6["detail"]
        assert detail["planned"] == (
            len(detail["registered_entry_ids"])
            + detail["unregistered_count"]
            + detail["failure_count"]
        )
        assert detail["pilot_reason"], "pilot entry 未注册却没有具名原因"
        # 直方图加总必须等于各自计数（否则「具名」只是空壳）
        assert sum(detail["reason_kind_histogram"].values()) == detail["unregistered_count"]
        assert sum(detail["failure_code_histogram"].values()) == detail["failure_count"]

    def test_plan_really_resolved_every_production_ref(
        self, report: Mapping[str, Any]
    ) -> None:
        """S7 是本门唯一真跑通的生产路径：`plan()` 内逐个 import + getattr 全过。"""
        s7 = next(
            step for step in report["supply_chain_walk"]["steps"] if step["step"] == "S7"
        )
        plans = s7["detail"]["plans_by_authority_model"]
        assert s7["detail"]["approved_bundle_count"] >= 3
        assert len(plans) >= 3
        # 🔴 原判据要求每条 plan 都不抛，那是「manifest 里没有 pending entry」的年代。
        #    现在分两类：抛错的必须落在合法拒绝的封闭集合里，其余逐项齐备且至少 3 条。
        resolved = {
            label: row for label, row in plans.items() if "error_type" not in row
        }
        for label, row in plans.items():
            if "error_type" in row:
                # 合法拒绝只有两类：pending 解析不出能力、harness 按准入拒掉。
                assert row["error_type"] in ("EntryProfileError", "HarnessRejected"), (
                    f"{label} 的 plan 抛了 {row['error_type']}（不在合法拒绝集合里）"
                )
                assert str(row.get("message", "")).strip(), f"{label} 的拒绝无原因文案"
                continue
            assert row["production_refs_all_resolvable"] is True
            assert row["scenario_count"] > 0
            assert len(row["bundle_sha256"]) == 64
            assert len(row["typed_child_digest"]) == 64
            assert len(row["required_scenario_set_digest"]) == 64
        assert len(resolved) >= 3, f"只有 {len(resolved)} 条 plan 真解析成功 ⇒ 分母塌了"

    def test_authority_substitution_only_swaps_the_field_level_pair(
        self, prod: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """custom/opaque 只替换字段级两条；close/recovery/authorization 一条不动。"""
        evidence = prod["evidence"]

        sensitivity = report["entry_derivation"]["authority_model_sensitivity"]
        added = set(sensitivity["scenarios_added_under_substituting_models"])
        removed = set(sensitivity["scenarios_removed_under_substituting_models"])
        assert removed == set(evidence.FIELD_LEVEL_SCENARIOS)
        assert added == {s.scenario_id for s in evidence.AUTHORITY_SUBSTITUTE_SCENARIOS}
        assert not (removed & evidence.NON_REPLACEABLE_SCENARIOS)

    def test_both_first_version_sources_are_blocked_and_no_third_path_is_built(
        self, live_db: Mapping[str, Any], report: Mapping[str, Any]
    ) -> None:
        """两侧都查：报告里的 S8 是产物，真跑的 S8 才对步骤 id 的改名敏感（教训 17）。"""
        for source in (live_db["supply_chain_walk"], report["supply_chain_walk"]):
            candidates = [step for step in source["steps"] if step["step"] == "S8"]
            assert len(candidates) == 1, (
                f"S8 步骤命中 {len(candidates)} 条 —— 步骤 id 被改名，"
                "「两条首版来源都被挡住」这条实证找不到了"
            )
            detail = candidates[0]["detail"]
            # 🔴 原来三项冻结成 0（当时的库状态；现算 83 / 435）。要证的是
            #    「不新建第三条首版路径」这个结构结论 + 计数是现算的。
            for key in ("entry_state_rows", "representation_upgrade_candidate_rows",
                        "content_version_rows"):
                assert isinstance(detail[key], int) and detail[key] >= 0, (
                    f"{key} 不是现算整数：{detail[key]!r}"
                )
            assert "不新建第三条" in detail["conclusion"].replace("**", "")

    def test_gate_does_not_write_a_representation_itself(self, gate: Any) -> None:
        """门里不得出现 representation / content version 的写入面（自建第三条路径）。

        判据走 AST 找 `session.add(...)` 与 `INSERT INTO` 字面量，先剥注释。
        """
        source = gate.strip_comments(GATE_PATH.read_text(encoding="utf-8"))
        tree = ast.parse(source)
        def _receiver_name(func: ast.Attribute) -> str:
            value = func.value
            if isinstance(value, ast.Name):
                return value.id
            if isinstance(value, ast.Attribute):
                return value.attr
            return ""

        # 🔴 必须看**接收者**：只按方法名 `add` 判会把 `set.add()` 全算成 ORM 写入
        #    （本门首轮实测 3 处假红，全是 `strip_comments` 里的 `drop.add(...)`）。
        adds = [
            f"{_receiver_name(node.func)}.{node.func.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add", "add_all", "merge", "bulk_save_objects", "flush"}
            and "session" in _receiver_name(node.func).lower()
        ]
        assert not adds, f"门里出现了 ORM 写入面: {adds}"

        # 反向自检：判据必须能抓到真的 session 写入面（否则收窄成了重言式）。
        planted = ast.parse("session.add(row)\nself._session.flush()\n")
        planted_hits = [
            node
            for node in ast.walk(planted)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"add", "add_all", "merge", "bulk_save_objects", "flush"}
            and "session" in _receiver_name(node.func).lower()
        ]
        assert len(planted_hits) == 2, "收窄后的判据抓不到真的 session 写入面"
        inserts = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.search(r"\b(insert\s+into|update\s+|delete\s+from)\b", node.value, re.I)
        ]
        assert not inserts, f"门里出现了写库 SQL: {inserts[:3]}"
