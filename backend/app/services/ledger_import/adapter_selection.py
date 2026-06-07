"""Adapter 自动选优服务 — 两阶段识别与 evidence 写入。

见 design.md §1 / requirements 需求 2。

核心流程：
1. provisional identify — 用 generic/global aliases 生成初步 column_mappings
2. detect_best — 在有 provisional mappings 的 fd 上选取最佳 Adapter
3. final identify — 用选中 adapter aliases + generic aliases 重新识别
4. evidence 写入 — adapter_id / adapter_score / 匹配证据写入 detection_evidence

adapter_hint 存在时跳过自动选优，直接使用指定 Adapter。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .adapters import AdapterRegistry, registry as default_registry
from .adapters.base import BaseAdapter
from .adapters.generic import GenericAdapter
from .detection_types import FileDetection, SheetDetection, TableType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ADAPTER_AUTO_PASS_THRESHOLD = 0.6
"""Adapter 分数 >= 此值时自动通过，低于时进入人工确认。"""


# ---------------------------------------------------------------------------
# 结果数据类
# ---------------------------------------------------------------------------


@dataclass
class AdapterSelectionResult:
    """Adapter 选优结果。"""

    adapter_id: str
    adapter_score: float
    evidence: dict = field(default_factory=dict)
    is_auto_pass: bool = False
    requires_human_confirm: bool = False
    source: str = "auto_detect"  # "auto_detect" | "user_hint"


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def select_adapter(
    fd: FileDetection,
    *,
    adapter_hint: Optional[str] = None,
    registry: Optional[AdapterRegistry] = None,
) -> AdapterSelectionResult:
    """两阶段 Adapter 选优。

    Args:
        fd: 已经完成 provisional identify 的 FileDetection（sheets 有 column_mappings）。
        adapter_hint: 用户显式指定的 adapter id，存在时跳过自动选优。
        registry: 注册表实例，默认使用模块单例。

    Returns:
        AdapterSelectionResult 包含选中 adapter 信息与 evidence。
    """
    reg = registry or default_registry

    # ---- adapter_hint 覆盖自动选优 (Task 2.2) ----
    if adapter_hint:
        adapter = reg.get(adapter_hint)
        if adapter is not None:
            score = adapter.match(fd)
            evidence = _build_evidence(adapter, fd, score)
            return AdapterSelectionResult(
                adapter_id=adapter.id,
                adapter_score=score,
                evidence=evidence,
                is_auto_pass=True,  # hint 总是 auto pass
                requires_human_confirm=False,
                source="user_hint",
            )
        else:
            logger.warning(
                "adapter_hint=%r not found in registry, falling back to auto detect",
                adapter_hint,
            )

    # ---- 自动选优 (Task 2.3) ----
    best_adapter, best_score = reg.detect_best(fd)
    evidence = _build_evidence(best_adapter, fd, best_score)

    # ---- 判定是否自动通过 (Task 2.6) ----
    is_auto_pass = best_score >= ADAPTER_AUTO_PASS_THRESHOLD
    requires_human_confirm = False

    if not is_auto_pass:
        # 低分 adapter — 检查 table_type 置信度
        # 如果 table_type 高置信，保留表类型但列映射进入人工确认
        has_high_confidence_type = any(
            sheet.table_type_confidence >= 70
            and sheet.table_type != "unknown"
            for sheet in fd.sheets
        )
        if has_high_confidence_type:
            requires_human_confirm = True
            # 退回 generic 兜底
            generic = reg.get("generic") or GenericAdapter()
            evidence["fallback_to_generic"] = True
            evidence["original_adapter_id"] = best_adapter.id
            evidence["original_adapter_score"] = best_score
            best_adapter = generic
            best_score = generic.match(fd)

    return AdapterSelectionResult(
        adapter_id=best_adapter.id,
        adapter_score=best_score,
        evidence=evidence,
        is_auto_pass=is_auto_pass,
        requires_human_confirm=requires_human_confirm,
        source="auto_detect",
    )


def write_adapter_evidence(
    fd: FileDetection,
    result: AdapterSelectionResult,
) -> None:
    """将 adapter 选优结果写入 detection_evidence.adapter_match (Task 2.5)。

    写入 FileDetection 的每个 sheet 的 detection_evidence 中。
    """
    adapter_match = {
        "adapter_id": result.adapter_id,
        "adapter_score": result.adapter_score,
        "source": result.source,
        "is_auto_pass": result.is_auto_pass,
        "requires_human_confirm": result.requires_human_confirm,
        **result.evidence,
    }

    for sheet in fd.sheets:
        sheet.detection_evidence["adapter_match"] = adapter_match
        sheet.adapter_id = result.adapter_id


def merge_aliases(
    adapter: BaseAdapter,
    table_type: TableType,
    generic: Optional[BaseAdapter] = None,
) -> dict[str, list[str]]:
    """合并选中 adapter aliases + generic aliases (Task 2.4)。

    优先级：adapter aliases > generic aliases（同 field 不覆盖，合并 alias 列表）。
    """
    if generic is None:
        generic = GenericAdapter()

    # 基础 = generic aliases
    merged = generic.get_column_aliases(table_type)

    # 叠加 adapter aliases（adapter 优先，放在前面）
    if adapter.id != "generic":
        adapter_aliases = adapter.get_column_aliases(table_type)
        for field_name, aliases in adapter_aliases.items():
            if field_name in merged:
                # adapter 的 aliases 优先放前面，去重
                existing = set(merged[field_name])
                combined = list(aliases)  # adapter first
                for a in merged[field_name]:
                    if a not in existing:
                        combined.append(a)
                    else:
                        # already in combined from adapter
                        if a not in combined:
                            combined.append(a)
                merged[field_name] = combined
            else:
                merged[field_name] = list(aliases)

    return merged


# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _build_evidence(
    adapter: BaseAdapter,
    fd: FileDetection,
    score: float,
) -> dict:
    """构建 adapter 匹配证据。"""
    evidence: dict = {
        "matched_filename": False,
        "matched_signature_columns": [],
        "fallback_to_generic": False,
    }

    # 检查文件名匹配（对 JsonDrivenAdapter 检查 _filename_patterns）
    if hasattr(adapter, "_filename_patterns"):
        for pat in adapter._filename_patterns:
            if pat.search(fd.file_name or ""):
                evidence["matched_filename"] = True
                break

    # 检查签名列匹配
    if hasattr(adapter, "_signature_columns") and fd.sheets:
        matched_cols: list[str] = []
        for sheet in fd.sheets:
            sig_for_type = adapter._signature_columns.get(sheet.table_type)
            if not sig_for_type:
                continue
            headers = {
                (m.column_header or "").strip()
                for m in sheet.column_mappings
                if m.column_header
            }
            matched_cols.extend(headers & sig_for_type)
        evidence["matched_signature_columns"] = sorted(set(matched_cols))

    return evidence


__all__ = [
    "ADAPTER_AUTO_PASS_THRESHOLD",
    "AdapterSelectionResult",
    "merge_aliases",
    "select_adapter",
    "write_adapter_evidence",
]
