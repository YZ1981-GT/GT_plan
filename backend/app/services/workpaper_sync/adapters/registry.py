"""fail-closed adapter registry（Task 13）。

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` Task 13
Requirements 1.4 / 6.1 / 6.2 / 6.3 / 6.10 / 6.14 / 6.20 / 9.8 / 12.1
Property 3（未注册 adapter 不得宣称双向）/ 20 / 21 / 28

## 启动期拒绝清册（每条独立判据，逐条可变异）

======  =========================================  ===============================
编号    反例                                        异常
======  =========================================  ===============================
RG-1    adapter 缺 protocol 成员/方法不可调用        `AdapterShapeError`
RG-2    matcher 空匹配（wp_codes 为空）              `MatcherError`
RG-3    matcher 与既有注册重叠                       `MatcherOverlapError`
RG-4    adapter_id 与 contract_id 不符                `RegistrationError`
RG-5    同一 adapter_id 重复注册                     `RegistrationError`
RG-6    document_type 在 adapter/contract/manifest    `DocumentTypeMismatchError`
        /bundle 之间不一致
RG-7    bundle 非 approved / slot 不全 / child 不符    `BundleIntegrityError`
RG-8    `projection_contract` 缺 contract 或用 marker  `AuthorityModelMismatchError`
RG-9    custom/opaque 却带 contract                   `AuthorityModelMismatchError`
RG-10   contract digest ≠ bundle contract slot digest  `StaleAdapterError`
RG-11   contract digest ≠ 磁盘契约文件当前 digest      `StaleAdapterError`
RG-12   entry 不在 source-backed manifest              `StaleAdapterError`
RG-13   entry 是 parent_duplicate / unreachable        `RegistrationError`
RG-14   manifest 缺 profile 三字段                     `EntryProfileMissingError`
RG-15   profile 与 capability 矛盾                     `EntryProfileDriftError`
RG-16   descriptor mode 与 capability 矛盾             `EntryProfileDriftError`
RG-17   room 事实与 room_model 矛盾 / doc_key 含 mtime  `EntryProfileDriftError`
RG-18   capability≠bidirectional 却注册双向 adapter     `FakeBidirectionalError`
RG-19   identity carrier 未过 probe gate                `ContractCarrierGateError`
======  =========================================  ===============================

RG-10 与 RG-11 必须分开：前者是「注册时 bundle 与 contract 对不上」（identity 漂移），
后者是「磁盘契约已被改过但 adapter 还挂着旧 digest」（stale）。合成一条之后，把
其中任一分支删掉都会被另一条遮蔽 ⇒ 变异检验判 GREEN。

## 不做的事

* **不解析历史 operation 的 bundle。** registry 只服务「当前该用哪个 adapter」；
  历史 operation/retry 一律读自己 frozen 的 `definition_bundle_id + sha256`
  （`definitions.DefinitionAliasRegistry.resolve_for_history` 恒抛）。alias 变化
  不影响历史 —— 本模块因此**不提供**任何按 entry_id 反查历史 bundle 的入口。
* **不放宽任何准入判据来抬高注册数。** :meth:`WorkpaperSyncAdapterRegistry.register_from_manifest`
  只按 manifest 派发，真正的准入仍是 :meth:`WorkpaperSyncAdapterRegistry.register` 的
  RG-1~RG-19 一条不少；供给不足的 entry 保持未注册并带**显式原因**，绝不用占位 id 充数。

## manifest 驱动的注册（Task 75）

Task 13~43 期间 :func:`build_production_registry` 只 `return WorkpaperSyncAdapterRegistry()`，
「注册哪些 entry」由每个调用方各拼一遍 attach —— 那是空壳形态。Task 75 起构造点同时绑定
**manifest 驱动的注册计划**（:func:`build_manifest_registration_plan`，每条 manifest entry
一项，带 provider 或带不可注册的显式原因），调用方唯一能补的是 DB session。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable, Final, Mapping, Sequence

from app.services.workpaper_sync.adapters.base import (
    ADAPTER_REQUIRED_ATTRS,
    ADAPTER_REQUIRED_METHODS,
    WorkpaperSyncAdapter,
)
from app.services.workpaper_sync.contracts import (
    ContractSchemaError,
    SyncContract,
    contract_path_for,
    load_contract,
)
from app.services.workpaper_sync.entry_profile import (
    Capability,
    DescriptorFacts,
    DescriptorMode,
    EntryProfileDriftError,
    EntryProfileError,
    EntryProfileMissingError,
    RoomFacts,
    assert_profile_consistent_with_capability,
    assert_profile_consistent_with_descriptor,
    assert_profile_consistent_with_room,
    capability_of,
    extract_entry_profile,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    BundleIntegrityError,
    DefinitionState,
    SyncDomainError,
    validate_bundle_slots,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

# ═══════════════════════════════════════════════════════════════════════════
# 0. 异常
# ═══════════════════════════════════════════════════════════════════════════


class RegistryError(SyncDomainError):
    error_code = "adapter_registry_invalid"


class AdapterShapeError(RegistryError):
    """adapter 不满足 protocol 形态（RG-1）。"""

    error_code = "adapter_shape_invalid"


class MatcherError(RegistryError):
    """matcher 空匹配或形态非法（RG-2）。"""

    error_code = "adapter_matcher_invalid"


class MatcherOverlapError(RegistryError):
    """两个 adapter 的 matcher 重叠（RG-3）。"""

    error_code = "adapter_matcher_overlap"


class RegistrationError(RegistryError):
    """注册本身不合法（RG-4 / RG-5 / RG-13）。"""

    error_code = "adapter_registration_invalid"


class DocumentTypeMismatchError(RegistryError):
    """document_type 在四个来源之间不一致（RG-6）。"""

    error_code = "adapter_document_type_mismatch"


class AuthorityModelMismatchError(RegistryError):
    """authority model 与 contract/bundle slot 组合不符（RG-8 / RG-9）。"""

    error_code = "adapter_authority_model_mismatch"


class StaleAdapterError(RegistryError):
    """adapter 挂着已漂移的 contract/entry（RG-10 / RG-11 / RG-12）。"""

    error_code = "adapter_stale"


class FakeBidirectionalError(RegistryError):
    """非 bidirectional entry 注册了双向 adapter（RG-18 / Property 3）。"""

    error_code = "adapter_fake_bidirectional"


class AdapterNotRegisteredError(RegistryError):
    """按 (wp_code, sheet_key, document_type) 解析不到 adapter。"""

    error_code = "adapter_not_registered"


class AmbiguousAdapterError(RegistryError):
    """解析到多个 adapter（matcher 重叠在注册期就该被拒，这里是纵深防御）。"""

    error_code = "adapter_resolution_ambiguous"


# ═══════════════════════════════════════════════════════════════════════════
# 1. matcher
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class EntryMatcher:
    """adapter 的匹配域。

    刻意用**精确 wp_code 集合**而不是 glob：glob 之间的重叠判定不可判定，只能靠
    人肉审阅，而 Requirement 6.1 要求 registry 在启动时机械地拒绝重叠。
    `sheet_keys` 为空表示「该 wp 的全部 sheet」。
    """

    document_type: str
    wp_codes: frozenset[str]
    sheet_keys: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.document_type not in {"xlsx", "docx"}:
            raise MatcherError(f"matcher.document_type 未登记: {self.document_type!r}")
        if not self.wp_codes:
            raise MatcherError(
                "matcher.wp_codes 为空 —— 空匹配的 adapter 永远不会被解析到，"
                "属于死注册（RG-2）"
            )
        for code in self.wp_codes:
            if not isinstance(code, str) or not code.strip() or not code.isascii():
                raise MatcherError(f"matcher.wp_codes 含非法 wp_code: {code!r}")
        for key in self.sheet_keys:
            if not isinstance(key, str) or not key.strip():
                raise MatcherError(f"matcher.sheet_keys 含空 sheet_key: {key!r}")

    def matches(self, *, wp_code: str, sheet_key: str | None, document_type: str) -> bool:
        if document_type != self.document_type or wp_code not in self.wp_codes:
            return False
        if not self.sheet_keys:
            return True
        return sheet_key is not None and sheet_key in self.sheet_keys

    def overlaps(self, other: "EntryMatcher") -> tuple[str, ...]:
        """返回重叠的 wp_code（空元组表示不重叠）。"""
        if self.document_type != other.document_type:
            return ()
        shared_codes = self.wp_codes & other.wp_codes
        if not shared_codes:
            return ()
        if not self.sheet_keys or not other.sheet_keys:
            # 任一侧是「全部 sheet」⇒ 与对侧必然相交。
            return tuple(sorted(shared_codes))
        if self.sheet_keys & other.sheet_keys:
            return tuple(sorted(shared_codes))
        return ()


# ═══════════════════════════════════════════════════════════════════════════
# 2. 注册记录
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AdapterRegistration:
    """一条 adapter 注册：adapter + matcher + frozen bundle + 交叉校验事实。

    `declared_capability` 是**注册方自己的声明**，刻意与 `descriptor.mode` 分开：

    * `descriptor.mode` 来自 Task 25/31 的服务端 launch descriptor（前端看到什么）；
    * `declared_capability` 来自 adapter 注册方（这个 adapter 声称能做什么）。

    🔴 早先把 `declares_bidirectional` 定义成 `descriptor.mode is bidirectional`，
    而 RG-16 又要求 `descriptor.mode == manifest capability` ⇒ RG-18「伪双向」永远
    不可能触发，成了结构性死代码（假绿第①源，实测过）。两者必须是可独立漂移的
    两个事实，才各有一条能真正打红的判据。
    """

    adapter: WorkpaperSyncAdapter
    entry_id: str
    matcher: EntryMatcher
    bundle: DefinitionBundleSnapshot
    descriptor: DescriptorFacts
    room: RoomFacts
    declared_capability: Capability
    contract: SyncContract | None = None

    @property
    def adapter_id(self) -> str:
        return str(getattr(self.adapter, "adapter_id", "") or "")

    @property
    def authority_model(self) -> AuthorityModel:
        return self.bundle.authority_model

    @property
    def declares_bidirectional(self) -> bool:
        return self.declared_capability is Capability.bidirectional


@dataclass(frozen=True)
class ObservedEntryFacts:
    """一条 entry 的**实测**descriptor / room 事实（RG-16 / RG-17 的另一侧）。

    🔴 必须由调用方从**运行时源码/行为**观察得来，**不能**从 manifest 里读回
    `room_model` / `scenario_profile`：两侧都读 manifest 时 RG-16/17 退化成自我比对，
    doc_key 实现漂移永远发现不了（假绿第③源）。生产观察器是
    `app.services.workpaper_sync.entry_source_facts.observe_descriptor_facts /
    observe_room_facts`。

    `descriptor is None` 表示「该入口今天根本产不出 descriptor」（不可达宿主）。
    """

    descriptor: DescriptorFacts | None
    room: RoomFacts


#: `build_report` 的实测事实注入点。registry 刻意**不**自己去扫源码：那会把
#: 「当前该用哪个 adapter」的职责和「源码事实采集」耦在一起，也会让 registry 依赖前端目录。
EntryFactsObserver = Callable[[Mapping[str, Any]], ObservedEntryFacts]


@dataclass(frozen=True)
class RegistryReport:
    """registry 闭合报告 —— 让「还差什么」可见，而不是只在异常里一次性抛。"""

    entry_count: int
    independent_entry_count: int
    registered_adapter_ids: tuple[str, ...] = ()
    missing_profile: tuple[str, ...] = ()
    profile_drift: tuple[str, ...] = ()
    bidirectional_without_adapter: tuple[str, ...] = ()
    fake_bidirectional: tuple[str, ...] = ()
    stale_adapters: tuple[str, ...] = ()
    contract_files_without_adapter: tuple[str, ...] = ()
    #: `entry_id -> 首个漂移原因`。让「哪条 RG 打红了」可读，而不是只有一个计数。
    profile_drift_reasons: Mapping[str, str] = field(default_factory=dict)

    @property
    def blocking_counts(self) -> Mapping[str, int]:
        return {
            "missing_profile": len(self.missing_profile),
            "profile_drift": len(self.profile_drift),
            "bidirectional_without_adapter": len(self.bidirectional_without_adapter),
            "fake_bidirectional": len(self.fake_bidirectional),
            "stale_adapters": len(self.stale_adapters),
            "contract_files_without_adapter": len(self.contract_files_without_adapter),
        }

    @property
    def blocking_total(self) -> int:
        return sum(self.blocking_counts.values())

    @property
    def closed(self) -> bool:
        return self.blocking_total == 0


# ═══════════════════════════════════════════════════════════════════════════
# 3. 逐条判据
# ═══════════════════════════════════════════════════════════════════════════


def assert_adapter_shape(adapter: Any) -> None:
    """RG-1：protocol 成员齐全且方法可调用。

    刻意**不**只用 `isinstance(adapter, WorkpaperSyncAdapter)`：`runtime_checkable`
    的 Protocol 只查属性存在性，一个把五个方法都写成 `None` 的桩也能通过。
    """
    missing_attrs = sorted(
        name
        for name in ADAPTER_REQUIRED_ATTRS
        if not isinstance(getattr(adapter, name, None), str)
        or not str(getattr(adapter, name)).strip()
    )
    if missing_attrs:
        raise AdapterShapeError(
            f"adapter {type(adapter).__name__} 缺非空字符串属性 {missing_attrs}"
            f"（protocol 要求 {sorted(ADAPTER_REQUIRED_ATTRS)}）"
        )
    not_callable = sorted(
        name for name in ADAPTER_REQUIRED_METHODS if not callable(getattr(adapter, name, None))
    )
    if not_callable:
        raise AdapterShapeError(
            f"adapter {getattr(adapter, 'adapter_id', type(adapter).__name__)} 的 "
            f"{not_callable} 不可调用 —— protocol 五个方法必须真实实现"
        )
    if not isinstance(adapter, WorkpaperSyncAdapter):
        raise AdapterShapeError(
            f"adapter {getattr(adapter, 'adapter_id', type(adapter).__name__)} 不满足 "
            "`WorkpaperSyncAdapter` protocol"
        )


def assert_bundle_usable(bundle: DefinitionBundleSnapshot, *, entry_id: str) -> None:
    """RG-7：bundle 必须 approved、四 slot 齐全、child 形态合法。

    slot 形态判据委托 `models.validate_bundle_slots`（单一真源），本函数只加
    「state 必须 approved」这一条 —— snapshot 可以被调用方直接构造，因此必须验。
    """
    if bundle.state is not DefinitionState.approved:
        raise BundleIntegrityError(
            f"entry {entry_id}: definition bundle state={bundle.state.value}，"
            "只有 approved 可被 registry/room 使用（Property 3 / 28）"
        )
    validate_bundle_slots(
        authority_model=bundle.authority_model,
        authority_model_definition_sha256=bundle.authority_model_definition_sha256,
        slots=bundle.slots,
    )


def assert_authority_model_contract_pairing(
    *, authority_model: AuthorityModel, contract: SyncContract | None, bundle: DefinitionBundleSnapshot,
    entry_id: str,
) -> None:
    """RG-8 / RG-9：authority model ↔ contract ↔ bundle contract slot 三向锁死。"""
    slot = bundle.slots.get(BundleSlot.contract)
    if slot is None:
        raise BundleIntegrityError(
            f"entry {entry_id}: bundle 缺 contract typed slot（slot omission）"
        )
    if authority_model is AuthorityModel.projection_contract:
        if contract is None:
            raise AuthorityModelMismatchError(
                f"entry {entry_id}: authority_model=projection_contract 必须解析到 approved "
                "per-entry contract —— 缺 contract 的 entry 不得进入 bidirectional 验收"
                "（Requirement 12.1 / Property 3）"
            )
        if not slot.is_definition:
            raise AuthorityModelMismatchError(
                f"entry {entry_id}: projection_contract bundle 的 contract slot 是 typed null "
                f"marker {slot.slot_type!r} —— marker 不得冒充 per-entry contract"
                "（Requirement 6.19）"
            )
        return
    if contract is not None:
        raise AuthorityModelMismatchError(
            f"entry {entry_id}: authority_model={authority_model.value} 不使用 projection "
            "contract，却传入了 SyncContract —— custom/opaque 只能在 contract slot 使用"
            "版本化 typed null marker（Requirement 6.19）"
        )
    if slot.is_definition:
        raise AuthorityModelMismatchError(
            f"entry {entry_id}: authority_model={authority_model.value} 的 bundle contract slot "
            f"却是 approved definition {slot.slot_digest!r} —— 与 authority model 声明矛盾"
        )


def assert_contract_identity_frozen(
    *, contract: SyncContract, bundle: DefinitionBundleSnapshot, entry_id: str
) -> None:
    """RG-10：contract canonical digest 必须等于 bundle 的 contract slot digest。"""
    slot = bundle.slots[BundleSlot.contract]
    if slot.slot_digest != contract.canonical_sha256:
        raise StaleAdapterError(
            f"entry {entry_id}: contract canonical digest {contract.canonical_sha256!r} 与 "
            f"frozen bundle 的 contract slot digest {slot.slot_digest!r} 不一致 —— definition "
            "漂移必须按 `template → instrumentation → contract → bundle → representation` "
            "重新发布（Property 28）"
        )
    contract.assert_matches_bundle_slots(bundle.slots)


def assert_contract_file_current(*, contract: SyncContract, entry_id: str) -> None:
    """RG-11：注册时挂的 contract 必须与磁盘契约文件当前内容一致。

    与 RG-10 是两条不同的漂移：RG-10 比「注册 ↔ frozen bundle」，本条比
    「注册 ↔ 磁盘真源」。只有磁盘文件被改过、adapter 却还挂着旧 digest 时才触发，
    这正是 stale adapter 最常见的形态。
    """
    path = contract_path_for(contract.contract_id)
    if not path.is_file():
        raise StaleAdapterError(
            f"entry {entry_id}: adapter 挂着 contract {contract.contract_id!r}，"
            f"但契约文件不存在: {path.name}"
        )
    try:
        on_disk = load_contract(contract.contract_id)
    except ContractSchemaError as exc:
        raise StaleAdapterError(
            f"entry {entry_id}: 磁盘契约 {path.name} 现在已无法通过强校验（{exc}）—— "
            "adapter 必须随契约一起更新"
        ) from exc
    if on_disk.canonical_sha256 != contract.canonical_sha256:
        raise StaleAdapterError(
            f"entry {entry_id}: 磁盘契约 {path.name} 的 canonical digest "
            f"{on_disk.canonical_sha256!r} 与注册时的 {contract.canonical_sha256!r} 不一致 —— "
            "stale adapter（RG-11）"
        )


def assert_document_types_agree(
    *,
    adapter_document_type: str,
    contract: SyncContract | None,
    matcher: EntryMatcher,
    manifest_document_type: str,
    entry_id: str,
) -> str:
    """RG-6：adapter / contract / matcher / manifest 四个来源的 document_type 必须一致。"""
    observed = {
        "adapter": adapter_document_type,
        "matcher": matcher.document_type,
        "manifest": manifest_document_type,
    }
    if contract is not None:
        observed["contract"] = contract.document_type
    distinct = sorted(set(observed.values()))
    if len(distinct) != 1:
        raise DocumentTypeMismatchError(
            f"entry {entry_id}: document_type 在四个来源之间不一致: {observed} —— "
            "模板缺失或类型与 adapter 不符必须显式报错，不得回退父级异类型文件"
            "（Requirement 9.5 / Property 41）"
        )
    return distinct[0]


# ═══════════════════════════════════════════════════════════════════════════
# 4. registry
# ═══════════════════════════════════════════════════════════════════════════


class WorkpaperSyncAdapterRegistry:
    """启动期 fail-closed adapter registry。

    用法（Tasks 40~57 / 62~64 逐 entry 注册）::

        registry = WorkpaperSyncAdapterRegistry(manifest=load_entry_manifest())
        registry.register(AdapterRegistration(...))     # 任一判据不过即抛
        registration = registry.resolve(wp_code="G7-1", sheet_key="g7-disclosure",
                                        document_type="xlsx")
        report = registry.build_report()                # 欠账可见
    """

    def __init__(self, *, manifest: Mapping[str, Any] | None = None) -> None:
        self._entries: Mapping[str, Mapping[str, Any]] = manifest_entries_by_id(manifest)
        self._by_adapter_id: dict[str, AdapterRegistration] = {}
        self._by_entry_id: dict[str, AdapterRegistration] = {}
        self._stale: list[str] = []
        self._plan: tuple["ManifestRegistrationPlanItem", ...] | None = None

    # ─────────────────────────────────────────────────────────────────
    @property
    def manifest_entries(self) -> Mapping[str, Mapping[str, Any]]:
        return self._entries

    # ─────────────────────────────────────────────────────────────────
    # manifest 驱动的注册计划（Task 75）
    # ─────────────────────────────────────────────────────────────────

    def bind_registration_plan(
        self, plan: Sequence["ManifestRegistrationPlanItem"]
    ) -> None:
        """绑定逐 entry 的注册计划。

        绑定发生在**构造点**（:func:`build_production_registry`），于是调用方唯一能补的
        是 DB session，补不了「注册哪些 entry」—— 这正是 Task 75 要拆掉的那种空壳形态
        （原先 `build_production_registry()` 只 `return WorkpaperSyncAdapterRegistry()`，
        注册哪些 entry 完全由每个调用方自行拼四条 attach）。
        """
        items = tuple(plan)
        seen = [item.entry_id for item in items]
        if len(set(seen)) != len(seen):
            raise RegistrationError(
                "注册计划里 entry_id 重复 —— 计划必须与 manifest entry 一一对应"
            )
        unknown = sorted(set(seen) - set(self._entries))
        if unknown:
            raise StaleAdapterError(
                f"注册计划包含 manifest 里没有的 entry: {unknown[:5]} —— 计划必须由 "
                "source-backed manifest 派生"
            )
        self._plan = items

    @property
    def registration_plan(self) -> tuple["ManifestRegistrationPlanItem", ...]:
        if self._plan is None:
            raise RegistrationError(
                "registry 未绑定注册计划 —— 生产 registry 只能由 "
                "`build_production_registry()` 构造（它负责绑定 manifest 驱动的计划）；"
                "手搓 `WorkpaperSyncAdapterRegistry()` 只用于测试 fixture"
            )
        return self._plan

    async def register_from_manifest(self, *, session: Any) -> "ManifestRegistrationOutcome":
        """执行已绑定的注册计划：逐 entry 真实注册，未满足供给的给**显式原因**。

        本方法自己不放宽任何准入判据：真正的注册仍由 :meth:`register` 执行（approved
        bundle / authority model 配对 / contract 双重漂移 / matcher 重叠一条不少），
        而 provider 侧的 `attach_*` 又必须先经 Task 75 的 published-identity 观测器读出
        frozen identity。本方法只做四件事：按计划派发、把「为什么没注册（供给不足）」记成
        可读原因、把**注册失败（真故障）** 记成 typed failure、把结果汇总成可断言的 outcome。

        🔴 **按 entry 隔离**（本 spec 核心修复）：某个 entry 的 provider/register 抛
        `SyncDomainError`（含 `ContractDriftError` / 观测器 `PublishedIdentityObserverError`
        / `RegistryError` 全部子类）时，记成一条 :class:`RegistrationFailure`（真故障，与
        「供给不足 reason」分型 —— AC 5.12）并**继续**下一个 entry，不让整批中断。非
        `SyncDomainError`（DB 故障 / `AttributeError` 等）仍**上抛** —— 那是真 bug，不能被
        当成 fail-visible 的注册失败吞掉。隔离前是「全有或全无」：一个 entry 抛错整批中断、
        缓存不写 ⇒ **所有** entry 的 sync 端点都 422（本 spec 起因）。隔离后 blast radius 只
        收敛到出错的那一个 entry；准入判据一条不放宽（`register()` RG-1~19 照跑）。
        """
        registered: list[str] = []
        # 🔴 已注册的 entry_id **实录**，不再由 `planned - reasons - failures` 反算：反算让
        #    记账等式变成恒真式（子集关系下无论如何都成立），于是「有 entry 被静默跳过」这条
        #    判据测不出任何东西 —— 变异 M19（把 `reasons[...] = supply` 换成 `pass`）实测
        #    GREEN 就是这个根因。三集合各有独立来源，跳过一个即三边之和少 1、立刻打红。
        registered_entries: list[str] = []
        reasons: dict[str, str] = {}
        failures: dict[str, RegistrationFailure] = {}
        for item in self.registration_plan:
            if item.entry_id in self._by_entry_id:
                registered.append(self._by_entry_id[item.entry_id].adapter_id)
                registered_entries.append(item.entry_id)
                continue
            if item.blocked_reason is not None:
                reasons[item.entry_id] = item.blocked_reason
                continue
            supply = await _describe_entry_supply(session=session, entry_id=item.entry_id)
            if supply is not None:
                reasons[item.entry_id] = supply
                continue
            # 🔴 只在这里隔离：只捕获 SyncDomainError（契约漂移 / 观测器 / 注册准入等
            #    fail-visible 域异常），记成 typed failure 并继续下一个 entry。非域异常
            #    （DB / AttributeError）仍上抛 —— 它是真 bug，不是「这个 entry 契约漂移」。
            try:
                provider = _load_entry_provider(item)
                ids = tuple(await provider(self, session=session))
            except SyncDomainError as exc:  # noqa: PERF203 - 隔离必须逐 entry
                failures[item.entry_id] = RegistrationFailure(
                    entry_id=item.entry_id,
                    error_code=str(getattr(exc, "error_code", "") or type(exc).__name__),
                    message=str(exc),
                    exc_type=type(exc).__name__,
                )
                continue
            if not ids:
                reasons[item.entry_id] = _describe_provider_block(item)
                continue
            registered.extend(ids)
            registered_entries.append(item.entry_id)
        return ManifestRegistrationOutcome(
            registered_adapter_ids=tuple(sorted(set(registered))),
            reasons=dict(sorted(reasons.items())),
            planned_entry_ids=tuple(item.entry_id for item in self.registration_plan),
            registered_entry_ids=tuple(sorted(set(registered_entries))),
            failures=dict(sorted(failures.items())),
        )

    def registrations(self) -> tuple[AdapterRegistration, ...]:
        return tuple(self._by_adapter_id[key] for key in sorted(self._by_adapter_id))

    # ─────────────────────────────────────────────────────────────────
    def register(self, registration: AdapterRegistration) -> None:
        """注册一个 adapter；任一判据不过即抛，不做部分注册。

        顺序刻意固定：形态 → 身份唯一 → manifest 归属 → **profile/descriptor/room/伪双向**
        → document_type → bundle → authority model → contract 双重漂移 → matcher 重叠。

        🔴 profile 三件事排在 contract 漂移**之前**是刻意的：这些是「这个 entry 根本
        没资格注册」的判据（不可编辑、descriptor 撒谎、doc_key 还带 mtime），而
        contract 漂移是「有资格但契约对不上」。反过来排会让一个连编辑都不允许的
        entry 收到「磁盘契约 stale」这种误导性诊断，也会在守卫里把 RG-14~RG-18
        全部遮蔽掉（实测过：contract 文件不存在时这四条一条都测不到）。
        """
        adapter = registration.adapter
        assert_adapter_shape(adapter)
        adapter_id = registration.adapter_id
        entry_id = registration.entry_id

        # ── ① 身份唯一与 contract_id 锁死（RG-4 / RG-5）
        if adapter_id in self._by_adapter_id:
            raise RegistrationError(f"adapter_id 重复注册: {adapter_id!r}")
        if entry_id in self._by_entry_id:
            raise RegistrationError(
                f"entry {entry_id} 已由 adapter "
                f"{self._by_entry_id[entry_id].adapter_id!r} 注册 —— 一个独立 entry 只能"
                "解析到唯一 adapter（Property 3）"
            )
        if registration.contract is not None and registration.contract.contract_id != adapter_id:
            raise RegistrationError(
                f"adapter_id {adapter_id!r} 与 contract_id "
                f"{registration.contract.contract_id!r} 不符（RG-4）"
            )

        # ── ② manifest 归属（RG-12 / RG-13）
        entry = self._entries.get(entry_id)
        if entry is None:
            self._stale.append(adapter_id)
            raise StaleAdapterError(
                f"adapter {adapter_id!r} 指向的 entry {entry_id!r} 不在 source-backed manifest "
                "中 —— 源码挂载点已变但 adapter 未同步（RG-12）"
            )
        if not entry.get("independent_entry"):
            raise RegistrationError(
                f"entry {entry_id} 是父组件重复入口（parent_entry_id="
                f"{entry.get('parent_entry_id')!r}）—— 只能复用其独立 entry 的 adapter，"
                "不得重复注册（Requirement 1.6 / 12.4）"
            )
        capability = capability_of(entry)
        if capability is Capability.unreachable:
            raise RegistrationError(
                f"entry {entry_id} 已裁决为 unreachable —— 不可达旧桩应删除，"
                "不得注册 adapter（Requirement 1.7）"
            )

        # ── ③ profile 与三类事实（RG-14 ~ RG-17）
        profile = extract_entry_profile(entry)
        assert_profile_consistent_with_capability(profile, capability)
        assert_profile_consistent_with_descriptor(profile, capability, registration.descriptor)
        assert_profile_consistent_with_room(profile, registration.room)

        # ── ④ 伪双向（RG-18 / Property 3）
        if registration.declares_bidirectional and capability is not Capability.bidirectional:
            raise FakeBidirectionalError(
                f"entry {entry_id}: manifest capability={capability.value}，却注册了 "
                "declared_capability=bidirectional 的 adapter —— 「仅能打开 OO」不得伪装成"
                "双向同步（Requirement 1.4 / 12.8 / Property 3）"
            )
        if capability is Capability.bidirectional and not registration.declares_bidirectional:
            raise RegistrationError(
                f"entry {entry_id}: manifest capability=bidirectional，但 adapter 只声明 "
                f"declared_capability={registration.declared_capability.value} —— 两侧必须一致"
            )

        # ── ⑤ document_type 四方一致（RG-6）
        assert_document_types_agree(
            adapter_document_type=str(getattr(adapter, "document_type", "")),
            contract=registration.contract,
            matcher=registration.matcher,
            manifest_document_type=str(entry.get("document_type") or ""),
            entry_id=entry_id,
        )

        # ── ⑥ bundle 与 authority model（RG-7 / RG-8 / RG-9）
        assert_bundle_usable(registration.bundle, entry_id=entry_id)
        assert_authority_model_contract_pairing(
            authority_model=registration.authority_model,
            contract=registration.contract,
            bundle=registration.bundle,
            entry_id=entry_id,
        )

        # ── ⑦ contract 双重漂移（RG-10 / RG-11）
        if registration.contract is not None:
            assert_contract_identity_frozen(
                contract=registration.contract, bundle=registration.bundle, entry_id=entry_id
            )
            assert_contract_file_current(contract=registration.contract, entry_id=entry_id)

        # ── ⑧ matcher 重叠（RG-3）
        for existing in self._by_adapter_id.values():
            shared = registration.matcher.overlaps(existing.matcher)
            if shared:
                raise MatcherOverlapError(
                    f"adapter {adapter_id!r} 与 {existing.adapter_id!r} 的 matcher 在 "
                    f"document_type={registration.matcher.document_type} 上重叠 wp_codes="
                    f"{list(shared)} —— 重叠 matcher 会让解析结果取决于注册顺序（RG-3）"
                )

        self._by_adapter_id[adapter_id] = registration
        self._by_entry_id[entry_id] = registration

    # ─────────────────────────────────────────────────────────────────
    def resolve(
        self, *, wp_code: str, document_type: str, sheet_key: str | None = None
    ) -> AdapterRegistration:
        hits = [
            reg
            for reg in self._by_adapter_id.values()
            if reg.matcher.matches(
                wp_code=wp_code, sheet_key=sheet_key, document_type=document_type
            )
        ]
        if not hits:
            raise AdapterNotRegisteredError(
                f"未注册 adapter: wp_code={wp_code!r} sheet_key={sheet_key!r} "
                f"document_type={document_type!r} —— 前端不得显示「可双向回写」，"
                "必须显示可操作原因（Requirement 1.4 / Property 3）"
            )
        if len(hits) > 1:
            raise AmbiguousAdapterError(
                f"wp_code={wp_code!r} sheet_key={sheet_key!r} 解析到多个 adapter: "
                f"{sorted(reg.adapter_id for reg in hits)}"
            )
        return hits[0]

    def resolve_for_entry(self, entry_id: str) -> AdapterRegistration:
        registration = self._by_entry_id.get(entry_id)
        if registration is None:
            raise AdapterNotRegisteredError(f"entry {entry_id!r} 未注册 adapter")
        return registration

    # ─────────────────────────────────────────────────────────────────
    def assert_bidirectional_ready(self, entry_id: str) -> AdapterRegistration:
        """Property 3：bidirectional entry 必须解析到唯一 adapter + approved authority
        model + 非空 immutable bundle；`projection_contract` 还必须有 approved contract。

        删掉 adapter、bundle 或 contract 任一项，本方法都会抛 —— 三条路径的异常类型
        各不相同（`AdapterNotRegisteredError` / `BundleIntegrityError` /
        `AuthorityModelMismatchError`），因此守卫能分辨到底缺了哪一项。
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            raise StaleAdapterError(f"entry {entry_id!r} 不在 source-backed manifest 中")
        capability = capability_of(entry)
        if capability is not Capability.bidirectional:
            raise FakeBidirectionalError(
                f"entry {entry_id}: capability={capability.value} 不是 bidirectional，"
                "不得按双向验收"
            )
        registration = self.resolve_for_entry(entry_id)
        assert_bundle_usable(registration.bundle, entry_id=entry_id)
        assert_authority_model_contract_pairing(
            authority_model=registration.authority_model,
            contract=registration.contract,
            bundle=registration.bundle,
            entry_id=entry_id,
        )
        if registration.contract is not None:
            assert_contract_identity_frozen(
                contract=registration.contract, bundle=registration.bundle, entry_id=entry_id
            )
        return registration

    # ─────────────────────────────────────────────────────────────────
    def build_report(
        self,
        *,
        contract_ids: Sequence[str] | None = None,
        facts_observer: EntryFactsObserver | None = None,
    ) -> RegistryReport:
        """产出闭合报告。

        不变式（Task 1 补齐 profile **之前和之后都成立**）：每条独立 entry 要么有
        完整合法 profile，要么不可能注册 adapter。因此 `missing_profile` 是可见的
        欠账计数，而不是被锁成基线的「当前真值」。

        `facts_observer` 给出时，RG-16/17 也逐条跑在**真实 manifest** 上：

        * RG-15（profile ↔ capability）只需 manifest 自身字段，**无条件**跑；
        * RG-16/17 需要 descriptor / room 实测事实，由观察器注入。

        这三条以前只能在手搓 fixture 上跑（零 adapter ⇒ `register()` 永不被调用），
        对真实数据结构性不可达 —— 那正是 additive 死代码（假绿第①源）。
        """
        missing_profile: list[str] = []
        profile_drift: list[str] = []
        profile_drift_reasons: dict[str, str] = {}
        bidirectional_without_adapter: list[str] = []
        fake_bidirectional: list[str] = []
        independent = 0
        for entry_id, entry in sorted(self._entries.items()):
            if not entry.get("independent_entry"):
                continue
            independent += 1
            capability = capability_of(entry)
            if capability is Capability.unreachable:
                continue
            profile = None
            try:
                profile = extract_entry_profile(entry)
            except EntryProfileMissingError:
                missing_profile.append(entry_id)
            except EntryProfileError:
                missing_profile.append(entry_id)
            if profile is not None:
                try:
                    assert_profile_consistent_with_capability(profile, capability)
                    if facts_observer is not None:
                        observed = facts_observer(entry)
                        if observed.descriptor is None:
                            raise EntryProfileDriftError(
                                f"entry {entry_id}: capability={capability.value} 的可达入口"
                                "产不出 descriptor 事实 —— 前端无法显示真实可用模式"
                                "（Requirement 1.4）"
                            )
                        assert_profile_consistent_with_descriptor(
                            profile, capability, observed.descriptor
                        )
                        assert_profile_consistent_with_room(profile, observed.room)
                except EntryProfileDriftError as exc:
                    profile_drift.append(entry_id)
                    profile_drift_reasons[entry_id] = str(exc)
            registration = self._by_entry_id.get(entry_id)
            if capability is Capability.bidirectional and registration is None:
                bidirectional_without_adapter.append(entry_id)
            if (
                registration is not None
                and registration.declares_bidirectional
                and capability is not Capability.bidirectional
            ):
                fake_bidirectional.append(entry_id)

        declared_contracts = set(contract_ids or ())
        used_contracts = {
            reg.contract.contract_id
            for reg in self._by_adapter_id.values()
            if reg.contract is not None
        }
        return RegistryReport(
            entry_count=len(self._entries),
            independent_entry_count=independent,
            registered_adapter_ids=tuple(sorted(self._by_adapter_id)),
            missing_profile=tuple(missing_profile),
            profile_drift=tuple(profile_drift),
            bidirectional_without_adapter=tuple(bidirectional_without_adapter),
            fake_bidirectional=tuple(fake_bidirectional),
            stale_adapters=tuple(sorted(set(self._stale))),
            contract_files_without_adapter=tuple(sorted(declared_contracts - used_contracts)),
            profile_drift_reasons=dict(profile_drift_reasons),
        )



# ═══════════════════════════════════════════════════════════════════════════
# engine adapter 交付裁决登记（Task 13 边界判据的翻转依据）
# ═══════════════════════════════════════════════════════════════════════════
#
# Task 13 交付时 `adapters/` 只有 `__init__.py` / `base.py` / `registry.py` 三份文件，
# 它的 `TestTask13ScopeBoundary::test_engine_packages_do_not_exist_yet` 把这个事实写成
# **绝对清单**。载体 engine 落地后那条清单必然过期，但**不能**把判据删掉 —— 删掉之后
# 「谁能往 `adapters/` 里放东西」就无人把守了。
#
# 做法与 `merge.RETIRED_DEFERRALS` 同款：把「已交付」与「仍未交付」各做成一张登记表，
# 边界判据改为与登记表**双向等值**：
#
# * 出现未登记的 `adapters/*.py` ⇒ 打红（有人绕过载体 gate 塞了个 engine adapter）；
# * 登记了却没有对应文件 ⇒ 打红（登记表与事实脱钩）；
# * 登记的 `engine_modules` 有一个不存在 ⇒ 打红（adapter 是空壳）；
# * :data:`PENDING_ENGINE_ADAPTERS` 里的 `forbidden_paths` 一旦出现 ⇒ 打红
#   （Word engine 未过 OO 9.4 pilot 门就先落地）。

#: **已交付**的载体 engine adapter。每条必须写明由哪个任务交付、adapter 模块本身、
#: 它背后的 engine 模块，以及为什么这次交付没有绕过载体 gate。
DELIVERED_ENGINE_ADAPTERS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "document_type": "xlsx",
        "delivered_by_task": "38",
        "adapter_module": "app/services/workpaper_sync/adapters/excel.py",
        "engine_modules": (
            "app/services/workpaper_sync/excel_extract.py",
            "app/services/workpaper_sync/excel_materialize.py",
            "app/services/workpaper_sync/excel_rematerialize.py",
        ),
        "identity_gate": "onlyoffice_excel_identity_carrier_contract.json",
        "reason": (
            "Task 38 落地 Excel identity-aware materializer/rematerializer，并按 protocol "
            "把 Task 37 的 extractor 与三个共用 verifier 接到 `ContentMutationService` 与 "
            "`oo_to_html` 的既有调用点上。载体 gate 没有被绕过：Task 5 的真实 OO 9.4 探针"
            "先证明了 hidden sheet / defined name / Excel Table + hidden UUID 列三类载体在"
            "编辑、插删、排序、复制、forcesave、下载、重开后仍保留（Requirement 6.16），"
            "Task 17 才据此注入，Task 36 的 frozen entry gate 才允许 engine 入口放行。"
            "本 adapter 自身零写入面（`assert_no_mutation_surface` 在构造时逐字段实测），"
            "既不提交也不切 pointer。"
        ),
    },
)

#: **仍未交付**的载体 engine adapter。`forbidden_paths` 是「在 gate 通过前这些路径不得
#: 出现」的可执行判据 —— 它替代了原先那条写死三个文件名的绝对清单。
PENDING_ENGINE_ADAPTERS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "document_type": "docx",
        "blocking_task": "59,60,61",
        "forbidden_paths": (
            "app/services/workpaper_sync/adapters/word.py",
            "app/services/workpaper_sync/adapters/word",
        ),
        "identity_gate": "onlyoffice_word_sdt_carrier_contract.json",
        "reason": (
            "Word tagged-SDT engine 的载体门是 F2-22/F2-23 的真实 OnlyOffice 9.4 pilot"
            "（design §OO 9.4 pilot 门七步）。该门未过之前不得落地 Word adapter，也不得"
            "降级成段落索引 / 正则定位（Requirement 6.16 / Property 34）。"
        ),
    },
)

#: Task 13 自己交付的三份文件。engine adapter 之外的 `adapters/*.py` 只能是这三个
#: + `NON_CARRIER_COMPANION_MODULES`（见下）。
TASK13_ADAPTER_MODULES: Final[tuple[str, ...]] = (
    "__init__.py",
    "base.py",
    "registry.py",
)

#: **非载体**伴生模块 —— `adapters/` 下不实现任何 carrier protocol 的纯数据 / 纯声明文件。
#:
#: 🔴 为什么要单独一类而不是塞进 `TASK13_ADAPTER_MODULES`：
#: `test_engine_adapters_match_the_delivery_registry_exactly` 用
#: 「`adapters/*.py` 文件集合 == 登记集合」来挡「有人新增 adapter 绕过载体 gate」。
#: 那条判据的保护对象是**载体**。把数据模块混进 Task 13 那三份里会模糊语义
#: （那三份是「Task 13 交付物」这个历史事实，不该被后来的文件污染）；
#: 而放宽成 glob 白名单又会让真正新增的 carrier 也蒙混过关。
#: ⇒ 单列一类，**逐个显式登记 + 写明为什么它不是载体**，判据对 carrier 的力度不变。
#:
#: 登记项：
#: * `delivered_contracts_ledger.py` —— `DELIVERED_PER_ENTRY_CONTRACTS` 的数据台账。
#:   从本文件抽出（曾占 1172 行 / 47%，且按设计每交付一条契约就增 40~60 行，
#:   连续两次提交各触发一次行数门禁；继续上调 whitelist 基线等于预留膨胀空间，
#:   是白名单注释第 7 行明令禁止的）。它**零 import 平台运行时**、
#:   不含任何函数与类，只有一个 `Final[tuple[Mapping[str, Any], ...]]` 字面量。
NON_CARRIER_COMPANION_MODULES: Final[tuple[str, ...]] = (
    "delivered_contracts_ledger.py",
)


#: 逐 entry 契约的交付登记表 —— 数据已抽到伴生模块 `delivered_contracts_ledger.py`
#: （它在本文件里曾占 1172 行 / 47%，且按设计持续增长，两次触发行数门禁）。
#:
#: 🔴 **本处只 re-export，追加新条目请改那个文件**。所有既有 import 路径不变：
#:    `from ...adapters.registry import DELIVERED_PER_ENTRY_CONTRACTS` 仍可用。
from app.services.workpaper_sync.adapters.delivered_contracts_ledger import (  # noqa: E402
    DELIVERED_PER_ENTRY_CONTRACTS,
)


# ═══════════════════════════════════════════════════════════════════════════
# manifest 驱动的注册计划与执行（Task 75）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ManifestRegistrationPlanItem:
    """一条 manifest entry 的注册计划。

    `provider_module` 是提供该 entry **自己**的 `attach_pilot_adapters` 的模块 ——
    刻意一 entry 一 provider 而不是一个共享 attach：复用另一个 entry 的 attach 就等于
    复用它的 contract / bundle / candidate（Tasks 40~57 正文明令禁止）。

    `blocked_reason` 非 `None` 时表示**静态**（不查库就能判定）的不可注册原因，例如
    「manifest 里没有该 entry 的 per-entry 生产契约」「parent 重复入口」
    「已裁决 unreachable」。它就是任务正文要求的「未满足供给的 entry 保持 `null` 加显式
    原因」里的那个原因。
    """

    entry_id: str
    capability: Capability
    contract_id: str | None = None
    provider_module: str | None = None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class RegistrationFailure:
    """一个 entry 的**注册失败**（真故障，与「供给不足 reason」分型）。

    起因是该 entry 的 provider attach / `register()` 抛了 `SyncDomainError`（如
    `ContractDriftError`：契约声明的受管结构与已发布 representation 漂移）。它**不是**
    「本项目无此数据」——AC 5.12 明令二者必须可分辨。请求解析到该 entry 时，端点据此把
    **原始** error_code/message 透传成 422（不退化成泛化 `adapter_not_ready`）。
    """

    entry_id: str
    error_code: str
    message: str
    exc_type: str


@dataclass(frozen=True)
class ManifestRegistrationOutcome:
    """一次 `register_from_manifest()` 的结果。

    未注册的计划 entry 分两类，**必须可分辨**（AC 5.12）：
      * ``reasons`` —— 供给不足（静态/数据原因，非故障：还没 approved bundle / published
        representation 等）；
      * ``failures`` —— 注册失败（真故障：provider/register 抛 `SyncDomainError`，如契约漂移）。

    记账等式（守卫据此打红「没有 entry 被静默跳过」）：
    ``len(registered_entry_ids) + len(reasons) + len(failures) == len(planned_entry_ids)``，
    三集合的 entry_id **两两不相交**。

    🔴 ``registered_entry_ids`` 是 :meth:`WorkpaperSyncAdapterRegistry.register_from_manifest`
    **实录**的字段，**不是** ``planned - reasons - failures`` 反算出来的。反算过一版：那样写
    上面那条等式在子集关系下**恒真**，于是「静默跳过一个 entry」照样满足等式 ⇒ 判据是装饰
    （变异 M19 实测 GREEN）。各集合独立来源之后，跳过一个 entry 会让三边之和少 1，立刻打红。
    """

    registered_adapter_ids: tuple[str, ...]
    reasons: Mapping[str, str]
    planned_entry_ids: tuple[str, ...]
    registered_entry_ids: tuple[str, ...]
    #: 🔴 注册失败（真故障）—— 与 `reasons` 并列、不相交。默认空 dict 保持向后兼容
    #: （历史构造 outcome 的测试无需改；隔离路径按 entry 填充）。
    failures: Mapping[str, RegistrationFailure] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "registered_adapter_ids": list(self.registered_adapter_ids),
            "registered_entry_ids": list(self.registered_entry_ids),
            "planned_entry_count": len(self.planned_entry_ids),
            "unregistered_entry_count": len(self.reasons) + len(self.failures),
            "reasons": dict(self.reasons),
            "failures": {
                eid: {
                    "error_code": f.error_code,
                    "message": f.message,
                    "exc_type": f.exc_type,
                }
                for eid, f in self.failures.items()
            },
        }


#: `provider_module` 的取值必须落在这张白名单里。写成白名单而不是「从登记表里读到什么就
#: import 什么」：登记表是可编辑常量，任意 import 目标等于给自己开了一条动态加载面。
_ALLOWED_PROVIDER_MODULES: Final[frozenset[str]] = frozenset(
    {
        "app.services.workpaper_sync.pilot_simple_checklist",
        "app.services.workpaper_sync.pilot_d2_large_json",
        "app.services.workpaper_sync.pilot_h1_grouped_dynamic",
        "app.services.workpaper_sync.pilot_g7_two_level_dynamic",
        # ── G5-1 追加（Phase 5 canary，harness 无关的独立 entry 双向路径）──────
        "app.services.workpaper_sync.phase5_d1_notes_receivable",
        "app.services.workpaper_sync.phase5_d7_contract_liabilities",
        "app.services.workpaper_sync.phase5_d3_prepaid_receipts",
        "app.services.workpaper_sync.phase5_d6_contract_assets",
        "app.services.workpaper_sync.phase5_d5_receivables_financing",
        "app.services.workpaper_sync.phase5_d4_revenue_detail",
        # ── E1 canary（spec: e1-sync-coverage-and-first-canary）──────
        "app.services.workpaper_sync.phase5_e1_monetary_fund",
        # ── F1 canary（spec: f1-sync-coverage-and-first-canary）──────
        "app.services.workpaper_sync.phase5_f1_prepayment",
        # ── F2 四 lane（spec: f2-sync-coverage-four-entry-lanes）──────
        "app.services.workpaper_sync.phase5_f2_inventory_main",
        "app.services.workpaper_sync.phase5_f2_stocktake_bundle",
        "app.services.workpaper_sync.phase5_f2_inventory_valuation",
        "app.services.workpaper_sync.phase5_f2_inventory_special",
        # ── F3 / F4 / F5 canary（spec: f{3,4,5}-sync-coverage-and-first-canary）──────
        "app.services.workpaper_sync.phase5_f3_notes_payable",
        "app.services.workpaper_sync.phase5_f4_accounts_payable",
        "app.services.workpaper_sync.phase5_f5_cost_of_sales",
        # ── G2 canary（spec: g-cycle-sync-foundation-and-first-canary · Task 14）──
        #    🔴 G 循环首条 `phase5_*` provider。同循环的 G7 走
        #    `pilot_g7_two_level_dynamic`（上面 pilot 段已登记），两者并存是裁决 GF-H3
        #    的直接结果：G7 是旧先导范式，新建的 17 条一律 `phase5_*`。
        "app.services.workpaper_sync.phase5_g2_interest_receivable",
        # ── H 循环（spec: h-cycle-sync-… / h2-h6-h10-… / h4-h8-…）──────────────
        #    🔴 同循环的 H1 走 `pilot_h1_grouped_dynamic`（上面 pilot 段已登记），
        #    新建的一律 `phase5_*`（同 G2/G7 并存的裁决）。
        #    🔴 **本段是补漏**：H9 的台账条目在首轮（commit 91933bd68）就已登记，
        #    但漏了这张白名单 ⇒ `test_registrar_delegates_to_each_entry_own_attach`
        #    的 `len(_ALLOWED_PROVIDER_MODULES) == len(DELIVERED_PER_ENTRY_CONTRACTS)`
        #    从那时起就红。追加台账条目时**必须同步这里**，否则 provider 会在
        #    `build_manifest_registration_plan` 里被判「不得从登记表任意 import」而拒绝注册。
        "app.services.workpaper_sync.phase5_h9_lease_liabilities",
        "app.services.workpaper_sync.phase5_h6_asset_disposal_clearing",
        "app.services.workpaper_sync.phase5_h4_engineering_materials",
        "app.services.workpaper_sync.phase5_h8_right_of_use_assets",
        "app.services.workpaper_sync.phase5_h2_construction_in_progress",
        "app.services.workpaper_sync.phase5_h3_investment_property",
        "app.services.workpaper_sync.phase5_h5_oil_gas_assets",
        "app.services.workpaper_sync.phase5_h7_biological_assets",
        "app.services.workpaper_sync.phase5_h10_asset_disposal_income",
        # ── G 循环 lane（spec: g4-g6-… / g5-… / g-cycle-single-region-…）────────
        #    🔴 **同上一段的补漏形态**：台账条目已登记但漏了白名单。
        "app.services.workpaper_sync.phase5_g8_other_equity",
        "app.services.workpaper_sync.phase5_g9_other_noncurrent",
        "app.services.workpaper_sync.phase5_g10_trading_liabilities",
        "app.services.workpaper_sync.phase5_g1_trading_financial_assets",
        "app.services.workpaper_sync.phase5_g3_dividend_receivable",
        "app.services.workpaper_sync.phase5_g4_bond_investment",
        "app.services.workpaper_sync.phase5_g5_long_term_receivable",
        "app.services.workpaper_sync.phase5_g6_other_bond",
        "app.services.workpaper_sync.phase5_g11_investment_income",
        "app.services.workpaper_sync.phase5_g12_net_hedge_gains",
        "app.services.workpaper_sync.phase5_g13_fair_value_changes",
        "app.services.workpaper_sync.phase5_g14_credit_impairment",
        # ── I 循环（spec: i-cycle-sync-… / i1-i3-… / i2-i4-i5-…）───────────────
        #    🔴 **6/6 全覆盖**。表头层级覆盖 1/2/3/4 四种
        #    （i6 单级 · i5 两级 · i2+i4 三级 · i1+i3 四级=平台上界）。
        "app.services.workpaper_sync.phase5_i1_intangible_assets",
        "app.services.workpaper_sync.phase5_i2_development_expenditure",
        "app.services.workpaper_sync.phase5_i3_goodwill",
        "app.services.workpaper_sync.phase5_i4_long_term_prepaid",
        "app.services.workpaper_sync.phase5_i5_other_noncurrent_assets",
        "app.services.workpaper_sync.phase5_i6_research_development_expense",
        # ── J 循环（spec: j-cycle-sync-foundation-and-first-canary）────────────
        #    🔴 manifest 里 J 只有 2 条 entry（1 独立 + 1 parent_duplicate）
        #    ⇒ 本循环恒 1 条 provider。
        "app.services.workpaper_sync.phase5_j1_employee_compensation",
    }
)


def build_manifest_registration_plan(
    entries: Mapping[str, Mapping[str, Any]]
) -> tuple[ManifestRegistrationPlanItem, ...]:
    """由 source-backed manifest + 交付登记表**现算**注册计划（每条 entry 一项）。

    provider 表从 :data:`DELIVERED_PER_ENTRY_CONTRACTS` 现算，不写第二份清单：Tasks
    46~57 每追加一行契约登记，计划自动多一个可注册 entry；反之登记表里出现 manifest 没有
    的 entry_id 会被 `bind_registration_plan` 打红。
    """
    providers: dict[str, Mapping[str, Any]] = {}
    for row in DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            raise RegistrationError("per-entry 契约登记行缺 entry_id")
        if entry_id in providers:
            raise RegistrationError(
                f"per-entry 契约登记表里 entry {entry_id!r} 出现两次 —— 一个独立 entry 只能"
                "解析到唯一 adapter（Property 3）"
            )
        providers[entry_id] = row

    plan: list[ManifestRegistrationPlanItem] = []
    for entry_id in sorted(entries):
        entry = entries[entry_id]
        capability = capability_of(entry)
        row = providers.get(entry_id)
        blocked: str | None = None
        if row is None:
            blocked = (
                "尚无该 entry 自己的 approved per-entry 生产契约（不在 "
                "`DELIVERED_PER_ENTRY_CONTRACTS` 里）—— 逐 entry 发布由 Tasks 46~57 / "
                "62~64 承接；禁止复用别的 entry 的契约"
            )
        elif not entry.get("independent_entry"):
            blocked = (
                f"parent 重复入口（parent_entry_id={entry.get('parent_entry_id')!r}）—— "
                "只能复用其独立 entry 的 adapter（Requirement 1.6 / 12.4）"
            )
        elif capability is Capability.unreachable:
            blocked = "已裁决 unreachable —— 不可达旧桩应删除，不得注册 adapter（Requirement 1.7）"
        provider_module = None if row is None else str(row.get("provider_module") or "").strip()
        if row is not None and blocked is None and not provider_module:
            raise RegistrationError(
                f"entry {entry_id}: 契约登记行缺 `provider_module` —— 每个 entry 必须指明"
                "提供它**自己**的 attach 的模块，不得共用别的 entry 的 attach"
            )
        plan.append(
            ManifestRegistrationPlanItem(
                entry_id=entry_id,
                capability=capability,
                contract_id=None if row is None else str(row.get("contract_id") or "") or None,
                provider_module=provider_module or None,
                blocked_reason=blocked,
            )
        )
    return tuple(plan)


def _load_entry_provider(item: ManifestRegistrationPlanItem) -> Any:
    """按白名单加载该 entry 自己的 `attach_pilot_adapters`。"""
    module_path = item.provider_module or ""
    if module_path not in _ALLOWED_PROVIDER_MODULES:
        raise RegistrationError(
            f"entry {item.entry_id}: provider_module {module_path!r} 不在白名单 "
            f"{sorted(_ALLOWED_PROVIDER_MODULES)} 内 —— 不得从登记表任意 import"
        )
    module = importlib.import_module(module_path)
    attach = getattr(module, "attach_pilot_adapters", None)
    if attach is None or not callable(attach):
        raise RegistrationError(
            f"entry {item.entry_id}: provider {module_path} 没有可调用的 "
            "`attach_pilot_adapters` —— provider 是空壳"
        )
    return attach


def _describe_provider_block(item: "ManifestRegistrationPlanItem") -> str:
    """provider returned an empty tuple -> recompute its own precondition as an explicit reason.

    The provider early-exit branches are `return ()`, not a raise, so the old text
    (see its own raised reason) pointed at an exception that never exists. When supply
    is satisfied but nothing registers, the caller could only see returned empty
    tuple while the real cause -- manifest capability not yet adjudicated
    bidirectional -- was discarded. AC 5.12 requires an explicit reason, so this
    reuses the provider own precondition function rather than writing a second one.

    Only the provider own narrow selection error is caught; anything else propagates
    (a broad except here would re-create the fail-open this fixes).
    """
    module_path = item.provider_module or ""
    module = importlib.import_module(module_path)
    selection_error = getattr(module, "PilotSelectionError", None)
    assert_capability = getattr(module, "assert_manifest_capability_enabled", None)
    if callable(assert_capability) and isinstance(selection_error, type):
        try:
            assert_capability()
        except selection_error as exc:
            return (
                f"provider {module_path}.attach_pilot_adapters 返回空元组，其"
                f"自身 capability 前置未过: {exc}"
            )
    # provider 自身 capability 前置过了，但仍返回空 —— 真因是 **manifest 实测 capability
    # 尚未裁决 bidirectional**。把它显式点名（引用 `item.capability` 现算值），reason 才是
    # 可执行事实（AC 5.12），不退化成「早退分支无原因」的悬空指针。
    return (
        f"provider {module_path}.attach_pilot_adapters 返回空元组：manifest 实测 "
        f"capability={item.capability.value}（非 bidirectional）—— 未裁决双向前不注册 "
        "adapter，是**顺序**而非遗漏。capability 裁决为 bidirectional（reviewed overlay，"
        "finalize 之后）后 provider 才会走 build_excel_adapter → register()。"
    )

async def _describe_entry_supply(*, session: Any, entry_id: str) -> str | None:
    """查供给：够了返回 `None`，不够返回**显式原因**。

    只读三件事，全部是 published 侧的冻结事实（**不碰** candidate 表）：entry current
    pointer 是否存在、它指向的 representation 是否存在、该 representation 是否绑定了
    definition bundle。三者都在 ⇒ 交给 provider 去跑真实观测器 + `register()`。
    """
    import sqlalchemy as sa

    from app.models.workpaper_sync_models import (
        WorkpaperContentRepresentation,
        WorkpaperSyncEntryState,
    )

    representation_id = (
        (
            await session.execute(
                sa.select(WorkpaperSyncEntryState.current_representation_id).where(
                    WorkpaperSyncEntryState.entry_id == entry_id
                )
            )
        )
        .scalars()
        .first()
    )
    if representation_id is None:
        return (
            "该 entry 还没有 current published representation（`working_paper_sync_entry_"
            "state` 无行）—— approved bundle 与 candidate 受控 attach 是 Task 76 的交付，"
            "published representation 则由 `ContentMutationService.commit(...)`（首版 "
            "content version）与 Task 36 / 77 的 finalize gate（同 content version 的新"
            "代际）产出（Task 77 更正首版的误记）；candidate 永不可作为运行态 substrate"
            "（AC 6.18 / Property 67）"
        )
    representation = (
        await session.execute(
            sa.select(WorkpaperContentRepresentation).where(
                WorkpaperContentRepresentation.id == representation_id
            )
        )
    ).scalar_one_or_none()
    if representation is None:
        return (
            f"entry current pointer 指向不存在的 representation {representation_id} —— "
            "半成功态必须可见，不得按「没有身份」处理"
        )
    if representation.definition_bundle_id is None:
        return (
            f"current representation {representation_id} 没有绑定 immutable definition "
            "bundle —— 缺 bundle 的 representation 不得注册 adapter（AC 3.3 / Property 3）"
        )
    return None


#: 生产 registry 单例的构造点。绑定 source-backed manifest **与** manifest 驱动的注册
#: 计划（Task 75 之前这里只 `return WorkpaperSyncAdapterRegistry()`，注册哪些 entry 由每个
#: 调用方各拼一遍 attach —— 那是空壳形态）。真正的注册由
#: :meth:`WorkpaperSyncAdapterRegistry.register_from_manifest` 在请求路径上执行；调用方
#: 唯一能补的是 DB session，补不了「注册哪些 entry」。
def build_production_registry(
    *, manifest: Mapping[str, Any] | None = None
) -> WorkpaperSyncAdapterRegistry:
    registry = WorkpaperSyncAdapterRegistry(manifest=manifest)
    registry.bind_registration_plan(
        build_manifest_registration_plan(registry.manifest_entries)
    )
    return registry


__all__ = [
    "RegistryError", "AdapterShapeError", "MatcherError", "MatcherOverlapError",
    "RegistrationError", "DocumentTypeMismatchError", "AuthorityModelMismatchError",
    "StaleAdapterError", "FakeBidirectionalError", "AdapterNotRegisteredError",
    "AmbiguousAdapterError",
    "EntryMatcher", "AdapterRegistration", "RegistryReport",
    "ObservedEntryFacts", "EntryFactsObserver",
    "assert_adapter_shape", "assert_bundle_usable",
    "assert_authority_model_contract_pairing", "assert_contract_identity_frozen",
    "assert_contract_file_current", "assert_document_types_agree",
    "WorkpaperSyncAdapterRegistry", "build_production_registry",
    "DELIVERED_ENGINE_ADAPTERS", "PENDING_ENGINE_ADAPTERS", "TASK13_ADAPTER_MODULES",
    "NON_CARRIER_COMPANION_MODULES",
    "DELIVERED_PER_ENTRY_CONTRACTS",
    "ManifestRegistrationPlanItem", "ManifestRegistrationOutcome", "RegistrationFailure",
    "build_manifest_registration_plan",
]
