"""projection lane 的**唯一**目标底稿解析：entry → 裁决码族 → 具体 `working_paper` 行。

═══ 为什么这个模块必须存在（BP-24，2026-09-05 实测）═══════════════════════════════

在建本模块之前，两个宿主各写了一份解析规则，读的是**同一份**裁决表
（`backend/data/workpaper_sync_entry_wp_code_adjudication.json`），却用**不同的全序**：

* `fix_projection_first_publication.py`
  `(has_store_payload DESC), wi.wp_code, wp.created_at, wp.id`
* `fix_task76_provision_projection_definitions.py`
  `wi.wp_code, wp.created_at, wp.id`

真库实测后果（4 个 pilot entry 里分歧 2 个）：

* **D2**：首版发布落在 `ef7f88e3`（project `2aa00f57`，`D2-detail-rows` 866,972 B），
  而 Task 76 的 provisioner 解析到 `1e171c06`（project `df5b8403`，store 为空）
  ⇒ provisioner `--check` 对**已发布**的 D2 报 `settlement=blocked` /
  `current_representation_id=null`。
* **B60**：provisioner 解析到 `afb9201a`（project `0ec33ac9`），与首版宿主不同。
* G7 / H1 恰好一致 —— 恰好，不是设计使然。

危害不止于「读数不准」：`--apply` 若照 provisioner 那份全序执行，会把 candidate /
representation 建在**另一条底稿**上，于是「Task 76 四表有真实行」与「首版已发布」
各自成立却指向不同的 wp —— 典型的假绿（两个判据分别在两个空集/异集上为真）。

⇒ 全序、裁决表读取、SQL 三者一并收敛到本模块，两个宿主 import 它，不各留一份。

═══ 为什么全序里有 `has_store_payload DESC` ══════════════════════════════════════

这一项是相对 design 的**显式偏离**，理由是实测：`H1-8-rows` 全库 0 行、
`D2-detail-rows` 有 2 行（866,972 B / 490,291 B）。纯
`wi.wp_code, wp.created_at, wp.id` 会把 D2 选到 store 为空的那条，于是首版发布出去的
是一个**空 projection** —— 管道通了，但「HTML 侧数据真的进了 OO 文件」这条判据完全
没有被验证到。加这一项后仍是**全序**、仍**确定**（同一库状态下重复运行选同一条），
只是把「有数据的那份」排在前面。

═══ 为什么候选集必须过滤到「审计师真能打开的底稿」（BP-26，2026-09-06 实测）═════════

本模块首版的 `WHERE` 只有 `wp.is_deleted = false` —— 只看**底稿自己**删没删，
不看它**所在的项目**删没删。Playwright 实测的后果：

* H1 的全序第一名是 `f663b18c`（project `df5b8403`「首汽租车_2025」，
  **`projects.is_deleted = true`**），首版 published representation 已经发在它上面；
* 而前端打开该底稿时 `GET /api/workpapers/{id}/render-config` 返回
  **404「项目已删除」** ⇒ 审计师**永远看不到**这条 representation。

于是「DB 里 published representation 存在」与「双向回写在界面上可用」这两个判据
分别在**两个异集**上为真 —— 与 BP-24 同族，但更隐蔽：BP-24 是两个宿主选到不同底稿
（比一下就发现），这一条是两个宿主**选到同一条**、只不过那条对用户不可见，
任何只查库的判据都恒绿。

为什么此前一路预演都没撞上：

* `has_store_payload DESC` **偶然**替 D2 挡住了 —— D2 在活项目那条底稿上有
  490,291 B 载荷，被排到最前；
* H1 的 `H1-8-rows` 全库 0 行载荷（裁决表自己记着 `max_payload_bytes: 0`）
  ⇒ 全序退化成 `wi.wp_code, wp.created_at, wp.id`，而**已删除的测试项目往往创建
  得最早**，于是它稳定地排第一；
* 裁决表的取证口径也漏了同一层：H1 那条 `wp_index_evidence` 写的是
  「5 行未删除、5 行有 file_path」，统计的是 `working_paper.is_deleted`，
  从未涉及所属项目。

⇒ 可见性过滤收敛成 :data:`TARGET_VISIBILITY_SQL`，与全序并列为本模块的两个真源。
它只**收窄**候选集（排除对用户不可达的底稿），不放宽任何门；
换句话说：能被选中的底稿，必须是审计师能在界面上真正打开的那种。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Sequence

import sqlalchemy as sa

#: `backend/` 根（本文件位于 `backend/app/services/workpaper_sync/`）。
_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

#: entry → wp_code 的**唯一** reviewed 真源。任何宿主都不得自造第二份解析规则。
#:
#: 曾有过三份真源（manifest 的 `wp_code_patterns` 启发式 / provider
#: `TEMPLATE_RELATIVE_PATH` 经 `_index.json` 反查 / 本裁决表），前两份各错一处：
#: 启发式产 `D2A` / `G7L` / `H1F` 三个在 `wp_index` 里 0 命中的幻影码；反查对 B60 选到
#: 「总体审计策略及具体审计计划」（5 个底稿只有 1 个有文件、且是 5749 B 占位表不含受管
#: sheet），而裁决表选的 `B60-1` 是 3 个底稿全有文件。
WP_CODE_ADJUDICATION: Final[Path] = (
    _BACKEND_ROOT / "data" / "workpaper_sync_entry_wp_code_adjudication.json"
)

#: 目标底稿的全序。改它必须同时改本模块顶部那段理由，否则下一个人会再拆成两份。
TARGET_ORDER_SQL: Final[str] = (
    "(CASE WHEN COALESCE(LENGTH(store.remark), 0) > 0 THEN 0 ELSE 1 END), "
    "wi.wp_code, wp.created_at, wp.id"
)

#: 候选底稿的**可见性**过滤（BP-26）。三层缺一不可，理由见模块顶部那一段：
#:
#: * `wp.is_deleted`  —— 底稿自身被删；
#: * `p.is_deleted`   —— 🔴 **所在项目**被删。前端 `render-config` 对这类底稿直接返回
#:   404「项目已删除」，发在它上面的 representation 审计师永远打不开；
#: * `wi.is_deleted`  —— 索引行被删（底稿不会出现在任何列表里）。
#:
#: 与 :data:`TARGET_ORDER_SQL` 并列的第二个真源：全序决定「多个可见候选里选哪个」，
#: 本常量决定「哪些候选算可见」。**不得**在宿主里各写一份，也**不得**为了让某个
#: entry 能发首版而放宽它 —— 放宽等于把「界面上打不开」重新变成不可观测。
TARGET_VISIBILITY_SQL: Final[str] = (
    "wp.is_deleted = false AND p.is_deleted = false AND wi.is_deleted = false"
)

#: 请求期按 entry 取 current representation 的全序（BP-27）。
#:
#: 与 :data:`TARGET_ORDER_SQL` **刻意分开**：那一条含 `has_store_payload DESC` 与
#: `wi.wp_code`，服务的是「发布期在码族内选宿主底稿」；这一条服务的是「同一 entry 在
#: 多个底稿实例上都有 entry_state 时，取哪一条」，此时 store 载荷偏好无从谈起
#: （`store_item_id` 不在入参里），码也已由 entry 唯一确定。
#:
#: **不**按 representation 的 generation 排 —— generation 是**每个 wp 各自**的代际
#: 计数，跨 wp 比较它没有意义（会让「另一条底稿改得更勤」变成选它的理由）。
VISIBLE_REPRESENTATION_ORDER_SQL: Final[str] = "wp.created_at, wp.id"


class ProjectionTargetResolutionError(RuntimeError):
    """目标解析失败。**不**降级为「无目标」：那会把「裁决表有问题」伪装成「本库没底稿」。"""


def load_wp_code_adjudication() -> dict[str, dict[str, Any]]:
    """读裁决表，返回 `{entry_id: 条目}`。缺文件即抛（fail closed）。

    缺文件时回落到启发式 = 把「无人裁决」伪装成「已裁决」，而启发式产的正是幻影码。
    """
    if not WP_CODE_ADJUDICATION.is_file():
        raise ProjectionTargetResolutionError(
            f"缺 wp_code 裁决表 {WP_CODE_ADJUDICATION} —— 目标解析不得回落到 "
            "`_index.json` 反查或 manifest 的 `wp_code_patterns` 启发式"
        )
    doc = json.loads(WP_CODE_ADJUDICATION.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for row in doc.get("adjudications") or []:
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            continue
        if entry_id in out:
            raise ProjectionTargetResolutionError(
                f"entry {entry_id!r} 在裁决表里出现多次 —— 一个 entry 只能有一条裁决"
            )
        out[entry_id] = row
    return out


def adjudicated_wp_codes(entry_id: str, *, adjudication: dict[str, dict[str, Any]] | None = None) -> tuple[str, ...]:
    """该 entry 的目标码族。缺条目 / 缺准入键 / 被裁决为不可定位 —— 一律抛。

    `wp_codes` 是**序列**而不是单个码：裁决表的 `wp_codes` 本就是列表，把它压成一个码
    会让「一个 entry 的宿主分布在两个码上」这种情形静默丢一半候选。

    🔴 准入键是 `resolvable_for_provisioning` 而**不是**旧的 `resolvable_today`：后者把
    两件互不相干的事混在一个布尔里 —— ①能不能为该 entry 定位宿主底稿（本函数要的）
    ②该 wp_code 能不能当 `EntryMatcher` 的域。G7 的 ② 为假（三个 entry 真码同为 G7 ⇒
    `MatcherOverlapError`），于是 ① 也被一并关掉，G7 的首版发布因此恒落
    `blocked_missing_approved_bundle`。
    缺键即抛，**不** `get(..., True)` —— 默认放行会让「裁决表漏填」被静默当成「已裁决」。
    """
    table = load_wp_code_adjudication() if adjudication is None else adjudication
    verdict = table.get(entry_id)
    if verdict is None:
        raise ProjectionTargetResolutionError(
            f"entry {entry_id!r} 在 wp_code 裁决表里没有条目 —— 宿主解析必须走显式裁决"
        )
    if "resolvable_for_provisioning" not in verdict:
        raise ProjectionTargetResolutionError(
            f"entry {entry_id!r} 的裁决条目缺 `resolvable_for_provisioning` —— "
            "该键是定位宿主的准入判据，缺键不得默认放行（fail-open）"
        )
    if not verdict["resolvable_for_provisioning"]:
        raise ProjectionTargetResolutionError(
            f"entry {entry_id!r} 被裁决为不可用于定位宿主底稿："
            f"{verdict.get('not_provisionable_reason') or '（未写明原因）'}"
        )
    codes = tuple(str(code).strip() for code in (verdict.get("wp_codes") or ()) if code)
    if not codes:
        raise ProjectionTargetResolutionError(
            f"entry {entry_id!r} 的裁决条目 `wp_codes` 为空 —— 裁决表结构错误"
        )
    return codes


async def resolve_projection_target(
    session: Any,
    *,
    wp_codes: Sequence[str],
    store_item_id: str,
    project_id: Any | None = None,
) -> Any | None:
    """按 :data:`TARGET_ORDER_SQL` 在裁决码族内选唯一目标底稿；无候选返回 `None`。

    返回行含 `wp_id` / `project_id` / `wp_code` / `rev` / `store_bytes` 五列 ——
    `store_bytes` 是全序的第一决定项，把它一并返回，调用方就不必再查一次
    （查第二次等于给「排序用的数」和「展示用的数」留出不一致的空间）。

    `store_item_id` 允许为空串：那表示该 provider 没有 store 载荷概念，此时
    `LEFT JOIN` 恒不命中、`store_bytes` 恒 0，全序退化成
    `wi.wp_code, wp.created_at, wp.id` —— 仍是全序、仍确定。
    """
    params: dict[str, Any] = {"codes": list(wp_codes), "item_id": store_item_id}
    project_clause = ""
    if project_id is not None:
        project_clause = "AND wp.project_id = :pid "
        params["pid"] = str(project_id)
    return (
        await session.execute(
            sa.text(
                "SELECT wp.id AS wp_id, wp.project_id, wi.wp_code, "
                "       COALESCE(wp.content_revision, 0) AS rev, "
                "       COALESCE(LENGTH(store.remark), 0) AS store_bytes "
                "FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                "JOIN projects p ON p.id = wp.project_id "
                "LEFT JOIN checklist_responses store "
                "       ON store.wp_id = wp.id AND store.item_id = :item_id "
                f"WHERE {TARGET_VISIBILITY_SQL} AND wi.wp_code = ANY(:codes) "
                + project_clause
                + f"ORDER BY {TARGET_ORDER_SQL} LIMIT 1"
            ),
            params,
        )
    ).first()


async def resolve_visible_current_representation_id(
    session: Any,
    *,
    entry_id: str,
) -> Any | None:
    """按 entry 取**当前** published representation id，且它必须挂在**可见**底稿上。

    ═══ 为什么这个函数必须存在（BP-27，2026-09-06 实测）═══════════════════════════

    四个 pilot 模块的 `attach_pilot_adapters()` 各写了一份**逐字相同**（md5
    `2256d0b778f0`）的查询：

    ```python
    sa.select(WorkpaperSyncEntryState.current_representation_id)
      .where(WorkpaperSyncEntryState.entry_id == PILOT_ENTRY_ID)
      ... .first()
    ```

    三个问题叠在一起：

    1. `working_paper_sync_entry_state` 的主键是 **`(wp_id, entry_id)`** ⇒ 同一个 entry
       在多个底稿实例上有状态是**合法设计**。只按 `entry_id` 过滤会命中多行；
    2. 没有 `ORDER BY` 而取 `.first()` ⇒ **取哪一条不确定**（PG 不保证顺序）；
    3. 不看底稿/项目是否可见 ⇒ 可能取到挂在**已删项目**上的那条。

    H1 实测正好三条全中：BP-26 修复后在活项目 `c71b7c54` 上发了新首版，而旧的
    `f663b18c`（项目「首汽租车_2025」`is_deleted=true`）那条 entry_state **仍在**
    ⇒ 同一 entry 两行，`.first()` 可能把 adapter 绑到前端 404 的那份 representation 上。

    这比 BP-26 更要紧：BP-26 在**宿主脚本**里（发布期，人看着报告跑），这一条在
    **生产请求路径**上（`wp_sync_router` 的 `_attach_pilot_adapters` /
    `_apply_durable_incoming`），错了就是审计师的请求静默绑到看不见的底稿。

    ⇒ 收敛成一处，并复用 :data:`TARGET_VISIBILITY_SQL` —— 与 BP-24 同一教训：
    四份副本必漂移，而「可见」的定义只能有一个。

    全序：可见性过滤之后按 `wp.created_at, wp.id` 定序（确定，且同一库状态重复调用
    必选同一条）。**不**按 representation 的 generation 排 —— generation 是**每个 wp
    各自**的代际计数，跨 wp 比它没有意义。
    """
    # 🔴 参数用 `.bindparams()` 而不是 `execute(stmt, params)` 的第二个位置参数：
    #    本函数被四个 pilot 的 `attach_pilot_adapters()` 调用，而它们的单测用
    #    `_StubSession.execute(self, stmt)`（**只收一个**位置参数）。传两个会让
    #    Tasks 40~43 的 67 个用例集体 `TypeError`（首版实测），而那是测试替身的契约、
    #    不是生产缺陷 —— 与其去改四份 stub，不如让语句自带参数。
    statement = sa.text(
        "SELECT s.current_representation_id AS rid "
        "FROM working_paper_sync_entry_state s "
        "JOIN working_paper wp ON wp.id = s.wp_id "
        "JOIN wp_index wi ON wi.id = wp.wp_index_id "
        "JOIN projects p ON p.id = wp.project_id "
        "WHERE s.entry_id = :entry_id "
        "  AND s.current_representation_id IS NOT NULL "
        f"  AND {TARGET_VISIBILITY_SQL} "
        f"ORDER BY {VISIBLE_REPRESENTATION_ORDER_SQL} LIMIT 1"
    ).bindparams(entry_id=str(entry_id))
    # 🔴 `.scalars().first()` 而不是 `.first()`：与被替换的原实现形态一致。
    #    Tasks 40~43 的 `_StubSession` 返回的 result 其 `.first()` 直接给**标量**
    #    （不是 Row），按 `row.rid` 取属性会 `AttributeError: 'UUID' object has no
    #    attribute 'rid'`（首版实测）。单列查询用 scalars 也更贴合语义。
    return (await session.execute(statement)).scalars().first()


async def count_candidates_hidden_by_visibility(
    session: Any,
    *,
    wp_codes: Sequence[str],
    project_id: Any | None = None,
) -> int:
    """码族内被 :data:`TARGET_VISIBILITY_SQL` 排除掉的候选条数。

    存在的理由是**报告不得说谎**（BP-26）：加上可见性过滤后，某个 entry 可能从
    「有目标」变成「无目标」。此时若宿主只会报「本库没有承载它的底稿」，读报告的人
    会去建底稿 —— 而真实情况是底稿有、只是它所在的项目已被删除，解除动作完全不同
    （恢复项目 / 换目标项目）。这正是本模块顶部反对的那类误导性兜底。

    只读、只 count，不参与选择 —— 选择仍只由 `resolve_projection_target` 一处决定。
    """
    params: dict[str, Any] = {"codes": list(wp_codes)}
    project_clause = ""
    if project_id is not None:
        project_clause = "AND wp.project_id = :pid "
        params["pid"] = str(project_id)
    row = (
        await session.execute(
            sa.text(
                "SELECT count(*) AS hidden "
                "FROM working_paper wp "
                "JOIN wp_index wi ON wi.id = wp.wp_index_id "
                "JOIN projects p ON p.id = wp.project_id "
                f"WHERE NOT ({TARGET_VISIBILITY_SQL}) AND wi.wp_code = ANY(:codes) "
                + project_clause
            ),
            params,
        )
    ).first()
    return int(row.hidden) if row is not None else 0
