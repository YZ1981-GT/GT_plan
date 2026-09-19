# -*- coding: utf-8 -*-
"""B60 章节数据拉取 API

POST /api/b60/chapters/{chapter_id}/pull — 从关联底稿提取数据填入章节
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/b60", tags=["b60-data-pull"])

# ---------------------------------------------------------------------------
# 静态章节定义加载（复用 b60_chapter_definitions.json）
# ---------------------------------------------------------------------------

_CHAPTER_DEFINITIONS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "b60_chapter_definitions.json"
)

_chapter_definitions_cache: list[dict] | None = None


def _load_chapter_definitions() -> list[dict]:
    """加载章节定义 JSON，模块级缓存。"""
    global _chapter_definitions_cache
    if _chapter_definitions_cache is not None:
        return _chapter_definitions_cache
    try:
        with open(_CHAPTER_DEFINITIONS_PATH, "r", encoding="utf-8") as f:
            _chapter_definitions_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("b60_chapter_definitions.json 加载失败: %s", e)
        _chapter_definitions_cache = []
    return _chapter_definitions_cache


def _find_chapter(chapter_id: str) -> dict | None:
    """根据 chapter_id 查找章节定义。"""
    for ch in _load_chapter_definitions():
        if ch.get("chapter_id") == chapter_id:
            return ch
    return None


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class PullRequest(BaseModel):
    """数据拉取请求体。"""
    project_id: UUID
    wp_id: UUID


class PullResponse(BaseModel):
    """数据拉取响应。"""
    content: str = ""
    source_label: str = ""


class B50RiskRowsResponse(BaseModel):
    """B50 结构化风险行（供 B60 第六/七章导入 Table 24/25/26）。"""
    fs_risks: list[dict] = []          # 财务报表层次风险（Table 24）
    assertion_risks: list[dict] = []   # 认定层次风险（Table 25）
    accounts: list[dict] = []          # 按科目聚合（Table 26 SCOT+ 候选）


# ---------------------------------------------------------------------------
# GET /api/b60/b50-risk-rows — B50 结构化风险行，供 B60 第六/七章一键带入
# ---------------------------------------------------------------------------


@router.get("/b50-risk-rows", response_model=B50RiskRowsResponse)
async def get_b50_risk_rows(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> B50RiskRowsResponse:
    """从 B50 风险评估读取结构化风险行（单一真源 checklist_responses）。

    - fs_risks:        财务报表层次风险 → B60 六（一）Table 24
    - assertion_risks: 认定层次风险     → B60 六（二）Table 25
    - accounts:        按科目聚合(含循环/方案/依赖控制/最高风险) → B60 七（一）SCOT+ Table 26
    B50 未编制或无数据时返回空列表（不报错）。
    """
    try:
        from app.services.b50_risk_reader import (
            load_b50_accounts,
            load_b50_fs_risks,
            load_b50_risks,
        )
        fs = await load_b50_fs_risks(db, project_id)
        assertion = await load_b50_risks(db, project_id)
        accounts = await load_b50_accounts(db, project_id)
        return B50RiskRowsResponse(
            fs_risks=fs, assertion_risks=assertion, accounts=accounts
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("B60 b50-risk-rows 读取失败 project=%s: %s", project_id, e)
        return B50RiskRowsResponse()


# ---------------------------------------------------------------------------
# POST /api/b60/chapters/{chapter_id}/pull
# ---------------------------------------------------------------------------


@router.post("/chapters/{chapter_id}/pull", response_model=PullResponse)
async def pull_chapter_data(
    chapter_id: str,
    body: PullRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PullResponse:
    """从关联底稿提取数据填入章节。

    1. 查找章节定义获取 data_source（含 wp_code 和 label）
    2. 通过 wp_code 在 wp_index 中定位源底稿 wp_id
    3. 从源底稿的 checklist_responses 中提取 remark 内容
    4. 返回 content + source_label；无数据时返回空
    """
    # 1. 查找章节定义
    chapter = _find_chapter(chapter_id)
    if chapter is None:
        return PullResponse(content="", source_label="")

    data_source = chapter.get("data_source")
    if not data_source:
        return PullResponse(content="", source_label="")

    # data_source 结构: { "label": "B50 风险评估", "wp_code": "B50" }
    source_wp_code = data_source.get("wp_code", "")
    source_label = data_source.get("label", "")

    if not source_wp_code:
        return PullResponse(content="", source_label="")

    # 2. 通过 wp_code 在 wp_index 中查找源底稿的 wp_id
    #    wp_index.id 是索引表主键；需要找到关联的 working_paper.id 作为 wp_id
    #    wp_index 可能无 wp_id 列，通过 working_paper 表 JOIN 获取
    try:
        find_source_sql = text("""
            SELECT wp.id AS wp_id
            FROM wp_index wi
            JOIN working_paper wp ON wp.wp_index_id = wi.id
            WHERE wi.project_id = :project_id
              AND wi.wp_code = :wp_code
              AND wi.is_deleted = false
              AND wp.is_deleted = false
            LIMIT 1
        """)
        result = await db.execute(
            find_source_sql,
            {"project_id": str(body.project_id), "wp_code": source_wp_code},
        )
        row = result.fetchone()
    except Exception as e:
        logger.warning("查询源底稿 wp_id 失败 (wp_code=%s): %s", source_wp_code, e)
        return PullResponse(content="", source_label="")

    if row is None:
        # 源底稿不存在，返回空
        return PullResponse(content="", source_label="")

    source_wp_id = row.wp_id

    # 2.5 B50 特殊处理：结构化格式化风险评估（财报层次 / 认定层次 / 特别风险），
    #     替代通用 remark 拼接，让 B60 总体策略章节拿到可读的风险清单。
    if source_wp_code == "B50":
        try:
            from app.services.b50_risk_reader import format_b50_summary_text
            b50_text = await format_b50_summary_text(db, body.project_id)
            if b50_text.strip():
                return PullResponse(content=b50_text, source_label=source_label or "B50 风险评估")
        except Exception as e:  # noqa: BLE001 — 降级到通用拼接
            logger.warning("B50 结构化拉取失败，降级通用拼接: %s", e)

    # 3. 从源底稿的 checklist_responses 中提取数据
    #    按 data_source.wp_code 的前缀匹配 item_id 或取全部 remark 拼接
    try:
        pull_sql = text("""
            SELECT item_id, remark
            FROM checklist_responses
            WHERE wp_id = :wp_id
              AND remark IS NOT NULL
              AND remark != ''
            ORDER BY item_id
            LIMIT 50
        """)
        result = await db.execute(pull_sql, {"wp_id": str(source_wp_id)})
        rows = result.fetchall()
    except Exception as e:
        logger.warning("查询源底稿 checklist_responses 失败 (wp_id=%s): %s", source_wp_id, e)
        return PullResponse(content="", source_label="")

    if not rows:
        return PullResponse(content="", source_label="")

    # 拼接内容：取非 JSON 的 remark 文本作为可读内容
    content_parts: list[str] = []
    for r in rows:
        remark = r.remark
        if not remark:
            continue
        # 跳过看起来是 JSON 结构的数据（如 applicability 矩阵等）
        stripped = remark.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            continue
        content_parts.append(remark)

    content = "\n\n".join(content_parts) if content_parts else ""

    return PullResponse(content=content, source_label=source_label)
