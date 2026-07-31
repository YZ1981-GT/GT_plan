/**
 * useF2Adjudication — F2-1 审定表三大块（原值/跌价/净值）
 *
 * Spec: .kiro/specs/f2-inventory-main/ Task 4.1
 * 比照 useD4Adjudication / useF3Adjudication
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcSubtotal,
  calcNetValue,
  calcAuditedEnd,
} from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'
import { F2_ROW_KEY_ACCOUNT } from './useF2CrossSheet'
import { eventBus } from '@/utils/eventBus'

export const F2_CATEGORIES = [
  { rowKey: 'raw-materials', label: '原材料' },
  { rowKey: 'material-in-transit', label: '材料采购在途' },
  { rowKey: 'revolving-materials', label: '周转材料' },
  { rowKey: 'semi-finished', label: '自制半成品' },
  { rowKey: 'outsourced-processing', label: '委托加工物资' },
  { rowKey: 'finished-goods', label: '库存商品' },
  { rowKey: 'goods-in-transit', label: '发出商品' },
  { rowKey: 'dev-products', label: '开发产品' },
  { rowKey: 'dev-costs', label: '开发成本' },
  { rowKey: 'contract-performance', label: '合同履约成本' },
  { rowKey: 'consumable-bio', label: '消耗性生物资产' },
  { rowKey: 'price-difference', label: '商品进销差价' },
  { rowKey: 'impairment-provision', label: '存货跌价准备' },
] as const

export type F2BlockKey = 'gross' | 'impairment'

export interface F2AdjudicationRow {
  rowKey: string
  label: string
  opening: number
  increase: number
  decrease: number
  endUnadjusted: number
  adjustment: number
  endAudited: number
  isFromCrossSheet?: boolean
}

function itemId(block: F2BlockKey, rowKey: string, field: string): string {
  return `F2-1-${block}-${rowKey}-${field}`
}

function loadField(map: Map<string, ChecklistResponse>, id: string): number {
  const v = map.get(id)?.conclusion
  return parseNum(v)
}

function buildBlockRows(
  block: F2BlockKey,
  map: Map<string, ChecklistResponse>,
  crossSheet?: ReturnType<typeof import('./useF2CrossSheet').useF2CrossSheet>,
): F2AdjudicationRow[] {
  return F2_CATEGORIES.map((cat) => {
    let opening = loadField(map, itemId(block, cat.rowKey, 'opening'))
    let increase = loadField(map, itemId(block, cat.rowKey, 'increase'))
    let decrease = loadField(map, itemId(block, cat.rowKey, 'decrease'))
    const adjustmentManual = loadField(map, itemId(block, cat.rowKey, 'adjustment'))
    let adjustment = adjustmentManual

    if (block === 'gross' && crossSheet?.hasAdjustmentData.value) {
      const fromAdj = crossSheet.grossAdjustmentByRowKey.value[cat.rowKey]
      if (fromAdj !== undefined) adjustment = fromAdj
    }
    if (block === 'impairment' && crossSheet?.hasAdjustmentData.value) {
      const fromAdj = crossSheet.impairmentAdjustmentByRowKey.value[cat.rowKey]
      if (fromAdj !== undefined) adjustment = fromAdj
    }
    let isFromCrossSheet = false

    if (block === 'gross' && crossSheet?.hasDetailData.value) {
      const summary = crossSheet.summaryForRowKey(cat.rowKey)
      if (summary && (summary.closingAmt !== 0 || summary.openingAmt !== 0)) {
        opening = summary.openingAmt
        increase = summary.increaseAmt
        decrease = summary.decreaseAmt
        isFromCrossSheet = true
      }
    }

    const endUnadjusted = opening + increase - decrease
    const endAudited = calcAuditedEnd(opening, increase, decrease, adjustment)
    return {
      rowKey: cat.rowKey,
      label: cat.label,
      opening,
      increase,
      decrease,
      endUnadjusted,
      adjustment,
      endAudited,
      isFromCrossSheet,
    }
  })
}

function subtotalRow(rows: F2AdjudicationRow[], label: string): F2AdjudicationRow {
  return {
    rowKey: 'subtotal',
    label,
    opening: calcSubtotal(rows.map((r) => r.opening)),
    increase: calcSubtotal(rows.map((r) => r.increase)),
    decrease: calcSubtotal(rows.map((r) => r.decrease)),
    endUnadjusted: calcSubtotal(rows.map((r) => r.endUnadjusted)),
    adjustment: calcSubtotal(rows.map((r) => r.adjustment)),
    endAudited: calcSubtotal(rows.map((r) => r.endAudited)),
  }
}

/**
 * 存货净额 = 余额合计(审定) − 跌价准备(1471 审定)
 * 纯函数，便于单测 (Property P6)
 */
export function calcNetInventory(totalBalance: number, impairmentProvision: number): number {
  return totalBalance - impairmentProvision
}

export interface TbValuesEntry {
  opening?: number
  closing?: number
  /** 灰度开时后端返回：本期增加 */
  increase?: number
  /** 灰度开时后端返回：本期减少 */
  decrease?: number
  /** 灰度开时后端返回：取数公式溯源 */
  formulas?: Record<string, string>
  /** 灰度开时后端返回：源科目编码 */
  source_codes?: string[]
}

export interface UseF2AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  crossSheet?: ReturnType<typeof import('./useF2CrossSheet').useF2CrossSheet>
  /** 后端 render 输出的 tb_values（各 rowKey 期初/期末未审） */
  tbValues?: Ref<Record<string, TbValuesEntry> | null | undefined>
  /** 后端 render 输出的存货净额 TB 核对标量（BS-010 trial_balance），无持久化时只读回退 seed */
  tbAmountSeed?: Ref<number | null | undefined>
}

export function useF2Adjudication(opts: UseF2AdjudicationOptions) {
  let metaDebounceTimer: ReturnType<typeof setTimeout> | null = null
  let seeded = false

  const auditNote = ref('')
  const conclusion = ref('')

  // ─── 预填 seed 逻辑（Req 1 — 消费后端 tb_values） ─────────────────────
  // 若 allResponses 中无 F2-adjudication-data 且 tbValues 存在 → seed 各行 beginUnadj/endUnadj
  function seedFromTbValues(): void {
    if (seeded) return
    const map = opts.allResponses.value
    // 检查是否已有持久化数据 → 不覆盖（Req 1.3 幂等）
    if (map.has('F2-adjudication-data')) return
    // 检查是否有任何 F2-1 区块数据已写入（用户曾编辑过）
    for (const [key] of map) {
      if (key.startsWith('F2-1-gross-') || key.startsWith('F2-1-impairment-')) return
    }
    const tbVals = opts.tbValues?.value
    if (!tbVals || Object.keys(tbVals).length === 0) return
    seeded = true
    // 将 tb_values 各 rowKey 的 opening/increase/decrease 填入对应行
    for (const cat of F2_CATEGORIES) {
      const entry = tbVals[cat.rowKey]
      if (!entry) continue

      // 判断是否为新结构（灰度开时后端返回含 increase/decrease）
      const hasNewFields = 'increase' in entry || 'decrease' in entry

      // 判断 block：impairment-provision 归 impairment block，其余归 gross
      const block: F2BlockKey = cat.rowKey === 'impairment-provision' ? 'impairment' : 'gross'

      if (hasNewFields) {
        // ─── 灰度开：直填 opening/increase/decrease（不粗猜） ───
        const opening = (entry as any).opening ?? 0
        const increase = (entry as any).increase ?? 0
        const decrease = (entry as any).decrease ?? 0

        if (opening !== 0) {
          const id = itemId(block, cat.rowKey, 'opening')
          if (!map.has(id)) {
            map.set(id, { item_id: id, conclusion: String(opening), remark: null })
          }
        }
        if (increase !== 0) {
          const id = itemId(block, cat.rowKey, 'increase')
          if (!map.has(id)) {
            map.set(id, { item_id: id, conclusion: String(increase), remark: null })
          }
        }
        if (decrease !== 0) {
          const id = itemId(block, cat.rowKey, 'decrease')
          if (!map.has(id)) {
            map.set(id, { item_id: id, conclusion: String(decrease), remark: null })
          }
        }
      } else {
        // ─── 灰度关/旧结构：保持旧 closing−opening 粗猜逻辑（零回归） ───
        const opening = entry.opening ?? 0
        const closing = entry.closing ?? 0
        if (opening !== 0) {
          const id = itemId(block, cat.rowKey, 'opening')
          if (!map.has(id)) {
            map.set(id, { item_id: id, conclusion: String(opening), remark: null })
          }
        }
        if (closing !== opening) {
          const incId = itemId(block, cat.rowKey, 'increase')
          if (!map.has(incId)) {
            const inc = closing - opening
            if (inc > 0) {
              map.set(incId, { item_id: incId, conclusion: String(inc), remark: null })
            } else if (inc < 0) {
              const decId = itemId(block, cat.rowKey, 'decrease')
              if (!map.has(decId)) {
                map.set(decId, { item_id: decId, conclusion: String(Math.abs(inc)), remark: null })
              }
            }
          }
        }
      }
    }
  }
  // 立即尝试 seed（加载后第一次调用）
  seedFromTbValues()
  // watch tbValues 变化再尝试（lazy load 场景）
  if (opts.tbValues) {
    watch(opts.tbValues, () => seedFromTbValues(), { immediate: true })
  }

  const grossRows = computed(() => buildBlockRows('gross', opts.allResponses.value, opts.crossSheet))
  const impairmentRows = computed(() => buildBlockRows('impairment', opts.allResponses.value))

  const grossSubtotal = computed(() => subtotalRow(grossRows.value, '原值合计'))
  const impairmentSubtotal = computed(() => subtotalRow(impairmentRows.value, '跌价合计'))

  const netRows = computed<F2AdjudicationRow[]>(() =>
    F2_CATEGORIES.map((cat, i) => {
      const g = grossRows.value[i]
      const imp = impairmentRows.value[i]
      const endAudited = calcNetValue(g.endAudited, imp.endAudited)
      return {
        rowKey: cat.rowKey,
        label: cat.label,
        opening: calcNetValue(g.opening, imp.opening),
        increase: calcNetValue(g.increase, imp.increase),
        decrease: calcNetValue(g.decrease, imp.decrease),
        endUnadjusted: calcNetValue(g.endUnadjusted, imp.endUnadjusted),
        adjustment: calcNetValue(g.adjustment, imp.adjustment),
        endAudited,
      }
    }),
  )

  const netSubtotal = computed(() => subtotalRow(netRows.value, '净值合计'))

  // ─── 存货净额行（Req 5 — 净额 = 余额合计 − 跌价准备1471）─────────────
  const inventoryNetRow = computed(() => {
    const totalBalance = grossSubtotal.value.endAudited
    const impairmentProvision = impairmentRows.value.find(
      (r) => r.rowKey === 'impairment-provision',
    )?.endAudited ?? impairmentSubtotal.value.endAudited
    return {
      label: '存货净额',
      totalBalance,
      impairmentProvision,
      netAmount: calcNetInventory(totalBalance, impairmentProvision),
    }
  })

  const trialBalanceAmount = computed(() => {
    // 手工优先：有持久化 F2-1-tb-total 用之；否则回退后端 render 的存货净额（BS-010）
    const persisted = opts.allResponses.value.get('F2-1-tb-total')?.remark
    if (persisted !== undefined && persisted !== null && String(persisted).trim() !== '') {
      return parseNum(persisted)
    }
    return parseNum(opts.tbAmountSeed?.value ?? 0)
  })

  const trialBalanceDiff = computed(
    () => netSubtotal.value.endAudited - trialBalanceAmount.value,
  )

  const detailCrossValidation: ComputedRef<string | null> = computed(() => {
    if (!opts.crossSheet) return null
    return opts.crossSheet.grossCrossValidation(grossSubtotal.value.endUnadjusted)
  })

  watch(
    () => opts.allResponses.value.get('F2-1-adj-note')?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get('F2-1-adj-conclusion')?.remark,
    (v) => { conclusion.value = v || '' },
    { immediate: true },
  )

  function flushMetaSave(): void {
    const items = [
      opts.allResponses.value.get('F2-1-adj-note'),
      opts.allResponses.value.get('F2-1-adj-conclusion'),
      opts.allResponses.value.get('F2-1-tb-total'),
    ].filter(Boolean) as ChecklistResponse[]
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
    }
  }

  function debounceMetaSave(): void {
    if (metaDebounceTimer) clearTimeout(metaDebounceTimer)
    metaDebounceTimer = setTimeout(() => {
      metaDebounceTimer = null
      flushMetaSave()
    }, 2000)
  }

  function updateTrialBalanceAmount(value: number): void {
    if (opts.isReadonly.value) return
    opts.allResponses.value.set('F2-1-tb-total', {
      item_id: 'F2-1-tb-total',
      conclusion: null,
      remark: String(value),
    })
    debounceMetaSave()
  }

  function updateCell(block: F2BlockKey, rowKey: string, field: string, value: number) {
    if (opts.isReadonly.value) return
    opts.debouncedSave(itemId(block, rowKey, field), { conclusion: String(value) })
  }

  function publishAdjudicated(): void {
    const netByCategory = netRows.value.map((r) => ({
      rowKey: r.rowKey,
      label: r.label,
      accountCode: F2_ROW_KEY_ACCOUNT[r.rowKey] || '',
      endAudited: r.endAudited,
      opening: r.opening,
    }))

    const accountCodes = [...new Set(netByCategory.map((r) => r.accountCode).filter(Boolean))]
    const auditedAmounts: Record<string, number> = {}
    for (const row of netByCategory) {
      if (row.accountCode) {
        auditedAmounts[row.accountCode] = (auditedAmounts[row.accountCode] || 0) + row.endAudited
      }
    }

    const payload = {
      wpCode: 'F2',
      accountCodes,
      auditedAmounts,
      netTotal: netSubtotal.value.endAudited,
    }

    try {
      eventBus.emit('substantive:adjudicated', payload)
    } catch { /* silent */ }

    if (opts.projectId.value) {
      for (const [accountCode, amount] of Object.entries(auditedAmounts)) {
        try {
          window.dispatchEvent(new CustomEvent('f2:writeback-trial-balance', {
            detail: {
              projectId: opts.projectId.value,
              accountCode,
              auditedAmount: amount,
            },
          }))
        } catch { /* silent */ }
      }
    }
  }

  watch(auditNote, (val) => {
    opts.allResponses.value.set('F2-1-adj-note', {
      item_id: 'F2-1-adj-note',
      conclusion: null,
      remark: val,
    })
    debounceMetaSave()
    try {
      eventBus.emit('disclosure:note-text-updated', { wpCode: 'F2', section: 'adj-note', text: val })
    } catch { /* silent */ }
  })

  watch(conclusion, (val) => {
    opts.allResponses.value.set('F2-1-adj-conclusion', {
      item_id: 'F2-1-adj-conclusion',
      conclusion: null,
      remark: val,
    })
    debounceMetaSave()
  })

  onBeforeUnmount(() => {
    if (metaDebounceTimer) {
      clearTimeout(metaDebounceTimer)
      flushMetaSave()
    }
    window.removeEventListener('impairment:calculated', onImpairmentCalculated)
  })

  const impairmentRefreshKey = ref(0)
  function onImpairmentCalculated(e: Event): void {
    const d = (e as CustomEvent).detail
    if (d?.wpCode === 'F2') impairmentRefreshKey.value += 1
  }
  window.addEventListener('impairment:calculated', onImpairmentCalculated)

  return {
    grossRows,
    impairmentRows,
    netRows,
    grossSubtotal,
    impairmentSubtotal,
    netSubtotal,
    inventoryNetRow,
    trialBalanceAmount,
    trialBalanceDiff,
    detailCrossValidation,
    impairmentRefreshKey,
    auditNote,
    conclusion,
    updateCell,
    updateTrialBalanceAmount,
    publishAdjudicated,
  }
}

export default useF2Adjudication
