"""底稿精细化规则引擎 — 底层共享 helper

仅放置被主引擎（提取逻辑）与审计检查子模块共用的低层工具函数，
保持依赖单向：wp_fine_rule_engine → wp_fine_rule_checks → wp_fine_rule_util。
"""
from decimal import Decimal, InvalidOperation
from typing import Optional


def _safe_num(val) -> Optional[float]:
    """安全转换为数字"""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, Decimal):
            return float(val)
        s = str(val).strip().replace(",", "")
        if not s or s in ("None", "-", "—", ""):
            return None
        return float(s)
    except (ValueError, InvalidOperation):
        return None
