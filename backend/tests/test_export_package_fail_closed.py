"""组合包 fail-closed 守卫（spec platform-global-display-settings-closure 任务 10 / AC-20）。

🔴 本文件守护的是**三个真实缺陷**（改造前 `export_package_service` 的形态）：

1. `except → BytesIO(b"")` 后**照样打包** —— 用户拿到一个 zip，里面那个 xlsx
   是 0 字节、打开报「文件已损坏」，而调用方只看到 200 ⇒ 静默产出废件。
2. `audit_content = b"Audit report placeholder"` —— **真占位符字节**，
   而 manifest 里还带着 sha256 与 size ⇒ 看起来像「有据可查的正式件」。
3. `wp_content = b"Workpapers placeholder"` —— 同上。

AC-20 原文：「组合包任一来源/policy 失败时不生成 zip，包内无空文件和 placeholder」。

判据分四层：
- 来源失败 ⇒ 抛 `ExportPackageBuildError`（不产出 zip）
- 来源返回 0 字节 ⇒ 同上
- 可选来源未接入 ⇒ 显式拒绝（不造假件）
- manifest 必带 `unit_policy.digest` 与每条文件的 `classification`
"""

from __future__ import annotations

import ast
import json
import re
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.export_package_service import (
    ExportPackageBuildError,
    ExportPackageService,
)

_SERVICE_PATH = Path(__file__).resolve().parents[1] / "app/services/export_package_service.py"
_SERVICE_SRC = _SERVICE_PATH.read_text(encoding="utf-8")

# 从源码里剔除注释与 docstring，只看**代码**（否则说明文字会被判成违规 ——
# 这正是「注释未剔除致误报」的现场）。
_AST = ast.parse(_SERVICE_SRC)


def _code_only() -> str:
    """把 AST 里所有字符串常量（docstring / 注释不含在 AST 里）保留，
    但去掉**注释**行后返回源码。"""
    return "\n".join(
        (line.split("#", 1)[0] if "#" in line else line)
        for line in _SERVICE_SRC.split("\n")
    )


class _FakeProject:
    def __init__(self):
        self.id = uuid4()
        self.name = "测试公司"
        self.client_name = "测试公司"
        self.template_type = "soe"
        self.report_scope = None
        self.wizard_state = {}


class _FakeDb:
    """最小 AsyncSession 替身：`execute()` 第一次回项目，后续回空。"""

    def __init__(self, project):
        self._project = project
        self.execute_count = 0

    async def execute(self, stmt, params=None):  # noqa: ANN001
        self.execute_count += 1
        project = self._project if self.execute_count == 1 else None

        class _R:
            def scalar_one_or_none(self_inner):  # noqa: N805
                return project

            def first(self_inner):  # noqa: N805
                return None

            def scalars(self_inner):  # noqa: N805
                class _S:
                    def all(self_s):  # noqa: N805
                        return []

                return _S()

        return _R()


def _gate_ok():
    """一致性门禁替身（恒通过），把焦点集中在「来源失败」这条判据上。"""

    class _Result:
        overall = "pass"
        has_blocking_failures = False
        checks: list = []

    class _Gate:
        def __init__(self, db):  # noqa: ANN001, ARG002
            pass

        async def run_all_checks(self, pid, year):  # noqa: ANN001, ARG002
            return _Result()

    class _Decision:
        blocks = False
        summary = "通过"

    return _Gate, (lambda result, consumer: _Decision())


# ---------------------------------------------------------------------------
# 1. 代码形态：不得再有 placeholder 字节 / 空 bytes 兜底
# ---------------------------------------------------------------------------


def test_no_placeholder_bytes_in_code():
    """源码的**代码部分**不得含 `b"Audit report placeholder"` 这类假件字节。"""
    code = _code_only()
    for needle in (
        'b"Audit report placeholder"',
        'b"Workpapers placeholder"',
        "b'Audit report placeholder'",
        "b'Workpapers placeholder'",
    ):
        assert needle not in code, f"发现 placeholder 字节: {needle}"


def test_no_empty_bytesio_fallback():
    """不得再有 `except → BytesIO(b"")` 的静默兜底。"""
    code = _code_only()
    assert 'BytesIO(b"")' not in code, "空 bytes 兜底会导致 zip 内出现 0 字节文件"


def test_no_placeholder_filename_constants():
    """占位符文件名常量也不该出现（`*年度审计报告*` 只有真件才允许写）。"""
    code = _code_only()
    # 改造后这两个文件名常量应已删除（改为显式拒绝）
    assert "audit_filename" not in code, "占位审计报告的文件名常量应已删除"
    assert "wp_filename" not in code, "占位审定表的文件名常量应已删除"


# ---------------------------------------------------------------------------
# 2. 行为：来源失败 / 空字节 ⇒ 整包失败
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_excel_failure_raises_not_empty_file():
    """Excel 生成抛错 ⇒ `ExportPackageBuildError`（不产出含 0 字节文件的 zip）。"""
    project = _FakeProject()
    db = _FakeDb(project)
    _Gate, _decision = _gate_ok()

    class _BoomExporter:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            raise RuntimeError("生成引擎炸了")

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _BoomExporter),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025
            )
    assert "财务报表生成失败" in str(exc.value)


@pytest.mark.anyio
async def test_excel_empty_bytes_raises():
    """Excel 返回 0 字节 ⇒ 同样整包失败（否则 zip 里有损坏文件）。"""
    project = _FakeProject()
    db = _FakeDb(project)
    _Gate, _decision = _gate_ok()

    class _EmptyExporter:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"")

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _EmptyExporter),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025
            )
    assert "0 字节" in str(exc.value)


@pytest.mark.anyio
async def test_word_failure_raises():
    """Word 附注生成抛错 ⇒ 整包失败。"""
    project = _FakeProject()
    db = _FakeDb(project)
    _Gate, _decision = _gate_ok()

    class _OkExcel:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"xlsx-bytes")

    class _BoomWord:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            raise RuntimeError("word 炸了")

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _BoomWord),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025
            )
    assert "附注 Word 生成失败" in str(exc.value)


@pytest.mark.anyio
@pytest.mark.parametrize("flag", ["include_audit_report", "include_workpapers"])
async def test_optional_sources_refuse_instead_of_placeholder(flag):
    """可选来源未接入 ⇒ **显式拒绝**而不是写 placeholder 字节。"""
    project = _FakeProject()
    db = _FakeDb(project)
    _Gate, _decision = _gate_ok()

    class _OkExcel:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"xlsx-bytes")

    class _OkWord:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"docx-bytes")

    kwargs = {flag: True}
    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _OkWord),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025, **kwargs
            )
    assert "placeholder" in str(exc.value)


@pytest.mark.anyio
async def test_policy_failure_raises():
    """单位策略快照取不到 ⇒ 整包失败（缺 policy 无法审计）。"""
    project = _FakeProject()
    db = _FakeDb(project)
    _Gate, _decision = _gate_ok()

    class _OkExcel:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"xlsx-bytes")

    class _OkWord:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"docx-bytes")

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _OkWord),
        patch(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            AsyncMock(side_effect=RuntimeError("policy 取不到")),
        ),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025
            )
    assert "单位策略快照构造失败" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. 正常路径：manifest 必须带 policy digest 与 classification
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_manifest_carries_policy_digest_and_classification():
    """manifest 必带 `unit_policy.digest`（AC-22）与每条文件的 `classification`。"""
    import zipfile

    project = _FakeProject()
    db = _FakeDb(project)
    _Gate, _decision = _gate_ok()

    class _OkExcel:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"xlsx-bytes-real")

    class _OkWord:
        def __init__(self, _db):  # noqa: ANN001
            pass

        async def export(self, **_kw):  # noqa: ANN003
            return BytesIO(b"docx-bytes-real")

    snapshot = json.dumps(
        {"unit": "wan", "divisor": 10000, "_digest": "a" * 64, "_project_id": str(project.id)}
    )

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _OkWord),
        patch(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            AsyncMock(return_value=snapshot),
        ),
    ):
        output = await ExportPackageService(db).export_package(
            project_id=project.id, year=2025
        )

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
        manifest = json.loads(zf.read("manifest.json"))

    # 无空文件
    with zipfile.ZipFile(output) as zf:
        for n in names:
            if n == "manifest.json":
                continue
            assert len(zf.read(n)) > 0, f"zip 内出现 0 字节文件: {n}"

    assert manifest["version"] == "1.1"
    assert manifest["unit_policy"]["digest"] == "a" * 64
    assert manifest["unit_policy"]["unit"] == "wan"
    assert manifest["unit_policy"]["divisor"] == 10000
    for entry in manifest["files"]:
        if entry["type"] in ("financial_statements", "notes_to_financial_statements"):
            assert entry["classification"] == "formal", entry
            assert entry["policy_digest"] == "a" * 64, entry


def test_no_placeholder_in_zip_manifest_types():
    """manifest 的文件类型里不得出现 `placeholder` 类条目。"""
    code = _code_only()
    assert not re.search(r'type"\s*:\s*"[a-z_]*placeholder', code)
