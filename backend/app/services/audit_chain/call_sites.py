"""审计链调用方裁决登记表

ADR-ALC-07: 三种策略 — mandatory / best_effort / own_session。

每个 append_audit_log( 调用点必须在此表登记，AST 守卫
test_audit_call_site_policy.py 会校验：
  - 全仓每个调用点都已登记
  - mandatory 的不得位于不重抛的 except Exception 内
  - best_effort 的必须在 begin_nested 内并被捕获
  - 登记表里的函数在源码中必须存在
"""
from __future__ import annotations

from typing import Literal

Policy = Literal["mandatory", "best_effort", "own_session"]

# 键 = "模块路径:函数名"（相对于 backend/app/）
# 值 = {"policy": Policy, "reason": str}
CALL_SITE_REGISTRY: dict[str, dict] = {
    # ── mandatory：审计失败即业务失败 ──
    "routers/archived_exception.py:archived_exception_access": {
        "policy": "mandatory",
        "reason": "归档例外通道访问（改数据权限）",
    },
    "routers/archived_exception.py:unarchive_project": {
        "policy": "mandatory",
        "reason": "解除归档操作",
    },
    "routers/formula_audit_log.py:add_audit_log": {
        "policy": "mandatory",
        "reason": "人工补记审计条目",
    },
    "routers/time_machine.py:restore_snapshot": {
        "policy": "mandatory",
        "reason": "时光机恢复（改数据）",
    },
    "routers/wp_formula.py:_write_wp_formula_audit": {
        "policy": "mandatory",
        "reason": "底稿公式增改（已在 begin_nested 内）",
    },
    "routers/wp_user_formulas.py:update_user_formulas": {
        "policy": "mandatory",
        "reason": "底稿用户公式修改",
    },
    "routers/wp_user_formulas.py:restore_preset_formula": {
        "policy": "mandatory",
        "reason": "恢复预设公式",
    },
    "services/ai_content_log_service.py:_write_lifecycle_audit": {
        "policy": "mandatory",
        "reason": "AI 内容生命周期留痕",
    },
    "services/ai_chat/adopt.py:_write_adopt_audit": {
        "policy": "mandatory",
        "reason": "AI 采纳审计（独立事务内）",
    },
    "services/bulk_tab/bulk_import_service.py:_write_import_audit_log": {
        "policy": "mandatory",
        "reason": "批量导入写数",
    },
    "services/bulk_tab/workflow_gate.py:_write_revert_audit_log": {
        "policy": "mandatory",
        "reason": "批量导入回退",
    },
    "services/conflict_resolution_service.py:_write_enqueue_audit": {
        "policy": "mandatory",
        "reason": "冲突入队审计",
    },
    "services/conflict_resolution_service.py:_write_resolve_audit": {
        "policy": "mandatory",
        "reason": "冲突调解审计",
    },
    "services/consol_audit_helper.py:log_consol_action": {
        "policy": "mandatory",
        "reason": "合并关键操作留痕",
    },
    "services/deliverable_hash_service.py:bind_version_hash": {
        "policy": "mandatory",
        "reason": "交付件版本哈希绑定",
    },
    "services/deliverable_service.py:unarchive": {
        "policy": "mandatory",
        "reason": "解除归档",
    },
    "services/draft_refresh_service.py:_write_runtime_hash_audit": {
        "policy": "mandatory",
        "reason": "运行时哈希审计",
    },
    "services/formula_settings/audit.py:audit_global": {
        "policy": "mandatory",
        "reason": "公式全局设置留痕",
    },
    "services/formula_settings/audit.py:audit_project": {
        "policy": "mandatory",
        "reason": "公式项目设置留痕",
    },
    "services/formula_settings/template_sync.py:_audit_subscription": {
        "policy": "mandatory",
        "reason": "公式模板订阅变更",
    },
    "services/gate_acknowledgement_service.py:acknowledge": {
        "policy": "mandatory",
        "reason": "门禁确认",
    },
    "services/gate_acknowledgement_service.py:revoke": {
        "policy": "mandatory",
        "reason": "门禁撤销",
    },
    "services/report_config_service.py:review_candidate": {
        "policy": "mandatory",
        "reason": "全局候选审核（已在 begin_nested 内）",
    },
    "services/note_data_lock_service.py:unlock": {
        "policy": "mandatory",
        "reason": "数据解锁（ADR-ALC-08 收口）",
    },
    "services/workpaper_ai_conclusion_audit_trail.py:record_draft_generation_audit": {
        "policy": "mandatory",
        "reason": "AI 结论草稿生成留痕",
    },
    "services/workpaper_ai_conclusion_audit_trail.py:record_confirm_audit": {
        "policy": "mandatory",
        "reason": "AI 结论确认留痕",
    },
    "services/workpaper_ai_conclusion_audit_trail.py:record_revise_audit": {
        "policy": "mandatory",
        "reason": "AI 结论修订留痕",
    },
    "services/workpaper_ai_conclusion_audit_trail.py:record_reject_audit": {
        "policy": "mandatory",
        "reason": "AI 结论拒绝留痕",
    },
    "services/workpaper_sync/adopt_substrate_response.py:_record_rollback_and_audit": {
        "policy": "mandatory",
        "reason": "回滚审计",
    },
    # ── best_effort：审计失败不阻断业务 ──
    "routers/consol_report.py:_write_consol_formula_audit": {
        "policy": "best_effort",
        "reason": "合并报表公式执行结果留痕",
    },
    "routers/report_config.py:execute_formulas_batch": {
        "policy": "best_effort",
        "reason": "公式批量执行留痕",
    },
    "services/event_handlers/_impl.py:_advance_project_status_on_dataset_activated": {
        "policy": "best_effort",
        "reason": "系统自动推进项目状态",
    },
    "services/formula_management/cross_check_run.py:_write_audit": {
        "policy": "best_effort",
        "reason": "表间审核执行留痕",
    },
    "services/onlyoffice_callback_service.py:write_security_log": {
        "policy": "best_effort",
        "reason": "OO 回调被拒安全日志（回调须及时应答）",
    },
    "services/onlyoffice_callback_service.py:_log_stale_base_save": {
        "policy": "best_effort",
        "reason": "OO 陈旧底版保存记录（回调须及时应答）",
    },
    "services/wp_disclosure_sync_service.py:_write_audit_log": {
        "policy": "best_effort",
        "reason": "HTML 附注同步审计（ADR-ALC-08 收口）",
    },
    # ── own_session：在独立会话内写并自行提交 ──
    "services/ai_chat/audit.py:audit_run_started": {
        "policy": "own_session",
        "reason": "AI 运行协调器（独立会话）",
    },
    "services/ai_chat/audit.py:audit_run_terminal": {
        "policy": "own_session",
        "reason": "AI 运行终态（独立会话）",
    },
    "services/ai_chat/audit.py:audit_access_denied": {
        "policy": "own_session",
        "reason": "AI 拒绝访问（独立会话）",
    },
    "services/ai_chat/audit.py:audit_note_saved": {
        "policy": "own_session",
        "reason": "AI 转存笔记（独立会话）",
    },
    "services/ai_chat/audit.py:audit_adopt_requested": {
        "policy": "own_session",
        "reason": "AI 采纳请求（独立会话）",
    },
    "services/ai_chat/audit.py:audit_attachment_cleanup": {
        "policy": "own_session",
        "reason": "AI 附件清理（独立会话）",
    },
    "services/ai_chat/audit.py:audit_tool_started": {
        "policy": "own_session",
        "reason": "AI 工具调用开始（独立会话）",
    },
    "services/ai_chat/audit.py:audit_tool_finished": {
        "policy": "own_session",
        "reason": "AI 工具调用结束（独立会话）",
    },
}
