"""Add rejection_reason, rejected_by, rejected_at columns to working_paper table.

Phase 11 Task 3.1: 底稿复核退回原因字段
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/audit_platform",
)
engine = create_engine(DATABASE_URL)

STATEMENTS = [
    "ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejection_reason TEXT;",
    "ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejected_by UUID REFERENCES users(id);",
    "ALTER TABLE working_paper ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP;",
]

with engine.begin() as conn:
    for stmt in STATEMENTS:
        print(f"  executing: {stmt}")
        conn.execute(text(stmt))

print("Done – rejection columns added to working_paper.")
engine.dispose()
