"""S-3 v2：高级查询构建器跨表 JOIN 扩展测试

验证：
1. /schema 返回 joins 字段（每张表可关联的目标表清单）
2. trial_balance INNER JOIN wp_index 按 project_id 关联，返回组合行
3. trial_balance LEFT JOIN wp_index：base 表行全保留，未匹配的 wp_index 字段为 NULL
4. fields 双段语法 ``trial_balance.audited_amount`` / ``wp_index.wp_code`` 都可用
5. filters 引用 join 表字段（``wp_index.wp_code = 'D2'``）正确生效
6. 不在 JOIN_WHITELIST 的关联 → 400 JOIN_NOT_REGISTERED
7. join 类型非 inner/left → 400 JOIN_TYPE_NOT_ALLOWED

🔴 2026-08-23 修订（advanced-query-hardening-wiring-closure R6.1）：
``trial_balance -> wp_index`` 的登记已被**移除**。其 ON 仅 ``project_id ↔ project_id``，
两表无业务关系 ⇒ 结果是项目内笛卡尔积（本文件原 ``test_inner_join_trial_balance_wp_index``
的注释即写着「3 条 TB × 2 条 wp_index = 6 行（笛卡儿积，因为 ON 仅 project_id）」——
**明知是笛卡尔积却把它锁为期望值**，属「守卫把错值当基线」）。且 LIMIT 施加在积之后，
PG 仍须物化整个 join 结果，导出路径会把百万行全部拉完。

故本文件涉及该 JOIN 的用例改为：
- 以 ``trial_balance -> account_chart``（含业务键 standard_account_code ↔ account_code）
  验证 JOIN / 双段字段 / join 表过滤 / preview 等原有能力；
- 新增用例断言纯作用域列的 JOIN 被拒绝（``JOIN_MISSING_BUSINESS_KEY`` 登记期不变式
  + 运行期 ``JOIN_NOT_REGISTERED``）。
8. join 目标表不在 TABLE_WHITELIST → 400 JOIN_TABLE_NOT_ALLOWED
9. 字段引用未声明 join 的表 → 400 FIELD_TABLE_NOT_JOINED
10. 多表组合查询：trial_balance + wp_index 复合 ON 条件（account_chart）
11. 聚合 + JOIN：count distinct wp_code per category

Validates: spec proposal-remaining-18 S-3 v2 扩展
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.audit_platform_models import (
    AccountChart,
    AccountCategory,
    TrialBalance,
)
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, User, UserRole
from app.models.workpaper_models import WpIndex
from app.routers.query_builder import router as query_builder_router

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self, role: UserRole = UserRole.admin):
        self.id = USER_ID
        self.role = role
        self.email = "tester@example.com"
        self.username = "tester"
        self.is_active = True


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _make_app(db_session: AsyncSession, role: UserRole = UserRole.admin) -> FastAPI:
    app = FastAPI()
    app.include_router(query_builder_router)

    async def _override_db():
        yield db_session

    async def _override_user():
        return _FakeUser(role=role)

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app


async def _seed_data(db: AsyncSession) -> None:
    db.add(Project(
        id=PROJECT_ID,
        name="JOIN 测试",
        client_name="x",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=USER_ID,
        audit_period_start=date(2025, 1, 1),
        audit_period_end=date(2025, 12, 31),
    ))
    # 2 条 wp_index
    db.add_all([
        WpIndex(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            wp_code="D2",
            wp_name="收入审定表",
            audit_cycle="D",
        ),
        WpIndex(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            wp_code="E1",
            wp_name="货币资金审定表",
            audit_cycle="E",
        ),
    ])
    # 3 条 trial_balance
    db.add_all([
        TrialBalance(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            year=2025,
            company_code="001",
            standard_account_code="1001",
            account_name="库存现金",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("100"),
            audited_amount=Decimal("100"),
        ),
        TrialBalance(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            year=2025,
            company_code="001",
            standard_account_code="1002",
            account_name="银行存款",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("9000"),
            audited_amount=Decimal("9000"),
        ),
        TrialBalance(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            year=2025,
            company_code="001",
            standard_account_code="6001",
            account_name="主营业务收入",
            account_category=AccountCategory.revenue,
            unadjusted_amount=Decimal("50000"),
            audited_amount=Decimal("50000"),
        ),
    ])
    # 3 条 account_chart，与上面 3 条 trial_balance 的科目码一一对应。
    # 这是**含业务键**的 JOIN 目标（standard_account_code ↔ account_code），
    # INNER JOIN 得 1:1 的 3 行，而非笛卡尔积。
    db.add_all([
        AccountChart(
            id=uuid.uuid4(),
            project_id=PROJECT_ID,
            account_code=code,
            account_name=name,
            direction=direction,
            level=1,
            category=category,
            source="manual",
        )
        for code, name, direction, category in (
            ("1001", "库存现金", "debit", "资产"),
            ("1002", "银行存款", "debit", "资产"),
            ("6001", "主营业务收入", "credit", "收入"),
        )
    ])
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# /schema 暴露 joins
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_includes_joins(db_session):
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.get("/api/query/schema")
    assert resp.status_code == 200
    schema = resp.json()
    tables = {t["name"]: t for t in schema["tables"]}
    tb_joins = {j["target_table"] for j in tables["trial_balance"]["joins"]}
    # 含业务键的 join 目标仍在
    assert "account_chart" in tb_joins
    assert "report_line_mapping" in tb_joins
    # 纯 project_id 关联的 wp_index 已移除（R6.1，笛卡尔积）
    assert "wp_index" not in tb_joins
    # account_chart 关联应包含 (project_id, project_id) + (standard_account_code, account_code)
    ac_join = next(j for j in tables["trial_balance"]["joins"] if j["target_table"] == "account_chart")
    assert len(ac_join["on"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# INNER JOIN
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inner_join_trial_balance_account_chart(db_session):
    """含业务键的 INNER JOIN：按科目码 1:1 关联，行数不放大。"""
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "account_chart", "type": "inner"}],
                "fields": [
                    "trial_balance.standard_account_code",
                    "trial_balance.audited_amount",
                    "account_chart.account_name",
                    "account_chart.direction",
                ],
                "filters": [
                    {"field": "trial_balance.project_id", "op": "eq", "value": str(PROJECT_ID)},
                ],
                "limit": 100,
            },
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 3 条 TB ⋈ 3 条 account_chart（按科目码）= 3 行，**不是** 3×3=9 的笛卡尔积
    assert data["total"] == 3
    for r in data["rows"]:
        assert r["account_chart.direction"] in ("debit", "credit")


@pytest.mark.asyncio
async def test_scope_only_join_is_rejected(db_session):
    """纯作用域列（project_id）的 JOIN 不再被接受（R6.1）。

    该登记已从 JOIN_WHITELIST 移除，故运行期报 JOIN_NOT_REGISTERED；
    若有人重新加回，导入期不变式 `_assert_all_joins_have_business_key` 会先失败。
    """
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "wp_index", "type": "inner"}],
                "fields": ["trial_balance.standard_account_code"],
                "limit": 100,
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "JOIN_NOT_REGISTERED"


def test_join_whitelist_has_no_scope_only_registration():
    """登记期不变式：JOIN_WHITELIST 中不存在纯作用域列的 JOIN（R6.1）。"""
    from app.services.custom_query.table_whitelist import (
        JOIN_WHITELIST,
        join_business_keys,
    )

    offending = [
        f"{base} -> {target}"
        for base, targets in JOIN_WHITELIST.items()
        for target, spec in targets.items()
        if not join_business_keys(spec.get("on") or ())
    ]
    assert offending == [], f"存在笛卡尔积风险的 JOIN 登记：{offending}"


@pytest.mark.asyncio
async def test_join_filter_on_joined_table(db_session):
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "account_chart", "type": "inner"}],
                "fields": [
                    "trial_balance.standard_account_code",
                    "account_chart.account_name",
                ],
                "filters": [
                    {"field": "account_chart.account_code", "op": "eq", "value": "1002"},
                ],
                "limit": 100,
            },
        )
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    # 仅匹配 1002 的科目：1 行
    assert len(rows) == 1
    assert rows[0]["account_chart.account_name"] == "银行存款"


# ─────────────────────────────────────────────────────────────────────────────
# LEFT JOIN
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_left_join_returns_null_for_unmatched(db_session):
    """trial_balance LEFT JOIN report_line_mapping：目标表无数据时返回 NULL

    用 report_line_mapping 而非 account_chart：后者已在 `_seed_data` 中 seed
    （见该函数注释，为验证含业务键的 1:1 JOIN 所需），此处需要一个**未 seed** 的
    合法 JOIN 目标才能验证 LEFT JOIN 的 NULL 语义。
    report_line_mapping 的 ON 含业务键 standard_account_code ↔ standard_account_code。
    """
    await _seed_data(db_session)
    # 不 seed report_line_mapping
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "report_line_mapping", "type": "left"}],
                "fields": [
                    "trial_balance.standard_account_code",
                    "report_line_mapping.report_line_name",
                ],
                "limit": 100,
            },
        )
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    # 3 条 TB 全部保留
    assert len(rows) == 3
    # 目标表字段全为 None
    for r in rows:
        assert r["report_line_mapping.report_line_name"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 错误路径
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unregistered_join_returns_400(db_session):
    """trial_balance ↔ materiality 没有预登记 JOIN → 400"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "materiality", "type": "inner"}],
                "fields": ["trial_balance.id"],
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "JOIN_NOT_REGISTERED"


@pytest.mark.asyncio
async def test_invalid_join_type_returns_400(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "wp_index", "type": "right"}],
                "fields": ["trial_balance.id"],
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "JOIN_TYPE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_join_target_not_in_whitelist_returns_400(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [{"table": "users", "type": "inner"}],  # 用户表不在白名单
                "fields": ["trial_balance.id"],
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "JOIN_TABLE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_field_ref_unjoined_table_returns_400(db_session):
    """fields 引用未在 joins 中声明的表 → 400 FIELD_TABLE_NOT_JOINED"""
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "joins": [],  # 没声明任何 join
                "fields": ["wp_index.wp_code"],  # 但引用了 wp_index
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "FIELD_TABLE_NOT_JOINED"


# ─────────────────────────────────────────────────────────────────────────────
# 向后兼容：v1 单段语法仍可用
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_v1_single_segment_syntax_still_works(db_session):
    """无 joins 时单段字段名 'audited_amount' 仍能解析为 base_table.audited_amount"""
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "fields": ["standard_account_code", "audited_amount"],
                "limit": 100,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["total"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# /preview 含 JOIN 的 SQL 预览
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preview_includes_join_sql(db_session):
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/preview",
            json={
                "table": "trial_balance",
                "joins": [{"table": "account_chart", "type": "inner"}],
                "fields": ["trial_balance.id", "account_chart.account_name"],
            },
        )
    assert resp.status_code == 200
    sql = resp.json()["sql"].upper()
    assert "JOIN" in sql
    assert "ACCOUNT_CHART" in sql



# ─────────────────────────────────────────────────────────────────────────────
# 类型 coerce：UUID / Decimal / Date / DateTime / Bool（修复 'str' has no attribute 'hex' bug）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_uuid_filter_str_value_coerced(db_session):
    """前端传 str UUID → 后端 coerce 为 UUID 对象，不再触发 'str' has no attribute 'hex'"""
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "fields": ["standard_account_code"],
                "filters": [
                    {"field": "project_id", "op": "eq", "value": str(PROJECT_ID)},
                ],
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_uuid_in_filter_str_list_coerced(db_session):
    """in 操作符的 str list 中每个 UUID 都正确 coerce"""
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "fields": ["standard_account_code"],
                "filters": [
                    {
                        "field": "project_id",
                        "op": "in",
                        "value": [str(PROJECT_ID), str(uuid.uuid4())],
                    },
                ],
            },
        )
    assert resp.status_code == 200
    # PROJECT_ID 命中 3 条，新生成 UUID 不命中
    assert resp.json()["total"] == 3


@pytest.mark.asyncio
async def test_invalid_uuid_returns_400(db_session):
    """非法 UUID 字符串 → 400 INVALID_UUID（而非 500）"""
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "fields": ["standard_account_code"],
                "filters": [
                    {"field": "project_id", "op": "eq", "value": "not-a-uuid"},
                ],
            },
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "INVALID_UUID"


@pytest.mark.asyncio
async def test_decimal_filter_str_value_coerced(db_session):
    """Decimal 列 filter str value 自动 coerce"""
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "fields": ["standard_account_code", "audited_amount"],
                "filters": [
                    {"field": "audited_amount", "op": "gte", "value": "5000"},
                ],
            },
        )
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    # >= 5000 命中 9000 + 50000 = 2 行
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_decimal_between_str_values_coerced(db_session):
    await _seed_data(db_session)
    app = _make_app(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        resp = await ac.post(
            "/api/query/execute",
            json={
                "table": "trial_balance",
                "fields": ["audited_amount"],
                "filters": [
                    {
                        "field": "audited_amount",
                        "op": "between",
                        "value": ["50", "10000"],
                    },
                ],
            },
        )
    assert resp.status_code == 200
    rows = resp.json()["rows"]
    # 100 + 9000 命中
    assert len(rows) == 2
