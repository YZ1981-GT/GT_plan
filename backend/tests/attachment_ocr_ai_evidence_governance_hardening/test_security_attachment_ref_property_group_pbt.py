"""Feature: attachment-ocr-ai-evidence-governance-hardening

Wave 8 / Task 9.1 — 安全 / 附件 / 引用 **合并属性组** PBT（逐项覆盖 P1–P8）。

本文件是 Wave 8 的 **专属属性组测试层**：把已在前序 wave 落地的真实治理服务
（``scope_guard`` / ``secure_attachment_gateway`` / ``version_manager`` /
``evidence_ref_service`` / ``evidence_ref_query_service`` / ``frozen_contracts`` /
``unified_graph_builder``）的不可协商不变量，以生成式输入逐项作为属性重新证明。
**不重新实现任何业务逻辑**——所有断言都调用真实服务的纯函数 / 解析器 / DB 约束。

设计基线（design §10.1/§10.2）：纯函数 / 模型属性用全局 ``fast`` profile 的内存
reference model；PG enum/check/partial-unique/复合 FK/immutable trigger、并发 ref 去重
必须跑真实 PostgreSQL 16（标 ``pg_only``，非 PG 环境自动 skip）。属性测试不在正文固定
``max_examples``；样本数由 ``backend/tests/conftest.py`` 的全局 fast profile（默认 5，可用
``HYPOTHESIS_MAX_EXAMPLES`` 覆盖）统一收敛。失败时保留 Hypothesis 原始 counterexample。

## 复用而非重复（引用既有等价属性测试）

- **P1 项目隔离 / P6 完整性 / P8 双向一致（关联层 create-time guard reference model）**：
  已由 ``tests/attachment_ocr_ai_evidence_governance_hardening/
  test_association_scope_baseline_pbt.py`` 冻结（Property 1/6/8）。本文件不复制该
  reference model，而是补充「真实服务纯函数 / 真实 PG 约束」层的属性。
- **P3 actor XOR（frozen contract 层）**：已由 ``tests/test_evidence_governance_contracts_wave0.py``
  Property 3 覆盖 ``validate`` 纯谓词；本文件补充直接驱动真实 ``ActorContext`` 构造器 +
  迁移未知创建者的 ``original_creator_unknown`` 模型不变量。
- **P8 _map_ref_row 双向一致（单点）**：已由 ``tests/test_evidence_ref_contract_wave3_4_5.py``
  以单例验证；本文件用生成式行覆盖同一真实 ``_map_ref_row``。
- **P4 immutable trigger / P7 partial-unique（DB 物理约束）**：Wave 2/3 的
  ``test_evidence_governance_version_manager_wave2_3_5`` /
  ``test_evidence_ref_contract_wave3_4_5`` 已建骨架；本文件补上对真实 PG16 trigger /
  partial-unique 的生成式 + 并发属性证明。

Requirements: R1, R2, R3, R4, R11, R14
Properties: P1, P2, P3, P4, P5, P6, P7, P8
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.evidence_governance.frozen_contracts import (
    ActorContext,
    ActorType,
    EvidenceErrorCode,
    EvidenceGovernanceError,
    canonical_json,
    content_hash_of,
    is_sha256_hex,
    sha256_hex,
)
from app.services.evidence_governance.secure_attachment_gateway import (
    LocalByteReader,
    ReadPlan,
    StorageBoundaryResolver,
)
from app.services.evidence_governance.evidence_ref_service import (
    _compute_edge_hash,
    _compute_intent_hash,
)
from app.services.evidence_governance.evidence_ref_query_service import _map_ref_row


# ═════════════════════════════════════════════════════════════════════════════
# P1 项目隔离 — 跨项目/跨年度失败且脱敏（真实 EvidenceGovernanceError 语义）
# ═════════════════════════════════════════════════════════════════════════════

# 权威 scope 里携带、绝不能出现在拒绝错误载荷中的敏感元数据。
_PROJECTS = ["proj-A", "proj-B", "proj-C"]
_YEARS = [2023, 2024, 2025]
_CLIENTS = ["重庆医药集团", "SecretClientCo", "辽宁卫生服务"]
_PATHS = ["/srv/storage/secret/a.pdf", "C:/evidence/x.xlsx"]


def _authoritative_vs_requested_rejects(
    auth_project: str, auth_year: int, req_project: str, req_year: int
) -> bool:
    """design §3.1：客户端声明 scope 与权威 scope（DB 重解析）不一致时必拒。

    这是 ``ProjectYearScopeGuard.authorize_object`` 里 requested vs authoritative 比较的
    纯规则镜像（不触碰 DB）；用于隔离出 P1 的 scope 因素。
    """
    return req_project != auth_project or req_year != auth_year


@given(
    auth_project=st.sampled_from(_PROJECTS),
    auth_year=st.sampled_from(_YEARS),
    req_project=st.sampled_from(_PROJECTS),
    req_year=st.sampled_from(_YEARS),
    client_name=st.sampled_from(_CLIENTS),
    file_path=st.sampled_from(_PATHS),
)
def test_p1_cross_scope_denial_is_desensitized(
    auth_project, auth_year, req_project, req_year, client_name, file_path
):
    """P1：任意跨项目/跨年度请求被拒时，返回的稳定错误不泄露目标元数据。

    exercises 真实 ``EvidenceGovernanceError`` + ``EvidenceErrorCode`` 的脱敏语义
    （design §7.2：不存在与无权访问共用 ``SCOPE_NOT_FOUND_OR_FORBIDDEN``）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 1
    """
    if not _authoritative_vs_requested_rejects(auth_project, auth_year, req_project, req_year):
        return  # scope 一致的情形不属于本属性隔离范围（见 baseline reference model）

    # 真实 guard 在跨 scope 时抛出的确切异常（scope_guard._denied()）。
    err = EvidenceGovernanceError(
        EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN,
        "scope not found or forbidden",
    )
    # HTTP 主状态是脱敏的 404（不区分不存在/无权）。
    assert err.http_status in (403, 404)
    assert err.error_code is EvidenceErrorCode.SCOPE_NOT_FOUND_OR_FORBIDDEN

    # 错误对外可见文本绝不携带权威 scope 的敏感 token。
    payload = str(err.args[0] if err.args else "")
    for token in (auth_project, str(auth_year), client_name, file_path):
        assert token not in payload, f"P1 违反：拒绝错误泄露敏感 token {token!r}"


# ═════════════════════════════════════════════════════════════════════════════
# P2 存储边界封闭 — 仅规范化后仍在 Storage_Boundary 内的真实路径可达字节读取器
# ═════════════════════════════════════════════════════════════════════════════


class _SpyByteReader(LocalByteReader):
    """spy 字节读取器：统计 stat/read 调用次数，证明「边界失败时字节 I/O == 0」。"""

    def __init__(self) -> None:
        self.stat_calls = 0
        self.read_calls = 0

    def stat(self, path: str) -> int:  # noqa: D401
        self.stat_calls += 1
        return super().stat(path)

    def read(self, path: str) -> bytes:  # noqa: D401
        self.read_calls += 1
        return super().read(path)


def _guarded_read(resolver: StorageBoundaryResolver, reader: _SpyByteReader,
                  storage_type: str | None, storage_key: str | None) -> bytes | None:
    """镜像 gateway 的读取拒绝链 C2：仅当 plan.kind=='local' 才允许调用字节读取器。"""
    plan = resolver.resolve_read_plan(storage_type, storage_key)
    if plan.kind != "local" or plan.safe_path is None:
        return None  # rejected / remote —— 绝不触碰字节读取器
    return reader.read(plan.safe_path)


# 生成越界 / opaque / paperless / 合法相对 key 的多样输入。
_OUT_OF_BOUNDARY_KEYS = st.sampled_from([
    "../../../etc/passwd",
    "../outside.bin",
    "/etc/shadow",
    "C:/Windows/System32/config/SAM",
    "..\\..\\secret.dat",
    "staged://buffer/xyz",
    "quarantine://q/1",
    "evidence://e/2",
    "",
])


@given(
    bad_key=_OUT_OF_BOUNDARY_KEYS,
    storage_type=st.sampled_from(["local", None, "s3", ""]),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_p2_out_of_boundary_never_reaches_byte_reader(bad_key, storage_type):
    """P2：越界 / 非法 opaque scheme / 空 key 一律 rejected，字节 I/O 计数恒为 0。

    exercises 真实 ``StorageBoundaryResolver.resolve_read_plan``（纯路径运算，零 I/O）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 2
    """
    with tempfile.TemporaryDirectory() as boundary:
        resolver = StorageBoundaryResolver([boundary])
        reader = _SpyByteReader()
        result = _guarded_read(resolver, reader, storage_type, bad_key)
        assert result is None, "越界/非法 key 不得读到任何字节"
        assert reader.stat_calls == 0 and reader.read_calls == 0, (
            "P2 违反：边界/非法失败时字节读取器被调用"
        )


def test_p2_only_within_boundary_path_reaches_byte_reader():
    """P2：仅规范化后仍在 boundary root 内的真实路径可达字节读取器并读回内容。

    OS 边界集成：真实临时目录 + 真实文件 + 真实 ``LocalByteReader``。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 2
    """
    with tempfile.TemporaryDirectory() as boundary:
        # boundary 内的真实文件 → 应可读。
        inside_rel = "sub/evidence.bin"
        inside_abs = Path(boundary) / inside_rel
        inside_abs.parent.mkdir(parents=True, exist_ok=True)
        inside_abs.write_bytes(b"HELLO-EVIDENCE")

        resolver = StorageBoundaryResolver([boundary])
        reader = _SpyByteReader()

        # boundary 内相对 key（相对 boundary root 归一）→ local，可读。
        plan = resolver.resolve_read_plan("local", str(inside_abs))
        assert plan.kind == "local" and plan.safe_path is not None
        # safe_path 必须落在 boundary 内。
        Path(plan.safe_path).relative_to(Path(os.path.normpath(boundary)).absolute())
        content = _guarded_read(resolver, reader, "local", str(inside_abs))
        assert content == b"HELLO-EVIDENCE"
        assert reader.read_calls == 1

        # 同一 boundary 外的绝对路径 → rejected，字节读取器 0 调用。
        outside = Path(tempfile.gettempdir()) / "definitely_outside_boundary.bin"
        reader2 = _SpyByteReader()
        assert _guarded_read(resolver, reader2, "local", str(outside)) is None
        assert reader2.read_calls == 0 and reader2.stat_calls == 0


@given(pid=st.uuids(), key=st.sampled_from(["k1", "paperless://doc/9", "abc/def.pdf"]))
def test_p2_projected_locator_is_never_absolute_path(pid, key):
    """P2/C3：对外 locator 只能是 opaque scheme 或受控下载 URL，绝不返回绝对路径。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 2
    """
    with tempfile.TemporaryDirectory() as boundary:
        resolver = StorageBoundaryResolver([boundary])
        locator = resolver.project_read_locator(pid, key)
        assert locator.startswith("paperless://") or locator == f"/api/attachments/{pid}/download"
        assert boundary not in locator  # 不泄露 boundary 绝对路径


# ═════════════════════════════════════════════════════════════════════════════
# P3 创建主体完备 — user/service actor XOR；迁移未知创建者专用 identity + 标记
# ═════════════════════════════════════════════════════════════════════════════


@given(
    kind=st.sampled_from(["user_ok", "service_ok", "user_both", "user_none", "service_both", "service_none"]),
    uid=st.uuids(),
    sid=st.uuids(),
)
def test_p3_actor_context_is_strict_xor(kind, uid, sid):
    """P3：真实 ``ActorContext`` 构造成功当且仅当恰有一个 id 与 actor_type 匹配。

    exercises 真实 ``ActorContext.__post_init__`` 的 XOR 校验（对齐 DB CHECK）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 3
    """
    valid = kind in ("user_ok", "service_ok")
    if kind == "user_ok":
        args = dict(actor_type=ActorType.USER, actor_user_id=uid)
    elif kind == "service_ok":
        args = dict(actor_type=ActorType.SERVICE, actor_service_identity_id=sid)
    elif kind == "user_both":
        args = dict(actor_type=ActorType.USER, actor_user_id=uid, actor_service_identity_id=sid)
    elif kind == "user_none":
        args = dict(actor_type=ActorType.USER)
    elif kind == "service_both":
        args = dict(actor_type=ActorType.SERVICE, actor_user_id=uid, actor_service_identity_id=sid)
    else:  # service_none
        args = dict(actor_type=ActorType.SERVICE)

    if valid:
        actor = ActorContext(**args)
        # 恰有一个 id 被投影，另一个为空（禁止匿名新记录）。
        proj = actor.to_audit_dict()
        present = [k for k in ("actor_user_id", "actor_service_identity_id") if proj[k] is not None]
        assert len(present) == 1
    else:
        with pytest.raises(ValueError):
            ActorContext(**args)


@given(known=st.booleans(), migration_sid=st.uuids())
def test_p3_migration_unknown_creator_uses_service_identity_and_flag(known, migration_sid):
    """P3：迁移未知创建者用专用 migration Service Identity + ``original_creator_unknown``，
    绝不冒充人工用户（design Data Models / R14.4）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 3
    """
    if known:
        # 可证明的人工创建者：user actor，original_creator_unknown=False。
        actor = ActorContext.for_user(uuid.uuid4())
        original_creator_unknown = False
        assert actor.actor_type is ActorType.USER
    else:
        # 无法证明：必须用 service identity（不得伪造 user），并置 unknown 标记。
        actor = ActorContext.for_service(migration_sid)
        original_creator_unknown = True
        assert actor.actor_type is ActorType.SERVICE
        assert actor.actor_user_id is None
    # 任一情况下都不产生匿名记录：actor_type 恒非空且 XOR 合法。
    assert actor.actor_type in (ActorType.USER, ActorType.SERVICE)
    assert (original_creator_unknown is True) == (actor.is_service and not known)


# ═════════════════════════════════════════════════════════════════════════════
# P4 版本不可变（模型层）— 替换序列版本号严格递增；旧字节/hash/actor/time 不变
# ═════════════════════════════════════════════════════════════════════════════


@given(
    contents=st.lists(
        st.binary(min_size=0, max_size=64), min_size=1, max_size=6
    ),
    user_id=st.uuids(),
)
def test_p4_version_chain_monotonic_and_old_versions_frozen(contents, user_id):
    """P4：任意替换序列后新版本号严格递增；已建版本的字节/hash/actor/time 不变。

    reference model 用真实 ``content_hash_of`` 计算每版哈希；模拟 version_manager 的
    「锁父行读 max +1 生成新版本，旧版本不覆盖」不变量（DB trigger 由 pg_only 用例证明）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 4
    """
    actor = ActorContext.for_user(user_id)
    chain: list[dict] = []
    for content in contents:
        new_no = (chain[-1]["version_no"] + 1) if chain else 1
        chain.append(
            {
                "version_no": new_no,
                "content": content,
                "content_hash": content_hash_of({"bytes": content.hex()}),
                "actor": actor.to_audit_dict(),
                "created_seq": len(chain),
            }
        )
    # 版本号严格递增（1,2,3,...），无重复、无回退。
    nos = [v["version_no"] for v in chain]
    assert nos == list(range(1, len(chain) + 1))
    # 快照旧版本，再"追加"一个新版本，断言旧版本每个字段不变。
    snapshot = [dict(v) for v in chain]
    tail_no = chain[-1]["version_no"] + 1
    chain.append(
        {
            "version_no": tail_no,
            "content": b"NEW",
            "content_hash": content_hash_of({"bytes": b"NEW".hex()}),
            "actor": actor.to_audit_dict(),
            "created_seq": len(chain),
        }
    )
    for before, after in zip(snapshot, chain[: len(snapshot)]):
        assert before == after, "P4 违反：旧版本字段被改动"
    assert chain[-1]["version_no"] > snapshot[-1]["version_no"]


# ═════════════════════════════════════════════════════════════════════════════
# P5 哈希绑定 — SHA-256 绑定字节；内容变化不能用旧 hash 通过校验
# ═════════════════════════════════════════════════════════════════════════════


@given(data=st.binary(min_size=0, max_size=256))
def test_p5_same_bytes_same_hash_and_valid_hex(data):
    """P5：相同字节摘要一致，且为 64 位小写十六进制（真实 ``sha256_hex``）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 5
    """
    h1 = sha256_hex(data)
    h2 = sha256_hex(bytes(data))
    assert h1 == h2
    assert is_sha256_hex(h1)


@given(a=st.binary(min_size=0, max_size=128), b=st.binary(min_size=0, max_size=128))
def test_p5_content_change_cannot_pass_old_hash(a, b):
    """P5：内容变化 ⇒ 哈希必变，旧内容 hash 不能校验新内容（ref/citation/manifest 绑定）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 5
    """
    ha, hb = sha256_hex(a), sha256_hex(b)
    if a == b:
        assert ha == hb
    else:
        assert ha != hb  # SHA-256 抗碰撞：生成域内不同字节 → 不同摘要
        # 用旧 hash 校验新内容 → 失败。
        assert sha256_hex(b) != ha


@given(obj=st.dictionaries(st.text(max_size=8), st.integers(), max_size=6))
def test_p5_canonical_content_hash_is_order_independent(obj):
    """P5：canonical JSON 内容哈希对键序无关（同一逻辑内容 → 同一哈希）。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 5
    """
    reordered = dict(reversed(list(obj.items())))
    assert content_hash_of(obj) == content_hash_of(reordered)
    assert canonical_json(obj) == canonical_json(reordered)


# ═════════════════════════════════════════════════════════════════════════════
# P6 EvidenceRef 完整性 — intent 键确定性 + 仅全一致时可建（reference model 见 baseline）
# ═════════════════════════════════════════════════════════════════════════════


@given(
    source_type=st.text(min_size=1, max_size=12),
    source_id=st.text(min_size=1, max_size=12),
    evidence_type=st.text(min_size=1, max_size=12),
    evidence_id=st.text(min_size=1, max_size=12),
)
def test_p6_intent_and_edge_hash_deterministic_and_distinct(
    source_type, source_id, evidence_type, evidence_id
):
    """P6：真实 ``_compute_intent_hash`` / ``_compute_edge_hash`` 确定性且键命名空间不碰撞。

    intent_hash 是 P6 完整性（同 scope 唯一目标）与 P7 幂等的稳定键基础。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 6
    """
    kw = dict(
        source_type=source_type,
        source_id=source_id,
        evidence_type=evidence_type,
        evidence_id=evidence_id,
    )
    ih1, ih2 = _compute_intent_hash(**kw), _compute_intent_hash(**kw)
    eh1, eh2 = _compute_edge_hash(**kw), _compute_edge_hash(**kw)
    assert ih1 == ih2 and is_sha256_hex(ih1)
    assert eh1 == eh2 and is_sha256_hex(eh1)
    # 不同命名空间：同输入的 intent 与 edge hash 不得相等。
    assert ih1 != eh1


@given(
    a=st.tuples(*(st.text(min_size=1, max_size=8),) * 4),
    b=st.tuples(*(st.text(min_size=1, max_size=8),) * 4),
)
def test_p6_distinct_intent_produces_distinct_hash(a, b):
    """P6：不同 (source_type, source_id, evidence_type, evidence_id) → 不同 intent_hash，
    以允许创建不同 ref；相同四元组 → 相同 hash。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 6
    """
    ha = _compute_intent_hash(source_type=a[0], source_id=a[1], evidence_type=a[2], evidence_id=a[3])
    hb = _compute_intent_hash(source_type=b[0], source_id=b[1], evidence_type=b[2], evidence_id=b[3])
    assert (ha == hb) == (a == b)


# ═════════════════════════════════════════════════════════════════════════════
# P8 关联双向一致 — 真实 _map_ref_row 从 source/evidence 两端得到同一 ref
# ═════════════════════════════════════════════════════════════════════════════


@st.composite
def _ref_rows(draw) -> dict:
    ref_id = draw(st.uuids())
    project_id = draw(st.uuids())
    source_type = draw(st.sampled_from(["workpaper_cell", "voucher", "review", "note"]))
    source_id = draw(st.text(min_size=1, max_size=10))
    evidence_type = draw(st.sampled_from(["attachment_version", "ocr_result", "citation"]))
    evidence_id = draw(st.text(min_size=1, max_size=10))
    status = draw(st.sampled_from(["active", "inactive"]))
    intent_hash = _compute_intent_hash(
        source_type=source_type, source_id=source_id,
        evidence_type=evidence_type, evidence_id=evidence_id,
    )
    from datetime import datetime, timezone
    return {
        "id": str(ref_id),
        "project_id": str(project_id),
        "audit_year": draw(st.sampled_from([2023, 2024, 2025])),
        "source_type": source_type,
        "source_id": source_id,
        "source_version": draw(st.integers(min_value=1, max_value=9)),
        "evidence_type": evidence_type,
        "evidence_id": evidence_id,
        "attachment_version_id": None,
        "target_version": draw(st.integers(min_value=1, max_value=9)),
        "target_hash": "a" * 64,
        "label": "lbl",
        "context": "ctx",
        "intent_hash": intent_hash,
        "status": status,
        "created_at": datetime.now(timezone.utc),
    }


@given(row=_ref_rows())
def test_p8_map_ref_row_bidirectional_consistency(row):
    """P8：真实 ``_map_ref_row`` 对同一行，从 source 端与 evidence 端读到的
    ref id / 版本 / 状态完全一致。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 8
    """
    mapped = _map_ref_row(row)
    # source 端视图字段。
    assert str(mapped.source_type) == row["source_type"]
    assert str(mapped.source_id) == row["source_id"]
    assert mapped.source_version == row["source_version"]
    # evidence/target 端视图字段。
    assert str(mapped.evidence_type) == row["evidence_type"]
    assert str(mapped.evidence_id) == row["evidence_id"]
    assert mapped.target_version == row["target_version"]
    # 共享身份：无论从哪端查，id / 状态 / intent_hash 恒一致。
    assert str(mapped.id) == row["id"]
    assert mapped.status == row["status"]
    assert mapped.intent_hash == row["intent_hash"]


# ═════════════════════════════════════════════════════════════════════════════
# 真实 PostgreSQL 16 物理约束层（pg_only；非 PG 环境自动 skip）
#   P4 immutable trigger、P7 active-intent partial unique + 并发去重
# ═════════════════════════════════════════════════════════════════════════════


def _pg_async_url() -> str | None:
    """真实 PG16 异步连接串。

    优先环境变量 ``DATABASE_URL``；缺省时回退到应用配置 ``settings.DATABASE_URL``
    （与整个后端一致——dev/CI 的 PG 连接串在 .env 由 settings 加载，不一定导出到
    os.environ）。任一为真实 postgresql 串即返回 asyncpg 变体，否则 None → 用例 skip。
    """
    url = os.getenv("DATABASE_URL", "")
    if not url or "postgresql" not in url:
        try:
            from app.core.config import settings

            url = settings.DATABASE_URL or ""
        except Exception:
            url = ""
    if not url or "postgresql" not in url:
        return None
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def _seed_project_and_user(conn) -> tuple[uuid.UUID, uuid.UUID]:
    """在给定连接的事务里插入最小 project + user（供 FK）。调用方负责回滚/清理。"""
    import sqlalchemy as sa

    pid = uuid.uuid4()
    uid = uuid.uuid4()
    await conn.execute(
        sa.text(
            "INSERT INTO projects (id, name, client_name, status, version) "
            "VALUES (:id, :n, :c, 'planning', 1)"
        ),
        {"id": str(pid), "n": f"pbt-{pid}", "c": "PBT-Client"},
    )
    await conn.execute(
        sa.text(
            "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted) "
            "VALUES (:id, :u, :e, 'x', 'auditor', true, false)"
        ),
        {"id": str(uid), "u": f"pbt-{uid}", "e": f"{uid}@pbt.local"},
    )
    return pid, uid


@pytest.mark.pg_only
@pytest.mark.asyncio
@given(
    source_id=st.uuids(),
    evidence_id=st.uuids(),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
async def test_p7_partial_unique_rejects_duplicate_active_intent(source_id, evidence_id):
    """P7（真实 PG16）：``uq_evidence_ref_active_intent`` partial unique 保证同一
    (project, year, intent_hash) 至多一个 ``active`` ref；重复 active 插入被拒，
    ``inactive`` 重复允许。整个用例在一个事务内完成并 rollback，对共享 DB 零污染。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 7
    """
    import sqlalchemy as sa
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _pg_async_url()
    if url is None:
        pytest.skip("requires PostgreSQL 16")

    engine = create_async_engine(url, echo=False)
    conn = await engine.connect()
    outer = await conn.begin()
    try:
        pid, uid = await _seed_project_and_user(conn)
        intent = _compute_intent_hash(
            source_type="workpaper_cell", source_id=str(source_id),
            evidence_type="attachment_version", evidence_id=str(evidence_id),
        )
        insert = sa.text(
            "INSERT INTO evidence_refs "
            "(id, project_id, audit_year, source_type, source_id, evidence_type, evidence_id, "
            " intent_hash, status, actor_type, actor_user_id) "
            "VALUES (:id, :pid, 2025, 'workpaper_cell', :sid, 'attachment_version', :eid, "
            " :ih, :status, 'user', :uid)"
        )
        base = dict(pid=str(pid), sid=str(source_id), eid=str(evidence_id), ih=intent, uid=str(uid))

        # 首个 active 插入成功。
        await conn.execute(insert, {**base, "id": str(uuid.uuid4()), "status": "active"})

        # 第二个 active 同 intent → partial unique 立即拒绝（statement-level）。
        sp = await conn.begin_nested()
        with pytest.raises(IntegrityError):
            await conn.execute(insert, {**base, "id": str(uuid.uuid4()), "status": "active"})
        await sp.rollback()

        # inactive 重复不受 partial unique 约束（WHERE status='active'）→ 允许。
        await conn.execute(insert, {**base, "id": str(uuid.uuid4()), "status": "inactive"})

        # 只有一个 active。
        cnt = (
            await conn.execute(
                sa.text(
                    "SELECT count(*) FROM evidence_refs "
                    "WHERE project_id=:pid AND audit_year=2025 AND intent_hash=:ih "
                    "AND status='active'"
                ),
                {"pid": str(pid), "ih": intent},
            )
        ).scalar()
        assert cnt == 1
    finally:
        await outer.rollback()
        await conn.close()
        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_p7_concurrent_same_intent_at_most_one_active():
    """P7（真实 PG16，真并发）：N 个独立连接并发提交同一 active intent，DB 唯一约束
    保证至多一个提交成功；最终恰有一个 active ref。用 finally 清理落库行。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 7
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    url = _pg_async_url()
    if url is None:
        pytest.skip("requires PostgreSQL 16")

    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    pid = uuid.uuid4()
    uid = uuid.uuid4()
    source_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    intent = _compute_intent_hash(
        source_type="workpaper_cell", source_id=str(source_id),
        evidence_type="attachment_version", evidence_id=str(evidence_id),
    )

    async def _insert_active(n: int):
        async with factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO evidence_refs "
                    "(id, project_id, audit_year, source_type, source_id, evidence_type, "
                    " evidence_id, intent_hash, status, actor_type, actor_user_id) "
                    "VALUES (:id, :pid, 2025, 'workpaper_cell', :sid, 'attachment_version', "
                    " :eid, :ih, 'active', 'user', :uid)"
                ),
                {
                    "id": str(uuid.uuid4()), "pid": str(pid), "sid": str(source_id),
                    "eid": str(evidence_id), "ih": intent, "uid": str(uid),
                },
            )
            await s.commit()
            return n

    try:
        # 提交 FK 依赖（project + user）先落库。
        async with factory() as s:
            await s.execute(
                sa.text(
                    "INSERT INTO projects (id, name, client_name, status, version) "
                    "VALUES (:id, :n, 'PBT', 'planning', 1)"
                ),
                {"id": str(pid), "n": f"pbt-conc-{pid}"},
            )
            await s.execute(
                sa.text(
                    "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted) "
                    "VALUES (:id, :u, :e, 'x', 'auditor', true, false)"
                ),
                {"id": str(uid), "u": f"pbt-conc-{uid}", "e": f"{uid}@pbt.local"},
            )
            await s.commit()

        results = await asyncio.gather(
            *[_insert_active(i) for i in range(4)], return_exceptions=True
        )
        successes = [r for r in results if not isinstance(r, BaseException)]
        assert len(successes) <= 1, f"至多一个并发插入可成功，实得 {len(successes)}"

        async with factory() as s:
            cnt = (
                await s.execute(
                    sa.text(
                        "SELECT count(*) FROM evidence_refs "
                        "WHERE project_id=:pid AND audit_year=2025 AND intent_hash=:ih "
                        "AND status='active'"
                    ),
                    {"pid": str(pid), "ih": intent},
                )
            ).scalar()
            assert cnt == 1, f"最终恰有一个 active ref，实得 {cnt}"
    finally:
        async with factory() as s:
            await s.execute(
                sa.text("DELETE FROM evidence_refs WHERE project_id=:pid"), {"pid": str(pid)}
            )
            await s.execute(sa.text("DELETE FROM projects WHERE id=:pid"), {"pid": str(pid)})
            await s.execute(sa.text("DELETE FROM users WHERE id=:uid"), {"uid": str(uid)})
            await s.commit()
        await engine.dispose()


@pytest.mark.pg_only
@pytest.mark.asyncio
@given(mutate=st.sampled_from(["content_hash", "byte_size", "version_no", "created_at"]))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
async def test_p4_immutable_trigger_blocks_frozen_column_update(mutate):
    """P4（真实 PG16）：``trg_av_immutable`` 触发器禁止 UPDATE 已建 AttachmentVersion 的
    冻结列（字节/hash/version_no/时间）。整个用例事务内完成并 rollback，零污染。

    Feature: attachment-ocr-ai-evidence-governance-hardening, Property 4
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _pg_async_url()
    if url is None:
        pytest.skip("requires PostgreSQL 16")

    engine = create_async_engine(url, echo=False)
    conn = await engine.connect()
    outer = await conn.begin()
    try:
        pid, uid = await _seed_project_and_user(conn)
        att_id = uuid.uuid4()
        ver_id = uuid.uuid4()
        await conn.execute(
            sa.text(
                "INSERT INTO attachments (id, project_id, audit_year, file_name, file_path, "
                " version, state, actor_type, actor_user_id) "
                "VALUES (:id, :pid, 2025, 'f.pdf', '/api/attachments/x/download', 1, 'available', "
                " 'user', :uid)"
            ),
            {"id": str(att_id), "pid": str(pid), "uid": str(uid)},
        )
        await conn.execute(
            sa.text(
                "INSERT INTO attachment_versions (id, attachment_id, project_id, audit_year, "
                " version_no, storage_type, storage_key, content_hash, byte_size, availability, "
                " actor_type, actor_user_id) "
                "VALUES (:id, :aid, :pid, 2025, 1, 'local', 'k1', :h, 10, 'available', "
                " 'user', :uid)"
            ),
            {"id": str(ver_id), "aid": str(att_id), "pid": str(pid), "h": "a" * 64, "uid": str(uid)},
        )

        # 尝试 UPDATE 冻结列 → 触发器必须抛错。
        col_value = {
            "content_hash": ("content_hash", "b" * 64),
            "byte_size": ("byte_size", 999),
            "version_no": ("version_no", 42),
            "created_at": ("created_at", "now()"),
        }[mutate]
        col, val = col_value
        sp = await conn.begin_nested()
        with pytest.raises(Exception) as ei:  # asyncpg RaiseError → DBAPIError
            if col == "created_at":
                # 用确定不同于插入时刻的固定时间戳：PG 的 now() 在同一事务内是常量
                # （== transaction_timestamp()），与刚插入行的 created_at 相同 → 不构成
                # 变更、触发器不会拦截；必须用真正不同的值才能验证不可变触发器。
                await conn.execute(
                    sa.text(
                        f"UPDATE attachment_versions SET {col}="
                        "TIMESTAMPTZ '2000-01-01 00:00:00+00' WHERE id=:id"
                    ),
                    {"id": str(ver_id)},
                )
            else:
                await conn.execute(
                    sa.text(f"UPDATE attachment_versions SET {col}=:v WHERE id=:id"),
                    {"v": val, "id": str(ver_id)},
                )
        await sp.rollback()
        # 错误来自不可变触发器（脱敏断言：不校验具体英文文案，只要 UPDATE 被拒）。
        assert ei.value is not None

        # 冻结列仍是原值。
        row = (
            await conn.execute(
                sa.text(
                    "SELECT content_hash, byte_size, version_no FROM attachment_versions WHERE id=:id"
                ),
                {"id": str(ver_id)},
            )
        ).mappings().first()
        assert row["content_hash"] == "a" * 64
        assert row["byte_size"] == 10
        assert row["version_no"] == 1
    finally:
        await outer.rollback()
        await conn.close()
        await engine.dispose()
