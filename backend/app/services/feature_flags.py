"""功能开关服务 — 控制实验功能的灰度发布

支持按项目/用户组/全局三级控制。
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# 功能开关默认值（全局）
_DEFAULT_FLAGS: dict[str, bool] = {
    "online_editing": True,        # 在线编辑（默认开启，不可用时自动降级到离线）
    "ai_workpaper_fill": True,     # AI 底稿填充
    "ai_review": True,             # AI 底稿复核
    "ai_recommendation": False,    # AI 底稿推荐（实验功能）
    "ai_diff_report": True,        # AI 年度差异分析
    "regulatory_filing": False,    # 监管报送（实验功能）
    "forum": True,                 # 吐槽专栏
    "check_in": True,              # 打卡签到
    "advanced_collaboration": False,  # 高级协同（实验功能）
    "ledger_import_v2": True,          # 新账表导入引擎（v2 已验证，默认启用）；支持项目级 override via set_project_flag
}

# 项目级覆盖（project_id → {flag: value}）
_project_overrides: dict[str, dict[str, bool]] = {}


def is_enabled(flag: str, project_id: str | UUID | None = None) -> bool:
    """检查功能是否启用

    优先级：项目级覆盖 > 全局默认
    """
    if project_id:
        pid = str(project_id)
        if pid in _project_overrides and flag in _project_overrides[pid]:
            return _project_overrides[pid][flag]
    return _DEFAULT_FLAGS.get(flag, False)


def set_project_flag(project_id: str | UUID, flag: str, enabled: bool):
    """设置项目级功能开关"""
    pid = str(project_id)
    if pid not in _project_overrides:
        _project_overrides[pid] = {}
    _project_overrides[pid][flag] = enabled
    logger.info("feature_flag: project=%s flag=%s enabled=%s", pid, flag, enabled)


def get_all_flags(project_id: str | UUID | None = None) -> dict[str, bool]:
    """获取所有功能开关状态"""
    flags = dict(_DEFAULT_FLAGS)
    if project_id:
        pid = str(project_id)
        if pid in _project_overrides:
            flags.update(_project_overrides[pid])
    return flags


def get_feature_maturity() -> dict[str, str]:
    """获取功能成熟度分级"""
    return {
        "online_editing": "pilot",  # 在线优先+离线兜底双模式
        "ai_workpaper_fill": "pilot",
        "ai_review": "pilot",
        "ai_recommendation": "experimental",
        "ai_diff_report": "pilot",
        "regulatory_filing": "experimental",
        "forum": "production",
        "check_in": "production",
        "advanced_collaboration": "experimental",
        "ledger_import_v2": "production",
        # 正式可用
        "project_management": "production",
        "trial_balance": "production",
        "adjustments": "production",
        "reports": "production",
        "disclosure_notes": "production",
        "offline_workpaper": "production",
        "attachments": "pilot",
    }
