"""import_column_mapping_history ORM model."""
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ImportColumnMappingHistory(Base):
    """列映射历史记录（F52 / Sprint 8.34 扩展版）。

    两代索引键：
    - ``software_fingerprint`` (既有)：粗粒度，表达 "金蝶 KIS / 用友 U8" 等软件版本。
    - ``file_fingerprint`` (F52 新增)：细粒度 SHA1，基于真实 sheet 名 +
      表头前 20 单元 + software_hint，同一模板文件二次导入能精确命中。

    历史链关系（F52 / override_parent_id）：
    - 用户在 detect 阶段拿到 history mapping 自动应用 + 手动修改几列后再次保存，
      新记录的 ``override_parent_id`` 指向被覆盖的上一代，形成可追溯的版本链。
    - ``override_parent_id IS NULL`` 代表该记录为根 (未基于任何历史而建)。

    30 天窗口（F52）：
    - 命中历史时按 ``created_at > now - 30d`` 做过滤，避免陈旧 mapping
      被错误复用；具体窗口可由调用方覆盖。
    """

    __tablename__ = "import_column_mapping_history"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    project_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    software_fingerprint: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    table_type: Mapped[str] = mapped_column(sa.String(30), nullable=False)
    column_mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    used_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="1")
    last_used_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))

    # F52 / Sprint 8.34: 细粒度文件指纹（sha1(sheet_name + header[:20] + software_hint)）。
    # 老数据 NULL；仅 detect 阶段新建记录时填。
    file_fingerprint: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)

    # F52 / Sprint 8.34: 历史链父记录（保留覆盖溯源）。
    # ondelete="SET NULL" 让旧父记录删除时不触发级联删除整条链。
    override_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        sa.ForeignKey("import_column_mapping_history.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.Index(
            "idx_icmh_project_fingerprint",
            "project_id", "software_fingerprint",
        ),
        # F52: project + file_fingerprint 命中 + 按 created_at 倒序取最新
        sa.Index(
            "idx_icmh_project_file_fp",
            "project_id", "file_fingerprint", "created_at",
        ),
    )
