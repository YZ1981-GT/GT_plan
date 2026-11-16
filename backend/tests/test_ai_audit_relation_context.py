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


# ---------------------------------------------------------------------------
# 底稿证据按 evidence_links 取（2026-11-15 真实库实测抓到的静默失效）
#
# 缺陷：原实现用 `EvidenceRef.source_id == host.resource_id`（底稿 id）匹配，
# 但真实库 29 条 active evidence_refs 的 source_id 全部是 **attachment_version id**
# （都能在 attachment_versions 里找到，wp_id 一条都匹配不上）⇒ 底稿宿主的
# evidence 段永远 0 条。底稿证据的权威来源是 evidence_links(wp_id, attachment_id)。
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workpaper_evidence_uses_evidence_links_not_evidence_refs() -> None:
    """底稿宿主必须查 evidence_links(wp_id)，且不得再用 source_id 当 wp_id。"""
    project_id, wp_id = uuid4(), uuid4()
    attachment_id, link_id = uuid4(), uuid4()
    db = _Db([
        _Result(scalar="E1"),                      # wp_code
        _Result(rows=[]),                          # 关联底稿
        _Result(rows=[]),                          # TB
        _Result(rows=[]),                          # 调整
        _Result(rows=[]),                          # 报表（无 report_row 时可能不查）
        _Result(rows=[]),                          # 附注
        _Result(scalar=None),                      # 上年项目
        _Result(rows=[SimpleNamespace(             # evidence_links 命中 1 条
            id=link_id, attachment_id=attachment_id, sheet_name="审定表E1-1",
            cell_ref="C8", evidence_type="voucher", check_conclusion="相符",
            created_at=None, file_name="银行回单.pdf",
        )]),
        _Result(rows=[]),                          # 知识标签
    ])
    host = SimpleNamespace(
        project_id=project_id, year=2025,
        resource_type=HostType.workpaper, resource_id=str(wp_id),
    )
    rows = await build_audit_relation_context(
        db, host=host, user=SimpleNamespace(id=uuid4())
    )
    evidence = [row for row in rows if row.source_type == "evidence"]
    assert len(evidence) == 1, rows
    item = evidence[0]
    assert "银行回单.pdf" in item.label
    assert "审定表E1-1!C8" in item.content
    assert "相符" in item.content
    assert item.jump_route == f"/attachments?attachment_id={attachment_id}"

    joined = " ".join(db.statements).lower()
    assert "evidence_links" in joined, "底稿证据必须查 evidence_links"
    # 底稿宿主不得再拿 wp id 去 evidence_refs.source_id 匹配
    assert "evidence_refs" not in joined, "底稿宿主不应再查 evidence_refs"


@pytest.mark.asyncio
async def test_note_host_still_uses_evidence_refs_source_id() -> None:
    """非底稿宿主保留 EvidenceRef.source_id 语义（该列对非底稿源是正确的）。"""
    project_id, note_id = uuid4(), uuid4()
    db = _Db([
        _Result(scalar="五、1"),                   # note_section
        _Result(rows=[]),                          # 关联底稿
        _Result(rows=[]),                          # TB
        _Result(rows=[]),                          # 调整
        _Result(rows=[]),                          # 报表
        _Result(rows=[]),                          # 附注
        _Result(scalar=None),                      # 上年项目
        _Result(rows=[SimpleNamespace(
            id=uuid4(), label="回函扫描件", evidence_type="confirmation",
            evidence_id="ev-1", created_at=None,
        )]),
        _Result(rows=[]),                          # 知识标签
    ])
    host = SimpleNamespace(
        project_id=project_id, year=2025,
        resource_type=HostType.note, resource_id=str(note_id),
    )
    rows = await build_audit_relation_context(
        db, host=host, user=SimpleNamespace(id=uuid4())
    )
    evidence = [row for row in rows if row.source_type == "evidence"]
    assert len(evidence) == 1
    assert "回函扫描件" in evidence[0].label
    joined = " ".join(db.statements).lower()
    assert "evidence_refs" in joined
    assert "evidence_links" not in joined
