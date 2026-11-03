"""自动匹配防编码撞号（spec mapping-code-collision-and-fetch-by-mapping R1 / R2）。

真库：重庆医药集团四川医药 2025（《企业会计制度》编号）资产负债类 9 个一级科目按编码精确匹配错
（1501 固定资产 → 持有至到期投资 等）；辽宁 1407 发出商品 → 商品进销差价。
用真标准科目模板 + 客户科目表跑 auto_suggest / auto_match（SQLite）。
"""

import io

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_schemas import BasicInfoSchema
from app.models.base import Base
from app.services.account_name_compat import level1_name_from_detail, reliable_level1_name, same_account

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


async def _project(db, csv_rows: list[str]):
    from app.services import account_chart_service, project_wizard_service

    project = await project_wizard_service.create_project(BasicInfoSchema(
        client_name="撞号测试", company_code="91110000710931130E", short_name="撞号",
        audit_year=2025, project_type="annual", accounting_standard="enterprise",
    ), db)
    await account_chart_service.load_standard_template(project.id, "enterprise", db)
    csv = "科目编码,科目名称,借贷方向\n" + "\n".join(csv_rows) + "\n"
    await account_chart_service.import_client_chart(
        project.id, UploadFile(filename="c.csv", file=io.BytesIO(csv.encode("utf-8-sig"))), db,
    )
    return project


async def _suggest(db, csv_rows: list[str]) -> dict[str, object]:
    from app.services import mapping_service

    project = await _project(db, csv_rows)
    return {s.original_account_code: s for s in await mapping_service.auto_suggest(project.id, db)}


def _codes(got: dict, keys) -> dict[str, str | None]:
    return {k: (got[k].suggested_standard_code if k in got else None) for k in keys}


# 《企业会计制度》（2001）编号的一份账：资产负债类同码不同义 + 损益类 5xxx
_SYS2001 = [
    "1001,现金,借", "100101,人民币,借",
    "1131,应收账款,借", "113101,甲公司,借",
    "1133,其他应收款,借", "113301,业务周转金,借",
    "1231,低值易耗品,借",
    "1301,待摊费用,借", "130101,保险费,借",
    "1401,长期股权投资,借",
    "1501,固定资产,借", "150101,房屋建筑物,借",
    "1502,累计折旧,贷",
    "1603,在建工程,借",
    "1701,固定资产清理,借",
    "1801,无形资产,借",
    "2151,应付工资,贷",
    "2171,应交税金,贷",
    "2181,其他应付款,贷", "218110,借款,贷",
    "3101,实收资本,贷", "310101,北京M餐饮有限公司,贷",
    "3141,利润分配,贷",
    "5101,主营业务收入,贷", "5102,其他业务收入,贷", "5401,主营业务成本,借",
    "5501,营业费用,借", "5502,管理费用,借", "5503,财务费用,借",
]


@pytest.mark.asyncio
async def test_legacy_balance_sheet_codes_matched_by_name_not_code(db):
    got = await _suggest(db, _SYS2001)
    assert _codes(got, ["1501", "1502", "1231", "1401", "1603", "1701", "1801", "3101", "1131"]) == {
        "1501": "1601",  # 固定资产（原：持有至到期投资）
        "1502": "1602",  # 累计折旧（原：持有至到期投资减值准备）
        "1231": "1411",  # 低值易耗品 → 周转材料（原：坏账准备）
        "1401": "1511",  # 长期股权投资（原：材料采购）
        "1603": "1604",  # 在建工程（原：固定资产减值准备）
        "1701": "1606",  # 固定资产清理（原：无形资产）
        "1801": "1701",  # 无形资产（原：长期待摊费用）
        "3101": "3001",  # 实收资本（原：盈余公积）
        "1131": "1122",  # 应收账款（原：应收股利）
    }
    assert got["1501"].match_method == "level1_name"
    assert got["1231"].match_method == "level1_synonym"


@pytest.mark.asyncio
async def test_legacy_synonyms_and_name_matches(db):
    got = await _suggest(db, _SYS2001)
    assert _codes(got, ["1001", "2151", "2171", "1133", "2181", "3141"]) == {
        "1001": "1001",  # 现金 ≈ 库存现金：编码认、名称兼容
        "2151": "2211",  # 应付工资 → 应付职工薪酬（同义表，先于模糊匹配；模糊会配成应付账款）
        "2171": "2221",  # 应交税金 → 应交税费
        "1133": "1221",  # 其他应收款（编码不在标准表，按名称）
        "2181": "2241",  # 其他应付款
        "3141": "3201",  # 利润分配
    }


@pytest.mark.asyncio
async def test_details_follow_level1(db):
    got = await _suggest(db, _SYS2001)
    # 编码撞号的一级科目下的明细跟随一级科目（不再前 4 位落到持有至到期投资 / 盈余公积）
    # 100101 人民币：标准科目表本身有 100101 人民币、一级科目「现金 ≈ 库存现金」兼容 ⇒ 照常按完整码认
    assert _codes(got, ["150101", "310101", "113301", "218110", "113101", "100101"]) == {
        "150101": "1601", "310101": "3001", "113301": "1221", "218110": "2241", "113101": "1122", "100101": "100101",
    }
    assert got["150101"].match_method == "inherit_parent"


@pytest.mark.asyncio
async def test_unknown_level1_left_unmapped_and_details_do_not_guess(db):
    got = await _suggest(db, _SYS2001)
    # 待摊费用：编码 1301 撞「贴现资产」，名称在标准表 / 同义表都没有 ⇒ 不自动映射，明细也不按「保险费」猜
    assert "1301" not in got and "130101" not in got


@pytest.mark.asyncio
async def test_legacy_pl_crosswalk_and_bad_debt_priority_unchanged(db):
    got = await _suggest(db, _SYS2001)
    assert _codes(got, ["5101", "5102", "5401", "5501", "5502", "5503"]) == {
        "5101": "6001", "5102": "6051", "5401": "6401", "5501": "6601", "5502": "6602", "5503": "6603",
    }
    assert {got[k].match_method for k in ("5101", "5501")} == {"legacy_pl_crosswalk"}


@pytest.mark.asyncio
async def test_new_standard_chart_keeps_code_matches(db):
    got = await _suggest(db, [
        "1001,库存现金,借", "1122,应收账款,借", "112201,甲公司,借", "1601,固定资产,借", "160101,房屋及建筑物,借",
        "2211,应付职工薪酬,贷", "221101,工资,贷", "4001,生产成本,借", "6001,主营业务收入,贷",
    ])
    assert _codes(got, ["1001", "1122", "112201", "1601", "160101", "2211", "221101", "4001", "6001"]) == {
        "1001": "1001", "1122": "1122", "112201": "1122", "1601": "1601", "160101": "1601",
        "2211": "2211", "221101": "221101", "4001": "4001", "6001": "6001",
    }
    assert got["1601"].match_method == "exact_code" and got["160101"].match_method == "prefix"


@pytest.mark.asyncio
async def test_level1_name_taken_from_detail_when_no_level1_row(db):
    """辽宁：权益类用 4xxx（4001 实收资本、4104 利润分配），没有一级科目行，只有「实收资本_国有资本」这类明细。"""
    got = await _suggest(db, [
        "4001.01,实收资本_国有资本,贷", "4001.03,实收资本_民营资本,贷", "4104.01,利润分配_提取法定盈余公积,贷",
        "1407,发出商品,借",
    ])
    assert _codes(got, ["4001.01", "4001.03", "4104.01", "1407"]) == {
        "4001.01": "3001", "4001.03": "3001", "4104.01": "3201", "1407": "1406",
    }


@pytest.mark.asyncio
async def test_ten_digit_codes_without_level1_rows(db):
    """北京那份账：10 位编码、没有一级科目行，明细名是「第二级名-第三级名」。

    「人工费用」「福利费」对不上标准一级科目 ⇒ 不推一级科目名、照常按 6601 认（首版把它们当撞号、13 个费用科目配不上）；
    「实收资本」「盈余公积-…」对上 3001 / 3101 ⇒ 4001 生产成本 / 4101 制造费用 按撞号处理。
    """
    got = await _suggest(db, [
        "6601030000,人工费用-工资津贴补贴,借", "6601030001,人工费用-奖金,借", "6601040000,福利费-宿舍费用,借",
        "6601100000,办公费,借", "1122010000,应收账款-外部,借",
        "4001010000,实收资本,贷", "4101010000,盈余公积-法定公积金,贷", "4002020000,资本公积-其他资本公积,贷",
    ])
    assert _codes(got, ["6601030000", "6601030001", "6601040000", "6601100000", "1122010000"]) == {
        "6601030000": "6601", "6601030001": "6601", "6601040000": "6601", "6601100000": "6601", "1122010000": "1122",
    }
    assert {got[k].match_method for k in ("6601030000", "6601100000")} == {"prefix"}
    assert _codes(got, ["4001010000", "4101010000", "4002020000"]) == {
        "4001010000": "3001", "4101010000": "3101", "4002020000": "3002",
    }


@pytest.mark.asyncio
async def test_inconsistent_derived_level1_is_not_used(db):
    """没有一级科目行、明细推出来的一级科目互相矛盾（管理费用-… / 财务费用-… 挂在 6601 下）：不推，照常按编码认。"""
    got = await _suggest(db, ["6601030000,管理费用-办公费,借", "6601040000,财务费用-手续费,借"])
    assert _codes(got, ["6601030000", "6601040000"]) == {"6601030000": "6601", "6601040000": "6601"}


@pytest.mark.asyncio
async def test_fuzzy_never_crosses_current_and_noncurrent(db):
    """ABC餐饮 1302 其他流动资产曾按字面模糊配到 1519 其他非流动金融资产，明细随之跟进：现在一级不配，明细各按自己匹配。"""
    got = await _suggest(db, ["1302,其他流动资产,借", "130201,待认证进项税额,借", "130202,预缴企业所得税,借"])
    assert "1302" not in got
    assert all(s.suggested_standard_code != "1519" for s in got.values())


@pytest.mark.asyncio
async def test_children_of_fuzzy_level1_do_not_inherit(db):
    """一级科目只是模糊认出来的（预付账款项 ≈ 预付账款）：明细不跟随，按自己的名称匹配。"""
    got = await _suggest(db, ["1199,预付账款项,借", "119901,银行存款,借"])
    assert got["1199"].match_method == "fuzzy_name" and got["1199"].suggested_standard_code == "1123"
    assert got["119901"].suggested_standard_code == "1002" and got["119901"].match_method == "exact_name"


@pytest.mark.asyncio
async def test_find_code_collisions_covers_separator_stripped_code(db):
    """辽宁 4001.01 实收资本_国有资本 → 400101（生产成本-直接材料）：按去分隔符的完整码认出来的撞号也要列出。"""
    from app.models.audit_platform_models import AccountMapping, MappingType
    from app.services.mapping_level1_match import find_code_collisions

    project = await _project(db, ["4001.01,实收资本_国有资本,贷", "4001.03,实收资本_民营资本,贷", "1001,库存现金,借"])
    for code, std in (("4001.01", "400101"), ("4001.03", "400103"), ("1001", "1001")):
        db.add(AccountMapping(project_id=project.id, original_account_code=code, standard_account_code=std,
                              mapping_type=MappingType.auto_exact))
    await db.commit()
    found = {c["code"]: (c["old_code"], c["new_code"]) for c in await find_code_collisions(project.id, db)}
    assert found == {"4001.01": ("400101", "3001"), "4001.03": ("400103", "3001")}


@pytest.mark.asyncio
async def test_unreliable_level1_name_keeps_code_match(db):
    """旧导入把上级科目路径当名称（「\\银行存款」挂在 1122 上）：名称不可信 ⇒ 不做名称校验，按编码认（原逻辑）。"""
    got = await _suggest(db, ["1122,\\银行存款,借", "112201,\\应收账款,借"])
    assert _codes(got, ["1122", "112201"]) == {"1122": "1122", "112201": "1122"}


@pytest.mark.asyncio
async def test_auto_match_skips_existing_mapping_by_normalized_code(db):
    """旧映射「1133.0」与新科目「1133」是同一科目：自动匹配不再插第二条。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountMapping, MappingType
    from app.services import mapping_service

    project = await _project(db, ["1001,库存现金,借", "1133,其他应收款,借"])
    db.add(AccountMapping(project_id=project.id, original_account_code="1133.0", original_account_name="其他应收款",
                          standard_account_code="1221", mapping_type=MappingType.manual))
    await db.commit()
    result = await mapping_service.auto_match(project.id, db)
    codes = (await db.execute(sa.select(AccountMapping.original_account_code).where(
        AccountMapping.project_id == project.id, AccountMapping.is_deleted == sa.false()))).scalars().all()
    assert sorted(codes) == ["1001", "1133.0"]
    assert result.saved_count == 1 and result.skipped_count == 1


@pytest.mark.asyncio
async def test_detail_under_unmatched_level1_does_not_guess_by_own_name(db):
    """一级科目「自定义科目」（编码不在标准表、名称也认不出）没匹配上：明细「银行存款」不按自己的名称配到 1002。"""
    got = await _suggest(db, ["9901,自定义科目,借", "990101,银行存款,借"])
    assert "9901" not in got and "990101" not in got


@pytest.mark.asyncio
async def test_level1_name_containment_counts_as_same_account(db):
    """客户一级科目名带括号说明（「应收账款（货款）」）：包含标准名 ⇒ 同一科目，照常按编码认。"""
    got = await _suggest(db, ["1122,应收账款（货款）,借", "112201,甲公司,借"])
    assert _codes(got, ["1122", "112201"]) == {"1122": "1122", "112201": "1122"}
    assert got["1122"].match_method == "exact_code"


@pytest.mark.asyncio
async def test_auto_match_skips_dot_zero_client_code_already_mapped(db):
    """客户科目表还是旧导入的「1133.0」、映射已有「1133」：同一科目，不再插「1133.0」。"""
    import sqlalchemy as sa

    from app.models.audit_platform_models import AccountChart, AccountMapping, AccountSource, MappingType
    from app.services import mapping_service

    project = await _project(db, ["1001,库存现金,借"])
    chart = (await db.execute(sa.select(AccountChart).where(
        AccountChart.project_id == project.id, AccountChart.source == AccountSource.client))).scalars().one()
    db.add(AccountChart(project_id=project.id, account_code="1133.0", account_name="其他应收款", direction=chart.direction,
                        level=1, category=chart.category, source=AccountSource.client))
    db.add(AccountMapping(project_id=project.id, original_account_code="1133", original_account_name="其他应收款",
                          standard_account_code="1221", mapping_type=MappingType.manual))
    await db.commit()
    result = await mapping_service.auto_match(project.id, db)
    codes = (await db.execute(sa.select(AccountMapping.original_account_code).where(
        AccountMapping.project_id == project.id, AccountMapping.is_deleted == sa.false()))).scalars().all()
    assert sorted(codes) == ["1001", "1133"]
    assert result.skipped_count == 1


def test_std_name_index_prefers_new_6xxx_code():
    """标准科目表同名两码（5001 / 6001 主营业务收入）：按名称认时取新准则 6001（报表公式只读 6xxx）。"""
    from app.models.audit_platform_models import AccountChart
    from app.services.mapping_level1_match import std_name_index

    index = std_name_index([AccountChart(account_code="5001", account_name="主营业务收入"),
                            AccountChart(account_code="6001", account_name="主营业务收入"),
                            AccountChart(account_code="1231-01", account_name="坏账准备-应收票据")])
    assert index["主营业务收入"].account_code == "6001"
    assert "坏账准备-应收票据" not in index  # 二级科目不参与按名称认一级


def test_name_compat_helpers():
    assert same_account("现金", "库存现金") and same_account("应付工资", "应付职工薪酬")
    assert same_account("应收帐款", "应收账款")
    assert not same_account("固定资产", "持有至到期投资") and not same_account("低值易耗品", "坏账准备")
    assert not same_account("发出商品", "商品进销差价") and not same_account("实收资本", "盈余公积")
    # 辽宁用报表行名当科目名：营业收入 / 营业成本 与 6001 / 6401 是同一科目（预览时首版误判成撞号）
    assert same_account("营业收入", "主营业务收入") and same_account("营业成本", "主营业务成本")
    assert level1_name_from_detail("实收资本_国有资本") == "实收资本"
    assert level1_name_from_detail("\\其他应付款\\北京某公司") == "其他应付款"
    assert level1_name_from_detail("房屋建筑物") is None
    assert reliable_level1_name("\\银行存款") is None and reliable_level1_name("固定资产") == "固定资产"
    from app.services.account_name_compat import current_noncurrent_conflict
    assert current_noncurrent_conflict("其他流动资产", "其他非流动金融资产")
    assert not current_noncurrent_conflict("其他非流动资产", "其他非流动金融资产")
    assert not current_noncurrent_conflict("其他流动资产", "其他应收款")
