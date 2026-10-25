"""adopt 覆盖计划 —— 幽灵行门的 **property 测试**（引擎侧语义 + 计划侧登记机制）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 4.5）
Requirements 1.6 · design § Correctness Properties / § prework 合并记录

本文件承载的 property（**一条一函数**，文件按 property 归集）：

| Property | 归属任务 | 状态 |
| --- | --- | --- |
| **Property 3: 幽灵行门语义不变且被如实登记** | Task 4.5 | ✅ 本文件已实现（分两半，见下） |
| **Property 8: 不可枚举形态的载荷不被改动且被登记** | Task 4.6 | ⬜ 未实现，落点在文末分隔线 |

═══ 🔴 Property 3 拆成两半的依据（Task 4.2 的裁定直接决定本文件形态）═══

`compute_overwrite_plan` 的 docstring「🔴 `rows_ghost_dropped` 在计划期**不可兑现**」整节已裁定：
幽灵行门的三个输入（`spec` + `managed_field_specs` 的锚点 json_path ／ merge **之后**的行 ／
merge 私有的两处 `continue`）**没有一个**在计划期输入面上 ⇒ 计划期预测 = 复现引擎判据 =
**第二真源**，且真源住在 `phase5_row_table_sheet`（OO 与 adopt 共用，Requirement 2 保护区）
⇒ 已被否决，改为**观测**。于是 Property 3 原文两句话落在两个被测面上：

| 半 | 原文 | 被测面 | 本文件 |
| --- | --- | --- | --- |
| 前半 | 新增且锚点空 ⇒ 不在结果行集；已存在行锚点空 ⇒ 仍在结果行集 | **引擎** `merge_projection_into_store_rows` | §3 property 级 |
| 后半 | 必定出现在响应的 `rows_ghost_dropped` 清单中 | `adopt_overwrite_compute` 的**登记机制** | §4 例子级 |

🔴 **端到端（merge 后观测 ghost → 经 `ghost_dropped_by_item` 回喂重算 → 响应里真有这份清单）属
Task 6.3，本文件不做。** 后半只证「登记机制在且有区分力」：给一份**注入**的 ghost 清单，它要么
放对 `(table, 分区)`、要么当场抛。计划期自己算真实 ghost 是 4.2 否决的第二真源，本文件**不试**。
连带约束（4.2 已登记）：**`rows_ghost_dropped ⊆ rows_added`** —— Task 3.1 把 ghost 刻意排除在
`_DISJOINT_FIELDS` 之外正是为此（§4 `test_ghost_may_overlap_added` 钉死：它若进了 disjoint
集合，本文件「正常落位」那几例根本构造不出来）。

═══ 🔴 B 与 E 必须互为对照（否则判据不能为 False）═══

requirements.md § Introduction 探针五例表里 **B**（新行无名 ⇒ 剔除）与 **E**（`[r1]` +
`r1.product=""` ⇒ `[r1]`，已存在行清空是合法编辑）是一对。只断言 B 时，「无名行一律剔除」
（不看 `pre_existing_ids`）的实现照样通过而会误删 E 类行；只断言 E 时，「门整个去掉」的实现
照样通过。⇒ §3 用**一个等式**同时表达两者（结果行集 == 已存在身份 ∪ 锚点非空的新增身份），
由 §5 的 M1／M2 各打红一侧；§6 累计器再钉住两类场景本次运行真的都出现过（否则等式恒真 = 空转）。
本任务即把 `test_ghost_row_defense.py` 的**例子级**观测（D1/D3/D4-2/D4-3/D5/D6/D7 七家）升级成
**属性级**：对任意锚点位置、任意身份键、任意「空」取值、任意新增/既有混合都成立。

═══ 建造器：reader 侧复用，merge 侧新造 ═══

`_spec` / `_readers` / `ITEM` / `IDENTITY_KEYS` / `_IDENTITY_ALPHABET` 从
`test_aos_property_row_identity` import（**顶层模块名**形态 —— 该目录无 `__init__.py`，pytest 以
`prepend` 模式把它塞进 `sys.path`；写成 `tests.workpaper_sync.…` 会得到第二个模块实例）。

🔴 **merge 侧建造器必须新造**：`_spec()` 的 `field_specs` 是空元组 ⇒ `managed_field_specs(spec)`
为空 ⇒ 引擎的 `name_json_path` 退化成 `""`、`field_to_path` 为空表（每个 projection 字段都
`continue`）⇒ 拿它测幽灵行门等于什么都没测。reader 建造器与 merge 建造器是两个东西。
projection 替身也不从 `test_ghost_row_defense` import：那边按「固定 table_key + 位置三元」建，
本文件需要控制 `stable_keys()` 的**顺序**（行序判据）并混入**未登记字段 id**。

═══ 现状 grep 确认（本轮逐字现读，不凭记忆；可执行判据见 §6 的源码锚点测试）═══

    pre_existing_ids = set(by_id)                     # ← by_id 来自 base_rows
    ghost_ids = {rid for rid in order
                 if rid not in pre_existing_ids       # ← 只对本次新增生效（E 的依据）
                 and not str(resolve_json_path(by_id[rid], name_json_path) or "").strip()}
    if ghost_ids:
        order = [rid for rid in order if rid not in ghost_ids]
        touched_rows -= ghost_ids                     # ← 幽灵行也不算 touched

而 `name_json_path = managed_field_specs(spec)[spec.ghost_row_anchor_index][4]` ⇒ **锚点字段名
一律从声明取**（`_anchor_of()`），本文件没有任何字段名字面量参与判定。
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync import adopt_overwrite_compute as AOC
from app.services.workpaper_sync import phase5_row_table_sheet as ENGINE
from app.services.workpaper_sync.adopt_overwrite_compute import compute_overwrite_plan
from app.services.workpaper_sync.adopt_overwrite_plan import (
    _DISJOINT_FIELDS,
    _ROW_LIST_FIELDS,
    ItemOverwriteDelta,
    OverwritePlanShapeError,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import EngineRowReader
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    managed_field_specs,
    merge_projection_into_store_rows,
    resolve_json_path,
    set_json_path,
)

# 🔴 复用 Property 10 文件的建造器（见模块 docstring：reader 侧禁抄第二份）。
from test_aos_property_row_identity import (  # noqa: E402
    _SECTION_FIELDS,
    IDENTITY_KEYS,
    ITEM,
    _IDENTITY_ALPHABET,
    _readers,
    _spec,
)

# ── 1. merge 侧建造器（新造；理由见模块 docstring） ─────────────────────────────────────

#: 合成字段表。7 元组 = `(column_key, column, mode, value_type, json_key, header_text, group_cell)`。
#:
#: 🔴 四个字段**刻意覆盖四种锚点形态**（`ghost_row_anchor_index` 在真实树上不是恒 0 —— 引擎该
#: 字段注释明写 D5 的 `[0]` 是枚举 `category`、D6 的 `[0]` 是整数 `seq_no`，两家都显式传 `1`）：
#: 第 3 项 `detail/product` 是 **nested json_path**（`resolve_json_path` 的多段分支），第 4 项
#: `amount` 是数值列（锚点落数值列时 `0` 判空，正是 D6 那条教训的形态）。
#: 🔴 `managed_field_specs` 按 `col_index(row[1])` 重排 ⇒ 列标 A~D 与声明序一致是刻意的（让下标
#: 语义可读）；判定一律走 `_anchor_of()`，不依赖这个巧合。
_MERGE_FIELDS: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    ("seq_no", "A", "editable", "text", "seqNo", "序号", ""),
    ("customer_name", "B", "editable", "text", "customerName", "客户名称", ""),
    ("product", "C", "editable", "text", "detail/product", "产品", ""),
    ("amount", "D", "editable", "amount", "amount", "本期金额", ""),
)

#: 未在 `field_specs` 里登记的字段 id —— 命中引擎 `if not json_path: continue` 那条分支。它仍会
#: **先**建出 shell 行（shell 创建在 `field_to_path.get` 之前，本轮现读确认）⇒ 这是「只有一个杂散
#: 格」缺陷最纯粹的形态：行存在、`visited`/`applied` 都不增。
_UNREGISTERED_FIELD = "aos_p3_unregistered_col"

#: 合成 store item 身份。刻意带 `AOS-P3`，万一漏进任何输出都能被搜到。
MERGE_ITEM = "AOS-P3-SYNTH-rows"

#: base 行锚点的初始业务名。E 类断言靠「它被换掉了」证明清空**真的生效**（而不是「projection
#: 没被应用所以看起来还在」）。
_BASE_ANCHOR_NAME = "基线客户名称"


def _merge_spec(
    *,
    anchor_index: int,
    identity_key: str = "rowId",
    section_field: str = "",
    section_value: str = "",
    table_key: str = "aos_p3_rows",
) -> RowTableSheetSpec:
    """造一条**真** `RowTableSheetSpec`（不是替身 dataclass），带真字段表。

    理由与 Property 10 同源：引擎的锚点解析走 `spec.ghost_row_anchor_index` +
    `managed_field_specs(spec)`，用替身就把「引擎按声明取锚点」换成「替身按声明取锚点」。
    """
    return RowTableSheetSpec(
        managed_sheet="合成受管表AOS-P3", sheet_key="aos-p3-managed", table_key=table_key,
        template_id="AOS_P3", table_name="AosP3Rows", uuid_col="Z",
        first_data_row=2, last_data_row=9, footer_row=10,
        store_item_id=MERGE_ITEM, row_identity_key=identity_key, field_specs=_MERGE_FIELDS,
        ghost_row_anchor_index=anchor_index,
        row_section_field=section_field, row_section_value=section_value,
    )


def _anchor_of(spec: RowTableSheetSpec) -> tuple[str, str]:
    """锚点 `(column_key, json_path)` = `managed_field_specs(spec)[ghost_row_anchor_index]` 第 0/4 位。
    🔴 这**不是**「复现幽灵行门判据」：门的判据是「新增 ∧ 锚点空 ⇒ 剔除」（逻辑），本函数只回答
    「锚点是哪一列」（声明）。4.2 否决的是在计划期复现前者。本文件无字段名字面量参与判定。"""
    row = managed_field_specs(spec)[spec.ghost_row_anchor_index]
    return row[0], row[4]


class _FieldValue:
    """最小 `FieldValue` 替身：引擎只读 `row_key` / `value` / `is_protected`（本轮现读确认）。"""

    def __init__(self, row_key: str, value: Any, *, is_protected: bool = False) -> None:
        self.row_key = row_key
        self.value = value
        self.is_protected = is_protected


class _Projection:
    """最小 projection 替身。dict 保插入序 ⇒ `stable_keys()` 顺序即引擎 `order` 的追加顺序。"""

    def __init__(self, items: dict[str, _FieldValue]) -> None:
        self._items = items

    def stable_keys(self) -> tuple[str, ...]:
        return tuple(self._items)

    def get(self, key: str) -> _FieldValue | None:
        return self._items.get(key)


def _projection(table_key: str, triples: list[tuple[str, str, Any, bool]]) -> _Projection:
    """`(row_identity, field_id, value, is_protected)` 序列 → projection。键形态
    `{table_key}/{row}/{field}` 与生产一致（引擎 `key.rsplit("/", 1)[-1]` 取 field_id）；身份字母表
    含 `/`（D4-22 现算如此）⇒ **故意**让身份里的 `/` 参与拼装，证明 `rsplit` 口径仍成立。"""
    return _Projection(
        {
            f"{table_key}/{row}/{field}": _FieldValue(row, value, is_protected=protected)
            for row, field, value, protected in triples
        }
    )


def _base_row(spec: RowTableSheetSpec, identity: str, *, anchor_value: Any) -> dict[str, Any]:
    """造一条 base（覆盖前已存在）行。锚点用引擎自己的 `set_json_path` 写 —— 手拼嵌套 dict 就成了
    第二份 json_path 实现，nested 路径（`detail/product`）会落错位置。"""
    row: dict[str, Any] = {spec.row_identity_key: identity}
    set_json_path(row, _anchor_of(spec)[1], anchor_value)
    if spec.row_section_field:
        row[spec.row_section_field] = spec.row_section_value
    return row


# ── 2. 「空锚点」取值池 —— 标签由**真引擎**逐值实测钉住（§2 的表格测试） ─────────────────────────────

#: 判定为「锚点为空」的取值。🔴 `0` / `0.0` / `False` 在内**不是凑数**：引擎的
#: `str(x or "").strip()` 口径下它们全部落空，而 D6 的 `[0]=seq_no` 正因此必须改用 `[1]` 作锚点
#: （引擎 `ghost_row_anchor_index` 注释原话：「`0` 是合法真值不是"空"信号」）。
_EMPTY_ANCHORS: tuple[Any, ...] = ("", "   ", "\t\n", None, 0, 0.0, False)

#: 判定为「锚点非空」的取值。含数值 `1` / `12.5`（与上池的 `0` 形成最小对照）、含 `"0abc"`
#: 与 `"-"`（看起来像空但不是）、含带 `/` 的中文自由文本（D4-22 身份族同形）。
_NONEMPTY_ANCHORS: tuple[Any, ...] = ("华东经销商", "0abc", "-", 1, 12.5, "运输费用/营业收入")


class TestAnchorPoolsAreEngineValidated:
    """两个取值池的标签**由生产引擎逐值判定**，不是本文件重写一遍「什么算空」。
    🔴 为什么必须有这一层：§3 的期望值由池标签推出。若标签只是我手写的断言，就等于在测试里
    **复现**了「什么算空」这条判据（4.2 否决的第二真源手法）。改成：标签是**声明**，本类用引擎
    把它验成真；引擎一旦改了「空」的口径（不再 `strip()`、不再把 `0` 当空）本类当场打红并点名值。"""

    @pytest.mark.parametrize("anchor_index", range(len(_MERGE_FIELDS)))
    @pytest.mark.parametrize(
        ("pool", "kept"), [(_EMPTY_ANCHORS, False), (_NONEMPTY_ANCHORS, True)]
    )
    def test_pool_labels_match_the_engine_verdict_on_a_new_row(
        self, pool: tuple[Any, ...], kept: bool, anchor_index: int
    ) -> None:
        spec = _merge_spec(anchor_index=anchor_index)
        anchor_key, _path = _anchor_of(spec)
        for value in pool:
            rows, *_rest = merge_projection_into_store_rows(
                spec,
                projection=_projection(spec.table_key, [("rNew", anchor_key, value, False)]),
                base_rows=[],
            )
            got = [r[spec.row_identity_key] for r in rows]
            assert got == (["rNew"] if kept else []), (
                f"锚点 {anchor_key!r} 取 {value!r} 的新增行 kept={bool(got)}（期望 {kept}）—— 池标签"
                "与引擎口径已漂，§3 的期望值随之失效；不得改断言迁就，先查引擎改了什么。"
                "（门只挡「命名字段完全没写过内容」，不判「像不像真名」——"
                " `test_ghost_row_defense` 那条乱码用例同源）"
            )

    def test_the_two_pools_do_not_overlap(self) -> None:
        """两池不得有交集（同一值既判空又判非空 ⇒ §3 期望值不可确定）。

        🔴 按 `repr` 比不按值比：`0 == False`、`0 == 0.0` 都为真，集合交集会误报 —— 它们在池里是
        三条**独立的形态观测**，不是重复项。
        """
        empty = {repr(v) for v in _EMPTY_ANCHORS}
        nonempty = {repr(v) for v in _NONEMPTY_ANCHORS}
        assert not empty & nonempty, sorted(empty & nonempty)
        assert len(empty) == len(_EMPTY_ANCHORS) and len(nonempty) == len(_NONEMPTY_ANCHORS)


# ── 3. Property 3 前半 —— 引擎那道门的语义（B 与 E 同一个等式，互为对照） ────────────────────────

#: 覆盖**前已存在**行的三种形态。前两种是 E 类（合并后锚点为空，必须仍在结果里），末项是对照组。
_PRE_MODES: tuple[str, ...] = (
    "cleared_by_projection",      # 探针用例 E 原形：base 有名 → projection 清空
    "already_empty_untouched",    # base 锚点本来就空，projection 只碰别的列
    "kept_nonempty",              # 对照组：锚点仍非空
)
#: 本次**新增**行的四种形态。前三种是 B 类（锚点为空，必须被剔除），末项是对照组。
_NEW_MODES: tuple[str, ...] = (
    "anchor_empty",                        # 锚点被写成空值 + 另有杂散格
    "anchor_absent_registered_stray",      # 锚点没出现，只有一个已登记的杂散列
    "anchor_absent_unregistered_stray",    # 杂散列**未登记** ⇒ shell 建了但 visited/applied 不增
    "anchor_nonempty",                     # 对照组：合法新增
)

#: 本次运行实际出现过的场景（§6 反空转判据用；等式在 B/E 都没出现时恒真 = 假绿）。
_SAW: dict[str, int] = {mode: 0 for mode in (*_PRE_MODES, *_NEW_MODES)}
_SAW_IDENTITY_KEYS: set[str] = set()
_SAW_ANCHOR_KEYS: set[str] = set()


@st.composite
def _scenario(draw: st.DrawFn) -> tuple[Any, Any]:
    """生成 `(pre, new)` 两张 `(identity, mode, anchor_value)` 清单，身份全域唯一。
    🔴 `min_size=2` + `split ∈ [1, len-1]` 保证**每次**都同时有「已存在行」与「新增行」—— B 与 E
    必须在**同一次**执行里互为对照（分两次跑就回到「只验一侧」的假绿形态）。"""
    identity = st.text(alphabet=_IDENTITY_ALPHABET, min_size=1, max_size=8)
    ids = draw(st.lists(identity, min_size=2, max_size=5, unique=True))
    split = draw(st.integers(min_value=1, max_value=len(ids) - 1))
    pre: list[tuple[str, str, Any]] = []
    for ident in ids[:split]:
        mode = draw(st.sampled_from(_PRE_MODES))
        pool = _NONEMPTY_ANCHORS if mode == "kept_nonempty" else _EMPTY_ANCHORS
        pre.append((ident, mode, draw(st.sampled_from(pool))))
    new: list[tuple[str, str, Any]] = []
    for ident in ids[split:]:
        mode = draw(st.sampled_from(_NEW_MODES))
        pool = _NONEMPTY_ANCHORS if mode == "anchor_nonempty" else _EMPTY_ANCHORS
        new.append((ident, mode, draw(st.sampled_from(pool))))
    return pre, new


def _usable_section_field(spec_fields: tuple[str, ...], identity_key: str) -> tuple[str, str]:
    """挑一个**现算**分区字段名（禁硬编码，含 `"section"`）；挑不到返回「无分区」。"""
    for field in _SECTION_FIELDS:
        if field not in spec_fields and field != identity_key:
            return field, "aos-p3-seg"
    return "", ""


_Rows = list[tuple[str, str, Any]]


def _build_merge_inputs(
    spec: RowTableSheetSpec, pre: _Rows, new: _Rows
) -> tuple[list[dict[str, Any]], _Projection, list[str]]:
    """按两张清单造 `(base_rows, projection, 期望结果行序)`。期望值**只从 mode 标签推**
    （标签由 §2 用真引擎钉住），不在此处重算「什么算空」。"""
    anchor_key, _anchor_path = _anchor_of(spec)
    stray_key = next(f[0] for f in _MERGE_FIELDS if f[0] != anchor_key)

    base_rows: list[dict[str, Any]] = []
    triples: list[tuple[str, str, Any, bool]] = []
    for ident, mode, value in pre:
        base_anchor = value if mode == "already_empty_untouched" else _BASE_ANCHOR_NAME
        base_rows.append(_base_row(spec, ident, anchor_value=base_anchor))
        if mode == "already_empty_untouched":
            triples.append((ident, stray_key, "噪声", False))
        else:  # cleared_by_projection / kept_nonempty 都由 projection 写锚点
            triples.append((ident, anchor_key, value, False))

    kept_new: list[str] = []
    for ident, mode, value in new:
        if mode == "anchor_empty":
            triples.append((ident, anchor_key, value, False))
            triples.append((ident, stray_key, "噪声", False))
        elif mode == "anchor_absent_registered_stray":
            triples.append((ident, stray_key, "噪声", False))
        elif mode == "anchor_absent_unregistered_stray":
            triples.append((ident, _UNREGISTERED_FIELD, 0, False))
        else:
            triples.append((ident, anchor_key, value, False))
            kept_new.append(ident)

    expected_order = [ident for ident, _m, _v in pre] + kept_new
    return base_rows, _projection(spec.table_key, triples), expected_order


class TestProperty3EngineGhostGateSemantics:
    """Property 3 前半：引擎 `merge_projection_into_store_rows` 的幽灵行门语义不变。

    🔴 一个等式同时表达 B 与 E：**结果行集 == 覆盖前已存在的全部身份 ∪ 锚点非空的新增身份**。
    少了任一半，判据都会对某一类错误实现为真（§5 的 M1／M2 各打红一侧即为此）。
    """

    @pytest.mark.parametrize("anchor_index", range(len(_MERGE_FIELDS)))
    @settings(max_examples=5, deadline=None)
    @given(
        scenario=_scenario(),
        identity_key=st.sampled_from(IDENTITY_KEYS),
        declare_section=st.booleans(),
    )
    def test_property_3_ghost_gate_only_drops_newly_added_unnamed_rows(
        self,
        anchor_index: int,
        scenario: tuple[_Rows, _Rows],
        identity_key: str,
        declare_section: bool,
    ) -> None:
        """Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 3: 幽灵行门语义不变且被如实登记

        **Validates: Requirements 1.6**

        Property 3 的**前半**（引擎侧语义）。后半（`rows_ghost_dropped` 的登记）在 §4；端到端
        （merge 后观测 ghost → 回喂重算 → 响应里真有这份清单）属 **Task 6.3**，不在本文件。
        随机维度：锚点位置（**穷举** 4 种，含 nested 路径与数值列）、行身份键（现算 7 种抽样 ——
        键名不是本 property 的被测对象，Property 10 已穷举）、两侧行数与形态、「空」的具体取值、
        是否声明分区维度。
        """
        pre, new = scenario
        section_field, section_value = (
            _usable_section_field(tuple(f[0] for f in _MERGE_FIELDS), identity_key)
            if declare_section else ("", "")
        )
        spec = _merge_spec(
            anchor_index=anchor_index, identity_key=identity_key,
            section_field=section_field, section_value=section_value,
        )
        anchor_key, anchor_path = _anchor_of(spec)
        base_rows, projection, expected_order = _build_merge_inputs(spec, pre, new)
        rows, _applied, _visited, touched = merge_projection_into_store_rows(
            spec, projection=projection, base_rows=base_rows
        )
        got = [row[spec.row_identity_key] for row in rows]
        where = f"锚点 {anchor_key!r} / 身份键 {identity_key!r} / 分区 {section_field!r}"
        pre_ids = {ident for ident, _m, _v in pre}
        ghosts = {ident for ident, mode, _v in new if mode != "anchor_nonempty"}

        # ① 等式本体（B 与 E 合一）：结果行集 == 已存在 ∪ 锚点非空的新增。
        assert got == expected_order, f"{where}：结果行序/行集不等（期望 {expected_order}）"
        # ② B：本次新增且锚点为空 ⇒ 不出现在结果行集中。
        assert not ghosts & set(got), f"{where}：幽灵身份 {sorted(ghosts & set(got))} 仍在结果里"
        # ③ E：覆盖前已存在的行即使锚点为空也必定仍在结果行集中。
        assert pre_ids <= set(got), f"{where}：已存在身份 {sorted(pre_ids - set(got))} 被误删"
        # ④ 幽灵行也不得算进 touched（引擎 `touched_rows -= ghost_ids`，下游按它判「真的动过」）。
        assert not ghosts & touched, f"{where}：幽灵身份进了 touched {sorted(ghosts & touched)}"

        by_id = {row[spec.row_identity_key]: row for row in rows}
        for ident, mode, _value in pre:
            if mode == "cleared_by_projection":
                # E 的**内容**判据：清空真的落地了（不是「projection 没应用所以看着还在」）。
                assert resolve_json_path(by_id[ident], anchor_path) != _BASE_ANCHOR_NAME, (
                    f"{where}：{ident!r} 仍是 base 名 {_BASE_ANCHOR_NAME!r} —— 清空未生效，"
                    "这条 E 用例退化成了「锚点非空所以没被剔除」，测不到门的 pre_existing 分支"
                )
            _SAW[mode] += 1
        for ident, mode, _value in new:
            _SAW[mode] += 1
            if mode == "anchor_nonempty" and section_field:
                assert by_id[ident].get(section_field) == section_value, (
                    f"{where}：新增行 {ident!r} 没带上分区归属（引擎 shell 创建那段）"
                )
        _SAW_IDENTITY_KEYS.add(identity_key)
        _SAW_ANCHOR_KEYS.add(anchor_key)


# ── 4. Property 3 后半 —— `rows_ghost_dropped` 的**登记机制**（不在计划期算 ghost） ──────
# 🔴 本节**注入** ghost 清单（模拟 Task 6.3 在 merge 之后观测到的结果），只验两件事：① 放对
#    `(table, 分区)`；② 放不进任何分区的 `rows_added` 时当场抛。计划期自己算真实 ghost = 复现引擎
#    判据 = 第二真源（4.2 明确否决）⇒ 本节不试；端到端「观测 → 回喂 → 响应」属 Task 6.3。

#: store 侧现有两条：一条会被 substrate 更新、一条不在 substrate 里（⇒ 删除侧）。
_STORE_UPDATED = "s-updated"
_STORE_DELETED = "s-deleted"
#: substrate 声明三条：命中既有那条 + 两条新增（后者才是 ghost 的合法落点）。
_DECLARED = (_STORE_UPDATED, "g-new-1", "g-new-2")


def _substrate(table_key: str, identities: tuple[str, ...]) -> Any:
    """最小 projection 替身：`compute_overwrite_plan` 只读它的 `row_keys`（现读确认）。"""
    return SimpleNamespace(row_keys={table_key: identities})


def _single_partition_plan(reader: Any, *, ghosts: Any) -> Any:
    spec = _spec(identity_key="rowId")
    payload = [{"rowId": _STORE_UPDATED}, {"rowId": _STORE_DELETED}]
    return compute_overwrite_plan(
        substrate_projection=_substrate(spec.table_key, _DECLARED),
        store_payloads={ITEM: payload},
        row_readers={ITEM: reader},
        ghost_dropped_by_item={ITEM: ghosts},
    )


class TestProperty3GhostIsRegisteredOnTheRightDelta:
    """后半 ①：注入的 ghost 落在**正确的** `(table, 分区)` delta 上，且 `ghost ⊆ rows_added`。"""

    @pytest.mark.parametrize("label", [name for name, _r in _readers(_spec(identity_key="rowId"))])
    def test_injected_ghost_lands_on_the_delta_that_declares_it_as_added(self, label: str) -> None:
        """三个 `RowReader` 实现各跑一遍 —— 登记机制不得依赖 reader 种类。"""
        reader = dict(_readers(_spec(identity_key="rowId")))[label]
        plan = _single_partition_plan(reader, ghosts=["g-new-1"])
        live = [d for d in plan.deltas if d.table_key is not None]
        assert len(live) == 1, f"{label}：单分区应恰 1 条 delta，实得 {len(live)}"
        delta = live[0]
        assert delta.rows_ghost_dropped == ("g-new-1",), (label, delta.rows_ghost_dropped)
        assert set(delta.rows_ghost_dropped) <= set(delta.rows_added), (
            f"{label}：ghost 不是 rows_added 的子集 —— Task 4.2 已把 "
            "`rows_ghost_dropped ⊆ rows_added` 登记为连带约束"
        )
        assert delta.rows_ghost_dropped_count == 1
        # 对照：不注入时计划期**恒空**（4.2 的裁定「本函数不预测幽灵行」的可执行判据）。
        plain = [d for d in _single_partition_plan(reader, ghosts=[]).deltas if d.table_key]
        assert plain[0].rows_ghost_dropped == (), (
            f"{label}：没注入 ghost 却算出了 {plain[0].rows_ghost_dropped} —— 计划期预测幽灵行"
            "就是 Task 4.2 否决的第二真源"
        )

    def test_ghost_goes_to_the_partition_where_it_is_added_not_to_the_first_bucket(self) -> None:
        """🔴 多分区：两个 ghost **各自**落在把它算作新增的那个分区，不是都堆进第一个桶。

        构造使归属唯一：`x1` 只在 segB 侧算新增（segA 侧它是 updated），`g1` 反之。
        ⇒ 一个「按第一个桶放」的实现会把两条都放进 segA 而打红。
        """
        section_field, _v = _usable_section_field(tuple(f[0] for f in _MERGE_FIELDS), "rowId")
        assert section_field, "现算分区字段名为空 ⇒ 本判据无从构造，须查 global_spec_index 是否失效"
        table_key = "aos_p3_multi_rows"
        reader = EngineRowReader(
            item_id=MERGE_ITEM,
            specs=tuple(
                _merge_spec(anchor_index=1, section_field=section_field,
                            section_value=seg, table_key=table_key)
                for seg in ("segA", "segB")
            ),
            section_field=section_field,
            declared_scopes=((table_key, "segA"), (table_key, "segB")),
        )
        payload = [{"rowId": "x1", section_field: "segA"}, {"rowId": "g1", section_field: "segB"}]
        plan = compute_overwrite_plan(
            substrate_projection=_substrate(table_key, ("x1", "g1", "g2")),
            store_payloads={MERGE_ITEM: payload},
            row_readers={MERGE_ITEM: reader},
            ghost_dropped_by_item={MERGE_ITEM: ["x1", "g1"]},
        )
        by_section = {d.row_section: d for d in plan.deltas if d.table_key is not None}
        assert sorted(by_section) == ["segA", "segB"], sorted(by_section)
        assert by_section["segA"].rows_ghost_dropped == ("g1",), by_section["segA"]
        assert by_section["segB"].rows_ghost_dropped == ("x1",), by_section["segB"]
        for section, delta in by_section.items():
            assert set(delta.rows_ghost_dropped) <= set(delta.rows_added), (section, delta)

    def test_ghost_may_overlap_added_because_it_is_not_in_the_disjoint_set(self) -> None:
        """`rows_ghost_dropped` 不在 `_DISJOINT_FIELDS` 里 —— 否则上面几例根本构造不出来。

        Task 3.1 注释原话：把 `ghost ∩ added = ∅` 挪进构造器，Task 4.5 的变异测试就再也看不到它
        是否成立。本条既核结构、又**实际构造**一条 ghost==added 的 delta 证明它真的放行。
        """
        assert "rows_ghost_dropped" in _ROW_LIST_FIELDS
        assert "rows_ghost_dropped" not in _DISJOINT_FIELDS, (
            "ghost 进了 disjoint 集合 ⇒ 连带约束 `ghost ⊆ rows_added` 与构造器互相矛盾"
        )
        delta = ItemOverwriteDelta(
            item_id=MERGE_ITEM, table_key="aos_p3_rows",
            rows_added=("g-new-1",), rows_ghost_dropped=("g-new-1",),
        )
        assert delta.rows_ghost_dropped == ("g-new-1",)


class TestProperty3IllegalGhostFailsVisible:
    """后半 ②：放不进任何分区 `rows_added` 的 ghost **当场抛**（语义已变，不得静默吞）。"""

    @pytest.mark.parametrize(
        ("ghosts", "why"),
        [
            ((_STORE_UPDATED,), "两侧都有 ⇒ 它是 rows_updated，不是本次新增"),
            ((_STORE_DELETED,), "只有 store 有 ⇒ 它是 rows_deleted"),
            (("never-declared-anywhere",), "两侧都没有 ⇒ 身份凭空出现"),
        ],
    )
    def test_ghost_outside_rows_added_raises(self, ghosts: tuple[str, ...], why: str) -> None:
        reader = _readers(_spec(identity_key="rowId"))[0][1]
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            _single_partition_plan(reader, ghosts=list(ghosts))
        message = str(excinfo.value)
        assert ITEM in message and ghosts[0] in message, (why, message[:200])
        assert "rows_added" in message, f"{why}：消息没点出违的是哪条约束 —— {message[:200]}"

    def test_ghost_list_given_as_a_bare_string_raises(self) -> None:
        """`{item: "g-new-1"}` 会被逐字符迭代成一堆假身份 ⇒ `_ghosts_for` 当场抛。"""
        reader = _readers(_spec(identity_key="rowId"))[0][1]
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            _single_partition_plan(reader, ghosts="g-new-1")
        assert ITEM in str(excinfo.value) and "逐字符" in str(excinfo.value)


# ── 5. 变异反证 —— 判据必须能为 False（🔴 全部**进程内**，不改任何共用文件） ─────────────────────────
#
# 🔴 手段 = **源码级进程内变异**：`inspect.getsource` 取生产函数源码 → 替换一个**唯一**锚点子串
#    → 在生产模块 globals 的**副本**里 exec → 得到独立函数对象。不用 `monkeypatch.setattr` 装回
#    模块：`phase5_row_table_sheet` 是 OO 与 adopt 共用（Requirement 2 保护区）且本域有并发会话，
#    装回去即便自动还原也在窗口期内改了共用模块的行为。变异体只被本节直接调用，生产模块一字不动
#    （判据见 `test_mutation_did_not_touch_the_shared_module`）。锚点是子串不是行号（行号会漂）；
#    `count(old) == 1` 让锚点消失时当场打红 —— 那说明门的写法变了，变异反证须重建。


def _source_mutant(func: Any, *, old: str, new: str, module: Any) -> Any:
    """按唯一锚点子串做源码级变异，返回**独立**函数对象（不回写 module）。"""
    src = inspect.getsource(func)
    hits = src.count(old)
    assert hits == 1, (
        f"变异锚点 {old!r} 在 {func.__name__} 源码里命中 {hits} 次（须恰 1）—— 生产代码的写法已变，"
        "本节的变异反证须按新写法重建；不得放宽成「命中就行」"
    )
    namespace = dict(vars(module))  # 🔴 副本 —— exec 不得写进生产模块的 globals
    mutated = "from __future__ import annotations\n" + src.replace(old, new)
    exec(  # noqa: S102 —— 变异体只在本测试进程内存在，不落盘、不回写生产模块
        compile(mutated, f"<aos-p3 mutant {func.__name__}>", "exec"), namespace
    )
    return namespace[func.__name__]


#: **M1 —— 门改成「无名行一律剔除」**（摘掉 `rid not in pre_existing_ids`）。预期：E 打红
#: （已存在行被清空后被误删）、B 仍通过 ⇒ 证明只验 B 不足。
_M1_DROP_ALL_UNNAMED = ("rid not in pre_existing_ids", "True")
#: **M2 —— 门整个去掉**（`if ghost_ids:` 恒假）。预期：B 打红（新增无名行留在结果里）、E 仍通过。
_M2_GATE_REMOVED = ("if ghost_ids:", "if False:")
#: **M3 —— 摘掉「放不进 rows_added 必抛」**（`if unplaced:` 恒假）。预期：§4 三条非法 ghost 判据
#: 全部打红（改为静默吞掉）。
_M3_GHOST_NEVER_RAISES = ("if unplaced:", "if False:")


def _engine_mutant(anchor: tuple[str, str]) -> Any:
    """引擎 merge 的变异体（M1 / M2 共用；生产模块一字不动）。"""
    return _source_mutant(
        merge_projection_into_store_rows, old=anchor[0], new=anchor[1], module=ENGINE
    )


class TestMutationCounterProof:
    """三组变异各贴一侧红 —— B 与 E 互为对照，登记机制的抛也有区分力。"""

    def _scenario_inputs(self) -> tuple[RowTableSheetSpec, Any, list[dict[str, Any]], Any]:
        """一份同时含 E 类与 B 类行的最小输入（与 §3 的 property 同形，固定取值便于逐行对账）。"""
        spec = _merge_spec(anchor_index=1)
        anchor_key, _path = _anchor_of(spec)
        base_rows = [_base_row(spec, "rOld", anchor_value=_BASE_ANCHOR_NAME)]
        projection = _projection(
            spec.table_key,
            [
                ("rOld", anchor_key, "", False),        # E：已存在行被清空
                ("rNew", "amount", 0, False),           # B：新增行只有一个杂散格
                ("rKeep", anchor_key, "华东经销商", False),  # 对照：合法新增
            ],
        )
        return spec, projection, base_rows, anchor_key

    def _ids(self, fn: Any, spec: RowTableSheetSpec, projection: Any, base: list[dict]) -> list[str]:
        rows, *_rest = fn(spec, projection=projection, base_rows=[dict(r) for r in base])
        return [row[spec.row_identity_key] for row in rows]

    def test_production_keeps_cleared_existing_row_and_drops_new_unnamed_row(self) -> None:
        """对照组：生产实现 B 与 E 同时成立（下面两个变异体才有对照基准）。"""
        spec, projection, base, _ak = self._scenario_inputs()
        assert self._ids(merge_projection_into_store_rows, spec, projection, base) == [
            "rOld",
            "rKeep",
        ]

    def test_m1_drop_all_unnamed_breaks_the_e_side_only(self) -> None:
        """M1：不看 `pre_existing_ids` ⇒ **E 打红、B 仍绿** ⇒ 只断言 B 的测试会把 M1 判绿。"""
        spec, projection, base, _ak = self._scenario_inputs()
        got = self._ids(_engine_mutant(_M1_DROP_ALL_UNNAMED), spec, projection, base)
        assert "rOld" not in got, (
            "M1 竟然保住了被清空的已存在行 —— 变异没生效（替换没打到那一子句？），反证失去意义"
        )
        assert "rNew" not in got, "M1 应当仍然剔除新增无名行（B 侧不受影响）"
        assert got == ["rKeep"], got

    def test_m2_gate_removed_breaks_the_b_side_only(self) -> None:
        """M2：门整个去掉 ⇒ **B 打红、E 仍绿** ⇒ 只断言 E 的测试会把 M2 判绿。"""
        spec, projection, base, _ak = self._scenario_inputs()
        got = self._ids(_engine_mutant(_M2_GATE_REMOVED), spec, projection, base)
        assert "rNew" in got, "M2 竟然仍剔除了新增无名行 —— 变异没生效，这条反证失去意义"
        assert "rOld" in got, "M2 应当仍然保住已存在行（E 侧不受影响）"
        assert got == ["rOld", "rNew", "rKeep"], got

    def test_m3_ghost_registration_without_the_raise_silently_swallows(self) -> None:
        """M3：摘掉 `if unplaced:` ⇒ 非法 ghost **静默消失**（§4 那三条判据全部打红）。"""
        spec = _spec(identity_key="rowId")
        reader = _readers(spec)[0][1]
        kwargs = dict(
            item_id=ITEM, reader=reader,
            payload=[{"rowId": _STORE_UPDATED}, {"rowId": _STORE_DELETED}],
            scopes=tuple(reader.declared_scopes),
            row_keys={spec.table_key: _DECLARED},
            ghosts=(_STORE_DELETED,),  # 删除侧身份，绝不可能是「本次新增」
        )
        with pytest.raises(OverwritePlanShapeError):
            AOC._deltas_for_item(**kwargs)  # 对照组：生产实现抛
        mutant = _source_mutant(
            AOC._deltas_for_item, old=_M3_GHOST_NEVER_RAISES[0],
            new=_M3_GHOST_NEVER_RAISES[1], module=AOC,
        )
        deltas = mutant(**kwargs)
        registered = {g for d in deltas for g in d.rows_ghost_dropped}
        assert registered == set(), (
            f"M3 竟然把非法 ghost 登记进了某条 delta（{sorted(registered)}）—— 变异没生效"
        )
        assert deltas, "M3 应当仍产出 delta（它只是不抛），实得空清单 ⇒ 变异打到了别处"

    def test_mutation_did_not_touch_the_shared_module(self) -> None:
        """🔴 变异不得污染共用模块：三个锚点在**实时**生产源码里仍各恰 1 处、且未被替换。
        `phase5_row_table_sheet` 是 OO callback 与 adopt 共用（Requirement 2 保护区）⇒ 这条是
        「用进程内变异而不是改文件」这个手段本身的验收判据：变异体若被回写，锚点就不在了。"""
        cases = (
            (ENGINE, merge_projection_into_store_rows, _M1_DROP_ALL_UNNAMED),
            (ENGINE, merge_projection_into_store_rows, _M2_GATE_REMOVED),
            (AOC, AOC._deltas_for_item, _M3_GHOST_NEVER_RAISES),
        )
        for module, func, (old, new) in cases:
            live = getattr(module, func.__name__)
            src = inspect.getsource(live)
            assert src.count(old) == 1, (func.__name__, old, src.count(old))
            assert new not in src, (
                f"{func.__name__} 的实时源码里出现了变异串 {new!r} —— 变异体被回写进了生产模块"
            )


# ── 6. 反空转判据（现状锚点 + 场景覆盖面 + 锚点字段名非硬编码） ────────────────────────────────────

#: 门的三个输入在引擎源码里的锚点（**现状 grep 确认**，逐字取自本轮现读）。🔴 判据是「各恰 1 处」
#: 而不是「存在」：出现第二处即说明门被复制了一份（第二真源）。
_GATE_SOURCE_ANCHORS: tuple[str, ...] = (
    r"pre_existing_ids = set\(by_id\)",                 # 输入①：base_rows ⇒ 已存在身份
    r"\[spec\.ghost_row_anchor_index\]\[4\]",           # 输入②：锚点 json_path 的取法
    r"rid not in pre_existing_ids",                     # 门的「只对新增生效」子句
    r"touched_rows -= ghost_ids",                       # 幽灵行也不算 touched
)


class TestGateSourceAnchorsAreLive:
    """现状锚点现算（含正则的核验落在测试文件里，不用 `python -c`）。"""

    def test_each_gate_anchor_appears_exactly_once_in_the_engine(self) -> None:
        src = Path(ENGINE.__file__).read_text(encoding="utf-8")
        counts = {p: len(re.findall(p, src, flags=re.MULTILINE)) for p in _GATE_SOURCE_ANCHORS}
        assert all(n == 1 for n in counts.values()), counts
        # 变异对照：同一扫描器对一个**不该存在**的形态必须得 0（证明它不是「什么都命中」）。
        assert not re.findall(r"rid in pre_existing_ids\b", src), (
            "引擎里出现了反向子句 —— 门的语义可能被整个翻转，本文件全部期望值须重算"
        )

    def test_the_ghost_gate_lives_only_inside_the_merge_function(self) -> None:
        """`ghost_ids` 的出现处**全部**落在 `merge_projection_into_store_rows` 函数体内 —— 这正是
        Task 4.2 那条裁定的依据：门只有一处、且在 merge 里 ⇒ 计划期要它只能复制。"""
        whole = Path(ENGINE.__file__).read_text(encoding="utf-8")
        inside = inspect.getsource(merge_projection_into_store_rows)
        total = len(re.findall(r"\bghost_ids\b", whole))
        assert total > 0 and total == len(re.findall(r"\bghost_ids\b", inside)), (
            f"`ghost_ids` 全仓 {total} 处，而 merge 函数体内只有 "
            f"{len(re.findall(r'ghost_ids', inside))} 处 ⇒ 门被复制到了别处（第二真源）"
        )


class TestProperty3DidNotRunVacuously:
    """§3 的等式在「B 或 E 一类都没出现」时恒真 ⇒ 必须钉住两类场景真的都跑过。"""

    def test_both_b_and_e_scenarios_were_exercised(self) -> None:
        if not any(_SAW.values()):
            pytest.skip("本次选择未执行 Property 3（如 -k 定向）⇒ 累计器为空，本判据无从成立")
        e_side = {m: _SAW[m] for m in _PRE_MODES if m != "kept_nonempty"}
        b_side = {m: _SAW[m] for m in _NEW_MODES if m != "anchor_nonempty"}
        assert sum(e_side.values()) > 0, f"E 类（已存在行锚点为空）一次都没出现：{e_side}"
        assert sum(b_side.values()) > 0, f"B 类（新增行锚点为空）一次都没出现：{b_side}"
        assert _SAW["kept_nonempty"] + _SAW["anchor_nonempty"] > 0, (
            f"对照组（锚点非空）一次都没出现 ⇒ 等式可能被「全剔除」实现满足：{_SAW}"
        )

    def test_anchor_positions_were_exhausted_and_never_hardcoded(self) -> None:
        """🔴 四个锚点位置**穷举**跑过，且锚点字段名由 `ghost_row_anchor_index` **决定**。

        判据形态 = 变下标必变字段名（四个下标得四个互不相同的 column_key 与 json_path）⇒ 任何
        「写死某个字段名」的实现（包括本测试自己写死）都无法同时满足四个下标。
        """
        got = [_anchor_of(_merge_spec(anchor_index=i)) for i in range(len(_MERGE_FIELDS))]
        assert len({k for k, _p in got}) == len(got) == len({p for _k, p in got}), got
        assert [p for _k, p in got if "/" in p], f"没有 nested json_path ⇒ 多段分支没覆盖：{got}"
        if not _SAW_ANCHOR_KEYS:
            pytest.skip("本次选择未执行 Property 3 ⇒ 累计器为空")
        assert _SAW_ANCHOR_KEYS == {k for k, _p in got}, sorted(_SAW_ANCHOR_KEYS)

    def test_identity_key_dimension_was_sampled_from_the_live_domain(self) -> None:
        """身份键取值来自**现算**域（Property 10 的 `IDENTITY_KEYS`），不是本文件的字面量。"""
        assert len(IDENTITY_KEYS) >= 7, (
            f"现算身份键域收窄到 {len(IDENTITY_KEYS)} 种（design 记 7）—— 须回 spec 登记差异"
        )
        if not _SAW_IDENTITY_KEYS:
            pytest.skip("本次选择未执行 Property 3 ⇒ 累计器为空")
        assert _SAW_IDENTITY_KEYS <= set(IDENTITY_KEYS), sorted(_SAW_IDENTITY_KEYS)

    def test_unregistered_stray_field_really_is_unregistered(self) -> None:
        """`_UNREGISTERED_FIELD` 必须不在字段表里，否则那一档退化成普通杂散列。"""
        assert _UNREGISTERED_FIELD not in {f[0] for f in _MERGE_FIELDS}
        spec = _merge_spec(anchor_index=0)
        rows, applied, visited, touched = merge_projection_into_store_rows(
            spec,
            projection=_projection(spec.table_key, [("rNew", _UNREGISTERED_FIELD, 1, False)]),
            base_rows=[],
        )
        # shell 建了（引擎 shell 创建在 `field_to_path.get` 之前）但一个字段都没落 ⇒ 必被剔除。
        assert rows == [] and applied == 0 and visited == 0 and touched == set()


# ── ── Property 8（Task 4.6）落点 ──────────────────────────────────────────────── ──
#
# **Property 8: 不可枚举形态的载荷不被改动且被登记**
# **Validates: Requirements 4.1**
#
# 🔴 本文件交付时已逼近 `.py` 门禁 **800**（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，
#    pre-commit 与 CI 的 `file-size-guard` 同源）⇒ Property 8 **几乎一定要抽伴生文件**（域内先例：
#    `test_aos_property_unreadable_payload.py` 由 `test_aos_property_row_identity.py` 切出），
#    切了在此留指针注释；若真要写在本文件下方，不要改上面任何断言语义。
#
# 可直接复用的建造器（禁抄第二份）：`_merge_spec(anchor_index=…, identity_key=…, section_field=…,
#    section_value=…, table_key=…)` / `MERGE_ITEM` / `_substrate(table_key, identities)` /
#    `_source_mutant(func, old=…, new=…, module=…)`（**进程内**源码级变异，不改共用文件、不回写
#    生产模块，Property 8 的变异反证可直接用）/ 从 `test_aos_property_row_identity` 导入的
#    `_readers` / `_spec` / `ITEM` / `IDENTITY_KEYS`。
#
# 🔴 Property 8 的两个断言面（design 原文）：① 该 item 载荷在删除侧**逐字节不变**（被测函数
#    `adopt_overwrite_plan.prune_undeclared_rows`）② 必定以 `(item_id, reason)` 出现在
#    `OverwritePlan.skipped_items`（`ItemOverwriteDelta(skipped_reason=…)` 的派生投影）。与本文件
#    的两半分工无关，不要混写。`SkipReason` 是**封闭六成员**（ADR-AOS-005 §5(4)）⇒ 生成器的原因
#    取值域应从枚举现取，不写字面量清单。
