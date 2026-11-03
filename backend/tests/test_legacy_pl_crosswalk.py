"""旧编码体系损益科目自动映射到新准则 6xxx（spec legacy-pl-account-crosswalk-mapping）。

真库：重庆医药集团四川医药 / 新健康大药房临港店 2025，客户损益科目是《企业会计制度》编码，
按编码落到标准科目表的 5xxx ⇒ 利润表（只读 6xxx）全 0，且 5501 营业费用 → 5403 营业税金及附加 等错位。
"""

import io

import pytest
import pytest_asyncio
from fastapi import UploadFile
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_schemas import BasicInfoSchema
from app.models.base import Base
from app.services.legacy_pl_crosswalk import (
    ENTERPRISE_SYSTEM_2001,
    SMALL_ENTERPRISE_2013,
    crosswalk_target,
    detect_legacy_pl_crosswalk,
    level1_code,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

#: 真库那份账的损益一级码（《企业会计制度》，带 Excel 读出的 .0 尾巴）
_SW_PL = ["5101.0", "5102.0", "5203.0", "5301.0", "5401.0", "5402.0", "5405.0",
          "5501.0", "5502.0", "5503.0", "5601.0", "5701.0", "5801.0"]


# ── 判定（纯函数）──────────────────────────────────────────────────────────


def test_detects_enterprise_system_2001_on_real_codes():
    got = detect_legacy_pl_crosswalk(["1001.0", "1122.0", *_SW_PL, "550201.0"])
    assert got is not None and got[0] == ENTERPRISE_SYSTEM_2001


def test_detects_small_enterprise_2013():
    got = detect_legacy_pl_crosswalk(["1001", "5001", "5051", "5401", "5602", "5603", "5711", "5801"])
    assert got is not None and got[0] == SMALL_ENTERPRISE_2013


def test_new_standard_chart_is_excluded():
    """新准则建筑企业：5001 生产成本 + 5403 机械作业 恰好凑够小企业特征码 2 个，
    只有「有 6xxx 损益码 ⇒ 新准则」这条能挡住（否则 5001 生产成本会被映射成收入）。"""
    codes = ["5001", "5101", "5201", "5401", "5402", "5403", "6001", "6401", "6602"]
    assert detect_legacy_pl_crosswalk(codes) is None


def test_cost_only_new_standard_chart_is_not_misread():
    """只有成本类 5xxx（还没有损益科目）的新准则账套：小企业侧只命中 5001 一个，不满足「至少 2 个」。"""
    assert detect_legacy_pl_crosswalk(["1001", "5001", "5101", "5301"]) is None


def test_balance_only_chart_is_not_misread():
    assert detect_legacy_pl_crosswalk(["1001", "1002", "1122", "2202", "4001"]) is None


@pytest.mark.parametrize("code", ["5501", "5501.0", "550101", "5501.01", "5501-01", "550101.0"])
def test_children_and_code_forms_follow_level1(code):
    _, cw = detect_legacy_pl_crosswalk(_SW_PL)
    assert crosswalk_target(code, cw) == "6601"


def test_level1_code_keeps_real_dotted_codes():
    assert level1_code("1002.10") == "1002"
    assert level1_code("100201.0") == "1002"


@pytest.mark.parametrize("old,new", [
    ("5101", "6001"), ("5402", "6403"), ("5405", "6402"), ("5501", "6601"),
    ("5601", "6711"), ("5701", "6801"), ("5801", "6901"),
])
def test_enterprise_system_crosswalk_values(old, new):
    """同码不同义的几条：真库按编码映射时恰好全错。"""
    _, cw = detect_legacy_pl_crosswalk(_SW_PL)
    assert crosswalk_target(old, cw) == new


# ── auto_suggest 集成（真标准科目模板：同时含 5xxx 与 6xxx）──────────────────

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


async def _suggest(db, csv_rows: list[str], *, drop_standard: tuple[str, ...] = ()) -> dict[str, object]:
    """建项目 + 标准模板 + 客户科目表，可先软删若干标准科目，再跑 auto_suggest。"""
    from sqlalchemy import update

    from app.models.audit_platform_models import AccountChart, AccountSource
    from app.services import account_chart_service, mapping_service, project_wizard_service

    project = await project_wizard_service.create_project(BasicInfoSchema(
        client_name="旧制度映射测试", company_code="91110000710931130E", short_name="旧制度",
        audit_year=2025, project_type="annual", accounting_standard="enterprise",
    ), db)
    await account_chart_service.load_standard_template(project.id, "enterprise", db)
    csv = "科目编码,科目名称,借贷方向\n" + "\n".join(csv_rows) + "\n"
    await account_chart_service.import_client_chart(
        project.id, UploadFile(filename="c.csv", file=io.BytesIO(csv.encode("utf-8-sig"))), db,
    )
    if drop_standard:
        await db.execute(update(AccountChart).where(
            AccountChart.project_id == project.id,
            AccountChart.source == AccountSource.standard,
            AccountChart.account_code.in_(drop_standard),
        ).values(is_deleted=True))
        await db.commit()
    return {s.original_account_code: s for s in await mapping_service.auto_suggest(project.id, db)}


_SW_CSV = [
    "1001,库存现金,借", "1122,应收账款,借",
    "5101,主营业务收入,贷", "510101,药品收入,贷", "5102,其他业务收入,贷",
    "5401,主营业务成本,借", "5402,税金及附加,借", "5501,营业费用,借", "550101,工资,借",
    "5502,管理费用,借", "5503,财务费用,借", "5601,营业外支出,借", "5701,所得税,借",
]


@pytest.mark.asyncio
async def test_auto_suggest_maps_legacy_pl_to_new_standard(db):
    got = await _suggest(db, _SW_CSV)
    expect = {"5101": "6001", "510101": "6001", "5102": "6051", "5401": "6401", "5402": "6403",
              "5501": "6601", "550101": "6601", "5502": "6602", "5503": "6603", "5601": "6711", "5701": "6801"}
    assert {k: got[k].suggested_standard_code for k in expect} == expect
    assert {got[k].match_method for k in expect} == {"legacy_pl_crosswalk"}
    # 资产负债类不受影响
    assert got["1001"].suggested_standard_code == "1001"
    assert got["1122"].match_method != "legacy_pl_crosswalk"


@pytest.mark.asyncio
async def test_auto_suggest_new_standard_chart_unchanged(db):
    """新准则账套：5001 生产成本 / 5403 机械作业 不被当成收入 / 税金及附加。

    原断言 ``5001 → 5001``：标准科目表 5001 是「主营业务收入」，按编码认就是把生产成本当收入（同码不同义）。
    spec mapping-code-collision-and-fetch-by-mapping 后按名称改配 4001 生产成本 / 4403 机械作业。
    """
    got = await _suggest(db, [
        "1001,库存现金,借", "5001,生产成本,借", "5403,机械作业,借",
        "6001,主营业务收入,贷", "6401,主营业务成本,借",
    ])
    assert got["5001"].suggested_standard_code == "4001"
    assert got["5403"].suggested_standard_code == "4403"
    assert got["6001"].suggested_standard_code == "6001"
    assert all(s.match_method != "legacy_pl_crosswalk" for s in got.values())


@pytest.mark.asyncio
async def test_missing_target_in_standard_chart_falls_back(db):
    """目标码不在本项目标准科目表 ⇒ 走原逻辑（不产出指向不存在科目的映射）。"""
    got = await _suggest(db, _SW_CSV, drop_standard=("6601",))
    # 原逻辑下「营业费用」名称也匹配不到 ⇒ 不出建议（留给人工），绝不能指向已删的 6601
    s5501 = got.get("5501")
    assert s5501 is None or (s5501.match_method != "legacy_pl_crosswalk" and s5501.suggested_standard_code != "6601")
    assert got["5101"].suggested_standard_code == "6001"
