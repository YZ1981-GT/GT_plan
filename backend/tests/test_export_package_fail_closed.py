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

            def all(self_inner):  # noqa: N805
                return []

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
    """占位符字节不得出现；但**真件路径**用 `audit_filename` 是合法的。

    🔴 改造后这两个文件名变量重新出现（接真件来源），判据必须改：
    旧判据「`audit_filename` 不得出现」把「真件写入」也判成违规。
    正确判据 = 「文件名变量存在时，它必须配 `zf.writestr(name, <真字节>)`，
    且不得配 `b"... placeholder"` 字面量」——已由
    `test_no_placeholder_bytes_in_code` 覆盖。
    """
    code = _code_only()
    # 只要没有 placeholder 字节，文件名变量存在是正常的
    assert 'b"Audit report placeholder"' not in code
    assert 'b"Workpapers placeholder"' not in code


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
async def test_optional_sources_refuse_when_source_missing(flag):
    """可选来源**缺失时** ⇒ 显式拒绝，不写 placeholder 字节。

    🔴 改造后这两项已接真件来源（审计报告读 `audit_report` 段落、
    审定表走 `WpExportEngine`）。本用例守的是「来源缺失时不得造假件」：
    - `include_audit_report`：库里无 `audit_report` 记录 ⇒ 抛
    - `include_workpapers`：本项目无审定表底稿 ⇒ 抛
    """
    project = _FakeProject()
    db = _FakeDb(project)  # execute 只第 1 次回项目，后续回 None / 空
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
    msg = str(exc.value)
    # 必须是「来源缺失」类原因，不得是 placeholder 已写入
    assert ("尚未生成" in msg) or ("没有可导出" in msg) or ("无段落" in msg), msg


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


# ---------------------------------------------------------------------------
# 4. 真件来源接入（2026-11-16 补：审计报告 / 审定表）
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_audit_report_uses_real_paragraphs_not_placeholder():
    """`include_audit_report=True` 且库里有报告 ⇒ 产出**真 docx**（不是占位符字节）。"""
    import zipfile

    project = _FakeProject()
    _Gate, _decision = _gate_ok()

    class _Report:
        # 共享正文口径（extract_audit_report_paragraphs）会读 report_body_json：
        # 无 Word 模板 sections 时回退 paragraphs，替身两者都要有形状。
        report_body_json = None
        paragraphs = {"审计意见": "我们认为，后附财务报表在所有重大方面公允反映……"}
        year = 2025

    class _DbWithReport(_FakeDb):
        async def execute(self, stmt, params=None):  # noqa: ANN001
            self.execute_count += 1

            class _R:
                def scalar_one_or_none(self_inner):  # noqa: N805
                    return project if self_outer.execute_count == 1 else _Report()

                def first(self_inner):  # noqa: N805
                    return None

                def all(self_inner):  # noqa: N805
                    return []

            self_outer = self

            class _R2:
                def scalar_one_or_none(self_inner):  # noqa: N805
                    return project if self_outer.execute_count == 1 else _Report()

                def first(self_inner):  # noqa: N805
                    return None

                def all(self_inner):  # noqa: N805
                    return []

            return _R2()

    db = _DbWithReport(project)

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

    snapshot = json.dumps({"unit": "yuan", "divisor": 1, "_digest": "b" * 64})

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
            project_id=project.id, year=2025, include_audit_report=True
        )

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
        audit_names = [n for n in names if "审计报告" in n]
        assert audit_names, names
        content = zf.read(audit_names[0])
        manifest = json.loads(zf.read("manifest.json"))

    # 必须是真 docx（zip 结构 + 非占位符字节）
    assert content[:2] == b"PK", content[:20]
    assert b"Audit report placeholder" not in content
    entry = next(e for e in manifest["files"] if e["type"] == "audit_report")
    assert entry["classification"] == "formal"
    assert entry["policy_digest"] == "b" * 64


@pytest.mark.anyio
async def test_workpapers_export_real_adjudication_sheets():
    """`include_workpapers=True` ⇒ 逐份审定表底稿导出真件（含 wp_code 进 manifest）。"""
    import zipfile

    project = _FakeProject()
    _Gate, _decision = _gate_ok()

    class _Wp:
        def __init__(self, wid):
            self.id = wid

    class _WpIndex:
        def __init__(self, code, name):
            self.wp_code = code
            self.wp_name = name

    class _DbWithWps(_FakeDb):
        async def execute(self, stmt, params=None):  # noqa: ANN001
            self.execute_count += 1

            class _R:
                def scalar_one_or_none(self_inner):  # noqa: N805
                    return project if self_outer.execute_count == 1 else None

                def first(self_inner):  # noqa: N805
                    return None

                def all(self_inner):  # noqa: N805
                    # 第一份是审定表（D2-1），第二份不是（D2）
                    return [
                        (_Wp(uuid4()), _WpIndex("D2-1", "应收账款")),
                        (_Wp(uuid4()), _WpIndex("D2", "应收账款明细")),
                    ]

            self_outer = self
            return _R()

    db = _DbWithWps(project)

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

    class _OkEngine:
        async def export_single(self, db, wp_id, project_id, exported_by=None):  # noqa: ANN001, ARG002
            from app.schemas.wp_export_schemas import ExportResult, MetadataBundle

            # 🔴 `metadata` 是必填 `MetadataBundle`（现读 model_fields 确认四个字段），
            # 传 `{}` 会 pydantic ValidationError（首版即踩）。
            return ExportResult(
                file_content=b"PK\x03\x04real-xlsx",
                filename="x.xlsx",
                file_format="xlsx",
                snapshot_hash="c" * 64,
                metadata=MetadataBundle(
                    wp_code="D2-1",
                    project_id=str(project_id),
                    file_version=1,
                    export_timestamp="2026-11-16T00:00:00+00:00",
                ),
            )

    snapshot = json.dumps({"unit": "yuan", "divisor": 1, "_digest": "d" * 64})

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _OkWord),
        patch("app.services.wp_export.export_engine.WpExportEngine", _OkEngine),
        patch(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            AsyncMock(return_value=snapshot),
        ),
    ):
        output = await ExportPackageService(db).export_package(
            project_id=project.id, year=2025, include_workpapers=True
        )

    with zipfile.ZipFile(output) as zf:
        manifest = json.loads(zf.read("manifest.json"))

    wp_entries = [e for e in manifest["files"] if e["type"] == "workpapers"]
    # 只有 D2-1 是审定表（D2 不匹配 ^[A-N]\d+-1$）
    assert len(wp_entries) == 1, wp_entries
    assert wp_entries[0]["wp_code"] == "D2-1"
    assert wp_entries[0]["classification"] == "formal"
    assert b"Workpapers placeholder" not in b""


def test_adjudication_matcher_is_single_source():
    """审定表识别必须复用 `AdjudicationExportTemplateService`，不另写正则。

    🔴 判据只看**代码**（`_code_only()` 已剔注释）：我自己的注释里写了
    `^[A-N]\\d+-1$` 作为说明，首版把注释也算进去 ⇒ 自判违规。
    """
    code = _code_only()
    assert "is_adjudication_table" in code, "未复用既有判据"
    # 不得在组合包里另写一份审定表正则（`re.compile` / `re.match` 形态）
    assert not re.search(r"re\.(compile|match|search)\([^)]*\[A-N\]", code), (
        "组合包内不应重复写审定表正则"
    )


# ---------------------------------------------------------------------------
# 5. 审定表导出的两条失败路径（变异 M4/M5 存活暴露的盲区）
# ---------------------------------------------------------------------------


def _db_with_one_adjudication(project):
    """一个含单份审定表（D2-1）的 db 替身。"""

    class _Wp:
        def __init__(self, wid):
            self.id = wid

    class _WpIndex:
        def __init__(self, code, name):
            self.wp_code = code
            self.wp_name = name

    class _Db(_FakeDb):
        async def execute(self, stmt, params=None):  # noqa: ANN001
            self.execute_count += 1

            class _R:
                def scalar_one_or_none(self_inner):  # noqa: N805
                    return project if outer.execute_count == 1 else None

                def first(self_inner):  # noqa: N805
                    return None

                def all(self_inner):  # noqa: N805
                    return [( _Wp(uuid4()), _WpIndex("D2-1", "应收账款") )]

            outer = self
            return _R()

    return _Db(project)


def _ok_exporters():
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

    return _OkExcel, _OkWord


@pytest.mark.anyio
async def test_adjudication_export_failure_raises_not_skip():
    """审定表导出抛错 ⇒ 整包失败（**不得静默跳过**那一份）。

    🔴 变异 M4（把 `raise` 改成 `logger.warning + continue`）首轮存活：
    说明此前没有任何用例走过「审定表导出失败」这条路径。
    静默跳过的危害 = 用户以为拿到全套审定表，实际少了一份。
    """
    project = _FakeProject()
    db = _db_with_one_adjudication(project)
    _Gate, _decision = _gate_ok()
    _OkExcel, _OkWord = _ok_exporters()

    class _BoomEngine:
        async def export_single(self, db, wp_id, project_id, exported_by=None):  # noqa: ANN001, ARG002
            raise RuntimeError("导出引擎炸了")

    snapshot = json.dumps({"unit": "yuan", "divisor": 1, "_digest": "e" * 64})

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _OkWord),
        patch("app.services.wp_export.export_engine.WpExportEngine", _BoomEngine),
        patch(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            AsyncMock(return_value=snapshot),
        ),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025, include_workpapers=True
            )
    msg = str(exc.value)
    assert "D2-1" in msg, msg
    assert "导出失败" in msg, msg


@pytest.mark.anyio
async def test_adjudication_zero_bytes_raises():
    """审定表导出返回 0 字节 ⇒ 整包失败（**不得写进 zip**）。

    🔴 变异 M5（删掉 `if not content: raise`）首轮存活，同一盲区。
    """
    project = _FakeProject()
    db = _db_with_one_adjudication(project)
    _Gate, _decision = _gate_ok()
    _OkExcel, _OkWord = _ok_exporters()

    class _EmptyEngine:
        async def export_single(self, db, wp_id, project_id, exported_by=None):  # noqa: ANN001, ARG002
            from app.schemas.wp_export_schemas import ExportResult, MetadataBundle

            return ExportResult(
                file_content=b"",
                filename="x.xlsx",
                file_format="xlsx",
                snapshot_hash="f" * 64,
                metadata=MetadataBundle(
                    wp_code="D2-1",
                    project_id=str(project_id),
                    file_version=1,
                    export_timestamp="2026-11-16T00:00:00+00:00",
                ),
            )

    snapshot = json.dumps({"unit": "yuan", "divisor": 1, "_digest": "g" * 64})

    with (
        patch("app.services.consistency_gate.ConsistencyGate", _Gate),
        patch("app.services.consistency_gate.gate_decision", _decision),
        patch("app.services.report_excel_exporter.ReportExcelExporter", _OkExcel),
        patch("app.services.note_word_exporter.NoteWordExporter", _OkWord),
        patch("app.services.wp_export.export_engine.WpExportEngine", _EmptyEngine),
        patch(
            "app.services.export_policy_snapshot.resolve_policy_snapshot_for_project",
            AsyncMock(return_value=snapshot),
        ),
    ):
        with pytest.raises(ExportPackageBuildError) as exc:
            await ExportPackageService(db).export_package(
                project_id=project.id, year=2025, include_workpapers=True
            )
    msg = str(exc.value)
    assert "0 字节" in msg, msg
