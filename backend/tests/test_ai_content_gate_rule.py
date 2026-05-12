"""R3 Sprint 4 Task 21: AI 内容统一结构化门禁规则测试

2 场景：
1. 项目含未确认 AI 内容 → gate 阻断（返回 GateRuleHit）
2. 项目所有 AI 内容已确认 → gate 通过（返回 None）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

# 注册所有模型
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.consolidation_models  # noqa: E402, F401
import app.models.staff_models  # noqa: E402, F401
import app.models.collaboration_models  # noqa: E402, F401
import app.models.ai_models  # noqa: E402, F401
import app.models.extension_models  # noqa: E402, F401
import app.models.gt_coding_models  # noqa: E402, F401
import app.models.t_account_models  # noqa: E402, F401
import app.models.attachment_models  # noqa: E402, F401
import app.models.phase13_models  # noqa: E402, F401
import app.models.eqcr_models  # noqa: E402, F401
import app.models.related_party_models  # noqa: E402, F401
import app.models.phase14_models  # noqa: E402, F401

from app.models.base import ProjectStatus, ProjectType, UserRole  # noqa: E402
from app.models.core import Project, User  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    WorkingPaper,
    WpSourceType,
    WpFileStatus,
    WpReviewStatus,
    WpIndex,
)
from app.services.gate_rules_ai_content import AIContentMustBeConfirmedRule  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def user(db_session: AsyncSession):
    u = User(
        id=uuid.uuid4(),
        username="test_user",
        email="test@example.com",
        hashed_password="x",
        role=UserRole.admin,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, user: User):
    p = Project(
        id=uuid.uuid4(),
        name="Test Project",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=user.id,
    )
    db_session.add(p)
    await db_session.flush()
    return p


@pytest_asyncio.fixture
async def wp_index(db_session: AsyncSession, project: Project):
    idx = WpIndex(
        id=uuid.uuid4(),
        project_id=project.id,
        wp_code="D-100",
        wp_name="测试底稿",
    )
    db_session.add(idx)
    await db_session.flush()
    return idx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unconfirmed_ai_content_blocks_sign_off(
    db_session: AsyncSession, project: Project, wp_index: WpIndex
):
    """场景 1: 项目含未确认 AI 内容 → gate 阻断"""
    # 创建底稿，parsed_data 中含未确认的 AI 生成内容
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project.id,
        wp_index_id=wp_index.id,
        file_path="/test/wp1.xlsx",
        source_type=WpSourceType.manual,
        status=WpFileStatus.draft,
        review_status=WpReviewStatus.not_submitted,
        parsed_data={
            "cells": [
                {"row": 1, "col": "A", "value": "正常数据"},
                {
                    "row": 2,
                    "col": "B",
                    "type": "ai_generated",
                    "source_model": "qwen3.5-27b",
                    "confidence": 0.85,
                    "confirmed_by": None,
                    "confirmed_at": None,
                    "value": "AI 生成的分析结论",
                },
            ],
        },
    )
    db_session.add(wp)
    await db_session.flush()

    rule = AIContentMustBeConfirmedRule()
    context = {"project_id": project.id}
    hit = await rule.check(db_session, context)

    assert hit is not None
    assert hit.rule_code == "R3-AI-UNCONFIRMED"
    assert hit.error_code == "AI_CONTENT_NOT_CONFIRMED"
    assert hit.severity == "blocking"
    assert "未确认的AI生成内容" in hit.message
    assert hit.location["unconfirmed_wp_count"] == 1


@pytest.mark.asyncio
async def test_confirmed_ai_content_passes_sign_off(
    db_session: AsyncSession, project: Project, wp_index: WpIndex
):
    """场景 2: 项目所有 AI 内容已确认 → gate 通过"""
    confirmer_id = uuid.uuid4()
    confirmed_time = datetime.now(timezone.utc).isoformat()

    # 创建底稿，parsed_data 中 AI 内容已确认
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project.id,
        wp_index_id=wp_index.id,
        file_path="/test/wp2.xlsx",
        source_type=WpSourceType.manual,
        status=WpFileStatus.draft,
        review_status=WpReviewStatus.not_submitted,
        parsed_data={
            "cells": [
                {"row": 1, "col": "A", "value": "正常数据"},
                {
                    "row": 2,
                    "col": "B",
                    "type": "ai_generated",
                    "source_model": "qwen3.5-27b",
                    "confidence": 0.85,
                    "confirmed_by": str(confirmer_id),
                    "confirmed_at": confirmed_time,
                    "value": "AI 生成的分析结论（已确认）",
                },
            ],
            "ai_analysis": {
                "type": "ai_generated",
                "source_model": "qwen3.5-27b",
                "confidence": 0.8,
                "confirmed_by": str(confirmer_id),
                "confirmed_at": confirmed_time,
                "value": "该科目余额变动正常",
            },
        },
    )
    db_session.add(wp)
    await db_session.flush()

    rule = AIContentMustBeConfirmedRule()
    context = {"project_id": project.id}
    hit = await rule.check(db_session, context)

    assert hit is None, "所有 AI 内容已确认，gate 应通过"
