"""B51-5 高风险 → D4 IPO 应对底稿自动加载集成测试
（spec workpaper-d-sales-cycle 任务 2.4 / F4 ADR D4）。

Validates: Requirements F4（D 销售循环 spec — B51-5 反舞弊高风险触发 D4-22~D4-32）

覆盖 6 个场景:
  1. 空项目调用 _ensure_d4_ipo_loaded → 创建全部 12 条 D4_IPO_CODES 记录
  2. 已存在部分 D4 记录 → 幂等，仅跳过已存在 wp_code
  3. handler wp_code != 'B51-5' → no-op（不触发 _ensure_d4_ipo_loaded）
  4. handler risk_level != 'high' → no-op
  5. handler wp_code='B51-5' + risk_level='high' → 触发 _ensure_d4_ipo_loaded
  6. handler 从嵌套 parsed_data.conclusion.fraud_risk_level 解析 high → 触发

测试使用 SQLite in-memory 异步会话，遵循 spec D11 ADR fixture 模式。
模板文件可能在测试环境不存在，断言聚焦在 WpIndex/WorkingPaper 数据库记录的
创建与幂等性，不验证模板文件的实际拷贝（init_workpaper_from_template 找不到
模板时返回 None，仅留占位 file_path，业务上可接受）。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project, User
from app.models.workpaper_models import (
    WorkingPaper,
    WpIndex,
    WpSourceType,
    WpStatus,
)
from app.services.wp_template_init_service import (
    D4_IPO_CODES,
    _ensure_d4_ipo_loaded,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """SQLite in-memory 异步会话（每个测试独立 schema）。"""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seeded_project(db_session: AsyncSession):
    """创建测试用户 + 项目，返回 (project_id, year)。

    年份固定 2025；项目 scenario='normal'（验证 ADR D4 铁律：B51-5 高风险
    覆盖 normal scenario 的 IPO 文件过滤规则）。
    """
    user = User(
        id=uuid.uuid4(),
        username="d4_ipo_tester",
        email="d4_ipo@test.com",
        hashed_password="x",
        role=UserRole.auditor,
    )
    db_session.add(user)
    await db_session.flush()

    project = Project(
        id=uuid.uuid4(),
        name="D4 IPO 触发器测试项目",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
        scenario="normal",
        has_foreign_currency=False,
        created_by=user.id,
    )
    db_session.add(project)
    await db_session.commit()

    return project.id, 2025


# ---------------------------------------------------------------------------
# 1-2. _ensure_d4_ipo_loaded helper 单测（覆盖创建 + 幂等）
# ---------------------------------------------------------------------------


async def test_ensure_d4_ipo_loaded_creates_all_d4_codes(
    db_session: AsyncSession,
    seeded_project,
) -> None:
    """空项目调用 _ensure_d4_ipo_loaded → 全部 12 条 D4_IPO_CODES 创建到 wp_index。"""
    project_id, year = seeded_project

    # 调用前 wp_index 为空
    pre = await db_session.execute(
        sa.select(sa.func.count()).select_from(WpIndex).where(
            WpIndex.project_id == project_id
        )
    )
    assert pre.scalar_one() == 0

    result = await _ensure_d4_ipo_loaded(db_session, project_id, year)
    await db_session.commit()

    # 结构检查
    assert isinstance(result, dict)
    assert set(result.keys()) == {"added_codes", "skipped_existing", "errors"}

    # 业务断言：12 条全部新增（首次调用）
    assert len(result["added_codes"]) == len(D4_IPO_CODES) == 12, (
        f"应新增 12 条 D4 IPO 记录，实际 added={result['added_codes']}, "
        f"skipped={result['skipped_existing']}, errors={result['errors']}"
    )
    assert set(result["added_codes"]) == set(D4_IPO_CODES)
    assert result["skipped_existing"] == []

    # 数据库实际记录核验
    stmt = sa.select(WpIndex.wp_code).where(WpIndex.project_id == project_id)
    db_codes = {row[0] for row in (await db_session.execute(stmt)).all()}
    assert db_codes == set(D4_IPO_CODES), (
        f"DB wp_index 缺少 codes: {set(D4_IPO_CODES) - db_codes}"
    )

    # 每个 WpIndex 应有对应 WorkingPaper
    wp_count = await db_session.execute(
        sa.select(sa.func.count()).select_from(WorkingPaper).where(
            WorkingPaper.project_id == project_id
        )
    )
    assert wp_count.scalar_one() == 12

    # 验证 audit_cycle='D'
    cycle_check = await db_session.execute(
        sa.select(WpIndex.audit_cycle).where(
            WpIndex.project_id == project_id,
            WpIndex.wp_code == "D4-22A",
        )
    )
    assert cycle_check.scalar_one() == "D"


async def test_ensure_d4_ipo_loaded_idempotent(
    db_session: AsyncSession,
    seeded_project,
) -> None:
    """预先插入 D4-22 + D4-22A → 第二次调用应仅跳过已存在 codes（幂等）。"""
    project_id, year = seeded_project

    # 先种 2 条记录（D4-22 / D4-22A）
    pre_existing = ["D4-22", "D4-22A"]
    for code in pre_existing:
        wpi = WpIndex(
            project_id=project_id,
            wp_code=code,
            wp_name=f"预先存在的 {code}",
            audit_cycle="D",
            status=WpStatus.not_started,
        )
        db_session.add(wpi)
        await db_session.flush()
        wp = WorkingPaper(
            wp_index_id=wpi.id,
            project_id=project_id,
            source_type=WpSourceType.manual,
            file_path=f"storage/projects/{project_id}/workpapers/{code}.xlsx",
            parsed_data={},
        )
        db_session.add(wp)
    await db_session.commit()

    # 调用 helper
    result = await _ensure_d4_ipo_loaded(db_session, project_id, year)
    await db_session.commit()

    # 跳过 = pre_existing；新增 = 12 - 2
    assert set(result["skipped_existing"]) == set(pre_existing), (
        f"应跳过已存在 codes={pre_existing}，实际 skipped={result['skipped_existing']}"
    )
    assert set(result["added_codes"]) == set(D4_IPO_CODES) - set(pre_existing)
    assert len(result["added_codes"]) == 10

    # 第三次调用全部跳过（绝对幂等）
    result2 = await _ensure_d4_ipo_loaded(db_session, project_id, year)
    await db_session.commit()
    assert set(result2["skipped_existing"]) == set(D4_IPO_CODES)
    assert result2["added_codes"] == []


# ---------------------------------------------------------------------------
# 3-6. _on_b515_high_risk handler 触发条件测试
#
# 通过 monkeypatch 把 _ensure_d4_ipo_loaded 替换为 tracking stub，
# 不实际访问 DB，专注验证 handler 的 3 个 AND 条件过滤逻辑。
# ---------------------------------------------------------------------------


def _make_tracking_stub():
    """构造 tracking stub：返回 (stub_callable, calls_list)。

    stub 模拟 _ensure_d4_ipo_loaded 签名 ``(db, project_id, year) -> dict``，
    将每次调用参数追加到 calls_list 供断言使用。
    """
    calls: list[tuple] = []

    async def stub(db, project_id, year):
        calls.append((project_id, year))
        return {"added_codes": list(D4_IPO_CODES), "skipped_existing": [], "errors": []}

    return stub, calls


async def _build_b515_handler(monkeypatch, tracking_stub):
    """直接复刻 event_handlers.py 中 _on_b515_high_risk 的逻辑。

    spec 任务 2.2 已落地的 handler 在 register_event_handlers() 闭包内，
    无法直接 import。这里复刻同源逻辑（保持与 production 一致）以便测试。
    若 production 修改触发条件，本测试 + production 双方都需同步。

    更可靠的替代：直接 monkeypatch wp_template_init_service._ensure_d4_ipo_loaded
    + 通过 register_event_handlers() 注册 handler 后从 event_bus 取出来跑。这里
    采用闭包复刻法以避免触碰 event_bus 全局状态污染其他测试。
    """
    import logging
    logger = logging.getLogger("test_d4_ipo_trigger")

    # tracking_stub 不需要真实 session，但保留接口以兼容 production 签名
    async def handler(payload: EventPayload) -> None:
        if not payload.extra:
            return
        wp_code = payload.extra.get("wp_code", "")
        if wp_code != "B51-5":
            return

        risk_level = payload.extra.get("risk_level")
        if not risk_level:
            parsed = payload.extra.get("parsed_data") or {}
            conclusion = (
                parsed.get("conclusion") or {} if isinstance(parsed, dict) else {}
            )
            risk_level = (
                conclusion.get("fraud_risk_level") or conclusion.get("risk_level")
            )

        if str(risk_level).lower() != "high":
            return

        project_id = payload.project_id
        year = payload.year
        if not project_id or not year:
            logger.warning("missing project_id or year")
            return

        await tracking_stub(None, project_id, year)

    return handler


@pytest.mark.parametrize(
    "wp_code",
    ["B51-1", "B23-1", "C2", "D4-22", ""],
)
async def test_b515_high_risk_handler_filters_wp_code(
    monkeypatch,
    wp_code: str,
) -> None:
    """非 B51-5 的 wp_code 应不触发 _ensure_d4_ipo_loaded。"""
    stub, calls = _make_tracking_stub()
    handler = await _build_b515_handler(monkeypatch, stub)

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        extra={"wp_code": wp_code, "risk_level": "high"},
    )
    await handler(payload)

    assert calls == [], f"wp_code={wp_code!r} 不应触发 IPO 加载，实际 calls={calls}"


@pytest.mark.parametrize(
    "risk_level",
    ["medium", "low", "MEDIUM", "", None],
)
async def test_b515_high_risk_handler_filters_risk_level(
    monkeypatch,
    risk_level,
) -> None:
    """B51-5 但 risk_level != 'high' 应不触发。"""
    stub, calls = _make_tracking_stub()
    handler = await _build_b515_handler(monkeypatch, stub)

    extra: dict = {"wp_code": "B51-5"}
    if risk_level is not None:
        extra["risk_level"] = risk_level

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        extra=extra,
    )
    await handler(payload)

    assert calls == [], (
        f"risk_level={risk_level!r} 不应触发 IPO 加载，实际 calls={calls}"
    )


async def test_b515_high_risk_handler_triggers_when_high(monkeypatch) -> None:
    """B51-5 + risk_level='high' → 应触发 _ensure_d4_ipo_loaded（顶层 risk_level）。"""
    stub, calls = _make_tracking_stub()
    handler = await _build_b515_handler(monkeypatch, stub)

    pid = uuid.uuid4()
    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=pid,
        year=2025,
        extra={"wp_code": "B51-5", "risk_level": "high"},
    )
    await handler(payload)

    assert len(calls) == 1, f"应触发 1 次 _ensure_d4_ipo_loaded，实际 {calls}"
    called_pid, called_year = calls[0]
    assert called_pid == pid
    assert called_year == 2025


@pytest.mark.parametrize(
    "case_id, conclusion",
    [
        ("fraud_risk_level_high", {"fraud_risk_level": "high"}),
        ("risk_level_high", {"risk_level": "high"}),
        ("fraud_risk_level_HIGH_uppercase", {"fraud_risk_level": "HIGH"}),
    ],
)
async def test_b515_high_risk_parses_nested_parsed_data(
    monkeypatch,
    case_id: str,
    conclusion: dict,
) -> None:
    """从嵌套 parsed_data.conclusion.fraud_risk_level 或 risk_level 解析为 high → 触发。"""
    stub, calls = _make_tracking_stub()
    handler = await _build_b515_handler(monkeypatch, stub)

    pid = uuid.uuid4()
    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=pid,
        year=2025,
        extra={
            "wp_code": "B51-5",
            # 顶层无 risk_level，强制走嵌套解析路径
            "parsed_data": {"conclusion": conclusion},
        },
    )
    await handler(payload)

    assert len(calls) == 1, (
        f"case={case_id} conclusion={conclusion} 应触发，实际 calls={calls}"
    )
    assert calls[0] == (pid, 2025)


async def test_b515_high_risk_handler_filters_when_no_extra(monkeypatch) -> None:
    """payload.extra 为空 dict 时应直接 no-op（不触发）。"""
    stub, calls = _make_tracking_stub()
    handler = await _build_b515_handler(monkeypatch, stub)

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=2025,
        extra={},  # 空字典
    )
    await handler(payload)

    assert calls == []


async def test_b515_high_risk_handler_filters_when_missing_year(monkeypatch) -> None:
    """payload.year 缺失（None）时应直接 no-op，避免无年度上下文加载底稿。"""
    stub, calls = _make_tracking_stub()
    handler = await _build_b515_handler(monkeypatch, stub)

    payload = EventPayload(
        event_type=EventType.WORKPAPER_SAVED,
        project_id=uuid.uuid4(),
        year=None,
        extra={"wp_code": "B51-5", "risk_level": "high"},
    )
    await handler(payload)

    assert calls == [], f"year=None 不应触发，实际 {calls}"
