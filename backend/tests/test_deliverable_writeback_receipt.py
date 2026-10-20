"""报告正文回填回执分组 + 路由提交 — deliverable-writeback-and-online-edit-integrity Task 18

覆盖（AC-3.2）：
- `_group_writeback_receipt` 把五桶归并为「已回填 / 已拒绝 / 未回填」三组，
  拒绝原因只认后端字段 ``rejection_reason``（修「前端读 item.reason 恒空」历史缺陷）；
- `未回填` = skipped（锚点丢失）+ failed（写入 0 行 / 派生段落）；
- 原始五桶键原样保留（兼容既有前端 WritebackResultPanel）；
- 路由 `/writeback` 成功后调用 `db.commit()`（修 get_db 不自动提交）；
- 反向自检（变异）：若路由不提交，提交断言必打红 —— 证明该断言非空转。

端点级用例复用 `test_deliverable_lineage_endpoints.py` 同款 mock（admin 绕过项目成员校验、
mock_db 为 AsyncMock），patch 掉回填服务 / section-states / audit_logger，只验路由编排。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user, get_db
from app.main import app
from app.models.core import User
from app.routers.deliverable_lineage import _group_writeback_receipt


# ─── 单元：_group_writeback_receipt ──────────────────────────────────────────


def _sample_result() -> dict:
    """一份五桶齐全的 WritebackResult（dict 形态，与 TypedDict 运行时一致）。"""
    return {
        "written": ["opinion", "basis"],
        "rejected": [
            {
                "kind": "title",
                "section_code": "signature",
                "content": "签章段",
                "rejection_reason": "章节标题由系统生成，不可从出品物回填",
            }
        ],
        "conflicts": [],
        "skipped": ["kam"],
        "failed": [
            {"section_code": "mgmt_responsibility", "reason": "该章节属派生/模板固定段落"}
        ],
        "trace_id": "trace-1",
    }


def test_receipt_three_groups_with_rejection_reason():
    """三组齐全：已回填 / 已拒绝（带 rejection_reason）/ 未回填（skipped+failed）。"""
    grouped = _group_writeback_receipt(_sample_result())
    receipt = grouped["receipt"]

    assert receipt["filled"] == ["opinion", "basis"]

    assert receipt["rejected"] == [
        {
            "section_code": "signature",
            "rejection_reason": "章节标题由系统生成，不可从出品物回填",
        }
    ]
    # 拒绝原因只认后端 rejection_reason —— 不得为空（历史缺陷：前端读 item.reason 恒空）
    assert receipt["rejected"][0]["rejection_reason"]

    # 未回填 = skipped（锚点丢失）+ failed（0 行 / 派生）
    not_filled_codes = {item["section_code"] for item in receipt["not_filled"]}
    assert not_filled_codes == {"kam", "mgmt_responsibility"}
    for item in receipt["not_filled"]:
        assert item["reason"], "未回填项必须带可读原因"

    assert receipt["counts"] == {"filled": 2, "rejected": 1, "not_filled": 2}


def test_receipt_preserves_raw_buckets():
    """原始五桶键原样保留，兼容既有前端。"""
    result = _sample_result()
    grouped = _group_writeback_receipt(result)
    for key in ("written", "rejected", "conflicts", "skipped", "failed", "trace_id"):
        assert grouped[key] == result[key]


def test_receipt_empty_result():
    """全空回执：三组皆空、计数全 0，不抛。"""
    grouped = _group_writeback_receipt(
        {
            "written": [],
            "rejected": [],
            "conflicts": [],
            "skipped": [],
            "failed": [],
            "trace_id": None,
        }
    )
    assert grouped["receipt"]["counts"] == {"filled": 0, "rejected": 0, "not_filled": 0}
    assert grouped["receipt"]["filled"] == []
    assert grouped["receipt"]["rejected"] == []
    assert grouped["receipt"]["not_filled"] == []


# ─── 端点：/writeback 提交 + 回执 ────────────────────────────────────────────


@pytest.fixture
def project_id():
    return uuid4()


@pytest.fixture
def task_id():
    return uuid4()


@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.role = MagicMock()
    user.role.value = "admin"  # admin 绕过项目成员校验
    user.username = "test_admin"
    return user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    mock_bind = MagicMock()
    mock_bind.dialect = MagicMock()
    mock_bind.dialect.name = "postgresql"
    db.get_bind = MagicMock(return_value=mock_bind)
    db.execute = AsyncMock(return_value=MagicMock())
    db.commit = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def override_deps(mock_user, mock_db):
    async def _override_get_db():
        return mock_db

    async def _override_get_current_user():
        return mock_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    # 回填走交付中心 _guard_action（admin 跳过成员校验但仍查 EQCR 委派）+ 交付件归属校验：mock_db 答不了这两类查询，
    # 本文件只验路由编排（提交 / 回执 / 能力门控），鉴权与归属见 test_deliverable_generation_membership_auth.py
    with (
        patch("app.routers.deliverable._is_project_eqcr", new=AsyncMock(return_value=False)),
        patch("app.routers.deliverable_lineage._ensure_task_in_project", new=AsyncMock(return_value=None)),
    ):
        yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_writeback_endpoint_commits_and_groups(project_id, task_id, mock_db):
    """成功回填 ⇒ 路由提交 + 响应带三组回执（含 rejection_reason）。"""
    sample = _sample_result()

    with (
        patch(
            "app.routers.deliverable_lineage._check_terminal_state",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.routers.deliverable_lineage._require_capability",
            new=AsyncMock(return_value="audit_report"),
        ),
        patch(
            "app.services.deliverable_section_state_service."
            "DeliverableSectionStateService.get_section_states",
            new=AsyncMock(return_value=[{"section_code": "opinion"}]),
        ),
        patch(
            "app.services.deliverable_writeback_service."
            "DeliverableWritebackService.writeback",
            new=AsyncMock(return_value=sample),
        ),
        patch(
            "app.routers.deliverable_lineage.audit_logger.log_action",
            new=AsyncMock(return_value=None),
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{project_id}/deliverables/{task_id}/writeback",
                json={"year": 2025},
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 响应信封可能被 ResponseWrapperMiddleware 包成 {code,message,data}
    data = body.get("data", body) if isinstance(body, dict) else body

    assert "receipt" in data
    assert data["receipt"]["filled"] == ["opinion", "basis"]
    assert data["receipt"]["rejected"][0]["rejection_reason"]
    assert data["receipt"]["counts"]["not_filled"] == 2
    # 原始桶仍在
    assert data["written"] == ["opinion", "basis"]

    # 🔴 路由必须提交（修 get_db 不自动提交）—— 变异：删掉 await db.commit() 本断言必打红
    mock_db.commit.assert_awaited_once()


# ─── 端点：/writeback 能力门控（附注已下线 → 400，US-2 / AC-2.1） ──────────────
#
# 与上面的用例不同，这里**不** patch `_require_capability` —— 让真实能力门控跑起来，
# 只把 `_get_doc_type` 打桩为具体 doc_type，验证端点确实对附注返回 400、对报告正文放行。
# 这补上 design §4.5「/writeback 对附注返回 400」的端点级断言（既有用例全把门控 patch 掉了，
# 从未真实走过这条分支）。


@pytest.mark.asyncio
async def test_writeback_endpoint_rejects_disclosure_notes_400(project_id, task_id):
    """附注交付件 POST /writeback ⇒ 400，文案指向「回底稿改并同步」（US-2 AC-2.1）。"""
    with (
        patch(
            "app.routers.deliverable_lineage._check_terminal_state",
            new=AsyncMock(return_value=None),
        ),
        # 真实能力门控（不 patch _require_capability）；只把 doc_type 读成附注
        patch(
            "app.routers.deliverable_lineage._get_doc_type",
            new=AsyncMock(return_value="disclosure_notes"),
        ),
        # 若门控失效、放行到下游，这里会被调用 ⇒ 用它反证门控确实短路在前面
        patch(
            "app.services.deliverable_section_state_service."
            "DeliverableSectionStateService.get_section_states",
            new=AsyncMock(return_value=[]),
        ) as spy_sections,
        patch(
            "app.services.deliverable_writeback_service."
            "DeliverableWritebackService.writeback",
            new=AsyncMock(return_value=_sample_result()),
        ) as spy_writeback,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{project_id}/deliverables/{task_id}/writeback",
                json={"year": 2025},
            )

    assert resp.status_code == 400, resp.text
    body = resp.json()
    detail = (body.get("detail") or body.get("message") or "") if isinstance(body, dict) else ""
    assert "底稿" in detail, f"附注回填拒绝文案未指向底稿: {detail!r}"
    # 🔴 门控必须短路在任何写入之前 —— service / section-states 一次都不能调
    spy_writeback.assert_not_awaited()
    spy_sections.assert_not_awaited()


@pytest.mark.asyncio
async def test_writeback_endpoint_allows_audit_report_through_gate(
    project_id, task_id, mock_db
):
    """反向控制：报告正文（audit_report）能通过真实能力门控、照常回填 + 提交。

    与上一条同样**不** patch `_require_capability`——证明「附注 400」不是因为门控恒拒，
    而是能力矩阵真的区分了 doc_type（否则这条会连带打红）。
    """
    sample = _sample_result()
    with (
        patch(
            "app.routers.deliverable_lineage._check_terminal_state",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.routers.deliverable_lineage._get_doc_type",
            new=AsyncMock(return_value="audit_report"),
        ),
        patch(
            "app.services.deliverable_section_state_service."
            "DeliverableSectionStateService.get_section_states",
            new=AsyncMock(return_value=[{"section_code": "opinion"}]),
        ),
        patch(
            "app.services.deliverable_writeback_service."
            "DeliverableWritebackService.writeback",
            new=AsyncMock(return_value=sample),
        ) as spy_writeback,
        patch(
            "app.routers.deliverable_lineage.audit_logger.log_action",
            new=AsyncMock(return_value=None),
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/projects/{project_id}/deliverables/{task_id}/writeback",
                json={"year": 2025},
            )

    assert resp.status_code == 200, resp.text
    spy_writeback.assert_awaited_once()
    mock_db.commit.assert_awaited_once()
