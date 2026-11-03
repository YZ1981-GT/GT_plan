#!/usr/bin/env python
"""workpaper sync 四件生成物的**原子**入口（`--check` / `--write`）。

**Spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 1.7**

═══ 为什么需要这一层 ══════════════════════════════════════════════════════════

四件生成物有**单向依赖**：

    source + overlay + adjudication ledger
      → ① entry manifest（`generate_workpaper_sync_manifest.py --apply`）
          └→ frontend `workpaperSyncManifest.generated.ts`（同一步原子写）
      → ② legacy baseline（读 ① 的 manifest）
      → ③ current-state report（读 ① + overlay + Task 66 删除计划）
      → ④ cycle current projection（读 ①，并回写 12 份 slice 的 `current_projection_ref`）

逐个手跑时，**顺序错或漏跑一个就会留下互相矛盾的事实**：②③④ 读的是旧 manifest，而 ①
已经变了。四个 `--check` 各自全绿也发现不了 —— 因为每个都只跟自己的输入比。

本宿主把它们收成一条命令，并加一条各生成器都没有的判据：**上游先于下游**。
`--check` 下任一件 stale 即整体失败（exit 1），且**一个字节都不写**；`--write` 按依赖序
逐件生成，随后再跑一遍全量 `--check` 自证收敛（幂等），不收敛即 exit 2。

🔴 这里**不复制**任何生成算法：四件各自的真源仍是各自的生成器，本宿主只负责「按序调用 +
   统一结算」。复制一份算法出来就又多了一个会漂移的真源。

═══ 用法 ════════════════════════════════════════════════════════════════════

    $env:PYTHONIOENCODING='utf-8'
    python backend/scripts/gen/generate_workpaper_sync_artifacts.py --check
    python backend/scripts/gen/generate_workpaper_sync_artifacts.py --write
    python backend/scripts/gen/generate_workpaper_sync_artifacts.py --check --json out.json

🔴 判成败看结算，不看单个子命令的 stdout —— 子命令全绿而依赖序错时本宿主仍会失败。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GEN_DIR = Path(__file__).resolve().parent


class ArtifactHostError(RuntimeError):
    """宿主自身前置不成立（不是某一件生成物 stale）。"""


@dataclass(frozen=True)
class Stage:
    """一件生成物：脚本名 + 两个模式的参数 + 它产出的文件。"""

    key: str
    script: str
    check_args: tuple[str, ...]
    write_args: tuple[str, ...]
    outputs: tuple[str, ...]
    #: 它读的上游生成物（必须排在它前面）。
    depends_on: tuple[str, ...] = ()


#: 依赖序即声明序。`depends_on` 只用于**自检**这个顺序没被改坏。
STAGES: Final[tuple[Stage, ...]] = (
    Stage(
        key="manifest",
        script="generate_workpaper_sync_manifest.py",
        check_args=("--check",),
        write_args=("--apply",),
        outputs=(
            "backend/data/workpaper_sync_entry_manifest.json",
            "audit-platform/frontend/src/components/workpaper/sync/"
            "workpaperSyncManifest.generated.ts",
        ),
    ),
    Stage(
        key="legacy_baseline",
        script="generate_workpaper_sync_legacy_baseline.py",
        check_args=("--check",),
        write_args=("--apply",),
        outputs=(
            "backend/data/workpaper_sync_legacy_baseline.json",
            "audit-platform/frontend/src/components/workpaper/sync/"
            "workpaperSyncLegacyBaseline.generated.ts",
        ),
        depends_on=("manifest",),
    ),
    Stage(
        key="current_state",
        script="generate_workpaper_sync_current_state.py",
        check_args=("--check",),
        write_args=("--write",),
        outputs=("backend/data/workpaper_sync_current_state.json",),
        depends_on=("manifest",),
    ),
    Stage(
        key="cycle_projection",
        script="generate_workpaper_sync_cycle_projection.py",
        check_args=("--check",),
        write_args=("--write",),
        outputs=("backend/data/workpaper_sync_cycle_current_projection.json",),
        depends_on=("manifest",),
    ),
)


@dataclass
class StageOutcome:
    key: str
    script: str
    mode: str
    returncode: int
    state: str  # ok / stale / failed / skipped
    missing_outputs: list[str] = field(default_factory=list)
    tail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _assert_dependency_order() -> None:
    """声明序必须是拓扑序 —— 有人把某件挪到它上游之前时立刻失败。"""
    seen: set[str] = set()
    keys = [stage.key for stage in STAGES]
    if len(set(keys)) != len(keys):
        raise ArtifactHostError(f"STAGES 里有重复 key：{keys}")
    for stage in STAGES:
        missing = [dep for dep in stage.depends_on if dep not in seen]
        if missing:
            raise ArtifactHostError(
                f"{stage.key} 声明依赖 {missing}，但它们没有排在前面 —— "
                "依赖序被改坏了（下游会读到旧的上游事实）"
            )
        seen.add(stage.key)


def _run(stage: Stage, *, write: bool) -> StageOutcome:
    args = stage.write_args if write else stage.check_args
    script = _GEN_DIR / stage.script
    if not script.is_file():
        raise ArtifactHostError(f"生成器不存在：{script}")
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    # 🔴 子进程 stdout 解码失败只会让它变 None 而不让 run() 失败 ⇒ 这里显式兜底，
    #    并把末行带进结算（只看 returncode 的宿主会在解码问题上假绿）。
    combined = (proc.stdout or "") + (proc.stderr or "")
    tail = combined.strip().splitlines()[-1] if combined.strip() else "<无输出>"
    missing = [rel for rel in stage.outputs if not (_REPO_ROOT / rel).is_file()]
    if proc.returncode == 0 and not missing:
        state = "ok"
    elif proc.returncode == 1:
        state = "stale"
    else:
        state = "failed"
    return StageOutcome(
        key=stage.key,
        script=stage.script,
        mode="write" if write else "check",
        returncode=proc.returncode,
        state=state,
        missing_outputs=missing,
        tail=tail,
    )


def check_all() -> list[StageOutcome]:
    """按依赖序逐件 `--check`。**不短路** —— 一次把全部 stale 点名，省掉反复跑。"""
    return [_run(stage, write=False) for stage in STAGES]


def write_all() -> tuple[list[StageOutcome], list[StageOutcome]]:
    """按依赖序逐件生成；上游失败即**停止**（下游会读到半截事实）。随后全量复检。"""
    produced: list[StageOutcome] = []
    done: set[str] = set()
    for stage in STAGES:
        blocked = [dep for dep in stage.depends_on if dep not in done]
        if blocked:
            produced.append(
                StageOutcome(
                    key=stage.key,
                    script=stage.script,
                    mode="write",
                    returncode=-1,
                    state="skipped",
                    tail=f"上游未成功：{blocked}",
                )
            )
            continue
        outcome = _run(stage, write=True)
        produced.append(outcome)
        if outcome.state == "ok":
            done.add(stage.key)
    return produced, check_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="逐件校验，不写盘")
    mode.add_argument("--write", action="store_true", help="按依赖序生成后自证幂等")
    parser.add_argument("--json", type=Path, default=None, help="把结算写成 JSON")
    args = parser.parse_args(argv)

    try:
        _assert_dependency_order()
    except ArtifactHostError as exc:
        print(f"[FAIL] {exc}")
        return 2

    report: dict[str, Any]
    if args.check:
        outcomes = check_all()
        report = {
            "mode": "check",
            "stages": [item.as_dict() for item in outcomes],
            "state_counts": _counts(outcomes),
        }
        exit_code = 0 if all(item.state == "ok" for item in outcomes) else 1
    else:
        produced, reverified = write_all()
        report = {
            "mode": "write",
            "stages": [item.as_dict() for item in produced],
            "reverify": [item.as_dict() for item in reverified],
            "state_counts": _counts(produced),
            "reverify_state_counts": _counts(reverified),
        }
        if not all(item.state == "ok" for item in produced):
            exit_code = 1
        elif not all(item.state == "ok" for item in reverified):
            # 写完立刻复检还 stale ⇒ 生成不幂等，比「某件过期」严重
            exit_code = 2
        else:
            exit_code = 0

    for item in report["stages"]:
        print(
            f"[{item['state'].upper():>7}] {item['key']:<17} {item['mode']:<5} "
            f"rc={item['returncode']} :: {item['tail']}"
        )
        if item["missing_outputs"]:
            print(f"          缺产物：{item['missing_outputs']}")
    if args.write:
        for item in report["reverify"]:
            print(f"[REVERIFY {item['state'].upper():>5}] {item['key']}")
    print(f"  结算分布: {report['state_counts']}")

    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print(f"[JSON] {args.json}")

    if exit_code == 0:
        print("[OK] 四件生成物按依赖序一致")
    elif exit_code == 1:
        print("[FAIL] 有生成物 stale 或生成失败 —— 上面逐件点名")
    else:
        print("[FAIL] 写入后复检仍不一致 —— 生成不幂等，先查该件的生成器")
    return exit_code


def _counts(outcomes: list[StageOutcome]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in outcomes:
        result[item.state] = result.get(item.state, 0) + 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
