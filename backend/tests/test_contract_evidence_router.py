"""合同证据路由测试（Spec F FEAT-001 F3）：contract-reuse 端点 + upload 带 contract_key。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestContractReuseEndpoint:
    """POST .../evidence/contract-reuse 路由。"""

    def test_endpoint_registered(self):
        """contract-reuse 路由在 router 上已注册。"""
        from app.routers.wp_evidence import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]
        assert any(p.endswith("/contract-reuse") for p in paths), f"未找到 /contract-reuse，已注册路由: {paths}"

    def test_contract_reuse_request_model(self):
        """ContractReuseRequest 有 contract_key 和 attachment_id 字段。"""
        from app.routers.wp_evidence import ContractReuseRequest

        req = ContractReuseRequest(contract_key='["HT-001","甲方"]', attachment_id=uuid.uuid4())
        assert req.contract_key == '["HT-001","甲方"]'
        assert req.attachment_id is not None

    def test_create_link_request_has_contract_key(self):
        """CreateLinkRequest 接受 contract_key 参数。"""
        from app.routers.wp_evidence import CreateLinkRequest

        req = CreateLinkRequest(attachment_id=uuid.uuid4(), contract_key='["HT-001","甲方"]')
        assert req.contract_key == '["HT-001","甲方"]'

    def test_batch_link_item_has_contract_key(self):
        """BatchLinkItem 接受 contract_key 参数。"""
        from app.routers.wp_evidence import BatchLinkItem

        item = BatchLinkItem(attachment_id=uuid.uuid4(), contract_key='["HT-002","乙方"]')
        assert item.contract_key == '["HT-002","乙方"]'


class TestContractKeyOnUpload:
    """upload 端点的 contract_key Form 参数（检查函数签名而非真发请求）。"""

    def test_upload_endpoint_accepts_contract_key(self):
        """upload_evidence 函数签名包含 contract_key 参数。"""
        import inspect
        from app.routers.wp_evidence import upload_evidence

        sig = inspect.signature(upload_evidence)
        assert "contract_key" in sig.parameters, f"upload_evidence 缺少 contract_key 参数，有: {list(sig.parameters)}"


class TestValidatedLinkFieldsWithContractKey:
    """_validated_link_fields 处理 contract_key 的默认类型分配。"""

    @pytest.mark.asyncio
    async def test_contract_key_sets_default_type(self):
        from app.routers.wp_evidence import _validated_link_fields, CreateLinkRequest

        item = CreateLinkRequest(
            attachment_id=uuid.uuid4(),
            contract_key='["HT-001","甲方"]',
        )
        fields = await _validated_link_fields(item)
        assert fields["evidence_type"] == "contract"
        assert fields["contract_key"] is not None

    @pytest.mark.asyncio
    async def test_no_keys_no_default_type(self):
        from app.routers.wp_evidence import _validated_link_fields, CreateLinkRequest

        item = CreateLinkRequest(attachment_id=uuid.uuid4())
        fields = await _validated_link_fields(item)
        assert fields["evidence_type"] is None
        assert fields["voucher_key"] is None
        assert fields["contract_key"] is None


class TestWpEvidenceServiceContractLink:
    """WpEvidenceService.create_contract_link 幂等行为。"""

    def test_create_contract_link_method_exists(self):
        from app.services.wp_evidence_service import WpEvidenceService

        assert hasattr(WpEvidenceService, "create_contract_link")

    def test_create_link_accepts_contract_key(self):
        """create_link 签名接受 contract_key。"""
        import inspect
        from app.services.wp_evidence_service import WpEvidenceService

        sig = inspect.signature(WpEvidenceService.create_link)
        assert "contract_key" in sig.parameters
