# -*- coding: utf-8 -*-
"""B60 章节定义 API — 提供静态章节结构供前端动态加载。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["b60-chapters"])

# ─── 模块级缓存：静态 JSON 只加载一次 ───────────────────────────────
_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "b60_chapter_definitions.json"
_cached_definitions: list[dict[str, Any]] | None = None


def _load_chapter_definitions() -> list[dict[str, Any]]:
    """从静态 JSON 文件加载章节定义列表，模块级缓存。"""
    global _cached_definitions
    if _cached_definitions is not None:
        return _cached_definitions
    try:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            _cached_definitions = json.load(f)
    except Exception as exc:
        logger.warning("加载 b60_chapter_definitions.json 失败: %s", exc)
        _cached_definitions = []
    return _cached_definitions


@router.get("/b60/chapter-definitions")
async def get_chapter_definitions(project_id: str | None = None) -> JSONResponse:
    """加载静态章节定义 JSON.

    当前版本统一返回完整列表，project_id 为未来按项目类型返回差异化章节预留接口。
    """
    definitions = _load_chapter_definitions()
    return JSONResponse(content=definitions, status_code=200)
