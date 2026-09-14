# -*- coding: utf-8 -*-
"""通用 **tagged-SDT** Word engine —— materialize / extract / rematerialize。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 59
Requirements: 2.3, 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.9, 7.10, 8.10,
8.11, 9.1, 9.8, 9.9, 9.10, 14.16
Properties: **P28**（immutable definition 漂移 fail closed）/ **P30**（Word 只认
tagged SDT）/ **P31**（Word-only 正文保留）/ **P32**（Word 多实例异值冲突）/
**P34**（SDT 丢失不降级）/ **P65**（projection 与同 revision representation 等值）/
**P67**（upgrader 先 candidate、approved bundle 后 finalize）/ **P71**（evidence 随
环境/runner/bundle 变化失效）

═══ 一、载体只能是 Task 6 真实通过的那三个 ═══

真源是 `backend/data/onlyoffice_word_sdt_carrier_contract.json`，本模块**不复制**其中
任何清单，一律经 `contracts.load_word_carrier_gate()` 读取。2026-08-24 真实 OO 9.4.0-129
的裁决：

===============================================  ==========  ==================
载体 / 锚点                                       裁决        可进 engine
===============================================  ==========  ==================
`field_sdt_inline`（run 级 SDT，26/26 保留）        passed      是
`field_sdt_block`（block 级 SDT，17/17 层级保留）   passed      是
`sdt_external_body`（SDT 外自由正文）              passed      是
`cell_level_field_sdt_tag_carrying_row_uuid`      passed      是（行身份）
`row_sdt`（row 级 SDT 包 `w:tr`）                  **failed**  **否**
锚点 `w_tag`                                      passed      是（唯一）
锚点 `alias_display_name` / `sdt_id`               passed      否（不唯一/可改名）
锚点 `paragraph_index` / `run_index`               **failed**  否
===============================================  ==========  ==================

`row_sdt` 的失败是硬事实：OO 9.4 在**首次序列化时**就把 `w:tbl` 下的 `w:sdt` 拆掉
（baseline 格 —— 只打开 + 一次净零编辑 + forcesave —— 已经 0 个 row tag），`w:tr`
原样留下但包装与 `w:tag` 一并消失。所以 Requirement 7.2 的行身份在本模块里由**单元格内
inline field SDT 的 tag** 承载（`gt:field:{contract}:rows/{row_uuid}/{column}`），
`contracts._parse_field` 已把「行域 docx 字段的 sdt_tag 必须含 `{row_uuid}`」写成硬判据。

═══ 二、为什么本模块不 import `word_sdt_fingerprint.parse_field_tag` ═══

🔴 那两个函数（`parse_field_tag` / `parse_row_tag`）认的是 **`gtsdt/v1/...` 旧方案**，
而 Task 6 探针真正注入、并且 `contracts.py` 强校验的是 **`gt:field:{contract}:{key}`**。
拿它们解析真实 tag 会对每一个 tag 都返回 `None` ⇒ 表现成「文档里没有任何受管字段」，
而这正是本 spec 记的「最贵的一类」fail-open：四层静态检查全绿，只有真跑才暴露。

因此本模块的 tag 形态**单一真源**是 `contracts._SDT_TAG_RE`（:data:`SDT_TAG_PATTERN`
直接指向同一个对象，守卫用 `is` 断言同一性 —— 复制一份正则会让任一侧改动不打红）。
`word_sdt_fingerprint` 的其余部分（`structure_fingerprint` / `SdtNode` /
`body_preservation_report`）是方案无关的**事实采集**，全部复用。

═══ 三、extract 只认 tag，没有 paragraph/regex fallback ═══

「没有 fallback」写成注释是不可验证的。本模块给出两条**结构判据**：

1. :data:`FORBIDDEN_SDT_LOCATOR_ATTRS` —— `SdtNode` 上四个伪锚点属性
   （`w_id` / `alias` / `body_child_index` / `run_count`）。守卫在**本模块 AST** 上
   断言这些属性名一次都没被读取；把它们中任何一个用进定位逻辑都会打红。
2. :data:`FORBIDDEN_FALLBACK_SYMBOLS` —— 旧方案 tag 解析器与段落计数字段。守卫在 AST
   的 import/attribute 图上断言零引用。

两条都落在真实 AST 上，而不是「源码里是否出现某个字符串」（后者改个别名就绕过，
是假绿第②源）。

═══ 四、缺 approved bundle 时只能离线验证 candidate ═══

Task 59 不为任何 entry 发布 contract/bundle（那是 Task 60 与 Tasks 62–64）。因此
engine 有两个**封闭**模式（:class:`WordEngineMode`）：

* `bundle_bound` —— 必须给 frozen `DefinitionBundleSnapshot`，并委派 Task 13 的
  `assert_bundle_usable` / `assert_authority_model_contract_pairing` /
  `assert_contract_identity_frozen`（**不重写**：重写会让任一侧被短路都不改变行为）。
* `offline_candidate_validation` —— 无 bundle，只允许读/校验与写 candidate 命名空间。
  :meth:`WordEngineBinding.assert_may_publish` 在此模式下**恒抛**
  :class:`WordApprovedBundleRequiredError`，于是「离线态偷偷发布 representation」在
  类型上就不可达。

本模块自身没有任何发布面：不持 session、不持 repository、不切 pointer、不动 revision。
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass, field as dataclass_field
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.word_sdt_fingerprint import (
    DocumentFingerprint,
    WordFingerprintError,
    body_preservation_report,
    normalise_text,
    structure_fingerprint,
)
from app.services.workpaper_sync.adapters.base import (
    FieldValue,
    MaterializeResult,
    Projection,
    SubstrateRole,
    UnmanagedRegionDriftError,
    UnmanagedRegionReport,
    assert_substrate_usable,
)
from app.services.workpaper_sync.adapters.registry import (
    assert_authority_model_contract_pairing,
    assert_bundle_usable,
    assert_contract_identity_frozen,
)
from app.services.workpaper_sync.conflicts import (
    ConflictKind,
    ConflictRecord,
    FieldLocator,
    FieldSource,
    ProtectionPolicy,
    SchemaAnomalyKind,
    SuggestedAction,
    ValueEnvelope,
)
from app.services.workpaper_sync.merge import (
    StructuralAnomaly,
    WordInstance,
    WordInstanceObservation,
    reduce_word_instances,
)
from app.services.workpaper_sync.contracts import (
    ROW_UUID_PLACEHOLDER,
    CarrierGate,
    FieldMode,
    FieldSpec,
    SyncContract,
    ValueType,
    load_word_carrier_gate,
)
# 🔴 tag 形态的**单一真源**。见模块 docstring 第二节：不复制正则、不换名字，
#    守卫用 `SDT_TAG_PATTERN is contracts._SDT_TAG_RE` 断言同一对象。
from app.services.workpaper_sync.contracts import _SDT_TAG_RE as SDT_TAG_PATTERN
from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import (
    ArtifactKind,
    ArtifactState,
    SyncDomainError,
)
from app.services.workpaper_sync.ooxml_security import validate_ooxml_artifact
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot

__all__ = [
    "WORD_DOCUMENT_PART",
    "WORD_DOCUMENT_TYPE",
    "SDT_TAG_PATTERN",
    "ROW_SCOPE_SEGMENT",
    "FORBIDDEN_SDT_LOCATOR_ATTRS",
    "FORBIDDEN_FALLBACK_SYMBOLS",
    "READ_GATE_ORDER",
    "WORD_ENGINE_FAILURE_CODES",
    "WORD_ONLY_ASPECTS",
    "WordEngineError",
    "WordCarrierBlockedError",
    "WordApprovedBundleRequiredError",
    "WordTagMissingError",
    "WordTagUnregisteredError",
    "WordTagInstanceCountError",
    "WordTagHierarchyDriftError",
    "WordRowIdentityMissingError",
    "UnmanagedRegionDriftError",
    "WordManagedProjectionMismatchError",
    "WordEngineMode",
    "WordSdtTagRef",
    "parse_sdt_tag",
    "format_sdt_tag",
    "WordEngineBinding",
    "WordSdtInstance",
    "WordRowInventory",
    "WordExtractOutcome",
    "extract_word_projection",
    "WordMaterializeOutcome",
    "materialize_word_projection",
    "verify_word_only_regions",
    "WordVerificationBundle",
    "verify_word_before_commit",
    "materialize_word_for_editing",
    "rematerialize_word_merged_projection",
]

# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量
# ═══════════════════════════════════════════════════════════════════════════

WORD_DOCUMENT_TYPE: Final[str] = "docx"

#: 唯一被 instrumentation / materialize 改写的 OOXML 部件。其余部件（批注、修订、
#: 图片、页眉页脚、styles、numbering…）一律逐字节复制 —— design §Word materialize
#: 「SDT 外段落、批注、修订、图片和表格保留」。
WORD_DOCUMENT_PART: Final[str] = "word/document.xml"

#: 行域 stable key 的固定首段（`rows/{row_uuid}/{column_key}`）。
ROW_SCOPE_SEGMENT: Final[str] = "rows"

#: `SdtNode` 上**禁止**参与定位的伪锚点属性（Task 6 逐条证伪/降级）。
#:
#: * `w_id` —— 同一 stable key 的两个实例被注入了**相同** `w:id` 且 OO 原样接受 ⇒ 不唯一；
#: * `alias` —— 可被审计师在 UI 改名的展示串；
#: * `body_child_index` —— 文首插 2 段后整体位移（`paragraph_index` 的实现形态）；
#: * `run_count` —— 注入 3 run 经 OO 一次往返变 2 run。
#:
#: 守卫在本模块 AST 上断言这些名字一次都没被读。
FORBIDDEN_SDT_LOCATOR_ATTRS: Final[frozenset[str]] = frozenset(
    {"w_id", "alias", "body_child_index", "run_count"}
)

#: 结构上禁止出现在本模块里的符号（旧 tag 方案解析器 + 段落计数）。
FORBIDDEN_FALLBACK_SYMBOLS: Final[frozenset[str]] = frozenset(
    {"parse_field_tag", "parse_row_tag", "paragraph_count", "outside_sdt_blocks"}
)

#: Word-only 保留报告里必须逐项判定的 aspect。取自 `word_sdt_fingerprint`
#: 的 `PRESERVATION_ASPECTS`，但**去掉** `row_uuid_set` —— 那一格由旧 `gtsdt/v1`
#: 解析器计算，在 `gt:` 方案下两侧恒为空集 ⇒ 恒真（假绿第⑥源「空集恒等价」）。
#: 行身份保留由本模块自己的 :func:`_row_uuid_index` 判定，见
#: :func:`verify_word_only_regions`。
WORD_ONLY_ASPECTS: Final[tuple[str, ...]] = (
    "sdt_tag_set",
    "sdt_hierarchy",
    "outside_sdt_text",
    "table_shape",
    "protected_parts",
    "managed_row_identity",
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常（每条拒绝理由一个 error_code —— 合并会让较早分支永久不可达）
# ═══════════════════════════════════════════════════════════════════════════


class WordEngineError(SyncDomainError):
    error_code = "word_sdt_engine_failed"


class WordCarrierBlockedError(WordEngineError):
    """契约/文档用到了 Task 6 证伪的载体或锚点（Requirement 7.1 / 7.2）。"""

    error_code = "word_sdt_carrier_blocked"


class WordApprovedBundleRequiredError(WordEngineError):
    """离线模式请求了只属于 bundle-bound 模式的能力（发布 / 运行态 substrate）。

    与 :class:`WordCarrierBlockedError` 分开：前者是「这个 entry 还没 approved
    bundle」（Task 60 / 62–64 承接），后者是「载体本身被证伪」（design 换载体）。
    合并成一个 code 之后，缺 bundle 的分支会被载体分支遮蔽 ⇒ 变异恒 GREEN。
    """

    error_code = "word_approved_bundle_required"


class WordTagMissingError(WordEngineError):
    """contract 声明的 tag 在文档里找不到（Requirement 7.8 / Property 30 / 34）。

    这是「tag retention 失败」的生产形态：operation 必须 error、incoming 保留、
    HTML 不变，**不得**回退段落索引。
    """

    error_code = "word_sdt_tag_missing"


class WordTagUnregisteredError(WordEngineError):
    """文档里出现了 `gt:` 形态但 contract 未登记 / contract 段不符的 tag。"""

    error_code = "word_sdt_tag_unregistered"


class WordTagInstanceCountError(WordEngineError):
    """实例计数与 contract 的 `instances` 声明不符（Requirement 7.10「字段实例计数」）。

    与 :class:`WordTagMissingError` 分开：0 个是「丢了」，`instances="one"` 却有 2 个
    是「模板漂移/被复制」。共用 code 时后者永久被前者遮蔽。
    """

    error_code = "word_sdt_instance_count_unexpected"


class WordTagHierarchyDriftError(WordEngineError):
    """层级漂移：block 内字段跑到 block 外，或行域字段跑到表格外。"""

    error_code = "word_sdt_hierarchy_drift"


class WordRowIdentityMissingError(WordEngineError):
    """要写的行 UUID 在文档里不存在（不得按行号猜，Requirement 7.2）。"""

    error_code = "word_sdt_row_identity_missing"


class WordManagedProjectionMismatchError(WordEngineError):
    """反读的受管 projection 与期望不等值（Requirement 8.11 / Property 65）。"""

    error_code = "word_managed_projection_mismatch"


#: 本模块可能抛出的**全部**失败 kind。守卫据它断言「每类各自真触发一次、集合基数
#: 等于登记数、且 error_code 互不相同」—— 比「每类各测一遍」强：后者在两类被合并成
#: 同一 code 时**全部仍绿**。
WORD_ENGINE_FAILURE_CODES: Final[tuple[str, ...]] = (
    WordCarrierBlockedError.error_code,
    WordApprovedBundleRequiredError.error_code,
    WordTagMissingError.error_code,
    WordTagUnregisteredError.error_code,
    WordTagInstanceCountError.error_code,
    WordTagHierarchyDriftError.error_code,
    WordRowIdentityMissingError.error_code,
    # 🔴 Word-only 区域漂移**不**新造类型：单一真源是 Task 13 的
    #    `UnmanagedRegionReport.assert_equivalent()`。首轮曾在此声明过一个
    #    `WordOnlyRegionDriftError`，可达性守卫立刻抓出它**从未被抛出**（登记了
    #    `word_only_region_drift`，实测触发的是 `adapter_unmanaged_region_drift`）——
    #    正是「登记了一个永久不可达的 kind」这种假绿，已按判据删掉那个死类型。
    UnmanagedRegionDriftError.error_code,
    WordManagedProjectionMismatchError.error_code,
)


# ═══════════════════════════════════════════════════════════════════════════
# 2. tag 域
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordSdtTagRef:
    """一个已解析的 `w:tag`。

    Attributes:
        kind: `field` | `block`（封闭于 :data:`SDT_TAG_PATTERN`）。
        contract_id: tag 内自带的 contract 段 —— 与 frozen contract 双向锁死。
        stable_key: 契约里的 stable field key（行域已实例化为具体 row_uuid）。
        row_uuid: 行域 tag 的行身份；非行域为 None。
    """

    kind: str
    contract_id: str
    stable_key: str
    row_uuid: str | None

    @property
    def raw(self) -> str:
        return f"gt:{self.kind}:{self.contract_id}:{self.stable_key}"

    @property
    def row_scoped(self) -> bool:
        return self.row_uuid is not None


def parse_sdt_tag(tag: str) -> WordSdtTagRef | None:
    """解析 `gt:{field|block}:{contract}:{stable_key}`；非本方案返回 None。

    返回 None 表示「这不是平台管理的 SDT」（审计师自己在 Word 里插的内容控件），
    调用方按 Word-only 处理；它**不是**失败态，所以不抛。真正的失败（形态像 `gt:`
    但 contract 段不符 / 未登记）由 :meth:`WordEngineBinding.resolve_tag` 抛。
    """
    match = SDT_TAG_PATTERN.match((tag or "").strip())
    if match is None:
        return None
    key = match.group("key")
    row_uuid: str | None = None
    parts = key.split("/")
    if len(parts) >= 3 and parts[0] == ROW_SCOPE_SEGMENT:
        # `rows/{row_uuid}/{column_key}` —— 行身份**在 tag 内部**，不看行号。
        row_uuid = parts[1]
        if not row_uuid or row_uuid == ROW_UUID_PLACEHOLDER:
            return None
    return WordSdtTagRef(
        kind=match.group("kind"),
        contract_id=match.group("contract"),
        stable_key=key,
        row_uuid=row_uuid,
    )


def format_sdt_tag(
    *, kind: str, contract_id: str, stable_key: str, row_uuid: str | None = None
) -> str:
    """按契约模板生成具体 tag（把 `{row_uuid}` 替换成真实行身份）。"""
    key = stable_key
    if row_uuid is not None:
        if ROW_UUID_PLACEHOLDER not in stable_key:
            raise WordEngineError(
                f"stable_key {stable_key!r} 不含 {ROW_UUID_PLACEHOLDER} 占位，"
                "不能按行实例化 —— 行域字段的 tag 模板必须携带行身份占位"
            )
        key = stable_key.replace(ROW_UUID_PLACEHOLDER, row_uuid)
    tag = f"gt:{kind}:{contract_id}:{key}"
    if SDT_TAG_PATTERN.match(tag) is None:
        raise WordEngineError(f"生成的 tag 形态非法: {tag!r}")
    return tag


def _instantiate(spec: FieldSpec, row_uuid: str | None) -> str:
    if row_uuid is None:
        return spec.stable_field_key
    return spec.stable_field_key.replace(ROW_UUID_PLACEHOLDER, row_uuid)


# ═══════════════════════════════════════════════════════════════════════════
# 3. binding（frozen 身份 + 载体门；无任何写库面）
# ═══════════════════════════════════════════════════════════════════════════


class WordEngineMode(str, Enum):
    """engine 的两个**封闭**模式。见模块 docstring 第四节。"""

    #: 运行态：必须有 frozen approved bundle。
    bundle_bound = "bundle_bound"
    #: 离线：无 bundle，只可读/校验/写 candidate，禁止任何发布。
    offline_candidate_validation = "offline_candidate_validation"


@dataclass(frozen=True)
class WordEngineBinding:
    """一次 engine 调用的冻结身份。

    `bundle=None` ⇒ 模式必须是 `offline_candidate_validation`；有 bundle ⇒ 必须是
    `bundle_bound`，且三条 Task 13 判据全部委派执行。两者在 :meth:`__post_init__`
    里**互斥校验**，因此「离线模式偷偷带 bundle」或「运行态忘了带」都不可能构造出来。
    """

    contract: SyncContract
    entry_id: str
    mode: WordEngineMode
    bundle: DefinitionBundleSnapshot | None = None
    carrier_gate: CarrierGate = dataclass_field(default_factory=load_word_carrier_gate)

    def __post_init__(self) -> None:
        if self.contract.document_type != WORD_DOCUMENT_TYPE:
            raise WordEngineError(
                f"entry {self.entry_id}: Word engine 只接受 document_type="
                f"{WORD_DOCUMENT_TYPE!r} 的契约，实得 {self.contract.document_type!r}"
            )
        if self.carrier_gate.document_type != WORD_DOCUMENT_TYPE:
            raise WordCarrierBlockedError(
                f"entry {self.entry_id}: 载体门是 "
                f"{self.carrier_gate.document_type!r} 域的，不能用于 Word engine"
            )
        # ── 载体门：契约声明的每个 identity carrier 都必须在 Task 6 allowlist 内。
        #    委派 `CarrierGate.assert_carrier`（真源是探针裁决 JSON），本模块不复制清单。
        for carrier in self.contract.identity_carriers:
            try:
                self.carrier_gate.assert_carrier(
                    carrier, location=f"entry {self.entry_id}"
                )
            except Exception as exc:  # noqa: BLE001 —— 转成本域可分辨类型后立即上抛
                raise WordCarrierBlockedError(
                    f"entry {self.entry_id}: identity 载体 {carrier!r} 未过 Task 6 真实 "
                    f"OO 9.4 探针门（{self.carrier_gate.source_path.name}）：{exc}"
                ) from exc
        # ── 锚点门：本 engine 只用 `w_tag` 定位，这一条必须在 allowlist 内；
        #    它不在时整个 engine 都不成立（而不是「换个锚点继续」）。
        try:
            self.carrier_gate.assert_anchor("w_tag", location=f"entry {self.entry_id}")
        except Exception as exc:  # noqa: BLE001
            raise WordCarrierBlockedError(
                f"entry {self.entry_id}: 唯一正式锚点 `w_tag` 未过探针门：{exc} —— "
                "本 engine 没有第二个锚点可退（Requirement 7.1 禁止段落索引/正则）"
            ) from exc

        if self.mode is WordEngineMode.bundle_bound:
            if self.bundle is None:
                raise WordApprovedBundleRequiredError(
                    f"entry {self.entry_id}: bundle_bound 模式必须给 frozen approved "
                    "definition bundle —— 缺 bundle 时只能用 "
                    "offline_candidate_validation（Task 59 不为任何 entry 伪造 bundle）"
                )
            # 🔴 三条判据全部**委派** Task 13：bundle approved + typed slots、
            #    authority model ↔ contract ↔ contract slot 三向配对、contract
            #    canonical digest ↔ frozen slot digest（含 template/instrumentation
            #    漂移）。重写任一条都会让「短路一侧不改变行为」⇒ 变异判 GREEN。
            assert_bundle_usable(self.bundle, entry_id=self.entry_id)
            assert_authority_model_contract_pairing(
                authority_model=self.bundle.authority_model,
                contract=self.contract,
                bundle=self.bundle,
                entry_id=self.entry_id,
            )
            assert_contract_identity_frozen(
                contract=self.contract, bundle=self.bundle, entry_id=self.entry_id
            )
        elif self.bundle is not None:
            raise WordApprovedBundleRequiredError(
                f"entry {self.entry_id}: offline_candidate_validation 模式不得携带 "
                "definition bundle —— 两个模式必须互斥，否则「离线」会变成"
                "「有时候也能发布」"
            )

    # ─────────────────────────────────────────────────────────────────

    def assert_may_publish(self) -> None:
        """把产物交给 `RepresentationService` / `ContentMutationService` 之前的门。

        离线模式**恒抛**。这不是多余的保险：Task 59 交付时磁盘上一个 approved Word
        bundle 都没有，若离线态也能走发布路径，「candidate 不得带入运行态」这条边界
        就只剩注释。
        """
        if self.mode is not WordEngineMode.bundle_bound or self.bundle is None:
            raise WordApprovedBundleRequiredError(
                f"entry {self.entry_id}: 模式 {self.mode.value} 不得发布 representation —— "
                "缺 approved per-entry contract / authority model / definition bundle 时"
                "只能离线验证 candidate；published representation 只能由 "
                "`RepresentationService.finalize_candidate` 在三者全部 approved 后创建"
                "（Requirement 6.18 / 9.10 / Property 67）"
            )

    @property
    def frozen_identity(self) -> dict[str, Any]:
        """写进 operation error detail / evidence 的冻结身份（Requirement 7.10）。"""
        return {
            "entry_id": self.entry_id,
            "mode": self.mode.value,
            "contract_id": self.contract.contract_id,
            "contract_semantic_version": self.contract.semantic_version,
            "contract_sha256": self.contract.canonical_sha256,
            "template_definition_sha256": self.contract.template_definition_sha256,
            "instrumentation_definition_sha256": (
                self.contract.instrumentation_definition_sha256
            ),
            "identity_carriers": list(self.contract.identity_carriers),
            "carrier_gate_digest": self.carrier_gate.source_digest,
            "definition_bundle_id": (
                str(self.bundle.bundle_id) if self.bundle is not None else None
            ),
            "definition_bundle_sha256": (
                self.bundle.bundle_sha256 if self.bundle is not None else None
            ),
            "authority_model": (
                self.bundle.authority_model.value if self.bundle is not None else None
            ),
            "declared_field_instances": self.declared_instance_counts(),
        }

    def declared_instance_counts(self) -> dict[str, str]:
        """契约声明的每个字段的 `instances`（Requirement 7.10「字段实例计数」）。"""
        return {
            spec.stable_field_key: spec.instances
            for spec in self.contract.all_fields()
        }

    def resolve_tag(self, tag: WordSdtTagRef) -> FieldSpec:
        """把文档里的 tag 映射回 contract 字段；未登记/contract 段不符即 fail closed。"""
        if tag.contract_id != self.contract.contract_id:
            raise WordTagUnregisteredError(
                f"entry {self.entry_id}: 文档里的 tag {tag.raw!r} 的 contract 段与 frozen "
                f"contract {self.contract.contract_id!r} 不符 —— 历史 operation 只读 frozen "
                "bundle，不得按 registry 当前 alias 换契约（Property 28）"
            )
        for spec in self.contract.all_fields():
            if tag.row_scoped != spec.row_scoped:
                continue
            if _tag_key_matches(spec.stable_field_key, tag.stable_key):
                return spec
        raise WordTagUnregisteredError(
            f"entry {self.entry_id}: 文档里的 tag {tag.raw!r} 未在 per-entry contract "
            f"{self.contract.contract_id!r} 登记 —— 受管字段必须逐条声明，"
            "不得按中文标题或段落位置推断（Requirement 7.1 / 6.20）"
        )


def _tag_key_matches(template: str, actual: str) -> bool:
    """契约 key 模板（可含 `{row_uuid}`）与已实例化 key 的逐段匹配。

    刻意**不**用前缀比较：`rows/{row_uuid}/amount` 与 `rows/{row_uuid}/amount_note`
    在前缀口径下会互相误配。
    """
    exp = template.split("/")
    got = actual.split("/")
    if len(exp) != len(got):
        return False
    return all(e == g or e == ROW_UUID_PLACEHOLDER for e, g in zip(exp, got))


# ═══════════════════════════════════════════════════════════════════════════
# 4. extract
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordSdtInstance:
    """一个受管 SDT 实例的读取结果。identity 是 `tag`，`xpath` 只作报告用位置。"""

    tag: WordSdtTagRef
    spec: FieldSpec
    #: 报告用位置（AC 7.4「列出全部 OO 位置」）。
    xpath: str
    container_path: str
    ancestor_tags: tuple[str, ...]
    text: str
    #: `w:sdtContent` 内是否还有嵌套 SDT（block 容器 ⇒ 不是写入目标）。
    has_nested_sdt: bool


@dataclass(frozen=True)
class WordExtractOutcome:
    """一次 extract 的完整结论。"""

    projection: Projection
    instances: tuple[WordSdtInstance, ...]
    #: 同 tag 多实例异值的 `duplicate_word_instance` 冲突（由 Task 14 的
    #: `reduce_word_instances` 构造 —— 本模块只观测，不重写归约规则）。
    conflicts: tuple[ConflictRecord, ...]
    #: 结构/身份异常**观测**，交 `merge_projections(structural_anomalies=...)` 成形。
    anomalies: tuple[StructuralAnomaly, ...]
    #: SDT 外自由正文的规范化 digest（Word-only 区域身份）。
    word_only_digest: str
    #: 受管表格的行身份清册（含表头 —— 见 :class:`WordRowInventory` docstring）。
    row_inventory: WordRowInventory
    #: 文档里出现的、非平台管理的 SDT 数（审计师自建内容控件）。
    unmanaged_sdt_count: int
    aspect_digests: Mapping[str, str]
    row_uuids: Mapping[str, tuple[str, ...]]

    @property
    def unidentified_row_count(self) -> int:
        return self.row_inventory.unidentified_rows

    def merge_inputs(self) -> tuple[Projection, tuple[StructuralAnomaly, ...]]:
        """喂给 `merge.merge_projections(incoming=..., structural_anomalies=...)`。

        与 Task 37 的 `ExcelExtractOutcome.merge_inputs()` 同签名 —— 两个文档域的
        extract 都只提供**观测**，三方 merge 与冲突成形由 Task 14 的域唯一负责。
        """
        return (self.projection, self.anomalies)

    @property
    def identity_inventory_sha256(self) -> str:
        """tag → 实例 xpath 清册的 digest（Requirement 7.10 的实例计数身份）。"""
        lines = [
            f"{inst.tag.raw}\t{inst.xpath}\t{inst.container_path}"
            for inst in sorted(self.instances, key=lambda i: (i.tag.raw, i.xpath))
        ]
        return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "managed_field_count": len(self.projection.values),
            "instance_count": len(self.instances),
            "conflict_kinds": sorted({c.kind.value for c in self.conflicts}),
            "word_only_digest": self.word_only_digest,
            "managed_table_count": self.row_inventory.managed_table_count,
            "managed_table_rows": self.row_inventory.total_rows,
            "identified_row_count": self.row_inventory.identified_rows,
            "unidentified_row_count": self.unidentified_row_count,
            "unmanaged_sdt_count": self.unmanaged_sdt_count,
            "identity_inventory_sha256": self.identity_inventory_sha256,
            "row_uuids": {k: list(v) for k, v in sorted(self.row_uuids.items())},
            "aspect_digests": dict(sorted(self.aspect_digests.items())),
        }


def _fingerprint_or_fail(data: bytes, *, where: str) -> DocumentFingerprint:
    """采集结构事实；任何采集错误都抛，**绝不**降级成「文档里没有 SDT」。"""
    try:
        fingerprint = structure_fingerprint(data)
    except WordFingerprintError as exc:
        raise WordEngineError(f"{where}: DOCX 结构采集失败: {exc}") from exc
    if fingerprint.errors:
        raise WordEngineError(
            f"{where}: DOCX 结构采集报错 {fingerprint.errors} —— 采集失败与「tag 被 OO "
            "剥离」是两件完全不同的事实，不得共用同一结论"
        )
    return fingerprint


#: 读侧门的**声明顺序**（Requirement 5.12 的可诊断性 + AC 8.10 的准入）。
#:
#: 🔴 顺序是**语义的一部分**，不是实现细节，所以写成可单条变异的声明而不是埋在
#: 函数体的语句先后里：
#:
#: * `substrate_admission` 必须最先 —— 放到后面时 quarantined artifact 会先被
#:   zip/结构错误拦住，「quarantined 永不进 engine」这条判据就落在永久不可达分支上
#:   （本 spec 已实测同形态 3 次）；
#: * `publish_authority` 紧随其后 —— 离线模式没有 published representation 可读，
#:   在解析之前就该拒；
#: * `ooxml_security` 最后 —— 它是三者里最贵的一步（要流式解压整包）。
#:
#: 守卫按本元组的**实际顺序**断言，并用一份「不是 zip」的 artifact 让顺序一换就打红。
READ_GATE_ORDER: Final[tuple[str, ...]] = (
    "substrate_admission",
    "publish_authority",
    "ooxml_security",
)


def _read_document_bytes(
    artifact: Path,
    *,
    binding: WordEngineBinding,
    substrate_role: SubstrateRole,
    artifact_kind: ArtifactKind,
    artifact_state: ArtifactState,
    limits: SyncLimits,
) -> bytes:
    """按 :data:`READ_GATE_ORDER` 逐门放行后读字节。**顺序即判据。**"""
    for gate in READ_GATE_ORDER:
        if gate == "substrate_admission":
            assert_substrate_usable(
                role=substrate_role,
                artifact_kind=artifact_kind,
                artifact_state=artifact_state,
            )
        elif gate == "publish_authority":
            if substrate_role is SubstrateRole.published_representation:
                binding.assert_may_publish()
        elif gate == "ooxml_security":
            # 预算/安全门全部委派 Task 11/26 的单一真源，本模块不复制任何阈值数字。
            validate_ooxml_artifact(
                artifact, document_type=WORD_DOCUMENT_TYPE, limits=limits
            )
        else:  # pragma: no cover - 封闭枚举，新增门必须在此登记
            raise WordEngineError(f"未登记的读侧门: {gate!r}")
    return artifact.read_bytes()


def _row_uuid_index(fingerprint: DocumentFingerprint) -> dict[str, tuple[str, ...]]:
    """按 `gt:` 方案从 tag 里取行身份：`{行域首段}` → 该表出现过的 row_uuid（按序）。

    🔴 不用 `word_sdt_fingerprint.row_uuids()`：那个方法认 `gtsdt/v1/row/...`，
    在本方案下恒返回空 dict ⇒ 「行身份没丢」这条判据变成空集恒真。
    """
    out: dict[str, list[str]] = {}
    for node in fingerprint.sdt_nodes:
        ref = parse_sdt_tag(node.tag)
        if ref is None or not ref.row_scoped:
            continue
        table_key = ref.stable_key.split("/")[2] if len(
            ref.stable_key.split("/")
        ) > 2 else ROW_SCOPE_SEGMENT
        bucket = out.setdefault(f"{ref.contract_id}:{table_key}", [])
        assert ref.row_uuid is not None  # parse_sdt_tag 已保证
        if ref.row_uuid not in bucket:
            bucket.append(ref.row_uuid)
    return {k: tuple(v) for k, v in sorted(out.items())}


@dataclass(frozen=True)
class WordRowInventory:
    """受管表格的行身份清册（Requirement 6.15 的 Word 侧观测量）。

    ═══ 为什么把「无身份行数」当**事实**报出来，而不是当错误抛 ═══

    受管表格里没有行身份 tag 的 `w:tr` 有两个来源：

    * **表头 / 标签行** —— 天然没有行身份，是正常形态（B30-11-2 的第 1 行就是
      10 列中文表头）；
    * **OO 内新增的数据行** —— Task 6 实测「OO 新增行不携带任何 identity」
      （`oo_created_row_has_no_uuid`），对应 Requirement 6.15 的 Word 侧同类问题，
      contract 必须显式分类为「分配新 ID / 结构冲突 / 拒绝」。

    engine 分不出这两者（分得出就意味着用了行号），所以它**只报事实**：
    `unidentified_rows` 含表头。可行动的判据是**同一 entry 的 substrate 与 incoming
    之间的差值** —— 新增一行会让它 +1、让 `row_uuids` 集合不变。调用方
    （Task 60 / 62–64 的 per-entry adapter）据 contract 分类。

    🔴 上一版实现读 `word_sdt_fingerprint` 的 `table_shapes[].rows[]["xpath"]`，
    而那个 dict **没有** `xpath` 键 ⇒ `row.get("xpath")` 恒为 `""`、
    `startswith("")` 恒 True ⇒ 计数恒 0，「OO 新增行」永远不可见。改成在 XML 上
    按 `w:tbl` / `w:tr` 的字节 span 直接数。
    """

    managed_table_count: int
    total_rows: int
    identified_rows: int
    unidentified_rows: int


def _outermost(
    spans: Sequence[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    """只保留互不嵌套的**最外层** span（嵌套表格/嵌套行会让「第 N 个」歧义）。"""
    return [
        span
        for span in spans
        if not any(
            other is not span and other[0] < span[0] and other[3] >= span[3]
            for other in spans
        )
    ]


def _row_inventory(document_xml: str) -> WordRowInventory:
    """受管表格（至少含一个行域 tag 的表）里逐行统计行身份覆盖。"""

    def _has_row_tag(fragment: str) -> bool:
        for span in _find_spans(fragment, "sdt"):
            tag = _tag_of(fragment[span[0] : span[3]])
            ref = parse_sdt_tag(tag or "")
            if ref is not None and ref.row_scoped:
                return True
        return False

    tables = _outermost(_find_spans(document_xml, "tbl"))
    managed = 0
    total = identified = 0
    for span in tables:
        table_xml = document_xml[span[0] : span[3]]
        if not _has_row_tag(table_xml):
            continue
        managed += 1
        for row in _outermost(_find_spans(table_xml, "tr")):
            total += 1
            if _has_row_tag(table_xml[row[0] : row[3]]):
                identified += 1
    return WordRowInventory(
        managed_table_count=managed,
        total_rows=total,
        identified_rows=identified,
        unidentified_rows=total - identified,
    )


def _normalise_value(spec: FieldSpec, text: str) -> Any:
    """按 contract 的 `value_type` 规范化读到的文本。

    转换失败**保留原值**（design §Extract「类型转换失败保留原值供裁决」），由调用方
    形成 `type_normalization_failure` schema 冲突 —— 不静默改值、不抛掉整次 extract。
    """
    raw = text if spec.value_type is ValueType.text else text.strip()
    if spec.value_type is ValueType.text:
        return raw
    if raw == "":
        return None
    try:
        if spec.value_type is ValueType.integer:
            return int(raw.replace(",", ""))
        if spec.value_type in (ValueType.amount, ValueType.rate, ValueType.ratio):
            from decimal import Decimal, InvalidOperation

            try:
                return Decimal(raw.replace(",", ""))
            except InvalidOperation:
                return raw
        if spec.value_type is ValueType.boolean:
            lowered = raw.lower()
            if lowered in {"true", "是", "y", "yes", "1"}:
                return True
            if lowered in {"false", "否", "n", "no", "0"}:
                return False
            return raw
        if spec.value_type is ValueType.date:
            from datetime import date

            return date.fromisoformat(raw)
        if spec.value_type is ValueType.datetime:
            from datetime import datetime

            return datetime.fromisoformat(raw)
    except ValueError:
        # 规范化失败**保留原值**供裁决（design §Extract）—— 调用方会据此形成
        # `type_normalization_failure` schema 冲突，engine 不静默改值。
        return raw
    return raw


def _locator_for(spec: FieldSpec, *, key: str, xpath: str, row_key: str) -> FieldLocator:
    pointer = spec.json_pointer
    if ROW_UUID_PLACEHOLDER in pointer and row_key:
        pointer = pointer.replace(ROW_UUID_PLACEHOLDER, row_key)
    protection = (
        ProtectionPolicy.editable
        if spec.mode is FieldMode.editable
        else ProtectionPolicy.word_only
        if spec.mode is FieldMode.word_only
        else ProtectionPolicy.read_only_formula
        if spec.mode is FieldMode.formula
        else ProtectionPolicy.read_only_auto_source
    )
    source = (
        FieldSource.onlyoffice_sdt
        if spec.mode in (FieldMode.editable, FieldMode.word_only)
        else FieldSource.server_formula
        if spec.mode is FieldMode.formula
        else FieldSource.auto_data_source
    )
    return FieldLocator(
        stable_field_key=key,
        business_label=spec.source_ref,
        json_pointer=pointer,
        oo_location=xpath,
        field_source=source,
        protection_policy=protection,
        value_type=spec.value_type,
        mode=spec.mode,
        row_key=row_key,
    )


def extract_word_projection(
    *,
    artifact: Path,
    binding: WordEngineBinding,
    substrate_role: SubstrateRole,
    artifact_kind: ArtifactKind,
    artifact_state: ArtifactState,
    limits: SyncLimits | None = None,
) -> WordExtractOutcome:
    """遍历全部 `w:sdt`，**只按 `w:tag`** 解析 stable key / row_uuid。

    判定顺序（不可交换）：

    1. substrate 准入（quarantined / candidate / 非 durable incoming 各自的类型）；
    2. OOXML 安全与容量门（委派 Task 11）；
    3. 结构采集，采集错误立即抛（禁 fail-open）；
    4. tag 解析与 contract 反查（未登记 / contract 段不符 fail closed）；
    5. 层级判据（block 内字段必须仍在 block 内、行域字段必须仍在表格单元格内）；
    6. 契约字段缺失 fail closed（Property 30 / 34）；
    7. `instances` 计数校验；
    8. 同 stable key 多实例：值一致合并、异值形成 `duplicate_word_instance` 冲突
       并列出**全部** XPath（Property 32）。

    SDT 外内容永不进 Projection（Requirement 7.3 后半句）。
    """
    lim = limits or load_limits()
    data = _read_document_bytes(
        artifact,
        binding=binding,
        substrate_role=substrate_role,
        artifact_kind=artifact_kind,
        artifact_state=artifact_state,
        limits=lim,
    )
    fingerprint = _fingerprint_or_fail(data, where=f"entry {binding.entry_id} extract")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        document_xml = zf.read(WORD_DOCUMENT_PART).decode("utf-8")
    text_by_tag = _sdt_texts_by_tag(document_xml)

    containers = _container_tags(fingerprint)
    instances: list[WordSdtInstance] = []
    unmanaged = 0
    block_tags_present: set[str] = set()
    seen_per_tag: dict[str, int] = {}
    for node in fingerprint.sdt_nodes:
        ref = parse_sdt_tag(node.tag)
        if ref is None:
            unmanaged += 1
            continue
        spec = binding.resolve_tag(ref)
        if ref.kind == "block":
            block_tags_present.add(ref.stable_key)
        ordinal = seen_per_tag.get(node.tag, 0)
        seen_per_tag[node.tag] = ordinal + 1
        texts = text_by_tag.get(node.tag) or []
        if ordinal >= len(texts):
            # 两个采集器（ElementTree 遍历 vs 字节 span 扫描）在同一份 XML 上
            # 数出的实例数不一致 ⇒ 采集器缺陷，绝不降级成「读到空值」。
            raise WordEngineError(
                f"entry {binding.entry_id}: tag {node.tag!r} 的实例计数在两个采集口径下"
                f"不一致（结构树第 {ordinal + 1} 个，字节扫描只有 {len(texts)} 个）—— "
                "采集不一致必须 fail closed"
            )
        instances.append(
            WordSdtInstance(
                tag=ref,
                spec=spec,
                xpath=node.xpath,
                container_path=node.container_path,
                ancestor_tags=tuple(node.ancestor_tags),
                text=texts[ordinal],
                has_nested_sdt=node.tag in containers,
            )
        )

    _assert_hierarchy(instances, block_tags_present, entry_id=binding.entry_id)

    by_key: dict[str, list[WordSdtInstance]] = {}
    for inst in instances:
        if inst.tag.kind == "block" and inst.has_nested_sdt:
            # block 容器只提供层级，值由内层 leaf 提供 —— 把它算进值集合会让同一
            # stable key 凭空多出一个「实例」，duplicate 判据全部失真。
            continue
        by_key.setdefault(inst.tag.stable_key, []).append(inst)

    _assert_contract_fields_present(binding, by_key)
    _assert_instance_counts(binding, by_key)

    values: dict[str, FieldValue] = {}
    conflicts: list[ConflictRecord] = []
    anomalies: list[StructuralAnomaly] = []
    for key, group in sorted(by_key.items()):
        spec = group[0].spec
        row_key = group[0].tag.row_uuid or ""
        # 🔴 同 tag 多实例的**归约**委派 Task 14 的 `reduce_word_instances`（单一真源）：
        #    「值一致则合并为一个字段、不一致则生成 duplicate 冲突并列出全部 XPath」
        #    这条 AC 7.4 规则只能有一份实现。本模块只负责**观测**（把 SDT 实例读成
        #    `WordInstanceObservation`），归约与冲突构造一概不重写 —— 重写会让任一侧被
        #    短路都不改变行为（变异检验判 GREEN），也会让两侧的「值相等」口径分叉。
        observation = WordInstanceObservation(
            stable_field_key=key,
            instances=tuple(
                WordInstance(xpath=inst.xpath, value=_normalise_value(spec, inst.text))
                for inst in sorted(group, key=lambda i: i.xpath)
            ),
        )
        locator = _locator_for(
            spec, key=key, xpath=group[0].xpath, row_key=row_key
        )
        incoming_envelope, duplicate = reduce_word_instances(observation, locator)
        if duplicate is not None:
            conflicts.append(duplicate)
            continue
        normalised = (
            incoming_envelope.value if incoming_envelope.present else None
        )
        if (
            spec.value_type is not ValueType.text
            and isinstance(normalised, str)
            and normalised.strip() != ""
        ):
            # 🔴 类型规范化失败**只报观测**（`StructuralAnomaly`），不在这里构造 `schema`
            #    ConflictRecord：那条转换规则的单一真源是 Task 14 的
            #    `merge_projections(structural_anomalies=...)`。与 Task 37 的
            #    `ExcelExtractOutcome.merge_inputs()` 同形态 —— extract 侧只观测，
            #    冲突域只成形一次。
            anomalies.append(
                StructuralAnomaly(
                    kind=SchemaAnomalyKind.type_normalization_failure,
                    stable_field_key=key,
                    detail=(
                        f"字段 {key!r} 声明 value_type={spec.value_type.value}，"
                        f"实读 {normalised!r} 无法规范化 —— 保留原值供裁决，不静默改写"
                    ),
                    row_key=row_key,
                    oo_location=group[0].xpath,
                    business_label=spec.source_ref,
                    json_pointer=locator.json_pointer,
                )
            )
        values[key] = FieldValue(
            stable_key=key,
            value=normalised,
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=row_key or None,
        )

    row_uuids = _row_uuid_index(fingerprint)
    projection = Projection(
        contract_id=binding.contract.contract_id,
        semantic_version=binding.contract.semantic_version,
        document_type=WORD_DOCUMENT_TYPE,
        values=values,
        row_keys=row_uuids,
    )
    projection.assert_matches_contract(binding.contract)
    return WordExtractOutcome(
        projection=projection,
        instances=tuple(instances),
        conflicts=tuple(conflicts),
        anomalies=tuple(anomalies),
        word_only_digest=fingerprint.aspect_digests()["outside_sdt_text"],
        row_inventory=_row_inventory(document_xml),
        unmanaged_sdt_count=unmanaged,
        aspect_digests=fingerprint.aspect_digests(),
        row_uuids=row_uuids,
    )


#: `w:br` / `w:cr` 在值里的语义（design §Word extract「保留 contract 指定的换行」）。
_BREAK_ELEMENTS: Final[tuple[str, ...]] = ("<w:br/>", "<w:br ", "<w:cr/>", "<w:cr ")


def _sdt_texts_by_tag(document_xml: str) -> dict[str, list[str]]:
    """按文档顺序取每个 tag 各实例的值文本，**`w:br` 计一个 `\\n`**。

    🔴 为什么不用 `SdtNode.text`：`word_sdt_fingerprint._node_text` 只 join `w:t`，
    把 `<w:br/>` 直接丢掉 ⇒ 「A 库\\nB 库」写进去、读回来是「A 库B 库」，
    `verify_word_before_commit` 在真实多行值上必红（2026-08-29 首轮实测）。design
    §Word extract 明写「保留 contract 指定的换行/富文本语义」，所以换行必须往返。

    与 fingerprint 的配对方式：两侧都是**文档顺序**，因此同一 tag 的第 k 个实例一一
    对应；:func:`extract_word_projection` 会断言两侧计数相等，不等即 fail closed
    （采集不一致绝不降级成「读到空值」）。
    """
    out: dict[str, list[str]] = {}
    for span in _find_spans(document_xml, "sdt"):
        el_start, _, _, el_end = span
        sdt_xml = document_xml[el_start:el_end]
        tag = _tag_of(sdt_xml)
        if tag is None:
            continue
        contents = _find_spans(sdt_xml, "sdtContent")
        if not contents:
            continue
        inner = sdt_xml[contents[0][1] : contents[0][2]]
        out.setdefault(tag, []).append(_inner_text(inner))
    return out


def _inner_text(inner: str) -> str:
    """`w:sdtContent` 的可见文本：`w:t` 内容按序拼接，`w:br`/`w:cr` 记 `\\n`。"""
    pieces: list[str] = []
    pos = 0
    while pos < len(inner):
        idx = inner.find("<w:", pos)
        if idx == -1:
            break
        if inner.startswith("<w:t", idx) and inner[idx + 4 : idx + 5] in (
            ">", " ", "\t", "\r", "\n", "/",
        ):
            gt = inner.find(">", idx)
            if gt == -1:
                break
            if inner[gt - 1 : gt] == "/":  # `<w:t/>`
                pos = gt + 1
                continue
            end = inner.find("</w:t>", gt)
            if end == -1:
                break
            pieces.append(_xml_unescape(inner[gt + 1 : end]))
            pos = end + len("</w:t>")
            continue
        if any(inner.startswith(marker, idx) for marker in _BREAK_ELEMENTS):
            pieces.append("\n")
            pos = inner.find(">", idx) + 1 or idx + 1
            continue
        pos = idx + 3
    return "".join(pieces)


def _xml_unescape(text: str) -> str:
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )


def _container_tags(fingerprint: DocumentFingerprint) -> frozenset[str]:
    """出现在**别人祖先链**里的 tag = block 容器（不是值的写入目标）。

    判据用 `ancestor_tags` 的反向汇总，而不是 `SdtNode.content_children` ——
    后者只列 `w:sdtContent` 的**直接**子元素本地名，而 block SDT 的实际形态是
    `sdtContent > p > sdt`，直接子元素里只有 `p`，嵌套关系看不出来
    （Task 6 的 F06 注入正是这个形态）。
    """
    return frozenset(
        tag for node in fingerprint.sdt_nodes for tag in node.ancestor_tags if tag
    )


def _assert_hierarchy(
    instances: Sequence[WordSdtInstance],
    block_tags_present: set[str],
    *,
    entry_id: str,
) -> None:
    """层级漂移 fail closed（design §Word materialize「结构漂移则阻断」）。

    两条判据都来自 Task 6 的实测形态：

    1. **block 内字段必须仍在 block 内** —— 探针取证了 `gt:block:…:plan/warehouses`
       包裹同 key 的 `gt:field:…`（depth=2，17/17 保留）。若同一 stable key 既登记了
       block 又登记了 field，而 field 实例的祖先 tag 链里没有那个 block ⇒ 层级被压扁。
    2. **行域字段必须仍在表格单元格内** —— 行身份靠单元格内 field SDT 承载；跑到表外
       就说明行结构被破坏，此时按 tag 读到的值不再属于任何行。
    """
    for inst in instances:
        if inst.tag.kind == "field" and inst.tag.stable_key in block_tags_present:
            block_tag = format_sdt_tag(
                kind="block",
                contract_id=inst.tag.contract_id,
                stable_key=inst.tag.stable_key,
            )
            if block_tag not in inst.ancestor_tags:
                raise WordTagHierarchyDriftError(
                    f"entry {entry_id}: field tag {inst.tag.raw!r} 的祖先链 "
                    f"{list(inst.ancestor_tags)} 里没有登记的 block 容器 {block_tag!r} —— "
                    "层级被压扁，禁止按段落位置猜归属（Requirement 7.5 / Property 30）"
                )
        if inst.tag.row_scoped and "/tc" not in inst.container_path:
            raise WordTagHierarchyDriftError(
                f"entry {entry_id}: 行域 tag {inst.tag.raw!r} 落在表格单元格之外"
                f"（container={inst.container_path!r}）—— 行身份由单元格内 field SDT 承载，"
                "表外实例无法归属任何行"
            )


def _assert_contract_fields_present(
    binding: WordEngineBinding, by_key: Mapping[str, Sequence[WordSdtInstance]]
) -> None:
    """契约声明的**非行域**字段必须逐个出现（Property 30 / 34）。

    行域字段按行实例化，行集合本身是可变的（审计师可增删行），所以缺某一行不算 tag
    丢失；但**非行域**字段少一个就是 tag retention 失败，必须 fail closed。
    """
    missing = [
        spec.stable_field_key
        for spec in binding.contract.all_fields()
        if not spec.row_scoped and spec.stable_field_key not in by_key
    ]
    if missing:
        raise WordTagMissingError(
            f"entry {binding.entry_id}: contract 声明的 tag 在文档里找不到: "
            f"{sorted(missing)} —— extract fail closed。**不得**回退段落绝对索引、"
            "中文正则或已替换 placeholder 文本（Requirement 7.1 / 7.8）；"
            f"frozen 身份 {binding.frozen_identity['contract_sha256'][:12]}…"
        )


def _assert_instance_counts(
    binding: WordEngineBinding, by_key: Mapping[str, Sequence[WordSdtInstance]]
) -> None:
    """`instances="one"` 的字段不得出现多个实例（Requirement 7.10）。"""
    bad: list[str] = []
    for key, group in sorted(by_key.items()):
        if group[0].spec.instances == "one" and len(group) > 1:
            bad.append(f"{key}×{len(group)}")
    if bad:
        raise WordTagInstanceCountError(
            f"entry {binding.entry_id}: contract 声明 instances='one' 的字段出现多个实例: "
            f"{bad} —— 模板漂移或 SDT 被复制，必须先裁决再回写"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. materialize（zip-level 定点改写，只碰 word/document.xml）
# ═══════════════════════════════════════════════════════════════════════════


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _find_spans(xml: str, local: str) -> list[tuple[int, int, int, int]]:
    """返回 `<w:{local}>` 元素的 `(el_start, inner_start, inner_end, el_end)` 列表。

    深度计数配对，**不用正则跨标签匹配**：嵌套 `w:sdt` 是本方案的正常形态
    （block 包 inline），正则会在第一个 `</w:sdt>` 上错配。自闭合元素返回
    `inner_start == inner_end`。
    """
    open_tag = f"<w:{local}"
    close_tag = f"</w:{local}>"
    spans: list[tuple[int, int, int, int]] = []
    stack: list[tuple[int, int]] = []
    pos = 0
    while pos < len(xml):
        next_open = xml.find(open_tag, pos)
        next_close = xml.find(close_tag, pos)
        if next_open == -1 and next_close == -1:
            break
        if next_open != -1 and (next_close == -1 or next_open < next_close):
            gt = xml.find(">", next_open)
            if gt == -1:
                break
            # 只接受 `<w:sdt>` / `<w:sdt ...>`，排除 `<w:sdtPr` / `<w:sdtContent`。
            head = xml[next_open + len(open_tag) : gt]
            if head[:1] not in ("", " ", "/", "\t", "\r", "\n", ">"):
                pos = gt + 1
                continue
            if head.endswith("/"):
                spans.append((next_open, gt + 1, gt + 1, gt + 1))
                pos = gt + 1
                continue
            stack.append((next_open, gt + 1))
            pos = gt + 1
            continue
        start = stack.pop() if stack else None
        if start is not None:
            spans.append((start[0], start[1], next_close, next_close + len(close_tag)))
        pos = next_close + len(close_tag)
    return sorted(spans)


def _tag_of(sdt_xml: str) -> str | None:
    """从一个 `w:sdt` 元素的 XML 里读 `w:sdtPr/w:tag/@w:val`。"""
    props = _find_spans(sdt_xml, "sdtPr")
    if not props:
        return None
    props_xml = sdt_xml[props[0][1] : props[0][2]]
    marker = "<w:tag "
    idx = props_xml.find(marker)
    if idx == -1:
        return None
    end = props_xml.find(">", idx)
    attrs = props_xml[idx + len(marker) : end]
    needle = 'w:val="'
    at = attrs.find(needle)
    if at == -1:
        return None
    close = attrs.find('"', at + len(needle))
    raw = attrs[at + len(needle) : close]
    return (
        raw.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )


def _render_runs(text: str, rpr: str) -> str:
    """把值渲染成一个（或按换行拆成一串）`w:r`，沿用原 run 的 `w:rPr`。

    `xml:space="preserve"` 必须写：不写时 Word/OO 会吃掉首尾空格，「不变字段也按
    merged projection 规范化」这条就会在空格上翻脸。
    """
    segments = str(text).split("\n")
    pieces: list[str] = []
    for idx, seg in enumerate(segments):
        if idx:
            pieces.append("<w:br/>")
        pieces.append(f'<w:t xml:space="preserve">{_xml_escape(seg)}</w:t>')
    return f"<w:r>{rpr}{''.join(pieces)}</w:r>"


def _rewrite_sdt_content(inner: str, value: str) -> str:
    """把 `w:sdtContent` 里的 run 序列换成新值，**保留** pPr / 段落壳与首个 rPr。

    只动 `w:r`：`w:pPr`（段落样式）、`w:bookmarkStart`、`w:proofErr`、`w:tbl` 等一概
    原样留下。design §Word materialize「仅替换匹配 tag 的 `w:sdtContent`」在实现上
    必须细到这一层 —— 整块替换会把 block SDT 里的段落样式一起丢掉。
    """
    runs = [s for s in _find_spans(inner, "r") if s[3] > s[0]]
    if not runs:
        # 没有 run 可替（例如注入时留了空 sdtContent）：在末尾追加一个。
        return inner + _render_runs(value, "")
    first = runs[0]
    rpr_spans = _find_spans(inner[first[1] : first[2]], "rPr")
    rpr = (
        inner[first[1] : first[2]][rpr_spans[0][0] : rpr_spans[0][3]]
        if rpr_spans
        else ""
    )
    # 🔴 一次性按**原始** span 切片重组，不做「先替换再逐个删、每轮重算 shift」。
    #    旧写法在 `sdtContent` 里有 **3 个以上** run 时会算错偏移：`shift` 在循环里
    #    每轮重新取 `len(out) - len(inner)`，而每删一个 run 这个差值就变一次 ⇒ 倒数
    #    第二个之后的删除位置整体前移，把相邻内容一起切掉。Task 77 的 AC 7.5 跨 run
    #    场景（把一个 SDT 的内容拆成 3~4 个 `w:r`）实测到这条：反读值与写入值不等，
    #    `verify_word_before_commit` 报 `WordManagedProjectionMismatchError`。
    #    2 个 run 时旧写法恰好正确，所以此前的 fixture 都没暴露它。
    pieces: list[str] = [inner[: first[0]], _render_runs(value, rpr)]
    prev_end = first[3]
    for span in runs[1:]:
        # run 之间的非 run 内容（bookmarkStart / proofErr / pPr 片段…）原样保留。
        pieces.append(inner[prev_end : span[0]])
        prev_end = span[3]
    pieces.append(inner[prev_end:])
    return "".join(pieces)


@dataclass(frozen=True)
class WordMaterializeOutcome:
    """一次 materialize 的产物（staged，**尚未** publish）。"""

    result: MaterializeResult
    written_tags: tuple[str, ...]
    skipped_container_tags: tuple[str, ...]
    document_part_changed: bool
    untouched_part_count: int

    @property
    def output_path(self) -> Path:
        return self.result.output_path

    def as_dict(self) -> dict[str, Any]:
        return {
            "output_path": str(self.output_path),
            "artifact_sha256": self.result.artifact_sha256,
            "structure_hash": self.result.structure_hash,
            "identity_inventory_sha256": self.result.identity_inventory_sha256,
            "managed_field_count": self.result.managed_field_count,
            "written_tags": list(self.written_tags),
            "skipped_container_tags": list(self.skipped_container_tags),
            "document_part_changed": self.document_part_changed,
            "untouched_part_count": self.untouched_part_count,
        }


def materialize_word_projection(
    *,
    substrate: Path,
    projection: Projection,
    output: Path,
    binding: WordEngineBinding,
    substrate_role: SubstrateRole,
    artifact_kind: ArtifactKind,
    artifact_state: ArtifactState,
    limits: SyncLimits | None = None,
) -> WordMaterializeOutcome:
    """把 projection 写进匹配 tag 的 `w:sdtContent`；其余一切逐字节保留。

    Requirement 7.9：**不得**用模板重生成覆盖审计师已编辑的 Word-only 内容 ——
    substrate 是当前 canonical/incoming 字节，本函数在它之上定点改写，
    `word/document.xml` 以外的部件（批注 `comments.xml`、修订、图片 `media/`、
    页眉页脚、styles、numbering、customXml…）连压缩参数都原样复制。
    """
    lim = limits or load_limits()
    data = _read_document_bytes(
        substrate,
        binding=binding,
        substrate_role=substrate_role,
        artifact_kind=artifact_kind,
        artifact_state=artifact_state,
        limits=lim,
    )
    fingerprint = _fingerprint_or_fail(
        data, where=f"entry {binding.entry_id} materialize substrate"
    )

    # 行身份必须**先**核对：要写的行 UUID 不在文档里时一个字节都不该写。
    present_rows = {
        ref.row_uuid
        for node in fingerprint.sdt_nodes
        if (ref := parse_sdt_tag(node.tag)) is not None and ref.row_scoped
    }
    wanted_rows = {
        value.row_key for value in projection.values.values() if value.row_key
    }
    orphan_rows = sorted(wanted_rows - present_rows)
    if orphan_rows:
        raise WordRowIdentityMissingError(
            f"entry {binding.entry_id}: 要写的行身份 {orphan_rows} 在文档里不存在 —— "
            "row 级 SDT 在 OO 9.4 上会被剥离，行身份只能由单元格内 field SDT 的 tag "
            "承载；缺行时必须按 contract 显式分配新 ID 或形成结构冲突，"
            "禁止按表格行号猜（Requirement 7.2 / 6.15）"
        )

    with zipfile.ZipFile(substrate) as zf:
        infos = zf.infolist()
        if WORD_DOCUMENT_PART not in {i.filename for i in infos}:
            raise WordEngineError(
                f"entry {binding.entry_id}: DOCX 缺 {WORD_DOCUMENT_PART} —— "
                "结构不合法，不得继续写入"
            )
        parts: dict[str, bytes] = {i.filename: zf.read(i) for i in infos}
        order = [(i.filename, i.compress_type) for i in infos]

    xml = parts[WORD_DOCUMENT_PART].decode("utf-8")
    written: list[str] = []
    skipped: list[str] = []
    all_spans = _find_spans(xml, "sdt")
    # 🔴 容器（内部还嵌着别的 SDT）**必须先分类再改写**：block SDT 与其内层 leaf 的
    #    span 互相**重叠**，只靠「从后往前」不足以保证下标有效 —— 改完内层之后外层的
    #    `el_end` 已经漂移。2026-08-29 首轮实测就是这个形态：block 容器被当成 leaf
    #    整块覆盖，`written_tags` 里同时出现容器 tag 与内层 tag，内层 SDT 连 tag
    #    一起被抹掉。分类后只改 leaf，leaf 之间互不重叠，反向替换才是安全的。
    targets: list[tuple[int, int, int, int]] = []
    for span in all_spans:
        nested = any(
            other is not span and other[0] > span[0] and other[3] <= span[3]
            for other in all_spans
        )
        raw_tag = _tag_of(xml[span[0] : span[3]])
        if raw_tag is None or parse_sdt_tag(raw_tag) is None:
            continue
        if nested:
            skipped.append(raw_tag)
            continue
        targets.append(span)

    for span in sorted(targets, reverse=True):
        el_start, _, _, el_end = span
        sdt_xml = xml[el_start:el_end]
        raw_tag = _tag_of(sdt_xml)
        ref = parse_sdt_tag(raw_tag or "")
        if ref is None:  # pragma: no cover - 上面已过滤
            continue
        binding.resolve_tag(ref)  # 未登记 tag 在写入前 fail closed
        value = projection.get(ref.stable_key)
        if value is None:
            continue
        contents = _find_spans(sdt_xml, "sdtContent")
        if not contents:
            raise WordEngineError(
                f"entry {binding.entry_id}: tag {raw_tag!r} 的 SDT 缺 w:sdtContent"
            )
        _, inner_start, inner_end, _ = contents[0]
        inner = sdt_xml[inner_start:inner_end]
        rendered = "" if value.value is None else str(value.value)
        new_inner = _rewrite_sdt_content(inner, rendered)
        xml = (
            xml[:el_start]
            + sdt_xml[:inner_start]
            + new_inner
            + sdt_xml[inner_end:]
            + xml[el_end:]
        )
        written.append(raw_tag or "")

    new_document = xml.encode("utf-8")
    changed = new_document != parts[WORD_DOCUMENT_PART]
    parts[WORD_DOCUMENT_PART] = new_document

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as out:
        for name, compress in order:
            out.writestr(zipfile.ZipInfo(name), parts[name], compress_type=compress)

    produced = output.read_bytes()
    after = _fingerprint_or_fail(
        produced, where=f"entry {binding.entry_id} materialize result"
    )
    aspects = after.aspect_digests()
    inventory = hashlib.sha256(
        "\n".join(
            f"{node.tag}\t{node.xpath}\t{node.container_path}"
            for node in sorted(after.sdt_nodes, key=lambda n: (n.tag, n.xpath))
            if node.tag
        ).encode("utf-8")
    ).hexdigest()
    structure = hashlib.sha256(
        "\n".join(f"{k}={aspects[k]}" for k in sorted(aspects)).encode("utf-8")
    ).hexdigest()
    return WordMaterializeOutcome(
        result=MaterializeResult(
            output_path=output,
            document_type=WORD_DOCUMENT_TYPE,
            artifact_sha256=hashlib.sha256(produced).hexdigest(),
            structure_hash=structure,
            identity_inventory_sha256=inventory,
            managed_field_count=len(projection.values),
        ),
        written_tags=tuple(sorted(written)),
        skipped_container_tags=tuple(sorted(skipped)),
        document_part_changed=changed,
        untouched_part_count=len(order) - 1,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. Word-only 保留与反读门
# ═══════════════════════════════════════════════════════════════════════════


def verify_word_only_regions(
    *,
    before: Path,
    after: Path,
    binding: WordEngineBinding,
    allow_added_outside_texts: Sequence[str] = (),
    allow_removed_outside_texts: Sequence[str] = (),
) -> UnmanagedRegionReport:
    """SDT 外正文 / 层级 / 表格形状 / 受保护部件 / 行身份逐 aspect 等价（Property 31）。

    ═══ 两条防「空集恒等价」的硬判据 ═══

    1. `word_sdt_fingerprint.body_preservation_report` 的 `row_uuid_set` 一格用旧
       `gtsdt/v1` 解析器，在本方案下两侧恒空 ⇒ 恒真。本函数**不采用**那一格，改用
       :func:`_row_uuid_index` 自己算 `managed_row_identity`。
    2. 每个 aspect 的**覆盖计数**必须 > 0（`details["coverage"]`）。手搓的最小 DOCX 上
       「SDT 外正文」是空集、「受保护部件」是空 dict，此时 `equivalent=True` 是空转；
       守卫据 `coverage` 断言 fixture 用的是真实权威模板。
    """
    before_bytes = before.read_bytes()
    after_bytes = after.read_bytes()
    report = body_preservation_report(
        before_bytes,
        after_bytes,
        label_before="substrate",
        label_after="result",
        allow_added_outside_texts=allow_added_outside_texts,
        allow_removed_outside_texts=allow_removed_outside_texts,
        allow_tag_additions=True,
    )
    if any(report["collection_errors"].values()):
        raise WordEngineError(
            f"entry {binding.entry_id}: Word-only 保留报告的采集侧报错 "
            f"{report['collection_errors']} —— 不得把采集失败当成「没有差异」"
        )

    fp_before = _fingerprint_or_fail(before_bytes, where="word-only before")
    fp_after = _fingerprint_or_fail(after_bytes, where="word-only after")
    rows_before = _row_uuid_index(fp_before)
    rows_after = _row_uuid_index(fp_after)
    lost_rows = {
        key: sorted(set(value) - set(rows_after.get(key, ())))
        for key, value in rows_before.items()
        if set(value) - set(rows_after.get(key, ()))
    }

    verdicts = {
        aspect: bool(report["aspect_verdicts"][aspect])
        for aspect in WORD_ONLY_ASPECTS
        if aspect in report["aspect_verdicts"]
    }
    verdicts["managed_row_identity"] = not lost_rows

    coverage = {
        "outside_sdt_text": len(fp_before.outside_sdt_texts()),
        "sdt_tag_set": len(fp_before.tag_set()),
        "sdt_hierarchy": len(fp_before.hierarchy_map()),
        "table_shape": len(fp_before.table_shapes),
        "protected_parts": sum(len(v) for v in fp_before.protected_parts.values()),
        "managed_row_identity": sum(len(v) for v in rows_before.values()),
    }

    failed = [aspect for aspect, ok in sorted(verdicts.items()) if not ok]
    first_difference: str | None = None
    if failed:
        aspect = failed[0]
        detail = (
            lost_rows
            if aspect == "managed_row_identity"
            else report["aspects"].get(aspect)
        )
        first_difference = f"{aspect}: {detail}"
    return UnmanagedRegionReport(
        equivalent=not failed,
        inspected_aspects=tuple(sorted(verdicts)),
        first_difference=first_difference,
        details={
            "aspect_verdicts": verdicts,
            "coverage": coverage,
            "lost_row_identity": lost_rows,
            "report": report["aspects"],
        },
    )


@dataclass(frozen=True)
class WordVerificationBundle:
    """commit / candidate finalize 之前的三条判据（AC 6.11 / 8.11 / Property 65）。"""

    extracted: WordExtractOutcome
    unmanaged: UnmanagedRegionReport
    mismatched_keys: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.mismatched_keys and self.unmanaged.equivalent

    def assert_publishable(self) -> None:
        """三条判据各抛**自己**的类型 —— 不包统一异常（否则哪条在起作用不可分辨）。"""
        if self.mismatched_keys:
            raise WordManagedProjectionMismatchError(
                f"反读的受管字段与期望不等值: {list(self.mismatched_keys)} —— "
                "HTML projection / current pointer / last-applied / client-confirmed base "
                "均不得推进（AC 8.11）"
            )
        self.unmanaged.assert_equivalent()

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "mismatched_keys": list(self.mismatched_keys),
            "unmanaged_equivalent": self.unmanaged.equivalent,
            "unmanaged_first_difference": self.unmanaged.first_difference,
            "unmanaged_coverage": dict(self.unmanaged.details.get("coverage", {})),
            "extracted": self.extracted.as_dict(),
        }


def verify_word_before_commit(
    *,
    expected: Projection,
    staged_result: Path,
    substrate: Path,
    binding: WordEngineBinding,
    limits: SyncLimits | None = None,
) -> WordVerificationBundle:
    """反读刚写出的 staged result 并与期望 projection 类型化比对 + Word-only 等价。

    `substrate_role=staged_result` 是 Task 37 为这一步专门加的角色：既不是 incoming
    也不是 published，用前两者中任何一个声明都会说谎。
    """
    lim = limits or load_limits()
    extracted = extract_word_projection(
        artifact=staged_result,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
        limits=lim,
    )
    mismatched: list[str] = []
    for key, want in sorted(expected.values.items()):
        got = extracted.projection.get(key)
        if got is None:
            mismatched.append(key)
            continue
        if _canonical(want) != _canonical(got):
            mismatched.append(key)
    unmanaged = verify_word_only_regions(
        before=substrate, after=staged_result, binding=binding
    )
    return WordVerificationBundle(
        extracted=extracted,
        unmanaged=unmanaged,
        mismatched_keys=tuple(mismatched),
    )


def _canonical(value: FieldValue) -> tuple[str, str]:
    """类型化等值口径：`(value_type, 规范化文本)`。

    对文本走 `normalise_text`（OO 会重排 run、拆合 `w:t`），对数值走 `str` ——
    刻意不比 Python 对象：`Decimal("1.0") != Decimal("1.00")` 会让等值判据在
    「OO 只是重序列化」上翻脸。
    """
    if value.value is None:
        return (value.value_type.value, "")
    if value.value_type is ValueType.text:
        return (value.value_type.value, normalise_text(str(value.value)))
    return (value.value_type.value, str(value.value))


# ═══════════════════════════════════════════════════════════════════════════
# 7. 两条方向固定的入口（substrate 角色写死，不参数化）
# ═══════════════════════════════════════════════════════════════════════════


def materialize_word_for_editing(
    *,
    current_representation: Path,
    projection: Projection,
    output: Path,
    binding: WordEngineBinding,
    limits: SyncLimits | None = None,
) -> tuple[WordMaterializeOutcome, WordVerificationBundle]:
    """HTML→OO：以**当前 published canonical Word** 为底（不以原模板重建）。

    design §Word materialize 第 1 条。substrate 角色/kind/state 三项写死成
    `published_representation / canonical / published` —— 参数化会让「OO→HTML 误用
    published representation 当底」在类型上合法。
    """
    lim = limits or load_limits()
    materialized = materialize_word_projection(
        substrate=current_representation,
        projection=projection,
        output=output,
        binding=binding,
        substrate_role=SubstrateRole.published_representation,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.published,
        limits=lim,
    )
    verification = verify_word_before_commit(
        expected=projection,
        staged_result=materialized.output_path,
        substrate=current_representation,
        binding=binding,
        limits=lim,
    )
    return materialized, verification


def rematerialize_word_merged_projection(
    *,
    merged: Projection,
    incoming_substrate: Path,
    output: Path,
    binding: WordEngineBinding,
    incoming_state: ArtifactState = ArtifactState.durable,
    limits: SyncLimits | None = None,
) -> tuple[WordMaterializeOutcome, WordVerificationBundle]:
    """OO→HTML：只以 application 固定的 `kind=incoming,state=durable` artifact 为**只读**底。

    AC 8.10：incoming 本身永不成为 published representation / current pointer /
    resolver 输出；本函数只在独立 staging 里重写结构化岛，并把 Word-only 区域与
    **incoming** 比对（不是与模板比 —— 与模板比会把审计师的自由正文判成「漂移」）。

    `incoming_state` 由调用方传入，因此 quarantined 与「未 durable」两种形态各自被
    Task 13 的专属类型在 engine 入口拒掉，而不是靠本函数记得检查。
    """
    lim = limits or load_limits()
    materialized = materialize_word_projection(
        substrate=incoming_substrate,
        projection=merged,
        output=output,
        binding=binding,
        substrate_role=SubstrateRole.incoming,
        artifact_kind=ArtifactKind.incoming,
        artifact_state=incoming_state,
        limits=lim,
    )
    verification = verify_word_before_commit(
        expected=merged,
        staged_result=materialized.output_path,
        substrate=incoming_substrate,
        binding=binding,
        limits=lim,
    )
    return materialized, verification
