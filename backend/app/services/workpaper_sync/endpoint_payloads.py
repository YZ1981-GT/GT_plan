# -*- coding: utf-8 -*-
"""HTTP 请求体 → 同步域值对象的**唯一**翻译层。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 28
Requirements: 8.3, 8.5, 10.6

═══ 为什么翻译不放在 router 里 ═══

两条独立理由，任一成立就足够：

1. **域边界**（Task 14 的 `TestTask14ScopeBoundary`）—— merge/冲突域的生产消费方必须
   全部在 `app/services/workpaper_sync/` 内且逐条登记在 `merge.RETIRED_DEFERRALS`。
   router 直接 `from ...merge import ResolutionChoice` 会让 `app/routers/` 成为
   merge 域消费方，那条双向等值判据立刻打红 —— 它守的正是「别让表现层拿着域值对象
   自己拼语义」。
2. **裁决落点由服务端决定**（AC 8.3）—— 前端只有 `conflict_id`（preview 给它的 opaque
   id），而 merge 域按 `(stable_field_key, row_key, oo_location)` 去重。让前端提交
   stable key 等于让它选择裁决落在哪一行：改一个字符，审计师点的「取 incoming」就落到
   另一个字段上，而两端的单测都绿。

因此本模块是**服务层**的一小块纯函数：入参是原始 JSON + 已加载的 conflict 行，
出参是域值对象。它不连库、不 commit、不判权限（那些各有唯一所有者）。
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final

from app.services.workpaper_sync.conflicts import ResolutionKind, ResolveFenceRequest
from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.merge import ResolutionChoice, ValueEnvelope
from app.services.workpaper_sync.models import SyncDomainError

__all__ = [
    "EndpointPayloadError",
    "FenceFieldMissingError",
    "UnknownConflictIdError",
    "UnknownResolutionKindError",
    "ManualValueRequiredError",
    "InstanceXpathRequiredError",
    "ProjectionPayloadError",
    "UnknownStableFieldKeyError",
    "RepeaterRowKeyRequiredError",
    "build_resolve_fence",
    "build_resolution_choices",
    "build_projection",
    "scope_only_projection",
    "RESOLVE_FENCE_REQUIRED_FIELDS",
]


class EndpointPayloadError(SyncDomainError):
    """请求体翻译失败基类。"""

    error_code = "endpoint_payload_invalid"


class FenceFieldMissingError(EndpointPayloadError):
    """resolve 的乐观锁字段缺失。

    AC 8.5 的八项乐观锁**每一项**都必须由客户端显式携带：缺项时按默认值补齐，
    等于让服务端替客户端声明「我看到的就是当前值」，fence 立刻失去意义。
    """

    error_code = "resolve_fence_field_missing"


class UnknownConflictIdError(EndpointPayloadError):
    """`conflict_id` 不属于本 canonical primary 的冲突集。

    与「不存在」共用同一语义（router 映射成统一 404）：能用别人的 conflict_id
    试探出「这个 id 存在」，就等于横向越权的存在性预言机。
    """

    error_code = "resolve_unknown_conflict_id"


class UnknownResolutionKindError(EndpointPayloadError):
    """`choice` 不在 :class:`ResolutionKind` 封闭域内 —— fail visible，不猜最近似值。"""

    error_code = "resolve_unknown_choice"


class ManualValueRequiredError(EndpointPayloadError):
    """`choice=manual` 缺 `value` 键。

    🔴 与「value 为 null」是两件事：`ValueEnvelope(present=False)` 表示「合并为删除」，
    是一个**合法裁决**。所以判据看的是 `"value" in payload`，不是 `payload.get("value")
    is not None` —— 后者会把「删除该字段」误判成「没填」。
    """

    error_code = "resolve_manual_value_required"


class InstanceXpathRequiredError(EndpointPayloadError):
    """`choice=take_instance` 缺 `instance_xpath`（AC 7.4 的 Word 实例裁决）。"""

    error_code = "resolve_instance_xpath_required"


#: AC 8.5 的八项乐观锁字段。**必填清单是判据的分母** —— 少登记一项，那一项就变成
#: 「可缺省」，而 fence 少比一项在功能测试里完全看不出来。
RESOLVE_FENCE_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "expected_current_revision",
    "room_generation",
    "client_edit_epoch",
    "canonical_application_id",
    "application_effective_request_sequence",
    "room_latest_durable_sequence",
    "conflict_set_digest",
)


def build_resolve_fence(payload: Mapping[str, Any]) -> ResolveFenceRequest:
    """请求体 → :class:`ResolveFenceRequest`。缺任一必填项即抛。

    `room_latest_durable_application_id` 刻意**不**在必填清单里：room 还没有任何
    durable application 时它就是 `null`，强制必填会让「第一次冲突」永远无法裁决。
    """
    missing = [key for key in RESOLVE_FENCE_REQUIRED_FIELDS if key not in payload]
    if missing:
        raise FenceFieldMissingError(
            f"resolve 请求缺乐观锁字段 {missing} —— AC 8.5 的八项必须由客户端显式携带，"
            "缺项时按默认值补齐等于让服务端替客户端声明「我看到的就是当前值」"
        )
    return ResolveFenceRequest(
        expected_current_revision=int(payload["expected_current_revision"]),
        room_generation=int(payload["room_generation"]),
        client_edit_epoch=int(payload["client_edit_epoch"]),
        canonical_application_id=_uuid(payload["canonical_application_id"]),
        application_effective_request_sequence=int(
            payload["application_effective_request_sequence"]
        ),
        room_latest_durable_application_id=_uuid_or_none(
            payload.get("room_latest_durable_application_id")
        ),
        room_latest_durable_sequence=int(payload["room_latest_durable_sequence"]),
        conflict_set_digest=str(payload["conflict_set_digest"]),
    )


def build_resolution_choices(
    *,
    items: Sequence[Mapping[str, Any]],
    conflict_rows: Iterable[Any],
) -> tuple[ResolutionChoice, ...]:
    """`[{conflict_id, choice, value?, instance_xpath?}]` → 域内裁决元组。

    `conflict_rows` 是 **canonical primary 的**冲突行（`repository.load_conflicts`
    的返回值）。翻译只从这些行取 `(stable_field_key, row_key, oo_location)` ——
    客户端提交的 stable key（如果有）一律忽略。
    """
    index = {row.id: row for row in conflict_rows}
    out: list[ResolutionChoice] = []
    for item in items:
        conflict_id = _uuid(item.get("conflict_id"))
        row = index.get(conflict_id)
        if row is None:
            raise UnknownConflictIdError(
                f"conflict {conflict_id} 不属于本 canonical primary 的冲突集 —— "
                "与「不存在」共用同一语义，不得据此推断该 id 是否存在"
            )
        raw = str(item.get("choice") or "")
        try:
            kind = ResolutionKind(raw)
        except ValueError as exc:
            raise UnknownResolutionKindError(
                f"choice={raw!r} 不在 {[k.value for k in ResolutionKind]} 内 —— "
                "未登记的裁决语义一律 fail visible，不按最近似值猜"
            ) from exc
        manual: ValueEnvelope | None = None
        if kind is ResolutionKind.manual:
            if "value" not in item:
                raise ManualValueRequiredError(
                    "choice=manual 必须携带 `value` 键（`null` 表示合并为删除）—— "
                    "缺键与显式 null 是两件事"
                )
            raw_value = item["value"]
            manual = ValueEnvelope(present=raw_value is not None, value=raw_value)
        instance_xpath: str | None = None
        if kind is ResolutionKind.take_instance:
            instance_xpath = str(item.get("instance_xpath") or "").strip() or None
            if instance_xpath is None:
                raise InstanceXpathRequiredError(
                    "choice=take_instance 必须携带 instance_xpath（AC 7.4）"
                )
        out.append(
            ResolutionChoice(
                stable_field_key=str(row.stable_field_key),
                kind=kind,
                row_key=str(row.row_key or ""),
                oo_location=str(row.oo_location or ""),
                manual=manual,
                instance_xpath=instance_xpath,
            )
        )
    return tuple(out)


def _uuid(raw: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError) as exc:
        raise EndpointPayloadError(f"{raw!r} 不是合法 UUID") from exc


def _uuid_or_none(raw: Any) -> uuid.UUID | None:
    return None if raw is None else _uuid(raw)


# ═══════════════════════════════════════════════════════════════════════════
# projection：`flushHtml()` 的 payload → 域内 Projection
# ═══════════════════════════════════════════════════════════════════════════


class ProjectionPayloadError(EndpointPayloadError):
    """flush payload 不是可解释的 projection。"""

    error_code = "projection_payload_invalid"


class UnknownStableFieldKeyError(EndpointPayloadError):
    """payload 里出现 contract 未登记的 stable key —— fail closed，禁位置猜测。

    与 :class:`ProjectionPayloadError` 分型的理由：形态错误（不是对象、值不是 mapping）
    是**客户端 bug**，而未登记 stable key 往往是**模板漂移**（contract 升级后前端还在发
    旧字段）。两者的运维处置完全不同，共用一个类型时前者会把后者遮蔽。
    """

    error_code = "projection_unknown_stable_field_key"


class RepeaterRowKeyRequiredError(EndpointPayloadError):
    """重复行字段缺 `row_key` —— 没有行身份就无法做字段级三方合并（AC 6.4）。"""

    error_code = "projection_repeater_row_key_required"


def build_projection(*, payload: Any, contract: SyncContract) -> Any:
    """`{"values": {stable_key: {"value": ..., "row_key": ...}}}` → :class:`Projection`。

    `value_type` 与 `mode` **只**从 contract 取，不从 payload 读：让客户端声明字段类型
    等于让它绕过金额口径与保护策略（`protected` 字段会变成可写）。这是 AC 6.1/6.5 的
    要求，也是 `merge` 域能按 `value_type` 规范化的前提。
    """
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection

    if not isinstance(payload, Mapping):
        raise ProjectionPayloadError(
            f"flush payload 是 {type(payload).__name__}，应为对象 —— "
            "缺 payload 时不得当成「空 projection」提交（那会把整表清空）"
        )
    raw_values = payload.get("values")
    if not isinstance(raw_values, Mapping):
        raise ProjectionPayloadError(
            "flush payload 缺 `values` 对象 —— 空 projection 与「没带 payload」必须可分辨"
        )
    repeater_prefixes = {str(r.table_key) for r in contract.repeaters()}
    values: dict[str, Any] = {}
    row_keys: dict[str, list[str]] = {}
    for raw_key, raw_item in raw_values.items():
        key = str(raw_key)
        item = raw_item if isinstance(raw_item, Mapping) else {"value": raw_item}
        row_key = item.get("row_key")
        lookup = key
        table = key.split("/")[0]
        if table in repeater_prefixes and row_key is None:
            raise RepeaterRowKeyRequiredError(
                f"重复行字段 {key!r} 缺 row_key —— 没有行身份就无法做字段级三方合并"
            )
        try:
            spec = contract.field_by_stable_key(lookup)
        except Exception as exc:  # noqa: BLE001 - 转型后立即抛，非 fail-open
            raise UnknownStableFieldKeyError(
                f"contract {contract.contract_id!r} 未登记 stable key {key!r} —— "
                "fail closed，不按位置或中文标题猜（AC 6.20）"
            ) from exc
        values[key] = FieldValue(
            stable_key=key,
            value=item.get("value"),
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=(None if row_key is None else str(row_key)),
        )
        if row_key is not None:
            row_keys.setdefault(table, []).append(str(row_key))
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={k: tuple(v) for k, v in row_keys.items()},
    )


def scope_only_projection() -> Any:
    """空 :class:`Projection` —— 只需要 scope 的端点（`confirm-descriptor`）用。

    🔴 与 `build_projection(payload={"values": {}})` 分开是有意的：后者表示「客户端
    真的提交了一个空 projection」（= 把整表清空），前者表示「本端点不涉及内容」。
    共用一条路径时，`confirm-descriptor` 的入参会在审计上看起来像一次清空提交。

    `contract_id` 用哨兵字符串而不是真 contract：任何试图把它当业务内容消费的路径
    都会在 contract 查找处失败，而不是静默按空表处理。
    """
    from app.services.workpaper_sync.adapters.base import Projection

    return Projection(
        contract_id="__scope_only__",
        semantic_version="0.0.0",
        document_type="xlsx",
        values={},
        row_keys={},
    )
