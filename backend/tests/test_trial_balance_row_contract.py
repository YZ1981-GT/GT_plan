"""试算表列表端点行契约（spec post-push-residual-defect-closure R1）。

真发请求（mini app + SQLite 真 ORM 行）：
* 年度省略 ⇒ 按项目审计年度；项目没填 ⇒ 422 中文原因；
* ``account_prefix`` 逗号分隔按标准科目码前缀筛；
* ``include_movement`` 本期借 / 贷 = 叶子汇总（父子不双计、未映射子科目继承父科目映射）；
* ``include_prior`` 上年审定数取同项目上年试算表，取不到为 null；
* 行键集合 == 前端唯一入口 ``services/trialBalanceRows.ts`` 的 ``TrialBalanceRow``（跨语言契约，
  可选键只在对应开关下出现）。原先前端读了 20 多种端点从不返回的字段（debit_amount / ending_balance /
  prior_* …）⇒ 静默得 0。
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.core.redis import get_redis
from app.deps import get_current_user
from app.models.audit_platform_models import AccountCategory, AccountMapping, TbBalance, TrialBalance
from app.models.base import Base, UserRole
from app.models.core import Project
from app.routers import trial_balance as tb_router
from app.services.ledger_import.sign_convention_guard import SignConventionReadinessResult

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TS_ROW_FILE = Path(__file__).resolve().parents[2] / "audit-platform" / "frontend" / "src" / "services" / "trialBalanceRows.ts"
OPTIONAL_BY_FLAG = {"include_movement": {"period_debit", "period_credit"}, "include_prior": {"prior_audited_amount"}}


def _ts_row_keys() -> tuple[set[str], set[str]]:
    """解析 ``export interface TrialBalanceRow { ... }`` → (必有键, 可选键)。"""
    src = TS_ROW_FILE.read_text(encoding="utf-8")
    body = re.search(r"export interface TrialBalanceRow\s*\{(?P<body>.*?)\n\}", src, re.S)
    assert body, "trialBalanceRows.ts 里找不到 TrialBalanceRow"
    required, optional = set(), set()
    for m in re.finditer(r"^\s{2}(?P<key>\w+)(?P<opt>\?)?\s*:", body.group("body"), re.M):
        (optional if m.group("opt") else required).add(m.group("key"))
    return required, optional


class _User:
    def __init__(self):
        self.id = uuid.uuid4()
        self.username = "tb_contract"
        self.email = "tb@test.com"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False


class _Redis:
    """CacheService 只用 get / set（过期参数忽略）。"""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value


@pytest_asyncio.fixture
async def env(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis = _Redis()

    async def _ready(*_a, **_k):
        return SignConventionReadinessResult(ready=True, has_legacy=False)

    monkeypatch.setattr(tb_router, "check_sign_convention_readiness", _ready)
    async with factory() as db:
        pid, empty_pid = uuid.uuid4(), uuid.uuid4()
        db.add_all([
            Project(id=pid, name="【测试】试算表契约_2025", client_name="契约测试", audit_year=2025),
            Project(id=empty_pid, name="【测试】无年度", client_name="契约测试"),
        ])
        published = datetime(2026, 10, 1, tzinfo=timezone.utc)
        tb = [  # (年度, 科目, 类别, 未审, 审定, 期初)
            (2025, "1122", AccountCategory.asset, "1000", "1100", "800"),
            (2025, "112201", AccountCategory.asset, "10", "10", "0"),
            (2025, "2211", AccountCategory.liability, "300", "300", "250"),
            (2025, "221101", AccountCategory.liability, "30", "30", "0"),
            (2025, "6001", AccountCategory.revenue, "500", "520", None),
            (2025, "6601", AccountCategory.expense, "200", "200", None),
            (2024, "1122", AccountCategory.asset, "800", "800", "600"),
            (2024, "6001", AccountCategory.revenue, "450", "460", None),
        ]
        for year, code, cat, unadj, aud, opening in tb:
            db.add(TrialBalance(
                project_id=pid, year=year, company_code="001", standard_account_code=code, account_name=code,
                account_category=cat, unadjusted_amount=Decimal(unadj), audited_amount=Decimal(aud),
                opening_balance=Decimal(opening) if opening else None,
                wp_adjustment=Decimal("100") if (year, code) == (2025, "1122") else Decimal("0"),
                wp_publish_base=Decimal("1000") if (year, code) == (2025, "1122") else None,
                wp_published_at=published if (year, code) == (2025, "1122") else None,
            ))
        # 余额表：1122 父级 + 两个子级（子级未映射，继承父级）；父级不计入（叶子口径）。
        # 2211 下 2211.01 自有映射 → 221101（最长前缀：用自身映射，不归父级），2211.02 未映射 → 继承 2211
        for code, dr, cr in (("1122", "900", "200"), ("1122.01", "600", "150"), ("1122.02", "300", "50"),
                             ("2211", "250", "300"), ("2211.01", "40", "10"), ("2211.02", "60", "20")):
            db.add(TbBalance(project_id=pid, year=2025, company_code="001", account_code=code, account_name=code,
                             debit_amount=Decimal(dr), credit_amount=Decimal(cr), closing_balance=Decimal("0")))
        for original, standard in (("1122", "1122"), ("2211", "2211"), ("2211.01", "221101")):
            db.add(AccountMapping(project_id=pid, original_account_code=original, standard_account_code=standard,
                                  mapping_type="manual"))
        await db.commit()

        app = FastAPI()
        app.include_router(tb_router.router)

        async def _db():
            yield db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: _User()
        app.dependency_overrides[get_redis] = lambda: redis
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, pid, empty_pid, redis
    await engine.dispose()


def _rows(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    return body if isinstance(body, list) else body["data"]


async def test_year_omitted_uses_project_audit_year(env):
    client, pid, _empty, _redis = env
    rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance"))
    assert {r["standard_account_code"] for r in rows} == {"1122", "112201", "2211", "221101", "6001", "6601"}
    explicit = _rows(await client.get(f"/api/projects/{pid}/trial-balance", params={"year": 2024}))
    assert {r["standard_account_code"] for r in explicit} == {"1122", "6001"}


async def test_project_without_audit_year_is_422_with_reason(env):
    client, _pid, empty, _redis = env
    resp = await client.get(f"/api/projects/{empty}/trial-balance")
    assert resp.status_code == 422 and "未设置审计年度" in resp.text


async def test_account_prefix_filters_by_standard_code_prefix(env):
    client, pid, _empty, _redis = env
    rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance", params={"account_prefix": "1122, 66"}))
    assert sorted(r["standard_account_code"] for r in rows) == ["1122", "112201", "6601"]


async def test_movement_is_leaf_rollup_without_parent_double_count(env):
    client, pid, _empty, _redis = env
    rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance", params={"include_movement": "true"}))
    by = {r["standard_account_code"]: (Decimal(r["period_debit"]), Decimal(r["period_credit"])) for r in rows}
    assert by["1122"] == (Decimal(900), Decimal(200)), "子级合计；父级行不得再加一遍"
    assert by["2211"] == (Decimal(60), Decimal(20)), "只含继承父级映射的 2211.02；2211.01 有自己的映射"
    assert by["221101"] == (Decimal(40), Decimal(10)), "子科目有自己的映射时按自身映射（最长前缀）"
    assert by["6601"] == (Decimal(0), Decimal(0)), "余额表没有的科目给 0"


async def test_prior_audited_amount_from_prior_year_or_null(env):
    client, pid, _empty, _redis = env
    rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance", params={"include_prior": "true"}))
    by = {r["standard_account_code"]: r for r in rows}
    assert Decimal(by["1122"]["prior_audited_amount"]) == Decimal(800)
    assert Decimal(by["6001"]["prior_audited_amount"]) == Decimal(460)
    assert by["2211"]["prior_audited_amount"] is None, "上年没有该科目 ⇒ null，不代入 0"


async def test_wp_publish_columns_are_returned(env):
    client, pid, _empty, _redis = env
    rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance"))
    row = next(r for r in rows if r["standard_account_code"] == "1122")
    assert Decimal(row["wp_adjustment"]) == Decimal(100) and Decimal(row["wp_publish_base"]) == Decimal(1000)
    assert row["wp_published_at"].startswith("2026-10-01")


async def test_cached_response_still_applies_prefix_and_extras(env):
    client, pid, _empty, redis = env
    await client.get(f"/api/projects/{pid}/trial-balance")
    assert redis.store, "首次请求应写缓存"
    rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance",
                                  params={"account_prefix": "2211", "include_movement": "true"}))
    assert sorted(r["standard_account_code"] for r in rows) == ["2211", "221101"]
    assert all("period_debit" in r for r in rows)
    full = _rows(await client.get(f"/api/projects/{pid}/trial-balance"))
    assert "period_debit" not in full[0], "附加字段不得写回缓存里的全量行"


async def test_row_keys_match_frontend_trial_balance_row(env):
    client, pid, _empty, _redis = env
    required, optional = _ts_row_keys()
    assert optional == set().union(*OPTIONAL_BY_FLAG.values()), "可选键应恰为各开关附加的字段"
    base = _rows(await client.get(f"/api/projects/{pid}/trial-balance"))
    assert set(base[0]) == required
    for flag, extra in OPTIONAL_BY_FLAG.items():
        rows = _rows(await client.get(f"/api/projects/{pid}/trial-balance", params={flag: "true"}))
        assert set(rows[0]) == required | extra, flag
