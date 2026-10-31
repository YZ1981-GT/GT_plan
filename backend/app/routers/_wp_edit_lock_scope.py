"""底稿写接口的编辑锁范围（单一来源，spec workpaper-multi-window-lock-gaps R3）。

路径带 ``{wp_id}``、经 :func:`app.routers._wp_gate.dedicated_wp_gate` 的非 GET 请求**默认校验编辑锁**：有效锁的持有人
（用户 + 窗口）以外 423。只有本模块 :data:`SCOPE_RULES` 列出的四类不在门里校验：

- 不写底稿：导出、校验、纯计算、AI 生成文本 / 对话 / 建议、只读比对；
- 协作与流程：复核意见与批注、复核 / 提交复核 / 底稿状态、分派、提醒、质控、签字 —— 复核人要在编制人持锁时照常工作；
- 锁管理：sheet 锁自身的申请 / 释放 / 心跳；
- 计算后可选写回（``apply_to_sheet``）：只算不写放行，写回那一步由 ``enforce_edit_lock_at_write_point`` 校验。

默认校验而不是「列出写接口」：第一轮只列了保存 / 导入，裁决保存、OCR、证据、公式、Univer 保存都漏了。
规则按路由模板（不是实际 URL）匹配、取第一条命中。``tests/test_wp_edit_lock_scope_guard.py`` 枚举应用全部
``{wp_id}`` 写路由：每条规则都要命中路由；「不写底稿」类的处理函数与同模块被调函数不得有写库证据
（:data:`NON_CONTENT_WRITES` 登记过的非内容写除外）；计算写回函数都要调写回点校验；不经门的写路由都要在
:data:`UNGATED_WRITE_DECISIONS` 登记。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

__all__ = [
    "EditLockScope",
    "ScopeRule",
    "SCOPE_RULES",
    "edit_lock_scope",
    "NON_CONTENT_WRITES",
    "UNGATED_WRITE_DECISIONS",
    "BODY_CARRIED_CHECKED",
]


class EditLockScope(str, Enum):
    CHECK = "check"
    NO_WRITE = "no_write"
    COLLAB = "collab"
    LOCK = "lock"
    ON_APPLY = "on_apply"


@dataclass(frozen=True)
class ScopeRule:
    scope: EditLockScope
    pattern: re.Pattern[str]
    reason: str


def _rule(scope: EditLockScope, pattern: str, reason: str) -> ScopeRule:
    return ScopeRule(scope, re.compile(pattern), reason)


_N, _C, _L, _A = EditLockScope.NO_WRITE, EditLockScope.COLLAB, EditLockScope.LOCK, EditLockScope.ON_APPLY

#: 不在门里校验的路由（其余一律校验）。正则对路由模板做 ``search``，都锚在末尾。
SCOPE_RULES: tuple[ScopeRule, ...] = (
    # ── 不写底稿 ──
    _rule(_N, r"/export-(?:template|data|xlsx|with-metadata)$", "导出：生成文件返回下载"),
    _rule(_N, r"/stocktake-plan-export$", "导出监盘计划 Word"),
    _rule(_N, r"/validate(?:-formulas?|-detail|-split)?$", "校验"),
    _rule(_N, r"/capability-assert$", "能力断言（只读）"),
    _rule(
        _N,
        r"/(?:calculate|calculate-dcf|calculate-interest|accrual-test|allocate|evaluate|fx-calculate|verify-calculate"
        r"|solve-eir|generate-schedule|generate-amortization|risk-provision-test|reclass-current-portion"
        r"|derecognition-judge)$",
        "纯计算：返回结果，由页面填表后走保存",
    ),
    _rule(_N, r"/auto-data$", "自动取数：返回取数结果"),
    _rule(_N, r"/audit-sheet-refresh$", "从四表预填审定表行：返回行，由页面合并后走保存"),
    _rule(_N, r"/row-name-alignment$", "行名对齐比对：返回匹配状态"),
    _rule(_N, r"/bad-debt-rows/serialize$", "坏账行导出为 JSON"),
    _rule(_N, r"/template-file/to-json$", "模板 xlsx 转 JSON"),
    _rule(_N, r"/disclosure-notify$", "披露文本更新通知（只广播事件）"),
    _rule(_N, r"/(?:ai-generate|ai-generate-notes|ai-assist|ai-chat)$", "AI 生成文本 / 对话：返回文本，由页面填入后走保存"),
    _rule(_N, r"/ai/\{section\}$", "AI 生成章节文本"),
    _rule(
        _N,
        r"/ai/(?:chat|suggest|generate-text|analytical-review|extract-confirmations|check-consistency|audit-conclusion"
        r"|check-conclusion|cutoff-conclusion|variance-analysis|review-questions|review-reply|tsj-review"
        r"|interview-summary|stocktake-summary)$",
        "AI 分析 / 建议 / 结论草稿",
    ),
    _rule(_N, r"/j2/ai/generate$", "AI 生成文本"),
    _rule(_N, r"/j3-ai/(?:bs-analysis|check-assist)$", "AI 分析"),
    _rule(_N, r"/wp-ai/\{wp_id\}/(?:generate-explanation|refine-explanation|review-content)$", "AI 审计说明草稿（确认写回另走 confirm-explanation）"),
    _rule(_N, r"/ai-chat/history$", "清空本人的 AI 对话记录"),
    # ── 协作与流程 ──
    _rule(_C, r"/working-papers/\{wp_id\}/reviews$", "复核意见"),
    _rule(_C, r"/reviews/\{review_id\}/(?:reply|resolve)$", "复核意见回复 / 解决"),
    _rule(_C, r"/annotations$", "单元格批注"),
    _rule(_C, r"/annotations/\{annotation_id\}/(?:reply|resolve)$", "批注回复 / 解决"),
    _rule(_C, r"/(?:review-status|submit-review)$", "复核状态 / 提交复核"),
    _rule(_C, r"/working-papers/\{wp_id\}/status$", "底稿状态"),
    _rule(_C, r"/(?:assign|remind)$", "分派编制 / 复核人、催办"),
    _rule(_C, r"/qc-check$", "质控检查"),
    _rule(_C, r"/sign-status$", "签字状态"),
    _rule(_C, r"/(?:review-sign|review-unlock)$", "A21 复核签字 / 解锁"),
    # ── 锁管理 ──
    _rule(_L, r"/sheets/\{sheet_name\}/lock(?:/heartbeat)?$", "sheet 锁自身的申请 / 释放 / 心跳"),
    # ── 计算后可选写回：写回那一步校验 ──
    _rule(
        _A,
        r"/(?:depreciation-calc|impairment-analysis|amortization-calc|capitalization-check|classification-check|ecl-calc"
        r"|fair-value-test|goodwill-impairment|impairment-summary|income-tax-calc|interest-calc|payroll-calc"
        r"|share-payment-calc|expense-analysis|equity-movement|bond-amortization|valuation-sample)$",
        "计算可选写回 parsed_data（apply_to_sheet）：写回函数里校验",
    ),
)


def edit_lock_scope(route_path: str | None) -> EditLockScope:
    """路由模板的编辑锁类别；没命中任何规则 = 校验（含取不到模板的情形）。"""
    if route_path:
        for rule in SCOPE_RULES:
            if rule.pattern.search(route_path):
                return rule.scope
    return EditLockScope.CHECK


#: 「不写底稿」类里处理函数确有写库、但写的不是底稿内容的路由（守卫按路由模板放行，并要求每条都还命中）。
NON_CONTENT_WRITES: dict[str, str] = {
    "/api/projects/{project_id}/workpapers/{wp_id}/export-with-metadata": "记导出快照 wp_export_snapshot（导入时冲突检测用）",
    "/api/workpapers/{wp_id}/ai-chat/history": "删本人在这张底稿上的 AI 对话记录",
}

#: 路径带 ``{wp_id}``、不经底稿门禁的写路由：(方法, 路由模板) → (是否校验编辑锁, 理由)。校验的由处理函数显式调用。
UNGATED_WRITE_DECISIONS: dict[tuple[str, str], tuple[bool, str]] = {
    ("POST", "/api/projects/{pid}/workpapers/{wp_id}/versions/{vid}/rollback"): (True, "版本回滚：用快照覆盖底稿内容"),
    ("POST", "/api/projects/{pid}/workpapers/{wp_id}/versions"): (False, "建快照：读当前内容另存一份"),
    ("POST", "/api/projects/{pid}/workpapers/{wp_id}/versions/compare"): (False, "版本对比（只读）"),
    ("POST", "/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/not-applicable"): (True, "程序行裁剪为不适用"),
    ("POST", "/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/restore"): (True, "程序行恢复执行"),
    ("POST", "/api/projects/{pid}/procedure-trim/workpapers/{wp_id}/program-rows/task"): (False, "取 / 建程序行任务供委派，不改底稿页面"),
    ("DELETE", "/api/working-papers/{wp_id}/attachments/{attachment_id}/link"): (True, "解除附件与底稿的关联"),
    ("POST", "/api/workpapers/{wp_id}/review"): (False, "AI 复核：追加复核结果记录，不改底稿内容"),
    ("POST", "/api/workpapers/{wp_id}/sheets/{sheet_name}/onlyoffice-callback"): (
        False, "文档服务回调：没有用户与窗口；只读窗口拿到的是只读配置，开不出编辑会话",
    ),
    **{
        ("POST", "/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}" + suffix): (True, reason)
        for suffix, reason in (
            ("/pending-mutations", "在线编辑入口：建待提交变更"),
            ("/materialize", "在线编辑入口：物化房间（参与者一律按编辑身份加入）"),
            ("/materialize-from-store", "在线编辑入口：服务端直取物化"),
            ("/first-publication", "在线编辑入口：首版发布"),
            ("/adopt-substrate", "在线编辑入口：采纳底版"),
            ("/versions/{version_id}/rollback", "在线编辑版本回滚"),
        )
    },
    **{
        ("POST", "/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id:path}" + suffix): (
            False, "在线编辑会话内操作：会话只能从已校验的入口建立，拦了已开的会话收不了尾",
        )
        for suffix in (
            "/rooms/{room_id}/confirm-descriptor",
            "/rooms/{room_id}/forcesave",
            "/rooms/{room_id}/close-intents",
            "/rooms/{room_id}/participants/{participant_id}/leave",
            "/operations/{operation_id}/resolve",
            "/operations/{operation_id}/retry",
            "/recovery-cases/{case_id}/claim",
            "/recovery-cases/{case_id}/download-only",
        )
    },
}

#: 路径不带 ``{wp_id}``、底稿 id 在请求体 / 表单里的编辑器内写入（处理函数显式校验）：(方法, 路由模板, 理由)。
BODY_CARRIED_CHECKED: tuple[tuple[str, str, str], ...] = (
    ("POST", "/api/h5/import-data", "H5 导入 xlsx（底稿 id 在表单里）"),
    ("POST", "/api/a17/independence/import-b3-periods", "A17-7 从 B3 导入独立性期间"),
    ("POST", "/api/attachments/{attachment_id}/associate", "附件关联到底稿"),
)
