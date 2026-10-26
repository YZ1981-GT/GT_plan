"""EQCR 消费方清单与正向授权不变（partner-manager-edit-permission 任务 14.6）。
# Feature: partner-manager-edit-permission, Property: EQCR 消费方清单

**产出**：
1. 登记表（``EQCR_CONSUMER_REGISTRY``）：键 = ``文件::函数``，值 = 用途 / 是否识别 ``独立复核合伙人`` / 处置 / 理由。
2. AST 扫描（三种检索口径）：委派角色值与字面量 ``eqcr`` 作相等/不等/成员判断；
   把 ``eqcr`` 列入委派角色名单；以委派角色为键取 EQCR 专属权限。
3. 扫描结果与登记表键集合相等：新增位置未登记、登记位置已消失都打红。

**需求 7.7**：全局 eqcr、在该项目没有 ``eqcr`` 现行委派的用户，
EQCR 正向授权端点仍拒绝（``_is_user_eqcr_on`` 只查委派不看全局角色）。

**Validates: Requirements 7.7, 7.8**
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any, NamedTuple

import pytest

# ─── 常量 ───────────────────────────────────────────────────────────────────
_APP_DIR = Path(__file__).resolve().parents[1] / "app"
_EQCR_LITERALS: frozenset[str] = frozenset({"eqcr", "独立复核合伙人"})

# 排除的文件/模块：这些位置的 'eqcr' 比的是全局角色、项目角色或角色上下文返回值，
# 不是委派角色（design §4.14 明确排除）。
_GLOBAL_ROLE_FILES: frozenset[str] = frozenset({
    # 全局角色比较
    "app/routers/audit_logs.py",            # _ALLOWED_PROJECT_ROLES 比项目角色
    "app/services/ai_chat/address_mention.py",  # 全局角色
    "app/services/ai_chat/dsh_engine.py",       # 全局角色
    "app/services/ai_chat/mcp_token.py",        # 全局角色
    "app/services/evidence_governance/role_capability_contract.py",  # 全局角色能力
    "app/services/custom_template_ingestion/authorization.py",  # 全局角色
    "app/services/acnr/resolver.py",         # 全局角色
    "app/permissions/permission_matrix.py",  # 操作矩阵（全局/项目角色组合）
    "app/services/permission_matrix_service.py",  # 同上
    "app/routers/wp_capability_snapshot.py",  # 角色上下文返回值
    "app/routers/review_dialog.py",          # 角色上下文返回值
    "app/services/role_context_service.py",  # 角色上下文本身
    "app/services/role_workbench_facade.py",  # 角色上下文
    "app/router_registry/collaboration.py",  # 路由注册条件
})


class ConsumerEntry(NamedTuple):
    """登记表条目。"""
    purpose: str
    recognizes_chinese_alias: bool
    treatment: str
    rationale: str


# ═══════════════════════════════════════════════════════════════════════════
# 登记表（design §4.14，实施时按扫描结果现算并逐个判读）
# 键 = "文件::函数"，委派角色比较位置
# ═══════════════════════════════════════════════════════════════════════════
EQCR_CONSUMER_REGISTRY: dict[str, ConsumerEntry] = {
    # ── 已改用 is_project_eqcr 的位置（不再含 'eqcr' 字面量，从登记表移除） ──
    # deliverable._guard_action 已改用 is_project_eqcr 函数调用，不含 'eqcr' 字面量比较。
    # 该变更在任务 9 中完成；此处不登记。
    # ── _is_user_eqcr_on 正向授权系列（保持） ──
    "app/services/eqcr_workbench_service.py::EqcrWorkbenchService._is_user_eqcr_on": ConsumerEntry(
        purpose="EQCR 本人正向授权判定",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7: 只会多拒绝不会多放行",
    ),
    "app/services/eqcr_workbench_service.py::EqcrWorkbenchService.list_my_projects": ConsumerEntry(
        purpose="正向授权（本人 EQCR 项目列表）",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7",
    ),
    "app/routers/eqcr/time_tracking.py::eqcr_time_track_start": ConsumerEntry(
        purpose="EQCR 工时开始 - 正向授权",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7",
    ),
    "app/routers/eqcr/time_tracking.py::eqcr_time_track_stop": ConsumerEntry(
        purpose="EQCR 工时结束 - 正向授权",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7",
    ),
    "app/routers/eqcr/time_tracking.py::eqcr_time_summary": ConsumerEntry(
        purpose="EQCR 工时汇总 - 统计",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7",
    ),
    "app/routers/eqcr_judgment.py::_check_eqcr_role": ConsumerEntry(
        purpose="结构化判断提交 - 正向授权（admin 照旧放行）",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7",
    ),
    "app/services/eqcr_memo_service.py::EqcrMemoService.generate_memo": ConsumerEntry(
        purpose="EQCR 备忘录生成 - 正向授权",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="7.7",
    ),
    "app/routers/eqcr/metrics.py::get_eqcr_metrics": ConsumerEntry(
        purpose="EQCR 仪表盘统计",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="统计",
    ),
    # ── 独立性控制（保持，范围外） ──
    "app/services/sod_guard_service.py::EqcrIndependenceRule.check": ConsumerEntry(
        purpose="独立性控制 - EQCR 独立性规则",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="9.5 不变量",
    ),
    "app/services/sod_guard_service.py::validate_eqcr_sod_in_batch": ConsumerEntry(
        purpose="独立性控制 - 批内预检",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="9.5 不变量",
    ),
    "app/services/rotation_check_service.py::RotationCheckService.check_rotation": ConsumerEntry(
        purpose="轮换检查",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="各自角色口径另有缺口",
    ),
    "app/services/independence_signing_service.py::IndependenceSigningService._get_committee_members": ConsumerEntry(
        purpose="独立性复核人查询",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="独立性控制",
    ),
    "app/services/gate_rules_phase14.py::<module>": ConsumerEntry(
        purpose="独立性声明必需角色",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="独立性控制",
    ),
    "app/routers/independence.py::get_my_pending_independence": ConsumerEntry(
        purpose="核心角色项目列表",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="独立性控制",
    ),
    # ── 含 EQCR 的宽权限名单（保持，范围外） ──
    "app/routers/eqcr_issues.py::_check_eqcr_visibility": ConsumerEntry(
        purpose="问题单可见角色",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="宽权限名单",
    ),
    "app/routers/eqcr_issues.py::reply_eqcr_issue": ConsumerEntry(
        purpose="问题单回复",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="宽权限名单",
    ),
    "app/routers/eqcr_issues.py::list_eqcr_issues": ConsumerEntry(
        purpose="问题单列表",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="宽权限名单",
    ),
    "app/services/wp_permission_service.py::WpPermissionService.check_cycle_access": ConsumerEntry(
        purpose="主管角色",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="宽权限名单",
    ),
    "app/services/wp_permission_service.py::WpPermissionService.check_workpaper_access": ConsumerEntry(
        purpose="底稿权限主管角色",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="宽权限名单",
    ),
    "app/routers/wp_editor_router.py::update_sign_status": ConsumerEntry(
        purpose="签字回退角色",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="宽权限名单",
    ),
    # role_classifier 的主管名单原为写死的英文角色集合（含 'eqcr' 字面量、不认中文别名）；
    # spec procedure-trim-generation-delegation-chain 任务 14 改为取 wp_visibility/effective_scope.SUPERVISOR_ROLES，
    # 后者由 ROLE_MAP（下一条，唯一来源）派生、认「独立复核合伙人」等中文别名 ⇒ 不再含字面量，从登记表移除。
    # ── ROLE_MAP（唯一来源） ──
    "app/services/assignment_service.py::<module>": ConsumerEntry(
        purpose="ROLE_MAP 唯一来源（含 eqcr 与 独立复核合伙人）",
        recognizes_chinese_alias=True,
        treatment="保持",
        rationale="2.1: 唯一映射",
    ),
    # ── 委派通知 ──
    "app/services/assignment_service.py::AssignmentService._send_assignment_notifications": ConsumerEntry(
        purpose="委派通知角色显示名映射",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="通知文案",
    ),
    # ── 口径存疑位置（判读后登记） ──
    "app/services/a21_a25_version_selector.py::_determine_applicability": ConsumerEntry(
        purpose="A25 复核表版本选择 - eqcr 在适用角色名单中",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="版本选择逻辑",
    ),
    "app/services/event_handlers/_impl.py::_notify_adjustment_event_sse": ConsumerEntry(
        purpose="调整分录事件通知 - eqcr 在接收角色名单中",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="事件通知",
    ),
    "app/services/wp_cell_lock_service.py::WpCellLockService.can_edit_cell": ConsumerEntry(
        purpose="单元格锁定 - eqcr 角色权限映射",
        recognizes_chinese_alias=False,
        treatment="保持，范围外",
        rationale="锁定逻辑",
    ),
    # ── project_permissions ──
    "app/services/project_permissions.py::<module>": ConsumerEntry(
        purpose="EQCR 专属权限映射",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="正向授权",
    ),
    # ── review_rbac_guard ──
    "app/services/review_rbac_guard.py::<module>": ConsumerEntry(
        purpose="A25 → eqcr 角色映射",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="正向授权",
    ),
    # ── eqcr/__init__ ──
    "app/routers/eqcr/__init__.py::<module>": ConsumerEntry(
        purpose="EQCR 路由子包角色常量",
        recognizes_chinese_alias=False,
        treatment="保持",
        rationale="路由注册",
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# AST 扫描器
# ═══════════════════════════════════════════════════════════════════════════
def _enclosing_function(tree: ast.Module, lineno: int) -> str:
    """获取给定行号的最内层包围函数名（含类名）。"""
    best = "<module>"
    # First pass: plain functions
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                best = node.name
    # Second pass: class methods (prefer more specific)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.lineno <= lineno <= (child.end_lineno or child.lineno):
                        best = f"{node.name}.{child.name}"
    return best


def _has_eqcr_literal(node: ast.AST) -> bool:
    """节点是否包含 EQCR 字面量。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in _EQCR_LITERALS
    return False


def _scan_eqcr_delegation_references(path: Path) -> set[str]:
    """扫描单个文件中与委派角色 'eqcr' 相关的位置。

    三种检索口径（design §4.14）：
    1. 委派角色值与字面量 'eqcr' 作相等/不等/成员判断
    2. 把 'eqcr' 列入委派角色名单（集合/列表/元组/字典键）
    3. 以委派角色为键取 EQCR 专属权限（字典键）
    """
    try:
        src = path.read_text("utf-8")
        tree = ast.parse(src, filename=str(path))
    except Exception:
        return set()

    rel_path = str(path.relative_to(_APP_DIR.parent)).replace("\\", "/")
    hits: set[str] = set()

    for node in ast.walk(tree):
        # 1. Comparisons: == / != / in / not in
        if isinstance(node, ast.Compare):
            has_eqcr = False
            if _has_eqcr_literal(node.left):
                has_eqcr = True
            for comp in node.comparators:
                if _has_eqcr_literal(comp):
                    has_eqcr = True
            if has_eqcr:
                func = _enclosing_function(tree, node.lineno)
                hits.add(f"{rel_path}::{func}")

        # 2. Collection members (set, list, tuple)
        if isinstance(node, (ast.List, ast.Set, ast.Tuple)):
            for elt in node.elts:
                if _has_eqcr_literal(elt):
                    func = _enclosing_function(tree, node.lineno)
                    hits.add(f"{rel_path}::{func}")
                    break

        # 3. Dict keys
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None and _has_eqcr_literal(key):
                    func = _enclosing_function(tree, node.lineno)
                    hits.add(f"{rel_path}::{func}")
                    break

    return hits


def scan_all_eqcr_consumers() -> set[str]:
    """扫描 app/ 下所有 Python 文件，返回包含委派角色 EQCR 引用的 '文件::函数' 集合。

    排除已知的全局角色比较位置。
    """
    results: set[str] = set()
    for root, dirs, files in os.walk(_APP_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if not f.endswith(".py"):
                continue
            filepath = Path(root) / f
            rel = str(filepath.relative_to(_APP_DIR.parent)).replace("\\", "/")
            # 排除全局角色比较文件
            if rel in _GLOBAL_ROLE_FILES:
                continue
            results |= _scan_eqcr_delegation_references(filepath)
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════════════════
class TestEqcrConsumerInventoryBidirectional:
    """扫描结果与登记表键集合双向相等。"""

    def test_scan_matches_registry(self) -> None:
        """AST 扫描找到的 EQCR 消费方 == 登记表键集合。

        新增未登记或登记已消失都打红。
        """
        scanned = scan_all_eqcr_consumers()
        registered = set(EQCR_CONSUMER_REGISTRY.keys())

        unregistered = sorted(scanned - registered)
        disappeared = sorted(registered - scanned)

        msg_parts: list[str] = []
        if unregistered:
            msg_parts.append(f"扫描到但未登记（须补入登记表）：\n" + "\n".join(f"  - {u}" for u in unregistered))
        if disappeared:
            msg_parts.append(f"已登记但扫描不到（须从登记表移除）：\n" + "\n".join(f"  - {d}" for d in disappeared))

        assert not msg_parts, "\n\n".join(msg_parts)

    def test_registry_not_empty(self) -> None:
        """登记表非空（防止扫描器和登记表同时为空的假绿）。"""
        assert len(EQCR_CONSUMER_REGISTRY) > 10, (
            f"登记表只有 {len(EQCR_CONSUMER_REGISTRY)} 条，预期至少 10 条"
        )

    def test_every_entry_has_required_fields(self) -> None:
        """每个登记条目都有完整的四个字段。"""
        for key, entry in EQCR_CONSUMER_REGISTRY.items():
            assert entry.purpose, f"{key}: 缺 purpose"
            assert entry.treatment, f"{key}: 缺 treatment"
            assert entry.rationale, f"{key}: 缺 rationale"


class TestEqcrPositiveAuthorizationUnchanged:
    """需求 7.7：全局 eqcr 但无本项目 EQCR 委派 → 正向授权端点拒绝。

    验证 ``_is_user_eqcr_on`` 只查委派不看全局角色这一既有行为不变。
    """

    @pytest.mark.asyncio
    async def test_global_eqcr_without_delegation_rejected_by_workbench(self) -> None:
        """全局 eqcr 在项目 P 无委派 → _is_user_eqcr_on 返回 False。"""
        import uuid
        from unittest.mock import AsyncMock, MagicMock

        from app.services.eqcr_workbench_service import EqcrWorkbenchService

        # _is_user_eqcr_on 执行 (await self.db.execute(q)).scalar() or 0
        # 无委派时 scalar() 返回 0
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar.return_value = 0
        db.execute.return_value = result_mock

        service = EqcrWorkbenchService(db)
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = await service._is_user_eqcr_on(user_id, project_id)
        assert result is False, "全局 eqcr 无委派应被正向授权拒绝"

    @pytest.mark.asyncio
    async def test_global_eqcr_with_delegation_accepted_by_workbench(self) -> None:
        """全局 eqcr 在项目 P 有 eqcr 委派 → _is_user_eqcr_on 返回 True。"""
        import uuid
        from unittest.mock import AsyncMock, MagicMock

        from app.services.eqcr_workbench_service import EqcrWorkbenchService

        db = AsyncMock()
        result_mock = MagicMock()
        # 有一条委派记录：scalar() 返回 1
        result_mock.scalar.return_value = 1
        db.execute.return_value = result_mock

        service = EqcrWorkbenchService(db)
        project_id = uuid.uuid4()
        user_id = uuid.uuid4()

        result = await service._is_user_eqcr_on(user_id, project_id)
        assert result is True, "有 eqcr 委派应被正向授权接受"

    @pytest.mark.asyncio
    async def test_is_project_eqcr_global_role_alone_returns_true(self) -> None:
        """is_project_eqcr 对全局 eqcr 用户始终返回 True（无论有无委派）。

        这与 _is_user_eqcr_on（只查委派）的行为不同。
        """
        import uuid
        from unittest.mock import AsyncMock, MagicMock

        from app.models.base import UserRole
        from app.models.core import User
        from app.services.eqcr_resolver import is_project_eqcr

        user = MagicMock(spec=User)
        user.role = UserRole.eqcr
        user.id = uuid.uuid4()

        db = AsyncMock()
        project_id = uuid.uuid4()

        result = await is_project_eqcr(db, user, project_id)
        assert result is True, "全局 eqcr → is_project_eqcr 应为 True"

    @pytest.mark.asyncio
    async def test_is_project_eqcr_non_eqcr_global_without_delegation(self) -> None:
        """非 eqcr 全局角色 + 无委派 → is_project_eqcr 返回 False。"""
        import uuid
        from unittest.mock import AsyncMock, MagicMock

        from app.models.base import UserRole
        from app.models.core import User
        from app.services.eqcr_resolver import is_project_eqcr

        user = MagicMock(spec=User)
        user.role = UserRole.auditor
        user.id = uuid.uuid4()

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar.return_value = 0
        db.execute.return_value = result_mock

        project_id = uuid.uuid4()

        result = await is_project_eqcr(db, user, project_id)
        assert result is False, "非 eqcr 全局角色 + 无委派 → False"
