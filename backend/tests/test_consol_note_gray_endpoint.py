"""合并附注 V2 灰度配置端点 路由契约测试（consol-disclosure-note-persistence Req4）。

补 Task 6 端点的覆盖缺口：Task 7 只测了 service 层，Req4 的端点（尤其 Req4.4
路径非冲突）无守卫。本测试以 ASGITransport 打真实 app 路由表，DB-free / auth-free：

- Req4.1/4.2 GET/PUT 已注册（不 404）
- **Req4.4 路径非冲突（核心）**：`/{project_id}/config/consol-note-gray`（3 段静态）
  不被 `/{project_id}/{year}`（year:int）或任何 3 段路由吞掉 —— 命中本端点则先过
  require_project_access（无 token → 401/403），而非 year 路由的 422（int 解析 `config` 失败）。

正向 200 round-trip / flag_modified 落库 / 404（Req4.2/4.3）由 service 层 Property
测试 + live 覆盖（避免 conftest DB fixture 的 FK 依赖）。

Validates: Requirements 4.1, 4.4
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

_BASE = "/api/consolidation/notes"
_PID = uuid.uuid4()
_PATH = f"{_BASE}/{_PID}/config/consol-note-gray"


class TestConsolNoteGrayEndpointRouting:
    @pytest.mark.asyncio
    async def test_get_route_registered_and_no_year_collision(self):
        """GET 灰度配置：命中本端点（401/403 鉴权拦截），非 404/422（未注册/被 year 吞）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(_PATH)
        # 404 = 未注册；422 = 被 /{project_id}/{year} 吞掉（config 当 int 解析失败）
        assert resp.status_code != 404, "灰度配置 GET 路由未注册"
        assert resp.status_code != 422, "路径被 /{project_id}/{year} 吞掉（Req4.4 冲突）"
        # 命中本端点 → 先过 require_project_access（无 token）→ 401/403
        assert resp.status_code in (401, 403), f"预期鉴权拦截，实际 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_put_route_registered_and_no_year_collision(self):
        """PUT 灰度配置：带合法 body 仍被鉴权拦截（route 已注册且非冲突）。"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.put(_PATH, json={"enabled": True})
        assert resp.status_code != 404, "灰度配置 PUT 路由未注册"
        assert resp.status_code != 422, "路径被 /{project_id}/{year} 吞掉或 body 契约不符"
        assert resp.status_code in (401, 403), f"预期鉴权拦截，实际 {resp.status_code}"

    def test_gray_config_path_present_in_app_routes(self):
        """路由表存在灰度配置 path（GET + PUT 各一条）。"""
        template = _BASE + "/{project_id}/config/consol-note-gray"
        matched = [
            r for r in app.routes
            if getattr(r, "path", None) == template
        ]
        methods = set()
        for r in matched:
            methods |= (getattr(r, "methods", None) or set())
        assert "GET" in methods, "灰度配置 GET 未在路由表"
        assert "PUT" in methods, "灰度配置 PUT 未在路由表"
