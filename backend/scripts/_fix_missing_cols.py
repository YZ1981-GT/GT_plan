"""补齐四表缺失的列"""
import psycopg2

conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/audit_platform")
cur = conn.cursor()

# 检查并补齐所有可能缺失的列
fixes = [
    ("tb_aux_ledger", "aux_dimensions_raw", "TEXT"),
    ("tb_aux_balance", "aux_dimensions_raw", "TEXT"),
    ("tb_aux_ledger", "aux_type_name", "VARCHAR(200)"),
    ("tb_aux_balance", "aux_type_name", "VARCHAR(200)"),
    ("tb_aux_ledger", "account_name", "VARCHAR(200)"),
    ("tb_aux_balance", "account_name", "VARCHAR(200)"),
    ("tb_ledger", "accounting_period", "INTEGER"),
    ("tb_ledger", "voucher_type", "VARCHAR(50)"),
    ("tb_ledger", "entry_seq", "INTEGER"),
    ("tb_ledger", "debit_qty", "NUMERIC(20,4)"),
    ("tb_ledger", "credit_qty", "NUMERIC(20,4)"),
    ("tb_ledger", "debit_fc", "NUMERIC(20,2)"),
    ("tb_ledger", "credit_fc", "NUMERIC(20,2)"),
    ("tb_balance", "opening_qty", "NUMERIC(20,4)"),
    ("tb_balance", "opening_fc", "NUMERIC(20,2)"),
    ("tb_balance", "opening_debit", "NUMERIC(20,2)"),
    ("tb_balance", "opening_credit", "NUMERIC(20,2)"),
    ("tb_balance", "closing_debit", "NUMERIC(20,2)"),
    ("tb_balance", "closing_credit", "NUMERIC(20,2)"),
    ("tb_balance", "level", "INTEGER"),
    ("tb_aux_balance", "opening_debit", "NUMERIC(20,2)"),
    ("tb_aux_balance", "opening_credit", "NUMERIC(20,2)"),
    ("tb_aux_balance", "closing_debit", "NUMERIC(20,2)"),
    ("tb_aux_balance", "closing_credit", "NUMERIC(20,2)"),
    ("tb_aux_balance", "opening_qty", "NUMERIC(20,4)"),
    ("tb_aux_balance", "opening_fc", "NUMERIC(20,2)"),
    ("tb_aux_ledger", "accounting_period", "INTEGER"),
    ("tb_aux_ledger", "voucher_type", "VARCHAR(50)"),
    ("tb_aux_ledger", "debit_qty", "NUMERIC(20,4)"),
    ("tb_aux_ledger", "credit_qty", "NUMERIC(20,4)"),
    ("tb_aux_ledger", "debit_fc", "NUMERIC(20,2)"),
    ("tb_aux_ledger", "credit_fc", "NUMERIC(20,2)"),
    ("trial_balance", "currency_code", "VARCHAR(3) DEFAULT 'CNY'"),
    ("attachments", "created_by", "UUID"),
]

added = 0
for table, col, col_type in fixes:
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s)",
        (table, col)
    )
    exists = cur.fetchone()[0]
    if not exists:
        sql = f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
        cur.execute(sql)
        print(f"  + {table}.{col} ({col_type})")
        added += 1

conn.commit()
print(f"\n补齐 {added} 列完成")
cur.close()
conn.close()
