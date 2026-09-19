"""扫描：披露同步载荷是否把「项目账龄配置口径」标签直接推给附注。

问题（2026-07-29 实测）：底稿账龄行 label 取自 `useAgingConfig` 的项目账龄配置
（`1-2年`），原样同步到附注后与附注模板/致同源模板字面（`1至2年`）不一致。
用户决策方案 A：在同步层用 `composables/disclosureAgingLabels.ts` 的
`toDisclosureAgingLabel()` 映射，项目账龄配置继续只服务底稿内部。

本守卫定位「仍未接入映射」的同步载荷构建器：

命中条件（同时满足视为未覆盖）：
1. 文件名形如 `*NoteSectionMap.ts` / `*DisclosureSyncPayload.ts` / `*SyncPayload.ts`
2. 载荷里出现账龄相关行来源（`agingRows` / `agingSegments` / `账龄`）
3. **未** import `disclosureAgingLabels`

默认 warn 不阻断（`--strict` 才 exit 1）—— 各循环随 rollout 批次收敛。

spec: disclosure-columns-coverage-rollout R6.7
用法：
    python backend/scripts/check/check_disclosure_aging_label_coverage.py [--strict]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOT = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# 扫描面：披露同步载荷 / 章节映射 / 披露行模型（G5 的行模型不叫 SyncPayload，需一并纳入）
FILENAME_RE = re.compile(
    r"(NoteSectionMap|SyncPayload|DisclosureRows|DisclosureModel|Disclosure(?:Listed|Soe|SOE))\.ts$"
)
# 🔴 信号必须是「行 label 由账龄段派生」，不能只看文件里出现「账龄」二字
#    —— 否则列头 `{ label: '账龄' }`（D6）、表名「账龄超过1年的重要合同负债」（D7）
#    这类与账龄档位无关的用法会被误判为未覆盖（实测假阳性 2 个循环）。
AGING_SIGNAL_RE = re.compile(
    r"\bagingRows\b|\bagingSegments\b|\bAgingSegment\b|AGING_BANDS|AGING_LABEL"
)
MAPPER_IMPORT_RE = re.compile(r"from\s+['\"][^'\"]*disclosureAgingLabels['\"]")

# 已确认无账龄披露的例外（保留结构，便于后续登记；每项须写原因）
ALLOWLIST: dict[str, str] = {}


CYCLE_RE = re.compile(r"^(?:use)?([a-z]+\d+)", re.IGNORECASE)


def _cycle_of(name: str) -> str | None:
    """从文件名提取循环前缀（`d2NoteSectionMap.ts` → `d2`，`useF1DisclosureSoe.ts` → `f1`）。"""
    m = CYCLE_RE.match(name)
    return m.group(1).lower() if m else None


def _cycles_with_mapper() -> set[str]:
    """已接入共享映射的循环集合。

    映射可合法地落在该循环的任一文件（F1 放在 `useF1Disclosure{Listed,Soe}.ts`，
    D2 放在 `d2NoteSectionMap.ts`）→ 按**循环**判定覆盖，而非按单文件。
    """
    hit: set[str] = set()
    for path in SCAN_ROOT.rglob("*.ts"):
        if "__tests__" in path.parts or path.name.endswith(".spec.ts"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not MAPPER_IMPORT_RE.search(text):
            continue
        cycle = _cycle_of(path.name)
        if cycle:
            hit.add(cycle)
    return hit


def scan() -> tuple[list[Path], list[Path]]:
    mapped_cycles = _cycles_with_mapper()
    covered: list[Path] = []
    uncovered: list[Path] = []
    for path in sorted(SCAN_ROOT.rglob("*.ts")):
        if "__tests__" in path.parts or path.name.endswith(".spec.ts"):
            continue
        if not FILENAME_RE.search(path.name):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not AGING_SIGNAL_RE.search(text):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        cycle = _cycle_of(path.name)
        is_covered = bool(MAPPER_IMPORT_RE.search(text)) or (cycle in mapped_cycles)
        (covered if is_covered else uncovered).append(path)
    return covered, uncovered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="未覆盖 > 0 时 exit 1")
    args = parser.parse_args()

    covered, uncovered = scan()
    total = len(covered) + len(uncovered)
    print(f"账龄披露口径映射覆盖：{len(covered)}/{total}")
    for p in covered:
        print(f"  [OK]   {p.relative_to(REPO_ROOT).as_posix()}")
    for p in uncovered:
        print(f"  [MISS] {p.relative_to(REPO_ROOT).as_posix()}")
    if ALLOWLIST:
        print("豁免：")
        for rel, reason in ALLOWLIST.items():
            print(f"  [SKIP] {rel} — {reason}")

    if not uncovered:
        print("[PASS] 全部账龄披露载荷已接入 toDisclosureAgingLabel")
        return 0
    tag = "FAIL" if args.strict else "WARN"
    print(
        f"[{tag}] {len(uncovered)} 个载荷仍直接推项目账龄配置口径标签"
        f"（附注会显示 `1-2年` 而非 `1至2年`）"
    )
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
