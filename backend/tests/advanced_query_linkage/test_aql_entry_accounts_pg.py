"""W6 业务对象 → 科目的真 PostgreSQL 金标准（任务 45；design §10.2「报表行构成科目」「附注章节与底稿」）。

真实数据只读；需要造数的两处（子科目、范围外章节、表侧映射）都在同一回滚事务里造。项目按未删除项目名称现取 UUID。

**R14.6 快照已过期**：需求里写的「华氏 BS-002 = 822,999,085.83」在共享库整体重建后不再成立，现查为 112,166,836.03。
本文件不引用快照数字，一律现算金标准（报表行金额与试算表审定数之和互为对照），并把两者相等本身作为判据。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import sqlalchemy as sa

import app.core.redis as core_redis
from app.models.audit_platform_models import TrialBalance
from app.models.note_account_mapping import NoteAccountMapping
from app.models.report_models import DisclosureNote
from app.services.custom_query import entry_accounts as ea
from tests.advanced_query_linkage.gold import AUDIT_YEAR, active_sql

pytestmark = pytest.mark.pg_only
CQ = "/api/custom-query"
PROJECTS = {
    "hs": "陕西华氏医药有限公司_2025",
    "hp": "重庆和平药房连锁有限责任公司_2025",
    "ah": "重药控股安徽有限公司_2025",
}
TB_ACTIVE = (
    "t.project_id = :pid AND t.year = :year AND NOT t.is_deleted"
)


async def _project_id(gold, name: str) -> uuid.UUID:
    rows = await gold.rows(
        "SELECT id FROM projects WHERE name=:name AND NOT is_deleted ORDER BY id", name=name,
    )
    assert len(rows) == 1, f"前置：未删除项目「{name}」应恰好一条，实得 {len(rows)} 条"
    return rows[0][0]


# ── 报表行构成科目 ───────────────────────────────────────────────────────────


async def test_report_row_entry_matches_the_report_amount(business, gold) -> None:
    """华氏 BS-002：按 ``report_row`` 取到的试算表行，审定数之和 = 报表本期金额（现算，不用过期快照）。"""
    pid = await _project_id(gold, PROJECTS["hs"])
    report = (await gold.rows(
        "SELECT current_period_amount, source_accounts::text, formula_used FROM financial_report "
        "WHERE project_id=:pid AND year=:year AND report_type::text='balance_sheet' AND row_code='BS-002' "
        "AND NOT is_deleted", pid=pid, year=AUDIT_YEAR,
    ))[0]
    report_amount = Decimal(str(report[0]))
    assert '["1001", "1002", "1012"]' == report[1], f"前置：取数科目现为 {report[1]}"

    gold_sum = Decimal(str(await gold.scalar(
        f"SELECT COALESCE(sum(t.audited_amount),0) FROM trial_balance t WHERE {TB_ACTIVE} AND ("
        "t.standard_account_code LIKE '1001%' OR t.standard_account_code LIKE '1002%' "
        "OR t.standard_account_code LIKE '1012%')", pid=pid, year=AUDIT_YEAR,
    )))
    assert gold_sum == report_amount, "报表本期金额应等于其取数科目的审定数之和"

    data = await business.ok(pid, "tb_detail", filters={"report_row": "balance_sheet:BS-002"}, limit=2000)
    assert data["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM trial_balance t WHERE {TB_ACTIVE} AND ("
        "t.standard_account_code LIKE '1001%' OR t.standard_account_code LIKE '1002%' "
        "OR t.standard_account_code LIKE '1012%')", pid=pid, year=AUDIT_YEAR,
    ))
    assert sum((Decimal(str(r["audited_amount"] or 0)) for r in data["rows"]), Decimal()) == report_amount
    assert data["meta"]["entry_accounts"] == ["1001", "1002", "1012"]
    assert any("含减项" in w and report[2] in w for w in data["warnings"]), data["warnings"]


async def test_report_row_prefix_also_catches_sub_accounts_created_in_this_transaction(business, gold) -> None:
    """单码按前缀：同一回滚事务里给该项目加一个 ``1002`` 的子科目行，结果与报表取数口径一起变大。"""
    pid = await _project_id(gold, PROJECTS["hs"])
    before = await business.ok(pid, "tb_detail", filters={"report_row": "balance_sheet:BS-002"}, limit=2000)
    existing = {row["standard_account_code"] for row in before["rows"]}
    sub_code = next(f"100201{i:02d}" for i in range(99) if f"100201{i:02d}" not in existing)

    # 按同项目真实行克隆一份（不逐列硬编码：trial_balance 有多列 NOT NULL，将来加列也不会让夹具失效）
    template = (await business.session.execute(
        sa.select(TrialBalance).where(
            TrialBalance.project_id == pid, TrialBalance.year == AUDIT_YEAR,
            TrialBalance.is_deleted.is_(False),
        ).order_by(TrialBalance.standard_account_code).limit(1)
    )).scalar_one()
    skip = {"id", "created_at", "updated_at"}
    clone = TrialBalance(**{
        column.name: getattr(template, column.name)
        for column in TrialBalance.__table__.columns if column.name not in skip
    })
    clone.id = uuid.uuid4()
    clone.standard_account_code = sub_code
    clone.account_name = "【测试】W6 子科目"
    for name in ("opening_balance", "unadjusted_amount", "rje_adjustment", "aje_adjustment"):
        if hasattr(clone, name):
            setattr(clone, name, Decimal("0"))
    clone.audited_amount = Decimal("1234.56")
    business.session.add(clone)
    await business.session.flush()
    await core_redis.redis_client.flushdb()

    after = await business.ok(pid, "tb_detail", filters={"report_row": "balance_sheet:BS-002"}, limit=2000)
    assert after["total"] == before["total"] + 1
    assert sub_code in {row["standard_account_code"] for row in after["rows"]}
    delta = sum((Decimal(str(r["audited_amount"] or 0)) for r in after["rows"]), Decimal()) - sum(
        (Decimal(str(r["audited_amount"] or 0)) for r in before["rows"]), Decimal())
    assert delta == Decimal("1234.56")


async def test_report_row_range_uses_between(business, gold) -> None:
    """``起~止`` 走 BETWEEN：华氏 BS-010（存货，``1401~1499``）与独立 SQL 的区间计数一致。"""
    pid = await _project_id(gold, PROJECTS["hs"])
    sources = (await gold.rows(
        "SELECT source_accounts::text FROM financial_report WHERE project_id=:pid AND year=:year "
        "AND report_type::text='balance_sheet' AND row_code='BS-010' AND NOT is_deleted",
        pid=pid, year=AUDIT_YEAR,
    ))[0][0]
    assert "~" in sources, f"前置：BS-010 的取数科目应是区间，实为 {sources}"

    data = await business.ok(pid, "tb_detail", filters={"report_row": "balance_sheet:BS-010"}, limit=2000)
    assert data["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM trial_balance t WHERE {TB_ACTIVE} "
        "AND t.standard_account_code BETWEEN '1401' AND '1499'", pid=pid, year=AUDIT_YEAR,
    ))


async def test_total_row_and_missing_row_are_4xx_not_500(business, gold) -> None:
    """合计行（``source_accounts`` 为 JSON null）与不存在的行次：直接调接口也只拿到 400。"""
    pid = await _project_id(gold, PROJECTS["hs"])
    total_row = (await gold.rows(
        "SELECT row_code, is_total_row, source_accounts::text FROM financial_report "
        "WHERE project_id=:pid AND year=:year AND report_type::text='balance_sheet' AND is_total_row "
        "AND jsonb_typeof(source_accounts)='null' AND NOT is_deleted ORDER BY row_code LIMIT 1",
        pid=pid, year=AUDIT_YEAR,
    ))
    assert total_row, "前置：该项目应有 source_accounts 为 JSON null 的合计行"
    code = total_row[0][0]

    detail = await business.error(pid, "tb_detail", 400, filters={"report_row": f"balance_sheet:{code}"})
    assert detail["error_code"] == "REPORT_ROW_NO_ACCOUNTS"
    assert detail["message"] == "该报表行没有直接取数的科目，请在报表页查看公式"

    detail = await business.error(pid, "tb_detail", 400, filters={"report_row": "balance_sheet:BS-99999"})
    assert detail["error_code"] == "REPORT_ROW_NOT_GENERATED"


# ── 附注章节与底稿 ───────────────────────────────────────────────────────────


async def test_note_section_entry_matches_the_workpaper_mapping(business, gold) -> None:
    """安徽「八、1 货币资金」：经底稿 E1 / E1-1 解析到 1001 / 1002 / 1012，与独立 SQL 的等值计数一致。"""
    pid = await _project_id(gold, PROJECTS["ah"])
    title = await gold.scalar(
        "SELECT section_title FROM disclosure_notes WHERE project_id=:pid AND year=:year "
        "AND note_section='八、1' AND NOT is_deleted", pid=pid, year=AUDIT_YEAR,
    )
    assert title == "货币资金", f"前置：安徽「八、1」现为「{title}」"
    codes = list(ea.codes_for_wp_code("E1"))
    assert codes == ["1001", "1002", "1012"]

    data = await business.ok(pid, "tb_detail", filters={"note_section": "八、1"}, limit=2000)
    assert data["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM trial_balance t WHERE {TB_ACTIVE} "
        "AND t.standard_account_code = ANY(:codes)", pid=pid, year=AUDIT_YEAR, codes=codes,
    ))
    assert data["meta"]["entry_accounts"] == codes
    assert any("E1、E1-1" in w for w in data["warnings"]), data["warnings"]


async def test_note_section_table_side_mapping_is_wired(business, gold) -> None:
    """design 原定的唯一来源 ``note_account_mappings`` 现查 **0 行**；在回滚事务里填一条证明这条支路真的接着。"""
    pid = await _project_id(gold, PROJECTS["ah"])
    assert int(await gold.scalar("SELECT count(*) FROM note_account_mappings")) == 0, (
        "若该表已被填充，请重新评估 entry_accounts 的两源并集口径"
    )
    section = "【测试】W6 仅表侧登记"
    business.session.add(DisclosureNote(
        id=uuid.uuid4(), project_id=pid, year=AUDIT_YEAR, note_section=section,
        section_title=section, is_deleted=False,
    ))
    business.session.add(NoteAccountMapping(
        template_type="soe_standalone", report_row_code="BS-006",
        note_section_code=section, table_index=0, wp_code="D2",
    ))
    await business.session.flush()
    await core_redis.redis_client.flushdb()

    assert ea.wp_codes_for_note_section(section, "soe") == (), "前置：JSON 侧不认这个章节"
    data = await business.ok(pid, "tb_detail", filters={"note_section": section}, limit=2000)
    assert data["meta"]["entry_accounts"] == list(ea.codes_for_wp_code("D2"))
    assert data["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM trial_balance t WHERE {TB_ACTIVE} "
        "AND t.standard_account_code = ANY(:codes)",
        pid=pid, year=AUDIT_YEAR, codes=list(ea.codes_for_wp_code("D2")),
    ))


async def test_unknown_section_and_section_without_accounts(business, gold) -> None:
    pid = await _project_id(gold, PROJECTS["ah"])
    detail = await business.error(pid, "tb_detail", 400, filters={"note_section": "不存在的章节"})
    assert detail["error_code"] == "NOTE_SECTION_NOT_FOUND"
    assert detail["message"] == "本项目该年度没有这个附注章节"

    bare = (await gold.rows(
        "SELECT note_section FROM disclosure_notes d WHERE d.project_id=:pid AND d.year=:year "
        "AND NOT d.is_deleted ORDER BY d.sort_index", pid=pid, year=AUDIT_YEAR,
    ))
    unmapped = next(
        row[0] for row in bare if not ea.wp_codes_for_note_section(row[0], "soe")
    )
    detail = await business.error(pid, "tb_detail", 400, filters={"note_section": unmapped})
    assert detail["error_code"] == "NOTE_SECTION_NO_ACCOUNTS"
    assert detail["message"] == "该附注章节没有登记对应科目"


# ── 底稿编码与多值科目（账簿侧）────────────────────────────────────────────


async def test_wp_code_entry_on_the_ledger_matches_the_prefix_count(business, gold) -> None:
    """和平药房底稿 E1 → 序时账：total = 独立 SQL 的三个前缀 OR 计数。"""
    pid = await _project_id(gold, PROJECTS["hp"])
    data = await business.ok(pid, "ledger_entries", filters={"wp_code": "E1"}, limit=100)
    expected = int(await gold.scalar(
        f"SELECT count(*) FROM tb_ledger t WHERE {active_sql('t')} AND (t.account_code LIKE '1001%' "
        "OR t.account_code LIKE '1002%' OR t.account_code LIKE '1012%')", pid=pid, year=AUDIT_YEAR,
    ))
    assert data["total"] == expected
    assert data["meta"]["entry_accounts"] == ["1001", "1002", "1012"]


async def test_account_code_single_and_multi_value_agree_with_independent_sql(business, gold) -> None:
    pid = await _project_id(gold, PROJECTS["hp"])
    single = await business.ok(pid, "ledger_entries", filters={"account_code": "1002"}, limit=1)
    assert single["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM tb_ledger t WHERE {active_sql('t')} AND t.account_code LIKE '1002%'",
        pid=pid, year=AUDIT_YEAR,
    ))

    multi = await business.ok(pid, "ledger_entries", filters={"account_code": ["1002", "1001"]}, limit=1)
    assert multi["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM tb_ledger t WHERE {active_sql('t')} AND (t.account_code LIKE '1001%' "
        "OR t.account_code LIKE '1002%')", pid=pid, year=AUDIT_YEAR,
    ))
    assert multi["total"] >= single["total"]
    assert multi["meta"]["entry_accounts"] == ["1001", "1002"]


async def test_wp_code_alone_satisfies_the_aux_ledger_required_filter(business, gold) -> None:
    """辅助明细只带 ``wp_code`` 时不得再报 ``AUX_FILTER_REQUIRED``（底稿入口切到辅助明细的落点）。"""
    pid = await _project_id(gold, PROJECTS["hp"])
    data = await business.ok(pid, "aux_ledger", filters={"wp_code": "E1"}, limit=1)
    assert data["total"] == int(await gold.scalar(
        f"SELECT count(*) FROM tb_aux_ledger t WHERE {active_sql('t')} AND (t.account_code LIKE '1001%' "
        "OR t.account_code LIKE '1002%' OR t.account_code LIKE '1012%')", pid=pid, year=AUDIT_YEAR,
    ))
    detail = await business.error(pid, "aux_ledger", 400)
    assert detail["error_code"] == "AUX_FILTER_REQUIRED"


async def test_wp_code_without_accounts_is_a_400_on_the_real_route(business, gold) -> None:
    pid = await _project_id(gold, PROJECTS["hp"])
    detail = await business.error(pid, "ledger_entries", 400, filters={"wp_code": "A1"})
    assert detail["error_code"] == "WP_CODE_NO_ACCOUNTS"
    assert detail["message"] == "该底稿没有登记对应科目"
