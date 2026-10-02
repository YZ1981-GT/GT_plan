"""公式推送 binding 注册表，唯一接入清单。"""
from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Any

BindingFactory = Callable[[], Any]
_REGISTRY: dict[str, str | BindingFactory] = {
    "E1": "app.services.formula_push.bindings.e1:E1Binding",
}


def _factory(entry: str | BindingFactory) -> BindingFactory:
    if isinstance(entry, str):
        module, name = entry.split(":", 1)
        return getattr(import_module(module), name)
    return entry


def get_binding(wp_code: str) -> Any:
    """按底稿编码取 binding；未接入的底稿抛 KeyError（中文原因）。"""
    try:
        entry = _REGISTRY[wp_code]
    except KeyError:
        raise KeyError(f"底稿 {wp_code} 尚未接入公式推送") from None
    return _factory(entry)()


def supported_wp_codes() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def watched_prefixes() -> dict[str, tuple[str, ...]]:
    return {code: tuple(get_binding(code).account_prefixes) for code in supported_wp_codes()}


def register_binding(wp_code: str, factory: BindingFactory) -> Callable[[], None]:
    """临时注册 binding；返回幂等撤销函数，生产清单仍仅在 _REGISTRY 登记。"""
    if not wp_code or wp_code in _REGISTRY:
        raise ValueError(f"底稿 {wp_code} 已注册或编码为空")
    binding = factory()
    if binding.wp_code != wp_code or not binding.account_prefixes:
        raise ValueError(f"底稿 {wp_code} 的 binding 编码或科目前缀不匹配")
    _REGISTRY[wp_code] = factory

    def revoke() -> None:
        if _REGISTRY.get(wp_code) is factory:
            del _REGISTRY[wp_code]

    return revoke
