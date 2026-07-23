import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum, calcCashBalance, calcFxConvert, sumField } from './useE1FormulaEngine'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

export type BankDetailVariant = 'rmb' | 'multi'
export type BankDetailSection = 'principal' | 'accrued'
export type BankDetailGroup = 'institution' | 'finance' | 'other'

export interface BankDetailRow {
  id: string
  section: BankDetailSection
  group: BankDetailGroup
  bankName: string
  totalLedgerBank: string
  accountNo: string
  accountType: string
  opening: number
  increase: number
  decrease: number
  ending: number
  adjustment: number
  audited: number
  statementBalance: number
  accountStatementDiff: number
  confirmAmount: number
  confirmIndexNo: string
  confirmDiff: number
  statementIndexNo: string
  reconciliationIndexNo: string
  restrictedAmount: number
  restrictedReason: string
  interestRate: number
  note: string
  fxCurrency: string
  fxRate: number
  openingFc: number
  increaseFc: number
  decreaseFc: number
  endingFc: number
  adjustmentFc: number
  auditedFc: number
}

export interface BankDetailGroupTotal {
  section: BankDetailSection
  group: BankDetailGroup
  groupName: string
  opening: number
  increase: number
  decrease: number
  ending: number
  adjustment: number
  audited: number
}

const STORAGE_KEY = 'E1-bank-detail-rows'
const VARIANT_KEY = 'E1-bank-variant'
const SECTIONS: BankDetailSection[] = ['principal', 'accrued']
const GROUPS: BankDetailGroup[] = ['institution', 'finance', 'other']

const SECTION_NAMES: Record<BankDetailSection, string> = {
  principal: '（一）存款本金',
  accrued: '（二）应计利息',
}
const GROUP_NAMES: Record<BankDetailGroup, string> = {
  institution: '银行机构',
  finance: '财务公司',
  other: '其他货币资金',
}

const CROSS_SHEET_KEYS = {
  principal: {
    opening: 'E1-bank-detail-principal-opening-unaudited',
    ending: 'E1-bank-detail-principal-total-unaudited',
  },
  institution: {
    opening: 'E1-bank-detail-institution-opening-unaudited',
    ending: 'E1-bank-detail-institution-total-unaudited',
  },
  finance: {
    opening: 'E1-bank-detail-finance-opening-unaudited',
    ending: 'E1-bank-detail-finance-total-unaudited',
  },
  other: {
    opening: 'E1-bank-detail-other-opening-unaudited',
    ending: 'E1-bank-detail-other-total-unaudited',
  },
} as const

const USER_FIELDS: Array<keyof BankDetailRow> = [
  'id', 'section', 'group', 'bankName', 'totalLedgerBank', 'accountNo', 'accountType',
  'opening', 'increase', 'decrease', 'adjustment', 'statementBalance',
  'confirmAmount', 'confirmIndexNo', 'statementIndexNo', 'reconciliationIndexNo',
  'restrictedAmount', 'restrictedReason', 'interestRate', 'note',
  'fxCurrency', 'fxRate', 'openingFc', 'increaseFc', 'decreaseFc', 'adjustmentFc',
]

function generateRowId(section: BankDetailSection, group: BankDetailGroup): string {
  return `bank-${section}-${group}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function recalcRow(row: BankDetailRow, variant: BankDetailVariant): BankDetailRow {
  if (variant === 'multi') {
    const endingFc = calcCashBalance(row.openingFc, row.increaseFc, row.decreaseFc)
    const auditedFc = endingFc + row.adjustmentFc
    const opening = calcFxConvert(row.openingFc, row.fxRate)
    const increase = calcFxConvert(row.increaseFc, row.fxRate)
    const decrease = calcFxConvert(row.decreaseFc, row.fxRate)
    const ending = calcFxConvert(endingFc, row.fxRate)
    const adjustment = calcFxConvert(row.adjustmentFc, row.fxRate)
    const audited = calcFxConvert(auditedFc, row.fxRate)
    return {
      ...row, opening, increase, decrease, ending, adjustment, audited, endingFc, auditedFc,
      accountStatementDiff: audited - row.statementBalance,
      confirmDiff: row.confirmAmount !== 0 ? audited - row.confirmAmount : 0,
    }
  }
  const ending = calcCashBalance(row.opening, row.increase, row.decrease)
  const audited = ending + row.adjustment
  const endingFc = calcCashBalance(row.openingFc, row.increaseFc, row.decreaseFc)
  return {
    ...row, ending, audited, endingFc, auditedFc: endingFc + row.adjustmentFc,
    accountStatementDiff: audited - row.statementBalance,
    confirmDiff: row.confirmAmount !== 0 ? audited - row.confirmAmount : 0,
  }
}

function createEmptyRow(section: BankDetailSection, group: BankDetailGroup): BankDetailRow {
  return {
    id: generateRowId(section, group), section, group,
    bankName: '', totalLedgerBank: '', accountNo: '', accountType: '',
    opening: 0, increase: 0, decrease: 0, ending: 0, adjustment: 0, audited: 0,
    statementBalance: 0, accountStatementDiff: 0, confirmAmount: 0,
    confirmIndexNo: '', confirmDiff: 0, statementIndexNo: '', reconciliationIndexNo: '',
    restrictedAmount: 0, restrictedReason: '', interestRate: 0, note: '',
    fxCurrency: '人民币', fxRate: 1, openingFc: 0, increaseFc: 0, decreaseFc: 0,
    endingFc: 0, adjustmentFc: 0, auditedFc: 0,
  }
}

function defaultRows(): BankDetailRow[] {
  return SECTIONS.flatMap(section => GROUPS.map(group => createEmptyRow(section, group)))
}

export function useE1BankDetail(options: UseE1BaseOptions & { variant: Ref<BankDetailVariant> }) {
  const { allResponses, saveImmediate, isReadonly, variant } = options
  const rows = ref<BankDetailRow[]>([])
  const isLoading = ref(false)

  function loadFromResponses(): void {
    const raw = allResponses.value.get(STORAGE_KEY)?.remark
    if (!raw) { rows.value = defaultRows(); return }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || !parsed.length) { rows.value = defaultRows(); return }
      rows.value = parsed.map((r: Record<string, unknown>) => {
        const legacyGroup = String(r.group || '')
        const section = (['principal', 'accrued'].includes(String(r.section))
          ? String(r.section) : 'principal') as BankDetailSection
        const group = (['institution', 'finance', 'other'].includes(legacyGroup)
          ? legacyGroup : 'institution') as BankDetailGroup
        return recalcRow({
          id: String(r.id || generateRowId(section, group)), section, group,
          bankName: String(r.bankName || ''), totalLedgerBank: String(r.totalLedgerBank || ''),
          accountNo: String(r.accountNo || ''), accountType: String(r.accountType || ''),
          opening: parseNum(r.opening), increase: parseNum(r.increase), decrease: parseNum(r.decrease),
          ending: 0, adjustment: parseNum(r.adjustment), audited: 0,
          statementBalance: parseNum(r.statementBalance), accountStatementDiff: 0,
          confirmAmount: parseNum(r.confirmAmount), confirmIndexNo: String(r.confirmIndexNo || ''),
          confirmDiff: 0, statementIndexNo: String(r.statementIndexNo || ''),
          reconciliationIndexNo: String(r.reconciliationIndexNo || ''),
          restrictedAmount: parseNum(r.restrictedAmount), restrictedReason: String(r.restrictedReason || ''),
          interestRate: parseNum(r.interestRate), note: String(r.note || ''),
          fxCurrency: String(r.fxCurrency || '人民币'), fxRate: parseNum(r.fxRate) || 1,
          openingFc: parseNum(r.openingFc), increaseFc: parseNum(r.increaseFc),
          decreaseFc: parseNum(r.decreaseFc), endingFc: 0,
          adjustmentFc: parseNum(r.adjustmentFc), auditedFc: 0,
        }, variant.value)
      })
    } catch { rows.value = defaultRows() }
  }
  loadFromResponses()

  function serializeRows(): string {
    return JSON.stringify(rows.value.map(row => Object.fromEntries(USER_FIELDS.map(field => [field, row[field]]))))
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, (next, prev) => {
    if (next !== prev && next !== serializeRows()) loadFromResponses()
  })
  watch(variant, next => { rows.value = rows.value.map(row => recalcRow(row, next)) })

  const groupedRows = computed(() => {
    const result = Object.fromEntries(SECTIONS.map(section => [section,
      Object.fromEntries(GROUPS.map(group => [group, [] as BankDetailRow[]])),
    ])) as Record<BankDetailSection, Record<BankDetailGroup, BankDetailRow[]>>
    for (const row of rows.value) result[row.section][row.group].push(row)
    return result
  })

  function calcGroupTotal(section: BankDetailSection, group: BankDetailGroup): BankDetailGroupTotal {
    const records = groupedRows.value[section][group] as unknown as Array<Record<string, unknown>>
    return {
      section, group, groupName: GROUP_NAMES[group],
      opening: sumField(records, 'opening'), increase: sumField(records, 'increase'),
      decrease: sumField(records, 'decrease'), ending: sumField(records, 'ending'),
      adjustment: sumField(records, 'adjustment'), audited: sumField(records, 'audited'),
    }
  }

  const groupTotals: ComputedRef<Record<BankDetailSection, Record<BankDetailGroup, BankDetailGroupTotal>>> = computed(() =>
    Object.fromEntries(SECTIONS.map(section => [section,
      Object.fromEntries(GROUPS.map(group => [group, calcGroupTotal(section, group)])),
    ])) as Record<BankDetailSection, Record<BankDetailGroup, BankDetailGroupTotal>>,
  )

  function crossSheetValues() {
    const principal = groupTotals.value.principal
    return {
      principal: {
        opening: principal.institution.opening + principal.finance.opening,
        ending: principal.institution.ending + principal.finance.ending,
      },
      institution: principal.institution,
      finance: principal.finance,
      other: principal.other,
    }
  }

  function syncCrossSheetTotals(): ChecklistItem[] {
    const values = crossSheetValues()
    const items: ChecklistItem[] = []
    for (const key of Object.keys(CROSS_SHEET_KEYS) as Array<keyof typeof CROSS_SHEET_KEYS>) {
      const mapping = CROSS_SHEET_KEYS[key]
      const value = values[key]
      for (const [period, itemId] of Object.entries(mapping) as Array<['opening' | 'ending', string]>) {
        const remark = String(value[period])
        const item = { item_id: itemId, conclusion: null, remark }
        allResponses.value.set(itemId, item)
        items.push(item)
      }
    }
    return items
  }

  watch(() => rows.value.map(row => [row.section, row.group, row.opening, row.ending]),
    () => { syncCrossSheetTotals() }, { deep: true, immediate: true })

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; persistToResponses() }, 2000)
  }
  function persistToResponses(): void {
    const serialized = serializeRows()
    const rowItem = { item_id: STORAGE_KEY, conclusion: null, remark: serialized }
    const variantItem = { item_id: VARIANT_KEY, conclusion: null, remark: variant.value }
    allResponses.value.set(STORAGE_KEY, rowItem)
    allResponses.value.set(VARIANT_KEY, variantItem)
    saveImmediate([rowItem, variantItem, ...syncCrossSheetTotals()]).catch(() => {})
  }

  function addRow(section: BankDetailSection, group: BankDetailGroup): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, recalcRow(createEmptyRow(section, group), variant.value)]
    scheduleSave()
  }
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(row => row.id !== rowId)
    scheduleSave()
  }
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const index = rows.value.findIndex(row => row.id === rowId)
    if (index < 0) return
    const row = { ...rows.value[index] }
    const stringFields: Array<keyof BankDetailRow> = [
      'bankName', 'totalLedgerBank', 'accountNo', 'accountType', 'confirmIndexNo',
      'statementIndexNo', 'reconciliationIndexNo', 'restrictedReason', 'note', 'fxCurrency',
    ]
    ;(row as any)[field] = stringFields.includes(field as keyof BankDetailRow) ? String(value) : parseNum(value)
    const next = [...rows.value]
    next[index] = recalcRow(row, variant.value)
    rows.value = next
    scheduleSave()
  }

  function hasConfirmDiff(row: BankDetailRow): boolean {
    return row.confirmAmount !== 0 && Math.abs(row.confirmDiff) > 0.005
  }
  function hydrate(): void {
    isLoading.value = true
    try { loadFromResponses() } finally { isLoading.value = false }
  }

  // ─── P1-5: 函证回写 — confirmation:received 拉取回函详情后按对象名匹配 confirmAmount ──
  //
  // 函证中心(ConfirmationHub)的 confirmation:received 载荷仅含 {projectId, confirmationId,
  // accountCode}，不含回函金额/账号。故此处拉取函证清单取回函金额(confirmed_amount)与函证
  // 对象(counterparty=开户行)，仅对 confirm_type='bank' 的银行函证按开户行名称做规范化匹配
  // 回写到 E1-3 对应行（银行账号在函证记录中不可得，故以开户行名匹配，最贴近可得数据）。
  async function onConfirmationReceived(payload: any): Promise<void> {
    if (!payload?.confirmationId || !payload?.projectId) return
    try {
      const res = await api.get(`/api/projects/${payload.projectId}/confirmations`)
      const items = ((res as any)?.items ?? []) as any[]
      const conf = items.find(c => c.id === payload.confirmationId)
      if (!conf) return
      // 仅银行函证回写货币资金明细
      if (conf.confirm_type && conf.confirm_type !== 'bank') return
      const replyAmount = parseNum(conf.confirmed_amount)
      const counterparty = String(conf.counterparty || '').trim()
      if (!counterparty || replyAmount === 0) return

      const norm = (s: string) => s.replace(/\s+/g, '').toLowerCase()
      const target = norm(counterparty)
      let matched = false
      const next = rows.value.map(row => {
        const rowName = norm(`${row.bankName || ''}${row.totalLedgerBank || ''}`)
        const bankOnly = norm(String(row.bankName || ''))
        if (rowName && (rowName.includes(target) || (bankOnly && target.includes(bankOnly)))) {
          matched = true
          return recalcRow({
            ...row,
            confirmAmount: replyAmount,
            confirmIndexNo: row.confirmIndexNo || `函证#${String(conf.id || '').slice(0, 8)}`,
          }, variant.value)
        }
        return row
      })
      if (matched) {
        rows.value = next
        scheduleSave()
      }
    } catch { /* silent：函证拉取失败不阻断 */ }
  }

  eventBus.on('confirmation:received', onConfirmationReceived)

  onBeforeUnmount(() => {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; persistToResponses() }
    eventBus.off('confirmation:received', onConfirmationReceived)
  })

  return {
    rows, groupedRows, groupTotals, isLoading, addRow, removeRow, updateCell,
    hasConfirmDiff, hydrate, GROUP_NAMES, SECTION_NAMES, SECTIONS, GROUPS,
  }
}
