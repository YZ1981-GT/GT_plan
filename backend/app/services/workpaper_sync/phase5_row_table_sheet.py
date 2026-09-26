# -*- coding: utf-8 -*-
"""行表型受管 sheet 引擎 —— 框架层单一实现（收敛七家 provider 的同构投影/合并/契约装配）。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 6/7/8/9
Requirements 1.1 / 1.2 / 1.3 / 11.1 / 11.2 / 11.3 / 11.4 / 11.5

═══ 成功先例 ═══

`phase5_transposed_sheet.py`（500 行通用引擎）+ `transposed_registry.py`（32 行注册表）已把
D4-29 从「几何常量与算法糅死的单例」泛化成「引擎 + 两份 spec」，且 D4-29 产物逐字节零回归。
本模块是同一手法在**行表**这个更大类上的复用。

═══ 三层架构里的位置（框架层，被调用不反向依赖）═══

  第 3 层（本模块）  RowTableSheetSpec + 投影/合并/契约装配引擎（零 wp_code 分支，CI 卡点守）
  第 2 层（循环层）  phase5_d1_notes_receivable 等 entry：声明事实，调本引擎
  第 1 层（sheet层） phase5_d1_02_category 等：SPEC 常量实例化

🔴 字段集**仅**来自七家 provider 的实测共性（design §Components），不多加「将来可能用到」的字段。

═══ 形态谱系三维（2026-09-25 复盘补，首版把「受管 sheet」等同「行表」，漏掉引擎已有且
D4 已用于生产的另两条路径，详见 spec design §附：D4 已验证的形态谱系）═══

  ① binding_kind：`excel_table`（动态，Excel Table + 隐藏 UUID 列）vs `static_region`
     （静态，workbook-scope definedName、无 Table 无 UUID 列，**绕开整条位移链**）。
     复用 `excel_extract.BindingKind`，不新造第三种。
  ② row_identity_key 三形态：`rowId`（UUID 动态行）/ `key`（稳定 key 固定行——仍是 excel_table
     binding 且仍注入 UUID 列，D4-6 范式）/ 无（走 static_region）。判据是「有没有行维度」。
  ③ HTML-only item 子集：受管 sheet ≠ 全部 item 受管（D4-5 三项因 footer 下 static_row 与插行
     fail-closed 冲突保持 HTML-only）。

🔴 StoreKind（store 载荷形状）与 BindingKind（Excel 侧几何）是**正交两维**：一个 fixed_text
   store item 既可能落在 static_region（D4-13 单 cell），也可能寄生在姊妹动态表的 excel_table
   binding 上（D4-5 分组紧凑表）。首版把二者混为一谈（把 fixed_text 当「无受管区」）是错的。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.services.workpaper_sync.excel_extract import BindingKind
from app.services.workpaper_sync.sheet_geometry import col_index, snake

__all__ = [
    "StoreKind",
    "AgingLayout",
    "AgingGroupSpec",
    "RowTableSheetSpec",
    "expand_aging_fields",
    "managed_field_specs",
    "attach_sibling_bindings",
]


class StoreKind(str, Enum):
    """store 载荷形状（`checklist_responses.remark` 的顶层结构）。

    🔴 与 `BindingKind`（Excel 侧几何）正交：StoreKind 描述 store 载荷长什么样，BindingKind
       描述该受管区在 Excel 里是动态 Table 还是静态区。二者不可混为一谈（首版的错法）。
    """

    rows = "rows"              # JSON 行数组（最常见）：D1-cust-rows / D3-det-rows / D2-detail-rows
    dict = "dict"              # 嵌套对象：D1-memo-rows {bankRows,commercialRows} / D4-9 {current,prior}
    fixed_text = "fixed_text"  # 纯文本标量：D1-14 政策 10 项 / D4-5 业务场景
    dedicated = "dedicated"    # 走 provider 专用 merge 门面：D4-7 products+monthly


class AgingLayout(str, Enum):
    """账龄组三形态（实测三种真实布局，必须全部表达且不互相污染）。

    * nested（D3/D7）：`{agingPrior: {within1: …}, agingAudited: {…}}`
    * flat（D6）：`agePrior1y / ageEnd1y` 平铺顶层
    * None（不设 aging_layout）：D1/D5/D4 无账龄组
    """

    nested = "nested"
    flat = "flat"


@dataclass(frozen=True)
class AgingGroupSpec:
    """一个账龄组的声明。

    :param json_prefix: nested 时的子对象名（`agingPrior`）；flat 时段键直接是各叶子键。
    :param group_header_cell: 组标题格（如 `I10`），进 field 的 group_source_ref。
    :param segments: `(段 key, 叶子列标)` 元组序列，或 flat 时 `(段 flat_key, 列标, 叶子标签)`。
        nested 用二元 `(seg_key, column)`；flat 用三元 `(flat_key, column, leaf_label)`。
        叶子标签（表头文本）nested 时由 leaf_labels 平行提供。
    :param leaf_labels: nested 时各段的表头文本（与 segments 一一对应）；flat 时为空（标签在
        segments 三元里）。
    """

    json_prefix: str
    group_header_cell: str
    segments: tuple[tuple[str, ...], ...]
    leaf_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class RowTableSheetSpec:
    """一张行表型受管 sheet 的全部几何 + 字段 + store 形态。引擎行为全由本类驱动，无隐藏常量。"""

    # ── 几何（七家 100% 同构的 6 个 + 1 个可选）────────────────────────────
    managed_sheet: str          # Excel 内的 sheet 名（含 wp_code 尾巴，如 '原值明细表（按类别）D1-2'）
    sheet_key: str              # 契约内的 sheet 键（如 'd12-managed'）
    table_key: str              # 契约内的 table 键（如 'category_detail_rows'）
    template_id: str            # _GT_SYNC 的 GT_TEMPLATE_IDS 项
    table_name: str             # Excel Table displayName
    uuid_col: str               # 隐藏身份列
    first_data_row: int
    last_data_row: int          # 模板预画末行（超出按样式克隆扩行）
    footer_row: int             # 合计 footer
    header_row: int | None = None       # D1/D4 有；账龄型在 aging 声明里带
    header_group_row: int | None = None  # 两级表头的组标题行（账龄型）
    header_leaf_row: int | None = None   # 两级表头的叶子行（账龄型）

    # ── binding 二分（复用 excel_extract.BindingKind，不新造第三种）──────────
    binding_kind: BindingKind = BindingKind.excel_table
    #: static_region 才有：workbook-scope definedName（动态区必空）。
    defined_name: str = ""

    # ── store ──────────────────────────────────────────────────────────────
    store_item_id: str = ""
    empty_payload: str = "[]"
    #: 🔴 行身份三形态：'rowId'（UUID 动态行）/ 'key'（稳定 key 固定行）/ ''（走 static_region 无行维度）。
    row_identity_key: str = "rowId"
    store_kind: StoreKind = StoreKind.rows

    # ── 字段（统一 7 元组，裁决 3：group_header_cell 内联第 7 位）──────────────
    #   (column_key, column, mode, value_type, json_key, header_text, group_header_cell)
    #   group_header_cell 为 "" 表示无分组表头
    field_specs: tuple[tuple[str, str, str, str, str, str, str], ...] = ()

    # ── 公式（mask 由引擎现算，provider 不手写字面量）────────────────────────
    formula_columns: tuple[str, ...] = ()
    formula_templates: Mapping[str, str] = field(default_factory=dict)

    # ── 分组（账龄三形态）────────────────────────────────────────────────────
    aging_layout: AgingLayout | None = None
    aging_groups: tuple[AgingGroupSpec, ...] = ()

    # ── footer / 错误消息标签（零回归：各家保持既有措辞）────────────────────
    footer_marker: str = "合计"
    #: footer 行是否携带合计/差异等公式（`contracts.FooterAnchorSpec.carries_total_formula`
    #: 的声明层来源）。默认 True 与七家既有 provider 现状逐字等价（零回归——它们的 footer
    #: 行全部真有公式，此前由 entry 模块各自硬编码 `"carries_total_formula": True`）。
    #: 🔴 D3-4 段②（Task 8）是本引擎首次出现 footer 行**无**公式的场景（`差异合理性分析`
    #: 纯文字说明行，R25 无 SUM/差异公式）——显式传 `False`，不得沿用默认值掩盖这个真实差异
    #: （`excel_materialize._grow_managed_table_ref` 据此决定 footer 公式区间是否需要跟随
    #: 插行重新归一化；无公式的 footer 行不该被当作"有公式待归一化"处理）。
    footer_carries_total_formula: bool = True
    error_label: str = ""

    #: HTML-only item 子集（受管 sheet ≠ 全部 item 受管；D4-5 范式）。
    html_only_item_ids: tuple[str, ...] = ()

    #: 幽灵行防护用哪个字段的 json_path 判定「新增行是否只有杂散字段」（Requirement 参见
    #: `merge_projection_into_store_rows` docstring）。默认第 0 位（D1/D2/D3/D4/D7 现状——
    #: 首个字段恰是真正业务名称）。🔴 D5/D6 是例外：D5 的 `[0]`=`category`（枚举）/
    #: D6 的 `[0]`=`seq_no`（整数序号，`0` 是合法真值不是"空"信号），二者原实现均改用
    #: `[1]` 作锚点（`item_name`/`contract_name`）。声明时若字段顺序里首位不适合当锚点，
    #: 显式传 `ghost_row_anchor_index=1`，**不得**为了适配框架层默认值而调整字段声明顺序
    #: （那会改变 `managed_field_specs()` 的输出顺序，破坏零回归门）。
    ghost_row_anchor_index: int = 0

    @property
    def formula_mask(self) -> tuple[str, ...]:
        """七家实测形态：全为列向区间 `{COL}{FIRST}:{COL}{LAST}`。取代 provider 侧手写 mask 字面量。

        做成 property 而非字段：七家无一例外都是该形态；做成字段会保留「手写 mask 与
        formula_columns 不一致」这个漂移面（design §Components 裁决依据）。
        """
        return tuple(
            f"{col}{self.first_data_row}:{col}{self.last_data_row}"
            for col in self.formula_columns
        )


def expand_aging_fields(spec: RowTableSheetSpec) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """账龄组展开成 7 元组 field spec（按 aging_layout 分派 key 派生规则，引擎内只剩一处 if）。

    * nested（D3/D7）：key = `f"{snake(json_prefix)}_{seg_key.lower()}"`，json_key =
      `f"{json_prefix}/{seg_key}"`，group_header_cell = 组标题格。
    * flat（D6）：key = `snake(flat_key)`，json_key = flat_key 本身（无 nested `/`），
      group_header_cell = 组标题格。

    这两种写法原本各自散在四个文件里，收进引擎后只剩下方这一处 if，由 D2/D3/D6/D7 四家零回归门钉住。
    """
    if spec.aging_layout is None:
        return ()
    out: list[tuple[str, str, str, str, str, str, str]] = []
    if spec.aging_layout is AgingLayout.nested:
        for group in spec.aging_groups:
            prefix_key = snake(group.json_prefix)
            if len(group.segments) != len(group.leaf_labels):
                raise ValueError(
                    f"账龄组 {group.json_prefix} 有 {len(group.segments)} 段，"
                    f"但 leaf_labels 有 {len(group.leaf_labels)} 个 —— 段与标签必须一一对应"
                )
            for (seg_key, column), leaf_label in zip(group.segments, group.leaf_labels):
                out.append((
                    f"{prefix_key}_{seg_key.lower()}",
                    column,
                    "editable",
                    "amount",
                    f"{group.json_prefix}/{seg_key}",
                    leaf_label,
                    group.group_header_cell,
                ))
    elif spec.aging_layout is AgingLayout.flat:
        for group in spec.aging_groups:
            for seg in group.segments:
                flat_key, column, leaf_label = seg  # 三元
                out.append((
                    snake(flat_key),
                    column,
                    "editable",
                    "amount",
                    flat_key,
                    leaf_label,
                    group.group_header_cell,
                ))
    return tuple(out)


def managed_field_specs(spec: RowTableSheetSpec) -> tuple[tuple[str, str, str, str, str, str, str], ...]:
    """标量字段 + 账龄展开，按列序排序。取代四家各写一遍的 `sorted(SCALAR + _aging(), key=_col_index)`。

    返回 7 元组序列（含 group_header_cell 第 7 位）。列序排序用框架层 `col_index`。
    """
    fields = list(spec.field_specs)
    fields.extend(expand_aging_fields(spec))
    return tuple(sorted(fields, key=lambda row: col_index(row[1])))


# ═══════════════════════════════════════════════════════════════════════════
# Task 9：行表引擎核心 —— 33 个同名函数里属于行表域的那批，每个在框架层恰有一处实现
#
# 🔴 引擎落地时六家 provider 一行不动（引擎无人调用、golden digest 门恒绿）；切换时一家
#    一个 commit、一家过一次门（tasks.md 阶段 1→3 的安全性来源）。
# ═══════════════════════════════════════════════════════════════════════════


class RowTableStorePayloadError(Exception):
    """HTML store 载荷形态不合法（非数组 / 缺 row identity / 重复 identity）。

    🔴 框架层不感知具体 wp_code：错误消息里的 store_item_id 由调用方经 spec 传入，
       不是本模块的字面量分支（需求 7.1 白名单第二类：错误消息文案）。

    各循环 provider 有自己的 `StorePayloadError(SyncDomainError)` 子类（error_code 各不同，
    进 4xx 分类）。引擎抛本类，provider 侧薄转发时按需转译，零回归门钉住消息措辞。
    """


def stable_key_for(spec: RowTableSheetSpec, column_key: str, row_identity: str = "{row_uuid}") -> str:
    """`{table_key}/{row_identity}/{column_key}` 的唯一拼装处（七家逐字相同）。"""
    return f"{spec.table_key}/{row_identity}/{column_key}"


def spec_to_contract_sheet_payload(spec: RowTableSheetSpec) -> dict:
    """从 `RowTableSheetSpec` 自动派生 contract sheet payload（取代 per-provider 手写）。

    产出结构与 D1/D4 各 per-sheet 模块手写的 `_rows_table_payload()` / `sheet_payload_*()`
    逐字段一致——只是改为从 spec 数据类自动推导，消除手写漂移面。
    """
    from app.services.workpaper_sync.excel_extract import TABLE_SHEET_ANCHOR

    specs = managed_field_specs(spec)
    fields = []
    for col_key, col, mode, vtype, json_key, hdr_text, group_cell in specs:
        fields.append({
            "stable_field_key": stable_key_for(spec, col_key),
            "json_pointer": f"/rows/{{row_uuid}}/{json_key}",
            "column_key": col_key,
            "cell": {"column": col, "row_from": "row_identity"},
            "mode": mode,
            "value_type": vtype,
            "source_ref": f"源xlsx!{spec.managed_sheet}!{col}{spec.first_data_row}",
            "header_source_ref": f"源xlsx!{spec.managed_sheet}!{col}{spec.header_row or spec.header_leaf_row or spec.first_data_row - 1}",
            "store_item_id": spec.store_item_id,
            "header_text": hdr_text,
        })

    header_row_count = 1
    if spec.header_group_row is not None and spec.header_leaf_row is not None:
        header_row_count = spec.header_leaf_row - spec.header_group_row + 1

    anchor_row = spec.header_row or spec.header_group_row or (spec.first_data_row - 1)

    table_payload = {
        "table_key": spec.table_key,
        "anchor": f"A{anchor_row}",
        "header_rows": header_row_count,
        "row_identity": {
            "kind": "field",
            "json_pointer": f"/rows/*/{spec.row_identity_key}",
        } if spec.row_identity_key else None,
        "delete_policy": "tombstone",
        "footer_anchor": {
            "marker": spec.footer_marker,
            "search_column": "A",
            "carries_total_formula": spec.footer_carries_total_formula,
        },
        "formula_mask": list(spec.formula_mask),
        "fields": fields,
    }
    if table_payload["row_identity"] is None:
        del table_payload["row_identity"]

    return {
        "sheet_key": spec.sheet_key,
        "excel_name": spec.managed_sheet,
        "locator": {"anchor": TABLE_SHEET_ANCHOR},
        "tables": [table_payload],
    }


def resolve_json_path(row: Mapping[str, object], json_path: str) -> object | None:
    """按 `agingPrior/within1` 这类路径取值；缺失返回 None（不猜、不造）。

    收敛 D2/D3/D7 三家的 `_resolve_json_path` 复制。flat 键（无 `/`）走单段，等价于直取。
    """
    cursor: object = row
    for segment in json_path.split("/"):
        if not isinstance(cursor, Mapping):
            return None
        cursor = cursor.get(segment)
    return cursor


def set_json_path(row: dict, json_path: str, value: object) -> bool:
    """按 `agingPrior/within1` 写值，逐级建 dict；返回是否真的改了值。

    收敛四家的 `_set_json_path` 复制。flat 键（无 `/`）走单段顶层写。
    """
    parts = json_path.split("/")
    cursor: dict = row
    for seg in parts[:-1]:
        nxt = cursor.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[seg] = nxt
        cursor = nxt
    leaf = parts[-1]
    if cursor.get(leaf) != value:
        cursor[leaf] = value
        return True
    return False


def store_row_identity(
    spec: RowTableSheetSpec, row: Mapping[str, object], *, ordinal: int
) -> str:
    """取一行的稳定行身份。空/非字符串即抛 —— **绝不**退回数组下标。

    🔴 `row_identity_key` 已参数化（三形态）：`rowId`（UUID 动态行）/ `key`（稳定 key 固定行，
       D4-6 范式）/ ``''``（走 static_region 无行维度，不应调用本函数）。
    """
    if not spec.row_identity_key:
        raise RowTableStorePayloadError(
            f"{spec.store_item_id} 声明为无行身份（static_region）—— 不应走行表投影路径"
        )
    raw = row.get(spec.row_identity_key)
    if not isinstance(raw, str) or not raw.strip():
        raise RowTableStorePayloadError(
            f"{spec.store_item_id} 第 {ordinal} 行缺少稳定行身份 "
            f"{spec.row_identity_key!r}（实得 {raw!r}）—— 不得退回数组下标作身份"
            "（Requirement 6.5 / Property 23）"
        )
    return raw.strip()


def iter_store_rows(spec: RowTableSheetSpec, payload):
    """流式 yield `(row_identity, row)`；非数组/重复身份即抛（fail closed）。

    收敛七家逐字相同的 `iter_store_rows`。载荷可为 JSON 文本、bytes 或已解析序列。
    """
    import json as _json

    if isinstance(payload, (str, bytes, bytearray)):
        text = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
        try:
            rows = _json.loads(text)
        except ValueError as exc:
            raise RowTableStorePayloadError(
                f"{spec.store_item_id} 的 remark 不是合法 JSON: {exc}"
            ) from exc
    else:
        rows = payload
    if not isinstance(rows, list):
        raise RowTableStorePayloadError(
            f"{spec.store_item_id} 的载荷必须是行对象数组，实得 {type(rows).__name__} —— "
            "整张表被存成别的形态时必须 fail closed，不得静默当成零行"
        )
    seen: set[str] = set()
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise RowTableStorePayloadError(
                f"{spec.store_item_id} 第 {ordinal} 项不是对象，实得 {type(row).__name__}"
            )
        identity = store_row_identity(spec, row, ordinal=ordinal)
        if identity in seen:
            raise RowTableStorePayloadError(
                f"{spec.store_item_id} 出现重复行身份 {identity!r}（第 {ordinal} 项）—— "
                "复制产生的重复 UUID 默认是结构冲突，不得静默合并成一行（Requirement 6.15）"
            )
        seen.add(identity)
        yield identity, row


def split_store_row(
    spec: RowTableSheetSpec, row: Mapping[str, object], *, row_identity: str, contract
):
    """一行 → N 条 `(stable_key, value, field_spec)`。`field_spec` 从 contract 取（未登记键即抛）。

    收敛七家的 `split_store_row`。nested 与 flat 的取值统一走 `resolve_json_path`
    （flat 键无 `/` ⇒ 单段直取，与原 `row.get(json_key)` 等价）。
    """
    for column_key, _column, _mode, _vt, json_path, _label, _group in managed_field_specs(spec):
        field_spec = contract.field_by_stable_key(stable_key_for(spec, column_key))
        yield (
            stable_key_for(spec, column_key, row_identity),
            resolve_json_path(row, json_path),
            field_spec,
        )


def build_store_projection(spec: RowTableSheetSpec, payload, *, contract, limits=None):
    """把 HTML store 的 JSON 载荷拆成按 stable field key 索引的 `Projection`。

    收敛七家逐字相同的 `build_store_projection`（含 `StreamingProjectionBudget` 预算）。
    """
    from app.services.workpaper_sync.adapters.base import FieldValue, Projection
    from app.services.workpaper_sync.excel_extract import StreamingProjectionBudget
    from app.services.workpaper_sync.limits import load_limits

    lim = limits or load_limits()
    budget = StreamingProjectionBudget(lim)
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for identity, row in iter_store_rows(spec, payload):
        budget.add_row(spec.table_key)
        row_keys.append(identity)
        for stable_key, value, field_spec in split_store_row(
            spec, row, row_identity=identity, contract=contract
        ):
            budget.add_field()
            values[stable_key] = FieldValue(
                stable_key=stable_key,
                value=value,
                value_type=field_spec.value_type,
                mode=field_spec.mode,
                row_key=identity,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={spec.table_key: tuple(row_keys)},
    )


def attach_sibling_bindings(
    *,
    provider: Any,
    primary: Any,
    contract: Any,
    dynamic_bindings: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Attach 时补 sibling binding —— 框架层泛化（Task 10），取代硬编码 `import ... as _provider`。

    spec: d1-sync-row-table-engine-and-d1-coverage · Task 10 · Requirements 1.5 / 2.4

    🔴 从 `phase5_d4_revenue_detail._attach_sibling_bindings`（原 :2665）逐字搬来，**函数体不动**，
    只把硬编码 `import app.services.workpaper_sync.phase5_d4_revenue_detail as _provider` 改成
    显式 `provider` 参数（design 裁决 D2）。继续调已有框架内核 `_align_specs_to_sibling_tables`
    / `_static_region_bindings`（publish 与 attach 两路径共享同一对齐规则，**不重写**——重写
    必然漂移）。

    Property 8 判据（`test_phase5_row_table_sheet.py`）：对 D4 传入 `provider=phase5_d4_revenue_detail`
    产出的 binding 元组 ≡ 泛化前 `_attach_sibling_bindings` 的输出（逐字段相等，含顺序）。
    """
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding
    from app.services.workpaper_sync.projection_first_publication import (
        _align_specs_to_sibling_tables,
        _static_region_bindings,
    )

    pairs = _align_specs_to_sibling_tables(
        provider=provider, contract=contract, primary=primary
    )
    siblings: list[Any] = []
    for spec, dynamic in pairs:
        binding = ExcelIdentityBinding(
            table_name=str(spec.table_name),
            uuid_column=str(spec.uuid_col),
            table_key=str(dynamic.table_key),
            metadata_sheet=GT_SYNC_SHEET_NAME,
            defined_name_prefix=str(
                getattr(spec, "defined_name_prefix", None) or "GT_"
            ),
            tombstoned_row_keys=(),
            dynamic_column_columns={
                str(table_key): dict(mapping)
                for table_key, mapping in (dynamic_bindings or {}).items()
                if isinstance(mapping, Mapping)
            },
        )
        siblings.append(binding)
    # 静态受管区 binding（引擎静态路径；无动态行，不经 _align_specs_to_sibling_tables）。
    # 复用 publish 侧同一通用生成器，两路径 binding 不漂移。
    siblings.extend(
        _static_region_bindings(provider=provider, metadata_sheet=GT_SYNC_SHEET_NAME)
    )
    return tuple(siblings)


def provider_managed_sheet_keys(provider: Any) -> set[str]:
    """provider 的 instrumentation 覆盖的**全部受管 sheet_key** 集合。

    收敛三类形态（Requirement 2.2）：
      * 复数 `instrumentation_specs()`（D4 / D2 改造后）—— 取每个 spec 的 `resolved_sheet_key`；
      * 单数 `instrumentation_spec()`（B60 / D1 父 / D3 父 / D5 / D6 / D7）；
      * 每个 spec 上寄生的 `static_sheets` / `transposed_sheets` 声明（静态区 / 转置表也是
        受管 sheet，其 sheet_key 必须计入 —— 否则「契约声明了静态区但 spec 漏挂」这类漏接
        绕过守卫）。
    """
    specs_fn = getattr(provider, "instrumentation_specs", None)
    if callable(specs_fn):
        specs = tuple(specs_fn())
    else:
        single = getattr(provider, "instrumentation_spec", None)
        specs = (single(),) if callable(single) else ()
    keys: set[str] = set()
    for spec in specs:
        rk = str(getattr(spec, "resolved_sheet_key", "") or "").strip()
        if rk:
            keys.add(rk)
        for parasitic in (
            *(getattr(spec, "static_sheets", ()) or ()),
            *(getattr(spec, "transposed_sheets", ()) or ()),
        ):
            sk = str((parasitic or {}).get("sheet_key") or "").strip()
            if sk:
                keys.add(sk)
    return keys


def assert_provider_specs_align_with_contract(provider: Any, contract: Any) -> None:
    """通用对齐守卫：provider instrumentation 覆盖的受管 sheet 集合 == 契约 `sheets[]` 集合。

    spec: workpaper-sync-registration-isolation-and-d2-republish · Requirement 2

    🔴 事故背书（D4-35）：契约加了 sheet（8 张）但漏了对应 instrumentation spec（7 个）⇒
       attach 期 `_align_specs_to_sibling_tables` **fail-closed 打挂整个 entry**，而不是只挂
       那一张。此前 D1/D3 各写一份同款守卫，D4/D2 没有 —— 本函数是**唯一**通用实现，覆盖所有
       暴露 instrumentation 的 provider（含 D4）。不一致即抛并**精确报差集**。

    与 `_align_specs_to_sibling_tables`（对齐 row table，运行期 binding）不同层：本函数在
    **声明期**比 sheet 集合，让漏接在接入/发布时就红，而不是上线后整册 500。
    """
    # 懒导入避免与 projection_first_publication 成环（后者 import 本模块的 spec）。
    from app.services.workpaper_sync.projection_first_publication import (
        ProviderCapabilityError,
    )

    spec_keys = provider_managed_sheet_keys(provider)
    contract_keys = {str(getattr(s, "sheet_key", "") or "") for s in contract.sheets}
    contract_keys.discard("")
    if spec_keys != contract_keys:
        missing = sorted(contract_keys - spec_keys)
        extra = sorted(spec_keys - contract_keys)
        raise ProviderCapabilityError(
            f"provider {getattr(provider, '__name__', provider)!r} 的 instrumentation 受管 "
            f"sheet 集合与契约 sheets 不对齐 —— 契约有而 spec 缺: {missing}；spec 有而契约缺: "
            f"{extra}。任一侧漏一张会让 attach fail-closed 打挂整个 entry（D4-35 事故形态）"
        )


def merge_projection_into_store_rows(
    spec: RowTableSheetSpec, *, projection, base_rows: list
) -> tuple[list[dict], int, int, set[str]]:
    """把已 extract 的 projection 合进 HTML store 行（不读盘）。

    🔴 field_id（契约侧 snake column_key）→ store json 路径（前端 camelCase / nested 路径）的
       映射由 `managed_field_specs(spec)` 的第 0/4 位给出，两侧不可能各写一份而脱钩。

    🔴 幽灵行防护（D4-2 同源缺陷，2026-09-22 用户实测）：Excel Table 边界被扩展时，若新行只有
       一个杂散的 editable 格非空（公式列已由 is_protected 挡掉），这一个字段就会让 identity
       通过 shell 创建关卡，而首列业务名称因从未在 Excel 里写入内容、根本不产出 FieldValue，
       永久停在空值 —— 用户在结构化视图里看到「有 rowId、没数据」的行。只对**本次新增**的
       identity 加这道门：已存在的行永不受影响（清空是合法编辑）。
    """
    specs = managed_field_specs(spec)
    field_to_path = {row[0]: row[4] for row in specs}
    name_json_path = specs[spec.ghost_row_anchor_index][4] if specs else ""
    identity_key = spec.row_identity_key

    by_id: dict[str, dict] = {}
    order: list[str] = []
    for row in base_rows:
        rid = str(row.get(identity_key) or "").strip()
        if not rid:
            continue
        by_id[rid] = dict(row)
        order.append(rid)

    pre_existing_ids = set(by_id)
    applied = 0
    visited = 0
    touched_rows: set[str] = set()
    for key in projection.stable_keys():
        fv = projection.get(key)
        if fv is None or getattr(fv, "is_protected", False):
            continue
        rid = getattr(fv, "row_key", None)
        if not rid:
            continue
        target = by_id.get(str(rid))
        if target is None:
            target = {identity_key: str(rid)}
            by_id[str(rid)] = target
            order.append(str(rid))
        field_id = str(key).rsplit("/", 1)[-1]
        json_path = field_to_path.get(field_id)
        if not json_path:
            continue
        visited += 1
        new_val = getattr(fv, "value", None)
        if set_json_path(target, json_path, new_val):
            applied += 1
            touched_rows.add(str(rid))

    ghost_ids = {
        rid
        for rid in order
        if rid not in pre_existing_ids
        and not str(resolve_json_path(by_id[rid], name_json_path) or "").strip()
    }
    if ghost_ids:
        order = [rid for rid in order if rid not in ghost_ids]
        touched_rows -= ghost_ids

    return [by_id[rid] for rid in order], applied, visited, touched_rows
