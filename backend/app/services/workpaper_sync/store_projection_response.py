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

    baseline = registration.adapter.extract(artifact=substrate, contract=contract)
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
        payloads: dict[str, str] = {}
        for item in store_item_ids:
            row = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                    ),
                    {"wp": str(wp_id), "item": item},
                )
            ).scalar_one_or_none()
            payloads[item] = (
                str(row) if row is not None and str(row).strip() else empty
            )
        # D4-5 固定 item（remark 纯文本）一并喂 combined
        for item in tuple(getattr(provider, "STORE_ITEM_IDS_D45_FIXED", ()) or ()):
            row = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item LIMIT 1"
                    ),
                    {"wp": str(wp_id), "item": item},
                )
            ).scalar_one_or_none()
            payloads[item] = str(row) if row is not None else ""
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
    return {
        "expected_revision": int(revision),
        "field_count": len(values),
        "row_count": sum(len(v) for v in projection.row_keys.values()),
        "store_field_count": store_field_count,
        "overlay_applied": bool(overlay_applied),
        "projection": {"values": values},
    }
