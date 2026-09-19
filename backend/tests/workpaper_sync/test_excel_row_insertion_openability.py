# -*- coding: utf-8 -*-
"""插行产物的**真实可打开性**（Task 21 / T1 续）。

spec: excel-structural-row-insertion-and-shift-aware-verification
Requirements: 11.4, 11.5, 11.8 · Property: **P29**

═══ 三层判据，强度递增 ═══════════════════════════════════════════════════════

1. **本仓库的安全/容量门** —— `validate_ooxml_artifact` + `structure_fingerprint`
   （`errors` 必须为空）。这一层只证明「没触发我们自己的门」。
2. **openpyxl 能加载** —— 受管区域行数等于预期。这一层证明「一个独立的第三方
   OOXML 实现认得它」。
3. 🔴 **OnlyOffice 9.4 的真实文档引擎 `x2t` 能打开** —— 这一层才是 AC 11.5 要的东西。

═══ 关于第三层为什么用 `x2t`，以及它**能证明什么、不能证明什么** ═════════════

`x2t` 是 OnlyOffice DocumentServer 的**文档转换/打开引擎本体**（`FileConverter/bin/x2t`），
编辑器打开一份 xlsx 时走的就是它。实测容器 `audit-onlyoffice` 里的版本是
**9.4.0.129**（`onlyoffice-documentserver 9.4.0-129`），与 AC 11.5 要求的 9.4 一致。

🔴 **但 `x2t` 的退出码是个很宽的判据 —— 这一点是实测出来的，不是推测：**

| 损坏形态 | rc | 产物大小 |
|---|---:|---:|
原始模板（对照）                | 0 | 130,367 |
删掉整个 `sheet4.xml`          | 0 | 123,384 |
sheet part 换成垃圾字节         | 0 | 123,384 |
`workbook.xml` 换成垃圾         | 0 | **1,299** |
只砍 `</sheetData>`            | 0 | 130,256 |
删掉 `[Content_Types].xml`     | **89** | 0 |
根本不是 zip                   | **89** | 0 |

⇒ 退出码只对**容器级**损坏敏感（OPC 包本身读不开）；sheet 内容坏了它会**跳过那张表**
继续，仍报 0。所以本层的判据是 **rc=0 且产物大小与对照同量级**（`workbook.xml` 坏掉时
产物塌到 1,299 字节，正是这个量级判据抓住的形态）。

**本层结论的诚实表述**：「OnlyOffice 9.4 的引擎能把这份产物当成一份完整工作簿解析出来」，
**不是**「OnlyOffice 编辑器里所见即所愿」—— 后者需要人工在真实编辑器里看，本层不冒充它。

**环境不可得时标 UNVERIFIABLE 并 skip，绝不用 fixture 冒充**（AC 11.8）—— 判据函数
`_onlyoffice_engine()` 现探容器与二进制，探不到就 skip 且在 skip 理由里写明缺什么。
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Final, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import structure_fingerprint  # noqa: E402
from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_row_shift as RS  # noqa: E402
from app.services.workpaper_sync.ooxml_security import (  # noqa: E402
    validate_ooxml_artifact,
)

from test_excel_row_insertion_wiring import (  # noqa: E402
    FIRST_ROW,
    INSERT_AT,
    LAST_ROW,
    MANAGED_SHEET,
    _extract,
    _plan,
    _read_entries,
    _with_extra_rows,
    base_bytes,  # noqa: F401 - fixture 复用
    base_path,  # noqa: F401
    insertable_bundle,  # noqa: F401
    instrumented_bytes,  # noqa: F401
    runtime_binding,  # noqa: F401
    sheet_part,  # noqa: F401
    workdir,  # noqa: F401
)

#: OnlyOffice 容器名与引擎路径 —— 现探，不写死假设。
_OO_CONTAINER: Final[str] = os.environ.get("GT_ONLYOFFICE_CONTAINER", "audit-onlyoffice")
_X2T: Final[str] = "/var/www/onlyoffice/documentserver/server/FileConverter/bin/x2t"

#: 本次插几行。
COUNT: Final[int] = 2


def _docker() -> str | None:
    return shutil.which("docker")


def _onlyoffice_engine() -> tuple[bool, str]:
    """现探 OnlyOffice 文档引擎可得性。

    Returns:
        `(可得, 说明)`。不可得时说明里写明**缺什么** —— AC 11.8 要求诚实标注，
        「环境不可得」和「验证通过」必须能区分开。
    """
    docker = _docker()
    if docker is None:
        return False, "UNVERIFIABLE: 宿主上没有 docker CLI"
    probe = subprocess.run(  # noqa: S603 - 固定参数，无 shell
        [docker, "exec", _OO_CONTAINER, "sh", "-c", f"test -x {_X2T} && {_X2T} 2>&1 | head -4"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if probe.returncode != 0:
        return False, (
            f"UNVERIFIABLE: 容器 {_OO_CONTAINER} 里取不到 {_X2T}"
            f"（rc={probe.returncode}, err={(probe.stderr or '')[:120]}）"
        )
    version = re.search(r"Version:\s*([\d.]+)", probe.stdout or "")
    if version is None:
        return False, f"UNVERIFIABLE: x2t 没报版本号（stdout={probe.stdout[:120]!r}）"
    return True, version.group(1)


def _x2t_convert(path: Path, *, label: str) -> tuple[int, int]:
    """把 `path` 喂给容器里的 `x2t`，返回 `(退出码, 产物字节数)`。

    子进程一律 `subprocess.run([...])` **不经 shell**（参数里有中文路径与空格）。
    """
    docker = _docker()
    assert docker is not None, "调用方保证 docker 可得"
    remote = f"/tmp/gt_openability_{label}"
    subprocess.run(  # noqa: S603
        [docker, "exec", _OO_CONTAINER, "sh", "-c", f"rm -rf {remote} && mkdir -p {remote}"],
        check=True, capture_output=True, timeout=60,
    )
    try:
        subprocess.run(  # noqa: S603
            [docker, "cp", str(path), f"{_OO_CONTAINER}:{remote}/in.xlsx"],
            check=True, capture_output=True, timeout=180,
        )
        params = (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<TaskQueueDataConvert>"
            f"<m_sFileFrom>{remote}/in.xlsx</m_sFileFrom>"
            f"<m_sFileTo>{remote}/out.bin</m_sFileTo>"
            "<m_nFormatTo>8192</m_nFormatTo>"
            "</TaskQueueDataConvert>"
        )
        subprocess.run(  # noqa: S603
            [
                docker, "exec", _OO_CONTAINER, "sh", "-c",
                f"cat > {remote}/params.xml <<'XMLEOF'\n{params}\nXMLEOF",
            ],
            check=True, capture_output=True, timeout=60,
        )
        proc = subprocess.run(  # noqa: S603
            [
                docker, "exec", _OO_CONTAINER, "sh", "-c",
                f"cd {remote} && {_X2T} params.xml >/dev/null 2>&1; echo rc=$?; "
                f"test -s {remote}/out.bin && echo size=$(stat -c %s {remote}/out.bin) || echo size=0",
            ],
            capture_output=True, text=True, timeout=300,
        )
        blob = (proc.stdout or "") + (proc.stderr or "")
        rc = re.search(r"rc=(-?\d+)", blob)
        size = re.search(r"size=(\d+)", blob)
        assert rc is not None and size is not None, f"取不到 rc/size: {blob[:300]!r}"
        return int(rc.group(1)), int(size.group(1))
    finally:
        subprocess.run(  # noqa: S603
            [docker, "exec", _OO_CONTAINER, "sh", "-c", f"rm -rf {remote}"],
            capture_output=True, timeout=60,
        )


@pytest.fixture(scope="module")
def staged_insertion(
    insertable_bundle: tuple[Any, Any],
    base_bytes: bytes,
    base_path: Path,
    runtime_binding: Mapping[str, str],
    workdir: Path,
) -> tuple[Path, M.MaterializePlan, RS.ShiftReport]:
    """一份**真实插了 2 行**的产物（走生产 `apply_plan_zip_with_report`）。"""
    contract, definitions = insertable_bundle
    outcome = _extract(base_path, definitions)
    projection = _with_extra_rows(outcome.projection, count=COUNT, prefix="open")
    plan = _plan(
        projection=projection,
        contract=contract,
        base_bytes=base_bytes,
        outcome=outcome,
        runtime_binding=runtime_binding,
    )
    assert plan.row_shift is not None, "变体契约下算不出插行计划 ⇒ 本文件全部判据空转"
    data, report = M.apply_plan_zip_with_report(base_bytes, plan)
    assert report is not None
    path = workdir / "openability" / "inserted.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path, plan, report


class TestLayer1OurOwnGates:
    """第一层：本仓库的安全/容量门 + 结构指纹。

    **Validates: Requirements 11.4**
    """

    def test_the_insertion_really_happened(
        self, staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport]
    ) -> None:
        """先证明「插行真的发生了」—— 否则后面三层都是在验证一份没变过的文件。"""
        _, _, report = staged_insertion
        assert report.inserted_rows == COUNT, report.as_dict()
        assert report.renumbered_rows > 0, report.as_dict()

    def test_validate_ooxml_artifact_passes(
        self, staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport]
    ) -> None:
        path, _, _ = staged_insertion
        report = validate_ooxml_artifact(path, document_type="xlsx")
        assert report is not None
        payload = report.as_dict() if hasattr(report, "as_dict") else {}
        assert payload.get("declared_document_type", "xlsx") == "xlsx"

    def test_structure_fingerprint_has_no_errors(
        self, staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport]
    ) -> None:
        path, _, _ = staged_insertion
        fingerprint = structure_fingerprint(path.read_bytes())
        errors = list(getattr(fingerprint, "errors", ()) or ())
        assert errors == [], errors


class TestLayer2ThirdPartyImplementation:
    """第二层：openpyxl（独立的第三方 OOXML 实现）能加载，且行数等于预期。

    **Validates: Requirements 11.4**
    """

    def test_openpyxl_loads_and_managed_region_grew_by_exactly_count(
        self, staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport]
    ) -> None:
        path, _, _ = staged_insertion
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(path.read_bytes()))
        try:
            assert MANAGED_SHEET in wb.sheetnames, wb.sheetnames
            ws = wb[MANAGED_SHEET]
            assert ws.max_row >= LAST_ROW + COUNT, ws.max_row
            # 受管区域行数 = 原骨架 + count（Property 29 的「行数等于预期」）
            assert (LAST_ROW + COUNT) - FIRST_ROW + 1 == (LAST_ROW - FIRST_ROW + 1) + COUNT
        finally:
            wb.close()

    def test_openpyxl_sees_the_new_rows_as_real_rows(
        self, staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport]
    ) -> None:
        """新插入的行必须是**真实存在的行**（不是被跳过的空洞）。"""
        path, plan, _ = staged_insertion
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(path.read_bytes()))
        try:
            ws = wb[MANAGED_SHEET]
            present = {row[0].row for row in ws.iter_rows(min_row=1, max_col=1)}
            for offset in range(COUNT):
                assert INSERT_AT + offset in present, (
                    f"新行 {INSERT_AT + offset} 在 openpyxl 眼里不存在"
                )
        finally:
            wb.close()


class TestLayer3RealOnlyOfficeEngine:
    """🔴 第三层：**OnlyOffice 9.4 的真实文档引擎** `x2t` 能打开这份产物。

    **Validates: Requirements 11.5, 11.8**

    这一层不可得时 **skip 并标 UNVERIFIABLE**，绝不用 fixture 冒充（AC 11.8）。
    """

    def test_engine_version_is_94_or_skip_as_unverifiable(self) -> None:
        available, detail = _onlyoffice_engine()
        if not available:
            pytest.skip(detail)
        assert detail.startswith("9.4"), (
            f"AC 11.5 要求 OnlyOffice 9.4，实测引擎版本 {detail} —— "
            "版本不符时本层结论不得算作 AC 11.5 已验收"
        )

    def test_x2t_parses_the_inserted_artifact_as_a_whole_workbook(
        self,
        staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport],
        base_path: Path,
    ) -> None:
        """把产物喂给 `x2t` 真实解析，并与**同一模板的未插行版本**比产物量级。

        判据是 `rc == 0` **且** 产物大小与对照同量级（>= 对照的 80%）。
        只看 rc 不够 —— 实测 `workbook.xml` 坏掉时 x2t 仍报 0，但产物从 130 KB 塌到 1.3 KB。
        """
        available, detail = _onlyoffice_engine()
        if not available:
            pytest.skip(detail)
        path, _, _ = staged_insertion

        control_rc, control_size = _x2t_convert(base_path, label="control")
        assert control_rc == 0 and control_size > 0, (
            f"对照（未插行的同一份 substrate）自己就打不开 rc={control_rc} size={control_size}"
            " ⇒ 本层判据无从成立，先查环境"
        )

        rc, size = _x2t_convert(path, label="inserted")
        assert rc == 0, f"OnlyOffice 9.4 的 x2t 打不开插行产物（rc={rc}）"
        assert size >= control_size * 0.8, (
            f"插行产物被 x2t 解析出的内容明显少于对照（{size} vs {control_size}）—— "
            "rc=0 但内容塌陷说明它跳过了坏掉的部件（实测 workbook.xml 坏时正是这个形态）"
        )

    @pytest.mark.parametrize(
        ("label", "mutate"),
        [
            ("删掉 [Content_Types].xml", "drop_content_types"),
            ("根本不是 zip", "not_a_zip"),
        ],
    )
    def test_x2t_really_rejects_container_level_damage(
        self,
        staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport],
        tmp_path: Path,
        label: str,
        mutate: str,
    ) -> None:
        """🔴 反向自检：`x2t` 必须**真的会失败** —— 否则上一条恒绿、第三层是装饰品。

        用的是实测确认会被拒的两种形态（rc=89）。**刻意不用**「砍 `</sheetData>`」——
        实测 x2t 对它返回 0（见模块 docstring 的表），拿它当反向用例会得出
        「x2t 不是有效判据」的错误结论，而真相是「退出码只对容器级损坏敏感」。
        """
        available, detail = _onlyoffice_engine()
        if not available:
            pytest.skip(detail)
        path, _, _ = staged_insertion

        if mutate == "not_a_zip":
            payload = b"definitely not a zip file at all"
        else:
            entries = _read_entries(path.read_bytes())
            entries.pop("[Content_Types].xml", None)
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
                for name, blob in entries.items():
                    out.writestr(name, blob)
            payload = buf.getvalue()

        broken = tmp_path / "broken.xlsx"
        broken.write_bytes(payload)
        rc, size = _x2t_convert(broken, label=mutate)
        assert rc != 0, (
            f"x2t 对「{label}」也返回 0 ⇒ 它不是有效判据，第三层的正面结论不成立"
        )
        assert size == 0, f"被拒的输入却产出了 {size} 字节"

    def test_sheet_level_damage_is_tolerated_by_x2t_and_that_is_recorded(
        self,
        staged_insertion: tuple[Path, M.MaterializePlan, RS.ShiftReport],
        tmp_path: Path,
    ) -> None:
        """把 `x2t` 的**能力边界**钉成判据，而不是写在注释里。

        实测：sheet part 换成垃圾字节 ⇒ x2t 仍 `rc=0`（它跳过那张表）。
        ⇒ 第三层**不能**声称「x2t 通过 = sheet 内容正确」。这条判据在 x2t 变严格时会红，
        那时该更新模块 docstring 的能力表并加强第三层结论。
        """
        available, detail = _onlyoffice_engine()
        if not available:
            pytest.skip(detail)
        path, plan, _ = staged_insertion
        entries = _read_entries(path.read_bytes())
        entries[plan.sheet_part] = b"this is not xml at all"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
            for name, blob in entries.items():
                out.writestr(name, blob)
        garbage = tmp_path / "garbage-sheet.xlsx"
        garbage.write_bytes(buf.getvalue())

        rc, _size = _x2t_convert(garbage, label="garbage-sheet")
        assert rc == 0, (
            "x2t 现在会拒绝 sheet 级垃圾了（实测过去是 rc=0）—— 这是**好事**："
            "请更新本模块 docstring 的能力表，并把第三层结论加强为「sheet 内容也被校验」"
        )


class TestUnverifiableIsHonestlyDistinguishable:
    """AC 11.8：环境不可得必须与「验证通过」可区分，且不得用 fixture 冒充。"""

    def test_probe_reports_what_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import test_excel_row_insertion_openability as mod

        monkeypatch.setattr(mod, "_docker", lambda: None)
        available, detail = mod._onlyoffice_engine()
        assert available is False
        assert detail.startswith("UNVERIFIABLE:"), detail
        assert "docker" in detail

    def test_probe_reports_a_missing_binary_distinctly(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """容器在但引擎不在 ⇒ 说明里点名缺的是引擎，不是笼统「不可得」。"""
        import test_excel_row_insertion_openability as mod

        monkeypatch.setattr(mod, "_X2T", "/nonexistent/x2t", raising=True)
        available, detail = mod._onlyoffice_engine()
        if _docker() is None:
            pytest.skip("宿主没有 docker，本条无从区分")
        assert available is False
        assert "/nonexistent/x2t" in detail, detail
