"""Round 5: Add CHECK constraints for EqcrOpinion.domain and verdict

Revision ID: round5_eqcr_check_constraints_20260506
Revises: round5_independence_20260506

Only applies to PostgreSQL (SQLite does not enforce CHECK constraints the same way).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "round5_eqcr_check_constraints_20260506"
down_revision = "round5_independence_20260506"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only add CHECK constraints on PostgreSQL
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(
        """
        ALTER TABLE eqcr_opinions ADD CONSTRAINT chk_eqcr_opinion_domain
        CHECK (domain IN ('materiality', 'estimate', 'related_party', 'going_concern', 'opinion_type', 'component_auditor'))
        """
    )
    op.execute(
        """
        ALTER TABLE eqcr_opinions ADD CONSTRAINT chk_eqcr_opinion_verdict
        CHECK (verdict IN ('agree', 'disagree', 'need_more_evidence'))
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE eqcr_opinions DROP CONSTRAINT IF EXISTS chk_eqcr_opinion_domain")
    op.execute("ALTER TABLE eqcr_opinions DROP CONSTRAINT IF EXISTS chk_eqcr_opinion_verdict")
