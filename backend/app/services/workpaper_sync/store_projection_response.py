"""store-backed entry 的 projection 服务端现算（G4-0c 的纯逻辑伴生模块）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · G4-0c
Requirements: 6.1（前端不重造映射，projection 由 provider 单一真源 `build_store_projection` 现算）

═══ 为什么抽出本模块 ═══

`wp_sync_router` 的 docstring 明确它「只搬运参数 / 过 guard / 映射状态码」，**不放业务逻辑**。
store-projection 的「解析 provider → 读 store → 投影 → 拍平成 values」是业务逻辑，理应住在
service 层。router 端点只做薄封装：拿到本函数的返回 dict 直接 JSON 化，异常由 router 唯一的
状态码映射点翻译（`SyncDomainError` → 422）。

本模块**只读**：不写库、不推 revision、不建 room。失败一律抛 `SyncDomainError`（带 error_code），
绝不返回空 projection（空 projection = 清空整表）。provider 模块仍受 registry 白名单约束。

═══ materialize-ready overlay ═══

有 published substrate 时，返回值 = substrate extract 基线 ⊕ store（与首版
`overlay_store_on_baseline_projection` 同语义）。否则纯 store 会在 materialize 的
roundtrip 门上因模板脚手架字段（如 D2 的 ``GTROW-*``）被拒。无 substrate 时仍返回纯
store（materialize 会另报 `materialize_substrate_not_published`）。
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from typing import Any

import sqlalchemy as sa

from app.services.workpaper_sync.models import SyncDomainError


class StoreProjectionNotBackedError(SyncDomainError):
    """entry 不是 store-backed（无 STORE_ITEM_ID / build_store_projection / 不在交付表）。"""

    error_code = "entry_not_store_backed"


class StoreProjectionContractRequiredError(SyncDomainError):
    """registration 无 approved contract —— 无契约无从按 stable key 投影 store（AC 3.3）。"""

    error_code = "per_entry_contract_required"


class StoreProjectionProviderNotAllowedError(SyncDomainError):
    """provider_module 不在 registry 白名单内。"""

    error_code = "provider_module_not_allowed"


def resolve_store_projection_provider(adapter_id: str) -> Any:
    """按 adapter_id 从交付登记表解析 provider 模块（白名单内）。

    复用 `DELIVERED_PER_ENTRY_CONTRACTS`（contract_id == adapter_id 的单一真源），不另写
    一份 adapter→module 映射；provider_module 仍受 registry 白名单约束。
    """
    from app.services.workpaper_sync.adapters import registry as reg_module

    for row in reg_module.DELIVERED_PER_ENTRY_CONTRACTS:
        if str(row.get("contract_id") or "") == adapter_id:
            module_path = str(row.get("provider_module") or "")
            if module_path not in reg_module._ALLOWED_PROVIDER_MODULES:
                raise StoreProjectionProviderNotAllowedError(
                    f"provider_module {module_path!r} 不在白名单内"
                )
            return importlib.import_module(module_path)
    raise StoreProjectionNotBackedError(
        f"adapter {adapter_id!r} 不在 DELIVERED_PER_ENTRY_CONTRACTS 里"
    )


def _flatten_projection_values(projection: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for stable_key, field_value in projection.values.items():
        values[str(stable_key)] = {
            "value": field_value.value,
            **({"row_key": field_value.row_key} if field_value.row_key is not None else {}),
        }
    return values


async def _overlay_with_published_substrate(
    *,
    resolution: Any,
    project_id: uuid.UUID,
    wp_id: Any,
    entry_id: str,
    registration: Any,
    store_projection: Any,
) -> tuple[Any, bool]:
    """有 published substrate 则基线 ⊕ store；否则原样返回 store。"""
    from pathlib import Path

    from app.services.workpaper_sync.projection_first_publication import (
        overlay_store_on_baseline_projection,
    )
    from app.services.workpaper_sync.resolution import (
        EntryPointerMissingError,
        ResolutionIntent,
    )

    contract = registration.contract
    try:
        resolved = await resolution.resolve(
            intent=ResolutionIntent.materialize,
            project_id=project_id,
            wp_id=wp_id if isinstance(wp_id, uuid.UUID) else uuid.UUID(str(wp_id)),
            entry_id=str(entry_id),
            expected_document_type=str(contract.document_type),
        )
    except EntryPointerMissingError:
        return store_projection, False

    substrate = Path(resolved.artifact_path)
    if not substrate.is_file():
        return store_projection, False

    # 🔴 baseline extract 是 substrate **字节的纯函数**：同一份已发布不可变 artifact 永远
    # 解析出同一 Projection。substrate 是内容寻址存储（`resolved.artifact_sha256` 是它的
    # 字节 sha256），因此按 `{contract_id}:{sha256}` 作键进程内 LRU 缓存 —— 字节一变即 key
    # 变即天然失效，无需推理"何时清除"。命中时省掉 40s 的整簿 openpyxl 全量解析（这是
    # store-projection 37-46s 的全部成本；overlay 本身是毫秒级）。
    # （spec oo-html-writeback-performance ROI-1）
    #
    # adapter.extract 是同步 openpyxl 全量解析：miss 时仍丢线程池执行，让事件循环在解析
    # 期间照常服务其他请求（并发轻量轮询不被连累）。
    from app.services.workpaper_sync.parse_cache import BASELINE_EXTRACT_CACHE

    cache_key = f"{contract.contract_id}:{resolved.artifact_sha256}"
    baseline = BASELINE_EXTRACT_CACHE.get(cache_key)
    if baseline is None:
        baseline = await asyncio.to_thread(
            registration.adapter.extract, artifact=substrate, contract=contract
        )
        BASELINE_EXTRACT_CACHE.put(cache_key, baseline)
    merged = overlay_store_on_baseline_projection(
        baseline=baseline, store_projection=store_projection
    )
    return merged, True


async def compute_store_projection_response(
    *,
    session: Any,
    project_id: uuid.UUID,
    wp_id: Any,
    entry_id: str,
    registration: Any,
    resolution: Any,
) -> dict[str, Any]:
    """现算 store-backed entry 的 **materialize-ready** projection。

    调用方（router 端点）负责 guard 与状态码映射；本函数只做业务并抛 `SyncDomainError`。
    """
    contract = registration.contract
    if contract is None:
        raise StoreProjectionContractRequiredError(
            f"entry {entry_id!r} 的 registration 没有 approved contract —— "
            "无契约无从按 stable key 投影 store（AC 3.3）"
        )
    provider = resolve_store_projection_provider(str(registration.adapter_id))
    store_item_id = str(getattr(provider, "STORE_ITEM_ID", "") or "")
    if not store_item_id or not hasattr(provider, "build_store_projection"):
        raise StoreProjectionNotBackedError(
            f"entry {entry_id!r} 的 provider 未声明 STORE_ITEM_ID / "
            "build_store_projection —— 该 entry 不是 store-backed，不能走本端点"
        )
    empty = str(getattr(provider, "EMPTY_STORE_PAYLOAD", "[]"))
    store_item_ids = tuple(getattr(provider, "STORE_ITEM_IDS", ()) or ())
    if len(store_item_ids) > 1 and hasattr(provider, "build_combined_store_projection"):
        # 🔴 payload 装配的**唯一**来源：provider 若暴露 `all_store_item_ids()`（Task 4），
        #    就用它——它把 STORE_ITEM_IDS ∪ D45_FIXED ∪ D413_FIXED ∪ {D435_DICT} ∪ D47_DEDICATED
        #    收敛成单一口径。此前本处只遍历 STORE_ITEM_IDS + D45_FIXED，**漏掉** D435_DICT 与
        #    D413_FIXED ⇒ D4-35 切 OO 恒空、D4-13 两段正文恒写不进 OO（探针实证 0 vs 32 / '' vs 正文）。
        #    未暴露该函数的老 provider 回退旧并集（行为不变）。
        all_ids_fn = getattr(provider, "all_store_item_ids", None)
        if callable(all_ids_fn):
            combined_item_ids = tuple(all_ids_fn())
        else:
            combined_item_ids = store_item_ids + tuple(
                getattr(provider, "STORE_ITEM_IDS_D45_FIXED", ()) or ()
            )
        # 缺失/空时塞 `""` 的集合 = **纯文本固定项**（D45 业务场景 6 项 / D413 核对过程·结论）：
        #   它们进 provider 固定字段投影、缺省是空文本，不会像 dict-store 那样对 "[]"/"" 抛
        #   非 domain ValueError。其余（list rows / dict-store 如 D4-9/D4-31/D4-35）缺失**不塞**。
        fixed_text_ids = set(
            getattr(provider, "STORE_ITEM_IDS_D45_FIXED", ()) or ()
        ) | set(getattr(provider, "STORE_ITEM_IDS_D413_FIXED", ()) or ())
        payloads: dict[str, str] = {}
        for item in combined_item_ids:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                    ),
                    {"wp": str(wp_id), "item": item},
                )
            ).scalar_one_or_none()
            if item in fixed_text_ids:
                # 纯文本固定项：缺失塞 ""（与原 D45_FIXED 循环同款）。
                payloads[item] = str(row) if row is not None else ""
            elif row is not None and str(row).strip():
                # 🔴 list/dict-store 缺失/空 **不塞** blanket `empty`（"[]"）：dict-store（D4-9 `{}`）
                #    与 singleton（D4-31 `{}`）拿到列表默认 "[]" 会在 provider 内抛非 domain
                #    ValueError（如「D4-31 必须是单对象问卷」），一路冒泡成 opaque 500，连累整个
                #    entry 的 store-projection。让 build_combined_store_projection 的
                #    `payloads.get(item, <per-item 默认>)` 用 provider 单源 per-item 默认
                #    （list item → [] / dict、singleton → {}）。与 d43_rematerialize 的
                #    `test_dict_store_missing_key_uses_provider_default_not_empty_list` 同源修复。
                payloads[item] = str(row)
        store_projection = provider.build_combined_store_projection(
            payloads, contract=contract
        )
    else:
        row = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                ),
                {"wp": str(wp_id), "item": store_item_id},
            )
        ).scalar_one_or_none()
        payload = (
            str(row)
            if row is not None and str(row).strip()
            else empty
        )
        store_projection = provider.build_store_projection(payload, contract=contract)
    store_field_count = len(store_projection.values)
    projection, overlay_applied = await _overlay_with_published_substrate(
        resolution=resolution,
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        registration=registration,
        store_projection=store_projection,
    )
    revision = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
            {"wp": str(wp_id)},
        )
    ).scalar_one()
    values = _flatten_projection_values(projection)
    row_keys = {
        str(table_key): [str(rid) for rid in ids]
        for table_key, ids in projection.row_keys.items()
    }
    return {
        "expected_revision": int(revision),
        "field_count": len(values),
        "row_count": sum(len(v) for v in projection.row_keys.values()),
        "store_field_count": store_field_count,
        "overlay_applied": bool(overlay_applied),
        # 契约：凡带 row identity 的表，projection 必须同时返回 values 与 row_keys。
        # 下游 materialize 依赖 row_keys 判定行增删；缺失会退化成把字段名当行 id 的误判。
        "projection": {"values": values, "row_keys": row_keys},
    }
