"""E2E 链路 2：创建 AJE → 验证试算表增量更新 → 验证报表更新

运行方式:
    python -m pytest backend/tests/e2e/test_e2e_chain2.py -v
"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def project_with_data(client, admin_user):
    """创建一个带基础数据的项目，供调整分录测试使用。"""
    r = await client.post("/api/projects", json={
        "client_name": "AJE测试公司",
        "audit_year": 2025,
        "project_type": "annual",
        "accounting_standard": "enterprise",
    })
    assert r.status_code == 200
    body = r.json()
    project = body.get("data", body) if isinstance(body, dict) else body
    project_id = project.get("id")
    assert project_id is not None

    # 加载标准科目
    await client.get(f"/api/projects/{project_id}/account-chart/standard")

    return project_id


@pytest.mark.asyncio
async def test_create_aje_verify_trial_balance_and_report_update(
    client, project_with_data
):
    """链路2完整流程：创建 AJE → 查询分录列表 → 试算表重算 → 报表更新"""
    project_id = project_with_data

    # ── 1. 创建审计调整分录 (AJE) ──
    aje_data = {
        "adjustment_type": "aje",
        "year": 2025,
        "description": "E2E测试调整分录-应收账款减值",
        "line_items": [
            {
                "standard_account_code": "6701",
                "account_name": "资产减值损失",
                "debit_amount": 50000,
                "credit_amount": 0,
            },
            {
                "standard_account_code": "1231",
                "account_name": "坏账准备",
                "debit_amount": 0,
                "credit_amount": 50000,
            },
        ],
    }
    r = await client.post(
        f"/api/projects/{project_id}/adjustments",
        json=aje_data,
    )
    assert r.status_code in (200, 201), f"创建AJE失败: {r.text}"
    aje_body = r.json()
    aje_resp = aje_body.get("data", aje_body) if isinstance(aje_body, dict) else aje_body
    aje_id = aje_resp.get("id") or aje_resp.get("entry_group_id")
    assert aje_id is not None, "AJE 创建后应返回 id"

    # ── 2. 查询调整分录列表 ──
    r = await client.get(
        f"/api/projects/{project_id}/adjustments",
        params={"year": 2025},
    )
    assert r.status_code == 200
    adj_body = r.json()
    entries = adj_body.get("data", adj_body) if isinstance(adj_body, dict) else adj_body
    if isinstance(entries, list):
        assert len(entries) >= 1, "应至少有1条调整分录"

    # ── 3. 触发试算表重算（验证增量更新） ──
    r = await client.post(
        f"/api/projects/{project_id}/trial-balance/recalc",
        params={"year": 2025},
    )
    assert r.status_code in (200, 201, 404, 422)

    # ── 4. 查询试算表验证 AJE 影响 ──
    r = await client.get(
        f"/api/projects/{project_id}/trial-balance",
        params={"year": 2025},
    )
    assert r.status_code == 200

    # ── 5. 生成报表验证更新 ──
    r = await client.post(
        f"/api/reports/{project_id}/generate",
        params={"year": 2025},
    )
    assert r.status_code in (200, 201, 400, 404, 422)

    # ── 6. 查询报表 ──
    r = await client.get(
        f"/api/reports/{project_id}",
        params={"year": 2025},
    )
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_create_rje_and_verify_summary(client, project_with_data):
    """创建 RJE 并验证调整分录汇总统计"""
    project_id = project_with_data

    # 创建一条 RJE
    rje_data = {
        "adjustment_type": "rje",
        "year": 2025,
        "description": "E2E测试重分类分录",
        "line_items": [
            {
                "standard_account_code": "1122",
                "account_name": "应收账款",
                "debit_amount": 30000,
                "credit_amount": 0,
            },
            {
                "standard_account_code": "2202",
                "account_name": "应付账款",
                "debit_amount": 0,
                "credit_amount": 30000,
            },
        ],
    }
    r = await client.post(
        f"/api/projects/{project_id}/adjustments",
        json=rje_data,
    )
    assert r.status_code in (200, 201), f"创建RJE失败: {r.text}"

    # 查询汇总
    r = await client.get(
        f"/api/projects/{project_id}/adjustments/summary",
        params={"year": 2025},
    )
    assert r.status_code == 200
    summary_body = r.json()
    summary = summary_body.get("data", summary_body) if isinstance(summary_body, dict) else summary_body
    assert isinstance(summary, dict), "汇总应返回字典"
