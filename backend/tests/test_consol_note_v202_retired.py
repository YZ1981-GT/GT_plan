"""守卫：V202（合并附注映射规则模板库 / 值确认 / 结构锁）已整体退役（spec note-pull-followup-closure R16）。

退役后再有人加回调用 / 路由 / 模型、或迁移被改，这里打红。保留且在用的只有子企业保存 → 合并附注标 is_stale
（``consol_note_value_change_service.on_note_section_saved``，见 ``test_consol_note_value_change.py``）。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
import pkgutil
import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
_FRONTEND_SRC = _REPO / "audit-platform" / "frontend" / "src"

_RETIRED_MODULES = (
    "app.models.consol_note_mapping_template_models",
    "app.services.consol_note_value_confirmation_service",
    "app.services.consol_note_structure_lock_service",
    "app.services.consol_note_mapping_template_service",
    "app.routers.consol_note_mapping_templates",
)
_RETIRED_TABLES = (
    "consol_note_mapping_rule_template",
    "consol_note_structure_lock",
    "consol_note_structure_lock_entity",
    "consol_note_value_confirmation",
)
_RETIRED_PATH_RE = re.compile(
    r"consol-note-mapping-templates|consol-note-structure-lock|consol-note-value/|consol-note-account-reference"
    r"|consol-note-mapping/rules/[^/]+/promote"
)


@pytest.mark.parametrize("module", _RETIRED_MODULES)
def test_retired_module_is_gone(module: str) -> None:
    assert importlib.util.find_spec(module) is None, f"{module} 应已删除"


def test_no_app_code_imports_retired_modules() -> None:
    """全应用 AST 扫 import（含函数体内的延迟导入）：不得再引用已删模块。"""
    offenders: list[str] = []
    for path in (_BACKEND / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))  # 个别文件带 BOM
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            if any(n in _RETIRED_MODULES for n in names):
                offenders.append(f"{path.relative_to(_BACKEND)}:{node.lineno}")
    assert offenders == []


def test_retired_tables_and_column_not_in_orm() -> None:
    import app.models as models_pkg

    for info in pkgutil.walk_packages(models_pkg.__path__, prefix="app.models."):
        importlib.import_module(info.name)
    from app.models.base import Base
    from app.models.consol_note_mapping_models import ConsolNoteMappingRule

    assert set(_RETIRED_TABLES) & set(Base.metadata.tables) == set()
    assert "promoted_to_template_id" not in ConsolNoteMappingRule.__table__.c


def test_no_registered_route_serves_retired_paths() -> None:
    from app.main import app

    hits = sorted(r.path for r in app.routes if _RETIRED_PATH_RE.search(getattr(r, "path", "")))
    assert hits == []
    # 对照：仍在用的明细映射 / 下推端点照常注册（正则没把整片合并附注路由误判成已退役）
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/consolidation/notes/{project_id}/{year}/push-template" in paths


def test_event_type_and_push_lock_parameters_removed() -> None:
    from app.models.audit_platform_schemas import EventType
    from app.routers.consol_notes import PushTemplateRequest
    from app.services.consol_note_template_push_service import push_template_to_subsidiaries
    from app.services.consol_note_value_change_service import on_note_section_saved

    assert not hasattr(EventType, "CONSOL_NOTE_VALUE_CHANGED")
    assert "activate_lock" not in PushTemplateRequest.model_fields
    assert "activate_lock" not in inspect.signature(push_template_to_subsidiaries).parameters
    # 值指纹随值确认退役：保存只标 is_stale，不再收行数据
    assert "rows" not in inspect.signature(on_note_section_saved).parameters


def _statements(sql: str) -> list[str]:
    body = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return [" ".join(s.split()) for s in body.split(";") if s.strip()]


def test_v208_drops_column_first_then_tables_and_r208_recreates_them() -> None:
    migrations = _BACKEND / "migrations"
    v208 = _statements((migrations / "V208__retire_consol_note_v202.sql").read_text(encoding="utf-8"))
    assert v208 == [
        "ALTER TABLE consol_note_mapping_rule DROP COLUMN IF EXISTS promoted_to_template_id",
        "DROP TABLE IF EXISTS consol_note_value_confirmation",
        "DROP TABLE IF EXISTS consol_note_structure_lock_entity",
        "DROP TABLE IF EXISTS consol_note_structure_lock",
        "DROP TABLE IF EXISTS consol_note_mapping_rule_template",
    ]
    r208 = (migrations / "R208__retire_consol_note_v202.sql").read_text(encoding="utf-8")
    v202 = (migrations / "V202__consol_note_mapping_reuse_and_reference.sql").read_text(encoding="utf-8")
    # 回滚按 V202 原样重建：建表 / 建索引 / 加列语句逐条一致
    assert _statements(r208) == _statements(v202)


def test_frontend_dead_code_removed() -> None:
    assert not (_FRONTEND_SRC / "composables" / "useConsolNoteReuse.ts").exists()
    report_paths = (_FRONTEND_SRC / "services" / "apiPaths" / "report.ts").read_text(encoding="utf-8")
    index_paths = (_FRONTEND_SRC / "services" / "apiPaths" / "index.ts").read_text(encoding="utf-8")
    assert "consolNoteReuse" not in report_paths and "consolNoteReuse" not in index_paths
    assert not _RETIRED_PATH_RE.search(report_paths)
    push = (_FRONTEND_SRC / "components" / "consolidation" / "composables" / "consolNoteTemplatePush.ts")
    assert "activate_lock" not in push.read_text(encoding="utf-8")
