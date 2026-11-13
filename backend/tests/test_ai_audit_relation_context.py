"""Chat 审计关系上下文：项目/年度边界与底稿逐项可见性。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.ai_chat.audit_relation_context import build_audit_relation_context
from app.services.ai_chat.contracts import HostType


class _Result:
    def __init__(self, *, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows


class _Db:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return self.results.pop(0)


@pytest.mark.asyncio
async def test_relation_context_filters_each_workpaper_and_uses_authorized_scope() -> None:
    project_id, current_id, visible_id, hidden_id = uuid4(), uuid4(), uuid4(), uuid4()
    db = _Db([
        _Result(scalar="E1"),
        _Result(rows=[
            (current_id, 3, "E1", "货币资金"),
            (visible_id, 2, "E1-1", "货币资金审定表"),
            (hidden_id, 1, "E1-2", "现金明细表"),
        ]),
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(rows=[]),
        _Result(scalar=None),   # prior project (None → skip prior-year queries)
        _Result(rows=[]),        # evidence_rows
        _Result(rows=[]),        # knowledge_rows (empty → no resolve_subject call)
    ])
    host = SimpleNamespace(
        project_id=project_id, year=2025,
        resource_type=HostType.workpaper, resource_id=str(current_id),
    )
    gate = AsyncMock(side_effect=[SimpleNamespace(project_id=project_id), None])
    with patch("app.services.wp_visibility.entry_integration.try_gate_wp", new=gate):
        rows = await build_audit_relation_context(
            db, host=host, user=SimpleNamespace(id=uuid4())
        )

    workpapers = [row for row in rows if row.source_type == "workpaper"]
    assert [row.source_id for row in workpapers] == [str(visible_id)]
    assert gate.await_count == 2
    assert all(call.kwargs["action"] == "ai_read" for call in gate.await_args_list)
    assert all(call.kwargs["wp_id"] != current_id for call in gate.await_args_list)
    # 核心关系查询（TB/调整/报表/附注）都在服务端绑定已授权 project；年度型数据还绑定 host.year。
    # 知识库查询按标签不按 project（权限由 KnowledgeAccessPolicy 控制），故排除在外。
    # projects 表查询用子查询匹配 client_name，也不含字面 project_id 过滤。
    project_bound = [
        s for s in db.statements
        if "evidence_ref" not in s.lower()
        and "knowledge" not in s.lower()
        and "projects.id" not in s.lower()
    ]
    assert all("project_id" in statement for statement in project_bound), [
        s for s in project_bound if "project_id" not in s
    ]
    assert sum("year" in statement for statement in db.statements) >= 4


@pytest.mark.asyncio
async def test_relation_context_without_project_or_year_reads_nothing() -> None:
    db = _Db([])
    rows = await build_audit_relation_context(
        db,
        host=SimpleNamespace(
            project_id=None, year=None,
            resource_type=HostType.global_knowledge, resource_id="global",
        ),
        user=SimpleNamespace(id=uuid4()),
    )
    assert rows == []
    assert db.statements == []
