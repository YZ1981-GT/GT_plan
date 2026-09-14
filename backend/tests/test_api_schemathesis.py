"""Schemathesis API fuzz（endpoint-fuzz-and-tracing spec）。

仅 fuzz GET 端点，主断言 = 无 5xx（抓崩溃端点）。
认证用 dependency_overrides 注入 fake admin user（全仓无 Bearer token 体系）。
标 pg_only：大量端点用 PG 专属裸 SQL，SQLite 下 500 非真实 bug。

Validates: Requirements 1.1, 1.2, 1.3, 1.5
"""

from __future__ import annotations

import uuid

import pytest

schemathesis = pytest.importorskip("schemathesis")
from hypothesis import settings as hyp_settings  # noqa: E402

import fakeredis.aioredis  # noqa: E402

from app.core.config import settings as app_settings  # noqa: E402
from app.core.redis import get_redis  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models.base import UserRole  # noqa: E402


# ---------------------------------------------------------------------------
# Allowlist：已知问题端点豁免（增量收敛——修一个从列表移除一个）
# ---------------------------------------------------------------------------
_SCHEMA_ALLOWLIST: set[str] = set()


# ---------------------------------------------------------------------------
# Fake admin user（仿 _test_auth_helper.FakeAuthUser，role 用 UserRole enum）
# ---------------------------------------------------------------------------
class _FakeAdminUser:
    """最小化 User 替身，admin 角色绕过项目权限检查。"""

    def __init__(self) -> None:
        self.id = uuid.UUID("00000000-0000-0000-0000-000000000099")
        self.username = "schemathesis_admin"
        self.role = UserRole.admin
        self.is_active = True
        self.is_deleted = False
        self.email = "schemathesis@test.local"


# ---------------------------------------------------------------------------
# Fixture：对 app.dependency_overrides 注入认证 + Redis
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _auth_and_deps_override():
    """注入 fake admin user / fake redis 到 app.dependency_overrides。

    DB（get_db）不做 override：pg_only 环境下 app 自身连接真实 PG 测试库。
    只读 GET fuzz 不写数据，无需隔离事务；PG 环境下 app 的 get_db 直接可用。
    Redis 用 fakeredis 避免依赖真实 Redis 实例。
    """
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _override_current_user():
        return _FakeAdminUser()

    async def _override_redis():
        yield fake_redis

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_redis] = _override_redis
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Schema：只 fuzz GET 端点（写端点排除，避免污染 DB）
# force_schema_version="30"：FastAPI 默认生成 OpenAPI 3.1.0，schemathesis 3.x
# 尚未完全支持 3.1，强制当 3.0 解析即可（结构差异对 fuzz 无影响）。
# ---------------------------------------------------------------------------
_base_schema = schemathesis.from_asgi(
    "/openapi.json",
    app=app,
    force_schema_version="30",
)
schema = _base_schema.include(method="GET")


# ---------------------------------------------------------------------------
# Fuzz test
# ---------------------------------------------------------------------------
@schema.parametrize()
@hyp_settings(max_examples=app_settings.SCHEMATHESIS_MAX_EXAMPLES, deadline=None)
@pytest.mark.pg_only
def test_api_no_5xx(case):
    """主断言：所有 GET 端点不得返回 5xx。

    不用 case.validate_response()——ResponseWrapperMiddleware 把所有 2xx 包成
    {code, message, data} 信封，但 openapi.json 声明未包装 schema，直接比对会
    全端点误报。schema 校验改为解信封后软校验（增量收敛目标）。
    """
    if case.path in _SCHEMA_ALLOWLIST:
        pytest.skip(f"allowlisted: {case.path}")

    response = case.call_asgi()

    # 主断言：无 5xx（核心价值——抓服务端崩溃）
    assert response.status_code < 500, (
        f"{case.method} {case.path} -> {response.status_code}"
    )

    # 软校验：解信封后对 data 做基本结构检查（best-effort，不作为硬断言）
    if response.status_code == 200:
        try:
            body = response.json()
        except Exception:
            return  # 非 JSON 响应（如文件下载），跳过软校验
        # 解信封：若响应结构为 {code, message, data}，提取 data
        if (
            isinstance(body, dict)
            and {"code", "message", "data"} <= set(body)
        ):
            _data = body["data"]  # noqa: F841  — 预留后续 schema 校验
            # TODO: 增量收敛目标——对 _data 做 openapi schema 软校验
