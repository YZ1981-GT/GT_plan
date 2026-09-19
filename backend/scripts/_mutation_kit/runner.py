"""测试执行与失败名收集（pytest / vitest）。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 6.1 · Property 20

## 两条平台实证（都是踩过才知道的）

1. **pytest 一律不经 shell**：`-k "a or b"` 经 shell 会被拆成多个位置参数，
   于是过滤器静默失效、跑了全量或跑了空集。故用 `subprocess.run([...])` 列表形态。
2. **vitest 在 Windows 上必须走 `cmd /c "<单串>"`**：`subprocess.run([...], shell=True)`
   形态下退出码是 0 但 **JSON 从不产出** —— npm 把 `--reporter/--outputFile` 当成自己的
   参数吞掉，不转发给 vitest。这一条抄自 `mutate_e_cycle_guards.run_frontend` 的实测注释。

## 失败名为什么保留 `文件::类::方法`

后端不能只取 nodeid 末段：`test_strip_comments_is_not_a_noop` 在两个不同守卫文件里同名，
只取末段会把两条不同测试折叠成一条，差集判定随之失真。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.MULTILINE)
_ERROR_RE = re.compile(r"^ERROR\s+(\S+)", re.MULTILINE)
_SUMMARY_RE = re.compile(r"\d+ (?:passed|failed|error)")


@dataclass
class RunResult:
    """一次测试运行的结果。

    :param failed: 失败测试名集合（差集判定的唯一依据）
    :param summary: 摘要行（用于与冻结基线比对）
    :param passed: 通过数（-1 表示未能解析）
    :param total: 总数（-1 表示未能解析）
    :param name2file: 测试名 → 守卫文件名（覆盖面分母用；前端靠它反查）
    """

    failed: set[str]
    summary: str
    passed: int = -1
    total: int = -1
    name2file: dict[str, str] = field(default_factory=dict)


def _env() -> dict[str, str]:
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUTF8"] = "1"
    return e


def short_nodeid(nodeid: str) -> str:
    """``tests/four_table/test_x.py::TestY::test_z`` → ``test_x.py::TestY::test_z``。"""
    parts = nodeid.split("::")
    parts[0] = parts[0].replace("\\", "/").rsplit("/", 1)[-1]
    return "::".join(parts)


def run_pytest(repo: Path, args: list[str], timeout: int = 1800) -> RunResult:
    """跑 pytest（**不经 shell**），从 `-rf` 摘要收失败 nodeid。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=str(repo),
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    names: set[str] = set()
    name2file: dict[str, str] = {}
    for nodeid in _FAILED_RE.findall(out) + _ERROR_RE.findall(out):
        short = short_nodeid(nodeid)
        names.add(short)
        name2file[short] = short.split("::")[0]
    tail = [ln for ln in out.splitlines() if _SUMMARY_RE.search(ln)]
    summary = tail[-1].strip() if tail else f"rc={proc.returncode} 无摘要行"
    m = re.search(r"(\d+) passed", summary)
    return RunResult(
        failed=names,
        summary=summary,
        passed=int(m.group(1)) if m else -1,
        total=-1,
        name2file=name2file,
    )


def run_vitest(
    frontend: Path,
    filters: list[str],
    json_path: Path,
    timeout: int = 1800,
) -> RunResult:
    """跑 vitest 并解析 JSON reporter。

    不解析 stdout 的 `FAIL` 行 —— 长中文标题会折行，正则抓不全。
    """
    if json_path.exists():
        json_path.unlink()
    filter_part = " ".join(filters)
    cmd = (
        f"npm exec -- vitest run {filter_part} --reporter=json "
        f'--outputFile="{json_path}"'
    )
    proc = subprocess.run(
        ["cmd", "/c", cmd] if os.name == "nt" else ["sh", "-c", cmd],
        cwd=str(frontend),
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if not json_path.exists():
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-600:]
        return RunResult(
            failed={"<vitest-no-output>"},
            summary=f"rc={proc.returncode} 未产出 JSON: {tail}",
        )
    data = json.loads(json_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    name2file: dict[str, str] = {}
    total = passed = 0
    for suite in data.get("testResults", []):
        fname = str(suite.get("name") or "").replace("\\", "/").rsplit("/", 1)[-1]
        if suite.get("message"):
            # 文件级错误（collect error）也要进失败集合，否则整文件挂掉会被判 GREEN
            names.add(f"<file-level>:{fname}")
            name2file[f"<file-level>:{fname}"] = fname
        for a in suite.get("assertionResults", []):
            total += 1
            full = str(a.get("fullName") or a.get("title") or "")
            name2file[full] = fname
            status = a.get("status")
            if status == "failed":
                names.add(full)
            elif status == "passed":
                passed += 1
    nfs = data.get("numFailedTestSuites")
    return RunResult(
        failed=names,
        summary=f"{passed}/{total} passed, numFailedTestSuites={nfs}",
        passed=passed,
        total=total,
        name2file=name2file,
    )
