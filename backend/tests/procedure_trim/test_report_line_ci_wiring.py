"""CI 接线与产物入库守卫（常驻，替代一次性验收脚本）。

Feature: procedure-trim-report-line-account-resolution — Task 15 收口（复盘补齐）
Requirements: 7.5
Validates: Property 22（CI job 可解析且无重名）,
           Property 21（部分：浏览器实测结论的可复验锚点）

═══ 为什么必须常驻 ═══

Task 15 加挂 CI job 时用的是一次性校验脚本（跑完即删）。复盘发现这让 **Property 22
没有常驻判据** —— 将来任何人改坏 `governance-checks.yml`（重名 job、缩进错、把本 spec
的 job 删掉、引用一个不存在的测试文件）都不会被发现，而 CI 自己在「job 被静默去重」
这种情形下**一片绿**（yaml 解析时后一个同名 job 覆盖前一个，前者从未运行）。

═══ 三类已实证的假绿形态 ═══

1. **重名 job 被 yaml 静默去重**：判据必须落在**原始文本**的顶层 job 行上，
   不能只看 `yaml.safe_load` 的 key 集合（后者已经去重了，查不出重名）。
2. **引用了不存在或未入库的测试文件**：本地有、HEAD 没有 ⇒ 干净 checkout 下 CI 挂，
   而本地全绿。判据 = 引用文件既要存在，又要**已被 git 跟踪**。
3. **门控正则写坏导致 job 恒跳过**：`scope` 步骤的 PATTERN 若不匹配本 spec 的核心
   文件，job 会静默 skip ⇒ 永远绿。判据 = PATTERN 必须命中本 spec 的关键路径。

🔴 本文件的判据都落在**仓库文件**上，不连库、不跑 npm，可进任何 CI。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve()
ROOT = _HERE.parents[3]
YML = ROOT / ".github" / "workflows" / "governance-checks.yml"

#: 本 spec 加挂的两个 job
MY_JOBS = (
    "report-line-account-resolution",
    "report-line-account-resolution-frontend",
)

#: 每个 job 的门控 PATTERN 必须命中的路径（改坏 PATTERN 会让 job 恒跳过而永远绿）。
#:
#: 🔴 **按 job 显式声明**，不要用子串过滤从一份总表里派生 —— 初版用
#: `"report_line_index" in p` 过滤，把 `backend/tests/.../test_report_line_index.py`
#: 也算进前端 job 的期望，而前端守卫压根不读后端测试文件 ⇒ 判据以「PATTERN 漏路径」
#: 的形态**假红**。期望集合本身写错时，判据的红绿都不可信。
GATED_PATHS: dict[str, tuple[str, ...]] = {
    "report-line-account-resolution": (
        "backend/app/services/four_table/report_line_index.py",
        "backend/app/services/trim_report_line_amounts.py",
        "backend/app/services/trim_decision_context.py",
        "backend/tests/procedure_trim/test_report_line_index.py",
        "backend/scripts/check/mutate_report_line_resolution_guards.py",
        "audit-platform/frontend/src/components/workpaper/composables/trimAmountSource.ts",
        "audit-platform/frontend/src/views/ProcedureTrimming.vue",
        "audit-platform/frontend/src/services/commonApi.ts",
    ),
    # 前端 job 只门控「前端面 + 后端索引模块」——
    # 后者因为与前端 `subjectPrefixOf` 的归一正则交叉锁死，改它必须重跑前端守卫。
    "report-line-account-resolution-frontend": (
        "audit-platform/frontend/src/components/workpaper/composables/trimAmountSource.ts",
        "audit-platform/frontend/src/components/workpaper/composables/procedureTrimDecision.ts",
        "audit-platform/frontend/src/views/ProcedureTrimming.vue",
        "audit-platform/frontend/src/services/commonApi.ts",
        "audit-platform/frontend/src/views/__tests__/trimAmountSourcePriority.spec.ts",
        "backend/app/services/four_table/report_line_index.py",
    ),
}


@pytest.fixture(scope="module")
def raw() -> str:
    assert YML.is_file(), f"workflow 不存在：{YML}"
    return YML.read_text(encoding="utf-8")


def _top_level_jobs(text: str) -> list[str]:
    """原始文本里的顶层 job 行（有序、**保留重复**）。

    🔴 不能用 `yaml.safe_load` 的 key —— 重名 job 会被静默去重，判不出重名。
    """
    body = text.split("\njobs:\n", 1)[-1]
    return re.findall(r"^  ([a-z0-9][a-z0-9-]*):\s*$", body, re.M)


def test_workflow_is_parsable(raw):
    """R7.5：workflow 可被 yaml 解析（缩进错会让整个文件失效）。"""
    yaml = pytest.importorskip("yaml", reason="PyYAML 未安装")
    doc = yaml.safe_load(raw)
    assert isinstance(doc, dict), "workflow 顶层不是映射"
    assert isinstance(doc.get("jobs"), dict), "workflow 无 jobs 段"


def test_no_duplicate_job_names(raw):
    """R7.5 / Property 22：无重名 job。

    重名时 yaml 静默保留后一个 ⇒ 前一个从未运行，而 CI 一片绿。
    """
    names = _top_level_jobs(raw)
    dups = sorted({n for n in names if names.count(n) > 1})
    assert not dups, (
        f"以下 job 重名（yaml 会静默去重，前一个从未运行）：{dups}"
    )


def test_duplicate_detector_is_not_a_no_op(raw):
    """🔴 反向自检：重名检测器对构造的重名样本必须报错。

    若它对重名视而不见，上一条就是空转 —— 无论 workflow 里有多少重名都会绿。
    """
    fake = raw.split("\njobs:\n", 1)[0] + "\njobs:\n  dup-job:\n    x: 1\n  dup-job:\n    y: 2\n"
    names = _top_level_jobs(fake)
    assert names.count("dup-job") == 2, f"检测器未抽到构造的重名：{names}"


def test_my_jobs_are_mounted(raw):
    """本 spec 的两个 job 仍挂在 workflow 上（被删掉即打红）。"""
    names = set(_top_level_jobs(raw))
    missing = [j for j in MY_JOBS if j not in names]
    assert not missing, (
        f"本 spec 的 CI job 缺失：{missing} —— 守卫不再进 CI，改坏实现不会被发现"
    )


def _job_segment(raw: str, job: str) -> str:
    m = re.search(r"^  %s:\s*$" % re.escape(job), raw, re.M)
    assert m, f"未定位到 job {job}"
    rest = raw[m.end():]
    nxt = re.search(r"^  [a-z0-9][a-z0-9-]*:\s*$", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def test_referenced_guards_exist_and_are_tracked(raw):
    """R7.5：job 引用的守卫文件既存在、又已被 git 跟踪。

    🔴 「存在」不够：本地有而 HEAD 没有（`??` 未跟踪）时，干净 checkout 下
    CI 必挂而本地全绿 —— 这是本平台反复出现的最贵一类假绿
    （本 spec 落地时实测本 spec 10 个产物 + 上游 2 个依赖全部未入库）。
    """
    refs: set[str] = set()
    for job in MY_JOBS:
        seg = _job_segment(raw, job)
        for m in re.finditer(r"(backend/[\w/.]+\.py|src/[\w/.]+\.spec\.ts)", seg):
            refs.add(m.group(1))
    assert refs, "两个 job 一个测试文件都没引用 —— job 是空壳"

    rel = [
        r if r.startswith("backend/") else f"audit-platform/frontend/{r}"
        for r in sorted(refs)
    ]
    missing = [r for r in rel if not (ROOT / r).is_file()]
    assert not missing, f"job 引用的文件不存在：{missing}"

    try:
        st = subprocess.run(
            ["git", "status", "--porcelain", "--", *rel],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"git 不可用（本条为入库判据）: {e!r}")
    untracked = sorted(
        ln[3:].strip().strip('"') for ln in (st.stdout or "").splitlines()
        if ln.startswith("??")
    )
    assert not untracked, (
        "job 引用的以下文件未被 git 跟踪 ⇒ 干净 checkout 下 CI 必挂："
        f"{untracked}"
    )


def test_scope_gate_covers_this_spec_surface(raw):
    """R7.5：门控 PATTERN 命中本 spec 的核心文件（写坏会让 job 恒跳过而永远绿）。"""
    misses: list[str] = []
    for job in MY_JOBS:
        seg = _job_segment(raw, job)
        m = re.search(r"PATTERN='([^']+)'", seg)
        assert m, f"job {job} 无 scope 门控 PATTERN"
        pattern = re.compile(m.group(1))
        for path in GATED_PATHS[job]:
            if not pattern.search(path):
                misses.append(f"{job}: {path}")
    assert not misses, (
        f"门控 PATTERN 漏掉以下路径 ⇒ 改这些文件时 job 会静默跳过：{misses}"
    )


def test_scope_gate_detector_is_not_a_no_op(raw):
    """🔴 反向自检：门控判据对「PATTERN 明显不匹配」必须报错。

    若一个只匹配 `^nothing/` 的 PATTERN 也能通过，上一条就是空转。
    """
    bogus = re.compile(r"^nothing-matches-this/")
    hit = [p for p in GATED_PATHS[MY_JOBS[0]] if bogus.search(p)]
    assert not hit, f"构造的空 PATTERN 竟命中了路径：{hit}"
    # 正向：真实 PATTERN 至少命中一条（证明不是拿空集合在比）
    m = re.search(r"PATTERN='([^']+)'", _job_segment(raw, MY_JOBS[0]))
    assert m
    real = re.compile(m.group(1))
    assert any(real.search(p) for p in GATED_PATHS[MY_JOBS[0]]), (
        "真实 PATTERN 一条都没命中 —— 期望集合或 PATTERN 抽取有误"
    )


def test_scope_gate_mutation_goes_red_in_memory(raw):
    """🔴 内存内变异：把真实 PATTERN 里的索引模块那段删掉，判据必须发现漏项。

    ``governance-checks.yml`` 是跨 spec 共享热点文件，平台铁律禁止对它做**磁盘**变异
    （并发会话会互相回退；脚本被打断时变异会留在工作树，下一轮又把变异版当基线）。
    ⇒ 正解 = 读真实文本 → 内存里改坏 → 断言判据打红。强度与磁盘变异等价、零残留。
    """
    seg = _job_segment(raw, MY_JOBS[1])
    m = re.search(r"PATTERN='([^']+)'", seg)
    assert m, "未抽到前端 job 的 PATTERN"
    original = m.group(1)
    # 变异 = 去掉「后端索引模块」那一段（改归一正则时前端守卫就不会重跑了）
    mutated = original.replace(
        r"backend/app/services/four_table/report_line_index\.py", "nothing-x"
    )
    assert mutated != original, "变异未施加（锚点未命中真实 PATTERN）"
    pattern = re.compile(mutated)
    misses = [p for p in GATED_PATHS[MY_JOBS[1]] if not pattern.search(p)]
    assert misses, (
        "删掉索引模块后判据仍认为门控完整 ⇒ 判据空转："
        "改 normalize_wp_code 时前端交叉锁死守卫不会重跑，而没人会发现"
    )
    assert any("report_line_index" in x for x in misses), (
        f"打红了但漏项不是索引模块（判据错行）：{misses}"
    )


def test_scope_gate_fails_open_toward_running(raw):
    """R7.5：门控方向必须 fail-open-toward-running（取不到 base 时跑，而不是跳）。

    反向（默认跳过）会让门控一坏就静默关闸 —— 那是假绿。
    """
    for job in MY_JOBS:
        seg = _job_segment(raw, job)
        assert "RUN=true" in seg, f"job {job} 的门控无 RUN=true 默认值"
        # 默认赋值必须出现在条件判断之前
        idx_default = seg.index("RUN=true")
        idx_cond = seg.find('if [ -n "${BASE:-}" ]')
        assert idx_cond > idx_default, (
            f"job {job} 的 RUN 默认值不在条件判断之前 ⇒ base 取不到时会静默跳过"
        )


def test_mutation_script_is_wired_with_skip_live_only(raw):
    """R7.2 / R7.5：变异脚本进 CI，且带 `--skip-live-only`。

    🔴 不带该开关时，三条「预期红判据只有连库判据」的变异在无库环境会 skip
    ⇒ 差集为空 ⇒ 被判 GREEN(守卫缺陷) ⇒ 本 job **假红**。
    """
    seg = _job_segment(raw, MY_JOBS[0])
    assert "mutate_report_line_resolution_guards.py" in seg, "变异脚本未进 CI"
    assert "--skip-live-only" in seg, (
        "变异脚本未带 --skip-live-only ⇒ 连库依赖的变异会被误判成 GREEN 而让 CI 假红"
    )


def test_live_verify_script_not_wired_into_ci(raw):
    """真实库验收脚本**不得**进 CI（CI 无库，它会 FATAL）。

    它是本地只读验收工具；进 CI 等于给自己加一条恒红的步骤。
    """
    for job in MY_JOBS:
        seg = _job_segment(raw, job)
        assert "verify_report_line_amounts_live.py" not in re.sub(
            r"^\s*#.*$", "", seg, flags=re.M
        ), f"job {job} 把真实库验收脚本挂进了 CI —— 无库环境必 FATAL"


def test_browser_verification_anchor_exists():
    """Property 21 的可复验锚点：浏览器实测的期望值有自动化判据兜住。

    浏览器实测本身无法进 CI，但它的**核心数值断言**（E 循环金额 = `BS-002` 公式的
    独立聚合结果）已由连库守卫覆盖。本条钉死那个锚点仍在，使「实测结论」不至于
    只存在于 tasks.md 的文字里。
    """
    guard = ROOT / "backend" / "tests" / "procedure_trim" / "test_trim_report_line_amounts.py"
    src = guard.read_text(encoding="utf-8")
    assert "test_live_bs002_matches_independent_sum" in src, (
        "BS-002 独立聚合复核判据消失 —— 浏览器实测的期望值失去自动化锚点"
    )
    assert "test_amounts_behavior_e1_resolves_on_live_project" in src, (
        "E1 解析成功判据消失 —— 本 spec 的立项缺陷失去回归保护"
    )
