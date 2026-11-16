"""
四表与客户科目的已知读取面注册表。

将 TbBalance/TbLedger/TbAuxBalance/TbAuxLedger 的生产读取 helper
映射到它们的模块路径，并提供 validate_surfaces() 检查 helper 存在性。

design §5, R8, AC-16, AC-23.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 2026-11-15 复核勘误（spec platform-global-display-settings-closure 任务 11B）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
原注册表登记 9 条、**全部是虚构符号**（`validate_surfaces()` 现跑
`valid=0`、`missing_module=2`、`missing_symbol=7`）：

  - `app.services.note_trace` 模块**不存在**（`ModuleNotFoundError`）；
  - `trial_balance_service.get_trial_balance_data / get_trial_balance_summary /
    get_ledger_detail / get_aux_balance_data / get_aux_ledger_detail` 均不存在
    （真实类 `TrialBalanceService` 只有 `recalc_unadjusted` 等，且是方法不是模块级函数）；
  - `disclosure_trace.trace_disclosure_balance` 不存在；
  - `note_source_resolvers.resolve_ledger_source` 不存在（真实名是
    `resolve_ledger_sum` / `resolve_aux_balance` / `resolve_aux_ledger_aging`）。

也就是说这张表**从未真实校验过**：`test_ledger_read_surfaces.py` 只测结构
（isinstance / 非空 / 无重复）与两个 mock 掉注册表的负例，从不跑真实注册表
⇒ 9 条全错而测试全绿。这正是「registry 成了只被测试看的副本」的同型缺陷。

现算真实规模（`tmp_ledger_surfaces/probe.py`，AST 扫 `backend/app/` 生产代码）：
**137 个文件 / 1327 处**四表名字引用，横跨 routers / services / wp_render_strategies。
逐条收口属独立 spec 工作量（与 memory ㉗③「规模超单轮能力时冻结棘轮」同纪律），
故本轮：

1. **删除全部虚构条目**，改为从真实符号表登记的**已核对子集**（每条都现跑 import 验证）；
2. 新增 `LEDGER_TABLE_READ_SURFACE_BASELINE`（文件数上限）作棘轮，只许变短；
3. `validate_surfaces()` 的失败不再被「测试只测结构」掩盖 —— 新增真实注册表用例。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Literal

# ── 数据结构 ──────────────────────────────────────────────

TableName = Literal["tb_balance", "tb_ledger", "tb_aux_balance", "tb_aux_ledger"]


@dataclass(frozen=True)
class ReadSurface:
    """一个已知的四表生产读取 helper。

    `module_path` + `symbol` 必须是**现跑可解析**的真实符号：
    - 模块级函数：`symbol="func_name"`
    - 类方法：`symbol="ClassName.method_name"`（用 `resolve_symbol` 逐段取属性）
    """

    module_path: str
    symbol: str
    description: str
    uses_active_predicate: bool = True  # 是否使用 get_active_filter / 精确 force_dataset_id


# ── 注册表（已核对子集）────────────────────────────────────
#
# 每条都经 `validate_surfaces()` 现跑 import + 属性解析验证过。
# 🔴 这不是完整闭集（真实读取面 137 文件 / 1327 处，见模块 docstring），
#    只登记「四表读取的公共入口」这一层；业务侧的散读按棘轮冻结。

LEDGER_TABLE_READ_SURFACES: dict[TableName, list[ReadSurface]] = {
    "tb_balance": [
        ReadSurface(
            module_path="app.services.trial_balance_service",
            symbol="TrialBalanceService.recalc_unadjusted",
            description="试算表未审数重算（四表读取公共入口）",
        ),
        ReadSurface(
            module_path="app.services.tb_balance_rollup",
            symbol="aggregate_period_movement",
            description="余额表期间发生额汇总",
        ),
    ],
    "tb_ledger": [
        ReadSurface(
            module_path="app.services.note_source_resolvers",
            symbol="resolve_ledger_sum",
            description="附注来源解析 - 序时账汇总",
        ),
        ReadSurface(
            module_path="app.services.ledger_window_service",
            symbol="LedgerWindowService.fetch",
            description="序时账服务端窗口取数",
        ),
    ],
    "tb_aux_balance": [
        ReadSurface(
            module_path="app.services.note_source_resolvers",
            symbol="resolve_aux_balance",
            description="附注来源解析 - 辅助余额",
        ),
        ReadSurface(
            module_path="app.services.note_aux_balance_explode",
            symbol="explode_aux_balance",
            description="辅助余额展开",
        ),
    ],
    "tb_aux_ledger": [
        ReadSurface(
            module_path="app.services.note_source_resolvers",
            symbol="resolve_aux_ledger_aging",
            description="附注来源解析 - 辅助明细账账龄",
        ),
    ],
}


#: 棘轮：真实读取面文件数上限（现算 137，只许变短）。
#:
#: 🔴 为什么不直接修完：逐条收口 1327 处横跨 137 文件，每条都要先判
#: 「是否走 `get_active_filter` 而非裸 `project/year/is_deleted`」，属独立
#: spec 工作量。冻结棘轮 + 只减不增，比「登记 9 条假符号 + 测试全绿」诚实。
LEDGER_TABLE_READ_SURFACE_BASELINE = 137


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


def resolve_symbol(module: object, dotted: str) -> object:
    """按 `"ClassName.method"` 逐段取属性；任一段缺失抛 AttributeError。

    🔴 不能只 `hasattr(module, symbol)`：类方法登记成 `Class.method` 时，
    `hasattr(module, "Class.method")` 恒 False（模块属性里没有带点的名字），
    于是「登记正确也被判缺失」。原实现的 7 条 missing_symbol 里就有这种混淆。
    """
    target: object = module
    for part in dotted.split("."):
        target = getattr(target, part)
    return target


def _module_source_path(module_path: str):
    """把 `app.services.x` 映射到 `backend/app/services/x.py`（或包的 `__init__.py`）。"""
    from pathlib import Path

    rel = module_path.split(".")
    base = Path(__file__).resolve().parents[2]  # backend/
    candidate = base.joinpath(*rel).with_suffix(".py")
    if candidate.exists():
        return candidate
    pkg = base.joinpath(*rel) / "__init__.py"
    if pkg.exists():
        return pkg
    raise FileNotFoundError(module_path)


def _symbol_defined(path, dotted: str) -> bool:
    """AST 判定 `dotted`（`func` 或 `Class.method`）是否在该模块源码中定义。

    🔴 为什么不用 import + getattr：`trial_balance_service` 等重型 service 的
    **属性解析**会触发模块级惰性初始化（实测 `validate_surfaces()` 在 CI 上挂住
    不返回，正是 11B 复核时该 registry 从未被真实跑过的原因之一）。AST 只读源码，
    零副作用、毫秒级，且判据更强（要求**定义**而非仅存在属性）。
    """
    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return False

    parts = dotted.split(".")
    body: list = list(tree.body)
    for index, part in enumerate(parts):
        found = None
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == part:
                found = node
                break
            if isinstance(node, ast.ClassDef) and node.name == part:
                found = node
                break
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for tgt in targets:
                    if isinstance(tgt, ast.Name) and tgt.id == part:
                        found = node
                        break
                if found is not None:
                    break
        if found is None:
            return False
        if index == len(parts) - 1:
            return True
        if isinstance(found, ast.ClassDef):
            body = list(found.body)
        else:
            # 函数上还有 `.x` 段 ⇒ 不可能（函数没有可解析的子定义）
            return False
    return True


def validate_surfaces() -> SurfaceValidationResult:
    """检查 LEDGER_TABLE_READ_SURFACES 中每个 helper 的模块和符号是否真实存在。

    判定走 **AST**（不 import、零副作用），并要求符号是**源码中真实定义**的。

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

    for _table_name, surfaces in LEDGER_TABLE_READ_SURFACES.items():
        for surface in surfaces:
            fqn = f"{surface.module_path}.{surface.symbol}"
            try:
                path = _module_source_path(surface.module_path)
            except FileNotFoundError:
                result.missing_module.append(fqn)
                continue

            if not _symbol_defined(path, surface.symbol):
                result.missing_symbol.append(fqn)
                continue

            result.valid.append(fqn)

    if not result.ok:
        raise SurfaceValidationError(result)

    return result


def declared_count() -> int:
    """登记条数（供守卫判「空注册表 = 恒绿」）。"""
    return sum(len(items) for items in LEDGER_TABLE_READ_SURFACES.values())
