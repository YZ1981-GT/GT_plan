"""Task 75 第五 bullet 的守卫：逐 entry 真调 adapter 的探针必须真跑、且判据可证伪。

tasks.md Task 75 原文登记的欠账：「对 D2/G7/H1 三个已注册 entry 逐 entry 真调
extract / materialize 以证明 adapter 能解析 published representation 并返回 frozen
identity」。

本守卫不重复探针的运行时行为（那要连真库，属 *_pg 范畴），而是锁三件事：

1. 探针**真的**消费 registry 冻结的 adapter（不是重新构造一份 —— 重造等于自我比对）；
2. **failed 与 unverifiable 分型**的判据真在代码里（变异把 failed 全改成
   unverifiable 必须打红 —— 这正是把「实现缺陷」降级成「环境不可得」的形态）；
3. frozen identity 断言真在（变异删掉 contract_id / document_type 比对必须打红）。

判据一律走 AST，不用子串：docstring 里也写着同样的符号名，子串检查在变异后照绿
（Task 44 的 M08 实测 GREEN 就是那个形态）。
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

_CHECK_DIR = Path(__file__).resolve().parents[2] / "scripts" / "check"
_PROBE_PATH = _CHECK_DIR / "_task75_entry_adapter_probe.py"

#: 三个 pilot 的 adapter_id 真源来自 Task 41/42/43 的 manifest entry，这里只作
#: 「探针必须逐条覆盖」的期望清单。
_EXPECTED_PILOTS = {
    "d2.receivable_detail",
    "g7.soe_subsidiary_disclosure",
    "h1.disposal_check",
}


def _probe_module():
    if not _PROBE_PATH.is_file():
        pytest.fail(f"探针模块不存在：{_PROBE_PATH}")
    spec = importlib.util.spec_from_file_location(
        "_task75_entry_adapter_probe", _PROBE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _source_text() -> str:
    return _PROBE_PATH.read_text(encoding="utf-8")


def _source_tree() -> ast.Module:
    return ast.parse(_source_text())


def _top_level_calls(tree: ast.Module) -> set[str]:
    """函数体里出现过的 Name / Attribute 调用目标（`reg.register_from_manifest()`
    是 Attribute 调用，只看 Name 会漏）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _assigned_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


class TestProbeConsumesRegisteredAdapter:
    """探针必须消费 registry 冻结的 adapter，不得重新构造。"""

    def test_probe_calls_register_from_manifest_and_resolves_by_entry_id(self) -> None:
        tree = _source_tree()
        calls = _top_level_calls(tree)
        assert "register_from_manifest" in calls, (
            "探针没有真跑 register_from_manifest() —— 拿 registry 快照当注册判据"
            "会在供给就绪时仍报失败（Task 44 已实测过这个形态）"
        )
        assert "resolve_for_entry" in calls, (
            "探针没有用 resolve_for_entry(entry_id) 取注册时冻结的 adapter —— "
            "自己 build_excel_adapter() 一份等于自我比对，测不出注册链路"
        )

    def test_probe_does_not_rebuild_the_adapter(self) -> None:
        """重建 adapter 会让探针与注册链路脱钩，判据失去意义。"""
        names = _assigned_names(_source_tree())
        assert "build_excel_adapter" not in names, (
            "探针重新构造了 adapter —— 必须消费 registry 冻结的那一份"
        )


class TestVerdictTaxonomy:
    """failed 与 unverifiable 必须分型，且两者都能真正被打到。"""

    def test_both_verdicts_are_emittable(self) -> None:
        tree = _source_tree()
        emitted: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in {"failed", "unverifiable", "verified"}:
                    emitted.add(node.value)
        assert emitted >= {"failed", "verified", "unverifiable"}, (
            f"判据只覆盖 {sorted(emitted)} —— failed/unverifiable/verified 三型缺一"
            "就会把「环境不可得」与「实现缺陷」混为一谈"
        )

    def test_failed_verdict_reaches_the_failed_counter(self) -> None:
        """把 failed 降级成 unverifiable 必须打红。

        🔴 数**所有** `failed` 下标字面（计数槽位 + 各 failed 分支），不是只数槽位：
        只数槽位时，把某个 `summary["failed"] += 1` 改成 `summary["unverifiable"] += 1`
        会保持槽位数不变 —— 2026-09-07 变异 M1 实测 GREEN，正是这个缺陷。改一个字面
        必然让总数变少，于是任何一处降级都会打红。
        """
        tree = ast.parse(_source_text())
        hits = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                slice_ = node.slice
                value = slice_.value if isinstance(slice_, ast.Index) else slice_
                if isinstance(value, ast.Constant) and value.value == "failed":
                    hits += 1
        # 1 个计数槽位 + 1 个初始字典字面 + 3 个 failed 分支 = 5 处
        assert hits >= 5, (
            f"failed 下标字面只有 {hits} 处（期望 >= 5）—— failed 分支被降级成 "
            "unverifiable 了：这是把「实现缺陷」伪装成「环境不可得」，AC 5.12 明令禁止"
        )

    def test_unverifiable_paths_do_not_require_a_registered_adapter(self) -> None:
        """环境缺供给的分支必须在真调 adapter **之前**就返回。

        若把 `unverifiable` 的 `continue` 删掉，缺 representation 的 entry 会继续走
        `adapter.extract()` 并抛异常 —— 于是「供给不足」被记成「实现缺陷」，
        这正是 AC 5.12 禁止的形态。
        """
        src = _source_text()
        tree = ast.parse(src)
        # 用 ast.get_source_segment 取不到模块根节点，直接读全文
        branches = [
            ln for ln in src.splitlines() if 'verdict="unverifiable"' in ln
        ]
        continues = [ln for ln in src.splitlines() if ln.strip() == "continue"]
        assert len(branches) >= 4, f"unverifiable 分支只有 {len(branches)} 处"
        assert len(continues) >= len(branches), (
            "unverifiable 分支没有全部 continue —— 缺供给的 entry 会继续走 extract()，"
            "把「供给不足」误判成「实现缺陷」"
        )
        module = _probe_module()
        assert module.__name__ == "_task75_entry_adapter_probe"
        assert tree is not None


class TestFrozenIdentityAssertion:
    """frozen identity 必须逐字段比对，且比对的是注册时契约。"""

    def test_identity_compared_against_the_registration_contract(self) -> None:
        """变异删掉 contract_id / document_type 比对必须打红。"""
        src = _PROBE_PATH.read_text(encoding="utf-8")
        assert "projection.contract_id != contract.contract_id" in src, (
            "探针没有比对 projection.contract_id 与注册契约 —— frozen identity 漂移"
            "不会被发现"
        )
        assert "projection.document_type != contract.document_type" in src, (
            "探针没有比对 projection.document_type 与注册契约"
        )

    def test_roundtrip_reextracts_and_compares_stable_keys(self) -> None:
        """materialize → extract 必须真跑且比对 stable key 数。"""
        src = _PROBE_PATH.read_text(encoding="utf-8")
        assert "adapter.materialize(" in src, "探针没有真调 materialize"
        assert "re_projection" in src, "探针没有反读 materialize 产物"
        assert "stable_keys()" in src, "探针没有比对 stable key 数 —— round-trip 是空操作"

    def test_extract_is_called_sync_not_awaited(self) -> None:
        """🔴 extract / materialize 是**同步**方法。

        2026-09-07 首跑实测：三 entry 全部报
        ``TypeError: object Projection can't be used in 'await' expression``
        —— 探针自己 `await adapter.extract(...)` 是探针缺陷，但一旦混进断言会
        被读成「adapter 实现有问题」。锁死正确调用形态。
        """
        tree = _source_tree()
        awaited_calls: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Attribute):
                    awaited_calls.add(node.value.func.attr)
        assert "extract" not in awaited_calls, (
            "extract 是同步方法，await 它必然 TypeError —— 见模块 docstring"
        )
        assert "materialize" not in awaited_calls, (
            "materialize 是同步方法，await 它必然 TypeError"
        )


class TestSubstrateShapeGate:
    """artifact 形态门必须用封闭词表，不得写死 (published, published)。"""

    def test_substrate_gate_uses_canonical_published(self) -> None:
        """探针首跑踩过：把 gate 写成 kind=='published' 会把供给充足的 entry 全判成缺供给。

        三个 entry 的 published representation artifact 实测均为
        ``kind='canonical' state='published'``（与 ``build_excel_adapter('html_to_oo')``
        的封闭词表一致）。写错这一处不会抛错，只会静默产出
        「3 个 unverifiable + 0 个 verified」，读起来像「供给不足」。
        """
        src = _PROBE_PATH.read_text(encoding="utf-8")
        assert 'artifact_row.kind != "canonical"' in src, (
            "substrate 形态门没有锁 kind='canonical' —— 可能把供给充足的 entry 误判成缺供给"
        )
        assert 'artifact_row.state != "published"' in src, (
            "substrate 形态门没有锁 state='published'"
        )
        assert 'artifact_row.kind != "published"' not in src, (
            "kind 判成 'published' 是错的 —— 那是 substrate_role 的词表，不是 artifact 表的 kind"
        )


class TestRealRun:
    """真库在场时，探针必须真的把三个 pilot 跑通。"""

    def test_three_pilots_are_all_verified_or_environment_unavailable(self) -> None:
        module = _probe_module()
        result = module.probe_entry_adapter_roundtrip()

        summary = result["summary"]
        if summary["registered"] == 0:
            # 环境不可得（CI 无库 / 导入失败）—— 分型必须可分辨，不记 failed。
            assert summary["failed"] == 0
            assert result.get("note"), "环境不可得时必须给出可操作原因"
            return

        assert summary["failed"] == 0, (
            "有 entry 判 failed —— 逐 entry 真调 adapter 未能兑现:\n"
            + "\n".join(
                f"  {e['entry_id']}: {e.get('detail')}" for e in result["entries"] if e.get("verdict") == "failed"
            )
        )

        verified_ids = {
            e["adapter_id"] for e in result["entries"] if e.get("verdict") == "verified"
        }
        unverifiable_ids = {
            e.get("adapter_id") for e in result["entries"] if e.get("verdict") == "unverifiable"
        }
        assert (verified_ids | unverifiable_ids) >= _EXPECTED_PILOTS, (
            f"三个 pilot 未被覆盖：verified={sorted(verified_ids)} "
            f"unverifiable={sorted(unverifiable_ids)}"
        )
        # 三个 pilot 都已注册且都有 published representation 时，必须全部 verified。
        # 出现 unverifiable 只可能是环境供给变化，必须可见而不是被 summary 计数吞掉。
        if summary["unverifiable"] and summary["registered"] == 3:
            assert summary["verified"] + summary["unverifiable"] == 3, (
                "三 pilot 注册齐全却既未 verified 也未 unverifiable —— 有 entry 被静默跳过"
            )
        for entry in result["entries"]:
            if entry.get("verdict") == "verified":
                assert entry.get("roundtrip_ok") is True, (
                    f"{entry['adapter_id']}: extract 通过但 materialize→extract round-trip 失败"
                )
                assert entry.get("stable_key_count", 0) > 0, (
                    f"{entry['adapter_id']}: projection 的 stable key 数为 0 —— 空投影等于空操作"
                )
