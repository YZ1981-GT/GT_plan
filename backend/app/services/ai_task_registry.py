"""平台 AI 任务与 Prompt 版本注册表。

任务代码是专业边界，不能由关键词猜测。Prompt 版本只追加，旧版本可按编号重放。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


class AiTaskRisk(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    prohibited = "prohibited"


class AiTrustZone(str, Enum):
    local_device = "local_device"
    firm_private = "firm_private"
    approved_provider = "approved_provider"
    restricted = "restricted"


@dataclass(frozen=True)
class PromptVersion:
    prompt_id: str
    version: str
    content: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AiTaskSpec:
    task_code: str
    risk_class: AiTaskRisk
    allowed_actions: FrozenSet[str]
    allowed_roles: FrozenSet[str]
    allowed_trust_zones: FrozenSet[AiTrustZone]
    mask_policy: str
    context_recipe: str
    prompt_id: str
    prompt_version: str
    output_schema: str
    verifier_id: str
    writeback_policy: str
    timeout_seconds: int
    max_output_tokens: int


_ALL_HUMAN_ROLES = frozenset({"admin", "partner", "manager", "auditor", "qc", "eqcr"})
_DRAFT_ROLES = frozenset({"admin", "partner", "manager", "auditor"})
_REVIEW_ROLES = frozenset({"admin", "partner", "manager", "qc", "eqcr"})
_LOCAL_OR_FIRM = frozenset({AiTrustZone.local_device, AiTrustZone.firm_private})
_APPROVED = frozenset({
    AiTrustZone.local_device,
    AiTrustZone.firm_private,
    AiTrustZone.approved_provider,
})


PROMPT_VERSIONS: dict[str, tuple[PromptVersion, ...]] = {
    "chat.audit_adviser": (
        PromptVersion(
            "chat.audit_adviser",
            "1.0.0",
            "你是审计辅助顾问。仅依据平台提供的资料回答；资料不足时明确说明。不得代替审计人员作最终专业判断。",
        ),
    ),
    "note.policy_draft": (
        PromptVersion(
            "note.policy_draft",
            "1.0.0",
            "你是审计附注编写助手。只依据参照资料生成供人工复核的会计政策措辞草稿；不得虚构企业采用的政策选择。",
        ),
    ),
    "note.change_analysis": (
        PromptVersion(
            "note.change_analysis",
            "1.0.0",
            "你是审计分析助手。只依据服务端权威事实描述变动；可能原因必须标为待核实假设，不得编造管理层解释或审计结论。",
        ),
    ),
    "note.rewrite": (
        PromptVersion(
            "note.rewrite",
            "1.0.0",
            "你是审计附注编写助手。保留原事实、数字和不确定性，只改写表达；只输出改写草稿。",
        ),
    ),
    "note.continue": (
        PromptVersion(
            "note.continue",
            "1.0.0",
            "你是审计附注编写助手。延续现有表述，只输出续写草稿；不得新增资料中不存在的数字和结论。",
        ),
    ),
    "note.completeness_review": (
        PromptVersion(
            "note.completeness_review",
            "1.0.0",
            "你是审计附注审核助手。只依据所给准则资料列出待人工核实的潜在披露缺口，不宣告完整性结论。",
        ),
    ),
    "review.workpaper": (
        PromptVersion(
            "review.workpaper",
            "1.0.0",
            "你是底稿复核辅助工具。系统检查是权威输入；你只能提出新增疑点，不得宣告底稿通过或决定签发。",
        ),
    ),
    "project.weekly_report": (
        PromptVersion(
            "project.weekly_report",
            "1.0.0",
            "根据服务端提供的项目进度事实润色周报。不得改变数字或自行补充项目事实。",
        ),
    ),
    "project.status_summary": (
        PromptVersion(
            "project.status_summary",
            "1.0.0",
            "根据服务端提供的指标生成项目状态摘要。风险结论须标明依据，不得替代合伙人判断。",
        ),
    ),
    "workpaper.subject_conclusion_advice": (
        PromptVersion(
            "workpaper.subject_conclusion_advice",
            "1.0.0",
            "输出科目结论措辞建议、判断因素、证据缺口和建议程序，供审计人员复核。不得生成最终审计意见。",
        ),
    ),
    "workpaper.analytical_review": (
        PromptVersion(
            "workpaper.analytical_review",
            "1.0.0",
            "只依据服务端余额和参照资料描述变动；原因必须标为待核实假设，不得虚构解释或下最终结论。",
        ),
    ),
    "workpaper.field_draft": (
        PromptVersion(
            "workpaper.field_draft",
            "1.0.0",
            "为指定底稿字段起草供人工复核的文字。只陈述输入事实；资料不足时列待补证据，不得宣告通过。",
        ),
    ),
}


def _task(
    code: str,
    *,
    risk: AiTaskRisk,
    roles: FrozenSet[str],
    zones: FrozenSet[AiTrustZone],
    prompt: str,
    output: str = "text_draft",
    verifier: str = "nonempty_draft",
    writeback: str = "pending_only",
    context: str = "host_and_authorized_knowledge",
    tokens: int = 1500,
) -> AiTaskSpec:
    versions = PROMPT_VERSIONS[prompt]
    return AiTaskSpec(
        task_code=code,
        risk_class=risk,
        allowed_actions=frozenset({"ask" if risk is AiTaskRisk.low else "draft"}),
        allowed_roles=roles,
        allowed_trust_zones=zones,
        mask_policy="strict" if AiTrustZone.approved_provider in zones else "role_based",
        context_recipe=context,
        prompt_id=prompt,
        prompt_version=versions[-1].version,
        output_schema=output,
        verifier_id=verifier,
        writeback_policy=writeback,
        timeout_seconds=90,
        max_output_tokens=tokens,
    )


AI_TASK_SPECS: dict[str, AiTaskSpec] = {
    "chat.general": _task(
        "chat.general", risk=AiTaskRisk.low, roles=_ALL_HUMAN_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="chat.audit_adviser", writeback="none",
    ),
    "note.policy_draft": _task(
        "note.policy_draft", risk=AiTaskRisk.normal, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="note.policy_draft",
    ),
    "note.change_analysis": _task(
        "note.change_analysis", risk=AiTaskRisk.high, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="note.change_analysis",
        verifier="note_fact_claims", context="note_fact_pack_and_prior_year", tokens=800,
    ),
    "note.rewrite": _task(
        "note.rewrite", risk=AiTaskRisk.normal, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="note.rewrite", verifier="preserve_note_facts",
    ),
    "note.continue": _task(
        "note.continue", risk=AiTaskRisk.normal, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="note.continue", verifier="preserve_note_facts", tokens=800,
    ),
    "note.completeness_review": _task(
        "note.completeness_review", risk=AiTaskRisk.high, roles=_ALL_HUMAN_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="note.completeness_review", output="review_findings",
        verifier="citation_required", writeback="none", tokens=800,
    ),
    "review.workpaper": _task(
        "review.workpaper", risk=AiTaskRisk.high, roles=_REVIEW_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="review.workpaper", output="review_findings",
        verifier="review_advisory_only", writeback="review_findings_pending", tokens=3000,
    ),
    "project.weekly_report": _task(
        "project.weekly_report", risk=AiTaskRisk.low, roles=_DRAFT_ROLES,
        zones=_APPROVED, prompt="project.weekly_report", writeback="none", tokens=500,
    ),
    "project.status_summary": _task(
        "project.status_summary", risk=AiTaskRisk.high, roles=_REVIEW_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="project.status_summary", writeback="none", tokens=600,
    ),
    "workpaper.subject_conclusion_advice": _task(
        "workpaper.subject_conclusion_advice", risk=AiTaskRisk.high, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="workpaper.subject_conclusion_advice",
        output="judgment_support", verifier="no_final_opinion", tokens=1200,
    ),
    "workpaper.analytical_review": _task(
        "workpaper.analytical_review", risk=AiTaskRisk.high, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="workpaper.analytical_review",
        verifier="note_fact_claims", writeback="none", tokens=800,
    ),
    "workpaper.field_draft": _task(
        "workpaper.field_draft", risk=AiTaskRisk.normal, roles=_DRAFT_ROLES,
        zones=_LOCAL_OR_FIRM, prompt="workpaper.field_draft",
        verifier="preserve_note_facts", tokens=1200,
    ),
}


class AiTaskNotRegistered(KeyError):
    pass


class PromptVersionNotFound(KeyError):
    pass


def get_ai_task_spec(task_code: str) -> AiTaskSpec:
    try:
        return AI_TASK_SPECS[task_code]
    except KeyError as exc:
        raise AiTaskNotRegistered(f"未登记 AI 任务：{task_code}") from exc


def get_prompt(prompt_id: str, version: str | None = None) -> PromptVersion:
    versions = PROMPT_VERSIONS.get(prompt_id)
    if not versions:
        raise PromptVersionNotFound(f"未登记 Prompt：{prompt_id}")
    if version is None:
        return versions[-1]
    for candidate in versions:
        if candidate.version == version:
            return candidate
    raise PromptVersionNotFound(f"Prompt {prompt_id} 不存在版本 {version}")


def validate_registry() -> None:
    """导入/CI 校验：任务引用真实且不可歧义的 Prompt 版本。"""
    if len(AI_TASK_SPECS) != len(set(AI_TASK_SPECS)):
        raise RuntimeError("AI task_code 重复")
    for code, spec in AI_TASK_SPECS.items():
        if code != spec.task_code:
            raise RuntimeError(f"AI task key 漂移：{code} != {spec.task_code}")
        prompt = get_prompt(spec.prompt_id, spec.prompt_version)
        if not prompt.content.strip():
            raise RuntimeError(f"Prompt 正文为空：{spec.prompt_id}@{spec.prompt_version}")
        if spec.risk_class is AiTaskRisk.prohibited and spec.writeback_policy != "none":
            raise RuntimeError(f"禁止任务不能配置写回：{code}")


validate_registry()
