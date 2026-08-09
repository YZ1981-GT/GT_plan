"""自定义底稿（componentType=custom）判定的单一真源。

## 为什么需要这个模块

`WorkingPaper` 表**没有** `component_type` 列 —— `custom` 是 render 期由
`wp_render_config_helpers._maybe_custom_classifications` 合成的：

    无模板归类  AND  ( 该 wp_code 有自定义程序实例  OR
                      (source_type == manual  AND  wp_code 不像标准编号) )
    ⇒ class_code = "CUSTOM"  ⇒ derive_component_type → "custom"

三个下游都要问「这张底稿是不是 custom」：
① `PUT /custom-cells` / `POST /custom-refresh-projection`（非 custom 必须 409，
   标准底稿的 HTML 侧是结构化表单，往它的 xlsx 直写格会绕过审计语义校验）
② `save_formula` 的求值结果双写 xlsx（仅 custom）
③ `delete_formula` 的清格（仅 custom）

若三处各写一份判定，改一处另两处不跟 ⇒ 判定漂移。故收敛在此。

🔴 **有意不 import `wp_render_config_helpers`**：那个模块正被并发 spec 改动
（`l0-confirmation-source-alignment` 在往里加注入器），import 它会把本模块绑到一个
高频变动的文件上。这里直接复用更底层的真源 `acnr.grammar.is_standard_wp_code`
与一条 `ProcedureInstance` 计数查询（与 `_has_custom_procedure` 逐字同构）。
两者语义一致性由守卫交叉锁死。

spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/ Wave 2 / Wave 4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpIndex,
    WpSourceType,
)
from app.services.acnr.grammar import is_standard_wp_code

logger = logging.getLogger(__name__)

#: 底稿处于这些状态时禁止改 xlsx（归档为只读，与既有 `_editor_mode` 口径一致）。
READ_ONLY_FILE_STATUSES: frozenset[WpFileStatus] = frozenset({WpFileStatus.archived})


@dataclass(frozen=True)
class CustomWpContext:
    """自定义底稿上下文（一次查询取齐，避免下游各查一遍）。"""

    wp: WorkingPaper
    wp_code: str
    #: sheet 名恒等于 wp_code（`_maybe_custom_classifications` 合成的
    #: `ClassificationResult.sheet_name = wp_code`；不一致则 render 取不到 html_data）
    sheet_name: str
    is_custom: bool
    is_read_only: bool


async def _has_custom_procedure(
    db: AsyncSession, project_id: UUID, wp_code: str
) -> bool:
    """该 wp_code 下是否存在自定义程序实例。

    与 `wp_render_config_helpers._has_custom_procedure` 逐字同构（守卫交叉锁死）。
    """
    n = (
        await db.execute(
            sa.select(sa.func.count())
            .select_from(ProcedureInstance)
            .where(
                ProcedureInstance.project_id == project_id,
                ProcedureInstance.wp_code == wp_code,
                ProcedureInstance.is_custom == True,  # noqa: E712
                ProcedureInstance.is_deleted == False,  # noqa: E712
            )
        )
    ).scalar() or 0
    return n > 0


async def resolve_is_custom(
    db: AsyncSession, wp: WorkingPaper, wp_code: str | None
) -> bool:
    """判定该底稿的 componentType 是否为 `custom`。

    判据与 `_maybe_custom_classifications` 一致（同一套谓词），差别只在：
    此处**不判「无模板归类」**这一前置 —— 那需要跑完整 classification 链。
    对本模块的三个消费方而言这是安全的收窄方向：

    - 有自定义程序实例 ⇒ 该 wp_code 本就是自定义程序底稿
    - `source_type == manual` 且编号不像标准编号 ⇒ 由 `create-custom` 建的自建底稿

    两者都不成立即返 False（宁可拒绝写入，也不能往标准底稿的 xlsx 直写格）。

    fail-open 说明：查询异常时返回 **False**（不是 True）——
    判不出来时按「不是 custom」处理，让写入端点 409 而非放行。
    """
    if not wp_code:
        return False
    try:
        if await _has_custom_procedure(db, wp.project_id, wp_code):
            return True
    except Exception as exc:  # noqa: BLE001 — 判不出来按 False 处理（拒绝写入）
        logger.warning("custom 判定查询失败 wp_id=%s: %s", wp.id, exc)
        return False
    if wp.source_type == WpSourceType.manual and not is_standard_wp_code(wp_code):
        return True
    return False


def resolve_is_custom_sync(wp: WorkingPaper, wp_code: str | None) -> bool:
    """`resolve_is_custom` 的同步收窄版（只判「自建底稿」这一支，不查 DB）。

    用于 OnlyOffice 路径 —— 那里的 `_resolve_wp_file` 是同步函数、且 WOPI 下载与
    callback 两个入口都不便再开一次查询。判据只保留不需要 DB 的那一支：

        source_type == manual  AND  wp_code 不像标准编号

    🔴 **有意比 `resolve_is_custom` 更窄**：漏判「有自定义程序实例但 source_type
    不是 manual」的底稿时，OO 侧退回既有的「模板 → 缓存副本」路径 —— 那是本函数
    引入前的行为，属零回归方向；而误判会把标准底稿的业务文件直接暴露给 OO 直编，
    绕过 `_hide_non_target_sheets` 等既有保护。故宁窄勿宽。

    两个函数对「自建底稿」这一支必须给出相同结论（守卫交叉锁死）。
    """
    if not wp_code:
        return False
    return wp.source_type == WpSourceType.manual and not is_standard_wp_code(wp_code)


def resolve_is_custom_sync(wp: WorkingPaper, wp_code: str | None) -> bool:
    """`resolve_is_custom` 的**同步子集**：只判「manual + 非标准编号」这一支。

    用于拿不到 `AsyncSession` 的调用点（OnlyOffice 文件解析路径在 WOPI/callback 里
    有些位置只有 ORM 对象）。

    🔴 **只判一支是有意的收窄** —— 「有自定义程序实例」那一支需要查库，此处判不了。
    收窄方向安全：判不出来时返回 False ⇒ 退回既有「模板 → OO 缓存」路径（零回归），
    而不是把标准底稿误判成 custom 去直编业务文件本体。

    `create-custom` 建的自建底稿恒满足 `source_type == manual` 且编号非标准
    （`_custom_code_exists` 侧的编号由用户自定义），故本 spec 的实测路径覆盖得到。
    """
    if not wp_code:
        return False
    try:
        return wp.source_type == WpSourceType.manual and not is_standard_wp_code(
            wp_code
        )
    except Exception as exc:  # noqa: BLE001 — 判不出来按 False（退回既有路径）
        logger.warning("custom 同步判定失败 wp_code=%s: %s", wp_code, exc)
        return False


async def load_custom_context(
    db: AsyncSession, wp_id: UUID
) -> CustomWpContext | None:
    """加载自定义底稿上下文。底稿不存在返回 None（调用方转 404）。

    `is_custom=False` 时仍返回对象（调用方据此转 409），便于错误信息里带上 wp_code。
    """
    wp = (
        await db.execute(
            sa.select(WorkingPaper).where(
                WorkingPaper.id == wp_id,
                WorkingPaper.is_deleted == sa.false(),
            )
        )
    ).scalar_one_or_none()
    if wp is None:
        return None

    wp_code: str | None = None
    if wp.wp_index_id:
        wp_code = (
            await db.execute(
                sa.select(WpIndex.wp_code).where(WpIndex.id == wp.wp_index_id)
            )
        ).scalar_one_or_none()

    is_custom = await resolve_is_custom(db, wp, wp_code)
    return CustomWpContext(
        wp=wp,
        wp_code=wp_code or "",
        sheet_name=wp_code or "",
        is_custom=is_custom,
        is_read_only=wp.status in READ_ONLY_FILE_STATUSES,
    )
