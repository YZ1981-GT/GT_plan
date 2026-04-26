"""Consolidated baseline migration

Generated: 2026-04-26 18:09
Replaces: 36 individual migration files (archived to _archived/)

This migration is a no-op marker. The actual schema is created by
Base.metadata.create_all() in _init_tables.py.

To initialize a fresh database:
  1. python backend/scripts/_init_tables.py
  2. python backend/scripts/_create_admin.py
  3. alembic stamp head
"""

revision = "001_consolidated"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Schema is managed by create_all(). This is a baseline marker."""
    pass


def downgrade() -> None:
    """Cannot downgrade from baseline."""
    raise RuntimeError("Cannot downgrade from consolidated baseline")
