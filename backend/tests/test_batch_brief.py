"""批量简报端点测试 — Round 2 需求 6 Task 15

覆盖：
- BatchBriefService 缓存键计算
- BatchBriefService 简报拼接
- BatchBriefService 创建任务 + 执行
- 7 天缓存复用
- AI 失败回退纯拼接
- API 端点集成测试
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.core import Project, User
from app.models.phase13_models import (
    ExportJob,
    ExportJobStatus,
    WordExportTask,
)
from app.services.batch_brief_service import (
    BatchBriefService,
    _compute_cache_key,
    CACHE_TTL_DAYS,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest_asyncio.fixture
async def test_db():
    """Create in-memory SQLite test database."""
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_local = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_local() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def test_user(test_db: AsyncSession) -> User:
    """Create a test user with manager role."""
    user = User(
        id=uuid.uuid4(),
        username="test_manager",
        email="manager@test.com",
        hashed_password="hashed",
        role="manager",
    )
    test_db.add(user)
    await test_db.flush()
    return user


@pytest_asyncio.fixture
async def test_projects(test_db: AsyncSession) -> list[Project]:
    """Create 3 test projects."""
    projects = []
    for i in range(3):
        project = Project(
            id=uuid.uuid4(),
            name=f"测试项目{i+1}",
            client_name=f"客户{i+1}有限公司",
            status="created",
            wizard_state={},
        )
        test_db.add(project)
        projects.append(project)
    await test_db.flush()
    return projects


# ===================================================================
# Unit Tests: _compute_cache_key
# ===================================================================


class TestComputeCacheKey:
    """缓存键计算测试"""

    def test_same_ids_same_key(self):
        """相同项目组合产生相同缓存键"""
        ids = [uuid.uuid4() for _ in range(3)]
        key1 = _compute_cache_key(ids, use_ai=True)
        key2 = _compute_cache_key(ids, use_ai=True)
        assert key1 == key2

    def test_order_independent(self):
        """项目 ID 顺序不影响缓存键"""
        ids = [uuid.uuid4() for _ in range(3)]
        key1 = _compute_cache_key(ids, use_ai=False)
        key2 = _compute_cache_key(list(reversed(ids)), use_ai=False)
        assert key1 == key2

    def test_different_ai_mode_different_key(self):
        """AI 模式不同产生不同缓存键"""
        ids = [uuid.uuid4() for _ in range(3)]
        key1 = _compute_cache_key(ids, use_ai=True)
        key2 = _compute_cache_key(ids, use_ai=False)
        assert key1 != key2

    def test_different_ids_different_key(self):
        """不同项目组合产生不同缓存键"""
        ids1 = [uuid.uuid4() for _ in range(3)]
        ids2 = [uuid.uuid4() for _ in range(3)]
        key1 = _compute_cache_key(ids1, use_ai=True)
        key2 = _compute_cache_key(ids2, use_ai=True)
        assert key1 != key2


# ===================================================================
# Unit Tests: BatchBriefService
# ===================================================================


class TestBatchBriefService:
    """BatchBriefService 核心逻辑测试"""

    @pytest.mark.asyncio
    async def test_create_job_no_cache(self, test_db, test_projects, test_user):
        """无缓存时创建新任务"""
        svc = BatchBriefService(test_db)
        project_ids = [p.id for p in test_projects]

        job_id = await svc.create_batch_brief_job(
            project_ids=project_ids,
            use_ai=False,
            user_id=test_user.id,
        )
        await test_db.flush()

        assert job_id is not None
        # 验证 job 已创建
        result = await test_db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        assert job is not None
        assert job.job_type == "batch_brief"
        assert job.status == ExportJobStatus.queued.value
        assert job.progress_total == 3

    @pytest.mark.asyncio
    async def test_cache_hit_returns_succeeded_job(self, test_db, test_projects, test_user):
        """7 天内缓存命中时直接返回已完成的 job"""
        project_ids = [p.id for p in test_projects]
        cache_key = _compute_cache_key(project_ids, use_ai=False)

        # 手动插入一个缓存结果
        cached_task = WordExportTask(
            id=uuid.uuid4(),
            project_id=project_ids[0],
            doc_type="batch_brief",
            status="generated",
            template_type=cache_key,
            file_path=json.dumps({"final_text": "cached result"}),
            created_by=test_user.id,
        )
        test_db.add(cached_task)
        await test_db.flush()

        svc = BatchBriefService(test_db)
        job_id = await svc.create_batch_brief_job(
            project_ids=project_ids,
            use_ai=False,
            user_id=test_user.id,
        )
        await test_db.flush()

        # 验证 job 直接标记为成功
        result = await test_db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        assert job is not None
        assert job.status == ExportJobStatus.succeeded.value
        assert job.progress_done == 3

    @pytest.mark.asyncio
    async def test_combine_briefs(self, test_db):
        """简报拼接格式正确"""
        svc = BatchBriefService(test_db)
        briefs = [
            {
                "project_name": "项目A",
                "completion_rate": 80.0,
                "raw_summary": "## 项目A 项目进度简报\n\n**整体完成率**：80%",
                "rejected_count": 2,
            },
            {
                "project_name": "项目B",
                "completion_rate": 40.0,
                "raw_summary": "## 项目B 项目进度简报\n\n**整体完成率**：40%",
                "rejected_count": 0,
            },
        ]
        result = svc._combine_briefs(briefs)

        assert "# 跨项目合并简报" in result
        assert "项目A" in result
        assert "项目B" in result
        assert "综合风险汇总" in result
        assert "项目A" in result  # 有退回
        assert "项目B(40.0%)" in result  # 完成率低于 50%

    @pytest.mark.asyncio
    async def test_execute_batch_brief_no_ai(self, test_db, test_projects, test_user):
        """执行批量简报（无 AI 模式）"""
        project_ids = [p.id for p in test_projects]

        # 先创建 job
        svc = BatchBriefService(test_db)
        job_id = await svc.create_batch_brief_job(
            project_ids=project_ids,
            use_ai=False,
            user_id=test_user.id,
        )
        await test_db.flush()

        # 执行
        result = await svc.execute_batch_brief(
            job_id=job_id,
            project_ids=project_ids,
            use_ai=False,
            user_id=test_user.id,
        )
        await test_db.flush()

        assert result is not None
        assert result["project_count"] == 3
        assert result["use_ai"] is False
        assert result["ai_used"] is False
        assert "combined_text" in result
        assert "briefs" in result
        assert len(result["briefs"]) == 3

        # 验证 job 状态更新为成功
        job_result = await test_db.execute(
            sa.select(ExportJob).where(ExportJob.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        assert job.status == ExportJobStatus.succeeded.value

    @pytest.mark.asyncio
    async def test_execute_batch_brief_ai_fallback(self, test_db, test_projects, test_user):
        """AI 模式失败时回退到纯拼接"""
        project_ids = [p.id for p in test_projects]

        svc = BatchBriefService(test_db)
        job_id = await svc.create_batch_brief_job(
            project_ids=project_ids,
            use_ai=True,
            user_id=test_user.id,
        )
        await test_db.flush()

        # Mock AI service to fail
        with patch.object(
            svc, "_generate_ai_summary", new_callable=AsyncMock, return_value=None
        ):
            result = await svc.execute_batch_brief(
                job_id=job_id,
                project_ids=project_ids,
                use_ai=True,
                user_id=test_user.id,
            )
            await test_db.flush()

        assert result is not None
        assert result["use_ai"] is True
        assert result["ai_used"] is False
        # final_text 应该是 combined_text（回退）
        assert result["final_text"] == result["combined_text"]

    @pytest.mark.asyncio
    async def test_get_job_result_succeeded(self, test_db, test_projects, test_user):
        """获取已完成任务的结果"""
        project_ids = [p.id for p in test_projects]

        svc = BatchBriefService(test_db)
        job_id = await svc.create_batch_brief_job(
            project_ids=project_ids,
            use_ai=False,
            user_id=test_user.id,
        )
        await test_db.flush()

        # 执行
        await svc.execute_batch_brief(
            job_id=job_id,
            project_ids=project_ids,
            use_ai=False,
            user_id=test_user.id,
        )
        await test_db.flush()

        # 获取结果
        result = await svc.get_job_result(job_id)
        assert result is not None
        assert result["status"] == ExportJobStatus.succeeded.value
        assert "data" in result

    @pytest.mark.asyncio
    async def test_get_job_result_not_found(self, test_db):
        """查询不存在的任务返回 None"""
        svc = BatchBriefService(test_db)
        result = await svc.get_job_result(uuid.uuid4())
        assert result is None
