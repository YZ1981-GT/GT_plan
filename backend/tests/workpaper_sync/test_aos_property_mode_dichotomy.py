"""Task 7.2 —— **Property 5: 模式二分（OO 不被连带改变）** 与 design § 3.3 的 **J3**。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
**Validates: Requirements 2.1, 2.4** · ADR-AOS-001（后置 prune ⇒ OO 路径零改动）

═══ design 原文（逐字）═══

> ### Property 5: 模式二分（OO 不被连带改变）
>
> *For any* 满足「base 独有身份非空」的 `(base, projection)` 组合，base 权威模式下这些身份全部
> 保留、substrate 权威模式下这些身份全部消失，且两模式的结果行集不相等。

design § 3.3 的 **J3** 是同一件事的判据形态：

> | J3 | 同一 `(base, projection)` 经 OO 路径与 adopt 路径执行，**删除侧结果不同** | 变异反证（相同即判据失效） |

⇒ 本文件同时兑现 Property 5 与 J3；J1 / J2 / J5 在 `test_aos_oo_path_isolation.py`，
J4 是 Task 7.3 的定向回归动作（无判据文件）。

═══ 两个「模式」在本 spec 里各是什么（现读实证，不是命名推断）═══

ADR-AOS-001 采纳的是「方案 4：后置 prune」⇒ 两个模式**不是**一个带 `mode` 参数的函数的两个
分支（那是被否决的方案 1），而是**两条调用序列**：

| 模式 | 序列 | 生产落点 |
| --- | --- | --- |
| **base 权威**（OO callback） | `provider_merge(projection, base)` | `store_mirror.mirror_projection_into_store` ——「三态 → merge → 写回」，全程**不出现**删除侧（J1/J2 已锁） |
| **substrate 权威**（adopt） | `provider_merge(...)` **再** `prune_undeclared_rows(...)` | `adopt_overwrite_apply.apply_overwrite_deletions` —— 全仓唯一 prune 调用点（J5 已锁） |

⇒ 本文件的两个 runner 就是这两条序列，**共用同一个** `merge_projection_into_store_rows`
（引擎，OO 与 adopt 的共用真源）。🔴 base 权威 runner **不是**我另写的一份「OO 的语义」，
它就是「只跑 merge」—— 这正是 `store_mirror` 做的全部事情。

═══ 🔴 为什么必须三条子判据一起断言（design prework 已裁定，本文件照它落）═══

design「§ prework 合并记录」那格原文：

> | 2.1 + 2.4 → P5 | 2.4 是 2.1 的变异证明。若拆两条，2.1 可能因「删除侧根本没接」而假绿；
> 合并后三个断言互为变异证明 |

具体：**C1**（base 权威保留）单独成立于「prune 从未被接进任何路径」；**C2**（substrate 权威
消失）单独成立于「两侧都删」；只有 **C3**（两侧结果**不相等**）把这两种退化同时排掉。
§4 的 M1 / M2 各打红一侧，M1 与 M2 互为对照 —— 一个变异只红一侧才说明三条子判据真的分得开。

═══ 🔴 反空转（否则「二分」在空集上恒真）═══

「base 独有身份非空」是 property 的**前提**。生成器保证它每次非空（`base_only` 的
`min_size=1`），但这还不够 —— 若 substrate 从不声明任何**新**身份，adopt 路径就退化成「只删」
而测不到「覆盖」；若分区维度从未出现，分区门（Requirement 1.4）在本 property 上是空转。
⇒ §5 用累计器现算四类场景的出现次数并断言均 > 0，交付时把实测计数写进 tasks.md。

═══ 建造器：**全部**复用，一份不抄 ═══

`_merge_spec` / `_anchor_of` / `_projection` / `_base_row` / 两个锚点取值池 / `MERGE_ITEM` /
`_usable_section_field` 从 `test_aos_property_ghost_gate` import（顶层模块名形态 —— 该目录无
`__init__.py`，pytest 走 `prepend`）；行身份字母表从 `test_aos_property_row_identity` import；
源码级变异器从 `test_aos_adopt_plan_wiring` import。🔴 一份都不新造：merge 侧建造器一漂，
本文件与 Property 3 就在测两件不同的事。
"""

from __future__ import annotations

import inspect
from typing import Any, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync import adopt_overwrite_plan as AOP
from app.services.workpaper_sync.adopt_overwrite_plan import prune_undeclared_rows
from app.services.workpaper_sync.adopt_row_reader_r3 import EngineRowReader
from app.services.workpaper_sync.phase5_row_table_sheet import (
    RowTableSheetSpec,
    merge_projection_into_store_rows,
)

from test_aos_adopt_plan_wiring import _source_mutant  # noqa: E402
from test_aos_property_ghost_gate import (  # noqa: E402
    _MERGE_FIELDS,
    _NONEMPTY_ANCHORS,
    _anchor_of,
    _base_row,
    _merge_spec,
    _projection,
    _usable_section_field,
    MERGE_ITEM,
)
from test_aos_property_row_identity import _IDENTITY_ALPHABET  # noqa: E402

#: 本文件的表 key（与 Property 3 的 `aos_p3_rows` 区分，便于失败文案定位）。
TABLE = "aos_p5_rows"


# ═══════════════════════════════════════════════════════════════════════════════
# §1 两条**真实**调用序列（两个「模式」）
# ═══════════════════════════════════════════════════════════════════════════════


def _reader(spec: RowTableSheetSpec) -> EngineRowReader:
    """本 item 的行枚举器 —— 与 adopt 生产侧同一实现（`adopt_row_reader_r3.EngineRowReader`）。

    🔴 `declared_scopes` 取自 **spec 声明**（`table_key` / `row_section_value`），不写字面量：
    分区值一旦硬编码，分区门（Requirement 1.4）就变成「测试自己规定的分区」。
    """
    return EngineRowReader(
        item_id=MERGE_ITEM,
        specs=(spec,),
        section_field=spec.row_section_field,
        declared_scopes=((spec.table_key, spec.row_section_value or None),),
    )


def run_base_authoritative(
    spec: RowTableSheetSpec, *, base_rows: list[dict[str, Any]], projection: Any
) -> list[Mapping[str, Any]]:
    """**base 权威模式 = OO callback 路径**：只跑 provider merge，没有删除侧。

    这不是「我模拟的 OO 语义」—— `store_mirror.mirror_projection_into_store` 的全部工作就是
    「三态查表 → 读 base → 调 merge → 写回」，其中与行集相关的只有这一次 merge（J1/J2 锁的
    正是「它体内没有任何删除侧符号」）。
    """
    merged, *_rest = merge_projection_into_store_rows(
        spec, projection=projection, base_rows=base_rows
    )
    return merged


def run_substrate_authoritative(
    spec: RowTableSheetSpec,
    *,
    base_rows: list[dict[str, Any]],
    projection: Any,
    declared: tuple[str, ...],
    prune: Any = prune_undeclared_rows,
) -> tuple[list[Mapping[str, Any]], tuple[str, ...]]:
    """**substrate 权威模式 = adopt 路径**：merge 跑完**再**后置 prune（ADR-AOS-001）。

    🔴 顺序不可调换（design ADR-AOS-001 / tasks.md 6.3 已实测）：前置清 base 会让幽灵行门
    全面生效。`prune` 留成入参**只为 §4 的变异反证**喂变异体，生产默认值就是真函数。
    """
    merged = run_base_authoritative(spec, base_rows=base_rows, projection=projection)
    pruned, deleted = prune(merged, row_keys={spec.table_key: declared}, reader=_reader(spec))
    return pruned, deleted


def _identities(spec: RowTableSheetSpec, rows: list[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(str(row[spec.row_identity_key]) for row in rows)


# ═══════════════════════════════════════════════════════════════════════════════
# §2 判据：三条子判据逐字对应 design Property 5 的三句话
# ═══════════════════════════════════════════════════════════════════════════════


def judge_mode_dichotomy(
    *,
    base_only: tuple[str, ...],
    oo_identities: tuple[str, ...],
    adopt_identities: tuple[str, ...],
) -> list[str]:
    """返回违规清单（空 = Property 5 成立）。**纯函数** ⇒ §4 的变异体可直接喂进来。"""
    violations: list[str] = []
    assert base_only, "前提已破：base 独有身份为空 —— Property 5 的 *For any* 限定了它非空"
    kept = [i for i in base_only if i in oo_identities]
    if len(kept) != len(base_only):
        violations.append(
            f"C1 破：base 权威模式（OO）丢了 base 独有身份 "
            f"{sorted(set(base_only) - set(oo_identities))} —— "
            "Requirement 2.1「不删除 projection 未声明的 store 行身份」当场破，"
            "用户在表单侧刚加的行会被 OO 的每次保存静默删掉"
        )
    still_there = [i for i in base_only if i in adopt_identities]
    if still_there:
        violations.append(
            f"C2 破：substrate 权威模式（adopt）没删掉 base 独有身份 {sorted(still_there)} —— "
            "「以在线编辑侧为准，覆盖表单」这个按钮在骗用户（Requirement 1.1）"
        )
    if set(oo_identities) == set(adopt_identities):
        violations.append(
            f"C3 破：两模式的结果行集相等（{sorted(set(oo_identities))}）—— "
            "模式二分不成立。这条同时排掉两种退化：删除侧根本没接（两侧都不删）"
            "与「顺手统一两侧」（两侧都删）"
        )
    return violations


# ═══════════════════════════════════════════════════════════════════════════════
# §3 生成器 + Property 5 本体
# ═══════════════════════════════════════════════════════════════════════════════

#: 本次运行真的出现过的场景（§5 反空转；计数在 tasks.md 登记）。
_SAW: dict[str, int] = {
    "oo_kept_base_only": 0,       # OO 路径**被走过**且真保留了 base 独有身份
    "adopt_deleted_base_only": 0,  # adopt 路径**被走过**且真删掉了 base 独有身份
    "substrate_added_new": 0,      # substrate 声明了 base 没有的新身份并被追加（不止「只删」）
    "section_declared": 0,         # 分区维度被走过（Requirement 1.4 的门真的在场）
    "anchor_indices": 0,           # 锚点位置的覆盖（位掩码，见 §5）
}


@st.composite
def _scenario(draw: st.DrawFn) -> dict[str, Any]:
    """生成 `(base 独有身份, 双方共有身份, substrate 新增身份, 锚点取值)`。

    🔴 `base_only` 的 `min_size=1` 是 Property 5 的**前提**（*For any* 满足「base 独有身份
    非空」）—— 不是为了让判据好过；空集下三条子判据全部平凡成立，测的就是空气。
    🔴 `shared` 与 `added` 不可同时为空：两者全空时 substrate 声明集为空，adopt 侧退化成
    「清空整表」（那是 Requirement 1.3 的边界、已由 Task 4.7 的显式对照单测覆盖），
    在本 property 上会让 C3 变成「非空 vs 空」这种最弱的形态。`pool` 的
    `min_size=3` + `base_only_n ≤ len-2` + `shared_n ≤ len-base_only_n-1` 共同保证 `added` 非空。

    🔴 **锚点下标与分区维度不在这里抽**，改由 pytest 参数化（见 §3 的 `@pytest.mark.parametrize`）：
    它们各只有 4 / 2 种取值，交给 hypothesis 在 `max_examples=5` 下随机抽会让「两维都被走过」
    变成**运气**，§5 的反空转断言随之成为**闪红**判据（铁律 ㉗：红成常态 = 没人看）。
    参数化后两维的覆盖是**结构性保证**而不是概率。
    """
    identity = st.text(alphabet=_IDENTITY_ALPHABET, min_size=1, max_size=8)
    pool = draw(st.lists(identity, min_size=3, max_size=7, unique=True))
    base_only_n = draw(st.integers(min_value=1, max_value=len(pool) - 2))
    shared_n = draw(st.integers(min_value=0, max_value=len(pool) - base_only_n - 1))
    base_only = tuple(pool[:base_only_n])
    shared = tuple(pool[base_only_n : base_only_n + shared_n])
    added = tuple(pool[base_only_n + shared_n :])
    return {
        "base_only": base_only,
        "shared": shared,
        "added": added,
        "anchor_values": draw(
            st.lists(
                st.sampled_from(_NONEMPTY_ANCHORS),
                min_size=len(pool),
                max_size=len(pool),
            )
        ),
    }


def _build(scenario: dict[str, Any]) -> dict[str, Any]:
    """场景 → `(spec, base_rows, projection, declared)`。

    🔴 全部锚点取值从 `_NONEMPTY_ANCHORS` 抽 —— 幽灵行门只对**新增且锚点空**的行生效
    （Property 3 的被测面）。本 property 要测的是模式二分，让幽灵门插进来就分不清
    「行没了是因为 prune 删的」还是「因为门剔的」⇒ 刻意让门**不**触发，并在 §5 钉住这个前提。
    """
    section_field, section_value = ("", "")
    if scenario["declare_section"]:
        section_field, section_value = _usable_section_field(
            tuple(f[0] for f in _MERGE_FIELDS), "rowId"
        )
    spec = _merge_spec(
        anchor_index=scenario["anchor_index"],
        section_field=section_field,
        section_value=section_value,
        table_key=TABLE,
    )
    anchor_key, _path = _anchor_of(spec)
    values = list(scenario["anchor_values"])
    base_rows = [
        _base_row(spec, ident, anchor_value=values[i])
        for i, ident in enumerate((*scenario["base_only"], *scenario["shared"]))
    ]
    # substrate 声明集 = 共有 ∪ 新增（**不含** base 独有 ⇒ 它们正是 adopt 侧该删的）。
    declared = (*scenario["shared"], *scenario["added"])
    projection = _projection(
        spec.table_key,
        [(ident, anchor_key, values[-1], False) for ident in declared],
    )
    return {"spec": spec, "base_rows": base_rows, "projection": projection, "declared": declared}


class TestProperty5ModeDichotomy:
    """**Property 5: 模式二分（OO 不被连带改变）** —— Validates: Requirements 2.1, 2.4"""

    @pytest.mark.parametrize("declare_section", [False, True], ids=["no-section", "sectioned"])
    @pytest.mark.parametrize("anchor_index", range(len(_MERGE_FIELDS)))
    @settings(max_examples=5, deadline=None)
    @given(scenario=_scenario())
    def test_property_5_base_authoritative_keeps_what_substrate_authoritative_drops(
        self, scenario: dict[str, Any], anchor_index: int, declare_section: bool
    ) -> None:
        scenario = {**scenario, "anchor_index": anchor_index, "declare_section": declare_section}
        built = _build(scenario)
        spec = built["spec"]
        base_only = scenario["base_only"]
        oo_rows = run_base_authoritative(
            spec, base_rows=[dict(r) for r in built["base_rows"]], projection=built["projection"]
        )
        adopt_rows, deleted = run_substrate_authoritative(
            spec,
            base_rows=[dict(r) for r in built["base_rows"]],
            projection=built["projection"],
            declared=built["declared"],
        )
        oo_ids = _identities(spec, oo_rows)
        adopt_ids = _identities(spec, adopt_rows)
        assert judge_mode_dichotomy(
            base_only=base_only, oo_identities=oo_ids, adopt_identities=adopt_ids
        ) == [], (
            f"base_only={sorted(base_only)} / OO={sorted(oo_ids)} / adopt={sorted(adopt_ids)} / "
            f"deleted={sorted(deleted)}"
        )
        # ── 反空转前提（不是 Property 5 的子判据，是让三条子判据**有意义**的前提）──
        assert set(built["declared"]) <= set(adopt_ids) or not built["declared"], (
            f"substrate 声明的身份 {sorted(set(built['declared']) - set(adopt_ids))} 在 adopt 结果里"
            "不见了 —— 「覆盖」退化成「清空」，C2 会因此假绿（删光当然删掉了 base 独有身份）"
        )
        assert set(deleted) == set(base_only), (
            f"prune 报删 {sorted(deleted)} ≠ base 独有身份 {sorted(base_only)} —— "
            "多删即越界（兄弟分区/声明行被删）、少删即门失效"
        )
        # ── 累计器（§5 逐项断言 > 0）──
        if set(base_only) <= set(oo_ids):
            _SAW["oo_kept_base_only"] += 1
        if deleted:
            _SAW["adopt_deleted_base_only"] += 1
        if set(scenario["added"]) & set(adopt_ids):
            _SAW["substrate_added_new"] += 1
        if spec.row_section_field:
            _SAW["section_declared"] += 1
        _SAW["anchor_indices"] |= 1 << int(scenario["anchor_index"])


# ═══════════════════════════════════════════════════════════════════════════════
# §4 J3 变异反证 —— 三条子判据必须**各自**能打红（一个变异只红一侧才算分得开）
#
# 🔴 变异全部**进程内源码级**：`inspect.getsource` → 换**唯一**锚点 → 在生产模块 `globals` 的
#    **副本**里 `exec`。生产文件一字不改；不用 `monkeypatch.setattr`（本域有并发会话，
#    即便自动还原，窗口期内也改了共用模块的行为）。
# ═══════════════════════════════════════════════════════════════════════════════

#: 固定场景（变异反证用）—— 不走 hypothesis：变异要的是「同一输入下判据红不红」的对照，
#: 随机输入会让「红了几条」不可复现。
_FIXED = {
    "base_only": ("p5-stale-1", "p5-stale-2"),
    "shared": ("p5-shared",),
    "added": ("p5-new",),
    "anchor_index": 1,
    "declare_section": False,
    "anchor_values": ["华东经销商"] * 6,
}

#: prune 变成**空操作**的锚点（作用域门那一步直接返回）⇒ 模拟「删除侧根本没接」。
_M1_PRUNE_IS_A_NOOP = ("if not in_scope:", "if True:")
#: prune 连**声明了的**行也删 ⇒ 模拟「覆盖退化成清空」（反空转前提要抓的形态）。
_M3_PRUNE_DELETES_DECLARED = (
    "if declared is None or identity in declared:",
    "if declared is None and False:",
)


def _run_pair(*, prune_for_adopt: Any, prune_for_oo: Any = None) -> list[str]:
    """跑一次「两模式对照」并返回判据违规清单。

    `prune_for_oo` 非 None 时表示**模拟泄漏**：base 权威模式也跑了 prune
    （「有人顺手统一两侧」的真实形态）。
    """
    built = _build(dict(_FIXED))
    spec = built["spec"]
    if prune_for_oo is None:
        oo_rows = run_base_authoritative(
            spec, base_rows=[dict(r) for r in built["base_rows"]], projection=built["projection"]
        )
    else:
        oo_rows, _d = run_substrate_authoritative(
            spec,
            base_rows=[dict(r) for r in built["base_rows"]],
            projection=built["projection"],
            declared=built["declared"],
            prune=prune_for_oo,
        )
    adopt_rows, _deleted = run_substrate_authoritative(
        spec,
        base_rows=[dict(r) for r in built["base_rows"]],
        projection=built["projection"],
        declared=built["declared"],
        prune=prune_for_adopt,
    )
    return judge_mode_dichotomy(
        base_only=_FIXED["base_only"],  # type: ignore[arg-type]
        oo_identities=_identities(spec, oo_rows),
        adopt_identities=_identities(spec, adopt_rows),
    )


def _prune_mutant(anchor: tuple[str, str]) -> Any:
    return _source_mutant(prune_undeclared_rows, old=anchor[0], new=anchor[1], module=AOP)


class TestJ3MutationReverseProof:
    def test_control_group_the_production_pair_is_green(self) -> None:
        """对照组：生产的两条序列 ⇒ 三条子判据全绿（red 0）。"""
        assert _run_pair(prune_for_adopt=prune_undeclared_rows) == []

    def test_m1_deletion_side_never_wired_reds_c2_and_c3(self) -> None:
        """M1：prune 变空操作（删除侧没接）⇒ **C2 + C3** 红，**C1 不红**。

        这一条证明 C1 单独立不住 —— 「OO 保留了 base 独有身份」在「谁都不删」时照样成立。
        """
        got = _run_pair(prune_for_adopt=_prune_mutant(_M1_PRUNE_IS_A_NOOP))
        assert len(got) == 2, f"M1 期望恰 2 条（C2 + C3），实得 {got}"
        assert "C2 破" in got[0] and "C3 破" in got[1], got

    def test_m2_leaked_into_the_oo_path_reds_c1_and_c3(self) -> None:
        """M2（**J3 的正题**）：adopt 侧的删除侧**漏进** OO 路径 ⇒ **C1 + C3** 红，**C2 不红**。

        这一条证明 C2 单独立不住 —— 「adopt 删掉了 base 独有身份」在「两侧都删」时照样成立，
        而那正是 Requirement 2.1 明令禁止的后果（OO 每次保存都变成全量覆盖）。
        M1 与 M2 红的是**不同**两条 ⇒ 三条子判据真的分得开。
        """
        got = _run_pair(
            prune_for_adopt=prune_undeclared_rows, prune_for_oo=prune_undeclared_rows
        )
        assert len(got) == 2, f"M2 期望恰 2 条（C1 + C3），实得 {got}"
        assert "C1 破" in got[0] and "C3 破" in got[1], got

    def test_m1_and_m2_red_disjoint_clauses(self) -> None:
        """把「分得开」写成可执行断言：M1 与 M2 的违规集合交集只剩 C3。"""
        m1 = {v.split(" ")[0] for v in _run_pair(prune_for_adopt=_prune_mutant(_M1_PRUNE_IS_A_NOOP))}
        m2 = {
            v.split(" ")[0]
            for v in _run_pair(prune_for_adopt=prune_undeclared_rows, prune_for_oo=prune_undeclared_rows)
        }
        assert m1 & m2 == {"C3"}, f"M1={sorted(m1)} / M2={sorted(m2)} —— 两变异没有各打红一侧"
        assert m1 ^ m2 == {"C1", "C2"}, f"M1={sorted(m1)} / M2={sorted(m2)}"

    def test_m3_overwrite_degenerating_into_wipe_is_caught_by_the_premise(self) -> None:
        """M3：prune 连声明了的行也删（覆盖退化成清空）⇒ 三条子判据**全绿**，前提断言打红。

        🔴 这一条是本 property 最重要的一条自我限制：Property 5 的三句话**抓不住** M3
        （删光当然满足「base 独有身份全消失」且「两侧不相等」）⇒ 必须另配「substrate 声明的
        身份仍在」这条前提。没有 M3 就看不出这个缺口，只会以为三条子判据覆盖了一切。
        """
        mutant = _prune_mutant(_M3_PRUNE_DELETES_DECLARED)
        assert _run_pair(prune_for_adopt=mutant) == [], (
            "M3 被三条子判据抓住了 —— 那 §3 的前提断言就是多余的，本条自我限制的结论需重写"
        )
        built = _build(dict(_FIXED))
        rows, deleted = run_substrate_authoritative(
            built["spec"],
            base_rows=[dict(r) for r in built["base_rows"]],
            projection=built["projection"],
            declared=built["declared"],
            prune=mutant,
        )
        assert not rows and set(deleted) == set(_FIXED["base_only"]) | set(built["declared"]), (
            f"M3 变异体没把整表删光（剩 {len(rows)} 行、删 {sorted(deleted)}）—— 锚点已失效"
        )

    def test_every_mutant_anchor_is_still_unique_in_the_live_source(self) -> None:
        """锚点卫生：两个锚点在**当前** prune 源码里各恰 1 次命中。

        `_source_mutant` 自己也断言 count==1，本条把它前移成独立用例 —— prune 被重构后
        锚点失效时，失败信息应指向「锚点漂了」而不是某条变异「没红」。
        """
        live = inspect.getsource(AOP.prune_undeclared_rows)
        for old, _new in (_M1_PRUNE_IS_A_NOOP, _M3_PRUNE_DELETES_DECLARED):
            assert live.count(old) == 1, f"锚点 {old!r} 命中 {live.count(old)} 次（须恰 1）"


# ═══════════════════════════════════════════════════════════════════════════════
# §5 反空转 —— 两类路径各被走过多少次（现算，禁写死期望次数）
#
# 🔴 类名以 `TestZZ` 开头是刻意的：pytest 默认按**文件内定义序**收集，累计器必须在 §3 的
#    property 跑完之后才有值。域内先例（`test_aos_property_ghost_gate` §6）同一处置。
# ═══════════════════════════════════════════════════════════════════════════════


class TestZZScenarioCoverageIsNotVacuous:
    def test_both_modes_were_really_exercised(self) -> None:
        """「二分」的两侧都必须真的被走过 —— 否则等式在空集上恒真。"""
        assert _SAW["oo_kept_base_only"] > 0, (
            f"OO 路径一次都没保留过 base 独有身份（计数 {_SAW}）—— C1 从未被真正评估"
        )
        assert _SAW["adopt_deleted_base_only"] > 0, (
            f"adopt 路径一次都没删过行（计数 {_SAW}）—— C2 从未被真正评估，"
            "「删除侧根本没接」这种退化本轮测不出来"
        )

    def test_substrate_really_added_rows_not_only_deleted(self) -> None:
        """adopt 侧必须至少一次**真追加**过新身份 —— 否则「覆盖」只测到了「删」这一半。"""
        assert _SAW["substrate_added_new"] > 0, (
            f"substrate 从未追加过 base 没有的新身份（计数 {_SAW}）—— "
            "本轮的 adopt 路径退化成纯删除，追加侧（Requirement 1.5）在本 property 上空转"
        )

    def test_the_partition_dimension_was_exercised(self) -> None:
        """分区门（Requirement 1.4）必须真的出现过 —— `declare_section` 是参数化维度而非随机维度。

        🔴 这条现在是**结构性保证**：`declare_section` 被 `parametrize([False, True])` 钉住
        ⇒ 有分区的那半必然跑过。首版把它交给 `st.booleans()`，那样本条就成了运气驱动的闪红
        判据（5 例全 False 即红），与铁律 ㉗ 冲突 —— 已改。
        """
        assert _SAW["section_declared"] > 0, f"分区维度一次都没出现（计数 {_SAW}）"

    def test_every_anchor_position_was_exercised(self) -> None:
        """四个锚点下标**全部**被走过 —— 同上，`parametrize(range(4))` 的结构性保证。

        锚点位置必须多于一个：恒为 0 时「锚点一律从 `spec.ghost_row_anchor_index` 声明取」
        这条（引擎注释明写 D5/D6 都显式传 1）在本文件上无从体现。
        """
        covered = bin(_SAW["anchor_indices"]).count("1")
        assert covered == len(_MERGE_FIELDS), (
            f"只覆盖了 {covered}/{len(_MERGE_FIELDS)} 个锚点下标"
            f"（位掩码 {bin(_SAW['anchor_indices'])}，计数 {_SAW}）"
        )

    def test_the_ghost_gate_was_deliberately_kept_out_of_the_way(self) -> None:
        """前提登记：本文件所有锚点值取自 `_NONEMPTY_ANCHORS` ⇒ 幽灵行门**不**触发。

        🔴 这不是回避难点，是**隔离变量**：门触发时「行没了」有两个可能成因，C2 就分不清是
        prune 删的还是门剔的。门本身的语义由 Property 3（Task 4.5）测。
        本条断言取值池确实没交集，防止有人往 `_FIXED` 里塞空锚点而不自知。
        """
        assert all(v in _NONEMPTY_ANCHORS for v in _FIXED["anchor_values"]), _FIXED["anchor_values"]
        built = _build(dict(_FIXED))
        oo_rows = run_base_authoritative(
            built["spec"],
            base_rows=[dict(r) for r in built["base_rows"]],
            projection=built["projection"],
        )
        expected = {*_FIXED["base_only"], *_FIXED["shared"], *_FIXED["added"]}
        assert set(_identities(built["spec"], oo_rows)) == expected, (
            f"merge 之后行集 {sorted(set(_identities(built['spec'], oo_rows)))} ≠ 全集 "
            f"{sorted(expected)} —— 有行被幽灵门剔掉了，本文件的前提已破"
        )


@pytest.mark.parametrize("token", ["prune", "overwrite"])
def test_the_oo_runner_really_has_no_deletion_side(token: str) -> None:
    """§1 的 base 权威 runner **自身**不含删除侧 —— 否则 C1 是自证其说。

    🔴 判据落在**本测试文件的 runner 源码**上：它是 C1 的被测对象，若它悄悄调了 prune，
    整条 Property 5 就是在拿 adopt 结果和 adopt 结果比。
    """
    src = inspect.getsource(run_base_authoritative)
    body = src.split('"""')[0] + src.split('"""')[-1]  # 剔掉 docstring（里面有指针说明）
    assert token not in body.lower(), f"base 权威 runner 的代码里出现 {token!r}：{body}"
