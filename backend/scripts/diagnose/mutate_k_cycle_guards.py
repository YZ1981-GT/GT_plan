#!/usr/bin/env python
"""K 循环收口 spec 的守卫变异检验（Task 22 / Requirement 13.9）。

**为什么需要它**：守卫全绿有两种可能 —— 代码真的对，或者守卫本身查不出问题。
平台已多次栽在后者（「grep 式守卫只查字符串存在」「参数化集合为空整条 SKIP」
「守卫把错值当基线锁死」）。本脚本对每条守卫施加一个「复现旧缺陷」的变异，
若守卫不打红即判定该守卫无效。

**三态判定（不看退出码）**

    RED          打红且**正是**预期那条守卫文件   ⇒ 守卫有效
    GREEN        没打红                           ⇒ 守卫缺陷（假绿）
    ANCHOR-MISS  锚点未命中 / 命中数 != 1         ⇒ 本脚本缺陷
    WRONG-TEST   打红了但不是预期文件             ⇒ 污染残留或锚点错行

只看退出码会把后三态全误判成 RED。故判据是「失败测试名集合的差集」。

**锚点铁律**（都是踩过的坑）

- 锚点必须**行内**，禁用字面 ``\\n`` 跨行 —— CRLF 文件下必失配（ANCHOR-MISS）
- 命中数必须**恰好 1**，否则改动位置不确定
- 备份落 ``.bak`` + md5 还原核验；异常路径也要还原（try/finally）
- 前端变异需跑 vitest（慢），默认跳过，用 ``--with-frontend`` 开启

**用法**::

    python backend/scripts/diagnose/mutate_k_cycle_guards.py            # 全部后端变异
    python backend/scripts/diagnose/mutate_k_cycle_guards.py --list     # 只列清单与覆盖面
    python backend/scripts/diagnose/mutate_k_cycle_guards.py --only M07 # 单条
    python backend/scripts/diagnose/mutate_k_cycle_guards.py --with-frontend
    python backend/scripts/diagnose/mutate_k_cycle_guards.py --restore  # 崩溃后兜底还原

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Task 22 / Requirement 13.9 / Property 48
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

ROOT = Path(__file__).resolve().parents[3]
assert (ROOT / "backend").is_dir(), f"仓库根解析错误：{ROOT}"

FE_DIR = ROOT / "audit-platform/frontend"


def _utf8_stdout() -> None:
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc is not None:
            try:
                rc(encoding="utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                pass


# ─────────────────────────────────────────────────────────────────────────────
# 守卫文件清单（targets）—— 覆盖面判据：每个文件至少被一条变异指向
# ─────────────────────────────────────────────────────────────────────────────

#: 本 spec 的全部守卫文件。**漏一个 = 该文件的守卫全体未经检验**。
GUARD_FILES: dict[str, str] = {
    "row_code_evidence": "backend/tests/four_table/test_k_cycle_row_code_evidence.py",
    "source_facts": "backend/tests/test_k_source_template_facts.py",
    "cycle_specs": "backend/tests/four_table/test_k_cycle_specs.py",
    "resolution_live": "backend/tests/four_table/test_k_cycle_resolution_live.py",
    "extraction": "backend/tests/four_table/test_k_cycle_extraction.py",
    "preset_closure": "backend/tests/four_table/test_k_cycle_preset_closure.py",
    "cross_spec_evidence": "backend/tests/four_table/test_cycle_specs_row_code_evidence.py",
    "k1_k2_single_source": "backend/tests/four_table/test_k1_k2_spec_single_source.py",
    "k1_presets_ft": "backend/tests/four_table/test_k1_formula_presets.py",
    "k1_presets_fm": "backend/tests/formula_management/test_k1_formula_presets.py",
    "k2_scope": "backend/tests/four_table/test_k2_account_scope.py",
    "k_cycle_presets": "backend/tests/four_table/test_k_cycle_formula_presets.py",
    "ci_wiring": "backend/tests/test_k_cycle_ci_wiring.py",
    "note_row_code": "backend/tests/four_table/test_note_k_row_code_evidence.py",
    "kit_row_codes": "backend/tests/services/test_note_structure_kit_row_codes.py",
    "failclosed_diag": "backend/tests/four_table/test_row_scope_failclosed_diagnosis.py",
    "note_closure": "backend/tests/services/test_note_k_structure_closure.py",
    "col_variant": "backend/tests/services/test_note_k_column_variant_alignment.py",
    "aging_payload": "backend/tests/services/test_note_k_aging_and_payload_closure.py",
}

#: 前端守卫（需 vitest，默认跳过）
FRONTEND_GUARDS: dict[str, str] = {
    "fe_cross_lock": (
        "src/components/workpaper/composables/__tests__/kCycleAccountScopeCrossLock.spec.ts"
    ),
    "fe_row_scope_failure": (
        "src/components/workpaper/composables/__tests__/rowScopeFailure.spec.ts"
    ),
    "fe_k11_sign": (
        "src/components/workpaper/composables/__tests__/k11DisclosureSign.spec.ts"
    ),
    "fe_note_contract": (
        "src/components/workpaper/composables/__tests__/kCycleNoteContract.spec.ts"
    ),
    #: 「本项目无此科目」三态判据（平台共享件）。本 spec 的 Task 25 浏览器实测在这里
    #: 修了 K6 的假 0 缺口（后端给 `empty_reason`、前端只看码列表 ⇒ 判据漂移）。
    "fe_tb_absent": (
        "src/components/workpaper/composables/shared/__tests__/tbSourceAbsent.spec.ts"
    ),
}

# 被变异的生产文件
SPECS_PY = "backend/app/services/four_table/k_cycle_specs.py"
PC_PY = "backend/app/services/four_table/parent_check.py"
STRAT = "backend/app/routers/wp_render_strategies"
MAP_JSON = "backend/data/prefill_formula_mapping.json"
FACTS_PY = GUARD_FILES["source_facts"]
YML = ".github/workflows/governance-checks.yml"
CI_GUARD = GUARD_FILES["ci_wiring"]
ROWCODE_FIX = "backend/scripts/fix/fix_note_k_report_row_codes.py"
SYNC_SVC = "backend/app/services/wp_disclosure_sync_service.py"
K11_MAP = (
    "audit-platform/frontend/src/components/workpaper/composables/k11NoteSectionMap.ts"
)
NOTE_LISTED = "backend/data/note_template_listed.json"
NOTE_SOE = "backend/data/note_template_soe.json"
SEG_GEN = "backend/scripts/gen/gen_note_shared_table_segments.py"


@dataclass(frozen=True)
class Mutation:
    """一条变异。

    Attributes:
        mid: 稳定编号（`--only` 用）。
        why: 复现的是哪个旧缺陷（写进报告，便于判断变异是否有意义）。
        target: 被改文件（仓库相对路径）。
        anchor: **行内**锚点原文，必须在目标文件中恰好出现 1 次。
        repl: 替换文本。
        expect: 期望打红的守卫键（:data:`GUARD_FILES` / :data:`FRONTEND_GUARDS`）。
            可给多个 —— 任一命中即判 RED。
        json_key: 非空表示走 JSON 补丁模式（`anchor`/`repl` 忽略）。
        frontend: 是否需要跑前端测试。
    """

    mid: str
    why: str
    target: str
    expect: tuple[str, ...]
    anchor: str = ""
    repl: str = ""
    json_patch: str = ""
    frontend: bool = False
    #: 正则锚点（需要跨行定位时用）。与 `anchor` 二选一。
    #:
    #: 🔴 跨行一律用 `\s+`（`\s` 含 `\r`，CRLF 安全），**禁写字面 `\n`** ——
    #: 那在 CRLF 文件里必失配，表现为 ANCHOR-MISS。命中数同样必须为 1。
    regex: str = ""
    #: 期望打红的**具体测试函数名**（可选，给了就逐一精确校验，全部命中才算 RED）。
    #:
    #: 🔴 只判「文件级有新失败」会把 WRONG-TEST 混进 RED：同一守卫文件里常有多条
    #: 测试，变异可能只踩中相邻那条（例如改 sheet 名既碰覆盖面又碰逐字校验），
    #: 于是「我以为验的是 A，其实红的是 B」，A 仍未经检验。给了 `expect_test`
    #: 之后，缺任一条即判 WRONG-TEST。
    expect_test: tuple[str, ...] = ()


# ─────────────────────────────────────────────────────────────────────────────
# 变异清单
# ─────────────────────────────────────────────────────────────────────────────

MUTATIONS: list[Mutation] = [
    # ── A. 声明真源 `k_cycle_specs.py` ───────────────────────────────────
    Mutation(
        "M01",
        "K9 row_code_soe 回退到 IS-023（= 减：所得税费用，ACTIVE_WRONG 活错数）",
        SPECS_PY,
        ("row_code_evidence", "cross_spec_evidence"),
        anchor='        row_code_soe="IS-005",',
        repl='        row_code_soe="IS-023",',
    ),
    Mutation(
        "M02",
        "K6 has_account 回退 False（把「宁缺勿造」错误结论重新钉死）",
        SPECS_PY,
        ("row_code_evidence", "cycle_specs"),
        anchor="        has_account=True,",
        repl="        has_account=False,",
    ),
    Mutation(
        "M03",
        "K5 撤 is_liability + gross_direction（负债被判成备抵、gross 变空）",
        SPECS_PY,
        ("cycle_specs", "row_code_evidence"),
        # 🔴 `is_liability=True` 在 K3/K4/K5/K7 + liability_spec_for 共 5 处出现，
        #    单行锚点无法定位到 K5。用**正则**跨行锚定（`\s` 含 `\r`，CRLF 安全），
        #    以 K5 独有的 `fallback_standard="2801"` 做定位前缀。
        #    禁写字面 `\n` —— CRLF 文件下必失配（ANCHOR-MISS）。
        regex=r'(fallback_standard="2801",\s+)is_liability=True,(\s+)gross_direction="credit",',
        repl=r"\1is_liability=False,\2gross_direction=None,",
    ),
    Mutation(
        "M04",
        "K3 撤 extra_standard_codes（2231 应付利息并入 gross ⇒ 与 L2 双算）",
        SPECS_PY,
        ("cycle_specs", "resolution_live"),
        anchor='        extra_standard_codes=("2231",),',
        repl="        extra_standard_codes=(),",
    ),
    Mutation(
        "M05",
        "K6 撤 provision_row_code（备抵 1482 不再经 IMP-007 独立行解析）",
        SPECS_PY,
        ("cycle_specs", "resolution_live"),
        anchor='        provision_row_code="IMP-007",',
        repl="        provision_row_code=None,",
    ),
    Mutation(
        "M06",
        "K6 负债侧撤兜底码（report_config 缺公式的项目取不到数）",
        SPECS_PY,
        ("extraction",),
        anchor="        fallback_gross=(K6_LIABILITY_STANDARD_CODE,),",
        repl="        fallback_gross=(),",
    ),
    Mutation(
        "M07",
        "K1 撤备抵名称过滤（宽前缀 1231 会把 D1/D2 的坏账串进来）",
        SPECS_PY,
        ("cycle_specs", "k1_k2_single_source"),
        anchor='        provision_name_filter="其他应收款",',
        repl="        provision_name_filter=None,",
    ),
    Mutation(
        "M08",
        "K1 撤 extra_standard_codes（应收股利/利息不再单列）",
        SPECS_PY,
        ("cycle_specs", "k1_k2_single_source"),
        anchor='        extra_standard_codes=("1131", "1132"),',
        repl="        extra_standard_codes=(),",
    ),
    Mutation(
        "M09",
        "K2 兜底码回退 1231（坏账准备，历史错误科目族）",
        SPECS_PY,
        ("cycle_specs", "k2_scope", "k1_k2_single_source"),
        anchor='        fallback_standard="1901",',
        repl='        fallback_standard="1231",',
    ),
    Mutation(
        "M10",
        "K5 兜底码回退 2701（长期应付款，L5 科目）",
        SPECS_PY,
        ("cycle_specs", "row_code_evidence"),
        anchor='        fallback_standard="2801",',
        repl='        fallback_standard="2701",',
    ),
    Mutation(
        "M11",
        "撤销 K0 豁免登记（豁免退化成静默盲区）",
        SPECS_PY,
        ("cycle_specs",),
        anchor='    "K0": EXEMPT_REASON_K0,',
        repl="",
    ),
    Mutation(
        "M12",
        "重新引入语义桥接（Task 10 已撤回的死代码）",
        SPECS_PY,
        ("cycle_specs",),
        anchor="def get_k_cycle_spec(wp_code: str) -> KCycleSpec | None:",
        repl=(
            "def to_semantic_spec(wp_code):\n"
            "    return None\n\n\n"
            "def get_k_cycle_spec(wp_code: str) -> KCycleSpec | None:"
        ),
    ),
    # ── B. 三口径共享件 `parent_check.py` ────────────────────────────────
    Mutation(
        "M13",
        "三态语义破坏：found=False 的槽也产键（前端把「无科目」显示成「余额 0」）",
        PC_PY,
        ("extraction",),
        anchor="if slot is None or not slot.found:",
        repl="if slot is None:",
    ),
    Mutation(
        "M14",
        "禁用 contra 方向自校验（族内反向子科目导致叶子和与父额不平）",
        PC_PY,
        ("extraction",),
        anchor="        if not occurrence and parent != 0.0 and abs(leaf_sum - parent) > TOLERANCE:",
        repl="        if False:",
    ),
    Mutation(
        "M15",
        "删 wide_prefix_scope 标记（宽口径自洽被误读成本循环已勾稽）",
        PC_PY,
        ("extraction",),
        anchor='        out[SLOT_PROVISION]["wide_prefix_scope"] = True',
        repl="        pass",
    ),
    Mutation(
        "M16",
        "wide_prefix_scope 恒真（标记失去信息量）",
        PC_PY,
        ("extraction",),
        anchor='if SLOT_PROVISION in out and not bool(getattr(accounts, "provision_exact", False)):',
        repl="if SLOT_PROVISION in out:",
    ),
    Mutation(
        "M17",
        "丢掉第三口径 trial_balance（退化成两口径，查不出 recalc 父子双算）",
        PC_PY,
        ("extraction",),
        anchor='            "trial_balance": trial,',
        repl='            "trial_balance_DROPPED": trial,',
    ),
    # ── C. render 装配 ──────────────────────────────────────────────────
    Mutation(
        "M18",
        "K6 不下发 adjudication_prefill（审定表回到全手工）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor='        "adjudication_prefill": adjudication_prefill,',
        repl='        "adjudication_prefill_DISABLED": adjudication_prefill,',
    ),
    Mutation(
        "M19",
        "K6 不下发 parent_check",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor='        "parent_check": parent_check,',
        repl='        "parent_check_DISABLED": parent_check,',
    ),
    Mutation(
        "M20",
        "K6 行集套一层 select_leaves（父行被筛掉、parent 恒 0、三口径静默退化）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor="        all_rows = await fetch_tb_balance_all(ctx, label=_LABEL)",
        repl="        all_rows = select_leaves(await fetch_tb_balance_all(ctx, label=_LABEL))",
    ),
    Mutation(
        "M21",
        "K2 行集套一层 select_leaves（同 M20）",
        f"{STRAT}/_k2_other_current_assets.py",
        ("extraction",),
        anchor="    all_rows = await fetch_tb_balance_all(ctx)",
        repl="    all_rows = select_leaves(await fetch_tb_balance_all(ctx))",
    ),
    Mutation(
        "M22",
        "K1 行集套一层 select_leaves（同 M20）",
        f"{STRAT}/_k1_other_receivables.py",
        ("extraction",),
        anchor="    all_rows = await _fetch_tb_balance_all(ctx)",
        repl="    all_rows = select_leaves(await _fetch_tb_balance_all(ctx))",
    ),
    Mutation(
        "M23",
        "K6 不用声明真源的负债规格（回到本地双真源）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor="        ctx, liability_spec_for(standards)",
        repl="        ctx, K6_SPEC.spec_for(standards)",
    ),
    Mutation(
        "M24",
        "K6 empty_reason 恒 None（「本项目无此科目」永不显示，用户只看到 0.00）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor='    out["empty_reason"] = None if leaf_hits else EMPTY_REASON_NOT_IN_PROJECT',
        repl='    out["empty_reason"] = None',
    ),
    Mutation(
        "M25",
        "K6 empty_reason 用 NO_ACCOUNT（谎报「标准科目表无此科目」）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor='    out["empty_reason"] = None if leaf_hits else EMPTY_REASON_NOT_IN_PROJECT',
        repl='    out["empty_reason"] = None if leaf_hits else EMPTY_REASON_NO_ACCOUNT',
    ),
    Mutation(
        "M26",
        "K6 负债侧预填不取绝对值（审定表出现负数、合计对不上）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor='                    "closing_balance": abs(r.closing) if absolute else r.closing,',
        repl='                    "closing_balance": r.closing,',
    ),
    Mutation(
        "M27",
        "K6 预填保留无名行（宁缺勿造被破坏）",
        f"{STRAT}/_k6_held_for_sale.py",
        ("extraction",),
        anchor="            if not name:",
        repl="            if False:",
    ),
    # ── D. 公式预设数据（JSON 补丁）─────────────────────────────────────
    Mutation("M28", "抹掉一个 formula_type", MAP_JSON, ("preset_closure",), json_patch="drop_formula_type"),
    Mutation("M29", "写入非法 formula_type", MAP_JSON, ("preset_closure",), json_patch="illegal_formula_type"),
    Mutation("M30", "formula_type 与公式函数名不符", MAP_JSON, ("preset_closure",), json_patch="mislabel_type"),
    Mutation("M31", "block.sheet 指向源 xlsx 不存在的 tab", MAP_JSON, ("preset_closure",), json_patch="bad_block_sheet"),
    Mutation("M32", "K5 公式实参丢空格（指向不存在的 tab）", MAP_JSON, ("preset_closure",), json_patch="k5_lose_space"),
    Mutation("M33", "损益类回退余额口径", MAP_JSON, ("preset_closure",), json_patch="pl_balance_caliber"),
    Mutation("M34", "损益类期初格回退 TB()（与未审数逐字相同 = 错数）", MAP_JSON, ("preset_closure",), json_patch="pl_opening_tb"),
    Mutation("M35", "使用未注册的期间字面量", MAP_JSON, ("preset_closure",), json_patch="unregistered_period"),
    Mutation(
        "M36",
        "重新引入项目专属辅助项编码（换项目即静默返 0）",
        MAP_JSON,
        ("preset_closure", "k1_presets_ft", "k1_presets_fm"),
        json_patch="revive_aux_code",
    ),
    Mutation("M37", "清空 cells 但不留移除痕迹", MAP_JSON, ("preset_closure",), json_patch="empty_without_note"),
    Mutation("M38", "月度明细丢 12 月", MAP_JSON, ("preset_closure",), json_patch="drop_month_12"),
    Mutation("M39", "预设科目跨循环（K8 写成 6602）", MAP_JSON, ("preset_closure", "k_cycle_presets"), json_patch="cross_cycle_account"),
    Mutation("M40", "wp_name 贴别的循环科目名", MAP_JSON, ("preset_closure",), json_patch="wrong_wp_name"),
    Mutation("M41", "复活 K8「分析程序K8-3」死块", MAP_JSON, ("preset_closure",), json_patch="revive_dead_block"),
    # ── E. 源模板事实守卫自身的冻结常量 ─────────────────────────────────
    Mutation(
        "M42",
        "把冻结的动态标记总数改错 1（验证守卫真在 openpyxl 直读源 xlsx，而非自我循环）",
        FACTS_PY,
        ("source_facts",),
        anchor="TOTAL_MARKERS = ",
        repl="TOTAL_MARKERS = 1 + ",
    ),
    # ── F. 前端交叉锁死（需 vitest）─────────────────────────────────────
    Mutation(
        "M43",
        "前端 K3 row_code 与后端声明脱钩",
        "audit-platform/frontend/src/components/workpaper/composables/k3AccountScope.ts",
        ("fe_cross_lock",),
        # `'BS-050'` 在该文件出现 2 次（listed + soe 两个常量），故锚点须带变量名。
        # `BS-053` 是 K4「其他流动负债」的行 —— 正是 K3 历史上错认的那个码。
        anchor="export const K3_REPORT_ROW_CODE_SOE = 'BS-050'",
        repl="export const K3_REPORT_ROW_CODE_SOE = 'BS-053'",
        frontend=True,
    ),
    # ── G. 披露块（Task 12 / Property 26~28）────────────────────────────
    Mutation(
        "M44",
        "删掉 K13 上市披露块（覆盖面回退到「有 sheet 无预设」的沉默态）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="drop_disclosure_block",
        expect_test=(
            "test_all_disclosure_sheets_have_presets",
            "test_disclosure_fix_script_is_idempotent",
        ),
    ),
    Mutation(
        "M45",
        "把 K1 披露 sheet 的括号「统一」成全角（分母若用 sheet 名集合则查不出）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="normalize_disclosure_bracket",
        # 🔴 这条正是「分母必须用 (wp_code, sheet) 对」的判据：
        #    `附注披露信息（上市公司）` 在 K10/K11/… 里真实存在 ⇒ 逐字校验
        #    (`..._verbatim`) 命中源 xlsx 名字**并集**照样绿，只有按对判的
        #    覆盖面守卫会红。初版守卫拿名字集合当分母，就是被这条揪出来的。
        expect_test=("test_all_disclosure_sheets_have_presets",),
    ),
    Mutation(
        "M46",
        "K2 披露 sheet 写成源 xlsx 不存在的简写（预设永不命中）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="fabricate_disclosure_sheet",
        expect_test=("test_disclosure_sheet_names_are_verbatim",),
    ),
    Mutation(
        "M47",
        "抹掉 K2 披露块 cell_ref 的 `_上市` 后缀（convert 去重时静默丢整块）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="strip_variant_suffix",
        expect_test=("test_disclosure_cell_refs_carry_variant_suffix",),
    ),
    Mutation(
        "M48",
        "K9 披露块两格 cell_ref 撞键（同 wp 内重复 ⇒ 后者被丢）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="collide_disclosure_cell_ref",
        expect_test=("test_disclosure_cell_refs_unique_per_wp",),
    ),
    Mutation(
        "M49",
        "K1 披露块改引明细表（与「审定表→明细表」合成三角环）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="disclosure_ref_detail",
        expect_test=("test_disclosure_blocks_reference_adjudication_one_way",),
    ),
    Mutation(
        "M50",
        "删 K3 披露块的审定表勾稽格（披露与审定各说各话，无追溯）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="drop_disclosure_adjudication_ref",
        expect_test=("test_disclosure_blocks_reference_adjudication_one_way",),
    ),
    Mutation(
        "M51",
        "K4 披露块补 TB()（其科目 account_chart 两侧零命中 = 造假数据）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="k4_disclosure_add_tb",
        expect_test=("test_k4_disclosure_has_no_tb_and_is_registered",),
    ),
    Mutation(
        "M52",
        "删 K4 披露块的「无预设」登记理由（宁缺勿造退化成沉默缺失）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="k4_drop_no_tb_reason",
        expect_test=("test_k4_disclosure_has_no_tb_and_is_registered",),
    ),
    Mutation(
        "M53",
        "K8 披露块回退余额口径（损益类无期末余额，取数恒空）",
        MAP_JSON,
        ("preset_closure",),
        json_patch="disclosure_pl_balance",
        expect_test=("test_disclosure_pl_cycles_use_occurrence",),
    ),
    # ── H. CI 接线（Task 23 / Requirement 13.10、13.11）──────────────────
    Mutation(
        "M54",
        "恢复 `|| echo ::warning::` 假绿兜底（前端守卫失败也 job 照绿）",
        YML,
        ("ci_wiring",),
        anchor=(
            "        run: npx vitest run "
            "src/components/workpaper/composables/__tests__/kCycleAccountScope.spec.ts "
            "src/components/workpaper/composables/__tests__/kCycleAccountScopeCrossLock.spec.ts "
            "--silent=true"
        ),
        repl=(
            "        run: npx vitest run "
            "src/components/workpaper/composables/__tests__/kCycleAccountScope.spec.ts "
            "src/components/workpaper/composables/__tests__/kCycleAccountScopeCrossLock.spec.ts "
            '--silent=true || echo "::warning::pending"'
        ),
        expect_test=("test_k_jobs_have_no_fake_pass_fallback",),
    ),
    Mutation(
        "M55",
        "vitest 过滤器改回幽灵文件（vitest 静默忽略 ⇒ 覆盖面与 yml 表述脱钩）",
        YML,
        ("ci_wiring",),
        anchor="__tests__/kCycleAccountScopeCrossLock.spec.ts --silent=true",
        repl="__tests__/kCycleFourTableWiring.spec.ts --silent=true",
        expect_test=("test_vitest_filters_resolve_to_real_files",),
    ),
    Mutation(
        "M56",
        "CI 引用不存在的测试文件（pytest exit 4，但没人解析 yml 就发现不了）",
        YML,
        ("ci_wiring",),
        anchor="          backend/tests/four_table/test_k_cycle_extraction.py",
        repl="          backend/tests/four_table/test_k_cycle_extraction_v2.py",
        expect_test=("test_referenced_pytest_paths_exist",),
    ),
    Mutation(
        "M57",
        "撤掉披露块幂等脚本的 --check 步骤（幂等收敛态无人看守）",
        YML,
        ("ci_wiring",),
        anchor="        run: python backend/scripts/fix/fix_k_cycle_disclosure_presets.py --check",
        repl="        run: echo skip",
        expect_test=("test_both_idempotent_fix_scripts_are_checked_in_ci",),
    ),
    Mutation(
        "M58",
        "job 重名（`safe_load` 静默保留最后一个 ⇒ 前一个 job 整段消失）",
        YML,
        ("ci_wiring",),
        anchor="  k-cycle-extraction-formula-closure:",
        repl="  k-cycle-frontend:",
        expect_test=("test_no_duplicate_job_names",),
    ),
    Mutation(
        "M59",
        "连库守卫从本地闸门登记名单里删掉（无声掉队）",
        CI_GUARD,
        ("ci_wiring",),
        anchor='    "backend/tests/four_table/test_k_cycle_resolution_live.py":',
        repl='    "backend/tests/four_table/_removed_from_registry.py":',
        expect_test=("test_db_guards_are_registered_as_local_only",),
    ),
    Mutation(
        "M60",
        "把离线守卫塞进本地闸门名单（把「登记」当成免 CI 的后门）",
        CI_GUARD,
        ("ci_wiring",),
        anchor="_LOCAL_ONLY_DB_GUARDS = {",
        repl=(
            "_LOCAL_ONLY_DB_GUARDS = {\n"
            '    "backend/tests/four_table/test_k_cycle_preset_closure.py":\n'
            '        "变异用：离线守卫被当成连库守卫登记，属逃避 CI 的后门",'
        ),
        expect_test=("test_db_guards_are_registered_as_local_only",),
    ),
    # ── I. 附注段首码（Task 14 / Property 39）───────────────────────────
    Mutation(
        "M61",
        "抹掉 listed 五、8 的段首码（回到「owner 推送整表 fail-closed」的沉默态）",
        NOTE_LISTED,
        ("note_row_code",),
        # 该码在整份 listed 模板里唯一 —— `BS-009` 只在 `五、8` 主表出现一次
        anchor='              "report_row_code": "BS-009"\n',
        repl='              "report_row_code": ""\n',
        expect_test=(
            "test_templates_carry_all_planned_codes",
            "test_shared_tables_become_locatable_after_stamping",
            "test_row_code_fix_script_is_idempotent",
        ),
    ),
    Mutation(
        "M62",
        "给「应付利息」造一个码（report_config 四侧零行 ⇒ 造码=造假勾稽）",
        NOTE_SOE,
        ("note_row_code",),
        json_patch="fabricate_interest_row_code",
        expect_test=("test_row_code_fix_script_is_idempotent",),
    ),
    Mutation(
        "M63",
        "PLAN 把 soe 应收股利的码换成异义码（形态同 BS-016 两侧异义）",
        ROWCODE_FIX,
        ("note_row_code",),
        anchor='                "row_code": "BS-016",\n                "owner": "G3",',
        repl='                "row_code": "BS-006",\n                "owner": "G3",',
        expect_test=("test_every_stamp_code_points_at_declared_row_name",),
    ),
    Mutation(
        "M64",
        "PLAN 的 report_row_name 与 report_config 实际行名脱钩",
        ROWCODE_FIX,
        ("note_row_code",),
        anchor='                "report_row_name": "其中：应付股利",',
        repl='                "report_row_name": "应付股利",',
        expect_test=("test_every_stamp_code_points_at_declared_row_name",),
    ),
    Mutation(
        "M65",
        "无码登记的行名换成 report_config 真有的名字（登记理由失效却不自知）",
        ROWCODE_FIX,
        ("note_row_code",),
        # `%应付利息%` / `%应收利息%` 各出现 2 次（两个变体各一条）⇒ 锚点不唯一，
        # 会 ANCHOR-MISS。`%应收股利%` 只在 listed `五、8` 出现一次，故取它。
        anchor='                "absent_name_like": "%应收股利%",',
        repl='                "absent_name_like": "%其他应收款%",',
        expect_test=("test_no_code_rows_really_have_zero_hits",),
    ),
    Mutation(
        "M66",
        "从单 owner 豁免名单删一条（覆盖面自检必须抓出「既未豁免也未补码」）",
        ROWCODE_FIX,
        ("note_row_code",),
        anchor='    "K9": "五、65 / 八、66 管理费用：owner 仅 K9，整表独占",\n',
        repl="",
        expect_test=("test_row_code_fix_script_is_idempotent",),
    ),
    Mutation(
        "M67",
        "共享表清单基线改错 1（验证清单真按模板重算，而非自我循环）",
        SEG_GEN,
        ("note_row_code",),
        anchor='EXPECTED_COUNTS = {"listed": 24, "soe": 8}',
        repl='EXPECTED_COUNTS = {"listed": 25, "soe": 8}',
        expect_test=("test_shared_table_manifest_has_no_drift",),
    ),
    Mutation(
        "M68",
        "共享 kit 重写 rows 时不再搬运段首码（结构脚本与段首码脚本互相回退）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes", "note_row_code"),
        anchor="            if key == \"rows\":",
        repl="            if False:",
        expect_test=(
            "test_apply_plan_preserves_code_end_to_end",
            "test_apply_plan_actually_calls_the_carrier",
        ),
    ),
    Mutation(
        "M69",
        "段首码搬运改按下标配对（结构修订插行后串位、搬到错行）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes",),
        anchor="        code = codes.get(label)",
        repl="        code = next(iter(codes.values()), None)",
        expect_test=("test_position_shift_does_not_break_pairing",),
    ),
    # ── J. fail-closed 可诊断（Task 15 / Property 40）─────────────────────
    Mutation(
        "M70",
        "删掉「模板缺段首码」的话术（成因落到兜底 ⇒ 说不出该找谁改什么）",
        SYNC_SVC,
        ("failclosed_diag",),
        regex=r'    "owner_row_code_not_in_template":\s+\([^)]+\),\s+',
        repl="    ",
        expect_test=("test_every_returned_error_code_has_actionable_hint",),
    ),
    Mutation(
        "M71",
        "话术退化成「把错误码翻成中文」（不给动作，读者仍不知怎么办）",
        SYNC_SVC,
        ("failclosed_diag",),
        anchor='        "附注模板里找不到该表 —— 底稿声明的表名与模板不一致（核对两侧表名逐字相同）"',
        repl='        "表不存在"',
        expect_test=("test_hints_are_actionable_not_restatements",),
    ),
    Mutation(
        "M72",
        "原因只进日志、不进返回值（回到「只知道哪张表失败」的状态）",
        SYNC_SVC,
        ("failclosed_diag",),
        # 改 return 而不是删赋值：删赋值会让紧随其后的 `logger.warning(..., reasons[key])`
        # 抛 KeyError —— 那测出来的是「代码崩了」而不是「原因没进返回值」。
        anchor="    return scoped, unresolved, reasons",
        repl="    return scoped, unresolved, {}",
        expect_test=(
            "test_each_cause_yields_its_own_reason",
            "test_reason_keys_are_exactly_the_unresolved_tables",
        ),
    ),
    Mutation(
        "M73",
        "未登记错误码兜底成空串（空串 = 静默，正是本条要拦的东西）",
        SYNC_SVC,
        ("failclosed_diag",),
        anchor='_ROW_SCOPE_ERROR_FALLBACK = "段边界解析失败（未登记的原因码，请查后端日志）"',
        repl='_ROW_SCOPE_ERROR_FALLBACK = ""',
        expect_test=("test_unknown_code_falls_back_loudly",),
    ),
    Mutation(
        "M74",
        "前端消费方退回自拼文案（后端多返的原因字段成死代码）",
        "audit-platform/frontend/src/components/workpaper/composables/useRestrictedAssetsSync.ts",
        ("fe_row_scope_failure",),
        regex=(
            r"        const failure = rowScopeFailureMessage\(\s+'受限资产',"
            r"\s+data\?\.row_scope_unresolved,\s+data\?\.row_scope_unresolved_reasons,\s+\)"
        ),
        repl=(
            "        const failure = (data?.row_scope_unresolved || []).length"
            "\r\n          ? '受限资产未能同步（段边界解析失败）：'"
            " + (data?.row_scope_unresolved || []).join('、')\r\n          : null"
        ),
        frontend=True,
        expect_test=("row_scope_unresolved_reasons",),
    ),
    # ── K. 附注结构三向比对（Task 16 / Requirement 13.7）──────────────────
    Mutation(
        "M75",
        "前端 K5 披露 sheet 名把「（上市公司)」括号统一成全角（推送永不命中）",
        "audit-platform/frontend/src/components/workpaper/composables/k5NoteSectionMap.ts",
        ("note_closure",),
        anchor="附注披露信息（上市公司)",
        repl="附注披露信息（上市公司）",
        expect_test=("test_class_b_frontend_sheet_names_match_source",),
    ),
    Mutation(
        "M76",
        "同步登记表的 sheet 名与源模板脱钩（K7「国有企业」写成「国企」）",
        "backend/data/note_workpaper_sync_registry.json",
        ("note_closure",),
        # 文本锚点不可用：`"sheet_soe": "附注披露信息（国有企业）"` 在登记表里出现
        # **20 次**（多个循环都用这个写法）⇒ 必走 JSON 补丁按 wp_code 定位。
        json_patch="registry_k7_sheet_soe",
        expect_test=("test_class_b_registry_sheet_names_match_source",),
    ),
    Mutation(
        "M77",
        "模板某表 columns 清空（前端渲染不出列头）",
        NOTE_LISTED,
        ("note_closure",),
        json_patch="strip_k_table_columns",
        expect_test=("test_class_b_every_table_has_columns",),
    ),
    Mutation(
        "M78",
        "模板某表两个列都标 is_label（行标题错位）",
        NOTE_SOE,
        ("note_closure",),
        json_patch="double_label_column",
        expect_test=("test_class_b_exactly_one_label_column",),
    ),
    Mutation(
        "M79",
        "单级表头循环凭空加 `_column_groups`（渲染出假父表头）",
        NOTE_SOE,
        ("note_closure",),
        json_patch="phantom_column_groups",
        expect_test=("test_class_b_single_level_cycles_have_no_phantom_groups",),
    ),
    Mutation(
        "M80",
        "可扩位缺口登记值被上调（假装 Task 18 已收口）",
        GUARD_FILES["note_closure"],
        ("note_closure",),
        anchor="TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18 = 26",
        repl="TEMPLATE_EXPANDABLE_ROWS_PENDING_TASK18 = 29",
        expect_test=("test_class_b_expandable_gap_is_registered",),
    ),
    # ── L. 列头分变体 / 源缺陷登记 / K11 符号（Task 17 / Requirement 8.2~8.7）──
    Mutation(
        "M81",
        "把 K3 soe 主表列头「统一」成 listed 那份（soe 用语整体错掉且不报错）",
        NOTE_SOE,
        ("col_variant",),
        json_patch="unify_k3_variant_columns",
        expect_test=("test_divergent_tables_stay_divergent",),
    ),
    Mutation(
        "M82",
        "单级表标签列去掉 flat（`_infer_groups_from_headers` 会推出凭空父表头）",
        NOTE_SOE,
        ("col_variant",),
        json_patch="drop_flat_flag",
        expect_test=("test_seed_side_single_level_tables_declare_flat",),
    ),
    Mutation(
        "M83",
        "撤掉 K11 载荷的符号翻转接线（附注里减值损失变正数，与利润表口径相反）",
        K11_MAP,
        ("col_variant", "fe_k11_sign"),
        anchor="    currentAmount: k11DisclosureAmount(r.currentAmount),",
        repl="    currentAmount: r.currentAmount,",
        frontend=True,
        # `frontend=True` 时脚本只跑前端守卫，故这里必须写**前端**测试标题；
        # 后端静态守卫由 M88 单独验（同一条变异不能横跨两个 runner）。
        expect_test=("载荷金额全部翻成负数",),
    ),
    Mutation(
        "M84",
        "翻转函数让 0 变成 -0（界面显示「-0.00」）",
        K11_MAP,
        ("fe_k11_sign",),
        anchor="  if (value === 0) return 0",
        repl="  if (value === 0) return -0",
        frontend=True,
        expect_test=("0 保持 0",),
    ),
    Mutation(
        "M85",
        "组件里再翻一次符号（双重翻转 = 翻回正数，且不会报错）",
        "audit-platform/frontend/src/components/workpaper/k11/core/K11TabDisclosureListed.vue",
        ("col_variant",),
        anchor="const payload = buildK11SyncPayload('listed', props.wpId || '',",
        repl=(
            "const _sign = -1 * 1\n    const payload = buildK11SyncPayload"
            "('listed', props.wpId || '',"
        ),
        expect_test=("test_k11_flip_is_single_point",),
    ),
    Mutation(
        "M86",
        "源缺陷登记理由删成一句空话（读者看不出为什么不照抄）",
        GUARD_FILES["col_variant"],
        ("col_variant",),
        regex=r'        "「按款项性质列示」表的标签列列头[^"]+"\s+"[^"]+",',
        repl='        "源模板笔误",',
        expect_test=("test_every_defect_has_substantial_reason",),
    ),
    Mutation(
        "M87",
        "把 K2 从「推 columns 的循环」清单里删掉（清单与代码脱钩 ⇒ 8.5 判据空转）",
        GUARD_FILES["col_variant"],
        ("col_variant",),
        anchor='FE_COLUMN_PUSHERS: tuple[str, ...] = ("K2", "K3", "K4", "K5", "K6", "K7")',
        repl='FE_COLUMN_PUSHERS: tuple[str, ...] = ("K3", "K4", "K5", "K6", "K7")',
        expect_test=("test_non_pushers_really_do_not_push_columns",),
    ),
    Mutation(
        "M88",
        "翻转函数改名（后端静态守卫应抓出「8.7 未实现」）",
        K11_MAP,
        ("col_variant",),
        anchor="export function k11DisclosureAmount(",
        repl="export function k11FlipAmount(",
        expect_test=("test_k11_sign_flip_exists_in_payload_layer",),
    ),
    # ── N. 账龄与载荷收口（Task 19 / Requirement 10.x、12.x）─────────────
    Mutation(
        "M98",
        "soe 账龄首档「统一」成 listed 写法（两版用语脱钩且不报错）",
        NOTE_SOE,
        ("aging_payload",),
        json_patch="unify_soe_aging_first_bucket",
        expect_test=("test_soe_aging_table_uses_soe_first_bucket",),
    ),
    Mutation(
        "M99",
        "把账龄作列的表改成账龄分档行（逐项列示表语义被改掉）",
        NOTE_LISTED,
        ("aging_payload",),
        json_patch="aging_column_to_rows",
        expect_test=(
            "test_aging_stays_as_column_where_registered",
            "test_aging_as_column_registry_is_complete",
        ),
    ),
    Mutation(
        "M100",
        "删掉 K1 listed 的月度细分行（源模板事实丢失）",
        NOTE_LISTED,
        ("aging_payload",),
        json_patch="drop_monthly_subdivision",
        expect_test=("test_listed_monthly_subdivision_rows_kept",),
    ),
    Mutation(
        "M101",
        "给无账龄循环（K4）塞一行账龄分档",
        NOTE_SOE,
        ("aging_payload",),
        json_patch="inject_aging_into_no_aging_cycle",
        expect_test=("test_no_aging_cycles_have_no_aging_enum",),
    ),
    Mutation(
        "M102",
        "K1 断开账龄共享真源（两版首档字面会各写一份而分叉）",
        "audit-platform/frontend/src/components/workpaper/composables/k1DisclosureModel.ts",
        ("aging_payload",),
        anchor="import { buildDisclosureAgingLabelMap } from './disclosureAgingLabels'",
        repl="const buildDisclosureAgingLabelMap = () => ({})",
        expect_test=("test_k1_aging_rows_are_driven_by_single_source",),
    ),
    Mutation(
        "M103",
        "子表名混入表头文字（推送落不到表，且不报错）",
        "audit-platform/frontend/src/components/workpaper/composables/k8NoteSectionMap.ts",
        ("aging_payload",),
        anchor="{ main: '销售费用（按费用性质列示）' }",
        repl="{ main: '销售费用（按费用性质列示）', header: '项目' }",
        expect_test=(
            "test_subtable_values_match_template_names",
            "test_subtable_values_are_not_headers_or_english_keys",
        ),
    ),
    # ── N2. 前端载荷契约（Task 21 / Property 36~38、42~45）────────────────
    # 🔴 与 M102/M103 的分工：那两条验的是**后端静态守卫**（`aging_payload` 读前端
    # 源码），这四条验的是**前端 vitest 守卫**。同一条变异不能横跨两个 runner
    # （`frontend=True` 时脚本只跑 vitest），故 M107 与 M102 共用锚点但分开登记。
    Mutation(
        "M104",
        "给无账龄循环（K5）引入账龄模块（会把账龄分档带进无账龄维度的循环）",
        "audit-platform/frontend/src/components/workpaper/composables/k5NoteSectionMap.ts",
        ("fe_note_contract",),
        anchor="  // 叙述正文必须挂 sub_table_data 内（后端 `_extract_note_texts(sub_table_data)` 只认这里）",
        repl=(
            "  const AGING_BANDS = ['1年以内', '1至2年']\n"
            "  void AGING_BANDS\n"
            "  // 叙述正文必须挂 sub_table_data 内（后端 `_extract_note_texts(sub_table_data)` 只认这里）"
        ),
        frontend=True,
        expect_test=("k5 的 NoteSectionMap 不引用任何账龄模块",),
    ),
    Mutation(
        "M105",
        "K9 子表名混入表头文字（推送落不到表，且不报错）",
        "audit-platform/frontend/src/components/workpaper/composables/k9NoteSectionMap.ts",
        ("fe_note_contract",),
        anchor="export const K9_SOE_SUBTABLE = { main: '管理费用' } as const",
        repl="export const K9_SOE_SUBTABLE = { main: '管理费用', header: '项目' } as const",
        frontend=True,
        expect_test=("k9 的子表名常量不含表头文字或英文列 key",),
    ),
    Mutation(
        "M106",
        "拆掉 K4 叙述段的空文本闸门（用户没填也推空段，覆盖附注既有正文）",
        "audit-platform/frontend/src/components/workpaper/composables/k4NoteSectionMap.ts",
        ("fe_note_contract",),
        anchor="  if (narrativeText.trim()) {",
        repl="  if (true) {",
        frontend=True,
        expect_test=("k4 的 _note_texts 过滤空文本",),
    ),
    Mutation(
        "M107",
        "K1 断开账龄共享真源（前端侧判据；后端静态侧由 M102 验）",
        "audit-platform/frontend/src/components/workpaper/composables/k1DisclosureModel.ts",
        ("fe_note_contract",),
        anchor="import { buildDisclosureAgingLabelMap } from './disclosureAgingLabels'",
        repl="const buildDisclosureAgingLabelMap = () => ({})",
        frontend=True,
        expect_test=("K1 走共享真源而不是自写枚举",),
    ),
    Mutation(
        "M108",
        "把守卫自己的 stripComments 变成恒等函数（注释即可满足判据 ⇒ 假绿总开关）",
        (
            "audit-platform/frontend/src/components/workpaper/composables/"
            "__tests__/kCycleNoteContract.spec.ts"
        ),
        ("fe_note_contract",),
        anchor="export function stripComments(src: string): string {",
        repl="export function stripComments(src: string): string {\n  return src",
        frontend=True,
        expect_test=(
            "行注释 / 块注释都被剥掉",
            "注释里的中文 title 不算数（否则注释即可假绿）",
            "注释里的空文本闸门不算数",
        ),
    ),
    # ── N3. 「本项目无此科目」判据（Task 25 浏览器实测所修）─────────────────
    Mutation(
        "M109",
        "撤掉 empty_reason 权威判定（K6 的「本项目无此科目」重新伪装成「余额为 0」）",
        (
            "audit-platform/frontend/src/components/workpaper/composables/shared/"
            "tbSourceCodes.ts"
        ),
        ("fe_tb_absent",),
        anchor="  if (String(src.empty_reason ?? '').trim()) return true",
        repl="  // 变异：撤掉 empty_reason 判定",
        frontend=True,
        expect_test=("后端给了 empty_reason ⇒ 判 absent，即便码列表非空",),
    ),
    Mutation(
        "M110",
        "empty_reason 判定改成 `in` 存在性（空串也算「有原因」⇒ 有码的循环被误判 absent）",
        (
            "audit-platform/frontend/src/components/workpaper/composables/shared/"
            "tbSourceCodes.ts"
        ),
        ("fe_tb_absent",),
        anchor="  if (String(src.empty_reason ?? '').trim()) return true",
        repl="  if ('empty_reason' in src) return true",
        frontend=True,
        expect_test=("empty_reason 为 null / 空串 / 全空白 ⇒ 回到按码列表判定",),
    ),
    # ── M. 可扩位行（Task 18 / Requirement 9.1~9.2）────────────────────────
    Mutation(
        "M89",
        "可扩位行 row_type 退回 data（会被结构脚本当占位垃圾删掉 ⇒ 加行落点消失）",
        NOTE_SOE,
        ("note_closure",),
        json_patch="downgrade_expandable_row",
        expect_test=("test_class_b_expandable_gap_is_registered",),
    ),
    Mutation(
        "M90",
        "结构脚本重新一刀切删占位行（把 R9 的可扩位行连带删掉）",
        "backend/scripts/fix/fix_note_k_pl_structure.py",
        ("note_closure",),
        anchor="            if not _is_expandable_row(r):",
        repl="            if True:",
        # 🔴 这条只在 `--apply` 路径生效（`--check` 的 validator 走另一条分支），
        #    所以**只读模板的断言全查不出**：数据此刻没变，下次 apply 才会删。
        #    判据必须直接调 `_strip_placeholder_rows()` 看可扩位行是否活下来。
        expect_test=("test_structure_script_keeps_expandable_rows",),
    ),
    Mutation(
        "M92",
        "共享 kit 重写 rows 时不再搬运可扩位行（结构脚本与可扩位脚本互相回退）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes",),
        anchor="                want = carry_expandable_rows(",
        repl="                want = (lambda *a, **k: want)(",
        expect_test=(
            "test_apply_plan_preserves_expandable_end_to_end",
            "test_apply_plan_actually_calls_the_expandable_carrier",
        ),
    ),
    Mutation(
        "M93",
        "可扩位行搬到合计行**之后**（附注里合计行上方凭空空一行、合计被推到中间）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes",),
        anchor="            at = _tail_total_start(out)\n        out.insert(at, row)",
        repl="            at = _tail_total_start(out)\n        out.append(row)",
        expect_test=("test_expandable_row_is_carried_before_total",),
    ),
    Mutation(
        "M94",
        "把 `row_type='data'` 的占位垃圾行也搬过去（垃圾行永生）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes",),
        anchor='        if str(r.get("row_type") or "") != _EXPANDABLE_ROW_TYPE:\n            continue\n',
        repl="",
        expect_test=("test_non_expandable_placeholder_is_not_carried",),
    ),
    Mutation(
        "M91",
        "可扩位处数不闭环（少登记一处 ⇒ 有标记无人负责）",
        "backend/scripts/fix/fix_note_k_expandable_rows.py",
        ("note_closure",),
        anchor='    ("soe", "八、42", "按款项性质列示", "可无限量添加行", "K3!A16"),\n',
        repl="",
        expect_test=("test_class_b_both_writers_check_zero",),
    ),
    Mutation(
        "M95",
        "抹掉 K6 的位置锚点（4 处 label 全一样 ⇒ 中间那处会被挤到表尾）",
        "backend/scripts/fix/fix_note_k_expandable_rows.py",
        ("note_closure",),
        anchor='("listed", "五、11", "持有待售资产减值准备", "……", "K6!A37", "无形资产"),',
        repl='("listed", "五、11", "持有待售资产减值准备", "……", "K6!A37"),',
        expect_test=("test_class_b_both_writers_check_zero",),
    ),
    Mutation(
        "M96",
        "kit 把表中间的可扩位行也一律插到合计前（与 after_label 落位打架）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes",),
        anchor="        if i != old_tail - 1 and i > 0 and isinstance(old_list[i - 1], Mapping):",
        repl="        if False:",
        expect_test=("test_mid_table_expandable_keeps_relative_position",),
    ),
    Mutation(
        "M97",
        "kit 把贴表尾的可扩位行也按前一行 label 还原（会被新增数据行挤到中间）",
        "backend/scripts/fix/_note_structure_kit.py",
        ("kit_row_codes",),
        anchor="        if i != old_tail - 1 and i > 0 and isinstance(old_list[i - 1], Mapping):",
        repl="        if i > 0 and isinstance(old_list[i - 1], Mapping):",
        expect_test=("test_tail_expandable_stays_at_data_area_end",),
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# JSON 补丁实现
# ─────────────────────────────────────────────────────────────────────────────


def _blk(data: dict, wp: str, sheet_sub: str) -> dict:
    for b in data["mappings"]:
        if b.get("wp_code") == wp and sheet_sub in str(b.get("sheet", "")):
            return b
    raise KeyError(f"未找到块 {wp}/{sheet_sub}")


def _replace_cell(b: dict, idx: int, **over) -> None:
    b["cells"][idx] = {**b["cells"][idx], **over}


def _registry_entry(doc: dict, wp: str) -> dict:
    """`note_workpaper_sync_registry.json` 里按 wp_code 定位条目（唯一命中）。"""
    hits = [
        e
        for e in doc.get("entries") or []
        if str(e.get("wp_code") or "").upper() == wp.upper()
    ]
    if len(hits) != 1:
        raise KeyError(f"登记表 {wp} 命中 {len(hits)} 条")
    return hits[0]


def _note_table(doc: dict, section: str, table: str) -> dict:
    """附注模板里定位一张表（章节号 + 表名唯一命中）。"""
    secs = [
        s
        for s in doc.get("sections") or []
        if str(s.get("section_number") or "").strip() == section
    ]
    if len(secs) != 1:
        raise KeyError(f"章节 {section} 命中 {len(secs)} 个")
    tbls = [
        t for t in secs[0].get("tables") or [] if str(t.get("name") or "").strip() == table
    ]
    if len(tbls) != 1:
        raise KeyError(f"{section}/{table} 命中 {len(tbls)} 张表")
    return tbls[0]


def _note_row(doc: dict, section: str, table: str, label: str) -> dict:
    """附注模板里定位一行（章节号 + 表名 + 行 label，三者必须唯一命中）。"""
    secs = [
        s
        for s in doc.get("sections") or []
        if str(s.get("section_number") or "").strip() == section
    ]
    if len(secs) != 1:
        raise KeyError(f"章节 {section} 命中 {len(secs)} 个")
    tbls = [
        t for t in secs[0].get("tables") or [] if str(t.get("name") or "").strip() == table
    ]
    if len(tbls) != 1:
        raise KeyError(f"{section}/{table} 命中 {len(tbls)} 张表")
    rows = [
        r
        for r in tbls[0].get("rows") or []
        if isinstance(r, dict) and str(r.get("label") or "").strip() == label
    ]
    if len(rows) != 1:
        raise KeyError(f"{section}/{table}/{label} 命中 {len(rows)} 行")
    return rows[0]


_DISC = "附注披露信息"


def _disc(data: dict, wp: str, variant: str) -> dict:
    """定位披露块。

    Args:
        variant: ``上市`` 或 ``国企``。

    🔴 按 **cell_ref 后缀**判变体，不按 sheet 名 —— K 的披露 tab 有 6 种括号写法
    （`(上市公司）`/`（上市公司）`/`(上市公司)`/`（国企）`/`(国企）`/`（国有企业）`），
    按名字匹配的定位器在源模板换一个括号时就静默失配（表现为 ANCHOR-MISS）。
    """
    hits = [
        b
        for b in data["mappings"]
        if b.get("wp_code") == wp
        and str(b.get("sheet", "")).startswith(_DISC)
        and any(
            str(c.get("cell_ref", "")).endswith("_" + variant)
            for c in b.get("cells") or []
        )
    ]
    if len(hits) != 1:
        raise KeyError(f"披露块定位失败 {wp}/{variant}：命中 {len(hits)} 个（须为 1）")
    return hits[0]


JSON_PATCHES: dict[str, object] = {
    "drop_formula_type": lambda d: _blk(d, "K3", "审定表")["cells"][0].pop("formula_type", None),
    "illegal_formula_type": lambda d: _replace_cell(_blk(d, "K3", "审定表"), 0, formula_type="BOGUS"),
    "mislabel_type": lambda d: _replace_cell(_blk(d, "K3", "审定表"), 0, formula_type="WP"),
    "bad_block_sheet": lambda d: _blk(d, "K3", "审定表").__setitem__("sheet", "分析程序K3-9"),
    "k5_lose_space": lambda d: _replace_cell(
        _blk(d, "K5", "审定表"), 4, formula="=PREV('K5','审定表K5-1','审定数')"
    ),
    "pl_balance_caliber": lambda d: _replace_cell(
        _blk(d, "K8", "审定表"), 1, formula="=TB('6601','期末余额')"
    ),
    "pl_opening_tb": lambda d: _replace_cell(
        _blk(d, "K10", "审定表"), 0, formula="=TB('6117','本期发生额')", formula_type="TB"
    ),
    "unregistered_period": lambda d: _replace_cell(
        _blk(d, "K3", "审定表"), 0, formula="=TB('2241','年中余额')"
    ),
    "revive_aux_code": lambda d: _blk(d, "K1", "明细表")["cells"].append(
        {
            "cell_ref": "三方收款_SKT211_期末",
            "formula": "=AUX('1221','三方收款标识','SKT211','期末余额')",
            "formula_type": "AUX",
            "description": "变异用",
        }
    ),
    "empty_without_note": lambda d: (
        _blk(d, "K3", "明细表").__setitem__("cells", []),
        _blk(d, "K3", "明细表").pop("_aux_removal_note", None),
    ),
    "drop_month_12": lambda d: _blk(d, "K8", "明细表").__setitem__(
        "cells",
        [c for c in _blk(d, "K8", "明细表")["cells"] if "12月" not in str(c.get("cell_ref"))],
    ),
    "cross_cycle_account": lambda d: _blk(d, "K8", "审定表").__setitem__("account_codes", ["6602"]),
    "wrong_wp_name": lambda d: _blk(d, "K8", "审定表").__setitem__("wp_name", "管理费用审定表"),
    # ── 附注结构三向比对（Task 16）────────────────────────────────────
    "registry_k7_sheet_soe": lambda d: _registry_entry(d, "K7").__setitem__(
        "sheet_soe", "附注披露信息（国企）"
    ),
    # ── 列头分变体 / flat（Task 17）───────────────────────────────────
    "unify_k3_variant_columns": lambda d: _note_table(
        d, "八、42", "其他应付款"
    ).__setitem__(
        "columns",
        [
            {"key": "label", "label": "项目", "is_label": True, "flat": True},
            {"key": "end_amount", "label": "期末余额", "format": "amount"},
            {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
        ],
    ),
    "drop_flat_flag": lambda d: _note_table(d, "八、55", "预计负债")["columns"][0].pop(
        "flat", None
    ),
    # ── 账龄与载荷（Task 19）──────────────────────────────────────────
    "unify_soe_aging_first_bucket": lambda d: _note_table(
        d, "八、9", "按账龄披露其他应收款项"
    )["rows"][0].__setitem__("label", "1年以内"),
    # 🔴 按 label 定位而不是按下标：`columns[1]` 未必就是账龄列，改错列时守卫
    #    照样看得到「账龄」⇒ 变异空转（实测踩过一次，判 GREEN）。
    "aging_column_to_rows": lambda d: next(
        c
        for c in _note_table(d, "五、8", "应收政府补助情况")["columns"]
        if "账龄" in str(c.get("label") or "")
    ).__setitem__("label", "金额"),
    "drop_monthly_subdivision": lambda d: _note_table(d, "五、8", "按账龄披露").__setitem__(
        "rows",
        [
            r
            for r in _note_table(d, "五、8", "按账龄披露")["rows"]
            if "个月" not in str(r.get("label") or "")
        ],
    ),
    "inject_aging_into_no_aging_cycle": lambda d: _note_table(
        d, "八、48", "其他流动负债"
    )["rows"].insert(0, {"label": "1至2年", "row_type": "data"}),
    # ── 可扩位行（Task 18）────────────────────────────────────────────
    "downgrade_expandable_row": lambda d: _note_row(
        d, "八、77", "营业外支出", "……"
    ).__setitem__("row_type", "data"),
    "strip_k_table_columns": lambda d: _note_table(d, "五、44", "其他流动负债").__setitem__(
        "columns", []
    ),
    "double_label_column": lambda d: _note_table(d, "八、55", "预计负债")["columns"][
        1
    ].__setitem__("is_label", True),
    "phantom_column_groups": lambda d: _note_table(d, "八、55", "预计负债").__setitem__(
        "_column_groups", [{"label": "假父表头", "start": 1, "span": 2}]
    ),
    # ── 附注段首码（Task 14）──────────────────────────────────────────
    "fabricate_interest_row_code": lambda d: _note_row(
        d, "八、42", "其他应付款", "应付利息"
    ).__setitem__("report_row_code", "BS-054"),
    # ── 披露块（Task 12）──────────────────────────────────────────────
    "drop_disclosure_block": lambda d: d["mappings"].remove(_disc(d, "K13", "上市")),
    "normalize_disclosure_bracket": lambda d: _disc(d, "K1", "上市").__setitem__(
        "sheet", "附注披露信息（上市公司）"
    ),
    "fabricate_disclosure_sheet": lambda d: _disc(d, "K2", "上市").__setitem__(
        "sheet", "附注披露信息（上市）"
    ),
    "strip_variant_suffix": lambda d: _disc(d, "K2", "上市").__setitem__(
        "cells",
        [
            {**c, "cell_ref": str(c.get("cell_ref", "")).removesuffix("_上市")}
            for c in _disc(d, "K2", "上市")["cells"]
        ],
    ),
    "collide_disclosure_cell_ref": lambda d: _replace_cell(
        _disc(d, "K9", "上市"), 1, cell_ref=_disc(d, "K9", "上市")["cells"][0]["cell_ref"]
    ),
    "disclosure_ref_detail": lambda d: _replace_cell(
        _disc(d, "K1", "上市"),
        0,
        formula="=WP('K1','明细表K1-2','合计')",
        formula_type="WP",
    ),
    "drop_disclosure_adjudication_ref": lambda d: _disc(d, "K3", "上市").__setitem__(
        "cells",
        [
            c
            for c in _disc(d, "K3", "上市")["cells"]
            if "审定表" not in str(c.get("formula", ""))
        ],
    ),
    "k4_disclosure_add_tb": lambda d: _disc(d, "K4", "上市")["cells"].append(
        {
            "cell_ref": "期末余额_上市",
            "formula": "=TB('2301','期末余额')",
            "formula_type": "TB",
            "description": "变异用",
        }
    ),
    "k4_drop_no_tb_reason": lambda d: _disc(d, "K4", "国企").pop(
        "_no_tb_preset_reason", None
    ),
    "disclosure_pl_balance": lambda d: _replace_cell(
        _disc(d, "K8", "上市"), 0, formula="=TB('6601','期末余额')"
    ),
    "revive_dead_block": lambda d: d["mappings"].append(
        {
            "wp_code": "K8",
            "wp_name": "管理费用分析程序",
            "sheet": "分析程序K8-3",
            "account_codes": ["6601", "6602", "6603"],
            "cells": [
                {
                    "cell_ref": "本年未审数",
                    "formula": "=TB_SUM('6601~6603','本期发生额')",
                    "formula_type": "TB_SUM",
                    "description": "变异用",
                }
            ],
        }
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# 执行
# ─────────────────────────────────────────────────────────────────────────────


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def run_backend_guards(keys: list[str]) -> set[str]:
    """跑指定守卫文件，返回**失败测试名集合**（不看退出码）。"""
    paths = [GUARD_FILES[k] for k in keys if k in GUARD_FILES]
    if not paths:
        return set()
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--no-header",
         "-p", "no:cacheprovider", "--tb=no"],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    return set(re.findall(r"^FAILED ([^\s]+)", out, re.M))


def run_frontend_guards(keys: list[str]) -> set[str]:
    paths = [FRONTEND_GUARDS[k] for k in keys if k in FRONTEND_GUARDS]
    if not paths:
        return set()
    r = subprocess.run(
        ["npx", "vitest", "run", *paths, "--reporter=json", "--outputFile=.vitest-mut.json"],
        cwd=str(FE_DIR), capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=True,
    )
    res = FE_DIR / ".vitest-mut.json"
    fails: set[str] = set()
    if res.exists():
        try:
            doc = json.loads(res.read_text(encoding="utf-8"))
            for tr in doc.get("testResults", []):
                for a in tr.get("assertionResults", []):
                    if a.get("status") == "failed":
                        fails.add(f"{tr.get('name','')}::{a.get('title','')}")
        except Exception:  # noqa: BLE001
            pass
        res.unlink(missing_ok=True)
    else:
        out = (r.stdout or "") + (r.stderr or "")
        fails = set(re.findall(r"(?:×|✗|FAIL)\s+(\S+)", out))
    return fails


def _apply(m: Mutation) -> None:
    p = ROOT / m.target
    if m.json_patch:
        data = json.loads(p.read_text(encoding="utf-8"))
        JSON_PATCHES[m.json_patch](data)  # type: ignore[operator]
        p.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return
    text = p.read_text(encoding="utf-8")
    if m.regex:
        found = list(re.finditer(m.regex, text))
        if len(found) != 1:
            raise LookupError(f"正则锚点命中 {len(found)} 次（须为 1）：{m.regex[:70]!r}")
        p.write_text(re.sub(m.regex, m.repl, text, count=1), encoding="utf-8")
        return
    if not m.anchor:
        raise LookupError("既无 anchor 也无 regex/json_patch")
    if m.anchor == m.repl:
        # 🔴 anchor == repl 是**空操作变异** —— 它必然「不打红」，会被误判成 GREEN
        #    （守卫缺陷）。实测踩过一次，故此处显式拒绝。
        raise LookupError("anchor 与 repl 完全相同 = 空操作变异，无法检验守卫")
    hits = text.count(m.anchor)
    if hits != 1:
        raise LookupError(f"锚点命中 {hits} 次（须为 1）：{m.anchor[:60]!r}")
    p.write_text(text.replace(m.anchor, m.repl, 1), encoding="utf-8")


def restore_all() -> int:
    """兜底：把所有 .bak 还原（脚本被 Ctrl+C 中断后用）。"""
    n = 0
    for m in MUTATIONS:
        p = ROOT / m.target
        bak = p.with_suffix(p.suffix + ".bak")
        if bak.exists():
            p.write_bytes(bak.read_bytes())
            bak.unlink()
            n += 1
            print(f"  RESTORED {m.target}")
    return n


def main() -> None:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="K 循环守卫变异检验")
    ap.add_argument("--only", help="只跑指定编号（如 M07），逗号分隔")
    ap.add_argument("--with-frontend", action="store_true", help="包含前端变异（需 vitest，慢）")
    ap.add_argument("--list", action="store_true", help="只列清单与覆盖面")
    ap.add_argument("--restore", action="store_true", help="兜底还原所有 .bak")
    args = ap.parse_args()

    if args.restore:
        print(f"还原 {restore_all()} 个文件")
        return

    # 覆盖面自检：每个守卫文件至少被一条变异指向
    covered = {k for m in MUTATIONS for k in m.expect}
    missing = sorted((set(GUARD_FILES) | set(FRONTEND_GUARDS)) - covered)
    if args.list:
        print(f"变异 {len(MUTATIONS)} 条，守卫文件 {len(GUARD_FILES) + len(FRONTEND_GUARDS)} 个")
        for m in MUTATIONS:
            tag = " [FE]" if m.frontend else ""
            print(f"  {m.mid}{tag} {m.why}")
            print(f"        → 期望打红 {list(m.expect)}")
        print(f"\n未被任何变异覆盖的守卫文件：{missing or '无'}")
        return
    if missing:
        print(f"❌ 覆盖面不足：{missing} 未被任何变异指向（该文件守卫全体未经检验）")
        sys.exit(1)

    selected = [m for m in MUTATIONS if not m.frontend or args.with_frontend]
    if args.only:
        want = {x.strip().upper() for x in args.only.split(",")}
        selected = [m for m in selected if m.mid in want]

    # ── 基线：**按 expect 分组**各取一次，且必须在任何变异之前取完 ──────
    #
    # 🔴 两条铁律，都是本轮实测踩出来的：
    #
    # ① **不能一次跑全部 12 个守卫文件**：`test_cycle_specs_row_code_evidence.py` 是
    #    **连库**守卫，与其余文件同进程共跑会污染共享连接池（memory 铁律：「每测试
    #    各自 async 会让第二个起 `NoneType has no attribute send`」）⇒ 基线出现
    #    **34 条不稳定失败**，而单独跑同样 12 个文件是 417 passed 零红。基线不稳定
    #    会让 `fails - base` 差集失真，把真 RED 误判成 GREEN。
    #
    # ② **基线必须前置全部取完**，不能惰性求值。初版把 `baseline_for()` 写成惰性、
    #    又放在 `_apply(m)` **之后**首次调用 ⇒ 取基线时文件已是变异态 ⇒ 基线把变异
    #    造成的失败也算进去 ⇒ 差集恒空 ⇒ 11 条真 RED 全被误判成 GREEN。
    base_cache: dict[tuple[str, ...], set[str]] = {}

    def group_of(keys: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(k for k in keys if k in GUARD_FILES))

    def baseline_for(keys: tuple[str, ...]) -> set[str]:
        return base_cache.get(group_of(keys), set())

    for _m in selected:
        g = group_of(_m.expect)
        if g and g not in base_cache:
            base_cache[g] = run_backend_guards(list(g))
    base_fe = run_frontend_guards(list(FRONTEND_GUARDS)) if args.with_frontend else set()
    print(f"后端基线分组 {len(base_cache)} 组，前端基线失败 {len(base_fe)} 条")
    for g, v in base_cache.items():
        if v:
            print(f"    baseline{list(g)}: {len(v)} 条 —— {sorted(v)[:2]}")

    results: list[dict] = []
    for m in selected:
        p = ROOT / m.target
        original = p.read_bytes()
        before = md5(p)
        bak = p.with_suffix(p.suffix + ".bak")
        bak.write_bytes(original)
        try:
            try:
                _apply(m)
            except Exception as exc:  # noqa: BLE001
                results.append(
                    {"mid": m.mid, "verdict": "ANCHOR-MISS", "why": m.why,
                     "err": f"{type(exc).__name__}: {exc}"}
                )
                continue
            if m.frontend:
                fails = run_frontend_guards(list(m.expect))
                new = fails - base_fe
                hit = bool(new)
            else:
                be_keys = [k for k in m.expect if k in GUARD_FILES]
                fails = run_backend_guards(be_keys)
                new = fails - baseline_for(m.expect)
                hit = any(
                    GUARD_FILES[k].replace("/", "\\") in f or GUARD_FILES[k] in f
                    for k in be_keys
                    for f in new
                )
            # 声明了具体测试名 ⇒ 必须**全部**出现在新增失败里，否则是 WRONG-TEST
            missing_named = [t for t in m.expect_test if not any(t in f for f in new)]
            if hit and missing_named:
                hit = False
            verdict = "GREEN" if not new else ("RED" if hit else "WRONG-TEST")
            results.append(
                {"mid": m.mid, "verdict": verdict, "why": m.why,
                 "expect": list(m.expect), "expect_test": list(m.expect_test),
                 "missing_named": missing_named, "new": sorted(new)[:6]}
            )
            print(f"  {m.mid} {verdict:11s} {m.why[:52]}")
        finally:
            p.write_bytes(original)
            bak.unlink(missing_ok=True)
            if md5(p) != before:
                print(f"❌❌ {m.target} 还原失败！md5 不符", file=sys.stderr)
                sys.exit(3)

    # 还原后逐组重取基线，与开跑时的分组基线逐一比对
    restored_clean = True
    drift: list[str] = []
    for keys, base in list(base_cache.items()):
        now = run_backend_guards(list(keys))
        if sorted(now) != sorted(base):
            restored_clean = False
            drift.append(f"{list(keys)}: base={len(base)} now={len(now)}")

    summary = {
        "total": len(selected),
        "RED": sum(1 for r in results if r["verdict"] == "RED"),
        "GREEN": sum(1 for r in results if r["verdict"] == "GREEN"),
        "ANCHOR_MISS": sum(1 for r in results if r["verdict"] == "ANCHOR-MISS"),
        "WRONG_TEST": sum(1 for r in results if r["verdict"] == "WRONG-TEST"),
        "guard_files": len(GUARD_FILES) + len(FRONTEND_GUARDS),
        "restored_clean": restored_clean,
        "baseline_drift": drift,
        "baseline_groups": {str(list(k)): len(v) for k, v in base_cache.items()},
    }
    (ROOT / "_k_cycle_mutation_report.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print()
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    for r in results:
        if r["verdict"] != "RED":
            print(" !!", json.dumps(r, ensure_ascii=False))
    if summary["GREEN"] or summary["ANCHOR_MISS"] or summary["WRONG_TEST"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
