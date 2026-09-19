"""Unit tests for ZipAssembler / ZipReader.

验证 ZIP 组装与解析、manifest 完整性校验、大小上限、sha256 校验、
中文文件名支持。

Requirements: 1.4, 6.3, 6.5
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from app.services.bulk_tab.zip_handler import (
    DEFAULT_MAX_SINGLE_FILE_SIZE,
    DEFAULT_MAX_TOTAL_ZIP_SIZE,
    ZipAssembler,
    ZipIntegrityError,
    ZipManifestMissing,
    ZipReader,
    ZipSizeLimitExceeded,
    check_no_secrets,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_zip_bytes(
    files: dict[str, bytes],
    manifest: dict | None = None,
    readme: str | None = None,
) -> bytes:
    """快速构建一个合法 ZIP 字节流用于测试。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in files.items():
            zf.writestr(path, data)
        if manifest is not None:
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False).encode("utf-8"),
            )
        if readme is not None:
            zf.writestr("README.txt", readme.encode("utf-8"))
    return buf.getvalue()


def _build_manifest_with_files(
    files: dict[str, bytes],
) -> dict:
    """构建一个含 sha256 的 manifest dict。"""
    entries = []
    for path, data in files.items():
        entries.append(
            {
                "zip_path": path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "sheet_code": "TEST",
                "addr_id": "TEST/" + path,
            }
        )
    return {"schema_version": "1.0", "files": entries, "skipped": []}


# ---------------------------------------------------------------------------
# ZipAssembler Tests
# ---------------------------------------------------------------------------


class TestZipAssembler:
    """ZipAssembler 单元测试。"""

    def test_write_and_finalize_basic(self):
        """基本写入与 finalize 流程。"""
        assembler = ZipAssembler()
        data = b"hello world"
        sha = assembler.write("test.txt", data)

        assert sha == hashlib.sha256(data).hexdigest()
        assert "test.txt" in assembler.sha256_map

        result = assembler.finalize()
        assert isinstance(result, io.BytesIO)

        # 验证生成的 ZIP 可读
        with zipfile.ZipFile(result, "r") as zf:
            assert zf.read("test.txt") == data

    def test_write_chinese_filename(self):
        """中文文件名 UTF-8 支持。"""
        assembler = ZipAssembler()
        path = "D/D2/D2-2_明细表_模板.xlsx"
        data = b"\x50\x4b" + b"\x00" * 100  # 模拟 xlsx 头部

        sha = assembler.write(path, data)
        assert sha == hashlib.sha256(data).hexdigest()

        result = assembler.finalize()
        with zipfile.ZipFile(result, "r") as zf:
            assert path in zf.namelist()
            assert zf.read(path) == data

    def test_set_manifest(self):
        """set_manifest 序列化 JSON 到 ZIP。"""
        assembler = ZipAssembler()
        manifest = {"schema_version": "1.0", "project_id": "test-123"}
        assembler.set_manifest(manifest)

        result = assembler.finalize()
        with zipfile.ZipFile(result, "r") as zf:
            raw = zf.read("manifest.json")
            parsed = json.loads(raw.decode("utf-8"))
            assert parsed == manifest

    def test_set_readme(self):
        """set_readme 写入 README.txt。"""
        assembler = ZipAssembler()
        readme_text = "这是使用说明，含中文。"
        assembler.set_readme(readme_text)

        result = assembler.finalize()
        with zipfile.ZipFile(result, "r") as zf:
            raw = zf.read("README.txt")
            assert raw.decode("utf-8") == readme_text

    def test_sha256_map_excludes_manifest_readme(self):
        """sha256_map 只包含 write() 的文件，不含 manifest/README。"""
        assembler = ZipAssembler()
        assembler.write("data.xlsx", b"data")
        assembler.set_manifest({"test": True})
        assembler.set_readme("README")

        assert "data.xlsx" in assembler.sha256_map
        assert "manifest.json" not in assembler.sha256_map
        assert "README.txt" not in assembler.sha256_map

    def test_write_after_finalize_raises(self):
        """finalize 后再 write 应抛异常。"""
        assembler = ZipAssembler()
        assembler.finalize()

        with pytest.raises(RuntimeError, match="已 finalize"):
            assembler.write("late.txt", b"too late")

    def test_set_manifest_after_finalize_raises(self):
        """finalize 后再 set_manifest 应抛异常。"""
        assembler = ZipAssembler()
        assembler.finalize()

        with pytest.raises(RuntimeError, match="已 finalize"):
            assembler.set_manifest({"x": 1})

    def test_set_readme_after_finalize_raises(self):
        """finalize 后再 set_readme 应抛异常。"""
        assembler = ZipAssembler()
        assembler.finalize()

        with pytest.raises(RuntimeError, match="已 finalize"):
            assembler.set_readme("late")

    def test_double_finalize_raises(self):
        """重复 finalize 应抛异常。"""
        assembler = ZipAssembler()
        assembler.finalize()

        with pytest.raises(RuntimeError, match="不可重复"):
            assembler.finalize()

    def test_multiple_files(self):
        """多文件写入。"""
        assembler = ZipAssembler()
        files = {
            "D/D2/D2-1_审定表_模板.xlsx": b"file1",
            "D/D2/D2-2_明细表_模板.xlsx": b"file2",
            "D/D3/D3-1_审定表_模板.xlsx": b"file3",
        }
        for path, data in files.items():
            assembler.write(path, data)

        result = assembler.finalize()
        with zipfile.ZipFile(result, "r") as zf:
            for path, data in files.items():
                assert zf.read(path) == data

        assert len(assembler.sha256_map) == 3


# ---------------------------------------------------------------------------
# ZipReader Tests
# ---------------------------------------------------------------------------


class TestZipReader:
    """ZipReader 单元测试。"""

    def test_from_bytes_basic(self):
        """基础解析 + manifest 获取。"""
        manifest = {"schema_version": "1.0", "files": [], "skipped": []}
        zip_bytes = _make_zip_bytes({"data.xlsx": b"test"}, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        assert reader.manifest == manifest
        reader.close()

    def test_manifest_missing_raises(self):
        """缺少 manifest.json 时应抛 ZipManifestMissing。"""
        # 构建无 manifest 的 ZIP
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("data.xlsx", b"some data")
        zip_bytes = buf.getvalue()

        with pytest.raises(ZipManifestMissing):
            ZipReader.from_bytes(zip_bytes)

    def test_manifest_invalid_json_raises(self):
        """manifest.json 非法 JSON 时应抛 ZipManifestMissing。"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", b"not valid json {{{")
        zip_bytes = buf.getvalue()

        with pytest.raises(ZipManifestMissing, match="解析失败"):
            ZipReader.from_bytes(zip_bytes)

    def test_total_size_limit_compressed(self):
        """ZIP 压缩态字节超限时应抛 ZipSizeLimitExceeded。"""
        # 构建超限 ZIP（设置很小的上限）
        manifest = {"schema_version": "1.0", "files": []}
        zip_bytes = _make_zip_bytes({"big.bin": b"x" * 1000}, manifest=manifest)

        with pytest.raises(ZipSizeLimitExceeded):
            ZipReader.from_bytes(zip_bytes, max_total_zip_size=10)

    def test_total_size_limit_uncompressed(self):
        """ZIP 解压后总大小超限时应抛 ZipSizeLimitExceeded。"""
        manifest = {"schema_version": "1.0", "files": []}
        # 重复数据压缩率高，压缩后小但解压后大
        big_data = b"A" * 2000
        zip_bytes = _make_zip_bytes({"big.bin": big_data}, manifest=manifest)

        # 设置上限为 1000 bytes（解压后 big.bin=2000 + manifest > 1000）
        with pytest.raises(ZipSizeLimitExceeded, match="解压后总大小"):
            ZipReader.from_bytes(zip_bytes, max_total_zip_size=1000)

    def test_single_file_size_limit(self):
        """单文件超限时应抛 ZipSizeLimitExceeded。"""
        manifest = {"schema_version": "1.0", "files": []}
        big_data = b"B" * 5000
        zip_bytes = _make_zip_bytes({"big.bin": big_data}, manifest=manifest)

        with pytest.raises(ZipSizeLimitExceeded, match="单文件上限"):
            ZipReader.from_bytes(zip_bytes, max_single_file_size=1000)

    def test_get_file_existing(self):
        """get_file 提取存在的文件。"""
        data = b"xlsx content here"
        manifest = {"schema_version": "1.0", "files": []}
        zip_bytes = _make_zip_bytes({"D/D2/test.xlsx": data}, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        assert reader.get_file("D/D2/test.xlsx") == data
        reader.close()

    def test_get_file_not_found_raises(self):
        """get_file 文件不存在时抛 KeyError。"""
        manifest = {"schema_version": "1.0", "files": []}
        zip_bytes = _make_zip_bytes({"a.txt": b"a"}, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        with pytest.raises(KeyError, match="不存在"):
            reader.get_file("b.txt")
        reader.close()

    def test_list_files(self):
        """list_files 返回所有文件路径。"""
        manifest = {"schema_version": "1.0", "files": []}
        zip_bytes = _make_zip_bytes(
            {"a.xlsx": b"a", "b.xlsx": b"b"}, manifest=manifest
        )

        reader = ZipReader.from_bytes(zip_bytes)
        names = reader.list_files()
        assert "a.xlsx" in names
        assert "b.xlsx" in names
        assert "manifest.json" in names
        reader.close()

    def test_verify_integrity_pass(self):
        """sha256 校验通过时返回空列表。"""
        files = {"D/D2/test.xlsx": b"correct data"}
        manifest = _build_manifest_with_files(files)
        zip_bytes = _make_zip_bytes(files, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        result = reader.verify_integrity()
        assert result == []
        reader.close()

    def test_verify_integrity_sha_mismatch(self):
        """sha256 不匹配时应抛 ZipIntegrityError。"""
        files = {"D/D2/test.xlsx": b"correct data"}
        manifest = _build_manifest_with_files(files)
        # 篡改 sha256
        manifest["files"][0]["sha256"] = "0" * 64

        zip_bytes = _make_zip_bytes(files, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        with pytest.raises(ZipIntegrityError, match="sha256 不匹配"):
            reader.verify_integrity()
        reader.close()

    def test_verify_integrity_file_missing(self):
        """manifest 引用的文件不在 ZIP 中时应抛 ZipIntegrityError。"""
        manifest = {
            "schema_version": "1.0",
            "files": [
                {
                    "zip_path": "D/D2/missing.xlsx",
                    "sha256": "a" * 64,
                    "sheet_code": "D2-1",
                    "addr_id": "D2/D2-1/rows",
                }
            ],
        }
        zip_bytes = _make_zip_bytes({}, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        with pytest.raises(ZipIntegrityError, match="不存在"):
            reader.verify_integrity()
        reader.close()

    def test_verify_integrity_empty_sha_skipped(self):
        """sha256 为空的条目应被跳过（不校验）。"""
        manifest = {
            "schema_version": "1.0",
            "files": [
                {
                    "zip_path": "test.xlsx",
                    "sha256": "",  # 空 sha256 跳过
                    "sheet_code": "T1",
                }
            ],
        }
        zip_bytes = _make_zip_bytes({"test.xlsx": b"data"}, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        result = reader.verify_integrity()
        assert result == []
        reader.close()

    def test_chinese_filename_roundtrip(self):
        """中文文件名 ZIP 往返正确。"""
        path = "D/D2/D2-2_明细表_数据.xlsx"
        data = b"chinese filename data"
        manifest = _build_manifest_with_files({path: data})
        zip_bytes = _make_zip_bytes({path: data}, manifest=manifest)

        reader = ZipReader.from_bytes(zip_bytes)
        assert reader.get_file(path) == data
        result = reader.verify_integrity()
        assert result == []
        reader.close()

    def test_assembler_reader_roundtrip(self):
        """ZipAssembler 组装 → ZipReader 解析完整往返。"""
        # Assemble
        assembler = ZipAssembler()
        files = {
            "D/D2/D2-1_审定表_模板.xlsx": b"adjudication data",
            "D/D2/D2-2_明细表_数据.xlsx": b"detail data",
        }
        for path, data in files.items():
            assembler.write(path, data)

        manifest = {
            "schema_version": "1.0",
            "files": [
                {
                    "zip_path": path,
                    "sha256": assembler.sha256_map[path],
                    "sheet_code": path.split("/")[-1][:4],
                    "addr_id": f"TEST/{path}",
                }
                for path in files
            ],
            "skipped": [],
        }
        assembler.set_manifest(manifest)
        assembler.set_readme("测试 README")

        zip_bio = assembler.finalize()
        zip_bytes = zip_bio.getvalue()

        # Read
        reader = ZipReader.from_bytes(zip_bytes)
        assert reader.manifest["schema_version"] == "1.0"
        assert len(reader.manifest["files"]) == 2

        for path, data in files.items():
            assert reader.get_file(path) == data

        # Integrity
        result = reader.verify_integrity()
        assert result == []
        reader.close()


# ---------------------------------------------------------------------------
# check_no_secrets Tests
# ---------------------------------------------------------------------------


class TestCheckNoSecrets:
    """check_no_secrets 敏感信息检测测试。"""

    def test_clean_json_passes(self):
        """正常 JSON 不报错。"""
        data = json.dumps({"project_id": "test", "mode": "template"}).encode()
        check_no_secrets(data, "manifest.json")  # should not raise

    def test_bearer_token_detected(self):
        """Bearer token 应被检出。"""
        data = b'{"auth": "Bearer sk-xxxx-yyyy"}'
        with pytest.raises(ValueError, match="敏感信息模式"):
            check_no_secrets(data, "manifest.json")

    def test_private_key_detected(self):
        """私钥头部应被检出。"""
        data = b"-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        with pytest.raises(ValueError, match="敏感信息模式"):
            check_no_secrets(data, "config.txt")

    def test_binary_file_skipped(self):
        """xlsx 二进制文件不做检测。"""
        # 即使含 'Bearer ' 也不报错（因为 filename 非文本类）
        data = b"Bearer sk-secret inside binary"
        check_no_secrets(data, "data.xlsx")  # should not raise

    def test_aws_key_detected(self):
        """AWS secret key 应被检出。"""
        data = b"aws_secret_access_key = AKIAIOSFODNN7EXAMPLE"
        with pytest.raises(ValueError, match="敏感信息模式"):
            check_no_secrets(data, "config.txt")
