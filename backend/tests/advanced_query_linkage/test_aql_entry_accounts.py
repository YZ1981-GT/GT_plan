"""W6 业务对象 → 科目与筛选键（advanced-query-linkage-closure 任务 45；design §3.12、§10.4 #26 / #27）。

- `codes_for_wp_code`：精确匹配、退主编码、没有科目的底稿、空输入；映射文件改动后按 mtime 重读。
- 章节 → 底稿编码**按准则分流**：刻意不用过时的通用 `note_section` 字段（现查 96 个有值行里 80 行与两套准则都不一致）。
- `report_row_predicate`：单码编译成转义后的 LIKE、`起~止` 编译成 BETWEEN、多码 or_；行不存在 / 没有取数科目各自抛域异常。
- 四个筛选键在注册表上的登记与 400 文案；`meta.entry_accounts` 排序、去重、截断。
"""
from __future__ import annotations

import json
import uuid

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.note_account_mapping import NoteAccountMapping
from app.models.report_models import DisclosureNote, FinancialReport
from app.services.custom_query import entry_accounts as ea
from app.services.custom_query import paged_fetch
from app.services.custom_query import entry_filters as ef
from app.services.custom_query import source_registry as sr
from tests.advanced_query_linkage.builder_tables import create_tables_with_closure

_PID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_TB_CODE = sr.TrialBalance.__table__.c.standard_account_code
_LED_CODE = sr.TbLedger.__table__.c.account_code


def _ctx(db=None, **kw) -> sr.FetchContext:
    return sr.FetchContext(
        db=db, user=None, project_id=kw.pop("project_id", _PID), year=kw.pop("year", 2025),
        filters=kw.pop("filters", {}), **kw,
    )


def _pg(expr) -> str:
    return str(expr.compile(dialect=postgresql.dialect()))


def _params(expr) -> dict:
    compiled = expr.compile(dialect=postgresql.dialect())
    return dict(compiled.params)


# ── 底稿编码 → 科目 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("wp_code", "expected"),
    [
        ("E1", ("1001", "1002", "1012")),   # 主编码自己登记了三个科目
        ("E1-2", ("1001",)),                 # 子编码自己有登记，取自己的
        ("E1-99", ("1001", "1002", "1012")),  # 子编码未登记 ⇒ 退到主编码 E1
        ("A1", ()),                          # 沟通类底稿登记了但没有科目
        ("ZZ-404", ()),                      # 主编码也没登记
        ("", ()),
        ("   ", ()),
    ],
)
def test_codes_for_wp_code(wp_code: str, expected: tuple[str, ...]) -> None:
    assert ea.codes_for_wp_code(wp_code) == expected


def test_mapping_index_is_reread_after_the_file_changes(tmp_path, monkeypatch) -> None:
    """映射表是人工维护的数据文件：改了之后不重启也要生效（按 mtime + 大小判断）。"""
    path = tmp_path / "wp_account_mapping.json"

    def write(codes: list[str]) -> None:
        path.write_text(json.dumps({"mappings": [
            {"wp_code": "X1", "account_codes": codes, "note_section_soe": "八、99"},
        ]}, ensure_ascii=False), encoding="utf-8")

    write(["1001"])
    monkeypatch.setattr(ea, "_mapping_path", lambda: path)
    ea._CACHE.pop(path, None)
    assert ea.codes_for_wp_code("X1") == ("1001",)

    write(["2001", "2002"])
    import os

    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))
    assert ea.codes_for_wp_code("X1") == ("2001", "2002")


# ── 附注章节 → 底稿编码（按准则分流）────────────────────────────────────────


@pytest.mark.parametrize(
    ("section", "template_type", "expected"),
    [
        ("八、1", "soe", ("E1", "E1-1")),      # 国企编号
        ("五、1", "listed", ("E1", "E1-1")),   # 上市编号
        ("五、1", "soe", ()),                   # 上市编号不得命中国企项目
        ("八、1", "listed", ()),
        ("", "soe", ()),
    ],
)
def test_wp_codes_for_note_section_is_per_standard(section, template_type, expected) -> None:
    assert ea.wp_codes_for_note_section(section, template_type) == expected


def test_stale_generic_note_section_field_is_not_used(tmp_path, monkeypatch) -> None:
    """同文件的通用 ``note_section`` 是过时字段（与两套准则字段都不一致），不得参与解析。

    这是本任务的核心判据之一：若把它加回索引，一套准则的编号会命中另一套的行（现查 D3 与 D6 的通用编号都写成「五、18」）。
    """
    path = tmp_path / "wp_account_mapping.json"
    path.write_text(json.dumps({"mappings": [
        {"wp_code": "Y1", "account_codes": ["1001"],
         "note_section": "五、18", "note_section_soe": "八、11", "note_section_listed": "五、10"},
    ]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(ea, "_mapping_path", lambda: path)
    ea._CACHE.pop(path, None)

    assert ea.wp_codes_for_note_section("八、11", "soe") == ("Y1",)
    assert ea.wp_codes_for_note_section("五、10", "listed") == ("Y1",)
    for template_type in ("soe", "listed"):
        assert ea.wp_codes_for_note_section("五、18", template_type) == (), "通用 note_section 字段不得参与解析"


# ── 报表行 → 谓词 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("token", "fragment", "expected_params"),
    [
        ("1001", "LIKE", {"standard_account_code_1": "1001%"}),
        ("1401~1499", "BETWEEN", {"standard_account_code_1": "1401", "standard_account_code_2": "1499"}),
    ],
)
def test_single_source_account_compiles(token, fragment, expected_params) -> None:
    clause = ea._source_account_predicate(_TB_CODE, token)
    assert clause is not None
    assert fragment in _pg(clause).upper()
    assert _params(clause) == expected_params


def test_like_metacharacters_in_a_source_account_are_escaped() -> None:
    clause = ea._source_account_predicate(_TB_CODE, "10%_x")
    assert _params(clause)["standard_account_code_1"] == r"10\%\_x%"


@pytest.mark.parametrize("token", ["", "   ", "~1499", "1401~", "~"])
def test_unusable_source_account_tokens_are_dropped(token: str) -> None:
    assert ea._source_account_predicate(_TB_CODE, token) is None


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(create_tables_with_closure, (
            FinancialReport.__table__, DisclosureNote.__table__, NoteAccountMapping.__table__,
        ))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
    await engine.dispose()


def _report_row(**kw) -> FinancialReport:
    return FinancialReport(
        id=uuid.uuid4(), project_id=_PID, year=2025, report_type="balance_sheet",
        is_deleted=False, **kw,
    )


async def test_report_row_predicate_joins_every_source_account(db: AsyncSession) -> None:
    db.add(_report_row(
        row_code="BS-002", source_accounts=["1001", "1002", "1012"],
        formula_used="TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')",
    ))
    await db.flush()

    predicate, info = await ea.report_row_predicate(
        db, project_id=_PID, year=2025, report_type="balance_sheet",
        row_code="BS-002", column=_TB_CODE,
    )
    sql = _pg(predicate)
    assert sql.upper().count("LIKE") == 3 and " OR " in sql
    assert info["codes"] == ["1001", "1002", "1012"]
    assert info["formula"].startswith("TB('1001'")


async def test_report_row_predicate_mixes_prefix_and_range(db: AsyncSession) -> None:
    db.add(_report_row(row_code="BS-010", source_accounts=["1401~1499", "1471"], formula_used="SUM_TB(...)"))
    await db.flush()
    predicate, info = await ea.report_row_predicate(
        db, project_id=_PID, year=2025, report_type="balance_sheet", row_code="BS-010", column=_TB_CODE,
    )
    sql = _pg(predicate).upper()
    assert "BETWEEN" in sql and "LIKE" in sql
    assert info["codes"] == ["1401~1499", "1471"]


async def test_report_row_not_generated(db: AsyncSession) -> None:
    with pytest.raises(ea.ReportRowNotGenerated):
        await ea.report_row_predicate(
            db, project_id=_PID, year=2025, report_type="balance_sheet", row_code="BS-999", column=_TB_CODE,
        )


@pytest.mark.parametrize("sources", [None, [], {}, "1001", [""], ["~"]])
async def test_report_row_without_usable_accounts(db: AsyncSession, sources) -> None:
    """合计行与矩阵报表行的 ``source_accounts`` 不是可用的码数组（真库里多数是 JSON null）。"""
    db.add(_report_row(row_code="BS-015", source_accounts=sources, formula_used="ROW('BS-002')"))
    await db.flush()
    with pytest.raises(ea.ReportRowNoAccounts):
        await ea.report_row_predicate(
            db, project_id=_PID, year=2025, report_type="balance_sheet", row_code="BS-015", column=_TB_CODE,
        )


async def test_report_row_is_scoped_to_project_year_and_type(db: AsyncSession) -> None:
    db.add(_report_row(row_code="BS-002", source_accounts=["1001"], formula_used="TB('1001','期末余额')"))
    await db.flush()
    for kw in ({"project_id": uuid.uuid4()}, {"year": 2024}, {"report_type": "income_statement"}):
        args = {"project_id": _PID, "year": 2025, "report_type": "balance_sheet", **kw}
        with pytest.raises(ea.ReportRowNotGenerated):
            await ea.report_row_predicate(db, row_code="BS-002", column=_TB_CODE, **args)


# ── 附注章节 → 科目（含 note_account_mappings 支路）──────────────────────────


async def test_codes_for_note_section_uses_the_json_mapping(db: AsyncSession) -> None:
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="八、1",
        section_title="货币资金", is_deleted=False,
    ))
    await db.flush()
    resolved = await ea.codes_for_note_section(
        db, project_id=_PID, year=2025, section="八、1", template_type="soe",
    )
    assert resolved.title == "货币资金"
    assert resolved.wp_codes == ("E1", "E1-1")
    assert resolved.codes == ("1001", "1002", "1012")


async def test_note_account_mappings_table_contributes_too(db: AsyncSession) -> None:
    """design 原定的唯一来源（现查共享库 0 行）仍接在链路上：填了就生效。"""
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="九、7",
        section_title="【测试】只在表里登记的章节", is_deleted=False,
    ))
    db.add(NoteAccountMapping(
        template_type="soe_standalone", report_row_code="BS-006",
        note_section_code="【测试】只在表里登记的章节", table_index=0, wp_code="D2",
    ))
    await db.flush()
    assert ea.wp_codes_for_note_section("九、7", "soe") == (), "前置：JSON 侧不认这个章节"

    resolved = await ea.codes_for_note_section(
        db, project_id=_PID, year=2025, section="九、7", template_type="soe",
    )
    assert resolved.wp_codes == ("D2",) and resolved.codes == ("1122",)


async def test_note_account_mappings_is_matched_per_standard(db: AsyncSession) -> None:
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="九、8",
        section_title="【测试】上市准则登记", is_deleted=False,
    ))
    db.add(NoteAccountMapping(
        template_type="listed_standalone", report_row_code="BS-006",
        note_section_code="【测试】上市准则登记", table_index=0, wp_code="D2",
    ))
    await db.flush()
    with pytest.raises(ea.NoteSectionNoAccounts):  # 国企项目取不到上市准则的登记
        await ea.codes_for_note_section(
            db, project_id=_PID, year=2025, section="九、8", template_type="soe",
        )


async def test_note_section_not_found_and_no_accounts(db: AsyncSession) -> None:
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="九、9",
        section_title="【测试】没有登记科目", is_deleted=False,
    ))
    await db.flush()
    with pytest.raises(ea.NoteSectionNotFound):
        await ea.codes_for_note_section(
            db, project_id=_PID, year=2025, section="不存在的章节", template_type="soe",
        )
    with pytest.raises(ea.NoteSectionNoAccounts):
        await ea.codes_for_note_section(
            db, project_id=_PID, year=2025, section="九、9", template_type="soe",
        )


# ── 注册表登记与筛选键行为 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("spec_key", "expected_keys"),
    [
        ("ACCOUNT_BALANCE", {"account_code", "wp_code"}),
        ("LEDGER_ENTRIES", {"account_code", "wp_code"}),
        ("AUX_BALANCE", {"account_code", "wp_code"}),
        ("AUX_LEDGER", {"account_code", "wp_code"}),
        ("TRIAL_BALANCE", {"report_row", "note_section"}),
    ],
)
def test_entry_filter_keys_are_registered_with_resolvers(spec_key: str, expected_keys: set[str]) -> None:
    spec = getattr(sr, spec_key)
    with_resolver = {fk.key for fk in spec.filter_keys if fk.resolver is not None}
    assert expected_keys <= with_resolver
    for fk in spec.filter_keys:
        assert spec.column(fk.column) is not None, f"{spec.key}.{fk.key} 指向未登记的列"


def test_trial_balance_has_no_account_code_key_and_four_tables_have_no_report_row() -> None:
    """落点是设计规定的：报表行 / 附注章节只在试算表；科目 / 底稿编码只在四表。"""
    tb_keys = {fk.key for fk in sr.TRIAL_BALANCE.filter_keys}
    assert "account_code" not in tb_keys and "wp_code" not in tb_keys
    for spec in (sr.ACCOUNT_BALANCE, sr.LEDGER_ENTRIES, sr.AUX_BALANCE, sr.AUX_LEDGER):
        keys = {fk.key for fk in spec.filter_keys}
        assert "report_row" not in keys and "note_section" not in keys


def test_aux_ledger_accepts_wp_code_as_a_narrowing_filter() -> None:
    """底稿入口切到辅助明细时只带 ``wp_code``，必填筛选要认它（否则恒 AUX_FILTER_REQUIRED）。"""
    groups = [set(g) for g in sr.AUX_LEDGER.required_filters]
    assert {"wp_code"} in groups and {"account_code"} in groups and {"aux_type"} in groups


async def _resolve(spec, key: str, value) -> object:
    fk = next(f for f in spec.filter_keys if f.key == key)
    ctx = _ctx()
    clause = await fk.resolver(ctx, value)
    return clause, ctx


async def test_account_code_single_value_matches_the_old_prefix_semantics() -> None:
    clause, _ = await _resolve(sr.LEDGER_ENTRIES, "account_code", "1002")
    from app.services.custom_query.param_sql_builder import build_portable_filter

    expected = build_portable_filter(_LED_CODE, "prefix", "1002", allow_internal=True)
    assert _pg(clause) == _pg(expected) and _params(clause) == _params(expected)


async def test_account_code_multi_value_is_an_or_of_prefixes() -> None:
    clause, ctx = await _resolve(sr.LEDGER_ENTRIES, "account_code", ["1002", "1001"])
    sql = _pg(clause)
    assert sql.upper().count("LIKE") == 2 and " OR " in sql
    assert ctx.memo["entry_accounts"] == ("1001", "1002")


@pytest.mark.parametrize("value", [[], ["", "  "], [None]])
async def test_account_code_rejects_empty_values(value) -> None:
    with pytest.raises(HTTPException) as err:
        await _resolve(sr.LEDGER_ENTRIES, "account_code", value)
    assert err.value.status_code == 400
    assert err.value.detail["error_code"] == "INVALID_FILTER_VALUE"


async def test_account_code_rejects_more_than_the_cap() -> None:
    with pytest.raises(HTTPException) as err:
        await _resolve(sr.LEDGER_ENTRIES, "account_code", [f"{i:04d}" for i in range(51)])
    assert err.value.detail["error_code"] == "INVALID_FILTER_VALUE"
    assert "最多 50 个科目" in err.value.detail["message"]


async def test_wp_code_resolves_to_prefixes_and_remembers_them() -> None:
    clause, ctx = await _resolve(sr.AUX_LEDGER, "wp_code", "E1")
    assert _pg(clause).upper().count("LIKE") == 3
    assert ctx.memo["entry_accounts"] == ("1001", "1002", "1012")


@pytest.mark.parametrize("wp_code", ["A1", "D5", "ZZ-404"])
async def test_wp_code_without_accounts_is_a_400(wp_code: str) -> None:
    with pytest.raises(HTTPException) as err:
        await _resolve(sr.LEDGER_ENTRIES, "wp_code", wp_code)
    assert err.value.status_code == 400
    assert err.value.detail["error_code"] == "WP_CODE_NO_ACCOUNTS"
    assert err.value.detail["message"] == "该底稿没有登记对应科目"


@pytest.mark.parametrize("value", ["BS-002", "balance_sheet:", ":BS-002", "no_such_report:BS-002", "BS-002:x:y"])
async def test_report_row_value_must_be_type_colon_row(value: str) -> None:
    with pytest.raises(HTTPException) as err:
        await _resolve(sr.TRIAL_BALANCE, "report_row", value)
    assert err.value.status_code == 400
    assert err.value.detail["error_code"] == "INVALID_FILTER_VALUE"


async def test_report_row_maps_domain_errors_to_400(db: AsyncSession) -> None:
    db.add(_report_row(row_code="BS-015", source_accounts=None, formula_used="ROW('BS-002')"))
    await db.flush()
    fk = next(f for f in sr.TRIAL_BALANCE.filter_keys if f.key == "report_row")

    with pytest.raises(HTTPException) as missing:
        await fk.resolver(_ctx(db=db), "balance_sheet:BS-404")
    assert missing.value.detail["error_code"] == "REPORT_ROW_NOT_GENERATED"
    assert missing.value.detail["message"] == "该报表行尚未生成，请先在报表页生成报表"

    with pytest.raises(HTTPException) as empty:
        await fk.resolver(_ctx(db=db), "balance_sheet:BS-015")
    assert empty.value.detail["error_code"] == "REPORT_ROW_NO_ACCOUNTS"
    assert empty.value.detail["message"] == "该报表行没有直接取数的科目，请在报表页查看公式"


async def test_note_section_maps_domain_errors_to_400(db: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(ef, "project_template_type", _fake_template_type("soe"))
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="九、9",
        section_title="【测试】没有登记科目", is_deleted=False,
    ))
    await db.flush()
    fk = next(f for f in sr.TRIAL_BALANCE.filter_keys if f.key == "note_section")

    with pytest.raises(HTTPException) as missing:
        await fk.resolver(_ctx(db=db), "不存在的章节")
    assert missing.value.status_code == 400
    assert missing.value.detail["error_code"] == "NOTE_SECTION_NOT_FOUND"
    assert missing.value.detail["message"] == "本项目该年度没有这个附注章节"

    with pytest.raises(HTTPException) as empty:
        await fk.resolver(_ctx(db=db), "九、9")
    assert empty.value.detail["error_code"] == "NOTE_SECTION_NO_ACCOUNTS"
    assert empty.value.detail["message"] == "该附注章节没有登记对应科目"


def _fake_template_type(template_type: str):
    async def resolve(_ctx):
        return template_type

    return resolve


class _Scope:
    def __init__(self, sections) -> None:
        self.sections = sections
        self.codes = None


class _Cycle:
    def __init__(self, sections) -> None:
        self._scope = _Scope(sections)

    async def scope(self, project_id):  # noqa: ANN001
        return self._scope


async def test_note_section_outside_the_users_cycle_scope_is_403(db: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(ef, "project_template_type", _fake_template_type("soe"))
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="八、1",
        section_title="货币资金", is_deleted=False,
    ))
    await db.flush()
    fk = next(f for f in sr.TRIAL_BALANCE.filter_keys if f.key == "note_section")

    with pytest.raises(HTTPException) as err:
        await fk.resolver(_ctx(db=db, cycle=_Cycle(frozenset({"八、2"}))), "八、1")
    assert err.value.status_code == 403
    assert err.value.detail["error_code"] == "SECTION_OUT_OF_SCOPE"

    clause = await fk.resolver(_ctx(db=db, cycle=_Cycle(frozenset({"八、1"}))), "八、1")
    assert "IN (" in _pg(clause).upper()
    unrestricted = await fk.resolver(_ctx(db=db, cycle=_Cycle(None)), "八、1")
    assert _pg(unrestricted) == _pg(clause)


async def test_note_section_warning_names_the_workpapers(db: AsyncSession, monkeypatch) -> None:
    monkeypatch.setattr(ef, "project_template_type", _fake_template_type("soe"))
    db.add(DisclosureNote(
        id=uuid.uuid4(), project_id=_PID, year=2025, note_section="八、1",
        section_title="货币资金", is_deleted=False,
    ))
    await db.flush()
    fk = next(f for f in sr.TRIAL_BALANCE.filter_keys if f.key == "note_section")
    ctx = _ctx(db=db)
    await fk.resolver(ctx, "八、1")
    assert ef.entry_warnings(ctx) == [
        "「货币资金」的相关科目按底稿 E1、E1-1 登记的科目列出"
    ]


async def test_report_row_warning_quotes_the_formula(db: AsyncSession) -> None:
    db.add(_report_row(
        row_code="BS-006", source_accounts=["1122", "1231-02"],
        formula_used="TB('1122','期末余额') - TB('1231-02','期末余额')",
    ))
    await db.flush()
    fk = next(f for f in sr.TRIAL_BALANCE.filter_keys if f.key == "report_row")
    ctx = _ctx(db=db)
    await fk.resolver(ctx, "balance_sheet:BS-006")
    assert ef.entry_warnings(ctx) == [
        "构成科目按报表公式 TB('1122','期末余额') - TB('1231-02','期末余额') 的取数科目列出（含减项）"
    ]
    assert ctx.memo["entry_accounts"] == ("1122", "1231-02")


# ── meta.entry_accounts ──────────────────────────────────────────────────────


async def test_entry_accounts_are_sorted_deduplicated_and_capped() -> None:
    ctx = _ctx()
    ef.remember_entry_accounts(ctx, ["1002", "1001", "1002", " ", None])
    assert ctx.memo["entry_accounts"] == ("1001", "1002")
    ef.remember_entry_accounts(ctx, [f"9{i:03d}" for i in range(80)])
    assert len(ctx.memo["entry_accounts"]) == ea.MAX_ENTRY_ACCOUNTS
    assert ctx.memo["entry_accounts"][:2] == ("1001", "1002")


async def test_page_meta_omits_entry_accounts_when_no_entry_filter_was_used() -> None:
    ctx = _ctx()
    ctx.memo["template_type"] = "soe"
    meta = await paged_fetch._page_meta(ctx, [])
    assert "entry_accounts" not in meta

    ef.remember_entry_accounts(ctx, ["1001"])
    meta = await paged_fetch._page_meta(ctx, [])
    assert meta["entry_accounts"] == ["1001"]


def test_resolver_predicates_compile_on_sqlite_too() -> None:
    """注册表谓词在 SQLite 上也能编译（单元回归在 SQLite 上真实执行）。"""
    clause = ef.prefix_any(_LED_CODE, ["1001", "1002"])
    assert "LIKE" in str(clause.compile(dialect=sqlite.dialect())).upper()


async def test_filter_predicates_awaits_resolvers_and_keeps_other_keys_single_value() -> None:
    """``_filter_predicates`` 对 resolver 键放行多值，对普通键仍坚持单值（否则 dict / list 能绕进 SQL）。"""
    clauses = await paged_fetch._filter_predicates(
        sr.LEDGER_ENTRIES, _ctx(), {"account_code": ["1001", "1002"]},
    )
    assert len(clauses) == 1 and isinstance(clauses[0], sa.sql.elements.ClauseElement)

    with pytest.raises(HTTPException) as err:
        await paged_fetch._filter_predicates(
            sr.LEDGER_ENTRIES, _ctx(), {"voucher_no": ["A", "B"]},
        )
    assert err.value.detail["error_code"] == "INVALID_FILTER_VALUE"


async def test_unknown_filter_key_still_lists_the_new_keys() -> None:
    with pytest.raises(HTTPException) as err:
        await paged_fetch._filter_predicates(sr.LEDGER_ENTRIES, _ctx(), {"nope": "x"})
    assert err.value.detail["error_code"] == "UNKNOWN_FILTER_KEY"
    assert "wp_code" in err.value.detail["allowed"] and "account_code" in err.value.detail["allowed"]
