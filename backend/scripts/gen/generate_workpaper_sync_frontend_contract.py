# -*- coding: utf-8 -*-
"""把 Task 28 router 与 workpaper_sync 域枚举投影成前端**唯一** contract 常量。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
Requirements: 3.1, 3.6, 3.7, 5.8, 11.2, 11.4, 11.5, 11.6, 11.11
Properties: **P10 / P11 / P47**（前端侧）

Usage from the repository root::

    py -3 backend/scripts/gen/generate_workpaper_sync_frontend_contract.py --check
    py -3 backend/scripts/gen/generate_workpaper_sync_frontend_contract.py --apply

═══ 为什么这些常量必须**生成**而不是手写 ═══

前端要知道四类事实：路由模板、哪些端点强制 `Idempotency-Key`、各状态机的封闭域、
以及 descriptor confirm 要逐项回传哪十项。四类的真源全在后端：

* 路由模板 —— `wp_sync_router.router.routes`（`USER_SYNC_PREFIX` 唯一拼接点）；
* `Idempotency-Key` 必填集 —— FastAPI 自己解出的 dependant（`field_info.is_required()`）；
* 状态封闭域 —— `workpaper_sync.models` 的 Enum 与 `TERMINAL_STATES`；
* confirm 回传项 —— `EditorLaunchDescriptor.confirm_payload()` 的**真实调用结果**。

手抄任一份的后果都是「静默漂移」：少一条路由 = 该端点前端永远打不到；
`Idempotency-Key` 少一个端点 = 复合幂等键最后一项恒空，同 participant 的两次
forcesave 折叠成一次；少一个 operation state = 该状态被前端当未知值 fail visible
（或更糟：被兜底成 `error`）；confirm 少回传一项 = 服务端逐项比对永远 409。
四种都不会有任何功能测试失败 —— 这正是本 spec 反复付过代价的形态。

═══ 刻意**不**投影的东西 ═══

* callback 路由（`public_router` 上的 `onlyoffice-callback`）—— 它是 DocServer 的
  服务凭证面，前端一旦拿到路径就可能去拼一个「自己造 callback」的调用；
  它同时被 `ResponseWrapperMiddleware` 排除包装，前端解包逻辑套上去必然错一层。
  另有反向判据钉住「生成物里不得出现这个路径」。
* `document.url` / 签名下载地址 —— descriptor 刻意不含（Task 25 / Task 28 的
  signature-TTL 论证）；前端只能用响应里的 `onlyoffice_config`，不得再请求 config。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, Final

_REPO = Path(__file__).resolve().parents[3]

if str(_REPO / "backend") not in sys.path:
    sys.path.insert(0, str(_REPO / "backend"))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from fastapi.dependencies.utils import get_dependant  # noqa: E402

from app.routers import wp_sync_router as _router_module  # noqa: E402
from app.services.workpaper_sync import models as _models  # noqa: E402
from app.services.workpaper_sync.definitions import AuthorityModel  # noqa: E402
from app.services.workpaper_sync.materialize_coordinator import (  # noqa: E402
    DESCRIPTOR_REQUIRED_FIELDS,
    MATERIALIZE_REJECTION_STATUS,
    DescriptorConfirmation,
    EditorLaunchDescriptor,
    PendingMutationReceipt,
)

_TARGET: Final[Path] = (
    _REPO
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "sync"
    / "workpaperSyncContract.generated.ts"
)

#: `Idempotency-Key` 的 header alias（router 用它做 `Header(..., alias=...)`）。
_IDEMPOTENCY_HEADER: Final[str] = "Idempotency-Key"

#: 需要投影到前端的状态机域。**逐个显式登记**而不是遍历 `models` 模块：
#: 自动遍历会把 delivery/candidate 之类纯服务端机器也投过去，前端拿到一堆没有
#: 消费方的常量 —— 那是本 spec 第一类假绿（additive 注入即死代码）。
#: 🔴 刻意**不含** `ParticipantState` / `ParticipantMode` / `RequestKind`：
#: 这 16 个端点没有任何一个返回 participant 的 state/mode（前端 DTO 因此只有
#: `participantId`），而 `kind` 是服务端专有 —— 客户端不得指定（`close_capture` 只能由
#: room arbiter 在锁内 CAS 提升）。投影它们等于给前端三个没有消费方的常量，
#: 那正是本模块开头列的第一类假绿。等哪天响应真带上了再加，同时才有判据可写。
_PROJECTED_ENUMS: Final[tuple[tuple[str, str], ...]] = (
    ("OperationState", "operation_states"),
    ("OperationShape", "operation_shapes"),
    ("RoomState", "room_states"),
    ("RecoveryCaseState", "recovery_case_states"),
    ("RecoveryReason", "recovery_reasons"),
)

#: 需要投影 terminal 集的状态机名（`TERMINAL_STATES` 的键）。
#:
#: 🔴 只有 `operation`：前端要用它判「还要不要继续等」。recovery case 的三实体规则
#: 是一份**人工裁决**（哪些状态必须三实体全空 / 全满），不能由 terminal 集派生 ——
#: `download_only` 是 terminal 而 `quarantined` 不是，但两者都必须三实体全空。
#: room 的 terminal 集目前无消费方，故不投影。
_PROJECTED_TERMINALS: Final[tuple[str, ...]] = ("operation",)

#: TS 侧的命名与发射形态（`facts` 键 → (常量名, 类型名, 形态)）。
#:
#: 形态两种：
#:
#: * ``const`` —— 发一个 `as const` 数组 + 由它派生的类型。前端**运行时**要拿它做封闭域
#:   校验（`member()`）时用这种。
#: * ``type`` —— 只发一个字面量联合类型。域在前端只用于**类型**约束、运行时无人读取时用
#:   这种：发一个没人读的数组就是 additive 死代码（本 spec 第一类假绿），而
#:   `test_no_domain_is_projected_without_a_frontend_consumer` 会打红。
#:   `operation_shapes` 属于此类 —— shape 由 `classifyOperationShape()` 从两个 link
#:   **派生**，服务端从不下发它，所以没有「校验收到的 shape」这回事。
_TS_NAMES: Final[dict[str, tuple[str, str, str]]] = {
    "operation_states": ("WP_SYNC_OPERATION_STATES", "WorkpaperSyncOperationState", "const"),
    "operation_shapes": ("WP_SYNC_OPERATION_SHAPES", "WorkpaperSyncOperationShape", "type"),
    "room_states": ("WP_SYNC_ROOM_STATES", "WorkpaperSyncRoomState", "const"),
    "recovery_case_states": (
        "WP_SYNC_RECOVERY_CASE_STATES",
        "WorkpaperSyncRecoveryCaseState",
        "const",
    ),
    "recovery_reasons": (
        "WP_SYNC_RECOVERY_REASONS",
        "WorkpaperSyncRecoveryReason",
        "const",
    ),
    "authority_models": (
        "WP_SYNC_AUTHORITY_MODELS",
        "WorkpaperSyncAuthorityModel",
        "const",
    ),
}


class ContractGenerationError(RuntimeError):
    """生成失败。**不吞**：静默降级会让整份 contract 变成空壳而前端全绿。"""


# ═══════════════════════════════════════════════════════════════════════════
# 1. 事实采集
# ═══════════════════════════════════════════════════════════════════════════


def _route_facts() -> tuple[str, list[dict[str, Any]]]:
    """从**真实** router 取路由模板与 `Idempotency-Key` 必填标志。

    `prefix_template` 去掉 `:path` 转换器后缀 —— 那是 Starlette 的语法，不是 URL 的
    一部分。前端按段拼 URL 时必须保留 `entry_id` 里的 `/`（186 条 entry_id 全部含 `/`，
    最深四段）；`encodeURIComponent` 会把它变成 `%2F`，Starlette 解出的
    `entry_id` 就不再等于原值。
    """
    prefix = str(_router_module.USER_SYNC_PREFIX)
    if "{entry_id:path}" not in prefix:
        raise ContractGenerationError(
            f"USER_SYNC_PREFIX={prefix!r} 的 entry 段不是 `:path` 转换器 —— "
            "默认转换器 `[^/]+` 下每一个端点在生产上恒 404"
        )
    prefix_template = prefix.replace("{entry_id:path}", "{entry_id}")

    routes: list[dict[str, Any]] = []
    for route in _router_module.router.routes:
        path = str(route.path)
        if not path.startswith(prefix):
            raise ContractGenerationError(
                f"{path!r} 不在显式 scope 前缀下 —— 缺 scope 段的端点必须从 "
                "room/operation 反推归属（AC 10.5 明令禁止）"
            )
        methods = sorted(m for m in route.methods if m not in ("HEAD", "OPTIONS"))
        if len(methods) != 1:
            raise ContractGenerationError(
                f"{path!r} 声明了 {methods} 个方法 —— 前端 contract 要求一路由一方法"
            )
        dependant = get_dependant(path=path, call=route.endpoint)
        required: bool | None = None
        for param in dependant.header_params:
            if str(getattr(param.field_info, "alias", "")) == _IDEMPOTENCY_HEADER:
                required = bool(param.field_info.is_required())
        routes.append(
            {
                "endpoint": route.endpoint.__name__,
                "method": methods[0],
                "suffix": path[len(prefix) :],
                # `None` = 该端点根本没声明这个 header；`False` = 声明成可选。
                # 两者都不是「必填」，但成因不同，投影时保留原样以便反向自检。
                "idempotency_key": (
                    "required"
                    if required is True
                    else ("optional" if required is False else "absent")
                ),
            }
        )
    if not routes:
        raise ContractGenerationError("router 一条路由都没解析出来")
    names = [r["endpoint"] for r in routes]
    if len(set(names)) != len(names):
        raise ContractGenerationError(f"endpoint 名重复：{names}")
    return prefix_template, sorted(routes, key=lambda r: r["endpoint"])


def _synthetic_descriptor() -> EditorLaunchDescriptor:
    """构造一个**合法**的 descriptor，用来真实调用 :meth:`confirm_payload`。

    🔴 为什么不 AST 扫那个方法体的 dict 字面量：AST 只能证明「源码里写了这些键」，
    而 confirm 的真实契约是「运行时回传了这些键」。真构造一次还顺手证明
    `assert_descriptor_mountable` 的判据与本生成器的期望值一致 —— 构造不出来就
    fail closed，而不是投影出一份没人能满足的 identity 清单。
    """
    digest = "a" * 64
    slot = {"type": "definition", "sha256": digest}
    return EditorLaunchDescriptor(
        operation_id=uuid.UUID(int=1),
        room_id=uuid.UUID(int=2),
        participant_id=uuid.UUID(int=3),
        doc_key="synthetic-doc-key",
        generation=1,
        server_applied_revision=1,
        client_confirmed_base_revision=1,
        content_version_id=uuid.UUID(int=4),
        representation_id=uuid.UUID(int=5),
        representation_generation=1,
        artifact_sha256=digest,
        write_fence_epoch=1,
        authority_model=AuthorityModel.projection_contract.value,
        authority_model_definition_sha256=digest,
        definition_bundle_id=uuid.UUID(int=6),
        definition_bundle_sha256=digest,
        definition_bundle_slots={
            "template": slot,
            "instrumentation": slot,
            "contract": slot,
        },
        document_type="xlsx",
        mode="edit",
        onlyoffice_config={"document": {"key": "synthetic-doc-key"}},
    )


def _synthetic_receipt() -> PendingMutationReceipt:
    """`POST .../pending-mutations` 的响应 DTO —— 键集从 :meth:`as_dict` 真调一次取。"""
    from datetime import datetime, timezone

    return PendingMutationReceipt(
        pending_mutation_id=uuid.UUID(int=7),
        pending_mutation_token="synthetic-token",
        expected_revision=1,
        payload_sha256="b" * 64,
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        idempotency_key="synthetic-key",
        replayed=False,
    )


def _synthetic_confirmation() -> DescriptorConfirmation:
    """`POST .../confirm-descriptor` 的响应 DTO。"""
    return DescriptorConfirmation(
        confirmation_id=uuid.UUID(int=8),
        room_id=uuid.UUID(int=2),
        participant_id=uuid.UUID(int=3),
        generation=1,
        representation_id=uuid.UUID(int=5),
        content_version_id=uuid.UUID(int=4),
        room_state="active",
        replayed=False,
        forcesave_unlocked=True,
    )


def collect_facts() -> dict[str, Any]:
    prefix_template, routes = _route_facts()
    descriptor = _synthetic_descriptor()

    facts: dict[str, Any] = {
        "prefix_template": prefix_template,
        "routes": routes,
        "idempotent_endpoints": sorted(
            r["endpoint"] for r in routes if r["idempotency_key"] == "required"
        ),
        "descriptor_fields": list(DESCRIPTOR_REQUIRED_FIELDS),
        "descriptor_confirm_keys": sorted(descriptor.confirm_payload()),
        # 下面三组响应键集**不投影到前端**（前端没有消费方），但进 `facts` 与 digest ——
        # 后端判据靠它们锁死「flush 回执不得泄露 revision 结果」「confirm 回传项必须能
        # 从 descriptor 响应取到」「confirm 响应必须带 forcesave 门」。
        "descriptor_response_keys": sorted(descriptor.as_dict()),
        "pending_mutation_receipt_keys": sorted(_synthetic_receipt().as_dict()),
        "descriptor_confirmation_keys": sorted(_synthetic_confirmation().as_dict()),
        "authority_models": [m.value for m in AuthorityModel],
        "rejection_status": {
            str(exc.error_code): int(status)
            for exc, status in sorted(
                MATERIALIZE_REJECTION_STATUS.items(), key=lambda kv: kv[0].__name__
            )
        },
    }
    for enum_name, key in _PROJECTED_ENUMS:
        enum = getattr(_models, enum_name, None)
        if enum is None:
            raise ContractGenerationError(f"models 里没有枚举 {enum_name}")
        facts[key] = [member.value for member in enum]
    for machine in _PROJECTED_TERMINALS:
        terminals = _models.TERMINAL_STATES.get(machine)
        if not terminals:
            raise ContractGenerationError(
                f"TERMINAL_STATES 里没有 {machine!r} 或它是空集 —— "
                "空 terminal 集会让前端永远等不到终态"
            )
        facts[f"{machine}_terminal_states"] = sorted(s.value for s in terminals)

    for code, status in facts["rejection_status"].items():
        if not code.strip():
            raise ContractGenerationError("拒绝映射里存在空 error_code")
        if status not in (403, 404, 409, 422, 500):
            raise ContractGenerationError(
                f"error_code={code!r} 映射到未登记状态码 {status}"
            )
    facts["contract_digest"] = _digest(facts)
    return facts


def _digest(facts: dict[str, Any]) -> str:
    payload = {k: v for k, v in facts.items() if k != "contract_digest"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 2. 渲染
# ═══════════════════════════════════════════════════════════════════════════


def _ts_json(value: Any, indent: int = 0) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    if indent:
        pad = " " * indent
        text = "\n".join(
            (pad + line if index else line) for index, line in enumerate(text.splitlines())
        )
    return text


def _closed_domain_block(key: str, facts: dict[str, Any]) -> str:
    const_name, type_name, emit = _TS_NAMES[key]
    if emit == "type":
        union = " | ".join(json.dumps(value) for value in facts[key])
        return (
            f"/** 封闭域只作类型约束（运行时由派生逻辑保证），故不发数组常量。 */\n"
            f"export type {type_name} = {union}"
        )
    return "\n".join(
        [
            f"export const {const_name} = {_ts_json(facts[key])} as const",
            f"export type {type_name} = (typeof {const_name})[number]",
        ]
    )


def render(facts: dict[str, Any]) -> str:
    domains = "\n\n".join(_closed_domain_block(key, facts) for key in _TS_NAMES)
    return f'''/**
 * 本文件由 `backend/scripts/gen/generate_workpaper_sync_frontend_contract.py` 生成，请勿手工编辑。
 *
 * 真源：`backend/app/routers/wp_sync_router.py`（路由模板 + Idempotency-Key 必填集）、
 * `backend/app/services/workpaper_sync/models.py`（状态机封闭域与 terminal 集）、
 * `EditorLaunchDescriptor.confirm_payload()`（confirm 逐项回传清单）、
 * `MATERIALIZE_REJECTION_STATUS`（error_code → HTTP 状态码）。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
 */

export const WP_SYNC_CONTRACT_DIGEST = {json.dumps(facts["contract_digest"])}

/**
 * 用户端统一前缀模板。`{{entry_id}}` 是**多段**值（186 条 entry_id 全部含 `/`，最深四段），
 * 路由用 Starlette 的 `:path` 转换器接收；拼 URL 时不得 percent-encode 其中的 `/`。
 */
export const WP_SYNC_USER_PREFIX_TEMPLATE = {json.dumps(facts["prefix_template"])}

export interface WorkpaperSyncRouteSpec {{
  readonly endpoint: string
  readonly method: 'GET' | 'POST'
  readonly suffix: string
  readonly idempotencyKey: 'required' | 'optional' | 'absent'
}}

/** 后端**真实**路由表（一路由一方法）。前端只能从这里取路径，不得再拼字面量。 */
export const WP_SYNC_ROUTES = {_ts_json([
    {
        "endpoint": r["endpoint"],
        "method": r["method"],
        "idempotencyKey": r["idempotency_key"],
        "suffix": r["suffix"],
    }
    for r in facts["routes"]
])} as const satisfies readonly WorkpaperSyncRouteSpec[]

/** 服务端**强制**携带 `Idempotency-Key` 的端点（缺 key 时复合幂等键最后一项恒空）。 */
export const WP_SYNC_IDEMPOTENT_ENDPOINTS = {_ts_json(facts["idempotent_endpoints"])} as const

/** descriptor 必备字段（缺任一项都不得挂载 DocEditor）。 */
export const WP_SYNC_DESCRIPTOR_FIELDS = {_ts_json(facts["descriptor_fields"])} as const

/** `onDocumentReady` 之后 confirm-descriptor 必须**逐项**回传的 identity。 */
export const WP_SYNC_DESCRIPTOR_CONFIRM_KEYS = {_ts_json(facts["descriptor_confirm_keys"])} as const

{domains}

/**
 * operation 的 terminal 状态（出边为空）。前端用它判「还要不要继续等」。
 * `error` **不在**其中 —— 它可重试（AC 5.8）。
 */
export const WP_SYNC_OPERATION_TERMINAL_STATES = {_ts_json(facts["operation_terminal_states"])} as const

/**
 * 服务端 `error_code` → HTTP 状态码的**唯一**映射（`classify_materialize_rejection`）。
 * 未登记的 error_code 一律 fail visible，不得兜底成 4xx。
 */
export const WP_SYNC_REJECTION_STATUS: Readonly<Record<string, number>> = {_ts_json(facts["rejection_status"])} as const
'''


# ═══════════════════════════════════════════════════════════════════════════
# 3. CLI
# ═══════════════════════════════════════════════════════════════════════════


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _print_stats(label: str, facts: dict[str, Any]) -> None:
    print(
        f"[{label}] routes={len(facts['routes'])} "
        f"idempotent={len(facts['idempotent_endpoints'])} "
        f"operation_states={len(facts['operation_states'])} "
        f"recovery_states={len(facts['recovery_case_states'])} "
        f"confirm_keys={len(facts['descriptor_confirm_keys'])} "
        f"rejections={len(facts['rejection_status'])}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the generated artifact")
    mode.add_argument("--apply", action="store_true", help="atomically regenerate it")
    args = parser.parse_args(argv)

    facts = collect_facts()
    content = render(facts)
    _print_stats("SOURCE", facts)

    if args.check:
        if not _TARGET.is_file():
            print(f"[FAIL] missing: {_TARGET.relative_to(_REPO)}")
            return 2
        if _TARGET.read_text(encoding="utf-8") != content:
            print(f"[FAIL] stale: {_TARGET.relative_to(_REPO)}")
            print("       run: py -3 backend/scripts/gen/"
                  "generate_workpaper_sync_frontend_contract.py --apply")
            return 2
        print(f"[OK] contract digest {facts['contract_digest']}")
        return 0

    _atomic_write(_TARGET, content)
    print(f"[APPLIED] {_TARGET.relative_to(_REPO)}")
    print(f"[OK] contract digest {facts['contract_digest']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractGenerationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
