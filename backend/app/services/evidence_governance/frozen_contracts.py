"""冻结的共享治理契约 — Wave 0 单一真源。

本模块冻结所有治理编排层与既有引擎共享的横切契约，使后续 wave（迁移、facade、
adapter、状态机、门禁、manifest）都以这里为唯一基线，禁止各处各自发明：

1. **API 约定**：新 API 根、写命令幂等键 header、版本敏感命令 expected-version
   header、cursor 分页上限。
2. **稳定错误码**：与 design §7.2 的失败类别表一一对应，含 HTTP 状态与
   "数据效果" 语义。
3. **ActorContext**：`actor_type ∈ {user, service}` 的 XOR 结构（对齐 design
   Data Models 的 actor CHECK），Service Identity 不得执行人工确认。
4. **canonical JSON / hash**：确定性 canonical JSON 序列化 + 小写十六进制
   SHA-256，用于内容哈希、intent_hash、edge_hash、payload_hash、审计脱敏。

引擎 adapter contract（八项引擎的真实接口形状）单独存于
``backend/data/evidence_governance/adapter_contract_manifest.json``，由
``load_engine_contracts()`` 读取；本模块只提供加载器，不复制引擎签名。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 1.5
Requirements: R1, R5, R7, R8, R9, R11, R12, R15
Properties: P3 (actor 完备), P5 (哈希绑定), P25 (command-root 唯一)
"""

from __future__ import annotations

import enum
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 0. 契约版本
# ---------------------------------------------------------------------------

#: 冻结契约语义版本。任何对错误码集合、header 名、actor 语义、canonical hash
#: 算法的破坏性变更都必须递增本号，并更新契约测试。
FROZEN_CONTRACT_VERSION = "1.0.0"

#: adapter contract 清单路径（单一真源，禁止分叉清单同源）。
ADAPTER_CONTRACT_MANIFEST_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evidence_governance"
    / "adapter_contract_manifest.json"
)

# ---------------------------------------------------------------------------
# 1. API 约定（design §6.1）
# ---------------------------------------------------------------------------

#: 新治理 API 根模板；path scope 必须与对象权威 scope 一致。
API_ROOT_TEMPLATE = "/api/projects/{project_id}/years/{year}/evidence"

#: 写命令幂等键 header（所有写命令必需）。
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"

#: 版本敏感命令的 expected-version header（乐观并发）。
EXPECTED_VERSION_HEADER = "If-Match"

#: cursor 分页默认上限与硬上限；大图/归档不提供无界列表。
CURSOR_PAGE_DEFAULT_LIMIT = 100
CURSOR_PAGE_MAX_LIMIT = 200


# ---------------------------------------------------------------------------
# 2. 稳定错误码（design §7.2）
# ---------------------------------------------------------------------------


class EvidenceErrorCode(str, enum.Enum):
    """治理层稳定失败类别。

    错误响应含稳定 ``error_code/message/trace_id/retryable``；权限/存在性错误
    不得包含目标名称、客户、项目或路径。
    """

    SCOPE_NOT_FOUND_OR_FORBIDDEN = "SCOPE_NOT_FOUND_OR_FORBIDDEN"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    EVIDENCE_GATE_BLOCKED = "EVIDENCE_GATE_BLOCKED"
    ATTACHMENT_TOO_LARGE = "ATTACHMENT_TOO_LARGE"
    MEDIA_TYPE_MISMATCH = "MEDIA_TYPE_MISMATCH"
    METADATA_INCOMPLETE = "METADATA_INCOMPLETE"
    REQUIRED_FIELD_UNDECIDED = "REQUIRED_FIELD_UNDECIDED"
    INVALID_MAPPING = "INVALID_MAPPING"
    LEGAL_HOLD_ACTIVE = "LEGAL_HOLD_ACTIVE"
    CAPACITY_BACKPRESSURE = "CAPACITY_BACKPRESSURE"
    DEPENDENCY_DEGRADED = "DEPENDENCY_DEGRADED"


#: error_code → 主 HTTP 状态码（design §7.2 表；多状态取语义主状态）。
ERROR_CODE_HTTP_STATUS: dict[EvidenceErrorCode, int] = {
    EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN: 404,
    EvidenceErrorCode.VERSION_CONFLICT: 409,
    EvidenceErrorCode.INVALID_STATE_TRANSITION: 409,
    EvidenceErrorCode.EVIDENCE_GATE_BLOCKED: 409,
    EvidenceErrorCode.ATTACHMENT_TOO_LARGE: 413,
    EvidenceErrorCode.MEDIA_TYPE_MISMATCH: 415,
    EvidenceErrorCode.METADATA_INCOMPLETE: 422,
    EvidenceErrorCode.REQUIRED_FIELD_UNDECIDED: 422,
    EvidenceErrorCode.INVALID_MAPPING: 422,
    EvidenceErrorCode.LEGAL_HOLD_ACTIVE: 423,
    EvidenceErrorCode.CAPACITY_BACKPRESSURE: 429,
    EvidenceErrorCode.DEPENDENCY_DEGRADED: 503,
}

#: "降级安全" 终态禁止码：这些错误发生时不得产生 confirmed/written_back/archived
#: 终态（P29）。
DEGRADED_SAFE_ERROR_CODES: frozenset[EvidenceErrorCode] = frozenset(
    {
        EvidenceErrorCode.DEPENDENCY_DEGRADED,
        EvidenceErrorCode.CAPACITY_BACKPRESSURE,
    }
)


class EvidenceGovernanceError(Exception):
    """带稳定 error_code 的治理异常。message 不得泄露目标名称/路径。"""

    def __init__(
        self,
        error_code: EvidenceErrorCode,
        message: str = "",
        *,
        retryable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.http_status = ERROR_CODE_HTTP_STATUS[error_code]
        self.retryable = retryable
        super().__init__(message or error_code.value)


# ---------------------------------------------------------------------------
# 3. ActorContext（design Data Models — actor XOR）
# ---------------------------------------------------------------------------


class ActorType(str, enum.Enum):
    USER = "user"
    SERVICE = "service"


#: Service Identity 永远不能执行的人工动作（design §2.2）。
SERVICE_FORBIDDEN_ACTIONS: frozenset[str] = frozenset(
    {
        "human_confirm",
        "review_close",
        "hold_release",
        "qc_complete",
        "eqcr_complete",
        "signoff",
        "ocr_confirm",
        "ai_confirm",
    }
)


@dataclass(frozen=True)
class ActorContext:
    """成功新记录的责任主体：人工用户或明确 Service Identity 的 XOR。

    对齐 design 的物理 actor CHECK：
        actor_type='user'    → actor_user_id 非空、actor_service_identity_id 空
        actor_type='service' → actor_service_identity_id 非空、actor_user_id 空

    禁止匿名新记录（P3）；禁止单个多态 actor_id。
    """

    actor_type: ActorType
    actor_user_id: uuid.UUID | None = None
    actor_service_identity_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        at = self.actor_type
        if at == ActorType.USER:
            if self.actor_user_id is None or self.actor_service_identity_id is not None:
                raise ValueError(
                    "actor_type='user' 必须提供 actor_user_id 且不得提供 "
                    "actor_service_identity_id"
                )
        elif at == ActorType.SERVICE:
            if (
                self.actor_service_identity_id is None
                or self.actor_user_id is not None
            ):
                raise ValueError(
                    "actor_type='service' 必须提供 actor_service_identity_id 且不得 "
                    "提供 actor_user_id"
                )
        else:  # pragma: no cover - enum 已约束
            raise ValueError(f"未知 actor_type: {at!r}")

    @property
    def is_service(self) -> bool:
        return self.actor_type == ActorType.SERVICE

    def can_perform_human_action(self, action: str) -> bool:
        """Service Identity 不得执行人工动作。"""
        if self.is_service and action in SERVICE_FORBIDDEN_ACTIONS:
            return False
        return True

    def assert_human_action(self, action: str) -> None:
        if not self.can_perform_human_action(action):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                f"Service Identity 不得执行人工动作: {action}",
            )

    def to_audit_dict(self) -> dict[str, str | None]:
        """脱敏审计投影：只含 actor 标识，不含凭据。"""
        return {
            "actor_type": self.actor_type.value,
            "actor_user_id": (
                str(self.actor_user_id) if self.actor_user_id else None
            ),
            "actor_service_identity_id": (
                str(self.actor_service_identity_id)
                if self.actor_service_identity_id
                else None
            ),
        }

    @classmethod
    def for_user(cls, user_id: uuid.UUID | str) -> "ActorContext":
        return cls(
            actor_type=ActorType.USER,
            actor_user_id=_coerce_uuid(user_id),
        )

    @classmethod
    def for_service(cls, service_identity_id: uuid.UUID | str) -> "ActorContext":
        return cls(
            actor_type=ActorType.SERVICE,
            actor_service_identity_id=_coerce_uuid(service_identity_id),
        )


def _coerce_uuid(value: uuid.UUID | str) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


# ---------------------------------------------------------------------------
# 4. canonical JSON / hash（P5 哈希绑定、intent/edge/payload/content hash）
# ---------------------------------------------------------------------------

#: 64 位小写十六进制 SHA-256。
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_json(obj: Any) -> str:
    """确定性 canonical JSON 序列化。

    - 键按字典序排序，保证同一逻辑对象序列化稳定；
    - 无多余空白（紧凑 separators）；
    - ``ensure_ascii=False`` 保留中文原文（哈希对字节而非转义码稳定）；
    - 与语言/平台无关，供跨进程离线重算（P24/离线验签）。
    """
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(value: Any) -> str:
    # UUID / Decimal / datetime 等以稳定字符串表示
    return str(value)


def sha256_hex(data: bytes | str) -> str:
    """字节或字符串的小写十六进制 SHA-256（P5）。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash_of(obj: Any) -> str:
    """任意可 JSON 化对象的 canonical 内容哈希。

    相同逻辑内容 → 相同哈希；任意内容变化 → 哈希变化（P5）。
    用于 content_hash / intent_hash / edge_hash / payload_hash / prompt_hash。
    """
    return sha256_hex(canonical_json(obj))


def is_sha256_hex(value: str | None) -> bool:
    return bool(value) and bool(SHA256_HEX_RE.match(value))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 5. Adapter contract 清单加载器（单一真源）
# ---------------------------------------------------------------------------


def load_engine_contracts(
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """加载八项引擎 adapter contract + 禁止分叉清单（单一真源）。

    契约测试与 no-fork CI guard 都读取同一份 JSON，保证 "验证真实接口形状" 与
    "禁止分叉" 使用同一基线。
    """
    path = manifest_path or ADAPTER_CONTRACT_MANIFEST_PATH
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


#: 冻结的八项复用引擎名（与 design §1.2 一致；AiContentLog 拆为 service+model
#: 两个契约条目，故清单条目数 > 8）。
FROZEN_ENGINE_NAMES: tuple[str, ...] = (
    "AttachmentService",
    "UnifiedOCRService",
    "KnowledgeIndexService",
    "AiContentLog",
    "ACNR",
    "StalePropagationEngine",
    "DeliverableService",
    "ArchiveOrchestrator",
)


__all__ = [
    "FROZEN_CONTRACT_VERSION",
    "ADAPTER_CONTRACT_MANIFEST_PATH",
    "API_ROOT_TEMPLATE",
    "IDEMPOTENCY_KEY_HEADER",
    "EXPECTED_VERSION_HEADER",
    "CURSOR_PAGE_DEFAULT_LIMIT",
    "CURSOR_PAGE_MAX_LIMIT",
    "EvidenceErrorCode",
    "ERROR_CODE_HTTP_STATUS",
    "DEGRADED_SAFE_ERROR_CODES",
    "EvidenceGovernanceError",
    "ActorType",
    "ActorContext",
    "SERVICE_FORBIDDEN_ACTIONS",
    "SHA256_HEX_RE",
    "canonical_json",
    "sha256_hex",
    "content_hash_of",
    "is_sha256_hex",
    "load_engine_contracts",
    "FROZEN_ENGINE_NAMES",
]
