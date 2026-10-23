"""新建底稿的文件落地（按编码生成 / 准则转换生成共用）。

spec: .kiro/specs/_archive/71-formula-fetch-and-wp-generation-defect-closure/（R5）

与链路编排（``chain_orchestrator``）同一解析：``init_workpaper_from_template`` 按底稿模板目录索引找主文件
（``find_template_file_any``，支持「E1-1至E1-11 …」这类区间命名与 xlsm / docx），多页底稿合并其余文件的
sheet，并按项目场景裁剪（normal 不带 IPO / 上市 / 重组 / 舞弊应对文件）。文件落在
``wp_storage/{project_id}/{wp_id}.*`` —— 与在线编辑首开初始化、链路编排是同一位置。

🔴 此前按编码生成与准则转换生成各自按 ``gt_template_library.json`` 精确匹配：模板集 1025 个编码里
722 个不在该库（E1 / D2 等多页底稿全在其中），统统落成只有三行字的空白册，且名称叫「底稿{code}」。
找不到模板时本模块仍建空白册（同一存储位置），由调用方单列回报，不冒充模板。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import wp_template_init_service as _init

logger = logging.getLogger(__name__)

#: Excel 页签名不允许的字符（openpyxl 遇到会抛错）
_SHEET_TITLE_BAD = re.compile(r"[\[\]:*?/\\]")

#: 找不到模板时空白册里的说明文字与所在行
BLANK_NOTICE = "未找到该编码的底稿模板，这是一份空白底稿"
BLANK_NOTICE_ROW = 8


@dataclass(frozen=True)
class GeneratedWorkpaperFile:
    """``path``：底稿文件；``from_template``：是否来自真实模板（False = 找不到模板建的空白册）。"""

    path: Path
    from_template: bool


async def load_generation_scenario(db: AsyncSession, project_id: UUID) -> tuple[str, bool]:
    """项目场景与是否有外币业务（与链路编排同口径；取不到按 normal / 无外币）。"""
    from app.models.core import Project

    row = (await db.execute(
        sa.select(Project.scenario, Project.has_foreign_currency).where(Project.id == project_id)
    )).first()
    if row is None:
        return "normal", False
    return (row[0] or "normal"), bool(row[1])


def materialize_workpaper_file(
    project_id: UUID,
    wp_id: UUID,
    wp_code: str,
    wp_name: str,
    *,
    scenario: str = "normal",
    has_foreign_currency: bool = False,
) -> GeneratedWorkpaperFile:
    """按模板生成底稿文件；找不到模板时在同一存储位置建空白册并标 ``from_template=False``。"""
    path = _init.init_workpaper_from_template(
        project_id=project_id,
        wp_id=wp_id,
        wp_code=wp_code,
        scenario=scenario,
        has_foreign_currency=has_foreign_currency,
    )
    if path is not None:
        return GeneratedWorkpaperFile(path=Path(path), from_template=True)

    import openpyxl

    target = _init.get_workpaper_storage_path(project_id, wp_id)
    wb = openpyxl.Workbook()
    try:
        ws = wb.active
        ws.title = (_SHEET_TITLE_BAD.sub("_", wp_code or "") or "Sheet1")[:31]
        ws["A1"] = f"底稿编号: {wp_code}"
        ws["A2"] = f"底稿名称: {wp_name}"
        # 第 8 行：表头填充（wp_header_service 标准布局占第 1~5 行）不会覆盖它
        ws[f"A{BLANK_NOTICE_ROW}"] = BLANK_NOTICE
        wb.save(str(target))
    finally:
        wb.close()
    logger.warning("生成底稿：未找到模板，已建空白底稿 wp_code=%s wp_id=%s", wp_code, wp_id)
    return GeneratedWorkpaperFile(path=target, from_template=False)


def discard_generated_file(generated: GeneratedWorkpaperFile | None) -> None:
    """生成流程在落文件之后失败（底稿行已回滚）时删掉孤儿文件；删不掉只记日志。"""
    if generated is None:
        return
    try:
        generated.path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("生成底稿：清理孤儿文件失败 %s: %s", generated.path, exc)
