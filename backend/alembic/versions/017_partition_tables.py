"""012 partition tables — tb_ledger 和 tb_aux_ledger 按年度分区

无生产数据，直接 DROP 旧表 + 重建为分区表。
分区键：year（包含在复合主键中）
预建分区：2023-2027 共5个年度

Revision ID: 012
Revises: 011
Create Date: 2026-04-13 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ================================================================
    # 1. DROP 旧表（无生产数据，安全删除）
    # ================================================================

    # 先删除 011 迁移创建的索引（如果存在）
    try:
        op.drop_index("idx_tb_ledger_project_year_voucher", table_name="tb_ledger")
    except Exception:
        pass
    try:
        op.drop_index("idx_tb_aux_ledger_project_year_aux_type_code", table_name="tb_aux_ledger")
    except Exception:
        pass

    # 删除旧索引
    try:
        op.drop_index("idx_tb_ledger_project_year_date_no", table_name="tb_ledger")
    except Exception:
        pass
    try:
        op.drop_index("idx_tb_ledger_project_year_account", table_name="tb_ledger")
    except Exception:
        pass
    try:
        op.drop_index("idx_tb_aux_ledger_project_year_account_aux", table_name="tb_aux_ledger")
    except Exception:
        pass

    op.drop_table("tb_aux_ledger")
    op.drop_table("tb_ledger")

    # ================================================================
    # 2. 重建 tb_ledger 为分区表
    # ================================================================

    op.execute("""
        CREATE TABLE tb_ledger (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            year INTEGER NOT NULL,
            company_code VARCHAR NOT NULL,
            voucher_date DATE NOT NULL,
            voucher_no VARCHAR NOT NULL,
            account_code VARCHAR NOT NULL,
            account_name VARCHAR,
            debit_amount NUMERIC(20,2),
            credit_amount NUMERIC(20,2),
            counterpart_account VARCHAR,
            summary TEXT,
            preparer VARCHAR,
            currency_code VARCHAR(3) NOT NULL DEFAULT 'CNY',
            import_batch_id UUID REFERENCES import_batches(id),
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (id, year)
        ) PARTITION BY RANGE (year);
    """)

    # 创建 2023-2027 年度分区
    for y in range(2023, 2028):
        op.execute(f"""
            CREATE TABLE tb_ledger_{y} PARTITION OF tb_ledger
                FOR VALUES FROM ({y}) TO ({y + 1});
        """)

    # 在每个分区上创建索引（自动继承到新分区）
    op.execute("""
        CREATE INDEX idx_tb_ledger_project_year_account
            ON tb_ledger (project_id, year, account_code);
    """)
    op.execute("""
        CREATE INDEX idx_tb_ledger_project_year_date_no
            ON tb_ledger (project_id, year, voucher_date, voucher_no);
    """)
    op.execute("""
        CREATE INDEX idx_tb_ledger_project_year_voucher
            ON tb_ledger (project_id, year, voucher_no);
    """)

    # ================================================================
    # 3. 重建 tb_aux_ledger 为分区表
    # ================================================================

    op.execute("""
        CREATE TABLE tb_aux_ledger (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            year INTEGER NOT NULL,
            company_code VARCHAR NOT NULL,
            voucher_date DATE,
            voucher_no VARCHAR,
            account_code VARCHAR NOT NULL,
            aux_type VARCHAR,
            aux_code VARCHAR,
            aux_name VARCHAR,
            debit_amount NUMERIC(20,2),
            credit_amount NUMERIC(20,2),
            summary TEXT,
            preparer VARCHAR,
            currency_code VARCHAR(3) NOT NULL DEFAULT 'CNY',
            import_batch_id UUID REFERENCES import_batches(id),
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (id, year)
        ) PARTITION BY RANGE (year);
    """)

    # 创建 2023-2027 年度分区
    for y in range(2023, 2028):
        op.execute(f"""
            CREATE TABLE tb_aux_ledger_{y} PARTITION OF tb_aux_ledger
                FOR VALUES FROM ({y}) TO ({y + 1});
        """)

    # 索引
    op.execute("""
        CREATE INDEX idx_tb_aux_ledger_project_year_account_aux
            ON tb_aux_ledger (project_id, year, account_code, aux_type);
    """)
    op.execute("""
        CREATE INDEX idx_tb_aux_ledger_project_year_aux_type_code
            ON tb_aux_ledger (project_id, year, aux_type, aux_code);
    """)


def downgrade() -> None:
    # 删除分区表（CASCADE 删除所有分区）
    op.execute("DROP TABLE IF EXISTS tb_aux_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS tb_ledger CASCADE")

    # 重建为普通表（简化版，只恢复基本结构）
    op.execute("""
        CREATE TABLE tb_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            year INTEGER NOT NULL,
            company_code VARCHAR NOT NULL,
            voucher_date DATE NOT NULL,
            voucher_no VARCHAR NOT NULL,
            account_code VARCHAR NOT NULL,
            account_name VARCHAR,
            debit_amount NUMERIC(20,2),
            credit_amount NUMERIC(20,2),
            counterpart_account VARCHAR,
            summary TEXT,
            preparer VARCHAR,
            currency_code VARCHAR(3) NOT NULL DEFAULT 'CNY',
            import_batch_id UUID REFERENCES import_batches(id),
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp
        );
    """)
    op.execute("""
        CREATE INDEX idx_tb_ledger_project_year_date_no
            ON tb_ledger (project_id, year, voucher_date, voucher_no);
    """)
    op.execute("""
        CREATE INDEX idx_tb_ledger_project_year_account
            ON tb_ledger (project_id, year, account_code);
    """)

    op.execute("""
        CREATE TABLE tb_aux_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id),
            year INTEGER NOT NULL,
            company_code VARCHAR NOT NULL,
            voucher_date DATE,
            voucher_no VARCHAR,
            account_code VARCHAR NOT NULL,
            aux_type VARCHAR,
            aux_code VARCHAR,
            aux_name VARCHAR,
            debit_amount NUMERIC(20,2),
            credit_amount NUMERIC(20,2),
            summary TEXT,
            preparer VARCHAR,
            currency_code VARCHAR(3) NOT NULL DEFAULT 'CNY',
            import_batch_id UUID REFERENCES import_batches(id),
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP DEFAULT current_timestamp,
            updated_at TIMESTAMP DEFAULT current_timestamp
        );
    """)
    op.execute("""
        CREATE INDEX idx_tb_aux_ledger_project_year_account_aux
            ON tb_aux_ledger (project_id, year, account_code, aux_type);
    """)
