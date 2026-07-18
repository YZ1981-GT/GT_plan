/**
 * useF4SupplierFinancing — F4-9 供应商融资检查表
 *
 * 源表逻辑：按供应商动态分组 → 登记融资明细 → 小计融资金额/采购金额/差异/借款余额
 * → 合计 → 关注融资金额大于采购金额的体外循环风险。
 * 支持从 F4-2 引用供应商插行、附件 OCR 确认回填、AI 说明/结论。
 */
import { computed, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useF4AccPayFormulaEngine'
import { migrateF4DetailRows } from './useF4Detail'
import { readRowJson, type ChecklistResponse } from './useF4FormData'

export const F4_FINANCING_STATUS_OPTIONS = [
  '未放款',
  '已放款',
  '已转让',
  '已还款',
  '逾期',
  '其他',
] as const

export interface F4FinancingOcrFields {
  supplierName?: string
  promisedPayer?: string
  financingNo?: string
  fundProvider?: string
  status?: string
  financingAmount?: number | string
  supplierSignDate?: string
  disbursementDate?: string
  transferDate?: string
  promisedRepayDate?: string
  actualRepayDate?: string
  purchaseAmount?: number | string
  loanBalance?: number | string
  remark?: string
}

export interface FinancingRow {
  rowId: string
  seq: number
  attSlot: number
  /** 同一供应商下多笔融资共用 groupId */
  groupId: string
  supplierName: string
  promisedPayer: string
  financingNo: string
  fundProvider: string
  status: string
  financingAmount: number
  supplierSignDate: string
  disbursementDate: string
  transferDate: string
  promisedRepayDate: string
  actualRepayDate: string
  purchaseAmount: number
  /** 差异 = 融资金额 − 本期采购金额（公式列） */
  difference: number
  loanBalance: number
  remark: string
  /** 来自 F4-2 的债权人行 ID；空表示手工行 */
  sourceRowId: string
  riskFlags: string[]
  highlightLevel: 'none' | 'warning' | 'danger'
}

interface StoredFinancingRow {
  rowId: string
  seq: number
  attSlot: number
  groupId: string
  supplierName: string
  promisedPayer: string
  financingNo: string
  fundProvider: string
  status: string
  financingAmount: number
  supplierSignDate: string
  disbursementDate: string
  transferDate: string
  promisedRepayDate: string
  actualRepayDate: string
  purchaseAmount: number
  loanBalance: number
  remark: string
  sourceRowId: string
}

export type FinancingDisplayKind = 'detail' | 'subtotal' | 'total'

export interface FinancingDisplayRow {
  kind: FinancingDisplayKind
  key: string
  groupId: string
  supplierName: string
  detail?: FinancingRow
  financingAmount: number
  purchaseAmount: number
  difference: number
  loanBalance: number
  rowCount: number
}

export interface F4FinancingSupplierCandidate {
  sourceRowId: string
  supplierName: string
  purchaseAmount: number
}

export interface UseF4SupplierFinancingOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

const STORAGE_KEY = 'F4-9-rows'
const LEGACY_KEYS = ['F4-9-factoring-rows', 'F4-9-note-rows', 'F4-9-supply-rows', 'F4-9-factoring', 'F4-9-note', 'F4-9-supply', 'F4-9-supplychain']
const DETAIL_KEY = 'F4-2-rows'
const NOTE_KEY = 'F4-9-audit-note'
const CONCLUSION_KEY = 'F4-9-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'F4-9-note-conclusion'
const TOLERANCE = 0.005

function generateId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function emptyF4FinancingRow(
  seq: number,
  attSlot = seq,
  groupId?: string,
  supplierName = '',
): StoredFinancingRow {
  return {
    rowId: generateId('f4sf'),
    seq,
    attSlot,
    groupId: groupId || generateId('grp'),
    supplierName,
    promisedPayer: '',
    financingNo: '',
    fundProvider: '',
    status: '',
    financingAmount: 0,
    supplierSignDate: '',
    disbursementDate: '',
    transferDate: '',
    promisedRepayDate: '',
    actualRepayDate: '',
    purchaseAmount: 0,
    loanBalance: 0,
    remark: '',
    sourceRowId: '',
  }
}

export function isBlankF4FinancingRow(row: StoredFinancingRow): boolean {
  return !row.supplierName && !row.promisedPayer && !row.financingNo && !row.fundProvider
    && !row.status && !row.financingAmount && !row.supplierSignDate && !row.disbursementDate
    && !row.transferDate && !row.promisedRepayDate && !row.actualRepayDate
    && !row.purchaseAmount && !row.loanBalance && !row.remark
}

/** 差异 = 融资金额 − 本期采购金额 */
export function calcF4FinancingDifference(financingAmount: number, purchaseAmount: number): number {
  return Math.round((financingAmount - purchaseAmount) * 100) / 100
}

export function computeF4FinancingRow(stored: StoredFinancingRow): FinancingRow {
  const financingAmount = parseNum(stored.financingAmount)
  const purchaseAmount = parseNum(stored.purchaseAmount)
  const difference = calcF4FinancingDifference(financingAmount, purchaseAmount)
  const loanBalance = parseNum(stored.loanBalance)
  const riskFlags: string[] = []

  if (financingAmount > 0 && purchaseAmount > 0 && financingAmount - purchaseAmount > TOLERANCE) {
    riskFlags.push('融资金额大于采购金额')
  }
  if (financingAmount > 0 && purchaseAmount <= TOLERANCE) {
    riskFlags.push('缺本期采购金额')
  }
  if (financingAmount > 0 && !stored.financingNo) {
    riskFlags.push('缺融资单号')
  }
  if (financingAmount > 0 && !stored.fundProvider) {
    riskFlags.push('缺资金提供方')
  }
  if (stored.status === '已还款' && loanBalance > TOLERANCE) {
    riskFlags.push('已还款但仍有借款余额')
  }
  if (stored.actualRepayDate && loanBalance > TOLERANCE) {
    riskFlags.push('已还款日仍有借款余额')
  }
  if (!stored.actualRepayDate && financingAmount > TOLERANCE && loanBalance <= TOLERANCE && stored.status !== '已还款') {
    riskFlags.push('未登记借款余额')
  }

  let highlightLevel: FinancingRow['highlightLevel'] = 'none'
  if (riskFlags.some((flag) => flag.includes('大于采购') || flag.includes('已还款但仍'))) {
    highlightLevel = 'danger'
  } else if (riskFlags.length) {
    highlightLevel = 'warning'
  }

  return {
    ...stored,
    financingAmount,
    purchaseAmount,
    difference,
    loanBalance,
    riskFlags,
    highlightLevel,
  }
}

function migrateLegacyRegionRow(raw: any, i: number, region: string): StoredFinancingRow {
  const base = emptyF4FinancingRow(i + 1, i + 1)
  const supplier = String(raw?.supplierName || raw?.supplier || raw?.vendor || '')
  const amount = parseNum(raw?.financingAmount ?? raw?.amount ?? raw?.noteAmount)
  const remarkParts = [
    region ? `原区域：${region}` : '',
    raw?.hasRecourse ? `有追索权：${raw.hasRecourse}` : '',
    raw?.isDerecognized || raw?.derecognized ? `终止确认：${raw.isDerecognized || raw.derecognized}` : '',
    raw?.reportingAccount ? `列报科目：${raw.reportingAccount}` : '',
    raw?.noteType ? `票据类型：${raw.noteType}` : '',
    raw?.isEndorsed ? `背书：${raw.isEndorsed}` : '',
    raw?.reportingAdequacy || raw?.reportingAppropriate ? `列报适当性：${raw.reportingAdequacy || raw.reportingAppropriate}` : '',
    raw?.coreEnterprise ? `核心企业：${raw.coreEnterprise}` : '',
    raw?.platform ? `平台：${raw.platform}` : '',
    raw?.hasModifiedTerms || raw?.paymentTermsChanged ? `付款条件变更：${raw.hasModifiedTerms || raw.paymentTermsChanged}` : '',
    raw?.shouldReclassify || raw?.needReclass ? `应重分类：${raw.shouldReclassify || raw.needReclass}` : '',
    raw?.auditEvaluation || '',
    raw?.remark || '',
  ].filter(Boolean)

  return {
    ...base,
    rowId: String(raw?.rowId || raw?.id || generateId('f4sf')),
    groupId: String(raw?.groupId || generateId('grp')),
    supplierName: supplier,
    promisedPayer: String(raw?.promisedPayer || raw?.coreEnterprise || ''),
    financingNo: String(raw?.financingNo || ''),
    fundProvider: String(raw?.fundProvider || raw?.factoringCompany || raw?.factor || raw?.platform || ''),
    status: String(raw?.status || ''),
    financingAmount: amount,
    supplierSignDate: String(raw?.supplierSignDate || raw?.date || raw?.startDate || raw?.issueDate || ''),
    disbursementDate: String(raw?.disbursementDate || ''),
    transferDate: String(raw?.transferDate || ''),
    promisedRepayDate: String(raw?.promisedRepayDate || raw?.dueDate || ''),
    actualRepayDate: String(raw?.actualRepayDate || ''),
    purchaseAmount: parseNum(raw?.purchaseAmount),
    loanBalance: parseNum(raw?.loanBalance ?? (raw?.discountAmount != null ? raw.discountAmount : amount)),
    remark: remarkParts.join('；'),
    sourceRowId: String(raw?.sourceRowId || ''),
    attSlot: Number(raw?.attSlot) || i + 1,
  }
}

export function migrateF4FinancingRows(value: string | null | undefined): StoredFinancingRow[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed)) return []
    const rows = parsed.map((raw: any, i: number) => {
      if (raw?.financingNo != null || raw?.fundProvider != null || raw?.purchaseAmount != null || raw?.groupId) {
        const base = emptyF4FinancingRow(i + 1, Number(raw?.attSlot) || i + 1, raw?.groupId)
        return {
          ...base,
          rowId: String(raw?.rowId || raw?.id || generateId('f4sf')),
          groupId: String(raw?.groupId || base.groupId),
          supplierName: String(raw?.supplierName || raw?.supplier || raw?.vendor || ''),
          promisedPayer: String(raw?.promisedPayer || ''),
          financingNo: String(raw?.financingNo || ''),
          fundProvider: String(raw?.fundProvider || ''),
          status: String(raw?.status || ''),
          financingAmount: parseNum(raw?.financingAmount ?? raw?.amount),
          supplierSignDate: String(raw?.supplierSignDate || ''),
          disbursementDate: String(raw?.disbursementDate || ''),
          transferDate: String(raw?.transferDate || ''),
          promisedRepayDate: String(raw?.promisedRepayDate || ''),
          actualRepayDate: String(raw?.actualRepayDate || ''),
          purchaseAmount: parseNum(raw?.purchaseAmount),
          loanBalance: parseNum(raw?.loanBalance),
          remark: String(raw?.remark || ''),
          sourceRowId: String(raw?.sourceRowId || ''),
          attSlot: Number(raw?.attSlot) || i + 1,
          seq: Number(raw?.seq) || i + 1,
        } as StoredFinancingRow
      }
      return migrateLegacyRegionRow(raw, i, '')
    })
    const pruned = rows.filter((row) => !isBlankF4FinancingRow(row))
    const kept = pruned.length ? pruned : rows.slice(0, 1)
    return kept.map((row, i) => ({ ...row, seq: i + 1 }))
  } catch {
    return []
  }
}

/** 从 F4-2 提取供应商候选（按债权人归集本期贷方作为采购参考） */
export function extractF4FinancingSupplierCandidates(
  detailJson: string | null | undefined,
): F4FinancingSupplierCandidate[] {
  if (!detailJson) return []
  try {
    const rows = migrateF4DetailRows(detailJson)
    const map = new Map<string, F4FinancingSupplierCandidate>()
    for (const row of rows) {
      const name = (row.creditor || '').trim()
      if (!name) continue
      const existing = map.get(name)
      const purchase = parseNum(row.currentCredit)
      if (existing) {
        existing.purchaseAmount = Math.round((existing.purchaseAmount + purchase) * 100) / 100
        existing.sourceRowId = `${existing.sourceRowId}|${row.rowId}`
      } else {
        map.set(name, {
          sourceRowId: row.rowId,
          supplierName: name,
          purchaseAmount: purchase,
        })
      }
    }
    return [...map.values()].sort((a, b) => b.purchaseAmount - a.purchaseAmount)
  } catch {
    return []
  }
}

export function buildF4FinancingDisplayRows(rows: FinancingRow[]): FinancingDisplayRow[] {
  const result: FinancingDisplayRow[] = []
  const groups = new Map<string, FinancingRow[]>()
  for (const row of rows) {
    const list = groups.get(row.groupId) || []
    list.push(row)
    groups.set(row.groupId, list)
  }

  let totalFinancing = 0
  let totalPurchase = 0
  let totalLoan = 0

  for (const [groupId, list] of groups) {
    const supplierName = list[0]?.supplierName || '未命名供应商'
    for (const detail of list) {
      result.push({
        kind: 'detail',
        key: detail.rowId,
        groupId,
        supplierName,
        detail,
        financingAmount: detail.financingAmount,
        purchaseAmount: detail.purchaseAmount,
        difference: detail.difference,
        loanBalance: detail.loanBalance,
        rowCount: 1,
      })
    }
    const financingAmount = calcSubtotal(list.map((r) => r.financingAmount))
    const purchaseAmount = calcSubtotal(list.map((r) => r.purchaseAmount))
    const loanBalance = calcSubtotal(list.map((r) => r.loanBalance))
    const difference = calcF4FinancingDifference(financingAmount, purchaseAmount)
    result.push({
      kind: 'subtotal',
      key: `sub-${groupId}`,
      groupId,
      supplierName,
      financingAmount,
      purchaseAmount,
      difference,
      loanBalance,
      rowCount: list.length,
    })
    totalFinancing += financingAmount
    totalPurchase += purchaseAmount
    totalLoan += loanBalance
  }

  if (rows.length) {
    result.push({
      kind: 'total',
      key: 'grand-total',
      groupId: '',
      supplierName: '合计',
      financingAmount: Math.round(totalFinancing * 100) / 100,
      purchaseAmount: Math.round(totalPurchase * 100) / 100,
      difference: calcF4FinancingDifference(totalFinancing, totalPurchase),
      loanBalance: Math.round(totalLoan * 100) / 100,
      rowCount: rows.length,
    })
  }
  return result
}

export function useF4SupplierFinancing(options: UseF4SupplierFinancingOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersisted = ''

  const storedRows = ref<StoredFinancingRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawRows(): string | null | undefined {
    const current = readRowJson(allResponses.value.get(STORAGE_KEY))
    if (current) return current
    // 合并旧三区数据
    const merged: StoredFinancingRow[] = []
    for (const key of LEGACY_KEYS) {
      const legacy = readRowJson(allResponses.value.get(key))
      if (!legacy) continue
      const region = key.includes('factor') ? '保理' : key.includes('note') ? '票据' : key.includes('supply') ? '供应链' : ''
      try {
        const parsed = JSON.parse(legacy)
        if (Array.isArray(parsed)) {
          parsed.forEach((raw, i) => merged.push(migrateLegacyRegionRow(raw, merged.length + i, region)))
        }
      } catch { /* ignore */ }
    }
    return merged.length ? JSON.stringify(merged) : null
  }

  function loadRows(): void {
    storedRows.value = migrateF4FinancingRows(rawRows())
    if (!storedRows.value.length) {
      storedRows.value = [emptyF4FinancingRow(1)]
    }
  }

  watch(() => rawRows(), (raw) => {
    if (raw && (raw === lastPersisted || raw === JSON.stringify(storedRows.value))) return
    loadRows()
  }, { immediate: true })

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark,
    ],
    ([note, conclusion, legacy]) => {
      auditNote.value = typeof note === 'string' ? note : ''
      auditConclusion.value = (typeof conclusion === 'string' && conclusion)
        || (typeof legacy === 'string' ? legacy : '')
        || ''
    },
    { immediate: true },
  )

  const rows = computed(() => storedRows.value.map(computeF4FinancingRow)) as ComputedRef<FinancingRow[]>
  const displayRows = computed(() => buildF4FinancingDisplayRows(rows.value))

  const summary = computed(() => {
    const total = displayRows.value.find((r) => r.kind === 'total')
    const overPurchase = rows.value.filter((r) => r.difference > TOLERANCE)
    const suppliers = new Set(rows.value.map((r) => r.groupId)).size
    return {
      supplierCount: suppliers,
      rowCount: rows.value.filter((r) => !isBlankF4FinancingRow(r)).length,
      financingTotal: total?.financingAmount || 0,
      purchaseTotal: total?.purchaseAmount || 0,
      differenceTotal: total?.difference || 0,
      loanTotal: total?.loanBalance || 0,
      overPurchaseCount: overPurchase.length,
      overPurchaseAmount: calcSubtotal(overPurchase.map((r) => r.difference)),
      highRiskCount: rows.value.filter((r) => r.highlightLevel === 'danger').length,
    }
  })

  const pendingSyncCount = computed(() => {
    const existing = new Set(rows.value.map((r) => r.supplierName.trim()).filter(Boolean))
    return extractF4FinancingSupplierCandidates(readRowJson(allResponses.value.get(DETAIL_KEY)))
      .filter((c) => !existing.has(c.supplierName)).length
  })

  function nextAttSlot(): number {
    return Math.max(0, ...storedRows.value.map((r) => Number(r.attSlot) || 0)) + 1
  }

  function persist(): void {
    const json = JSON.stringify(storedRows.value)
    lastPersisted = json
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function setText(key: string, value: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: value })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  function renumber(): void {
    storedRows.value.forEach((row, i) => { row.seq = i + 1 })
  }

  /** 新增供应商分组（带一行空白明细） */
  function addSupplierGroup(supplierName = ''): void {
    if (readonly.value) return
    const groupId = generateId('grp')
    storedRows.value.push(emptyF4FinancingRow(storedRows.value.length + 1, nextAttSlot(), groupId, supplierName))
    renumber()
    persist()
  }

  /** 在指定供应商下插入融资明细行 */
  function addRowInGroup(groupId: string): void {
    if (readonly.value) return
    const siblings = storedRows.value.filter((r) => r.groupId === groupId)
    const supplierName = siblings[0]?.supplierName || ''
    const lastIdx = storedRows.value.map((r) => r.groupId).lastIndexOf(groupId)
    const insertAt = lastIdx >= 0 ? lastIdx + 1 : storedRows.value.length
    const row = emptyF4FinancingRow(0, nextAttSlot(), groupId, supplierName)
    storedRows.value.splice(insertAt, 0, row)
    renumber()
    persist()
  }

  function addRow(): void {
    if (readonly.value) return
    if (!storedRows.value.length) {
      addSupplierGroup()
      return
    }
    // 默认追加到最后一个供应商组
    const lastGroup = storedRows.value[storedRows.value.length - 1].groupId
    addRowInGroup(lastGroup)
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    if (storedRows.value.length <= 1) {
      storedRows.value = [emptyF4FinancingRow(1)]
      persist()
      return
    }
    const idx = storedRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedRows.value.splice(idx, 1)
    renumber()
    persist()
  }

  function removeSupplierGroup(groupId: string): void {
    if (readonly.value) return
    storedRows.value = storedRows.value.filter((r) => r.groupId !== groupId)
    if (!storedRows.value.length) storedRows.value = [emptyF4FinancingRow(1)]
    renumber()
    persist()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = storedRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numericFields = ['financingAmount', 'purchaseAmount', 'loanBalance']
    if (field === 'supplierName') {
      const name = String(value ?? '')
      // 同组供应商名称联动
      for (const item of storedRows.value) {
        if (item.groupId === row.groupId) item.supplierName = name
      }
    } else if (numericFields.includes(field)) {
      ;(row as any)[field] = parseNum(value as string | number | null | undefined)
    } else {
      ;(row as any)[field] = String(value ?? '')
    }
    persist()
  }

  function syncFromDetail(): number {
    if (readonly.value) return 0
    const candidates = extractF4FinancingSupplierCandidates(readRowJson(allResponses.value.get(DETAIL_KEY)))
    const existing = new Set(storedRows.value.map((r) => r.supplierName.trim()).filter(Boolean))
    let added = 0
    // 清掉唯一空白占位行
    if (storedRows.value.length === 1 && isBlankF4FinancingRow(storedRows.value[0])) {
      storedRows.value = []
    }
    for (const candidate of candidates) {
      if (existing.has(candidate.supplierName)) continue
      const groupId = generateId('grp')
      const row = emptyF4FinancingRow(storedRows.value.length + 1, nextAttSlot(), groupId, candidate.supplierName)
      row.sourceRowId = candidate.sourceRowId
      row.purchaseAmount = candidate.purchaseAmount
      storedRows.value.push(row)
      existing.add(candidate.supplierName)
      added += 1
    }
    if (!storedRows.value.length) storedRows.value = [emptyF4FinancingRow(1)]
    renumber()
    persist()
    return added
  }

  function mergeOcrFields(rowId: string, fields: F4FinancingOcrFields, overwrite = false): void {
    if (readonly.value) return
    const row = storedRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const textFields: Array<keyof F4FinancingOcrFields> = [
      'supplierName', 'promisedPayer', 'financingNo', 'fundProvider', 'status',
      'supplierSignDate', 'disbursementDate', 'transferDate', 'promisedRepayDate',
      'actualRepayDate', 'remark',
    ]
    const numericFields: Array<keyof F4FinancingOcrFields> = [
      'financingAmount', 'purchaseAmount', 'loanBalance',
    ]
    for (const key of textFields) {
      const next = fields[key]
      if (next == null || next === '') continue
      if (!overwrite && (row as any)[key]) continue
      if (key === 'supplierName') {
        const name = String(next)
        for (const item of storedRows.value) {
          if (item.groupId === row.groupId) item.supplierName = name
        }
      } else {
        ;(row as any)[key] = String(next)
      }
    }
    for (const key of numericFields) {
      const next = fields[key]
      if (next == null || next === '' || next === 0) continue
      if (!overwrite && parseNum((row as any)[key])) continue
      ;(row as any)[key] = parseNum(next as string | number)
    }
    persist()
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    setText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    setText(CONCLUSION_KEY, value)
  }

  function rowClassName({ row }: { row: FinancingDisplayRow }): string {
    if (row.kind === 'subtotal') return 'row-subtotal'
    if (row.kind === 'total') return 'row-total'
    const level = row.detail?.highlightLevel
    if (level === 'danger') return 'row-danger'
    if (level === 'warning') return 'row-warning'
    return ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    displayRows,
    summary,
    pendingSyncCount,
    auditNote,
    auditConclusion,
    loadRows,
    addSupplierGroup,
    addRowInGroup,
    addRow,
    removeRow,
    removeSupplierGroup,
    updateCell,
    syncFromDetail,
    mergeOcrFields,
    saveAuditNote,
    saveAuditConclusion,
    rowClassName,
  }
}

export default useF4SupplierFinancing
