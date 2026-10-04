# -*- coding: utf-8 -*-
"""pre-commit 门：暂存的附注模板不得出现「陈旧副本整体覆盖」的宏观信号。

背景见 `backend/tests/test_note_template_stale_overwrite_guard.py`（2026-09-30 事故：
`56acf363d` 在一个与附注无关的提交里把两份模板整体换成 7 月下旬的陈旧副本，
既有守卫全红三天没人被拦住）。那条测试进了 CI，但 CI 在 push 之后；这个事故的真实
失效方式是「无关文件搭车进了提交」，**提交时**就该拦住，所以本门挂在 pre-commit。

判据（与测试同源，读 `COVERAGE_FLOOR`，不另立一份阈值）：
  * 带 columns / guidance 的表数不得低于棘轮下限
  * 表头不得含 `<br/>`
  * 零悬空 parent_section_id

只检查**暂存区**内容（`git show :<path>`），不看工作树 —— 门判的是「这次提交之后仓库
是什么样」。未暂存附注模板时静默通过（exit 0，零开销）。

用法：python backend/scripts/check/check_note_template_ratchet.py
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
TEMPLATES = {
    "listed": "backend/data/note_template_listed.json",
    "soe": "backend/data/note_template_soe.json",
}


def _load_guard():
    """复用测试文件里的阈值与判据函数（单一真源）。"""
    path = BACKEND / "tests" / "test_note_template_stale_overwrite_guard.py"
    spec = importlib.util.spec_from_file_location("_stale_guard", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _staged_paths() -> set[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=str(REPO), capture_output=True,
    ).stdout.decode("utf-8", "replace")
    return {line.strip() for line in out.splitlines() if line.strip()}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")

    staged = _staged_paths()
    targets = {v: rel for v, rel in TEMPLATES.items() if rel in staged}
    if not targets:
        return 0

    guard = _load_guard()
    problems: list[str] = []
    for variant, rel in targets.items():
        blob = subprocess.run(["git", "show", f":{rel}"], cwd=str(REPO), capture_output=True)
        if blob.returncode != 0:
            problems.append(f"[{variant}] 读不到暂存内容 {rel}")
            continue
        doc = json.loads(blob.stdout.decode("utf-8"))
        cols, guid = guard._coverage(doc)
        problems += [f"[{variant}] {p}" for p in guard._violations(variant, cols, guid)]
        br = guard._br_headers(doc)
        if br:
            problems.append(f"[{variant}] 表头含 {len(br)} 处 <br/>，首条：{br[0]}")
        secs = doc.get("sections") or []
        ids = {s.get("section_id") for s in secs}
        dangling = [s.get("section_number") for s in secs
                    if s.get("parent_section_id") and s["parent_section_id"] not in ids]
        if dangling:
            problems.append(f"[{variant}] 悬空 parent_section_id：{dangling[:5]}")

    if not problems:
        print(f"[pre-commit] ✅ 附注模板棘轮通过（{', '.join(targets)}）")
        return 0
    print("[pre-commit] ❌ 暂存的附注模板出现「陈旧副本整体覆盖」信号：")
    for p in problems:
        print(f"   {p}")
    print("   先确认这个文件是不是搭车进了本次提交：git diff --cached --stat -- backend/data/")
    print("   不是你要改的 ⇒ git restore --staged <path>；确属有意 ⇒ 更新 COVERAGE_FLOOR 并写明理由")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
