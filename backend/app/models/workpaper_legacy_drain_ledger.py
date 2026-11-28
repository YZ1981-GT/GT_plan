# -*- coding: utf-8 -*-
"""旧式 doc key / callback 的 drain ledger ORM（V277）。

spec: onlyoffice-sheet-open-via-published-artifact 任务 4.2

═══ 为什么单独一个文件（不在 workpaper_sync_models.py 里）═══

`workpaper_sync_models.py` 已在 `file_size_whitelist.txt` 基线 +5% 边缘
（whitelist 1152，上限约 1209）。本表加进去会越过门限，而本仓纪律是
「优先拆模块，不抬白名单」。

═══ 为什么本表刻意不进 WORKPAPER_SYNC_TABLES ═══

那张字典的语义是「V151 的 28 张表」，`test_orm_covers_exactly_the_v151_tables`
以完全相等锁死它（多一张即红）。本表 DDL 真源是
`backend/migrations/V277__workpaper_legacy_drain_ledger.sql`，由本 spec 自己的
守卫做 DDL 与 ORM 双向比对，不挂在 V151 的分母上。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.workpaper_sync_models import _DIGEST, _TS, _UUID, _pk


class WorkpaperLegacyDrainLedger(Base):
    """旧式 doc key / callback 签发与结算的 append-only ledger（V277）。

    为什么 append-only（签发行 + 结算行两行）：
    「已签发 -> 已结算」是状态跃迁，但审计要能回答「这一条何时被结算」。
    原地覆盖会让「先 draining 后过期」与「直接过期」不可区分，而这两者在
    Requirement 6.3 的语义下处置不同（前者是正常收尾，后者是超时放弃）。

    为什么存 doc_key 的哈希而不存明文：
    doc_key 是 OO 房间身份。明文落库等于把可伪造的会话标识写进审计表；
    查「某个 doc_key 有没有签发记录」用等值哈希查询即可，不需要明文。
    """

    __tablename__ = "working_paper_legacy_drain_ledger"

    id: Mapped[uuid.UUID] = _pk()
    # issued = 旧式 doc key / callback URL 已签发；settled = 该签发已终结
    event_kind: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    # issued 行恒 NULL；settled 行指向被结算的 issued 行
    issuance_id: Mapped[uuid.UUID | None] = mapped_column(
        _UUID, ForeignKey("working_paper_legacy_drain_ledger.id"), nullable=True
    )
    # 签发时的 binding 快照（迁移后可回溯当时按哪条 binding 签的）
    binding_id: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
    binding_status: Mapped[str | None] = mapped_column(sa.String(40), nullable=True)
    entry_id: Mapped[str] = mapped_column(sa.String(300), nullable=False)
    source_wp_code: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(sa.String(300), nullable=True)
    whole_workbook: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.text("false")
    )
    wp_id: Mapped[uuid.UUID] = mapped_column(_UUID, nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(_UUID, nullable=False)
    # doc_key 的 sha256（不存明文，见类 docstring）
    doc_key_sha256: Mapped[str | None] = mapped_column(_DIGEST, nullable=True)
    # room 代际。旧式链路可能没有 room，故可空
    generation: Mapped[int | None] = mapped_column(sa.BigInteger, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        _TS, nullable=False, server_default=sa.func.now()
    )
    # TTL 到期时刻。drain 的「已签发者还能存」边界就是它
    expires_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    # settled 行的终结状态；issued 行为 NULL
    terminal_state: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    terminal_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    # 结算时 callback 是否仍在途（任务 4.4 的 in-flight 计数来源）
    callback_in_flight: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
