"""归档章节化 Registry — archive_section_registry

Refinement Round 1 — 需求 6：归档包采用"插件化章节"结构，各轮通过
register(order_prefix, filename, generator_func) 注册自己的章节生成器，
归档时按前缀排序拼装。

API:
  - register(order_prefix, filename, generator_func, description="")
  - list_all() -> list[SectionDef]
  - get_by_prefix(prefix) -> SectionDef | None
  - generate_all(project_id, db) -> list[tuple[str, bytes | Path | None]]

预留章节位（不注册，由各自轮次实现）：
# 02 - EQCR 备忘录（R5 需求 9）
# 03 - 质控抽查报告（R3 需求 4）
# 04 - 独立性声明（R1 需求 10，Task 23 注册）
# 10 - 底稿/（现有，由 wp_storage 直接打包）
# 20 - 报表/（现有）
# 30 - 附注/（现有）
# 40 - 附件/（现有）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Generator 函数签名：接收 project_id 和 db session，返回 bytes/Path/None
GeneratorFunc = Callable[[UUID, AsyncSession], Awaitable[bytes | Path | None]]


@dataclass
class SectionDef:
    """归档章节定义。"""

    order_prefix: str
    filename: str
    generator_func: GeneratorFunc
    description: str = ""


# 模块级 registry 存储
_registry: list[SectionDef] = []


def register(
    order_prefix: str,
    filename: str,
    generator_func: GeneratorFunc,
    description: str = "",
) -> None:
    """注册一个归档章节生成器。

    如果同 order_prefix 已存在，则覆盖（后注册的优先）。
    注册后自动按 order_prefix 排序。
    """
    global _registry
    # 覆盖同 prefix 的已有注册
    _registry = [s for s in _registry if s.order_prefix != order_prefix]
    _registry.append(
        SectionDef(
            order_prefix=order_prefix,
            filename=filename,
            generator_func=generator_func,
            description=description,
        )
    )
    # 按 order_prefix 排序
    _registry.sort(key=lambda s: s.order_prefix)


def list_all() -> list[SectionDef]:
    """返回按 order_prefix 排序的所有已注册章节。"""
    return list(_registry)


def get_by_prefix(prefix: str) -> SectionDef | None:
    """按 order_prefix 查找章节定义，未找到返回 None。"""
    for section in _registry:
        if section.order_prefix == prefix:
            return section
    return None


async def generate_all(
    project_id: UUID, db: AsyncSession
) -> list[tuple[str, bytes | Path | None]]:
    """按顺序调用每个已注册的 generator_func，返回 (filename, content) 列表。

    单个 generator 失败时记录日志并返回 None 作为 content（不中断整体流程）。
    """
    results: list[tuple[str, bytes | Path | None]] = []
    for section in _registry:
        try:
            content = await section.generator_func(project_id, db)
            results.append((section.filename, content))
        except Exception as exc:
            logger.error(
                "[ARCHIVE_SECTION_REGISTRY] generator failed: prefix=%s filename=%s error=%s",
                section.order_prefix,
                section.filename,
                exc,
            )
            results.append((section.filename, None))
    return results


def clear() -> None:
    """清空 registry（仅用于测试）。"""
    global _registry
    _registry = []


# ---------------------------------------------------------------------------
# R1 章节注册
# ---------------------------------------------------------------------------


async def generate_project_cover_pdf(
    project_id: UUID, db: AsyncSession
) -> bytes | Path | None:
    """生成项目封面 PDF（R1 需求 6）。

    查询 Project + AuditReport 数据，填充 HTML 模板，通过 LibreOffice 转 PDF。
    """
    from app.services.archive_pdf_generators import (
        generate_project_cover_pdf as _impl,
    )

    return await _impl(project_id, db)


async def generate_signature_ledger_pdf(
    project_id: UUID, db: AsyncSession
) -> bytes | Path | None:
    """生成签字流水 PDF（R1 需求 6）。

    列出 N 级签字流水（预留 EQCR 扩展），通过 LibreOffice 转 PDF。
    """
    from app.services.archive_pdf_generators import (
        generate_signature_ledger_pdf as _impl,
    )

    return await _impl(project_id, db)


async def generate_audit_log_export(
    project_id: UUID, db: AsyncSession
) -> bytes | Path | None:
    """导出审计日志 JSONL（stub，Task 21 实现真实逻辑）。"""
    return None


async def generate_independence_declarations_pdf(
    project_id: UUID, db: AsyncSession
) -> bytes | Path | None:
    """生成独立性声明 PDF（R1 需求 10，Task 23）。

    按项目成员拆分独立 PDF，汇总为单文件。
    当前为 stub 实现，后续可接入 pdf_export_engine。
    """
    try:
        from app.services.independence_service import IndependenceService

        declarations = await IndependenceService.list_declarations(db, project_id)
        if not declarations:
            return None

        # Stub: 返回简单文本标识，后续替换为真实 PDF 生成
        content_lines = [f"独立性声明汇总 - 项目 {project_id}\n"]
        for decl in declarations:
            content_lines.append(
                f"  声明人: {decl.declarant_id} | 年度: {decl.declaration_year} | 状态: {decl.status}\n"
            )
        return "".join(content_lines).encode("utf-8")
    except Exception as exc:
        logger.error("[ARCHIVE] independence PDF generation failed: %s", exc)
        return None


def register_r1_sections() -> None:
    """注册 Round 1 本轮的归档章节。"""
    register(
        "00",
        "00-项目封面.pdf",
        generate_project_cover_pdf,
        "项目封面（R1）",
    )
    register(
        "01",
        "01-签字流水.pdf",
        generate_signature_ledger_pdf,
        "签字流水（R1）",
    )
    register(
        "04",
        "04-独立性声明.pdf",
        generate_independence_declarations_pdf,
        "独立性声明（R1 需求 10）",
    )
    register(
        "99",
        "99-审计日志.jsonl",
        generate_audit_log_export,
        "审计日志导出（R1）",
    )


# 模块加载时自动注册 R1 章节
register_r1_sections()


# ---------------------------------------------------------------------------
# R5 章节注册：EQCR 备忘录
# ---------------------------------------------------------------------------


async def _eqcr_memo_pdf_generator(
    project_id: UUID, db: AsyncSession
) -> bytes | Path | None:
    """归档引擎调用：返回 EQCR 备忘录 PDF 字节。"""
    from app.services.eqcr_memo_service import eqcr_memo_pdf_generator
    from app.models.core import Project
    from sqlalchemy import select as _select

    proj = (await db.execute(
        _select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if proj is None:
        return None
    wizard_state = proj.wizard_state or {}
    return eqcr_memo_pdf_generator(project_id, wizard_state)


register(
    "02",
    "02-EQCR备忘录.pdf",
    _eqcr_memo_pdf_generator,
    "EQCR 备忘录（R5 需求 9）",
)
