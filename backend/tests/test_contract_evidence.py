"""合同证据单测（Spec F FEAT-001 F2）：normalize / label / 查询 / 复用。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ─── normalize_contract_key ──────────────────────────────────────────────────


class TestNormalizeContractKey:
    """normalize_contract_key 校验与规范化。"""

    def test_none_returns_none(self):
        from app.services.contract_evidence import normalize_contract_key

        assert normalize_contract_key(None) is None

    def test_empty_returns_none(self):
        from app.services.contract_evidence import normalize_contract_key

        assert normalize_contract_key("") is None
        assert normalize_contract_key("  ") is None

    def test_valid_json_array(self):
        from app.services.contract_evidence import normalize_contract_key

        result = normalize_contract_key('["HT-001","甲方公司"]')
        parsed = json.loads(result)
        assert parsed == ["HT-001", "甲方公司"]

    def test_valid_plain_string(self):
        """纯合同号回退到 ["合同号", ""]。"""
        from app.services.contract_evidence import normalize_contract_key

        result = normalize_contract_key("HT-001")
        parsed = json.loads(result)
        assert parsed == ["HT-001", ""]

    def test_too_long_raises_400(self):
        from app.services.contract_evidence import normalize_contract_key

        with pytest.raises(HTTPException) as exc_info:
            normalize_contract_key("x" * 601)
        assert exc_info.value.status_code == 400
        assert "过长" in exc_info.value.detail

    def test_empty_contract_no_raises_400(self):
        from app.services.contract_evidence import normalize_contract_key

        with pytest.raises(HTTPException) as exc_info:
            normalize_contract_key('[" ","对方"]')
        assert exc_info.value.status_code == 400
        assert "缺少合同号" in exc_info.value.detail

    def test_whitespace_trimmed(self):
        from app.services.contract_evidence import normalize_contract_key

        result = normalize_contract_key('  ["  HT-002 "," 乙方 "]  ')
        parsed = json.loads(result)
        assert parsed == ["HT-002", "乙方"]

    def test_wrong_array_length_falls_back_to_string(self):
        """非二元素数组回退到纯字符串解析。"""
        from app.services.contract_evidence import normalize_contract_key

        result = normalize_contract_key('["HT-001"]')
        parsed = json.loads(result)
        assert parsed[0] == '["HT-001"]'

    def test_idempotent(self):
        """规范串再次传入 ⇒ 不变。"""
        from app.services.contract_evidence import normalize_contract_key

        first = normalize_contract_key('["HT-001","甲方"]')
        second = normalize_contract_key(first)
        assert first == second


# ─── contract_key_label ──────────────────────────────────────────────────────


class TestContractKeyLabel:
    def test_with_counterparty(self):
        from app.services.contract_evidence import contract_key_label

        label = contract_key_label('["HT-001","甲方公司"]')
        assert label == "HT-001 / 甲方公司"

    def test_without_counterparty(self):
        from app.services.contract_evidence import contract_key_label

        label = contract_key_label('["HT-001",""]')
        assert label == "HT-001"

    def test_none(self):
        from app.services.contract_evidence import contract_key_label

        assert contract_key_label(None) == ""

    def test_unparseable(self):
        from app.services.contract_evidence import contract_key_label

        assert contract_key_label("not-json") == "not-json"


# ─── contract_evidence_by_keys ──────────────────────────────────────────────


class TestContractEvidenceByKeys:
    @pytest.mark.asyncio
    async def test_too_many_keys_raises_422(self):
        from app.services.contract_evidence import contract_evidence_by_keys, MAX_QUERY_KEYS

        db = AsyncMock()
        user = MagicMock()
        keys = [f'["HT-{i:04d}","对方"]' for i in range(MAX_QUERY_KEYS + 1)]
        with pytest.raises(HTTPException) as exc_info:
            await contract_evidence_by_keys(db, user, uuid.uuid4(), keys)
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_keys_returns_empty(self):
        from app.services.contract_evidence import contract_evidence_by_keys

        db = AsyncMock()
        user = MagicMock()
        result = await contract_evidence_by_keys(db, user, uuid.uuid4(), [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_invalid_keys_returns_empty(self):
        from app.services.contract_evidence import contract_evidence_by_keys

        db = AsyncMock()
        user = MagicMock()
        # 空合同号 ⇒ normalize 抛 400，被跳过返回空
        result = await contract_evidence_by_keys(db, user, uuid.uuid4(), ['["",""]'])
        assert result == {}


# ─── reuse_contract_evidence ────────────────────────────────────────────────


class TestReuseContractEvidence:
    @pytest.mark.asyncio
    async def test_empty_key_raises_400(self):
        from app.services.contract_evidence import reuse_contract_evidence

        db = AsyncMock()
        user = MagicMock()
        wp = MagicMock()
        wp.project_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await reuse_contract_evidence(db, user, wp, "", uuid.uuid4())
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_source_not_found_raises_404(self):
        from app.services.contract_evidence import reuse_contract_evidence

        db = AsyncMock()
        # 模拟空查询结果
        mock_result = MagicMock()
        mock_result.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        user = MagicMock()
        wp = MagicMock()
        wp.id = uuid.uuid4()
        wp.project_id = uuid.uuid4()
        with pytest.raises(HTTPException) as exc_info:
            await reuse_contract_evidence(db, user, wp, '["HT-001","甲方"]', uuid.uuid4())
        assert exc_info.value.status_code == 404


# ─── EvidenceLink ORM 字段 ──────────────────────────────────────────────────


class TestEvidenceLinkORM:
    def test_contract_key_field_exists(self):
        from app.models.wp_optimization_models import EvidenceLink

        assert hasattr(EvidenceLink, "contract_key"), "EvidenceLink 须有 contract_key 列"

    def test_contract_key_nullable(self):
        from app.models.wp_optimization_models import EvidenceLink

        col = EvidenceLink.__table__.c.contract_key
        assert col.nullable is True


# ─── 变异测试 ────────────────────────────────────────────────────────────────


class TestMutationDetection:
    """变异证明：去掉关键校验后本组测试变红。"""

    def test_remove_validation_makes_empty_no_pass(self):
        """normalize_contract_key 里删掉合同号非空校验 ⇒ 空合同号被放行。"""
        from app.services.contract_evidence import normalize_contract_key

        # 当前实现正确拒绝空合同号
        with pytest.raises(HTTPException):
            normalize_contract_key('[" ","对方"]')
        # 如果校验被删除，这里不会抛异常 ⇒ 测试变红

    def test_remove_length_check_makes_long_pass(self):
        """normalize_contract_key 里删掉长度校验 ⇒ 超长输入被放行。"""
        from app.services.contract_evidence import normalize_contract_key

        with pytest.raises(HTTPException):
            normalize_contract_key("x" * 601)
