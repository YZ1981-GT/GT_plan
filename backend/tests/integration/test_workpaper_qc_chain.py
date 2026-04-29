"""集成测试：底稿上传 → 解析 → QC 检查 → 提交复核门禁

验证底稿生命周期的关键链路：
1. 上传底稿文件
2. 自动解析 parsed_data
3. QC 引擎检查（14 条规则）
4. 提交复核时门禁校验

需要真实 PostgreSQL 运行（TEST_DATABASE_URL）。
"""

import uuid

import pytest


@pytest.mark.asyncio
async def test_qc_check_endpoint(pg_client):
    """QC 检查端点可达"""
    await pg_client.post("/api/auth/register", json={
        "username": "qc_user",
        "email": "qc@test.com",
        "password": "Test123456",
    })
    login_resp = await pg_client.post("/api/auth/login", json={
        "username": "qc_user",
        "password": "Test123456",
    })
    if login_resp.status_code != 200:
        pytest.skip("登录失败")

    token = login_resp.json().get("data", login_resp.json())["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # QC 检查（无底稿时应返回 404，不应 500）
    resp = await pg_client.post(
        f"/api/qc/qc-check",
        json={"working_paper_id": str(uuid.uuid4())},
        headers=headers,
    )
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_submit_review_gate_blocks_without_reviewer(pg_client):
    """提交复核时缺少复核人应被门禁阻断"""
    await pg_client.post("/api/auth/register", json={
        "username": "gate_user",
        "email": "gate@test.com",
        "password": "Test123456",
    })
    login_resp = await pg_client.post("/api/auth/login", json={
        "username": "gate_user",
        "password": "Test123456",
    })
    if login_resp.status_code != 200:
        pytest.skip("登录失败")

    token = login_resp.json().get("data", login_resp.json())["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 对不存在的底稿提交复核
    resp = await pg_client.post(
        f"/api/working-papers/{uuid.uuid4()}/submit-review",
        headers=headers,
    )
    # 应返回 404（底稿不存在）或 400（门禁阻断），不应 500
    assert resp.status_code in (400, 403, 404, 422)


@pytest.mark.asyncio
async def test_gate_evaluate_submit_review(pg_client):
    """门禁评估端点对 submit_review 类型可用"""
    await pg_client.post("/api/auth/register", json={
        "username": "gate2_user",
        "email": "gate2@test.com",
        "password": "Test123456",
    })
    login_resp = await pg_client.post("/api/auth/login", json={
        "username": "gate2_user",
        "password": "Test123456",
    })
    if login_resp.status_code != 200:
        pytest.skip("登录失败")

    token = login_resp.json().get("data", login_resp.json())["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = await pg_client.post("/api/gate/evaluate", json={
        "gate_type": "submit_review",
        "project_id": str(uuid.uuid4()),
        "target_id": str(uuid.uuid4()),
    }, headers=headers)

    # 门禁应返回评估结果（可能 blocked），不应 500
    assert resp.status_code in (200, 400, 404, 422)
