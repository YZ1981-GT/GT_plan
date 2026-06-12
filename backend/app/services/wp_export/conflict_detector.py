"""ConflictDetector — 冲突检测器 【复用】check_version_conflict + 新增哈希层

两层冲突检测：
1. 版本号比对（复用现有 WpUploadService.check_version_conflict 逻辑）
2. 内容哈希实质冲突判断（新增）：版本号冲突时查 wp_export_snapshot 的
   snapshot_hash 与当前内容 hash 比对 → 判断是否为实质冲突

设计原则：
- detect() 是纯函数（不需 DB），方便 PBT 测试
- 字段级冲突继续由现有 offline_conflict_service.detect 负责（不重建）

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.wp_export_schemas import ConflictResult


class ConflictDetector:
    """冲突检测器：版本号 + 内容哈希双层检测"""

    def detect(
        self,
        imported_version: int,
        server_version: int,
        export_hash: str | None = None,
        current_hash: str | None = None,
    ) -> ConflictResult:
        """两层冲突检测：版本号 + 内容哈希。

        Layer 1: imported_version < server_version → 版本冲突
        Layer 2: 版本冲突时比较 export_hash vs current_hash → 实质冲突判断

        Args:
            imported_version: 导入文件携带的 file_version
            server_version: 服务器当前 file_version
            export_hash: 导出时记录的 snapshot_hash（从 wp_export_snapshot 获取）
            current_hash: 服务器当前内容的 hash

        Returns:
            ConflictResult 包含冲突状态和详情
        """
        # Layer 1: 版本号比对
        if imported_version >= server_version:
            # 无冲突
            return ConflictResult(
                has_conflict=False,
                conflict_type=None,
                server_version=server_version,
                imported_version=imported_version,
                is_substantive=False,
            )

        # Layer 2: 实质冲突判断（内容是否真的变了）
        is_substantive = self._is_substantive_conflict(export_hash, current_hash)

        conflict_type: str
        if is_substantive:
            conflict_type = "both"  # 版本号冲突 + 内容实质变更
        else:
            conflict_type = "version"  # 仅版本号冲突，内容未变

        return ConflictResult(
            has_conflict=True,
            conflict_type=conflict_type,
            server_version=server_version,
            imported_version=imported_version,
            is_substantive=is_substantive,
        )

    def _is_substantive_conflict(
        self, export_hash: str | None, current_hash: str | None
    ) -> bool:
        """判断是否为实质冲突（内容真的变了）。

        - export_hash != current_hash → 实质冲突
        - export_hash == current_hash → 非实质冲突（仅版本号差异）
        - 任一 hash 为 None → 保守认为实质冲突（无快照记录时）

        Args:
            export_hash: 导出时的 snapshot_hash
            current_hash: 当前内容的 hash

        Returns:
            True 表示实质冲突，False 表示非实质冲突
        """
        if export_hash is None or current_hash is None:
            # 无快照记录，保守认为实质冲突
            return True

        return export_hash != current_hash
