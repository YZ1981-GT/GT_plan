"""Lane 裁决的**单一真源** —— projection vs opaque vs undecided。

本模块不复制任何一份来源列表；它只读取既有真源并据此裁决。

**Spec: published-representation-production-path-and-lane-adjudication**
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7 (Task 1.1)
Requirements: 1.8, 1.9 (Task 1.3)
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import SyncDomainError

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class LaneRegistryError(SyncDomainError):
    """lane 裁决域异常基类。"""
    error_code = "lane_registry_error"


class LaneIsOpaqueError(LaneRegistryError):
    """entry 属于 opaque lane —— 这不是错误，但 ``assert_projection_lane`` 调用者
    认为它应该是 projection。

    :attr:`lane_id` 是**可编程**属性：调用方要按命中的 lane 分流时不必去 parse
    错误文案（文案会改，属性不会）。
    """
    error_code = "lane_is_opaque"

    def __init__(self, message: str, *, entry_id: str = "", lane_id: str = "") -> None:
        super().__init__(message)
        self.entry_id = entry_id
        self.lane_id = lane_id


class LaneUndecidedError(LaneRegistryError):
    """判据不足 —— fail closed。

    :attr:`criterion_number` / :attr:`source_path` 是**可编程**属性，与错误文案
    同源（都由 :class:`_UndecidedDiagnostic` 派生），不是各写一遍。
    """
    error_code = "lane_undecided"

    def __init__(
        self,
        message: str,
        *,
        entry_id: str = "",
        criterion_number: int | None = None,
        criterion_label: str = "",
        source_path: str = "",
    ) -> None:
        super().__init__(message)
        self.entry_id = entry_id
        self.criterion_number = criterion_number
        self.criterion_label = criterion_label
        self.source_path = source_path


class LaneSupplyObservationError(LaneRegistryError):
    """四条供给判据取数时发生异常 —— **不**降级为 False。"""
    error_code = "lane_supply_observation_failed"


class OpaqueLaneCoverageDriftError(LaneRegistryError):
    """L1 形态表与 ``OPAQUE_AUTHORITY_LANES`` 不一致。"""
    error_code = "opaque_lane_coverage_drift"


# ---------------------------------------------------------------------------
# LaneVerdict 封闭三值枚举
# ---------------------------------------------------------------------------


class LaneVerdict(str, Enum):
    """选路裁决的封闭三值域。

    ``str`` 基类让它可直接 JSON 序列化（``json.dumps({"lane": LaneVerdict.opaque})``
    得到 ``"opaque"``）。
    """

    projection = "projection"
    """权威 = 受管 projection，OOXML 由 adapter materialize。"""

    opaque = "opaque"
    """权威 = OOXML 本体，无受管 projection。"""

    undecided = "undecided"
    """判据不足 —— fail closed，不得默认任一侧。"""


# ---------------------------------------------------------------------------
# LaneSupplyFacts 冻结数据类（四条独立布尔判据）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LaneSupplyFacts:
    """一个 (project, wp, entry) 的 lane 供给事实。

    四个布尔各有独立取数来源（取数逻辑在 ``observe_lane_supply`` 中实现，Task 2.1）。
    """

    entry_id: str
    verdict: LaneVerdict

    #: 判据 A —— 库里有该 entry 的 approved projection bundle
    projection_bundle_provisioned: bool

    #: 判据 B —— 该 (wp, entry) 有 current published representation
    published_representation_current: bool

    #: 判据 C —— current representation 绑定的 bundle 是 projection_contract
    representation_follows_projection_contract: bool

    #: 判据 D —— 磁盘契约 canonical digest 与 bundle slot digest 一致
    representation_contract_digest_matches: bool

    @property
    def supply_satisfied(self) -> bool:
        """供给成立 = A AND B AND C AND D。四条**全部**必需，缺一即不成立。"""
        return (
            self.projection_bundle_provisioned
            and self.published_representation_current
            and self.representation_follows_projection_contract
            and self.representation_contract_digest_matches
        )


# ---------------------------------------------------------------------------
# L1 的 opaque 形态表 —— 与 OPAQUE_AUTHORITY_LANES 双向锁死
# ---------------------------------------------------------------------------
#
# 判据说明：L1 需要判断给定 entry_id 是否「命中 OPAQUE_AUTHORITY_LANES 任一 lane 声明
# 的 entry_id_source 形态」。opaque entry_id 全部以 "opaque-" 前缀开头（唯一构造处
# = writer_migration.opaque_entry_id），因此 L1 的判据是：
#   entry_id.startswith(OPAQUE_ENTRY_PREFIX)
# 这等价于命中**全部五条** opaque lane 的共同特征——它们的 entry_id 都是
# ``opaque_entry_id(...)`` 产出的，而该函数恒加 ``OPAQUE_ENTRY_PREFIX``。
#
# L1 **必须**排第一。反过来排会让 opaque entry_id（永不在 manifest 里）先撞 L2 的
# ``undecided``，于是 L1 变成不可达分支。


def _opaque_entry_prefix() -> str:
    """从真源取 opaque entry_id 前缀 —— 不写第二份。"""
    from app.services.workpaper_sync.writer_migration import OPAQUE_ENTRY_PREFIX
    return OPAQUE_ENTRY_PREFIX


def _is_opaque_entry_id(entry_id: str) -> bool:
    """L1 判据：entry_id 是否命中 opaque 命名空间。"""
    return entry_id.startswith(_opaque_entry_prefix())


def _find_matching_opaque_lane(entry_id: str) -> str | None:
    """若 entry_id 命中 opaque 形态，返回首个匹配的 lane_id；否则 None。"""
    if not _is_opaque_entry_id(entry_id):
        return None
    from app.services.workpaper_sync.opaque_entry_gate import OPAQUE_AUTHORITY_LANES
    # 全部 opaque lane 的 entry_id 都以 opaque- 前缀开头，且由不同的 entry_id_source
    # 形态区分。一旦命中前缀，返回第一条 lane（L1 只需知道「是 opaque」）。
    if OPAQUE_AUTHORITY_LANES:
        return OPAQUE_AUTHORITY_LANES[0].lane_id
    return None  # pragma: no cover — OPAQUE_AUTHORITY_LANES 恒非空


# ---------------------------------------------------------------------------
# 诊断辅助
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _UndecidedDiagnostic:
    """L2~L5 中首个不成立判据的诊断。"""
    criterion_number: int
    criterion_label: str
    source_path: str
    detail: str


# 各判据的真源文件路径
_L2_SOURCE: Final[str] = "backend/data/workpaper_sync_entry_manifest.json"
_L3_SOURCE: Final[str] = "backend/app/services/workpaper_sync/adapters/registry.py"
_L4_SOURCE: Final[str] = _L2_SOURCE  # manifest 里的 independent_entry / capability
_L5_SOURCE: Final[str] = "backend/data/workpaper_sync_contracts/"


# ---------------------------------------------------------------------------
# adjudicate_lane  —  L1 → L2 → L3 → L4 → L5 → projection
# ---------------------------------------------------------------------------


def adjudicate_lane(
    entry_id: str, *, manifest: Mapping[str, Any] | None = None
) -> LaneVerdict:
    """按 L1 → L5 固定顺序裁决。fail closed：判据不足返回 ``undecided``。

    各真源一律现读，本函数不抄第二份：
    - opaque 形态取自 ``opaque_entry_gate.OPAQUE_AUTHORITY_LANES``
    - manifest 取自 ``manifest_entries_by_id(load_entry_manifest())``
    - 契约登记取自 ``adapters.registry.DELIVERED_PER_ENTRY_CONTRACTS``
    - 契约解析走 ``contracts.load_contract``
    """
    # ── L1：opaque entry_id 形态 ──────────────────────────────
    # 必须排第一。opaque entry_id 永不在 manifest 里，后移会让它撞 L2 的 undecided。
    if _is_opaque_entry_id(entry_id):
        return LaneVerdict.opaque

    # ── L2：entry_id 在 source-backed manifest 内 ────────────
    # `manifest_entries_by_id(None)` 自己会 `load_entry_manifest()`，故这里不再导入
    # 后者（导了不用等于给读者一个「本函数直接读盘」的错误印象）。
    from app.services.workpaper_sync.entry_profile import manifest_entries_by_id

    entries = manifest_entries_by_id(manifest)
    if entry_id not in entries:
        return LaneVerdict.undecided

    # ── L3：DELIVERED_PER_ENTRY_CONTRACTS 有登记行 ────────────
    contract_row = _find_delivered_contract(entry_id)
    if contract_row is None:
        return LaneVerdict.undecided

    # ── L4：independent_entry 且 capability != unreachable ────
    from app.services.workpaper_sync.entry_profile import (
        Capability,
        capability_of,
    )
    entry = entries[entry_id]
    if not entry.get("independent_entry"):
        return LaneVerdict.undecided
    cap = capability_of(entry)
    if cap is Capability.unreachable:
        return LaneVerdict.undecided

    # ── L5：磁盘 per-entry contract review_status == reviewed ─
    from app.services.workpaper_sync.contracts import (
        ContractReviewStatus,
        load_contract,
    )
    contract_id = str(contract_row.get("contract_id") or "").strip()
    if not contract_id:
        return LaneVerdict.undecided
    try:
        contract = load_contract(contract_id)
    except Exception:
        return LaneVerdict.undecided
    if contract.review_status is not ContractReviewStatus.reviewed:
        return LaneVerdict.undecided

    # ── 全过 ──────────────────────────────────────────────────
    return LaneVerdict.projection


# ---------------------------------------------------------------------------
# _adjudicate_with_diagnostic —— 带诊断信息的裁决（供 assert 和 describe 使用）
# ---------------------------------------------------------------------------


def _adjudicate_with_diagnostic(
    entry_id: str, *, manifest: Mapping[str, Any] | None = None
) -> tuple[LaneVerdict, _UndecidedDiagnostic | str | None]:
    """裁决并返回诊断。

    Returns:
        (verdict, diagnostic)
        - ``opaque``: diagnostic = lane_id (str)
        - ``undecided``: diagnostic = _UndecidedDiagnostic
        - ``projection``: diagnostic = None
    """
    # ── L1 ──
    if _is_opaque_entry_id(entry_id):
        lane_id = _find_matching_opaque_lane(entry_id)
        return LaneVerdict.opaque, lane_id or "opaque"

    # ── L2 ──
    from app.services.workpaper_sync.entry_profile import manifest_entries_by_id

    entries = manifest_entries_by_id(manifest)
    if entry_id not in entries:
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=2,
            criterion_label="L2: manifest 归属",
            source_path=_L2_SOURCE,
            detail=f"entry_id {entry_id!r} 不在 source-backed manifest 内",
        )

    # ── L3 ──
    contract_row = _find_delivered_contract(entry_id)
    if contract_row is None:
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=3,
            criterion_label="L3: per-entry 契约登记",
            source_path=_L3_SOURCE,
            detail=(
                f"entry_id {entry_id!r} 在 manifest 里但没有"
                " DELIVERED_PER_ENTRY_CONTRACTS 登记行"
            ),
        )

    # ── L4 ──
    from app.services.workpaper_sync.entry_profile import (
        Capability,
        capability_of,
    )
    entry = entries[entry_id]
    if not entry.get("independent_entry"):
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=4,
            criterion_label="L4: independent_entry",
            source_path=_L4_SOURCE,
            detail=f"entry_id {entry_id!r} 不是 independent_entry",
        )
    cap = capability_of(entry)
    if cap is Capability.unreachable:
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=4,
            criterion_label="L4: capability != unreachable",
            source_path=_L4_SOURCE,
            detail=f"entry_id {entry_id!r} 的 capability 为 unreachable",
        )

    # ── L5 ──
    from app.services.workpaper_sync.contracts import (
        ContractReviewStatus,
        load_contract,
    )
    contract_id = str(contract_row.get("contract_id") or "").strip()
    if not contract_id:
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=5,
            criterion_label="L5: 磁盘契约 review_status",
            source_path=_L5_SOURCE,
            detail=(
                f"entry_id {entry_id!r} 的 DELIVERED_PER_ENTRY_CONTRACTS 行"
                " 缺 contract_id"
            ),
        )
    try:
        contract = load_contract(contract_id)
    except Exception as exc:
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=5,
            criterion_label="L5: 磁盘契约加载",
            source_path=os.path.join(_L5_SOURCE, f"{contract_id}.json"),
            detail=f"加载契约 {contract_id!r} 失败: {exc}",
        )
    if contract.review_status is not ContractReviewStatus.reviewed:
        return LaneVerdict.undecided, _UndecidedDiagnostic(
            criterion_number=5,
            criterion_label="L5: 磁盘契约 review_status",
            source_path=os.path.join(_L5_SOURCE, f"{contract_id}.json"),
            detail=(
                f"契约 {contract_id!r} 的 review_status 为"
                f" {contract.review_status.value!r}（需 reviewed）"
            ),
        )

    # ── 全过 ──
    return LaneVerdict.projection, None


# ---------------------------------------------------------------------------
# assert_projection_lane
# ---------------------------------------------------------------------------


def assert_projection_lane(entry_id: str) -> None:
    """非 ``projection`` 即抛，带 ``error_code`` + 首个不符的判据编号 + 真源路径。

    - ``opaque`` → ``LaneIsOpaqueError``（附命中的 ``lane_id``）
    - ``undecided`` → ``LaneUndecidedError``（附首个不成立判据编号 + 真源文件路径）
    """
    verdict, diagnostic = _adjudicate_with_diagnostic(entry_id)
    if verdict is LaneVerdict.projection:
        return

    if verdict is LaneVerdict.opaque:
        lane_id = diagnostic if isinstance(diagnostic, str) else "opaque"
        raise LaneIsOpaqueError(
            f"entry_id {entry_id!r} 属于 opaque lane"
            f"（命中 lane_id={lane_id!r}）—— 不可用于 projection",
            entry_id=entry_id,
            lane_id=lane_id,
        )

    # undecided
    if isinstance(diagnostic, _UndecidedDiagnostic):
        raise LaneUndecidedError(
            f"entry_id {entry_id!r} 的 lane 裁决为 undecided"
            f"（首个不成立判据: L{diagnostic.criterion_number}"
            f" [{diagnostic.criterion_label}]"
            f"，真源: {diagnostic.source_path}）: {diagnostic.detail}",
            entry_id=entry_id,
            criterion_number=diagnostic.criterion_number,
            criterion_label=diagnostic.criterion_label,
            source_path=diagnostic.source_path,
        )
    raise LaneUndecidedError(  # pragma: no cover
        f"entry_id {entry_id!r} 的 lane 裁决为 undecided",
        entry_id=entry_id,
    )


# ---------------------------------------------------------------------------
# describe_supply_gap（供给诊断 —— Task 2.1 会扩充）
# ---------------------------------------------------------------------------


def describe_supply_gap(facts: LaneSupplyFacts) -> str | None:
    """供给不足时给出**指名道姓**的原因。供给成立返回 ``None``。

    文案必须能区分 A/B/C/D 四条中具体哪条不成立。
    当 A 为真 B 为假时，文本**同时**点明「判据 A 已满足」与「判据 B 未满足」。
    """
    if facts.supply_satisfied:
        return None

    # 🔴 规则是**通用**的：按 A→B→C→D 顺序，把首个为假之前**已满足**的逐条点明，
    #    再点明首个为假者。这样「A 真 B 假 ⇒ 同时点明 A 已满足与 B 未满足」是该规则
    #    的一个实例，而不是写死的特例分支。
    #
    #    写死那一对（`if A and not B: parts = [...]`）表面上能过 AC，但 A 真 B 真 C 假
    #    时就只剩一句「C 未满足」，读者无法判断 A/B 是真满足还是没跑到；而任何把
    #    顺序或字段换一下的变异都不会打红 —— 判据形同虚设。
    labels: tuple[tuple[str, str, bool], ...] = (
        ("A", "projection_bundle_provisioned", facts.projection_bundle_provisioned),
        (
            "B",
            "published_representation_current",
            facts.published_representation_current,
        ),
        (
            "C",
            "representation_follows_projection_contract",
            facts.representation_follows_projection_contract,
        ),
        (
            "D",
            "representation_contract_digest_matches",
            facts.representation_contract_digest_matches,
        ),
    )

    parts: list[str] = []
    for letter, name, value in labels:
        if value:
            parts.append(f"判据 {letter}（{name}）已满足")
            continue
        parts.append(f"判据 {letter}（{name}）未满足")
        break  # 只点名**首个**为假者，后续不再展开（fail-closed 的诊断只需第一因）

    return f"供给未成立（entry_id={facts.entry_id!r}）: " + "; ".join(parts)


# ---------------------------------------------------------------------------
# 辅助：在 DELIVERED_PER_ENTRY_CONTRACTS 中查找
# ---------------------------------------------------------------------------


def _find_delivered_contract(entry_id: str) -> Mapping[str, Any] | None:
    """在 ``DELIVERED_PER_ENTRY_CONTRACTS`` 中按 entry_id 查找登记行。"""
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )
    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        if str(row.get("entry_id") or "").strip() == entry_id:
            return row
    return None


# ---------------------------------------------------------------------------
# 占位：Task 1.3 将实现的双向锁与 AST 守卫
# ---------------------------------------------------------------------------


#: L1 的 opaque 形态表 —— 双向锁的**本侧**。
#:
#: 🔴 这张表是「锁的另一半」，不是第二份业务真源：
#:
#: * **业务语义**（哪条 writer 属哪条 lane、它的 entry_id 怎么构造）唯一真源仍是
#:   ``opaque_entry_gate.OPAQUE_AUTHORITY_LANES``；本模块从不据本表做任何裁决 ——
#:   ``adjudicate_lane`` / ``_find_matching_opaque_lane`` 都现读那边。
#: * 本表只承载「L1 **已知**并已核对过的 lane 名册与其 entry_id 形态」。它的唯一消费者
#:   是 :func:`assert_registry_covers_opaque_lanes`。
#:
#: 为什么必须有它（Requirement 1.8 / Property 4）：没有本表时，
#: ``assert_registry_covers_opaque_lanes`` 只能拿 ``OPAQUE_AUTHORITY_LANES`` 跟**它自己**
#: 比（判 lane_id 不重复、entry_id_source 是合法枚举成员），于是「往那边新增一条 lane」
#: 或「把某条 lane 的 entry_id_source 从 wp_code 换成 wp_id」**都不会打红** ——
#: 判据在单侧上恒真。首版实现正是那样：``opaque_sources`` 收集完即弃、从未被读。
#:
#: 新增一条 opaque lane 时的正确动作：先在 ``OPAQUE_AUTHORITY_LANES`` 登记，然后**人工
#: 核对** L1 是否真能识别它的 entry_id 形态，再把它加进本表。本表被改动即意味着
#: 「L1 的识别范围变了」，那是需要有人看一眼的事，不该静默跟随。
_L1_OPAQUE_LANE_SHAPES: Final[Mapping[str, str]] = {
    "custom_cells": "wp_code",
    "offline_upload": "wp_id",
    "wopi_put_file": "wp_id",
    "f2_stocktake_plan": "wp_code_with_sheet",
    "f2_stocktake_summary": "wp_code_with_sheet",
}


def assert_registry_covers_opaque_lanes() -> None:
    """L1 形态表与 ``OPAQUE_AUTHORITY_LANES`` 逐项交叉锁死。

    两侧任一新增、删除或修改一条 lane 时失败并指出具体 ``lane_id``。
    本函数在 **import 时**即跑（坏表不许被加载）。

    交叉判据（**三个方向一起算完再报告**，与
    ``opaque_entry_gate.assert_lane_registry_covers_source`` 同款）：

    1. **未被 L1 认领的 lane** —— ``OPAQUE_AUTHORITY_LANES`` 有而本模块形态表没有：
       新加了一条 opaque writer 而 L1 不知道它，那条 lane 的 entry_id 会落进
       ``undecided`` 并被首版入口当成「可发 projection 首版」。
    2. **无对应 lane 的 L1 登记** —— 本模块形态表有而那边没有：lane 被删或改名，
       L1 的识别范围成了空指望（与 manifest 生成器的 stale overlay 判据同款）。
    3. **entry_id 形态漂移** —— 两侧 ``entry_id_source`` 对同一 ``lane_id`` 不一致：
       entry_id 命名空间被悄悄换掉（``opaque-{wp_code}`` ↔ ``opaque-{wp_id}``）。

    🔴 三个方向必须一起算完：只报第一个时，守卫为了独立 falsify 第三条判据必须先把前两
    条构造成通过，而那需要改生产源码 —— 判据于是无法被独立打红。

    Requirements: 1.8
    """
    from app.services.workpaper_sync.opaque_entry_gate import (
        OPAQUE_AUTHORITY_LANES,
        EntryIdSource,
    )

    if not OPAQUE_AUTHORITY_LANES:
        raise OpaqueLaneCoverageDriftError(
            "OPAQUE_AUTHORITY_LANES 为空 —— L1 形态表失去分母，"
            "opaque 命名空间将无法被识别"
        )
    if not _L1_OPAQUE_LANE_SHAPES:
        raise OpaqueLaneCoverageDriftError(
            "_L1_OPAQUE_LANE_SHAPES 为空 —— 双向锁只剩一侧，"
            "那边任意增删改都不会打红"
        )

    # L1 的前缀判据：整个命名空间识别依赖它非空。
    prefix = _opaque_entry_prefix()
    if not prefix:
        raise OpaqueLaneCoverageDriftError(
            "OPAQUE_ENTRY_PREFIX 为空 —— L1 的 startswith 判据会命中所有 entry_id，"
            "opaque 与 projection 的命名空间无法区分"
        )

    # ── 收集那一侧 ────────────────────────────────────────────────────
    source_shapes: dict[str, str] = {}
    for lane in OPAQUE_AUTHORITY_LANES:
        if lane.lane_id in source_shapes:
            raise OpaqueLaneCoverageDriftError(
                f"OPAQUE_AUTHORITY_LANES 里 lane_id {lane.lane_id!r} 重复 "
                "—— 与 assert_lane_self_consistent 的 lane_id 唯一判据冲突"
            )
        if not isinstance(lane.entry_id_source, EntryIdSource):
            raise OpaqueLaneCoverageDriftError(
                f"lane {lane.lane_id!r}: entry_id_source "
                f"{lane.entry_id_source!r} 不是 EntryIdSource 枚举成员"
            )
        source_shapes[lane.lane_id] = lane.entry_id_source.value

    # ── 三方向差集 ────────────────────────────────────────────────────
    unclaimed = sorted(set(source_shapes) - set(_L1_OPAQUE_LANE_SHAPES))
    stale = sorted(set(_L1_OPAQUE_LANE_SHAPES) - set(source_shapes))
    drifted = sorted(
        f"{lane_id}: L1 登记 {_L1_OPAQUE_LANE_SHAPES[lane_id]!r}、"
        f"OPAQUE_AUTHORITY_LANES 实测 {source_shapes[lane_id]!r}"
        for lane_id in set(source_shapes) & set(_L1_OPAQUE_LANE_SHAPES)
        if source_shapes[lane_id] != _L1_OPAQUE_LANE_SHAPES[lane_id]
    )

    if unclaimed or stale or drifted:
        raise OpaqueLaneCoverageDriftError(
            "L1 形态表与 OPAQUE_AUTHORITY_LANES 不一致：\n"
            f"  未被 L1 认领的 lane ({len(unclaimed)}): {unclaimed}\n"
            f"  无对应 lane 的 L1 登记 ({len(stale)}): {stale}\n"
            f"  entry_id 形态漂移 ({len(drifted)}): {drifted}\n"
            "L1 是 projection / opaque 选路的第一道门：漏认领会让那条 lane 的 entry_id "
            "落进 undecided 并被首版入口当成可发 projection 首版（覆盖用户的权威 OOXML）；"
            "形态漂移等于 entry_id 命名空间被悄悄换掉"
        )


# ---------------------------------------------------------------------------
# AST 扫描辅助 —— 三个判据 helper
# ---------------------------------------------------------------------------
#
# 🔴 这三个函数被 `assert_no_second_lane_decision_site` 调用。Task 1.1 交付时它们
#    只有调用点没有定义，而模块当时还带一处 SyntaxError（docstring 里嵌了三引号），
#    于是「从未被 import 过」把 NameError 一起遮住了 —— 这正是「守卫只查字符存在、
#    没人真跑一次」的形态。故本节的判据全部落在**真实执行**上。

#: 构成「lane 判定」的比较运算符。字符串的 ``<`` / ``>`` 排序不是判定，把它算进
#: 违规会把无关的排序代码误报成第二真源。
_LANE_DECISION_OPS: Final[tuple[type[ast.cmpop], ...]] = (
    ast.Eq,
    ast.NotEq,
    ast.In,
    ast.NotIn,
    ast.Is,
    ast.IsNot,
)


def _is_string_constant(node: ast.AST, expected: str) -> bool:
    """``node`` 是否为值恰等于 ``expected`` 的字符串字面量。

    只认 :class:`ast.Constant` 且 ``isinstance(value, str)``：``ast.Constant`` 也
    承载 ``True`` / ``1`` / ``None``，而 ``True == 1`` 在 Python 里为真，漏掉类型
    判据会让 ``x == True`` 命中 ``expected="1"`` 这类误报。
    """
    return (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value == expected
    )


def _is_in_comparison_context(node: ast.Compare) -> bool:
    """``node`` 是否构成一次 lane **判定**（而非排序）。

    判据 = 运算符里至少有一个属于 :data:`_LANE_DECISION_OPS`。链式比较
    ``a == b < c`` 中 ``==`` 已足以构成判定，故用 ``any`` 而非 ``all``。
    """
    return any(isinstance(op, _LANE_DECISION_OPS) for op in node.ops)


def _build_scope_index(tree: ast.Module) -> list[tuple[int, int, str]]:
    """收集 ``tree`` 内全部函数/类的 ``(起始行, 结束行, qualname)``。

    🔴 用 ``ast`` 的 ``lineno`` / ``end_lineno`` 定位，**不**用固定字符窗口截函数体：
    多行签名与 ``-> Mapping[str, Any]`` 返回注解都会骗到「第一个冒号/括号」。
    """
    spans: list[tuple[int, int, str]] = []

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                end = getattr(child, "end_lineno", None) or child.lineno
                spans.append((child.lineno, end, qualname))
                walk(child, qualname)
            else:
                walk(child, prefix)

    walk(tree, "")
    return spans


def _scope_index_for(tree: ast.Module) -> list[tuple[int, int, str]]:
    """:func:`_build_scope_index` 的 per-tree 缓存。

    扫描器对每个命中节点都要问一次 enclosing scope；不缓存就是 O(节点数 × 作用域数)，
    在 ``backend/app/**`` 这个量级上会把只读扫描拖到分钟级。缓存挂在 tree 对象上，
    生命周期与 tree 一致，不会跨文件串味（``id()`` 做 key 会因 gc 复用而串）。
    """
    cached = getattr(tree, "_gt_lane_scope_index", None)
    if cached is None:
        cached = _build_scope_index(tree)
        try:
            tree._gt_lane_scope_index = cached  # type: ignore[attr-defined]
        except AttributeError:  # pragma: no cover — ast 节点允许任意属性
            pass
    return cached


def _enclosing_qualname_for_scanner(tree: ast.Module, node: ast.AST) -> str:
    """``node`` 所在**最内层**函数/类的 qualname；不在任何作用域内返回 ``"<module>"``。

    取最内层的判据 = 命中区间里跨度最小的那个（嵌套函数的区间必然被外层包含）。
    """
    lineno = getattr(node, "lineno", None)
    if lineno is None:  # pragma: no cover — 表达式节点恒有 lineno
        return "<module>"
    best: tuple[int, str] | None = None
    for start, end, qualname in _scope_index_for(tree):
        if start <= lineno <= end:
            span = end - start
            if best is None or span < best[0]:
                best = (span, qualname)
    return best[1] if best else "<module>"


#: 表达式里出现这些标识片段 ⇒ 被比较的操作数来自 **entry**，因此该比较是一次
#: 「这个 entry 属于哪条 lane」的判定。lane 是 entry 的属性，这是本判据的语义根。
_ENTRY_DERIVED_HINTS: Final[tuple[str, ...]] = ("entry", "manifest")

#: 表达式里出现这些标识片段 ⇒ 操作数来自 **bundle / definition artifact**，该比较
#: 是在校验那个对象自身的形状（例如「声明 projection_contract 的 bundle，其 contract
#: slot 必须是 approved definition child」），不是在给某个 entry 选路。
_SHAPE_DERIVED_HINTS: Final[tuple[str, ...]] = (
    "bundle",
    "authority",
    "definition",
    "snapshot",
    "artifact",
    "slot",
)


def _classify_authority_comparison(operand: ast.AST) -> str:
    """把一次 ``== "projection_contract"`` 比较分成 ``"lane"`` 或 ``"shape"``。

    判据不是文件豁免名单，而是**被比较的那个操作数从哪来**：

    * 来自 entry（``entry["authority_model"]`` / ``manifest_row[...]``）⇒ ``"lane"``
      —— 这是在替 entry 选路，必须经本模块裁决；
    * 来自 bundle / definition artifact（``bundle.authority_model.value`` /
      ``authority.get("authority_model_type")``）⇒ ``"shape"`` —— 这是在校验那个
      对象自身的不变量，与 entry 选路无关。

    🔴 为什么不用「按文件豁免」：豁免列会随时间只增不减，而且一旦某个被豁免的文件真的
    加了一处 entry 选路，判据就再也拦不住它。按操作数来源分类则对新增代码同样生效。

    两类提示词同时命中时判 ``"lane"``（从严）：``entry_bundle.authority_model`` 这种
    表达式既碰 entry 又碰 bundle，宁可要求它走裁决。
    """
    expr = ast.unparse(operand).lower()
    if any(hint in expr for hint in _ENTRY_DERIVED_HINTS):
        return "lane"
    if any(hint in expr for hint in _SHAPE_DERIVED_HINTS):
        return "shape"
    # 两类都不命中：无法判定来源 ⇒ fail closed 判 lane，要求它显式走裁决。
    return "lane"


def _scope_calls_lane_registry(
    tree: ast.Module, node: ast.AST, registry_names: frozenset[str]
) -> bool:
    """``node`` 所在最内层作用域内是否**真的调用**了本模块的裁决函数。

    比「文件级 import 了就算合规」精确一档：一个文件可以既 import 裁决函数、又在
    另一个函数里私自判 lane，文件级判据会把后者一起放过。
    """
    target_scope = _enclosing_qualname_for_scanner(tree, node)
    for scope_node in ast.walk(tree):
        if not isinstance(
            scope_node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        if _enclosing_qualname_for_scanner(tree, scope_node) != target_scope:
            # 只看恰好等于目标作用域的那个定义节点（它的 enclosing 就是自己）
            continue
        for inner in ast.walk(scope_node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name in registry_names:
                return True
    return False


def assert_no_second_lane_decision_site() -> Mapping[str, tuple[str, ...]]:
    """AST 扫描 ``backend/app/**`` 与 ``backend/scripts/**``，报告违规位置。

    违规 = 在本模块之外**替某个 entry 判定 lane**：比较 authority model 取值
    （``== "projection_contract"``）或判 ``opaque-`` 前缀
    （``startswith("opaque-")``），且该比较的操作数来自 entry。

    **不**违规的两类，各有结构判据而非文件豁免：

    1. 操作数来自 bundle / definition artifact ⇒ 那是对象自身的形状校验
       （见 :func:`_classify_authority_comparison`）；
    2. 该位置所在作用域真的调用了本模块的裁决函数
       （见 :func:`_scope_calls_lane_registry`）。

    返回 ``{module_path: (site_description, ...)}`` —— 合规调用点与形状校验点的清册，
    供 evidence 现读。违规时抛 :class:`LaneRegistryError` 并逐条点名。

    🔴 AST 扫描不得用 ``strip_comments``：那会连带剥掉以三引号包裹的内嵌 SQL
    文本块（``sa.text(...)`` 的实参）。节点定位一律走语法树。

    Requirements: 1.9
    """
    backend_root = Path(__file__).resolve().parents[3]  # …/backend

    scan_roots: list[Path] = []
    for subdir in ("app", "scripts"):
        root = backend_root / subdir
        if root.is_dir():
            scan_roots.append(root)

    # 本模块自身的 module path（豁免）
    self_module_path = Path(__file__).resolve()

    # 收集两类已知的合规导入——如果文件 import 了本模块的函数，其调用不算违规
    _LANE_REGISTRY_MODULE = "app.services.workpaper_sync.projection_lane_registry"
    _LANE_REGISTRY_FUNCTIONS = frozenset({
        "adjudicate_lane",
        "assert_projection_lane",
        "_is_opaque_entry_id",
        "_opaque_entry_prefix",
        "_find_matching_opaque_lane",
        "observe_lane_supply",
        "assert_registry_covers_opaque_lanes",
        "assert_no_second_lane_decision_site",
    })

    # opaque_entry_gate 里的 OPAQUE_ENTRY_PREFIX 和 opaque_entry_id 也是合规的
    # （它是真源，不是第二真源）
    _OPAQUE_GATE_NAMES = frozenset({
        "OPAQUE_ENTRY_PREFIX",
        "opaque_entry_id",
        "OPAQUE_AUTHORITY_LANES",
        "assert_lane_self_consistent",
        "assert_lane_registry_covers_source",
    })

    violations: dict[str, list[str]] = {}
    compliant_sites: dict[str, list[str]] = {}

    for scan_root in scan_roots:
        for py_path in sorted(scan_root.rglob("*.py")):
            # 跳过本模块
            if py_path.resolve() == self_module_path:
                continue

            try:
                source = py_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            # 快速跳过：文件里连目标字符串都没有
            has_projection_contract = '"projection_contract"' in source or "'projection_contract'" in source
            has_opaque_prefix = '"opaque-"' in source or "'opaque-'" in source
            if not has_projection_contract and not has_opaque_prefix:
                continue

            try:
                tree = ast.parse(source, filename=str(py_path))
            except SyntaxError:
                continue

            rel_path = py_path.relative_to(backend_root.parent).as_posix()

            # 收集文件级 import：哪些名字从 lane registry 或 opaque gate 导入
            imported_from_lane_registry: set[str] = set()
            imported_from_opaque_gate: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if _LANE_REGISTRY_MODULE in node.module:
                        for alias in (node.names or []):
                            imported_from_lane_registry.add(alias.asname or alias.name)
                    if "opaque_entry_gate" in node.module or "writer_migration" in node.module:
                        for alias in (node.names or []):
                            imported_from_opaque_gate.add(alias.asname or alias.name)

            file_violations: list[str] = []
            file_compliant: list[str] = []

            for node in ast.walk(tree):
                # ── pattern 1: 比较 "projection_contract" ──────────────
                if isinstance(node, ast.Compare) and _is_in_comparison_context(node):
                    literal_side: ast.AST | None = None
                    other_side: ast.AST | None = None
                    if _is_string_constant(node.left, "projection_contract"):
                        literal_side = node.left
                        other_side = node.comparators[0] if node.comparators else None
                    else:
                        for cmp_node in node.comparators:
                            if _is_string_constant(cmp_node, "projection_contract"):
                                literal_side = cmp_node
                                other_side = node.left
                                break

                    if literal_side is not None and other_side is not None:
                        ctx = _enclosing_qualname_for_scanner(tree, node)
                        expr = ast.unparse(other_side)
                        kind = _classify_authority_comparison(other_side)
                        if kind == "shape":
                            # bundle / definition artifact 自身的形状校验 —— 不是选路
                            file_compliant.append(
                                f"L{node.lineno}: {ctx} 校验 {expr} 的 authority model "
                                f"形状（非 entry 选路，无需裁决）"
                            )
                        elif _scope_calls_lane_registry(
                            tree, node, _LANE_REGISTRY_FUNCTIONS
                        ) or (imported_from_lane_registry & _LANE_REGISTRY_FUNCTIONS):
                            file_compliant.append(
                                f"L{node.lineno}: {ctx} 以 {expr} 判 lane"
                                f"（已经 projection_lane_registry 裁决）"
                            )
                        else:
                            file_violations.append(
                                f"L{node.lineno}: {ctx} 以 {expr} 比较 "
                                f"'projection_contract' 判定 entry 的 lane，"
                                f"但未经 projection_lane_registry 裁决"
                            )

                # ── pattern 2: startswith("opaque-") ──────────────────
                # 这一类**恒为** lane 判定：`opaque-` 前缀只出现在 entry_id 命名空间里，
                # 没有「校验某个 bundle 形状」的解释空间，故不走 shape 分类。
                if isinstance(node, ast.Call):
                    if (
                        isinstance(node.func, ast.Attribute)
                        and node.func.attr == "startswith"
                        and node.args
                        and _is_string_constant(node.args[0], "opaque-")
                    ):
                        ctx = _enclosing_qualname_for_scanner(tree, node)
                        # 🔴 2026-09-04 修：删掉两条**文件级** import 豁免。
                        #
                        # 原判据是
                        #     scope_calls_registry
                        #     or (imported_from_lane_registry & ...)
                        #     or (imported_from_opaque_gate & ...)
                        # 后两项让「这个文件 import 过裁决函数」就豁免**整个文件**里的
                        # 任意 `startswith("opaque-")`。变异检验 M7 实测判 GREEN：在
                        # `projection_first_publication.py`（它正当地 import 了
                        # `assert_projection_lane` / `observe_lane_supply`）里新增一个
                        # 私自判定的 `_is_opaque_second_source`，扫描器**放过**了它。
                        #
                        # 这正是本函数 docstring 与 `_scope_calls_lane_registry` 自己写明
                        # 要避免的形态：「一个文件可以既 import 裁决函数、又在另一个函数里
                        # 私自判 lane，文件级判据会把后者一起放过」。作用域级判据已经实现
                        # 了正确语义，却被这两条 `or` 短路成了文件级。
                        #
                        # 真源自身（`writer_migration.opaque_entry_id` 构造前缀、
                        # `opaque_entry_gate` 的 lane 表）不受影响：它们**不**用
                        # `startswith("opaque-")` 判定 entry，因此本 pattern 根本不命中。
                        if _scope_calls_lane_registry(
                            tree, node, _LANE_REGISTRY_FUNCTIONS
                        ):
                            file_compliant.append(
                                f"L{node.lineno}: {ctx} startswith('opaque-')"
                                f"（已经 lane registry / opaque gate 真源裁决）"
                            )
                        else:
                            file_violations.append(
                                f"L{node.lineno}: {ctx} 自行 startswith('opaque-') "
                                f"判定 entry 的 lane，但未经 projection_lane_registry 裁决"
                            )

            if file_violations:
                violations[rel_path] = file_violations
            if file_compliant:
                compliant_sites[rel_path] = file_compliant

    if violations:
        details = []
        for mod, items in sorted(violations.items()):
            details.append(f"  {mod}:")
            for item in items:
                details.append(f"    - {item}")
        raise LaneRegistryError(
            f"发现 {sum(len(v) for v in violations.values())} 处第二 lane 判定位置"
            f"（{len(violations)} 个模块）：\n" + "\n".join(details) + "\n"
            "所有 lane 判定必须经 projection_lane_registry 的 adjudicate_lane / "
            "assert_projection_lane 裁决，不得自行比较 authority model 取值或"
            "检查 opaque- 前缀"
        )

    # 返回合规调用点清册（按模块归组）
    return {mod: tuple(items) for mod, items in sorted(compliant_sites.items())}


# ---------------------------------------------------------------------------
# 供给观测 —— 四条独立判据（Task 2.1 / Requirements 2.1~2.8）
# ---------------------------------------------------------------------------
#
# 四条判据的取数来源**两两不同**，这是 Property 8 的落点：
#
#   A  approved projection bundle 存在吗          bundle ⋈ authority artifact（按 entry）
#   B  该 (wp, entry) 有 current representation 吗  sync_entry_state（带 wp scope）
#   C  已发布的那个 representation 在 projection lane 吗  representation → bundle → authority
#   D  已发布的 bundle 绑的还是今天的磁盘契约吗      磁盘 contract digest ↔ bundle slot digest
#
# A 与 C 的区别常被读成重复，其实不是：A 问「这个 entry 有没有供给」，C 问「已经发布
# 出去的那一份属于哪条 lane」。D2 就是活证人 —— 它 A 为真（bundle 已 provision）而 C
# 为假（库里那条 current representation 绑的是 opaque bundle）。

#: authority model definition 的 logical_id 后缀。
#:
#: 真源 = 各 provider 模块 `publish_pilot_definitions()` 里的
#: ``logical_id=f"{PILOT_ADAPTER_ID}.authority-model"``。这里写一份是因为反向查询
#: （给 entry 找它的 authority artifact）必须能构造出这个 key，而 provider 侧只有正向
#: 构造。两侧由 :func:`assert_authority_logical_suffix_matches_providers` 双向锁死：
#: 任一 provider 改了后缀而这里没跟，守卫打红 —— 而不是让判据 A 静默恒假。
_AUTHORITY_MODEL_LOGICAL_SUFFIX: Final[str] = ".authority-model"


def authority_model_logical_id(contract_id: str) -> str:
    """该 contract 对应的 authority model definition 的 ``logical_id``。"""
    return f"{contract_id}{_AUTHORITY_MODEL_LOGICAL_SUFFIX}"


def assert_authority_logical_suffix_matches_providers() -> tuple[str, ...]:
    """与各 provider 模块的正向构造双向锁死；返回已核对的模块清册。

    结构判据（不是 grep 字符串）：在每个白名单 provider 模块里定位
    ``publish_definition(kind=DefinitionKind.authority_model, ..., logical_id=<f-string>)``
    这个调用，取出 ``logical_id`` 的 f-string 常量部分，要求它恰等于
    :data:`_AUTHORITY_MODEL_LOGICAL_SUFFIX`。

    Raises:
        OpaqueLaneCoverageDriftError: 某 provider 的后缀与本模块不一致，或找不到该调用。
    """
    from app.services.workpaper_sync.adapters import registry as registry_module

    backend_root = Path(__file__).resolve().parents[3]
    checked: list[str] = []

    for module_path in sorted(registry_module._ALLOWED_PROVIDER_MODULES):
        rel = module_path.replace("app.", "app/", 1).replace(".", "/") + ".py"
        py_path = backend_root / rel
        if not py_path.is_file():  # pragma: no cover — 白名单指向真实模块
            raise OpaqueLaneCoverageDriftError(
                f"provider 模块 {module_path!r} 的源文件不存在: {py_path}"
            )
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))

        found_suffix: str | None = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            kind_node = kwargs.get("kind")
            logical_node = kwargs.get("logical_id")
            if kind_node is None or logical_node is None:
                continue
            if "authority_model" not in ast.unparse(kind_node):
                continue
            # logical_id 必须是 f-string，且其字面部分就是后缀
            if not isinstance(logical_node, ast.JoinedStr):
                raise OpaqueLaneCoverageDriftError(
                    f"{module_path}: authority model 的 logical_id 不是 f-string"
                    f"（实得 {ast.unparse(logical_node)}）—— 无法与本模块的反向构造锁死"
                )
            literals = [
                part.value
                for part in logical_node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            ]
            found_suffix = "".join(literals)
            break

        if found_suffix is None:
            raise OpaqueLaneCoverageDriftError(
                f"{module_path}: 找不到 authority model 的 publish_definition 调用 —— "
                "判据 A 的反向查询 key 无从核对"
            )
        if found_suffix != _AUTHORITY_MODEL_LOGICAL_SUFFIX:
            raise OpaqueLaneCoverageDriftError(
                f"{module_path}: authority model logical_id 后缀为 {found_suffix!r}，"
                f"本模块的反向构造用 {_AUTHORITY_MODEL_LOGICAL_SUFFIX!r} —— 两侧不一致会让"
                "判据 A 静默恒假（供给明明已 provision 却报未 provision）"
            )
        checked.append(module_path)

    return tuple(checked)


def _slot_specs_from_bundle_row(row: Any) -> dict[str, Any]:
    """把 bundle DB 行的三组 slot 列还原成 :class:`BundleSlotSpec`。

    🔴 刻意**不**在 SQL 里写 ``contract_slot_type = 'definition'``：``"definition"``
    这个字面量的真源是 ``models.BundleSlotSpec.is_definition``。在 SQL 里再写一遍就是
    第二真源 —— 那边改了判据这边不会红，只会静默放行。
    """
    from app.services.workpaper_sync.models import BundleSlot, BundleSlotSpec

    specs: dict[str, Any] = {}
    for slot in BundleSlot:
        specs[slot.value] = BundleSlotSpec(
            slot=slot,
            slot_type=str(getattr(row, f"{slot.value}_slot_type") or ""),
            slot_ref=str(getattr(row, f"{slot.value}_slot_ref") or ""),
            slot_digest=str(getattr(row, f"{slot.value}_slot_digest") or ""),
        )
    return specs


#: 判据 A —— 该 entry 是否有 approved projection bundle。
#:
#: 三 slot 的 ``is_definition`` **不**在 SQL 里判（见 :func:`_slot_specs_from_bundle_row`），
#: 故这里把三组 slot 列一并取回，由 Python 侧用真源属性判。
_SQL_CRITERION_A: Final[str] = """
SELECT b.id                          AS bundle_id,
       b.canonical_payload_sha256    AS bundle_sha256,
       b.template_slot_type, b.template_slot_ref, b.template_slot_digest,
       b.instrumentation_slot_type, b.instrumentation_slot_ref,
       b.instrumentation_slot_digest,
       b.contract_slot_type, b.contract_slot_ref, b.contract_slot_digest
FROM working_paper_sync_definition_bundle b
JOIN working_paper_sync_definition_artifact a
  ON a.id = b.authority_model_definition_id
WHERE a.logical_id = :authority_logical_id
  AND a.authority_model_type = :projection_authority_type
  AND a.state = :approved
  AND b.state = :approved
ORDER BY b.approved_at DESC NULLS LAST, b.created_at DESC
LIMIT 1
"""

#: 判据 B —— 该 **(wp, entry)** 是否有 current published representation。
#:
#: 🔴 带 ``wp_id`` + ``entry_id`` 双条件。供给门里那条全局 ``.first()`` 会让「库里任何
#: 一条 representation」都算作「本 entry 有 representation」—— 本模块不复制它。
_SQL_CRITERION_B: Final[str] = """
SELECT s.current_representation_id AS representation_id,
       s.representation_generation AS generation
FROM working_paper_sync_entry_state s
WHERE s.wp_id = :wp_id AND s.entry_id = :entry_id
LIMIT 1
"""

#: 判据 C/D —— 已发布 representation 绑定的 bundle 与其 authority model 类型。
#: 取数路径与判据 A 完全不同：从 representation 反查，而不是按 entry 正查。
_SQL_CRITERION_CD: Final[str] = """
SELECT r.id                        AS representation_id,
       r.definition_bundle_id      AS bundle_id,
       a.authority_model_type      AS authority_model_type,
       b.contract_slot_digest      AS contract_slot_digest,
       b.contract_slot_type        AS contract_slot_type
FROM working_paper_content_representation r
JOIN working_paper_sync_definition_bundle b   ON b.id = r.definition_bundle_id
JOIN working_paper_sync_definition_artifact a ON a.id = b.authority_model_definition_id
WHERE r.id = :representation_id
LIMIT 1
"""


async def observe_lane_supply(
    *, session: Any, project_id: Any, wp_id: Any, entry_id: str
) -> LaneSupplyFacts:
    """观测一个 ``(project, wp, entry)`` 的四条供给判据。

    四条判据**各自独立取数**，来源两两不同（见本节顶部注释）。

    Raises:
        LaneSupplyObservationError: 任一取数失败。**不**降级为「四条皆假」——
            fail-open 掩盖接线错误（函数名/列名拼错、传错 session 形态）是本仓库
            最贵的一类缺陷：它把「代码没接通」伪装成「本项目无此数据」。

    Note:
        ``project_id`` 参与错误诊断与调用方 scope 校验，不参与判据 B 的 SQL ——
        ``working_paper_sync_entry_state`` 的主键是 ``(wp_id, entry_id)``，多加一个
        表上没有的列只会让 SQL 报错。
    """
    import logging

    from app.services.workpaper_sync.models import AuthorityModel

    logger = logging.getLogger(__name__)

    verdict = adjudicate_lane(entry_id)
    contract_id = _contract_id_for_entry(entry_id)

    try:
        import sqlalchemy as sa

        approved = "approved"
        projection_type = AuthorityModel.projection_contract.value

        # ── 判据 A ────────────────────────────────────────────
        criterion_a = False
        if contract_id:
            row_a = (
                await session.execute(
                    sa.text(_SQL_CRITERION_A),
                    {
                        "authority_logical_id": authority_model_logical_id(contract_id),
                        "projection_authority_type": projection_type,
                        "approved": approved,
                    },
                )
            ).first()
            if row_a is not None:
                specs = _slot_specs_from_bundle_row(row_a)
                criterion_a = all(spec.is_definition for spec in specs.values())

        # ── 判据 B ────────────────────────────────────────────
        row_b = (
            await session.execute(
                sa.text(_SQL_CRITERION_B),
                {"wp_id": str(wp_id), "entry_id": entry_id},
            )
        ).first()
        representation_id = row_b.representation_id if row_b is not None else None
        criterion_b = representation_id is not None

        # ── 判据 C / D ────────────────────────────────────────
        criterion_c = False
        criterion_d = False
        if criterion_b:
            row_cd = (
                await session.execute(
                    sa.text(_SQL_CRITERION_CD),
                    {"representation_id": str(representation_id)},
                )
            ).first()
            if row_cd is not None:
                criterion_c = row_cd.authority_model_type == projection_type
                # D 跨来源比对：磁盘契约的 canonical digest ↔ 已发布 bundle 的 slot digest。
                # 只有 C 成立才谈得上 D —— opaque bundle 的 contract slot 是 typed null
                # marker，拿它跟磁盘契约比恒假，那属于 C 的结论而不是 D 的结论。
                if criterion_c and contract_id:
                    criterion_d = (
                        str(row_cd.contract_slot_digest or "").strip()
                        == _disk_contract_canonical_digest(contract_id)
                    )

    except LaneSupplyObservationError:
        raise
    except Exception as exc:
        logger.error(
            "lane 供给观测失败 entry_id=%s project_id=%s wp_id=%s contract_id=%s: %s",
            entry_id,
            project_id,
            wp_id,
            contract_id,
            exc,
            exc_info=True,
        )
        raise LaneSupplyObservationError(
            f"供给观测失败（entry_id={entry_id!r} wp_id={wp_id} "
            f"project_id={project_id}）: {type(exc).__name__}: {exc}"
        ) from exc

    return LaneSupplyFacts(
        entry_id=entry_id,
        verdict=verdict,
        projection_bundle_provisioned=criterion_a,
        published_representation_current=criterion_b,
        representation_follows_projection_contract=criterion_c,
        representation_contract_digest_matches=criterion_d,
    )


def _contract_id_for_entry(entry_id: str) -> str:
    """该 entry 的 ``contract_id``；未登记返回空串（判据 A 随之为假）。"""
    row = _find_delivered_contract(entry_id)
    if row is None:
        return ""
    return str(row.get("contract_id") or "").strip()


def _disk_contract_canonical_digest(contract_id: str) -> str:
    """磁盘契约的 canonical SHA-256 —— 判据 D 的**跨来源**一侧。

    走 ``contracts.load_contract`` 的强校验路径（它是 ``review_status != reviewed``
    的单点拒绝处），不自己读 JSON：自己读会绕过 CS-1~CS-3 全部反例判据。
    """
    from app.services.workpaper_sync.contracts import load_contract

    return load_contract(contract_id).canonical_sha256


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------


__all__ = [
    "LaneVerdict",
    "LaneSupplyFacts",
    "adjudicate_lane",
    "assert_projection_lane",
    "describe_supply_gap",
    "observe_lane_supply",
    "authority_model_logical_id",
    "assert_authority_logical_suffix_matches_providers",
    "assert_registry_covers_opaque_lanes",
    "assert_no_second_lane_decision_site",
    # 异常
    "LaneRegistryError",
    "LaneIsOpaqueError",
    "LaneUndecidedError",
    "LaneSupplyObservationError",
    "OpaqueLaneCoverageDriftError",
]


# ---------------------------------------------------------------------------
# import 期即跑双向锁 —— 坏表不许被加载
# ---------------------------------------------------------------------------
#
# 与 `opaque_entry_gate.assert_lane_self_consistent()` 同款约定：登记表与源码不一致时
# 让 **import 失败**，而不是等某个调用方碰巧调了守卫才发现。放在 `__all__` 之后是为了
# 让 `from ... import *` 的名字表在断言前就已成形（断言失败时 traceback 更好读）。
#
# 🔴 只跑 `assert_registry_covers_opaque_lanes()`（纯内存、微秒级）。
#    `assert_no_second_lane_decision_site()` 要遍历 `backend/app/**` 与
#    `backend/scripts/**` 的全部 .py，秒级 —— 挂在 import 期会拖慢每一次进程启动，
#    它的归属是 CI 回归门（Task 9.1）与守卫测试，不是 import 副作用。
assert_registry_covers_opaque_lanes()
