"""Tests for wp_audit_flow_graph endpoint — 程序表流程导航图

锚定 spec workpaper-editor-slimdown Task 17.2 + 17.3
Validates: US-16（程序表流程导航图）
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.routers.wp_audit_flow_graph import (
    STANDARD_ASSERTIONS,
    AuditFlowGraphResponse,
)


class TestStandardAssertions:
    """Test the 5 standard audit assertions are defined."""

    def test_five_assertions(self):
        assert len(STANDARD_ASSERTIONS) == 5

    def test_assertion_names(self):
        names = [a.name for a in STANDARD_ASSERTIONS]
        assert "存在" in names
        assert "完整性" in names
        assert "权利义务" in names
        assert "准确性" in names
        assert "列报" in names

    def test_assertion_ids_unique(self):
        ids = [a.id for a in STANDARD_ASSERTIONS]
        assert len(ids) == len(set(ids))


class TestAuditFlowGraphResponse:
    """Test the response model structure."""

    def test_empty_graph(self):
        resp = AuditFlowGraphResponse(
            objectives=STANDARD_ASSERTIONS,
            risks=[],
            procedures=[],
            workpapers=[],
            edges=[],
        )
        assert len(resp.objectives) == 5
        assert resp.risks == []
        assert resp.procedures == []
        assert resp.workpapers == []
        assert resp.edges == []

    def test_graph_with_data(self):
        from app.routers.wp_audit_flow_graph import (
            IdentifiedRisk,
            ProcedureNode,
            LinkedWorkpaper,
            FlowEdge,
        )

        resp = AuditFlowGraphResponse(
            objectives=STANDARD_ASSERTIONS,
            risks=[
                IdentifiedRisk(
                    id="risk-0",
                    description="应收账款存在虚假挂账风险",
                    level="significant",
                    source_wp_code="B1-1",
                )
            ],
            procedures=[
                ProcedureNode(
                    id="proc-0",
                    program_no=1,
                    category="常规★",
                    status="completed",
                    assertions=["存在", "准确性"],
                ),
                ProcedureNode(
                    id="proc-1",
                    program_no=2,
                    category="备选",
                    status="pending",
                    assertions=["完整性"],
                ),
            ],
            workpapers=[
                LinkedWorkpaper(
                    wp_code="D2A",
                    wp_name="应收账款实质性程序表",
                    status="exists",
                    exists=True,
                )
            ],
            edges=[
                FlowEdge(
                    from_id="assertion-existence",
                    to_id="risk-0",
                    type="objective-risk",
                ),
                FlowEdge(
                    from_id="risk-0",
                    to_id="proc-0",
                    type="risk-procedure",
                ),
                FlowEdge(
                    from_id="proc-0",
                    to_id="wp-D2A",
                    type="procedure-workpaper",
                ),
            ],
        )

        assert len(resp.risks) == 1
        assert resp.risks[0].level == "significant"
        assert len(resp.procedures) == 2
        assert resp.procedures[0].status == "completed"
        assert resp.procedures[1].status == "pending"
        assert len(resp.workpapers) == 1
        assert resp.workpapers[0].exists is True
        assert len(resp.edges) == 3
