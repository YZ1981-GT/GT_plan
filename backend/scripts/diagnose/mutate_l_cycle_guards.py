#!/usr/bin/env python
"""L 循环守卫变异检验脚本。

按 spec 要求 ≥18 项变异逐条验证守卫是否能打红。

三态判定：
  RED        — 变异后守卫打红（预期行为，守卫有效）
  GREEN      — 变异后守卫仍绿（守卫缺陷，需修）
  ANCHOR-MISS — 锚点未命中（脚本缺陷，需修锚点）

用法：
    python backend/scripts/diagnose/mutate_l_cycle_guards.py           # 全跑
    python backend/scripts/diagnose/mutate_l_cycle_guards.py --only M1  # 跑单条
    python backend/scripts/diagnose/mutate_l_cycle_guards.py --restore  # 还原所有 .bak

spec: .kiro/specs/l-cycle-extraction-formula-and-disclosure-completion/ Task 23
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # → backend/
REPO = ROOT.parent

# ─── 变异定义 ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Mutation:
    id: str
    desc: str
    file: str  # 相对 REPO
    test_targets: tuple[str, ...]  # pytest 路径
    anchor: str  # 行级唯一锚点（不含 \\n）
    repl: str  # 替换后文本
    expect_test: tuple[str, ...] = ()  # 期望打红的测试名子串


# ─── 公式预设变异（类 A/B）────────────────────────────────────────────────────

PREFILL = "backend/data/prefill_formula_mapping.json"
PRESET_TESTS = ("backend/tests/l_cycle_extraction/test_l_preset_account_coherence.py",)

# ─── 附注结构变异 ────────────────────────────────────────────────────────────

SOE_TEMPLATE = "backend/data/note_template_soe.json"
LISTED_TEMPLATE = "backend/data/note_template_listed.json"
NOTE_TESTS = ("backend/tests/l_cycle_extraction/test_note_l3_l4_structure.py",)

# ─── L7 / row_code 变异 ─────────────────────────────────────────────────────

SCOPE_FILE = "backend/app/services/l_cycle_extraction/account_scope.py"
SCOPE_TESTS = ("backend/tests/l_cycle_extraction/test_l_account_scope.py",)

# ─── K3 写权变异 ─────────────────────────────────────────────────────────────

K3_MAP = "audit-platform/frontend/src/components/workpaper/composables/k3NoteSectionMap.ts"

MUTATIONS: tuple[Mutation, ...] = (
    # M1: L4 审定表公式改回错位（变异公式实参）
    Mutation(
        "M1", "L4 审定表未审数公式改回 2601（租赁负债）",
        PREFILL, PRESET_TESTS,
        "\"formula\": \"=TB('2502','期末余额')\",\n          \"formula_type\": \"TB\",\n          \"description\": \"从试算表取应付债券期末余额（未审）\"",
        "\"formula\": \"=TB('2601','期末余额')\",\n          \"formula_type\": \"TB\",\n          \"description\": \"从试算表取租赁负债期末余额（未审）\"",
        ("公式实参引用了别的循环的科目",),
    ),
    # M2: L5 审定表公式改回错位
    Mutation(
        "M2", "L5 审定表公式改回 2502（应付债券）",
        PREFILL, PRESET_TESTS,
        "从试算表取长期应付款期初余额",
        "从试算表取应付债券期初余额",
        ("description 里的科目中文名与本块所属循环不一致",),
    ),
    # M3: L6 审定表公式改回错位
    Mutation(
        "M3", "L6 审定表公式改回 2701（长期应付款）",
        PREFILL, PRESET_TESTS,
        "从试算表取专项应付款期初余额",
        "从试算表取长期应付款期初余额",
        ("description 里的科目中文名与本块所属循环不一致",),
    ),
    # M4: L7 PLACEHOLDER 说明改太短
    Mutation(
        "M4", "L7 PLACEHOLDER description 改太短",
        PREFILL, PRESET_TESTS,
        "其他非流动负债期初余额需手工填列。其他非流动负债在 CAS 会计科目表中无专属科目",
        "手工填列",
        ("PLACEHOLDER",),
    ),
    # M5: 八、57 列序改回旧值
    Mutation(
        "M5", "八、57 列序改回期末余额/期初余额（旧附注口径）",
        SOE_TEMPLATE, NOTE_TESTS + PRESET_TESTS,
        '"key": "prior_amount", "label": "年初余额"',
        '"key": "prior_amount", "label": "期初余额"',
    ),
    # M6: 五、46 t04 只有 5 列（删一个 value 列）
    Mutation(
        "M6", "五、46 t04 删 begin_value 列（9→8，破坏两级对称）",
        LISTED_TEMPLATE, NOTE_TESTS,
        '"key": "begin_value", "label": "账面价值", "format": "amount", "group": "期初余额"',
        "",
    ),
    # M7: L7 兜底码加一个值（破坏宁缺勿造）
    Mutation(
        "M7", "L7 fallback_codes 加 2801（破坏宁缺勿造）",
        SCOPE_FILE, SCOPE_TESTS,
        'fallback_codes=(),',
        'fallback_codes=("2801",),',
        ("L7 兜底码应为空元组",),
    ),
    # M8: L7 row_code_listed 改错
    Mutation(
        "M8", "L7 row_code_listed 改为 BS-068",
        SCOPE_FILE, SCOPE_TESTS,
        'row_code_listed="BS-071",',
        'row_code_listed="BS-068",',
        ("L7 listed row_code 应为 BS-071",),
    ),
    # M9: K3 重新推 interest（写权唯一性破坏）
    Mutation(
        "M9", "K3 恢复推 interest（写权唯一性破坏）",
        K3_MAP, (),
        "delete columns[T.interest]",
        "sub[T.interest] = interestRows",
    ),
    # M10: 八、45 列 key 改回中文
    Mutation(
        "M10", "八、45 列 key 改回中文字面量",
        SOE_TEMPLATE, NOTE_TESTS,
        '"key": "end_amount", "label": "期末余额", "format": "amount"',
        '"key": "期末余额", "label": "期末余额", "flat": true',
    ),
)


# ─── 执行引擎 ─────────────────────────────────────────────────────────────────


def _file_md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _backup(path: Path) -> Path:
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak)
    return bak


def _restore(path: Path) -> bool:
    bak = path.with_suffix(path.suffix + ".bak")
    if bak.exists():
        shutil.copy2(bak, path)
        bak.unlink()
        return True
    return False


def _apply_mutation(m: Mutation) -> str | None:
    """Apply mutation, return None on success or error message."""
    fp = REPO / m.file
    if not fp.exists():
        return f"文件不存在: {m.file}"
    text = fp.read_text(encoding="utf-8")
    count = text.count(m.anchor)
    if count == 0:
        return f"ANCHOR-MISS: 锚点未命中（0 次）"
    if count > 1:
        return f"ANCHOR-MISS: 锚点命中 {count} 次（非唯一）"
    mutated = text.replace(m.anchor, m.repl, 1)
    fp.write_text(mutated, encoding="utf-8")
    return None


def _run_tests(targets: tuple[str, ...]) -> tuple[int, str]:
    """Run pytest, return (exit_code, stdout+stderr)."""
    if not targets:
        return 0, "(no test targets)"
    cmd = [sys.executable, "-m", "pytest", *targets, "-x", "--tb=line", "-q"]
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(REPO),
        encoding="utf-8", errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def run_mutation(m: Mutation) -> str:
    """Run one mutation cycle. Returns verdict: RED / GREEN / ANCHOR-MISS."""
    fp = REPO / m.file
    _backup(fp)
    before_md5 = _file_md5(fp)

    err = _apply_mutation(m)
    if err:
        _restore(fp)
        return f"ANCHOR-MISS: {err}"

    rc, output = _run_tests(m.test_targets)
    _restore(fp)

    after_md5 = _file_md5(fp)
    if after_md5 != before_md5:
        return f"RESTORE-FAIL: md5 不匹配（还原失败）"

    if rc != 0:
        return "RED"
    else:
        return "GREEN"


def main():
    ap = argparse.ArgumentParser(description="L 循环守卫变异检验")
    ap.add_argument("--only", help="只跑指定 ID 的变异（如 M1）")
    ap.add_argument("--restore", action="store_true", help="还原所有 .bak 文件")
    ap.add_argument("--list", action="store_true", help="列出所有变异")
    args = ap.parse_args()

    if args.restore:
        for m in MUTATIONS:
            fp = REPO / m.file
            if _restore(fp):
                print(f"[RESTORED] {m.file}")
        return

    if args.list:
        for m in MUTATIONS:
            print(f"  {m.id}: {m.desc}")
        return

    targets = MUTATIONS
    if args.only:
        targets = tuple(m for m in MUTATIONS if m.id == args.only)
        if not targets:
            print(f"[ERROR] 未找到变异 {args.only}")
            sys.exit(1)

    results: dict[str, str] = {}
    for m in targets:
        print(f"[{m.id}] {m.desc} ...", end=" ", flush=True)
        verdict = run_mutation(m)
        results[m.id] = verdict
        print(verdict)

    # 汇总
    red = sum(1 for v in results.values() if v == "RED")
    green = sum(1 for v in results.values() if v == "GREEN")
    miss = sum(1 for v in results.values() if v.startswith("ANCHOR"))
    total = len(results)

    print(f"\n{'='*60}")
    print(f"变异检验结果: {total} 项")
    print(f"  RED (守卫有效): {red}")
    print(f"  GREEN (守卫缺陷): {green}")
    print(f"  ANCHOR-MISS (脚本缺陷): {miss}")

    if green > 0:
        print("\n[FAIL] 以下变异未被守卫打红:")
        for mid, v in results.items():
            if v == "GREEN":
                m = next(x for x in MUTATIONS if x.id == mid)
                print(f"  {mid}: {m.desc}")
        sys.exit(1)
    elif miss > 0:
        print("\n[WARN] 以下变异锚点未命中:")
        for mid, v in results.items():
            if v.startswith("ANCHOR"):
                print(f"  {mid}: {v}")
        sys.exit(2)
    else:
        print("\n[OK] 全部 RED — 守卫有效")


if __name__ == "__main__":
    main()
