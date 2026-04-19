# -*- coding: utf-8 -*-
"""测试四表数据库查询性能"""
import sys, time, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    from app.core.database import engine
    import sqlalchemy as sa

    async with engine.begin() as conn:
        # 1. 各表数据量
        print("=== 1. 数据量 ===", flush=True)
        for tbl in ["tb_balance", "tb_aux_balance", "tb_ledger", "tb_aux_ledger"]:
            r = await conn.execute(sa.text(f"SELECT COUNT(*) FROM {tbl} WHERE is_deleted = false"))
            print(f"  {tbl}: {r.scalar():,} 行", flush=True)

        # 2. 表大小和索引
        print("\n=== 2. 表大小 ===", flush=True)
        r = await conn.execute(sa.text("""
            SELECT relname, pg_size_pretty(pg_total_relation_size(c.oid)) as total,
                   pg_size_pretty(pg_relation_size(c.oid)) as data,
                   pg_size_pretty(pg_indexes_size(c.oid)) as indexes
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE relname IN ('tb_balance','tb_aux_balance','tb_ledger','tb_aux_ledger')
            AND n.nspname = 'public'
        """))
        for row in r.fetchall():
            print(f"  {row[0]}: 总{row[1]}, 数据{row[2]}, 索引{row[3]}", flush=True)

        # 3. 现有索引
        print("\n=== 3. 索引 ===", flush=True)
        r = await conn.execute(sa.text("""
            SELECT tablename, indexname FROM pg_indexes
            WHERE tablename IN ('tb_balance','tb_aux_balance','tb_ledger','tb_aux_ledger')
            ORDER BY tablename, indexname
        """))
        for row in r.fetchall():
            print(f"  {row[0]}: {row[1]}", flush=True)

        pid = "6687b8ce-7a83-4816-bd4a-c2d173d4b683"

        # 4. 典型查询性能
        print("\n=== 4. 查询性能 ===", flush=True)

        # 4a. 余额表全量（科目余额表页面）
        t0 = time.time()
        r = await conn.execute(sa.text(f"""
            SELECT account_code, account_name, opening_balance, debit_amount, credit_amount, closing_balance, level
            FROM tb_balance WHERE project_id = '{pid}' AND year = 2025 AND is_deleted = false
            ORDER BY account_code
        """))
        rows = r.fetchall()
        print(f"  余额表全量: {len(rows)} 行, {(time.time()-t0)*1000:.0f}ms", flush=True)

        # 4b. 序时账按科目查（穿透查询）
        t0 = time.time()
        r = await conn.execute(sa.text(f"""
            SELECT voucher_date, voucher_no, account_code, account_name, debit_amount, credit_amount, summary
            FROM tb_ledger WHERE project_id = '{pid}' AND year = 2025 AND account_code = '1002' AND is_deleted = false
            ORDER BY voucher_date, voucher_no
        """))
        rows = r.fetchall()
        print(f"  序时账(1002): {len(rows)} 行, {(time.time()-t0)*1000:.0f}ms", flush=True)

        # 4c. 序时账按科目前缀查（合计行穿透）
        t0 = time.time()
        r = await conn.execute(sa.text(f"""
            SELECT voucher_date, voucher_no, account_code, debit_amount, credit_amount, summary
            FROM tb_ledger WHERE project_id = '{pid}' AND year = 2025 AND account_code LIKE '1122%' AND is_deleted = false
            ORDER BY voucher_date, voucher_no
        """))
        rows = r.fetchall()
        print(f"  序时账(1122%): {len(rows)} 行, {(time.time()-t0)*1000:.0f}ms", flush=True)

        # 4d. 辅助余额表按科目查
        t0 = time.time()
        r = await conn.execute(sa.text(f"""
            SELECT account_code, aux_type, aux_code, aux_name, opening_balance, debit_amount, credit_amount, closing_balance
            FROM tb_aux_balance WHERE project_id = '{pid}' AND year = 2025 AND account_code = '1002' AND is_deleted = false
        """))
        rows = r.fetchall()
        print(f"  辅助余额(1002): {len(rows)} 行, {(time.time()-t0)*1000:.0f}ms", flush=True)

        # 4e. 辅助明细账按科目+维度查
        t0 = time.time()
        r = await conn.execute(sa.text(f"""
            SELECT voucher_date, voucher_no, aux_type, aux_code, aux_name, debit_amount, credit_amount, summary
            FROM tb_aux_ledger WHERE project_id = '{pid}' AND year = 2025 AND account_code = '1002'
            AND aux_type = '成本中心' AND is_deleted = false
            ORDER BY voucher_date
        """))
        rows = r.fetchall()
        print(f"  辅助明细(1002/成本中心): {len(rows)} 行, {(time.time()-t0)*1000:.0f}ms", flush=True)

        # 4f. 辅助明细账全量COUNT
        t0 = time.time()
        r = await conn.execute(sa.text(f"""
            SELECT COUNT(*) FROM tb_aux_ledger WHERE project_id = '{pid}' AND year = 2025 AND is_deleted = false
        """))
        print(f"  辅助明细COUNT: {r.scalar():,}, {(time.time()-t0)*1000:.0f}ms", flush=True)

        # 5. EXPLAIN ANALYZE 关键查询
        print("\n=== 5. EXPLAIN ANALYZE ===", flush=True)
        r = await conn.execute(sa.text(f"""
            EXPLAIN ANALYZE
            SELECT voucher_date, voucher_no, account_code, debit_amount, credit_amount, summary
            FROM tb_ledger WHERE project_id = '{pid}' AND year = 2025 AND account_code = '1002' AND is_deleted = false
            ORDER BY voucher_date, voucher_no
        """))
        for row in r.fetchall():
            print(f"  {row[0]}", flush=True)

asyncio.run(main())
