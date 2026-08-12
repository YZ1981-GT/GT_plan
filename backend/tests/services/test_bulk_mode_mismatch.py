"""模板↔数据错用校验守卫 —— Wave 4 Task 11
spec: workpaper-import-export-lifecycle-closure（R3.5）

## 缺陷本体

`manifest_builder` 早已把 `mode: "template"|"data"` 写进 `manifest.json`，但
`bulk_import_service` **只读 `files` 与 `cycles` 两个键，从不读 `mode`** ——
所以「拿场景①的空白模板包去场景③回传」这件事此前**完全无校验**。

后果不对称，这决定了错误文案必须说清后果：

| 错用方向 | 后果 |
|---|---|
| 空白模板包 → 覆盖已录入底稿 | **用空单元格清空数据，不可撤销** |
| 数据包 → 当模板填 | 把别人的数据当自己的底稿，属数据串项目 |

## 判据形态

- 纯函数 `validate_import_mode` 直测四态（相符 / 两种不符 / mode 缺失）
- **零写入**用真实执行证明：造一个 mode 不符的 ZIP 真跑 `run()`，
  断言 `SnapshotGuard` / `import_tab` 一次都没被调用
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.services.bulk_tab.scenario_registry import (
    ModeMismatch,
    importable_scenario_keys,
    validate_import_mode,
)


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 纯函数四态
# ═══════════════════════════════════════════════════════════════════════════


class TestValidateImportMode:
    def test_matching_mode_passes(self) -> None:
        assert validate_import_mode("template", "fill_back") is None
        assert validate_import_mode("data", "refresh_edit") is None

    def test_template_zip_into_data_scenario_rejected(self) -> None:
        """🔴 最危险的方向：空白模板包覆盖已录入底稿 = 清空数据。"""
        got = validate_import_mode("template", "refresh_edit")
        assert isinstance(got, ModeMismatch)
        assert got.manifest_mode == "template"
        assert got.expected_mode == "data"
        # 文案必须说清后果，不能只说"不匹配"
        assert "覆盖" in got.message
        assert "不可撤销" in got.message

    def test_data_zip_into_template_scenario_rejected(self) -> None:
        got = validate_import_mode("data", "fill_back")
        assert isinstance(got, ModeMismatch)
        assert got.manifest_mode == "data"
        assert got.expected_mode == "template"
        assert "数据" in got.message

    def test_missing_mode_is_fail_closed(self) -> None:
        """mode 缺失 ⇒ 不放行。无法判断包性质就不能写库。"""
        for bad in (None, "", "unknown"):
            got = validate_import_mode(bad, "refresh_edit")
            assert isinstance(got, ModeMismatch), f"mode={bad!r} 应被拒绝"

    def test_missing_mode_message_says_cannot_determine(self) -> None:
        got = validate_import_mode(None, "fill_back")
        assert isinstance(got, ModeMismatch)
        assert "缺少 mode" in got.message or "未标注" in got.message

    def test_message_includes_scenario_label_and_next_step(self) -> None:
        """可读错误 = 说清「所选场景 / 实际 ZIP / 后果 / 下一步」四件事。"""
        got = validate_import_mode("template", "refresh_edit")
        assert isinstance(got, ModeMismatch)
        for must in ("所选场景", "实际 ZIP", "请改用"):
            assert must in got.message, f"错误文案缺「{must}」: {got.message}"

    def test_unknown_scenario_raises(self) -> None:
        with pytest.raises(KeyError):
            validate_import_mode("data", "no_such_scenario")

    def test_export_only_scenario_raises(self) -> None:
        """拿纯导出场景校验导入属调用方逻辑错，必须抛而非静默放行。"""
        for key in ("blank_template", "archive_export"):
            with pytest.raises(ValueError):
                validate_import_mode("data", key)

    def test_importable_keys_are_the_two_expected(self) -> None:
        assert set(importable_scenario_keys()) == {"fill_back", "refresh_edit"}


# ═══════════════════════════════════════════════════════════════════════════
# 类 A —— 校验器自身出错时 fail-closed
# ═══════════════════════════════════════════════════════════════════════════


class TestCheckerFailClosed:
    def test_invalid_scenario_key_still_rejects(self) -> None:
        """🔴 校验器出错 ⇒ 仍拒绝导入。

        一个拼错的场景键若导致放行，整条 R3.5 防线静默失效
        （memory：fail-open 掩盖接线错误是最贵的一类）。
        """
        from app.services.bulk_tab.bulk_import_service import _check_manifest_mode

        got = _check_manifest_mode({"mode": "data"}, "typo_scenario")
        assert got is not None, "未知场景键必须拒绝而非放行"
        assert "无效" in got.message

    def test_export_only_scenario_still_rejects(self) -> None:
        from app.services.bulk_tab.bulk_import_service import _check_manifest_mode

        got = _check_manifest_mode({"mode": "data"}, "archive_export")
        assert got is not None, "不可回传的场景必须拒绝"

    def test_valid_call_passes_through(self) -> None:
        """反向自检：正常调用必须返 None，否则上面两条是恒真的。"""
        from app.services.bulk_tab.bulk_import_service import _check_manifest_mode

        assert _check_manifest_mode({"mode": "data"}, "refresh_edit") is None


# ═══════════════════════════════════════════════════════════════════════════
# 类 B —— 零写入（真实执行）
# ═══════════════════════════════════════════════════════════════════════════


def _make_zip(mode: str) -> bytes:
    """造一个 manifest 合法但 mode 为指定值的最小 ZIP。"""
    manifest = {
        "schema_version": "1.0",
        "project_id": "00000000-0000-0000-0000-000000000001",
        "audit_year": 2025,
        "exported_at": "2026-08-10T00:00:00+00:00",
        "exported_by": "t",
        "platform_version": "t",
        "mode": mode,
        "cycles": ["D"],
        "files": [],
        "skipped": [],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return buf.getvalue()


@pytest.mark.asyncio
class TestZeroWriteOnMismatch:
    async def test_run_rejects_before_any_snapshot_or_write(self, monkeypatch) -> None:
        """🔴 零写入判据：mode 不符时 `SnapshotGuard` 与 `import_tab` 都不得被调用。

        只断言"返回了失败报告"不够 —— 可能先写了一半才失败。
        故直接给两个副作用入口下探针，断言调用次数为 0。
        """
        from app.services.bulk_tab import bulk_import_service as svc

        calls: list[str] = []

        def _spy_snapshot(*_a, **_kw):
            calls.append("snapshot")
            raise AssertionError("mode 不符时不应创建快照")

        async def _spy_import_tab(*_a, **_kw):
            calls.append("import_tab")
            raise AssertionError("mode 不符时不应写入任何 sheet")

        monkeypatch.setattr(svc.SnapshotGuard, "__init__", _spy_snapshot, raising=False)
        monkeypatch.setattr(svc, "import_tab", _spy_import_tab, raising=False)

        report = await svc.run(
            db=None,  # 走不到 DB 就返回 ⇒ 传 None 即可证明零写入
            project_id="00000000-0000-0000-0000-000000000001",
            zip_bytes=_make_zip("template"),
            scenario="refresh_edit",
        )

        assert calls == [], f"发生了副作用调用: {calls}"
        assert report.dry_run is False
        failed = [s for s in report.sheets if s.status == "failed"]
        assert failed, "应产出失败条目"
        assert any(s.sheet_code == "__mode__" for s in failed), (
            f"失败原因未归到 __mode__: {[s.sheet_code for s in failed]}"
        )

    async def test_dry_run_also_reports_mismatch(self) -> None:
        """预检侧也要报 —— 否则用户点"预检通过"后才在正式导入时被拒。"""
        from app.services.bulk_tab import bulk_import_service as svc

        report = await svc.dry_run(
            db=None,
            project_id="00000000-0000-0000-0000-000000000001",
            zip_bytes=_make_zip("data"),
            scenario="fill_back",
        )
        assert report.dry_run is True
        assert any(s.sheet_code == "__mode__" for s in report.sheets)

    async def test_no_scenario_keeps_legacy_behaviour(self, monkeypatch) -> None:
        """`scenario=None`（既有调用方）必须完全跳过本校验。

        additive 保证：改造前的调用点一个字都没改，行为必须逐字相同。
        """
        from app.services.bulk_tab import bulk_import_service as svc

        report = await svc.dry_run(
            db=None,
            project_id="00000000-0000-0000-0000-000000000001",
            zip_bytes=_make_zip("template"),
            scenario=None,
        )
        # 不因 mode 被拒（会因后续步骤缺 DB 而失败，但不该是 __mode__）
        assert not any(s.sheet_code == "__mode__" for s in report.sheets)

    async def test_matching_mode_passes_mode_gate(self) -> None:
        """相符时必须**通过** mode 闸（后续因无 DB 失败与本闸无关）。

        反向自检：防「闸门恒拒」——那样零写入断言也会通过，但功能全废。
        """
        from app.services.bulk_tab import bulk_import_service as svc

        report = await svc.dry_run(
            db=None,
            project_id="00000000-0000-0000-0000-000000000001",
            zip_bytes=_make_zip("template"),
            scenario="fill_back",
        )
        assert not any(s.sheet_code == "__mode__" for s in report.sheets), (
            "mode 相符却被闸门拒绝 ⇒ 闸门恒拒，功能全废"
        )
