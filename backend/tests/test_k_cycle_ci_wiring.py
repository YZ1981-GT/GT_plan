"""CI 接线守卫：`governance-checks.yml` 的 K 循环 job 不得与磁盘脱钩。

本文件拦的是**「看得见的覆盖面」与「真实覆盖面」脱钩**这一类缺陷 —— 它们在
任何单测里都查不出来，因为 yml 不被任何测试解析：

1. **幽灵过滤器**：`npx vitest run <不存在的文件>` **不报错**。vitest 的位置参数是
   *子串过滤器*而非文件路径，只要有一个命中，不命中的那个被**静默忽略**
   （2026-08-12 本地实测：`kCycleAccountScope.spec.ts` + 从未存在的
   `kCycleFourTableWiring.spec.ts` 两个过滤器 ⇒ `Test Files 1 passed (1)`、exit 0）。
   于是 yml 读起来像跑了两组守卫，实际只跑一组，且**永远不会有人发现**。
2. **`|| echo "::warning::…"` 兜底**：步骤真失败也只留一条 warning、job 照绿。
   该写法通常是"守卫还没建好"时期的临时脚手架，守卫建好后没人回来拆。
3. **连库守卫无声掉队**：本 spec 有 2 个守卫按 Property 1 要求「连不上库判红而非
   skip」，放进 CI 必然全红（CI 的 postgres 只跑迁移，而 `report_config` /
   `account_chart` 都不由迁移灌数）。正确处置是**登记为本地闸门**；错误处置是
   悄悄不提。本文件要求二者必居其一。
4. **重名 job**：`yaml.safe_load` 对重复 key **静默保留最后一个**，前一个 job
   连同它的全部步骤消失且不报错。故须在**原始文本**上查重。

判据全部落到「真实文件系统 / 真实解析」上，不做字符串存在性检查。

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 13.10, 13.11
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_YML = _ROOT / ".github/workflows/governance-checks.yml"
_FE_DIR = _ROOT / "audit-platform/frontend"
_MUTATE = _ROOT / "backend/scripts/diagnose/mutate_k_cycle_guards.py"

#: 本 spec 新增的 job 名
_JOB = "k-cycle-extraction-formula-closure"

#: 与本 spec 相关的全部 K job（前一个 spec 的两个 job 也一并纳管 —— 假绿就在那里）
_K_JOBS = (
    "k-cycle-four-table-extraction",
    "k-cycle-frontend",
    _JOB,
)

#: 🔴 **显式登记**的本地闸门守卫：连不上库判红而非 skip，故不进 CI。
#:
#: 登记不是豁免 —— `test_db_guards_are_registered_as_local_only` 会反向要求
#: 名单里的每个文件**确实**连库（写死一个离线守卫进来会被打红）。
_LOCAL_ONLY_DB_GUARDS = {
    "backend/tests/four_table/test_k_cycle_row_code_evidence.py":
        "Property 1 要求连库反查 report_config 四变体；CI 的 PG 无该表数据",
    "backend/tests/four_table/test_k_cycle_resolution_live.py":
        "Requirement 2.5 要求真跑 resolve_report_line_accounts；CI 的 PG 无 account_chart 数据",
    "backend/tests/four_table/test_note_k_row_code_evidence.py":
        "Requirement 11.2 要求段首码与 report_config 连库对账；CI 的 PG 无 report_config 数据。"
        "该文件的离线判据（模板齐备 / 段可定位 / 合计行在可写区外）另由 "
        "fix_note_k_report_row_codes.py --check 在 CI 里看守",
}

#: 连库特征名（AST 判定用，见 `_is_db_guard`）
_DB_IMPORT_MODULES = ("app.core.database", "sqlalchemy.ext.asyncio")
_DB_NAMES = frozenset({"create_async_engine", "async_sessionmaker", "AsyncEngine"})
_DB_ENV = frozenset({"DATABASE_URL"})


def _is_db_guard(path: Path) -> bool:
    """AST 判定「该守卫是否需要真实数据库」。

    🔴 **必须走 AST，不能正则扫文本**：本文件自己就得写出这些标识符（清单、正则、
    注释、断言消息都会提到 `create_async_engine` / `DATABASE_URL`），正则扫文本会把
    **本文件自身**判成连库守卫 —— 初版就是这么翻的：`_DB_MARK` 的模式串本身命中了
    自己，于是「连库守卫未登记」在基线上恒红，还顺带把两条变异污染成
    GREEN / WRONG-TEST（基线脏 ⇒ 差集把真失败减掉了）。

    判据只认三种**结构**：
    1. `from app.core.database import …` / `from sqlalchemy.ext.asyncio import …`
    2. 直接引用 `create_async_engine` 等引擎构造名（`Name` 或 `Attribute`）
    3. 从环境读 `DATABASE_URL`（`os.environ[...]` / `os.getenv(...)`）
    """
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if any(node.module.startswith(m) for m in _DB_IMPORT_MODULES):
                return True
        elif isinstance(node, ast.Import):
            if any(a.name.startswith(_DB_IMPORT_MODULES) for a in node.names):
                return True
        elif isinstance(node, ast.Name) and node.id in _DB_NAMES:
            return True
        elif isinstance(node, ast.Attribute) and node.attr in _DB_NAMES:
            return True
    # `os.environ["DATABASE_URL"]` / `os.getenv("DATABASE_URL")` 的结构化判定
    # （裸字符串出现在清单/注释里不算 —— 必须真的被下标或实参使用）
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value in _DB_ENV:
                return True
        if isinstance(node, ast.Call):
            for a in node.args:
                if isinstance(a, ast.Constant) and a.value in _DB_ENV:
                    return True
    return False

#: 假绿兜底写法
_FAKE_PASS = re.compile(r"\|\|\s*(?:echo|true)\b|continue-on-error:\s*true")


# ─────────────────────────────────────────────────────────────────────────────
# 解析
# ─────────────────────────────────────────────────────────────────────────────


def _text() -> str:
    if not _YML.exists():  # pragma: no cover - 仓库结构变动
        pytest.fail(f"找不到 {_YML}")
    return _YML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def raw() -> str:
    return _text()


@pytest.fixture(scope="module")
def doc(raw: str) -> dict:
    # 🔴 不用 `importorskip`：PyYAML 缺失时**必须打红**。`skip` 会让「yml 可解析 +
    #    无重名 job」两条判据静默空转，而那正是 Requirement 13.11 的全部内容。
    #    PyYAML 已在 backend/requirements.txt 内，CI 装的就是它。
    import yaml

    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict), "governance-checks.yml 顶层不是映射"
    return parsed


@pytest.fixture(scope="module")
def guard_files() -> dict[str, str]:
    """守卫文件清单**单一真源** = 变异脚本的 ``GUARD_FILES``。

    这样「新加一个守卫文件」只需改一处：变异脚本必须给它配变异（那边有覆盖面
    自检），本文件随即要求它进 CI 或进本地闸门登记名单。
    """
    spec = importlib.util.spec_from_file_location("_k_mutate", _MUTATE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # dataclass 在模块未登记进 sys.modules 时会 AttributeError
    sys.modules["_k_mutate"] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("_k_mutate", None)
    files: dict[str, str] = dict(mod.GUARD_FILES)
    assert len(files) >= 10, f"GUARD_FILES 只读到 {len(files)} 个，真源可疑"
    return files


def _job_blocks(raw: str) -> dict[str, str]:
    """按缩进切出每个 job 的原始文本块（含其全部步骤）。

    不用 `safe_load` 的原因：要看 `run:` 的**原文**（含 `|| echo`），而 YAML 解析
    后的折叠标量会把它规整掉，也拿不到重复 key。
    """
    lines = raw.splitlines()
    starts: list[tuple[int, str]] = []
    in_jobs = False
    for i, ln in enumerate(lines):
        if re.match(r"^jobs:\s*$", ln):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if ln and not ln.startswith(" ") and not ln.startswith("#"):
            break  # 走出 jobs: 段
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", ln)
        if m:
            starts.append((i, m.group(1)))
    out: dict[str, str] = {}
    for idx, (line_no, name) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        out.setdefault(name, "")
        out[name] += "\n".join(lines[line_no:end])
    return out


def _run_commands(block: str) -> list[str]:
    """取 job 里所有 `run:` 的命令原文（含 `>-` / `|` 折叠块）。"""
    cmds: list[str] = []
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)(?:- name:.*)?$", lines[i])
        run = re.match(r"^(\s*)run:\s*(.*)$", lines[i])
        if run:
            indent, first = run.group(1), run.group(2).strip()
            if first in {">-", ">", "|", "|-"}:
                body: list[str] = []
                i += 1
                while i < len(lines) and (
                    not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > len(indent)
                ):
                    body.append(lines[i].strip())
                    i += 1
                cmds.append(" ".join(x for x in body if x))
                continue
            cmds.append(first)
        i += 1 if not m or run else 1
    return cmds


# ─────────────────────────────────────────────────────────────────────────────
# 1. 可解析 / 无重名
# ─────────────────────────────────────────────────────────────────────────────


def test_yaml_parses_and_job_exists(doc: dict) -> None:
    jobs = doc.get("jobs") or {}
    assert _JOB in jobs, (
        f"`{_JOB}` job 不在 governance-checks.yml —— 本 spec 的 CI 收口未生效"
    )


def test_no_duplicate_job_names(raw: str) -> None:
    """重名 job 必打红。

    🔴 `yaml.safe_load` 对重复 key **静默保留最后一个** ⇒ 前一个 job 整段消失、
    解析零报错。故只能在原始文本上数。
    """
    lines = raw.splitlines()
    seen: dict[str, int] = {}
    dups: list[str] = []
    in_jobs = False
    for ln in lines:
        if re.match(r"^jobs:\s*$", ln):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if ln and not ln.startswith(" ") and not ln.startswith("#"):
            break
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", ln)
        if m:
            name = m.group(1)
            seen[name] = seen.get(name, 0) + 1
            if seen[name] == 2:
                dups.append(name)
    assert not dups, f"job 重名（safe_load 会静默吞掉前一个）：{dups}"


def test_job_block_parser_really_sees_the_k_jobs(raw: str) -> None:
    """反向自检：切块器必须真的切出全部 K job。

    切块器失配时上面几条会「无对象可查」而全绿 —— 那是最典型的守卫空转。
    """
    blocks = _job_blocks(raw)
    missing = [j for j in _K_JOBS if j not in blocks]
    assert not missing, f"job 切块器没找到 {missing}（守卫会空转）"
    for j in _K_JOBS:
        assert "run:" in blocks[j], f"{j} 块里没有 run: —— 切块边界错了"


# ─────────────────────────────────────────────────────────────────────────────
# 2. 引用的路径必须真实存在
# ─────────────────────────────────────────────────────────────────────────────


def _pytest_paths(cmd: str) -> list[str]:
    if "pytest" not in cmd:
        return []
    return re.findall(r"(backend/tests/[\w/.-]+\.py)", cmd)


def _script_paths(cmd: str) -> list[str]:
    return re.findall(r"(backend/scripts/[\w/.-]+\.py)", cmd)


def _vitest_filters(cmd: str) -> list[str]:
    if "vitest" not in cmd:
        return []
    return re.findall(r"(src/[\w/.\[\]-]+\.spec\.ts)", cmd)


def test_referenced_pytest_paths_exist(raw: str) -> None:
    blocks = _job_blocks(raw)
    bad: list[tuple[str, str]] = []
    total = 0
    for job in _K_JOBS:
        for cmd in _run_commands(blocks[job]):
            for p in _pytest_paths(cmd):
                total += 1
                if not (_ROOT / p).exists():
                    bad.append((job, p))
    assert total >= 8, f"只解析到 {total} 个 pytest 路径，解析器可疑"
    assert not bad, f"CI 引用了不存在的测试文件（pytest 会直接 exit 4）：{bad}"


def test_referenced_scripts_exist(raw: str) -> None:
    blocks = _job_blocks(raw)
    bad: list[tuple[str, str]] = []
    total = 0
    for job in _K_JOBS:
        for cmd in _run_commands(blocks[job]):
            for p in _script_paths(cmd):
                total += 1
                if not (_ROOT / p).exists():
                    bad.append((job, p))
    assert total >= 3, f"只解析到 {total} 个脚本路径，解析器可疑"
    assert not bad, f"CI 引用了不存在的脚本：{bad}"


def test_vitest_filters_resolve_to_real_files(raw: str) -> None:
    """每个 vitest 过滤器必须命中 ≥1 个真实文件。

    🔴 这是「幽灵过滤器」的唯一可靠判据：vitest 对不命中的过滤器**静默忽略**，
    退出码照样 0，所以只有在磁盘上解析才查得出。
    """
    blocks = _job_blocks(raw)
    ghosts: list[tuple[str, str]] = []
    total = 0
    for job in _K_JOBS:
        for cmd in _run_commands(blocks[job]):
            for f in _vitest_filters(cmd):
                total += 1
                if not (_FE_DIR / f).exists():
                    ghosts.append((job, f))
    assert total >= 2, f"只解析到 {total} 个 vitest 过滤器，解析器可疑"
    assert not ghosts, (
        "vitest 过滤器指向不存在的文件 —— vitest 会静默忽略、job 照绿，"
        f"覆盖面与 yml 表述脱钩：{ghosts}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. 禁假绿兜底
# ─────────────────────────────────────────────────────────────────────────────


def test_k_jobs_have_no_fake_pass_fallback(raw: str) -> None:
    """K job 内禁 `|| echo` / `|| true` / `continue-on-error: true`。"""
    blocks = _job_blocks(raw)
    bad: list[tuple[str, str]] = []
    for job in _K_JOBS:
        for ln in blocks[job].splitlines():
            stripped = ln.strip()
            if stripped.startswith("#"):
                continue  # 注释里写明"曾经有过"是登记，不是假绿
            if _FAKE_PASS.search(stripped):
                bad.append((job, stripped[:110]))
    assert not bad, (
        "K job 里有假绿兜底：步骤失败也只留 warning / job 照绿。"
        f"守卫已交付就该拆掉脚手架：{bad}"
    )


def test_db_guard_detector_is_structural_not_textual() -> None:
    """反向自检：连库判定器必须**结构化**，不能被文本出现骗到。

    三个方向：
    - 本文件自己写满了 `create_async_engine` / `DATABASE_URL` 字样（清单、注释、
      断言消息），但它**不连库** ⇒ 必须判 False。初版用正则扫文本，正是在这里翻的。
    - 真连库的两个守卫 ⇒ 必须判 True。
    - 纯字符串清单（不作下标/实参）⇒ 判 False。
    """
    assert not _is_db_guard(Path(__file__)), (
        "判定器把本文件误判成连库守卫 —— 说明它在扫文本而不是看结构"
    )
    for p in _LOCAL_ONLY_DB_GUARDS:
        assert _is_db_guard(_ROOT / p), f"真连库守卫被漏判：{p}"
    offline = _ROOT / "backend/tests/four_table/test_k_cycle_preset_closure.py"
    assert offline.exists() and not _is_db_guard(offline), "离线守卫被误判成连库"


def test_fake_pass_detector_actually_matches(raw: str) -> None:
    """反向自检：假绿检测器对真实形态必须命中。

    否则上一条会因为正则写错而恒绿 —— 这正是它要拦的缺陷本身。
    """
    samples = [
        'run: npx vitest run a.spec.ts || echo "::warning::pending"',
        "run: python x.py || true",
        "continue-on-error: true",
    ]
    for s in samples:
        assert _FAKE_PASS.search(s), f"检测器漏了：{s}"
    assert not _FAKE_PASS.search("run: python -m pytest backend/tests/x.py -q")


# ─────────────────────────────────────────────────────────────────────────────
# 4. 覆盖面：守卫文件要么进 CI，要么进本地闸门登记
# ─────────────────────────────────────────────────────────────────────────────


def _all_ci_pytest_paths(raw: str) -> set[str]:
    """全 yml（不限 K job）里被 pytest 跑到的测试路径。"""
    return set(re.findall(r"(backend/tests/[\w/.-]+\.py)", raw))


def test_every_guard_file_is_in_ci_or_registered(raw: str, guard_files: dict) -> None:
    in_ci = _all_ci_pytest_paths(raw)
    orphan = [
        v
        for v in guard_files.values()
        if v not in in_ci and v not in _LOCAL_ONLY_DB_GUARDS
    ]
    assert not orphan, (
        "守卫文件既不在 CI、也不在本地闸门登记名单 —— 无声掉队："
        f"{orphan}\n（进 CI 或加进 _LOCAL_ONLY_DB_GUARDS 并写理由，二者必居其一）"
    )


def test_db_guards_are_registered_as_local_only(guard_files: dict) -> None:
    """登记名单必须**恰好**是连库守卫集合。

    两个方向都查：
    - 名单里写了离线守卫 ⇒ 打红（否则「登记」会变成逃避 CI 的后门）
    - 连库守卫没进名单又没进 CI ⇒ 由上一条打红
    """
    declared = set(_LOCAL_ONLY_DB_GUARDS)
    for p in declared:
        f = _ROOT / p
        assert f.exists(), f"登记名单里的文件不存在：{p}"
        assert _is_db_guard(f), (
            f"{p} 并非连库守卫，不该登记为本地闸门（登记不是免 CI 的后门）"
        )
        assert len(_LOCAL_ONLY_DB_GUARDS[p]) >= 15, f"{p} 的登记理由太短"

    # 反向：GUARD_FILES 里凡是连库的，都必须在名单里
    unregistered = [
        v for v in guard_files.values() if _is_db_guard(_ROOT / v) and v not in declared
    ]
    assert not unregistered, (
        f"连库守卫未登记：{unregistered} —— 放进 CI 必红（CI 的 PG 无 report_config "
        "/ account_chart 数据），故必须登记为本地闸门并写明理由"
    )


def test_both_idempotent_fix_scripts_are_checked_in_ci(raw: str) -> None:
    """本 spec 的幂等脚本都要有 `--check` 步骤。"""
    scripts = [
        "backend/scripts/fix/fix_k_cycle_prefill_presets.py",
        "backend/scripts/fix/fix_k_cycle_disclosure_presets.py",
        "backend/scripts/fix/fix_note_k_report_row_codes.py",
        "backend/scripts/fix/fix_note_k_expandable_rows.py",
    ]
    for s in scripts:
        assert (_ROOT / s).exists(), f"脚本不存在：{s}"
        assert re.search(re.escape(s) + r"\s+--check", raw), (
            f"{s} 缺 `--check` CI 步骤 —— 幂等收敛态无人看守"
        )


def test_migrations_really_do_not_seed_report_config() -> None:
    """反向自检：本地闸门的登记理由必须成立。

    理由是「CI 的 PG 只跑迁移，而 `report_config` / `account_chart` 不由迁移灌数」。
    哪天有人加了 seed 迁移，这条会打红 —— 提醒把连库守卫**收回 CI**，
    而不是让登记名单永久固化成借口。
    """
    mig = _ROOT / "backend/migrations"
    assert mig.is_dir(), "找不到 migrations 目录"
    files = sorted(mig.glob("V*.sql"))
    assert len(files) >= 50, f"只找到 {len(files)} 个迁移，判据源可疑"
    pat = re.compile(r"INSERT\s+INTO\s+(?:public\.)?(report_config|account_chart)", re.I)
    seeded = sorted(
        {
            m.group(1)
            for f in files
            for m in pat.finditer(f.read_text(encoding="utf-8", errors="replace"))
        }
    )
    assert not seeded, (
        f"迁移已开始灌 {seeded} —— 本地闸门的登记理由不再成立，"
        "应把连库守卫收回 CI（加 postgres service + 迁移步骤）"
    )
