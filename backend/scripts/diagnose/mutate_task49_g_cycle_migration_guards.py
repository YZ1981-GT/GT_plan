# -*- coding: utf-8 -*-
r"""Task 49 守卫变异检验 —— G 循环（除 G7）Excel 独立 entry 迁移。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 5 Task 49

用平台共享件 `backend/scripts/_mutation_kit`（`test_mutation_kit_adoption.py` 对新脚本
强制采纳：共享件的 `run_cli` 把 `guard_files`（覆盖面分母）做成签名层面必填）。

═══ 本脚本的三条硬约束 ═══

1. **数据文件变异一律带 `scope_check`**。四态判定式「新增失败集合是否为空」识别不出
   「锚点落在被测判据的作用域之外」—— 改到了别处会被判 GREEN（守卫缺陷），而真相是
   脚本缺陷。回调解析 JSON 后断言目标字段真的变成了期望值。

2. **重复形态字段用 `scope` + `offset` 相对定位，不用绝对行号**。slice 是生成物，
   `"capability": null,` 出现 17 次、`"html_counterpart_verdict": "exists",` 17 次、
   `"row_identity_is_positional": false,` 16 次、`"endpoint_read": …` 17 次；而绝对行号
   一改文件就失效（Task 47 的 M12 写死 `line=155` 而那行早已是别的内容）。`scope` 取该
   entry 唯一的 `entry_id` 行，`offset` 由 `tmp_t49_anchors*.py`（一次性诊断，已清理）实算。

3. **capability 变异按「裁决形态」而不是「逐 entry 复制」枚举**。本 slice 17 条 entry 的
   capability **全是同一种形态**（null + 三字段齐备的待裁决态），逐条各写一次是 17 份同
   信息量的变异（每条要跑一遍全量守卫 ≈ 27s），换不来任何新判据。这里按**可被区分的
   裁决错法**枚举：四个枚举值各填一次（bidirectional / single_onlyoffice / single_html /
   unreachable）+ 自造枚举值 + 三个待裁决必填字段各破坏一次（空串 stage / 非枚举 target /
   空数组 blocked_by）+ blockers 指向不存在的前置 + adapter_id 非 null，并分布在 6 条不同
   entry 上（G1 / G2 / G4-sppi / G6-sppi / G6-ecl / G14），从而同时把 6 组不同的 offset 走通。

用法（仓库根；本仓库 PATH 上的 `python` 指向坏掉的 venv，必须用 `.\.venv\Scripts\python.exe`）::

    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task49_g_cycle_migration_guards.py --list
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task49_g_cycle_migration_guards.py --check-anchors
    .\.venv\Scripts\python.exe backend/scripts/diagnose/mutate_task49_g_cycle_migration_guards.py --run all \
        --out .kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/evidence/task49-g-cycle-migration/mutation_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/scripts

from _mutation_kit import Mutation, run_cli  # noqa: E402

REPO = Path(__file__).resolve().parents[3]

# ── 被变异的对象 ───────────────────────────────────────────────────────────
SLICE = "backend/data/workpaper_sync_g_cycle_manifest_slice.json"
PLAN = "backend/data/workpaper_sync_g_cycle_deletion_plan.json"
G7_CONTRACT = "backend/data/workpaper_sync_contracts/g7.soe_subsidiary_disclosure.json"

FE = "audit-platform/frontend/src"
WP = f"{FE}/components/workpaper"
NOTICE_TS = f"{WP}/sync/workpaperEntrySyncNotice.ts"
NOTICE_VUE = f"{WP}/sync/GtEntrySyncCapabilityNotice.vue"
REGISTRY_TS = f"{WP}/htmlRendererRegistry.ts"
HOST_G1 = f"{WP}/GtG1TradingFinancialAssets.vue"
HOST_G14 = f"{WP}/GtG14CreditImpairmentLoss.vue"
HOST_G6ECL = f"{WP}/GtG6OtherBondInvestmentEcl.vue"
G1_LABELS = f"{WP}/composables/g1SheetLabels.ts"
G4_MAP = f"{WP}/composables/g4NoteSectionMap.ts"
G6_MAP = f"{WP}/composables/g6NoteSectionMap.ts"
G2_DETAIL = f"{WP}/composables/useG2Detail.ts"
G6_SPPI = f"{WP}/composables/useG6SppiFairValue.ts"
G6_LISTED = f"{WP}/g6-other-bond-investment-main/core/G6TabDisclosureListed.vue"

T49 = "test_task49_g_cycle_migration.py"
_SELF = f"{T49}::TestGuardSelfChecks"
_ADJ = f"{T49}::TestAdjudicationLegality"
_HTML = f"{T49}::TestHtmlCounterpartIsSourceBacked"
_P20 = f"{T49}::TestProperty20And21NotClaimedPassingForThisSlice"
_P28 = f"{T49}::TestProperty28DefinitionDriftFailClosed"
_TPL = f"{T49}::TestTemplateResolution"
_NOTE = f"{T49}::TestNoteSyncPathIntegrity"
_P69 = f"{T49}::TestProperty69EvidenceAndCounters"
_P70 = f"{T49}::TestProperty70NoCrossEntryReuse"
_AC14 = f"{T49}::TestAc14HonestModeVisibility"
_PARA = f"{T49}::TestParadigmCompliance"
_SRC = f"{T49}::TestSourceCodeStructure"

# ── 相对定位用的唯一 scope 锚（每条 entry 的 entry_id 行）───────────────────
S_G1 = '      "entry_id": "xlsx/gt-g1-trading-financial-assets",'
S_G2 = '      "entry_id": "xlsx/gt-g2-interest-receivable",'
S_G4S = '      "entry_id": "xlsx/gt-g4-bond-investment-sppi",'
S_G6S = '      "entry_id": "xlsx/gt-g6-other-bond-sppi",'
S_G6E = '      "entry_id": "xlsx/gt-g6-other-bond-investment-ecl",'
S_G14 = '      "entry_id": "xlsx/gt-g14-credit-impairment-loss",'

E_G1 = "xlsx/gt-g1-trading-financial-assets"
E_G2 = "xlsx/gt-g2-interest-receivable"
E_G4S = "xlsx/gt-g4-bond-investment-sppi"
E_G6S = "xlsx/gt-g6-other-bond-sppi"
E_G6E = "xlsx/gt-g6-other-bond-investment-ecl"
E_G14 = "xlsx/gt-g14-credit-impairment-loss"


# ═══════════════════════════════════════════════════════════════════════════
# 作用域自证回调（数据文件变异必带）
#
# 🔴 为什么每条数据变异都要带：共享件的四态判定只看「新增失败集合」，锚点若命中了同名的
# 文档说明 / 注释 / 另一个结构，判定会报 GREEN（守卫缺陷），而真相是脚本缺陷。回调在
# 变异写盘后立刻解析 JSON 并断言目标字段**真的**变成了期望值 —— 不成立即判 ANCHOR-MISS。
# ═══════════════════════════════════════════════════════════════════════════
def _entry_field(entry_id: str, *path):
    """slice/plan 里某 entry 的嵌套字段必须**恰好**等于期望值（path 末位是期望值）。"""
    expected = path[-1]
    keys = path[:-1]

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        rows = payload.get("independent_entries") or payload.get("entries") or []
        for entry in rows:
            if entry.get("entry_id") != entry_id:
                continue
            node = entry
            for key in keys:
                if not isinstance(node, dict) or key not in node:
                    return False
                node = node[key]
            return node == expected
        return False

    return check


def _top_path_is(expected, *keys: str):
    def check(data: bytes) -> bool:
        node = json.loads(data.decode("utf-8"))
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return False
            node = node[key]
        return node == expected

    return check


def _template_field(name: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for record in payload["authoritative_templates"]["files"]:
            if record["name"] == name:
                return record.get(key) == expected
        return False

    return check


def _bp_field(bp_id: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for bp in payload["blocking_preconditions"]:
            if bp.get("id") == bp_id:
                return bp.get(key) == expected
        return False

    return check


def _fd_group_is(mode: str, expected: list[str]):
    """FD-1 的 entries_by_mode 某一组必须恰好等于期望列表。"""

    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for diff in payload["g_cycle_form_differences"]["differences"]:
            if diff["id"] == "FD-1":
                return diff.get("entries_by_mode", {}).get(mode) == expected
        return False

    return check


def _plan_composable_field(path_suffix: str, key: str, expected):
    def check(data: bytes) -> bool:
        payload = json.loads(data.decode("utf-8"))
        for entry in payload["entries"]:
            for comp in entry.get("legacy_composables_to_delete", []):
                if comp["file"].endswith(path_suffix):
                    return comp.get(key) == expected
        return False

    return check


def _text_contains(needle: str, *, absent: bool = False):
    """源码类（.ts/.vue）变异的作用域自证：变异后的字节里必须（或必须不）含该串。

    🔴 源码侧没有 JSON 结构可解析，但仍然需要自证 —— 否则「锚点命中了注释里的同名行」
    这类脚本缺陷会被判成 GREEN。这里最少也要证明「改动确实落在我关心的那段文本上」。
    """

    def check(data: bytes) -> bool:
        text = data.decode("utf-8", errors="replace")
        return (needle not in text) if absent else (needle in text)

    return check


MUTATIONS: list[Mutation] = [
    # ═══════════════════════════════════════════════════════════════════════
    # ① AC 1.3 / 12.1 / 12.8 / 12.9：capability 裁决（按错法枚举，见模块 docstring 第 3 条）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M01", side="be", path=SLICE, kind="replace",
        scope=S_G1, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "bidirectional",',
        want=f"{_ADJ}::test_bidirectional_requires_all_five_identity_fields",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="把终态未定改成 bidirectional 而五个身份字段仍为 null 仍绿 ⇒ AC 12.1 的"
            "「缺 approved contract/bundle 不得进入 bidirectional 验收」与 SR-6 整条失守",
        scope_check=_entry_field(E_G1, "capability", "bidirectional"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M02", side="be", path=SLICE, kind="replace",
        scope=S_G2, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "single_onlyoffice",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(
            f"{_ADJ}::test_capability_matches_honest_capability",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="html_counterpart_verdict=exists 却裁 single_onlyoffice 仍绿 ⇒ AC 12.8 的"
            "「不得为满足数字伪造字段映射或制造对端」这条唯一合法判据（无 HTML 对端）失守",
        scope_check=_entry_field(E_G2, "capability", "single_onlyoffice"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M03", side="be", path=SLICE, kind="replace",
        scope=S_G4S, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "single_html",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
        ),
        why="裁 single_html（= 声称 OO 侧无业务价值，AC 12.9）而 honest_capability 仍为 null "
            "仍绿 ⇒ 对外字段与诚实裁决可以双口径（SR-4 失守）",
        scope_check=_entry_field(E_G4S, "capability", "single_html"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M04", side="be", path=SLICE, kind="replace",
        scope=S_G6E, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "unreachable",',
        want=f"{_ADJ}::test_capability_matches_honest_capability",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="把一个有宿主、有挂载点、有 HTML 通道的 entry 裁成 unreachable 仍绿 ⇒ AC 1.7 的"
            "「不可达旧桩 SHALL 删除」会被误用到活入口上（删掉在用的宿主）",
        scope_check=_entry_field(E_G6E, "capability", "unreachable"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M05", side="be", path=SLICE, kind="replace",
        scope=S_G14, offset=5,
        anchor='      "capability": null,',
        new='      "capability": "dual",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="自造能力态 dual 仍绿 ⇒ AC 1.3 明令禁止的「含糊 dual 布尔值」回来了，"
            "而 dual 既不是四个终态之一也不是待裁决态",
        scope_check=_entry_field(E_G14, "capability", "dual"),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M06", side="be", path=SLICE, kind="replace",
        scope=S_G6S, offset=6,
        anchor='      "capability_verdict_stage": "pipeline_entry_pending_definition_delivery",',
        new='      "capability_verdict_stage": "",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="待裁决态的 stage 变空串仍绿 ⇒ SR-3 右支的 non_empty_string 语义没人执行，"
            "「留空而不解释」就能冒充待裁决",
        scope_check=_entry_field(E_G6S, "capability_verdict_stage", ""),
        tags=("adjudication", "data", "sr3"),
    ),
    Mutation(
        id="M07", side="be", path=SLICE, kind="replace",
        scope=S_G1, offset=7,
        anchor='      "capability_target": "bidirectional",',
        new='      "capability_target": "maybe_later",',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="capability_target 填一个不在枚举内的值仍绿 ⇒ SR-3 右支的 "
            "member_of_capability_enum 失守，「不知道往哪走」就能算成待裁决"
            "（范式原话：那不是待裁决，是没调查）",
        scope_check=_entry_field(E_G1, "capability_target", "maybe_later"),
        tags=("adjudication", "data", "sr3"),
    ),
    Mutation(
        id="M08", side="be", path=SLICE, kind="insert",
        scope=S_G2, offset=14,
        anchor="      ],",
        new='      "capability_target_blocked_by": [],',
        want=f"{_ADJ}::test_capability_is_enum_or_explicitly_pending",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="blocked_by 变空数组仍绿 ⇒ SR-3 右支的 non_empty_list 失守（声称有阻塞却说不出"
            "是什么 = 自由文本豁免）。用「在数组闭合行后插入同名空数组」实现：JSON 重复键"
            "取最后一个，故 blocked_by 生效值为 []，且文件仍是合法 JSON —— 单行 replace 无法"
            "在不破坏 JSON 的前提下清空一个多元素数组",
        scope_check=_entry_field(E_G2, "capability_target_blocked_by", []),
        tags=("adjudication", "data", "sr3"),
    ),
    Mutation(
        id="M09", side="be", path=SLICE, kind="replace",
        scope=S_G1, offset=9,
        anchor='        "BP-1",',
        new='        "BP-404",',
        want=f"{_ADJ}::test_capability_blockers_reference_real_preconditions",
        why="阻断项指向一个不存在的前置仍绿 ⇒ blocked_by 退化成自由文本标签，"
            "「缺什么已逐条登记」这句话失去可核对性",
        scope_check=_entry_field(
            E_G1, "capability_target_blocked_by",
            ["BP-404", "BP-2", "BP-3", "BP-4", "BP-5", "BP-7"],
        ),
        tags=("adjudication", "data"),
    ),
    Mutation(
        id="M10", side="be", path=SLICE, kind="replace",
        scope=S_G2, offset=17,
        anchor='      "adapter_id": null,',
        new='      "adapter_id": "g2.interest_receivable",',
        want=f"{_P20}::test_no_slice_entry_has_a_registered_adapter",
        wants=(f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",),
        why="给待裁决 entry 挂一个不存在的 adapter 仍绿 ⇒ SR-5「裁 single/待裁决的 entry 不得"
            "挂 adapter/contract/bundle」失守，AC 1.4 的 UI 门也会据此显示「可双向回写」",
        scope_check=_entry_field(E_G2, "adapter_id", "g2.interest_receivable"),
        tags=("adjudication", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ② AC 12.4：HTML 对端逐 entry 回源码核验（含本次新修的四处判据）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M11", side="be", path=SLICE, kind="replace",
        scope=S_G6S, offset=30,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "none",',
        want=f"{_ADJ}::test_single_onlyoffice_requires_no_html_counterpart",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_ADJ}::test_adjudication_reason_is_not_circular",
        ),
        why="有 HTML 对端却裁 none 仍绿 ⇒ AC 12.8 的判据被反向滥用（伪造「无对端」来把 entry"
            "推成 single_onlyoffice），而 slice 里 17 条 source_ref 明明指着真实读写路径",
        scope_check=_entry_field(E_G6S, "html_counterpart_verdict", "none"),
        tags=("html", "data"),
    ),
    Mutation(
        id="M12", side="be", path=SLICE, kind="replace",
        scope=S_G14, offset=27,
        anchor='      "html_counterpart_verdict": "exists",',
        new='      "html_counterpart_verdict": "probably",',
        want=f"{_ADJ}::test_every_entry_has_a_binary_html_counterpart_verdict",
        why="第 3 步的二值结论被写成第三种值仍绿 ⇒ 范式 AP-1 的 allowed_verdict_values "
            "形同不存在，裁决可以停在「大概有吧」",
        scope_check=_entry_field(E_G14, "html_counterpart_verdict", "probably"),
        tags=("html", "data"),
    ),
    Mutation(
        id="M13", side="be", path=SLICE, kind="replace",
        scope=S_G4S, offset=36,
        anchor='        "payload_column_mode": "dual_write_remark_and_conclusion",',
        new='        "payload_column_mode": "conclusion_canonical_remark_mirror",',
        want=f"{_HTML}::test_payload_column_mode_is_declared_and_matches_the_write_site",
        wants=(
            f"{_P69}::test_form_difference_counts_are_recomputed",
        ),
        why="把 G4-sppi 的 payload 形态改回本次修正前的误判值（声称走 storage contract 的 "
            "buildCanonicalPayload，而 useG4SppiInventory.ts 全文没有该函数）仍绿 ⇒ "
            "「mode 声明必须回写入点源码核对」这条判据白写，per-entry contract 的 "
            "json_pointer 会指向 checklist_responses 里错的列",
        scope_check=_entry_field(
            E_G4S, "html_counterpart", "payload_column_mode",
            "conclusion_canonical_remark_mirror",
        ),
        tags=("html", "data", "fixed-this-round"),
    ),
    Mutation(
        id="M14", side="be", path=SLICE, kind="replace",
        scope=S_G2, offset=73,
        anchor='          "conclusion"',
        new='          "remark"',
        want=f"{_HTML}::test_payload_null_placeholder_is_declared_both_ways",
        why="把 G2 的空占位列从 conclusion 改成 remark 仍绿 ⇒ 空占位登记不再双向可核，"
            "而它正是 `_strip_null_placeholder_columns` 这把「放宽刀」的唯一约束"
            "（不核的话真双写退化成单写也不会有人发现）",
        scope_check=_entry_field(
            E_G2, "html_counterpart", "payload_null_placeholder_columns", ["remark"]
        ),
        tags=("html", "data", "fixed-this-round"),
    ),
    Mutation(
        id="M15", side="be", path=G2_DETAIL, kind="delete",
        scope="  function persistRows(rows: StoredDetailRow[]): void {", offset=3,
        anchor="      conclusion: null,",
        want=f"{_HTML}::test_payload_null_placeholder_is_declared_both_ways",
        why="源码侧把 `conclusion: null` 删掉（登记仍写 ['conclusion']）仍绿 ⇒ 双向锁只锁了"
            "「声称有的真有」一侧，漏报（源码已变而登记没跟上）照样通过",
        scope_check=_text_contains(
            "      item_id: STORAGE_KEY,\r\n      remark: JSON.stringify(rows),"
        ),
        tags=("html", "source", "fixed-this-round"),
    ),
    Mutation(
        id="M16", side="be", path=SLICE, kind="replace",
        anchor='          "remark_only": [',
        new='          "remark_only_typo": [',
        want=f"{_HTML}::test_payload_column_mode_is_declared_and_matches_the_write_site",
        why="FD-1 的 entries_by_mode 组名改一个字仍绿 ⇒ 本次把「散文里的数字」搬进可复核字段"
            "这件事没落地（原 what 散文与机器计数三处不符正是这么来的）",
        scope_check=_fd_group_is("remark_only", None),
        tags=("html", "data", "fixed-this-round"),
    ),
    Mutation(
        id="M17", side="be", path=SLICE, kind="replace",
        anchor='            "xlsx/gt-g2-interest-receivable",',
        new='            "xlsx/gt-g4-bond-investment-main",',
        want=f"{_HTML}::test_payload_column_mode_is_declared_and_matches_the_write_site",
        why="把 entries_by_mode 里的 remark_only 组换成一条实际走 storage contract 的 entry "
            "仍绿 ⇒ 分组登记与逐 entry 现算脱钩，FD-1 又变回不受判据管的散文",
        scope_check=_fd_group_is(
            "remark_only",
            [
                "xlsx/gt-g4-bond-investment-main",
                "xlsx/gt-g8-other-equity-instruments",
                "xlsx/gt-g9-other-noncurrent-financial",
                "xlsx/gt-g10-trading-financial-liabilities",
                "xlsx/gt-g11-investment-income",
                "xlsx/gt-g12-net-hedge-gains",
                "xlsx/gt-g13-fair-value-changes",
                "xlsx/gt-g14-credit-impairment-loss",
            ],
        ),
        tags=("html", "data", "fixed-this-round"),
    ),
    Mutation(
        id="M18", side="be", path=SLICE, kind="replace",
        scope=S_G6E, offset=41,
        anchor='        "http_client_binding": "http",',
        new='        "http_client_binding": "api",',
        want=f"{_HTML}::test_persistence_composable_really_calls_both_endpoints_with_its_own_client",
        wants=(f"{_P69}::test_form_difference_counts_are_recomputed",),
        why="把 http 族 entry 的客户端绑定谎报成 api 仍绿 ⇒ FD-2 的「按登记名拼探针」退化成"
            "二选一并集（另一族还在，探针恒真），F 循环那套写死 `api.get(` 的探针会在 4 条 "
            "entry 上静默失配",
        scope_check=_entry_field(E_G6E, "html_counterpart", "http_client_binding", "api"),
        tags=("html", "data"),
    ),
    Mutation(
        id="M19", side="be", path=SLICE, kind="replace",
        anchor='        "html_persistence_composable": "audit-platform/frontend/src/components/workpaper/composables/useG2IntRecFormData.ts#L17(GET)/#L53(PUT)",',
        new='        "html_persistence_composable": "audit-platform/frontend/src/components/workpaper/composables/useG2Nonexistent.ts#L17(GET)/#L53(PUT)",',
        want=f"{_HTML}::test_source_refs_point_at_real_paths",
        wants=(
            f"{_HTML}::test_persistence_composable_really_calls_both_endpoints_with_its_own_client",
        ),
        why="source_ref 指向不存在的文件仍绿 ⇒「有 HTML 对端」这个结论不再可在磁盘上复核，"
            "整条 AC 12.4 的证据链变成自由文本",
        scope_check=_entry_field(
            E_G2, "html_counterpart", "html_persistence_composable",
            "audit-platform/frontend/src/components/workpaper/composables/"
            "useG2Nonexistent.ts#L17(GET)/#L53(PUT)",
        ),
        tags=("html", "data"),
    ),
    Mutation(
        id="M20", side="be", path=SLICE, kind="replace",
        scope=S_G2, offset=32,
        anchor='        "endpoint_read": "GET /api/workpapers/{wp_id}/checklist-responses",',
        new='        "endpoint_read": "GET /api/workpapers/{wp_id}/g2-responses",',
        want=f"{_HTML}::test_html_store_endpoints_exist_in_the_router",
        why="读端点谎报成一个路由里没有的路径仍绿 ⇒ HTML 侧持久化通道的存在性无人核对",
        scope_check=_entry_field(
            E_G2, "html_counterpart", "endpoint_read",
            "GET /api/workpapers/{wp_id}/g2-responses",
        ),
        tags=("html", "data"),
    ),
    Mutation(
        id="M21", side="be", path=SLICE, kind="replace",
        scope=S_G1, offset=70,
        anchor='          "identity_text": "类别"',
        new='          "identity_text": "类 别"',
        want=f"{_HTML}::test_primary_table_identity_cell_matches_the_authoritative_template",
        why="身份列表头与权威模板单元格差一个空格仍绿 ⇒ 第三边（openpyxl 真读 sheet!cell）"
            "没在比对，Property 28 的 17 组三元组分母是假的",
        scope_check=_entry_field(
            E_G1, "html_counterpart", "primary_table", "identity_text", "类 别"
        ),
        tags=("html", "data", "property28"),
    ),
    Mutation(
        id="M22", side="be", path=SLICE, kind="replace",
        scope=S_G6E, offset=49,
        anchor='        "row_identity_generator_form": "globalThis.crypto?.randomUUID?.() ?? `g6-stage-${Date.now()}-${Math.random().toString(36).slice(2)}`",',
        new='        "row_identity_generator_form": "crypto.randomUUID?.() ?? `g6-stage-${Date.now()}-${Math.random().toString(36).slice(2)}`",',
        want=f"{_HTML}::test_row_identity_key_and_generator_are_source_backed",
        why="把 G6-ecl 的生成器形态改回本次修正前的不精确转写（漏 `globalThis.` 与 `crypto` "
            "后的可选链问号）仍绿 ⇒「声明的形态必须逐字回源」没落地，slice 的转写可以随便写",
        scope_check=_entry_field(
            E_G6E, "html_counterpart", "row_identity_generator_form",
            "crypto.randomUUID?.() ?? `g6-stage-${Date.now()}-"
            "${Math.random().toString(36).slice(2)}`",
        ),
        tags=("html", "data", "fixed-this-round"),
    ),
    Mutation(
        id="M23", side="be", path=SLICE, kind="replace",
        anchor='        "row_identity_is_positional": true,',
        new='        "row_identity_is_positional": false,',
        want=f"{_HTML}::test_positional_row_identity_defects_are_real_and_exhaustive",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="把 G6-sppi 唯一那条真实位置化缺陷谎报成 false 仍绿 ⇒ BP-7 可以被悄悄抹掉，"
            "而它是本 slice 唯一的 stable-field-key 可保持性缺陷",
        scope_check=_entry_field(E_G6S, "html_counterpart", "row_identity_is_positional", False),
        tags=("html", "data"),
    ),
    Mutation(
        id="M24", side="be", path=SLICE, kind="replace",
        scope=S_G14, offset=48,
        anchor='        "row_identity_is_positional": false,',
        new='        "row_identity_is_positional": true,',
        want=f"{_HTML}::test_positional_row_identity_defects_are_real_and_exhaustive",
        why="给一条实际不位置化的 entry 虚报缺陷仍绿 ⇒ 双向锁只有「声称有的真有」一侧，"
            "拿不存在的缺陷凑 BP 也能过（虚报与漏报同样是缺陷）",
        scope_check=_entry_field(E_G14, "html_counterpart", "row_identity_is_positional", True),
        tags=("html", "data"),
    ),
    Mutation(
        id="M25", side="be", path=G6_SPPI, kind="replace",
        anchor="  const base = emptyRow(String(raw.id || `fv-${Date.now()}-${seq}`), seq, raw.investProject || '')",
        new="  const base = emptyRow(String(raw.id || `fv-${Date.now()}`), seq, raw.investProject || '')",
        want=f"{_HTML}::test_positional_row_identity_defects_are_real_and_exhaustive",
        why="把 G6-sppi 的下标派生表达式修好（登记仍写 true）仍绿 ⇒ 「修复后必须回来改 slice」"
            "这条反向锁不存在，BP-7 会永久挂着一个已经不存在的缺陷",
        scope_check=_text_contains("`fv-${Date.now()}-${seq}`", absent=True),
        tags=("html", "source"),
    ),
    Mutation(
        id="M26", side="be", path=SLICE, kind="replace",
        anchor='    "duplicated_item_id_literals_in_g_cycle": 80,',
        new='    "duplicated_item_id_literals_in_g_cycle": 12,',
        want=f"{_HTML}::test_duplicated_item_id_literal_scale_is_recomputable",
        why="BP-10 的规模数字改小仍绿 ⇒ 「80 个 item_id 多处重复」这条规模结论不是现扫复算的，"
            "而是自由文本；收敛进度也就无从判断",
        scope_check=_top_path_is(
            12, "honest_adjudication_summary", "duplicated_item_id_literals_in_g_cycle"
        ),
        tags=("html", "data", "bp10"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ③ Property 28：immutable definition 漂移 fail closed
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M27", side="be", path=SLICE, kind="replace",
        anchor='        "sha256": "eba510b3b7cef68a0e3ea1a16eaa1262468bee11fccbee47a39ff513c33fba73",',
        new='        "sha256": "fba510b3b7cef68a0e3ea1a16eaa1262468bee11fccbee47a39ff513c33fba73",',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="G1 权威模板 sha256 改一位仍绿 ⇒ digest 没有被 hashlib 现算比对，"
            "Property 28 的 15 个模板分母是假的",
        scope_check=_template_field(
            "G1 交易性金融资产.xlsx", "sha256",
            "fba510b3b7cef68a0e3ea1a16eaa1262468bee11fccbee47a39ff513c33fba73",
        ),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M28", side="be", path=SLICE, kind="replace",
        anchor='        "size": 60094,',
        new='        "size": 60095,',
        want=f"{_P28}::test_authoritative_templates_digests_recompute",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="G14 权威模板 size 差一字节仍绿 ⇒ size 只是抄下来的数字，没有 stat() 比对",
        scope_check=_template_field("G14 信用减值损失.xlsx", "size", 60095),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M29", side="be", path=SLICE, kind="replace",
        anchor='        "normalized_structure_hash": "87035257394c948e26fd84be009345a0d905bbac2487b52fcf5de7d3ca3f8941"',
        new='        "normalized_structure_hash": "87035257394c948e26fd84be009345a0d905bbac2487b52fcf5de7d3ca3f8942"',
        want=f"{_P28}::test_normalized_structure_hash_recomputes",
        why="结构 hash 改一位仍绿 ⇒ 没有用生产实现 excel_instrumentation.normalized_structure_hash "
            "现算，模板结构漂移（加删 sheet/行/列）不会 fail closed",
        scope_check=_template_field(
            "G1 交易性金融资产.xlsx", "normalized_structure_hash",
            "87035257394c948e26fd84be009345a0d905bbac2487b52fcf5de7d3ca3f8942",
        ),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M30", side="be", path=SLICE, kind="replace",
        anchor='      "template_ref": "G/G1 交易性金融资产.xlsx",',
        new='      "template_ref": null,',
        want=f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",
        wants=(f"{_HTML}::test_template_ref_resolves_through_the_runtime_index",),
        why="template_ref 置 null 仍绿 ⇒ 判据写成了 `if ref:` 形态（Task 46 首轮实测的 "
            "fail-open：置 null 后 36 例全绿），整个模板真源链条可被一键跳过",
        scope_check=_entry_field(E_G1, "template_ref", None),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M31", side="be", path=SLICE, kind="replace",
        scope=S_G4S, offset=22,
        anchor='      "template_ref": "G/G4 债权投资.xlsx",',
        new='      "template_ref": "G/G4 债权投资底稿.xlsx",',
        want=f"{_HTML}::test_template_ref_resolves_through_the_runtime_index",
        wants=(f"{_P28}::test_every_entry_template_ref_is_registered_with_digest",),
        why="template_ref 指向一本磁盘与 _index.json 里都不存在的册子仍绿 ⇒ D4 "
            "`D4收入底稿.xlsx` / F2 `F2存货.xlsx` 那种「磁盘有、索引无、finder 永不返回」"
            "的同型陷阱在 G 循环不会被检出",
        scope_check=_entry_field(E_G4S, "template_ref", "G/G4 债权投资底稿.xlsx"),
        tags=("property28", "data"),
    ),
    Mutation(
        id="M32", side="be", path=G1_LABELS, kind="replace",
        anchor="  G1A: '交易性金融资产实质性程序表G1A',",
        new="  G1A: '交易性金融资产实质性程序表G1A ',",
        want=f"{_P28}::test_bp5_g1_fallback_sheet_labels_point_at_nonexistent_tabs",
        why="把 BP-5 的 5 条错标签之一修对（补上权威 tab 名尾部那个空格）仍绿 ⇒ BP-5 的双向锁"
            "只锁了「缺陷存在」，修好后不会逼作者回来改 status，登记会永久停在 "
            "REGISTERED_NOT_FIXED",
        scope_check=_text_contains("G1A: '交易性金融资产实质性程序表G1A ',"),
        tags=("property28", "source", "bp5"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ④ Requirement 9.1：附注同步链路（不把虚构表或 metadata sheet 推进附注）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M33", side="be", path=G4_MAP, kind="delete",
        anchor="  '期末重要的债权投资（续：上年年末余额）': '同上（续表）',",
        want=f"{_NOTE}::test_g4_not_synced_tables_are_declared_instead_of_fabricated",
        why="删掉 G4_NOT_SYNCED_TABLES 的续表登记仍绿 ⇒「宁缺勿造」的正向证据可以缩水而无人"
            "发现（本轮修判据时正是这条被 `{20,}` 长度阈值筛掉，从而误报「登记缩水」）",
        scope_check=_text_contains("同上（续表）", absent=True),
        tags=("note", "source", "fixed-this-round"),
    ),
    Mutation(
        id="M34", side="be", path=G4_MAP, kind="replace",
        anchor="  '期末重要的债权投资（续：上年年末余额）': '同上（续表）',",
        new="  '期末重要的债权投资（续：上年年末余额）': '暂不处理',",
        want=f"{_NOTE}::test_g4_not_synced_tables_are_declared_instead_of_fabricated",
        why="把续表理由换成「暂不处理」这类自由文本豁免仍绿 ⇒ 不推理由不再需要能追溯到本表的"
            "实质列差异说明，登记退化成免责声明",
        scope_check=_text_contains("'暂不处理',"),
        tags=("note", "source", "fixed-this-round"),
    ),
    Mutation(
        id="M35", side="be", path=G6_MAP, kind="replace",
        anchor="  balance: '其他债权投资',",
        new="  balance: '其他债权投资成本项目',",
        want=f"{_NOTE}::test_g6_listed_subtables_come_from_the_note_section_map",
        why="上市侧子表名混进自造小节标记（成本项目）仍绿 ⇒ G6 自造形态的回归锁失效，"
            "接附注同步会把虚构表推进附注",
        scope_check=_text_contains("balance: '其他债权投资成本项目',"),
        tags=("note", "source"),
    ),
    Mutation(
        id="M36", side="be", path=G6_LISTED, kind="insert",
        anchor="import { G6_LISTED_SUBTABLE, G6_NOTE_SECTION } from '../../composables/g6NoteSectionMap'",
        new="function generateRows(n: number) { return Array.from({ length: n }, (_, i) => ({ item: `成本项目${i + 1}` })) }",
        want=f"{_NOTE}::test_g6_forgery_markers_exist_only_in_comments",
        why="把自造行生成器加回**可执行代码**（不是注释）仍绿 ⇒ 判据只在注释层面检查，"
            "`generateRows` + 「成本项目N」这套 137 行虚构披露可以原地复活",
        scope_check=_text_contains("function generateRows(n: number)"),
        tags=("note", "source"),
    ),
    Mutation(
        id="M37", side="be", path=SLICE, kind="replace",
        anchor='      "verdict": "already_rewritten_by_another_spec_verified_here",',
        new='      "verdict": "excluded_from_note_sync",',
        want=f"{_NOTE}::test_g6_forgery_markers_exist_only_in_comments",
        why="把 G6 自造件的处置裁决改成「排除出附注同步」仍绿 ⇒ 任务正文那个二选一"
            "（重写 / 排除+登记）与实测的第三种处置（核验+回归锁）之间可以随意切换而无据",
        scope_check=_top_path_is(
            "excluded_from_note_sync",
            "note_sync_path_audit", "g6_listed_disclosure_forgery", "verdict",
        ),
        tags=("note", "data"),
    ),
    Mutation(
        id="M38", side="be", path=G6_MAP, kind="replace",
        anchor="export const G6_DISCLOSURE_SHEET_NAME = {",
        new="export const G6_DISCLOSURE_SHEET_NAME = { listed: '底稿目录', soe: '底稿目录',",
        want=f"{_NOTE}::test_no_metadata_sheet_reaches_the_note_mapping",
        why="把披露 sheet 名改成 metadata sheet「底稿目录」仍绿 ⇒ 任务正文「不把 metadata "
            "sheet 同步到附注」这条硬约束无人把守（重复键取最后一个，故原声明仍在但生效值被"
            "顶掉；文件仍是合法 TS）",
        scope_check=_text_contains("listed: '底稿目录', soe: '底稿目录',"),
        tags=("note", "source"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑤ Property 69：计数与 evidence（含 selection_rule 与 SR-9）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M39", side="be", path=SLICE, kind="replace",
        anchor='    "independent_entry_count": 17,',
        new='    "independent_entry_count": 16,',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        wants=(
            f"{_P69}::test_summary_counters_are_recomputed_from_entries",
            f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        ),
        why="slice_scope 的 entry 计数与 selection_rule 现算不符仍绿 ⇒ SR-1 失守，"
            "「17 条」这个分母可以手填",
        scope_check=_top_path_is(16, "slice_scope", "independent_entry_count"),
        tags=("counters", "data"),
    ),
    Mutation(
        id="M40", side="be", path=SLICE, kind="replace",
        anchor='    "g_prefixed_independent_total": 20,',
        new='    "g_prefixed_independent_total": 21,',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        why="selection_rule 的中间量（G 前缀 independent 总数）说谎仍绿 ⇒ "
            "「20 - 3 = 17」这条推导链不是从 source manifest 现算的，排除边界无从复核",
        scope_check=_top_path_is(21, "slice_scope", "g_prefixed_independent_total"),
        tags=("counters", "data"),
    ),
    Mutation(
        id="M41", side="be", path=SLICE, kind="replace",
        anchor='    "excluded_g7_entry_count": 3,',
        new='    "excluded_g7_entry_count": 2,',
        want=f"{_P69}::test_slice_scope_is_recomputable_from_the_manifest",
        why="G7 排除条数说谎仍绿 ⇒ 任务正文「除 G7 外」这条边界不可复核，"
            "少算一条就意味着有一个 G7 entry 被悄悄算进本 slice",
        scope_check=_top_path_is(2, "slice_scope", "excluded_g7_entry_count"),
        tags=("counters", "data"),
    ),
    Mutation(
        id="M42", side="be", path=SLICE, kind="replace",
        anchor='      "unadjudicated": 17,',
        new='      "unadjudicated": 0,',
        want=f"{_PARA}::test_the_slice_passes_the_paradigm_nominated_validator",
        wants=(f"{_P69}::test_summary_counters_are_recomputed_from_entries",),
        why="把待裁决计数改成 0（同时 17 条 capability 仍为 null）仍绿 ⇒ 范式新增的 SR-9 没在"
            "管计数，SR-3 右支就成了后门：「把全部 entry 记成待裁决、同时报 unadjudicated=0」"
            "能通过校验",
        scope_check=_top_path_is(
            0, "honest_adjudication_summary", "slice_counters", "unadjudicated"
        ),
        tags=("counters", "data", "sr9"),
    ),
    Mutation(
        id="M43", side="be", path=SLICE, kind="replace",
        anchor='    "payload_null_placeholder_entries": 1,',
        new='    "payload_null_placeholder_entries": 0,',
        want=f"{_HTML}::test_payload_null_placeholder_is_declared_both_ways",
        why="空占位 entry 计数说谎仍绿 ⇒ 本轮新加的登记只有逐 entry 一侧，摘要侧可以对不上",
        scope_check=_top_path_is(
            0, "honest_adjudication_summary", "payload_null_placeholder_entries"
        ),
        tags=("counters", "data", "fixed-this-round"),
    ),
    Mutation(
        id="M44", side="be", path=SLICE, kind="replace",
        anchor='    "templates_serving_multiple_entries": 2,',
        new='    "templates_serving_multiple_entries": 0,',
        want=f"{_P28}::test_template_owner_mapping_covers_every_entry_exactly_once",
        why="把「一册服务多 entry」的模板数记成 0 仍绿 ⇒ FD-3 的 1:N 归属结论不可复核，"
            "而 BP-8（G4/G6 各一册服务 3 条 entry 的身份唯一性）正建立在它上面",
        scope_check=_top_path_is(
            0, "honest_adjudication_summary", "templates_serving_multiple_entries"
        ),
        tags=("counters", "data"),
    ),
    Mutation(
        id="M45", side="be", path=SLICE, kind="replace",
        scope='      "id": "BP-5",', offset=9,
        anchor='      "status": "REGISTERED_NOT_FIXED",',
        new='      "status": "FIXED",',
        want=f"{_P28}::test_bp5_g1_fallback_sheet_labels_point_at_nonexistent_tabs",
        why="把 BP-5 的 status 谎报成已修（G1 兜底标签表其实一条没改）仍绿 ⇒ 阻断项状态与"
            "源码实况脱钩，「只登记不修」会变成「登记了就算修了」",
        scope_check=_bp_field("BP-5", "status", "FIXED"),
        tags=("counters", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑥ Property 70 / AC 1.7：deletion plan 与不可达旧桩
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M46", side="be", path=PLAN, kind="replace",
        anchor='    "inbound_reference_count": 0,',
        new='    "inbound_reference_count": 1,',
        want=f"{_P70}::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges",
        why="旧桩入边数谎报成 1 仍绿 ⇒ AC 1.7 的「不可达」这个前提不是实扫出来的，"
            "删除决策就没有依据",
        scope_check=_top_path_is(1, "unreachable_stub_to_delete", "inbound_reference_count"),
        tags=("deletion", "data", "ac17"),
    ),
    Mutation(
        id="M47", side="be", path=PLAN, kind="replace",
        anchor='      "is_an_inbound_edge_to_the_stub": false,',
        new='      "is_an_inbound_edge_to_the_stub": true,',
        want=f"{_P70}::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges",
        why="把「registry 的同名别名不是入边」这个结论翻转仍绿 ⇒ 本轮那条实读结论"
            "（别名指向 GtG6OtherBondInvestmentEcl.vue，旧桩零入边）没有被锁住，"
            "下一个人还会按符号名判一次并再次误报「旧桩被救活」",
        scope_check=_top_path_is(
            True, "unreachable_stub_to_delete", "registry_homonymous_alias",
            "is_an_inbound_edge_to_the_stub",
        ),
        tags=("deletion", "data", "ac17"),
    ),
    Mutation(
        id="M48", side="be", path=REGISTRY_TS, kind="replace",
        anchor="const GtG6OtherBondEcl = defineAsyncComponent(() => import('./GtG6OtherBondInvestmentEcl.vue'))",
        new="const GtG6OtherBondEcl = defineAsyncComponent(() => import('./GtG6OtherBondEcl.vue'))",
        want=f"{_P70}::test_unreachable_stub_is_registered_and_still_has_zero_inbound_edges",
        why="把 registry 的别名真的接到旧桩文件上（= 救活旧桩，这才是真入边）仍绿 ⇒ "
            "AC 1.7 的裁决对象可以在无人察觉时变成活组件；这条同时反证「按模块边判」比"
            "「按符号名判」强：符号名两侧都在，只有 import 路径变了",
        scope_check=_text_contains("import('./GtG6OtherBondEcl.vue')"),
        tags=("deletion", "source", "ac17"),
    ),
    Mutation(
        id="M49", side="be", path=PLAN, kind="replace",
        anchor='          "wraps_shared_base": true,',
        new='          "wraps_shared_base": false,',
        want=f"{_P70}::test_wraps_shared_base_flag_is_source_backed_both_ways",
        wants=(f"{_P70}::test_deletion_plan_declares_no_pilot_and_preserves_shared_base",),
        why="把唯一那条包了共享基座的 composable（useG2DualMode）谎报成没包仍绿 ⇒ "
            "「删共享基座是安全的」这个错误结论会通过，而 17 个 entry 里恰有 1 条依赖它",
        scope_check=_plan_composable_field("useG2DualMode.ts", "wraps_shared_base", False),
        tags=("deletion", "data"),
    ),
    Mutation(
        id="M50", side="be", path=PLAN, kind="replace",
        anchor='    "g_cycle_does_not_consume_it": false,',
        new='    "g_cycle_does_not_consume_it": true,',
        want=f"{_P70}::test_deletion_plan_declares_no_pilot_and_preserves_shared_base",
        why="声称 G 循环不消费共享基座仍绿 ⇒ 与 F 循环形态不同这件事没被登记住，"
            "删除清册会把还有消费方的基座算成可删",
        scope_check=_top_path_is(True, "shared_base_preserved", "g_cycle_does_not_consume_it"),
        tags=("deletion", "data"),
    ),
    Mutation(
        id="M51", side="be", path=PLAN, kind="replace",
        anchor='      "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue"',
        new='      "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue"',
        want=f"{_P70}::test_cross_cycle_shared_composable_is_registered_with_its_consumers",
        why="把 useG1DualMode 的跨循环消费方从 E1 宿主换成一个并不 import 它的宿主仍绿 ⇒ "
            "BP-9（E 循环延后删除登记能否解除）的事实基础不可复核",
        scope_check=_top_path_is(
            [
                "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue",
                "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue",
            ],
            "cross_cycle_shared_composable", "consumers",
        ),
        tags=("deletion", "data", "bp9"),
    ),
    Mutation(
        id="M52", side="be", path=PLAN, kind="replace",
        anchor='      "can_it_be_released_now": false,',
        new='      "can_it_be_released_now": true,',
        want=f"{_P70}::test_cross_cycle_shared_composable_is_registered_with_its_consumers",
        why="声称 E 循环的延后删除登记「现在就能解除」仍绿 ⇒ Task 49 不含 step 9（宿主改线）"
            "这一事实被绕过，E 循环会据此删掉仍在用的 composable",
        scope_check=_top_path_is(
            True, "cross_cycle_shared_composable", "e_cycle_deferred_registration",
            "can_it_be_released_now",
        ),
        tags=("deletion", "data", "bp9"),
    ),
    Mutation(
        id="M53", side="be", path=SLICE, kind="replace",
        anchor='      "legacy_dual_mode_composable": "useG1DualMode",',
        new='      "legacy_dual_mode_composable": "useG2DualMode",',
        want=f"{_SRC}::test_hosts_exist_and_still_import_their_legacy_composable",
        wants=(f"{_P70}::test_deletion_plan_matches_slice",),
        why="把 G1 的 legacy composable 谎报成 G2 的仍绿 ⇒ 「逐 entry 独立、宿主真 import 它」"
            "这条现状锁失效，删除清册会删错文件",
        scope_check=_entry_field(E_G1, "legacy_dual_mode_composable", "useG2DualMode"),
        tags=("deletion", "data"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑦ AC 1.4：裁决自带的 UI 义务（宿主挂载点三种破坏形态）
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M54", side="be", path=HOST_G1, kind="delete",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g1-trading-financial-assets" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="删掉宿主的通知挂载点仍绿 ⇒ AC 1.4「显示可操作原因」在该宿主上无人把守，"
            "界面会退回「只有一个不可兑现的模式切换按钮」",
        scope_check=_text_contains(
            '<GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g1-trading-financial-assets" />',
            absent=True,
        ),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M55", side="be", path=HOST_G14, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g14-credit-impairment-loss" />',
        new='        <!-- <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g14-credit-impairment-loss" /> -->',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="把挂载点整行注释掉仍绿 ⇒ 判据没先 stripComments，注释可以充当证据"
            "（平台已登记的假绿形态）",
        scope_check=_text_contains(
            '<!-- <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g14-credit-impairment-loss" /> -->'
        ),
        tags=("ac14", "source", "stripcomments"),
    ),
    Mutation(
        id="M56", side="be", path=HOST_G6ECL, kind="replace",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g6-other-bond-investment-ecl" />',
        new='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g6-other-bond-main" />',
        want=f"{_AC14}::test_every_pending_entry_host_mounts_the_notice",
        why="挂载点绑成另一条 entry 的 id 仍绿 ⇒ 通知内容会显示别的 entry 的阻断原因，"
            "而 Vue 传错 prop 值是静默失效（四层静态检查都查不出）",
        scope_check=_text_contains(
            '<GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g6-other-bond-main" />'
        ),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M57", side="be", path=HOST_G1, kind="replace",
        anchor="""      <div v-if="currentSheet !== '底稿目录'" class="g1-toolbar">""",
        new="""      <div v-if="currentSheet !== '底稿目录'" class="g1-mode-toolbar">""",
        want=f"{_AC14}::test_notice_mount_sits_inside_the_declared_mode_toolbar",
        why="宿主工具栏类名漂移而 slice 的 ui_toolbar_gate 没跟上仍绿 ⇒ 「通知挂在模式工具栏"
            "内（而不是藏在某个折叠区）」这条判据不会因宿主结构变化而打红",
        scope_check=_text_contains('class="g1-mode-toolbar"'),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M58", side="be", path=HOST_G14, kind="insert",
        anchor='        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g14-credit-impairment-loss" />',
        new='        <el-tag size="small" type="success">可双向回写</el-tag>',
        want=f"{_AC14}::test_hosts_do_not_claim_bidirectional_writeback",
        why="宿主直接打出「可双向回写」仍绿 ⇒ AC 1.4 前半句（未注册 adapter 禁止显示可双向"
            "回写）无人把守",
        scope_check=_text_contains('<el-tag size="small" type="success">可双向回写</el-tag>'),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M59", side="be", path=NOTICE_TS, kind="replace",
        anchor="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = []",
        new="export const SYNC_ADAPTER_REGISTERED_ENTRY_IDS: readonly string[] = ['xlsx/gt-g1-trading-financial-assets']",
        want=f"{_AC14}::test_registered_entry_ids_agree_with_the_slice",
        why="前端把没有 adapter 的 entry 登记成已注册仍绿 ⇒ 界面会以「已双向」呈现，"
            "正是 AC 1.4 前半句禁止的事；而这份 TS 是 AC 1.4 的单一真源",
        scope_check=_text_contains("['xlsx/gt-g1-trading-financial-assets']"),
        tags=("ac14", "source"),
    ),
    Mutation(
        id="M60", side="be", path=NOTICE_VUE, kind="replace",
        anchor='      <span class="entry-sync-notice__summary">{{ notice.summary }}</span>',
        new='      <span class="entry-sync-notice__summary">详情</span>',
        want=f"{_AC14}::test_notice_component_renders_summary_and_binds_entry_id",
        why="常显摘要从模板里消失（原因只剩 hover 才出现的 tooltip）仍绿 ⇒ AC 1.4 的"
            "「显示可操作原因」退化成默认看不见（EP tooltip 内容是 teleport 出去的）",
        scope_check=_text_contains('__summary">详情</span>'),
        tags=("ac14", "source"),
    ),
    # ═══════════════════════════════════════════════════════════════════════
    # ⑧ Property 20：本循环唯一那份生产契约上的正向核验
    # ═══════════════════════════════════════════════════════════════════════
    Mutation(
        id="M61", side="be", path=G7_CONTRACT, kind="replace",
        anchor='  "review_status": "reviewed",',
        new='  "review_status": "draft",',
        want=f"{_P20}::test_g7_pilot_contract_has_no_generated_col_placeholder",
        why="把本循环唯一那份生产契约的审核态改成 draft 仍绿 ⇒ Property 20 的正向核验读错了"
            "字段路径（本轮的失败正是这么来的：判据读 review.review_status 恒得 None，"
            "而真值在顶层）—— 读对了才会因审核态变化而打红",
        scope_check=_top_path_is("draft", "review_status"),
        tags=("property20", "data"),
    ),
]

GUARD_FILES = {
    T49: "Task 49 新建（AC 1.3/12.1/12.8/12.9 裁决合法性、HTML 对端四形态三边锁、"
         "payload 空占位双向锁、行身份三族 + 位置化缺陷双向锁、模板 digest/structure "
         "hash/sheet!cell 现算、BP-5 G1 sheet 兜底锁、附注同步链路（G6 自造件回归锁 + "
         "G4 宁缺勿造登记 + metadata sheet 禁入）、selection_rule 与 SR-9 计数、"
         "deletion plan 与 AC 1.7 不可达旧桩零入边、AC 1.4 的 UI 义务、范式 slice_schema）",
}

if __name__ == "__main__":
    raise SystemExit(
        run_cli(
            mutations=MUTATIONS,
            guard_files=GUARD_FILES,
            repo=REPO,
            description="Task 49 G 循环（除 G7）Excel 独立 entry 迁移守卫变异检验",
            backend_args=[
                "backend/tests/workpaper_sync/test_task49_g_cycle_migration.py",
                "-q",
                "--tb=no",
                "-rfE",
                "-p",
                "no:randomly",
            ],
            baseline_backend_passed=96,
        )
    )
