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
  calcChangeRate,
} from './useI1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表从 I1-2 带入模式（对齐 H8/H9） */
export type I1FillMode = 'book' | 'full'

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

/** 四、净值（按分类 + 变动额/率，对齐 Excel） */
export interface I1NetValueRow {
  rowId: string
  category: string
  beginNet: number
  endNet: number
  changeAmount: number
  changeRate: number | null
  isSignificant: boolean
  explanation: string
  isSubtotal?: boolean
}

/** Excel 审计说明事项(1)(2)(3) */
export interface I1QualitativeNotes {
  /** (1) 净值重大变动原因（变动率≥30%） */
  fluctuation: string
  /** (2) 使用寿命不确定无形资产的判断依据 */
  indefiniteLife: string
  /** (3) 权属、抵押情况说明 */
  ownershipPledge: string
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

/** 对齐 Excel 审定表分类（含住房使用权/矿产权/数据资源） */
export const I1_DEFAULT_CATEGORIES = [
  '土地使用权',
  '住房使用权',
  '专利权',
  '非专利技术',
  '商标权',
  '著作权',
  '特许经营权',
  '软件',
  '矿产权',
  '数据资源',
  '其他',
] as const

const DEFAULT_COST_CATEGORIES = [...I1_DEFAULT_CATEGORIES]
const DEFAULT_AMORT_CATEGORIES = [...I1_DEFAULT_CATEGORIES]
const DEFAULT_IMPAIRMENT_CATEGORIES = [...I1_DEFAULT_CATEGORIES]

/** 净值变动率阈值（%），对齐 Excel「主要原因」提示 */
export const I1_CHANGE_RATE_THRESHOLD = 30

const ITEM_PREFIX = 'I1-adj'
const ITEM_ID_DETAIL = 'I1-2-rows'
const QUAL_KEY = `${ITEM_PREFIX}-qual-notes`
const NET_EXPLAIN_KEY = `${ITEM_PREFIX}-net-explanations`

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
  /** Excel 说明事项(1)(2)(3) */
  const qualitativeNotes = ref<I1QualitativeNotes>({
    fluctuation: '',
    indefiniteLife: '',
    ownershipPledge: '',
  })
  /** 净值分类变动说明 */
  const changeExplanations = ref<Record<string, string>>({})

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

    const qual = _getJson(QUAL_KEY)
    if (qual && typeof qual === 'object') {
      qualitativeNotes.value = {
        fluctuation: String(qual.fluctuation ?? ''),
        indefiniteLife: String(qual.indefiniteLife ?? ''),
        ownershipPledge: String(qual.ownershipPledge ?? ''),
      }
    }
    const explains = _getJson(NET_EXPLAIN_KEY)
    changeExplanations.value =
      explains && typeof explains === 'object' && !Array.isArray(explains)
        ? { ...explains }
        : {}
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

  const netValueBegin = computed(() =>
    calcNetValue(
      costSubtotal.value.beginBalance,
      amortSubtotal.value.beginBalance,
      impairmentSubtotal.value.beginBalance,
    ),
  )

  /** 净值行对象（用于渲染合计行） */
  const netValueRow = computed<I1AdjudicationRow>(() => ({
    rowId: 'row-net-value',
    category: '无形资产净值合计',
    beginBalance: netValueBegin.value,
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

  /** 四、净值：按分类派生 + 变动额/率（对齐 Excel） */
  const netRows = computed<I1NetValueRow[]>(() => {
    const byCat = (rows: I1AdjudicationRow[]) => {
      const m = new Map<string, I1AdjudicationRow>()
      for (const r of rows.filter((x) => !x.isSubtotal)) m.set(r.category, r)
      return m
    }
    const costs = byCat(costRows.value)
    const amorts = byCat(amortRows.value)
    const impairs = byCat(impairmentRows.value)
    const cats = [
      ...new Set([
        ...costs.keys(),
        ...amorts.keys(),
        ...impairs.keys(),
        ...DEFAULT_COST_CATEGORIES,
      ]),
    ]

    const detail: I1NetValueRow[] = cats.map((cat) => {
      const c = costs.get(cat)
      const a = amorts.get(cat)
      const i = impairs.get(cat)
      const beginNet = calcNetValue(c?.beginBalance ?? 0, a?.beginBalance ?? 0, i?.beginBalance ?? 0)
      const endNet = calcNetValue(c?.audited ?? 0, a?.audited ?? 0, i?.audited ?? 0)
      const changeAmount = endNet - beginNet
      const changeRate = calcChangeRate(endNet, beginNet)
      return {
        rowId: `row-n-${cat}`,
        category: cat,
        beginNet,
        endNet,
        changeAmount,
        changeRate,
        isSignificant: changeRate != null && Math.abs(changeRate) >= I1_CHANGE_RATE_THRESHOLD,
        explanation: changeExplanations.value[cat] || '',
        isSubtotal: false,
      }
    })

    const beginNet = calcSubtotal(detail.map((r) => r.beginNet))
    const endNet = calcSubtotal(detail.map((r) => r.endNet))
    const changeAmount = endNet - beginNet
    const changeRate = calcChangeRate(endNet, beginNet)
    detail.push({
      rowId: 'row-n-subtotal',
      category: '净值合计',
      beginNet,
      endNet,
      changeAmount,
      changeRate,
      isSignificant: changeRate != null && Math.abs(changeRate) >= I1_CHANGE_RATE_THRESHOLD,
      explanation: '',
      isSubtotal: true,
    })
    return detail
  })

  const significantNetChanges = computed(() =>
    netRows.value.filter((r) => !r.isSubtotal && r.isSignificant),
  )

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
    options?.onSave?.(`${ITEM_PREFIX}-cost-increase-total`, costSubtotal.value.increase)
    options?.onSave?.('I1-adjudication-cost-addition-total', costSubtotal.value.increase)
    // 摊销本期增加（贷方计提）合计 → I1-10/11 勾稽
    options?.onSave?.(`${ITEM_PREFIX}-amort-increase-total`, amortSubtotal.value.increase)
    options?.onSave?.('I1-1-amort-provision', amortSubtotal.value.increase)

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
    // 跨表 seed：原值本期增加合计 → I1-5 检查比例分母（及兼容旧 key）
    const costIncreaseTotal = costSubtotal.value.increase
    save(`${ITEM_PREFIX}-cost-increase-total`, costIncreaseTotal)
    save('I1-adjudication-cost-addition-total', costIncreaseTotal)
    // 摊销本期增加（贷方计提）→ I1-10/11 / I1-9 勾稽
    const amortIncreaseTotal = amortSubtotal.value.increase
    save(`${ITEM_PREFIX}-amort-increase-total`, amortIncreaseTotal)
    save('I1-1-amort-provision', amortIncreaseTotal)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function saveQualitativeNotes(): void {
    options?.onSave?.(QUAL_KEY, { ...qualitativeNotes.value })
  }

  function setNetExplanation(category: string, text: string): void {
    changeExplanations.value = { ...changeExplanations.value, [category]: text }
    options?.onSave?.(NET_EXPLAIN_KEY, { ...changeExplanations.value })
  }

  /** 行级变动额/率（期末审定 vs 期初，对齐 Excel 比较列） */
  function rowChange(row: I1AdjudicationRow): { amount: number; rate: number | null; significant: boolean } {
    const amount = row.audited - row.beginBalance
    const rate = calcChangeRate(row.audited, row.beginBalance)
    return {
      amount,
      rate,
      significant: rate != null && Math.abs(rate) >= I1_CHANGE_RATE_THRESHOLD,
    }
  }

/** 从 I1-2 按分类聚合带入期初/增加/减少/期末/未审 */
  /**
   * 从 I1-2 按分类聚合带入期初/增加/减少/期末/未审。
   * mode=book：写入未审数，保留已有 AJE/RJE（留给 I1-3）。
   * mode=full：写入明细审定数并清零 AJE/RJE。
   */
  function fillFromDetail(mode: I1FillMode = 'book'): { ok: boolean; message: string; count: number } {
    const item = allResponses.value.get(ITEM_ID_DETAIL)
    const raw = item?.remark ?? item?.conclusion
    if (!raw) return { ok: false, message: 'I1-2 明细表暂无数据', count: 0 }
    let detail: any[] = []
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      detail = Array.isArray(parsed) ? parsed : []
    } catch {
      return { ok: false, message: 'I1-2 数据解析失败', count: 0 }
    }
    if (!detail.length) return { ok: false, message: 'I1-2 明细表暂无数据', count: 0 }

    type Agg = {
      costBegin: number; costInc: number; costDec: number; costEnd: number
      amortBegin: number; amortInc: number; amortDec: number; amortEnd: number
      impairBegin: number; impairInc: number; impairDec: number; impairEnd: number
    }
    const map = new Map<string, Agg>()
    const ensure = (cat: string) => {
      if (!map.has(cat)) {
        map.set(cat, {
          costBegin: 0, costInc: 0, costDec: 0, costEnd: 0,
          amortBegin: 0, amortInc: 0, amortDec: 0, amortEnd: 0,
          impairBegin: 0, impairInc: 0, impairDec: 0, impairEnd: 0,
        })
      }
      return map.get(cat)!
    }

    const useAudited = mode === 'full'
    for (const d of detail) {
      const cat = String(d.category || d.type || '其他').trim() || '其他'
      const a = ensure(cat)
      if (useAudited) {
        a.costBegin += Number(d.auditedCostBegin ?? d.costBegin) || 0
        a.costInc += Number(d.auditedCostIncrease ?? d.costIncrease) || 0
        a.costDec += Number(d.auditedCostDecrease ?? d.costDecrease) || 0
        a.costEnd += Number(d.auditedCostEnd ?? d.costEnd) || 0
        a.amortBegin += Number(d.auditedAccAmortBegin ?? d.accAmortBegin) || 0
        a.amortInc += Number(d.auditedAmortIncrease ?? d.amortProvision) || 0
        a.amortDec += Number(d.auditedAmortDecrease ?? d.amortTransferOut) || 0
        a.amortEnd += Number(d.auditedAccAmortEnd ?? d.accAmortEnd) || 0
        a.impairBegin += Number(d.auditedImpairmentBegin ?? d.impairmentBegin) || 0
        a.impairInc += Number(d.auditedImpairmentIncrease ?? d.impairmentProvision) || 0
        a.impairDec += Number(d.auditedImpairmentDecrease ?? d.impairmentReversal) || 0
        a.impairEnd += Number(d.auditedImpairmentEnd ?? d.impairmentEnd) || 0
      } else {
        a.costBegin += Number(d.costBegin) || 0
        a.costInc += Number(d.costIncrease) || 0
        a.costDec += Number(d.costDecrease) || 0
        a.costEnd += Number(d.costEnd) || 0
        a.amortBegin += Number(d.accAmortBegin) || 0
        a.amortInc += Number(d.amortProvision) || 0
        a.amortDec += Number(d.amortTransferOut) || 0
        a.amortEnd += Number(d.accAmortEnd) || 0
        a.impairBegin += Number(d.impairmentBegin) || 0
        a.impairInc += Number(d.impairmentProvision) || 0
        a.impairDec += Number(d.impairmentReversal) || 0
        a.impairEnd += Number(d.impairmentEnd) || 0
      }
    }

    const applyBlock = (
      block: I1BlockType,
      pick: (a: Agg) => { begin: number; inc: number; dec: number; end: number },
    ) => {
      const rows = block === 'cost' ? costRows : block === 'amort' ? amortRows : impairmentRows
      const byCat = new Map(rows.value.filter((r) => !r.isSubtotal).map((r) => [r.category, r]))
      for (const [cat, agg] of map) {
        const vals = pick(agg)
        let row = byCat.get(cat)
        if (!row) {
          const prefix = block === 'cost' ? 'c' : block === 'amort' ? 'a' : 'i'
          row = {
            rowId: `row-${prefix}-${cat}`,
            category: cat,
            beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
            unadjusted: 0, aje: 0, rje: 0, audited: 0,
            isSubtotal: false, isEditable: true,
          }
          rows.value = [...rows.value.filter((r) => !r.isSubtotal), row]
          byCat.set(cat, row)
        }
        row.beginBalance = vals.begin
        row.increase = vals.inc
        row.decrease = vals.dec
        row.endBalance = vals.end
        row.unadjusted = vals.end
        if (mode === 'full') {
          row.aje = 0
          row.rje = 0
        }
        row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      }
    }

    applyBlock('cost', (a) => ({ begin: a.costBegin, inc: a.costInc, dec: a.costDec, end: a.costEnd }))
    applyBlock('amort', (a) => ({ begin: a.amortBegin, inc: a.amortInc, dec: a.amortDec, end: a.amortEnd }))
    applyBlock('impairment', (a) => ({ begin: a.impairBegin, inc: a.impairInc, dec: a.impairDec, end: a.impairEnd }))

    _persist()
    const modeLabel = mode === 'full' ? '审定覆盖（已清零 AJE/RJE）' : '未审带入（保留 AJE/RJE）'
    return { ok: true, message: `已从 I1-2 按 ${map.size} 个分类${modeLabel}`, count: map.size }
  }

  /** @deprecated 请用 fillFromDetail('book') */
  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    return fillFromDetail('book')
  }

  /** Excel 结论模板 A/B/C */
  function applyConclusionTemplate(kind: 'A' | 'B' | 'C'): string {
    const net = netValueAudited.value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    const templates: Record<'A' | 'B' | 'C', string> = {
      A: `经审计，无形资产及相关备抵科目（累计摊销、减值准备）在所有重大方面公允反映，三角勾稽与试算平衡表核对一致，审定净值 ${net} 元。未见重大异常。`,
      B: `经审计，无形资产及相关备抵科目在实施审计调整后，在所有重大方面公允反映。调整事项详见 I1-3；审定净值 ${net} 元。`,
      C: `经审计，无形资产及相关备抵科目存在尚未消除的重大错报/勾稽差异（详见本表勾稽校验与说明事项），审定净值 ${net} 元尚不能作为报表列报依据，须进一步追查并调整。`,
    }
    const text = templates[kind]
    saveConclusion(text)
    return text
  }

  function draftFluctuationNote(): string {
    const sig = significantNetChanges.value
    if (!sig.length) return '本期各分类净值变动率均未超过 30%，无重大波动须专项说明。'
    return sig
      .map((r) => `「${r.category}」变动额 ${r.changeAmount.toFixed(2)}、变动率 ${r.changeRate?.toFixed(1)}%${r.explanation ? `：${r.explanation}` : '（待补充原因）'}`)
      .join('；')
  }

  /** 从 I1-7 不确定寿命清单/检查行汇总说明事项(2)草稿 */
  function draftIndefiniteLifeNote(): string {
    const pubRaw = allResponses.value.get('I1-7-indefinite-list')?.remark
      ?? allResponses.value.get('I1-7-indefinite-list')?.conclusion
    if (pubRaw) {
      try {
        const parsed = typeof pubRaw === 'string' ? JSON.parse(pubRaw) : pubRaw
        const assets = Array.isArray(parsed?.assets) ? parsed.assets : []
        if (assets.length) {
          return assets
            .map((a: any) => {
              const name = String(a.name || '未命名')
              const basis = String(a.judgmentBasis || '').trim()
              const nbv = a.netBookValue != null ? Number(a.netBookValue) : null
              const nbvPart = nbv != null && Number.isFinite(nbv) ? `，账面净值 ${nbv.toFixed(2)}` : ''
              return basis
                ? `「${name}」${nbvPart}：${basis}`
                : `「${name}」${nbvPart}：判断依据待补充（详见 I1-7）`
            })
            .join('；')
        }
      } catch { /* fall through */ }
    }

    const rowsRaw = allResponses.value.get('I1-7-rows')?.remark
      ?? allResponses.value.get('I1-7-rows')?.conclusion
    if (rowsRaw) {
      try {
        const rows = typeof rowsRaw === 'string' ? JSON.parse(rowsRaw) : rowsRaw
        if (Array.isArray(rows)) {
          const indef = rows.filter((r: any) =>
            r.isIndefinite === 'Y' || r.isIndefinite === true || Number(r.usefulLifeMonths) <= 0,
          )
          if (indef.length) {
            return indef
              .map((r: any) => {
                const name = String(r.name || '未命名')
                const basis = String(r.indefiniteJudgmentBasis || r.judgmentBasis || '').trim()
                return basis
                  ? `「${name}」：${basis}`
                  : `「${name}」：判断依据待补充（详见 I1-7）`
              })
              .join('；')
          }
        }
      } catch { /* ignore */ }
    }
    return '本期未见使用寿命不确定的无形资产；如有，请在 I1-7 完成判定与询问后再带回。'
  }

  function _round2(n: number): number {
    return Math.round((n || 0) * 100) / 100
  }

  /** 按未审权重分摊 AJE 或 RJE 到分类明细行 */
  function _allocateAdjField(
    details: I1AdjudicationRow[],
    field: 'aje' | 'rje',
    net: number,
  ): void {
    if (!details.length) return
    if (Math.abs(net) < 0.005) {
      for (const r of details) {
        r[field] = 0
        r.audited = calcAuditedAmount(r.unadjusted, r.aje, r.rje)
      }
      return
    }
    const weights = details.map((r) => Math.abs(r.unadjusted) || 0)
    const weightSum = weights.reduce((s, w) => s + w, 0)
    let allocated = 0
    details.forEach((r, i) => {
      if (i === details.length - 1) {
        r[field] = _round2(net - allocated)
      } else if (weightSum < 0.005) {
        const each = _round2(net / details.length)
        r[field] = each
        allocated = _round2(allocated + each)
      } else {
        const share = _round2((net * weights[i]) / weightSum)
        r[field] = share
        allocated = _round2(allocated + share)
      }
      r.audited = calcAuditedAmount(r.unadjusted, r.aje, r.rje)
    })
  }

  /**
   * 从 I1-3 回写 AJE/RJE 到三区块（按未审权重分摊）。
   * 原值(1701)：净额=借−贷；摊销/减值(1702/1703)备抵：写入 −(借−贷)，使贷方计提增加审定余额。
   */
  function syncAjeRjeFromI13(nets?: {
    costAje?: number
    costRje?: number
    amortAje?: number
    amortRje?: number
    impairAje?: number
    impairRje?: number
  }): { applied: boolean; message: string } {
    const readNum = (key: string) => Number(allResponses.value.get(key)?.remark) || 0
    let costAje = nets?.costAje
    let costRje = nets?.costRje
    let amortAje = nets?.amortAje
    let amortRje = nets?.amortRje
    let impairAje = nets?.impairAje
    let impairRje = nets?.impairRje

    const needRead = ![costAje, costRje, amortAje, amortRje, impairAje, impairRje]
      .every((n) => n != null && Number.isFinite(Number(n)))

    if (needRead) {
      costAje = readNum('I1-3-cost-aje-net')
      costRje = readNum('I1-3-cost-rje-net')
      amortAje = readNum('I1-3-amort-aje-net')
      amortRje = readNum('I1-3-amort-rje-net')
      impairAje = readNum('I1-3-impair-aje-net')
      impairRje = readNum('I1-3-impair-rje-net')

      const adjRowsRaw = allResponses.value.get('I1-3-rows')?.remark
      if (adjRowsRaw) {
        try {
          const adjRows = typeof adjRowsRaw === 'string' ? JSON.parse(adjRowsRaw) : adjRowsRaw
          if (Array.isArray(adjRows) && adjRows.length) {
            costAje = 0; costRje = 0; amortAje = 0; amortRje = 0; impairAje = 0; impairRje = 0
            for (const r of adjRows) {
              const code = String(r.accountCode || '')
              const debit = Number(r.debitAmount ?? r.debit) || 0
              const credit = Number(r.creditAmount ?? r.credit) || 0
              const net = debit - credit
              const isRje =
                r.category === '报表调整'
                || String(r.entryType || '').toUpperCase() === 'RJE'
              if (code === '1701' || code.startsWith('1701')) {
                if (isRje) costRje += net
                else costAje += net
              } else if (code === '1702' || code.startsWith('1702')) {
                if (isRje) amortRje += net
                else amortAje += net
              } else if (code === '1703' || code.startsWith('1703')) {
                if (isRje) impairRje += net
                else impairAje += net
              }
            }
          }
        } catch { /* keep key values */ }
      }
    }

    const cA = Number(costAje) || 0
    const cR = Number(costRje) || 0
    // 备抵：分录净额借−贷；贷方计提应增加审定余额 → 取反
    const aA = -(Number(amortAje) || 0)
    const aR = -(Number(amortRje) || 0)
    const iA = -(Number(impairAje) || 0)
    const iR = -(Number(impairRje) || 0)

    const totalAbs = Math.abs(cA) + Math.abs(cR) + Math.abs(aA) + Math.abs(aR) + Math.abs(iA) + Math.abs(iR)
    if (totalAbs < 0.005) {
      return { applied: false, message: 'I1-3 暂无 1701/1702/1703 调整净额' }
    }

    _allocateAdjField(costRows.value.filter((r) => !r.isSubtotal), 'aje', cA)
    _allocateAdjField(costRows.value.filter((r) => !r.isSubtotal), 'rje', cR)
    _allocateAdjField(amortRows.value.filter((r) => !r.isSubtotal), 'aje', aA)
    _allocateAdjField(amortRows.value.filter((r) => !r.isSubtotal), 'rje', aR)
    _allocateAdjField(impairmentRows.value.filter((r) => !r.isSubtotal), 'aje', iA)
    _allocateAdjField(impairmentRows.value.filter((r) => !r.isSubtotal), 'rje', iR)
    _persist()

    return {
      applied: true,
      message:
        `已从 I1-3 回写：1701 AJE ${cA.toLocaleString('zh-CN')} / RJE ${cR.toLocaleString('zh-CN')}；`
        + `1702 AJE ${aA.toLocaleString('zh-CN')}；1703 AJE ${iA.toLocaleString('zh-CN')}`,
    }
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
    qualitativeNotes,
    // Computed — 小计行
    costSubtotal,
    amortSubtotal,
    impairmentSubtotal,
    // Computed — 净值
    netValueAudited,
    netValueBegin,
    netValueRow,
    netRows,
    significantNetChanges,
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
    saveQualitativeNotes,
    setNetExplanation,
    rowChange,
    seedFromDetail,
    fillFromDetail,
    applyConclusionTemplate,
    draftFluctuationNote,
    draftIndefiniteLifeNote,
    syncAjeRjeFromI13,
    CHANGE_RATE_THRESHOLD: I1_CHANGE_RATE_THRESHOLD,
  }
}

export default useI1Adjudication
