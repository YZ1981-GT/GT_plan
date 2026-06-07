"""历史映射保存与复用服务。

见 design.md §6 / requirements 需求 6。

核心职责：
1. submit 成功前保存 file_fingerprint / software_fingerprint → mapping_entries
2. 用户修改历史预填时写 override_parent_id（形成父子链）
3. detect 阶段命中历史映射时标记 auto_applied_from_history
4. 禁止跨项目历史映射静默覆盖，跨项目复用必须显式触发

设计选择：
- 使用内存字典存储（本批次不新建 DB 表）
- 30 天窗口：find_matching_history 跳过过期记录
- override_parent_id 形成单链表追溯链
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional


__all__ = [
    "MappingHistoryRecord",
    "MappingHistoryService",
]


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class MappingHistoryRecord:
    """单条历史映射记录。"""

    id: str
    project_id: str
    file_fingerprint: str
    software_fingerprint: Optional[str]
    mapping_entries: list[dict]
    override_parent_id: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# MappingHistoryService
# ---------------------------------------------------------------------------


class MappingHistoryService:
    """历史映射保存与复用。

    使用内存字典存储，适合当前批次的单元测试验证。
    后续可替换为 DB 持久化。
    """

    EXPIRY_DAYS = 30  # 30 天窗口

    def __init__(self) -> None:
        self._store: dict[str, MappingHistoryRecord] = {}

    async def save_mapping(
        self,
        project_id: str,
        file_fingerprint: str,
        software_fingerprint: Optional[str],
        mapping_entries: list[dict],
        override_parent_id: Optional[str] = None,
    ) -> MappingHistoryRecord:
        """保存一条历史映射记录。

        在 submit 成功前调用，确保即使 submit 失败也记录映射尝试。

        Args:
            project_id: 当前项目 ID
            file_fingerprint: 文件指纹（SHA256 等）
            software_fingerprint: 软件指纹（如 yonyou-u8）
            mapping_entries: 列映射条目列表（dict 格式）
            override_parent_id: 被覆盖的父记录 ID（修改历史预填时写入）

        Returns:
            MappingHistoryRecord — 新建的历史记录
        """
        record = MappingHistoryRecord(
            id=str(uuid.uuid4()),
            project_id=project_id,
            file_fingerprint=file_fingerprint,
            software_fingerprint=software_fingerprint,
            mapping_entries=mapping_entries,
            override_parent_id=override_parent_id,
        )
        self._store[record.id] = record
        return record

    async def find_matching_history(
        self,
        file_fingerprint: str,
        software_fingerprint: Optional[str] = None,
        project_id: Optional[str] = None,
        max_age_days: int = 30,
    ) -> Optional[MappingHistoryRecord]:
        """查找匹配的历史映射记录。

        匹配规则：
        1. file_fingerprint 完全匹配
        2. 如果 software_fingerprint 提供，优先匹配同时命中两者的记录
        3. 如果 project_id 提供，只返回该项目的记录
        4. 如果 project_id=None，返回任意项目的记录（跨项目场景）
        5. 超过 max_age_days 的记录不返回

        Args:
            file_fingerprint: 文件指纹
            software_fingerprint: 软件指纹（可选）
            project_id: 项目 ID（None 表示跨项目搜索）
            max_age_days: 最大有效天数

        Returns:
            MappingHistoryRecord | None — 最近的匹配记录，或 None
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        candidates: list[MappingHistoryRecord] = []
        for record in self._store.values():
            # 过期检查
            if record.created_at < cutoff:
                continue
            # fingerprint 匹配
            if record.file_fingerprint != file_fingerprint:
                continue
            # 项目过滤
            if project_id is not None and record.project_id != project_id:
                continue
            candidates.append(record)

        if not candidates:
            return None

        # 优先同时匹配 software_fingerprint
        if software_fingerprint:
            sw_matches = [
                r for r in candidates
                if r.software_fingerprint == software_fingerprint
            ]
            if sw_matches:
                candidates = sw_matches

        # 返回最新的
        candidates.sort(key=lambda r: r.created_at, reverse=True)
        return candidates[0]

    async def apply_history_mapping(
        self,
        history_record: MappingHistoryRecord,
        target_project_id: str,
    ) -> dict:
        """将历史映射应用到目标检测。

        跨项目匹配时必须设置 requires_user_confirmation=True。

        Args:
            history_record: 历史映射记录
            target_project_id: 目标项目 ID

        Returns:
            dict — 包含 auto_applied_from_history, history_mapping_id,
                   requires_user_confirmation 等标记
        """
        is_cross_project = history_record.project_id != target_project_id

        return {
            "auto_applied_from_history": True,
            "history_mapping_id": history_record.id,
            "requires_user_confirmation": is_cross_project,
            "source_project_id": history_record.project_id,
            "mapping_entries": history_record.mapping_entries,
        }
