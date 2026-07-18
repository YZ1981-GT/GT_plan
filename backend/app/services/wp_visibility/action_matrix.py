"""Action Matrix 与 Review Whitelist（Task 6 / 组件 C6 ActionMatrix）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 7.1：Action_Matrix 键 = (user_class, access_kind, identity, entrypoint, route, method,
    action, source_state, target_state) 九维共同匹配一个完整允许项。
  - 7.2/7.3：全部维度命中同一完整允许项才允许；任一维度未命中即拒绝。
  - 7.4：未登记 action / route / method / 状态迁移一律默认拒绝。
  - 7.5：Operation_Reviewer 复核动作必须同时命中 Action_Matrix 完整允许项与 Review_Whitelist 完整允许项。
  - 7.6/7.7：多身份仅合并各身份 **独立命中** 的完整允许项；禁止跨身份拼接维度。
  - 7.8：无状态迁移的 action 用已登记的 ``"none"`` source/target 完成匹配。
  - 7.9/7.10：每个 Access_Grant 用自身 access_kind/页面/动作匹配完整条目，命中后才并集。
Design: 组件 C6 / "Action Matrix and Review Whitelist" §6 / Property 8（P8：grant/matrix/多身份）、
  Property 9（P9：reviewer 白名单）。

**data/config-driven（Route_Drift_Guard 可静态读取，Task 16）**：全部完整允许项在模块加载时由
下方声明式规则展开为不可变 ``frozenset[MatrixEntry]``。矩阵纯数据、无副作用；``lookup()`` 是纯查表。

**entrypoint vs route（初始登记约定）**：``entrypoint`` 是稳定入口族标识（如 ``workpaper.render_config``），
是本任务可控的主安全维度；``route`` 在 Task 9–11 把具体路由接入 gate 时按路由粒度登记。初始条目
``route=None`` 表示"entrypoint 族条目，覆盖映射到该 entrypoint 的全部路由"（Task 16 Ledger 绑定
路由→entrypoint）。``lookup()`` 优先精确匹配 (含 route)，未命中再回退到同键 ``route=None`` 的族条目——
这是**唯一**的、被明确定义的回退，其余八维（user_class/access_kind/identity/entrypoint/method/
action/source/target）恒为精确相等，绝不放宽（Req 7.3/7.4）。

**access_mode（read/mutation）**：每个完整允许项声明其读/写属性。gate 对 readonly grant（History_Only）
只接受 ``access_mode == "read"`` 的条目（Req 5.12–5.14）。access_mode 是条目属性、不入九维键。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# user_class（角色分类，与 VisibilityRole.value 对齐）
# ---------------------------------------------------------------------------
UC_ADMIN = "admin"
UC_SUPERVISOR = "supervisor"
UC_RESTRICTED = "restricted"

# access_kind（与 contracts.REGISTERED_ACCESS_KINDS 对齐）
AK_ADMIN = "admin"
AK_SUPERVISOR_SCOPE = "supervisor_scope"
AK_LEAD = "lead"
AK_ASSIGNEE = "assignee"
AK_REVIEWER = "reviewer"
AK_LEAD_HISTORY = "lead_history"
AK_ROW_HISTORY = "row_history"

# 每个 access_kind 的固定来源 identity 标签（与 visibility_query._IDENTITY_BY_KIND 对齐）。
IDENTITY_BY_KIND: dict[str, str] = {
    AK_ADMIN: "admin",
    AK_SUPERVISOR_SCOPE: "supervisor_scope",
    AK_LEAD: "workpaper_lead",
    AK_ASSIGNEE: "row_assignee",
    AK_REVIEWER: "row_reviewer",
    AK_LEAD_HISTORY: "lead_history",
    AK_ROW_HISTORY: "row_history",
}

NONE_STATE = "none"

AccessMode = Literal["read", "mutation"]


@dataclass(frozen=True)
class MatrixKey:
    """Action_Matrix 九维键（Req 7.1）。route 为 None 表示 entrypoint 族条目。"""

    user_class: str
    access_kind: str
    identity: str
    entrypoint: str
    route: str | None
    method: str | None
    action: str
    source_state: str
    target_state: str


@dataclass(frozen=True)
class MatrixEntry:
    """完整允许项 = 九维键 + access_mode（read/mutation）。"""

    key: MatrixKey
    access_mode: AccessMode


# ---------------------------------------------------------------------------
# 声明式规则 → 展开为完整允许项
#
# 读入口（GET / 无状态迁移）：source=target="none"。
# 写入口：按需带状态迁移；无迁移的写入口用 "none"/"none"（Req 7.8）。
# ---------------------------------------------------------------------------

# (entrypoint, method, action) —— 读族（全部只读）
_READ_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("workpaper.list", "GET", "list"),
    ("workpaper.detail", "GET", "read_detail"),
    ("workpaper.render_config", "GET", "read_render"),
    ("workpaper.html", "GET", "read_html"),
    ("workpaper.checklist_read", "GET", "read_checklist"),
    ("workpaper.parsed_data_read", "GET", "read_parsed_data"),
    ("workpaper.status_read", "GET", "read_status"),
    ("workpaper.version_list", "GET", "read_versions"),
    ("workpaper.ai_context", "GET", "ai_read"),
    ("procedure.task_read", "GET", "read_task"),
    ("editor.config", "GET", "editor_config"),
    ("editor.file_read", "GET", "editor_read"),
    ("attachment.read", "GET", "attach_read"),
    ("attachment.download", "GET", "attach_download"),
    ("file.download", "GET", "file_download"),
    ("file.preview", "GET", "file_preview"),
)

# (entrypoint, method, action) —— 无状态迁移的内容写族
_CONTENT_MUTATION_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("workpaper.checklist_save", "PUT", "save_checklist"),
    ("workpaper.parsed_data_write", "PUT", "save_parsed_data"),
    ("workpaper.ai_generate", "POST", "ai_generate"),
    ("attachment.upload", "POST", "attach_upload"),
    ("attachment.delete", "DELETE", "attach_delete"),
    ("workpaper.import", "POST", "import_data"),
    ("workpaper.export", "POST", "export_data"),
)

# 附件关联（associate）：lead/admin/supervisor_scope 允许；assignee/reviewer 不允许（§6）。
_ASSOCIATE_FAMILY = ("attachment.associate", "POST", "attach_associate")
# 版本回滚（restore）：仅 lead/admin/supervisor_scope。
_VERSION_RESTORE_FAMILY = ("version.restore", "POST", "version_restore")
# 版本快照创建（snapshot）：whole-wp 写，仅 lead/admin/supervisor_scope（与 restore 同级）。
_VERSION_SNAPSHOT_FAMILY = ("version.snapshot", "POST", "version_snapshot")
# 编辑器写盘：仅 lead/admin/supervisor_scope（reviewer editor write 明确禁止，§6）。
_EDITOR_WRITE_FAMILY = ("editor.file_write", "POST", "editor_write")
# 试算表审定回写（trial-balance writeback）：whole-wp 审定数写 trial_balance，
# 仅 lead/admin/supervisor_scope；method 因组件而异（S/M 类 POST、N 类 PUT）均登记。
_TB_WRITEBACK_METHODS: tuple[str, ...] = ("POST", "PUT")

# 通用 file_status 状态迁移（status_transition）：登记真实 ``WpFileStatus`` 枚举值之间的合法迁移
# （lead/admin/supervisor_scope）。真实枚举（app.models.workpaper_models.WpFileStatus）：
#   draft / edit_complete / under_review / revision_required / review_passed / archived。
# 迁移集精确对齐服务端权威状态机 ``WorkingPaperService.update_status.VALID_TRANSITIONS``
# （working_paper_service.py），使 gate 绝不拒绝服务端合法的 file_status 迁移：
#   draft→edit_complete；edit_complete→draft/under_review；under_review→revision_required/review_passed；
#   revision_required→edit_complete；review_passed→archived。
#   + 旧值兼容 review_level1_passed / review_level2_passed 的合法迁移。
_STATUS_TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("draft", "edit_complete"),
    ("edit_complete", "draft"),
    ("edit_complete", "under_review"),
    ("under_review", "revision_required"),
    ("under_review", "review_passed"),
    ("revision_required", "edit_complete"),
    ("review_passed", "archived"),
    # 旧值兼容（legacy WpFileStatus 值）
    ("review_level1_passed", "review_level2_passed"),
    ("review_level1_passed", "edit_complete"),
    ("review_level1_passed", "archived"),
    ("review_level2_passed", "review_level1_passed"),
    ("review_level2_passed", "archived"),
)

# ProcedureRowTask 状态机迁移（design "Data Models"：unassigned→assigned→acknowledged→
# in_progress→submitted→reviewed，支持 changes_requested 返修）。
# assignee 可发起的执行侧迁移：
_ASSIGNEE_TASK_TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("assigned", "acknowledged"),
    ("acknowledged", "in_progress"),
    ("in_progress", "submitted"),
    ("changes_requested", "in_progress"),
)
# reviewer 可发起的复核侧迁移（Review_Whitelist）：
_REVIEWER_TASK_TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("submitted", "reviewed"),
    ("submitted", "changes_requested"),
)

# reviewer 复核会话动作（同 task/sheet）：读 + 评论（Review_Whitelist）。
_REVIEW_CONVERSATION_READ = ("review.conversation.read", "GET", "review_read")
_REVIEW_CONVERSATION_COMMENT = ("review.conversation.comment", "POST", "review_comment")

# ---------------------------------------------------------------------------
# 专属组件 /{wp_id}/... 通用子路由族（Task 9 DEDICATED-SUB-ROUTE / 组件 C10 EntryIntegration）
#
# D~N（及 A/B/C/S）专属科目组件的 per-component 路由全部形如 ``/api/{module}/{wp_id}/{suffix}``，
# 由单一 router-level 依赖 ``dedicated_wp_gate`` 按 HTTP method 统一分类接入 gate（不逐路由手工接线）：
#   - GET/HEAD          → 读动作 ``dedicated_read``（只读族；全部读身份，含 reviewer / History_Only）。
#   - POST/PUT/PATCH    → 内容写 ``dedicated_write``（full_power + assignee；reviewer / History_Only 拒绝）。
#   - DELETE            → 内容删 ``dedicated_delete``（同写；full_power + assignee）。
# 该族按 **每个 method** 分别登记完整条目（九维精确匹配，Req 7.1/7.8），使 gate 绝不因 method 不匹配
# 而误拒合法 lead/assignee/admin 访问，也绝不放宽 reviewer / History_Only 的只读边界。
_DEDICATED_ENTRYPOINT = "workpaper.dedicated_subroute"
_DEDICATED_READ_METHODS: tuple[str, ...] = ("GET", "HEAD")
_DEDICATED_WRITE_METHODS: tuple[str, ...] = ("POST", "PUT", "PATCH")
_DEDICATED_READ_ACTION = "dedicated_read"
_DEDICATED_WRITE_ACTION = "dedicated_write"
_DEDICATED_DELETE_ACTION = "dedicated_delete"


def _entry(
    user_class: str,
    access_kind: str,
    entrypoint: str,
    method: str | None,
    action: str,
    access_mode: AccessMode,
    source: str = NONE_STATE,
    target: str = NONE_STATE,
    route: str | None = None,
) -> MatrixEntry:
    return MatrixEntry(
        key=MatrixKey(
            user_class=user_class,
            access_kind=access_kind,
            identity=IDENTITY_BY_KIND[access_kind],
            entrypoint=entrypoint,
            route=route,
            method=method,
            action=action,
            source_state=source,
            target_state=target,
        ),
        access_mode=access_mode,
    )


def _build_entries() -> tuple[frozenset[MatrixEntry], frozenset[MatrixKey]]:
    """展开全部完整允许项与 Review_Whitelist 键集合。"""
    entries: set[MatrixEntry] = set()
    review_whitelist: set[MatrixKey] = set()

    # full-power access_kind（scope 内整稿全动作）：admin/supervisor_scope/lead。
    # 各自的 user_class：admin→admin；supervisor_scope→supervisor；lead 可属 supervisor 或 restricted。
    full_power: tuple[tuple[str, str], ...] = (
        (UC_ADMIN, AK_ADMIN),
        (UC_SUPERVISOR, AK_SUPERVISOR_SCOPE),
        (UC_SUPERVISOR, AK_LEAD),
        (UC_RESTRICTED, AK_LEAD),
    )
    for uc, ak in full_power:
        for ep, method, action in _READ_FAMILIES:
            entries.add(_entry(uc, ak, ep, method, action, "read"))
        for ep, method, action in _CONTENT_MUTATION_FAMILIES:
            entries.add(_entry(uc, ak, ep, method, action, "mutation"))
        for ep, method, action in (
            _ASSOCIATE_FAMILY,
            _VERSION_RESTORE_FAMILY,
            _VERSION_SNAPSHOT_FAMILY,
            _EDITOR_WRITE_FAMILY,
        ):
            entries.add(_entry(uc, ak, ep, method, action, "mutation"))
        for src, tgt in _STATUS_TRANSITIONS:
            entries.add(
                _entry(uc, ak, "workpaper.status_transition", "POST",
                       "status_transition", "mutation", source=src, target=tgt)
            )
        # 试算表审定回写（whole-wp 审定数 → trial_balance）；POST/PUT 均登记。
        for _m in _TB_WRITEBACK_METHODS:
            entries.add(
                _entry(uc, ak, "workpaper.tb_writeback", _m, "tb_writeback", "mutation")
            )
        # lead/admin/supervisor_scope 也能发起全部 task 迁移（执行 + 复核侧）
        for src, tgt in (*_ASSIGNEE_TASK_TRANSITIONS, *_REVIEWER_TASK_TRANSITIONS):
            entries.add(
                _entry(uc, ak, "procedure.task_transition", "POST",
                       "task_transition", "mutation", source=src, target=tgt)
            )
        # 复核会话（读 + 评论）
        rep, rm, ra = _REVIEW_CONVERSATION_READ
        entries.add(_entry(uc, ak, rep, rm, ra, "read"))
        cep, cm, ca = _REVIEW_CONVERSATION_COMMENT
        entries.add(_entry(uc, ak, cep, cm, ca, "mutation"))
        # 专属组件 /{wp_id}/... 通用子路由（读/写/删）
        for _m in _DEDICATED_READ_METHODS:
            entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, _m,
                               _DEDICATED_READ_ACTION, "read"))
        for _m in _DEDICATED_WRITE_METHODS:
            entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, _m,
                               _DEDICATED_WRITE_ACTION, "mutation"))
        entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, "DELETE",
                           _DEDICATED_DELETE_ACTION, "mutation"))

    # assignee：读（映射 sheet）+ 内容写（映射 sheet）+ 执行侧 task 迁移；无 associate/restore/editor_write。
    for uc in (UC_SUPERVISOR, UC_RESTRICTED):
        ak = AK_ASSIGNEE
        for ep, method, action in _READ_FAMILIES:
            entries.add(_entry(uc, ak, ep, method, action, "read"))
        for ep, method, action in _CONTENT_MUTATION_FAMILIES:
            entries.add(_entry(uc, ak, ep, method, action, "mutation"))
        for src, tgt in _ASSIGNEE_TASK_TRANSITIONS:
            entries.add(
                _entry(uc, ak, "procedure.task_transition", "POST",
                       "task_transition", "mutation", source=src, target=tgt)
            )
        # 专属组件 /{wp_id}/... 通用子路由：assignee 在映射 sheet 上可读可写（整稿读/写由 grant 页面覆盖裁剪）。
        for _m in _DEDICATED_READ_METHODS:
            entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, _m,
                               _DEDICATED_READ_ACTION, "read"))
        for _m in _DEDICATED_WRITE_METHODS:
            entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, _m,
                               _DEDICATED_WRITE_ACTION, "mutation"))
        entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, "DELETE",
                           _DEDICATED_DELETE_ACTION, "mutation"))

    # reviewer：读（复核 sheet）+ Review_Whitelist 写（复核迁移 + 会话评论）。
    for uc in (UC_SUPERVISOR, UC_RESTRICTED):
        ak = AK_REVIEWER
        for ep, method, action in _READ_FAMILIES:
            entries.add(_entry(uc, ak, ep, method, action, "read"))
        # 复核迁移（submitted→reviewed / submitted→changes_requested）
        for src, tgt in _REVIEWER_TASK_TRANSITIONS:
            e = _entry(uc, ak, "review.transition", "POST", "review_transition",
                       "mutation", source=src, target=tgt)
            entries.add(e)
            review_whitelist.add(e.key)
        # 复核会话读 + 评论（同 task/sheet）
        rep, rm, ra = _REVIEW_CONVERSATION_READ
        er = _entry(uc, ak, rep, rm, ra, "read")
        entries.add(er)
        review_whitelist.add(er.key)
        cep, cm, ca = _REVIEW_CONVERSATION_COMMENT
        ec = _entry(uc, ak, cep, cm, ca, "mutation")
        entries.add(ec)
        review_whitelist.add(ec.key)
        # 专属组件 /{wp_id}/... 通用子路由：reviewer 仅只读（写动作走 Review_Whitelist，非本族）。
        for _m in _DEDICATED_READ_METHODS:
            entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, _m,
                               _DEDICATED_READ_ACTION, "read"))

    # lead_history / row_history：只读 Current_Version（Req 5.12–5.14），仅读族条目。
    for uc in (UC_SUPERVISOR, UC_RESTRICTED):
        for ak in (AK_LEAD_HISTORY, AK_ROW_HISTORY):
            for ep, method, action in _READ_FAMILIES:
                entries.add(_entry(uc, ak, ep, method, action, "read"))
            # 专属组件 /{wp_id}/... 通用子路由：History_Only 仅读 Current_Version（写/删被拒）。
            for _m in _DEDICATED_READ_METHODS:
                entries.add(_entry(uc, ak, _DEDICATED_ENTRYPOINT, _m,
                                   _DEDICATED_READ_ACTION, "read"))

    return frozenset(entries), frozenset(review_whitelist)


_ENTRIES, _REVIEW_WHITELIST = _build_entries()
# 精确键 → 条目（含 route）；族键 → 条目（route=None）。
_BY_KEY: dict[MatrixKey, MatrixEntry] = {e.key: e for e in _ENTRIES}


class ActionMatrix:
    """唯一服务端授权矩阵（完整允许项 + Review_Whitelist）。纯查表、无副作用、data-driven。"""

    # 供 Route_Drift_Guard / 测试静态读取的不可变全集。
    entries: frozenset[MatrixEntry] = _ENTRIES
    review_whitelist: frozenset[MatrixKey] = _REVIEW_WHITELIST

    @classmethod
    def lookup(cls, key: MatrixKey) -> MatrixEntry | None:
        """精确九维匹配（含 route）；未命中回退到同键 ``route=None`` 的 entrypoint 族条目。

        其余八维恒精确相等；未登记任一维度 → 返回 None（默认拒绝，Req 7.3/7.4）。
        """
        hit = _BY_KEY.get(key)
        if hit is not None:
            return hit
        if key.route is not None:
            family_key = MatrixKey(
                user_class=key.user_class,
                access_kind=key.access_kind,
                identity=key.identity,
                entrypoint=key.entrypoint,
                route=None,
                method=key.method,
                action=key.action,
                source_state=key.source_state,
                target_state=key.target_state,
            )
            return _BY_KEY.get(family_key)
        return None

    @classmethod
    def is_allowed(cls, key: MatrixKey) -> bool:
        """九维是否命中一个完整允许项（Req 7.2）。"""
        return cls.lookup(key) is not None

    @classmethod
    def is_review_whitelisted(cls, key: MatrixKey) -> bool:
        """该键是否命中 Review_Whitelist 完整条目（Req 7.5）。"""
        if key in cls.review_whitelist:
            return True
        if key.route is not None:
            family_key = MatrixKey(
                user_class=key.user_class,
                access_kind=key.access_kind,
                identity=key.identity,
                entrypoint=key.entrypoint,
                route=None,
                method=key.method,
                action=key.action,
                source_state=key.source_state,
                target_state=key.target_state,
            )
            return family_key in cls.review_whitelist
        return False
