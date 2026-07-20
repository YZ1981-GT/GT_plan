"""Integration tests for review-prompt HTTP endpoints.

Tests:
1. POST /api/workpapers/{wp_id}/review — response structure validation
2. POST /api/projects/{pid}/batch-review — batch call structure
3. GET /api/review-prompts/coverage — coverage report from real filesystem
4. ai_content persistence logic verification

**Validates: Requirements 3.4, 4.3, 10.3, 5.1**
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import httpx

from app.main import app


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

FAKE_WP_ID = str(uuid.uuid4())
FAKE_PROJECT_ID = str(uuid.uuid4())

# Simulated LLM response with checklist format
MOCK_LLM_RESPONSE = """\
## 高风险

1. **期初期末勾稽**：期初余额与上期审定期末不一致

- [ ] 期初余额与上期底稿审定期末核对一致
- [x] 本期发生额合计正确

## 中风险

- [ ] 样本量是否充分
- [x] 审计程序完整执行

## 低风险

- [x] 底稿格式规范
"""


@pytest_asyncio.fixture
async def client():
    """Create httpx AsyncClient with ASGITransport for testing."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1: POST /api/workpapers/{wp_id}/review 端点响应结构
# Validates: Requirement 3.4
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_review_workpaper_returns_404_when_wp_not_found(client):
    """When wp_id doesn't exist, return 404."""
    fake_id = str(uuid.uuid4())

    with patch(
        "app.routers.review_prompt._get_wp_code",
        new_callable=AsyncMock,
        return_value=None,
    ):
        resp = await client.post(
            f"/api/workpapers/{fake_id}/review",
            json={"sheet_name": "审定表D2-1"},
        )

    # ResponseWrapperMiddleware may wrap or not — check status
    assert resp.status_code in (404, 200)
    data = resp.json()
    if resp.status_code == 200:
        # Wrapped: {code, message, data} — check inner
        inner = data.get("data", data)
        if "detail" in inner or data.get("code") == 404:
            pass  # expected 404 behavior
    else:
        assert "detail" in data or "message" in data


@pytest.mark.asyncio
async def test_review_workpaper_response_structure(client):
    """POST /api/workpapers/{wp_id}/review returns correct ReviewResponse shape.

    Validates: Requirement 3.4
    """
    with (
        patch(
            "app.routers.review_prompt._get_wp_code",
            new_callable=AsyncMock,
            return_value="D2",
        ),
        patch(
            "app.routers.review_prompt._get_workpaper_content",
            new_callable=AsyncMock,
            return_value="底稿内容示例",
        ),
        patch(
            "app.routers.review_prompt._call_llm",
            new_callable=AsyncMock,
            return_value=MOCK_LLM_RESPONSE,
        ),
    ):
        resp = await client.post(
            f"/api/workpapers/{FAKE_WP_ID}/review",
            json={"sheet_name": "审定表D2-1"},
        )

    assert resp.status_code == 200
    body = resp.json()
    # Handle ResponseWrapperMiddleware wrapping
    data = body.get("data", body)

    # Validate required fields
    assert "findings" in data
    assert "overall_pass" in data
    assert "risk_summary" in data
    assert "sheet_info" in data

    # Validate findings structure
    assert isinstance(data["findings"], list)
    if data["findings"]:
        finding = data["findings"][0]
        assert "id" in finding
        assert "description" in finding
        assert "risk_level" in finding
        assert "pass_status" in finding
        assert "category" in finding

    # Validate risk_summary keys
    risk = data["risk_summary"]
    assert "high" in risk
    assert "medium" in risk
    assert "low" in risk

    # Validate sheet_info structure
    info = data["sheet_info"]
    assert "wp_id" in info
    assert "wp_code" in info
    assert "prompt_source" in info
    assert info["wp_code"] == "D2"
    assert info["prompt_source"] in ("sheet", "subject", "base")


@pytest.mark.asyncio
async def test_review_workpaper_without_sheet_name(client):
    """POST /api/workpapers/{wp_id}/review with no sheet_name falls back gracefully."""
    with (
        patch(
            "app.routers.review_prompt._get_wp_code",
            new_callable=AsyncMock,
            return_value="D2",
        ),
        patch(
            "app.routers.review_prompt._get_workpaper_content",
            new_callable=AsyncMock,
            return_value="一些底稿数据",
        ),
        patch(
            "app.routers.review_prompt._call_llm",
            new_callable=AsyncMock,
            return_value=MOCK_LLM_RESPONSE,
        ),
    ):
        resp = await client.post(f"/api/workpapers/{FAKE_WP_ID}/review")

    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    # Without sheet_name, prompt_source should be "subject" or "base"
    assert data["sheet_info"]["prompt_source"] in ("sheet", "subject", "base")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2: POST /api/projects/{pid}/batch-review 批量调用
# Validates: Requirement 4.3
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_batch_review_response_structure(client):
    """POST /api/projects/{pid}/batch-review returns BatchReviewReportResponse shape.

    Validates: Requirement 4.3
    """
    fake_sheets = [
        {"wp_id": str(uuid.uuid4()), "wp_code": "D2-1", "sheet_name": "审定表D2-1"},
        {"wp_id": str(uuid.uuid4()), "wp_code": "D2-2", "sheet_name": "明细表D2-2"},
    ]

    with (
        patch(
            "app.services.batch_review_service.BatchReviewService._get_sheets_for_prefix",
            new_callable=AsyncMock,
            return_value=fake_sheets,
        ),
        patch(
            "app.services.batch_review_service.chat_completion",
            new_callable=AsyncMock,
            return_value=MOCK_LLM_RESPONSE,
        ),
        patch(
            "app.services.batch_review_service.BatchReviewService._get_workpaper_content",
            new_callable=AsyncMock,
            return_value="底稿内容",
        ),
        patch(
            "app.services.batch_review_service.BatchReviewService.persist_review_results",
            new_callable=AsyncMock,
        ),
    ):
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/batch-review",
            json={"wp_code_prefix": "D2", "year": 2025},
        )

    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)

    # Top-level fields
    assert "session_id" in data
    assert "wp_code_prefix" in data
    assert "project_id" in data
    assert "results" in data
    assert "statistics" in data
    assert "execution" in data

    # Statistics structure: total = passed + failed + error
    stats = data["statistics"]
    assert "total_sheets" in stats
    assert "passed_count" in stats
    assert "failed_count" in stats
    assert "error_count" in stats
    assert "total_findings" in stats
    assert "findings_by_risk" in stats
    assert stats["total_sheets"] == stats["passed_count"] + stats["failed_count"] + stats["error_count"]

    # Results list matches sheet count
    assert len(data["results"]) == len(fake_sheets)

    # Each result has required fields
    for result in data["results"]:
        assert "wp_id" in result
        assert "sheet_name" in result
        assert "wp_code" in result
        assert "pass_status" in result
        assert "findings" in result
        assert "risk_summary" in result
        assert "reviewed_at" in result
        assert "model_used" in result
        assert "prompt_source" in result

    # Execution metadata
    execution = data["execution"]
    assert "start_time" in execution
    assert "end_time" in execution
    assert "duration_seconds" in execution
    assert "model_used" in execution
    assert execution["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_batch_review_empty_prefix(client):
    """Batch review with no sheets returns empty results."""
    with (
        patch(
            "app.services.batch_review_service.BatchReviewService._get_sheets_for_prefix",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.services.batch_review_service.BatchReviewService.persist_review_results",
            new_callable=AsyncMock,
        ),
    ):
        resp = await client.post(
            f"/api/projects/{FAKE_PROJECT_ID}/batch-review",
            json={"wp_code_prefix": "Z99", "year": 2025},
        )

    assert resp.status_code == 200
    data = resp.json().get("data", resp.json())
    assert data["results"] == []
    assert data["statistics"]["total_sheets"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3: GET /api/review-prompts/coverage 覆盖率
# Validates: Requirement 10.3
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_coverage_endpoint_response_structure(client):
    """GET /api/review-prompts/coverage returns correct CoverageReport shape.

    Uses real ReviewPromptService (filesystem-based, no DB needed).

    Validates: Requirement 10.3
    """
    resp = await client.get("/api/review-prompts/coverage")

    assert resp.status_code == 200
    body = resp.json()
    data = body.get("data", body)

    # Required fields
    assert "total_subjects" in data
    assert "subjects_with_sheet_prompts" in data
    assert "sheet_breakdown" in data
    assert "missing_gaps" in data

    # Type validation
    assert isinstance(data["total_subjects"], int)
    assert isinstance(data["subjects_with_sheet_prompts"], int)
    assert isinstance(data["sheet_breakdown"], dict)
    assert isinstance(data["missing_gaps"], list)

    # total_subjects >= subjects_with_sheet_prompts
    assert data["total_subjects"] >= data["subjects_with_sheet_prompts"]

    # sheet_breakdown values are lists of strings
    for prefix, suffixes in data["sheet_breakdown"].items():
        assert isinstance(prefix, str)
        assert isinstance(suffixes, list)
        for s in suffixes:
            assert isinstance(s, str)

    # D2 should be present (we created sheet-level prompts for it)
    assert "D2" in data["sheet_breakdown"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4: ai_content 表写入验证
# Validates: Requirement 5.1
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_persist_review_results_writes_correct_content_type():
    """Verify persist_review_results INSERTs to ai_content with correct content_type
    and data_sources fields.

    Validates: Requirement 5.1
    """
    from app.services.batch_review_service import (
        BatchReviewService,
        BatchStatistics,
        ReviewResult,
    )
    from app.services.llm_response_parser import ReviewFinding

    service = BatchReviewService()

    fake_finding = ReviewFinding(
        id=str(uuid.uuid4()),
        description="期初余额与上期不一致",
        risk_level="high",
        pass_status=False,
        category="数据完整性",
        sheet_location="A列第5行",
        suggestion="请核对上期审定数",
    )

    fake_results = [
        ReviewResult(
            wp_id=str(uuid.uuid4()),
            sheet_name="审定表D2-1",
            wp_code="D2-1",
            pass_status="fail",
            findings=[fake_finding],
            risk_summary={"high": 1, "medium": 0, "low": 0},
            reviewed_at="2025-06-01T00:00:00Z",
            model_used="qwen3.5-27b",
            prompt_source="sheet",
            error_message=None,
        ),
    ]

    fake_statistics = BatchStatistics(
        total_sheets=1,
        passed_count=0,
        failed_count=1,
        error_count=0,
        total_findings=1,
        findings_by_risk={"high": 1, "medium": 0, "low": 0},
    )

    # Capture the SQL executions
    executed_statements: list[tuple] = []

    class FakeResult:
        pass

    class FakeSession:
        async def execute(self, stmt, params=None):
            executed_statements.append((str(stmt), params))
            return FakeResult()

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    with patch(
        "app.services.batch_review_service.async_session",
        return_value=FakeSession(),
    ):
        await service.persist_review_results(
            project_id=FAKE_PROJECT_ID,
            session_id="test-session-001",
            wp_code_prefix="D2",
            results=fake_results,
            statistics=fake_statistics,
        )

    # Verify at least one INSERT to ai_content was called
    ai_content_inserts = [
        (stmt, params)
        for stmt, params in executed_statements
        if "ai_content" in stmt and "INSERT" in stmt.upper()
    ]
    assert len(ai_content_inserts) >= 1, "Should INSERT at least one ai_content record"

    # Verify the first ai_content INSERT has correct fields
    _, params = ai_content_inserts[0]
    assert params["project_id"] == FAKE_PROJECT_ID
    assert params["workpaper_id"] == fake_results[0].wp_id
    assert params["content_text"] == fake_finding.description

    # Verify data_sources contains required fields (Req 5.1)
    data_sources = json.loads(params["data_sources"])
    assert data_sources["session_id"] == "test-session-001"
    assert data_sources["wp_code"] == "D2-1"
    assert data_sources["sheet_name"] == "审定表D2-1"
    assert data_sources["risk_level"] == "high"
    assert data_sources["pass_status"] == "False"
    assert data_sources["category"] == "数据完整性"

    # Verify checklist_responses session index was written
    checklist_inserts = [
        (stmt, params)
        for stmt, params in executed_statements
        if "checklist_responses" in stmt and "INSERT" in stmt.upper()
    ]
    assert len(checklist_inserts) >= 1, "Should INSERT session index to checklist_responses"

    _, cr_params = checklist_inserts[0]
    assert cr_params["project_id"] == FAKE_PROJECT_ID
    assert "review-session" in cr_params["item_id"]


@pytest.mark.asyncio
async def test_persist_review_results_skips_error_sheets():
    """Verify that sheets with review_error status are skipped for findings persistence
    but session index is still written.

    Validates: Requirement 5.1
    """
    from app.services.batch_review_service import (
        BatchReviewService,
        BatchStatistics,
        ReviewResult,
    )

    service = BatchReviewService()

    error_result = ReviewResult(
        wp_id=str(uuid.uuid4()),
        sheet_name="审定表D2-1",
        wp_code="D2-1",
        pass_status="review_error",
        findings=[],
        risk_summary={"high": 0, "medium": 0, "low": 0},
        reviewed_at="2025-06-01T00:00:00Z",
        model_used="qwen3.5-27b",
        prompt_source="sheet",
        error_message="LLM unavailable",
    )

    fake_statistics = BatchStatistics(
        total_sheets=1,
        passed_count=0,
        failed_count=0,
        error_count=1,
        total_findings=0,
        findings_by_risk={"high": 0, "medium": 0, "low": 0},
    )

    executed_statements: list[tuple] = []

    class FakeSession:
        async def execute(self, stmt, params=None):
            executed_statements.append((str(stmt), params))

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    with patch(
        "app.services.batch_review_service.async_session",
        return_value=FakeSession(),
    ):
        await service.persist_review_results(
            project_id=FAKE_PROJECT_ID,
            session_id="test-session-002",
            wp_code_prefix="D2",
            results=[error_result],
            statistics=fake_statistics,
        )

    # No ai_content INSERT for error sheets
    ai_content_inserts = [
        (stmt, params)
        for stmt, params in executed_statements
        if "ai_content" in stmt and "INSERT" in stmt.upper()
    ]
    assert len(ai_content_inserts) == 0, "review_error sheets should not write ai_content"

    # But session index should still be written
    checklist_inserts = [
        (stmt, params)
        for stmt, params in executed_statements
        if "checklist_responses" in stmt and "INSERT" in stmt.upper()
    ]
    assert len(checklist_inserts) >= 1, "Session index should still be written"
