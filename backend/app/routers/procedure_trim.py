"""程序行两层裁剪与方案 preview/apply API（Task 6）

Feature: procedure-delegation-notification
需求：3.3-3.8、4.2-4.6 / Design C4、D4、API section

端点（全部挂 **项目级 Delegator 守卫** `require_project_delegator_pid`，fail-closed 403）：
- ``POST /api/projects/{pid}/procedure-trim/preview``：方案预览 + 一次性 preview 凭证。
- ``POST /api/projects/{pid}/procedure-trim/apply``：消费 preview，经 TransitionService 真实应用；
  返回真实 applied/unchanged/conflict；legacy UUID 无法唯一转换 → 409 migration_conflict。
- ``POST /api/projects/{pid}/procedure-trim/schemes``：保存 canonical key + revision + 文本快照方案。
- ``POST /api/projects/{pid}/procedure-trim/rows/{task_id}/not-applicable``：细裁 → cancel。
- ``POST /api/projects/{pid}/procedure-trim/rows/{task_id}/restore``：细裁恢复 → reopen（须重新 assign→ack）。
- ``GET  /api/projects/{pid}/procedure-trim/note-linkage``：附注反向联动**只读**预览（Task 21）。
- ``POST /api/projects/{pid}/procedure-trim/note-linkage/apply``：应用联动，**只写**
  ``disclosure_notes.is_empty`` + provenance 面包屑（不新建不适用字段、不删章节）。

约定：service 只 flush；router 显式 commit。均为显式 POST 写命令，非 GET/render 读路径。
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.services.procedure_authorization import (
    DelegatorContext,
    require_project_delegator_pid,
)
from app.services.procedure_trim_service import ProcedureTrimService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["procedure-row-tasks"])


class TrimSchemeEntry(BaseModel):
    kind: str  # "scope" | "row"
    # scope
    cycle: str | None = None
    wp_index_code: str | None = None
    target_status: str | None = None
    # 粗裁理由（审计轨迹；execute 时忽略）。旧 PUT /procedures/{cycle}/trim 下线后由此承载。
    skip_reason: str | None = Field(default=None, max_length=500)
    # 粗裁结构化理由码（Task 12，additive）。
    #
    # 与 `skip_reason` 并列、随**同一次**请求提交，由 service 在同一事务里写
    # `procedure_instances.suggestion_state.reason_code`。
    #
    # 🔴 为什么不能「先 apply 状态、再补写理由码」：apply 消费的是**一次性** preview
    #    凭证，第二次写入没有凭证可用；且两次写入之间存在「状态已改、理由码未写」的
    #    中间态，正是要消除的不可追溯状态。
    # 🔴 为什么不编码进 `skip_reason` 文本：那样聚合仍要靠字符串解析，与改造前
    #    自由文本等价，等于没做。
    # 🔴 不传时请求 payload 与写入行为**逐字节不变**（存量调用方零影响，见守卫
    #    `test_trim_reason_codes.py::TestAdditiveZeroRegression`）。
    reason_code: str | None = Field(default=None, max_length=50)
    # row
    template_code: str | None = None
    sheet_key: str | None = None
    definition_key: str | None = None
    target_applicability: str | None = None


class TrimPreviewRequest(BaseModel):
    entries: list[TrimSchemeEntry] = Field(default_factory=list)
    scheme_id: UUID | None = None


class TrimApplyRequest(TrimPreviewRequest):
    preview_id: UUID
    request_id: str


class TrimSchemeSaveRequest(BaseModel):
    scheme_name: str
    audit_cycle: str
    entries: list[TrimSchemeEntry] = Field(default_factory=list)


class RowTrimRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    request_id: str | None = None


class RowRestoreRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    request_id: str | None = None


class SuggestionRejectRequest(BaseModel):
    """驳回系统裁剪建议（procedure-trimming-and-delegation-intelligence Task 13 / R6.4）。

    驳回**不改变**程序适用性状态，只在 ``suggestion_state`` 上留一个「已驳回」标记；
    决策内核见该标记后恒判 keep，不再重复提示同一条建议。

    🔴 为什么必须新建端点而不是复用 canonical trim apply：canonical trim 的语义是
    「改适用性状态」，而驳回恰恰是**不改状态**。若借它落理由，会把「审计师认为该
    程序应当保留」写成一次状态变更，在历史里留下一条不存在的裁剪动作。
    """

    # 🔴 字段名必须与前端 `commonApi.rejectTrimSuggestions` 的请求体键、以及
    #    `ProcedureTrimService.reject_suggestions` 的形参名**三处一致**。
    #    此前三处写了两个名字（模型 `wp_codes` / 前端与服务 `wp_index_codes`），
    #    两个后果都不报错在编译期：① pydantic 默认忽略未知键 ⇒ 前端传的
    #    `wp_index_codes` 被丢掉、`wp_codes` 取默认空列表 ⇒ 驳回恒 0 条；
    #    ② router 用 `wp_codes=` 调服务 ⇒ 运行时 TypeError → 500。
    #    守卫 `test_completeness_scope_override.py::TestRouterServiceKwargAgreement`
    #    按 AST 比对 router 每个 `svc.*()` 调用的关键字与服务形参，钉死这类错配。
    wp_index_codes: list[str] = Field(default_factory=list, max_length=500)
    cycle: str = Field(min_length=1, max_length=20)
    reason: str | None = Field(default=None, max_length=500)


class CompletenessScopeOverrideRequest(BaseModel):
    """完整性敏感清单的项目级覆盖（Task 14 / R5.5、R5.6）。

    落 ``checklist_responses`` 的 ``B50-T3-cscope-{cycle}``：``conclusion`` 存
    ``Y``/``N``、``remark`` 存覆盖理由。理由必填 —— 覆盖平台默认清单是一项要向
    质控与项目质量控制复核人解释的判断，无理由的覆盖在复核时无法评价其适当性。
    """

    cycle: str = Field(min_length=1, max_length=20)
    sensitive: bool
    reason: str = Field(min_length=1, max_length=500)


class NoteLinkageApplyRequest(BaseModel):
    """附注反向联动的应用请求（Task 21 / R13.1~R13.3）。

    只有 ``year`` 一个字段：标注**哪些**章节由后端按 ``procedure_instances`` 现状
    与 section→wp 映射当场派生，不由前端传清单。

    🔴 为什么不让前端传章节清单：那会产生第二份判定口径 —— 前端传来的清单与后端
    当下的裁剪状态可能已不一致（并发会话改了裁剪），照单执行就会把「已恢复执行」的
    循环对应章节标成不适用。派生式还天然幂等，可反复调用。
    """

    year: int = Field(ge=1900, le=2999)


def _entries_payload(entries: list[TrimSchemeEntry]) -> list[dict]:
    return [e.model_dump(exclude_none=True) for e in entries]


@router.post("/{pid}/procedure-trim/preview")
async def trim_preview(
    pid: UUID,
    body: TrimPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """方案预览：解析计划 + 一次性 preview 凭证。"""
    svc = ProcedureTrimService(db)
    result = await svc.preview_scheme(
        pid,
        actor_user_id=user.id,
        entries=_entries_payload(body.entries) if body.entries else None,
        scheme_id=body.scheme_id,
    )
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/apply")
async def trim_apply(
    pid: UUID,
    body: TrimApplyRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """方案应用：消费 preview，真实 applied/unchanged/conflict；legacy UUID 无法唯一转换 → 409。"""
    svc = ProcedureTrimService(db)
    try:
        result = await svc.apply_scheme(
            pid,
            actor_user_id=user.id,
            preview_id=body.preview_id,
            request_id=body.request_id,
            entries=_entries_payload(body.entries) if body.entries else None,
            scheme_id=body.scheme_id,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/schemes")
async def trim_save_scheme(
    pid: UUID,
    body: TrimSchemeSaveRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """保存裁剪方案（canonical key + revision + 文本快照）。"""
    svc = ProcedureTrimService(db)
    result = await svc.save_scheme(
        pid,
        scheme_name=body.scheme_name,
        audit_cycle=body.audit_cycle,
        entries=_entries_payload(body.entries),
        created_by=user.id,
    )
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/rows/{task_id}/not-applicable")
async def trim_row_not_applicable(
    pid: UUID,
    task_id: UUID,
    body: RowTrimRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """细裁 → not_applicable：经 TransitionService cancel（applicability→not_applicable + workflow→cancelled）。"""
    svc = ProcedureTrimService(db)
    try:
        result = await svc.set_row_not_applicable(
            pid,
            task_id,
            actor_user_id=user.id,
            reason=body.reason,
            request_id=body.request_id,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/suggestions/reject")
async def trim_reject_suggestions(
    pid: UUID,
    body: SuggestionRejectRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """驳回裁剪建议：只写 ``suggestion_state.rejected``，**不改适用性状态**（R6.4）。

    驳回后决策内核恒判 keep，同一条建议不再重复出现。
    """
    svc = ProcedureTrimService(db)
    try:
        result = await svc.reject_suggestions(
            pid,
            cycle=body.cycle,
            wp_index_codes=body.wp_index_codes,
            actor_user_id=user.id,
            reason=body.reason,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.get("/{pid}/procedure-trim/completeness-scope")
async def trim_list_completeness_scope(
    pid: UUID,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """读回本项目完整性敏感清单的项目级覆盖（含理由与最后修改留痕）。

    未出现在返回列表里的循环 = 未覆盖 ⇒ 前端退回平台默认清单
    （``completenessExemption.COMPLETENESS_CYCLE_RULES``）并标注「使用平台默认，
    未经本项目确认」（R5.6）。
    """
    svc = ProcedureTrimService(db)
    return await svc.list_completeness_scope_overrides(pid)


@router.put("/{pid}/procedure-trim/completeness-scope")
async def trim_set_completeness_scope(
    pid: UUID,
    body: CompletenessScopeOverrideRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """写一条完整性敏感清单的项目级覆盖（``Y``/``N`` 都算已表态）。

    🔴 只写 ``B50-T3-cscope-{cycle}`` 这一个 item_id，绝不触碰 B50 的矩阵 /
    cycle / plan 三类键 —— 守卫另有一条断言「cscope 行不改变
    ``load_b50_accounts()`` 的任何输出」。
    """
    svc = ProcedureTrimService(db)
    try:
        result = await svc.set_completeness_scope_override(
            pid,
            cycle=body.cycle,
            sensitive=body.sensitive,
            actor_user_id=user.id,
            reason=body.reason,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.delete("/{pid}/procedure-trim/completeness-scope/{cycle}")
async def trim_clear_completeness_scope(
    pid: UUID,
    cycle: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """撤销某循环的项目级覆盖 → 该循环退回平台默认清单。

    删行而不是写空串：读取侧以「该循环是否出现在 dict 里」区分「已表态」与
    「未覆盖」，留一行空 ``conclusion`` 会让两态都表现为未覆盖却多一条脏记录。
    """
    svc = ProcedureTrimService(db)
    try:
        result = await svc.clear_completeness_scope_override(pid, cycle=cycle)
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.get("/{pid}/procedure-trim/note-linkage")
async def trim_note_linkage_preview(
    pid: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """只读预览：本次程序裁剪会把哪些附注章节标为本期不适用 / 撤销 / 只提示（R13.1）。

    🔴 ``year`` 是**必需**查询参数：``procedure_instances`` 没有 year 列，而
    ``disclosure_notes`` 按 ``(project, year, note_section)`` 唯一 —— 缺 year 就定位不到
    章节行，会让整份联动静默返回空（表现为"这个项目没有可标注的章节"）。
    """
    from app.services.procedure_trim_note_linkage import preview_note_linkage

    return await preview_note_linkage(db, pid, year)


@router.post("/{pid}/procedure-trim/note-linkage/apply")
async def trim_note_linkage_apply(
    pid: UUID,
    body: NoteLinkageApplyRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """应用联动：**只写** ``disclosure_notes.is_empty`` + provenance 面包屑。

    🔴 不新建"不适用"字段、不删除章节、不动 ``table_data`` / ``text_content``：附注侧
    已有的 ``is_empty`` + ``note_content_utils.note_has_data`` 就是唯一真源，另建一套
    会让附注树标记与 Word 导出结果漂移。
    """
    from app.services.procedure_trim_note_linkage import apply_note_linkage

    try:
        result = await apply_note_linkage(db, pid, body.year, actor_user_id=user.id)
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result


@router.post("/{pid}/procedure-trim/rows/{task_id}/restore")
async def trim_row_restore(
    pid: UUID,
    task_id: UUID,
    body: RowRestoreRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
    _guard: DelegatorContext = Depends(require_project_delegator_pid),
):
    """细裁恢复 → execute：经 TransitionService reopen（cancelled→unassigned，须重新 assign→ack）。"""
    svc = ProcedureTrimService(db)
    try:
        result = await svc.restore_row_execute(
            pid,
            task_id,
            actor_user_id=user.id,
            request_id=body.request_id,
            reason=body.reason,
        )
    except Exception:
        await db.rollback()
        raise
    await db.commit()
    return result
