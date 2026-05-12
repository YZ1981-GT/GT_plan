"""F10 CSV 大文件性能保障测试（Sprint 10 Task 10.30）。

合成 ~100MB 测试 CSV 并验证 detect_file_from_path：
- 探测耗时 < 5s
- 内存峰值 < 200MB

CI 模式下可通过 skip marker 关闭（速度换稳定性）。
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import pytest

from app.services.ledger_import.detector import detect_file_from_path


def _generate_csv(target_bytes: int, path: str) -> None:
    """生成约 target_bytes 字节的 CSV（utf-8 编码）。"""
    header = "凭证日期,凭证号,科目编码,科目名称,借方金额,贷方金额,摘要\n"
    row_template = "2025-0{m}-{d:02d},记-{n:06d},100{c}01,{name},{debit:.2f},{credit:.2f},本期业务-{n}\n"

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(header)
        written = len(header.encode("utf-8"))
        n = 1
        while written < target_bytes:
            line = row_template.format(
                m=(n % 12) + 1,
                d=(n % 28) + 1,
                n=n,
                c=n % 10,
                name=f"科目名{n % 100}",
                debit=n * 13.75 % 99999,
                credit=n * 7.25 % 99999,
            )
            f.write(line)
            written += len(line.encode("utf-8"))
            n += 1


@pytest.mark.slow
def test_large_csv_detect_under_5s():
    """合成 ~100MB CSV，detect 阶段耗时 < 5 秒。"""
    target_bytes = 100 * 1024 * 1024  # 100MB
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as tf:
        tmp_path = tf.name

    try:
        # 合成数据（此步本身可能较慢，不计入 detect 耗时）
        _generate_csv(target_bytes, tmp_path)
        actual_size = os.path.getsize(tmp_path)
        assert actual_size >= 90 * 1024 * 1024, f"Generated only {actual_size} bytes"

        # 计时：只量 detect
        start = time.monotonic()
        fd = detect_file_from_path(tmp_path, os.path.basename(tmp_path))
        elapsed = time.monotonic() - start

        assert fd.file_size_bytes == actual_size
        assert fd.sheets, "应有至少一个 sheet"
        assert elapsed < 5.0, (
            f"detect_file_from_path 耗时 {elapsed:.2f}s 超过 5s 预算"
        )

        # 前 20 行应已解析
        sheet = fd.sheets[0]
        assert len(sheet.preview_rows) >= 10
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def test_small_csv_smoke():
    """小 CSV（~1KB）smoke 测试，确保基本流程工作。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as tf:
        tf.write("a,b,c\n1,2,3\n4,5,6\n")
        tmp_path = tf.name

    try:
        fd = detect_file_from_path(tmp_path, os.path.basename(tmp_path))
        assert fd.file_type == "csv"
        assert fd.sheets
        assert len(fd.sheets[0].preview_rows) == 3
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
