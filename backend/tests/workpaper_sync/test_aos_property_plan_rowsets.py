"""adopt 覆盖计划 —— 计划层的**行集 property**（声明侧等式 / 作用域外不变）。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 1.1 / 1.3 / 1.5 · design § Correctness Properties · ADR-AOS-002

本文件承载的 property（**一条一函数**，文件按 property 归集而非按任务归集）：

| Property | 归属任务 | 状态 |
| --- | --- | --- |
| **Property 1: 声明侧行集等式** | Task 4.3 | ✅ 本文件已实现 |
| **Property 2: 作用域外的行逐元素不变** | Task 4.4 | ⬜ 落点在文末分隔线处（**先数行数**，见那里的说明） |

═══ 🔴 Property 1 在**计划期**的可验口径（Task 4.2 的裁定改变了可验范围）═══

design 的 Property 1 原文是「覆盖执行后每个 declared_table 在 store 侧的受管行身份集合 ==
该 table 的 `row_keys` 集合**减去**被幽灵行门剔除的身份集合」。而 Task 4.2
（`adopt_overwrite_compute.compute_overwrite_plan` 的 docstring「🔴 `rows_ghost_dropped` 在计划期
不可兑现」节）已裁定：幽灵行门的三个输入（`spec` + `managed_field_specs` 的锚点 json_path /
merge **之后**的行 / merge 私有的两处 continue）**没有一个**在 `compute_overwrite_plan` 的输入面
上 ⇒ 计划期预测幽灵集合只能复现引擎判据 = 第二真源，已被明确否决。

⇒ 本文件**不复现**幽灵行门，把「减去」这一项拆成两组可验形态：

1. **计划期本体**（`ghost_dropped_by_item` 不传 ⇒ ghost 恒空）：等式退化为
   `declared == rows_added ∪ rows_updated` 且 `rows_deleted == store侧 − declared`，
   并**真按计划应用一次**（production `prune_undeclared_rows` 删 + 按 `rows_added` 追加）后
   重新枚举，断言最终身份集合 `== declared`；
2. **注入 ghost 组**（经 `ghost_dropped_by_item` 喂**观测值**，模拟 Task 6.3 的回喂）：
   断言 `ghost ⊆ rows_added`（Task 4.2 已把「放不进任何分区的 added」实现成当场抛，本文件只验
   它在），应用时不追加被观测为幽灵的身份 ⇒ 最终集合 `== declared − ghost`。

🔴 **建议（不动手改 design，仅提出）**：Property 1 的原文按上述裁定改写为
「*For any* substrate projection 与任意 store 载荷，覆盖执行后每个 declared_table 在 store 侧的
受管行身份集合，应等于该 table 的 `row_keys` 集合减去**被观测到**并经
`ghost_dropped_by_item` 回喂的幽灵身份集合；计划期该集合恒空，故等式退化为
`row_keys == rows_added ∪ rows_updated` 且 `rows_deleted == store 侧 − row_keys`。」
理由 = 原文的「被幽灵行门剔除」读起来像是计划期算得出来的量，而它不是。

═══ P1 与 P3 / P7 不合并（design § prework 合并记录）═══

* 与 **P3**（Task 4.5，幽灵行门语义）不合并：prework 明写「有幽灵行时 P1 的裸『集合相等』
  **不成立**」⇒ 本文件只验「ghost 被减掉后等式成立」与「ghost ⊆ added」，**不**验幽灵门本身
  的判据（锚点为空即剔除 / 已存在的行不受影响）—— 那是 4.5 的事，本文件一个字都不碰；
* 与 **P7**（Task 6.6，应用后重算为空）不合并：本文件应用一次后只断言**身份集合**，
  不重算计划。

═══ 🔴 建造器不复制 ═══

`_spec` / `_readers` / `_row` / `ITEM` / `IDENTITY_KEYS` / `_IDENTITY_ALPHABET` 全部从
`test_aos_property_row_identity` import（Task 3.6 已验证跨文件复用可行）。抄第二份 `_spec()`
就是第二真源 —— 三条 property 的合成 `RowTableSheetSpec` 一漂就在测不同的东西。
import 用**顶层模块名**形态（`backend/tests/workpaper_sync/` 无 `__init__.py` ⇒ pytest 以
`prepend` 模式把该目录塞进 `sys.path`）；写成 `tests.workpaper_sync.…` 会得到**第二个**模块
实例，模块级累计器就会分家。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync.adopt_overwrite_compute import compute_overwrite_plan
from app.services.workpaper_sync.adopt_overwrite_plan import (
    ItemOverwriteDelta,
    OverwritePlanShapeError,
    prune_undeclared_rows,
)

# 🔴 复用 Property 10 文件的建造器（见模块 docstring：禁抄第二份）。
from test_aos_property_row_identity import (  # noqa: E402
    IDENTITY_KEYS,
    ITEM,
    _IDENTITY_ALPHABET,
    _readers,
    _row,
    _spec,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. 三种 declared 形态（Requirement 1.1 本体 + 1.3 边界 + 其「不在键集合」对照）
# ═══════════════════════════════════════════════════════════════════════════

#: `undeclared` 形态里 projection 改去声明的**另一张**表。它不是本 item 的 scope ⇒ 本 item 的
#: table 就落在「不在 `row_keys` 键集合」上（ADR-AOS-002：声明了才动，未声明不碰）。
_OTHER_TABLE = "aos_p1_other_table_rows"

#: declared 维度**穷举**（不抽样）：三者的代码路径不同，抽样会漏。
#:
#: * `partial`        —— 声明集与 store 集**部分**交叠 ⇒ 三清单各自非空（Requirement 1.1 / 1.5）
#: * `empty_declared` —— 在键集合但值为空元组 ⇒ 清空（Requirement 1.3；prework 明写「declared 为空
#:                       ⇒ 结果为空，由 P1 生成器覆盖」）
#: * `undeclared`     —— **不在**键集合 ⇒ 一个字节都不碰。它不是 Property 1 的断言对象，而是
#:                       「空值二分」变异反证的**对照组**：`in` 换成 `.get()` 时本形态会被误当成
#:                       `empty_declared` 而整表清空。🔴 Task 4.7 的显式对照单测仍归 4.7，
#:                       本文件只借它做判据的区分力证明。
DECLARED_MODES: tuple[str, ...] = ("partial", "empty_declared", "undeclared")

#: 本次运行实际出现过「三清单各自非空」的场景（形态, added, deleted, updated 四元组）。
#: 🔴 没有它，等式在空集上恒真 —— 见 :class:`TestPropertyOneJudgeCanBeFalse` 的收口判据。
_NONEMPTY_TRIPLES: list[tuple[str, int, int, int]] = []

#: 变异反证的红数累计器：变异体名 → 判据打红次数。
_MUTANT_REDS: dict[str, int] = {}


def _identities(prefix: str) -> st.SearchStrategy[list[str]]:
    """一桶身份。前缀保证三桶**两两不相交**，且都不可能以 `DECOY-` 起头（前缀全小写）。"""
    return st.lists(
        st.text(alphabet=_IDENTITY_ALPHABET, min_size=1, max_size=8),
        min_size=1,
        max_size=3,
        unique=True,
    ).map(lambda xs: [f"{prefix}{x}" for x in xs])


def _scenario(
    *,
    mode: str,
    both: list[str],
    only_substrate: list[str],
    only_store: list[str],
    identity_key: str,
    as_json_text: bool,
) -> tuple[Any, dict[str, tuple[str, ...]], frozenset[str], frozenset[str] | None]:
    """造 `(store 载荷, row_keys, store 侧身份集, declared)`。`declared is None` = 作用域外。

    store 侧恒为 `both + only_store`（**声明与否不改 store 侧**，这样三种形态共用同一份载荷 ⇒
    「结果不同」只能来自 `row_keys`，不会被载荷差异混淆）。
    """
    spec = _spec(identity_key=identity_key)
    store_ids = [*both, *only_store]
    rows = [_row(identity_key, ident, noise={}, section=("", "")) for ident in store_ids]
    payload: Any = json.dumps(rows, ensure_ascii=False) if as_json_text else rows

    if mode == "partial":
        row_keys = {spec.table_key: tuple([*both, *only_substrate])}
        declared: frozenset[str] | None = frozenset([*both, *only_substrate])
    elif mode == "empty_declared":
        row_keys = {spec.table_key: ()}
        declared = frozenset()
    elif mode == "undeclared":
        row_keys = {_OTHER_TABLE: tuple(only_substrate)}
        declared = None
    else:  # pragma: no cover - 形态域封闭
        raise AssertionError(f"未知 declared 形态 {mode!r}")
    return payload, row_keys, frozenset(store_ids), declared


# ═══════════════════════════════════════════════════════════════════════════
# 2. 「真应用一次」—— 让 property 断言落在**结果行集**上，不只是三清单的并集关系
# ═══════════════════════════════════════════════════════════════════════════


def _rows_of(payload: Any) -> list[Any]:
    """载荷 → 行 list。

    🔴 必须有这一步：`prune_undeclared_rows` **零删除时按字面返回入参对象本身**
    （其 docstring：「零删除时第一个元素是入参对象本身（`is` 相等）」）⇒ 当入参是 JSON 文本时，
    拿回来的也是 JSON 文本而不是 list。
    """
    parsed = json.loads(payload) if isinstance(payload, (str, bytes, bytearray)) else payload
    return list(parsed)


def _apply_overwrite(
    payload: Any,
    *,
    row_keys: Mapping[str, Any],
    reader: Any,
    identity_key: str,
    added: Iterable[str],
    ghosts: Iterable[str] = (),
) -> tuple[frozenset[str], tuple[str, ...]]:
    """按计划应用一次覆盖，返回 `(应用后 store 侧身份集, production 删除侧实际删掉的身份)`。

    两侧都用**生产**代码路径：删除侧是 Task 4.1 的 `prune_undeclared_rows`；追加侧按
    ADR-AOS-001「后置 prune」的真实顺序模型 —— merge 先追加、prune 再剪 —— 在身份集合层面
    等价于「删完再补」，因为 prune 只剪「声明了的 table ∩ 声明了的分区」里**未声明**的身份，
    而追加的恰是已声明身份，两步不会互相吃掉。

    🔴 `ghosts` 里的身份**不追加** —— 这是对幽灵行门的**观测结果**建模，不是复现它的判据
    （Task 4.2 裁定：门的三个输入都不在计划期的输入面上）。
    """
    kept, deleted = prune_undeclared_rows(payload, row_keys=row_keys, reader=reader)
    rows = _rows_of(kept)
    for identity in sorted(set(added) - set(ghosts)):
        rows.append(_row(identity_key, identity, noise={}, section=("", "")))
    return frozenset(identity for identity, _row_obj in reader.iter_rows(rows)), deleted


def _deltas_for(
    deltas: Iterable[ItemOverwriteDelta], *, item_id: str, table_key: str
) -> list[ItemOverwriteDelta]:
    return [d for d in deltas if d.item_id == item_id and d.table_key == table_key]


def _assert_property_1(
    *,
    label: str,
    deltas: Iterable[ItemOverwriteDelta],
    applied_identities: frozenset[str],
    store_identities: frozenset[str],
    declared: frozenset[str] | None,
    table_key: str,
    ghosts: frozenset[str] = frozenset(),
    item_id: str = ITEM,
) -> ItemOverwriteDelta | None:
    """Property 1 的**唯一**判据实现。变异体喂进来必须打红（`AssertionError`）。

    `declared is None` ⇒ 作用域外：断言**没有** delta 且结果行集逐元素不变。
    其余 ⇒ 五条等式 + 「ghost ⊆ added」+ 结果行集 == `declared − ghosts`。
    """
    mine = _deltas_for(deltas, item_id=item_id, table_key=table_key)
    if declared is None:
        assert not mine, (
            f"{label}：table {table_key!r} **不在** `row_keys` 键集合里却产出了 {len(mine)} 条 "
            f"delta（rows_deleted={[d.rows_deleted for d in mine]}）—— 作用域门失效"
            "（ADR-AOS-002 / Requirement 1.2）。🔴 最典型的成因是把 `in` 判键集合换成了 "
            "`.get(table_key) or ()`，那会把「未声明」压成「声明为空」而整表清空"
        )
        assert applied_identities == store_identities, (
            f"{label}：作用域外的表被改动了 —— 应用后 {sorted(applied_identities)} != "
            f"应用前 {sorted(store_identities)}"
        )
        return None

    assert len(mine) == 1, (
        f"{label}：declared_table {table_key!r} 应恰有 1 条 delta，实得 {len(mine)} 条"
    )
    delta = mine[0]
    added = frozenset(delta.rows_added)
    deleted = frozenset(delta.rows_deleted)
    updated = frozenset(delta.rows_updated)

    # ① 声明侧行集等式本体（Requirement 1.1 + 1.5：集合相等蕴含「缺的必须被追加」）
    assert added | updated == declared, (
        f"{label}：`rows_added ∪ rows_updated` = {sorted(added | updated)} != declared "
        f"{sorted(declared)} —— 声明侧等式破（只在声明里 {sorted(declared - (added | updated))}；"
        f"只在计划里 {sorted((added | updated) - declared)}）"
    )
    # ② 三清单按「两侧各有无」互斥定义 —— 这三条钉住「算反了」与「不看 substrate」
    assert added == declared - store_identities, (
        f"{label}：rows_added = {sorted(added)} != declared − store = "
        f"{sorted(declared - store_identities)}"
    )
    assert updated == declared & store_identities, (
        f"{label}：rows_updated = {sorted(updated)} != declared ∩ store = "
        f"{sorted(declared & store_identities)}"
    )
    assert deleted == store_identities - declared, (
        f"{label}：rows_deleted = {sorted(deleted)} != store − declared = "
        f"{sorted(store_identities - declared)}"
    )
    # ③ 幽灵是 added 的子集（Task 4.2 的连带后果，design ADR 与 Property 3 同一表述）
    assert ghosts <= added, (
        f"{label}：被观测的幽灵身份 {sorted(ghosts - added)} 不在 rows_added 里 —— "
        "幽灵行门只对**本次新增**的身份生效"
    )
    # ④ 结果行集（property 原文的断言对象）
    assert applied_identities == declared - ghosts, (
        f"{label}：应用后 store 侧身份集 {sorted(applied_identities)} != declared − ghost "
        f"{sorted(declared - ghosts)}"
    )
    return delta


# ═══════════════════════════════════════════════════════════════════════════
# 3. Property 1（Task 4.3）
# ═══════════════════════════════════════════════════════════════════════════


def _plan_for(
    *, row_keys: Mapping[str, Any], payload: Any, reader: Any, ghosts: Iterable[str] = ()
) -> Any:
    """跑生产计划函数。`ghosts` 非空即模拟 Task 6.3 的 `ghost_dropped_by_item` 回喂。"""
    kwargs: dict[str, Any] = {}
    if ghosts:
        kwargs["ghost_dropped_by_item"] = {ITEM: tuple(ghosts)}
    return compute_overwrite_plan(
        substrate_projection=SimpleNamespace(row_keys=dict(row_keys)),
        store_payloads={ITEM: payload},
        row_readers={ITEM: reader},
        **kwargs,
    )


class TestProperty1DeclaredRowSetEquality:
    """Property 1：覆盖后每个 declared_table 的 store 侧身份集 == `row_keys` 集合 − 幽灵集。"""

    @pytest.mark.parametrize("mode", DECLARED_MODES)
    @settings(max_examples=5, deadline=None)
    @given(
        both=_identities("upd-"),
        only_substrate=_identities("add-"),
        only_store=_identities("del-"),
        as_json_text=st.booleans(),
        key_pick=st.integers(min_value=0, max_value=len(IDENTITY_KEYS) * 3),
    )
    def test_property_1_declared_row_set_equality(
        self,
        mode: str,
        both: list[str],
        only_substrate: list[str],
        only_store: list[str],
        as_json_text: bool,
        key_pick: int,
    ) -> None:
        """Feature: workpaper-sync-adopt-overwrite-and-refresh-source, Property 1: 声明侧行集等式

        **Validates: Requirements 1.1, 1.3, 1.5**

        随机维度：三桶身份取值（含 `/` 与中文，互不相交）、载荷是 JSON 文本还是已解析序列
        （引擎两条入口分支都要走到）、身份键取值。declared 形态维度**穷举**（3 种），
        `RowReader` 实现维度**穷举**（3 个）⇒ 9 格矩阵。

        每格都**真按计划应用一次**（production `prune_undeclared_rows` + 按 `rows_added` 追加），
        再重新枚举结果行集 —— 这样断言才落在 property 原文说的「覆盖执行后 store 侧的受管行身份
        集合」上，而不只是三清单之间的并集关系（后者对恒返回空计划的实现可能部分为真）。
        """
        identity_key = IDENTITY_KEYS[key_pick % len(IDENTITY_KEYS)]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _scenario(
            mode=mode,
            both=both,
            only_substrate=only_substrate,
            only_store=only_store,
            identity_key=identity_key,
            as_json_text=as_json_text,
        )
        for reader_label, reader in _readers(spec):
            where = f"{reader_label} / 形态 {mode} / 键名 {identity_key!r}"
            plan = _plan_for(row_keys=row_keys, payload=payload, reader=reader)
            mine = _deltas_for(plan.deltas, item_id=ITEM, table_key=spec.table_key)
            applied, deleted_ids = _apply_overwrite(
                payload,
                row_keys=row_keys,
                reader=reader,
                identity_key=identity_key,
                added=mine[0].rows_added if len(mine) == 1 else (),
            )
            delta = _assert_property_1(
                label=where,
                deltas=plan.deltas,
                applied_identities=applied,
                store_identities=store_ids,
                declared=declared,
                table_key=spec.table_key,
            )
            # 🔴 计划与**真删除**的交叉对账：计划报的 rows_deleted 必须就是 prune 实际删掉的。
            #    少了这条，「计划算对了但删除侧没照它执行」在本 property 里不可见。
            expected_deleted = () if delta is None else delta.rows_deleted
            assert deleted_ids == tuple(sorted(expected_deleted)), (
                f"{where}：prune 实际删掉 {list(deleted_ids)} != 计划报的 "
                f"{sorted(expected_deleted)}"
            )
            if delta is not None:
                assert plan.substrate_rows_by_table[spec.table_key] == len(declared or ()), (
                    f"{where}：substrate_rows_by_table 与 declared 集合大小不等"
                )
                if delta.rows_added and delta.rows_deleted and delta.rows_updated:
                    _NONEMPTY_TRIPLES.append(
                        (
                            mode,
                            delta.rows_added_count,
                            delta.rows_deleted_count,
                            delta.rows_updated_count,
                        )
                    )

    @pytest.mark.parametrize("reader_index", range(3))
    def test_property_1_holds_when_ghost_identities_are_observed(self, reader_index: int) -> None:
        """注入组：经 `ghost_dropped_by_item` 喂**观测值** ⇒ 等式变成 `declared − ghost`。

        这是 Property 1「减去被幽灵行门剔除的身份集合」在计划期唯一可验的形态（裁定见模块
        docstring）。同时钉住 Task 4.2 的连带后果 `ghost ⊆ rows_added`。
        """
        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _scenario(
            mode="partial",
            both=["upd-a1", "upd-b2"],
            only_substrate=["add-x1", "add-y2", "add-运输费用"],
            only_store=["del-z9"],
            identity_key=identity_key,
            as_json_text=reader_index % 2 == 0,
        )
        assert declared is not None
        reader_label, reader = _readers(spec)[reader_index]
        ghosts = frozenset({"add-y2", "add-运输费用"})  # ⊂ rows_added（substrate 有 / store 无）
        plan = _plan_for(row_keys=row_keys, payload=payload, reader=reader, ghosts=ghosts)
        mine = _deltas_for(plan.deltas, item_id=ITEM, table_key=spec.table_key)
        assert len(mine) == 1
        assert frozenset(mine[0].rows_ghost_dropped) == ghosts, mine[0].rows_ghost_dropped
        applied, _deleted = _apply_overwrite(
            payload,
            row_keys=row_keys,
            reader=reader,
            identity_key=identity_key,
            added=mine[0].rows_added,
            ghosts=ghosts,
        )
        _assert_property_1(
            label=f"{reader_label} / ghost 注入",
            deltas=plan.deltas,
            applied_identities=applied,
            store_identities=store_ids,
            declared=declared,
            table_key=spec.table_key,
            ghosts=ghosts,
        )
        # 🔴 裸「集合相等」在有幽灵时**不成立** —— prework「P1 与 P3 不合并」那一行的直接实证。
        assert applied != declared, (
            "注入的幽灵身份一个都没被减掉 ⇒ 本判据退化成计划期本体，注入组失去意义"
        )

    @pytest.mark.parametrize(
        "ghost_identity, why",
        [
            ("del-z9", "store 侧独有（属 rows_deleted）"),
            ("upd-a1", "两侧都有（属 rows_updated）"),
            ("ghost-不存在于任何一侧", "凭空的身份"),
        ],
    )
    def test_ghost_outside_rows_added_is_rejected(self, ghost_identity: str, why: str) -> None:
        """🔴 观测到的幽灵身份放不进任何分区的 `rows_added` ⇒ Task 4.2 必须当场抛。

        本任务只验它**在**（实现属 4.2）。它是「幽灵行门语义已变」的唯一哨兵：静默吞掉就会让
        dry_run 报出一份永远执行不了的计划。
        """
        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, _store_ids, _declared = _scenario(
            mode="partial",
            both=["upd-a1"],
            only_substrate=["add-x1"],
            only_store=["del-z9"],
            identity_key=identity_key,
            as_json_text=False,
        )
        _label, reader = _readers(spec)[0]
        with pytest.raises(OverwritePlanShapeError) as excinfo:
            _plan_for(
                row_keys=row_keys, payload=payload, reader=reader, ghosts=(ghost_identity,)
            )
        message = str(excinfo.value)
        assert ITEM in message and ghost_identity in message, (
            f"{why}：异常消息里既要有 item_id 又要有那个身份，实得 {message[:200]!r}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. 正面判据 —— 三清单**各自非空**（否则等式在空集上恒真）
# ═══════════════════════════════════════════════════════════════════════════

#: 三清单各自非空的确定性场景。三桶都给 2 条 ⇒ added / deleted / updated 各 2。
_TRIPLE_BOTH = ["upd-a1", "upd-b2"]
_TRIPLE_ONLY_SUBSTRATE = ["add-x1", "add-y2"]
_TRIPLE_ONLY_STORE = ["del-z9", "del-运输费用"]


def _triple_scenario(identity_key: str, *, mode: str = "partial", as_json_text: bool = False):
    return _scenario(
        mode=mode,
        both=list(_TRIPLE_BOTH),
        only_substrate=list(_TRIPLE_ONLY_SUBSTRATE),
        only_store=list(_TRIPLE_ONLY_STORE),
        identity_key=identity_key,
        as_json_text=as_json_text,
    )


class TestNonEmptyTripleIsExercised:
    """确定性正面场景：三清单各自非空，且等式仍成立。"""

    @pytest.mark.parametrize("reader_index", range(3))
    def test_all_three_lists_are_non_empty_and_equality_holds(self, reader_index: int) -> None:
        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _triple_scenario(identity_key)
        reader_label, reader = _readers(spec)[reader_index]
        plan = _plan_for(row_keys=row_keys, payload=payload, reader=reader)
        (delta,) = _deltas_for(plan.deltas, item_id=ITEM, table_key=spec.table_key)
        assert (
            delta.rows_added_count == len(_TRIPLE_ONLY_SUBSTRATE)
            and delta.rows_deleted_count == len(_TRIPLE_ONLY_STORE)
            and delta.rows_updated_count == len(_TRIPLE_BOTH)
        ), (
            f"{reader_label}：三清单实测 added={delta.rows_added_count} / "
            f"deleted={delta.rows_deleted_count} / updated={delta.rows_updated_count} —— "
            "任一为 0 都会让「declared == added ∪ updated」这条等式变成空集上的恒真式"
        )
        applied, _deleted = _apply_overwrite(
            payload,
            row_keys=row_keys,
            reader=reader,
            identity_key=identity_key,
            added=delta.rows_added,
        )
        _assert_property_1(
            label=f"{reader_label} / 三清单非空",
            deltas=plan.deltas,
            applied_identities=applied,
            store_identities=store_ids,
            declared=declared,
            table_key=spec.table_key,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. 变异反证 —— 判据必须能为 False（三组，各自独立打红）
# ═══════════════════════════════════════════════════════════════════════════


def _expect_red(name: str, run: Any) -> AssertionError:
    """跑变异体，要求判据**打红**；红了就记一次。"""
    with pytest.raises(AssertionError) as excinfo:
        run()
    _MUTANT_REDS[name] = _MUTANT_REDS.get(name, 0) + 1
    return excinfo.value


class TestPropertyOneJudgeCanBeFalse:
    """三个变异体各自对应一类真实可能的实现错误，判据必须逐个打红。"""

    @pytest.mark.parametrize("reader_index", range(3))
    def test_m1_added_and_deleted_swapped_is_caught(self, reader_index: int) -> None:
        """M1：把 `rows_added` 与 `rows_deleted` 算反 —— 覆盖侧最危险的一种错位。"""
        from dataclasses import replace

        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _triple_scenario(identity_key)
        reader_label, reader = _readers(spec)[reader_index]
        plan = _plan_for(row_keys=row_keys, payload=payload, reader=reader)
        (truth,) = _deltas_for(plan.deltas, item_id=ITEM, table_key=spec.table_key)
        applied, _deleted = _apply_overwrite(
            payload,
            row_keys=row_keys,
            reader=reader,
            identity_key=identity_key,
            added=truth.rows_added,
        )
        # 对照组：生产计划在同一坐标下必须通过（否则下面的红没有意义）。
        _assert_property_1(
            label=f"{reader_label} / M1 对照组",
            deltas=plan.deltas,
            applied_identities=applied,
            store_identities=store_ids,
            declared=declared,
            table_key=spec.table_key,
        )
        mutant = replace(truth, rows_added=truth.rows_deleted, rows_deleted=truth.rows_added)
        _expect_red(
            "M1_added_deleted_swapped",
            lambda: _assert_property_1(
                label=f"{reader_label} / M1 算反",
                deltas=(mutant,),
                applied_identities=applied,
                store_identities=store_ids,
                declared=declared,
                table_key=spec.table_key,
            ),
        )

    @pytest.mark.parametrize("reader_index", range(3))
    def test_m2_declared_taken_from_store_side_is_caught(self, reader_index: int) -> None:
        """M2：declared 集合换成「store 侧集合」（即不看 substrate）⇒ 覆盖变成恒等变换。

        这是「adopt 只更新字段、行还是原来那些」那条上游缺陷的计划期形态：三清单变成
        `added=∅ / deleted=∅ / updated=store`，看上去自洽，但 substrate 独有的行一条都不追加。
        """
        from dataclasses import replace

        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _triple_scenario(identity_key)
        reader_label, reader = _readers(spec)[reader_index]
        plan = _plan_for(row_keys=row_keys, payload=payload, reader=reader)
        (truth,) = _deltas_for(plan.deltas, item_id=ITEM, table_key=spec.table_key)
        mutant = replace(
            truth, rows_added=(), rows_deleted=(), rows_updated=tuple(sorted(store_ids))
        )
        # 变异体的「应用」也按它自己的计划走：什么都不删、什么都不追加 ⇒ store 侧原样。
        _expect_red(
            "M2_declared_from_store_side",
            lambda: _assert_property_1(
                label=f"{reader_label} / M2 不看 substrate",
                deltas=(mutant,),
                applied_identities=store_ids,
                store_identities=store_ids,
                declared=declared,
                table_key=spec.table_key,
            ),
        )

    @pytest.mark.parametrize("reader_index", range(3))
    def test_m3_get_instead_of_in_is_caught(self, reader_index: int) -> None:
        """M3：空值二分踩错 —— `table_key in row_keys` 换成 `.get(table_key) or ()`。

        后果：**未声明**的表被压成「声明为空」⇒ 整表清空。本 spec 唯一破坏性路径上最严重的
        一种错（ADR-AOS-002 / Requirement 1.2）。变异体的删除侧也按 `.get()` 的语义真跑一遍
        production `prune_undeclared_rows`（喂 `{table: ()}` 正是那个塌缩结果）⇒ 判据在
        「产出了 delta」与「作用域外被改动」两处都该红。
        """
        identity_key = IDENTITY_KEYS[0]
        spec = _spec(identity_key=identity_key)
        payload, row_keys, store_ids, declared = _triple_scenario(
            identity_key, mode="undeclared"
        )
        assert declared is None and spec.table_key not in row_keys
        reader_label, reader = _readers(spec)[reader_index]
        # 对照组：生产实现对未声明的表既不产 delta 也不删一行。
        plan = _plan_for(row_keys=row_keys, payload=payload, reader=reader)
        applied, deleted_ids = _apply_overwrite(
            payload, row_keys=row_keys, reader=reader, identity_key=identity_key, added=()
        )
        assert deleted_ids == () and applied == store_ids
        _assert_property_1(
            label=f"{reader_label} / M3 对照组",
            deltas=plan.deltas,
            applied_identities=applied,
            store_identities=store_ids,
            declared=declared,
            table_key=spec.table_key,
        )
        # 变异体：`.get()` 塌缩后的真实行为。
        mutant_applied, mutant_deleted = _apply_overwrite(
            payload,
            row_keys={spec.table_key: ()},
            reader=reader,
            identity_key=identity_key,
            added=(),
        )
        assert mutant_applied == frozenset() and len(mutant_deleted) == len(store_ids), (
            f"{reader_label}：`.get()` 塌缩后竟没有清空整表（删 {len(mutant_deleted)} 行 / "
            f"剩 {sorted(mutant_applied)}）—— 变异体没造出它要模拟的危害，反证前提已变"
        )
        mutant_delta = ItemOverwriteDelta(
            item_id=ITEM,
            table_key=spec.table_key,
            rows_deleted=tuple(sorted(store_ids)),
        )
        _expect_red(
            "M3_get_instead_of_in",
            lambda: _assert_property_1(
                label=f"{reader_label} / M3 空值二分踩错",
                deltas=(mutant_delta,),
                applied_identities=mutant_applied,
                store_identities=store_ids,
                declared=declared,
                table_key=spec.table_key,
            ),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 收口判据（定义在最后 ⇒ 上面的 property 与变异组已跑过）
# ═══════════════════════════════════════════════════════════════════════════

#: 变异组名 → 期望红数。🔴 期望值**由参数化推导**（reader 实现数），不写死。
_MUTANT_GROUPS: tuple[str, ...] = (
    "M1_added_deleted_swapped",
    "M2_declared_from_store_side",
    "M3_get_instead_of_in",
)


class TestJudgesAreNotVacuous:
    """判据不是恒真：三个变异组都真的被打红，且随机跑里出现过三清单非空的场景。"""

    def test_every_mutant_group_was_caught(self) -> None:
        """🔴 **不 skip**：累计器空时自己把三组跑满。

        本仓装了 `pytest-randomly` ⇒ 用例顺序会被打乱，本判据若靠「排在变异组之后」就会时不时
        变成 skip，而 skip 掉的收口判据等于没有（平台铁律㉗「有门禁 ≠ 门禁生效」）。
        """
        expected = len(_readers(_spec(identity_key=IDENTITY_KEYS[0])))
        before = dict(_MUTANT_REDS)
        mutants = TestPropertyOneJudgeCanBeFalse()
        for index in range(expected):
            mutants.test_m1_added_and_deleted_swapped_is_caught(index)
            mutants.test_m2_declared_taken_from_store_side_is_caught(index)
            mutants.test_m3_get_instead_of_in_is_caught(index)
        gained = {
            name: _MUTANT_REDS.get(name, 0) - before.get(name, 0) for name in _MUTANT_GROUPS
        }
        assert all(gained[name] == expected for name in _MUTANT_GROUPS), (
            f"本判据自跑一轮实得红数 {gained}，应逐个等于 reader 实现数 {expected} —— "
            "某一组没打满（= 那类实现错误对 Property 1 至少在一个 reader 上不可见）"
        )
        assert set(_MUTANT_REDS) == set(_MUTANT_GROUPS), (
            f"变异组累计 {sorted(_MUTANT_REDS)} != 登记的 {list(_MUTANT_GROUPS)}"
        )

    def test_random_run_exercised_a_non_empty_triple(self) -> None:
        """随机维度里也出现过三清单各自非空（确定性正面场景另有 :class:`TestNonEmptyTripleIsExercised`）。"""
        if not any(mode == "partial" for mode, *_rest in _NONEMPTY_TRIPLES):
            pytest.skip(
                "本次选择未执行 Property 1 的 partial 形态（如 -k 定向）⇒ 累计器为空"
            )
        assert _NONEMPTY_TRIPLES, "累计器为空"
        assert all(a and d and u for _mode, a, d, u in _NONEMPTY_TRIPLES), _NONEMPTY_TRIPLES

    def test_identity_buckets_are_pairwise_disjoint_by_construction(self) -> None:
        """三桶前缀互不相交，且都不可能撞 `_row` 布下的 `DECOY-` 诱饵值（前缀全小写）。"""
        buckets = (_TRIPLE_BOTH, _TRIPLE_ONLY_SUBSTRATE, _TRIPLE_ONLY_STORE)
        flat = [x for bucket in buckets for x in bucket]
        assert len(set(flat)) == len(flat), flat
        assert not any(x.startswith("DECOY-") for x in flat), flat
        assert "D" not in _IDENTITY_ALPHABET, (
            "身份字符集混进了大写 D ⇒ 随机身份有可能长成 `DECOY-…`，诱饵判据失去区分力"
        )


# ── Property 2（Task 4.4）落点 ────────────────────────────────────────────────
#
# **Property 2: 作用域外的行逐元素不变**（Validates: Requirements 1.2, 1.4），两维参数化：
#   (a) `table_key` 不在 `row_keys` 键集合中的表；(b) 同一载荷内不属本次声明分区的行。
#
# 🔴 **落点先数行数再决定**：本文件交付 Task 4.3 后已接近 `.py` 门禁 **800**
#    （`backend/scripts/check/check_file_size.py` 的 `LIMITS`，pre-commit 与 CI 的
#    `file-size-guard` 同源）。判据 = `python backend/scripts/check/check_file_size.py <文件>`
#    exit=0。越界就抽伴生文件（域内已有四次同样处置：`phase5_g9_store_facade.py` /
#    `adopt_row_reader.py` / `adopt_row_reader_r3.py` / `adopt_overwrite_compute.py`，
#    测试侧一次：`test_aos_property_unreadable_payload.py`），并在被切的一侧留指针注释。
#    🔴 行数本身不写进注释 —— 那是自指计数，每次编辑都会过期。
#
# **可直接复用的建造器（都在本文件里，禁抄第二份）**：
#   * `_identities(prefix)`   —— 一桶互不相交的随机身份（前缀保证跨桶不撞、不撞 `DECOY-`）
#   * `_scenario(...)`        —— `(载荷, row_keys, store 侧身份集, declared)`；其 `undeclared`
#                                形态**正是** Property 2 的 (a) 维（本文件只把它当变异反证的
#                                对照组用，没有断言「逐元素」相等 —— 那是 4.4 要补的）
#   * `_rows_of` / `_apply_overwrite` —— 按计划真应用一次（production prune + 追加）
#   * `_plan_for(...)`        —— 跑 `compute_overwrite_plan`（可选 `ghosts` 回喂）
#   * `_deltas_for(...)`      —— 按 `(item_id, table_key)` 取 delta
#   * `_expect_red(name, run)` / `_MUTANT_REDS` —— 变异反证的红数累计（收口判据会核对）
#
# 🔴 **4.4 必须自己补的两件事**（本文件刻意没做）：
#   1. **分区维**：本文件全部用 `section_field=""` 的 spec（单桶 `None`），分区门一个字都没测。
#      4.4 要用 `_spec(identity_key=…, section_field=…, section_value=…)` 造多分区，并注意
#      `_readers` 生成的 `declared_scopes` 只含**一个** scope ⇒ 兄弟分区要另造 reader；
#      分区字段名须取自**声明**（`test_aos_property_row_identity.declared_section_fields()`），
#      禁硬编码（含 `"section"`）。
#   2. **逐元素**（不是集合）：Property 2 原文要的是「身份**序列**逐元素相等」，本文件的判据
#      一律是集合相等 ⇒ 顺序变化在这里不可见。
#
# 🔴 **不要动 `_assert_property_1`**：它是 Property 1 的唯一判据，变异反证按它的红数收口；
#    Property 2 请另写自己的判据函数。
