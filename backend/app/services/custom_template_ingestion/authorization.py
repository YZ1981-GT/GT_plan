"""tenant/org/project scope、capability 与 immutable ApprovalIntent。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 11.7, 16.2, 16.4

## G-C0 消费关系（Requirement 2.x / design §1）

本模块**不复制** G-C0 的字段定义。`TemplateAuthorityIdentity`（candidate/finalized）、
`ConsumerAck`、`EvidenceEnvelope` 的 wire schema 真源在
`audit-platform/frontend/src/shared/contracts/gc0/index.ts`（已交付，见 T01 §F）。
本模块只做两件事：

1. 复述 **字段名集合**（`GC0_IDENTITY_FIELDS_*`）用于跨语言 conformance 校验；
2. 消费它构造 `TemplateAuthorityIdentity` 载荷 dict（供 Task 9/11 提交 handoff）。

字段名集合若与 G-C0 漂移，`test_contract_conformance.py` 必红 —— 判据是集合**等值**，
不是字符串存在。

## 已实测的平台缺口（写入代码，不假绿）

T01 §D 取证：

* 平台**无 Organization 实体**。`users` 表只有 `office_code`；
  `audit_platform_models` / `dataset_models` 的 `tenant_id` 是 `String(64)` 且恒
  `server_default='default'`，注释明写「多租户预留列（暂恒为 'default'）」；
  `get_active_filter` 未启用租户校验。
* `pg_catalog.pg_type` 的 `userrole` 枚举 = `{admin, auditor, eqcr, manager, partner, qc, readonly}`
  —— **无 `template_admin`**。

因此 Task 2 的可交付边界是：

| 项 | 状态 |
|---|---|
| scope 结构 + 服务端推导 + 拒客户端推断 | ✅ 本模块交付 |
| ApprovalIntent 不可变 + 失效规则 + initiator≠approver | ✅ 本模块交付 |
| `template_admin` 角色 + 五角色 capability 矩阵 | ⚠️ 矩阵已交付；**角色落库需新增 PG enum 值**（迁移 V156+，未做） |
| 真实多租户 tenant_id | ⚠️ 占位 `'default'`，待平台级多租户落地（不在本 spec 范围） |

## authorizationEpoch / writeFence 与 content fingerprint 分离（Requirement 2.5 / 11.7）

`AuthorizationEpoch` 只在**角色 / 项目成员关系 / 权限位**变化时推进，与文件字节无关。
🔴 content fingerprint 由 Task 3 的 policy/adapter/guidance digest 构成，**绝不**包含
角色信息 —— 否则「换个人审批」会被误判成「文件变了」，制造无谓的 artifact 冲突。
本模块只提供 epoch 载体，不提供 fingerprint 计算（避免两处真源）。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol

# ─────────────────────────────────────────────────────────────────────────────
# 0) 可注入时钟 —— 所有时间判断走它，测试不得依赖真实墙钟（Requirement 6.7）
# ─────────────────────────────────────────────────────────────────────────────


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """生产用时钟。时区感知（timestamptz 回写必须 Python 侧转 datetime）。"""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _utc_now(clock: Clock) -> datetime:
    v = clock.now()
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# 1) G-C0 字段名集合 —— 用于 conformance 校验，非 wire 真源
# ─────────────────────────────────────────────────────────────────────────────

GC0_CONTRACT_VERSION: str = "1.0"

#: 真源 = frontend/src/shared/contracts/gc0/index.ts::TemplateAuthorityIdentityCandidate
GC0_IDENTITY_FIELDS_CANDIDATE: frozenset[str] = frozenset({
    "contractVersion",
    "phase",
    "scope",
    "organizationId",
    "projectId",
    "candidateId",
    "candidateRevision",
    "workbookLineageId",
    "artifactSha256",
    "policyVersion",
})

#: 真源 = .../TemplateAuthorityIdentityFinalized
GC0_IDENTITY_FIELDS_FINALIZED: frozenset[str] = frozenset({
    "contractVersion",
    "phase",
    "scope",
    "organizationId",
    "projectId",
    "templateId",
    "templateVersionId",
    "finalizationId",
    "workbookLineageId",
    "artifactSha256",
    "policyVersion",
    "manifestVersion",
})

#: candidate 必须**不含** template/finalization 三字段（G-C0 Req 1.4 的判别器约束）。
GC0_FINALIZED_ONLY_FIELDS: frozenset[str] = frozenset({
    "templateId",
    "templateVersionId",
    "finalizationId",
})

assert not (GC0_IDENTITY_FIELDS_CANDIDATE & GC0_FINALIZED_ONLY_FIELDS)
assert GC0_IDENTITY_FIELDS_FINALIZED >= GC0_FINALIZED_ONLY_FIELDS


def build_authority_identity_candidate(
    *,
    scope: Literal["organization", "project"],
    organization_id: str,
    project_id: str | None,
    candidate_id: str,
    candidate_revision: str,
    workbook_lineage_id: str,
    artifact_sha256: str,
    policy_version: str,
) -> dict[str, object]:
    """构造 G-C0 candidate authority identity 载荷。

    🔴 字段名集合必须精确等于 `GC0_IDENTITY_FIELDS_CANDIDATE`，且不含
    `GC0_FINALIZED_ONLY_FIELDS` —— candidate 阶段填 finalization 字段就是
    Requirement 9.4 禁止的「伪造 confirmed」。
    """
    payload: dict[str, object] = {
        "contractVersion": GC0_CONTRACT_VERSION,
        "phase": "candidate",
        "scope": scope,
        "organizationId": organization_id,
        "projectId": project_id,
        "candidateId": candidate_id,
        "candidateRevision": candidate_revision,
        "workbookLineageId": workbook_lineage_id,
        "artifactSha256": artifact_sha256,
        "policyVersion": policy_version,
    }
    _assert_identity_shape(payload, GC0_IDENTITY_FIELDS_CANDIDATE, allow_extra=False)
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# 2) Scope —— 服务端推导，绝不信任客户端推断（Requirement 2.1）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Scope:
    """domain object 的归属 scope。

    Attributes:
        tenant_id: 平台预留多租户列，当前恒 `'default'`（T01 §D 实测缺口）。
        organization_id: 组织 id。platform 无 Organization 实体，当前由
            `organization_id_from_user` 从 `office_code` 确定性派生 —— 这是
            **占位策略**，非真源；落地 Organization 表后必须替换。
        project_id: project-local 对象必填。
    """

    tenant_id: str
    organization_id: str
    project_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "tenantId": self.tenant_id,
            "organizationId": self.organization_id,
            "projectId": self.project_id,
        }


# 平台多租户预留值 —— 与 audit_platform_models.tenant_id server_default 对齐。
# 🔴 这是占位，不是能力：`Scope.from_*` 会校验它，但不代表真做了租户隔离。
PLATFORM_TENANT_ID: str = "default"


class ScopeError(ValueError):
    """scope 推导失败。"""


def organization_id_from_user(user: object) -> str:
    """从用户推导 organization id。

    🔴 平台无 Organization 实体（T01 §D）：唯一可用的稳定组织维度是
    `users.office_code`。缺失时回落到字面量 `'default'` 而不是抛错 —— 现存用户
    大量没有 office_code，抛错会让全部 legacy 数据不可迁移。

    返回值仅作**稳定分组键**，禁止当权威组织身份用。
    """
    code = getattr(user, "office_code", None)
    code = (code or "").strip()
    return f"org:{code.lower()}" if code else "org:default"


def derive_implicit_scope(*, user: object, project_id: str | None = None) -> Scope:
    """服务端推导隐式 scope。

    Requirement 2.1：project-local 对象必须绑定 project；服务端不得从客户端文件名或
    wp_code 推断 scope。本函数**不接受**任何客户端提供的 scope 字段。
    """
    if not getattr(user, "is_active", True):
        raise ScopeError("用户已停用，无法推导 scope")
    return Scope(
        tenant_id=PLATFORM_TENANT_ID,
        organization_id=organization_id_from_user(user),
        project_id=project_id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3) Capability —— 五角色矩阵（Requirement 2.4, 2.6, 2.7）
# ─────────────────────────────────────────────────────────────────────────────

#: 自定义模板摄取域的角色取值。
#:
#: 🔴 `template_admin` 在 PG enum `userrole` 中**不存在**（T01 实测 7 值）。
#: 矩阵在此声明它是合法 actor，但 `role_of()` 永远取不到它，除非先加迁移扩展枚举。
#: 因此「方法论/模板管理员发起发布」这条路径在迁移落地前**结构性不可达**，
#: 由 `test_template_admin_role_is_declared_but_not_provisioned` 显式锁死该事实，
#: 防止有人误以为权限已就绪。
TEMPLATE_ADMIN_ROLE: str = "template_admin"

#: 平台既有系统角色（真源 = role_capability_contract.SYSTEM_ROLES）。
KNOWN_SYSTEM_ROLES: tuple[str, ...] = (
    "admin",
    "partner",
    "manager",
    "auditor",
    "qc",
    "eqcr",
    "readonly",
)

#: 本域 actor = 平台角色 + template_admin。
CUSTOM_DOMAIN_ACTORS: frozenset[str] = frozenset(KNOWN_SYSTEM_ROLES) | {TEMPLATE_ADMIN_ROLE}

#: Requirement 2.4 规定的发起/批准角色类。
ORIGINATOR_CLASSES: frozenset[str] = frozenset({TEMPLATE_ADMIN_ROLE})
APPROVER_CLASSES: frozenset[str] = frozenset({"partner", "qc"})


class Capability:
    """摄取域 capability 名（稳定字符串，用于幂等键与审计）。

    🔴 区分「发起」（publish/confirm）与「批准」（approve）两类权：
    * 发起权 = `PUBLISH_ORGANIZATION` / `CONFIRM_MAPPING` —— 只有 template_admin /
      manager 等有；
    * 批准权 = `APPROVE_PUBLISH_ORGANIZATION` —— partner / qc 拥有，用于在
      ApprovalIntent 流程中做双人复核。

    若把两者合并成一个 capability，Requirement 2.3 的「initiator≠approver」
    就无法表达（发起者恰好也带批准权时同一个人就能自批自过）。
    """

    UPLOAD = "custom_template.upload"
    CONFIRM_MAPPING = "custom_template.confirm_mapping"
    PUBLISH_ORGANIZATION = "custom_template.publish_organization"
    APPROVE_PUBLISH_ORGANIZATION = "custom_template.approve_publish_organization"
    FINALIZE_PROJECT = "custom_template.finalize_project"
    INSTANTIATE = "custom_template.instantiate"
    WRITE_MUTATION = "custom_template.write_mutation"
    READ_RAW_QUARANTINE = "custom_template.read_raw_quarantine"


#: 角色 → capability。Requirement 2.4 的硬约束：
#: * 审计助理只能上传与编辑 draft mapping（**不能**确认/发布/实例化/写入）；
#: * 现场经理能项目级 finalize / instantiate / write，**不能**组织级发布；
#: * 业务合伙人/QC 只有**批准**权，不能发起组织级发布（Requirement 2.7：
#:   有项目读取权限不等于获得发布权限）；
#: * 组织级发布的**发起**只有 template_admin。
#: 🔴 读 raw quarantine 不给审计助理（Requirement 2.7）。
CAPABILITY_MATRIX: dict[str, frozenset[str]] = {
    TEMPLATE_ADMIN_ROLE: frozenset({
        Capability.UPLOAD,
        Capability.CONFIRM_MAPPING,
        Capability.PUBLISH_ORGANIZATION,
        Capability.READ_RAW_QUARANTINE,
    }),
    "manager": frozenset({
        Capability.UPLOAD,
        Capability.CONFIRM_MAPPING,
        Capability.FINALIZE_PROJECT,
        Capability.INSTANTIATE,
        Capability.WRITE_MUTATION,
    }),
    "partner": frozenset({
        Capability.UPLOAD,
        Capability.FINALIZE_PROJECT,
        Capability.INSTANTIATE,
        Capability.WRITE_MUTATION,
        Capability.APPROVE_PUBLISH_ORGANIZATION,  # 批准者，非发起者
    }),
    "qc": frozenset({
        Capability.UPLOAD,
        Capability.APPROVE_PUBLISH_ORGANIZATION,  # 质量控制复核合伙人批准
    }),
    "eqcr": frozenset({Capability.UPLOAD}),
    "auditor": frozenset({
        Capability.UPLOAD,
    }),  # 🔴 Requirement 2.4：只能上传 + 编辑 draft mapping；confirm 不给
    "admin": frozenset({
        Capability.UPLOAD,
        Capability.CONFIRM_MAPPING,
        Capability.FINALIZE_PROJECT,
        Capability.INSTANTIATE,
        Capability.WRITE_MUTATION,
    }),
    "readonly": frozenset(),
}


def approval_capability_for_action(action: str) -> str:
    """批准动作所需 capability（与发起 capability 分离）。

    只有组织级发布走双人复核；其余动作的项目级审批由现场经理 capability 直接复验
    （Requirement 2.4）。
    """
    if action == "publish_organization":
        return Capability.APPROVE_PUBLISH_ORGANIZATION
    if action in ("finalize_project", "upgrade", "rollback", "remap"):
        return Capability.FINALIZE_PROJECT
    if action == "security_revoke":
        return Capability.APPROVE_PUBLISH_ORGANIZATION
    raise ValueError(f"无映射 approval capability 的 action: {action!r}")


def role_of(user: object) -> str:
    """取系统角色字符串（真源 = `users.role`，不读 JWT claim）。"""
    raw = getattr(user, "role", None)
    if raw is None:
        return "readonly"
    if isinstance(raw, str):
        return raw
    # ORM enum → value
    val = getattr(raw, "value", None)
    return str(val) if val is not None else "readonly"


def is_permitted(role: str, capability: str) -> bool:
    """deny-by-default 判定。

    🔴 未在矩阵登记的角色或 capability 一律 False —— 与 evidence_governance 的
    `is_permitted` 同语义，禁止静默放行。
    """
    return capability in CAPABILITY_MATRIX.get(role, frozenset())


# ─────────────────────────────────────────────────────────────────────────────
# 4) AuthorizationEpoch / WriteFence —— 与 content fingerprint 独立
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AuthorizationEpoch:
    """权限纪元。只在授权事实变化时推进。

    🔴 与 content fingerprint 严格分离（Requirement 2.5 / 11.7）：
    角色/成员关系变化推进它，但**不**改变文件 digest，因此不会制造
    「权限变了 → artifact 冲突」的假冲突。

    Attributes:
        basis: 规范 JSON 事实串（可审计、可读）。
        basis_digest: basis 的稳定摘要。
        basis 不得包含角色、权限或任何文件字节字段。
    """

    epoch: int
    organization_id: str
    basis: str
    basis_digest: str = ""

    def __post_init__(self) -> None:
        if not self.basis_digest:
            object.__setattr__(
                self, "basis_digest",
                hashlib.sha256(self.basis.encode()).hexdigest()[:8],
            )


def compute_authorization_epoch(*, organization_id: str, project_id: str | None) -> AuthorizationEpoch:
    """从授权事实推导 epoch。

    🔴 签名只接受 organization/project 身份 —— 不接受 role、permission、
    file_sha256 等任何 content 字段。这是 Requirement 11.7 的结构性保证：
    权限变化推进 epoch，但不会与 artifact 内容冲突混在一起。

    真实实现在 Task 7 的生命周期仓库里持久化递增；本函数保证「输入面」正确，
    使任何想在 epoch 里塞文件字节的改动都改不动。
    """
    basis = json.dumps({
        "organizationId": organization_id,
        "projectId": project_id,
    }, sort_keys=True)
    return AuthorizationEpoch(
        epoch=1, organization_id=organization_id, basis=basis
    )


class AuthorizationEpochMismatch(ValueError):
    """客户端提交的 epoch 与服务端不一致。"""


class WriteFenceMismatch(ValueError):
    """客户端 write fence 与服务端 operation fence 不匹配。"""


# ─────────────────────────────────────────────────────────────────────────────
# 5) ApprovalIntent —— 不可变审批意图（Requirement 2.2, 2.3, 2.5）
# ─────────────────────────────────────────────────────────────────────────────

RequestedAction = Literal[
    "publish_organization",
    "finalize_project",
    "upgrade",
    "rollback",
    "remap",
    "security_revoke",
]

_REQUESTED_ACTIONS: frozenset[str] = frozenset({
    "publish_organization",
    "finalize_project",
    "upgrade",
    "rollback",
    "remap",
    "security_revoke",
})

DEFAULT_INTENT_TTL_SECONDS: int = 7 * 24 * 3600


@dataclass(frozen=True, slots=True)
class ApprovalIntent:
    """不可变审批意图。

    🔴 构造后所有字段冻结（`frozen=True` + `slots=True`）。任何 candidate /
    policy / scope / digest / authorizationEpoch 变化都必须**新建**一个 intent，
    不得原地改批准对象（Requirement 2.5）。

    Attributes:
        scope: 必须是 `'organization'` 或 `'project'`。
        required_approver_class: 批准角色类；组织级发布时不得等于 initiator 角色。
        authorization_epoch: 冻结授权纪元；变化即失效。
    """

    approval_intent_id: str
    scope: Literal["organization", "project"]
    organization_id: str
    project_id: str | None
    candidate_id: str
    candidate_digest: str
    policy_version: str
    requested_action: RequestedAction
    initiator_id: str
    initiator_role: str
    required_approver_class: str
    authorization_epoch: int
    created_at: datetime
    expires_at: datetime
    _digest: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.requested_action not in _REQUESTED_ACTIONS:
            raise ValueError(
                f"非法 requested_action: {self.requested_action!r}（合法 {sorted(_REQUESTED_ACTIONS)}）"
            )
        if self.scope not in ("organization", "project"):
            raise ValueError(f"非法 scope: {self.scope!r}")
        if self.scope == "project" and not self.project_id:
            raise ValueError("project scope 必须带 project_id")
        if self.scope == "organization" and self.project_id is not None:
            raise ValueError("organization scope 不得带 project_id")
        if not self.candidate_digest or not self.candidate_id:
            raise ValueError("candidate_id / candidate_digest 必填")
        if not self.policy_version:
            raise ValueError("policy_version 必填")
        if not is_permitted(self.initiator_role, self._capability_for_action()):
            raise PermissionError(
                f"角色 {self.initiator_role!r} 无权发起 {self.requested_action!r}"
            )
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at 必须晚于 created_at")
        object.__setattr__(
            self, "_digest", self._compute_digest()
        )

    def _capability_for_action(self) -> str:
        if self.requested_action == "publish_organization":
            return Capability.PUBLISH_ORGANIZATION
        if self.requested_action in ("finalize_project", "upgrade", "rollback", "remap"):
            return Capability.FINALIZE_PROJECT
        if self.requested_action == "security_revoke":
            return Capability.PUBLISH_ORGANIZATION
        raise ValueError(f"无映射 capability 的 action: {self.requested_action!r}")

    def _compute_digest(self) -> str:
        """审批意图的规范 digest（用于幂等与失效比对）。

        🔴 不纳入 `created_at`/`expires_at` —— 否则「重新签发同一意图」会得到不同
        digest，幂等重试无法识别为同一条。时间仅用于过期判断。
        """
        basis = {
            "scope": self.scope,
            "organizationId": self.organization_id,
            "projectId": self.project_id,
            "candidateId": self.candidate_id,
            "candidateDigest": self.candidate_digest,
            "policyVersion": self.policy_version,
            "requestedAction": self.requested_action,
            "initiatorId": self.initiator_id,
            "requiredApproverClass": self.required_approver_class,
            "authorizationEpoch": self.authorization_epoch,
        }
        return hashlib.sha256(
            json.dumps(basis, sort_keys=True).encode()
        ).hexdigest()

    def fingerprint(self) -> str:
        """用于「变化即失效」比较的 digest。"""
        return self._digest

    def is_expired(self, clock: Clock) -> bool:
        return _utc_now(clock) >= self.expires_at

    def still_valid_for(
        self,
        *,
        candidate_digest: str,
        policy_version: str,
        scope: str,
        organization_id: str,
        project_id: str | None,
        authorization_epoch: int,
        clock: Clock,
    ) -> bool:
        """Requirement 2.5：candidate/policy/scope/digest/epoch 任一变化即失效。"""
        if self.is_expired(clock):
            return False
        return (
            self.candidate_digest == candidate_digest
            and self.policy_version == policy_version
            and self.scope == scope
            and self.organization_id == organization_id
            and self.project_id == project_id
            and self.authorization_epoch == authorization_epoch
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "approvalIntentId": self.approval_intent_id,
            "scope": self.scope,
            "organizationId": self.organization_id,
            "projectId": self.project_id,
            "candidateId": self.candidate_id,
            "candidateDigest": self.candidate_digest,
            "policyVersion": self.policy_version,
            "requestedAction": self.requested_action,
            "initiatorId": self.initiator_id,
            "initiatorRole": self.initiator_role,
            "requiredApproverClass": self.required_approver_class,
            "authorizationEpoch": self.authorization_epoch,
            "createdAt": self.created_at.isoformat(),
            "expiresAt": self.expires_at.isoformat(),
            "fingerprint": self.fingerprint(),
        }


class ApprovalIntentStale(ValueError):
    """审批意图已失效（过期或指纹变化）。"""


class InitiatorApproverSameSubject(PermissionError):
    """initiator 与 approver 为同一主体（Requirement 2.3）。"""


def approve_intent(
    intent: ApprovalIntent,
    *,
    approver_id: str,
    approver_role: str,
    candidate_digest: str,
    policy_version: str,
    authorization_epoch: int,
    clock: Clock,
) -> None:
    """校验一次批准动作。

    Requirement 2.3：组织级发布时 initiator 与 approver 必须为不同主体，且审批人
    必须属于 `required_approver_class`。
    Requirement 2.5：candidate digest / policy / epoch 变化则原 intent 失效。
    """
    if intent.is_expired(clock):
        raise ApprovalIntentStale(f"审批意图 {intent.approval_intent_id} 已过期")
    if approver_id == intent.initiator_id:
        raise InitiatorApproverSameSubject(
            f"发起人 {approver_id} 与审批人相同 —— Requirement 2.3 要求二者为不同主体"
        )
    if approver_role != intent.required_approver_class:
        raise PermissionError(
            f"角色 {approver_role!r} 不是本意图要求的审批角色类 "
            f"{intent.required_approver_class!r}"
        )
    if not is_permitted(approver_role, approval_capability_for_action(intent.requested_action)):
        raise PermissionError(
            f"角色 {approver_role!r} 不具备批准 {intent.requested_action!r} 的 capability"
        )
    if not intent.still_valid_for(
        candidate_digest=candidate_digest,
        policy_version=policy_version,
        scope=intent.scope,
        organization_id=intent.organization_id,
        project_id=intent.project_id,
        authorization_epoch=authorization_epoch,
        clock=clock,
    ):
        raise ApprovalIntentStale(
            "candidate digest / policy / scope / epoch 已变化 —— 必须创建新的 ApprovalIntent"
        )


def _assert_identity_shape(
    payload: dict[str, object], expected: frozenset[str], *, allow_extra: bool
) -> None:
    keys = frozenset(payload.keys())
    if keys != expected:
        extra = keys - expected
        missing = expected - keys
        detail = []
        if missing:
            detail.append(f"缺失 {sorted(missing)}")
        if extra:
            detail.append(f"多出 {sorted(extra)}")
        raise ValueError(
            "G-C0 authority identity 字段集合不符：" + "；".join(detail)
        )
    if not allow_extra:
        leaked = keys & GC0_FINALIZED_ONLY_FIELDS
        if leaked:
            raise ValueError(
                f"candidate 载荷不得携带 finalized-only 字段: {sorted(leaked)}"
            )
