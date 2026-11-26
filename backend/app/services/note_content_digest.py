"""单体附注内容摘要与跨会话 CAS 冲突（2026-11-26 穿透复盘 P0）。

摘要 = ``stable_hash``（与统一写入内核同一 canonical JSON 实现，spec
platform-heavy-jobs-and-capacity-closure C2）对 ``{"text_content":…, "table_data":…}``
整体取 SHA-256，取**前 16 位**做短摘要：足够区分编辑代际，又不会在
409 响应 / 前端日志里刷屏。

只覆盖正文与表格两个**业务内容**字段 —— status / guidance / 同步簿记不属于
「内容被别人改了」的范畴（它们不动 table_data/text_content，不会造成
跨会话覆盖丢失）。
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.disclosure.note_section_write_kernel import stable_hash

__all__ = ["NOTE_CONTENT_CONFLICT", "note_content_digest", "note_content_conflict"]

NOTE_CONTENT_CONFLICT = "NOTE_CONTENT_CONFLICT"


def note_content_digest(text_content: str | None, table_data: dict | None) -> str:
    """`(正文, 表格)` 的稳定短摘要；前端把它当编辑起点回传（expected_digest）。"""
    payload: dict[str, Any] = {
        "text_content": text_content or "",
        "table_data": table_data if table_data is not None else {},
    }
    return stable_hash(payload)[:16]


def note_content_conflict(current_note: Any) -> HTTPException:
    """CAS 不匹配 → 409，附当前摘要与当前内容，调用方可展示「他人已修改」。"""
    from app.models.report_schemas import DisclosureNoteDetail  # 避免循环 import

    digest = note_content_digest(current_note.text_content, current_note.table_data)
    from fastapi.encoders import jsonable_encoder

    try:
        current = jsonable_encoder(DisclosureNoteDetail.model_validate(current_note).model_dump())
    except Exception:  # noqa: BLE001 — 只做响应载荷，不该因序列化问题盖掉冲突本身
        current = jsonable_encoder({
            "text_content": current_note.text_content,
            "table_data": current_note.table_data,
        })
    current["content_digest"] = digest
    return HTTPException(
        status_code=409,
        detail={
            "error_code": NOTE_CONTENT_CONFLICT,
            "message": "该章节已被其他会话修改，请先查看最新内容后再保存",
            "current_digest": digest,
            "current": current,
        },
    )
