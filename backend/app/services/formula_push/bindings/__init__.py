"""公式推送 binding 协议与注册表，唯一接入清单。"""
from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from importlib import import_module
from typing import Any, Protocol, runtime_checkable


# ── 通用数据类（各 binding 共用，不定义在具体 binding 模块内） ──────────────


@dataclass(frozen=True)
class WorkpaperTarget:
    """一个底稿目标。``row_id``/``field`` 为空 = 单值键（写 remark）。"""

    rule_id: str
    policy: str
    addr_id: str
    item_id: str
    formula_value: Any
    current_value: Any
    row_id: str | None = None
    field: str | None = None
    mirror_field: str | None = None


@dataclass(frozen=True)
class TargetSkip:
    rule_id: str
    addr_id: str | None
    reason: str


# ── binding 协议 ────────────────────────────────────────────────────────────


@runtime_checkable
class PushBinding(Protocol):
    wp_code: str
    account_prefixes: tuple[str, ...]
    derivations: frozenset[str]
    four_table_slots: frozenset[str]
    tb_columns: frozenset[str]
    paper_codes: tuple[str, ...]

    async def load_sources(self, db: Any, project_id: Any, year: int, wp_id: Any) -> Any: ...
    def workpaper_targets(self, rule: Any, overlay: Mapping[str, Any], sources: Any) -> tuple[list, list]: ...
    def apply(self, overlay: dict[str, Any], target: Any, value: Any) -> bool: ...
    def note_rows(self, overlay: Mapping[str, Any], template_type: str, rule: Any) -> list[dict]: ...
    def entry_warnings(self, overlay: Mapping[str, Any]) -> list[str]: ...


BindingFactory = Callable[[], PushBinding]
_REGISTRY: dict[str, str | BindingFactory] = {
    "E1": "app.services.formula_push.bindings.e1:E1Binding",
    "K1": "app.services.formula_push.bindings.k1:K1Binding",
    # ── Tier A 单公式锚点族 binding（design §九，18 码 21 条锚点） ──
    "D1": "app.services.formula_push.bindings.tier_a:binding_for('D1')",
    "D2": "app.services.formula_push.bindings.tier_a:binding_for('D2')",
    "D3": "app.services.formula_push.bindings.tier_a:binding_for('D3')",
    "D4": "app.services.formula_push.bindings.tier_a:binding_for('D4')",
    "D6": "app.services.formula_push.bindings.tier_a:binding_for('D6')",
    "D7": "app.services.formula_push.bindings.tier_a:binding_for('D7')",
    "H5": "app.services.formula_push.bindings.tier_a:binding_for('H5')",
    "H6": "app.services.formula_push.bindings.tier_a:binding_for('H6')",
    "H7": "app.services.formula_push.bindings.tier_a:binding_for('H7')",
    "H8": "app.services.formula_push.bindings.tier_a:binding_for('H8')",
    "H9": "app.services.formula_push.bindings.tier_a:binding_for('H9')",
    "H10": "app.services.formula_push.bindings.tier_a:binding_for('H10')",
    "I1": "app.services.formula_push.bindings.tier_a:binding_for('I1')",
    "I2": "app.services.formula_push.bindings.tier_a:binding_for('I2')",
    "I3": "app.services.formula_push.bindings.tier_a:binding_for('I3')",
    "I4": "app.services.formula_push.bindings.tier_a:binding_for('I4')",
    "I5": "app.services.formula_push.bindings.tier_a:binding_for('I5')",
    "I6": "app.services.formula_push.bindings.tier_a:binding_for('I6')",
}
_METHOD_ARITY = {"load_sources": 4, "workpaper_targets": 3, "apply": 3, "note_rows": 3, "entry_warnings": 1}
_CODE_RE = re.compile(r"^[A-Z]\d+$")


def _factory(entry: str | BindingFactory) -> BindingFactory:
    if not isinstance(entry, str):
        if not callable(entry):
            raise ValueError("公式推送 binding 工厂必须可调用")
        return entry
    try:
        module, reference = entry.split(":", 1)
        node = ast.parse(reference, mode="eval").body
        if isinstance(node, ast.Name):
            factory = getattr(import_module(module), node.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if any(k.arg is None for k in node.keywords):
                raise ValueError("工厂不支持展开参数")
            factory = partial(
                getattr(import_module(module), node.func.id),
                *(ast.literal_eval(arg) for arg in node.args),
                **{k.arg: ast.literal_eval(k.value) for k in node.keywords},
            )
        else:
            raise ValueError("工厂必须是名称或带字面量参数的调用")
        if not callable(factory):
            raise ValueError("工厂必须可调用")
        return factory
    except (SyntaxError, ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"公式推送 binding 工厂 {entry!r} 不合法：{exc}") from exc


def _validate_binding(wp_code: str, binding: Any) -> PushBinding:
    errors: list[str] = []
    if not isinstance(wp_code, str) or not _CODE_RE.fullmatch(wp_code):
        errors.append("注册键必须是主编码")
    if not isinstance(getattr(binding, "wp_code", None), str) or binding.wp_code != wp_code:
        errors.append("binding 编码与注册键不一致")
    if not hasattr(binding, "paper_codes"):
        try:
            binding.paper_codes = (wp_code,)
        except (AttributeError, TypeError):
            errors.append("binding 缺少 paper_codes 且无法设置缺省值")
    for name, kind, required in (
        ("account_prefixes", tuple, True), ("paper_codes", tuple, True),
        ("derivations", frozenset, False), ("four_table_slots", frozenset, False),
        ("tb_columns", frozenset, True),
    ):
        value = getattr(binding, name, None)
        if not isinstance(value, kind) or (required and not value) or not all(
            isinstance(item, str) and item and item == item.strip() for item in value
        ):
            errors.append(f"{name} 必须是{'非空' if required else ''}{kind.__name__} 字符串集合")
    papers = getattr(binding, "paper_codes", ())
    if isinstance(papers, tuple) and all(isinstance(code, str) for code in papers):
        if len(papers) != len(set(papers)) or any(
            code != wp_code and not code.startswith(f"{wp_code}-") for code in papers
        ):
            errors.append("paper_codes 必须无重复且只含本 binding 的主册或分册")
    for name, arity in _METHOD_ARITY.items():
        method = getattr(binding, name, None)
        if not callable(method):
            errors.append(f"缺少可调用方法 {name}")
            continue
        try:
            inspect.signature(method).bind(*([None] * arity))
        except (TypeError, ValueError):
            errors.append(f"方法 {name} 签名不符合协议")
        if name == "load_sources" and not inspect.iscoroutinefunction(method):
            errors.append("load_sources 必须是异步方法")
    if not isinstance(binding, PushBinding):
        errors.append("binding 未实现 PushBinding 协议")
    if errors:
        raise ValueError(f"底稿 {wp_code} 的 binding 不合法：" + "；".join(errors))
    return binding


def get_binding(wp_code: str) -> PushBinding:
    """按底稿编码取并校验 binding；未接入的底稿抛 KeyError（中文原因）。"""
    try:
        entry = _REGISTRY[wp_code]
    except KeyError:
        raise KeyError(f"底稿 {wp_code} 尚未接入公式推送") from None
    return _validate_binding(wp_code, _factory(entry)())


def supported_wp_codes() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def watched_prefixes() -> dict[str, tuple[str, ...]]:
    return {code: get_binding(code).account_prefixes for code in supported_wp_codes()}


def register_binding(wp_code: str, factory: str | BindingFactory) -> Callable[[], None]:
    """临时注册 binding；返回幂等撤销函数，生产清单仍仅在 _REGISTRY 登记。"""
    if not wp_code or wp_code in _REGISTRY:
        raise ValueError(f"底稿 {wp_code} 已注册或编码为空")
    _validate_binding(wp_code, _factory(factory)())
    _REGISTRY[wp_code] = factory

    def revoke() -> None:
        if _REGISTRY.get(wp_code) is factory:
            del _REGISTRY[wp_code]

    return revoke
