"""Wave 9 thin-router functional PG round-trip tests.

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R8, R11, R13
Design: §5.3 RAG/AI, §5.5 Archive/Retention/Legal Hold, §6.2 主要端点
Properties: P17 (AI 状态门禁), P24 (manifest 防覆盖), P26/P27 (Hold 保护 / Purge 四条件)
UAT: UAT-10 / UAT-12 / UAT-13

真实 PostgreSQL 16 round-trip，经 ASGI app + 授权 partner 用户，证明 Wave 9 新 thin router
不只是 401-可达，而是与既有服务的原始 SQL / 事务边界真正对齐（列名、CAST、facade 提交）：

  * Legal Hold create → purge 同节点：active hold 内 purge 零效果（delta=0, unmet=hold_active）。UAT-13
  * AI 生成登记 → 未确认 → FormalOutput 资格 blocked(NOT_CONFIRMED)；确认后 eligible。UAT-10
  * Archive 构建封存（空清单）→ sealed 落库 → 离线校验 package 通过。UAT-12

复用既有集成测试的 PG harness（同一连接 + 外层事务回滚 + 授权 partner FakeUser）。
非 PG 环境自动 skip。
"""

from __future__ import annotations

import uuid

import pytest

# 复用既有集成测试的 PG harness / ASGI client 辅助（同一连接、外层事务回滚、授权 partner）。
from tests.attachment_ocr_ai_evidence_governance_hardening.test_evidence_governance_http_wiring_integration import (  # noqa: F401
    _cleanup_overrides,
    _client,
    _unwrap,
    harness,
)

_YEAR = 2025


# ═════════════════════════════════════════════════════════════════════════════
# UAT-13 — Legal Hold veto: purge under active hold is zero-effect
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_legal_hold_create_then_purge_blocked_zero_effect(harness):
    client, app = await _client(harness)
    base = f"/api/projects/{harness.project_a}/years/{_YEAR}/evidence/legal-holds"
    node_id = str(uuid.uuid4())
    try:
        # 1) 创建法定保全，直接保护一个节点
        r = await client.post(
            base,
            json={
                "reason": "litigation hold",
                "seed_nodes": [{"node_type": "attachment_version", "node_id": node_id}],
            },
            headers={"Idempotency-Key": f"lh-{uuid.uuid4()}"},
        )
        assert r.status_code == 201, r.text
        created = _unwrap(r.json())
        assert created["direct_count"] >= 1
        assert created["graph_watermark"]

        # 2) 对同一受保护节点发起 purge（retention 已届满）——仍必须零效果（P26/P27）
        r2 = await client.post(
            base + "/purge-jobs",
            json={
                "node_type": "attachment_version",
                "node_id": node_id,
                "retention_expired": True,
            },
            headers={"Idempotency-Key": f"purge-{uuid.uuid4()}"},
        )
        assert r2.status_code == 200, r2.text
        decision = _unwrap(r2.json())
        assert decision["allowed"] is False
        assert decision["delta"] == 0
        assert "hold_active" in decision["unmet_conditions"]
        assert decision["tombstone_id"] is None
    finally:
        await client.aclose()
        _cleanup_overrides(app)


# ═════════════════════════════════════════════════════════════════════════════
# UAT-10 — AI draft not human-confirmed is blocked from FormalOutput
# ═════════════════════════════════════════════════════════════════════════════


async def _table_exists(harness, table: str) -> bool:
    import sqlalchemy as sa

    row = (
        await harness.conn.execute(
            sa.text("SELECT to_regclass(:t) IS NOT NULL AS present"),
            {"t": f"public.{table}"},
        )
    ).mappings().first()
    return bool(row and row["present"])


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_ai_generation_confirm_gate_roundtrip(harness):
    # GAP（诚实报告，非 fake-green）：设计 §4.6 的 ``ai_content_governance`` 物理表在当前库
    # 尚未迁移（见 test_rag_ai_property_group_pbt.py §平台现状；Wave 5 AIEvidenceGate 单测全用
    # mock DB）。AI 门禁 router 已正确接线到 AIEvidenceGate（SQL 经 CAST 修复后可编译，见
    # 本次对 ai_evidence_gate.py 的 :refs::jsonb→CAST 修复），但该域端到端 round-trip 需先补
    # ai_content_governance 迁移。表缺失时 skip，避免伪造通过；表就绪后本用例自动生效。
    if not await _table_exists(harness, "ai_content_governance"):
        pytest.skip(
            "ai_content_governance 表尚未迁移（已知上游 gap）——AI 门禁 router 已接线，"
            "但域端到端 round-trip 待该表迁移后可用"
        )
    client, app = await _client(harness)
    base = f"/api/projects/{harness.project_a}/years/{_YEAR}/evidence/ai"
    try:
        # 1) 登记 AI 生成（draft）
        r = await client.post(
            base + "/generations",
            json={
                "entry_point": "generate_text",
                "prompt_hash": "prompt seed text",
                "model_name": "qwen-test",
                "output": "AI 草稿结论内容",
            },
            headers={"Idempotency-Key": f"ai-{uuid.uuid4()}"},
        )
        assert r.status_code == 201, r.text
        reg = _unwrap(r.json())
        content_id = reg["content_id"]
        assert reg["lifecycle_status"] == "draft"

        # 2) 未确认 → FormalOutput 资格 blocked(NOT_CONFIRMED) —— UAT-10 一票否决点
        r2 = await client.get(base + f"/generations/{content_id}/eligibility")
        assert r2.status_code == 200, r2.text
        elig = _unwrap(r2.json())
        assert elig["eligible"] is False
        assert any(reason["code"] == "NOT_CONFIRMED" for reason in elig["reasons"])

        # 3) 人工确认 → 资格 eligible
        r3 = await client.post(
            base + f"/generations/{content_id}/confirm",
            headers={"Idempotency-Key": f"ai-confirm-{uuid.uuid4()}"},
        )
        assert r3.status_code == 200, r3.text
        assert _unwrap(r3.json())["confirmed"] is True

        r4 = await client.get(base + f"/generations/{content_id}/eligibility")
        assert r4.status_code == 200, r4.text
        assert _unwrap(r4.json())["eligible"] is True
    finally:
        await client.aclose()
        _cleanup_overrides(app)


# ═════════════════════════════════════════════════════════════════════════════
# UAT-12 — Archive build seals a manifest; offline verify passes
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_archive_build_and_offline_verify(harness):
    client, app = await _client(harness)
    base = f"/api/projects/{harness.project_a}/years/{_YEAR}/evidence/archive"
    try:
        # 1) 构建/封存归档清单（默认 provider → 空证据集 → gate PASS → sealed）
        r = await client.post(
            base + "/manifests",
            json={},
            headers={"Idempotency-Key": f"arch-{uuid.uuid4()}"},
        )
        assert r.status_code == 201, r.text
        built = _unwrap(r.json())
        assert built["success"] is True
        assert built["state"] == "sealed"
        assert built["version"] == 1
        pkg = built["sealed_package"]
        assert pkg and pkg.get("package_hash")

        # 2) 列表可见该已封存清单
        rl = await client.get(base + "/manifests")
        assert rl.status_code == 200, rl.text
        items = _unwrap(rl.json())["items"]
        assert any(it["version_no"] == 1 and it["state"] == "sealed" for it in items)

        # 3) 离线校验返回的封存包 → 通过（重算 hash 一致，未生成阻断报告）
        rv = await client.post(base + "/verify", json={"package": pkg})
        assert rv.status_code == 200, rv.text
        verify = _unwrap(rv.json())
        assert verify["verification_status"] == "passed"
        assert verify["is_valid"] is True
    finally:
        await client.aclose()
        _cleanup_overrides(app)
