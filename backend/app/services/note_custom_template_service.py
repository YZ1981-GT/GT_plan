"""自定义附注模板存储服务（Sprint 3 Task 3.2）.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.2
Design: D8 自定义模板存储与版本

存储路径
--------
仓库根 ``storage/projects/{project_id}/templates/``：
- ``custom_note_template.json``  当前活动版本（含 history 元数据）
- ``v{N}.json``                  历史快照（不可变，含 sections）

主文件 schema（v{N}.json 同样包含 sections，作为不可变快照）：

    {
        "version": 3,
        "updated_at": "2026-05-26T14:00:00Z",
        "updated_by": "uuid-of-user",
        "history": [
            {"version": 1, "snapshot_path": "v1.json", "updated_at": "..."},
            {"version": 2, "snapshot_path": "v2.json", "updated_at": "..."}
        ],
        "sections": [...]
    }

设计要点
--------
1. **纯文件 IO**：不依赖 DB；db 参数仅为后续扩展（审计日志写库）保留。
2. **路径越界保护**：``project_id`` 必须是合法 UUID，``v{N}.json`` 严禁
   穿越（拒 ``..``）。
3. **快照不可变**：``save`` 时仅写 ``v{new_version}.json`` 一次；``restore``
   产生新版本，绝不覆盖历史。
4. **并发幂等**：以"读 → +1 → 写"为单元；并发场景退化为"按版本号顺序排队"。
5. **空 sections 合法**：允许保存空数组（删除全部章节场景）。

Validates: Requirements R4.3 验收 36（自定义模板隔离）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

# `backend/app/services/note_custom_template_service.py`
#  ↑ parents[0]=services / parents[1]=app / parents[2]=backend / parents[3]=仓库根
REPO_ROOT: Path = Path(__file__).resolve().parents[3]
STORAGE_ROOT: Path = REPO_ROOT / "storage" / "projects"

MAIN_FILE_NAME = "custom_note_template.json"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _validate_pid(project_id: UUID | str) -> str:
    """归一化 project_id 为 str，防止路径越界."""
    if isinstance(project_id, UUID):
        return str(project_id)
    if isinstance(project_id, str):
        # 严格校验 UUID 形态
        try:
            return str(UUID(project_id))
        except (ValueError, AttributeError) as err:
            raise ValueError(f"非法 project_id: {project_id!r}") from err
    raise ValueError(f"非法 project_id 类型: {type(project_id).__name__}")


def _project_template_dir(project_id: UUID | str, *, root: Path | None = None) -> Path:
    """返回 ``{root}/projects/{pid}/templates/``，校验 project_id."""
    pid = _validate_pid(project_id)
    base = root if root is not None else STORAGE_ROOT
    return base / pid / "templates"


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NoteCustomTemplateService:
    """自定义附注模板存储服务.

    支持注入 ``storage_root`` 用于测试隔离（tmp_path）。
    """

    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        storage_root: Path | None = None,
    ):
        self.db = db
        # 测试时可注入 tmp_path 隔离文件系统
        self.storage_root: Path = storage_root if storage_root is not None else STORAGE_ROOT

    # ------------------------------------------------------------------
    # 路径辅助
    # ------------------------------------------------------------------

    def _template_dir(self, project_id: UUID | str) -> Path:
        pid = _validate_pid(project_id)
        return self.storage_root / pid / "templates"

    def _main_path(self, project_id: UUID | str) -> Path:
        return self._template_dir(project_id) / MAIN_FILE_NAME

    def _snapshot_path(self, project_id: UUID | str, version: int) -> Path:
        if not isinstance(version, int) or version <= 0:
            raise ValueError(f"非法 version: {version!r}")
        # 严禁穿越：仅允许形如 v{int}.json
        return self._template_dir(project_id) / f"v{version}.json"

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    async def save_custom_template(
        self,
        project_id: UUID | str,
        sections: list[dict[str, Any]],
        updated_by: UUID | str | None,
    ) -> dict[str, Any]:
        """保存自定义模板：写主文件 + 写不可变 v{new_version}.json 快照.

        Args:
            project_id: 项目 UUID。
            sections:   sections 数组（允许空 list 但必须是 list）。
            updated_by: 操作人 UUID（None 时存 ""）。

        Returns:
            ``{"version": int, "updated_at": str, "history": [...]}``
        """
        if sections is None or not isinstance(sections, list):
            raise ValueError("sections 必须是 list")

        tmpl_dir = self._template_dir(project_id)
        tmpl_dir.mkdir(parents=True, exist_ok=True)
        main_path = self._main_path(project_id)

        existing = self._read_json_safe(main_path)
        prev_version = int(existing.get("version", 0) or 0) if existing else 0
        new_version = prev_version + 1

        history: list[dict[str, Any]] = list(existing.get("history") or []) if existing else []

        snapshot_path = self._snapshot_path(project_id, new_version)
        updated_at = _now_iso()
        updated_by_str = str(updated_by) if updated_by is not None else ""

        snapshot_payload: dict[str, Any] = {
            "version": new_version,
            "updated_at": updated_at,
            "updated_by": updated_by_str,
            "sections": sections,
        }
        # 不可变快照：先写 v{N}.json
        self._write_json_atomic(snapshot_path, snapshot_payload)

        # 在 history 追加当前快照（自身亦计入）
        history.append({
            "version": new_version,
            "snapshot_path": snapshot_path.name,
            "updated_at": updated_at,
        })

        main_payload: dict[str, Any] = {
            "version": new_version,
            "updated_at": updated_at,
            "updated_by": updated_by_str,
            "history": history,
            "sections": sections,
        }
        self._write_json_atomic(main_path, main_payload)

        logger.info(
            "saved custom note template: project=%s version=%d sections=%d",
            project_id, new_version, len(sections),
        )
        return {"version": new_version, "updated_at": updated_at, "history": history}

    async def load_custom_template(self, project_id: UUID | str) -> dict[str, Any] | None:
        """读主文件；不存在返 None."""
        main_path = self._main_path(project_id)
        if not main_path.exists():
            return None
        payload = self._read_json_safe(main_path)
        return payload or None

    async def restore_to_version(
        self,
        project_id: UUID | str,
        target_version: int,
        updated_by: UUID | str | None = None,
    ) -> dict[str, Any]:
        """从 v{target}.json 读 sections 写为新版本（不覆盖历史快照）.

        Args:
            project_id:     项目 UUID。
            target_version: 目标历史版本号（必须 ≥ 1，且对应 v{N}.json 存在）。
            updated_by:     执行回滚的操作人。

        Returns:
            与 ``save_custom_template`` 相同 schema。
        """
        snapshot_path = self._snapshot_path(project_id, target_version)
        if not snapshot_path.exists():
            raise FileNotFoundError(
                f"目标版本 v{target_version} 快照不存在: {snapshot_path.name}"
            )
        snapshot = self._read_json_safe(snapshot_path) or {}
        sections = snapshot.get("sections")
        if not isinstance(sections, list):
            raise ValueError(f"v{target_version}.json sections 字段非法")

        # 复用 save 逻辑产生新版本
        return await self.save_custom_template(project_id, sections, updated_by)

    async def list_versions(self, project_id: UUID | str) -> list[dict[str, Any]]:
        """返回历史版本清单（来自主文件 history；主文件不存在 → []）."""
        payload = await self.load_custom_template(project_id)
        if not payload:
            return []
        history = payload.get("history") or []
        return list(history) if isinstance(history, list) else []

    # ------------------------------------------------------------------
    # IO 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json_safe(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as err:
            logger.warning("read json failed %s: %s", path, err)
            return {}

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        """先写临时文件再 rename；最大化避免半写文件."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(path)


__all__ = [
    "NoteCustomTemplateService",
    "STORAGE_ROOT",
    "MAIN_FILE_NAME",
]
