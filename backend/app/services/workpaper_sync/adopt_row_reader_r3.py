"""R3 兜底路径 —— 全域行表 spec 索引 + 引擎 `iter_store_rows(spec, payload)`。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 3.7）
Requirements 4.1 / 4.4 / 4.5 · **ADR-AOS-005**（用户裁决：解析器来源优先级两级扩为三级）

═══ 为什么是伴生模块（第二次同样处置）═══

Task 3.7 的落点被 tasks.md 写成 `adopt_row_reader.py`，但该文件交付 Task 3.4 后已 **624** 行，
而 `.py` 行数门禁上限 **800**（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit
与 CI 的 `file-size-guard` 同源）⇒ R3 的全部机件塞进去必触门禁。门禁自己给的处置顺序是
「优先拆分 / 抽伴生模块，确有必要才改 whitelist 基线」⇒ 本模块承载 R3 的**枚举面**
（索引 / 去重 / 两个 `RowReader` 实现），`adopt_row_reader.py` 只保留**判定面**
（三级优先级的接线 + 复用它自己的 L4 正面判据）。域内第三次同样处置
（前两次：`phase5_g9_store_facade.py`、`adopt_row_reader.py` 本身）。

🔴 依赖方向**单向**：`adopt_row_reader` → 本模块 → `adopt_overwrite_plan` + 引擎。
本模块**不**反向 import `adopt_row_reader`（会成环）。`section_value_of` 由两边共用，
故它住在**被依赖的一侧**（本模块），`_FacadeRowReader.section_of` 委托过来 —— 两份实现就是
两个真源，一旦一边 strip 一边不 strip，「读得出但判不进任何分区」的行会凭空出现。

═══ R3 与第 ① 级（provider 门面）的分工 ═══

第 ① 级用 provider 的 `iter_store_rows` 门面。它解不了两类问题（ADR-AOS-005 §2，现算复核见
Task 3.7 交付记录）：

* **门面覆盖面不全**：`G1-2-rows` 声明 3 段（`acctClass` = `trading` / `classified_fvpl` /
  `designated_fvpl`），门面是**单 spec** 薄转发（`_spec_of_store_item` 取**首个**匹配 spec）
  ⇒ 只 yield 第 ① 段。R3 按 spec 逐条枚举 ⇒ 3 段都能寻址。
* **门面被借给别的 entry**：`G3-2-detail-rows` / `G4-7-items` / `G5-2-rows` /
  `G6-5-fair-value-data` 四家的门面全部 re-export 自 `phase5_g9_store_facade`，其 `specs_for`
  惰性取 **G9** 主模块 ⇒ 传本 item 即抛。R3 绕开门面，直接用**本 item 自己的** spec。

🔴 **门面优先、R3 兜底**（ADR §5(2)）：门面是既有执行侧真源，merge 也走它 —— 读侧单方面改走
R3 会重演「读写口径不等」。两路都可用时用 :class:`ReconcilingRowReader` **对账**。

═══ 三条硬纪律 ═══

1. 🔴 **禁缓存 spec 清单**（ADR §5(1)）：`managed_row_table_specs()` 内有灰度 manifest 判断，
   缓存会让「开关一开就多两段」被一次进程内的旧结论盖住。故 :func:`global_spec_index`
   每次真扫。代价实测：首次 0.425s（含 import），二次 0.002s（模块已在 `sys.modules`）。
2. 🔴 **索引必须覆盖伴生模块**（ADR §4(1)）：`D1` 的 **17** 个 item / **18** 条 spec 住在
   `phase5_d1_expansion`，而 registry 指向的 `phase5_d1_notes_receivable` **没有**
   `managed_row_table_specs`（现算 `has_specs=False`）⇒ 只扫 registry 指定模块会把这 17 条假阴。
   故按**包**遍历而非按 registry 取模块。变异证明见测试
   `TestGlobalSpecIndexCoversCompanionModules`。
3. 🔴 **身份键与分区字段全取自声明**（Requirement 4.5）：引擎读的是
   `RowTableSheetSpec.row_identity_key` / `row_section_field`，本模块一个键名字面量都不写。
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Any, Final, Iterator, Mapping

from app.services.workpaper_sync.adopt_overwrite_plan import (
    OverwritePlanShapeError,
    RowReader,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (
    iter_store_rows as engine_iter_store_rows,
)

#: 声明层暴露行表 spec 清单的门面名（与 `adopt_row_reader._SPECS_NAME` 同一个名字，
#: 刻意不跨模块共享常量：那会把依赖方向变成双向）。
SPECS_NAME: Final[str] = "managed_row_table_specs"


def global_spec_index() -> dict[str, tuple[Any, ...]]:
    """全域行表 spec 索引：`store_item_id` → 该 item 的全部 spec（声明序）。

    🔴 **按包遍历，不按 registry 取模块** —— 见模块 docstring 纪律 2（D1 伴生模块）。
    🔴 **每次真扫，禁缓存** —— 见纪律 1（灰度 manifest）。

    import 或调用抛的模块**静默跳过**：本函数是兜底路径的入口，不该因为域内某个无关模块坏了
    就让整条 adopt 路径挂掉。这个「静默」有分母撑着：现算扫 **271** 个模块、**43** 个模块有
    声明面、覆盖 **84** 个 store item、import/调用失败 **0** 个 ⇒ 空的失败集合是事实而不是
    「吞了异常所以看不见」（对照组见测试：喂一个 import 必抛的包必须被跳过且不影响其余条目）。
    """
    from app.services import workpaper_sync as ws_pkg

    index: dict[str, list[Any]] = {}
    for info in pkgutil.walk_packages(
        ws_pkg.__path__, prefix=ws_pkg.__name__ + ".", onerror=lambda _name: None
    ):
        try:
            module = importlib.import_module(info.name)
        except Exception:  # noqa: BLE001 —— 见 docstring：域内无关模块不该拖垮兜底路径
            continue
        fn = getattr(module, SPECS_NAME, None)
        if not callable(fn):
            continue
        try:
            specs = tuple(fn())
        except Exception:  # noqa: BLE001 —— 灰度未开 / manifest 漂移 ⇒ 当作无声明
            continue
        for spec in specs:
            item_id = str(getattr(spec, "store_item_id", "") or "")
            if item_id:
                index.setdefault(item_id, []).append(spec)
    return {item: tuple(specs) for item, specs in index.items()}


def dedup_specs(specs: tuple[Any, ...], *, store_item_id: str) -> tuple[Any, ...]:
    """按 `(store_item_id, row_section_value)` 去重 —— ADR §5(3) 的硬要求。

    🔴 R3 是**逐 spec 遍历**，而引擎只按 `row_section_field` 过滤：两个 spec 同属一个 item 且
    都没有分区字段时，**两个 spec 都 yield 全表** ⇒ 同一行被数两次 ⇒ 行数凭空翻倍。现算恰 2 例：
    `D1-memo-rows`（`phase5_d1_expansion` 的 `memo_bank_rows` / `memo_commercial_rows`）与
    `I5-2-rows`（`phase5_i5_other_noncurrent_assets` 的 `other_noncurrent_gross_rows` /
    `other_noncurrent_impairment_rows`）。
    `adopt_row_reader._declared_scopes` 的去重只对 `(table_key, 分区)` **整对**生效
    （两个 table 不会被合成一个），**不替本函数兑现这条** —— 其 docstring 已如此声明。

    两种声明漂移当场抛（`OverwritePlanShapeError` = 声明/编程错误 ⇒ 500 + 堆栈）：

    * **同一 (item, 分区值) 的重复 spec 身份键不一致**：留哪条都会换掉行身份口径；
    * **同一 item 内部分 spec 声明了分区字段、部分没声明**：没声明的那条会 yield 全表，
      与声明了的那条重叠 ⇒ 仍然翻倍，而按 `row_section_value` 去重看不出来（值都不同）。

    两条现算均为 **0** 例；结构性零配变异证明（测试里用 stub spec 各造一例，必须打红）。
    """
    fields = {str(getattr(s, "row_section_field", "") or "") for s in specs}
    if len(fields) > 1:
        raise OverwritePlanShapeError(
            f"{store_item_id} 的 spec 在「有没有分区字段」上不一致（现得 {sorted(fields)}）—— "
            "没声明分区字段的那条会 yield 全表并与声明了的那条重叠，逐 spec 枚举必然重复计数"
        )
    kept: dict[str, Any] = {}
    for spec in specs:
        scope = str(getattr(spec, "row_section_value", "") or "")
        first = kept.get(scope)
        if first is None:
            kept[scope] = spec
            continue
        key_a = str(getattr(first, "row_identity_key", "") or "")
        key_b = str(getattr(spec, "row_identity_key", "") or "")
        if key_a != key_b:
            raise OverwritePlanShapeError(
                f"{store_item_id} 分区 {scope!r} 有多条 spec 且 row_identity_key 不一致"
                f"（{key_a!r} vs {key_b!r}）—— 去重时留哪条都会换掉行身份口径"
            )
    return tuple(kept.values())


def section_value_of(row: Mapping[str, Any], *, field: str, item_id: str) -> str | None:
    """本行的分区归属；无分区维度或取值为空返回 `None`。**两个 reader 共用的唯一实现。**

    🔴 取值口径与引擎 `iter_store_rows` 的过滤式**逐字同构**（`str(row.get(field) or "")`，
    **不 strip**）—— 一旦这里 strip 而引擎不 strip，「读得出但判不进任何分区」的行就会凭空出现。

    🔴 未声明的分区值**原样返回**（不归一成 `None`）：那种行不属任何声明分区 ⇒ Task 4.1 据此判
    它在作用域外并保留。归一成 `None` 会让它混进「无分区」桶，进而被当成在作用域内。
    """
    if not field:
        return None
    if not isinstance(row, Mapping):
        raise OverwritePlanShapeError(
            f"{item_id} 的 section_of 收到非 Mapping 行（实得 {type(row).__name__}）"
        )
    return str(row.get(field) or "") or None


@dataclass(frozen=True, kw_only=True)
class EngineRowReader:
    """:class:`RowReader` 的第 ② 个实现：逐 spec 调**引擎** `iter_store_rows(spec, payload)`。

    **不自己解析载荷、不自己提取身份、不自己过滤分区** —— 三件事全在引擎里，本类只做「把本
    item 的 N 条 spec 依次喂给引擎」这一件事。另写一份解析就是第二真源，必与执行侧漂移。

    Requirement 4.4 由**引擎**兜住（现读 `phase5_row_table_sheet.iter_store_rows` 逐条确认）：
    非法 JSON 即抛 · 非数组即抛 · 元素非对象即抛 · 缺稳定行身份即抛（明写「不得退回数组下标
    作身份」）· 重复身份即抛。⇒ 绕开门面不弱化 fail-visible 语义（ADR §5(1)）。

    🔴 `specs` 必须是 :func:`dedup_specs` 的产物：构造时**不**自己去重（去重会抛的两种声明漂移
    属于「应当被看见」的错误，藏在构造函数里就没人看得见了）。
    """

    #: store item 身份（错误文案定位用；本类不据它做任何键名假设）。
    item_id: str
    #: 已按 `(item, 分区值)` 去重的 spec（声明序）。
    specs: tuple[Any, ...]
    #: 分区字段名（取自 `RowTableSheetSpec.row_section_field`）；`""` = 本 item 无分区维度。
    section_field: str = ""
    #: 本 item 声明覆盖的 `(table_key, 分区)` 对。
    declared_scopes: tuple[tuple[str, str | None], ...] = ()

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="EngineRowReader")
        if not self.specs:
            raise OverwritePlanShapeError(
                f"{self.item_id} 的 EngineRowReader 没有 spec —— 空 spec 清单会让它对任何载荷都"
                "枚举出零行，那正是 Requirement 4.1 禁止的「静默当成零行」"
            )

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """yield `(row_identity, row)`：逐 spec `yield from` 引擎。

        🔴 **不 try/except**：载荷非法时引擎的原生异常必须原样穿透（Requirement 4.4，
        且原生文案已带 `spec.store_item_id`）。把它吞成「零行」正是那条 AC 点名禁止的。

        载荷**原样**传给每条 spec（不预解析成 list 再复用）—— 预解析就等于本模块自己写了一份
        JSON 解析与形态校验，而那份必与引擎漂移。多 spec 时重复解析的代价换的是单一真源。
        """
        for spec in self.specs:
            yield from engine_iter_store_rows(spec, payload)

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        """委托 :func:`section_value_of` —— 与 `_FacadeRowReader.section_of` 同一实现。"""
        return section_value_of(row, field=self.section_field, item_id=self.item_id)


@dataclass(frozen=True, kw_only=True)
class ReconcilingRowReader:
    """两路都可用时的**对账**包装：ADR §5(2) 的「不得取并集、不得择一静默」。

    行为：`iter_rows` 先把**同一载荷**喂给两路，比对**身份集合**；相等则按 `primary`
    （= 门面路，门面优先）原样 yield，不等即 :class:`OverwritePlanShapeError` fail visible。

    🔴 为什么必须有它：R3 不经过门面，而 merge（写侧）走的**是**门面。若读侧悄悄换了口径而没人
    对账，R3 就成了一个无人看管的第二真源 —— `G1-2-rows` 那类「计划报了增删而落库没动」
    （Requirement 3.8 当场破）会换一种形态复现。

    🔴 为什么是 `OverwritePlanShapeError` 而不是 Task 6.2 的 422 族：两路对同一份**合法**载荷
    给出不同身份集合，是**声明/代码漂移**（编程错误 ⇒ 500 + 堆栈），不是「用户存了份坏数据」。
    载荷本身坏时两路都会抛引擎的原生异常，走的是 Requirement 4.4 那条路，到不了这里。

    🔴 代价显式：每次读都跑两遍枚举。这是 ADR 明确要求的对账成本 —— 现算只有**两路都可用**的
    item 会被包（门面不可用的走裸 R3、无 spec 的走裸门面），不是全域加倍。
    """

    item_id: str
    #: 门面路（权威，yield 它的结果）。
    primary: RowReader
    #: R3 路（影子，只参与对账）。
    shadow: RowReader

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="ReconcilingRowReader")

    @property
    def section_field(self) -> str:
        """透传 `primary` 的分区字段名。

        🔴 不是可选的便利属性：另两个 reader 实现都有这个属性，包装器少了它就会让「包不包」
        变成调用方可观测的差异（Task 3.7 实测：既有测试正是在这里 `AttributeError`）。
        """
        return str(getattr(self.primary, "section_field", "") or "")

    @property
    def declared_scopes(self) -> tuple[tuple[str, str | None], ...]:
        """透传 `primary` 声明覆盖的 `(table_key, 分区)` 对（Task 4.1/4.2 要读它）。"""
        return tuple(getattr(self.primary, "declared_scopes", ()) or ())

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        primary_rows = list(self.primary.iter_rows(payload))
        shadow_ids = {identity for identity, _row in self.shadow.iter_rows(payload)}
        primary_ids = {identity for identity, _row in primary_rows}
        if primary_ids != shadow_ids:
            raise OverwritePlanShapeError(
                f"{self.item_id} 的门面路与 R3 路对同一载荷枚举出的身份集合不等 —— "
                f"只门面有 {sorted(primary_ids - shadow_ids)}、只 R3 有 "
                f"{sorted(shadow_ids - primary_ids)}。两路语义已漂移；取并集或择一静默会让"
                "「计划报了增删而落库没动」再次发生（Requirement 3.8），故当场拒收"
            )
        yield from primary_rows

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        """按 `primary` 判分区（门面优先）—— 对账只管身份集合，分区口径不另立第二份。"""
        return self.primary.section_of(row)


__all__ = [
    "EngineRowReader",
    "ReconcilingRowReader",
    "SPECS_NAME",
    "dedup_specs",
    "global_spec_index",
    "section_value_of",
]
