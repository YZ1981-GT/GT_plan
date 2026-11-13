# -*- coding: utf-8 -*-
"""Task 57 冻结 slice 的漂移台账：数据 + 判定机制（被 `test_task57_abcs_and_shared_migration.py` 使用）。

═══ 为什么有这张台账 ═══

`workpaper_sync_abcs_cycle_manifest_slice.json` 自己写着 `frozen_at = Task 57（2026-08-31）`，
是**那一刻**的域快照。Task 57 的判据原先一律写成「快照登记值 == 现算值」，源码此后每一次合法
演进都让它打红（2026-11-04 实测 36 条）：宿主改走共享同步宿主、契约目录从 4 份长到 91 份、
registry 条目挪行、AC-14 notice 被本 spec task 3.5 接到 185 个宿主上……假红掩盖的恰恰是这些判据
本该守住的东西 —— 与同文件 `MIN_TOTAL_WORKBOOKS`、AC 1.6 的 `global_parent_duplicate_count`
当初从等式改成下界时的理由逐字相同。

⇒ 判据改成**棘轮**：没漂移时照旧逐值比较；漂移必须在本台账点名，连现算值一起钉住。四种后果
都会打红：① 出现没登记的新漂移；② 已登记项的现算值又变了（按方向判）；③ 漂移消失（快照与现算
重新相等）⇒ 条目必须删掉；④ 条目登记了却在所属测试类整类跑完后从未被触达（死条目）。

🔴 台账**不是**豁免名单：每一项都带 `observed`（可伪证的现算值）与 `why`（机理）。只写理由不写
现算值的条目在构造时就拒收 —— 那种写法加一行就能变绿，等于后门。

方向（`direction`）：
* ``pinned``  现算必须与登记值相等（分类结论 / 布尔 / 冻结口径下的计数）；
* ``grow`` / ``shrink``  数值或规模只许增 / 只许减（平台合法增长的量、迁移中只许收敛的量）；
* ``superset`` / ``subset``  集合只许变大 / 只许变小（按元素比，不只比个数）。
"""

from __future__ import annotations

from typing import Any

_DIRECTIONS = frozenset({"pinned", "grow", "shrink", "superset", "subset"})


def _keys(prefix: str, *suffixes: str) -> frozenset[str]:
    """组成员：公共前缀 + **逐个点名**的后缀。

    🔴 组不许写成「前缀匹配」：前缀会连带收走此后新出现的同前缀键（没调查过的新漂移静默进组），
    那就把棘轮变回了豁免名单。
    """
    assert suffixes and len(set(suffixes)) == len(suffixes), suffixes
    return frozenset(prefix + suffix for suffix in suffixes)


class _Drift:
    """一条已登记的快照漂移。

    ``claim``：理由里能机械核对的那句话的名字（如「宿主已把 OO 挂载点换成共享同步宿主」）。
    测试模块的 `_DRIFT_CLAIMS` 按名字逐键核对；写不成可核对声明的理由才只靠 `why` 文本。
    """

    __slots__ = ("observed", "direction", "why", "claim")

    def __init__(self, observed: Any, direction: str, why: str, claim: str | None = None) -> None:
        assert direction in _DIRECTIONS, direction
        assert why and len(why) >= 12, f"漂移条目必须写清机理：{why!r}"
        if direction in {"superset", "subset"}:
            assert isinstance(observed, (list, tuple, set, frozenset)), (
                f"{direction} 方向的登记值必须是集合：{observed!r}"
            )
        self.observed = observed
        self.direction = direction
        self.why = why
        self.claim = claim

    def __repr__(self) -> str:
        return f"_Drift({self.observed!r}, {self.direction!r}, claim={self.claim!r})"


# ── 漂移台账：开始（逐条人工复核；改动须写明机理与现算值）──────────────────────
_SLICE_DRIFTS: dict[str, _Drift] = {
    'TestAdjudicationLegality::ac14_in_scope_consumer_count': _Drift(
        42, 'grow', (
            '本 slice 宿主里 import AC-14 notice 组件（GtEntrySyncCapabilityNotice）的文件 0 → 42：'
            '本 spec task 3.5 给宿主接同步能力单源时逐个挂了 notice（44 条 entry，有的 entry 共用宿主文件）。只许增长：掉下'
            '去说明有宿主把 notice 摘了。'
        ),
    ),
    'TestAdjudicationLegality::ac14_out_of_scope_consumer_count': _Drift(
        185, 'grow', (
            'notice 组件的非本 slice 消费方 46 → 185：本 spec task 3.5 给其余循环宿主接同步能力单源时逐个挂了 notice'
            '。只许增长。'
        ),
    ),
    'TestAdjudicationLegality::no_switch_shape::xlsx/gt-a3-consolidation-console': _Drift(
        'switch+no_gt_oo_mount', 'pinned', (
            'A3 合并中控台改挂共享同步宿主（sync bridge 替代 legacy mode + GtOnlyOfficeSheet），同时有了「结构化 '
            '/ 在线编辑」开关；冻结时它是 4 条无开关 entry 之一。'
        ), claim='carrier_moved_to_sync_editor_host',
    ),
    'TestAdjudicationLegality::no_switch_shape::xlsx/gt-c22-itgc-bundle': _Drift(
        'switch+gt_oo_mount', 'pinned', (
            'C22 接同步能力单源（本 spec task 3.5）后有了受 showModeSwitch 控制的 mode 开关，仍挂 GtOnlyOffic'
            'eSheet；冻结时它是无开关 entry。'
        ),
    ),
    'TestBusinessModelProjection::wp_code_count::a-program-console': _Drift(
        23, 'shrink', (
            '程序表宿主 a-program-console 服务的 wp_code 32 → 23：S 循环检查表组件接进渲染管线（655faa7c4 / 40'
            '561d2c6，2026-10-25），S9-1 / S9-2 / S10-1 / S10-2 / S17-1 / S17-2 / S17-3 / '
            'S17-11 / S17-21 改派到各自的检查表组件。只许收缩：长回去说明又有码被塞回程序表壳。'
        ),
    ),
    'TestDeletionPlanConsistency::shared_base_production_edges': _Drift(
        23, 'shrink', (
            '共享基类 useWorkpaperEntryDualMode.ts 的生产消费边 26 → 23：J2 / J3 / M9 三个 per-entry'
            ' dual-mode 薄壳随各自 lane 改线后删除（与 production_edge_files 消失的 3 个文件逐一对应）。只许收缩。'
        ),
    ),
    'TestDualModeCarrierInventory::all_dual_mode_modules_in_repo': _Drift(
        92, 'shrink', (
            '全仓 *DualMode*.ts 模块 114 → 92：各循环 lane 把宿主改到共享载体后删掉了 per-entry dual-mode 孤儿'
            '。只许收缩：长回去说明又造了 per-entry 载体。'
        ),
    ),
    'TestDualModeCarrierInventory::production_edge_files::useCycleHtmlOoDualMode.ts': _Drift(
        [
            'audit-platform/frontend/src/components/workpaper/GtL1ShortTermLoans.vue',
            'audit-platform/frontend/src/components/workpaper/GtL2InterestPayable.vue',
            'audit-platform/frontend/src/components/workpaper/GtL3LongTermLoans.vue',
            'audit-platform/frontend/src/components/workpaper/GtL4BondsPayable.vue',
            'audit-platform/frontend/src/components/workpaper/GtL5LongTermPayables.vue',
            'audit-platform/frontend/src/components/workpaper/GtL6SpecialPayables.vue',
            'audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue',
            'audit-platform/frontend/src/components/workpaper/GtL8FinancialExpenses.vue',
            'audit-platform/frontend/src/components/workpaper/shared/CycleStandaloneProcedureShell.vue',
        ], 'superset', (
            'L 循环 lane 把 L3~L8 六个宿主改到共享载体 useCycleHtmlOoDualMode（生产消费文件 3 → 9）。只许变大：少了说'
            '明有宿主又退回 per-entry 载体。'
        ),
    ),
    'TestDualModeCarrierInventory::production_edge_files::useWorkpaperEntryDualMode.ts': _Drift(
        [
            'audit-platform/frontend/src/components/workpaper/GtB22AControlMatrix.vue',
            'audit-platform/frontend/src/components/workpaper/GtB22BControlMatrix.vue',
            'audit-platform/frontend/src/components/workpaper/GtB22BDeficiencyEvaluation.vue',
            'audit-platform/frontend/src/components/workpaper/GtB22CDesignEffectiveness.vue',
            'audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue',
            'audit-platform/frontend/src/components/workpaper/composables/useD1EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useD3EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useD4EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useD5EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useD6EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useD7EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useG2DualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM10EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM1EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM2EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM3EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM4EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM5EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM6EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM7EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useM8EntryDualMode.ts',
            'audit-platform/frontend/src/components/workpaper/composables/useN2DualMode.ts',
            'audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue',
        ], 'subset', 'J2 / J3 / M9 的 per-entry dual-mode 薄壳删除后，共享基类的生产消费文件 26 → 23。只许变小。',
    ),
    'TestDualModeCarrierInventory::test_edge_count::useCycleHtmlOoDualMode.ts': _Drift(
        1, 'grow', (
            '共享载体有了守卫用例 sync/__tests__/sharedModeSwitchGate.spec.ts（本 spec task 3.5 的 m'
            'ode 开关门控单源）。只许增长。'
        ),
    ),
    'TestDynamicRowIdentity::defect::b50_account_assertion_matrix_rows': _Drift(
        'missing', 'pinned', (
            'B50 科目矩阵的 :key 已从可改科目名 row.name 改成 row.rowKey（BC-48 修复）⇒ 冻结时登记的缺陷形态没了；slic'
            'e 仍记 DEFECT（冻结），修复的确认归 6.3。'
        ),
    ),
    'TestEntryGroupsAreRecomputable::wp_code_count::a-program-console': _Drift(
        23, 'shrink', (
            '程序表宿主 a-program-console 服务的 wp_code 32 → 23：S 循环检查表组件接进渲染管线（655faa7c4 / 40'
            '561d2c6，2026-10-25），S9-1 / S9-2 / S10-1 / S10-2 / S17-1 / S17-2 / S17-3 / '
            'S17-11 / S17-21 改派到各自的检查表组件。只许收缩：长回去说明又有码被塞回程序表壳。'
        ),
    ),
    'TestFormDifferences::ad1_xlsx_independent_total': _Drift(
        139, 'pinned', (
            'manifest 的 xlsx 独立入口 136 → 139：2026-10-07 起新增 gt-d2-inspection（D2 检查表单独发布）'
            '、j2 设定受益计划、j3 股份支付三个独立 entry，都不属 A/B/C/S，本 slice 的范围算术不受影响。'
        ),
    ),
    'TestHtmlCounterpartIsSourceBacked::runtime_sheet_exprs::xlsx/gt-a177-independence-declaration': _Drift(
        [], 'pinned', (
            'A17-7 的 OO 挂载点换成共享同步宿主，sheet 由发布的 representation 决定，挂载点不再带 :sheet-name 表达式'
            '。'
        ), claim='carrier_moved_to_sync_editor_host',
    ),
    'TestHtmlCounterpartIsSourceBacked::runtime_sheet_exprs::xlsx/gt-c22-itgc-bundle': _Drift(
        ["activeDocTab.ooSheetName || ''"], 'pinned', (
            'C22 的 OO 挂载点改传册内真实 sheet 名 activeDocTab.ooSheetName（CC-63：原先传 wpCode，与册内 s'
            'heet 名零交集）。'
        ),
    ),
    'TestHtmlCounterpartIsSourceBacked::sheet_literal::xlsx/gt-a38-goodwill-impairment': _Drift(
        'absent', 'pinned', (
            'A3-8 的挂载点改传纯 wp_code（7e4b339bc，2026-10-04：lane3 spec 把解析层的两层缺口修好 —— 合册真名以 '
            'A3-7 起头、A-only 子码正则走严格分支 ⇒ 原先纯码解析不到册），不再传册内中文 sheet 名 A3-8商誉减值测试；slice 冻结的'
            '是宿主层改之前的写法。声明核对 resolver 真能把 A3-8 解析到那本合册。'
        ), claim='sheet_literal_replaced_by_bare_wp_code',
    ),
    'TestModeSwitchResolution::counter::entries_mounting_the_ac14_notice': _Drift(
        44, 'grow', '挂了 AC-14 notice 的 entry 0 → 44（本 spec task 3.5，见 bp7_superseded 组）。只许增长。',
    ),
    'TestModeSwitchResolution::counter::hosts_with_oo_mount': _Drift(
        29, 'shrink', (
            '17 个 A 类宿主把 GtOnlyOfficeSheet 换成共享同步宿主（冻结口径只认 GtOnlyOfficeSheet）⇒ 46 → 29。'
            '只许收缩：长回去说明又有宿主直接挂 legacy 载体。'
        ),
    ),
    'TestModeSwitchResolution::counter::hosts_with_segmented_site': _Drift(
        44, 'pinned', 'A3 与 C22 新增了 mode 开关 ⇒ 带开关的宿主 42 → 44。',
    ),
    'TestModeSwitchResolution::counter::oo_mounts_mode_gated': _Drift(
        37, 'shrink', (
            '受 mode 门控的 GtOnlyOfficeSheet 挂载点 51 → 37：载体迁移到共享同步宿主的宿主不再计入（C22 由 1 个变 2 个'
            '）。只许收缩。'
        ),
    ),
    'TestModeSwitchResolution::counter::oo_mounts_sheet_fallthrough': _Drift(
        2, 'shrink', '无 mode 门控、只靠 sheet 条件的 GtOnlyOfficeSheet 挂载点 4 → 2（载体迁移）。只许收缩。',
    ),
    'TestModeSwitchResolution::counter::oo_mounts_total': _Drift(
        39, 'shrink', 'GtOnlyOfficeSheet 挂载点 55 → 39（= 门控 37 + sheet 条件 2，划分恒等式照旧成立）。只许收缩。',
    ),
    'TestModeSwitchResolution::verdict::xlsx/gt-c22-itgc-bundle': _Drift(
        'redeemable', 'pinned', (
            'C22 新开关的 v-model renderMode 正是两个 OO 挂载点的门控变量 ⇒ 现算 redeemable（冻结时 no_switch'
            '_at_all）。'
        ),
    ),
    'TestProperty22DynamicColumnIdentity::P22-D1::site': _Drift(
        'missing', 'pinned', (
            'P22-D1 已修（26e5ef994）：列 key 从裸下标 i 改为 year_${i+1}，列数改由 FORECAST_YEARS 驱动（宿主'
            '注释「Property 22 修复」），写死的 (_, i) in 5 没了。'
        ),
    ),
    'TestProperty22DynamicColumnIdentity::P22-D1::value_binding_site': _Drift(
        'moved', 'pinned', '值绑定 recoverable.dcf.cash_flows[i] 仍在，随 P22-D1 的修复平移了行。',
    ),
    'TestProperty22DynamicColumnIdentity::P22-D3::audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue#L1577': _Drift(
        'moved', 'pinned', '列偏好分组仍用 grp.label 作 key（P22-D3 未修的那一处），随源码增删平移。',
    ),
    'TestProperty22DynamicColumnIdentity::label_as_key_site_files': _Drift(
        ['audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue'], 'pinned', (
            'label 作 key 的站点 3 → 1：B50 科目矩阵行与统计行的 :key="row.name" 已改成 row.rowKey（BC-48 '
            '修复，宿主注释可见），只剩列偏好分组 :key="grp.label"。'
        ),
    ),
    'TestProperty69EvidenceAndCounters::registry_component_type_total': _Drift(
        228, 'grow', (
            'htmlRendererRegistry 的 componentType 216 → 228：新增的含 S 循环检查表组件（s1 / s8 / s9'
            ' / s10 / s17，655faa7c4 FEAT-002 接进渲染管线）。只许增长：掉下去说明有 componentType 被删了。'
        ),
    ),
    'TestSliceScopeIsRecomputable::abcs_letter_hit_total': _Drift(
        43, 'pinned', (
            'c-control-test 的 wp_match 现在带 C2（wp_code 裁决），从无码共享族进了 C 字母桶 ⇒ A/B/C/S 字母命中'
            ' 42 → 43、C 桶 1 → 2、无码共享 5 → 4。'
        ),
    ),
    'TestSliceScopeIsRecomputable::letter_bucket_counts': _Drift(
        {'A': 20, 'B': 11, 'C': 2, 'S': 10, 'pattern_less_shared': 4}, 'pinned', (
            'c-control-test 的 wp_match 现在带 C2（wp_code 裁决），从无码共享族进了 C 字母桶 ⇒ A/B/C/S 字母命中'
            ' 42 → 43、C 桶 1 → 2、无码共享 5 → 4。'
        ),
    ),
    'TestSliceScopeIsRecomputable::pattern_less_shared_total': _Drift(
        4, 'pinned', (
            'c-control-test 的 wp_match 现在带 C2（wp_code 裁决），从无码共享族进了 C 字母桶 ⇒ A/B/C/S 字母命中'
            ' 42 → 43、C 桶 1 → 2、无码共享 5 → 4。'
        ),
    ),
    'TestSliceScopeIsRecomputable::slice_entries_with_delivered_contract': _Drift(
        [
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-c-control-test',
        ], 'superset', (
            'slice 冻结时本域一份 per-entry 契约都没有；此后 A 循环 canary（a51.cashflow_audit）与 C 循环 can'
            'ary（c-control-test 的 reviewed 契约）交付。只许变大：已交付的契约不许消失。'
        ),
    ),
    'TestSliceScopeIsRecomputable::xlsx_independent_total_in_manifest': _Drift(
        139, 'pinned', (
            'manifest 的 xlsx 独立入口 136 → 139：2026-10-07 起新增 gt-d2-inspection（D2 检查表单独发布）'
            '、j2 设定受益计划、j3 股份支付三个独立 entry，都不属 A/B/C/S，本 slice 的范围算术不受影响。'
        ),
    ),
}

_SLICE_DRIFT_GROUPS: tuple[tuple[str, frozenset[str], _Drift], ...] = (
    (
        'manifest_capability_pending',
        _keys(
            'TestAdjudicationLegality::mirror_capability::',
            'xlsx/cash-flow-verification',
            'xlsx/gt-a101-governance-communication',
            'xlsx/gt-a111-subsequent-events-inquiry',
            'xlsx/gt-a112-dual-checklist',
            'xlsx/gt-a115-disclosure-checklist',
            'xlsx/gt-a121-legal-confirmation',
            'xlsx/gt-a171-audit-summary',
            'xlsx/gt-a1721-kam',
            'xlsx/gt-a173-consultation-record',
            'xlsx/gt-a1731-consultation-execution',
            'xlsx/gt-a174-disagreement-record',
            'xlsx/gt-a176-closing-meeting',
            'xlsx/gt-a177-independence-declaration',
            'xlsx/gt-a181-regulatory-submission',
            'xlsx/gt-a182-regulatory-communication',
            'xlsx/gt-a271-it-audit-memo',
            'xlsx/gt-a3-consolidation-console',
            'xlsx/gt-a38-goodwill-impairment',
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-a81-other-info-representation',
            'xlsx/gt-a91-deficiency-letter',
            'xlsx/gt-b1-evaluation',
            'xlsx/gt-b1-kaa-check',
            'xlsx/gt-b1-risk-assessment',
            'xlsx/gt-b14-due-diligence-report',
            'xlsx/gt-b22-a-control-matrix',
            'xlsx/gt-b22-b-control-matrix',
            'xlsx/gt-b22-b-deficiency-evaluation',
            'xlsx/gt-b22-c-design-effectiveness',
            'xlsx/gt-b23-process-control',
            'xlsx/gt-b50-risk-assessment',
            'xlsx/gt-c-control-test',
            'xlsx/gt-c22-itgc-bundle',
            'xlsx/gt-custom-wp-editor',
            'xlsx/gt-wp-renderer',
            'xlsx/s12-cpa-expert/gt-s12-cpa-expert',
            'xlsx/s13-mgmt-expert/gt-s13-mgmt-expert',
            'xlsx/s14-accounting-estimate/gt-s14-accounting-estimate',
            'xlsx/s15-eps-roe/gt-s15-eps-roe',
            'xlsx/s20-revenue-deduction/gt-s20-revenue-deduction',
            'xlsx/s21-data-asset/gt-s21-data-asset',
            'xlsx/s3-policy-change/gt-s3-policy-change',
            'xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange',
            'xlsx/s5-debt-restructuring/gt-s5-debt-restructuring',
            'xlsx/s6-fund-occupation/gt-s6-fund-occupation',
            'xlsx/shared/cycle-standalone-procedure-shell',
        ),
        _Drift(None, 'pinned', (
            '全量 manifest 已把这 46 条 entry 的 capability 置为 null（pending 裁决制，umbrella task '
            '1.1），与本 slice 的 capability 一致；冻结时 manifest 还写着 single_onlyoffice（BP-3 的分歧）'
            '。capability 终裁属 6.3，裁完后本组整体删除。'
        )),
    ),
    (
        'html_store_from_sync_host_carrier',
        _keys(
            'TestAdjudicationLegality::mirror_html_store::',
            'xlsx/gt-a101-governance-communication',
            'xlsx/gt-a111-subsequent-events-inquiry',
            'xlsx/gt-a121-legal-confirmation',
            'xlsx/gt-a171-audit-summary',
            'xlsx/gt-a1721-kam',
            'xlsx/gt-a173-consultation-record',
            'xlsx/gt-a1731-consultation-execution',
            'xlsx/gt-a174-disagreement-record',
            'xlsx/gt-a176-closing-meeting',
            'xlsx/gt-a177-independence-declaration',
            'xlsx/gt-a181-regulatory-submission',
            'xlsx/gt-a182-regulatory-communication',
            'xlsx/gt-a271-it-audit-memo',
            'xlsx/gt-a3-consolidation-console',
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-a81-other-info-representation',
            'xlsx/gt-a91-deficiency-letter',
        ),
        _Drift('projection_contract', 'pinned', (
            '这 17 个宿主的 OO 挂载点换成共享同步宿主后，manifest 生成器把 html_store 记为 projection_contract（'
            'resolver = workpaper_sync_published_representation）；其中只有 a51 有 per-entry 契'
            '约，其余 16 条的 projection_contract 来自载体而非契约。'
        ), claim='carrier_moved_to_sync_editor_host'),
    ),
    (
        'sheet_literal_gone_with_carrier',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::sheet_literal::',
            'xlsx/gt-a101-governance-communication',
            'xlsx/gt-a111-subsequent-events-inquiry',
            'xlsx/gt-a121-legal-confirmation',
            'xlsx/gt-a171-audit-summary',
            'xlsx/gt-a1721-kam',
            'xlsx/gt-a173-consultation-record',
            'xlsx/gt-a1731-consultation-execution',
            'xlsx/gt-a174-disagreement-record',
            'xlsx/gt-a176-closing-meeting',
            'xlsx/gt-a181-regulatory-submission',
            'xlsx/gt-a182-regulatory-communication',
            'xlsx/gt-a271-it-audit-memo',
            'xlsx/gt-a3-consolidation-console',
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-a81-other-info-representation',
            'xlsx/gt-a91-deficiency-letter',
        ),
        _Drift('absent', 'pinned', (
            'OO 挂载点换成共享同步宿主后 sheet 由发布的 representation 决定，挂载点上不再有 sheet-name 字面量；slice '
            '的 template_ref 取证口径与现状脱钩，重取证归 6.3。'
        ), claim='carrier_moved_to_sync_editor_host'),
    ),
    (
        'switch_judged_inert_under_frozen_carrier',
        _keys(
            'TestModeSwitchResolution::verdict::',
            'xlsx/gt-a101-governance-communication',
            'xlsx/gt-a111-subsequent-events-inquiry',
            'xlsx/gt-a121-legal-confirmation',
            'xlsx/gt-a171-audit-summary',
            'xlsx/gt-a1721-kam',
            'xlsx/gt-a173-consultation-record',
            'xlsx/gt-a1731-consultation-execution',
            'xlsx/gt-a174-disagreement-record',
            'xlsx/gt-a176-closing-meeting',
            'xlsx/gt-a177-independence-declaration',
            'xlsx/gt-a181-regulatory-submission',
            'xlsx/gt-a182-regulatory-communication',
            'xlsx/gt-a271-it-audit-memo',
            'xlsx/gt-a3-consolidation-console',
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-a81-other-info-representation',
            'xlsx/gt-a91-deficiency-letter',
        ),
        _Drift('inert', 'pinned', (
            '冻结口径只认 GtOnlyOfficeSheet 为 OO 挂载点；这 17 个宿主改挂共享同步宿主后现算判成 inert。可伪证声明逐宿主核了新载'
            '体仍在 mode 开关门控的分支里（开关仍有效），不是 AC 1.4 的真 inert。'
        ), claim='carrier_moved_to_sync_editor_host'),
    ),
    (
        'redeemable_shape_under_frozen_carrier',
        _keys(
            'TestModeSwitchResolution::redeemable_shape::',
            'xlsx/gt-a101-governance-communication',
            'xlsx/gt-a111-subsequent-events-inquiry',
            'xlsx/gt-a121-legal-confirmation',
            'xlsx/gt-a171-audit-summary',
            'xlsx/gt-a1721-kam',
            'xlsx/gt-a173-consultation-record',
            'xlsx/gt-a1731-consultation-execution',
            'xlsx/gt-a174-disagreement-record',
            'xlsx/gt-a176-closing-meeting',
            'xlsx/gt-a177-independence-declaration',
            'xlsx/gt-a181-regulatory-submission',
            'xlsx/gt-a182-regulatory-communication',
            'xlsx/gt-a271-it-audit-memo',
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-a81-other-info-representation',
            'xlsx/gt-a91-deficiency-letter',
        ),
        _Drift('switch+no_gated_gt_oo', 'pinned', '冻结口径下「开关 + 受门控的 GtOnlyOfficeSheet」三要素缺了后者：载体换成了共享同步宿主（声明逐宿主核对新载体仍受同一开关门控）。', claim='carrier_moved_to_sync_editor_host'),
    ),
    (
        'bp7_superseded_by_ac14_notice',
        _keys(
            'TestAdjudicationLegality::bp7_superseded::',
            'xlsx/gt-a101-governance-communication',
            'xlsx/gt-a111-subsequent-events-inquiry',
            'xlsx/gt-a112-dual-checklist',
            'xlsx/gt-a115-disclosure-checklist',
            'xlsx/gt-a121-legal-confirmation',
            'xlsx/gt-a171-audit-summary',
            'xlsx/gt-a1721-kam',
            'xlsx/gt-a173-consultation-record',
            'xlsx/gt-a1731-consultation-execution',
            'xlsx/gt-a174-disagreement-record',
            'xlsx/gt-a176-closing-meeting',
            'xlsx/gt-a177-independence-declaration',
            'xlsx/gt-a181-regulatory-submission',
            'xlsx/gt-a182-regulatory-communication',
            'xlsx/gt-a271-it-audit-memo',
            'xlsx/gt-a3-consolidation-console',
            'xlsx/gt-a38-goodwill-impairment',
            'xlsx/gt-a51-cashflow-audit',
            'xlsx/gt-a81-other-info-representation',
            'xlsx/gt-a91-deficiency-letter',
            'xlsx/gt-b1-evaluation',
            'xlsx/gt-b1-kaa-check',
            'xlsx/gt-b1-risk-assessment',
            'xlsx/gt-b14-due-diligence-report',
            'xlsx/gt-b22-a-control-matrix',
            'xlsx/gt-b22-b-control-matrix',
            'xlsx/gt-b22-b-deficiency-evaluation',
            'xlsx/gt-b22-c-design-effectiveness',
            'xlsx/gt-b23-process-control',
            'xlsx/gt-b50-risk-assessment',
            'xlsx/gt-c-control-test',
            'xlsx/gt-c22-itgc-bundle',
            'xlsx/gt-custom-wp-editor',
            'xlsx/s12-cpa-expert/gt-s12-cpa-expert',
            'xlsx/s13-mgmt-expert/gt-s13-mgmt-expert',
            'xlsx/s14-accounting-estimate/gt-s14-accounting-estimate',
            'xlsx/s15-eps-roe/gt-s15-eps-roe',
            'xlsx/s20-revenue-deduction/gt-s20-revenue-deduction',
            'xlsx/s21-data-asset/gt-s21-data-asset',
            'xlsx/s3-policy-change/gt-s3-policy-change',
            'xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange',
            'xlsx/s5-debt-restructuring/gt-s5-debt-restructuring',
            'xlsx/s6-fund-occupation/gt-s6-fund-occupation',
            'xlsx/shared/cycle-standalone-procedure-shell',
        ),
        _Drift('mounts_notice', 'pinned', (
            '本 spec task 3.5 给这 44 条 entry 的宿主挂了 AC-14 notice ⇒ 冻结时登记的 BP-7「未挂 notice」已'
            '消解；slice 冻结不改，这里只钉住消解后的现状。'
        )),
    ),
    (
        'persistence_one_level_beyond_closure',
        _keys(
            'Test',
            'AdjudicationLegality::channel_detected::xlsx/shared/cycle-standalone-procedure-shell',
            'EntryGroupsAreRecomputable::channel::xlsx/shared/cycle-standalone-procedure-shell',
            'EntryGroupsAreRecomputable::group_channel::xlsx/shared/cycle-standalone-procedure-shell',
        ),
        _Drift('none_detected', 'pinned', (
            '共享程序表壳的 field-overrides 写调用随年度门控收口从 GtAProgramConsole 搬进 @/composables/use'
            'ProgramOverrideTarget.ts：壳 → CycleTabProcedure → CycleProgramConsoleTab → '
            'GtAProgramConsole → useProgramOverrideTarget，比冻结时深一层、落在闭包深度 3 之外；通道仍是 fiel'
            'd_overrides（声明用深度 4 现算核对）。'
        ), claim='persistence_one_level_beyond_closure'),
    ),
    (
        'override_write_moved_to_shared_composable',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::channel_ref::',
            'xlsx/gt-a3-consolidation-console::field_overrides::audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue#L376',
            'xlsx/gt-b50-risk-assessment::field_overrides::audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1174',
            'xlsx/shared/cycle-standalone-procedure-shell::field_overrides::audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1174',
        ),
        _Drift('missing', 'pinned', (
            '程序表宿主（GtAProgramConsole / GtA3ConsolidationConsole）的 field-overrides 写调用搬进'
            '了 @/composables/useProgramOverrideTarget.ts（位置 / 年度取不到时不写），声明行上的字面量因此没了。'
        ), claim='override_write_moved_to_shared_composable'),
    ),
    (
        'channel_literal_still_in_file',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::channel_ref::',
            'xlsx/gt-a112-dual-checklist::field_overrides::audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L624',
            'xlsx/gt-a112-dual-checklist::field_overrides::audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L638',
            'xlsx/gt-a112-dual-checklist::field_overrides::audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L652',
            'xlsx/gt-a115-disclosure-checklist::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useA115Checklist.ts#L175',
            'xlsx/gt-a115-disclosure-checklist::field_overrides::audit-platform/frontend/src/components/workpaper/composables/useA115Checklist.ts#L269',
            'xlsx/gt-a91-deficiency-letter::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useA91DeficiencyLetter.ts#L270',
            'xlsx/gt-b1-evaluation::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/gt-b1-kaa-check::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/gt-b1-risk-assessment::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useB1RiskAssessment.ts#L261',
            'xlsx/gt-b1-risk-assessment::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/gt-b14-due-diligence-report::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/gt-b22-b-control-matrix::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useB22BControlMatrix.ts#L160',
            'xlsx/gt-b22-b-control-matrix::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useB22BControlMatrix.ts#L197',
            'xlsx/gt-b22-b-control-matrix::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useB22BControlMatrix.ts#L383',
            'xlsx/gt-b22-b-deficiency-evaluation::checklist_responses::audit-platform/frontend/src/components/workpaper/GtB22BDeficiencyEvaluation.vue#L385',
            'xlsx/gt-b22-c-design-effectiveness::checklist_responses::audit-platform/frontend/src/components/workpaper/GtB22CDesignEffectiveness.vue#L197',
            'xlsx/gt-b22-c-design-effectiveness::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useB22CDesignEffectiveness.ts#L282',
            'xlsx/gt-b22-c-design-effectiveness::checklist_responses::audit-platform/frontend/src/components/workpaper/composables/useB22CDesignEffectiveness.ts#L393',
            'xlsx/gt-b23-process-control::field_overrides::audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L624',
            'xlsx/gt-b50-risk-assessment::checklist_responses::audit-platform/frontend/src/components/workpaper/WpPopupChecklist.vue#L123',
            'xlsx/gt-b50-risk-assessment::checklist_responses::audit-platform/frontend/src/components/workpaper/WpPopupChecklist.vue#L75',
            'xlsx/gt-b50-risk-assessment::checklist_responses::audit-platform/frontend/src/components/workpaper/WpPopupDocxEditor.vue#L152',
            'xlsx/gt-c-control-test::checklist_responses::audit-platform/frontend/src/components/workpaper/cControlTest/CControlTestSubPage.vue#L616',
            'xlsx/gt-c-control-test::checklist_responses::audit-platform/frontend/src/components/workpaper/cControlTest/CControlTestSubPage.vue#L796',
            'xlsx/gt-c-control-test::checklist_responses::audit-platform/frontend/src/components/workpaper/cControlTest/CControlTestSubPage.vue#L819',
            'xlsx/gt-custom-wp-editor::custom_cells::audit-platform/frontend/src/components/workpaper/custom/GtCustomGridSheet.vue#L417',
            'xlsx/gt-custom-wp-editor::custom_cells::audit-platform/frontend/src/services/apiPaths/workpaper.ts#L36',
            'xlsx/gt-wp-renderer::custom_cells::audit-platform/frontend/src/components/workpaper/custom/GtCustomGridSheet.vue#L417',
            'xlsx/gt-wp-renderer::field_overrides::audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L624',
            'xlsx/s12-cpa-expert/gt-s12-cpa-expert::checklist_responses::audit-platform/frontend/src/components/workpaper/s12-cpa-expert/GtS12CpaExpert.vue#L370',
            'xlsx/s12-cpa-expert/gt-s12-cpa-expert::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s13-mgmt-expert/gt-s13-mgmt-expert::checklist_responses::audit-platform/frontend/src/components/workpaper/s13-mgmt-expert/GtS13MgmtExpert.vue#L354',
            'xlsx/s13-mgmt-expert/gt-s13-mgmt-expert::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s14-accounting-estimate/gt-s14-accounting-estimate::checklist_responses::audit-platform/frontend/src/components/workpaper/s14-accounting-estimate/GtS14AccountingEstimate.vue#L326',
            'xlsx/s14-accounting-estimate/gt-s14-accounting-estimate::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s15-eps-roe/gt-s15-eps-roe::checklist_responses::audit-platform/frontend/src/components/workpaper/s15-eps-roe/GtS15EpsRoe.vue#L318',
            'xlsx/s15-eps-roe/gt-s15-eps-roe::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s20-revenue-deduction/gt-s20-revenue-deduction::checklist_responses::audit-platform/frontend/src/components/workpaper/s20-revenue-deduction/GtS20RevenueDeduction.vue#L960',
            'xlsx/s20-revenue-deduction/gt-s20-revenue-deduction::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s21-data-asset/gt-s21-data-asset::checklist_responses::audit-platform/frontend/src/components/workpaper/s21-data-asset/GtS21DataAsset.vue#L327',
            'xlsx/s21-data-asset/gt-s21-data-asset::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s3-policy-change/gt-s3-policy-change::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s5-debt-restructuring/gt-s5-debt-restructuring::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
            'xlsx/s6-fund-occupation/gt-s6-fund-occupation::checklist_responses::audit-platform/frontend/src/composables/useReviewDialog.ts#L427',
        ),
        _Drift('present', 'pinned', '声明行随源码增删平移；通道字面量仍在同一文件里（同文件可有多处调用，不区分平移与另一处）。'),
    ),
    (
        'read_write_call_still_in_file',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::',
            'read::xlsx/gt-b22-b-control-matrix',
            'read::xlsx/gt-b22-b-deficiency-evaluation',
            'read::xlsx/gt-b22-c-design-effectiveness',
            'read::xlsx/gt-b50-risk-assessment',
            'read::xlsx/gt-c22-itgc-bundle',
            'write::xlsx/gt-a115-disclosure-checklist',
            'write::xlsx/gt-a91-deficiency-letter',
            'write::xlsx/gt-b1-risk-assessment',
            'write::xlsx/gt-b22-b-control-matrix',
            'write::xlsx/gt-b22-c-design-effectiveness',
            'write::xlsx/gt-b50-risk-assessment',
            'write::xlsx/gt-c-control-test',
            'write::xlsx/s12-cpa-expert/gt-s12-cpa-expert',
            'write::xlsx/s13-mgmt-expert/gt-s13-mgmt-expert',
            'write::xlsx/s14-accounting-estimate/gt-s14-accounting-estimate',
            'write::xlsx/s15-eps-roe/gt-s15-eps-roe',
            'write::xlsx/s20-revenue-deduction/gt-s20-revenue-deduction',
            'write::xlsx/s21-data-asset/gt-s21-data-asset',
            'write::xlsx/s3-policy-change/gt-s3-policy-change',
            'write::xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange',
            'write::xlsx/s5-debt-restructuring/gt-s5-debt-restructuring',
            'write::xlsx/s6-fund-occupation/gt-s6-fund-occupation',
        ),
        _Drift('present', 'pinned', '读 / 写调用所在行随源码增删平移；同一文件里仍有 checklist-responses 的读 / 写调用。'),
    ),
    (
        'prefix_constant_moved',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::prefix::',
            'xlsx/gt-b22-a-control-matrix::IT_SOD_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-b22-a-control-matrix::IT_SUMMARY_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-b22-a-control-matrix::IT_SYSTEM_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-b22-b-deficiency-evaluation::IT_SOD_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-b22-b-deficiency-evaluation::IT_SUMMARY_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-b22-b-deficiency-evaluation::IT_SYSTEM_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-b23-process-control::OVERALL_ITEM_ID@GtC1EntityControl.vue',
            'xlsx/gt-b23-process-control::summaryItemId@GtC24JournalDetail.vue',
            'xlsx/gt-c22-itgc-bundle::C21_CARRYOVER_ITEM_ID@useC22BundleState.ts',
            'xlsx/gt-wp-renderer::IT_SOD_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-wp-renderer::IT_SUMMARY_PREFIX@useB22AControlMatrix.ts',
            'xlsx/gt-wp-renderer::IT_SYSTEM_PREFIX@useB22AControlMatrix.ts',
            'xlsx/s21-data-asset/gt-s21-data-asset::CONDITIONS_ID@GtS21Capitalization.vue',
        ),
        _Drift('moved', 'pinned', 'owner 模块增删代码后前缀常量声明行平移；内容锚点（常量名 + 字面量）仍唯一命中。'),
    ),
    (
        'k_legacy_dual_mode_prefix_removed',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::prefix::',
            'xlsx/gt-b23-process-control::DUAL_MODE_STORAGE_PREFIX@GtK4OtherCurrentLiabilities.vue',
            'xlsx/gt-b23-process-control::DUAL_MODE_STORAGE_PREFIX@GtK5Provisions.vue',
            'xlsx/gt-b23-process-control::DUAL_MODE_STORAGE_PREFIX@GtK6HeldForSale.vue',
        ),
        _Drift('missing', 'pinned', (
            'K 循环 lane 删掉了 K4 / K5 / K6 宿主的 legacy `kN-dual-mode:` localStorage 前缀常量（与已'
            '删 orphan 孪生同值撞车，宿主注释可见）；b23 的闭包常量清单冻结时把它们收了进来。'
        )),
    ),
    (
        'registry_line_moved',
        _keys(
            'TestEntryGroupsAreRecomputable::registry_line::',
            's12-cpa-expert',
            's13-mgmt-expert',
            's14-accounting-estimate',
            's15-eps-roe',
            's20-revenue-deduction',
            's21-data-asset',
        ),
        _Drift('moved', 'pinned', 'registry 条目文件新增条目后 s12 / s13 / s14 / s15 / s20 / s21 的声明行一起平移；同判据已先核内容。'),
    ),
    (
        'source_ref_lands_on_blank_line',
        _keys(
            'TestHtmlCounterpartIsSourceBacked::nonblank::',
            'audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1472',
            'audit-platform/frontend/src/components/workpaper/composables/useB1RiskAssessment.ts#L261',
            'audit-platform/frontend/src/components/workpaper/composables/useB22BControlMatrix.ts#L160',
        ),
        _Drift('blank', 'pinned', (
            '声明的 source_ref 行号落在空行：所在文件改动后锚点平移，这几条 ref 只存位置不存 token（内容锚点由 read / write '
            '/ channel_ref 判据负责）。'
        )),
    ),
    (
        'clean_row_identity_line_moved',
        _keys(
            'TestDynamicRowIdentity::clean::',
            'a38_fair_value_rows',
            'c_control_test_step_rows',
        ),
        _Drift('moved', 'pinned', (
            '稳定身份寻址的那一行（A3-8 removeFairValueRow(row.id) / C 控制测试 :key="step.num"）随源码增删平'
            '移，内容唯一命中。'
        )),
    ),
    (
        'p22_d3_row_name_keys_fixed',
        _keys(
            'TestProperty22DynamicColumnIdentity::P22-D3::',
            'audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue#L1475',
            'audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue#L1792',
        ),
        _Drift('missing', 'pinned', 'B50 科目矩阵行与统计行的 :key="row.name" 已改成 row.rowKey（BC-48 修复）。'),
    ),
)
# ── 漂移台账：结束 ────────────────────────────────────────────────────────────

#: 本次运行里真正被判据触达过的 key（死条目自检用）。
_DRIFT_SITES_TOUCHED: set[str] = set()


def _ledger_items() -> list[tuple[str, frozenset[str], _Drift]]:
    """单项与组统一成 (名字, 键集合, 登记)；单项的名字就是它的键。"""
    singles = [(key, frozenset({key}), drift) for key, drift in _SLICE_DRIFTS.items()]
    return [*singles, *_SLICE_DRIFT_GROUPS]


def _ledger_keys() -> set[str]:
    return {key for _name, keys, _drift in _ledger_items() for key in keys}


def _ledger_drifts() -> list[_Drift]:
    return [drift for _name, _keys, drift in _ledger_items()]


def _drift_of(key: str) -> "_Drift | None":
    _DRIFT_SITES_TOUCHED.add(key)
    hit = _SLICE_DRIFTS.get(key)
    if hit is not None:
        return hit
    for _name, keys, drift in _SLICE_DRIFT_GROUPS:
        if key in keys:
            return drift
    return None


def _drift_scalar(value: Any) -> int:
    """「可比较的规模」：数值取本身，集合 / 序列 / 映射取长度。"""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return len(value)


def _assert_declared_or_registered_drift(
    key: str, *, declared: Any, observed: Any, hint: str = ""
) -> None:
    """快照登记值与现算值：相等即过；不等则必须与台账登记的现算值一致（按方向）。"""
    drift = _drift_of(key)
    if declared == observed:
        assert drift is None, (
            f"{key}: 快照与现算已重新相等（{declared!r}）⇒ 漂移台账里的条目必须删掉，"
            f"否则它会一直替一个不存在的问题背书（登记的现算值 {drift.observed!r}）"
        )
        return
    assert drift is not None, (
        f"{key}: 快照登记 {declared!r} 与现算 {observed!r} 不一致，且漂移台账里没有这一条 "
        f"⇒ 先查清是源码变了还是快照错了，再决定登记还是修。{hint}"
    )
    registered = drift.observed
    if drift.direction == "pinned":
        assert observed == registered, (
            f"{key}: 现算 {observed!r} 与台账钉住的 {registered!r} 不同 ⇒ 又漂了一次，必须重新取证。"
            f"{drift.why}"
        )
    elif drift.direction == "grow":
        assert _drift_scalar(observed) >= _drift_scalar(registered), (
            f"{key}: 现算 {observed!r} 小于登记的 {registered!r}，而该量只许增长 ⇒ 重新取证。{drift.why}"
        )
    elif drift.direction == "shrink":
        assert _drift_scalar(observed) <= _drift_scalar(registered), (
            f"{key}: 现算 {observed!r} 大于登记的 {registered!r}，而该量只许收缩 ⇒ 重新取证。{drift.why}"
        )
    elif drift.direction == "superset":
        lost = sorted(set(registered) - set(observed))
        assert not lost, f"{key}: 登记过的元素不见了 {lost[:5]}（该集合只许变大）⇒ 重新取证。{drift.why}"
    else:
        extra = sorted(set(observed) - set(registered))
        assert not extra, f"{key}: 出现登记之外的新元素 {extra[:5]}（该集合只许变小）⇒ 重新取证。{drift.why}"
