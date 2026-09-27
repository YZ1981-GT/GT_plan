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

#: Task 13 自己交付的三份文件。engine adapter 之外的 `adapters/*.py` 只能是这三个。
TASK13_ADAPTER_MODULES: Final[tuple[str, ...]] = (
    "__init__.py",
    "base.py",
    "registry.py",
)


# ═══════════════════════════════════════════════════════════════════════════
# per-entry 生产契约交付登记（Task 40 追加；只加不动）
# ═══════════════════════════════════════════════════════════════════════════
#
# Task 13 交付时 `backend/data/workpaper_sync_contracts/` 里没有任何生产契约，它的
# `test_contract_directory_holds_no_production_contract_yet` 把这个事实写成**绝对空清册**。
# Tasks 40~57 / 62~64 逐 entry 发布契约后那条清册必然过期，但**不能**把判据删掉 ——
# 删掉之后「谁能往契约目录里放生产契约」就无人把守了。
#
# 做法与 :data:`DELIVERED_ENGINE_ADAPTERS` / `merge.RETIRED_DEFERRALS` 同款：把「已发布」
# 做成一张登记表，边界判据改为与 `contracts.available_contract_ids()` **双向等值**：
#
# * 出现未登记的生产契约 ⇒ 打红（有人绕过 pilot 门放了个契约）；
# * 登记了却没有对应文件 ⇒ 打红（登记表与事实脱钩）；
# * 登记的 `entry_id` 不在 source-backed manifest 里 ⇒ 打红（契约指向已消失的入口）。

#: **已发布**的 per-entry 生产契约。每条写明由哪个任务发布、对应哪个 manifest entry、
#: 权威模板载体，以及"为什么这次发布没有跳过 finalize 顺序"。
DELIVERED_PER_ENTRY_CONTRACTS: Final[tuple[Mapping[str, Any], ...]] = (
    {
        "contract_id": "b60.hour_budget",
        "provider_module": "app.services.workpaper_sync.pilot_simple_checklist",
        "delivered_by_task": "40",
        "pilot_class": "simple_checklist",
        "entry_id": "xlsx/b60/gt-b60-bundle",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "B/B60-1 审计项目工时预算与控制表.xlsx",
        "adapter_registered": False,
        "reason": (
            "Task 40 冻结 simple_checklist pilot 的唯一合格 entry（174 个候选里唯一"
            "independent 且 wp_code 与 wp_templates/_index.json 精确相等、零回退的那个），"
            "逐 sheet 读权威模板后人工审核并发布 approved authority model / per-entry "
            "contract / non-null bundle。`adapter_registered=False` 是**顺序**而不是遗漏："
            "任务正文要求「经 Task 36 finalize Task 17 candidate 为 published "
            "representation 后，方可注册 adapter / 接宿主 / 启用 capability」。"
            "Task 75 已交付该 finalize 缺的公共观测器（`published_identity_observer`）并把 "
            "`resolve_published_frozen_definitions()` 改成真实现；今天仍未注册的原因换成了"
            "**供给**：`working_paper_sync_definition_bundle` / "
            "`working_paper_content_representation` / `working_paper_sync_entry_state` 三表"
            "实测 0 行。其中 approved bundle 与 candidate 受控 attach 是 Task 76 的交付；"
            "**published representation 不是** —— 它的生产者是 "
            "`ContentMutationService.commit(...)`（首版 content version）与 Task 36 / Task 77 "
            "的 finalize gate（同 content version 的新代际）。"
            "（Task 77 更正：首版此处把 representation 一并归给 Task 76，属误记。）"
            "`register_from_manifest()` 对本 entry 给出的显式原因即"
            "「还没有 current published representation」。"
            "契约孤儿由 `RegistryReport.contract_files_without_adapter` 持续可见。"
        ),
    },
    # ── Task 41 追加（只加不动；本条起至 tuple 结束是 Task 41 的字节区间）────────
    {
        "contract_id": "d2.receivable_detail",
        "provider_module": "app.services.workpaper_sync.pilot_d2_large_json",
        "delivered_by_task": "41",
        "pilot_class": "d2_large_json",
        "entry_id": "xlsx/gt-d2-accounts-receivable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx",
        "adapter_registered": True,
        "reason": (
            "Task 41 冻结 d2_large_json pilot 的唯一候选 entry（`assess_pilot_classes()` 实测 "
            "1 个候选、bidirectional 0 个），逐 sheet 读权威模板的 11 张 sheet 后只声明受管 "
            "sheet `明细表D2-2`，按 stable field + row UUID 把真实 906,239 字节的 HTML store "
            "载荷（`checklist_responses.item_id='D2-detail-rows'`，1260 行 × 39 列）拆成 "
            "49,140 个字段，禁止把整 JSON 当一个字段（AC 6.9 / 6.12）。"
            "`adapter_registered=True`：2026-09-07 实测真库 `register_from_manifest()` 已注册"
            "`d2.receivable_detail` —— 该 entry 的 manifest 已由 reviewed overlay 裁决为 "
            "`bidirectional`（`adapter_id` 同步写回），approved bundle / current published "
            "representation / entry_state 三件供给齐备，观测器真读出 frozen identity 后走完 "
            "`build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）。"
            "顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的 reviewed overlay "
            "动作（Task 36 / Task 77 的 finalize gate 已产出 published representation），"
            "不是本登记表自己宣称的。"
            "🔴 「注册成功」≠「pilot 已验收」：真实 OO required scenarios 未按 Task 70 "
            "刷新，evidence 保持 UNVERIFIABLE（`RegistryReport.contract_files_without_adapter` "
            "对本 entry 已不再登记为孤儿）。"
        ),
    },
    # ── Task 42 追加（只加不动；本条起至 tuple 结束是 Task 42 的字节区间）────────
    {
        "contract_id": "h1.disposal_check",
        "provider_module": "app.services.workpaper_sync.pilot_h1_grouped_dynamic",
        "delivered_by_task": "42",
        "pilot_class": "h1_grouped_dynamic",
        "entry_id": "xlsx/gt-h1-fixed-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H1 固定资产.xlsx",
        "adapter_registered": True,
        "reason": (
            "Task 42 冻结 h1_grouped_dynamic pilot 的唯一候选 entry（`assess_pilot_classes()` "
            "实测 1 个候选、bidirectional 0 个），逐 sheet 读权威模板的 26 张 sheet 后只声明"
            "受管 sheet `减少检查表H1-8` —— 它是契约 schema 域内（`header_rows` 1..3）分组"
            "最深的一张：三级表头 10/11/12 行（4 个横向组 + 3 个中层 + 6 个真叶子）、"
            "动态行 13..27、L/O 两列逐行公式、A28 合计 footer、B/E 两条数据验证。"
            "25 个字段各带 source_ref / header_source_ref / mid_source_ref / "
            "group_source_ref；骨架行数由 `skeleton_row_count(seed) = max(seed,1)` 决定，"
            "不写死模板自带的 15 行。X 列是模板占位列（表头 `……`）故按 Requirement 6.1 "
            "不声明；UUID 列取 AB 而非 AA（AA11 有可见注解）。"
            "工作簿里分组更深的 `明细表H1-2`（四级表头）**表达不了**，登记为 "
            "`pilot_h1_grouped_dynamic.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE`。"
            "`adapter_registered=True`：2026-09-07 实测真库 `register_from_manifest()` 已注册"
            "`h1.disposal_check` —— 该 entry 的 manifest 已由 reviewed overlay 裁决为 "
            "`bidirectional`（`adapter_id` 同步写回），approved bundle / current published "
            "representation / entry_state 三件供给齐备，观测器真读出 frozen identity 后走完 "
            "`build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）。"
            "顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的 reviewed overlay "
            "动作（Task 36 / Task 77 的 finalize gate 已产出 published representation）。"
            "🔴 「注册成功」≠「pilot 已验收」：真实 OO required scenarios 未按 Task 70 "
            "刷新，evidence 保持 UNVERIFIABLE。"
        ),
    },
    # ── Task 43 追加（只加不动；本条起至 tuple 结束是 Task 43 的字节区间）────────
    {
        "contract_id": "g7.soe_subsidiary_disclosure",
        "provider_module": "app.services.workpaper_sync.pilot_g7_two_level_dynamic",
        "delivered_by_task": "43",
        "pilot_class": "g7_two_level_dynamic",
        "entry_id": "xlsx/gt-g7-long-term-equity-main",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G7 长期股权投资.xlsx",
        "adapter_registered": True,
        "reason": (
            "Task 43 冻结 g7_two_level_dynamic pilot 的 entry。`assess_pilot_classes()` 实测 "
            "**3 个**候选（gt-g7-equity-method / gt-g7-equity-subsidiary / "
            "gt-g7-long-term-equity-main）、bidirectional 0 个；收敛到一个的决定性事实是 "
            "**matcher 域独占**：前两个共用 `wp_code_patterns == [\"G7E\"]`，以它为 "
            "`EntryMatcher.wp_codes` 的 adapter 会触发 RG-3 `MatcherOverlapError` / "
            "`AmbiguousAdapterError`，而 `G7L` 只属本 entry。"
            "逐 sheet 读权威模板的 22 张 sheet 后只声明受管 sheet `附注披露信息（国企）`，"
            "并在其上声明两张表：① 静态块 `minority_financials`（源「2、主要财务信息」，"
            "两级表头 62/63 行 —— 行 62 的 5 个**空白**横向合并就是源模板自己的动态列占位，"
            "行 63 的 10 个叶子只有 2 个不同 label 各重复 5 次；10 metric × 10 动态列 = 100 "
            "个字段，`C64:L73` 逐格实测全空 ⇒ 全部 editable）；② 动态行表 "
            "`former_subsidiary_basic`（源「（1）原子公司的基本情况」，5 行骨架、A 列字面量 "
            "1..5 ⇒ auto_source、B..G 逐格跨 sheet 公式 ⇒ formula + formula_mask B79:G83、"
            "footer 取 A85 真实文本）。"
            "本 pilot 是四类里**唯一**真有 `{slot}_{seq}` 动态列的那个：键由 Task 36 的 "
            "`dynamic_column_stable_keys(slot=table_key, count=…)` 生成（签名里拿不到 label），"
            "列数由 `dynamic_column_keys_for_entities()` 从实体列表推出、不写死；"
            "键→列的实测绑定由 `dynamic_column_binding_for()` 产出。"
            "上市侧同构的 5 张动态列矩阵因数据格在源模板里全是公式 ⇒ 零 editable 字段、"
            "merge 家族两条 required scenario 结构性不可满足，故未选用，登记为 "
            "`pilot_g7_two_level_dynamic.UPSTREAM_DEBT_TWO_LEVEL_MATRIX_MODE_IS_PER_COLUMN`。"
            "`adapter_registered=True`：2026-09-07 实测真库 `register_from_manifest()` 已注册"
            "`g7.soe_subsidiary_disclosure` —— 该 entry 的 manifest 已由 reviewed overlay "
            "裁决为 `bidirectional`（`adapter_id` 同步写回），approved bundle / current "
            "published representation / entry_state 三件供给齐备，观测器真读出 frozen "
            "identity（含 observed_dynamic_columns 由工作簿物理列跨度 + merge 铺开的 label "
            "现读）后走完 `build_excel_adapter` → `registry.register()`（RG-1~RG-19 一条不少）。"
            "顺序门仍然成立且未被绕过：capability 裁决是 finalize **之后**的 reviewed overlay "
            "动作（Task 36 / Task 77 的 finalize gate 已产出 published representation）。"
            "🔴 「注册成功」≠「pilot 已验收」：真实 OO required scenarios 未按 Task 70 "
            "刷新，evidence 保持 UNVERIFIABLE。"
        ),
    },
    # ── G5-1 追加（Phase 5 首个 canary，harness 无关的独立 entry 双向路径）─────────
    {
        "contract_id": "d1.notes_receivable_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d1_notes_receivable",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_notes_receivable",
        "entry_id": "xlsx/gt-d1-notes-receivable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D1 应收票据.xlsx",
        "adapter_registered": True,
        "reason": (
            "G5-1 Phase 5 首个 canary。**不是第五个 pilot**：四个 pilot 是 "
            "`pilot_harness.PilotClass` 封闭枚举的代表，`xlsx/gt-d1-notes-receivable` 的 "
            "entry_id 不含 d2/h1/g7 会被归进 catch-all `simple_checklist`（B60 已占），故本 "
            "provider 的选型守卫 `assert_entry_selectable` 直接在真 manifest + 真 finder 上核"
            "四条事实（entry 存在 / independent=True / profile==D2/B60 同型 "
            "`xlsx.editable.shared.single.room_service_wired.v1` / wp_code==['D1N']）+ 零回退"
            "（D1N find/any 均 None、父码 D1 落权威模板），**不**调 `assess_pilot_classes()`。"
            "逐 sheet 读权威模板 `D/D1 应收票据.xlsx`（21 张 sheet）后只声明受管 sheet "
            "`原值明细表（按客户）D1-3`：单级表头行 10（15 列 A..O）、数据区 11..20、"
            "G/J/L/O 四列逐行公式 `=D+E+F` / `=D+H-I` / `=J+K` / `=L+M+N`（openpyxl 逐格实测）、"
            "A21 合计 footer。HTML store = `checklist_responses.item_id='D1-cust-rows'`"
            "（前端 useD1DetailCustomer.ts 的 CustomerRow 整行数组 serializeRows()），按 "
            "stable field + rowId 拆成 15 字段/行，禁止把整 JSON 当一个字段。"
            "`adapter_registered=False` 是**顺序**：Task 4 把 overlay 裁决为 bidirectional 并"
            "重生 manifest（当前 capability=single_onlyoffice）、发布链产出 approved bundle + "
            "current published representation 之后方可注册；未就绪时 `attach_adapters` 返回空"
            "元组且一次库都不读，契约孤儿由 `RegistryReport.contract_files_without_adapter` "
            "持续可见。"
        ),
    },
    # ── G5-1 追加（Phase 5 第二个 canary：D7 合同负债，两级表头 + 账龄组）─────────
    {
        "contract_id": "d7.contract_liabilities_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d7_contract_liabilities",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_contract_liabilities",
        "entry_id": "xlsx/gt-d7-contract-liabilities",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D7 合同负债.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第二个 canary（同 D1 的 harness 无关独立 entry 路径，非第五 pilot）。"
            "选型守卫 assert_entry_selectable 直接核四条 manifest 事实（entry 存在 / "
            "independent=True / profile==D2/B60 同型 / wp_code==['D7C']）+ 零回退（D7C find/any "
            "均 None、父码 D7 落权威模板），不调 assess_pilot_classes()。逐 sheet 读权威模板 "
            "D/D7 合同负债.xlsx 后只声明受管 sheet 明细表D7-2：两级表头行 8 / 行 9（账龄子标题），"
            "27 列 A-AA，数据区 10-22，I/P/R/U 四列逐行公式 =F+G+H / =F-N+O（贷方科目）/ =P+Q / "
            "=R+S+T，A23 合计 footer；19 标量 + 两个账龄组各 4 段（THREE_YEAR），字段键与前端 "
            "useD7Detail.DetailRow 锁死。HTML store = checklist_responses.item_id='D7-2-rows'，"
            "账龄 nested keyed。wp_code 裁决=['D7']（**不是 D7C 幻影码 / D7-2 名义码**）：查真库"
            "确认 store 载荷落 wp_code=D7（project 0ec33ac9 / wp 6f23dcce / 669B）。"
            "`adapter_registered=False` 是顺序：overlay 裁决 bidirectional + 重生 manifest + 发布链"
            "产出 approved bundle + current published representation 之后方可注册。"
        ),
    },
    # ── G5-1 追加（Phase 5 第三个 canary：D3 预收账款，两级表头 + 账龄组）─────────
    {
        "contract_id": "d3.prepaid_receipts_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d3_prepaid_receipts",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_prepaid_receipts",
        "entry_id": "xlsx/gt-d3-prepaid-accounts",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D3 预收账款.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第三个 canary（同 D1/D7 的 harness 无关独立 entry 路径）。选型守卫 "
            "assert_entry_selectable 核四条 manifest 事实（entry 存在 / independent=True / "
            "profile==room_service_wired.v1 / wp_code==['D3P']）+ 零回退（D3P find/any 均 None、"
            "父码 D3 落净化后权威模板）。逐 sheet 读净化后权威模板 D/D3 预收账款.xlsx（外链净化后 "
            "sha256 699a9be0）后只声明受管 sheet 预收账款明细表D3-2：两级表头行 10 / 行 11（账龄"
            "子标题），27 列 A-AA，数据区 12-23，H/O/Q/T 四列逐行公式 =E+F+G / =E+N-M（贷方科目）/ "
            "=O+P / =Q+R+S，A24「合计」footer（纯两字无空格，非 D7 的三空格）；19 标量 + 两个账龄组"
            "各 4 段（THREE_YEAR），字段键与前端 useD3Detail.DetailRow 锁死。HTML store = "
            "checklist_responses.item_id='D3-det-rows'，账龄 nested keyed。wp_code 裁决=['D3']"
            "（**不是 D3P 幻影码 / D3-2 名义码**）：D3-det-rows 全库 0 行（同 H1 空表单），但 sibling "
            "D3-vc-current-rows 载荷落 wp_code=D3（1 行 3601B）已证 D3 store 落点=D3，且 D3 wp 未删除"
            "有 file_path。`adapter_registered=False`：**与真实库对齐**——真库 "
            "`register_from_manifest()` 当前只注册 {d2,d4,g7,h1}（有真实供给的 entry），"
            "D3-det-rows / D3-vc 全库 0 行、无 current published representation ⇒ 未注册成功。"
            "原登记乐观标 True 与现实脱钩（Property 49 实测捕获）；发布链真正产出 representation 后再回填 True。"
        ),
    },
    # ── G5-1 追加（Phase 5 第四个 canary：D6 合同资产，两级表头 + 账龄组，账龄 FLAT 键）─────
    {
        "contract_id": "d6.contract_assets_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d6_contract_assets",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_contract_assets",
        "entry_id": "xlsx/gt-d6-contract-assets",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D6 合同资产.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第四个 canary（同 D1/D3/D7 的 harness 无关独立 entry 路径）。选型守卫核四条"
            "manifest 事实（entry 存在 / independent=True / profile==room_service_wired.v1 / "
            "wp_code==['D6C']）+ 零回退（D6C find/any 均 None、父码 D6 落净化后权威模板）。逐 sheet 读"
            "净化后权威模板 D/D6 合同资产.xlsx（外链净化后 sha256 88125e42）后只声明受管 sheet "
            "明细表D6-2：两级表头行 12 / 行 13（账龄子标题），32 列 A-AF（受管 A-AD），数据区 14-25，"
            "J/Q/T 三列逐行公式 =G+H+I / =G+O-P（借方科目）/ =Q+R+S，A26「合   计」footer（3 半角空格，"
            "同 D7）；22 标量 + 两个账龄组各 4 段（K-N 期初 / U-X 期末，**FLAT 键 agePrior*/ageEnd***，"
            "非 D3/D7 的 nested），字段键与前端 useD6Detail.DetailRow 锁死。HTML store = "
            "checklist_responses.item_id='D6-2-rows'。wp_code 裁决=['D6']（**不是 D6C 幻影码 / D6-2 "
            "名义码**）：D6-2-rows 全库 0 行（同 H1/D3 空表单），D6 wp 未删除有 file_path。"
            "`adapter_registered=False`：**与真实库对齐**——真库 `register_from_manifest()` 当前只注册 "
            "{d2,d4,g7,h1}，D6-2-rows 0 行、无 current published representation ⇒ 未注册成功。"
            "原乐观标 True 与现实脱钩（Property 49 捕获）；发布链产出 representation 后再回填 True。"
        ),
    },
    # ── G5-1 追加（Phase 5 第五个 canary：D5 应收款项融资，两级表头无账龄 FVOCI）─────
    {
        "contract_id": "d5.receivables_financing_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d5_receivables_financing",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_receivables_financing",
        "entry_id": "xlsx/gt-d5-receivables-financing",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D5 应收款项融资.xlsx",
        "adapter_registered": False,
        "reason": (
            "G5-1 Phase 5 第五个 canary（同 D1/D3/D6/D7 的 harness 无关独立 entry 路径）。选型守卫核"
            "四条 manifest 事实（entry 存在 / independent=True / profile==room_service_wired.v1 / "
            "wp_code==['D5R']）+ 零回退（D5R find/any 均 None、父码 D5 落净化后权威模板）。逐 sheet 读"
            "净化后权威模板 D/D5 应收款项融资.xlsx（外链净化后 sha256 92c5f7f2）后只声明受管 sheet "
            "应收款项融资明细表D5-2：两级表头行 10（组标题 期初数 C:G / 本期变动 H:I / 期末数 J:P）/ "
            "行 11（子标题），17 列 A-Q，数据区 12-16，F/J/L/O 四列逐行公式 =C+E+D / =C+H-I / =J+K / "
            "=J+N+M，A17「合计」footer（纯两字，同 D3）；**FVOCI 无账龄组**（最简 canary，group 下"
            "每个子列是不同语义字段），字段键与前端 useD5Detail.DetailRow 锁死（postRealized/eclStage "
            "store-only 不入）。HTML store = checklist_responses.item_id='D5-2-rows'。wp_code 裁决=['D5']"
            "（**不是 D5R 幻影码 / D5-2 名义码**）：D5-2-rows 全库 0 行（同 H1/D3/D6 空表单），D5 wp 未删除"
            "有 file_path。`adapter_registered=False`：**与真实库对齐**——真库 `register_from_manifest()` "
            "当前只注册 {d2,d4,g7,h1}，D5-2-rows 0 行、无 current published representation ⇒ 未注册成功。"
            "原乐观标 True 与现实脱钩（Property 49 捕获）；发布链产出 representation 后再回填 True。"
        ),
    },
    # ── G5-1 D4 营业收入（位置数组；契约含 D4-2/D4-3/D4-5 sibling sheets）─────
    {
        "contract_id": "d4.revenue_detail",
        "provider_module": "app.services.workpaper_sync.phase5_d4_revenue_detail",
        "delivered_by_task": "G5-1",
        "pilot_class": "phase5_revenue_detail",
        "entry_id": "xlsx/gt-d4-operating-revenue",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "D/D4 收入底稿.xlsx",
        "adapter_registered": True,
        "reason": (
            "G5-1 Phase 5 第六个 canary（第五种行形态：位置数组）。选型守卫 assert_entry_selectable "
            "核四条 manifest 事实（entry 存在 / independent=True / profile==room_service_wired.v1 / "
            "wp_code==['D4O']）+ 零回退（D4O find/any 均 None、父码 D4 落净化后权威模板）+ "
            "mapping_digest 哨兵。权威模板 D/D4 收入底稿.xlsx（sha256 b8fb92d4…）；受管 sheets="
            "d42-managed / d43-managed / d45-managed（D4-5 政策检查：分组紧凑表 + 经营模式 B11–B16；"
            "宿主 D4TabPolicyCheck 独立，不进 isD4DetailSheet）。HTML store 含 D4-2-rows / D4-3-rows / "
            "D4-5-policy-groups + D4-5-biz-*。wp_code 裁决=['D4']（真载荷落点）。"
            "D4-9 重要客户结构分析作为 sibling sheet（d49-managed，同 entry / 同 adapter）"
            "并入本 entry —— 与 D4-1/2/3/5/15/16/21~29/35 同架构（overlay 规则：D4 子表 mount "
            "归父 entry，不独立计数）。"
        ),
    },
    # ── E1 货币资金 canary（spec: e1-sync-coverage-and-first-canary · Task 10）─────
    {
        "contract_id": "e1.monetary_fund_detail",
        "provider_module": "app.services.workpaper_sync.phase5_e1_monetary_fund",
        "delivered_by_task": "E1-canary",
        "pilot_class": "phase5_monetary_fund",
        "entry_id": "xlsx/gt-e1-monetary-fund",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx",
        "adapter_registered": False,
        "reason": (
            "E1 canary（spec e1-sync-coverage-and-first-canary）。选型守卫 assert_entry_selectable "
            "核四条 manifest 事实（entry 存在 / independent=True / "
            "profile==xlsx.editable.shared.single.room_service_wired.v1 / wp_code==['E1']）。"
            "权威模板 E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx "
            "（sha256 8317e2ba…）；受管 sheets= e12-managed(canary) / e14-managed / "
            "e16-managed / e17-managed / e18-managed / e19-managed / e110-managed / "
            "e111-managed(static_region)。HTML store 含 E1-cash-detail-rows / "
            "E1-digital-rows / E1-reconciliation-rows / E1-cash-count-{rmb|fx|cert}-rows / "
            "E1-account-list-rows + static E1-account-commit。行身份键统一为 `id`"
            "（不是 D 类的 rowId）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7 卡在同一平台级缺口"
            "（umbrella BP-61-1：published representation 三表近空，186 个 planned "
            "entry 一个都注册不上），供给就绪后真栈注册。"
        ),
    },
    # ── F1 预付账款 canary（spec: f1-sync-coverage-and-first-canary · Task 9）─────
    {
        "contract_id": "f1.prepayment_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f1_prepayment",
        "delivered_by_task": "F1-canary",
        "pilot_class": "phase5_prepayment",
        "entry_id": "xlsx/gt-f1-prepayment",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F1 预付账款.xlsx",
        "adapter_registered": False,
        "reason": (
            "F1 canary（spec f1-sync-coverage-and-first-canary）。选型守卫 "
            "assert_entry_selectable 核四条 manifest 事实（entry 存在 / "
            "independent=True / profile==room_service_wired.v1 / "
            "wp_code==['F1P']）+ 零回退（F1P find/any 均 None、父码 F1 落权威模板）。"
            "权威模板 F/F1 预付账款.xlsx（sha256 f30055cb…）；canary 受管 sheet = "
            "关联方及交易检查表F1-6（单级表头 / 3 行 / F/H 两列公式 / UUID N 列）。"
            "HTML store = checklist_responses.item_id='F1-rp-rows'（前端 "
            "useF1RelatedParty.ts 的 RelatedPartyRow 行数组）。"
            "wp_code 裁决=['F1']（store 载荷 F1-det-rows 46,295 B 落在 "
            "wp_code=F1 上；F1P 是 CamelCase 幻影码 finder 零命中）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1 卡在同一平台级缺口"
            "（umbrella BP-61-1），供给就绪后真栈注册。"
        ),
    },
    # ── F2 main（spec: f2-sync-coverage-four-entry-lanes · Task 7）──────
    {
        "contract_id": "f2.inventory_main",
        "provider_module": "app.services.workpaper_sync.phase5_f2_inventory_main",
        "delivered_by_task": "F2-main-canary",
        "pilot_class": "phase5_f2_inventory_main",
        "entry_id": "xlsx/gt-f2-inventory-main",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": (
            "F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx"
        ),
        "adapter_registered": False,
        "reason": (
            "F2 main lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "三个 F2I entry 共用幻影码，matcher 域靠 sheet_keys 互斥解 RG-3（F2-H1）。"
            "canary 受管 sheet = 四、自制半成品明细表F2-6（F2-H4）。"
            "权威模板 F/F2-1至F2-14（sha256 9e57efd2…）；"
            "HTML store = checklist_responses.item_id='F2-6-rows'。"
            "wp_code 裁决=['F2']（35 键全在父码 F2）。"
            "`adapter_registered=False`：与 D/E/F1 卡在同一平台级缺口"
            "（umbrella BP-61-1），供给就绪后真栈注册。"
        ),
    },
    # ── F2 stocktake（spec: f2-sync-coverage-four-entry-lanes · Task 14）──────
    {
        "contract_id": "f2.stocktake_bundle",
        "provider_module": "app.services.workpaper_sync.phase5_f2_stocktake_bundle",
        "delivered_by_task": "F2-stocktake-canary",
        "pilot_class": "phase5_f2_stocktake_bundle",
        "entry_id": "xlsx/gt-f2-stocktake-bundle",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": (
            "F/F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx"
        ),
        "adapter_registered": False,
        "reason": (
            "F2 stocktake lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "F2S 独占幻影码，无 RG-3 冲突。canary = F2-25 双区。"
            "权威模板 F/F2-21至F2-26（sha256 bdfdcf8a…）。"
            "wp_code 裁决=['F2']。"
            "`adapter_registered=False`：BP-61-1。"
        ),
    },
    # ── F2 valuation（spec: f2-sync-coverage-four-entry-lanes · Task 18）──────
    {
        "contract_id": "f2.inventory_valuation",
        "provider_module": "app.services.workpaper_sync.phase5_f2_inventory_valuation",
        "delivered_by_task": "F2-valuation-canary",
        "pilot_class": "phase5_f2_inventory_valuation",
        "entry_id": "xlsx/gt-f2-inventory-valuation",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": (
            "F/F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx"
        ),
        "adapter_registered": False,
        "reason": (
            "F2 valuation lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "F2I + sheet_keys 解 RG-3。canary = F2-48 dict 子数组。"
            "F2-47 卡 FC-10（百分数换算），灰度关待 Task 20。"
            "权威模板 F/F2-47至F2-49（sha256 bab0abc0…）。"
            "`adapter_registered=False`：BP-61-1。"
        ),
    },
    # ── F2 special（spec: f2-sync-coverage-four-entry-lanes · Task 22）──────
    {
        "contract_id": "f2.inventory_special",
        "provider_module": "app.services.workpaper_sync.phase5_f2_inventory_special",
        "delivered_by_task": "F2-special-canary",
        "pilot_class": "phase5_f2_inventory_special",
        "entry_id": "xlsx/gt-f2-inventory-special",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F2-55至F2-58 合同履约成本.xlsx",
        "adapter_registered": False,
        "reason": (
            "F2 special lane canary（spec f2-sync-coverage-four-entry-lanes）。"
            "F2I + sheet_keys 解 RG-3。canary = F2-57 dict 子数组。"
            "权威模板 F/F2-55至F2-58（sha256 b9ea2481…）。"
            "`adapter_registered=False`：BP-61-1。"
        ),
    },
    # ── F3 canary（spec: f3-sync-coverage-and-first-canary · Task 9）─────────
    {
        "contract_id": "f3.notes_payable_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f3_notes_payable",
        "delivered_by_task": "F3-canary",
        "pilot_class": "phase5_notes_payable",
        "entry_id": "xlsx/gt-f3-notes-payable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F3 应付票据.xlsx",
        "adapter_registered": False,
        "reason": (
            "F3 canary（spec f3-sync-coverage-and-first-canary）。选型守卫 "
            "assert_entry_selectable 照 D3 同签名（resolution 必填 / 无关闭开关）并对**真 "
            "manifest 真调**（wp_code_patterns==['F3N'] 幻影码）+ 零回退（F3N 在 wp_index 与 "
            "wp_templates/_index.json 均 0 命中，父码 F3 落权威模板）。"
            "权威模板 F/F3 应付票据.xlsx（sha256 06de707b…，79,616 B，12 sheets）；"
            "canary 受管 sheet = 逾期票据检查F3-5（两级表头 R5/R6 / 数据 R7-21 / "
            "footer R22「合计」纯两字 / UUID 列 P / **数据区零公式** —— 10 个公式全在页眉与 footer）。"
            "HTML store = checklist_responses.item_id='F3-5-rows'（真库 675 B / 2 行全带 rowId，"
            "F3 唯一有载荷的键；🔴 实测是 2 行**空白行**，有意义数值的 roundtrip 仍需 seed）。"
            "🔴 契约装配走框架层 spec_to_contract_sheet_payload（不手写 table payload）—— "
            "F1 的手写版缺 anchor/header_rows/row_identity.json_pointer 等必填字段，parse_contract 直接抛。"
            "I 列（票面利率）命中 FC-10（模板 0.00% × 前端存百分数）⇒ 暂不进 field_specs，"
            "待 value_type=percent_points 换算落地（merge.py 现无任何 percent 换算）。"
            "wp_code 裁决=['F3']（wp_index 4 行）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1/F2 卡在同一平台级缺口"
            "（umbrella BP-61-1：slice 实测 published_representation=null），供给就绪后真栈注册。"
        ),
    },
    # ── F4 canary（spec: f4-sync-coverage-and-first-canary · Task 8）─────────
    {
        "contract_id": "f4.accounts_payable_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f4_accounts_payable",
        "delivered_by_task": "F4-canary",
        "pilot_class": "phase5_accounts_payable",
        "entry_id": "xlsx/gt-f4-accounts-payable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F4 应付账款.xlsx",
        "adapter_registered": False,
        "reason": (
            "F4 canary（spec f4-sync-coverage-and-first-canary）。"
            "🔴 **全 F 循环唯一「幻影码撞真码」**：manifest 的 wp_code_patterns==['F4A'] 与 "
            "wp_code_overrides.json 的程序表路由码 F4A 字面相同（裁决 F4-H2：两侧都不改）。"
            "四条隔离事实实测：wp_templates/_index.json 无 F4A（F 循环只有 F0~F5 六个真码）· "
            "wp_index 无 F4A（真码 F4 有 5 行）· provisioner 用裁决真码 ['F4'] · "
            "assert_no_implicit_template_fallback('F4A') 通过 ⇒ 幻影码只存在于路由表一处，"
            "误当业务码用时得到空集而不是命中程序表。"
            "权威模板 F/F4 应付账款.xlsx（sha256 e20e6272…，108,329 B，15 sheets）；"
            "canary 受管 sheet = 关联方及交易检查表F4-6（单级表头 R6 / 数据 R7-11 / "
            "footer R12「合计」/ UUID 列 M / formula_columns=('F',)）。"
            "🔴 公式 F=C+E-D（**负债类**：期初+贷方−借方）与 F1-6 的 F=C+D-E（资产类）互为镜像 —— "
            "同型不等于同式，逐格实测所得（FC-4）。"
            "HTML store = checklist_responses.item_id='F4-6-rows'；真库 F4-2-rows 3,485 B / "
            "4 行全带 rowId + F4-7-estimated-inbound-rows 1,211 B / 2 行（同一底稿）。"
            "FC-10 **不命中**（F4-6 逐格实测零百分比格式格）—— 四个 F spec 里唯一无该阻塞的。"
            "顺带发现并登记的模板缺陷：B8:B11 的数据验证 formula1=$N$7:$N$14 而 N 列全空"
            "（悬空引用，仅 B7 的 DV 指向真实枚举源 $B$18:$B$25）—— 不改模板字节。"
            "`adapter_registered=False`：同 BP-61-1。"
        ),
    },
    # ── F5 canary（spec: f5-sync-coverage-and-first-canary · Task 9）─────────
    {
        "contract_id": "f5.cost_of_sales_detail",
        "provider_module": "app.services.workpaper_sync.phase5_f5_cost_of_sales",
        "delivered_by_task": "F5-canary",
        "pilot_class": "phase5_cost_of_sales",
        "entry_id": "xlsx/gt-f5-cost-of-sales",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "F/F5 营业成本.xlsx",
        "adapter_registered": False,
        "reason": (
            "F5 canary（spec f5-sync-coverage-and-first-canary）。选型守卫对真 manifest 真调"
            "（wp_code_patterns==['F5C']）+ 零回退（F5C 在 wp_index 与 _index.json 均 0 命中）。"
            "权威模板 F/F5 营业成本.xlsx（sha256 417e5ae7…，187,721 B，11 sheets）；"
            "canary 受管 sheet = 重大调整核查表F5-8（两级表头 R12/R13 / 数据 R14-29 / "
            "**无 footer 合计** ⇒ 锚行 R30 + footer_carries_total_formula=False，"
            "🔴 marker 逐字是「三、审计说明：」**带全角冒号**（spec Task 8 漏了冒号，"
            "assert_footer_anchor_stable 逐字匹配会失败）/ UUID 列 I —— "
            "🔴 **超出模板 max_column(H)** ⇒ instrumentation 需扩列）。"
            "🔴 行身份是 **`id`** 不是 rowId（F5-2/3/5/8 四张皆如此，与 D 类惯例相反）。"
            "G 列不单独声明 —— 被 F 列的 F{r}:G{r} 逐行合并吞掉（表头区 F12:G13 跨两行两列）。"
            "🔴 **真库完全无载荷**（全部 F5-% 键 0 行，F 循环唯一）⇒ wp_code 裁决条目的 "
            "max_payload_bytes 如实记 0（不伪造），验收前必须先 seed（裁决 F5-H7 / Property 8），"
            "否则空表往返会被判 store_mirrored 假绿。"
            "BP-7 三处下标派生行身份（useF5MonthlyDetail:133 / useF5OtherCost:146 / "
            "useF5Comparison:128）是 slice 明令的双向硬前置，已由 f5RowIdentity.ts 单点收敛并立即回写。"
            "HTML-only 登记：F5-1 主营区（七列全是引 F5-2 的公式、零 editable ⇒ 受管会与 F5-2 双源，"
            "裁决 F5-H3）· F5-4（FC-6 hub）· F5-6（244 公式三块，后置另立 spec）。"
            "`adapter_registered=False`：同 BP-61-1。"
        ),
    },
    # ── G2 canary（spec: g-cycle-sync-foundation-and-first-canary · Task 14）──
    {
        "contract_id": "g2.interest_receivable_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_g2_interest_receivable"
        ),
        "delivered_by_task": "G2-canary",
        "pilot_class": "phase5_interest_receivable",
        "entry_id": "xlsx/gt-g2-interest-receivable",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G2 应收利息.xlsx",
        "adapter_registered": False,
        "reason": (
            "G 循环**首条** entry（spec g-cycle-sync-foundation-and-first-canary，"
            "canary 裁决 GF-H1）。G 循环起点是 E1 级：17 条 entry 零 provider / 零契约 / "
            "零 published representation，本条是第一个。"
            "assert_entry_selectable 照 D3 同签名（resolution 必填 / 无关闭开关）并对"
            "**真 manifest 真调**（wp_code_patterns==['G2I'] 幻影码）+ 零回退"
            "（G2I 在 wp_index 实测 0 命中，真码 G2 有 4 行活行）。"
            "权威模板 G/G2 应收利息.xlsx（sha256 c7563e85…，99,479 B，12 sheets）；"
            "canary 受管 sheet = 明细表G2-2（**单级**表头 R9 / 数据 R10-15 / "
            "footer R16「合计」/ 公式列 E·H·J 共 18 格：E=C+D · H=C+F-G · J=H+I / "
            "有效内容列 13 即 A-M、N·O·P 全空 ⇒ UUID 列 N / 0 个 definedName）。"
            "🔴 **范式裁决 GF-H3**：走 `phase5_*` 声明式范式，**不照** 同循环已迁移的 G7 "
            "（G7 是 `pilot_g7_two_level_dynamic` 的 `pilot_*` 范式，形态早于行表引擎）；"
            "唯一复用 G7 的是 `oo_crash_neutralization_fn`（范式无关的 per-file 缓解件）。"
            "🔴 **GC-2**：G2 册裸 IF **21 格**（审定表G2-1 19 + 应收利息坏账准备测算G2-7 2，"
            "受管表本身零命中）⇒ 仍按 per-file 保守策略挂中性化。"
            "（spec RG-4 表记的 40 是 `findall` 出现次数不是格数，权威口径见 evidence/task0。）"
            "🔴 **GC-5**：HTML store = checklist_responses.item_id='G2-2-detail-rows'，"
            "payload 落 **remark**（`conclusion` 是字面 null 占位 —— FD-1 的 null 占位"
            "子形态，**全 slice 仅 G2 一条**）。判 mode 必须先剔占位，否则会被误判 dual_write。"
            "真库实测 remark **475 B** / conclusion 0 B ⇒ 裁决 GF-H2：**不 seed**，"
            "但验收判据须断言 roundtrip 行数 > 0 且来自真库。"
            "🔴 契约装配走框架层 `spec_to_contract_sheet_payload`（同 F3~F5 的做法）—— "
            "本轮实测 F1 的手写版缺 anchor/header_rows/row_identity.json_pointer，"
            "`parse_contract` 直接抛、`assert_contract_file_matches_source` 从来过不了；"
            "G2 的生成器在写盘前先跑 parse_contract，形态错就不落盘。"
            "BP-10 的 G2 份额已收敛：`G2-2-detail-rows` 原有 **5 处**声明"
            "（g2CrossHelpers / useG2Detail / useG2DisclosureListed / useG2DisclosureSoe / "
            "useG2InterestCalc）⇒ 新建 `g2StorageContract.G2_ITEM_IDS` 单一真源 + 派生别名"
            "（范式照 BP-10 正面样本 g6CrossHelpers）。"
            "wp_code 裁决=['G2']（真库 G2-2-detail-rows 载荷落 wp_code=G2）。"
            "FC-9 红线：G2 已接显式发布门（科目 1132 余额口径，useG2Adjudication.publishToTb=3），"
            "本 provider 对 trial_balance 写次数为 0。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5 卡在同一平台级缺口"
            "（umbrella BP-61-1 = G slice 的 BP-1~BP-3：instrumentation candidate / "
            "人工审核契约 / approved bundle 三缺），供给就绪后真栈注册。"
        ),
    },
    # ── G9（spec: g-cycle-single-region-detail-lanes · Task 8 / C-5）──────────
    {
        "contract_id": "g9.other_noncurrent_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_g9_other_noncurrent"
        ),
        "delivered_by_task": "G1R-Task8",
        "pilot_class": "phase5_other_noncurrent_financial",
        "entry_id": "xlsx/gt-g9-other-noncurrent-financial",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G9 其他非流动金融资产.xlsx",
        "adapter_registered": False,
        "reason": (
            "spec `g-cycle-single-region-detail-lanes` 九条中的**首条**（lane 顺序由易到难 "
            "G9→G10→G8→G14→G11→G13→G12→G3→G1）。范式照 G2 的 `phase5_*`，不照 G7 的 "
            "`pilot_*`；唯一复用 G7 的是 `oo_crash_neutralization_fn`。"
            "权威模板 G/G9 其他非流动金融资产.xlsx（sha256 264322c0…，88,636 B，10 sheets）；"
            "受管 sheet = 明细表G9-2（**两级**表头 R9 组 / R10 叶子 / 有效内容列 28 即 A-AB / "
            "0 个 definedName / 12 个公式列 E·H·I·J·L·P·Q·R·U·V·W·Y 共 156 格 / "
            "合计 R30 是**枚举相加** =SUM(C17,C24,C29) 非 SUM 区间）。"
            "🔴 **全库首个「一个 store 键 × 三个受管区」**：三区 R12-16 / R19-23 / R26-28 "
            "（区标题行 R11·R18·R25 与小计行 R17·R24·R29 均不受管）的行都存在**同一个** "
            "`G9-detail-rows` 数组里，区归属由行的 `section` 字段表达。既有多区范式 "
            "`phase5_d3_04_analysis` 是「一区一个 store_item_id」（要求前端拆键）—— 这里"
            "**不拆**：该键有真库载荷 605 B、被 8 个跨表消费方读取、且是 BP-10 登记键，"
            "拆键波及面远大于在引擎加一层可选过滤。改为引擎 `row_section_field='section'` + "
            "逐段 `row_section_value`（`iter_store_rows` 按它过滤、"
            "`merge_projection_into_store_rows` 给新增行补它，两处成对）。"
            "⇒ provider 的三个 store 门面按「遍历三段」组合：投影合并三段、回写顺序穿线、"
            "iter 串联三段；`html_store.item_ids` 仍只有 **1** 条（不是 3）。"
            "🔴 `template_id` 逐区不同（G92R1/R2/R3）而 `sheet_key` 共享（g902-managed）："
            "instrumentation 的 definedName 按 template_id 命名（实测抛「多 sheet "
            "instrumentation 的 template_id 必须唯一」），而契约层同 excel_name 两个 "
            "sheet_key 会产出重复 sheet 条目。先例 `phase5_d3_04_analysis`（D34DEBIT/D34CREDIT）。"
            "🔴 **前端根治在先**（用户拍板选项 C）：`useG9Detail.ts` 原 30 列里 15 列与权威模板"
            "不符 —— `ociChange`/`ociCumulative`/`impairmentLoss`/`impairmentProvision` 属 "
            "FVOCI 口径（G9 模板编制说明 A38-A43 五类全 **FVTPL**，CAS22 下不确认 OCI 与减值）、"
            "`fairValueLevel`/`valuationMethod` 属 G9-4/G9-5 两张表、另 6 列模板没有。已按模板"
            "列序 A..AB 重写为 28 字段「三分量 × 四阶段」模型（成本 + 累计公允价值变动 = 公允"
            "价值；未审→账项调整→审定→重分类报表）并带迁移函数与丢弃计数。"
            "🔴 顺带修掉 `g9FvCrossHelpers.pushG9FvToDetail`（G9-4 往 G9-2 回写那三列，"
            "层次与方向都错 —— G9-2 无公允价值层次列）。"
            "🔴 **GC-2**：G9 册裸 IF **42 格**（全在 审定表G9-1，受管表 明细表G9-2 零命中）"
            "⇒ 仍按 per-file 保守策略挂中性化（点同册任一 sheet 的在线编辑都会触发整册加载）。"
            "🔴 **FD-1**：HTML store = checklist_responses.item_id='G9-detail-rows'，"
            "payload 落 **remark**（真库实证 remark 605 B / conclusion 0 B）⇒ 不 seed，"
            "验收判据断言 roundtrip 行数 > 0 且来自真库。"
            "wp_code 裁决：manifest 幻影码 ['G9O']（matcher 域），真码 **G9**（载荷所在）。"
            "FC-9 红线：G9 已接显式发布门（useG9Adjudication.publishToTb），"
            "本 provider 对 trial_balance 写次数为 0；审定表 审定表G9-1 归后置 spec "
            "`g-cycle-adjudication-sheets-coverage`（GF-H5）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2 卡在同一平台级缺口"
            "（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册。"
        ),
    },
    # ── G10（spec: g-cycle-single-region-detail-lanes · Task 9 / C-7）─────────
    {
        "contract_id": "g10.trading_liabilities_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_g10_trading_liabilities"
        ),
        "delivered_by_task": "G1R-Task9",
        "pilot_class": "phase5_trading_financial_liabilities",
        "entry_id": "xlsx/gt-g10-trading-financial-liabilities",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "G/G10 交易性金融负债.xlsx",
        "adapter_registered": False,
        "reason": (
            "spec `g-cycle-single-region-detail-lanes` 九条中的**第二条**。范式照 G2/G9 的 "
            "`phase5_*`；与首条 G9 的结构差别只在受管区数量 —— G10 是**单区** ⇒ 三个 store "
            "门面各自 ≤3 行薄转发框架层引擎，不需要 G9 那样的「遍历三段」伴生模块。"
            "权威模板 G/G10 交易性金融负债.xlsx（sha256 3afd5131…，99,458 B，12 sheets）；"
            "受管 sheet = 明细表G10-2（**两级**表头 R9 组 / R10 叶子 / 单区 R11-R20 / "
            "footer R21 逐列 =SUM(x11:x20) 且 **O21 例外**为 =M21+N21 / 6 个公式列 "
            "E·G·K·L·M·O 共 60 格 / 0 个 definedName）。"
            "🔴 **UUID 列取 T 不是 max_column+1**：`max_column=24` 含空列，有效内容列只有 "
            "**19**（A..S，T..X 全空）⇒ 判据 GC-3 的口径是「有效列右移一列」。"
            "🔴 **前端根治在先**（用户拍板选项 C）：`useG10Detail.ts` 原 35 列里 16 列与权威"
            "模板不符 —— OCI/减值四列属 FVOCI 口径（CAS22 下 FVTPL 不确认 OCI 与减值）、"
            "`fairValueLevel`/`valuationMethod` 属 G10-5/G10-6 两张表、`isDerivative` 属 "
            "G10-8、另自研 `currentDecrease`/`closingBalance` 两列与模板口径冲突。已按模板"
            "列序 A..S 重写为 19 字段模型。"
            "🔴 **负债侧三处会计口径差异（不是 G9 的镜像）**：① `F`/`G`（期初调整/审定）与 "
            "`N`/`O`（期末）在 R9 **无合并区** —— 负债侧调整与审定**都不拆分量**，资产侧 G9 "
            "是拆的（M/N 两列调整 → P/Q 两列审定）；② `L=D+I+J` **含利息 J** —— 交易性金融"
            "负债的利息计入财务费用**同时增加负债账面价值**，改造前前端算 D+I（漏 J）致审定数"
            "系统性偏小；③ 本期变动是**净额列**（表头逐字「增加\"+\"/减少\"—\"」）⇒ 模板没有"
            "「本期减少」列，改造前的自研 `currentDecrease` 与走审定线的 `closingBalance`"
            "（=期初审定+变动−减少）两个字段都与模板不符，已移除。`K=C+H` 走未审线（同 G9 的 P=C+M）。"
            "🔴 顺带停用两处方向错的回写：`pushG10FvToDetail`（公允价值层次应落 G10-5）与 "
            "`pushG10DerivativeCheckToDetail`（衍生工具核查应落 G10-8）—— 保签名恒返 0 不写 "
            "store，避免打断 4 个调用方；`sumG10DetailLevel3Closing` 与 "
            "`useG10L3Reconciliation` 的 Level3 名单改由 **G10-5** 定，"
            "`isG10DerivativeDetailRow` 只按 B 列项目名称判。"
            "🔴 **GC-2**：G10 册裸 IF **28 格**（全在 审定表G10-1，受管表 明细表G10-2 零命中）"
            "⇒ 仍按 per-file 保守策略挂中性化（点同册任一 sheet 的在线编辑都会触发整册加载）。"
            "🔴 **FD-1**：HTML store = checklist_responses.item_id='G10-detail-rows'，"
            "payload 落 **remark**（真库实证 remark **2 B 即空数组** / conclusion 0 B）⇒ "
            "与 G9 的 605 B 不同，本条**没有**真实行数据可对，roundtrip 判据一律用合成行。"
            "🔴 该键是 **BP-10 第二严重**的重复声明（6 处 `const … = 'G10-detail-rows'`，"
            "仅次于 G1-2-rows 的 8 处）—— 收敛到 per-cycle storage contract 是未清欠账，"
            "本条只在 provider 侧立单一口径（`all_store_item_ids()`）。"
            "wp_code 裁决：manifest 幻影码 ['G10T']（matcher 域），真码 **G10**（载荷所在，"
            "逐字见 workpaper_sync_entry_wp_code_adjudication.json 该节点，其 contract_id "
            "就是本 provider 的 ADAPTER_ID）。"
            "FC-9 红线：G10 已接显式发布门（useG10Adjudication.publishToTb），"
            "本 provider 对 trial_balance 写次数为 0；审定表 审定表G10-1 归后置 spec "
            "`g-cycle-adjudication-sheets-coverage`（GF-H5）。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2/G9 卡在同一平台级缺口"
            "（umbrella BP-61-1 = G slice 的 BP-1~BP-3），供给就绪后真栈注册。"
        ),
    },
    # ── H9 canary（spec: h-cycle-sync-foundation-and-first-canary · Task 20）──
    {
        "contract_id": "h9.lease_liability_detail",
        "provider_module": "app.services.workpaper_sync.phase5_h9_lease_liabilities",
        "delivered_by_task": "H9-canary",
        "pilot_class": "phase5_lease_liability_detail",
        "entry_id": "xlsx/gt-h9-lease-liabilities",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H9 租赁负债.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**首条** entry（spec h-cycle-sync-foundation-and-first-canary，canary = H9）。"
            "H 循环起点同 E1/G：9 条独立 entry 零 provider / 零契约 / 零 representation。"
            "canary 选型硬依据：**真库唯一非空主表载荷** —— 现算 checklist_responses 的 remark，"
            "9 条主表键只有 3 条命中（H8-2-rows=[] 2B · H10-detail-rows=[] 2B · "
            "**H9-2-rows 819 B / 2 行真实数据**），其余 6 条无行；"
            "几何最简族（两级表头 R7/R8 · 数据 R9-13 仅 5 行 · footer R14 纯 SUM · "
            "22 有效列 · 54 公式 · 裸 IF 24 格全 H 次少）；无专属阻塞。"
            "受管 sheet = `租赁负债明细表H9-2`，公式列 E·I·J·K·L·N（🔴 **负债贷方**口径 "
            "E=B-C+D / L=I-J+K，抄成资产类会让审定期末反号）；UUID 列 W = 有效内容列 22 + 1。"
            "🔴 **平台级前置**：本 entry 所在循环有五条主受管表是**四级表头**"
            "（明细表H2-2 / H4-2 / H5-2 /（成本模式）H7-2 / H8-2）⇒ 本 spec 把 "
            "`contracts._parse_table` 的 header_rows 上界从 3 扩到 **4**"
            "（新增 `MIN_HEADER_ROWS` / `MAX_HEADER_ROWS`），结清 Task 42 登记的 "
            "`pilot_h1_grouped_dynamic.UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE` 欠账。"
            "🔴 H1 的契约 / adapter / golden digest **一字未改**（HC-8）——"
            "h1.disposal_check.json 里那段欠账叙述是冻结的历史记录。"
            "🔴 **范式裁决**：走 `phase5_*`，**不照**同循环已注册的 H1（`pilot_h1_grouped_dynamic` "
            "的 `pilot_*` 范式早于行表引擎）；唯一复用 pilot 的是 `oo_crash_neutralization_fn`。"
            "七段公共流程收进 `phase5_h_cycle_common`（H 要接 9 条，抄 9 份就是 9 个漂移面）。"
            "🔴 **幻影码零回退口径在 H 必须改**：G2 的 assert_no_implicit_template_fallback 断言"
            "「幻影码不得命中任何模板」，但实测 9 个幻影码里 `H6A` / `H10A` **同时是真实程序表码**"
            "（固定资产清理实质性程序表H6A / 资产处置损益实质性程序表H10A）⇒ 照 G2 写这两条 provider "
            "会在注册路径上直接抛。正确不变量 = 「不得命中**别的 entry** 的册子」；"
            "本条的 `H9L` 是真幻影码（三条 finder 路径实测全空）。"
            "🔴 **HD-7 缺口**：H9 `publishToTb` 全链路 **0 处** ⇒ 契约 "
            "`review.tb_publish_gate=None` 是**声明**不是遗漏，本 canary **不覆盖发布链**；"
            "发布链首例归 h2-h6-h10-pilot-cross-reference-lanes。"
            "sync 路径对 trial_balance 写次数为 0。"
            "🔴 **HC-11**：`isRelatedParty` / `isConfirmed` / `isTerminated` 是**中文枚举**"
            "（值域 {是,否}，真库实测全为 '否'），**不得**声明为 boolean（回写会把 '否' 写成 "
            "false、前端下拉失配）；`terminatedFromH8` 是 H8 终止租赁流程回传的**跨 entry 派生标记**，"
            "OO 侧编辑必被覆盖 ⇒ 声明 derived。"
            "口径差异如实登记：模板 `U 期后付款` / `V 备注` 有列但 HTML 无字段（不进 field_specs，"
            "照 H1 对占位列 X 的处置）；`contractNo`/`assetDesc`/`ibrRate`/`leaseTerm`/"
            "`isTerminated`/`terminationDate`/`terminatedFromH8` 七个 HTML 有字段但模板无列"
            "（store-only，不映射格）；6 个公式列 json_key **不落库**（前端 load 时重算）。"
            "🔴 `locked` 标志在 H 循环**惰性**：实测 9 张 H 主受管表 sheet 级保护**全部未启用**"
            "（ws.protection.sheet=False / 无密码 / workbook 未锁结构）⇒ 单元格 locked=True "
            "只是 Excel 未设样式时的默认值。本表 locked = E·I·J·K·L·**M**·N 七列而 M（重分类）"
            "无公式且 HTML 侧可编辑 —— 这**不是模板缺陷**，是「locked 无判读价值」的实证。"
            "契约 mode 一律按「该格逐行有没有真公式」判，merge._protection 也只看契约 "
            "mode + formula_mask 不读模板 locked ⇒ 两边口径一致、无需覆盖层。"
            "🔴 HC-8：`H9-2-rows` 被 `useH8CrossSheet.ts` / `useH8DisposalCheck.ts` 跨 entry 消费 "
            "⇒ 键名冻结。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2 卡在同一平台级缺口"
            "（BP-1~BP-3：instrumentation candidate / 人工审核契约 / approved bundle 三缺），"
            "供给就绪后真栈注册。🔴 capability 从 single_onlyoffice → bidirectional 只能由 "
            "`register_from_manifest()` 在注册成功后驱动，**禁止手改 manifest 文件**（HC-1）。"
        ),
    },
    # ── H6 发布链首例（spec: h2-h6-h10-pilot-cross-reference-lanes）──
    {
        "contract_id": "h6.asset_disposal_clearing_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_h6_asset_disposal_clearing"
        ),
        "delivered_by_task": "H6-publish-chain-first",
        "pilot_class": "phase5_asset_disposal_clearing_detail",
        "entry_id": "xlsx/gt-h6-asset-disposal-clearing",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H6 固定资产清理.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**第二条** entry，也是**发布链首例**：H6 的审定数经 "
            "`H6TabAdjudication → useH6Adjudication.publishToTb` 走显式发布门"
            "（POST audit-determination/publish-to-tb，科目 1606，中文二次确认）；"
            "H8/H9 两条 `publishToTb` 全链路 0 处 ⇒ canary 覆盖不到发布链，由本条补上。"
            "🔴 但 sync 路径对 trial_balance 的写次数仍为 **0** —— 发布是用户显式动作，"
            "不是回写副作用；把 materialize/merge 接到 TB 上会绕过二次确认，"
            "违反 tb-writeback-explicit-publish-gate 铁律。"
            "🔴 **与 canary H9 的三处实质差异（照抄会静默出错）**："
            "① `H6A` **不是幻影码** —— 它同时是真实程序表码（册内 sheet "
            "`固定资产清理实质性程序表H6A`），解析到自己的册 ⇒ "
            "`phantom_code_resolves_to_own_workbook=True`；照 G2 的「幻影码不得命中任何模板」"
            "会让本 provider 注册时直接抛。"
            "② 审定期末公式是**资产口径** `L=I+J-K`（H9 是负债口径 `L=I-J+K`）—— "
            "直接复制 H9 的模板会让 H6 审定期末反号。"
            "③ payload 列是 `dual_write_remark_and_conclusion`（H9 是 `remark_only`）。"
            "🔴 **公式列部分落库**：E/I/L 的 json_key 落库、**J/K 不落库**"
            "（前端 load 时 `applyH62BalanceFormulas` 重算）⇒ 回写比对不得按 H9 的"
            "「公式列一律不落库」推演，否则把「store 里本来就没有」误报成「回写丢字段」。"
            "🔴 **HC-6 派生合计 6 键**（H6-2-subtotal-gain-loss / -net-book-value / "
            "-begin-unadjusted / -end-unadjusted / -begin-audited / -end-audited）"
            "与主表同批写出，不参与 roundtrip 比对。"
            "🔴 **HC-8 键名冻结**：`H6-2-rows` 被 h10RelatedH6Pull.ts / "
            "h1SoeClearingH6Pull.ts / h6DisclosureModel.ts 三处跨 entry 消费 ⇒ 本轮只补契约不改键名。"
            "🔴 **真库零载荷**：`H6-2-rows` 在 checklist_responses 无行 ⇒ roundtrip 真实证"
            "需造数据，这正是 canary 选 H9 而非 H6 的原因（如实登记，不粉饰）。"
            "模板 16 列**全部**有 store 字段 ⇒ `template_only_columns` 为空（与 H9 的 U/V 不同）；"
            "反向 20 个 HTML 字段模板无列（含 accDepreciation/tax/netGainLoss/h1Reference/"
            "h10Reference 五个兼容别名 + 派生列 endAdjustment）。"
            "`adapter_registered=False` 同 canary：BP-1~BP-3 属平台缺口，不手改 manifest。"
        ),
    },
    # ── H4 首个四级表头 + 三区块宽表（spec: h4-h8-sub-entry-lanes-…）──
    {
        "contract_id": "h4.engineering_materials_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_h4_engineering_materials"
        ),
        "delivered_by_task": "H4-four-level-header",
        "pilot_class": "phase5_engineering_materials_detail",
        "entry_id": "xlsx/gt-h4-engineering-materials",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "H/H4 工程物资.xlsx",
        "adapter_registered": False,
        "reason": (
            "H 循环**第三条** entry，规模上是前两条的量级之外："
            "🔴 **四级表头**（R8/R9/R10/R11）—— 这是 `contracts.MAX_HEADER_ROWS` 从 3 扩到 4 "
            "之后的**首个真实消费者**（扩容见 commit 91933bd68，结清 Task 42 登记的 "
            "UPSTREAM_DEBT_FOUR_LEVEL_HEADER_NOT_EXPRESSIBLE 欠账）；schema 回退到 3 "
            "则本 entry 直接无法表达。H9/H6 都只是两级表头。"
            "🔴 **49 有效内容列 + 三区块**（原值 E..AH / 减值准备 AI..AS / 期末净值 AT..AU），"
            "对比 H9 的 22 列单区块与 H6 的 16 列单区块；max_column=67 是空列尾巴。"
            "🔴 **18 个 template-only 列**，主体是**调整/审定块的数量列与单价列** —— "
            "前端在那些位置只有金额标量。该映射**由代码定死不是命名推测**："
            "`useH4Detail.ts#L63` 注释『调整（金额口径 AJE，对齐 Excel 核实情况）』+ "
            "`#L140 auditedBegin = calcAuditedAmount(row.beginAmount, row.ajeBegin, 0)` "
            "以金额为基。若把 `ajeBegin` 映到数量列 Q，回写会把金额写进数量格，"
            "且单价公式 `=金额/数量` 立刻算出荒谬单价。"
            "**覆盖闭合自检：31 映射 + 18 template-only == 49 有效列**，无重复无交叠"
            "（落在契约 review.column_coverage_closure，判据可复算）。"
            "🔴 **`ajeImpair` 是 store-only**：前端把减值调整压成一个字段，模板却是 "
            "AM 期初调整 + AN 账项增加 + AO 账项减少三列且 AS 走 `=AP+AQ-AR`，"
            "一对三无法确定分摊 ⇒ 不映射任何格，两侧口径差异写进 html_store_note。"
            "🔴 **footer R28 之下还有不受管区域 R29-R34**（`A29='其中：'` + 5 行按类别 "
            "SUMPRODUCT 小计，行标签取 =底稿目录!A9..A13）—— H9/H6 的 footer 之下无内容；"
            "不显式登记（review.unmanaged_regions），merge 可能把它们当数据行覆盖，"
            "一次就把分类小计整块写坏。"
            "🔴 **2 条 `H4T` 子入口**（h4/impairment/H4TabImpairment.vue / H4TabRecoverable.vue）"
            "按 AC 1.6 **复用本 entry 的 adapter** —— 不新建 adapter、不给子入口单独登记契约。"
            "🔴 `H4-3-rows` 登记在 review.sibling_tables_not_managed：它是**另一张表**"
            "（调整分录汇总 H4-3），不是本表的合计副本，也不在本轮受管面 —— "
            "登记它是为了让后续批次不把它误当派生键跳过。"
            "载体族：write/read 皆 `formdata_composable`（H9/H6 都是 host_inline）。"
            "幻影码 `H4E` 是**真**幻影码（三条 finder 路径实测全空；程序表码是 `H4A` 不是 `H4E`），"
            "与 `H6A`/`H10A` 那两个同时是真实程序表码的情形相反。"
            "HD-7：H4 **无** TB 发布门（publishToTb 在 H4 链路 0 处；发布链首例是 H6）。"
            "`adapter_registered=False` 同前两条：BP-1~BP-3 属平台缺口，不手改 manifest。"
        ),
    },
    # ── I6 canary（spec: i-cycle-sync-foundation-and-first-canary · Task 22）──
    {
        "contract_id": "i6.research_development_expense_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_i6_research_development_expense"
        ),
        "delivered_by_task": "I6-canary",
        "pilot_class": "phase5_research_development_expense_detail",
        "entry_id": "xlsx/gt-i6-research-development-expense",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I6 研发费用.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环**首条** entry（spec i-cycle-sync-foundation-and-first-canary，canary = I6）。"
            "I 循环起点：6 条独立 entry 零 provider / 零契约 / 零 representation、**无 pilot**"
            "（四个 pilot 是 B60/D2/H1/G7，逐文件读 review.entry_id 无一条属 I）。"
            "canary 选型硬依据：**真库有非空主表载荷** —— 现算 checklist_responses 的 remark，"
            "I 前缀只 7 个 item_id 有行，6 条主表键里只有 2 条非空"
            "（I5-2-rows 745 B 但 rowId 是 E2E 种子 e2e-i52-contract ⇒ 成色不如 I6 · "
            "**I6-2-detail-rows 194 B / 2 行**），I1/I2/I3/I4 主表键 + I6-2-rows(legacy) 全零；"
            "几何最简（**单级**表头 R8 全 I 最浅 · 数据 R9-18 十行 · 84 公式 · "
            "裸 IF 45 格全 I 最少 · definedName 0 · merged 仅 2）；"
            "🔴 **与 H10-2 / D4-2 高度同构**（12 月度列 B-M + 年度合计 N=SUM(B:M)）⇒ "
            "months/0..months/11 数组路径复用 D4-2 已验通范式，json_path 是唯一数组段真源。"
            "受管 sheet = `明细表I6-2`，公式列 N·Q·R·W（🔴 R 的分母是 footer 绝对引用 $Q$19，"
            "抄成相对引用会让每行占比指向错误分母行）；UUID 列 AA = 有效内容列 26 + 1"
            "（🔴 **不得放 66** —— max_column 是 65，有效与 max 之间 39 列全空，放 66 会让 "
            "OO 打开后列宽错位）。"
            "🔴 **双 footer**：R19 合计（B..Y 各 =SUM(x9:x18)）+ R20「各月比例」"
            "（B..N 各 =IF($N$19=0,0,x19/$N$19)）。R20 是 R19 的**派生**不是第二个合计锚点 ⇒ "
            "引擎 footer_row 只取 R19，契约 review.footer_rows=[19,20] 是**事实声明**"
            "（供 roundtrip 判据知道 R20 不是业务行），两者不得混用。"
            "🔴 **身份 backfill 是 canary 第一道前置**：真库那 2 行原本既无 id 也无 rowId，"
            "useI6Detail.ts#L303 的 raw.id ?? raw.rowId ?? `row-${Date.now()}` 兜底会每次读都"
            "生成新 id、roundtrip 恒判「全删全增」⇒ 已一次性 backfill 为 "
            "i6-detail-bf01-zhptyd / i6-detail-bf02-xplcsy。"
            "🔴 **键名冻结**（IC-17）：I6-2-detail-rows 有 5 个跨 entry 消费方，其中 "
            "h1DepAllocCounterpartPull.ts 属 **H1 pilot**（adapter 已注册、golden 已锁）⇒ "
            "本条任何改动完成后回归 H1 契约 golden digest，且**不得修改 H1 的契约/adapter/golden**。"
            "另有 legacy alias I6-2-rows（LEGACY_STORAGE_KEY 真存在）⇒ 契约声明"
            "「读认两键、写只写主键」，删它历史数据读不出。"
            "🔴 **BP-5②禁接**：useI6FormData.ts（448 行）含完整 checklist GET/PUT + "
            "trial-balance/writeback 管道，但 import 生产/测试消费**双零**（按 import 路径字面量"
            "三形态现算，禁符号名 grep）⇒ 契约 forbidden_carriers 显式禁接。接到它上面会让宿主"
            "行为一点不变而守卫因「文件确实被改了」全绿 = **假绿第①源**。"
            "🔴 **范式裁决**：走 `phase5_*`；七段公共流程**直接复用** phase5_h_cycle_common"
            "（实测零 H 硬编码，类名带 H 只是历史命名）⇒ I 不再造第二份骨架。"
            "唯一复用 pilot 的是 `oo_crash_neutralization_fn`（IC-9，per-file 挂，本册 45 格；"
            "整册统一挂不行 —— I1 的 321 与 I6 的 45 差 7 倍）。"
            "🔴 **GC-9 在 I 反向**：I 循环 **6/6 全有 TB 发布门**（与 H 的 H8/H9 完全无门相反）⇒ "
            "canary 直接覆盖发布链，不外移首例。I6 的门在 useI6Adjudication.ts（publishToTb ×3）"
            "+ i6/core/I6TabAdjudication.vue（×2），只走 POST "
            "/api/workpapers/{wpId}/audit-determination/publish-to-tb + 二次确认。"
            "`adapter_registered=False`：与 D1/D3/D5/D6/D7/E1/F1~F5/G2/H9 卡在同一平台级缺口"
            "（BP-1~BP-3：instrumentation candidate / 人工审核契约 / approved bundle 三缺），"
            "供给就绪后真栈注册。🔴 capability 从 single_onlyoffice → bidirectional 只能由 "
            "`register_from_manifest()` 在注册成功后驱动，**禁止手改 manifest 文件**（IC-1）。"
        ),
    },
    # ── I2（spec: i2-i4-i5-carrier-and-structure-exceptions · Task 17）────────
    {
        "contract_id": "i2.development_expenditure_detail",
        "provider_module": (
            "app.services.workpaper_sync.phase5_i2_development_expenditure"
        ),
        "delivered_by_task": "I2-lane2",
        "pilot_class": "phase5_development_expenditure_detail",
        "entry_id": "xlsx/gt-i2-development-expenditure",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I2 开发支出.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第二条（canary I6 之后）。选它先接的理由：**除 canary 外几何最简的单区表**"
            "（单区无派生区 · 有效列 20 即 A..T · 数据 R13-22 十行 · footer R23）。"
            "受管 sheet = `明细表I2-2`，🔴 **三级表头 R10/R11/R12**（header_rows=3，"
            "各列 header_text 取该列最深非空标题 —— A/Q/S/T 在 R10 · B/G/H/I/L/M/P 在 R11 · "
            "C/D/E/F/J/K/N/O 在 R12；照「统一取 leaf 行」会让 12 列取到 None）；"
            "公式列 G·L·M·N·O·P·R（🔴 G 与 P 是**减两项**口径「期初+增加−计入资产−计入损益」，"
            "抄成「期初+增加−减少」会漏一个减项）；UUID 列 U = 有效 20 + 1"
            "（🔴 **不得放 62** —— max_column 61，有效与 max 之间 41 列全空，全 I 差距最大）。"
            "🔴 **footer 非单一形态**：B..P 十四格纯 SUM，但 **R23 例外是 =P23-Q23** 套用行公式"
            "（同 I3-2 R23 的 row_formula_applied，本表只此一格）⇒ roundtrip 判据不得对 footer "
            "做统一形态假设。"
            "🔴 **I2 是 I 循环唯一「双例外」entry**：①唯一**缺二级 UI 门控**"
            "（宿主 isOoAvailable 与「仅结构化视图」tag 命中均 0 ⇒ OO 探测失败时切换按钮照样显示，"
            "违反 AC 1.5；判据写「全 slice 都有二级门控」会在本条上静默恒真、恰好漏掉最严重那条）"
            "②唯一**发布门不在 composable**（useI2Adjudication.ts 里 publishToTb **0 命中**，"
            "门在 I2TabAdjudication.vue#L384 自建）⇒ 契约 gate_layer='host_tab'；"
            "「I 循环 6/6 全有发布门」是 **entry 维度**成立的结论，判据按 composable 找门会假红。"
            "🔴 **第三个例外：有第二写路径且是活代码** —— useI2FormData.ts（501 行）import "
            "生产消费现算 **4**（宿主 + useI2Adjudication + useI2Impairment + "
            "i2/core/I2TabAdjudication.vue）。对比 useI4FormData(394 行)/useI6FormData(448 行) "
            "**双零消费**是死代码 ⇒ 三个文件名同型但只有 I2 那个是活的，一刀切「I 的 FormData "
            "都是孤儿」会把 I2 的写路径删掉、保存静默失效。两条写路径打同一端点同一 item 形状 "
            "{item_id, conclusion, remark}，注册 adapter 后不应分叉。"
            "🔴 **主表键 I2-2-rows 是跨 lane 冻结键**：lane 1 的 useI1AdditionCheck.ts#L250-251 "
            "读它且读法是 `?.remark ?? ?.conclusion` ⇒ ①不得改键名 ②不得在未通知 lane 1 的"
            "情况下改 payload 列语义；i2ConsistencyModel.ts#L213 的前缀映射 "
            "'I2-2-': ['I2-2-rows'] 也依赖它，改名会同时打断一致性检查前缀表。"
            "🔴 **IC-12 全 I 最严重的 wp_index 问题落在本条**：真库 wp_index 里 `I2-1` "
            "**一码两名两底稿** —— `商誉减值测试`（×1，业务上属 **I3**）与 `开发支出审定表`（×3）"
            "指完全不同的底稿（比 H 的 H1-2 同底稿不同名严重）⇒ 契约 source_ref 只用 "
            "{workbook_sha256, sheet_name}，**禁任何 wp_index 来源字段**。"
            "🔴 **IC-5 两个 verdict 同属本 entry**：CD-5 主表无 impl 分类常量 ⇒ "
            "NO_IMPL_CLASSIFICATION_BY_DESIGN/clean；CD-6 defaultPerCapitaPeers ⇒ "
            "HARDCODED_SEED_ROW_COUNT_NO_SOURCE_REF/scanned_and_classified_not_a_defect"
            "（不是缺陷 —— 「同业人均数」对照表的默认行数种子，模板本来就没有对应分类区间）。"
            "status 维度上两者**不相加**。"
            "🔴 **IC-6 在本 entry 命中 0** 且不是漏扫（8 个位置化 site 全在 lane 1 的 {I1,I3}）"
            "⇒ 按 IC-20 断言「现算 0」但**不宣称该维度通过**。"
            "**源模板真源断链登记不修**：明细表I2-2!A17 是字面「数据资源」（不是 =底稿目录!A18）"
            "⇒ 改 A18 不传播；另 2 处同型在 I1 归 lane 1。不改模板字节。"
            "IC-9 per-file 裸 IF **113**（I1 321 / I4 186 / I2 113 / I3 63 / I5 49 / I6 45，"
            "总 777）⇒ 整册统一挂不行，最重与最轻差 7 倍。"
            "真库 `I2-2-rows` **无行** ⇒ roundtrip 只能合成载荷。"
            "`adapter_registered=False`：同 I6 卡 BP-1~BP-3 平台级缺口。"
        ),
    },
    # ── I4（spec: i2-i4-i5-carrier-and-structure-exceptions · Task 17）────────
    {
        "contract_id": "i4.long_term_prepaid_detail",
        "provider_module": "app.services.workpaper_sync.phase5_i4_long_term_prepaid",
        "delivered_by_task": "I4-lane2",
        "pilot_class": "phase5_long_term_prepaid_detail",
        "entry_id": "xlsx/gt-i4-long-term-prepaid",
        "document_type": "xlsx",
        "authority_model": "projection_contract",
        "template_relative_path": "I/I4 长期待摊费用.xlsx",
        "adapter_registered": False,
        "reason": (
            "I 循环第三条。受管 sheet = `明细表I4-2`，🔴 **三级表头 R8/R9/R10**（header_rows=3，"
            "各列 header_text 取该列最深非空标题 —— A/B/C/D/E/T/U 在 R8 · F/G/J/K/L/O/P/S 在 R9 · "
            "H/I/M/N/Q/R 在 R10）；数据 R11-22 十二行；footer R23 合计（E..S 各 =SUM(x11:x22)，"
            "A/B/C/D/T/U 无合计）；公式列 J·O·P·Q·R·S（🔴 J 与 S 是**减两项**口径"
            "「期初+增加−本期摊销−其他减少」）；UUID 列 W = 有效 22 + 1。"
            "🔴 **双区（IC-19）**：第 2 区 `R24「其中：」+ R25-28` 四行是**派生区** —— A 列逐格 "
            "`=底稿目录!A9`..`A12`、E..J 等列是 **ArrayFormula** 按 B 列类别回汇总第 1 区 ⇒ "
            "标 `derived`、**不纳入业务行比对**（否则 roundtrip 会把「第 1 区改动引起的派生区重算」"
            "判成用户编辑了派生区）；且 `editable_labels=false` —— 允许用户改标签会被下次 render "
            "从 `底稿目录` 静默覆盖。"
            "🔴 **本条与 I5 是 definedName「基线不增长」口径的唯一实证场**：本册 **476**"
            "（全 I 最多；I5 334、其余四册 I1/I2/I3/I6 全 0，合计 810）⇒ 判据 SHALL 用"
            "「登记基线 + 断言不增长」，**不得**照抄 H 循环 HC-14 的「断言全 0」—— 那在 "
            "I1/I2/I3/I6 上恒真悄悄通过，**只有 I4/I5 会打红**。"
            "🔴 **不删这 476 个**：是模板公式的命名引用，删了会让 max_column 内的公式整片失效；"
            "只声明「同步时不新增、不改写」。"
            "🔴 **BP-5 双零消费死代码禁接**：`useI4FormData.ts`（394 行）import 生产/测试消费"
            "**双零**（按 import 路径字面量三形态现算，禁符号名 grep —— I 循环有 4 处注释链式"
            "提及 dual-mode composable，符号名口径会把注释当消费边）。**对比 I2**："
            "`useI2FormData.ts`（501 行）消费计数 **4** 是**活代码**（_doSave 内真 PUT = I2 的"
            "第二写路径）—— 三个 FormData 文件名同型（i2/i4/i6）但**只有 I2 那个是活的**，"
            "一刀切「I 的 FormData 都是孤儿」会把 I2 的写路径删掉、保存静默失效。"
            "⇒ 契约 forbidden_carriers 禁接；🔴 **本轮不删文件**（跨 spec 清理动作，"
            "与并发会话有冲突风险；禁接已足够防误用）。"
            "🔴 **payload mode `dual_write` 未被真库证实**：slice 记 "
            "dual_write_remark_and_conclusion_for_status_marker，但真库 I 循环 **7 行全部 "
            "remark_only**（conclusion 全 NULL）⇒ 标 `unverified_in_live_db`，"
            "**不得**把 slice 声明当已验证事实；落地时须断言写 conclusion 列**不破坏** "
            "remark_only 读侧（I2 的第二写路径与 lane 1 的 useI1AdditionCheck 都读 conclusion 兜底）。"
            "🔴 **CD-8 = BP-8②**：impl `CATEGORY_OPTIONS` **6 条** vs 源 `明细表I4-2!A11` 真读"
            "**仅 1 条**（`使用权资产改良及维护支出`；A9/A10 空 + A12:A22 全空）⇒ verdict "
            "PREFIX_MATCH_WITH_UNSOURCED_TAIL，无真源尾部 **3 条**（租入固定资产改良支出 / "
            "固定资产大修理支出 / 开办费）。修法归**业务确认**（是否属长期待摊费用的合法分类是"
            "会计判断）⇒ 本轮登记不修。"
            "🔴 **删行 API 属 id 族**（`useI4Detail.ts#L672 removeRow(rowId: string)` 先 "
            "findIndex 再 splice），与同 lane 的 I2 `removeRow(index: number)` 下标族不同 ⇒ "
            "本 lane 是 **1:2 跨两族**，而 lane 1 两条 entry **100% 下标族** ⇒ 两个 lane "
            "**不得复用同一个签名断言**，否则一边必然假红或假绿。"
            "🔴 **IC-6 在本 entry 命中 0** 且不是漏扫（8 个位置化 site 全在 lane 1 的 {I1,I3}）；"
            "**IC-18 derived_total_keys 现算 0** 且已裁非漏扫（I1 8 / I2 2 / I6 3 · I3/I4/I5 皆 0）"
            "⇒ 两项均按 IC-20 空分母纪律断言「现算 0」但**不宣称该维度通过**。"
            "**模板侧其他字段不进本契约**：`I4DetailRow` 的摊销政策族（amortizationMethod / "
            "totalMonths / accAmortization / …）与基础族（occurDate / contractNo / startDate / …）"
            "属 `摊销测算I4-6` 与 `摊销测算表I4-7（工作量法）` 两张后置 sheet"
            "（🔴 后者禁 strip 括号）—— Requirement 6.1 禁止无来源自造字段。"
            "IC-9 per-file 裸 IF **186**（全 I 第二重；I1 321 / I4 186 / I2 113 / I3 63 / "
            "I5 49 / I6 45，总 777）⇒ 整册统一挂不行。"
            "真库 `I4-2-rows` **无行** ⇒ roundtrip 只能合成载荷。"
            "`adapter_registered=False`：同 I2/I6 卡 BP-1~BP-3 平台级缺口。"
        ),
    },
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
    "DELIVERED_PER_ENTRY_CONTRACTS",
    "ManifestRegistrationPlanItem", "ManifestRegistrationOutcome", "RegistrationFailure",
    "build_manifest_registration_plan",
]
