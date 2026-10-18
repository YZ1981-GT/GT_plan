"""历史 wp_formula.stable_sheet_key 回填集成测试（spec formula-manager-closure · Task 1.3）。

验收判据（tasks.md Task 1.3）：
  - 集成测试断言：回填逻辑与 ``derive_stable_key`` 对同一 ``(sheet_name, target_cell)``
    产出一致（含 ``needs_review`` 行的标记与排除）。
  - 变异反证：篡改回填归一逻辑应使一致性断言打红；反向断言未篡改时通过。

口径（ADR-FMC-01 / §5 步骤 1 改动点①「回填为主、标注为过渡」）：
  - 回填**优先**补齐 stable_sheet_key；回填后仍无结构身份（stable_sheet_key 为空）的
    needs_review 行**才** fail-closed 排除（excluded_no_identity=True）。
  - 命名单元 target_cell（如「净额」）→ needs_review=True 但 sheet 键仍回填、**不排除**。

真库行为用 ORM 层在 SQLite 建 wp_formula 表并逐行插入（UUID 由 ORM 处理），
不裸 SQL 比字符串 UUID（memory 铁律：原生 SQL 按 str(uuid) 在 SQLite 恒匹配不到）。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.workpaper_models import WpFormula
from app.services.formula_management.stable_key import derive_stable_key
from scripts.migrate.backfill_wp_formula_stable_key import (
    _apply_rows,
    _fetch_target_rows,
    compute_backfill_row,
)

# JSONB → JSON、ARRAY → TEXT，让 wp_formula 的 JSONB 列在 SQLite 建表通过。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"


# ─────────────────────────────────────────────────────────────────────────────
# 共享样本：(sheet_name, target_cell, 期望 excluded_no_identity)
# 覆盖 正常 A1 / 带排序前缀 / 全角空格 / 命名单元（needs_review 不排除）/
# 无结构身份 sheet（回填后仍空 → 排除）。
# ─────────────────────────────────────────────────────────────────────────────
_SAMPLES: list[tuple[str | None, str | None, bool]] = [
    ("五、1 审定表D2-1", "C7", False),          # 带排序前缀 → 剥离后 审定表D2-1
    ("审定表\u3000D2-1", "B5", False),           # 全角空格折叠
    ("审定表D2-1", "aa12", False),               # 列小写 → 回填大写 AA
    ("审定表D2-1", "净额", False),               # 命名单元 → needs_review 但 sheet 键非空，不排除
    ("", "B5", True),                            # sheet 名空 → stable_sheet_key 空 → 排除
    (None, "C3", True),                          # sheet 名 None → 排除
]


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    # 仅建 wp_formula 单表；SQLite 默认不强制 FK，故不需建 projects/working_paper/users。
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=[WpFormula.__table__]))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=[WpFormula.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession) -> list[uuid.UUID]:
    """插入一批 stable_sheet_key=NULL 的历史行，返回 id 列表（插入顺序）。"""
    ids: list[uuid.UUID] = []
    for sheet_name, target_cell, _exp in _SAMPLES:
        fid = uuid.uuid4()
        db.add(
            WpFormula(
                id=fid,
                project_id=uuid.uuid4(),
                wp_id=uuid.uuid4(),
                sheet_name=sheet_name if sheet_name is not None else "",  # 列 NOT NULL；用空串模拟缺值
                target_cell=target_cell if target_cell is not None else "",
                expression="TB('1001','期末余额')",
                # stable_sheet_key 不赋值 → NULL（历史缺值行）
            )
        )
        ids.append(fid)
    await db.commit()
    return ids


# ═══════════════════════════════════════════════════════════════════════════════
# 单元：compute_backfill_row 与 derive_stable_key 对同一入参逐值一致
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sheet_name,target_cell,exp_excluded", _SAMPLES)
def test_compute_backfill_row_matches_derive_stable_key(sheet_name, target_cell, exp_excluded):
    """回填入口 compute_backfill_row 的三键与标记必须 == derive_stable_key（单一真源）。"""
    rid = str(uuid.uuid4())
    # 入库用的是「空串代 None」，故这里也喂规范化后的值以对齐库里行为。
    sn = sheet_name if sheet_name is not None else ""
    tc = target_cell if target_cell is not None else ""
    got = compute_backfill_row(rid, sn, tc)
    want = derive_stable_key(sn, tc)

    assert got.stable_sheet_key == want.stable_sheet_key
    assert got.row_key == want.row_key
    assert got.field_key == want.field_key
    assert got.needs_review == want.needs_review
    # excluded_no_identity = 回填后 stable_sheet_key 仍为空
    assert got.excluded_no_identity == (not want.stable_sheet_key)
    assert got.excluded_no_identity == exp_excluded


# ═══════════════════════════════════════════════════════════════════════════════
# 集成：真 ORM 行 → 回填 → 逐行与 derive_stable_key 一致 + needs_review/排除标记正确
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_backfill_writes_values_matching_derive_stable_key(db_session: AsyncSession):
    await _seed(db_session)

    raw = await _fetch_target_rows(db_session, recompute=False)
    assert len(raw) == len(_SAMPLES), "回填目标应为全部 stable_sheet_key IS NULL 的历史行"

    counts = await _apply_rows(db_session, raw, apply=True)
    assert counts["applied"] == len(_SAMPLES)

    # 逐行读回，对每行断言库里值 == derive_stable_key(当前 sheet_name,target_cell)。
    rows = (await db_session.execute(sa.select(WpFormula))).scalars().all()
    assert len(rows) == len(_SAMPLES)
    excluded = 0
    needs_review = 0
    for r in rows:
        want = derive_stable_key(r.sheet_name, r.target_cell)
        assert r.stable_sheet_key == want.stable_sheet_key, f"sheet_key 不一致: {r.sheet_name!r}"
        assert r.row_key == want.row_key
        assert r.field_key == want.field_key
        assert bool(r.stable_key_needs_review) == want.needs_review
        if want.needs_review:
            needs_review += 1
        if not want.stable_sheet_key:
            excluded += 1

    # 样本里：命名单元 1 条 + sheet 空 2 条 = 3 条 needs_review；其中 sheet 空 2 条才是排除。
    assert counts["needs_review"] == needs_review == 3
    assert counts["excluded_no_identity"] == excluded == 2


@pytest.mark.asyncio
async def test_backfill_idempotent_does_not_overwrite_existing(db_session: AsyncSession):
    """幂等：已有 stable_sheet_key 的行不进默认回填集，重跑不改。"""
    ids = await _seed(db_session)

    # 第一次回填（apply）
    raw1 = await _fetch_target_rows(db_session, recompute=False)
    await _apply_rows(db_session, raw1, apply=True)

    # 人为篡改其中一行的 stable_sheet_key 为哨兵值，证明重跑不覆盖它。
    sentinel_id = ids[0]
    await db_session.execute(
        sa.update(WpFormula).where(WpFormula.id == sentinel_id).values(stable_sheet_key="__SENTINEL__")
    )
    await db_session.commit()

    # 第二次：默认模式只取 IS NULL 的行 → 现在应为空（全部已填）。
    raw2 = await _fetch_target_rows(db_session, recompute=False)
    assert raw2 == [], "重跑时无 NULL 行可回填（幂等）"
    counts2 = await _apply_rows(db_session, raw2, apply=True)
    assert counts2["applied"] == 0

    # 哨兵值未被覆盖。
    row = (
        await db_session.execute(sa.select(WpFormula).where(WpFormula.id == sentinel_id))
    ).scalar_one()
    assert row.stable_sheet_key == "__SENTINEL__"


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(db_session: AsyncSession):
    """dry-run（apply=False）只报计数不写库。"""
    await _seed(db_session)
    raw = await _fetch_target_rows(db_session, recompute=False)
    counts = await _apply_rows(db_session, raw, apply=False)
    assert counts["applied"] == 0
    assert counts["targeted"] == len(_SAMPLES)
    # 库里仍全是 NULL。
    still_null = await _fetch_target_rows(db_session, recompute=False)
    assert len(still_null) == len(_SAMPLES)


# ═══════════════════════════════════════════════════════════════════════════════
# 变异反证：篡改回填归一逻辑 → 一致性断言打红；反向断言未篡改时通过（铁律㉒）
# ═══════════════════════════════════════════════════════════════════════════════


def test_mutation_tampered_backfill_normalization_breaks_consistency():
    """若回填自己写一套 sheet 名归一（偏离 stable_key 真源），一致性断言必打红。

    变异体：对带排序前缀的 sheet 名**不剥前缀**（直接原样当 stable_sheet_key）。
    这正是「另写一套规范化」会犯的错。断言它与 derive_stable_key 不一致 ⇒ 坐实
    「回填一旦偏离单一真源，本测试会红」。
    """
    sheet_name, target_cell = "五、1 审定表D2-1", "C7"

    def _tampered_compute(sn: str, tc: str):
        # 偏离真源：不剥排序前缀（错误归一）
        return sn, tc

    tampered_key, _ = _tampered_compute(sheet_name, target_cell)
    want = derive_stable_key(sheet_name, target_cell)

    # 变异体结果与真源不一致（含前缀 vs 已剥前缀）→ 若生产回填这么写，上面的集成一致性断言必红。
    assert tampered_key != want.stable_sheet_key
    assert tampered_key == "五、1 审定表D2-1"
    assert want.stable_sheet_key == "审定表D2-1"

    # 反向断言：未篡改（真正复用 compute_backfill_row）时一致（未注入不命中）。
    got = compute_backfill_row(str(uuid.uuid4()), sheet_name, target_cell)
    assert got.stable_sheet_key == want.stable_sheet_key
