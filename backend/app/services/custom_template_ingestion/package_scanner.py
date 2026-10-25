"""ZIP/XML/OOXML package security scanner（Task 5）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1

## 本模块交付什么、不交付什么

**交付**：对 quarantine 内的 ZIP 字节做包级安全扫描：路径规范化、symlink、
碰撞、压缩比/条目预算、禁 DTD 的 XML、OOXML 能力矩阵、preservation inventory。
公式只当不可信文本过 XML，**不计算**。

**不交付**：

* 不生成 HTML / OnlyOffice config / WOPI / runtime entry（与 quarantine 同口径）；
* 不做逐 sheet 语义 preflight（Task 6）；
* 不访问网络：不 fetch relationship Target、不解析 external link 目标。

## 空报告永不 valid（Requirement 3.6 / 5.7）

``derive_verdict`` 复用 policy 模块：空 findings → BLOCKED。真正通过必须带
显式 INFO ``PACKAGE.scan_complete``，且无 BLOCKER。

## .xlsm / VBA 的分工（Requirement 4.4 vs 4.5）

* 容器 ``container.xlsm`` → PREFLIGHT_ONLY，finalize 永久阻断，但**允许**
  产出只读 preflight 报告；
* ``vba_macro`` 本身是 BLOCK —— 不得交浏览器 / OnlyOffice 执行。
  因此含 ``xl/vbaProject.bin`` 的包 verdict=BLOCKED（可解释、可复现），
  而不是改扩展名或丢宏后放行。
"""
from __future__ import annotations

import io
import logging
import time
import zipfile
from dataclasses import dataclass
from typing import Callable, Iterable
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.services.custom_template_ingestion.package_paths import (
    CanonicalZipPath,
    PathRejection,
    PathRejectionCode,
    find_casefold_collisions,
    inspect_zip_entry_name,
    is_symlink_external_attr,
)
from app.services.custom_template_ingestion.package_xml import (
    XmlScanRejection,
    XmlScanStats,
    scan_xml_bytes,
)
from app.services.custom_template_ingestion.policy import (
    POLICY_V1,
    PRESERVATION_INVENTORY_FEATURES,
    CustomTemplateIngestionPolicy,
    FeatureDecision,
    Finding,
    PreflightResult,
    ResourceObservation,
    Severity,
    Verdict,
    decide_feature,
    derive_verdict,
    finalize_allowed,
    validate_against_policy,
)

logger = logging.getLogger(__name__)

SCANNER_BUILD_ID: str = "custom-template-package-scanner/v1.0.0"

FINDING_SCAN_COMPLETE: str = "PACKAGE.scan_complete"
FINDING_CORRUPT: str = "PACKAGE.corrupt_package"
FINDING_ENCRYPTED: str = "PACKAGE.encrypted_package"
FINDING_PASSWORD: str = "PACKAGE.password_protected"
FINDING_TIMEOUT: str = "PACKAGE.wall_seconds_exceeded"
FINDING_BUDGET: str = "PACKAGE.resource_budget"

#: ZIP 加密位。
_ZIP_ENCRYPTED_FLAG: int = 0x1

#: 已知 OOXML 关系类型 → FEATURE_MATRIX key。未登记且不在良性白名单中的
#: relationship type 走 decide_feature(未知) → BLOCK_PENDING_POLICY。
_RELATIONSHIP_TYPE_FEATURES: dict[str, str] = {
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument": "container.xlsx",
    "http://schemas.microsoft.com/office/2006/relationships/vbaProject": "vba_macro",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject": "ole_embedded_object",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink": "external_link",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image": "image",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart": "chart",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing": "drawing",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments": "comment",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/table": "table",
}

#: 标准工作簿必需/常见关系。这些不是「未知能力」，不得 BLOCK_PENDING。
_BENIGN_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/calcChain",
    "http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/extendedProperties",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing",
})

#: [Content_Types].xml Override ContentType → feature key。
_CONTENT_TYPE_FEATURES: dict[str, str] = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml": "container.xlsx",
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml": "container.xlsm",
    "application/vnd.ms-office.vbaProject": "vba_macro",
    "application/vnd.openxmlformats-officedocument.drawingml.chart+xml": "chart",
    "application/vnd.openxmlformats-officedocument.drawing+xml": "drawing",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.comments+xml": "comment",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.table+xml": "table",
}

#: 路径前缀 / 精确名 → feature（不依赖 Content_Types，防止漏登记）。
_PATH_FEATURE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("xl/vbaProject.bin", "vba_macro"),
    ("xl/externalLinks/", "external_link"),
    ("xl/activeX/", "activex_control"),
    ("xl/embeddings/", "ole_embedded_object"),
    ("xl/drawings/", "drawing"),
    ("xl/charts/", "chart"),
    ("xl/media/", "image"),
    ("xl/tables/", "table"),
    ("xl/comments", "comment"),
    ("xl/connections.xml", "external_data_connection"),
    ("xl/macrosheets/", "xlm_macro"),
    ("EncryptionInfo", "encrypted_package"),
    ("EncryptedPackage", "encrypted_package"),
)

#: 允许出现、不单独登记为未知能力的 ContentType（Default/Override 白名单）。
_BENIGN_CONTENT_TYPES: frozenset[str] = frozenset({
    "application/xml",
    "application/vnd.openxmlformats-package.relationships+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "application/vnd.openxmlformats-package.core-properties+xml",
    "application/vnd.openxmlformats-officedocument.extended-properties+xml",
    "application/vnd.openxmlformats-officedocument.theme+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.calcChain+xml",
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/vnd.openxmlformats-officedocument.vmlDrawing",
})


class MonotonicClock:
    """墙钟预算用单调时钟（Requirement 6.7：测试可注入，不 sleep）。"""

    def monotonic(self) -> float:
        return time.monotonic()


@dataclass(frozen=True, slots=True)
class PackageScanResult:
    """包级扫描结论。

    ``preflight`` 的 ``valid`` / ``verdict`` 只能由 findings 派生。
    ``container_kind`` 是观测，不是裁决；裁决走 FEATURE_MATRIX。
    """

    preflight: PreflightResult
    container_kind: str | None
    observed_features: tuple[str, ...]
    entry_count: int
    expanded_bytes: int
    relationships: int
    observation: ResourceObservation
    finalize_blocked: bool
    xml_stats: tuple[XmlScanStats, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.preflight.is_valid

    def to_dict(self) -> dict:
        return {
            "preflight": self.preflight.to_dict(),
            "containerKind": self.container_kind,
            "observedFeatures": list(self.observed_features),
            "entryCount": self.entry_count,
            "expandedBytes": self.expanded_bytes,
            "relationships": self.relationships,
            "finalizeBlocked": self.finalize_blocked,
        }


def scan_package_bytes(
    payload: bytes,
    *,
    policy: CustomTemplateIngestionPolicy = POLICY_V1,
    clock: MonotonicClock | None = None,
    filename_hint: str | None = None,
) -> PackageScanResult:
    """扫描一段 ZIP/OOXML 字节。永不返回空 findings。"""
    started = (clock or MonotonicClock()).monotonic()
    findings: list[Finding] = []
    observed_features: set[str] = set()
    preservation: list[str] = []
    xml_stats: list[XmlScanStats] = []
    relationships = 0
    expanded_bytes = 0
    max_xml_bytes = 0
    max_xml_depth = 0
    max_xml_nodes = 0
    entry_count = 0
    container_kind: str | None = None
    max_entry_ratio = 0.0

    def _timed_out() -> bool:
        return (clock or MonotonicClock()).monotonic() - started > policy.max_wall_seconds

    def _add_feature(feature: str, locator: str) -> None:
        key = feature.strip().casefold()
        if not key:
            key = "unknown_empty"
        observed_features.add(key)
        decision = decide_feature(key)
        if key in PRESERVATION_INVENTORY_FEATURES and key not in preservation:
            preservation.append(key)
        if decision is FeatureDecision.BLOCK:
            findings.append(Finding(
                code=f"PACKAGE.feature_{key}",
                severity=Severity.BLOCKER,
                locator=locator,
                policy_decision=f"{key}={decision.value}",
                remediation="移除此能力后重新上传；v1 无 sanitizer",
            ))
        elif decision is FeatureDecision.BLOCK_PENDING_POLICY:
            findings.append(Finding(
                code=f"PACKAGE.feature_pending_{key}",
                severity=Severity.BLOCKER,
                locator=locator,
                policy_decision=f"{key}={decision.value}",
                remediation="未知 OOXML 能力按 BLOCK_PENDING_POLICY 阻断（Requirement 4.7）",
            ))
        elif decision is FeatureDecision.PREFLIGHT_ONLY:
            findings.append(Finding(
                code=f"PACKAGE.feature_{key}",
                severity=Severity.WARNING,
                locator=locator,
                policy_decision=f"{key}={decision.value}（FINALIZE_BLOCKED）",
                remediation="v1 只允许 quarantine + 只读 preflight，不得改扩展名或丢宏后发布",
            ))

    if not payload:
        findings.append(Finding(
            code=FINDING_CORRUPT,
            severity=Severity.BLOCKER,
            locator="package",
            policy_decision="空字节不可扫描",
            remediation="重新上传完整 .xlsx/.xlsm",
        ))
        return _finish(
            findings, observed_features, preservation, xml_stats,
            container_kind, entry_count, expanded_bytes, relationships,
            ResourceObservation(), policy,
        )

    if filename_hint and filename_hint.casefold().endswith(".xlsm"):
        container_kind = "xlsm"
        _add_feature("container.xlsm", "filename_hint")
    elif filename_hint and filename_hint.casefold().endswith(".xlsx"):
        container_kind = "xlsx"
        _add_feature("container.xlsx", "filename_hint")

    try:
        zf = ZipFile(io.BytesIO(payload), "r")
    except BadZipFile as exc:
        findings.append(Finding(
            code=FINDING_CORRUPT,
            severity=Severity.BLOCKER,
            locator="package",
            policy_decision=f"损坏的 ZIP: {type(exc).__name__}",
            remediation="文件不是完整 OOXML 包",
        ))
        return _finish(
            findings, observed_features, preservation, xml_stats,
            container_kind, 0, 0, 0, ResourceObservation(), policy,
        )

    with zf:
        infos = list(zf.infolist())
        entry_count = len(infos)
        if entry_count > policy.max_zip_entries:
            findings.append(Finding(
                code="POLICY.zip_entries_exceeded",
                severity=Severity.BLOCKER,
                locator="zip.entries",
                policy_decision=f"entries={entry_count} > {policy.max_zip_entries}",
                remediation="减少 ZIP 条目后重试",
                observed=entry_count,
                limit=policy.max_zip_entries,
            ))
            # 超条目仍继续做路径闸，但不读 XML 内容（防 zip bomb）。
            _scan_entry_paths(infos, findings, skip_xml=True)
            observation = ResourceObservation(
                zip_entries=entry_count,
                expanded_bytes=0,
            )
            return _finish(
                findings, observed_features, preservation, xml_stats,
                container_kind, entry_count, 0, 0, observation, policy,
            )

        canonical: list[CanonicalZipPath] = []
        encrypted = False
        for info in infos:
            if _timed_out():
                findings.append(_timeout_finding(policy))
                break
            if info.flag_bits & _ZIP_ENCRYPTED_FLAG:
                encrypted = True
            if is_symlink_external_attr(info.external_attr):
                findings.append(Finding(
                    code=PathRejectionCode.SYMLINK.value,
                    severity=Severity.BLOCKER,
                    locator=info.filename,
                    policy_decision="ZIP entry 为 symlink/reparse",
                    remediation="删除符号链接条目后重试",
                ))
                continue
            inspected = inspect_zip_entry_name(info.filename)
            if isinstance(inspected, PathRejection):
                findings.append(Finding(
                    code=inspected.code.value,
                    severity=Severity.BLOCKER,
                    locator=inspected.original,
                    policy_decision=inspected.detail,
                    remediation="使用相对、无穿越、无 ADS 的 OOXML 路径",
                ))
                continue
            canonical.append(inspected)
            uncompressed = max(int(info.file_size), 0)
            compressed = max(int(info.compress_size), 0)
            expanded_bytes += uncompressed
            if compressed > 0:
                ratio = uncompressed / compressed
                if ratio > max_entry_ratio:
                    max_entry_ratio = ratio
                if ratio > policy.max_entry_compression_ratio:
                    findings.append(Finding(
                        code="POLICY.entry_compression_ratio_exceeded",
                        severity=Severity.BLOCKER,
                        locator=inspected.posix,
                        policy_decision=f"entry ratio={ratio:.1f} > {policy.max_entry_compression_ratio}",
                        remediation="拒绝 zip bomb",
                        observed=ratio,
                        limit=policy.max_entry_compression_ratio,
                    ))

        for left, right in find_casefold_collisions(canonical):
            findings.append(Finding(
                code=PathRejectionCode.COLLISION.value,
                severity=Severity.BLOCKER,
                locator=right.original,
                policy_decision=f"与 {left.original!r} casefold 碰撞",
                remediation="ZIP 条目名规范化后必须唯一",
            ))

        if encrypted:
            findings.append(Finding(
                code=FINDING_ENCRYPTED,
                severity=Severity.BLOCKER,
                locator="package",
                policy_decision="ZIP 加密位被设置",
                remediation="移除密码/加密后重试；加密包不得进入预览",
            ))

        if expanded_bytes > policy.max_expanded_bytes:
            findings.append(Finding(
                code="POLICY.expanded_bytes_exceeded",
                severity=Severity.BLOCKER,
                locator="zip.expanded",
                policy_decision=f"expanded={expanded_bytes} > {policy.max_expanded_bytes}",
                remediation="缩小工作簿",
                observed=expanded_bytes,
                limit=policy.max_expanded_bytes,
            ))

        total_compressed = max(len(payload), 1)
        total_ratio = expanded_bytes / total_compressed
        if total_ratio > policy.max_total_compression_ratio:
            findings.append(Finding(
                code="POLICY.total_compression_ratio_exceeded",
                severity=Severity.BLOCKER,
                locator="zip.total_ratio",
                policy_decision=f"total ratio={total_ratio:.1f} > {policy.max_total_compression_ratio}",
                remediation="拒绝 zip bomb",
                observed=total_ratio,
                limit=policy.max_total_compression_ratio,
            ))

        path_blockers = any(
            f.severity is Severity.BLOCKER and f.code.startswith("PACKAGE.path_")
            for f in findings
        )
        budget_or_crypto_blockers = any(
            f.code in {FINDING_ENCRYPTED, FINDING_PASSWORD, FINDING_CORRUPT, FINDING_TIMEOUT}
            or (f.code.endswith("_exceeded") and f.severity is Severity.BLOCKER)
            for f in findings
        )

        # Requirement 5.1：package blocker 不得进入可执行预览。加密/路径穿越/
        # zip bomb 预算超限时不读 XML 内容。
        can_read_xml = (
            not encrypted
            and not path_blockers
            and not budget_or_crypto_blockers
        )

        if can_read_xml:
            for info in infos:
                if _timed_out():
                    findings.append(_timeout_finding(policy))
                    break
                inspected = inspect_zip_entry_name(info.filename)
                if isinstance(inspected, PathRejection):
                    continue
                posix = inspected.posix
                _detect_path_features(posix, _add_feature)
                if posix.casefold() == "[content_types].xml":
                    raw, err = _read_entry(zf, info, policy)
                    if isinstance(err, Finding):
                        findings.append(err)
                        continue
                    assert raw is not None
                    stats_or_rej, extra_rels = _scan_content_types(
                        raw, posix, policy, _add_feature,
                    )
                    if isinstance(stats_or_rej, XmlScanRejection):
                        findings.append(_xml_finding(stats_or_rej))
                    else:
                        xml_stats.append(stats_or_rej)
                        max_xml_bytes = max(max_xml_bytes, stats_or_rej.bytes_read)
                        max_xml_depth = max(max_xml_depth, stats_or_rej.depth)
                        max_xml_nodes = max(max_xml_nodes, stats_or_rej.nodes)
                    continue
                if posix.endswith(".rels") or posix.endswith(".xml"):
                    raw, err = _read_entry(zf, info, policy)
                    if isinstance(err, Finding):
                        findings.append(err)
                        continue
                    assert raw is not None
                    rel_count_holder = {"n": 0}

                    def _hook(name: str, attrs: dict[str, str], posix: str = posix) -> None:
                        nonlocal relationships
                        local = name.rsplit("}", 1)[-1]
                        if local == "Relationship":
                            rel_count_holder["n"] += 1
                            relationships += 1
                            target_mode = attrs.get("TargetMode") or attrs.get("targetMode") or ""
                            rel_type = attrs.get("Type") or attrs.get("type") or ""
                            if target_mode.casefold() == "external":
                                _add_feature("external_relationship", posix)
                            mapped = _RELATIONSHIP_TYPE_FEATURES.get(rel_type)
                            if mapped:
                                _add_feature(mapped, posix)
                            elif rel_type and rel_type not in _BENIGN_RELATIONSHIP_TYPES:
                                _add_feature(f"relationship:{rel_type}", posix)
                        if local.lower() in {"ddelink", "dde", "oleobject"}:
                            feature = {
                                "ddelink": "dde_link",
                                "dde": "dde_link",
                                "oleobject": "ole_embedded_object",
                            }[local.lower()]
                            _add_feature(feature, posix)

                    result = scan_xml_bytes(
                        raw, locator=posix, policy=policy, start_element_hook=_hook,
                    )
                    if isinstance(result, XmlScanRejection):
                        findings.append(_xml_finding(result))
                    else:
                        xml_stats.append(result)
                        max_xml_bytes = max(max_xml_bytes, result.bytes_read)
                        max_xml_depth = max(max_xml_depth, result.depth)
                        max_xml_nodes = max(max_xml_nodes, result.nodes)

        if relationships > policy.max_relationships:
            findings.append(Finding(
                code="POLICY.relationships_exceeded",
                severity=Severity.BLOCKER,
                locator="relationships",
                policy_decision=f"relationships={relationships} > {policy.max_relationships}",
                remediation="减少关系数",
                observed=relationships,
                limit=policy.max_relationships,
            ))

        if "container.xlsm" in observed_features:
            container_kind = "xlsm"
        elif "container.xlsx" in observed_features:
            container_kind = container_kind or "xlsx"

        has_content_types = any(
            p.posix.casefold() == "[content_types].xml" for p in canonical
        )
        has_workbook = any(
            p.posix.casefold() == "xl/workbook.xml" for p in canonical
        )
        if can_read_xml and not has_content_types:
            findings.append(Finding(
                code=FINDING_CORRUPT,
                severity=Severity.BLOCKER,
                locator="[Content_Types].xml",
                policy_decision="缺少 [Content_Types].xml",
                remediation="不是完整 OOXML 包",
            ))
        if can_read_xml and not has_workbook:
            findings.append(Finding(
                code=FINDING_CORRUPT,
                severity=Severity.BLOCKER,
                locator="xl/workbook.xml",
                policy_decision="缺少 xl/workbook.xml",
                remediation="不是完整工作簿",
            ))

        # 含宏的 .xlsx（ContentType 声明 sheet.main 却带 vbaProject）仍按 VBA BLOCK。
        observation = ResourceObservation(
            zip_entries=entry_count,
            expanded_bytes=expanded_bytes,
            entry_compression_ratio=max_entry_ratio if max_entry_ratio else None,
            total_compression_ratio=total_ratio,
            xml_bytes=max_xml_bytes or None,
            xml_depth=max_xml_depth or None,
            xml_nodes=max_xml_nodes or None,
            relationships=relationships or None,
            wall_seconds=(clock or MonotonicClock()).monotonic() - started,
        )
        # 预算闸与包闸合并：validate_against_policy 对上报项再判一次，避免
        # scanner 漏掉某一项阈值。
        budget = validate_against_policy(observation, policy)
        findings.extend(budget.findings)

    return _finish(
        findings, observed_features, preservation, xml_stats,
        container_kind, entry_count, expanded_bytes, relationships,
        observation if "observation" in locals() else ResourceObservation(
            zip_entries=entry_count, expanded_bytes=expanded_bytes,
        ),
        policy,
    )


def _scan_entry_paths(infos: list[ZipInfo], findings: list[Finding], *, skip_xml: bool) -> None:
    del skip_xml
    for info in infos:
        inspected = inspect_zip_entry_name(info.filename)
        if isinstance(inspected, PathRejection):
            findings.append(Finding(
                code=inspected.code.value,
                severity=Severity.BLOCKER,
                locator=inspected.original,
                policy_decision=inspected.detail,
                remediation="使用相对、无穿越的 OOXML 路径",
            ))


def _detect_path_features(posix: str, add_feature: Callable[[str, str], None]) -> None:
    folded = posix.casefold()
    for prefix, feature in _PATH_FEATURE_PREFIXES:
        if folded == prefix.casefold() or folded.startswith(prefix.casefold()):
            add_feature(feature, posix)


def _read_entry(
    zf: ZipFile,
    info: ZipInfo,
    policy: CustomTemplateIngestionPolicy,
) -> tuple[bytes | None, Finding | None]:
    if info.file_size > policy.max_xml_bytes:
        return None, Finding(
            code="POLICY.xml_bytes_exceeded",
            severity=Severity.BLOCKER,
            locator=info.filename,
            policy_decision=f"entry {info.file_size} > max_xml_bytes={policy.max_xml_bytes}",
            remediation="缩小该 XML part",
            observed=info.file_size,
            limit=policy.max_xml_bytes,
        )
    try:
        with zf.open(info, "r") as handle:
            data = handle.read(policy.max_xml_bytes + 1)
    except RuntimeError as exc:
        # zipfile 对加密条目抛 RuntimeError("File <name> is encrypted")
        msg = str(exc).casefold()
        if "password" in msg or "encrypt" in msg:
            return None, Finding(
                code=FINDING_PASSWORD,
                severity=Severity.BLOCKER,
                locator=info.filename,
                policy_decision="条目需要密码",
                remediation="移除密码保护",
            )
        return None, Finding(
            code=FINDING_CORRUPT,
            severity=Severity.BLOCKER,
            locator=info.filename,
            policy_decision=f"读取失败: {type(exc).__name__}",
            remediation="重新打包",
        )
    except (BadZipFile, zipfile.BadZipFile, OSError) as exc:
        return None, Finding(
            code=FINDING_CORRUPT,
            severity=Severity.BLOCKER,
            locator=info.filename,
            policy_decision=f"读取失败: {type(exc).__name__}",
            remediation="重新打包",
        )
    if len(data) > policy.max_xml_bytes:
        return None, Finding(
            code="POLICY.xml_bytes_exceeded",
            severity=Severity.BLOCKER,
            locator=info.filename,
            policy_decision="XML 超出政策字节上限",
            remediation="缩小该 XML part",
            observed=len(data),
            limit=policy.max_xml_bytes,
        )
    return data, None


def _scan_content_types(
    payload: bytes,
    locator: str,
    policy: CustomTemplateIngestionPolicy,
    add_feature: Callable[[str, str], None],
) -> tuple[XmlScanStats | XmlScanRejection, int]:
    def hook(name: str, attrs: dict[str, str]) -> None:
        local = name.rsplit("}", 1)[-1]
        content_type = attrs.get("ContentType") or attrs.get("contentType") or ""
        if not content_type:
            return
        mapped = _CONTENT_TYPE_FEATURES.get(content_type)
        if mapped:
            add_feature(mapped, locator)
            return
        if content_type in _BENIGN_CONTENT_TYPES:
            return
        if local in {"Default", "Override"}:
            add_feature(f"contenttype:{content_type}", locator)

    result = scan_xml_bytes(payload, locator=locator, policy=policy, start_element_hook=hook)
    return result, 0


def _xml_finding(rejection: XmlScanRejection) -> Finding:
    severity = Severity.BLOCKER
    return Finding(
        code=rejection.code.value,
        severity=severity,
        locator=rejection.locator,
        policy_decision=rejection.detail,
        remediation="移除 DTD/实体、降低 XML 复杂度或修复损坏包",
        observed=rejection.stats.nodes,
    )


def _timeout_finding(policy: CustomTemplateIngestionPolicy) -> Finding:
    return Finding(
        code=FINDING_TIMEOUT,
        severity=Severity.BLOCKER,
        locator="wall_seconds",
        policy_decision=f"扫描超过 max_wall_seconds={policy.max_wall_seconds}",
        remediation="缩小工作簿后重试",
        limit=policy.max_wall_seconds,
    )


def _finish(
    findings: list[Finding],
    observed_features: Iterable[str],
    preservation: list[str],
    xml_stats: list[XmlScanStats],
    container_kind: str | None,
    entry_count: int,
    expanded_bytes: int,
    relationships: int,
    observation: ResourceObservation,
    policy: CustomTemplateIngestionPolicy,
) -> PackageScanResult:
    features = tuple(sorted(set(observed_features)))
    if not findings:
        # Requirement 3.6 / 5.7：空报告永不 valid。这里补一条 BLOCKER 而不是
        # 静默 PASS —— 扫描器若什么都没观测到，就是失败态。
        findings.append(Finding(
            code="POLICY.empty_report",
            severity=Severity.BLOCKER,
            locator="package",
            policy_decision="package scanner 未产生任何 finding",
            remediation="禁止返回空报告",
        ))
    elif not any(f.severity is Severity.BLOCKER for f in findings):
        findings.append(Finding(
            code=FINDING_SCAN_COMPLETE,
            severity=Severity.INFO,
            locator="package",
            policy_decision="package security scan 完成且无 BLOCKER",
            remediation="无需处理",
        ))

    # finalize：容器或任一 BLOCK 能力都会阻断。xlsm 的 PREFLIGHT_ONLY 也阻断。
    container_decision = decide_feature(
        f"container.{container_kind}" if container_kind else "",
    )
    blocked = any(f.severity is Severity.BLOCKER for f in findings)
    finalize_blocked = blocked or not finalize_allowed(container_decision)

    result = PreflightResult(
        verdict=derive_verdict(tuple(findings)),
        findings=tuple(findings),
        preservation_inventory=tuple(preservation),
        policy_version=policy.version,
    )
    return PackageScanResult(
        preflight=result,
        container_kind=container_kind,
        observed_features=features,
        entry_count=entry_count,
        expanded_bytes=expanded_bytes,
        relationships=relationships,
        observation=observation,
        finalize_blocked=finalize_blocked,
        xml_stats=tuple(xml_stats),
    )
