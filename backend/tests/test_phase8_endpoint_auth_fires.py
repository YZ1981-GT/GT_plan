"""Phase 8 Task 8：证明补上的项目级鉴权**真的会拦**（端点级 TestClient，不只 AST 看依赖挂没挂）。

memory 铁律 ㉕：新增端点必做端点级测试，只测 service / 只看依赖挂没挂会漏掉「挂了但不生效」。
这里对三类代表端点各发一个**不带有效会话**的请求，断言不是 200（被鉴权拦住）：
- 路由级 dependencies（b5_version / wp_review_status / cf_verification 读）
- 端点级 Depends（ledger_penetration.penetrate / sign_convention 写）

🔴 不 override require_project_access（它是依赖工厂、每次返回新函数对象，key 匹配不上会静默失效 → 全 401 假绿）。
这里走真实依赖链：不提供令牌 ⇒ get_current_user 先抛 401，证明「鉴权在请求路径上真的跑了」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_PID = "2aa00f57-1df4-4fe8-9840-2d65d0fd8749"

# (模块, 路由变量, METHOD, 路径, 期望被拦)
_CASES = [
    ("app.routers.b5_version", "router", "get", f"/api/projects/{_PID}/b5/recommended-version"),
    ("app.routers.wp_review_status", "router", "get", f"/api/projects/{_PID}/workpapers/review-status"),
    ("app.routers.auto_data", "router", "get", f"/api/projects/{_PID}/auto-data/a15_financial_ratios?year=2025"),
    ("app.routers.ledger_penetration", "router", "get", f"/api/projects/{_PID}/ledger/penetrate?year=2025"),
    ("app.routers.cf_verification", "router", "get", f"/api/projects/{_PID}/cf-verification/2025/cash-equivalents"),
]


@pytest.mark.parametrize("module,var,method,path", _CASES, ids=[c[3].split("?")[0] for c in _CASES])
def test_unauthenticated_request_is_rejected(module: str, var: str, method: str, path: str) -> None:
    import importlib

    mod = importlib.import_module(module)
    app = FastAPI()
    app.include_router(getattr(mod, var))
    client = TestClient(app, raise_server_exceptions=False)
    resp = getattr(client, method)(path)  # 不带 Authorization 头
    assert resp.status_code != 200, (
        f"{method.upper()} {path} 未带令牌却返回 200 —— 项目级鉴权没有生效（依赖挂了但没跑）"
    )
    # 未登录应是 401（get_current_user 先拦）；403 亦可接受（已登录但无项目权限的真实场景）
    assert resp.status_code in (401, 403), f"期望 401/403，实际 {resp.status_code}"


def test_cases_cover_router_level_and_endpoint_level() -> None:
    """自检：样本同时覆盖路由级 dependencies 与端点级 Depends 两种写法，否则只验了一半。"""
    import ast

    router_level = "b5_version"  # dependencies=[...] 在 APIRouter(...)
    endpoint_level = "ledger_penetration"  # Depends 在 penetrate 函数签名
    src_router = (_BACKEND / "app/routers/b5_version.py").read_text(encoding="utf-8")
    src_ep = (_BACKEND / "app/routers/ledger_penetration.py").read_text(encoding="utf-8")
    assert "dependencies=[Depends(require_project_access" in src_router, f"{router_level} 不是路由级写法"
    # penetrate 函数体内有 require_project_access
    tree = ast.parse(src_ep)
    pen = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "penetrate")
    assert any("require_project_access" in (ast.get_source_segment(src_ep, a) or "")
               for a in pen.args.args + pen.args.kwonlyargs) or \
        "require_project_access" in (ast.get_source_segment(src_ep, pen) or ""), f"{endpoint_level} 不是端点级写法"
