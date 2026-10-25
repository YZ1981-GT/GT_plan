"""S17 sheet 分类回填（.xls 模板未被 .xlsx 扫描收录，故 S17 分类为 0 行）。

候选来自 generate_s17_classification_dry_run.py 的 8 行模板派生分类，
class_code 遵循 S9/S10 既有约定。--apply 前为只读 dry-run。
幂等：ON CONFLICT (wp_code, sheet_name) DO NOTHING。

spec: s-cycle-linkage-trimming-and-component-wiring R6.6（用户 2026-10-26 明确批准写入）
用法：
  python backend/scripts/ops/backfill_s17_classification.py            # dry-run
  python backend/scripts/ops/backfill_s17_classification.py --apply    # 写库
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402

# S9/S10 既有分类的模板版本（保持 S 循环一致）
_TEMPLATE_VERSION_ID = "d3710183-30cd-44fc-833f-ddc20c5d5606"

# (sheet_name, class_code, class, is_real, is_static, excl_archive, excl_progress)
_ROWS = [
    ("表头（请先填写）", "I-占位", "I", False, False, True, True),
    ("审计程序S17", "A-S 议题程序", "A", True, False, False, False),
    ("审定表S17-1", "F-审定表", "F", True, False, False, False),
    ("审核表（合并）S17-2", "D-检查表", "D", True, False, False, False),
    ("审核表（个别报表）S17-3", "D-检查表", "D", True, False, False, False),
    ("提示（供参考，不打印）", "H-辅助说明", "H", False, True, False, True),
    ("与营业外收支等核对表S17-11", "D-检查表", "D", True, False, False, False),
    ("非经常性损益项目的所得税影响S17-21", "D-检查表", "D", True, False, False, False),
]


async def run(apply: bool) -> int:
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    eng = create_async_engine(url, echo=False)
    factory = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    inserted = 0
    async with factory() as s:
        # 现状
        before = (await s.execute(sa.text(
            "SELECT COUNT(1) FROM workpaper_sheet_classification WHERE wp_code='S17'"
        ))).scalar()
        print(f"[S17] before rows = {before}")
        for sheet, cc, cls, is_real, is_static, ex_arc, ex_prog in _ROWS:
            print(f"  candidate: {sheet!r:40} -> {cc} (class={cls})")
        if not apply:
            print("[DRY-RUN] 未写库。加 --apply 执行写入。")
            await eng.dispose()
            return 0
        for sheet, cc, cls, is_real, is_static, ex_arc, ex_prog in _ROWS:
            res = await s.execute(sa.text(
                "INSERT INTO workpaper_sheet_classification "
                "(id, wp_code, sheet_name, class_code, class, is_real_workpaper, "
                " is_static_doc, exclude_from_archive, exclude_from_progress, scope, "
                " template_version_id, created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'S17', :sheet, :cc, :cls, :is_real, "
                " :is_static, :ex_arc, :ex_prog, 'standalone', :tv, now(), now()) "
                "ON CONFLICT (wp_code, sheet_name) DO NOTHING"
            ), {
                "sheet": sheet, "cc": cc, "cls": cls, "is_real": is_real,
                "is_static": is_static, "ex_arc": ex_arc, "ex_prog": ex_prog,
                "tv": _TEMPLATE_VERSION_ID,
            })
            inserted += res.rowcount or 0
        await s.commit()
        after = (await s.execute(sa.text(
            "SELECT COUNT(1) FROM workpaper_sheet_classification WHERE wp_code='S17'"
        ))).scalar()
        print(f"[APPLIED] inserted={inserted} after rows={after}")
    await eng.dispose()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="执行写库（默认 dry-run）")
    args = ap.parse_args()
    return asyncio.run(run(args.apply))


if __name__ == "__main__":
    raise SystemExit(main())