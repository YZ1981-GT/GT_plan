"""run_uvicorn.py 的 argv glob 展开守卫。

## 背景（2026-09-06 实测事故）

后端起不来，只报一句看不出出处的：

    Error: Got unexpected extra arguments (tmp_check_resolve.py tmp_drift_full.txt
    tmp_failopen_check.py tmp_find.py ... tmp_restore_ep.py)

## 根因

1. `start-dev.bat` 传 `--reload-exclude "tmp_*"`，该命令经
   `start ... cmd /k "... "%PY%" run_uvicorn.py ... --reload-exclude "tmp_*" ..."`
   层层嵌套，引号被 cmd / MSVCRT 剥掉，裸 `tmp_*` 进 `sys.argv`。
2. `run_uvicorn.py` 末尾复用的 `uvicorn.main.main` 是 **click** 命令。click 在
   Windows 上默认 `windows_expand_args=True`（Linux 由 shell 展开 glob，Windows
   没有 shell 展开，click 便自己 glob 补偿），于是把 `tmp_*` 按**当前工作目录
   `backend/`** 展开成 69 个文件：第 1 个 `tmp_add_tm.py` 被 `--reload-exclude`
   吃掉，其余 68 个溢出成位置参数 ⇒ click 报 extra arguments。

`--reload-exclude "*.pyc"` / `"*.json"` 长期没炸只是**侥幸**：`backend/` 根下这
两类文件恰好 0 个，glob 无匹配时 click 原样保留。根目录一旦落一个 `.json`，
会以完全相同的方式炸 —— 所以这不是「tmp_ 文件太多」的问题，清空 tmp_ 也不算修好。

## 判据

1. `test_main_called_with_expand_disabled` —— 源码层：`main()` 必须显式传
   `windows_expand_args=False`（真源判据，防回弹）。
2. `test_argv_glob_not_expanded` —— **行为判据**：以 `backend/` 为 cwd 真起一次
   进程，传与 start-dev.bat 同形的参数（含 `--reload-exclude tmp_*`），断言
   **不出现** extra arguments，且失败原因是预期的「app 模块不存在」。
3. `test_click_would_expand_without_the_flag` —— **反向自检**：用同形状的
   click 命令证明「不传 `windows_expand_args=False` 时确实会展开并报同一条错」。
   若本条变绿，说明 click 行为已变，判据 1/2 的前提需重新评估，而不是删测试。

判据 2 的两处设计约束（都是实测踩出来的，改动前请先读）：
  - **不能加 `--help`**：click 的 `--help` 是 eager 参数，会在校验「多余位置参数」
    之前打印帮助并退出 ⇒ 展开仍开着也返绿（假绿）。
  - **不能加 `--reload`**：reload supervisor 会常驻重试导致进程不退（TIMEOUT）。
    本判据发生在 argv 解析阶段，早于 reload 生效，去掉不削弱判定。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
RUN_UVICORN = BACKEND_DIR / "run_uvicorn.py"

EXTRA_ARGS_MARKER = "Got unexpected extra arguments"

# 与 start-dev.bat 同形的参数（app 换成不存在的模块；不带 --reload / --help，理由见模块 docstring）
LAUNCH_ARGS = (
    "_gt_nonexistent_app_for_guard:app",
    "--host", "127.0.0.1",
    "--port", "9",
    "--reload-dir", "app",
    "--reload-delay", "2.0",
    "--reload-exclude", "*.pyc",
    "--reload-exclude", "__pycache__",
    "--reload-exclude", ".hypothesis",
    "--reload-exclude", "*.json",
    "--reload-exclude", "tmp_*",
    "--log-level", "warning",
)


def _source() -> str:
    assert RUN_UVICORN.is_file(), f"启动入口不存在: {RUN_UVICORN}"
    return RUN_UVICORN.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """去掉 # 注释与三引号块，避免「注释里写了就算通过」的 grep 式假绿。"""
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"'''.*?'''", "", src, flags=re.S)
    return re.sub(r"(?m)#.*$", "", src)


def test_main_called_with_expand_disabled() -> None:
    """`main()` 必须显式关掉 click 的 Windows glob 展开。"""
    code = _strip_comments(_source())

    calls = re.findall(r"\bmain\s*\(([^)]*)\)", code)
    assert calls, (
        "run_uvicorn.py 里找不到对 uvicorn `main(...)` 的调用 —— "
        "本守卫的前提变了，请同步更新判据而不是删测试。"
    )
    for args in calls:
        assert "windows_expand_args" in args and "False" in args, (
            "run_uvicorn.py 调用 uvicorn 的 click 入口时必须传 "
            "`windows_expand_args=False`。\n"
            "否则 start-dev.bat 传的 `--reload-exclude \"tmp_*\"` 会被 click 按 cwd "
            "展开成一堆文件名，后端启动直接报 "
            f"`{EXTRA_ARGS_MARKER} (...)`。\n"
            f"实际调用: main({args})"
        )

    # 反向自检：判据必须真的与「False」绑定，而不是只要出现关键字就过
    assert not re.search(r"windows_expand_args\s*=\s*True", code), (
        "run_uvicorn.py 显式传了 windows_expand_args=True，等于主动打开 glob 展开。"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="click 的 argv glob 展开仅在 Windows 生效")
def test_argv_glob_not_expanded(tmp_path: Path) -> None:
    """行为判据：真跑一次，`--reload-exclude tmp_*` 不得被展开成文件列表。"""
    # 必须存在至少一个能被 tmp_* 命中的文件，否则展开无匹配 ⇒ 本测试恒绿（空转）
    probe = BACKEND_DIR / "tmp_argv_glob_guard_probe.txt"
    created = not probe.exists()
    if created:
        probe.write_text("guard probe\n", encoding="utf-8")

    env = dict(os.environ)
    env["GT_BOOTSTRAP_DONE"] = "1"        # 跳过预引导迁移，不连库
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        matches = sorted(p.name for p in BACKEND_DIR.glob("tmp_*"))
        assert matches, "backend/ 下没有 tmp_* 文件，本测试会空转"

        proc = subprocess.run(
            [sys.executable, "run_uvicorn.py", *LAUNCH_ARGS],
            cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    finally:
        if created:
            probe.unlink(missing_ok=True)

    out = (proc.stdout or "") + (proc.stderr or "")

    assert EXTRA_ARGS_MARKER not in out, (
        "`--reload-exclude tmp_*` 被 click 展开成了文件列表 ⇒ 后端起不来。\n"
        "修法：run_uvicorn.py 里 `main(windows_expand_args=False)`。\n"
        f"进程输出：\n{textwrap.indent(out[:1500], '    ')}"
    )

    # 解析通过的正证：失败原因必须是预期的「模块不存在」，而不是别的（防 INCONCLUSIVE 蒙对）
    assert ("Error loading ASGI app" in out or "ModuleNotFoundError" in out
            or "_gt_nonexistent_app_for_guard" in out), (
        "argv 虽未见展开，但失败原因不是预期的「app 模块不存在」，"
        "本测试可能没测到解析链路。\n"
        f"exit={proc.returncode}\n进程输出：\n{textwrap.indent(out[:1500], '    ')}"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="click 的 argv glob 展开仅在 Windows 生效")
def test_click_would_expand_without_the_flag(tmp_path: Path) -> None:
    """反向自检：不传该 flag 时，click 确实会展开 glob 并报同一条错。

    用同形状的独立 click 命令（一个位置参 + multiple 选项），不碰 uvicorn。
    """
    script = tmp_path / "expand_probe.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys
            import click

            @click.command()
            @click.argument("app")
            @click.option("--reload-exclude", multiple=True)
            def cmd(app, reload_exclude):
                print("PARSED_OK", app, reload_exclude)

            if __name__ == "__main__":
                expand = sys.argv[1] != "off"
                sys.argv = ["probe.py", "app:app", "--reload-exclude", "tmp_*"]
                try:
                    cmd.main(standalone_mode=False, windows_expand_args=expand)
                except click.UsageError as exc:
                    print("USAGE_ERROR", exc)
                    sys.exit(2)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    probe = BACKEND_DIR / "tmp_argv_glob_guard_probe.txt"
    created = not probe.exists()
    if created:
        probe.write_text("guard probe\n", encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    def _run(mode: str) -> str:
        proc = subprocess.run(
            [sys.executable, str(script), mode],
            cwd=str(BACKEND_DIR), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=90,
        )
        return (proc.stdout or "") + (proc.stderr or "")

    try:
        on = _run("on")     # 展开开启（click 默认）
        off = _run("off")   # 展开关闭（本仓库修法）
    finally:
        if created:
            probe.unlink(missing_ok=True)

    assert EXTRA_ARGS_MARKER in on, (
        "click 在 Windows 上不再展开 argv 里的 glob（版本行为已变）。\n"
        "这不代表本守卫可以删：请重新评估 run_uvicorn.py 的修法是否仍必要。\n"
        f"输出：\n{textwrap.indent(on[:800], '    ')}"
    )
    assert "PARSED_OK" in off, (
        f"windows_expand_args=False 下仍未正常解析。\n输出：\n{textwrap.indent(off[:800], '    ')}"
    )
