"""抽凭登记的科目取被抽中分录的科目（spec voucher-workflow-linkage-lineage-closure 任务 1）。

共享库实测：E1 按 1001 / 1002 / 1012 抽凭，旧实现把 30 行登记的科目一律写成筛选条件的第一个科目 1001，
回填日志 ``filled_unit_ids`` 指向的 30 笔分录实际全是 1002。登记科目改为按分录 id 回查；回查不到时
筛选条件只有一个科目才用它，否则留空（不猜）。旧格式日志只有凭证号时，回查到唯一一张凭证就补上凭证键。
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import date
from types import SimpleNamespace

from app.services import sampling_registry_service as reg

PID = uuid.uuid4()
LINE_A = uuid.uuid4()
LINE_B = uuid.uuid4()
COMPANY = "重药控股安徽有限公司"


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _DB:
    """第一条 SELECT 回分录，INSERT 只记下来。"""

    def __init__(self, lines):
        self.lines = lines
        self.inserts = []
        self.selects = 0

    async def execute(self, stmt):
        if stmt.__visit_name__ == "select":
            self.selects += 1
            return _Rows(self.lines)
        self.inserts.append(stmt)
        return SimpleNamespace(rowcount=len(stmt._multi_values[0]))

    async def flush(self):
        return None

    def begin_nested(self):
        return contextlib.nullcontext()


def _line(no, account, *, d=date(2025, 1, 24), vtype="主账簿"):
    return SimpleNamespace(company_code=COMPANY, voucher_date=d, voucher_type=vtype, voucher_no=no, account_code=account)


def _log(**criteria):
    return SimpleNamespace(project_id=PID, workpaper_id=uuid.uuid4(), batch_id=uuid.uuid4(), user_id=uuid.uuid4(),
                           extraction_criteria={"phase": "final", **criteria})


def _registered(db):
    assert db.inserts, "没有写登记"
    rows = [dict(r) for r in db.inserts[0]._multi_values[0]]
    return [{getattr(k, "name", k): v for k, v in r.items()} for r in rows]


def test_account_comes_from_sampled_line_not_filter():
    db = _DB([_line("0909", "1002")])
    log = _log(filled_voucher_nos=["0909"], filled_unit_ids=[str(LINE_A)],
               filters={"account_codes": ["1001", "1002", "1012"]})
    assert asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025)) == 1
    (row,) = _registered(db)
    assert row["account_code"] == "1002"
    # 旧格式日志只有号：按回查到的唯一一张凭证补上凭证键
    assert (row["voucher_date"], row["company_code"], row["voucher_type"]) == (date(2025, 1, 24), COMPANY, "主账簿")


def test_new_format_key_matches_line_and_takes_its_account():
    key = '["2025","%s","2025-01-24","主账簿","0909"]' % COMPANY
    db = _DB([_line("0909", "1002.01")])
    log = _log(filled_voucher_keys=[key], filled_unit_ids=[str(LINE_A)], filters={"account_codes": ["1001", "1002"]})
    asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025))
    assert _registered(db)[0]["account_code"] == "1002.01"


def test_two_accounts_in_same_voucher_leave_account_empty():
    db = _DB([_line("0909", "1002"), _line("0909", "1012")])
    log = _log(filled_voucher_nos=["0909"], filled_unit_ids=[str(LINE_A), str(LINE_B)],
               filters={"account_codes": ["1002", "1012"]})
    asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025))
    assert _registered(db)[0]["account_code"] is None


def test_number_on_two_dates_is_not_guessed():
    db = _DB([_line("0019", "1002", d=date(2025, 1, 5)), _line("0019", "1002", d=date(2025, 2, 5))])
    log = _log(filled_voucher_nos=["0019"], filled_unit_ids=[str(LINE_A), str(LINE_B)],
               filters={"account_codes": ["1002"]})
    asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025))
    (row,) = _registered(db)
    assert row["voucher_date"] is None  # 两张同号凭证：不猜
    assert row["account_code"] == "1002"  # 凭证键没定下来，按唯一筛选科目


def test_without_unit_ids_single_filter_code_kept_multi_filter_codes_empty():
    one = _DB([])
    asyncio.run(reg.register_sampled_vouchers(one, log=_log(filled_voucher_nos=["1"], filters={"account_codes": ["1122"]}), year=2025))
    assert _registered(one)[0]["account_code"] == "1122"
    assert one.selects == 0, "没有分录 id 不该回查序时账"
    many = _DB([])
    asyncio.run(reg.register_sampled_vouchers(
        many, log=_log(filled_voucher_nos=["1"], filters={"account_codes": ["1001", "1002"]}), year=2025))
    assert _registered(many)[0]["account_code"] is None


def test_lookup_failure_keeps_registration():
    class _Boom(_DB):
        async def execute(self, stmt):
            if stmt.__visit_name__ == "select":
                raise RuntimeError("tb_ledger 不可用")
            return await super().execute(stmt)

    db = _Boom([])
    log = _log(filled_voucher_nos=["0909"], filled_unit_ids=[str(LINE_A)], filters={"account_codes": ["1002"]})
    assert asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025)) == 1
    assert _registered(db)[0]["account_code"] == "1002"


def test_registered_account_rule():
    assert reg._registered_account({"1002"}, ["1001", "1002"]) == "1002"
    assert reg._registered_account({"1002", "1012"}, ["1002"]) is None
    assert reg._registered_account(None, ["1122"]) == "1122"
    assert reg._registered_account(set(), ["1001", "1002"]) is None
    assert reg._registered_account(None, []) is None
