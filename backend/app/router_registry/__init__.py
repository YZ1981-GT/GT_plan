"""路由注册表 — 按业务域拆分为子模块

将原 router_registry.py 单文件按业务域拆分为 5 个子模块，
`register_all_routers(app)` 统一入口保持 main.py 零改动。

子模块划分：
  - workpaper.py      : 底稿管理 + 底稿深度优化 + 模板管理
  - report.py         : 报表与附注 + 附注高级功能 + 导出
  - collaboration.py  : 团队看板 + PBC/函证 + 通知 + 协作 + 门禁
  - system.py         : 基础设施 + 系统管理 + 账表导入 + 健康检查
  - cycle_engines.py  : 各审计循环计算引擎（D/F/H/I/G/J/K/L/M/N）

变更日志：
  - 2026-05-22: 从单文件拆分为包结构（Phase 5 F4）
  - 2026-06-21: 添加 _validate_registry_completeness 启动校验（Req 8）
"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

from .workpaper import register_workpaper_routers
from .report import register_report_routers
from .collaboration import register_collaboration_routers
from .system import register_system_routers
from .cycle_engines import register_cycle_engine_routers

logger = logging.getLogger(__name__)

# 故意不注册的模块（废弃/实验性/子路由已通过父包 include_router 注册）
_EXCLUDED_ROUTERS: set[str] = {
    # eqcr 子模块通过 eqcr/__init__.py 的 include_router 聚合注册
    "app.routers.eqcr.workbench",
    "app.routers.eqcr.time_tracking",
    "app.routers.eqcr.shadow_compute",
    "app.routers.eqcr.related_parties",
    "app.routers.eqcr.prior_year",
    "app.routers.eqcr.opinions",
    "app.routers.eqcr.notes",
    "app.routers.eqcr.metrics",
    "app.routers.eqcr.memo",
    "app.routers.eqcr.independence",
    "app.routers.eqcr.gate",
    "app.routers.eqcr.constants",
    # 待注册模块（功能完整但尚未纳入主注册流程）
    "app.routers.issue_hints",
    "app.routers.workpaper_summaries",
    "app.routers.wp_render_registry",
}

_ROUTER_PATTERN = re.compile(r"^router\s*=\s*APIRouter\(", re.MULTILINE)


def register_all_routers(app: "FastAPI") -> None:
    """一次性注册所有路由，按业务域分组。

    保持与原 router_registry.py 完全相同的函数签名，
    main.py 调用方式零改动。
    """
    register_system_routers(app)
    register_workpaper_routers(app)
    register_report_routers(app)
    register_collaboration_routers(app)
    register_cycle_engine_routers(app)

    _validate_registry_completeness(app)


def _validate_registry_completeness(app: "FastAPI") -> None:
    """扫描 routers/ 目录，比对已注册列表，WARNING 遗漏。

    不阻断启动，仅日志输出遗漏模块以便开发者排查。
    """
    try:
        routers_pkg = importlib.import_module("app.routers")
    except ImportError:
        logger.warning("无法导入 app.routers 包，跳过注册完整性校验")
        return

    # 1. 扫描所有含 router = APIRouter(...) 的模块
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
            # 策略文件如 _b_index.py / _context.py 不是 router
            # 但 eqcr 子模块以正常名称命名，不受影响
            continue

        try:
            # 尝试获取源码检查是否含 router = APIRouter(
            mod = importlib.import_module(module_name)
            source_file = inspect.getfile(mod)
            with open(source_file, "r", encoding="utf-8") as f:
                source = f.read()
            if _ROUTER_PATTERN.search(source):
                discovered.add(module_name)
        except Exception:
            # 无法加载/读取的模块跳过
            continue

    # 2. 收集已注册路由的 endpoint 所属模块
    registered: set[str] = set()
    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is not None:
            registered.add(endpoint.__module__)

    # 3. 比对，输出遗漏
    missing = discovered - registered - _EXCLUDED_ROUTERS
    if missing:
        logger.warning(
            "未注册的 router 模块（共 %d 个）: %s",
            len(missing),
            sorted(missing),
        )
