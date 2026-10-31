"""真 PG 年度契约测试（formula-hub 任务 23-2C；ADR-FHIC-06 §8.2 年度闸门）。

用快照库 ``fh_snap_202610270028`` 经 ``pg_tx``（回滚事务）建 fixture。
五组用例覆盖 ``resolve_wp_cell`` 的 ``_year_gate`` 与底稿绑定路径。

Requirements: 1.6, 1.9
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.core import Project
from app.models.workpaper_models import WorkingPaper, WpIndex
from app.services.project_audit_year import fetch_project_audit_year
from app.services.wp_cell_reader import resolve_wp_cell


pytestmark = pytest.mark.pg_only


async def _make_project(session, *, name: str, audit_year: int | None = None) -> uuid.UUID:
    """ORM 创建最小项目（Python 默认值自动填充 NOT NULL 列）。"""
    project = Project(name=name, client_name="【测试】formula-hub", audit_year=audit_year)
    session.add(project)
    await session.flush()
    return project.id


async def _make_wp(session, *, project_id: uuid.UUID, wp_code: str,
                   parsed_data: dict | None = None) -> uuid.UUID:
    """建 wp_index + working_paper 一对，返回 working_paper.id。"""
    from app.models.workpaper_models import WpSourceType

    idx = WpIndex(project_id=project_id, wp_code=wp_code, wp_name=f"【测试】{wp_code}")
    session.add(idx)
    await session.flush()
    pd = parsed_data if parsed_data is not None else {"html_data": {"审定表": {"cells": {"A1": 100}}}}
    wp = WorkingPaper(
        project_id=project_id, wp_index_id=idx.id, parsed_data=pd,
        is_deleted=False, file_path=f"/tmp/fh_test/{wp_code}.xlsx",
        source_type=WpSourceType.template,
    )
    session.add(wp)
    await session.flush()
    return wp.id


# ── 用例 1：audit_year=2025 + year=2025 → ok ──────────────────────────────

@pytest.mark.anyio
async def test_year_match_returns_ok(pg_tx):
    """项目 audit_year=2025，year=2025 → resolve_wp_cell ok。"""
    pid = await _make_project(pg_tx, name="【测试】fh_year_ok", audit_year=2025)
    await _make_wp(pg_tx, project_id=pid, wp_code="FH-T23")

    read = await resolve_wp_cell(pg_tx, pid, 2025, "FH-T23", None, "A1")
    assert read.state == "ok"
    assert read.value is not None


# ── 用例 2：audit_year=NULL + year=2025 → blocked「项目未设置审计年度」 ────

@pytest.mark.anyio
async def test_year_null_returns_blocked(pg_tx):
    """项目 audit_year 为 NULL，year=2025 → blocked「项目未设置审计年度」。"""
    pid = await _make_project(pg_tx, name="【测试】fh_year_null", audit_year=None)
    await _make_wp(pg_tx, project_id=pid, wp_code="FH-T23N")

    read = await resolve_wp_cell(pg_tx, pid, 2025, "FH-T23N", None, "A1")
    assert read.state == "blocked"
    assert read.reason is not None
    assert "项目未设置审计年度" in read.reason


# ── 用例 3：audit_year=2024 + year=2025 → missing ──────────────────────────

@pytest.mark.anyio
async def test_year_mismatch_returns_missing(pg_tx):
    """项目 audit_year=2024，year=2025 → missing（年度不符）。"""
    pid = await _make_project(pg_tx, name="【测试】fh_year_mismatch", audit_year=2024)
    await _make_wp(pg_tx, project_id=pid, wp_code="FH-T23M")

    read = await resolve_wp_cell(pg_tx, pid, 2025, "FH-T23M", None, "A1")
    assert read.state == "missing"
    assert read.reason is not None
    assert "年度" in read.reason


# ── 用例 4：一对多底稿 → blocked「底稿记录有歧义」 ───────────────────────

@pytest.mark.anyio
async def test_ambiguous_wp_unreachable_with_constraint(pg_tx):
    """唯一约束 uq_wp_index_project_code 阻止同一项目同一 wp_code 出现两条底稿。

    ``resolve_wp_cell`` 的 ``len(rows) > 1 → blocked`` 是防御性代码路径，
    在正确 schema 下不可达。此用例验证约束确实存在。
    """
    pid = await _make_project(pg_tx, name="【测试】fh_constraint", audit_year=2025)
    await _make_wp(pg_tx, project_id=pid, wp_code="FH-UNQ")
    # 第二条同 wp_code 应被唯一约束拦截
    with pytest.raises(Exception, match="uq_wp_index_project_code|unique"):
        await _make_wp(pg_tx, project_id=pid, wp_code="FH-UNQ")


# ── 用例 5：快照库中有试算表的活项目年度均可解析 ───────────────────────────

@pytest.mark.anyio
async def test_snapshot_active_projects_have_resolvable_year(pg_tx):
    """快照库中有 trial_balance 行的活项目 → fetch_project_audit_year 返回非 None。"""
    rows = (await pg_tx.execute(sa.text(
        "SELECT DISTINCT p.id, p.name "
        "FROM projects p "
        "JOIN trial_balance tb ON tb.project_id = p.id "
        "WHERE p.is_deleted IS NOT TRUE "
        "LIMIT 20"
    ))).all()
    assert len(rows) > 0, "快照库中没有带试算表的活项目"

    for pid, name in rows:
        year = await fetch_project_audit_year(pg_tx, pid)
        assert year is not None, f"项目 {name}（{pid}）审计年度解析失败"
