"""formula_settings.outbox 的**专用派发器自注册**（从 outbox.py 抽出，行数门禁）。

🔴 2026-11-14 解耦背景（domain-boundary 的 2 条 forbidden_edge）
=====================================================================
通用 outbox（``import_event_outbox_service._deliver``）里原先**内联**了本模块的派发
分支，于是 import-export 反向 import formula_settings，而 formula_settings.outbox 又用
``ImportEventOutboxService`` 做存储 —— 双向依赖。事件派发是开放扩展点，通用 outbox
不该知道任何具体业务域。现由本模块**自注册**：

    register_typed_deliverer("formula_config.changed", _deliver_via_registry)

行为逐字保留（含 origin 判断）：
  - ``origin == ORIGIN``（本模块入队的行）-> 调 ``deliver()`` 直接跑传播处理器，不经
    事件总线（S4 ADR-SDO-02：总线会吞异常）
  - 其他 origin（旧路径 / 非 outbox 入队的公式事件）-> 仍走事件总线

🔴 为什么单独成文件：``outbox.py`` 已 426 行（原 381），按仓库规矩（超限优先抽
伴生模块、不抬 whitelist 基线）把这段注册逻辑整段搬出。``startup_formula.py`` 导入
本模块以触发注册，并断言注册确实发生。
"""
from __future__ import annotations

# 🔴 抽模块时必须显式 import 原同文件里的符号 —— 漏了会在**运行时**才炸
# （``name 'ORIGIN' is not defined``），且表现为「派发失败」而不是 ImportError，
# 只会落在 outbox 的 last_error 里，很容易被当成业务错误。本轮实测 23 个用例因此红。
# 循环导入安全：outbox.py 在**文件末尾**才 import 本模块，此时 ORIGIN/deliver 已定义。
from app.services.formula_settings.outbox import ORIGIN, deliver


# ═══════════════════════════════════════════════════════════════════════════════
# 专用派发器自注册（🔴 2026-11-14 解耦）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 背景：通用 outbox（import_event_outbox_service._deliver）里原先**内联**了本模块的派发
# 分支，于是 import-export 反向 import formula_settings —— domain-boundary 门禁的两条
# forbidden_edge（formula -> import-export 与 import-export -> formula 双向）。
# 事件派发是开放扩展点，通用 outbox 不该知道任何具体业务域；改由本模块**自注册**。
#
# 行为保持逐字不变（含 origin 判断）：
#   - origin == ORIGIN（本模块入队的行）-> 调 deliver() 直接跑传播处理器，不经事件总线
#     （S4 ADR-SDO-02：总线会吞异常）
#   - 其他 origin（旧路径 / 非 outbox 入队的公式事件）-> 仍走事件总线


async def _deliver_via_registry(db, item, payload) -> None:
    """注册给通用 outbox 的派发器：只接管 origin 匹配本模块的行，其余交还事件总线。"""
    from app.services.event_bus import event_bus

    event_extra = dict(getattr(payload, "extra", None) or {})
    if event_extra.get("origin") != ORIGIN:
        await event_bus.publish_immediate(payload)
        return

    from app.models.audit_platform_schemas import EventType as _EventType
    from app.services.workpaper_sync.outbox import PendingPublication

    pub = PendingPublication(
        outbox_id=item.id,
        event_type=_EventType.FORMULA_CONFIG_CHANGED,
        project_id=item.project_id,
        year=item.year,
    )
    await deliver(db, pub)


def _register() -> None:
    from app.models.audit_platform_schemas import EventType as _EventType
    from app.services.import_event_outbox_service import register_typed_deliverer

    register_typed_deliverer(_EventType.FORMULA_CONFIG_CHANGED.value, _deliver_via_registry)


_register()
