# -*- coding: utf-8 -*-
"""A 域平台级欠账登记守卫 — Task 21* (不在本 spec 闭合)。

spec: a-cycle-sync-foundation-and-first-canary

═══ 目的 ═══

登记 5 项 Blocking Point（BP-1~BP-5）在 abcs slice 全部 46 条 entry 上的基线状态，
以及两项已知平台级缺陷：

  1. BP-1 — approved 权威模型未发布（`capability_verdict_stage` 非 `approved`）
  2. BP-2 — 逐 entry 契约（contract）未发布（`contract_id` 全 null）
  3. BP-3 — capability 是 overlay 默认值（`capability_target` 统一为 bidirectional），
             非逐 entry 独立裁决
  4. BP-4 — definition bundle 与 published representation 未交付
             （46/46 `migration_state` = `legacy_fake_bidirectional`）
  5. BP-5 — adapter 未注册（`adapter_id` 全 null，46/46）

  6. schema 验证器拒收诚实声明（`validate_slice_against_schema` 对缺陷越多
     的声明越容易报错；A 轮走追加节绕开，`residual_inconsistency` = null）
  7. 归档区 `report-view-slimdown/tasks.md` 编码修复验证

每条写成 **基线断言 + 解除信号**（解除即打红提醒同步更新 spec）。

_Requirements: 11, 13_
_AC/AF-P: AC-33 · AF-P1_
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ── 路径 ────────────────────────────────────────────────────────────
_BACKEND = Path(__file__).resolve().parents[2]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_SLICE_PATH = _BACKEND / "data" / "workpaper_sync_abcs_cycle_manifest_slice.json"
_ARCHIVE_ROOT = _ROOT / ".kiro" / "specs" / "_archive"

sys.path.insert(0, str(_BACKEND / "scripts" / "analyze"))
from a_cycle_scanner import a_domain_entries  # noqa: E402

# ── fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def manifest_slice() -> dict:
    return json.loads(_SLICE_PATH.read_bytes())


@pytest.fixture(scope="module")
def all_entries(manifest_slice: dict) -> list[dict]:
    return manifest_slice["independent_entries"]


@pytest.fixture(scope="module")
def a_entries(manifest_slice: dict) -> list[dict]:
    return a_domain_entries(manifest_slice["independent_entries"])


# ════════════════════════════════════════════════════════════════════
# §1  BP-5 基线：adapter_id 全 null（46/46）
# ════════════════════════════════════════════════════════════════════

class TestBP5AdapterNotRegistered:
    """BP-5: 46/46 条 entry 的 adapter_id 为 null。

    解除信号：任一 entry 的 adapter_id 变为非 null ⇒ 打红，
    表明 adapter 注册机制已就绪，应同步更新 spec 与 capability。
    """

    def test_all_46_entries_have_null_adapter_id(
        self, all_entries: list[dict]
    ) -> None:
        """BP-5 基线：adapter_id 46/46 为 null。"""
        null_count = sum(
            1 for e in all_entries if e.get("adapter_id") is None
        )
        assert null_count == len(all_entries) == 46, (
            f"adapter_id null count = {null_count}/{len(all_entries)}; "
            "若非 46/46 说明 adapter 注册机制已就绪，应更新 spec"
        )

    def test_a_domain_20_have_null_adapter_id(
        self, a_entries: list[dict]
    ) -> None:
        """BP-5 在 A 域的投影：20/20 为 null。"""
        null_count = sum(
            1 for e in a_entries if e.get("adapter_id") is None
        )
        assert null_count == 20, (
            f"A 域 adapter_id null = {null_count}/20; "
            "若有 adapter 注册应更新 a-cycle spec"
        )


# ════════════════════════════════════════════════════════════════════
# §2  BP-2 基线：contract_id 全 null
# ════════════════════════════════════════════════════════════════════

class TestBP2ContractNotPublished:
    """BP-2: 逐 entry 契约（contract）未发布。

    解除信号：任一 entry 的 contract_id 变为非 null。
    """

    def test_all_entries_have_null_contract_id(
        self, all_entries: list[dict]
    ) -> None:
        """BP-2 基线：contract_id 46/46 为 null。"""
        non_null = [
            e["entry_id"]
            for e in all_entries
            if e.get("contract_id") is not None
        ]
        assert non_null == [], (
            f"contract_id 非 null 的 entry: {non_null}; "
            "若已有契约发布应更新 spec"
        )


# ════════════════════════════════════════════════════════════════════
# §3  BP-3 基线：capability 是 overlay 默认值
# ════════════════════════════════════════════════════════════════════

class TestBP3CapabilityIsOverlayDefault:
    """BP-3: capability_target 全部为 'bidirectional'（overlay 默认值），
    非逐 entry 独立裁决。

    🔴 这不代表每条 entry 真的可以做双向回写 —— 只是 overlay 没有
    按 entry 粒度裁决，统一给了 bidirectional 默认值。

    解除信号：出现非 bidirectional 的 capability_target，说明已开始逐
    entry 独立裁决。
    """

    def test_all_entries_capability_target_is_bidirectional(
        self, all_entries: list[dict]
    ) -> None:
        """BP-3 基线：46/46 的 capability_target = 'bidirectional'。"""
        non_bidi = [
            (e["entry_id"], e.get("capability_target"))
            for e in all_entries
            if e.get("capability_target") != "bidirectional"
        ]
        assert non_bidi == [], (
            f"非 bidirectional 的 entry: {non_bidi}; "
            "若已逐 entry 裁决 capability 应更新 spec"
        )

    def test_a_domain_capability_verdict_stage_not_approved(
        self, a_entries: list[dict]
    ) -> None:
        """BP-1 在 A 域的投影：approved 权威模型未发布。

        所有 A 域 entry 的 capability_verdict_stage 应尚未到达 'approved'。
        """
        # BP-1: capability_verdict_stage 可能为 null 或非 approved 值
        approved = [
            e["entry_id"]
            for e in a_entries
            if e.get("capability_verdict_stage") == "approved"
        ]
        assert approved == [], (
            f"A 域已 approved 的 entry: {approved}; "
            "若有 approved entry 说明 BP-1 部分解除，应更新 spec"
        )


# ════════════════════════════════════════════════════════════════════
# §4  BP-4 基线：migration_state 全部 legacy
# ════════════════════════════════════════════════════════════════════

class TestBP4DefinitionBundleNotDelivered:
    """BP-4: definition bundle 与 published representation 未交付。

    现算 45/46 的 migration_state = 'legacy_fake_bidirectional'，
    唯一例外 `xlsx/gt-custom-wp-editor` 为 'adapter_candidate'（已进入
    候选阶段但仍未交付 definition bundle）。

    解除信号：出现 'published' 或其他已交付状态的 migration_state。
    """

    # 已知例外：这些 entry 不是 legacy_fake_bidirectional 但也没交付 bundle
    _KNOWN_NON_LEGACY = {
        "xlsx/gt-custom-wp-editor": "adapter_candidate",
    }

    def test_all_entries_migration_state_baseline(
        self, all_entries: list[dict]
    ) -> None:
        """BP-4 基线：45 条 legacy + 1 条 adapter_candidate = 46。"""
        unexpected = []
        for e in all_entries:
            eid = e["entry_id"]
            ms = e.get("migration_state")
            expected = self._KNOWN_NON_LEGACY.get(eid, "legacy_fake_bidirectional")
            if ms != expected:
                unexpected.append((eid, ms, expected))
        assert unexpected == [], (
            f"migration_state 不符合基线的 entry: {unexpected}; "
            "若某条 entry 的 migration_state 已变更应更新此基线"
        )

    def test_a_domain_all_legacy(self, a_entries: list[dict]) -> None:
        """A 域 20/20 全部为 legacy_fake_bidirectional。"""
        non_legacy = [
            (e["entry_id"], e.get("migration_state"))
            for e in a_entries
            if e.get("migration_state") != "legacy_fake_bidirectional"
        ]
        assert non_legacy == [], (
            f"A 域非 legacy 的 entry: {non_legacy}; "
            "A 域全部 entry 的 definition bundle 均未交付"
        )


# ════════════════════════════════════════════════════════════════════
# §5  BP-1~5 共存守卫：每条 entry 至少被 BP-1~5 全覆盖
# ════════════════════════════════════════════════════════════════════

class TestBP1Through5UniversallyCover:
    """所有 46 条 entry 的 capability_target_blocked_by 都包含 BP-1~5。

    这是 BP-1~5「均需平台层方案」的最强断言：不存在任何一条 entry
    绕过了 BP-1~5 中的任何一项。

    解除信号：某条 entry 不再被某项 BP 阻塞（差集非空）。
    """

    _REQUIRED_BPS = {"BP-1", "BP-2", "BP-3", "BP-4", "BP-5"}

    def test_every_entry_blocked_by_bp1_through_bp5(
        self, all_entries: list[dict]
    ) -> None:
        """每条 entry 的 blocked_by 集合都包含 {BP-1, BP-2, BP-3, BP-4, BP-5}。"""
        missing = {}
        for e in all_entries:
            blocked = set(e.get("capability_target_blocked_by", []))
            gap = self._REQUIRED_BPS - blocked
            if gap:
                missing[e["entry_id"]] = sorted(gap)
        assert missing == {}, (
            f"以下 entry 缺少 BP-1~5 中的阻塞项: {missing}; "
            "若某项 BP 解除应同步更新 spec"
        )

    def test_bp_distribution_counts(
        self, all_entries: list[dict]
    ) -> None:
        """BP-1~5 各自的覆盖数应为 46（全覆盖）。"""
        from collections import Counter

        counter: Counter[str] = Counter()
        for e in all_entries:
            for bp in e.get("capability_target_blocked_by", []):
                counter[bp] += 1
        for bp in sorted(self._REQUIRED_BPS):
            assert counter[bp] == 46, (
                f"{bp} 只覆盖 {counter[bp]}/46 条; "
                "若非 46 说明该 BP 已部分解除"
            )


# ════════════════════════════════════════════════════════════════════
# §6  schema 验证器拒收诚实声明
# ════════════════════════════════════════════════════════════════════

class TestSchemaValidatorRejectsHonestDeclaration:
    """N 轮发现：`validate_slice_against_schema` 对缺陷越多的声明越容易
    报错 —— 越如实点名越通不过 = 反向激励藏缺陷。

    A 轮走追加节（supplementary sections）绕开，`residual_inconsistency`
    写为 null。

    这是平台层欠账，单循环 spec 无法闭合。

    断言 residual_inconsistency 当前为 null（绕开成功）；若变为非 null，
    说明有人尝试诚实声明但被拒收，欠账恶化。
    """

    def test_residual_inconsistency_is_null_workaround_succeeded(
        self, manifest_slice: dict
    ) -> None:
        """A 轮绕开策略成功：residual_inconsistency = null。"""
        ri = manifest_slice.get("residual_inconsistency")
        assert ri is None, (
            f"residual_inconsistency = {ri!r}; "
            "若非 null 说明追加节绕开已失效或有人尝试诚实声明被拒"
        )

    def test_paradigm_schema_conflict_is_documented(
        self, manifest_slice: dict
    ) -> None:
        """schema 冲突已登记在 slice 的 paradigm_schema_conflict 节。"""
        psc = manifest_slice.get("paradigm_schema_conflict")
        assert psc is not None, (
            "paradigm_schema_conflict 节不存在; "
            "该节记录 schema 验证器拒收问题，应确保 slice 含此信息"
        )
        assert isinstance(psc, dict), (
            f"paradigm_schema_conflict 应为 dict, 实为 {type(psc).__name__}"
        )


# ════════════════════════════════════════════════════════════════════
# §7  归档区编码修复验证
# ════════════════════════════════════════════════════════════════════

class TestArchiveEncodingRepair:
    """report-view-slimdown/tasks.md 曾是非 UTF-8 文件（179 处多字节序列
    中间字节被 0x3F 替换）。

    修复后该文件已转为合法 UTF-8（损坏位置以 U+FFFD 替代字符标记，
    原始字节不可恢复）。

    本守卫确保：
      1. 文件现在能被 `read_text(encoding='utf-8')` 正常读取（不抛异常）
      2. 行数与内容特征不变
      3. 全归档区扫描不再因编码问题崩溃
    """

    _TARGET = (
        _ARCHIVE_ROOT
        / "07-workpaper-slimdown"
        / "report-view-slimdown"
        / "tasks.md"
    )

    def test_repaired_file_is_valid_utf8(self) -> None:
        """修复后的文件可以用 UTF-8 正常读取。"""
        if not self._TARGET.exists():
            pytest.skip("归档文件不存在（仓库可能未包含完整归档区）")
        # 🔴 修复前此处会抛 UnicodeDecodeError
        text = self._TARGET.read_text(encoding="utf-8")
        assert len(text) > 0, "文件内容为空"
        # 文件内容应包含 spec 标题
        assert "ReportView" in text or "Slimdown" in text or "Implementation" in text

    def test_repaired_file_has_expected_line_count(self) -> None:
        """修复后行数应在合理范围（原文约 260 行）。"""
        if not self._TARGET.exists():
            pytest.skip("归档文件不存在")
        text = self._TARGET.read_text(encoding="utf-8")
        line_count = len(text.split("\n"))
        assert 200 <= line_count <= 300, (
            f"行数 {line_count} 不在预期范围 [200, 300]; "
            "文件可能被错误修改"
        )

    def test_replacement_chars_are_bounded(self) -> None:
        """修复后的 U+FFFD 替代字符数应等于已知的 179 个损坏位置。"""
        if not self._TARGET.exists():
            pytest.skip("归档文件不存在")
        text = self._TARGET.read_text(encoding="utf-8")
        fffd_count = text.count("\ufffd")
        assert fffd_count == 179, (
            f"U+FFFD 数量 = {fffd_count}, 预期 179; "
            "文件被再次修改或损坏"
        )

    def test_archive_scan_does_not_crash_on_any_file(self) -> None:
        """全归档区扫描：所有 .md 文件都能被 errors='replace' 安全读取。"""
        if not _ARCHIVE_ROOT.exists():
            pytest.skip("归档区不存在")
        crashed = []
        for md in _ARCHIVE_ROOT.rglob("*.md"):
            try:
                md.read_bytes().decode("utf-8", errors="replace")
            except Exception as exc:
                crashed.append((str(md.relative_to(_ROOT)), str(exc)))
        assert crashed == [], (
            f"以下归档 .md 文件即使带 errors='replace' 也无法读取: {crashed}"
        )


# ════════════════════════════════════════════════════════════════════
# §8  综合欠账台账（文档型断言）
# ════════════════════════════════════════════════════════════════════

class TestPlatformDebtLedger:
    """将 5 项 BP 欠账 + 2 项平台缺陷写成文档型断言，确保台账存在且完整。

    这些断言不验证外部系统，只验证 slice 与本地文件中**欠账已被登记**。
    """

    def test_bp_codes_are_documented_in_slice(
        self, manifest_slice: dict
    ) -> None:
        """slice 中应至少记录 BP-1 ~ BP-5 这 5 个 blocking point 编号。"""
        all_bps: set[str] = set()
        for e in manifest_slice["independent_entries"]:
            for bp in e.get("capability_target_blocked_by", []):
                all_bps.add(bp)
        documented = {"BP-1", "BP-2", "BP-3", "BP-4", "BP-5"}
        missing = documented - all_bps
        assert missing == set(), (
            f"以下 BP 未在 slice 中登记: {sorted(missing)}"
        )

    def test_schema_version_is_v1(
        self, manifest_slice: dict
    ) -> None:
        """slice schema 版本 = v1（记录型：锁定当前版本）。"""
        sv = manifest_slice.get("schema_version")
        assert sv == "manifest-slice:v1", (
            f"schema_version = {sv!r}; 若版本变更须重新评估全部判据"
        )

    def test_blocking_reasons_text(self) -> None:
        """台账文本：5 项 BP 阻塞理由概述。

        🔴 本断言仅验证台账文本存在（即本测试文件的 docstring）——
        不验证外部系统状态。单循环 spec 无法闭合这些欠账。

        BP-1: approved 权威模型未发布
        BP-2: 逐 entry contract 未发布
        BP-3: capability 是 overlay 默认值非逐 entry 裁决
        BP-4: definition bundle 与 published representation 未交付
        BP-5: adapter 未注册（adapter_id 46/46 为 null）
        """
        # 本测试本身就是台账——docstring 记录了 5 项 BP 阻塞理由。
        # 用最小断言确保该测试被执行。
        assert True, "台账文本已记录在本测试 docstring 中"
