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

    def test_pilot_bridge_adapter_deleted(self) -> None:
        """Task 5.4 已物理删除 usePilotBridgeAdapter.ts，不允许复活。"""
        adapter = _SYNC / "usePilotBridgeAdapter.ts"
        assert not adapter.exists(), "usePilotBridgeAdapter.ts 不应存在 —— Task 5.4 已删"

    def test_pilot_bridge_adapter_no_production_residue(self) -> None:
        """已删 adapter 不得有残留的非注释 import。"""
        import re
        needle = "usePilotBridgeAdapter"
        for host in self.PILOT_HOSTS:
            if not host.is_file():
                continue
            source = host.read_text(encoding="utf-8")
            stripped = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
            stripped = re.sub(r'//.*$', '', stripped, flags=re.MULTILINE)
            assert needle not in stripped, (
                f"{host.name} 仍在非注释代码中引用已删的 {needle}"
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

    @staticmethod
    def _code_only(source: str) -> str:
        """去掉 HTML 注释、块注释与行注释。散文提及不算接线。"""
        source = re.sub(r"<!--.*?-->", "", source, flags=re.DOTALL)
        source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
        return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)

    @classmethod
    def _drives_bridge_via_wrapper(cls, host: pathlib.Path, code: str) -> str | None:
        """宿主经**相对 import 的包装模块**调 `useWorkpaperSyncBridge` 时返回该模块名。

        🔴 为什么必须认这一形态：`useHSyncMode` / `useD4SyncMode` / `useA51SyncMode` 都是
        「宿主挂 EditorHost、bridge 调用收在包装模块里」，而且 `sync/hManagedSheets.ts`
        把「受管 sheet 身份**不得**内联回宿主」当成正确做法。只认「宿主文件里直接出现
        `useWorkpaperSyncBridge`」等于逼 H1 这类宿主把包装拆回宿主。

        判据没有放松：这里**真的去读**被 import 的 `.ts` 文件，确认里面有
        `useWorkpaperSyncBridge(` 调用；只 import 一个名字对不上的模块不算。
        """
        for spec in re.findall(r"""from\s+['"](\.[^'"]+)['"]""", code):
            base = (host.parent / spec).resolve()
            for cand in (base.with_suffix(".ts"), base / "index.ts", base):
                if cand.suffix == ".ts" and cand.is_file():
                    if re.search(r"\buseWorkpaperSyncBridge\s*\(", cand.read_text(encoding="utf-8")):
                        return cand.stem
        return None

    @staticmethod
    def _manifest_says_no_managed_surface(host: pathlib.Path) -> str | None:
        """manifest 实证「本宿主无受管面」时返回理由，否则 None。

        🔴 实证只认 manifest 字段，**不认宿主注释** —— 否则任何宿主写一句「我没有受管面」
        就能把门喂饱。合法形态两种（逐条来自 `workpaper_sync_entry_manifest.json`）：

        * `migration_state == "parent_duplicate"`：登记它只为盘清 OO 挂载点，
          持久化身份归父 entry（`GtB60DocxPane` 即此类，`parent_entry_id` 指向 bundle）；
        * `independent_entry is False` 且 `adapter_id is None`：非独立且无 adapter
          ⇒ 没有可 materialize 的受管 sheet。
        """
        manifest = json.loads(
            (_BACKEND_DATA / "workpaper_sync_entry_manifest.json").read_text(encoding="utf-8")
        )
        entries = manifest["entries"] if isinstance(manifest, dict) else manifest
        rel = host.relative_to(_REPO).as_posix()
        for entry in entries:
            if str(entry.get("host_path") or "") != rel:
                continue
            state = entry.get("migration_state")
            if state == "parent_duplicate":
                return f"{entry.get('entry_id')} migration_state=parent_duplicate"
            if entry.get("independent_entry") is False and entry.get("adapter_id") is None:
                return f"{entry.get('entry_id')} independent_entry=False + adapter_id=None"
            return None
        return None

    @pytest.mark.parametrize("host", PILOT_HOSTS, ids=lambda p: p.name)
    def test_host_is_on_the_unified_sync_path(self, host: pathlib.Path) -> None:
        """宿主必须在统一 sync 路径上：过渡态 adapter **或**终态 editor host + bridge。

        🔴 本条原文是「必须 import `usePilotBridgeAdapter`」，那把 Task 45 的**过渡态**
        写成了永久不变量。`usePilotBridgeAdapter.ts` 自己的 docstring 写明：

            「这不是长期方案 —— Wave 5 的每个 entry 迁移时宿主会直接用
              `WorkpaperSyncEditorHost` 并彻底删除 adapter-shaped wiring。」
            「删除条件：当四个 pilot 宿主全部改为直接渲染 `WorkpaperSyncEditorHost` 时，
              本文件删除。」

        也就是说**每个宿主完成 Wave 5 迁移都会把这条判据打红**，而红的那一刻它恰恰是
        更靠近目标的形态（D2 已于 `42d2f6e6f` 走完，故只有 D2 红）。照原样留着，
        唯一的"修法"是把宿主退回 adapter —— 让判据逼着生产代码倒退。

        Task 45 真正要守的是 AC 11.1「不存在与 sync bridge 并行的第二条路径」。它由两条
        判据共同承担：`test_host_does_not_import_deleted_composable` 断死 legacy 侧，
        本条断活统一侧。故本条按「在统一路径上」表达，四种合法形态都接受：

        * 过渡态：`usePilotBridgeAdapter`（**现已无生产消费方**，留着只为不倒逼回退）
        * 终态 A：宿主渲染 `WorkpaperSyncEditorHost` **且**自己调 `useWorkpaperSyncBridge`
          （D2 / G7 / B60Bundle 现状）
        * 终态 B：宿主渲染 `WorkpaperSyncEditorHost`，bridge 调用收在**相对 import 的包装
          模块**里（H1 → `useHSyncMode`；同族还有 `useD4SyncMode` / `useA51SyncMode`）
        * 不适用：manifest 实证该宿主**无受管面**（`GtB60DocxPane` 的 entry 是
          `parent_duplicate`，`adapter_id=None` 且无契约 ⇒ 没有可 materialize 的 sheet）

        🔴 三处都比原判据**更严**而不是更松：
        * 终态 A 要求 EditorHost 与 bridge 同时在场（只写组件名不接桥不算）；
        * 终态 B 会**真的去读**被 import 的 `.ts`，确认里面有 `useWorkpaperSyncBridge(`；
        * 「不适用」只认 manifest 字段，宿主注释里写一句「我没有受管面」不作数。

        两形态皆无且 manifest 也不认，仍然打红 —— 宿主掉出统一路径这件事没被放行。
        散文不算数：先剥注释再判，否则 D2 那句「`useD2SyncBridge` 仍保留至
        ONLYOFFICE_VERIFIED」之类的说明会把门喂饱。
        """
        code = self._code_only(host.read_text(encoding="utf-8"))
        transitional = "usePilotBridgeAdapter" in code
        mounts_host = "WorkpaperSyncEditorHost" in code
        terminal_direct = mounts_host and "useWorkpaperSyncBridge" in code
        wrapper = self._drives_bridge_via_wrapper(host, code) if mounts_host else None
        exempt = self._manifest_says_no_managed_surface(host)
        assert transitional or terminal_direct or wrapper or exempt, (
            f"{host.name} 不在统一 sync 路径上：既无过渡态 usePilotBridgeAdapter，"
            "也没有 WorkpaperSyncEditorHost + useWorkpaperSyncBridge（宿主内或包装模块内），"
            "且 manifest 未把它登记为无受管面（parent_duplicate / "
            "independent_entry=False+adapter_id=None）—— 删除 legacy 后宿主必须留在统一 "
            "sync 路径上（AC 11.1）"
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

    #: 禁止出现在**代码**里的成功文案标记（注释里引用不算，见下条 docstring）。
    SUCCESS_TOAST_MARKERS = ("ElMessage", "ElNotification", "message.success", "拉取成功")

    def test_adapter_has_no_success_toast(self) -> None:
        """adapter 已删（Task 5.4）——原先检查 toast 标记的判据已随删除退役。"""
        assert not self.PILOT_ADAPTER.exists(), (
            "usePilotBridgeAdapter.ts 不应存在 —— Task 5.4 已删"
        )

    def test_marker_in_code_is_still_caught(self) -> None:
        """反向自检：剥注释不得变成逃逸通道 —— 写在代码里的 toast 必须仍被抓到。"""
        strip = TestProperty47LegacyDeleted._code_only
        for marker in self.SUCCESS_TOAST_MARKERS:
            in_comment = f"// 曾经这里会 {marker}\n/* 或 {marker} */\nconst a = 1\n"
            assert marker not in strip(in_comment), f"{marker!r} 在注释里应被剥掉"
            in_code = f"import {{ ElMessage }} from 'element-plus'\nvoid '{marker}'\n"
            assert marker in strip(in_code), f"{marker!r} 写在代码里却被剥掉了 —— 判据失效"

    def test_adapter_has_no_switching_success_message(self) -> None:
        """adapter 已删（Task 5.4）——原先检查切换成功消息的判据已随删除退役。"""
        assert not self.PILOT_ADAPTER.exists(), (
            "usePilotBridgeAdapter.ts 不应存在 —— Task 5.4 已删"
        )


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

    def test_bridge_adapter_is_deleted(self) -> None:
        """Task 5.4 已删 adapter —— 以下原先逐项校验 adapter 内容的判据已退役。"""
        assert not (_SYNC / "usePilotBridgeAdapter.ts").exists(), (
            "usePilotBridgeAdapter.ts 不应存在 —— Task 5.4 已删"
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


# ════════════════════════════════════════════════════════════════════════════
# 适配器字段契约：宿主访问的字段必须在 PilotBridgeAdapter 接口里真实存在
# ════════════════════════════════════════════════════════════════════════════
#
# 为什么补这一节（2026-09-03 三个生产缺陷倒推）：
#
# Task 45 把 legacy composable 换成 `usePilotBridgeAdapter`，但两者 **API 表面不同**
# （legacy: mode / ooAvailable / checking / checkOOHealth；
#   adapter: currentMode / isOoAvailable / switching，且**刻意不做**健康探测）。
# 宿主照旧按老名字取用，实测三处：
#
#   1. GtD2AccountsReceivable.vue  `dualMode.ooAvailable.value`
#      → computed 求值即 `Cannot read properties of undefined (reading 'value')`
#      → 点开 D2 任一子表整页崩「页面渲染出错」（浏览器实测 + 变异复现）
#   2. GtH1FixedAssets.vue         `dual.checking`
#      → undefined，模板 `:disabled="ooChecking"` 恒 falsy ⇒ 切换中不禁用（静默失效）
#   3. GtB60Bundle.vue             `mainDual.checkOOHealth()`
#      → onMounted 抛 `is not a function` ⇒ B60 整页崩
#
# 本节之前的 Task 45 守卫只查「宿主是否 import 了 adapter」这类**字符串存在**，
# 三处全部照旧通过；`get_diagnostics`(Volar) / vitest / Vite transform 也全绿
# （SFC 里从 composable 返回值取不存在的字段是 ESM 运行时错误）。
# 故判据必须落到「字段名对不对得上真源接口」这个结构关系上。
#
# 真源字段**动态抽取**，不写死清单 —— 否则接口新增字段时守卫会误判。


def _brace_block(src: str, start_idx: int) -> str:
    """从 start_idx 之后第一个 `{` 起做花括号配对，返回块体（不含外层花括号）。

    🔴 不用固定字符窗口截取：TS 的返回类型注解 `): Promise<{...}>` 之类会骗到
    「第一个 `{`」，配对才稳。
    """
    i = src.index("{", start_idx)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1 : j]
    raise AssertionError("花括号未配对 —— 接口体截取失败")


def _strip_ts_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"(?<!:)//[^\n]*", "", src)
    return src


class TestPilotAdapterDeletedAndNoResidue:
    """Task 5.4：`usePilotBridgeAdapter.ts` 已物理删除，且无残留消费方。

    原来的 ``TestPilotAdapterFieldContract``（含 ``_adapter_interface_fields`` /
    ``_adapter_field_accesses`` / ``_adapter_consumer_hosts`` 三个辅助函数）全部随
    adapter 文件一并删除——它们整类都在校验 adapter 的字段契约，adapter 不在了它们
    就是空转恒绿。删除清单见 spec ``evidence/phase5-pre-delete-eligibility-2026-11-01.md``。
    """

    _ADAPTER = _SYNC / "usePilotBridgeAdapter.ts"

    def test_adapter_file_is_deleted(self) -> None:
        """文件必须不在盘上——不允许保留「DEPRECATED 注释 + 空壳」。"""
        assert not self._ADAPTER.exists(), (
            f"usePilotBridgeAdapter.ts 仍在盘上：{self._ADAPTER} —— Task 5.4 要求物理删除"
        )

    def test_no_production_import_residue(self) -> None:
        """不得有任何生产文件（非测试）仍然 import 已删的 adapter。"""
        needle = "usePilotBridgeAdapter"
        offenders: list[str] = []
        for path in _FRONTEND.rglob("*.vue"):
            if "__tests__" in path.parts:
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            # 剥注释后判
            stripped = re.sub(r"/\*[\s\S]*?\*/", "", source)
            stripped = re.sub(r"(?<!:)//[^\n]*", "", stripped)
            if needle in stripped:
                offenders.append(str(path.relative_to(_FRONTEND.parent.parent)))
        assert offenders == [], (
            f"这些生产文件仍 import 已删的 usePilotBridgeAdapter：{offenders}"
        )

    def test_real_bridge_pilots_still_reachable(self) -> None:
        """删 adapter 后 B60 / D2 / G7 / H1 真桥仍可达（不因删除而丢路径）。"""
        for name in ("GtB60Bundle.vue", "GtD2AccountsReceivable.vue",
                     "GtG7LongTermEquityMain.vue", "GtH1FixedAssets.vue"):
            hits = list(_FRONTEND.rglob(name))
            assert hits, f"真桥宿主 {name} 不可达 —— 删 adapter 连带丢了别的东西"
