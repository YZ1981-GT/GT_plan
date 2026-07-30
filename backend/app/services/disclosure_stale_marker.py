"""底稿保存 → 附注章节标记过期（**只标 stale，不重建同步载荷**）。

## 为什么只标 stale 而不真同步

`wp_disclosure_sync_service.sync_from_workpaper` 需要 `sub_table_data` +
`sub_table_columns`，二者由**前端** `buildXSyncPayload` 从各 composable 的行模型算出。
`WORKPAPER_SAVED` 事件的 `extra` 只有 `{wp_id, wp_code, trigger, item_ids, atomic}`
（`PUT /api/workpapers/{wp_id}/checklist-responses` 发布，无 sheet_name、无表结构）。
要在后端重建载荷就得把每个循环的载荷逻辑双写一遍 → 违反 DRY 且必然漂移。

真正的自动同步由前端 `useDisclosureAutoSync` 承担（防抖 800ms + 复用手动按钮的
`syncToDisclosureNotes`，与手动同源幂等）。本模块是**兜底**：当披露数据经**不走前端
composable 的路径**被修改时，让附注侧可见「已过期」，由用户点一次同步或走模板回流。

已知会绕过前端自动同步的路径：

- **多区块导入**（`POST /api/workpapers/{id}/f2/import-data`，本 spec 同期新增）
- API 直写 `checklist_responses`
- 后台重算 / 数据迁移脚本
- 用户在别的 Tab 改了上游（如 F2-1 审定表）而没打开披露 Tab

## 行为

1. 从 `extra.wp_code`（或 `item_ids` 前缀）识别 wp_code
2. 查 `note_workpaper_sync_registry.json` 得该 wp 的 listed/soe 章节号
3. 对项目下这些章节 `is_stale = true` + `stale_source = 'workpaper_saved'`
4. fail-soft：任何异常只 warning，绝不冒泡（底稿保存已提交，不能反向破坏）

灰度开关 `DISCLOSURE_AUTO_SYNC_ENABLED`（默认 false）只管本兜底；前端自动同步已在
生产运行，不加开关以免回退既有 89 个 Tab 的行为。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R1.4 / R5.1 / Task 4.4
"""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "STALE_SOURCE",
    "is_enabled",
    "sections_for_wp_code",
    "wp_code_from_payload",
    "mark_sections_stale",
    "handle_workpaper_saved_for_disclosure",
]

STALE_SOURCE = "workpaper_saved"

_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_workpaper_sync_registry.json"

# 披露 item_id 形态：`{WP}-note-{variant}-{suffix}` 或 `{WP}-disclosure-{variant}-{suffix}`
_DISCLOSURE_ITEM_RE = re.compile(r"^([A-Z]\d+(?:-\d+)?)-(?:note|disclosure)-(listed|soe)\b")


def is_enabled() -> bool:
    """灰度开关：默认关（Requirement 6.5 / Property 10）。"""
    raw = os.getenv("DISCLOSURE_AUTO_SYNC_ENABLED", "")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def _registry() -> dict[str, dict[str, str]]:
    """wp_code → {listed: 章节号, soe: 章节号}（模块级缓存，registry 是生成产物）。"""
    try:
        doc = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — registry 不可用时兜底降级为空
        logger.warning("disclosure_stale_marker: registry unavailable: %s", exc)
        return {}
    out: dict[str, dict[str, str]] = {}
    for e in doc.get("entries") or []:
        if not isinstance(e, dict):
            continue
        code = str(e.get("wp_code") or "").strip()
        if not code:
            continue
        out[code] = {
            k: str(e.get(k) or "").strip()
            for k in ("listed", "soe")
            if str(e.get(k) or "").strip()
        }
    return out


def sections_for_wp_code(wp_code: str | None) -> list[str]:
    """该底稿对应的附注章节号（listed + soe 都返回，实际只有匹配 variant 的存在）。"""
    if not wp_code:
        return []
    entry = _registry().get(str(wp_code).strip())
    if not entry:
        return []
    return [v for v in entry.values() if v]


def wp_code_from_payload(extra: Any) -> str | None:
    """从事件 extra 取 wp_code；缺失时按披露 item_id 前缀反推。

    `checklist_responses` 路由发布的 `extra` 含 `wp_code`，但历史/其它路径可能缺，
    此时用 `item_ids` 里的披露 item 前缀（如 `F2-note-listed-s2-overrides` → `F2`）。
    """
    if not isinstance(extra, dict):
        return None
    code = extra.get("wp_code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    items = extra.get("item_ids")
    if isinstance(items, list):
        for it in items:
            m = _DISCLOSURE_ITEM_RE.match(str(it or ""))
            if m:
                return m.group(1)
    return None


async def mark_sections_stale(
    db: AsyncSession,
    project_id: UUID,
    sections: list[str],
    *,
    year: int | None = None,
    source: str = STALE_SOURCE,
) -> int:
    """把指定章节标记为过期。返回受影响行数。

    只改 `is_stale` / `stale_source`，**不动 table_data**（Property 5：手工覆盖免疫 ——
    过期标记只是提示，不修改任何业务内容）。
    """
    if not sections:
        return 0
    params: dict[str, Any] = {
        "pid": str(project_id),
        "secs": list(sections),
        "src": source,
    }
    year_clause = ""
    if year:
        year_clause = " AND year = :year"
        params["year"] = year
    result = await db.execute(
        sa.text(
            "UPDATE disclosure_notes SET is_stale = true, stale_source = :src "
            "WHERE project_id = :pid AND is_deleted = false "
            "  AND note_section = ANY(:secs)" + year_clause
        ),
        params,
    )
    return int(result.rowcount or 0)


async def handle_workpaper_saved_for_disclosure(payload: Any) -> dict[str, Any]:
    """`WORKPAPER_SAVED` handler：标记对应附注章节过期（fail-soft）。

    Returns:
        `{"status": ..., "sections": [...], "marked": n}`；
        status ∈ `disabled` / `no_project` / `no_wp_code` / `no_mapping` / `marked` / `failed`
    """
    if not is_enabled():
        return {"status": "disabled", "sections": [], "marked": 0}

    project_id = getattr(payload, "project_id", None)
    if not project_id:
        return {"status": "no_project", "sections": [], "marked": 0}

    extra = getattr(payload, "extra", None)
    wp_code = wp_code_from_payload(extra)
    if not wp_code:
        return {"status": "no_wp_code", "sections": [], "marked": 0}

    sections = sections_for_wp_code(wp_code)
    if not sections:
        # 非披露底稿（绝大多数 WORKPAPER_SAVED）→ 正常情况，不记 error
        return {"status": "no_mapping", "sections": [], "marked": 0}

    year = getattr(payload, "year", None)
    try:
        from app.core.database import async_session

        async with async_session() as db:
            try:
                marked = await mark_sections_stale(
                    db, project_id, sections, year=year,
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    except Exception as exc:  # noqa: BLE001 — 兜底绝不冒泡到底稿保存
        logger.warning(
            "disclosure_stale_marker: mark failed project=%s wp_code=%s: %s",
            project_id, wp_code, exc,
        )
        return {"status": "failed", "sections": sections, "marked": 0}

    if marked:
        logger.info(
            "disclosure_stale_marker: marked %d sections stale project=%s wp_code=%s %s",
            marked, project_id, wp_code, sections,
        )
    return {"status": "marked", "sections": sections, "marked": marked}
