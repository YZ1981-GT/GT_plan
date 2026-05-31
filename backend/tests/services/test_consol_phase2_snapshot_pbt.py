"""合并模块 Phase 2 S8 签字快照冻结/还原 PBT（hypothesis + 集成）

`consol_snapshot_service` 把签字时刻的真实合并数据序列化 + SHA-256 哈希 + base64+gzip
压缩存入 ConsolSnapshot.snapshot_data，实现签字冻结（ADR-CONSOL-206 / 需求 8）。

属性 S8（需求 8.3）：create_snapshot 后，即使子公司数据/抵销被改，从快照反序列化能
还原"签字时合并数"且哈希校验通过。

测试：
1. round-trip 纯函数：_decompress_payload(_compress_payload(json)) == json；
   _sha256_hex 对相同输入稳定（hypothesis 变化 raw 数据，金额作字符串）。
2. restore 集成：fake snapshot 对象（snapshot_data 含 gzip+base64 格式）→
   restore_consol_snapshot 还原 data == 原始 raw + hash_valid==True + _locked。
3. 篡改 _hash → hash_valid==False（完整性检测）。
4. 旧空壳快照（{created_at}）→ hash_valid==False + legacy==True。

Validates: Requirements 8.1, 8.2, 8.3 (Property S8); Error scenario EH8
"""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from hypothesis import given, settings, strategies as st

from app.services.consol_snapshot_service import (
    _canonical_json,
    _compress_payload,
    _decompress_payload,
    _sha256_hex,
    restore_consol_snapshot,
)

# ---------------------------------------------------------------------------
# strategies：合并数据 raw dict（金额一律字符串，镜像生产 str(Decimal) 序列化）
# ---------------------------------------------------------------------------

_amount_str = st.decimals(
    min_value=Decimal("-9999999.99"),
    max_value=Decimal("9999999.99"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
).map(str)

_trial_row = st.fixed_dictionaries(
    {
        "standard_account_code": st.from_regex(r"[1-9]\d{3}", fullmatch=True),
        "account_name": st.text(max_size=12),
        "individual_sum": _amount_str,
        "consol_elimination": _amount_str,
        "consol_amount": _amount_str,
    }
)

_raw_data = st.fixed_dictionaries(
    {
        "project_id": st.uuids().map(str),
        "year": st.integers(min_value=2000, max_value=2100),
        "trial": st.lists(_trial_row, max_size=6),
        "worksheet": st.lists(
            st.fixed_dictionaries(
                {"node_company_code": st.text(max_size=6), "consolidated_amount": _amount_str}
            ),
            max_size=4,
        ),
    }
)


def _make_snapshot(snapshot_data: dict, project_id=None, year=2025):
    """构造 ConsolSnapshot-like 替身（仅含 restore 读取的属性）。"""
    return SimpleNamespace(
        snapshot_data=snapshot_data,
        project_id=project_id,
        year=year,
    )


def _build_frozen_snapshot_data(raw: dict, *, locked: bool = True) -> dict:
    """模拟 create_consol_snapshot 的存储格式（gzip+base64 + 哈希）。"""
    raw_json = _canonical_json(raw)
    return {
        "_format": "gzip+base64",
        "_payload": _compress_payload(raw_json),
        "_hash": _sha256_hex(raw_json),
        "_locked": locked,
        "_meta": {"year": raw.get("year")},
    }


# ===========================================================================
# round-trip 纯函数（压缩/解压 + 哈希稳定）
# ===========================================================================


class TestCompressRoundTrip:
    """_decompress_payload(_compress_payload(x)) == x；哈希稳定。"""

    @given(raw=_raw_data)
    @settings(max_examples=15)
    def test_compress_decompress_roundtrip(self, raw):
        """canonical_json → compress → decompress 还原原始 JSON 字符串。"""
        raw_json = _canonical_json(raw)
        restored = _decompress_payload(_compress_payload(raw_json))
        assert restored == raw_json
        # 还原后 json.loads 语义等价
        assert json.loads(restored) == json.loads(raw_json)

    @given(raw=_raw_data)
    @settings(max_examples=15)
    def test_sha256_stable_and_canonical_independent_of_key_order(self, raw):
        """canonical_json sort_keys → 相同内容不同插入顺序哈希一致。"""
        raw_json = _canonical_json(raw)
        # 用打乱 key 顺序的等价 dict 重建
        shuffled = dict(reversed(list(raw.items())))
        assert _sha256_hex(_canonical_json(shuffled)) == _sha256_hex(raw_json)

    @given(text=st.text())
    @settings(max_examples=10)
    def test_sha256_deterministic(self, text):
        """同一字符串两次哈希相同。"""
        assert _sha256_hex(text) == _sha256_hex(text)


# ===========================================================================
# S8 restore 还原 + 哈希校验
# ===========================================================================


class TestS8RestoreFreeze:
    """S8：从冻结快照还原"签字时合并数" + 哈希校验通过。

    **Validates: Requirements 8.3**
    """

    @given(raw=_raw_data)
    @settings(max_examples=15)
    def test_restore_recovers_original_data_with_valid_hash(self, raw):
        """冻结快照 → restore 还原 data == 原始 raw + hash_valid==True。"""
        snapshot_data = _build_frozen_snapshot_data(raw, locked=True)
        snap = _make_snapshot(snapshot_data)

        restored = restore_consol_snapshot(snap)

        assert restored["hash_valid"] is True
        assert restored["locked"] is True
        # 还原数据与签字时刻原始数据精确相等（金额字符串无精度丢失）
        assert restored["data"] == raw

    @given(raw=_raw_data)
    @settings(max_examples=15)
    def test_tampered_hash_detected(self, raw):
        """篡改 _hash → hash_valid==False（完整性检测，S8）。"""
        snapshot_data = _build_frozen_snapshot_data(raw, locked=True)
        # 篡改存储哈希
        snapshot_data["_hash"] = "deadbeef" * 8
        snap = _make_snapshot(snapshot_data)

        restored = restore_consol_snapshot(snap)

        assert restored["hash_valid"] is False
        # data 仍可还原（payload 未篡改），只是哈希不匹配
        assert restored["data"] == raw

    @given(raw=_raw_data)
    @settings(max_examples=10)
    def test_tampered_payload_detected(self, raw):
        """篡改 _payload → 还原后重算哈希 != 存储哈希 → hash_valid==False。"""
        snapshot_data = _build_frozen_snapshot_data(raw, locked=True)
        # 用另一份不同数据的 payload 替换（哈希仍指向旧数据）
        other = dict(raw)
        other["_tampered"] = "injected"
        snapshot_data["_payload"] = _compress_payload(_canonical_json(other))
        snap = _make_snapshot(snapshot_data)

        restored = restore_consol_snapshot(snap)
        assert restored["hash_valid"] is False


# ===========================================================================
# EH8 / 旧空壳兼容
# ===========================================================================


class TestLegacyAndEdgeCases:
    """旧空壳快照 + 损坏 payload 的健壮处理。"""

    def test_legacy_shell_snapshot(self):
        """旧空壳快照（仅 {created_at}）→ hash_valid==False + legacy==True，不抛错。"""
        snap = _make_snapshot({"created_at": "2026-05-30T00:00:00Z"})
        restored = restore_consol_snapshot(snap)

        assert restored["hash_valid"] is False
        assert restored.get("legacy") is True
        # 原样返回 snapshot_data 作为 data
        assert restored["data"] == {"created_at": "2026-05-30T00:00:00Z"}

    def test_empty_snapshot_data(self):
        """snapshot_data 为 None → 视为空壳，不抛错。"""
        snap = _make_snapshot(None)
        restored = restore_consol_snapshot(snap)
        assert restored["hash_valid"] is False
        assert restored.get("legacy") is True

    def test_corrupt_payload_returns_invalid_not_raise(self):
        """_payload 非法 base64 → 还原失败返回 hash_valid==False，不抛异常。"""
        snapshot_data = {
            "_format": "gzip+base64",
            "_payload": "!!!not-valid-base64!!!",
            "_hash": "abc",
            "_locked": True,
        }
        snap = _make_snapshot(snapshot_data)
        restored = restore_consol_snapshot(snap)

        assert restored["hash_valid"] is False
        assert restored["data"] == {}

    def test_locked_flag_preserved(self):
        """_locked 标志在还原结果中保留（签字锁定只读语义）。"""
        raw = {"project_id": "p", "year": 2025, "trial": []}
        unlocked = _make_snapshot(_build_frozen_snapshot_data(raw, locked=False))
        locked = _make_snapshot(_build_frozen_snapshot_data(raw, locked=True))

        assert restore_consol_snapshot(unlocked)["locked"] is False
        assert restore_consol_snapshot(locked)["locked"] is True
