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
    """纯内存计算逻辑验证（不需要数据库）。

    口径变更（spec consol-tree-three-code-autobuild 任务 7.6）：旧版 ``_calc_node_batch`` 已删除，
    计算口径收敛到 ``consol_calc_basis``；树改由三码推导（合并 / 合并差额 / 母公司三节点）。
    """
    from app.services.consol_calc_basis import TbRow, build_calc_basis, worksheet_rows
    from app.services.consol_group_tree import ProjectRecord, derive_group_tree

    def rec(code, scope, parent=None):
        return ProjectRecord(
            id=uuid.uuid4(), company_code=code, client_name=f"企业{code}", report_scope=scope,
            audit_year=2025, parent_company_code=parent, relation_to_parent="subsidiary" if parent else None,
        )

    root = rec("ROOT", "consolidated")
    a, b = rec("A", "standalone", "ROOT"), rec("B", "standalone", "ROOT")
    tree = derive_group_tree([root, a, b], root, 2025).root

    tb = [
        TbRow(a.id, "1001", "货币资金", None, Decimal("100")),
        TbRow(a.id, "2001", "短期借款", None, Decimal("50")),
        TbRow(b.id, "1001", "货币资金", None, Decimal("200")),
        TbRow(b.id, "2001", "短期借款", None, Decimal("80")),
    ]
    rows = worksheet_rows(build_calc_basis(tree, 2025, tb, []))
    by_key = {(k, acct): v for k, acct, v in rows}

    # 根节点合并数 = 子A + 子B（母公司没有单户项目 ⇒ 母公司数据节点计 0）
    assert by_key[("ROOT:consol", "1001")].consolidated_amount == Decimal("300")
    assert by_key[("ROOT:consol", "2001")].consolidated_amount == Decimal("130")
    assert by_key[("ROOT:parent", "1001")].consolidated_amount == Decimal("0")

    # 结果行数 = 5 节点（合并、合并差额、母公司、A、B）× 2 科目
    assert len(rows) == 10
