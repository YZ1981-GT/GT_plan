"""adopt 删除侧的**应用**与提交前复读比对（Task 6.3）＋ 变更口径与审计 details（Task 6.4 / 6.5）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 1.1 / 1.2 / 1.8 / 3.5 / 3.6 / 6.9 ·
ADR-AOS-001（后置 prune）· ADR-AOS-002（作用域 = declared_table ∩ 本 row_section）

🔴 Task 6.4 / 6.5 的四个纯函数在**本文件末尾**（`changed_items_from_plan` /
`rollback_snapshot_items` / `skipped_items_wire` / `audit_details_for_applied`），
落点理由与三条裁定见那一节的抬头注释与各自 docstring。

═══ 🔴 顺序不可调换：删除侧必须在 merge **之后** ═══

调用点（`adopt_substrate_response.compute_adopt_substrate`）的顺序是

    mirror_projection_into_store(..., commit=False)   ← 追加 + 更新 + 幽灵行门
    apply_overwrite_deletions(...)                    ← 本模块：只做删除侧
    _snapshot_store(...)                              ← 复读（同事务）
    verify_applied_plan(...)                          ← 与 plan 比对，不符即 rollback

**前置清 base 会让幽灵行门全面生效**（ADR-AOS-001 否决方案 3 的实证理由）：清空 base 之后
projection 里**每一行**都变成「本次新增身份」，于是 merge 私有的那两处 `continue` 会把锚点
业务名为空的行**全部**剔除 —— 探针用例 E（「已存在行被清空是合法编辑、不剔除」）那一类行
会被错误地降级成用例 B（「新增且无名 ⇒ 剔除」）来处理。结果是「覆盖」变成**大面积静默少写**。
后置 prune 不改变「谁是新增身份」的判定 ⇒ 幽灵行门语义**完全不变**（Requirement 2 的保护区
一个字节都不碰：本模块不 import `store_mirror`、不 import `oo_to_html`）。

═══ 🔴 幽灵行是**观测**出来的，不是预测出来的 ═══

`OverwritePlan.rows_ghost_dropped` 在**计划期恒空**，裁定与依据见
`adopt_overwrite_compute.compute_overwrite_plan` 的 docstring：幽灵行门的三个输入
（`spec` + `managed_field_specs` 的锚点 json_path / merge **之后**的行 / merge 私有的两处
`continue`）没有一个在计划函数的输入面上 ⇒ 预测就是复现引擎判据 = 第二真源。

本模块兑现它给出的**零复制**口径：

    观测 ghost = plan 的 rows_added − merge 之后真实存在的身份

🔴 **连带约束 `rows_ghost_dropped ⊆ rows_added` 必须有牙**，所以观测面刻意取得比 ghost 更宽：

    expected = rows_added ∪ rows_updated      （计划说 merge 之后**应当**在场的身份）
    missing  = expected − present
    ghost    = missing ∩ rows_added           ⇒ 合法差异（幽灵行门的既有语义）
    vanished = missing − rows_added           ⇒ **违规**，fail visible

`vanished` 非空意味着一个**本来就存在**的身份在 merge 之后不见了 —— 而引擎
`merge_projection_into_store_rows` 明写「已存在的行永不受影响，清空是合法编辑」
⇒ 那道门的语义已变（或 merge 删了行），不得静默当成幽灵接受。
若只按 `ghost = added − present` 观测而不看 updated 侧，这条约束就是构造上恒真的废话，
断言等于没写。

═══ 🔴 复读比对比的是**身份集合**，不是计数 ═══

只比计数会放过「删错了行但删对了个数」（删掉一条 declared 行、留下一条 undeclared 行，
两侧计数一模一样）。故 :func:`verify_applied_plan` 逐 `(item, table/分区)` 比**集合**：

* **作用域内**分区的期望集合 = `(rows_added − rows_ghost_dropped) ∪ rows_updated`
  —— 它只由 **plan** 决定（`declared − ghost`），因此这条比对是对**计划**的独立交叉核，
  不是「prune 有没有照自己说的做」的自问自答；
* **作用域外**分区的期望集合 = merge 之后观测到的那一份（逐元素原样）
  —— 这正是 Requirement 1.2 / 1.4 最危险的失效形态（prune 删到兄弟分区）的落点判据；
* 幽灵行是**已知的合法差异** ⇒ 期望集合里已按上式把它们减掉，且减掉的那一份自身满足
  `⊆ rows_added`（见上一节）。

═══ 为什么 re-plan（幽灵回喂）在本模块而不在 service ═══

回喂必须发生在写之后（幽灵只有 merge 跑完才观测得到），而 `compute_adopt_substrate` 里
`compute_plan_for_adopt` 的调用点被既有判据钉死为**恰 1 处**（`test_aos_adopt_plan_wiring.py`
的 `judge_shared_plan` 子判据 1）。⇒ 第二次计算落在本模块，且**仍走同一个门面**
（不直接调 `compute_overwrite_plan`）⇒ ADR-AOS-003 的「只有一处算法」不被破坏。

🔴 **本模块不 commit / 不 flush**：事务边界是 `compute_adopt_substrate` 末尾那一处统一
commit（平台铁律：service 只 flush 不 commit 的唯一例外）。本模块只发 UPDATE，
失败时由调用方的 `except Exception: rollback; raise` 兜住。
"""

from __future__ import annotations

import json
from typing import Any, Collection, Final, Mapping

import sqlalchemy as sa

# 🔴 三个 `_` 前缀的现读：它们是本域「取 row_keys / 取权威 scope / 按分区枚举身份」的**唯一**
#    实现，另写一份就是第二真源（而第二真源的后果恰是 Requirement 3.8 要防的「计划报了增删
#    而落库没动」）。特别是 `_store_ids_by_section` 的两条语义必须与计划侧逐字一致：
#    `payload is None` 才短路成零行（其余形态一律交给 reader 原生抛）· 分区值原样分桶不归一。
from app.services.workpaper_sync.adopt_overwrite_compute import (
    _row_keys_of,
    _scopes_of,
    _store_ids_by_section,
)
from app.services.workpaper_sync.adopt_overwrite_plan import (
    OverwritePlan,
    RowReader,
    prune_undeclared_rows,
)

#: 删除侧唯一的写语句。**只 UPDATE 不 INSERT** —— 有行可删就说明这条 `checklist_responses`
#: 已经存在；INSERT 分支在删除侧永远不可达，写出来只会多一条没人跑过的路径。
_UPDATE_REMARK: Final[str] = (
    "UPDATE checklist_responses SET remark = :val, updated_at = now() "
    "WHERE wp_id = :wp AND item_id = :item"
)


class _ScopedReader:
    """给 reader 套上**权威 scope** 的薄代理。只为 `declared_scopes` 为空的那几条 item 而存在。

    🔴 **为什么必须有它**：`prune_undeclared_rows` 的作用域门只读 `reader.declared_scopes`
    （其签名与判据已由 Task 4.1 交付、20+ 测试在引用，不为本任务改），而现算恰 **3** 条 item
    （`D4-2-rows` / `D2-detail-rows` / `H1-8-rows`）的 reader 自带 scope 为空、真声明由
    `AdoptPlanInputs.item_scopes` 从门面定义模块的 `ROWS_TABLE_KEY` 供入（Task 6.1）。
    不套上这层代理，删除侧就会对这 3 条当场抛 —— 而计划期明明算得出来。

    🔴 **为什么不用 `dataclasses.replace`**：三个 reader 实现里 `ReconcilingRowReader` 的
    `section_field` / `declared_scopes` 是 **property 不是字段** ⇒ `replace(...)` 会当场
    `TypeError`。现读实证过，不是推测。

    🔴 **只代理不重写**：`iter_rows` / `section_of` 原样转发 —— 行对象必须是**入参载荷的元素**
    本身，否则 `prune_undeclared_rows` 的「reader yield 出不属于入参 list 的行」那条会抛。
    """

    __slots__ = ("_inner", "declared_scopes")

    def __init__(
        self, *, inner: RowReader, declared_scopes: tuple[tuple[str, str | None], ...]
    ) -> None:
        self._inner = inner
        self.declared_scopes = declared_scopes

    @property
    def section_field(self) -> str:
        return str(getattr(self._inner, "section_field", "") or "")

    def iter_rows(self, payload: Any) -> Any:
        return self._inner.iter_rows(payload)

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        return self._inner.section_of(row)


class AppliedOverwrite:
    """删除侧应用之后的四样产出。**普通类不是 dataclass**（同 `AdoptPlanInputs` 的处置）。"""

    __slots__ = ("plan", "rows_deleted_by_item", "post_merge_ids", "ghost_dropped_by_item", "mismatches")

    def __init__(
        self,
        *,
        plan: OverwritePlan,
        rows_deleted_by_item: Mapping[str, tuple[str, ...]],
        post_merge_ids: Mapping[str, Mapping[str | None, frozenset[str]]],
        ghost_dropped_by_item: Mapping[str, tuple[str, ...]],
        mismatches: list[str],
    ) -> None:
        #: 幽灵回喂之后重算的最终计划（`rows_ghost_dropped` 已落到各自分区）。
        self.plan = plan
        #: 逐 item 真实删掉的行身份（Task 6.5 写进审计 details 用）。
        self.rows_deleted_by_item = rows_deleted_by_item
        #: merge **之后、prune 之前**的身份快照（作用域外分区的「不变」判据基准）。
        self.post_merge_ids = post_merge_ids
        #: 观测到被幽灵行门剔除的身份（构造上 ⊆ `rows_added`）。
        self.ghost_dropped_by_item = ghost_dropped_by_item
        #: 已发现的不符项（写回 0 行 / 非幽灵身份凭空消失）。调用方与复读结果合并后一次抛。
        self.mismatches = mismatches


def _declared_by_item(plan: OverwritePlan) -> dict[str, tuple[set[str], set[str]]]:
    """item → (本次新增身份, 本次更新身份)，跨该 item 的全部 `(table, 分区)` delta 取并集。

    🔴 **刻意按 item 而不按分区聚合**：被幽灵行门剔除的行**根本不在载荷里**，因此它没有分区
    可言（`section_of` 无从对一个不存在的行取值）。按分区找它必然找不到，进而把它误判成
    「作用域外」而静默放过 —— 那正是 Requirement 1.6 要登记的那件事。
    """
    out: dict[str, tuple[set[str], set[str]]] = {}
    for delta in plan.deltas:
        if delta.table_key is None:
            continue
        added, updated = out.setdefault(delta.item_id, (set(), set()))
        added.update(delta.rows_added)
        updated.update(delta.rows_updated)
    return out


def observe_ghost_dropped(
    plan: OverwritePlan,
    *,
    post_merge_ids: Mapping[str, Mapping[str | None, frozenset[str]]],
) -> tuple[dict[str, tuple[str, ...]], list[str]]:
    """**纯函数**：按「计划说该在场、merge 之后却不在」观测幽灵行。

    :returns: `(ghost_dropped_by_item, 违规清单)`。前者回喂
        `compute_plan_for_adopt(ghost_dropped_by_item=…)`；后者非空即 Requirement 3.5 的
        fail visible（由调用方抛 `AdoptPlanVerificationError` → 500 + rollback）。

    `ghost ⊆ rows_added` 由**构造**保证（`missing & added`），而这条约束**有牙**是因为
    观测面取的是 `added ∪ updated`：落在 `updated` 侧的缺失会被单独拎出来当违规，
    而不是一起塞进 ghost 里蒙混过关（模块 docstring 第二节给了完整推理）。

    🔴 另一道独立复核在 `adopt_overwrite_compute._deltas_for_item` 末尾：回喂的幽灵身份若
    落不进任何分区的 `rows_added`，那边当场抛 `OverwritePlanShapeError`。两处口径不同
    （本处按 item、那处按分区）⇒ 观测口径错了两边都拦得住。
    """
    ghosts: dict[str, tuple[str, ...]] = {}
    violations: list[str] = []
    for item_id, (added, updated) in sorted(_declared_by_item(plan).items()):
        present: set[str] = set()
        for ids in (post_merge_ids.get(item_id) or {}).values():
            present |= set(ids)
        missing = (added | updated) - present
        if not missing:
            continue
        ghost = missing & added
        if ghost:
            ghosts[item_id] = tuple(sorted(ghost))
        vanished = missing - added
        if vanished:
            violations.append(
                f"{item_id}：身份 {sorted(vanished)} 在 merge 之后不在场，而它们**不是**本次"
                "新增（不在 rows_added 里）—— 幽灵行门只对本次新增生效（引擎明写「已存在的行"
                "永不受影响，清空是合法编辑」）⇒ 观测到这种缺失说明那道门的语义已变或 merge "
                "删了行，不得静默当成幽灵接受（Requirement 1.6 / 3.5）"
            )
    return ghosts, violations


def _diff_sections(
    item_id: str,
    *,
    expected: Mapping[str | None, set[str]],
    actual: Mapping[str | None, set[str]],
) -> list[str]:
    """逐分区比**身份集合**；文案同时给出两侧多出/缺失的身份**与**两侧行数。

    🔴 计数只是随附上下文，判据是集合相等 —— 「删对个数但删错行」两侧计数相同、集合不同。
    """
    out: list[str] = []
    for section in sorted(set(expected) | set(actual), key=lambda s: s or ""):
        want = set(expected.get(section) or ())
        got = set(actual.get(section) or ())
        if want == got:
            continue
        out.append(
            f"{item_id} / 分区 {section!r}：多出 {sorted(got - want)}、缺失 {sorted(want - got)}"
            f"（计划期望 {len(want)} 行、复读实得 {len(got)} 行）"
        )
    return out


def verify_applied_plan(
    plan: OverwritePlan,
    *,
    final_payloads: Mapping[str, Any],
    row_readers: Mapping[str, RowReader],
    item_scopes: Mapping[str, Any] | None = None,
    post_merge_ids: Mapping[str, Mapping[str | None, frozenset[str]]],
) -> list[str]:
    """**纯函数**：提交前复读结果与计划逐 item / 逐分区比对，返回不符项清单（空 = 相符）。

    :param final_payloads: 写完之后在**同事务**复读出来的载荷（`_snapshot_store` 的产物）。
    :param post_merge_ids: merge 之后、prune 之前的身份快照（作用域外分区的基准）。

    期望集合的两档取法见模块 docstring 第三节。不返回 bool 也不自己抛：
    `AdoptPlanVerificationError` 住在 `adopt_substrate_response`，由调用方合并两处不符项后
    **一次**抛出 —— 本模块反过来 import 它就会成环。
    """
    mismatches: list[str] = []
    for item_id in sorted(row_readers):
        expected: dict[str | None, set[str]] = {
            section: set(ids)
            for section, ids in (post_merge_ids.get(item_id) or {}).items()
        }
        for delta in plan.deltas:
            if delta.item_id != item_id or delta.table_key is None:
                continue
            expected[delta.row_section] = (
                set(delta.rows_added) - set(delta.rows_ghost_dropped)
            ) | set(delta.rows_updated)
        reader = _authoritative_reader(item_id, row_readers[item_id], item_scopes)
        actual = _store_ids_by_section(item_id, reader, final_payloads.get(item_id))
        mismatches.extend(_diff_sections(item_id, expected=expected, actual=actual))
    return mismatches


def _authoritative_reader(
    item_id: str, reader: RowReader, item_scopes: Mapping[str, Any] | None
) -> RowReader:
    """权威 scope 下的 reader —— 与计划期**同一条** `_scopes_of`，不另判一次。

    reader 自带的 scope 已是权威时原样返回（绝大多数 item 走这条，代理一次都不构造）。
    """
    scopes = _scopes_of(item_id, reader, item_scopes)
    if scopes == tuple(getattr(reader, "declared_scopes", ()) or ()):
        return reader
    return _ScopedReader(inner=reader, declared_scopes=scopes)


async def apply_overwrite_deletions(
    session: Any,
    *,
    wp_id: Any,
    baseline: Any,
    store_payloads: Mapping[str, Any],
    plan_inputs: Any,
    plan: OverwritePlan,
) -> AppliedOverwrite:
    """应用删除侧（ADR-AOS-001 的后置 prune）+ 观测幽灵行 + 回喂重算计划。

    🔴 **调用点必须在 `mirror_projection_into_store(..., commit=False)` 之后**（模块 docstring
    第一节给了实证理由：前置会让幽灵行门全面生效 ⇒ 覆盖变成大面积静默少写）。

    :param store_payloads: **merge 之前**的载荷（计划与回滚快照那一次读取）—— 回喂重算要用
        它，重算的必须是同一份计划、只多出幽灵归属；拿 merge 之后的载荷重算会算出另一份计划。
    :param plan: merge 之前算出的计划（digest 已对过的那一份），幽灵观测的基准。

    本函数**不 commit 不 flush**：删除侧的 UPDATE 与上游 merge 的写同处一个未提交事务，
    调用方复读比对通过后统一 commit，不通过则整体 rollback。
    """
    # 🔴 与 service 同一条 SELECT 口径（`_snapshot_store`）+ 同一个计划门面
    #    （`compute_plan_for_adopt`）—— 另写一份读取或直接调 `compute_overwrite_plan`
    #    都会多出一处真源。顶层 import 会与 `adopt_substrate_response` 成环，故在此处引入。
    from app.services.workpaper_sync.adopt_substrate_response import (
        _snapshot_store,
        compute_plan_for_adopt,
    )

    row_keys = _row_keys_of(baseline)
    readers: Mapping[str, RowReader] = plan_inputs.row_readers
    merged = await _snapshot_store(session, wp_id=wp_id, item_ids=plan_inputs.item_ids)

    post_merge_ids: dict[str, Mapping[str | None, frozenset[str]]] = {}
    rows_deleted_by_item: dict[str, tuple[str, ...]] = {}
    mismatches: list[str] = []
    for item_id in sorted(readers):
        reader = _authoritative_reader(item_id, readers[item_id], plan_inputs.item_scopes)
        payload = merged.get(item_id)
        post_merge_ids[item_id] = {
            section: frozenset(ids)
            for section, ids in _store_ids_by_section(item_id, reader, payload).items()
        }
        pruned, deleted = prune_undeclared_rows(payload, row_keys=row_keys, reader=reader)
        if not deleted:
            # 🔴 零删除时 prune 返回入参对象本身 ⇒ 连重序列化都不发生（避免白白虚报一次变更）。
            continue
        rows_deleted_by_item[item_id] = deleted
        written = (
            await session.execute(
                sa.text(_UPDATE_REMARK),
                {
                    "val": json.dumps(pruned, ensure_ascii=False),
                    "wp": str(wp_id),
                    "item": item_id,
                },
            )
        ).rowcount
        if not written:
            mismatches.append(
                f"{item_id}：删除侧要删 {list(deleted)} 却 UPDATE 到 0 行 —— 这条 "
                "checklist_responses 在本事务里消失了（并发删除 / wp_id 不匹配），"
                "计划报了删除而库里没删（Requirement 3.5）"
            )

    ghost_dropped_by_item, ghost_violations = observe_ghost_dropped(
        plan, post_merge_ids=post_merge_ids
    )
    return AppliedOverwrite(
        plan=compute_plan_for_adopt(
            baseline=baseline,
            store_payloads=store_payloads,
            plan_inputs=plan_inputs,
            ghost_dropped_by_item=ghost_dropped_by_item,
        ),
        rows_deleted_by_item=rows_deleted_by_item,
        post_merge_ids=post_merge_ids,
        ghost_dropped_by_item=ghost_dropped_by_item,
        mismatches=[*mismatches, *ghost_violations],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Task 6.4 / 6.5 —— `changed_item_count` 的来源 · 回滚快照覆盖面 · 审计 details 追加字段
#
# 三个都是**纯函数**，落点在本模块而不是 `adopt_substrate_response` 的理由有两条：
# ① 行数门禁 —— service 交付 6.3 后 748/800 只剩 52 行，装不下这三段的判据级 docstring；
# ② 它们全部只读 `AppliedOverwrite`（本模块自己的产出物）⇒ 数据与口径同处一地，
#    service 侧只剩「把它们接起来」这一件事。
# ═══════════════════════════════════════════════════════════════════════════════


def changed_items_from_plan(plan: OverwritePlan) -> list[str]:
    """**纯函数**：本次覆盖有变更的 item（有序去重）—— `changed_item_count` 的唯一来源。

    口径 = **追加 / 删除 / 更新三类行身份任一非空**的 item（Requirement 3.6）。

    🔴 **为什么不再用「覆盖前后 remark 快照差集」**：design ADR-AOS-003 附注在真实
    PostgreSQL 上实测它**两个方向都失真** —— 漏报（`applied <= 0 and base_rows` 命中时
    `store_mirror` 一条写都不发，差集报 0）与虚报（写回一律 `json.dumps(..., ensure_ascii=False)`
    带空格分隔符，而前端写的是紧凑形态；真库 200 条大载荷里 **155** 条重序列化后不等 ⇒
    语义零净变化也会被报成「变了」）。计划侧是「这次覆盖动了哪些 item」的唯一权威。

    🔴 **幽灵行计入（本任务裁定）**：本函数读的是**裸 `rows_added`**，不是
    `rows_added − rows_ghost_dropped`。因为 `rows_ghost_dropped ⊆ rows_added`（构造保证，
    见本模块第二节），所以「全部新增身份都被幽灵行门剔除」这种退化 item **仍然算有变更**。
    三条理由：

    1. **误差方向不对称**：回滚快照的覆盖面以本函数为起算之一（:func:`rollback_snapshot_items`
       / Requirement 6.9）⇒ 少算一个 item = 它的原值不进快照 = 被改的内容再也恢复不了；
       多算一个 item 的代价只是快照里多一个键。
    2. **幽灵 item 的载荷真的被改写过**：design ADR-AOS-003 附注复现的那一例逐字记着 ——
       projection 新增一个无姓名身份、被幽灵行门剔除，`applied = 1`（不命中跳过判定式）、
       `merged == base`（语义相等），但**写回了一个重新序列化的字符串**。⇒ 把它算成「没变」
       与实测相反。
    3. **口径要能被前端复述**：wire form 同时给 `rows_added`（含 ghost）与 `rows_ghost_dropped`
       两个清单，弹窗按「将追加 N 行（其中 M 行会被剔除）」渲染 ⇒ changed 的口径必须用同一个
       `rows_added`，否则会出现「清单说动了、计数说没动」。

    🔴 **被跳过的 item 不在本函数口径内**（它们的 delta 三清单恒空，`table_key` 为 `None`）——
    这是**刻意**的：Requirement 3.6 问的是「这次覆盖动了哪些行集」，而跳过的 item 正是
    「删除侧做不到」的那些。它们的可回滚性由 :func:`rollback_snapshot_items` 的并集口径兜住，
    不靠本函数。
    """
    return sorted(
        {
            delta.item_id
            for delta in plan.deltas
            if delta.rows_added or delta.rows_deleted or delta.rows_updated
        }
    )


def rollback_snapshot_items(
    *, plan_changed: Collection[str], snapshot_changed: Collection[str]
) -> list[str]:
    """回滚快照要留原值的 item —— **两个口径的并集**（Requirement 6.9）。有序去重。

    :param plan_changed: :func:`changed_items_from_plan` 的产出（按**构造**得出）。
    :param snapshot_changed: 覆盖前后 `remark` 差集（**事后字节观测**）。

    🔴 **为什么不能只用 plan 侧**：被**跳过**的 item（不可枚举形态，现算 62 条 item 级
    + 2 条 adapter 级）在 plan 里三清单恒空 ⇒ plan 口径**看不见**它们，而
    `mirror_projection_into_store` 照样会 merge 并改写它们的 `remark`
    （**删除侧跳过 ≠ merge 跳过**）。只按 plan 存快照，这些 item 的原值当场丢失。

    🔴 **为什么也不能只用快照差集**：它是事后字节观测，只读 `remark` 一列，且已被真库实测证明
    两个方向都失真（见 :func:`changed_items_from_plan` 的第一段）。把「能不能恢复」唯一建立在
    一个已知不可信的观测量上，等于把 Requirement 6.9 交给运气。plan 侧是**按构造**保证
    「删除侧动过的 item 一个不漏」的那一半 —— 它不依赖任何观测仪器。

    🔴 **如实声明并集里两半的贡献并不对称**（Task 6.4 探针 5 个场景逐值实测，不是推测）：
    唯一一个「一方看得见、另一方看不见且**真的需要恢复**」的场景是 **plan 看不见**的那一向
    （被跳过的 item，见上）。反向那一例（幂等重采纳：行集全等、字节一字未变）里 plan 多报的
    item 其实什么都没变 ⇒ plan 侧在「可恢复性」上没有补到字节差集的盲区。
    ⇒ 并集的价值是**冗余**（两套互不依赖的判据同时盯着同一件事），不是「各补一半盲区」。
    并集只会让快照变大不会变小 ⇒ 这个选择在「可恢复」这件事上没有下行风险。
    """
    return sorted({*(str(x) for x in plan_changed), *(str(x) for x in snapshot_changed)})


def skipped_items_wire(plan: OverwritePlan) -> list[list[str]]:
    """`skipped_items` 的对外形态 —— 响应 wire form 与审计 details **同一口径**。

    🔴 存在的全部理由是**不让这个投影有第二份**：`_plan_wire_form` 与审计 details 都要它，
    两处各写一遍 `[[item_id, reason.value] …]` 就是两处口径，而它们迟早会不等
    （比如有人给其中一处加了第三格）。
    """
    return [[item_id, reason.value] for item_id, reason in plan.skipped_items]


def audit_details_for_applied(applied: AppliedOverwrite) -> dict[str, Any]:
    """审计 details 的**追加**三字段（Requirement 1.8 · design § Data Models 的三行）。纯函数。

    `rows_deleted_by_item` 是 Requirement 1.8 逐字要求的那件事（「把删除侧的行身份清单写入
    审计日志 details」）；`plan_digest` 让事后能把这条留痕与用户当时确认的那份摘要对上；
    `skipped_items` 让「这次覆盖对哪些 item 做不到」留在审计轨迹里而不是只出现在一次响应里。

    🔴 **`event_type` 不在本函数里**（它是 details 的固定头部，与「本次应用产出了什么」无关），
    也**不得**为这三个字段给 `workpaper_sync_adopt_substrate` 登记 `EVENT_TYPE_SCHEMAS` ——
    那是既有的有意裁决（未登记 event_type 跳过 schema 校验、正常写入并维护 hash chain），
    登记之后这三个字段就变成必填，而它们本质上是「有就写」的诊断信息。
    """
    return {
        "plan_digest": applied.plan.digest,
        "rows_deleted_by_item": {
            item_id: list(identities)
            for item_id, identities in sorted(applied.rows_deleted_by_item.items())
        },
        "skipped_items": skipped_items_wire(applied.plan),
    }


__all__ = [
    "AppliedOverwrite",
    "apply_overwrite_deletions",
    "audit_details_for_applied",
    "changed_items_from_plan",
    "observe_ghost_dropped",
    "rollback_snapshot_items",
    "skipped_items_wire",
    "verify_applied_plan",
]
