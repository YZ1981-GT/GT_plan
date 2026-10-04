"""Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 8: 不可枚举形态的载荷不被改动且被登记

spec: workpaper-sync-adopt-overwrite-and-refresh-source（Task 4.6）
Requirements 4.1 / 4.2 · design § Correctness Properties / §4.1b (3)(4)(7) · ADR-AOS-005 §5(4)

Property 8 原文：

> *For any* 含不可枚举形态 store item（dict 形态 / 纯文本固定项）的输入，该 item 的载荷在删除侧
> 逐字节不变，且该 item 必定以 `(item_id, reason)` 形式出现在 `skipped_items` 清单中。

═══ 🔴 为什么是伴生文件而不是追加进 `test_aos_property_ghost_gate.py` ═══

那个文件（Task 4.5 交付）现算 **800** 行（`check_file_size.py` 的 `splitlines()` 口径），而 `.py`
门禁上限正是 **800** ⇒ 再加一行即打红。它文末已留交接说明「Property 8 几乎一定要抽伴生文件」，
域内先例 = `test_aos_property_unreadable_payload.py` 由 `test_aos_property_row_identity.py` 切出。
本文件即该伴生文件；4.5 那侧的落点已改成指针注释，**断言语义一字未动**。

═══ 🔴 两个断言面（design 原文两句话，落在两个被测面上，别混写）═══

| 面 | 原文 | 被测面 | 本文件 |
| --- | --- | --- | --- |
| ① | 该 item 的载荷在**删除侧**逐字节不变 | `adopt_overwrite_plan.prune_undeclared_rows`（唯一会重写载荷的函数）+ `compute_overwrite_plan` 的计划侧 | §3 / §4 |
| ② | 必定以 `(item_id, reason)` 出现在 `skipped_items` | `OverwritePlan.skipped_items`（`ItemOverwriteDelta(skipped_reason=…)` 的**派生投影**） | §3 / §5 |

🔴 **面 ① 为什么必须分两级**（不是我把一条判据写成两条）：不可枚举 item **没有 reader** ⇒
`compute_overwrite_plan` 根本不把它路由进 `_deltas_for_item` ⇒ `prune_undeclared_rows` 对它**永不
被调用**。于是「逐字节不变」的兑现机制有两层，缺任一层都不成立：

* **计划级**（§3 面 ①-plan）：该 item 的 delta `table_key is None` / `rows_deleted == ()`
  （`ItemOverwriteDelta._validate_scope_and_skip` 已把「跳过却带删除清单」钉成当场抛），
  且 `compute_overwrite_plan` 不改调用方手里那份载荷对象；
* **执行级**（§3 面 ①-prune + §4）：真正重写载荷的 `prune_undeclared_rows` 在
  「本 item 一张 in-scope 表都没有」时**返回入参对象本身**；而万一它真被喂了不可枚举形态且表在
  作用域内，它 **fail visible** 而绝不返回一份被静默重写的载荷（§4 实测两种形态各抛
  `RowTableStorePayloadError`）。

🔴 **与 Property 2（Task 4.4）的分界**：P2 管「同一份载荷里作用域外的**行**逐元素不变」，
P8 管「整个**不可枚举 item** 一个字节都不碰 + 必被登记」。本文件不断言行级作用域语义。

═══ 🔴 「逐字节不变」验到什么粒度：`is` 相等，不是 `==` ═══

Task 4.1 的 `prune_undeclared_rows` docstring 明写「**零删除时第一个元素是入参对象本身**（`is`
相等）—— Requirement 1.2 的「保持原样不变」按字面兑现，连重序列化都不会发生」，依据是
ADR-AOS-003 附注实测：`json.dumps` 与前端 `JSON.stringify` 的分隔符差异会让真库 200 条大载荷里
**155** 条「重序列化即字符串漂移」。⇒ 若载荷是 JSON **文本**，`is` 相等意味着连解析-重序列化都
没发生；若已是解析后的序列，`is` 相等意味着连浅拷贝都没有。
`==` **不够**：§5 的 M2 变异体做的就是一次纯 round-trip（`json.loads(_canonical_json(payload))`）——
它产出的对象 `==` 入参但 `is` 不等 ⇒ **只用 `==` 的判据会把 M2 判绿**。两种形态各一例，见 §3。

═══ 🔴 「不可枚举形态」的清单是**现算**的，不是编的 ═══

design §4.1b (4) 的 D4 子形态表（dict store / list store / 纯文本固定项 / D4-7 专用块）其分类真源
= `store_mirror._mirror_row_stores` 逐字用的**provider 自己的常量**（那里正是按这些常量把它们从
rows 循环里排除的）。§1 照同一口径现算，再用生产 `diagnose_row_reader` 逐条问出 `SkipReason`
⇒ 本文件**不写**「5 / 1 / 8 / 2 / 16」这些数字作判据（tasks.md 顶部纪律：计数类禁写死）。

🔴 本轮现算结论（记录，判据一律现算）：D4 特殊形态 16 条**全部**落进 `item_blind` 桶 ——
因为 `SkipReason` 分的是「**为什么取不到行枚举器**」这一成因，而不是「载荷长什么样」：D4 的门面
硬绑 `STORE_ITEM_ID='D4-2-rows'`、签名不认 `store_item_id`（§4.1b (5) 变异证明第 5 行）。
⇒ Property 8 说的「dict 形态 / 纯文本固定项」在**现行树上**对应的成员是 `item_blind`，这是
§4.1b (3) 的原因分桶表 + (4) 的 D4 子形态表**交叉**得出的，不是任一张表单独能读出的结论。
§1 把它当**现算观测**断言（成员必属封闭域、桶按现算记录），不写死成员名。

═══ 建造器：全部复用，本文件不抄第二份 ═══

`_merge_spec` / `MERGE_ITEM` / `_substrate` / `_source_mutant` 来自 `test_aos_property_ghost_gate`；
`_readers` / `_spec` / `ITEM` 来自 `test_aos_property_row_identity`（**顶层模块名**形态 —— 该目录无
`__init__.py`，pytest 以 `prepend` 模式把它塞进 `sys.path`）。
🔴 **不**从 `test_aos_skip_whitelist_guard` import 它的 `_census()` / `_whitelist()`：那是 Task 4.8
的独立第二判据，借过来会让本文件的现算退化成对它的回声。
"""
from __future__ import annotations

import inspect
import json
from typing import Any, Final

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync import adopt_overwrite_compute as AOC
from app.services.workpaper_sync import adopt_overwrite_plan as APO
from app.services.workpaper_sync.adopt_overwrite_compute import compute_overwrite_plan
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlanShapeError,
    SkipReason,
    prune_undeclared_rows,
)
from app.services.workpaper_sync.adopt_row_reader import diagnose_row_reader
from app.services.workpaper_sync.store_projection_response import (
    resolve_store_projection_provider,
)

# 🔴 建造器复用（见模块 docstring：禁抄第二份）。
from test_aos_property_ghost_gate import (  # noqa: E402
    _source_mutant,
    _substrate,
)
from test_aos_property_row_identity import ITEM, _readers, _spec  # noqa: E402

# ═════════════════════════════════════════════════════════════════════════════
# 1. 「不可枚举形态」的现算清单（D4 子形态 → SkipReason 成员）
#
# 🔴 分类真源不是本文件，也不是 design 的表格文字，而是 **provider 自己的常量** ——
#    `store_mirror._mirror_row_stores` 正是按下面这些常量名把它们从 rows 循环里排除的
#    （现读该函数的 `_dict_store_items` 构造段，逐字同名）。design §4.1b (4) 的 D4 子形态表
#    只是同一口径的**记录**；口径漂了本节当场打红并点名差异。
# ═════════════════════════════════════════════════════════════════════════════

#: D4 adapter（design §4.1b (4)：无替代路径的 62 条里 `d4` 占 45，其中 16 条属形态使然）。
_D4_ADAPTER: Final[str] = "d4.revenue_detail"

#: 「一个 item 一个常量」的形态。**声明**（常量名），不是 item_id 字面量。
_SCALAR_SHAPE_CONSTS: Final[tuple[tuple[str, str], ...]] = (
    ("dict store", "STORE_ITEM_ID_D49_DICT"),
    ("dict store", "STORE_ITEM_ID_D433_DICT"),
    ("dict store", "STORE_ITEM_ID_D434_DICT"),
    ("dict store", "STORE_ITEM_ID_D436_DICT"),
    ("dict store", "STORE_ITEM_ID_D435_DICT"),
    ("list store", "STORE_ITEM_ID_D48_DICT"),
)

#: 「一个常量一串 item」的形态。
_TUPLE_SHAPE_CONSTS: Final[tuple[tuple[str, str], ...]] = (
    ("D4-7 专用块", "STORE_ITEM_IDS_D47_DEDICATED"),
    ("纯文本固定项", "STORE_ITEM_IDS_D45_FIXED"),
    ("纯文本固定项", "STORE_ITEM_IDS_D413_FIXED"),
)

#: 走 rows 循环、且门面硬绑的**正是它** ⇒ 可枚举（§4.1b (2) 三条之一）。§1 的变异对照组：
#: 同一段扫描器在它身上必须判「不跳过」，否则「全判跳过」的实现也能让本节全绿。
_D4_ENUMERABLE_CONTROL: Final[str] = "STORE_ITEM_ID"


def _d4_special_shapes() -> dict[str, tuple[str, ...]]:
    """现算 D4 的「不进 rows 循环」item，按子形态分组。**返回值全部现读**，无字面量 item_id。"""
    provider = resolve_store_projection_provider(_D4_ADAPTER)
    grouped: dict[str, list[str]] = {}
    for shape, const in _SCALAR_SHAPE_CONSTS:
        value = str(getattr(provider, const, "") or "")
        assert value, f"provider 不再暴露 {const} —— store_mirror 的排除口径已变，本节须按新口径重建"
        grouped.setdefault(shape, []).append(value)
    for shape, const in _TUPLE_SHAPE_CONSTS:
        values = tuple(str(s) for s in (getattr(provider, const, ()) or ()))
        assert values, f"provider 的 {const} 现算为空 —— 排除口径已变，不得当成「本来就没有」"
        grouped.setdefault(shape, []).extend(values)
    return {shape: tuple(items) for shape, items in grouped.items()}


def _skip_reason_of(item_id: str) -> SkipReason | None:
    """生产判定：这条 item 有没有可用行枚举器；没有就给成因。`None` = 可枚举。"""
    provider = resolve_store_projection_provider(_D4_ADAPTER)
    return diagnose_row_reader(provider=provider, store_item_id=item_id).skip_reason


class TestNonEnumerableCensusIsLive:
    """「不可枚举形态」的清单与它们的 `SkipReason` 成员 —— 全部现算，配变异对照。"""

    def test_shape_groups_match_the_store_mirror_exclusion_caliber(self) -> None:
        """四个子形态都非空、彼此不重叠、且**全部**落在 `all_store_item_ids()` 里。

        🔴 判据不写「5 / 1 / 8 / 2 / 16」这些数 —— 只断言结构（非空 / 不重叠 / 是真 item）。
        条数作为**现算观测**进断言消息，口径漂了消息里就能看到差异。
        """
        provider = resolve_store_projection_provider(_D4_ADAPTER)
        grouped = _d4_special_shapes()
        all_ids = set(provider.all_store_item_ids())
        flat = [item for items in grouped.values() for item in items]
        census = {shape: len(items) for shape, items in sorted(grouped.items())}
        assert len(flat) == len(set(flat)), f"子形态之间有重复 item：{census}"
        assert set(flat) <= all_ids, (
            f"这些 item 不在 provider 的 all_store_item_ids() 里：{sorted(set(flat) - all_ids)}"
            f"（现算分组 {census}）—— 排除口径与 provider 清单已脱钩"
        )
        assert len(grouped) == len({s for s, _c in (*_SCALAR_SHAPE_CONSTS, *_TUPLE_SHAPE_CONSTS)}), (
            f"子形态组数与声明的常量分组数不等：{census}"
        )

    def test_every_special_shape_item_is_skipped_with_a_closed_domain_reason(self) -> None:
        """逐条问生产：这些形态**确实**取不到行枚举器，且成因属封闭六成员。

        🔴 这是 Property 8 前提的可执行判据 —— 「不可枚举」不是我声明的，是
        `diagnose_row_reader` 判的。任一条转成可枚举（例如工单修好了门面）本条当场打红，
        届时它就**不该**再被本 property 当作不可枚举形态。
        """
        buckets: dict[str, list[str]] = {}
        for items in _d4_special_shapes().values():
            for item in items:
                reason = _skip_reason_of(item)
                assert reason is not None, (
                    f"{item} 现算**可枚举**了 —— 它已不属「不可枚举形态」，Property 8 的前提在它"
                    "身上不再成立；请回 design §4.1b (4) 重算子形态表，不得改断言迁就"
                )
                assert isinstance(reason, SkipReason), (reason, type(reason).__name__)
                buckets.setdefault(reason.value, []).append(item)
        assert buckets, "现算清单为空 ⇒ 本节空转（先查 _d4_special_shapes 是否读到了常量）"
        # 现算观测入消息：本轮实得全部落一个桶（成因 = 门面 item-blind，见模块 docstring）。
        assert set(buckets) <= {r.value for r in SkipReason}, sorted(buckets)

    def test_the_census_scanner_does_not_judge_everything_unenumerable(self) -> None:
        """🔴 变异对照：同一段扫描器对**走 rows 循环**的那条 item 必须判「可枚举」。

        没有这一条，「全判不可枚举」的实现也能让上一条全绿（结构性结论必配变异证明）。
        """
        provider = resolve_store_projection_provider(_D4_ADAPTER)
        control = str(getattr(provider, _D4_ENUMERABLE_CONTROL, "") or "")
        assert control, f"provider 不再暴露 {_D4_ENUMERABLE_CONTROL} —— 对照组无从构造"
        assert control not in {
            item for items in _d4_special_shapes().values() for item in items
        }, f"{control} 竟落在特殊形态清单里 —— 对照组与被测集合相交，反证失效"
        assert _skip_reason_of(control) is None, (
            f"{control}（门面硬绑的正是它）竟被判不可枚举 —— 扫描器「什么都判跳过」，"
            "上一条断言失去区分力"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2. 载荷池 —— 形态取自 §1 现算出的四个子形态的**真实载荷长相**
#
# 🔴 两种承载形态都必须在（面 ① 的 `is` 判据对两者意义不同）：
#    * **已解析序列 / 映射**：`is` 相等 ⇒ 连浅拷贝都没有；
#    * **JSON 文本**：`is` 相等 ⇒ 连「解析后重序列化」都没有（ADR-AOS-003 的 155/200 漂移）。
# ═════════════════════════════════════════════════════════════════════════════

#: dict 形态（D4-9 `{current,prior}+totals` / D4-33 `{bizTypes,months,priorYear}` 同构）。
_DICT_SHAPE: Final[dict[str, Any]] = {
    "current": {"rows": [{"rowId": "c1", "name": "华东经销商"}], "totalAmount": 1200.5},
    "prior": {"rows": [], "totalAmount": 0},
}

#: list 形态（D4-8 `ProductData[]`）—— 是数组，但没有行身份键、也没有 reader。
_LIST_SHAPE: Final[list[dict[str, Any]]] = [
    {"name": "产品A", "months": [1, 2, 3], "industry": []},
    {"name": "产品B", "months": [], "industry": []},
]

#: 纯文本固定项（D4-5 业务场景 / D4-13 核对过程·结论）—— `remark` 直接存自由文本，**不是 JSON**。
_TEXT_SHAPE: Final[str] = "客户直销为主，账期 60 天；无返利政策与退货条款。"

#: 「载荷形态」池。标签是**声明**，其可解析性由 §4 的实测判据钉住。
_NON_ENUMERABLE_PAYLOADS: Final[tuple[tuple[str, Any], ...]] = (
    ("dict（已解析映射）", _DICT_SHAPE),
    ("dict（JSON 文本）", json.dumps(_DICT_SHAPE, ensure_ascii=False)),
    ("list（已解析序列）", _LIST_SHAPE),
    ("list（JSON 文本）", json.dumps(_LIST_SHAPE, ensure_ascii=False)),
    ("纯文本固定项", _TEXT_SHAPE),
)

#: 合成的不可枚举 store item 身份。刻意带 `AOS-P8`，万一漏进任何输出都能被搜到。
SKIPPED_ITEM: Final[str] = "AOS-P8-NONENUMERABLE-data"

#: 可枚举 item 的载荷（对照组本体）。两条行身份：一条被 substrate 声明、一条没有 ⇒ 必被删。
_KEPT_IDENTITY: Final[str] = "p8-kept"
_DOOMED_IDENTITY: Final[str] = "p8-doomed"


def _enumerable_rows() -> list[dict[str, Any]]:
    """🔴 每次**新建** —— `prune_undeclared_rows` 的对照组要看「入参对象被换掉了」，
    共用一个模块级 list 会让前一条用例的删除结果泄进下一条。"""
    return [{"rowId": _KEPT_IDENTITY, "amount": 1}, {"rowId": _DOOMED_IDENTITY, "amount": 2}]


#: 一个**不在**任何 reader 的 `declared_scopes` 里的表名 —— 用来把「本 item 一张 in-scope 表都
#: 没有」这条作用域门做成可执行输入（`prune_undeclared_rows` 的 `if not in_scope` 早返回）。
_UNDECLARED_TABLE: Final[str] = "aos_p8_table_no_reader_declares"


def _substrate_with(row_keys: dict[str, tuple[str, ...]]) -> Any:
    """多表 projection 替身 —— 复用 ghost gate 的 `_substrate`（单表）再补齐其余表，
    本文件不另写一份 `SimpleNamespace(row_keys=…)`（那就是第二份替身）。"""
    first, *rest = sorted(row_keys)
    projection = _substrate(first, tuple(row_keys[first]))
    for table in rest:
        projection.row_keys[table] = tuple(row_keys[table])
    return projection


def _snapshot(payload: Any) -> str:
    """载荷的**逐字节**快照。独立序列化（不借生产 `_canonical_json`）—— 拿生产实现核生产实现，
    「序列化口径变了」这一类改动会同步移动快照与被测值而永不打红。"""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=repr)


#: 本次运行实际跑过的 `(载荷形态, 跳过原因)` 组合（§6 反空转判据用）。
_SAW_SHAPES: set[str] = set()
_SAW_REASONS: set[str] = set()
#: 对照组实测值：可枚举 item 的载荷**真的**被改动过几次（为 0 ⇒ 「不变」是恒真）。
_SAW_CONTROL_MUTATED: list[tuple[str, int]] = []


# ═════════════════════════════════════════════════════════════════════════════
# 3. Property 8 —— 属性测试本体
# ═════════════════════════════════════════════════════════════════════════════


@given(
    shape=st.sampled_from(_NON_ENUMERABLE_PAYLOADS),
    # 🔴 原因取值域从**枚举现取**（ADR-AOS-005 §5(4)：封闭六成员），不写字面量清单 ——
    #    新增成员自动进生成器，漏进白名单校验的后门当场被本 property 走到。
    reason=st.sampled_from(tuple(SkipReason)),
    declare_other_table=st.booleans(),
)
@settings(max_examples=5, deadline=None)
def test_property8_nonenumerable_payload_untouched_and_registered(
    shape: tuple[str, Any], reason: SkipReason, declare_other_table: bool
) -> None:
    """Property 8: 不可枚举形态的载荷不被改动且被登记。

    **Validates: Requirements 4.1**

    一次执行同时跑三件事（缺任一件判据就不能为 False）：

    * 面 ①-plan：跳过项的 delta `table_key is None` / `rows_deleted == ()`，且
      `compute_overwrite_plan` 不动调用方手里那份载荷对象（`is` + 逐字节快照双判）；
    * 面 ②：`(item_id, reason)` 必在 `skipped_items` 里；
    * **对照组**：同一次输入里的可枚举 item 载荷**确实被改动**（`rows_deleted` 非空）⇒
      「不变」不是恒真。
    """
    label, payload = shape
    spec = _spec(identity_key="rowId")
    reader = dict(_readers(spec))["EngineRowReader"]
    rows = _enumerable_rows()
    row_keys = {spec.table_key: (_KEPT_IDENTITY,)}
    if declare_other_table:
        # 多一张与本次无关的声明表 —— 跳过项不因「声明面变宽」而被卷进删除侧。
        row_keys["aos_p8_unrelated_rows"] = (_DOOMED_IDENTITY,)

    before = _snapshot(payload)
    plan = compute_overwrite_plan(
        substrate_projection=_substrate_with(row_keys),
        store_payloads={ITEM: rows, SKIPPED_ITEM: payload},
        row_readers={ITEM: reader},
        skip_reasons={SKIPPED_ITEM: reason},
    )

    # ── 面 ②：显式清单里必有 `(item_id, reason)` 这个二元组 ───────────────────
    assert (SKIPPED_ITEM, reason) in plan.skipped_items, (
        f"{label} / {reason.value}：跳过项没进 skipped_items（实得 {plan.skipped_items}）—— "
        "Requirement 4.2 的显式清单漏项。它是 deltas 的派生投影 ⇒ 最可能是该 item 没产 delta"
    )

    # ── 面 ①-plan：计划侧一条删除都没有，且载荷对象没被换掉/改写 ──────────────
    dead = [d for d in plan.deltas if d.item_id == SKIPPED_ITEM]
    assert len(dead) == 1, f"{label}：跳过项应恰 1 条 delta，实得 {len(dead)}"
    assert dead[0].table_key is None and dead[0].skipped_reason is reason, dead[0]
    assert dead[0].rows_deleted == (), (
        f"{label} / {reason.value}：跳过项带了 {dead[0].rows_deleted} 条 rows_deleted —— "
        "Requirement 4.1 跳过的是**删除侧**，带删除清单就是「悄悄删了一部分」"
    )
    assert _snapshot(payload) == before, (
        f"{label} / {reason.value}：载荷逐字节快照变了 —— compute_overwrite_plan 改了入参"
    )

    # ── 对照组：可枚举 item 的载荷**确实**被删除侧改动 ─────────────────────────
    live = [d for d in plan.deltas if d.item_id == ITEM]
    assert len(live) == 1 and live[0].rows_deleted == (_DOOMED_IDENTITY,), (
        f"{label}：对照组没算出删除（实得 {[d.rows_deleted for d in live]}）⇒ 本次「跳过项不变」"
        "是恒真的，判据无区分力"
    )
    pruned, deleted = prune_undeclared_rows(rows, row_keys=row_keys, reader=reader)
    assert deleted == (_DOOMED_IDENTITY,) and pruned is not rows, (
        f"{label}：对照组载荷未被换掉（deleted={deleted}）⇒ 「不变」恒真"
    )
    assert [r["rowId"] for r in pruned] == [_KEPT_IDENTITY], pruned
    _SAW_CONTROL_MUTATED.append((label, len(rows) - len(pruned)))

    # ── 面 ①-prune：真正重写载荷的那个函数在跳过项上返回**入参对象本身** ───────
    #    跳过项没有 reader ⇒ 生产路径根本不调它；这里用「一张 in-scope 表都没有」把同一条
    #    保证做成可执行判据：`is` 相等 ⇒ JSON 文本连解析-重序列化都没发生。
    kept, nothing = prune_undeclared_rows(
        payload, row_keys={_UNDECLARED_TABLE: (_KEPT_IDENTITY,)}, reader=reader
    )
    assert kept is payload, (
        f"{label}：prune 返回了**另一个对象**（{type(kept).__name__}）—— `==` 相等也不够，"
        "Task 4.1 的契约是「零删除时第一个元素是入参对象本身」（ADR-AOS-003：重序列化即漂移）"
    )
    assert nothing == (), (label, nothing)
    assert _snapshot(payload) == before, f"{label}：prune 改了入参载荷"

    _SAW_SHAPES.add(label)
    _SAW_REASONS.add(reason.value)


# ═════════════════════════════════════════════════════════════════════════════
# 4. 面 ① 的另一半 —— 不可枚举形态**落进作用域**时 fail visible，绝不静默重写
#
# 🔴 §3 验的是「作用域外 ⇒ 原样返回」；本节验「万一真被喂进来 ⇒ 抛，而不是返回一份被重写的
#    载荷」。两条合起来才排除「静默部分覆盖」这唯一真正危险的第三种结局。
# 🔴 抛的必须是 **provider / 引擎的原生异常**（`RowTableStorePayloadError`，Task 6.2 翻 422），
#    不是本模块的 `OverwritePlanShapeError`（它刻意不映射状态码，兜住会把 422 变 500）。
# ═════════════════════════════════════════════════════════════════════════════


class TestNonEnumerableShapeInScopeFailsVisible:
    """不可枚举形态 + 表在作用域内 ⇒ 抛；且抛之前**没有**返回过任何被重写的载荷。"""

    @pytest.mark.parametrize(
        ("label", "payload"),
        [(lb, pl) for lb, pl in _NON_ENUMERABLE_PAYLOADS if not isinstance(pl, list)],
    )
    def test_dict_and_text_shapes_raise_instead_of_being_rewritten(
        self, label: str, payload: Any
    ) -> None:
        spec = _spec(identity_key="rowId")
        reader = dict(_readers(spec))["EngineRowReader"]
        before = _snapshot(payload)
        with pytest.raises(Exception) as excinfo:  # noqa: PT011 —— 见下断言：类名 + 文案双判
            prune_undeclared_rows(
                payload, row_keys={spec.table_key: (_KEPT_IDENTITY,)}, reader=reader
            )
        assert type(excinfo.value).__name__ == "RowTableStorePayloadError", (
            f"{label}：抛的是 {type(excinfo.value).__name__} 而不是引擎原生异常 —— "
            "Task 6.2 按后者翻 422；换成 OverwritePlanShapeError 会变 500"
        )
        assert ITEM in str(excinfo.value), (
            f"{label}：异常文案没带 item_id —— Requirement 4.4 要求「给出该 item 的 item_id」"
        )
        assert _snapshot(payload) == before, f"{label}：抛之前把入参改了"

    def test_the_list_shape_is_parseable_so_its_skip_is_about_the_reader_not_the_json(
        self,
    ) -> None:
        """🔴 list 形态（D4-8 `ProductData[]`）**能**被解析成数组 ⇒ 它被跳过的原因**不是**载荷
        不可解析，而是**没有行枚举器**（现算成因 `item_blind`，见 §1）。

        这条是防归因错误的：把 D4-8 写进 Requirement 4.4（fail visible）那一族就错了 ——
        它该走 Requirement 4.1（跳过 + 登记）。判据 = 它是合法 JSON 数组、且元素是对象。
        """
        for label, payload in _NON_ENUMERABLE_PAYLOADS:
            if not label.startswith("list"):
                continue
            parsed = json.loads(payload) if isinstance(payload, str) else payload
            assert isinstance(parsed, list) and parsed, (label, type(parsed).__name__)
            assert all(isinstance(element, dict) for element in parsed), label
            # 但它没有行身份键 ⇒ 交给引擎必抛「缺少稳定行身份」，故**不能**硬塞一个 reader 凑合用。
            assert all("rowId" not in element for element in parsed), (
                f"{label}：样本带上了行身份键 ⇒ 它其实可枚举，不再是本 property 的形态"
            )


# ═════════════════════════════════════════════════════════════════════════════
# 5. 变异反证 —— 三组，判据必须能为 False
#
# 🔴 手段与 Task 4.5 同源：复用 `_source_mutant`（**进程内**源码级变异，`inspect.getsource`
#    取生产函数 → 替换唯一锚点 → 在模块 globals 的**副本**里 exec）⇒ 生产模块一字不动、
#    不改任何共用文件、不落盘。锚点是子串不是行号；`count(old) == 1` 让锚点消失时当场打红。
# ═════════════════════════════════════════════════════════════════════════════

#: **M1 —— 跳过的 item 不产 delta**。`skipped_items` 是 `deltas` 的派生投影 ⇒ 不产 delta 它就
#: 整条消失，Requirement 4.2 的显式清单漏项。预期：面 ② 打红。
_M1_SKIPPED_ITEM_PRODUCES_NO_DELTA: Final[tuple[str, str]] = (
    "deltas.append(\n                ItemOverwriteDelta(item_id=item_id, "
    "table_key=None, skipped_reason=reason)\n            )",
    "pass",
)

#: **M2 —— 零删除时也重序列化一遍**（纯 round-trip：`json.loads(_canonical_json(payload))`）。
#: 🔴 变异体的产物 `==` 入参但 `is` 不等 ⇒ **只用 `==` 的判据会把它判绿**，正是「逐字节不变必须
#: 验到 `is`」这条的可执行证明（ADR-AOS-003：重序列化即字符串漂移，真库 155/200 条）。
_M2_ZERO_DELETION_RESERIALISES: Final[tuple[str, str]] = (
    "if not in_scope:\n        return payload, ()",
    "if not in_scope:\n        return json.loads(_canonical_json(payload)), ()",
)

#: **M3 —— 域外原因静默降级成一个合法成员**（而不是当场拒收）。预期：封闭域守卫失效，
#: 一个编造的原因被报成 `absent` ⇒ Requirement 4.3 的「白名单无失效条目」形同虚设。
_M3_OUT_OF_DOMAIN_REASON_DEGRADES: Final[tuple[str, str]] = (
    "out[key] = SkipReason(str(raw))",
    "out[key] = SkipReason(str(raw)) if str(raw) in {r.value for r in SkipReason} "
    "else SkipReason.absent",
)

#: 域外原因字符串。刻意像个合理的粗粒度兜底名（design §4.1b (4) 点名禁止的那一类）。
_BOGUS_REASON: Final[str] = "no_row_reader"


def _mixed_inputs(*, with_skipped: bool = True) -> dict[str, Any]:
    """一份同时含「可枚举 item」与「不可枚举 item」的最小输入（三组变异共用）。

    🔴 `with_skipped=False` 是 **adapter 级**那条路要的形态：`no_store_item` 的键是 adapter_id、
    本来就不在 `store_payloads` 里，而 `compute_overwrite_plan` 对「在 `store_payloads` 里却既无
    reader 也无原因」的 item 会当场抛（现读那条 `既无 reader 也无跳过原因` 分支）⇒ 走 adapter 级
    时必须把 item 级的跳过项一并撤掉，否则测的是那条无关的抛。
    """
    spec = _spec(identity_key="rowId")
    reader = dict(_readers(spec))["EngineRowReader"]
    payloads: dict[str, Any] = {ITEM: _enumerable_rows()}
    if with_skipped:
        payloads[SKIPPED_ITEM] = _DICT_SHAPE
    return {
        "substrate_projection": _substrate_with({spec.table_key: (_KEPT_IDENTITY,)}),
        "store_payloads": payloads,
        "row_readers": {ITEM: reader},
    }


class TestMutationCounterProof:
    """三组变异各贴一侧红。全部进程内，生产模块一字不动（末条是该手段本身的验收判据）。"""

    def test_m1_skipped_item_without_a_delta_disappears_from_the_list(self) -> None:
        """M1：跳过项不产 delta ⇒ `skipped_items` 空 ⇒ 面 ② 打红。"""
        kwargs = _mixed_inputs() | {"skip_reasons": {SKIPPED_ITEM: SkipReason.item_blind}}
        # 对照组：生产实现登记得上。
        assert (SKIPPED_ITEM, SkipReason.item_blind) in compute_overwrite_plan(
            **kwargs
        ).skipped_items
        mutant = _source_mutant(
            AOC.compute_overwrite_plan,
            old=_M1_SKIPPED_ITEM_PRODUCES_NO_DELTA[0],
            new=_M1_SKIPPED_ITEM_PRODUCES_NO_DELTA[1],
            module=AOC,
        )
        plan = mutant(**_mixed_inputs() | {"skip_reasons": {SKIPPED_ITEM: SkipReason.item_blind}})
        assert plan.skipped_items == (), (
            f"M1 竟仍登记了 {plan.skipped_items} —— 变异没生效（append 那段没被打到），反证失效"
        )
        assert [d.item_id for d in plan.deltas] == [ITEM], (
            f"M1 应当只剩可枚举 item 的 delta，实得 {[d.item_id for d in plan.deltas]}"
        )

    @pytest.mark.parametrize(
        ("label", "payload"),
        [
            (lb, pl)
            for lb, pl in _NON_ENUMERABLE_PAYLOADS
            if lb in ("dict（已解析映射）", "dict（JSON 文本）")
        ],
    )
    def test_m2_reserialisation_is_invisible_to_eq_but_caught_by_is(
        self, label: str, payload: Any
    ) -> None:
        """M2：零删除时做一次纯 round-trip ⇒ `==` **仍然通过**、`is` 打红。

        🔴 这条同时证明了两件事：① 面 ① 的判据必须是 `is`；② 用 `==` 写的那版判据是假绿。
        """
        spec = _spec(identity_key="rowId")
        reader = dict(_readers(spec))["EngineRowReader"]
        args = {"row_keys": {_UNDECLARED_TABLE: (_KEPT_IDENTITY,)}, "reader": reader}
        # 对照组：生产实现返回入参对象本身。
        assert prune_undeclared_rows(payload, **args)[0] is payload
        mutant = _source_mutant(
            APO.prune_undeclared_rows,
            old=_M2_ZERO_DELETION_RESERIALISES[0],
            new=_M2_ZERO_DELETION_RESERIALISES[1],
            module=APO,
        )
        got, deleted = mutant(payload, **args)
        assert got is not payload, (
            f"{label}：M2 仍返回了同一个对象 —— 变异没生效（早返回那句没被打到），反证失效"
        )
        assert got == payload, (
            f"{label}：M2 的产物连 `==` 都不等（{type(got).__name__}）—— 那就不是「只是重序列化」，"
            "这条反证证明不了「`==` 判据是假绿」；请检查变异串"
        )
        assert deleted == (), (label, deleted)

    def test_m3_out_of_domain_reason_silently_becomes_a_legal_member(self) -> None:
        """M3：域外原因不再当场拒收 ⇒ 被静默报成 `absent`（形态合法、内容是错的）。

        对照组 = 生产实现在 **两个**层面都拒收：`compute_overwrite_plan` 的 `_normalise_reasons`
        与 `ItemOverwriteDelta._normalise_skipped_reason`（两道同口径的门，任一单独失效都仍被另一
        道挡住 ⇒ 分开各验一次）。
        """
        kwargs = _mixed_inputs() | {"skip_reasons": {SKIPPED_ITEM: _BOGUS_REASON}}
        with pytest.raises(OverwritePlanShapeError) as plan_side:
            compute_overwrite_plan(**kwargs)
        assert _BOGUS_REASON in str(plan_side.value) and "封闭域" in str(plan_side.value)
        with pytest.raises(OverwritePlanShapeError) as delta_side:
            ItemOverwriteDelta(item_id=SKIPPED_ITEM, table_key=None, skipped_reason=_BOGUS_REASON)
        assert _BOGUS_REASON in str(delta_side.value)

        mutant = _source_mutant(
            AOC._normalise_reasons,
            old=_M3_OUT_OF_DOMAIN_REASON_DEGRADES[0],
            new=_M3_OUT_OF_DOMAIN_REASON_DEGRADES[1],
            module=AOC,
        )
        got = mutant({SKIPPED_ITEM: _BOGUS_REASON})
        assert got == {SKIPPED_ITEM: SkipReason.absent}, (
            f"M3 实得 {got} —— 变异没生效（归一那句没被打到），反证失效"
        )
        # 危害具体化：降级后的原因**形态合法** ⇒ 一路走到 skipped_items 里冒充真原因。
        laundered = compute_overwrite_plan(
            **(_mixed_inputs() | {"skip_reasons": {SKIPPED_ITEM: got[SKIPPED_ITEM]}})
        )
        assert laundered.skipped_items == ((SKIPPED_ITEM, SkipReason.absent),), (
            f"降级后的原因没能冒充真原因（实得 {laundered.skipped_items}）—— M3 的危害就在于"
            "「编造的原因被洗成了一个合法成员」，这条没证成整组反证就只证了一半"
        )

    def test_mutation_did_not_touch_the_production_modules(self) -> None:
        """🔴 变异不得回写生产模块：三个锚点在**实时**源码里仍各恰 1 处、且变异串不在。

        这是「用进程内变异而不是改文件」这个手段本身的验收判据 —— 变异体若被回写，锚点就不在了。
        """
        cases = (
            (AOC.compute_overwrite_plan, _M1_SKIPPED_ITEM_PRODUCES_NO_DELTA),
            (APO.prune_undeclared_rows, _M2_ZERO_DELETION_RESERIALISES),
            (AOC._normalise_reasons, _M3_OUT_OF_DOMAIN_REASON_DEGRADES),
        )
        for func, (old, new) in cases:
            src = inspect.getsource(func)
            assert src.count(old) == 1, (func.__name__, src.count(old))
            assert new not in src, (
                f"{func.__name__} 的实时源码里出现了变异串 —— 变异体被回写进了生产模块"
            )


# ═════════════════════════════════════════════════════════════════════════════
# 6. 反空转判据（生成器覆盖面 + 封闭域现取 + 对照组实测值）
# ═════════════════════════════════════════════════════════════════════════════


class TestProperty8DidNotRunVacuously:
    """§3 的三段断言在「载荷池 / 原因域 / 对照组」任一退化时都会变成空转 ⇒ 逐条钉住。"""

    def test_the_reason_domain_is_taken_from_the_live_enum_and_is_closed_at_six(self) -> None:
        """🔴 原因取值域必须**从枚举现取**，不是本文件的字面量清单。

        判据两条：① 生成器的取值域 `is` 那个枚举（`tuple(SkipReason)` 逐值相等）；
        ② 成员数与 ADR-AOS-005 §5(4) 的「六成员封闭」对账 —— 不等时点名差异，
        提醒「新增成员必须同时更新 Requirement 4.3 的白名单校验（Task 4.8）」。
        """
        live = tuple(SkipReason)
        assert len(live) == len({member.value for member in live}), live
        assert len(live) == 6, (
            f"`SkipReason` 现算 {len(live)} 个成员（ADR-AOS-005 §5(4) 记六成员封闭）："
            f"{[m.value for m in live]} —— 扩域必须同步 Task 4.8 的白名单校验表，"
            "否则新原因就是个没人核的后门"
        )
        assert _BOGUS_REASON not in {member.value for member in live}, (
            f"{_BOGUS_REASON!r} 竟进了封闭域 —— §5 的 M3 反证失去意义"
            "（design §4.1b (4) 点名它是被四个原因桶取代的粗粒度写法）"
        )

    def test_every_reason_member_was_exercised_by_the_property(self) -> None:
        """🔴 `max_examples=5` < 六成员 ⇒ 单次运行不可能穷举 ⇒ 本条只断言「跑过的都在域内、
        且至少跑过一个」，另由下面的参数化测试把六个成员**穷举**一遍。"""
        if not _SAW_REASONS:
            pytest.skip("本次选择未执行 Property 8（如 -k 定向）⇒ 累计器为空")
        assert _SAW_REASONS <= {member.value for member in SkipReason}, sorted(_SAW_REASONS)

    @pytest.mark.parametrize("reason", list(SkipReason), ids=lambda r: r.value)
    def test_each_reason_member_reaches_the_skipped_items_list(
        self, reason: SkipReason
    ) -> None:
        """六成员**逐个**都能以 `(item_id, reason)` 落进清单 —— 补齐 PBT 采样覆盖不到的那几个。

        🔴 含 `no_store_item`：它是唯一允许以 **adapter_id** 作键的成员
        （`_ADAPTER_LEVEL_REASONS`），但本条走的是 item 级（key 在 `store_payloads` 里）⇒
        两条路都走得通，不是笔误。
        """
        plan = compute_overwrite_plan(**(_mixed_inputs() | {"skip_reasons": {SKIPPED_ITEM: reason}}))
        assert plan.skipped_items == ((SKIPPED_ITEM, reason),), plan.skipped_items
        # 🔴 adapter 级那条路也逐成员走一遍（key **不在** `store_payloads` 里）：只有
        #    `_ADAPTER_LEVEL_REASONS` 的成员许可，其余必须当场抛 —— 这才证明那个门是真门，
        #    而不是「随便哪个原因都能拿 adapter_id 作键」。
        adapter_key = "aos.p8_adapter_without_store_item"
        adapter_kwargs = _mixed_inputs(with_skipped=False) | {
            "skip_reasons": {adapter_key: reason}
        }
        if reason in AOC._ADAPTER_LEVEL_REASONS:
            assert (adapter_key, reason) in compute_overwrite_plan(
                **adapter_kwargs
            ).skipped_items, f"{reason.value} 是 adapter 级成员却没能以 adapter_id 登记"
        else:
            with pytest.raises(OverwritePlanShapeError) as excinfo:
                compute_overwrite_plan(**adapter_kwargs)
            assert adapter_key in str(excinfo.value), (reason.value, str(excinfo.value)[:200])

    def test_all_payload_shapes_were_exercised(self) -> None:
        """🔴 `max_examples=5` 与池大小同阶 ⇒ 不保证一次跑全，故这里只核「跑过的都在池里」，
        并由下面那条把两种承载形态（JSON 文本 / 已解析）各钉一例。"""
        if not _SAW_SHAPES:
            pytest.skip("本次选择未执行 Property 8 ⇒ 累计器为空")
        assert _SAW_SHAPES <= {label for label, _p in _NON_ENUMERABLE_PAYLOADS}, sorted(_SAW_SHAPES)

    def test_both_carrier_forms_are_in_the_pool_and_is_identity_holds_for_each(self) -> None:
        """🔴 两种承载形态必须都在池里、且 `is` 判据对两者各成立一例。

        * **JSON 文本**：`is` 相等 ⇒ 连「解析后重序列化」都没发生（`_as_row_list` 真的解析过它，
          零删除分支返回的却仍是原**文本对象**）；
        * **已解析序列 / 映射**：`is` 相等 ⇒ 连浅拷贝都没有。
        """
        texts = [(lb, pl) for lb, pl in _NON_ENUMERABLE_PAYLOADS if isinstance(pl, str)]
        parsed = [(lb, pl) for lb, pl in _NON_ENUMERABLE_PAYLOADS if not isinstance(pl, str)]
        assert texts and parsed, (
            f"载荷池缺一种承载形态（文本 {len(texts)} / 已解析 {len(parsed)}）—— "
            "面 ① 的 `is` 判据对两者意义不同，缺一即少验一半"
        )
        spec = _spec(identity_key="rowId")
        reader = dict(_readers(spec))["EngineRowReader"]
        for label, payload in (*texts, *parsed):
            got, deleted = prune_undeclared_rows(
                payload, row_keys={_UNDECLARED_TABLE: (_KEPT_IDENTITY,)}, reader=reader
            )
            assert got is payload and deleted == (), (label, type(got).__name__, deleted)

    def test_json_text_survives_parsing_without_reserialisation(self) -> None:
        """🔴 最强的那一例：载荷**在作用域内**、被真解析过、只是零删除 ⇒ 返回物仍 `is` 原文本。

        这条与 §3 的「作用域外早返回」**不同**：那条根本没解析；本条 `_as_row_list` 真跑了
        `json.loads`，返回的却仍是原字符串对象 ⇒ ADR-AOS-003 的「重序列化即漂移」被按字面挡住。
        对照组在同一函数里：只要有一行未声明，返回物就换成新 list。
        """
        spec = _spec(identity_key="rowId")
        reader = dict(_readers(spec))["EngineRowReader"]
        text = json.dumps(_enumerable_rows(), ensure_ascii=False)
        got, deleted = prune_undeclared_rows(
            text,
            row_keys={spec.table_key: (_KEPT_IDENTITY, _DOOMED_IDENTITY)},
            reader=reader,
        )
        assert got is text and deleted == (), (type(got).__name__, deleted)
        shrunk, dropped = prune_undeclared_rows(
            text, row_keys={spec.table_key: (_KEPT_IDENTITY,)}, reader=reader
        )
        assert dropped == (_DOOMED_IDENTITY,) and isinstance(shrunk, list), (dropped, shrunk)
        assert shrunk is not text and json.loads(text) != shrunk, (
            "有删除时返回物竟与原载荷等价 —— 对照组失效，「零删除时 is 相等」这条无从证明其强度"
        )

    def test_the_control_group_really_mutated_the_enumerable_payload(self) -> None:
        """🔴 对照组实测值：可枚举 item 的载荷**每次**都真被删掉了行（删 0 行 ⇒ 「不变」恒真）。"""
        if not _SAW_CONTROL_MUTATED:
            pytest.skip("本次选择未执行 Property 8 ⇒ 累计器为空")
        assert all(dropped == 1 for _label, dropped in _SAW_CONTROL_MUTATED), (
            f"对照组有 run 没删到行：{_SAW_CONTROL_MUTATED}"
        )

    def test_the_skipped_item_is_not_accidentally_enumerable(self) -> None:
        """🔴 合成的跳过项身份不得与可枚举 item 撞名，否则 §3 的两组断言指向同一条 delta。"""
        assert SKIPPED_ITEM != ITEM and _UNDECLARED_TABLE != _spec(
            identity_key="rowId"
        ).table_key
        assert "AOS-P8" in SKIPPED_ITEM, "合成身份要能被搜到（漏进真实输出时可定位）"

    def test_the_skip_gate_in_the_delta_model_is_live(self) -> None:
        """🔴 面 ①-plan 靠的是 `ItemOverwriteDelta` 的「跳过 ⇒ 删除清单必须为空」那道门 ——
        这里直接验它还在（它若被摘掉，§3 的 `rows_deleted == ()` 就只是在验 compute 的巧合）。"""
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            ItemOverwriteDelta(
                item_id=SKIPPED_ITEM,
                table_key=None,
                rows_deleted=(_DOOMED_IDENTITY,),
                skipped_reason=SkipReason.item_blind,
            )
        assert "rows_deleted" in str(excinfo.value) and SKIPPED_ITEM in str(excinfo.value)
        # 变异对照：同一构造去掉 `rows_deleted` 必须通过 ⇒ 这道门不是「什么都拒」。
        assert ItemOverwriteDelta(
            item_id=SKIPPED_ITEM, table_key=None, skipped_reason=SkipReason.item_blind
        ).rows_deleted == ()

    def test_the_source_anchors_used_by_section_5_are_live(self) -> None:
        """三个变异锚点在生产源码里各恰 1 处（锚点消失 ⇒ 生产写法变了，§5 须按新写法重建）。"""
        counts = {
            func.__name__: inspect.getsource(func).count(old)
            for func, (old, _new) in (
                (AOC.compute_overwrite_plan, _M1_SKIPPED_ITEM_PRODUCES_NO_DELTA),
                (APO.prune_undeclared_rows, _M2_ZERO_DELETION_RESERIALISES),
                (AOC._normalise_reasons, _M3_OUT_OF_DOMAIN_REASON_DEGRADES),
            )
        }
        assert all(n == 1 for n in counts.values()), counts
        # 变异对照：`return payload, ()` 在 prune 里现算**多于 1 处** ⇒ M2 的锚点必须带上
        # `if not in_scope:` 前缀才唯一。这条钉住「锚点收窄是必需的」而不是我多写了一行。
        bare = inspect.getsource(APO.prune_undeclared_rows).count("return payload, ()")
        assert bare > 1, (
            f"`return payload, ()` 现算只有 {bare} 处 —— M2 锚点的收窄理由消失了，"
            "请复核 prune_undeclared_rows 的早返回分支是否被合并"
        )
