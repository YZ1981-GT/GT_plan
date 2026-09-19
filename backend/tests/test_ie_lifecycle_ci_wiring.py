"""导入导出全生命周期 —— CI 接线守卫（Wave 6 Task 22）

spec: workpaper-import-export-lifecycle-closure（R7.4）

## 为什么 CI 配置也要守

`governance-checks.yml` 有 4300+ 行、几十个 job。往里加 job 有三种静默失效：

1. **yaml 语法/缩进错** ⇒ 整个 workflow 不再运行（不只是新 job），
   而本地跑测试全绿，只有 push 后在 Actions 页面才看到 red X。
2. **job 名重复** ⇒ 后者覆盖前者，被覆盖的那批守卫**从此不再跑**，
   CI 却显示全绿（因为它确实没失败，只是没执行）。
3. **引用的测试文件不存在 / 路径写错** ⇒ pytest 报 `file or directory not found`，
   若该 step 恰好带 `|| true` 或 `continue-on-error` 就彻底静默。

⇒ 本文件把这三条变成本地可跑的判据，不必等 push。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml", reason="需要 PyYAML 解析 workflow")

_REPO = Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO / ".github" / "workflows" / "governance-checks.yml"

#: 本 spec 新增的两个 job
_JOB_BACKEND = "wp-import-export-lifecycle"
_JOB_FRONTEND = "wp-import-export-lifecycle-frontend"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert _WORKFLOW.is_file(), f"workflow 不存在: {_WORKFLOW}"
    data = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict), "workflow 顶层应为 mapping"
    return data


@pytest.fixture(scope="module")
def raw_text() -> str:
    return _WORKFLOW.read_text(encoding="utf-8")


def test_workflow_is_parseable(workflow: dict) -> None:
    """yaml.safe_load 可解析 —— 语法错会让**整个** workflow 停摆。"""
    assert "jobs" in workflow, "workflow 缺 jobs 段"
    assert isinstance(workflow["jobs"], dict)
    assert len(workflow["jobs"]) > 20, (
        f"只解析出 {len(workflow['jobs'])} 个 job，疑似被截断"
    )


def test_no_duplicate_job_names(raw_text: str) -> None:
    """🔴 job 名不得重复。

    yaml 解析时后者会**静默覆盖**前者 —— 被覆盖的 job 从此不跑，
    而 CI 不会报错。故必须在原文里按缩进层级数一遍，不能只看解析结果
    （解析结果里重复的键早就丢了，看不出来）。
    """
    names = re.findall(r"^  ([a-z][a-z0-9-]*):\s*$", raw_text, re.M)
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, (
        f"job 名重复（后者会静默覆盖前者，被覆盖的守卫从此不跑）: {dupes}"
    )


def test_both_new_jobs_present(workflow: dict) -> None:
    """本 spec 的两个 job 都在。"""
    jobs = workflow["jobs"]
    for name in (_JOB_BACKEND, _JOB_FRONTEND):
        assert name in jobs, f"CI 缺 job: {name}"
        assert jobs[name].get("runs-on"), f"{name} 缺 runs-on"
        assert jobs[name].get("steps"), f"{name} 缺 steps"


def _step_commands(job: dict) -> str:
    return "\n".join(
        str(s.get("run", "")) for s in job.get("steps", []) if isinstance(s, dict)
    )


def test_backend_job_references_existing_test_files(workflow: dict) -> None:
    """🔴 job 里引用的每个 pytest 目标文件都必须真实存在。

    路径写错时 pytest 报 "file or directory not found"，而该 step 若带
    `|| true` 就彻底静默 —— CI 绿着，守卫一条没跑。
    """
    cmds = _step_commands(workflow["jobs"][_JOB_BACKEND])
    targets = re.findall(r"(backend/tests/[\w/]+\.py)", cmds)
    assert targets, "后端 job 里没解析出任何 pytest 目标 —— 抽取失效"
    missing = sorted({t for t in targets if not (_REPO / t).is_file()})
    assert not missing, f"CI 引用了不存在的测试文件: {missing}"


def test_backend_job_references_existing_scripts(workflow: dict) -> None:
    """脚本路径同理必须存在。"""
    cmds = _step_commands(workflow["jobs"][_JOB_BACKEND])
    scripts = re.findall(r"(backend/scripts/[\w/]+\.py)", cmds)
    assert scripts, "后端 job 里没解析出任何脚本调用"
    missing = sorted({s for s in scripts if not (_REPO / s).is_file()})
    assert not missing, f"CI 引用了不存在的脚本: {missing}"


def test_frontend_job_references_existing_specs(workflow: dict) -> None:
    """前端 spec 路径必须存在（相对 audit-platform/frontend）。"""
    job = workflow["jobs"][_JOB_FRONTEND]
    wd = (job.get("defaults") or {}).get("run", {}).get("working-directory")
    assert wd == "audit-platform/frontend", f"前端 job 的 working-directory 异常: {wd}"

    cmds = _step_commands(job)
    specs = re.findall(r"(src/components/workpaper/[\w/]+\.spec\.ts)", cmds)
    assert specs, "前端 job 里没解析出任何 spec 目标"
    missing = sorted({s for s in specs if not (_REPO / wd / s).is_file()})
    assert not missing, f"CI 引用了不存在的前端 spec: {missing}"


def test_all_backend_guard_files_are_mounted(workflow: dict) -> None:
    """🔴 本 spec 的每个后端守卫文件都必须被 CI 挂载。

    漏挂一个 = 该文件的守卫在 CI 里全体缺席，只在本地偶尔跑到。
    守卫清单复用变异脚本的 `GUARD_FILES`（单一真源，不在此另抄）。
    """
    import sys

    if str(_REPO / "backend") not in sys.path:
        sys.path.insert(0, str(_REPO / "backend"))
    from scripts.diagnose.mutate_ie_lifecycle_guards import GUARD_FILES

    cmds = _step_commands(workflow["jobs"][_JOB_BACKEND])
    backend_guards = {
        rel for rel in GUARD_FILES.values()
        if rel.startswith("backend/tests/")
        # x3 守卫有自己的 CI job（x3-adjustment-entry-import-export spec 产物），
        # 不挂在本 spec 的 job 里。
        and "x3_" not in rel and "/test_x3_" not in rel
    }
    unmounted = sorted(rel for rel in backend_guards if rel not in cmds)
    assert not unmounted, (
        "以下后端守卫未被 CI 挂载（CI 里全体缺席）：\n"
        + "\n".join(f"  {u}" for u in unmounted)
    )


def test_all_frontend_guard_files_are_mounted(workflow: dict) -> None:
    """前端守卫同样必须全部挂载（含 continue-on-error 的那个）。"""
    import sys

    if str(_REPO / "backend") not in sys.path:
        sys.path.insert(0, str(_REPO / "backend"))
    from scripts.diagnose.mutate_ie_lifecycle_guards import GUARD_FILES

    cmds = _step_commands(workflow["jobs"][_JOB_FRONTEND])
    fe_guards = {
        rel.replace("audit-platform/frontend/", "")
        for rel in GUARD_FILES.values()
        if rel.endswith(".spec.ts")
    }
    unmounted = sorted(rel for rel in fe_guards if rel not in cmds)
    assert not unmounted, f"以下前端守卫未被 CI 挂载: {unmounted}"


def test_idempotent_scripts_use_check_only(workflow: dict) -> None:
    """🔴 CI 里的幂等脚本只许 `--check`，不得 `--apply`。

    `--apply` 会改 catalog / 生成文件；在 CI 跑等于让流水线改版本库产物，
    且并发 job 之间会互相覆盖。
    """
    cmds = _step_commands(workflow["jobs"][_JOB_BACKEND])
    for banned in ("--apply", "--confirm-destructive", "--dry-run"):
        assert banned not in cmds, (
            f"CI 后端 job 出现 {banned!r} ⇒ 流水线会改版本库产物或执行破坏性操作"
        )
    assert "--check" in cmds, "未见任何 --check 调用，幂等校验缺席"


def test_mutation_script_only_lists_in_ci(workflow: dict) -> None:
    """变异脚本在 CI 里只许 `--list`。

    `--run` 会真改源文件再还原；CI 并发环境下若被中断，残留的 `.mutbak`
    会让后续 job 跑在被改坏的代码上。
    """
    cmds = _step_commands(workflow["jobs"][_JOB_BACKEND])
    if "mutate_ie_lifecycle_guards.py" in cmds:
        assert "--list" in cmds, "变异脚本应以 --list 模式调用"
        assert not re.search(r"mutate_ie_lifecycle_guards\.py[^\n]*--run", cmds), (
            "CI 里不得跑 --run（会改源文件；中断后残留 .mutbak 影响后续 job）"
        )


def test_orphan_baseline_is_report_mode(workflow: dict) -> None:
    """孤儿基线那条必须是 continue-on-error（它有意留红）。

    否则 CI 会长期红，红久了就没人看 —— 比不挂更糟。
    """
    steps = workflow["jobs"][_JOB_FRONTEND]["steps"]
    orphan_steps = [
        s for s in steps if isinstance(s, dict) and "ieOrphanBaseline" in str(s.get("run", ""))
    ]
    assert orphan_steps, "前端 job 未挂 ieOrphanBaseline"
    for s in orphan_steps:
        assert s.get("continue-on-error") is True, (
            "ieOrphanBaseline 有 1 条有意留红的占位断言，"
            "必须 continue-on-error，否则该 job 长期红"
        )


def test_strict_steps_are_not_silenced(workflow: dict) -> None:
    """严格 step 不得用 `|| true` 消音。

    `|| true` 会让失败变成成功 —— 比不挂载更有害，因为看起来是绿的。
    """
    for job_name in (_JOB_BACKEND, _JOB_FRONTEND):
        job = workflow["jobs"][job_name]
        for step in job.get("steps", []):
            if not isinstance(step, dict):
                continue
            run = str(step.get("run", ""))
            if not run:
                continue
            if step.get("continue-on-error") is True:
                continue  # 已显式声明报告模式，另有断言校验其正当性
            assert "|| true" not in run, (
                f"{job_name} 的 step {step.get('name')!r} 用 `|| true` 消音 ⇒ "
                "失败会被伪装成成功"
            )
