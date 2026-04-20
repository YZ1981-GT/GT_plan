"""检查四表 year 列和导入相关问题"""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/audit_platform')
cur = conn.cursor()

# 检查四表是否有 year 列
for t in ['tb_balance', 'tb_ledger', 'tb_aux_balance', 'tb_aux_ledger']:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name=%s AND column_name='year'", (t,)
    )
    has = cur.fetchone()
    print(f"{t}.year: {'YES' if has else 'MISSING'}")

# 检查 import_batches 缺失列
for col in ['is_deleted', 'deleted_at', 'updated_at']:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='import_batches' AND column_name=%s", (col,)
    )
    has = cur.fetchone()
    print(f"import_batches.{col}: {'YES' if has else 'MISSING'}")

# 检查项目的 wizard_state 中的年度
cur.execute("SELECT id, name, wizard_state->'basic_info'->>'audit_year' FROM projects LIMIT 5")
for r in cur.fetchall():
    print(f"\nProject: {r[1]}, audit_year: {r[2]}")

conn.close()
