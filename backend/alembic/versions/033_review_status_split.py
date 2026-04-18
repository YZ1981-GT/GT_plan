"""Split workpaper status into lifecycle + review status

Revision ID: 033
Revises: 032
Create Date: 2026-04-18

Adds review_status column to working_paper table.
Creates wp_review_status enum type.
"""

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    # Create the enum type
    wp_review_status = sa.Enum(
        'not_submitted', 'pending_level1', 'level1_in_progress',
        'level1_passed', 'level1_rejected',
        'pending_level2', 'level2_in_progress',
        'level2_passed', 'level2_rejected',
        name='wp_review_status',
    )
    wp_review_status.create(op.get_bind(), checkfirst=True)

    # Add review_status column
    op.add_column(
        'working_paper',
        sa.Column(
            'review_status',
            sa.Enum(
                'not_submitted', 'pending_level1', 'level1_in_progress',
                'level1_passed', 'level1_rejected',
                'pending_level2', 'level2_in_progress',
                'level2_passed', 'level2_rejected',
                name='wp_review_status',
                create_type=False,
            ),
            server_default='not_submitted',
            nullable=False,
        ),
    )

    # Add new values to wp_file_status enum if needed
    # under_review, revision_required, review_passed
    conn = op.get_bind()
    for val in ('under_review', 'revision_required', 'review_passed'):
        try:
            conn.execute(
                sa.text(f"ALTER TYPE wp_file_status ADD VALUE IF NOT EXISTS '{val}'")
            )
        except Exception:
            pass  # Value may already exist


def downgrade() -> None:
    op.drop_column('working_paper', 'review_status')
    sa.Enum(name='wp_review_status').drop(op.get_bind(), checkfirst=True)
