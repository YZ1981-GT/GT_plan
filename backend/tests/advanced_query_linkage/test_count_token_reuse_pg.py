"""计数凭证真 PG 回归（platform-performance-user-experience-closure 任务 11；需求 R3.4，design §5.2）。

回滚事务里建一个【测试】项目：生效数据集 25 行辅助明细（银行账户 15、现金 10）+ 3 行已删 + 已替代数据集 4 行。
请求经生产注册的 custom_query / query_builder router 真发，观测面是驱动层真正发出的 SQL（``before_cursor_execute``）：

- 第 1 页 COUNT 一次、total 精确、签发凭证；带凭证翻页 ``count_reused=true`` 且一条 COUNT 都不发，行不重不漏；
- 篡改凭证、换了筛选、换了用户、切换生效数据集 ⇒ 凭证失效，照常 COUNT，total 按新口径精确。

真实项目只读、不碰；夹具结束整体回滚，Redis 与审计写入换成独占替身（见 ``business_client`` / ``builder_client``）。
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.models.audit_platform_models import TbAuxLedger
from app.models.base import ProjectStatus, UserRole
from app.models.core import Project, User
from app.models.dataset_models import DatasetStatus, LedgerDataset
from tests.advanced_query_linkage.gold import AUDIT_YEAR

pytestmark = pytest.mark.pg_only

_COUNT = re.compile(r"\bcount\(\*\)", re.IGNORECASE)
_PAGE = 10


async def _seed(session) -> dict[str, uuid.UUID]:
    """回滚事务：【测试】项目 + 生效 / 已替代两个数据集与辅助明细行。"""
    pid = uuid.uuid4()
    session.add(Project(id=pid, name="【测试】计数凭证翻页", client_name="【测试】计数凭证翻页",
                        status=ProjectStatus.execution, template_type="listed", report_scope="standalone",
                        audit_year=AUDIT_YEAR, scenario="normal"))
    await session.flush()
    t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    active = LedgerDataset(project_id=pid, year=AUDIT_YEAR, status=DatasetStatus.active, activated_at=t0)
    old = LedgerDataset(project_id=pid, year=AUDIT_YEAR, status=DatasetStatus.superseded,
                        activated_at=t0 - dt.timedelta(days=1))
    session.add_all([active, old])
    await session.flush()

    def row(i: int, dataset_id: uuid.UUID, aux_type: str, *, deleted: bool = False) -> TbAuxLedger:
        return TbAuxLedger(project_id=pid, year=AUDIT_YEAR, company_code="PPUX", account_code="1002",
                           voucher_date=dt.date(AUDIT_YEAR, 1 + i % 12, 1), voucher_no=f"PPUX-{i:03d}",
                           aux_type=aux_type, aux_code=f"A{i:03d}", aux_name=f"A{i:03d}",
                           debit_amount=Decimal("1.00"), summary="【测试】计数凭证回滚事务造行",
                           dataset_id=dataset_id, is_deleted=deleted)

    session.add_all([row(i, active.id, "银行账户" if i < 15 else "现金") for i in range(25)])
    session.add_all([row(100 + i, active.id, "银行账户", deleted=True) for i in range(3)])
    session.add_all([row(200 + i, old.id, "银行账户") for i in range(4)])
    await session.flush()
    return {"project": pid, "active": active.id, "old": old.id}


@contextmanager
def _counts(sync_conn) -> Iterator[list[str]]:
    """记下本段内驱动层发出的、针对辅助明细的 COUNT 语句。"""
    seen: list[str] = []

    def _capture(_conn, _cursor, statement, _params, _context, _executemany) -> None:
        if _COUNT.search(statement) and "tb_aux_ledger" in statement:
            seen.append(statement)

    event.listen(sync_conn, "before_cursor_execute", _capture)
    try:
        yield seen
    finally:
        event.remove(sync_conn, "before_cursor_execute", _capture)


def _tamper(token: str) -> str:
    return token[:-1] + ("A" if token[-1] != "A" else "B")


async def _sync_conn(session):
    return (await session.connection()).sync_connection


async def test_business_view_pages_reuse_exact_total_without_count(business) -> None:
    ids = await _seed(business.session)
    sync_conn = await _sync_conn(business.session)
    pid, body = ids["project"], {"filters": {"account_code": "1002"}, "limit": _PAGE}

    with _counts(sync_conn) as first_counts:
        first = await business.ok(pid, "aux_ledger", offset=0, **body)
    assert (first["total"], first["count_reused"], len(first_counts)) == (25, False, 1)
    assert first["count_token"]

    seen = [r["id"] for r in first["rows"]]
    token = first["count_token"]
    for offset, expected_rows in ((10, 10), (20, 5)):
        with _counts(sync_conn) as later_counts:
            data = await business.ok(pid, "aux_ledger", offset=offset, count_token=token, **body)
        assert (data["total"], data["count_reused"], later_counts) == (25, True, []), offset
        assert len(data["rows"]) == expected_rows
        seen.extend(r["id"] for r in data["rows"])
        token = data["count_token"]
    assert len(seen) == len(set(seen)) == 25, "三页不重不漏"


async def test_business_view_tampered_or_foreign_token_recounts(business) -> None:
    ids = await _seed(business.session)
    sync_conn = await _sync_conn(business.session)
    pid = ids["project"]
    first = await business.ok(pid, "aux_ledger", filters={"account_code": "1002"}, limit=_PAGE)
    token = first["count_token"]

    with _counts(sync_conn) as counts:
        tampered = await business.ok(pid, "aux_ledger", filters={"account_code": "1002"}, limit=_PAGE,
                                     offset=10, count_token=_tamper(token))
    assert (tampered["total"], tampered["count_reused"], len(counts)) == (25, False, 1)

    with _counts(sync_conn) as counts:
        narrowed = await business.ok(pid, "aux_ledger", filters={"account_code": "1002", "aux_type": "银行账户"},
                                     limit=_PAGE, offset=10, count_token=token)
    assert (narrowed["total"], narrowed["count_reused"], len(counts)) == (15, False, 1), "换了筛选就重新计数"


async def test_business_view_dataset_switch_invalidates_token(business) -> None:
    ids = await _seed(business.session)
    sync_conn = await _sync_conn(business.session)
    pid = ids["project"]
    first = await business.ok(pid, "aux_ledger", filters={"account_code": "1002"}, limit=_PAGE)
    assert first["total"] == 25

    active = await business.session.get(LedgerDataset, ids["active"])
    old = await business.session.get(LedgerDataset, ids["old"])
    active.status = DatasetStatus.superseded
    await business.session.flush()  # 每个项目年度只许一个生效数据集（uq_ledger_datasets_one_active）：先退旧的
    old.status = DatasetStatus.active
    old.activated_at = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
    await business.session.flush()

    with _counts(sync_conn) as counts:
        data = await business.ok(pid, "aux_ledger", filters={"account_code": "1002"}, limit=_PAGE, offset=10,
                                 count_token=first["count_token"])
    assert (data["total"], data["count_reused"], len(counts)) == (4, False, 1), "生效数据集变了，旧 total 不得沿用"


async def test_builder_token_is_bound_to_the_issuing_user(builder) -> None:
    ids = await _seed(builder.session)
    sync_conn = await _sync_conn(builder.session)
    query = {"table": "tb_aux_ledger", "project_id": str(ids["project"]), "year": AUDIT_YEAR,
             "fields": ["tb_aux_ledger.aux_code"], "limit": _PAGE}
    first = await builder.ok(builder.admin, {**query, "offset": 0})
    assert (first["total"], first["count_reused"]) == (25, False) and first["count_token"]

    other = User(id=uuid.uuid4(), username="ppux-admin-2", email="ppux-admin-2@test.invalid", hashed_password="x",
                 role=UserRole.admin, is_active=True)
    with _counts(sync_conn) as counts:
        foreign = await builder.ok(other, {**query, "offset": 10, "count_token": first["count_token"]})
    assert (foreign["total"], foreign["count_reused"], len(counts)) == (25, False, 1), "别人的凭证不能复用"

    with _counts(sync_conn) as counts:
        own = await builder.ok(builder.admin, {**query, "offset": 10, "count_token": first["count_token"]})
    assert (own["total"], own["count_reused"], counts) == (25, True, [])
    assert len(own["rows"]) == _PAGE
