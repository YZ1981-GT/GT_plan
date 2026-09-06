# -*- coding: utf-8 -*-
"""Excel instrumentation definition 与 **non-current** representation upgrade candidate 生成器。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 17
Requirements: 2.1, 2.3, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.19, 9.1, 9.8, 9.9,
9.10, 14.16
Properties: **P28**（immutable definition 漂移 fail closed）/ **P66**（只用真实 OO 探针
通过的载体）/ **P67**（upgrader 先 candidate、approved bundle 后 finalize）/
**P71**（evidence 随环境/runner/definition 变化失效）

═══ 一、本模块**能**做什么、**不能**做什么（否定式承诺是核心） ═══

能做（发布 DAG 的前两段 + candidate 登记）::

    template definition ──► instrumentation definition ──► non-current candidate
    （publish template blob）  （只单向引用 template digest）  （staged / awaiting_contract）

**不能**做，且每一条都有可执行判据而不是注释：

======================================  ===============================================
禁令                                     判据落点
======================================  ===============================================
不得创建 published/current representation :class:`CandidateOnlyRepository` 恒抛
不得切 entry pointer                     :class:`CandidateOnlyRepository` 恒抛
不得 finalize candidate                  :class:`CandidateOnlyRepository` 恒抛
不得递增 content revision                 :class:`CandidateOnlyRepository`（含 Task 15
                                         的 `REVISION_DOMAIN_WRITE_METHODS` 全集）
不得伪造 contract / authority / bundle    :meth:`ExcelInstrumentationUpgrader.
                                         register_candidate` 的三个 target 字段恒为
                                         None，并由 :func:`assert_candidate_is_non_current`
                                         逐字段实测
instrumentation payload 不含自身 UUID/hash Task 12 `validate_instrumentation_payload`
instrumentation payload 不含 contract/    同上（`_BACKWARD_REFERENCE_PREFIXES`）
bundle digest
`_GT_SYNC` 不得预写 runtime binding       :func:`assert_no_runtime_binding`
不得用 sheetId / sheet 展示名当锚点        :class:`ExcelIdentityCarrierGate`
                                         `forbidden_anchors` + 反读只走 table 路径
不得改动权威模板本体                       :meth:`ExcelInstrumentationUpgrader.
                                         instrument_source_bytes` 只吃 bytes，
                                         并由守卫在跑完后核 `backend/wp_templates/`
                                         的 sha256 未变
======================================  ===============================================

「不得创建 representation」为什么必须做成**门面**而不是「本模块没写那段代码」：
没写等于没有判据 —— 变异检验无法证明它被锁住，下一个人往这里加一行
`repo.create_representation(...)` 也不会有任何测试变红。Task 15 的
:class:`RevisionLockedRepository` 已经用这个形态锁死 revision 域，本模块把它扩到
representation/pointer/finalize 三个方法上（**包含** Task 15 的 revision 三件套，
`_CANDIDATE_FORBIDDEN` 是二者的并集）。

═══ 二、载体选择完全由 Task 5 的真实 OO 9.4 探针裁决约束 ═══

`backend/data/onlyoffice_excel_identity_carrier_contract.json` 是唯一真源。
:class:`ExcelIdentityCarrierGate` 逐 carrier / 逐 anchor 读 `probe_verdict`，见到
`failed` / `not_covered` 即 fail closed。实测裁决（findings.md §3）::

    hidden_sheet / defined_name / excel_table / hidden_uuid_column  → passed
    defined_name_ref / excel_table_sheet_association（锚点）        → passed
    sheet_id / sheet_display_name（锚点）                          → **failed**

`sheet_id` 被证伪的后果很硬：OO 9.4 **每次保存**都把 `sheetId` 按 tab 顺序重编号为
`1..N`（15/15 个回传 artifact 全部如此，第一个失败的操作只是「打开→改一格→forcesave」）。
所以本模块的反读（:meth:`~ExcelInstrumentationUpgrader.read_back_identity`）
**只传** `expected_table` + `uuid_column_letter`，让 `identity_inventory()` 走
`table_sheet` 这一条路径；`uuid_sheet_id` / `uuid_sheet_name` 一个都不传 ⇒ 结构上
不可能退化到被证伪的锚点上（而不是「代码里记得别传」）。

也正因为 sheet 改名后只剩 Table 一条路径可用（`defined_name` 的 ref 会被 OO 自动改写
成新名，可定位 sheet 但不给区域边界），Excel Table 在生产 instrumentation 里是
**必需项**：:class:`ExcelInstrumentationSpec` 没有「不注 Table」的开关。Task 5 里
C24 未注 Table 只是因为那份文档专用于 chart 部件取证，契约已把这一点写成
「Table 载体对生产是必需项而非可选项」的实证理由。

═══ 三、visible-equivalence 是真比对，不是声明 ═══

:func:`~app.services.excel_structure_fingerprint.visible_equivalence_report` 逐
aspect（可见 sheet / 业务值 / 公式 / 样式 / merge / drawing·chart·pivot 受保护部件）
比对注入前后两份字节，白名单只有四样：隐藏 `_GT_SYNC`、`GT_` defined names、受管
sheet 上那一列隐藏 UUID、`headerRowCount=0` 的 Table 部件。Task 5 实测 K11/C24 六个
aspect 全 0 diff，且 C24 的 8 chart / 3 drawing / 1 media 字节未变。

**不用字节口径**：Task 5 的控制组证明 OO 往返本身会重映射 487 处填充色、替换字体、
压平长公式（不带 instrumentation 也一样），按 protected-part 字节 digest 判等会让
每次 OO 保存都误判成结构漂移。本模块的等价判定只发生在「注入前 vs 注入后」这一对
**都没过 OO** 的字节上，因此 strict 口径成立且必须成立。

═══ 四、Property 71 在本任务的落点 ═══

Task 5 契约自己声明了 `stale_policy.invalidate_on` 四项（OO build / 两份源模板
sha256 / probe 脚本与 fingerprint 模块 / evidence 两份 JSON）。
:class:`ExcelIdentityCarrierGate` 把这四项落成机器比对：Tier A（全在 `backend/` 下，
生产必然存在）在 `load()` 里无条件强制；Tier B（`.kiro/specs/**` 的 evidence）由
:meth:`~ExcelIdentityCarrierGate.assert_evidence_fresh` 在仓库上下文强制，
**evidence 目录缺失本身即判 stale**，不降级为 skip。基线见
`backend/data/onlyoffice_excel_instrumentation_gate.json`。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Iterable, Mapping, Sequence

from app.services.excel_structure_fingerprint import (
    GT_SYNC_SHEET_NAME,
    FingerprintError,
    identity_inventory,
    structure_fingerprint,
    visible_equivalence_report,
)
from app.services.workpaper_sync import excel_typography_rows as _typography
from app.services.workpaper_sync.canonical_paths import (
    TEMPLATE_ROOT,
    PathBoundaryError,
    resolve_within_root,
)
from app.services.workpaper_sync.definitions import (
    DefinitionPublisher,
    PublishStage,
    canonical_digest,
    canonical_json_bytes,
    validate_instrumentation_payload,
    validate_template_payload,
)
from app.services.workpaper_sync.models import (
    CandidateState,
    DefinitionKind,
    SyncDomainError,
    is_digest,
)

__all__ = [
    "InstrumentationError",
    "CarrierGateError",
    "ProbeEvidenceStaleError",
    "ForbiddenAnchorError",
    "VisibleEquivalenceError",
    "IdentityReadbackError",
    "RuntimeBindingForbiddenError",
    "CandidateSurfaceForbiddenError",
    "ExcelIdentityCarrierGate",
    "ExcelInstrumentationSpec",
    "InstrumentedWorkbook",
    "CandidateOnlyRepository",
    "UpgradeCandidateOutcome",
    "ExcelInstrumentationUpgrader",
    "INSTRUMENTATION_SCHEMA_VERSION",
    "TEMPLATE_SCHEMA_VERSION",
    "IDENTITY_SCHEMA_VERSION",
    "INSTRUMENTATION_VERSION",
    "RUNTIME_BINDING_KEYS",
    "REQUIRED_GT_SYNC_KEYS",
    "CANDIDATE_FORBIDDEN_METHODS",
    "GATE_CONTRACT_PATH",
    "GATE_BASELINE_PATH",
    "assert_no_runtime_binding",
    "assert_candidate_is_non_current",
    "build_instrumentation_payload",
    "build_template_payload",
    "instrument_workbook_bytes",
    "verify_visible_equivalence",
    "read_back_identity",
    "normalized_structure_hash",
    "TEMPLATE_AUTHORITY_ROOT",
]

# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量与路径
# ═══════════════════════════════════════════════════════════════════════════

#: 仓库根（`backend/app/services/workpaper_sync/x.py` → 上溯 4 层是 `backend/`）。
_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_REPO_ROOT: Final[Path] = _BACKEND_ROOT.parent

#: Task 5 载体裁决契约（**唯一**真源）。
GATE_CONTRACT_PATH: Final[Path] = (
    _BACKEND_ROOT / "data" / "onlyoffice_excel_identity_carrier_contract.json"
)
#: Task 17 的 stale-policy digest 基线。
GATE_BASELINE_PATH: Final[Path] = (
    _BACKEND_ROOT / "data" / "onlyoffice_excel_instrumentation_gate.json"
)
#: 运行时权威模板源（Requirement 9.1）。参考副本一律不认。
#: 🔴 直接 alias 到 `canonical_paths.TEMPLATE_ROOT`，**不重新拼一次** `_BACKEND_ROOT /
#: "wp_templates"` —— 那会形成第二份「权威模板根」真源，Task 12 把模板根收敛成单一
#: 常量的意义就丢了（改一处另一处不红）。
TEMPLATE_AUTHORITY_ROOT: Final[Path] = TEMPLATE_ROOT

TEMPLATE_SCHEMA_VERSION: Final[str] = "template-definition:v1"
INSTRUMENTATION_SCHEMA_VERSION: Final[str] = "instrumentation-definition:v1"
IDENTITY_SCHEMA_VERSION: Final[str] = "1.0.0"
INSTRUMENTATION_VERSION: Final[str] = "1.0.0"

#: `_GT_SYNC` 里 Task 5 契约声明的必备键（`carriers[hidden_sheet].required_keys`）。
#: 这里**不复制**契约里的清单，只声明「本模块要写哪些」；守卫按契约反向核对二者一致。
REQUIRED_GT_SYNC_KEYS: Final[tuple[str, ...]] = (
    "GT_SYNC_SCHEMA_VERSION",
    "GT_IDENTITY_SCHEMA_VERSION",
    "GT_INSTRUMENTATION_VERSION",
    "GT_TEMPLATE_ID",
    "GT_TEMPLATE_SHA256",
    "GT_MANAGED_SHEET_ID",
    "GT_ROW_UUID_COLUMN",
)

#: **只能在 representation finalize 时**写进 `_GT_SYNC` 的 runtime binding 键
#: （design §Excel instrumentation contract）。本任务的 instrumentation 阶段一个都
#: 不许写：那五个 digest 里有三个（contract / bundle / authority model）此刻**根本
#: 还不存在**，预留一个空位或写占位值都会让 candidate 看起来像已绑定 bundle。
RUNTIME_BINDING_KEYS: Final[tuple[str, ...]] = (
    "GT_AUTHORITY_MODEL_DEFINITION_SHA256",
    "GT_TEMPLATE_DEFINITION_SHA256",
    "GT_INSTRUMENTATION_DEFINITION_SHA256",
    "GT_CONTRACT_DEFINITION_SHA256",
    "GT_DEFINITION_BUNDLE_SHA256",
)

#: candidate 生成路径上**不可达**的仓储方法。
#:
#: 前三个是本任务新增的禁令（representation / pointer / finalize），后三个来自
#: Task 15 的 `REVISION_DOMAIN_WRITE_METHODS` —— 用 import 取并集而不是手抄，
#: 否则 Task 15 那边加一个 revision writer，这里就漏一个。
def _candidate_forbidden_methods() -> frozenset[str]:
    from app.services.workpaper_sync.content_mutation import REVISION_DOMAIN_WRITE_METHODS

    return frozenset(
        {"create_representation", "set_entry_pointer", "finalize_candidate"}
    ) | frozenset(REVISION_DOMAIN_WRITE_METHODS)


CANDIDATE_FORBIDDEN_METHODS: Final[frozenset[str]] = _candidate_forbidden_methods()

_MAIN_NS: Final[str] = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS: Final[str] = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_GT_SYNC_REL_ID: Final[str] = "rIdGTSYNC"
_GT_TABLE_REL_ID: Final[str] = "rIdGTTBL1"
_GT_SYNC_SHEET_PART: Final[str] = "xl/worksheets/sheetGtSync.xml"
_GT_TABLE_PART: Final[str] = "xl/tables/tableGtRowId.xml"

#: `<worksheet>` 里必须排在 `<tableParts>` **之前**的尾部元素（OOXML 顺序敏感）。
_SHEET_TAIL_ORDER: Final[tuple[str, ...]] = (
    "picture",
    "drawing",
    "legacyDrawing",
    "oleObjects",
    "controls",
    "webPublishItems",
    "extLst",
)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常（每条拒绝理由一个类型 —— 共用类型会让短路变异互相遮蔽）
# ═══════════════════════════════════════════════════════════════════════════


class InstrumentationError(SyncDomainError):
    error_code = "excel_instrumentation_failed"


class CarrierGateError(InstrumentationError):
    """载体/锚点未过真实 OO 探针（Requirement 6.16）。"""

    error_code = "identity_carrier_not_probed"


class ProbeEvidenceStaleError(InstrumentationError):
    """探针实证已 stale（OO build / 模板 / 脚本 / evidence 漂移，Requirement 14.16）。"""

    error_code = "probe_evidence_stale"


class ForbiddenAnchorError(InstrumentationError):
    """使用了被证伪的锚点（sheetId / sheet 展示名，Requirement 6.14）。"""

    error_code = "forbidden_identity_anchor"


class VisibleEquivalenceError(InstrumentationError):
    """instrumentation 破坏了可见业务结构（Requirement 6.17）。"""

    error_code = "visible_equivalence_violated"


class IdentityReadbackError(InstrumentationError):
    """反读拿不到预期 identity inventory（Requirement 6.15 / 6.20）。"""

    error_code = "identity_readback_failed"


class RuntimeBindingForbiddenError(InstrumentationError):
    """instrumentation 阶段预写了只属于 finalize 的 runtime binding（Requirement 6.14）。"""

    error_code = "runtime_binding_written_too_early"


class CandidateSurfaceForbiddenError(InstrumentationError):
    """candidate 生成路径触碰了 representation / pointer / finalize / revision 写入面。"""

    error_code = "candidate_stage_surface_forbidden"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 载体裁决门（Task 5 契约的 fail-closed loader + Property 71 stale 门）
# ═══════════════════════════════════════════════════════════════════════════


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def normalized_structure_hash(data: bytes) -> str:
    """workbook 的 normalized structure hash（Requirement 9.1 / 9.8 的漂移判据）。

    由 Task 5 的六个 aspect digest **按 aspect 名排序**折成一个 digest。刻意不用
    字节 sha256：字节会随 zip 压缩参数与部件顺序变化，而这个 hash 要回答的是
    「可见业务结构有没有变」。采集报错时抛，绝不返回一个「看起来正常」的 hash。
    """
    fingerprint = structure_fingerprint(data)
    if fingerprint.errors:
        raise InstrumentationError(f"结构指纹采集报错: {fingerprint.errors}")
    aspects = fingerprint.aspect_digests()
    joined = "\n".join(f"{name}={aspects[name]}" for name in sorted(aspects))
    return _sha256_bytes(joined.encode("utf-8"))


@dataclass(frozen=True)
class ExcelIdentityCarrierGate:
    """Task 5 载体裁决的机器可读投影。构造只能经 :meth:`load`。

    `allowed_carriers` / `allowed_anchors` 全部**从契约实测裁决反算**，不是抄
    `gate_for_downstream_tasks` 里那份清单：抄清单时，若某天有人把 carrier 的
    `probe_verdict` 改成 failed 却忘了改清单，loader 会照旧放行。这里两侧都读，
    并断言二者一致（:meth:`_assert_gate_matches_verdicts`）。
    """

    contract_sha256: str
    onlyoffice_build: str
    allowed_carriers: frozenset[str]
    allowed_anchors: frozenset[str]
    forbidden_anchors: frozenset[str]
    required_hidden_sheet_keys: tuple[str, ...]
    #: `{'K11': 'dc0e…', 'C24': 'b702…'}` —— 探针覆盖过的模板及其权威源 digest。
    probed_template_digests: Mapping[str, str]
    #: `requirement_6_15_classification` 的三类处置（空 UUID / 重复 UUID / 删列）。
    row_uuid_classification: Mapping[str, Mapping[str, Any]]

    # ─────────────────────────────────────────────────────────────

    @classmethod
    def load(
        cls,
        *,
        contract_path: Path | None = None,
        baseline_path: Path | None = None,
        template_root: Path | None = None,
    ) -> "ExcelIdentityCarrierGate":
        """读契约 + 逐条查 `probe_verdict` + Tier A stale 门。任一不合格即 fail closed。"""
        contract_file = contract_path or GATE_CONTRACT_PATH
        baseline_file = baseline_path or GATE_BASELINE_PATH
        for label, path in (("carrier contract", contract_file), ("gate baseline", baseline_file)):
            if not path.is_file():
                raise ProbeEvidenceStaleError(
                    f"{label} 文件不存在: {path} —— 缺实证依据一律 fail closed，"
                    "不得按默认值放行 instrumentation（Requirement 6.16）"
                )
        contract = json.loads(contract_file.read_text(encoding="utf-8"))
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))

        cls._assert_tier_a_fresh(
            baseline, contract_file=contract_file, template_root=template_root
        )

        carriers = {c["carrier"]: c for c in contract["carriers"]}
        anchors = {a["anchor"]: a for a in contract["anchors"]}
        passed_carriers = frozenset(
            name for name, c in carriers.items() if c.get("probe_verdict") == "passed"
        )
        passed_anchors = frozenset(
            name for name, a in anchors.items() if a.get("probe_verdict") == "passed"
        )
        failed_anchors = frozenset(
            name for name, a in anchors.items() if a.get("probe_verdict") != "passed"
        )
        gate = contract["gate_for_downstream_tasks"]["task_17_instrumentation_definition"]
        cls._assert_gate_matches_verdicts(
            gate,
            passed_carriers=passed_carriers,
            passed_anchors=passed_anchors,
            failed_anchors=failed_anchors,
        )

        hidden = carriers.get("hidden_sheet") or {}
        uuid_carrier = carriers.get("hidden_uuid_column") or {}
        return cls(
            contract_sha256=_sha256_path(contract_file),
            onlyoffice_build=str(baseline["tier_a_runtime"]["onlyoffice_build"]),
            allowed_carriers=passed_carriers,
            allowed_anchors=passed_anchors,
            forbidden_anchors=failed_anchors,
            required_hidden_sheet_keys=tuple(hidden.get("required_keys") or ()),
            probed_template_digests={
                str(t["template_id"]): str(t["sha256"])
                for t in baseline["tier_a_runtime"]["probed_templates"]
            },
            row_uuid_classification=dict(
                uuid_carrier.get("requirement_6_15_classification") or {}
            ),
        )

    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _assert_tier_a_fresh(
        baseline: Mapping[str, Any], *, contract_file: Path, template_root: Path | None
    ) -> None:
        """Tier A：契约本体 + fingerprint 模块 + 两份权威模板的 digest 必须与基线一致。"""
        tier = baseline["tier_a_runtime"]
        for item in tier["files"]:
            path = _REPO_ROOT / item["path"]
            # 契约文件允许由调用方重定向（守卫会用副本做变异），其余固定路径。
            if item["role"] == "carrier_contract":
                path = contract_file
            if not path.is_file():
                raise ProbeEvidenceStaleError(
                    f"stale 门输入缺失: {item['role']} → {path}"
                )
            observed = _sha256_path(path)
            if observed != item["sha256"]:
                raise ProbeEvidenceStaleError(
                    f"{item['role']} digest 漂移：基线 {item['sha256'][:12]}… ≠ 实测 "
                    f"{observed[:12]}…（{item['path']}）—— Task 5 探针裁决已 stale，"
                    "必须重跑探针并重新裁决 probe_verdict，不得沿用旧裁决"
                    "（Requirement 14.16 / Property 71）"
                )
        root = template_root or TEMPLATE_AUTHORITY_ROOT
        for item in tier["probed_templates"]:
            rel = str(item["path"])
            path = (
                root / rel.split("wp_templates/", 1)[1]
                if "wp_templates/" in rel
                else _REPO_ROOT / rel
            )
            if not path.is_file():
                raise ProbeEvidenceStaleError(
                    f"探针覆盖的权威模板缺失: {item['template_id']} → {path}"
                )
            observed = _sha256_path(path)
            if observed != item["sha256"]:
                raise ProbeEvidenceStaleError(
                    f"权威模板 {item['template_id']} digest 漂移：基线 "
                    f"{item['sha256'][:12]}… ≠ 实测 {observed[:12]}… —— 探针文档已变，"
                    "载体裁决 stale"
                )

    @staticmethod
    def _assert_gate_matches_verdicts(
        gate: Mapping[str, Any],
        *,
        passed_carriers: frozenset[str],
        passed_anchors: frozenset[str],
        failed_anchors: frozenset[str],
    ) -> None:
        """`gate_for_downstream_tasks` 的三份清单必须与逐条 `probe_verdict` 反算一致。"""
        declared_carriers = frozenset(gate["allowed_carriers"])
        declared_allowed = frozenset(gate["allowed_anchors"])
        declared_forbidden = frozenset(gate["forbidden_anchors"])
        if declared_carriers != passed_carriers:
            raise CarrierGateError(
                "契约 gate.allowed_carriers 与逐 carrier probe_verdict 反算不一致："
                f"声明 {sorted(declared_carriers)} ≠ 实测 passed {sorted(passed_carriers)}"
                " —— 两侧必须互锁，否则改一侧即可悄悄放行未过门的载体"
            )
        if declared_allowed != passed_anchors:
            raise CarrierGateError(
                "契约 gate.allowed_anchors 与逐 anchor probe_verdict 反算不一致："
                f"声明 {sorted(declared_allowed)} ≠ 实测 passed {sorted(passed_anchors)}"
            )
        if declared_forbidden != failed_anchors:
            raise CarrierGateError(
                "契约 gate.forbidden_anchors 与逐 anchor probe_verdict 反算不一致："
                f"声明 {sorted(declared_forbidden)} ≠ 实测非 passed {sorted(failed_anchors)}"
            )
        if not declared_forbidden:
            raise CarrierGateError(
                "forbidden_anchors 为空 —— Task 5 已证伪 sheet_id 与 sheet 展示名两个锚点，"
                "空集意味着契约被改坏或读错了字段"
            )

    # ─────────────────────────────────────────────────────────────

    def assert_evidence_fresh(self, *, baseline_path: Path | None = None) -> dict[str, str]:
        """Tier B：probe 脚本与 evidence JSON 的 digest 必须与基线一致。

        返回实测 digest 映射（供 evidence 报告记录）。**缺文件即判 stale**，
        不 skip —— skip 会把「实证没了」伪装成「无需检查」。
        """
        baseline = json.loads((baseline_path or GATE_BASELINE_PATH).read_text(encoding="utf-8"))
        observed: dict[str, str] = {}
        for item in baseline["tier_b_evidence"]["files"]:
            path = _REPO_ROOT / item["path"]
            if not path.is_file():
                raise ProbeEvidenceStaleError(
                    f"evidence 输入缺失: {item['role']} → {path} —— evidence 不可复现即判 stale"
                )
            got = _sha256_path(path)
            observed[item["role"]] = got
            if got != item["sha256"]:
                raise ProbeEvidenceStaleError(
                    f"{item['role']} digest 漂移：基线 {item['sha256'][:12]}… ≠ 实测 "
                    f"{got[:12]}… —— 旧 test run/evidence 自动 stale，capability 不再计入已验收"
                )
        return observed

    def assert_carrier_allowed(self, carrier: str) -> None:
        if carrier not in self.allowed_carriers:
            raise CarrierGateError(
                f"载体 {carrier!r} 未通过真实 OO 9.4 探针（allowed={sorted(self.allowed_carriers)}）"
                " —— Requirement 6.16 禁止建设依赖未过门载体的 engine"
            )

    def assert_anchor_allowed(self, anchor: str) -> None:
        """锚点门。**先查 forbidden 再查 allowed**，让被证伪的锚点得到专属异常类型。"""
        if anchor in self.forbidden_anchors:
            raise ForbiddenAnchorError(
                f"锚点 {anchor!r} 已被 Task 5 探针证伪（probe_verdict=failed）："
                "OO 9.4 每次保存都把 sheetId 按 tab 顺序重编号、sheet 展示名可被用户改名 ⇒ "
                "两者都不得作为运行时定位锚点（Requirement 6.14）"
            )
        if anchor not in self.allowed_anchors:
            raise CarrierGateError(
                f"锚点 {anchor!r} 不在探针通过清单 {sorted(self.allowed_anchors)} 内"
            )

    def assert_template_under_authority(self, relative_path: str) -> Path:
        """模板必须位于 `backend/wp_templates/` 之内（Requirement 9.1）。

        🔴 边界判据**委托** :func:`canonical_paths.resolve_within_root`，本模块不自写
        `not in x.parents`。理由与 Task 12 相同：整个同步域只允许一份边界实现，否则
        「软链接越界」这类判据改一处另一处不红。这里只负责把 `PathBoundaryError`
        包成本模块的 :class:`InstrumentationError`（保留 Task 17 的 error 语义）。
        """
        rel = relative_path.replace("\\", "/").strip("/")
        if rel.startswith("backend/wp_templates/"):
            rel = rel.split("backend/wp_templates/", 1)[1]
        try:
            target = resolve_within_root(
                TEMPLATE_AUTHORITY_ROOT, rel, boundary="template_authority_root"
            )
        except PathBoundaryError as exc:
            raise InstrumentationError(
                f"模板 {relative_path!r} 不在权威源 backend/wp_templates/ 之内 —— "
                "参考副本（基础数据/致同通用审计程序及底稿模板…）已落后，不得据它 instrumentation"
                f"（Requirement 9.1 / 9.9）：{exc}"
            ) from exc
        if not target.is_file():
            raise InstrumentationError(f"权威模板不存在: {target}")
        return target


# ═══════════════════════════════════════════════════════════════════════════
# 3. 声明式 instrumentation 清单（Requirement 9.9：只能经声明式迁移清单增加）
# ═══════════════════════════════════════════════════════════════════════════


def _col_index(letters: str) -> int:
    idx = 0
    for ch in letters.upper():
        idx = idx * 26 + (ord(ch) - 64)
    return idx


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@dataclass(frozen=True)
class ExcelInstrumentationSpec:
    """一个 entry 的 instrumentation 声明。

    `managed_sheet` 是**构建期**选择器：它针对一个已固定 `template_sha256` 的模板
    定位要注入的 sheet。这与 Requirement 6.14 的「identity 不得依赖 sheet 展示名」
    不矛盾 —— 被禁的是**运行时**按展示名定位；发布出去的 canonical payload 里，
    locator 只写 defined name 与 Table displayName（见
    :func:`build_instrumentation_payload`）。

    没有 `inject_table` 开关：Table 是生产必需项（见模块 docstring §二）。
    """

    entry_id: str
    template_id: str
    #: `backend/wp_templates/` 下的相对路径（也接受带 `backend/wp_templates/` 前缀）
    template_relative_path: str
    managed_sheet: str
    first_data_row: int
    last_data_row: int
    footer_row: int
    #: 受管业务列的最后一列（Table 覆盖 A 列到 UUID 列）
    managed_last_col: str
    #: 隐藏 row UUID 列列标（必须在 `managed_last_col` 右侧，避免压住业务列）
    uuid_col: str
    table_name: str
    semantic_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise InstrumentationError("entry_id 不得为空")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.table_name or ""):
            raise InstrumentationError(
                f"Excel Table displayName 非法: {self.table_name!r}"
                "（OOXML 要求以字母/下划线开头、不含空格）"
            )
        if self.first_data_row < 1 or self.last_data_row < self.first_data_row:
            raise InstrumentationError(
                f"受管行区间非法: {self.first_data_row}..{self.last_data_row}"
            )
        if self.footer_row <= self.last_data_row:
            raise InstrumentationError(
                f"footer_row {self.footer_row} 必须在受管行区间之后 —— "
                "footer 落在动态行内会被插删行推走"
            )
        if _col_index(self.uuid_col) <= _col_index(self.managed_last_col):
            raise InstrumentationError(
                f"隐藏 UUID 列 {self.uuid_col} 必须在受管业务列 {self.managed_last_col} 右侧，"
                "否则会覆盖可见业务单元格（Requirement 6.13：不得改变业务公式/标签）"
            )

    @property
    def managed_range(self) -> str:
        return f"A{self.first_data_row}:{self.managed_last_col}{self.last_data_row}"

    @property
    def table_ref(self) -> str:
        return f"A{self.first_data_row}:{self.uuid_col}{self.last_data_row}"

    @property
    def row_count(self) -> int:
        return self.last_data_row - self.first_data_row + 1

    def defined_names(self) -> tuple[tuple[str, str, bool], ...]:
        """`(name, ref_template, sheet_local)`；ref 里的 sheet 名在注入时按实际名填。"""
        return (
            (f"GT_MANAGED_REGION_{self.template_id}", "{sheet}!$A${first}:${last_col}${last}", False),
            (f"GT_FOOTER_ANCHOR_{self.template_id}", "{sheet}!$A${footer}", False),
            (f"GT_SYNC_ANCHOR_{self.template_id}", f"{GT_SYNC_SHEET_NAME}!$A$1", False),
            (f"GT_ROW_UUID_RANGE_{self.template_id}", "{sheet}!${uuid_col}${first}:${uuid_col}${last}", True),
        )

    def row_uuid(self, row: int) -> str:
        """预生成字面量（Requirement 6.14：不得用可重算公式）。"""
        return f"GTROW-{self.template_id}-{row:04d}"


# ═══════════════════════════════════════════════════════════════════════════
# 4. canonical payload
# ═══════════════════════════════════════════════════════════════════════════


def build_template_payload(*, spec: ExcelInstrumentationSpec, template_sha256: str,
                           structure_hash: str) -> dict[str, Any]:
    """template definition 的 canonical payload（发布 DAG 第一段）。"""
    if not is_digest(template_sha256):
        raise InstrumentationError(f"template_sha256 非法: {template_sha256!r}")
    payload = {
        "schema_version": TEMPLATE_SCHEMA_VERSION,
        "template_id": spec.template_id,
        "template_relative_path": f"backend/wp_templates/{spec.template_relative_path.replace(chr(92), '/').split('backend/wp_templates/')[-1].lstrip('/')}",
        "template_sha256": template_sha256,
        "normalized_structure_hash": structure_hash,
        "authority_root": "backend/wp_templates",
    }
    validate_template_payload(payload)
    return payload


def build_instrumentation_payload(
    *,
    spec: ExcelInstrumentationSpec,
    template_definition_sha256: str,
    template_sha256: str,
    gate: ExcelIdentityCarrierGate,
    identity_anchors: Sequence[str] = ("defined_name_ref", "excel_table_sheet_association"),
) -> dict[str, Any]:
    """instrumentation definition 的 canonical semantic payload。

    四条硬约束（Requirement 6.14），每条都由**别处的判据**兜住而不是靠这里写对：

    1. 不含自身 UUID/hash → Task 12 `validate_instrumentation_payload` 的
       `_assert_no_self_reference`（禁 `id` / `sha256` / `artifact_id` … 等键名）；
    2. 不含 contract/bundle 反向引用 → 同一函数的 `_BACKWARD_REFERENCE_PREFIXES`；
    3. 单向引用已发布 template digest → 同一函数强制 `template_definition_sha256`；
    4. 不依赖被证伪的锚点 → 本函数逐个 `gate.assert_anchor_allowed(...)`。

    **payload 里没有 sheetId、没有 sheet 展示名、没有中文 label、没有单元格坐标当
    identity**：受管 sheet 由 defined name 定位、受管行区域边界由 Table 定位、行身份
    由隐藏列里的字面量 UUID 表达。`cell_geometry` 只描述注入时刻的几何（用于
    instrumentation 复现），它被显式标注 `anchor_role: "none"`。
    """
    for anchor in identity_anchors:
        gate.assert_anchor_allowed(anchor)
    for carrier in ("hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"):
        gate.assert_carrier_allowed(carrier)
    if not is_digest(template_definition_sha256):
        raise InstrumentationError(
            f"template_definition_sha256 非法: {template_definition_sha256!r}"
        )

    names = {
        name: ref_tpl.format(
            sheet="{managed_sheet}",
            first=spec.first_data_row,
            last=spec.last_data_row,
            last_col=spec.managed_last_col,
            footer=spec.footer_row,
            uuid_col=spec.uuid_col,
        )
        for name, ref_tpl, _ in spec.defined_names()
    }
    payload: dict[str, Any] = {
        "schema_version": INSTRUMENTATION_SCHEMA_VERSION,
        "entry_id": spec.entry_id,
        "template_id": spec.template_id,
        # 单向引用：已发布 template definition 的 digest + 模板 blob 的内容身份
        "template_definition_sha256": template_definition_sha256,
        "template_sha256": template_sha256,
        "instrumentation_version": INSTRUMENTATION_VERSION,
        "identity_schema_version": IDENTITY_SCHEMA_VERSION,
        "identity_carriers": list(sorted(gate.allowed_carriers)),
        "identity_anchors": list(identity_anchors),
        "forbidden_anchors": list(sorted(gate.forbidden_anchors)),
        "managed_sheets": [
            {
                # 逻辑 sheet 身份（contract 的 sheet_key）。**不是**展示名、**不是** sheetId。
                "sheet_key": f"{spec.template_id.lower()}-managed",
                "locator": {
                    "anchor": "defined_name_ref",
                    "defined_name": f"GT_MANAGED_REGION_{spec.template_id}",
                },
                "region_boundary_locator": {
                    "anchor": "excel_table_sheet_association",
                    "table_key": spec.table_name,
                },
                "tables": [
                    {
                        "table_key": spec.table_name,
                        "row_identity": "row_uuid",
                        "row_uuid_column_letter": spec.uuid_col,
                        "row_uuid_literal_prefix": f"GTROW-{spec.template_id}-",
                        "header_row_count": 0,
                        "managed_row_count_at_instrumentation": spec.row_count,
                    }
                ],
                "footer_locator": {
                    "anchor": "defined_name_ref",
                    "defined_name": f"GT_FOOTER_ANCHOR_{spec.template_id}",
                },
            }
        ],
        "defined_names": names,
        "hidden_metadata_sheet": {
            "sheet_name": GT_SYNC_SHEET_NAME,
            "keys": list(REQUIRED_GT_SYNC_KEYS),
            "runtime_binding_keys_written_at_finalize_only": list(RUNTIME_BINDING_KEYS),
        },
        "row_uuid_disposition": {
            "empty_uuid_on_new_row": "allocate_new_id",
            "duplicate_uuid_from_copy": "structural_conflict",
            "user_deleted_identity_column": "reject",
            "reuse_of_deleted_uuid": "forbidden",
        },
        "visible_equivalence_policy": "strict",
        "ignored_by_business_sheet_enumerators": [GT_SYNC_SHEET_NAME],
        "cell_geometry": {
            "anchor_role": "none",
            "note": (
                "仅描述注入时刻的几何以便复现 instrumentation；运行时定位一律走 "
                "identity_anchors，不得按坐标猜"
            ),
            "managed_range": spec.managed_range,
            "table_ref": spec.table_ref,
            "footer_row": spec.footer_row,
        },
    }
    validate_instrumentation_payload(payload)
    _assert_no_forbidden_anchor_declared(payload, gate=gate)
    return payload


def _iter_anchor_declarations(node: Any) -> Iterable[str]:
    """递归收集所有 `{"anchor": ...}` 声明值。"""
    if isinstance(node, Mapping):
        if "anchor" in node and isinstance(node["anchor"], str):
            yield node["anchor"]
        for value in node.values():
            yield from _iter_anchor_declarations(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _iter_anchor_declarations(item)


def _assert_no_forbidden_anchor_declared(
    payload: Mapping[str, Any], *, gate: ExcelIdentityCarrierGate
) -> None:
    """payload 里任何 locator 的 `anchor` 都不得是被证伪的锚点。

    判据是**结构**（逐个 locator 的 anchor 值）而不是全文 grep：payload 的
    `forbidden_anchors` 字段本身就写着 `sheet_id`/`sheet_display_name`（那是给下游
    loader 的黑名单，必须保留），全文搜字符串会把它误判成违规。
    """
    declared = [a for a in _iter_anchor_declarations(payload)]
    bad = sorted({a for a in declared if a in gate.forbidden_anchors})
    if bad:
        raise ForbiddenAnchorError(
            f"instrumentation payload 的 locator 使用了被证伪的锚点 {bad} —— "
            "Task 5 实测 sheetId 每次保存重编号、展示名可改名（Requirement 6.14）"
        )
    if not declared:
        raise ForbiddenAnchorError(
            "instrumentation payload 一个 locator anchor 都没有 —— "
            "identity 必须显式声明锚点，缺声明等于运行时按坐标/名称猜"
        )


def assert_no_runtime_binding(pairs: Mapping[str, str]) -> None:
    """`_GT_SYNC` 的键值对里不得出现 runtime binding 键（Requirement 6.14）。

    runtime binding 的五个 digest 只在具体 representation finalize 时写入；
    instrumentation 阶段 contract / bundle / authority model **还不存在**，
    预写一个空位或占位值会让 candidate 看起来已绑定 bundle。
    """
    hit = sorted(set(pairs) & set(RUNTIME_BINDING_KEYS))
    if hit:
        raise RuntimeBindingForbiddenError(
            f"instrumentation 阶段的 `_GT_SYNC` 预写了 runtime binding 键 {hit} —— "
            "authority-model/template/instrumentation/contract/bundle digests 只能在 "
            "representation finalize 时写入（design §Excel instrumentation contract）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 5. zip 级定点注入（design：优先 zip-level，不做 openpyxl 全量重写）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class InstrumentedWorkbook:
    """一次 instrumentation 的产物 + 自证材料。"""

    source_sha256: str
    instrumented_bytes: bytes
    instrumented_sha256: str
    managed_sheet_name_at_instrumentation: str
    #: 注入时刻的 OOXML `sheetId`。**只作审计线索**（契约 usage_rules），非锚点。
    managed_sheet_id_at_instrumentation: str
    row_uuids: Mapping[int, str]
    gt_sync_pairs: Mapping[str, str]
    defined_name_refs: Mapping[str, str]
    table_ref: str

    @property
    def added_hidden_columns(self) -> dict[str, list[str]]:
        return {self.managed_sheet_name_at_instrumentation: []}


def _insert_before(text: str, needle: str, addition: str, *, what: str) -> str:
    idx = text.find(needle)
    if idx < 0:
        raise InstrumentationError(f"注入 {what} 失败：找不到锚点 {needle!r}")
    return text[:idx] + addition + text[idx:]


def _gt_sync_sheet_xml(pairs: Sequence[tuple[str, str]]) -> bytes:
    rows = [
        f'<row r="{i}">'
        f'<c r="A{i}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(k)}</t></is></c>'
        f'<c r="B{i}" t="inlineStr"><is><t xml:space="preserve">{_xml_escape(v)}</t></is></c>'
        f"</row>"
        for i, (k, v) in enumerate(pairs, start=1)
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<worksheet xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}">'
        f'<dimension ref="A1:B{max(len(pairs), 1)}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="14.25"/>'
        '<cols><col min="1" max="1" width="34" customWidth="1"/>'
        '<col min="2" max="2" width="72" customWidth="1"/></cols>'
        f'<sheetData>{"".join(rows)}</sheetData>'
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        "</worksheet>"
    ).encode("utf-8")


def _table_xml(*, table_id: int, name: str, ref: str, column_count: int) -> bytes:
    """`headerRowCount=0` 的 Excel Table。

    置 0 是 Task 5 的刻意选择：业务模板的两级合并表头无法充当 Table 表头行，置 0 可以
    在**不改任何可见单元格**的前提下圈出受管行区域。`tableStyleInfo` 不带 `name`、
    stripes 全 0，否则会给业务区域叠加可见表格样式。
    """
    cols = "".join(
        f'<tableColumn id="{i}" name="GTCol{i}"/>' for i in range(1, column_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        f'<table xmlns="{_MAIN_NS}" id="{table_id}" name="{name}" displayName="{name}" '
        f'ref="{ref}" headerRowCount="0" totalsRowShown="0">'
        f'<tableColumns count="{column_count}">{cols}</tableColumns>'
        '<tableStyleInfo showFirstColumn="0" showLastColumn="0" showRowStripes="0" '
        'showColumnStripes="0"/>'
        "</table>"
    ).encode("utf-8")


def _sheet_part_for(workbook_xml: str, rels_xml: str, sheet_name: str) -> str:
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(_xml_escape(sheet_name)) + r'"[^>]*r:id="(rId\d+)"',
        workbook_xml,
    )
    if not match:
        raise InstrumentationError(f"workbook.xml 中找不到 sheet {sheet_name!r}")
    rid = match.group(1)
    # 🔴 Task 42 修：**OOXML 不保证 `<Relationship>` 的属性顺序**。原实现写的是
    #    `Id="{rid}"[^>]*Target="..."`，隐含「Id 必须排在 Target 之前」——
    #    实测 `backend/wp_templates/` 下 369 个工作簿里有 **10 个**把顺序写成
    #    `Type` → `Target` → `Id`（含 Task 40 的 `B60-1 审计项目工时预算与控制表.xlsx`、
    #    Task 43 的 `G7 长期股权投资.xlsx` 与 Task 42 的 `H1 固定资产.xlsx`），
    #    对它们一律抛「workbook rels 中找不到 rIdN」。缺陷此前是潜伏的：Task 40 的守卫
    #    根本不调 `instrument_workbook_bytes`，Task 41 的 D2 模板恰好是 Id-first。
    #    正解是**先定位含该 Id 的 Relationship 元素**，再从元素内取 Target（顺序无关）。
    element: str | None = None
    for candidate in re.finditer(r"<Relationship\b[^>]*?/?>", rels_xml):
        if re.search(r'\bId="' + re.escape(rid) + r'"', candidate.group(0)):
            element = candidate.group(0)
            break
    if element is None:
        raise InstrumentationError(f"workbook rels 中找不到 {rid}")
    rel = re.search(r'\bTarget="([^"]+)"', element)
    if not rel:
        raise InstrumentationError(
            f"workbook rels 的 {rid} 关系缺 Target 属性: {element!r}"
        )
    target = rel.group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _sheet_id_for(workbook_xml: str, sheet_name: str) -> str:
    escaped = re.escape(_xml_escape(sheet_name))
    for pattern in (
        r'<sheet [^>]*name="' + escaped + r'"[^>]*?sheetId="(\d+)"',
        r'<sheet [^>]*sheetId="(\d+)"[^>]*name="' + escaped + r'"',
    ):
        match = re.search(pattern, workbook_xml)
        if match:
            return match.group(1)
    raise InstrumentationError(f"取不到 sheet {sheet_name!r} 的 sheetId")


def _add_uuid_cells(sheet_xml: str, *, uuid_col: str, uuids: Mapping[int, str]) -> str:
    for row_no, value in sorted(uuids.items()):
        cell = (
            f'<c r="{uuid_col}{row_no}" t="inlineStr">'
            f"<is><t>{_xml_escape(value)}</t></is></c>"
        )
        # 🔴 Task 43 修（只加一个前置分支，其余路径字节不变）：UUID 列在**某些模板**里已经
        #    有一个「有样式、无值」的格（实测 `G7 长期股权投资.xlsx` 的
        #    `附注披露信息（国企）` 第 79..83 行都有 `<c r="N79" s="35" t="n"></c>`）。
        #    原实现无条件在 `</row>` 前追加，于是同一行里出现**两个相同 `r` 的 `<c>`** ——
        #    这是非法 OOXML：Excel/OO 可能拒绝打开或静默丢弃其中一个，而 openpyxl 恰好
        #    "后者胜出"，于是缺陷被掩盖成"能跑"。
        #    只在该格**确实已存在**时替换；不存在时走原来的追加路径 ⇒ 另外那些模板的注入
        #    字节与 Task 40/41/42 冻结的结构 hash 一个都不变。
        existing = re.search(
            rf'<c r="{uuid_col}{row_no}"(?:\s[^>]*?)?(?:/>|>.*?</c>)', sheet_xml, re.S
        )
        if existing is not None:
            sheet_xml = sheet_xml[: existing.start()] + cell + sheet_xml[existing.end() :]
            continue
        self_closing = re.search(rf'<row r="{row_no}"(?:\s[^>]*)?/>', sheet_xml)
        if self_closing:
            raw = self_closing.group(0)
            sheet_xml = sheet_xml.replace(raw, raw[:-2] + ">" + cell + "</row>", 1)
            continue
        opened = re.search(rf'<row r="{row_no}"(?:\s[^>]*)?>', sheet_xml)
        if not opened:
            raise InstrumentationError(
                f"受管 sheet 中找不到第 {row_no} 行，无法写 row UUID —— "
                "声明的受管行区间与模板实际结构不符（Requirement 6.10：结构漂移 fail closed）"
            )
        close_idx = sheet_xml.find("</row>", opened.end())
        if close_idx < 0:
            raise InstrumentationError(f"第 {row_no} 行缺少 </row>")
        sheet_xml = sheet_xml[:close_idx] + cell + sheet_xml[close_idx:]
    return sheet_xml


def _hide_uuid_column(sheet_xml: str, *, uuid_col: str) -> str:
    col_no = _col_index(uuid_col)
    col = f'<col min="{col_no}" max="{col_no}" width="9" hidden="1" customWidth="1"/>'
    if "<cols>" in sheet_xml:
        return _insert_before(sheet_xml, "</cols>", col, what="hidden UUID col")
    return _insert_before(sheet_xml, "<sheetData", f"<cols>{col}</cols>", what="cols block")


def _attach_table_part(sheet_xml: str) -> str:
    # 🔴 Task 42 修：`<tablePart>` 用 `r:id`，而**有些工作簿的 `<worksheet>` 根元素并不
    #    声明 `xmlns:r`**（实测 `H1 固定资产.xlsx` 的 26 张 sheet 全是这种：根元素只有
    #    默认命名空间，`r:` 声明写在需要它的子元素上）。原实现无条件不带声明，对这类
    #    sheet 产出的 XML 里 `r:` 前缀**未绑定** ⇒ `_parse_tables` 抛
    #    `unbound prefix`，`identity_inventory` / `structure_fingerprint` 全线不可用。
    #    与 `<sheet>` 侧同一处置：只在根元素**确实没有**声明时才补，避免改动另外 358 个
    #    工作簿的注入字节（那会改掉 Task 40/41 已冻结的 structure hash）。
    root_end = sheet_xml.find(">", sheet_xml.find("<worksheet"))
    root_tag = sheet_xml[: root_end + 1] if root_end > 0 else sheet_xml
    rel_ns_decl = "" if 'xmlns:r="' in root_tag else f' xmlns:r="{_REL_NS}"'
    block = (
        f'<tableParts{rel_ns_decl} count="1">'
        f'<tablePart r:id="{_GT_TABLE_REL_ID}"/></tableParts>'
    )
    for tail in _SHEET_TAIL_ORDER:
        idx = sheet_xml.find(f"<{tail}")
        if idx >= 0:
            return sheet_xml[:idx] + block + sheet_xml[idx:]
    return _insert_before(sheet_xml, "</worksheet>", block, what="tableParts")


def instrument_workbook_bytes(
    source: bytes, spec: ExcelInstrumentationSpec, *, gate: ExcelIdentityCarrierGate
) -> InstrumentedWorkbook:
    """把四类探针通过的 identity 载体注入 workbook **副本字节**。

    只吃 bytes、只吐 bytes：本函数结构上碰不到 `backend/wp_templates/` 里的文件
    （Requirement 9.9「不得在运行时临时写回模板库」）。
    """
    for carrier in ("hidden_sheet", "defined_name", "excel_table", "hidden_uuid_column"):
        gate.assert_carrier_allowed(carrier)

    template_sha = _sha256_bytes(source)
    try:
        with zipfile.ZipFile(io.BytesIO(source)) as zf:
            entries: dict[str, bytes] = {name: zf.read(name) for name in zf.namelist()}
    except zipfile.BadZipFile as exc:
        raise InstrumentationError(f"源 artifact 不是合法 xlsx zip: {exc}") from exc

    for required in ("xl/workbook.xml", "xl/_rels/workbook.xml.rels", "[Content_Types].xml"):
        if required not in entries:
            raise InstrumentationError(f"源 artifact 缺 OOXML 必需部件: {required}")
    if _GT_SYNC_SHEET_PART in entries or _GT_TABLE_PART in entries:
        raise InstrumentationError(
            "源 artifact 已含 instrumentation 部件 —— 重复注入会产生第二套 identity；"
            "存量 instrumented artifact 应走 definition 升级而不是再注入一次"
        )

    workbook_xml = entries["xl/workbook.xml"].decode("utf-8")
    wb_rels_xml = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    content_types = entries["[Content_Types].xml"].decode("utf-8")

    managed_sheet_id = _sheet_id_for(workbook_xml, spec.managed_sheet)
    target_part = _sheet_part_for(workbook_xml, wb_rels_xml, spec.managed_sheet)
    if target_part not in entries:
        raise InstrumentationError(f"目标 sheet 部件不存在: {target_part}")

    # ── BP-21 门：声明的受管行区间末行不得落在「排版占位行」上 ──────────────
    #
    # 中文审计模板普遍在数据区末尾放一行续行省略号（整格 `……`），紧跟其后才是 `合计`。
    # 受管区行范围是派生的，派生规则「表头与合计之间都是数据行」会把它一并吞进受管区 ⇒
    # materialize 试图把 `……` 按 `integer` 写回业务字段（首版发布实测卡在 H1 的 `A27`）。
    #
    # 🔴 为什么排在**这里**：本函数是「provider 声明的行区间」第一次遇上「模板真实字节」的
    #    地方。往后一步（`uuids = {...}`）就已经按声明的区间给占位行发了 row UUID，那个
    #    UUID 会进冻结 identity inventory，此后无论读侧怎么收缩都会被
    #    `assert_identity_inventory_retained` 判成「OO 往返后丢了一个 row identity」——
    #    实测过：只在 `resolve_managed_region` 收缩会撞 `IdentityRetentionError`。
    #    区间、UUID 集合、冻结清册三者必须**同源**收缩，而它们的共同上游只有本函数。
    #
    # 🔴 为什么 fail closed 而不是引擎自动收缩：自动收缩会让 `GT_ROW_UUID_LAST_ROW` 写 27
    #    而 UUID 只到 26，「声明与实况不符」自己是一类缺陷；且下一个 provider 作者永远不会
    #    知道这条规则存在。fail closed 让他撞一次、改一次，而声明可被 digest 冻结。
    #
    # 全库实测 170 处 / 37 份模板 / 35 个 wp_code ⇒ 逐契约写 `excluded_rows` 必然遗漏，
    # 故落成平台级门。判据实现在 `excel_typography_rows`（单一真源，验收脚本也消费它）。
    _where = f"entry {spec.entry_id} / sheet {spec.managed_sheet!r}"
    try:
        _typography.assert_label_column_matches_spec(spec.table_ref, where=_where)
        _typography.assert_last_data_row_is_not_typography_placeholder(
            sheet_xml=entries[target_part].decode("utf-8", "replace"),
            shared=_typography.read_shared_strings_from_entries(entries),
            label_column=_typography.MANAGED_LABEL_COLUMN,
            first_data_row=spec.first_data_row,
            last_data_row=spec.last_data_row,
            where=_where,
        )
    except _typography.TypographyRowError as exc:
        raise InstrumentationError(str(exc)) from exc

    uuids = {row: spec.row_uuid(row) for row in range(spec.first_data_row, spec.last_data_row + 1)}

    # ── 载体 1：hidden `_GT_SYNC` metadata sheet ──────────────────────
    pairs: list[tuple[str, str]] = [
        ("GT_SYNC_SCHEMA_VERSION", "1"),
        ("GT_IDENTITY_SCHEMA_VERSION", IDENTITY_SCHEMA_VERSION),
        ("GT_INSTRUMENTATION_VERSION", INSTRUMENTATION_VERSION),
        ("GT_TEMPLATE_ID", spec.template_id),
        ("GT_TEMPLATE_SHA256", template_sha),
        ("GT_ENTRY_ID", spec.entry_id),
        # 🔴 保留但**降级**：Task 5 已证伪 sheetId 作为运行时锚点（OO 每次保存重编号）。
        #    该键只是 instrumentation 时刻的审计线索，契约 usage_rules 写死了这一点。
        ("GT_MANAGED_SHEET_ID", managed_sheet_id),
        ("GT_MANAGED_SHEET_NAME_AT_INSTRUMENTATION", spec.managed_sheet),
        ("GT_MANAGED_RANGE", spec.managed_range),
        ("GT_FOOTER_ROW", str(spec.footer_row)),
        ("GT_ROW_UUID_COLUMN", spec.uuid_col),
        ("GT_ROW_UUID_FIRST_ROW", str(spec.first_data_row)),
        ("GT_ROW_UUID_LAST_ROW", str(spec.last_data_row)),
        ("GT_MANAGED_TABLE", spec.table_name),
        ("GT_MANAGED_TABLE_REF", spec.table_ref),
    ]
    pair_map = dict(pairs)
    missing_required = [k for k in REQUIRED_GT_SYNC_KEYS if k not in pair_map]
    if missing_required:
        raise InstrumentationError(
            f"`_GT_SYNC` 缺 Task 5 契约声明的必备键 {missing_required}"
        )
    assert_no_runtime_binding(pair_map)
    entries[_GT_SYNC_SHEET_PART] = _gt_sync_sheet_xml(pairs)

    existing_ids = [int(m) for m in re.findall(r'<sheet [^>]*sheetId="(\d+)"', workbook_xml)]
    # 🔴 Task 42 修：注入的 `<sheet>` 用 `r:id`，而**有些工作簿的 `<workbook>` 根元素
    #    并不声明 `xmlns:r`** —— 它们把声明写在每个 `<sheet>` 元素上（实测
    #    `H1 固定资产.xlsx` 就是这种：根元素只有默认命名空间，26 个 `<sheet>` 各带一份
    #    `xmlns:r=...`）。原实现无条件不带声明，对这类工作簿产出的 workbook.xml 里
    #    `r:` 前缀**未绑定**，`ET.fromstring` 直接 `ParseError: unbound prefix`，
    #    下游 `identity_inventory` / `structure_fingerprint` 全线不可用。
    #    只在根元素**确实没有**声明时才补一份（同 URI 的重复声明虽合法，但无条件加会改动
    #    另外 358 个工作簿的注入字节，从而改掉 Task 40/41 已冻结的 structure hash）。
    _root_end = workbook_xml.find(">", workbook_xml.find("<workbook"))
    _root_tag = workbook_xml[: _root_end + 1] if _root_end > 0 else workbook_xml
    _rel_ns_decl = "" if 'xmlns:r="' in _root_tag else f' xmlns:r="{_REL_NS}"'
    workbook_xml = _insert_before(
        workbook_xml,
        "</sheets>",
        f"<sheet{_rel_ns_decl} name=\"{GT_SYNC_SHEET_NAME}\" "
        f'sheetId="{(max(existing_ids) + 1) if existing_ids else 1}" '
        f'state="hidden" r:id="{_GT_SYNC_REL_ID}"/>',
        what="hidden _GT_SYNC sheet 声明",
    )
    wb_rels_xml = _insert_before(
        wb_rels_xml,
        "</Relationships>",
        f'<Relationship Id="{_GT_SYNC_REL_ID}" Type="{_REL_NS}/worksheet" '
        'Target="worksheets/sheetGtSync.xml"/>',
        what="_GT_SYNC 关系",
    )
    content_types = _insert_before(
        content_types,
        "</Types>",
        f'<Override PartName="/{_GT_SYNC_SHEET_PART}" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>',
        what="_GT_SYNC content type",
    )

    # ── 载体 2：defined names（sheet 改名后 OO 会自动改写 ref）───────────
    quoted = (
        f"'{spec.managed_sheet}'"
        if re.search(r"[\s\-()（）]", spec.managed_sheet)
        else spec.managed_sheet
    )
    sheet_order = re.findall(r'<sheet [^>]*name="([^"]+)"', workbook_xml)
    local_sheet_id = sheet_order.index(_xml_escape(spec.managed_sheet))
    refs: dict[str, str] = {}
    nodes: list[str] = []
    for name, ref_tpl, sheet_local in spec.defined_names():
        ref = ref_tpl.format(
            sheet=quoted,
            first=spec.first_data_row,
            last=spec.last_data_row,
            last_col=spec.managed_last_col,
            footer=spec.footer_row,
            uuid_col=spec.uuid_col,
        )
        refs[name] = ref
        scope = f' localSheetId="{local_sheet_id}"' if sheet_local else ""
        nodes.append(f'<definedName name="{name}"{scope}>{_xml_escape(ref)}</definedName>')
    joined = "".join(nodes)
    if "<definedNames>" in workbook_xml:
        workbook_xml = _insert_before(workbook_xml, "</definedNames>", joined, what="defined names")
    else:
        workbook_xml = workbook_xml.replace(
            "</sheets>", f"</sheets><definedNames>{joined}</definedNames>", 1
        )

    # ── 载体 3/4：Excel Table + 隐藏 UUID 列 ──────────────────────────
    sheet_xml = entries[target_part].decode("utf-8")
    sheet_xml = _add_uuid_cells(sheet_xml, uuid_col=spec.uuid_col, uuids=uuids)
    sheet_xml = _hide_uuid_column(sheet_xml, uuid_col=spec.uuid_col)
    dim = re.search(r'<dimension ref="([A-Z]+\d+):([A-Z]+)(\d+)"/>', sheet_xml)
    if dim and _col_index(dim.group(2)) < _col_index(spec.uuid_col):
        sheet_xml = sheet_xml.replace(
            dim.group(0), f'<dimension ref="{dim.group(1)}:{spec.uuid_col}{dim.group(3)}"/>', 1
        )
    table_ids = [
        int(m)
        for name, blob in entries.items()
        if name.startswith("xl/tables/")
        for m in re.findall(r'<table [^>]*\bid="(\d+)"', blob.decode("utf-8", "replace"))
    ]
    entries[_GT_TABLE_PART] = _table_xml(
        table_id=(max(table_ids) + 1) if table_ids else 1,
        name=spec.table_name,
        ref=spec.table_ref,
        column_count=_col_index(spec.uuid_col),
    )
    sheet_xml = _attach_table_part(sheet_xml)
    rels_part = f"{target_part.rsplit('/', 1)[0]}/_rels/{target_part.rsplit('/', 1)[1]}.rels"
    rel_node = (
        f'<Relationship Id="{_GT_TABLE_REL_ID}" Type="{_REL_NS}/table" '
        'Target="../tables/tableGtRowId.xml"/>'
    )
    if rels_part in entries:
        entries[rels_part] = _insert_before(
            entries[rels_part].decode("utf-8"), "</Relationships>", rel_node, what="table 关系"
        ).encode("utf-8")
    else:
        entries[rels_part] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f"{rel_node}</Relationships>"
        ).encode("utf-8")
    content_types = _insert_before(
        content_types,
        "</Types>",
        f'<Override PartName="/{_GT_TABLE_PART}" ContentType="application/'
        'vnd.openxmlformats-officedocument.spreadsheetml.table+xml"/>',
        what="table content type",
    )

    entries[target_part] = sheet_xml.encode("utf-8")
    entries["xl/workbook.xml"] = workbook_xml.encode("utf-8")
    entries["xl/_rels/workbook.xml.rels"] = wb_rels_xml.encode("utf-8")
    entries["[Content_Types].xml"] = content_types.encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name in entries:
            out.writestr(name, entries[name])
    result = buf.getvalue()

    return InstrumentedWorkbook(
        source_sha256=template_sha,
        instrumented_bytes=result,
        instrumented_sha256=_sha256_bytes(result),
        managed_sheet_name_at_instrumentation=spec.managed_sheet,
        managed_sheet_id_at_instrumentation=managed_sheet_id,
        row_uuids=uuids,
        gt_sync_pairs=pair_map,
        defined_name_refs=refs,
        table_ref=spec.table_ref,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 6. 等价校验与反读
# ═══════════════════════════════════════════════════════════════════════════


def verify_visible_equivalence(
    *, source: bytes, instrumented: InstrumentedWorkbook, spec: ExcelInstrumentationSpec
) -> dict[str, Any]:
    """Requirement 6.17：注入前后可见结构必须等价，隐藏元数据 sheet 必须被业务枚举排除。

    白名单只有四样（隐藏 sheet / `GT_` defined names / 一列隐藏 UUID / `headerRowCount=0`
    的 Table 部件），其余任何 aspect 差异一律判不等价。
    """
    report = visible_equivalence_report(
        source,
        instrumented.instrumented_bytes,
        ignored_sheets=(GT_SYNC_SHEET_NAME,),
        allow_added_hidden_columns={spec.managed_sheet: [spec.uuid_col]},
        label_before="template",
        label_after="instrumented",
    )
    if not report["equivalent"]:
        bad = [a for a, ok in report["aspect_verdicts"].items() if not ok]
        raise VisibleEquivalenceError(
            f"instrumentation 破坏了可见业务结构，首批不等价 aspect: {bad}；"
            f"collection_errors={report['collection_errors']}"
            "（Requirement 6.17：可见 sheet/业务值/公式/样式/merge/受保护部件必须等价）"
        )
    if report["hidden_sheets_added"] != [GT_SYNC_SHEET_NAME]:
        raise VisibleEquivalenceError(
            f"instrumentation 新增的隐藏 sheet 不止 `{GT_SYNC_SHEET_NAME}`: "
            f"{report['hidden_sheets_added']}"
        )
    if not report["metadata_sheet_excluded_from_business"]:
        raise VisibleEquivalenceError(
            f"`{GT_SYNC_SHEET_NAME}` 未被业务 sheet 枚举排除（Requirement 6.17 后半句）"
        )
    return report


def read_back_identity(
    *, instrumented: InstrumentedWorkbook, spec: ExcelInstrumentationSpec,
    gate: ExcelIdentityCarrierGate,
) -> dict[str, Any]:
    """反读 identity inventory 并与注入声明逐项比对（extract roundtrip 的前置形态）。

    🔴 **只传 `expected_table` + `uuid_column_letter`**：不传 `uuid_sheet_id` /
    `uuid_sheet_name`，于是 `identity_inventory()` 的 sheet 解析候选里结构上不可能
    出现被证伪的 `sheet_id` / `sheet_name` 两条路径。这不是「记得别传」，而是让
    `sheet_resolution_candidates` 只剩 `table_sheet` 一项 —— 守卫直接断言这一点。
    """
    gate.assert_anchor_allowed("excel_table_sheet_association")
    try:
        inv = identity_inventory(
            instrumented.instrumented_bytes,
            expected_table=spec.table_name,
            uuid_column_letter=spec.uuid_col,
        )
    except FingerprintError as exc:  # 采集失败绝不降级成「无 identity」
        raise IdentityReadbackError(f"identity 反读采集失败: {exc}") from exc

    if inv["errors"]:
        raise IdentityReadbackError(f"identity 反读报告了采集错误: {inv['errors']}")

    hidden = inv["hidden_sheet"]
    if not (hidden["present"] and hidden["is_hidden"]):
        raise IdentityReadbackError(
            f"`{GT_SYNC_SHEET_NAME}` 反读失败: present={hidden['present']} "
            f"is_hidden={hidden['is_hidden']}"
        )
    if not hidden["excluded_from_business_enumeration"]:
        raise IdentityReadbackError(
            f"`{GT_SYNC_SHEET_NAME}` 未被业务 sheet 枚举排除"
        )
    missing_keys = [k for k in gate.required_hidden_sheet_keys if k not in hidden["pairs"]]
    if missing_keys:
        raise IdentityReadbackError(
            f"`_GT_SYNC` 缺契约要求的键 {missing_keys}（契约 required_keys 是单一真源）"
        )
    assert_no_runtime_binding(hidden["pairs"])

    names = inv["defined_name"]
    expected_names = {n for n, _, _ in spec.defined_names()}
    if set(names["names"]) != expected_names:
        raise IdentityReadbackError(
            f"`GT_` defined name 反读不符：期望 {sorted(expected_names)}，"
            f"实得 {sorted(names['names'])}"
        )

    table = inv["excel_table"]
    if not table["present"]:
        raise IdentityReadbackError(
            f"Excel Table {spec.table_name!r} 反读不到 —— 它是 sheet 改名后唯一可用的"
            "区域边界锚点，缺它即无锚点可用"
        )
    if table["header_row_count_zero"] is not True:
        raise IdentityReadbackError(
            f"Table {spec.table_name!r} 的 headerRowCount 不是 0 —— 非 0 会把业务两级"
            "表头当成 Table 表头行"
        )
    if table["table_ref"] != spec.table_ref:
        raise IdentityReadbackError(
            f"Table ref 反读不符：期望 {spec.table_ref}，实得 {table['table_ref']}"
        )

    col = inv["hidden_uuid_column"]
    candidates = set(col["sheet_resolution_candidates"])
    forbidden_hit = sorted(candidates & {"sheet_id", "sheet_name"})
    if forbidden_hit:
        raise ForbiddenAnchorError(
            f"反读用到了被证伪的 sheet 定位路径 {forbidden_hit} —— "
            "生产反读只能走 excel_table_sheet_association"
        )
    # 🔴 顺序敏感：`resolved_sheet_by is None` 必须**先**被归类成「identity 列没了」
    #    （Requirement 6.15 的「拒绝」形态），再判锚点是否走错路径。反过来写时，
    #    「用户删掉整列 UUID」会被报成 ForbiddenAnchorError（锚点用错），错误原因指错
    #    地方，而真正的锚点误用分支变得不可分辨 —— 与 `assert_candidate_finalizable`
    #    的「语义判据在前、状态边在后」同源。
    if col["resolved_sheet_by"] is None:
        raise IdentityReadbackError(
            f"受管 sheet 上一个 row UUID 都读不到（Table ref={inv['excel_table']['table_ref']} "
            "仍覆盖数据行）—— 对应 Requirement 6.15 的「用户删除 identity 列」形态，"
            "contract 处置为**拒绝**，不得静默按位置猜行身份"
        )
    if col["resolved_sheet_by"] != "table_sheet":
        raise ForbiddenAnchorError(
            f"UUID 列的 sheet 由 {col['resolved_sheet_by']!r} 解析 —— 必须是 table_sheet"
        )
    if col["uuid_column_hidden"] is not True:
        raise IdentityReadbackError(f"UUID 列 {spec.uuid_col} 未隐藏")
    expected_uuids = dict(instrumented.row_uuids)
    got = {int(k): v for k, v in col["row_uuids"].items()}
    if got != expected_uuids:
        raise IdentityReadbackError(
            f"row UUID 反读不等值：期望 {len(expected_uuids)} 个、实得 {len(got)} 个；"
            f"首个差异 {sorted(set(expected_uuids.items()) ^ set(got.items()))[:3]}"
        )
    if col["duplicate_row_uuids"] or col["empty_row_uuids"]:
        raise IdentityReadbackError(
            f"注入即产生重复/空 UUID：duplicates={col['duplicate_row_uuids']} "
            f"empty={col['empty_row_uuids']}"
        )
    return inv


# ═══════════════════════════════════════════════════════════════════════════
# 7. candidate-only 仓储门面
# ═══════════════════════════════════════════════════════════════════════════


class CandidateOnlyRepository:
    """把「发布 representation / 切 pointer / finalize / 推进 revision」四类写入面
    从仓储上**摘掉**的门面。

    与 Task 15 的 :class:`~app.services.workpaper_sync.content_mutation.
    RevisionLockedRepository` 同形态、同理由：禁令必须有可执行判据。往本模块注入一行
    `create_representation(...)` / `set_entry_pointer(...)` / `finalize_candidate(...)`
    / `bump_content_revision(...)` 都会立刻抛 —— 于是「本任务只能生成 non-current
    candidate」这条否定式承诺可 falsify（变异检验 M09~M12）。

    其余方法一律透传：它不是第二套仓储，没有复制任何写入逻辑。
    """

    __slots__ = ("_inner",)

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def inner(self) -> Any:
        return self._inner

    @property
    def session(self) -> Any:
        return self._inner.session

    def __getattr__(self, name: str) -> Any:
        if name in CANDIDATE_FORBIDDEN_METHODS:
            raise CandidateSurfaceForbiddenError(
                f"`{name}` 属 representation/pointer/finalize/revision 写入面，"
                "instrumentation candidate 生成路径不得调用 —— published representation "
                "只能由 RepresentationService.finalize_candidate() 在 approved per-entry "
                "contract + authority model + definition bundle 全部就位后创建"
                "（Requirement 6.18 / 9.10 / Property 67）"
            )
        return getattr(self._inner, name)


# ═══════════════════════════════════════════════════════════════════════════
# 8. candidate 结果与非当前性自证
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class UpgradeCandidateOutcome:
    """一次 instrumentation upgrade 的完整审计快照（Requirement 9.10 的记录清单）。"""

    candidate_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str
    content_version_id: uuid.UUID
    source_representation_id: uuid.UUID
    from_definition_bundle_id: uuid.UUID | None
    from_definition_bundle_sha256: str | None
    template_definition_id: uuid.UUID
    template_definition_sha256: str
    instrumentation_definition_id: uuid.UUID
    instrumentation_definition_sha256: str
    #: 三者恒为 None —— 本任务不得伪造 contract / authority model / bundle
    target_contract_definition_id: None
    target_definition_bundle_id: None
    state: CandidateState
    staged_artifact_id: uuid.UUID
    staged_artifact_sha256: str
    staged_relative_path: str
    rollback_source_sha256: str
    visible_equivalence_report_sha256: str
    identity_inventory_sha256: str
    structure_hash: str
    content_revision_before: int
    content_revision_after: int
    entry_pointer_before: uuid.UUID | None
    entry_pointer_after: uuid.UUID | None
    representation_count_before: int
    representation_count_after: int
    probe_gate: Mapping[str, str]
    actor_id: uuid.UUID | None

    @property
    def revision_unchanged(self) -> bool:
        return self.content_revision_before == self.content_revision_after

    @property
    def pointer_unchanged(self) -> bool:
        return self.entry_pointer_before == self.entry_pointer_after

    @property
    def no_representation_created(self) -> bool:
        return self.representation_count_before == self.representation_count_after

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": str(self.candidate_id),
            "wp_id": str(self.wp_id),
            "entry_id": self.entry_id,
            "content_version_id": str(self.content_version_id),
            "source_representation_id": str(self.source_representation_id),
            "from_definition_bundle_id": (
                str(self.from_definition_bundle_id) if self.from_definition_bundle_id else None
            ),
            "from_definition_bundle_sha256": self.from_definition_bundle_sha256,
            "template_definition_id": str(self.template_definition_id),
            "template_definition_sha256": self.template_definition_sha256,
            "instrumentation_definition_id": str(self.instrumentation_definition_id),
            "instrumentation_definition_sha256": self.instrumentation_definition_sha256,
            "target_contract_definition_id": self.target_contract_definition_id,
            "target_definition_bundle_id": self.target_definition_bundle_id,
            "state": self.state.value,
            "staged_artifact_id": str(self.staged_artifact_id),
            "staged_artifact_sha256": self.staged_artifact_sha256,
            "staged_relative_path": self.staged_relative_path,
            "rollback_source_sha256": self.rollback_source_sha256,
            "visible_equivalence_report_sha256": self.visible_equivalence_report_sha256,
            "identity_inventory_sha256": self.identity_inventory_sha256,
            "structure_hash": self.structure_hash,
            "content_revision_before": self.content_revision_before,
            "content_revision_after": self.content_revision_after,
            "revision_unchanged": self.revision_unchanged,
            "entry_pointer_before": (
                str(self.entry_pointer_before) if self.entry_pointer_before else None
            ),
            "entry_pointer_after": (
                str(self.entry_pointer_after) if self.entry_pointer_after else None
            ),
            "pointer_unchanged": self.pointer_unchanged,
            "representation_count_before": self.representation_count_before,
            "representation_count_after": self.representation_count_after,
            "no_representation_created": self.no_representation_created,
            "probe_gate": dict(self.probe_gate),
            "actor_id": str(self.actor_id) if self.actor_id else None,
        }


def assert_candidate_is_non_current(outcome: UpgradeCandidateOutcome) -> None:
    """本任务的**否定式承诺**逐条断言。

    每条都用 outcome 里 finalize 前后各采一次的实测值，而不是「代码里没写那一步」：

    * `content_revision` 未变（Requirement 2.1 / 6.18 / 9.10）
    * entry pointer 未动（同上）
    * representation 行数未增（Property 67）
    * candidate state ∈ `{staged, awaiting_contract}` —— 既不是 `ready`（那要 bundle
      compatibility 通过）也不是 `finalized`
    * contract / bundle 两个 target 恒 None（不得伪造 approved child）
    """
    if not outcome.revision_unchanged:
        raise CandidateSurfaceForbiddenError(
            f"instrumentation candidate 生成推进了 content revision："
            f"{outcome.content_revision_before} → {outcome.content_revision_after}"
        )
    if not outcome.pointer_unchanged:
        raise CandidateSurfaceForbiddenError(
            f"instrumentation candidate 生成切换了 entry pointer："
            f"{outcome.entry_pointer_before} → {outcome.entry_pointer_after}"
        )
    if not outcome.no_representation_created:
        raise CandidateSurfaceForbiddenError(
            f"instrumentation candidate 生成创建了 representation："
            f"{outcome.representation_count_before} → {outcome.representation_count_after}"
        )
    if outcome.state not in (CandidateState.staged, CandidateState.awaiting_contract):
        raise CandidateSurfaceForbiddenError(
            f"candidate state={outcome.state.value} —— 本阶段只能是 staged / "
            "awaiting_contract；ready/finalized 需要 approved bundle 与 compatibility"
        )
    if outcome.target_contract_definition_id is not None:
        raise CandidateSurfaceForbiddenError(
            "candidate 带上了 target contract —— 本任务不得伪造 per-entry contract，"
            "由 Task 36 与 Tasks 40–57 发布后回填"
        )
    if outcome.target_definition_bundle_id is not None:
        raise CandidateSurfaceForbiddenError(
            "candidate 带上了 target definition bundle —— 本任务不得伪造 bundle"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 9. 编排器
# ═══════════════════════════════════════════════════════════════════════════


class ExcelInstrumentationUpgrader:
    """存量 xlsx artifact → non-current `working_paper_representation_upgrade_candidate`。

    流程（design §Versioned upgrader 的前置阶段，顺序即判据）::

        1. gate.load()                 —— Task 5 载体裁决 + Tier A stale 门
        2. publish template definition —— DAG 第一段（权威源 backend/wp_templates/）
        3. publish instrumentation     —— 只单向引用 template digest
        4. 复制源 artifact 字节 → 注入 identity（源文件只读）
        5. visible-equivalence（strict）+ identity 反读等值
        6. stage_upgrade_candidate     —— `.upgrade-candidates/` 隔离命名空间
        7. create_upgrade_candidate    —— state=awaiting_contract，三个 target 全 None

    第 7 步之后**就结束了**。published representation / entry pointer / content
    revision 一个都不碰，且这三件事在门面层不可达（:class:`CandidateOnlyRepository`）。
    """

    def __init__(
        self,
        *,
        session: Any,
        repository: Any,
        artifacts: Any,
        project_id: uuid.UUID,
        source_commit: str,
        gate: ExcelIdentityCarrierGate | None = None,
    ) -> None:
        self._session = session
        # 🔴 无条件包门面：即便调用方传裸 repository，本类也拿不到那四类写入面。
        self._repo = (
            repository
            if isinstance(repository, CandidateOnlyRepository)
            else CandidateOnlyRepository(repository)
        )
        self._artifacts = artifacts
        self._project_id = project_id
        self._source_commit = source_commit
        self._gate = gate or ExcelIdentityCarrierGate.load()

    @property
    def gate(self) -> ExcelIdentityCarrierGate:
        return self._gate

    @property
    def repository(self) -> CandidateOnlyRepository:
        return self._repo

    # ─────────────────────────────────────────────────────────────

    async def publish_definitions(
        self, *, spec: ExcelInstrumentationSpec, wp_id: uuid.UUID, template_bytes: bytes
    ) -> tuple[Any, Any, dict[str, Any]]:
        """按 DAG 发布 template → instrumentation，返回两个 `PublishedDefinition` + payload。

        `DefinitionPublisher` 是 Task 12 的实现，本方法**不重写**发布逻辑；它只负责
        构造两个 canonical payload 并保证顺序。`publish_definition` 内部对
        instrumentation 会调 `assert_publish_order`，template 未 approved 时直接抛
        `PublishOrderError` —— 顺序不是靠本方法的语句先后保证的。
        """
        publisher = DefinitionPublisher(
            artifacts=self._artifacts,
            repository=self._repo,
            project_id=self._project_id,
            wp_id=wp_id,
            source_commit=self._source_commit,
        )
        structure_hash = normalized_structure_hash(template_bytes)
        template_payload = build_template_payload(
            spec=spec,
            template_sha256=_sha256_bytes(template_bytes),
            structure_hash=structure_hash,
        )
        template_def = await publisher.publish_definition(
            kind=DefinitionKind.template,
            payload=template_payload,
            logical_id=f"excel-template/{spec.template_id}",
            semantic_version=spec.semantic_version,
            blob_bytes=template_bytes,
            structure_hash=structure_hash,
        )
        instrumentation_payload = build_instrumentation_payload(
            spec=spec,
            template_definition_sha256=template_def.sha256,
            template_sha256=_sha256_bytes(template_bytes),
            gate=self._gate,
        )
        instrumentation_def = await publisher.publish_definition(
            kind=DefinitionKind.instrumentation,
            payload=instrumentation_payload,
            logical_id=f"excel-instrumentation/{spec.entry_id}",
            semantic_version=spec.semantic_version,
        )
        return template_def, instrumentation_def, instrumentation_payload

    # ─────────────────────────────────────────────────────────────

    def instrument_source_bytes(
        self, *, source: bytes, spec: ExcelInstrumentationSpec
    ) -> tuple[InstrumentedWorkbook, dict[str, Any], dict[str, Any]]:
        """注入 + 等价校验 + 反读。纯函数式（只吃 bytes），不碰 DB 也不碰模板库。"""
        instrumented = instrument_workbook_bytes(source, spec, gate=self._gate)
        equivalence = verify_visible_equivalence(
            source=source, instrumented=instrumented, spec=spec
        )
        inventory = read_back_identity(
            instrumented=instrumented, spec=spec, gate=self._gate
        )
        return instrumented, equivalence, inventory

    # ─────────────────────────────────────────────────────────────

    async def stage_and_register_candidate(
        self,
        *,
        spec: ExcelInstrumentationSpec,
        wp_id: uuid.UUID,
        content_version_id: uuid.UUID,
        source_representation_id: uuid.UUID,
        source_bytes: bytes,
        instrumented: InstrumentedWorkbook,
        equivalence: Mapping[str, Any],
        inventory: Mapping[str, Any],
        template_definition: Any,
        instrumentation_definition: Any,
        from_definition_bundle_id: uuid.UUID | None = None,
        from_definition_bundle_sha256: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> UpgradeCandidateOutcome:
        """把 instrumented 字节移入 candidate 隔离目录并登记 non-current candidate。"""
        before = await self._snapshot(wp_id=wp_id, entry_id=spec.entry_id)

        report = {
            "schema_version": "instrumentation-upgrade-evidence:v1",
            "entry_id": spec.entry_id,
            "template_id": spec.template_id,
            "source_representation_id": str(source_representation_id),
            "content_version_id": str(content_version_id),
            "from_definition_bundle_id": (
                str(from_definition_bundle_id) if from_definition_bundle_id else None
            ),
            "from_definition_bundle_sha256": from_definition_bundle_sha256,
            "template_definition_sha256": template_definition.sha256,
            "instrumentation_definition_sha256": instrumentation_definition.sha256,
            "rollback_source_sha256": _sha256_bytes(source_bytes),
            "instrumented_sha256": instrumented.instrumented_sha256,
            "visible_equivalence": equivalence,
            "identity_inventory": inventory,
            "probe_gate": self.probe_gate_identity(),
        }
        report_bytes = canonical_json_bytes(report)

        staged = self._artifacts.stage_bytes(
            project_id=self._project_id,
            wp_id=wp_id,
            payload=instrumented.instrumented_bytes,
            document_type="xlsx",
            filename="instrumented.tmp",
            expected_sha256=instrumented.instrumented_sha256,
        )
        candidate_artifact = self._artifacts.stage_upgrade_candidate(
            staged=staged, entry_id=spec.entry_id, equivalence_report=report_bytes
        )
        artifact_row = await self._repo.register_artifact(
            project_id=self._project_id,
            wp_id=wp_id,
            kind="upgrade_candidate",
            state="candidate",
            relative_path=candidate_artifact.relative_path,
            sha256=candidate_artifact.sha256,
            size_bytes=candidate_artifact.size_bytes,
            document_type=candidate_artifact.document_type,
        )
        candidate = await self._repo.create_upgrade_candidate(
            project_id=self._project_id,
            wp_id=wp_id,
            entry_id=spec.entry_id,
            content_version_id=content_version_id,
            source_representation_id=source_representation_id,
            staged_artifact_id=artifact_row.id,
            staged_artifact_sha256=candidate_artifact.sha256,
            template_definition_id=template_definition.definition_id,
            instrumentation_definition_id=instrumentation_definition.definition_id,
            # 🔴 三个 target 显式留空：本任务不得伪造 per-entry contract / bundle。
            #    `assert_candidate_finalizable`（Task 12）会因此拒绝 finalize，
            #    直到 Task 36 与 Tasks 40–57 把 approved child 补齐。
            target_contract_definition_id=None,
            target_definition_bundle_id=None,
            state=CandidateState.awaiting_contract,
        )
        candidate.visible_equivalence_report_sha256 = _sha256_bytes(report_bytes)
        candidate.rollback_source_sha256 = _sha256_bytes(source_bytes)
        await self._repo.session.flush()

        after = await self._snapshot(wp_id=wp_id, entry_id=spec.entry_id)
        outcome = UpgradeCandidateOutcome(
            candidate_id=candidate.id,
            wp_id=wp_id,
            entry_id=spec.entry_id,
            content_version_id=content_version_id,
            source_representation_id=source_representation_id,
            from_definition_bundle_id=from_definition_bundle_id,
            from_definition_bundle_sha256=from_definition_bundle_sha256,
            template_definition_id=template_definition.definition_id,
            template_definition_sha256=template_definition.sha256,
            instrumentation_definition_id=instrumentation_definition.definition_id,
            instrumentation_definition_sha256=instrumentation_definition.sha256,
            target_contract_definition_id=None,
            target_definition_bundle_id=None,
            state=CandidateState(candidate.state),
            staged_artifact_id=artifact_row.id,
            staged_artifact_sha256=candidate_artifact.sha256,
            staged_relative_path=candidate_artifact.relative_path,
            rollback_source_sha256=_sha256_bytes(source_bytes),
            visible_equivalence_report_sha256=_sha256_bytes(report_bytes),
            identity_inventory_sha256=canonical_digest(dict(inventory)),
            structure_hash=normalized_structure_hash(instrumented.instrumented_bytes),
            content_revision_before=before["content_revision"],
            content_revision_after=after["content_revision"],
            entry_pointer_before=before["pointer_representation_id"],
            entry_pointer_after=after["pointer_representation_id"],
            representation_count_before=before["representation_count"],
            representation_count_after=after["representation_count"],
            probe_gate=self.probe_gate_identity(),
            actor_id=actor_id,
        )
        assert_candidate_is_non_current(outcome)
        return outcome

    # ─────────────────────────────────────────────────────────────

    def probe_gate_identity(self) -> dict[str, str]:
        """写进 candidate 证据的探针门身份（Requirement 14.16 的记录清单）。"""
        return {
            "carrier_contract_sha256": self._gate.contract_sha256,
            "onlyoffice_build": self._gate.onlyoffice_build,
            "source_commit": self._source_commit,
            "identity_schema_version": IDENTITY_SCHEMA_VERSION,
            "instrumentation_version": INSTRUMENTATION_VERSION,
        }

    async def _snapshot(self, *, wp_id: uuid.UUID, entry_id: str) -> dict[str, Any]:
        """revision / pointer / representation 计数三项实测快照。

        用**裸 SQL** 而不是 ORM 关系遍历：本快照要证明「我没动这三样」，若经由同一批
        ORM 对象读取，session identity map 里的脏对象会让 before/after 读到同一份
        内存态 ⇒ 恒相等 ⇒ 判据空转。
        """
        import sqlalchemy as sa

        revision = (
            await self._session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": str(wp_id)},
            )
        ).scalar_one()
        pointer = (
            await self._session.execute(
                sa.text(
                    "SELECT current_representation_id FROM working_paper_sync_entry_state "
                    "WHERE wp_id = :wp AND entry_id = :e"
                ),
                {"wp": str(wp_id), "e": entry_id},
            )
        ).first()
        count = (
            await self._session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_content_representation "
                    "WHERE wp_id = :wp AND entry_id = :e"
                ),
                {"wp": str(wp_id), "e": entry_id},
            )
        ).scalar_one()
        return {
            "content_revision": int(revision),
            "pointer_representation_id": pointer[0] if pointer else None,
            "representation_count": int(count),
        }
