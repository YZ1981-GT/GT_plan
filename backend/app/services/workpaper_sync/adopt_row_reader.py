"""`RowReader` 适配层 —— 对 provider 既有 `iter_store_rows` 门面的**薄转发**。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 3.4）
Requirements 4.1 / 4.4 / 4.5 · ADR-AOS-001 / ADR-AOS-002

═══ 为什么是伴生模块，而不是 `adopt_overwrite_plan.py` 的一节 ═══

design §4.1 把落点写在 `adopt_overwrite_plan.py`，Task 3.4 也照此追加过 —— 但追加后该文件
**1172 行**，而 `.py` 行数门禁上限 **800**（`backend/scripts/check/check_file_size.py` 的
`LIMITS`，pre-commit 与 CI 的 `file-size-guard` 同源）⇒ 提交必被拒。门禁自己给的处置顺序是
「优先拆分 / 抽伴生模块，确有必要才改 whitelist 基线」，且域内已有两次同样处置：
`phase5_g9_store_facade.py`（G9 触到同一门禁）与 `pilot_h1_store_merge.py`。故切成伴生模块。

🔴 依赖方向**单向**：本模块 → `adopt_overwrite_plan`（取 `RowReader` 协议、`SkipReason`
封闭域、`OverwritePlanShapeError`）。主模块**不**反向 re-export —— 双向 top-level import 在
「先 import 本模块」的顺序下会拿到半初始化的主模块而 `ImportError`（`phase5_g9_store_facade`
用函数体内惰性 import 绕开同一问题；这里改成单向，连惰性 import 都不需要）。
调用方（Task 4.2）从本模块取 :func:`diagnose_row_reader` / :func:`resolve_row_reader`。

═══ 本模块做什么、不做什么 ═══

**不解析载荷**、**不提取身份**、**不过滤分区** —— 三件事全在 provider 门面（最终都落到引擎
`phase5_row_table_sheet.iter_store_rows(spec, payload)`）里。本模块只做三件事：
①判「这个 `(provider, item)` 的门面能不能用」②能用就包成 :class:`RowReader`
③不能用就给 `None` + 一个 `SkipReason`，由调用方登记进 `skipped_items`（Requirement 4.1/4.2）。

🔴 **Task 3.7 起是三级，不是两级**（ADR-AOS-005，用户裁决采纳 R3）：
① provider 门面（:func:`_diagnose_via_facade`）→ ② R3 = 全域 spec 索引 + 引擎
`phase5_row_table_sheet.iter_store_rows(spec, payload)`（:func:`_diagnose_via_engine`，机件在伴生
模块 `adopt_row_reader_r3`）→ ③ 跳过并登记 `SkipReason`。**门面优先、R3 兜底**；两路都可用时包成
`ReconcilingRowReader` 做身份集合**对账**（不等即 fail visible，不取并集、不择一静默）。
R3 仍是**声明驱动**（`row_identity_key` / `row_section_field`），不是键名兜底。
现算收益：跳过清单 **104 → 62**，未裁决形态 **1 → 0**。

═══ 判定链（design §4.1b 的 L1~L4，逐级现读，每级配变异对照）═══

  L1 provider 模块能 import 吗        ← 🔴 **不在本层**：本层收到的是已 import 的模块对象，
                                         观测不到 import 失败。`SkipReason.import_failed`
                                         由调用方在 `resolve_store_projection_provider`
                                         抛时登记；`SkipReason.no_store_item` 同理（adapter 级）。
  L2 暴露 `iter_store_rows` 吗        ← 没有 ⇒ `absent`
  L3 签名认 `store_item_id` 吗        ← 认 ⇒ **只**用「显式传本 item」这一种调法；
                                         不认 ⇒ 门面硬绑其**定义模块**的 `STORE_ITEM_ID`，
                                         只有等于本 item 时可用，否则 `item_blind`
  L4 真调 + **消费** + 正面判据        ← 抛 ⇒ `row_reader_bound_to_other_entry`（门面 re-export
                                         自别家）或 `item_unresolvable`；覆盖面不全 ⇒
                                         :attr:`RowReaderResolution.is_unruled_shape`
                                         （🔴 这三种结论现在都只是 **① 级**的结论，会被第 ② 级
                                         R3 接住；顶层终态见 :func:`diagnose_row_reader`）

🔴 **L3 禁回退**（design §4.1b 明写这是探针 v1 的实际缺陷）：门面普遍写成
   `_spec_of_store_item(store_item_id or STORE_ITEM_ID)` —— 不传就落到门面定义模块自己的
   `STORE_ITEM_ID` ⇒ **任何假 item_id 都会被判可枚举**。故本层对 item-aware 门面只发
   `fn(payload, store_item_id=<本 item>)` 一种调用，取不到就返回 None，**不试第二种调法**。

🔴 **L4 必须消费生成器**：G 循环的门面是 `yield from` 生成器函数，`specs_for` 的抛错发生在
   **第一次迭代**而不是调用时 ⇒ 只调不 `list()` 会把 G3/G4/G5/G6 全判通过（design §4.1b(6)）。

🔴 **禁自造 `row.get("rowId")` 兜底**：行身份键现算 7 种取值（design § Overview）。本层唯一会
   碰键名的地方是**探活用的合成行**，而那个键名取自**声明**
   （`RowTableSheetSpec.row_identity_key` / 门面定义模块的 `ROW_IDENTITY_STORE_KEY`），
   不是字面量；真实枚举时身份由门面产出，本层当**不透明字符串**看。

═══ Requirement 4.4（载荷不可解析 ⇒ fail visible）的分工裁定 ═══

本层**原样穿透** provider / 引擎的原生异常，既不包装也不新建异常类型。三条理由：

1. 原生异常**已携带 item_id**（引擎 `f"{spec.store_item_id} 的载荷必须是行对象数组…"`、
   provider `f"{STORE_ITEM_ID} 的 remark 不是合法 JSON…"`）⇒ 重新包装只会重复或丢信息；
2. `OverwritePlanShapeError` 明写是「**编程错误**，应以 500 + 堆栈暴露，不得被翻译成用户可
   重试的提示」；而「store 里存着一份非法 JSON」是**数据**问题，Requirement 4.4 要的是 422
   ⇒ 用它会把归类搞反；
3. `AdoptStorePayloadUnreadableError`（→422）属 Task 6.2，本任务不建。

🔴 交给 Task 6.2 的**可机械执行**约定（不需要任何异常类型学）：本层的 L4 探活已经把「门面结构
   上能不能用」与「这份载荷能不能读」**分开**了 —— 拿到 `RowReader` 就意味着该门面已在合成载荷
   上真跑通过。因此 Task 6.2 只需在**调用点**包装：
   `try: list(reader.iter_rows(payload)) except Exception as exc:
    raise AdoptStorePayloadUnreadableError(item_id=…) from exc`，
   不必按异常类型甄别（原生类型异构：引擎 `RowTableStorePayloadError(Exception)`、多数 provider
   `StorePayloadError(SyncDomainError)`、`phase5_d4_customer_structure` 的是
   `StorePayloadError(ValueError)` —— 按类型分流必漂）。
"""

from __future__ import annotations

import inspect
import sys
from dataclasses import dataclass, replace
from typing import Any, Callable, Final, Iterator, Mapping

from app.services.workpaper_sync.adopt_overwrite_plan import (
    OverwritePlanShapeError,
    RowReader,
    SkipReason,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import (
    EngineRowReader,
    ReconcilingRowReader,
    dedup_specs,
    global_spec_index,
    section_value_of,
)

#: provider 暴露行枚举能力的门面名。现算 25 个定义（design § Overview）。
FACADE_NAME: Final[str] = "iter_store_rows"

#: item-aware 门面的那个关键字参数名（L3 的判据）。
_ITEM_PARAM: Final[str] = "store_item_id"

#: 声明层暴露行表 spec 清单的门面名（读 `row_identity_key` / `row_section_field` 用）。
_SPECS_NAME: Final[str] = "managed_row_table_specs"

#: item-blind 门面硬绑的 item / 身份键所在的模块常量名（**声明**，不是键名字面量）。
_HARD_BOUND_ITEM_CONST: Final[str] = "STORE_ITEM_ID"
_HARD_BOUND_IDENTITY_CONST: Final[str] = "ROW_IDENTITY_STORE_KEY"

#: L4 正面判据的合成行身份前缀。刻意带 `aos`，让它万一漏进任何输出都能被搜到。
_PROBE_PREFIX: Final[str] = "_aos-rowreader-probe"


def _facade_of(provider: Any) -> Any | None:
    """取 provider 的行枚举门面（含 re-export）。取不到返回 `None` ⇒ L2 判 `absent`。"""
    fn = getattr(provider, FACADE_NAME, None)
    return fn if callable(fn) else None


def _facade_accepts_item(fn: Any) -> bool:
    """L3：签名里有**显式命名**的 `store_item_id` 参数吗。

    🔴 刻意**不**把 `**kwargs` 算作「认」：`**kwargs` 只证明「传进去不报 TypeError」，
    不证明「真的按它选 spec」—— 那正是 L3 要排除的静默错配。
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):  # C 扩展 / 无签名对象
        return False
    param = sig.parameters.get(_ITEM_PARAM)
    return param is not None and param.kind in (
        inspect.Parameter.KEYWORD_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    )


def _facade_module_name(fn: Any) -> str:
    """门面的**定义**模块名。

    🔴 用 `__module__` 而不是「provider 模块名」：G3/G4/G5/G6 四家的门面全部 re-export 自
    `phase5_g9_store_facade`（design §4.1b(6) 以 `__module__` 现算确认），
    `getattr(provider, "iter_store_rows")` 拿到的是**别家**的函数。
    """
    return str(getattr(fn, "__module__", "") or "")


def _hard_bound_item_of(fn: Any) -> str:
    """item-blind 门面实际服务的那一个 item —— 取其**定义模块**的 `STORE_ITEM_ID`。"""
    owner = sys.modules.get(_facade_module_name(fn))
    return str(getattr(owner, _HARD_BOUND_ITEM_CONST, "") or "")


def _hard_bound_identity_key_of(fn: Any) -> str:
    """item-blind 门面的身份键 —— 取其定义模块的 `ROW_IDENTITY_STORE_KEY`（**声明**）。"""
    owner = sys.modules.get(_facade_module_name(fn))
    return str(getattr(owner, _HARD_BOUND_IDENTITY_CONST, "") or "")


def _declared_specs(provider: Any, store_item_id: str) -> tuple[Any, ...]:
    """本 item 的行表 spec 声明，**只看 registry 指定的这个 provider 模块**。

    🔴 这个「只看本模块」是 ① 级的正确口径（门面就在本模块上），但对 R3 是**错的** ——
    `D1` 的 17 个 item 的 spec 住在伴生模块 `phase5_d1_expansion`，registry 指向的
    `phase5_d1_notes_receivable` 没有声明面 ⇒ 用本函数做 R3 会把这 17 条假阴。故 R3 走
    `adopt_row_reader_r3.global_spec_index()`（按包遍历），不复用本函数。

    取不到声明面（或无匹配）返回空元组。

    🔴 spec 清单按灰度开关现算（`managed_row_table_specs()` 里有 manifest 判断）⇒ **不缓存**：
    缓存会让「开关一开就多两段」这类变化被一次进程内的旧结论盖住。
    """
    fn = getattr(provider, _SPECS_NAME, None)
    if not callable(fn):
        return ()
    try:
        specs = tuple(fn())
    except Exception:
        # 声明面自己抛（灰度未开 / manifest 漂移）⇒ 当作「无声明」，由 L4 探活定生死。
        return ()
    return tuple(s for s in specs if str(getattr(s, "store_item_id", "") or "") == store_item_id)


def _section_field_of(specs: tuple[Any, ...], *, store_item_id: str) -> str:
    """本 item 的分区字段名 —— **只从 `RowTableSheetSpec.row_section_field` 读**。

    🔴 禁硬编码字段名（含 `"section"`）：现算 6 个多分区 store item 共 **5** 种取值
    （`acctClass` / `agingCategory` / `maturityCategory`（g4 与 g6 共用）/ `sectionKey` /
    `section`），且合同清单里的 `"row_section_field": "section"` 是**描述性元数据不是真源**
    （5 处里 4 处与功能声明值不符，design § Overview 已登记该既存漂移）。

    两种声明漂移当场抛（`OverwritePlanShapeError` = 编程/声明错误，应 500 + 堆栈）：

    * 同一 item 的多个 spec 用了**不同**分区字段 ⇒ 无从判定一行属哪段；
    * 声明了 `row_section_field` 但 `row_section_value` 为空串 ⇒ 退化声明，与「无分区」在
      `ItemOverwriteDelta` 的模型里不可区分（Task 3.1 `_normalise_row_section` 明写「Task 4.1
      遇到时必须当场抛，不得静默归一」）。现算 **0** 处；**变异对照** = 同一段扫描在「声明了
      field」一侧命中非零（G1 3 段 / G9 3 段 / G5 12 段实测，见 Task 3.4 交付记录）。
    """
    fields = {str(getattr(s, "row_section_field", "") or "") for s in specs}
    fields.discard("")
    if len(fields) > 1:
        raise OverwritePlanShapeError(
            f"{store_item_id} 的多个 spec 声明了不同的 row_section_field {sorted(fields)} —— "
            "一行属哪个分区就无从判定；分区门（Requirement 1.4）必须有唯一字段"
        )
    field_name = next(iter(fields), "")
    if field_name:
        degenerate = [
            str(getattr(s, "table_key", "") or "")
            for s in specs
            if str(getattr(s, "row_section_field", "") or "") == field_name
            and not str(getattr(s, "row_section_value", "") or "")
        ]
        if degenerate:
            raise OverwritePlanShapeError(
                f"{store_item_id} 的 spec {degenerate} 声明了 row_section_field "
                f"{field_name!r} 却把 row_section_value 留空 —— 这是退化声明（语义 = 「该字段为空"
                "的那些行」这一**真分区**），与「无分区」在计划模型里不可区分，必须先在 provider "
                "侧显式化"
            )
    return field_name


def _declared_scopes(specs: tuple[Any, ...], *, section_field: str) -> tuple[tuple[str, str | None], ...]:
    """本 item 声明覆盖的 `(table_key, 分区)` 对，去重后按字典序。

    Task 4.1/4.2 需要它：`ItemOverwriteDelta` 的身份是 `(item_id, table_key, row_section)`，
    而「一个 store 载荷承载多个 (table, 分区)」正是 G 循环的常态（G5 一个 item **12** 段）。
    自己再从 spec 推一遍就是第二真源 ⇒ 由本层随 reader 一起交出去。

    🔴 `D1-memo-rows` / `I5-2-rows` 那种「多 spec 但无分区字段」会得到多个
    `(table_key, None)` —— 去重**只对 `(table, 分区)` 整对生效**，不会把两个 table 合成一个，
    因此 Task 4.1「按 `(store_item_id, row_section_value)` 去重」那条纪律仍需它自己兑现
    （本层只保证「重复了一定会被看见」，与 Task 3.1 的同名约定一致）。
    """
    scopes = {
        (
            str(getattr(s, "table_key", "") or ""),
            (str(getattr(s, "row_section_value", "") or "") if section_field else None),
        )
        for s in specs
    }
    return tuple(sorted(scopes, key=lambda pair: (pair[0], pair[1] or "")))


def _probe_rows(
    specs: tuple[Any, ...], *, section_field: str, fallback_identity_key: str
) -> tuple[list[dict[str, Any]], tuple[tuple[str, tuple[str, str | None]], ...]]:
    """L4 正面判据的合成载荷：**逐 spec 造一行**，身份键与分区值全取自**声明**。

    返回 `(合成载荷, ((期望身份, 该身份所属 (table_key, 分区)), …))`。逐 spec 各造一行是必需的
    —— 只造一行时，多分区 item 的其余段会被引擎的分区过滤全部剔掉，于是「门面只覆盖第一段」
    这类**静默部分覆盖**就看不见了（Task 3.4 实测：`G1-2-rows` 声明 3 段而门面只 yield 第 1 段）。

    🔴 期望身份**带着它的 scope 一起返回**，不靠下标去 `declared_scopes` 里对位 ——
    后者已去重且排序过，按 spec 序号索引它会报出错误的分区名（那种「报出来的和实际差的不是
    同一条」的错误文案比不报更糟）。

    🔴 身份键**不是字面量**：item-aware 路走 `spec.row_identity_key`，item-blind 路走门面定义
    模块的 `ROW_IDENTITY_STORE_KEY`。取不到声明的键就造不出合成行 ⇒ 由调用方判「无法验证」。
    """
    rows: list[dict[str, Any]] = []
    expected: list[tuple[str, tuple[str, str | None]]] = []
    if specs:
        for ordinal, spec in enumerate(specs):
            key = str(getattr(spec, "row_identity_key", "") or "")
            if not key:
                # static_region（无行维度）不该走行枚举路径 —— 不造行，交由覆盖面判据打掉。
                continue
            identity = f"{_PROBE_PREFIX}-{ordinal}"
            section_value = str(getattr(spec, "row_section_value", "") or "")
            row: dict[str, Any] = {key: identity}
            if section_field:
                row[section_field] = section_value
            rows.append(row)
            expected.append(
                (
                    identity,
                    (
                        str(getattr(spec, "table_key", "") or ""),
                        section_value if section_field else None,
                    ),
                )
            )
        return rows, tuple(expected)
    if fallback_identity_key:
        identity = f"{_PROBE_PREFIX}-0"
        return [{fallback_identity_key: identity}], ((identity, ("", None)),)
    return [], ()


def _consume(call: Callable[[Any], Any], payload: Any) -> list[Any]:
    """调门面并**真消费**返回值。

    🔴 这一行是 L4 的全部要害：G 循环的门面是 `yield from` 生成器函数，`specs_for` 的
    `EntrySelectionError` 发生在**第一次迭代**；只调不消费会让 G3/G4/G5/G6 四条「门面被借给
    G9」的真缺陷全部判成可枚举（design §4.1b(6)）。单区门面（如 g10）则在 `call` 当场抛 ——
    两种时机都被这一句罩住。
    """
    return list(call(payload))


@dataclass(frozen=True, kw_only=True)
class _FacadeRowReader:
    """:class:`RowReader` 的第 ① 个实现：对一个 provider 门面的薄转发。

    刻意不公开（`_` 前缀）：调用方拿到的应当是 :class:`RowReader` 协议，换实现不该改调用点。
    构造只经 :func:`_diagnose_via_facade` —— 它是「已通过 L2~L4」这件事的唯一凭证。

    🔴 Task 3.4 时它是**唯一**实现；Task 3.7（ADR-AOS-005）起另有两个：
    `adopt_row_reader_r3.EngineRowReader`（R3）与 `…ReconcilingRowReader`（两路对账包装）。
    """

    #: store item 身份（错误文案定位用；本层不据它做任何键名假设）。
    item_id: str
    #: 门面调用闭包。item-aware 路已把 `store_item_id=<本 item>` 绑死 ⇒ **无从**退回无参调法。
    invoke: Callable[[Any], Any]
    #: 分区字段名（取自 `RowTableSheetSpec.row_section_field`）；`""` = 本 item 无分区维度。
    section_field: str = ""
    #: 本 item 声明覆盖的 `(table_key, 分区)` 对（见 :func:`_declared_scopes`）。
    declared_scopes: tuple[tuple[str, str | None], ...] = ()

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="_FacadeRowReader")

    def iter_rows(self, payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """yield `(row_identity, row)` —— 原样转发门面，只在边界校验元组形态。

        🔴 **不 try/except**：载荷非法时 provider / 引擎的原生异常必须原样穿透
        （Requirement 4.4 fail visible，且原生文案已带 item_id）。把它吞成「零行」正是那条 AC
        点名禁止的；把它翻译成本模块的异常则会让 Task 6.2 的 422 归类变成 500
        （见模块 docstring 的「Requirement 4.4 分工裁定」）。
        """
        for ordinal, item in enumerate(self.invoke(payload)):
            if not isinstance(item, tuple) or len(item) != 2:
                raise OverwritePlanShapeError(
                    f"{self.item_id} 的 {FACADE_NAME} 第 {ordinal} 项不是 (identity, row) 二元组"
                    f"（实得 {type(item).__name__} 元数 "
                    f"{len(item) if isinstance(item, tuple) else 'n/a'}）—— 现算有门面 yield 三元组"
                    "（`phase5_d4_customer_structure` / `phase5_d2_03_bad_debt` 的 "
                    "`(table_key, rowId, row)`），按二元组解包会把 table_key 当成行身份"
                )
            identity, row = item
            if not isinstance(identity, str) or not identity.strip():
                raise OverwritePlanShapeError(
                    f"{self.item_id} 的 {FACADE_NAME} 第 {ordinal} 项身份不是非空字符串"
                    f"（实得 {identity!r}）"
                )
            if not isinstance(row, Mapping):
                raise OverwritePlanShapeError(
                    f"{self.item_id} 的 {FACADE_NAME} 第 {ordinal} 项行不是 Mapping"
                    f"（实得 {type(row).__name__}）"
                )
            yield identity, row

    def section_of(self, row: Mapping[str, Any]) -> str | None:
        """本行的分区归属；无分区维度或取值为空返回 `None`。

        🔴 取值口径与引擎 `iter_store_rows` 的过滤式**逐字同构**
        （`str(row.get(field) or "")`，**不 strip**）—— 一旦这里 strip 而引擎不 strip，
        「读得出但判不进任何分区」的行就会凭空出现。

        🔴 未声明的分区值**原样返回**（不归一成 `None`）：那种行不属任何声明分区 ⇒ Task 4.1
        据此判它在作用域外并保留。归一成 `None` 会让它混进「无分区」桶，进而被当成在作用域内。

        🔴 实现委托给 `adopt_row_reader_r3.section_value_of`（Task 3.7）—— R3 的
        :class:`~adopt_row_reader_r3.EngineRowReader` 用的是同一个函数。两份实现就是两个真源，
        一边 strip 一边不 strip 就会凭空造出「读得出但判不进任何分区」的行。
        """
        return section_value_of(row, field=self.section_field, item_id=self.item_id)


@dataclass(frozen=True, kw_only=True)
class RowReaderResolution:
    """一次「这个 (provider, item) 有没有可用行枚举器」的判定结果 + 判定依据。

    三态（`__post_init__` 钉死，不许出现第四种组合）：

    * **可枚举**：`reader` 非空、`skip_reason` 为空；
    * **已裁决的跳过**：`reader` 为空、`skip_reason` 非空 ⇒ 调用方按它登记 `skipped_items`；
    * 🔴 **未裁决形态**：两者都为空、`detail` 必非空，见 :attr:`is_unruled_shape`。
      它**不是**「无行」，调用方不得当零行处理。Task 3.4 时现算恰 1 例；Task 3.7 接上 R3 后
      顶层现算 **0 例**（棘轮基线已清成空集），但**① 级仍会产出它**（G1 的门面没被修好）
      ⇒ 形态本身保留，它是「门面路给不出结论」的载体。
    """

    item_id: str
    reader: RowReader | None = None
    skip_reason: SkipReason | None = None
    #: 人类可读依据。未裁决形态下必非空；其余形态下可空。
    detail: str = ""
    #: 门面的**定义**模块（`__module__`），空 = 没有门面。
    facade_module: str = ""
    #: 声明覆盖的 `(table_key, 分区)` 对。
    declared_scopes: tuple[tuple[str, str | None], ...] = ()
    #: L4 探活里**真被 yield 出来**的分区（`declared_scopes` 的子集）。
    covered_sections: tuple[str | None, ...] = ()

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.adapters.base import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="RowReaderResolution")

        if not isinstance(self.item_id, str) or not self.item_id.strip():
            raise OverwritePlanShapeError(f"resolution 缺 item_id（实得 {self.item_id!r}）")
        if self.reader is not None and self.skip_reason is not None:
            raise OverwritePlanShapeError(
                f"{self.item_id} 同时给了 reader 与 skip_reason "
                f"{self.skip_reason.value!r} —— 「能枚举」与「被跳过」互斥，两者并存会让调用方"
                "既枚举又登记跳过，Requirement 4.2 的显式清单随即失真"
            )
        if self.reader is None and self.skip_reason is None and not self.detail.strip():
            raise OverwritePlanShapeError(
                f"{self.item_id} 既无 reader 也无 skip_reason，却没给 detail —— 未裁决形态"
                "必须自带可读依据，否则它与「无行」在下游不可区分（那正是 Requirement 4 要消灭"
                "的静默部分覆盖）"
            )

    @property
    def is_enumerable(self) -> bool:
        return self.reader is not None

    @property
    def is_unruled_shape(self) -> bool:
        """门面路给不出结论的形态。**① 级现算恰 1 例 / 顶层（三级）现算 0 例**。

        🔴 Task 3.7 更新：下面整段仍然成立，但它描述的是 **① 级**（:func:`_diagnose_via_facade`）
        的结论。ADR-AOS-005 采纳 R3 后，这 1 例被第 ② 级接住 ⇒ `diagnose_row_reader` 的顶层结论
        是「可枚举（reader = `EngineRowReader`，3 段全覆盖）」，棘轮基线随之清成**空集**。
        「①新增 `SkipReason.section_coverage_incomplete`」那条出路**已被否决**（ADR §6：它把一个
        可修的能力缺口写成永久豁免），故 `SkipReason` 封闭域**六成员不变**。

        以下为 Task 3.4 的原始归因（保留，因为门面那条缺陷本身**没被修**）：

        `g1.trading_financial_assets_detail / G1-2-rows`。

        成因（Task 3.4 执行实测，不是推演）：G1 声明 3 段（`acctClass` =
        `trading` / `classified_fvpl` / `designated_fvpl`，三段各自的 `table_key` =
        `g1_2_rows_r1/r2/r3`），而它的门面是**单 spec** 薄转发
        （`_spec_of_store_item(store_item_id or STORE_ITEM_ID)` 取**首个**匹配 spec）
        ⇒ `iter_store_rows(payload, store_item_id="G1-2-rows")` 实测只 yield 第 ① 段，
        第 ②③ 段**无从寻址**（门面没有 `section` 参数，G9 那种多段门面才有）。

        为什么不能凑合用这个「只覆盖 1/3」的 reader：substrate 侧的 `row_keys` 含全部三个
        table，而 store 侧只读到 r1 ⇒ r2/r3 的既有行会被算成 `rows_added`，而 merge
        （`store_mirror` → 同一个单 spec 门面）同样只处理 r1、根本不会去加 ⇒ 计划报了增删而
        落库没动，Requirement 3.8 的「dry_run 摘要 == 实际落库变更」当场破。

        为什么 :class:`SkipReason` 现有六个成员一个都不能用（逐条核过，非省略）：
        `absent` 门面在 ✗｜`item_blind` 门面认 `store_item_id` ✗｜`item_unresolvable` 不抛 ✗｜
        `row_reader_bound_to_other_entry` 门面 `__module__` 就是自家 ✗｜`import_failed` ✗｜
        `no_store_item` ✗。硬塞任何一个都会变成 Requirement 4.3「白名单失效条目」——
        Task 4.8 逐条核原因类型时必打红。

        ⇒ Task 3.4 **只如实登记**，不擅自扩 `SkipReason`。两个候选出路里，设计层
        （ADR-AOS-005）裁决采纳 **②** R3 替代路径（引擎 + 全域 spec）—— 它同时解掉这 1 条与
        `row_reader_bound_to_other_entry` 的 4 条，实测均已转为可枚举。
        """
        return self.reader is None and self.skip_reason is None


def _diagnose_via_facade(*, provider: Any, store_item_id: str) -> RowReaderResolution:
    """第 ① 级：provider 门面路。判定链 L2~L4，见模块 docstring。

    🔴 它**不是**公开入口 —— 公开入口是 :func:`diagnose_row_reader`，后者在本函数给不出
    reader 时接第 ② 级（R3）。直接调本函数会拿到「只有门面路」的结论，那正是 Task 3.7 之前的
    行为（`G1-2-rows` 判未裁决形态、G3/G4/G5/G6 判 `row_reader_bound_to_other_entry`）。
    """
    # ── L2 ────────────────────────────────────────────────────────────────
    facade = _facade_of(provider)
    if facade is None:
        return RowReaderResolution(
            item_id=store_item_id,
            skip_reason=SkipReason.absent,
            detail=f"{getattr(provider, '__name__', provider)!r} 不暴露 {FACADE_NAME}",
        )
    facade_module = _facade_module_name(facade)
    reexported = facade_module != str(getattr(provider, "__name__", "") or "")

    # ── L3：只认「显式传本 item」这一种调法，**禁回退** ──────────────────────
    if _facade_accepts_item(facade):
        invoke: Callable[[Any], Any] = lambda payload: facade(  # noqa: E731
            payload, **{_ITEM_PARAM: store_item_id}
        )
        fallback_key = ""
    else:
        bound = _hard_bound_item_of(facade)
        if bound != store_item_id:
            return RowReaderResolution(
                item_id=store_item_id,
                skip_reason=SkipReason.item_blind,
                detail=(
                    f"{FACADE_NAME} 签名无 {_ITEM_PARAM}，硬绑 {facade_module}."
                    f"{_HARD_BOUND_ITEM_CONST}={bound!r}"
                ),
                facade_module=facade_module,
            )
        invoke = lambda payload: facade(payload)  # noqa: E731
        fallback_key = _hard_bound_identity_key_of(facade)

    specs = _declared_specs(provider, store_item_id)
    section_field = _section_field_of(specs, store_item_id=store_item_id)
    scopes = _declared_scopes(specs, section_field=section_field)

    # ── L4 阶段一：结构探活。空载荷即可触发 `specs_for` —— 无需任何键名 ──────
    try:
        leftover = _consume(invoke, [])
    except Exception as exc:
        reason = (
            SkipReason.row_reader_bound_to_other_entry
            if reexported
            else SkipReason.item_unresolvable
        )
        return RowReaderResolution(
            item_id=store_item_id,
            skip_reason=reason,
            detail=f"{FACADE_NAME} 在空载荷上即抛 {type(exc).__name__}: {exc}"[:400],
            facade_module=facade_module,
            declared_scopes=scopes,
        )
    if leftover:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"{FACADE_NAME} 对空载荷 yield 了 {len(leftover)} 项 —— 门面凭空造行，"
                "不可用于判「store 侧有哪些行」"
            ),
            facade_module=facade_module,
            declared_scopes=scopes,
        )
    return _finish_positive_probe(
        provider=provider,
        store_item_id=store_item_id,
        invoke=invoke,
        specs=specs,
        section_field=section_field,
        scopes=scopes,
        facade_module=facade_module,
        fallback_key=fallback_key,
    )


def _finish_positive_probe(
    *,
    provider: Any,
    store_item_id: str,
    invoke: Callable[[Any], Any],
    specs: tuple[Any, ...],
    section_field: str,
    scopes: tuple[tuple[str, str | None], ...],
    facade_module: str,
    fallback_key: str,
) -> RowReaderResolution:
    """L4 阶段二：正面判据 —— 合成载荷必须被**真 yield 出来**，且覆盖全部声明分区。

    🔴 这一段的存在理由就是「判据必须能为 False」：只做阶段一（空载荷不抛）时，
    「门面只覆盖第 1/3 段」与「载荷缺身份键照样过」两类问题都看不见。实测反证见
    :attr:`RowReaderResolution.is_unruled_shape`（G1 只覆盖 1/3）与
    `test_aos_row_reader_adapter.py`（缺身份键的行必抛）。
    """
    rows, expected = _probe_rows(
        specs, section_field=section_field, fallback_identity_key=fallback_key
    )
    if not expected:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"取不到本 item 的行身份键声明（spec {len(specs)} 条 / 门面模块常量 "
                f"{_HARD_BOUND_IDENTITY_CONST} 为空）⇒ 无从构造正面判据。"
                "🔴 禁按键名兜底（行身份键现算 7 种取值），故不判可枚举"
            ),
            facade_module=facade_module,
            declared_scopes=scopes,
        )
    expected_ids = tuple(identity for identity, _scope in expected)
    try:
        got = _consume(invoke, rows)
    except Exception as exc:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"{FACADE_NAME} 在按声明合成的 {len(rows)} 行载荷上抛 "
                f"{type(exc).__name__}: {exc}"
            )[:400],
            facade_module=facade_module,
            declared_scopes=scopes,
        )
    arities = sorted({len(t) if isinstance(t, tuple) else -1 for t in got})
    identities = {t[0] for t in got if isinstance(t, tuple) and t}
    missing_scopes = tuple(
        scope for identity, scope in expected if identity not in identities
    )
    if arities != [2] or missing_scopes:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"正面判据不成立：合成 {len(rows)} 行、期望身份 {list(expected_ids)}，"
                f"实得元数 {arities}、身份 {sorted(identities)}；"
                f"未被 yield 的声明分区 {list(missing_scopes)} —— 门面覆盖面不全，"
                "拿它算计划会把未覆盖分区的既有行误报成 rows_added（Requirement 3.8 当场破）"
            ),
            facade_module=facade_module,
            declared_scopes=scopes,
        )
    reader = _FacadeRowReader(
        item_id=store_item_id,
        invoke=invoke,
        section_field=section_field,
        declared_scopes=scopes,
    )
    covered = tuple(sorted({reader.section_of(t[1]) or "" for t in got}))
    return RowReaderResolution(
        item_id=store_item_id,
        reader=reader,
        facade_module=facade_module,
        declared_scopes=scopes,
        covered_sections=tuple(c or None for c in covered),
    )


def _diagnose_via_engine(*, store_item_id: str) -> RowReaderResolution:
    """第 ② 级 **R3**：全域 spec 索引 + 引擎 `iter_store_rows(spec, payload)`。ADR-AOS-005。

    与第 ① 级的三点关键差别：

    1. spec 从 **全域索引**取，不从 `provider` 取 —— `D1` 的 **17** 个 item 的 spec 住在伴生模块
       `phase5_d1_expansion`，而 registry 指向的 `phase5_d1_notes_receivable` 没有声明面
       ⇒ 只看 registry 指定模块会把这 17 条假阴（ADR §4(1)，变异证明在测试里）；
    2. spec 必须按 `(item, 分区值)` **去重**（ADR §5(3)）—— 逐 spec 枚举是 R3 的固有形态，
       `D1-memo-rows` / `I5-2-rows` 各 2 条无分区 spec 不去重就把同一行数两次；
    3. 因此**不需要**门面的 L3（没有「签名认不认 item」这回事）；L4 正面判据**完全复用**
       ① 级的 :func:`_probe_rows` + :func:`_consume` + 覆盖面比对 —— 两份判据就是两个真源。

    返回三态与 :class:`RowReaderResolution` 一致；**不可用时给 detail 说明**（不给 skip_reason
    —— 跳过原因归 ① 级裁定，R3 只回答「兜不兜得住」）。
    """
    specs = global_spec_index().get(store_item_id, ())
    if not specs:
        return RowReaderResolution(
            item_id=store_item_id,
            detail="R3 不可用：全域行表 spec 索引里没有本 item",
        )
    specs = dedup_specs(specs, store_item_id=store_item_id)
    section_field = _section_field_of(specs, store_item_id=store_item_id)
    scopes = _declared_scopes(specs, section_field=section_field)
    rows, expected = _probe_rows(specs, section_field=section_field, fallback_identity_key="")
    if not expected:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"R3 不可用：{len(specs)} 条 spec 都没声明 row_identity_key（static_region 无行"
                "维度）⇒ 无从构造正面判据。🔴 禁按键名兜底，故不判可枚举"
            ),
            declared_scopes=scopes,
        )
    reader = EngineRowReader(
        item_id=store_item_id,
        specs=specs,
        section_field=section_field,
        declared_scopes=scopes,
    )
    try:
        got = _consume(reader.iter_rows, rows)
    except Exception as exc:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"R3 不可用：引擎在按声明合成的 {len(rows)} 行载荷上抛 "
                f"{type(exc).__name__}: {exc}"
            )[:400],
            declared_scopes=scopes,
        )
    identities = {t[0] for t in got if isinstance(t, tuple) and t}
    missing = tuple(scope for identity, scope in expected if identity not in identities)
    if missing:
        return RowReaderResolution(
            item_id=store_item_id,
            detail=(
                f"R3 不可用：合成 {len(rows)} 行、期望身份 {[i for i, _s in expected]}，"
                f"实得 {sorted(identities)}；未被 yield 的声明分区 {list(missing)}"
            ),
            declared_scopes=scopes,
        )
    covered = tuple(sorted({reader.section_of(t[1]) or "" for t in got}))
    return RowReaderResolution(
        item_id=store_item_id,
        reader=reader,
        declared_scopes=scopes,
        covered_sections=tuple(c or None for c in covered),
    )


def diagnose_row_reader(*, provider: Any, store_item_id: str) -> RowReaderResolution:
    """判一个 `(provider, store item)` 有没有可用的行枚举器，并给出依据。

    :param provider: **已 import** 的 provider 模块（由调用方经
        `store_projection_response.resolve_store_projection_provider` 解析 —— 那一步抛就是
        `SkipReason.import_failed`，本层观测不到，见模块 docstring 的判定链 L1）。
    :param store_item_id: 本次要枚举的 store item（非空）。**只**用它调门面，不回退。

    三级优先级（ADR-AOS-005，design §4.1）：

    ① :func:`_diagnose_via_facade`（provider 门面）→ ② :func:`_diagnose_via_engine`（R3）
    → ③ 跳过并登记 :class:`SkipReason`。

    🔴 **门面优先、R3 兜底**；两路都可用时包成 :class:`ReconcilingRowReader` 做**一致性对账**
    （同一载荷两路身份集合必须相等，不等即 fail visible —— 不取并集、不择一静默）。

    纯函数：不碰 DB、不写文件、不改 provider 状态；副作用限于对门面/引擎发**合成载荷**的只读
    调用（L4 探活）与建索引时的 `import_module`（幂等）。
    """
    if not isinstance(store_item_id, str) or not store_item_id.strip():
        raise OverwritePlanShapeError(f"store_item_id 必须非空（实得 {store_item_id!r}）")
    facade = _diagnose_via_facade(provider=provider, store_item_id=store_item_id)
    engine = _diagnose_via_engine(store_item_id=store_item_id)
    if facade.is_enumerable:
        if not engine.is_enumerable:
            return facade
        assert facade.reader is not None and engine.reader is not None  # noqa: S101
        return replace(
            facade,
            reader=ReconcilingRowReader(
                item_id=store_item_id, primary=facade.reader, shadow=engine.reader
            ),
            detail="门面路与 R3 路都可用 ⇒ 门面优先 + 逐次读取对账（ADR-AOS-005 §5(2)）",
        )
    if engine.is_enumerable:
        why = facade.skip_reason.value if facade.skip_reason else facade.detail
        return replace(
            engine,
            detail=f"门面路不可用（{why}）⇒ 降级第 ② 级 R3：引擎 + 全域 spec 索引"[:400],
            facade_module=facade.facade_module,
        )
    return replace(facade, detail=f"{facade.detail} ｜ {engine.detail}"[:600])


def resolve_row_reader(*, provider: Any, store_item_id: str) -> RowReader | None:
    """取不到就返回 `None`（Task 3.4 的字面契约）。

    🔴 想知道**为什么**取不到，用 :func:`diagnose_row_reader` —— 调用方按
    `RowReaderResolution.skip_reason` 登记 `skipped_reason`（Requirement 4.1 / 4.2），
    并**必须**单独处置 `is_unruled_shape`（它不是「无行」）。
    """
    return diagnose_row_reader(provider=provider, store_item_id=store_item_id).reader


#: 🔴 放在**文件末尾**：夹在中间的 `__all__` 会让下一个追加者看不见它、漏登记新公开符号。
__all__ = [
    "FACADE_NAME",
    "RowReaderResolution",
    "diagnose_row_reader",
    "resolve_row_reader",
]
