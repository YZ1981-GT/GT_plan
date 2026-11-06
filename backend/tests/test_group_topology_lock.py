"""集团拓扑年度逻辑锁接线与 SQLite 兼容守卫。"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.services.group_topology_lock import (
    NULL_AUDIT_YEAR_LOCK_KEY,
    lock_topology_years,
)

pytest_plugins = ("tests._batch_project_fixtures",)
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_sqlite_topology_lock_is_sorted_noop_and_keeps_empty_year(db):
    assert await lock_topology_years(db, [2026, None, 2025, 2026]) == (
        NULL_AUDIT_YEAR_LOCK_KEY,
        2025,
        2026,
    )


def _functions(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _call_lines(node: ast.AST, name: str) -> list[int]:
    out = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        called = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
        if called == name:
            out.append(child.lineno)
    return out


@pytest.mark.parametrize(("relative", "symbol", "first_sensitive"), [
    ("app/services/batch_project_execution.py", "apply_validation_plan", "load_dependency_inventory"),
    ("app/services/batch_project_plan.py", "parse_and_import", "load_dependency_inventory"),
    ("app/services/project_wizard_service.py", "create_project", "check_uniqueness"),
    ("app/services/project_wizard_service.py", "update_step", "prepare_group_fields"),
    ("app/services/continuous_audit_service.py", "create_next_year", "check_uniqueness"),
    ("app/services/group_links.py", "sync_group_links", "load_year_records"),
    ("app/services/group_links.py", "reparent_project", "load_year_records"),
    ("app/services/group_links.py", "update_group_relationship", "load_year_records"),
    ("app/services/project_subsidiary_attachment_service.py", "attach_subsidiaries", "apply_group_values"),
    ("app/routers/project_wizard.py", "delete_project", "soft_delete"),
    ("app/routers/project_wizard.py", "batch_delete_projects", "soft_delete"),
    # 项目配置的读写自 platform-global-display-settings-closure 起收进 ProjectConfigService（路由只管提交）
    ("app/services/project_config_service.py", "update_config", "flush"),
    ("app/services/standard_unification_service.py", "set_standard", "_read_standard"),
])
def test_topology_writers_lock_before_sensitive_work(relative: str, symbol: str, first_sensitive: str):
    node = _functions(ROOT / relative)[symbol]
    locks = _call_lines(node, "lock_topology_years")
    sensitive = _call_lines(node, first_sensitive)
    assert locks and sensitive, f"guard vacuous: {relative}:{symbol}"
    assert min(locks) < min(sensitive), f"{relative}:{symbol} must lock before {first_sensitive}"


def test_project_restore_locks_before_clearing_deleted_flag():
    source = (ROOT / "app/routers/recycle_bin.py").read_text(encoding="utf-8")
    block = source.split("async def restore_item(", 1)[1].split("@router.delete", 1)[0]
    assert "lock_topology_years" in block and "row.is_deleted = False" in block
    assert block.index("lock_topology_years") < block.index("row.is_deleted = False")


def test_all_group_link_recompute_callers_are_explicitly_reviewed():
    expected = {
        ("app/services/project_config_service.py", "update_config"),
        ("app/services/project_subsidiary_attachment_service.py", "attach_subsidiaries"),
        ("app/routers/project_wizard.py", "delete_project"),
        ("app/routers/project_wizard.py", "batch_delete_projects"),
        ("app/routers/recycle_bin.py", "restore_item"),
        ("app/services/batch_project_execution.py", "apply_validation_plan"),
        ("app/services/batch_project_plan.py", "parse_and_import"),
        ("app/services/continuous_audit_service.py", "create_next_year"),
        ("app/services/group_links.py", "sync_group_links_for"),
        ("app/services/group_links.py", "reparent_project"),
        ("app/services/group_links.py", "update_group_relationship"),
        ("app/services/project_wizard_service.py", "create_project"),
        ("app/services/project_wizard_service.py", "update_step"),
        ("app/services/standard_unification_service.py", "set_standard"),
    }
    found: set[tuple[str, str]] = set()
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _call_lines(node, "sync_group_links") or _call_lines(node, "sync_group_links_for"):
                found.add((relative, node.name))
    assert found == expected


# ── 三码 / 年度 / 口径写入面的冻结守卫（不只看 sync 调用方） ──────────────────────
_TOPOLOGY_FIELDS = {
    "company_code", "parent_company_code", "ultimate_company_code",
    "relation_to_parent", "audit_year", "report_scope",
}
_TOPOLOGY_HELPERS = {
    "apply_group_values", "_sync_basic_info_to_project", "propagate_to_counterpart",
    "update_group_relationship", "reparent_project",
}
_RAW_PROJECT_UPDATE = re.compile(r"\bupdate\s+projects\b", re.IGNORECASE)
# 这两个入口在自身首个敏感读取前取年度锁（上方顺序守卫已逐个钉住）。
_SELF_LOCKING_HELPERS = {"update_group_relationship", "reparent_project"}
# 本身不取锁的共享写助手：其每个调用点都必须已在同一函数内先取年度锁。
_CALLER_LOCKED_HELPERS = {
    ("app/services/group_links.py", "propagate_to_counterpart"): "propagate_to_counterpart",
    ("app/services/project_wizard_service.py", "_sync_basic_info_to_project"): "_sync_basic_info_to_project",
}
_PROJECT_TOPOLOGY_WRITERS = {
    ("app/services/project_config_service.py", "ProjectConfigService.update_config"),
    ("app/routers/project_wizard.py", "update_parent_code"),
    ("app/services/batch_project_execution.py", "apply_validation_plan"),
    ("app/services/continuous_audit_service.py", "ContinuousAuditService.create_next_year"),
    ("app/services/group_links.py", "propagate_to_counterpart"),
    ("app/services/group_links.py", "reparent_project"),
    ("app/services/group_links.py", "update_group_relationship"),
    ("app/services/project_subsidiary_attachment_service.py", "attach_subsidiaries"),
    ("app/services/project_wizard_service.py", "_sync_basic_info_to_project"),
    ("app/services/project_wizard_service.py", "create_project"),
    ("app/services/project_wizard_service.py", "update_step"),
    ("app/services/standard_unification_service.py", "StandardUnificationService.set_standard"),
}
# 命中扫描形态但不写 projects 行：每条都写明对象类型，新增命中必须重新裁决。
_NON_PROJECT_TARGETS = {
    ("app/routers/project_wizard.py", "list_available_subsidiaries"): "响应 DTO",
    ("app/routers/voucher_links.py", "sample_voucher"): "凭证行企业代码",
    ("app/routers/voucher_links.py", "_attach_one"): "凭证行企业代码",
    ("app/services/batch_project_plan.py", "_prepare_create_group_fields"): "内存计划行",
    ("app/services/evidence_governance/offline_manifest_verifier.py",
     "OfflineManifestVerifier.verify_package"): "离线校验结果",
    ("app/services/group_links.py", "normalize_group_fields"): "建项请求 schema",
    ("app/services/group_links.py", "inherit_from_counterpart"): "建项请求 schema",
    ("app/services/group_links.py", "infer_ultimate_from_parent"): "建项请求 schema / probe",
    ("app/services/group_links.py", "default_relation_by_name"): "建项请求 schema",
}


def _called(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _scan_source(source: str, relative: str):
    """返回 (拓扑写入命中, 每个函数内的调用行)。owner 用类名.函数名的限定名。"""
    tree = ast.parse(source)
    hits: list[tuple[str, str, str, int]] = []
    calls: dict[tuple[str, str], list[tuple[str, int]]] = {}

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            current = owner
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                current = f"{owner}.{child.name}" if owner else child.name
            if isinstance(child, ast.Call):
                name = _called(child.func)
                calls.setdefault((relative, owner), []).append((name, child.lineno))
                keywords = {item.arg for item in child.keywords if item.arg}
                if name == "Project" and keywords & _TOPOLOGY_FIELDS:
                    hits.append((relative, owner, "project_ctor", child.lineno))
                if name in _TOPOLOGY_HELPERS:
                    hits.append((relative, owner, name, child.lineno))
                if name == "values" and isinstance(child.func, ast.Attribute):
                    if "update(Project)" in ast.unparse(child.func.value) and keywords & _TOPOLOGY_FIELDS:
                        hits.append((relative, owner, "orm_update", child.lineno))
            if isinstance(child, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for target in targets:
                    if isinstance(target, ast.Attribute) and target.attr in _TOPOLOGY_FIELDS:
                        hits.append((relative, owner, "attr_assign", child.lineno))
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                text = child.value
                if _RAW_PROJECT_UPDATE.search(text) and any(f in text for f in _TOPOLOGY_FIELDS):
                    hits.append((relative, owner, "raw_sql", child.lineno))
            visit(child, current)

    visit(tree, "")
    return hits, calls


def _scan_app():
    hits: list[tuple[str, str, str, int]] = []
    calls: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for path in sorted((ROOT / "app").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        file_hits, file_calls = _scan_source(path.read_text(encoding="utf-8-sig"), relative)
        hits.extend(file_hits)
        calls.update(file_calls)
    return hits, calls


def _unlocked_writes(hits, calls) -> list[tuple[str, str, str, int]]:
    """写入命中所在函数若不是“调用方持锁”的共享助手，必须先于写入取年度锁。"""
    bad = []
    for relative, owner, kind, line in hits:
        if (relative, owner) in _NON_PROJECT_TARGETS or (relative, owner) in _CALLER_LOCKED_HELPERS:
            continue
        if kind in _SELF_LOCKING_HELPERS:
            continue
        lock_lines = [
            call_line for name, call_line in calls.get((relative, owner), [])
            if name == "lock_topology_years"
        ]
        if not lock_lines or min(lock_lines) > line:
            bad.append((relative, owner, kind, line))
    return bad


def test_project_topology_write_surface_is_frozen_and_classified():
    hits, _calls = _scan_app()
    found = {(relative, owner) for relative, owner, _kind, _line in hits}
    expected = _PROJECT_TOPOLOGY_WRITERS | set(_NON_PROJECT_TARGETS)
    assert found == expected, {
        "new_unreviewed": sorted(found - expected),
        "stale_entries": sorted(expected - found),
    }


def test_every_project_topology_write_runs_after_year_lock():
    hits, calls = _scan_app()
    assert _unlocked_writes(hits, calls) == []
    for (relative, owner), helper in _CALLER_LOCKED_HELPERS.items():
        call_sites = [
            (site, name, line)
            for site, site_calls in calls.items()
            for name, line in site_calls
            if name == helper
        ]
        assert call_sites, f"guard vacuous: {relative}:{owner} 无调用点"
        for site, _name, line in call_sites:
            lock_lines = [
                call_line for name, call_line in calls.get(site, [])
                if name == "lock_topology_years"
            ]
            assert lock_lines and min(lock_lines) < line, f"{site} 调用 {helper} 前未取年度锁"


def test_topology_write_guard_detects_unlocked_constructor_and_accepts_locked_one():
    unlocked = """
async def create_bad(db):
    project = Project(company_code="X", audit_year=2026)
    await lock_topology_years(db, [2026])
"""
    locked = """
async def create_good(db):
    await lock_topology_years(db, [2026])
    project = Project(company_code="X", audit_year=2026)
"""
    bad_hits, bad_calls = _scan_source(unlocked, "sample/bad.py")
    good_hits, good_calls = _scan_source(locked, "sample/good.py")
    assert _unlocked_writes(bad_hits, bad_calls) == [("sample/bad.py", "create_bad", "project_ctor", 3)]
    assert good_hits and _unlocked_writes(good_hits, good_calls) == []


_MEMBERSHIP_LOCKS = {"lock_actor_and_project_memberships", "_lock_plan_memberships"}
_PERMISSION_CHECKS = {"assert_project_permission", "_assert_plan_project_access"}
_MEMBERSHIP_GATED_WRITERS = {
    ("app/services/project_creation_coordinator.py", "create_project_for_actor"),
    ("app/services/batch_project_plan.py", "parse_and_import"),
    ("app/services/batch_project_execution.py", "apply_validation_plan"),
    ("app/services/continuous_audit_service.py", "ContinuousAuditService.create_next_year"),
    ("app/services/project_subsidiary_attachment_service.py", "attach_subsidiaries"),
}


def _permission_before_membership_lock(site_calls: list[tuple[str, int]]) -> list[int]:
    lock_lines = [line for name, line in site_calls if name == "lock_topology_years"]
    if not lock_lines:
        return [-1]
    entered = min(lock_lines)
    membership = [line for name, line in site_calls if name in _MEMBERSHIP_LOCKS and line > entered]
    if not membership:
        return [-1]
    first_membership = min(membership)
    return [
        line for name, line in site_calls
        if name in _PERMISSION_CHECKS and entered < line < first_membership
    ]


def test_write_path_permission_checks_run_under_membership_locks():
    _hits, calls = _scan_app()
    for site in sorted(_MEMBERSHIP_GATED_WRITERS):
        site_calls = calls.get(site, [])
        assert any(name in _PERMISSION_CHECKS for name, _line in site_calls), f"guard vacuous: {site}"
        assert _permission_before_membership_lock(site_calls) == [], site


def test_membership_lock_guard_detects_check_before_lock():
    sample = """
async def write(db, actor):
    await lock_topology_years(db, [2026])
    await assert_project_permission(db, actor, project_id, "edit")
    await lock_actor_and_project_memberships(db, actor, [project_id])
"""
    _hits, calls = _scan_source(sample, "sample/order.py")
    assert _permission_before_membership_lock(calls[("sample/order.py", "write")]) == [4]


def test_project_purge_rechecks_deleted_state_under_restore_lock():
    """三个彻底删除入口都先拿恢复用的年度锁，再交统一 purge service；service 锁行后复核仍在回收站。

    2026-11-01 合并 a61fa626e 曾把单条删除改回已不存在的 ``_cascade_delete_project``、批量删除改成
    ``bulk_hard_delete`` 直删项目行 —— 写入方必须是 purge service，名字写死在这里。
    """
    source = (ROOT / "app/routers/recycle_bin.py").read_text(encoding="utf-8")
    _hits, calls = _scan_source(source, "app/routers/recycle_bin.py")
    for owner, writer in (
        ("permanently_delete", "_purge_project_in_current_transaction"),
        ("batch_permanently_delete", "_batch_purge_projects"),
        ("empty_recycle_bin", "_batch_purge_projects"),
    ):
        site_calls = calls[("app/routers/recycle_bin.py", owner)]
        locks = [line for name, line in site_calls if name == "_lock_deleted_projects_for_purge"]
        writes = [line for name, line in site_calls if name == writer]
        assert locks and writes and min(locks) < min(writes), owner
    called = {name for site in calls.values() for name, _line in site}
    assert "_cascade_delete_project" not in called  # 按 AST 调用判，注释里提到旧名不算
    purge = (ROOT / "app/services/project_purge_service.py").read_text(encoding="utf-8")
    lock_project = re.split(r"\n    (?:@|async def |def )", purge.split("async def _lock_project(", 1)[1], maxsplit=1)[0]
    assert "with_for_update()" in lock_project
    assert "project.is_deleted is not True" in lock_project
