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
"""

from __future__ import annotations

import importlib
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


async def compute_store_projection_response(
    *,
    session: Any,
    wp_id: Any,
    entry_id: str,
    registration: Any,
) -> dict[str, Any]:
    """现算 store-backed entry 的 projection，返回可直接 JSON 化的响应 dict。

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
        else str(getattr(provider, "EMPTY_STORE_PAYLOAD", "[]"))
    )
    projection = provider.build_store_projection(payload, contract=contract)
    revision = (
        await session.execute(
            sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
            {"wp": str(wp_id)},
        )
    ).scalar_one()
    values: dict[str, Any] = {}
    for stable_key, field_value in projection.values.items():
        values[str(stable_key)] = {
            "value": field_value.value,
            **({"row_key": field_value.row_key} if field_value.row_key is not None else {}),
        }
    return {
        "expected_revision": int(revision),
        "field_count": len(values),
        "row_count": sum(len(v) for v in projection.row_keys.values()),
        "projection": {"values": values},
    }
