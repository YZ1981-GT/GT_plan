"""T18 项目状态写入点、版本锁接线与生产调用完整性守卫。"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "backend" / "app"

EXPECTED_WRITERS = {
    ("backend/app/routers/archived_exception.py", "unarchive_project", "execution"),
    ("backend/app/services/archive_orchestrator.py", "_step_lock", "archived"),
    ("backend/app/services/deliverable_service.py", "archive_project_deliverables", "archived"),
    ("backend/app/services/event_handlers/_impl.py", "_advance_project_status_on_dataset_activated", "execution"),
    ("backend/app/services/project_wizard_service.py", "confirm_project", "planning"),
}


def _read(path: Path) -> str:
    # utf-8-sig：仓库里有既有文件带 BOM（note_offline.py 等），用 utf-8 读会让 ast.parse
    # 撞 U+FEFF 直接崩，守卫扫描全 app 必须对带/不带 BOM 的文件都稳。
    return path.read_text(encoding="utf-8-sig")


def _tree(rel: str) -> ast.Module:
    return ast.parse(_read(ROOT / rel))


def _function(rel: str, name: str) -> ast.AsyncFunctionDef:
    return next(n for n in ast.walk(_tree(rel)) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)


def _calls(fn: ast.AST, name: str) -> list[ast.Call]:
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)
            and (getattr(n.func, "id", None) == name or getattr(n.func, "attr", None) == name)]


def _status_writers() -> set[tuple[str, str, str]]:
    found: set[tuple[str, str, str]] = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(_read(path))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(t, ast.Attribute) and t.attr == "status" for t in node.targets):
                continue
            if not isinstance(node.value, ast.Attribute) or not isinstance(node.value.value, ast.Name) \
                    or node.value.value.id != "ProjectStatus":
                continue
            owner = parents.get(node)
            while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = parents.get(owner)
            found.add((path.relative_to(ROOT).as_posix(), getattr(owner, "name", "<module>"), node.value.attr))
    return found


def test_project_status_writers_are_exactly_the_five_reviewed_paths():
    assert _status_writers() == EXPECTED_WRITERS


def test_both_archive_writers_lock_before_archived_assignment():
    for rel, fn_name in (
        ("backend/app/services/archive_orchestrator.py", "_step_lock"),
        ("backend/app/services/deliverable_service.py", "archive_project_deliverables"),
    ):
        fn = _function(rel, fn_name)
        lock_lines = [c.lineno for c in _calls(fn, "lock_project_registry")]
        archived_lines = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
                          and isinstance(n.value, ast.Attribute) and n.value.attr == "archived"]
        assert len(lock_lines) == 1 and len(archived_lines) == 1, rel
        assert lock_lines[0] < archived_lines[0], rel


def test_unarchive_unlocks_before_commit_and_audits_old_version():
    fn = _function("backend/app/routers/archived_exception.py", "unarchive_project")
    unlock = _calls(fn, "unlock_project_registry")
    commits = _calls(fn, "commit")
    assert len(unlock) == 1 and commits and unlock[0].lineno < min(c.lineno for c in commits)
    constants = {n.value for n in ast.walk(fn) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert "acnr_registry_version_unlocked" in constants


def test_event_handler_only_promotes_created_or_planning():
    fn = _function(
        "backend/app/services/event_handlers/_impl.py",
        "_advance_project_status_on_dataset_activated",
    )
    text = ast.unparse(fn)
    assert "cur not in ('created', 'planning')" in text


def test_wizard_archived_is_stable_409():
    fn = _function("backend/app/services/project_wizard_service.py", "confirm_project")
    text = ast.unparse(fn)
    assert "ProjectStatus.archived" in text
    assert "status_code=409" in text and "PROJECT_ARCHIVED" in text


def test_no_raw_sql_updates_project_status():
    # 只认真的「裸 SQL 改 projects.status」：UPDATE projects 自己的 SET 子句写 status = ...。
    # 旧粗判（文件里同时出现 "UPDATE projects" 和 "status" 两词）会误报 —— recycle_bin 改
    # parent_project_id、continuous_audit 改 prior_year_project_id、note_group_template 改
    # wizard_state，这几处 SQL 都不碰 status，只是文件别处恰好出现了 status 这个词。
    import re
    offenders = []
    for path in APP.rglob("*.py"):
        text = _read(path)
        for m in re.finditer(r"UPDATE\s+projects\b", text, re.IGNORECASE):
            # 截到本条语句末（下一个分号或下一条 UPDATE projects 之前），只看它自己的 SET
            stmt = re.split(r";|UPDATE\s+projects\b", text[m.end():], maxsplit=1)[0]
            if re.search(r"\bSET\b.*?\bstatus\b\s*=", stmt, re.IGNORECASE | re.DOTALL):
                line = text[:m.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line}")
    assert offenders == []


def test_full_resolve_project_calls_always_pass_db_in_production():
    # T20 已用 AST 守卫（test_cross_sheet_identity_paths）钉死：生产构造 CrossSheetResolver 全传
    # resolve_identity=False，桥接函数 _sync_resolve 只在 _bridge_identity 的 if self._resolve_identity
    # 分支里被调用，生产不可达（RV7.7-01 / 台账 notes）。它是同步纯 BFS 上下文、本就拿不到 db，
    # 这处 full_resolve(project_id=...) 不传 db 属该不可达路径，不计入「生产调用」。
    _UNREACHABLE_BRIDGES = {
        ("backend/app/services/custom_query/cross_sheet_resolver.py", "_sync_resolve"),
    }
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        tree = ast.parse(_read(path))
        parents: dict[ast.AST, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", getattr(node.func, "attr", None)) != "full_resolve":
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            if "project_id" not in kw or "db" in kw:
                continue
            owner = parents.get(node)
            while owner is not None and not isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                owner = parents.get(owner)
            owner_name = getattr(owner, "name", "<module>")
            if (rel, owner_name) in _UNREACHABLE_BRIDGES:
                continue
            offenders.append(f"{rel}:{node.lineno}")
    assert offenders == []


def test_in_memory_project_lock_api_is_absent():
    tree = _tree("backend/app/services/acnr/immutability.py")
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    assert not names & {
        "ProjectRegistryVersionRecord", "record_project_registry_version", "get_project_registry_version",
        "remove_project_registry_version", "list_archived_projects", "clear_all_project_versions",
    }
