# -*- coding: utf-8 -*-
"""模板覆盖层的写入门与结构性判据。

spec: .kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/
Requirements: 1.5
Properties: 5

═══ 本文件现在覆盖哪两条 ═══

| Task | 判据 | 形态 |
|---|---|---|
| 4 / 5 | Property 5 覆盖层根与权威目录互不包含 | 三种失守情形逐个真调用 + import 期行为判据 |
| 101 | 执行备份的脚本扫描面含 `OVERRIDE_ROOT` | 真调用根解析 + 反向自检 + AST 可达性 |

═══ 判据纪律 ═══

* 「字符存在」型不算判据。本文件对源码的判断一律走 **AST**（天然不会把 docstring
  里叙述性提到的符号名当成真实引用），对常量的判断一律**真调用**。
* Task 101 那条必须有**反向自检**：若判据在修正前的旧口径下也通过，说明它恒真。
  故 :func:`test_task101_old_cwd_relative_root_did_not_cover_override_root` 断言旧口径
  **不**覆盖 —— 这条一旦变绿，说明整条判据失去意义。
* 分母断言：权威目录 476 条索引、覆盖层异常 6 个、备份扫描根 ≥ 1。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import uuid
from pathlib import Path

import pytest

from app.models.template_library_models import TemplateLevel
from app.services.workpaper_sync.models import SyncDomainError
from app.services.wp_template_override import (
    AUTHORITATIVE_ROOT,
    EDITABLE_FORMATS,
    OVERRIDE_ERRORS,
    OVERRIDE_ROOT,
    SCOPE_PRIORITY,
    OverrideRootEscapeError,
    assert_error_codes_distinct,
    assert_override_root_disjoint_from_authoritative,
    assert_target_within_override_root,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = _REPO_ROOT / "backend"
_OVERRIDE_MODULE = _BACKEND_DIR / "app" / "services" / "wp_template_override.py"
_BACKUP_SCRIPT = _BACKEND_DIR / "scripts" / "ops" / "backup.py"
_VERIFY_SCRIPT = _BACKEND_DIR / "scripts" / "check" / "verify_backup.py"
_STORAGE_ROOTS_MODULE = _BACKEND_DIR / "scripts" / "_storage_roots.py"

#: 权威目录索引条数 —— 分母，防判据在空集上恒真。
_EXPECTED_INDEX_ENTRIES = 476

#: 格式分布。可编辑集合 = xlsx 349；其余 127 份走上传替换（Requirement 7.2 覆盖面表）。
_EXPECTED_FORMAT_DISTRIBUTION = {
    "xlsx": 349,
    "docx": 107,
    "xlsm": 17,
    "doc": 2,
    "xls": 1,
}


def _load_storage_roots():
    """加载 `backend/scripts/_storage_roots.py`（脚本目录不在包路径上）。"""
    scripts_dir = str(_BACKEND_DIR / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import _storage_roots  # noqa: PLC0415 —— 需先补 sys.path

    return _storage_roots


def _module_level_call_names(source: str) -> set[str]:
    """模块**顶层**语句里被调用的函数名集合（AST，非字符串搜索）。"""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            fn = node.value.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.add(fn.attr)
    return names


def _calls_within_function(source: str, func_name: str) -> set[str]:
    """某函数体内（含嵌套）被调用的名字集合。"""
    tree = ast.parse(source)
    target = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            target = node
            break
    if target is None:
        raise AssertionError(f"AST 里找不到函数 {func_name!r}")

    names: set[str] = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name):
                names.add(fn.id)
            elif isinstance(fn, ast.Attribute):
                names.add(fn.attr)
    return names


def _module_level_assigned_names(source: str) -> set[str]:
    """模块顶层被赋值的名字集合（含带注解的赋值）。"""
    names: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


# ═══════════════════════════════════════════════════════════════════════════
# Property 5 —— 覆盖层根与权威目录互不包含（Task 4 / 5，Requirement 1.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty5RootDisjoint:
    """三种失守情形均抛，互不包含时通过。"""

    def test_current_constants_are_disjoint(self):
        """现行常量互不包含 —— 无参调用不抛。"""
        assert_override_root_disjoint_from_authoritative()

    def test_override_root_as_descendant_raises(self):
        """覆盖层根是权威目录的后代 ⇒ 抛。"""
        with pytest.raises(OverrideRootEscapeError) as exc:
            assert_override_root_disjoint_from_authoritative(
                override_root=AUTHORITATIVE_ROOT / "overrides",
                authoritative_root=AUTHORITATIVE_ROOT,
            )
        assert exc.value.error_code == "template_override_root_escape"

    def test_override_root_as_ancestor_raises(self):
        """覆盖层根是权威目录的祖先 ⇒ 抛（覆盖层清理会波及权威基线）。"""
        with pytest.raises(OverrideRootEscapeError):
            assert_override_root_disjoint_from_authoritative(
                override_root=AUTHORITATIVE_ROOT.parent,
                authoritative_root=AUTHORITATIVE_ROOT,
            )

    def test_override_root_equal_raises(self):
        """两者相等 ⇒ 抛。"""
        with pytest.raises(OverrideRootEscapeError):
            assert_override_root_disjoint_from_authoritative(
                override_root=AUTHORITATIVE_ROOT,
                authoritative_root=AUTHORITATIVE_ROOT,
            )

    def test_sibling_dirs_pass(self):
        """同级兄弟目录互不包含 ⇒ 通过（证明判据不是恒抛）。"""
        assert_override_root_disjoint_from_authoritative(
            override_root=_BACKEND_DIR / "storage" / "template_overrides",
            authoritative_root=_BACKEND_DIR / "wp_templates",
        )

    def test_string_prefix_lookalike_passes(self):
        """`wp_templates_backup` 不是 `wp_templates` 的后代 —— 字符串前缀比较会误判。"""
        assert_override_root_disjoint_from_authoritative(
            override_root=_BACKEND_DIR / "wp_templates_backup",
            authoritative_root=_BACKEND_DIR / "wp_templates",
        )


class TestImportTimeAssertion:
    """断言在 **import 期**真的执行，而不是只定义了一个没人调的函数。"""

    def test_module_body_calls_the_assertions(self):
        source = _OVERRIDE_MODULE.read_text(encoding="utf-8")
        called = _module_level_call_names(source)
        assert "assert_override_root_disjoint_from_authoritative" in called, (
            "模块顶层没有调用互斥断言 —— import 期不会暴露接线错误"
        )
        assert "assert_error_codes_distinct" in called

    def test_breached_constant_fails_at_import(self, tmp_path):
        """行为判据：把 `OVERRIDE_ROOT` 改成权威目录的后代后，import 必抛。

        这条比 AST 判据更硬 —— 它证明「import 会炸」这件事本身，而不只是
        「顶层有一行调用」。
        """
        source = _OVERRIDE_MODULE.read_text(encoding="utf-8")
        anchor = 'OVERRIDE_ROOT: Final[Path] = BACKEND_DIR / "storage" / "template_overrides"'
        assert source.count(anchor) == 1, "锚点未命中或命中多处 —— 判据脚本缺陷（ANCHOR-MISS）"

        breached = source.replace(
            anchor,
            'OVERRIDE_ROOT: Final[Path] = BACKEND_DIR / "wp_templates" / "overrides"',
        )
        assert breached != source

        mod_path = tmp_path / "breached_wp_template_override.py"
        mod_path.write_text(breached, encoding="utf-8")

        spec = importlib.util.spec_from_file_location(mod_path.stem, mod_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            # 🔴 不能用 `pytest.raises(OverrideRootEscapeError)`：临时模块会**重新执行**
            #    class 语句，产出一个同名但不同身份的类，isinstance 比对必失败。
            #    `SyncDomainError` 来自 `sys.modules` 里已加载的共享模块 ⇒ 身份一致，
            #    可以拿它当捕获类型，再按 error_code 与类名断言精确性。
            with pytest.raises(SyncDomainError) as exc:
                spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)

        assert type(exc.value).__name__ == "OverrideRootEscapeError"
        assert exc.value.error_code == "template_override_root_escape"


class TestOverrideConstants:
    """常量的分母与口径。"""

    def test_error_codes_distinct_with_denominator(self):
        assert len(OVERRIDE_ERRORS) == 6, "异常类数量变了，判据分母需同步复核"
        assert_error_codes_distinct()
        codes = {e.error_code for e in OVERRIDE_ERRORS}
        assert len(codes) == 6

    def test_scope_priority_matches_template_level(self):
        """作用域复用既有 `TemplateLevel` 三档（Gate 2），不新造词汇。"""
        assert [s.value for s in SCOPE_PRIORITY] == [
            "project",
            "group_custom",
            "firm_default",
        ]

    def test_editable_formats_excludes_xlsm(self):
        """Gate 3 裁决：17/17 份 xlsm 含 vbaProject.bin 且 OO 保留性未取证 ⇒ 排除。"""
        assert EDITABLE_FORMATS == frozenset({".xlsx"})

    def test_authoritative_root_matches_finder(self):
        """与 `wp_template_finder.TEMPLATES_DIR` 同一目录 —— 防两处口径漂移。

        本模块刻意不 import finder（Wave 2 起 finder 会反向调用本模块，会成环），
        所以「两处推导一致」必须由判据锁死而不是靠约定。
        """
        from app.services.wp_template_finder import TEMPLATES_DIR

        assert AUTHORITATIVE_ROOT == TEMPLATES_DIR

    def test_authoritative_index_denominator(self):
        """权威目录 476 条索引 + 格式分布 —— 分母断言，防后续判据在空集上恒真。

        索引自报的 `total_files` 与实际 `files` 条数**双向锁死**：只信一个的话，
        任一侧漂移都查不出来。
        """
        index_file = AUTHORITATIVE_ROOT / "_index.json"
        assert index_file.is_file(), f"权威索引不存在：{index_file}"
        payload = json.loads(index_file.read_text(encoding="utf-8"))

        files = payload["files"]
        assert len(files) == _EXPECTED_INDEX_ENTRIES, (
            f"索引条数 {len(files)} != {_EXPECTED_INDEX_ENTRIES}，"
            "分母变了 —— 全部覆盖面判据需复算"
        )
        assert payload["total_files"] == _EXPECTED_INDEX_ENTRIES, (
            f"索引自报 total_files={payload['total_files']} 与 {_EXPECTED_INDEX_ENTRIES} 不符"
        )

        by_format: dict[str, int] = {}
        for entry in files:
            by_format[entry["format"]] = by_format.get(entry["format"], 0) + 1
        assert by_format == _EXPECTED_FORMAT_DISTRIBUTION, (
            f"格式分布变了：{by_format} != {_EXPECTED_FORMAT_DISTRIBUTION}。"
            "可编辑集合（xlsx 349）与置灰集合（127）的口径需复算"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Task 101 —— 执行备份的脚本必须覆盖 OVERRIDE_ROOT（Requirement 1.5）
# ═══════════════════════════════════════════════════════════════════════════


class TestTask101BackupCoversOverrideRoot:
    """不得留「覆盖层在恢复时静默丢失」。

    Gate 1 原先只证明了备份**校验**脚本 (`verify_backup.py`) 的 `rglob("*")` 是全递归，
    没有确认**执行**备份的脚本。实测确认了一处真实缺口：两个脚本都相对 **cwd** 解析
    `./storage`，从仓库根跑时指向 `<repo>/storage`（281 个陈旧文件），而后端进程以
    `backend/` 为 cwd，运行时产物落在 `backend/storage/`（2308 个文件）。
    """

    def test_backup_scan_roots_cover_override_root(self):
        mod = _load_storage_roots()
        roots = mod.backup_scan_roots(require_existing=False)
        assert len(roots) >= 1, "扫描面为空 —— 判据会在空集上恒真"
        assert mod.path_is_covered(OVERRIDE_ROOT, roots), (
            f"OVERRIDE_ROOT={OVERRIDE_ROOT} 不在备份扫描面内："
            f"{[str(r.path) for r in roots]} —— 覆盖层会在恢复时静默丢失"
        )

    def test_runtime_storage_root_is_relative_to_backend(self):
        """运行时根必须相对 `backend/` 解析 —— 这是后端进程的 cwd。"""
        mod = _load_storage_roots()
        assert mod.runtime_storage_root() == (_BACKEND_DIR / "storage").resolve()

    def test_task101_old_cwd_relative_root_did_not_cover_override_root(self):
        """🔴 反向自检：修正前的口径**不**覆盖 `OVERRIDE_ROOT`。

        这条一旦变绿，说明上面那条判据已经恒真、失去意义。
        """
        mod = _load_storage_roots()
        old_root = mod.StorageRoot(
            path=(_REPO_ROOT / "storage").resolve(),
            label="storage",
            origin="修正前：相对 cwd（仓库根）解析",
        )
        assert not mod.path_is_covered(OVERRIDE_ROOT, [old_root]), (
            "旧口径竟然覆盖了 OVERRIDE_ROOT —— 要么目录布局变了，要么判据写错了"
        )

    def test_backup_script_really_uses_shared_root_resolution(self):
        """AST 可达性：`backup_storage` 真的调用了 `backup_scan_roots`。

        只 import 不用是「additive 注入即死代码」，四层静态检查全绿也照样没生效。
        """
        source = _BACKUP_SCRIPT.read_text(encoding="utf-8")
        calls = _calls_within_function(source, "backup_storage")
        assert "backup_scan_roots" in calls, (
            "backup_storage 没有调用 backup_scan_roots —— 扫描面修正未生效"
        )

    def test_backup_script_no_longer_defines_cwd_relative_storage_dir(self):
        """防回退：模块顶层不得再出现 `STORAGE_DIR` 这个相对 cwd 的常量。"""
        source = _BACKUP_SCRIPT.read_text(encoding="utf-8")
        assigned = _module_level_assigned_names(source)
        assert "STORAGE_DIR" not in assigned, (
            "backup.py 顶层又出现 STORAGE_DIR —— 相对 cwd 解析的缺口回来了"
        )

    def test_verify_script_no_longer_hardcodes_storage_dir(self):
        """`verify_backup.py` 原先硬编码 `Path("storage")`，连 STORAGE_ROOT 都不读。"""
        source = _VERIFY_SCRIPT.read_text(encoding="utf-8")
        assigned = _module_level_assigned_names(source)
        assert "STORAGE_DIR" not in assigned, (
            "verify_backup.py 顶层又出现硬编码 STORAGE_DIR"
        )

    def test_storage_root_resolution_is_not_fail_open(self):
        """解析不出任何存在的根时必须抛，而不是返回空列表让调用方"跳过"。"""
        mod = _load_storage_roots()
        assert issubclass(mod.StorageRootResolutionError, RuntimeError)

        calls = _calls_within_function(
            _BACKUP_SCRIPT.read_text(encoding="utf-8"), "backup_storage"
        )
        # 失败路径必须被显式处理成 failed（而不是 skipped）
        assert "backup_scan_roots" in calls
        source = _BACKUP_SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        handlers: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                if isinstance(node.type, ast.Name):
                    handlers.append(node.type.id)
        assert "StorageRootResolutionError" in handlers, (
            "backup.py 没有显式处理 StorageRootResolutionError"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 1 / 2 / 9 —— 越界门、写入目标位、扩展名门（Task 11 / 12）
# Requirements: 1.1, 1.2, 2.6
# ═══════════════════════════════════════════════════════════════════════════


def _names_in_expression(node: ast.AST) -> set[str]:
    """表达式里出现的全部标识符（含 `A / "x" / "y"` 这种 BinOp 链的左端）。"""
    found: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name):
            found.add(sub.id)
        elif isinstance(sub, ast.Attribute):
            found.add(sub.attr)
    return found


#: 会把字节写到某个路径上的调用。`os.replace` 的目标是**第二个位置参数**，
#: 其余都是「接收者就是目标」的方法调用。
_WRITE_ATTRS: frozenset[str] = frozenset({
    "write_bytes", "write_text", "mkdir", "unlink", "touch", "rmdir",
})
_COPY_FUNCS: frozenset[str] = frozenset({"copy", "copy2", "copyfile", "copytree", "move"})

#: 权威目录的两个名字（本模块叫 AUTHORITATIVE_ROOT，finder 里叫 TEMPLATES_DIR）。
_AUTHORITATIVE_NAMES: frozenset[str] = frozenset({"AUTHORITATIVE_ROOT", "TEMPLATES_DIR"})


class TestProperty1RootEscapeGate:
    """越界门：`..` 穿越 / 绝对路径 / 符号链接三形态各一例。"""

    def test_dotdot_traversal_is_rejected(self):
        with pytest.raises(OverrideRootEscapeError):
            assert_target_within_override_root(OVERRIDE_ROOT / ".." / "escaped.xlsx")

    def test_absolute_path_outside_root_is_rejected(self):
        with pytest.raises(OverrideRootEscapeError):
            assert_target_within_override_root(AUTHORITATIVE_ROOT / "A" / "hijacked.xlsx")

    def test_symlink_pointing_outside_is_rejected(self, tmp_path, monkeypatch):
        """符号链接形态 —— `resolve()` 解掉链接后才做前缀比较，这条才成立。"""
        from app.services import wp_template_override as mod

        fake_root = tmp_path / "template_overrides"
        fake_root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        link = fake_root / "sneaky"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:  # Windows 需要权限
            pytest.skip(f"本机无法创建符号链接：{exc}")

        monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)
        with pytest.raises(OverrideRootEscapeError):
            mod.assert_target_within_override_root(link / "payload.xlsx")

    def test_inside_root_passes_and_returns_resolved(self, tmp_path, monkeypatch):
        """正例：根内路径通过，且**返回 resolve 后的路径**。

        返回值这件事必须断言 —— 若调用方拿原始未 resolve 的路径去落盘，这道门只是装饰。
        """
        from app.services import wp_template_override as mod

        fake_root = tmp_path / "template_overrides"
        fake_root.mkdir()
        monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)

        got = mod.assert_target_within_override_root(fake_root / "sub" / "x.xlsx")
        assert got == (fake_root / "sub" / "x.xlsx").resolve()
        assert got.is_absolute()

    def test_wp_code_with_separator_is_rejected_before_path_join(self, tmp_path, monkeypatch):
        """`wp_code` 含分隔符必须在拼路径**之前**被拒。

        含 `/` 的 wp_code 虽然 resolve 后仍在根内（不越界），却会凭空造出目录层级，
        让两个不同的 wp_code 写到同一位置 —— 版本表的唯一索引会形同虚设。
        """
        from app.services import wp_template_override as mod

        fake_root = tmp_path / "template_overrides"
        fake_root.mkdir()
        monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)
        authoritative = tmp_path / "A1 foo.xlsx"
        authoritative.write_bytes(b"x")

        for bad in ("A1/../A2", "A1/sub", "..", "A1\\sub", "/abs"):
            with pytest.raises(OverrideRootEscapeError):
                mod.stage_override(
                    bad, authoritative, TemplateLevel.firm_default, b"payload",
                    version_id="v1",
                )


class TestProperty2NoAuthoritativeInWriteTargets:
    """AST：本模块任何写入调用的目标位都不出现权威目录。"""

    def test_write_targets_never_mention_authoritative_root(self):
        source = _OVERRIDE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        offenders: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func

            # ① 方法调用：接收者即写入目标（p.write_bytes() / p.mkdir() / ...）
            if isinstance(fn, ast.Attribute) and fn.attr in _WRITE_ATTRS:
                names = _names_in_expression(fn.value)
                hit = names & _AUTHORITATIVE_NAMES
                if hit:
                    offenders.append(f"L{node.lineno}: {fn.attr}() 的接收者含 {sorted(hit)}")

            # ② os.replace(src, dst) —— 目标是第二个位置参数
            if isinstance(fn, ast.Attribute) and fn.attr == "replace" and len(node.args) >= 2:
                names = _names_in_expression(node.args[1])
                hit = names & _AUTHORITATIVE_NAMES
                if hit:
                    offenders.append(f"L{node.lineno}: os.replace 的目标含 {sorted(hit)}")

            # ③ shutil.copy* / move —— 目标是第二个位置参数
            if isinstance(fn, ast.Attribute) and fn.attr in _COPY_FUNCS and len(node.args) >= 2:
                names = _names_in_expression(node.args[1])
                hit = names & _AUTHORITATIVE_NAMES
                if hit:
                    offenders.append(f"L{node.lineno}: {fn.attr} 的目标含 {sorted(hit)}")

            # ④ open(path, 'w'/'a'/'x'/'wb'...)
            if isinstance(fn, ast.Name) and fn.id == "open" and node.args:
                mode = ""
                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].value)
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        mode = str(kw.value.value)
                if any(c in mode for c in ("w", "a", "x", "+")):
                    names = _names_in_expression(node.args[0])
                    hit = names & _AUTHORITATIVE_NAMES
                    if hit:
                        offenders.append(f"L{node.lineno}: open(..., {mode!r}) 的目标含 {sorted(hit)}")

        assert not offenders, (
            "覆盖层模块把权威目录当成了写入目标：\n" + "\n".join(offenders)
        )

    def test_the_scanner_actually_catches_a_planted_violation(self):
        """🔴 反向自检：给扫描器喂一个合成违规，它必须抓到。

        否则「0 offenders」可能只是扫描器什么都没看。
        """
        planted = (
            "from pathlib import Path\n"
            "AUTHORITATIVE_ROOT = Path('/x')\n"
            "def bad(payload):\n"
            "    (AUTHORITATIVE_ROOT / 'A' / 'a.xlsx').write_bytes(payload)\n"
        )
        tree = ast.parse(planted)
        caught = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in _WRITE_ATTRS:
                    if _names_in_expression(node.func.value) & _AUTHORITATIVE_NAMES:
                        caught += 1
        assert caught == 1, f"扫描器漏掉了合成违规（caught={caught}）"

    def test_module_has_write_calls_at_all(self):
        """分母：本模块确实存在写入调用，否则 Property 2 在空集上恒真。"""
        source = _OVERRIDE_MODULE.read_text(encoding="utf-8")
        write_calls = 0
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in _WRITE_ATTRS or node.func.attr == "replace":
                    write_calls += 1
        assert write_calls >= 4, (
            f"本模块只有 {write_calls} 处写入调用 —— Property 2 的分母太小，判据接近恒真"
        )


class TestProperty9ExtensionGate:
    """扩展名门：来源扩展名与权威文件不一致时拒绝。"""

    @pytest.fixture
    def sandbox(self, tmp_path, monkeypatch):
        from app.services import wp_template_override as mod

        fake_root = tmp_path / "template_overrides"
        fake_root.mkdir()
        monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)
        return mod, tmp_path

    def test_xlsx_over_docx_is_rejected(self, sandbox):
        mod, tmp_path = sandbox
        authoritative = tmp_path / "B2-1 沟通函.docx"
        authoritative.write_bytes(b"docx-bytes")

        with pytest.raises(mod.OverrideExtensionMismatchError) as exc:
            mod.stage_override(
                "B2-1", authoritative, TemplateLevel.firm_default, b"xlsx-bytes",
                version_id="v1", source_extension=".xlsx",
            )
        assert exc.value.error_code == "template_override_extension_mismatch"

    def test_same_extension_passes(self, sandbox):
        mod, tmp_path = sandbox
        authoritative = tmp_path / "A1 程序表.xlsx"
        authoritative.write_bytes(b"orig")

        staged = mod.stage_override(
            "A1", authoritative, TemplateLevel.firm_default, b"new-bytes",
            version_id="v1", source_extension=".xlsx",
        )
        assert staged.staged_path.is_file()
        assert staged.staged_path.read_bytes() == b"new-bytes"
        assert staged.extension == ".xlsx"

    def test_case_insensitive_match_but_stored_lowercase_form(self, sandbox):
        """`.XLSX` 覆盖 `.xlsx` 放行，但落盘用权威文件的写法 —— 否则文件系统上会有两个 current。"""
        mod, tmp_path = sandbox
        authoritative = tmp_path / "A1 程序表.xlsx"
        authoritative.write_bytes(b"orig")

        staged = mod.stage_override(
            "A1", authoritative, TemplateLevel.firm_default, b"new",
            version_id="v1", source_extension=".XLSX",
        )
        assert staged.extension == ".xlsx"
        assert staged.staged_path.suffix == ".xlsx"

    def test_docx_rejected_only_when_editable_required(self, sandbox):
        """格式门只作用于浏览器内编辑；上传替换必须能覆盖 docx（Requirement 7.2）。"""
        mod, tmp_path = sandbox
        authoritative = tmp_path / "B2-1 沟通函.docx"
        authoritative.write_bytes(b"docx")

        # 上传替换路径：放行
        staged = mod.stage_override(
            "B2-1", authoritative, TemplateLevel.firm_default, b"replaced",
            version_id="v1", source_extension=".docx", require_editable_format=False,
        )
        assert staged.staged_path.is_file()

        # 浏览器内编辑路径：拒绝
        with pytest.raises(mod.OverrideFormatNotEditableError) as exc:
            mod.stage_override(
                "B2-1", authoritative, TemplateLevel.firm_default, b"edited",
                version_id="v2", source_extension=".docx", require_editable_format=True,
            )
        assert exc.value.error_code == "template_override_format_not_editable"

    def test_xlsm_rejected_for_in_browser_edit(self, sandbox):
        """Gate 3：17/17 份 xlsm 含 vbaProject.bin 且 OO 保留性未取证 ⇒ 不可浏览器内编辑。"""
        mod, tmp_path = sandbox
        authoritative = tmp_path / "S1 宏模板.xlsm"
        authoritative.write_bytes(b"xlsm")

        with pytest.raises(mod.OverrideFormatNotEditableError):
            mod.stage_override(
                "S1", authoritative, TemplateLevel.firm_default, b"edited",
                version_id="v1", source_extension=".xlsm", require_editable_format=True,
            )
        # 但上传替换必须放行（xlsm 也在 476/476 可覆盖面内）
        staged = mod.stage_override(
            "S1", authoritative, TemplateLevel.firm_default, b"uploaded",
            version_id="v2", source_extension=".xlsm", require_editable_format=False,
        )
        assert staged.staged_path.is_file()


class TestStageAndActivateSeparation:
    """落盘与生效必须能分开失败（写入顺序裁决的前提）。"""

    @pytest.fixture
    def sandbox(self, tmp_path, monkeypatch):
        from app.services import wp_template_override as mod

        fake_root = tmp_path / "template_overrides"
        fake_root.mkdir()
        monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)
        authoritative = tmp_path / "A1 程序表.xlsx"
        authoritative.write_bytes(b"authoritative-bytes")
        return mod, authoritative, fake_root

    def test_stage_does_not_make_it_current(self, sandbox):
        mod, authoritative, _root = sandbox
        staged = mod.stage_override(
            "A1", authoritative, TemplateLevel.firm_default, b"v1-bytes", version_id="ver-1",
        )
        assert staged.staged_path.is_file(), "版本文件应已落盘"
        assert not staged.current_path.exists(), "stage 不得让它成为当前版本"

        resolution = mod.resolve_template("A1")
        assert resolution is not None
        assert resolution.origin == "authoritative", "尚未 activate，解析必须仍是权威文件"

    def test_activate_makes_it_current_and_is_idempotent(self, sandbox):
        mod, authoritative, _root = sandbox
        staged = mod.stage_override(
            "A1", authoritative, TemplateLevel.firm_default, b"v1-bytes", version_id="ver-1",
        )
        mod.activate_staged_override(staged)

        assert staged.current_path.is_file()
        assert staged.current_path.read_bytes() == b"v1-bytes"
        marker = staged.current_path.with_name("current.version")
        assert marker.read_text(encoding="utf-8") == "ver-1"

        # 幂等：重复 activate 结果相同（一致性检查要能安全补切）
        mod.activate_staged_override(staged)
        assert staged.current_path.read_bytes() == b"v1-bytes"
        assert marker.read_text(encoding="utf-8") == "ver-1"

    def test_deactivate_falls_back_and_keeps_history(self, sandbox):
        """Requirement 4.5：摘掉当前版本后回落，且历史文件保留。"""
        mod, authoritative, _root = sandbox
        staged = mod.stage_override(
            "A1", authoritative, TemplateLevel.firm_default, b"v1-bytes", version_id="ver-1",
        )
        mod.activate_staged_override(staged)

        removed = mod.deactivate_override("A1", authoritative, TemplateLevel.firm_default)
        assert removed is True
        assert not staged.current_path.exists()
        assert staged.staged_path.is_file(), "versions/ 下的历史文件不得被删"

        # 幂等：再摘一次返回 False
        assert mod.deactivate_override("A1", authoritative, TemplateLevel.firm_default) is False

    def test_stage_leaves_no_staging_temp_file(self, sandbox):
        """临时文件必须被清掉，且与目标同目录（跨设备 os.replace 会失败）。"""
        mod, authoritative, root = sandbox
        mod.stage_override(
            "A1", authoritative, TemplateLevel.firm_default, b"x", version_id="ver-1",
        )
        leftovers = [p.name for p in root.rglob(".*.staging")]
        assert not leftovers, f"残留临时文件：{leftovers}"

    def test_missing_scope_id_raises_scope_unknown(self, sandbox):
        mod, authoritative, _root = sandbox
        with pytest.raises(mod.OverrideScopeUnknownError) as exc:
            mod.stage_override(
                "A1", authoritative, TemplateLevel.project, b"x", version_id="ver-1",
            )
        assert exc.value.error_code == "template_override_scope_unknown"


# ═══════════════════════════════════════════════════════════════════════════
# Property 16 / 17 / 18 / 19 —— 版本化、回滚、并发唯一性、回落（Task 13 / 14）
# Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
# ═══════════════════════════════════════════════════════════════════════════
#
# 这一组需要**真实 PostgreSQL**：部分唯一索引、`IS NOT DISTINCT FROM` 的三值语义、
# 以及 Property 18 的真并发在 SQLite 上都测不出来。非 PG 环境 skip 并说明。
#
# 🔴 全部用例在事务内跑、结束回滚 ⇒ 零残留。这不是洁癖：V154 有 BEFORE DELETE 触发器
#    禁止物理删除（Requirement 4.3），一旦提交了测试数据就**清不掉**。


def _pg_or_skip():
    from app.core.config import settings

    url = settings.DATABASE_URL
    if not url.startswith("postgresql"):
        pytest.skip(f"需要 PostgreSQL（部分唯一索引 / 真并发），实得 {url[:24]}")
    return url


@pytest.fixture
async def pg_session():
    """真库 AsyncSession，测试结束回滚。"""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    url = _pg_or_skip()
    engine = create_async_engine(url, pool_pre_ping=True, echo=False)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                # 前置：V154 必须已应用，否则下面测的是"表不存在"
                exists = (
                    await conn.exec_driver_sql(
                        "SELECT count(*) FROM information_schema.tables "
                        "WHERE table_name = 'workpaper_template_override_version'"
                    )
                ).scalar()
                if not exists:
                    pytest.skip(
                        "workpaper_template_override_version 不存在 —— 需先应用迁移 V154"
                    )
                yield session
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


#: 用于 DB 判据的 wp_code —— **必须是权威目录里真实存在的**。
#:
#: 🔴 第一版用随机 `OVR{hex}` 做 wp_code，两条判据当场红在 `resolve_template` 返回
#:    None 上。那不是 bug 而是设计：`resolve_template` 先取权威文件作定位基准与扩展名
#:    参照，权威侧解析不出来时**直接返回 None 且不查覆盖层** —— "覆盖"必须有被覆盖对象。
#:    顺带落一条实测语义：模板库里不存在的 wp_code（自定义底稿如 `ZZT26A`）**不能**有
#:    模板覆盖。这是正确的，但需要写下来，否则将来会被当缺陷去"修"。
_DB_TEST_WP_CODE = "A1"


@pytest.fixture
def override_sandbox(tmp_path, monkeypatch):
    """把 OVERRIDE_ROOT 指到 tmp；权威文件用**真实**的那一份。

    权威侧不做任何 monkeypatch —— 覆盖层的全部行为都相对真实权威目录成立才算数。
    """
    from app.services import wp_template_finder as finder
    from app.services import wp_template_override as mod

    fake_root = tmp_path / "template_overrides"
    fake_root.mkdir()
    monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)

    authoritative = finder.find_template_file_unresolved(_DB_TEST_WP_CODE)
    assert authoritative is not None and authoritative.is_file(), (
        f"{_DB_TEST_WP_CODE} 的权威模板不存在 —— DB 判据的前提不成立"
    )
    return mod, authoritative, fake_root


class TestProperty16And17VersionChain:
    """版本链：每次保存接父版本；回滚只改 is_current 不删行。"""

    async def test_second_save_links_parent_and_transfers_current(
        self, pg_session, override_sandbox
    ):
        mod, authoritative, _root = override_sandbox
        wp_code = _DB_TEST_WP_CODE

        v1 = mod.stage_override(
            wp_code, authoritative, TemplateLevel.firm_default, b"v1",
            version_id=str(uuid.uuid4()),
        )
        await mod.record_override_version(pg_session, v1)

        rows = await mod.list_override_versions(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert len(rows) == 1
        assert rows[0]["is_current"] is True
        assert rows[0]["parent_version_id"] is None, "首版的父版本必须为 NULL"

        v2 = mod.stage_override(
            wp_code, authoritative, TemplateLevel.firm_default, b"v2",
            version_id=str(uuid.uuid4()),
        )
        await mod.record_override_version(pg_session, v2)

        rows = await mod.list_override_versions(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert len(rows) == 2, "保存必须产生新行而不是就地覆盖"
        by_id = {str(r["id"]): r for r in rows}
        assert by_id[v2.version_id]["is_current"] is True
        assert by_id[v1.version_id]["is_current"] is False
        assert str(by_id[v2.version_id]["parent_version_id"]) == v1.version_id, (
            "新版本必须接上保存前的当前版本"
        )

    async def test_firm_default_demote_works_despite_null_ids(
        self, pg_session, override_sandbox
    ):
        """🔴 `firm_default` 下两个 id 都是 NULL，摘旧当前版本必须用
        `IS NOT DISTINCT FROM` 而不是 `=`。

        用 `=` 时三值逻辑让 WHERE 永不匹配 ⇒ 旧当前版本摘不掉 ⇒ 紧随的 INSERT 撞
        部分唯一索引。这条用例就是为了让那种写法必然报错。
        """
        mod, authoritative, _root = override_sandbox
        wp_code = _DB_TEST_WP_CODE

        for i in range(3):
            staged = mod.stage_override(
                wp_code, authoritative, TemplateLevel.firm_default, f"v{i}".encode(),
                version_id=str(uuid.uuid4()),
            )
            await mod.record_override_version(pg_session, staged)

        rows = await mod.list_override_versions(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert len(rows) == 3
        assert sum(1 for r in rows if r["is_current"]) == 1, "当前版本必须恰一条"

    async def test_rollback_promotes_history_without_deleting_rows(
        self, pg_session, override_sandbox
    ):
        """Property 17：回滚取历史版本，行数不减。"""
        mod, authoritative, _root = override_sandbox
        wp_code = _DB_TEST_WP_CODE

        staged = []
        for i in range(3):
            s = mod.stage_override(
                wp_code, authoritative, TemplateLevel.firm_default, f"payload-{i}".encode(),
                version_id=str(uuid.uuid4()),
            )
            await mod.record_override_version(pg_session, s)
            staged.append(s)

        before = await mod.list_override_versions(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert len(before) == 3

        promoted = await mod.promote_override_version(pg_session, staged[0].version_id)
        assert promoted["file_relpath"] == staged[0].relpath

        after = await mod.list_override_versions(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert len(after) == 3, "回滚不得删除任何版本记录"
        current = [r for r in after if r["is_current"]]
        assert len(current) == 1
        assert str(current[0]["id"]) == staged[0].version_id

        # 回滚后切 current 投影，解析必须拿到那个历史版本的字节
        mod.activate_staged_override(staged[0])
        resolution = mod.resolve_template(wp_code)
        assert resolution is not None
        assert resolution.origin == "override:firm_default"
        assert resolution.path.read_bytes() == b"payload-0"
        assert resolution.sha256 == staged[0].sha256

    def test_metadata_suffixes_cover_what_activate_writes(self, override_sandbox):
        """🔴 双向锁死：`activate_staged_override` 在当前版本目录里写下的**每一个**
        非模板文件，其后缀都必须登记在 `CURRENT_METADATA_SUFFIXES` 里。

        缺这条判据就会重演已发生的缺陷：解析用 `glob("current.*")` 找当前版本，
        activate 在同目录写 `current.version`，没排除它 ⇒ glob 拿到两个文件 ⇒
        判「多个当前版本」抛 `OverrideCurrentVersionAmbiguousError` ⇒ **一激活就再也
        解析不出来**。将来若加第二个元数据文件而忘了登记，这条会立刻红。

        行为判据（真跑一次 activate 再扫目录），不是「字符串存在」。
        """
        mod, authoritative, _root = override_sandbox
        staged = mod.stage_override(
            _DB_TEST_WP_CODE, authoritative, TemplateLevel.firm_default, b"payload",
            version_id=str(uuid.uuid4()),
        )
        mod.activate_staged_override(staged)

        code_dir = staged.current_path.parent
        stray = [
            p.suffix.lower()
            for p in code_dir.glob(f"{mod.CURRENT_STEM}.*")
            if p.is_file() and p.suffix.lower() != authoritative.suffix.lower()
        ]
        assert stray, "activate 一个元数据文件都没写 —— 判据在空集上恒真"
        unregistered = sorted(set(stray) - mod.CURRENT_METADATA_SUFFIXES)
        assert not unregistered, (
            f"activate 写了未登记的元数据后缀 {unregistered} —— "
            "解析的 glob 会把它当成另一个当前版本并抛歧义错"
        )

        # 反面确认：登记之后解析必须仍能工作
        resolution = mod.resolve_template(_DB_TEST_WP_CODE)
        assert resolution is not None
        assert resolution.origin == "override:firm_default"
        assert resolution.version_id == staged.version_id

    async def test_physical_delete_is_forbidden_by_db(self, pg_session, override_sandbox):
        """Requirement 4.3 在 DB 层的兜底 —— 应用层绕过也删不掉。"""
        import sqlalchemy as sa

        mod, authoritative, _root = override_sandbox
        wp_code = _DB_TEST_WP_CODE
        staged = mod.stage_override(
            wp_code, authoritative, TemplateLevel.firm_default, b"x",
            version_id=str(uuid.uuid4()),
        )
        await mod.record_override_version(pg_session, staged)

        sp = await pg_session.begin_nested()
        with pytest.raises(Exception) as exc:
            await pg_session.execute(
                sa.text(
                    f"DELETE FROM {mod.OVERRIDE_VERSION_TABLE} WHERE id = :id"
                ),
                {"id": staged.version_id},
            )
        await sp.rollback()
        assert "禁止物理删除" in str(exc.value) or "restrict" in str(exc.value).lower()


class TestProperty19FallbackAfterClear:
    """Property 19：删除覆盖后回落权威文件，sha256 与现算相等。"""

    async def test_clear_current_falls_back_to_authoritative(
        self, pg_session, override_sandbox
    ):
        import hashlib

        mod, authoritative, _root = override_sandbox
        wp_code = _DB_TEST_WP_CODE

        staged = mod.stage_override(
            wp_code, authoritative, TemplateLevel.firm_default, b"override-payload",
            version_id=str(uuid.uuid4()),
        )
        await mod.record_override_version(pg_session, staged)
        mod.activate_staged_override(staged)

        # 覆盖生效
        hit = mod.resolve_template(wp_code)
        assert hit is not None and hit.origin == "override:firm_default"

        # 删除覆盖：DB 摘当前版本 + 文件系统摘 current 投影
        affected = await mod.clear_current_override(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert affected == 1
        assert mod.deactivate_override(
            wp_code, authoritative, TemplateLevel.firm_default
        ) is True

        rows = await mod.list_override_versions(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        )
        assert len(rows) == 1, "删除覆盖不得删版本记录"
        assert all(r["is_current"] is False for r in rows)

        # 🔴 回落到权威文件，且 sha256 == 权威文件**现算**值
        back = mod.resolve_template(wp_code)
        assert back is not None
        assert back.origin == "authoritative"
        assert back.path == authoritative
        assert back.sha256 == hashlib.sha256(authoritative.read_bytes()).hexdigest()

        # 历史文件仍在（可回滚）
        assert staged.staged_path.is_file()

    async def test_clear_is_idempotent(self, pg_session, override_sandbox):
        mod, authoritative, _root = override_sandbox
        wp_code = _DB_TEST_WP_CODE
        assert await mod.clear_current_override(
            pg_session, wp_code, authoritative.stem, TemplateLevel.firm_default
        ) == 0


class TestProperty18ConcurrentCurrentVersion:
    """Property 18：并发下当前版本恰一条 —— 靠部分唯一索引，不靠应用层检查。

    🔴 必须用**两个真实连接**。单连接测不出来：应用层的 "先 SELECT 再 INSERT" 在单连接
    下永远看得见自己刚写的行，怎么写都对。

    做法：conn_a 插入 is_current=true 但**不提交**；conn_b 用短 `lock_timeout` 插同 key
    的 is_current=true。索引在起作用时 conn_b 会**阻塞**（等 conn_a 决定），随即因
    lock_timeout 失败。两个连接最后都 ROLLBACK ⇒ 零残留（V154 禁止 DELETE，不能留数据）。
    """

    #: 判据形态 = 「**被阻塞本身**就是索引生效的证据」。
    #:
    #: 🔴 第一版用 `SET LOCAL lock_timeout` + `get_raw_connection()` 直接发语句，
    #:    结果整轮测试 **10 分钟超时**：绕过 SQLAlchemy 的事务后 `SET LOCAL` 落在
    #:    别的事务里、对本次 INSERT 无效，于是 conn_b 无限等下去。
    #:    （所幸 conn_a 的 INSERT 仍在 SQLAlchemy 事务内，进程被杀时回滚，表里 0 行。）
    #:
    #: 现在改用 `asyncio.wait_for` 在**客户端**掐断：conn_b 超时 = 它确实在等 conn_a
    #: 决定 = 唯一索引在起作用。应用层的「先 SELECT 再 INSERT」检查**不会**阻塞
    #: （它会读到 0 条当前版本然后直接插入成功），所以这条判据能区分二者。
    _INSERT_SQL = """
        INSERT INTO workpaper_template_override_version
            (id, wp_code, authoritative_stem, scope, project_id, group_id,
             file_relpath, extension, sha256, is_current)
        VALUES
            (:id, :wp_code, :stem, 'firm_default', NULL, NULL,
             :relpath, '.xlsx', :sha, true)
    """

    @staticmethod
    def _payload(wp_code: str, stem: str, fill: str) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "wp_code": wp_code,
            "stem": stem,
            "relpath": f"firm_default/{wp_code}/{stem}/versions/{uuid.uuid4()}.xlsx",
            "sha": fill * 64,
        }

    async def test_second_concurrent_current_is_blocked_by_the_index(self):
        import asyncio

        import sqlalchemy as sa
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _pg_or_skip()
        engine_a = create_async_engine(url, pool_pre_ping=True, echo=False)
        engine_b = create_async_engine(url, pool_pre_ping=True, echo=False)

        wp_code = f"CONC{uuid.uuid4().hex[:8]}"
        stem = "concurrent-stem"
        insert = sa.text(self._INSERT_SQL)

        conn_a = conn_b = None
        try:
            conn_a = await engine_a.connect()
            conn_b = await engine_b.connect()
            trans_a = await conn_a.begin()
            trans_b = await conn_b.begin()

            exists = (
                await conn_a.exec_driver_sql(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'workpaper_template_override_version'"
                )
            ).scalar()
            if not exists:
                pytest.skip("需先应用迁移 V154")

            # conn_a 占住该 (wp_code, stem, firm_default) 的当前版本，**不提交**
            await conn_a.execute(insert, self._payload(wp_code, stem, "a"))

            # ① 同 key ⇒ 必须被阻塞（客户端掐断即为证据）
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(
                    conn_b.execute(insert, self._payload(wp_code, stem, "b")),
                    timeout=3.0,
                )

            await trans_b.rollback()
            await trans_a.rollback()
        finally:
            for c in (conn_b, conn_a):
                if c is not None:
                    try:
                        await c.close()
                    except Exception:  # noqa: BLE001 —— 被 cancel 的连接可能已不可用
                        pass
            await engine_b.dispose()
            await engine_a.dispose()

        # 零残留复核（V154 禁止 DELETE，只能靠回滚清）
        engine_c = create_async_engine(url, pool_pre_ping=True, echo=False)
        try:
            async with engine_c.connect() as conn:
                left = (
                    await conn.execute(
                        sa.text(
                            "SELECT count(*) FROM workpaper_template_override_version "
                            "WHERE wp_code = :c"
                        ),
                        {"c": wp_code},
                    )
                ).scalar()
        finally:
            await engine_c.dispose()
        assert left == 0, f"并发用例留下了 {left} 行 —— 必须靠回滚清"

    async def test_different_key_does_not_block(self):
        """🔴 正向对照：**不同** key 的并发 is_current=true 不该被阻塞。

        没有这条，上一条的超时可能来自任意别的原因（连接池耗尽、表锁、网络），
        「阻塞」就不再是「索引生效」的证据。
        """
        import asyncio

        import sqlalchemy as sa
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _pg_or_skip()
        engine_a = create_async_engine(url, pool_pre_ping=True, echo=False)
        engine_b = create_async_engine(url, pool_pre_ping=True, echo=False)

        stem = "concurrent-stem"
        code_a = f"CONC{uuid.uuid4().hex[:8]}"
        code_b = f"CONC{uuid.uuid4().hex[:8]}"
        insert = sa.text(self._INSERT_SQL)

        conn_a = conn_b = None
        try:
            conn_a = await engine_a.connect()
            conn_b = await engine_b.connect()
            trans_a = await conn_a.begin()
            trans_b = await conn_b.begin()

            exists = (
                await conn_a.exec_driver_sql(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = 'workpaper_template_override_version'"
                )
            ).scalar()
            if not exists:
                pytest.skip("需先应用迁移 V154")

            await conn_a.execute(insert, self._payload(code_a, stem, "a"))
            # 不同 wp_code ⇒ 不同索引键 ⇒ 不该等
            await asyncio.wait_for(
                conn_b.execute(insert, self._payload(code_b, stem, "b")),
                timeout=3.0,
            )

            await trans_b.rollback()
            await trans_a.rollback()
        finally:
            for c in (conn_b, conn_a):
                if c is not None:
                    try:
                        await c.close()
                    except Exception:  # noqa: BLE001
                        pass
            await engine_b.dispose()
            await engine_a.dispose()

    async def test_the_partial_unique_index_really_exists(self):
        """分母：索引真的在库里，否则上一条可能因别的原因失败而被误判成通过。"""
        from sqlalchemy.ext.asyncio import create_async_engine

        url = _pg_or_skip()
        engine = create_async_engine(url, pool_pre_ping=True, echo=False)
        async with engine.connect() as conn:
            row = (
                await conn.exec_driver_sql(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_wptov_one_current_per_scope'"
                )
            ).scalar()
        await engine.dispose()
        if row is None:
            pytest.skip("需先应用迁移 V154")
        assert "UNIQUE" in row.upper()
        assert "COALESCE" in row.upper(), (
            "索引必须用 COALESCE 归一 NULL —— PG 唯一索引对 NULL 不去重，"
            "否则 firm_default 下可插入任意多条 is_current=true"
        )
        assert "is_current" in row, "必须是 WHERE is_current 的**部分**索引"


# ═══════════════════════════════════════════════════════════════════════════
# Property 22 / 23 —— 受影响面与不倒灌（Task 22）
# Requirements: 6.1, 6.2, 6.3
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty22AffectedSurface:
    """受影响面必须与直接查库现算相等。"""

    async def test_affected_count_matches_a_direct_recount(self, pg_session):
        """🔴 `working_paper` 没有 `wp_code` 列（在 `wp_index`），必须 JOIN。

        少了这个 JOIN 的话结果恒空 ⇒ 报告说"不影响任何底稿"而实际影响了几百份。
        本判据用**另一种写法**现算同一个数字来交叉验证。
        """
        import sqlalchemy as sa

        from app.services import wp_template_override as mod

        # 先找一个真有底稿的 wp_code，否则判据在空集上恒真
        probe = (
            await pg_session.execute(
                sa.text(
                    """
                    SELECT wi.wp_code, count(*) AS n
                      FROM working_paper wp
                      JOIN wp_index wi ON wi.id = wp.wp_index_id
                     WHERE coalesce(wi.is_deleted, false) = false
                       AND coalesce(wp.is_deleted, false) = false
                     GROUP BY wi.wp_code
                     ORDER BY n DESC
                     LIMIT 1
                    """
                )
            )
        ).mappings().first()
        if probe is None or int(probe["n"]) == 0:
            pytest.skip("库里没有任何底稿 —— 受影响面判据会在空集上恒真")

        wp_code = probe["wp_code"]
        affected = await mod.count_affected_workpapers(pg_session, wp_code)

        assert affected, f"{wp_code} 明明有 {probe['n']} 份底稿，受影响面却是空的"
        total = sum(a["workpaper_count"] for a in affected)
        assert total == int(probe["n"]), (
            f"受影响面合计 {total} != 现算 {probe['n']}"
        )
        # 按项目分组：每个 project_id 只出现一次
        project_ids = [a["project_id"] for a in affected]
        assert len(project_ids) == len(set(project_ids)), "同一项目出现多行"

    async def test_unknown_wp_code_yields_empty_surface(self, pg_session):
        from app.services import wp_template_override as mod

        assert await mod.count_affected_workpapers(
            pg_session, f"NO-SUCH-{uuid.uuid4().hex[:8]}"
        ) == []

    async def test_the_join_is_really_needed(self, pg_session):
        """反向自检：不 JOIN 的写法拿不到结果 —— 证明 JOIN 不是多余的。

        若某天 `working_paper` 真加上了 `wp_code` 列，这条会红并提示可以简化。
        """
        import sqlalchemy as sa

        cols = (
            await pg_session.execute(
                sa.text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_name = 'working_paper' AND column_name = 'wp_code'"
                )
            )
        ).scalar()
        assert cols == 0, (
            "`working_paper` 现在有 wp_code 列了 —— `count_affected_workpapers` 的 JOIN "
            "可以简化，但要先确认两处 wp_code 一致"
        )


class TestProperty23NoRetroactiveRewrite:
    """既有底稿不被倒灌。"""

    async def test_existing_workpaper_files_are_untouched_by_a_save(
        self, pg_session, override_sandbox
    ):
        """保存覆盖后，抽样既有 `working_paper` 文件的 sha256 不变。"""
        import hashlib

        import sqlalchemy as sa

        mod, authoritative, _root = override_sandbox

        rows = (
            await pg_session.execute(
                sa.text(
                    """
                    SELECT wp.file_path
                      FROM working_paper wp
                      JOIN wp_index wi ON wi.id = wp.wp_index_id
                     WHERE wi.wp_code = :wp_code
                       AND wp.file_path IS NOT NULL
                       AND coalesce(wp.is_deleted, false) = false
                     LIMIT 8
                    """
                ),
                {"wp_code": _DB_TEST_WP_CODE},
            )
        ).scalars().all()

        # 解析到真实存在的文件。`file_path` 可能是相对路径，而后端进程的 cwd 是
        # `backend/`（见 Task 101 的 storage 根口径），故两个基准都试。
        existing: dict[str, str] = {}
        for rel in rows:
            for base in (_BACKEND_DIR, _REPO_ROOT):
                candidate = Path(rel) if Path(rel).is_absolute() else base / rel
                if candidate.is_file():
                    existing[str(candidate)] = hashlib.sha256(
                        candidate.read_bytes()
                    ).hexdigest()
                    break
        if not existing:
            pytest.skip(
                f"{_DB_TEST_WP_CODE} 没有磁盘上真实存在的既有底稿文件 —— "
                "不倒灌判据无可抽样对象"
            )

        staged = mod.stage_override(
            _DB_TEST_WP_CODE, authoritative, TemplateLevel.firm_default,
            b"override-that-must-not-touch-existing-workpapers",
            version_id=str(uuid.uuid4()),
        )
        await mod.record_override_version(pg_session, staged)
        mod.activate_staged_override(staged)

        drifted = [
            path
            for path, before in existing.items()
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != before
        ]
        assert not drifted, (
            f"保存覆盖改动了 {len(drifted)} 份既有底稿文件（模板变更不得倒灌）：{drifted[:3]}"
        )

    def test_router_declares_no_retroactive_rewrite(self):
        """响应必须**显式**声明不回溯改写（Requirement 6.2）。

        不是注释里说 —— 是响应模型里有这个字段且默认 False，调用方能读到。
        """
        from app.routers.wp_template_override_router import SaveResultOut

        fields = SaveResultOut.model_fields
        assert "retroactive_rewrite" in fields
        assert fields["retroactive_rewrite"].default is False
        assert "affected_workpapers" in fields

    def test_router_really_calls_the_affected_surface_counter(self):
        """AST 可达性：upload 端点真的调了 `count_affected_workpapers`。

        字段声明了却没人填 = 恒空的受影响面（additive 注入即死代码）。
        """
        source = (
            _BACKEND_DIR / "app" / "routers" / "wp_template_override_router.py"
        ).read_text(encoding="utf-8")
        calls = _calls_within_function(source, "upload_replacement")
        assert "count_affected_workpapers" in calls, (
            "upload 端点没有统计受影响面 —— 响应里那个字段会恒空"
        )
