"""import_column_mapping_history ORM model."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ImportColumnMappingHistory(Base):
    __tablename__ = "import_column_mapping_history"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    software_fingerprint: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    table_type: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    used_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    last_used_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
