"""formula_runtime.adapters.workpaper — 底稿领域变更适配器。

WorkpaperMutationAdapter 实现 DomainMutationAdapter 协议，
针对 checklist_responses 表的结构化持久化载体提供
prepare/apply/restore/read_versions 四个操作。

locator 结构: {"wp_id": str(uuid), "item": str(item_id), "cell": str(json_path)}
version 策略: 使用 row updated_at ISO 字符串作为 CAS 版本标识。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    FormulaMutation,
    RestoredMutation,
)


class OwnershipViolation(Exception):
    """目标底稿不属于请求项目。"""

    def __init__(self, wp_id: UUID, expected_project: UUID, actual_project: UUID | None):
        self.wp_id = wp_id
        self.expected_project = expected_project
        self.actual_project = actual_project
        super().__init__(
            f"wp {wp_id} does not belong to project {expected_project}"
        )


class VersionConflict(Exception):
    """CAS 版本冲突。"""

    def __init__(self, target: CanonicalFormulaTarget, expected: str | None, current: str | None):
        self.target = target
        self.expected = expected
        self.current = current
        super().__init__(
            f"version conflict for {target.addr_id}: expected={expected}, current={current}"
        )


def _version_from_timestamp(ts: datetime | str | None) -> str:
    """将 updated_at 转换为稳定版本字符串。

    SQLite 返回 TEXT 类型，PostgreSQL 返回 datetime 类型，统一处理。
    """
    if ts is None:
        return "__none__"
    if isinstance(ts, str):
        return ts
    return ts.isoformat()


def _cell_read(remark_json: str | None, cell: str) -> Any:
    """从 remark JSON 中按 cell (json path) 读取值。

    cell 格式:
    - "." 表示整个 remark 值
    - "key" 表示顶层 key
    - "key.sub" 表示嵌套路径
    """
    if remark_json is None:
        return None
    try:
        data = json.loads(remark_json) if isinstance(remark_json, str) else remark_json
    except (json.JSONDecodeError, TypeError):
        return None
    if cell == ".":
        return data
    parts = cell.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _cell_write(remark_json: str | None, cell: str, value: Any) -> str:
    """向 remark JSON 中按 cell (json path) 写入值，返回新 JSON 字符串。"""
    if remark_json is None or remark_json == "":
        data: Any = {}
    else:
        try:
            data = json.loads(remark_json) if isinstance(remark_json, str) else remark_json
        except (json.JSONDecodeError, TypeError):
            data = {}

    if cell == ".":
        return json.dumps(value, ensure_ascii=False)

    parts = cell.split(".")
    current = data
    for part in parts[:-1]:
        if not isinstance(current, dict):
            current = {}
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    if isinstance(current, dict):
        current[parts[-1]] = value
    return json.dumps(data, ensure_ascii=False)


def _locator_key(locator: dict[str, str] | Any) -> str:
    """从 locator 构建唯一标识键。"""
    wp_id = locator.get("wp_id", "")
    item = locator.get("item", "")
    cell = locator.get("cell", "")
    return f"{wp_id}::{item}::{cell}"


class WorkpaperMutationAdapter:
    """底稿领域变更适配器，实现 DomainMutationAdapter 协议。"""

    domain: str = "workpaper"

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _verify_ownership(self, wp_id: UUID, project_id: UUID) -> None:
        """校验 working_paper.project_id == target.project_id。"""
        result = await self._session.execute(
            text("SELECT project_id FROM working_paper WHERE id = :wp_id"),
            {"wp_id": str(wp_id)},
        )
        row = result.fetchone()
        if row is None:
            raise OwnershipViolation(wp_id, project_id, None)
        actual_pid = UUID(str(row[0])) if not isinstance(row[0], UUID) else row[0]
        if actual_pid != project_id:
            raise OwnershipViolation(wp_id, project_id, actual_pid)

    async def _read_row(self, wp_id: UUID, item_id: str) -> tuple[str | None, datetime | None]:
        """读取 checklist_responses 中的 remark 和 updated_at。"""
        result = await self._session.execute(
            text(
                "SELECT remark, updated_at FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id = :item_id"
            ),
            {"wp_id": str(wp_id), "item_id": item_id},
        )
        row = result.fetchone()
        if row is None:
            return None, None
        return row[0], row[1]

    async def prepare_many(
        self,
        targets: list[CanonicalFormulaTarget],
        values: dict[str, Any],
    ) -> list[FormulaMutation]:
        """读取当前值并构建 mutation，不做写入。"""
        mutations: list[FormulaMutation] = []
        for target in targets:
            locator = dict(target.locator)
            wp_id_str = locator.get("wp_id")
            item_id = locator.get("item")
            cell = locator.get("cell", ".")
            if not wp_id_str or not item_id:
                continue

            wp_id = UUID(wp_id_str)
            # ownership check during prepare
            await self._verify_ownership(wp_id, target.project_id)

            remark, updated_at = await self._read_row(wp_id, item_id)
            before_value = _cell_read(remark, cell)
            version = _version_from_timestamp(updated_at)

            # after_value 来自 values dict, key 为 addr_id
            after_value = values.get(target.addr_id, before_value)

            mutations.append(
                FormulaMutation(
                    target=target,
                    before_value=before_value,
                    after_value=after_value,
                    expected_version=version,
                    source_formula_id=None,
                )
            )
        return mutations

    async def apply_many(
        self,
        mutations: list[FormulaMutation],
    ) -> list[AppliedMutation]:
        """写入新值，校验项目归属与版本。仅 flush 不 commit。"""
        applied: list[AppliedMutation] = []
        now = datetime.now(timezone.utc)

        for mutation in mutations:
            locator = dict(mutation.target.locator)
            wp_id = UUID(locator["wp_id"])
            item_id = locator["item"]
            cell = locator.get("cell", ".")

            # 再次校验归属
            await self._verify_ownership(wp_id, mutation.target.project_id)

            # 版本校验 (CAS)
            remark, updated_at = await self._read_row(wp_id, item_id)
            current_version = _version_from_timestamp(updated_at)
            if mutation.expected_version is not None and current_version != mutation.expected_version:
                raise VersionConflict(mutation.target, mutation.expected_version, current_version)

            # 写入新值
            new_remark = _cell_write(remark, cell, mutation.after_value)

            # UPSERT
            await self._session.execute(
                text(
                    "INSERT INTO checklist_responses (wp_id, item_id, remark, updated_at) "
                    "VALUES (:wp_id, :item_id, :remark, :updated_at) "
                    "ON CONFLICT (wp_id, item_id) DO UPDATE "
                    "SET remark = :remark, updated_at = :updated_at"
                ),
                {
                    "wp_id": str(wp_id),
                    "item_id": item_id,
                    "remark": new_remark,
                    "updated_at": now.isoformat(),
                },
            )
            await self._session.flush()

            applied.append(
                AppliedMutation(
                    target=mutation.target,
                    applied_version=now.isoformat(),
                    applied_at=now.isoformat(),
                )
            )
        return applied

    async def restore_many(
        self,
        snapshots: list[FormulaMutation],
    ) -> list[RestoredMutation]:
        """恢复 before_value，使用 optimistic version check。

        恢复时 expected_version 应为 apply 时写入的 applied_version，
        即当前值必须等于 apply 后的版本（未被后续编辑修改）。
        """
        restored: list[RestoredMutation] = []
        now = datetime.now(timezone.utc)

        for snapshot in snapshots:
            locator = dict(snapshot.target.locator)
            wp_id = UUID(locator["wp_id"])
            item_id = locator["item"]
            cell = locator.get("cell", ".")

            # 归属校验
            await self._verify_ownership(wp_id, snapshot.target.project_id)

            # Optimistic version check
            remark, updated_at = await self._read_row(wp_id, item_id)
            current_version = _version_from_timestamp(updated_at)

            conflict = False
            conflict_detail = None
            if snapshot.expected_version is not None and current_version != snapshot.expected_version:
                conflict = True
                conflict_detail = (
                    f"expected={snapshot.expected_version}, current={current_version}"
                )
                restored.append(
                    RestoredMutation(
                        target=snapshot.target,
                        restored_version=current_version,
                        conflict=True,
                        conflict_detail=conflict_detail,
                    )
                )
                continue

            # 恢复 before_value
            new_remark = _cell_write(remark, cell, snapshot.before_value)
            await self._session.execute(
                text(
                    "UPDATE checklist_responses "
                    "SET remark = :remark, updated_at = :updated_at "
                    "WHERE wp_id = :wp_id AND item_id = :item_id"
                ),
                {
                    "wp_id": str(wp_id),
                    "item_id": item_id,
                    "remark": new_remark,
                    "updated_at": now.isoformat(),
                },
            )
            await self._session.flush()

            restored.append(
                RestoredMutation(
                    target=snapshot.target,
                    restored_version=now.isoformat(),
                    conflict=False,
                    conflict_detail=None,
                )
            )
        return restored

    async def read_versions(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, str]:
        """返回每个 target 的当前版本字符串。"""
        versions: dict[str, str] = {}
        for target in targets:
            locator = dict(target.locator)
            wp_id_str = locator.get("wp_id")
            item_id = locator.get("item")
            if not wp_id_str or not item_id:
                continue
            wp_id = UUID(wp_id_str)
            _, updated_at = await self._read_row(wp_id, item_id)
            versions[target.addr_id] = _version_from_timestamp(updated_at)
        return versions
