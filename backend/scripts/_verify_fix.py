"""验证修复结果"""
import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/audit_platform')
cur = conn.cursor()

# 检查 import_batches 列
for col in ['is_deleted', 'deleted_at', 'updated_at']:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='import_batches' AND column_name=%s", (col,)
    )
    has = cur.fetchone()
    status = 'OK' if has else 'STILL MISSING'
    print(f"import_batches.{col}: {status}")

# 检查 trial_balance.currency_code
cur.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name='trial_balance' AND column_name='currency_code'"
)
print(f"trial_balance.currency_code: {'OK' if cur.fetchone() else 'MISSING'}")

# 检查 tb_balance.level
cur.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name='tb_balance' AND column_name='level'"
)
print(f"tb_balance.level: {'OK' if cur.fetchone() else 'MISSING'}")

conn.close()
print("Done")
