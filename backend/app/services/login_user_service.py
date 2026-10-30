"""Auth_Assembler —— LoginUser 组装与 Redis 缓存（dept-role-data-permission Task 7）

四个入口：
  `assemble_login_user`          从 DB 组装（不碰缓存）
  `cache_login_user`             写缓存 + 维护 user→token 反向索引
  `get_login_user`               取缓存，miss 则重组并回写
  `invalidate_login_user_by_user` 角色变更时失效该账号的全部缓存

🔴 **三条方向性铁律（写反任意一条都是安全事故）**：
  1. **组装失败 ⇒ 抛 401，绝不以空权限或受限权限放行**（Req 5.6）。
     "降级为最小权限"听起来安全，实则是把「系统故障」伪装成「你没权限」——
     用户会以为是配置问题而反复重试，运维看不到任何异常。
  2. **Redis 不可用 ⇒ 现算不缓存，功能照常**（design 的降级考量）。
     缓存是性能设施，不是权限来源。Redis 挂了就每次现算，**不能**因此拒绝服务。
  3. **缓存写失败 ⇒ 只记 warning，不影响本次请求**。已经算出正确的 LoginUser 了，
     为"存不进缓存"而让请求失败是本末倒置。

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import User
from app.models.sys_permission import (
    DATA_SCOPE_ALL,
    DATA_SCOPE_CUSTOM,
    DATA_SCOPE_PARTICIPANT,
    DATA_SCOPE_SELF,
    SysRole,
    SysRoleProject,
    SysUserRole,
)
from app.schemas.login_user import LoginUser, RoleScope
from app.services.data_scope_service import compute_effective_data_scope

logger = logging.getLogger(__name__)

__all__ = [
    "ERR_ASSEMBLE_FAILED",
    "LOGIN_USER_KEY_PREFIX",
    "LOGIN_USER_TTL_SECONDS",
    "USER_INDEX_KEY_PREFIX",
    "assemble_login_user",
    "cache_login_user",
    "get_login_user",
    "invalidate_login_user_by_user",
]

LOGIN_USER_KEY_PREFIX = "login_user:"
USER_INDEX_KEY_PREFIX = "login_user_index:"
LOGIN_USER_TTL_SECONDS = 30 * 60
"""缓存 TTL（30 分钟）。

与 access_token 有效期同量级即可 —— 更长没意义（token 过期后缓存自然无人问），
更短则失去缓存价值。角色变更靠 `invalidate_login_user_by_user` 主动失效，
不依赖 TTL 自然过期（Req 5.4）。
"""

ERR_ASSEMBLE_FAILED = "鉴权信息组装失败，请重新登录"
"""Req 5.6 规定的文案。前端按此提示引导用户重新登录。"""

# users.role 枚举值 → 该枚举对应 seed 角色的 data_scope（Req 10.3 / 10.4）
# 用于账号未绑定任何角色时的回退（Req 10.5）。
#
# 🔴🔴 **这张表才是真库的实际生效路径，不是 sys_role 表**
#      （2026-08-31 实测：`sys_user_role` **0 行**、`sys_role_project` **0 行**
#      ⇒ 全部 8 个活跃账号**都没绑定过任何 sys_role**）
#      ⇒ 改 seed 迁移（V156/V158/V162）只影响"绑定了角色的账号"= 当前 0 个；
#        真正决定每个账号实际范围的是本表。两者必须**成对**改，
#        否则「绑了角色的」与「没绑的」两类账号行为分叉。
_SEED_SCOPE_BY_ENUM_ROLE: dict[str, int] = {
    "admin": DATA_SCOPE_ALL,
    "partner": DATA_SCOPE_ALL,
    # 🔴 **manager / site_lead = 6「我参与的项目」**（2026-08-31 改，原为 5「仅本人」）
    #    Spec: data-scope-participant-visibility Task 4.2 / Req 5.5，配套迁移 V162。
    #
    #    改因（真库实测）：最终可见 = 项目级 ∩ 数据权限，而 scope=5 **只认**
    #    `created_by == 本人` ⇒ 被指派为项目经理／现场负责人但**不是创建人**的
    #    账号，两层口径几乎不相交 ⇒ 最终可见集为 **0**：
    #        xingzihao2 (manager)   项目级=2  scope5 集=0  最终=0
    #        xingzihao3 (site_lead) 项目级=2  scope5 集=0  最终=0
    #
    #    ⚠️ 刻意**不是**放宽 scope=5 的语义 —— 上游 `dept-role-data-permission`
    #       Req 6.4 明文禁止把「仅本人」的依据换成 project_users/partner_id/
    #       manager_id。scope=6 是**新增档位**，scope=5 一字未动。
    "manager": DATA_SCOPE_PARTICIPANT,
    # site_lead（现场经理）与 manager 同档 —— `site-lead-and-field-lead` spec 的
    # 核心约定是「site_lead 权限等同 manager」，故两者恒同值。
    #
    # 写成字面量而非 `= [...]["manager"]` 别名：本 dict 是
    # `UserRoleBindingPanel.vue` 的 `SEED_SCOPE` 的真源，前端守卫
    # （`RoleDataScopeManager.spec.ts` D 层）用正则抓本**字面量**做精确相等比对
    # ⇒ 只有写进字面量里，两侧才能真正双向锁死。
    # ⚠️ 那条守卫的正则原先**只解析 `DATA_SCOPE_ALL|DATA_SCOPE_SELF` 两个常量名**
    #    ⇒ 引入 `DATA_SCOPE_PARTICIPANT` 后这两行会匹配不到、parsed 少两项。
    #    已在同 spec Task 5.3 同步扩为三个常量名。
    "site_lead": DATA_SCOPE_PARTICIPANT,
    # 🔴 **auditor / qc / eqcr = 6「我参与的项目」**（2026-09-03 改，原为 5「仅本人」）
    #    配套迁移 **V163**；上一轮 manager/site_lead 的改动见上方注释与 V162。
    #
    #    改因与 manager/site_lead 那次**是同一个缺陷**：最终可见 = 项目级 ∩ 数据权限，
    #    而 scope=5 只认 `created_by == 本人` ⇒ **审计员从来不是项目创建人**
    #    （项目由 admin/manager/partner 建）⇒ 两层交集恒为空 ⇒
    #    `deps.get_visible_project_ids` 在「空集」分支直接 `return []` ⇒
    #    工作台「项目总数/进行中/待复核/已完成」四个计数全为 0，而委派通知照常收到
    #    —— 用户 2026-09-03 实报的形态正是「收到委派通知但工作台没有项目」。
    #
    #    ⚠️ **上一轮（Req 5.2）把这三个角色刻意排除的理由已被实测推翻**：当时写的是
    #       「业务定位是看自己经手的，放宽属超出诉求」。但 scope=5 的**实现**是
    #       `projects.created_by == 本人`，它表达的是「我**创建**的」而不是
    #       「我**经手**的」⇒ 对不建项目的角色，scope=5 等于「什么都看不到」，
    #       与其业务定位恰好相反。scope=6「我参与的」才是「经手」的正确投影。
    #       用户 2026-09-03 拍板放宽这三个。
    #
    #    ⚠️ **不放宽越权面**：scope=6 = 项目级 5 来源并集 ⇒ 与项目级做 AND 后
    #       交集 = 项目级本身 ⇒ 只有**本就被登记为该项目成员/负责人/创建人**的账号
    #       才可见，与该项目无任何关系的账号仍然一个都看不到
    #       （由 `test_scope_participant.py` 的 stranger 判据钉住）。
    "auditor": DATA_SCOPE_PARTICIPANT,
    "qc": DATA_SCOPE_PARTICIPANT,
    "eqcr": DATA_SCOPE_PARTICIPANT,
    # ⚠️ **readonly 刻意仍为 5**（本轮不动）：它是「只读观察者」，没有「参与项目」
    #    的业务语义 —— 它本就不该被委派任何工作，放宽它等于让一个只读账号
    #    看到全部沾过边的项目。用户 2026-09-03 明确只放宽前三个。
    "readonly": DATA_SCOPE_SELF,
}


def _login_user_key(token: str) -> str:
    return f"{LOGIN_USER_KEY_PREFIX}{token}"


def _user_index_key(user_id: UUID | str) -> str:
    return f"{USER_INDEX_KEY_PREFIX}{user_id}"


def _fallback_scope_for(enum_role: str) -> int:
    """未绑定角色时的回退 data_scope（Req 10.5 / 10.6）。

    🔴 **这里刻意不返回固定的 5**，尽管 Req 4.4 字面上那样写。
       Req 10.5/10.6 要求按 `users.role` 对应的 seed 角色解析，且 admin/partner
       不得低于其 seed 范围（=1）。两条需求对「未绑定角色的 admin」表述矛盾；
       按 4.4 实现会让未绑定的 admin 拿到 scope=5，而本库 admin 名下
       `created_by` 项目为 0 ⇒ **管理员什么都看不到**。故按 10.5/10.6。
       （Property 6 的表述也与 10.5/10.6 一致。）

    未知枚举值回退到最小权限 —— 这个方向是安全的（宁可少看，不可多看）。
    """
    scope = _SEED_SCOPE_BY_ENUM_ROLE.get(enum_role)
    if scope is None:
        logger.warning(
            "[login_user] 未知的 users.role 枚举值 %r → 回退为最小权限 %d",
            enum_role, DATA_SCOPE_SELF,
        )
        return DATA_SCOPE_SELF
    return scope


async def assemble_login_user(
    user: User | UUID, db: AsyncSession
) -> LoginUser:
    """从 DB 组装 LoginUser（Req 5.1）。

    Args:
        user: `User` ORM 对象，或 user_id（后者会先查库）
        db: 数据库会话

    Returns:
        完整的 LoginUser

    Raises:
        ValueError: 账号不存在或已软删（由 `get_login_user` 转成 401）

    ⚠️ 本函数**不碰缓存**，也不吞异常 —— DB 层的错误原样上抛，
       由 `get_login_user` 统一转 401（Req 5.6）。这样分层使得
       "组装逻辑"可以独立测试，不必构造 Redis。
    """
    # ---- 1. 取账号 ----
    if isinstance(user, User):
        db_user = user
    else:
        db_user = (
            await db.execute(
                select(User).where(
                    User.id == user,
                    User.is_deleted == False,  # noqa: E712
                )
            )
        ).scalar_one_or_none()
        if db_user is None:
            raise ValueError(f"账号不存在或已删除: {user}")

    enum_role = (
        db_user.role.value if hasattr(db_user.role, "value") else str(db_user.role)
    )

    # ---- 2. 取全部未删除角色 ----
    role_rows = (
        await db.execute(
            select(SysRole.id, SysRole.role_key, SysRole.data_scope)
            .join(SysUserRole, SysUserRole.role_id == SysRole.id)
            .where(
                SysUserRole.user_id == db_user.id,
                SysRole.is_deleted == False,  # noqa: E712
            )
            .order_by(SysRole.id)
        )
    ).all()
    roles = [
        RoleScope(role_id=r[0], role_key=r[1], data_scope=r[2]) for r in role_rows
    ]

    # ---- 3. 算 effective_data_scope ----
    seed_scope = _fallback_scope_for(enum_role)
    scope_candidates: list[int] = [r.data_scope for r in roles]

    # 🔴 **Req 10.6 的权限地板**：admin/partner 的最终可见范围
    #    "不得低于其 seed 角色 data_scope 对应的可见范围"。
    #    `fallback_scope` 只在 roles 为空时生效 ⇒ 若 admin 被绑了一个
    #    data_scope=2 的角色，argmin 会算出 2，**低于** admin 的 seed（=1），
    #    既违反 10.6，也会让 `get_visible_project_ids` 的短路条件
    #    （`effective==1`）失效 —— 管理员反而看得比普通账号少。
    #    故对这两个枚举角色，把 seed 值作为**候选值**一并参与取最大权限。
    #    ⚠️ 这不改 `compute_effective_data_scope` 的语义（它只管取最大），
    #       "谁有权限地板"是调用方的策略，放在这里而不是纯逻辑层。
    if seed_scope == DATA_SCOPE_ALL:
        scope_candidates.append(seed_scope)

    effective = compute_effective_data_scope(
        scope_candidates,
        fallback_scope=seed_scope,
    )

    # ---- 4. 取 data_scope=2 角色的项目并集（Req 6.2）----
    # 只有当 effective 真的是 2 时才需要这个集合，但**仍然无条件查** ——
    # 理由：LoginUser 会被缓存复用，而角色的 data_scope 可能在缓存有效期内
    # 被管理员改动（改动会触发失效，但失效与读取之间存在窗口）。
    # 无条件带上该字段，使缓存对象自洽、不依赖 effective 的当时取值。
    # 代价是一次额外查询，命中缓存后不再发生。
    custom_ids: list[UUID] = []
    scope2_role_ids = [r.role_id for r in roles if r.data_scope == DATA_SCOPE_CUSTOM]
    if scope2_role_ids:
        proj_rows = (
            await db.execute(
                select(SysRoleProject.project_id)
                .where(SysRoleProject.role_id.in_(scope2_role_ids))
                .distinct()
            )
        ).all()
        # 排序保证序列化结果稳定（便于缓存内容比对与测试断言）
        custom_ids = sorted((r[0] for r in proj_rows), key=str)

    return LoginUser(
        user_id=db_user.id,
        username=db_user.username,
        system_role=enum_role,
        roles=roles,
        custom_project_ids=custom_ids,
        effective_data_scope=effective,
    )


async def cache_login_user(token: str, login_user: LoginUser, redis) -> None:
    """写缓存 + 维护 user→token 反向索引（Req 5.2）。

    Redis key 以 **token** 为主键（每个会话一份），而失效发生在 **user** 维度
    （管理员改某账号的角色）⇒ 必须维护 `login_user_index:{user_id}` 集合
    记录该账号当前活跃的 token，供 `invalidate_login_user_by_user` 批量删除。

    ⚠️ `redis` 为 None（不可用）时**静默跳过** —— 缓存是性能设施，不是权限来源。
    ⚠️ 任何写入异常都只记 warning：LoginUser 已经算对了，
       为"存不进缓存"而让请求失败是本末倒置。
    """
    if redis is None:
        return
    try:
        payload = login_user.model_dump_json()
        await redis.set(_login_user_key(token), payload, ex=LOGIN_USER_TTL_SECONDS)

        idx_key = _user_index_key(login_user.user_id)
        await redis.sadd(idx_key, token)
        # 索引本身也要有 TTL，否则会无限累积已过期 token 的名字。
        # 取比 LoginUser 略长的 TTL，保证索引不会先于它指向的 key 消失
        # （那样会漏删 —— 失效时遍历不到该 token）。
        await redis.expire(idx_key, LOGIN_USER_TTL_SECONDS * 2)
    except Exception as e:  # noqa: BLE001
        logger.warning("[login_user] 写缓存失败（不影响本次请求）: %s", e)


async def _read_cached(token: str, redis) -> LoginUser | None:
    """读缓存。命中且能反序列化则返回，否则 None（视作 miss）。

    ⚠️ 反序列化失败必须当 miss 处理而**不是**抛错：缓存里可能残留旧版本
       schema 的 JSON（字段增删后格式不兼容）。当 miss 会自动重组并回写新格式，
       是自愈的；抛错则会让所有老会话直接 401。
    """
    if redis is None:
        return None
    try:
        raw = await redis.get(_login_user_key(token))
    except Exception as e:  # noqa: BLE001
        logger.warning("[login_user] 读缓存失败，按 miss 处理: %s", e)
        return None
    if not raw:
        return None
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return LoginUser.model_validate(json.loads(raw))
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "[login_user] 缓存内容无法反序列化（可能是旧版 schema），按 miss 重组: %s", e
        )
        return None


async def get_login_user(
    token: str, user: User | UUID, db: AsyncSession, redis
) -> LoginUser:
    """取 LoginUser：缓存命中即返回，miss 则重组并回写（Req 5.5）。

    Raises:
        HTTPException 401: 重组失败（DB 不可用 / 数据损坏 / 账号已删）——
            **绝不以受限或空权限放行**（Req 5.6）。

    🔴 为什么组装失败必须 401 而不是"降级为最小权限"：
       降级会把「系统故障」伪装成「你没权限」。用户看到的是空列表，
       会以为是配置问题而反复重试；运维在监控上看不到任何异常。
       401 + 明确文案让故障可见、可追踪。
    """
    cached = await _read_cached(token, redis)
    if cached is not None:
        return cached

    try:
        login_user = await assemble_login_user(user, db)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "[login_user] 组装失败，拒绝放行（不降级）: %s: %s",
            type(e).__name__, e,
        )
        raise HTTPException(status_code=401, detail=ERR_ASSEMBLE_FAILED) from e

    await cache_login_user(token, login_user, redis)
    return login_user


async def invalidate_login_user_by_user(user_id: UUID | str, redis) -> int:
    """失效该账号的全部缓存 LoginUser（Req 5.4）。

    Returns:
        实际删除的 token 数（供调用方记日志；Redis 不可用时返回 0）

    调用时机（缺一处就会出现"改了权限但不生效"）：
      - `assign_roles` 之后（账号的角色集变了）
      - `update_role` 改了 data_scope 或 sys_role_project 之后 ——
        ⚠️ 这时要对**所有绑定该角色的账号**逐一调用（用
        `role_service.get_user_ids_by_role` 反查）
      - `delete_role` 之后（同上，且**必须在删除前**反查账号列表，
        因为 delete_role 会清掉 sys_user_role）

    ⚠️ Redis 不可用时返回 0 而不抛错：此时压根没有缓存需要失效
       （`get_login_user` 会每次现算），语义上等价于"已全部失效"。
    """
    if redis is None:
        return 0
    idx_key = _user_index_key(user_id)
    try:
        tokens = await redis.smembers(idx_key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[login_user] 读反向索引失败: %s", e)
        return 0

    deleted = 0
    for t in tokens or ():
        if isinstance(t, bytes):
            t = t.decode("utf-8")
        try:
            await redis.delete(_login_user_key(t))
            deleted += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("[login_user] 删除缓存 %s 失败: %s", t[:12], e)
    try:
        await redis.delete(idx_key)
    except Exception as e:  # noqa: BLE001
        logger.warning("[login_user] 删除反向索引失败: %s", e)

    if deleted:
        logger.info("[login_user] 已失效账号 %s 的 %d 个缓存会话", user_id, deleted)
    return deleted
