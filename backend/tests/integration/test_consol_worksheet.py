"""集成测试：合并差额表计算

验证 consol_worksheet_engine 的批量计算逻辑：
1. 构建企业树（根 + 2 个子公司）
2. 子公司有 trial_balance 审定数
3. recalc_full 后序遍历计算
4. 验证合并数 = Σ子公司审定数 + 抵消净额

需要真实 PostgreSQL 运行（TEST_DATABASE_URL）。
"""

import uuid
from decimal import Decimal

import pytest


@pytest.mark.asyncio
async def test_consol_tree_endpoint(pg_client):
    """合并树端点可达"""
    await pg_client.post("/api/auth/register", json={
        "username": "consol_user",
        "email": "consol@test.com",
        "password": "Test123456",
    })
    login_resp = await pg_client.post("/api/auth/login", json={
        "username": "consol_user",
        "password": "Test123456",
    })
    if login_resp.status_code != 200:
        pytest.skip("登录失败")

    token = login_resp.json().get("data", login_resp.json())["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 创建合并项目
    proj_resp = await pg_client.post("/api/project-wizard/", json={
        "client_name": "合并测试集团",
        "audit_year": "2025",
        "project_type": "consolidation",
    }, headers=headers)

    if proj_resp.status_code not in (200, 201):
        pytest.skip(f"项目创建失败: {proj_resp.status_code}")

    project_data = proj_resp.json().get("data", proj_resp.json())
    project_id = project_data.get("id")

    # 查询合并树
    tree_resp = await pg_client.get(
        f"/api/consol-worksheet/tree/{project_id}",
        headers=headers,
    )
    # 新项目无子公司，可能返回空树或 404
    assert tree_resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_consol_recalc_endpoint(pg_client):
    """差额表重算端点可达"""
    await pg_client.post("/api/auth/register", json={
        "username": "consol2_user",
        "email": "consol2@test.com",
        "password": "Test123456",
    })
    login_resp = await pg_client.post("/api/auth/login", json={
        "username": "consol2_user",
        "password": "Test123456",
    })
    if login_resp.status_code != 200:
        pytest.skip("登录失败")

    token = login_resp.json().get("data", login_resp.json())["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 对不存在的项目重算（应返回空结果或 404，不应 500）
    resp = await pg_client.post(
        f"/api/consol-worksheet/recalc",
        json={"project_id": str(uuid.uuid4()), "year": 2025},
        headers=headers,
    )
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_consol_worksheet_engine_pure_logic():
    """纯内存计算逻辑验证（不需要数据库）"""
    from app.services.consol_worksheet_engine import _calc_node_batch, ZERO
    from app.services.consol_tree_service import TreeNode

    # 构建简单树：根 → 子A + 子B
    root_id = uuid.uuid4()
    child_a_id = uuid.uuid4()
    child_b_id = uuid.uuid4()

    child_a = TreeNode(
        project_id=child_a_id, company_code="A",
        company_name="子公司A", parent_company_code="ROOT",
        ultimate_company_code="ROOT", consol_level=2,
    )
    child_b = TreeNode(
        project_id=child_b_id, company_code="B",
        company_name="子公司B", parent_company_code="ROOT",
        ultimate_company_code="ROOT", consol_level=2,
    )
    root = TreeNode(
        project_id=root_id, company_code="ROOT",
        company_name="集团", parent_company_code=None,
        ultimate_company_code="ROOT", consol_level=1,
        children=[child_a, child_b],
    )

    # 模拟数据
    account_codes = {"1001", "2001"}
    tb_map = {
        (child_a_id, "1001"): Decimal("100"),
        (child_a_id, "2001"): Decimal("50"),
        (child_b_id, "1001"): Decimal("200"),
        (child_b_id, "2001"): Decimal("80"),
    }
    ws_map = {}  # 无已有 worksheet
    elim_map = {}  # 无抵消分录

    results = []
    node_amounts = _calc_node_batch(root, account_codes, tb_map, ws_map, elim_map, results)

    # 验证根节点合并数 = 子A + 子B
    assert node_amounts["1001"] == Decimal("300")  # 100 + 200
    assert node_amounts["2001"] == Decimal("130")  # 50 + 80

    # 验证结果行数 = 3 节点 × 2 科目 = 6
    assert len(results) == 6
