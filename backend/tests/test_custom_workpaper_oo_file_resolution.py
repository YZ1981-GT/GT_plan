"""自定义底稿的 OnlyOffice 文件解析守卫（Task 26 浏览器实测抓出的 P0）。

## 被钉死的缺陷

2026-08-08 浏览器实测：点「在线编辑」→ `onlyoffice-config` **404**。

根因 = `_resolve_wp_file` 只认两个来源：
① OO 缓存副本 `{project}/workpapers/onlyoffice/{wp_code}.xlsx`
② **模板文件**（`find_template_file_any`）

而自定义底稿**没有模板**（编号如 `ZZT26A` 在 `wp_templates/` 里不存在），其 xlsx 在
`working_paper.file_path` 指的业务存储下 ⇒ 两来源都不命中 ⇒ `FileNotFoundError` ⇒ 404
⇒ **「在线编辑」模式从上线起就打不开**。

更深一层（即便复制一份到缓存也不对）：callback 落盘写缓存，而
`refresh_custom_projection` 读 `wp.file_path`（业务文件）⇒ OO 改动永远进不了 HTML 侧，
且「xlsx 本体唯一权威」退化成两份 xlsx 互相打架。

⇒ custom 的 config / WOPI 下载 / callback 落盘三处统一指向**业务文件本体**，
与投影读取同源。

## 为什么四层验证抓不到

- `get_diagnostics`：404 是运行时分支，不是类型错误
- 既有单测：`_resolve_wp_file` 的测试都用「有模板」的标准 wp_code
- vitest：前端只看到 `catch` 后的 ElMessage，不知道是 404
- 只有浏览器点一下「在线编辑」才暴露

spec: custom-workpaper-dual-mode-formula-and-batch Task 26
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
ROUTER = BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"
CTX = BACKEND / "app" / "services" / "custom_workpaper_context.py"
PROJ = BACKEND / "app" / "services" / "custom_workpaper_projection.py"


def _src(p: Path) -> str:
    assert p.exists(), f"文件不存在: {p}"
    return p.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """剥 `#` 行注释与三引号 docstring。

    🔴 必须剥 —— 本守卫治的正是「注释里写反例被数成真实调用」那一类；
    修复说明里会原样写出 `_onlyoffice_storage_dir` 等被禁形态。
    """
    import ast
    import io
    import tokenize

    # 1) 剥 docstring（按行号置空，保留行数以便报错定位）
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError:  # pragma: no cover
        return src
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                doc_lines.add(ln)
    kept = [("" if (i + 1) in doc_lines else ln) for i, ln in enumerate(lines)]
    stage1 = "\n".join(kept)

    # 2) 剥 `#` 注释（按行切除注释片段，保留行数与真实代码）
    #    🔴 普通字符串字面量**不剥** —— 字典键名/SQL 片段可能是真消费。
    cut: dict[int, int] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(stage1).readline):
            if tok.type == tokenize.COMMENT:
                ln, col = tok.start
                # 同一行可能多次命中，取最左的注释起点
                cut[ln] = min(cut.get(ln, col), col)
    except tokenize.TokenError:  # pragma: no cover
        return stage1
    res = []
    for i, ln in enumerate(stage1.splitlines(), start=1):
        res.append(ln[: cut[i]].rstrip() if i in cut else ln)
    return "\n".join(res)


def _func_body(src: str, name: str) -> str:
    """按缩进截取顶层函数体。

    🔴 先用圆括号配对跳过参数列表 —— 多行签名的 `) -> X:` 那行缩进为 0，
    按「首个缩进 <= def 缩进的行即结束」会在签名处提前中断（memory 已记该坑）。
    """
    m = re.search(rf"^(async def|def)\s+{re.escape(name)}\s*\(", src, re.M)
    assert m, f"未找到函数定义: {name}"
    i = src.index("(", m.start())
    depth = 0
    while i < len(src):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    tail = src[i:]
    brace = tail.index(":\n") if ":\n" in tail else 0
    rest = tail[brace + 1 :]
    lines = rest.splitlines()
    body: list[str] = []
    for ln in lines[1:]:
        if ln.strip() and not ln.startswith((" ", "\t")):
            break
        body.append(ln)
    assert body, f"函数体为空: {name}"
    return "\n".join(body)


# ─── Property: custom 分流 helper 存在且被三处消费 ──────────────────────────


def test_custom_oo_resolver_exists():
    """custom 专用解析 helper 必须存在（缺它则回落到「模板→缓存」必 404）。"""
    code = _strip_comments(_src(ROUTER))
    assert "def _resolve_custom_wp_file(" in code, (
        "缺少 `_resolve_custom_wp_file` —— 自定义底稿无模板，"
        "落到既有「模板 → OO 缓存」路径必然 FileNotFoundError → config 404"
    )


@pytest.mark.parametrize(
    "func,why",
    [
        (
            "get_sheet_onlyoffice_config",
            "config 端点不分流 ⇒ 点「在线编辑」直接 404（2026-08-08 实测形态）",
        ),
        (
            "get_sheet_wopi_contents",
            "WOPI 下载不分流 ⇒ OnlyOffice 拉不到文件，编辑器空白",
        ),
    ],
)
def test_custom_branch_wired_in_read_paths(func: str, why: str):
    """config 与 WOPI 下载两处必须先试 custom 分流。"""
    code = _strip_comments(_src(ROUTER))
    body = _func_body(code, func)
    assert "_resolve_custom_wp_file(" in body, f"{func} 未接 custom 分流：{why}"


def test_custom_branch_wired_in_callback():
    """callback 落盘必须写业务文件本体，否则 OO 改动进不了投影。

    判据形态而非标识符 —— 只断言「函数体里出现该符号」挡不住
    「算出来但没用」（memory 记的弱判据坑）。
    """
    code = _strip_comments(_src(ROUTER))
    body = _func_body(code, "post_sheet_onlyoffice_callback")
    assert "_resolve_custom_wp_file(" in body, (
        "callback 未接 custom 分流 ⇒ OO 保存只落 OO 缓存，"
        "而 refresh_custom_projection 读 wp.file_path（业务文件）⇒ 两份 xlsx 打架"
    )
    # target 必须真的被赋成 custom 路径（不是算完丢弃）
    assert re.search(r"target\s*=\s*_custom_target", body), (
        "callback 里算出 custom 目标却没赋给 target ⇒ 仍写 OO 缓存（dead branch）"
    )


# ─── Property: 判定与投影同源 ──────────────────────────────────────────────


def test_sync_custom_predicate_exists():
    """OO 路径拿不到 db，必须有同步版判定（异步版在此不可用）。"""
    code = _strip_comments(_src(CTX))
    assert "def resolve_is_custom_sync(" in code, (
        "缺少 `resolve_is_custom_sync` —— OO 的 `_resolve_wp_file` 调用链是同步的，"
        "在那里 await 异步判定会抛 TypeError 并被吞成「退回既有路径」"
    )


def test_projection_reads_business_file_path():
    """投影读 `wp.file_path` —— 这是 OO 侧必须与之同源的那个真源。

    该断言是「同源」判据的另一半：投影侧一旦改读别处，本守卫要打红提醒
    OO 侧跟进（否则又出现两份 xlsx）。
    """
    code = _strip_comments(_src(PROJ))
    body = _func_body(code, "refresh_custom_projection")
    assert 'getattr(wp, "file_path"' in body or "wp.file_path" in body, (
        "refresh_custom_projection 不再读 wp.file_path ⇒ 与 OO 侧分流目标失去同源基准"
    )


def test_custom_resolver_does_not_touch_sheet_visibility():
    """custom 恒单 sheet，禁对业务文件本体动 sheet 可见性（会真实改写用户底稿）。"""
    code = _strip_comments(_src(ROUTER))
    body = _func_body(code, "_resolve_custom_wp_file")
    for banned in ("_hide_non_target_sheets", "_ensure_all_sheets_visible"):
        assert banned not in body, (
            f"custom 解析里出现 {banned} —— custom 单 sheet 无此需要，"
            "而对业务文件本体改可见性会污染用户底稿"
        )


def test_custom_resolver_actually_returns_business_file(tmp_path):
    """行为级判据：真跑 `_resolve_custom_wp_file`，必须返回**业务文件本体**。

    🔴 只做源码级「出现 wp.file_path 字样」的断言挡不住把 `raw` 改成别的来源
    （变异实测 GREEN）—— 字面还在、行为已错。故此处真实调用一次。
    """
    from app.routers import wp_onlyoffice_router as R

    biz = tmp_path / "ZZGUARD1.xlsx"
    import openpyxl

    wb = openpyxl.Workbook()
    wb.active.title = "ZZGUARD1"
    wb.active["A1"] = 1
    wb.save(str(biz))
    wb.close()

    class _WP:
        file_path = str(biz)
        source_type = None
        id = "guard"

    # 让 custom 判定为真（判定本身另有守卫，此处只验分流目标）
    import app.services.custom_workpaper_context as CTX_MOD

    orig = CTX_MOD.resolve_is_custom_sync
    CTX_MOD.resolve_is_custom_sync = lambda wp, code: True  # type: ignore[assignment]
    try:
        got = R._resolve_custom_wp_file(_WP(), "ZZGUARD1")
    finally:
        CTX_MOD.resolve_is_custom_sync = orig  # type: ignore[assignment]

    assert got is not None, "custom 解析返回 None ⇒ 会退回「模板→缓存」路径 ⇒ config 404 复发"
    assert Path(got).resolve() == biz.resolve(), (
        f"custom 解析目标 {got} 不是业务文件本体 {biz} ⇒ "
        "OO 与投影读不同文件，「xlsx 本体唯一权威」被破坏"
    )
    assert "onlyoffice" not in str(got).replace("\\", "/").lower(), (
        "custom 解析落到 OO 缓存目录 ⇒ callback 写缓存而投影读业务文件 ⇒ 两份 xlsx 打架"
    )


def test_custom_resolver_is_fail_soft():
    """解析失败必须返回 None 退回既有路径（零回归方向），不得抛异常。"""
    code = _strip_comments(_src(ROUTER))
    body = _func_body(code, "_resolve_custom_wp_file")
    assert "return None" in body, "custom 解析必须能返回 None 以退回既有「模板→缓存」路径"
    assert "except Exception" in body, "custom 解析必须 fail-soft，异常不得冒泡成 500"


# ─── 反向自检（防判据空转）────────────────────────────────────────────────


def test_strip_comments_actually_strips():
    """`_strip_comments` 必须真的剥掉注释与 docstring，否则上面全部判据可被注释骗过。"""
    sample = '''
def f():
    """docstring 里写 _resolve_custom_wp_file( 反例"""
    # 注释里也写 _resolve_custom_wp_file(
    return 1
'''
    stripped = _strip_comments(sample)
    assert "_resolve_custom_wp_file(" not in stripped, (
        "剥注释失效 ⇒ 本文件全部「必须出现某符号」判据都会被注释里的反例满足"
    )
    assert "return 1" in stripped, "剥注释误伤了真实代码"


def test_func_body_skips_multiline_signature():
    """`_func_body` 必须跳过多行参数列表（否则截出来只有签名，断言恒假红）。"""
    sample = """
def g(
    a: int,
    b: str,
) -> dict:
    marker_inside = 1
    return {}
"""
    body = _func_body(sample, "g")
    assert "marker_inside" in body, "多行签名下截取函数体失败（memory 已记该坑）"
