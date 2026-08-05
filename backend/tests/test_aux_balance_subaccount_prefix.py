"""平台级守卫 —— `get_aux_balance` 一级科目码必须按**前缀**匹配子科目.

## 立项背景（2026-08-04，F0 spec Task 20.2 浏览器实测挖出）

`LedgerPenetrationService.get_aux_balance` 原实现按 `account_code == account_code`
**精确等值**过滤，而账套里辅助余额几乎全部落在子科目上 → 传一级码（`1123`/`2202`/
`1503`/`1519`/`2101`）**一条都查不到**，四个前端消费方全部静默取空：

| 消费方 | 传入科目码 | 用途 |
|--------|-----------|------|
| `coordination/importFromSummary.fetchAuxBalances` | F0-5 `1123` / F0-6 `2202` | 替代程序「期末余额」取账面精确值（R2.3） |
| `g8CrossHelpers` | `1503` | G8 辅助核算取数 |
| `g9CrossHelpers` | `1519`/`1510`/`1504` | G9 辅助核算取数 |
| `g10CrossHelpers` | `2101`/`2102` | G10 辅助核算取数 |

**三方一致的判据（本方法此前是唯一的例外）**：

1. `four_table/aux_aggregation.py` 铁律 3 —— 「账套里科目通常落在子科目
   （`1221.01` / `1221.12` …），故用前缀匹配而非精确等值」
2. 同族端点 `GET /ledger/aux-balance-detail` 早已是这个判据（表达式逐字同款）
3. 全库实测（2026-08-04，10 个项目）：`tb_aux_balance` 落在**子科目 810,884 行**、
   落在**精确四位码仅 1,507 行** → 精确等值漏掉 99.8% 的数据

**为什么四层验证全绿**：既有 `test_ledger_penetration.test_aux_balance` 的 fixture
把 aux 行的 `account_code` 直接写成 `"1122"`（精确四位码），与错误假设同构 →
精确等值下恰好通过。本守卫的 fixture **刻意只放子科目行**，复现真实账套形态。

spec: .kiro/specs/f0-confirmation-linkage-and-structural-enhancement/
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbAuxBalance
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType, ProjectUser, User

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_ENGINE = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

_USER_ID = uuid.uuid4()
_PROJECT_ID = uuid.uuid4()
_YEAR = 2025

#: 真实账套形态：一级码 1123 下**没有** `account_code == '1123'` 的行，
#: 全部落在 `1123.01` / `1123.03`（实测项目 2aa00f57 即如此）
_SUBACCOUNT_ROWS = [
    ("1123.03", "客户", "792827", "重庆航天职业技术学院", Decimal("114800.00")),
    ("1123.03", "客户", "100001", "重庆发展置业管理有限公司", Decimal("115624.16")),
    ("1123.01", "客户", "100002", "某预付货款单位", Decimal("4861.28")),
    # 同名不同科目族：确认前缀限定不会把 2202 的行也捞进来
    ("2202.01", "供应商", "200001", "重庆航天职业技术学院", Decimal("-5000.00")),
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_ENGINE, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession):
    db_session.add(User(
        id=_USER_ID, username="aux-tester", email="aux@test.com",
        hashed_password="x", role="member",
    ))
    db_session.add(Project(
        id=_PROJECT_ID, name="辅助余额子科目前缀守卫", client_name="测试",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=_USER_ID,
    ))
    db_session.add(ProjectUser(
        project_id=_PROJECT_ID, user_id=_USER_ID,
        role="auditor", permission_level="edit", is_deleted=False,
    ))
    for code, aux_type, aux_code, aux_name, closing in _SUBACCOUNT_ROWS:
        db_session.add(TbAuxBalance(
            project_id=_PROJECT_ID, year=_YEAR, company_code="001",
            account_code=code, aux_type=aux_type,
            aux_code=aux_code, aux_name=aux_name,
            opening_balance=Decimal("0"),
            debit_amount=Decimal("0"),
            credit_amount=Decimal("0"),
            closing_balance=closing,
        ))
    await db_session.flush()
    yield db_session


def _svc(db: AsyncSession):
    from app.services.ledger_penetration_service import LedgerPenetrationService
    return LedgerPenetrationService(db)


# ─── Property 1：一级码按前缀命中子科目 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_parent_code_matches_subaccounts(seeded):
    """传一级码 `1123` 必须命中 `1123.01` + `1123.03` 的全部行。"""
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "1123")
    assert len(rows) == 3, "一级码应命中 1123.01/1123.03 共 3 行"
    codes = {r["account_code"] for r in rows}
    assert codes == {"1123.01", "1123.03"}


@pytest.mark.asyncio
async def test_parent_code_does_not_leak_other_account_family(seeded):
    """前缀限定不得把别的科目族（2202）捞进来 —— 即便 aux_name 同名。"""
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "1123")
    assert all(str(r["account_code"]).startswith("1123") for r in rows)
    names = [r["aux_name"] for r in rows]
    # 「重庆航天职业技术学院」在 2202.01 也有一行，前缀限定后只应出现 1123 那一条
    assert names.count("重庆航天职业技术学院") == 1


@pytest.mark.asyncio
async def test_target_entity_balance_is_the_subaccount_value(seeded):
    """核心业务断言：F0-5 用 `1123` 取「重庆航天职业技术学院」应得 114,800.00。

    修复前得 `[]` → `matchAuxBalance` 返 undefined → 替代程序期末余额回退成
    汇总表「发函金额」（浏览器实测落库 `closing_balance: 1000`，而非账面 114,800）。
    """
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "1123")
    hit = [r for r in rows if r["aux_name"] == "重庆航天职业技术学院"]
    assert len(hit) == 1
    assert float(hit[0]["closing_balance"]) == pytest.approx(114800.00, abs=0.01)


# ─── Property 2：子科目码仍按精确等值（不放宽）────────────────────────────────

@pytest.mark.asyncio
async def test_subaccount_code_stays_exact(seeded):
    """含点号的子科目码按精确等值 —— 传 `1123.01` 不得命中 `1123.03`。"""
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "1123.01")
    assert len(rows) == 1
    assert rows[0]["account_code"] == "1123.01"
    assert rows[0]["aux_name"] == "某预付货款单位"


@pytest.mark.asyncio
async def test_unknown_code_returns_empty(seeded):
    """不存在的科目码返空（区分「无此科目」与「余额为 0」由调用方处理）。"""
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "9999")
    assert rows == []


# ─── Property 3：aux_type 过滤仍生效 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_aux_type_filter_still_applies(seeded):
    """前缀改造不得破坏既有 `aux_type` 过滤。"""
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "1123", aux_type="客户")
    assert len(rows) == 3
    assert await _svc(seeded).get_aux_balance(
        _PROJECT_ID, _YEAR, "1123", aux_type="供应商",
    ) == []


# ─── Property 4：投影必须带 account_code（前端 accountPrefix 限定依赖它）──────

@pytest.mark.asyncio
async def test_projection_exposes_account_code(seeded):
    """返回行必须含 `account_code`。

    前端 `matchAuxBalance(entityName, auxRows, accountPrefix)` 用它做科目前缀
    限定（`r.accountCode.startsWith(accountPrefix)`）。前缀匹配后返回的是子科目码，
    若不投影该列，`fetchAuxBalances` 会回退成「传入的一级码」，
    F0-5 传 `1123` 恰好仍能通过，但 G9/G10 的多别名场景会张冠李戴。
    """
    rows = await _svc(seeded).get_aux_balance(_PROJECT_ID, _YEAR, "1123")
    assert rows and all("account_code" in r for r in rows)


# ─── 反向自检：复现旧行为必须打红 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reverse_selfcheck_exact_equality_would_return_nothing(seeded):
    """反向自检 —— 用旧的精确等值谓词直查，必须返回 0 行。

    这条钉死「本守卫真的在测前缀匹配」：若哪天有人把实现改回精确等值，
    上面 Property 1~4 会红，而本条会绿 —— 两者互为旁证。
    """
    tbl = TbAuxBalance.__table__
    legacy_rows = (
        await seeded.execute(
            sa.select(sa.func.count()).select_from(tbl).where(
                tbl.c.project_id == _PROJECT_ID,
                tbl.c.year == _YEAR,
                tbl.c.account_code == "1123",  # 旧谓词
            )
        )
    ).scalar()
    assert legacy_rows == 0, (
        "fixture 必须只含子科目行（复现真实账套形态）；"
        "若这里 > 0 说明 fixture 被改成精确四位码，守卫将退化为空转"
    )


@pytest.mark.asyncio
async def test_reverse_selfcheck_source_uses_prefix_predicate():
    """源码级自检：实现里必须存在前缀谓词，且注释说明未被删。"""
    import inspect
    from app.services.ledger_penetration_service import LedgerPenetrationService

    src = inspect.getsource(LedgerPenetrationService.get_aux_balance)
    assert ".like(account_code" in src, "一级科目码必须按前缀匹配"
    assert '"." in account_code' in src, "含点号的子科目码必须保持精确等值"


# ─── 同族端点一致性：判据只许有一份 ───────────────────────────────────────────

def test_sibling_endpoint_uses_same_predicate():
    """`aux-balance-detail` 与本方法必须是同一个判据（防两处漂移）。"""
    from pathlib import Path

    router = Path(__file__).resolve().parents[1] / "app" / "routers" / "ledger_penetration.py"
    src = router.read_text(encoding="utf-8")
    # 同族端点早已是「无点号→前缀 / 有点号→等值」
    assert "like(account_code + '%')" in src or 'like(account_code + "%")' in src, (
        "aux-balance-detail 的前缀判据不见了 —— 两处判据必须一致，"
        "改一处必须同步另一处"
    )
