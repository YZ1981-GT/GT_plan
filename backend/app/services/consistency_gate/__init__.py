"""一致性门控服务 — 按域拆分

原 consistency_gate.py（~2141 行）按检查域拆分为子模块：
- _helpers.py       : 共享辅助方法（_get_dynamic_tolerance / _get_wp_parsed_data 等）
- _base_checks.py   : 5 项基础检查 mixin 索引
- _e1_checks.py     : E1↔CFS 勾稽 mixin 索引
- _d4_checks.py     : D4 营业收入勾稽 mixin 索引
- _cycle_checks.py  : F/H/I/G/J/K/L/M/N 循环三角勾稽 mixin 索引
- _models.py        : 数据模型独立定义（文档用途，未来可替代 _impl 内定义）
- _impl.py          : 原始完整实现（域模块从此委托，避免代码重复）

外部行为不变：所有导入路径仍可通过 `from app.services.consistency_gate import ...` 使用。
"""

# 全部从 _impl 导出以保证类型一致性（CheckItem/ConsistencyResult 必须是同一类）
from app.services.consistency_gate._impl import (  # noqa: F401
    CheckItem,
    ConsistencyGate,
    ConsistencyResult,
)

__all__ = [
    "CheckItem",
    "ConsistencyResult",
    "ConsistencyGate",
]
