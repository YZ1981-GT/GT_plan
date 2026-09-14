"""CI 接线守卫：`governance-checks.yml` 的 I 循环 job 不得与磁盘脱钩。

## 为什么 CI 配置也要守

`governance-checks.yml` 有 4800+ 行、140+ 个 job，且**不被任何测试解析**。
往里加 job 有四种静默失效，任何单测都查不出来：

1. **幽灵过滤器** —— `npx vitest run <不存在的文件>` **不报错**。
   vitest 的位置参数是*子串过滤器*而非文件路径，只要有一个命中，
   不命中的那个被**静默忽略**（`test_k_cycle_ci_wiring` 已本地实测：
   两个过滤器其中一个是从未存在的文件 ⇒ `Test Files 1 passed (1)`、exit 0）。
   于是 yml 读起来像跑了两组守卫、实际只跑一组，且**永远不会有人发现**。
2. **`|| echo "::warning::…"` 兜底** —— 步骤真失败也只留一条 warning、job 照绿。
3. **重名 job** —— `yaml.safe_load` 对重复 key **静默保留最后一个**，
   前一个 job 连同它的全部步骤消失且零报错。故须在**原始文本**上查重。
   （本 spec Task 21 的 tasks.md 原文写「新增 `i-cycle-frontend`」，而该 job
   **前一个 spec 已建**；照抄会造成重名、把既有 5 个前端守卫整段吞掉。
   实际处置 = 新增 `i-cycle-extraction-closure` + **扩充**既有 `i-cycle-frontend`。）
4. **引用了不存在的文件** —— pytest 会报 `file or directory not found` 而红，
   但 vitest 不会（见 1）；且 `python <script> --check` 若脚本被改名则整 job 红。
   故两侧都要 `Path.exists()` 逐个断言。

判据全部落到「真实文件系统 / 真实解析」上，不做字符串存在性检查。

spec: .kiro/specs/i-cycle-extraction-formula-and-disclosure-closure/
      Task 21 / Requirements 11.4
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_YML = _ROOT / ".github/workflows/governance-checks.yml"
_FE_DIR = _ROOT / "audit-platform/frontend"

#: 本 spec Task 21 新增的 job
_NEW_JOB = "i-cycle-extraction-closure"

#: 与 I 循环相关的全部 job（前一个 spec 的三个也一并纳管 —— 假绿可能在那里）
_I_JOBS = (
    "note-i-cycle-structure",
    "i-cycle-extraction",
    "i-cycle-frontend",
    _NEW_JOB,
)

#: 本 spec 产出、**必须**被某个 I job 覆盖的后端守卫
_REQUIRED_BACKEND_GUARDS = (
    "backend/tests/four_table/test_i_cycle_row_code_evidence.py",
    "backend/tests/four_table/test_i_cycle_accounts.py",
    "backend/tests/four_table/test_i5_absent_account.py",
    "backend/tests/test_i_cycle_formula_presets.py",
    "backend/tests/test_note_i_cycle_structure.py",
)

#: 必须被 `--check` 的幂等脚本
_REQUIRED_CHECK_SCRIPTS = (
    "backend/scripts/fix/fix_note_i_cycle_structure.py",
    "backend/scripts/fix/fix_i_cycle_prefill_presets.py",
)

#: 本 spec 产出、必须被前端 job 覆盖的守卫（相对 `audit-platform/frontend`）
_REQUIRED_FRONTEND_SPECS = (
    "src/components/workpaper/composables/__tests__/iCycleAccountScope.spec.ts",
    "src/components/workpaper/composables/__tests__/iCycleDynamicRows.spec.ts",
    "src/components/workpaper/composables/__tests__/iCycleDisclosureWiring.spec.ts",
    "src/components/workpaper/composables/__tests__/iCycleNoteSubtableContract.spec.ts",
    "src/components/workpaper/composables/__tests__/iCycleAdjudicationSeed.spec.ts",
    "src/components/workpaper/composables/__tests__/iDisclosureColumns.spec.ts",
)


# ─── 原始文本切块（不用 safe_load：要看 `run:` 原文与重复 key） ─────────────────


@pytest.fixture(scope="module")
def raw() -> str:
    assert _YML.is_file(), f"workflow 不存在: {_YML}"
    return _YML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def job_blocks(raw: str) -> dict[str, str]:
    """按缩进切出每个 job 的原始文本块（含其全部步骤）。"""
    lines = raw.splitlines()
    starts: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = re.match(r"^  ([a-z0-9][\w-]*):\s*$", ln)
        if m:
            starts.append((i, m.group(1)))
    blocks: dict[str, str] = {}
    for idx, (line_no, name) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        blocks.setdefault(name, "\n".join(lines[line_no:end]))
    return blocks


@pytest.fixture(scope="module")
def parsed(raw: str) -> dict:
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict), "governance-checks.yml 顶层不是映射"
    return data


# ─── 可解析性与 job 存在性 ────────────────────────────────────────────────────


def test_workflow_is_parseable(parsed: dict) -> None:
    """`yaml.safe_load` 可解析 —— 语法错会让**整个** workflow 停摆（不只是新 job）。"""
    assert "jobs" in parsed, "workflow 缺 jobs 段"
    assert isinstance(parsed["jobs"], dict), "jobs 段不是映射"
    assert len(parsed["jobs"]) >= 100, f"job 数 {len(parsed['jobs'])} 异常偏少，疑似解析截断"


def test_all_i_cycle_jobs_exist(parsed: dict) -> None:
    """四个 I 循环 job 都在（本 spec 新增的 + 前一个 spec 的三个）。"""
    jobs = parsed["jobs"]
    missing = [j for j in _I_JOBS if j not in jobs]
    assert not missing, f"以下 I 循环 job 不存在：{missing}"


def test_no_duplicate_job_names(raw: str) -> None:
    """重名 job 必打红。

    🔴 `yaml.safe_load` 对重复 key **静默保留最后一个** ⇒ 前一个 job 整段消失、
    解析零报错。故只能在**原始文本**上数。
    """
    names = re.findall(r"^  ([a-z0-9][\w-]*):\s*$", raw, re.M)
    seen: dict[str, int] = {}
    dups: list[str] = []
    for n in names:
        seen[n] = seen.get(n, 0) + 1
        if seen[n] == 2:
            dups.append(n)
    assert not dups, f"job 重名（safe_load 会静默吞掉前一个）：{dups}"


def test_new_job_has_python_and_deps(job_blocks: dict[str, str]) -> None:
    """新 job 必须装好 Python 与依赖 —— 否则 pytest / openpyxl 直接 ImportError。"""
    block = job_blocks[_NEW_JOB]
    assert "actions/setup-python@v5" in block, f"{_NEW_JOB} 缺 setup-python"
    assert "actions/checkout@v4" in block, f"{_NEW_JOB} 缺 checkout"
    m = re.search(r"pip install ([^\n]+)", block)
    assert m, f"{_NEW_JOB} 缺 pip install 步骤"
    deps = m.group(1)
    for pkg in ("pytest", "openpyxl"):
        assert pkg in deps, (
            f"{_NEW_JOB} 的依赖缺 {pkg}（本 spec 守卫要 openpyxl 直读源 xlsx）：{deps!r}"
        )


# ─── 引用的文件必须真实存在 ───────────────────────────────────────────────────


def _referenced_pytest_paths(block: str) -> list[str]:
    """从 job 块里抽 pytest 的路径参数。"""
    out: list[str] = []
    for m in re.finditer(r"python -m pytest ([^\n]+)", block):
        for tok in m.group(1).split():
            if tok.endswith(".py") or "/tests/" in tok:
                out.append(tok)
    return out


def _referenced_scripts(block: str) -> list[str]:
    """从 job 块里抽 `python <script> --check` 的脚本路径。"""
    return re.findall(r"python (backend/scripts/[^\s]+\.py)", block)


def _referenced_vitest_specs(block: str) -> list[str]:
    return re.findall(r"(src/components/[^\s]+\.spec\.ts)", block)


@pytest.mark.parametrize("job", [j for j in _I_JOBS if j != "i-cycle-frontend"])
def test_backend_job_paths_exist(job: str, job_blocks: dict[str, str]) -> None:
    """后端 job 引用的 pytest 路径与脚本必须在磁盘上存在。"""
    block = job_blocks[job]
    refs = _referenced_pytest_paths(block) + _referenced_scripts(block)
    assert refs, f"{job} 未引用任何 pytest 路径或脚本 ⇒ 该 job 是空跑"
    missing = [r for r in refs if not (_ROOT / r).exists()]
    assert not missing, f"{job} 引用了不存在的文件：{missing}"


def test_frontend_job_specs_exist(job_blocks: dict[str, str]) -> None:
    """🔴 前端 job 引用的 spec 必须存在 —— vitest 对不存在的过滤器**静默忽略**。

    这是本文件最重要的一条：pytest 引用错文件会红，vitest 不会。
    """
    block = job_blocks["i-cycle-frontend"]
    specs = _referenced_vitest_specs(block)
    assert specs, "i-cycle-frontend 未引用任何 spec ⇒ 该 job 是空跑"
    missing = [s for s in specs if not (_FE_DIR / s).exists()]
    assert not missing, (
        f"i-cycle-frontend 引用了不存在的 spec：{missing}\n"
        f"🔴 vitest 的位置参数是**子串过滤器**，不命中的会被静默忽略、job 仍绿 ——"
        f"yml 读起来像跑了、实际没跑"
    )


# ─── 覆盖面：本 spec 的守卫一个都不能漏 ────────────────────────────────────────


def test_required_backend_guards_are_covered(job_blocks: dict[str, str]) -> None:
    """本 spec 的 5 个后端守卫必须至少被一个 I job 引用。"""
    covered: set[str] = set()
    for job in _I_JOBS:
        if job not in job_blocks:
            continue
        covered.update(_referenced_pytest_paths(job_blocks[job]))
    missing = [g for g in _REQUIRED_BACKEND_GUARDS if g not in covered]
    assert not missing, (
        f"以下后端守卫不在任何 I job 内 ⇒ 回退不会被 CI 发现：{missing}\n"
        f"已覆盖：{sorted(covered)}"
    )


def test_required_check_scripts_are_covered(job_blocks: dict[str, str]) -> None:
    """两个幂等脚本必须被 `--check`（只跑不带 --check 等于没验幂等）。"""
    for script in _REQUIRED_CHECK_SCRIPTS:
        hit = False
        for job in _I_JOBS:
            block = job_blocks.get(job, "")
            if re.search(rf"python {re.escape(script)}\s+--check", block):
                hit = True
                break
        assert hit, f"{script} 未被任何 I job 以 `--check` 调用"


def test_required_frontend_specs_are_covered(job_blocks: dict[str, str]) -> None:
    """本 spec 的 6 个前端守卫必须被 `i-cycle-frontend` 引用。"""
    block = job_blocks["i-cycle-frontend"]
    specs = set(_referenced_vitest_specs(block))
    missing = [s for s in _REQUIRED_FRONTEND_SPECS if s not in specs]
    assert not missing, (
        f"以下前端守卫不在 i-cycle-frontend 内：{missing}\n已覆盖：{sorted(specs)}"
    )


# ─── 不得有兜底吞错 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("job", _I_JOBS)
def test_no_warning_fallback_in_i_jobs(job: str, job_blocks: dict[str, str]) -> None:
    """`|| echo "::warning::…"` 会让步骤失败也照绿 —— I 循环 job 一律禁用。"""
    block = job_blocks.get(job, "")
    offenders = [
        ln.strip() for ln in block.splitlines()
        if "::warning::" in ln or re.search(r"\|\|\s*(echo|true)\b", ln)
    ]
    assert not offenders, f"{job} 含兜底吞错写法：{offenders}"


@pytest.mark.parametrize("job", _I_JOBS)
def test_no_continue_on_error(job: str, job_blocks: dict[str, str]) -> None:
    """`continue-on-error: true` 同样让 job 恒绿。"""
    block = job_blocks.get(job, "")
    assert "continue-on-error: true" not in block, f"{job} 含 continue-on-error"


# ─── 反向自检 ────────────────────────────────────────────────────────────────


def test_reverse_self_check_path_extractors_work(job_blocks: dict[str, str]) -> None:
    """反向自检：三个抽取器在真实 job 块上都必须抽到东西（抽不到 = 判据空转）。"""
    be = _referenced_pytest_paths(job_blocks[_NEW_JOB])
    sc = _referenced_scripts(job_blocks[_NEW_JOB])
    fe = _referenced_vitest_specs(job_blocks["i-cycle-frontend"])
    assert len(be) >= 4, f"后端路径抽取器只抽到 {be}"
    assert len(sc) >= 2, f"脚本抽取器只抽到 {sc}"
    assert len(fe) >= 6, f"前端 spec 抽取器只抽到 {len(fe)} 个"


def test_reverse_self_check_extractors_reject_nonexistent() -> None:
    """反向自检：抽取器对构造的假路径必须能抽出来（这样 exists 断言才有意义）。"""
    fake_be = "python -m pytest backend/tests/test_definitely_not_here.py -q"
    assert _referenced_pytest_paths(fake_be) == ["backend/tests/test_definitely_not_here.py"]
    fake_fe = "npx vitest run src/components/workpaper/__tests__/nope.spec.ts"
    assert _referenced_vitest_specs(fake_fe) == ["src/components/workpaper/__tests__/nope.spec.ts"]
    fake_sc = "python backend/scripts/fix/not_a_real_script.py --check"
    assert _referenced_scripts(fake_sc) == ["backend/scripts/fix/not_a_real_script.py"]
    # 且它们确实不在磁盘上 —— 否则上面的 exists 断言恒真
    assert not (_ROOT / "backend/tests/test_definitely_not_here.py").exists()
    assert not (_FE_DIR / "src/components/workpaper/__tests__/nope.spec.ts").exists()


def test_reverse_self_check_job_block_slicing(job_blocks: dict[str, str]) -> None:
    """反向自检：切块不得把相邻 job 的内容混进来。"""
    block = job_blocks[_NEW_JOB]
    assert block.startswith(f"  {_NEW_JOB}:"), f"切块起点错：{block[:60]!r}"
    others = [j for j in ("k-cycle-four-table-extraction", "i-cycle-frontend") if f"  {j}:" in block]
    assert not others, f"{_NEW_JOB} 的块里混进了 {others}"
