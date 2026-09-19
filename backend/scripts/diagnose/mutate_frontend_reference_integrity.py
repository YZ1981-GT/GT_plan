"""FrontendReferenceIntegrity 守卫的变异检验（四态判定）。

为什么需要它：`FrontendReferenceIntegrity.spec.ts` 抓的是「引用了不存在的目标」，
而这类判据最容易悄悄变宽 —— 比如 `pathMatchesDeclaredRoute` 若把 catch-all
算进可达集合，任何路径都"匹配得上"，判据恒真且全绿。这正是 AC 1.5 那条
e2e 判据（只断言 URL）失效的同一机制，所以必须逐条证明守卫抓得到。

四态判定（只看退出码会把后三态误判成 RED）：
  RED          变异后打红，且预期那条测试确实在失败集合里
  GREEN        变异后仍全绿  → 守卫缺陷
  ANCHOR-MISS  锚点在源码里命中 0 次或 >1 次 → 脚本缺陷
  WRONG-TEST   打红了但预期测试没红 → 锚点错行或污染残留

用法：
  python backend/scripts/diagnose/mutate_frontend_reference_integrity.py --check-anchors
  python backend/scripts/diagnose/mutate_frontend_reference_integrity.py --run \
      --out .kiro/specs/dsh-agent-panel-integration/mutation_results_reference_integrity.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[3]
FRONTEND = REPO / "audit-platform" / "frontend"
GUARD_SPEC = "src/__tests__/FrontendReferenceIntegrity.spec.ts"


@dataclass
class Mutation:
    id: str
    desc: str
    file: str
    anchor: str
    replacement: str
    expect_test: str
    verdict: str = ""
    failed_tests: list[str] = field(default_factory=list)


# 锚点一律单行（CRLF 下跨行裸字符串必 ANCHOR-MISS）。
MUTATIONS: list[Mutation] = [
    Mutation(
        id="MR1",
        desc="删掉 /ai-chat 路由声明（复刻 AC 1.5 的原始缺陷形态）",
        file="src/router/index.ts",
        anchor="      path: '/ai-chat',",
        replacement="      path: '/__ai_chat_removed__',",
        expect_test="AC 1.5：新窗口聊天路由 /ai-chat 已注册",
    ),
    Mutation(
        id="MR2",
        desc="让 catch-all 参与匹配（判据恒真的核心形态）",
        file="src/__tests__/_helpers/frontendSourceScan.ts",
        anchor="    if (CATCH_ALL_PATTERN.test(route.full)) continue // 🔴 catch-all 不算可达",
        replacement="    // mutated: catch-all 参与匹配",
        expect_test="判据自检：catch-all 不得参与匹配",
    ),
    Mutation(
        id="MR3",
        desc="把已修好的导航目标改回不存在的路由",
        file="src/views/ManagementDashboard.vue",
        anchor="@click=\"$router.push('/settings/staff')\"",
        replacement="@click=\"$router.push('/staff')\"",
        expect_test="所有写死的站内导航目标都能匹配到非 catch-all 路由",
    ),
    Mutation(
        id="MR4",
        desc="stripJsComments 换成朴素正则（会截断 'https://x'）",
        file="src/__tests__/_helpers/frontendSourceScan.ts",
        anchor="export function stripJsComments(source: string): string {",
        replacement=(
            "export function stripJsComments(source: string): string {\n"
            "  return source.replace(/\\/\\/.*$/gm, '').replace(/\\/\\*[\\s\\S]*?\\*\\//g, '')\n"
            "  // mutated: 朴素正则版本"
        ),
        expect_test="判据自检：stripJsComments 不得截断含 // 的字符串",
    ),
    Mutation(
        id="MR5",
        desc="把一个生产 import 改成不存在的路径（复刻 import 深度错）",
        file="src/components/workpaper/confirmation/diffReconcile/GtConfirmationDiffReconcile.vue",
        anchor="import { buildDiffMisstatementPayload } from '../composables/confirmationRiskPush'",
        replacement="import { buildDiffMisstatementPayload } from '../../composables/confirmationRiskPush'",
        expect_test="不存在未登记的坏 import",
    ),
    Mutation(
        id="MR6",
        desc="路径匹配放宽成前缀式（段数不等也算匹配）",
        file="src/__tests__/_helpers/frontendSourceScan.ts",
        anchor="    if (routeSegs.length !== targetSegs.length) continue",
        replacement="    if (routeSegs.length > targetSegs.length) continue",
        expect_test="判据自检：动态段匹配任意单段，段数必须相等",
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def anchor_hits(text: str, anchor: str) -> int:
    return text.count(anchor)


def check_anchors() -> int:
    print("=== 锚点静态检查 ===")
    guard_src = (FRONTEND / GUARD_SPEC).read_text(encoding="utf-8")
    # vitest 的 it/describe 标题
    titles = set(re.findall(r"(?:it|test|describe)\(\s*['\"](.+?)['\"]", guard_src))

    bad = 0
    for m in MUTATIONS:
        target = FRONTEND / m.file
        if not target.is_file():
            print(f"  {m.id}: MISS  文件不存在 {m.file}")
            bad += 1
            continue
        text = target.read_text(encoding="utf-8")
        hits = anchor_hits(text, m.anchor)
        # expect_test 必须命中真实测试标题（防「锚点还在但测试名已漂移」）
        title_ok = any(m.expect_test in t or t in m.expect_test for t in titles)
        status = "OK" if hits == 1 and title_ok else "MISS"
        if status == "MISS":
            bad += 1
        print(
            f"  {m.id}: {status:4} 锚点命中 {hits} 次 | expect_test "
            f"{'命中测试标题' if title_ok else '❌ 未命中任何测试标题'}"
        )
    print(f"\n结论: {len(MUTATIONS) - bad}/{len(MUTATIONS)} 通过")
    return 0 if bad == 0 else 1


def run_guard() -> tuple[bool, list[str]]:
    """跑守卫，返回 (全绿?, 失败测试名列表)。"""
    out_file = REPO / "tmp_mutation_vitest.json"
    if out_file.exists():
        out_file.unlink()
    subprocess.run(
        [
            "npx",
            "vitest",
            "run",
            GUARD_SPEC,
            "--reporter=json",
            f"--outputFile={out_file}",
        ],
        cwd=FRONTEND,
        capture_output=True,
        shell=True,
    )
    if not out_file.exists():
        return False, ["<vitest 未产出报告>"]
    data = json.loads(out_file.read_text(encoding="utf-8"))
    out_file.unlink()
    failed: list[str] = []
    for suite in data.get("testResults", []):
        for case in suite.get("assertionResults", []):
            if case.get("status") == "failed":
                failed.append(case.get("title", "<no title>"))
    return (len(failed) == 0), failed


def run_mutations(out_path: Path | None) -> int:
    print("=== 变异实跑（四态判定）===\n")
    baseline_green, baseline_failed = run_guard()
    if not baseline_green:
        print(f"❌ 基线不绿，先修守卫再变异。失败项: {baseline_failed}")
        return 1
    print("基线: 全绿 ✅\n")

    for m in MUTATIONS:
        target = FRONTEND / m.file
        original = target.read_bytes()
        original_sha = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")

        hits = anchor_hits(text, m.anchor)
        if hits != 1:
            m.verdict = "ANCHOR-MISS"
            print(f"{m.id}  {m.verdict}  (锚点命中 {hits} 次)  {m.desc}")
            continue

        try:
            target.write_text(text.replace(m.anchor, m.replacement, 1), encoding="utf-8", newline="")
            green, failed = run_guard()
            m.failed_tests = failed
            if green:
                m.verdict = "GREEN"
            elif any(m.expect_test in f or f in m.expect_test for f in failed):
                m.verdict = "RED"
            else:
                m.verdict = "WRONG-TEST"
        finally:
            target.write_bytes(original)
            assert sha256(target) == original_sha, f"{m.file} 复原失败！"

        mark = "✅" if m.verdict == "RED" else "🔴"
        print(f"{m.id}  {m.verdict:11} {mark}  {m.desc}")
        if m.verdict != "RED":
            print(f"      实际失败项: {m.failed_tests}")
        else:
            print(f"      打红: {m.failed_tests}")

    reds = sum(1 for m in MUTATIONS if m.verdict == "RED")
    print(f"\n结论: {reds}/{len(MUTATIONS)} RED")
    for state in ("GREEN", "ANCHOR-MISS", "WRONG-TEST"):
        n = sum(1 for m in MUTATIONS if m.verdict == state)
        print(f"  {state}: {n}")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "spec": "dsh-agent-panel-integration",
                    "scope": "FrontendReferenceIntegrity 守卫（P0 收口新增）",
                    "guard_file": GUARD_SPEC,
                    "total": len(MUTATIONS),
                    "red": reds,
                    "results": [
                        {
                            "id": m.id,
                            "desc": m.desc,
                            "file": m.file,
                            "expect_test": m.expect_test,
                            "verdict": m.verdict,
                            "failed_tests": m.failed_tests,
                        }
                        for m in MUTATIONS
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\n结果已写入 {out_path}")

    return 0 if reds == len(MUTATIONS) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.check_anchors:
        return check_anchors()
    if args.run:
        return run_mutations(args.out)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
