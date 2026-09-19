"""``formula_category`` 推导与回填守卫。

公式看板里的「未分类」不是渲染问题，是种子数据 ``formula_category`` 为空
（实测模板级：soe_standalone 38 行 / soe_consolidated 3 行 / listed 两档 0 行）。

本文件锁死三件事：

1. 推导判据 —— 比较算子优先判 ``logic_check``；取数函数判 ``auto_calc``；
   判不准返回 ``None``（**宁缺勿造**：错标 auto_calc 会让「应用自动运算」
   把勾稽校验式拿去当取数执行）；
2. 回填只碰「有公式且分类为空」的行，不动已有分类，也不动无公式的结构行；
3. 幂等：第二次执行 filled=0。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.report_models import FinancialReportType, ReportConfig
from app.services.report_config_service import (
    ReportConfigService,
    derive_formula_category,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

STANDARD = "test_category_standard"
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _row(row_code: str, formula: str | None, category: str | None, n: int) -> ReportConfig:
    return ReportConfig(
        id=uuid.uuid4(),
        report_type=FinancialReportType.balance_sheet,
        row_number=n,
        row_code=row_code,
        row_name=f"行 {row_code}",
        indent_level=0,
        formula=formula,
        formula_category=category,
        applicable_standard=STANDARD,
        is_total_row=False,
    )


# ── 推导判据（纯函数）───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "formula,expected",
    [
        # 实测缺分类行的真实形态：全是取数式
        ("TB('1001','期末余额')", "auto_calc"),
        ("ROW('BS-126') + ROW('BS-127')", "auto_calc"),
        ("TB('6115', '发生额') * -1", "auto_calc"),
        ("(TB('1122','期初余额') - TB('1122','期末余额'))", "auto_calc"),
        ("SUM_TB('10~19','期末余额')", "auto_calc"),
        ("NOTE('货币资金','合计','期末')", "auto_calc"),
        # 勾稽校验：绝不能标成 auto_calc
        ("ROW('BS-100') == ROW('BS-128')", "logic_check"),
        ("REPORT('BS-002','期末') = NOTE('货币资金','合计','期末')", "logic_check"),
        ("ROW('EQ-005') >= 0", "logic_check"),
        # 判不准 → 留空
        ("12345", None),
        ("", None),
        ("   ", None),
    ],
)
def test_derive_formula_category(formula: str, expected: str | None) -> None:
    assert derive_formula_category(formula) == expected


def test_comparison_wins_over_extraction() -> None:
    """既含取数函数又含比较算子 ⇒ 必须判 logic_check（错判会进批量执行链路）。"""
    assert derive_formula_category("TB('1001','期末余额') == ROW('BS-002')") == "logic_check"


# ── 回填行为 ────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    rows = [
        _row("BS-001", "TB('1001','期末余额')", None, 1),          # 待回填 → auto_calc
        _row("BS-002", "ROW('BS-001') == ROW('BS-003')", None, 2),  # 待回填 → logic_check
        _row("BS-003", "TB('1002','期末余额')", "reasonability", 3),  # 已有分类 → 不动
        _row("BS-004", None, None, 4),                              # 无公式 → 不动
        _row("BS-005", "42", None, 5),                              # 判不准 → 留空
    ]
    for r in rows:
        db_session.add(r)
    await db_session.flush()
    return rows


async def _by_code(db_session: AsyncSession) -> dict[str, ReportConfig]:
    result = await db_session.execute(
        sa.select(ReportConfig).where(ReportConfig.applicable_standard == STANDARD)
    )
    return {r.row_code: r for r in result.scalars().all()}


@pytest.mark.asyncio
async def test_backfill_fills_only_missing_and_keeps_undecided_empty(
    db_session: AsyncSession, seeded
):
    svc = ReportConfigService(db_session)

    result = await svc.backfill_formula_categories(applicable_standard=STANDARD)

    assert result["scanned"] == 3, "只扫「有公式且分类为空」的行"
    assert result["filled"] == 2
    assert result["undecided"] == 1
    assert result["by_category"] == {"auto_calc": 1, "logic_check": 1}

    rows = await _by_code(db_session)
    assert rows["BS-001"].formula_category == "auto_calc"
    assert rows["BS-002"].formula_category == "logic_check"
    assert rows["BS-003"].formula_category == "reasonability", "已有分类不得被改写"
    assert rows["BS-004"].formula_category is None
    assert rows["BS-005"].formula_category is None, "判不准必须留空（宁缺勿造）"


@pytest.mark.asyncio
async def test_backfill_is_idempotent(db_session: AsyncSession, seeded):
    svc = ReportConfigService(db_session)

    first = await svc.backfill_formula_categories(applicable_standard=STANDARD)
    second = await svc.backfill_formula_categories(applicable_standard=STANDARD)

    assert first["filled"] == 2
    assert second["filled"] == 0
    assert second["scanned"] == 1, "第二次只剩那条判不准的行"


def test_response_schema_exposes_category_fields() -> None:
    """``ReportConfigRow`` 必须下发分类/说明/来源。

    🔴 回填只改库没用：此前响应模型只有 ``formula``，前端永远收不到
    ``formula_category`` ⇒ 公式看板满屏「未分类」，只能靠客户端兜底补
    ``auto_calc``（于是"改数据"在界面上完全看不出效果，属于典型的不可见写入）。
    """
    from app.models.report_schemas import ReportConfigRow

    fields = set(ReportConfigRow.model_fields)
    for name in ("formula", "formula_category", "formula_description", "formula_source"):
        assert name in fields, f"ReportConfigRow 缺字段：{name}"


@pytest.mark.asyncio
async def test_project_scoped_rows_skipped_by_default(db_session: AsyncSession):
    """项目级行默认不处理（避免一次调用同时改模板级与各项目数据）。"""
    pid = uuid.uuid4()
    row = _row("BS-009", "TB('1001','期末余额')", None, 9)
    row.applicable_standard = f"project:{pid}"
    db_session.add(row)
    await db_session.flush()

    svc = ReportConfigService(db_session)
    skipped = await svc.backfill_formula_categories()
    assert skipped["scanned"] == 0

    included = await svc.backfill_formula_categories(include_project_scoped=True)
    assert included["filled"] == 1
