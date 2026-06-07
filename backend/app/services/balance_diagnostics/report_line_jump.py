"""Report_Line_Mapping 跳转参数构建器。

负责构建从诊断弹窗跳转到 ReportLineMappingDialog 时的参数，
区分 seed_missing / unconfirmed / manual_error 三类情况，
前端 dialog 通过 dialog_prop transport 接收 initialAccountCode 实现定位高亮。

Requirements: 6.1, 6.2, 6.4, 6.5
"""

from __future__ import annotations

from backend.app.services.balance_diagnostics.diagnostics_types import (
    DiagnosticJumpTarget,
)


# ---------------------------------------------------------------------------
# mapping_status 常量
# ---------------------------------------------------------------------------

MAPPING_STATUS_SEED_MISSING = "seed_missing"
MAPPING_STATUS_UNCONFIRMED = "unconfirmed"
MAPPING_STATUS_MANUAL_ERROR = "manual_error"

VALID_MAPPING_STATUSES = {
    MAPPING_STATUS_SEED_MISSING,
    MAPPING_STATUS_UNCONFIRMED,
    MAPPING_STATUS_MANUAL_ERROR,
}


# ---------------------------------------------------------------------------
# 跳转参数构建
# ---------------------------------------------------------------------------


def build_report_line_jump_params(
    account_code: str,
    mapping_status: str,
) -> DiagnosticJumpTarget:
    """构建从诊断跳转到 ReportLineMappingDialog 的参数。

    根据 mapping_status 区分三类情况：
    - seed_missing: seed 中不存在该科目的映射 → 需补充 seed
    - unconfirmed: 有 ai_suggested 但用户未确认 → 需确认
    - manual_error: 用户手工映射存在错误 → 需修正

    transport 统一使用 dialog_prop，前端 dialog 接收 initialAccountCode。

    Args:
        account_code: 需定位的科目编码
        mapping_status: 映射状态（seed_missing / unconfirmed / manual_error）

    Returns:
        DiagnosticJumpTarget 含 transport=dialog_prop 和定位参数
    """
    if mapping_status not in VALID_MAPPING_STATUSES:
        mapping_status = MAPPING_STATUS_SEED_MISSING

    label = _get_jump_label(mapping_status)

    params: dict[str, str] = {
        "initialAccountCode": account_code,
        "highlight": "true",
        "mapping_status": mapping_status,
    }

    return DiagnosticJumpTarget(
        target_type="report_line_mapping",
        label=label,
        transport="dialog_prop",
        params=params,
    )


def _get_jump_label(mapping_status: str) -> str:
    """根据 mapping_status 返回跳转按钮中文文案。"""
    labels = {
        MAPPING_STATUS_SEED_MISSING: "补充报表行次映射（Seed 缺失）",
        MAPPING_STATUS_UNCONFIRMED: "确认报表行次映射",
        MAPPING_STATUS_MANUAL_ERROR: "修正报表行次映射",
    }
    return labels.get(mapping_status, "查看报表行次映射")


# ---------------------------------------------------------------------------
# 批量构建（多科目）
# ---------------------------------------------------------------------------


def build_report_line_jump_targets_batch(
    accounts: list[dict],
) -> list[DiagnosticJumpTarget]:
    """为一批未匹配科目构建跳转目标。

    如果所有科目 mapping_status 相同，只生成一个跳转按钮（首个科目定位）。
    如果有多类 status，按类分组生成多个跳转按钮。

    Args:
        accounts: [{account_code, mapping_status}] 列表

    Returns:
        DiagnosticJumpTarget 列表
    """
    if not accounts:
        return []

    # 按 mapping_status 分组
    by_status: dict[str, list[str]] = {}
    for acc in accounts:
        status = acc.get("mapping_status", MAPPING_STATUS_SEED_MISSING)
        if status not in VALID_MAPPING_STATUSES:
            status = MAPPING_STATUS_SEED_MISSING
        by_status.setdefault(status, []).append(acc.get("account_code", ""))

    targets: list[DiagnosticJumpTarget] = []
    for status, codes in by_status.items():
        if codes:
            targets.append(build_report_line_jump_params(codes[0], status))

    return targets


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "MAPPING_STATUS_SEED_MISSING",
    "MAPPING_STATUS_UNCONFIRMED",
    "MAPPING_STATUS_MANUAL_ERROR",
    "VALID_MAPPING_STATUSES",
    "build_report_line_jump_params",
    "build_report_line_jump_targets_batch",
]
