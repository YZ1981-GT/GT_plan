"""地址库附注域只登记取得到数的引用（spec formula-fetch-followup-defect-closure 7.2 浏览器实测发现）。

公式选择器 / 公式栏插入的是地址库登记的引用写法（R3）。原先每张附注表的每个表头都登记一条
``NOTE('章节','合计','表头')``：国企模板 1422 条只有 213 条取得到它说的那张表那一列，上市模板 2356 条只有 238 条。
其余插入后保存即判悬空（行名列「项目」、没有合计行的政策表、同名列重复），或静默取到主表同名列的数（子表：
NOTE 没有「第几张表」参数，「合计」先在主表里找）。判据与求值 / 保存校验同一套匹配（``note_locate``）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import tests.conftest  # noqa: F401  注册全部模型 + SQLite JSONB 兼容
from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services import address_registry as ar

P = uuid.UUID("7d3c2b1a-0f9e-4d8c-b7a6-5f4e3d2c1b0a")


async def _entries(template_type: str):
    return await ar.build_note_entries(None, str(P), 2025, template_type)


@pytest.mark.asyncio
@pytest.mark.parametrize("template_type", ["soe", "listed"])
async def test_every_registered_note_ref_resolves_to_its_own_table(template_type):
    """每条都按求值同一套匹配取得到「它标的那张表」的那一列（标签第三段是表名）。"""
    import json
    from pathlib import Path

    from app.services.formula_ref_check import _template_table_data
    from app.services.formula_ref_preload import note_locate

    raw = json.loads((Path(ar.__file__).parents[2] / "data" / f"note_template_{template_type}.json")
                     .read_text(encoding="utf-8-sig"))
    sections = {str(s.get("section_number") or ""): s for s in raw["sections"] if isinstance(s, dict)}
    entries = await _entries(template_type)
    assert len(entries) > 100, len(entries)  # 防空转
    for e in entries:
        td = _template_table_data(sections[e.note_section])
        row, idx, headers, reason = note_locate(td, e.note_section, "合计", e.cell, require_values=False)
        assert not reason, f"{e.formula_ref}：{reason}"
        table_name = e.label.split(" > ")[2]
        owner = next(t for t in td["_tables"] if any(r is row for r in t["rows"]))
        assert (owner.get("name") or "") == table_name or table_name.startswith("表"), (e.formula_ref, e.label)
        assert headers[idx + 1] == e.cell


@pytest.mark.asyncio
async def test_unusable_refs_are_not_offered():
    refs = {e.formula_ref: e.label for e in await _entries("soe")}
    assert "NOTE('八、1','合计','期末余额')" in refs and refs["NOTE('八、1','合计','期末余额')"].split(" > ")[2] == "货币资金"
    assert "NOTE('八、1','合计','项目')" not in refs, "行名列不是数据列"
    assert "NOTE('四、固定资产','合计','使用年限')" not in refs, "政策表没有合计行"
    assert "NOTE('八、4','合计','账面余额')" not in refs, "列名在表里出现多次（期末 / 期初各一组）"
    assert not any("受限制的货币资金明细" in label for label in refs.values()), "子表的「合计」取到的是主表"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: MetaData().create_all(c, tables=[Project.__table__, DisclosureNote.__table__]))
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as session:
        session.add(Project(id=P, name="地址库附注_2025", client_name="地址库附注", template_type="soe",
                            report_scope="standalone", audit_year=2025))
        await session.flush()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_every_registered_note_ref_passes_save_validation(db):
    """选择器插入的引用保存时不判悬空：本年度附注未生成 ⇒ 校验按附注模板判（与 R5.2 同一校验器）。"""
    from app.services.formula_ref_check import FormulaRefChecker

    checker = FormulaRefChecker(db, P, 2025, "soe")
    rejected = []
    for e in await _entries("soe"):
        verdict = await checker.check(e.formula_ref)
        if verdict is None or not verdict.exists:
            rejected.append(f"{e.formula_ref}：{getattr(verdict, 'reason', '不是单个引用')}")
    assert not rejected, "\n".join(rejected[:10])
