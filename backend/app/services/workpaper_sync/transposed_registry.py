"""转置表注册表 + 契约分派（spec d4-12-transposed-writeback / Task 4）。

把「哪些 sheet 走转置引擎」从写死 D4-29 单例，改为注册表命中分派：
``resolve_transposed_specs(contract)`` 返回该 contract 里所有命中的
:class:`TransposedSheetSpec`（据 sheet_key）。``is_enabled`` 兼容为
``bool(resolve_transposed_specs(...))``.

灰度顺序：Task 4 阶段 REGISTRY 仅含 SPEC_D429（纯泛化、D4-29 零回归）；Task 8 再把
SPEC_D412 加入；G4-9/G6-11 ECL 加入由 `g4-g6-shared-workbook-three-entry-lanes` spec
Task 10/15 接入。
"""
from __future__ import annotations

from app.services.workpaper_sync.phase5_transposed_sheet import TransposedSheetSpec

# 转置表规格注册表。所有转置 sheet 的单一真源。
from app.services.workpaper_sync.phase5_d4_29_customer_detail import SPEC_D429
from app.services.workpaper_sync.phase5_d4_12_contract import SPEC_D412
from app.services.workpaper_sync.phase5_g4_09_ecl_stage import SPEC_G409
from app.services.workpaper_sync.phase5_g6_11_ecl_stage import SPEC_G611
from app.services.workpaper_sync.phase5_g5_09_ecl_stage import SPEC_G509

#: 🔴 泛化（g4-g6 spec Task 10/15）：不再硬编码 contract_id，改为纯 sheet_key 命中。
#: 旧值 `_TRANSPOSED_CONTRACT_ID = "d4.revenue_detail"` 已删除。
#: REGISTRY 是唯一真源——contract 的 sheets 里出现 REGISTRY 中的 sheet_key 即走转置引擎。
REGISTRY: tuple[TransposedSheetSpec, ...] = (SPEC_D429, SPEC_D412, SPEC_G409, SPEC_G611, SPEC_G509)

#: 按 sheet_key 索引（O(1) 查找）。
_BY_SHEET_KEY: dict[str, TransposedSheetSpec] = {s.sheet_key: s for s in REGISTRY}


def resolve_transposed_specs(contract) -> list[TransposedSheetSpec]:
    """返回该 contract 里所有命中的转置 spec（按 REGISTRY 顺序）。

    命中判据：该 sheet_key 出现在 contract.sheets 中且在 REGISTRY 里有对应 spec。
    未命中（普通行表 / 空 sheets）返回空列表。

    🔴 泛化前硬编码 `contract_id == "d4.revenue_detail"` 做第一道过滤，G4/G6 的 ECL
    contract 永远被拒。泛化后改为纯 sheet_key 命中——与 `spec_by_sheet_key()` 同口径。
    D4 的行为零回归：D4 contract 里的 d429-managed / d412-managed 仍在 REGISTRY 里命中。
    """
    sheets = getattr(contract, "sheets", None)
    if not sheets:
        return []
    present = {getattr(s, "sheet_key", None) or s.get("sheet_key", "") for s in sheets}
    return [spec for spec in REGISTRY if spec.sheet_key in present]


def spec_by_sheet_key(sheet_key: str) -> TransposedSheetSpec | None:
    """按 sheet_key 精确取转置 spec（observer / instrumentation 定位用）；无则 None。"""
    return _BY_SHEET_KEY.get(sheet_key)
