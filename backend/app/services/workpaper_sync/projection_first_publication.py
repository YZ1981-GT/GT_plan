"""`projection_contract` lane 的**首版** published representation 发布服务层。

**Spec: published-representation-production-path-and-lane-adjudication**
Requirements: 3.1~3.9（准入）、4.1~4.6（暂存）、5.1~5.8 / 7.2 / 7.9 / 7.10（发布）
Tasks: 4.1（`FirstPublicationPlan` + `resolve_plan`）、4.3（`stage_instrumented_substrate`）、
4.5（`publish_first_generation`）

═══ 这个模块解决的是一个「先有鸡还是先有蛋」════════════════════════════════════

`PublishedIdentityObserver.observe(representation=…)` 与各 pilot 的
`resolve_published_frozen_definitions(*, session, representation, contract)` 都要求先有
一条 **published representation** 才能读出 `FrozenEntryDefinitions`；而 representation
又要 `FrozenEntryDefinitions` 派生出的 adapter 才能被 `ContentMutationService.commit`
创建。库里 `projection_contract` lane 的 representation 因此恒为 0 行（实测），四个
Excel pilot 的 `adapter_registered` 恒 `False`，manifest 186 条 entry 的 `adapter_id`
恒 `null`。

破环点是 :class:`ExcelEntryDefinitionLoader.load` —— 它的入参是
``entry_id / frozen_bundle_id / frozen_bundle_sha256 / adapter_build /
identity_inventory / observed_structure / observed_business_sheets /
observed_dynamic_columns``，**没有一个是 representation 标识**。这四项实测入参可以直接
从「权威模板字节 → instrumentation」现算出来，不需要任何 representation 先存在。
本模块就是把这条路走通（Property 18 的落点）。

═══ 本模块**不**做的事 ═══════════════════════════════════════════════════════

* 不 commit：事务边界属于宿主脚本（与 `WorkpaperSyncRepository` 只 flush 不 commit、
  `ProjectionDefinitionProvisioner` 不自己开事务的既有约定一致）；
* 不选目标底稿：目标选取属宿主（Task 6.1 的 `TARGET_ORDER_SQL` 全序）；
* 不发布 definition：那是 Task 76 的 `ProjectionDefinitionProvisioner`；
* 不降级任何判据：`commit` 的 `_assert_authority_shape` 仍要求 projection + contract +
  adapter 三者齐备，bundle 仍必须 approved，typed slot 仍不得是 marker；
* 不注册 adapter、不碰 `PENDING_ENGINE_ADAPTERS`、不引用 Word lane。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.workpaper_sync.models import SyncDomainError

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 异常 —— 每条准入/失败形态一个独立 error_code（Property 12：两两不同）
# ═══════════════════════════════════════════════════════════════════════════


class FirstPublicationError(SyncDomainError):
    """首版发布域异常基类。"""

    error_code = "first_publication_error"


class ProjectionBundleNotProvisionedError(FirstPublicationError):
    """判据 A 不成立 —— 该 entry 还没有 approved projection bundle。"""

    error_code = "projection_bundle_not_provisioned"
    #: 诊断指向的解除动作（不是自由文本：守卫按它断言诊断真的指了宿主）
    remediation: Final[str] = (
        "backend/scripts/fix/fix_task76_provision_projection_definitions.py"
    )


class FirstPublicationAlreadyDoneError(FirstPublicationError):
    """判据 B 已成立 —— 本入口是**首版**专用，不得拿来覆盖既有 representation。"""

    error_code = "first_publication_already_done"


class ContractNotReviewedError(FirstPublicationError):
    """磁盘契约的 `review_status` 不是 `reviewed` —— generator 候选不得当生产契约。"""

    error_code = "contract_not_reviewed"


class OoxmlSecurityRejectedError(FirstPublicationError):
    """instrumented 字节被 OOXML 安全策略拒绝（在产出 staged artifact **之前**）。"""

    error_code = "ooxml_security_rejected"

    def __init__(self, message: str, *, entry_id: str = "", gate: str = "") -> None:
        super().__init__(message)
        self.entry_id = entry_id
        #: 被触发的具体门名（如 `external_relationships`）。可编程属性，不必 parse 文案。
        self.gate = gate


class SubstrateStagingError(FirstPublicationError):
    """暂存阶段的非安全类失败（instrumentation 抛错、实测入参算不出来）。"""

    error_code = "substrate_staging_failed"


class ProviderCapabilityError(FirstPublicationError):
    """provider 模块缺本流程必需的导出（例如没有 `build_store_projection`）。"""

    error_code = "provider_capability_missing"


#: lane 裁决里判「磁盘契约 `review_status == reviewed`」那一条判据的编号（L5）。
#:
#: 🔴 这个数字**不是**本模块自己规定的，它是 `adjudicate_lane` 的 L1→L5 顺序里契约那一
#: 格的位置。`resolve_plan` 的第 ⑤ 条与它判的是同一件事，因此不另查一遍，而是按这个
#: 编号把 `lane_undecided` 翻译成 `contract_not_reviewed`（见 `resolve_plan` 第 ① 条）。
#: 两侧靠 `_assert_contract_criterion_number_agrees()` 锁死 —— L 顺序变了这里必须跟着变。
_CONTRACT_CRITERION: Final[int] = 5


def _assert_contract_criterion_number_agrees() -> None:
    """`_CONTRACT_CRITERION` 必须真的是 lane 裁决里契约那一格的编号。

    判据落在**真实执行**：拿一个已交付 entry，把它的契约加载打断，看 `adjudicate_lane`
    报出来的 `criterion_number` 是不是这个数。写死一个数而不锁，L 顺序调整后翻译就会
    落到错的格上（把「bundle 缺失」当成「契约未复核」）。

    本函数在 **import 期**跑（与 `assert_registry_covers_opaque_lanes` 同款）。
    """
    from app.services.workpaper_sync import contracts as contracts_module
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )
    from app.services.workpaper_sync.projection_lane_registry import (
        LaneUndecidedError,
        assert_projection_lane,
    )

    if not DELIVERED_PER_ENTRY_CONTRACTS:  # pragma: no cover — 登记表恒非空
        raise FirstPublicationError(
            "DELIVERED_PER_ENTRY_CONTRACTS 为空 —— 判据编号锁失去分母"
        )
    entry_id = str(DELIVERED_PER_ENTRY_CONTRACTS[0]["entry_id"])

    original = contracts_module.load_contract

    def _break(_contract_id: str) -> Any:
        raise RuntimeError("判据编号锁：临时打断契约加载")

    contracts_module.load_contract = _break  # type: ignore[assignment]
    try:
        assert_projection_lane(entry_id)
    except LaneUndecidedError as exc:
        if exc.criterion_number != _CONTRACT_CRITERION:
            raise FirstPublicationError(
                f"契约那一格的判据编号实测为 L{exc.criterion_number}"
                f"（{exc.criterion_label}），而本模块按 L{_CONTRACT_CRITERION} 翻译 —— "
                "lane 裁决的 L 顺序变了，翻译会落到错的结算格上"
            ) from exc
    except Exception as exc:  # pragma: no cover — 其它异常说明构造前提已变
        raise FirstPublicationError(
            f"判据编号锁的构造失效：打断契约加载后抛的是 {type(exc).__name__} "
            f"而不是 LaneUndecidedError（{exc}）"
        ) from exc
    else:  # pragma: no cover
        raise FirstPublicationError(
            "打断契约加载后 lane 裁决竟然通过了 —— L5 没有真的读磁盘契约"
        )
    finally:
        contracts_module.load_contract = original  # type: ignore[assignment]


_assert_contract_criterion_number_agrees()


# ═══════════════════════════════════════════════════════════════════════════
# 1. FirstPublicationPlan（Task 4.1 / Requirement 3.9）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FirstPublicationPlan:
    """一次首版发布的**冻结**计划。零写入面。

    `__post_init__` 调 `assert_no_mutation_surface` —— 与 `ContentCommitPlan` /
    `BusinessMutation` 同款约定：计划对象里不许夹带 session / repository / outbox，
    否则「计划」就变成了可以自己写库的东西，事务边界随之失控。
    """

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    contract_id: str
    provider_module: str
    document_type: str
    expected_revision: int
    #: `resolution.load_bundle_snapshot()` 的产出（approved + 三 typed slot 已校验）
    bundle: Any
    #: `contracts.load_contract()` 的产出（`review_status == reviewed` 已在其内部强校验）
    contract: Any
    #: 该 entry 的 authority model definition logical_id（现取，不写死字面量）
    authority_model_logical_id: str
    actor_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        from app.services.workpaper_sync.content_mutation import (
            assert_no_mutation_surface,
        )

        assert_no_mutation_surface(self, label="FirstPublicationPlan")


@dataclass(frozen=True)
class StagedSubstrate:
    """`stage_instrumented_substrate` 的产出。纯文件侧，无任何数据库标识。"""

    entry_id: str
    staged_path: Path
    source_sha256: str
    instrumented_sha256: str
    #: 四项**现算**实测入参（Requirement 4.1）
    identity_inventory: Any
    observed_structure: tuple[tuple[str, str, str, str], ...]
    observed_business_sheets: tuple[str, ...]
    observed_dynamic_columns: Mapping[str, tuple[tuple[str, str], ...]]
    #: `table_key` → (`{slot}_{seq}` → **Excel 列标**) 的实测绑定。
    #:
    #: 🔴 与 :attr:`observed_dynamic_columns` 是**两件不同的东西**，不可互相顶替：
    #: 前者是 `(label, key)` 对，喂给 loader 做「键不由 label 派生」的判据；本项是
    #: `key → 列标`，喂给 `ExcelIdentityBinding.dynamic_column_columns` 决定往哪一列写。
    #: 首版实现曾把前者塞进后者（`{key: label}`），G7 实测炸在
    #: `ValueError: 'minority_financials#1' is not a valid column name` —— 前三个 entry
    #: 都没有动态列，字典恒空，于是这个错形三个 entry 全查不出来。
    observed_dynamic_bindings: Mapping[str, Mapping[str, str]]
    #: OOXML 安全门报告（已通过；未通过时本对象根本不会被构造）
    ooxml_gates: tuple[str, ...]


# ═══════════════════════════════════════════════════════════════════════════
# 2. resolve_plan —— 五条准入，顺序固定（Task 4.1 / Requirements 3.1~3.8）
# ═══════════════════════════════════════════════════════════════════════════


async def resolve_plan(
    *,
    session: Any,
    resolution: Any,
    project_id: uuid.UUID,
    wp_id: uuid.UUID,
    entry_id: str,
    actor_id: uuid.UUID | None = None,
) -> FirstPublicationPlan:
    """按固定顺序求值五条准入；任一不成立时**不写任何库行**。

    顺序不可交换（Property 10 的判据落点 = 「使第 k 条不成立时抛出的恰是第 k 个
    error_code」）：

    ① :func:`assert_projection_lane`      → `lane_undecided` / `lane_is_opaque`
    ② 供给判据 A 必须为 **True**          → `projection_bundle_not_provisioned`
    ③ 供给判据 B 必须为 **False**（首版专用）→ `first_publication_already_done`
    ④ bundle 三 typed slot 逐项校验        → 委派 `load_bundle_snapshot`（六类 slot 异常）
    ⑤ 磁盘契约 `review_status == reviewed` → `contract_not_reviewed`

    ①在②之前是必需的：opaque entry 没有 per-entry 契约登记，②会先报
    `projection_bundle_not_provisioned`，把「这根本不是 projection lane」这条更根本的
    原因遮蔽掉。

    ④**委派**而不重写：`load_bundle_snapshot` 与 `ExcelEntryDefinitionLoader` 已经实现
    了 typed slot 的六类分类；在这里重写一份的后果不是更安全，而是任一侧被短路都不改变
    行为 ⇒ 变异检验判 GREEN。

    ⑤ 与 lane 裁决的 L5 判的是**同一件事**（磁盘契约 `review_status == reviewed`），
    因此它不另查一遍，而是把 ① 抛出的 `lane_undecided`（当且仅当首个不成立判据是 L5）
    **翻译**成本模块的 `contract_not_reviewed`。见 `_CONTRACT_CRITERION` 处的说明。
    """
    from app.services.workpaper_sync.contracts import load_contract
    from app.services.workpaper_sync.projection_lane_registry import (
        LaneUndecidedError,
        assert_projection_lane,
        authority_model_logical_id,
        observe_lane_supply,
    )

    # ── ① lane 裁决（内含 ⑤ 的判定 —— 见下）────────────────────────
    #
    # 🔴 2026-09-05 更正一处**结构性不可达**：原实现在 ④ 之后另跑一次 `load_contract`
    #    并把异常翻译成 `ContractNotReviewedError`，但 lane 裁决的 **L5 判的就是这件事**
    #    （`review_status != reviewed` ⇒ `undecided`）。于是任何能让第 ⑤ 条不成立的输入
    #    都会先在第 ① 条抛 `lane_undecided` ⇒ 第 ⑤ 条永不可达、`ContractNotReviewedError`
    #    是死代码、宿主的 `blocked_contract_not_reviewed` 结算格永远到不了，
    #    Requirement 3.6 未被满足。
    #
    #    后果不是理论上的：契约未复核时运维会被 `blocked_lane_undecided` 送去查
    #    lane 裁决真源（L1~L5 五条判据），而真正该做的事是**契约复核方把 review_status
    #    推到 reviewed** —— 宿主的 `_STATE_UNBLOCK_OWNER` 里那两格写的解除方完全不同。
    #
    #    改法是**翻译**而不是再查一遍：L5 仍是唯一判定处（不产生第二真源），
    #    但它那一格的 `undecided` 在本入口有专属 error_code 与专属解除方。
    try:
        assert_projection_lane(entry_id)
    except LaneUndecidedError as exc:
        if exc.criterion_number == _CONTRACT_CRITERION:
            raise ContractNotReviewedError(
                f"entry {entry_id!r} 的磁盘 per-entry 契约不可用作生产契约"
                f"（lane 裁决 L{_CONTRACT_CRITERION}：{exc.criterion_label}，"
                f"真源 {exc.source_path}）: {exc}"
            ) from exc
        raise

    # ── 现取该 entry 的交付登记（contract_id / provider_module / document_type）──
    supply_row = _delivered_row(entry_id)
    contract_id = str(supply_row["contract_id"])
    provider_module = str(supply_row["provider_module"])
    document_type = str(supply_row["document_type"])

    # ── ②③ 供给四条判据 ────────────────────────────────────────────
    facts = await observe_lane_supply(
        session=session, project_id=project_id, wp_id=wp_id, entry_id=entry_id
    )
    if not facts.projection_bundle_provisioned:
        raise ProjectionBundleNotProvisionedError(
            f"entry {entry_id!r} 的判据 A（projection_bundle_provisioned）不成立 —— "
            f"库里没有 authority model logical_id="
            f"{authority_model_logical_id(contract_id)!r} 的 approved projection bundle。"
            f"解除动作：先跑 {ProjectionBundleNotProvisionedError.remediation}"
        )
    if facts.published_representation_current:
        raise FirstPublicationAlreadyDoneError(
            f"entry {entry_id!r} 在 wp={wp_id} 上已有 current published representation "
            "（判据 B 已成立）—— 本入口只发布**首版**；同 content version 的新代际走 "
            "Task 36 / 77 的 finalize gate，不走这里"
        )

    # ── ④ bundle snapshot（三 typed slot 由被委派方校验）────────────
    bundle_id = await _approved_projection_bundle_id(
        session, contract_id=contract_id
    )
    bundle = await resolution.load_bundle_snapshot(bundle_id)

    # ── ⑤ 磁盘契约（判定已在 ① 的 L5 完成，这里只取对象）──────────
    #
    # 到这里 L5 已经成立（否则 ① 就抛了 `contract_not_reviewed`），因此 `load_contract`
    # 必然成功。仍然包 try：若它在此刻失败，那是**两次读取之间磁盘变了**（并发改动），
    # 属真实异常而非准入不成立 —— 用同一个 error_code 抛出去，诊断里点明这一点。
    try:
        contract = load_contract(contract_id)
    except Exception as exc:
        raise ContractNotReviewedError(
            f"entry {entry_id!r} 的磁盘契约 {contract_id!r} 在 lane 裁决 L"
            f"{_CONTRACT_CRITERION} 通过之后变得不可加载 —— 两次读取之间磁盘被改动: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    expected_revision = await _current_revision(session, wp_id=wp_id)

    return FirstPublicationPlan(
        project_id=project_id,
        wp_id=wp_id,
        entry_id=entry_id,
        contract_id=contract_id,
        provider_module=provider_module,
        document_type=document_type,
        expected_revision=expected_revision,
        bundle=bundle,
        contract=contract,
        authority_model_logical_id=authority_model_logical_id(contract_id),
        actor_id=actor_id,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. stage_instrumented_substrate（Task 4.3 / Requirements 4.1~4.6）
# ═══════════════════════════════════════════════════════════════════════════


def stage_instrumented_substrate(
    *, entry_id: str, staging_dir: Path, contract: Any | None = None
) -> StagedSubstrate:
    """权威模板字节 → instrumentation → OOXML 安全门 → 四项实测入参。

    **暂存期零数据库读写**（Requirement 4.2）：本函数签名里没有 session，因此
    「失败时库一行没动」在构造上成立，不需要靠调用方自觉。

    OOXML 安全门排在产出 staged artifact **之前**（Requirement 4.3~4.5）：B60 的
    `xl/externalLinks/` 必须在这里以 `error_code=ooxml_security_rejected` + 具体
    `gate` 名显式失败，而不是让 `commit` 在事务中途炸出一个看不出来源的错误。

    Raises:
        OoxmlSecurityRejectedError: 安全策略拒绝（携带 `gate` 属性）。
        SubstrateStagingError: instrumentation 抛错或实测入参算不出来。
    """
    from app.services.workpaper_sync.artifacts import (
        load_limits,
        validate_ooxml_artifact,
    )
    from app.services.workpaper_sync.excel_instrumentation import (
        instrument_workbook_bytes,
    )

    provider = _provider_for(entry_id)
    if contract is None:
        contract = provider.load_pilot_contract()

    try:
        source_bytes = provider.read_authoritative_template()
        instrumented = instrument_workbook_bytes(
            source_bytes,
            provider.instrumentation_spec(),
            gate=provider.excel_carrier_gate(),
        )
    except Exception as exc:
        raise SubstrateStagingError(
            f"entry {entry_id!r} 的权威模板 instrumentation 失败: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    # ── 安全门：先落一个**临时**文件给校验器，通过后才移进 staging ────────
    staging_dir.mkdir(parents=True, exist_ok=True)
    probe_path = staging_dir / f"_probe-{instrumented.instrumented_sha256[:12]}.xlsx"
    probe_path.write_bytes(instrumented.instrumented_bytes)
    try:
        report = validate_ooxml_artifact(
            probe_path, document_type="xlsx", limits=load_limits()
        )
    except Exception as exc:
        # 失败即删探针文件 —— staged 目录不得留下被策略拒绝的字节
        probe_path.unlink(missing_ok=True)
        gate = str(getattr(exc, "gate", "") or "")
        raise OoxmlSecurityRejectedError(
            f"entry {entry_id!r} 的 instrumented 字节被 OOXML 策略拒绝"
            f"（gate={gate or 'unknown'}）: {exc}",
            entry_id=entry_id,
            gate=gate,
        ) from exc

    staged_path = staging_dir / f"substrate-{instrumented.instrumented_sha256[:12]}.xlsx"
    probe_path.replace(staged_path)

    try:
        identity_inventory = _observe_identity_inventory(
            instrumented=instrumented, provider=provider
        )
        observed_business_sheets = _observe_business_sheets(
            instrumented_bytes=instrumented.instrumented_bytes, provider=provider
        )
        observed_structure = _observe_structure(
            contract=contract,
            instrumented=instrumented,
            observed_business_sheets=observed_business_sheets,
        )
        observed_dynamic_columns = _observe_dynamic_columns(
            contract=contract, instrumented=instrumented
        )
        observed_dynamic_bindings = _observe_dynamic_bindings(
            contract=contract, instrumented=instrumented
        )
    except FirstPublicationError:
        raise
    except Exception as exc:
        raise SubstrateStagingError(
            f"entry {entry_id!r} 的实测入参现算失败: {type(exc).__name__}: {exc}"
        ) from exc

    return StagedSubstrate(
        entry_id=entry_id,
        staged_path=staged_path,
        source_sha256=instrumented.source_sha256,
        instrumented_sha256=instrumented.instrumented_sha256,
        identity_inventory=identity_inventory,
        observed_structure=observed_structure,
        observed_business_sheets=observed_business_sheets,
        observed_dynamic_columns=observed_dynamic_columns,
        observed_dynamic_bindings=observed_dynamic_bindings,
        ooxml_gates=tuple(getattr(report, "gates", ()) or ()),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 4. publish_first_generation（Task 4.5 / Requirements 5.1~5.8）
# ═══════════════════════════════════════════════════════════════════════════

#: 首版发布**恒为** HTML→OO 方向。写成模块常量而不是参数：这条链的作用是把 HTML 侧
#: 已有的业务 projection materialize 成 canonical OOXML；反方向（OO→HTML）需要
#: durable incoming 作 substrate，那是 Task 26 coordinator 的范围。
FIRST_PUBLICATION_DIRECTION: Final[str] = "html_to_oo"


async def publish_first_generation(
    *,
    session: Any,
    resolution: Any,
    artifacts: Any,
    repository: Any,
    plan: FirstPublicationPlan,
    staged: StagedSubstrate,
    store_payload: Any,
) -> Any:
    """loader → adapter → `ContentMutationService.commit`。**不 commit 事务**。

    链路（每一步都不降级判据）：

    1. :meth:`ExcelEntryDefinitionLoader.load` —— 入参全部来自 ``plan`` 与 ``staged``，
       **零 representation 依赖**（Property 18）；
    2. :func:`build_excel_adapter` —— ``direction`` 恒为
       :data:`FIRST_PUBLICATION_DIRECTION`；
    3. :meth:`ContentMutationService.commit` —— ``adapter`` 必须非空、``contract`` 必须
       非空、``mutation.projection`` 必须非空，三者由 `_assert_authority_shape` 把守。

    Args:
        store_payload: HTML store 里该 entry 的业务载荷（`checklist_responses` 的
            `remark`/`conclusion` 原文）。由宿主读出后传入 —— 本模块不查业务表，
            那会让「暂存期零数据库」的边界变得含糊。
    """
    from app.services.workpaper_sync.adapters.base import SubstrateRole
    from app.services.workpaper_sync.adapters.excel import build_excel_adapter
    from app.services.workpaper_sync.content_mutation import (
        BusinessMutation,
        ContentCommitPlan,
        ContentMutationService,
        ContentSource,
    )
    from app.services.workpaper_sync.excel_entry_gate import (
        AdapterBuild,
        ExcelEntryDefinitionLoader,
    )
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState
    from app.services.workpaper_sync.publish_time_structure_hash import (
        anchors_from_instrumentation_spec,
    )

    provider = _provider_for(plan.entry_id)

    # ── ① FrozenEntryDefinitions（破环点）──────────────────────────
    loader = ExcelEntryDefinitionLoader(session=session, resolution=resolution)
    adapter_build = AdapterBuild(
        adapter_id=plan.contract_id,
        adapter_build_digest=_adapter_build_digest(plan.contract_id),
        document_type=plan.document_type,
        contract_version=str(plan.contract.semantic_version),
    )
    definitions = await loader.load(
        entry_id=plan.entry_id,
        frozen_bundle_id=plan.bundle.bundle_id,
        frozen_bundle_sha256=plan.bundle.bundle_sha256,
        adapter_build=adapter_build,
        identity_inventory=staged.identity_inventory,
        observed_structure=staged.observed_structure,
        observed_business_sheets=staged.observed_business_sheets,
        observed_dynamic_columns=staged.observed_dynamic_columns,
    )

    # ── ② adapter ─────────────────────────────────────────────────
    adapter = build_excel_adapter(
        definitions=definitions,
        binding=_identity_binding(
            provider=provider, staged=staged, contract=plan.contract
        ),
        direction=FIRST_PUBLICATION_DIRECTION,
    )

    # ── ③ business projection = substrate 基线 ⊕ HTML store 覆盖 ────
    if not hasattr(provider, "build_store_projection"):
        raise ProviderCapabilityError(
            f"provider {plan.provider_module!r} 未导出 `build_store_projection` —— "
            "projection-based commit 必须提交业务 projection，不得用权威 OOXML 字节代替"
            "（Requirement 2.11 的反面）"
        )
    store_projection = provider.build_store_projection(
        store_payload, contract=plan.contract
    )
    projection = _overlay_store_on_substrate_baseline(
        adapter=adapter,
        contract=plan.contract,
        substrate=staged.staged_path,
        store_projection=store_projection,
    )

    # ── ④ 唯一业务 commit ─────────────────────────────────────────
    mutation_service = ContentMutationService(
        session=session,
        repository=repository,
        artifacts=artifacts,
        resolution=resolution,
    )
    commit_plan = ContentCommitPlan(
        project_id=plan.project_id,
        wp_id=plan.wp_id,
        entry_id=plan.entry_id,
        source=ContentSource("html"),
        expected_revision=plan.expected_revision,
        bundle=plan.bundle,
        adapter_id=adapter_build.adapter_id,
        adapter_build_digest=adapter_build.adapter_build_digest,
        document_type=plan.document_type,
        substrate_path=staged.staged_path,
        substrate_role=SubstrateRole.published_representation,
        substrate_kind=ArtifactKind.canonical,
        substrate_state=ArtifactState.published,
        actor_id=plan.actor_id,
        # 🔴 contract 必须非空：projection_contract 入口缺 per-entry contract 时
        #    `_assert_authority_shape` 抛 `ContractRequiredError`，那是判据不是障碍。
        contract=plan.contract,
        # 🔴 BP-30：发布时刻的 `structure_hash` 必须与请求时刻观测器同构（见
        #    `compute_structure_hash_from_artifact` 的模块文档）。锚点从 provider 的
        #    instrumentation spec 投影 —— 此刻那份 instrumentation definition 还没发布
        #    （它与 representation 同一次事务才成形），取不到冻结 payload。
        structure_anchors=anchors_from_instrumentation_spec(
            provider.instrumentation_spec()
        ),
        reason="content_commit",
    )
    return await mutation_service.commit(
        plan=commit_plan,
        mutation=BusinessMutation(projection=projection),
        adapter=adapter,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 内部：现取真源（本模块不抄第二份清单）
# ═══════════════════════════════════════════════════════════════════════════


def _delivered_row(entry_id: str) -> Mapping[str, Any]:
    """该 entry 的 `DELIVERED_PER_ENTRY_CONTRACTS` 登记行；未登记即 fail closed。"""
    from app.services.workpaper_sync.adapters.registry import (
        DELIVERED_PER_ENTRY_CONTRACTS,
    )

    rows = [
        row
        for row in DELIVERED_PER_ENTRY_CONTRACTS
        if str(row.get("entry_id") or "").strip() == entry_id
    ]
    if len(rows) != 1:
        raise ProjectionBundleNotProvisionedError(
            f"entry {entry_id!r} 在 `DELIVERED_PER_ENTRY_CONTRACTS` 里有 {len(rows)} 条"
            "登记（需恰 1 条）—— 一个独立 entry 只能有唯一 per-entry 契约"
        )
    return rows[0]


def _provider_for(entry_id: str) -> Any:
    """该 entry 自己的 provider 模块。白名单由 registry 单点把守，本模块不放宽。"""
    import importlib

    from app.services.workpaper_sync.adapters import registry as registry_module

    module_path = str(_delivered_row(entry_id)["provider_module"])
    if module_path not in registry_module._ALLOWED_PROVIDER_MODULES:
        raise ProviderCapabilityError(
            f"entry {entry_id}: provider_module {module_path!r} 不在 registry 白名单内"
            " —— 不得从登记表任意 import"
        )
    return importlib.import_module(module_path)


def _adapter_build_digest(adapter_id: str) -> str:
    """adapter 实现身份 digest。复用 `writer_migration` 的同名算法，不另造一份。"""
    from app.services.workpaper_sync.writer_migration import _adapter_build_digest as impl

    return impl(adapter_id)


async def _current_revision(session: Any, *, wp_id: uuid.UUID) -> int:
    """读当前 business content revision（**不推进**、不加 advisory lock）。

    与 `AuthoritativeContentWriter.current_revision` / `wp_html_save` 的 Step 2b 同形：
    这里只做「早失败 + 可读诊断」，真正的并发裁决是 `commit()` 事务内的 CAS。
    """
    import sqlalchemy as sa

    row = (
        await session.execute(
            sa.text(
                "SELECT COALESCE(content_revision, 0) FROM working_paper WHERE id = :wp"
            ),
            {"wp": str(wp_id)},
        )
    ).scalar_one_or_none()
    return int(row or 0)


async def _approved_projection_bundle_id(
    session: Any, *, contract_id: str
) -> uuid.UUID:
    """按 authority model logical_id 定位该 entry 的 approved projection bundle id。

    判据与 `observe_lane_supply` 的判据 A 同源（同一 SQL 常量），因此「A 为真但这里取
    不到」不可能发生 —— 两处若各写一份 SQL 就会出现那种自相矛盾的状态。
    """
    import sqlalchemy as sa

    from app.services.workpaper_sync.models import AuthorityModel
    from app.services.workpaper_sync.projection_lane_registry import (
        _SQL_CRITERION_A,
        authority_model_logical_id,
    )

    row = (
        await session.execute(
            sa.text(_SQL_CRITERION_A),
            {
                "authority_logical_id": authority_model_logical_id(contract_id),
                "projection_authority_type": AuthorityModel.projection_contract.value,
                "approved": "approved",
            },
        )
    ).first()
    if row is None:  # pragma: no cover — 判据 A 已在 resolve_plan 里为真
        raise ProjectionBundleNotProvisionedError(
            f"contract {contract_id!r} 的 approved projection bundle 消失了 —— "
            "判据 A 与 bundle 定位使用同一 SQL，这里取空说明期间发生了并发撤销"
        )
    return row.bundle_id


# ═══════════════════════════════════════════════════════════════════════════
# 内部：四项实测入参的现算
# ═══════════════════════════════════════════════════════════════════════════


def _observe_identity_inventory(*, instrumented: Any, provider: Any) -> Any:
    """从 instrumented 字节现算 identity inventory 并投影成类型化对象。

    锚点全部取自 provider 的冻结常量与 instrumentation 产出，**不猜**：
    `uuid_sheet_id` 用 instrumentation 当时记下的 sheetId（sheetId 不随展示名变化，
    是用户改 sheet 名后唯一还能定位的锚点）。
    """
    from app.services.excel_structure_fingerprint import (
        GT_SYNC_SHEET_NAME,
        identity_inventory,
    )
    from app.services.workpaper_sync.excel_entry_gate import parse_identity_inventory

    spec = provider.instrumentation_spec()
    raw = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=getattr(spec, "table_name", None)
        or getattr(provider, "TABLE_NAME", None),
        uuid_column_letter=getattr(spec, "uuid_column", None)
        or getattr(provider, "UUID_COL", None),
        # 🔴 **刻意不传** `uuid_sheet_id` / `uuid_sheet_name`。
        #
        # `identity_inventory` 的 `winner` 按 `("sheet_id", "sheet_name", "table_sheet")`
        # 取**首个**能定位到 UUID 列的候选。传了 sheetId 它就赢，`resolved_sheet_by` 落成
        # `"sheet_id"`，而 `assert_identity_inventory_usable` 要求恰为 `"table_sheet"` ——
        # Task 5 的真实 OO 9.4 probe 已把 `sheet_id` 与 sheet 展示名两个锚点**证伪**
        # （改名/复制后不保留）。首版实测：传 sheetId 时 H1 与 D2 双双被
        # `excel_entry_identity_inventory_invalid` 拒。
        #
        # 唯一存活的锚点是 Excel Table ↔ sheet 关联（`expected_table` 那一路），它由
        # `xl/tables/tableN.xml` 与 sheet 的 rel 绑定，改名不动、复制保留。
        metadata_sheet=GT_SYNC_SHEET_NAME,
        defined_name_prefix=str(getattr(spec, "defined_name_prefix", None) or "GT_"),
    )
    return parse_identity_inventory(raw)


def _observe_business_sheets(
    *, instrumented_bytes: bytes, provider: Any
) -> tuple[str, ...]:
    """实测业务 sheet 枚举 —— 平台隐藏 metadata sheet 必须被显式排除。

    排除项取自 `excel_entry_gate` 的真源常量，不在本模块写死 `_GT_SYNC`
    （Requirement 6.13 / 6.17 后半句：隐藏元数据 sheet 必须被业务枚举排除）。
    """
    from app.services.excel_structure_fingerprint import structure_fingerprint
    from app.services.workpaper_sync.excel_entry_gate import (
        exclude_metadata_sheets,
    )

    fingerprint = structure_fingerprint(instrumented_bytes)
    return tuple(exclude_metadata_sheets(fingerprint.sheet_names))


def _observe_structure(
    *,
    contract: Any,
    instrumented: Any,
    observed_business_sheets: Sequence[str],
) -> tuple[tuple[str, str, str, str], ...]:
    """实测受管结构清册 `(sheet_key, table_key, stable_field_key, locator)`。

    ═══ 为什么不是「把 declared 原样抄一遍」════════════════════════════════

    抄一遍会让 `assert_no_structure_drift` 变成恒真重言式（假绿第③源）。这里的做法是：
    对契约声明的每个字段，**在 instrumented 工作簿里核实它的受管 sheet 真的存在**且
    该 sheet 已进入业务枚举；核实通过才发出与声明相同的 locator，核实不通过则发出一个
    带 `MISSING:` 前缀的 locator —— 于是漂移会被 `first_structure_drift` 抓到并指名
    首个不一致位置。

    受管 sheet 的定位锚点是 instrumentation 当时记下的展示名（它同时被写进
    `_GT_SYNC` 与 defined name，两侧一致才算 identity 成立）。
    """
    from app.services.workpaper_sync.contracts import declared_structure_inventory

    business = set(observed_business_sheets)
    managed_sheet = str(instrumented.managed_sheet_name_at_instrumentation)
    managed_sheet_present = managed_sheet in business

    rows: list[tuple[str, str, str, str]] = []
    for sheet_key, table_key, stable_key, locator in declared_structure_inventory(
        contract
    ):
        if managed_sheet_present:
            rows.append((sheet_key, table_key, stable_key, locator))
        else:
            rows.append(
                (
                    sheet_key,
                    table_key,
                    stable_key,
                    f"MISSING:{managed_sheet}:{locator}",
                )
            )
    return tuple(sorted(rows))


def _observe_dynamic_columns(
    *, contract: Any, instrumented: Any
) -> Mapping[str, tuple[tuple[str, str], ...]]:
    """实测动态列的 `(label, key)` 对；契约没声明 `dynamic_columns` 的表不出现。

    key 一律由 :func:`dynamic_column_stable_keys` 按 `{slot}_{seq}` 派生 —— 该函数的
    签名里**没有** label 入参，因此「重命名列改变了 key」在构造上不可能发生
    （Property 22 的实现方式，不是它的检查方式）。

    label 只从 instrumentation 的 defined name 引用里取，且只进 observed 一侧。
    """
    from app.services.workpaper_sync.excel_entry_gate import (
        dynamic_column_stable_keys,
    )

    out: dict[str, tuple[tuple[str, str], ...]] = {}
    for sheet in contract.sheets:
        for table in sheet.tables:
            if table.dynamic_columns is None:
                continue
            count = _dynamic_column_count(table.dynamic_columns, table_key=table.table_key)
            keys = dynamic_column_stable_keys(slot=table.table_key, count=count)
            labels = _dynamic_column_labels(
                instrumented=instrumented, table_key=table.table_key, count=count
            )
            out[table.table_key] = tuple(zip(labels, keys))
    return out


def _observe_dynamic_bindings(
    *, contract: Any, instrumented: Any
) -> Mapping[str, Mapping[str, str]]:
    """实测 `table_key` → (`{slot}_{seq}` → Excel 列标)。

    ═══ 为什么委派而不自己算 ════════════════════════════════════════════════════

    `published_identity_observer.observe_dynamic_column_bindings` 是这件事的生产实现，
    它与 `observe_dynamic_columns`（label 那一份）**共用同一段物理列跨度推导**
    （`_dynamic_spans`），因此「键数与列数不等」「两个键绑同一列」在构造上不可能出现。
    在这里另写一份的后果不是更安全，而是两侧任一被短路都不改变行为 ⇒ 变异判 GREEN。

    `physical_sheet_by_key` 的取值：instrumentation 当时记下的受管 sheet 展示名。
    契约含多张 sheet 时 fail closed —— instrumentation 只记了**一个**受管 sheet 名，
    拿它去填多个 sheet_key 等于把「不知道」伪装成「都一样」。
    """
    from app.services.excel_structure_fingerprint import structure_fingerprint
    from app.services.workpaper_sync.published_identity_observer import (
        observe_dynamic_column_bindings,
    )

    declared = [
        sheet.sheet_key
        for sheet in contract.sheets
        for table in sheet.tables
        if table.dynamic_columns is not None
    ]
    if not declared:
        return {}

    sheet_keys = [sheet.sheet_key for sheet in contract.sheets]
    if len(sheet_keys) != 1:
        raise SubstrateStagingError(
            f"契约 {contract.contract_id!r} 声明了 {len(sheet_keys)} 张受管 sheet "
            f"{sheet_keys}，而 instrumentation 只记下一个受管 sheet 展示名 —— "
            "动态列绑定的物理 sheet 无从确定，不得拿同一个名字填所有 sheet_key"
        )

    managed_sheet = str(instrumented.managed_sheet_name_at_instrumentation)
    return observe_dynamic_column_bindings(
        contract=contract,
        fingerprint=structure_fingerprint(instrumented.instrumented_bytes),
        physical_sheet_by_key={sheet_keys[0]: managed_sheet},
    )


def _dynamic_column_count(spec: Any, *, table_key: str) -> int:
    """动态列的列数 —— 从 `source_ref` 的 A1 列跨度派生。

    🔴 `DynamicColumnSpec` 只有 ``identity`` 与 ``source_ref`` 两个字段，**没有**
    ``count``。首版实现写成 ``getattr(spec, "count", 0)`` 时 G7 的
    ``minority_financials`` 实测得 0（真值是 10）—— 一个 `getattr` 默认值把「读错字段」
    静默降级成「这张表没有动态列」，而下游 `assert_dynamic_columns_label_independent`
    对空序列无话可说，于是整条动态列判据变成空转。故这里**不给默认值**：读不出
    `source_ref` 就抛。

    列数 = A1 区间的列跨度（`C62:L62` ⇒ C..L ⇒ 10 列），行跨度不参与 —— 动态的是
    「横向展开多少家公司/单位」，不是纵向行数。
    """
    from app.services.workpaper_sync.contracts import parse_a1_range

    source_ref = str(getattr(spec, "source_ref", "") or "").strip()
    if not source_ref:
        raise SubstrateStagingError(
            f"table {table_key!r} 声明了 dynamic_columns 但 source_ref 为空 —— "
            "动态列数只能由 source_ref 的 A1 列跨度派生，缺它即无从现算"
        )
    # `source_ref` 形如 `源xlsx!附注披露信息（国企）!C62:L62`：取最后一段做 A1 区间。
    # sheet 展示名里含 `!` 的极端情形下取最后一段仍正确（区间本身不含 `!`）。
    a1 = source_ref.rsplit("!", 1)[-1].strip()
    col_from, _row_from, col_to, _row_to = parse_a1_range(
        a1, location=f"dynamic_columns[{table_key}].source_ref"
    )
    low, high = sorted((_column_index_of(col_from), _column_index_of(col_to)))
    return high - low + 1


def _column_index_of(column: str) -> int:
    """列字母 → 1-based 序号。与 `contracts._column_index` 同算法（那是私有名）。"""
    index = 0
    for char in column.upper():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


def _overlay_store_on_substrate_baseline(
    *, adapter: Any, contract: Any, substrate: Path, store_projection: Any
) -> Any:
    """首版业务 projection = **substrate 基线** ⊕ HTML store 覆盖。

    ═══ 为什么首版不能只提交 store projection ═══════════════════════════════════

    实测（H1，`H1-8-rows` 全库 0 行）：只交 store projection 时
    `_assert_roundtrip_equivalent` 报「反读出未提交的受管字段
    `disposal_check_rows/GTROW-H18-0013/seq` …（共 15 个）」。

    根因不是 materialize 写错了，而是**那 15 个 `seq` 本来就在权威模板里** —— H1-8 的
    A13:A27 预印了序号 1..15，`seq` 的 contract mode 是 `auto_source`（表单脚手架，不是
    审计师录入项）。materialize 对不在 projection 里的行不写任何东西，于是模板值原样留
    在 staged artifact 上，extract 自然读得到它，而 projection 里没有对端 ⇒ 判「多出字段」。

    正确的业务语义是：**首版记录的是「这张表当前的内容」**，而不是「store 里有什么」。
    空 store 的固定资产减少检查表，在 OO 里就该显示那张印着序号 1..15 的空白表单 ——
    那是审计师期望看到的纸质表形态，不是脏数据。

    故这里先 `adapter.extract(staged substrate)` 取基线（= 权威模板经 instrumentation 后
    的当前内容），再把 store projection 逐字段叠加在上面（**store 侧优先**：HTML 已录入
    的值是更新的业务事实）。两侧都没有的字段不出现。

    🔴 只在**首版**这么做。后续代际的 substrate 是上一版 published representation，
    基线已经包含全部业务内容，再叠加一次是空操作；而 OO→HTML 方向的 substrate 是
    durable incoming，那条路必须走 Task 26 的三方 merge，不得用本函数的「后者覆盖前者」
    代替 —— 那正是 design「明确拒绝的方案」第 5 条（last-write-wins）。
    """
    from app.services.workpaper_sync.adapters.base import Projection

    baseline = adapter.extract(artifact=substrate, contract=contract)

    values = dict(baseline.values)
    for key, field in store_projection.values.items():
        # 🔴 只丢「基线没有该键 **且** store 侧取值为 None」的字段 —— 那既不是业务事实、
        #    也不是清空动作，是 provider 为固定形状的矩阵吐出的**占位**。
        #
        #    实测（G7，`minority_financials` 是 10×10 矩阵）：`build_store_projection`
        #    吐出 **100 个显式 None** 的 amount 字段，而 substrate 上那 100 格本来是空的
        #    （`adapter.extract` 对空格**不产键**，基线只有 5 个值）。照原样叠加的后果是
        #    materialize 把 None 写成 `0`，反读回来 100 处全部 `None → 0` 不等值，
        #    `_assert_roundtrip_equivalent` 判 `roundtrip_projection_mismatch`。
        #
        #    判据必须带「基线没有该键」这一半：基线**有值**而 store 给 None 是审计师
        #    「清空这一格」的真实动作，那一种必须保留、必须写下去。少了这一半就会把
        #    清空静默吞掉 —— 那比多写一个 0 更贵。
        if field.value is None and key not in baseline.values:
            continue
        values[key] = field

    # row_keys 按表合并：基线的物理行序 + store 新增行（保序、去重）
    row_keys: dict[str, tuple[str, ...]] = {}
    for table_key in {*baseline.row_keys, *store_projection.row_keys}:
        merged: list[str] = []
        for source in (
            baseline.row_keys.get(table_key, ()),
            store_projection.row_keys.get(table_key, ()),
        ):
            for key in source:
                if key not in merged:
                    merged.append(key)
        row_keys[table_key] = tuple(merged)

    return Projection(
        contract_id=str(store_projection.contract_id),
        semantic_version=str(store_projection.semantic_version),
        document_type=str(store_projection.document_type),
        values=values,
        row_keys=row_keys,
    )


def _row_bearing_table_key(*, contract: Any, provider: Any) -> str:
    """行身份表的 `table_key` —— 从**冻结契约的结构**派生，与 provider 常量双向锁死。

    ═══ 为什么不直接读 `provider.ROWS_TABLE_KEY` ════════════════════════════════

    那是个**只有部分 provider 遵守的命名约定**，不是真源。实测 4 个 pilot：

    | provider | `ROWS_TABLE_KEY` |
    |---|---|
    | `pilot_simple_checklist`（B60） | `hour_budget_rows` |
    | `pilot_d2_large_json` | `receivable_detail_rows` |
    | `pilot_h1_grouped_dynamic` | `disposal_check_rows` |
    | `pilot_g7_two_level_dynamic` | **没有这个常量** —— 它有两张表，导出的是 `MATRIX_TABLE_KEY` / `RECORD_TABLE_KEY` |

    于是 `str(provider.ROWS_TABLE_KEY)` 对 G7 直接 `AttributeError`，首版链在 adapter
    装配处断掉（实测 G7 止步 5/10）。

    契约侧有真源：**恰有一张表**同时满足「`row_identity` 声明非空」与「有字段的
    `cell.row_from == "row_identity"`」。实测 4/4 各得 1 张，且与三个声明了常量的
    provider 逐一相符（G7 得 `former_subsidiary_basic`；它另一张 `minority_financials`
    是 100 个 static 格 + 动态列，不承载行身份）。

    provider 声明了常量时**双向锁死**：不一致即抛，而不是任选一侧 —— 两侧不一致时
    静默取一侧会让「契约改了表名而 provider 没跟」变成无声的错行写入。
    """
    candidates = [
        str(table.table_key)
        for sheet in contract.sheets
        for table in sheet.tables
        if getattr(table, "row_identity", None) is not None
        and any(
            getattr(getattr(field, "cell", None), "row_from", None) == "row_identity"
            for field in table.fields
        )
    ]
    if len(candidates) != 1:
        raise ProviderCapabilityError(
            f"契约 {contract.contract_id!r} 里满足「row_identity 声明非空 ∧ 有 "
            f"row_from=row_identity 字段」的表有 {len(candidates)} 张 {candidates}"
            " —— 需恰 1 张才能确定行身份表；0 张说明契约没声明动态行，"
            "多张说明一个受管 sheet 上有两套行身份，identity 绑定无法二选一"
        )
    derived = candidates[0]
    declared = str(getattr(provider, "ROWS_TABLE_KEY", "") or "").strip()
    if declared and declared != derived:
        raise ProviderCapabilityError(
            f"provider 声明 ROWS_TABLE_KEY={declared!r}，但契约 "
            f"{contract.contract_id!r} 的行身份表是 {derived!r} —— 两侧不一致时"
            "不得静默取一侧：那会把「契约改了表名而 provider 没跟」变成无声的错行写入"
        )
    return derived


def _identity_binding(
    *, provider: Any, staged: StagedSubstrate, contract: Any
) -> Any:
    """运行态 identity 绑定 —— 全部取自 provider 冻结常量与 instrumentation 实测产出。

    🔴 `metadata_sheet` 取真源常量而不是写死 ``"_GT_SYNC"``：那个名字同时被
    `excel_instrumentation` 写进工作簿、被 `excel_entry_gate` 从业务枚举里排除、被
    契约的 `identity_carriers` 声明；在这里抄第四份的话，改名时三处会红、这里静默不红。
    """
    from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME
    from app.services.workpaper_sync.excel_extract import ExcelIdentityBinding

    spec = provider.instrumentation_spec()
    inventory = staged.identity_inventory
    return ExcelIdentityBinding(
        table_name=str(
            getattr(spec, "table_name", None) or getattr(provider, "TABLE_NAME", "")
        ),
        uuid_column=str(
            getattr(spec, "uuid_column", None) or getattr(provider, "UUID_COL", "")
        ),
        table_key=_row_bearing_table_key(contract=contract, provider=provider),
        metadata_sheet=GT_SYNC_SHEET_NAME,
        defined_name_prefix=str(
            getattr(spec, "defined_name_prefix", None) or "GT_"
        ),
        # 首版没有任何已删除行 —— 墓碑集合恒空，不是「忘了填」。
        tombstoned_row_keys=(),
        # 🔴 值必须是 **Excel 列标**，不是 label。首版实现写的是
        #    `{key: label for label, key in staged.observed_dynamic_columns[...]}`，
        #    G7 实测炸在 `ValueError: 'minority_financials#1' is not a valid column
        #    name`。前三个 entry 的契约都没声明 dynamic_columns ⇒ 字典恒空 ⇒ 这个错形
        #    在三个 entry 上完全不可见（空集上恒真的又一种形态）。
        dynamic_column_columns={
            table_key: dict(mapping)
            for table_key, mapping in staged.observed_dynamic_bindings.items()
        },
    )


def _dynamic_column_labels(
    *, instrumented: Any, table_key: str, count: int
) -> tuple[str, ...]:
    """动态列的实测 label。

    instrumentation 不改可见表头，故 label 取自 `defined_name_refs` 里该表的受管区域
    声明顺序；取不到时用稳定占位（label 只进 observed 一侧，不参与 identity）。
    """
    refs = dict(getattr(instrumented, "defined_name_refs", {}) or {})
    ordered = [name for name in sorted(refs) if table_key.upper() in name.upper()]
    labels: list[str] = []
    for seq in range(1, count + 1):
        labels.append(ordered[seq - 1] if seq - 1 < len(ordered) else f"{table_key}#{seq}")
    return tuple(labels)


__all__ = [
    "FIRST_PUBLICATION_DIRECTION",
    "FirstPublicationPlan",
    "StagedSubstrate",
    "resolve_plan",
    "stage_instrumented_substrate",
    "publish_first_generation",
    # 异常
    "FirstPublicationError",
    "ProjectionBundleNotProvisionedError",
    "FirstPublicationAlreadyDoneError",
    "ContractNotReviewedError",
    "OoxmlSecurityRejectedError",
    "SubstrateStagingError",
    "ProviderCapabilityError",
]
