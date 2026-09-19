"""母公司口径定位（单一真源）。

附注取数与报表「母公司个别数」列**共用**本模块，避免两个交付件的母公司数打架。

母公司身份完全由 ``projects`` 表既有三元组 ``(company_code, audit_year,
report_scope)`` 推导 —— **不新增 DB 列、不新增表、无迁移**。

判据：唯一索引 ``uq_project_company_year_scope (company_code, audit_year,
report_scope)``（``WHERE is_deleted = false AND company_code IS NOT NULL
AND audit_year IS NOT NULL``）保证同企业代码同年度只能靠 ``report_scope``
区分，故「合并项目 + 母公司单体」是唯一可能的同代码对。

口径与展示层 ``app.services.project_display.get_project_display_name(
project: dict, all_projects: list[dict]) -> str`` 一致：consolidated 加
「（合并）」；standalone 且存在同代码同年度 consolidated 兄弟 → 加「（母公司）」。

「上级公司」不是母公司单体
--------------------------
``projects`` 有三个企业代码：``company_code``（本企业）/ ``parent_company_code``
（**上级公司，代码不同**）/ ``ultimate_company_code``（最终）。本模块定位的是
**同代码 standalone 兄弟**，与 ``parent_company_code`` 指向的上级公司是两件事。
区分这两者正是本模块的核心价值 —— 报表侧 ``report_excel_exporter.
_load_parent_row_index()`` 原实现把两者混为一谈（按上级公司代码定位，且缺
``report_scope`` 与 ``audit_year`` 过滤）。

需求 8.6 的决定（登记）
----------------------
**不扩展** ``note_section_catalog.normalize_report_scope`` 的取值域。该函数只认
``standalone`` / ``consolidated``，其余取值静默回退 ``standalone``。母公司口径改由
「**合并项目 + 跨项目取数**」表达：附注仍挂在合并项目下，母公司章的数据经本模块
定位到同代码 standalone 兄弟项目后跨项目取数。因此 ``parent_only`` **不进附注层**
（它全后端仅 1 处使用，在 ``wp_render_config`` 底稿层做 redirect），附注层取数路径
不出现该取值，也就不存在「``parent_only`` 被静默回退成 ``standalone``」的歧义。

实现约定（勿"优化"掉）
--------------------
1. 两个 resolver 的三个查询条件（``company_code`` / ``audit_year`` /
   ``report_scope``）**逐字显式写在各自的 where 里**，字面量不抽常量、不做动态
   拼装 —— 源码级守卫按此形态断言「三条件齐备」，去掉任一条必须打红。
2. **本模块不做 fail-open**：DB 异常原样抛出，不用 ``except Exception`` 吞成
   ``None``。否则「函数名写错 / 接线错」会被伪装成「本项目无母公司单体」。是否
   fail-open 由调用方决定（报表侧 ``_load_parent_row_index`` 自己保留 fail-open
   并留空该列）。
3. 返回 ORM ``Project`` 对象而非 id，便于调用方直接读 ``name`` / ``company_code``
   做溯源展示。
4. 两个 resolver 都不需要排除入参自身：``report_scope`` 是单值列，入参与目标口径
   相反，故 scope 条件已严格排除自身。
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.services.note_section_catalog import normalize_report_scope

logger = logging.getLogger(__name__)

__all__ = [
    "resolve_parent_standalone_project",
    "resolve_consolidated_sibling",
    "is_parent_company_project",
]


def _locator_ready(project: Project, *, direction: str) -> bool:
    """三元组是否齐备到可定位（``company_code`` 与 ``audit_year`` 均非空）。

    唯一索引只覆盖 ``company_code IS NOT NULL AND audit_year IS NOT NULL``，
    任一为空则唯一性无保证、定位也无意义 → 记 INFO 后返回 None（合法状态）。
    """
    if project.company_code is None or project.audit_year is None:
        logger.info(
            "母公司口径定位跳过（%s）：项目 %s 缺少定位字段 "
            "company_code=%r audit_year=%r",
            direction,
            project.id,
            project.company_code,
            project.audit_year,
        )
        return False
    return True


def _pick_unique(
    rows: list[Project],
    *,
    source: Project,
    target_scope: str,
) -> Project | None:
    """从查询结果中取唯一兄弟项目。

    唯一索引理论上保证 ``len(rows) <= 1``。出现多条说明索引被误删，此时记 ERROR
    并断言 —— 宁可打红也不要静默取错（``.first()`` 可能把另一条项目的数据写进
    交付件）。
    """
    if not rows:
        return None
    if len(rows) > 1:
        logger.error(
            "母公司口径定位到多条 %s 项目（唯一索引 uq_project_company_year_scope "
            "理论上不可能）：company_code=%r audit_year=%r 命中 %d 条 ids=%s，"
            "来源项目 %s。请检查该唯一索引是否被误删。",
            target_scope,
            source.company_code,
            source.audit_year,
            len(rows),
            [str(r.id) for r in rows],
            source.id,
        )
        raise AssertionError(
            f"expected at most one {target_scope} project for "
            f"company_code={source.company_code!r} audit_year={source.audit_year!r}, "
            f"got {len(rows)}"
        )
    return rows[0]


async def resolve_parent_standalone_project(
    db: AsyncSession, consol_project: Project
) -> Project | None:
    """定位母公司单体项目（与合并项目同企业代码、同年度、口径为 standalone）。

    仅当入参为 ``consolidated`` 项目时成立 —— 母公司口径只在合并项目下有意义，
    非合并项目返回 ``None``。

    找不到兄弟项目返回 ``None`` 并记 INFO：合并项目尚未建母公司单体是**合法状态**，
    调用方应留空而非报错。

    Args:
        db: 数据库会话。
        consol_project: 合并项目（``report_scope == "consolidated"``）。

    Returns:
        母公司单体项目的 ORM 对象；入参非合并 / 定位字段缺失 / 无兄弟时为 ``None``。

    Raises:
        AssertionError: 同代码同年度命中多条 standalone 项目（唯一索引被误删）。
    """
    if normalize_report_scope(consol_project.report_scope) != "consolidated":
        logger.info(
            "母公司口径定位跳过：项目 %s 的 report_scope=%r 不是 consolidated，"
            "母公司口径只在合并项目下成立",
            consol_project.id,
            consol_project.report_scope,
        )
        return None

    if not _locator_ready(consol_project, direction="合并→母公司单体"):
        return None

    result = await db.execute(
        sa.select(Project).where(
            Project.company_code == consol_project.company_code,
            Project.audit_year == consol_project.audit_year,
            Project.report_scope == "standalone",
            Project.is_deleted == sa.false(),
        )
    )
    parent_project = _pick_unique(
        list(result.scalars().all()),
        source=consol_project,
        target_scope="standalone",
    )
    if parent_project is None:
        logger.info(
            "未找到母公司单体项目：company_code=%r audit_year=%r "
            "（合并项目 %s 尚未建母公司单体，属合法状态，调用方应留空）",
            consol_project.company_code,
            consol_project.audit_year,
            consol_project.id,
        )
    return parent_project


async def resolve_consolidated_sibling(
    db: AsyncSession, standalone_project: Project
) -> Project | None:
    """反向：某 standalone 项目是否有同代码同年度的合并兄弟。

    用于判定该 standalone 项目是否为母公司（口径与
    ``project_display.get_project_display_name`` 的「（母公司）」后缀一致）。

    Args:
        db: 数据库会话。
        standalone_project: 单体项目（``report_scope == "standalone"``）。

    Returns:
        合并兄弟项目的 ORM 对象；入参非单体 / 定位字段缺失 / 无兄弟时为 ``None``。

    Raises:
        AssertionError: 同代码同年度命中多条 consolidated 项目（唯一索引被误删）。
    """
    if normalize_report_scope(standalone_project.report_scope) != "standalone":
        logger.info(
            "合并兄弟定位跳过：项目 %s 的 report_scope=%r 不是 standalone",
            standalone_project.id,
            standalone_project.report_scope,
        )
        return None

    if not _locator_ready(standalone_project, direction="母公司单体→合并"):
        return None

    result = await db.execute(
        sa.select(Project).where(
            Project.company_code == standalone_project.company_code,
            Project.audit_year == standalone_project.audit_year,
            Project.report_scope == "consolidated",
            Project.is_deleted == sa.false(),
        )
    )
    sibling = _pick_unique(
        list(result.scalars().all()),
        source=standalone_project,
        target_scope="consolidated",
    )
    if sibling is None:
        logger.info(
            "未找到合并兄弟项目：company_code=%r audit_year=%r "
            "（单体项目 %s 不构成母公司口径）",
            standalone_project.company_code,
            standalone_project.audit_year,
            standalone_project.id,
        )
    return sibling


async def is_parent_company_project(db: AsyncSession, project: Project) -> bool:
    """该项目是否为母公司（standalone 且存在同代码同年度 consolidated 兄弟）。

    口径与 ``project_display.get_project_display_name(project, all_projects)``
    一致：该函数为 standalone 项目追加「（母公司）」后缀的条件，就是本函数返回
    ``True`` 的条件。两者必须同进同退（守卫交叉锁死）。

    Args:
        db: 数据库会话。
        project: 待判定项目。

    Returns:
        ``True`` 表示该项目是母公司单体项目。
    """
    return await resolve_consolidated_sibling(db, project) is not None
