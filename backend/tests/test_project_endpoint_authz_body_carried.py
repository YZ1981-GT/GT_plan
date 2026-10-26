"""项目端点鉴权基线 · 第三维：项目在请求体 / 查询参数里的端点（spec formula-governance-coverage-closure R1.7）。

``test_project_endpoint_authorization_baseline`` 前两维只看完整路径里的 ``{project_id}``；项目放在**请求体或查询参数**
的端点整类脱管 —— 本 spec 抓到的公式调试（按请求体项目原样回显试算表 / 报表）、公式导入（按查询参数项目做引用解析）、
全局一键刷新（按请求体项目批量改写）都是这种形态。路径含 ``{wp_id}`` / ``{wp_index_id}`` 的端点不在本维：它们经
router_registry 统一挂 router 级 ``dedicated_wp_gate``（按路径上的对象反查项目判可见性）。

口径（全部用 AST，与基线文件同一套鉴权标识，禁文本匹配 —— memory ㉖）：
* 「带项目」：函数有名为 ``project_id`` 的参数，或读了某个参数的 ``.project_id`` 属性（请求体模型）；
* 档位：引用了项目级标识 = ``project``；只有身份认证 = ``identity``；都没有 = ``none``。
  项目级标识 = 基线文件的 ``_PROJECT_LEVEL_TOKENS`` + 本维额外认可的本地 / 服务层 helper（``_EXTRA_PROJECT_TOKENS``，
  每个都有可伪证的证明链，且路由里用到的必须就是证明过的那一份）。
本维只冻结上限（棘轮只许向下）并钉住本 spec 修过的端点；其余端点跨多个业务域，不在本 spec 逐个修（另立 spec）。
"""
from __future__ import annotations

import ast
import functools
import re

import pytest

from tests.test_project_endpoint_authorization_baseline import (
    _ANY_DECOR,
    _IDENTITY_ONLY_TOKENS,
    _PROJECT_LEVEL_TOKENS,
    _ROUTERS,
    _auth_names_in_node,
    _matches,
    _router_vars,
)

_APP = _ROUTERS.parent
_OBJECT_PATH_PARAMS = ("{project_id}", "{wp_id}", "{wp_index_id}")

#: 本维额外认可的项目级标识 → 证明链。每一环 = (相对 backend/app 的文件, 函数限定名, 该函数必须**全部**引用到的名字)。
#: 证据按 AST 收集：Name / Attribute（同基线 ``_auth_names_in_node``，docstring / 注释不计），外加 SQL 字符串里
#: ``FROM / JOIN project_users`` 记作 ``project_users``。末环必须落到基线项目级标识或项目成员表 / 底稿可见性门。
#: 限定名等于标识本身的环即该标识的**定义**：路由里用到它，必须是本地定义的这一份或从这些模块导入。
_EXTRA_PROJECT_TOKENS: dict[str, tuple[tuple[str, str, tuple[str, ...]], ...]] = {
    # 取证 / 事件流 / 地址目录共用：project_users 直接成员或 staff→project_assignments 委派（admin / partner 放行）
    "check_project_access": (("services/acnr/auth.py", "check_project_access", ("project_users",)),),
    # 报表配置读：有项目上下文时 assert_project_permission(readonly)；无项目时读的是全局模板
    "_authorize_report_config_read": (
        ("routers/report_config.py", "_authorize_report_config_read", ("assert_project_permission",)),),
    # 报表配置写：按行归属分流 —— 项目行 assert_project_permission(edit)，全局模板行仅 admin
    "_authorize_report_config_write": (
        ("routers/report_config.py", "_authorize_report_config_write", ("assert_project_permission",)),),
    # 附件 / 附件预览：ProjectUser 成员级别比对（admin 放行）
    "_ensure_project_access": (
        ("routers/attachments.py", "_ensure_project_access", ("ProjectUser", "PERMISSION_HIERARCHY")),
        ("routers/office_preview.py", "_ensure_project_access", ("ProjectUser", "PERMISSION_HIERARCHY")),
    ),
    # 自定义查询回写：项目可见集 + 编辑级成员 + 逐目标 ownership_guard
    "_assert_writeback_authorized": (
        ("routers/custom_query.py", "_assert_writeback_authorized",
         ("get_visible_project_ids", "ProjectUser", "ownership_guard")),),
    # 文档级 AI 对话：宿主反查 → 唯一授权真源 ResourceAccessResolver（附注 / 报表 = 成员关系，底稿 = 可见性门）
    "_authorize_doc_host": (
        ("routers/doc_ai_chat.py", "_authorize_doc_host", ("HostContextResolver", "enforce")),
        ("services/ai_chat/host_context.py", "HostContextResolver.enforce", ("resolve",)),
        ("services/ai_chat/host_context.py", "HostContextResolver.resolve", ("authorize_host", "allowed")),
        ("services/ai_chat/access.py", "ResourceAccessResolver.authorize_host", ("_authorize",)),
        ("services/ai_chat/access.py", "ResourceAccessResolver._authorize",
         ("_authorize_workpaper", "_authorize_project_resource")),
        ("services/ai_chat/access.py", "ResourceAccessResolver._authorize_workpaper", ("try_gate_wp",)),
        ("services/ai_chat/access.py", "ResourceAccessResolver._authorize_project_resource", ("_is_project_member",)),
        ("services/ai_chat/access.py", "ResourceAccessResolver._is_project_member", ("ProjectUser",)),
    ),
    # 本 spec 新增：公式导入 / 新增自定义预设的引用解析项目上下文（readonly）
    "_assert_context_project": (
        ("routers/formula_import_export.py", "_assert_context_project", ("assert_project_permission",)),),
}

#: 刻意保持仅登录、不计入欠账的端点 → 理由（可伪证：``test_identity_by_design_endpoints_do_not_touch_data``）
_BODY_IDENTITY_BY_DESIGN: dict[str, str] = {
    # spec formula-fetch-followup-defect-closure R4.1：只把地址换算成前端路由，请求体的项目只拼进路由字符串
    "address_registry.py::get_jump_route": "只做字符串换算、不读库",
}

_BODY_PROJECT_TOKENS = _PROJECT_LEVEL_TOKENS + tuple(_EXTRA_PROJECT_TOKENS)

#: 本 spec 修过的端点（回归钉子：必须在本维且是项目级）
_FIXED_ENDPOINTS = frozenset({
    "formula_debug.py::debug_formula",
    "formula_import_export.py::import_data",
    "formula_import_export.py::create_custom_preset",
    "draft_refresh.py::one_click_draft_refresh",
    "refresh_scopes.py::list_refresh_scopes",
    "row_name_alignment_router.py::batch_refresh",
    # spec acnr-foundation-defect-closure D8：联动总线写 stale 的两个端点
    # （/impact 写 stale 走 edit；/impact-by-addr 改只读预览走 readonly）
    "linkage_bus.py::stale_impact",
    "linkage_bus.py::stale_impact_by_addr",
    # spec formula-fetch-followup-defect-closure R4.1：地址库读项目数据的五个端点（只读级）
    "address_registry.py::search_addresses",
    "address_registry.py::get_stats",
    "address_registry.py::resolve_uri",
    "address_registry.py::validate_formula",
    "address_registry.py::invalidate_cache",
})

#: 不用会话令牌、自带签名校验的端点 → 必须调到的校验依赖（可伪证：``test_body_self_auth_endpoints_really_verify``）
_BODY_SELF_AUTH: dict[str, str] = {
    # MCP scoped token（HMAC，签发时绑定 run / 项目），逐个工具调用再按资源授权
    "ai_chat_mcp.py::mcp_tool_call": "_validate_mcp_token",
}

#: 🔴 本维无鉴权欠账（2026-10-22 现算 5 个，**只许变短**）。均为他域端点，本 spec 不改，交用户裁决：
#:   · metabase.py::get_embed_url        —— 未登录即可按任意 project_id 签发 Metabase 嵌入 JWT（10 分钟有效），风险最高
#:   · metabase.py::build_drilldown_url  —— 拼下钻 URL，不读库
#:   · feature_flags.py::list_flags / check_flag —— 已废弃的旧端点，按项目读功能开关状态
#:   · b60_chapters.py::get_chapter_definitions —— 读静态章节定义 JSON，project_id 是预留参数、未使用
_BODY_KNOWN_GAPS: frozenset[str] = frozenset({
    "metabase.py::get_embed_url",
    "metabase.py::build_drilldown_url",
    "feature_flags.py::list_flags",
    "feature_flags.py::check_flag",
    "b60_chapters.py::get_chapter_definitions",
})

#: 本维「仅登录 / 仅角色、不校项目」上限，棘轮只许向下。2026-10-22 首次现算 111（只认请求体属性写法）；
#: 补额外项目级标识（误判 21 个）、修本 spec 六个端点、扫描口径补 dict 请求体（+5）后现算 93。
#: 其中与公式链路相邻、建议另立 spec 收口的：联动总线 stale 标记两个写端点（POST /impact、GET /impact-by-addr 都会
#: 写 stale）与地址库 v2 notify-cell-change（同样写 stale）、地址库六个读端点、底稿字段覆盖值两个端点。
#: 2026-10-24 spec formula-fetch-followup-defect-closure R4.1 修地址库五个读端点（jump 只拼路由、登记进
#: _BODY_IDENTITY_BY_DESIGN 不计欠账）后现算 87。
#: 2026-10-27 spec acnr-foundation-defect-closure D8：linkage-bus /impact（edit）、/impact-by-addr（readonly）
#: 两个 stale 写端点加项目鉴权升到 project 档，v2 notify-cell-change 下线去请求体（不再带项目、退出本维）后现算 84。
_BODY_IDENTITY_ONLY_BASELINE = 84


def _rooted_at_param(expr: ast.AST, params: set[str]) -> bool:
    """``body`` / ``body.target`` / ``request.query_params`` 这类以某个函数参数为根的表达式。"""
    while isinstance(expr, (ast.Attribute, ast.Subscript, ast.Call)):
        expr = expr.func if isinstance(expr, ast.Call) else expr.value
    return isinstance(expr, ast.Name) and expr.id in params


def _is_project_key(expr: ast.AST) -> bool:
    return isinstance(expr, ast.Constant) and expr.value == "project_id"


def _carries_project(node: ast.AST) -> bool:
    """参数名 ``project_id``，或从参数上读 ``project_id``：属性（请求体模型）/ ``["project_id"]`` / ``.get("project_id")``
    （``body: dict`` 的写法 —— 首版只认属性，漏掉了地址库三个 dict 请求体端点）。"""
    args = node.args
    params = {a.arg for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]}
    if "project_id" in params:
        return True
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and sub.attr == "project_id" and _rooted_at_param(sub.value, params):
            return True
        if isinstance(sub, ast.Subscript) and _is_project_key(sub.slice) and _rooted_at_param(sub.value, params):
            return True
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get" \
                and sub.args and _is_project_key(sub.args[0]) and _rooted_at_param(sub.func.value, params):
            return True
    return False


def _scan_source(rel: str, src: str) -> list[tuple[str, str, str]]:
    """一份路由源码里本维的端点 → (key, METHOD /完整路径, 档位)。"""
    tree = ast.parse(src)
    routers, out = _router_vars(tree), []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            seg = ast.get_source_segment(src, d) or ""
            m = _ANY_DECOR.search(seg if seg.startswith("@") else "@" + seg)
            if not m:
                continue
            var, method, path = m.groups()
            prefix, router_deps = routers.get(var, ("", set()))
            full = prefix + path
            if any(p in full for p in _OBJECT_PATH_PARAMS) or not _carries_project(node):
                break
            names = _auth_names_in_node(node) | router_deps
            tier = "project" if _matches(names, _BODY_PROJECT_TOKENS) else \
                "identity" if _matches(names, _IDENTITY_ONLY_TOKENS) else "none"
            out.append((f"{rel}::{node.name}", f"{method.upper()} {full}", tier))
            break
    return out


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[tuple[str, str, str], ...]:
    found: list[tuple[str, str, str]] = []
    for f in sorted(_ROUTERS.rglob("*.py")):
        src = f.read_text(encoding="utf-8-sig", errors="replace")
        found.extend(_scan_source(f.relative_to(_ROUTERS).as_posix(), src))
    return tuple(found)


# ── 额外项目级标识的证明链与绑定（可伪证） ───────────────────────────────────────

_SQL_MEMBER_TABLE = re.compile(r"\b(?:from|join)\s+project_users\b", re.IGNORECASE)

#: 证明链必须落到的判定（之一）：基线项目级标识、项目成员表、项目可见集、底稿可见性门
_TERMINAL_EVIDENCE = frozenset(_PROJECT_LEVEL_TOKENS) | {
    "ProjectUser", "project_users", "get_visible_project_ids", "try_gate_wp"}


def _read_app(rel: str) -> str:
    return (_APP / rel).read_text(encoding="utf-8-sig", errors="replace")


def _router_sources() -> dict[str, str]:
    return {f"routers/{f.relative_to(_ROUTERS).as_posix()}": f.read_text(encoding="utf-8-sig", errors="replace")
            for f in sorted(_ROUTERS.rglob("*.py"))}


def _function(tree: ast.Module, qualname: str) -> ast.AST | None:
    """按限定名（``func`` / ``Class.method``）取模块级函数或类方法。"""
    scope: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in qualname.split("."):
        node = next((n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                     and n.name == part), None)
        if node is None:
            return None
        scope = node.body
    return node if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None


def _evidence(node: ast.AST) -> set[str]:
    """函数真实引用到的名字 + SQL 字符串里的成员表（docstring 不算）。"""
    names = _auth_names_in_node(node)
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and _SQL_MEMBER_TABLE.search(sub.value):
                names.add("project_users")
    return names


def _chain_problems(token: str, chain, read=_read_app) -> list[str]:
    problems = []
    for rel, qualname, required in chain:
        node = _function(ast.parse(read(rel)), qualname)
        if node is None:
            problems.append(f"{token}：{rel}::{qualname} 不存在")
            continue
        missing = sorted(set(required) - _evidence(node))
        if missing:
            problems.append(f"{token}：{rel}::{qualname} 没有引用 {missing}")
    return problems


def _module_of(rel: str) -> str:
    return "app." + rel.removesuffix(".py").replace("/", ".")


def _binding_problems(token: str, chain, sources: dict[str, str]) -> list[str]:
    """路由里引用到的 ``token``（含前缀同族名，与 ``_matches`` 同口径）必须是证明过的那一份：
    本地定义的文件在证明链里，或从证明链里的模块导入；属性方式引用（``svc.token``）无法确认来源，一律报出。"""
    defs = {rel for rel, qualname, _ in chain if qualname == token}
    modules = {_module_of(rel) for rel in defs}
    problems = []
    for rel, src in sources.items():
        tree = ast.parse(src)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id.startswith(token)}
        if any(isinstance(n, ast.Attribute) and n.attr.startswith(token) for n in ast.walk(tree)):
            problems.append(f"{rel} 以属性方式引用 {token}，无法确认是证明过的那一份")
        for name in sorted(used):
            local = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in tree.body)
            imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                        and any(a.name == name and a.asname in (None, name) for a in n.names)}
            if name != token:
                problems.append(f"{rel} 引用了同族名 {name}，它不在证明链里")
            elif local and rel not in defs:
                problems.append(f"{rel} 自定义了一份 {token}，未经证明")
            elif not local and not (imported and imported <= modules):
                problems.append(f"{rel} 的 {token} 来源 {sorted(imported) or '未知'} 不在证明链里")
    return problems


@pytest.mark.parametrize("token", sorted(_EXTRA_PROJECT_TOKENS))
def test_extra_project_token_is_really_project_level(token: str):
    chain = _EXTRA_PROJECT_TOKENS[token]
    assert any(qualname == token for _, qualname, _ in chain), f"{token} 的证明链缺定义环"
    assert set().union(*(set(required) for *_, required in chain)) & _TERMINAL_EVIDENCE, \
        f"{token} 的证明链没有落到项目级判定"
    assert not _chain_problems(token, chain), _chain_problems(token, chain)
    problems = _binding_problems(token, chain, _router_sources())
    assert not problems, problems


def test_extra_token_checks_can_fail():
    """反向自检：docstring 里的表名不算证据；自写同名函数 / 属性引用 / 别处导入 / 同族名都必须报出。"""
    chain = (("services/x.py", "guard", ("project_users",)),)
    doc_only = 'async def guard(user, pid):\n    """SELECT 1 FROM project_users —— 只是说明"""\n    return None\n'
    real = 'async def guard(db, user, pid):\n    await db.execute(text("SELECT 1 FROM project_users WHERE x"))\n'
    assert _chain_problems("guard", chain, read={"services/x.py": doc_only}.__getitem__)
    assert not _chain_problems("guard", chain, read={"services/x.py": real}.__getitem__)

    call = "\nasync def ep():\n    await guard(1, 2)\n"
    routers = {
        "routers/ok.py": "from app.services.x import guard" + call,
        "routers/own.py": "async def guard(u, p):\n    return None" + call,
        "routers/attr.py": "async def ep(svc):\n    await svc.guard(1, 2)\n",
        "routers/elsewhere.py": "from app.services.y import guard" + call,
        "routers/variant.py": "from app.services.x import guard_v2\nasync def ep():\n    await guard_v2(1, 2)\n",
    }
    flagged = sorted({p.split(" ", 1)[0] for p in _binding_problems("guard", chain, routers)})
    assert flagged == ["routers/attr.py", "routers/elsewhere.py", "routers/own.py", "routers/variant.py"], flagged


# ── 扫描口径自检（双向变异） ──────────────────────────────────────────────────

def test_scanner_denominator_is_sane():
    rows = _scan()
    assert len(rows) >= 150, f"本维只扫到 {len(rows)} 个端点，扫描口径可能坏了（编写时 227）"
    assert {tier for *_, tier in rows} <= {"project", "identity", "none"}


def test_scanner_self_check():
    """合成样本：请求体属性 / dict.get / 下标 / 查询参数四种「带项目」写法都看得见；docstring 不算鉴权；
    额外项目级标识计入项目级；路径带 ``{wp_id}`` 的、根本不带项目的不在本维。"""
    sample = (
        'router = APIRouter(prefix="/api/x")\n'
        '@router.post("/bare")\n'
        "async def bare(body: Body, db=Depends(get_db)):\n"
        '    """权限：assert_project_permission —— 只是说明"""\n'
        "    return body.project_id\n"
        '@router.post("/dict")\n'
        "async def via_dict(body: dict, user=Depends(get_current_user)):\n"
        '    return body.get("project_id")\n'
        '@router.post("/subscript")\n'
        "async def via_subscript(payload: dict, user=Depends(get_current_user)):\n"
        '    return payload["project_id"]\n'
        '@router.get("/query")\n'
        "async def via_query(project_id: UUID, db=Depends(get_db), user=Depends(get_current_user)):\n"
        '    await assert_project_permission(db, user, project_id, "readonly")\n'
        '@router.post("/helper")\n'
        "async def via_helper(body: Body, db=Depends(get_db), user=Depends(get_current_user)):\n"
        "    await _authorize_doc_host(db, user, project_id=body.project_id)\n"
        '@router.get("/{wp_id}/x")\n'
        "async def wp_bound(wp_id: UUID, project_id: UUID):\n"
        "    return 1\n"
        '@router.get("/plain")\n'
        "async def no_project(user=Depends(get_current_user)):\n"
        "    return 1\n"
    )
    got = {k: tier for k, _, tier in _scan_source("s.py", sample)}
    assert got == {"s.py::bare": "none", "s.py::via_dict": "identity", "s.py::via_subscript": "identity",
                   "s.py::via_query": "project", "s.py::via_helper": "project"}, got


def _calls_project_token(tree: ast.AST) -> bool:
    return any(isinstance(c, ast.Call) and _matches(
        {c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", "")}, _BODY_PROJECT_TOKENS)
        for c in ast.walk(tree))


class _StripProjectGates(ast.NodeTransformer):
    """变异：删掉指定端点函数体里调用项目级标识的语句，签名里的项目级依赖（``Depends(require_project_access(...))``）
    换成仅登录（模拟「鉴权被摘掉」；查询参数带项目的端点门禁在签名里，只删函数体打不到）。"""

    def __init__(self, fn: str) -> None:
        self.fn, self.removed = fn, 0

    def _strip(self, node):
        if node.name == self.fn:
            kept = [s for s in node.body if not _calls_project_token(s)]
            self.removed += len(node.body) - len(kept)
            node.body = kept or [ast.Pass()]
            for defaults in (node.args.defaults, node.args.kw_defaults):
                for i, default in enumerate(defaults):
                    if default is not None and _calls_project_token(default):
                        defaults[i] = ast.parse("Depends(get_current_user)", mode="eval").body
                        self.removed += 1
        return node

    visit_FunctionDef = visit_AsyncFunctionDef = _strip


@pytest.mark.parametrize("key", sorted(_FIXED_ENDPOINTS))
def test_fixed_endpoint_stays_project_level_and_mutation_is_caught(key: str):
    """回归钉子 + 真实源码变异：本 spec 修过的端点必须在本维且是项目级；摘掉它的项目级判定后扫描器必须看出来。"""
    found = {k: tier for k, _, tier in _scan()}
    assert key in found, f"{key} 已不在本维（改名 / 改签名？），请同步钉子"
    assert found[key] == "project", f"{key} 回退成 {found[key]}"

    rel, fn = key.split("::", 1)
    stripper = _StripProjectGates(fn)
    mutated = ast.unparse(stripper.visit(ast.parse((_ROUTERS / rel).read_text(encoding="utf-8-sig"))))
    assert stripper.removed >= 1, f"{key} 函数体 / 签名里找不到项目级判定（变异没打到）"
    after = {k: tier for k, _, tier in _scan_source(rel, mutated)}
    assert after.get(key) in {"identity", "none"}, f"摘掉 {key} 的项目级判定后扫描器仍判 {after.get(key)}"


# ── 冻结 ──────────────────────────────────────────────────────────────────────

def test_no_new_unauthorized_body_project_endpoint():
    none = {k for k, _, tier in _scan() if tier == "none"}
    new_gaps = sorted(none - _BODY_KNOWN_GAPS - set(_BODY_SELF_AUTH))
    assert not new_gaps, "新增了无鉴权、项目在请求体 / 查询参数里的端点：\n  " + "\n  ".join(new_gaps)


def test_body_known_gaps_only_shrink():
    none = {k for k, _, tier in _scan() if tier == "none"}
    fixed = sorted(_BODY_KNOWN_GAPS - none)
    assert not fixed, f"以下端点已补鉴权（或已删 / 改名），请从 _BODY_KNOWN_GAPS 删除：{fixed}"


def test_body_self_auth_endpoints_really_verify():
    """自鉴权豁免必须仍在本维，且端点真的依赖了校验函数；校验函数本身遇无效令牌必须抛出（不得退化为放行）。"""
    found = {k: tier for k, _, tier in _scan()}
    for key, verifier in _BODY_SELF_AUTH.items():
        assert key in found, f"{key} 已不在本维，请删除豁免"
        rel, fn = key.split("::", 1)
        tree = ast.parse((_ROUTERS / rel).read_text(encoding="utf-8-sig"))
        assert verifier in _auth_names_in_node(_function(tree, fn)), f"{key} 没依赖 {verifier}"
        verifier_node = _function(tree, verifier)
        assert verifier_node is not None, f"{verifier} 不在 {rel} 里"
        assert any(isinstance(n, ast.Raise) for n in ast.walk(verifier_node)), f"{verifier} 里没有 raise —— 校验退化为放行"


def test_identity_by_design_endpoints_do_not_touch_data():
    """刻意仅登录的端点必须仍在本维、是仅登录档，且不碰数据：不挂会话依赖、不引用 ORM 会话 / 查询。"""
    found = {k: tier for k, _, tier in _scan()}
    for key in _BODY_IDENTITY_BY_DESIGN:
        assert found.get(key) == "identity", f"{key} 不在本维或档位变了（{found.get(key)}），请同步豁免"
        rel, fn = key.split("::", 1)
        node = _function(ast.parse((_ROUTERS / rel).read_text(encoding="utf-8-sig")), fn)
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}
        params = {a.arg for a in [*node.args.args, *node.args.kwonlyargs]}
        touched = sorted((names & {"get_db", "AsyncSession", "execute", "select", "text"}) | (params & {"db", "session"}))
        assert not touched, f"{key} 登记为不读库，实际引用了 {touched}"


def test_body_identity_only_do_not_grow():
    n = sum(1 for key, _, tier in _scan() if tier == "identity" and key not in _BODY_IDENTITY_BY_DESIGN)
    assert n <= _BODY_IDENTITY_ONLY_BASELINE, (
        f"本维「仅登录不校项目」从 {_BODY_IDENTITY_ONLY_BASELINE} 增至 {n} —— 项目在请求体 / 查询参数里的端点"
        "请在函数体首句直调 assert_project_permission")
    assert _BODY_IDENTITY_ONLY_BASELINE - n <= 20, f"现算 {n} 远低于基线，请下调常量锁住成果"


#: 本 spec 修过、项目在**路径**里的端点（归基线文件第一维；那边只冻结总数，这里逐个钉住）
_FIXED_PATH_ENDPOINTS = frozenset({
    "reports.py::consistency_check",
    "disclosure_notes.py::set_formula_gray",
})


@pytest.mark.parametrize("key", sorted(_FIXED_PATH_ENDPOINTS))
def test_fixed_path_endpoint_stays_project_level(key: str):
    from tests.test_project_endpoint_authorization_baseline import (
        _scan_identity_only,
        _scan_unauthorized,
        _total_project_endpoints,
    )

    rel, fn = key.split("::", 1)
    node = _function(ast.parse((_ROUTERS / rel).read_text(encoding="utf-8-sig")), fn)
    assert node is not None, f"{key} 不存在（改名？），请同步钉子"
    assert _total_project_endpoints() >= 300
    names = _auth_names_in_node(node)
    assert _matches(names, _PROJECT_LEVEL_TOKENS), f"{key} 不再引用项目级判定：{sorted(names)}"
    flagged = {k for k, _ in _scan_identity_only()} | {k for k, _ in _scan_unauthorized()}
    assert key not in flagged, f"{key} 回退成仅登录 / 无鉴权"


def test_object_path_params_still_cover_wp_routes():
    """本维把路径带 {wp_id} / {wp_index_id} 的端点交给 router 级可见性门：该前提须成立（门会对这两个路径参数判定）。"""
    src = (_ROUTERS / "_wp_gate.py").read_text(encoding="utf-8-sig")
    gate = _function(ast.parse(src), "dedicated_wp_gate")
    consts = {n.value for n in ast.walk(gate) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert {"wp_id", "wp_index_id"} <= consts, "dedicated_wp_gate 不再按 wp_id / wp_index_id 判定，本维的排除前提失效"
