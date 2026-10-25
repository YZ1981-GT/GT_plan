"""ProjectWorkbookInstance ORM（Task 10 / design §10）。

一份整册 = 一个 current artifact + generation + room；
child entries 只承载导航 / capability / G-ID sheet 身份，**不**复制 xlsx/pointer/room。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import String, Integer, BigInteger, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectWorkbookInstanceRow(Base):
    __tablename__ = "project_workbook_instance"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workbook_instance_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    organization_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    wp_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workbook_lineage_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pinned_template_version_id: Mapped[str] = mapped_column(String(128), nullable=False)
    current_artifact_id: Mapped[str] = mapped_column(String(128), nullable=False)
    content_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    representation_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    workbook_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    onlyoffice_room_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    context_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    authorization_epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


class ProjectWorkbookSheetEntryRow(Base):
    __tablename__ = "project_workbook_sheet_entry"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entry_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    workbook_instance_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sheet_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    sheet_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wp_code: Mapped[str] = mapped_column(String(64), nullable=False)
    component_type: Mapped[str] = mapped_column(String(64), nullable=False)
    projection_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    guidance_revision: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    #: child 派生 projection 世代——随 workbook_generation 推进而刷新，但 entry_id 不变
    projection_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "workbook_instance_id",
            "sheet_uid",
            name="ux_pwi_sheet_uid",
        ),
    )
