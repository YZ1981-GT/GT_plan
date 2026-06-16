"""一次性脚本：回填 tb_balance 中 opening_direction / closing_direction 为空的存量行。

逻辑：
  1. opening_debit > 0 且 opening_credit 为空或 0 → opening_direction = 'debit'
  2. opening_credit > 0 且 opening_debit 为空或 0 → opening_direction = 'credit'
  3. 两者都有值（异常）→ 按净额方向（借-贷>=0 → debit，否则 credit）
  4. 两者都为 0 或空 → 默认 'debit'
  5. closing 同理

只更新 direction 为空的行，不动已有方向的。
同时补 sign_convention_version = 'v2_category_natural_positive'（如果为空）。

用法：
  python scripts/fix/_fix_balance_direction_backfill.py [--dry-run]
"""

import asyncio
import sys
from pathlib import Path

# 加 backend 到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from decimal import Decimal
import sqlalchemy as sa
from app.core.database import async_session


def _determine_direction(debit_val, credit_val) -> str:
    """从分列值确定方向"""
    d = Decimal(str(debit_val)) if debit_val is not None else Decimal(0)
    c = Decimal(str(credit_val)) if credit_val is not None else Decimal(0)
    if d > 0 and c <= 0:
        return "debit"
    if c > 0 and d <= 0:
        return "credit"
    if d > 0 and c > 0:
        return "debit" if (d - c) >= 0 else "credit"
    return "debit"  # 都为 0 → 默认借


async def main():
    dry_run = "--dry-run" in sys.argv

    async with async_session() as db:
        # 查所有 direction 为空的行
        stmt = sa.text("""
            SELECT id, opening_debit, opening_credit, closing_debit, closing_credit,
                   opening_direction, closing_direction, sign_convention_version,
                   account_code
            FROM tb_balance
            WHERE is_deleted = false
              AND (opening_direction IS NULL OR closing_direction IS NULL
                   OR sign_convention_version IS NULL)
        """)
        result = await db.execute(stmt)
        rows = result.fetchall()
        print(f"找到 {len(rows)} 行需要回填方向")

        if not rows:
            print("无需处理，退出")
            return

        updated = 0
        for row in rows:
            rid, od, oc, cd, cc, open_dir, close_dir, scv, code = row
            updates = {}

            if open_dir is None:
                updates["opening_direction"] = _determine_direction(od, oc)
                updates["opening_direction_source"] = "backfill_from_split"

            if close_dir is None:
                updates["closing_direction"] = _determine_direction(cd, cc)
                updates["closing_direction_source"] = "backfill_from_split"

            if scv is None:
                updates["sign_convention_version"] = "v2_category_natural_positive"

            if updates:
                if not dry_run:
                    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
                    await db.execute(
                        sa.text(f"UPDATE tb_balance SET {set_clause} WHERE id = :id"),
                        {**updates, "id": rid},
                    )
                updated += 1

        if not dry_run:
            await db.commit()
            print(f"✅ 已回填 {updated} 行（opening_direction + closing_direction + sign_convention_version）")
        else:
            print(f"[DRY-RUN] 将回填 {updated} 行，未写入数据库")

        # 统计回填后的分布
        check = await db.execute(sa.text("""
            SELECT opening_direction, COUNT(*) FROM tb_balance
            WHERE is_deleted = false GROUP BY opening_direction ORDER BY 1
        """))
        print("\n回填后 opening_direction 分布：")
        for r in check.fetchall():
            print(f"  {r[0] or 'NULL'}: {r[1]}")


if __name__ == "__main__":
    asyncio.run(main())
