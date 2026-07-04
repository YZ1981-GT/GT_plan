/**
 * useAlternativeG06Data — G0-6 投资循环替代程序数据 composable
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../../confirmation/alternativeD05/alternativeD05Types'
import type { AlternativeG06Payload } from '../alternativeG06Types'
import { getSumFieldsG06 } from '../blockColumnConfigsG06'
import { calcDisposalGain, calcDividendDiff } from '../../composables/useG0FormulaEngine'

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function precise(n: number): number {
  return Math.round(n * 100) / 100
}

export interface UseAlternativeG06DataProps {
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeG06DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: 'payment' | 'inbound') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  buildPayload: () => AlternativeG06Payload
}

function toNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function applyBlockFormulas(blockType: BlockType, row: CheckRow) {
  if (blockType === 'block2') {
    row.dividend_diff = calcDividendDiff(
      toNum(row.dividend_receivable),
      toNum(row.net_received),
      toNum(row.dividend_tax),
    )
  }
  if (blockType === 'block3') {
    row.disposal_gain = calcDisposalGain(
      toNum(row.trade_amount),
      toNum(row.original_cost),
      toNum(row.fee),
    )
  }
}

export function useAlternativeG06Data(props: UseAlternativeG06DataProps): UseAlternativeG06DataReturn {
  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'alternative-g06-v1') {
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

  initFromHtmlData(props.htmlData())
  watch(() => props.htmlData(), (newData) => { initFromHtmlData(newData) }, { deep: true })

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {},
      balance: { item_name: '交易性金融资产', investment_type: '交易性金融资产' },
      block1_rows: [],
      block2_rows: [],
      block3_rows: [],
      block4_rows: [],
      conclusion: {},
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
        sampling: item.sampling || {},
        balance: { item_name: '交易性金融资产', investment_type: '交易性金融资产', ...(item.balance || {}) },
        block1_rows: [],
        block2_rows: [],
        block3_rows: [],
        block4_rows: [],
        conclusion: {},
      })
    })
    isDirty.value = true
  }

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
    applyBlockFormulas(blockType, row)
    isDirty.value = true
  }

  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = getSumFieldsG06(blockType)
    const totals: Record<string, number> = {}
    for (const field of fields) {
      let sum = 0
      for (const row of rows) {
        const val = Number(row[field])
        if (!isNaN(val)) sum += val
      }
      totals[field] = precise(sum)
    }
    return totals
  }

  function getClosingBalance(company: AlternativeCompany): number {
    return Number(company.balance?.closing_balance ?? company.balance?.sales_amount ?? 0)
  }

  function getCheckRatio(company: AlternativeCompany, type: 'payment' | 'inbound'): number | null {
    const base = getClosingBalance(company)
    if (!base) return null
    if (type === 'inbound') {
      const totals = getBlockTotal(company, 'block1')
      const sum = totals.market_value ?? totals.voucher_amount ?? 0
      return precise((sum / base) * 100)
    }
    const totals = getBlockTotal(company, 'block2')
    const sum = totals.received_amount ?? totals.dividend_receivable ?? 0
    return precise((sum / base) * 100)
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
        receipt_ratio: getCheckRatio(company, 'payment'),
        shipment_ratio: getCheckRatio(company, 'inbound'),
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

  function buildPayload(): AlternativeG06Payload {
    return {
      _format: 'alternative-g06-v1',
      companies: companies.value.map((company) => ({
        ...company,
        balance: {
          ...company.balance,
          inbound_check_ratio: getCheckRatio(company, 'inbound'),
          payment_check_ratio: getCheckRatio(company, 'payment'),
        },
      })),
    }
  }

  return {
    companies,
    isDirty,
    selectedCompanyId,
    addCompany,
    deleteCompany,
    updateCompany,
    importCompanies,
    addBlockRow,
    deleteBlockRow,
    updateBlockField,
    getBlockTotal,
    getCheckRatio,
    getCompletionStatus,
    hasAbnormal,
    metrics,
    buildPayload,
  }
}
