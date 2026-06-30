/**
 * useD4Adjudication — D4-1 审定表核心逻辑 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 6.1
 *
 * 职责：
 * - 双区块固定行（主营产品行+小计 / 其他项目行+小计 / 营业收入合计）
 * - sections computed（从crossSheet聚合值填入）
 * - trialBalanceRow + differenceRow（TB科目6001+6051）
 * - mainCrossValidation / otherCrossValidation 警告
 * - updateCell + addProductRow/removeProductRow
 * - publishAdjudicated（EventBus → TB回写6001+6051）
 * - onAdjustmentCreated监听
 *
 * Requirements: 2.1-2.10, 18.1
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcChangeRate,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD4BaseOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface AdjudicationRow {
  rowKey: string
  label: string
  isFixed: boolean
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  currentAudited: number    // = 未审 + AJE + RJE (auto)
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number      // = 未审 + AJE + RJE (auto)
  isFromCrossSheet: boolean
  isEditable: boolean
}

export interface AdjudicationSection {
  sectionKey: 'main-revenue' | 'other-revenue'
  sectionLabel: string
  rows: AdjudicationRow[]
  subtotalRow: AdjudicationRow
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ADJ_STORAGE_KEY = 'D4-1-adj-rows'
const BALANCE_TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowKey(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

interface StoredAdjRow {
  rowKey: string
  label: string
  isFixed: boolean
  sectionKey: 'main-revenue' | 'other-revenue'
  currentUnadjusted: number
  currentAje: number
  currentRje: number
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  isFromCrossSheet: boolean
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Adjudication(options: UseD4BaseOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Audit note / conclusion ─────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load stored rows ────────────────────────────────────────────────

  const storedRows = computed<StoredAdjRow[]>(() => {
    const resp = allResponses.value.get(ADJ_STORAGE_KEY)
    return safeParseRows<StoredAdjRow>(resp?.remark)
  })

  // ─── CrossSheet data (from allResponses D4-2/D4-3/D4-4) ─────────────

  /** Parse D4-2 rows for main revenue aggregation */
  const mainRevenueByProduct = computed<Record<string, { current: number; prior: number }>>(() => {
    const resp = allResponses.value.get('D4-2-rows')
    const rows = safeParseRows<any>(resp?.remark)
    const result: Record<string, { current: number; prior: number }> = {}
    for (const row of rows) {
      const product = row.product || '未命名'
      const months = Array.isArray(row.months) ? row.months.map(parseNum) : []
      const periodTotal = months.reduce((s: number, v: number) => s + v, 0)
      const audited = periodTotal + parseNum(row.auditAdjustment)
      const priorAudited = parseNum(row.priorUnadjusted) + parseNum(row.priorAdjustment)
      if (!result[product]) result[product] = { current: 0, prior: 0 }
      result[product].current += audited
      result[product].prior += priorAudited
    }
    return result
  })

  /** Parse D4-3 rows for other revenue aggregation */
  const otherRevenueByItem = computed<Record<string, { current: number; prior: number }>>(() => {
    const resp = allResponses.value.get('D4-3-rows')
    const rows = safeParseRows<any>(resp?.remark)
    const result: Record<string, { current: number; prior: number }> = {}
    for (const row of rows) {
      const item = row.item || '未命名'
      const currentAudited = parseNum(row.currentUnadjusted) + parseNum(row.currentAdjustment)
      const priorAudited = parseNum(row.priorUnadjusted) + parseNum(row.priorAdjustment)
      if (!result[item]) result[item] = { current: 0, prior: 0 }
      result[item].current += currentAudited
      result[item].prior += priorAudited
    }
    return result
  })

  /** Parse D4-4 adjustment totals */
  const adjustmentTotals = computed(() => {
    const resp = allResponses.value.get('D4-4-rows')
    const rows = safeParseRows<any>(resp?.remark)
    let mainAje = 0, mainRje = 0, otherAje = 0, otherRje = 0
    for (const row of rows) {
      const code = row.accountName || row.accountCode || ''
      const amount = parseNum(row.debitAmount) - parseNum(row.creditAmount)
      const isMain = code.includes('6001')
      const isOther = code.includes('6051')
      if (isMain) {
        if (row.category === 'AJE' || row.entryType === 'AJE') mainAje += amount
        else mainRje += amount
      } else if (isOther) {
        if (row.category === 'AJE' || row.entryType === 'AJE') otherAje += amount
        else otherRje += amount
      }
    }
    return { mainAje, mainRje, otherAje, otherRje }
  })

  // ─── Sections computed ───────────────────────────────────────────────

  const sections: ComputedRef<AdjudicationSection[]> = computed(() => {
    const stored = storedRows.value
    const mainByProduct = mainRevenueByProduct.value
    const otherByItem = otherRevenueByItem.value
    const adjTotals = adjustmentTotals.value

    // === Main Revenue Section ===
    const mainProducts = Object.keys(mainByProduct)
    const mainStoredRows = stored.filter(r => r.sectionKey === 'main-revenue')
    const mainRows: AdjudicationRow[] = []

    // Use crossSheet products to populate rows
    for (const product of mainProducts) {
      const data = mainByProduct[product]
      const existingStored = mainStoredRows.find(r => r.label === product)
      mainRows.push({
        rowKey: existingStored?.rowKey || `main-${product}`,
        label: product,
        isFixed: false,
        currentUnadjusted: data.current,
        currentAje: adjTotals.mainAje,
        currentRje: adjTotals.mainRje,
        currentAudited: calcAuditedAmount(data.current, 0, 0), // AJE/RJE at subtotal level
        priorUnadjusted: data.prior,
        priorAje: existingStored ? parseNum(existingStored.priorAje) : 0,
        priorRje: existingStored ? parseNum(existingStored.priorRje) : 0,
        priorAudited: calcAuditedAmount(data.prior, existingStored ? parseNum(existingStored.priorAje) : 0, existingStored ? parseNum(existingStored.priorRje) : 0),
        isFromCrossSheet: true,
        isEditable: false,
      })
    }

    // Add manually added rows (not from crossSheet)
    for (const sr of mainStoredRows) {
      if (!mainProducts.includes(sr.label) && !sr.isFromCrossSheet) {
        mainRows.push({
          rowKey: sr.rowKey,
          label: sr.label,
          isFixed: sr.isFixed,
          currentUnadjusted: parseNum(sr.currentUnadjusted),
          currentAje: parseNum(sr.currentAje),
          currentRje: parseNum(sr.currentRje),
          currentAudited: calcAuditedAmount(parseNum(sr.currentUnadjusted), parseNum(sr.currentAje), parseNum(sr.currentRje)),
          priorUnadjusted: parseNum(sr.priorUnadjusted),
          priorAje: parseNum(sr.priorAje),
          priorRje: parseNum(sr.priorRje),
          priorAudited: calcAuditedAmount(parseNum(sr.priorUnadjusted), parseNum(sr.priorAje), parseNum(sr.priorRje)),
          isFromCrossSheet: false,
          isEditable: true,
        })
      }
    }

    const mainSubtotal: AdjudicationRow = {
      rowKey: 'main-subtotal',
      label: '主营业务收入小计',
      isFixed: true,
      currentUnadjusted: calcSubtotal(mainRows.map(r => r.currentUnadjusted)),
      currentAje: adjTotals.mainAje,
      currentRje: adjTotals.mainRje,
      currentAudited: calcAuditedAmount(
        calcSubtotal(mainRows.map(r => r.currentUnadjusted)),
        adjTotals.mainAje,
        adjTotals.mainRje,
      ),
      priorUnadjusted: calcSubtotal(mainRows.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(mainRows.map(r => r.priorAje)),
      priorRje: calcSubtotal(mainRows.map(r => r.priorRje)),
      priorAudited: calcAuditedAmount(
        calcSubtotal(mainRows.map(r => r.priorUnadjusted)),
        calcSubtotal(mainRows.map(r => r.priorAje)),
        calcSubtotal(mainRows.map(r => r.priorRje)),
      ),
      isFromCrossSheet: false,
      isEditable: false,
    }

    // === Other Revenue Section ===
    const otherItems = Object.keys(otherByItem)
    const otherStoredRows = stored.filter(r => r.sectionKey === 'other-revenue')
    const otherRows: AdjudicationRow[] = []

    for (const item of otherItems) {
      const data = otherByItem[item]
      const existingStored = otherStoredRows.find(r => r.label === item)
      otherRows.push({
        rowKey: existingStored?.rowKey || `other-${item}`,
        label: item,
        isFixed: false,
        currentUnadjusted: data.current,
        currentAje: adjTotals.otherAje,
        currentRje: adjTotals.otherRje,
        currentAudited: calcAuditedAmount(data.current, 0, 0),
        priorUnadjusted: data.prior,
        priorAje: existingStored ? parseNum(existingStored.priorAje) : 0,
        priorRje: existingStored ? parseNum(existingStored.priorRje) : 0,
        priorAudited: calcAuditedAmount(data.prior, existingStored ? parseNum(existingStored.priorAje) : 0, existingStored ? parseNum(existingStored.priorRje) : 0),
        isFromCrossSheet: true,
        isEditable: false,
      })
    }

    // Add manually added rows (not from crossSheet)
    for (const sr of otherStoredRows) {
      if (!otherItems.includes(sr.label) && !sr.isFromCrossSheet) {
        otherRows.push({
          rowKey: sr.rowKey,
          label: sr.label,
          isFixed: sr.isFixed,
          currentUnadjusted: parseNum(sr.currentUnadjusted),
          currentAje: parseNum(sr.currentAje),
          currentRje: parseNum(sr.currentRje),
          currentAudited: calcAuditedAmount(parseNum(sr.currentUnadjusted), parseNum(sr.currentAje), parseNum(sr.currentRje)),
          priorUnadjusted: parseNum(sr.priorUnadjusted),
          priorAje: parseNum(sr.priorAje),
          priorRje: parseNum(sr.priorRje),
          priorAudited: calcAuditedAmount(parseNum(sr.priorUnadjusted), parseNum(sr.priorAje), parseNum(sr.priorRje)),
          isFromCrossSheet: false,
          isEditable: true,
        })
      }
    }

    const otherSubtotal: AdjudicationRow = {
      rowKey: 'other-subtotal',
      label: '其他业务收入小计',
      isFixed: true,
      currentUnadjusted: calcSubtotal(otherRows.map(r => r.currentUnadjusted)),
      currentAje: adjTotals.otherAje,
      currentRje: adjTotals.otherRje,
      currentAudited: calcAuditedAmount(
        calcSubtotal(otherRows.map(r => r.currentUnadjusted)),
        adjTotals.otherAje,
        adjTotals.otherRje,
      ),
      priorUnadjusted: calcSubtotal(otherRows.map(r => r.priorUnadjusted)),
      priorAje: calcSubtotal(otherRows.map(r => r.priorAje)),
      priorRje: calcSubtotal(otherRows.map(r => r.priorRje)),
      priorAudited: calcAuditedAmount(
        calcSubtotal(otherRows.map(r => r.priorUnadjusted)),
        calcSubtotal(otherRows.map(r => r.priorAje)),
        calcSubtotal(otherRows.map(r => r.priorRje)),
      ),
      isFromCrossSheet: false,
      isEditable: false,
    }

    return [
      {
        sectionKey: 'main-revenue' as const,
        sectionLabel: '一、主营业务收入',
        rows: mainRows,
        subtotalRow: mainSubtotal,
      },
      {
        sectionKey: 'other-revenue' as const,
        sectionLabel: '二、其他业务收入',
        rows: otherRows,
        subtotalRow: otherSubtotal,
      },
    ]
  })

  // ─── Grand Total Row ─────────────────────────────────────────────────

  const grandTotalRow: ComputedRef<AdjudicationRow> = computed(() => {
    const secs = sections.value
    const mainSub = secs[0]?.subtotalRow
    const otherSub = secs[1]?.subtotalRow

    if (!mainSub || !otherSub) {
      return {
        rowKey: 'grand-total', label: '营业收入合计', isFixed: true,
        currentUnadjusted: 0, currentAje: 0, currentRje: 0, currentAudited: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, priorAudited: 0,
        isFromCrossSheet: false, isEditable: false,
      }
    }

    return {
      rowKey: 'grand-total',
      label: '营业收入合计',
      isFixed: true,
      currentUnadjusted: mainSub.currentUnadjusted + otherSub.currentUnadjusted,
      currentAje: mainSub.currentAje + otherSub.currentAje,
      currentRje: mainSub.currentRje + otherSub.currentRje,
      currentAudited: mainSub.currentAudited + otherSub.currentAudited,
      priorUnadjusted: mainSub.priorUnadjusted + otherSub.priorUnadjusted,
      priorAje: mainSub.priorAje + otherSub.priorAje,
      priorRje: mainSub.priorRje + otherSub.priorRje,
      priorAudited: mainSub.priorAudited + otherSub.priorAudited,
      isFromCrossSheet: false,
      isEditable: false,
    }
  })

  // ─── Trial Balance Row ───────────────────────────────────────────────

  const trialBalanceRow: ComputedRef<{ amount6001: number; amount6051: number; total: number }> = computed(() => {
    const tb6001 = parseNum(allResponses.value.get('D4-1-adj-tb-6001')?.remark)
    const tb6051 = parseNum(allResponses.value.get('D4-1-adj-tb-6051')?.remark)
    return { amount6001: tb6001, amount6051: tb6051, total: tb6001 + tb6051 }
  })

  // ─── Difference Row ──────────────────────────────────────────────────

  const differenceRow: ComputedRef<number> = computed(() => {
    return grandTotalRow.value.currentAudited - trialBalanceRow.value.total
  })

  // ─── Cross Validation Warnings ───────────────────────────────────────

  const mainCrossValidation: ComputedRef<string | null> = computed(() => {
    const mainSubtotal = sections.value[0]?.subtotalRow
    if (!mainSubtotal) return null
    const d4_2_resp = allResponses.value.get('D4-2-rows')
    if (!d4_2_resp?.remark) return null
    const d4_2_rows = safeParseRows<any>(d4_2_resp.remark)
    if (d4_2_rows.length === 0) return null

    // D4-2 subtotal audited
    let d4_2_total = 0
    for (const row of d4_2_rows) {
      const months = Array.isArray(row.months) ? row.months.map(parseNum) : []
      const periodTotal = months.reduce((s: number, v: number) => s + v, 0)
      d4_2_total += periodTotal + parseNum(row.auditAdjustment)
    }

    const diff = mainSubtotal.currentAudited - d4_2_total
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `D4-1主营小计(${mainSubtotal.currentAudited.toFixed(2)}) 与 D4-2合计(${d4_2_total.toFixed(2)}) 差异${diff.toFixed(2)}`
    }
    return null
  })

  const otherCrossValidation: ComputedRef<string | null> = computed(() => {
    const otherSubtotal = sections.value[1]?.subtotalRow
    if (!otherSubtotal) return null
    const d4_3_resp = allResponses.value.get('D4-3-rows')
    if (!d4_3_resp?.remark) return null
    const d4_3_rows = safeParseRows<any>(d4_3_resp.remark)
    if (d4_3_rows.length === 0) return null

    let d4_3_total = 0
    for (const row of d4_3_rows) {
      d4_3_total += parseNum(row.currentUnadjusted) + parseNum(row.currentAdjustment)
    }

    const diff = otherSubtotal.currentAudited - d4_3_total
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `D4-1其他小计(${otherSubtotal.currentAudited.toFixed(2)}) 与 D4-3合计(${d4_3_total.toFixed(2)}) 差异${diff.toFixed(2)}`
    }
    return null
  })

  // ─── Row Operations ──────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: number): void {
    if (readonly.value) return
    const stored = safeParseRows<StoredAdjRow>(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const idx = stored.findIndex(r => r.rowKey === rowKey)
    if (idx === -1) return
    ;(stored[idx] as any)[field] = value
    persistRows(stored)
  }

  function addProductRow(): void {
    if (readonly.value) return
    const stored = safeParseRows<StoredAdjRow>(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    stored.push({
      rowKey: generateRowKey(),
      label: '',
      isFixed: false,
      sectionKey: 'main-revenue',
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      isFromCrossSheet: false,
    })
    persistRows(stored)
  }

  function removeProductRow(rowKey: string): void {
    if (readonly.value) return
    const stored = safeParseRows<StoredAdjRow>(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const filtered = stored.filter(r => r.rowKey !== rowKey)
    persistRows(filtered)
  }

  // ─── Persist / Save ──────────────────────────────────────────────────

  function persistRows(rows: StoredAdjRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(ADJ_STORAGE_KEY, {
      item_id: ADJ_STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const items = [
        allResponses.value.get(ADJ_STORAGE_KEY),
        allResponses.value.get('D4-1-adj-note'),
        allResponses.value.get('D4-1-adj-conclusion'),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  // ─── EventBus: publishAdjudicated ────────────────────────────────────

  function publishAdjudicated(): void {
    const total = grandTotalRow.value
    const mainSub = sections.value[0]?.subtotalRow
    const otherSub = sections.value[1]?.subtotalRow

    const payload = {
      wpCode: 'D4',
      accountCode: '6001,6051',
      auditedAmount: {
        main: mainSub?.currentAudited ?? 0,
        other: otherSub?.currentAudited ?? 0,
      },
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }

    // Writeback TB
    if (projectId.value) {
      try {
        window.dispatchEvent(new CustomEvent('d4:writeback-trial-balance', {
          detail: {
            projectId: projectId.value,
            accountCode: '6001',
            auditedAmount: mainSub?.currentAudited ?? 0,
          },
        }))
        window.dispatchEvent(new CustomEvent('d4:writeback-trial-balance', {
          detail: {
            projectId: projectId.value,
            accountCode: '6051',
            auditedAmount: otherSub?.currentAudited ?? 0,
          },
        }))
      } catch { /* silent */ }
    }
  }

  // ─── EventBus: onAdjustmentCreated ───────────────────────────────────

  function onAdjustmentCreated(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail || detail.wpCode !== 'D4') return
    // AJE/RJE changes auto-reflected via adjustmentTotals computed
  }

  // ─── Watch audit note/conclusion ─────────────────────────────────────

  watch(
    () => allResponses.value.get('D4-1-adj-note')?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get('D4-1-adj-conclusion')?.remark,
    (val) => { auditConclusion.value = val || '' },
    { immediate: true },
  )

  watch(auditNote, (val) => {
    allResponses.value.set('D4-1-adj-note', { item_id: 'D4-1-adj-note', conclusion: null, remark: val })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set('D4-1-adj-conclusion', { item_id: 'D4-1-adj-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  // ─── EventBus Registration ───────────────────────────────────────────

  const adjustmentHandler = (e: Event) => onAdjustmentCreated(e)
  window.addEventListener('adjustment:created', adjustmentHandler)
  eventListeners.push({ event: 'adjustment:created', handler: adjustmentHandler })

  // ─── D4-2/D4-3 行同步监听（Task 22.1） ────────────────────────────────

  const syncRowHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (!detail) return
    const { section, action, product, item } = detail
    const name = product || item || ''
    if (!name) return

    const targetSection = section === 'main-revenue' ? 'main-revenue' : 'other-revenue'

    if (action === 'add') {
      // 添加一行到审定表，标记为 isFromCrossSheet
      const stored = safeParseRows<StoredAdjRow>(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
      // 避免重复添加
      if (stored.some(r => r.label === name && r.sectionKey === targetSection)) return
      stored.push({
        rowKey: generateRowKey(),
        label: name,
        isFixed: false,
        sectionKey: targetSection,
        currentUnadjusted: 0,
        currentAje: 0,
        currentRje: 0,
        priorUnadjusted: 0,
        priorAje: 0,
        priorRje: 0,
        isFromCrossSheet: true,
      })
      persistRows(stored)
    } else if (action === 'remove') {
      const stored = safeParseRows<StoredAdjRow>(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
      const row = stored.find(r => r.label === name && r.sectionKey === targetSection && r.isFromCrossSheet)
      if (row) {
        // AJE/RJE 非零时不自动删除（需用户确认）
        if (row.currentAje === 0 && row.currentRje === 0 && row.priorAje === 0 && row.priorRje === 0) {
          const filtered = stored.filter(r => r.rowKey !== row.rowKey)
          persistRows(filtered)
        }
      }
    }
  }
  window.addEventListener('d4:sync-row', syncRowHandler)
  eventListeners.push({ event: 'd4:sync-row', handler: syncRowHandler })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    sections,
    grandTotalRow,
    trialBalanceRow,
    differenceRow,
    mainCrossValidation,
    otherCrossValidation,
    auditNote,
    auditConclusion,
    updateCell,
    addProductRow,
    removeProductRow,
    publishAdjudicated,
  }
}

export default useD4Adjudication
