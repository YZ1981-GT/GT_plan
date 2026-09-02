# -*- coding: utf-8 -*-
"""OOXML 安全与容量校验门：ZIP/行/field 预算、外部关系、宏、嵌入对象与文档类型。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 11
Requirements: 5.6, 5.12, 9.6, 10.8, 14.11
Properties: P17 / P42 / P60

═══ 为什么这一层必须流式且必须在 durable 之前 ═══

Requirement 5.6：「下载文件 SHALL 先进入隔离 staged path，流式校验压缩大小、MIME/ZIP
magic、OOXML 类型、entry/展开量、外部关系、宏策略和恶意路径。全部校验通过后才可登记
`kind=incoming,state=durable`」。因此本模块的每个门都：

* 只接受**已落盘的 staged 路径**（不接受 bytes），杜绝「先整包读进内存再判大小」；
* 展开量按块累计，越界立即 `raise`，绝不先解完再看总数（那就是 zip bomb 的胜利条件）；
* 失败一律抛带 `error_code` 的异常。**禁止返回 bool** —— 返回值会被
  `if not ok: pass` 吞掉，而 Requirement 5.12 明令不得把解析异常降为成功。

═══ 校验顺序是语义的一部分，不是实现细节 ═══

`magic → entry 名安全 → entry 数 → 压缩体积 → 流式展开量/压缩比 → required parts →
文档类型 → 外部关系 → 宏 → 嵌入对象`

顺序固定的理由：**每一步都必须在比它更昂贵的下一步之前完成**。若把「entry 数」放到
「流式展开」之后，20000+ entry 的炸弹会先被完整展开一遍才被拒。守卫用
:attr:`OoxmlReport.gates` 的**实际顺序**断言，而不是断言「某个 gate 存在」。

═══ 不用 openpyxl / python-docx ═══

它们会把整个文档树读进内存，正是 Requirement 10.8「不得直接交给解析器无限展开」禁止的
形态。本模块只用 `zipfile` 的流式接口 + 有界正则，`roundtrip_equivalence` 等语义等值
校验属于 adapter（Task 13+）职责，不在安全门内。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.services.workpaper_sync.limits import SyncLimits, load_limits
from app.services.workpaper_sync.models import SyncDomainError

#: `TargetMode="External"` 的有界匹配。刻意不解析 XML —— 恶意 XML 本身可以是 billion
#: laughs；这里只做字节级扫描，且每个 .rels 部件的展开量已被 expanded 预算覆盖。
_TARGET_MODE_RE = re.compile(rb'TargetMode\s*=\s*"([^"]{0,64})"', re.IGNORECASE)

#: 绝对路径 entry 名（`/x`、`C:\x`、`\\server\share`）。
_ABSOLUTE_ENTRY_RE = re.compile(r"^(?:[/\\]|[A-Za-z]:)")


class OoxmlSecurityError(SyncDomainError):
    """OOXML 安全策略拒绝（宏/外部关系/嵌入对象/恶意 entry 名/类型不符）。"""

    error_code = "ooxml_security_rejected"

    def __init__(self, *, gate: str, detail: str) -> None:
        self.gate = gate
        self.detail = detail
        super().__init__(f"OOXML 安全门 {gate} 拒绝：{detail}")


class OoxmlStructureError(SyncDomainError):
    """不是可打开的 ZIP、缺必需部件，或声明类型与内部部件不符。"""

    error_code = "ooxml_structure_invalid"

    def __init__(self, *, gate: str, detail: str) -> None:
        self.gate = gate
        self.detail = detail
        super().__init__(f"OOXML 结构门 {gate} 拒绝：{detail}")


@dataclass
class OoxmlReport:
    """一次校验的可审计观测量（进 operation error detail / evidence trace）。"""

    path: str
    declared_document_type: str
    detected_document_type: str | None = None
    archive_bytes: int = 0
    entry_count: int = 0
    expanded_bytes: int = 0
    max_entry_ratio: float = 0.0
    overall_ratio: float = 0.0
    gates: list[str] = field(default_factory=list)
    external_relationship_parts: list[str] = field(default_factory=list)
    macro_parts: list[str] = field(default_factory=list)
    embedded_object_parts: list[str] = field(default_factory=list)
    policy_version: str = ""

    def _passed(self, gate: str) -> None:
        self.gates.append(gate)


#: 门顺序真源。守卫断言 :attr:`OoxmlReport.gates` 是本序列的前缀。
GATE_ORDER: tuple[str, ...] = (
    "zip_magic",
    "entry_names",
    "zip_entries",
    "compressed_size",
    "expanded_size",
    "required_parts",
    "document_type",
    "external_relationships",
    "macros",
    "embedded_objects",
)


def validate_ooxml_artifact(
    path: Path,
    *,
    document_type: str,
    limits: SyncLimits | None = None,
) -> OoxmlReport:
    """按固定顺序跑完全部安全/容量门；任一门失败即抛异常（fail visible）。

    :param document_type: 声明类型（`xlsx` / `docx`）。必须与 ZIP 内部件一致 ——
        Task 7 fs7 实测「xlsx 字节改名 `.docx`」可被内部部件识破，扩展名不作类型依据。
    """
    lim = limits or load_limits()
    policy = lim.ooxml
    report = OoxmlReport(
        path=str(path), declared_document_type=document_type,
        policy_version=policy.policy_version,
    )

    if document_type not in policy.document_type_markers:
        raise OoxmlStructureError(
            gate="document_type",
            detail=f"未登记的声明类型 {document_type!r}（登记: "
                   f"{sorted(policy.document_type_markers)}）",
        )

    # ── 1. magic bytes（扩展名不作类型依据；Task 7 fs7）─────────────────
    try:
        report.archive_bytes = path.stat().st_size
        with path.open("rb") as fh:
            head = fh.read(len(policy.zip_magic))
    except OSError as exc:
        raise OoxmlStructureError(gate="zip_magic", detail=f"无法读取 staged 文件: {exc}") from exc
    if head != policy.zip_magic:
        raise OoxmlStructureError(
            gate="zip_magic",
            detail=f"ZIP magic 不符：期望 {policy.zip_magic.hex()} 实得 {head.hex()}",
        )
    report._passed("zip_magic")

    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise OoxmlStructureError(gate="zip_magic", detail=f"BadZipFile: {exc}") from exc

    with zf:
        infos = zf.infolist()

        # ── 2. entry 名安全（`..`、绝对路径、盘符、反斜杠；Requirement 5.6 恶意路径）──
        for info in infos:
            name = info.filename
            if policy.reject_absolute_entry_names and _ABSOLUTE_ENTRY_RE.match(name):
                raise OoxmlSecurityError(
                    gate="entry_names", detail=f"绝对路径 entry 名: {name!r}"
                )
            for bad in policy.forbidden_entry_name_patterns:
                if bad and bad in name:
                    raise OoxmlSecurityError(
                        gate="entry_names",
                        detail=f"entry 名含禁止片段 {bad!r}: {name!r}",
                    )
        report._passed("entry_names")

        # ── 3. entry 数（在任何展开之前）───────────────────────────────
        report.entry_count = len(infos)
        lim.assert_zip_entries(report.entry_count)
        report._passed("zip_entries")

        # ── 4. 压缩体积（在任何展开之前）───────────────────────────────
        lim.assert_compressed_size(report.archive_bytes)
        report._passed("compressed_size")

        # ── 5. 流式展开量 + 逐 entry 压缩比（越界立即中止）───────────────
        total_expanded = 0
        for info in infos:
            if info.is_dir():
                continue
            entry_expanded = 0
            with zf.open(info, "r") as src:
                while True:
                    chunk = src.read(lim.chunk_bytes)
                    if not chunk:
                        break
                    entry_expanded += len(chunk)
                    total_expanded += len(chunk)
                    # 🔴 在循环内判定 —— 放到循环外就是「先解完再看总数」，
                    # zip bomb 已经赢了。
                    lim.assert_expanded_size(total_expanded)
            if info.compress_size > 0:
                ratio = entry_expanded / info.compress_size
                report.max_entry_ratio = max(report.max_entry_ratio, ratio)
                lim.assert_compression_ratio(
                    compressed=info.compress_size, expanded=entry_expanded
                )
        report.expanded_bytes = total_expanded
        if report.archive_bytes > 0:
            report.overall_ratio = total_expanded / report.archive_bytes
            lim.assert_compression_ratio(
                compressed=report.archive_bytes, expanded=total_expanded
            )
        report._passed("expanded_size")

        names = [i.filename for i in infos]
        lowered = {n.lower(): n for n in names}

        # ── 6. 必需部件 ────────────────────────────────────────────────
        missing = [p for p in policy.required_parts if p not in names]
        if missing:
            raise OoxmlStructureError(
                gate="required_parts", detail=f"缺必需部件: {missing}"
            )
        report._passed("required_parts")

        # ── 7. 文档类型由内部部件决定 ───────────────────────────────────
        detected: str | None = None
        for doc_type, marker in policy.document_type_markers.items():
            if marker.lower() in lowered:
                detected = doc_type
                break
        report.detected_document_type = detected
        if detected is None:
            raise OoxmlStructureError(
                gate="document_type",
                detail="ZIP 内不含任何登记的类型标记部件"
                       f"（期望其一: {sorted(policy.document_type_markers.values())}）",
            )
        if detected != document_type:
            raise OoxmlStructureError(
                gate="document_type",
                detail=f"扩展名伪装：声明 {document_type} 但内部部件表明 {detected}",
            )
        report._passed("document_type")

        # ── 8. 外部关系 ────────────────────────────────────────────────
        mode = policy.external_relationship_target_mode.encode("utf-8").lower()
        for info in infos:
            if not info.filename.lower().endswith(".rels"):
                continue
            with zf.open(info, "r") as src:
                blob = src.read(lim.chunk_bytes * 4)
            for found in _TARGET_MODE_RE.findall(blob):
                if found.lower() == mode:
                    report.external_relationship_parts.append(info.filename)
                    break
        if report.external_relationship_parts and not policy.allow_external_relationships:
            raise OoxmlSecurityError(
                gate="external_relationships",
                detail=f"外部关系被策略拒绝: {report.external_relationship_parts}",
            )
        report._passed("external_relationships")

        # ── 9. 宏（部件名 + [Content_Types].xml 声明双判据）──────────────
        for low, original in lowered.items():
            if any(marker in low for marker in policy.macro_part_markers):
                report.macro_parts.append(original)
        ct_name = policy.required_parts[0]
        if ct_name in names:
            with zf.open(ct_name, "r") as src:
                ct_blob = src.read(lim.chunk_bytes * 4).lower()
            for declared in policy.macro_content_types:
                if declared.encode("utf-8") in ct_blob:
                    report.macro_parts.append(f"{ct_name}:{declared}")
        if report.macro_parts and not policy.allow_macros:
            raise OoxmlSecurityError(
                gate="macros", detail=f"宏被策略拒绝: {sorted(set(report.macro_parts))}"
            )
        report._passed("macros")

        # ── 10. 嵌入对象 ───────────────────────────────────────────────
        for low, original in lowered.items():
            if any(low.startswith(prefix) for prefix in policy.embedded_object_prefixes):
                report.embedded_object_parts.append(original)
        if report.embedded_object_parts and not policy.allow_embedded_objects:
            raise OoxmlSecurityError(
                gate="embedded_objects",
                detail=f"嵌入对象被策略拒绝: {sorted(set(report.embedded_object_parts))}",
            )
        report._passed("embedded_objects")

    return report


# ═══════════════════════════════════════════════════════════════════════════
# projection 预算（Requirement 14.11 的行/field 两项）
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ProjectionBudgetReport:
    """projection 结构规模观测量。"""

    field_count: int = 0
    max_table_rows: int = 0
    max_table_key: str = ""
    table_count: int = 0


def measure_projection(payload: object) -> ProjectionBudgetReport:
    """文档无关地统计 projection 的 field 数与最大表行数。

    判据是**结构**而不是某个 adapter schema（adapter contract 由 Task 13 才发布）：

    * ``field`` = 任一叶子标量（str/int/float/bool/None）；
    * ``row``   = 「元素是 mapping 的 list」的长度 —— 无论它挂在
      ``tables[x].rows`` 还是 ``sub_table_data[key]`` 下都成立。

    这样 Task 13/14 引入正式 Projection 类型后无需改这里，也不会因为换了嵌套层级
    而让预算门静默失效。
    """
    report = ProjectionBudgetReport()

    def walk(node: object, key: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
            return
        if isinstance(node, (list, tuple)):
            if node and all(isinstance(e, dict) for e in node):
                report.table_count += 1
                if len(node) > report.max_table_rows:
                    report.max_table_rows = len(node)
                    report.max_table_key = key
            for e in node:
                walk(e, key)
            return
        report.field_count += 1

    walk(payload, "<root>")
    return report


def assert_projection_budget(
    payload: object, *, limits: SyncLimits | None = None
) -> ProjectionBudgetReport:
    """行/field 预算门（Requirement 14.11 后两项）。超限抛 `BudgetExceededError`。"""
    lim = limits or load_limits()
    report = measure_projection(payload)
    lim.assert_table_rows(report.max_table_rows, table_key=report.max_table_key)
    lim.assert_projection_fields(report.field_count)
    return report


__all__ = [
    "GATE_ORDER",
    "OoxmlReport",
    "OoxmlSecurityError",
    "OoxmlStructureError",
    "ProjectionBudgetReport",
    "assert_projection_budget",
    "measure_projection",
    "validate_ooxml_artifact",
]
