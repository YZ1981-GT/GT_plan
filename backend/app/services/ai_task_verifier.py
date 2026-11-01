"""AiTaskSpec 声明的输出验证器。

验证器只做可确定的后置条件。失败会把 typed result 转为 invalid_output，不能形成
message 或 DraftArtifact；它不代替人工专业判断。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable

from app.services.ai_task_registry import AiTaskSpec


@dataclass(frozen=True)
class AiVerifierOutcome:
    verifier_id: str
    status: str
    reason_code: str | None = None
    message: str | None = None
    output_hash: str | None = None


_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d[\d,]*(?:\.\d+)?%?")
_FINAL_OPINION_RE = re.compile(
    r"(?:发表|出具|确定|最终(?:形成|作出)).{0,8}(?:无保留|保留|否定|无法表示)?审计意见"
    r"|审计意见(?:类型)?[：:]?\s*(?:标准)?(?:无保留|保留|否定|无法表示)"
)


def _fact_numbers(text: str) -> set[str]:
    values: set[str] = set()
    for match in _NUMBER_RE.finditer(text or ""):
        raw = match.group(0).replace(",", "")
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 2 or "." in raw or "%" in raw:
            values.add(raw)
    return values


def _validate_fact_tokens(output: str, corpus: str) -> tuple[bool, str | None]:
    invented = sorted(_fact_numbers(output) - _fact_numbers(corpus))
    if invented:
        return False, "输出含输入事实中不存在的数字或日期：" + "、".join(invented[:8])
    return True, None


def verify_ai_output(
    spec: AiTaskSpec,
    output: str,
    *,
    user_prompt: str,
    system_addendum: str | None,
    context_documents: Iterable[str],
) -> AiVerifierOutcome:
    verifier_id = spec.verifier_id
    stripped = (output or "").strip()
    output_hash = hashlib.sha256(stripped.encode("utf-8")).hexdigest() if stripped else None
    if not stripped:
        return AiVerifierOutcome(verifier_id, "failed", "empty_output", "模型未返回可用草稿")

    docs = [str(doc) for doc in context_documents]
    corpus = "\n".join([
        user_prompt or "",
        system_addendum or "",
        *docs,
    ])
    if verifier_id in {"note_fact_claims", "preserve_note_facts"}:
        passed, message = _validate_fact_tokens(stripped, corpus)
        if not passed:
            return AiVerifierOutcome(
                verifier_id, "failed", "unverified_fact_token", message, output_hash
            )
    elif verifier_id == "citation_required":
        if not docs:
            return AiVerifierOutcome(
                verifier_id,
                "failed",
                "citation_context_missing",
                "没有可定位依据，不能形成披露完整性建议",
                output_hash,
            )
    elif verifier_id == "review_advisory_only":
        from app.services.llm_response_parser import LlmResponseParser

        parsed = LlmResponseParser.parse(stripped)
        if not parsed.parse_success:
            return AiVerifierOutcome(
                verifier_id, "failed", "review_output_unparseable",
                "复核输出无法解析为结构化疑点", output_hash,
            )
    elif verifier_id == "no_final_opinion":
        if _FINAL_OPINION_RE.search(stripped):
            return AiVerifierOutcome(
                verifier_id, "failed", "final_opinion_prohibited",
                "AI 输出越过专业判断边界，已拒绝形成草稿", output_hash,
            )

    return AiVerifierOutcome(verifier_id, "passed", output_hash=output_hash)
