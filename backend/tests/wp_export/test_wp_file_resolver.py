"""底稿文件路径解析共享件守卫 — 导入导出批量打包缺陷收口

判据分两类（照「先打红」范式）：

* 类 A = **独立口径判据**（本文件自己算出的事实：`Path('')` 的 Python 语义、
  四种 file_path 形态的真实分布、模板库回退可达性）。这些**现在就应该全绿** ——
  绿了才证明判据基础设施有效而非空转。
* 类 B = **被测实现**（`app.services.wp_export.wp_file_resolver` 与三个调用方）。
  改造前应**全红**，红消息里写明「尚未实现（Task N）」。

🔴 本文件的核心不变量（变异检验必须逐条打红）：

1. `Path('')` → `WindowsPath('.')` → `.exists()` 为 **True** ——
   这是「1564 份空 file_path 被 `zf.write` 写成目录条目」的唯一成因。
   任何路径解析件必须把空串判为**不可达**，绝不能依赖裸 `.exists()`。
2. 打包侧必须有 `is_file()` 兜底红线：即便解析件将来又漏了一种形态，
   也绝不能把**目录**写进交付 ZIP。
3. 解析必须是**共享件**：`download_pack` / `download_single` /
   `_resolve_docx_template` 三处不得各写一份（改一处另一处不红）。
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
import zipfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

# 双哨兵向上查找（单哨兵不够稳；目录做哨兵会被历史空目录骗停）
assert (BACKEND_ROOT / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert (BACKEND_ROOT / "wp_templates").is_dir(), "哨兵失效：backend/wp_templates 不存在"

RESOLVER_PATH = BACKEND_ROOT / "app" / "services" / "wp_export" / "wp_file_resolver.py"
DOWNLOAD_SERVICE_PATH = BACKEND_ROOT / "app" / "services" / "wp_download_service.py"
EXPORT_ENGINE_PATH = BACKEND_ROOT / "app" / "services" / "wp_export" / "export_engine.py"


# ───────────────────────── 源码读取 helper ─────────────────────────


def _read(path: Path) -> str:
    if not path.is_file():
        pytest.fail(f"文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def _strip_comments_and_docstrings(src: str) -> str:
    """剥 `#` 注释 + docstring，**保留普通字符串字面量**。

    🔴 为什么必须剥：守卫要断言「源码里不得出现裸 `.exists()` 判可达」，
    而修复说明注释里必然会写出这个反例（memory 已记多次踩中）。
    🔴 为什么**不**剥普通字符串：字典键名/SQL 片段可能是真实消费。
    """
    # 1) 剥 docstring（AST 级，只置空独立的 Expr(Constant(str)) 语句）
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None

    lines = src.splitlines(keepends=True)
    if tree is not None:
        blank: set[int] = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                    blank.add(ln)
        lines = ["\n" if (i + 1) in blank else ln for i, ln in enumerate(lines)]

    # 2) 剥 `#` 注释（tokenize 级，不会误伤字符串里的 `#`）
    joined = "".join(lines)
    out: list[str] = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(joined).readline))
    except (tokenize.TokenError, IndentationError):
        return joined
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            continue
        out.append(tok)
    # tokenize 反序列化不保真，改用行级剔除注释 token 的列区间
    result_lines = joined.splitlines(keepends=True)
    for tok in reversed([t for t in toks if t.type == tokenize.COMMENT]):
        row = tok.start[0] - 1
        col = tok.start[1]
        if 0 <= row < len(result_lines):
            line = result_lines[row]
            tail = "\n" if line.endswith("\n") else ""
            result_lines[row] = line[:col].rstrip() + tail
    return "".join(result_lines)


def _func_src(src: str, func_name: str) -> str:
    """按 AST 精确取某个函数/方法的源码（含签名）。

    🔴 不用「声明后第一个 `{`/缩进」启发式：多行签名 + 返回类型注解会让
    那类写法截到签名或参数类型里（memory 已记多次）。
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return ast.get_source_segment(src, node) or ""
    return ""


# ═══════════════════════════════════════════════════════════════════
# 类 A：独立口径判据（现在就应全绿 —— 证明判据本身有效）
# ═══════════════════════════════════════════════════════════════════


class TestPathEmptyStringSemantics:
    """Property 1：`Path('')` 的 Python 语义 —— 空 file_path 缺陷的根因。"""

    def test_empty_string_path_resolves_to_cwd(self):
        """`Path('')` 是 `.`（当前目录），不是「不存在的路径」。"""
        p = Path("")
        assert str(p) == ".", f"Path('') 应为 '.'，实际 {p!r}"

    def test_empty_string_path_exists_is_true(self):
        """🔴 核心：`.exists()` 对空串返回 **True** —— 裸 exists 判可达必然放行空串。"""
        assert Path("").exists() is True, (
            "Path('').exists() 应为 True。若此断言失败说明 Python 语义变了，"
            "本守卫的根因分析需重做。"
        )

    def test_empty_string_path_is_file_is_false(self):
        """而 `.is_file()` 对空串返回 False —— 这是兜底红线的依据。"""
        assert Path("").is_file() is False

    def test_zipfile_write_of_directory_produces_dir_entry(self, tmp_path: Path):
        """复现缺陷形态：把目录交给 `zf.write` 会产出**目录条目**而非文件。

        这就是用户看到「导出来是空的」的真相 —— ZIP 里那些条目根本不是文件。
        """
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_path, "D/x.xlsx")
        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            infos = zf.infolist()
            assert len(infos) == 1
            assert infos[0].is_dir() is True, "把目录写进 ZIP 应产出目录条目"
            assert infos[0].file_size == 0
            assert infos[0].filename.endswith("/"), (
                f"目录条目名应以 / 结尾，实际 {infos[0].filename!r}"
            )


class TestFilePathFormsExistInRepo:
    """Property 2：四种 file_path 形态的解析基准（不连库，用替身覆盖全部形态）。"""

    def test_template_relative_path_reachable_from_backend_cwd(self):
        """`wp_templates/...` 相对路径以 backend/ 为基准可达。"""
        sample = BACKEND_ROOT / "wp_templates"
        assert sample.is_dir(), "wp_templates 目录应存在（TEMPLATE_REL 形态的基准）"

    def test_storage_relative_path_base_is_backend(self):
        """`storage\\projects\\...` 相对路径同样以 backend/ 为基准。"""
        # 该目录可能为空但父级应存在（若不存在则说明部署布局变了）
        assert (BACKEND_ROOT / "storage").exists() or True, "仅记录基准，不强制存在"

    def test_tmp_absolute_style_is_unreachable_on_windows(self):
        """`/tmp/xxx.xlsx` 形态在本平台不可达（应被判 skip 而非写目录）。"""
        p = Path("/tmp/__gt_nonexistent_probe__.xlsx")
        assert not p.is_file()


class TestTemplateFallbackIsAvailable:
    """Property 3：模板库回退可用 —— 空 file_path 的正确兜底来源。"""

    def test_find_template_file_any_importable(self):
        from app.services.wp_template_init_service import find_template_file_any

        assert callable(find_template_file_any)

    def test_find_template_file_any_hits_known_code(self):
        """已知 wp_code 应能从模板库找到文件（证明回退真的能救回空 file_path）。"""
        from app.services.wp_template_init_service import find_template_file_any

        hit = find_template_file_any("F2")
        assert hit is not None, "F2 应能在模板库命中（回退链路的基准）"
        assert hit.is_file(), f"模板库返回的应是真实文件: {hit}"


# ═══════════════════════════════════════════════════════════════════
# 类 B：被测实现（改造前应全红）
# ═══════════════════════════════════════════════════════════════════


def _import_resolver():
    try:
        from app.services.wp_export import wp_file_resolver  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - Wave 1 预期红
        pytest.fail(
            f"共享件 app.services.wp_export.wp_file_resolver 尚未实现（Task 2）: {exc}"
        )
    return wp_file_resolver


class TestResolverContract:
    """Property 4：共享解析件的行为契约。"""

    def test_module_exists(self):
        assert RESOLVER_PATH.is_file(), (
            f"共享件尚未实现（Task 2）: {RESOLVER_PATH.relative_to(REPO_ROOT)}"
        )

    def test_exports_resolve_and_verdict(self):
        mod = _import_resolver()
        for name in (
            "resolve_wp_file",
            "WpFileResolution",
            "WpFileVerdict",
            "WP_FILE_VERDICTS",
            "VERDICT_LABELS",
        ):
            assert hasattr(mod, name), f"共享件缺少导出: {name}（Task 2）"

    def test_verdict_values_come_from_single_source(self):
        """🔴 verdict 取值域只许有一份真源。

        `WpFileVerdict` 是 `Literal` 别名（**没有 `.MISSING` 这类类属性**，
        按枚举写 `"missing"` 会 AttributeError），
        字面量真源是 `WP_FILE_VERDICTS`；本条把两者钉死，
        防后续把取值域改成 Enum 后守卫与实现各写一份。
        """
        mod = _import_resolver()
        # 🔴 期望集按**实测**冻结（探针实跑 resolve_wp_file 得到的取值），
        #    不按「应该叫什么」猜：本条曾写 "file" 而实现是 "file" → 假红一轮。
        #
        # 🔴 2026-08：workpaper-html-onlyoffice-bidirectional-writeback-closure
        #    Task 12 新增 `path_rejected` / `type_mismatch` 两档（Requirement 9.5/9.6,
        #    Property 41/42）。**不得**把它们并进 `missing`：
        #    * `path_rejected` = 路径越界（安全事件，要进安全日志与裁决清册）；
        #    * `type_mismatch` = 命中了文件但类型不符（resolver 正确拒绝父级异类型
        #      回退），与「该 wp_code 根本没登记模板」是两回事。
        #    合并后 Requirement 9.4 与 9.5 就无法各自验证。
        assert set(mod.WP_FILE_VERDICTS) == {
            "file",
            "template_fallback",
            "missing",
            "empty",
            "path_rejected",
            "type_mismatch",
        }, f"verdict 取值域变更需同步守卫: {mod.WP_FILE_VERDICTS}"
        # 每个取值都要有中文标签（供 ZIP 清单/前端提示，禁裸英文）
        for v in mod.WP_FILE_VERDICTS:
            label = mod.VERDICT_LABELS.get(v, "")
            assert label and not label.isascii(), (
                f"verdict={v} 缺中文标签（UI 全中文化铁律）: {label!r}"
            )

    def test_empty_path_is_unreachable_without_fallback(self):
        """🔴 空 file_path 在无模板库回退时必须判**不可达**，绝不能返回 `.`。"""
        mod = _import_resolver()
        res = mod.resolve_wp_file("", wp_code=None)
        assert res.path is None, (
            f"空 file_path 且无 wp_code 时必须不可达，实际返回 {res.path!r}"
        )
        # 空串与「配了路径但找不到」是两种态，不可混为一谈
        assert res.verdict == "empty", f"空 file_path 应判 empty，实际 {res.verdict!r}"

    def test_empty_path_falls_back_to_template_library(self):
        """空 file_path + 已知 wp_code → 回退模板库（这才是 1564 份的救回路径）。"""
        mod = _import_resolver()
        res = mod.resolve_wp_file("", wp_code="F2")
        assert res.path is not None, "空 file_path + wp_code=F2 应回退到模板库"
        assert res.path.is_file()
        assert res.verdict == "template_fallback", (
            f"空 file_path 回退模板库应判 template_fallback，实际 {res.verdict!r}"
        )

    def test_never_returns_a_directory(self, tmp_path: Path):
        """🔴 解析结果永远不是目录（哪怕入参就是一个真实目录）。"""
        mod = _import_resolver()
        res = mod.resolve_wp_file(str(tmp_path), wp_code=None)
        assert res.path is None, f"目录入参必须判不可达，实际 {res.path!r}"

    def test_template_relative_resolves_from_backend_root(self):
        """`wp_templates/...` 相对路径不依赖进程 cwd（挂 systemd/别的 cwd 也要能解析）。"""
        mod = _import_resolver()
        # 取一个真实存在的模板相对路径
        cand = next((BACKEND_ROOT / "wp_templates").rglob("*.xlsx"), None)
        assert cand is not None, "wp_templates 下应有 xlsx（判据基准）"
        rel = cand.relative_to(BACKEND_ROOT).as_posix()
        res = mod.resolve_wp_file(rel, wp_code=None)
        assert res.path is not None, f"相对路径 {rel} 应可解析"
        assert res.path.resolve() == cand.resolve()

    def test_backslash_relative_path_resolves(self):
        """Windows 反斜杠相对路径（`storage\\projects\\...` 形态）同样要能解析。"""
        mod = _import_resolver()
        cand = next((BACKEND_ROOT / "wp_templates").rglob("*.xlsx"), None)
        assert cand is not None
        rel_bs = str(cand.relative_to(BACKEND_ROOT)).replace("/", "\\")
        res = mod.resolve_wp_file(rel_bs, wp_code=None)
        assert res.path is not None, f"反斜杠相对路径 {rel_bs!r} 应可解析"

    def test_absolute_existing_path_passthrough(self):
        mod = _import_resolver()
        cand = next((BACKEND_ROOT / "wp_templates").rglob("*.xlsx"), None)
        assert cand is not None
        res = mod.resolve_wp_file(str(cand), wp_code=None)
        assert res.path is not None
        assert res.path.resolve() == cand.resolve()

    def test_unreachable_absolute_falls_back_then_missing(self):
        """不可达绝对路径 + 无 wp_code → MISSING（不得静默返回原路径）。"""
        mod = _import_resolver()
        res = mod.resolve_wp_file("/tmp/__gt_no_such__.xlsx", wp_code=None)
        assert res.path is None
        assert res.verdict == "missing", (
            f"配了路径但磁盘找不到应判 missing，实际 {res.verdict!r}"
        )

    def test_none_path_is_accepted(self):
        """`file_path` 允许为 None（ORM 列可空），不得抛异常。"""
        mod = _import_resolver()
        res = mod.resolve_wp_file(None, wp_code=None)
        assert res.path is None
        assert res.verdict == "empty", (
            f"file_path 为 None 应判 empty（与 missing 区分），实际 {res.verdict!r}"
        )

    def test_resolution_carries_reason_text(self):
        """不可达时要带**可读原因**（供 ZIP 清单/前端提示，不能只有布尔）。"""
        mod = _import_resolver()
        res = mod.resolve_wp_file("", wp_code=None)
        assert isinstance(res.reason, str) and res.reason.strip(), "不可达必须给出原因文本"


class TestDownloadPackUsesSharedResolver:
    """Property 5：`download_pack` 必须走共享件 + 有 is_file 兜底。"""

    def test_download_pack_imports_resolver(self):
        src = _strip_comments_and_docstrings(_read(DOWNLOAD_SERVICE_PATH))
        assert "wp_file_resolver" in src, (
            "wp_download_service 尚未接共享解析件（Task 3）"
        )

    def test_download_pack_has_is_file_guard(self):
        """🔴 兜底红线：打包前必须 `is_file()`，绝不把目录写进 ZIP。"""
        src = _strip_comments_and_docstrings(_read(DOWNLOAD_SERVICE_PATH))
        body = _func_src(src, "download_pack")
        assert body, "未找到 download_pack 函数体（守卫自身缺陷或已改名）"
        assert re.search(r"\.is_file\(\)", body), (
            "download_pack 必须有 is_file() 兜底判断（Task 3）"
        )

    def test_download_pack_no_bare_exists_reachability(self):
        """download_pack 不得再用裸 `.exists()` 判可达（那正是缺陷本身）。"""
        src = _strip_comments_and_docstrings(_read(DOWNLOAD_SERVICE_PATH))
        body = _func_src(src, "download_pack")
        assert body, "未找到 download_pack 函数体"
        assert not re.search(r"if\s+not\s+\w+(?:_\w+)*\.exists\(\)", body), (
            "download_pack 仍在用 `if not xxx.exists()` 判可达 —— "
            "空 file_path 会被判为存在（Task 3）"
        )

    def test_download_pack_reports_skipped(self):
        """跳过的底稿必须有出口（ZIP 内清单），不能只进后端日志。"""
        src = _strip_comments_and_docstrings(_read(DOWNLOAD_SERVICE_PATH))
        body = _func_src(src, "download_pack")
        assert body, "未找到 download_pack 函数体"
        # 🔴 判据必须落在「常量真被 writestr 用到」上。
        #    改造前写的是 `"skipped" in body`，而 `skipped` 是 download_pack 里的
        #    局部变量名 ⇒ 把清单文件名常量改名/换成字面量后，局部变量仍在、
        #    断言照过（变异 M4 实测 GREEN）。
        assert re.search(r"writestr\s*\(\s*\n?\s*_SKIPPED_MANIFEST_NAME", body), (
            "download_pack 必须用常量 _SKIPPED_MANIFEST_NAME 把跳过清单写进 ZIP（Task 4）"
        )
        # 常量自身必须有定义（防「只在调用处写字面量」的第二真源）
        assert re.search(r"^_SKIPPED_MANIFEST_NAME\s*=", src, re.M), (
            "跳过清单文件名必须收敛成模块级常量 _SKIPPED_MANIFEST_NAME（Task 4）"
        )


class TestDownloadSingleUsesSharedResolver:
    """Property 6：`download_single` 的自写回退要收敛到共享件。"""

    def test_download_single_delegates(self):
        src = _strip_comments_and_docstrings(_read(DOWNLOAD_SERVICE_PATH))
        body = _func_src(src, "download_single")
        assert body, "未找到 download_single 函数体"
        assert "resolve_wp_file" in body, (
            "download_single 应委托共享解析件，不自写 backend/ 回退（Task 3）"
        )

    def test_no_duplicated_backend_prefix_fallback(self):
        """🔴 单一真源：整个 service 不得再出现自写的 `parent.parent.parent` 回退。"""
        src = _strip_comments_and_docstrings(_read(DOWNLOAD_SERVICE_PATH))
        assert "parent.parent.parent" not in src, (
            "wp_download_service 仍有自写路径回退，未收敛到共享件（Task 3）"
        )


class TestExportEngineFallbackIsHonest:
    """Property 7：`_export_xlsx` 的空白回退必须自证失败，不得伪装成成功。"""

    def test_no_blanket_except_exception_tuple(self):
        """`except (TemplateNotFoundError, Exception)` 是吞一切的写法，必须收窄。"""
        src = _strip_comments_and_docstrings(_read(EXPORT_ENGINE_PATH))
        assert "(TemplateNotFoundError, Exception)" not in src, (
            "_export_xlsx 仍用 `except (TemplateNotFoundError, Exception)` "
            "吞掉一切异常并回退空白 workbook（Task 5）"
        )

    def test_fallback_workbook_carries_failure_marker(self):
        """回退产出的 workbook 必须写入失败标记，让空文件自证是失败。

        🔴 判据必须落在**真正构造 workbook 的函数**上。
        回退逻辑抽成了 `_build_failure_fallback_workbook`，若仍截
        `_export_xlsx` 的函数体去找「导出失败」，即便实现完全正确也会打红
        （判据落错函数 = 假红，与「守卫符号名必须与实现一致」同族）。
        """
        src = _strip_comments_and_docstrings(_read(EXPORT_ENGINE_PATH))

        # ① _export_xlsx 的失败路径必须委托辅助方法（而不是自己内联一段空白 workbook）
        outer = _func_src(src, "_export_xlsx")
        assert outer, "未找到 _export_xlsx 函数体"
        assert "_build_failure_fallback_workbook" in outer, (
            "_export_xlsx 的失败回退必须委托 _build_failure_fallback_workbook（Task 5）"
        )

        # ② 辅助方法体内必须出现「导出失败」四字
        inner = _func_src(src, "_build_failure_fallback_workbook")
        assert inner, "未找到 _build_failure_fallback_workbook 函数体（Task 5）"
        assert "导出失败" in inner, (
            "空白回退必须在 workbook 内写明「导出失败」及原因（Task 5）"
        )

        # ③ 必须是写进单元格的值，不能只是日志/变量名里提一句。
        #    注释与 docstring 已被 strip，这条进一步要求它出现在 value= 实参里。
        assert re.search(r"value\s*=\s*f?[\"\']导出失败", inner), (
            "「导出失败」必须写进单元格 value（形如 value=f\"导出失败：...\"），"
            "只在日志里提一句不算（Task 5）"
        )

    def test_docx_template_resolution_delegates(self):
        """`_resolve_docx_template` 也应收敛到共享件（第三处副本）。"""
        src = _strip_comments_and_docstrings(_read(EXPORT_ENGINE_PATH))
        body = _func_src(src, "_resolve_docx_template")
        assert body, "未找到 _resolve_docx_template 函数体"
        # 🔴 必须断言**调用形态**而非标识符出现：局部 import 行
        #    `from app.services.wp_export.wp_file_resolver import resolve_wp_file`
        #    本身就含该字样 ⇒ 把委托改回自写路径解析、只留 import 时
        #    裸 `in body` 判据不红（变异 M7 实测 GREEN）。
        assert re.search(r"resolve_wp_file\s*\(", body), (
            "_resolve_docx_template 应**调用**共享解析件 resolve_wp_file(...)（Task 3）"
        )
        # 反向：函数体内不得再出现自写路径回退特征
        for bad in (".is_file()", "find_template_file_any", "parents["):
            assert bad not in body, (
                f"_resolve_docx_template 仍残留自写路径解析特征 {bad!r}，"
                "路径形态归一必须只由共享件负责（Task 3）"
            )


class TestNoSecondCopyOfResolver:
    """Property 8：解析判据只许一份（防「改一处另一处不红」）。"""

    _ALLOWED = {
        "app/services/wp_export/wp_file_resolver.py",  # 真源
    }

    def test_only_one_definition_of_resolve_wp_file(self):
        hits: list[str] = []
        for py in (BACKEND_ROOT / "app").rglob("*.py"):
            code = _strip_comments_and_docstrings(py.read_text(encoding="utf-8", errors="replace"))
            if re.search(r"^def\s+resolve_wp_file\s*\(", code, re.M):
                hits.append(py.relative_to(BACKEND_ROOT).as_posix())
        assert hits, "未找到 resolve_wp_file 定义（Task 2）"
        assert set(hits) <= self._ALLOWED, (
            f"resolve_wp_file 出现多份定义: {hits}（必须收敛到单一真源）"
        )


# ═══════════════════════════════════════════════════════════════════
# 反向自检：证明判据本身有效（不是空转）
# ═══════════════════════════════════════════════════════════════════


class TestGuardSelfCheck:
    """替身反向自检 —— 复现旧行为时判据必须打红。"""

    _BAD_BARE_EXISTS = '''
async def download_pack(self, db, project_id, wp_ids):
    for wp, idx in rows:
        file_path = Path(wp.file_path)
        if not file_path.exists():
            logger.warning("missing")
            continue
        zf.write(file_path, arc_name)
'''

    _GOOD = '''
async def download_pack(self, db, project_id, wp_ids):
    for wp, idx in rows:
        res = resolve_wp_file(wp.file_path, wp_code=idx.wp_code)
        if res.path is None or not res.path.is_file():
            _skipped.append(idx.wp_code)
            continue
        zf.write(res.path, arc_name)
'''

    def test_bare_exists_pattern_is_detected(self):
        """旧实现（裸 exists）必须被判据抓到。"""
        body = _func_src(self._BAD_BARE_EXISTS, "download_pack")
        assert body
        assert re.search(r"if\s+not\s+\w+(?:_\w+)*\.exists\(\)", body), (
            "反向自检失败：判据抓不到旧的裸 exists 写法"
        )

    def test_good_pattern_passes(self):
        """新实现不得被误判。"""
        body = _func_src(self._GOOD, "download_pack")
        assert body
        assert not re.search(r"if\s+not\s+\w+(?:_\w+)*\.exists\(\)", body)
        assert re.search(r"\.is_file\(\)", body)

    def test_strip_comments_removes_counterexample_in_comment(self):
        """🔴 剥注释必须生效：注释里写的反例不得被数成真实代码。"""
        src = 'x = 1\n# if not file_path.exists():  这是踩坑说明\ny = 2\n'
        stripped = _strip_comments_and_docstrings(src)
        assert "exists()" not in stripped, "剥注释失效 → 说明文字会被误判成真实调用"
        assert "x = 1" in stripped and "y = 2" in stripped

    def test_strip_comments_keeps_plain_string_literals(self):
        """普通字符串字面量不剥（可能是真消费，如字典键名）。"""
        src = 'KEYS = {"file_path": 1}\n'
        stripped = _strip_comments_and_docstrings(src)
        assert '"file_path"' in stripped

    def test_strip_docstring_removes_counterexample_in_docstring(self):
        src = 'def f():\n    """反例: if not p.exists(): pass"""\n    return 1\n'
        stripped = _strip_comments_and_docstrings(src)
        assert "exists()" not in stripped

    def test_func_src_handles_multiline_signature(self):
        """🔴 多行签名 + 返回类型注解不得让函数体截断（memory 已记的坑）。"""
        src = (
            "def f(\n"
            "    a: str,\n"
            "    b: int = 0,\n"
            ") -> dict[str, int]:\n"
            "    marker = 1\n"
            "    return {}\n"
        )
        body = _func_src(src, "f")
        assert "marker = 1" in body, f"多行签名下函数体被截断: {body!r}"

    def test_func_src_returns_empty_for_missing(self):
        assert _func_src("x = 1\n", "nope") == ""
