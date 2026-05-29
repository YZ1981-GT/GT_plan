# -*- coding: utf-8 -*-
"""四表查询性能优化 — 创建针对性索引"""
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

INDEXES = [
    # 序时账：穿透查询覆盖索引（包含排序列避免外部磁盘排序）
    ("idx_tb_ledger_penetrate",
     "CREATE INDEX IF NOT EXISTS idx_tb_ledger_penetrate ON tb_ledger (project_id, year, account_code, voucher_date, voucher_no) WHERE is_deleted = false"),
    # 辅助明细账：按科目+维度类型穿透
    ("idx_tb_aux_ledger_penetrate",
     "CREATE INDEX IF NOT EXISTS idx_tb_aux_ledger_penetrate ON tb_aux_ledger (project_id, year, account_code, aux_type, voucher_date) WHERE is_deleted = false"),
    # 辅助余额表：按科目查询
    ("idx_tb_aux_balance_account",
     "CREATE INDEX IF NOT EXISTS idx_tb_aux_balance_account ON tb_aux_balance (project_id, year, account_code) WHERE is_deleted = false"),
    # 序时账：按凭证号查询
    ("idx_tb_ledger_voucher",
     "CREATE INDEX IF NOT EXISTS idx_tb_ledger_voucher ON tb_ledger (project_id, year, voucher_no, voucher_date) WHERE is_deleted = false"),
    # 序时账：按月份查询
    ("idx_tb_ledger_period",
     "CREATE INDEX IF NOT EXISTS idx_tb_ledger_period ON tb_ledger (project_id, year, accounting_period) WHERE is_deleted = false"),
]

async def main():
    from app.core.database import engine
    import sqlalchemy as sa

    async with engine.begin() as conn:
        for name, sql in INDEXES:
            print(f"创建索引: {name} ...", end=" ", flush=True)
            try:
                await conn.execute(sa.text(sql))
                print("OK", flush=True)
            except Exception as e:
                print(f"跳过: {e}", flush=True)

    # 验证 + ANALYZE
    async with engine.begin() as conn:
        print("\nANALYZE...", flush=True)
        for tbl in ["tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"]:
            await conn.execute(sa.text(f"ANALYZE {tbl}"))

        print("\n索引列表:", flush=True)
        r = await conn.execute(sa.text("""
            SELECT tablename, indexname, pg_size_pretty(pg_relation_size(c.oid)) as size
            FROM pg_indexes i JOIN pg_class c ON c.relname = i.indexname
            WHERE tablename IN ('tb_balance','tb_aux_balance','tb_ledger','tb_aux_ledger')
            ORDER BY tablename, indexname
        """))
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]} ({row[2]})", flush=True)

asyncio.run(main())
