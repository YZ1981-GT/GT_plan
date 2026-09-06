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
from dataclasses import dataclass
from typing import Any, Final

from app.services.workpaper_sync.conflicts import ResolutionKind, ResolveFenceRequest
from app.services.workpaper_sync.contracts import ROW_UUID_PLACEHOLDER, SyncContract
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
    "UninstantiatedRowKeyError",
    "_ResolvedKey",
    "_segments_match",
    "_segments_match_all",
    "_prefix_suffix_match_all",
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


class UninstantiatedRowKeyError(EndpointPayloadError):
    """行域字段的 stable key 仍含 `{row_uuid}` 占位 —— 引擎永不消费该形态。

    🔴 这条是 BP-61-1（D2 HTML↔Excel 双向回写）实测抓出的 fail-open：

    `build_projection` 对行域字段要求了 `row_key`，却**不校验 key 本体是否已按
    `row_key` 实例化**。而 `plan_managed_writes._emit` 取值用的是
    `_instantiate(spec.stable_field_key, identity)` —— 实例化后的 key。提交一个
    占位字面量时，`contract.field_by_stable_key` 能查到它（它是登记在案的模板 key），
    `projection.get(实例化key)` 却永远取不到 ⇒ 一个受管字段都没写进 OOXML。

    失败会在 `_assert_roundtrip_equivalent` 才显形，报的是
    「staged representation 反读后缺少受管字段 ['表/{row_uuid}/字段']」—— 报错点与
    真因相距四个阶段，且占位字面量看上去像「引擎 bug」而不是「载荷形态错」。
    这里把失败前移到载荷解析期，并给出可执行的修复指令。
    """

    error_code = "projection_row_uuid_not_instantiated"


@dataclass(frozen=True)
class _ResolvedKey:
    """stable key 解析结果：归一化后的**实例化** key + 对应的契约模板。

    🔴 模板必须随结果一起带出：`SyncContract.field_by_stable_key` 只做**等值**匹配
    （`contracts.py`），行域字段实例化后的 key 不是登记在案的模板，直接拿实例化 key
    去查会 `ContractSchemaError`。而模板才是 `value_type`/`mode` 的唯一真源 ——
    `build_projection` 必须走模板取 spec，否则等于让 payload 的 key 形态决定契约语义。
    """

    resolved_key: str
    template_key: str


def _segments_match(template: str, key: str) -> bool:
    """模板 key 与实例化 key 是否指向同一个字段（段级等值，占位段通配）。

    与 ``Projection._matches_any_template`` 保持同一口径：分段数必须一致、
    除 ``{row_uuid}`` 占位段外每段逐字等值。这保证了「归一化后查不到契约」
    这条 fail-closed 分支不会被前后缀巧合绕过。
    """
    expected = template.split("/")
    actual = key.split("/")
    if len(expected) != len(actual):
        return False
    return all(
        exp == act or exp == ROW_UUID_PLACEHOLDER
        for exp, act in zip(expected, actual)
    )


def _template_matches(template: str, key: str) -> bool:
    """匹配口径的**唯一生产入口**（单模板版）。

    🔴 收敛成入口而不是散着调 ``_segments_match``，是为了让匹配口径的弱化
    成为**单点变异**：M7 变异 = 把本函数体改成段前缀重合，仅此一处；
    ``_segments_match`` 保持原样作为实现，测试断言的是入口判据必须与
    ``_prefix_suffix_match_all`` 逐模板分叉 ⇒ 单点改弱立刻打红。
    若没有这个入口，弱化可能分散在 ``_resolve_stable_key`` 的循环里，
    测试无法把它与实现区分开。
    """
    return _segments_match(template, key)


def _segments_match_all(templates: set[str], key: str) -> bool:
    """段级判据的全量模板版（与 ``Projection._matches_any_template`` 同口径）。

    供测试比对「段级判据 vs 前后缀判据」的结论差异；生产路径走
    ``_resolve_stable_key`` 的循环，不经过本函数。
    """
    for template in templates:
        if _segments_match(template, key):
            return True
    return False

def _prefix_suffix_match_all(
    templates: set[str], key: str
) -> bool:
    """**反例判据**：段数一致 + 占位段通配 + 其余段允许**前缀重合**（fail-open）。

    🔴 这个函数**仅**由测试调用，用来证明段级判据是必需的。它比「`startswith` +
    `endswith` + 长度」更接近真实回归（后者对 `remark_typo` 反而拦得住），
    实测会让 `remark_typo` 通过 `remark` 的模板、`aging_audited_over50` 通过
    `aging_audited_over5` 的模板 —— 静默挂到错误字段上。
    生产代码路径不得调用它：`_resolve_stable_key` 若改回这个判据，
    `test_matching_is_segment_level_not_prefix_suffix` 会打红。
    """
    for template in templates:
        template_segs = template.split("/")
        key_segs = key.split("/")
        if len(template_segs) != len(key_segs):
            continue
        if all(
            exp == ROW_UUID_PLACEHOLDER or act.startswith(exp)
            for exp, act in zip(template_segs, key_segs)
        ):
            return True
    return False



def _resolve_stable_key(
    key: str,
    *,
    contract: SyncContract,
    row_key: str | None,
    row_scoped_templates: set[str],
) -> _ResolvedKey:
    """把 payload 的 stable key 归一化成域内约定的**实例化**形态。

    客户端有两种自然写法，两种都要收下并落到同一个形态：

    * **模板 key**（`表/{row_uuid}/字段`）+ `row_key` ⇒ 按 `row_key` 实例化。
      这是契约侧唯一可查的形态（`field_by_stable_key` 只认模板）。
    * **已实例化 key**（`表/dr-xxx/字段`）⇒ 反查唯一能匹配的契约模板，并校验
      key 内嵌的行身份与 `row_key` 一致。

    域内约定的依据：`Projection.assert_matches_contract` 明文写着「行域 key 允许行
    实例化 … projection 里是具体行值」（`_matches_any_template` 用 `{row_uuid}`
    通配比对），`extract`/`merge` 产出的都是实例化 key，`plan_managed_writes._emit`
    也用 `_instantiate(spec.stable_field_key, identity)` 取值。所以
    `projection.values` 必须存**实例化 key**，而 spec 必须从**模板**取。

    Raises:
        UnknownStableFieldKeyError: 无法解析到唯一契约字段（含歧义）。
        RepeaterRowKeyRequiredError: 行域 key 缺 `row_key`。
        UninstantiatedRowKeyError: 已实例化 key 内嵌身份与 `row_key` 不一致。
    """
    if ROW_UUID_PLACEHOLDER in key:
        if key not in row_scoped_templates:
            raise UnknownStableFieldKeyError(
                f"contract {contract.contract_id!r} 未登记 stable key {key!r} —— "
                "fail closed，不按位置或中文标题猜（AC 6.20）"
            )
        if row_key is None:
            raise RepeaterRowKeyRequiredError(
                f"行域字段 {key!r} 含 {ROW_UUID_PLACEHOLDER!r} 占位但缺 row_key"
                " —— 无法实例化成引擎能消费的 key"
            )
        return _ResolvedKey(
            resolved_key=key.replace(ROW_UUID_PLACEHOLDER, row_key),
            template_key=key,
        )

    spec = None
    try:
        spec = contract.field_by_stable_key(key)
    except Exception:  # noqa: BLE001 - 未登记，继续走模板反查
        spec = None
    if spec is not None and not spec.row_scoped:
        return _ResolvedKey(resolved_key=key, template_key=key)

    # 🔴 匹配必须在**模板的 key 段级**做，不是「前缀匹配 + 后缀匹配 + 长度比较」。
    # 后者是 fail-open：若用「段数 + 占位段通配 + 其余段前缀重合」，
    # `remark_typo` 会挂到 `remark` 的模板、`aging_audited_over50` 会挂到
    # `aging_audited_over5` —— 两个不同字段静默归一成另一个契约字段，且无报错。
    # 段级匹配要求 key 的分段数与模板一致、除占位段外逐段等值（与
    # `Projection._matches_any_template` 的比对方式对齐，两者口径统一）。
    prefix_matches: list[tuple[str, str, str]] = []
    for template in row_scoped_templates:
        head, _, tail = template.partition(ROW_UUID_PLACEHOLDER)
        if not _template_matches(template, key):
            continue
        prefix_matches.append((template, head, tail))
    if not prefix_matches:
        raise UnknownStableFieldKeyError(
            f"contract {contract.contract_id!r} 未登记 stable key {key!r} —— "
            "fail closed，不按位置或中文标题猜（AC 6.20）"
        )
    _template, head, tail = prefix_matches[0]
    embedded = key[len(head) : (len(key) - len(tail)) if tail else len(key)]
    if row_key is not None and embedded != row_key:
        raise UninstantiatedRowKeyError(
            f"行域字段 {key!r} 内嵌的行身份 {embedded!r} 与 row_key={row_key!r}"
            "不一致 —— 二者必须指向同一行，否则三方合并会挂错行"
        )
    return _ResolvedKey(resolved_key=key, template_key=_template)


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
    # 行域（repeater）前缀必须同时覆盖 xlsx 与 docx 两种契约形态：
    # - docx 契约的行域字段挂在顶层 `repeaters`；
    # - xlsx 契约按 CS-19 只能挂在 `sheets[].tables[].fields`，`repeaters` 恒为空。
    # 两者共同的判据是 `FieldSpec.row_scoped`（stable key 含 `{row_uuid}` 占位）。
    # 只用 `contract.repeaters` 会让 xlsx 契约的行字段全部绕过 row_key 校验 ——
    # 字段级三方合并随即失去行身份，729 行明细会被压成一张无身份的行集合。
    repeater_prefixes = {
        str(spec.stable_field_key).split("/", 1)[0]
        for spec in contract.all_fields()
        if spec.row_scoped
    }
    row_scoped_templates = {
        str(spec.stable_field_key) for spec in contract.all_fields() if spec.row_scoped
    }
    values: dict[str, Any] = {}
    row_keys: dict[str, list[str]] = {}
    for raw_key, raw_item in raw_values.items():
        key = str(raw_key)
        item = raw_item if isinstance(raw_item, Mapping) else {"value": raw_item}
        row_key = item.get("row_key")
        table = key.split("/")[0]
        is_row_scoped = table in repeater_prefixes
        if is_row_scoped and row_key is None:
            raise RepeaterRowKeyRequiredError(
                f"重复行字段 {key!r} 缺 row_key —— 没有行身份就无法做字段级三方合并"
            )
        resolved = _resolve_stable_key(
            key,
            contract=contract,
            row_key=None if row_key is None else str(row_key),
            row_scoped_templates=row_scoped_templates,
        )
        # 契约 spec 必须按**模板**取：`field_by_stable_key` 是等值匹配，行域字段
        # 实例化后的 key 未登记（BP-61-1 实测 `ContractSchemaError`）。
        spec = contract.field_by_stable_key(resolved.template_key)
        values[resolved.resolved_key] = FieldValue(
            stable_key=resolved.resolved_key,
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
