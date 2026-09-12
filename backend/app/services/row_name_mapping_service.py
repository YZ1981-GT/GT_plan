"""行名对齐映射读写服务（formula-row-name-alignment-confirmation Task 7 / 8）。

- 读：`load_active_mappings` → `{row_key: SavedMapping}`，供 `classify` / `resolve_amounts`
- 写：`batch_confirm` → **单事务**全回滚、幂等重试、版本冲突检测；
  覆盖历史写新版本行并 supersede 旧行（Requirement 3.5 / 3.6）

版本模型：每次确认写新行（mapping_version+1，is_active=true），旧行 is_active=false
且被新行 superseded_from 指向。stale 由 `dataset_fingerprint` 与目标身份集判定。

spec: .kiro/specs/formula-row-name-alignment-confirmation/ Requirement 3.2~3.6 / 1.4
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_row_name_mapping_models import (
    WorkpaperRowNameMapping,
    WorkpaperRowNameMappingTarget,
)
from app.services.four_table.row_name_alignment import (
    SavedMapping,
    TargetIdentity,
)

logger = logging.getLogger(__name__)


class MappingConflictError(Exception):
    """乐观锁版本冲突（base_mapping_version 不匹配当前 active 版本）。"""

    def __init__(self, row_key: str, expected: int | None, actual: int | None):
        self.row_key = row_key
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"version conflict on row_key={row_key}: "
            f"base={expected} != current active={actual}"
        )


@dataclass
class MappingScope:
    """映射作用域键。"""

    project_id: uuid.UUID
    year: int
    wp_code: str
    sheet_code: str


@dataclass
class RowConfirmInput:
    """单行确认输入。"""

    row_key: str
    targets: list[TargetIdentity]
    base_mapping_version: int | None = None  # None = 首次确认（无既有 active 版本）


def compute_dataset_fingerprint(
    dataset_id: str | None, targets: list[TargetIdentity]
) -> str:
    """由 dataset_id + 目标身份集 + source schema digest 组成 stale 指纹（Requirement 1.4）。

    目标身份集变化或 dataset 变化 → 指纹变化 → 判 stale。
    """
    parts = [str(dataset_id or "")]
    for t in sorted(targets, key=lambda x: x.identity_tuple()):
        parts.append("|".join(str(x) for x in t.identity_tuple()))
    raw = "\x1e".join(parts)
    return "fp1-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _target_from_row(row: WorkpaperRowNameMappingTarget) -> TargetIdentity:
    return TargetIdentity(
        source_kind=row.source_kind,
        account_code=row.account_code,
        aux_type=row.aux_type,
        aux_name=row.aux_name,
        dimension_key=row.dimension_key,
        dataset_id=str(row.dataset_id) if row.dataset_id else None,
    )


class RowNameMappingService:
    """行名对齐映射读写服务。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def load_active_mappings(
        self, scope: MappingScope
    ) -> dict[str, SavedMapping]:
        """读该作用域下**全部 active 行**的确认映射 → `{row_key: SavedMapping}`。"""
        stmt = (
            sa.select(WorkpaperRowNameMapping)
            .where(
                WorkpaperRowNameMapping.project_id == scope.project_id,
                WorkpaperRowNameMapping.year == scope.year,
                WorkpaperRowNameMapping.wp_code == scope.wp_code,
                WorkpaperRowNameMapping.sheet_code == scope.sheet_code,
                WorkpaperRowNameMapping.is_active.is_(True),
            )
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        if not rows:
            return {}

        # 拉目标明细（可查询身份来源）
        ids = [r.id for r in rows]
        tgt_stmt = sa.select(WorkpaperRowNameMappingTarget).where(
            WorkpaperRowNameMappingTarget.mapping_id.in_(ids)
        )
        tgt_rows = (await self.db.execute(tgt_stmt)).scalars().all()
        by_mapping: dict[uuid.UUID, list[TargetIdentity]] = {}
        for tr in tgt_rows:
            by_mapping.setdefault(tr.mapping_id, []).append(_target_from_row(tr))

        out: dict[str, SavedMapping] = {}
        for r in rows:
            out[r.row_key] = SavedMapping(
                row_key=r.row_key,
                targets=tuple(by_mapping.get(r.id, [])),
                mapping_version=r.mapping_version,
                confirmed_by=str(r.confirmed_by) if r.confirmed_by else None,
                confirmed_at=r.confirmed_at.isoformat() if r.confirmed_at else None,
            )
        return out

    async def get_by_idempotency_key(
        self, project_id: uuid.UUID, idempotency_key: str
    ) -> list[WorkpaperRowNameMapping]:
        """幂等：若该 key 已提交过，返回其写入的行（重复请求返回第一次结果）。"""
        stmt = sa.select(WorkpaperRowNameMapping).where(
            WorkpaperRowNameMapping.project_id == project_id,
            WorkpaperRowNameMapping.idempotency_key == idempotency_key,
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def batch_confirm(
        self,
        scope: MappingScope,
        rows: list[RowConfirmInput],
        *,
        confirmed_by: uuid.UUID | None,
        idempotency_key: str,
        dataset_id: str | None = None,
    ) -> dict[str, SavedMapping]:
        """批量确认映射：**单事务**全回滚、幂等、版本冲突检测（Requirement 3.6）。

        任一行版本冲突或校验失败 ⇒ 抛异常 ⇒ 全部映射与留痕不写入。
        重复 `idempotency_key` ⇒ 返回第一次提交结果，不重复写。
        覆盖已有 active 版本 ⇒ 写新版本行（version+1，superseded_from 指向旧行），
        旧行置 is_active=false（留痕，Requirement 3.5）。

        本方法**不自行 commit**：由调用方（路由层）在 `async with db.begin()` 或
        请求级事务中提交，保证与其它写入原子。冲突/失败抛异常触发上层回滚。
        """
        # ① 幂等短路
        if idempotency_key:
            existing = await self.get_by_idempotency_key(
                scope.project_id, idempotency_key
            )
            if existing:
                logger.info(
                    "row_name_mapping: 幂等命中 key=%s，返回既有 %d 行",
                    idempotency_key,
                    len(existing),
                )
                return await self.load_active_mappings(scope)

        # ② 读当前 active 版本（用于版本冲突检测 + supersede）
        current = await self._load_active_rows(scope)
        current_by_key = {r.row_key: r for r in current}

        # ③ 逐行校验版本冲突（先全部校验，再全部写 —— 保证全回滚语义）
        for inp in rows:
            cur = current_by_key.get(inp.row_key)
            cur_version = cur.mapping_version if cur else None
            if inp.base_mapping_version != cur_version:
                # None==None（首次）通过；其余不等即冲突
                raise MappingConflictError(
                    inp.row_key, inp.base_mapping_version, cur_version
                )
            if not inp.targets:
                raise ValueError(
                    f"row_key={inp.row_key} 无目标身份，拒绝写入空映射"
                )

        # ④ 全部校验通过 → 逐行写新版本 + supersede 旧行
        for inp in rows:
            cur = current_by_key.get(inp.row_key)
            new_version = (cur.mapping_version + 1) if cur else 1
            if cur is not None:
                cur.is_active = False  # 旧行退役（留痕）
            new_row = WorkpaperRowNameMapping(
                project_id=scope.project_id,
                year=scope.year,
                wp_code=scope.wp_code,
                sheet_code=scope.sheet_code,
                row_key=inp.row_key,
                targets=[self._target_to_dict(t) for t in inp.targets],
                match_state="user_confirmed",
                dataset_fingerprint=compute_dataset_fingerprint(dataset_id, inp.targets),
                mapping_version=new_version,
                base_mapping_version=inp.base_mapping_version,
                idempotency_key=idempotency_key or None,
                is_active=True,
                superseded_from=cur.id if cur is not None else None,
                confirmed_by=confirmed_by,
            )
            self.db.add(new_row)
            await self.db.flush()  # 拿 new_row.id 供明细外键
            for t in inp.targets:
                self.db.add(
                    WorkpaperRowNameMappingTarget(
                        mapping_id=new_row.id,
                        source_kind=t.source_kind,
                        account_code=t.account_code,
                        aux_type=t.aux_type,
                        aux_name=t.aux_name,
                        dimension_key=t.dimension_key,
                        dataset_id=uuid.UUID(t.dataset_id)
                        if t.dataset_id and _is_uuid(t.dataset_id)
                        else None,
                    )
                )

        await self.db.flush()
        return await self.load_active_mappings(scope)

    async def _load_active_rows(
        self, scope: MappingScope
    ) -> list[WorkpaperRowNameMapping]:
        stmt = sa.select(WorkpaperRowNameMapping).where(
            WorkpaperRowNameMapping.project_id == scope.project_id,
            WorkpaperRowNameMapping.year == scope.year,
            WorkpaperRowNameMapping.wp_code == scope.wp_code,
            WorkpaperRowNameMapping.sheet_code == scope.sheet_code,
            WorkpaperRowNameMapping.is_active.is_(True),
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _target_to_dict(t: TargetIdentity) -> dict:
        return {
            "source_kind": t.source_kind,
            "account_code": t.account_code,
            "aux_type": t.aux_type,
            "aux_name": t.aux_name,
            "dimension_key": t.dimension_key,
            "dataset_id": t.dataset_id,
        }


def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


__all__ = [
    "MappingConflictError",
    "MappingScope",
    "RowConfirmInput",
    "RowNameMappingService",
    "compute_dataset_fingerprint",
]
