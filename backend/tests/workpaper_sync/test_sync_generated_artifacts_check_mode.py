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

import json
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


def test_committed_evidence_projection_was_produced_against_a_reachable_database() -> None:
    """入库的 runtime evidence 投影不得是**连不上库**时降级产出的那一份。

    🔴 这条是被一次真实的环境陷阱逼出来的：本仓的终端是跨会话共享的，而「只跑隔离用例」
    的约定会把 `DATABASE_URL` 设成一个**不存在的库名**。在那种 shell 里跑
    `generate_runtime_evidence_projection.py --write`，生成器会如实记下
    `pg_facts.status = "degraded:InvalidCatalogNameError"` 并把 67 条 entry 全标 `missing`
    —— 内容与「真库上确实一条验收记录都没有」**逐字相同**。

    也就是说：如果没有这条判据，「0 条证据」这个结论可以被一个环境变量伪造出来，而且
    看不出区别。本 spec 的 closure 判据正是从这份产物里读数的，所以必须钉住它的来源。

    判据只读已入库 JSON 的 `pg_facts.status`，不连库 ⇒ 确定性，不会变成一条环境相关的
    永红门禁（那正是上面把 evidence projection 排除在 `--check` 硬判据之外的理由）。
    """
    path = BACKEND / "data" / "workpaper_sync_runtime_evidence_projection.json"
    facts = json.loads(path.read_text(encoding="utf-8")).get("pg_facts") or {}
    status = str(facts.get("status") or "")
    assert status, f"{path.name} 缺 pg_facts.status —— 无法判断它是在什么环境下产出的"
    assert not status.startswith("degraded"), (
        f"入库的 evidence 投影是降级产出的（status={status}）—— 它的 `missing` 分布反映的是"
        "「连不上库」而不是「库里没有验收记录」。请在能连到共享库的环境重跑 --write 后再提交。"
    )
    assert status != "not_postgresql", (
        f"入库的 evidence 投影产自非 PostgreSQL 环境（status={status}）—— 同上，不可采信"
    )


def test_deterministic_list_is_not_empty_and_scripts_exist() -> None:
    assert len(DETERMINISTIC) >= 4, "确定性生成器清单过短 ⇒ 本文件判据分母塌了"
    missing = [s for s in (*DETERMINISTIC, ENVIRONMENT_DEPENDENT) if not (GEN / s).is_file()]
    assert not missing, f"清单里有不存在的生成器：{missing}"
