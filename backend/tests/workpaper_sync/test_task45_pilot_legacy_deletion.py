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


def _adapter_interface_fields() -> set[str]:
    """从 `export interface PilotBridgeAdapter { ... }` 抽出成员名（真源）。"""
    src = (_SYNC / "usePilotBridgeAdapter.ts").read_text(encoding="utf-8")
    m = re.search(r"export\s+interface\s+PilotBridgeAdapter\s*\{", src)
    assert m, "找不到 PilotBridgeAdapter 接口声明 —— adapter 契约无从校验"
    body = _strip_ts_comments(_brace_block(src, m.start()))
    fields = set(re.findall(r"^\s*([A-Za-z_$][\w$]*)\s*[?:]", body, flags=re.M))
    assert fields, "PilotBridgeAdapter 接口字段抽取为空 —— 抽取器失效"
    return fields


def _adapter_field_accesses(source: str) -> set[str]:
    """抽出某宿主源码里对 adapter 返回值取用的字段名（实例访问 + 解构）。"""
    src = _strip_ts_comments(source)
    used: set[str] = set()

    # 形式 A：const <名> = usePilotBridgeAdapter({...})  →  扫 <名>.<字段>
    for name in re.findall(r"const\s+([A-Za-z_$][\w$]*)\s*=\s*usePilotBridgeAdapter\s*\(", src):
        used |= set(re.findall(rf"\b{re.escape(name)}\.([A-Za-z_$][\w$]*)", src))

    # 形式 B：const { a, b } = usePilotBridgeAdapter({...})
    for m in re.finditer(r"const\s*\{", src):
        try:
            body = _brace_block(src, m.start())
        except (AssertionError, ValueError):
            continue
        tail = src[src.index("}", m.start()) :]
        if not re.match(r"\}\s*=\s*usePilotBridgeAdapter\s*\(", tail):
            continue
        for part in body.split(","):
            key = part.split(":")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", key):
                used.add(key)
    return used


def _adapter_consumer_hosts() -> list[pathlib.Path]:
    """扫出所有实例化 adapter 的宿主（不写死清单，Wave 5 新增宿主自动纳入）。"""
    hosts: list[pathlib.Path] = []
    for path in _FRONTEND.rglob("*.vue"):
        if "__tests__" in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "usePilotBridgeAdapter(" in _strip_ts_comments(source):
            hosts.append(path)
    return sorted(hosts)


class TestPilotAdapterFieldContract:
    """
    **Validates: Requirements 11.1, 11.5**

    宿主从 `usePilotBridgeAdapter` 取用的每个字段都必须在
    `PilotBridgeAdapter` 接口里真实存在。
    """

    def test_scan_surface_is_not_empty(self) -> None:
        """扫描面自检：宿主数与字段访问数都不能为 0（防判据空转恒绿）。"""
        hosts = _adapter_consumer_hosts()
        assert len(hosts) >= 4, (
            f"只扫到 {len(hosts)} 个 adapter 宿主 —— Task 45 至少迁了四类 pilot，"
            "扫描器可能失效"
        )
        total = sum(len(_adapter_field_accesses(h.read_text(encoding="utf-8"))) for h in hosts)
        assert total > 0, "宿主字段访问抽取总数为 0 —— 抽取器失效，判据恒绿"

    @pytest.mark.parametrize(
        "host", _adapter_consumer_hosts(), ids=lambda p: p.name
    )
    def test_host_only_uses_declared_adapter_fields(self, host: pathlib.Path) -> None:
        """宿主不得取用接口未声明的字段（运行时 undefined，四层验证全绿）。"""
        truth = _adapter_interface_fields()
        used = _adapter_field_accesses(host.read_text(encoding="utf-8"))
        unknown = sorted(used - truth)
        assert not unknown, (
            f"{host.name} 取用了 PilotBridgeAdapter 未声明的字段 {unknown}。\n"
            f"接口真源字段：{sorted(truth)}\n"
            "这类写法运行时得到 undefined —— 取 `.value` 直接整页崩「页面渲染出错」，"
            "当函数调用则抛 `is not a function`，而 Volar/vitest/Vite 三层全绿。\n"
            "常见错配：ooAvailable→isOoAvailable / mode→currentMode / "
            "checking→switching / checkOOHealth→已废除（健康探测归 bridge）"
        )

    def test_judgment_catches_wrong_field_names(self) -> None:
        """反向自检：故意写错的字段必须被抽出并判为未声明（判据不恒真）。"""
        truth = _adapter_interface_fields()

        bad_instance = """
        const dualMode = usePilotBridgeAdapter({ entryId: 'x', wpId: w })
        const opts = { disabled: !dualMode.ooAvailable.value }
        void dualMode.checkOOHealth()
        """
        used = _adapter_field_accesses(bad_instance)
        assert {"ooAvailable", "checkOOHealth"} <= used, "实例式字段访问抽取失效"
        assert {"ooAvailable", "checkOOHealth"} <= (used - truth), (
            "错误字段未被判为未声明 —— 判据失效"
        )

        bad_destructure = """
        const { currentMode, ooAvailable } = usePilotBridgeAdapter({ entryId: 'x', wpId: w })
        """
        used2 = _adapter_field_accesses(bad_destructure)
        assert "ooAvailable" in used2 - truth, "解构式字段访问抽取失效"

        good = """
        const dual = usePilotBridgeAdapter({ entryId: 'x', wpId: w })
        const a = dual.currentMode.value
        const b = dual.isOoAvailable.value
        const c = dual.switching.value
        """
        assert not (_adapter_field_accesses(good) - truth), (
            "正确字段被误判为未声明 —— 判据过严，会对合法宿主假红"
        )

    def test_comment_only_mention_does_not_count(self) -> None:
        """注释里提到旧字段名不算取用（否则修复时写的说明注释会把判据打红）。"""
        truth = _adapter_interface_fields()
        source = """
        const dual = usePilotBridgeAdapter({ entryId: 'x', wpId: w })
        // 🔴 真源是 isOoAvailable，写 dual.ooAvailable 会整页崩
        const b = dual.isOoAvailable.value
        """
        assert not (_adapter_field_accesses(source) - truth), (
            "注释中的旧字段名被当成真取用 —— 会让带说明注释的正确代码假红"
        )
