"""项目级端点鉴权基线守卫 —— 防「路径含 {project_id} 却无鉴权」整类复发

spec: disclosure-payload-authority-source（复盘第三轮触类旁通产出）

## 缘起

本轮自查发现新写的 `disclosure-sync-coverage` 端点**漏挂 `require_project_access`**
（只有 `Depends(get_db)`）⇒ 任意 `project_id` 可未授权读取该项目披露同步状态（IDOR）。
按「发现一处反模式立即 grep 全仓找同类」的纪律扫描，命中 **15** 处
（现算，见 `_KNOWN_GAPS`）。

## 本守卫的作用

**不是**把现存欠账一次修完（那要改多个业务域的端点，超出本 spec 范围且需逐个评估
调用方影响），而是**冻结基线**：清单只许变短，新增端点必须挂鉴权。

## 两类豁免的区别

* `_GONE_ENDPOINTS` —— 函数体只 `raise _gone(...)` 返回 410 的废弃端点，
  不触达任何数据，无鉴权**合理**。
* `_KNOWN_GAPS` —— **真实欠账**，已如实登记待另立 spec 修。
  按严重度排序见文件末尾注释。
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
_ROUTERS = _ROOT / "backend/app/routers"

#: 任一 token 出现在端点函数源码里即视为「有鉴权」。
#: 覆盖依赖注入式与函数体内显式调用式两种写法。
#: 🔴 口径必须穷举全仓真实鉴权形态 —— 首版只列了 10 个 token，漏掉
#: `require_project_delegator` / `require_project_delegator_pid` /
#: `require_wp_edit_permission` / `require_query_builder_access` /
#: `dedicated_wp_gate`，把 8 个**有鉴权**的 procedures 端点误判成欠账
#: （本守卫自己先把我抓了一次）。清单由
#: `Counter(re.findall(r'Depends\(\s*([A-Za-z_][\w.]*)', ...))` 现算全仓 Depends
#: 被依赖名后逐个甄别得出，新增鉴权方式须同步补进来。
#:
#: 🔴🔴 **两档必须分开**（第四轮复盘）：
#: `get_current_user` / `require_role` 只保证「登录了」「是某角色」，
#: **不含项目维度** —— 挂了它们的端点仍可被任意登录用户用于访问任意项目。
#: 上一轮我给 `t_accounts.list` 补 `get_current_user` 就当"修完"，理由是
#: 「对齐同文件另 7 处」，而那 7 处本身全是跨项目 IDOR ⇒
#: **把"对齐既有基准"当正确性依据 = 把缺陷正当化**。
#: 故本文件区分：
#:   · `_PROJECT_LEVEL_TOKENS` —— 真能保证「该用户对该项目/对象有权」
#:   · `_IDENTITY_ONLY_TOKENS` —— 仅身份认证，算"有鉴权"但**不算项目隔离**

#: 项目级鉴权（含对象归属反查型）
_PROJECT_LEVEL_TOKENS = (
    "require_project_access",
    "assert_project_permission",
    "require_operation",
    "require_wp_edit_permission",
    "authorize_wp_read",
    "authorize_wp_edit",
    "require_project_delegator",      # 亦覆盖 require_project_delegator_pid（前缀匹配）
    "require_query_builder_access",
    "dedicated_wp_gate",
    "ownership_guard",
    "_assert_project_edit",
    "_assert_note_project_access",
    "_assert_object_project_access",
    "_assert_validation_project_access",
)

#: 仅身份认证 / 角色判定，不含项目维度
_IDENTITY_ONLY_TOKENS = (
    "get_current_user",
    "require_role",
    "require_confirmation_token",
    "_require_manager_role",
)

#: 「有任何鉴权」= 两档之一（用于 `test_no_new_unauthorized_project_endpoint`：
#: 至少不能裸奔）
_AUTH_TOKENS = _PROJECT_LEVEL_TOKENS + _IDENTITY_ONLY_TOKENS

_DECOR = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]+)[\'"]')

#: **桩端点**豁免：函数体只 `raise` 4xx/5xx（410 已废弃 / 501 未实现），
#: **不触达 DB、不接收文件、无任何副作用** ⇒ 无鉴权合理。现算 **6** 处。
#:
#: 🔴 首版误列 9 处：`init_procedures` / `add_custom` / `delete_custom_procedure` /
#: `add_custom_with_template` 其实是**活端点且已挂 `require_project_delegator`**，
#: 是 `_AUTH_TOKENS` 口径不全造成的误判；`batch_apply` 真名是 `batch_apply_gone`。
#: 两处错误均由本文件的 `test_stub_endpoints_really_are_stubs` /
#: `test_stub_list_has_no_stale_entries` 自己抓出。
#:
#: 🔴 `disclosure_notes.py::upload_history` 第三轮曾被误列为 P2 欠账，实为桩端点：
#: 恒返回 501 `HISTORICAL_UPLOAD_NOT_IMPLEMENTED`，且其 docstring 明确写
#: 「端点**不声明** DB / 文件 / 后台任务依赖 —— 未实现的能力不应该占用连接池」
#: ⇒ 给它加鉴权会违背该有意设计，正确处置是归入本豁免。
_STUB_ENDPOINTS: frozenset[str] = frozenset({
    "procedures.py::save_trim_gone",
    "procedures.py::assign_procedures_gone",
    "procedures.py::apply_scheme_gone",
    "procedures.py::batch_apply_gone",
    "procedures.py::update_execution_status_gone",
    "disclosure_notes.py::upload_history",
})

#: 桩端点所在文件（供 `test_stub_endpoints_really_are_stubs` 定位源码）
_STUB_FILES: frozenset[str] = frozenset({"procedures.py", "disclosure_notes.py"})

#: 🔴 真实鉴权欠账基线 —— **2026-09-28 已清零**（原 6 处全部修完）。
#: **只许变短**：新增无鉴权端点由 `test_no_new_unauthorized_project_endpoint` 判红。
#:
#: 修复记录（第三轮复盘触类旁通产出，逐处对齐既有权限基准而非自造）：
#:   · `formula_audit_log.py::get_audit_log`    → `require_project_access("readonly")`
#:   · `formula_audit_log.py::add_audit_log`    → `require_project_access("edit")`
#:         并把写死的 `user_id=00000000-…` 换成 `current_user.id`
#:         （原注释自称「POST 端点无 current_user 上下文」—— 那不是没有上下文，
#:          是没挂鉴权依赖；审计留痕写不出人等于没有留痕）
#:   · `formula_audit_log.py::rollback_formula` → `require_role(["admin","partner","manager"])`
#:         用角色而非项目权限，因其 `UPDATE` 的 `report_config` 是**全局表**
#:         （无 `project_id` 列），一次回滚影响全平台 ⇒ 项目级权限保护不了全局资源；
#:         对齐 `report_config.populate-formulas`（同样改全局公式，用 `require_role`）。
#:         🔴 这是**权限收紧**：此前任何人可调。
#:   · `t_accounts.py::list_t_accounts`         → `get_current_user`（对齐同文件另 7 端点）
#:   · `metabase.py::clear_cache`               → `get_current_user`
#:         （该 router 内唯一有写副作用的端点；其余为读静态配置，本次不动）
#:   · `disclosure_notes.py::upload_history`    → **移入 `_STUB_ENDPOINTS`**（501 桩端点，误判）
_KNOWN_GAPS: frozenset[str] = frozenset()


def _endpoint_route(src: str, node: ast.AST) -> tuple[str, str] | None:
    """从装饰器解析 (method, path)，非路由端点返回 None。"""
    for d in getattr(node, "decorator_list", []):
        seg = ast.get_source_segment(src, d) or ""
        m = _DECOR.search(seg if seg.startswith("@") else "@" + seg)
        if m:
            return m.group(1), m.group(2)
    return None


def _auth_names_in_node(node: ast.AST) -> set[str]:
    """用 **AST** 收集函数里真实引用到的鉴权标识名。

    🔴 必须走 AST 而不是文本 `in` 匹配：端点的 **docstring / 注释**里常写
    「权限：`require_project_access("readonly")` —— 与 xx 同级」这类说明，
    纯文本匹配会把说明文字数成真实鉴权 ⇒ **漏报**（守卫恒绿）。
    本轮变异实测：摘掉 3 个端点的鉴权依赖后旧版扫描器仍全绿，就是这个原因。

    收集范围：
      · 签名 defaults / kw_defaults 里的 `Depends(X)` 与 `Depends(X(...))`
      · 函数体内的 `Name` / `Attribute` 引用（跳过 docstring —— 它是 Constant 不产生 Name）
    """
    names: set[str] = set()

    def _add(n: ast.AST) -> None:
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            cur: ast.AST = n
            while isinstance(cur, ast.Attribute):
                names.add(cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                names.add(cur.id)

    args = getattr(node, "args", None)
    if args is not None:
        for default in [*(args.defaults or []), *(args.kw_defaults or [])]:
            if default is None:
                continue
            for sub in ast.walk(default):
                _add(sub)

    for stmt in getattr(node, "body", []):
        # docstring 是 Expr(Constant)，walk 它不产生 Name/Attribute，天然被排除；
        # `#` 注释根本不进 AST。
        for sub in ast.walk(stmt):
            _add(sub)
    return names


def _has_auth(node: ast.AST) -> bool:
    """节点是否真实引用了任一鉴权标识。

    前缀匹配用于覆盖 `require_project_delegator` / `require_project_delegator_pid`
    这类同族命名。
    """
    referenced = _auth_names_in_node(node)
    return any(
        name == tok or name.startswith(tok)
        for name in referenced
        for tok in _AUTH_TOKENS
    )


def _scan_unauthorized() -> list[tuple[str, str]]:
    """扫描路径含 {project_id} 却**真实未引用**任何鉴权标识的端点。

    返回 [(key, "METHOD /path"), ...]，key = "文件名::函数名"。
    """
    found: list[tuple[str, str]] = []
    for f in sorted(_ROUTERS.rglob("*.py")):
        src = f.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route = _endpoint_route(src, node)
            if route is None or "{project_id}" not in route[1]:
                continue
            if _has_auth(node):
                continue
            found.append((f"{f.name}::{node.name}", f"{route[0].upper()} {route[1]}"))
    return found


def _total_project_endpoints() -> int:
    """路径含 {project_id} 的端点总数（分母，防扫描器被架空）。"""
    n = 0
    for f in sorted(_ROUTERS.rglob("*.py")):
        src = f.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in node.decorator_list:
                seg = ast.get_source_segment(src, d) or ""
                m = _DECOR.search(seg if seg.startswith("@") else "@" + seg)
                if m and "{project_id}" in m.group(2):
                    n += 1
                    break
    return n


# ══════════════════════════════════════════════════════════════════════════


def test_scanner_denominator_is_sane():
    """自检：分母现算 ≥ 300（编写时 381），防扫描路径错导致空转。"""
    total = _total_project_endpoints()
    assert total >= 300, f"含 {{project_id}} 的端点仅 {total} 个，扫描路径可能错"


def test_no_new_unauthorized_project_endpoint():
    """🔴 基线守卫：不得新增「含 {project_id} 却无鉴权」的端点。"""
    found = {k for k, _ in _scan_unauthorized()}
    allowed = _STUB_ENDPOINTS | _KNOWN_GAPS
    new_gaps = sorted(found - allowed)
    assert not new_gaps, (
        "新增了无鉴权的项目级端点 —— 任意 project_id 可未授权访问（IDOR）。\n"
        "必须挂 `require_project_access(...)` / `require_role([...])`，或在函数体"
        "首句调 `assert_project_permission(...)`；若是未实现/已废弃的桩端点"
        "（只 raise 4xx/5xx 且不触达数据）则登记进 `_STUB_ENDPOINTS`：\n  "
        + "\n  ".join(new_gaps)
    )


def test_known_gaps_is_empty():
    """真实欠账已清零，且不得回填。

    🔴 `_KNOWN_GAPS` 是**临时**基线，2026-09-28 原 6 处全部修完后清空。
    再往里加条目 = 又欠了一笔债，必须同时在 spec 里登记原因与计划。
    """
    assert _KNOWN_GAPS == frozenset(), (
        "又出现了已知鉴权欠账。允许暂存，但必须：① 在 spec/dev-history 登记严重度与"
        f"修复计划 ② 本断言相应放宽并写明理由。当前：{sorted(_KNOWN_GAPS)}"
    )


def test_known_gaps_only_shrink():
    """基线只许变短：已修好的欠账必须从 `_KNOWN_GAPS` 删掉。"""
    found = {k for k, _ in _scan_unauthorized()}
    fixed = sorted(_KNOWN_GAPS - found)
    assert not fixed, (
        "以下端点已补鉴权，请从 _KNOWN_GAPS 删除（清单只许变短，"
        f"留着会掩盖新欠账）：{fixed}"
    )


def _stub_sources() -> dict[str, tuple[str, dict]]:
    """加载桩端点所在文件的源码与函数节点索引。"""
    out: dict[str, tuple[str, dict]] = {}
    for fname in _STUB_FILES:
        src = (_ROUTERS / fname).read_text(encoding="utf-8", errors="replace")
        by_name = {
            n.name: n for n in ast.walk(ast.parse(src))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        out[fname] = (src, by_name)
    return out


def test_stub_endpoints_really_are_stubs():
    """`_STUB_ENDPOINTS` 必须真的只 raise 且不触达数据，不得借豁免藏活端点。"""
    sources = _stub_sources()
    for key in sorted(_STUB_ENDPOINTS):
        fname, func = key.split("::", 1)
        src, by_name = sources[fname]
        node = by_name.get(func)
        if node is None:
            continue  # 函数已删，由 test_stub_list_has_no_stale_entries 兜
        body = ast.get_source_segment(src, node) or ""
        assert "raise " in body, (
            f"{key} 在桩端点豁免里却不 raise —— 要么补鉴权，要么移出名单"
        )
        for forbidden in ("await db.execute", "await db.commit", "await svc.", "Depends(get_db)"):
            assert forbidden not in body, (
                f"{key} 声称是桩端点却出现 {forbidden!r} —— 有真实副作用必须补鉴权"
            )


def test_stub_list_has_no_stale_entries():
    """豁免名单不得有失效条目（函数已删/已改名）。"""
    sources = _stub_sources()
    stale = []
    for key in _STUB_ENDPOINTS:
        fname, func = key.split("::", 1)
        if func not in sources[fname][1]:
            stale.append(key)
    assert not stale, f"豁免名单条目已不存在，请删除：{sorted(stale)}"


#: 本轮补过鉴权的端点 —— 逐个钉死防回退。
_FIXED_ENDPOINTS: frozenset[str] = frozenset({
    "disclosure_sync_coverage.py::get_disclosure_sync_coverage",
    "formula_audit_log.py::get_audit_log",
    "formula_audit_log.py::add_audit_log",
    "formula_audit_log.py::rollback_formula",
    "t_accounts.py::list_t_accounts",
    "metabase.py::clear_cache",
})


@pytest.mark.parametrize("key", sorted(_FIXED_ENDPOINTS))
def test_fixed_endpoint_stays_authorized(key: str):
    """回归钉子：2026-09-28 补过鉴权的端点不得再丢。"""
    found = {k for k, _ in _scan_unauthorized()}
    assert key not in found, f"{key} 的鉴权依赖被移除了"


# ══════════════════════════════════════════════════════════════════════════
# 第二维度：「仅登录不校项目」 —— 平台级现状基线（不是本轮修复目标）
# ══════════════════════════════════════════════════════════════════════════


def _scan_identity_only() -> list[tuple[str, str]]:
    """路径含 {project_id}、挂了身份认证但**无项目级鉴权**的端点。

    这类端点任何登录用户都能用于访问任意项目（项目维度不设防）。
    """
    found: list[tuple[str, str]] = []
    for f in sorted(_ROUTERS.rglob("*.py")):
        src = f.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            route = _endpoint_route(src, node)
            if route is None or "{project_id}" not in route[1]:
                continue
            names = _auth_names_in_node(node)
            has_project = any(
                n == t or n.startswith(t)
                for n in names for t in _PROJECT_LEVEL_TOKENS
            )
            has_identity = any(
                n == t or n.startswith(t)
                for n in names for t in _IDENTITY_ONLY_TOKENS
            )
            if has_identity and not has_project:
                found.append((f"{f.name}::{node.name}", f"{route[0].upper()} {route[1]}"))
    return found


#: 🔴 **平台级现状**（2026-09-28 现算 **227 / 381**，约 60%；
#: 本轮把 t_accounts 的 7 个端点从「仅登录」升级为项目级后由 234 降至 227）：
#: 挂了 `get_current_user` / `require_role` 但无项目级鉴权的端点 ——
#: 任何登录用户可用于访问任意项目。
#:
#: 这**不是本轮引入的**，也不是本轮修复目标（900+ 端点 / 214 张无 RLS 保护的
#: 带 project_id 表，属平台架构决策范围：要推 RLS 覆盖、还是逐端点补门禁、
#: 还是收紧默认依赖，需要专门立项）。
#:
#: 本断言只**冻结上限**：不得比现状更差。
#: 🔴 阈值是现算值而非拍脑袋 —— 降到更低后应同步下调（棘轮只许向下）。
_IDENTITY_ONLY_BASELINE = 227


def test_identity_only_endpoints_do_not_grow():
    """棘轮：「仅登录不校项目」的端点数不得增加。

    新写端点请用 `require_project_access(...)` 而非 `get_current_user`。
    """
    n = len(_scan_identity_only())
    assert n <= _IDENTITY_ONLY_BASELINE, (
        f"「仅登录不校项目」端点从 {_IDENTITY_ONLY_BASELINE} 增至 {n} —— "
        "新端点应挂 `require_project_access(...)`（含项目维度），"
        "而非仅 `get_current_user`"
    )


def test_identity_only_baseline_is_not_stale():
    """棘轮不得虚高：基线常量须贴近现算值（差距 >20 说明该下调了）。"""
    n = len(_scan_identity_only())
    assert _IDENTITY_ONLY_BASELINE - n <= 20, (
        f"现算 {n} 已远低于基线 {_IDENTITY_ONLY_BASELINE}，请下调基线常量锁住成果"
    )


def test_t_accounts_uses_project_level_auth():
    """回归钉子：T 型账户端点必须用项目级鉴权（本轮从仅登录升级而来）。

    第四轮修复：8 个端点原先只有 `get_current_user`（1 个连这都没有），
    且 service 层不按 project_id 过滤 ⇒ 跨项目可读可写。
    """
    identity_only = {k for k, _ in _scan_identity_only()}
    leaked = sorted(k for k in identity_only if k.startswith("t_accounts.py::"))
    assert not leaked, (
        f"T 型账户端点回退到仅登录鉴权（不含项目维度）：{leaked}"
    )


def test_audit_log_writes_real_user_id():
    """🔴 审计留痕必须记真实操作人，不得回到写死的全零 user_id。

    原实现 `user_id = uuid.UUID("00000000-0000-0000-0000-000000000000")`
    + 注释「POST 端点无 current_user 上下文」⇒ 留痕可伪造。
    """
    src = (_ROUTERS / "formula_audit_log.py").read_text(encoding="utf-8", errors="replace")
    # 剔注释后再查，避免把「说明为什么不能这么写」的注释数成真实代码
    code = re.sub(r"#.*$", "", src, flags=re.MULTILINE)
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    assert '"user_id": current_user.id' in code, (
        "审计日志未写真实操作人 user_id"
    )
    assert "00000000-0000-0000-0000-000000000000" not in code, (
        "又出现写死的全零 user_id ⇒ 审计留痕可伪造"
    )

    # 双向变异自检：注释里的全零 UUID 不应被数进来
    assert "00000000-0000-0000-0000-000000000000" in src, (
        "本文件已完全不含全零 UUID 字样，上一条断言的剔注释逻辑无从验证 —— "
        "若确实连注释都删了，请同步删除本自检"
    )


def _first_func(sample: str) -> ast.AST:
    for node in ast.walk(ast.parse(sample)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise AssertionError("样本里没有函数")


def test_scanner_detects_injected_gap():
    """双向变异：无鉴权样本必须被识别（证明 `_has_auth` 非恒真）。"""
    sample = (
        '@router.get("/api/projects/{project_id}/fake")\n'
        "async def fake_endpoint(project_id, db = Depends(get_db)):\n"
        "    return {}\n"
    )
    assert not _has_auth(_first_func(sample)), "扫描器识别不出无鉴权端点 ⇒ 守卫恒绿"


def test_scanner_accepts_authorized_sample():
    """反向变异：带鉴权的样本不得被误报。"""
    sample = (
        '@router.get("/api/projects/{project_id}/fake")\n'
        "async def fake_endpoint(\n"
        "    project_id,\n"
        "    db = Depends(get_db),\n"
        '    current_user = Depends(require_project_access("readonly")),\n'
        "):\n"
        "    return {}\n"
    )
    assert _has_auth(_first_func(sample)), "带鉴权的端点被误判为欠账"


def test_scanner_ignores_auth_mentioned_only_in_docstring():
    """🔴 关键：docstring / 注释里提到鉴权**不算**有鉴权。

    旧版用文本 `in` 匹配，把端点 docstring 里
    「权限：`require_project_access("readonly")` —— 与 xx 同级」的说明文字
    数成真实鉴权 ⇒ 本轮变异实测有 3 个端点摘掉依赖后守卫仍全绿（漏报）。
    """
    sample = (
        '@router.get("/api/projects/{project_id}/fake")\n'
        "async def fake_endpoint(project_id, db = Depends(get_db)):\n"
        '    """权限：require_project_access("readonly") —— 与其余只读端点同级。\n'
        "\n"
        "    也提一下 require_role([\"admin\"]) 和 get_current_user。\n"
        '    """\n'
        "    # 注释里同样提到 assert_project_permission\n"
        "    return {}\n"
    )
    assert not _has_auth(_first_func(sample)), (
        "docstring/注释里的鉴权字样被数成真实鉴权 ⇒ 守卫漏报"
    )


def test_scanner_detects_body_level_auth_call():
    """函数体内显式调用（非依赖注入）也算有鉴权。"""
    sample = (
        '@router.patch("/api/projects/{project_id}/fake")\n'
        "async def fake_endpoint(project_id, db = Depends(get_db)):\n"
        "    await assert_project_permission(db, user, project_id, 'edit')\n"
        "    return {}\n"
    )
    assert _has_auth(_first_func(sample))


def test_scanner_matches_delegator_family_by_prefix():
    """同族命名走前缀匹配（`require_project_delegator_pid` 等）。"""
    sample = (
        '@router.post("/api/projects/{project_id}/fake")\n'
        "async def fake_endpoint(\n"
        "    project_id,\n"
        "    _guard = Depends(require_project_delegator_pid),\n"
        "):\n"
        "    return {}\n"
    )
    assert _has_auth(_first_func(sample))
