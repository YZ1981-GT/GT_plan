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
import functools
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
    # 项目 id 在路径 / 查询参数里时，矩阵放行后再 assert_project_permission（2026-10-27 起；此前只看权限矩阵、
    # 不校成员却一直记作项目级 —— spec consol-autotree-residual-closure R3）。项目在请求体里它看不到，
    # 请求体维不认它（test_project_endpoint_authz_body_carried）。可伪证：test_require_operation_token_tier.py
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
    # 2026-10-16 补（spec disclosure-note-template-word-realignment Task 19，前缀维现算出现）：
    "require_project_permission",     # deps.py：先 assert_project_permission 再校细粒度项目权限
    "authorize_object",               # 取证治理 scope_guard：按对象反查项目归属
    # 2026-10-19 补：交付中心鉴权 —— 先 assert_project_permission 校验本项目成员，再按交付件角色矩阵；
    # word-exports / 导出附注 Word / 组合导出包复用同一函数。可伪证：test_guard_action_token_is_really_project_level
    "_guard_action",
    # 2026-10-20 补（spec partner-manager-edit-permission 任务 6.5）：附注编辑门禁 app/services/note_edit_gate.py。前缀匹配
    # 同时覆盖 assert_note_edit_access_for_object / _on_projects。可伪证：test_note_edit_gate_tokens_are_really_project_level
    "require_note_edit_access",
    "assert_note_edit_access",
    "assert_note_role_access",
    # 2026-10-27 补（spec attachment-security-baseline 需求 2.1）：函证路由的路由级门 services/confirmation_scope_gate.py
    # —— 先 assert_project_permission（GET readonly / 其余 edit），再核对路径与请求体对象属于路径项目。
    # 可伪证：tests/attachment_security_baseline/test_confirmation_gate_token_proof.py::test_confirmation_project_gate_is_really_project_level
    "confirmation_project_gate",
    # 2026-10-31 补（spec project-pid-path-authz-coverage：项目段参数叫 {pid} 的 49 条路由进视野后现算出现）。
    # 可伪证：tests/test_project_pid_path_authz_baseline.py 的 *_is_really_project_level 各条
    "enforce_wp_gate",                    # 底稿门：把路径项目交给 resolve_wp_binding_and_access，拒绝即 404
    "enforce_task_gate",                  # 任务门：同上（任务绑定）
    "resolve_conversation_access",        # 程序复核参与者判定（端点同时 _load_task 绑定路径项目）
    "_authorize_survival",                # 抽样阶段：底稿权限 + 底稿属于路径项目
    "_authorize_and_validate_extract",    # 抽凭提取：同上（编辑权）
    "_authorize_and_validate_evaluation", # 抽凭评价：同上（编辑权）
    "_authorize_undo",                    # 抽凭撤销：记录属于路径项目 + 底稿编辑权
    "_authorize_cutoff_wp",               # 截止测试：底稿权限 + 底稿属于路径项目
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

#: 项目段：字面量 ``{project_id}``，或 ``/projects/{任意名}``（原先只认前者，49 条 ``{pid}`` 路由从未进视野，
#: 其中 AI 批量复核等 3 个一个鉴权依赖都没有 —— spec project-pid-path-authz-coverage）
_PROJECT_SEG = re.compile(r"/projects/\{\w+(?::\w+)?\}")


def _has_project_segment(path: str) -> bool:
    return "{project_id}" in path or bool(_PROJECT_SEG.search(path))

#: **桩端点**豁免：函数体只 `raise` 4xx/5xx（410 已废弃 / 501 未实现），
#: **不触达 DB、不接收文件、无任何副作用** ⇒ 无鉴权合理。现算 **7** 处
#: （`wp_mapping.py::assign_workpaper_gone` 由 spec procedure-trim-generation-delegation-chain 任务 12 下线：
#: 原按姓名写主编、只 flush 不提交，绕过裁剪与可见范围）。
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
    "wp_mapping.py::assign_workpaper_gone",
})

#: 桩端点所在文件（供 `test_stub_endpoints_really_are_stubs` 定位源码）
_STUB_FILES: frozenset[str] = frozenset({"procedures.py", "disclosure_notes.py", "wp_mapping.py"})

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
            if route is None or not _has_project_segment(route[1]):
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
                if m and _has_project_segment(m.group(2)):
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
    # spec formula-fetch-followup-defect-closure R4.2/R4.3 + procedure-chain-hardening：
    # 生成底稿五端点（edit×4 + readonly×1）与模板清单（readonly）
    "wp_template.py::generate_project_workpapers",
    "wp_template.py::generate_from_codes",
    "wp_template.py::create_custom_workpaper",
    "wp_template.py::create_custom_workpaper_batch",
    "wp_template.py::preview_custom_workpaper_batch",
    "wp_template_list.py::get_template_list",
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
            if route is None or not _has_project_segment(route[1]):
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
#: 本轮把 t_accounts 的 7 个端点从「仅登录」升级为项目级后由 234 降至 227）。
#: 2026-09-30 降至 **224**（spec knowledge-upload-robustness-and-consumer-wiring）：
#: 删掉被遮蔽的重复 `note_ai.ai_complete`（query 版），续写 / 改写升级为
#: `require_project_access("readonly")`（它们要按用户判定知识文档可见性）。
#: 挂了 `get_current_user` / `require_role` 但无项目级鉴权的端点 ——
#: 任何登录用户可用于访问任意项目。
#:
#: 这**不是本轮引入的**，也不是本轮修复目标（900+ 端点 / 214 张无 RLS 保护的
#: 带 project_id 表，属平台架构决策范围：要推 RLS 覆盖、还是逐端点补门禁、
#: 还是收紧默认依赖，需要专门立项）。
#:
#: 本断言只**冻结上限**：不得比现状更差。
#: 🔴 阈值是现算值而非拍脑袋 —— 降到更低后应同步下调（棘轮只许向下）。
#: 2026-10-23 现算 200：formula-governance-coverage-closure R1（74c7c0a8f）给公式域端点补项目级判定后
#: 降 2，当时未同步下调，`test_note_edit_gate_endpoints` 的相等断言因此一直红（spec
#: formula-fetch-and-wp-generation-defect-closure R7 收口时下调）。
#: 2026-10-24 现算 193：spec procedure-trim-generation-delegation-chain 给生成底稿两端点、自定义底稿三端点、
#: 准则切换两端点补项目级判定（edit / readonly）后降 7。
#: 2026-10-26 现算 191：spec procedure-chain-followup-closure R2.3 给程序行任务物化两端点（materialize /
#: materialize-jobs，原先任何登录用户都能给任意项目物化）挂 ``require_project_delegator`` 后降 2。
#: 2026-10-27 现算 169（改前 189）：spec consol-autotree-residual-closure R1.1 / R1.3 给报表页 / 报表行次映射 / 报表行关联
#: 底稿 / 试算分析四个 router 共 20 个端点改挂 ``require_project_access``（readonly / edit）后降 20。
#: 2026-10-27 现算 166：审计报告 3 个端点（generate/update_paragraph/update_status）加 assert_project_permission 后降 3。
#: 2026-10-31 现算 153（改前 165）：spec platform-performance-residual-findings-closure R1 —— 账龄配置 GET / PUT
#: 改挂 ``require_project_access``（readonly / edit）2 个、completion_phase 删掉与正式实现重复注册的 5 个、
#: 被遮蔽的附注裁剪 2 个与附注底稿映射 1 个恢复可达时补 readonly 门，去重后才生效的问题提示 / 底稿摘要 2 个
#: 补 readonly 门，共降 12。
#: 2026-10-31 现算 152（改前 153）：spec platform-performance-residual-findings-closure R12 —— batch_review 从
#: readonly 提升到 review（项目级），不再算「仅登录不校项目」。
_IDENTITY_ONLY_BASELINE = 152


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
    zero = "00000000-0000-0000-0000-000000000000"

    def _strip(text: str) -> str:
        # 剔注释后再查，避免把「说明为什么不能这么写」的注释数成真实代码
        return re.sub(r'"""[\s\S]*?"""', "", re.sub(r"#.*$", "", text, flags=re.MULTILINE))

    src = (_ROUTERS / "formula_audit_log.py").read_text(encoding="utf-8", errors="replace")
    code = _strip(src)
    assert '"user_id": current_user.id' in code, (
        "审计日志未写真实操作人 user_id"
    )
    assert zero not in code, (
        "又出现写死的全零 user_id ⇒ 审计留痕可伪造"
    )

    # 双向变异自检：剔注释逻辑只剔注释 / docstring，代码里的全零 UUID 照样数进来。原自检依赖本文件注释里恰好留着
    # 全零 UUID 字样（spec formula-hub-integrity-closure 重写 add_audit_log 的 docstring 后已不含）⇒ 改用合成样本
    sample = f'"""说明：不得写 {zero}"""\n# 旧写法 {zero}\nuser_id = uuid.UUID("{zero}")\n'
    assert _strip(sample).count(zero) == 1, "剔注释逻辑失效：注释 / docstring 里的全零 UUID 被数进来，或代码里的被剔掉"
    assert zero not in _strip(f'"""{zero}"""\n# {zero}\nok = 1\n')


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


# ══════════════════════════════════════════════════════════════════════════
# 第三维度：路由前缀 / 非 ``router`` 变量名 —— 上两维的盲区
# （spec disclosure-note-template-word-realignment Task 19，2026-10-16）
# ══════════════════════════════════════════════════════════════════════════
#
# 上两维只认 ``@router.<method>("…{project_id}…")``：①``APIRouter(prefix="/api/projects/{project_id}/notes")``
# 下的 ``@router.post("/import-prior-year")`` 装饰器路径不含 ``{project_id}``；②路由变量不叫 ``router``
# （``signing_router`` / ``public_router`` …）；③空路径 ``@router.get("")`` —— 三类都看不见。
# ``note_advanced.py`` 五个端点一个鉴权依赖都没挂（未登录可读写任意项目附注）就是这么漏掉的，实测
# ``GET /api/projects/{pid}/notes/cross-references`` 不带令牌 200。现算该维 **632** 个端点：项目级 237 /
# 仅登录 339 / **无鉴权 56**（其中 2 个是签名 / 回调自鉴权，见 ``_PREFIXED_SELF_AUTH``）。
#
# 处置：note_advanced 五个由 disclosure-payload spec 修；其余 54 个由 disclosure-note-template-word-realignment
# Phase 8 Task 8（2026-10-18）逐个评估调用方后补齐 —— 读端点挂 require_project_access("readonly")、写端点挂
# "edit"（整路由同级的用路由级 dependencies）。``_PREFIXED_KNOWN_GAPS`` 现清空；仅登录档冻结上限。
# 🔴 wp_template_files / wp_template_docx / wp_template_xlsx 的 /template-file 端点确认为**前端 Univer 渲染用**
# （OnlyOffice 走 wp_onlyoffice_router + {ONLYOFFICE_URL} ConvertService，不抓这些），前端带会话令牌 ⇒ 加鉴权安全。

_ANY_DECOR = re.compile(r'@(\w+)\.(get|post|put|patch|delete)\(\s*[\'"]([^\'"]*)[\'"]')

#: 不用会话令牌、自带签名校验的端点 → 必须调到的校验函数（可伪证：``test_self_auth_endpoints_really_verify``）
_PREFIXED_SELF_AUTH: dict[str, str] = {
    "deliverable.py::onlyoffice_callback": "verify_callback_jwt",        # OnlyOffice 回调 JWT
    "deliverable.py::signed_download_version": "_verify_download_sig",  # 10 分钟 HMAC 签名下载
}

#: 🔴 前缀维真实欠账：2026-10-16 快照 16 个路由文件 54 个端点，**2026-10-18 Phase 8 Task 8 已全部补齐并清零**。
#: 守卫 `test_prefixed_known_gaps_only_shrink` 只许变短；清零后它退化为「禁止任何条目回潮」，而真正拦住新增无鉴权
#: 端点的是 `test_no_new_prefixed_unauthorized_endpoint`（扫 none 档必为空）。
_PREFIXED_KNOWN_GAPS: frozenset[str] = frozenset()

#: 前缀维「仅登录不校项目」上限，棘轮只许向下。2026-10-16 现算 339；2026-10-19 补附注 / 交付件生成链路
#: （交付中心 35 + word-exports 13 + 导出附注 Word 1 + 全链路工作流 10）后现算 277。
#: 2026-10-27 现算 256（改前 260）：spec consol-autotree-residual-closure R1.3 报表映射 3 个端点 + 报表 Excel 导出改挂项目级。
#: 2026-10-27 spec attachment-security-baseline：函证路由 17 个端点挂路由级项目门，在上一条基础上再减 17，现算 → 239
#: 2026-10-28 合入远端（BM，advanced-query-linkage-closure 在 tmp_aql_verify 构建 M）后现算 238。
#: 2026-10-31 HEAD 841166b57 现算 232；spec platform-performance-residual-findings-closure R1.4 给恢复可达的工时
#: 预算对比、待审批列表两个端点补 readonly 门后降 2 → 230（未计入别处未入库的 continuous_audit 改动）。
#: spec project-pid-path-authz-coverage：项目段认 ``{pid}`` 后，HEAD 9791805c8 现算 235（截止测试 4 + 抽凭历史 / 对比 2
#: 进视野，原先这 6 个只校验登录）；本 spec 把这 6 个改成项目级、R1.4 降 2 ⇒ 227。主工作树另含并发会话未入库的
#: continuous_audit 1 + 调整分录锁 / 重分类 / 关联底稿 7 个改动，现算 219（随那些改动入库再下调）。
_PREFIXED_IDENTITY_ONLY_BASELINE = 227


def _matches(names: set[str], tokens: tuple[str, ...]) -> bool:
    return any(n == t or n.startswith(t) for n in names for t in tokens)


def _router_vars(tree: ast.Module) -> dict[str, tuple[str, set[str]]]:
    """模块级 ``X = APIRouter(prefix="…", dependencies=[…])``：变量名 → (前缀, 路由级依赖里引用到的名字)。"""
    out: dict[str, tuple[str, set[str]]] = {}
    for node in tree.body:
        call = node.value if isinstance(node, ast.Assign) else None
        if not isinstance(call, ast.Call) or (getattr(call.func, "id", None) or getattr(call.func, "attr", "")) \
                != "APIRouter":
            continue
        prefix, names = "", set()
        for kw in call.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                prefix = str(kw.value.value)
            elif kw.arg == "dependencies":
                for sub in ast.walk(kw.value):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
                    elif isinstance(sub, ast.Attribute):
                        names.add(sub.attr)
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = (prefix, names)
    return out


def _scan_prefixed_source(rel: str, src: str) -> list[tuple[str, str, str]]:
    """一份路由源码里上两维看不见、完整路径含 ``{project_id}`` 的端点 → (key, METHOD /完整路径, 档位)。

    档位：``project`` 项目级 / ``identity`` 仅登录 / ``none`` 无鉴权（路由级 dependencies 计入）。
    """
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
            if _has_project_segment(prefix + path) and not (var == "router" and _has_project_segment(path)):
                names = _auth_names_in_node(node) | router_deps
                tier = "project" if _matches(names, _PROJECT_LEVEL_TOKENS) else \
                    "identity" if _matches(names, _IDENTITY_ONLY_TOKENS) else "none"
                out.append((f"{rel}::{node.name}", f"{method.upper()} {prefix}{path}", tier))
            break
    return out


@functools.lru_cache(maxsize=1)
def _scan_prefixed() -> tuple[tuple[str, str, str], ...]:
    found: list[tuple[str, str, str]] = []
    for f in sorted(_ROUTERS.rglob("*.py")):
        src = f.read_text(encoding="utf-8-sig", errors="replace")
        found.extend(_scan_prefixed_source(f.relative_to(_ROUTERS).as_posix(), src))
    return tuple(found)


def test_prefixed_scanner_sees_the_blind_spot():
    """分母自检 + 阳性对照：该维现算 632；note_advanced 五个端点必须在内且是项目级（本轮修的）。"""
    found = {k: tier for k, _, tier in _scan_prefixed()}
    assert len(found) >= 500, f"前缀维只扫到 {len(found)} 个端点，扫描口径可能坏了"
    advanced = {k: t for k, t in found.items() if k.startswith("note_advanced.py::")}
    assert len(advanced) == 5 and set(advanced.values()) == {"project"}, advanced


def test_every_router_prefix_is_a_literal():
    """前缀写成变量 / f-string 时扫描器解析不了 ⇒ 整个文件静默脱管。"""
    bad = []
    for f in sorted(_ROUTERS.rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8-sig", errors="replace"))):
            if isinstance(node, ast.Call) and (getattr(node.func, "id", None) or getattr(node.func, "attr", "")) \
                    == "APIRouter":
                bad.extend(f"{f.name}: {ast.unparse(kw.value)}" for kw in node.keywords
                           if kw.arg == "prefix" and not isinstance(kw.value, ast.Constant))
    assert not bad, bad


def test_no_new_prefixed_unauthorized_endpoint():
    none = {k for k, _, tier in _scan_prefixed() if tier == "none"}
    # 桩端点（只 raise 410 / 501、不声明依赖）两维同一豁免，真伪由 test_stub_endpoints_really_are_stubs 核验
    new_gaps = sorted(none - _PREFIXED_KNOWN_GAPS - set(_PREFIXED_SELF_AUTH) - _STUB_ENDPOINTS)
    assert not new_gaps, "新增了无鉴权的项目级端点（路由前缀带 {project_id}）：\n  " + "\n  ".join(new_gaps)


def test_prefixed_known_gaps_only_shrink():
    none = {k for k, _, tier in _scan_prefixed() if tier == "none"}
    fixed = sorted(_PREFIXED_KNOWN_GAPS - none)
    assert not fixed, f"以下端点已补鉴权（或已删），请从 _PREFIXED_KNOWN_GAPS 删除：{fixed}"


def test_self_auth_endpoints_really_verify():
    """自鉴权豁免必须真的调校验函数，且仍属于该维（不得借豁免藏无鉴权端点）。"""
    src = (_ROUTERS / "deliverable.py").read_text(encoding="utf-8-sig", errors="replace")
    funcs = {n.name: n for n in ast.walk(ast.parse(src)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    found = {k for k, _, _ in _scan_prefixed()}
    for key, verifier in _PREFIXED_SELF_AUTH.items():
        assert key in found, f"{key} 已不在前缀维，请删除豁免"
        assert verifier in _auth_names_in_node(funcs[key.split("::", 1)[1]]), f"{key} 没调 {verifier}"


def test_guard_action_token_is_really_project_level():
    """``_guard_action`` 记作项目级的前提（可伪证）：

    ① 全部路由里只有 deliverable.py 定义它，且函数体真的调 ``assert_project_permission``；
    ② 其余路由用到它必须是从 ``app.routers.deliverable`` 导入的那一个 —— 自写一份同名函数不得被当成项目级。
    """
    defs: dict[str, ast.AST] = {}
    users: dict[str, bool] = {}
    for f in sorted(_ROUTERS.rglob("*.py")):
        rel = f.relative_to(_ROUTERS).as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8-sig", errors="replace"))
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("_guard_action"):
                defs[rel] = n
        if rel != "deliverable.py" and any(isinstance(n, ast.Name) and n.id == "_guard_action" for n in ast.walk(tree)):
            users[rel] = any(
                isinstance(n, ast.ImportFrom) and n.module == "app.routers.deliverable"
                and any(a.name == "_guard_action" for a in n.names)
                for n in ast.walk(tree)
            )
    assert set(defs) == {"deliverable.py"}, f"_guard_action 只许交付中心定义一份：{sorted(defs)}"
    assert "assert_project_permission" in _auth_names_in_node(defs["deliverable.py"]), "_guard_action 不再校验项目成员"
    # Task 13.1：_guard_action 调用 is_project_eqcr（需求 7.3），不含 _is_project_eqcr，不含与 "eqcr" 字面量比较
    guard_names = _auth_names_in_node(defs["deliverable.py"])
    assert "is_project_eqcr" in guard_names, "_guard_action 不再调用 is_project_eqcr（需求 7.3）"
    assert "_is_project_eqcr" not in guard_names, "_guard_action 仍残留旧的 _is_project_eqcr 调用"
    # 不含与字面量 "eqcr" 比较：函数体内不应有 Constant(value="eqcr") 出现
    guard_node = defs["deliverable.py"]
    eqcr_literals = [
        n for n in ast.walk(guard_node)
        if isinstance(n, ast.Constant) and n.value == "eqcr"
    ]
    assert not eqcr_literals, f"_guard_action 含与字面量 'eqcr' 的比较（{len(eqcr_literals)} 处），应通过 is_project_eqcr 判定"
    assert users and all(users.values()), f"复用方必须从 app.routers.deliverable 导入：{users}"


def test_g_class_word_exports_use_only_guard_action():
    """G 类导出 Word 端点只走 _guard_action，不调附注编辑门禁（需求 6.9）。

    deliverable.py 整文件不应 import 或引用 note_edit_gate 任何函数名。"""
    src = (_ROUTERS / "deliverable.py").read_text(encoding="utf-8-sig", errors="replace")
    tree = ast.parse(src)
    _NOTE_GATE_NAMES = {
        "require_note_edit_access", "assert_note_edit_access",
        "assert_note_edit_access_for_object", "assert_note_edit_access_on_projects",
        "assert_note_role_access",
    }
    # 检查 import 层：不应从 note_edit_gate 导入
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "note_edit_gate" in node.module:
            imported = {a.name for a in node.names}
            assert not imported & _NOTE_GATE_NAMES, (
                f"deliverable.py 导入了附注编辑门禁函数 {sorted(imported & _NOTE_GATE_NAMES)}（需求 6.9）"
            )
    # 检查引用层：函数体内不应出现这些名字
    all_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            all_names.add(node.id)
        elif isinstance(node, ast.Attribute):
            all_names.add(node.attr)
    gate_refs = all_names & _NOTE_GATE_NAMES
    assert not gate_refs, (
        f"deliverable.py 引用了附注编辑门禁 {sorted(gate_refs)}，G 类端点应只走 _guard_action（需求 6.9）"
    )


def test_prefixed_identity_only_do_not_grow():
    n = sum(1 for *_, tier in _scan_prefixed() if tier == "identity")
    assert n <= _PREFIXED_IDENTITY_ONLY_BASELINE, (
        f"前缀维「仅登录不校项目」从 {_PREFIXED_IDENTITY_ONLY_BASELINE} 增至 {n} —— 新端点请挂 require_project_access")
    assert _PREFIXED_IDENTITY_ONLY_BASELINE - n <= 20, f"现算 {n} 远低于基线，请下调常量锁住成果"


def test_prefixed_scanner_self_check():
    """合成样本：前缀带 {project_id} 无鉴权 → none；路由级依赖 → project；非 router 变量名 / 空路径也看得见。"""
    sample = (
        'router = APIRouter(prefix="/api/projects/{project_id}/x")\n'
        'guarded = APIRouter(prefix="/api/projects/{project_id}/y",\n'
        '                    dependencies=[Depends(require_project_access("readonly"))])\n'
        '@router.get("")\n'
        "async def bare(project_id, db = Depends(get_db)):\n"
        '    """权限：require_project_access —— 只是说明"""\n'
        "    return {}\n"
        '@guarded.post("/z")\n'
        "async def via_router(project_id):\n"
        "    return {}\n"
        '@router.get("/{project_id}/old")\n'
        "async def old_dimension(project_id):\n"
        "    return {}\n"
    )
    got = {k: tier for k, _, tier in _scan_prefixed_source("s.py", sample)}
    assert got == {"s.py::bare": "none", "s.py::via_router": "project"}, got


# ══════════════════════════════════════════════════════════════════════════
# 附注编辑门禁三个令牌记作项目级的前提（spec partner-manager-edit-permission 需求 6.10，任务 6.5）
# ══════════════════════════════════════════════════════════════════════════
# 按 AST 判定（注释 / docstring / 字符串里的名字不计）。判定函数 ``note_gate_ast_facts`` 与附注门禁契约守卫共用，
# 合成样例自检在那边；``_NOTE_GATE`` 在调用时读取，变异实测可把它指向源码副本（不改磁盘上的生产文件）。

_NOTE_GATE = _ROOT / "backend/app/services/note_edit_gate.py"

#: 事实键（与 ``note_gate_ast_facts`` 一致）→ 不成立时的说明
_NOTE_GATE_FACTS = {
    "permission": "需求 6.10 ①：assert_note_edit_access 不再在条件分支、异常处理与提前 return 之外以 review 级"
                  "（字面量或同文件常量）await app.deps.assert_project_permission",
    "eqcr": "需求 6.10 ②：assert_note_edit_access 不再无条件 await EQCR 判定 app.services.eqcr_resolver.is_project_eqcr",
    "role": "assert_note_role_access 不再在任何 return 之前无条件 await 判定实现 assert_note_edit_access",
}


def _note_gate_facts(src: str) -> dict[str, bool]:
    # 延迟导入：本文件其余用例只读源码，不因 app 导入失败而无法收集
    from tests.test_disclosure_notes_project_gate_contract import note_gate_ast_facts

    return note_gate_ast_facts(src)


@pytest.mark.parametrize("fact", sorted(_NOTE_GATE_FACTS))
def test_note_edit_gate_tokens_are_really_project_level(fact: str):
    """三个附注令牌记作项目级的前提（可伪证）：判定实现做 review 级成员校验与 EQCR 判定，角色限定形态先调判定实现。"""
    assert _note_gate_facts(_NOTE_GATE.read_text(encoding="utf-8"))[fact], _NOTE_GATE_FACTS[fact]


def test_note_gate_facts_can_fail():
    """反向自检：不满足的源码三条全为 False —— 共享判定函数退化为恒真时，本文件也能独立打红。"""
    sample = "async def assert_note_edit_access(db, user, project_id, *, consol_lock):\n    return user\n"
    assert _note_gate_facts(sample) == {"permission": False, "eqcr": False, "role": False}
