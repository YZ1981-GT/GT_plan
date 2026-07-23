/**
 * useK1LargeAmountSheet — K1-5 大额其他应收款情况分析表（对齐致同 Excel）
 *
 * 列：债务人 | 期初 | 借方 | 贷方 | 期末未审(公式) | 坏账准备 | 账面价值(公式) |
 *     账龄 | 经济业务 | 关联方 | 协议索引 | 期后收款 | 占比
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useG2IntRecFormulaEngine'
import { calcAssetEndBalance, calcNetValue, calcProportion } from './useK1FormulaEngine'
import {
  loadK1DetailPartials,
  extractTopLargeFromK1Detail,
} from './k1CrossHelpers'
import { computeMissingRelatedParties } from './useF1RelatedParty'
import { matchK1RelatedPartyFromRegistry } from './useK1RelatedParty'
import {
  fetchK1PostPaymentFromLedger,
  resolveK1BsDate,
} from './k1PostPaymentFromLedger'

export const K1_LARGE_STORAGE_KEY = 'K1-5-large-amount'
/** K1-12 特定样本读取兼容键 */
export const K1_LARGE_LEGACY_ROWS_KEY = 'K1-5-large-rows'

export const K1_LARGE_TOP_N = 10

export interface K1LargeAmountSheetRow {
  id: string
  seq: number
  debtorName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  endUnaudited: number
  provision: number
  bookValue: number
  aging: string
  businessDesc: string
  isRelated: boolean
  contractIndex: string
  postCollection: number
  proportion: number | null
  sourceRowId: string
}

interface StoredK1LargeRow {
  id: string
  seq: number
  debtorName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  provision: number
  aging: string
  businessDesc: string
  isRelated: boolean
  contractIndex: string
  postCollection: number
  sourceRowId: string
}

export interface K1LargeAmountSummary {
  endUnaudited: number
  provision: number
  bookValue: number
  postCollection: number
  relatedCount: number
  detailTotal: number
  topTotalProportion: number | null
}

function generateId(): string {
  return `k1-large-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function computeRow(stored: StoredK1LargeRow, detailTotal: number): K1LargeAmountSheetRow {
  const endUnaudited = calcAssetEndBalance(
    stored.openingBalance,
    stored.periodDebit,
    stored.periodCredit,
  )
  const bookValue = calcNetValue(endUnaudited, stored.provision)
  return {
    ...stored,
    endUnaudited,
    bookValue,
    proportion: calcProportion(endUnaudited, detailTotal),
  }
}

function createEmptyRow(seq: number): StoredK1LargeRow {
  return {
    id: generateId(),
    seq,
    debtorName: '',
    openingBalance: 0,
    periodDebit: 0,
    periodCredit: 0,
    provision: 0,
    aging: '',
    businessDesc: '',
    isRelated: false,
    contractIndex: '',
    postCollection: 0,
    sourceRowId: '',
  }
}

function migrateLegacyRow(row: any, seq: number): StoredK1LargeRow {
  if (row && ('debtorName' in row || 'counterparty' in row || 'openingBalance' in row || 'beginBalance' in row)) {
    return {
      id: String(row.id || row.rowId || generateId()),
      seq: Number(row.seq) || seq,
      debtorName: String(row.debtorName || row.counterparty || ''),
      openingBalance: parseNum(row.openingBalance ?? row.beginBalance),
      periodDebit: parseNum(row.periodDebit ?? row.debit),
      periodCredit: parseNum(row.periodCredit ?? row.credit),
      provision: parseNum(row.provision),
      aging: String(row.aging || ''),
      businessDesc: String(row.businessDesc || row.nature || ''),
      isRelated: Boolean(row.isRelated ?? row.relatedParty === '是'),
      contractIndex: String(row.contractIndex || ''),
      postCollection: parseNum(row.postCollection),
      sourceRowId: String(row.sourceRowId || ''),
    }
  }
  return createEmptyRow(seq)
}

function safeParseBundle(jsonStr: string | null | undefined): {
  rows: StoredK1LargeRow[]
  auditNote: string
  conclusion: string
  conclusionOption: string
} {
  if (!jsonStr) return { rows: [], auditNote: '', conclusion: '', conclusionOption: '' }
  try {
    const parsed = JSON.parse(jsonStr)
    if (Array.isArray(parsed)) {
      return {
        rows: parsed.map((r, i) => migrateLegacyRow(r, i + 1)),
        auditNote: '',
        conclusion: '',
        conclusionOption: '',
      }
    }
    const rawRows = parsed.rows ?? parsed.tables?.rows
    const rows = Array.isArray(rawRows)
      ? rawRows.map((r: any, i: number) => migrateLegacyRow(r, i + 1))
      : []
    return {
      rows,
      auditNote: String(parsed.auditNote ?? ''),
      conclusion: String(parsed.conclusion ?? ''),
      conclusionOption: String(parsed.conclusionOption ?? ''),
    }
  } catch {
    return { rows: [], auditNote: '', conclusion: '', conclusionOption: '' }
  }
}

function buildLegacyRowsPayload(rows: K1LargeAmountSheetRow[]): string {
  return JSON.stringify(
    rows.map((r) => ({
      id: r.id,
      counterparty: r.debtorName,
      endBalance: r.endUnaudited,
      proportion: r.proportion,
      nature: r.businessDesc,
    })),
  )
}

export interface UseK1LargeAmountSheetOptions {
  allResponses: Ref<Map<string, any>>
  isReadonly?: Ref<boolean>
  relatedParties?: Ref<string[]>
  projectId?: Ref<string>
  bsDate?: Ref<string>
  year?: Ref<number | undefined>
  onSave: (itemId: string, payload: { remark: string }) => void
}

/** B19 清单是否匹配债务人名称（未考虑是否已勾选关联方） */
export function isK1LargeRowB19Match(debtorName: string, registry: string[]): boolean {
  return matchK1RelatedPartyFromRegistry(debtorName, registry) !== '否'
}

/** B19 匹配但未标记关联方的行数（纯函数，便于测试） */
export function countK1LargeB19Suspects(
  rows: Array<{ debtorName: string; isRelated: boolean }>,
  registry: string[],
): number {
  if (!registry.length) return 0
  return rows.filter((r) => !r.isRelated && isK1LargeRowB19Match(r.debtorName, registry)).length
}

/** 将 B19 匹配到的行勾选为关联方，返回更新行数 */
export function applyB19MatchToLargeRows(
  rows: StoredK1LargeRow[],
  registry: string[],
): number {
  if (!registry.length) return 0
  let count = 0
  for (const row of rows) {
    if (row.isRelated) continue
    if (isK1LargeRowB19Match(row.debtorName, registry)) {
      row.isRelated = true
      count += 1
    }
  }
  return count
}

/** B19 清单中未在本表出现的关联方名称 */
export function computeK1LargeMissingFromRegistry(
  registry: string[],
  rows: Array<{ debtorName: string }>,
): string[] {
  return computeMissingRelatedParties(registry, rows.map((r) => ({ partyName: r.debtorName })))
}

export function useK1LargeAmountSheet(options: UseK1LargeAmountSheetOptions) {
  const { allResponses, isReadonly, relatedParties, onSave, projectId, bsDate, year } = options
  const readonly = isReadonly ?? ref(false)
  const registry = computed(() => relatedParties?.value ?? [])
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const postPaymentLoading = ref(false)

  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  function loadMeta(): void {
    const bundle = safeParseBundle(allResponses.value.get(K1_LARGE_STORAGE_KEY)?.remark)
    auditNote.value = bundle.auditNote
    conclusion.value = bundle.conclusion
    conclusionOption.value = bundle.conclusionOption
  }

  watch(
    () => allResponses.value.get(K1_LARGE_STORAGE_KEY)?.remark,
    () => loadMeta(),
    { immediate: true },
  )

  const detailTotal: ComputedRef<number> = computed(() => {
    const raw = allResponses.value.get('K1-2-end-subtotal')?.remark
    const sub = parseNum(raw)
    if (sub > 0) return sub
    const details = loadK1DetailPartials(allResponses.value)
    return calcSubtotal(details.map((d) => d.endBalance))
  })

  const dataRows: ComputedRef<K1LargeAmountSheetRow[]> = computed(() => {
    const bundle = safeParseBundle(allResponses.value.get(K1_LARGE_STORAGE_KEY)?.remark)
    const total = detailTotal.value
    return bundle.rows.map((r) => computeRow(r, total))
  })

  const displayRows: ComputedRef<K1LargeAmountSheetRow[]> = computed(() => {
    const rows = dataRows.value
    if (!rows.length) return rows
    const t = summary.value
    return [
      ...rows,
      {
        id: '__subtotal__',
        seq: 0,
        debtorName: '合计',
        openingBalance: calcSubtotal(rows.map((r) => r.openingBalance)),
        periodDebit: calcSubtotal(rows.map((r) => r.periodDebit)),
        periodCredit: calcSubtotal(rows.map((r) => r.periodCredit)),
        endUnaudited: t.endUnaudited,
        provision: t.provision,
        bookValue: t.bookValue,
        aging: '',
        businessDesc: '',
        isRelated: false,
        contractIndex: '',
        postCollection: t.postCollection,
        proportion: t.topTotalProportion,
        sourceRowId: '',
      },
    ]
  })

  const summary: ComputedRef<K1LargeAmountSummary> = computed(() => {
    const rows = dataRows.value
    const endUnaudited = calcSubtotal(rows.map((r) => r.endUnaudited))
    return {
      endUnaudited,
      provision: calcSubtotal(rows.map((r) => r.provision)),
      bookValue: calcSubtotal(rows.map((r) => r.bookValue)),
      postCollection: calcSubtotal(rows.map((r) => r.postCollection)),
      relatedCount: rows.filter((r) => r.isRelated).length,
      detailTotal: detailTotal.value,
      topTotalProportion: calcProportion(endUnaudited, detailTotal.value),
    }
  })

  const isOverTopN = computed(() => dataRows.value.length > K1_LARGE_TOP_N)

  const b19SuspectRows = computed(() =>
    dataRows.value.filter(
      (r) => !r.isRelated && isK1LargeRowB19Match(r.debtorName, registry.value),
    ),
  )

  const b19MissingFromTable = computed(() =>
    computeK1LargeMissingFromRegistry(registry.value, dataRows.value),
  )

  function isB19Suspect(row: K1LargeAmountSheetRow): boolean {
    return !row.isRelated && isK1LargeRowB19Match(row.debtorName, registry.value)
  }

  function applyB19Match(): number {
    if (readonly.value || !registry.value.length) return 0
    const current = getStoredRows()
    const count = applyB19MatchToLargeRows(current, registry.value)
    if (count) persistRows(current)
    return count
  }

  function isMetaRow(row: K1LargeAmountSheetRow): boolean {
    return row.id === '__subtotal__'
  }

  function getStoredRows(): StoredK1LargeRow[] {
    return safeParseBundle(allResponses.value.get(K1_LARGE_STORAGE_KEY)?.remark).rows
  }

  function serializeBundle(rows: StoredK1LargeRow[]): string {
    return JSON.stringify({
      rows,
      auditNote: auditNote.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  function publishLegacyRows(computedRows: K1LargeAmountSheetRow[]): void {
    const legacy = buildLegacyRowsPayload(computedRows.filter((r) => r.id !== '__subtotal__'))
    allResponses.value.set(K1_LARGE_LEGACY_ROWS_KEY, {
      item_id: K1_LARGE_LEGACY_ROWS_KEY,
      conclusion: null,
      remark: legacy,
    })
    onSave(K1_LARGE_LEGACY_ROWS_KEY, { remark: legacy })
  }

  function persistRows(rows: StoredK1LargeRow[]): void {
    const remark = serializeBundle(rows)
    allResponses.value.set(K1_LARGE_STORAGE_KEY, {
      item_id: K1_LARGE_STORAGE_KEY,
      conclusion: null,
      remark,
    })
    debounceSave(K1_LARGE_STORAGE_KEY, remark)
    const total = detailTotal.value
    publishLegacyRows(rows.map((r) => computeRow(r, total)))
  }

  function debounceSave(itemId: string, remark: string): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      onSave(itemId, { remark })
    }, 400)
  }

  function flushSave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    const remark = allResponses.value.get(K1_LARGE_STORAGE_KEY)?.remark
    if (remark != null) onSave(K1_LARGE_STORAGE_KEY, { remark: String(remark) })
  }

  function addRow(): void {
    if (readonly.value) return
    const current = getStoredRows()
    if (current.length >= K1_LARGE_TOP_N) return
    const nextSeq = current.length ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyRow(nextSeq))
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const current = getStoredRows().filter((r) => r.id !== id)
    current.forEach((r, i) => { r.seq = i + 1 })
    persistRows(current)
  }

  function updateCell(rowId: string, field: string, value: string | number | boolean): void {
    if (readonly.value || rowId === '__subtotal__') return
    const current = getStoredRows()
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const alias: Record<string, string> = {
      beginBalance: 'openingBalance',
      debit: 'periodDebit',
      credit: 'periodCredit',
      debtorName: 'debtorName',
      nature: 'businessDesc',
    }
    const key = alias[field] || field
    const numeric = ['openingBalance', 'periodDebit', 'periodCredit', 'provision', 'postCollection']
    if (numeric.includes(key)) {
      ;(current[idx] as any)[key] = typeof value === 'number' ? value : parseNum(value)
    } else if (key === 'isRelated') {
      current[idx].isRelated = Boolean(value)
    } else {
      ;(current[idx] as any)[key] = value
    }
    persistRows(current)
  }

  /** 从 K1-2 按期末余额取前 10 名（不含合并范围内关联方） */
  function importTopFromDetail(replace = true): { imported: number; skippedRelated: number } {
    if (readonly.value) return { imported: 0, skippedRelated: 0 }
    const details = loadK1DetailPartials(allResponses.value)
    const skippedRelated = details.filter((d) => d.relatedParty === '是' && d.endBalance > 0).length
    const top = extractTopLargeFromK1Detail(details, { limit: K1_LARGE_TOP_N })
    if (!top.length) return { imported: 0, skippedRelated }

    if (replace) {
      const fresh = top.map((src, i) => {
        const row = createEmptyRow(i + 1)
        row.debtorName = src.debtorName
        row.openingBalance = src.openingBalance
        row.periodDebit = src.periodDebit
        row.periodCredit = src.periodCredit
        row.provision = src.provision
        row.aging = src.aging
        row.businessDesc = src.businessDesc
        row.isRelated = src.isRelated
        row.sourceRowId = src.sourceRowId
        return row
      })
      persistRows(fresh)
      return { imported: fresh.length, skippedRelated }
    }

    const current = getStoredRows()
    const byName = new Map(current.map((r) => [r.debtorName.trim(), r]))
    let imported = 0
    let nextSeq = current.length ? Math.max(...current.map((r) => r.seq)) + 1 : 1

    for (const src of top) {
      const name = src.debtorName.trim()
      if (!name) continue
      const existing = byName.get(name)
      if (existing) {
        existing.openingBalance = src.openingBalance
        existing.periodDebit = src.periodDebit
        existing.periodCredit = src.periodCredit
        existing.provision = src.provision
        if (src.aging) existing.aging = src.aging
        if (src.businessDesc) existing.businessDesc = src.businessDesc
        existing.isRelated = src.isRelated
        existing.sourceRowId = src.sourceRowId
      } else if (current.length < K1_LARGE_TOP_N) {
        const row = createEmptyRow(nextSeq++)
        row.debtorName = name
        row.openingBalance = src.openingBalance
        row.periodDebit = src.periodDebit
        row.periodCredit = src.periodCredit
        row.provision = src.provision
        row.aging = src.aging
        row.businessDesc = src.businessDesc
        row.isRelated = src.isRelated
        row.sourceRowId = src.sourceRowId
        current.push(row)
        byName.set(name, row)
        imported += 1
      }
    }

    persistRows(current.slice(0, K1_LARGE_TOP_N))
    return { imported, skippedRelated }
  }

  function persistTextFields(): void {
    persistRows(getStoredRows())
  }

  /** 从序时账 1221 贷方取期后回款，按债务人归集填入 postCollection */
  async function importPostPaymentFromLedger(monthsAfter = 6): Promise<{ matched: number; filledAmount: number }> {
    const empty = { matched: 0, filledAmount: 0 }
    if (readonly.value) return empty
    postPaymentLoading.value = true
    try {
      const current = getStoredRows()
      const result = await fetchK1PostPaymentFromLedger({
        projectId: projectId?.value || '',
        bsDate: resolveK1BsDate(bsDate?.value, year?.value),
        rows: current.map((r) => ({ id: r.id, name: r.debtorName })),
        monthsAfter,
      })
      if (result.cancelled || result.matched === 0) return empty
      for (const [id, amt] of result.amounts) {
        const row = current.find((r) => r.id === id)
        if (row) row.postCollection = amt
      }
      persistRows(current)
      return { matched: result.matched, filledAmount: result.filledAmount }
    } finally {
      postPaymentLoading.value = false
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    auditNote,
    conclusion,
    conclusionOption,
    dataRows,
    displayRows,
    summary,
    detailTotal,
    isOverTopN,
    isMetaRow,
    addRow,
    removeRow,
    updateCell,
    importTopFromDetail,
    importPostPaymentFromLedger,
    postPaymentLoading,
    persistTextFields,
    flushSave,
    registry,
    b19SuspectRows,
    b19MissingFromTable,
    isB19Suspect,
    applyB19Match,
  }
}

export default useK1LargeAmountSheet
