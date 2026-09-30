"""store_mirror —— 把 Projection 镜像进 HTML store（checklist_responses）的**会话无关**执行层。

═══ 为什么单独成模块 ═══

「把一个 Projection 按 provider 分发、逐 store item merge 后写回 checklist_responses」这件事
有**两个**触发方，方向相同、数据源不同：

* OO callback 落地（`OoToHtmlCoordinator._mirror_store_backed_if_needed`）——
  数据源是三路合并后的 **merged incoming** projection；
* 反向收敛端点（`adopt-substrate`，spec workpaper-sync-managed-row-convergence）——
  数据源是 **published substrate** 的 extract。

两者若各写一套「按 `store_item_registry` 分发 + 逐 item SELECT/merge/UPSERT」的镜像逻辑，
就是平台明令禁止的第二真源（将来 provider 门面命名/新增 dedicated item 时两处必然漂移）。
故把执行层抽到这里：入参只有 `(session, adapter_id, project_id, wp_id, merged_projection)`，
不依赖任何 coordinator 状态。`OoToHtmlCoordinator` 的三个 `_mirror_*` 方法改为**薄转发**，
逐字节等价（本模块函数体即从那三个方法机械搬来，仅把 `self._session`→`session`、
`state.frozen.X`→入参）。

🔴 三态语义原样保留（这是本模块存在的初衷之一，不得弱化）：
  plan 命中 → 镜像；`store_merge_plan_or_skip` 返回 None（不像 adapter_id）→ 跳过；
  像 adapter_id 却未注册 → 抛错（D4-35 恒空 / D4-13 正文写不进 OO 的根因形态）。
"""

from __future__ import annotations

import json  # 🔴 模块级：三个 _mirror_* 函数都用 json.loads/dumps。原 oo_to_html 里
#            `_mirror_dedicated_dict_stores` 靠外层类作用域的 import json 可见，搬成独立
#            模块函数后必须显式在模块级 import（否则该函数内 json.loads 抛 NameError ——
#            这是抽取时的搬移缺陷，adopt 首次真调即触发 500）。
from typing import Any

import sqlalchemy as sa


# ===== 来自 oo_to_html.py L2571~L2681（_mirror_store_backed_if_needed）=====
async def mirror_projection_into_store(
    session: Any, *, adapter_id: str, project_id: Any, wp_id: Any, merged_projection: Any, commit: bool = True
) -> None:
    """Store-backed pilot：把 merged projection 镜像进 checklist_responses。

    统一路径只提交 content_version；D2/H1 宿主 ``reloadHtml`` 仍读 checklist。
    不镜像则 OO 受管格回写对结构化视图不可见（§9.6）。
    """
    # 🔴 注册表查表取代原 9 分支 `elif adapter_id == "…"` 链（spec
    #    d1-sync-row-table-engine-and-d1-coverage Task 13 / 需求 3.1）。
    #    原链「未命中 ⇒ 静默 return」正是 D4-35 恒空 / D4-13 正文写不进 OO 两个已修 bug 的
    #    根因形态；改为 O(1) dict 查表 + 未命中显式抛错（含已注册清单，需求 3.4）。
    #    非 store-backed adapter 须在注册表的 NON_STORE_BACKED_ADAPTERS 里**显式登记**，
    #    不得靠「查不到就跳过」蒙混过关。
    import importlib

    from app.services.workpaper_sync.store_item_registry import store_merge_plan_or_skip

    adapter_id = str(adapter_id)
    # 三态：plan / None（不是 adapter_id ⇒ 本就无 store 计划，跳过）/ 抛错（像 adapter_id
    # 却未注册 ⇒ 真漏接，D4-35 恒空的根因形态，必须显式打红）。
    plan = store_merge_plan_or_skip(adapter_id)
    if plan is None:
        return
    bridge = importlib.import_module(
        f"app.services.workpaper_sync.{plan.provider_module}"
    )
    if plan.dual_store_fn:
        # 多 store item 的整体镜像走 provider 专用门面（D4 的 _mirror_d4_dual_stores 同型）。
        await _mirror_dual_stores(
            session, adapter_id=adapter_id, project_id=project_id, wp_id=wp_id, merged_projection=merged_projection, bridge=bridge, plan=plan, commit=commit
        )
        return
    store_item_id = bridge.STORE_ITEM_ID
    if plan.merge_state_fn:
        merge_kind = "state"
        merge_state_fn = getattr(bridge, plan.merge_state_fn)
    else:
        merge_kind = "rows"
        merge_rows_fn = getattr(bridge, plan.merge_rows_fn)

    import json

    raw = (
        await session.execute(
            sa.text(
                "SELECT remark FROM checklist_responses "
                "WHERE wp_id = :wp AND item_id = :item"
            ),
            {"wp": str(wp_id), "item": store_item_id},
        )
    ).scalar_one_or_none()
    if merge_kind == "state":
        base_state: dict | None = None
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    base_state = parsed
            except (TypeError, ValueError):
                base_state = None
        merged_payload, applied, _visited = merge_state_fn(
            projection=merged_projection, base_state=base_state
        )
        if applied <= 0 and base_state:
            return
        payload = json.dumps(merged_payload, ensure_ascii=False)
    else:
        base_rows: list = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    base_rows = parsed
            except (TypeError, ValueError):
                base_rows = []
        merged_rows, applied, _visited, _touched = merge_rows_fn(
            projection=merged_projection, base_rows=base_rows
        )
        if applied <= 0 and base_rows:
            # 投影相对 store 无字段变化时仍允许跳过写库（避免无意义大 JSON 刷新）
            return
        payload = json.dumps(merged_rows, ensure_ascii=False)
    updated = (
        await session.execute(
            sa.text(
                "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                "WHERE wp_id = :wp AND item_id = :item"
            ),
            {
                "val": payload,
                "wp": str(wp_id),
                "item": store_item_id,
            },
        )
    ).rowcount
    if not updated:
        await session.execute(
            sa.text(
                "INSERT INTO checklist_responses "
                "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
            ),
            {
                "pid": str(project_id),
                "wp": str(wp_id),
                "item": store_item_id,
                "val": payload,
            },
        )
    if commit:
        await session.commit()


# ===== 来自 oo_to_html.py L2683~L2764（_mirror_dedicated_dict_stores）=====
async def _mirror_dedicated_dict_stores(
    session: Any, *, adapter_id: str, project_id: Any, wp_id: Any, merged_projection: Any, commit: bool = True
) -> None:
    """按注册表 `dedicated_items` 清单逐条镜像 dict/list store（Task 13 收敛）。

    取代原 6 段几乎逐字重复的 `hasattr(bridge, ...)` 试探代码。每条的行为与原对应段
    逐字节一致：同一条 SELECT/UPDATE/INSERT SQL、同一个「applied<=0 且已有基线则跳过
    写库」判断（dict 基线用 `is not None`、list 基线用真值判断——D4-8 是全仓唯一 list
    基线，空列表 `[]` 也应触发跳过，这条差异原样保留，不强行统一）、同一个 per-item commit。
    """
    from app.services.workpaper_sync.store_item_registry import STORE_MERGE_REGISTRY

    plan = STORE_MERGE_REGISTRY.get(adapter_id)
    if plan is None or not plan.dedicated_items:
        return

    import importlib

    for dedicated in plan.dedicated_items:
        module = importlib.import_module(
            f"app.services.workpaper_sync.{dedicated.provider_module}"
        )
        if not (hasattr(module, dedicated.merge_fn) and hasattr(module, dedicated.item_id_const)):
            # 与原 hasattr 试探等价的兜底：provider 未提供该门面则跳过（不是"漏注册"，
            # 是"注册表登记了但 provider 侧尚未实现"——两者观测面不同，保持跳过而非报错，
            # 因为原代码本就是 hasattr 试探式的软跳过，不是这次改动引入的新语义）。
            continue
        item_id = getattr(module, dedicated.item_id_const)
        merge_fn = getattr(module, dedicated.merge_fn)
        raw = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item"
                ),
                {"wp": str(wp_id), "item": item_id},
            )
        ).scalar_one_or_none()
        base_state: dict | list | None = None
        if raw:
            try:
                parsed = json.loads(raw)
                if dedicated.base_kind == "dict" and isinstance(parsed, dict):
                    base_state = parsed
                elif dedicated.base_kind == "list" and isinstance(parsed, list):
                    base_state = parsed
            except (TypeError, ValueError):
                base_state = None
        merged_payload, applied, _visited = merge_fn(
            projection=merged_projection, base_state=base_state
        )
        if dedicated.base_kind == "list":
            skip = applied <= 0 and base_state  # 原 D4-8 段：真值判断（空列表也跳过）
        else:
            skip = applied <= 0 and base_state is not None  # 原其余 5 段：is not None
        if skip:
            continue
        payload = json.dumps(merged_payload, ensure_ascii=False)
        updated = (
            await session.execute(
                sa.text(
                    "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                    "WHERE wp_id = :wp AND item_id = :item"
                ),
                {"val": payload, "wp": str(wp_id), "item": item_id},
            )
        ).rowcount
        if not updated:
            await session.execute(
                sa.text(
                    "INSERT INTO checklist_responses "
                    "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
                ),
                {
                    "pid": str(project_id),
                    "wp": str(wp_id),
                    "item": item_id,
                    "val": payload,
                },
            )
        if commit:
            await session.commit()


# ===== 来自 oo_to_html.py L2766~L3042（_mirror_d4_dual_stores）=====
async def _mirror_dual_stores(
    session: Any, *, adapter_id: str, project_id: Any, wp_id: Any, merged_projection: Any, bridge: Any, plan: Any = None, commit: bool = True
) -> None:
    """多 store item 整体镜像：按 table 前缀分别 merge 后写回各自 checklist item。

    🔴 泛化（spec workpaper-sync-registration-isolation）：`plan.merge_all_fn` 动态取
    bridge 上的 merge 函数名，取代硬编码 `bridge.merge_projection_into_all_d4_stores`。
    D4 行为逐字节不变（`merge_all_fn` 默认值就是 `merge_projection_into_all_d4_stores`）。
    """
    import json

    # dict store（D4-9 {current,prior}+totals / D4-33 {bizTypes,months,priorYear} /
    # D4-34 {rentals,consults}）不走本 rows 循环，由下方各自专用 dict 块单独处理
    # （同 D4-35 STORE_ITEM_ID_D435_DICT）。它们在 STORE_ITEM_IDS 里（combined projection 需要），
    # 但 merge_projection_into_all_d4_stores 不产出它们，故这里从 base_by_item 构造中跳过。
    _dict_store_items = {
        str(getattr(bridge, name, "") or "")
        for name in (
            "STORE_ITEM_ID_D49_DICT",
            "STORE_ITEM_ID_D433_DICT",
            "STORE_ITEM_ID_D434_DICT",
            "STORE_ITEM_ID_D436_DICT",
            # D4-8（list 形态 ProductData[]）走专用块（3-tuple 门面 merge_d48_from_projection），
            # merge_projection_into_all_d4_stores 不产出它，故从 rows 循环 base 构造排除。
            "STORE_ITEM_ID_D48_DICT",
        )
    }
    # D4-7 两 item（products / monthly）也走专用块，从 rows 循环 base 构造中排除
    _dict_store_items |= {str(s) for s in getattr(bridge, "STORE_ITEM_IDS_D47_DEDICATED", ()) or ()}
    # 🔴 纯文本固定项（D4-5 业务场景 / D4-13 核对过程·结论）与 D4-35 dict-store 也各走专用块
    #    （见下方 merge_d45_fixed / merge_d413_fixed / merge_d435 分支），从 rows 循环 base
    #    构造中排除——否则它们会被当成行数组 base，与专用块重复处理。
    _dict_store_items |= {str(s) for s in getattr(bridge, "STORE_ITEM_IDS_D45_FIXED", ()) or ()}
    _dict_store_items |= {str(s) for s in getattr(bridge, "STORE_ITEM_IDS_D413_FIXED", ()) or ()}
    _dict_store_items.add(str(getattr(bridge, "STORE_ITEM_ID_D435_DICT", "") or ""))
    _dict_store_items.discard("")
    # 🔴 rows 循环的**基础集合**取 provider 单一口径 `all_store_item_ids()`（与出方向
    #    store_projection_response 同源，Requirement 3.1「两方向不得各自维护并集」），
    #    再显式减去上面所有走专用块的 item。老 provider 无该函数则回退 STORE_ITEM_IDS。
    _all_ids_fn = getattr(bridge, "all_store_item_ids", None)
    _rows_loop_item_ids = (
        tuple(_all_ids_fn()) if callable(_all_ids_fn) else tuple(bridge.STORE_ITEM_IDS)
    )
    base_by_item: dict[str, Any] = {}
    for item_id in _rows_loop_item_ids:
        if item_id in _dict_store_items:
            continue
        raw = (
            await session.execute(
                sa.text(
                    "SELECT remark FROM checklist_responses "
                    "WHERE wp_id = :wp AND item_id = :item"
                ),
                {"wp": str(wp_id), "item": item_id},
            )
        ).scalar_one_or_none()
        # 🔴 base 可能是 list（rows-store）或 dict（D4-10 {rows,...} / D4-30
        # {customers,customDimensions} / D4-31 singleton）——两者都要透传给
        # merge，否则 dict-store 的表级标量（totalAmount 等）会因基线被降为 [] 而丢失。
        base_payload: Any = []
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, (list, dict)):
                    base_payload = parsed
            except (TypeError, ValueError):
                base_payload = []
        base_by_item[item_id] = base_payload

    # 🔴 泛化：按 plan.merge_all_fn 动态取 bridge 上的 merge 函数（D4 默认值不变）。
    _merge_all_fn_name = getattr(plan, "merge_all_fn", "merge_projection_into_all_d4_stores") or "merge_projection_into_all_d4_stores"
    _merge_all_fn = getattr(bridge, _merge_all_fn_name)
    updates = _merge_all_fn(
        projection=merged_projection, base_by_item=base_by_item
    )
    wrote_any = False
    for item_id, (merged_rows, applied, _visited, _touched) in updates.items():
        base_rows = base_by_item.get(item_id) or []
        if applied <= 0 and base_rows:
            continue
        if applied <= 0 and not merged_rows:
            continue
        payload = json.dumps(merged_rows, ensure_ascii=False)
        updated = (
            await session.execute(
                sa.text(
                    "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                    "WHERE wp_id = :wp AND item_id = :item"
                ),
                {
                    "val": payload,
                    "wp": str(wp_id),
                    "item": item_id,
                },
            )
        ).rowcount
        if not updated:
            await session.execute(
                sa.text(
                    "INSERT INTO checklist_responses "
                    "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
                ),
                {
                    "pid": str(project_id),
                    "wp": str(wp_id),
                    "item": item_id,
                    "val": payload,
                },
            )
        wrote_any = True
    if wrote_any:
        if commit:
            await session.commit()

    # D4-5 固定 item（纯文本 remark）
    if hasattr(bridge, "merge_d45_fixed_from_projection") and hasattr(
        bridge, "STORE_ITEM_IDS_D45_FIXED"
    ):
        base_fixed: dict[str, str | None] = {}
        for item_id in bridge.STORE_ITEM_IDS_D45_FIXED:
            raw = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item"
                    ),
                    {"wp": str(wp_id), "item": item_id},
                )
            ).scalar_one_or_none()
            base_fixed[item_id] = raw if isinstance(raw, str) else None
        fixed_updates = bridge.merge_d45_fixed_from_projection(
            projection=merged_projection, base_by_item=base_fixed
        )
        for item_id, text in fixed_updates.items():
            updated = (
                await session.execute(
                    sa.text(
                        "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                        "WHERE wp_id = :wp AND item_id = :item"
                    ),
                    {
                        "val": text,
                        "wp": str(wp_id),
                        "item": item_id,
                    },
                )
            ).rowcount
            if not updated:
                await session.execute(
                    sa.text(
                        "INSERT INTO checklist_responses "
                        "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
                    ),
                    {
                        "pid": str(project_id),
                        "wp": str(wp_id),
                        "item": item_id,
                        "val": text,
                    },
                )
        if fixed_updates:
            if commit:
                await session.commit()

    # D4-13 固定 item（核对过程/核对结论，纯文本 remark）—— 与 D4-5 固定 item 同构。
    if hasattr(bridge, "merge_d413_fixed_from_projection") and hasattr(
        bridge, "STORE_ITEM_IDS_D413_FIXED"
    ):
        base_fixed_d413: dict[str, str | None] = {}
        for item_id in bridge.STORE_ITEM_IDS_D413_FIXED:
            raw = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item"
                    ),
                    {"wp": str(wp_id), "item": item_id},
                )
            ).scalar_one_or_none()
            base_fixed_d413[item_id] = raw if isinstance(raw, str) else None
        fixed_updates_d413 = bridge.merge_d413_fixed_from_projection(
            projection=merged_projection, base_by_item=base_fixed_d413
        )
        for item_id, text in fixed_updates_d413.items():
            updated = (
                await session.execute(
                    sa.text(
                        "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                        "WHERE wp_id = :wp AND item_id = :item"
                    ),
                    {
                        "val": text,
                        "wp": str(wp_id),
                        "item": item_id,
                    },
                )
            ).rowcount
            if not updated:
                await session.execute(
                    sa.text(
                        "INSERT INTO checklist_responses "
                        "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
                    ),
                    {
                        "pid": str(project_id),
                        "wp": str(wp_id),
                        "item": item_id,
                        "val": text,
                    },
                )
        if fixed_updates_d413:
            if commit:
                await session.commit()

    # D4-35 dict store（{rows, sampling, periodAmount}）：只 merge rows，保留 sampling/periodAmount
    # 🔴 原 6 段几乎逐字重复的 hasattr 试探代码（D4-35/D4-9/D4-8/D4-33/D4-34/D4-36）已收敛
    # 为注册表驱动的统一循环（Task 13 / 需求 3.1 / 3.2）：`hasattr(bridge, "merge_d*")
    # and hasattr(bridge, "STORE_ITEM_ID_D*_DICT")` 式试探改成显式声明
    # `STORE_MERGE_REGISTRY["d4.revenue_detail"].dedicated_items`，未声明的 item 不会被
    # 静默尝试（原判据本就是"存在就跑"，收敛后行为等价：注册表里的清单与原 hasattr 目标
    # 逐个对应，零增减）。逐条 SQL 语句与提交时机保持逐字节不变，只把判断入口从运行时
    # hasattr 探测改成注册表登记。
    await _mirror_dedicated_dict_stores(session, adapter_id=adapter_id, project_id=project_id, wp_id=wp_id, merged_projection=merged_projection, commit=commit)

    # D4-7 两 store item（D4-7-products 行数组 + D4-7-monthly 标量对象）：同 sheet 1 dynamic + 1 static，
    # 由专用块同时处理两 item（不进 rows 4-tuple 循环）。§一月度静态 cell 随 §二产品 binding 一起被
    # 纳入受管坐标，两 item 的投影都在 merged_projection 里，按 (payload, applied) 逐 item 写回。
    if hasattr(bridge, "merge_d47_from_projection") and hasattr(
        bridge, "STORE_ITEM_IDS_D47_DEDICATED"
    ):
        d47_base: dict = {}
        for item_id in bridge.STORE_ITEM_IDS_D47_DEDICATED:
            raw = (
                await session.execute(
                    sa.text(
                        "SELECT remark FROM checklist_responses "
                        "WHERE wp_id = :wp AND item_id = :item"
                    ),
                    {"wp": str(wp_id), "item": item_id},
                )
            ).scalar_one_or_none()
            d47_base[item_id] = raw if isinstance(raw, str) and raw.strip() else None
        d47_updates = bridge.merge_d47_from_projection(
            projection=merged_projection, base_by_item=d47_base
        )
        d47_wrote = False
        for item_id, (merged_payload, applied) in d47_updates.items():
            # 无投影覆盖且已有基线 → 不写（避免把已有 store 覆空）
            if applied <= 0 and d47_base.get(item_id) is not None:
                continue
            payload = json.dumps(merged_payload, ensure_ascii=False)
            updated = (
                await session.execute(
                    sa.text(
                        "UPDATE checklist_responses SET remark = :val, updated_at = now() "
                        "WHERE wp_id = :wp AND item_id = :item"
                    ),
                    {"val": payload, "wp": str(wp_id), "item": item_id},
                )
            ).rowcount
            if not updated:
                await session.execute(
                    sa.text(
                        "INSERT INTO checklist_responses "
                        "(id, project_id, wp_id, item_id, remark, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :pid, :wp, :item, :val, now(), now())"
                    ),
                    {
                        "pid": str(project_id),
                        "wp": str(wp_id),
                        "item": item_id,
                        "val": payload,
                    },
                )
            d47_wrote = True
        if d47_wrote:
            if commit:
                await session.commit()
