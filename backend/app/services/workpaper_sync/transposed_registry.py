"""转置表注册表 + 契约分派（spec d4-12-transposed-writeback / Task 4）。

把「哪些 sheet 走转置引擎」从写死 D4-29 单例，改为注册表命中分派：
``resolve_transposed_specs(contract)`` 返回该 contract 里所有命中的
:class:`TransposedSheetSpec`（据 contract_id + sheet_key）。``is_enabled`` 兼容为
``bool(resolve_transposed_specs(...))``。

灰度顺序：Task 4 阶段 REGISTRY 仅含 SPEC_D429（纯泛化、D4-29 零回归）；Task 8 再把
SPEC_D412 加入。
"""
from __future__ import annotations

from app.services.workpaper_sync.phase5_transposed_sheet import TransposedSheetSpec

# 转置表规格注册表。所有转置 sheet 的单一真源。
# Task 8 会把 SPEC_D412 追加进来（此前仅 D4-29，保证泛化灰度可独立验证）。
from app.services.workpaper_sync.phase5_d4_29_customer_detail import SPEC_D429
from app.services.workpaper_sync.phase5_d4_12_contract import SPEC_D412

#: 转置引擎当前挂接的合约（目前只有 D4 营业收入明细 entry）。
_TRANSPOSED_CONTRACT_ID = "d4.revenue_detail"

REGISTRY: tuple[TransposedSheetSpec, ...] = (SPEC_D429, SPEC_D412)


def resolve_transposed_specs(contract) -> list[TransposedSheetSpec]:
    """返回该 contract 里所有命中的转置 spec（按 REGISTRY 顺序）。

    命中判据：contract_id == 转置合约 且 该 sheet_key 出现在 contract.sheets 中。
    未命中（普通行表 / 空 sheets / 其它 entry）返回空列表。
    """
    if getattr(contract, "contract_id", None) != _TRANSPOSED_CONTRACT_ID:
        return []
    present = {s.sheet_key for s in contract.sheets}
    return [spec for spec in REGISTRY if spec.sheet_key in present]


def spec_by_sheet_key(sheet_key: str) -> TransposedSheetSpec | None:
    """按 sheet_key 精确取转置 spec（observer / instrumentation 定位用）；无则 None。"""
    for spec in REGISTRY:
        if spec.sheet_key == sheet_key:
            return spec
    return None
