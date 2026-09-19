# -*- coding: utf-8 -*-
"""模板覆盖层无损判据 —— OnlyOffice 编辑会话与保存路径。

spec: .kiro/specs/excel-template-override-layer-and-onlyoffice-template-editor/
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7
Properties: 10, 11, 12, 13, 14, 15

═══ 取证模板为什么选 K11（AC 3.5 要求"模板选取有明确理由"）═══

`K11 资产减值损失.xlsx` 现读指标与 design.md 里记录的 **openpyxl 全量重写毁坏样本**
逐项吻合 —— 它就是那次毁坏的原始样本：

| 指标 | K11 现读 | design.md 记录的毁坏后 |
|---|---:|---|
| zip 部件数 | **37** | 19（丢 printerSettings / worksheets/_rels / sharedStrings / calcChain / 批注 / customXml） |
| 共享公式主格 | **13** | 0（整组被摊平） |
| 非空缓存值 | **716** | 28 |
| printerSettings 部件 | **7** | 0（全丢） |
| worksheets/_rels 部件 | **7** | 1（丢 6 个） |
| 跨 sheet 引用（去重） | **201** | —— |
| sheet 数 | **7** | —— |

用它取证的意义是：**如果本 spec 的落盘路径重新引入了那类毁坏，这些数字会立刻掉下来。**
Property 14 断言跨 sheet 引用数 > 0，防止挑到一个恰好没有跨 sheet 引用的模板让判据恒真。

═══ 判据纪律 ═══

* Property 11 复用已交付的 `excel_sheet_visibility.assert_only_workbook_part_changed`
  （design.md 明写要复用，不再抄一份逐部件比对）。
* Property 15 是 **AST 可达性**而不是「字符串存在」：从落盘入口出发收集调用图涉及的模块，
  对这些模块检查是否出现有损中间层符号。只查一个文件会漏掉它 import 的那些。
"""

from __future__ import annotations

import ast
import io
import re
import zipfile
from pathlib import Path

import pytest

from app.models.template_library_models import TemplateLevel

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_DIR = _REPO_ROOT / "backend"
_TEMPLATES_DIR = _BACKEND_DIR / "wp_templates"
_OVERRIDE_MODULE = _BACKEND_DIR / "app" / "services" / "wp_template_override.py"
_VISIBILITY_MODULE = (
    _BACKEND_DIR / "app" / "services" / "workpaper_sync" / "excel_sheet_visibility.py"
)

#: 取证模板 —— 理由见模块 docstring。
_FORENSIC_WP_CODE = "K11"

#: K11 的现读指标基线。任一项掉下来 = 落盘路径引入了有损转换。
_K11_BASELINE = {
    "zip_parts": 37,
    "sheets": 7,
    "xsheet_refs_unique": 201,
    "shared_formula_masters": 13,
    "nonempty_cached_values": 716,
    "printer_settings": 7,
    "worksheet_rels": 7,
    "style_ids": 1742,
}

_XSHEET_RE = re.compile(r"(?:'([^']+)'|([A-Za-z0-9_\u4e00-\u9fff]+))!\$?[A-Z]{1,3}\$?\d+")
_SHARED_MASTER_RE = re.compile(r'<f[^>]*\bt="shared"[^>]*\bref="')
_V_RE = re.compile(r"<v>([^<]*)</v>")
_STYLE_RE = re.compile(r'\bs="(\d+)"')

_WORKBOOK_PART = "xl/workbook.xml"


def _structural_metrics(path: Path) -> dict:
    """五项结构指标 + 部件数 + 跨 sheet 引用集合。"""
    with zipfile.ZipFile(str(path)) as zf:
        names = zf.namelist()
        sheet_xmls = [
            n for n in names if n.startswith("xl/worksheets/") and n.endswith(".xml")
        ]
        xsheet_refs: set[str] = set()
        shared_masters = 0
        nonempty_v = 0
        style_ids: list[str] = []
        for n in sheet_xmls:
            text = zf.read(n).decode("utf-8", "replace")
            xsheet_refs.update(m.group(0) for m in _XSHEET_RE.finditer(text))
            shared_masters += len(_SHARED_MASTER_RE.findall(text))
            nonempty_v += sum(1 for v in _V_RE.findall(text) if v.strip())
            style_ids.extend(_STYLE_RE.findall(text))
        return {
            "zip_parts": len(names),
            "sheets": len(sheet_xmls),
            "xsheet_refs": xsheet_refs,
            "xsheet_refs_unique": len(xsheet_refs),
            "shared_formula_masters": shared_masters,
            "nonempty_cached_values": nonempty_v,
            "printer_settings": sum(1 for n in names if "printerSettings" in n),
            "worksheet_rels": sum(1 for n in names if n.startswith("xl/worksheets/_rels/")),
            "style_ids": len(style_ids),
            "style_id_sequence": tuple(style_ids),
        }


@pytest.fixture
def forensic_template():
    from app.services.wp_template_finder import find_template_file_unresolved

    path = find_template_file_unresolved(_FORENSIC_WP_CODE)
    if path is None or not path.is_file():
        pytest.skip(f"{_FORENSIC_WP_CODE} 的权威模板不存在")
    if path.suffix.lower() not in (".xlsx", ".xlsm"):
        pytest.skip(f"{_FORENSIC_WP_CODE} 不是 OOXML workbook：{path.suffix}")
    return path


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    from app.services import wp_template_override as mod

    fake_root = tmp_path / "template_overrides"
    fake_root.mkdir()
    monkeypatch.setattr(mod, "OVERRIDE_ROOT", fake_root)
    return mod, fake_root


# ═══════════════════════════════════════════════════════════════════════════
# Property 14 —— 取证模板的跨 sheet 引用数非零（先立分母）
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty14ForensicTemplateIsSuitable:
    def test_baseline_metrics_hold(self, forensic_template):
        """K11 的八项指标与登记基线逐项相同 —— 分母。

        基线掉下来有两种可能：有人改了 K11 权威模板（查是否合法），
        或某条路径真的重写过它（那正是本 spec 要防的）。
        """
        got = _structural_metrics(forensic_template)
        actual = {k: got[k] for k in _K11_BASELINE}
        assert actual == _K11_BASELINE, (
            f"K11 指标漂移：\n  期望 {_K11_BASELINE}\n  实得 {actual}"
        )

    def test_cross_sheet_reference_count_is_nonzero(self, forensic_template):
        """Property 14：跨 sheet 引用数 > 0，否则 Property 12 在空集上恒真。"""
        got = _structural_metrics(forensic_template)
        assert got["xsheet_refs_unique"] > 0
        assert got["xsheet_refs_unique"] == _K11_BASELINE["xsheet_refs_unique"]
        assert got["sheets"] > 1, "单 sheet 模板不可能有跨 sheet 引用"


# ═══════════════════════════════════════════════════════════════════════════
# Property 10 / 11 —— 会话层：整本模式 + 仅 workbook.xml 变
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty10And11SessionLayer:
    def test_session_makes_all_sheets_visible(self, sandbox, forensic_template):
        """Property 10 的服务层部分：工作副本全部 sheet 可见。

        （config 不含 `actionLink` 那一半在 router 判据里 —— 那是 Task 16 的 N3。）
        """
        from app.services.workpaper_sync.excel_sheet_visibility import read_sheet_entries

        mod, _root = sandbox
        session = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="sess-p10"
        )
        entries = read_sheet_entries(session.working_path)
        assert len(entries) == _K11_BASELINE["sheets"]
        hidden = [e.name for e in entries if not e.is_visible]
        assert not hidden, f"会话里仍有隐藏 sheet：{hidden}"

    def test_only_workbook_part_changes_when_session_starts(
        self, sandbox, forensic_template
    ):
        """Property 11：会话建立前后除 `xl/workbook.xml` 外全部部件字节相同。"""
        from app.services.workpaper_sync.excel_sheet_visibility import (
            assert_only_workbook_part_changed,
        )

        mod, _root = sandbox
        before = forensic_template.read_bytes()
        session = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="sess-p11"
        )
        after = session.working_path.read_bytes()

        # 复用已交付的结构性自检（design.md 明写要复用）
        assert_only_workbook_part_changed(before, after)

        # 且部件集合与数量不变
        got = _structural_metrics(session.working_path)
        assert got["zip_parts"] == _K11_BASELINE["zip_parts"]

    def test_authoritative_file_untouched_by_session(self, sandbox, forensic_template):
        """会话只动副本 —— 权威文件 sha256 不变。"""
        import hashlib

        mod, _root = sandbox
        before = hashlib.sha256(forensic_template.read_bytes()).hexdigest()
        mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="sess-untouched"
        )
        after = hashlib.sha256(forensic_template.read_bytes()).hexdigest()
        assert after == before, "会话建立改动了权威模板"

    def test_working_copy_lives_inside_override_root(self, sandbox, forensic_template):
        mod, root = sandbox
        session = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="sess-inside"
        )
        assert session.working_path.resolve().is_relative_to(root.resolve())

    def test_session_id_path_injection_is_rejected(self, sandbox, forensic_template):
        mod, _root = sandbox
        for bad in ("../escape", "a/b", "..", "/abs"):
            with pytest.raises(mod.OverrideRootEscapeError):
                mod.prepare_template_edit_session(
                    _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id=bad
                )

    def test_discard_is_idempotent(self, sandbox, forensic_template):
        mod, _root = sandbox
        mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="sess-discard"
        )
        assert mod.discard_template_edit_session("sess-discard") is True
        assert mod.discard_template_edit_session("sess-discard") is False


# ═══════════════════════════════════════════════════════════════════════════
# Property 12 / 13 —— 保存层：空保存后引用集合与五项指标不变
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty12And13SaveLayer:
    """「打开 → 不改任何内容 → 保存」后，结构一项不动。"""

    @staticmethod
    def _round_trip(mod, wp_code: str, session_id: str):
        session = mod.prepare_template_edit_session(
            wp_code, TemplateLevel.firm_default, session_id=session_id
        )
        staged = mod.commit_template_edit_session(session, version_id=f"{session_id}-v1")
        return session, staged

    def test_cross_sheet_reference_set_is_identical(self, sandbox, forensic_template):
        """Property 12：跨 sheet 引用去重集合**逐项**相同。"""
        mod, _root = sandbox
        _session, staged = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-p12")

        before = _structural_metrics(forensic_template)
        after = _structural_metrics(staged.staged_path)

        assert after["xsheet_refs_unique"] == before["xsheet_refs_unique"]
        missing = before["xsheet_refs"] - after["xsheet_refs"]
        extra = after["xsheet_refs"] - before["xsheet_refs"]
        assert not missing and not extra, (
            f"跨 sheet 引用集合变了：丢 {sorted(missing)[:10]} / 多 {sorted(extra)[:10]}"
        )

    def test_five_structural_metrics_are_identical(self, sandbox, forensic_template):
        """Property 13：共享公式主格 / 非空缓存值 / printerSettings / worksheets_rels /
        样式索引序列 —— 五项逐项不变。"""
        mod, _root = sandbox
        _session, staged = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-p13")

        before = _structural_metrics(forensic_template)
        after = _structural_metrics(staged.staged_path)

        for key in (
            "shared_formula_masters",
            "nonempty_cached_values",
            "printer_settings",
            "worksheet_rels",
        ):
            assert after[key] == before[key] == _K11_BASELINE[key], (
                f"{key}: 源 {before[key]} → 保存后 {after[key]}（基线 {_K11_BASELINE[key]}）"
            )
        assert after["style_id_sequence"] == before["style_id_sequence"], (
            "样式索引序列被重排 —— openpyxl 全量重写的典型特征"
        )
        assert after["zip_parts"] == before["zip_parts"] == _K11_BASELINE["zip_parts"]

    def test_empty_save_restores_workbook_part_to_source(self, sandbox, forensic_template):
        """空保存后 `xl/workbook.xml` 的内容必须回到源模板的样子。

        会话为了显示全部 sheet 改过它；保存时若不还原，覆盖版本会悄悄改变 sheet 可见性
        —— 用户没要求过的语义漂移。
        """
        mod, _root = sandbox
        _session, staged = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-restore")

        with zipfile.ZipFile(str(forensic_template)) as zf:
            source_xml = zf.read(_WORKBOOK_PART).decode("utf-8")
        with zipfile.ZipFile(str(staged.staged_path)) as zf:
            saved_xml = zf.read(_WORKBOOK_PART).decode("utf-8")
        assert saved_xml == source_xml, (
            "workbook.xml 未还原 —— 覆盖版本的 sheet 可见性与权威模板不一致"
        )

    def test_empty_save_is_byte_identical_to_source(self, sandbox, forensic_template):
        """最强形态：空保存后**除 workbook.xml 外**逐部件字节相同。

        workbook.xml 内容已由上一条锁定相同；它的**压缩字节**可能因重新 deflate 而不同，
        所以这里用逐部件比对而不是整文件 sha256。
        """
        from app.services.workpaper_sync.excel_sheet_visibility import (
            assert_only_workbook_part_changed,
        )

        mod, _root = sandbox
        _session, staged = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-bytes")
        assert_only_workbook_part_changed(
            forensic_template.read_bytes(), staged.staged_path.read_bytes()
        )

    def test_authoritative_still_untouched_after_save(self, sandbox, forensic_template):
        import hashlib

        mod, _root = sandbox
        before = hashlib.sha256(forensic_template.read_bytes()).hexdigest()
        self._round_trip(mod, _FORENSIC_WP_CODE, "sess-after-save")
        assert hashlib.sha256(forensic_template.read_bytes()).hexdigest() == before

    def test_staged_version_lands_under_authoritative_stem(self, sandbox, forensic_template):
        """🔴 版本目录必须按**权威**文件 stem 分级，不是按解析结果。

        已有覆盖时解析结果是 `current.xlsx`，若拿它的 stem 定位，第二次保存会落到
        `{wp_code}/current/` 而不是 `{wp_code}/{权威stem}/` —— 目录对不上，解析再也找不到。
        """
        mod, root = sandbox
        session, staged = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-stem")
        assert session.authoritative_path == forensic_template
        expected_dir = (
            root / "firm_default" / _FORENSIC_WP_CODE / forensic_template.stem / "versions"
        )
        assert staged.staged_path.parent == expected_dir, (
            f"版本落在 {staged.staged_path.parent}，期望 {expected_dir}"
        )

    def test_second_edit_round_still_uses_authoritative_stem(
        self, sandbox, forensic_template
    ):
        """在**已有覆盖**之上再编辑一轮 —— 这是上一条描述的缺陷唯一会暴露的场景。"""
        mod, root = sandbox

        s1, staged1 = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-r1")
        mod.activate_staged_override(staged1)
        resolved = mod.resolve_template(_FORENSIC_WP_CODE)
        assert resolved is not None and resolved.origin == "override:firm_default"
        assert resolved.path.name.startswith("current"), "此刻解析结果应是 current.xlsx"

        s2, staged2 = self._round_trip(mod, _FORENSIC_WP_CODE, "sess-r2")
        # 会话打开的是覆盖文件，但定位仍按权威 stem
        assert s2.source_path == resolved.path
        assert s2.authoritative_path == forensic_template
        assert staged2.staged_path.parent == staged1.staged_path.parent, (
            "第二轮的版本目录与第一轮不同 —— stem 用错了"
        )
        assert staged2.authoritative_stem == forensic_template.stem


# ═══════════════════════════════════════════════════════════════════════════
# Property 15 —— 落盘路径不含有损中间层（AST 可达性）
# ═══════════════════════════════════════════════════════════════════════════

#: 有损中间层的符号。出现在落盘路径可达的任何模块里即违规。
_LOSSY_TOKENS: frozenset[str] = frozenset({
    "openpyxl",
    "load_workbook",
    "univer",
    "Univer",
    "exceljs",
    "xlsxwriter",
    "read_excel",
    "to_excel",
    "ExcelWriter",
})

#: 落盘路径的入口函数。
_WRITE_PATH_ENTRIES: tuple[str, ...] = (
    "prepare_template_edit_session",
    "commit_template_edit_session",
    "stage_override",
    "activate_staged_override",
)


def _strip_docstrings(source: str) -> str:
    """剥掉全部 docstring 后再做符号判断。

    🔴 `_strip_comments` 类工具**不剥 docstring**。本模块的 docstring 里大量叙述性提到
    `openpyxl`（反面教材记录），不剥就会把叙述当成真实引用 ⇒ 判据恒红。
    （`test_task54_l_cycle_migration.py` 已在这里栽过一次。）
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body[0].value.value = ""
    return ast.unparse(tree)


class TestProperty15NoLossyIntermediateLayer:
    def test_write_path_modules_do_not_import_lossy_layers(self):
        """落盘路径可达的模块里不出现有损中间层符号。

        判据是 **AST**（剥 docstring 后 unparse 再解析），不是「文件里有没有这个词」。
        """
        offenders: list[str] = []
        for module_path in (_OVERRIDE_MODULE, _VISIBILITY_MODULE):
            stripped = _strip_docstrings(module_path.read_text(encoding="utf-8"))
            tree = ast.parse(stripped)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        if root in _LOSSY_TOKENS:
                            offenders.append(f"{module_path.name}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    if root in _LOSSY_TOKENS:
                        offenders.append(f"{module_path.name}: from {node.module} import …")
                    for alias in node.names:
                        if alias.name in _LOSSY_TOKENS:
                            offenders.append(
                                f"{module_path.name}: from {node.module} import {alias.name}"
                            )
                elif isinstance(node, ast.Name) and node.id in _LOSSY_TOKENS:
                    offenders.append(f"{module_path.name}: 引用 {node.id}")
                elif isinstance(node, ast.Attribute) and node.attr in _LOSSY_TOKENS:
                    offenders.append(f"{module_path.name}: 属性 .{node.attr}")

        assert not offenders, "落盘路径出现有损中间层：\n" + "\n".join(offenders)

    def test_the_scanner_catches_a_planted_import(self):
        """🔴 反向自检：喂一个合成的 openpyxl import，扫描器必须抓到。"""
        planted = "import openpyxl\ndef f():\n    return openpyxl.load_workbook('x')\n"
        tree = ast.parse(_strip_docstrings(planted))
        caught = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _LOSSY_TOKENS:
                        caught += 1
            elif isinstance(node, ast.Attribute) and node.attr in _LOSSY_TOKENS:
                caught += 1
        assert caught >= 2, f"扫描器漏了合成违规（caught={caught}）"

    def test_docstring_stripping_is_required_not_optional(self):
        """🔴 证明「必须剥 docstring」：不剥就会因叙述性提及而误判。

        这条同时是上面那条判据形态的正当性证明 —— 若某天有人把 `_strip_docstrings`
        去掉，这条会说明为什么不能去。
        """
        raw = _OVERRIDE_MODULE.read_text(encoding="utf-8")
        assert "openpyxl" in raw, (
            "本模块的 docstring 本应记录 openpyxl 反面教材 —— 若已删，本判据失去意义"
        )
        stripped = _strip_docstrings(raw)
        assert "openpyxl" not in stripped, (
            "剥 docstring 后仍出现 openpyxl —— 那就是**真实引用**，是违规"
        )

    def test_write_path_entries_exist(self):
        """分母：四个入口函数真的存在，否则 Property 15 在空集上恒真。"""
        tree = ast.parse(_OVERRIDE_MODULE.read_text(encoding="utf-8"))
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = [e for e in _WRITE_PATH_ENTRIES if e not in defined]
        assert not missing, f"落盘入口缺失：{missing}"

    def test_write_path_reaches_only_the_two_scanned_modules(self):
        """落盘入口的跨模块依赖只有被扫的那两个（+ finder 的纯路径解析）。

        没有这条，`_LOSSY_TOKENS` 扫描的模块集合可能漏掉某个真正在落盘路径上的模块，
        于是「0 offenders」只说明"我扫的那两个干净"。
        """
        tree = ast.parse(_OVERRIDE_MODULE.read_text(encoding="utf-8"))
        targets: set[str] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in _WRITE_PATH_ENTRIES:
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.ImportFrom) and sub.module:
                    if sub.module.startswith("app."):
                        targets.add(sub.module)
                elif isinstance(sub, ast.Import):
                    for alias in sub.names:
                        if alias.name.startswith("app."):
                            targets.add(alias.name)

        allowed = {
            "app.services.workpaper_sync.excel_sheet_visibility",  # zip 级可见性（已扫）
            "app.services.wp_template_finder",  # 纯文件系统路径解析，无 xlsx 读写
        }
        unexpected = targets - allowed
        assert not unexpected, (
            f"落盘入口引入了未登记的模块 {sorted(unexpected)} —— "
            "要么把它加进扫描集合，要么它不该在落盘路径上"
        )
        assert targets, "落盘入口一个跨模块依赖都没有 —— 判据可能没解析到函数体"


# ═══════════════════════════════════════════════════════════════════════════
# Property 10 的 router 半边 —— config 不含 actionLink（Task 16）
# Requirements: 3.1
# ═══════════════════════════════════════════════════════════════════════════
#
# 判据形态：**真调路由处理函数**（不经 HTTP 栈也不经依赖注入），断言返回的 config。
# 不用 `app.dependency_overrides` 是因为 `require_role([...])` 每次调用都返回**新**的闭包，
# 拿不到可作 override key 的稳定对象；直接调函数反而更硬 —— 测的是真实执行结果。


def _fake_request():
    """最小可用的 Starlette Request —— 只需支撑 `request.base_url`。"""
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/wp-template-overrides/K11/edit-session",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "query_string": b"",
        }
    )


def _fake_user():
    import uuid as _uuid
    from types import SimpleNamespace

    return SimpleNamespace(id=_uuid.uuid4(), username="tester")


class TestProperty10RouterIsWholeWorkbookMode:
    async def test_config_has_no_action_link(self, sandbox, forensic_template):
        """Property 10：编辑会话的 OO config **不含** `actionLink`。

        加了 actionLink 会把 OO 定位到某个 sheet 的书签上，审计师就看不到 sheet 间关系
        —— 而"看到全部 sheet 与 sheet 间公式"正是 Requirement 3 的目的。
        """
        import json

        from app.routers import wp_template_override_router as api

        _mod, _root = sandbox
        out = await api.create_edit_session(
            _FORENSIC_WP_CODE,
            _fake_request(),
            scope=TemplateLevel.firm_default.value,
            project_id=None,
            group_id=None,
            current_user=_fake_user(),
        )
        blob = json.dumps(out.onlyoffice_config, ensure_ascii=False)
        assert "actionLink" not in blob, f"config 里出现 actionLink：{blob[:400]}"
        assert out.onlyoffice_config["documentType"] == "cell"
        assert out.onlyoffice_config["editorConfig"]["mode"] == "edit"
        assert out.onlyoffice_config["document"]["fileType"] == "xlsx"

    async def test_session_working_copy_is_all_sheets_visible(self, sandbox, forensic_template):
        """端点建出来的那份工作副本，全部 sheet 可见。"""
        from app.routers import wp_template_override_router as api
        from app.services import wp_template_override as mod
        from app.services.workpaper_sync.excel_sheet_visibility import read_sheet_entries

        _mod, _root = sandbox
        out = await api.create_edit_session(
            _FORENSIC_WP_CODE, _fake_request(),
            scope=TemplateLevel.firm_default.value,
            project_id=None, group_id=None, current_user=_fake_user(),
        )
        session = mod.load_session_manifest(out.session_id)
        entries = read_sheet_entries(session.working_path)
        assert len(entries) == _K11_BASELINE["sheets"]
        assert not [e.name for e in entries if not e.is_visible]

    async def test_session_manifest_survives_process_boundary(
        self, sandbox, forensic_template
    ):
        """🔴 会话元数据必须落盘，不能只在进程内。

        OO 的 callback 是另一个请求，多 worker 下可能落到别的进程 —— 进程内字典会随机
        丢失，表现为"保存时报会话不存在"。这条判据用「重新从磁盘加载」证明它不依赖内存。
        """
        from app.routers import wp_template_override_router as api
        from app.services import wp_template_override as mod

        _mod, _root = sandbox
        out = await api.create_edit_session(
            _FORENSIC_WP_CODE, _fake_request(),
            scope=TemplateLevel.firm_default.value,
            project_id=None, group_id=None, current_user=_fake_user(),
        )
        reloaded = mod.load_session_manifest(out.session_id)
        assert reloaded.wp_code == _FORENSIC_WP_CODE
        assert reloaded.authoritative_path == forensic_template
        assert reloaded.source_workbook_xml is not None
        assert reloaded.working_path.is_file()

        # 会话不存在时必须**抛**而不是当作新会话（否则保存会落到错误的 wp_code）
        with pytest.raises(mod.TemplateOverrideError):
            mod.load_session_manifest("no-such-session")

    async def test_docx_is_rejected_for_in_browser_edit(self, sandbox):
        """在线编辑入口只放 xlsx；docx 必须被拒并给出 error_code（Requirement 5.2）。"""
        from fastapi import HTTPException

        from app.routers import wp_template_override_router as api
        from app.services.wp_template_finder import find_template_file_any_unresolved

        # 找一个真实的 docx wp_code。用 `_any` 口径 —— `find_template_file` 只认
        # xlsx/xlsm，拿它找 docx 永远找不到，这条判据会永久 skip（即形同不存在）。
        docx_code = None
        for candidate in ("B2-1", "B2-6", "B2-8", "B2-11", "B18-3-1", "B40-1"):
            p = find_template_file_any_unresolved(candidate)
            if p is not None and p.suffix.lower() == ".docx":
                docx_code = candidate
                break
        if docx_code is None:
            pytest.skip("找不到解析为 docx 的 wp_code")

        with pytest.raises(HTTPException) as exc:
            await api.create_edit_session(
                docx_code, _fake_request(),
                scope=TemplateLevel.firm_default.value,
                project_id=None, group_id=None, current_user=_fake_user(),
            )
        assert exc.value.status_code == 400
        assert exc.value.detail["error_code"] == "template_override_format_not_editable"


class TestRouterIsRegistered:
    """端点必须真的挂上 —— 否则整个 router 是死代码（假绿第①源）。"""

    def test_eight_endpoints_are_registered_by_the_registry(self):
        from fastapi import FastAPI

        from app.router_registry.workpaper import register_workpaper_routers

        app = FastAPI()
        register_workpaper_routers(app)
        paths = {getattr(r, "path", "") for r in app.routes}
        mine = sorted(p for p in paths if p.startswith("/api/wp-template-overrides"))
        assert len(mine) == 8, f"模板覆盖层端点注册了 {len(mine)} 条，期望 8：{mine}"

        # 只加不动：既有的模板管理端点仍在（分组里原有 8 个 router）
        template_ish = [p for p in paths if "template" in p.lower()]
        assert len(template_ish) > len(mine), (
            "除我的 8 条外没有别的 template 端点 —— 注册可能挤掉了既有 router"
        )

    def test_machine_to_machine_endpoints_do_not_require_bearer(self):
        """`contents` / `callback` 由 DocServer 直连，**不得**声明 `get_current_user`。

        声明了会恒 401 —— 文档下载与保存全失败，且失败点在 OO 内部、很难查。
        判据落在函数签名（真实依赖声明），不是注释。
        """
        import inspect

        from app.deps import get_current_user, require_role
        from app.routers import wp_template_override_router as api

        for fn in (api.get_session_contents, api.session_callback):
            params = inspect.signature(fn).parameters
            for name, param in params.items():
                default = param.default
                dep = getattr(default, "dependency", None)
                assert dep is not get_current_user, (
                    f"{fn.__name__} 的参数 {name} 依赖 get_current_user —— 机对机端点会恒 401"
                )
                # require_role 返回闭包，按 qualname 识别
                if dep is not None:
                    assert "require_role" not in getattr(dep, "__qualname__", ""), (
                        f"{fn.__name__} 的参数 {name} 依赖 require_role"
                    )
        # 反面：管理端点**必须**有权限依赖，否则任何人都能改模板
        for fn in (api.create_edit_session, api.upload_replacement,
                   api.promote_version, api.delete_current_override):
            deps = [
                getattr(p.default, "dependency", None)
                for p in inspect.signature(fn).parameters.values()
            ]
            qualnames = [getattr(d, "__qualname__", "") for d in deps if d is not None]
            assert any("require_role" in q for q in qualnames), (
                f"{fn.__name__} 没有角色门 —— 模板覆盖是事务所级操作，不能裸奔"
            )


# ═══════════════════════════════════════════════════════════════════════════
# Task 103 —— OnlyOffice 处理 xlsm 是否保留 vbaProject.bin（Gate 3 的取证）
# Requirements: 5.2
# ═══════════════════════════════════════════════════════════════════════════
#
# Gate 3 当前的裁决是**保守排除 xlsm**，理由是「17/17 份含 `vbaProject.bin` 而 OO 保留性
# 未取证」。这一节把「未取证」变成「已取到一半」：
#
# * **已取证**：OO 的 `ConvertService.ashx` 做 xlsm → xlsm 往返后，`vbaProject.bin`
#   **逐字节保留**，zip 部件数与 `printerSettings` 也不变（实测样本
#   `B30-2B 组成部分重要性水平（2021年6月）.xlsm`：parts 30→30、vba 52224→52224 同 sha、
#   printerSettings 2→2）。
# * **仍未取证**：编辑保存路径（浏览器打开 DocEditor → forcesave → callback）。它与
#   conversion **不是同一条代码路径**，而 OO 只在有浏览器 session 时才建立 document
#   session ⇒ 无法在纯后端测试里驱动。
#
# ⇒ **不放开 xlsm**。这条判据的作用是**锁住已知的那一半**：若某次 OO 升级让
#   conversion 开始丢 VBA，它会立刻打红 —— 那时连"待取证"都不必再谈，直接永久排除。

_VBA_PART = "xl/vbaProject.bin"
_OO_BASE = "http://127.0.0.1:8080"
_PROBE_PORT = 18098


def _oo_reachable() -> bool:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{_OO_BASE}/healthcheck", timeout=6) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _xlsm_metrics(data: bytes) -> dict:
    import hashlib
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        vba = zf.read(_VBA_PART) if _VBA_PART in names else b""
        return {
            "parts": len(names),
            "has_vba": _VBA_PART in names,
            "vba_size": len(vba),
            "vba_sha256": hashlib.sha256(vba).hexdigest() if vba else None,
            "printer_settings": sum(1 for n in names if "printerSettings" in n),
        }


class TestTask103XlsmVbaSurvivesConversion:
    """OO conversion 不丢 VBA —— Gate 3 已取证的那一半。"""

    def test_all_xlsm_templates_still_carry_vba(self):
        """Gate 3 的分母：索引声明的 17 份 xlsm **全部**含 `vbaProject.bin`。

        这个 17/17 是「保守排除」的全部理由。若某天有一份不含宏了，排除的口径就该复核。
        """
        xlsm = sorted(_TEMPLATES_DIR.rglob("*.xlsm"))
        assert len(xlsm) == 17, f"xlsm 份数 {len(xlsm)} != 17 —— Gate 3 的分母变了"
        without_vba = []
        for path in xlsm:
            with zipfile.ZipFile(str(path)) as zf:
                if _VBA_PART not in zf.namelist():
                    without_vba.append(path.name)
        assert not without_vba, (
            f"这些 xlsm 不含 vbaProject.bin：{without_vba} —— "
            "「17/17 全含宏」不再成立，Gate 3 的排除理由需复核"
        )

    def test_conversion_roundtrip_preserves_vba_bytes(self):
        """真跑一次 OO conversion 往返，`vbaProject.bin` 必须逐字节不变。

        依赖 `audit-onlyoffice` 容器可达；不可达则 skip（CI 主 job 会 skip）。
        """
        import http.server
        import json
        import socketserver
        import threading
        import time
        import urllib.request

        if not _oo_reachable():
            pytest.skip(f"OnlyOffice 不可达（{_OO_BASE}/healthcheck）")

        # 挑最小的一份含宏 xlsm，减少传输时间
        sample = None
        for path in sorted(_TEMPLATES_DIR.rglob("*.xlsm"), key=lambda p: p.stat().st_size):
            with zipfile.ZipFile(str(path)) as zf:
                if _VBA_PART in zf.namelist():
                    sample = path
                    break
        if sample is None:
            pytest.skip("没有含 vbaProject.bin 的 xlsm")

        before = _xlsm_metrics(sample.read_bytes())
        assert before["has_vba"] and before["vba_size"] > 0

        payload_bytes = sample.read_bytes()

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/vnd.ms-excel.sheet.macroEnabled.12"
                )
                self.send_header("Content-Length", str(len(payload_bytes)))
                self.end_headers()
                self.wfile.write(payload_bytes)

            def log_message(self, *args):
                pass

        httpd = socketserver.TCPServer(("0.0.0.0", _PROBE_PORT), _Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            from app.core.config import settings

            request_payload = {
                "async": False,
                "filetype": "xlsm",
                "outputtype": "xlsm",
                "key": f"task103-guard-{int(time.time())}",
                "title": sample.name,
                # OO 在容器里，宿主用 host.docker.internal 可达（Docker Desktop）
                "url": f"http://host.docker.internal:{_PROBE_PORT}/{sample.name}",
            }
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if settings.ONLYOFFICE_JWT_SECRET:
                from jose import jwt

                request_payload["token"] = jwt.encode(
                    request_payload, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256"
                )
                headers["Authorization"] = "Bearer " + jwt.encode(
                    {"payload": request_payload},
                    settings.ONLYOFFICE_JWT_SECRET,
                    algorithm="HS256",
                )

            req = urllib.request.Request(
                f"{_OO_BASE}/ConvertService.ashx",
                data=json.dumps(request_payload).encode("utf-8"),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    result = json.loads(resp.read().decode("utf-8", "replace"))
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"ConvertService 不可用：{type(exc).__name__}: {exc}")

            if result.get("error"):
                pytest.skip(
                    f"OO 转换报错 error={result['error']}"
                    "（-4=下载失败 -3=转换错误 -8=token 无效）"
                )
            out_url = result.get("fileUrl")
            assert out_url, f"响应没有 fileUrl：{result}"

            fetch_url = out_url.replace("http://localhost/", f"{_OO_BASE}/")
            with urllib.request.urlopen(fetch_url, timeout=180) as resp:
                converted = resp.read()
        finally:
            httpd.shutdown()

        after = _xlsm_metrics(converted)

        assert after["has_vba"], (
            "🔴 OO conversion **丢弃**了 vbaProject.bin ⇒ Gate 3 的保守排除可升级为"
            "「已证否」，xlsm 应永久排除（并把本判据改成断言「丢弃」）"
        )
        assert after["vba_sha256"] == before["vba_sha256"], (
            f"vbaProject.bin 字节被改写：{before['vba_sha256'][:16]} → "
            f"{after['vba_sha256'][:16]}。宏也许仍能跑，但对模板库应视为有损。"
        )
        assert after["parts"] == before["parts"], (
            f"zip 部件数变了：{before['parts']} → {after['parts']}"
        )
        assert after["printer_settings"] == before["printer_settings"]

    def test_xlsm_is_still_excluded_from_editable_formats(self):
        """🔴 即便 conversion 保留了 VBA，`EDITABLE_FORMATS` **仍**不含 xlsm。

        这条不是多余：上一条判据一绿，下一个读它的人很容易顺手把 xlsm 加进可编辑集合。
        conversion 与编辑保存不是同一条路径，放开的前置条件是**编辑路径**取证
        （浏览器打开 DocEditor → forcesave → 比对 VBA），那条还没做。
        """
        from app.services.wp_template_override import EDITABLE_FORMATS

        assert ".xlsm" not in EDITABLE_FORMATS, (
            "xlsm 被放进 EDITABLE_FORMATS 了 —— 若编辑路径已取证，请同时把本判据改掉"
            "并在 tasks.md Task 103 记录证据；否则回退"
        )
        assert EDITABLE_FORMATS == frozenset({".xlsx"})


# ═══════════════════════════════════════════════════════════════════════════
# Property 20 —— 打印设置（pageSetup）业务属性等价
#
# 背景（Task 103 取证）：OO **编辑往返**会丢掉 `printerSettings*.bin`
# （K11 实测 7 → 0，worksheets/_rels 7 → 1，pageSetup 的 `r:id` 7 → 0），而 OO
# **ConvertService** 不丢（37→37 部件、printerSettings 7→7、r:id 7→7）。
# ⇒ 丢弃发生在 DocEditor 的保存路径，不是转换内核。
#
# 丢的那个 .bin 是 DEVMODE —— 绑定到模板作者当年那台打印机的驱动私有结构。
# 换一台机器打开 Excel 本来就会 fallback 到本机默认打印机。**业务语义**（纸张、
# 缩放、方向、页边距、页码起始…）在 OOXML 里存的是 `<pageSetup>` 的属性，OO
# 把它们完整内联保留了。
#
# 🔴 所以本节判据锁的是「业务属性等价」，**不是**「printerSettings 部件数不变」。
# 后者会把一条良性行为锁成永久红灯，逼后人去做「给 pageSetup 加回 r:id + 重建
# rels」这种内容级改写 —— 风险远大于收益（详见 tasks.md Task 103 的裁决）。
# ═══════════════════════════════════════════════════════════════════════════

_PAGE_SETUP_SUB_RE = re.compile(r"<pageSetup\b([^>]*?)/?>")


def _tamper_page_setup(data: bytes, part: str, attr: str, value: str) -> bytes:
    """把某个 sheet 的 `pageSetup` 某属性改成 `value`（属性不存在则插入）。

    只重写目标部件，其余部件连 `ZipInfo` 原样搬 —— 保证除该属性外没有别的变量。
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as src, \
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        seen = False
        for item in src.infolist():
            payload = src.read(item.filename)
            if item.filename == part:
                text = payload.decode("utf-8")

                def _sub(m: "re.Match[str]") -> str:
                    inner = m.group(1)
                    if f'{attr}="' in inner:
                        inner = re.sub(rf'{attr}="[^"]*"', f'{attr}="{value}"', inner)
                    else:
                        inner = f' {attr}="{value}"' + inner
                    return f"<pageSetup{inner}/>"

                text, n = _PAGE_SETUP_SUB_RE.subn(_sub, text, count=1)
                assert n == 1, f"{part} 里没找到 <pageSetup> —— 篡改没生效，判据会假绿"
                seen = True
                payload = text.encode("utf-8")
            dst.writestr(item, payload)
        assert seen, f"zip 里没有部件 {part}"
    return buf.getvalue()


def _first_sheet_with_page_setup(path: Path) -> str:
    from app.services.wp_template_override import read_page_setup_attributes

    attrs = read_page_setup_attributes(path.read_bytes())
    for part, values in sorted(attrs.items()):
        if values:
            return part
    pytest.skip(f"{path.name} 没有任何 <pageSetup>，无法做本节判据")


class TestProperty20PageSetupDiffIsSound:
    """`diff_page_setup` 本身站得住 —— 先立可信度，再拿它下结论。"""

    def test_device_bound_attrs_are_excluded_from_comparison(self):
        """设备绑定属性**不参与**比对，且两个集合不相交。

        这是 14 项良性差异不被误报的唯一原因。若 `horizontalDpi` 哪天被加进
        `PAGE_SETUP_MEANINGFUL_ATTRS`，OO 每次保存都会报 14 项「变化」。
        """
        from app.services.wp_template_override import (
            PAGE_SETUP_DEVICE_BOUND_ATTRS,
            PAGE_SETUP_MEANINGFUL_ATTRS,
        )

        overlap = set(PAGE_SETUP_MEANINGFUL_ATTRS) & set(PAGE_SETUP_DEVICE_BOUND_ATTRS)
        assert not overlap, (
            f"这些属性同时在「有业务意义」和「设备绑定」两个集合里：{sorted(overlap)}"
            " —— 语义冲突，比对结果取决于代码里先判哪个"
        )
        for attr in ("r:id", "horizontalDpi", "verticalDpi"):
            assert attr in PAGE_SETUP_DEVICE_BOUND_ATTRS, (
                f"{attr} 不在设备绑定集合里 —— OO 往返会因它报假差异"
            )
        for attr in ("paperSize", "scale", "orientation"):
            assert attr in PAGE_SETUP_MEANINGFUL_ATTRS, (
                f"{attr} 是审计师肉眼可见的打印语义，必须参与比对"
            )

    def test_omitted_attribute_equals_explicit_default(self, forensic_template):
        """省略 ↔ 显式写默认值，视为等价。

        OO 的行为就是把 Excel 省略的属性显式写出来。不归一 ⇒ 每次保存都报一堆
        「从空变成 100」的假差异。
        """
        from app.services.wp_template_override import (
            PAGE_SETUP_DEFAULTS,
            diff_page_setup,
            read_page_setup_attributes,
        )

        original = forensic_template.read_bytes()
        attrs = read_page_setup_attributes(original)
        target = next(
            (p for p, v in sorted(attrs.items()) if v and "scale" not in v), None
        )
        if target is None:
            pytest.skip("K11 每个 sheet 都显式写了 scale，无法检验省略侧")

        explicit = _tamper_page_setup(
            original, target, "scale", PAGE_SETUP_DEFAULTS["scale"]
        )
        assert diff_page_setup(original, explicit) == (), (
            f"给原本省略 scale 的 {target} 显式写 scale="
            f"{PAGE_SETUP_DEFAULTS['scale']} 却报出差异 —— 默认值归一没生效"
        )

    def test_orientation_default_equals_portrait(self, forensic_template):
        """`orientation="default"` ↔ `"portrait"` 等价（Excel 语义）。"""
        from app.services.wp_template_override import diff_page_setup

        original = forensic_template.read_bytes()
        part = _first_sheet_with_page_setup(forensic_template)
        as_default = _tamper_page_setup(original, part, "orientation", "default")
        as_portrait = _tamper_page_setup(original, part, "orientation", "portrait")
        assert diff_page_setup(as_default, as_portrait) == (), (
            "default 与 portrait 被判成不同 —— 会对某些模板恒报一条假差异"
        )

    @pytest.mark.parametrize(
        ("attr", "value"),
        [
            ("scale", "42"),
            ("orientation", "landscape"),
            ("paperSize", "1"),
            ("fitToWidth", "3"),
            ("firstPageNumber", "7"),
        ],
    )
    def test_real_change_is_detected(self, forensic_template, attr, value):
        """反向自检：真改一处业务属性**必须**被抓到。

        🔴 没有这条，上面三条「等价」判据可以靠 `return ()` 全绿（假绿第②源）。
        """
        from app.services.wp_template_override import diff_page_setup

        original = forensic_template.read_bytes()
        part = _first_sheet_with_page_setup(forensic_template)
        tampered = _tamper_page_setup(original, part, attr, value)

        changes = diff_page_setup(original, tampered)
        hits = [c for c in changes if c.attribute == attr and c.sheet_part == part]
        assert hits, (
            f"把 {part} 的 {attr} 改成 {value} 却没被 diff_page_setup 抓到。"
            f"实得差异：{[c.as_dict() for c in changes]}"
        )
        assert hits[0].after == value

    def test_missing_sheet_is_reported(self, forensic_template):
        """sheet 部件消失要报出来，而不是「交集为空所以等价」。"""
        from app.services.wp_template_override import diff_page_setup

        original = forensic_template.read_bytes()
        part = _first_sheet_with_page_setup(forensic_template)

        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as src, \
                zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename == part:
                    continue
                dst.writestr(item, src.read(item.filename))

        changes = diff_page_setup(original, buf.getvalue())
        assert any(c.sheet_part == part and c.attribute == "<sheet>" for c in changes), (
            f"删掉部件 {part} 后没有任何差异被报出 —— 少一个 sheet 是重大损失，"
            f"不能因为两侧只比交集而静默。实得：{[c.as_dict() for c in changes]}"
        )


class TestProperty20SaveWiresPageSetupDiff:
    """差异必须真的挂到保存结果上 —— 否则 `diff_page_setup` 是死代码（假绿第①源）。"""

    def test_untouched_save_reports_no_page_setup_change(self, sandbox, forensic_template):
        """空保存（不改任何内容）⇒ 打印设置零差异。"""
        mod, _root = sandbox
        session = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="ps-clean"
        )
        staged = mod.commit_template_edit_session(session, version_id="ps-clean-v1")
        assert staged.page_setup_changes == (), (
            "什么都没改却报出打印设置变化："
            f"{[c.as_dict() for c in staged.page_setup_changes]}"
        )

    def test_page_setup_change_in_working_copy_reaches_staged_result(
        self, sandbox, forensic_template
    ):
        """🔴 接线判据：改工作副本的 `pageSetup` ⇒ `staged.page_setup_changes` 必须出现。

        这条是本节的核心。前面几条只证明 `diff_page_setup` 函数本身对，
        **这条**才证明它被 `commit_template_edit_session` 真的调用了。
        把 commit 里那次调用删掉，只有这条会红。
        """
        mod, _root = sandbox
        session = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="ps-dirty"
        )
        part = _first_sheet_with_page_setup(session.working_path)
        session.working_path.write_bytes(
            _tamper_page_setup(session.working_path.read_bytes(), part, "scale", "77")
        )

        staged = mod.commit_template_edit_session(session, version_id="ps-dirty-v1")
        hits = [c for c in staged.page_setup_changes if c.attribute == "scale"]
        assert hits, (
            "工作副本的 scale 已改成 77，但保存结果里没有对应的 page_setup_changes"
            " —— diff_page_setup 没被 commit_template_edit_session 调用，或结果被丢弃。"
            f"实得：{[c.as_dict() for c in staged.page_setup_changes]}"
        )
        assert hits[0].after == "77"

    def test_baseline_is_edit_start_not_authoritative(self, sandbox, forensic_template):
        """比对基线是**编辑起点**，不是权威文件。

        否则第二次编辑会把第一次的合法改动重复报一遍：用户改了纸张方向并保存，
        下次打开什么都不动再保存，又收到同一条「变化」。
        """
        mod, _root = sandbox

        # 第一次：真改一处并保存 + 生效（造出一层覆盖）
        s1 = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="ps-gen1"
        )
        part = _first_sheet_with_page_setup(s1.working_path)
        s1.working_path.write_bytes(
            _tamper_page_setup(s1.working_path.read_bytes(), part, "scale", "55")
        )
        staged1 = mod.commit_template_edit_session(s1, version_id="ps-gen1-v1")
        assert [
            c.after for c in staged1.page_setup_changes if c.attribute == "scale"
        ] == ["55"]
        mod.activate_staged_override(staged1)

        # 第二次：从覆盖层起点开门，什么都不改
        s2 = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="ps-gen2"
        )
        assert s2.source_origin != "authoritative", (
            "第二次会话没解析到刚生效的覆盖 —— 前置条件不成立，本判据无意义"
        )
        staged2 = mod.commit_template_edit_session(s2, version_id="ps-gen2-v1")
        assert staged2.page_setup_changes == (), (
            "第二次空保存又报出打印设置变化 ⇒ 基线用的是权威文件而不是编辑起点。"
            f"实得：{[c.as_dict() for c in staged2.page_setup_changes]}"
        )

    def test_comparison_failure_is_not_silently_empty(
        self, sandbox, forensic_template, monkeypatch
    ):
        """比对抛错时**不**降级成空 tuple（fail-open 会让「没跑」和「通过」长得一样）。"""
        mod, _root = sandbox
        session = mod.prepare_template_edit_session(
            _FORENSIC_WP_CODE, TemplateLevel.firm_default, session_id="ps-boom"
        )

        def _boom(*_a, **_kw):
            raise zipfile.BadZipFile("injected")

        monkeypatch.setattr(mod, "diff_page_setup", _boom)
        staged = mod.commit_template_edit_session(session, version_id="ps-boom-v1")

        assert staged.page_setup_changes, (
            "比对抛错却返回空 page_setup_changes —— 调用方无法区分「等价」与「没比对」"
        )
        assert any("BadZipFile" in c.attribute for c in staged.page_setup_changes), (
            f"错误没被显性记录：{[c.as_dict() for c in staged.page_setup_changes]}"
        )
        # 保存本身不受影响 —— 比对是观测手段，不是门
        assert staged.staged_path.is_file()


class TestProperty20RouterExposesPageSetupChanges:
    """结果要能到前端 —— 只挂到服务层对象上但不出响应体，等于没接。"""

    def test_save_result_schema_has_page_setup_changes(self):
        from app.routers.wp_template_override_router import (
            PageSetupChangeOut,
            SaveResultOut,
        )

        assert "page_setup_changes" in SaveResultOut.model_fields, (
            "SaveResultOut 没有 page_setup_changes —— 差异到不了前端"
        )
        for field in ("sheet_part", "attribute", "before", "after"):
            assert field in PageSetupChangeOut.model_fields, (
                f"PageSetupChangeOut 缺 {field} —— 前端无法定位是哪张 sheet 的哪个属性"
            )

    def test_page_setup_change_as_dict_matches_router_schema(self):
        """服务层 `as_dict()` 的键与 router 的字段**逐项**对齐。

        对不上时 `PageSetupChangeOut(**c.as_dict())` 会在运行时 TypeError，
        而那行只在真有差异时才执行 ⇒ 平时全绿，用户改了纸张方向才 500。
        """
        from app.routers.wp_template_override_router import PageSetupChangeOut
        from app.services.wp_template_override import PageSetupChange

        sample = PageSetupChange("xl/worksheets/sheet1.xml", "scale", "100", "77")
        assert set(sample.as_dict()) == set(PageSetupChangeOut.model_fields)
        assert PageSetupChangeOut(**sample.as_dict()).attribute == "scale"


class TestProperty20OnlyOfficeConversionPreservesPageSetup:
    """真跑一次 OO ConvertService，打印设置业务属性必须等价（OO 不可达则 skip）。"""

    def test_conversion_roundtrip_keeps_page_setup_semantics(self, forensic_template):
        import http.server
        import json
        import socketserver
        import threading
        import time
        import urllib.request

        from app.services.wp_template_override import (
            diff_page_setup,
            read_page_setup_attributes,
        )

        if not _oo_reachable():
            pytest.skip(f"OnlyOffice 不可达（{_OO_BASE}/healthcheck）")

        payload_bytes = forensic_template.read_bytes()

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet",
                )
                self.send_header("Content-Length", str(len(payload_bytes)))
                self.end_headers()
                self.wfile.write(payload_bytes)

            def log_message(self, *args):
                pass

        httpd = socketserver.TCPServer(("0.0.0.0", _PROBE_PORT), _Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            from app.core.config import settings

            request_payload = {
                "async": False,
                "filetype": "xlsx",
                "outputtype": "xlsx",
                "key": f"prop20-{int(time.time())}",
                "title": forensic_template.name,
                "url": f"http://host.docker.internal:{_PROBE_PORT}/"
                       f"{forensic_template.name}",
            }
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if settings.ONLYOFFICE_JWT_SECRET:
                from jose import jwt

                request_payload["token"] = jwt.encode(
                    request_payload, settings.ONLYOFFICE_JWT_SECRET, algorithm="HS256"
                )
                headers["Authorization"] = "Bearer " + jwt.encode(
                    {"payload": request_payload},
                    settings.ONLYOFFICE_JWT_SECRET,
                    algorithm="HS256",
                )

            req = urllib.request.Request(
                f"{_OO_BASE}/ConvertService.ashx",
                data=json.dumps(request_payload).encode("utf-8"),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    result = json.loads(resp.read().decode("utf-8", "replace"))
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"ConvertService 不可用：{type(exc).__name__}: {exc}")
            if result.get("error"):
                pytest.skip(f"OO 转换报错 error={result['error']}")
            out_url = result.get("fileUrl")
            assert out_url, f"响应没有 fileUrl：{result}"
            with urllib.request.urlopen(
                out_url.replace("http://localhost/", f"{_OO_BASE}/"), timeout=180
            ) as resp:
                converted = resp.read()
        finally:
            httpd.shutdown()

        # 分母 1：源模板真的有 pageSetup，否则下面的等价断言在空集上恒真
        source_attrs = read_page_setup_attributes(payload_bytes)
        assert sum(1 for v in source_attrs.values() if v) >= 2, (
            f"源模板 pageSetup 元素太少（{source_attrs}）—— 等价断言没有意义"
        )

        # 分母 2：OO 真的重写了文件。少了这条，任何一层缓存/代理把原字节回吐都会
        # 让"等价"恒真 —— 那就变成"没跑"和"通过"长得一样（fail-open 的变体）。
        assert converted != payload_bytes, (
            "ConvertService 返回的字节与输入**完全相同** —— 转换没真发生"
            "（缓存命中？），本判据此时不成立"
        )
        with zipfile.ZipFile(io.BytesIO(converted)) as zf:
            out_sheets = sum(
                1 for n in zf.namelist()
                if n.startswith("xl/worksheets/") and n.endswith(".xml")
            )
        assert out_sheets == _K11_BASELINE["sheets"], (
            f"转换结果 sheet 数 {out_sheets} != 基线 {_K11_BASELINE['sheets']}"
            " —— 拿回来的不是同一本工作簿"
        )

        changes = diff_page_setup(payload_bytes, converted)
        assert changes == (), (
            "OO ConvertService 改动了 pageSetup 的业务属性：\n"
            + "\n".join(
                f"  {c.sheet_part} {c.attribute}: {c.before!r} → {c.after!r}"
                for c in changes
            )
            + "\n实测基线是 0 项。非空说明 OO 版本行为变了，需复核打印设置是否仍可用。"
        )


class TestProperty20UploadPathAlsoDiffs:
    """上传替换路径同样要比对 —— 人手改过的文件比 OO 往返更可能悄悄改了纸张方向。"""

    def test_upload_path_calls_attach_page_setup_changes(self):
        """🔴 接线判据（AST）：`upload_replacement` 函数体里真的调了 `attach_page_setup_changes`。

        不用 grep 整文件 —— 那样把函数删了、只在注释里留个名字也能绿。
        这里定位到**那个函数的 AST 子树**再找调用。
        """
        source = (
            _BACKEND_DIR / "app" / "routers" / "wp_template_override_router.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        target = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name == "upload_replacement"
            ):
                target = node
                break
        assert target is not None, "router 里找不到 upload_replacement"

        calls = {
            ast.unparse(n.func)
            for n in ast.walk(target)
            if isinstance(n, ast.Call)
        }
        assert any("attach_page_setup_changes" in c for c in calls), (
            "upload_replacement 没调 attach_page_setup_changes ⇒ 上传替换不比对打印设置，"
            f"而 SaveResultOut.page_setup_changes 在这条路径上恒空。实得调用：{sorted(calls)}"
        )

    def test_upload_baseline_is_read_before_staging(self):
        """基线必须在 `stage_override` **之前**读。

        落盘后 `current` 已被换掉，再读就是拿新的比新的 ⇒ 差异恒空（假绿）。
        用行号先后判断：读基线的那行必须早于 stage_override 那行。
        """
        source = (
            _BACKEND_DIR / "app" / "routers" / "wp_template_override_router.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "upload_replacement"
        )

        baseline_line = stage_line = None
        for node in ast.walk(target):
            if not isinstance(node, ast.Call):
                continue
            rendered = ast.unparse(node.func)
            if "resolve_template_any" in rendered and baseline_line is None:
                baseline_line = node.lineno
            if "stage_override" in rendered and stage_line is None:
                stage_line = node.lineno

        assert baseline_line is not None, (
            "upload_replacement 里没有 resolve_template_any 调用 —— 没取比对基线"
        )
        assert stage_line is not None, "upload_replacement 里没有 stage_override 调用"
        assert baseline_line < stage_line, (
            f"基线在第 {baseline_line} 行读、stage_override 在第 {stage_line} 行 —— "
            "顺序反了会拿替换后的文件当基线，差异恒空"
        )


class TestProperty20FrontendLabelsCoverBackendAttrs:
    """前端的属性中文表必须覆盖后端全部比对项（双份声明 ⇒ 必须有判据锁）。"""

    def test_every_meaningful_attr_has_a_chinese_label(self):
        """漏一项 ⇒ UI 上显示英文属性名，违反「UI 全中文化」。"""
        from app.services.wp_template_override import PAGE_SETUP_MEANINGFUL_ATTRS

        vue = (
            _REPO_ROOT / "audit-platform" / "frontend" / "src" / "components"
            / "template-library" / "WpTemplateDetail.vue"
        ).read_text(encoding="utf-8")

        start = vue.find("const PAGE_SETUP_LABELS")
        assert start != -1, "WpTemplateDetail.vue 里找不到 PAGE_SETUP_LABELS"
        end = vue.find("}", vue.find("{", start))
        block = vue[start:end]

        missing = [a for a in PAGE_SETUP_MEANINGFUL_ATTRS if f"{a}:" not in block]
        assert not missing, (
            f"这些属性在前端没有中文标签：{missing} —— 真出差异时 UI 会显示英文属性名。"
            "后端新增比对项时必须同步这张表"
        )
