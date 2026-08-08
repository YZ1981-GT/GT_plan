"""抽样记录完整性判据 — 纯函数（sampling-evaluation-and-governance-closure R7）

## 改造前 QC-12 为什么是死规则（2026-08-05 实证 F14）

`SamplingCompletenessRule` 原判据是「项目级有 `SamplingConfig` 则必须有 `SamplingRecord`」，
双重失效：

1. 真实库 `sampling_config` **0 行**，且该表已由 `sampling-compliance-closure` Task 15 标为
   软弃用（抽样参数的权威留痕在 `workpaper_extraction_log.extraction_criteria`）
   → 遍历体永不执行；
2. 即便有 config，新写入的 `SamplingRecord.sampling_config_id` 恒为 NULL
   （`build_record_fields` 不含该字段，真实库 `sr_with_config`=0）→ 关联条件也匹配不上。

结果是「抽样记录完整」这条 QC 规则在投影表真正开始有数据之后反而彻底失效。

## 新判据

按 CAS 1314 的记录要求，问「有抽凭批次却缺记录项」：

- 缺评价（`extraction_criteria.evaluation` 不存在或无实质内容）
- 结论未经人工确认（`evaluation.conclusion_confirmed` 为假）
- 抽样框已变更（`dataset_stale`）→ 同种子不可复算，需复核

**无批次 → 零 finding**：那是「不适用」而非「不合规」。这条边界很重要，
否则平台上所有不需要抽样的底稿都会挂一条质量缺口。

本模块**不连库**（入参是视图对象），既便于单测也便于 QC 与归档两处复用同一判据。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SamplingBatchView:
    """一个抽凭批次的判定所需视图（由调用方从 `workpaper_extraction_log` 装配）。"""

    batch_id: str | None
    #: 批次留痕（`extraction_criteria`）
    criteria: dict[str, Any] = field(default_factory=dict)
    #: 抽样框是否已变更（同种子不可复算）
    dataset_stale: bool = False
    #: 底稿编码，供 finding 文案定位
    wp_code: str | None = None

    @property
    def evaluation(self) -> dict[str, Any]:
        ev = self.criteria.get("evaluation")
        return ev if isinstance(ev, dict) else {}


#: 判定「评价有实质内容」所需的键 —— 只要任一项有值即认为审计师做过评价。
#: 不要求全部齐备：MUS 与经典法产出的字段不同，强制全齐会对经典法误报。
_SUBSTANTIVE_EVAL_KEYS = (
    "projected",
    "upper_limit",
    "conclusion_message",
    "conclusion_code",
    "deviation_count",
)

#: 视为「未评价」的空值。注意 `"0.00"` **不算空** —— 推断错报为 0 是有效评价结论
#: （查了没发现错报），把它当未评价会对所有干净的抽样误报。
_EMPTY_VALUES = (None, "", "undetermined")


def has_substantive_evaluation(evaluation: dict[str, Any]) -> bool:
    """评价是否有实质内容。

    `conclusion_code == "undetermined"` 视为未评价（那是归一化的默认值，不是审计师结论）；
    金额字段的 `"0.00"` 视为有效评价。
    """
    if not evaluation:
        return False
    for key in _SUBSTANTIVE_EVAL_KEYS:
        val = evaluation.get(key)
        if key == "deviation_count":
            # 计数型：0 是有效值，但「键不存在」才算缺失
            if key in evaluation and val is not None:
                return True
            continue
        if val not in _EMPTY_VALUES:
            return True
    return False


def evaluate_sampling_completeness(batches: list[SamplingBatchView]) -> list[str]:
    """返回抽样记录完整性缺口消息（空列表 = 通过或不适用）。

    每条消息含**缺失项类别 + 批次标识**，便于复核人直接定位（R7.8）。
    """
    if not batches:
        # 不适用 ≠ 不合规
        return []

    findings: list[str] = []
    for b in batches:
        tag = _batch_tag(b)
        ev = b.evaluation

        if not has_substantive_evaluation(ev):
            findings.append(
                f"{tag}已执行抽凭但缺少抽样评价："
                "按 CAS 1314 应记录偏差笔数、推断错报、错报上限与总体结论"
            )
            # 缺评价时不再叠加「结论未确认」——那是同一个缺口的下游表现，两条会让复核人
            # 以为有两个问题
            continue

        if not ev.get("conclusion_confirmed"):
            findings.append(
                f"{tag}抽样结论尚未经人工确认："
                "系统计算的结论建议须由审计师确认后方可作为最终结论"
            )

        if b.dataset_stale:
            findings.append(
                f"{tag}抽样框（序时账数据集）已变更："
                "同一随机种子不再能复现当时样本，请复核抽样结果是否仍然适用"
            )

    return findings


def _batch_tag(b: SamplingBatchView) -> str:
    """批次定位前缀。batch_id 缺失时如实说明而不是留空。"""
    parts = []
    if b.wp_code:
        parts.append(f"底稿 {b.wp_code}")
    if b.batch_id:
        parts.append(f"批次 {str(b.batch_id)[:8]}")
    else:
        parts.append("批次标识缺失")
    return "（" + "，".join(parts) + "）"
