"""修复数据库缺失列"""
import psycopg2

conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/audit_platform')
conn.autocommit = True
cur = conn.cursor()

# 1. import_batches 补齐缺失列
fixes = [
    "ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false NOT NULL",
    "ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP",
    "ALTER TABLE import_batches ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT now()",
]
for sql in fixes:
    cur.execute(sql)
    print(f"OK: {sql[:60]}...")

# 2. 检查并修复其他可能缺失的列（根据 memory.md 记录）
extra_fixes = [
    # tb_aux_balance/tb_aux_ledger 可能缺 account_name
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS account_name VARCHAR(200)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS account_name VARCHAR(200)",
    # tb_aux_balance/tb_aux_ledger 可能缺 aux_dimensions_raw
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS aux_dimensions_raw TEXT",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS aux_dimensions_raw TEXT",
    # 四表扩展字段
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS opening_debit NUMERIC(20,2)",
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS opening_credit NUMERIC(20,2)",
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS closing_debit NUMERIC(20,2)",
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS closing_credit NUMERIC(20,2)",
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS opening_qty NUMERIC(20,4)",
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS opening_fc NUMERIC(20,2)",
    "ALTER TABLE tb_balance ADD COLUMN IF NOT EXISTS level INTEGER",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20)",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS voucher_type VARCHAR(50)",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS entry_seq INTEGER",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS debit_qty NUMERIC(20,4)",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS credit_qty NUMERIC(20,4)",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS debit_fc NUMERIC(20,2)",
    "ALTER TABLE tb_ledger ADD COLUMN IF NOT EXISTS credit_fc NUMERIC(20,2)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS aux_type_name VARCHAR(100)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS opening_qty NUMERIC(20,4)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS opening_fc NUMERIC(20,2)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS opening_debit NUMERIC(20,2)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS opening_credit NUMERIC(20,2)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS closing_debit NUMERIC(20,2)",
    "ALTER TABLE tb_aux_balance ADD COLUMN IF NOT EXISTS closing_credit NUMERIC(20,2)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS aux_type_name VARCHAR(100)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS accounting_period VARCHAR(20)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS voucher_type VARCHAR(50)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS debit_qty NUMERIC(20,4)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS credit_qty NUMERIC(20,4)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS debit_fc NUMERIC(20,2)",
    "ALTER TABLE tb_aux_ledger ADD COLUMN IF NOT EXISTS credit_fc NUMERIC(20,2)",
    # trial_balance 可能缺 currency_code
    "ALTER TABLE trial_balance ADD COLUMN IF NOT EXISTS currency_code VARCHAR(3) DEFAULT 'CNY'",
    # attachments 可能缺列
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS attachment_type VARCHAR(50) DEFAULT 'general'",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS reference_id UUID",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS reference_type VARCHAR(50)",
    "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS storage_type VARCHAR(20) DEFAULT 'local'",
]
for sql in extra_fixes:
    try:
        cur.execute(sql)
        print(f"OK: {sql[:70]}...")
    except Exception as e:
        print(f"SKIP: {sql[:50]}... ({e})")

print("\nAll fixes applied!")
conn.close()
