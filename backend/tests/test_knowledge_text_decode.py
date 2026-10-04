"""知识库上传的纯函数：文本解码 / 类型规范化 / NUL 清洗 / 落盘名 / 失败原因

spec: knowledge-upload-robustness-and-consumer-wiring（Requirement 2 / 3，design §二 §三）
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from app.models.knowledge_models import (
    DOCUMENT_NAME_MAX_LEN,
    FILE_TYPE_MAX_LEN,
    KnowledgeDocument,
    KnowledgeFolder,
    normalize_file_type,
    strip_nul,
)
from app.services.knowledge_upload_service import (
    disk_file_name as _disk_file_name,
    upload_failure_reason as _upload_failure_reason,
)
from app.services.knowledge_folder_service import decode_text_bytes

ZH = "应收账款函证程序：发函、跟函、回函核对；坏账准备计提测试。"


# ─── decode_text_bytes ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "encoding",
    ["utf-8", "utf-8-sig", "utf-16", "gbk", "gb18030"],
)
def test_decode_roundtrip_common_encodings(encoding: str) -> None:
    assert decode_text_bytes(ZH.encode(encoding)) == ZH


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be"])
def test_decode_bomless_utf16_with_ascii(encoding: str) -> None:
    """无 BOM 的 UTF-16：ASCII 字符的 0 字节集中在同一奇偶位，可识别。"""
    text = "Account 1122 应收账款 balance 1000\nAccount 1231 坏账准备 balance -50\n"
    assert decode_text_bytes(text.encode(encoding)) == text


def test_decode_mostly_ascii_gbk_is_not_mistaken_for_utf8() -> None:
    """大半是数字的 GBK 表格：只有表头是中文，按替换符比例判会误留 UTF-8。"""
    text = "科目,金额\n" + "\n".join(f"{1000 + i},{i * 13.5}" for i in range(200))
    assert decode_text_bytes(text.encode("gbk")) == text


def test_decode_keeps_utf8_with_a_stray_bad_byte() -> None:
    """UTF-8 文本中混入 1 个坏字节：保留 UTF-8（整篇改判 GB18030 会把它放大成全文乱码）。"""
    data = ZH.encode("utf-8") + b"\xff" + ZH.encode("utf-8")
    out = decode_text_bytes(data)
    assert out.count(ZH) == 2 and out.count("\ufffd") == 1


@pytest.mark.parametrize(
    "text",
    [
        # 🔴 这一条是真库守卫抓到的：19 字节、1 个 NUL，只按比例判时一侧恰好 1/9 ≥ 10%
        # 被误判为 UTF-16。下一条多 4 个 ASCII 字符后比例不够，旧样本只写了它，侥幸通过。
        "前半段\x00后半段",
        "前半段\x00后半段 ABC",
        "\x00",
        "应收\x00账款\x00坏账",
    ],
)
def test_decode_sparse_nul_in_utf8_is_not_mistaken_for_utf16(text: str) -> None:
    assert decode_text_bytes(text.encode("utf-8")) == text


def test_decode_empty() -> None:
    assert decode_text_bytes(b"") == ""


@settings(max_examples=5, deadline=None)
@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=200))
def test_decode_utf8_is_lossless(text: str) -> None:
    """合法 UTF-8 永远原样解码（严格 UTF-8 是第一优先级的非 BOM 分支）。"""
    data = text.encode("utf-8")
    if data[:3] == b"\xef\xbb\xbf" or data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return  # 以 BOM 字节开头的文本按 BOM 分支处理，不在本性质范围
    if data.count(0) * 10 >= len(data) // 2:
        return  # 大量 NUL 的输入按 UTF-16 启发式处理，不在本性质范围
    assert decode_text_bytes(data) == text


# ─── normalize_file_type ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw, expected",
    [
        (".PDF", "pdf"),
        ("docx", "docx"),
        (" .Xlsx ", "xlsx"),
        ("tar.gz", None),  # 含点：不是单一扩展名
        ("final-reviewed-by-partner-v2", None),  # 超 20 字（2026-09-30 真库 500 的样本）
        ("a" * FILE_TYPE_MAX_LEN, "a" * FILE_TYPE_MAX_LEN),
        ("a" * (FILE_TYPE_MAX_LEN + 1), None),
        ("md\x00", "md"),
        ("中文", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_file_type(raw, expected) -> None:
    assert normalize_file_type(raw) == expected


def test_column_width_constants_match_orm() -> None:
    cols = KnowledgeDocument.__table__.c
    assert cols.file_type.type.length == FILE_TYPE_MAX_LEN
    assert cols.name.type.length == DOCUMENT_NAME_MAX_LEN


# ─── strip_nul + ORM validates ────────────────────────────────────────────────


def test_strip_nul_values() -> None:
    assert strip_nul("a\x00b") == "ab"
    assert strip_nul(["x\x00", 1, None]) == ["x", 1, None]
    assert strip_nul(None) is None and strip_nul(3) == 3


def test_orm_validators_clean_document_and_folder_fields() -> None:
    doc = KnowledgeDocument(
        name="名\x00称", content_text="正\x00文", content_summary="摘\x00要",
        tags=["t\x00"], file_type=".TXT", index_error="e\x00",
    )
    assert (doc.name, doc.content_text, doc.content_summary) == ("名称", "正文", "摘要")
    assert doc.tags == ["t"] and doc.file_type == "txt" and doc.index_error == "e"
    doc.content_text = "赋\x00值"  # 属性赋值同样经 validates（索引流水线回填正文走这条）
    assert doc.content_text == "赋值"
    folder = KnowledgeFolder(name="夹\x00", description="说\x00明")
    assert (folder.name, folder.description) == ("夹", "说明")


# ─── 落盘名 ───────────────────────────────────────────────────────────────────


def test_disk_file_name_is_unique_safe_and_byte_bounded() -> None:
    a, b = _disk_file_name("制度.txt"), _disk_file_name("制度.txt")
    assert a != b and a.endswith("_制度.txt") and b.endswith("_制度.txt")
    long_name = _disk_file_name("中" * 400 + ".xlsx")
    assert len(long_name.encode("utf-8")) <= 255 and long_name.endswith(".xlsx")
    unsafe = _disk_file_name('a:b<c>|d?e*"f.txt')
    assert not any(ch in unsafe[33:] for ch in '<>:"|?*') and unsafe.endswith(".txt")


# ─── 失败原因 ─────────────────────────────────────────────────────────────────


class _Orig:
    def __init__(self, sqlstate):
        self.sqlstate = sqlstate


class _DBError(Exception):
    def __init__(self, sqlstate):
        super().__init__("INSERT INTO knowledge_documents ... secret-path")
        self.orig = _Orig(sqlstate)


@pytest.mark.parametrize(
    "sqlstate, fragment",
    [("22001", "长度"), ("22021", "字符"), ("23505", "冲突"), ("XX000", "保存失败")],
)
def test_failure_reason_is_chinese_and_does_not_leak_sql(sqlstate, fragment) -> None:
    reason = _upload_failure_reason(_DBError(sqlstate))
    assert fragment in reason and "INSERT" not in reason and "secret" not in reason
    assert _upload_failure_reason(RuntimeError("boom")).startswith("保存失败")
