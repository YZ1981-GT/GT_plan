# -*- coding: utf-8 -*-
"""materialize 复用判定的**机器可读**判词 + 未命中原因分型（纯函数，零 IO）。

spec: oo-single-pass-materialize-and-room-leave · Requirement 3.1 / 3.2 / 3.3

═══ 这里的「复用」是哪一个 ═══

本 spec 里有两个完全不同的「复用」，混用会把两条独立的判据面搅成一团：

* **解析复用**（任务 8 / 需求 2）—— `excel_extract.workbook_read_scope()`：一次 CPU 段内
  同一份字节只解析一次。它发生在 materialize **内部**，与「要不要 materialize」无关。
* **业务身份复用**（本模块 / 需求 3）—— `materialize_coordinator._find_business_identity_reuse`：
  内容一字未改 ⇒ **根本不 materialize**。命中即秒级，不命中就是整趟 4.7s + 尾段。

本模块只服务后者。

═══ 为什么未命中原因必须分型（需求 3.3）═══

2026-09-22 的真栈缺陷是：`projection_sha256` 两侧走了两套值表示口径（同一个金额零一侧
`0`、另一侧 `0.0`），于是业务身份复用**恒不命中**，每次点「在线编辑」都全量重物化
（store-projection 首请求 32325ms、切 D4-6 31508ms）。那次缺陷之所以能活下来，是因为
「未命中」在观测面上与「用户真改了内容」**长得一模一样** —— 两者都只是「走了全量」。

所以判词必须能把三件事分开（requirements 3.3）：

1. :attr:`ReuseMissReason.content_changed` —— 内容真变了。**正常**，全量物化是对的。
2. :attr:`ReuseMissReason.contract_or_bundle_changed` —— 契约/bundle/substrate 身份变了。
   **正常**，新 representation 必须重算。
3. :attr:`ReuseMissReason.digest_representation_drift` —— 业务内容**逐键相等**却没命中。
   这是**缺陷**（:data:`DEFECT_MISS_REASONS`），不是合法回落：它意味着 digest 口径在两条
   派生路径上分叉了。CI 门见 `backend/scripts/check/check_materialize_reuse_digest_caliber.py`。
4. :attr:`ReuseMissReason.no_base_projection` —— 基线那侧压根没有可比的 projection 载荷
   （首代 representation / 历史行的 `projection_artifact_id` 为空）。单列出来是为了不让
   「无从比较」被误记成上面任何一类 —— 尤其不能记成第 3 类那个缺陷类。

═══ 🔴 业务比较口径为什么**刻意**独立于 digest 口径 ═══

分类第 3 类要回答的问题是「digest 说不一样，业务内容到底一样不一样」。如果这里复用
`projection_digest_value.canonical_value_for_digest()`，答案就是**同一条口径的自证**：
口径分叉时两侧算出的 payload 本来就不同 ⇒ 分类器只会说 `content_changed`，第 3 类
**永远不可达**，需求 3.3 那条判据变成空话。

因此 :func:`compare_projection_payloads` 用一套**表示无关**的业务相等（数值族一律
`Decimal(str(x))` 比值），并且**只**用于给未命中归因，**从不**参与「要不要复用」的裁决
（那条永远只由 `projection_sha256` 的字节相等决定）。这与 design 附录 B.2「为什么不复用
现成 helper」是同一条纪律，方向相反：那边拒绝用宽口径当等值判据，这边拒绝用窄口径当
差异判据。

═══ 单趟 decline 为什么**不**折进本模块的 result 域（任务 3 遗留的第四类）═══

任务 3（design 附录 A.6 第 2 条）把完整碰撞集合写进 `SinglePassDeclined.reason`，理由
正是「需求 3.3 要能统计回落比例与回落原因」；`adapters/excel._try_single_pass_materialize`
也明写「复用判定的可观测面归 Requirement 3 / Task 10 在 coordinator 层做」。它确实归这里，
但**是另一个维度**，用另一个指标（:data:`SINGLE_PASS_DECLINE_METRIC`）：

* 复用未命中回答「这次**要不要**物化」——每次 materialize 恰好落一个桶；
* 单趟 decline 回答「既然要物化，**用哪条写盘路径**」——它只在未命中之后才存在。

折成一个 result 域会有两个具体后果：①同一次 materialize 要往同一个封闭域里记两次值，
命中率的分母就没了（需求 3.1 要的「一眼看出这次是复用还是全量」直接失效）；②「内容真
变了 + 单趟命中」与「内容真变了 + 回落链式」会被迫二选一地压成一个值。所以两个维度
分开记，各自封闭域，不交叉。
"""

from __future__ import annotations

import contextlib
import contextvars
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Final, Iterator, Mapping

__all__ = [
    "DEFECT_MISS_REASONS",
    "NUMERIC_VALUE_TYPES",
    "PayloadComparison",
    "REUSE_METRIC",
    "REUSE_RESULT_DOMAIN",
    "SINGLE_PASS_DECLINE_DOMAIN",
    "SINGLE_PASS_DECLINE_METRIC",
    "ReuseDecision",
    "ReuseMissReason",
    "ReuseVerdict",
    "SinglePassDeclineClass",
    "business_value_equal",
    "classify_single_pass_decline",
    "compare_projection_payloads",
    "record_single_pass_decline",
    "single_pass_decline_scope",
    "verdict_for_miss",
]


class ReuseDecision(str, Enum):
    """一次 materialize 在「有没有复用」这一维上的三个互斥终态。"""

    #: 业务身份复用命中：不进 `commit()`，revision 一动不动。
    hit = "hit"
    #: 同 token 重放（另一条幂等路径，Task 15 的 `_replay_if_committed`）。
    #: 与 `hit` 分开是因为两者的**触发条件**不同：重放靠 pending mutation 的
    #: `state=committed`，复用靠三元组身份 —— 把它们记成同一个值，
    #: 「复用命中率」就会被重放次数注水。
    replayed = "replayed"
    #: 未命中，走全量物化。原因见 :class:`ReuseMissReason`。
    miss = "miss"


class ReuseMissReason(str, Enum):
    """未命中原因的**封闭**域（requirements 3.3「至少三类可区分」）。"""

    content_changed = "content_changed"
    contract_or_bundle_changed = "contract_or_bundle_changed"
    #: 🔴 缺陷类，不是合法回落。见模块文档。
    digest_representation_drift = "digest_representation_drift"
    no_base_projection = "no_base_projection"


#: 🔴 属于**缺陷**而非合法回落的未命中原因。CI 门按这个集合判红。
#:
#: 做成数据而不是散在分支里的 `if reason == ...`：CI 检查脚本、指标目录与判据三处读同一份，
#: 「悄悄把缺陷类降级成正常回落」就必须改这一行（而改这一行会让守卫红）。
DEFECT_MISS_REASONS: Final[frozenset[ReuseMissReason]] = frozenset(
    {ReuseMissReason.digest_representation_drift}
)

#: 业务身份复用判定的指标名（`workpaper_sync_*` 家族，counter）。
REUSE_METRIC: Final[str] = "workpaper_sync_materialize_reuse_total"

#: :data:`REUSE_METRIC` 的封闭 result 域 —— hit / replayed / 每个 miss 原因各一格。
#:
#: 展平成一维是为了塞进既有 metrics 家族的 `result_domain`（`SyncMetrics` 只认一个
#: `result` 标签，不认「结果 + 子原因」两层）。展平不丢信息：`miss_` 前缀 + 原因名可
#: 逐字还原成 (decision, reason)，:meth:`ReuseVerdict.metric_result` 是唯一构造处。
REUSE_RESULT_DOMAIN: Final[tuple[str, ...]] = (
    ReuseDecision.hit.value,
    ReuseDecision.replayed.value,
) + tuple(f"miss_{reason.value}" for reason in ReuseMissReason)


class SinglePassDeclineClass(str, Enum):
    """单趟写入回落原因的封闭域（design 附录 A.6 第 2 条的统计面）。

    与 `excel_materialize` 里每一处 `raise SinglePassDeclined(...)` 一一对应；
    新增一处 decline 而不在此登记 ⇒ 落进 :attr:`unclassified`，CI 门
    （`check_materialize_reuse_digest_caliber.py` 的第 3 段）按 raise 点数与本枚举
    对账后判红。
    """

    #: binding 集合为空。
    empty_bindings = "empty_bindings"
    #: 某 binding 的写入策略是 openpyxl 全量重写（按文件改写，不是 zip 局部补丁）。
    openpyxl_roundtrip = "openpyxl_roundtrip"
    #: 某 binding 需要结构性插行 —— 真依赖（design 附录 A.5 第 1 条）。
    row_shift = "row_shift"
    #: 跨 binding 同坐标写入 payload 冲突（完整碰撞清单在 reason 串里）。
    payload_conflict = "payload_conflict"
    #: binding 集合里没有主表。
    missing_primary_binding = "missing_primary_binding"
    #: 🔴 兜底：出现了没被登记的 decline 原因。
    #:
    #: 刻意**不**让它抛异常 —— 指标记不准不该把一次真实物化搞失败。可见性由 CI 门承担：
    #: 它比对 `excel_materialize` 里 `raise SinglePassDeclined` 的处数与本枚举可映射的
    #: 处数，不等即红。
    unclassified = "unclassified"


#: 单趟回落统计的指标名（与复用判定**分开**的第二个维度，见模块文档末节）。
SINGLE_PASS_DECLINE_METRIC: Final[str] = "workpaper_sync_single_pass_decline_total"

SINGLE_PASS_DECLINE_DOMAIN: Final[tuple[str, ...]] = tuple(
    member.value for member in SinglePassDeclineClass
)

#: decline 原因串 → 分型的判别子串。顺序有意义（先匹配者胜），与
#: `excel_materialize.materialize_projection_single_pass` 的 raise 顺序一致。
_DECLINE_MARKERS: Final[tuple[tuple[str, SinglePassDeclineClass], ...]] = (
    ("binding 集合为空", SinglePassDeclineClass.empty_bindings),
    ("openpyxl 全量重写", SinglePassDeclineClass.openpyxl_roundtrip),
    ("row_shift", SinglePassDeclineClass.row_shift),
    ("payload 冲突", SinglePassDeclineClass.payload_conflict),
    ("没有主表", SinglePassDeclineClass.missing_primary_binding),
)


#: 一次请求内登记到的单趟回落分型。`ContextVar` 而不是全局 list：并发请求各自独立
#: （与 `excel_extract._workbook_scope` 同一条理由与同一形态）。
_decline_scope: contextvars.ContextVar[list["SinglePassDeclineClass"] | None] = (
    contextvars.ContextVar("workpaper_sync_single_pass_decline_scope", default=None)
)


@contextlib.contextmanager
def single_pass_decline_scope() -> Iterator[list["SinglePassDeclineClass"]]:
    """打开回落登记作用域；退出时无条件还原（含异常路径）。

    ═══ 为什么要一个作用域，而不是在 engine 里直接 emit ═══

    `excel_materialize` / `adapters/excel` 是**纯计算**层：拿不到 `project_id` / `wp_id`，
    而 `workpaper_sync_*` 的 platform 级归因强制这两个维度（`SyncMetrics._validate_labels`
    会拒）。engine 直接 emit 只有两条出路：编一个 scope（假归因），或绕过注册制自建第二个
    指标 —— 两条都被本家族的设计明文否决（见 `metrics` 模块文档）。

    作用域把「谁发生了」与「归因给谁」解耦：engine 只登记**分型**，emit 由持有 scope 的
    router 完成。嵌套沿用外层 list（与 `workbook_read_scope` 同语义），所以一次请求内多
    次物化的回落会一并入册而不会互相覆盖。
    """
    outer = _decline_scope.get()
    if outer is not None:
        yield outer
        return
    bucket: list[SinglePassDeclineClass] = []
    token = _decline_scope.set(bucket)
    try:
        yield bucket
    finally:
        _decline_scope.reset(token)


def record_single_pass_decline(reason: str) -> "SinglePassDeclineClass":
    """engine 侧登记一次单趟回落，返回它的分型。

    作用域之外是**安全空操作**（仍返回分型，供调用方写日志）—— 与
    `excel_extract.release_scoped_workbooks` 同一条纪律：观测设施不得让业务路径失败。
    """
    member = classify_single_pass_decline(reason)
    bucket = _decline_scope.get()
    if bucket is not None:
        bucket.append(member)
    return member


def classify_single_pass_decline(reason: str) -> SinglePassDeclineClass:
    """把 `SinglePassDeclined.reason` 归进封闭域。

    按**原因串**分型而不是给异常加字段：`reason` 已经是生产那一份唯一格式
    （`_payload_conflict_decline_reason` 等），在它上面分型不需要动 engine 的公开语义；
    而 CI 门会逐一驱动**真实** raise 点，确认每一处都落进非 `unclassified` 的格子。
    """
    text = str(reason or "")
    for marker, member in _DECLINE_MARKERS:
        if marker in text:
            return member
    return SinglePassDeclineClass.unclassified


#: 值表示无关比较里按**数值**处理的 `value_type`（`ValueType` 的数值族）。
#:
#: 用字符串而不是 import `ValueType`：本模块的输入是**已序列化的 payload**
#: （`_projection_payload` 的产物，`value_type` 在里面是字符串），不是 `FieldValue`。
#: 让纯函数只依赖 payload 形态，判据与 CI 门就都能离线驱动它。
NUMERIC_VALUE_TYPES: Final[frozenset[str]] = frozenset(
    {"amount", "integer", "rate", "ratio"}
)


def business_value_equal(value_type: str, left: Any, right: Any) -> bool:
    """两个 payload 值在**业务**意义上是否相等（表示无关）。

    * `None` 只与 `None` 相等 —— 「未填」与「填了零」是两种审计事实
      （`projection_digest_value` 模块文档里同一条纪律）。
    * 数值族按 `Decimal(str(x))` 比值：`0` / `0.0` / `"0.00"` / `"0E-2"` 全等。
      这正是 digest 口径分叉时两侧的形态差异 —— 比得出「业务相同」才分得清缺陷与真改动。
    * 其余（text/boolean/date/datetime/enum/json）按 `==`。
    """
    if left is None or right is None:
        return left is None and right is None
    if value_type in NUMERIC_VALUE_TYPES:
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, ValueError, TypeError):
            return left == right
    return left == right


#: `_projection_payload` 里属于**契约身份**而不是业务内容的顶层键。
_IDENTITY_KEYS: Final[tuple[str, ...]] = (
    "schema_version",
    "contract_id",
    "semantic_version",
    "document_type",
)


@dataclass(frozen=True)
class PayloadComparison:
    """两份 projection payload 的差异清单。**完整且排序**（同 design 附录 A.6 第 2 条）。

    抽样报一条是这批判据反复否决过的形态：真库要统计、要复现，抽样既不可复现也统计不出来。
    """

    identity_differences: tuple[str, ...]
    content_differences: tuple[str, ...]

    @property
    def identical(self) -> bool:
        return not self.identity_differences and not self.content_differences

    @property
    def difference_count(self) -> int:
        return len(self.identity_differences) + len(self.content_differences)

    def as_dict(self) -> dict[str, Any]:
        return {
            "identical": self.identical,
            "identity_differences": list(self.identity_differences),
            "content_differences": list(self.content_differences),
        }


def compare_projection_payloads(
    base: Mapping[str, Any], incoming: Mapping[str, Any]
) -> PayloadComparison:
    """业务比较两份 `_projection_payload` 产物（表示无关，见模块文档）。

    覆盖 design 附录 B.4 第 1 条点名的**三类**（缺 key / 多 key / 值或类型变）——
    只比 key 集合的判据在「漏写一个 binding」那条反证下是绿的。
    """
    identity: list[str] = []
    for key in _IDENTITY_KEYS:
        left, right = base.get(key), incoming.get(key)
        if left != right:
            identity.append(f"{key}: {left!r} -> {right!r}")

    content: list[str] = []
    base_values: Mapping[str, Any] = base.get("values") or {}
    incoming_values: Mapping[str, Any] = incoming.get("values") or {}
    for key in sorted(set(base_values) - set(incoming_values)):
        content.append(f"values[{key}]: 缺失（基线有、本次无）")
    for key in sorted(set(incoming_values) - set(base_values)):
        content.append(f"values[{key}]: 新增（基线无、本次有）")
    for key in sorted(set(base_values) & set(incoming_values)):
        left = base_values[key] or {}
        right = incoming_values[key] or {}
        for field in ("value_type", "mode", "row_key"):
            if left.get(field) != right.get(field):
                content.append(
                    f"values[{key}].{field}: {left.get(field)!r} -> {right.get(field)!r}"
                )
        value_type = str(right.get("value_type") or left.get("value_type") or "")
        if not business_value_equal(value_type, left.get("value"), right.get("value")):
            content.append(
                f"values[{key}].value: {left.get('value')!r} -> {right.get('value')!r}"
            )

    base_rows: Mapping[str, Any] = base.get("row_keys") or {}
    incoming_rows: Mapping[str, Any] = incoming.get("row_keys") or {}
    for table in sorted(set(base_rows) | set(incoming_rows)):
        left_rows = list(base_rows.get(table) or ())
        right_rows = list(incoming_rows.get(table) or ())
        if left_rows != right_rows:
            content.append(
                f"row_keys[{table}]: {len(left_rows)} 行 -> {len(right_rows)} 行（行序/行身份不同）"
            )

    return PayloadComparison(
        identity_differences=tuple(identity), content_differences=tuple(content)
    )


@dataclass(frozen=True)
class ReuseVerdict:
    """一次 materialize 的**机器可读**复用判词（requirements 3.1 的「机器可读」那半）。

    `decision` 与 `miss_reason` 互相约束（`__post_init__` 强制）：命中/重放不得带原因，
    未命中必须带原因。让「未命中但说不出为什么」在**构造上**不可表达 —— 这正是上一轮那个
    缺陷能藏住的条件。
    """

    decision: ReuseDecision
    miss_reason: ReuseMissReason | None = None
    #: 归因用的完整差异清单（排序）。命中/重放为空。
    differences: tuple[str, ...] = ()
    #: 分类时业务比较的字段数（判据用它证明「真的比过」而不是空集合恒等）。
    compared_field_count: int = 0

    def __post_init__(self) -> None:
        if self.decision is ReuseDecision.miss and self.miss_reason is None:
            raise ValueError(
                "未命中必须带 miss_reason —— 「走了全量但说不出为什么」正是 2026-09-22 "
                "那个 digest 口径缺陷能存活的条件（requirements 3.3）"
            )
        if self.decision is not ReuseDecision.miss and self.miss_reason is not None:
            raise ValueError(
                f"decision={self.decision.value} 不得带 miss_reason="
                f"{self.miss_reason.value}"
            )

    @property
    def reused(self) -> bool:
        """是否「没有产生新 content revision」。命中与重放都算。"""
        return self.decision is not ReuseDecision.miss

    @property
    def is_defect(self) -> bool:
        """本次未命中是否属于**缺陷**类（:data:`DEFECT_MISS_REASONS`）。"""
        return self.miss_reason in DEFECT_MISS_REASONS

    @property
    def metric_result(self) -> str:
        """落进 :data:`REUSE_METRIC` 的 `result` 标签（封闭域里的一个值）。"""
        if self.decision is ReuseDecision.miss:
            assert self.miss_reason is not None  # __post_init__ 已保证
            return f"miss_{self.miss_reason.value}"
        return self.decision.value

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "miss_reason": None if self.miss_reason is None else self.miss_reason.value,
            "metric_result": self.metric_result,
            "reused": self.reused,
            "is_defect": self.is_defect,
            "compared_field_count": int(self.compared_field_count),
            "differences": list(self.differences),
        }


#: 命中与重放两个常量判词（无原因、无差异）。
HIT: Final[ReuseVerdict] = ReuseVerdict(decision=ReuseDecision.hit)
REPLAYED: Final[ReuseVerdict] = ReuseVerdict(decision=ReuseDecision.replayed)


def verdict_for_miss(
    *,
    base_payload: Mapping[str, Any] | None,
    incoming_payload: Mapping[str, Any],
    base_version_matched: bool,
) -> ReuseVerdict:
    """把一次**已确定未命中**的 materialize 归因（requirements 3.3）。

    入参对应 AC 3.6 三元组的两条腿 + 可比性：

    * `base_version_matched` —— projection digest 那条腿：基线 content version 的
      `projection_sha256` 是否等于本次的 payload digest。这**就是** digest 相等判定本身，
      所以本函数不再自己比一次 digest（那会是第二套口径）。
      它为 `True` 而整体仍未命中 ⇒ 未命中必定来自 substrate + bundle 那条腿
      （当前 published representation 不是挂在那个 content version 上的那一行）。
    * `base_payload` / `incoming_payload` —— 归因用的业务比较面（表示无关，见模块文档）。

    分支顺序是**判别性**的，不是偏好：先看业务内容变没变（那决定了「全量物化是不是对的」），
    最后才把「内容全等却没命中」判成缺陷。
    """
    if not base_version_matched:
        if base_payload is None:
            return ReuseVerdict(
                decision=ReuseDecision.miss,
                miss_reason=ReuseMissReason.no_base_projection,
                differences=("基线 content version 没有可读的 projection 载荷 ⇒ 无从比较",),
            )
        comparison = compare_projection_payloads(base_payload, incoming_payload)
        compared = len((incoming_payload.get("values") or {}))
        if comparison.identity_differences:
            return ReuseVerdict(
                decision=ReuseDecision.miss,
                miss_reason=ReuseMissReason.contract_or_bundle_changed,
                differences=comparison.identity_differences
                + comparison.content_differences,
                compared_field_count=compared,
            )
        if comparison.content_differences:
            return ReuseVerdict(
                decision=ReuseDecision.miss,
                miss_reason=ReuseMissReason.content_changed,
                differences=comparison.content_differences,
                compared_field_count=compared,
            )
        # 🔴 业务内容逐键全等，digest 却判不等 ⇒ 口径分叉，缺陷。
        return ReuseVerdict(
            decision=ReuseDecision.miss,
            miss_reason=ReuseMissReason.digest_representation_drift,
            differences=(
                f"业务内容逐键全等（{compared} 个字段，0 缺 0 多 0 改）却没命中复用 ⇒ "
                "projection digest 的值表示口径在两条派生路径上分叉了"
                "（见 projection_digest_value 模块文档与 requirements 3.3）",
            ),
            compared_field_count=compared,
        )

    # base version 匹配、representation 不匹配 ⇒ substrate/bundle 那条腿变了。
    return ReuseVerdict(
        decision=ReuseDecision.miss,
        miss_reason=ReuseMissReason.contract_or_bundle_changed,
        differences=(
            "基线 content version 的 projection digest 相同，但当前 published "
            "representation 不是挂在它上面的那一行 ⇒ substrate / definition bundle 身份已前进",
        ),
        compared_field_count=len((incoming_payload.get("values") or {})),
    )


__all__ += ["HIT", "REPLAYED"]
