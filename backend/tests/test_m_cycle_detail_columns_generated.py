# -*- coding: utf-8 -*-
"""M 循环明细表列元数据守卫：生成文件必须与 provider 一致。

为什么需要：M3/M5/M7 原先的前端列是**手写**的，于是必然随模板演化而漂移
（M5 手写 6 列 vs 模板 17 列，交集 0）。现在列由生成器从 provider 导出，
本守卫钉住「生成文件 == provider 现算」，任何人手改生成文件或改 provider 忘了
重跑生成器，都在这里打红。

判据形态（与仓库既有约定一致）：
  * `--check` 退出码 0 = 一致；2 = 漂移。本守卫只断言退出码与输出内容。
  * 反向自检（`test_check_detects_a_hand_edit`）：真的手改一格必须让 `--check` 变红
    —— 否则「一致性判据」可能对任何改动都绿（恒绿门禁比没门禁更糟）。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_GEN = _ROOT / "backend" / "scripts" / "gen" / "generate_m_cycle_detail_columns.py"
_TARGET = (
    _ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "components"
    / "workpaper"
    / "m-cycle"
    / "mCycleDetailColumns.generated.ts"
)


def _run_check() -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(_GEN), "--check"],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def test_generated_columns_match_provider() -> None:
    """生成文件必须与 provider 现算一致（退出码 0 + 输出含 OK）。"""
    rc, out = _run_check()
    assert rc == 0, (
        f"M 循环列元数据生成文件与 provider 不一致（rc={rc}）。\n"
        f"修法：python backend/scripts/gen/generate_m_cycle_detail_columns.py\n"
        f"输出：{out.strip()[-600:]}"
    )
    # 只断言退出码是不够的：脚本可能因为别的异常以非 0 退出而在别的场景下
    # 又以 0 退出却没有真正比较。要求它明确报告比较通过。
    assert "OK" in out, f"`--check` 退出 0 但没有报告比较通过：{out.strip()[-400:]}"


def test_check_detects_a_hand_edit() -> None:
    """反向自检：手改生成文件一格，`--check` 必须变红（防恒绿判据）。"""
    if not _TARGET.exists():
        pytest.fail(f"生成文件不存在：{_TARGET}")
    original = _TARGET.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    try:
        text = original.decode("utf-8")
        needle = '"jsonKey": "priorOpening"'
        assert needle in text, "锚点不在生成文件里 —— 生成器结构变了，本守卫需同步"
        mutated = text.replace(needle, '"jsonKey": "priorOpeningMUTATED"', 1)
        assert mutated != text
        _TARGET.write_text(mutated, encoding="utf-8", newline="\n")
        rc, out = _run_check()
        assert rc == 2, (
            f"手改生成文件后 `--check` 仍通过（rc={rc}）—— 一致性判据失效。输出：{out.strip()[-400:]}"
        )
        assert "不一致" in out or "m-cycle-columns" in out, out
    finally:
        _TARGET.write_bytes(original)
        assert hashlib.sha256(_TARGET.read_bytes()).hexdigest() == sha, "生成文件未按字节还原"


def test_target_file_exists_and_is_generated() -> None:
    """生成文件存在且带「自动生成」标记（防有人把它换成手写文件）。"""
    assert _TARGET.exists()
    head = _TARGET.read_text(encoding="utf-8")[:400]
    assert "\u81ea\u52a8\u751f\u6210" in head, "生成文件头缺少「自动生成，勿手改」标记"
    assert "generate_m_cycle_detail_columns.py" in head, "生成文件头未指向生成器"
