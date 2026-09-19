"""Feature: attachment-ocr-ai-evidence-governance-hardening

Wave 0 / Task 1.4 — 跨项目 working-paper / attachment 关联否决基线 (create-time guard)。

本文件是 **契约冻结基线**（reference-model PBT），不是最终 EvidenceRefService 的实现测试。
它把 design §4.4「EvidenceRef 创建时的四项 create-time command guard」冻结为一个纯函数
参考模型 + 一个最小内存 store，用于在 Wave 3 (task 4.2) 真正实现 `EvidenceRefService`
之前锁定以下不可协商的 R3/R4 P0 不变量：

  1. 同 project / 同 year：源对象与目标对象必须属于同一 (project_id, audit_year)。
  2. 双端权限：调用者必须同时具备源端与目标端访问权。
  3. 脱敏错误：任何拒绝的错误载荷都不得泄露目标 client / project / path / 对象名称。
  4. 失败零部分写入：任一校验失败时，不得留下 ref / edge / 反向关系 / 审计-root 半成品。
  5. 四项校验只在「创建关联」时按需执行一次，**不建立持续轮询**——读取 / 影响查询
     不得重新触发这四项创建校验。

## 已实证的当前代码缺口（本基线锁定的目标契约尚未落地）

经 codegraph 实测，现有两条关联代码路径都不满足上述契约（Wave 3 修复）：

- `POST /api/attachments/{id}/associate` → `AttachmentService.associate_with_wp`
  只对「附件所在项目」做 `edit` 校验，**从不校验 wp_id 属于同一 project/year，也不做
  目标端权限**，且 `created_by` 未透传（匿名 link）。→ 跨项目关联可成功（P0 泄露）。
- `POST /api/projects/{pid}/workpapers/{wp}/evidence/link` → `WpEvidenceService.create_link`
  **无任何项目访问校验、无 scope 校验**，`created_by` 默认零 UUID（匿名）。

参考模型即这两条路径统一收敛后必须满足的行为规范。

Requirements: R3 (3.1, 3.2), R4 (4.1, 4.2), 4.3, 4.4
Properties: P1 (项目隔离), P6 (EvidenceRef 完整性), P8 (关联双向一致)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum

from hypothesis import given
from hypothesis import strategies as st


# ─────────────────────────────────────────────────────────────────────────────
# Reference model: create-time association guard (design §4.4)
# ─────────────────────────────────────────────────────────────────────────────


class GuardOutcome(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


# 唯一对外暴露的脱敏错误码（design §7.2）。拒绝时只允许暴露这一个码，
# 不区分「不存在」与「无权访问」，不携带目标元数据。
SCOPE_REDACTED_ERROR_CODE = "SCOPE_NOT_FOUND_OR_FORBIDDEN"
VERSION_CONFLICT_ERROR_CODE = "VERSION_CONFLICT"


@dataclass(frozen=True)
class Scope:
    """(project_id, audit_year) 复合 scope。"""

    project_id: str
    audit_year: int


@dataclass(frozen=True)
class Endpoint:
    """关联的一端（源或目标）。target 端携带敏感元数据仅用于验证脱敏。"""

    obj_type: str
    obj_id: str
    scope: Scope
    exists: bool = True
    deleted: bool = False
    version: int = 1
    content_hash: str = "h0"
    # 以下是「绝不能出现在错误里」的敏感字段
    client_name: str = ""
    file_path: str = ""
    object_name: str = ""


@dataclass(frozen=True)
class Actor:
    can_read_source: bool
    can_read_target: bool


@dataclass(frozen=True)
class AssociationCommand:
    source: Endpoint
    target: Endpoint
    actor: Actor
    expected_target_version: int
    expected_target_hash: str


@dataclass
class GuardError:
    error_code: str
    trace_id: str
    retryable: bool

    def serialized(self) -> str:
        return json.dumps(
            {"error_code": self.error_code, "trace_id": self.trace_id, "retryable": self.retryable}
        )


@dataclass
class GuardResult:
    outcome: GuardOutcome
    error: GuardError | None = None
    # 命中的失败原因（内部诊断用，不进入对外错误载荷）
    internal_reason: str | None = None


@dataclass
class AssociationStore:
    """最小内存 store，用于证明：失败零部分写入 + 四项校验仅创建时执行。"""

    edges: list[dict] = field(default_factory=list)
    # 反向索引：target_key -> [ref_id]，双向一致要求它与 edges 同生共灭
    reverse_index: dict[str, list[str]] = field(default_factory=dict)
    audit_roots: list[dict] = field(default_factory=list)
    # 四项 create-time 校验累计执行次数（证明「不持续轮询」）
    guard_invocations: int = 0

    # ── create-time command guard：四项校验按需执行一次 ──────────────────────
    def create_association(self, cmd: AssociationCommand) -> GuardResult:
        self.guard_invocations += 1
        res = _evaluate_create_time_guard(cmd)
        if res.outcome is GuardOutcome.ACCEPTED:
            ref_id = str(uuid.uuid4())
            tkey = f"{cmd.target.obj_type}:{cmd.target.obj_id}"
            self.edges.append(
                {
                    "ref_id": ref_id,
                    "source": f"{cmd.source.obj_type}:{cmd.source.obj_id}",
                    "target": tkey,
                    "project_id": cmd.source.scope.project_id,
                    "audit_year": cmd.source.scope.audit_year,
                    "target_version": cmd.target.version,
                    "target_hash": cmd.target.content_hash,
                }
            )
            self.reverse_index.setdefault(tkey, []).append(ref_id)
            self.audit_roots.append({"ref_id": ref_id, "command": "evidence_ref.create"})
        return res

    # ── 读取 / 影响查询：绝不重跑四项创建校验（无持续轮询） ────────────────────
    def read_edges_from_source(self, source_key: str) -> list[dict]:
        return [e for e in self.edges if e["source"] == source_key]

    def read_edges_from_target(self, target_key: str) -> list[dict]:
        return [e for e in self.edges if e["target"] == target_key]


def _evaluate_create_time_guard(cmd: AssociationCommand) -> GuardResult:
    """design §4.4 的四项 create-time 校验 + 目标存在/版本/hash/状态。

    任一校验失败一律返回同一脱敏错误码，不泄露目标元数据。
    """
    redacted = GuardError(SCOPE_REDACTED_ERROR_CODE, trace_id=str(uuid.uuid4()), retryable=False)

    # 校验 1：源 scope 有效（源对象可解析）
    if not cmd.source.exists or cmd.source.deleted:
        return GuardResult(GuardOutcome.REJECTED, redacted, "source_scope_invalid")
    # 校验 2：目标 scope 有效 + 与源同 project 同 year
    if not cmd.target.exists or cmd.target.deleted:
        return GuardResult(GuardOutcome.REJECTED, redacted, "target_missing_or_deleted")
    if cmd.source.scope != cmd.target.scope:
        return GuardResult(GuardOutcome.REJECTED, redacted, "cross_scope")
    # 校验 3：调用者源端权限
    if not cmd.actor.can_read_source:
        return GuardResult(GuardOutcome.REJECTED, redacted, "no_source_permission")
    # 校验 4：调用者目标端权限
    if not cmd.actor.can_read_target:
        return GuardResult(GuardOutcome.REJECTED, redacted, "no_target_permission")
    # 目标版本 / hash 匹配（P6 完整性）——版本冲突用独立稳定码，仍不泄露元数据
    if (
        cmd.expected_target_version != cmd.target.version
        or cmd.expected_target_hash != cmd.target.content_hash
    ):
        return GuardResult(
            GuardOutcome.REJECTED,
            GuardError(VERSION_CONFLICT_ERROR_CODE, trace_id=str(uuid.uuid4()), retryable=False),
            "version_or_hash_mismatch",
        )
    return GuardResult(GuardOutcome.ACCEPTED)


# ─────────────────────────────────────────────────────────────────────────────
# Hypothesis strategies
# ─────────────────────────────────────────────────────────────────────────────

_PROJECTS = ["proj-A", "proj-B", "proj-C"]
_YEARS = [2023, 2024, 2025]


@st.composite
def _scopes(draw) -> Scope:
    return Scope(project_id=draw(st.sampled_from(_PROJECTS)), audit_year=draw(st.sampled_from(_YEARS)))


@st.composite
def _endpoints(draw, scope: Scope | None = None, is_target: bool = False) -> Endpoint:
    sc = scope if scope is not None else draw(_scopes())
    kwargs = dict(
        obj_type=draw(st.sampled_from(["working_paper", "attachment_version"])),
        obj_id=str(draw(st.uuids())),
        scope=sc,
        exists=draw(st.booleans()),
        deleted=draw(st.booleans()),
        version=draw(st.integers(min_value=1, max_value=5)),
        content_hash=draw(st.sampled_from(["h0", "h1", "h2"])),
    )
    if is_target:
        # 目标端注入敏感元数据，用于脱敏断言
        kwargs.update(
            client_name=draw(st.sampled_from(["重庆医药集团", "SecretClientCo", "辽宁卫生"])),
            file_path=draw(st.sampled_from(["/srv/storage/secret/a.pdf", "C:/evidence/x.xlsx"])),
            object_name=draw(st.sampled_from(["审定表K5-1", "hidden-object-42"])),
        )
    return Endpoint(**kwargs)


@st.composite
def _commands(draw) -> AssociationCommand:
    src_scope = draw(_scopes())
    # 目标 scope 有一半概率与源相同，制造大量跨 scope 用例
    same = draw(st.booleans())
    tgt_scope = src_scope if same else draw(_scopes())
    source = draw(_endpoints(scope=src_scope))
    target = draw(_endpoints(scope=tgt_scope, is_target=True))
    actor = Actor(can_read_source=draw(st.booleans()), can_read_target=draw(st.booleans()))
    return AssociationCommand(
        source=source,
        target=target,
        actor=actor,
        expected_target_version=draw(st.integers(min_value=1, max_value=5)),
        expected_target_hash=draw(st.sampled_from(["h0", "h1", "h2"])),
    )


def _sensitive_tokens(cmd: AssociationCommand) -> list[str]:
    t = cmd.target
    return [
        tok
        for tok in (t.client_name, t.file_path, t.object_name, t.scope.project_id, str(t.scope.audit_year), t.obj_id)
        if tok
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Property tests — freeze R3/R4 create-time association contract
# ─────────────────────────────────────────────────────────────────────────────


@given(cmd=_commands())
def test_cross_scope_association_always_rejected(cmd: AssociationCommand):
    """P1 / R4.1 / R4.2：源与目标 scope（project 或 year）不一致时，关联必被否决。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 1
    """
    # 只关注两端都存在且有效、双端权限齐备但 scope 不同的情形，隔离出 scope 因素
    if cmd.source.scope == cmd.target.scope:
        return
    valid_cmd = AssociationCommand(
        source=Endpoint(**{**cmd.source.__dict__, "exists": True, "deleted": False}),
        target=Endpoint(**{**cmd.target.__dict__, "exists": True, "deleted": False}),
        actor=Actor(can_read_source=True, can_read_target=True),
        expected_target_version=cmd.target.version,
        expected_target_hash=cmd.target.content_hash,
    )
    store = AssociationStore()
    res = store.create_association(valid_cmd)
    assert res.outcome is GuardOutcome.REJECTED
    assert res.error is not None and res.error.error_code == SCOPE_REDACTED_ERROR_CODE
    # 零部分写入
    assert store.edges == []
    assert store.reverse_index == {}
    assert store.audit_roots == []


@given(cmd=_commands())
def test_both_endpoint_permission_required(cmd: AssociationCommand):
    """R4.1：合法关联要求调用者同时具备源端与目标端权限；缺任一端必被否决。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 6
    """
    # 构造 scope 一致、两端有效、版本/hash 匹配的命令，只让权限组合变化
    src = Endpoint(**{**cmd.source.__dict__, "exists": True, "deleted": False})
    tgt = Endpoint(
        **{
            **cmd.target.__dict__,
            "scope": src.scope,
            "exists": True,
            "deleted": False,
        }
    )
    base = dict(source=src, target=tgt, expected_target_version=tgt.version, expected_target_hash=tgt.content_hash)

    for can_src, can_tgt in [(True, True), (True, False), (False, True), (False, False)]:
        store = AssociationStore()
        res = store.create_association(
            AssociationCommand(actor=Actor(can_src, can_tgt), **base)
        )
        if can_src and can_tgt:
            assert res.outcome is GuardOutcome.ACCEPTED
            assert len(store.edges) == 1
        else:
            assert res.outcome is GuardOutcome.REJECTED
            assert res.error.error_code == SCOPE_REDACTED_ERROR_CODE
            assert store.edges == [] and store.reverse_index == {} and store.audit_roots == []


@given(cmd=_commands())
def test_rejection_error_is_redacted(cmd: AssociationCommand):
    """R4.2：任何拒绝错误都不得泄露目标 client / project / path / 对象名称 / 年度 / ID。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 1
    """
    store = AssociationStore()
    res = store.create_association(cmd)
    if res.outcome is GuardOutcome.REJECTED:
        payload = res.error.serialized()
        for token in _sensitive_tokens(cmd):
            assert token not in payload, f"error payload leaked sensitive token: {token!r}"


@given(cmd=_commands())
def test_failure_leaves_zero_partial_writes(cmd: AssociationCommand):
    """R3.2 / R4.2：任一校验失败时不得留下 ref / edge / 反向关系 / 审计-root 半成品。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 6
    """
    store = AssociationStore()
    res = store.create_association(cmd)
    if res.outcome is GuardOutcome.REJECTED:
        assert store.edges == []
        assert store.reverse_index == {}
        assert store.audit_roots == []
    else:
        # 成功时 edge 与反向关系严格成对出现（P8 双向一致的前置）
        assert len(store.edges) == 1
        assert sum(len(v) for v in store.reverse_index.values()) == 1
        assert len(store.audit_roots) == 1


@given(cmd=_commands())
def test_accepted_association_is_bidirectionally_consistent(cmd: AssociationCommand):
    """R4.3 / P8：合法关联从源端与目标端查询到同一 ref。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 8
    """
    src = Endpoint(**{**cmd.source.__dict__, "exists": True, "deleted": False})
    tgt = Endpoint(**{**cmd.target.__dict__, "scope": src.scope, "exists": True, "deleted": False})
    store = AssociationStore()
    res = store.create_association(
        AssociationCommand(
            source=src,
            target=tgt,
            actor=Actor(True, True),
            expected_target_version=tgt.version,
            expected_target_hash=tgt.content_hash,
        )
    )
    assert res.outcome is GuardOutcome.ACCEPTED
    src_key = f"{src.obj_type}:{src.obj_id}"
    tgt_key = f"{tgt.obj_type}:{tgt.obj_id}"
    from_source = store.read_edges_from_source(src_key)
    from_target = store.read_edges_from_target(tgt_key)
    assert len(from_source) == 1 and len(from_target) == 1
    assert from_source[0]["ref_id"] == from_target[0]["ref_id"]


@given(cmd=_commands())
def test_four_checks_run_only_at_creation_not_on_read(cmd: AssociationCommand):
    """R4 / design §4.4：四项校验只在创建关联时按需执行一次，读取/影响查询不重跑。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 1
    """
    store = AssociationStore()
    store.create_association(cmd)
    assert store.guard_invocations == 1, "create-time guard 必须恰好执行一次"

    # 大量读取 / 影响查询都不得重新触发四项创建校验（不建立持续轮询）
    for _ in range(25):
        store.read_edges_from_source("working_paper:none")
        store.read_edges_from_target("attachment_version:none")
    assert store.guard_invocations == 1, "读取/影响查询不得重跑四项创建校验（无持续轮询）"


@given(commands=st.lists(_commands(), min_size=1, max_size=8))
def test_guard_invocation_count_equals_create_attempts(commands: list[AssociationCommand]):
    """R12 / design §7.1：guard 执行次数恰等于创建尝试数（不因读取/轮询膨胀）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 25
    """
    store = AssociationStore()
    for c in commands:
        store.create_association(c)
        # 中途穿插读取，验证读取零 guard 消耗
        store.read_edges_from_source("x:y")
    assert store.guard_invocations == len(commands)
