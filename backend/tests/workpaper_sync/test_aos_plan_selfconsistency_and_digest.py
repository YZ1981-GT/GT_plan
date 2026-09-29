"""Property 4（计划内部自洽）与 Property 6（digest 顺序无关且内容敏感）——**主体**。

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 3.2 + Task 3.3）
Requirements 1.7 / 3.3 · design § Correctness Properties / § prework 合并记录

| Property | 归属任务 | design 原文的断言面 | 本文件 |
| --- | --- | --- | --- |
| **Property 4: Overwrite_Plan 内部自洽** | 3.2 | ① 四个计数 == 对应清单长度 ② `rows_added`/`rows_deleted`/`rows_updated` **两两**不相交 | §3 |
| **Property 6: plan_digest 顺序无关且内容敏感** | 3.3 | ① 置换任意清单元素顺序 ⇒ digest 不变 ② 改任一行身份或任一计数 ⇒ digest 必变 | §3 |

两条合一份的理由（任务书的原话）：都测 `adopt_overwrite_plan.py` 的**数据模型层**
（`ItemOverwriteDelta` / `OverwritePlan` / `OverwritePlan.digest`，Task 3.1 交付），共享同一个
场景建造器 —— 建两份 `OverwritePlan` 生成器就是第二真源。

═══ 🔴 Property 4 的面 ② 在「只造合法计划」的生成器上**恒真** ═══

`ItemOverwriteDelta._validate_row_lists` 已把「三清单相交」钉成构造期当场抛 ⇒ 相交的计划
**造不出来** ⇒ 只喂合法计划时面 ② 永远成立，而那不是「判据强」是「判据没被考」。故本文件把
面 ② 拆成**两个方向**，缺一即假绿：

* **正向**（§3 property）：凡能构造出的计划，三清单两两不相交；
* **门是活的**（§4 例子级）：凡相交的输入，构造期必抛 `OverwritePlanShapeError` ——
  这才是面 ② 真正的承重点。

而「判据本身有区分力」由伴生文件的 M2 / M3 两组变异兑现：把那道门摘掉 / 只留第一对之后，
**相交的计划真的造得出来**，正向判据必须当场打红（否则它只是在复述构造器的既成事实）。

═══ 🔴 落点为何是新建文件 ═══

`.py` 门禁上限 **800**（`backend/scripts/check/check_file_size.py` 的 `LIMITS`；口径
`splitlines()`）。现状：`adopt_overwrite_plan.py` 已 **781** 行（只剩 19 行余量）、Task 4.3 的
`test_aos_property_plan_rowsets.py` 已 **753** 行（余量 47 行装不下两条 property + 九组变异）
⇒ 新建。变异反证再切一份伴生 `test_aos_plan_digest_mutants.py`（域内先例：
`test_aos_property_out_of_scope_mutants.py` 由 `test_aos_property_out_of_scope_rows.py` 切出；
`test_aos_property_unreadable_payload.py` 由 `test_aos_property_row_identity.py` 切出）。

🔴 **伴生文件 import 本文件必须用顶层模块名**（`from test_aos_plan_selfconsistency_and_digest
import …`）：该目录无 `__init__.py`，pytest 以 `prepend` 模式把它塞进 `sys.path`；写成
`tests.workpaper_sync.…` 会拿到**第二个**模块实例，`_P46_MUTANT_REDS` 与 `_SAW` 两个模块级
累计器就此分家 —— §6 的收口判据会读到空 dict，而伴生文件的红一次都不算数。

🔴 **不复用别的 property 的累计器**：`_MUTANT_REDS`（Task 4.3）与 `_P2_MUTANT_REDS`（Task 4.4）
的收口判据都是「组名集合恰等于本文件登记的组」⇒ 塞进本轮组名会让**它们**打红。故另立
`_P46_MUTANT_REDS`；判据函数亦另立，与 `_assert_property_1` / `_assert_property_2` 互不调用。

═══ 建造器：身份字母表复用，计划建造器新造 ═══

`_IDENTITY_ALPHABET` 从 `test_aos_property_row_identity` import（含 `/` 与中文 ⇒ 顺带压到
`_canonical_json` 的 `ensure_ascii=False` 那一档）。计划建造器**必须新造** —— 域内既有建造器
产出的是 `(spec, reader, payload)` 三件套（prune 侧），本文件被测面上根本没有载荷与 reader。
"""
from __future__ import annotations

import dataclasses
import random
from itertools import combinations
from typing import Any, Final, Iterable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.adopt_overwrite_plan import (
    _DISJOINT_FIELDS,
    _ROW_LIST_FIELDS,
    DIGEST_FORMAT,
    ItemOverwriteDelta,
    OverwritePlan,
    OverwritePlanShapeError,
    SkipReason,
)

# 🔴 身份字母表的**唯一**来源（禁抄第二份；顶层模块名形态见 docstring）。
from test_aos_property_row_identity import _IDENTITY_ALPHABET  # noqa: E402

# ── 1. 建造器与覆盖累计器 ─────────────────────────────────────────────────────────────

#: 合成 store item 身份前缀。刻意带 `AOS46`，万一漏进任何输出都能被搜到。
ITEM_PREFIX: Final[str] = "AOS46-item"

#: 合成 declared_table 名池。**≥2 个是刻意的** —— 两个 Mapping 的「键序」维度要有东西可置换。
TABLES: Final[tuple[str, ...]] = ("aos46_t1", "aos46_t2", "aos46_t3")

#: 身份变异用的后缀 / 新身份标记。`~` **不在** `_IDENTITY_ALPHABET` 里 ⇒ 改出来的身份一定是
#: 新串、一定不会与三清单里任何既有身份相撞（否则会撞上构造器的「两两不相交」而抛，
#: 那就不是在测 digest 而是在测构造器了）。
_FRESH_MARK: Final[str] = "~"

#: 生成器与判据**真的走到过**的形态。§5 反空转判据**读**它 —— 只写不读的累计器是假绿的标准形态
#: （Task 4.4 §6 的收口就是补这个）。
_SAW: dict[str, int] = {}


def _saw(key: str) -> None:
    _SAW[key] = _SAW.get(key, 0) + 1


#: §5 逐条核对的**结构性保证**清单：建造器按构造就该产出这些形态，一条不见即生成器退化。
_REQUIRED_COVERAGE: Final[tuple[str, ...]] = (
    "nonempty_rows_added",
    "nonempty_rows_deleted",
    "nonempty_rows_updated",
    "nonempty_rows_ghost_dropped",
    "list_with_two_or_more",
    "three_lists_all_nonempty",
    "plan_with_two_or_more_deltas",
    "delta_with_skip_reason",
    "mapping_with_two_or_more_keys",
    "order_changed_lists",
    "order_changed_deltas",
    "order_changed_mapping_keys",
    "content_variant_identity",
    "content_variant_count_up",
    "content_variant_count_down",
    "content_variant_stored_count",
)

#: 允许出现但**不保证**出现的形态（取值随机而非结构保证）。§5 用它堵住「f-string 拼出来的
#: 累计器键名打错字」—— 打错的键既不在必需清单也不在本清单，判据当场打红。
_OPTIONAL_COVERAGE: Final[tuple[str, ...]] = (
    "delta_with_row_section",
    "non_ascii_identity",
)


def fixed_plan(
    *,
    delta_cls: Any = ItemOverwriteDelta,
    plan_cls: Any = OverwritePlan,
    added: tuple[str, ...] = ("r-a1", "r-a2"),
    deleted: tuple[str, ...] = ("r-d1", "r-d2"),
    updated: tuple[str, ...] = ("r-u1", "r-u2"),
    ghost: tuple[str, ...] = ("r-a1", "r-a2"),
    store: dict[str, int] | None = None,
    substrate: dict[str, int] | None = None,
    with_skipped: bool = True,
) -> Any:
    """确定性最小**非平凡**计划 —— 变异反证共用（`@given` 生成器只给 §3 的 property 用）。

    「非平凡」逐条兑现：**四个清单都非空且长度都 ≥2**（面 ① 不落在 `0 == 0` 上，且每个清单的
    元素序都真的可置换 —— 长度 1 的清单洗不动，M4 那组变异在它上面打不出红）· 三清单同时非空
    （面 ② 有候选可查）· ≥2 个 delta（deltas 维度可置换）· 两个 Mapping 各 ≥2 键（键序维度可
    置换）· 含一条被跳过的 delta（`skipped_reason` 也进 digest）。

    `delta_cls` / `plan_cls` 可换成伴生文件的**变异类**：那两个类是在 `globals` 副本里
    `exec` 出来的独立对象，生产模块一字不改。
    """
    deltas = [
        delta_cls(
            item_id=f"{ITEM_PREFIX}-0",
            table_key=TABLES[0],
            rows_added=added,
            rows_deleted=deleted,
            rows_updated=updated,
            rows_ghost_dropped=ghost,
        )
    ]
    if with_skipped:
        deltas.append(
            delta_cls(
                item_id=f"{ITEM_PREFIX}-1",
                table_key=None,
                skipped_reason=SkipReason.item_blind,
            )
        )
    return plan_cls(
        deltas=tuple(deltas),
        store_rows_by_table=dict(store if store is not None else {TABLES[0]: 5, TABLES[1]: 0}),
        substrate_rows_by_table=dict(
            substrate if substrate is not None else {TABLES[0]: 7, TABLES[1]: 2}
        ),
    )

_IDENTITY = st.text(alphabet=_IDENTITY_ALPHABET, min_size=1, max_size=8)

#: 分区取值域。`""` 会被 `_normalise_row_section` 归一成 `None`（Task 3.1 明写）⇒ 刻意在场，
#: 让「两种写法算出同一个 digest」这条稳定性承诺被顺带压到。
_SECTIONS: Final[tuple[str | None, ...]] = (None, "", "s1", "s2")


@st.composite
def _plans(
    draw: Any, *, delta_cls: Any = ItemOverwriteDelta, plan_cls: Any = OverwritePlan
) -> Any:
    """`OverwritePlan` 生成器 —— 本文件两条 property **共享**的唯一场景建造器。

    🔴 **结构性保证而不是 `assume`**：`max_examples=5`（用户明确要求，禁默认 100）下靠概率凑
    非平凡形态会大面积空转 ⇒ 第 0 条 delta 恒「富」（三清单各 ≥2 且幽灵非空）、第 1 条 delta
    恒「被跳过」、Mapping 恒 ≥2 键。随机性留给身份取值 / 清单长度 / 额外 delta 的形态。
    """
    pool = draw(st.lists(_IDENTITY, min_size=10, max_size=16, unique=True))
    n_add = draw(st.integers(min_value=2, max_value=4))
    n_del = draw(st.integers(min_value=2, max_value=3))
    n_upd = draw(st.integers(min_value=2, max_value=3))
    added = tuple(pool[:n_add])
    deleted = tuple(pool[n_add : n_add + n_del])
    updated = tuple(pool[n_add + n_del : n_add + n_del + n_upd])
    ghost = added[: draw(st.integers(min_value=1, max_value=n_add))]

    deltas: list[Any] = [
        delta_cls(
            item_id=f"{ITEM_PREFIX}-0",
            table_key=TABLES[0],
            row_section=draw(st.sampled_from(_SECTIONS)),
            rows_added=added,
            rows_deleted=deleted,
            rows_updated=updated,
            rows_ghost_dropped=ghost,
        ),
        delta_cls(
            item_id=f"{ITEM_PREFIX}-1",
            table_key=None,
            skipped_reason=draw(st.sampled_from(tuple(SkipReason))),
            rows_added=tuple(pool[-1:]),
        ),
    ]
    for index, kind in enumerate(
        draw(st.lists(st.sampled_from(("plain", "empty")), min_size=0, max_size=2)), start=2
    ):
        deltas.append(
            delta_cls(
                item_id=f"{ITEM_PREFIX}-{index}",
                table_key=draw(st.sampled_from(TABLES)),
                row_section=draw(st.sampled_from(_SECTIONS)),
                rows_updated=tuple(pool[-3:-1]) if kind == "plain" else (),
            )
        )

    keys = list(TABLES[: draw(st.integers(min_value=2, max_value=len(TABLES)))])
    store = {key: draw(st.integers(min_value=0, max_value=40)) for key in keys}
    substrate = {key: draw(st.integers(min_value=0, max_value=40)) for key in keys}

    for name in _ROW_LIST_FIELDS:
        rows = getattr(deltas[0], name)
        if rows:
            _saw(f"nonempty_{name}")
        if len(rows) >= 2:
            _saw("list_with_two_or_more")
    if added and deleted and updated:
        _saw("three_lists_all_nonempty")
    if len(deltas) >= 2:
        _saw("plan_with_two_or_more_deltas")
    if any(delta.skipped_reason is not None for delta in deltas):
        _saw("delta_with_skip_reason")
    if any(delta.row_section is not None for delta in deltas):
        _saw("delta_with_row_section")
    if len(keys) >= 2:
        _saw("mapping_with_two_or_more_keys")
    if any(not identity.isascii() for identity in added + deleted + updated):
        _saw("non_ascii_identity")

    return plan_cls(
        deltas=tuple(deltas), store_rows_by_table=store, substrate_rows_by_table=substrate
    )

# ── 2. 判据（本文件是 Property 4 / Property 6 的**唯一**实现；变异体喂进来必须打红） ─────────────


def _assert_property_4(plan: Any, *, label: str = "") -> None:
    """Property 4 的唯一判据 —— design 原文的**两个**断言面逐个在场。

    面 ①「四个计数分别等于其对应身份清单的长度」：字段域取自生产模块 `_ROW_LIST_FIELDS`
    （四个全查，不是抽一个查；伴生文件的 M1 按四个字段逐个变异 ⇒ 少查一个就有一个字段的
    「计数与清单脱钩」永远看不见）。
    面 ②「三个集合两两不相交」：对子由生产模块 `_DISJOINT_FIELDS` 现算 `combinations(…, 2)`
    得出 —— 写死「(added, deleted)」一对会让另两对失守（伴生文件 M3 直证）。

    🔴 `rows_ghost_dropped` **刻意不进面 ②**：Task 3.1 把它排除在 `_DISJOINT_FIELDS` 之外是有
    裁定的（连带约束是 `ghost ⊆ rows_added`，归 Property 3）。此处照抄生产域而不是自己列清单，
    正是为了「哪天那个域变了，本判据跟着变」。
    """
    assert plan.deltas, f"{label}：空计划 ⇒ 两个面都落在空集上恒真（本判据无从成立）"
    for delta in plan.deltas:
        for name in _ROW_LIST_FIELDS:
            rows = getattr(delta, name)
            count = getattr(delta, f"{name}_count")
            assert count == len(rows), (
                f"{label}：{delta.item_id}.{name}_count = {count} 而清单长度 {len(rows)}"
                f"（{list(rows)}）—— 计数与身份清单脱钩。Requirement 1.7 要的是「四个计数**与**"
                "对应身份清单」，两者不等时弹窗上那个「将删除 N 行」就是假数字"
            )
        for left, right in combinations(_DISJOINT_FIELDS, 2):
            overlap = sorted(set(getattr(delta, left)) & set(getattr(delta, right)))
            assert not overlap, (
                f"{label}：{delta.item_id} 的 {left} 与 {right} 相交于 {overlap} —— 一个行身份"
                "只能落在追加 / 删除 / 更新之一（三者按「两侧各有无」互斥定义），相交即分类有 bug，"
                "而「同一行既报追加又报删除」会让对账（Requirement 3.8）永远对不上"
            )


def _shuffled(seq: Iterable[Any], rng: random.Random) -> list[Any]:
    """打乱；若恰好洗回原序且长度 >1 则改为倒序 ⇒ **保证真的换了序**（否则判据在恒等上恒真）。"""
    original = list(seq)
    out = list(original)
    rng.shuffle(out)
    if len(out) > 1 and out == original:
        out.reverse()
    return out


def _reordered_plan(plan: Any, *, rng: random.Random) -> tuple[Any, tuple[str, ...]]:
    """把计划的**三个**顺序维度全部换一遍：四个清单的元素序 · deltas 的排列 · 两个 Mapping 的键序。

    返回 `(孪生计划, 真的换了序的维度名)`。第二个返回值是反空转用的 —— 一个维度都没换动时
    「digest 不变」是恒等变换上的废话。
    """
    changed: list[str] = []
    rebuilt: list[Any] = []
    for delta in plan.deltas:
        overrides: dict[str, Any] = {}
        for name in _ROW_LIST_FIELDS:
            rows = getattr(delta, name)
            shuffled = tuple(_shuffled(rows, rng))
            if shuffled != rows:
                changed.append(f"lists:{delta.item_id}.{name}")
            overrides[name] = shuffled
        rebuilt.append(dataclasses.replace(delta, **overrides))
    ordered = _shuffled(rebuilt, rng)
    if [d.key for d in ordered] != [d.key for d in rebuilt]:
        changed.append("deltas")
    remapped: dict[str, dict[str, int]] = {}
    for field_name in ("store_rows_by_table", "substrate_rows_by_table"):
        source = getattr(plan, field_name)
        remapped[field_name] = {key: source[key] for key in _shuffled(list(source), rng)}
        if list(remapped[field_name]) != list(source):
            changed.append(f"mapping_keys:{field_name}")
    twin = dataclasses.replace(plan, deltas=tuple(ordered), **remapped)
    return twin, tuple(changed)

def _assert_property_6_order_free(plan: Any, *, rng: random.Random, label: str = "") -> None:
    """Property 6 面 ①「置换任意清单的元素顺序后 plan_digest 不变」的唯一判据。"""
    twin, changed = _reordered_plan(plan, rng=rng)
    assert changed, (
        f"{label}：三个顺序维度一个都没真的换序 ⇒ 本判据落在恒等变换上恒真（空转）。"
        "建造器的结构性保证（清单 ≥2 元素 / ≥2 个 delta / Mapping ≥2 键）已失效"
    )
    for dimension in ("lists", "deltas", "mapping_keys"):
        if any(item.split(":")[0] == dimension for item in changed):
            _saw(f"order_changed_{dimension}")
    assert twin.digest == plan.digest, (
        f"{label}：只换了顺序（{list(changed)}）digest 就变了 —— 清单元素的顺序是枚举顺序的"
        "副产物、不是语义。Requirement 3.4 的 409 会对着自己误报：用户拿到 dry_run 的 digest 后"
        "什么都没改，回传却被判过期"
    )


def _with_rows(plan: Any, *, index: int, name: str, rows: tuple[str, ...]) -> Any:
    deltas = list(plan.deltas)
    deltas[index] = dataclasses.replace(deltas[index], **{name: rows})
    return dataclasses.replace(plan, deltas=tuple(deltas))


def _content_variants(plan: Any) -> list[tuple[str, Any, str]]:
    """内容敏感面的变体清单：`(改了什么, 变体计划, 覆盖面标记)`。

    design 面 ② 的两个被改对象逐个在场：**任一行身份**（改一个字符）与**任一计数**
    （两个方向：追加一条 ⇒ 计数 +1、摘掉一条 ⇒ 计数 −1；另加两个 Mapping 里**存字段**的
    逐表行数 —— 那是计划里唯一「存起来的计数」，其余四个都是 `len()` 派生）。

    🔴 新身份一律带 `_FRESH_MARK`（`~` 不在 `_IDENTITY_ALPHABET` 内）⇒ 绝不会与三清单里
    既有身份相撞。撞了就会先触发构造器的「两两不相交」而抛，那时测的是构造器不是 digest。
    """
    out: list[tuple[str, Any, str]] = []
    for index, delta in enumerate(plan.deltas):
        for name in _ROW_LIST_FIELDS:
            rows = getattr(delta, name)
            if not rows:
                continue
            where = f"{delta.item_id}.{name}"
            out.append((
                f"identity/{where}",
                _with_rows(plan, index=index, name=name, rows=(rows[0] + _FRESH_MARK,) + rows[1:]),
                "content_variant_identity",
            ))
            out.append((
                f"count+1/{where}",
                _with_rows(plan, index=index, name=name, rows=rows + (f"{_FRESH_MARK}new",)),
                "content_variant_count_up",
            ))
            out.append((
                f"count-1/{where}",
                _with_rows(plan, index=index, name=name, rows=rows[1:]),
                "content_variant_count_down",
            ))
    for field_name in ("store_rows_by_table", "substrate_rows_by_table"):
        mapping = dict(getattr(plan, field_name))
        key = sorted(mapping)[0]
        mapping[key] = mapping[key] + 1
        out.append((
            f"count/{field_name}[{key}]",
            dataclasses.replace(plan, **{field_name: mapping}),
            "content_variant_stored_count",
        ))
    return out


def _assert_property_6_content_sensitive(plan: Any, *, label: str = "") -> None:
    """Property 6 面 ②「改任一行身份或任一计数后 plan_digest 必定改变」的唯一判据。"""
    base = plan.digest
    variants = _content_variants(plan)
    assert variants, f"{label}：一个内容变体都没造出来 ⇒ 面 ② 空转"
    for what, variant, kind in variants:
        _saw(kind)
        assert variant.digest != base, (
            f"{label}：改了 {what}，plan_digest 却仍是 {base} —— 摘要漏算了这一项。危害是"
            "「内容变了摘要不变」：Requirement 3.4 的 409 放行一个已过期的计划，用户确认的与"
            "实际执行的不是同一件事"
        )


def _assert_no_concatenation_ambiguity(
    *, delta_cls: Any = ItemOverwriteDelta, plan_cls: Any = OverwritePlan, label: str = ""
) -> None:
    """三种边界不得被拍平成一串（元素边界 / 字段边界 / 表边界）。

    三者都是「摘要把结构拼成一个字符串」这类实现会踩的：元素边界 = 同一清单内的切分方式
    （`["a","bc"]` vs `["ab","c"]`）· 字段边界 = 同一批身份在追加与删除之间互换 · 表边界 =
    逐表行数分布不同而总和相同（若 digest 只吃派生总数就会撞）。
    """
    def plan(**kwargs: Any) -> Any:
        return fixed_plan(delta_cls=delta_cls, plan_cls=plan_cls, **kwargs)

    assert plan(added=("a", "bc"), ghost=()).digest != plan(added=("ab", "c"), ghost=()).digest, (
        f"{label}：`['a','bc']` 与 `['ab','c']` 算出了同一个 digest —— 清单被拼成一串而没有"
        "分隔符。危害：两份**行集不同**的计划共用一个 digest ⇒ Requirement 3.4 的 409 放行错的那份"
    )
    swapped = (
        plan(added=("a", "b"), deleted=("c", "d"), ghost=()).digest,
        plan(added=("c", "d"), deleted=("a", "b"), ghost=()).digest,
    )
    assert swapped[0] != swapped[1], (
        f"{label}：把同一批身份在「追加」与「删除」之间互换后 digest 没变 —— 字段边界被抹平了。"
        "这是本 spec 唯一破坏性路径上最严重的一种混淆：删的那侧与加的那侧对调而摘要无感"
    )
    left = plan(store={TABLES[0]: 1, TABLES[1]: 22})
    right = plan(store={TABLES[0]: 22, TABLES[1]: 1})
    assert left.store_row_count == right.store_row_count == 23, f"{label}：前提已变，两例总数本该相等"
    assert left.digest != right.digest, (
        f"{label}：逐表行数分布不同而 digest 相同 —— 摘要只吃了派生总数。`store_rows_by_table` 是"
        "原始事实、总数才是它的函数（Task 3.1 的「派生量一律不存字段」正是这个方向）"
    )

# ── 3. Property 测试（一条 property 一个测试函数） ────────────────────────────────────────


class TestPropertyFourPlanIsInternallyConsistent:
    """**Property 4: Overwrite_Plan 内部自洽**

    **Validates: Requirements 1.7**
    """

    @settings(max_examples=5, deadline=None)
    @given(plan=_plans())
    def test_property4_counts_match_lists_and_three_sets_are_disjoint(self, plan: Any) -> None:
        # Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 4:
        # 四个计数分别等于其对应身份清单的长度，且 rows_added / rows_deleted / rows_updated
        # 三个集合两两不相交。
        _assert_property_4(plan, label="P4")


class TestPropertySixDigestIsOrderFreeAndContentSensitive:
    """**Property 6: plan_digest 顺序无关且内容敏感**

    **Validates: Requirements 3.3**

    两半写在一个函数里（design § prework 合并记录：「3.3 两半 → P6 —— 顺序无关与内容敏感是
    同一条 property 的两个断言」）。拆成两个测试函数会让「摘要把整个计划都忽略掉」这种实现
    在前一半上通过、后一半上失败，读起来像两条互不相干的 property。
    """

    @settings(max_examples=5, deadline=None)
    @given(plan=_plans(), seed=st.integers(min_value=0, max_value=2**31 - 1))
    def test_property6_digest_is_order_free_and_content_sensitive(
        self, plan: Any, seed: int
    ) -> None:
        # Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 6:
        # 随机置换其任意清单的元素顺序后 plan_digest 不变；而修改其中任一行身份或任一计数后
        # plan_digest 必定改变。
        _assert_property_6_order_free(plan, rng=random.Random(seed), label="P6/order")
        _assert_property_6_content_sensitive(plan, label="P6/content")


# ── 4. 例子级锚点（property 之外的承重点，缺了 property 就是在复述构造器的既成事实） ──────────


class TestDisjointGateIsLive:
    """🔴 Property 4 面 ② 的真正承重点：**相交的计划造不出来**。

    没有本类，面 ② 在「只造合法计划」的生成器上恒真（模块 docstring 已展开这条）。三对逐个验，
    对子由 `_DISJOINT_FIELDS` 现算得出 —— 写死一对会漏掉另两对。
    """

    @pytest.mark.parametrize("pair", list(combinations(_DISJOINT_FIELDS, 2)))
    def test_overlapping_lists_are_rejected_at_construction(self, pair: tuple[str, str]) -> None:
        left, right = pair
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            ItemOverwriteDelta(
                item_id=f"{ITEM_PREFIX}-gate",
                table_key=TABLES[0],
                **{left: ("aos46-x", "aos46-y"), right: ("aos46-x",)},
            )
        message = str(excinfo.value)
        assert left in message and right in message and "aos46-x" in message, message
        # 变异对照：同一批身份**不相交**时必须构造成功 ⇒ 这道门不是「什么都拒」。
        clean = ItemOverwriteDelta(
            item_id=f"{ITEM_PREFIX}-gate",
            table_key=TABLES[0],
            **{left: ("aos46-x",), right: ("aos46-y",)},
        )
        assert getattr(clean, left) == ("aos46-x",) and getattr(clean, right) == ("aos46-y",)


class TestDigestHasNoConcatenationAmbiguity:
    """🔴 分隔符缺失的经典漏洞：`["a","bc"]` 与 `["ab","c"]` 不得同 digest。

    判据本体是 `_assert_no_concatenation_ambiguity`（**唯一**实现，伴生文件 M9 直接喂变异类进去
    要求它打红）；三种边界写在同一个判据里，因为「把结构拍平成一串」的实现会同时踩穿它们，
    拆三个测试函数反而读成三条互不相干的事。
    """

    def test_all_three_boundaries_are_preserved(self) -> None:
        _assert_no_concatenation_ambiguity(label="production")


class TestDigestShapeAndStability:
    """digest 的形态与稳定性 —— `plan_digest` 要能被 `models.is_digest` 收（Task 3.1 第 4 步）。"""

    def test_digest_is_64_lowercase_hex_and_stable_across_calls(self) -> None:
        plan = fixed_plan()
        first, second = plan.digest, plan.digest
        assert first == second and len(first) == 64
        assert first == first.lower() and all(char in "0123456789abcdef" for char in first)

    def test_two_independently_built_equal_plans_agree(self) -> None:
        """同内容、**不同对象**的两份计划 digest 相等 ⇒ 摘要吃的是内容不是对象身份。"""
        assert fixed_plan() is not fixed_plan()
        assert fixed_plan().digest == fixed_plan().digest

    def test_non_ascii_identities_participate_without_escaping_collapse(self) -> None:
        """🔴 `ensure_ascii=False` 那一档：中文身份必须参与摘要且不与其 ASCII 近邻相撞。

        真实树上的身份**确实**含中文与 `/`（`_IDENTITY_ALPHABET` 的注释：D4-22 的身份是自由
        文本指标名，现算含 `运输费用/营业收入`）⇒ ASCII-only 的判据测不到这一族。
        """
        chinese = fixed_plan(added=("运输费用/营业收入", "r-a2"), ghost=())
        ascii_twin = fixed_plan(added=("r-a1", "r-a2"), ghost=())
        assert chinese.digest != ascii_twin.digest and len(chinese.digest) == 64
        # 同一中文身份换一个字 ⇒ digest 必变（转义形态不得把不同中文压成同一串）
        other = fixed_plan(added=("运输费用/营业成本", "r-a2"), ghost=())
        assert chinese.digest != other.digest


# ── 5. 反空转判据（生成器真的走到过非平凡形态 + 判据域取自活的生产域） ──────────────────────────


class TestPropertiesDidNotRunVacuously:
    """🔴 `_SAW` 必须被**读**：只写不读的累计器是假绿的标准形态（Task 4.4 §6 的收口即为此补）。"""

    @staticmethod
    def _ensure_campaign_ran() -> None:
        """累计器为空就自跑一轮 —— 🔴 **不 skip**：`-k` 定向选择下 skip 等于判据在空 dict 上「通过」。"""
        if _SAW:
            return
        TestPropertyFourPlanIsInternallyConsistent().test_property4_counts_match_lists_and_three_sets_are_disjoint()
        TestPropertySixDigestIsOrderFreeAndContentSensitive().test_property6_digest_is_order_free_and_content_sensitive()

    def test_every_required_shape_was_exercised(self) -> None:
        """16 个结构性保证逐条现算核对 —— 一条为 0 即生成器或判据退化成了平凡输入。"""
        self._ensure_campaign_ran()
        missing = [key for key in _REQUIRED_COVERAGE if _SAW.get(key, 0) <= 0]
        assert not missing, (
            f"以下形态本次一次都没出现：{missing}（实得 {dict(sorted(_SAW.items()))}）—— "
            "两条 property 在这些维度上是空转的"
        )

    def test_accumulator_keys_are_closed_over_the_declared_domains(self) -> None:
        """累计器键集合 ⊆ 必需 ∪ 可选 ⇒ f-string 拼出来的键名打错字当场打红。"""
        self._ensure_campaign_ran()
        assert len(set(_REQUIRED_COVERAGE)) == len(_REQUIRED_COVERAGE), "必需清单有重复项"
        unknown = sorted(set(_SAW) - set(_REQUIRED_COVERAGE) - set(_OPTIONAL_COVERAGE))
        assert not unknown, (
            f"出现未登记的累计器键 {unknown} —— 要么是 `_saw(f\"…{{name}}\")` 拼错了字，"
            "要么是新增了形态却没进两张清单（那它就永远不会被反空转判据看见）"
        )

    def test_both_judge_field_domains_come_from_the_production_module(self) -> None:
        """面 ① 的四个字段与面 ② 的三个对子都取自生产模块的活域，不是本文件的字面量。"""
        assert len(_ROW_LIST_FIELDS) == 4, _ROW_LIST_FIELDS
        for name in _ROW_LIST_FIELDS:
            assert isinstance(
                getattr(ItemOverwriteDelta, f"{name}_count", None), property
            ), f"{name}_count 不是 property ⇒ 面 ① 的 getattr 取不到派生计数"
        assert set(_DISJOINT_FIELDS) < set(_ROW_LIST_FIELDS) and len(_DISJOINT_FIELDS) == 3
        # 🔴 ghost 刻意不在 disjoint 域内（连带约束 `ghost ⊆ rows_added` 归 Property 3 / Task 4.5）。
        assert "rows_ghost_dropped" not in _DISJOINT_FIELDS, (
            "`rows_ghost_dropped` 进了 disjoint 域 ⇒ `fixed_plan` 的默认 ghost（added 的子集）"
            "根本构造不出来，本文件全部例子级锚点会连带失效"
        )
        assert len(list(combinations(_DISJOINT_FIELDS, 2))) == 3

    def test_fresh_mark_cannot_collide_with_any_generated_identity(self) -> None:
        """身份变体靠 `~` 造新串。它若落进字母表，变体就可能撞上既有身份而触发构造器的抛。"""
        assert _FRESH_MARK and _FRESH_MARK not in _IDENTITY_ALPHABET
        variants = _content_variants(fixed_plan())
        assert variants and all(plan.digest for _what, plan, _kind in variants)

    def test_digest_format_carries_a_version_segment(self) -> None:
        """归一形态改了必须在版本号上可见（Task 3.1 第 3 步）—— 否则只是静默算出另一个合法 hex。"""
        assert DIGEST_FORMAT.startswith("aos-overwrite-plan/") and "/v" in DIGEST_FORMAT


# ── 6. 变异反证的累计器（**声明在此，伴生文件 import 后读写**） ────────────────────────────────
#
# 🔴 为什么不复用别处的累计器：`_MUTANT_REDS`（Task 4.3）与 `_P2_MUTANT_REDS`（Task 4.4）的收口
#    判据都是「组名集合恰等于本文件登记的组」⇒ 往里塞本轮组名会让**它们**打红。故另立一份。

#: 九组变异反证的组名（前三组贴 Property 4，后六组贴 Property 6）。
_MUTANT_GROUPS: Final[tuple[str, ...]] = (
    "M1_count_from_wrong_list",
    "M2_disjoint_gate_removed",
    "M3_only_first_pair_checked",
    "M4_list_sort_removed",
    "M5_delta_sort_neutralised",
    "M6_key_order_belts_removed",
    "M7_field_omitted_from_digest",
    "M8_stored_counts_omitted",
    "M9_list_joined_without_separator",
)

#: 逐组累计的「判据真的打红了几次」。伴生文件 §收口 **读**它。
_P46_MUTANT_REDS: dict[str, int] = {}


def _expect_red_p46(name: str, run: Any) -> AssertionError:
    """跑变异体，要求本文件的判据**打红**；红了就记一次。"""
    assert name in _MUTANT_GROUPS, f"未登记的变异组名 {name!r}"
    with pytest.raises(AssertionError) as excinfo:
        run()
    _P46_MUTANT_REDS[name] = _P46_MUTANT_REDS.get(name, 0) + 1
    return excinfo.value


# ── ── 变异反证落点（伴生文件 `test_aos_plan_digest_mutants.py`）────────────────────────── ──
#
# 本文件交付时已逼近 `.py` 门禁 **800**（`check_file_size.py` 的 `LIMITS`，pre-commit 与 CI 的
# `file-size-guard` 同源）⇒ 九组变异反证 + 收口 + 「未污染生产模块」判据抽伴生文件。
#
# 伴生文件**只 import 不另造**：`_assert_property_4` / `_assert_property_6_order_free` /
# `_assert_property_6_content_sensitive` / `_assert_no_concatenation_ambiguity` / `fixed_plan` /
# `_reordered_plan` / `_MUTANT_GROUPS` / `_P46_MUTANT_REDS` / `_expect_red_p46` / `TABLES` /
# `ITEM_PREFIX` 全部从本文件取（四个判据是 Property 4 / 6 的唯一实现，禁抄第二份）。
# 🔴 import 必须用**顶层模块名**（该目录无 `__init__.py`，pytest `prepend` 模式）—— 写成
# `tests.workpaper_sync.…` 会拿到第二个模块实例，两个累计器就分家。
