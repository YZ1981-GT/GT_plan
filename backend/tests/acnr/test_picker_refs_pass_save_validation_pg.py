"""T10（pg_only、只读回滚）：选址器给出的引用都能通过公式保存校验（design §6.5）。

以安徽骨科医院_2025 为上下文，对目录全部非停用 cell 的 formula_ref 调 `validate_refs_via_acnr`，拒绝数 0；
停用 cell 的 formula_ref 也被接受（不出 issue）并记指标 `deprecated_ref_saved`（design §3.3）；
多义写法被拒绝且 message 是中文原因。
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.services.acnr import exact_identity
from app.services.acnr.catalog import get_catalog
from app.services.acnr.formula_validation import validate_refs_via_acnr
from app.services.acnr.metrics import get_acnr_metrics

pytestmark = [pytest.mark.pg_only]

_PROJECT_NAME = "安徽骨科医院_2025"


async def _with_session(fn):
    eng = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            await s.execute(text("SET TRANSACTION READ ONLY"))
            try:
                pid = (await s.execute(text("SELECT id::text FROM projects WHERE name = :n"),
                                       {"n": _PROJECT_NAME})).scalar_one()
                return await fn(s, pid)
            finally:
                await s.rollback()
    finally:
        await eng.dispose()


def _cells(deprecated: bool) -> list[dict]:
    cat = get_catalog()
    return [c for c in cat.cells_by_addr_id.values()
            if bool(c.get("deprecated")) is deprecated and c.get("parent_addr_id") in cat.sheets_by_addr_id]


@pytest.mark.asyncio
async def test_all_live_cell_formula_refs_pass_save_validation(caplog):
    cells = _cells(False)
    # 本批次现算：有效 98 = 语义待核对 33 + 模板核对坐标 65；停用 441 = 孤儿 25 + 超范围 14 + 与模板不符 402（spec wp-deeplink-locate-coverage-closure）
    assert len(cells) == 98

    async def run(s, pid):
        rejected = []
        for c in cells:
            issues = await validate_refs_via_acnr(s, pid, 2025, f"={c['formula_ref']}")
            if issues:
                rejected.append((c["addr_id"], c["formula_ref"], issues[0]["message"]))
        return rejected

    with caplog.at_level("WARNING", logger="app.services.acnr.formula_validation"):
        rejected = await _with_session(run)
    # 防假绿：结果必须来自 ACNR full_resolve，不能是 fail-open 回退 legacy 校验后的放行
    fallback = [r.getMessage() for r in caplog.records if "回退 legacy" in r.getMessage()]
    assert fallback == [], fallback[:3]
    assert rejected == [], f"拒绝 {len(rejected)} 条，前 5：{rejected[:5]}"


@pytest.mark.asyncio
async def test_deprecated_refs_accepted_and_counted():
    cells = _cells(True)
    assert len(cells) == 441
    m = get_acnr_metrics()
    before = m.get_aggregated_metrics()["alerts"]["by_type"].get("deprecated_ref_saved", 0)

    async def run(s, pid):
        return [c["addr_id"] for c in cells
                if await validate_refs_via_acnr(s, pid, 2025, f"={c['formula_ref']}")]

    assert await _with_session(run) == []
    after = m.get_aggregated_metrics()["alerts"]["by_type"].get("deprecated_ref_saved", 0)
    assert after - before == len(cells)


@pytest.mark.asyncio
async def test_ambiguous_writing_rejected_with_chinese_reason():
    cat = get_catalog()
    sample = None
    for s in sorted(cat.sheets_by_addr_id.values(), key=lambda x: x["addr_id"]):
        if exact_identity.sheet_of(s["parent_wp_code"], s.get("sheet_name") or "").state == "ambiguous":
            sample = (s["parent_wp_code"], s["sheet_name"])
            break
    assert sample, "目录里没有多义名称"

    async def run(s, pid):
        return await validate_refs_via_acnr(s, pid, 2025, f"=WP('{sample[0]}','{sample[1]}','A1')")

    issues = await _with_session(run)
    assert len(issues) == 1 and issues[0]["reason"] == "ambiguous"
    assert "对应多张表" in issues[0]["message"]
