# -*- coding: utf-8 -*-
"""预存失败清册棘轮：按声明口径跑 pytest，失败集必须 ⊆ 清册，且清册无僵尸。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-h（2026-09-28）

═══ 这个门禁解决什么 ═══

本仓库工作树长期混多条 lane（实测 `git status --porcelain` 806 条），
`tests/workpaper_sync/` 里躺着一批与当前 lane 无关的既存失败。后果是每个人接手时
都要重新甄别一遍「这条红是我引入的吗」——

上一轮我为 9 条红做归因，最后靠 `git diff --name-only <起点>..HEAD` 证明那 29 个
改动文件不含它们的实现与测试才敢下结论。下一个人会把这件事完整重做。

⇒ 冻结成清册：nodeid + 归属 lane + 首见 commit + 原因摘要。新增红立刻可见，
  历史红不再消耗每个人的注意力。

═══ 口径是显式的，不假装全量 ═══

跑全量 `tests/workpaper_sync/ + tests/scripts/` 约 14700 个用例、耗时过长，
本门用**已验证可复现**的收集口径（`_DEFAULT_K`，270 秒级）。口径写死在这里并可用
`--k` 覆盖；换口径就要重建清册，这是有意的摩擦 —— 免得清册边界含糊。

🔴 明确不声称覆盖全量。清册的语义是「在本口径下，失败集恰为这些」。

═══ 为什么不直接 xfail ═══

`xfail` 要改别 lane 的测试文件（那是他们的工作区），而且会把「红」变成「预期的绿」，
下一个人看不到它还红着。清册把状态留在外部、留在可读的一张表里，不动别人的文件。

═══ 🔴 本门**不进 CI** ═══

清册的语义是「**开发者工作树**上的预存失败」—— 它的成因正是别 lane 的**未提交**改动。
CI 检出的是 HEAD（没有那些改动），失败集完全不同 ⇒ 接进 CI 会永远红。

进 CI 的是它的自测 `backend/tests/scripts/test_check_known_failing_registry.py`
（验清册结构 + nodeid 解析 + 变异，stdlib-only、秒级）。

本门的用法：接手本仓库、拿到一批红时先跑它 ——
  `python backend/scripts/check/check_known_failing_registry.py`
exit 0 说明「这些红都不是你引入的」；报「新增」才需要归因。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent

#: 默认收集口径（与 2026-09-28 实测一致，270 秒级可复现）。
_DEFAULT_TARGETS = ("tests/workpaper_sync/", "tests/scripts/")
_DEFAULT_K = "d1 or template_override or multi_trip or row_shift or check_"

#: 🔴 预存失败清册（棘轮，**只许变短**）。
#:
#: 每条：nodeid -> (归属 lane, 首见 commit, 原因摘要)
#:
#: 首见 commit 记的是「确认它已存在」的那个点，不是「它被引入」的那个点 —— 后者需要
#: 二分查找，成本与收益不匹配；前者足以支撑「不是我引入的」这个判断。
KNOWN_FAILING: dict[str, tuple[str, str, str]] = {
    # ── 别 lane：G 循环兄弟表位移 ──────────────────────────────────────────
    "tests/workpaper_sync/test_sibling_table_ref_row_shift.py"
    "::test_all_multi_region_sheets_shift_sibling_table_refs[余额明细表G5-2]": (
        "g-cycle-single-region-detail-lanes",
        "e3dd25a0d",
        "G5-2 兄弟表引用未随行位移；G 循环 lane 工作区",
    ),
    # ── 别 lane：生成物 stale（生成器 --check 与磁盘文件不一致）─────────────
    "tests/workpaper_sync/test_task31_frontend_contract.py"
    "::test_check_mode_agrees_with_the_stored_artifact": (
        "workpaper-sync-frontend-contract",
        "e3dd25a0d",
        "workpaperSyncContract.generated.ts 过期（routes=19 现算 vs 磁盘）；"
        "需跑 generate_workpaper_sync_frontend_contract.py --apply",
    ),
    "tests/workpaper_sync/test_task64_dedicated_word_chain.py"
    "::TestGeneratorContract::test_generator_check_is_idempotent": (
        "workpaper-sync-dedicated-word-chain",
        "e3dd25a0d",
        "生成器 --check 非幂等；生成物未与源同步",
    ),
    "tests/workpaper_sync/test_task66_legacy_deletion_plan.py"
    "::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk": (
        "workpaper-sync-legacy-deletion",
        "e3dd25a0d",
        "legacy 删除计划生成器 --check 与磁盘文件不一致；生成物未随源更新",
    ),
    "tests/workpaper_sync/test_task67_structural_pre_reconcile.py"
    "::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk": (
        "workpaper-sync-structural-pre-reconcile",
        "e3dd25a0d",
        "结构预对账生成器 --check 与磁盘文件不一致；生成物未随源更新",
    ),
    # ── 别 lane：ref_collision（测试文件本身未完成，`_plan_from_trips` 里
    #    `ref_before=before` 引用未定义名 ⇒ NameError）────────────────────────
    "tests/workpaper_sync/test_workbook_propagation_ref_collision.py"
    "::test_multi_trip_normalise_round_trip[cross_trip_chain_prefix]": (
        "workpaper-sync-row-deletion-multi-region-propagation",
        "e3dd25a0d",
        "测试辅助函数 _plan_from_trips 引用未定义的 before/after ⇒ NameError；"
        "该文件仍是未跟踪的在写状态",
    ),
    "tests/workpaper_sync/test_workbook_propagation_ref_collision.py"
    "::test_multi_trip_normalise_round_trip[cross_trip_same_text_diff_name]": (
        "workpaper-sync-row-deletion-multi-region-propagation",
        "e3dd25a0d",
        "同一辅助函数 _plan_from_trips 的 NameError（同 cross_trip_chain_prefix）",
    ),
    "tests/workpaper_sync/test_workbook_propagation_ref_collision.py"
    "::test_multi_trip_normalise_round_trip[same_trip_whole_equal_k8]": (
        "workpaper-sync-row-deletion-multi-region-propagation",
        "e3dd25a0d",
        "同一辅助函数 _plan_from_trips 的 NameError（同 cross_trip_chain_prefix）",
    ),
    # ── 曾经在册、已移除 ─────────────────────────────────────────────────
    # `test_workbook_row_change_wiring.py::TestPropagationOrderInApply
    #  ::test_propagation_follows_row_shift`
    #
    # 🔴 这条是清册**易变性的实证**，值得留注释：2026-09-28 07:0x 观测它红
    # （`assert 23 < 21` —— shift_sheet_rows 排在 _apply_workbook_propagation 之后），
    # 约一小时后在**完全相同的收集口径**下复跑，它绿了。
    #
    # 期间 `excel_workbook_row_change.py` 的工作树内容被别 lane 改动
    # （工作树 3022 行 vs HEAD 2382 行，640 行未提交差异；mtime 落在那段时间内）。
    # 我方改动经核验完好（`net_propagation_pairs` 工作树/HEAD 各 6 处，
    # `excel_row_shift.py` 工作树 ≡ HEAD 且 clean）。
    #
    # ⇒ 在混多 lane 的单工作树里，「某条测试是否红」是**时间的函数**。清册反映的是
    #   某一时刻的观测，不是永久事实。这正是本门要求「新增/僵尸都报出来」而不是
    #   静默容忍的原因 —— 漂移必须可见。
}

_NODEID_RE = re.compile(r"^(?P<file>tests/[^:]+\.py)::")

_ESCAPED_RE = re.compile(r"\\u[0-9a-fA-F]{4}")


def _unescape_nodeid(nodeid: str) -> str:
    """把 pytest 输出里的 `\\uXXXX` 还原成真字符。

    🔴 实测踩坑：`-q` 模式下 pytest 把参数化 id 里的非 ASCII 转成 ASCII 转义 ——
    `[余额明细表G5-2]` 输出成 `[\\u4f59\\u989d\\u660e\\u7ec6\\u8868G5-2]`。
    清册里写真中文（可读），比对前把输出还原，**两边归一到真字符**。

    不反过来（把清册转成转义形式）：那样万一 pytest 哪天不转义了就对不上，
    而且清册的可读性会毁掉。nodeid 用 `/` 作分隔符，所以 `unicode_escape` 不会
    误伤路径分隔符。
    """
    if not _ESCAPED_RE.search(nodeid):
        return nodeid
    try:
        return nodeid.encode("latin-1", "backslashreplace").decode("unicode_escape")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return nodeid


def _run_pytest(targets: tuple[str, ...], k: str | None) -> tuple[set[str], str]:
    """跑 pytest，返回 (失败 nodeid 集合, 原始尾部输出)。"""
    args = [
        sys.executable, "-m", "pytest", *targets,
        "-q", "--no-header", "--tb=no", "-p", "no:randomly",
    ]
    if k:
        args += ["-k", k]
    proc = subprocess.run(
        args, cwd=str(_BACKEND), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=3600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    failed: set[str] = set()
    for line in out.splitlines():
        s = line.strip()
        for prefix in ("FAILED ", "ERROR "):
            if s.startswith(prefix):
                raw = s[len(prefix):].split(" - ")[0].strip()
                failed.add(_unescape_nodeid(raw))
    return failed, out[-3000:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", default=_DEFAULT_K, help="pytest -k 表达式（默认用声明口径）")
    parser.add_argument("--no-k", action="store_true", help="不加 -k，跑全量（很慢）")
    parser.add_argument("--json", type=str, default=None)
    # 🔴 与 `check_template_index_drift_ledger.py` 的接口保持一致：实测发现本门没有
    #    `--quiet` 时 argparse 直接返回 **2**，而调用方按 0/1 判断 ⇒ 看起来像「门失败」，
    #    实际是参数不认识。两个同族门禁的 flag 必须一致，自测里有一条钉住这点。
    parser.add_argument(
        "--quiet", action="store_true", help="只给结论，不逐条列出清册"
    )
    args = parser.parse_args(argv)

    k = None if args.no_k else args.k
    failed, tail = _run_pytest(_DEFAULT_TARGETS, k)

    registry = set(KNOWN_FAILING)
    newly = sorted(failed - registry)
    zombies = sorted(registry - failed)

    report = {
        "ok": not newly and not zombies,
        "caliber": {"targets": list(_DEFAULT_TARGETS), "k": k},
        "failed_now": sorted(failed),
        "registry_size": len(registry),
        "newly_failing": newly,
        "zombie_entries": zombies,
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["ok"]:
        print(
            f"✅ 预存失败清册一致：本口径下失败 {len(failed)} 条，"
            f"与清册（{len(registry)} 条）逐条相符，无新增、无僵尸"
        )
        if not args.quiet:
            for nodeid in sorted(failed):
                lane, since, why = KNOWN_FAILING[nodeid]
                print(f"   [{lane}] {nodeid.split('::')[-1]} —— {why}（首见 {since}）")
        return 0

    if newly:
        print(
            f"❌ 新增 {len(newly)} 条失败**不在**清册里 —— 先判归因："
            "是本次改动引入的就修，确属别 lane 既存的才登记进 KNOWN_FAILING："
        )
        for n in newly:
            print(f"   [新增] {n}")
    if zombies:
        print(
            f"❌ 清册里 {len(zombies)} 条已经不红了 —— 请从 KNOWN_FAILING 删除"
            "（棘轮只许变短，留着会掩盖该用例重新劣化）："
        )
        for z in zombies:
            print(f"   [僵尸] {z}")
    print("\n--- pytest 尾部输出 ---")
    print(tail)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
