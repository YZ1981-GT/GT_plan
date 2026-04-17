"""Phase 10 Task 2.1-2.2: 连续审计测试"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


class TestContinuousAuditService:
    """ContinuousAuditService 单元测试"""

    @pytest.mark.asyncio
    async def test_create_next_year_project_not_found(self):
        from app.services.continuous_audit_service import ContinuousAuditService
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        svc = ContinuousAuditService()
        with pytest.raises(ValueError, match="上年项目不存在"):
            await svc.create_next_year(db, uuid4())

    @pytest.mark.asyncio
    async def test_create_next_year_copies_basic_info(self):
        from app.services.continuous_audit_service import ContinuousAuditService
        from app.models.core import Project
        from app.models.base import ProjectStatus

        prior = MagicMock(spec=Project)
        prior.id = uuid4()
        prior.client_name = "测试公司"
        prior.project_type = "annual"
        prior.status = ProjectStatus.archived
        prior.manager_id = uuid4()
        prior.partner_id = uuid4()
        prior.company_code = "TC001"
        prior.template_type = "soe"
        prior.report_scope = "standalone"
        prior.parent_company_name = None
        prior.parent_company_code = None
        prior.ultimate_company_name = None
        prior.ultimate_company_code = None
        prior.parent_project_id = None
        prior.consol_level = 1
        prior.wizard_state = {
            "steps": {
                "basic_info": {
                    "data": {"audit_year": 2025, "client_name": "测试公司"}
                }
            }
        }

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: get prior project
                mock_result.scalar_one_or_none.return_value = prior
            elif call_count == 2:
                # Second call: UPDATE prior_year_project_id
                mock_result.rowcount = 1
            else:
                # Subsequent calls: empty results for mappings/team/tb/adj/mis
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        db.execute = mock_execute
        db.add = MagicMock()
        db.flush = AsyncMock()

        svc = ContinuousAuditService()
        result = await svc.create_next_year(db, prior.id)

        assert result["new_year"] == 2026
        assert result["prior_year_project_id"] == str(prior.id)
        assert "new_project_id" in result
        assert "items_copied" in result

    def test_schemas_import(self):
        from app.models.phase10_schemas import (
            CreateNextYearRequest, CreateNextYearResponse,
        )
        req = CreateNextYearRequest()
        assert req.copy_team is True
        assert req.copy_mapping is True

    def test_router_import(self):
        from app.routers.continuous_audit import router
        routes = [r.path for r in router.routes]
        assert "/create-next-year" in routes or any("create-next-year" in r for r in routes)
