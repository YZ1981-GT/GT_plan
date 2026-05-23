"""日志集中查看 — admin 可见，读取后端 JSON 日志文件最近 N 行

[proposal-remaining-18 / MT-8 / 任务 5.7]

API：
  GET /api/admin/logs?lines=1000&level=INFO&search=keyword
    返回最近 N 行日志（jsonl 解析后的 JSON 对象数组）+ 元信息。
    - 仅 admin 可访问（403 其他角色）
    - lines 上限 5000（防 OOM）
    - level 过滤：精确匹配 DEBUG/INFO/WARNING/ERROR/CRITICAL（大小写不敏感）
    - search 过滤：模糊匹配 message 字段（大小写不敏感）

降级策略：
  - 日志文件不存在（启动后未产生日志） → 200 + items=[] + status="no_log_file"
  - 解析失败的行（非合法 JSON） → 跳过该行，total_skipped 计数

注册到 router_registry.system 域 §120。
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.logging_config import DEFAULT_LOG_FILE_PATH
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin-logs"])


VALID_LEVELS: frozenset[str] = frozenset({
    "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL",
})

# 行数上限（防 OOM）
LINES_HARD_CAP: int = 5000


def _resolve_log_file_path() -> Path:
    """解析 JSON 日志文件路径（与 logging_config 同款规则）。"""
    env_path = os.environ.get("LOG_FILE_PATH")
    if env_path is None:
        return Path(DEFAULT_LOG_FILE_PATH)
    return Path(env_path)


def _read_last_n_lines(file_path: Path, n: int) -> list[str]:
    """读取文件最后 N 行（不一次性 readlines 整个文件）。

    使用 deque(maxlen=n) 流式读取，常数内存。
    """
    if not file_path.exists():
        return []

    if not file_path.is_file():
        return []

    try:
        with file_path.open("r", encoding="utf-8", errors="replace") as f:
            return list(deque(f, maxlen=n))
    except OSError as exc:
        logger.warning("[LOGS_VIEWER] failed to read %s: %s", file_path, exc)
        raise HTTPException(
            status_code=500,
            detail=f"无法读取日志文件：{exc.__class__.__name__}",
        ) from exc


def _parse_and_filter(
    raw_lines: list[str],
    level: str | None,
    search: str | None,
) -> tuple[list[dict[str, Any]], int]:
    """解析 jsonl 行，应用过滤。

    Returns: (items, skipped_count)
    """
    items: list[dict[str, Any]] = []
    skipped = 0

    level_upper = level.upper() if level else None
    search_lower = search.lower() if search else None

    for raw in raw_lines:
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            skipped += 1
            continue
        if not isinstance(entry, dict):
            skipped += 1
            continue

        # level 过滤
        if level_upper:
            entry_level = str(entry.get("level", "")).upper()
            if entry_level != level_upper:
                continue

        # search 模糊匹配 message 字段（大小写不敏感）
        if search_lower:
            msg = str(entry.get("message", "")).lower()
            if search_lower not in msg:
                continue

        items.append(entry)

    return items, skipped


def _require_admin(user: User) -> None:
    """仅 admin 可访问日志查看面板。"""
    role_value = user.role.value if user.role and hasattr(user.role, "value") else str(user.role or "")
    if role_value != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可查看系统日志")


@router.get("/logs", summary="读取最近 N 行 JSON 日志（admin only）")
async def get_recent_logs(
    lines: int = Query(1000, ge=1, le=LINES_HARD_CAP, description="读取行数（1-5000）"),
    level: str | None = Query(None, description="日志级别过滤（DEBUG/INFO/WARNING/ERROR/CRITICAL）"),
    search: str | None = Query(None, description="message 字段模糊匹配（大小写不敏感）"),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """返回最近 N 行日志（jsonl 解析后），按时间正序。

    Response shape:
    {
      "items": [{timestamp, level, logger, message, module, function, line, request_id}, ...],
      "total": 123,
      "log_file": "logs/app.jsonl",
      "log_file_exists": true,
      "skipped_lines": 0,
      "status": "ok" | "no_log_file"
    }
    """
    _require_admin(current_user)

    # level 入参校验
    if level is not None:
        level_upper = level.upper().strip()
        if level_upper and level_upper not in VALID_LEVELS:
            raise HTTPException(
                status_code=400,
                detail=f"非法日志级别：{level}（合法值：{sorted(VALID_LEVELS)}）",
            )

    file_path = _resolve_log_file_path()

    if not file_path.exists():
        return {
            "items": [],
            "total": 0,
            "log_file": str(file_path),
            "log_file_exists": False,
            "skipped_lines": 0,
            "status": "no_log_file",
        }

    raw_lines = _read_last_n_lines(file_path, lines)
    items, skipped = _parse_and_filter(raw_lines, level=level, search=search)

    return {
        "items": items,
        "total": len(items),
        "log_file": str(file_path),
        "log_file_exists": True,
        "skipped_lines": skipped,
        "status": "ok",
    }
