/**
 * useI1Adjudication — I1 审定表 composable
 *
 * 三区块固定行结构：
 *   一、无形资产-原值（1701，借方/资产类）：分类行 + 小计
 *   二、累计摊销（1702，贷方/备抵类）：分类行 + 小计
 *   三、减值准备（1703，贷方/备抵类）：分类行 + 小计
 *   末行：无形资产净值合计 = 原值小计 - 摊销小计 - 减值小计
 *
 * 列：项目 | 期初余额 | 本期增加 | 本期减少 | 期末余额 | 未审数 | AJE | RJE | 审定数
 *
 * 公式引擎接入：
 * - 审定数 = 未审 + AJE + RJE (calcAuditedAmount)
 * - 原值(1701): 期末 = 期初 + 增加 - 减少 (calcAssetEndBalance)
 * - 摊销/减值(1702/1703): 期末 = 期初 + 贷方 - 借方 (calcContraEndBalance)
 * - 三角勾稽: calcTriangleReconciliation(begin, increase, decrease, end) === 0
 * - 净值: calcNetValue(原值小计, 摊销小计, 减值小计)
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.3
 * Requirements: 2.1-2.11
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ChecklistItem, TbData } from './useI1FormData'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcNetValue,
} from './useI1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行 */
export interface I1AdjudicationRow {
  rowId: string
  category: string            // 项目名称/分类
  beginBalance: number        // 期初余额
  increase: number            // 本期增加
  decrease: number            // 本期减少
  endBalance: number          // 期末余额（公式列）
  unadjusted: number          // 未审数
  aje: number                 // AJE调整
  rje: number                 // RJE重分类
  audited: number             // 审定数（公式列）
  isSubtotal?: boolean        // 小计行标记
  isEditable?: boolean        // 可编辑标记
}

/** 三角勾稽校验结果 */
export interface I1ReconciliationResult {
  rowId: string
  layer: string               // '原值' | '累计摊销' | '减值准备'
  category: string            // 行项目名称
  difference: number          // 差额（0=平衡）
  isBalanced: boolean
}

/** TB差异行 */
export interface I1DifferenceRow {
  label: string
  accountCode: string
  audited: number
  tbAmount: number
  difference: number
}

/** 区块类型 */
export type I1BlockType = 'cost' | 'amort' | 'impairment'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认无形资产分类 */
const DEFAULT_COST_CATEGORIES = [
  '专利权', '商标权', '著作权', '土地使用权', '软件', '非专利技术', '特许经营权', '其他',
]

/** 默认摊销分类（与原值对应） */
const DEFAULT_AMORT_CATEGORIES = [
  '专利权', '商标权', '著作权', '土地使用权', '软件', '非专利技术', '特许经营权', '其他',
]

/** 默认减值分类（与原值对应） */
const DEFAULT_IMPAIRMENT_CATEGORIES = [
  '专利权', '商标权', '著作权', '土地使用权', '软件', '非专利技术', '特许经营权', '其他',
]

const ITEM_PREFIX = 'I1-adj'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    tbData?: Ref<TbData>
    crossSheetCostAudited?: Ref<number>
    crossSheetAmortAudited?: Ref<number>
    crossSheetImpairAudited?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 区块一：无形资产-原值（1701借方/资产类） */
  const costRows = ref<I1AdjudicationRow[]>([])
  /** 区块二：累计摊销（1702贷方/备抵类） */
  const amortRows = ref<I1AdjudicationRow[]>([])
  /** 区块三：减值准备（1703贷方/备抵类） */
  const impairmentRows = ref<I1AdjudicationRow[]>([])
  /** 审计说明 */
  const auditNote = ref('')
  /** 审计结论 */
  const auditConclusion = ref('')

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const costData = _getJson(`${ITEM_PREFIX}-cost-rows`)
    const amortData = _getJson(`${ITEM_PREFIX}-amort-rows`)
    const impairData = _getJson(`${ITEM_PREFIX}-impair-rows`)

    if (Array.isArray(costData) && costData.length > 0) {
      costRows.value = costData.map(_normalizeRow)
    } else {
      costRows.value = _buildDefaultRows(DEFAULT_COST_CATEGORIES, 'cost')
    }

    if (Array.isArray(amortData) && amortData.length > 0) {
      amortRows.value = amortData.map(_normalizeRow)
    } else {
      amortRows.value = _buildDefaultRows(DEFAULT_AMORT_CATEGORIES, 'amort')
    }

    if (Array.isArray(impairData) && impairData.length > 0) {
      impairmentRows.value = impairData.map(_normalizeRow)
    } else {
      impairmentRows.value = _buildDefaultRows(DEFAULT_IMPAIRMENT_CATEGORIES, 'impairment')
    }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): I1AdjudicationRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      category: raw.category ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      increase: Number(raw.increase) || 0,
      decrease: Number(raw.decrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      unadjusted: Number(raw.unadjusted) || 0,
      aje: Number(raw.aje) || 0,
      rje: Number(raw.rje) || 0,
      audited: Number(raw.audited) || 0,
      isSubtotal: raw.isSubtotal ?? false,
      isEditable: raw.isEditable ?? true,
    }
  }

  function _buildDefaultRows(categories: string[], block: I1BlockType): I1AdjudicationRow[] {
    const prefix = block === 'cost' ? 'c' : block === 'amort' ? 'a' : 'i'
    const rows: I1AdjudicationRow[] = categories.map((cat) => ({
      rowId: `row-${prefix}-${cat}`,
      category: cat,
      beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: false, isEditable: true,
    }))
    // 小计行
    const subtotalLabel = block === 'cost'
      ? '无形资产-原值小计'
      : block === 'amort'
        ? '累计摊销小计'
        : '减值准备小计'
    rows.push({
      rowId: `row-${prefix}-subtotal`,
      category: subtotalLabel,
      beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
      unadjusted: 0, aje: 0, rje: 0, audited: 0,
      isSubtotal: true, isEditable: false,
    })
    return rows
  }

  // ─── Computed: 小计行（三区块各一） ────────────────────────────────────────

  const costSubtotal = computed<I1AdjudicationRow>(() => {
    const detail = costRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-c-subtotal',
      category: '无形资产-原值小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      increase: calcSubtotal(detail.map((r) => r.increase)),
      decrease: calcSubtotal(detail.map((r) => r.decrease)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  const amortSubtotal = computed<I1AdjudicationRow>(() => {
    const detail = amortRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-a-subtotal',
      category: '累计摊销小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      increase: calcSubtotal(detail.map((r) => r.increase)),
      decrease: calcSubtotal(detail.map((r) => r.decrease)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  const impairmentSubtotal = computed<I1AdjudicationRow>(() => {
    const detail = impairmentRows.value.filter((r) => !r.isSubtotal)
    return {
      rowId: 'row-i-subtotal',
      category: '减值准备小计',
      beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
      increase: calcSubtotal(detail.map((r) => r.increase)),
      decrease: calcSubtotal(detail.map((r) => r.decrease)),
      endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
      unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
      aje: calcSubtotal(detail.map((r) => r.aje)),
      rje: calcSubtotal(detail.map((r) => r.rje)),
      audited: calcSubtotal(detail.map((r) => r.audited)),
      isSubtotal: true,
      isEditable: false,
    }
  })

  /** 无形资产净值合计 = 原值小计审定 - 摊销小计审定 - 减值小计审定 */
  const netValueAudited = computed(() =>
    calcNetValue(costSubtotal.value.audited, amortSubtotal.value.audited, impairmentSubtotal.value.audited),
  )

  /** 净值行对象（用于渲染末行） */
  const netValueRow = computed<I1AdjudicationRow>(() => ({
    rowId: 'row-net-value',
    category: '无形资产净值合计',
    beginBalance: calcNetValue(costSubtotal.value.beginBalance, amortSubtotal.value.beginBalance, impairmentSubtotal.value.beginBalance),
    increase: calcNetValue(costSubtotal.value.increase, amortSubtotal.value.increase, impairmentSubtotal.value.increase),
    decrease: calcNetValue(costSubtotal.value.decrease, amortSubtotal.value.decrease, impairmentSubtotal.value.decrease),
    endBalance: calcNetValue(costSubtotal.value.endBalance, amortSubtotal.value.endBalance, impairmentSubtotal.value.endBalance),
    unadjusted: calcNetValue(costSubtotal.value.unadjusted, amortSubtotal.value.unadjusted, impairmentSubtotal.value.unadjusted),
    aje: calcNetValue(costSubtotal.value.aje, amortSubtotal.value.aje, impairmentSubtotal.value.aje),
    rje: calcNetValue(costSubtotal.value.rje, amortSubtotal.value.rje, impairmentSubtotal.value.rje),
    audited: netValueAudited.value,
    isSubtotal: true,
    isEditable: false,
  }))

  // ─── Computed: 三角勾稽校验（每行+三区块小计） ─────────────────────────────

  /**
   * 三角勾稽校验：
   * - 原值(1701资产类)：期末 = 期初 + 增加 - 减少
   * - 摊销(1702备抵类)：期末 = 期初 + 贷方(增加) - 借方(减少)
   * - 减值(1703备抵类)：期末 = 期初 + 贷方(增加) - 借方(减少)
   *
   * 注意：对备抵类，increase列即贷方发生(计提/增加)，decrease列即借方发生(转回/减少)
   * 因此三角勾稽公式统一为：end - (begin + increase - decrease) === 0
   */
  const reconciliationResults = computed<I1ReconciliationResult[]>(() => {
    const results: I1ReconciliationResult[] = []

    // 原值区块各行校验
    for (const row of costRows.value.filter((r) => !r.isSubtotal)) {
      const diff = calcTriangleReconciliation(row.beginBalance, row.increase, row.decrease, row.endBalance)
      results.push({
        rowId: row.rowId,
        layer: '原值',
        category: row.category,
        difference: diff,
        isBalanced: Math.abs(diff) < 0.01,
      })
    }
    // 原值小计勾稽
    const cs = costSubtotal.value
    const csDiff = calcTriangleReconciliation(cs.beginBalance, cs.increase, cs.decrease, cs.endBalance)
    results.push({
      rowId: cs.rowId,
      layer: '原值',
      category: cs.category,
      difference: csDiff,
      isBalanced: Math.abs(csDiff) < 0.01,
    })

    // 摊销区块各行校验
    for (const row of amortRows.value.filter((r) => !r.isSubtotal)) {
      const diff = calcTriangleReconciliation(row.beginBalance, row.increase, row.decrease, row.endBalance)
      results.push({
        rowId: row.rowId,
        layer: '累计摊销',
        category: row.category,
        difference: diff,
        isBalanced: Math.abs(diff) < 0.01,
      })
    }
    // 摊销小计勾稽
    const as = amortSubtotal.value
    const asDiff = calcTriangleReconciliation(as.beginBalance, as.increase, as.decrease, as.endBalance)
    results.push({
      rowId: as.rowId,
      layer: '累计摊销',
      category: as.category,
      difference: asDiff,
      isBalanced: Math.abs(asDiff) < 0.01,
    })

    // 减值区块各行校验
    for (const row of impairmentRows.value.filter((r) => !r.isSubtotal)) {
      const diff = calcTriangleReconciliation(row.beginBalance, row.increase, row.decrease, row.endBalance)
      results.push({
        rowId: row.rowId,
        layer: '减值准备',
        category: row.category,
        difference: diff,
        isBalanced: Math.abs(diff) < 0.01,
      })
    }
    // 减值小计勾稽
    const is = impairmentSubtotal.value
    const isDiff = calcTriangleReconciliation(is.beginBalance, is.increase, is.decrease, is.endBalance)
    results.push({
      rowId: is.rowId,
      layer: '减值准备',
      category: is.category,
      difference: isDiff,
      isBalanced: Math.abs(isDiff) < 0.01,
    })

    return results
  })

  /** 三区块勾稽总体是否平衡 */
  const isAllReconciled = computed(() =>
    reconciliationResults.value.every((r) => r.isBalanced),
  )

  // ─── Computed: TB取数行 + 差异行（Req 2.9）────────────────────────────────

  /** TB取数行：从 tbData 读取各科目未审数/审定数 */
  const tbRow = computed(() => {
    const tb = options?.tbData?.value ?? {
      unadjusted1701: 0, audited1701: 0,
      unadjusted1702: 0, audited1702: 0,
      unadjusted1703: 0, audited1703: 0,
    }
    return {
      cost: { unadjusted: tb.unadjusted1701, audited: tb.audited1701 },
      amort: { unadjusted: tb.unadjusted1702, audited: tb.audited1702 },
      impairment: { unadjusted: tb.unadjusted1703, audited: tb.audited1703 },
    }
  })

  /** 差异行：审定数 vs TB已有审定数 */
  const differenceRows = computed<I1DifferenceRow[]>(() => {
    const tb = options?.tbData?.value ?? {
      unadjusted1701: 0, audited1701: 0,
      unadjusted1702: 0, audited1702: 0,
      unadjusted1703: 0, audited1703: 0,
    }
    const costAudited = costSubtotal.value.audited
    const amortAudited = amortSubtotal.value.audited
    const impairAudited = impairmentSubtotal.value.audited
    return [
      { label: '无形资产(1701)', accountCode: '1701', audited: costAudited, tbAmount: tb.unadjusted1701, difference: costAudited - tb.unadjusted1701 },
      { label: '累计摊销(1702)', accountCode: '1702', audited: amortAudited, tbAmount: tb.unadjusted1702, difference: amortAudited - tb.unadjusted1702 },
      { label: '减值准备(1703)', accountCode: '1703', audited: impairAudited, tbAmount: tb.unadjusted1703, difference: impairAudited - tb.unadjusted1703 },
    ]
  })

  // ─── Computed: 交叉验证 I1-2 明细表（Req 2.4-2.7）─────────────────────────

  const crossValidation = computed(() => {
    const costFromDetail = options?.crossSheetCostAudited?.value ?? 0
    const amortFromDetail = options?.crossSheetAmortAudited?.value ?? 0
    const impairFromDetail = options?.crossSheetImpairAudited?.value ?? 0
    const costDiff = costSubtotal.value.audited - costFromDetail
    const amortDiff = amortSubtotal.value.audited - amortFromDetail
    const impairDiff = impairmentSubtotal.value.audited - impairFromDetail
    return {
      costDiff,
      amortDiff,
      impairDiff,
      hasCostWarning: Math.abs(costDiff) > 0.01,
      hasAmortWarning: Math.abs(amortDiff) > 0.01,
      hasImpairWarning: Math.abs(impairDiff) > 0.01,
    }
  })

  // ─── updateCell ────────────────────────────────────────────────────────────

  /**
   * 更新审定表某行某列值，自动重算公式列。
   * block: 'cost'=原值(1701) / 'amort'=摊销(1702) / 'impairment'=减值(1703)
   */
  function updateCell(
    block: I1BlockType,
    rowId: string,
    field: keyof I1AdjudicationRow,
    value: number,
  ): void {
    const rows = block === 'cost'
      ? costRows.value
      : block === 'amort'
        ? amortRows.value
        : impairmentRows.value
    const row = rows.find((r) => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    ;(row as any)[field] = value

    // 自动重算期末余额
    if (block === 'cost') {
      // 资产类(1701)：期末 = 期初 + 增加(借方) - 减少(贷方)
      row.endBalance = calcAssetEndBalance(row.beginBalance, row.increase, row.decrease)
    } else {
      // 备抵类(1702/1703)：期末 = 期初 + 增加(贷方) - 减少(借方)
      row.endBalance = calcContraEndBalance(row.beginBalance, row.decrease, row.increase)
    }

    // 自动重算审定数
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    _persist()
  }

  // ─── Constants for TB writeback ─────────────────────────────────────────────

  const ACCOUNT_CODE_1701 = '1701'
  const ACCOUNT_CODE_1702 = '1702'
  const ACCOUNT_CODE_1703 = '1703'

  // ─── saveAdjudication（持久化 + TB回写 + EventBus）──────────────────────────

  /**
   * 保存审定表并回写TB（Req 2.10）：
   * 1. 持久化三区块行数据到 checklist_responses
   * 2. 持久化审定小计到独立 item_id（render策略回读seed）
   * 3. writebackTrialBalance（科目1701+1702+1703）
   * 4. 发布 'substantive:adjudicated' EventBus事件
   *
   * 铁律：EventBus跨表值必须持久化到checklist_responses(独立item_id)+render策略回读seed
   */
  async function saveAdjudication(): Promise<void> {
    _persist()

    const auditedCost = costSubtotal.value.audited
    const auditedAmort = amortSubtotal.value.audited
    const auditedImpairment = impairmentSubtotal.value.audited

    // 持久化审定小计（独立item_id，供render策略回读seed + 跨session持久化）
    options?.onSave?.(`${ITEM_PREFIX}-audited-cost`, auditedCost)
    options?.onSave?.(`${ITEM_PREFIX}-audited-amort`, auditedAmort)
    options?.onSave?.(`${ITEM_PREFIX}-audited-impairment`, auditedImpairment)
    options?.onSave?.(`${ITEM_PREFIX}-audited-net`, netValueAudited.value)

    // TB回写（科目1701+1702+1703）
    if (projectId.value) {
      try {
        await Promise.all([
          api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
            account_code: ACCOUNT_CODE_1701,
            audited_amount: auditedCost,
          }),
          api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
            account_code: ACCOUNT_CODE_1702,
            audited_amount: auditedAmort,
          }),
          api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
            account_code: ACCOUNT_CODE_1703,
            audited_amount: auditedImpairment,
          }),
        ])
      } catch {
        ElMessage.warning('审定数回写试算表失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus 事件（轻量通知，附注/报表等消费）
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I1',
        accountCodes: [ACCOUNT_CODE_1701, ACCOUNT_CODE_1702, ACCOUNT_CODE_1703],
        auditedCost,
        auditedAmort,
        auditedImpairment,
        netValue: netValueAudited.value,
      },
    }))
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(`${ITEM_PREFIX}-cost-rows`, costRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-amort-rows`, amortRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-impair-rows`, impairmentRows.value.filter((r) => !r.isSubtotal))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    costRows,
    amortRows,
    impairmentRows,
    auditNote,
    auditConclusion,
    // Computed — 小计行
    costSubtotal,
    amortSubtotal,
    impairmentSubtotal,
    // Computed — 净值
    netValueAudited,
    netValueRow,
    // Computed — 三角勾稽
    reconciliationResults,
    isAllReconciled,
    // Computed — TB取数 + 差异
    tbRow,
    differenceRows,
    // Computed — 交叉验证
    crossValidation,
    // Actions
    updateCell,
    saveAdjudication,
    saveNote,
    saveConclusion,
  }
}

export default useI1Adjudication
