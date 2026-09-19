# -*- coding: utf-8 -*-
"""Task 12 守卫：统一 canonical resolver、immutable definition/bundle store、
candidate 隔离与 writer/resolver 迁移矩阵（不连库部分）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 12
Requirements: 2.3, 2.10, 6.2, 6.10, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.11, 9.12
Properties: P7 / P28 / P39 / P40 / P41 / P42

═══ 判据落在哪 ═══

* **P42 路径安全** —— 真建目录/软链接后跑 `resolve_within_root`，断言 realpath 之后
  仍在 root 内；并断言 `artifacts.py` 与 `wp_file_resolver.py` 共用**同一份**实现
  （单一真源，改一处两边都红）。
* **P40 子码最具体** —— 真在 tmp 目录建「父级 XLSX + 子码 DOCX」两个文件，断言
  `pick_most_specific` 对子码返回 DOCX；并断言 `is_sub_code` 判据与字母类无关。
* **P41 缺失不异类型回退** —— 只有父级 XLSX 时必须抛
  `DocumentTypeMismatchError`（**不是** `TemplateMissingError`），两类异常不可合并。
* **P28 definition 漂移 fail closed** —— bundle canonicalizer 的 14 条反例逐条断言，
  且每条的**异常消息**要能定位到首个失败 slot。
* **P39 config/callback 同源** —— 结构判据：十个意图共用唯一入口
  `CanonicalResolutionService.resolve`，且 `ResolutionIntent` 是封闭枚举、
  historical 四意图强制 frozen identity。
* **P7 全链统一** —— 同 (content version, entry, generation) 下十意图返回值除
  `intent` 外逐字段相等，由 `test_task12_resolution_pg.py` 用真库断言；本文件只锁
  「策略表覆盖全部意图 + 无第二个解析入口」的结构面。

═══ 反向自检 ═══

`TestGuardSelfCheck` 用替身复现旧行为（裸 `.exists()`、A-only 子码正则、marker 冒充
contract），证明判据不是空转。
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import canonical_paths as CP  # noqa: E402
from app.services.workpaper_sync import definitions as D  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
)
from app.services.workpaper_sync.resolution import (  # noqa: E402
    INTENT_POLICY,
    CanonicalResolutionService,
    ResolutionIntent,
    SheetVisibilityForbiddenError,
)

_ARTIFACTS_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "artifacts.py"
_RESOLUTION_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "resolution.py"
_CANONICAL_PATHS_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "canonical_paths.py"
_LEGACY_RESOLVER_PY = _BACKEND / "app" / "services" / "wp_export" / "wp_file_resolver.py"
_WOPI_PY = _BACKEND / "app" / "services" / "wopi_service.py"
_STORAGE_PY = _BACKEND / "app" / "services" / "wp_storage_service.py"
_MATRIX_JSON = _BACKEND / "data" / "workpaper_resolver_migration_matrix.json"

# 双哨兵：单哨兵会被历史空目录骗停
assert (_BACKEND / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert (_BACKEND / "wp_templates").is_dir(), "哨兵失效：backend/wp_templates 不存在"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _read(path: Path) -> str:
    assert path.is_file(), f"文件不存在: {path}"
    return path.read_text(encoding="utf-8")


def _stripped(path: Path) -> str:
    """剥注释/docstring 后的源码（防「说明文字里的反例」被数成真实代码）。"""
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        strip_comments_and_docstrings,
    )

    return strip_comments_and_docstrings(_read(path))


def _func_src(src: str, qualname: str) -> str:
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        function_source,
    )

    return function_source(src, qualname)


# ═══════════════════════════════════════════════════════════════════════════
# Property 42：路径安全
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty42PathBoundary:
    """目录穿越 / 项目外绝对路径 / 软链接越界 / 跨 root 复用全部被拒。"""

    def test_traversal_rejected(self, tmp_path: Path):
        root = tmp_path / "root"
        (root / "inner").mkdir(parents=True)
        with pytest.raises(CP.PathBoundaryError) as ei:
            CP.resolve_within_root(root, "../outside.xlsx", boundary="project_root")
        assert ei.value.reason == "outside_project_root"

    def test_absolute_outside_root_rejected(self, tmp_path: Path):
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "elsewhere" / "x.xlsx"
        outside.parent.mkdir()
        outside.write_bytes(b"x")
        with pytest.raises(CP.PathBoundaryError):
            CP.resolve_within_root(root, str(outside), boundary="project_root")

    def test_empty_relative_rejected(self, tmp_path: Path):
        """🔴 空串必须在构造 Path 之前拒绝：`Path('')` 归一成 `.`，`.exists()` 为 True。"""
        assert Path("").exists() is True, "Python 语义变了，本守卫的根因分析需重做"
        with pytest.raises(CP.PathBoundaryError) as ei:
            CP.resolve_within_root(tmp_path, "   ", boundary="project_root")
        assert ei.value.reason == "empty_relative_path"

    def test_symlink_escape_rejected(self, tmp_path: Path):
        """软链接越界：只做字符串前缀比较拦不住，必须 realpath 之后再判。"""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.xlsx").write_bytes(b"s")
        link = root / "link"
        try:
            os.symlink(str(outside), str(link), target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError) as exc:
            pytest.skip(f"本机不允许创建软链接（需管理员/开发者模式）: {exc}")
        # 字符串前缀判据会放行（link 在 root 下），realpath 判据必须拒绝
        assert str(link / "secret.xlsx").startswith(str(root))
        with pytest.raises(CP.PathBoundaryError):
            CP.resolve_within_root(root, "link/secret.xlsx", boundary="project_root")

    def test_cross_root_reuse_rejected(self, tmp_path: Path):
        a, b = tmp_path / "a", tmp_path / "b"
        (a / "wp").mkdir(parents=True)
        (b / "wp").mkdir(parents=True)
        target = a / "wp" / "x.xlsx"
        target.write_bytes(b"x")
        CP.assert_within_root(a, target, boundary="project_root")
        with pytest.raises(CP.PathBoundaryError):
            CP.assert_within_root(b, target, boundary="project_root")

    def test_inside_root_accepted(self, tmp_path: Path):
        root = tmp_path / "root"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "ok.xlsx").write_bytes(b"o")
        got = CP.resolve_within_root(root, "sub/ok.xlsx", boundary="project_root")
        assert got == Path(os.path.realpath(str(root / "sub" / "ok.xlsx")))

    def test_backslash_relative_accepted(self, tmp_path: Path):
        root = tmp_path / "root"
        (root / "sub").mkdir(parents=True)
        (root / "sub" / "ok.xlsx").write_bytes(b"o")
        got = CP.resolve_within_root(root, "sub\\ok.xlsx", boundary="project_root")
        assert got.name == "ok.xlsx"


class TestPathBoundaryHasSingleImplementation:
    """🔴 边界判据只许一份实现：artifacts.py 必须**调用** canonical_paths。"""

    def test_artifacts_delegates_to_canonical_paths(self):
        src = _stripped(_ARTIFACTS_PY)
        body = _func_src(src, "CanonicalArtifactRepository._resolve_within")
        assert body, "未找到 CanonicalArtifactRepository._resolve_within"
        # 必须是**调用**形态：只留 import 时 `in body` 会假绿（既有 M7 实测过）
        assert re.search(r"resolve_within_root\s*\(", body), (
            "artifacts.py 的 _resolve_within 必须调用 canonical_paths.resolve_within_root，"
            "不得自写第二份 realpath 比较"
        )
        assert "os.path.realpath" not in body, (
            "artifacts.py 的 _resolve_within 仍自写 realpath 比较 ⇒ 边界判据两份实现"
        )

    def test_project_owns_delegates(self):
        src = _stripped(_ARTIFACTS_PY)
        body = _func_src(src, "CanonicalArtifactRepository.assert_project_owns")
        assert body
        assert re.search(r"assert_within_root\s*\(", body), (
            "assert_project_owns 必须调用 canonical_paths.assert_within_root"
        )

    def test_legacy_resolver_uses_boundary_gate(self):
        src = _stripped(_LEGACY_RESOLVER_PY)
        for fn in ("resolve_wp_file", "_template_fallback"):
            body = _func_src(src, fn)
            assert body, f"未找到 {fn}"
            assert re.search(r"is_within_any_legacy_root\s*\(", body), (
                f"{fn} 必须调用统一边界判据 is_within_any_legacy_root（Property 42）"
            )

    def test_no_second_boundary_predicate_in_sync_package(self):
        """同步域内除 canonical_paths 外，不得再出现「边界比较」实现。

        🔴 判据是**边界比较的形状**（`not in <x>.parents`），不是「出现过 realpath」。
        `artifacts.py` 里 `same_volume()` 与 `ArtifactStorageLayout.relative_of()`
        都合法用到 realpath（判盘符、绝对转相对），把它们一起算成分叉会逼守卫降标，
        而降标之后真正的第二份边界判据也就抓不到了。
        """
        pkg = _BACKEND / "app" / "services" / "workpaper_sync"
        offenders: dict[str, list[int]] = {}
        for py in sorted(pkg.glob("*.py")):
            if py.name == "canonical_paths.py":
                continue
            code = _stripped(py)
            hits = [
                code[: m.start()].count("\n") + 1
                for m in re.finditer(r"not\s+in\s+\w+\.parents", code)
            ]
            if hits:
                offenders[py.name] = hits
        assert not offenders, (
            f"以下模块自写了边界比较 `not in x.parents`（应委托 canonical_paths）: {offenders}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 40 / 41：子码最具体匹配与异类型 fail closed
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty40MostSpecificSubCode:
    """子码判据与字母类无关；父码候选永不抢占子码候选。"""

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("A9-1", True), ("A10-1", True),
            ("B12-1", True), ("B7-3", True),
            ("S33-REV", True), ("E1-3", True), ("D2-2", True),
            ("D2", False), ("F2", False), ("A16", False), ("G7", False),
            ("", False),
        ],
    )
    def test_sub_code_is_letter_class_agnostic(self, code: str, expected: bool):
        """🔴 Requirement 9.4：不得只对 A 类特殊处理。"""
        assert CP.is_sub_code(code) is expected, (
            f"{code!r} 的子码判定应为 {expected}；既有 wp_template_finder 写死 "
            "^A\\d+-\\d+ 正是 B/S 子码抢父级 XLSX 的成因"
        )

    def test_parent_code_of(self):
        assert CP.parent_code_of("B12-1") == "B12"
        assert CP.parent_code_of("S33-REV") == "S33"
        assert CP.parent_code_of("D2") is None

    def test_specificity_rank_orders_exact_above_parent(self):
        assert CP.specificity_rank("B12-1", "B12-1") > CP.specificity_rank("B12", "B12-1")
        assert CP.specificity_rank("C4", "B12-1") == -1

    def _mk(self, root: Path, name: str, wp_code: str) -> CP.TemplateCandidate:
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
        return CP.TemplateCandidate(wp_code=wp_code, path=p)

    def test_sub_code_docx_wins_over_parent_xlsx(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(CP, "TEMPLATE_ROOT", tmp_path)
        parent = self._mk(tmp_path, "B12 程序表.xlsx", "B12")
        child = self._mk(tmp_path, "B12-1 说明.docx", "B12-1")
        got = CP.pick_most_specific(
            [parent, child], wp_code="B12-1", expected_document_type="docx"
        )
        assert got.path == child.path, "子码 DOCX 必须胜过父级 XLSX（Property 40）"

    def test_exact_code_wins_over_parent_same_type(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(CP, "TEMPLATE_ROOT", tmp_path)
        parent = self._mk(tmp_path, "B12 程序表.docx", "B12")
        child = self._mk(tmp_path, "B12-1 说明.docx", "B12-1")
        got = CP.pick_most_specific(
            [parent, child], wp_code="B12-1", expected_document_type="docx"
        )
        assert got.path == child.path


class TestProperty41NoCrossTypeFallback:
    """缺 DOCX 时必须报 type mismatch / missing，绝不返回父级 XLSX。"""

    def _mk(self, root: Path, name: str, wp_code: str) -> CP.TemplateCandidate:
        p = root / name
        p.write_bytes(b"x")
        return CP.TemplateCandidate(wp_code=wp_code, path=p)

    def test_only_parent_xlsx_raises_type_mismatch(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(CP, "TEMPLATE_ROOT", tmp_path)
        parent = self._mk(tmp_path, "B12 程序表.xlsx", "B12")
        with pytest.raises(CP.DocumentTypeMismatchError) as ei:
            CP.pick_most_specific(
                [parent], wp_code="B12-1", expected_document_type="docx"
            )
        assert ei.value.expected == "docx"
        assert ei.value.observed == "xlsx"

    def test_no_candidate_raises_template_missing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(CP, "TEMPLATE_ROOT", tmp_path)
        with pytest.raises(CP.TemplateMissingError):
            CP.pick_most_specific([], wp_code="B12-1", expected_document_type="docx")

    def test_missing_and_mismatch_are_distinct_types(self):
        """🔴 两类异常不得合并：合并后「拒绝异类型回退」会被「缺模板」永久遮蔽。"""
        assert not issubclass(CP.DocumentTypeMismatchError, CP.TemplateMissingError)
        assert not issubclass(CP.TemplateMissingError, CP.DocumentTypeMismatchError)
        assert (
            CP.DocumentTypeMismatchError.error_code != CP.TemplateMissingError.error_code
        )

    def test_assert_document_type_rejects_xlsm_for_docx(self, tmp_path: Path):
        p = tmp_path / "a.xlsm"
        p.write_bytes(b"x")
        with pytest.raises(CP.DocumentTypeMismatchError):
            CP.assert_document_type(p, "docx")
        CP.assert_document_type(p, "xlsx")  # xlsm 与 xlsx 同族

    def test_legacy_resolver_type_gate_is_wired(self, tmp_path: Path):
        """`resolve_wp_file(expected_document_type=...)` 真的拒绝异类型命中。"""
        from app.services.wp_export.wp_file_resolver import resolve_wp_file

        xlsx = CP.BACKEND_ROOT / "wp_templates"
        cand = next(xlsx.rglob("*.xlsx"), None)
        assert cand is not None, "wp_templates 下应有 xlsx（判据基准）"
        rel = cand.relative_to(CP.BACKEND_ROOT).as_posix()
        ok = resolve_wp_file(rel, wp_code=None, expected_document_type="xlsx")
        assert ok.verdict == "file" and ok.path is not None
        bad = resolve_wp_file(rel, wp_code=None, expected_document_type="docx")
        assert bad.path is None, "类型不符必须不可达"
        assert bad.verdict == "type_mismatch", (
            f"类型不符应判 type_mismatch 而非 missing，实得 {bad.verdict!r}"
        )

    def test_export_engine_declares_docx_type(self):
        """P41 的**真实消费方**：_resolve_docx_template 必须声明 docx 类型门。"""
        src = _stripped(_BACKEND / "app" / "services" / "wp_export" / "export_engine.py")
        body = _func_src(src, "WpExportEngine._resolve_docx_template")
        assert body, "未找到 _resolve_docx_template"
        assert re.search(r"resolve_wp_file\s*\(", body), "必须调用统一入口"
        assert re.search(r"expected_document_type\s*=\s*[\"']docx[\"']", body), (
            "_resolve_docx_template 必须传 expected_document_type='docx' —— "
            "否则 find_template_file_any 会把父级 XLSX 当 docx 交给 Document()"
        )


class TestProperty40And41OnRealTemplateLibrary:
    """🔴 判据落在**真实** `backend/wp_templates/` 上，不是 tmp 里的替身。

    为什么必须有这一组：`TestProperty40MostSpecificSubCode` 与
    `TestProperty41NoCrossTypeFallback` 都 monkeypatch `TEMPLATE_ROOT` 到 tmp 目录，
    证明的是「判据函数本身正确」；而 Requirement 9.4 的原文点名的是**存量
    `find_template_file_any()` 在真实模板库上的行为**。只有替身判据时，
    `resolve_template_docx` 这个 Task 12 交付的类型安全包装可以整个是死代码
    （零消费方 + 零测试），而 spec 的 Property 40/41 照样「全绿」—— 假绿第①源。

    Task 12 的边界（矩阵里已登记 `blocking_task=58`）：**不改 finder 本体**，
    只提供类型门。故此处第一条用例把「finder 仍然错取父级 XLSX」显式锁成基线，
    第二条证明类型门在真实数据上真的把它挡住了。
    """

    #: 真实库里存在父级 XLSX 但**没有**自己 DOCX 的 B 子码（Requirement 9.4 原始反例）。
    B_SUB_CODE = "B12-1"
    #: 真实库里存在自己 DOCX 的 A 子码（反向：类型门不是一律拒绝）。
    A_SUB_CODE = "A9-1"
    #: 库里不可能存在的子码 —— 用合成码而不是 `S33-REV`，避免 Task 58 补了模板后本用例假红。
    ABSENT_SUB_CODE = "ZZ99-NOPE"

    def test_finder_still_returns_parent_xlsx_for_b_sub_code(self):
        """基线：存量 finder 对 B 子码返回**父级 XLSX**（Task 58 才修本体）。"""
        from app.services.wp_template_init_service import find_template_file_any

        got = find_template_file_any(self.B_SUB_CODE)
        assert got is not None, (
            f"{self.B_SUB_CODE} 在真实模板库里已无任何命中 —— 基线变了，"
            "本组用例的前提需重新确认"
        )
        assert Path(got).suffix.lower() == ".xlsx", (
            f"存量 finder 对 {self.B_SUB_CODE} 已不再返回父级 XLSX（实得 {got}）—— "
            "若 Task 58 已修 finder 本体，请把本基线用例改成正向断言"
        )
        assert CP.is_sub_code(self.B_SUB_CODE), "统一判据必须认它是子码（Requirement 9.4）"

    def test_resolve_template_docx_rejects_parent_xlsx(self):
        """Property 41 在真实数据上的核心判据：拿不到 DOCX 就报 type_mismatch。"""
        from app.services.wp_export.wp_file_resolver import resolve_template_docx

        res = resolve_template_docx(self.B_SUB_CODE)
        assert res.path is None, (
            f"{self.B_SUB_CODE} 竟解析出 {res.path} —— 父级 XLSX 被当 DOCX 交给 "
            "Document() 会直接损坏导出（Requirement 9.5）"
        )
        assert res.verdict == "type_mismatch", (
            f"应判 type_mismatch（有命中但类型不符），实得 {res.verdict!r} —— "
            "并进 missing 会让「拒绝异类型回退」与「该码无模板」分不开"
        )

    def test_resolve_template_docx_returns_real_docx(self):
        """反向：真有 DOCX 时必须返回它（证明类型门不是恒拒的死路）。"""
        from app.services.wp_export.wp_file_resolver import resolve_template_docx

        res = resolve_template_docx(self.A_SUB_CODE)
        assert res.verdict == "template_fallback", res.verdict
        assert res.path is not None and res.path.suffix.lower() == ".docx"
        assert res.path.is_file()
        assert CP.is_within_any_legacy_root(res.path), "模板路径必须在允许根内（P42）"

    def test_absent_code_is_missing_not_empty(self):
        """🔴 终态必须是 `missing`：本入口根本不读 `file_path`，`empty` 的文案
        （「未配置底稿文件路径」）会把部署缺件误导成数据没填（Requirement 9.5）。"""
        from app.services.wp_export.wp_file_resolver import resolve_template_docx

        res = resolve_template_docx(self.ABSENT_SUB_CODE)
        assert res.path is None
        assert res.verdict == "missing", (
            f"缺模板应判 missing，实得 {res.verdict!r}；`empty` 的语义是 "
            "「file_path 为空」，而本入口不读 file_path"
        )
        assert "file_path" not in res.reason, (
            f"终态文案不得提 file_path（本入口不读它），实得 {res.reason!r}"
        )


class TestLegacyResolverBoundaryVerdicts:
    """`resolve_wp_file` 的两个新 verdict 档必须真实可达且语义分离。"""

    def test_out_of_root_absolute_is_path_rejected(self, tmp_path: Path):
        from app.services.wp_export.wp_file_resolver import resolve_wp_file

        outside = tmp_path / "outside.xlsx"
        outside.write_bytes(b"x")
        if CP.is_within_any_legacy_root(outside):
            pytest.skip("tmp_path 落在仓库根内（本机 TEMP 配置特殊），该用例无法构造越界")
        res = resolve_wp_file(str(outside), wp_code=None)
        assert res.path is None
        assert res.verdict == "path_rejected", (
            f"项目外绝对路径应判 path_rejected 而非 missing，实得 {res.verdict!r}"
        )

    def test_verdict_labels_cover_new_verdicts(self):
        from app.services.wp_export.wp_file_resolver import (
            VERDICT_LABELS,
            WP_FILE_VERDICTS,
        )

        for v in ("path_rejected", "type_mismatch"):
            assert v in WP_FILE_VERDICTS
            label = VERDICT_LABELS.get(v, "")
            assert label and re.search(r"[\u4e00-\u9fff]", label), (
                f"verdict={v} 缺中文标签（UI 全中文化铁律）"
            )

    def test_template_fallback_has_no_blanket_except(self):
        """🔴 fail-open 是本任务最贵的坑：模板库回退不得 `except Exception`。"""
        src = _stripped(_LEGACY_RESOLVER_PY)
        body = _func_src(src, "_template_fallback")
        assert body
        assert "except Exception" not in body, (
            "_template_fallback 仍用 `except Exception` 吞一切 ⇒ 函数名/索引结构错会被"
            "静默记成「该 wp_code 无模板」，四层静态检查全绿"
        )
        assert re.search(r"logger\.error\(", body), (
            "模板库回退失败必须记 ERROR 态（不是 WARNING）—— 否则 fail-open 无声"
        )
        # 🔴 反向：`_template_fallback` 里**不得**出现 WARNING 级诊断。
        #    只断言「有 error」不够：把其中一条降级成 warning 后仍有别的 error 行，
        #    正则照过（变异 M15 实测 GREEN）。这里要求整个函数没有 warning 级出口。
        assert "logger.warning(" not in body, (
            "_template_fallback 出现 WARNING 级诊断 —— 模板库回退失败是部署/结构错误，"
            "必须全部 ERROR，否则 fail-open 在日志里看不见"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 28：definition/bundle 漂移 fail closed
# ═══════════════════════════════════════════════════════════════════════════


def _def_slot(slot: str, digest: str) -> BundleSlotSpec:
    return D.definition_slot_spec(slot, definition_id=uuid.uuid4(), definition_sha256=digest)


def _all_definition_slots() -> dict[str, BundleSlotSpec]:
    return {
        "template": _def_slot("template", _d("t")),
        "instrumentation": _def_slot("instrumentation", _d("i")),
        "contract": _def_slot("contract", _d("c")),
    }


def _all_marker_slots() -> dict[str, BundleSlotSpec]:
    return {s: D.marker_slot_spec(s) for s in ("template", "instrumentation", "contract")}


class TestProperty28BundleCanonicalizerFailClosed:
    """FC-1 ~ FC-14 逐条反例。每条都断言**异常类型 + 消息定位**。"""

    def test_fc1_slot_omission(self):
        with pytest.raises(BundleIntegrityError, match="缺失"):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots={"template": D.marker_slot_spec("template")},
            )

    def test_fc2_sql_null_slot(self):
        slots = _all_marker_slots()
        slots["contract"] = None  # type: ignore[assignment]
        with pytest.raises(BundleIntegrityError, match="NULL"):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc3_json_null_field(self):
        """JSON `null` 与 SQL NULL 分成两个用例：只测一条时另一条入口删掉不红。"""
        slots: dict = _all_marker_slots()
        slots["instrumentation"] = {"type": None, "ref": "x", "digest": _d("i")}
        with pytest.raises(BundleIntegrityError, match="NULL"):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc4_empty_string_field(self):
        """空串/纯空白 slot 字段被拒（判据单点在 `models.validate_bundle_slot`）。"""
        slots: dict = _all_marker_slots()
        slots["contract"] = {"type": "  ", "ref": "marker:contract:none:v1", "digest": _d("c")}
        with pytest.raises(BundleIntegrityError, match="空串"):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc5_all_zero_digest(self):
        """🔴 断言落在「伪身份」这句专属诊断上，而不是只看异常类型。

        全零 hash 被 `models.is_digest` 也会拒（消息里同样有「全零」二字），所以只断言
        类型或「全零」时，把 canonicalizer 里的专属检查短路掉仍然绿（变异 M19 实测）。
        FC-5 的要求是错误能**定位到成因**（忘了算 hash 就填 0），故判据锁「伪身份」。
        """
        slots: dict = _all_definition_slots()
        slots["template"] = {
            "type": "definition", "ref": f"definition:{uuid.uuid4()}", "digest": "0" * 64,
        }
        with pytest.raises(BundleIntegrityError, match="伪身份"):
            D.build_bundle_canonical_payload(
                authority_model="projection_contract",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc6_malformed_digest(self):
        slots: dict = _all_definition_slots()
        slots["template"] = {
            "type": "definition", "ref": f"definition:{uuid.uuid4()}",
            "digest": _d("t").upper(),
        }
        with pytest.raises(BundleIntegrityError, match="小写 hex"):
            D.build_bundle_canonical_payload(
                authority_model="projection_contract",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc7_unregistered_marker(self):
        slots: dict = _all_marker_slots()
        slots["contract"] = {
            "type": "contract:none:v99",
            "ref": "marker:contract:none:v99",
            "digest": _d("x"),
        }
        with pytest.raises(BundleIntegrityError, match="registry"):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc8_cross_slot_marker(self):
        m = D.marker_for("contract")
        slots: dict = _all_marker_slots()
        slots["instrumentation"] = {
            "type": m.slot_type, "ref": m.slot_ref, "digest": m.slot_digest,
        }
        with pytest.raises(BundleIntegrityError):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc9_marker_digest_mismatch(self):
        m = D.marker_for("contract")
        slots: dict = _all_marker_slots()
        slots["contract"] = {
            "type": m.slot_type, "ref": m.slot_ref, "digest": _d("wrong"),
        }
        with pytest.raises(BundleIntegrityError, match="digest"):
            D.build_bundle_canonical_payload(
                authority_model="opaque_single_onlyoffice",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc10_malformed_definition_ref(self):
        slots: dict = _all_definition_slots()
        slots["template"] = {
            "type": "definition", "ref": "definition:not-a-uuid", "digest": _d("t"),
        }
        with pytest.raises(BundleIntegrityError, match="definition:<uuid>"):
            D.build_bundle_canonical_payload(
                authority_model="projection_contract",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc12_marker_cannot_impersonate_contract(self):
        slots: dict = _all_definition_slots()
        slots["contract"] = D.marker_slot_spec("contract")
        with pytest.raises(BundleIntegrityError, match="approved definition"):
            D.build_bundle_canonical_payload(
                authority_model="projection_contract",
                authority_model_definition_sha256=_d("a"),
                slots=slots,
            )

    def test_fc13_invalid_authority_digest(self):
        for bad in (None, "", "0" * 64, "zz"):
            with pytest.raises(BundleIntegrityError):
                D.build_bundle_canonical_payload(
                    authority_model="opaque_single_onlyoffice",
                    authority_model_definition_sha256=bad,  # type: ignore[arg-type]
                    slots=_all_marker_slots(),
                )

    def test_fc14_unknown_authority_model(self):
        with pytest.raises(BundleIntegrityError, match="枚举未登记"):
            D.build_bundle_canonical_payload(
                authority_model="whatever_i_like",
                authority_model_definition_sha256=_d("a"),
                slots=_all_marker_slots(),
            )

    def test_valid_projection_contract_bundle_is_accepted(self):
        payload = D.build_bundle_canonical_payload(
            authority_model="projection_contract",
            authority_model_definition_sha256=_d("a"),
            slots=_all_definition_slots(),
        )
        assert payload["schema_version"] == D.BUNDLE_SCHEMA_VERSION
        assert set(payload) == {
            "schema_version", "authority_model", "template", "instrumentation", "contract",
        }
        for slot in ("template", "instrumentation", "contract"):
            assert payload[slot]["type"] == "definition"

    def test_valid_opaque_bundle_uses_markers(self):
        payload = D.build_bundle_canonical_payload(
            authority_model="opaque_single_onlyoffice",
            authority_model_definition_sha256=_d("a"),
            slots=_all_marker_slots(),
        )
        for slot in ("template", "instrumentation", "contract"):
            assert payload[slot]["type"] == f"{slot}:none:v1"


class TestBundleCanonicalBytes:
    """canonical bytes 必须对键序/空白扰动稳定，且不含 null/空串/全零。"""

    def test_key_order_perturbation_is_stable(self):
        slots = _all_definition_slots()
        a = D.bundle_canonical_digest(
            authority_model="projection_contract",
            authority_model_definition_sha256=_d("a"),
            slots={k: slots[k] for k in ("template", "instrumentation", "contract")},
        )
        b = D.bundle_canonical_digest(
            authority_model="projection_contract",
            authority_model_definition_sha256=_d("a"),
            slots={k: slots[k] for k in ("contract", "template", "instrumentation")},
        )
        assert a == b, "slot 声明顺序不得影响 canonical digest"

    def test_canonical_bytes_have_no_forbidden_tokens(self):
        raw = D.bundle_canonical_bytes(
            authority_model="opaque_single_onlyoffice",
            authority_model_definition_sha256=_d("a"),
            slots=_all_marker_slots(),
        ).decode("utf-8")
        assert "null" not in raw
        assert '""' not in raw
        assert "0" * 64 not in raw

    def test_marker_digest_matches_v151_seed_bytes(self):
        """🔴 marker digest 必须与 V151 seed 的 canonical payload 逐字节同源。"""
        for slot in ("template", "instrumentation", "contract"):
            literal = (
                '{"schema_version":"definition-bundle-marker:v1",'
                f'"slot":"{slot}","value":"none"}}'
            )
            assert D.marker_digest(slot) == hashlib.sha256(
                literal.encode("utf-8")
            ).hexdigest(), (
                f"{slot} marker digest 与 V151 seed 不一致 ⇒ DB trigger 与服务层会互相打红"
            )

    def test_canonical_json_rejects_nan(self):
        with pytest.raises(ValueError):
            D.canonical_json_bytes({"schema_version": "x", "v": float("nan")})


class TestPublishDag:
    """发布 DAG 固定为 template → instrumentation → contract → bundle → representation。"""

    def test_dag_order_is_fixed(self):
        assert [s.value for s in D.PUBLISH_DAG] == [
            "template", "instrumentation", "contract", "bundle", "representation",
        ]

    def test_prerequisites_are_monotone(self):
        for stage, prereqs in D.PUBLISH_PREREQUISITES.items():
            for p in prereqs:
                assert D.stage_index(p) < D.stage_index(stage), (
                    f"{stage.value} 的前置 {p.value} 不在它之前 ⇒ DAG 出现环/逆序"
                )

    def test_contract_requires_template_and_instrumentation(self):
        with pytest.raises(D.PublishOrderError, match="instrumentation"):
            D.assert_publish_order(
                stage="contract", approved_stages={"template"}
            )
        D.assert_publish_order(
            stage="contract", approved_stages={"template", "instrumentation"}
        )

    def test_bundle_requires_all_three(self):
        with pytest.raises(D.PublishOrderError):
            D.assert_publish_order(
                stage="bundle", approved_stages={"template", "instrumentation"}
            )

    def test_instrumentation_payload_rejects_backward_reference(self):
        """🔴 只有阶段偏序不够：payload 级反向引用禁令必须独立存在。"""
        payload = {
            "schema_version": "instrumentation-definition:v1",
            "template_definition_sha256": _d("t"),
            "contract_definition_sha256": _d("c"),
        }
        with pytest.raises(D.PublishOrderError, match="反向引用"):
            D.validate_instrumentation_payload(payload)

    def test_instrumentation_payload_rejects_bundle_reference(self):
        payload = {
            "schema_version": "instrumentation-definition:v1",
            "template_definition_sha256": _d("t"),
            "definition_bundle_sha256": _d("b"),
        }
        with pytest.raises(D.PublishOrderError):
            D.validate_instrumentation_payload(payload)

    def test_contract_payload_rejects_bundle_reference(self):
        payload = {
            "schema_version": "contract-definition:v1",
            "template_definition_sha256": _d("t"),
            "instrumentation_definition_sha256": _d("i"),
            "bundle_sha256": _d("b"),
        }
        with pytest.raises(D.PublishOrderError):
            D.validate_contract_payload(payload)

    def test_payload_rejects_self_reference(self):
        payload = {
            "schema_version": "contract-definition:v1",
            "template_definition_sha256": _d("t"),
            "instrumentation_definition_sha256": _d("i"),
            "definition_sha256": _d("self"),
        }
        with pytest.raises(Exception) as ei:
            D.validate_contract_payload(payload)
        assert "自身" in str(ei.value)

    def test_valid_payloads_accepted(self):
        D.validate_template_payload(
            {"schema_version": "template-definition:v1", "template_sha256": _d("t")}
        )
        D.validate_instrumentation_payload({
            "schema_version": "instrumentation-definition:v1",
            "template_definition_sha256": _d("t"),
            "identity_schema_version": "v1",
        })
        D.validate_contract_payload({
            "schema_version": "contract-definition:v1",
            "template_definition_sha256": _d("t"),
            "instrumentation_definition_sha256": _d("i"),
            "stable_field_key": "row_uuid",
        })
        assert D.validate_authority_model_payload({
            "schema_version": "authority-model-definition:v1",
            "authority_model": "projection_contract",
        }) is AuthorityModel.projection_contract


class TestAliasNeverUsedForHistory:
    """Requirement 2.10：历史读取不得按当前 alias 重组 bundle。"""

    def test_history_resolution_always_raises(self):
        reg = D.DefinitionAliasRegistry()
        reg.register(D.DefinitionAliasTarget(
            alias="g7.contract.latest",
            definition_id=uuid.uuid4(),
            definition_sha256=_d("c"),
        ))
        assert reg.resolve_for_publish("g7.contract.latest").definition_sha256 == _d("c")
        with pytest.raises(D.AliasResolutionForbiddenError):
            reg.resolve_for_history("g7.contract.latest")

    def test_alias_rejects_invalid_digest(self):
        reg = D.DefinitionAliasRegistry()
        with pytest.raises(Exception):
            reg.register(D.DefinitionAliasTarget(
                alias="bad", definition_id=uuid.uuid4(), definition_sha256="0" * 64
            ))


# ═══════════════════════════════════════════════════════════════════════════
# Property 7 / 39：十意图共用唯一入口
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty7SingleResolverEntry:
    """Requirement 2.10 / 9.11 列出的十个意图必须全部登记且共用一个入口。"""

    def test_intents_are_exactly_the_requirement_list(self):
        assert {i.value for i in ResolutionIntent} == {
            "config", "download", "callback", "materialize", "extract",
            "rematerialize", "retry", "rollback", "history", "evidence",
        }, "意图枚举与 Requirement 2.10/9.11 的原文清单不符 ⇒ 全链统一出现盲区"

    def test_policy_covers_every_intent(self):
        missing = [i.value for i in ResolutionIntent if i not in INTENT_POLICY]
        assert not missing, f"INTENT_POLICY 缺意图: {missing}"

    def test_historical_intents_require_frozen_identity(self):
        for intent in ("retry", "rollback", "history", "evidence"):
            pol = INTENT_POLICY[ResolutionIntent(intent)]
            assert pol.requires_frozen_identity, (
                f"{intent} 是历史读取，必须强制 frozen representation identity"
            )
            assert not pol.allows_current_pointer, (
                f"{intent} 不得按 entry current pointer 解析"
            )

    def test_live_intents_allow_current_pointer(self):
        for intent in ("config", "download", "callback", "materialize",
                       "extract", "rematerialize"):
            pol = INTENT_POLICY[ResolutionIntent(intent)]
            assert pol.allows_current_pointer
            assert not pol.requires_frozen_identity

    def test_only_materialize_may_hide_sheets(self):
        """Requirement 9.12：sheet 隐藏只作用于 room/staged representation。"""
        allowed = [i.value for i in ResolutionIntent if INTENT_POLICY[i].may_hide_sheets]
        assert allowed == ["materialize"], (
            f"允许改 sheet 可见性的意图应只有 materialize，实得 {allowed}"
        )

    def test_service_exposes_single_public_resolve(self):
        """结构判据：服务上不得出现第二个 `resolve_*` 公开入口。"""
        tree = ast.parse(_read(_RESOLUTION_PY))
        cls = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef) and n.name == "CanonicalResolutionService"
        )
        public_resolvers = sorted(
            m.name for m in cls.body
            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
            and not m.name.startswith("_")
            and m.name.startswith("resolve")
        )
        assert public_resolvers == ["resolve"], (
            f"canonical resolver 只许一个公开解析入口，实得 {public_resolvers} —— "
            "每意图一个函数会让「返回相同结果」退化成「作者记得都调」"
        )

    def test_resolve_takes_intent_as_parameter(self):
        tree = ast.parse(_read(_RESOLUTION_PY))
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "resolve"
        )
        kwonly = [a.arg for a in fn.args.kwonlyargs]
        assert "intent" in kwonly, "意图必须是参数而不是分叉（Property 7 的结构前提）"
        for required in ("project_id", "wp_id", "entry_id"):
            assert required in kwonly, f"resolve 必须显式接收 {required}（scope 不得反推）"


class TestProperty39ConfigCallbackSameSource:
    """config 与 callback 走同一意图策略 ⇒ 同一 published artifact + bundle。"""

    def test_config_and_callback_have_identical_policy(self):
        cfg = INTENT_POLICY[ResolutionIntent.config]
        cb = INTENT_POLICY[ResolutionIntent.callback]
        assert (cfg.allows_current_pointer, cfg.requires_frozen_identity) == (
            cb.allows_current_pointer, cb.requires_frozen_identity
        ), "config 与 callback 的解析策略必须一致（Property 39：两侧同一 canonical version）"

    def test_neither_config_nor_callback_may_hide_sheets(self):
        assert not INTENT_POLICY[ResolutionIntent.config].may_hide_sheets
        assert not INTENT_POLICY[ResolutionIntent.callback].may_hide_sheets


class TestSheetVisibilityGate:
    """Requirement 9.12 的可执行判据。"""

    def test_materialize_on_staged_is_allowed(self):
        CanonicalResolutionService.assert_sheet_visibility_target(
            intent="materialize",
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )

    def test_published_current_artifact_is_forbidden(self):
        with pytest.raises(SheetVisibilityForbiddenError, match="staged"):
            CanonicalResolutionService.assert_sheet_visibility_target(
                intent="materialize",
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.published,
            )

    def test_config_intent_is_forbidden(self):
        with pytest.raises(SheetVisibilityForbiddenError, match="materialize"):
            CanonicalResolutionService.assert_sheet_visibility_target(
                intent="config",
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.staged,
            )

    def test_incoming_substrate_is_forbidden(self):
        with pytest.raises(SheetVisibilityForbiddenError):
            CanonicalResolutionService.assert_sheet_visibility_target(
                intent="materialize",
                artifact_kind=ArtifactKind.incoming,
                artifact_state=ArtifactState.staged,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 迁移矩阵：状态必须由源码派生
# ═══════════════════════════════════════════════════════════════════════════


class TestResolverMigrationMatrix:
    """矩阵是 Task 12 第 4 条的可核对产物：每行状态都要有源码证据。"""

    @pytest.fixture(scope="class")
    def matrix(self) -> dict:
        assert _MATRIX_JSON.is_file(), (
            f"矩阵未生成: {_MATRIX_JSON}（跑 "
            "backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py --apply）"
        )
        return json.loads(_MATRIX_JSON.read_text(encoding="utf-8"))

    def test_matrix_is_fresh(self):
        """磁盘矩阵必须与当前源码一致（源码改了不重跑 ⇒ 状态是 stale 声明）。"""
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            build_matrix,
        )

        fresh = build_matrix()
        on_disk = json.loads(_MATRIX_JSON.read_text(encoding="utf-8"))
        assert on_disk["matrix_digest"] == fresh["matrix_digest"], (
            "矩阵与源码不一致，请重跑 --apply（状态必须派生自源码，不能是手写声明）"
        )

    def test_status_derivation_truth_table(self):
        """🔴 `migrated` 必须由「意图 ∧ 证据」派生 —— 直接锁死真值表。

        为什么必须有这条：当前矩阵没有任何 regressed 行，所以把 `build_matrix()` 里
        的证据判断整段短路成 `if False:` 之后输出完全不变、digest 不变、其余守卫全绿
        （变异 M43 实测 GREEN）。判据不能依赖「矩阵里恰好存在一个反例行」这个偶然条件。
        """
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            derive_status,
        )

        cases = [
            # (intended, evidence_ok, residue) -> status
            (("migrated", True, []), "migrated"),
            (("migrated", False, []), "regressed"),
            (("migrated", True, ["bare_exists_reachability"]), "regressed"),
            (("migrated", False, ["manual_backend_root"]), "regressed"),
            (("deferred", False, []), "deferred"),
            (("deferred", True, ["ad_hoc_storage_join"]), "deferred"),
        ]
        for (intended, ok, residue), expected in cases:
            got = derive_status(intended=intended, evidence_ok=ok, residue=list(residue))
            assert got == expected, (
                f"derive_status(intended={intended!r}, evidence_ok={ok}, "
                f"residue={residue}) 应为 {expected!r}，实得 {got!r}"
            )

    def test_no_regressed_rows(self, matrix: dict):
        bad = [r["writer_id"] for r in matrix["rows"] if r["status"] == "regressed"]
        assert not bad, (
            f"以下行声明 migrated 但源码里找不到统一入口调用（假绿第①源）: {bad}"
        )

    def test_denominator_matches_inventory(self, matrix: dict):
        """分母来自 Task 3 清册，不由矩阵自己决定（少登记一行不能蒙过去）。"""
        inv = json.loads(
            (_BACKEND / "data" / "workpaper_writer_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        expected = {
            e["writer_id"] for e in inv["entries"]
            if e["kind"] in ("resolver", "writer_resolver")
            and (e["verdicts"]["non_canonical_resolver_only"] or e["verdicts"]["multi_resolver"])
        }
        registered = {r["writer_id"] for r in matrix["rows"]}
        missing = sorted(expected - registered)
        assert not missing, f"以下 resolver 分叉未进矩阵: {missing}"

    def test_every_deferred_row_has_blocking_task_and_reason(self, matrix: dict):
        bad = [
            r["writer_id"] for r in matrix["rows"]
            if r["status"] == "deferred"
            and not (r.get("blocking_task") and r.get("reason"))
        ]
        assert not bad, (
            f"以下未迁移行缺 blocking_task/reason（等于悄悄留双真源）: {bad}"
        )

    def test_task12_named_forks_are_migrated(self, matrix: dict):
        """Task 12 第 4 条点名的三类分叉必须真的 migrated。"""
        by_module: dict[str, list[dict]] = {}
        for r in matrix["rows"]:
            by_module.setdefault(r["module"], []).append(r)
        for module in (
            "app.services.wp_export.wp_file_resolver",
            "app.services.wopi_service",
            "app.services.wp_storage_service",
        ):
            rows = by_module.get(module, [])
            assert rows, f"点名分叉 {module} 未出现在矩阵中"
            assert all(r["status"] == "migrated" for r in rows), (
                f"{module} 仍有未迁移行: "
                f"{[r['writer_id'] for r in rows if r['status'] != 'migrated']}"
            )
            for r in rows:
                assert r["evidence"]["module_unified_entry_calls"], (
                    f"{r['writer_id']} 声明 migrated 但模块内无统一入口调用"
                )

    def test_migrated_functions_have_no_self_written_markers(self, matrix: dict):
        """migrated 行的**函数体内**不得残留自写路径解析特征。

        🔴 判据落在函数级而不是模块级：模块里合法存在的目录存在性检查
        （`if not version_dir.exists()`）与显示名取值（`Path(wp.file_path).name`）
        不是解析分叉。用模块级会误判，进而逼守卫降标；降标后真正的回退
        （在 `get_file` 里重写 `fp = Path(wp.file_path)`）反而抓不到。
        """
        offenders = {}
        for r in matrix["rows"]:
            if r["status"] != "migrated":
                continue
            markers = r["evidence"]["function_self_written_markers"]
            if markers:
                offenders[r["writer_id"]] = markers
        assert not offenders, (
            f"以下已迁移函数仍残留自写路径解析特征: {offenders}"
        )

    def test_template_finder_deferral_names_94_and_the_bridge(self, matrix: dict):
        """🔴 Requirement 9.4 的登记必须逐 writer 可核对：谁已迁移、谁还没、还差什么。

        `find_template_file_any` 是 Requirement 9.4 **原文点名**的函数。Task 12 只提供
        类型门、不改本体；**Task 58 已改本体**（自有-DOCX 探测提到 A-only 分支之前并
        委派 `word_resolution.resolve_own_docx_or_none`），故它在矩阵里现在是
        `migrated`；同模块的 `find_all_template_files` 只服务 xlsx 多文件底稿，仍
        `deferred`。

        没有这条守卫时，两者的裁决可以被改成任意文本、`blocking_task` 可以被清空，
        于是「9.4 到底谁负责、还差什么」在矩阵里消失，而
        `test_every_deferred_row_has_blocking_task_and_reason` 只看**非空**。

        🔴 判据刻意**逐 writer** 而不是「本模块全部 deferred」：后者在模块内一半迁移
        一半没迁移时只能整体打红或整体放过，两种都会丢掉逐项可核对性（矩阵生成器的
        `POLICY_BY_WRITER` 存在的同一理由）。
        """
        rows = {
            r["qualname"]: r
            for r in matrix["rows"]
            if r["module"] == "app.services.wp_template_finder"
        }
        assert rows, "wp_template_finder 未进矩阵（Requirement 9.4 点名的分叉）"
        # Task 74 the detector fix recovered three more rows in this module:
        # `_record_ad_hoc_path` now resolves module-level path constants, so the
        # `TEMPLATES_DIR / ...` lookups that the d1262c80 file split had made
        # invisible are back in the denominator. The set is still enumerated
        # writer-by-writer on purpose -- see this test docstring.
        assert set(rows) == {
            "find_template_file_any",
            "find_all_template_files",
            "find_template_file",
            "_find_docx_by_index_or_disk",
            "_find_docx_on_disk",
        }, (
            f"矩阵里的 finder writer 集合变了: {sorted(rows)}"
        )

        migrated = rows["find_template_file_any"]
        assert migrated["status"] == "migrated", (
            "Requirement 9.4 原文点名的 find_template_file_any 已由 Task 58 改本体，"
            f"矩阵却记 {migrated['status']!r}"
        )
        # 「已迁移」必须有源码证据（不是声明）：矩阵自己的 evidence 列要能看到委派调用
        assert "resolve_own_docx_or_none" in (
            migrated["evidence"]["module_unified_entry_calls"]
        ), "migrated 却看不到对统一 Word resolver 的调用 —— 声明与源码脱钩"
        assert not migrated["evidence"]["function_self_written_markers"], (
            f"已迁移函数仍残留自写路径特征: {migrated['evidence']['function_self_written_markers']}"
        )
        note = migrated.get("note") or ""
        assert "resolve_own_docx_or_none" in note and "58" in note, (
            "migrated 裁决必须写明委派目标与责任任务（否则交付边界不可核对）"
        )

        deferred = rows["find_all_template_files"]
        assert deferred["status"] == "deferred"
        reason = deferred["reason"] or ""
        assert "xlsx" in reason and "Task 58" in reason, (
            "剩余 deferral 必须写明「不在 Word lane 内」这条边界，否则读者会以为 9.4 没做完"
        )
        assert str(deferred.get("blocking_task") or "").strip(), (
            "deferral 必须保留非空 blocking_task"
        )
        assert "58" not in str(deferred.get("blocking_task") or ""), (
            "Task 58 已落地，blocking_task 不得再指向它（否则矩阵声称一个已完成的阻塞）"
        )

        # The three recovered rows are helpers of the same template-library lane:
        # none of them is on the Word lane Task 58 migrated, so each must still
        # carry a non-empty blocking_task that does not point at the done Task 58.
        for name in ("find_template_file", "_find_docx_by_index_or_disk", "_find_docx_on_disk"):
            row = rows[name]
            assert row["status"] == "deferred", name
            assert str(row.get("blocking_task") or "").strip(), name
            assert "58" not in str(row.get("blocking_task") or ""), name

    def test_oo_router_deferral_is_registered_with_912_reason(self, matrix: dict):
        """Requirement 9.12 的未迁移登记必须显式点名（防悄悄放过）。"""
        rows = [
            r for r in matrix["rows"]
            if r["module"] == "app.routers.wp_onlyoffice_router"
        ]
        assert rows, "wp_onlyoffice_router 未进矩阵"
        assert all(r["status"] == "deferred" for r in rows)
        reason = rows[0]["reason"] or ""
        assert "9.12" in reason and "assert_sheet_visibility_target" in reason, (
            "OO router 的 deferral 必须写明 Requirement 9.12 与 Task 12 已提供的判据函数"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 反向自检：判据不是空转
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardSelfCheck:
    """替身复现旧行为时判据必须打红。"""

    _A_ONLY_SUB_CODE = re.compile(r"^A\d+-\d+")

    def test_a_only_regex_misses_b_sub_codes(self):
        """证明「只对 A 类特殊处理」确实漏 B/S 子码 —— Property 40 的判据基础。"""
        assert self._A_ONLY_SUB_CODE.match("A9-1")
        assert not self._A_ONLY_SUB_CODE.match("B12-1")
        assert not self._A_ONLY_SUB_CODE.match("S33-REV")
        # 而统一判据全部命中
        assert CP.is_sub_code("B12-1") and CP.is_sub_code("S33-REV")

    def test_prefix_only_boundary_check_is_fooled_by_symlink(self, tmp_path: Path):
        """证明字符串前缀判据不足 —— Property 42 必须 realpath。"""
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        link = root / "link"
        try:
            os.symlink(str(outside), str(link), target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError) as exc:
            pytest.skip(f"本机不允许创建软链接: {exc}")
        naive_ok = str(link).startswith(str(root))
        assert naive_ok, "前缀判据会放行（这正是它不够的证明）"
        assert not CP.is_within_root(root, link), "realpath 判据必须拒绝"

    def test_bare_exists_pattern_is_detectable(self):
        """证明「裸 exists 判可达」的正则判据抓得到旧写法。"""
        bad = "def f(wp):\n    fp = Path(wp.file_path)\n    if not fp.exists():\n        return None\n"
        assert re.search(
            r"if\s+not\s+[\w\.]+\.exists\(\)", bad
        ), "反向自检失败：判据抓不到旧写法"
        good = "def f(wp):\n    r = resolve_wp_file(wp.file_path)\n    return r.path\n"
        assert not re.search(r"if\s+not\s+[\w\.]+\.exists\(\)", good)

    def test_strip_comments_removes_counterexample(self):
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            strip_comments_and_docstrings,
        )

        src = "x = 1\n# 反例: if not fp.exists(): pass\ny = 2\n"
        out = strip_comments_and_docstrings(src)
        assert "exists()" not in out
        assert "x = 1" in out and "y = 2" in out

    def test_called_names_ignores_import_only(self):
        """🔴 「只留 import、把委托改回自写」必须被抓到。"""
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            called_names,
        )

        import_only = (
            "def f(p):\n"
            "    from app.services.wp_export.wp_file_resolver import resolve_wp_file\n"
            "    return Path(p).resolve()\n"
        )
        assert "resolve_wp_file" not in called_names(import_only), (
            "called_names 把 import 行当成调用 ⇒ 迁移证据会假绿"
        )
        real_call = (
            "def f(p):\n"
            "    from app.services.wp_export.wp_file_resolver import resolve_wp_file\n"
            "    return resolve_wp_file(p).path\n"
        )
        assert "resolve_wp_file" in called_names(real_call)

    def test_function_source_handles_multiline_signature(self):
        sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
        from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
            function_source,
        )

        src = (
            "def f(\n"
            "    a: str,\n"
            "    b: int = 0,\n"
            ") -> dict[str, int]:\n"
            "    marker = 1\n"
            "    return {}\n"
        )
        assert "marker = 1" in function_source(src, "f")

    def test_marker_impersonation_is_detected(self):
        """替身：projection_contract 用 marker 冒充 contract 必须被拒。"""
        with pytest.raises(BundleIntegrityError):
            D.build_bundle_canonical_payload(
                authority_model="projection_contract",
                authority_model_definition_sha256=_d("a"),
                slots={
                    "template": _def_slot("template", _d("t")),
                    "instrumentation": _def_slot("instrumentation", _d("i")),
                    "contract": D.marker_slot_spec("contract"),
                },
            )
        # 反向：opaque 用 marker 是合法的（证明判据没把 marker 一律禁掉）
        D.build_bundle_canonical_payload(
            authority_model="opaque_single_onlyoffice",
            authority_model_definition_sha256=_d("a"),
            slots=_all_marker_slots(),
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
