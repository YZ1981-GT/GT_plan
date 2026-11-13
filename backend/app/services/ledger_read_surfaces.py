"""
四表与客户科目的已知读取面注册表。

将 TbBalance/TbLedger/TbAuxBalance/TbAuxLedger 的生产读取 helper
映射到它们的模块路径，并提供 validate_surfaces() 检查 helper 存在性。

design §5, R8, AC-16, AC-23.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Literal

# ── 数据结构 ──────────────────────────────────────────────

TableName = Literal["tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"]


@dataclass(frozen=True)
class ReadSurface:
    """一个已知的四表生产读取 helper。"""

    module_path: str  # 完整模块路径，如 app.services.trial_balance_service
    symbol: str  # 函数或方法名
    description: str
    uses_active_predicate: bool = True  # 是否使用 get_active_filter / 精确 force_dataset_id


# ── 注册表 ────────────────────────────────────────────────

LEDGER_TABLE_READ_SURFACES: dict[TableName, list[ReadSurface]] = {
    "tb_balance": [
        ReadSurface(
            module_path="app.services.trial_balance_service",
            symbol="get_trial_balance_data",
            description="试算表主查询",
        ),
        ReadSurface(
            module_path="app.services.trial_balance_service",
            symbol="get_trial_balance_summary",
            description="试算表汇总查询",
        ),
        ReadSurface(
            module_path="app.services.note_trace",
            symbol="trace_note_balance",
            description="附注穿透 - 余额表取数",
        ),
        ReadSurface(
            module_path="app.services.disclosure_trace",
            symbol="trace_disclosure_balance",
            description="披露穿透 - 余额表取数",
        ),
    ],
    "tb_ledger": [
        ReadSurface(
            module_path="app.services.trial_balance_service",
            symbol="get_ledger_detail",
            description="序时账明细查询",
        ),
        ReadSurface(
            module_path="app.services.note_trace",
            symbol="trace_note_ledger",
            description="附注穿透 - 序时账取数",
        ),
        ReadSurface(
            module_path="app.services.note_source_resolvers",
            symbol="resolve_ledger_source",
            description="附注来源解析 - 序时账",
        ),
    ],
    "tb_aux_balance": [
        ReadSurface(
            module_path="app.services.trial_balance_service",
            symbol="get_aux_balance_data",
            description="辅助余额表查询",
        ),
    ],
    "tb_aux_ledger": [
        ReadSurface(
            module_path="app.services.trial_balance_service",
            symbol="get_aux_ledger_detail",
            description="辅助明细账查询",
        ),
    ],
}


# ── 校验 ──────────────────────────────────────────────────

@dataclass
class SurfaceValidationResult:
    """validate_surfaces 的结果。"""

    valid: list[str] = field(default_factory=list)
    missing_module: list[str] = field(default_factory=list)
    missing_symbol: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_module and not self.missing_symbol


class SurfaceValidationError(Exception):
    """读取面注册表中存在不可解析的 helper。"""

    def __init__(self, result: SurfaceValidationResult) -> None:
        self.result = result
        parts: list[str] = []
        if result.missing_module:
            parts.append(f"缺失模块: {result.missing_module}")
        if result.missing_symbol:
            parts.append(f"缺失符号: {result.missing_symbol}")
        super().__init__("; ".join(parts))


def validate_surfaces() -> SurfaceValidationResult:
    """检查 LEDGER_TABLE_READ_SURFACES 中每个 helper 的模块和符号是否真实存在。

    Returns
    -------
    SurfaceValidationResult
        包含 valid / missing_module / missing_symbol 三类结果。

    Raises
    ------
    SurfaceValidationError
        如果存在任一缺失的模块或符号。
    """
    result = SurfaceValidationResult()

    for table_name, surfaces in LEDGER_TABLE_READ_SURFACES.items():
        for surface in surfaces:
            fqn = f"{surface.module_path}.{surface.symbol}"
            try:
                mod = importlib.import_module(surface.module_path)
            except (ImportError, ModuleNotFoundError):
                result.missing_module.append(fqn)
                continue

            if not hasattr(mod, surface.symbol):
                result.missing_symbol.append(fqn)
                continue

            result.valid.append(fqn)

    if not result.ok:
        raise SurfaceValidationError(result)

    return result
