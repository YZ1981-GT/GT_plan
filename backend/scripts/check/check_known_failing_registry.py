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
    # ══ 2026-10-10 补登 21 条（spec d2-online-edit-platform-closure 回归归因）══════
    #
    # 归因方法：在 `git worktree add --detach HEAD`（5914e315b，不含本 spec 任何改动）上
    # 用**同一口径**跑本门的 pytest，与主工作树逐条比对 junit：这 21 条在 HEAD 上同样红、
    # 失败消息同因（仅归档 spec 路径前缀随检出目录不同），本 spec 新增红 0。
    # 下面按根因分组；首见 commit 一律记 HEAD 5914e315b（确认存在点），已查到的
    # 引入提交写在原因里。
    #
    # ── 归档 spec 后路径失效（FileNotFoundError / setup 断言）──────────────────
    "tests/workpaper_sync/test_d1_05_single_html_adjudication.py"
    "::TestDecisionIsStillSingleHtml::test_verdict_file_says_single_html": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "spec 已于 a6f8158b8 归档到 _archive/31-…，fixture 仍读旧路径 evidence/"
        "task27-d1-5-single-html-adjudication.json ⇒ FileNotFoundError（setup ERROR）",
    ),
    "tests/workpaper_sync/test_d1_05_single_html_adjudication.py"
    "::TestSamePatternAsD44Precedent::test_headers_match_d4_4_verdict_verbatim": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "同 test_verdict_file_says_single_html：归档后 evidence 旧路径失效",
    ),
    "tests/workpaper_sync/test_d1_05_single_html_adjudication.py"
    "::TestSamePatternAsD44Precedent::test_both_verdicts_agree_on_single_html": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "同 test_verdict_file_says_single_html：归档后 evidence 旧路径失效",
    ),
    "tests/workpaper_sync/test_task61_first_published_representation_bootstrap.py"
    "::TestEvidenceLedgerIsRealAndComplete::test_every_check_passed_and_nothing_failed": (
        "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "5914e315b",
        "总纲 spec 已于 239eb9a89 归档，fixture 仍读旧路径 evidence/task61-oo94-word-"
        "pilot-gate/first_published_representation_bootstrap.json ⇒ setup 断言失败",
    ),
    "tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py"
    "::TestBindingConstraintIsMeasured"
    "::test_the_registry_coverage_check_rejects_an_empty_constraint_list": (
        "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "5914e315b",
        "门禁 read_task_body() 读总纲 tasks.md 旧路径（239eb9a89 已归档）⇒ FileNotFoundError",
    ),
    "tests/workpaper_sync/test_task62_generic_docx_entries.py"
    "::TestGeneratorIsIdempotentAndCheckIsStrict::test_check_matches_the_file_on_disk": (
        "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "5914e315b",
        "生成器 requirement_7_7_declared() 读总纲 requirements.md 旧路径（239eb9a89 已归档）"
        " ⇒ Task62GeneratorError",
    ),
    # ── 真库数据：重药安徽 entry pointer 被删 ──────────────────────────────
    #    项目 0ec33ac9 下 18 个 (wp, entry) 有 representation 却无
    #    `working_paper_sync_entry_state` 行；pg_stat 显示该表自 2026-10-09 15:20（PG 重启、
    #    统计清零）以来恰有 18 次已提交删除，本 spec design.md（10-10 22:43 写）的现算
    #    「71 个 entry 有 entry_state」已是删后状态。仓库代码无删除该表的路径（FK 为
    #    RESTRICT，无级联）⇒ 是一次库外/一次性操作。未擅自回填（选哪条 representation
    #    当 current 需要归属方裁决）。
    "tests/workpaper_sync/test_d1_full_book_gate_open_pg.py"
    "::test_published_representation_exists_with_real_adapter": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "真库 wp 68c7740e 的 D1 entry pointer 行缺失 ⇒ EntryPointerMissingError（setup ERROR）；"
        "9 条 representation 仍在",
    ),
    "tests/workpaper_sync/test_d1_full_book_gate_open_pg.py"
    "::test_gate_is_open_frozen_hash_matches_recomputed": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "同 test_published_representation_exists_with_real_adapter（同一 module fixture）",
    ),
    "tests/workpaper_sync/test_d1_full_book_gate_open_pg.py"
    "::test_root_cause_was_missing_plural_instrumentation_entry": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "同 test_published_representation_exists_with_real_adapter（同一 module fixture）",
    ),
    "tests/workpaper_sync/test_d1_full_book_gate_open_pg.py"
    "::test_error_message_omits_frozen_inventory_size": (
        "d1-sync-row-table-engine-and-d1-coverage",
        "5914e315b",
        "同 test_published_representation_exists_with_real_adapter（同一 module fixture）",
    ),
    # ── f1 签名统一后两道门的「f1 特例」判据失效 ─────────────────────────────
    #    5cb7ebe70 把 f1 `build_store_projection` 的 `store_item_id` 从首位位置参数改成
    #    KEYWORD_ONLY（带默认值）⇒ golden digest 不再 SKIP f1、分派分组里首位位置参数组变空。
    #    两条判据本身就写明「分组一变本条会红，届时应连带简化门里的分派分支」。
    "tests/scripts/test_check_staged_tree_self_consistency.py"
    "::test_expected_skips_are_still_actually_skipped": (
        "f1-sync-coverage-and-first-canary",
        "5914e315b",
        "_EXPECTED_SKIPS 登记的 golden digest「[SKIP] f1」已不再出现（5cb7ebe70 统一了 f1 签名）",
    ),
    "tests/scripts/test_check_sync_provider_golden_digest.py"
    "::test_store_item_id_dispatch_keys_on_parameter_kind_not_name": (
        "f1-sync-coverage-and-first-canary",
        "5914e315b",
        "首位位置参数是 store_item_id 的 provider 现算 [] ≠ ['f1']（5cb7ebe70 统一了 f1 签名）",
    ),
    # ── 冻结计数被别 lane 的提交改变 ───────────────────────────────────────
    #    （test_baseline_is_exactly_thirteen_with_owning_lanes 已出列：2026-10-28 G4 / G6 接通后
    #     KNOWN_UNWIRED 15 → 13，spec oo-writeback-template-parity-closure R3 批 B3）
    "tests/workpaper_sync/test_task57_abcs_and_shared_migration.py"
    "::TestFormDifferences::test_ad1_scope_arithmetic_closes": (
        "abcs-cycle-sync-migration",
        "5914e315b",
        "全量 manifest 的 xlsx 独立 entry 现算 138 ≠ slice 冻结 136（manifest 于 "
        "4750bde7d / 5cb7ebe70 / 5fbe5de29 / c0713ac80 多次变动）",
    ),
    "tests/workpaper_sync/test_task54_l_cycle_migration.py"
    "::TestLCycleFormDifferences::test_ld1_carrier_three_way_split_is_real_and_exclusive": (
        "l-cycle-sync-foundation-and-first-canary",
        "5914e315b",
        "共享载体现算 L1~L8 共 8 个，冻结判据只允许 L1/L2（26e5ef994 L3~L8 真双向改线后载体归并）",
    ),
    "tests/workpaper_sync/test_task55_m_cycle_migration.py"
    "::TestMCycleFormDifferences::test_md1_twin_pairing_is_exclusive_and_exhaustive": (
        "m-cycle-sync-foundation-and-first-canary",
        "5914e315b",
        "orphan composable 现算 12 ≠ 冻结 11 − 已删 2（M 域新增 useM*DualMode 载体）",
    ),
    "tests/workpaper_sync/test_sibling_table_ref_row_shift.py"
    "::test_all_multi_region_sheets_shift_sibling_table_refs[审定表F3-1]": (
        "f-cycle-sync-coverage",
        "5914e315b",
        "F3-1 上区 GT_F31_SLOT_ROWS 末行 +1 恰为下区首行（9 = 9），「下方兄弟区」前提不成立；"
        "F3 provider 末次改动 5cb7ebe70",
    ),
    # ── 权威模板目录：别 lane 已提交模板改动，账本 / 登记未跟上 ──────────────────
    "tests/workpaper_sync/test_template_override_resolution.py"
    "::TestProperty3AuthoritativeFrozen::test_index_size_drift_is_registered_not_growing": (
        "template-index-drift-ledger",
        "5914e315b",
        "35 份权威模板的 size_kb 与 _index.json 漂移且未登记进 INDEX_DRIFT_LEDGER"
        "（各循环模板净化提交，如 c0713ac80）",
    ),
    "tests/workpaper_sync/test_template_override_resolution.py"
    "::TestTask24ScopeBoundary::test_authoritative_directory_has_no_uncommitted_changes": (
        "template-index-drift-ledger",
        "5914e315b",
        "KNOWN_DIRTY_AUTHORITATIVE_PATHS 里的 M10 登记已失效（该模板改动已于 0a9600db9 提交）"
        " ⇒ 反向断言 stale",
    ),
    "tests/scripts/test_check_template_index_drift_ledger.py::test_ledger_matches_现算": (
        "template-index-drift-ledger",
        "5914e315b",
        "账本与现算不符 5 条：G4 / H2 / H3 / H8 / M10（别 lane 已提交模板改动）",
    ),
    # ── 别 lane：生成物 stale（生成器 --check 与磁盘文件不一致）─────────────
    #    2026-10-10 复核：task66 现在的失败形态是读总纲 tasks.md 旧路径的 FileNotFoundError
    #    （与上面「归档 spec 后路径失效」同根因）；task67 现为 EntrySourceFactError
    #    （`xlsx/d4/analysis/d4-tab-customer-price` 不在 Task 2 红基线里）。登记不变。
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
    # `test_sibling_table_ref_row_shift.py::test_all_multi_region_sheets_shift_sibling_table_refs
    #  [余额明细表G5-2]`（g-cycle-single-region-detail-lanes，首见 e3dd25a0d）
    #
    # 2026-10-10 本门报僵尸：HEAD 5914e315b 干净检出与主工作树上都已转绿（G 循环 lane 的
    # 提交修好了，非 d2-online-edit-platform-closure 的改动所致）。按棘轮要求删除。
    #
    # `test_task31_frontend_contract.py::test_check_mode_agrees_with_the_stored_artifact`
    #
    # 2026-10-10 spec d2-online-edit-platform-closure 重生成前端契约后转绿（生成物此前漏
    # `adopt_substrate` 路由；本 spec 新增 `ensure_first_publication` 路由与
    # `room_not_writable: 409`，三处一并落盘，`--check` 返回 0）。
    #
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
