"""正式导出单位策略快照的**唯一构造入口**
（spec platform-global-display-settings-closure 任务 10 / AC-21）。

背景：`ExportTask.unit_policy_snapshot`（V265 列）此前**只在模型层**，没有生产写入方
⇒ 「这份交付件是按哪个单位出的」无法审计。本模块是它的唯一生产写入方。

三条纪律：

1. **快照必须含 digest**：`canonical_snapshot`（键排序的 canonical JSON）+
   `canonical_digest`（sha256）。只存 `unit` 不存 digest 无法证明「当时算的就是这份」。
2. **构造失败要能降级**：读不到项目单位时回落 `yuan`（divisor=1，不缩放金额），
   但**在 snapshot 里注明 `fallback: true`** —— 静默回落会让「元」看起来像正常结果。
3. **快照只描述单位，不描述金额**：金额由数据本身承担，混进来会让
   「同一份 policy、不同数据量」的两次导出 digest 不同，审计时无法比对。

🔴 本模块只读 `projects.amount_unit`，不碰四表数据。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

#: Unit → divisor（与 `ledger_unit_normalization_apply.UNIT_FACTORS` 逐值一致）。
_UNIT_DIVISORS: dict[str, int] = {
    "yuan": 1,
    "qian": 1000,
    "wan": 10000,
}


def build_policy_snapshot(
    *,
    project_id: UUID,
    unit: str,
    regions: list[dict[str, Any]] | None = None,
    fallback: bool = False,
) -> str:
    """构造 `unit_policy_snapshot` 的 canonical JSON 字符串。

    Args:
        project_id: 项目 UUID（写进快照，便于事后核对「这份快照属于哪个项目」）
        unit: `yuan` / `qian` / `wan`
        regions: 可选的 region 列表（每个含 stable_id / measure_kind / ratio_scale 等）
        fallback: 是否是「读不到项目单位、回落到 yuan」的降级快照

    Returns:
        canonical JSON 字符串（键排序、无空格、含 digest）
    """
    if unit not in _UNIT_DIVISORS:
        raise ValueError(f"非法 unit {unit!r}（只接受 {sorted(_UNIT_DIVISORS)}）")
    from app.schemas.export_unit_policy import ExportUnitPolicy

    policy = ExportUnitPolicy(
        project_id=project_id,
        unit=unit,  # type: ignore[arg-type]
        divisor=_UNIT_DIVISORS[unit],
        regions=[_coerce_region(r) for r in (regions or [])],
    ).compute_digest()

    payload = json.loads(policy.canonical_snapshot)
    # 追加两个审计字段（不参与 digest 计算 —— digest 只覆盖 unit/divisor/regions，
    # 与 `ExportUnitPolicy.compute_digest` 的口径一致；改口径会让历史快照全部失效）。
    payload["_digest"] = policy.canonical_digest
    payload["_project_id"] = str(project_id)
    if fallback:
        payload["_fallback"] = True
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _coerce_region(region: dict[str, Any]) -> Any:
    """把 dict 转 `ExportUnitRegion`（缺字段时抛，不静默补默认值）。"""
    from app.schemas.export_unit_policy import ExportUnitRegion

    return ExportUnitRegion(**region)


async def resolve_policy_snapshot_for_project(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int | None = None,
    regions: list[dict[str, Any]] | None = None,
) -> str:
    """读项目单位并构造快照（**正式导出的生产入口**）。

    🔴 读不到项目单位时回落 `yuan` 并在快照里标 `_fallback: true` ——
    **不静默**。静默回落会让「元」看起来像用户选择的正常结果。

    `year` 目前不参与（项目单位是项目级不是年度级），保留参数是为了将来
    「按年度冻结单位」时不必改签名。
    """
    unit = "yuan"
    fallback = True
    try:
        row = (
            await db.execute(
                sa.text("SELECT amount_unit FROM projects WHERE id = :pid"),
                {"pid": str(project_id)},
            )
        ).first()
        if row is not None:
            raw = row[0]
            if isinstance(raw, str) and raw in _UNIT_DIVISORS:
                unit = raw
                fallback = False
    except Exception:  # noqa: BLE001 — 读不到就降级，但标 fallback
        unit = "yuan"
        fallback = True
    return build_policy_snapshot(
        project_id=project_id, unit=unit, regions=regions, fallback=fallback
    )
