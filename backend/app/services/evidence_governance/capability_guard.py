"""CapabilityGuard — 后端权威能力决策（Task 3.1, Wave 2）。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R5, R8, R12
Design: §3.1 信任边界, §2.2 Capability 基线, §7.2 稳定失败类别

后端 capability 判定是唯一真源（design §2.1）；前端只展示/隐藏/解释，不承担授权。
本 guard 是纯决策层（无 IO），基于冻结的 capability 矩阵
（``role_capability_contract``）判定 ``(actor_role, capability)``：

1. **矩阵权威**：``is_permitted`` 之外一律 deny-by-default。
2. **admin 不能绕过**：admin 仍受同一矩阵约束——scope（由 ProjectYearScopeGuard
   独立强制）、actor XOR（ActorContext 结构强制）、Legal Hold（``legal_hold_permits``
   对任何 actor 恒零效果）、人工确认（``ocr.confirm``/``ai.confirm`` 对 admin 亦是
   conditional「有目标编辑权时」而非 bypass）都不因 admin 而放开。
3. **Service Identity 禁止人工动作**：``SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES``
   （human-confirm / review-close / hold-release / QC-EQCR-complete / signoff）对
   service actor 恒 deny，先于矩阵判定。

拒绝统一抛 ``EvidenceGovernanceError(SCOPE_NOT_FOUND_OR_FORBIDDEN)``（脱敏，不泄露
目标/角色细节，与 not-found 同码，design §7.2）。
"""

from __future__ import annotations

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    EvidenceErrorCode,
    EvidenceGovernanceError,
)
from app.services.evidence_governance.role_capability_contract import (
    LEGAL_HOLD_PROTECTED_OPERATIONS,
    SERVICE_IDENTITY,
    SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES,
    is_permitted,
    legal_hold_permits,
)


class CapabilityGuard:
    """后端权威 capability 决策（纯函数式，无 IO）。"""

    def is_authorized(
        self,
        actor_role: str,
        capability: str,
        *,
        actor: ActorContext | None = None,
    ) -> bool:
        """返回 ``(actor_role, capability)`` 是否被允许（allowed/conditional）。

        - ``actor`` 为 service 时，先对 ``SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES``
          恒 deny（人工动作永不授予 Service Identity）。
        - 决策口径与矩阵单一真源一致；admin 不特权跳过。
        """
        role = self._effective_role(actor_role, actor)
        if role == SERVICE_IDENTITY and capability in SERVICE_IDENTITY_FORBIDDEN_CAPABILITIES:
            return False
        return is_permitted(role, capability)

    def authorize(
        self,
        actor_role: str,
        capability: str,
        *,
        actor: ActorContext | None = None,
    ) -> None:
        """能力不足时抛脱敏 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``（design §7.2）。"""
        if not self.is_authorized(actor_role, capability, actor=actor):
            raise EvidenceGovernanceError(
                EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
                "capability not permitted",
            )

    def authorize_destructive_under_hold(
        self,
        actor_role: str,
        operation: str,
        *,
        hold_active: bool,
        actor: ActorContext | None = None,
    ) -> None:
        """Legal Hold 生效时，delete/purge/overwrite 对任何 actor 恒零效果（R13/P26）。

        任何角色、admin、Service Identity 或紧急授权都无绕过通道
        （``legal_hold_permits`` 对受保护操作恒 False）。
        """
        if hold_active and operation in LEGAL_HOLD_PROTECTED_OPERATIONS:
            # 冗余显式：即便调用方传了 actor_role，legal_hold_permits 也对所有 actor 恒 False。
            if not legal_hold_permits(actor_role, operation):
                raise EvidenceGovernanceError(
                    EvidenceErrorCode.LEGAL_HOLD_ACTIVE,
                    "operation blocked by active legal hold",
                )

    @staticmethod
    def _effective_role(actor_role: str, actor: ActorContext | None) -> str:
        """ActorContext 为 service 时，能力行强制走 ``service`` 行（不信任传入 role）。"""
        if actor is not None and actor.is_service:
            return SERVICE_IDENTITY
        return actor_role
