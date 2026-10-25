# -*- coding: utf-8 -*-
"""CI workflow 里声明的门禁脚本 / 自测文件必须真的在版本控制里。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-c
Requirements 7.4

═══ 为什么需要这条（2026-09-28 实测）═══

`check_row_table_formula_columns_consistency.py`（Gate 5）与
`check_store_item_two_way_parity.py`（Gate 6）本地写好、手动跑 exit 0、自测全绿、
tasks.md 也登记了「立成 CI 卡点」—— 但四个文件（2 门禁 + 2 自测）**从未提交过**
（`git log` 对它们零记录），而把它们接进 workflow 的那段 yml 改动也未提交。

于是形成一个**双向都看不见**的空洞：

* 只看本地 → 门禁在、绿的，一切正常；
* 只看 HEAD → workflow 不引用它们，CI 也不会红。

⇒ 「CI 卡点已建立」这句话在仓库里没有任何对应物。这与同轮的另两次同型：
  ① 脚本支持 `--staged` ≠ hook 真的传了（`.git/hooks/` 未同步）
  ② 注释里出现 `--staged` ≠ 代码真做了（文本 `in` 匹配被注释骗过）
三者共同的形状是「声明层已完备，接入层是空的」。

本条把**接入层**钉住：workflow 声明的每个路径都必须 `git ls-files` 认得。
存在于磁盘但未跟踪也算红 —— 那正是本次的形态（文件在，只是没入库）。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_WORKFLOWS = [
    _REPO / ".github" / "workflows" / "governance-checks.yml",
    _REPO / ".github" / "workflows" / "ci.yml",
]

#: workflow 里出现的仓库内 python 路径。只认 `backend/...` 前缀的具体文件，
#: 不去猜 shell 变量拼出来的路径（那种本条覆盖不到，另见各门禁自身的自测）。
_PATH_RE = re.compile(r"(backend/(?:scripts|tests)/[A-Za-z0-9_/]+\.py)")


def _declared_paths(text: str) -> set[str]:
    return set(_PATH_RE.findall(text))


def _is_tracked(rel: str) -> bool:
    return subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", rel],
        cwd=str(_REPO), capture_output=True,
    ).returncode == 0


def _all_declared() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for wf in _WORKFLOWS:
        if not wf.exists():
            continue
        for rel in _declared_paths(wf.read_text(encoding="utf-8")):
            out.setdefault(rel, []).append(wf.name)
    return out


#: 🔴 既存欠账棘轮（**只许变短**）。本条判据一上手就抓到一处历史缺陷，
#: 它**不属于本 spec**，所以不在本轮硬修 —— 但也不许静默放过：
#:
#:   `backend/scripts/audit_a7_a15_xlsx.py` —— ci.yml 的 `audit-xlsx-drift` job
#:   （INFRA-3，注释说「验证 a7_a15_xlsx_audit.json 未与实际 xlsx 模板脱节」）
#:   引用了一个磁盘上不存在的脚本。该 job 标着 `continue-on-error: true`，所以
#:   CI 整体不红 —— 代价是这个 job **从来没有真正生效过**，而它的注释还写着
#:   「过渡期 continue-on-error（观察 2 周后移除改 hard fail）」。真改成 hard fail
#:   的那天 CI 会立刻崩。
#:
#: 下面三条反向断言保证这条登记不会变成永久遮羞布：
#:   1. 登记项必须**真的仍然缺失**（脚本找回来了就必须删登记）；
#:   2. 登记项所在 job 必须**仍然** `continue-on-error: true`（有人改成 hard fail
#:      而脚本还没补回 ⇒ 立刻红）；
#:   3. 白名单不得增长（新出现的缺失一律红，不许往这里加）。
_KNOWN_MISSING: dict[str, str] = {
    "backend/scripts/audit_a7_a15_xlsx.py": "audit-xlsx-drift",
}


def test_every_declared_path_exists_on_disk() -> None:
    declared = _all_declared()
    assert declared, "两个 workflow 里一个 backend/*.py 路径都没解析到 —— 正则失效了"
    missing = {rel: wfs for rel, wfs in declared.items() if not (_REPO / rel).exists()}
    unexpected = {rel: wfs for rel, wfs in missing.items() if rel not in _KNOWN_MISSING}
    assert not unexpected, (
        "workflow 引用了磁盘上不存在的文件 ⇒ CI 会在该步直接失败：\n"
        + "\n".join(f"  {rel}  ({', '.join(wfs)})" for rel, wfs in sorted(unexpected.items()))
        + "\n（若确属他 lane 欠账，请连同「所在 job 仍是 continue-on-error」的证据一起"
        "登记到 _KNOWN_MISSING，不要直接放宽本条）"
    )


def test_known_missing_entries_are_still_missing() -> None:
    """棘轮反向断言：登记项被补回后必须删登记，否则白名单会烂成遮羞布。"""
    stale = [rel for rel in _KNOWN_MISSING if (_REPO / rel).exists()]
    assert not stale, (
        "下列路径已经存在了，请从 _KNOWN_MISSING 里删掉（棘轮只许变短）：\n"
        + "\n".join(f"  {rel}" for rel in sorted(stale))
    )


def test_known_missing_jobs_are_still_continue_on_error() -> None:
    """登记项被容忍的**前提**是它所在 job 不会让 CI 红。前提消失就必须红。

    🔴 不用文本匹配判 `continue-on-error` —— 那分不清是哪个 job 的。解析 YAML 取
    job 级字段（铁律㉖的同一条纪律：判断「真做了什么」不要靠文本 in）。
    """
    yaml = pytest.importorskip("yaml", reason="PyYAML 缺失时无法按 job 解析")
    doc = yaml.safe_load((_REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or {}
    for rel, job_name in sorted(_KNOWN_MISSING.items()):
        assert job_name in jobs, (
            f"_KNOWN_MISSING 登记 {rel} 属于 job `{job_name}`，但 ci.yml 里没有这个 job "
            "—— 登记已过期，请重新核对"
        )
        job = jobs[job_name] or {}
        assert job.get("continue-on-error") is True, (
            f"job `{job_name}` 不再是 continue-on-error，而它引用的 {rel} 仍然缺失 "
            "⇒ CI 会真的红。要么补回脚本，要么移除该步。"
        )
        steps_text = str(job.get("steps") or "")
        assert rel in steps_text, (
            f"job `{job_name}` 的 steps 里已经不引用 {rel} 了 —— 登记已过期，请删除"
        )


def test_every_declared_path_is_tracked_by_git() -> None:
    """🔴 存在但未跟踪 == CI 上不存在。这是本次实测踩到的形态。"""
    declared = _all_declared()
    untracked = {
        rel: wfs for rel, wfs in declared.items()
        if (_REPO / rel).exists() and not _is_tracked(rel)
    }
    assert not untracked, (
        "下列文件在你本地存在但**未纳入版本控制** —— workflow 引用它们，CI 上却拉不到：\n"
        + "\n".join(f"  {rel}  ({', '.join(wfs)})" for rel, wfs in sorted(untracked.items()))
        + "\n（这正是 Gate 5/6 本地全绿、CI 却什么都没跑的那个空洞）"
    )


def test_mutation_unknown_script_is_detected() -> None:
    """变异反证：往声明集合里塞一个不存在的脚本名 ⇒ 检查必须报出来。

    不改真 workflow 文件（那会污染仓库），直接对解析+判定函数做变异。
    """
    phantom = "backend/scripts/check/check_this_gate_does_not_exist_xyz.py"
    fake_text = f"      - run: python {phantom}\n"
    parsed = _declared_paths(fake_text)
    assert phantom in parsed, "正则没解析出注入的路径 —— 锚点没命中，不算证明"
    assert not (_REPO / phantom).exists(), "幻影路径竟然真存在，换一个名字"
    assert not _is_tracked(phantom)


def test_mutation_tracked_check_is_not_flagged() -> None:
    """反向变异：一个**已跟踪**的真实门禁不得被判红（防止把干净仓库判成有缺陷）。"""
    real = "backend/scripts/check/check_utf8_integrity.py"
    assert (_REPO / real).exists(), f"{real} 不在了，换一个已提交的门禁做正面样本"
    assert _is_tracked(real), f"{real} 未被 git 跟踪 —— 正面样本前提不成立"


def test_gate5_and_gate6_are_wired_into_governance_workflow() -> None:
    """正面钉子：本轮补的两个门禁必须真的出现在 governance workflow 里。

    否则「脚本入库了但 CI 不跑」—— 卡点形同虚设，与未入库没有实质差别。
    """
    wf = _REPO / ".github" / "workflows" / "governance-checks.yml"
    if not wf.exists():
        pytest.skip("governance-checks.yml 不存在")
    text = wf.read_text(encoding="utf-8")
    for rel in [
        "backend/scripts/check/check_row_table_formula_columns_consistency.py",
        "backend/scripts/check/check_store_item_two_way_parity.py",
        "backend/tests/scripts/test_check_row_table_formula_columns_consistency.py",
        "backend/tests/scripts/test_check_store_item_two_way_parity.py",
    ]:
        assert rel in text, f"governance-checks.yml 没有接入 {rel}"
        assert _is_tracked(rel), f"{rel} 未入库"
