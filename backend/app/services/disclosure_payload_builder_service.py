"""后端披露表 payload builder 服务。

从 checklist_responses 读取底稿数据，构建 sub_table_data，
不依赖前端 buildXSyncPayload。

spec: backend-disclosure-payload-builder Phase 1
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── 数据类 ────────────────────────────────────────────────────────────────────


@dataclass
class PayloadBuildResult:
    """后端 builder 的产出。"""
    wp_code: str
    section_id: str                                    # 目标附注章节号
    sub_table_data: dict[str, list[dict]]              # {table_key: [row_dicts]}
    sub_table_columns: dict[str, list[dict]] | None    # 列定义
    sheet_name: str                                    # 披露表 sheet 名
    current_standard: str                              # "soe_standalone" / "listed_standalone"


# ── 抽象基类 ──────────────────────────────────────────────────────────────────


class DisclosurePayloadBuilder(ABC):
    """披露表 payload builder 抽象基类。

    每个科目一个子类，实现 build() 从 checklist_responses 构建 sub_table_data。
    """
    wp_code: str = ""

    @abstractmethod
    async def build(
        self, db: AsyncSession, project_id: UUID, year: int,
    ) -> PayloadBuildResult | None:
        """构建 sub_table_data。None = 底稿无数据。"""
        ...


# ── checklist_responses 数据读取 ──────────────────────────────────────────────


async def load_disclosure_entries(
    db: AsyncSession,
    project_id: UUID,
    wp_code: str,
) -> dict[str, Any]:
    """读取底稿 wp_code 的全部 checklist_responses，按 item_id 索引。

    返回 {item_id: remark_value}（remark 列是大部分底稿的数据列）。
    空 dict = 底稿不存在或无数据。
    """
    # wp_index → working_paper → checklist_responses
    result = await db.execute(sa.text("""
        SELECT cr.item_id, cr.remark, cr.conclusion
        FROM checklist_responses cr
        JOIN working_paper wp ON wp.id = cr.wp_id
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE wi.project_id = :pid AND wi.wp_code = :code
    """), {"pid": str(project_id), "code": wp_code})

    entries: dict[str, Any] = {}
    for row in result.fetchall():
        item_id, remark, conclusion = row
        # 优先 remark（大部分底稿），conclusion 用于 N3 等特殊底稿
        value = remark if remark is not None else conclusion
        if value is not None:
            entries[item_id] = value
    return entries


async def load_project_template_type(
    db: AsyncSession, project_id: UUID,
) -> str:
    """读取项目的附注模板类型（soe/listed）。"""
    result = await db.execute(sa.text(
        "SELECT template_type FROM projects WHERE id = :pid"
    ), {"pid": str(project_id)})
    row = result.fetchone()
    return (row[0] or "soe") if row else "soe"


async def load_project_standard(
    db: AsyncSession, project_id: UUID,
) -> str:
    """读取项目的 current_standard（soe_standalone / listed_standalone 等）。"""
    tt = await load_project_template_type(db, project_id)
    return f"{tt}_standalone"


# ── 注册表 ────────────────────────────────────────────────────────────────────


_BUILDER_REGISTRY: dict[str, type[DisclosurePayloadBuilder]] = {}


def register_builder(cls: type[DisclosurePayloadBuilder]) -> type[DisclosurePayloadBuilder]:
    """装饰器：注册 builder 类。"""
    code = cls.wp_code
    if not code:
        raise ValueError(f"builder {cls.__name__} 缺少 wp_code")
    _BUILDER_REGISTRY[code] = cls
    return cls


def get_builder(wp_code: str) -> DisclosurePayloadBuilder | None:
    """按 wp_code 获取 builder 实例。None = 该科目尚未实现 builder。"""
    _ensure_builders_loaded()
    cls = _BUILDER_REGISTRY.get(wp_code)
    return cls() if cls else None


def registered_wp_codes() -> list[str]:
    """已注册的全部 wp_code。"""
    _ensure_builders_loaded()
    return sorted(_BUILDER_REGISTRY.keys())


# ── 入口 ──────────────────────────────────────────────────────────────────────


_builders_loaded = False


def _ensure_builders_loaded() -> None:
    """懒加载 disclosure_builders 包，触发 @register_builder 装饰器。"""
    global _builders_loaded  # noqa: PLW0603
    if _builders_loaded:
        return
    _builders_loaded = True
    try:
        import app.services.disclosure_builders  # noqa: F401
    except Exception as exc:
        logger.warning("disclosure_builders import failed: %s", exc)


async def build_for_wp_code(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str,
) -> PayloadBuildResult | None:
    """按 wp_code 调 builder。None = 未注册或底稿无数据。"""
    _ensure_builders_loaded()
    builder = get_builder(wp_code)
    if builder is None:
        return None
    try:
        return await builder.build(db, project_id, year)
    except Exception as exc:
        logger.warning(
            "disclosure_payload_builder: %s failed project=%s: %s",
            wp_code, project_id, exc,
        )
        return None


async def _source_wp_id(db: AsyncSession, project_id: UUID, wp_code: str) -> UUID | None:
    """builder 读的那张底稿（与 `load_disclosure_entries` 同一条关联；(项目, wp_code) 至多一张）。"""
    row = (await db.execute(sa.text("""
        SELECT wp.id FROM working_paper wp
        JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE wi.project_id = :pid AND wi.wp_code = :code
        LIMIT 1
    """), {"pid": str(project_id), "code": wp_code})).first()
    return None if row is None else UUID(str(row[0]))


async def build_and_sync(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_code: str,
    *,
    triggered_by: UUID | None = None,
) -> dict[str, Any]:
    """builder → sync_from_workpaper 一步到位。

    返回 sync 结果 dict 或 {"skipped": True, "reason": ...}。

    🔴 不用占位身份（spec writeback-followup-issue-closure R7.2）：原先无触发人时写
    `User(id=UUID(int=0))`、底稿写 `UUID(int=0)` ⇒ `disclosure_notes.updated_by` 外键在下一次
    查询的 autoflush 上炸，整次附注刷新失败（底稿保存的事件从来不带 user_id，所以每次都炸）。
    现在无触发人 = 系统重算，`updated_by` 记 NULL；来源底稿取 builder 读的那张（`last_sync_wp_id`）。

    全部读写在一个 SAVEPOINT 里（释放保存点时 flush，约束错误就地暴露）：builder 失败只回滚它
    自己，调用方随后的附注刷新仍在健康的事务上（PG 上吞掉异常而不回滚到保存点，整个事务停在 aborted）。
    """
    from app.models.core import User
    from app.services.wp_disclosure_sync_service import sync_from_workpaper

    nested = await db.begin_nested()
    try:
        result = await build_for_wp_code(db, project_id, year, wp_code)
        source_wp_id = None if result is None else await _source_wp_id(db, project_id, wp_code)
        if result is None or source_wp_id is None:
            # 什么都没写；builder 内部吞掉的查询失败（PG 上已 aborted）也就此回滚到保存点
            await nested.rollback()
            reason = "无 builder 或底稿无数据" if result is None else "在本项目没有底稿"
            return {"skipped": True, "reason": f"{wp_code} {reason}"}
        sync_result = await sync_from_workpaper(
            db, project_id,
            wp_id=source_wp_id,
            sheet_name=result.sheet_name,
            section_id=result.section_id,
            sub_table_data=result.sub_table_data,
            current_standard=result.current_standard,
            # 只读 `.id`；事件触发没有 HTTP 请求上下文，无触发人即系统重算
            user=User(id=triggered_by),
            year=year,
            sub_table_columns=result.sub_table_columns,
            propagation_origin="system_recompute",
            commit=False,
        )
        await nested.commit()
    except Exception:
        # flush 失败后保存点已失活（is_active=False）但仍须显式 rollback，会话才回到外层事务
        await nested.rollback()
        raise
    return sync_result
