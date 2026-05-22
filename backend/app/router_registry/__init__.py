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
"""
from fastapi import FastAPI

from .workpaper import register_workpaper_routers
from .report import register_report_routers
from .collaboration import register_collaboration_routers
from .system import register_system_routers
from .cycle_engines import register_cycle_engine_routers


def register_all_routers(app: FastAPI) -> None:
    """一次性注册所有路由，按业务域分组。

    保持与原 router_registry.py 完全相同的函数签名，
    main.py 调用方式零改动。
    """
    register_system_routers(app)
    register_workpaper_routers(app)
    register_report_routers(app)
    register_collaboration_routers(app)
    register_cycle_engine_routers(app)
