"""批 7 任务 7.1：快照 v2 manifest 升级的单元测试。

测试覆盖：
- 11 类分片的 hash 计算
- 根 hash 基于有序分片 hash 列表
- operation_ref 和 version_ref 提取
- 新旧格式兼容读取
- 分片生成和验证逻辑
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.services.consol_snapshot_service import (
    _build_v2_manifest,
    _canonical_json,
    _root_hash,
    _shard_hash,
    _sha256_hex,
    restore_consol_snapshot,
    _FORMAT_V1,
    _FORMAT_V2,
    _SHARD_ORDER,
    _compress_payload,
    _decompress_payload,
    _manifest_operation_ref,
    _manifest_version_ref,
)


class TestShardHash:
    """测试单个分片的 hash 计算（ADR-CRW-007）"""

    def test_empty_shard_hash(self):
        """空分片也能计算 hash"""
        h = _shard_hash([])
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex = 64 字符

    def test_list_shard_hash_deterministic(self):
        """列表分片 hash 可复现（canonical JSON）"""
        shard = [
            {"code": "1001", "amount": "100.00"},
            {"code": "1002", "amount": "200.00"},
        ]
        h1 = _shard_hash(shard)
        h2 = _shard_hash(shard)
        assert h1 == h2

    def test_dict_shard_hash_deterministic(self):
        """字典分片 hash 可复现（sort_keys）"""
        shard = {"revision": 2, "fingerprint": "abc123", "status": "active"}
        h1 = _shard_hash(shard)
        h2 = _shard_hash(shard)
        assert h1 == h2

    def test_order_affects_hash(self):
        """元素顺序不同，hash 不同"""
        shard1 = [{"a": 1}, {"b": 2}]
        shard2 = [{"b": 2}, {"a": 1}]
        assert _shard_hash(shard1) != _shard_hash(shard2)

    def test_decimal_serialization(self):
        """Decimal 类型正确序列化为字符串（避免 float 精度丢失）"""
        shard = [{"amount": Decimal("123.456789")}]
        h = _shard_hash(shard)
        # 重算验证：Decimal 被 str() 处理
        json_str = _canonical_json(shard)
        assert '"123.456789"' in json_str
        assert _sha256_hex(json_str) == h

    def test_uuid_serialization(self):
        """UUID 类型正确序列化为字符串"""
        uid = uuid4()
        shard = [{"id": uid}]
        json_str = _canonical_json(shard)
        assert str(uid) in json_str

    def test_datetime_serialization(self):
        """datetime 类型正确序列化为 ISO 字符串"""
        dt = datetime(2026, 5, 15, 10, 30, 0, tzinfo=timezone.utc)
        shard = [{"ts": dt}]
        json_str = _canonical_json(shard)
        assert "2026-05-15" in json_str


class TestRootHash:
    """测试根 hash 计算（基于有序分片 hash）"""

    def test_root_hash_with_two_shards(self):
        """两个分片的根 hash"""
        shard_hashes = {
            "trial": "hash_trial_abc",
            "report": "hash_report_xyz",
        }
        root = _root_hash(shard_hashes)
        assert isinstance(root, str)
        assert len(root) == 64

    def test_root_hash_follows_shard_order(self):
        """根 hash 按 _SHARD_ORDER 固定顺序计算（可复现）"""
        # trial 在 _SHARD_ORDER 第 5 位，report 第 6 位
        shard_hashes = {
            "report": "hash_report",
            "trial": "hash_trial",
        }
        root1 = _root_hash(shard_hashes)
        root2 = _root_hash(shard_hashes)
        assert root1 == root2

        # 验证顺序：按 _SHARD_ORDER 有序列表计算
        ordered = [["trial", "hash_trial"], ["report", "hash_report"]]
        expected = _sha256_hex(_canonical_json(ordered))
        assert root1 == expected

    def test_root_hash_only_includes_present_shards(self):
        """根 hash 只纳入实际捕获的分片（缺失分片不参与）"""
        shard_hashes = {"trial": "hash_a"}
        root1 = _root_hash(shard_hashes)

        shard_hashes_more = {"trial": "hash_a", "report": "hash_b"}
        root2 = _root_hash(shard_hashes_more)

        # 分片集合不同，根 hash 必不同
        assert root1 != root2

    def test_root_hash_with_all_11_shards(self):
        """11 类分片全覆盖时的根 hash"""
        shard_hashes = {key: f"hash_{key}" for key in _SHARD_ORDER}
        root = _root_hash(shard_hashes)
        assert len(root) == 64

        # 验证顺序固定
        ordered = [[key, f"hash_{key}"] for key in _SHARD_ORDER]
        expected = _sha256_hex(_canonical_json(ordered))
        assert root == expected


class TestV2ManifestBuild:
    """测试 v2 manifest 组装"""

    def test_manifest_structure(self):
        """manifest 含必要字段"""
        shards = {"trial": [{"code": "1001"}], "report": [{"row": "R1"}]}
        shard_hashes = {
            "trial": _shard_hash(shards["trial"]),
            "report": _shard_hash(shards["report"]),
        }
        manifest = _build_v2_manifest(
            shards,
            shard_hashes,
            captured_sources=["trial", "report"],
            failed_sources=[],
            operation_ref={"operation_id": "op-1"},
            version_ref={"digest": "vd-1"},
            partial=False,
        )

        assert manifest["manifest_version"] == 2
        assert manifest["shard_order"] == list(_SHARD_ORDER)
        assert manifest["shard_hashes"] == shard_hashes
        assert "root_hash" in manifest
        assert manifest["counts"] == {"trial": 1, "report": 1}
        assert manifest["captured_sources"] == ["trial", "report"]
        assert manifest["failed_sources"] == []
        assert manifest["partial"] is False
        assert manifest["operation_ref"] == {"operation_id": "op-1"}
        assert manifest["version_ref"] == {"digest": "vd-1"}

    def test_manifest_counts_list_length(self):
        """counts 统计列表长度"""
        shards = {"trial": [1, 2, 3], "entries": [{"a": 1}]}
        shard_hashes = {k: _shard_hash(v) for k, v in shards.items()}
        manifest = _build_v2_manifest(
            shards,
            shard_hashes,
            captured_sources=list(shards.keys()),
            failed_sources=[],
            operation_ref=None,
            version_ref=None,
            partial=False,
        )
        assert manifest["counts"]["trial"] == 3
        assert manifest["counts"]["entries"] == 1

    def test_manifest_counts_dict_length(self):
        """counts 统计字典条目数"""
        shards = {"mappings": {"rules": [1, 2], "bindings": [3]}}
        shard_hashes = {k: _shard_hash(v) for k, v in shards.items()}
        manifest = _build_v2_manifest(
            shards,
            shard_hashes,
            captured_sources=["mappings"],
            failed_sources=[],
            operation_ref=None,
            version_ref=None,
            partial=False,
        )
        # dict 长度 = key 数量
        assert manifest["counts"]["mappings"] == 2

    def test_manifest_partial_with_failed_sources(self):
        """partial 快照记录失败分片"""
        shards = {"trial": []}
        shard_hashes = {"trial": _shard_hash([])}
        manifest = _build_v2_manifest(
            shards,
            shard_hashes,
            captured_sources=["trial"],
            failed_sources=["report", "artifact"],
            operation_ref=None,
            version_ref=None,
            partial=True,
        )
        assert manifest["partial"] is True
        assert manifest["failed_sources"] == ["report", "artifact"]


class TestOperationAndVersionRefs:
    """测试 operation 和 version 引用提取"""

    def test_operation_ref_from_lifecycle_shard(self):
        """从 lifecycle 分片提取 operation 引用"""
        lifecycle = {
            "operation": {
                "id": "op-123",
                "revision": 5,
                "status": "succeeded",
                "request_hash": "req-hash-xyz",
            },
            "audit_count": 10,
        }
        ref = _manifest_operation_ref(lifecycle)
        assert ref["operation_id"] == "op-123"
        assert ref["revision"] == 5
        assert ref["status"] == "succeeded"
        assert ref["request_hash"] == "req-hash-xyz"

    def test_operation_ref_missing_operation(self):
        """lifecycle 分片无 operation 时返回空字典"""
        lifecycle = {"audit_count": 0}
        ref = _manifest_operation_ref(lifecycle)
        assert ref == {}

    def test_operation_ref_invalid_input(self):
        """非字典输入返回空字典"""
        assert _manifest_operation_ref(None) == {}
        assert _manifest_operation_ref([]) == {}

    def test_version_ref_from_operation(self):
        """从 operation 的 version_vector 提取版本摘要"""
        from types import SimpleNamespace

        operation = SimpleNamespace(
            version_vector={
                "digest": "vd-abc",
                "tree_fingerprint": "tf-123",
                "tree_revision": 3,
                "tb_digest": "tb-xyz",
                "elimination_digest": "el-456",
                "formula_digest": "fm-789",
                "note_mapping_digest": "nm-abc",
                "template_digest": "tm-def",
            }
        )
        ref = _manifest_version_ref(operation)
        assert ref["digest"] == "vd-abc"
        assert ref["tree_fingerprint"] == "tf-123"
        assert ref["tree_revision"] == 3
        assert ref["tb_digest"] == "tb-xyz"
        assert ref["elimination_digest"] == "el-456"
        assert ref["formula_digest"] == "fm-789"
        assert ref["note_mapping_digest"] == "nm-abc"
        assert ref["template_digest"] == "tm-def"

    def test_version_ref_none_operation(self):
        """operation 为 None 时返回空字典"""
        assert _manifest_version_ref(None) == {}

    def test_version_ref_missing_vector(self):
        """operation 无 version_vector 属性时返回空字典"""
        from types import SimpleNamespace

        operation = SimpleNamespace(id="op-1")
        ref = _manifest_version_ref(operation)
        assert ref == {}


class TestCompressionDecompression:
    """测试压缩和解压（gzip+base64）"""

    def test_compress_decompress_roundtrip(self):
        """压缩后解压能还原原文"""
        original = '{"project_id": "abc", "year": 2025, "trial": []}'
        compressed = _compress_payload(original)
        assert isinstance(compressed, str)
        # base64 编码后应该比原文更长（小文本）
        assert len(compressed) > 0

        decompressed = _decompress_payload(compressed)
        assert decompressed == original

    def test_compress_large_data(self):
        """压缩大数据能显著减小体积"""
        large = json.dumps([{"code": f"100{i}", "amount": "1000.00"} for i in range(1000)])
        compressed = _compress_payload(large)
        # gzip 对重复数据压缩率高
        assert len(compressed) < len(large)


class TestRestoreSnapshot:
    """测试快照还原与 hash 校验（新旧格式兼容）"""

    def test_restore_v1_snapshot_valid_hash(self):
        """还原 v1 快照，hash 校验通过"""
        from types import SimpleNamespace

        raw = {"project_id": "pid-1", "year": 2025, "trial": []}
        raw_json = _canonical_json(raw)
        snapshot_data = {
            "_format": _FORMAT_V1,
            "_payload": _compress_payload(raw_json),
            "_hash": _sha256_hex(raw_json),
            "_locked": True,
            "_meta": {"year": 2025},
        }
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        assert result["hash_valid"] is True
        assert result["locked"] is True
        assert result["data"] == raw
        assert result["hash"] == snapshot_data["_hash"]

    def test_restore_v1_snapshot_tampered(self):
        """v1 快照被篡改，hash 校验失败"""
        from types import SimpleNamespace

        raw = {"project_id": "pid-1", "year": 2025, "trial": []}
        raw_json = _canonical_json(raw)
        snapshot_data = {
            "_format": _FORMAT_V1,
            "_payload": _compress_payload(raw_json),
            "_hash": "tampered_hash_not_matching",  # 篡改的 hash
            "_locked": True,
        }
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        assert result["hash_valid"] is False
        assert result["hash"] == "tampered_hash_not_matching"

    def test_restore_v2_snapshot_all_hashes_valid(self):
        """还原 v2 快照，逐分片 hash + 根 hash 全通过"""
        from types import SimpleNamespace

        shards = {
            "trial": [{"code": "1001", "amount": "100"}],
            "report": [{"row": "R1"}],
        }
        shard_hashes = {k: _shard_hash(v) for k, v in shards.items()}
        root = _root_hash(shard_hashes)

        manifest = {
            "manifest_version": 2,
            "shard_hashes": shard_hashes,
            "root_hash": root,
            "counts": {k: len(v) for k, v in shards.items()},
        }

        raw = {"project_id": "pid-1", "year": 2025, "shards": shards}
        raw_json = _canonical_json(raw)

        snapshot_data = {
            "_format": _FORMAT_V2,
            "_payload": _compress_payload(raw_json),
            "_hash": root,
            "_locked": True,
            "_manifest": manifest,
            "_meta": {},
        }
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        assert result["hash_valid"] is True
        assert result["root_valid"] is True
        assert result["shard_mismatches"] == []
        assert result["locked"] is True
        assert result["data"]["shards"] == shards

    def test_restore_v2_snapshot_shard_mismatch(self):
        """v2 快照某个分片被篡改，hash_valid=False"""
        from types import SimpleNamespace

        shards = {
            "trial": [{"code": "1001"}],
            "report": [{"row": "R1"}],
        }
        shard_hashes = {
            "trial": _shard_hash(shards["trial"]),
            "report": "fake_hash_not_matching",  # 篡改
        }
        root = _root_hash(shard_hashes)

        manifest = {
            "manifest_version": 2,
            "shard_hashes": shard_hashes,
            "root_hash": root,
        }

        raw = {"shards": shards}
        snapshot_data = {
            "_format": _FORMAT_V2,
            "_payload": _compress_payload(_canonical_json(raw)),
            "_hash": root,
            "_locked": True,
            "_manifest": manifest,
        }
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        assert result["hash_valid"] is False
        assert "report" in result["shard_mismatches"]

    def test_restore_v2_snapshot_root_mismatch(self):
        """v2 快照根 hash 被篡改，hash_valid=False"""
        from types import SimpleNamespace

        shards = {"trial": []}
        shard_hashes = {"trial": _shard_hash(shards["trial"])}
        correct_root = _root_hash(shard_hashes)

        manifest = {
            "manifest_version": 2,
            "shard_hashes": shard_hashes,
            "root_hash": correct_root,
        }

        raw = {"shards": shards}
        snapshot_data = {
            "_format": _FORMAT_V2,
            "_payload": _compress_payload(_canonical_json(raw)),
            "_hash": "tampered_root",  # 篡改的根 hash
            "_locked": False,
            "_manifest": manifest,
        }
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        assert result["hash_valid"] is False
        assert result["root_valid"] is False

    def test_restore_legacy_empty_shell(self):
        """旧空壳快照（无 _format/_payload）安全降级"""
        from types import SimpleNamespace

        snapshot_data = {"created_at": "2026-05-01T00:00:00Z"}
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        assert result["hash_valid"] is False
        assert result["locked"] is False
        assert result.get("legacy") is True
        assert result["data"] == snapshot_data

    def test_restore_v2_flattens_shards_to_top_level(self):
        """v2 还原后的 data 既含 shards，也把各分片展平到顶层（兼容按分片名直接取）"""
        from types import SimpleNamespace

        shards = {"trial": [1, 2], "report": [3, 4]}
        shard_hashes = {k: _shard_hash(v) for k, v in shards.items()}
        root = _root_hash(shard_hashes)

        raw = {"project_id": "pid", "year": 2025, "shards": shards}
        manifest = {
            "manifest_version": 2,
            "shard_hashes": shard_hashes,
            "root_hash": root,
        }
        snapshot_data = {
            "_format": _FORMAT_V2,
            "_payload": _compress_payload(_canonical_json(raw)),
            "_hash": root,
            "_manifest": manifest,
        }
        snapshot = SimpleNamespace(snapshot_data=snapshot_data)

        result = restore_consol_snapshot(snapshot)
        data = result["data"]
        assert data["shards"] == shards
        # 展平到顶层
        assert data["trial"] == [1, 2]
        assert data["report"] == [3, 4]


class TestV2ShardOrderContract:
    """测试 11 类分片顺序契约"""

    def test_shard_order_is_fixed(self):
        """_SHARD_ORDER 包含且仅包含 11 类分片，顺序固定"""
        expected_11 = {
            "tree",
            "worksheet_data",
            "entries",
            "worksheet_calc",
            "trial",
            "report",
            "consol_notes",
            "mappings",
            "formulas",
            "lifecycle",
            "artifact",
        }
        assert set(_SHARD_ORDER) == expected_11
        assert len(_SHARD_ORDER) == 11
        # 顺序固定（用于根 hash 可复现）
        assert _SHARD_ORDER[0] == "tree"
        assert _SHARD_ORDER[4] == "trial"
        assert _SHARD_ORDER[10] == "artifact"

    def test_root_hash_respects_shard_order(self):
        """根 hash 按 _SHARD_ORDER 顺序计算（改变顺序会改变根 hash）"""
        shard_hashes = {"trial": "h1", "tree": "h2"}

        # 按 _SHARD_ORDER：tree 在前，trial 在后
        root1 = _root_hash(shard_hashes)

        # 手工构造反序（不按 _SHARD_ORDER）
        reversed_ordered = [["trial", "h1"], ["tree", "h2"]]
        root2 = _sha256_hex(_canonical_json(reversed_ordered))

        # 顺序不同，hash 不同
        assert root1 != root2
