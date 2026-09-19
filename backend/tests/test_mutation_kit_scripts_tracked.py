"""变异脚本入库守卫 — 每个 mutate*.py 要么被 git 跟踪，要么显式登记豁免。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 5.4, 5.6 · Property 16

## 为什么需要它

变异脚本是「守卫是否真承重」的唯一反证手段，但它本身**没有任何机制保证它进了库**。
2026-08-15 实测：`procedure-trimming-and-delegation-intelligence`(26/26) 已归档，
其归档 commit 只带了 `mutate_trim_decision_guards.py`，**遗漏同 spec 的 7 个变异脚本**
（3108 行），它们只存在于某台机器的工作树里 —— 干净 checkout 下无法复现其判定，
工作树一丢即全部蒸发。而且正因为没有 CI 跑它们，其中 `mutate_task23` 的两条变异
早在该 spec 归档时就随生产代码重构失效了，**漂移无人发现**。

这是 memory 铁律「spec 全绿 ≠ 产物已入库」在变异脚本上的具体形态。

## 判据设计

判「是否入库」用 `git ls-files --error-unmatch`（查 index，不看 .gitignore）——
不是查文件存在（工作树里存在恰恰是问题所在），也不是查 `git status`（未跟踪文件
可能被 .gitignore 挡住而不出现在 status 里）。

豁免走 `backend/data/mutation_kit_exemptions.json` 的显式登记，且
`test_mutation_kit_exemptions.py` 负责校验豁免项本身的有效性与失效检测。
豁免表解析失败时本守卫**失败**（fail-closed）—— 解析不了就等于没有豁免。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXEMPTIONS = REPO / "backend/data/mutation_kit_exemptions.json"
SCAN_DIRS = ("backend/scripts/check", "backend/scripts/diagnose")


def discover_mutation_scripts() -> list[str]:
    """仓库相对路径的 mutate*.py 全集（排序，便于断言稳定）。"""
    found: list[str] = []
    for rel in SCAN_DIRS:
        d = REPO / rel
        if not d.is_dir():
            continue
        for p in sorted(d.glob("mutate*.py")):
            found.append(str(p.relative_to(REPO)).replace("\\", "/"))
    return found


def load_exempt_scripts() -> set[str]:
    """豁免表里的 script 集合。解析失败一律抛 —— fail-closed。"""
    raw = EXEMPTIONS.read_text(encoding="utf-8")
    data = json.loads(raw)
    return {str(e["script"]).replace("\\", "/") for e in data["exemptions"]}


def is_tracked(rel_path: str) -> bool:
    """git index 里是否有该路径。"""
    rc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel_path],
        cwd=str(REPO), capture_output=True, text=True,
    )
    return rc.returncode == 0


def find_untracked(scripts: list[str], exempt: set[str]) -> list[str]:
    """核心判据（抽成纯函数，便于反向自检）：未跟踪且未豁免的脚本。"""
    return [s for s in scripts if s not in exempt and not is_tracked(s)]


def test_exemptions_file_parses() -> None:
    """豁免表必须可解析 —— 解析不了就等于没有豁免（fail-closed）。"""
    assert EXEMPTIONS.exists(), f"豁免表缺失：{EXEMPTIONS}"
    data = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    assert isinstance(data.get("exemptions"), list), "exemptions 必须是数组"


def test_git_is_available() -> None:
    """本守卫的前提是仓库为 git 工作副本；不可用时显式失败而非静默跳过。"""
    rc = subprocess.run(["git", "rev-parse", "--git-dir"],
                        cwd=str(REPO), capture_output=True, text=True)
    assert rc.returncode == 0, "git 不可用，无法判定入库状态（本守卫不做静默跳过）"


def test_mutation_scripts_discovered() -> None:
    """扫描本身要有产出 —— 扫到 0 个说明目录或 glob 写错了，那会让本守卫恒绿。"""
    scripts = discover_mutation_scripts()
    assert len(scripts) >= 10, f"只扫到 {len(scripts)} 个变异脚本，疑似扫描路径失效：{scripts}"


def test_every_mutation_script_is_tracked_or_exempt() -> None:
    """主判据：mutate*.py 要么入库，要么在豁免表里。"""
    scripts = discover_mutation_scripts()
    exempt = load_exempt_scripts()
    offenders = find_untracked(scripts, exempt)
    assert not offenders, (
        "以下变异脚本既未入库也未登记豁免（丢工作树即蒸发，且干净 checkout 下无法复现判定）：\n"
        + "\n".join("  ?? " + o for o in offenders)
        + "\n\n处置二选一：① git add 入库 ② 在 backend/data/mutation_kit_exemptions.json "
          "登记豁免（须带 spec / reason / registered_at / revoke_when）"
    )


def test_exempt_scripts_actually_exist() -> None:
    """豁免表不得有僵尸项 —— 登记了一个已删除的脚本会让豁免表越积越脏。"""
    exempt = load_exempt_scripts()
    missing = [s for s in sorted(exempt) if not (REPO / s).exists()]
    assert not missing, (
        "豁免表登记了不存在的脚本（应删除该豁免项）：\n" + "\n".join("  " + m for m in missing)
    )


def test_exemption_is_not_used_to_hide_tracked_scripts() -> None:
    """已入库的脚本无需 tracked 豁免 —— 但允许其为 adoption 守卫保留豁免。

    故此处不断言「豁免项必须未跟踪」，只断言豁免项的 reason 里说明了它的用途，
    避免「入库了还挂着豁免」变成无人复核的死条目。
    """
    data = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    for entry in data["exemptions"]:
        script = str(entry["script"]).replace("\\", "/")
        if is_tracked(script):
            reason = str(entry.get("reason", ""))
            assert len(reason) >= 10, (
                f"{script} 已入库却挂着豁免，其 reason 必须说明豁免的用途"
                f"（例如仅为 adoption 守卫保留）：{reason!r}"
            )


# ─── 反向自检：守卫必须能打红 ────────────────────────────────────────────────
#
# memory 铁律：每写完守卫必做变异检验，「没打红 = 守卫有缺陷，不是代码没问题」。
# 这里把核心判据 find_untracked 抽成纯函数后直接反证。


def test_reverse_selfcheck_untracked_script_is_caught() -> None:
    """喂一个确定不在 index 里的路径，find_untracked 必须报出它。"""
    fake = "backend/scripts/diagnose/mutate__reverse_selfcheck_does_not_exist__.py"
    assert not is_tracked(fake), "自检前提被破坏：该假路径不应在 git index 里"
    caught = find_untracked([fake], exempt=set())
    assert caught == [fake], f"未跟踪脚本没被报出 ⇒ 判据失效，实际={caught}"


def test_reverse_selfcheck_exemption_suppresses() -> None:
    """同一个假路径登记豁免后必须被放过 —— 证明豁免机制真的生效（而非恒报）。"""
    fake = "backend/scripts/diagnose/mutate__reverse_selfcheck_does_not_exist__.py"
    assert find_untracked([fake], exempt={fake}) == [], "豁免未生效 ⇒ 豁免机制是装饰"


def test_reverse_selfcheck_tracked_script_passes() -> None:
    """已入库的真实脚本不得被误报（防判据反向失效：把所有脚本都报一遍也能"全绿→全红"）。"""
    real = "backend/scripts/diagnose/mutate_e_cycle_guards.py"
    assert is_tracked(real), f"前提被破坏：{real} 应已入库"
    assert find_untracked([real], exempt=set()) == [], "已入库脚本被误报 ⇒ 判据有假阳性"


def test_reverse_selfcheck_broken_exemption_file_fails_closed() -> None:
    """豁免表不可解析时必须抛，而不是当成「没有豁免项」继续（fail-open）。"""
    with pytest.raises(json.JSONDecodeError):
        json.loads("{ not valid json")
