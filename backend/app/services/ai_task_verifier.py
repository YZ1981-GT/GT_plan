"""AiTaskSpec 声明的输出验证器。

验证器只做可确定的后置条件。失败会把 typed result 转为 invalid_output，不能形成
message 或 DraftArtifact；它不代替人工专业判断。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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


_DATE_RES = (
    re.compile(r"(?P<y>\d{4})\s*年\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"),
    re.compile(r"(?<!\d)(?P<y>\d{4})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})(?!\d)"),
)
_ENTITY_SUFFIXES = ("股份有限公司", "有限责任公司", "集团有限公司", "有限公司", "集团公司")
_ENTITY_RE = re.compile(
    r"[\u4e00-\u9fa5A-Za-z0-9（）()]{2,40}?(?:" + "|".join(_ENTITY_SUFFIXES) + r")"
)
# “均为有限公司”“一家有限公司”这类泛称不是具体主体
_GENERIC_ENTITY_HEADS = ("均为", "都为", "都是", "皆为", "一家", "两家", "多家", "各家", "该家", "其他")


def _normalize_number(raw: str) -> str | None:
    """数字按 Decimal 规范化：1,000.00 与 1000 视为同一事实，12.50% 与 12.5% 相同。"""
    percent = raw.endswith("%")
    body = raw.rstrip("%").replace(",", "").strip()
    try:
        value = Decimal(body)
    except InvalidOperation:
        return None
    if value == value.to_integral():
        normalized = format(value.quantize(Decimal(1)), "f")
    else:
        normalized = format(value.normalize(), "f")
    if normalized in {"-0", "+0"}:
        normalized = "0"
    return normalized + ("%" if percent else "")


def _strip_dates(text: str) -> tuple[str, set[str]]:
    dates: set[str] = set()

    def _collect(match: re.Match[str]) -> str:
        y, m, d = int(match["y"]), int(match["m"]), int(match["d"])
        if 1 <= m <= 12 and 1 <= d <= 31:
            dates.add(f"{y:04d}-{m:02d}-{d:02d}")
        return " "

    for pattern in _DATE_RES:
        text = pattern.sub(_collect, text or "")
    return text, dates


def _fact_numbers(text: str) -> set[str]:
    values: set[str] = set()
    for match in _NUMBER_RE.finditer(text or ""):
        raw = match.group(0).replace(",", "")
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 2 or "." in raw or "%" in raw:
            normalized = _normalize_number(raw)
            if normalized is not None:
                values.add(normalized)
    return values


def _fact_tokens(text: str) -> tuple[set[str], set[str]]:
    """返回 (数字, 日期)；日期先整体取出，避免“12 月 31 日”被拆成两个数字误判。"""
    remainder, dates = _strip_dates(text)
    return _fact_numbers(remainder), dates


def _invented_entities(output: str, corpus: str) -> list[str]:
    invented: list[str] = []
    for match in _ENTITY_RE.finditer(output or ""):
        name = match.group(0)
        suffix = next(s for s in _ENTITY_SUFFIXES if name.endswith(s))
        head = name[: -len(suffix)]
        if head[-2:] in _GENERIC_ENTITY_HEADS or len(head) < 2:
            continue
        # 前面可能粘着动词/介词（“向某某有限公司采购”），任一后缀尾段出现在资料里即视为有来源。
        tails = (name[i:] for i in range(0, len(head) - 1))
        if not any(tail in corpus for tail in tails):
            invented.append(name)
    return invented


def _validate_fact_tokens(
    output: str,
    corpus: str,
    *,
    allowed_facts: Iterable[str] = (),
) -> tuple[bool, str | None]:
    out_numbers, out_dates = _fact_tokens(output)
    corpus_numbers, corpus_dates = _fact_tokens(corpus)
    for fact in allowed_facts:
        normalized = _normalize_number(str(fact))
        if normalized is not None:
            corpus_numbers.add(normalized)
    corpus_years = {n for n in corpus_numbers if len(n) == 4 and n.isdigit()}
    # 资料里出现过的年度，其年末（资产负债表日）属于可推导日期
    derivable = {f"{y}-12-31" for y in corpus_years} | {f"{int(y) - 1}-12-31" for y in corpus_years}
    invented = sorted(out_numbers - corpus_numbers)
    invented_dates = sorted(out_dates - corpus_dates - derivable)
    invented_entities = _invented_entities(output, corpus)
    problems = invented[:8] + invented_dates[:4] + invented_entities[:4]
    if problems:
        return False, "输出含输入事实中不存在的数字、日期或主体：" + "、".join(problems)
    return True, None


def verify_ai_output(
    spec: AiTaskSpec,
    output: str,
    *,
    user_prompt: str,
    system_addendum: str | None,
    context_documents: Iterable[str],
    allowed_facts: Iterable[str] = (),
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
        # 事实类叙述（变动分析等）只认服务端事实包与调用方派生值；参照文档里的数字
        # 不是本期权威事实。改写/续写可沿用参照资料原文里的数字。
        fact_corpus = (
            "\n".join([user_prompt or "", system_addendum or ""])
            if verifier_id == "note_fact_claims"
            else corpus
        )
        passed, message = _validate_fact_tokens(
            stripped, fact_corpus, allowed_facts=allowed_facts
        )
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
