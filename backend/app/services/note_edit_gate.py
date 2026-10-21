"""附注编辑门禁 —— 覆盖集合内附注写端点对目标项目唯一的项目级判定（partner-manager-edit-permission design §4.6、D1、D13）。

判定实现只有一份 ``assert_note_edit_access``，三种挂载形态都调用它（需求 6.1）：

- 路径依赖 ``require_note_edit_access(consol_lock=...)``：路径含 ``{project_id}`` 的端点挂在签名默认值里，依赖返回当前用户。
- 函数体 ``assert_note_edit_access(db, current_user, project_id, consol_lock=...)``：项目在请求体里（或沿用函数体写法）的端点，
  在条件分支与异常处理之外、先于一切业务调用执行。
- 对象反查 ``assert_note_edit_access_for_object(...)``：路径上只有对象 id 的端点。先只取对象所属项目一列，对象不存在返回 404，
  再对该项目调判定实现；签名里没有项目参数，调用方另附的项目标识不改变目标项目（需求 6.8）。

design 定级形态（只给 design §4.8 表 B 声明的端点用；清册把它们识别为独立门禁形态，不计入「挂载附注编辑门禁」）同样调用判定实现：
- 多项目 ``assert_note_edit_access_on_projects(...)``：请求涉及的每个项目各判一次，任一不通过即整单拒绝（需求 8.5）。
- 角色限定 ``assert_note_role_access(...)``：判定实现放行后，非 admin 的成员行项目角色还须属于声明的集合（需求 8.3）。

判定顺序（需求 6.1、6.13）：前一步拒绝即不再往下判，各步针对同一目标项目。
  ① 项目已归档 → 423 ``PROJECT_ARCHIVED``「项目已归档，无法编辑」，对任何调用者（含 admin、非成员与 EQCR，需求 6.7）
  ② 非 admin，且没有未删除成员行或级别为 readonly → 403「权限不足」（需求 6.4）
     ①② 都由 ``assert_project_permission(..., NOTE_EDIT_MIN_LEVEL)`` 给出，文案沿用其现有固定文本。
  ③ ``is_project_eqcr`` 判为本项目 EQCR（admin 不豁免）→ 403 ``NOTE_EDIT_EQCR_READONLY``（需求 6.5、7.1）
  ④ 非 admin，「全局角色 ∪ 成员行项目角色」的操作权限不含 ``note:edit`` → 403 ``NOTE_EDIT_OPERATION_DENIED``（需求 6.12）
  ⑤ 仅 ``consol_lock=True``：项目合并锁定 → 423「项目已被合并锁定，无法修改」（沿用 ``check_consol_lock``，需求 6.6）
  以上都不成立即放行，返回当前用户：业务以调用者本人为操作人（需求 6.2、6.3）。

``consol_lock`` 是必填关键字参数，调用处以字面量写明（清册据此静态读出是否判合并锁，需求 1.8、6.6）；不是 bool 即报错。
三种挂载形态与角色限定形态对判定实现的调用都位于函数体顶层语句序列（不在 if / try / 循环内）。多项目形态按 design 逐项目调用，
调用在 for / try 内：去重后的每个项目都判（循环里没有 if / break / continue），except 只收 403 / 423，其余原样再抛。

出错语义（需求 6.11、7.6）：任一步的查询出错都原样冒泡 —— 请求失败，业务一次也不执行，不按放行处理。模块里唯一的 ``try``
在多项目形态：只接住判定实现给出的 403 / 423 拒绝（``HTTPException``）用于收集，其余异常原样再抛。

拒绝原因（D13）：拒绝文案集中为下面的模块常量；``note_edit_rejection_reason`` 从拒绝异常取中文原因，门禁与附注可编辑
判定查询共用，判定查询给出的原因与写请求的拒绝原因逐字相同（需求 10.1）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app import deps
from app.core.database import get_db
from app.deps import assert_project_permission, check_consol_lock, get_current_user
from app.models.base import ProjectUserRole, UserRole
from app.models.core import User
from app.services.eqcr_resolver import is_project_eqcr
from app.services.permission_matrix_service import can

#: 项目级别下限：本项目 review 及以上成员可写（用户指令「逐个放开到复核级」，需求 6.2）
NOTE_EDIT_MIN_LEVEL = "review"
#: 操作矩阵权限点（需求 6.12；矩阵内容不改，Q1）
NOTE_EDIT_OPERATION = "note:edit"
#: ② 的拒绝文案：``assert_project_permission`` 的现有固定文本，本模块不另行抛出，供判定查询与测试对拍
REASON_FORBIDDEN = "权限不足"
#: ③ 的拒绝文案（需求 6.5）
REASON_EQCR_READONLY = "独立复核合伙人（EQCR）在本项目只读，不能编辑附注"
#: ④ 的拒绝文案（需求 6.12）
REASON_OPERATION_DENIED = "您在本项目的角色没有编辑附注的操作权限"
#: 多项目形态拒绝文案的前缀，其后逐个列出未通过的项目 id 及其单独判定的原因（需求 8.5）
REASON_MULTI_PROJECT_DENIED_PREFIX = "以下项目未通过附注编辑权限判定："

#: 多项目形态收集的单项目拒绝：403（权限不足 / EQCR 只读 / 操作矩阵）与 423（归档 / 合并锁）；其他异常原样冒泡
_MULTI_PROJECT_COLLECTED_STATUSES = frozenset({403, 423})
#: 角色限定形态 ``project_roles`` 的合法成员：成员行项目角色的全部取值
_PROJECT_ROLE_VALUES = frozenset(role.value for role in ProjectUserRole)


def _require_bool_consol_lock(consol_lock: object, *, caller: str) -> None:
    """``consol_lock`` 只收 True / False（fail-closed）：写成 None、0 或字符串会让合并锁判定被静默跳过或误判。"""
    if not isinstance(consol_lock, bool):
        raise TypeError(f"{caller} 的 consol_lock 须为 True 或 False，收到 {consol_lock!r}")


async def _resolve_project_role(db: AsyncSession, user_id: UUID, project_id: UUID) -> str | None:
    """用户在项目的未删除成员行的项目角色（字符串取值），没有成员行返回 None。操作矩阵判定（④）的下层取数点。

    查询用 ``require_operation`` 所用的同一函数 ``app.deps._resolve_project_role``，经模块属性调用：
    矩阵口径与 ``require_operation("note:edit")`` 不分叉；替换或故障注入落在本函数或 deps 那一层都生效。
    """
    return await deps._resolve_project_role(db, user_id, project_id)


async def assert_note_edit_access(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
    *,
    consol_lock: bool,
) -> User:
    """附注编辑门禁的判定实现（唯一一份）：放行返回当前用户，拒绝抛 ``HTTPException``（顺序见模块说明）。"""
    _require_bool_consol_lock(consol_lock, caller="assert_note_edit_access")
    # ① 归档 423 → ② 成员 review 及以上，否则 403「权限不足」（admin 跳过 ②、不跳过 ①）
    await assert_project_permission(db, current_user, project_id, NOTE_EDIT_MIN_LEVEL)
    # ③ 本项目 EQCR：admin 不豁免；判定出错原样冒泡，不按「非 EQCR」放行（需求 7.6）
    is_eqcr = await is_project_eqcr(db, current_user, project_id)
    if is_eqcr:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "NOTE_EDIT_EQCR_READONLY", "message": REASON_EQCR_READONLY},
        )
    # ④ 操作矩阵（全局角色 ∪ 成员行项目角色的并集口径）：admin 恒放行，不查项目角色
    if current_user.role.value != UserRole.admin.value:
        project_role = await _resolve_project_role(db, current_user.id, project_id)
        if not can(current_user.role.value, project_role, NOTE_EDIT_OPERATION):
            raise HTTPException(
                status_code=403,
                detail={"error_code": "NOTE_EDIT_OPERATION_DENIED", "message": REASON_OPERATION_DENIED},
            )
    # ⑤ 合并锁：只对合并锁适用集合（调用处写 consol_lock=True）
    if consol_lock:
        await check_consol_lock(project_id=project_id, db=db)
    return current_user


def require_note_edit_access(*, consol_lock: bool) -> Callable[..., Awaitable[User]]:
    """路径依赖形态：端点签名写 ``current_user: User = Depends(require_note_edit_access(consol_lock=...))``。

    ``consol_lock`` 在工厂调用期（= 模块导入期）即校验。只用于路径含 ``{project_id}`` 的端点：路径上没有它时，
    FastAPI 会把 ``project_id`` 变成必填查询参数，门禁校验的就成了调用方自选的项目 —— 那类端点改用函数体或对象反查形态。
    """
    _require_bool_consol_lock(consol_lock, caller="require_note_edit_access")

    async def dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        await assert_note_edit_access(db, current_user, project_id, consol_lock=consol_lock)
        return current_user

    return dependency


async def assert_note_edit_access_for_object(
    db: AsyncSession,
    current_user: User,
    *,
    id_column: InstrumentedAttribute[Any],
    project_column: InstrumentedAttribute[Any],
    object_id: UUID,
    not_found_detail: str,
    consol_lock: bool,
) -> UUID:
    """对象反查形态：只取对象所属项目一列 → 对象不存在 404 ``not_found_detail`` → 对该项目调判定实现；返回该项目 id。

    唯一的那条最小投影查询封装在这里、排在判定之前，端点体内门禁之前 0 次读（需求 6.1、6.8）。目标项目只取自对象本身：
    签名里没有项目参数，调用方在查询参数或请求体里另附的项目标识不参与判定。对象不存在时不进入任何判定
    （与 ``disclosure_notes._assert_object_project_access`` 的反查语义相同）。
    """
    _require_bool_consol_lock(consol_lock, caller="assert_note_edit_access_for_object")
    project_id = (await db.execute(select(project_column).where(id_column == object_id))).scalar_one_or_none()
    if project_id is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    await assert_note_edit_access(db, current_user, project_id, consol_lock=consol_lock)
    return project_id


def note_edit_rejection_reason(exc: HTTPException) -> str:
    """门禁拒绝异常的中文原因（D13）：``detail`` 是字符串原样返回，是 dict 取 ``message``。

    门禁的拒绝都落在这两种形态里：②「权限不足」与 ⑤ 合并锁是字符串，① 归档与 ③ ④ 是带 ``message`` 的 dict。
    其他形态给不出原因，报错而不猜 —— 判定查询随之失败，不会给出没有原因的「不能编辑」。
    """
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict) and isinstance(detail.get("message"), str):
        return detail["message"]
    raise ValueError(f"无法从拒绝响应取出原因：状态码 {exc.status_code}，detail 类型 {type(detail).__name__}")


# ─── design 定级形态（design §4.6、§4.8 表 B） ──────────────────────────────


async def assert_note_edit_access_on_projects(
    db: AsyncSession,
    current_user: User,
    project_ids: Iterable[UUID],
    *,
    consol_lock: bool,
) -> User:
    """多项目形态（需求 8.5）：请求涉及的每个项目都调一次判定实现，任一项目不通过即整单拒绝；放行返回当前用户。

    - 去重保序后逐项目判定；某项目得 403 / 423 时记下、接着判下一个项目，全部判完才下结论。其他异常（查询出错、
      其他状态码的 ``HTTPException`` 等）原样冒泡，不并入整单拒绝，后面的项目也不再判。
    - 有项目未通过：其中有 403 即 403，否则 423；detail 为 ``NOTE_EDIT_MULTI_PROJECT_DENIED``、中文 ``message``（逐个列出未通过的
      项目 id 及其单独判定的原因）与 ``project_ids``（未通过的项目 id，按判定先后）。拒绝时不重设 RLS 上下文。
    - 全部通过：判定实现逐项目设置 RLS 上下文，最后一次落在末个项目；这里经同一个 ``deps.set_rls_context`` 重设为首个项目
      （design N14 / R14：附注表无 RLS，只为结果可预期）。
    - 参数 fail-closed（任何读库之前）：没有项目即报错（一个项目都不判就放行等于没有门禁）；项目须为 ``UUID``（去重按 UUID 取值，
      误把单个 id 字符串当序列传入时不会按字符逐个判定）。
    """
    _require_bool_consol_lock(consol_lock, caller="assert_note_edit_access_on_projects")
    ordered = list(dict.fromkeys(project_ids))
    if not ordered:
        raise ValueError("assert_note_edit_access_on_projects 至少需要一个项目：一个项目都不判就放行等于没有门禁")
    if not all(isinstance(project_id, UUID) for project_id in ordered):
        kinds = sorted({type(project_id).__name__ for project_id in ordered})
        raise TypeError(f"assert_note_edit_access_on_projects 的项目须为 UUID，收到 {kinds}")
    denied: list[tuple[UUID, HTTPException]] = []
    for project_id in ordered:
        try:
            await assert_note_edit_access(db, current_user, project_id, consol_lock=consol_lock)
        except HTTPException as exc:
            if exc.status_code not in _MULTI_PROJECT_COLLECTED_STATUSES:
                raise
            denied.append((project_id, exc))
    if denied:
        status_code = 403 if any(exc.status_code == 403 for _project_id, exc in denied) else 423
        listed = "、".join(f"{project_id}（{note_edit_rejection_reason(exc)}）" for project_id, exc in denied)
        raise HTTPException(
            status_code=status_code,
            detail={
                "error_code": "NOTE_EDIT_MULTI_PROJECT_DENIED",
                "message": REASON_MULTI_PROJECT_DENIED_PREFIX + listed,
                "project_ids": [str(project_id) for project_id, _exc in denied],
            },
        )
    await deps.set_rls_context(db, ordered[0])
    return current_user


def _require_role_parameters(project_roles: object, denied_message: object) -> None:
    """角色限定形态的参数校验（fail-closed，在任何读库之前）。

    ``project_roles`` 须为 ``frozenset``，成员都是成员行项目角色的取值：拼错的角色名永远匹配不上，会让角色限定静默变成
    「仅 admin」；误传字符串则会按子串判定（``"qc" in "eqcr"`` 为真）。``denied_message`` 须为非空字符串：拒绝要给出
    中文原因（需求 10.7）。
    """
    if not isinstance(project_roles, frozenset):
        raise TypeError(f"assert_note_role_access 的 project_roles 须为 frozenset，收到 {type(project_roles).__name__}")
    unknown = sorted(repr(role) for role in project_roles if role not in _PROJECT_ROLE_VALUES)
    if unknown:
        raise ValueError(
            f"assert_note_role_access 的 project_roles 含未登记的项目角色 {'、'.join(unknown)}；"
            f"合法值：{'、'.join(sorted(_PROJECT_ROLE_VALUES))}"
        )
    if not isinstance(denied_message, str) or not denied_message.strip():
        raise ValueError(f"assert_note_role_access 的 denied_message 须为非空的中文拒绝原因，收到 {denied_message!r}")


async def assert_note_role_access(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
    *,
    project_roles: frozenset[str],
    denied_message: str,
) -> User:
    """角色限定形态（需求 8.3；design §4.8 表 B）：先过判定实现，再判成员行项目角色；放行返回当前用户。

    - 判定实现在前，``consol_lock=False``（用这一形态的端点改造前只校验登录，新纳入的端点一律不判合并锁，需求 6.6）：
      归档 423、「权限不足」、EQCR 只读（admin 不豁免）、操作矩阵的拒绝都先于角色判定给出。
    - admin 放行；否则未删除成员行的项目角色须属于 ``project_roles``，不属于 → 403 ``NOTE_ROLE_REQUIRED``，``message`` 为调用方
      声明的 ``denied_message``。``project_roles`` 为空集即仅 admin。
    - 项目角色与操作矩阵一步同一取数（``_resolve_project_role``），非 admin 放行时共两次点查。
    """
    _require_role_parameters(project_roles, denied_message)
    await assert_note_edit_access(db, current_user, project_id, consol_lock=False)
    if current_user.role.value == UserRole.admin.value:
        return current_user
    project_role = await _resolve_project_role(db, current_user.id, project_id)
    if project_role not in project_roles:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "NOTE_ROLE_REQUIRED", "message": denied_message},
        )
    return current_user
