"""检查数据库表结构"""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/audit_platform')
cur = conn.cursor()

# 查看 projects 表列
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='projects' ORDER BY ordinal_position")
print("=== projects columns ===")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

# 查看已有项目
cur.execute("SELECT id, name, status FROM projects LIMIT 5")
print("\n=== projects data ===")
rows = cur.fetchall()
for r in rows:
    print(f"  {r}")
if not rows:
    print("  (empty)")

# 查看 tb_balance 分区情况
cur.execute("SELECT relname FROM pg_class WHERE relname LIKE 'tb_balance%' AND relkind IN ('r','p') ORDER BY relname")
print("\n=== tb_balance tables ===")
for r in cur.fetchall():
    print(f"  {r[0]}")

# 查看 import_batches
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='import_batches' ORDER BY ordinal_position")
print("\n=== import_batches columns ===")
for r in cur.fetchall():
    print(f"  {r[0]}")

conn.close()
