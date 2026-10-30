"""公式推送深度反向校验：真实动作枚举、dry-run 签名与无持久化事务边界。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.services.formula_push.results import CONFLICT, FALLBACK_TO_TOTAL, SKIPPED, PushItem, RunResult


@pytest.mark.asyncio
async def test_deep_verify_uses_manual_dry_run_and_classifies_all_actions(monkeypatch):
    from app.services.formula_push import engine, verify

    pid = uuid.uuid4()
    db = AsyncMock()
    calls = []

    async def fake_run(db_arg, *, project_id, year, trigger, dry_run, **kwargs):
        calls.append((db_arg, project_id, year, trigger, dry_run, kwargs))
        return RunResult(
            project_id=pid,
            year=2025,
            trigger=trigger,
            items=[
                PushItem("r1", "note", "note", "n1", "unchanged", formula=1, current=1),
                PushItem("r2", "note", "note", "n2", "write", formula=2, current=1),
                PushItem("r3", "note", "note", "n3", "keep_manual", formula=3, current=1),
                PushItem("r4", "note", "note", "n4", SKIPPED, reason="缺来源"),
                PushItem("r5", "note", "note", "n5", FALLBACK_TO_TOTAL, reason="写入合计"),
                PushItem("r6", "note", "note", "n6", CONFLICT, reason="并发"),
            ],
        )

    monkeypatch.setattr(engine, "run", fake_run)
    result = await verify.deep_verify_push(db, pid, 2025)

    assert calls == [(db, pid, 2025, engine.MANUAL, True, {})]
    assert result["mode"] == "deep"
    assert result["total"] == 6
    assert {key: result[key] for key in ("consistent", "diverged", "manual_override", "unresolved", "fallback")} == {
        "consistent": 1, "diverged": 1, "manual_override": 1, "unresolved": 2, "fallback": 1,
    }
    assert result["action_counts"] == {
        "unchanged": 1, "write": 1, "keep_manual": 1, SKIPPED: 1, FALLBACK_TO_TOTAL: 1, CONFLICT: 1,
    }
    assert result["diverged_items"] == [
        {"addr_id": "n2", "domain": "note", "rule_id": "r2", "action": "write", "reason": None,
         "formula_value": "2", "current_value": "1"},
        {"addr_id": "n4", "domain": "note", "rule_id": "r4", "action": SKIPPED, "reason": "缺来源",
         "formula_value": None, "current_value": None},
        {"addr_id": "n6", "domain": "note", "rule_id": "r6", "action": CONFLICT, "reason": "并发",
         "formula_value": None, "current_value": None},
    ]
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_deep_verify_returns_error_and_still_rolls_back(monkeypatch):
    from app.services.formula_push import engine, verify

    db = AsyncMock()

    async def exploding(*args, **kwargs):
        raise RuntimeError("expected probe failure")

    monkeypatch.setattr(engine, "run", exploding)
    result = await verify.deep_verify_push(db, uuid.uuid4(), 2025)
    assert result["mode"] == "deep" and result["total"] == 0
    assert "expected probe failure" in result["error"]
    db.rollback.assert_awaited_once()
