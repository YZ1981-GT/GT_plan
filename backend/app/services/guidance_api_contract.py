"""Task 9：Guidance API 版本、稳定缓存与错误模型。

对齐 spec Requirement 9 + design.md §9：
    * Response fingerprint 覆盖 subject / inventory / publication / supplement /
      refs / schema / contract version
    * Stable cache key 不含 contextRevision（contextRevision 只作竞态门）
    * ETag = `"W/" + response_version`（弱 ETag，内容指纹，非强一致）
    * 结构化错误返回（invalid / timeout / stale / permission / blocked）
    * 日志脱敏：不写 token / 附件正文 / 敏感项目内容

🔴 判据：
    * fingerprint 稳定：同 subject + 同 digests → 同 etag；任何一维变化 → 变
    * stable cache key 无 contextRevision（变异 M-T9-CTX-REVISION-IN-KEY 打红）
    * error 结构化：code/subject/operation/correlation 必填（M-T9-ERROR-FLAT 打红）
    * 日志只记 correlation/subject/operation/version/verdict（M-T9-LOG-PII 打红）
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

GUIDANCE_RESPONSE_SCHEMA_VERSION = "guidance-response-v1"

StructuredErrorCode = Literal[
    "invalid",
    "timeout",
    "stale",
    "permission_denied",
    "membership_denied",
    "blocked",
    "internal",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response fingerprint / ETag
# ---------------------------------------------------------------------------


def compute_response_fingerprint(*, parts: dict[str, Any]) -> str:
    """稳定 sha256 fingerprint。

    入参是 dict；内部 JSON 序列化 sort_keys=True + compact separators，
    保证同内容 → 同 fingerprint。None / 空列表 / 空字典都参与计算。
    """
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_etag(response_version: str) -> str:
    """弱 ETag（内容协商语义：内容变了 ETag 变，但客户端不应把 ETag 当强一致）。"""
    return f'W/"{response_version}"'


def response_version_from_fingerprint(fingerprint: str) -> str:
    """fingerprint 前 16 位作为 response_version 短串（避免整串 64 位塞入 ETag）。"""
    return fingerprint[:16]


# ---------------------------------------------------------------------------
# Stable cache key
# ---------------------------------------------------------------------------


def compute_stable_cache_key(
    *,
    project_id: str | None,
    wp_code: str,
    entry_id: str | None,
    sheet_key: str | None,
    schema_version: str = GUIDANCE_RESPONSE_SCHEMA_VERSION,
    subject_digest: str | None = None,
    inventory_digest: str | None = None,
    publication_digest: str | None = None,
    supplement_digest: str | None = None,
    refs_digest: str | None = None,
) -> str:
    """稳定 cache key。

    🔴 铁律：不含 contextRevision / ownerEpoch / 客户端瞬态字段。
    这些字段只作竞态门，不作持久 cache identity。
    """
    fingerprint = compute_response_fingerprint(parts={
        "project_id": project_id,
        "wp_code": wp_code,
        "entry_id": entry_id,
        "sheet_key": sheet_key,
        "schema_version": schema_version,
        "subject_digest": subject_digest,
        "inventory_digest": inventory_digest,
        "publication_digest": publication_digest,
        "supplement_digest": supplement_digest,
        "refs_digest": refs_digest,
    })
    return f"guidance|{fingerprint[:32]}"


# ---------------------------------------------------------------------------
# Structured errors
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructuredError:
    """结构化错误返回。

    🔴 必须包含 code / subject / operation / correlation —— 缺一个 route 层守卫打红。
    🔴 message 不含敏感项目内容/token/附件正文（由 to_dict 层脱敏）。
    """

    code: StructuredErrorCode
    message: str
    subject: str | None = None
    operation: str = "guidance.resolve"
    correlation_id: str | None = None
    owner_user_id: str | None = None
    owner_role: str | None = None
    next_step_hint: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": _redact_message(self.message),
                "subject": self.subject,
                "operation": self.operation,
                "correlation_id": self.correlation_id,
                "owner": {"user_id": self.owner_user_id, "role": self.owner_role} if self.owner_user_id else None,
                "next_step": self.next_step_hint,
                "details": self.details,
            }
        }


def _redact_message(message: str) -> str:
    """脱敏 message：不出现 token/长字符串/密钥。

    判据：
        - 64+ 位的十六进制串视为 token/hash，替换为 [REDACTED]
        - 长度 > 200 的字符串截断到 100 字
    """
    if not message:
        return message
    out = message
    # 64+ hex 串 → 替换
    import re
    out = re.sub(r"\b[0-9a-fA-F]{32,}\b", "[REDACTED]", out)
    if len(out) > 200:
        out = out[:100] + "...[TRUNCATED]"
    return out


# ---------------------------------------------------------------------------
# 日志脱敏（memory 铁律：日志只记 correlation/subject/operation/version/verdict）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuidanceLogEvent:
    """结构化日志事件。仅允许字段：correlation/subject/operation/version/verdict。"""

    correlation_id: str
    subject: str
    operation: str
    version: str
    verdict: str

    def to_dict(self) -> dict[str, str]:
        return {
            "correlation_id": self.correlation_id,
            "subject": self.subject,
            "operation": self.operation,
            "version": self.version,
            "verdict": self.verdict,
        }


def log_guidance_event(event: GuidanceLogEvent) -> None:
    """输出到 logger；只含白名单字段，绝无正文/token。"""
    logger.info("guidance_event %s", json.dumps(event.to_dict(), ensure_ascii=False))


# ---------------------------------------------------------------------------
# Owner epoch / revision gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnerGate:
    """owner_epoch / revision 竞态门。

    用途：前端收到 async response 时，比对 owner_epoch 和 revision 是否仍是
    当前 context 的；不匹配即丢弃（防串项目/串 sheet）。
    """

    owner_epoch: int
    revision: str | None = None

    def accepts(self, incoming_epoch: int, incoming_revision: str | None) -> bool:
        if incoming_epoch != self.owner_epoch:
            return False
        if self.revision is not None and incoming_revision != self.revision:
            return False
        return True
