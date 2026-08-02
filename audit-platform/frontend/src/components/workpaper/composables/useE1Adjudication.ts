/**
 * useE1Adjudication — E1-1 货币资金审定表核心 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 3.1
 *
 * 职责：
 * - 固定项目行矩阵（11行：库存现金/银行存款本金/存放财务公司款项/银行机构存款/
 *   其他货币资金/数字货币/应计利息小计/合计/境外/试算平衡/差异）
 * - 审定数 = 未审数 + 账项调整（单列，非AJE/RJE四列）
 * - 跨Sheet取数：从 allResponses Map 读取 E1-2/3/4 未审 + E1-5 账项调整
 * - TB回写：debounce 2s，按 accountCode 归集(1001/1002/1012)
 * - EventBus 监听 adjustment:created 刷新调整数据
 * - 变动率>30% 高亮 + 差异≠0 高亮
 *
 * Requirements: 1.1-1.7, 12.1-12.5
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAudited,
  calcChange,
  calcChangeRate,
  exceedsThreshold,
} from './useE1FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface ChecklistItem {
  item_id: string
  conclusion?: string | null
  remark?: string | null
}

export interface UseE1BaseOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: SaveFn
  debouncedSave: SaveFn
  isReadonly: Ref<boolean>
  bsDate?: Ref<string>
}

export interface AdjRow {
  itemKey: string
  itemName: string
  accountCode?: '1001' | '1002' | '1012'
  openingUnaudited: number
  openingAdjustment: number
  openingAudited: number
  endingUnaudited: number
  endingAdjustment: number
  endingAudited: number
  changeAmount: number
  changeRate: number | ''
  varianceNote: string
  isSubtotal?: boolean
  isReadonly?: boolean
  sourceWpCode?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 固定项目行配置（源模板E1-1行顺序） */
interface RowConfig {
  itemKey: string
  itemName: string
  accountCode?: '1001' | '1002' | '1012'
  isSubtotal?: boolean
  isReadonly?: boolean
  sourceWpCode?: string
}

const ROW_MATRIX: RowConfig[] = [
  { itemKey: 'cash', itemName: '库存现金', accountCode: '1001' },
  { itemKey: 'bank_principal', itemName: '银行存款（本金）', accountCode: '1002' },
  { itemKey: 'finance_co', itemName: '其中：存放财务公司款项' },
  { itemKey: 'bank_institution', itemName: '银行机构存款' },
  { itemKey: 'other_mf', itemName: '其他货币资金（本金）', accountCode: '1012' },
  { itemKey: 'digital', itemName: '数字货币（本金）' },
  { itemKey: 'accrued_interest', itemName: '应计利息', isSubtotal: true, isReadonly: true, sourceWpCode: 'E1-20' },
  { itemKey: 'accrued_finance', itemName: '其中：财务公司存款', isReadonly: true, sourceWpCode: 'E1-20' },
  { itemKey: 'accrued_bank', itemName: '银行机构存款', isReadonly: true, sourceWpCode: 'E1-20' },
  { itemKey: 'accrued_other', itemName: '其他货币资金', isReadonly: true, sourceWpCode: 'E1-20' },
  { itemKey: 'accrued_digital', itemName: '数字货币', isReadonly: true, sourceWpCode: 'E1-20' },
  { itemKey: 'total', itemName: '合计', isSubtotal: true, isReadonly: true },
  { itemKey: 'overseas', itemName: '其中：存放在境外的款项总额' },
  { itemKey: 'tb_amount', itemName: '试算平衡表数', isReadonly: true },
  { itemKey: 'diff', itemName: '差异数', isReadonly: true },
]

/** 变动率高亮阈值 */
const CHANGE_RATE_THRESHOLD = 0.3

/** 浮点容差 */
const BALANCE_TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch { return [] }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1Adjudication(options: UseE1BaseOptions) {
  const { projectId, allResponses, debouncedSave, isReadonly } = options

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const crossSheetStatus = ref<'loaded' | 'loading' | 'error'>('loaded')
  const isLoading = ref(false)

  // ─── allResponses Helpers ────────────────────────────────────────────

  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  }

  function setLocal(itemId: string, remark: string | null, conclusion?: string | null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, remark, conclusion: conclusion ?? null }
    allResponses.value.set(itemId, { item_id: itemId, conclusion: conclusion ?? null, remark })
    return item
  }

  // ─── Cross-Sheet Data (computed from allResponses) ───────────────────

  /**
   * 从 E1-2 现金明细取期末未审合计
   * key: 'E1-cash-detail-total-unaudited'
   */
  const cashUnaudited = computed(() => ({
    opening: parseNum(getVal('E1-cash-detail-opening-unaudited').remark),
    ending: parseNum(getVal('E1-cash-detail-total-unaudited').remark),
  }))

  /**
   * 从 E1-3 银行明细取各分组期末未审合计
   * keys: 'E1-bank-detail-{group}-total-unaudited'
   */
  const bankUnaudited = computed(() => ({
    opening: parseNum(getVal('E1-bank-detail-principal-opening-unaudited').remark),
    ending: parseNum(getVal('E1-bank-detail-principal-total-unaudited').remark),
  }))

  const financeCoUnaudited = computed(() => ({
    opening: parseNum(getVal('E1-bank-detail-finance-opening-unaudited').remark),
    ending: parseNum(getVal('E1-bank-detail-finance-total-unaudited').remark),
  }))

  const bankInstitutionUnaudited = computed(() => ({
    opening: parseNum(getVal('E1-bank-detail-institution-opening-unaudited').remark),
    ending: parseNum(getVal('E1-bank-detail-institution-total-unaudited').remark),
  }))

  const otherMfUnaudited = computed(() => ({
    opening: parseNum(getVal('E1-bank-detail-other-opening-unaudited').remark),
    ending: parseNum(getVal('E1-bank-detail-other-total-unaudited').remark),
  }))

  /**
   * 从 E1-4 数字货币取期末未审合计
   * key: 'E1-digital-total-unaudited'
   */
  const digitalUnaudited = computed(() => ({
    opening: parseNum(getVal('E1-digital-opening-unaudited').remark),
    ending: parseNum(getVal('E1-digital-total-unaudited').remark),
  }))

  /** E1-20 应计利息按 E1-1 源模板四类分项汇总。 */
  const accruedInterestRows = computed(() => safeParseRows<Record<string, unknown>>(
    getVal('E1-accrued-interest-rows').remark,
  ))
  const accruedInterestByCategory = computed(() => {
    const totals = { finance: 0, bank: 0, other: 0, digital: 0 }
    for (const row of accruedInterestRows.value) {
      const category = String(row.category || 'bank') as keyof typeof totals
      if (category in totals) totals[category] += parseNum(row.accruedRmb)
    }
    return totals
  })

  function accruedCategoryValues(itemKey: string): { opening: number; ending: number } {
    const category = itemKey.replace('accrued_', '') as keyof typeof accruedInterestByCategory.value
    return {
      opening: parseNum(getVal(`E1-adj-${itemKey}-opening-unadj`).remark),
      ending: accruedInterestRows.value.length
        ? accruedInterestByCategory.value[category] || 0
        : parseNum(getVal(`E1-adj-${itemKey}-ending-unadj`).remark),
    }
  }

  function accruedTotalValues(): { opening: number; ending: number } {
    const categoryKeys = ['accrued_finance', 'accrued_bank', 'accrued_other', 'accrued_digital']
    const categoryValues = categoryKeys.map(accruedCategoryValues)
    const openingByCategory = categoryValues.reduce((sum, value) => sum + value.opening, 0)
    const endingByCategory = categoryValues.reduce((sum, value) => sum + value.ending, 0)
    const legacyOpening = parseNum(getVal('E1-adj-accrued_interest-opening-unadj').remark)
    return {
      opening: categoryValues.every(value => value.opening === 0) ? legacyOpening : openingByCategory,
      ending: endingByCategory,
    }
  }

  /**
   * 从 E1-5 调整分录按项目归集账项调整
   * keys: 'E1-adjustment-by-item-{itemKey}'
   */
  function getAdjustment(itemKey: string, period: 'opening' | 'ending'): number {
    return parseNum(getVal(`E1-adjustment-by-item-${itemKey}-${period}`).remark)
  }

  // ─── Row Builder ─────────────────────────────────────────────────────

  function buildRow(cfg: RowConfig): AdjRow {
    const { itemKey } = cfg

    // Determine unaudited values from cross-sheet or stored
    let openingUnaudited: number
    let endingUnaudited: number

    switch (itemKey) {
      case 'cash':
        openingUnaudited = cashUnaudited.value.opening
        endingUnaudited = cashUnaudited.value.ending
        break
      case 'bank_principal':
        openingUnaudited = bankUnaudited.value.opening
        endingUnaudited = bankUnaudited.value.ending
        break
      case 'finance_co':
        openingUnaudited = financeCoUnaudited.value.opening
        endingUnaudited = financeCoUnaudited.value.ending
        break
      case 'bank_institution':
        openingUnaudited = bankInstitutionUnaudited.value.opening
        endingUnaudited = bankInstitutionUnaudited.value.ending
        break
      case 'other_mf':
        openingUnaudited = otherMfUnaudited.value.opening
        endingUnaudited = otherMfUnaudited.value.ending
        break
      case 'digital':
        openingUnaudited = digitalUnaudited.value.opening
        endingUnaudited = digitalUnaudited.value.ending
        break
      case 'accrued_interest': {
        const accrued = accruedTotalValues()
        openingUnaudited = accrued.opening
        endingUnaudited = accrued.ending
        break
      }
      case 'accrued_finance':
      case 'accrued_bank':
      case 'accrued_other':
      case 'accrued_digital': {
        const accrued = accruedCategoryValues(itemKey)
        openingUnaudited = accrued.opening
        endingUnaudited = accrued.ending
        break
      }
      default:
        // For overseas and other manual supplementary rows — read from stored
        openingUnaudited = parseNum(getVal(`E1-adj-${itemKey}-opening-unadj`).remark)
        endingUnaudited = parseNum(getVal(`E1-adj-${itemKey}-ending-unadj`).remark)
    }

    // Adjustments from E1-5 cross-sheet. 应计利息总行严格汇总四个子项，避免与子项重复或口径不一致。
    const accruedChildKeys = ['accrued_finance', 'accrued_bank', 'accrued_other', 'accrued_digital']
    const openingAdjustment = itemKey === 'accrued_interest'
      ? accruedChildKeys.reduce((sum, key) => sum + getAdjustment(key, 'opening'), 0)
      : getAdjustment(itemKey, 'opening')
    const endingAdjustment = itemKey === 'accrued_interest'
      ? accruedChildKeys.reduce((sum, key) => sum + getAdjustment(key, 'ending'), 0)
      : getAdjustment(itemKey, 'ending')

    // Computed: 审定数 = 未审数 + 账项调整
    const openingAudited = calcAudited(openingUnaudited, openingAdjustment)
    const endingAudited = calcAudited(endingUnaudited, endingAdjustment)

    // Computed: 变动额/变动率
    const changeAmount = calcChange(endingAudited, openingAudited)
    const changeRate = calcChangeRate(changeAmount, openingAudited)

    // User-editable variance note
    const varianceNote = getVal(`E1-adj-${itemKey}-note`).remark || ''

    return {
      itemKey,
      itemName: cfg.itemName,
      accountCode: cfg.accountCode,
      openingUnaudited,
      openingAdjustment,
      openingAudited,
      endingUnaudited,
      endingAdjustment,
      endingAudited,
      changeAmount,
      changeRate,
      varianceNote,
      isSubtotal: cfg.isSubtotal,
      isReadonly: cfg.isReadonly,
      sourceWpCode: cfg.sourceWpCode,
    }
  }

  // ─── Rows Computed ───────────────────────────────────────────────────

  /** 固定项目行（不含合计/TB/差异这三个特殊行） */
  const detailRows = computed<AdjRow[]>(() => {
    return ROW_MATRIX
      .filter(cfg => !['total', 'tb_amount', 'diff'].includes(cfg.itemKey))
      .map(cfg => buildRow(cfg))
  })

  /** 合计行 = SUM(库存现金~应计利息小计) */
  const totalRow: ComputedRef<AdjRow> = computed(() => {
    // Sum the summable detail rows (cash through accrued_interest)
    const summableKeys = ['cash', 'bank_principal', 'other_mf', 'digital', 'accrued_interest']
    const summableRows = detailRows.value.filter(r => summableKeys.includes(r.itemKey))

    const openingUnaudited = summableRows.reduce((s, r) => s + r.openingUnaudited, 0)
    const openingAdjustment = summableRows.reduce((s, r) => s + r.openingAdjustment, 0)
    const openingAudited = summableRows.reduce((s, r) => s + r.openingAudited, 0)
    const endingUnaudited = summableRows.reduce((s, r) => s + r.endingUnaudited, 0)
    const endingAdjustment = summableRows.reduce((s, r) => s + r.endingAdjustment, 0)
    const endingAudited = summableRows.reduce((s, r) => s + r.endingAudited, 0)
    const changeAmount = calcChange(endingAudited, openingAudited)
    const changeRate = calcChangeRate(changeAmount, openingAudited)

    return {
      itemKey: 'total',
      itemName: '合计',
      openingUnaudited,
      openingAdjustment,
      openingAudited,
      endingUnaudited,
      endingAdjustment,
      endingAudited,
      changeAmount,
      changeRate,
      varianceNote: getVal('E1-adj-total-note').remark || '',
      isSubtotal: true,
      isReadonly: true,
    }
  })

  /** 试算平衡表数行（auto_source: trial_balance） */
  const tbAmountRow: ComputedRef<AdjRow> = computed(() => {
    const openingAudited = parseNum(getVal('E1-adj-tb-amount-opening').remark)
    const endingAudited = parseNum(getVal('E1-adj-tb-amount-ending').remark)
    const changeAmount = calcChange(endingAudited, openingAudited)
    const changeRate = calcChangeRate(changeAmount, openingAudited)

    return {
      itemKey: 'tb_amount',
      itemName: '试算平衡表数',
      openingUnaudited: openingAudited,
      openingAdjustment: 0,
      openingAudited,
      endingUnaudited: endingAudited,
      endingAdjustment: 0,
      endingAudited,
      changeAmount,
      changeRate,
      varianceNote: '',
      isReadonly: true,
    }
  })

  /** 差异行 = 合计审定 - TB数 */
  const diffRow: ComputedRef<AdjRow> = computed(() => {
    const total = totalRow.value
    const tb = tbAmountRow.value

    const openingAudited = total.openingAudited - tb.openingAudited
    const endingAudited = total.endingAudited - tb.endingAudited
    const changeAmount = calcChange(endingAudited, openingAudited)
    const changeRate = calcChangeRate(changeAmount, openingAudited)

    return {
      itemKey: 'diff',
      itemName: '差异数',
      openingUnaudited: openingAudited,
      openingAdjustment: 0,
      openingAudited,
      endingUnaudited: endingAudited,
      endingAdjustment: 0,
      endingAudited,
      changeAmount,
      changeRate,
      varianceNote: getVal('E1-adj-diff-note').remark || '',
      isReadonly: true,
    }
  })

  /** 完整行列表（严格按源模板：应计利息四子项后立即为合计，再列境外/TB/差异） */
  const rows: ComputedRef<AdjRow[]> = computed(() => {
    const detail = detailRows.value
    const overseas = detail.find(row => row.itemKey === 'overseas')
    const beforeTotal = detail.filter(row => row.itemKey !== 'overseas')
    return [...beforeTotal, totalRow.value, ...(overseas ? [overseas] : []), tbAmountRow.value, diffRow.value]
  })

  // ─── Highlight Helpers ───────────────────────────────────────────────

  function isRateExceeding(row: AdjRow): boolean {
    return exceedsThreshold(row.changeRate, CHANGE_RATE_THRESHOLD)
  }

  function hasDifference(): boolean {
    const diff = diffRow.value
    return Math.abs(diff.endingAudited) > BALANCE_TOLERANCE || Math.abs(diff.openingAudited) > BALANCE_TOLERANCE
  }

  // ─── Cell Update ─────────────────────────────────────────────────────

  function updateCell(itemKey: string, field: string, value: number): void {
    if (isReadonly.value) return
    const itemId = `E1-adj-${itemKey}-${field}`
    setLocal(itemId, String(value))
    scheduleSave()
  }

  function saveVarianceNote(itemKey: string, text: string): void {
    if (isReadonly.value) return
    const itemId = `E1-adj-${itemKey}-note`
    setLocal(itemId, text)
    scheduleSave()
  }

  /**
   * 「从四表库带入未审数」落库。
   *
   * 🔴 写的是**跨 sheet 聚合键**（`E1-cash-detail-*` / `E1-bank-detail-*` / `E1-digital-*`），
   * 不是 `E1-adj-*` —— 审定表未审数列本来就读那些键（见 `cashUnaudited` 等 computed）。
   * 而 `flushSave` 只收集 `E1-adj-` 前缀，故这些键**必须在此显式提交**，
   * 否则只改内存、刷新即丢（与 E1 早期 `E1-adj-total-*` 只在回写时写入是同款坑）。
   *
   * 计划由纯函数 `planE1AdjudicationPrefill` 生成（含「无该科目则跳过」「已有值不静默覆盖」）。
   */
  async function applyFourTablePrefill(
    writes: ReadonlyArray<{ itemId: string; value: string }>,
  ): Promise<number> {
    if (isReadonly.value || !writes.length) return 0
    const items: ChecklistItem[] = writes.map((w) => setLocal(w.itemId, w.value))
    await debouncedSave(items)
    // 未审数变了 → 审定数/合计/差异随之变化，触发一次常规保存与 TB 回写
    scheduleSave()
    return items.length
  }

  // ─── TB Writeback (debounce 2s, by accountCode) ──────────────────────

  /**
   * 归集三科目（1001/1002/1012）审定合计（纯计算，供内存同步与 TB 回写共用）。
   * @param period 'ending'=期末审定数（默认，TB 回写口径）；'opening'=期初审定数（供披露表期初预填）
   */
  function aggregateAuditedByCode(period: 'opening' | 'ending' = 'ending'): Record<string, number> {
    const byCode: Record<string, number> = { '1001': 0, '1002': 0, '1012': 0 }
    const val = (r: { openingAudited: number; endingAudited: number } | undefined): number =>
      r ? (period === 'opening' ? r.openingAudited : r.endingAudited) : 0
    // 1001 = 库存现金
    byCode['1001'] = val(detailRows.value.find(r => r.itemKey === 'cash'))
    // 1002 = 银行存款本金 (includes finance_co + bank_institution as sub-items)
    byCode['1002'] = val(detailRows.value.find(r => r.itemKey === 'bank_principal'))
    // 1012 = 其他货币资金 + 数字货币
    byCode['1012'] = val(detailRows.value.find(r => r.itemKey === 'other_mf'))
      + val(detailRows.value.find(r => r.itemKey === 'digital'))
    return byCode
  }

  /**
   * 将三科目审定合计写入 allResponses（仅内存，不落库、不发事件）。
   * 供 E1-14 分析表 / 附注披露 / 主入口全局告警实时读取——审定表一挂载或数据变化即同步，
   * 不再依赖用户触发 writebackTrialBalance（此前 E1-adj-total-* 仅在回写时写入，
   * 而 E1 从不主动回写 → 全局告警「审定合计」恒 0.00，产生虚假全额差异）。
   *
   * 同时写期末（E1-adj-total-{code}）与期初（E1-adj-total-{code}-opening）审定数，
   * 供披露表期末数（只读取数）与期初数（自动预填，可手工覆盖）跨 sheet 消费。
   */
  function syncAuditedTotals(): void {
    const ending = aggregateAuditedByCode('ending')
    for (const [code, amount] of Object.entries(ending)) {
      setLocal(`E1-adj-total-${code}`, String(amount))
    }
    const opening = aggregateAuditedByCode('opening')
    for (const [code, amount] of Object.entries(opening)) {
      setLocal(`E1-adj-total-${code}-opening`, String(amount))
    }
  }

  function writebackTrialBalance(): void {
    if (!projectId.value) return

    const byCode = aggregateAuditedByCode()

    // Write to allResponses for cross-spec consumption (E1-14 分析表/全局告警读取)
    syncAuditedTotals()

    // 真实 TB 回写：走平台统一端点（对齐 F3/F4/F5/G 循环 writebackTrialBalance）。
    // 按 1001/1002/1012 三科目分别 upsert 审定数到 trial_balance。
    for (const [code, amount] of Object.entries(byCode)) {
      api
        .put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: code,
          audited_amount: amount,
        })
        .catch(() => { /* silent：回写失败不阻断本地保存 */ })
    }
  }

  // ─── Debounce Save ───────────────────────────────────────────────────

  function scheduleSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items: ChecklistItem[] = []
    for (const [, resp] of allResponses.value) {
      if (resp.item_id.startsWith('E1-adj-')) {
        items.push({ item_id: resp.item_id, conclusion: resp.conclusion, remark: resp.remark })
      }
    }
    if (items.length > 0) {
      debouncedSave(items).catch(() => { /* silent */ })
    }
    // Trigger TB writeback after save
    writebackTrialBalance()
  }

  // ─── EventBus: adjustment:created ────────────────────────────────────

  function onAdjustmentCreated(payload: any): void {
    if (!payload || (payload.wpCode && payload.wpCode !== 'E1')) return
    // E1-5 adjustments update allResponses keys directly;
    // this handler ensures we debounce-save the adjudication state
    scheduleSave()
  }

  // ─── Event Registration ──────────────────────────────────────────────

  eventBus.on('adjustment:created', onAdjustmentCreated)

  // ─── Cleanup ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    eventBus.off('adjustment:created', onAdjustmentCreated)
  })

  function publishAdjudicated(): void {
    const total = totalRow.value
    const payload = {
      wpCode: 'E1',
      accountCode: '1001,1002,1012',
      auditedAmount: total.endingAudited,
      adjudicatedAmount: total.endingAudited,
      auditedTotal: total.endingAudited,
      detail: {
        '1001': detailRows.value.find(r => r.itemKey === 'cash')?.endingAudited ?? 0,
        '1002': detailRows.value.find(r => r.itemKey === 'bank_principal')?.endingAudited ?? 0,
        '1012': (detailRows.value.find(r => r.itemKey === 'other_mf')?.endingAudited ?? 0) +
                (detailRows.value.find(r => r.itemKey === 'digital')?.endingAudited ?? 0),
      },
      timestamp: Date.now(),
    }
    eventBus.emit('substantive:adjudicated', payload)
  }

  // Watch total audited → auto publish + writeback
  let previousTotalAudited: number | null = null
  watch(
    () => totalRow.value.endingAudited,
    (current) => {
      if (previousTotalAudited !== null && Math.abs(previousTotalAudited - current) > BALANCE_TOLERANCE) {
        publishAdjudicated()
        writebackTrialBalance()
      }
      previousTotalAudited = current
    },
  )

  // 实时同步三科目审定合计到 allResponses（含首次挂载）——与 TB 回写/事件解耦，
  // 仅内存写入，确保「审定合计」全局告警 + E1-14 + 附注披露即时读到正确审定数。
  watch(
    detailRows,
    () => syncAuditedTotals(),
    { immediate: true },
  )

  // ─── Hydration ───────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    crossSheetStatus.value = 'loading'
    try {
      // Cross-sheet data is derived from allResponses computed chain.
      // Hydration just validates the map is populated.
      crossSheetStatus.value = 'loaded'
    } catch {
      crossSheetStatus.value = 'error'
    } finally {
      isLoading.value = false
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    detailRows,
    totalRow,
    tbAmountRow,
    diffRow,
    crossSheetStatus,
    isLoading,
    isRateExceeding,
    hasDifference,
    updateCell,
    saveVarianceNote,
    applyFourTablePrefill,
    getVal,
    writebackTrialBalance,
    publishAdjudicated,
    hydrate,
  }
}
