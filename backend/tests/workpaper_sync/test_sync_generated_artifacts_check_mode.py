# -*- coding: utf-8 -*-
"""本 spec 的生成物必须与现算一致（`--check` 幂等）。

spec `workpaper-html-onlyoffice-bidirectional-writeback-closure`（AC 1.3 / 12.1）。

## 为什么补这条

task 4.1 / 6.1 / 6.2 产出了四件生成物，但其中**三件没有任何 pytest 守卫**：
`required_scenario_set` / `runtime_evidence_projection` / `cycle_reconciliation`
（现扫 `backend/tests/**` 对这三个生成器零引用）。生成器自带 `--check`，可只要没有判据
在跑它，产物就可以静默漂移 —— 而本 spec 的 closure 判据全是从这些产物里读数的。

## 为什么把 evidence projection 排除在硬判据之外

`generate_runtime_evidence_projection.py` 要连共享 PG：连得上就按 test_run 现算，连不上
就把全部标 `missing`。两种结果的 digest 不同 ⇒ 它的 `--check` 是**环境相关**的。
把环境相关的东西写成 CI 硬判据 = 制造一条永红门禁，而永红门禁等于没门禁
（本 spec task 7.4 已经在干净检出上实测到这一点：worktree 无 `.env` ⇒ PG digest 不同）。
所以这里只对**不依赖实时 PG** 的两件做硬判据，并显式断言「被排除的那一件确实是环境相关的」
—— 不留一句没人能验证的豁免理由。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
GEN = BACKEND / "scripts" / "gen"

#: 不依赖实时 PG 的生成器：`--check` 必须幂等通过。
DETERMINISTIC = (
    "generate_required_scenario_set.py",
    "generate_cycle_reconciliation.py",
    "generate_residual_lane_ledger.py",
    "generate_task66_execution_ledger.py",
)
#: 依赖实时 PG 的生成器：只断言它**真的**读 PG（所以不能当硬判据），不跑它的 --check。
ENVIRONMENT_DEPENDENT = "generate_runtime_evidence_projection.py"


def _run_check(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GEN / script), "--check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=600,
    )


@pytest.mark.parametrize("script", DETERMINISTIC)
def test_deterministic_generator_check_mode_passes(script: str) -> None:
    assert (GEN / script).is_file(), f"生成器不在磁盘：{script}"
    proc = _run_check(script)
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, (
        f"{script} --check 失败（rc={proc.returncode}）—— 生成物与现算不一致，"
        f"请重跑 --write 并复核 diff：\n{combined[-1500:]}"
    )
    # 🔴 只看退出码会被「解码失败把 stdout 变成 None / 脚本什么都没做就 exit 0」骗过。
    #    同一不变量写两种强度的判据（退出码 + 输出内容）才能互相咬出假绿。
    assert combined.strip(), f"{script} --check 没有任何输出 ⇒ 无法确认它真的跑了比对"


def test_environment_dependent_generator_is_really_environment_dependent() -> None:
    """被排除的那一件必须**可验证地**环境相关，而不是写个理由就豁免。"""
    source = (GEN / ENVIRONMENT_DEPENDENT).read_text(encoding="utf-8")
    assert "DATABASE_URL" in source or "create_async_engine" in source or "asyncpg" in source, (
        f"{ENVIRONMENT_DEPENDENT} 里找不到任何连库痕迹 —— 那它就不该被排除在硬判据之外"
    )
    assert "missing" in source, (
        "找不到「连不上就全标 missing」的降级分支 —— 排除理由的前提不成立"
    )


def test_deterministic_list_is_not_empty_and_scripts_exist() -> None:
    assert len(DETERMINISTIC) >= 4, "确定性生成器清单过短 ⇒ 本文件判据分母塌了"
    missing = [s for s in (*DETERMINISTIC, ENVIRONMENT_DEPENDENT) if not (GEN / s).is_file()]
    assert not missing, f"清单里有不存在的生成器：{missing}"
