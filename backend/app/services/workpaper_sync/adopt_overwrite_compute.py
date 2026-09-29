"""`compute_overwrite_plan` —— 把逐 item 的行集差异聚合成一份 `OverwritePlan`。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 4.2）
Requirements 1.1 / 1.5 / 1.6 / 1.7 / 3.1 / 3.2 / 4.1 / 4.2 ·
ADR-AOS-002（作用域 = declared_table ∩ 本 row_section）/ ADR-AOS-003（dry_run 与真实执行共用
同一计划纯函数）/ ADR-AOS-005 §5(3)（分区去重是调用方的活）

═══ 为什么是伴生模块（域内第四次同样处置）═══

design §4.1 与 tasks.md 都把落点写成 `adopt_overwrite_plan.py`，但该文件交付 Task 4.1 后已
**781** 行，而 `.py` 行数门禁上限 **800**（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，
pre-commit 与 CI 的 `file-size-guard` 同源）⇒ 只剩 19 行余量，本任务塞不进去。门禁自己给的处置
顺序是「优先拆分 / 抽伴生模块，确有必要才改 whitelist 基线」。前三次同样处置：
`phase5_g9_store_facade.py` / `adopt_row_reader.py` / `adopt_row_reader_r3.py`。
`adopt_row_reader.py` 现 768 行（32 行余量）⇒ 也不是落点。

🔴 依赖方向**单向**：本模块 → `adopt_overwrite_plan`（取 `OverwritePlan` / `ItemOverwriteDelta` /
`SkipReason` / `RowReader` / `OverwritePlanShapeError`）。主模块**不**反向 re-export ——
双向 top-level import 在「先 import 伴生模块」的顺序下会拿到半初始化模块而 `ImportError`
（前两个伴生模块的 docstring 已把这条写成硬约束）。本模块也**不** import `adopt_row_reader`：
reader 由调用方解析后**传进来**，故本模块对「reader 怎么来的」零耦合。

═══ 纯函数（Requirement 3.1 / 3.2 / ADR-AOS-003）═══

不碰 DB、不发请求、不读盘、不改入参。输入 = substrate projection + 逐 item store 载荷 +
逐 item reader；输出 = `OverwritePlan`。**只有一处算法** —— Task 6.1 让 dry_run 与真实执行都调
它，摘要可信不靠「两处算出同样的数」，靠只有一处能算。

副作用的唯一来源是 `reader.iter_rows(payload)`（只读枚举）与它可能抛的原生异常
（Requirement 4.4 fail visible：非法 JSON / 非数组 / 元素非对象 / 缺身份 / 重复身份，全部由引擎
或 provider 门面原样抛出，本模块**不**吞、**不**包装 —— 包装会把 Task 6.2 的 422 变成 500）。
"""

from __future__ import annotations

from typing import Any, Collection, Final, Mapping

from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlan,
    OverwritePlanShapeError,
    RowReader,
    SkipReason,
    _declared_identities,
)

#: 唯一允许以 **adapter_id** 而非 store item_id 作键的跳过原因。
#:
#: Task 3.1 把这条留给本任务裁决（`SkipReason.no_store_item` 的 docstring：「此原因没有
#: item_id 可填 ⇒ 它**是否**落进清单由 Task 4.2 裁定；若登记，第一位放 adapter_id」）。
#: 🔴 **裁定：登记，第一位放 adapter_id。** 理由 = Requirement 4.2 要的是显式清单：现算 B 分母
#: 有 **2** 个这种 adapter（`a51.cashflow_audit` / `c2.control_test_summary`），不登记它们就在
#: 「覆盖做不到什么」这件事上完全不可见，而那正是 Requirement 4 要消灭的形态。
_ADAPTER_LEVEL_REASONS: Final[frozenset[SkipReason]] = frozenset({SkipReason.no_store_item})


# ═══════════════════════════════════════════════════════════════════════════════
# 🔴 为什么 import 了主模块的私有 `_declared_identities`
#
# 它是 `row_keys[table]` → 身份集合的**唯一**校验口径，且其中一条是本 spec 里唯一能造成
# **误删**的输入形态：裸 `str` 满足 `Collection` 却被逐字符迭代 ⇒ `row_keys={"t": "r1"}` 被读成
# 声明了 `{'r','1'}`，真身份 `r1` 落进「未声明」而**被删**（该函数 docstring 明写）。
# 在本模块另写一份就是第二真源，两份一旦漂移，漂的正是这条。⇒ 宁可 import 私有名并在此登记
# 理由：主模块若重命名它，本模块 import 当场 `ImportError`，而不是静默退化成「少校验一条」。
# ═══════════════════════════════════════════════════════════════════════════════


def _row_keys_of(substrate_projection: Any) -> Mapping[str, Collection[str]]:
    """取 projection 的 `row_keys`。形态与 `adopt_substrate_response._baseline_row_counts` 同源。"""
    raw = getattr(substrate_projection, "row_keys", None)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise OverwritePlanShapeError(
            f"substrate_projection.row_keys 必须是 Mapping，实得 {type(raw).__name__}"
        )
    return raw


def _normalise_reasons(
    skip_reasons: Mapping[str, Any] | None,
) -> dict[str, SkipReason]:
    """把跳过原因归一成封闭域成员；域外取值当场抛（沿用 `ItemOverwriteDelta` 的口径）。"""
    out: dict[str, SkipReason] = {}
    for key, raw in (skip_reasons or {}).items():
        if not isinstance(key, str) or not key.strip():
            raise OverwritePlanShapeError(f"skip_reasons 的键不是非空 item_id/adapter_id（{key!r}）")
        if isinstance(raw, SkipReason):
            out[key] = raw
            continue
        try:
            out[key] = SkipReason(str(raw))
        except ValueError as exc:
            raise OverwritePlanShapeError(
                f"{key} 的跳过原因 {raw!r} 不在封闭域 "
                f"{sorted(r.value for r in SkipReason)} 内（ADR-AOS-005 §5(4)：六成员封闭）"
            ) from exc
    return out


def _scopes_of(
    item_id: str,
    reader: RowReader,
    item_scopes: Mapping[str, Collection[Any]] | None,
) -> tuple[tuple[str, str | None], ...]:
    """本 item 声明覆盖的 `(table_key, 分区)` 对。优先用调用方显式给的，其次用 reader 自带的。

    🔴 **取不到就当场抛，不静默跳过删除侧** —— 三条理由：

    1. 与 Task 4.1 的 `prune_undeclared_rows` **逐字一致**：该函数对「reader 未给出
       `declared_scopes`」已经是当场抛（「作用域门与分区门都无从判定」）。本任务若改成静默
       跳过，同一条输入在计划期与执行期会有两种处置 —— 那是比报错更坏的结果。
    2. `SkipReason` 是**封闭六成员**（ADR-AOS-005 §5(4)，禁扩），而这种形态一个都不匹配：
       `absent` 门面在 ✗ ｜ `item_blind` 门面认本 item ✗ ｜ `item_unresolvable` 不抛 ✗ ｜
       `row_reader_bound_to_other_entry` 门面就是自家 ✗ ｜ `import_failed` ✗ ｜
       `no_store_item` 有 item ✗。硬塞任一个都会变成 Requirement 4.3 的「白名单失效条目」，
       Task 4.8 逐条核原因类型时必打红。
    3. 它是**可修的能力缺口**，不是形态使然 ⇒ 登记成豁免就是把缺口合法化（ADR-AOS-005 §6
       否决出路 (a) 时用的正是这条理由）。

    🔴 **现算恰 3 例**（Task 4.2 探针，B 分母 129 item 全量跑 `diagnose_row_reader`）：
    `d4.revenue_detail / D4-2-rows` · `d2.receivable_detail / D2-detail-rows` ·
    `h1.disposal_check / H1-8-rows` —— 正是 design §4.1b(2) 那 3 条「门面 item-blind 但硬绑的
    正是它」。它们的 provider **没有** `managed_row_table_specs()`，全域 spec 索引里也没有它们的
    spec（reader 类型实测是裸 `_FacadeRowReader`，不是 `ReconcilingRowReader`）⇒ `declared_scopes`
    为空元组。

    ⇒ **交给 Task 6.1 的接线约定（这条不做完，adopt 对 D4/D2/H1 会当场 fail visible）**：
    这 3 条的 table_key 有**现成声明**可取 —— 门面**定义模块**的 `ROWS_TABLE_KEY` 常量
    （现读实测：`phase5_d4_revenue_detail.ROWS_TABLE_KEY='revenue_detail_rows'` ·
    `pilot_d2_large_json.ROWS_TABLE_KEY='receivable_detail_rows'` ·
    `pilot_h1_grouped_dynamic.ROWS_TABLE_KEY='disposal_check_rows'`），而且**正是**这三个
    provider 自己 `build_store_projection` 里 `row_keys={ROWS_TABLE_KEY: …}` 用的那一个常量
    ⇒ 取它不是键名兜底，是取声明，与 Task 3.4 用 `STORE_ITEM_ID` / `ROW_IDENTITY_STORE_KEY`
    的做法同源。Task 6.1 把它读出来经 `item_scopes` 传进本函数即可。
    🔴 本任务**不**自己去读那个常量：`compute_overwrite_plan` 的输入面由 design §4.1 钉死为
    「projection + 载荷 + reader」，加一个「provider 模块」入参就不再是纯函数的那三样，
    且 reader 不暴露门面对象，无从拿到定义模块（拿 `invoke.__module__` 是 hack）。
    """
    override = (item_scopes or {}).get(item_id)
    raw: Collection[Any] = (
        override if override is not None else (getattr(reader, "declared_scopes", ()) or ())
    )
    scopes: list[tuple[str, str | None]] = []
    for pair in raw:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise OverwritePlanShapeError(
                f"{item_id} 的 scope {pair!r} 不是 (table_key, 分区) 二元组"
            )
        table_key, section = pair
        if not isinstance(table_key, str) or not table_key.strip():
            raise OverwritePlanShapeError(f"{item_id} 的 scope 缺 table_key（实得 {table_key!r}）")
        if section is not None and not isinstance(section, str):
            raise OverwritePlanShapeError(
                f"{item_id} 的 scope {table_key!r} 分区值必须是 str 或 None"
                f"（实得 {type(section).__name__}）"
            )
        scopes.append((table_key, section))
    if not scopes:
        raise OverwritePlanShapeError(
            f"{item_id} 有可用 reader 却拿不到 declared_scopes（reader 与 item_scopes 都为空）—— "
            "作用域门（Requirement 1.2）与分区门（Requirement 1.4）都无从判定，而 `SkipReason` 是"
            "封闭六成员、没有一个匹配这种形态（硬塞任一个即 Requirement 4.3 的失效白名单条目）。"
            "🔴 现算恰 3 例（D4-2-rows / D2-detail-rows / H1-8-rows），其 table_key 在门面定义"
            "模块的 `ROWS_TABLE_KEY` 常量里有现成声明 ⇒ 由 Task 6.1 经 item_scopes 传入"
        )
    return tuple(scopes)


def _in_scope_by_section(
    item_id: str,
    scopes: tuple[tuple[str, str | None], ...],
    *,
    section_field: str,
    row_keys: Mapping[str, Collection[str]],
) -> dict[str | None, tuple[str, frozenset[str]]]:
    """分区 → `(该分区唯一的 in-scope table_key, 该表声明的身份集)`。**三条门都在这里。**

    1. **作用域门**（Requirement 1.2）：`table_key not in row_keys` ⇒ 整条 scope 不参与，
       连 `store_rows_by_table` 都不登记。🔴 `in` 判**键集合**，不得换 `.get()`。
    2. **空值二分**（Requirement 1.3）：在键集合但值为空 ⇒ 身份集为空集 ⇒ 该表 store 侧全部
       行进 `rows_deleted`（清空）。这与「不在键集合」严格二分。
    3. **分区去重**（ADR-AOS-005 §5(3)，约束②）：按 `(item_id, 分区值)` 分桶。同一分区落到
       **两个** in-scope table_key 时**当场抛** —— 见下。

    🔴 **为什么同分区多表必须抛而不是取并集**：`prune_undeclared_rows` 在这种输入上会把两表的
    身份**并集**当作 declared（它的 `in_scope[section]` 是 `update` 累加），删除侧因此是对的；
    但 `ItemOverwriteDelta` 的身份是 `(item_id, table_key, row_section)` **单个** table_key ——
    报告侧只能挑一个表，挑谁都是错归属（「报出来的和实际删的不是同一条」比不报更糟）。
    现算 **0 例**（B 分母 129 item 全量跑：多 scope item 恰 4 条，`G5-2-rows` 12 段 /
    `G9-detail-rows` 3 段 / `G1-2-rows` 3 段 / `G3-2-detail-rows` 2 段，**分区值逐条互不相同**；
    `D1-memo-rows` / `I5-2-rows` 那两条「2 spec 无分区字段」经 `dedup_specs` 已收敛成 1 个 scope）
    ⇒ 结构性零，配变异证明（stub reader 造一例必须打红）。

    🔴 另两条当场抛是**刻意与 `prune_undeclared_rows` 逐字对齐**（退化声明 / 反向不一致）：
    若计划期放行而执行期抛，dry_run 就会报出一份永远执行不了的计划 —— Requirement 3.8
    （dry_run 摘要 == 实际落库变更）当场破。两处都抛，任一处单方面改动都会在 Property 7
    （应用计划后重算为空）上现形。
    """
    buckets: dict[str | None, tuple[str, frozenset[str]]] = {}
    for table_key, section in scopes:
        if section_field and section == "":
            raise OverwritePlanShapeError(
                f"{item_id} 的 {table_key!r} 声明了 row_section_field {section_field!r} 却把分区值"
                "留空 —— 退化声明（语义 = 「该字段为空的那些行」这一真分区）与「无分区」在计划"
                "模型里不可区分，必须先在 provider 侧显式化（与 prune_undeclared_rows 同判据）"
            )
        if not section_field and section is not None:
            raise OverwritePlanShapeError(
                f"{item_id} 的 reader section_field 为空却声明了分区 {section!r}"
                f"（table {table_key!r}）—— 行的 section_of 恒为 None 而永不命中该分区，"
                "删除侧会静默少删（与 prune_undeclared_rows 同判据）"
            )
        if table_key not in row_keys:  # 🔴 未声明 ⇒ 一个字节都不碰
            continue
        declared = _declared_identities(row_keys[table_key], table_key=table_key)
        taken = buckets.get(section)
        if taken is not None:
            raise OverwritePlanShapeError(
                f"{item_id} 的分区 {section!r} 同时落在 in-scope table {taken[0]!r} 与 "
                f"{table_key!r} 上 —— delta 的身份是 (item_id, table_key, row_section) 单表，"
                "两表共用一个分区就无从归属；prune 侧会按两表身份并集删除，报告侧挑任一个都是"
                "错归属 ⇒ 当场拒收（ADR-AOS-005 §5(3) 的去重必须在这一层兑现）"
            )
        buckets[section] = (table_key, declared)
    return buckets


def _store_ids_by_section(
    item_id: str, reader: RowReader, payload: Any
) -> dict[str | None, set[str]]:
    """store 侧现有行身份，按 `reader.section_of(row)` 逐字分桶。

    🔴 `payload is None`（库里根本没这条 `checklist_responses`）才短路成「零行」；其余形态
    **一律交给 reader**，非法 JSON / 非数组 / 元素非对象 / 缺身份 / 重复身份由引擎或 provider
    原生抛出（Requirement 4.4 fail visible）—— 与 Task 4.1 `_as_row_list` 的口径逐字一致，
    「当成零行处理」正是那条 AC 点名禁止的。

    🔴 分区值**原样分桶不归一**：未声明的分区值会自成一桶，而 `_in_scope_by_section` 里没有
    它 ⇒ 这些行在作用域外、既不计数也不删（Requirement 1.4）。归一进 `None` 桶会让它们被
    当成「无分区」而进入作用域。
    """
    out: dict[str | None, set[str]] = {}
    if payload is None:
        return out
    for identity, row in reader.iter_rows(payload):
        out.setdefault(reader.section_of(row), set()).add(identity)
    return out


def _ghosts_for(
    item_id: str,
    ghost_dropped_by_item: Mapping[str, Collection[str]] | None,
) -> tuple[str, ...]:
    """本 item 被**观测到**的幽灵身份（Task 6.3 供入；计划期恒空，裁定见 `compute_overwrite_plan`）。"""
    raw = (ghost_dropped_by_item or {}).get(item_id) or ()
    if isinstance(raw, (str, bytes, bytearray)):
        raise OverwritePlanShapeError(
            f"{item_id} 的 ghost 清单是 {type(raw).__name__} 而不是身份序列 —— 字符串会被逐字符"
            "迭代成一堆假身份"
        )
    return tuple(str(x) for x in raw)


def _deltas_for_item(
    *,
    item_id: str,
    reader: RowReader,
    payload: Any,
    scopes: tuple[tuple[str, str | None], ...],
    row_keys: Mapping[str, Collection[str]],
    ghosts: tuple[str, ...],
) -> list[ItemOverwriteDelta]:
    """一个可枚举 item 的逐 `(table, 分区)` delta。三清单按「两侧各有无」互斥定义。"""
    section_field = str(getattr(reader, "section_field", "") or "")
    buckets = _in_scope_by_section(
        item_id, scopes, section_field=section_field, row_keys=row_keys
    )
    if not buckets:  # 本 item 的表一个都没被本次 substrate 声明 ⇒ 原样不动、无差异可报
        return []
    store_by_section = _store_ids_by_section(item_id, reader, payload)

    deltas: list[ItemOverwriteDelta] = []
    unplaced = set(ghosts)
    for section, (table_key, declared) in sorted(
        buckets.items(), key=lambda kv: (kv[1][0], kv[0] or "")
    ):
        store_ids = store_by_section.get(section, set())
        added = declared - store_ids
        mine = tuple(sorted(unplaced & added))
        unplaced -= set(mine)
        deltas.append(
            ItemOverwriteDelta(
                item_id=item_id,
                table_key=table_key,
                row_section=section,
                rows_added=tuple(sorted(added)),
                rows_deleted=tuple(sorted(store_ids - declared)),
                rows_updated=tuple(sorted(declared & store_ids)),
                rows_ghost_dropped=mine,
            )
        )
    if unplaced:
        raise OverwritePlanShapeError(
            f"{item_id} 被登记的幽灵身份 {sorted(unplaced)} 不在任何分区的 rows_added 里 —— "
            "幽灵行门只对**本次新增**的身份生效（引擎 `merge_projection_into_store_rows` 明写"
            "「已存在的行永不受影响，清空是合法编辑」）⇒ 观测到一个不在 added 里的幽灵，说明"
            "那道门的语义已变（Requirement 1.6 / Property 3），不得静默吞掉"
        )
    return deltas


def compute_overwrite_plan(
    *,
    substrate_projection: Any,
    store_payloads: Mapping[str, Any],
    row_readers: Mapping[str, RowReader],
    skip_reasons: Mapping[str, Any] | None = None,
    item_scopes: Mapping[str, Collection[Any]] | None = None,
    ghost_dropped_by_item: Mapping[str, Collection[str]] | None = None,
) -> OverwritePlan:
    """聚合逐 item delta 与两侧行数 —— dry_run 与真实执行**共用**的唯一算法（ADR-AOS-003）。

    :param substrate_projection: adapter `extract` 出的 projection；只读它的 `row_keys`
        （`Mapping[table_key, 身份序列]`，与 `_baseline_row_counts` 同源）。
    :param store_payloads: `item_id` → store 侧原始载荷（`checklist_responses.remark` 或已解析
        序列）。`None` = 库里没这条。**它的键集合就是 item 分母**。
    :param row_readers: `item_id` → 可用的行枚举器（由调用方经
        `adopt_row_reader.diagnose_row_reader` 解析）。
    :param skip_reasons: `item_id` → `SkipReason`（取不到 reader 的那些）。
        `no_store_item` 这一个原因允许以 **adapter_id** 作键（Task 3.1 留给本任务的裁决，
        见 :data:`_ADAPTER_LEVEL_REASONS`）。
    :param item_scopes: `item_id` → `((table_key, 分区), …)` 显式覆盖，用于 reader 自身
        `declared_scopes` 为空的 item（现算恰 3 例，见 :func:`_scopes_of`）。
    :param ghost_dropped_by_item: `item_id` → **观测到**被幽灵行门剔除的身份。计划期传空，
        由 Task 6.3 在 merge 之后供入 —— 裁定见下。

    ═══ 分母（约束⑤，Requirement 4.2）═══

    分母**必须**以 adopt 真实路径为准：`adopt_substrate_response._store_item_ids` →
    `store_projection_response.resolve_store_projection_provider` →
    `adapters/registry.DELIVERED_PER_ENTRY_CONTRACTS`（现算 **51** adapter / **129** item），
    **不是** `store_item_registry.STORE_MERGE_REGISTRY`（现算 **42** adapter / **113** item，
    且对 `d2.receivable_detail` 的 provider 指向与前者不一致 ⇒ D2 一侧取到 1 条 item、
    另一侧 10 条）。本函数是纯函数、不解析注册表 ⇒ 分母**由入参带进来**；
    调用方用错注册表时由 :func:`verify_plan_item_denominator` 打红。

    本函数只对分母做两条自洽校验（漏登记即抛，不静默少算）：
    每个 `store_payloads` 的键必须**恰好**落在 `row_readers` 或 `skip_reasons` 之一；
    `row_readers` / `skip_reasons` 里不在 `store_payloads` 的键一律抛，
    唯一例外是 :data:`_ADAPTER_LEVEL_REASONS`（adapter 级，本来就没有 item）。

    ═══ 🔴 `rows_ghost_dropped` 在计划期**不可兑现** —— 裁定与依据 ═══

    **裁定：如实登记「计划期不可兑现」，本函数不预测幽灵行；观测点在 Task 6.3。**

    依据（现读 `phase5_row_table_sheet.merge_projection_into_store_rows`，不是推演）：那道门是

        ghost_ids = {rid for rid in order
                     if rid not in pre_existing_ids
                     and not str(resolve_json_path(by_id[rid], name_json_path) or "").strip()}

    它有三个输入，**没有一个**在本函数的输入面上：

    1. `name_json_path = managed_field_specs(spec)[spec.ghost_row_anchor_index][4]` ——
       要 `spec` 与 `managed_field_specs`。本函数只拿到 `RowReader` 协议（`iter_rows` /
       `section_of` / `declared_scopes` / `section_field`），三个实现里只有 `EngineRowReader`
       有 `.specs`，`_FacadeRowReader` 与 `ReconcilingRowReader` 都没有 ⇒ 取不到；
    2. `by_id[rid]` 是**merge 之后**的行（锚点值来自 projection 逐字段 `set_json_path`），
       而本函数跑在 merge **之前**；
    3. 门内还有两处 merge 私有的跳过（`fv.is_protected` 与 `field_to_path.get(field_id)`
       为假即 `continue`）。

    ⇒ 要在计划期得出 ghost 集合，只能**复现**上面整段（含 `ghost_row_anchor_index`、
    `strip()` 口径、两处 continue）—— 那是教科书式的**第二真源**，且真源住在
    `phase5_row_table_sheet`（OO callback 与 adopt 共用的引擎，Requirement 2 保护区）
    ⇒ 漂移不可避免而后果是「计划报了增删而落库没动」，正是 Requirement 3.8 要防的那件事。

    **这条 AC 应由谁在何时补**：Task 6.3（`mirror_projection_into_store(..., commit=False)`
    之后、同事务复读比对那一步）。那里是**观测**而非复现，零复制判据：

        观测 ghost = 本 plan 的 rows_added − merge 后载荷里真实存在的身份

    Task 6.3 把观测结果经 `ghost_dropped_by_item` 回喂本函数重算一次，即得带 ghost 的最终
    响应；本函数负责的是**把它放对位置**（按 `(table, 分区)` 归属）并在放不下时抛
    （见 :func:`_deltas_for_item` 末尾：幽灵身份必须落在某个分区的 `rows_added` 里）。

    🔴 **连带后果，必须显式登记**：`rows_ghost_dropped ⊆ rows_added`（Task 3.1 把 ghost 刻意
    排除在 `_DISJOINT_FIELDS` 之外，正是为此）⇒ dry_run 报的 `rows_added` 会**包含**将被幽灵门
    剔除的身份。因此 Requirement 3.8 的「dry_run 三清单 == 实际落库三清单」在有幽灵行时须按
    `rows_added − rows_ghost_dropped` 对账（与 Property 1 的「减去被幽灵行门剔除的身份集合」
    同一表述）。Task 4.5（Property 3）与 Task 8.5（真库对账）按此裁定书写。
    """
    row_keys = _row_keys_of(substrate_projection)
    reasons = _normalise_reasons(skip_reasons)

    for item_id in row_readers:
        if item_id not in store_payloads:
            raise OverwritePlanShapeError(
                f"{item_id} 有 reader 却不在 store_payloads 里 —— 分母漏登记会让这个 item 既不"
                "产 delta 也不进跳过清单（Requirement 4.2 的显式清单当场漏项）"
            )
        if item_id in reasons:
            raise OverwritePlanShapeError(
                f"{item_id} 同时给了 reader 与跳过原因 {reasons[item_id].value!r} —— 「能枚举」"
                "与「被跳过」互斥（`RowReaderResolution.__post_init__` 已按同一条钉死）"
            )
    for key, reason in reasons.items():
        if key not in store_payloads and reason not in _ADAPTER_LEVEL_REASONS:
            raise OverwritePlanShapeError(
                f"{key} 的跳过原因 {reason.value!r} 不在 store_payloads 里 —— 只有 "
                f"{sorted(r.value for r in _ADAPTER_LEVEL_REASONS)} 允许以 adapter_id 作键"
            )

    deltas: list[ItemOverwriteDelta] = []
    store_rows_by_table: dict[str, int] = {}
    for item_id in sorted(store_payloads):
        reader = row_readers.get(item_id)
        if reader is None:
            reason = reasons.get(item_id)
            if reason is None:
                raise OverwritePlanShapeError(
                    f"{item_id} 既无 reader 也无跳过原因 —— 本函数不猜：静默略过它就是"
                    "Requirement 4 要消灭的「静默部分覆盖」"
                )
            # 🔴 约束①：被跳过的 item **也必须产一条 delta**。`OverwritePlan.skipped_items` 是
            #    `deltas` 的派生投影（Task 3.1 明写「代价：Task 4.2 必须照办」）⇒ 不产 delta
            #    它就不会出现在跳过清单里，Requirement 4.2 的显式清单直接漏项。
            deltas.append(
                ItemOverwriteDelta(item_id=item_id, table_key=None, skipped_reason=reason)
            )
            continue
        item_deltas = _deltas_for_item(
            item_id=item_id,
            reader=reader,
            payload=store_payloads[item_id],
            scopes=_scopes_of(item_id, reader, item_scopes),
            row_keys=row_keys,
            ghosts=_ghosts_for(item_id, ghost_dropped_by_item),
        )
        for delta in item_deltas:
            table_key = str(delta.table_key)
            # 两个 item 声明同一张表时按累加（各自的行都真实住在那张逻辑表里）。
            store_rows_by_table[table_key] = store_rows_by_table.get(table_key, 0) + (
                delta.rows_deleted_count + delta.rows_updated_count
            )
        deltas.extend(item_deltas)

    # adapter 级跳过（无 item ⇒ 不在 store_payloads 循环里）单独补 delta。
    for key, reason in sorted(reasons.items()):
        if key not in store_payloads:
            deltas.append(
                ItemOverwriteDelta(item_id=key, table_key=None, skipped_reason=reason)
            )

    return OverwritePlan(
        deltas=tuple(deltas),
        store_rows_by_table=store_rows_by_table,
        # 🔴 substrate 侧登记**全部** declared table（design §4.1：「= projection.row_keys 逐表
        #    长度」），与 store 侧「只登记可枚举 in-scope 表」刻意不对称 —— 前者是「在线编辑侧
        #    真有多少行」，后者是「表单侧我们看得懂多少行」，两个数不同本身就是要给用户看的信息。
        #    行数取**去重后**的身份数（`_declared_identities` 返 frozenset）：若 row_keys 里有重复
        #    身份，用裸 `len(tuple)` 会让 substrate_rows_by_table 与 added/updated 的集合运算对不上。
        substrate_rows_by_table={
            str(table): len(_declared_identities(ids, table_key=str(table)))
            for table, ids in row_keys.items()
        },
    )


def verify_plan_item_denominator(
    plan: OverwritePlan, *, expected_item_ids: Collection[str]
) -> None:
    """断言计划覆盖的 store item 集合**恰好**等于预期分母（约束⑤的可执行判据）。

    `compute_overwrite_plan` 是纯函数、不解析注册表，分母由入参带进来 ⇒ 「用错注册表」这类
    错误必须有一条**独立**判据能打红，否则它只是文档里的一句话。

    预期分母**必须**来自 adopt 真实路径（`DELIVERED_PER_ENTRY_CONTRACTS` → provider →
    `all_store_item_ids()`，现算 **51** adapter / **129** item）。用
    `store_item_registry.STORE_MERGE_REGISTRY`（现算 42 / 113）会在这里当场打红：
    B ⊋ A，差 **16** 条（D2 多 9 + I1~I6 各 1 + J1 1）。

    🔴 adapter 级 delta（:data:`_ADAPTER_LEVEL_REASONS`）不参与比对 —— 它的 `item_id` 位放的是
    adapter_id（本模块顶部的裁定），拿它去比 item 分母必然误报。
    """
    expected = {str(x) for x in expected_item_ids}
    got = {
        d.item_id
        for d in plan.deltas
        if d.skipped_reason not in _ADAPTER_LEVEL_REASONS
    }
    if got != expected:
        raise OverwritePlanShapeError(
            f"计划覆盖的 item 集合与预期分母不等 —— 只在计划里 {sorted(got - expected)}；"
            f"只在分母里 {sorted(expected - got)}。🔴 最可能的成因是分母取自 "
            "`store_item_registry.STORE_MERGE_REGISTRY`（42 adapter / 113 item）而 adopt 真实"
            "路径走的是 `adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS`（51 / 129）"
        )


__all__ = [
    "compute_overwrite_plan",
    "verify_plan_item_denominator",
]
