# -*- coding: utf-8 -*-
"""两条脚本级安全不变量的防复发守卫（2026-09-30）。

两个缺陷形态不同，但**失效方式是同一个**：出问题的是「本应什么都不做」和「本应把话说完」
这类边缘路径，而既有测试只走主路径，所以都长期无人发现。

1. ``fix_note_m_equity_structure.py --dry-run`` **必须一个字节都不写**。
   实测原代码有**两处**写盘只判了 ``not check``（新建 `八、94` 整章 / 删 header_label 假行），
   ``--dry-run`` 照样落盘 —— 干跑本是「决定要不要改」之前的安全动作，它写盘等于把这个
   安全保证反过来用。

2. ``check_staged_tree_self_consistency.py`` 的**失败**报文在 GBK 控制台下必须能打完。
   成功分支的 `✅`(U+2705) 恰好能被 GBK 编码、失败分支的 `❌`(U+274C) 不能 ⇒ 判红时
   在打印诊断那一行 ``UnicodeEncodeError`` ⇒ 整份诊断丢失，pre-push 只剩一句失败。

两条都配**反向断言**：证明被测那条写盘路径/崩溃条件真的可达，否则「没写盘」「没崩」
会是空转得来的假绿。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
FIX_DIR = BACKEND / "scripts" / "fix"
GATE = BACKEND / "scripts" / "check" / "check_staged_tree_self_consistency.py"
DATA = BACKEND / "data"

if str(FIX_DIR) not in sys.path:
    sys.path.insert(0, str(FIX_DIR))


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """把两份模板复制到 tmp 并让脚本模块指向副本，再摘掉 soe `八、94`。

    摘掉 `八、94` 是为了让 ``_ensure_soe_m8_section()`` 这条**写盘路径真的可达** ——
    真实模板现已对齐，直接跑 dry-run 会 0 变更，那样「没写盘」是空转结论。
    """
    import fix_note_m_equity_structure as M

    soe = tmp_path / "note_template_soe.json"
    listed = tmp_path / "note_template_listed.json"
    soe.write_bytes((DATA / "note_template_soe.json").read_bytes())
    listed.write_bytes((DATA / "note_template_listed.json").read_bytes())

    doc = json.loads(soe.read_text(encoding="utf-8"))
    before = len(doc["sections"])
    doc["sections"] = [
        s
        for s in doc["sections"]
        if (s.get("section_number") or "").replace(" ", "") != "八、94"
    ]
    assert len(doc["sections"]) == before - 1, "未摘到 soe 八、94，沙箱前提不成立"
    soe.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(M, "SOE", soe)
    monkeypatch.setattr(M, "LISTED", listed)
    remapped = {
        key: (num, soe if path.name.endswith("soe.json") else listed, plan)
        for key, (num, path, plan) in M.SECTIONS.items()
    }
    monkeypatch.setattr(M, "SECTIONS", remapped)
    return M, soe, listed


class TestDryRunWritesNothing:
    """``--dry-run`` 不得落盘（含 `八、94` 建章与 header_label 删行两条路径）。"""

    def test_dry_run_leaves_files_byte_identical(self, sandbox) -> None:
        M, soe, listed = sandbox
        before = {soe: _sha(soe), listed: _sha(listed)}

        M._run("soe-m8-94", dry_run=True, check=False)

        for path, digest in before.items():
            assert _sha(path) == digest, (
                f"--dry-run 改写了 {path.name} —— 干跑必须零字节写入"
            )

    def test_write_path_is_actually_reachable(self, sandbox) -> None:
        """反向断言：同一入参在**写模式**下必须真的改文件。

        否则上一条的「没写盘」可能只是因为这条路径根本没被走到（空转假绿）。
        """
        M, soe, _listed = sandbox
        assert not M._soe_m8_section_exists(), "沙箱里 八、94 应当不存在"
        before = _sha(soe)

        M._run("soe-m8-94", dry_run=False, check=False)

        assert _sha(soe) != before, (
            "写模式没有改动 soe 模板 ⇒ 建章路径不可达，dry-run 的「未写盘」结论无意义"
        )
        assert M._soe_m8_section_exists(), "写模式后 八、94 仍不存在"

    def test_check_mode_also_writes_nothing(self, sandbox) -> None:
        M, soe, listed = sandbox
        before = {soe: _sha(soe), listed: _sha(listed)}
        M._run("soe-m8-94", dry_run=False, check=True)
        for path, digest in before.items():
            assert _sha(path) == digest, f"--check 改写了 {path.name}"


#: 子进程脚本：导入门模块 → 可选调用编码修复 → 打印失败报文里的字符。
#: `\u274c` = ❌（GBK 装不下，失败分支用它）；`\u2705` = ✅（GBK 恰好装得下，成功分支用）。
_CHILD = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("gate", r"{gate}")
m = importlib.util.module_from_spec(spec)
sys.modules["gate"] = m
spec.loader.exec_module(m)
if {call_fix}:
    m._force_utf8_stdout()
print("\\u274c \\u6682\\u5b58\\u6811\\u4e0a\\u6709 1 \\u9053\\u95e8\\u4e0d\\u8fc7")
print("DIAGNOSTICS-COMPLETE")
"""


def _run_gate_child(call_fix: bool) -> subprocess.CompletedProcess[bytes]:
    """在**强制 GBK** 的子进程里跑，复现 Windows 默认控制台编码。"""
    return subprocess.run(
        [sys.executable, "-c", _CHILD.format(gate=GATE.as_posix(), call_fix=call_fix)],
        cwd=str(BACKEND.parent),
        capture_output=True,
        env={**os.environ, "PYTHONIOENCODING": "gbk"},
    )


class TestGateFailurePathPrintable:
    """门的**失败**报文必须能在 GBK 控制台打完（判红却说不出红在哪 = 半个门）。"""

    def test_force_utf8_stdout_exists(self) -> None:
        assert GATE.is_file(), f"门脚本不存在：{GATE}"
        text = GATE.read_text(encoding="utf-8")
        assert "_force_utf8_stdout" in text, "门脚本缺输出编码兜底"
        assert "_force_utf8_stdout()" in text.split("def main(", 1)[1][:400], (
            "main() 开头未调用 _force_utf8_stdout —— 修复函数存在但没接线"
        )

    def test_failure_glyph_prints_under_gbk(self) -> None:
        proc = _run_gate_child(call_fix=True)
        stdout = (proc.stdout or b"").decode("utf-8", "replace")
        stderr = (proc.stderr or b"").decode("utf-8", "replace")
        assert proc.returncode == 0, f"GBK 下打印失败报文崩了：\n{stderr[-1500:]}"
        assert "UnicodeEncodeError" not in stderr, stderr[-1500:]
        assert "DIAGNOSTICS-COMPLETE" in stdout, (
            "诊断没打完 —— 失败路径中途被编码异常截断"
        )

    def test_without_fix_it_really_crashes(self) -> None:
        """反向断言：不调修复时必须真的崩。

        否则「调了修复就不崩」无从证明 —— 可能是复现条件根本没成立
        （例如 CI 上 stdout 已是 UTF-8），那样上一条是空转绿。
        """
        proc = _run_gate_child(call_fix=False)
        stderr = (proc.stderr or b"").decode("utf-8", "replace")
        if proc.returncode == 0:
            pytest.skip(
                "本机/CI 环境下 PYTHONIOENCODING=gbk 未能复现编码限制，"
                "无法对该修复做反向证明"
            )
        assert "UnicodeEncodeError" in stderr, (
            f"崩了但不是编码原因，变异前提不成立：\n{stderr[-1500:]}"
        )
