"""模板索引全量投影、原子应用与 finder 缓存生命周期守卫。"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

from app.services import wp_template_finder as finder

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = BACKEND_ROOT / "scripts" / "ops" / "setup_wp_templates_dir.py"


def _load_setup_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_setup_wp_templates_dir_under_test", SETUP_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


setup = _load_setup_module()


def _write_template(root: Path, relative: str, content: bytes = b"template") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _write_index(path: Path, payload: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = setup.render_index(payload).encode("utf-8")
    path.write_bytes(raw)
    return raw


@pytest.fixture
def isolated_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "wp_templates"
    root.mkdir()
    index_file = root / "_index.json"
    monkeypatch.setattr(setup, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(setup, "TARGET_DIR", root)
    monkeypatch.setattr(setup, "INDEX_FILE", index_file)
    monkeypatch.setattr(setup, "SPECIAL_ENTRY_ROLES", {})
    return root, index_file


def test_default_check_mode_never_writes_index(
    isolated_runtime: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    root, index_file = isolated_runtime
    _write_template(root, "A/A1 新模板.xlsx")
    before = _write_index(
        index_file,
        {"description": "旧索引", "total_files": 0, "files": []},
    )

    assert setup.main([]) == 1
    assert index_file.read_bytes() == before
    output = capsys.readouterr().out
    assert "[DRIFT]" in output
    assert "--apply" in output


def test_full_projection_preserves_extension_slot_parent_code_and_roles(
    isolated_runtime: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _index_file = isolated_runtime
    old_relative = "A/A17-7 独立性声明.doc"
    replacement_relative = "A/A17-7 独立性声明.docx"
    old_entry = {
        "wp_code": "A17",
        "filename": Path(old_relative).name,
        "relative_path": old_relative,
        "format": "doc",
        "size_kb": 1.0,
        "category": "A-manual",
        "manual_marker": "keep",
    }
    paths = (
        replacement_relative,
        "A/A1-11 业务约定.xlsx",
        "D/D4-1至D4-4 营业收入-审定表.xlsx",
        "D/D4收入底稿.xlsx",
        "F/F2-1至F2-14 存货-审定表.xlsx",
        "F/F2存货.xlsx",
        "F/F2-22 存货监盘计划.docx",
        "F/F2-23 存货监盘小结.docx",
    )
    for sequence, relative in enumerate(paths, start=1):
        _write_template(root, relative, f"template-{sequence}".encode())

    roles = {
        "D/D4收入底稿.xlsx": "whole_workbook",
        "F/F2存货.xlsx": "whole_workbook",
        "F/F2-22 存货监盘计划.docx": "dedicated_subtemplate",
        "F/F2-23 存货监盘小结.docx": "dedicated_subtemplate",
    }
    monkeypatch.setattr(setup, "SPECIAL_ENTRY_ROLES", roles)
    payload = setup.build_index(
        template_root=root,
        existing_payload={"description": "旧索引", "files": [old_entry]},
    )

    entries = payload["files"]
    assert payload["total_files"] == len(paths)
    assert {entry["relative_path"] for entry in entries} == set(paths)
    assert entries[0]["relative_path"] == replacement_relative
    assert entries[0]["wp_code"] == "A17"
    assert entries[0]["category"] == "A-manual"
    assert entries[0]["manual_marker"] == "keep"

    by_path = {entry["relative_path"]: entry for entry in entries}
    assert by_path["A/A1-11 业务约定.xlsx"]["wp_code"] == "A1"
    assert by_path["F/F2-22 存货监盘计划.docx"]["wp_code"] == "F2"
    assert by_path["F/F2-23 存货监盘小结.docx"]["wp_code"] == "F2"
    assert {relative: by_path[relative].get("role") for relative in roles} == roles
    setup.validate_index(payload, template_root=root)


def test_validate_index_locks_both_projection_directions(
    isolated_runtime: tuple[Path, Path]
) -> None:
    root, _index_file = isolated_runtime
    _write_template(root, "A/A1 主模板.xlsx")
    _write_template(root, "B/B1 主模板.docx")
    payload = setup.build_index(template_root=root, existing_payload={"files": []})

    missing_disk_projection = copy.deepcopy(payload)
    missing_disk_projection["files"].pop()
    missing_disk_projection["total_files"] -= 1
    with pytest.raises(setup.TemplateIndexError, match="unexpected"):
        setup.validate_index(missing_disk_projection, template_root=root)

    ghost_index_projection = copy.deepcopy(payload)
    ghost_index_projection["files"].append(
        {
            "wp_code": "C1",
            "filename": "C1 幽灵模板.xlsx",
            "relative_path": "C/C1 幽灵模板.xlsx",
            "format": "xlsx",
            "size_kb": 1.0,
            "category": "C",
        }
    )
    ghost_index_projection["total_files"] += 1
    with pytest.raises(setup.TemplateIndexError, match="missing"):
        setup.validate_index(ghost_index_projection, template_root=root)


def test_source_missing_fails_before_apply_without_side_effect(
    isolated_runtime: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root, index_file = isolated_runtime
    _write_template(root, "A/A1 主模板.xlsx")
    before = _write_index(
        index_file,
        {"description": "不可改", "total_files": 0, "files": []},
    )
    monkeypatch.setattr(
        setup,
        "SOURCE_DIRS",
        {"A": (tmp_path / "missing-source",)},
    )

    assert setup.main(["--sync-from-source", "--apply"]) == 2
    assert index_file.read_bytes() == before
    assert tuple(root.rglob("*.xlsx")) == (root / "A" / "A1 主模板.xlsx",)


def test_apply_uses_atomic_replace_cas_and_is_idempotent(
    isolated_runtime: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, index_file = isolated_runtime
    _write_template(root, "A/A1 主模板.xlsx")
    _write_index(index_file, {"description": "旧索引", "total_files": 0, "files": []})

    original_replace = os.replace
    replacements: list[tuple[Path, Path]] = []

    def recording_replace(source: str | bytes | os.PathLike, target: str | bytes | os.PathLike) -> None:
        replacements.append((Path(source), Path(target)))
        original_replace(source, target)

    monkeypatch.setattr(setup.os, "replace", recording_replace)
    assert setup.main(["--apply"]) == 0
    assert replacements and replacements[-1][1] == index_file
    assert not tuple(index_file.parent.glob(f".{index_file.name}.*.tmp"))

    applied = index_file.read_bytes()
    assert setup.main(["--check"]) == 0
    assert setup.main(["--check"]) == 0
    assert index_file.read_bytes() == applied

    with pytest.raises(setup.TemplateIndexError, match="拒绝覆盖"):
        setup._atomic_write_index(
            index_file,
            applied.decode("utf-8"),
            expected_old_sha256="0" * 64,
        )
    assert index_file.read_bytes() == applied


def test_finder_role_separation_uses_index_as_single_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "wp_templates"
    bundle = _write_template(root, "F/F2-1至F2-14 存货-审定表.xlsx")
    whole = _write_template(root, "F/F2存货.xlsx")
    dedicated = _write_template(root, "F/F2-22 存货监盘计划.docx")
    entries = [
        {
            "wp_code": "F2",
            "filename": bundle.name,
            "relative_path": bundle.relative_to(root).as_posix(),
            "format": "xlsx",
            "size_kb": 0.0,
            "category": "D-N",
        },
        {
            "wp_code": "F2",
            "filename": whole.name,
            "relative_path": whole.relative_to(root).as_posix(),
            "format": "xlsx",
            "size_kb": 0.0,
            "category": "D-N",
            "role": "whole_workbook",
        },
        {
            "wp_code": "F2",
            "filename": dedicated.name,
            "relative_path": dedicated.relative_to(root).as_posix(),
            "format": "docx",
            "size_kb": 0.0,
            "category": "D-N",
            "role": "dedicated_subtemplate",
        },
    ]
    index_file = root / "_index.json"
    index_file.write_text(json.dumps({"files": entries}), encoding="utf-8")
    monkeypatch.setattr(finder, "TEMPLATES_DIR", root)
    monkeypatch.setattr(finder, "INDEX_FILE", index_file)
    monkeypatch.setattr(finder, "_index_cache", None)

    assert finder.find_all_template_files_unresolved("F2") == [bundle]
    assert finder.find_whole_workbook_template("F2") == whole
    assert finder.list_available_templates() == [
        {
            "wp_code": "F2",
            "filename": bundle.name,
            "format": "xlsx",
            "size_kb": 0.0,
        }
    ]


def test_finder_cache_reloads_same_size_atomic_replace_and_returns_copies(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "wp_templates"
    root.mkdir()
    index_file = root / "_index.json"

    def payload(filename: str) -> bytes:
        entry = {
            "wp_code": "A1",
            "filename": filename,
            "relative_path": f"A/{filename}",
            "format": "xlsx",
            "size_kb": 1.0,
            "category": "A",
        }
        return json.dumps({"files": [entry]}, ensure_ascii=False).encode("utf-8")

    first_raw = payload("A1-a.xlsx")
    second_raw = payload("A1-b.xlsx")
    assert len(first_raw) == len(second_raw)
    index_file.write_bytes(first_raw)
    original_stat = index_file.stat()

    monkeypatch.setattr(finder, "TEMPLATES_DIR", root)
    monkeypatch.setattr(finder, "INDEX_FILE", index_file)
    monkeypatch.setattr(finder, "_index_cache", None)

    first = finder._load_index()
    first[0]["filename"] = "被调用方篡改.xlsx"
    assert finder._load_index()[0]["filename"] == "A1-a.xlsx"

    replacement = root / ".same-size-index.tmp"
    replacement.write_bytes(second_raw)
    os.replace(replacement, index_file)
    os.utime(
        index_file,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    replaced_stat = index_file.stat()
    assert replaced_stat.st_size == original_stat.st_size
    assert replaced_stat.st_mtime_ns == original_stat.st_mtime_ns
    assert finder._load_index()[0]["filename"] == "A1-b.xlsx"
