"""Role_Service —— 角色与数据权限配置（dept-role-data-permission Task 4）

职责：`sys_role` 的 CRUD + `sys_role_project`（data_scope=2 的自定义项目）覆盖写。

🔴 **写入侧「拒绝」与读取侧「降级」是两套刻意不同的口径，不要统一**：
   - 本模块（写入侧，Req 3.2）：data_scope ∉ {1,2,5} ⇒ **拒绝** HTTP 400
     "数据权限范围取值非法"。含已废弃的 3/4 —— 不允许再往库里写部门维度取值。
   - `data_scope_service.normalize_data_scope`（读取侧，Req 6.5/12.3）：遇到 3/4 或
     未知值 ⇒ **降级为 5 并告警**，不抛异常。因为库里可能已存在历史脏数据
     （或被人手工 UPDATE 过），读取时抛异常会让整个鉴权链路 500。
   一句话：**入口严、出口宽**。若把写入侧也改成降级，非法值会被静默存进库；
   若把读取侧改成抛异常，一条脏数据能让全站登录失败。

📌 **data_scope 校验的唯一入口在本模块**（项目铁律）：请求 schema **不加** `ge/le`
   约束。原因是 Pydantic 的范围校验会返回 **422** 且文案由框架生成，
   而 Req 3.2 明确要求 **400 + "数据权限范围取值非法"**。

服务层只 `flush` 不 `commit`，由路由层统一 `commit`（项目铁律）。

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.sys_permission import (
    DATA_SCOPE_CUSTOM,
    ROLE_STATUS_ENABLED,
    VALID_DATA_SCOPES,
    SysRole,
    SysRoleProject,
    SysUserRole,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ERR_DATA_SCOPE_INVALID",
    "ERR_ROLE_KEY_DUPLICATE",
    "ERR_ROLE_NOT_FOUND",
    "create_role",
    "delete_role",
    "get_role_project_ids",
    "list_roles",
    "update_role",
    "validate_data_scope",
]

# 错误文案（Req 3.2 / 3.3 逐字要求，勿改动措辞 —— 前端与测试都按这个文案断言）
ERR_DATA_SCOPE_INVALID = "数据权限范围取值非法"
ERR_ROLE_KEY_DUPLICATE = "角色标识已存在"
ERR_ROLE_NOT_FOUND = "角色不存在"


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def validate_data_scope(data_scope: object) -> int:
    """校验 data_scope 必须 ∈ {1, 2, 5}，否则抛 400。

    与读取侧的 `normalize_data_scope` 相反：这里**不降级**，直接拒绝（Req 3.2）。

    ⚠️ `bool` 必须显式拦掉：Python 里 `True == 1` 且 `True in {1,2,5}` 为真，
       放行会让 `data_scope=true` 静默存成 1（=全部数据，最大权限）。
    """
    if isinstance(data_scope, bool) or not isinstance(data_scope, int):
        raise HTTPException(status_code=400, detail=ERR_DATA_SCOPE_INVALID)
    if data_scope not in VALID_DATA_SCOPES:
        # 3/4 是已废弃的部门维度取值，与越界值同等对待（Req 3.2 明确含 3、4）
        raise HTTPException(status_code=400, detail=ERR_DATA_SCOPE_INVALID)
    return data_scope


async def _assert_role_key_available(
    db: AsyncSession, role_key: str, *, exclude_role_id: int | None = None
) -> None:
    """role_key 在**未删除**范围内必须唯一（Req 3.3）。

    只查 `is_deleted == false`，与 `idx_sys_role_key` 的 partial unique 谓词
    保持同一口径 —— 软删角色的 role_key 允许被复用。
    """
    stmt = select(SysRole.id).where(
        SysRole.role_key == role_key,
        SysRole.is_deleted == False,  # noqa: E712
    )
    if exclude_role_id is not None:
        # 修改自身时不应与自己冲突
        stmt = stmt.where(SysRole.id != exclude_role_id)
    if (await db.execute(stmt)).first() is not None:
        raise HTTPException(status_code=400, detail=ERR_ROLE_KEY_DUPLICATE)


async def _get_role_or_404(db: AsyncSession, role_id: int) -> SysRole:
    role = (
        await db.execute(
            select(SysRole).where(
                SysRole.id == role_id,
                SysRole.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=404, detail=ERR_ROLE_NOT_FOUND)
    return role


async def _validate_project_ids(
    db: AsyncSession, project_ids: Iterable[UUID]
) -> set[UUID]:
    """校验项目 id 都存在且未软删，返回去重集合。

    需求未明写此校验，但**必须做**：`fk_sys_role_project_project` 外键存在，
    传入幽灵 id 会让 INSERT 抛 IntegrityError → 未捕获的 500。
    给出明确 400 比 500 有用得多。软删项目也拒绝 —— 绑定一个已删项目没有意义，
    且 Scope_Resolver 读取时本就会把它过滤掉（静默失效比报错更难排查）。
    """
    unique = {UUID(str(pid)) for pid in project_ids}
    if not unique:
        return set()

    rows = await db.execute(
        select(Project.id).where(
            Project.id.in_(unique),
            Project.is_deleted == False,  # noqa: E712
        )
    )
    existing = {r[0] for r in rows.all()}
    missing = unique - existing
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"项目不存在或已删除: {', '.join(str(p) for p in sorted(missing, key=str))}",
        )
    return unique


# ---------------------------------------------------------------------------
# sys_role_project 覆盖写
# ---------------------------------------------------------------------------


async def _overwrite_role_projects(
    db: AsyncSession, role_id: int, project_ids: Iterable[UUID]
) -> set[UUID]:
    """覆盖写该角色的自定义项目关联：**先全删、再按新集合插入**（Req 3.4）。

    幂等（Property 4）：结果只取决于 `project_ids` 去重后的集合，
    与调用次数、原有关联、传入顺序、重复元素均无关。

    ⚠️ 必须"先全删"而不是"求差集增量改"：增量写在并发下会残留旧行，
       且实现复杂度换不来任何收益（关联表行数极小）。
    """
    await db.execute(
        delete(SysRoleProject).where(SysRoleProject.role_id == role_id)
    )
    unique = {UUID(str(pid)) for pid in project_ids}
    for pid in unique:
        db.add(SysRoleProject(role_id=role_id, project_id=pid))
    return unique


async def _clear_role_projects(db: AsyncSession, role_id: int) -> None:
    """清空该角色的全部自定义项目关联（data_scope 从 2 改为非 2 时，Req 3.5）。

    🔴 必须清空而非保留：若保留，角色日后再被改回 data_scope=2 会**突然恢复**
       一批管理员早已忘记的旧关联 —— 一个静默的越权。
    """
    await db.execute(
        delete(SysRoleProject).where(SysRoleProject.role_id == role_id)
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_role(
    db: AsyncSession,
    *,
    name: str,
    role_key: str,
    data_scope: int,
    status: str = ROLE_STATUS_ENABLED,
    project_ids: Sequence[UUID] | None = None,
) -> SysRole:
    """创建角色（Req 3.1/3.2/3.3/3.4）。

    校验顺序刻意如此：**data_scope 先于 role_key**。
    这样"两个字段同时非法"时报的是范围错误 —— 与 Req 3.2 把 data_scope 列为
    创建的首要约束一致，也让测试断言有确定性（否则报哪个取决于实现顺序）。

    Raises:
        HTTPException 400: data_scope 非法 / role_key 重复 / 项目 id 不存在
    """
    scope = validate_data_scope(data_scope)

    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="角色名称为必填项")
    clean_key = (role_key or "").strip()
    if not clean_key:
        raise HTTPException(status_code=400, detail="角色标识为必填项")

    await _assert_role_key_available(db, clean_key)

    # data_scope=2 才允许带项目；非 2 时传了项目一律忽略（不报错，见下方注释）
    wanted_projects: set[UUID] = set()
    if scope == DATA_SCOPE_CUSTOM:
        wanted_projects = await _validate_project_ids(db, project_ids or [])
    elif project_ids:
        # 不报错而是忽略：前端切换 data_scope 下拉时可能仍带着上次勾选的项目，
        # 为此报 400 体验很差。但要留痕，便于排查"我选的项目怎么没了"。
        logger.info(
            "[role_service] 创建角色 %r 的 data_scope=%d（非 2），忽略传入的 %d 个项目 id",
            clean_key, scope, len(project_ids),
        )

    role = SysRole(
        name=clean_name,
        role_key=clean_key,
        data_scope=scope,
        status=status or ROLE_STATUS_ENABLED,
    )
    db.add(role)
    await db.flush()  # 取自增 id，供下面写关联用

    if scope == DATA_SCOPE_CUSTOM:
        await _overwrite_role_projects(db, role.id, wanted_projects)
        await db.flush()

    return role


async def update_role(
    db: AsyncSession,
    role_id: int,
    *,
    name: str | None = None,
    role_key: str | None = None,
    data_scope: int | None = None,
    status: str | None = None,
    project_ids: Sequence[UUID] | None = None,
) -> SysRole:
    """修改角色（Req 3.2~3.5）。

    关联表处理规则（这是本函数最容易写错的部分）：
      - 目标 data_scope == 2 且**传了** project_ids → 覆盖写（Req 3.4）
      - 目标 data_scope == 2 且**没传** project_ids → 保持原关联不动
        （`None` = "本次不改这个字段"，与 `[]` = "清空"必须区分开；
         若把 None 也当清空，只改角色名的请求会把项目配置全抹掉）
      - 目标 data_scope != 2 → **清空**全部关联（Req 3.5），不论是否传了 project_ids

    Raises:
        HTTPException 404: 角色不存在或已删除
        HTTPException 400: data_scope 非法 / role_key 重复 / 项目 id 不存在
    """
    role = await _get_role_or_404(db, role_id)

    target_scope = role.data_scope if data_scope is None else validate_data_scope(data_scope)

    if role_key is not None:
        clean_key = role_key.strip()
        if not clean_key:
            raise HTTPException(status_code=400, detail="角色标识为必填项")
        await _assert_role_key_available(db, clean_key, exclude_role_id=role_id)
        role.role_key = clean_key

    if name is not None:
        clean_name = name.strip()
        if not clean_name:
            raise HTTPException(status_code=400, detail="角色名称为必填项")
        role.name = clean_name

    if status is not None:
        role.status = status

    # 先校验项目 id（可能抛 400），再改 data_scope —— 保证校验失败时不留下
    # "data_scope 已改但关联未更新"的半成品状态（虽然路由层未 commit，
    # 但同一 session 内后续查询会看到脏值）
    if target_scope == DATA_SCOPE_CUSTOM and project_ids is not None:
        wanted = await _validate_project_ids(db, project_ids)
        role.data_scope = target_scope
        await _overwrite_role_projects(db, role_id, wanted)
    elif target_scope != DATA_SCOPE_CUSTOM:
        role.data_scope = target_scope
        await _clear_role_projects(db, role_id)
    else:
        # scope=2 且未传 project_ids：保持原关联
        role.data_scope = target_scope

    await db.flush()
    return role


async def list_roles(db: AsyncSession, *, include_deleted: bool = False) -> list[SysRole]:
    """查询角色列表及其 data_scope（Req 3.6）。

    默认只返回未删除角色。`include_deleted` 仅供运维排查用，不暴露给 API。
    """
    stmt = select(SysRole)
    if not include_deleted:
        stmt = stmt.where(SysRole.is_deleted == False)  # noqa: E712
    stmt = stmt.order_by(SysRole.id)
    return list((await db.execute(stmt)).scalars().all())


async def get_role_by_id(db: AsyncSession, role_id: int) -> SysRole:
    """按 id 取未删除角色，不存在抛 404。"""
    return await _get_role_or_404(db, role_id)


async def get_role_project_ids(db: AsyncSession, role_id: int) -> list[UUID]:
    """取角色的自定义项目 id 列表。

    JOIN `projects` 过滤软删项目 —— 关联表里可能残留软删项目的 id
    （**软删不触发 FK CASCADE**），直接返回会让前端多选框显示一个已删项目。
    返回列表按字符串序排序，保证响应稳定（便于前端 diff 与测试断言）。
    """
    await _get_role_or_404(db, role_id)
    rows = await db.execute(
        select(SysRoleProject.project_id)
        .join(Project, Project.id == SysRoleProject.project_id)
        .where(
            SysRoleProject.role_id == role_id,
            Project.is_deleted == False,  # noqa: E712
        )
    )
    return sorted((r[0] for r in rows.all()), key=str)


async def delete_role(db: AsyncSession, role_id: int) -> None:
    """软删角色并清理其全部关联（Req 3.6）。

    - `sys_role`：软删（`is_deleted=True`，`deleted_at` 由 event listener 自动填）
    - `sys_role_project`：**硬删**全部关联
    - `sys_user_role`：**硬删**全部账号绑定

    为什么关联表用硬删：两张表都没有 `is_deleted` 列（覆盖写语义，见 ORM 注释）。
    保留孤立行的唯一"好处"是角色被恢复时能带回旧配置，但需求里没有恢复功能，
    而留着会让 `assemble_login_user` 的 JOIN 多做无用过滤。

    ⚠️ 清 `sys_user_role` 会**改变已登录账号的实际权限**，调用方（路由层）
       必须随后调 `invalidate_login_user_by_user` 失效相关缓存（Task 9.1）。

    🔴 **必须调 `soft_delete()` 而不是直接写 `is_deleted = True`**：
       `SoftDeleteMixin` 的 docstring 曾声称"设置 is_deleted=True 时会通过
       @event.listens_for 自动填充 deleted_at" —— **该 listener 在本仓压根不存在**
       （全仓 0 处 `listens_for`）。直接赋值会让 `deleted_at` 永久为 NULL，
       事后无法回答"这条是什么时候删的"。`soft_delete()` 才会同时设置两个字段。
    """
    role = await _get_role_or_404(db, role_id)

    await db.execute(delete(SysRoleProject).where(SysRoleProject.role_id == role_id))
    await db.execute(delete(SysUserRole).where(SysUserRole.role_id == role_id))

    role.soft_delete()  # 同时置 is_deleted=True 与 deleted_at（无 event listener 兜底）
    await db.flush()


async def get_user_ids_by_role(db: AsyncSession, role_id: int) -> list[UUID]:
    """反查绑定了该角色的全部账号 id。

    供路由层在角色 data_scope 变更后精确失效这些账号的 LoginUser 缓存（Req 5.4）。
    ⚠️ 必须在**变更前**调用：`delete_role` 会清掉 `sys_user_role`，之后就查不到了。
    """
    rows = await db.execute(
        select(SysUserRole.user_id).where(SysUserRole.role_id == role_id)
    )
    return [r[0] for r in rows.all()]


async def count_roles(db: AsyncSession) -> int:
    """未删除角色总数（供分页 / 健康检查用）。"""
    return (
        await db.execute(
            select(func.count())
            .select_from(SysRole)
            .where(SysRole.is_deleted == False)  # noqa: E712
        )
    ).scalar_one()
