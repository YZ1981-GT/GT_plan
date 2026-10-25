# -*- coding: utf-8 -*-
"""`check_file_size.py --staged` 的判据。

spec: d1-sync-row-table-engine-and-d1-coverage · X1

═══ 这组判据守什么 ═══

行数门此前**选文件**用 `git diff --cached --name-only`（= 你提交了什么），却去
**读工作树内容**（= 工作树有什么）—— 内部不自洽。

实测后果（本 spec X1）：`excel_materialize.py` 某次提交只 +31 行（暂存 3691，在
whitelist 基线 3660 +5% 之内），但同一文件里另一条 lane 有 ~258 行**未提交**改动
⇒ 门按工作树 3948 判「膨胀」。这会逼人做两件错事之一：

* 把基线抬到 3948 —— 替那条 lane 预留额度，并把**别人**的膨胀记到自己账上；
* `git commit --no-verify` —— 门直接失效。

`--staged` 让「门量的东西」== 「commit 里真正是什么」。

═══ 为什么每条都必须有 ═══

新增一个模式却不验它，等于多了一条没人看过的分支。下面四条分别钉住：
默认口径没变 / staged 口径生效 / 未暂存时 fail-visible（不静默回落工作树）/
两个口径在「暂存 == 工作树」时同值。
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_CHECK = _REPO / "backend" / "scripts" / "check" / "check_file_size.py"


def _load():
    """每次都重新 exec —— `_STAGED_MODE` 是模块级状态，复用会串测。"""
    spec = importlib.util.spec_from_file_location("_check_file_size_staged", _CHECK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_CHECK), *args],
        cwd=str(_REPO), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )


def test_default_mode_reads_worktree() -> None:
    """默认口径不变：读工作树。"""
    mod = _load()
    assert mod._STAGED_MODE is False
    target = _REPO / "backend" / "scripts" / "check" / "check_file_size.py"
    assert mod.count_lines(target) == len(
        target.read_text(encoding="utf-8").splitlines()
    )


def test_staged_mode_reads_index_not_worktree(tmp_path) -> None:
    """`--staged` 读的是 `git show :<path>` 而不是磁盘内容。

    构造：找一个**既已暂存又与工作树不同**的文件。本仓库工作树长期混多 lane，
    正常情况下能找到；找不到时 skip 并说明（不假装通过）。
    """
    proc = subprocess.run(
        ["git", "diff", "--name-only"], cwd=str(_REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=str(_REPO),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    both = (
        {l.strip() for l in proc.stdout.splitlines() if l.strip().endswith(".py")}
        & {l.strip() for l in staged.stdout.splitlines() if l.strip().endswith(".py")}
    )
    if not both:
        pytest.skip(
            "当前没有「既已暂存、又与工作树不同」的 .py —— 本条需要那种文件才能"
            "区分两个口径（不构造假数据：git 索引状态是本条的被测对象本身）"
        )
    rel = sorted(both)[0]
    mod = _load()
    mod._STAGED_MODE = True
    staged_lines = mod.count_lines(_REPO / rel)
    worktree_lines = len((_REPO / rel).read_text(encoding="utf-8").splitlines())
    index_bytes = subprocess.run(
        ["git", "show", f":{rel}"], cwd=str(_REPO), capture_output=True
    ).stdout
    assert staged_lines == len(index_bytes.decode("utf-8", "replace").splitlines())
    assert staged_lines != worktree_lines, (
        f"{rel} 的暂存与工作树行数相同 —— 本条没能区分两个口径，换一个文件"
    )


def test_staged_mode_fails_visibly_for_unstaged_file() -> None:
    """未暂存的文件在 `--staged` 下必须**抛**，不得静默回落工作树。

    🔴 静默回落会让「门量的是暂存内容」变成一句空话 —— 恰好是本模式要消除的那种
    「口径说一套做一套」。
    """
    mod = _load()
    mod._STAGED_MODE = True
    # 用一个确定不在 index 里的路径（tmp 名字不会被 git 跟踪）
    phantom = _REPO / "backend" / "scripts" / "check" / "_not_staged_probe_xyz.py"
    with pytest.raises(OSError, match="取不到"):
        mod.count_lines(phantom)


def test_cli_staged_flag_actually_switches_the_mode() -> None:
    """🔴 CLI 的 `--staged` 必须真的把口径切过去 —— 不能只是「接受这个参数」。

    做法：构造一个**暂存内容与工作树内容行数不同**且暂存版**不超限**、工作树版**超限**
    的真实文件，两个口径必须给出不同 rc。

    为什么必须有这条：只断言「CLI 接受 --staged 不报错」的判据，在「解析了参数但忘了
    接到 `_STAGED_MODE`」时**恒绿** —— 实测把那三行改成 `if False:` 后其余判据全部通过。
    """
    probe_rel = "backend/scripts/check/_staged_mode_probe.py"
    probe = _REPO / probe_rel
    # 暂存版 1 行（远低于 .py 上限），工作树版造到 1200 行（超 800 上限且不在 whitelist）
    try:
        probe.write_text("x = 1\n", encoding="utf-8")
        assert subprocess.run(
            ["git", "add", "--intent-to-add", "--", probe_rel], cwd=str(_REPO)
        ).returncode == 0
        assert subprocess.run(
            ["git", "add", "--", probe_rel], cwd=str(_REPO)
        ).returncode == 0
        probe.write_text("x = 1\n" * 1200, encoding="utf-8")

        worktree = _run([probe_rel])
        staged = _run([probe_rel, "--staged"])
        assert worktree.returncode != 0, (
            "工作树 1200 行的新文件竟未超限 —— 前提不成立，本条失去覆盖面\n"
            f"{worktree.stdout}{worktree.stderr}"
        )
        assert staged.returncode == 0, (
            "暂存版只有 1 行却被判超限 ⇒ `--staged` 没有真的切换口径\n"
            f"{staged.stdout}{staged.stderr}"
        )
    finally:
        subprocess.run(
            ["git", "rm", "--cached", "--force", "--quiet", "--", probe_rel],
            cwd=str(_REPO), capture_output=True,
        )
        probe.unlink(missing_ok=True)


def test_cli_accepts_staged_flag_and_agrees_when_index_equals_worktree() -> None:
    """CLI 接受 `--staged`；对「暂存 == 工作树」的文件两口径同结论。

    取本判据文件自身所在目录下一个**已提交且干净**的文件 —— 它的 index 与工作树
    相同，所以两个口径必须给出同一个 rc。
    """
    rel = "backend/scripts/check/check_file_size.py"
    dirty = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", rel], cwd=str(_REPO)
    ).returncode != 0
    if dirty:
        pytest.skip(f"{rel} 当前有未提交改动，两口径本就应不同 —— 换干净文件才有意义")
    a = _run([rel])
    b = _run([rel, "--staged"])
    assert a.returncode == b.returncode, (
        f"暂存与工作树内容相同，两口径却给出不同 rc（{a.returncode} vs "
        f"{b.returncode}）\n工作树: {a.stdout}{a.stderr}\n暂存: {b.stdout}{b.stderr}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 补：脚本支持 `--staged` ≠ hook 真的传了 `--staged`
#
# 实测（本 spec X4 提交时被 hook 拦下）：脚本改好、5 条判据全绿、手动跑 `--staged`
# rc=0 —— 但 `git commit` 仍按**工作树** 4213 行判膨胀。原因是 hook 有两份：
#   * `.git-hooks/pre-commit`   —— 版本控制里的**源**，我改的是这份（带 --staged）
#   * `.git/hooks/pre-commit`   —— git 实际执行的那份，需 `install.ps1` 复制过去
# 源改了没装 ⇒ 门的修复对本地 commit 完全无效。
#
# 🔴 而且我当时是用 `'--staged' in text` 判断「已装好」的，得到 True —— 命中的是我
# 自己写的**注释**。这与铁律㉖（判断代码是否真做了 X 要用 AST，别用文本 in）同型，
# 只不过 shell 没有 AST，所以下面用「剔除注释行后再匹配」，并配变异证明该剔除真的生效。
# ─────────────────────────────────────────────────────────────────────────────

_HOOK_SRC = _REPO / ".git-hooks" / "pre-commit"


def _size_gate_invocation_lines(text: str) -> list[str]:
    """取 hook 里**非注释**的 `check_file_size.py` 调用行。

    只按 `#` 开头剔注释（shell 无块注释）；不做 `in` 全文匹配 —— 那会被注释骗过。
    """
    out = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "check_file_size.py" in line:
            out.append(line)
    return out


def test_hook_source_passes_staged_flag() -> None:
    """`.git-hooks/pre-commit` 必须以 `--staged` 调用行数门。"""
    lines = _size_gate_invocation_lines(_HOOK_SRC.read_text(encoding="utf-8"))
    assert lines, "hook 源里找不到 check_file_size.py 的调用行（非注释）"
    for line in lines:
        assert "--staged" in line, (
            "hook 选文件用 `git diff --cached` 却不传 `--staged` ⇒ 又回到「选暂存、"
            f"读工作树」的不自洽口径：\n  {line}"
        )


def test_comment_only_staged_mention_does_not_count() -> None:
    """变异反证：把调用行的 flag 去掉、只在注释里留 `--staged` ⇒ 必须判红。

    这条钉住的是**扫描器本身**：若改用全文 `'--staged' in text`，本条会假绿。
    """
    mutated = _HOOK_SRC.read_text(encoding="utf-8").replace(
        "check_file_size.py --staged", "check_file_size.py"
    )
    assert "# 🔴 `--staged`" in mutated or "--staged" in mutated, (
        "变异后注释里应仍留有 `--staged` 字样 —— 否则这条变异证明不了「剔注释」的必要性"
    )
    lines = _size_gate_invocation_lines(mutated)
    assert lines, "变异体里仍应有调用行"
    assert all("--staged" not in l for l in lines), (
        "变异没生效（锚点没命中）—— 不算证明"
    )


def test_installed_hook_matches_source_or_tells_you_to_install() -> None:
    """已安装的 hook 与源不一致时要**说出来**，而不是让人下次 commit 才发现。

    `.git/hooks/` 不在版本控制里，CI 上根本不存在 ⇒ 缺失时 skip（不是 fail）；
    但存在且**内容不同**时必须红 —— 那正是本次踩的坑。
    """
    installed = _REPO / ".git" / "hooks" / "pre-commit"
    if not installed.exists():
        pytest.skip(".git/hooks/pre-commit 不存在（CI 环境正常）—— 本地请跑 .git-hooks/install.ps1")
    src_lines = _size_gate_invocation_lines(_HOOK_SRC.read_text(encoding="utf-8"))
    got_lines = _size_gate_invocation_lines(
        installed.read_text(encoding="utf-8", errors="replace")
    )
    assert got_lines == src_lines, (
        "已安装的 hook 与 .git-hooks/ 源不一致 —— 你对门的修改不会生效。\n"
        f"源:   {src_lines}\n已装: {got_lines}\n"
        "修复：powershell -File .git-hooks/install.ps1"
    )
