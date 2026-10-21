"""附注写端点清册与 edit 级影响清单的失败条件测试（任务 8.8）。

每种失败条件各一个合成输入：断言退出码、中文原因（含文件 / 函数 / 未识别名称或样例名）、
不写出文件、已提交产物不变。另以合成清册与声明验证目标门禁合并与「现门禁已等于目标门禁」标注。

测试策略：脚本的完整流水线会在子进程里导入被扫描树以收集运行时路由表，对合成目录不可行。
因此在子流水线入口附近切入：
- 自检失败、无路由目录、零匹配文件、无法解析文件：直接调 run() / build()，这些在路由表收集前就失败。
- 未识别依赖、I 类缺声明、声明对不上端点等：调内部 _scan_files / _entries / _validate，绕过运行时路由收集。
- 检查模式漂移：直接调 check_against()。
- 影响清单同类。
- 目标门禁合并：调 classify 纯函数。

_Requirements: 1.4, 1.5, 1.7, 1.9, 1.10, 9.8_
"""
from __future__ import annotations

import io
import contextlib
import json
import sys
import textwrap
from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import patch

import pytest

# ─── 把脚本目录加入搜索路径 ──────────────────────────────────────────────────
_SCRIPTS_GEN = Path(__file__).resolve().parents[1] / "scripts" / "gen"
if str(_SCRIPTS_GEN) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_GEN))

from authz_inventory import classify, gates, render, routes, selfcheck  # noqa: E402
import importlib  # noqa: E402

_note_inv = importlib.import_module("gen_note_write_inventory")
_impact_inv = importlib.import_module("gen_edit_level_impact_inventory")

EXIT_OK, EXIT_FAILED, EXIT_DRIFT = 0, 1, 2


# ═══════════════════════════════════════════════════════════════════════════════
#  辅助
# ═══════════════════════════════════════════════════════════════════════════════

def _make_repo(tmp_path: Path, *, router_files: dict[str, str] | None = None,
               app_files: dict[str, str] | None = None) -> Path:
    """在 tmp_path 下建最小仓库骨架（只含 backend/app/routers/ 和可选的 app 文件）。"""
    root = tmp_path / "repo"
    routers = root / "backend" / "app" / "routers"
    routers.mkdir(parents=True)
    (routers / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "__init__.py").write_text("", encoding="utf-8")
    if router_files:
        for name, source in router_files.items():
            (routers / name).write_text(textwrap.dedent(source), encoding="utf-8")
    if app_files:
        for relpath, source in app_files.items():
            target = root / "backend" / "app" / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(textwrap.dedent(source), encoding="utf-8")
    return root


def _capture_run_note(root: Path, *, check: bool = False, out: Path | None = None,
                      declarations: Path | None = None,
                      samples: Any = None) -> tuple[int, str, str]:
    """调用附注写端点清册 run()，捕获 stdout/stderr。"""
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    kw: dict[str, Any] = {"root": root, "check": check,
                          "out": out or (root / "note_write_inventory.json")}
    if declarations is not None:
        kw["declarations"] = declarations
    if samples is not None:
        kw["samples"] = samples
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        code = _note_inv.run(**kw)
    return code, stdout_buf.getvalue(), stderr_buf.getvalue()


def _capture_run_impact(root: Path, *, check: bool = False, out: Path | None = None,
                        samples: Any = None) -> tuple[int, str, str]:
    """调用 edit 级影响清单 run()，捕获 stdout/stderr。"""
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    kw: dict[str, Any] = {"root": root, "check": check,
                          "out": out or (root / "impact_inventory.json")}
    if samples is not None:
        kw["samples"] = samples
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        code = _impact_inv.run(**kw)
    return code, stdout_buf.getvalue(), stderr_buf.getvalue()


_EMPTY_DECLARATIONS = {"schema": "note_write_target_declarations/v1", "declarations": []}


def _write_declarations(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
#  一、附注写端点清册的自检失败（需求 1.6）
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoteInvSelfcheckFailure:
    """自检判错 → 退出码 1、中文原因含样例名、不写文件。"""

    def test_selfcheck_wrong_sample(self, tmp_path: Path):
        broken = selfcheck.Sample("故意判错的样例", expected="不可能", run=lambda: "实际")
        out = tmp_path / "should_not_exist.json"
        code, _, stderr = _capture_run_note(
            tmp_path, out=out, samples=(broken,),
            declarations=tmp_path / "decl.json",
        )
        assert code == EXIT_FAILED
        assert "故意判错的样例" in stderr
        assert "判错" in stderr or "未通过" in stderr
        assert not out.exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  二、附注写端点清册的需求 1.7 失败条件
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoteInvReq17:
    """需求 1.7 列出的各种失败条件。"""

    def test_no_routers_dir(self, tmp_path: Path):
        """--root 没有 backend/app/routers/ → 退出码 1。"""
        root = tmp_path / "empty_repo"
        root.mkdir()
        decl = tmp_path / "decl.json"
        _write_declarations(decl, _EMPTY_DECLARATIONS)
        out = tmp_path / "out.json"
        code, _, stderr = _capture_run_note(root, out=out, declarations=decl)
        assert code == EXIT_FAILED
        assert "backend/app/routers" in stderr
        assert not out.exists()

    def test_zero_scanned_files(self, tmp_path: Path):
        """扫描到的附注路由文件数为 0。"""
        root = _make_repo(tmp_path, router_files={"other_stuff.py": "x = 1\n"})
        decl = tmp_path / "decl.json"
        _write_declarations(decl, _EMPTY_DECLARATIONS)
        out = tmp_path / "out.json"
        code, _, stderr = _capture_run_note(root, out=out, declarations=decl)
        assert code == EXIT_FAILED
        assert "文件数为 0" in stderr
        assert not out.exists()

    def test_unparseable_file(self, tmp_path: Path):
        """匹配文件无法解析 → 包含文件名的中文原因。"""
        root = _make_repo(tmp_path, router_files={"note_broken.py": "def x(:\n"})
        decl = tmp_path / "decl.json"
        _write_declarations(decl, _EMPTY_DECLARATIONS)
        out = tmp_path / "out.json"
        code, _, stderr = _capture_run_note(root, out=out, declarations=decl)
        assert code == EXIT_FAILED
        assert "无法解析" in stderr
        assert "note_broken" in stderr
        assert not out.exists()

    def test_unregistered_dependency_via_recognition(self):
        """需求 1.7：挂载未登记的依赖 → 识别结果有问题、包含未识别名称。
        直接用 selfcheck.recognize_source 验证（因为完整流水线需要运行时路由表）。"""
        source = textwrap.dedent("""\
            from fastapi import APIRouter, Depends
            from app.deps import get_current_user
            from app.somewhere import load_tenant
            router = APIRouter(prefix="/api/selfcheck/{project_id}")
            @router.post("/unknown")
            async def endpoint(project_id: str, tenant=Depends(load_tenant)):
                return tenant
        """)
        result = selfcheck.recognize_source(source, "endpoint")
        # 必须有未识别依赖的问题
        issue_kinds = {i.kind for i in result.issues}
        assert gates.UNKNOWN_DEPENDENCY in issue_kinds
        # 问题信息包含未识别的名称
        for issue in result.issues:
            if issue.kind == gates.UNKNOWN_DEPENDENCY:
                assert "load_tenant" in issue.name

    def test_unregistered_dep_prevents_classification(self):
        """未识别依赖的端点不归类（category 为 None）——这确保 build() 会报问题。"""
        source = textwrap.dedent("""\
            from fastapi import APIRouter, Depends
            from app.somewhere import load_tenant
            router = APIRouter(prefix="/api/selfcheck/{project_id}")
            @router.post("/unknown")
            async def endpoint(project_id: str, tenant=Depends(load_tenant)):
                return tenant
        """)
        result = selfcheck.recognize_source(source, "endpoint")
        verdict = classify.classify(selfcheck.SAMPLE_FILE, result)
        assert verdict.category is None, "有未识别依赖的端点不应被归类"

    def test_zero_write_endpoints(self, tmp_path: Path):
        """扫描到的写端点数为 0（只有 GET）。
        测内部函数 _write_routes：空 pairs 时 problems 非空。"""
        problems: list[str] = []
        # 空路由对：没有 POST/PUT/PATCH/DELETE
        table = routes.RouteTable(
            groups=(), routes=(),
            api_route_counts=(), other_route_counts=(), app_file="",
        )
        pairs = _note_inv._write_routes(
            infos={},
            files=("backend/app/routers/note_ro.py",),
            table=table,
            problems=problems,
        )
        assert not pairs
        assert any("写端点数为 0" in p for p in problems)

    def test_i_class_missing_declaration(self):
        """需求 1.9：I 类端点缺少声明 → problems 非空。
        测内部函数 _entries（绕过路由收集）。"""
        # 构造一个 I 类端点的识别信息
        source = textwrap.dedent("""\
            from fastapi import APIRouter
            from sqlalchemy.ext.asyncio import AsyncSession
            router = APIRouter(prefix="/api/note-test")
            @router.post("/{project_id}/save")
            async def save_note(project_id: str):
                return None
        """)
        file = "backend/app/routers/note_no_auth.py"
        info = gates.analyze_module(file, textwrap.dedent(source))
        declared = info.declared_routes()[0]
        record = routes.RouteRecord(
            method="POST", path="/api/note-test/{project_id}/save",
            file=file, function="save_note", registered=True, group="report",
            module="note_no_auth",
        )
        problems: list[str] = []
        entries = _note_inv._entries(
            infos={file: info},
            pairs=[(declared, record)],
            declarations={},  # 空声明：I 类无默认值
            problems=problems,
        )
        assert any("I 类" in p for p in problems), f"期望 I 类缺声明的问题，实际 problems: {problems}"

    def test_committed_product_unchanged_on_failure(self, tmp_path: Path):
        """失败时已提交的清册保持不变。"""
        out = tmp_path / "existing.json"
        original = b'{"existing": true}'
        out.write_bytes(original)
        root = tmp_path / "bad_repo"
        root.mkdir()
        decl = tmp_path / "decl.json"
        _write_declarations(decl, _EMPTY_DECLARATIONS)
        code, _, _ = _capture_run_note(root, out=out, declarations=decl)
        assert code == EXIT_FAILED
        assert out.read_bytes() == original


# ═══════════════════════════════════════════════════════════════════════════════
#  三、附注写端点清册的需求 1.5 校验失败
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoteInvReq15:
    """需求 1.5 的四项校验不成立。"""

    def test_declaration_for_nonexistent_endpoint(self):
        """声明对不上现存写端点 → 校验报「对不上」。"""
        # 构造一个有端点的清册 + 一条指向不存在端点的声明
        source = textwrap.dedent("""\
            from fastapi import APIRouter, Depends
            from app.deps import require_project_access
            router = APIRouter(prefix="/api/note-test")
            @router.post("/{project_id}/real")
            async def real_ep(project_id: str, _=Depends(require_project_access("edit"))):
                return None
        """)
        file = "backend/app/routers/note_decl.py"
        info = gates.analyze_module(file, textwrap.dedent(source))
        declared = info.declared_routes()[0]
        record = routes.RouteRecord(
            method="POST", path="/api/note-test/{project_id}/real",
            file=file, function="real_ep", registered=True, group="report",
            module="note_decl",
        )
        # 声明里多了一个不存在的端点
        phantom_decl = classify.Declaration(
            method="POST", path="/api/note-test/{project_id}/nonexistent",
            target=classify.Target(kind="note_edit_gate", declared=True),
        )
        problems: list[str] = []
        _note_inv._validate(
            pairs=[(declared, record)],
            entries=[{"category": "E", "method": "POST", "path": "/api/note-test/{project_id}/real"}],
            declarations={
                ("POST", "/api/note-test/{project_id}/real"): classify.Declaration(
                    method="POST", path="/api/note-test/{project_id}/real",
                    target=classify.Target(kind="note_edit_gate", declared=True),
                ),
                ("POST", "/api/note-test/{project_id}/nonexistent"): phantom_decl,
            },
            frontend=None,
            problems=problems,
        )
        assert any("nonexistent" in p and "对不上" in p for p in problems), \
            f"期望报 nonexistent 对不上，实际 problems: {problems}"


# ═══════════════════════════════════════════════════════════════════════════════
#  四、附注写端点清册的需求 1.10 检查模式
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoteInvCheckMode:
    """需求 1.10：检查模式下的漂移检测。"""

    def test_committed_not_exists(self, tmp_path: Path):
        """已提交的清册不存在 → 退出码 2。"""
        out = tmp_path / "nonexistent.json"
        built = _note_inv.Built(
            payload={"endpoints": [], "scan": {}, "counts": {}, "schema": "test",
                     "editor_unmatched": None, "editor_write_call_total": None},
            text='{"test": true}',
            summary=("test",),
        )
        code = _note_inv.check_against(out, built)
        assert code == EXIT_DRIFT

    def test_content_mismatch(self, tmp_path: Path):
        """已提交清册内容与现算不同 → 退出码 2 并列出变化。"""
        out = tmp_path / "inventory.json"
        # 写入与现算不同的内容
        old_payload = {"schema": "test", "endpoints": [{"method": "DELETE", "path": "/fake"}],
                       "scan": {}, "counts": {}}
        out.write_text(json.dumps(old_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        built = _note_inv.Built(
            payload={"endpoints": [], "scan": {}, "counts": {}, "schema": "test",
                     "editor_unmatched": None, "editor_write_call_total": None},
            text='{"endpoints": []}',
            summary=("test",),
        )
        stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            code = _note_inv.check_against(out, built)
        assert code == EXIT_DRIFT
        assert "不一致" in stderr_buf.getvalue()

    def test_byte_identical_is_ok(self, tmp_path: Path):
        """已提交清册逐字节相同 → 退出码 0。"""
        text = '{"test": true}\n'
        out = tmp_path / "inventory.json"
        out.write_bytes(text.encode("utf-8"))
        built = _note_inv.Built(
            payload={}, text=text, summary=(),
        )
        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            code = _note_inv.check_against(out, built)
        assert code == EXIT_OK
        assert _note_inv.CONSISTENT in stdout_buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
#  五、edit 级影响清单的自检失败（需求 9.8）
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpactInvSelfcheckFailure:
    """自检判错 → 退出码 1、含样例名。"""

    def test_selfcheck_wrong_sample(self, tmp_path: Path):
        broken = selfcheck.Sample("影响清单故意判错", expected="不对", run=lambda: "实际")
        out = tmp_path / "should_not_exist.json"
        code, _, stderr = _capture_run_impact(tmp_path, out=out, samples=(broken,))
        assert code == EXIT_FAILED
        assert "影响清单故意判错" in stderr
        assert "判错" in stderr or "未通过" in stderr
        assert not out.exists()


# ═══════════════════════════════════════════════════════════════════════════════
#  六、edit 级影响清单的失败条件（需求 9.8）
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpactInvFailures:
    """影响清单的各种失败条件。"""

    def test_no_app_dir(self, tmp_path: Path):
        """--root 没有 backend/app/ → 退出码 1。"""
        root = tmp_path / "empty"
        root.mkdir()
        out = tmp_path / "out.json"
        code, _, stderr = _capture_run_impact(root, out=out)
        assert code == EXIT_FAILED
        assert "backend/app" in stderr
        assert not out.exists()

    def test_unparseable_app_file(self, tmp_path: Path):
        """backend/app/ 下有无法解析的 .py → 退出码 1。"""
        root = _make_repo(tmp_path, app_files={
            "services/broken_service.py": "def x(:\n",
        })
        out = tmp_path / "out.json"
        code, _, stderr = _capture_run_impact(root, out=out)
        assert code == EXIT_FAILED
        assert "无法解析" in stderr
        assert not out.exists()

    def test_committed_product_unchanged_on_failure(self, tmp_path: Path):
        """失败时已提交的清单保持不变。"""
        out = tmp_path / "existing.json"
        original = b'{"preserved": true}'
        out.write_bytes(original)
        root = tmp_path / "bad"
        root.mkdir()
        code, _, _ = _capture_run_impact(root, out=out)
        assert code == EXIT_FAILED
        assert out.read_bytes() == original


# ═══════════════════════════════════════════════════════════════════════════════
#  七、edit 级影响清单的检查模式（需求 1.10 同类）
# ═══════════════════════════════════════════════════════════════════════════════

class TestImpactInvCheckMode:
    """检查模式漂移。"""

    def test_committed_not_exists(self, tmp_path: Path):
        """已提交的清单不存在 → 退出码 2。"""
        out = tmp_path / "nonexistent.json"
        built = _impact_inv.Built(
            payload={"gate_points": [], "direct_comparisons": [],
                     "appendix_non_auth_reads": [], "totals": {}},
            text='{"test": true}',
            summary=("test",),
        )
        code = _impact_inv.check_against(out, built)
        assert code == EXIT_DRIFT

    def test_content_mismatch(self, tmp_path: Path):
        """已提交清单内容与现算不同 → 退出码 2。"""
        out = tmp_path / "impact.json"
        out.write_text('{"gate_points": [{"old": true}], "totals": {}}', encoding="utf-8")
        built = _impact_inv.Built(
            payload={"gate_points": [], "direct_comparisons": [],
                     "appendix_non_auth_reads": [], "totals": {}},
            text='{"gate_points": []}',
            summary=(),
        )
        stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            code = _impact_inv.check_against(out, built)
        assert code == EXIT_DRIFT
        assert "不一致" in stderr_buf.getvalue()

    def test_byte_identical_is_ok(self, tmp_path: Path):
        """已提交清单逐字节相同 → 退出码 0。"""
        text = '{"test": true}\n'
        out = tmp_path / "impact.json"
        out.write_bytes(text.encode("utf-8"))
        built = _impact_inv.Built(
            payload={}, text=text, summary=(),
        )
        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            code = _impact_inv.check_against(out, built)
        assert code == EXIT_OK
        assert _impact_inv.CONSISTENT in stdout_buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
#  八、目标门禁合并与「现门禁已等于目标门禁」标注
# ═══════════════════════════════════════════════════════════════════════════════

class TestTargetGateMerging:
    """以合成清册与声明验证 resolve_target 与 target_met。"""

    def test_e_class_defaults_to_note_edit_gate(self):
        """E 类默认目标为附注编辑门禁。"""
        target = classify.resolve_target("E", None)
        assert target.kind == "note_edit_gate"
        assert target.declared is False

    def test_i_class_no_default(self):
        """I 类没有默认值，未声明时 kind 为 None。"""
        target = classify.resolve_target("I", None)
        assert target.kind is None

    def test_s_c_g_r_x_default_to_keep_current(self):
        """S/C/G/R/X 类默认保持现门禁。"""
        for cat in ("S", "C", "G", "R", "X"):
            target = classify.resolve_target(cat, None)
            assert target.kind == "keep_current", f"{cat} 默认应为 keep_current"

    def test_declaration_overrides_default(self):
        """声明覆盖类别默认值。"""
        decl = classify.Declaration(
            method="POST", path="/api/test",
            target=classify.Target(kind="design_gate", declared=True, reason="test",
                                   gate="require_project_access",
                                   params=(("level", "readonly"),),
                                   project_from=("path",), eqcr="allow"),
        )
        target = classify.resolve_target("E", decl)
        assert target.kind == "design_gate"
        assert target.declared is True

    def test_keep_current_always_met(self):
        """target_met：keep_current 恒为 True。"""
        result = gates.EndpointGates(
            file="test.py", function="ep", uses=(), markers=frozenset(),
            signature_kinds=frozenset(), stub=frozenset(), issues=(),
        )
        assert classify.target_met(result, classify.Target(kind="keep_current", declared=False)) is True

    def test_note_edit_gate_met_when_all_note_edit(self):
        """target_met：全部非中性非登录判定都是附注编辑门禁 → True。"""
        use = gates.GateUse(
            name="assert_note_edit_access", category="note_edit", via="body",
            conditional=False, chain=(), level="review", level_origin="fixed",
            params=(), param="", site=(selfcheck.SAMPLE_FILE, "ep", 0),
        )
        result = gates.EndpointGates(
            file="test.py", function="ep", uses=(use,), markers=frozenset(),
            signature_kinds=frozenset(), stub=frozenset(), issues=(),
        )
        assert classify.target_met(result, classify.Target(kind="note_edit_gate", declared=False)) is True

    def test_note_edit_gate_not_met_when_mixed(self):
        """target_met：混合门禁 → False。"""
        use1 = gates.GateUse(
            name="assert_note_edit_access", category="note_edit", via="body",
            conditional=False, chain=(), level="review", level_origin="fixed",
            params=(), param="", site=(selfcheck.SAMPLE_FILE, "ep", 0),
        )
        use2 = gates.GateUse(
            name="require_project_access", category="project", via="signature",
            conditional=False, chain=(), level="edit", level_origin="literal",
            params=(), param="_", site=(selfcheck.SAMPLE_FILE, "ep", 1),
        )
        result = gates.EndpointGates(
            file="test.py", function="ep", uses=(use1, use2), markers=frozenset(),
            signature_kinds=frozenset(), stub=frozenset(), issues=(),
        )
        assert classify.target_met(result, classify.Target(kind="note_edit_gate", declared=False)) is False

    def test_note_edit_gate_not_met_when_conditional(self):
        """target_met：条件执行的附注编辑门禁 → False。"""
        use = gates.GateUse(
            name="assert_note_edit_access", category="note_edit", via="body",
            conditional=True, chain=(), level="review", level_origin="fixed",
            params=(), param="", site=(selfcheck.SAMPLE_FILE, "ep", 0),
        )
        result = gates.EndpointGates(
            file="test.py", function="ep", uses=(use,), markers=frozenset(),
            signature_kinds=frozenset(), stub=frozenset(), issues=(),
        )
        assert classify.target_met(result, classify.Target(kind="note_edit_gate", declared=False)) is False

    def test_note_edit_gate_not_met_when_empty(self):
        """target_met：无判定 → False。"""
        result = gates.EndpointGates(
            file="test.py", function="ep", uses=(), markers=frozenset(),
            signature_kinds=frozenset(), stub=frozenset(), issues=(),
        )
        assert classify.target_met(result, classify.Target(kind="note_edit_gate", declared=False)) is False

    def test_pending_design_review_never_met(self):
        """target_met：待 design 核对恒为 False。"""
        result = gates.EndpointGates(
            file="test.py", function="ep", uses=(), markers=frozenset(),
            signature_kinds=frozenset(), stub=frozenset(), issues=(),
        )
        assert classify.target_met(result, classify.Target(kind="pending_design_review", declared=True)) is False


# ═══════════════════════════════════════════════════════════════════════════════
#  九、声明文件解析的失败情形
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeclarationParsing:
    """声明文件解析的失败与边界情形。"""

    def test_invalid_schema(self):
        """schema 不对 → 问题清单非空。"""
        found, problems = classify.parse_declarations({"schema": "wrong", "declarations": []})
        assert problems
        assert "格式不符" in problems[0]

    def test_duplicate_declaration(self):
        """同一方法与路径声明两次 → 报重复。"""
        data = {
            "schema": "note_write_target_declarations/v1",
            "declarations": [
                {"method": "POST", "path": "/api/test", "target": "keep_current", "reason": "a"},
                {"method": "POST", "path": "/api/test", "target": "keep_current", "reason": "b"},
            ],
        }
        found, problems = classify.parse_declarations(data)
        assert any("重复" in p for p in problems)

    def test_missing_required_fields(self):
        """声明缺少必填字段 → 问题非空。"""
        data = {
            "schema": "note_write_target_declarations/v1",
            "declarations": [
                {"method": "POST"},  # 缺 path / target / reason
            ],
        }
        found, problems = classify.parse_declarations(data)
        assert problems

    def test_not_a_dict(self):
        """声明文件不是 dict → 报格式不符。"""
        found, problems = classify.parse_declarations([1, 2, 3])
        assert problems
        assert "格式不符" in problems[0]

    def test_declarations_not_a_list(self):
        """declarations 不是列表 → 报格式不符。"""
        found, problems = classify.parse_declarations(
            {"schema": "note_write_target_declarations/v1", "declarations": "not_a_list"}
        )
        assert problems
        assert "格式不符" in problems[0]
