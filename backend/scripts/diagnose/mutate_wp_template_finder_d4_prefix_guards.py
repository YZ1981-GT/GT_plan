"""D4/F2 前缀碰撞 + 整册识别守卫的受控变异验证。

每条变异只改一个**唯一**锚点、只跑对应测试，并在 ``finally`` 中按字节恢复。
退出 0 表示所有变异都由预期测试精确打红且源文件已恢复。

四态判读（与同域 mutate_* 脚本一致）：
  RED         变红，且失败项**正是**预期用例          → 守卫有效
  GREEN       没变红                                  → 守卫有缺陷（不是代码没问题）
  ANCHOR-MISS 锚点 0 命中或 >1 命中                    → 脚本缺陷
  WRONG-TEST  变红了但不是预期用例                     → 锚点错行 / 污染残留

用法::

    python backend/scripts/diagnose/mutate_wp_template_finder_d4_prefix_guards.py --check-anchors
    python backend/scripts/diagnose/mutate_wp_template_finder_d4_prefix_guards.py --apply
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FINDER = "backend/app/services/wp_template_finder.py"
TEST_FILE = "backend/tests/test_wp_template_finder_d4_prefix.py"
TIER_TEST_FILE = "backend/tests/test_wp_template_finder_tier_selection.py"


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    path: str
    old: str
    new: str
    test_name: str
    reason: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        mutation_id="M01-tier-collapse",
        path=FINDER,
        old='_PRIMARY_TEMPLATE_TIERS: tuple[str, ...] = ("审定", "常规程序")',
        new='_PRIMARY_TEMPLATE_TIERS: tuple[str, ...] = ("常规程序", "审定")',
        test_name="test_d4_primary_prefers_adjudication_workbook",
        reason="审定与常规程序调换优先级 ⇒ D4 又拿到 D4-12 合同检查（原缺陷形态）",
    ),
    Mutation(
        mutation_id="M02-tier-unordered",
        path=FINDER,
        old="            hits.sort(key=lambda item: (len(item[0]), item[0]))\n",
        new="            # mutation: 取遍历到的第一个，结果重新依赖索引顺序\n",
        test_name="test_same_tier_is_ordered_by_length_then_name",
        reason=(
            "同级内不排序 ⇒ 回到「索引/目录枚举顺序决定结果」。"
            "🔴 预期打红的是 tier_selection 里的纯逻辑判据，**不是**端到端那条："
            "真实数据里 D4/F2 都先命中「审定」级、永远走不到「常规程序」级，"
            "端到端对本条恒绿（首轮实测 GREEN 即此因）"
        ),
    ),
    Mutation(
        mutation_id="M03-prefix-boundary-off",
        path=FINDER,
        old="    rest = filename[len(wp_code):]\n    return not rest[:1].isdigit()",
        new="    return True  # mutation: 放弃数字边界判定",
        test_name="test_wp_code_prefix_no_collision",
        reason="放弃边界判定 ⇒ D4-1 命中 D4-12、F2-2 命中 F2-29（前缀碰撞复现）",
    ),
    Mutation(
        mutation_id="M04-whole-excel-accepts-split-pack",
        path=FINDER,
        old=r'_WHOLE_EXCEL_NAME_RE = re.compile(r"^[A-Z]+\d+[\u4e00-\u9fff]")',
        new=r'_WHOLE_EXCEL_NAME_RE = re.compile(r"^[A-Z]+\d+")',
        test_name="test_whole_excel_d4_income_pack",
        reason="不要求编码后紧跟 CJK ⇒ 范围式拆分包也被当整册合并本",
    ),
    Mutation(
        mutation_id="M05-program-table-fallback-off",
        path=FINDER,
        old="    if program_table and not _has_own_render_schema(wp_code):\n",
        new="    if False:  # mutation: 关掉程序表码回落\n",
        test_name="test_d4a_falls_back_to_adjudication_workbook",
        reason="关掉回落 ⇒ D4A / F2A 回到 None",
    ),
    Mutation(
        mutation_id="M06-program-table-suffix-widened",
        path=FINDER,
        old=r'_PROGRAM_TABLE_CODE_RE = re.compile(r"^([A-Z]+\d+)A$")',
        new=r'_PROGRAM_TABLE_CODE_RE = re.compile(r"^([A-Z]+\d+)[A-Z]$")',
        test_name="",  # 跨 spec：见 _PILOT_EXPECTED_NODE
        reason=(
            "后缀放宽成任意字母 ⇒ H1F / G7L / G7E 这些名字提取产物也被回落，"
            "pilot_h1 / pilot_g7 的「零回退」判据必红"
        ),
    ),
    Mutation(
        mutation_id="M07-render-schema-guard-off",
        path=FINDER,
        old="    return (_RENDER_SCHEMA_DIR / f\"{wp_code}.yaml\").is_file()",
        new="    return False  # mutation: 忽略配置真源",
        test_name="",  # 跨 spec：见 _PILOT_EXPECTED_NODE
        reason=(
            "忽略 render schema ⇒ D2A 被回落，pilot_d2 的「零回退」判据必红。"
            "🔴 pilot_d2 的正路径测试叫 `test_wp_code_has_no_implicit_template_fallback`，"
            "**不叫** `test_selection_passes_on_the_real_manifest`（后者只在 g7/h1 里）——"
            "首轮用后者做 -k 过滤，等于压根没测到 pilot_d2，因此误判 GREEN"
        ),
    ),
)

#: M06 / M07 的预期打红对象在别的 spec 的测试文件里（跨 spec 判据）。
_PILOT_TESTS: tuple[str, ...] = (
    "backend/tests/workpaper_sync/test_task41_d2_large_json_pilot.py",
    "backend/tests/workpaper_sync/test_task42_h1_grouped_dynamic_pilot.py",
    "backend/tests/workpaper_sync/test_task43_g7_two_level_dynamic_pilot.py",
)
#: 三个 pilot 共有的「零回退」正路径判据都带 `fallback` 字样：
#: task41 `test_wp_code_has_no_implicit_template_fallback`、
#: task42/43 各自调 `assert_no_implicit_template_fallback` 的那条。
#: 用它做 -k 而不是某一个具体函数名，避免再次选错对象。
_PILOT_EXPECTED_NODE = "fallback"
_PILOT_MUTATIONS = {"M06-program-table-suffix-widened", "M07-render-schema-guard-off"}


def _anchor_hits(text: str, anchor: str) -> int:
    """CRLF 无关的命中计数（磁盘可能是 CRLF，锚点写的是 LF）。"""
    normalized = text.replace("\r\n", "\n")
    return normalized.count(anchor.replace("\r\n", "\n"))


def _apply_anchor(text: str, old: str, new: str) -> str:
    crlf = "\r\n" in text
    body = text.replace("\r\n", "\n")
    body = body.replace(old.replace("\r\n", "\n"), new.replace("\r\n", "\n"), 1)
    return body.replace("\n", "\r\n") if crlf else body


def check_anchors() -> int:
    bad = 0
    for m in MUTATIONS:
        path = REPO_ROOT / m.path
        if not path.is_file():
            print(f"  [FAIL] {m.mutation_id} 目标文件不存在: {m.path}")
            bad += 1
            continue
        n = _anchor_hits(path.read_text(encoding="utf-8"), m.old)
        if n == 1:
            print(f"  [OK] {m.mutation_id} (n=1)")
        else:
            print(f"  [FAIL] {m.mutation_id} ANCHOR-MISS: 命中 {n} 次（应为 1）")
            bad += 1
    return 1 if bad else 0


def _run_pytest(targets: list[str], node: str | None) -> tuple[int, str]:
    args = ["python", "-m", "pytest", *targets, "-q", "--no-header",
            "-p", "no:cacheprovider", "--tb=no"]
    if node:
        args += ["-k", node]
    r = subprocess.run(
        args, cwd=str(REPO_ROOT), capture_output=True,
        encoding="utf-8", errors="replace", timeout=2400,
    )
    return r.returncode, r.stdout + r.stderr


def apply_all() -> int:
    verdicts: list[tuple[str, str]] = []
    for m in MUTATIONS:
        path = REPO_ROOT / m.path
        original = path.read_bytes()
        text = original.decode("utf-8")
        if _anchor_hits(text, m.old) != 1:
            verdicts.append((m.mutation_id, "ANCHOR-MISS"))
            continue

        is_pilot = m.mutation_id in _PILOT_MUTATIONS
        if is_pilot:
            targets = list(_PILOT_TESTS)
            node = _PILOT_EXPECTED_NODE
        else:
            targets = [TEST_FILE, TIER_TEST_FILE]
            node = m.test_name
        try:
            path.write_text(_apply_anchor(text, m.old, m.new), encoding="utf-8")
            code, out = _run_pytest(targets, node)
            if code == 0:
                verdicts.append((m.mutation_id, "GREEN"))
            else:
                expected = node or ""
                verdicts.append(
                    (m.mutation_id, "RED" if expected in out else "WRONG-TEST")
                )
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original, f"{m.mutation_id} 字节复原失败"

    print()
    reds = 0
    for mid, verdict in verdicts:
        mark = "OK " if verdict == "RED" else "!!!"
        print(f"  [{mark}] {mid:<38} {verdict}")
        reds += verdict == "RED"
    print()
    print(f"RED {reds}/{len(verdicts)}")
    return 0 if reds == len(verdicts) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ns = ap.parse_args()
    if ns.check_anchors:
        return check_anchors()
    if ns.apply:
        return apply_all()
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
