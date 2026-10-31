"""项目段参数写成 ``{pid}`` 的路由的鉴权覆盖（spec project-pid-path-authz-coverage）。

鉴权基线守卫 ``test_project_endpoint_authorization_baseline.py`` 的三个维度原先只认字面量 ``{project_id}``：
49 条 ``/api/projects/{pid}/…`` 路由从未进视野，其中 AI 批量复核 / 进度 / 导出三个一个鉴权依赖都没有（未登录可调），
截止测试四个、抽凭历史与对比两个只校验登录（任意登录用户可跨项目读写）。现在三个维度都按 ``_has_project_segment``
判项目段；本文件钉住：①``{pid}`` 路由全部进视野且全部是项目级 ②新记作项目级的 token 真的校验了路径项目 / 对象归属
③``{pid}`` 路由上不得挂按名字取 ``project_id`` 的依赖（会变成必填查询参数，前端不带 ⇒ 422）。
"""

from __future__ import annotations

import ast
import functools

import pytest

from tests import test_project_endpoint_authorization_baseline as base

_ROUTERS = base._ROUTERS

#: 现算 2026-10-31：49 条（程序裁剪 / 委派 / 投递 / 主编 22、版本链 5、程序复核 3、抽样阶段 5、抽凭 6、截止测试 4、AI 复核 3）
_PID_ROUTE_MIN = 49


@functools.lru_cache(maxsize=None)
def _defs(rel: str) -> dict[str, ast.AST]:
    tree = ast.parse((_ROUTERS / rel).read_text(encoding="utf-8-sig", errors="replace"))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _pid_endpoints() -> dict[str, tuple[str, str]]:
    """全部路由文件里完整路径的项目段参数名不是 project_id 的端点 → (METHOD /完整路径, 档位)。"""
    out: dict[str, tuple[str, str]] = {}
    for f in sorted(_ROUTERS.rglob("*.py")):
        rel = f.relative_to(_ROUTERS).as_posix()
        src = f.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(src)
        routers = base._router_vars(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                seg = ast.get_source_segment(src, d) or ""
                m = base._ANY_DECOR.search(seg if seg.startswith("@") else "@" + seg)
                if not m:
                    continue
                var, method, path = m.groups()
                prefix, router_deps = routers.get(var, ("", set()))
                full = prefix + path
                seg_m = base._PROJECT_SEG.search(full)
                if seg_m and "{project_id}" not in full:
                    names = base._auth_names_in_node(node) | router_deps
                    tier = "project" if base._matches(names, base._PROJECT_LEVEL_TOKENS) else \
                        "identity" if base._matches(names, base._IDENTITY_ONLY_TOKENS) else "none"
                    out[f"{rel}::{node.name}"] = (f"{method.upper()} {full}", tier)
                break
    return out


def test_pid_routes_are_in_view_of_both_scanners():
    """``{pid}`` 路由进视野：装饰器路径自带项目段的进上两维（AI 复核三个），其余进前缀维。"""
    pid = _pid_endpoints()
    assert len(pid) >= _PID_ROUTE_MIN, f"只扫到 {len(pid)} 个 {{pid}} 端点"
    prefixed = {k for k, _, _ in base._scan_prefixed()}
    decorated = {k for k in pid if "/projects/{pid}" in pid[k][0] and k.startswith("review_prompt.py::")}
    assert decorated == {
        "review_prompt.py::batch_review",
        "review_prompt.py::get_batch_review_progress",
        "review_prompt.py::export_review_report",
    }
    missing = sorted(set(pid) - decorated - prefixed)
    assert not missing, f"{{pid}} 端点不在前缀维：{missing}"
    assert base._total_project_endpoints() >= 300 + len(decorated)


def test_every_pid_endpoint_is_project_level():
    """``{pid}`` 端点全部是项目级（无鉴权 / 仅登录各 0）。"""
    bad = {k: v for k, v in _pid_endpoints().items() if v[1] != "project"}
    assert not bad, "\n".join(f"{k}  {route}  [{tier}]" for k, (route, tier) in sorted(bad.items()))


def test_pid_routes_do_not_use_project_id_param_factories():
    """``require_project_access`` / ``require_project_permission`` 的内层依赖按名字取 ``project_id``：挂到
    ``{pid}`` 路由上会变成必填查询参数（前端不带 ⇒ 422）。``{pid}`` 路由用函数体首句 ``assert_project_permission``。"""
    trap = ("require_project_access", "require_project_permission")
    hits = []
    for f in sorted(_ROUTERS.rglob("*.py")):
        rel = f.relative_to(_ROUTERS).as_posix()
        src = f.read_text(encoding="utf-8-sig", errors="replace")
        tree = ast.parse(src)
        routers = base._router_vars(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                seg = ast.get_source_segment(src, d) or ""
                m = base._ANY_DECOR.search(seg if seg.startswith("@") else "@" + seg)
                if not m:
                    continue
                var, _method, path = m.groups()
                prefix, router_deps = routers.get(var, ("", set()))
                full = prefix + path
                if base._PROJECT_SEG.search(full) and "{project_id}" not in full:
                    if (base._auth_names_in_node(node) | router_deps) & set(trap):
                        hits.append(f"{rel}::{node.name}")
                break
    assert not hits, hits


def test_project_segment_predicate_self_check():
    assert base._has_project_segment("/api/projects/{pid}/batch-review")
    assert base._has_project_segment("/api/projects/{project_id}/x")
    assert base._has_project_segment("/{project_id}/x")
    assert base._has_project_segment("/api/projects/{pid:uuid}/x")
    assert not base._has_project_segment("/{pid}/procedure-trim/preview")  # 前缀里才有 /projects/，归前缀维
    assert not base._has_project_segment("/api/workpapers/{wp_id}/review")


def test_prefixed_scanner_sees_pid_samples():
    """合成样本：前缀带 {pid} 无鉴权 → none；前缀 /api/projects + 装饰器 /{pid}/… 有项目级 → project；仅登录 → identity。"""
    sample = (
        'bare = APIRouter(prefix="/api/projects/{pid}/x")\n'
        'router = APIRouter(prefix="/api/projects")\n'
        '@bare.get("/a")\n'
        "async def no_auth(pid, db = Depends(get_db)):\n"
        "    return {}\n"
        '@router.post("/{pid}/b")\n'
        "async def checked(pid, db = Depends(get_db), user = Depends(get_current_user)):\n"
        "    await assert_project_permission(db, user, pid, 'edit')\n"
        "    return {}\n"
        '@router.get("/{pid}/c")\n'
        "async def login_only(pid, user = Depends(get_current_user)):\n"
        "    return {}\n"
    )
    got = {k: tier for k, _, tier in base._scan_prefixed_source("s.py", sample)}
    assert got == {"s.py::no_auth": "none", "s.py::checked": "project", "s.py::login_only": "identity"}, got


# ── 新记作项目级的 token：可伪证 ───────────────────────────────────────────────


def _calls(node: ast.AST, name: str) -> list[ast.Call]:
    return [
        c for c in ast.walk(node)
        if isinstance(c, ast.Call)
        and ((isinstance(c.func, ast.Name) and c.func.id == name) or (isinstance(c.func, ast.Attribute) and c.func.attr == name))
    ]


def _kw_is_name(call: ast.Call, kw: str, value: str) -> bool:
    return any(k.arg == kw and isinstance(k.value, ast.Name) and k.value.id == value for k in call.keywords)


@pytest.mark.parametrize("gate", ["enforce_wp_gate", "enforce_task_gate"])
def test_wp_and_task_gates_are_really_project_level(gate: str):
    """底稿门 / 任务门：把 ``project_id`` 交进请求、交给 ``resolve_wp_binding_and_access`` 判定（拒绝即 404，
    跨项目 PG 用例见 procedure_delegation_visibility/test_task9_core_route_gate.py）；``{pid}`` 端点调用时都传了 ``project_id=pid``。"""
    fn = _defs("_wp_gate.py")[gate]
    assert any(_kw_is_name(c, "project_id", "project_id") for c in ast.walk(fn) if isinstance(c, ast.Call)), \
        f"{gate} 不再把 project_id 交进门的请求"
    assert _calls(fn, "resolve_wp_binding_and_access"), f"{gate} 不再调 resolve_wp_binding_and_access"
    users = [k for k in _pid_endpoints() if gate in base._auth_names_in_node(_defs(k.split("::")[0])[k.split("::")[1]])]
    assert users, f"{{pid}} 端点里没人用 {gate}，token 失去依据"
    for key in users:
        rel, name = key.split("::")
        assert any(_kw_is_name(c, "project_id", "pid") for c in _calls(_defs(rel)[name], gate)), f"{key} 调 {gate} 没传 project_id=pid"


def test_conversation_access_token_is_really_project_level():
    """程序复核参与者判定：引用它的端点都先 ``_load_task``（任务须属于路径项目，跨项目 404），访问级别不足时 403；
    无关用户判为 none 的行为证据见 procedure_delegation/test_procedure_review_service.py。"""
    defs = _defs("procedure_review.py")
    assert _calls(defs["_load_task"], "assert_task_in_project"), "_load_task 不再校验任务属于路径项目"
    users = [d for d in defs.values() if _calls(d, "resolve_conversation_access") and d.name != "_load_task"]
    assert len(users) >= 2
    for fn in users:
        names = base._auth_names_in_node(fn)
        assert "_load_task" in names or "enforce_task_gate" in names, f"{fn.name} 没绑定路径项目"
        raises_403 = any(
            isinstance(r, ast.Raise) and isinstance(r.exc, ast.Call)
            and any(k.arg == "status_code" and isinstance(k.value, ast.Constant) and k.value.value == 403 for k in r.exc.keywords)
            for r in ast.walk(fn)
        )
        assert raises_403, f"{fn.name} 访问级别不足时不报 403"


_SAMPLING_HELPERS = {
    "_authorize_survival": "sampling_phase.py",
    "_authorize_and_validate_extract": "voucher_sampling.py",
    "_authorize_and_validate_evaluation": "voucher_sampling.py",
    "_authorize_undo": "voucher_sampling.py",
    "_authorize_cutoff_wp": "cutoff_sampling.py",
}


@pytest.mark.parametrize("helper", sorted(_SAMPLING_HELPERS))
def test_sampling_authorize_helpers_are_really_project_level(helper: str):
    """抽样本地鉴权辅助函数：只在登记的文件里定义一份；调 ``authorize_wp_edit`` / ``authorize_wp_read``，
    并把底稿所属项目与路径 ``pid`` 比较、不等即 403。"""
    owners = [f.relative_to(_ROUTERS).as_posix() for f in sorted(_ROUTERS.rglob("*.py")) if helper in _defs(f.relative_to(_ROUTERS).as_posix())]
    assert owners == [_SAMPLING_HELPERS[helper]], f"{helper} 定义处：{owners}"
    fn = _defs(owners[0])[helper]
    names = base._auth_names_in_node(fn)
    assert {"authorize_wp_edit", "authorize_wp_read"} & names, f"{helper} 不再校验底稿权限"
    compares_pid = any(
        isinstance(c, ast.Compare) and any(isinstance(n, ast.Name) and n.id == "pid" for n in ast.walk(c))
        for c in ast.walk(fn)
    )
    assert compares_pid, f"{helper} 不再核对底稿属于路径项目"
    assert any(
        isinstance(r, ast.Raise) and isinstance(r.exc, ast.Call)
        and any(k.arg == "status_code" and isinstance(k.value, ast.Constant) and k.value.value == 403 for k in r.exc.keywords)
        for r in ast.walk(fn)
    ), f"{helper} 不属于路径项目时不报 403"


def test_review_prompt_router_has_no_unauthenticated_endpoint():
    """review_prompt 全文件原先 7 个端点一个鉴权依赖都没有（含非项目路径的单底稿复核、改发现状态）：逐个都要至少登录，
    读写项目数据的 5 个要项目级。"""
    defs = _defs("review_prompt.py")
    endpoints = {
        name: fn for name, fn in defs.items()
        if any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") in {"get", "post", "put", "patch", "delete"}
               for d in fn.decorator_list)
    }
    assert len(endpoints) == 7, sorted(endpoints)
    project_level = {"review_workpaper", "update_finding_status", "get_batch_review_progress", "batch_review", "export_review_report"}
    for name, fn in endpoints.items():
        names = base._auth_names_in_node(fn)
        assert base._matches(names, base._AUTH_TOKENS), f"{name} 没有任何鉴权"
        if name in project_level:
            assert base._matches(names, base._PROJECT_LEVEL_TOKENS), f"{name} 只校验登录"


def test_pid_scanner_falls_back_to_literal_if_reverted(monkeypatch):
    """反向自检：项目段判定退回只认字面量 {project_id} 时，{pid} 端点在两维都消失（本文件的判据随之失效会被看见）。"""
    monkeypatch.setattr(base, "_has_project_segment", lambda p: "{project_id}" in p)
    base._scan_prefixed.cache_clear()
    try:
        prefixed = {k for k, _, _ in base._scan_prefixed()}
        assert not any(k.startswith(("cutoff_sampling.py::", "version_trail.py::")) for k in prefixed)
    finally:
        base._scan_prefixed.cache_clear()
