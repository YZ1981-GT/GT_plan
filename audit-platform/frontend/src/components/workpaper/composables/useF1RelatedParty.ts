/**
 * useF1RelatedParty — F1-6 预付账款关联方及交易检查表
 *
 * Excel 13 列：关联方|关系|期初|借方|贷方|期末(自动)|坏账|账面价值(自动)|
 * 账龄|款项性质|期后到货|索引|备注
 * 期末 = 期初 + 借方 − 贷方（借方科目）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcRelatedPartyEndBalance } from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { RelatedPartyImportRow } from './useF1CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RelatedPartyRow {
  rowId: string
  partyName: string           // 关联方名称
  relationship: string        // 关联关系
  priorBalance: number        // 期初余额
  debit: number               // 借方发生额
  credit: number              // 贷方发生额
  endBalance: number          // 期末余额 = 期初+借方−贷方
  badDebt: number             // 减：坏账准备
  bookValue: number           // 账面价值 = 期末−坏账
  agingDescription: string    // 发生时间及账龄
  natureDescription: string   // 发生原因（款项性质）
  postPeriodDelivery: number  // 期后到货
  indexRef: string            // 索引号
  remark: string              // 备注
}

export interface UseF1RelatedPartyOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  /** 项目关联方清单（来自登记表），用于完整性校验防漏列 */
  relatedParties?: Ref<string[]>
}

/** 关联方名称模糊匹配（双向包含，忽略大小写/空白） */
export function relatedPartyNameMatches(a: string, b: string): boolean {
  const na = String(a || '').trim().toLowerCase().replace(/\s+/g, '')
  const nb = String(b || '').trim().toLowerCase().replace(/\s+/g, '')
  if (!na || !nb) return false
  return na === nb || na.includes(nb) || nb.includes(na)
}

/** 清单中未在 F1-6 行内识别到的关联方（纯函数，便于测试） */
export function computeMissingRelatedParties(
  registry: string[],
  rows: Array<{ partyName: string }>,
): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  for (const name of registry) {
    const key = String(name || '').trim()
    if (!key || seen.has(key)) continue
    seen.add(key)
    const matched = rows.some((r) => relatedPartyNameMatches(r.partyName, key))
    if (!matched) out.push(key)
  }
  return out
}

/** Excel 模板「关联关系」枚举 */
export const F1_RELATED_PARTY_RELATIONSHIP_OPTIONS = [
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的近亲属及关联企业',
  '持有5%以上股份的法人或其他组织',
  '联营企业',
  '合营企业',
  '董高监等关键管理人员',
  '其他关联方',
  // F1-2 明细常用值，导入时兼容
  '母公司',
  '子公司',
] as const

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'F1-rp-rows'
const ITEM_ID_NOTE = 'F1-rp-note'
const ITEM_ID_CONCLUSION = 'F1-rp-conclusion'

// ─── Pure helpers ────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

export function recalcRelatedPartyRow(row: RelatedPartyRow): RelatedPartyRow {
  const endBalance = calcRelatedPartyEndBalance(row.priorBalance, row.debit, row.credit)
  const bookValue = endBalance - parseNum(row.badDebt)
  return { ...row, endBalance, bookValue }
}

export function normalizeRelatedPartyRow(raw: any): RelatedPartyRow {
  return recalcRelatedPartyRow({
    rowId: raw.rowId || generateRowId(),
    partyName: raw.partyName || raw.customerName || '',
    relationship: raw.relationship || '',
    priorBalance: parseNum(raw.priorBalance),
    debit: parseNum(raw.debit),
    credit: parseNum(raw.credit),
    endBalance: parseNum(raw.endBalance),
    badDebt: parseNum(raw.badDebt ?? raw.badDebtProvision),
    bookValue: parseNum(raw.bookValue),
    agingDescription: raw.agingDescription || '',
    natureDescription: raw.natureDescription || raw.nature || '',
    postPeriodDelivery: parseNum(raw.postPeriodDelivery ?? raw.postPeriodSettlement),
    indexRef: raw.indexRef || '',
    remark: raw.remark || '',
  })
}

export function createEmptyRelatedPartyRow(): RelatedPartyRow {
  return {
    rowId: generateRowId(),
    partyName: '',
    relationship: '',
    priorBalance: 0,
    debit: 0,
    credit: 0,
    endBalance: 0,
    badDebt: 0,
    bookValue: 0,
    agingDescription: '',
    natureDescription: '',
    postPeriodDelivery: 0,
    indexRef: '',
    remark: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): RelatedPartyRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeRelatedPartyRow) : []
  } catch {
    return []
  }
}

/** 从 F1-2 关联方行合并导入（同名更新金额，保留已填说明） */
export function mergeRelatedPartyFromImport(
  existing: RelatedPartyRow[],
  imported: RelatedPartyImportRow[],
): RelatedPartyRow[] {
  const map = new Map(existing.map(r => [r.partyName, r]))
  for (const src of imported) {
    const name = src.customerName || ''
    if (!name) continue
    const prev = map.get(name)
    if (prev) {
      map.set(
        name,
        recalcRelatedPartyRow({
          ...prev,
          relationship: src.relationType || prev.relationship,
          priorBalance: src.priorAudited,
          debit: src.debit,
          credit: src.credit,
          natureDescription: src.nature || prev.natureDescription,
          agingDescription: src.agingDescription || prev.agingDescription,
          postPeriodDelivery:
            src.postPeriodSettlement != null && src.postPeriodSettlement !== 0
              ? src.postPeriodSettlement
              : prev.postPeriodDelivery,
        }),
      )
    } else {
      map.set(
        name,
        recalcRelatedPartyRow({
          ...createEmptyRelatedPartyRow(),
          partyName: name,
          relationship: src.relationType || '',
          priorBalance: src.priorAudited,
          debit: src.debit,
          credit: src.credit,
          natureDescription: src.nature || '',
          agingDescription: src.agingDescription || '',
          postPeriodDelivery: parseNum(src.postPeriodSettlement),
        }),
      )
    }
  }
  return Array.from(map.values())
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1RelatedParty(options: UseF1RelatedPartyOptions) {
  const { allResponses, debouncedSave, isReadonly, relatedParties } = options

  const rows = ref<RelatedPartyRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (jsonStr) => { rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  function persistRows(): void {
    debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  const subtotalRow = computed(() => ({
    priorBalance: calcSubtotal(rows.value.map(r => r.priorBalance)),
    debit: calcSubtotal(rows.value.map(r => r.debit)),
    credit: calcSubtotal(rows.value.map(r => r.credit)),
    endBalance: calcSubtotal(rows.value.map(r => r.endBalance)),
    badDebt: calcSubtotal(rows.value.map(r => r.badDebt)),
    bookValue: calcSubtotal(rows.value.map(r => r.bookValue)),
    postPeriodDelivery: calcSubtotal(rows.value.map(r => r.postPeriodDelivery)),
  }))

  function importFromCrossSheet(relatedPartyRows: RelatedPartyImportRow[]): void {
    if (isReadonly.value) return
    if (relatedPartyRows.length === 0) return
    rows.value = mergeRelatedPartyFromImport(rows.value, relatedPartyRows)
    persistRows()
  }

  /** 完整性校验：登记表关联方清单中未在本表识别到的名单（可能漏列） */
  const missingRelatedParties: ComputedRef<string[]> = computed(() =>
    computeMissingRelatedParties(relatedParties?.value ?? [], rows.value),
  )

  /** 一键补充漏列关联方（为每个缺失名单追加空行，仅填名称） */
  function addMissingRelatedParties(): number {
    if (isReadonly.value) return 0
    const missing = missingRelatedParties.value
    if (!missing.length) return 0
    const added = missing.map((name) => ({
      ...createEmptyRelatedPartyRow(),
      partyName: name,
    }))
    rows.value = [...rows.value, ...added]
    persistRows()
    return added.length
  }

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRelatedPartyRow()]
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  const NUMERIC = new Set([
    'priorBalance', 'debit', 'credit', 'badDebt', 'postPeriodDelivery',
  ])

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (NUMERIC.has(field)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows.value]
    newRows[idx] = recalcRelatedPartyRow(row)
    rows.value = newRows
    persistRows()
  }

  const auditNote = ref('')
  const conclusion = ref('')

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (val) => { conclusion.value = val || '' },
    { immediate: true },
  )
  watch(() => auditNote.value, (val) => { if (!isReadonly.value) debouncedSave(ITEM_ID_NOTE, { remark: val }) })
  watch(() => conclusion.value, (val) => { if (!isReadonly.value) debouncedSave(ITEM_ID_CONCLUSION, { remark: val }) })

  return {
    rows,
    subtotalRow,
    auditNote,
    conclusion,
    missingRelatedParties,
    addMissingRelatedParties,
    addRow,
    removeRow,
    updateCell,
    importFromCrossSheet,
  }
}

export default useF1RelatedParty
