"""底稿 OCR 端点的旁路落盘目录（spec attachment-security-baseline 需求 1.6，ADR-ASB-07）。

26 个底稿 OCR 端点把上传文件写到 ``storage/workpapers/{wp_id}/{子目录}/``。改造前目录段直接用路径参数原文：
14 个端点在 ``wp_id`` 不是 UUID 时兜底成全零 UUID 继续写盘、调用 OCR 与大模型，另 7 个完全不校验；路由级
``dedicated_wp_gate`` 对非 UUID 路径段按设计 no-op，于是任何登录用户都能借这些端点上传文件、消耗识别算力。

统一入口：``wp_id`` 必须是合法 UUID（否则 400），目录段写规范化后的 UUID 字符串。Spec B 把这些端点改成
「先建附件再识别」时继续复用这里。
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

SIDE_STORAGE_ROOT = Path("storage/workpapers")

_SUBDIR_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")


def parse_workpaper_id(wp_id: str | UUID) -> UUID:
    """把路径参数解析成 UUID；非法时抛 400（不写盘、不调用识别）。"""
    if isinstance(wp_id, UUID):
        return wp_id
    try:
        return UUID(str(wp_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=400, detail="无效的底稿 ID")


def side_storage_dir(wp_id: str | UUID, subdir: str) -> Path:
    """``storage/workpapers/{规范化 UUID}/{subdir}``；``subdir`` 只许小写字母、数字与连字符。"""
    if not _SUBDIR_RE.fullmatch(subdir):
        raise ValueError(f"旁路目录名不合法：{subdir!r}")
    return SIDE_STORAGE_ROOT / str(parse_workpaper_id(wp_id)) / subdir
