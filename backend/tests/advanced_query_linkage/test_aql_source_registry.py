"""源注册表与 SQL 分页内核（advanced-query-linkage-closure 任务 4；design §3.1、§10.1；ADR-AQL-03 / 06）。

- 注册表自洽：每个源的显示列 / 隐藏列 / 旧筛选键 / 默认排序 / 唯一键都落在其 ORM 表的真实列上；
- 源键解析：别名、前缀、合并单位、底稿叶子（带 / 不带单元格区域）、附注叶子、未知源 400；
- 语句形态（postgresql 方言编译）：WHERE 含项目、年度、未删与生效数据集谓词，ORDER BY 末项为唯一键、
  NULLS LAST 只在可空列，用户值只在绑定参数里；sqlite 方言同一语句可编译；
- 未登记的筛选键 / 条件字段 / 算子 / 列 → 400（不再静默忽略，R6.2）；offset 超 100,000 → 422；
- SQLite 真执行：like / 前缀按字面匹配 ``%`` ``_`` ``\\``，COUNT 与分页、可空列空值在后、无生效数据集的 warnings；
- ``build_portable_filter`` 与构建器 ``_build_filter`` 对白名单算子等价，内部算子只对旧筛选键开放。
"""
from __future__ import annotations

import datetime as dt
import unicodedata
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.audit_platform_models import TbLedger
from app.models.base import Base, ProjectStatus
from app.models.core import Project
from app.models.dataset_models import LedgerDataset
from app.services.custom_query import paged_fetch
from app.services.custom_query import source_registry as sr
from app.services.custom_query.builder_dsl import _build_filter
from app.services.custom_query.param_sql_builder import BLANK_CHARS, build_portable_filter
from app.services.custom_query.table_whitelist import OPERATOR_WHITELIST
from app.services.dataset_service import DatasetService
from tests.advanced_query_linkage.builder_tables import create_tables_with_closure

_PID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_DATASET = uuid.UUID("99999999-8888-7777-6666-555555555555")


def _ctx(db=None, **kw) -> sr.FetchContext:
    return sr.FetchContext(db=db, user=None, project_id=kw.pop("project_id", _PID), year=kw.pop("year", 2025),
                           filters=kw.pop("filters", {}), **kw)


def _pg(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


def _detail(exc: pytest.ExceptionInfo) -> dict:
    assert isinstance(exc.value, HTTPException)
    return exc.value.detail


# ─── 注册表自洽 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("spec", list(sr.SOURCE_REGISTRY.values()), ids=list(sr.SOURCE_REGISTRY))
def test_registry_entries_are_real_orm_columns(spec: sr.SourceSpec) -> None:
    keys = [c.key for c in (*spec.columns, *spec.hidden)]
    assert len(keys) == len(set(keys)), f"{spec.key} 列键重复：{keys}"
    for column in (*spec.columns, *spec.hidden):
        base = sr._base_column(column.expr)
        assert isinstance(base, sa.Column), f"{spec.key}.{column.key} 不是表列：{base!r}"
        assert Base.metadata.tables.get(base.table.name) is base.table, f"{spec.key}.{column.key} 不在 ORM 元数据里"
        assert base.name == column.key, f"{spec.key}.{column.key} 与列名 {base.name} 不一致"
    for fk in spec.filter_keys:
        assert spec.column(fk.column) is not None, f"{spec.key} 筛选键 {fk.key} 指向未登记的列 {fk.column}"
    sortable = {c.key for c in (*spec.columns, *spec.hidden) if c.sortable}
    for field, direction in spec.default_sort:
        assert field in sortable and direction in ("asc", "desc"), (spec.key, field, direction)
    assert spec.unique_key in {c.key for c in spec.hidden}, f"{spec.key} 唯一键须是隐藏列"
    assert not ({c.key for c in spec.columns} & {c.key for c in spec.hidden}), f"{spec.key} 显示列与隐藏列重叠"


def test_nullable_is_read_from_column_definition() -> None:
    led = sr.LEDGER_ENTRIES
    assert led.column("voucher_date").nullable is False and led.column("debit_amount").nullable is True
    assert sr.WORKPAPER.column("status").nullable is False, "Cast 包着的枚举列按底层列定义判可空"


# ─── 源键解析 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("source", "filters", "expect"), [
    ("tb_detail", {}, ("spec", "trial_balance", {}, None)),
    ("trial_balance", {}, ("spec", "trial_balance", {}, None)),
    ("account_balance", {}, ("spec", "account_balance", {}, None)),
    ("ledger_entries", {}, ("spec", "ledger_entries", {}, None)),
    ("workhours", {}, ("spec", "workhours", {}, None)),
    ("workpaper", {}, ("spec", "workpaper", {}, None)),
    ("workpaper:E1", {}, ("spec", "workpaper", {"wp_code": "E1"}, None)),
    ("workpaper:E1|审定表", {}, ("spec", "workpaper", {"wp_code": "E1", "sheet_name": "审定表"}, None)),
    ("workpaper:E1|审定表", {"cell_range": "A1:B2"},
     ("json", sr.WORKPAPER_CELLS, {"wp_code": "E1", "sheet_name": "审定表"}, None)),
    ("workpaper", {"wp_code": "E1", "cell_range": "A1"}, ("json", sr.WORKPAPER_CELLS, {}, None)),
    ("consol_unit:C01:ledger_entries", {}, ("spec", "ledger_entries", {}, "C01")),
    ("consol_unit:C01:tb_detail", {}, ("spec", "trial_balance", {}, "C01")),
    ("consol_unit:C01:adjustment", {}, ("legacy", "_query_adjustments", {"company_code": "C01", "adjustment_type": "AJE"}, None)),
    ("disclosure_note:八、1", {}, ("json", ("disclosure", "_query_disclosure"), {"section_id": "八、1"}, None)),
    ("disclosure", {}, ("json", ("disclosure", "_query_disclosure"), {}, None)),
    ("tb_summary", {}, ("json", ("worksheet", "_query_tb_summary"), {}, None)),
    ("ws_consol_tb", {}, ("json", ("worksheet", "_query_worksheet"), {}, None)),
    ("report_balance_sheet", {}, ("legacy", "_query_report", {}, None)),
    ("report_lines", {}, ("legacy", "_query_report_lines", {}, None)),
    ("adj_aje", {}, ("legacy", "_query_adjustments", {}, None)),
])
def test_resolve_source(source: str, filters: dict, expect: tuple) -> None:
    kind, target, fixed, company = expect
    resolved = sr.resolve_source(source, filters)
    if kind == "spec":
        assert resolved.spec is sr.SOURCE_REGISTRY[target] and resolved.json_fetcher is None
    elif kind == "json":
        assert resolved.json_fetcher == target and resolved.spec is None
    else:
        assert resolved.legacy_fetcher == target and resolved.spec is None
    assert dict(resolved.fixed_filters) == fixed and resolved.company_code == company


@pytest.mark.parametrize("source", ["", "nope", "consol_unit:C01", "consol_unit::ledger_entries",
                                    "consol_unit:C01:workhours", "workpaper:"])
def test_unknown_source_is_400(source: str) -> None:
    with pytest.raises(HTTPException) as exc:
        sr.resolve_source(source, {})
    assert exc.value.status_code == 400 and _detail(exc)["error_code"] == "UNKNOWN_SOURCE"


# ─── 语句形态 ────────────────────────────────────────────────────────────────


@pytest.fixture
def fixed_active_dataset(monkeypatch):
    async def _active(db, project_id, year):
        return _DATASET

    monkeypatch.setattr(DatasetService, "get_active_dataset_id", staticmethod(_active))


async def test_ledger_statement_where_and_order_in_postgres(fixed_active_dataset) -> None:
    hostile = "10'01; DROP TABLE tb_ledger --"
    ctx = _ctx(filters={"account_code": hostile, "summary": "冲销"})
    stmt, display = await paged_fetch.build_statement(
        sr.LEDGER_ENTRIES, ctx, conditions=[{"field": "debit_amount", "op": "gt", "value": "100000000"}],
    )
    sql = _pg(stmt)
    for clause in ("tb_ledger.project_id = %(", "tb_ledger.year = %(", "tb_ledger.dataset_id = %(",
                   "tb_ledger.is_deleted = false", "tb_ledger.debit_amount > %(", "tb_ledger.account_code LIKE %(",
                   "tb_ledger.summary LIKE %("):
        assert clause in sql, f"WHERE 缺 {clause}：{sql}"
    assert "DROP" not in sql and "冲销" not in sql and "100000000" not in sql, "用户值只能出现在绑定参数里"
    assert [c.key for c in display] == sr.LEDGER_ENTRIES.display_keys
    ordered = _pg(stmt.order_by(*paged_fetch._order_by(sr.LEDGER_ENTRIES, ())))
    tail = ordered.split("ORDER BY", 1)[1]
    assert "voucher_date DESC" in tail and "voucher_date DESC NULLS LAST" not in tail, "非空列不加 NULLS LAST"
    assert "entry_seq ASC NULLS LAST" in tail, "可空列加 NULLS LAST"
    assert tail.strip().endswith("id ASC"), f"ORDER BY 末项须是唯一键：{tail}"
    by_debit = _pg(stmt.order_by(*paged_fetch._order_by(sr.LEDGER_ENTRIES, [{"field": "debit_amount", "direction": "desc"}])))
    assert "debit_amount DESC NULLS LAST" in by_debit.split("ORDER BY", 1)[1]
    str(stmt.compile(dialect=sqlite.dialect()))  # 同一语句以 sqlite 方言编译不报错


async def test_trial_balance_and_workpaper_statement_shape() -> None:
    tb_stmt, _ = await paged_fetch.build_statement(sr.TRIAL_BALANCE, _ctx(company_code="C01"))
    sql = _pg(tb_stmt)
    for clause in ("trial_balance.project_id = %(", "trial_balance.year = %(", "trial_balance.is_deleted = false",
                   "trial_balance.company_code = %("):
        assert clause in sql, sql
    wp_stmt, _ = await paged_fetch.build_statement(
        sr.WORKPAPER, _ctx(filters={"wp_code": "E1", "sheet_name": "审定表"}))
    wp_sql = _pg(wp_stmt)
    assert "JOIN wp_index ON wp_index.id = working_paper.wp_index_id" in wp_sql
    assert "wp_index.wp_code = %(" in wp_sql and "wp_index.wp_code LIKE %(" in wp_sql, "编码精确或其子编码"
    assert " AS sheet_name" in wp_sql, "底稿叶子的 sheet 名以隐藏列回显"
    assert "working_paper.project_id = %(" in wp_sql and "working_paper.is_deleted = false" in wp_sql


# ─── 未登记的输入一律 400 ─────────────────────────────────────────────────────


@pytest.mark.parametrize(("kwargs", "code"), [
    ({"filters": {"debit_amount_min": 1}}, "UNKNOWN_FILTER_KEY"),
    ({"filters": {"account_code": ["1001", "1002"]}}, "INVALID_FILTER_VALUE"),
    ({"conditions": [{"field": "nope", "op": "eq", "value": 1}]}, "UNKNOWN_CONDITION_FIELD"),
    ({"conditions": [{"field": "id", "op": "eq", "value": 1}]}, "UNKNOWN_CONDITION_FIELD"),
    ({"conditions": [{"field": "summary", "op": "regex", "value": "x"}]}, "OP_NOT_ALLOWED"),
    ({"conditions": [{"field": "account_code", "op": "prefix", "value": "10"}]}, "OP_NOT_ALLOWED"),
    ({"conditions": [{"field": "account_code", "op": "in", "value": [str(i) for i in range(501)]}]}, "INVALID_IN_VALUE"),
    ({"columns": ["account_name", "closing_balance"]}, "UNKNOWN_COLUMN"),
], ids=["filter-key", "filter-list", "cond-field", "cond-hidden", "cond-op", "cond-internal-op", "cond-in-500",
        "column"])
async def test_unregistered_inputs_are_400(kwargs: dict, code: str, fixed_active_dataset) -> None:
    # 口径谓词不触库（生效数据集 id 固定）：校验若被跳过，语句照常建出 ⇒ 形态是 DID NOT RAISE，而不是别的报错
    ctx = _ctx(filters=kwargs.pop("filters", {}))
    with pytest.raises(HTTPException) as exc:
        await paged_fetch.build_statement(sr.LEDGER_ENTRIES, ctx, **kwargs)
    assert exc.value.status_code == 400 and _detail(exc)["error_code"] == code, _detail(exc)
    assert _detail(exc)["message"], "400 须带中文原因"


async def test_offset_beyond_100k_is_422_and_bad_sort_is_422() -> None:
    with pytest.raises(HTTPException) as deep:
        await paged_fetch.page(sr.LEDGER_ENTRIES, _ctx(), limit=100, offset=paged_fetch.MAX_SQL_OFFSET + 1)
    assert deep.value.status_code == 422 and _detail(deep)["error_code"] == "OFFSET_TOO_DEEP"
    with pytest.raises(HTTPException) as bad_field:
        await paged_fetch.page(sr.LEDGER_ENTRIES, _ctx(), sort=[{"field": "nope"}], limit=10, offset=0)
    assert bad_field.value.status_code == 422 and _detail(bad_field)["error_code"] == "INVALID_SORT_FIELD"
    with pytest.raises(HTTPException) as bad_dir:
        await paged_fetch.page(sr.LEDGER_ENTRIES, _ctx(), sort=[{"field": "voucher_no", "direction": "up"}],
                               limit=10, offset=0)
    assert _detail(bad_dir)["error_code"] == "INVALID_SORT_FIELD_DIRECTION"


# ─── SQLite 真执行 ───────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def ledger_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(create_tables_with_closure, (TbLedger.__table__, LedgerDataset.__table__, Project.__table__))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        session.add(Project(id=_PID, name="【测试】aql 注册表", client_name="aql", status=ProjectStatus.created))
        rows = [
            ("50%_x", "10_1", Decimal("5")), ("50abx", "1001", None), ("5", "10%1", Decimal("7")),
            ("a\\b", "1002", Decimal("3")), ("50%_y", "1001", None),
        ]
        for i, (summary, code, debit) in enumerate(rows):
            session.add(TbLedger(project_id=_PID, year=2025, company_code="001", voucher_date=dt.date(2025, 1, 1 + i),
                                 voucher_no=f"V{i}", account_code=code, summary=summary, debit_amount=debit))
        session.add(TbLedger(project_id=_PID, year=2025, company_code="001", voucher_date=dt.date(2025, 2, 1),
                             voucher_no="DEL", account_code="1001", summary="50%_deleted", is_deleted=True))
        await session.commit()
        yield session
    await engine.dispose()


async def _page(db, **kw):
    filters = kw.pop("filters", {})
    return await paged_fetch.page(sr.LEDGER_ENTRIES, _ctx(db, filters=filters), limit=kw.pop("limit", 100),
                                  offset=kw.pop("offset", 0), **kw)


async def test_like_matches_percent_and_underscore_literally(ledger_db) -> None:
    hit = await _page(ledger_db, conditions=[{"field": "summary", "op": "like", "value": "50%_"}])
    assert sorted(r["summary"] for r in hit.rows) == ["50%_x", "50%_y"], "包含 50%_ 按字面匹配，不把 % _ 当通配符"
    assert hit.total == 2 and hit.paged
    backslash = await _page(ledger_db, conditions=[{"field": "summary", "op": "like", "value": "a\\b"}])
    assert [r["summary"] for r in backslash.rows] == ["a\\b"]
    exclude = await _page(ledger_db, conditions=[{"field": "summary", "op": "not_like", "value": "50%_"}])
    assert exclude.total == 3


async def test_prefix_filter_key_is_literal(ledger_db) -> None:
    underscore = await _page(ledger_db, filters={"account_code": "10_"})
    assert [r["account_code"] for r in underscore.rows] == ["10_1"], "前缀筛选的 _ 按字面匹配"
    percent = await _page(ledger_db, filters={"account_code": "10%"})
    assert [r["account_code"] for r in percent.rows] == ["10%1"]


async def test_count_paging_nulls_last_and_warning(ledger_db) -> None:
    first = await _page(ledger_db, limit=2, sort=[{"field": "debit_amount", "direction": "desc"}])
    second = await _page(ledger_db, limit=2, offset=2, sort=[{"field": "debit_amount", "direction": "desc"}])
    third = await _page(ledger_db, limit=2, offset=4, sort=[{"field": "debit_amount", "direction": "desc"}])
    assert first.total == second.total == third.total == 5, "total 来自 COUNT，不随页变化；软删行不计"
    debits = [r["debit_amount"] for r in (*first.rows, *second.rows, *third.rows)]
    assert debits == [7.0, 5.0, 3.0, None, None], "降序时空值在后"
    asc = await _page(ledger_db, sort=[{"field": "debit_amount", "direction": "asc"}])
    assert [r["debit_amount"] for r in asc.rows] == [3.0, 5.0, 7.0, None, None], "升序时空值也在后"
    ids = [r["id"] for r in (*first.rows, *second.rows, *third.rows)]
    assert len(set(ids)) == 5, "逐页并集 = 全集且互不重叠"
    assert sr.NO_ACTIVE_DATASET_WARNING in first.warnings, "没有生效数据集时 warnings 写明按未删除行返回"
    assert first.meta == {"ref_context": {"template_type": "soe", "year": 2025}}
    assert [c.key for c in first.columns] == sr.LEDGER_ENTRIES.display_keys
    assert {"id", "entry_seq", "accounting_period", "company_code"} <= set(first.rows[0]), "隐藏列随行返回"


async def test_column_projection_keeps_hidden_keys(ledger_db) -> None:
    page = await _page(ledger_db, columns=["account_name", "voucher_no"])
    assert [c.key for c in page.columns] == ["voucher_no", "account_name"], "只含所选列（按源定义的列序）"
    assert "summary" not in page.rows[0] and "id" in page.rows[0], "未选的显示列不返回，下钻键随行返回"


async def test_all_rows_rejects_aggregation_over_cap(ledger_db) -> None:
    full = await paged_fetch.all_rows(sr.LEDGER_ENTRIES, _ctx(ledger_db), cap=5)
    assert full.total == 5 and not full.paged
    with pytest.raises(HTTPException) as exc:
        await paged_fetch.all_rows(sr.LEDGER_ENTRIES, _ctx(ledger_db), cap=4)
    assert exc.value.status_code == 400 and _detail(exc)["error_code"] == "AGGREGATION_TOO_LARGE"
    assert _detail(exc)["row_count"] == 5


# ─── 谓词来源 ────────────────────────────────────────────────────────────────

_COL = TbLedger.__table__.c.account_code
_NUM = TbLedger.__table__.c.debit_amount
_VALUES = {"in": ["1001", "1002"], "not_in": ["1001"], "between": ["1001", "1009"], "is_null": None,
           "is_not_null": None}


@pytest.mark.parametrize("op", sorted(OPERATOR_WHITELIST))
def test_portable_filter_equals_builder_filter(op: str) -> None:
    value = _VALUES.get(op, "10_1%")
    portable = build_portable_filter(_COL, op, value).compile(dialect=postgresql.dialect())
    builder = _build_filter(_COL, op, value).compile(dialect=postgresql.dialect())
    assert str(portable) == str(builder) and portable.params == builder.params


def test_internal_operators_only_for_legacy_filter_keys() -> None:
    for op in ("prefix", "nonempty"):
        with pytest.raises(HTTPException) as exc:
            build_portable_filter(_COL, op, "x")
        assert _detail(exc)["error_code"] == "OP_NOT_ALLOWED"
        with pytest.raises(HTTPException):
            _build_filter(_COL, op, "x")
    prefix = build_portable_filter(_COL, "prefix", "10_", allow_internal=True).compile(dialect=postgresql.dialect())
    assert "LIKE" in str(prefix) and list(prefix.params.values()) == ["10\\_%"]
    blank = str(build_portable_filter(_COL, "nonempty", False, allow_internal=True).compile(dialect=sqlite.dialect()))
    nonempty = str(build_portable_filter(_COL, "nonempty", True, allow_internal=True).compile(dialect=sqlite.dialect()))
    assert "IS NULL" in blank and "trim(" in blank and nonempty.startswith("NOT")


def test_blank_chars_are_js_trim_whitespace() -> None:
    zs = {chr(cp) for cp in range(0x110000) if unicodedata.category(chr(cp)) == "Zs"}
    expected = zs | {"\t", "\n", "\x0b", "\x0c", "\r", "\u2028", "\u2029", "\ufeff"}
    assert set(BLANK_CHARS) == expected and len(BLANK_CHARS) == len(expected) == 25


def test_numeric_condition_value_is_coerced_and_bad_value_400() -> None:
    compiled = build_portable_filter(_NUM, "gt", "100000000").compile(dialect=postgresql.dialect())
    assert list(compiled.params.values()) == [Decimal("100000000")]
    with pytest.raises(HTTPException) as exc:
        build_portable_filter(_NUM, "gt", "一亿")
    assert _detail(exc)["error_code"] == "INVALID_DECIMAL"


async def test_ref_context_follows_project_template_type() -> None:
    class _DB:
        def __init__(self, project):
            self.project, self.calls = project, 0

        async def get(self, model, pk):
            self.calls += 1
            return self.project

    listed = _DB(SimpleNamespace(template_type="listed"))
    ctx = _ctx(listed)
    assert await sr.ref_context(ctx) == {"template_type": "listed", "year": 2025}
    assert await sr.ref_context(ctx) == {"template_type": "listed", "year": 2025} and listed.calls == 1, "同一请求只查一次"
    assert await sr.ref_context(_ctx(_DB(None))) == {"template_type": "soe", "year": 2025}
