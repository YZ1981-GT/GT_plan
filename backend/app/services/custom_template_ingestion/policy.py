"""单一 ingestion policy、quota 与 scanner provenance。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 4.3, 4.4, 4.5, 4.6, 4.7, 6.7

## 为什么是「一份」policy（Requirement 3.3）

🔴 本模块是 upload/expanded/entries/ratio/sheet/cell/range/XML/CPU/wall/RAM/FD/
temp disk/org quota 与 TTL 的**唯一真源**。禁止在路由、scanner、worker 或前端再抄
一份阈值常量 —— 那样「散落魔数」会成为假绿第①源：改了 policy 却漏改某处，测试
全绿而生产按旧阈值放行。所有消费方必须 `from ... import POLICY_V1` 或注入
`CustomTemplateIngestionPolicy` 实例。

## 空报告永不 valid（Requirement 3.6）

`validate_against_policy()` 对**空** `ResourceObservation`（未提供任何观测值）或
**异常**观测值（负数、NaN）一律返回 `BLOCKER` finding 且 `verdict=BLOCKED`。
`verdict` 只能由 findings 派生（`derive_verdict()`），不存在「无 finding 即 valid」
的默认分支 —— 这是本模块最重要的结构性防假绿点。

## 阈值变化使旧 evidence stale（Requirement 3.4 / 3.5）

`ScannerProvenance.fingerprint()` 冻结 policy 指纹 + scanner build digest +
worker image digest + parser versions。`is_stale_for()` 比较三者：任一变化即
stale，必须重新 preflight 前不得 finalize。

🔴 这里用的是**派生比较**，不是「字符串包含」：`test_provenance_fingerprint_is_
derived_not_client_supplied` 锁死 fingerprint 不可手写注入，防止有人构造一个
「看起来匹配」的 digest 绕过 stale 判定。

## content fingerprint 分离（承接 Task 2 / Requirement 11.7）

policy 只描述**摄取**约束，绝不参与角色/权限判断；反之角色也绝不进入本模块。
这条边界由 `test_policy_never_carries_role_fields` 锁死。
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

# ─────────────────────────────────────────────────────────────────────────────
# 0) 单位常量 —— 只做单位换算，禁止把它们当阈值用
# ─────────────────────────────────────────────────────────────────────────────

_KIB: int = 1024
_MIB: int = _KIB * _KIB
_GIB: int = _MIB * _KIB

SECOND: int = 1
MINUTE: int = 60 * SECOND
HOUR: int = 60 * MINUTE
DAY: int = 24 * HOUR


# ─────────────────────────────────────────────────────────────────────────────
# 1) 政策版本与裁决枚举
# ─────────────────────────────────────────────────────────────────────────────

POLICY_CONTRACT_VERSION: str = "1"
POLICY_VERSION_V1: str = f"custom-template-ingestion-policy/v{POLICY_CONTRACT_VERSION}.0.0"


class Severity(str, Enum):
    """finding 严重度。只有 BLOCKER 会使 verdict 变为 BLOCKED。"""

    BLOCKER = "BLOCKER"
    WARNING = "WARNING"
    INFO = "INFO"


class FeatureDecision(str, Enum):
    """OOXML 能力矩阵裁决（Requirement 4.3–4.7）。

    * ``ALLOW_TO_PREFLIGHT`` —— 可进入完整 preflight（`.xlsx`）
    * ``PREFLIGHT_ONLY`` —— 只允许 quarantine + 只读 preflight，finalize 永久阻断
      （`.xlsm`；Requirement 4.4：不得改扩展名或用 ``keep_vba=False`` 静默丢宏）
    * ``BLOCK`` —— 无条件阻断，无 sanitizer（Requirement 4.5 / 4.6）
    * ``BLOCK_PENDING_POLICY`` —— 未知能力 fail-closed 挂起（Requirement 4.7）
    """

    ALLOW_TO_PREFLIGHT = "ALLOW_TO_PREFLIGHT"
    PREFLIGHT_ONLY = "PREFLIGHT_ONLY"
    BLOCK = "BLOCK"
    BLOCK_PENDING_POLICY = "BLOCK_PENDING_POLICY"


#: 允许 finalize 的裁决集合 —— 只有它才可能走到 publication。
#: 🔴 `.xlsm` 的 PREFLIGHT_ONLY **不在**其中：Requirement 4.4 的 finalize 永久阻断
#: 是结构性保证，不是靠散落 if 判断。
FINALIZE_CAPABLE: frozenset[FeatureDecision] = frozenset({
    FeatureDecision.ALLOW_TO_PREFLIGHT,
})


class Verdict(str, Enum):
    """preflight 结论，只能由 findings 派生。"""

    BLOCKED = "BLOCKED"
    PREFLIGHT_READY = "PREFLIGHT_READY"


# ─────────────────────────────────────────────────────────────────────────────
# 2) 政策对象 —— 全部阈值的唯一真源（Requirement 3.3）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CustomTemplateIngestionPolicy:
    """版本化摄取政策。

    🔴 frozen + slots：政策不可原地修改。阈值调整必须**新建** policy（递增
    version），使既有 evidence 由 ``is_stale_for()`` 判 stale（Requirement 3.4）。

    Attributes:
        version: 政策版本标识，必须包含版本号，禁止为空。
        max_upload_bytes: 流式上传的字节上限（含 multipart 头部前的正文）。
        max_expanded_bytes: ZIP 解压后**全部** entry 的总字节数上限（zip bomb 防线）。
        max_zip_entries: ZIP entry 数量上限。
        max_entry_compression_ratio: 单项压缩比上限（uncompressed/compressed）。
        max_total_compression_ratio: 整包压缩比上限。
        max_sheets: workbook sheet 数上限。
        max_non_empty_cells: 全册非空单元格上限。
        max_declared_range_cells: 单个 sheet 声明范围（dimension）单元格上限 ——
            用于拦「稀疏炸弹」（声明 2^20×2^15 但只写 1 格）。
        max_xml_bytes: 单个 XML part 字节上限。
        max_xml_depth: XML 嵌套深度上限（拦 billion laughs / deeply-nested DoS）。
        max_xml_nodes: 单个 XML 节点数上限。
        max_relationships: OOXML relationship 总数上限。
        max_cpu_seconds: worker CPU 时间预算。
        max_wall_seconds: worker 墙钟时间预算（Requirement 3.3 明写 120）。
        max_ram_bytes: worker 常驻内存上限。
        max_file_descriptors: worker FD 上限。
        max_temp_disk_bytes: worker 临时磁盘上限。
        organization_concurrency: 单组织并发 preflight 数上限。
        organization_storage_bytes: 单组织 quarantine 存储上限。
        incoming_ttl_seconds: quarantine 原始字节保留期（Requirement 15.6 明写 24h）。
        failed_artifact_ttl_seconds: failed/rejected 保留期（7d）。
        candidate_ttl_seconds: 未发布 candidate 保留期（30d）。
    """

    version: str = POLICY_VERSION_V1
    max_upload_bytes: int = 50 * _MIB
    max_expanded_bytes: int = 512 * _MIB
    max_zip_entries: int = 20_000
    max_entry_compression_ratio: float = 100.0
    max_total_compression_ratio: float = 100.0
    max_sheets: int = 256
    max_non_empty_cells: int = 5_000_000
    max_declared_range_cells: int = 20_000_000
    max_xml_bytes: int = 128 * _MIB
    max_xml_depth: int = 128
    max_xml_nodes: int = 5_000_000
    max_relationships: int = 20_000
    max_cpu_seconds: float = 60.0
    max_wall_seconds: int = 120
    max_ram_bytes: int = 2 * _GIB
    max_file_descriptors: int = 256
    max_temp_disk_bytes: int = 4 * _GIB
    organization_concurrency: int = 8
    organization_storage_bytes: int = 5 * _GIB
    incoming_ttl_seconds: int = 24 * HOUR
    failed_artifact_ttl_seconds: int = 7 * DAY
    candidate_ttl_seconds: int = 30 * DAY

    def __post_init__(self) -> None:
        """构造即校验：阈值必须是有限、正数、彼此自洽。

        🔴 这条防线针对「阈值被写成 0/负数/NaN」的静默失效 —— 那会让
        validate 全部放行或全部拒绝，而测试若只测「大于即 BLOCKER」会漏掉。
        """
        if not self.version or self.version.strip() == "":
            raise ValueError("policy version 不可为空")
        self._require_positive_int_fields()
        self._require_positive_finite_float_fields()
        # 自洽：单项压缩比必须 <= 总压缩比（否则单项检查形同虚设）
        if self.max_entry_compression_ratio > self.max_total_compression_ratio + 1e-9:
            raise ValueError(
                "max_entry_compression_ratio 不得大于 max_total_compression_ratio"
            )
        # 自洽：上传上限不得大于解压上限（解压上限是更宽的口子）
        if self.max_upload_bytes > self.max_expanded_bytes:
            raise ValueError("max_upload_bytes 不得大于 max_expanded_bytes")
        # 自洽：TTL 必须严格递增（incoming < failed < candidate），
        # 否则 retention 会「先删后保」，违反 Requirement 15.6 的期限语义。
        if not (
            self.incoming_ttl_seconds
            < self.failed_artifact_ttl_seconds
            < self.candidate_ttl_seconds
        ):
            raise ValueError(
                "TTL 必须严格递增：incoming < failed_artifact < candidate"
            )

    def _require_positive_int_fields(self) -> None:
        for name in _POSITIVE_INT_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"policy 字段 {name!r} 必须为正整数，实际 {value!r}")

    def _require_positive_finite_float_fields(self) -> None:
        for name in _POSITIVE_FLOAT_FIELDS:
            value = getattr(self, name)
            if not isinstance(value, (int, float)):
                raise ValueError(f"policy 字段 {name!r} 必须是数值，实际 {type(value).__name__}")
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(f"policy 字段 {name!r} 必须是有限正数，实际 {value!r}")

    def to_dict(self) -> dict[str, Any]:
        """政策快照（供 evidence 冻结与只读展示 endpoint）。"""
        return {
            "version": self.version,
            "thresholds": {
                name: getattr(self, name)
                for name in _POSITIVE_INT_FIELDS + _POSITIVE_FLOAT_FIELDS
            },
        }

    def fingerprint(self) -> str:
        """政策指纹：由 version + 全部阈值派生，不可手写注入。

        🔴 排序序列化保证同一语义、不同字段顺序得到同一指纹。测试
        ``test_policy_fingerprint_is_derived`` 会校验它是 sha256 的 hexdigest
        前缀，防止有人把 fingerprint 改成客户端可控字段。
        """
        payload = json.dumps(
            {"version": self.version, "thresholds": self.to_dict()["thresholds"]},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


#: 整数阈值字段（Requirement 3.3 列举的字节/条目/单元格/XML/CPU/FD/TTL 项）。
_POSITIVE_INT_FIELDS: tuple[str, ...] = (
    "max_upload_bytes",
    "max_expanded_bytes",
    "max_zip_entries",
    "max_sheets",
    "max_non_empty_cells",
    "max_declared_range_cells",
    "max_xml_bytes",
    "max_xml_depth",
    "max_xml_nodes",
    "max_relationships",
    "max_wall_seconds",
    "max_ram_bytes",
    "max_file_descriptors",
    "max_temp_disk_bytes",
    "organization_concurrency",
    "organization_storage_bytes",
    "incoming_ttl_seconds",
    "failed_artifact_ttl_seconds",
    "candidate_ttl_seconds",
)

#: 浮点阈值字段（压缩比与 CPU 秒允许小数）。
_POSITIVE_FLOAT_FIELDS: tuple[str, ...] = (
    "max_entry_compression_ratio",
    "max_total_compression_ratio",
    "max_cpu_seconds",
)


#: 服务端唯一默认政策实例。
POLICY_V1: CustomTemplateIngestionPolicy = CustomTemplateIngestionPolicy()


# ─────────────────────────────────────────────────────────────────────────────
# 3) OOXML 能力矩阵（Requirement 4.3–4.7）—— fail-closed
# ─────────────────────────────────────────────────────────────────────────────

#: 能力 key → 裁决。**新增能力必须显式登记**；未登记的走 BLOCK_PENDING_POLICY。
FEATURE_MATRIX: dict[str, FeatureDecision] = {
    # ── 容器格式 ──
    "container.xlsx": FeatureDecision.ALLOW_TO_PREFLIGHT,
    # Requirement 4.4：v1 只允许 quarantine + 只读 preflight，FINALIZE 永久阻断。
    # 不得改扩展名或用 keep_vba=False 静默丢宏后发布。
    "container.xlsm": FeatureDecision.PREFLIGHT_ONLY,
    # ── 可执行 / 外部交互（Requirement 4.5）──
    "vba_macro": FeatureDecision.BLOCK,
    "xlm_macro": FeatureDecision.BLOCK,
    "dde_link": FeatureDecision.BLOCK,
    "activex_control": FeatureDecision.BLOCK,
    "ole_embedded_object": FeatureDecision.BLOCK,
    "remote_data_connection": FeatureDecision.BLOCK,
    # ── 外部依赖（Requirement 4.6：v1 永久 BLOCKER，无 sanitizer）──
    "external_link": FeatureDecision.BLOCK,
    "external_relationship": FeatureDecision.BLOCK,
    "external_data_connection": FeatureDecision.BLOCK,
    # ── 损坏/加密（Requirement 4.2）──
    "encrypted_package": FeatureDecision.BLOCK,
    "password_protected": FeatureDecision.BLOCK,
    "corrupt_package": FeatureDecision.BLOCK,
    # ── 允许但必须进入 preservation inventory（Requirement 4.7）──
    "image": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "chart": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "drawing": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "comment": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "defined_name": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "table": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "data_validation": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "conditional_formatting": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "merged_cell": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "hidden_row_or_col": FeatureDecision.ALLOW_TO_PREFLIGHT,
    "sheet_protection": FeatureDecision.ALLOW_TO_PREFLIGHT,
}


def decide_feature(feature: str) -> FeatureDecision:
    """解析一个 OOXML 能力的裁决。

    🔴 未登记能力返回 ``BLOCK_PENDING_POLICY``（Requirement 4.7），**不**返回
    ALLOW —— 这是 fail-closed 的唯一实现点，禁止在调用方再写一层 if 放行。
    """
    key = (feature or "").strip().casefold()
    if not key:
        return FeatureDecision.BLOCK_PENDING_POLICY
    return FEATURE_MATRIX.get(key, FeatureDecision.BLOCK_PENDING_POLICY)


def finalize_allowed(decision: FeatureDecision) -> bool:
    """该裁决是否允许进入 finalize/publication。

    Requirement 4.4/4.5/4.6/4.7 的结构性保证：PREFLIGHT_ONLY（.xlsm）、
    BLOCK、BLOCK_PENDING_POLICY 全部返回 False。
    """
    return decision in FINALIZE_CAPABLE


#: 允许 finalize 的能力必须进入 preservation inventory（Requirement 4.7：
#: image/chart/drawing/comment/name/table/validation/CF/merge/hidden/protection
#: 等允许项不得因 HTML 不消费而静默丢失）。
PRESERVATION_INVENTORY_FEATURES: frozenset[str] = frozenset({
    "image",
    "chart",
    "drawing",
    "comment",
    "defined_name",
    "table",
    "data_validation",
    "conditional_formatting",
    "merged_cell",
    "hidden_row_or_col",
    "sheet_protection",
})


# ─────────────────────────────────────────────────────────────────────────────
# 4) 观测值与 finding
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ResourceObservation:
    """一次 preflight 的实测资源用量（Requirement 3.5 / 3.7）。

    🔴 **全字段可选**：scanner/worker 崩溃、取消、timeout 时可能只上报部分字段。
    但 ``validate_against_policy`` 对空观测（未上报任何预算字段）判 BLOCKER ——
    见下方空报告防线。缺失字段不会被当成 0 放行。
    """

    upload_bytes: int | None = None
    expanded_bytes: int | None = None
    zip_entries: int | None = None
    entry_compression_ratio: float | None = None
    total_compression_ratio: float | None = None
    sheets: int | None = None
    non_empty_cells: int | None = None
    max_declared_range_cells: int | None = None
    xml_bytes: int | None = None
    xml_depth: int | None = None
    xml_nodes: int | None = None
    relationships: int | None = None
    cpu_seconds: float | None = None
    wall_seconds: float | None = None
    ram_bytes: int | None = None
    file_descriptors: int | None = None
    temp_disk_bytes: int | None = None
    organization_active_preflights: int | None = None
    organization_storage_used_bytes: int | None = None


#: 观测字段 → policy 阈值字段的映射。唯一真源，禁止在循环里硬编码字段名。
_OBSERVATION_LIMITS: tuple[tuple[str, str], ...] = (
    ("upload_bytes", "max_upload_bytes"),
    ("expanded_bytes", "max_expanded_bytes"),
    ("zip_entries", "max_zip_entries"),
    ("entry_compression_ratio", "max_entry_compression_ratio"),
    ("total_compression_ratio", "max_total_compression_ratio"),
    ("sheets", "max_sheets"),
    ("non_empty_cells", "max_non_empty_cells"),
    ("max_declared_range_cells", "max_declared_range_cells"),
    ("xml_bytes", "max_xml_bytes"),
    ("xml_depth", "max_xml_depth"),
    ("xml_nodes", "max_xml_nodes"),
    ("relationships", "max_relationships"),
    ("cpu_seconds", "max_cpu_seconds"),
    ("wall_seconds", "max_wall_seconds"),
    ("ram_bytes", "max_ram_bytes"),
    ("file_descriptors", "max_file_descriptors"),
    ("temp_disk_bytes", "max_temp_disk_bytes"),
    ("organization_active_preflights", "organization_concurrency"),
    ("organization_storage_used_bytes", "organization_storage_bytes"),
)


@dataclass(frozen=True, slots=True)
class Finding:
    """结构化 finding（Requirement 3.7 / 5.7）。

    Attributes:
        code: 稳定机器码（如 ``POLICY.upload_bytes_exceeded``）。
        severity: BLOCKER 才使 verdict 变为 BLOCKED。
        locator: 定位（observed/limit 名、feature key 等）。
        policy_decision: 人类可读的裁决理由。
        remediation: 可操作的修复建议。
        observed: 实测值。
        limit: 政策阈值。
    """

    code: str
    severity: Severity
    locator: str
    policy_decision: str
    remediation: str
    observed: Any = None
    limit: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "locator": self.locator,
            "policyDecision": self.policy_decision,
            "remediation": self.remediation,
            "observed": self.observed,
            "limit": self.limit,
        }


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """preflight 结构化结论。

    🔴 ``verdict`` 只能由 ``derive_verdict()`` 从 findings 派生，不存在
    「无 finding 即 valid」的隐式分支（Requirement 3.6）。
    """

    verdict: Verdict
    findings: tuple[Finding, ...]
    preservation_inventory: tuple[str, ...]
    policy_version: str

    @property
    def is_valid(self) -> bool:
        """verdict 的别名，便于调用方书写。"""
        return self.verdict == Verdict.PREFLIGHT_READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "valid": self.is_valid,
            "findings": [f.to_dict() for f in self.findings],
            "preservationInventory": list(self.preservation_inventory),
            "policyVersion": self.policy_version,
        }


def derive_verdict(findings: tuple[Finding, ...]) -> Verdict:
    """从 findings 派生 verdict。

    🔴 没有任何隐式 PASS 分支：只要 findings 为空，也返回 BLOCKED —— 空 findings
    意味着观测缺失（见 ``validate_against_policy`` 的空报告防线），而不是「全部通过」。
    真正通过的报告必须**显式**包含一条 ``Severity.INFO`` 的 ``POLICY.all_within_limits``，
    此时仍无任何 BLOCKER，verdict 才为 PREFLIGHT_READY。
    """
    if not findings:
        return Verdict.BLOCKED
    return Verdict.BLOCKED if any(f.severity is Severity.BLOCKER for f in findings) else Verdict.PREFLIGHT_READY


# ─────────────────────────────────────────────────────────────────────────────
# 5) 预算校验（Requirement 3.3 / 3.6 / 3.7）
# ─────────────────────────────────────────────────────────────────────────────

#: 空报告 finding 的稳定 code。
FINDING_EMPTY_REPORT: str = "POLICY.empty_report"
FINDING_INVALID_OBSERVATION: str = "POLICY.invalid_observation"
FINDING_WITHIN_LIMITS: str = "POLICY.all_within_limits"


def validate_against_policy(
    observation: ResourceObservation,
    policy: CustomTemplateIngestionPolicy = POLICY_V1,
) -> PreflightResult:
    """把实测资源用量与政策阈值逐项比对。

    规则：

    1. **空观测**（未上报任何预算字段）→ 单条 BLOCKER，verdict=BLOCKED。
       这是 Requirement 3.6「不得返回空报告或 valid=true」的实现点。
    2. **非法值**（负数 / NaN / inf）→ BLOCKER。scanner 崩溃或取消时可能上报
       异常值，绝不能被当作 0 放行。
    3. 超限 → BLOCKER（结构化 code = ``POLICY.<field>_exceeded``）。
    4. 全部合法且未超限 → 一条 INFO ``POLICY.all_within_limits``，verdict=PREFLIGHT_READY。
    """
    findings: list[Finding] = []
    observed_values = [(name, getattr(observation, name)) for name, _ in _OBSERVATION_LIMITS]
    reported = [(name, value) for name, value in observed_values if value is not None]

    if not reported:
        findings.append(Finding(
            code=FINDING_EMPTY_REPORT,
            severity=Severity.BLOCKER,
            locator="ResourceObservation",
            policy_decision="preflight 未上报任何资源观测值",
            remediation="禁止返回空报告；scanner/worker 失败必须结构化上报失败态（Requirement 3.6）",
        ))
        return PreflightResult(
            verdict=derive_verdict(tuple(findings)),
            findings=tuple(findings),
            preservation_inventory=(),
            policy_version=policy.version,
        )

    for obs_name, limit_name in _OBSERVATION_LIMITS:
        value = getattr(observation, obs_name)
        if value is None:
            continue
        limit = getattr(policy, limit_name)
        if not _is_valid_observation(value):
            findings.append(Finding(
                code=FINDING_INVALID_OBSERVATION,
                severity=Severity.BLOCKER,
                locator=obs_name,
                policy_decision=f"观测值非法: {value!r}",
                remediation="scanner/worker 崩溃或取消必须结构化失败，不得上报异常数值",
                observed=value,
                limit=limit,
            ))
            continue
        if value > limit:
            findings.append(Finding(
                code=f"POLICY.{obs_name}_exceeded",
                severity=Severity.BLOCKER,
                locator=obs_name,
                policy_decision=(
                    f"{obs_name}={value!r} 超过政策阈值 {limit_name}={limit!r}"
                ),
                remediation=f"缩减 {obs_name} 至 {limit} 以内后重试",
                observed=value,
                limit=limit,
            ))

    if not findings:
        findings.append(Finding(
            code=FINDING_WITHIN_LIMITS,
            severity=Severity.INFO,
            locator="ResourceObservation",
            policy_decision="全部上报项均在政策阈值内",
            remediation="无需处理",
            observed=None,
            limit=None,
        ))

    return PreflightResult(
        verdict=derive_verdict(tuple(findings)),
        findings=tuple(findings),
        preservation_inventory=(),
        policy_version=policy.version,
    )


def _is_valid_observation(value: Any) -> bool:
    """观测值必须是有限非负数（整数或浮点）。"""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value >= 0
    if isinstance(value, float):
        return math.isfinite(value) and value >= 0
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 6) Scanner provenance envelope（Requirement 3.5 / 3.4）
# ─────────────────────────────────────────────────────────────────────────────


class ScannerProvenanceError(ValueError):
    """provenance 载荷不合法。"""


@dataclass(frozen=True, slots=True)
class ScannerProvenance:
    """scanner/worker 执行的 provenance 信封。

    Attributes:
        policy_version: 本次执行使用的政策版本。
        policy_fingerprint: 由 policy 派生的指纹（不可手写注入）。
        scanner_build_digest: scanner 构建产物摘要。
        worker_image_digest: worker 容器镜像 digest（Docker 风格 ``sha256:...``）。
        parser_versions: 解析库版本字典（openpyxl/zipfile/lxml 等）。
        resource_observations: 实际资源用量（Requirement 3.5 明写「资源用量」）。
    """

    policy_version: str
    policy_fingerprint: str
    scanner_build_digest: str
    worker_image_digest: str
    parser_versions: dict[str, str]
    resource_observations: ResourceObservation = field(default_factory=ResourceObservation)

    def __post_init__(self) -> None:
        for name in ("policy_version", "scanner_build_digest", "worker_image_digest"):
            value = getattr(self, name)
            if not value or not str(value).strip():
                raise ScannerProvenanceError(f"provenance 字段 {name!r} 不可为空")
        if not self.parser_versions:
            raise ScannerProvenanceError("parser_versions 不可为空（Requirement 3.5）")

    def fingerprint(self) -> str:
        """provenance 指纹：policy + scanner build + worker image + parser versions。

        🔴 **不**纳入 resource_observations —— 资源用量随运行波动，纳入会让
        「同一 policy + 同一 scanner build」的两次合法运行得到不同指纹，stale
        判定失去意义。资源用量单独序列化供审计，但参与不了 staleness。

        🔴 由字段派生，不可手写注入：测试校验 fingerprint == 期望 sha256 前缀。
        """
        payload = json.dumps(
            {
                "policyVersion": self.policy_version,
                "policyFingerprint": self.policy_fingerprint,
                "scannerBuildDigest": self.scanner_build_digest,
                "workerImageDigest": self.worker_image_digest,
                "parserVersions": self.parser_versions,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_stale_for(
        self,
        *,
        policy: CustomTemplateIngestionPolicy,
        scanner_build_digest: str,
        worker_image_digest: str,
    ) -> bool:
        """判断本 provenance 是否已 stale（Requirement 3.4 / 3.5）。

        任一变化即 stale：
        * 政策阈值或版本（policy fingerprint）
        * scanner build digest
        * worker image digest

        🔴 这里用**派生指纹等值**判定，不比较 policy_version 字符串 —— 因为
        version 相同的两份 policy 可能阈值不同（如手工改错），只有指纹能捕获。
        """
        return (
            self.policy_fingerprint != policy.fingerprint()
            or self.scanner_build_digest != scanner_build_digest
            or self.worker_image_digest != worker_image_digest
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "policyVersion": self.policy_version,
            "policyFingerprint": self.policy_fingerprint,
            "scannerBuildDigest": self.scanner_build_digest,
            "workerImageDigest": self.worker_image_digest,
            "parserVersions": dict(self.parser_versions),
            "resourceObservations": {name: getattr(self.resource_observations, name)
                                     for name, _ in _OBSERVATION_LIMITS},
            "provenanceFingerprint": self.fingerprint(),
        }


def build_provenance(
    *,
    policy: CustomTemplateIngestionPolicy,
    scanner_build_digest: str,
    worker_image_digest: str,
    parser_versions: dict[str, str],
    resource_observations: ResourceObservation | None = None,
) -> ScannerProvenance:
    """构造 provenance，policy fingerprint 由 policy 派生。

    🔴 不接受客户端传入的 policy_fingerprint —— 由 policy 唯一计算。这样
    「未知构建复用旧 PASS」（Requirement 17.2 变异项）在构造层就无法伪造。
    """
    return ScannerProvenance(
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint(),
        scanner_build_digest=scanner_build_digest,
        worker_image_digest=worker_image_digest,
        parser_versions=dict(parser_versions),
        resource_observations=resource_observations or ResourceObservation(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7) 组织 quota 准入（Requirement 3.3 / 3.7）
# ─────────────────────────────────────────────────────────────────────────────

#: quota 相关 finding code。
FINDING_ORG_CONCURRENCY_EXCEEDED: str = "POLICY.organization_concurrency_exceeded"
FINDING_ORG_STORAGE_EXCEEDED: str = "POLICY.organization_storage_exceeded"


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    """组织级 quota 准入结论。"""

    admitted: bool
    findings: tuple[Finding, ...]
    organization_id: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "organizationId": self.organization_id,
            "policyVersion": self.policy_version,
            "findings": [f.to_dict() for f in self.findings],
        }


def check_organization_quota(
    *,
    organization_id: str,
    active_preflights: int,
    storage_used_bytes: int,
    pending_upload_bytes: int,
    policy: CustomTemplateIngestionPolicy = POLICY_V1,
) -> AdmissionResult:
    """准入检查：并发 preflight 数与组织存储。

    🔴 传入值非法（负数）时判拒绝而非放行 —— quota 检查崩溃时 fail-closed。
    ``pending_upload_bytes`` 会累加进已用存储再比较，避免「已用 90% 但还有
    10 次并发请求」全部通过后存储爆掉。
    """
    findings: list[Finding] = []
    if (
        not isinstance(active_preflights, int)
        or not isinstance(storage_used_bytes, int)
        or not isinstance(pending_upload_bytes, int)
        or active_preflights < 0
        or storage_used_bytes < 0
        or pending_upload_bytes < 0
        or not organization_id.strip()
    ):
        findings.append(Finding(
            code="POLICY.quota_input_invalid",
            severity=Severity.BLOCKER,
            locator="organization_quota",
            policy_decision="quota 输入非法（必须为非负整数且 organization_id 非空）",
            remediation="服务端推导组织身份与真实用量，不得接受非法客户端值",
        ))
        return AdmissionResult(
            admitted=False,
            findings=tuple(findings),
            organization_id=organization_id,
            policy_version=policy.version,
        )

    if active_preflights >= policy.organization_concurrency:
        findings.append(Finding(
            code=FINDING_ORG_CONCURRENCY_EXCEEDED,
            severity=Severity.BLOCKER,
            locator="organization_concurrency",
            policy_decision=(
                f"组织 {organization_id} 并发 preflight {active_preflights} "
                f"已达上限 {policy.organization_concurrency}"
            ),
            remediation="等待既有 preflight 完成或提高组织并发配额",
            observed=active_preflights,
            limit=policy.organization_concurrency,
        ))

    projected = storage_used_bytes + pending_upload_bytes
    if projected > policy.organization_storage_bytes:
        findings.append(Finding(
            code=FINDING_ORG_STORAGE_EXCEEDED,
            severity=Severity.BLOCKER,
            locator="organization_storage_bytes",
            policy_decision=(
                f"组织 {organization_id} 预计存储 {projected} 字节 "
                f"超过配额 {policy.organization_storage_bytes}"
            ),
            remediation="清理过期 quarantine 字节或提高组织存储配额",
            observed=projected,
            limit=policy.organization_storage_bytes,
        ))

    return AdmissionResult(
        admitted=not findings,
        findings=tuple(findings),
        organization_id=organization_id,
        policy_version=policy.version,
    )
