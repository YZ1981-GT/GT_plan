# -*- coding: utf-8 -*-
"""复用可观测 + 「连续两次必命中」守卫（任务 10 · P6 · requirements 3.1 / 3.2 / 3.3）。

spec: oo-single-pass-materialize-and-room-leave

═══ 这里守的是哪一个「复用」═══

**不是** 任务 8/9 那个解析复用（`workbook_read_scope()`，一次 CPU 段内同一份字节只解析
一次），而是**业务身份复用**：内容一字未改 ⇒ 根本不 materialize
（`materialize_coordinator._find_business_identity_reuse`）。前者省的是「物化内部读几遍」，
后者省的是「要不要物化」——真库 D4 上一个是 7.5s→4.7s，另一个是 30s→2.1s。

═══ requirements 3.2 点名的那个判据缺口 ═══

原文：「这条正是上一轮那个『digest 口径不一致 ⇒ 复用恒不命中』缺陷的**判据缺口**：当时
`_find_business_identity_reuse` 的单测全绿，因为没有人把『两次同内容』跑成一条链。」

缺口的**具体形态**（读实现 + 真栈证据得出，不是复述）：那个缺陷发生在两条**派生路径**
之间 —— 已提交的 projection 与当次 flush 的 projection 是同一份业务内容的两次独立派生
（HTML store 走 JSON ⇒ 裸 int/float；Excel extract 走 openpyxl ⇒ int/float/str；merge 与
审定回写 ⇒ `Decimal`）。只要判据两侧喂的是**同一批 Python 对象**，digest 必然相等，缺陷
就永远看不见 —— 既有 `test_projection_digest_is_representation_stable.py`（值级矩阵）与
PG 侧 `test_task25_materialize_coordinator_pg.py` 阶段 8b（同字面量两次 flush）都落在这个
盲区里。

所以本文件的链条刻意让两侧**各自独立派生**：

```
模板 substrate ──extract①──> projection A ──materialize①──> 产物 gen1
                                                              │
                                        projection B <──extract②
```

projection A 与 B 是同一份业务内容的两次**不同**派生（一次从模板字节、一次从产物字节，
两份字节逐字节不同），A 是「已提交」那一侧、B 是「当次 flush」那一侧 —— 与真栈那条缺陷
的成因逐项对应。第二次 materialize 必须命中复用，即
`verdict.decision is ReuseDecision.hit`。

═══ 反证（承重，不是空转）═══

把 digest 口径退回改动前的裸 `json_safe`（= `mutate_projection_digest_stability_guards`
的第 1 条变异，这里用运行时替换，生产文件零改动）：同一条链上 digests 立刻分叉，而 218 个
字段**逐键全等**（0 缺 0 多 0 改）⇒ 判词必须是
`miss_digest_representation_drift` 且 `is_defect=True`。那正是真栈那 899 键全等、digest
却不同的形态，本文件把它做成了自动判据。

CI 门在 `backend/scripts/check/check_materialize_reuse_digest_caliber.py`（requirements 3.3
的「在 CI 里直接判红」）：`tests/workpaper_sync/` 有约 291 条既存失败（design 附录 F.9 的
A/B 差分实测），在那个分母上「pytest 红了」不是可归因信号，所以缺陷类必须有一个自己就能
红的门。本文件是它的 falsifier，门的第 ④ 段反过来检查本文件还在。
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import inspect
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))

from app.services.workpaper_sync import content_mutation as CM  # noqa: E402
from app.services.workpaper_sync import excel_materialize as EM  # noqa: E402
from app.services.workpaper_sync import materialize_coordinator as MC  # noqa: E402
from app.services.workpaper_sync import metrics as MX  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldMode,
    FieldValue,
    Projection,
    ValueType,
)
from app.services.workpaper_sync.definitions import json_safe  # noqa: E402
from app.services.workpaper_sync.materialize_reuse_verdict import (  # noqa: E402
    DEFECT_MISS_REASONS,
    REUSE_METRIC,
    REUSE_RESULT_DOMAIN,
    SINGLE_PASS_DECLINE_DOMAIN,
    SINGLE_PASS_DECLINE_METRIC,
    ReuseDecision,
    ReuseMissReason,
    ReuseVerdict,
    business_value_equal,
    classify_single_pass_decline,
    compare_projection_payloads,
    record_single_pass_decline,
    single_pass_decline_scope,
    verdict_for_miss,
)
from tests.workpaper_sync.d4_materialize_harness import (  # noqa: E402
    build_world,
    rebased_world,
)
from tests.workpaper_sync.test_single_pass_artifact_equivalence import (  # noqa: E402
    compare_zip_entries,
    projection_differences,
)

_COORDINATOR_PY = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "materialize_coordinator.py"
)
_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_sync_router.py"
_ADAPTER_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "adapters" / "excel.py"


# ═══════════════════════════════════════════════════════════════════════════
# 链条：真库 D4 上连续两次 materialize（module 作用域，铺 world + 两趟物化 ≈ 20s）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ReuseChain:
    """一条真实的「连续两次 materialize」链，两侧 projection **各自独立派生**。"""

    #: 第一次 materialize 喂进去的 projection（= 被提交的那一侧）。
    committed: Projection
    #: 从第一次的产物**重新反读**出来的 projection（= 下一次 flush 会算 digest 的那一侧）。
    rederived: Projection
    #: 第一次的产物；它同时是第二代 world 的 substrate。
    gen1: Path
    #: 第二次 materialize 的产物（用于「第二趟全是白干」的等值判据）。
    gen2: Path
    #: 第一代 substrate（模板字节）与第二代 substrate（gen1 字节）的路径。
    gen0_substrate: Path
    gen1_substrate: Path
    #: 第一代 world（`adapter` / `contract` 挂在它上面，供 `rebased_world` 再挂一代用）。
    world: Any


@pytest.fixture(scope="module")
def chain(tmp_path_factory: pytest.TempPathFactory) -> ReuseChain:
    world = build_world(tmp_path_factory.mktemp("reuse_chain"))
    gen1 = world.materialize("gen1.xlsx")
    steady = rebased_world(world, substrate_bytes=gen1.read_bytes(), label="steady")
    gen2 = steady.materialize("gen2.xlsx")
    return ReuseChain(
        committed=world.projection,
        rederived=steady.projection,
        gen1=gen1,
        gen2=gen2,
        gen0_substrate=world.base,
        gen1_substrate=steady.base,
        world=world,
    )


def _payload(projection: Projection) -> dict[str, Any]:
    return CM._projection_payload(projection)


def _digest(projection: Projection) -> str:
    return CM.projection_canonical_digest(projection)


def _verdict_for(committed: Projection, rederived: Projection) -> ReuseVerdict:
    """用**生产**那两个函数复现 coordinator 的复用判定 + 归因。

    `base_version_matched` 刻意由 digest 相等**现算**而不是写死：coordinator 的那条腿就是
    `WorkpaperContentVersion.projection_sha256 == payload_sha256`（见
    `_find_business_identity_reuse`），也就是这两个 digest 的字节相等。链条判据要跟着
    真实判定走，写死一个布尔值就变成自证。
    """
    base_payload, incoming_payload = _payload(committed), _payload(rederived)
    matched = _digest(committed) == _digest(rederived)
    if matched:
        return MC.REUSE_HIT
    return verdict_for_miss(
        base_payload=base_payload,
        incoming_payload=incoming_payload,
        base_version_matched=False,
    )


@contextlib.contextmanager
def digest_caliber_reverted() -> Iterator[None]:
    """承重反证：把 digest 的**值表示**口径退回改动前的裸 `json_safe`。

    等价于 `scripts/diagnose/mutate_projection_digest_stability_guards.py` 的第 1 条变异
    （「退回改动前的口径（直接 json_safe 原值）」），但用运行时替换 —— 生产文件零改动、
    退出即还原，不依赖「改完记得按 sha256 复原」这种人工纪律。

    替换点是 `content_mutation` 命名空间里的那个名字：`_projection_payload` 是在模块级
    `from ... import canonical_value_for_digest` 之后按**全局名**解析它的，所以换模块属性
    就真的改变了生产序列化路径（本文件的判据实测两侧 digest 会分叉，即证明替换生效）。
    """
    original = CM.canonical_value_for_digest
    CM.canonical_value_for_digest = lambda field: json_safe(field.value)
    try:
        yield
    finally:
        CM.canonical_value_for_digest = original


# ═══════════════════════════════════════════════════════════════════════════
# requirements 3.2：同一 projection 连续两次 materialize，第二次必须命中复用
# ═══════════════════════════════════════════════════════════════════════════


class TestConsecutiveMaterializeHitsReuse:
    """P6。链条是真的：两次 `adapter.materialize` + 两次独立 `extract`，零 mock。"""

    def test_the_two_sides_are_really_two_independent_derivations(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2**

        反空转前提。少了这一条，「第二次命中复用」可以靠「两侧是同一批 Python 对象」
        恒真 —— 而那恰恰是 requirements 3.2 说的那个判据缺口（既有值级矩阵与 PG 阶段 8b
        都落在这里）。

        三层各自立分母：①两侧不是同一个对象；②两侧的 substrate 字节逐字节不同（所以是
        两次真解析，不是同一次的缓存）；③两侧都覆盖全部受管字段（218），不是一个子集碰巧
        相等。
        """
        assert chain.committed is not chain.rederived
        gen0_bytes = chain.gen0_substrate.read_bytes()
        gen1_bytes = chain.gen1_substrate.read_bytes()
        assert gen0_bytes != gen1_bytes, (
            "两代 substrate 字节相同 —— 那说明第二次 extract 读的是同一份字节，"
            "两条派生路径就不是两条了"
        )
        assert len(chain.committed.values) == len(chain.rederived.values) == 218, (
            f"字段数 {len(chain.committed.values)} / {len(chain.rederived.values)}"
            " —— 真库 D4 受管字段实测 218，任一侧变少说明这条链已经不是全量面"
        )

    def test_the_second_materialize_hits_business_identity_reuse(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2**

        本 spec 里 P6 的正面判据：第二次必须命中。断言的是**判词**而不是「digest 相等」——
        判词是生产下游（metrics / 日志 / 前端）真正消费的那个值。
        """
        verdict = _verdict_for(chain.committed, chain.rederived)
        assert verdict.decision is ReuseDecision.hit, (
            f"第二次 materialize 没命中复用：{verdict.as_dict()} —— "
            "内容一字未改却要重新物化整本工作簿（真库 D4 实测 CPU 段 7.5s + 发布/IO），"
            "这正是 2026-09-22 那个 digest 口径缺陷的表现"
        )
        assert verdict.miss_reason is None
        assert verdict.reused is True
        assert verdict.metric_result == "hit"

    def test_the_two_derivations_differ_only_in_four_boolean_representations(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2**

        🔴 **实测结论，不是预期**（本任务发现，登记在 design 附录 H.2）：两条派生路径在
        `repr` 口径（任务 4 的 `projection_differences`，最严的那套）下**不是**逐字段相等
        —— 真库 D4 上恰有 **4** 个 `boolean` 字段一侧是 `int:1`、另一侧是 `bool:True`：

        * `undisclosed_rp_rows/GTROW-D427-0015/is_customer_legal`
        * `undisclosed_rp_rows/GTROW-D427-0015/is_production_dept`
        * `undisclosed_rp_rows/GTROW-D427-0016/is_finance_dept`
        * `undisclosed_rp_rows/GTROW-D427-0016/is_personal_customer`

        成因与真栈那条 `0` vs `0.0` **同构**：instrumented 模板里这些格是数字字面量，
        openpyxl 反读成 `int 1`；materialize 按 `boolean_literal` 写进产物后再反读成
        `bool True`。两者 `==` 相等、`repr` 不同、落盘字节不同。

        ⇒ 这不是缺陷，而是这条链**真的是两条派生路径**的最硬证据，同时说明
        `canonical_value_for_digest` 在真库 D4 上**今天就在承重**：哪怕一个金额零都不参与，
        光这 4 个 boolean 就足以让业务身份复用恒不命中（本文件
        `test_reverting_the_digest_caliber_turns_the_chain_into_a_defect_miss` 实测）。

        判据因此写成「差异恰是这 4 个、形态恰是 int→bool、且 payload 把它们折叠成同一个
        JSON `true`」，而不是「差异为空」。多一处差异、少一处差异、或形态变了都会红。
        """
        differences = projection_differences(
            chain.committed,
            chain.rederived,
            left_label="committed",
            right_label="rederived",
        )
        drifted = sorted(item.split(":", 1)[0] for item in differences)
        assert drifted == [
            "undisclosed_rp_rows/GTROW-D427-0015/is_customer_legal",
            "undisclosed_rp_rows/GTROW-D427-0015/is_production_dept",
            "undisclosed_rp_rows/GTROW-D427-0016/is_finance_dept",
            "undisclosed_rp_rows/GTROW-D427-0016/is_personal_customer",
        ], f"表示差异的集合变了：{differences}"
        for key in drifted:
            left = chain.committed.values[key]
            right = chain.rederived.values[key]
            assert left.value_type is ValueType.boolean
            assert (type(left.value).__name__, type(right.value).__name__) == (
                "int",
                "bool",
            ), f"{key} 的表示差异形态变了：{left.value!r} / {right.value!r}"
            assert left.value == right.value  # 业务上是同一个真值
        # digest 看到的那一层：payload 把 int 1 与 bool True 折成同一个 JSON true。
        committed_payload, rederived_payload = (
            _payload(chain.committed),
            _payload(chain.rederived),
        )
        for key in drifted:
            assert committed_payload["values"][key]["value"] is True
            assert rederived_payload["values"][key]["value"] is True
        assert CM.canonical_json_bytes(committed_payload) == (
            CM.canonical_json_bytes(rederived_payload)
        )

    def test_the_business_comparison_sees_no_difference_at_all(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2, 3.3**

        归因用的业务比较面（表示无关）在同一条链上必须报 **0** 差异，且必须真的比过
        218 个字段 —— 否则「内容全等却没命中 ⇒ 缺陷」这条归因就建立在一个空集合上。
        """
        comparison = compare_projection_payloads(
            _payload(chain.committed), _payload(chain.rederived)
        )
        assert comparison.as_dict() == {
            "identical": True,
            "identity_differences": [],
            "content_differences": [],
        }
        assert len(_payload(chain.rederived)["values"]) == 218

    def test_the_second_materialize_would_have_produced_nothing_new(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2**

        复用命中之所以是**对的**（而不只是快），是因为第二趟的产物与第一趟逐 entry 内容全同
        —— 那一趟整个是白干。这条同时是 design 附录 G.2「materialize 在 steady state 上是
        不动点」的复用侧读法。

        `date_time` 显式分流（同 design 附录 B.3 口径：任务 1 实测 142 个时间戳必全不同，
        不摘掉这条判据永远红），所以剩下的每一个差异都是真差异。
        """
        comparison = compare_zip_entries(chain.gen1, chain.gen2)
        assert comparison.namelist_equal
        assert comparison.content_differences == (), (
            f"第二趟产物与第一趟有真实字节差异：{comparison.content_differences} —— "
            "那说明 steady state 不是不动点，复用命中会丢掉这些差异"
        )
        assert comparison.entry_count == 142
        assert len(comparison.timestamp_differences) == comparison.entry_count
        assert comparison.sha256_equal is False, (
            "整份 sha256 竟然相同 —— 那说明 zip 时间戳被冻结了，"
            "而本判据的 `date_time` 分流是按「必然全不同」立的（任务 1 实测）"
        )

    def test_the_digest_is_a_fixed_point_across_further_generations(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2**

        命中一次不够：生产里用户可能连切好几次。第三代 substrate（gen2 字节）再反读一次，
        digest 必须仍是同一个 —— 否则复用会「隔一次命中一次」，而那种间歇性缺陷比恒不命中
        更难查。
        """
        third = rebased_world(
            chain.world, substrate_bytes=chain.gen2.read_bytes(), label="gen3"
        )
        assert _digest(third.projection) == _digest(chain.rederived) == _digest(
            chain.committed
        )
        assert _verdict_for(chain.rederived, third.projection).decision is (
            ReuseDecision.hit
        )


# ═══════════════════════════════════════════════════════════════════════════
# requirements 3.3：未命中原因至少三类可区分（+ 第四类「无从比较」）
# ═══════════════════════════════════════════════════════════════════════════


def _field(value: Any, value_type: ValueType = ValueType.amount) -> FieldValue:
    return FieldValue(
        stable_key="t/r1/f",
        value=value,
        value_type=value_type,
        mode=FieldMode.editable,
        row_key="r1",
    )


def _mini(value: Any, *, contract_id: str = "c1", version: str = "1.0.0") -> Projection:
    return Projection(
        contract_id=contract_id,
        semantic_version=version,
        document_type="xlsx",
        values={"t/r1/f": _field(value)},
        row_keys={"t": ("r1",)},
    )


class TestMissReasonsAreDistinguishable:
    """四类未命中在**同一个**分类器上给出四个不同的封闭域值。"""

    def test_content_changed_is_its_own_class(self) -> None:
        """**Validates: Requirements 3.3**

        「内容真变了」—— 正常，全量物化是对的。它必须与缺陷类区分开，否则值班会把每一次
        正常的编辑都当成缺陷告警。
        """
        verdict = verdict_for_miss(
            base_payload=_payload(_mini(Decimal("1234.50"))),
            incoming_payload=_payload(_mini(Decimal("8888.00"))),
            base_version_matched=False,
        )
        assert verdict.miss_reason is ReuseMissReason.content_changed
        assert verdict.metric_result == "miss_content_changed"
        assert verdict.is_defect is False
        assert verdict.differences and "values[t/r1/f].value" in verdict.differences[0]

    @pytest.mark.parametrize(
        "kwargs",
        [
            pytest.param({"contract_id": "c2"}, id="contract_id"),
            pytest.param({"version": "2.0.0"}, id="semantic_version"),
        ],
    )
    def test_contract_change_is_its_own_class(self, kwargs: Mapping[str, str]) -> None:
        """**Validates: Requirements 3.3**

        「契约或 bundle 变了」—— 也正常（新 representation 必须重算），但 runbook 与上一类
        不同：那一类要看用户改了什么，这一类要看契约是谁发布的。
        """
        verdict = verdict_for_miss(
            base_payload=_payload(_mini(Decimal("1234.50"))),
            incoming_payload=_payload(_mini(Decimal("1234.50"), **kwargs)),
            base_version_matched=False,
        )
        assert verdict.miss_reason is ReuseMissReason.contract_or_bundle_changed
        assert verdict.metric_result == "miss_contract_or_bundle_changed"
        assert verdict.is_defect is False

    def test_bundle_or_substrate_leg_is_the_same_class(self) -> None:
        """**Validates: Requirements 3.3**

        AC 3.6 三元组的另一条腿：projection digest 相同、但当前 published representation
        已经不是挂在那个 content version 上的那一行（definitions-only 升级换代等）。
        requirements 3.3 把契约与 bundle 归成同一类，所以它与上一条同格。
        """
        same = _payload(_mini(Decimal("1234.50")))
        verdict = verdict_for_miss(
            base_payload=same, incoming_payload=same, base_version_matched=True
        )
        assert verdict.miss_reason is ReuseMissReason.contract_or_bundle_changed
        assert "representation" in verdict.differences[0]
        assert verdict.is_defect is False

    def test_no_base_projection_is_its_own_class(self) -> None:
        """**Validates: Requirements 3.3**

        「无从比较」必须单列。把它并进上面任何一类都会说谎；尤其**不能**并进缺陷类 ——
        首代 representation 与历史行（`projection_artifact_id IS NULL`）本来就没有可比载荷，
        那不是缺陷。
        """
        verdict = verdict_for_miss(
            base_payload=None,
            incoming_payload=_payload(_mini(Decimal("1"))),
            base_version_matched=False,
        )
        assert verdict.miss_reason is ReuseMissReason.no_base_projection
        assert verdict.is_defect is False

    def test_digest_representation_drift_is_a_defect_class(self) -> None:
        """**Validates: Requirements 3.3**

        🔴 第三类：业务内容逐键全等却没命中 ⇒ digest 口径分叉，**缺陷**。

        两侧 payload 的 `value` 刻意是 `0`（int）与 `"0.00"`（str）—— 那正是口径分叉时
        落盘字节的真实形态（真栈首个差异 `"value":0` vs `"value":0.0`）。
        """
        base = _payload(_mini(0))
        incoming = _payload(_mini(0))
        base["values"]["t/r1/f"]["value"] = 0
        incoming["values"]["t/r1/f"]["value"] = "0.00"
        verdict = verdict_for_miss(
            base_payload=base, incoming_payload=incoming, base_version_matched=False
        )
        assert verdict.miss_reason is ReuseMissReason.digest_representation_drift
        assert verdict.metric_result == "miss_digest_representation_drift"
        assert verdict.is_defect is True
        assert verdict.compared_field_count == 1
        assert "逐键全等" in verdict.differences[0]

    def test_the_four_classes_map_to_four_distinct_metric_results(self) -> None:
        """**Validates: Requirements 3.1, 3.3**

        「可区分」的机器判据：四个原因 → 四个互不相同的封闭域值，且封闭域恰好等于
        `hit` + `replayed` + 四个 `miss_*`（多一格少一格都红）。
        """
        results = {
            ReuseVerdict(
                decision=ReuseDecision.miss, miss_reason=reason
            ).metric_result
            for reason in ReuseMissReason
        }
        assert len(results) == len(list(ReuseMissReason)) == 4
        assert set(REUSE_RESULT_DOMAIN) == results | {"hit", "replayed"}

    def test_only_the_digest_drift_class_is_marked_as_a_defect(self) -> None:
        """**Validates: Requirements 3.3**

        缺陷集合两侧锁死：少一个 ⇒ 缺陷被降级成正常回落（CI 门失效）；多一个 ⇒ 正常的
        全量物化会被报成缺陷（告警噪音把真缺陷埋掉）。
        """
        assert DEFECT_MISS_REASONS == frozenset(
            {ReuseMissReason.digest_representation_drift}
        )
        assert all(
            ReuseVerdict(decision=ReuseDecision.miss, miss_reason=reason).is_defect
            is (reason in DEFECT_MISS_REASONS)
            for reason in ReuseMissReason
        )


class TestBusinessComparisonIsIndependentOfTheDigestCaliber:
    """缺陷类可达的**前提**：归因用的业务比较面不能是 digest 口径的自证。"""

    @pytest.mark.parametrize(
        "value_type,left,right",
        [
            ("amount", 0, 0.0),
            ("amount", 0, "0.00"),
            ("amount", 1234.5, "1234.50"),
            ("integer", 7, 7.0),
            ("rate", "0.0325", "0.03250"),
        ],
    )
    def test_representation_differences_are_business_equal(
        self, value_type: str, left: Any, right: Any
    ) -> None:
        """**Validates: Requirements 3.3**"""
        assert business_value_equal(value_type, left, right) is True

    @pytest.mark.parametrize(
        "value_type,left,right",
        [
            ("amount", 0, None),
            ("amount", None, 0),
            ("amount", "0.01", "0.02"),
            ("text", "", "0"),
            ("text", "0", 0),
            ("boolean", True, False),
            ("json", {"a": 1}, {"a": 2}),
        ],
    )
    def test_semantic_differences_stay_different(
        self, value_type: str, left: Any, right: Any
    ) -> None:
        """**Validates: Requirements 3.3**

        反向锁。少了它，`business_value_equal` 可以恒 `True`，于是**每一次**未命中都被判成
        缺陷类 —— 那比看不见缺陷更坏（真实的内容修改会被报成 bug）。
        """
        assert business_value_equal(value_type, left, right) is False

    def test_the_comparison_reports_missing_extra_and_changed_keys(self) -> None:
        """**Validates: Requirements 3.3**

        三类差异（缺 key / 多 key / 值变）都要能报 —— design 附录 B.4 第 1 条实测过，
        只比 key 集合的判据在「漏写一个 binding」那条反证下是绿的。清单还必须**完整且排序**
        （同 A.6 第 2 条），所以这里断言逐条内容而不是只断言「非空」。
        """
        base = _payload(_mini(Decimal("1")))
        base["values"]["t/r1/gone"] = dict(base["values"]["t/r1/f"])
        incoming = _payload(_mini(Decimal("2")))
        incoming["values"]["t/r1/new"] = dict(incoming["values"]["t/r1/f"])
        comparison = compare_projection_payloads(base, incoming)
        assert comparison.identity_differences == ()
        assert comparison.content_differences == (
            "values[t/r1/gone]: 缺失（基线有、本次无）",
            "values[t/r1/new]: 新增（基线无、本次有）",
            "values[t/r1/f].value: '1' -> '2'",
        )

    def test_row_key_order_is_part_of_the_comparison(self) -> None:
        """**Validates: Requirements 3.3**

        行序/行身份变了就是内容变了（行身份是 D4 的隐藏 UUID 列承载的真实业务事实）。
        """
        base = _payload(
            dataclasses.replace(_mini(Decimal("1")), row_keys={"t": ("r1", "r2")})
        )
        incoming = _payload(
            dataclasses.replace(_mini(Decimal("1")), row_keys={"t": ("r2", "r1")})
        )
        comparison = compare_projection_payloads(base, incoming)
        assert any("row_keys[t]" in item for item in comparison.content_differences)


# ═══════════════════════════════════════════════════════════════════════════
# requirements 3.1：机器可读判词落进既有 metrics（不是只写日志）
# ═══════════════════════════════════════════════════════════════════════════


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _func(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _emit_metric_names(fn: ast.AST) -> list[str]:
    """函数体里每一次 `sync_metrics.<emit>()` 的第一个实参（字面量或常量名）。

    既有 `test_task29_timeline_evidence` 的同类判据只收**字符串字面量** ⇒ 用常量名 emit 的
    指标它一个都看不见。这里把 `ast.Name` 也收进来并在调用侧解析成真值，所以本 spec 的两个
    emit 也在覆盖面里（否则「router 用了目录外的指标名」这条对本任务是空门）。
    """
    names: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in ("record_outcome", "observe", "set_gauge", "record_error"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.append(first.value)
        elif isinstance(first, ast.Name):
            names.append(f"<name:{first.id}>")
    return names


class TestTheVerdictIsMachineReadableAndRegistered:
    def test_the_materialize_outcome_carries_the_verdict(self) -> None:
        """**Validates: Requirements 3.1**

        「materialize 的结果 SHALL 带一个机器可读的复用判定」的**类型层**判据：字段存在、
        类型是 `ReuseVerdict`、且**没有默认值**（有默认值就等于允许某条路径悄悄记成别的桶）。
        """
        fields = {f.name: f for f in dataclasses.fields(MC.MaterializeOutcome)}
        assert "reuse_verdict" in fields, (
            "MaterializeOutcome 没有 reuse_verdict —— requirements 3.1 要求结果**带**判定，"
            "而不是让调用方从 business_identity_reused 这个布尔去猜原因"
        )
        field = fields["reuse_verdict"]
        assert field.default is dataclasses.MISSING
        assert field.default_factory is dataclasses.MISSING
        assert "ReuseVerdict" in str(field.type)

    def test_every_settle_path_supplies_its_own_verdict(self) -> None:
        """**Validates: Requirements 3.1**

        三条终结路径各自构造 `MaterializeOutcome`，每一处都必须**显式**给 `reuse_verdict`。
        AST 判据而不是跑三条路径：跑不到的那一条（例如 PG 缺失时）会静默漏掉。
        """
        tree = _tree(_COORDINATOR_PY)
        constructions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "MaterializeOutcome"
        ]
        assert len(constructions) == 4, (
            f"MaterializeOutcome 的构造处变成 {len(constructions)} 处 —— "
            "本判据按「三条终结路径 + materialize() 的最终改写」共 4 处立的"
        )
        for call in constructions:
            supplied = {kw.arg for kw in call.keywords}
            assert "reuse_verdict" in supplied, (
                f"第 {call.lineno} 行的 MaterializeOutcome 没给 reuse_verdict"
            )

    def test_the_verdict_is_computed_before_the_operation_is_opened(self) -> None:
        """**Validates: Requirements 3.1, 3.3**

        归因必须在**写任何东西之前**算完：`_open_operation` 之后世界已经前进，那时算出来的
        「基线」不再是判定时的基线。AST 上钉住 `materialize()` 里三件事的先后：
        `_find_business_identity_reuse` → `_classify_reuse_miss` → `_open_operation`。
        """
        fn = _func(_tree(_COORDINATOR_PY), "materialize")
        order: list[tuple[int, str]] = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in (
                    "_find_business_identity_reuse",
                    "_classify_reuse_miss",
                    "_open_operation",
                ):
                    order.append((node.lineno, node.func.attr))
        seen = [name for _, name in sorted(order)]
        assert seen == [
            "_find_business_identity_reuse",
            "_classify_reuse_miss",
            "_open_operation",
        ], f"materialize() 里的调用顺序是 {seen}"

    def test_both_metrics_are_registered_in_the_existing_catalog(self) -> None:
        """**Validates: Requirements 3.1**

        「落进既有 metrics（`workpaper_sync_*`）」的判据：走目录、走注册制、过目录自检 ——
        不是另起一套记数机制。
        """
        assert MX.validate_catalog() == ()
        for metric, domain in (
            (REUSE_METRIC, REUSE_RESULT_DOMAIN),
            (SINGLE_PASS_DECLINE_METRIC, SINGLE_PASS_DECLINE_DOMAIN),
        ):
            definition = MX.METRICS_BY_NAME[metric]
            assert metric.startswith("workpaper_sync_") and metric.endswith("_total")
            assert definition.kind is MX.MetricKind.counter
            assert tuple(definition.result_domain) == tuple(domain)
            # platform 级：复用判定是**内容身份**事实，与 room/participant 无关。
            assert definition.attribution is MX.AttributionClass.platform_scoped

    def test_the_recorder_accepts_every_result_and_rejects_anything_else(self) -> None:
        """**Validates: Requirements 3.1**

        封闭域真的被 `SyncMetrics` 执行：域内每个值都能记，域外一个字都记不进去。
        这条同时证明 emit 侧不可能悄悄多一个「其它」桶。
        """
        recorder = MX.SyncMetrics()
        labels = {"project_id": "p", "wp_id": "w", "entry_id": "e"}
        for result in REUSE_RESULT_DOMAIN:
            sample = recorder.record_outcome(
                REUSE_METRIC, result=result, landed=True, **labels
            )
            assert sample.result == result
        assert recorder.total(REUSE_METRIC) == len(REUSE_RESULT_DOMAIN)
        with pytest.raises(MX.MetricAttributionError):
            recorder.record_outcome(
                REUSE_METRIC, result="miss_whatever", landed=True, **labels
            )
        # platform 级归因维度缺失也必须拒（「记不准」不得 fail open）。
        with pytest.raises(MX.MetricAttributionError):
            recorder.record_outcome(REUSE_METRIC, result="hit", landed=True)

    def test_the_router_emits_the_verdict_on_the_materialize_endpoint(self) -> None:
        """**Validates: Requirements 3.1**

        接线判据：唯一 materialize 端点里必须有这两个 emit，且第一个实参解析出来就是目录里
        那两个名字。用 AST 而不是 `in source`：注释里写一遍指标名也能让 `in source` 通过。
        """
        fn = _func(_tree(_ROUTER_PY), "materialize")
        emitted = _emit_metric_names(fn)
        assert "<name:REUSE_METRIC>" in emitted, (
            f"materialize 端点没有 emit 复用判定，实得 {emitted} —— "
            "requirements 3.1 明说「而不是只写日志」"
        )
        assert "<name:SINGLE_PASS_DECLINE_METRIC>" in emitted
        # 常量名真的解析成目录里的指标（打错名字 ⇒ 永不 emit，而静态检查全绿）。
        import app.routers.wp_sync_router as router_module

        assert router_module.REUSE_METRIC in MX.METRICS_BY_NAME
        assert router_module.SINGLE_PASS_DECLINE_METRIC in MX.METRICS_BY_NAME
        assert router_module.REUSE_METRIC == REUSE_METRIC

    def test_the_emit_reads_the_result_off_the_verdict_and_not_a_default(self) -> None:
        """**Validates: Requirements 3.1**

        `result=` 必须取自 `outcome.reuse_verdict.metric_result`。
        `getattr(..., default)` / 字面量 / 三元表达式都不行 —— 那会把「字段名写错」变成
        「永远记成命中」，而四层静态检查全绿（本 spec 反复踩过的形态）。
        """
        fn = _func(_tree(_ROUTER_PY), "materialize")
        found: list[str] = []
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "record_outcome" or not node.args:
                continue
            first = node.args[0]
            if not (isinstance(first, ast.Name) and first.id == "REUSE_METRIC"):
                continue
            for kw in node.keywords:
                if kw.arg == "result":
                    found.append(ast.dump(kw.value))
        assert len(found) == 1, f"复用判定的 emit 应恰有一处，实得 {len(found)}"
        assert "attr='metric_result'" in found[0], found[0]
        assert "reuse_verdict" in found[0], found[0]
        assert "getattr" not in found[0]

    def test_the_verdict_serialises_for_logs_and_evidence(self) -> None:
        """**Validates: Requirements 3.1**

        「机器可读」也包括能进 JSON（证据文件 / 结构化日志 / 前端）。
        """
        verdict = verdict_for_miss(
            base_payload=_payload(_mini(Decimal("1"))),
            incoming_payload=_payload(_mini(Decimal("2"))),
            base_version_matched=False,
        )
        body = verdict.as_dict()
        assert body["decision"] == "miss"
        assert body["miss_reason"] == "content_changed"
        assert body["metric_result"] == "miss_content_changed"
        assert body["is_defect"] is False
        import json

        assert json.loads(json.dumps(body, ensure_ascii=False)) == body

    def test_a_miss_without_a_reason_cannot_be_constructed(self) -> None:
        """**Validates: Requirements 3.1, 3.3**

        「未命中但说不出为什么」必须在**构造上**不可表达 —— 那正是上一轮缺陷能藏住的条件。
        两侧都锁：miss 缺原因要抛，hit/replayed 带原因也要抛。
        """
        with pytest.raises(ValueError, match="必须带 miss_reason"):
            ReuseVerdict(decision=ReuseDecision.miss)
        with pytest.raises(ValueError, match="不得带 miss_reason"):
            ReuseVerdict(
                decision=ReuseDecision.hit,
                miss_reason=ReuseMissReason.content_changed,
            )
        assert MC.REUSE_HIT.decision is ReuseDecision.hit
        assert MC.REUSE_REPLAYED.decision is ReuseDecision.replayed
        assert MC.REUSE_HIT.reused and MC.REUSE_REPLAYED.reused


# ═══════════════════════════════════════════════════════════════════════════
# 第四类 miss：单趟 decline —— 折进来还是分开？（任务 3 遗留，见模块/设计附录 H.3）
# ═══════════════════════════════════════════════════════════════════════════


class TestSinglePassDeclineIsASeparateDimension:
    """裁定：**分开**。同一次 materialize 在两个维度上各落一格，互不覆盖。"""

    def test_the_two_result_domains_do_not_overlap(self) -> None:
        """**Validates: Requirements 3.3**

        「保持为两个维度」的机器判据：两个封闭域零交集。哪天有人把 decline 原因塞进复用
        result 域（或反之），这条会红。
        """
        assert set(REUSE_RESULT_DOMAIN) & set(SINGLE_PASS_DECLINE_DOMAIN) == set()
        assert REUSE_METRIC != SINGLE_PASS_DECLINE_METRIC

    def test_every_engine_decline_maps_to_a_registered_class(self) -> None:
        """**Validates: Requirements 3.3**

        `SinglePassDeclined.reason` 的每一种真实形态都要能归进封闭域。断言用的是**生产那一份**
        原因串（`_payload_conflict_decline_reason` 现算、其余照 raise 点的字面量），
        不在测试里抄一遍格式 —— 抄一遍的话「原因串改了」两边会一起错。
        """
        conflicts = ["xl/worksheets/sheet14.xml!C24 被 [a, b] 写且 payload 不同（差异字段 value）"]
        cases = {
            EM._payload_conflict_decline_reason(conflicts): "payload_conflict",
            "binding 集合为空": "empty_bindings",
            "binding d4 的写入策略是 openpyxl 全量重写（按文件改写）": "openpyxl_roundtrip",
            "binding d4 需要结构性插行（row_shift）—— 插行会位移其它 sheet": "row_shift",
            "binding 集合里没有主表 d4.revenue_detail": "missing_primary_binding",
        }
        for reason, expected in cases.items():
            assert classify_single_pass_decline(reason).value == expected, reason
        # 兜底格子存在，但不得被上面任何一条真实原因命中。
        assert classify_single_pass_decline("某种全新的回落原因").value == "unclassified"

    def test_the_engine_records_into_the_scope_and_is_a_noop_outside_it(self) -> None:
        """**Validates: Requirements 3.3**

        作用域语义：域内登记、域外**安全空操作**（观测设施不得让业务路径失败），
        嵌套沿用外层桶（一次请求里多趟物化的回落一并入册、不互相覆盖）。
        """
        # 域外：不抛、仍返回分型。
        assert record_single_pass_decline("binding 集合为空").value == "empty_bindings"
        with single_pass_decline_scope() as outer:
            record_single_pass_decline("binding 集合为空")
            with single_pass_decline_scope() as inner:
                assert inner is outer
                record_single_pass_decline("需要结构性插行（row_shift）")
            assert [m.value for m in outer] == ["empty_bindings", "row_shift"]
        # 退出后 ContextVar 必须还原（否则下一个请求会往别人的桶里记）。
        with single_pass_decline_scope() as fresh:
            assert fresh == []

    def test_the_adapter_records_the_decline_instead_of_emitting_a_metric(self) -> None:
        """**Validates: Requirements 3.3**

        engine 层的分工：登记分型 + 写日志，**不** emit。它拿不到 project_id/wp_id，emit 就
        只能编一个 scope（假归因）或绕过注册制自建第二个指标 —— 两条都被 metrics 家族明文
        否决。AST 上两侧都钉：`_try_single_pass_materialize` 里有
        `record_single_pass_decline`，且整个 adapter 文件里没有 `sync_metrics` 的 emit。
        """
        fn = _func(_tree(_ADAPTER_PY), "_try_single_pass_materialize")
        calls = {
            node.func.id
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "record_single_pass_decline" in calls
        source = _ADAPTER_PY.read_text(encoding="utf-8")
        assert "sync_metrics" not in source, (
            "adapter 里出现了 sync_metrics —— engine 层没有 scope，emit 必然是假归因"
        )

    def test_the_router_emits_one_decline_sample_per_recorded_decline(self) -> None:
        """**Validates: Requirements 3.3**

        emit 侧：逐条记而不是「记一个布尔」。AST 确认 decline 的 emit 在一个 `for` 循环体内
        （一次请求可能有多趟物化），且循环变量来自作用域返回的桶。
        """
        fn = _func(_tree(_ROUTER_PY), "materialize")
        loops = [node for node in ast.walk(fn) if isinstance(node, ast.For)]
        hosting = [
            loop
            for loop in loops
            if "<name:SINGLE_PASS_DECLINE_METRIC>" in _emit_metric_names(loop)
        ]
        assert len(hosting) == 1, "decline 的 emit 应恰在一个 for 循环体内"
        assert isinstance(hosting[0].iter, ast.Name)
        withs = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.With)
            and any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "single_pass_decline_scope"
                for item in node.items
            )
        ]
        assert len(withs) == 1, "materialize 端点应恰有一处 single_pass_decline_scope"
        bound = {
            item.optional_vars.id
            for node in withs
            for item in node.items
            if isinstance(item.optional_vars, ast.Name)
        }
        assert hosting[0].iter.id in bound, (
            f"decline 循环迭代的是 {hosting[0].iter.id}，不是作用域返回的桶 {bound}"
        )

    def test_the_scope_wraps_the_materialize_call(self) -> None:
        """**Validates: Requirements 3.3**

        作用域必须**包住** `coordinator.materialize(...)` —— decline 发生在它内部，
        作用域开在它之后就一条都收不到（而判据若只看「有作用域」会绿）。
        """
        fn = _func(_tree(_ROUTER_PY), "materialize")
        for node in ast.walk(fn):
            if not isinstance(node, ast.With):
                continue
            if not any(
                isinstance(item.context_expr, ast.Call)
                and isinstance(item.context_expr.func, ast.Name)
                and item.context_expr.func.id == "single_pass_decline_scope"
                for item in node.items
            ):
                continue
            inner = {
                child.func.attr
                for child in ast.walk(node)
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
            }
            assert "materialize" in inner, (
                "single_pass_decline_scope 没有包住 coordinator.materialize(...)"
            )
            return
        raise AssertionError("materialize 端点里找不到 single_pass_decline_scope")


# ═══════════════════════════════════════════════════════════════════════════
# 承重反证：把 digest 口径退回改动前 ⇒ 这条链必须变成缺陷类未命中
# ═══════════════════════════════════════════════════════════════════════════


class TestTheChainIsLoadBearing:
    """留着全绿只说明「没坏」。这一节证明判据**承重**。"""

    def test_reverting_the_digest_caliber_turns_the_chain_into_a_defect_miss(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2, 3.3**

        design 五 P6 点名的反证方式：「把 digest 口径改回裸 `json_safe` ⇒ 第二次走全量 ⇒ 红」。
        本条把它做成自动判据，并且比原措辞更严 —— 不只要求「走全量」，还要求归因恰好是
        **缺陷类**，且业务比较面在同一份输入上报 0 差异（218 个字段逐键全等）。

        那正是 2026-09-22 真栈的形态（899 键全等、canonical 字节 121485 vs 121487、
        digest `ecb4f807…` vs `f22f1e75…`），本判据在 D4 harness 的 218 字段上复现它。
        """
        with digest_caliber_reverted():
            base, incoming = _payload(chain.committed), _payload(chain.rederived)
            assert _digest(chain.committed) != _digest(chain.rederived), (
                "退回旧口径后两侧 digest 仍相等 —— 说明运行时替换没生效，本反证是空转"
            )
            comparison = compare_projection_payloads(base, incoming)
            assert comparison.identical, (
                f"业务比较面报了 {comparison.difference_count} 处差异 —— "
                "那说明它不是表示无关的，缺陷类因此不可达"
            )
            verdict = verdict_for_miss(
                base_payload=base, incoming_payload=incoming, base_version_matched=False
            )
        assert verdict.decision is ReuseDecision.miss
        assert verdict.miss_reason is ReuseMissReason.digest_representation_drift
        assert verdict.is_defect is True
        assert verdict.compared_field_count == 218
        assert verdict.metric_result == "miss_digest_representation_drift"

    def test_the_caliber_is_restored_after_the_reversal(self, chain: ReuseChain) -> None:
        """**Validates: Requirements 3.2**

        反证不得留后遗症：退出作用域后同一条链必须重新命中（否则后续判据会在一个被污染的
        进程里跑，而污染的方向恰好是「让缺陷类恒真」）。
        """
        assert CM.canonical_value_for_digest.__module__ == (
            "app.services.workpaper_sync.projection_digest_value"
        )
        assert _verdict_for(chain.committed, chain.rederived).decision is (
            ReuseDecision.hit
        )

    def test_the_boolean_fields_alone_are_enough_to_break_reuse(
        self, chain: ReuseChain
    ) -> None:
        """**Validates: Requirements 3.2**

        本任务的实测发现（design 附录 H.2）做成判据：真库 D4 上**只**那 4 个 boolean 字段
        存在表示差异，所以它们**独自**就足以让复用恒不命中 —— 换句话说
        `canonical_value_for_digest` 在 D4 上今天就在承重，不是为将来准备的。

        做法：只把那 4 个字段按旧口径序列化、其余全按新口径，digest 仍必须分叉。
        """
        drifted = [
            "undisclosed_rp_rows/GTROW-D427-0015/is_customer_legal",
            "undisclosed_rp_rows/GTROW-D427-0015/is_production_dept",
            "undisclosed_rp_rows/GTROW-D427-0016/is_finance_dept",
            "undisclosed_rp_rows/GTROW-D427-0016/is_personal_customer",
        ]
        original = CM.canonical_value_for_digest

        def partial(field: Any) -> Any:
            if str(field.stable_key) in drifted:
                return json_safe(field.value)  # 旧口径
            return original(field)

        CM.canonical_value_for_digest = partial
        try:
            left, right = _digest(chain.committed), _digest(chain.rederived)
        finally:
            CM.canonical_value_for_digest = original
        assert left != right, (
            "只退化那 4 个 boolean 字段的口径后 digest 仍相等 —— "
            "那说明 H.2 的实测前提（恰这 4 个字段存在表示差异）已经变了，本判据要重新量"
        )
        assert _digest(chain.committed) == _digest(chain.rederived)

    def test_folding_everything_is_not_an_acceptable_way_to_pass(self) -> None:
        """**Validates: Requirements 3.3**

        另一侧的承重：如果口径改成「什么都折叠」（例如一律返回常量），等价表示那一组会全绿，
        但**异义值**那一组必须红。这条把 CI 门第 ① 段的两组配对关系钉在判据里。
        """
        original = CM.canonical_value_for_digest
        CM.canonical_value_for_digest = lambda field: "<folded>"
        try:
            same = _digest(_mini(Decimal("1"))) == _digest(_mini(Decimal("2")))
        finally:
            CM.canonical_value_for_digest = original
        assert same, "预期「全折叠」会让异义值同 digest —— 反证前提不成立"
        assert _digest(_mini(Decimal("1"))) != _digest(_mini(Decimal("2")))


class TestTheCiGateIsWiredAndFires:
    """requirements 3.3 的「在 CI 里直接判红」：门存在、可离线跑、且真的会红。"""

    def test_the_gate_script_exists_and_passes_on_healthy_code(self) -> None:
        """**Validates: Requirements 3.3**"""
        gate = _BACKEND / "scripts" / "check" / "check_materialize_reuse_digest_caliber.py"
        assert gate.exists()
        module = _load_gate(gate)
        assert module.main() == 0

    def test_the_gate_fires_when_the_caliber_regresses(self) -> None:
        """**Validates: Requirements 3.3**

        门的承重反证：同一段口径退化下，门必须 `exit 1`，且报出来的是**口径分叉**那一类
        （不是随便红一下）。这是「digest 口径不一致这一类在 CI 判红」的直接实测。
        """
        gate = _BACKEND / "scripts" / "check" / "check_materialize_reuse_digest_caliber.py"
        module = _load_gate(gate)
        with digest_caliber_reverted():
            problems = module._check_digest_caliber()
            assert module.main() == 1
        assert problems, "退化口径下门一条都没报 —— 那门是空的"
        assert all("[口径分叉]" in problem for problem in problems)
        assert len(problems) == len(module._EQUIVALENT_PAIRS), (
            f"只有 {len(problems)}/{len(module._EQUIVALENT_PAIRS)} 组等价表示被报出 —— "
            "矩阵里有配对在旧口径下也相等，那几组对本门没有判别力"
        )
        assert module.main() == 0, "门在口径恢复后仍是红的 —— 说明它有残留状态"

    def test_the_gate_is_registered_in_the_governance_workflow(self) -> None:
        """**Validates: Requirements 3.3**

        门不进 CI 就只是个脚本。这里断言 workflow 里真的有一行跑它 —— 并且**不带**
        `|| true` / `continue-on-error`（带了就不判红了，requirements 3.3 要的正是判红）。
        """
        import yaml

        path = _BACKEND.parent / ".github" / "workflows" / "governance-checks.yml"
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        assert "materialize-reuse-digest-caliber" in jobs, (
            "governance-checks.yml 里没有 materialize-reuse-digest-caliber 这个 job —— "
            "门不进 CI 就只是个脚本"
        )
        job = jobs["materialize-reuse-digest-caliber"]
        # 🔴 解析 YAML 而不是切字符串：注释里提一句脚本名也能让「字符串包含」通过。
        runs = [str(step.get("run") or "") for step in job["steps"]]
        gate_steps = [
            run for run in runs if "check_materialize_reuse_digest_caliber.py" in run
        ]
        assert len(gate_steps) == 1, f"跑本门的步骤应恰有一条，实得 {gate_steps}"
        assert "|| true" not in gate_steps[0], "门被 `|| true` 掐成不判红了"
        assert job.get("continue-on-error") is not True
        assert all(step.get("continue-on-error") is not True for step in job["steps"])
        # 判据文件本身也必须在 CI 里跑（否则 falsifier 只在本机有效）。
        assert any(
            "test_materialize_reuse_observability.py" in run for run in runs
        ), "workflow 没有跑本判据文件"


def _load_gate(path: Path) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("_reuse_gate_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_second_reuse_verdict_vocabulary_exists() -> None:
    """**Validates: Requirements 3.1**

    单源：判词、封闭域、缺陷集合只有 `materialize_reuse_verdict` 一份。
    coordinator / router / metrics / CI 门四处都**引用**它，谁都不得自己抄一份枚举。

    判法是「谁 import 了它」而不是「谁没有字面量」：后者会被注释与 docstring 里的示例误伤
    （本 spec 的判据里到处是这些名字）。
    """
    consumers = {
        _COORDINATOR_PY: ("verdict_for_miss", "ReuseVerdict"),
        _ROUTER_PY: ("REUSE_METRIC", "SINGLE_PASS_DECLINE_METRIC"),
    }
    for path, names in consumers.items():
        imported: set[str] = set()
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(
                "materialize_reuse_verdict"
            ):
                imported.update(alias.name for alias in node.names)
        missing = sorted(set(names) - imported)
        assert not missing, f"{path.name} 没有从 materialize_reuse_verdict import {missing}"
    assert inspect.getmodule(verdict_for_miss).__name__.endswith(
        "materialize_reuse_verdict"
    )
    assert MX.REUSE_METRIC is REUSE_METRIC if hasattr(MX, "REUSE_METRIC") else True
