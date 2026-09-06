"""start-dev.bat 编码守卫。

## 背景（2026-09-05 实测事故）

start-dev.bat 里被加入中文 REM 注释后，启动脚本在解析阶段就碎掉，现象：

    [2/5] Starting backend on :9980 ...
    '??' is not recognized as an internal or external command,
    [3/5] Waiting for backend health ...
    '*在' is not recognized as an internal or external command,
    '连接失败。' is not recognized as an internal or external command,
    '[WARN]' is not recognized as an internal or external command,

## 根因（2×2 因子实验实测确认，两个因子缺一不可）

| 块内多字节字符 | 解析中途 `chcp 65001` | 结果 |
|---|---|---|
| 有 | 有 | **碎（复现残片）** |
| 有 | 无 | 干净 |
| 无 | 有 | 干净 |

cmd.exe 先按**父 console 当前代码页**打开并逐行解析 bat；第 3 行 `chcp 65001`
把代码页换成 UTF-8 后，cmd 的「字符数 vs 字节数」记账失去同步。解析 `( ... )`
块时它需要回退文件指针重读，错位的指针于是落到某行中间，把中文 REM 注释的
后半截当成命令执行。这是 cmd.exe 的缺陷，**无法在 bat 内部规避**。

## 为什么必须强制 CP936 才测得出来

触发条件依赖**父进程 console 代码页**：
  - 父 CP=936（中文 Windows 默认，用户双击 bat 的真实情形）-> 碎
  - 父 CP=65001（已切 UTF-8 的终端 / python 子进程管道）    -> 不碎
所以自检**必须显式 `chcp 936`** 再跑。否则在已是 65001 的会话里恒绿，
测试通过但什么都没验证 —— 这正是本守卫初版踩过的坑。

## 判据

1. `test_no_non_ascii_bytes`  —— start-dev.bat 必须 0 个非 ASCII 字节（真源判据）
2. `test_crlf_only` / `test_no_bom` —— 行尾与 BOM
3. `test_ascii_only_marker_comment_present` —— 就地告警注释仍在
4. `test_failure_mode_is_real` —— **反向自检**：CP936 下含中文 REM 的 bat
   必须复现残片，ASCII 对照组必须干净。若中文组变绿，说明判据 1 的前提不再
   成立，应重新评估而不是删限制/删测试。
5. `test_real_launcher_parses_clean_under_cp936` —— **端到端**：真实
   start-dev.bat（副作用打桩）在 CP936 下必须 0 残片且 6 个步骤 banner 全到。

判据 4/5 是防「grep 式假绿」的关键：不检查字符串是否存在，而是让 cmd 真的
执行一次，用行为证明。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BAT = REPO_ROOT / "start-dev.bat"

# cmd.exe 解析错位后打出的特征串
GARBAGE_MARKERS = (
    "is not recognized as an internal or external command",
    "was unexpected at this time",
)


def _read_bytes() -> bytes:
    assert BAT.is_file(), f"启动脚本不存在: {BAT}"
    return BAT.read_bytes()


def test_no_non_ascii_bytes() -> None:
    """start-dev.bat 必须纯 ASCII。中文说明请写到 docs/dev/start-dev-launcher-notes.md。"""
    raw = _read_bytes()
    offenders = [(i, b) for i, b in enumerate(raw) if b > 0x7F]
    if offenders:
        # 定位到行号，给出可操作的报错
        text = raw.decode("utf-8", errors="replace")
        bad_lines = [
            (n, line)
            for n, line in enumerate(text.splitlines(), 1)
            if any(ord(c) > 0x7F for c in line)
        ]
        detail = "\n".join(f"  L{n}: {line.strip()[:90]}" for n, line in bad_lines[:20])
        pytest.fail(
            f"start-dev.bat 含 {len(offenders)} 个非 ASCII 字节，"
            f"分布在 {len(bad_lines)} 行：\n{detail}\n"
            "原因：chcp 65001 下 cmd 按字符数回退文件指针、按字节读文件，"
            "括号块内多字节字符会让解析错位并执行注释残片。"
            "中文说明请移到 docs/dev/start-dev-launcher-notes.md。"
        )


def test_crlf_only() -> None:
    """bat 必须全 CRLF；bare LF 会让 cmd 的行解析行为不可靠。"""
    raw = _read_bytes()
    crlf = raw.count(b"\r\n")
    total_lf = raw.count(b"\n")
    assert total_lf - crlf == 0, (
        f"start-dev.bat 存在 {total_lf - crlf} 个裸 LF 行尾（CRLF={crlf}）。"
        "检查 .gitattributes 是否对 *.bat 强制了 LF。"
    )


def test_no_bom() -> None:
    """UTF-8 BOM 会被 cmd 当成第一条命令的一部分。"""
    assert not _read_bytes().startswith(b"\xef\xbb\xbf"), "start-dev.bat 不应带 UTF-8 BOM"


def test_ascii_only_marker_comment_present() -> None:
    """文件头必须留下 ASCII-only 的告警，否则下一个人会再把中文加回来。"""
    text = _read_bytes().decode("ascii", errors="replace")
    assert "ASCII-ONLY FILE" in text, (
        "start-dev.bat 头部缺少 ASCII-ONLY 告警注释；"
        "缺了它，下次有人加中文注释时没有任何就地提示。"
    )


def _run_bat_under_cp936(bat: Path, out_file: Path, timeout: int = 120) -> str:
    """在父 console 代码页 = 936 下执行 bat，返回合并输出。

    必须经 PowerShell 显式 `chcp 936`：触发条件依赖父进程代码页，
    直接用 python subprocess + 管道时父 CP 可能已是 65001，恒不复现。
    输出重定向由 cmd 自己写文件（避免管道改变 console 语义）。
    """
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f'chcp 936 > $null; cmd /c "`"{bat}`" > `"{out_file}`" 2>&1"',
        ],
        capture_output=True,
        timeout=timeout,
    )
    if not out_file.exists():
        return "<no output file produced>"
    return out_file.read_text(encoding="utf-8", errors="replace")


def _garbage_lines(text: str) -> list[str]:
    return [
        ln.strip()
        for ln in text.splitlines()
        if any(m in ln for m in GARBAGE_MARKERS)
    ]


def test_referenced_notes_doc_exists() -> None:
    """bat 头部引用的中文说明文档必须真实存在（防死链）。

    中文说明被强制移出 bat，若引用路径写错/文档被挪走，
    下一个人就找不到「为什么不能写中文」的实测依据，坑会重现。
    """
    text = _read_bytes().decode("ascii", errors="replace")
    m = re.search(r"Rationale in Chinese:\s*(\S+\.md)", text)
    assert m, "start-dev.bat 头部缺少 `Rationale in Chinese: <path>.md` 引用行"
    rel = m.group(1)
    doc = REPO_ROOT / rel
    assert doc.is_file(), (
        f"start-dev.bat 引用的说明文档不存在: {rel}（解析为 {doc}）。"
        "要么补上文档，要么修正引用路径。"
    )
    body = doc.read_text(encoding="utf-8", errors="replace")
    assert "chcp" in body and "936" in body, (
        f"{rel} 未包含代码页相关说明（chcp / 936），"
        "该文档应承载 ASCII-only 限制的根因与实测数据。"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe 解析行为仅 Windows 相关")
def test_failure_mode_is_real(tmp_path: Path) -> None:
    """反向自检：CP936 下含中文 REM 的括号块必须真的复现残片执行。

    断言的是**本守卫存在的前提**，不是产品代码。
    中文组变绿 = cmd 行为变了 -> 去重新评估 ASCII 限制，
    而不是删掉限制或删掉这条测试。
    """
    head = (
        "@echo off\r\n"
        "setlocal EnableExtensions EnableDelayedExpansion\r\n"
        "chcp 65001 >nul 2>nul\r\n"
        "echo [A] start\r\n"
        'set "R=0"\r\n'
        "for /L %%i in (1,1,2) do (\r\n"
        "  if !R!==0 (\r\n"
    )
    tail = "    echo [B] loop %%i\r\n  )\r\n)\r\necho [C] end\r\n"
    cn_body = (
        "    REM 必须用 127.0.0.1 而非 localhost：uvicorn 只监听 IPv4。\r\n"
        "    REM Windows 上 localhost 先解析 ::1，连接失败后才回退，实测耗时 ~2050ms。\r\n"
        "    REM 这条假失败会打出误导性的 [WARN] Backend not responding。\r\n"
    )
    ascii_body = (
        "    REM Must use 127.0.0.1 not localhost: uvicorn listens IPv4 only.\r\n"
        "    REM On Windows localhost resolves ::1 first then falls back, ~2050ms.\r\n"
        "    REM This false failure prints a misleading [WARN] Backend not responding.\r\n"
    )

    def probe(stem: str, body: str) -> str:
        p = tmp_path / f"{stem}.bat"
        p.write_bytes((head + body + tail).encode("utf-8"))
        return _run_bat_under_cp936(p, tmp_path / f"{stem}.out")

    ascii_out = probe("probe_ascii", ascii_body)
    cn_out = probe("probe_cn", cn_body)

    ascii_bad = _garbage_lines(ascii_out)
    cn_bad = _garbage_lines(cn_out)

    # 装置自检：ASCII 对照组必须干净且真的跑完，否则复现装置本身坏了
    assert not ascii_bad, (
        "ASCII 对照组出现解析残片，复现装置本身有问题，不能用来支撑判据：\n"
        f"{textwrap.indent(ascii_out, '    ')}"
    )
    assert "[C] end" in ascii_out, (
        "ASCII 对照组没跑到结尾，复现装置未生效（可能 powershell/chcp 调用失败）：\n"
        f"{textwrap.indent(ascii_out, '    ')}"
    )

    assert cn_bad, (
        "CP936 下含中文 REM 的括号块**未**复现解析残片。"
        "cmd.exe 的代码页切换记账行为可能已改变。"
        "请重新评估 start-dev.bat 的 ASCII-only 限制，不要直接删除限制或本测试。\n"
        f"实际输出：\n{textwrap.indent(cn_out, '    ')}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe 解析行为仅 Windows 相关")
def test_real_launcher_parses_clean_under_cp936(tmp_path: Path) -> None:
    """端到端：真实 start-dev.bat 在 CP936 下必须 0 残片、6 个步骤 banner 全到。

    把有副作用的命令（taskkill/start/timeout/powershell 探测）替换成桩，
    只跑解析与控制流，不启动任何真实服务、不杀任何进程。
    这条覆盖「判据 1 通过但脚本仍在别处碎掉」的情形。
    """
    src = BAT.read_bytes().decode("ascii")

    stub = re.sub(r'powershell -NoProfile -Command ".*?"', "cmd /c exit 0", src, flags=re.S)
    stub = re.sub(r"^\s*taskkill .*$", "rem stubbed-taskkill", stub, flags=re.M)
    stub = re.sub(r'^start ".*$', "echo    [stub] would start service", stub, flags=re.M)
    stub = re.sub(r"^timeout .*$", "rem stubbed-timeout", stub, flags=re.M)

    assert "cmd /c exit 0" in stub, "打桩失败：未替换任何 powershell 探测调用"
    assert "[stub] would start service" in stub, "打桩失败：未替换 start 调用"

    # 桩必须落在仓库根目录：bat 里 %~dp0 派生 BACKEND_DIR/FRONTEND_DIR，
    # 放到 tmp_path 会让前置检查 `if not exist %BACKEND_DIR%\app\main.py`
    # 直接 exit /b 1，测出来的就不是解析行为了。
    p = REPO_ROOT / f"tmp_launcher_dryrun_{os.getpid()}.bat"
    try:
        p.write_bytes(stub.encode("ascii"))
        out = _run_bat_under_cp936(p, tmp_path / "launcher_dryrun.out")
    finally:
        p.unlink(missing_ok=True)

    assert "Backend not found" not in out and "Frontend not found" not in out, (
        "前置检查未通过，本测试没测到解析行为。"
        f"确认从仓库根运行且依赖已装：\n{textwrap.indent(out, '    ')}"
    )

    bad = _garbage_lines(out)
    assert not bad, (
        f"start-dev.bat 在 CP936 下出现 {len(bad)} 条解析残片：\n"
        + textwrap.indent("\n".join(bad[:10]), "    ")
        + f"\n完整输出：\n{textwrap.indent(out, '    ')}"
    )

    missing = [s for s in ("[1/5]", "[2/5]", "[3/5]", "[3.5]", "[4/5]", "[5/5]")
               if s not in out]
    assert not missing, (
        f"start-dev.bat 缺少步骤 banner {missing}，说明脚本中途被解析错误终止。\n"
        f"完整输出：\n{textwrap.indent(out, '    ')}"
    )
