"""WpFormulaService.save 公式态保护（P0-项2 · 导入/保存入口）

验证 save 对 damaged/blocked 公式**拒绝写库**（不静默仅存值），返回 issue 保留原始表达式作证据；
合法公式正常写入。

ownership / 悬空引用校验被 patch（隔离，聚焦态分类分支）。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wp_formula_service import WpFormulaService


def _patched_svc_and_db():
    svc = WpFormulaService()
    db = AsyncMock()
    # upsert 查既有行 → None（走新建分支）
    _res = MagicMock()
    _res.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=_res)
    db.flush = AsyncMock()
    return svc, db


async def _save(svc, db, expression):
    with patch.object(svc, "_verify_wp_ownership", new=AsyncMock(return_value=True)), patch(
        "app.services.wp_formula_service.validate_refs_via_acnr",
        new=AsyncMock(return_value=[]),
    ):
        return await svc.save(
            db,
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            sheet_name="审定表D2-1",
            target_cell="B5",
            expression=expression,
            year=2025,
        )


@pytest.mark.asyncio
async def test_save_rejects_blocked_formula_with_evidence():
    """含 eval/未注册函数 → 拒绝写库，issue 保留原始表达式证据，不落库。"""
    svc, db = _patched_svc_and_db()
    saved, issues = await _save(svc, db, "eval('2+2')")
    assert saved is None
    assert issues and issues[0]["reason"] == "formula_blocked"
    assert issues[0]["expression"] == "eval('2+2')"  # 原始表达式作证据
    db.add.assert_not_called()  # 未落库


@pytest.mark.asyncio
async def test_save_rejects_unknown_function_as_blocked():
    svc, db = _patched_svc_and_db()
    saved, issues = await _save(svc, db, "HACKFN('x')")
    assert saved is None
    assert issues[0]["reason"] == "formula_blocked"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_rejects_damaged_formula():
    """结构损坏（AST 解析失败）→ 拒绝，reason=formula_damaged，保留原始表达式。"""
    svc, db = _patched_svc_and_db()
    saved, issues = await _save(svc, db, "TB('1001'")
    assert saved is None
    assert issues[0]["reason"] == "formula_damaged"
    assert issues[0]["expression"] == "TB('1001'"
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_accepts_valid_formula():
    """合法白名单公式 → 通过态分类，进入落库路径（db.add 被调用）。"""
    svc, db = _patched_svc_and_db()
    saved, issues = await _save(svc, db, "TB('1001','期末余额')+ROW('BS-002')")
    # 无既有行（mock execute 返回 scalar_one_or_none=None）→ 新建分支 db.add
    assert issues == []
    db.add.assert_called_once()
