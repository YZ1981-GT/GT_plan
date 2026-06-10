"""出品物章节级状态服务：快照计算 / stale 标记 / 查询。

仅承载状态逻辑，不含传播逻辑（传播复用 StalePropagationEngine）。
服务签名统一以 word_export_task_id 为出品物标识键。

Spec: deliverable-lineage-and-writeback
Design: 组件「3. DeliverableSectionStateService」+ 数据模型「Source_Snapshot_Hash 计算口径」+ 决策 D8/D9
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import DeliverableSectionState, TrialBalance
from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

# 附注种子数据路径（与 disclosure_engine 一致）
_SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"

# 种子数据模块级缓存
_seed_cache: dict | None = None


def _load_seed() -> dict:
    """延迟加载附注种子数据（含 sections→account_codes 映射）。"""
    global _seed_cache
    if _seed_cache is not None:
        return _seed_cache
    if not _SEED_DATA_PATH.exists():
        _seed_cache = {}
        return _seed_cache
    try:
        _seed_cache = json.loads(_SEED_DATA_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as err:
        logger.warning("Failed to load note_templates_seed.json: %s", err)
        _seed_cache = {}
    return _seed_cache


def _get_account_codes_for_section(section_code: str) -> list[str]:
    """从种子数据获取章节关联的科目编码列表。"""
    seed = _load_seed()
    for section in seed.get("sections", []):
        if section.get("note_section") == section_code:
            return section.get("account_codes", [])
        # 也匹配 section_number 字段
        if section.get("section_number") == section_code:
            return section.get("account_codes", [])
    return []


def compute_snapshot_hash_from_parts(
    section_code: str,
    text_content: str | None,
    table_data: dict | None,
    audited_amounts: list[dict[str, str]],
) -> str:
    """纯函数：根据已收集的数据计算确定性 sha256 哈希。

    Args:
        section_code: 章节编码（canonical）
        text_content: 附注文字内容
        table_data: 附注表格数据（JSONB dict）
        audited_amounts: 按 account_code 排序的审定金额列表
            每项 {"account_code": "...", "audited_amount": "..."}

    Returns:
        sha256 hex digest（64 字符）
    """
    snapshot_input = {
        "section_code": section_code,
        "text_content": text_content or "",
        "table_data": table_data if table_data is not None else {},
        "audited_amounts": audited_amounts,
    }
    serialized = json.dumps(
        snapshot_input,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


class DeliverableSectionStateService:
    """出品物章节级状态：快照计算 / stale 标记 / 查询。

    仅承载状态，不含传播逻辑（传播复用 StalePropagationEngine）。
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def compute_source_snapshot_hash(
        self,
        project_id: UUID,
        year: int,
        section_code: str,
    ) -> str:
        """计算章节源快照哈希（需求 4.1 / 10.5）。

        覆盖：disclosure_notes.text_content + table_data + 相关 audited_amount。
        规范化 JSON（sort_keys, ensure_ascii=False, separators=(",",":")）→ sha256，确定性。

        与 doc 级 tb_hash 分层配合（D9）：tb_hash 不含 text_content，
        本章节级 hash 在其口径上细化到 section_code + text_content。
        """
        # 1. 读取 disclosure_notes 记录
        note_stmt = sa.select(
            DisclosureNote.text_content,
            DisclosureNote.table_data,
        ).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.note_section == section_code,
            DisclosureNote.is_deleted == sa.false(),
        )
        note_result = await self.db.execute(note_stmt)
        note_row = note_result.first()

        text_content: str | None = None
        table_data: dict | None = None
        if note_row:
            text_content = note_row.text_content
            table_data = note_row.table_data

        # 2. 获取相关 audited_amount（按 account_code 排序，金额转字符串）
        account_codes = _get_account_codes_for_section(section_code)
        audited_amounts: list[dict[str, str]] = []
        if account_codes:
            tb_stmt = (
                sa.select(
                    TrialBalance.standard_account_code,
                    TrialBalance.audited_amount,
                )
                .where(
                    TrialBalance.project_id == project_id,
                    TrialBalance.year == year,
                    TrialBalance.standard_account_code.in_(account_codes),
                    TrialBalance.is_deleted == sa.false(),
                )
                .order_by(TrialBalance.standard_account_code)
            )
            tb_result = await self.db.execute(tb_stmt)
            for row in tb_result.all():
                audited_amounts.append({
                    "account_code": row.standard_account_code,
                    "audited_amount": str(row.audited_amount) if row.audited_amount is not None else "0",
                })

        # 3. 计算确定性 hash
        return compute_snapshot_hash_from_parts(
            section_code=section_code,
            text_content=text_content,
            table_data=table_data,
            audited_amounts=audited_amounts,
        )

    async def snapshot_on_confirm(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        kept_codes: list[str],
    ) -> None:
        """confirm 生成时为每个保留章节 upsert 快照 + 清 stale（需求 4.1/4.6）。

        对每个 kept_codes 中的 section_code：
        1. 计算 source_snapshot_hash
        2. upsert deliverable_section_state（insert or update on conflict）
        3. 清除 is_stale
        """
        for section_code in kept_codes:
            snapshot_hash = await self.compute_source_snapshot_hash(
                project_id, year, section_code
            )
            # upsert: 利用唯一约束 (word_export_task_id, section_code)
            existing_stmt = sa.select(DeliverableSectionState).where(
                DeliverableSectionState.word_export_task_id == word_export_task_id,
                DeliverableSectionState.section_code == section_code,
            )
            result = await self.db.execute(existing_stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.source_snapshot_hash = snapshot_hash
                existing.is_stale = False
                existing.project_id = project_id
                existing.year = year
            else:
                new_state = DeliverableSectionState(
                    word_export_task_id=word_export_task_id,
                    project_id=project_id,
                    year=year,
                    section_code=section_code,
                    source_snapshot_hash=snapshot_hash,
                    is_stale=False,
                )
                self.db.add(new_state)

        await self.db.flush()

    async def mark_section_stale(
        self,
        word_export_task_id: UUID,
        section_code: str,
        *,
        source_uri: str,
    ) -> int:
        """被 StalePropagationEngine 调用，置章节 is_stale=true。

        Returns:
            受影响行数（0 或 1）
        """
        stmt = (
            sa.update(DeliverableSectionState)
            .where(
                DeliverableSectionState.word_export_task_id == word_export_task_id,
                DeliverableSectionState.section_code == section_code,
            )
            .values(is_stale=True)
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        count = result.rowcount  # type: ignore[union-attr]
        if count:
            logger.info(
                "Marked section stale: task=%s section=%s source=%s",
                word_export_task_id,
                section_code,
                source_uri,
            )
        return count

    async def clear_section_stale(
        self,
        word_export_task_id: UUID,
        section_code: str,
        new_hash: str,
    ) -> None:
        """增量刷新/全量刷新后清 stale + 更新快照（需求 4.6 / 5.3）。"""
        stmt = (
            sa.update(DeliverableSectionState)
            .where(
                DeliverableSectionState.word_export_task_id == word_export_task_id,
                DeliverableSectionState.section_code == section_code,
            )
            .values(
                is_stale=False,
                source_snapshot_hash=new_hash,
            )
        )
        await self.db.execute(stmt)
        await self.db.flush()

    async def get_section_states(
        self,
        word_export_task_id: UUID,
    ) -> list[dict]:
        """供 Lineage_Panel 与回填冲突检测查询章节状态 + 基线 hash。

        Returns:
            list of dicts with keys:
            section_code, source_snapshot_hash, is_stale,
            last_writeback_baseline_hash, anchor_name
        """
        stmt = sa.select(DeliverableSectionState).where(
            DeliverableSectionState.word_export_task_id == word_export_task_id,
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        return [
            {
                "section_code": row.section_code,
                "source_snapshot_hash": row.source_snapshot_hash,
                "is_stale": row.is_stale,
                "last_writeback_baseline_hash": row.last_writeback_baseline_hash,
                "anchor_name": row.anchor_name,
                "version_no": row.version_no,
            }
            for row in rows
        ]

    async def detect_stale_sections_layered(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
    ) -> list[str]:
        """分层 stale 检测（D9）：先比 doc 级 tb_hash，变了才逐章算。

        复用 DeliverableSnapshotService 的 tb_hash 作为整份文档的廉价闸门：
        1. 从 WordExportTask.source_snapshot_refs 读取绑定时的 tb_hash
        2. 计算当前 tb_hash（via DeliverableSnapshotService）
        3. tb_hash 未变 → 返回空列表（整份未变，跳过逐章计算）
        4. tb_hash 变了 → 逐章节计算 section hash，与存储 hash 比对

        Returns:
            变更的 section_code 列表（tb_hash 未变时返回空列表）
        """
        from app.models.phase13_models import WordExportTask
        from app.services.deliverable_snapshot_service import DeliverableSnapshotService

        # 1. 读取绑定的 tb_hash（doc 级闸门）
        task_stmt = sa.select(WordExportTask).where(
            WordExportTask.id == word_export_task_id,
        )
        task_result = await self.db.execute(task_stmt)
        task = task_result.scalar_one_or_none()

        if task is None:
            logger.warning(
                "detect_stale_sections_layered: task not found %s",
                word_export_task_id,
            )
            return []

        refs = task.source_snapshot_refs
        if not isinstance(refs, dict) or not refs.get("tb_hash"):
            # 无绑定快照引用，无法判定，返回空
            logger.info(
                "detect_stale_sections_layered: no bound tb_hash for task %s",
                word_export_task_id,
            )
            return []

        bound_tb_hash = refs["tb_hash"]

        # 2. 计算当前 tb_hash（复用 DeliverableSnapshotService）
        snap_svc = DeliverableSnapshotService(self.db)
        current_ref = await snap_svc.capture_snapshot_ref(project_id, year, task.doc_type)
        current_tb_hash = current_ref.tb_hash

        # 3. tb_hash 未变 → 整份未变，跳过逐章计算
        if bound_tb_hash == current_tb_hash:
            return []

        # 4. tb_hash 变了 → 逐章节计算 section hash 定位具体变更
        section_stmt = sa.select(DeliverableSectionState).where(
            DeliverableSectionState.word_export_task_id == word_export_task_id,
        )
        section_result = await self.db.execute(section_stmt)
        sections = section_result.scalars().all()

        if not sections:
            return []

        stale_codes: list[str] = []
        for section in sections:
            current_hash = await self.compute_source_snapshot_hash(
                project_id, year, section.section_code
            )
            if current_hash != section.source_snapshot_hash:
                stale_codes.append(section.section_code)

        return stale_codes

    async def detect_upstream_drift(
        self,
        word_export_task_id: UUID,
        project_id: UUID,
        year: int,
        section_code: str,
    ) -> bool:
        """冲突检测用（需求 8.1）：当前 DB 内容哈希 ≠ 生成时基线 hash → 上游已独立修改。

        Returns:
            True 表示上游已漂移（发生冲突），False 表示一致。
        """
        # 读取存储的基线 hash
        stmt = sa.select(DeliverableSectionState.source_snapshot_hash).where(
            DeliverableSectionState.word_export_task_id == word_export_task_id,
            DeliverableSectionState.section_code == section_code,
        )
        result = await self.db.execute(stmt)
        baseline_hash = result.scalar_one_or_none()

        if baseline_hash is None:
            # 无基线记录，视为无漂移（可能尚未 confirm）
            return False

        # 计算当前 DB 内容 hash
        current_hash = await self.compute_source_snapshot_hash(
            project_id, year, section_code
        )

        return current_hash != baseline_hash
