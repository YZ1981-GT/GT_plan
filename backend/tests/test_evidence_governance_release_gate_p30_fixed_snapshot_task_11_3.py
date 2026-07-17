"""Release Gate — P30 固定不可变快照独立复算门（Task 11.3）。

Feature: attachment-ocr-ai-evidence-governance-hardening
Task: 11.3 (Wave 10 — 可执行最终发布门)
Requirements: R16（历史覆盖与持续质量治理；R16.1 历史原始字节变化数为 0）
Design: §9 质量快照；§P30；§7 发布门 "P2：R16 …… 历史增强启用前，必须以预先固定且
        不可变的治理数据快照单独验收 P30，P30 不与 UAT-15 绑定"

本文件是 **独立发布门**，与 Wave 8 的 P30 属性组（随机化 PBT，
``test_evidence_governance_migration_quality_properties_wave8_9_6.py``）刻意分离：

- **独立可调用**：带专属标记 ``release_gate_p30``，可用
  ``python -m pytest -m release_gate_p30`` 单独运行，作为"历史增强启用前"的前置门。
- **固定不可变快照**：被测输入是本模块内写死的 ``FIXED_IMMUTABLE_SNAPSHOT`` 常量
  （确定性、非随机、非数据库、非在线容量数据），冻结了"历史原始字节"（记录 content_hash）
  与参考日 ``as_of_day``。
- **不以在线容量数据替代**：本门 **不依赖任何 DB session / Redis / HTTP / 6000 VU 容量场景 /
  UAT-15**；``compute_quality_snapshot`` 是纯函数，且下方 ``test_gate_is_independent_*``
  以源码审查 + 签名审查客观证明它不读取 now()/随机/IO/在线数据。
- **原始字节与业务结论不变**：重复计算得到完全相同的 metrics / 账龄桶 / 问题清单 /
  business_conclusion / input_hash；且计算 **不得原地修改** 固定快照（原始字节零变化，R16.1），
  business_conclusion 与金样固定值一致（结论不漂移）。

无随机、无 DB、无外部依赖 —— 与 UAT-15 / 6000 VU 容量报告完全解耦。
"""

from __future__ import annotations

import copy
import inspect

import pytest

from app.services.evidence_governance.quality_snapshot import (
    AGING_BUCKET_KEYS,
    build_snapshot_input_hash,
    compute_quality_snapshot,
)
from app.services.evidence_governance import quality_snapshot as _qs_module

# 全模块级发布门标记：可用 `-m release_gate_p30` 独立运行，独立于 UAT-15/容量套件。
pytestmark = pytest.mark.release_gate_p30


# ═══════════════════════════════════════════════════════════════════════════
# 固定不可变治理数据快照（写死常量 —— 非 DB / 非随机 / 非在线容量数据）
# 冻结历史原始字节（content_hash）与参考日（as_of_day）。启用历史增强前对它单独验收 P30。
# ═══════════════════════════════════════════════════════════════════════════

FIXED_IMMUTABLE_SNAPSHOT: dict = {
    "scope": {
        "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "audit_year": 2025,
    },
    # 参考日为快照采集时冻结的序数，绝不使用 now()（P30 独立于在线时间/容量数据）。
    "as_of_day": 20250,
    "records": [
        # id 采用可预测的升序前缀，锁定 issue_list 的确定性排序（先 id 后类型）。
        {"id": "r01-av", "evidence_type": "attachment_version", "has_actor": True,
         "content_hash": "1" * 64, "version": 1, "is_active_ref": True,
         "unverified_chain": False, "is_stale": False, "age_days": 5},
        {"id": "r02-av", "evidence_type": "attachment_version", "has_actor": False,
         "content_hash": None, "version": None, "is_active_ref": True,
         "unverified_chain": False, "is_stale": False, "age_days": 45},
        {"id": "r03-av", "evidence_type": "attachment_version", "has_actor": True,
         "content_hash": "3" * 64, "version": 2, "is_active_ref": True,
         "unverified_chain": False, "is_stale": True, "age_days": 100},
        {"id": "r04-ocr", "evidence_type": "ocr_result", "has_actor": True,
         "content_hash": "4" * 64, "version": 1, "is_active_ref": True,
         "ocr_confirmed": True, "age_days": 200},
        {"id": "r05-ocr", "evidence_type": "ocr_result", "has_actor": True,
         "content_hash": "5" * 64, "version": 1, "is_active_ref": True,
         "ocr_confirmed": False, "age_days": 400},
        {"id": "r06-ai", "evidence_type": "ai_content", "has_actor": True,
         "content_hash": "6" * 64, "version": 1, "is_active_ref": True,
         "ai_human_confirmed": False, "age_days": 10},
        {"id": "r07-ai", "evidence_type": "ai_content", "has_actor": True,
         "content_hash": "7" * 64, "version": 1, "is_active_ref": True,
         "ai_human_confirmed": True, "age_days": 20},
        {"id": "r08-cit", "evidence_type": "citation", "has_actor": True,
         "content_hash": "8" * 64, "version": 1, "is_active_ref": True,
         "citation_locatable": False, "age_days": 370},
        {"id": "r09-ref", "evidence_type": "ref", "has_actor": True,
         "content_hash": "9" * 64, "version": 1, "is_active_ref": False,
         "age_days": 60},
        {"id": "r10-ref", "evidence_type": "ref", "has_actor": True,
         "content_hash": "a" * 64, "version": 1, "is_active_ref": True,
         "unverified_chain": True, "age_days": 500},
        {"id": "r11-av", "evidence_type": "attachment_version", "has_actor": True,
         "content_hash": None, "version": 3, "is_active_ref": True,
         "age_days": 150},
    ],
}

# 金样固定期望（人工推导，确定性）—— 结论与指标不得漂移。
_EXPECTED_AGING_BUCKETS: dict = {
    "0-30": 3,      # r01(5), r06(10), r07(20)
    "31-90": 2,     # r02(45), r09(60)
    "91-180": 2,    # r03(100), r11(150)
    "181-365": 1,   # r04(200)
    "365+": 3,      # r05(400), r08(370), r10(500)
}

_EXPECTED_ISSUE_LIST: list = [
    {"id": "r02-av", "evidence_type": "attachment_version", "issues": ["MISSING_ACTOR"]},
    {"id": "r03-av", "evidence_type": "attachment_version", "issues": ["STALE"]},
    {"id": "r05-ocr", "evidence_type": "ocr_result", "issues": ["OCR_UNCONFIRMED"]},
    {"id": "r06-ai", "evidence_type": "ai_content", "issues": ["AI_UNCONFIRMED"]},
    {"id": "r08-cit", "evidence_type": "citation", "issues": ["CITATION_NOT_LOCATABLE"]},
    {"id": "r09-ref", "evidence_type": "ref", "issues": ["REF_INACTIVE"]},
    {"id": "r10-ref", "evidence_type": "ref", "issues": ["UNVERIFIED_CHAIN"]},
    {"id": "r11-av", "evidence_type": "attachment_version", "issues": ["MISSING_HASH"]},
]

_EXPECTED_BUSINESS_CONCLUSION: dict = {
    "archive_ready": False,
    "grade": "blocked",
    "blocking_records": 7,   # r02,r03,r05,r06,r08,r09,r11（r10 仅 advisory）
    "advisory_records": 1,   # r10 UNVERIFIED_CHAIN
}

# 复算次数：模拟"多次面板刷新/多进程复算"（发布门要求稳定复现）。
_RECOMPUTE_TIMES = 5


# ═══════════════════════════════════════════════════════════════════════════
# 发布门主体
# ═══════════════════════════════════════════════════════════════════════════


def test_release_gate_p30_recompute_is_byte_identical_across_runs():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3, Property 30.

    对固定不可变快照重复计算 ``_RECOMPUTE_TIMES`` 次 → metrics / aging_buckets /
    issue_list / business_conclusion / input_hash / snapshot_key 完全一致（可复算）。
    """
    results = [compute_quality_snapshot(FIXED_IMMUTABLE_SNAPSHOT) for _ in range(_RECOMPUTE_TIMES)]
    first = results[0].as_dict()
    for r in results[1:]:
        assert r.as_dict() == first, "P30 复算漂移：固定快照重复计算结果不一致"


def test_release_gate_p30_matches_frozen_golden_metrics():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3, Property 30.

    固定快照的指标 / 账龄桶 / 问题清单与人工推导的金样固定值一致（防止计算规则悄然漂移）。
    """
    r = compute_quality_snapshot(FIXED_IMMUTABLE_SNAPSHOT)

    assert r.aging_buckets == _EXPECTED_AGING_BUCKETS
    assert set(r.aging_buckets.keys()) == set(AGING_BUCKET_KEYS)
    assert sum(r.aging_buckets.values()) == len(FIXED_IMMUTABLE_SNAPSHOT["records"])

    assert r.issue_list == _EXPECTED_ISSUE_LIST

    assert r.metrics["total_records"] == 11
    assert r.metrics["with_content_hash"] == 9
    assert r.metrics["missing_content_hash"] == 2
    assert r.metrics["missing_actor"] == 1
    assert r.metrics["inactive_ref"] == 1
    assert r.metrics["unverified_chain"] == 1
    assert r.metrics["stale"] == 1
    assert r.metrics["ocr_total"] == 2
    assert r.metrics["ocr_confirmed"] == 1
    assert r.metrics["ocr_unconfirmed"] == 1
    assert r.metrics["ai_total"] == 2
    assert r.metrics["ai_confirmed"] == 1
    assert r.metrics["ai_unconfirmed"] == 1
    assert r.metrics["citation_total"] == 1
    assert r.metrics["citation_locatable"] == 0
    assert r.metrics["citation_not_locatable"] == 1
    assert r.metrics["records_with_issues"] == 8
    assert r.metrics["blocking_records"] == 7
    assert r.metrics["hash_coverage_ratio"] == round(9 / 11, 4)
    assert r.metrics["actor_coverage_ratio"] == round(10 / 11, 4)
    assert r.metrics["type_counts"] == {
        "ai_content": 2,
        "attachment_version": 4,
        "citation": 1,
        "ocr_result": 2,
        "ref": 2,
    }


def test_release_gate_p30_business_conclusion_does_not_drift():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3, Property 30 / R16.3.

    业务结论由指标确定性派生，重复计算不漂移，且与金样固定结论一致
    （R16 门禁"不得自动修改业务结论"）。
    """
    conclusions = [
        compute_quality_snapshot(FIXED_IMMUTABLE_SNAPSHOT).business_conclusion
        for _ in range(_RECOMPUTE_TIMES)
    ]
    for c in conclusions:
        assert c == _EXPECTED_BUSINESS_CONCLUSION
        # archive_ready ⇔ blocking_records == 0（确定性派生，不漂移）。
        assert c["archive_ready"] == (c["blocking_records"] == 0)


def test_release_gate_p30_original_bytes_unchanged_by_recompute():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3, R16.1.

    历史原始字节变化数为 0：复算是只读的，绝不原地修改固定快照
    （records 的 content_hash / version 等"原始字节指纹"逐条不变）。
    """
    pristine = copy.deepcopy(FIXED_IMMUTABLE_SNAPSHOT)

    for _ in range(_RECOMPUTE_TIMES):
        compute_quality_snapshot(FIXED_IMMUTABLE_SNAPSHOT)

    # 整快照深比较：结构/字节零变化。
    assert FIXED_IMMUTABLE_SNAPSHOT == pristine, "复算改动了固定快照（违反 R16.1 原始字节零变化）"

    # 逐条核对"原始字节指纹"（content_hash + version）未被复算触碰。
    for before, after in zip(pristine["records"], FIXED_IMMUTABLE_SNAPSHOT["records"]):
        assert after["id"] == before["id"]
        assert after.get("content_hash") == before.get("content_hash")
        assert after.get("version") == before.get("version")


def test_release_gate_p30_input_hash_reproducible_across_fresh_rebuild():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3, Property 30.

    input_hash 仅依赖固定快照的逻辑内容，可在独立重建（模拟另一进程/另一次采集）中复现，
    且与记录顺序无关 —— 证明它是"固定快照"的稳定指纹，而非在线状态。
    """
    base = compute_quality_snapshot(FIXED_IMMUTABLE_SNAPSHOT)

    # 全新重建同一逻辑快照（新对象、新列表、打乱记录顺序）。
    rebuilt_records = list(reversed(copy.deepcopy(FIXED_IMMUTABLE_SNAPSHOT["records"])))
    rebuilt = {
        "scope": {
            "project_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "audit_year": 2025,
        },
        "as_of_day": 20250,
        "records": rebuilt_records,
    }
    r = compute_quality_snapshot(rebuilt)

    assert r.input_hash == base.input_hash
    assert r.snapshot_key == base.snapshot_key
    assert r.metrics == base.metrics
    assert r.aging_buckets == base.aging_buckets
    assert r.issue_list == base.issue_list
    assert r.business_conclusion == base.business_conclusion

    # 与独立哈希函数复算一致（跨进程比对锚点）。
    assert base.input_hash == build_snapshot_input_hash(FIXED_IMMUTABLE_SNAPSHOT)


# ═══════════════════════════════════════════════════════════════════════════
# 独立性证明：本门不读取 DB / now() / 随机 / HTTP / 在线容量数据（P30 独立于 UAT-15）
# ═══════════════════════════════════════════════════════════════════════════


def test_gate_is_independent_signature_takes_only_fixed_payload():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3.

    ``compute_quality_snapshot`` 的签名只接收固定快照 payload（无 db/session/now/http 参数），
    客观证明它不依赖在线容量数据或数据库连接。
    """
    params = list(inspect.signature(compute_quality_snapshot).parameters)
    assert params == ["payload"], f"计算入口不应接收 payload 以外的参数：{params}"


def test_gate_is_independent_source_has_no_io_or_online_dependencies():
    """Feature: attachment-ocr-ai-evidence-governance-hardening, Task 11.3.

    源码审查：质量快照模块不含 DB / 时间 / 随机 / 网络 / 在线容量的读取符号，
    保证 P30 只对固定不可变快照计算，绝不以在线容量数据替代（独立于 UAT-15 / 6000 VU）。
    """
    src = inspect.getsource(_qs_module)
    forbidden = [
        "datetime.now",
        "datetime.utcnow",
        "time.time(",
        "random.",
        "AsyncSession",
        "get_db",
        "httpx",
        "requests.",
        "aioredis",
        "redis.",
        "execute(",   # 无 SQL 执行
        "select(",    # 无 ORM 查询
    ]
    hits = [tok for tok in forbidden if tok in src]
    assert not hits, f"质量快照模块疑似引入 IO/在线依赖，违反 P30 固定快照独立性：{hits}"
