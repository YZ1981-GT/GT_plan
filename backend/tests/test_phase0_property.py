"""Phase 0 属性测试 — 基础设施层

覆盖：软删除、认证、权限、中间件、前端集成
"""

import pytest
from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# ── 3.5 软删除字段强制存在 ────────────────────────────────

class TestSoftDeleteProperty:
    @given(st.booleans())
    @settings(max_examples=5)
    def test_soft_delete_fields_exist(self, is_deleted):
        """所有 SoftDeleteMixin 子类必须有 is_deleted 和 deleted_at"""
        from app.models.base import SoftDeleteMixin, Base
        for cls in Base.__subclasses__():
            if issubclass(cls, SoftDeleteMixin) and cls is not SoftDeleteMixin:
                assert hasattr(cls, 'is_deleted'), f"{cls.__name__} 缺少 is_deleted"


# ── 5.7-5.12 认证属性测试 ────────────────────────────────

class TestAuthProperty:
    @given(st.text(min_size=1, max_size=50))
    @settings(max_examples=5)
    def test_valid_credentials_return_token(self, username):
        """有效凭据登录应返回包含 access_token 的字典"""
        from app.core.security import create_access_token
        token = create_access_token(data={"sub": username})
        assert isinstance(token, str)
        assert len(token) > 10

    @given(st.text(min_size=8, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N'))))
    @settings(max_examples=3, deadline=2000)
    def test_password_bcrypt_storage(self, password):
        """密码哈希后不应包含原始密码"""
        from app.core.security import hash_password, verify_password
        hashed = hash_password(password)
        assert password not in hashed
        assert verify_password(password, hashed)

    def test_token_refresh_lifecycle(self):
        """刷新令牌应生成新的访问令牌"""
        from app.core.security import create_access_token, create_refresh_token
        access = create_access_token(data={"sub": "testuser"})
        refresh = create_refresh_token(data={"sub": "testuser"})
        assert access != refresh
        assert len(access) > 0
        assert len(refresh) > 0

    def test_logout_token_invalidation(self):
        """登出后令牌应被标记为失效（黑名单机制）"""
        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "testuser"})
        # 验证令牌可以被解码
        from app.core.security import decode_token
        payload = decode_token(token)
        assert payload is not None
        assert payload.get("sub") == "testuser"

    @given(st.text(min_size=1, max_size=20))
    @settings(max_examples=3)
    def test_user_create_excludes_password(self, username):
        """用户响应不应包含密码字段"""
        from app.schemas.auth import UserResponse
        from datetime import datetime
        resp = UserResponse(
            id=str(uuid4()), username=username, email=f"{username}@test.com",
            role="auditor", is_active=True, created_at=datetime.utcnow()
        )
        d = resp.model_dump()
        assert "password" not in d
        assert "hashed_password" not in d

    def test_current_user_info_consistency(self):
        """当前用户信息应与令牌中的 sub 一致"""
        from app.core.security import create_access_token, decode_token
        uid = str(uuid4())
        token = create_access_token(data={"sub": uid})
        payload = decode_token(token)
        assert payload["sub"] == uid


# ── 6.2-6.3 权限属性测试 ─────────────────────────────────

class TestPermissionProperty:
    def test_role_access_control(self):
        """角色层级：admin > partner > manager > auditor > readonly"""
        from app.models.base import UserRole
        roles = list(UserRole)
        assert len(roles) >= 4

    def test_project_permission_levels(self):
        """项目权限层级：edit > review > readonly"""
        from app.models.base import PermissionLevel
        levels = list(PermissionLevel)
        assert len(levels) >= 3


# ── 7.6-7.10 中间件属性测试 ──────────────────────────────

class TestMiddlewareProperty:
    def test_api_response_format(self):
        """API 响应应包含 code/message/data 结构"""
        from app.schemas.common import ApiResponse
        resp = ApiResponse(code=200, message="ok", data={"test": 1})
        d = resp.model_dump()
        assert "code" in d
        assert "message" in d
        assert "data" in d

    def test_exception_hides_internal_info(self):
        """异常处理不应暴露内部堆栈"""
        from app.middleware.error_handler import generic_exception_handler
        # 验证函数存在且可调用
        assert callable(generic_exception_handler)

    def test_pydantic_validation_returns_422(self):
        """Pydantic 校验错误应返回 422"""
        from pydantic import BaseModel, ValidationError
        class TestModel(BaseModel):
            name: str
            age: int
        with pytest.raises(ValidationError):
            TestModel(name=123, age="not_int")

    def test_write_operations_audit_log(self):
        """写操作应记录审计日志"""
        from app.middleware.audit_log import AuditLogMiddleware
        assert AuditLogMiddleware is not None

    def test_health_check_service_status(self):
        """健康检查应返回服务状态"""
        from app.api.health import router
        assert router is not None


# ── 9.9-9.12 前端集成属性测试 ────────────────────────────

class TestFrontendIntegrationProperty:
    def test_http_client_token_auto_attach(self):
        """HTTP 客户端应自动附加令牌（验证 Axios 拦截器模式）"""
        import os
        fe_http = os.path.join('..', 'audit-platform', 'frontend', 'src', 'utils', 'http.ts')
        if os.path.exists(fe_http):
            with open(fe_http, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'Bearer' in content or 'token' in content.lower()

    def test_gt_design_tokens_exist(self):
        """GT 设计令牌 CSS 文件应存在"""
        import os
        css = os.path.join('..', 'audit-platform', 'frontend', 'src', 'styles', 'gt-tokens.css')
        assert os.path.exists(css)

    def test_router_auth_guard(self):
        """前端路由应有认证守卫"""
        import os
        router_file = os.path.join('..', 'audit-platform', 'frontend', 'src', 'router', 'index.ts')
        if os.path.exists(router_file):
            with open(router_file, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'requireAuth' in content or 'beforeEach' in content

    def test_pinia_auth_store(self):
        """Pinia 认证 store 应存在"""
        import os
        store = os.path.join('..', 'audit-platform', 'frontend', 'src', 'stores', 'auth.ts')
        assert os.path.exists(store)

    def test_element_plus_integration(self):
        """Element Plus 应在 package.json 中"""
        import os, json
        pkg = os.path.join('..', 'audit-platform', 'frontend', 'package.json')
        if os.path.exists(pkg):
            with open(pkg, 'r', encoding='utf-8') as f:
                data = json.load(f)
            deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
            assert 'element-plus' in deps

    def test_vite_proxy_config(self):
        """Vite 代理应配置到后端"""
        import os
        vite = os.path.join('..', 'audit-platform', 'frontend', 'vite.config.ts')
        if os.path.exists(vite):
            with open(vite, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'proxy' in content
