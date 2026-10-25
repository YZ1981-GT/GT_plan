"""Task 6.6 判据：**Property 7** —— 应用一次覆盖之后，以同一 substrate projection 重算的收敛形态。

spec: workpaper-sync-adopt-overwrite-and-refresh-source
Requirements 3.8 · design § Correctness Properties / Property 7 ·
ADR-AOS-001（后置 prune）· ADR-AOS-003（dry_run 与真实执行共用同一计划纯函数）

═══ 🔴 裁定：design 的 Property 7 逐字文本**只在平凡输入上成立**，本文件按域重述 ═══

design 原文：「按 Overwrite_Plan 应用一次之后……其 `rows_added` / `rows_deleted` /
`rows_updated` 三个清单均为空」。**现算实测**（探针 5 场景，逐值见 tasks.md 6.6）发现**两处**
与逐字文本不符 —— 不是一处：

1. **幽灵行让 `rows_added` 必然非空**（本任务被交办时已点明的那处张力）：被幽灵行门剔除的身份
   substrate 声明了它、store 里始终没有 ⇒ 重算时它**再次**落进 `rows_added`。
2. 🔴 **`rows_updated` 在收敛后恒等于「全部受管行」，与幽灵毫无关系**（这一处是本轮现算新发现）：
   `rows_updated` 的定义是 `declared ∩ store_ids`（「两侧都有 ⇒ 字段以 substrate 为权威更新」），
   而收敛的**含义就是**两侧行集一致 ⇒ 收敛后 `rows_updated == declared − ghost`。
   ⇒ 「三个清单均为空」当且仅当 `declared` 为空（探针 5 场景里唯一满足逐字文本的就是
   `declared=()` 那一例）。**把生成器调成只产空 projection 就能让逐字文本全绿** —— 这正是
   本任务明令禁止的蒙绿形态，所以照抄逐字文本不是「更严」而是**必然落进平凡输入**。

**选择的处置 = 交办的第 3 条（按域断言），并把它扩到覆盖第 2 处偏差**（交办原文的第 3 条写的是
「`rows_deleted` / `rows_updated` 为空」—— 其中 `rows_updated` 那一半与第 2 处偏差同样不可满足,
故不能照抄）。落地的四条断言：

| 断言 | 形态 | 它在防什么 |
| --- | --- | --- |
| C1 | `rows_deleted == ∅` | 删除侧**真落库**了（计划报了删而库里没删 ⇒ 这里非空） |
| C2 | `rows_added == 上一轮登记的 rows_ghost_dropped`（**等式**，比 ⊆ 强） | 「还差的行」恰好只有登记过的幽灵；多一个都是漏写，少一个都是漏登记 |
| C3 | `rows_updated == declared − rows_ghost_dropped` | **正面形态**：收敛后的受管行集逐值钉死 ⇒ 这一条才证明「该追加的真的追加上了」 |
| C4 | 第三次重算与第二次逐值相等 + digest 相等 | 不动点（「再跑不再有动作」的可执行含义） |

🔴 **C3 不是把「为空」降级** —— 逐字文本在非平凡输入上无解，「为空」在那里不是更严的判据而是
**假的**判据；C3 钉死的是集合的**确切内容**，比任何一条单侧不等式都强。对 design 的改写建议
（不直接改 design）登记在 tasks.md 6.6 条目下。

🔴 **Requirement 3.8 原文支持这个处置**（逐字引）：「THE Test_Suite SHALL 用真实 PostgreSQL 做
对账：同一 substrate 与同一 store 版本下，dry_run 报出的三个身份清单与真实执行后实际落库的三个
身份清单逐元素相等」—— 它要的是「计划与落库一致」，**没有**要求「重算为空」；而
`adopt_overwrite_compute.compute_overwrite_plan` 的 docstring 末节已把这条 AC 的对账口径显式裁定
为「须按 `rows_added − rows_ghost_dropped` 对账（与 Property 1 的「减去被幽灵行门剔除的身份集合」
同一表述）」。⇒ 按域重述与 Requirement 3.8 + 域内既有裁定同向，不是判据的让步。
（Requirement 3.8 逐字要的**真实 PostgreSQL 对账**归 Task 8.5；本文件是它的纯函数层前哨。）

═══ 本文件的另一半身份：**6.6 与 6.7 共用的场景建造器** ═══

`Scenario` / `build_scenario` / `run_overwrite_once` / `CORPUS` 供
`test_aos_property_rollback_roundtrip.py`（Task 6.7 / Property 11）import ——「跑一遍覆盖」的
脚手架只有一份。🔴 用**顶层模块名** import（该目录无 `__init__.py`、pytest 走 `prepend`；写成
`tests.workpaper_sync.…` 会拿到第二个模块实例）。

🔴 **工具与桩从 `test_aos_adopt_plan_wiring.py` / `…_deletion_apply_and_verify.py` import，不另造
第二份**：`_source_mutant` / `_StubReader` / `_projection` / `_IDENTITY_KEY` / `_FakeSession`。

🔴 **变异一律进程内源码级**（`inspect.getsource` → 换**唯一**锚点 → 在生产模块 `globals` 的
**副本**里 `exec`），生产文件一字不改，也不用 `monkeypatch.setattr`（本域有并发会话）。

🔴 **作用域外行的不变性不在本文件**：那是 Property 2（`test_aos_property_out_of_scope_rows.py`
+ `…_out_of_scope_mutants.py`）的主场，本文件的场景刻意只造**单分区**以免与它重复造第二套判据。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Mapping

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from app.services.workpaper_sync import adopt_overwrite_apply as AOA
from app.services.workpaper_sync import adopt_substrate_response as ASR
from app.services.workpaper_sync.adopt_overwrite_plan import OverwritePlan, SkipReason

from test_aos_adopt_plan_wiring import (  # noqa: E402
    _IDENTITY_KEY,
    _StubReader,
    _projection,
    _source_mutant,
)
from test_aos_deletion_apply_and_verify import _FakeSession  # noqa: E402

#: 本文件的 item 分母：一条可枚举行数组 item + 一条**被跳过**的 dict 形态 item。
#: 🔴 被跳过的那条是刻意常驻的：Task 6.7 的 round-trip 覆盖面必须包含它（回滚快照的并集口径
#:    正是为它而设），而 Property 7 侧它顺带证明「跳过的 item 不破坏收敛」。
ITEM = "AOS66-rows"
BLIND = "AOS66-blind"
TABLE = "aos66_rows"
#: 受管字段：merge 会把它按 substrate 权威改写（store 侧原值与 substrate 值刻意不同）。
NAME_FIELD = "rowName"
_SUBSTRATE_NAME = "在线编辑侧-{}"
_STORE_NAME = "表单旧值-{}"
#: 被跳过 item 的覆盖前原值（紧凑形态，与 `json.dumps(..., ensure_ascii=False)` 的带空格形态
#: 逐字节不同 —— 真库 200 条大载荷里 155 条「重序列化即漂移」的同一形态）。
BLIND_BEFORE = '{"answer":"覆盖前的原值","n":1}'


# ═══════════════════════════════════════════════════════════════════════════════
# 场景：三个身份集合（store 侧 / substrate 声明 / 被幽灵门剔除）+ 一条被跳过 item
# ═══════════════════════════════════════════════════════════════════════════════


class Scenario:
    """一次覆盖的输入。**普通类不是 dataclass**（同域内 `AdoptPlanInputs` / `AppliedOverwrite`）。

    :param store_ids: 覆盖前 store 侧已有的行身份（有序，字节形态按此顺序）。
    :param declared_ids: substrate projection 为 :data:`TABLE` 声明的行身份。
    :param ghost_ids: `declared − store` 里**锚点业务名为空**因而会被既有幽灵行门剔除的那些。
        🔴 必须 ⊆ `declared − store`（幽灵门只对**本次新增**生效，引擎明写「已存在的行永不受
        影响」）—— 构造器当场校验，不静默归一。
    """

    __slots__ = ("store_ids", "declared_ids", "ghost_ids")

    def __init__(
        self,
        *,
        store_ids: tuple[str, ...],
        declared_ids: tuple[str, ...],
        ghost_ids: tuple[str, ...] = (),
    ) -> None:
        illegal = set(ghost_ids) - (set(declared_ids) - set(store_ids))
        assert not illegal, (
            f"ghost_ids {sorted(illegal)} 不在 `declared − store` 里 —— 幽灵门只对本次新增生效，"
            "这种场景造出来会被 compute 侧当场拒收（OverwritePlanShapeError），不是有效输入"
        )
        self.store_ids = store_ids
        self.declared_ids = declared_ids
        self.ghost_ids = ghost_ids

    # ── 四类非平凡性（反空转普查用；口径与 `ItemOverwriteDelta` 三清单的定义同源）────
    @property
    def has_add(self) -> bool:
        """有真正落库的新增（幽灵不算 —— 它恰恰是「没落库」的那一类）。"""
        return bool((set(self.declared_ids) - set(self.store_ids)) - set(self.ghost_ids))

    @property
    def has_delete(self) -> bool:
        return bool(set(self.store_ids) - set(self.declared_ids))

    @property
    def has_update(self) -> bool:
        return bool(set(self.declared_ids) & set(self.store_ids))

    @property
    def has_ghost(self) -> bool:
        return bool(self.ghost_ids)

    @property
    def label(self) -> str:
        return (
            f"store={sorted(self.store_ids)} declared={sorted(self.declared_ids)} "
            f"ghost={sorted(self.ghost_ids)}"
        )


#: 🔴 **覆盖前**的 store 载荷用**紧凑**分隔符 —— 这是前端 `JSON.stringify` 写进库的真实形态，
#: 而平台一切写回都走 `json.dumps(..., ensure_ascii=False)`（带空格）。两者的差异正是 design
#: ADR-AOS-003 附注真库实测的那条「重序列化即字符串漂移」（200 条大载荷里 155 条命中）。
#: 用带空格形态造 store 侧会让这条漂移在本域**消失**，Task 6.7 的「字节精确 vs 语义相等」就再也
#: 分不开 —— 那是把判据调成测不出问题的形态。
_COMPACT: tuple[str, str] = (",", ":")


def _rows_json(pairs: tuple[tuple[str, str], ...], *, compact: bool) -> str:
    """`(身份, 业务名)` 序列 → JSON 文本（真库 `checklist_responses.remark` 的形态）。"""
    return json.dumps(
        [{_IDENTITY_KEY: identity, NAME_FIELD: name} for identity, name in pairs],
        ensure_ascii=False,
        separators=_COMPACT if compact else None,
    )


def _store_payload(scenario: Scenario) -> str:
    return _rows_json(
        tuple((i, _STORE_NAME.format(i)) for i in scenario.store_ids), compact=True
    )


def merge_simulator(payload: str, scenario: Scenario) -> str:
    """模拟引擎 merge 的**结果**（不复现它的判据）。三条规则逐条对应引擎的明文语义：

    1. **已存在的行永不被删**（`merge_projection_into_store_rows` 明写「清空是合法编辑」）
       ⇒ 原行按原序保留；
    2. **两侧都有的行以 substrate 为权威改写受管字段**（`rows_updated` 的定义）
       ⇒ `NAME_FIELD` 改成 substrate 值 —— 这一条让 Task 6.7 的 round-trip 必须还原**字段内容**
       而不只是身份；
    3. **本次新增的身份追加到末尾，锚点业务名为空的那些被幽灵行门剔除** ⇒ `ghost_ids` 不追加。

    🔴 **为什么是模拟而不是真跑 `mirror_projection_into_store`**：那是 Requirement 2 的保护区
    （OO callback 与 adopt 共用的执行层），真跑要一整套 provider / spec / 真库 —— 那是 Task 8.5
    的活。本文件只模拟**结果**，与生产 `observe_ghost_dropped` 的「零复制」同一立场：不复现幽灵
    门的判据（`ghost_row_anchor_index` / `strip()` 口径 / 两处私有 `continue`），只让结果长成
    它产出的样子。
    🔴 模拟是否保真**有独立判据**：`TestMergeSimulatorFidelity` 按上面三条逐条核，且每个场景都
    额外过一遍**生产自己的**交叉核（`applied.mismatches` 与 `verify_applied_plan` 都须为空）——
    模拟一旦不保真，生产那道复读比对会先打红。
    """
    rows = json.loads(payload)
    declared = set(scenario.declared_ids)
    for row in rows:
        if str(row[_IDENTITY_KEY]) in declared:
            row[NAME_FIELD] = _SUBSTRATE_NAME.format(row[_IDENTITY_KEY])
    present = {str(row[_IDENTITY_KEY]) for row in rows}
    ghosts = set(scenario.ghost_ids)
    for identity in scenario.declared_ids:
        if identity in present or identity in ghosts:
            continue
        rows.append({_IDENTITY_KEY: identity, NAME_FIELD: _SUBSTRATE_NAME.format(identity)})
    return json.dumps(rows, ensure_ascii=False)


class Overwritten:
    """跑完一遍覆盖之后的全部观测量（6.6 与 6.7 共用）。"""

    __slots__ = (
        "scenario",
        "baseline",
        "inputs",
        "before",
        "plan1",
        "applied",
        "final",
        "mismatches",
        "session",
    )

    def __init__(self, **fields: Any) -> None:
        for key, value in fields.items():
            setattr(self, key, value)

    def replan(self) -> OverwritePlan:
        """以**同一** substrate projection 对**当前**载荷重算（Property 7 的第二次计算）。

        🔴 走 `compute_plan_for_adopt` 这个**门面**，不直接调 `compute_overwrite_plan` ——
        ADR-AOS-003 的「只有一处算法」对重算同样成立（生产 `apply_overwrite_deletions` 的幽灵
        回喂重算也走同一门面，既有判据已钉死）。
        """
        return ASR.compute_plan_for_adopt(
            baseline=self.baseline,
            store_payloads=dict(self.final),
            plan_inputs=self.inputs,
        )

    @property
    def managed_delta(self) -> Any:
        """:data:`ITEM` 那条 delta（本文件单分区 ⇒ 恰 1 条）。"""
        return _managed_delta(self.applied.plan)


def _managed_delta(plan: OverwritePlan) -> Any:
    found = [d for d in plan.deltas if d.table_key is not None]
    assert len(found) == 1, f"本文件场景只应产恰 1 条受管 delta，实得 {len(found)} 条"
    return found[0]


def _plan_inputs() -> Any:
    """item 分母 = 一条可枚举 + 一条被跳过。`declared_scopes` 由 reader 自带（非 3 条例外形态）。"""
    return ASR.AdoptPlanInputs(
        item_ids=(BLIND, ITEM),
        row_readers={ITEM: _StubReader(item_id=ITEM, declared_scopes=((TABLE, None),))},
        skip_reasons={BLIND: SkipReason.item_blind},
        item_scopes={},
    )


def run_overwrite_once(scenario: Scenario, *, apply_fn: Any = None) -> Overwritten:
    """跑一遍完整覆盖：算计划 → 模拟 merge → **生产**删除侧 → 复读比对。6.6 / 6.7 共用。

    :param apply_fn: 变异体入口（默认 `AOA.apply_overwrite_deletions`）。生产路径与变异路径
        **同一条**建造器 ⇒ 变异反证与对照组的差异只可能来自被变异的那一行。

    🔴 顺序与 `compute_adopt_substrate` 逐步对齐（ADR-AOS-001）：
    `store_payloads`（= `before_snapshot`，**同一次**读取）→ 计划 → merge → 删除侧 → 复读。
    """
    baseline = _projection(**{TABLE: scenario.declared_ids})
    inputs = _plan_inputs()
    before: dict[str, str | None] = {ITEM: _store_payload(scenario), BLIND: BLIND_BEFORE}
    plan1 = ASR.compute_plan_for_adopt(
        baseline=baseline, store_payloads=dict(before), plan_inputs=inputs
    )
    # merge 之后、删除侧之前的库状态。🔴 被跳过的 item 也被 merge 改写字节（删除侧跳过 ≠ merge
    #    跳过）—— 这正是回滚快照并集口径里「字节差集」那一半唯一能看见的东西。
    session = _FakeSession(
        {
            ITEM: merge_simulator(str(before[ITEM]), scenario),
            BLIND: json.dumps(json.loads(BLIND_BEFORE), ensure_ascii=False),
        }
    )
    applied = asyncio.run(
        (apply_fn or AOA.apply_overwrite_deletions)(
            session,
            wp_id="aos66-wp",
            baseline=baseline,
            store_payloads=dict(before),
            plan_inputs=inputs,
            plan=plan1,
        )
    )
    final = dict(session.store)
    mismatches = [
        *applied.mismatches,
        *AOA.verify_applied_plan(
            applied.plan,
            final_payloads=final,
            row_readers=inputs.row_readers,
            item_scopes=inputs.item_scopes,
            post_merge_ids=applied.post_merge_ids,
        ),
    ]
    return Overwritten(
        scenario=scenario,
        baseline=baseline,
        inputs=inputs,
        before=before,
        plan1=plan1,
        applied=applied,
        final=final,
        mismatches=mismatches,
        session=session,
    )


def identities_of(payload: str | None) -> tuple[str, ...]:
    """载荷里的行身份（原序）。6.7 也用。"""
    if payload is None:
        return ()
    return tuple(str(row[_IDENTITY_KEY]) for row in json.loads(payload))


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7 的判据函数（四条断言 C1~C4，逐条独立给出违规文案）
# ═══════════════════════════════════════════════════════════════════════════════


def judge_convergence(run: Overwritten) -> list[str]:
    """按域重述后的 Property 7（模块 docstring 的 C1~C4）。返回违规清单（空 = 收敛）。"""
    violations: list[str] = []
    first = run.managed_delta
    ghost = set(first.rows_ghost_dropped)
    declared = set(run.scenario.declared_ids)
    plan2 = run.replan()
    plan3 = run.replan()
    second = _managed_delta(plan2)

    if second.rows_deleted:  # C1
        violations.append(
            f"C1 破：重算仍报 rows_deleted={sorted(second.rows_deleted)} —— 删除侧没真落库"
            "（计划报了删而库里还在，Requirement 3.5 / 3.8）"
        )
    if set(second.rows_added) != ghost:  # C2
        violations.append(
            f"C2 破：重算的 rows_added={sorted(second.rows_added)} ≠ 上一轮登记的 "
            f"rows_ghost_dropped={sorted(ghost)}；多出 {sorted(set(second.rows_added) - ghost)}"
            f"（这些行该追加却没落库）、缺少 {sorted(ghost - set(second.rows_added))}"
            "（登记了幽灵却又在场 ⇒ 登记不实）"
        )
    if set(second.rows_updated) != declared - ghost:  # C3
        violations.append(
            f"C3 破：收敛后的受管行集应恰为 declared − ghost = {sorted(declared - ghost)}，"
            f"实得 rows_updated={sorted(second.rows_updated)}"
        )
    third = _managed_delta(plan3)  # C4：不动点（「再跑不再有动作」的可执行含义）
    if (third.rows_added, third.rows_deleted, third.rows_updated) != (
        second.rows_added,
        second.rows_deleted,
        second.rows_updated,
    ):
        violations.append(
            f"C4 破：第三次重算的三清单与第二次不等（第三次 added={sorted(third.rows_added)} "
            f"deleted={sorted(third.rows_deleted)} updated={sorted(third.rows_updated)}）"
        )
    if plan2.digest != plan3.digest:
        violations.append(
            f"C4 破：同一载荷两次重算的 plan_digest 不等（{plan2.digest[:12]}… vs "
            f"{plan3.digest[:12]}…）—— 不动点不成立"
        )
    return violations


# ═══════════════════════════════════════════════════════════════════════════════
# 🔴 反空转：显式语料 + 四类非平凡场景的**现算**普查
#
# 禁把生成器调成只产平凡输入蒙绿（恒空 projection 恰好是逐字文本唯一成立的地方 ⇒ 这条纪律在
# 本 property 上格外要紧）。落地两层：
#   ① `CORPUS` 是**确定性**语料，逐条经 `@example` 钉进 hypothesis 运行（`max_examples` 再小也
#      必跑）、同时经 `@pytest.mark.parametrize` 单独跑一遍；
#   ② `TestGeneratorIsNotVacuous` 对 `CORPUS` **现算**四类计数并逐类断言 ≥1 ——
#      普查自带对照（平凡场景那一条必须四类全 False，否则分类器本身在乱认）。
# ═══════════════════════════════════════════════════════════════════════════════

#: 🔴 每条都注明它为四类贡献了什么（改动语料时必须同步改这里，否则普查会打红）。
CORPUS: tuple[Scenario, ...] = (
    # 增 + 删 + 改（无幽灵）—— 最常见的真实形态
    Scenario(store_ids=("r1", "r2"), declared_ids=("r1", "r3")),
    # 增 + 删 + 改 + 幽灵（四类同时非空）
    Scenario(store_ids=("r1", "r2"), declared_ids=("r1", "r3", "r4"), ghost_ids=("r4",)),
    # 只删（substrate 声明为空 ⇒ 清空整张表，Requirement 1.3 的执行侧）
    Scenario(store_ids=("r1", "r2"), declared_ids=()),
    # 只增（store 侧本来是空的）
    Scenario(store_ids=(), declared_ids=("r1", "r2")),
    # 纯幽灵：全部新增身份都被门剔除（`changed_items_from_plan` 的幽灵计入裁定就落在这一条）
    Scenario(store_ids=("r1",), declared_ids=("r1", "r5"), ghost_ids=("r5",)),
    # 幂等重采纳：两侧行集已全等 ⇒ 只有 update（这一条是「收敛后再跑」的直接样本）
    Scenario(store_ids=("r1", "r2"), declared_ids=("r1", "r2")),
    # 🔴 平凡对照：四类全空。**只为普查提供对照**（证明分类器不是恒 True），
    #    它同时是逐字 Property 7 文本唯一成立的形态 —— 见 `test_literal_text_holds_only_here`
    Scenario(store_ids=(), declared_ids=()),
)

_CLASSES = ("has_add", "has_delete", "has_update", "has_ghost")


def _census(corpus: tuple[Scenario, ...] = CORPUS) -> dict[str, int]:
    return {name: sum(1 for s in corpus if getattr(s, name)) for name in _CLASSES}


class TestGeneratorIsNotVacuous:
    def test_all_four_nontrivial_classes_are_produced(self) -> None:
        """四类各现算 ≥1 例。🔴 计数值写进 tasks.md，但断言只卡 ≥1（语料可增不可空）。"""
        counts = _census()
        missing = [name for name, n in counts.items() if n == 0]
        assert not missing, f"语料没产出这些类：{missing}（现算 {counts}）"
        assert counts == {
            "has_add": 3,
            "has_delete": 3,
            "has_update": 4,
            "has_ghost": 2,
        }, f"语料构成变了 —— 现算 {counts}，改语料时请同步更新本断言与 tasks.md 的记录"

    def test_the_trivial_control_is_really_trivial(self) -> None:
        """对照：平凡那条四类全 False ⇒ 分类器不是恒 True（否则上一条什么都没在数）。"""
        trivial = Scenario(store_ids=(), declared_ids=())
        assert [getattr(trivial, name) for name in _CLASSES] == [False] * 4
        assert _census((trivial,)) == dict.fromkeys(_CLASSES, 0)

    def test_every_corpus_member_is_really_exercised(self) -> None:
        """语料每一条都真的跑过一遍覆盖（不是摆着好看）—— 且生产的交叉核全部通过。"""
        for scenario in CORPUS:
            run = run_overwrite_once(scenario)
            assert run.mismatches == [], f"{scenario.label}：生产交叉核打红 {run.mismatches}"


# ═══════════════════════════════════════════════════════════════════════════════
# Property 7 本体
# ═══════════════════════════════════════════════════════════════════════════════

_POOL = ("r1", "r2", "r3", "r4", "r5")


@st.composite
def scenarios(draw: Any) -> Scenario:
    """智能生成器：先抽两侧身份集，再从「可新增」里抽幽灵子集（受幽灵门的合法域约束）。

    🔴 **不是无约束乱抽**：`ghost ⊆ declared − store` 是幽灵门的语义前提（引擎明写「已存在的
    行永不受影响」），抽到域外的组合会被 compute 侧当场拒收 —— 那不是「更强的输入」而是**无效
    输入**，只会把 property 变成在测异常路径（异常路径的判据在
    `test_aos_deletion_apply_and_verify.py` §1 与 `_deltas_for_item` 末尾那条）。
    """
    store = tuple(draw(st.lists(st.sampled_from(_POOL), unique=True, max_size=5)))
    declared = tuple(draw(st.lists(st.sampled_from(_POOL), unique=True, max_size=5)))
    addable = tuple(sorted(set(declared) - set(store)))
    ghosts = (
        tuple(draw(st.lists(st.sampled_from(addable), unique=True, max_size=len(addable))))
        if addable
        else ()
    )
    return Scenario(store_ids=store, declared_ids=declared, ghost_ids=ghosts)


class TestProperty7Convergence:
    """**Property 7: 应用计划后重算计划为空（收敛）** —— 按域重述为 C1~C4。

    **Validates: Requirements 3.8**
    """

    @settings(max_examples=5, deadline=None)
    @given(scenarios())
    @example(CORPUS[0])
    @example(CORPUS[1])
    @example(CORPUS[2])
    @example(CORPUS[3])
    @example(CORPUS[4])
    @example(CORPUS[5])
    @example(CORPUS[6])
    def test_replan_after_apply_converges(self, scenario: Scenario) -> None:
        run = run_overwrite_once(scenario)
        assert run.mismatches == [], f"{scenario.label}：生产复读比对先打红了 {run.mismatches}"
        assert judge_convergence(run) == [], scenario.label

    @pytest.mark.parametrize("scenario", CORPUS, ids=[s.label for s in CORPUS])
    def test_corpus_member_converges(self, scenario: Scenario) -> None:
        """语料逐条单独跑（hypothesis 的 `@example` 之外再来一遍，便于定位是哪一条红）。"""
        assert judge_convergence(run_overwrite_once(scenario)) == []


# ═══════════════════════════════════════════════════════════════════════════════
# 🔴 裁定的可执行证据：design 逐字文本「三个清单均为空」的真实适用域
#
# 本节不是「解释为什么放宽」，而是把**两处偏差**做成可执行断言 —— 谁要改回逐字文本，这两条会
# 当场打红并指出反例。对 design 的改写建议登记在 tasks.md（本轮不改 design）。
# ═══════════════════════════════════════════════════════════════════════════════


def _literal_three_lists_empty(run: Overwritten) -> bool:
    """design 逐字文本：重算的三清单是否**都**为空。"""
    d = _managed_delta(run.replan())
    return not (d.rows_added or d.rows_deleted or d.rows_updated)


class TestLiteralTextApplicabilityDomain:
    def test_deviation_1_ghost_rows_reappear_in_rows_added(self) -> None:
        """偏差①：幽灵身份重算时**必然**回到 `rows_added` ⇒ 逐字文本在有幽灵时不成立。"""
        run = run_overwrite_once(
            Scenario(store_ids=("r1",), declared_ids=("r1", "r5"), ghost_ids=("r5",))
        )
        second = _managed_delta(run.replan())
        assert second.rows_added == ("r5",), second.rows_added
        assert run.managed_delta.rows_ghost_dropped == ("r5",)
        assert not _literal_three_lists_empty(run)

    def test_deviation_2_rows_updated_equals_the_whole_converged_row_set(self) -> None:
        """🔴 偏差②（本轮现算新发现，**与幽灵无关**）：`rows_updated = declared ∩ store`，
        而收敛的含义就是两侧一致 ⇒ 收敛后它恒等于全部受管行，只有 `declared` 为空才空。
        """
        run = run_overwrite_once(Scenario(store_ids=("r1", "r2"), declared_ids=("r1", "r3")))
        second = _managed_delta(run.replan())
        assert second.rows_added == () and second.rows_deleted == ()
        assert set(second.rows_updated) == {"r1", "r3"}, second.rows_updated
        assert not _literal_three_lists_empty(run), (
            "无幽灵、增删改齐全的普通场景里逐字文本就已经不成立 ⇒ 偏差②不是幽灵带来的"
        )

    @pytest.mark.parametrize("scenario", CORPUS, ids=[s.label for s in CORPUS])
    def test_literal_text_holds_only_on_the_trivial_input(self, scenario: Scenario) -> None:
        """🔴 逐字文本成立 ⟺ `declared` 为空 —— 即「清空整表」那一族（含平凡空场景）。

        这条同时是**反空转的底线证明**：若把生成器缩到只产 `declared=()`，逐字文本会全绿而
        收敛的实质（该追加的有没有落库）一个字都没测到。
        """
        holds = _literal_three_lists_empty(run_overwrite_once(scenario))
        assert holds is (not scenario.declared_ids), scenario.label

    def test_only_the_empty_declaration_family_satisfies_the_literal_text(self) -> None:
        """🔴 现算：语料 7 条里只有 2 条满足逐字文本，且两条的 `declared` 都是空。

        其中 1 条并不平凡（store 有 2 行、真删了 2 行）⇒ **不能**把「逐字文本成立」等同于
        「什么都没发生」；它成立的真实条件就是「收敛后受管行集为空」这一件事。
        """
        satisfied = [s.label for s in CORPUS if _literal_three_lists_empty(run_overwrite_once(s))]
        assert len(satisfied) == 2, satisfied
        assert all(not s.declared_ids for s in CORPUS if s.label in satisfied)
        assert [s.has_delete for s in CORPUS if not s.declared_ids] == [True, False], (
            "两条里应恰有一条真删过行（否则「非平凡也能满足逐字文本」这一点就没有样本）"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 变异反证：三组，各自打红 C1 / C2 / C3 中不同的一条（每组都配**对照组**）
#
# 🔴 三个锚点全在 `apply_overwrite_deletions` 里 —— 不是因为图省事，而是因为变异体必须真的被
#    调用：`_source_mutant` 返回的是独立函数对象、**不回写模块**，所以只有直接被
#    `run_overwrite_once(apply_fn=…)` 当入口的那个函数才能生效。变异 `prune_undeclared_rows` /
#    `observe_ghost_dropped` 本体会得到一个没人调的函数（= 变异没生效的假绿）。三组因此都改
#    「删除侧传给下游的东西」，各自等价于下游的一种失效。
# ═══════════════════════════════════════════════════════════════════════════════

#: 🔴 M2 的场景必须满足 `declared ⊋ ghost`（否则「整表被清空」与「全是幽灵」在重算结果上同形）。
_M_SCENARIO = Scenario(store_ids=("r1", "r2"), declared_ids=("r1", "r3", "r4"), ghost_ids=("r4",))


def _mutant_apply(*, old: str, new: str) -> Any:
    return _source_mutant(AOA.apply_overwrite_deletions, old=old, new=new, module=AOA)


class TestConvergenceJudgeHasTeeth:
    def test_control_group_production_converges(self) -> None:
        """对照组：同一场景在生产实现下四条断言全过（三组变异共用这一条对照）。"""
        assert judge_convergence(run_overwrite_once(_M_SCENARIO)) == []

    def test_mutant_m1_deletion_not_written_back_breaks_c1(self) -> None:
        """M1：写回的是**未剪枝**载荷（删除侧白跑一趟）⇒ 重算仍报 `rows_deleted` ⇒ C1 打红。

        🔴 `json.loads(payload)` 那一步是**形态所需**不是绕路：`payload` 是库里的原始 remark
        字符串，直接 `json.dumps(payload)` 会把它二次编码成「字符串的 JSON」，下一轮读取当场
        `TypeError` —— 那测出来的是解析崩溃而不是「删除侧没落库」。
        """
        mutant = _mutant_apply(
            old='"val": json.dumps(pruned, ensure_ascii=False),',
            new='"val": json.dumps(json.loads(payload), ensure_ascii=False),',
        )
        run = run_overwrite_once(_M_SCENARIO, apply_fn=mutant)
        got = judge_convergence(run)
        assert len(got) == 1 and got[0].startswith("C1 破"), got
        # 变异生效断言：`rows_deleted_by_item` 仍报了删除（红的是「没落库」不是「没打算删」）
        assert run.applied.rows_deleted_by_item == {ITEM: ("r2",)}
        assert identities_of(run.final[ITEM]) == ("r1", "r2", "r3")
        # 🔴 同一失效被**两个互不依赖的判据**抓住：生产自己的提交前复读比对也打红
        assert any("多出 ['r2']" in m for m in run.mismatches), run.mismatches

    def test_mutant_m2_declared_collapsed_to_empty_breaks_c2_and_c3(self) -> None:
        """M2：删除侧把 `declared` 当成空集（`.get()` 语义那类错）⇒ 整张受管表被清空。

        ⇒ 重算把全部声明身份报成新增（≠ 登记的幽灵）且受管行集变空 ⇒ C2 与 C3 同时打红。
        """
        mutant = _mutant_apply(
            old="row_keys = _row_keys_of(baseline)",
            new="row_keys = {t: () for t in _row_keys_of(baseline)}",
        )
        run = run_overwrite_once(_M_SCENARIO, apply_fn=mutant)
        got = judge_convergence(run)
        assert [v[:4] for v in got] == ["C2 破", "C3 破"], got
        assert identities_of(run.final[ITEM]) == (), "变异没生效（受管表没被清空）"

    def test_mutant_m3_ghost_not_fed_back_breaks_c2(self) -> None:
        """🔴 M3：观测到的幽灵**不回喂**最终计划 ⇒ 登记清单为空 ⇒ C2 的容许集塌成空集。

        这一组是 C2 那条「容许集」**不是一张免检通行证**的证明：C2 容许的不是「任何还缺的身份」，
        而是**恰好那些被登记过的**。不回喂 ⇒ 同一个 `r4` 立刻变成违规。

        🔴 锚点必须带上前一行：裸 `ghost_dropped_by_item=ghost_dropped_by_item,` 在该函数源码里
        命中 **2** 次（另一处是 `AppliedOverwrite(...)` 的同名字段）—— 只改后者就变成「观测没
        登记进产出物」而不是「没回喂计划」，两件事不同。
        """
        mutant = _mutant_apply(
            old=(
                "            plan_inputs=plan_inputs,\n"
                "            ghost_dropped_by_item=ghost_dropped_by_item,\n"
            ),
            new="            plan_inputs=plan_inputs,\n            ghost_dropped_by_item=None,\n",
        )
        run = run_overwrite_once(_M_SCENARIO, apply_fn=mutant)
        assert run.managed_delta.rows_ghost_dropped == (), "变异没生效（幽灵仍被登记）"
        got = judge_convergence(run)
        # 🔴 C2 与 C3 的期望集合**都**从登记清单派生 ⇒ 抹掉登记会同时打红两条。如实断言两条，
        #    不把它写成「只红 C2」（那样一旦 C3 的派生方式改了就静默不符）。
        assert [v[:4] for v in got] == ["C2 破", "C3 破"], got
        assert "多出 ['r4']" in got[0] and "rows_ghost_dropped=[]" in got[0], got
        # 观测本身仍在（红的是「没登记进计划」不是「没观测到」）
        assert run.applied.ghost_dropped_by_item == {ITEM: ("r4",)}


# ═══════════════════════════════════════════════════════════════════════════════
# merge 模拟器的保真判据（模拟不保真 ⇒ 整个 property 在测另一件事）
# ═══════════════════════════════════════════════════════════════════════════════


class TestMergeSimulatorFidelity:
    """逐条核 `merge_simulator` 的三条规则（它们全部取自引擎的明文语义，见该函数 docstring）。"""

    @pytest.mark.parametrize("scenario", CORPUS, ids=[s.label for s in CORPUS])
    def test_three_documented_rules(self, scenario: Scenario) -> None:
        before = _store_payload(scenario)
        after = merge_simulator(before, scenario)
        got = identities_of(after)
        # 规则 1：已存在的行一个都没少，且**原序**在前
        assert got[: len(scenario.store_ids)] == scenario.store_ids
        # 规则 3a：本次新增的非幽灵身份都追加上了；3b：幽灵一个都没进来
        expected_new = tuple(
            i
            for i in scenario.declared_ids
            if i not in set(scenario.store_ids) and i not in set(scenario.ghost_ids)
        )
        assert got[len(scenario.store_ids) :] == expected_new
        assert not set(got) & set(scenario.ghost_ids)
        # 规则 2：两侧都有的行，受管字段已被 substrate 权威改写
        rows = {str(r[_IDENTITY_KEY]): r for r in json.loads(after)}
        for identity in set(scenario.declared_ids) & set(scenario.store_ids):
            assert rows[identity][NAME_FIELD] == _SUBSTRATE_NAME.format(identity)
        # 作用域内但未声明的行（待删）**不被 merge 碰**（原值留着 ⇒ 6.7 的还原有内容可比）
        for identity in set(scenario.store_ids) - set(scenario.declared_ids):
            assert rows[identity][NAME_FIELD] == _STORE_NAME.format(identity)

    def test_the_two_sides_names_really_differ(self) -> None:
        """前提对照：store 侧原值与 substrate 值**不同** —— 相同则规则 2 那条什么都没在查。"""
        assert _STORE_NAME.format("x") != _SUBSTRATE_NAME.format("x")

    def test_skipped_item_is_rewritten_by_merge(self) -> None:
        """被跳过的 item 也被 merge 改写字节（删除侧跳过 ≠ merge 跳过）——
        它是回滚快照并集口径里「字节差集」那一半唯一能看见的东西（Task 6.7 依赖这条前提）。
        """
        run = run_overwrite_once(CORPUS[1])
        assert run.final[BLIND] != BLIND_BEFORE
        assert json.loads(str(run.final[BLIND])) == json.loads(BLIND_BEFORE), (
            "语义应相等、字节应不同（真库实测的重序列化漂移形态）"
        )
        assert ASR._diff_snapshots(dict(run.before), dict(run.final)) == [BLIND, ITEM]

    def test_store_side_bytes_are_compact_while_writeback_is_spaced(self) -> None:
        """🔴 前提对照：覆盖前是**紧凑**形态、写回是**带空格**形态 ⇒ 重序列化漂移真实存在。

        两侧若同形，Task 6.7 的「字节精确」与「语义相等」两档判据就退化成同一档（分不开 =
        测不出重序列化这类缺陷）。
        """
        scenario = Scenario(store_ids=("r1",), declared_ids=("r1",))
        before = _store_payload(scenario)
        assert '", "' not in before and '": "' not in before, before
        spaced = json.dumps(json.loads(before), ensure_ascii=False)
        assert spaced != before and json.loads(spaced) == json.loads(before)
        assert run_overwrite_once(scenario).final[ITEM] != before


# ═══════════════════════════════════════════════════════════════════════════════
# 指针：相邻判据在哪
# ═══════════════════════════════════════════════════════════════════════════════
#
# · **Property 11（回滚 round-trip / Task 6.7）在 `test_aos_property_rollback_roundtrip.py`** ——
#   它 import 本文件的 `Scenario` / `CORPUS` / `run_overwrite_once` / `identities_of`
#   / `merge_simulator`，「跑一遍覆盖」的脚手架只有这一份。
# · 删除侧应用 / 幽灵**观测**口径 / 复读比对 / 假 session → `test_aos_deletion_apply_and_verify.py`
# · 幽灵行门的语义与登记（Property 3）→ `test_aos_property_ghost_gate.py`
# · 作用域外行逐元素不变（Property 2）→ `test_aos_property_out_of_scope_rows.py` + `…_mutants.py`
# · plan 内部自洽（Property 4）/ digest（Property 6）→ `test_aos_plan_selfconsistency_and_digest.py`
# · Requirement 3.8 逐字要的**真实 PostgreSQL 对账**归 Task 8.5 —— 本文件不假装覆盖它。
