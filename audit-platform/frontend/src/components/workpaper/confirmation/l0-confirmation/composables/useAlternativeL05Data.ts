/**
 * useAlternativeL05Data — L0-5 债务循环替代程序 composable
 *
 * Master-Detail 结构：公司列表 → 选中公司 → 4 区块检查表
 * 4 区块：①期后付款/还款检查 ②期末余额支持性证据(借款合同/银行对账单)
 *         ③本期借款检查 ④抵质押/担保证据
 *
 * 数据流：loadAll(htmlData) → companies → buildPayload → persistAll
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  BlockType,
  CheckRow,
  SamplingConfig,
  BalanceSummary,
  AuditConclusion,
  AlternativeD05Metrics,
} from '../../alternativeD05/alternativeD05Types'
import { calcBlockTotal, calcRepaymentRatio } from './useL0FormulaEngine'
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

export const FORMAT_VERSION = 'alternative-l05-v1' as const

export interface AlternativeL05Payload {
  _format: typeof FORMAT_VERSION
  companies: AlternativeCompany[]
}

export interface AlternativeL05Summary {
  investmentType: string
  openingBalance: number
  debitAmount: number
  creditAmount: number
  closingBalance: number
  currentLoan: number
  repaymentCheckRatio: number
  mortgageCheckRatio: number
}

export interface L01UnrepliedEntity {
  entity_name: string
  confirm_index?: string
  confirm_amount?: number
  unreplied_reason?: string
}

export interface UseAlternativeL05DataProps {
  wpId: string
  projectId: string
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeL05DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>
  loading: Ref<boolean>
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void
  importFromSummary: () => Promise<number>
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void
  getBlockRows: (company: AlternativeCompany, blockType: BlockType) => CheckRow[]
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getClosingBalance: (company: AlternativeCompany) => number
  getRepaymentRatio: (company: AlternativeCompany) => number
  getMortgageRatio: (company: AlternativeCompany) => number
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  balanceSummary: ComputedRef<AlternativeL05Summary>
  loadAll: () => void
  persistAll: () => AlternativeL05Payload
  buildPayload: () => AlternativeL05Payload
}

// ─── 4 区块金额 Sum 字段 ───────────────────────────────────────────────────

const SUM_FIELDS: Record<BlockType, string[]> = {
  block1: ['voucher_amount', 'repayment_principal', 'repayment_interest'],
  block2: ['voucher_amount', 'contract_amount', 'book_balance'],
  block3: ['voucher_amount', 'arrival_amount'],
  block4: ['voucher_amount', 'mortgage_amount', 'guarantee_amount'],
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function precise(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useAlternativeL05Data(props: UseAlternativeL05DataProps): UseAlternativeL05DataReturn {
  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)
  const loading = ref(false)

  // ─── Init / Load ─────────────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || data._format !== FORMAT_VERSION) {
      companies.value = []
      return
    }
    companies.value = Array.isArray(data.companies) ? data.companies.map(ensureCompanyId) : []
    isDirty.value = false
  }

  function ensureCompanyId(company: AlternativeCompany): AlternativeCompany {
    return {
      ...company,
      _company_id: company._company_id || generateId(),
      block1_rows: (company.block1_rows || []).map(ensureRowId),
      block2_rows: (company.block2_rows || []).map(ensureRowId),
      block3_rows: (company.block3_rows || []).map(ensureRowId),
      block4_rows: (company.block4_rows || []).map(ensureRowId),
    }
  }

  function ensureRowId(row: CheckRow): CheckRow {
    if (!row._row_id) return { ...row, _row_id: generateId() }
    return row
  }

  function loadAll() {
    initFromHtmlData(props.htmlData())
  }

  loadAll()
  watch(() => props.htmlData(), (newData) => { initFromHtmlData(newData) }, { deep: true })

  // ─── Company CRUD ────────────────────────────────────────────────────────

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {} as SamplingConfig,
      balance: { item_name: '长期应付款/借款' } as BalanceSummary,
      block1_rows: [],
      block2_rows: [],
      block3_rows: [],
      block4_rows: [],
      conclusion: {} as AuditConclusion,
      ...partial,
    }
    companies.value.push(newCompany)
    isDirty.value = true
    return newCompany
  }

  function deleteCompany(companyId: string) {
    companies.value = companies.value.filter((c) => c._company_id !== companyId)
    if (selectedCompanyId.value === companyId) {
      selectedCompanyId.value = companies.value[0]?._company_id ?? null
    }
    isDirty.value = true
  }

  function updateCompany(companyId: string, field: string, value: any) {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    ;(company as any)[field] = value
    isDirty.value = true
  }

  function importCompanies(items: Partial<AlternativeCompany>[]) {
    const existingIndexes = new Set(companies.value.map((c) => c.confirm_index).filter(Boolean))
    const deduped = items.filter((item) => !item.confirm_index || !existingIndexes.has(item.confirm_index))
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    deduped.forEach((item, i) => {
      companies.value.push({
        _company_id: generateId(),
        seq: maxSeq + i + 1,
        entity_name: item.entity_name || '',
        confirm_index: item.confirm_index,
        _source: item._source || 'auto',
        sampling: item.sampling || ({} as SamplingConfig),
        balance: { item_name: '长期应付款/借款', ...(item.balance || {}) } as BalanceSummary,
        block1_rows: [],
        block2_rows: [],
        block3_rows: [],
        block4_rows: [],
        conclusion: {} as AuditConclusion,
      })
    })
    isDirty.value = true
  }

  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get(`/api/workpapers/${props.wpId}/l0/unreplied-entities`, {
        params: { sheet: 'L0-5' },
      })
      const entities: L01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
      if (!entities.length) return 0
      importCompanies(
        entities.map((e) => ({
          entity_name: e.entity_name,
          confirm_index: e.confirm_index,
          _source: 'auto',
          balance: { item_name: '长期应付款/借款', closing_balance: e.confirm_amount } as BalanceSummary,
        })),
      )
      return entities.length
    } catch {
      return 0
    } finally {
      loading.value = false
    }
  }

  // ─── Block CRUD ──────────────────────────────────────────────────────────

  function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
    const key = `${blockType}_rows` as keyof AlternativeCompany
    return (company[key] as CheckRow[]) || []
  }

  function setBlockRows(company: AlternativeCompany, blockType: BlockType, rows: CheckRow[]) {
    const key = `${blockType}_rows` as keyof AlternativeCompany
    ;(company as any)[key] = rows
  }

  function addBlockRow(companyId: string, blockType: BlockType): CheckRow | undefined {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return undefined
    const rows = getBlockRows(company, blockType)
    const maxSeq = rows.reduce((max, r) => Math.max(max, r.seq ?? 0), 0)
    const newRow: CheckRow = { _row_id: generateId(), seq: maxSeq + 1, _source: 'manual', is_abnormal: '否' }
    rows.push(newRow)
    setBlockRows(company, blockType, rows)
    isDirty.value = true
    return newRow
  }

  function deleteBlockRow(companyId: string, blockType: BlockType, rowId: string) {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    setBlockRows(company, blockType, getBlockRows(company, blockType).filter((r) => r._row_id !== rowId))
    isDirty.value = true
  }

  function updateBlockField(companyId: string, blockType: BlockType, rowId: string, field: string, value: any) {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    const row = getBlockRows(company, blockType).find((r) => r._row_id === rowId)
    if (!row) return
    row[field] = value
    isDirty.value = true
  }

  // ─── Computed / Calculations ─────────────────────────────────────────────

  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = SUM_FIELDS[blockType] || ['voucher_amount']
    const totals: Record<string, number> = {}
    for (const field of fields) {
      const amounts = rows.map((r) => Number(r[field])).filter((n) => !isNaN(n))
      totals[field] = precise(calcBlockTotal(amounts))
    }
    return totals
  }

  function getClosingBalance(company: AlternativeCompany): number {
    return Number(company.balance?.closing_balance ?? 0)
  }

  function getRepaymentRatio(company: AlternativeCompany): number {
    const block1Total = getBlockTotal(company, 'block1')
    const repaid = block1Total.repayment_principal ?? block1Total.voucher_amount ?? 0
    const balance = getClosingBalance(company)
    return precise(calcRepaymentRatio(repaid, balance) * 100)
  }

  function getMortgageRatio(company: AlternativeCompany): number {
    const block4Total = getBlockTotal(company, 'block4')
    const mortgageAmt = block4Total.mortgage_amount ?? block4Total.voucher_amount ?? 0
    const balance = getClosingBalance(company)
    return balance > 0 ? precise((mortgageAmt / balance) * 100) : 0
  }

  function getCompletionStatus(company: AlternativeCompany) {
    const blocks: BlockType[] = ['block1', 'block2', 'block3', 'block4']
    let completed = 0
    for (const bt of blocks) {
      if (getBlockRows(company, bt).length > 0) completed++
    }
    return { completed, total: 4, rate: Math.round((completed / 4) * 100) }
  }

  function hasAbnormal(company: AlternativeCompany): boolean {
    for (const bt of ['block1', 'block2', 'block3', 'block4'] as BlockType[]) {
      if (getBlockRows(company, bt).some((r) => r.is_abnormal === '是')) return true
    }
    return false
  }

  const metrics = computed<AlternativeD05Metrics>(() => {
    let completedCount = 0
    let abnormalCount = 0
    const ratioDistribution: AlternativeD05Metrics['ratio_distribution'] = []
    for (const company of companies.value) {
      const status = getCompletionStatus(company)
      if (status.completed === 4) completedCount++
      if (hasAbnormal(company)) abnormalCount++
      ratioDistribution.push({
        entity_name: company.entity_name || '未命名',
        receipt_ratio: getRepaymentRatio(company),
        shipment_ratio: getMortgageRatio(company),
      })
    }
    const total = companies.value.length
    return {
      total_companies: total,
      completed_companies: completedCount,
      abnormal_companies: abnormalCount,
      ratio_distribution: ratioDistribution,
      completion_rate: total > 0 ? Math.round((completedCount / total) * 100) : 0,
    }
  })

  const balanceSummary = computed<AlternativeL05Summary>(() => {
    let opening = 0, debit = 0, credit = 0, closing = 0, currentLoan = 0
    for (const c of companies.value) {
      opening += Number(c.balance?.opening_balance ?? 0)
      debit += Number(c.balance?.debit_amount ?? 0)
      credit += Number(c.balance?.credit_amount ?? 0)
      closing += getClosingBalance(c)
      const block3Total = getBlockTotal(c, 'block3')
      currentLoan += block3Total.voucher_amount ?? 0
    }
    const avgRepayment = companies.value.length > 0
      ? companies.value.reduce((s, c) => s + getRepaymentRatio(c), 0) / companies.value.length
      : 0
    const avgMortgage = companies.value.length > 0
      ? companies.value.reduce((s, c) => s + getMortgageRatio(c), 0) / companies.value.length
      : 0
    return {
      investmentType: '长期应付款/借款',
      openingBalance: precise(opening),
      debitAmount: precise(debit),
      creditAmount: precise(credit),
      closingBalance: precise(closing),
      currentLoan: precise(currentLoan),
      repaymentCheckRatio: precise(avgRepayment),
      mortgageCheckRatio: precise(avgMortgage),
    }
  })

  // ─── Persist ─────────────────────────────────────────────────────────────

  function buildPayload(): AlternativeL05Payload {
    return {
      _format: FORMAT_VERSION,
      companies: companies.value.map((company) => ({
        ...company,
        balance: {
          ...company.balance,
          receipt_check_ratio: getRepaymentRatio(company),
          shipment_check_ratio: getMortgageRatio(company),
        },
      })),
    }
  }

  function persistAll(): AlternativeL05Payload {
    isDirty.value = false
    return buildPayload()
  }

  return {
    companies,
    isDirty,
    selectedCompanyId,
    loading,
    addCompany,
    deleteCompany,
    updateCompany,
    importCompanies,
    importFromSummary,
    addBlockRow,
    deleteBlockRow,
    updateBlockField,
    getBlockRows,
    getBlockTotal,
    getClosingBalance,
    getRepaymentRatio,
    getMortgageRatio,
    getCompletionStatus,
    hasAbnormal,
    metrics,
    balanceSummary,
    loadAll,
    persistAll,
    buildPayload,
  }
}

export default useAlternativeL05Data
