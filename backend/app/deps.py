"""依赖注入 — get_current_user, require_role, require_project_access, require_operation

Validates: Requirements 3.7, 3.8, 3.9, 3.10
"""

import logging
from collections.abc import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, set_rls_context
from app.core.redis import get_redis
from app.core.security import decode_token

# Alias for routers that use "db" as the Depends name
db = get_db

# Alias for sync routers (consolidation module etc.) that use synchronous ORM
from app.core.database import get_sync_db  # noqa: E402
sync_db = get_sync_db

from app.models.core import Project, ProjectUser, User
from app.models.base import ProjectStatus

logger = logging.getLogger(__name__)

security = HTTPBearer()

# ---------------------------------------------------------------------------
# 权限层级常量
# ---------------------------------------------------------------------------

PERMISSION_HIERARCHY: dict[str, int] = {"edit": 3, "review": 2, "readonly": 1}


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 Authorization header 解析 JWT，查询用户，验证 is_active 和 is_deleted。

    包含 access token 黑名单检查（Redis 不可用时降级跳过）。
    未认证或 token 无效时返回 401。
    """
    token = credentials.credentials

    # 黑名单检查（Redis 不可用时降级跳过，不阻断请求）
    try:
        from app.core.redis import redis_client
        from app.services.auth_service import is_token_blacklisted
        if await is_token_blacklisted(token, redis_client):
            raise HTTPException(status_code=401, detail="Token 已被吊销")
    except HTTPException:
        raise
    except Exception:
        logger.debug("Redis unavailable for blacklist check, skipping")

    # Phase 14: SoD 角色变更黑名单检查
    # 角色变更后旧 token 在 5 秒内失效（Redis key: sod_revoke:{user_id}:{project_id}）
    # 注意：当前实现只检查全局撤销（sod_revoke:{user_id}），不检查项目级撤销
    # （sod_revoke:{user_id}:{project_id}）。如需项目级 SoD 检查，需在此处扩展。
    try:
        from app.core.redis import redis_client as _redis
        if _redis:
            # 从 token payload 提取 user_id，检查是否有 SoD 撤销标记
            _payload_pre = decode_token(token)
            _uid = _payload_pre.get("sub")
            if _uid:
                # 检查全局 SoD 撤销（不限项目）
                _sod_key = f"sod_revoke:{_uid}:*"
                # 简化实现：检查 sod_revoke:{user_id} 前缀
                _sod_global = await _redis.get(f"sod_revoke:{_uid}")
                if _sod_global:
                    raise HTTPException(status_code=403, detail={
                        "error_code": "SOD_TOKEN_REVOKED",
                        "message": "角色变更后 Token 已失效，请重新登录",
                    })
    except HTTPException:
        raise
    except Exception:
        pass  # Redis 不可用时降级跳过

    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    # 仅接受 access token
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    result = await db.execute(
        select(User).where(
            User.id == UUID(user_id),
            User.is_active == True,   # noqa: E712
            User.is_deleted == False,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")

    return user


# ---------------------------------------------------------------------------
# get_current_user_sse — SSE (EventSource) 鉴权：header 优先 + query token 回退
# ---------------------------------------------------------------------------


async def get_current_user_sse(
    request: Request,
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db, scope="function"),
) -> User:
    """SSE / EventSource 专用鉴权（acnr-invalidation-overlay-hardening R1.2/R3.1）。

    `EventSource` 无法设置 Authorization 头，故鉴权 token 经 query `?token=` 传递。
    优先读 Authorization header（普通 fetch/SSE polyfill），回退 query token（原生 EventSource）。
    复用 `get_current_user` 的完整校验（黑名单 / SoD / decode / 用户查库 / RLS），不重复实现。
    """
    raw: str | None = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        raw = auth_header[7:]
    elif token:
        raw = token

    if not raw:
        raise HTTPException(status_code=401, detail="未认证")

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=raw)
    return await get_current_user(credentials=creds, db=db)


# ---------------------------------------------------------------------------
# require_role
# ---------------------------------------------------------------------------


def require_role(allowed_roles: list[str]) -> Callable:
    """角色校验依赖工厂。

    用户角色不在 allowed_roles 列表中时返回 403 "权限不足"。
    """

    async def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return current_user

    return dependency


def assert_self_or_admin(current_user: User, user_id: UUID) -> None:
    """路径里的 ``user_id`` 只能是本人，admin 例外（私人库、改语言等「用户自己的数据」端点用）。"""
    role = getattr(getattr(current_user, "role", None), "value", None)
    if role != "admin" and str(current_user.id) != str(user_id):
        raise HTTPException(status_code=403, detail="只能操作自己的数据")


# ---------------------------------------------------------------------------
# _check_project_not_archived — 归档项目只读守卫
# ---------------------------------------------------------------------------


async def _check_project_not_archived(
    db: AsyncSession,
    project_id: UUID,
    current_user: User,
    min_permission: str,
) -> None:
    """归档项目只读守卫。

    - readonly 权限：跳过（允许只读查询）
    - editor / admin 权限：检查 project.status，archived 时抛 423
    """
    if min_permission == "readonly":
        return
    project = await db.get(Project, project_id)
    if project and project.status == ProjectStatus.archived:
        raise HTTPException(
            status_code=423,
            detail={
                "error_code": "PROJECT_ARCHIVED",
                "message": "项目已归档，无法编辑",
                "message_en": "Project archived (read-only)",
            },
        )


# ---------------------------------------------------------------------------
# require_project_access
# ---------------------------------------------------------------------------


def require_project_access(min_permission: str = "readonly") -> Callable:
    """项目级权限校验依赖工厂。

    - admin 角色跳过检查
    - 其余用户按本项目未删除成员行的级别判定（每次直接查库）
    - 权限不足返回 403

    ``min_permission`` 必须是 :data:`PERMISSION_HIERARCHY` 的键，**在工厂调用期即校验**
    （= 模块导入期，拼错直接启动失败）。

    为什么必须 fail-closed：下面比较用的是 ``PERMISSION_HIERARCHY.get(min_permission, 0)``
    —— 未登记的级别名会静默取到 **0**，于是 ``user_level < 0`` 恒为假，**任何项目成员
    （含 readonly）都能通过**，门禁形同不存在。实测曾有 4 个写端点因此被降级：
    ``disclosure_notes`` 的删除 / 状态更新 / 恢复三处写 ``"editor"``、
    ``wp_editor_router`` 的签署状态更新写 ``"member"`` —— 两个名字都不在登记表里。
    这类拼写错误不会有任何报错或日志，只有逐字符核对才发现，故改为导入期硬失败。
    """
    _validate_permission_level(min_permission, caller="require_project_access")

    async def dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        return await assert_project_permission(
            db, current_user, project_id, min_permission
        )

    return dependency


def _validate_permission_level(min_permission: str, *, caller: str) -> None:
    """校验权限级别名已登记，未登记即抛 ValueError（fail-closed）。"""
    if min_permission not in PERMISSION_HIERARCHY:
        raise ValueError(
            f"{caller} 收到未登记的权限级别 {min_permission!r}；"
            f"合法值：{sorted(PERMISSION_HIERARCHY)}。"
            "未登记的级别会被 PERMISSION_HIERARCHY.get(..., 0) 静默降级为 0，"
            "使门禁对任何项目成员放行。"
        )


async def assert_project_permission(
    db: AsyncSession,
    current_user: User,
    project_id: UUID,
    min_permission: str = "readonly",
) -> User:
    """项目级权限校验的**可直调**版本（与 ``require_project_access`` 同一实现）。

    ``require_project_access`` 是 FastAPI 依赖工厂，其内部依赖从**路径/查询参数**取
    ``project_id`` —— 对「project_id 在请求体里」或「只给了 note_id、需先反查所属项目」
    的端点用不上。那类端点必须在函数体首句显式调用本函数。

    两条路径共用同一实现，避免出现第二份权限判定（判定分叉必然漂移）。
    """
    _validate_permission_level(min_permission, caller="assert_project_permission")

    # 归档项目只读守卫（仅 non-readonly 权限触发）
    await _check_project_not_archived(db, project_id, current_user, min_permission)

    # admin 跳过项目权限检查（不设置 RLS context，admin 使用 bypass 函数）
    if current_user.role.value == "admin":
        # admin 仍设置 RLS context 以便普通查询正常工作
        # 跨项目聚合查询使用 SECURITY DEFINER 函数绕过
        await set_rls_context(db, project_id)
        return current_user

    required_level = PERMISSION_HIERARCHY[min_permission]

    # 查询 project_users 表（只取级别一列，每次直接查库）
    level_value = await _load_member_level(db, current_user.id, project_id)

    if level_value is None:
        raise HTTPException(status_code=403, detail="权限不足")

    if PERMISSION_HIERARCHY.get(level_value, 0) < required_level:
        raise HTTPException(status_code=403, detail="权限不足")

    # 设置 RLS context（SET LOCAL 仅当前事务有效）
    await set_rls_context(db, project_id)
    return current_user


# ---------------------------------------------------------------------------
# Fine-grained project permission
# ---------------------------------------------------------------------------


def require_project_permission(permission: str) -> Callable:
    """按项目成员级别和共享权限映射校验细粒度项目权限。

    先复用 ``assert_project_permission(..., "review")`` 保证项目成员、归档状态
    和 RLS 上下文正确，再用 project_permissions 的合并权限集合判断具体能力。
    """
    from app.services.project_permissions import ALL_PERMISSIONS

    if permission not in ALL_PERMISSIONS:
        raise ValueError(f"未登记的项目权限: {permission!r}")

    async def dependency(
        project_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.services.project_permissions import resolve_project_permissions

        user = await assert_project_permission(
            db, current_user, project_id, "review"
        )
        if current_user.role.value != "admin":
            permissions = await resolve_project_permissions(db, current_user, project_id)
            if permission not in permissions:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error_code": "PROJECT_PERMISSION_REQUIRED",
                        "permission": permission,
                    },
                )
        return user

    return dependency


# ---------------------------------------------------------------------------
# require_wp_edit_permission — 底稿编辑权门禁（Module_Refresh 用）
# ---------------------------------------------------------------------------


def require_wp_edit_permission() -> Callable:
    """底稿编辑权门禁（公式管理库 Req 20，Module_Refresh 用）。

    与 ``require_role`` 是**两条不同门禁**：本门禁按"对目标底稿具编辑权"放行，
    **不要求合伙人角色**，避免模块/循环级刷新（如 ``audit-sheet-refresh`` 逐底稿刷新）
    被锁死为合伙人专属；``require_role`` 则按系统角色判定（用于全局一键刷新的合伙人门禁）。

    判定口径（基于既有 ``permission_service.Permission.WORKPAPER_WRITE`` + 项目成员编辑权）：

    1. 角色须具 ``WORKPAPER_WRITE`` 能力（``permission_service`` 角色权限矩阵）——
       ``qc`` / ``readonly`` 无该能力 → 403。
    2. ``admin`` / ``partner`` 全局放行（矩阵含全集）。
    3. 其余角色（``manager`` / ``auditor``）须为目标底稿所属项目成员且具 ``edit`` 权
       （``project_users.permission_level >= edit``），否则 403（Req 20.2）。

    ``wp_id`` 从路径参数解析（route 形如 ``/{wp_id}/audit-sheet-refresh``）。所有校验在
    依赖解析阶段完成，**先于任何数据写入**（Req 20.2）。
    """

    async def dependency(
        wp_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        await authorize_wp_edit(db, current_user, wp_id)
        return current_user

    return dependency


async def authorize_wp_edit(db: AsyncSession, current_user: User, wp_id: UUID) -> UUID:
    """底稿编辑权校验（可复用；供路径依赖 require_wp_edit_permission 与 body-wp_id 端点调用）。

    判定口径同 require_wp_edit_permission：
    1. 角色须具 WORKPAPER_WRITE（qc/readonly → 403）。
    2. admin/partner 全局放行。
    3. 其余角色须为目标底稿所属项目成员且具 edit 权（project_users）。

    Returns:
        目标底稿所属 project_id（供调用方进一步校验归属）。

    Raises:
        HTTPException 403（无编辑权）/ 404（底稿不存在）。
    """
    from app.models.workpaper_models import WorkingPaper
    from app.services.permission_service import Permission, check_permission

    role = current_user.role.value

    # ① 角色级 WORKPAPER_WRITE 能力
    if not check_permission(role, Permission.WORKPAPER_WRITE):
        raise HTTPException(status_code=403, detail="无底稿编辑权限")

    # ③ 解析目标底稿所属项目
    project_id = (
        await db.execute(
            select(WorkingPaper.project_id).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if project_id is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    # ② admin/partner 全局放行（在确认底稿存在后返回其 project_id）
    if role in ("admin", "partner"):
        return project_id

    # ④ 项目成员编辑权（project_users edit 级；每次直接查库）
    level = await _load_member_level(db, current_user.id, project_id)
    if level is None:
        raise HTTPException(status_code=403, detail="无底稿编辑权限")

    if PERMISSION_HIERARCHY.get(level, 0) < PERMISSION_HIERARCHY["edit"]:
        raise HTTPException(status_code=403, detail="无底稿编辑权限")

    return project_id


async def authorize_wp_read(db: AsyncSession, current_user: User, wp_id: UUID) -> UUID:
    """底稿只读权校验（可复用；供 body/path-wp_id 的**读**端点调用）。

    与 ``authorize_wp_edit`` 对称，但只要求项目 ``readonly`` 级权限——用于导出模板/
    导出数据等读操作：不能被误提到 edit（否则 readonly 成员无法导出），但也不能对
    非项目成员放行（否则任意登录用户可拉取他人项目底稿数据）。

    判定口径：
    1. admin/partner 全局放行（在确认底稿存在后返回其 project_id）。
    2. 其余角色须为目标底稿所属项目成员（``project_users`` 任一权限级 ≥ readonly）。

    Returns:
        目标底稿所属 project_id。

    Raises:
        HTTPException 403（非项目成员）/ 404（底稿不存在）。
    """
    from app.models.workpaper_models import WorkingPaper

    role = current_user.role.value

    project_id = (
        await db.execute(
            select(WorkingPaper.project_id).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if project_id is None:
        raise HTTPException(status_code=404, detail="底稿不存在")

    if role in ("admin", "partner"):
        return project_id

    level = await _load_member_level(db, current_user.id, project_id)
    if level is None:
        raise HTTPException(status_code=403, detail="无底稿访问权限")

    if PERMISSION_HIERARCHY.get(level, 0) < PERMISSION_HIERARCHY["readonly"]:
        raise HTTPException(status_code=403, detail="无底稿访问权限")

    return project_id


# ---------------------------------------------------------------------------
# _load_member_level — 级别判定点共用的成员级别读取（不经缓存）
# ---------------------------------------------------------------------------


async def _load_member_level(db: AsyncSession, user_id: UUID, project_id: UUID) -> str | None:
    """返回用户在项目的未删除成员行级别（``permission_level`` 的字符串取值），没有成员行返回 None。

    ``assert_project_permission``、``authorize_wp_edit``、``authorize_wp_read`` 三个级别判定点共用本函数，
    每次判定都直接查库（partner-manager-edit-permission D3：权限缓存已移除）。只取级别一列、不经 ORM
    身份映射：结果取自本次查询返回的行，不会是同一会话里早先加载、之后已过时的成员行对象。
    """
    level = (
        await db.execute(
            select(ProjectUser.permission_level).where(
                ProjectUser.project_id == project_id,
                ProjectUser.user_id == user_id,
                ProjectUser.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    return level.value if level is not None else None


# ---------------------------------------------------------------------------
# check_consol_lock — 合并锁定检查
# ---------------------------------------------------------------------------


async def check_consol_lock(
    project_id: UUID | None = None,
    wp_id: UUID | None = None,
    note_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """检查项目是否被合并锁定，锁定时返回 423。

    Phase 0 修复（consol-phase0-core-pipeline Task 8.1）：
    consol_lock 列已通过 V034 迁移就位 + ORM Project 模型声明，
    移除旧的"列可能不存在"SAVEPOINT 静默 pass，改用 ORM select。
    锁定态直接抛 423，真实异常暴露而非吞掉。

    Phase 1（consol-phase1-arch-lock Task 5.2/5.3）：全端点覆盖。
    端点路径含 project_id 时直接判锁；仅含资源 id（wp_id/note_id）时
    反查所属 project_id 再判锁。反查失败放行不误拦 + 记 warning（EH4）。
    """
    resolved_pid = project_id

    # EH4：路径仅含资源 id 时反查所属 project_id（走主键索引，写端点低频）
    if resolved_pid is None and wp_id is not None:
        try:
            from app.models.workpaper_models import WorkingPaper
            res = await db.execute(
                select(WorkingPaper.project_id).where(WorkingPaper.id == wp_id)
            )
            resolved_pid = res.scalar_one_or_none()
        except Exception as err:
            logger.warning("check_consol_lock 反查 project_id (wp_id=%s) 失败，放行: %s", wp_id, err)
            return

    if resolved_pid is None and note_id is not None:
        try:
            from app.models.report_models import DisclosureNote
            res = await db.execute(
                select(DisclosureNote.project_id).where(DisclosureNote.id == note_id)
            )
            resolved_pid = res.scalar_one_or_none()
        except Exception as err:
            logger.warning("check_consol_lock 反查 project_id (note_id=%s) 失败，放行: %s", note_id, err)
            return

    # 无法确定项目（既无 project_id 也反查不到）→ 放行不误拦（EH4）
    if resolved_pid is None:
        return

    result = await db.execute(
        select(Project.consol_lock).where(Project.id == resolved_pid)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=423, detail="项目已被合并锁定，无法修改")


# ---------------------------------------------------------------------------
# get_visible_projects — 项目可见性过滤
# ---------------------------------------------------------------------------


async def get_visible_project_ids(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[UUID]:
    """返回当前用户可见的项目 ID 列表。

    admin/partner 可见所有项目，其他角色只能看到自己参与的项目。
    """
    if current_user.role.value in ("admin", "partner"):
        from app.models.core import Project
        result = await db.execute(
            select(Project.id).where(Project.is_deleted == False)  # noqa: E712
        )
        return [r[0] for r in result.all()]

    result = await db.execute(
        select(ProjectUser.project_id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    return [r[0] for r in result.all()]


async def readable_project_ids(db: AsyncSession, current_user: User) -> set[UUID] | None:
    """当前用户按 ``assert_project_permission(..., "readonly")`` 能读的项目（「参照其他项目」类候选的筛选口径）。

    与门禁同一口径：admin 不限（返回 ``None``）；其余 = 本人未删除成员行所在的项目（任何级别都不低于 readonly）。
    不能用 ``get_visible_project_ids``：它给 partner 全部项目，而门禁不给 partner 越过成员行 —— 用它筛候选，
    列出来的项目一读就 403（spec consol-autotree-residual-closure R2）。
    """
    if current_user.role.value == "admin":
        return None
    result = await db.execute(
        select(ProjectUser.project_id).where(
            ProjectUser.user_id == current_user.id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    return {r[0] for r in result.all()}


# ---------------------------------------------------------------------------
# get_user_scope_cycles — 循环级权限过滤
# ---------------------------------------------------------------------------


async def get_user_scope_cycles(
    current_user: User,
    project_id: UUID,
    db: AsyncSession,
) -> list[str] | None:
    """用户在指定项目中的循环范围限制（试算表 / 调整分录 / 附注按循环过滤）。

    ``None`` = 不限：系统 admin / partner，以及本项目主管（经理、合伙人、质控、EQCR，含中文别名）。
    受限成员返回有效范围（团队分配勾选 ∪ 委派扩大的循环），**可以是空列表** —— 调用方须按
    ``is not None`` 过滤，空列表即什么都不给。原先只读 ``project_users.scope_cycles`` 且空 = 不限，
    与底稿可见性相反（spec procedure-trim-generation-delegation-chain 需求 5，与角色分类器同一来源）。
    """
    if current_user.role.value in ("admin", "partner"):
        return None
    from app.services.wp_visibility.effective_scope import resolve_member_scope

    member = await resolve_member_scope(db, project_id, current_user.id)
    if member.is_supervisor and not member.is_admin:
        return None
    return sorted(member.cycles) if not member.is_admin else []


# ---------------------------------------------------------------------------
# _resolve_project_role — 查询用户在项目中的角色
# ---------------------------------------------------------------------------


async def _resolve_project_role(
    db: AsyncSession, user_id: UUID, project_id: UUID | None
) -> str | None:
    """从 ProjectUser 表查询用户在指定项目中的角色。

    返回 project_role 字符串（如 "manager"/"preparer"），无记录返回 None。
    project_id 为 None 时直接返回 None（全局端点仅依赖 system_role）。
    """
    if project_id is None:
        return None

    result = await db.execute(
        select(ProjectUser.role).where(
            ProjectUser.project_id == project_id,
            ProjectUser.user_id == user_id,
            ProjectUser.is_deleted == False,  # noqa: E712
        )
    )
    role_enum = result.scalar_one_or_none()
    return role_enum.value if role_enum else None


# ---------------------------------------------------------------------------
# require_operation — 权限矩阵操作级授权工厂
# ---------------------------------------------------------------------------


def require_operation(operation: str) -> Callable:
    """操作级权限校验依赖工厂。

    根据 permission_matrix_service.can(system_role, project_role, operation) 判断。
    admin/partner 的系统角色在矩阵里有全集。
    project_id 从路径参数/查询参数自动获取；无 project_id 的全局端点仅按 system_role 判断
    （project_id 在请求体里的端点，须在函数体内另调 ``assert_project_permission``）。

    请求带 project_id 时另有两道项目判定（spec consol-autotree-residual-closure R3）：

    - 最先：会改项目数据的操作遇已归档项目 ⇒ 423（与 ``require_project_access`` 的 edit / review 级同一守卫）；
    - 矩阵放行后：须为本项目成员（``assert_project_permission(..., "readonly")``，admin 例外）。

    原先只看矩阵：系统角色为 manager / auditor / partner 的用户矩阵里就有 wp:edit / report:edit，于是对任何
    项目都放行 —— 改路径里的项目 id 即可往别人的项目里建调整分录、编排归档；归档项目也照改不误。
    """

    async def dependency(
        current_user: User = Depends(get_current_user),
        project_id: UUID | None = None,
        db: AsyncSession = Depends(get_db),
    ) -> User:
        from app.services.permission_matrix_service import can

        if project_id is not None and operation not in _OPERATIONS_ALLOWED_ON_ARCHIVED:
            # 已归档项目只读：与 require_project_access 的 edit / review 级同一守卫、同一次序（最先判，任何人都是 423）
            await _check_project_not_archived(db, project_id, current_user, "edit")

        system_role = current_user.role.value
        project_role = await _resolve_project_role(db, current_user.id, project_id)

        if not can(system_role, project_role, operation):
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "OPERATION_NOT_ALLOWED",
                    "operation": operation,
                },
            )
        if project_id is not None:
            await assert_project_permission(db, current_user, project_id, "readonly")
        return current_user

    return dependency


# 已归档项目上仍可执行的操作：只读查看；归档编排本身要能对已归档项目幂等重入（再次推送、查任务）。
# 其余操作都会改项目数据 ⇒ 已归档即 423。这些端点原先挂 require_project_access("edit")（含归档守卫），
# 换成 require_operation 后归档守卫与成员判定一起丢了（test_archived_project_guard 自那时起一直红）。
_OPERATIONS_ALLOWED_ON_ARCHIVED: frozenset[str] = frozenset({"project:view", "archive:manage"})


# ---------------------------------------------------------------------------
# require_project_audit_year — 项目年度解析（非鉴权依赖）
# ---------------------------------------------------------------------------

async def require_project_audit_year(
    db: AsyncSession,
    project_id: UUID,
    requested_year: int | None = None,
) -> int:
    """返回请求年度或项目审计年度，缺失时以 422 明确拒绝。

    ``year`` 是项目数据的业务维度，不能用自然年或固定年度兜底。显式传入的
    年度保留调用方选择；缺省时从项目的统一年度解析器取值。
    """
    from app.services.project_audit_year import resolve_project_audit_year_for_request

    year = await resolve_project_audit_year_for_request(db, project_id, requested_year)
    if year is None:
        raise HTTPException(
            status_code=422,
            detail="未设置审计年度，请先在项目基本信息中填写",
        )
    return year
