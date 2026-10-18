"""历史 wp_formula 行的 stable_sheet_key 回填脚本（spec formula-manager-closure · Task 1.3）。

背景（ADR-FMC-01 / §5 步骤 1 改动点①「回填为主、标注为过渡」）
================================================================
右栏「当前页公式」改为按 ``stable_sheet_key`` 结构化精确等值 + fail-closed（删除旧
``includes`` 子串匹配）。因 ``stable_sheet_key`` 列可空（V163 新增，见
``backend/migrations/V163__wp_formula_stable_key.sql``），历史行里仍可能有 NULL：
V163 的 UPDATE 只在迁移那一刻对 ``stable_sheet_key IS NULL`` 的行回填一次；在 V163 之后
以旧路径写入、或在未完整跑过 V163 的环境里导入的历史行，可能仍留空。缺值行在精确匹配下
会被 fail-closed 从右栏排除（公式「消失」）。

本脚本是对 V163 回填的**补偿兜底**：**优先**把历史缺值行的 ``stable_sheet_key`` 补齐，
使它们重新进入右栏精确匹配；回填后仍无法解析出结构身份（``stable_sheet_key`` 为空）的
``needs_review`` 行**才** fail-closed 排除，由右栏「无结构身份已排除 N 行」标注过渡。
即「回填为主、标注为过渡」，非二选一。

单一真源（ADR-FMC-01 / NIT-1 硬约束）
====================================
回填与任何 sheet 名归一**一律复用** ``backend/app/services/formula_management/stable_key.py``
的 ``derive_stable_key`` / ``normalize_sheet_key``，**禁在本脚本另写一套规范化**（不写正则、
不抄 V163 的 SQL ``regexp_replace``）。这样回填结果与 service 写入、前端本地归一同口径，
不会出现「同一 sheet 在不同路径归一后对不上」的隐蔽串/漏。

幂等（铁律：已有 stable_sheet_key 的行不覆盖）
==============================================
``WHERE stable_sheet_key IS NULL`` 天然幂等；重跑不改已有非空值。``--recompute`` 显式重算模式
（对所有行重推并覆盖，仅在确需按新口径重算时手动用）默认关闭。

仅处理历史数据，不改范式（不加列、不改索引、不改 ORM）。``wp_formula`` 表本身无 ``is_deleted``
列、无 ``dataset_id``（非四表），故本脚本按行主键逐条 UPDATE，不涉 ``get_active_filter``。

用法::

    cd backend
    python -m scripts.migrate.backfill_wp_formula_stable_key            # dry-run（默认，只报计数）
    python -m scripts.migrate.backfill_wp_formula_stable_key --apply    # 真正写库（WHERE IS NULL）
    python -m scripts.migrate.backfill_wp_formula_stable_key --recompute --apply  # 重算模式（覆盖全部）

非迁移编号脚本（放 scripts/migrate/，避免与并发 V*.sql 迁移编号冲突）。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.config import settings  # noqa: E402

# 🔴 单一真源：回填归一一律复用 stable_key，禁另写规范化（ADR-FMC-01 / NIT-1）。
from app.services.formula_management.stable_key import derive_stable_key  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


@dataclass
class BackfillRow:
    """一行待回填的计算结果（主键 + 由 stable_key 单一真源推导出的三键 + 标记）。"""

    id: str
    stable_sheet_key: str
    row_key: str | None
    field_key: str
    needs_review: bool
    # 回填后仍无结构身份（stable_sheet_key 为空）→ 右栏精确匹配下被 fail-closed 排除。
    excluded_no_identity: bool


def compute_backfill_row(row_id: str, sheet_name: str | None, target_cell: str | None) -> BackfillRow:
    """由 (sheet_name, target_cell) 用单一真源推导回填值。

    **这是回填与一致性断言共用的入口**（集成测试直接对它断言「与 derive_stable_key 一致」）。
    不在此处写任何规范化逻辑，全部委托 ``derive_stable_key``。
    """
    key = derive_stable_key(sheet_name, target_cell)
    return BackfillRow(
        id=row_id,
        stable_sheet_key=key.stable_sheet_key,
        row_key=key.row_key,
        field_key=key.field_key,
        needs_review=key.needs_review,
        # fail-closed 排除的判据 = 回填后 stable_sheet_key 仍为空（无结构身份）。
        # needs_review=True 但 stable_sheet_key 非空（如命名单元 target_cell）→ 仍回填 sheet 键、
        # 仅标记复核，不从右栏排除；只有 sheet 键也解析不出的才真正排除。
        excluded_no_identity=not key.stable_sheet_key,
    )


async def _fetch_target_rows(session: AsyncSession, *, recompute: bool) -> list[tuple[str, str | None, str | None]]:
    """取待回填行 (id, sheet_name, target_cell)。默认只取 stable_sheet_key IS NULL（幂等）。"""
    where = "" if recompute else "WHERE stable_sheet_key IS NULL"
    q = text(f"SELECT id, sheet_name, target_cell FROM wp_formula {where}")
    result = await session.execute(q)
    # id 统一转 str：PG UUID / SQLite TEXT 两方言下 str(id) 都能回绑 WHERE id = :id。
    return [(str(r[0]), r[1], r[2]) for r in result.fetchall()]


async def run(*, apply: bool = False, recompute: bool = False) -> dict[str, int]:
    """执行回填。apply=False 为 dry-run 只报计数。返回计数字典（供测试/CLI 复用）。"""
    engine = create_async_engine(settings.DATABASE_URL, pool_size=5, max_overflow=0)
    async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with async_session_factory() as session:
            raw_rows = await _fetch_target_rows(session, recompute=recompute)
            return await _apply_rows(session, raw_rows, apply=apply)
    finally:
        await engine.dispose()


async def _apply_rows(
    session: AsyncSession,
    raw_rows: list[tuple[str, str | None, str | None]],
    *,
    apply: bool,
) -> dict[str, int]:
    """对已取出的行计算回填值并（可选）写库。拆出以便集成测试直接喂 ORM-prepared 行。"""
    if not raw_rows:
        logger.info("No rows to backfill (stable_sheet_key IS NULL = 0).")
        return {"targeted": 0, "filled": 0, "needs_review": 0, "excluded_no_identity": 0, "applied": 0}

    computed = [compute_backfill_row(rid, sn, tc) for rid, sn, tc in raw_rows]
    needs_review = sum(1 for c in computed if c.needs_review)
    excluded = sum(1 for c in computed if c.excluded_no_identity)

    logger.info(
        "Backfill target: %d rows (needs_review=%d, excluded_no_identity=%d).",
        len(computed), needs_review, excluded,
    )

    if not apply:
        logger.info("[DRY-RUN] No changes written. Use --apply to execute.")
        return {
            "targeted": len(computed),
            "filled": len(computed),
            "needs_review": needs_review,
            "excluded_no_identity": excluded,
            "applied": 0,
        }

    # 逐行 UPDATE（安全、非批量）。幂等条件：默认模式只回填仍为 NULL 的行。
    update_q = text(
        """
        UPDATE wp_formula
        SET stable_sheet_key = :ssk,
            row_key = :rk,
            field_key = :fk,
            stable_key_needs_review = :nr
        WHERE id = :id
        """
    )
    applied = 0
    for c in computed:
        r = await session.execute(
            update_q,
            {
                "ssk": c.stable_sheet_key,
                "rk": c.row_key,
                "fk": c.field_key,
                "nr": c.needs_review,
                "id": c.id,
            },
        )
        applied += r.rowcount or 0

    await session.commit()
    logger.info(
        "[APPLIED] Updated %d rows (needs_review=%d, excluded_no_identity=%d).",
        applied, needs_review, excluded,
    )
    return {
        "targeted": len(computed),
        "filled": len(computed),
        "needs_review": needs_review,
        "excluded_no_identity": excluded,
        "applied": applied,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="回填历史 wp_formula.stable_sheet_key（复用 stable_key 单一真源，幂等）"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True, help="只读报计数，不写库（默认）")
    group.add_argument("--apply", action="store_true", help="真正执行回填写库")
    parser.add_argument(
        "--recompute",
        action="store_true",
        help="重算模式：对所有行（含已有 stable_sheet_key）重推并覆盖（默认关闭，仅按新口径重算时用）",
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, recompute=args.recompute))


if __name__ == "__main__":
    main()
