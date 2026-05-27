"""ai_content_log_service 单元测试 — V3 收官增强 Req 6.1

覆盖 9 个测试用例：
- test_create_pending — 创建后 confirm_action='pending'
- test_confirm_success — 确认后 confirm_action='confirmed' + confirmed_at/by 已写
- test_confirm_already_confirmed_raises — 重复确认抛 ValueError
- test_confirm_not_found_raises — log_id 不存在抛 ValueError
- test_revise_success — 修订后 revised_content 写入 + confirm_action='revised'
- test_reject_success — 拒绝后 confirm_action='rejected' + revised_content 仍 NULL
- test_list_by_project — 按项目过滤
- test_list_pending — 仅返回 pending
- test_count_pending — 计数正确
- test_audit_log_written — 每次操作都写 audit_log
- test_list_by_project_with_status_filter — 状态过滤生效
- test_list_by_project_with_instance_type_filter — 业务实例类型过滤生效
- test_create_with_confidence_decimal_passthrough — 置信度 Decimal 透传

Validates: Requirements 6.1
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402

# 仅注册测试所需的模型
import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401

from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.models.v3_refinement_models import AiContentLog  # noqa: E402
from app.services import ai_content_log_service as svc  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。

    创建：users / projects / audit_log_entries / ai_content_log 4 张表，
    项目级 FK 通过预先写入的 user/project 记录保证完整性。
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["ai_content_log"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def user_and_project(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """预先写入 users / projects 各一条，返回 (user_id, project_id) 供 FK 引用。"""
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    user = User(
        id=user_id,
        username=f"tester-{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@test.local",
        hashed_password="hashed",
        role=UserRole.auditor,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
    )
    db_session.add(user)
    db_session.add(project)
    await db_session.commit()
    return user_id, project_id


def _make_create_kwargs(
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    instance_type: str = "workpaper",
    instance_id: uuid.UUID | None = None,
    target_cell: str | None = "narrative",
    content_hash: str | None = None,
    generated_content: str = "AI 生成的结论建议：科目余额变动合理，无需进一步审计程序。",
    model: str = "qwen3.5-27b",
    prompt_hash: str | None = "p" * 64,
    confidence: Decimal | float | None = Decimal("0.85"),
) -> dict:
    return {
        "project_id": project_id,
        "user_id": user_id,
        "instance_type": instance_type,
        "instance_id": instance_id or uuid.uuid4(),
        "target_cell": target_cell,
        "model": model,
        "prompt_hash": prompt_hash,
        "content_hash": content_hash or ("c" * 64),
        "generated_content": generated_content,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


class TestCreate:
    """create() 写入 pending 状态 + 审计日志。"""

    @pytest.mark.asyncio
    async def test_create_pending(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        kwargs = _make_create_kwargs(user_id, project_id)
        log = await svc.create(db=db_session, **kwargs)
        await db_session.commit()

        assert isinstance(log.id, uuid.UUID)
        assert log.project_id == project_id
        assert log.user_id == user_id
        assert log.confirm_action == "pending"
        assert log.confirmed_by is None
        assert log.confirmed_at is None
        assert log.revised_content is None
        assert log.generated_content == kwargs["generated_content"]
        assert log.model == "qwen3.5-27b"
        assert log.confidence == Decimal("0.85")
        # target_cell 应被前缀化保存
        assert log.target_cell.startswith("workpaper:")
        assert "narrative" in log.target_cell

    @pytest.mark.asyncio
    async def test_create_with_confidence_float_converts_to_decimal(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        kwargs = _make_create_kwargs(user_id, project_id, confidence=0.75)
        log = await svc.create(db=db_session, **kwargs)
        await db_session.commit()
        assert isinstance(log.confidence, Decimal)
        assert log.confidence == Decimal("0.75")

    @pytest.mark.asyncio
    async def test_create_without_target_cell_uses_instance_only(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        kwargs = _make_create_kwargs(user_id, project_id, target_cell=None)
        log = await svc.create(db=db_session, **kwargs)
        await db_session.commit()
        # target_cell 应为 'workpaper:<uuid>'（无字段后缀）
        assert log.target_cell.startswith("workpaper:")
        assert log.target_cell.count(":") == 1


# ---------------------------------------------------------------------------
# confirm
# ---------------------------------------------------------------------------


class TestConfirm:
    """confirm() 状态流转与异常分支。"""

    @pytest.mark.asyncio
    async def test_confirm_success(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        log = await svc.create(db=db_session, **_make_create_kwargs(user_id, project_id))
        await db_session.commit()

        confirmer_id = uuid.uuid4()
        confirmed = await svc.confirm(
            db=db_session, log_id=log.id, user_id=confirmer_id
        )
        await db_session.commit()

        assert confirmed.id == log.id
        assert confirmed.confirm_action == "confirmed"
        assert confirmed.confirmed_by == confirmer_id
        assert isinstance(confirmed.confirmed_at, datetime)
        assert confirmed.revised_content is None  # confirm 不写 revised_content

    @pytest.mark.asyncio
    async def test_confirm_already_confirmed_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        log = await svc.create(db=db_session, **_make_create_kwargs(user_id, project_id))
        await db_session.commit()
        await svc.confirm(db=db_session, log_id=log.id, user_id=uuid.uuid4())
        await db_session.commit()

        with pytest.raises(ValueError, match="已处理过"):
            await svc.confirm(db=db_session, log_id=log.id, user_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_confirm_not_found_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        with pytest.raises(ValueError, match="不存在"):
            await svc.confirm(
                db=db_session, log_id=uuid.uuid4(), user_id=uuid.uuid4()
            )


# ---------------------------------------------------------------------------
# revise
# ---------------------------------------------------------------------------


class TestRevise:
    @pytest.mark.asyncio
    async def test_revise_success(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        log = await svc.create(db=db_session, **_make_create_kwargs(user_id, project_id))
        await db_session.commit()

        revised_text = "审计师修订后的版本：补充了对周转率异常的进一步分析。"
        revised = await svc.revise(
            db=db_session,
            log_id=log.id,
            user_id=user_id,
            revised_content=revised_text,
        )
        await db_session.commit()

        assert revised.confirm_action == "revised"
        assert revised.revised_content == revised_text
        assert revised.confirmed_by == user_id
        assert isinstance(revised.confirmed_at, datetime)

    @pytest.mark.asyncio
    async def test_revise_already_processed_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        log = await svc.create(db=db_session, **_make_create_kwargs(user_id, project_id))
        await db_session.commit()
        await svc.confirm(db=db_session, log_id=log.id, user_id=user_id)
        await db_session.commit()

        with pytest.raises(ValueError, match="已处理过"):
            await svc.revise(
                db=db_session,
                log_id=log.id,
                user_id=user_id,
                revised_content="再次修订",
            )


# ---------------------------------------------------------------------------
# reject
# ---------------------------------------------------------------------------


class TestReject:
    @pytest.mark.asyncio
    async def test_reject_success(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        log = await svc.create(db=db_session, **_make_create_kwargs(user_id, project_id))
        await db_session.commit()

        rejected = await svc.reject(
            db=db_session, log_id=log.id, user_id=user_id
        )
        await db_session.commit()

        assert rejected.confirm_action == "rejected"
        assert rejected.confirmed_by == user_id
        assert isinstance(rejected.confirmed_at, datetime)
        # 拒绝场景下 revised_content 必须保持 NULL（语义：不接受任何形式）
        assert rejected.revised_content is None


# ---------------------------------------------------------------------------
# list / count
# ---------------------------------------------------------------------------


class TestListAndCount:
    @pytest.mark.asyncio
    async def test_list_by_project_filters_by_project(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        # 在同一个 user/project 下写 3 条
        for i in range(3):
            await svc.create(
                db=db_session,
                **_make_create_kwargs(
                    user_id, project_id, content_hash=f"{i:0>64}"
                ),
            )
        # 另建第二个 project，写 1 条
        from app.models.base import ProjectStatus
        from app.models.core import Project

        other_project_id = uuid.uuid4()
        db_session.add(
            Project(
                id=other_project_id,
                name="另一项目",
                client_name="另一客户",
                status=ProjectStatus.execution,
            )
        )
        await db_session.commit()
        await svc.create(
            db=db_session,
            **_make_create_kwargs(user_id, other_project_id, content_hash="z" * 64),
        )
        await db_session.commit()

        rows = await svc.list_by_project(db=db_session, project_id=project_id)
        assert len(rows) == 3
        assert all(r.project_id == project_id for r in rows)

    @pytest.mark.asyncio
    async def test_list_by_project_status_filter(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        log_a = await svc.create(
            db=db_session,
            **_make_create_kwargs(user_id, project_id, content_hash="a" * 64),
        )
        log_b = await svc.create(
            db=db_session,
            **_make_create_kwargs(user_id, project_id, content_hash="b" * 64),
        )
        log_c = await svc.create(
            db=db_session,
            **_make_create_kwargs(user_id, project_id, content_hash="c" * 64),
        )
        await db_session.commit()
        await svc.confirm(db=db_session, log_id=log_b.id, user_id=user_id)
        await svc.reject(db=db_session, log_id=log_c.id, user_id=user_id)
        await db_session.commit()

        confirmed = await svc.list_by_project(
            db=db_session, project_id=project_id, status="confirmed"
        )
        assert {r.id for r in confirmed} == {log_b.id}

        rejected = await svc.list_by_project(
            db=db_session, project_id=project_id, status="rejected"
        )
        assert {r.id for r in rejected} == {log_c.id}

        pending = await svc.list_by_project(
            db=db_session, project_id=project_id, status="pending"
        )
        assert {r.id for r in pending} == {log_a.id}

    @pytest.mark.asyncio
    async def test_list_by_project_instance_type_filter(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        await svc.create(
            db=db_session,
            **_make_create_kwargs(
                user_id,
                project_id,
                instance_type="workpaper",
                content_hash="1" * 64,
            ),
        )
        await svc.create(
            db=db_session,
            **_make_create_kwargs(
                user_id,
                project_id,
                instance_type="adjustment",
                content_hash="2" * 64,
            ),
        )
        await svc.create(
            db=db_session,
            **_make_create_kwargs(
                user_id,
                project_id,
                instance_type="adjustment",
                content_hash="3" * 64,
            ),
        )
        await db_session.commit()

        wps = await svc.list_by_project(
            db=db_session, project_id=project_id, instance_type="workpaper"
        )
        assert len(wps) == 1

        adjs = await svc.list_by_project(
            db=db_session, project_id=project_id, instance_type="adjustment"
        )
        assert len(adjs) == 2

    @pytest.mark.asyncio
    async def test_list_by_project_invalid_status_raises(
        self, db_session: AsyncSession, user_and_project
    ):
        _, project_id = user_and_project
        with pytest.raises(ValueError):
            await svc.list_by_project(
                db=db_session, project_id=project_id, status="not-a-status"
            )

    @pytest.mark.asyncio
    async def test_list_pending_by_project(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        # 3 pending + 1 confirmed
        pending_ids = []
        for i in range(3):
            log = await svc.create(
                db=db_session,
                **_make_create_kwargs(
                    user_id, project_id, content_hash=f"p{i:0>63}"
                ),
            )
            pending_ids.append(log.id)
        log_done = await svc.create(
            db=db_session,
            **_make_create_kwargs(user_id, project_id, content_hash="d" * 64),
        )
        await db_session.commit()
        await svc.confirm(db=db_session, log_id=log_done.id, user_id=user_id)
        await db_session.commit()

        rows = await svc.list_pending_by_project(
            db=db_session, project_id=project_id
        )
        assert len(rows) == 3
        assert {r.id for r in rows} == set(pending_ids)
        assert all(r.confirm_action == "pending" for r in rows)

    @pytest.mark.asyncio
    async def test_count_pending_by_project(
        self, db_session: AsyncSession, user_and_project
    ):
        user_id, project_id = user_and_project
        # 0 条时应为 0
        assert (
            await svc.count_pending_by_project(db=db_session, project_id=project_id)
        ) == 0

        # 写 4 条，其中 1 条 confirm、1 条 reject、1 条 revise → 仅剩 1 条 pending
        logs = []
        for i in range(4):
            log = await svc.create(
                db=db_session,
                **_make_create_kwargs(
                    user_id, project_id, content_hash=f"x{i:0>63}"
                ),
            )
            logs.append(log)
        await db_session.commit()
        await svc.confirm(db=db_session, log_id=logs[0].id, user_id=user_id)
        await svc.reject(db=db_session, log_id=logs[1].id, user_id=user_id)
        await svc.revise(
            db=db_session,
            log_id=logs[2].id,
            user_id=user_id,
            revised_content="修订后内容",
        )
        await db_session.commit()

        count = await svc.count_pending_by_project(
            db=db_session, project_id=project_id
        )
        assert count == 1


# ---------------------------------------------------------------------------
# 审计日志写入验证
# ---------------------------------------------------------------------------


class TestAuditLog:
    @pytest.mark.asyncio
    async def test_audit_log_written_for_each_action(
        self, db_session: AsyncSession, user_and_project
    ):
        """每次 create/confirm/revise/reject 都写一条 ai_content_lifecycle 审计。"""
        user_id, project_id = user_and_project

        log_a = await svc.create(
            db=db_session, **_make_create_kwargs(user_id, project_id, content_hash="a" * 64)
        )
        log_b = await svc.create(
            db=db_session, **_make_create_kwargs(user_id, project_id, content_hash="b" * 64)
        )
        log_c = await svc.create(
            db=db_session, **_make_create_kwargs(user_id, project_id, content_hash="c" * 64)
        )
        await db_session.commit()

        await svc.confirm(db=db_session, log_id=log_a.id, user_id=user_id)
        await svc.revise(
            db=db_session, log_id=log_b.id, user_id=user_id, revised_content="修订"
        )
        await svc.reject(db=db_session, log_id=log_c.id, user_id=user_id)
        await db_session.commit()

        # 共 6 条 audit_log（3 generate + 1 confirm + 1 revise + 1 reject）
        result = await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.object_type == "ai_content_log"
            )
        )
        entries = list(result.scalars().all())
        assert len(entries) == 6

        actions = sorted(
            (e.payload or {}).get("action") for e in entries if e.payload
        )
        assert actions == ["confirm", "generate", "generate", "generate", "reject", "revise"]

        # 全部 event_type='ai_content_lifecycle'
        for e in entries:
            assert (e.payload or {}).get("event_type") == "ai_content_lifecycle"
            assert (e.payload or {}).get("ai_content_log_id") is not None
            # project_id 由 append_audit_log 自动注入到 payload
            assert (e.payload or {}).get("project_id") == str(project_id)

    @pytest.mark.asyncio
    async def test_audit_log_resource_id_links_to_log(
        self, db_session: AsyncSession, user_and_project
    ):
        """resource_id (object_id) 指向新建的 ai_content_log.id。"""
        user_id, project_id = user_and_project
        log = await svc.create(
            db=db_session, **_make_create_kwargs(user_id, project_id)
        )
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.object_type == "ai_content_log"
            )
        )
        entries = list(result.scalars().all())
        assert len(entries) == 1
        assert entries[0].object_id == log.id
        assert entries[0].action_type == "ai_content_generate"
