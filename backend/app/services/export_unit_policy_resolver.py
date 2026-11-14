"""正式导出单位策略的唯一解析入口（spec platform-global-display-settings-closure 任务 10）。

## 为什么需要这个模块

`app/schemas/export_unit_policy.py` 里的 `ExportUnitPolicy` / `ExportUnitRegion` /
`build_policy` 此前是**孤岛**：`git grep "from app.schemas.export_unit_policy" -- backend/app`
零命中、`ExportUnitRegion` 在 `backend/app/services` 零命中。结果是：

- 屏幕上的金额按账号偏好换算（`utils/formatMeasure.ts` 读 `displayPrefs.unitDivisor`）；
- 导出的文件**永远是元**，而且大多数 sink 连单位标注都没有。

用户按万元看数、导出的却是元值，文件里也不写单位 —— 这是最容易被带进正式交付件的一类错。

## 设计要点（对齐 `note_table_measure_catalog` 的正面样板）

1. **唯一读取 `projects.amount_unit` 的地方**：其它 service 不允许自己查这一列，
   一律经本模块拿 policy。这样「口径漂移」只可能发生在一个文件里。
2. **读取层未命中显式降级**：项目不存在 / amount_unit 非法 ⇒ 回落到 `yuan`
   （fail-safe：绝不因为配置读不到就把金额缩小 10000 倍），但**不做静默猜测** ——
   调用方可从返回的 policy 看到实际用的单位。
3. **纯函数式**：`build_policy` 本身无 IO，本模块只是「查库 → 调 build_policy」。
4. **不读 displayPrefs**：个人显示偏好属于屏幕口径，进入正式导出就必须是项目口径
   （requirements AC-20）。

Requirements: AC-19~AC-22、AC-23（B/C 部分）
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.export_unit_policy import (
    UNIT_DIVISORS,
    ExportUnitPolicy,
    ExportUnitRegion,
    build_policy,
)

#: 允许的导出单位（与 `export_unit_policy.AmountUnit` 逐值对应）。
#: 守卫 `test_export_unit_policy_wiring.py` 断言本集合 == `UNIT_DIVISORS` 的键集合，
#: 防止 schema 新增单位而解析层漏掉（漏掉会静默落到 yuan）。
ALLOWED_UNITS: frozenset[str] = frozenset({"yuan", "qian", "wan"})

assert set(ALLOWED_UNITS) == set(UNIT_DIVISORS), "ALLOWED_UNITS 与 schema 的 UNIT_DIVISORS 必须逐值一致"


async def resolve_project_amount_unit(
    db: AsyncSession, project_id: uuid.UUID | None
) -> str:
    """读取项目的正式导出单位，读不到 / 非法时回落 `yuan`（不放大也不缩小金额）。

    回落而不是抛错的理由：导出是只读下游动作，一次配置缺失不应该让用户拿不到文件；
    但回落到 `yuan` 是**不改变数值**的安全方向 —— 若回落成 `wan` 会把金额缩小一万倍。
    """
    if project_id is None:
        return "yuan"
    try:
        from app.models.core import Project  # 局部导入，避免 core 与本模块的循环

        row = await db.execute(
            select(Project.amount_unit).where(Project.id == project_id)
        )
        unit = row.scalar_one_or_none()
    except Exception:  # noqa: BLE001 — 配置读不到不应阻断导出（方向已选为安全的 yuan）
        return "yuan"
    if not unit or unit not in ALLOWED_UNITS:
        return "yuan"
    return str(unit)


async def resolve_export_policy(
    db: AsyncSession,
    project_id: uuid.UUID | None,
    *,
    regions: list[ExportUnitRegion] | None = None,
) -> ExportUnitPolicy:
    """给正式导出 sink 构造单位策略（唯一入口）。

    Args:
        project_id: 所属项目；None 时按 `yuan`（例如无项目上下文的单机导出）。
        regions: 逐区域的 measure kind / ratio scale（由调用方按自己的表结构给；
            拿不到就传 `[]` —— 此时只按整份文件的统一单位换算）。
    """
    unit = await resolve_project_amount_unit(db, project_id)
    return build_policy(project_id or uuid.UUID(int=0), unit, regions or [])  # type: ignore[arg-type]


async def resolve_project_id_for_wp_index(
    db: AsyncSession, wp_index_id: uuid.UUID | None
) -> uuid.UUID | None:
    """从 `wp_index.id` 反查 `project_id`（底稿类导出 sink 的入口）。"""
    if wp_index_id is None:
        return None
    try:
        from app.models.workpaper_models import WpIndex

        row = await db.execute(
            select(WpIndex.project_id).where(WpIndex.id == wp_index_id)
        )
        return row.scalar_one_or_none()
    except Exception:  # noqa: BLE001
        return None


__all__ = [
    "ALLOWED_UNITS",
    "resolve_export_policy",
    "resolve_project_amount_unit",
    "resolve_project_id_for_wp_index",
]