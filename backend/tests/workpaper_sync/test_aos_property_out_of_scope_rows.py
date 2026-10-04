"""adopt 覆盖计划 —— **作用域外的行逐元素不变**（Property 2 的伴生文件）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 4.4）
Requirements 1.2 / 1.4 · design § Correctness Properties · ADR-AOS-002 · 删除侧六道保护第 1~3 道

| Property | 归属任务 | 状态 |
| --- | --- | --- |
| **Property 2: 作用域外的行逐元素不变** | Task 4.4 | ✅ 本文件 |

═══ 🔴 为什么是伴生文件而不是追加进 `test_aos_property_plan_rowsets.py` ═══

那份（Task 4.3，Property 1）交付后 **753** 行，`.py` 门禁 **800**
（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit 与 CI 的 `file-size-guard`
同源）⇒ 余量 47 行，装不下本 property 的两维判据 + 五组变异反证。按门禁自己给的处置顺序抽伴生
文件（测试侧先例：`test_aos_property_unreadable_payload.py` 由 `test_aos_property_row_identity.py`
切出；生产侧四例见 Task 4.2 记录）。被切一侧的指针注释已在那份文件末尾。

═══ 🔴 建造器复用与**一处刻意不复用** ═══

复用 `test_aos_property_plan_rowsets` 的 `_identities` / `_scenario` / `_rows_of` / `_plan_for` /
`_deltas_for`，以及 `test_aos_property_row_identity` 的 `_spec` / `_readers` / `_row` / `ITEM` /
`IDENTITY_KEYS` / `declared_section_fields`。import 用**顶层模块名**形态（该目录无 `__init__.py`，
pytest 以 `prepend` 模式把它塞进 `sys.path`；写成 `tests.workpaper_sync.…` 会得到第二个模块实例，
模块级累计器就会分家）。

🔴 **`_MUTANT_REDS` / `_expect_red` 刻意不复用** —— 交接说明把它们列进了「可复用」清单，但
Task 4.3 的收口判据是 `assert set(_MUTANT_REDS) == set(_MUTANT_GROUPS)`（恰三组 M1~M3）。往那个
共享 dict 里写本文件的变异组名会让**它**打红 ⇒ 本文件另立 :data:`_P2_MUTANT_REDS`。
（红数累计器不是「真源」，场景建造器才是；复用后者、各记各的红是唯一不互相破坏的分法。）

🔴 **不动 `_assert_property_1`**：它是 Property 1 的唯一判据。本文件的判据是
:func:`_assert_property_2`，两者互不调用。

═══ 两维与「逐元素」的粒度（Property 2 原文的两个要点）═══

* **(a) 维**：`table_key` **不在** `row_keys` 键集合中的表。复用 `_scenario(mode="undeclared")`
  —— Task 4.3 只把它当变异反证的对照组、断言的是**集合**相等；本文件补的是**序列 + 对象身份**。
* **(b) 维**：同一载荷内不属本次声明分区的行。三类行同时在场（现算构造，见 :func:`_b_payload`）：
  ① 兄弟分区（有 spec、`section_of` 判得出，但其 table 不在 `row_keys` 里）；
  ② 分区值未被任何 spec 覆盖（reader **根本枚举不到**）；③ 作用域内的行（其中一部分**真被删**，
  否则「不变」在空集上恒真）。

* **逐元素粒度**：`prune_undeclared_rows` 的 docstring 明写「保留的行对象原样复用，不复制」
  ⇒ 载荷是**已解析序列**时断言到**对象 `is` 相等**；是 **JSON 文本**时 prune 内部必须先解析
  （`_as_row_list`）⇒ 对象身份无从谈起，降级为「逐元素 `==` + 身份序列相等」。零删除时两种形态
  都断言 `pruned is payload`（那条「连重序列化都不会发生」的字面承诺）。

═══ 🔴 一条本轮实证的**不可达**结论（登记而非硬造） ═══

任务书列的第三组变异「把未声明分区值归一成 `None`」在**生产接线下不可达**：`in_scope` 只有在
存在 `section == None` 的 scope 时才有「无分区」桶，而 `adopt_row_reader._declared_scopes` 的
`(str(row_section_value or "") if section_field else None)` 决定了 —— `section_field` 非空时
分区值恒为 `str`（空值得 `""`，那是**退化声明**、prune 与 `_in_scope_by_section` 两处都当场抛），
`section_field` 为空时才得 `None`，而那时**不存在**「未声明的分区值」（`section_of` 恒 `None`）。
⇒ 归一成 `None` 只会把行放进一个**不存在**的桶，行仍被保留，判据打不出红。
可达的同型危害是「把未声明的分区值归一进**某个已声明**桶」，本文件按两种真实形态各给一组红：
**M3**（`section_value_of` 做 `strip()` —— 该函数 docstring 点名禁止的那一条）与
**M4**（prune 的分区查表加「取不到就落进第一个桶」兜底）。
结构性依据本身也是判据，不是散文：见 :meth:`TestNoneCollapseIsUnreachable`。

🔴 **建议（不动手改 design / requirements，仅提出）**：Property 2 的 (b) 维文本可补一句限定
「……不属本次 projection 声明分区的行（含**未被任何 spec 覆盖**因而读不到的分区值）」——
现行文本读起来只覆盖「兄弟分区」，而实测第二类（读不到的分区值）才是 M5 唯一能打红的那类。
"""
from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlanShapeError,
    prune_undeclared_rows,
)
from app.services.workpaper_sync.adopt_row_reader import (
    _declared_scopes,
    _FacadeRowReader,
)
from app.services.workpaper_sync.adopt_row_reader_r3 import EngineRowReader
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    iter_store_rows as engine_iter_store_rows,
)

# 🔴 建造器复用（见模块 docstring：禁抄第二份；`_MUTANT_REDS` 刻意不在此列）。
from test_aos_property_plan_rowsets import (  # noqa: E402
    _identities,
    _plan_for,
    _rows_of,
    _scenario,
)
from test_aos_property_row_identity import (  # noqa: E402
    IDENTITY_KEYS,
    ITEM,
    _readers,
    _row,
    _spec,
    declared_section_fields,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 分区维的现算取值域（🔴 字段名取自**声明**，禁硬编码 —— 含 `"section"`）
# ═══════════════════════════════════════════════════════════════════════════

#: 现算全域声明过的分区字段名。取法 = `RowTableSheetSpec.row_section_field` 的非空取值
#: （`declared_section_fields()` 走 `global_spec_index()`）。本文件**没有任何分区字段名字面量**
#: 参与判定，判据见 :meth:`TestSectionFieldComesFromDeclaration`。
_SECTION_FIELDS: tuple[str, ...] = declared_section_fields()

#: (b) 维两张表：`_IN` 会被 substrate 声明、`_OUT` 不会（兄弟分区的落点）。
_TABLE_IN = "aos_p2_in_scope_rows"
_TABLE_OUT = "aos_p2_sibling_rows"

#: 三个分区值。`_SEG_IN` / `_SEG_SIBLING` 各有 spec；`_SEG_UNENUMERATED` **没有** spec ⇒
#: 引擎的分区过滤（`str(row.get(field) or "") != spec.row_section_value` ⇒ `continue`）让它
#: 一行都 yield 不出来 —— 那类行只能靠「按**位置**摘」保住，是 M5 唯一能打红的那类。
_SEG_IN = "aos-p2-segIn"
_SEG_SIBLING = "aos-p2-segSibling"
_SEG_UNENUMERATED = "aos-p2-segZ"

#: 本次运行实际出现过的正面场景（作用域内**真被删**的行数 / 作用域外**真保住**的行数）。
#: 🔴 没有它，「作用域外不变」在「作用域内也什么都没删」的输入上恒真。
_LIVE_CASES: list[tuple[str, int, int]] = []

#: 变异组名 → 打红次数。🔴 **本文件独有**（不写 Task 4.3 的 `_MUTANT_REDS`，理由见模块 docstring）。
_P2_MUTANT_REDS: dict[str, int] = {}


def _section_field() -> str:
    """挑一个现算分区字段名；须不撞行身份键（否则 `_row` 会把身份覆盖掉）。"""
    for field in _SECTION_FIELDS:
        if field not in IDENTITY_KEYS:
            return field
    raise AssertionError(
        f"现算分区字段名 {list(_SECTION_FIELDS)} 全部撞上行身份键 {list(IDENTITY_KEYS)} —— "
        "(b) 维无从构造，须查 global_spec_index 是否失效（不得回退成硬编码字段名）"
    )


def _p2_spec(*, table_key: str, section_value: str, identity_key: str) -> RowTableSheetSpec:
    """(b) 维专用 spec：换 table 与分区值，其余沿用 `_spec()`（同一份合成声明，不另造）。"""
    return replace(
        _spec(
            identity_key=identity_key,
            section_field=_section_field(),
            section_value=section_value,
        ),
        table_key=table_key,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. (b) 维建造器 —— 多分区 reader + 三类行交错的载荷
# ═══════════════════════════════════════════════════════════════════════════


def _b_specs(identity_key: str) -> tuple[RowTableSheetSpec, ...]:
    """两条 spec：`_SEG_IN` 挂 `_TABLE_IN`、`_SEG_SIBLING` 挂 `_TABLE_OUT`。

    🔴 `_SEG_UNENUMERATED` 刻意**没有** spec —— 那正是「分区值未被任何 spec 覆盖」这一类。
    """
    return (
        _p2_spec(table_key=_TABLE_IN, section_value=_SEG_IN, identity_key=identity_key),
        _p2_spec(table_key=_TABLE_OUT, section_value=_SEG_SIBLING, identity_key=identity_key),
    )


def _b_readers(identity_key: str) -> tuple[tuple[str, Any], ...]:
    """(b) 维的两个 `RowReader` 实现（都吃多 spec）。

    🔴 不复用 `_readers()`：它按**单** spec 造，`declared_scopes` 只含一个 scope
    （交接说明已点明）⇒ 兄弟分区无从表达。这里的 scope 对**两个**分区都声明 —— 与生产一致
    （`adopt_row_reader._declared_scopes` 从 spec 推，spec 有几段就有几个 scope）；
    `_TABLE_OUT` 落在作用域外靠的是它**不在 `row_keys` 键集合里**，不是靠少声明一个 scope。
    """
    specs = _b_specs(identity_key)
    field = _section_field()
    scopes = tuple((s.table_key, s.row_section_value) for s in specs)
    engine = EngineRowReader(
        item_id=ITEM, specs=specs, section_field=field, declared_scopes=scopes
    )

    def invoke(payload: Any) -> Iterator[tuple[str, Mapping[str, Any]]]:
        """多段门面：逐 spec `yield from` 引擎 —— 与现算 25 个真门面同构的薄转发。"""
        for spec in specs:
            yield from engine_iter_store_rows(spec, payload)

    facade = _FacadeRowReader(
        item_id=ITEM, invoke=invoke, section_field=field, declared_scopes=scopes
    )
    return (("EngineRowReader", engine), ("_FacadeRowReader", facade))


def _b_payload(
    *,
    identity_key: str,
    in_updated: Iterable[str],
    in_deleted: Iterable[str],
    siblings: Iterable[str],
    unenumerated: Iterable[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """交错构造 `(载荷, 作用域外的行对象子序列)`。

    🔴 **必须交错**：作用域外的行夹在被删的行之间，顺序变化才可见。全堆在尾部时「按 iter_rows
    重建」这种实现也能给出同一个子序列（M5 就打不出红了）。
    """
    field = _section_field()
    buckets = (
        [(i, _SEG_SIBLING, True) for i in siblings],
        [(i, _SEG_IN, False) for i in in_updated],
        [(i, _SEG_UNENUMERATED, True) for i in unenumerated],
        [(i, _SEG_IN, False) for i in in_deleted],
    )
    payload: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []
    for ordinal in range(max((len(b) for b in buckets), default=0)):
        for bucket in buckets:
            if ordinal >= len(bucket):
                continue
            identity, section, is_outside = bucket[ordinal]
            row = _row(identity_key, identity, noise={}, section=(field, section))
            payload.append(row)
            if is_outside:
                outside.append(row)
    return payload, outside


# ═══════════════════════════════════════════════════════════════════════════
# 2. Property 2 的**唯一**判据（两维共用；与 `_assert_property_1` 互不调用）
# ═══════════════════════════════════════════════════════════════════════════


def _identity_seq(rows: Iterable[Any], identity_key: str) -> list[str]:
    return [str(row[identity_key]) for row in rows]


def _assert_property_2(
    *,
    label: str,
    payload_before: Any,
    rows_before: list[Mapping[str, Any]],
    outside: list[Mapping[str, Any]],
    outside_tables: frozenset[str],
    pruned: Any,
    deleted: tuple[str, ...],
    deltas: Iterable[ItemOverwriteDelta],
    identity_key: str,
    by_object: bool,
) -> None:
    """五条断言。变异体喂进来必须打红（`AssertionError`）。

    :param rows_before: 覆盖前的**行对象序列**（已解析形态即入参本身）。
    :param outside: 作用域外的行对象**子序列**（构造时标定 —— 这是测试自己的构造知识，
        不是把生产的三条门再实现一遍）。
    :param by_object: 载荷是已解析序列 ⇒ 断言到对象 `is`；JSON 文本 ⇒ 降级为 `==`
        （prune 内部必须先解析，对象身份无从谈起）。
    """
    outside_ids = _identity_seq(outside, identity_key)
    assert len(set(outside_ids)) == len(outside_ids), f"{label}：作用域外身份有重复，判据会串味"

    # ① 作用域外的表一条 delta 都不该产（Requirement 1.2 / ADR-AOS-002 作用域门）
    stray = [d for d in deltas if d.table_key in outside_tables]
    assert not stray, (
        f"{label}：作用域外的表 {sorted(outside_tables)} 产出了 {len(stray)} 条 delta"
        f"（rows_deleted={[d.rows_deleted for d in stray]}）—— 作用域门失效。🔴 最典型成因是把 "
        "`table_key in row_keys` 换成 `.get(table_key) or ()`，那会把「未声明」压成「声明为空」"
    )
    # ② 作用域外的身份一个都不许进删除清单（prune 实际删的 + 每条 delta 报的）
    hit = sorted(set(outside_ids) & set(deleted))
    assert not hit, f"{label}：prune 删掉了作用域外的行 {hit}"
    for delta in deltas:
        bad = sorted(set(outside_ids) & set(delta.rows_deleted))
        assert not bad, f"{label}：delta({delta.table_key}/{delta.row_section}) 报删了 {bad}"

    # ③ 🔴 **逐元素**（Property 2 原文说的是「身份**序列**」，不是集合）
    pruned_rows = _rows_of(pruned)
    kept_outside = [r for r in pruned_rows if str(r[identity_key]) in set(outside_ids)]
    assert _identity_seq(kept_outside, identity_key) == outside_ids, (
        f"{label}：作用域外的身份**序列**变了 —— 覆盖后 "
        f"{_identity_seq(kept_outside, identity_key)} != 覆盖前 {outside_ids}。"
        "集合相等在这里不够：`prune_undeclared_rows` 是按**位置**摘（`kept = [element for "
        "ordinal, element in enumerate(rows) if ordinal not in doomed]`）⇒ 顺序本应逐元素保持；"
        "顺序变了说明实现改成了「从 reader.iter_rows 重建载荷」，而那会连未被枚举的分区值一起丢"
    )
    if by_object:
        # 「保留的行对象原样复用，不复制」—— prune 的 docstring 按字面兑现，这里断到 `is`
        same = [k is e for k, e in zip(kept_outside, outside)]
        assert all(same) and len(same) == len(outside), (
            f"{label}：作用域外的行**对象**被换掉了（逐元素 is 结果 {same}）—— 身份序列相等但"
            "对象不同，说明载荷被重建过一遍（哪怕值一样，也已经不是「一个字节都不碰」）"
        )
    else:
        assert kept_outside == outside, f"{label}：作用域外的行内容变了（JSON 文本形态按 == 比）"

    # ④ 全序列保序：留下的行（含作用域内未被删的）必须仍是原序（Requirement 1.2 字面兑现）
    expected_kept = [
        r for r in rows_before if str(r[identity_key]) not in set(deleted)
    ]
    assert _identity_seq(pruned_rows, identity_key) == _identity_seq(
        expected_kept, identity_key
    ), (
        f"{label}：保留行的整体顺序变了 —— 实得 {_identity_seq(pruned_rows, identity_key)}，"
        f"应为原序去掉被删的 {_identity_seq(expected_kept, identity_key)}"
    )
    # ⑤ 零删除 ⇒ 返回**入参对象本身**（连重序列化都不发生；两种载荷形态都适用）
    if not deleted:
        assert pruned is payload_before, (
            f"{label}：一行都没删却没有返回入参对象本身（实得 {type(pruned).__name__}）—— "
            "prune 的「零删除时 `is` 相等」承诺破；重序列化会让 item 白白虚报一次变更"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 2 —— (a) 维：`table_key` 不在 `row_keys` 键集合中的表
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2UndeclaredTableIsUntouched:
    """(a) 维：整张表未被声明 ⇒ 逐元素不变，且一条 delta 都不产。"""

    @settings(max_examples=5, deadline=None)
    @given(
        both=_identities("upd-"),
        only_substrate=_identities("add-"),
        only_store=_identities("del-"),
        as_json_text=st.booleans(),
        key_pick=st.integers(min_value=0, max_value=len(IDENTITY_KEYS) * 3),
    )
    def test_property_2_dimension_a_rows_are_elementwise_unchanged(
        self,
        both: list[str],
        only_substrate: list[str],
        only_store: list[str],
        as_json_text: bool,
        key_pick: int,
    ) -> None:
        """Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 2: 作用域外的行逐元素不变

        **Validates: Requirements 1.2, 1.4**

        (a) 维。载荷复用 `_scenario(mode="undeclared")`（Task 4.3 的「不在键集合」形态）——
        它只断言过集合相等；本条补**序列 + 对象身份 + 零删除 `is`**。
        `RowReader` 实现维度穷举（3 个），载荷形态与身份键随机。

        🔴 反例同批做掉：同一份载荷把该表**声明**进 `row_keys` 后，`only_store` 那几行必须真被删
        —— 否则「不变」是因为这份输入根本没有可删的行（恒真），判据无区分力。
        """
        identity_key = IDENTITY_KEYS[key_pick % len(IDENTITY_KEYS)]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _scenario(
            mode="undeclared",
            both=both,
            only_substrate=only_substrate,
            only_store=only_store,
            identity_key=identity_key,
            as_json_text=as_json_text,
        )
        assert declared is None and spec.table_key not in row_keys
        rows_before = _rows_of(payload)
        for reader_label, reader in _readers(spec):
            where = f"{reader_label} / (a) 维 / 键名 {identity_key!r} / text={as_json_text}"
            pruned, deleted = prune_undeclared_rows(
                payload, row_keys=row_keys, reader=reader
            )
            _assert_property_2(
                label=where,
                payload_before=payload,
                rows_before=rows_before,
                outside=rows_before,  # (a) 维：**整表**都在作用域外
                outside_tables=frozenset({spec.table_key}),
                pruned=pruned,
                deleted=deleted,
                deltas=_plan_for(row_keys=row_keys, payload=payload, reader=reader).deltas,
                identity_key=identity_key,
                by_object=not as_json_text,
            )
            # 反例：声明这张表 ⇒ store 独有的行**真被删**（判据不是恒真）
            counter_keys = {spec.table_key: tuple([*both, *only_substrate])}
            _kept, counter_deleted = prune_undeclared_rows(
                payload, row_keys=counter_keys, reader=reader
            )
            assert set(counter_deleted) == set(only_store) and counter_deleted, (
                f"{where}：反例组把表声明进 row_keys 后应删掉 {sorted(only_store)}，"
                f"实删 {list(counter_deleted)} —— 一行都没删说明这份输入无从区分「不碰」与「删」"
            )
            _LIVE_CASES.append(("a", len(counter_deleted), len(rows_before)))


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 2 —— (b) 维：同一载荷内不属本次声明分区的行
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty2UndeclaredSectionIsUntouched:
    """(b) 维：兄弟分区 + 未被任何 spec 覆盖的分区值，在「同分区确有删除」时仍逐元素不变。"""

    @settings(max_examples=5, deadline=None)
    @given(
        in_updated=_identities("upd-"),
        in_deleted=_identities("del-"),
        siblings=_identities("sib-"),
        unenumerated=_identities("unenum-"),
        as_json_text=st.booleans(),
        key_pick=st.integers(min_value=0, max_value=len(IDENTITY_KEYS) * 3),
    )
    def test_property_2_dimension_b_sibling_sections_are_elementwise_unchanged(
        self,
        in_updated: list[str],
        in_deleted: list[str],
        siblings: list[str],
        unenumerated: list[str],
        as_json_text: bool,
        key_pick: int,
    ) -> None:
        """Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 2: 作用域外的行逐元素不变

        **Validates: Requirements 1.2, 1.4**

        (b) 维。一份载荷承三类行（交错，见 :func:`_b_payload`），`row_keys` 只声明 `_TABLE_IN`：

        * `_SEG_IN` 的行在作用域内 —— `in_deleted` 那几条**真被删**（正例，非空由生成器保证）；
        * `_SEG_SIBLING` 的行有 spec、`section_of` 判得出，但其 table 不在 `row_keys` ⇒ 作用域外；
        * `_SEG_UNENUMERATED` 的行**没有** spec ⇒ reader 一行都枚举不到 ⇒ 只能靠按位置摘保住。

        分区字段名取自 :func:`declared_section_fields`（声明），不是字面量。
        """
        identity_key = IDENTITY_KEYS[key_pick % len(IDENTITY_KEYS)]
        payload, outside = _b_payload(
            identity_key=identity_key,
            in_updated=in_updated,
            in_deleted=in_deleted,
            siblings=siblings,
            unenumerated=unenumerated,
        )
        rows_before = list(payload)
        given_payload: Any = json.dumps(payload, ensure_ascii=False) if as_json_text else payload
        row_keys = {_TABLE_IN: tuple(in_updated)}
        for reader_label, reader in _b_readers(identity_key):
            where = f"{reader_label} / (b) 维 / 键名 {identity_key!r} / text={as_json_text}"
            pruned, deleted = prune_undeclared_rows(
                given_payload, row_keys=row_keys, reader=reader
            )
            assert set(deleted) == set(in_deleted) and deleted, (
                f"{where}：作用域内应删 {sorted(in_deleted)}，实删 {list(deleted)} —— "
                "同分区一行都没删时「作用域外不变」恒真，判据失去区分力"
            )
            _assert_property_2(
                label=where,
                payload_before=given_payload,
                rows_before=rows_before,
                outside=outside,
                outside_tables=frozenset({_TABLE_OUT}),
                pruned=pruned,
                deleted=deleted,
                deltas=_plan_for(
                    row_keys=row_keys, payload=given_payload, reader=reader
                ).deltas,
                identity_key=identity_key,
                by_object=not as_json_text,
            )
            _LIVE_CASES.append(("b", len(deleted), len(outside)))

    @pytest.mark.parametrize("reader_index", (0, 1))
    def test_declaring_the_sibling_table_really_deletes_its_rows(self, reader_index: int) -> None:
        """(b) 维的**反例**：把兄弟分区那张表也声明进 `row_keys`（空元组）⇒ 它的行确实会被删。

        这条证明「作用域外不变」不是因为那些行天生删不掉 —— 删得掉，只是本次没声明它。
        同时它就是 Requirement 1.3 空值二分的「在键集合但值为空 ⇒ 清空」那一侧在多分区下的形态。
        """
        identity_key = IDENTITY_KEYS[0]
        payload, outside = _b_payload(
            identity_key=identity_key,
            in_updated=["upd-a1"],
            in_deleted=["del-z9"],
            siblings=["sib-s1", "sib-s2"],
            unenumerated=["unenum-u1"],
        )
        reader_label, reader = _b_readers(identity_key)[reader_index]
        _kept, deleted = prune_undeclared_rows(
            payload, row_keys={_TABLE_IN: ("upd-a1",), _TABLE_OUT: ()}, reader=reader
        )
        assert set(deleted) == {"del-z9", "sib-s1", "sib-s2"}, (
            f"{reader_label}：两表都声明后应连兄弟分区一起删，实删 {list(deleted)}"
        )
        # 🔴 `_SEG_UNENUMERATED` 那条**即使两表都声明也删不掉** —— 它压根没被 reader 枚举到。
        #    这正是它只能靠「按位置摘」保住、而 M5 能把它弄丢的原因。
        assert "unenum-u1" not in deleted and outside, (
            "未被任何 spec 覆盖的分区值竟被删了 —— 引擎的分区过滤口径变了，(b) 维第二类须重建"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 反空转判据（定义在最后 ⇒ 上面两维的 property 已跑过）
# ═══════════════════════════════════════════════════════════════════════════


class TestJudgesAreNotVacuous:
    """两维都真跑过，且每一维都伴随「作用域内确有删除」（否则「不变」恒真）。"""

    def test_both_dimensions_were_exercised_with_live_deletions(self) -> None:
        if not _LIVE_CASES:
            pytest.skip("本次选择未执行两维 property（如 -k 定向）⇒ 累计器为空，本判据无从成立")
        dims = {dim for dim, _deleted, _outside in _LIVE_CASES}
        assert dims == {"a", "b"}, (
            f"实际跑过的维度 {sorted(dims)} != 两维 ['a', 'b'] —— Property 2 的 (a)/(b) 必须都成立"
        )
        assert all(deleted > 0 for _dim, deleted, _outside in _LIVE_CASES), (
            f"某一格「作用域内」一行都没删：{_LIVE_CASES} —— 那一格的「作用域外不变」是恒真式"
        )
        assert all(outside > 0 for _dim, _deleted, outside in _LIVE_CASES), (
            f"某一格「作用域外」一行都没有：{_LIVE_CASES} —— 判据在空集上恒真"
        )


class TestSectionFieldComesFromDeclaration:
    """🔴 分区字段名取自**声明**，本文件里没有任何分区字段名字面量（含 `"section"`）。"""

    def test_section_fields_are_live_computed(self) -> None:
        assert _SECTION_FIELDS == declared_section_fields() and _SECTION_FIELDS, (
            f"两次现算不一致或为空（实得 {list(_SECTION_FIELDS)}）—— 取值域不稳定 / 索引失效"
        )
        assert not set(_SECTION_FIELDS) & set(IDENTITY_KEYS), (
            f"分区字段名 {list(_SECTION_FIELDS)} 与行身份键 {list(IDENTITY_KEYS)} 相撞"
        )
        assert _section_field() in _SECTION_FIELDS

    def test_no_section_field_name_appears_as_a_literal_in_this_file(self) -> None:
        """判据用 **AST 字符串常量**而不是文本匹配（平台铁律㉖）。

        文本匹配在这里必假阳：`section_field` / `section_of` / `_SECTION_FIELDS` 这些标识符里都
        含子串 `section`，而现算取值域里恰好有一个就叫 `section` ⇒ 只数子串会把每个标识符都算成
        「硬编码了字段名」。AST 只看 `ast.Constant[str]`，标识符不在其中。
        """
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        constants = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        hits = sorted(set(_SECTION_FIELDS) & constants)
        assert not hits, (
            f"本文件把分区字段名写成了字符串常量 {hits} —— 字段名必须取自 "
            "`RowTableSheetSpec.row_section_field` 的声明（design § Overview 已登记：合同清单里的 "
            '`"row_section_field": "section"` 是描述性元数据不是真源，5 处里 4 处与功能声明不符）'
        )
        # 变异对照：同一扫描器对**真有**字面量的输入必须命中（否则它是「什么都没扫到」）。
        probe = ast.parse(f"x = {_SECTION_FIELDS[0]!r}\n")
        assert {
            n.value
            for n in ast.walk(probe)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        } & set(_SECTION_FIELDS), "扫描器对已知含字面量的样本都不命中 ⇒ 口径失效"


class TestNoneCollapseIsUnreachable:
    """🔴 「把未声明分区值归一成 `None`」在生产接线下**不可达** —— 结构性依据，不是散文。

    `in_scope` 只有在存在 `section is None` 的 scope 时才有「无分区」桶。本类逐条现算证明：
    `section_field` 非空时 `_declared_scopes` **永不**产出 `None`；它在分区值为空时产出的 `""`
    是**退化声明**，被 `prune_undeclared_rows` 当场拒收 ⇒ 两条路都到不了「无分区」桶。
    ⇒ 任务书第三组变异的可达同型是「归一进**某个已声明**桶」，见伴生文件的 M3。
    """

    def test_declared_scopes_never_yields_a_none_section_when_field_is_set(self) -> None:
        field = _section_field()
        specs = (
            _p2_spec(table_key=_TABLE_IN, section_value=_SEG_IN, identity_key=IDENTITY_KEYS[0]),
            replace(
                _p2_spec(
                    table_key=_TABLE_OUT, section_value=_SEG_IN, identity_key=IDENTITY_KEYS[0]
                ),
                row_section_value="",
            ),
        )
        # 🔴 `_declared_scopes` 按 `(table_key, 分区 or "")` 排序 ⇒ 判据按**表**取值，不按位置
        scopes = dict(_declared_scopes(specs, section_field=field))
        assert scopes == {_TABLE_IN: _SEG_IN, _TABLE_OUT: ""}, (
            f"现算 scopes={scopes} —— 期望「分区值为空 ⇒ `''`、非空 ⇒ 原值」，两者都不是 None"
        )
        assert None not in scopes.values(), scopes
        # 空 section_field 才得 None，而那时 `section_of` 恒 None ⇒ 不存在「未声明的分区值」
        plain = _declared_scopes(
            (_spec(identity_key=IDENTITY_KEYS[0]),), section_field=""
        )
        assert [s for _t, s in plain] == [None], plain

    def test_the_degenerate_empty_section_is_rejected_on_both_gates(self) -> None:
        """`""` 分区值在 prune 与 `_in_scope_by_section` 两处都当场抛（逐字对齐的同判据）。"""
        field = _section_field()
        spec = _p2_spec(
            table_key=_TABLE_IN, section_value=_SEG_IN, identity_key=IDENTITY_KEYS[0]
        )
        reader = EngineRowReader(
            item_id=ITEM,
            specs=(spec,),
            section_field=field,
            declared_scopes=((_TABLE_IN, ""),),
        )
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            prune_undeclared_rows([], row_keys={_TABLE_IN: ()}, reader=reader)
        assert "退化声明" in str(excinfo.value), str(excinfo.value)[:200]


# ── 伴生文件指针 ──────────────────────────────────────────────────────────────
# **变异反证（M1~M4）与「未污染生产模块」判据在 `test_aos_property_out_of_scope_mutants.py`**。
# 🔴 为什么切出去：本文件写到第 4 节即 500 行，§5 变异反证实测 328 行 ⇒ 合计 828 已越 `.py` 门禁
#    800（`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit 与 CI 的
#    `file-size-guard` 同源）。域内同样处置的测试侧先例：`test_aos_property_unreadable_payload.py`。
#    伴生文件**复用**本文件的 `_assert_property_2` / `_b_payload` / `_b_readers` /
#    `_identity_seq` / `_p2_spec` / `_section_field`，不另造判据也不另造场景。
