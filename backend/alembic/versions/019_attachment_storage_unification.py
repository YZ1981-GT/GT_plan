from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "019_attachment_storage"
down_revision = "018"
branch_labels = None
depends_on = None


def _guess_file_type(file_name: str | None) -> str:
    if not file_name or "." not in file_name:
        return "unknown"
    ext = file_name.rsplit(".", 1)[-1].lower()
    if ext in {"jpg", "jpeg", "png", "gif", "bmp", "webp"}:
        return "image"
    if ext in {"xls", "xlsx", "csv"}:
        return "excel"
    if ext in {"doc", "docx"}:
        return "word"
    return ext or "unknown"


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("attachment_type", sa.String(50), server_default=sa.text("'general'"), nullable=False),
    )
    op.add_column(
        "attachments",
        sa.Column("reference_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column("reference_type", sa.String(50), nullable=True),
    )
    op.add_column(
        "attachments",
        sa.Column("storage_type", sa.String(20), server_default=sa.text("'paperless'"), nullable=False),
    )
    op.create_index(
        "idx_attachments_type_ref",
        "attachments",
        ["attachment_type", "reference_type", "reference_id"],
    )
    op.create_index("idx_attachments_storage_type", "attachments", ["storage_type"])

    op.execute(
        sa.text(
            """
            UPDATE attachments
            SET attachment_type = COALESCE(attachment_type, 'general'),
                storage_type = CASE
                    WHEN paperless_document_id IS NOT NULL THEN 'paperless'
                    ELSE 'local'
                END
            """
        )
    )

    conn = op.get_bind()
    legacy_rows = conn.execute(
        sa.text(
            """
            SELECT
                ca.confirmation_list_id,
                ca.file_name,
                ca.file_path,
                COALESCE(ca.file_size, 0) AS file_size,
                ca.uploaded_by,
                ca.is_deleted,
                ca.created_at,
                cl.project_id
            FROM confirmation_attachments ca
            JOIN confirmation_lists cl ON cl.id = ca.confirmation_list_id
            """
        )
    ).mappings().all()

    existing_keys = {
        (
            row["reference_id"],
            row["reference_type"],
            row["file_name"],
            row["file_path"],
        )
        for row in conn.execute(
            sa.text(
                """
                SELECT reference_id, reference_type, file_name, file_path
                FROM attachments
                """
            )
        ).mappings().all()
    }

    for row in legacy_rows:
        key = (
            row["confirmation_list_id"],
            "confirmation_list",
            row["file_name"],
            row["file_path"],
        )
        if key in existing_keys:
            continue

        conn.execute(
            sa.text(
                """
                INSERT INTO attachments (
                    id,
                    project_id,
                    file_name,
                    file_path,
                    file_type,
                    file_size,
                    attachment_type,
                    reference_id,
                    reference_type,
                    storage_type,
                    paperless_document_id,
                    ocr_status,
                    ocr_text,
                    is_deleted,
                    created_by,
                    created_at,
                    updated_at
                ) VALUES (
                    :id,
                    :project_id,
                    :file_name,
                    :file_path,
                    :file_type,
                    :file_size,
                    :attachment_type,
                    :reference_id,
                    :reference_type,
                    :storage_type,
                    :paperless_document_id,
                    :ocr_status,
                    :ocr_text,
                    :is_deleted,
                    :created_by,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "project_id": row["project_id"],
                "file_name": row["file_name"],
                "file_path": row["file_path"],
                "file_type": _guess_file_type(row["file_name"]),
                "file_size": row["file_size"],
                "attachment_type": "confirmation",
                "reference_id": row["confirmation_list_id"],
                "reference_type": "confirmation_list",
                "storage_type": "local",
                "paperless_document_id": None,
                "ocr_status": "pending",
                "ocr_text": None,
                "is_deleted": row["is_deleted"] if row["is_deleted"] is not None else False,
                "created_by": row["uploaded_by"],
                "created_at": row["created_at"],
                "updated_at": row["created_at"],
            },
        )


def downgrade() -> None:
    op.drop_index("idx_attachments_storage_type", table_name="attachments")
    op.drop_index("idx_attachments_type_ref", table_name="attachments")
    op.drop_column("attachments", "storage_type")
    op.drop_column("attachments", "reference_type")
    op.drop_column("attachments", "reference_id")
    op.drop_column("attachments", "attachment_type")
