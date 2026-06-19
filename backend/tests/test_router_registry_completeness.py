"""Router 注册完整性 CI 测试

断言所有含 `router = APIRouter` 的模块已注册到 FastAPI app 中（CI 阻断）。
排除 `_EXCLUDED_ROUTERS` 中的豁免模块。

Validates: Requirements 8.4
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

import pytest
from fastapi import FastAPI

from app.router_registry import (
    _EXCLUDED_ROUTERS,
    _ROUTER_PATTERN,
    register_all_routers,
)


def _discover_router_modules() -> set[str]:
    """扫描 app/routers/ 下所有含 `router = APIRouter(` 的非私有模块。"""
    routers_pkg = importlib.import_module("app.routers")
    discovered: set[str] = set()

    for module_info in pkgutil.walk_packages(
        routers_pkg.__path__, prefix="app.routers."
    ):
        if module_info.ispkg:
            continue
        module_name = module_info.name
        # 跳过私有策略文件（非 router 模块）
        parts = module_name.split(".")
        leaf = parts[-1]
        if leaf.startswith("_") and leaf != "__init__":
            continue

        try:
            mod = importlib.import_module(module_name)
            source_file = inspect.getfile(mod)
            with open(source_file, "r", encoding="utf-8") as f:
                source = f.read()
            if _ROUTER_PATTERN.search(source):
                discovered.add(module_name)
        except Exception:
            continue

    return discovered


def test_all_routers_registered():
    """断言所有含 router = APIRouter 的模块已注册（CI 阻断）。

    逻辑与 _validate_registry_completeness 相同，
    但使用 assert 而非 WARNING，确保 CI 阻断遗漏。
    """
    app = FastAPI()
    register_all_routers(app)

    # 1. 扫描所有含 router = APIRouter(...) 的模块
    discovered = _discover_router_modules()

    # 2. 收集已注册路由的 endpoint 所属模块
    registered: set[str] = set()
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            registered.add(endpoint.__module__)

    # 3. 比对，断言无遗漏
    missing = discovered - registered - _EXCLUDED_ROUTERS
    assert not missing, (
        f"未注册的 router 模块（共 {len(missing)} 个）:\n"
        + "\n".join(f"  - {m}" for m in sorted(missing))
        + "\n\n如果是故意不注册的模块，请添加到 "
        "app.router_registry._EXCLUDED_ROUTERS 中。"
    )
