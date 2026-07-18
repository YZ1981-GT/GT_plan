"""OnlyOffice/WOPI 编辑器令牌安全（Task 11 / 组件 C11 EditorSecurity）

Feature: procedure-delegation-visibility-isolation
Requirements:
  - 8.8/8.9：编辑器配置/文件读取/保存/回调/转换 与 OnlyOffice/WOPI 配置/读取/保存/回调/转换
    入口在读正文/副作用前经统一门独立判定。
  - 10.1：Token_Binding_Claims 完整且每个 claim 非空
    （sub, project_id, wp_id, sheet_name, wp_code, version, action, iat, exp, jti）。
  - 10.2：令牌签名校验通过。
  - 10.3：令牌过期校验通过。
  - 10.4：每个 claim 逐一绑定到 URL 参数与服务端解析资源。
  - 10.5：任一 claim 与 URL/服务端解析不一致 → 拒绝并记录 ``token_invalid``。
  - 10.6/10.7：callback 落盘前重新校验 Current_Version、Action_Matrix 与 claim ``action``。
  - 10.8：只读令牌请求写动作 → 拒绝写入。
  - 10.9：令牌 secret 或安全配置缺失 → fail-closed 拒绝（含 JWT disabled bypass）。
  - 10.10：从验收前冻结的安全配置读取有限正值 JWT_Lifetime。
  - 10.11：JWT_Lifetime 配置标识与值写入 Evidence_Manifest。
Design: 组件 C11 / "Lists, editor, coverage and frontend"（token 必含非空 claim；secret 缺失/
  disabled bypass/签名/过期/不一致 fail-closed；callback/PutFile 落盘前重校验版本/actor/action/
  Page_Visibility_Set/epoch；``UserCanWrite = gate allow ∩ file state ∩ lock``）/ Property 10/13。

本模块是纯函数 + JWT 编解码，无 DB / 无副作用；授权判定（角色/scope/grants/矩阵）仍由
``resolve_wp_binding_and_access()`` 承担。端点用本模块：
  1. 签发全 claim 有限时效令牌（``sign_editor_token``）；
  2. 全量校验令牌（``validate_editor_token``：签名 + 过期 + 非空 + jti + 逐 claim 绑定）；
  3. 组合写权限（``compute_user_can_write = gate allow ∩ file state ∩ lock``）；
  4. callback/PutFile 落盘前重校验版本/action（``verify_callback_preconditions``）。

**fail-closed 铁律（Req 10.9）**：``validate_editor_token`` 在 secret 缺失、JWT disabled、令牌为空、
签名错误、过期、任一必需 claim 缺失/为空、任一 claim 与服务端解析不一致、只读令牌请求写动作时，
一律返回 ``ok=False``。校验机制本身恒 fail-closed，与部署是否开启 enforce 无关。
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

__all__ = [
    "REQUIRED_EDITOR_CLAIMS",
    "BOUND_CLAIM_KEYS",
    "READ_ACTIONS",
    "WRITE_ACTIONS",
    "JWT_LIFETIME_CONFIG_ID",
    "frozen_jwt_lifetime_seconds",
    "EditorTokenResult",
    "sign_editor_token",
    "validate_editor_token",
    "claims_bound_to",
    "compute_user_can_write",
    "verify_callback_preconditions",
]

# 签名令牌必含且非空的 claim（Req 10.1）。
REQUIRED_EDITOR_CLAIMS: tuple[str, ...] = (
    "sub",
    "project_id",
    "wp_id",
    "sheet_name",
    "wp_code",
    "version",
    "action",
    "iat",
    "exp",
    "jti",
)

# 逐一绑定到 URL / 服务端解析资源的 claim（Req 10.4；sub/iat/exp/jti 不参与资源绑定，
# 但 sub/iat/exp/jti 仍须非空 + 参与签名/过期校验）。
BOUND_CLAIM_KEYS: tuple[str, ...] = (
    "project_id",
    "wp_id",
    "sheet_name",
    "wp_code",
    "version",
    "action",
)

# 只读动作（编辑器配置/文件读取）。写动作（保存/回调/PutFile/转换写）不在此集合。
READ_ACTIONS: frozenset[str] = frozenset({"editor_config", "editor_read", "view"})
WRITE_ACTIONS: frozenset[str] = frozenset(
    {"editor_write", "callback", "put_file", "convert_write"}
)

# 冻结 JWT_Lifetime 的配置标识符（Evidence_Manifest 记录用，Req 10.11）。
JWT_LIFETIME_CONFIG_ID = "ONLYOFFICE_JWT_LIFETIME_SECONDS"


def frozen_jwt_lifetime_seconds() -> int:
    """返回验收前冻结的有限正值 JWT_Lifetime（秒，Req 10.10）。

    从安全配置 ``settings.ONLYOFFICE_JWT_LIFETIME_SECONDS`` 读取（config 层 ``ge=1`` 保证正值）。
    """
    from app.core.config import settings

    value = int(getattr(settings, "ONLYOFFICE_JWT_LIFETIME_SECONDS", 900))
    # 兜底：非正值一律拒绝无限/非法配置（fail-closed 到最小 1s，绝不放行无限时效）。
    return value if value >= 1 else 1


@dataclass(frozen=True)
class EditorTokenResult:
    """编辑器令牌校验结果（不可变）。

    - ``ok``：全量校验通过（签名 + 过期 + 非空 + jti + 逐 claim 绑定 + 写权限）。
    - ``reason``：失败原因（供内部审计，对外统一 ``token_invalid`` → 404）。取值：
      ``secret_missing / jwt_disabled / token_missing / bad_signature / expired /
      missing_claim / empty_claim / claim_mismatch / readonly_token``。
    - ``claims``：解码后的 claim（校验失败时可能为空 dict）。
    """

    ok: bool
    reason: str | None = None
    claims: Mapping[str, Any] = field(default_factory=dict)


def sign_editor_token(
    *,
    secret: str,
    sub: str,
    project_id: str,
    wp_id: str,
    sheet_name: str,
    wp_code: str,
    version: str,
    action: str,
    jti: str | None = None,
    lifetime_seconds: int | None = None,
    now: int | None = None,
) -> str:
    """签发全 claim 有限时效编辑器令牌（HS256）。

    ``lifetime_seconds`` 缺省取冻结值 ``frozen_jwt_lifetime_seconds()``（Req 10.10）。
    ``jti`` 缺省生成随机 UUID（供防重放追踪）。secret 为空抛 ValueError（不产生无签名令牌，Req 10.9）。
    """
    if not (secret or "").strip():
        raise ValueError("editor token secret 缺失，拒绝签发无签名令牌（fail-closed）")
    iat = int(now if now is not None else time.time())
    ttl = int(lifetime_seconds if lifetime_seconds is not None else frozen_jwt_lifetime_seconds())
    if ttl < 1:
        ttl = frozen_jwt_lifetime_seconds()
    payload = {
        "sub": str(sub),
        "project_id": str(project_id),
        "wp_id": str(wp_id),
        "sheet_name": str(sheet_name),
        "wp_code": str(wp_code),
        "version": str(version),
        "action": str(action),
        "iat": iat,
        "exp": iat + ttl,
        "jti": jti or uuid.uuid4().hex,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def validate_editor_token(
    token: str | None,
    *,
    secret: str,
    expected: Mapping[str, Any],
    require_write: bool = False,
    now: int | None = None,
) -> EditorTokenResult:
    """全量校验签名编辑器令牌（Req 10.1–10.5, 10.8, 10.9；Property 13）。

    校验顺序（任一步失败 fail-closed）：
      1. secret 缺失 → ``secret_missing``（含 JWT disabled bypass，Req 10.9）。
      2. token 为空 → ``token_missing``。
      3. 签名 + 过期（jose 验签，exp 校验）→ ``bad_signature`` / ``expired``（Req 10.2/10.3）。
      4. 必需 claim 完整且非空（含 jti，Req 10.1）→ ``missing_claim`` / ``empty_claim``。
      5. 逐 claim 绑定到 URL/服务端解析（``expected``，Req 10.4/10.5）→ ``claim_mismatch``
         （覆盖跨资源重放：为资源 A 签发的令牌用于资源 B 时 wp_id/sheet 等不匹配）。
      6. 只读令牌请求写动作 → ``readonly_token``（Req 10.8）。

    ``expected`` 应包含服务端解析出的 ``project_id/wp_id/sheet_name/wp_code/version/action``
    （值转字符串比较）；缺省项跳过绑定校验，但已提供项必须一致。
    """
    if not (secret or "").strip():
        return EditorTokenResult(ok=False, reason="secret_missing")
    if not (token or "").strip():
        return EditorTokenResult(ok=False, reason="token_missing")

    tok = token.strip()
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()

    options = {"verify_exp": True, "verify_signature": True}
    decode_kwargs: dict[str, Any] = {"algorithms": ["HS256"], "options": options}
    if now is not None:
        # jose 支持通过 datetime 校验 exp/nbf；用 int 时间戳。
        decode_kwargs["options"]["leeway"] = 0
    try:
        claims = jwt.decode(tok, secret, **decode_kwargs)
    except ExpiredSignatureError:
        return EditorTokenResult(ok=False, reason="expired")
    except JWTError:
        return EditorTokenResult(ok=False, reason="bad_signature")
    except Exception:  # noqa: BLE001 — 任何解码异常 fail-closed
        return EditorTokenResult(ok=False, reason="bad_signature")

    # exp 显式再校验（当调用方传入固定 now，规避机器时钟依赖）。
    if now is not None:
        exp = claims.get("exp")
        try:
            if exp is None or int(exp) <= int(now):
                return EditorTokenResult(ok=False, reason="expired", claims=claims)
        except (TypeError, ValueError):
            return EditorTokenResult(ok=False, reason="empty_claim", claims=claims)

    # 必需 claim 完整且非空（Req 10.1）。
    for key in REQUIRED_EDITOR_CLAIMS:
        if key not in claims:
            return EditorTokenResult(ok=False, reason="missing_claim", claims=claims)
        val = claims.get(key)
        if val is None or str(val).strip() == "":
            return EditorTokenResult(ok=False, reason="empty_claim", claims=claims)

    # 逐 claim 绑定（Req 10.4/10.5；跨资源重放在此拦截）。
    if not claims_bound_to(claims, expected):
        return EditorTokenResult(ok=False, reason="claim_mismatch", claims=claims)

    # 只读令牌请求写动作（Req 10.8）。
    if require_write:
        action = str(claims.get("action") or "")
        if action in READ_ACTIONS:
            return EditorTokenResult(ok=False, reason="readonly_token", claims=claims)

    return EditorTokenResult(ok=True, reason=None, claims=claims)


def claims_bound_to(claims: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """逐 claim 与服务端解析值绑定校验（Req 10.4/10.5）。

    仅对 ``BOUND_CLAIM_KEYS`` 中且 ``expected`` 已提供的键做严格相等（字符串比较）。
    任一不一致返回 False（跨资源/跨动作重放拦截）。
    """
    for key in BOUND_CLAIM_KEYS:
        if key not in expected or expected.get(key) is None:
            continue
        exp_val = str(expected[key])
        claim_val = claims.get(key)
        if claim_val is None or str(claim_val) != exp_val:
            return False
    return True


def compute_user_can_write(
    *, gate_allow: bool, file_state_writable: bool, lock_ok: bool
) -> bool:
    """``UserCanWrite = gate allow ∩ file state ∩ lock``（Design C11）。

    三者全真才可写：门授权允许写、文件状态非归档/复核通过、锁未被他人持有。
    """
    return bool(gate_allow) and bool(file_state_writable) and bool(lock_ok)


def verify_callback_preconditions(
    *,
    claim_action: str | None,
    server_action: str,
    claim_version: str | None,
    current_version: str | None,
    gate_allow_write: bool,
    epoch_valid: bool = True,
) -> tuple[bool, str | None]:
    """callback/PutFile 落盘前重校验（Req 10.6/10.7/10.8）。

    返回 ``(ok, reason)``：全部通过 ``(True, None)``；否则 ``(False, reason)``：
      - ``version_conflict``：claim/current version 与 Current_Version 不一致（防旧版本覆盖）。
      - ``action_denied``：claim ``action`` 与服务端动作不一致，或非写动作。
      - ``readonly_token``：只读令牌请求写。
      - ``epoch_stale``：撤权后 policy epoch 失效（已撤权会话）。
      - ``not_delegated``：门不再授权写（撤权/越权）。
    """
    if not gate_allow_write:
        return False, "not_delegated"
    if not epoch_valid:
        return False, "epoch_stale"
    action = str(claim_action or "")
    if action in READ_ACTIONS:
        return False, "readonly_token"
    if claim_action is not None and server_action and action != server_action:
        return False, "action_denied"
    # Current_Version 重校验：claim 声明的版本必须等于当前生效版本（Req 10.6）。
    if claim_version is not None and current_version is not None:
        if str(claim_version) != str(current_version):
            return False, "version_conflict"
    return True, None
