"""已发布 AI Prompt 版本哈希锁（ADR-LLM-017：Prompt 版本 append-only）。

用法：
    python backend/scripts/check/check_ai_prompt_versions.py --check   # CI：锁与登记逐条一致
    python backend/scripts/check/check_ai_prompt_versions.py --write   # 只追加新版本，已发布版本被改即拒绝

已发布版本的正文一旦变化，`--check` 与 `--write` 都退出 2：必须追加新版本号，而不是原地改正文。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
LOCK_PATH = BACKEND / "data" / "ai_prompt_version_lock.json"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def registry_hashes() -> dict[str, str]:
    from app.services.ai_task_registry import PROMPT_VERSIONS

    return {
        f"{item.prompt_id}@{item.version}": item.sha256
        for versions in PROMPT_VERSIONS.values()
        for item in versions
    }


def load_lock(path: Path = LOCK_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data.get("versions") or {})


def compare(current: dict[str, str], locked: dict[str, str]) -> dict[str, list[str]]:
    """返回 changed（已发布正文被改）、removed（已发布版本被删）、unlocked（新版本未登记锁）。"""
    return {
        "changed": sorted(k for k in current if k in locked and current[k] != locked[k]),
        "removed": sorted(k for k in locked if k not in current),
        "unlocked": sorted(k for k in current if k not in locked),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    current = registry_hashes()
    locked = load_lock()
    diff = compare(current, locked)
    if diff["changed"] or diff["removed"]:
        for key in diff["changed"]:
            print(f"[FAIL] 已发布 Prompt 正文被修改：{key}（请追加新版本号）")
        for key in diff["removed"]:
            print(f"[FAIL] 已发布 Prompt 版本被删除：{key}")
        return 2
    if args.check:
        if diff["unlocked"]:
            for key in diff["unlocked"]:
                print(f"[FAIL] 新 Prompt 版本未登记哈希锁：{key}（运行 --write）")
            return 2
        print(f"[OK] {len(current)} 个已发布 Prompt 版本与哈希锁一致")
        return 0
    if not diff["unlocked"]:
        print("[OK] 没有新版本需要登记")
        return 0
    merged = {**locked, **{k: current[k] for k in diff["unlocked"]}}
    LOCK_PATH.write_text(
        json.dumps({"schema": 1, "versions": dict(sorted(merged.items()))}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] 追加 {len(diff['unlocked'])} 个 Prompt 版本哈希")
    return 0


if __name__ == "__main__":
    sys.exit(main())
