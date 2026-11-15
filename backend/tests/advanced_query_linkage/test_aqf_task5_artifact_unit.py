"""查询证据封存的纯函数与降级路径（AQF 任务 5；SQLite / 无库，不连真 PG）。

真库端到端在 ``test_aqf_task5_artifact_pg.py``（P10-a~d + 清单端点 + 审计字段）。
本文件补的是**不依赖 PG** 的那几层，使「接线断了」在 SQLite 环境也能被看见：

1. 清单规范序列化往返：序列化 → 解析 → 再序列化**字节相同**（design §6.4）。
2. 说明页四行：`artifact_extra_info_rows` 的四个键与取值口径（R4.2）。
3. 证据目录与路径：`artifact_directory` / `artifact_path` / `partial_path` / `storage_key`
   在 `QUERY_ARTIFACT_ROOT` 下自洽，且 `.partial` 与最终文件同目录（跨盘 `os.replace` 会失败）。
4. 封存失败降级：证据根不可用时 `seal_artifact` 返回 `ok=False` 且**不抛**（ADR-AQF-06）。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from app.services.custom_query import query_artifacts as qa


def _manifest() -> dict:
    return qa._canonical_manifest(
        artifact_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        run_id="22222222-2222-2222-2222-222222222222",
        entry="business", origin="direct", template_id=None,
        project_id="33333333-3333-3333-3333-333333333333", project_name="【测试】项目",
        year=2025, source_key="ledger_entries", source_label="序时账",
        definition={"source": "ledger_entries"}, definition_hash="a" * 64,
        scope={"year": 2025}, version_vector={"components": [], "vector_hash": "b" * 64},
        vector_hash="b" * 64, vector_weak=False, captured_at="2026-11-15T00:00:00+00:00",
        columns=[{"key": "voucher_no", "title": "凭证号"}], row_count=3, warnings=[],
        info_rows=[["项目", "【测试】项目"]], file_name="证据.xlsx", byte_size=1024,
        sha256="c" * 64, generated_at="2026-11-15T00:00:01+00:00",
        user_id="44444444-4444-4444-4444-444444444444", username="tester",
    )


def test_storage_key_is_relative_to_the_artifact_root(tmp_path, monkeypatch):
    """`storage_key` 必须是**相对**证据根的键（不能是绝对路径）。

    2026-11-15 W3 走查实测：库里存的是 `D:\\GT_plan\\backend\\storage\\...\\x.xlsx`。
    根因是 `directory` 已 resolve 而 `_artifact_root()` 没 resolve，`relative_to` 抛
    `ValueError` 后走 except 分支写绝对路径 —— 既把服务器路径写进数据库，换证据根后旧记录全失效。
    """
    from app.core.config import settings

    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    aid = uuid.uuid4()
    directory = qa.artifact_directory(aid)
    key = qa.storage_key(directory, aid)
    assert not Path(key).is_absolute(), f"storage_key 是绝对路径：{key}"
    assert key == f"{directory.name}/{aid}.xlsx" or key.endswith(f"/{aid}.xlsx"), key
    # 反向：拿 key 拼回根目录，必须指到真实文件
    root = Path(settings.QUERY_ARTIFACT_ROOT)
    assert (root / key).resolve() == qa.artifact_path(directory, aid).resolve()


def test_manifest_canonical_roundtrip_is_byte_identical():
    """规范序列化往返：解析后再序列化，字节必须相同（否则清单摘要不可复算）。"""
    manifest = _manifest()
    once = qa.canonical_manifest_json(manifest)
    twice = qa.canonical_manifest_json(json.loads(once))
    assert once == twice
    # 键排序 + 紧凑分隔符 + 不转义中文，三条都是「规范」的组成部分
    assert once.startswith(b'{"artifact_id":')
    assert b'": ' not in once.replace(b'":"', b'')  # 没有 ", " 形式的空隙
    assert "【测试】项目".encode() in once
    assert qa.manifest_sha256(manifest) == qa.manifest_sha256(json.loads(once))


def test_extra_info_rows_has_the_four_required_keys():
    """说明页四行：查询编号 / 证据编号 / 数据版本 / 版本摘要（R4.2）。"""
    rows = qa.artifact_extra_info_rows(
        run_id="22222222-2222-2222-2222-222222222222",
        artifact_id="11111111-1111-1111-1111-111111111111",
        version_components=[
            {"label": "数据集", "digest": "abcdef1234567890"},
            {"label": "行版本", "digest": "0987654321fedcba"},
        ],
        vector_hash="b" * 64,
    )
    keys = [k for k, _v in rows]
    assert keys == ["查询编号", "证据编号", "数据版本", "版本摘要"]
    values = dict(rows)
    assert values["查询编号"] == "22222222-2222-2222-2222-222222222222"
    assert values["证据编号"] == "11111111-1111-1111-1111-111111111111"
    assert "数据集=abcdef12" in values["数据版本"]
    assert "行版本=09876543" in values["数据版本"]
    assert values["版本摘要"] == "b" * 16


def test_extra_info_rows_degrades_when_run_missing_and_no_version():
    """运行未登记 / 版本未采集时如实写「未记录」「—」，不抛异常（R1.6 降级方向）。"""
    rows = dict(qa.artifact_extra_info_rows(
        run_id=None, artifact_id="11111111-1111-1111-1111-111111111111",
        version_components=[], vector_hash="",
    ))
    assert rows["查询编号"] == "未记录"
    assert rows["数据版本"] == "（未采集）"
    assert rows["版本摘要"] == "—"


def test_partial_and_final_file_live_in_the_same_directory(tmp_path, monkeypatch):
    """`.partial` 与最终文件同目录 —— 跨盘 `os.replace` 在 Windows 上必失败（WinError 17）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", str(tmp_path / "evidence"))
    aid = uuid.uuid4()
    directory = qa.artifact_directory(aid)
    part = qa.partial_path(directory, aid)
    final = qa.artifact_path(directory, aid)
    assert part.parent == final.parent == directory
    assert final.name == f"{aid}.xlsx"
    assert part.name == f".{aid}.partial"
    # storage_key 相对证据根，能拼回最终文件
    key = qa.storage_key(directory, aid)
    assert not key.startswith(("/", "\\"))
    assert (tmp_path / "evidence" / key).resolve() == final.resolve()


async def test_seal_returns_failure_instead_of_raising_when_root_unusable(tmp_path, monkeypatch):
    """封存失败必须返回 `ok=False`（降级），不能抛 —— 否则导出整体 500（ADR-AQF-06）。"""
    from app.core.config import settings

    blocked = tmp_path / "not_a_dir"
    blocked.write_text("x", encoding="utf-8")
    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", str(blocked / "evidence"))

    result = await qa.seal_artifact(
        db=None, user=None, entry="business", project_id=None, year=None,
        source_key="ledger_entries", source_label="序时账",
        definition={}, definition_hash="a" * 64, scope={},
        version_vector={}, vector_hash="", vector_weak=False, captured_at=None, run_id=None,
        rows=[], columns=[], info_rows_base=[], file_name="x.xlsx",
        sheet_title=None,
    )
    assert result.ok is False
    assert result.status == "unavailable"
    assert result.reason, "降级时必须给出中文原因（审计要用）"


@pytest.mark.parametrize("bad", ["", None])
def test_artifact_root_falls_back_to_storage_root(bad, monkeypatch, tmp_path):
    """`QUERY_ARTIFACT_ROOT` 为空 ⇒ 派生自 `STORAGE_ROOT`（design §6.1）。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "QUERY_ARTIFACT_ROOT", bad)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path / "storage"))
    root = str(qa._artifact_root()).replace("\\", "/")
    assert root.endswith("storage/query_artifacts")


def test_stream_and_build_share_one_workbook_kernel():
    """`stream_xlsx` 与 `build_xlsx_file` 必须共用 `_build_workbook`（AQF §6.2）。

    design §6.2 要求「`stream_xlsx` 改为调用它且行为不变」。两份各自实现时，
    「容量守卫 / 行上限 / 说明页 / 附加页」任一处改动只生效一半 —— 这正是本仓
    反复踩过的「同一判据写两份，变异只改一份」缺陷形态。
    判据用 AST 取两个方法的函数体，不读源码文本（注释与 docstring 会骗过文本匹配）。
    """
    import ast
    import inspect

    from app.services.custom_query.export_service import ExportService

    tree = ast.parse(inspect.getsource(ExportService))
    calls: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
            "stream_xlsx", "build_xlsx_file",
        }:
            called = {
                sub.attr
                for sub in ast.walk(node)
                if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "self"
            }
            calls[node.name] = called

    assert set(calls) == {"stream_xlsx", "build_xlsx_file"}, f"AST 没解析到两个方法：{sorted(calls)}"
    for name in ("stream_xlsx", "build_xlsx_file"):
        assert "_build_workbook" in calls[name], (
            f"{name} 没有委托 `_build_workbook` —— 说明它又自己写了一遍建表逻辑"
        )
    # 反向自检：这两个方法都不该再自己建 Workbook（那正是重复实现的标志）
    for name in ("stream_xlsx", "build_xlsx_file"):
        assert "_header_cells" not in calls[name], (
            f"{name} 仍在直接调 `_header_cells`（建表细节应只在 `_build_workbook` 里）"
        )
