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

# SQLite JSONB / ARRAY 兼容（必须在导入模型之前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

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
import app.models.audit_log_models  # noqa: E402, F401  # ai_content_log_service 审计写入
import app.models.v3_refinement_models  # noqa: E402, F401  # ai_content_log 表

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
from app.services import ai_content_log_service  # noqa: E402
from app.services.gate_engine import rule_registry  # noqa: E402
from app.models.phase14_enums import GateType  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # 仅建测试需要的表，避免拉入 custom_query_templates(ARRAY/jsonb cast) 等不兼容 SQLite 的表
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["wp_index"],
            Base.metadata.tables["working_paper"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["ai_content_log"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)
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


# ---------------------------------------------------------------------------
# V3 Req 6.3：ai_content_log 表新机制 + 注册校验
# ---------------------------------------------------------------------------


async def _create_pending_log(
    db_session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
):
    """工具：写一条 pending 的 ai_content_log 记录。"""
    return await ai_content_log_service.create(
        db=db_session,
        project_id=project_id,
        user_id=user_id,
        instance_type="workpaper",
        instance_id=uuid.uuid4(),
        target_cell="narrative",
        model="qwen3.5-27b",
        prompt_hash="p" * 64,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32],
        generated_content="待确认的 AI 输出内容",
        confidence=0.85,
    )


@pytest.mark.asyncio
async def test_pending_ai_content_log_blocks_sign_off(
    db_session: AsyncSession, project: Project, user: User
):
    """ai_content_log 含 pending 时，规则命中且 location.via='ai_content_log'。"""
    await _create_pending_log(db_session, project.id, user.id)
    await db_session.flush()

    rule = AIContentMustBeConfirmedRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    assert hit.rule_code == "R3-AI-UNCONFIRMED"
    assert hit.error_code == "AI_CONTENT_NOT_CONFIRMED"
    assert hit.severity == "blocking"
    assert hit.location.get("via") == "ai_content_log"
    assert hit.location.get("pending_count") == 1
    assert len(hit.location.get("sample_log_ids", [])) == 1


@pytest.mark.asyncio
async def test_confirmed_ai_content_log_passes_sign_off(
    db_session: AsyncSession, project: Project, user: User
):
    """ai_content_log 全部 confirmed 时，规则不触发。"""
    log = await _create_pending_log(db_session, project.id, user.id)
    await db_session.flush()
    await ai_content_log_service.confirm(
        db=db_session, log_id=log.id, user_id=user.id
    )
    await db_session.flush()

    rule = AIContentMustBeConfirmedRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is None, "所有 ai_content_log 已 confirmed，sign_off 应通过"


@pytest.mark.asyncio
async def test_mixed_pending_log_and_clean_parsed_data_blocks(
    db_session: AsyncSession, project: Project, wp_index: WpIndex, user: User
):
    """log 表 pending + parsed_data 干净 → 仍阻断（来源标 ai_content_log）。"""
    # 1 条 pending log
    await _create_pending_log(db_session, project.id, user.id)

    # 一份 parsed_data 完全没有 ai_generated 内容的底稿
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project.id,
        wp_index_id=wp_index.id,
        file_path="/test/clean.xlsx",
        source_type=WpSourceType.manual,
        status=WpFileStatus.draft,
        review_status=WpReviewStatus.not_submitted,
        parsed_data={"cells": [{"row": 1, "col": "A", "value": "纯人工内容"}]},
    )
    db_session.add(wp)
    await db_session.flush()

    rule = AIContentMustBeConfirmedRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    assert hit.location.get("via") == "ai_content_log"


@pytest.mark.asyncio
async def test_clean_log_and_pending_parsed_data_blocks(
    db_session: AsyncSession, project: Project, wp_index: WpIndex, user: User
):
    """log 表干净 + parsed_data 有未确认 → 仍阻断（来源标 parsed_data）。"""
    # ai_content_log 完全空，parsed_data 含 ai_generated/confirmed_by=None
    wp = WorkingPaper(
        id=uuid.uuid4(),
        project_id=project.id,
        wp_index_id=wp_index.id,
        file_path="/test/legacy.xlsx",
        source_type=WpSourceType.manual,
        status=WpFileStatus.draft,
        review_status=WpReviewStatus.not_submitted,
        parsed_data={
            "cells": [
                {
                    "row": 2,
                    "col": "B",
                    "type": "ai_generated",
                    "source_model": "qwen3.5-27b",
                    "confirmed_by": None,
                    "confirmed_at": None,
                    "value": "历史底稿遗留 AI 输出",
                }
            ]
        },
    )
    db_session.add(wp)
    await db_session.flush()

    rule = AIContentMustBeConfirmedRule()
    hit = await rule.check(db_session, {"project_id": project.id})

    assert hit is not None
    # 旧路径命中：via='parsed_data'
    assert hit.location.get("via") == "parsed_data"
    assert hit.location.get("unconfirmed_wp_count") == 1


def test_rule_registered_to_sign_off():
    """模块导入时 AIContentMustBeConfirmedRule 已注册到 sign_off gate。"""
    rules = rule_registry.get_rules(GateType.sign_off)
    rule_codes = [getattr(r, "rule_code", None) for r in rules]
    assert "R3-AI-UNCONFIRMED" in rule_codes, (
        f"R3-AI-UNCONFIRMED 应注册到 sign_off，但实际只有 {rule_codes}"
    )

    # 确保是 AIContentMustBeConfirmedRule 实例（不是 stub/mock）
    target = next(
        (r for r in rules if getattr(r, "rule_code", None) == "R3-AI-UNCONFIRMED"),
        None,
    )
    assert target is not None
    assert isinstance(target, AIContentMustBeConfirmedRule)
