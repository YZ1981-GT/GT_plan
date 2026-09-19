"""公式运行时三张 0 行表的定性登记（单一真源）。

spec: formula-management-runtime-closure Task 11（Requirements 6.6 / Property 18）

2026-08-06 全链只读实证：``cross_check_results`` / ``draft_marker`` /
``formula_runtime_outbox`` **各 0 行**。

🔴 **「表在但空」是最坏状态** —— 它同时具备两个坏性质：

1. 看起来功能已实现（表建好了、读写方都在），实则整条链路没有数据流经过；
2. 没有任何东西提醒后来者「这里其实是空转」，下个会话要么当成已完成、
   要么误判成死代码删掉。

故本模块给每张表登记 ``{判据, 处置, 读方, 写方, 实测日期}``，
并由 ``test_formula_type_runtime_status.py`` 钉死：

- 三张表齐备（条目数固定）；
- **处置取值域只有 ``接线`` / ``保留待接线``，不含 ``弃用``**
  —— 三张表都有生产读写方，删表会打断已实现的链路；
- 每条的判据与实测状态非空且带日期（防条目退化成占位）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 处置取值域。**刻意不含 `'弃用'`**（Property 18）：三张表都有生产读/写方。
Disposition = Literal["接线", "保留待接线"]

#: 允许的处置取值（守卫按它做取值域断言）。
ALLOWED_DISPOSITIONS: frozenset[str] = frozenset({"接线", "保留待接线"})


@dataclass(frozen=True)
class RuntimeTableStatus:
    """一张公式运行时表的定性登记。"""

    table: str
    #: 为什么保留 / 为什么可接线（必须写出读写方这一硬判据）
    basis: str
    disposition: Disposition
    #: 生产读方（`backend/app/**` 非测试）
    readers: tuple[str, ...]
    #: 生产写方
    writers: tuple[str, ...]
    #: 实测状态，必须含实测日期（守卫断言含 `2026-`）
    measured: str


FORMULA_RUNTIME_TABLE_STATUS: tuple[RuntimeTableStatus, ...] = (
    RuntimeTableStatus(
        table="cross_check_results",
        basis=(
            "有两个生产读方（wp_cross_check_service / wp_quality_score_service），"
            "而 logic_check 链路只 return 不 INSERT ⇒ 缺的是写入路径不是表"
        ),
        disposition="接线",
        readers=(
            "app/services/wp_cross_check_service.py",
            "app/services/wp_quality_score_service.py",
        ),
        writers=(
            "app/services/wp_cross_check_service.py（既有，与 logic_check 链路无关）",
            "app/services/formula_management/logic_check.py"
            "::persist_cross_check_results（本 spec Task 10 新增）",
        ),
        measured=(
            "2026-08-06 实测 0 行；2026-08-07 本 spec Task 10 已接线，"
            "GET /api/projects/{pid}/formula/report-cross-check 每次执行 upsert 7 条"
        ),
    ),
    RuntimeTableStatus(
        table="draft_marker",
        basis=(
            "唯一写方 DraftRefreshOrchestrator 已实现，前端 GtRefreshScopeDialog.vue "
            "有用户入口；空是因为上游 wp_formula 无公式定义 ⇒ 不是链路缺陷"
        ),
        disposition="保留待接线",
        readers=("app/services/draft_refresh/*",),
        writers=("app/services/draft_refresh/* (DraftRefreshOrchestrator)",),
        measured=(
            "2026-08-06 实测 0 行；本 spec Task 8 收敛用户公式进 wp_formula 后，"
            "用户保存一条公式并触发草稿刷新即会产生首行（Task 18 往返实测验证）"
        ),
    ),
    RuntimeTableStatus(
        table="formula_runtime_outbox",
        basis=(
            "唯一写方 formula_runtime/outbox.py 已实现；空的成因同 draft_marker "
            "（上游无公式定义），删表会打断已实现的 outbox 投递链"
        ),
        disposition="保留待接线",
        readers=("app/services/formula_runtime/outbox.py",),
        writers=("app/services/formula_runtime/outbox.py",),
        measured=(
            "2026-08-06 实测 0 行；依赖 mutation plan 产出非空 mutations，"
            "而后者依赖 wp_formula 有活数据（Task 8 已打通存储侧）"
        ),
    ),
)


def status_of(table: str) -> RuntimeTableStatus | None:
    """按表名取登记条目；未登记返回 ``None``（调用方决定是否打红）。"""
    for entry in FORMULA_RUNTIME_TABLE_STATUS:
        if entry.table == table:
            return entry
    return None


def registered_tables() -> tuple[str, ...]:
    """已登记的表名（守卫用它做集合精确相等断言）。"""
    return tuple(e.table for e in FORMULA_RUNTIME_TABLE_STATUS)
