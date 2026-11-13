"""批 6.6 / recipe 5：归档包 hash 验证 + 篡改检测。

合并归档包最终经通用打包器 `archive_package_builder` 写出：每个入包项在 `manifest.json` 里记
`sha256`，整个 `manifest.json` 再算一个根 `manifest_hash`，整包文件算 `sha256`（`PackageResult`）。

本文件复用通用打包器的**生产 hash 原语**（`_Writer`（逐项 sha256）、`file_sha256`、manifest 根 hash
的构造方式与 `build_archive_package` 末尾逐字节一致），对一个真实 zip 做：

1. **逐项验证**：从 zip 读回每个入包项字节，重算 sha256，与 manifest 记录逐项相等。
2. **根 hash 验证**：重算 `manifest.json` 字节的 sha256，与 `PackageResult.manifest_hash` 相等；
   整包文件 sha256 与 `PackageResult.sha256` 相等。
3. **篡改文件**：改掉某入包项的字节 ⇒ 该项重算 sha256 与 manifest 不符（验证失败）。
4. **篡改 manifest hash**：改掉 manifest 里某项的 sha256 ⇒ 重算 `manifest_hash` 与原根 hash 不符。

合并链自身的 hash 验证（签字快照 `_hash` 可还原、artifact `sha256` 缺失即缺件、证据附件悬挂）
在 `test_workpaper_shell_and_archive.py` 的 TestArchiveProvider 篡改用例里已取证
（`test_corrupted_snapshot_hash_blocks_archive` / `test_missing_artifact...` / `test_dangling_evidence...`）。
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import tests.conftest  # noqa: F401
from app.services.archive_package_builder import _Writer, file_sha256


def _build_real_package(path: Path) -> tuple[str, str, list[dict]]:
    """用生产打包器的 _Writer + manifest 构造方式写一个真实 zip（与 build_archive_package 末尾一致）。

    返回 ``(file_sha256, manifest_hash, entries)``。
    """
    entries_items = [
        ("01-报表/合并报表.json", b'{"report": "consol"}', "report_excel"),
        ("11-底稿数据/A3-CONSOL.json", b'{"wp_code": "A3-CONSOL"}', "workpaper_data"),
        ("10-证据/evidence.pdf", b"%PDF-1.4 fake evidence bytes", "attachments"),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        w = _Writer(zf)
        for arcname, data, category in entries_items:
            w.add_bytes(arcname, data, category=category, source_id=arcname, label=arcname)
        manifest = {
            "project_id": "pid", "job_id": "jid",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "entries": w.entries, "skipped": [],
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    return file_sha256(path), manifest_hash, list(w.entries)


def _read_manifest(path: Path) -> dict:
    with zipfile.ZipFile(path, "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def _verify_entries(path: Path) -> list[str]:
    """逐项从 zip 读回字节重算 sha256，与 manifest 对比；返回不符项（空 = 全部通过）。"""
    manifest = _read_manifest(path)
    mismatches: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        for entry in manifest["entries"]:
            data = zf.read(entry["arcname"])
            if hashlib.sha256(data).hexdigest() != entry["sha256"]:
                mismatches.append(entry["arcname"])
    return mismatches


def test_per_item_sha256_and_root_hash_verify(tmp_path):
    """逐项 sha256 + 根 manifest_hash + 整包 sha256 全部验证通过。"""
    pkg = tmp_path / "consol-archive.zip"
    file_hash, manifest_hash, entries = _build_real_package(pkg)

    # 逐项 sha256 对得上
    assert _verify_entries(pkg) == []
    assert len(entries) == 3
    assert all(len(e["sha256"]) == 64 for e in entries)

    # 根 manifest_hash：重算 manifest.json 字节 sha256 == 记录的 manifest_hash
    with zipfile.ZipFile(pkg, "r") as zf:
        manifest_bytes = zf.read("manifest.json")
    assert hashlib.sha256(manifest_bytes).hexdigest() == manifest_hash

    # 整包文件 sha256 复算一致（PackageResult.sha256 的口径）
    assert file_sha256(pkg) == file_hash


def test_tampering_a_file_fails_per_item_verification(tmp_path):
    """篡改某入包项的字节 ⇒ 该项重算 sha256 与 manifest 不符（逐项验证检出）。"""
    pkg = tmp_path / "consol-archive.zip"
    _build_real_package(pkg)
    assert _verify_entries(pkg) == []  # 篡改前全通过

    # 重写 zip：把 evidence.pdf 的字节改掉，manifest 不动（模拟文件被动过）
    manifest = _read_manifest(pkg)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(pkg, "r") as src, zipfile.ZipFile(tampered, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "10-证据/evidence.pdf":
                data = b"%PDF-1.4 TAMPERED evidence bytes"  # 改内容，不改 manifest
            dst.writestr(name, data)

    mismatches = _verify_entries(tampered)
    assert "10-证据/evidence.pdf" in mismatches
    # manifest 里记录的 sha256 没变（证明是文件被改，不是 manifest 被改）
    assert _read_manifest(tampered)["entries"] == manifest["entries"]


def test_tampering_manifest_hash_is_detected(tmp_path):
    """篡改 manifest 里某项的 sha256 ⇒ 重算 manifest_hash 与原根 hash 不符（根 hash 验证检出）。"""
    pkg = tmp_path / "consol-archive.zip"
    _, original_manifest_hash, _ = _build_real_package(pkg)

    manifest = _read_manifest(pkg)
    # 篡改 manifest 里第一项的 sha256
    manifest["entries"][0]["sha256"] = "0" * 64
    tampered_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    recomputed = hashlib.sha256(tampered_bytes).hexdigest()

    assert recomputed != original_manifest_hash  # 根 hash 变了 ⇒ manifest 被动过


def test_removing_an_entry_changes_manifest_hash(tmp_path):
    """从 manifest 删掉一项 ⇒ 根 manifest_hash 变化（清单与文件集合不再闭合）。"""
    pkg = tmp_path / "consol-archive.zip"
    _, original_manifest_hash, _ = _build_real_package(pkg)
    manifest = _read_manifest(pkg)
    manifest["entries"] = manifest["entries"][:-1]  # 删最后一项
    shortened = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    assert hashlib.sha256(shortened).hexdigest() != original_manifest_hash
