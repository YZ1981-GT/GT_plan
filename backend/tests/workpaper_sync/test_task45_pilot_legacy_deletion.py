"""
Task 45: 删除四个 pilot 宿主 legacy，执行 post-delete 全场景重验并冻结迁移范式

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 45
Requirements: 11.1, 11.5, 11.8, 11.10, 11.12, 12.10, 12.13, 12.14, 14.16
Properties: P47, P48, P51, P69, P71

本测试验证：
1. 四个 legacy composable 文件已被物理删除（source-backed deletion）
2. 宿主已迁移到 bridge adapter（不再调用 onlyoffice-config / health 端点）
3. 旧 localStorage 前缀不再被新代码写入（统一键由 bridge 管理）
4. deletion plan 与实际删除一致
5. 源码变化使 Task 44 evidence 按 source_commit_changed 路径 stale
6. 迁移范式可冻结（四个 pilot 全部通过 post-delete 验证）
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────

_REPO = pathlib.Path(__file__).resolve().parents[3]
_FRONTEND = _REPO / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
_SYNC = _FRONTEND / "sync"
_B60 = _FRONTEND / "b60"
_COMPOSABLES = _FRONTEND / "composables"
_BACKEND_DATA = _REPO / "backend" / "data"
_PILOT_SYNC = _REPO / "backend" / "app" / "services" / "workpaper_sync"


# ────────────────────────────────────────────────────────────────────────────
# Deletion plan fixture
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def deletion_plan() -> dict:
    plan_path = _BACKEND_DATA / "workpaper_sync_pilot_deletion_plan.json"
    assert plan_path.exists(), f"deletion plan 不存在: {plan_path}"
    return json.loads(plan_path.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
# Property 47: 编辑器只消费 descriptor 并暴露 durable API
# ════════════════════════════════════════════════════════════════════════════

class TestProperty47LegacyDeleted:
    """
    **Validates: Requirements 11.5**

    P47: 编辑器只消费 descriptor，不再自行请求 config。

    删除四个 legacy composable 后，pilot 宿主不再直接调用
    `/api/workpapers/{wpId}/sheets/{sn}/onlyoffice-config`。
    """

    DELETED_FILES = [
        _B60 / "composables" / "useB60DualMode.ts",
        _COMPOSABLES / "useD2EntryDualMode.ts",
        _COMPOSABLES / "useH1DualMode.ts",
        _COMPOSABLES / "useG7DualMode.ts",
    ]

    @pytest.mark.parametrize("path", DELETED_FILES, ids=lambda p: p.name)
    def test_legacy_composable_physically_deleted(self, path: pathlib.Path) -> None:
        """legacy composable 文件必须不存在（不是 DEPRECATED 注释）。"""
        assert not path.exists(), (
            f"legacy composable {path.name} 仍然存在 —— Task 45 要求物理删除，"
            "不留 DEPRECATED/fallback 注释"
        )

    def test_pilot_bridge_adapter_exists(self) -> None:
        """替代品 usePilotBridgeAdapter.ts 必须存在。"""
        adapter = _SYNC / "usePilotBridgeAdapter.ts"
        assert adapter.exists(), "usePilotBridgeAdapter.ts 不存在"

    def test_pilot_bridge_adapter_does_not_call_config_endpoint(self) -> None:
        """adapter 不得调用 legacy onlyoffice-config 端点（注释中提及不算调用）。"""
        adapter = _SYNC / "usePilotBridgeAdapter.ts"
        source = adapter.read_text(encoding="utf-8")
        # Strip single-line and block comments before checking
        import re
        stripped = re.sub(r'//.*$', '', source, flags=re.MULTILINE)
        stripped = re.sub(r'/\*.*?\*/', '', stripped, flags=re.DOTALL)
        assert "onlyoffice-config" not in stripped, (
            "usePilotBridgeAdapter 在非注释代码中调用 onlyoffice-config —— "
            "这是 legacy 路径，必须由 bridge 的 materialize 协议完成"
        )
        assert "/api/workpapers/onlyoffice/health" not in stripped, (
            "usePilotBridgeAdapter 在非注释代码中调用 OO health 端点 —— "
            "健康检查由 bridge 内部管理"
        )

    PILOT_HOSTS = [
        _FRONTEND / "GtG7LongTermEquityMain.vue",
        _FRONTEND / "GtH1FixedAssets.vue",
        _FRONTEND / "GtD2AccountsReceivable.vue",
        _B60 / "GtB60Bundle.vue",
        _B60 / "GtB60DocxPane.vue",
    ]

    @pytest.mark.parametrize("host", PILOT_HOSTS, ids=lambda p: p.name)
    def test_host_does_not_import_deleted_composable(self, host: pathlib.Path) -> None:
        """宿主不得 import 已删除的 legacy composable。"""
        source = host.read_text(encoding="utf-8")
        for deleted in ("useB60DualMode", "useD2EntryDualMode", "useH1DualMode", "useG7DualMode"):
            # 允许注释中提到（如 // Task 45: legacy xxx deleted），但不允许在 import 语句中
            import_pattern = re.compile(
                rf"^\s*import\s+.*{deleted}",
                re.MULTILINE,
            )
            assert not import_pattern.search(source), (
                f"{host.name} 仍然 import {deleted} —— 必须改用 usePilotBridgeAdapter"
            )

    @pytest.mark.parametrize("host", PILOT_HOSTS, ids=lambda p: p.name)
    def test_host_imports_bridge_adapter(self, host: pathlib.Path) -> None:
        """宿主必须 import usePilotBridgeAdapter。"""
        source = host.read_text(encoding="utf-8")
        assert "usePilotBridgeAdapter" in source, (
            f"{host.name} 未 import usePilotBridgeAdapter —— "
            "删除 legacy 后宿主必须使用 bridge adapter"
        )


# ════════════════════════════════════════════════════════════════════════════
# Property 48: 同步失败不被成功文案覆盖
# ════════════════════════════════════════════════════════════════════════════

class TestProperty48NoLegacySuccessMessages:
    """
    **Validates: Requirements 11.10**

    P48: 任一真实同步失败后不得调用 success 文案。

    删除 legacy composable 后，宿主不得包含独立的 success/error toast 或 ElMessage。
    成功/失败文案由 bridge 的 feedback 管理。
    """

    PILOT_ADAPTER = _SYNC / "usePilotBridgeAdapter.ts"

    def test_adapter_has_no_success_toast(self) -> None:
        """adapter 不得包含 ElMessage / ElNotification 成功提示。"""
        source = self.PILOT_ADAPTER.read_text(encoding="utf-8")
        for pattern in ("ElMessage", "ElNotification", "message.success", "拉取成功"):
            assert pattern not in source, (
                f"usePilotBridgeAdapter 包含 {pattern!r} —— "
                "成功文案必须由 bridge feedback 管理（Property 48）"
            )

    def test_adapter_has_no_switching_success_message(self) -> None:
        """适配器不得在切换后显示独立成功消息。"""
        source = self.PILOT_ADAPTER.read_text(encoding="utf-8")
        assert "切换成功" not in source
        assert "在线编辑模式成功" not in source


# ════════════════════════════════════════════════════════════════════════════
# Property 51: manifest/evidence 收口五个零
# ════════════════════════════════════════════════════════════════════════════

class TestProperty51DeletionPlanAlignment:
    """
    **Validates: Requirements 12.13**

    P51: structural pre-reconcile 可报告 stale；真正 pre-delete eligibility 要求五类计数全为 0。

    验证 deletion plan 存在、结构正确、且四个 pilot 全部登记。
    """

    def test_deletion_plan_schema(self, deletion_plan: dict) -> None:
        """plan 必须有 schema version 和四个 pilot。"""
        assert deletion_plan["schema_version"] == "pilot-deletion-plan:v1"
        assert len(deletion_plan["pilots"]) == 4

    def test_deletion_plan_covers_all_pilots(self, deletion_plan: dict) -> None:
        """plan 必须覆盖四个 pilot class。"""
        classes = {p["pilot_class"] for p in deletion_plan["pilots"]}
        expected = {"simple_checklist", "d2_large_json", "h1_grouped_dynamic", "g7_two_level_dynamic"}
        assert classes == expected, f"deletion plan pilot classes = {classes}, expected {expected}"

    def test_deletion_plan_entry_ids(self, deletion_plan: dict) -> None:
        """plan 中的 entry_id 必须与 pilot 模块一致。"""
        entry_ids = {p["entry_id"] for p in deletion_plan["pilots"]}
        expected = {
            "xlsx/b60/gt-b60-bundle",
            "xlsx/gt-d2-accounts-receivable",
            "xlsx/gt-h1-fixed-assets",
            "xlsx/gt-g7-long-term-equity-main",
        }
        assert entry_ids == expected

    def test_each_pilot_has_action(self, deletion_plan: dict) -> None:
        """每个 pilot 必须有明确的删除动作。"""
        for pilot in deletion_plan["pilots"]:
            assert pilot.get("action"), f"pilot {pilot['pilot_class']} 缺少 action"
            assert "delete" in pilot["action"], (
                f"pilot {pilot['pilot_class']} 的 action={pilot['action']!r} 不含 delete"
            )


# ════════════════════════════════════════════════════════════════════════════
# Property 69: evidence 由逐 scenario 实体与服务端重算闭合
# ════════════════════════════════════════════════════════════════════════════

class TestProperty69PostDeleteEvidenceStale:
    """
    **Validates: Requirements 12.10**

    P69: 删除改变 source commit → Task 44 evidence 立即 stale。

    验证 evidence_freshness 模块的 StaleReason 包含 source_commit_changed，
    且 pilot harness 能感知源文件变化。
    """

    def test_stale_reason_enum_has_source_commit_changed(self) -> None:
        """StaleReason 必须包含 source_commit_changed。"""
        from app.services.workpaper_sync.evidence import StaleReason  # noqa: E402
        assert hasattr(StaleReason, "source_commit_changed"), (
            "StaleReason 缺少 source_commit_changed —— "
            "删除 legacy 文件后 evidence 必须走此路径 stale"
        )

    def test_freshness_guard_tracks_source_commit(self) -> None:
        """evidence 模块的 stale reasons 必须包含 source_commit 变化检测。"""
        # source_commit_changed 在 evidence.py 的 EvidenceRecomputer._stale_reasons 中实现，
        # evidence_freshness.py 补充 bundle/child 轴。两者合在一起形成完整的 stale policy。
        ev_path = _PILOT_SYNC / "evidence.py"
        source = ev_path.read_text(encoding="utf-8")
        assert "source_commit" in source, (
            "evidence.py 缺少 source_commit 引用 —— "
            "deletion 后 evidence 无法按 source_commit_changed 失效"
        )


# ════════════════════════════════════════════════════════════════════════════
# Property 71: evidence 随环境、runner 与 immutable definition bundle 变化失效
# ════════════════════════════════════════════════════════════════════════════

class TestProperty71PostDeleteStalePolicy:
    """
    **Validates: Requirements 14.16**

    P71: source commit / runner / OO build / bundle 变化后 evidence stale。

    删除 legacy 文件后 source commit 必然变化，四个 pilot 的 evidence 必须失效。
    验证 stale policy 的多轴机制存在。
    """

    def test_multiple_stale_axes_exist(self) -> None:
        """evidence 模块必须有多条独立 stale 轴（source_commit 在 evidence.py，bundle 在 evidence_freshness.py）。"""
        # source_commit 轴在 evidence.py
        ev_path = _PILOT_SYNC / "evidence.py"
        ev_source = ev_path.read_text(encoding="utf-8")
        assert "source_commit" in ev_source, (
            "evidence.py 缺少 source_commit 轴"
        )

        # bundle / environment 轴在 evidence_freshness.py 或 evidence.py
        ef_path = _PILOT_SYNC / "evidence_freshness.py"
        ef_source = ef_path.read_text(encoding="utf-8")
        combined = ev_source + ef_source
        for axis in ("environment", "bundle"):
            assert axis in combined, (
                f"evidence 模块缺少 {axis} 轴 —— "
                "deletion 后必须按多轴独立判定 stale"
            )

    def test_pilot_harness_module_exists(self) -> None:
        """pilot_harness.py 必须存在（Task 39 产物，Task 45 消费）。"""
        harness = _PILOT_SYNC / "pilot_harness.py"
        assert harness.exists(), "pilot_harness.py 不存在"

    def test_pilot_modules_exist_for_all_four(self) -> None:
        """四个 pilot 模块必须存在（非 legacy composable，是 backend 定义模块）。"""
        for name in (
            "pilot_simple_checklist.py",
            "pilot_d2_large_json.py",
            "pilot_h1_grouped_dynamic.py",
            "pilot_g7_two_level_dynamic.py",
        ):
            path = _PILOT_SYNC / name
            assert path.exists(), f"pilot 模块 {name} 不存在"


# ════════════════════════════════════════════════════════════════════════════
# 迁移范式冻结守卫
# ════════════════════════════════════════════════════════════════════════════

class TestMigrationParadigmFreeze:
    """
    验证删除后形成的可复用迁移范式：

    1. 每个 pilot 宿主只传 entry_id / flush / reload
    2. 宿主不直接调用 onlyoffice-config 或 health 端点
    3. localStorage 使用统一键前缀
    4. 成功/失败文案由 bridge feedback 管理
    """

    def test_bridge_adapter_uses_unified_storage_key(self) -> None:
        """adapter 必须使用统一 localStorage 前缀。"""
        source = (_SYNC / "usePilotBridgeAdapter.ts").read_text(encoding="utf-8")
        assert "workpaper-sync-mode:" in source, (
            "usePilotBridgeAdapter 未使用统一 localStorage 前缀 workpaper-sync-mode:"
        )

    def test_no_legacy_storage_prefixes_in_adapter(self) -> None:
        """adapter 不得使用旧 localStorage 前缀。"""
        source = (_SYNC / "usePilotBridgeAdapter.ts").read_text(encoding="utf-8")
        for prefix in ("b60-dual-mode:", "h1-dual-mode:", "g7-main-mode-", "wp-entry-dual-mode:"):
            assert prefix not in source, (
                f"usePilotBridgeAdapter 使用旧 localStorage 前缀 {prefix!r}"
            )

    def test_adapter_exposes_entry_id_parameter(self) -> None:
        """adapter 接口必须接受 entryId 参数（source-backed manifest 的稳定入口）。"""
        source = (_SYNC / "usePilotBridgeAdapter.ts").read_text(encoding="utf-8")
        assert "entryId" in source, (
            "usePilotBridgeAdapter 缺少 entryId 参数 —— 宿主必须传 manifest 稳定入口"
        )

    def test_adapter_is_documented_as_transitional(self) -> None:
        """adapter 必须注明是过渡层，Wave 5 后删除。"""
        source = (_SYNC / "usePilotBridgeAdapter.ts").read_text(encoding="utf-8")
        assert "过渡" in source or "transitional" in source.lower() or "Task 45" in source, (
            "usePilotBridgeAdapter 未注明过渡性质"
        )

    def test_deletion_plan_has_post_delete_actions(self, deletion_plan: dict) -> None:
        """deletion plan 必须有 post_delete_actions 部分。"""
        assert "post_delete_actions" in deletion_plan
        actions = deletion_plan["post_delete_actions"]
        assert actions.get("regenerate_manifest") is True
        assert actions.get("new_test_runs_required") is True
        assert "source_commit" in actions.get("evidence_stale_reason", "")

    def test_deletion_plan_properties_match_task(self, deletion_plan: dict) -> None:
        """deletion plan 的 properties 必须与 Task 45 的要求一致。"""
        expected = {47, 48, 51, 69, 71}
        actual = set(deletion_plan.get("properties_verified", []))
        assert actual == expected, f"properties_verified = {actual}, expected {expected}"
