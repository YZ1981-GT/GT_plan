"""从 OnlyOffice 回调 body 解析**实际编辑人**（纯函数，无 DB 依赖）。

Spec: deliverable-lineage-wiring-and-writeback-closure — Wave 2 Task 14 / 需求 7.2, 7.3

历史缺陷：`onlyoffice_callback` 路由把 `task.created_by`（交付物创建人）当编辑人传给
`handle_callback`，并以此写版本 `created_by` 与审计日志 actor → **版本链上所有 OO 编辑
版本的作者都是创建人**，与「谁改的」这一审计事实不符。当时的注释称「callback 不携带
user_id」，但实测 OnlyOffice Document Server 的回调体确实带：

- ``users``: 本次保存涉及的用户 id 列表（我们在 ``editorConfig.user.id`` 下发的就是
  平台 user_id，故可直接反解）
- ``actions``: ``[{"type": 0|1|2, "userid": "..."}]``（0=断开 1=连接 2=强制保存）
- ``history.changes[].user.id``（部分版本携带变更历史）

**铁律：解析不出就记 None（未知），禁止回退 created_by。** 伪装成创建人比留空更坏 ——
留空能看出「这条留痕缺失」，伪装则让错误信息看起来是可信的审计证据。
"""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)

#: 回调体中承载编辑人的字段（按优先级）。``users`` 是最直接的一手来源。
_USER_LIST_KEYS = ("users",)


def _coerce_uuid(raw: object) -> UUID | None:
    """把回调里的用户标识转成 UUID；非 UUID 形态（匿名 / 外部标识）返回 None。"""
    if isinstance(raw, UUID):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return UUID(raw.strip())
    except (ValueError, AttributeError):
        return None


def extract_editor_ids(body: dict) -> list[UUID]:
    """按优先级收集回调体中出现的编辑人 UUID（去重、保持出现顺序）。

    Returns:
        可解析为 UUID 的用户标识列表；无法解析时返回 ``[]``。
        **不做任何兜底猜测** —— 空列表即「未知」。
    """
    if not isinstance(body, dict):
        return []

    ordered: list[UUID] = []
    seen: set[UUID] = set()

    def _push(raw: object) -> None:
        uid = _coerce_uuid(raw)
        if uid is not None and uid not in seen:
            seen.add(uid)
            ordered.append(uid)

    for key in _USER_LIST_KEYS:
        for item in body.get(key) or []:
            _push(item)

    for action in body.get("actions") or []:
        if isinstance(action, dict):
            _push(action.get("userid"))

    history = body.get("history")
    if isinstance(history, dict):
        for change in history.get("changes") or []:
            if isinstance(change, dict):
                user = change.get("user")
                if isinstance(user, dict):
                    _push(user.get("id"))

    return ordered


def resolve_editor_id(body: dict, *, task_id: object = None) -> UUID | None:
    """解析本次保存的编辑人；解析不出记 warning 并返回 ``None``（需求 7.3）。

    多人协同时取**首个**可识别用户（``users`` 通常只含本次保存的那位；多人场景由
    ``edited_by`` + 版本链共同呈现，本函数不猜测「主要编辑人」）。
    """
    ids = extract_editor_ids(body)
    if ids:
        return ids[0]
    logger.warning(
        "OnlyOffice callback 未携带可识别编辑人，如实记为未知 task=%s keys=%s",
        task_id,
        sorted(body.keys()) if isinstance(body, dict) else type(body).__name__,
    )
    return None
