"""formula_runtime.adapters.consol_worksheet — 合并工作底稿领域变更适配器。

ConsolWorksheetMutationAdapter 实现 DomainMutationAdapter 协议，
按 (project_id, year, sheet_key) 定位 JSON 数据，通过 row_identity/cell_identity
读写具体单元格，使用整数 version 做乐观并发 CAS。

locator 必含:
  - sheet_key: 表键（如 'info', 'equity_inv', 'share_change_1'）
  - row_identity: 行定位（对象 key 或数组下标字符串）
  - cell_identity: 列/字段名

spec: consol-node-key-isolation-and-shared-context 任务 8.3
设计: §十二.3（ADR-CNSC-008）
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_runtime.contracts import (
    AppliedMutation,
    CanonicalFormulaTarget,
    FormulaMutation,
    RestoredMutation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REQUIRED_LOCATOR_KEYS = frozenset({"sheet_key", "row_identity", "cell_identity"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_locator(target: CanonicalFormulaTarget) -> str | None:
    """校验 locator 必需键。返回错误信息或 None。"""
    missing = _REQUIRED_LOCATOR_KEYS - set(target.locator.keys())
    if missing:
        return f"locator 缺少必需键: {sorted(missing)}"
    return None


def _get_cell_value(data: Any, row_identity: str, cell_identity: str) -> Any:
    """从工作底稿 JSON 中按行/列身份提取值。

    支持两种形态：
    - 对象行：data 是 dict，row_identity 作为 key
    - 二维数组：data["rows"] 是 list，row_identity 是数组下标
    """
    if not isinstance(data, dict):
        return None

    # 1. data[row_identity][cell_identity] — 直接嵌套 dict
    if row_identity in data:
        row_data = data[row_identity]
        if isinstance(row_data, dict) and cell_identity in row_data:
            return row_data[cell_identity]

    # 2. data["rows"] 结构
    rows = data.get("rows")
    if rows is None:
        if cell_identity in data:
            return data[cell_identity]
        return None

    # 2a. rows 是 list
    if isinstance(rows, list):
        try:
            idx = int(row_identity)
            if 0 <= idx < len(rows):
                row = rows[idx]
                if isinstance(row, dict) and cell_identity in row:
                    return row[cell_identity]
        except (ValueError, TypeError):
            for row in rows:
                if isinstance(row, dict):
                    row_id = str(
                        row.get("_id")
                        or row.get("company_code")
                        or row.get("item_id")
                        or ""
                    )
                    if row_id == row_identity and cell_identity in row:
                        return row[cell_identity]
        return None

    # 2b. rows 是 dict
    if isinstance(rows, dict):
        row_data = rows.get(row_identity)
        if isinstance(row_data, dict) and cell_identity in row_data:
            return row_data[cell_identity]

    return None


def _set_cell_value(
    data: Any, row_identity: str, cell_identity: str, value: Any,
) -> dict:
    """在 JSON 数据中设置单元格值，返回新 dict（触发 ORM 脏标记）。"""
    if data is None:
        data = {}
    # 深拷贝确保 ORM 脏检测
    result = json.loads(json.dumps(data, default=str))

    # 1. 直接嵌套 dict 形态
    if row_identity in result and isinstance(result[row_identity], dict):
        result[row_identity][cell_identity] = value
        return result

    # 2. rows 结构
    rows = result.get("rows")

    if isinstance(rows, list):
        # 按下标或标识字段查找行
        try:
            idx = int(row_identity)
            if 0 <= idx < len(rows) and isinstance(rows[idx], dict):
                rows[idx][cell_identity] = value
                return result
        except (ValueError, TypeError):
            for row in rows:
                if isinstance(row, dict):
                    row_id = str(
                        row.get("_id")
                        or row.get("company_code")
                        or row.get("item_id")
                        or ""
                    )
                    if row_id == row_identity:
                        row[cell_identity] = value
                        return result
            # 未找到行，追加
            rows.append({"_id": row_identity, cell_identity: value})
            return result

    if isinstance(rows, dict):
        row_data = rows.setdefault(row_identity, {})
        if isinstance(row_data, dict):
            row_data[cell_identity] = value
        return result

    # 无 rows，创建嵌套 dict 结构
    result.setdefault(row_identity, {})[cell_identity] = value
    return result


def _group_by_sheet(
    targets: list[CanonicalFormulaTarget],
) -> dict[tuple[UUID, int, str], list[CanonicalFormulaTarget]]:
    """按 (project_id, year, sheet_key) 分组。"""
    groups: dict[tuple[UUID, int, str], list[CanonicalFormulaTarget]] = {}
    for t in targets:
        key = (t.project_id, t.year, t.locator["sheet_key"])
        groups.setdefault(key, []).append(t)
    return groups


# ---------------------------------------------------------------------------
# ConsolWorksheetMutationAdapter
# ---------------------------------------------------------------------------


class ConsolWorksheetMutationAdapter:
    """合并工作底稿领域变更适配器。

    使用整数 version CAS 而非 hash，与后端 PUT 端点逻辑一致。
    """

    domain: str = "consol_worksheet"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # prepare_many
    # ------------------------------------------------------------------

    async def prepare_many(
        self,
        targets: list[CanonicalFormulaTarget],
        values: dict[str, Any],
    ) -> list[FormulaMutation]:
        """读取当前值并准备变更计划。"""
        from app.models.consol_worksheet_data_models import ConsolWorksheetData

        mutations: list[FormulaMutation] = []
        rejected: list[str] = []

        valid_targets: list[CanonicalFormulaTarget] = []
        for t in targets:
            err = _validate_locator(t)
            if err:
                rejected.append(f"{t.addr_id}: {err}")
                continue
            valid_targets.append(t)

        if rejected:
            raise ValueError(f"拒绝的目标: {'; '.join(rejected)}")

        groups = _group_by_sheet(valid_targets)

        for (project_id, year, sheet_key), group_targets in groups.items():
            stmt = select(ConsolWorksheetData).where(
                and_(
                    ConsolWorksheetData.project_id == project_id,
                    ConsolWorksheetData.year == year,
                    ConsolWorksheetData.sheet_key == sheet_key,
                )
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()

            for t in group_targets:
                row_identity = t.locator["row_identity"]
                cell_identity = t.locator["cell_identity"]

                before_value: Any = None
                expected_version: str | None = None

                if row is not None:
                    before_value = _get_cell_value(row.data, row_identity, cell_identity)
                    # 使用整数版本号（与后端 PUT CAS 一致）
                    expected_version = str(int(row.version or 0))

                after_value = values.get(t.addr_id)
                if isinstance(after_value, Decimal):
                    after_value = str(after_value)

                mutations.append(
                    FormulaMutation(
                        target=t,
                        before_value=before_value,
                        after_value=after_value,
                        expected_version=expected_version,
                        source_formula_id=t.locator.get("source_formula_id"),
                    )
                )

        return mutations

    # ------------------------------------------------------------------
    # apply_many
    # ------------------------------------------------------------------

    async def apply_many(
        self,
        mutations: list[FormulaMutation],
    ) -> list[AppliedMutation]:
        """写入 after_value 到工作底稿 JSON，使用整数 version CAS。"""
        from app.models.consol_worksheet_data_models import ConsolWorksheetData

        applied: list[AppliedMutation] = []
        now = datetime.now(timezone.utc)

        # 按 sheet 分组，每组一次 DB 操作
        sheet_groups: dict[tuple[UUID, int, str], list[FormulaMutation]] = {}
        for m in mutations:
            key = (m.target.project_id, m.target.year, m.target.locator["sheet_key"])
            sheet_groups.setdefault(key, []).append(m)

        for (project_id, year, sheet_key), group_mutations in sheet_groups.items():
            stmt = select(ConsolWorksheetData).where(
                and_(
                    ConsolWorksheetData.project_id == project_id,
                    ConsolWorksheetData.year == year,
                    ConsolWorksheetData.sheet_key == sheet_key,
                )
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()

            if row is None:
                raise ValueError(
                    f"工作底稿不存在: project={project_id}, year={year}, sheet={sheet_key}"
                )

            current_version = int(row.version or 0)

            # CAS 检查：所有同 sheet 的 mutation 应该引用同一 expected_version
            for m in group_mutations:
                if m.expected_version is not None:
                    expected = int(m.expected_version)
                    if current_version != expected:
                        raise ValueError(
                            f"版本冲突 {m.target.addr_id}: "
                            f"expected={expected}, current={current_version}"
                        )

            # 批量应用所有单元格修改到同一 JSON 对象
            new_data = row.data
            for m in group_mutations:
                row_identity = m.target.locator["row_identity"]
                cell_identity = m.target.locator["cell_identity"]
                new_data = _set_cell_value(new_data, row_identity, cell_identity, m.after_value)

            # 条件 UPDATE（version CAS）
            new_version = current_version + 1
            update_result = await self._session.execute(
                update(ConsolWorksheetData)
                .where(
                    ConsolWorksheetData.id == row.id,
                    ConsolWorksheetData.version == current_version,
                )
                .values(data=new_data, version=new_version, updated_at=now)
            )
            if update_result.rowcount != 1:
                raise ValueError(
                    f"工作底稿并发冲突（条件 UPDATE 失败）: sheet={sheet_key}, "
                    f"version={current_version}"
                )

            # 刷新 ORM 对象
            row.data = new_data
            row.version = new_version
            row.updated_at = now
            await self._session.flush()

            now_iso = now.isoformat()
            for m in group_mutations:
                applied.append(
                    AppliedMutation(
                        target=m.target,
                        applied_version=str(new_version),
                        applied_at=now_iso,
                    )
                )

        return applied

    # ------------------------------------------------------------------
    # restore_many
    # ------------------------------------------------------------------

    async def restore_many(
        self,
        snapshots: list[FormulaMutation],
    ) -> list[RestoredMutation]:
        """恢复 before_value，使用版本号做冲突检测。"""
        from app.models.consol_worksheet_data_models import ConsolWorksheetData

        restored: list[RestoredMutation] = []
        now = datetime.now(timezone.utc)

        sheet_groups: dict[tuple[UUID, int, str], list[FormulaMutation]] = {}
        for m in snapshots:
            key = (m.target.project_id, m.target.year, m.target.locator["sheet_key"])
            sheet_groups.setdefault(key, []).append(m)

        for (project_id, year, sheet_key), group_mutations in sheet_groups.items():
            stmt = select(ConsolWorksheetData).where(
                and_(
                    ConsolWorksheetData.project_id == project_id,
                    ConsolWorksheetData.year == year,
                    ConsolWorksheetData.sheet_key == sheet_key,
                )
            )
            result = await self._session.execute(stmt)
            row = result.scalar_one_or_none()

            for m in group_mutations:
                row_identity = m.target.locator["row_identity"]
                cell_identity = m.target.locator["cell_identity"]

                if row is None:
                    restored.append(
                        RestoredMutation(
                            target=m.target,
                            restored_version="",
                            conflict=True,
                            conflict_detail=f"工作底稿不存在: sheet={sheet_key}",
                        )
                    )
                    continue

                # 冲突检测：当前值是否仍是 apply 写入的 after_value
                current_value = _get_cell_value(row.data, row_identity, cell_identity)
                if json.dumps(current_value, sort_keys=True, default=str) != json.dumps(
                    m.after_value, sort_keys=True, default=str
                ):
                    restored.append(
                        RestoredMutation(
                            target=m.target,
                            restored_version=str(int(row.version or 0)),
                            conflict=True,
                            conflict_detail=(
                                f"单元格已被修改: {m.target.addr_id}"
                            ),
                        )
                    )
                    continue

                # 恢复 before_value
                row.data = _set_cell_value(row.data, row_identity, cell_identity, m.before_value)
                restored.append(
                    RestoredMutation(
                        target=m.target,
                        restored_version=str(int(row.version or 0)),
                        conflict=False,
                    )
                )

            if row is not None:
                row.updated_at = now
                await self._session.flush()

        return restored

    # ------------------------------------------------------------------
    # read_versions
    # ------------------------------------------------------------------

    async def read_versions(
        self,
        targets: list[CanonicalFormulaTarget],
    ) -> dict[str, str]:
        """返回各目标当前版本号。"""
        from app.models.consol_worksheet_data_models import ConsolWorksheetData

        versions: dict[str, str] = {}
        groups = _group_by_sheet(targets)

        for (project_id, year, sheet_key), group_targets in groups.items():
            stmt = select(ConsolWorksheetData.version).where(
                and_(
                    ConsolWorksheetData.project_id == project_id,
                    ConsolWorksheetData.year == year,
                    ConsolWorksheetData.sheet_key == sheet_key,
                )
            )
            result = await self._session.execute(stmt)
            version_val = result.scalar_one_or_none()

            for t in group_targets:
                if version_val is not None:
                    versions[t.addr_id] = str(int(version_val))
                else:
                    versions[t.addr_id] = "0"

        return versions
