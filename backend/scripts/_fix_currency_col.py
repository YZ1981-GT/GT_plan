"""补齐 trial_balance.currency_code 列"""
import psycopg2

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/audit_platform")
cur = conn.cursor()
cur.execute("ALTER TABLE trial_balance ADD COLUMN IF NOT EXISTS currency_code VARCHAR(3) DEFAULT 'CNY'")
conn.commit()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='trial_balance' AND column_name='currency_code'")
print("Result:", cur.fetchall())
cur.close()
conn.close()
print("Done!")
