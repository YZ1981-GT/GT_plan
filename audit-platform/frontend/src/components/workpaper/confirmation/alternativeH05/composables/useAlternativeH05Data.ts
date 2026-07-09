/**
 * useAlternativeH05Data — H0-5 固定资产循环替代程序数据 composable
 *
 * Master-Detail（公司→4 区块检查表）
 * - loadAll / persistAll（_format: alternative-h05-v1）
 * - importFromSummary（H0-1 未回函，对标 D0-1→D0-5）
 * - 四区块 CRUD + 合计 + 检查比例
 *
 * Requirements: 2, 3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import type { AlternativeH05Payload, H01UnrepliedEntity } from '../alternativeH05Types'
import { getSumFieldsH05 } from '../blockColumnConfigsH05'
import { calcCheckRatio as calcRatio, calcBlockTotal as calcTotal, parseNum } from './useH0FormulaEngine'
import http from '@/utils/http'

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function precise(n: number): number {
  return Math.round(n * 100) / 100
}

export interface UseAlternativeH05DataProps {
  wpId: string
  projectId: string
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeH05DataReturn {
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
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: 'ownership' | 'acceptance') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  loadAll: () => void
  persistAll: () => AlternativeH05Payload
  buildPayload: () => AlternativeH05Payload
}

export function useAlternativeH05Data(props: UseAlternativeH05DataProps): UseAlternativeH05DataReturn {
  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)
  const loading = ref(false)

  // ─── Load / Persist ───────────────────────────────────────────────────────

  function loadAll() {
    initFromHtmlData(props.htmlData())
  }

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'alternative-h05-v1') {
      companies.value = []
      return
    }
    companies.value = Array.isArray(data.companies) ? data.companies.map(ensureCompanyId) : []
    isDirty.value = false
  }

  function persistAll(): AlternativeH05Payload {
    return buildPayload()
  }

  function buildPayload(): AlternativeH05Payload {
    return {
      _format: 'alternative-h05-v1',
      companies: companies.value.map((company) => ({
        ...company,
        balance: {
          ...company.balance,
          ownership_check_ratio: getCheckRatio(company, 'ownership'),
          post_acceptance_ratio: getCheckRatio(company, 'acceptance'),
        },
      })),
    }
  }

  // ─── ID helpers ───────────────────────────────────────────────────────────

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

  // ─── Init ─────────────────────────────────────────────────────────────────

  loadAll()
  watch(() => props.htmlData(), () => { loadAll() }, { deep: true })

  // ─── Company CRUD ─────────────────────────────────────────────────────────

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {},
      balance: { item_name: '固定资产' },
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

  /**
   * 批量导入公司（通用，按 confirm_index 去重）
   */
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
        balance: { item_name: '固定资产', ...(item.balance || {}) },
        block1_rows: [],
        block2_rows: [],
        block3_rows: [],
        block4_rows: [],
        conclusion: {},
      })
    })
    isDirty.value = true
  }

  /**
   * 从 H0-1 函证汇总表带入未回函公司（对标 D0-1→D0-5 模式）
   * 调用后端 API 获取 H0-1 未回函列表，按 confirm_index 去重后插入
   * @returns 新增公司数量
   */
  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get<H01UnrepliedEntity[]>(
        `/api/workpapers/${props.wpId}/h0/unreplied-entities`,
        { params: { sheet: 'H0-5' } },
      )
      const entities: H01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
      if (!entities.length) return 0

      const existingIndexes = new Set(
        companies.value.map((c) => c.confirm_index).filter(Boolean),
      )
      const newItems = entities.filter(
        (e) => !e.confirm_index || !existingIndexes.has(e.confirm_index),
      )
      if (!newItems.length) return 0

      const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
      newItems.forEach((item, i) => {
        companies.value.push({
          _company_id: generateId(),
          seq: maxSeq + i + 1,
          entity_name: item.entity_name || '',
          confirm_index: item.confirm_index,
          _source: 'auto',
          sampling: {},
          balance: {
            item_name: '固定资产',
            closing_balance: item.confirm_amount ?? 0,
          },
          block1_rows: [],
          block2_rows: [],
          block3_rows: [],
          block4_rows: [],
          conclusion: {},
        })
      })
      isDirty.value = true
      return newItems.length
    } finally {
      loading.value = false
    }
  }

  // ─── Block Row CRUD ───────────────────────────────────────────────────────

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

  // ─── Computed: totals & ratios ────────────────────────────────────────────

  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = getSumFieldsH05(blockType)
    const totals: Record<string, number> = {}
    for (const field of fields) {
      const amounts = rows.map((r) => parseNum(r[field]))
      totals[field] = precise(calcTotal(amounts))
    }
    return totals
  }

  function getClosingBalance(company: AlternativeCompany): number {
    return parseNum(company.balance?.closing_balance ?? company.balance?.ending_balance ?? 0)
  }

  /**
   * 检查比例计算
   * - ownership: 区块②余额支持性证据合计 / 期末余额
   * - acceptance: 区块①期后验收合计 / 期末余额
   */
  function getCheckRatio(company: AlternativeCompany, type: 'ownership' | 'acceptance'): number | null {
    const closing = getClosingBalance(company)
    if (!closing) return null
    if (type === 'ownership') {
      const totals = getBlockTotal(company, 'block2')
      const sum = totals.contract_amount ?? totals.invoice_amount ?? totals.payment_amount ?? 0
      return precise(calcRatio(sum, closing) * 100)
    }
    // acceptance: block1 voucher_amount
    const totals = getBlockTotal(company, 'block1')
    const sum = totals.voucher_amount ?? 0
    return precise(calcRatio(sum, closing) * 100)
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

  // ─── Metrics ──────────────────────────────────────────────────────────────

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
        receipt_ratio: getCheckRatio(company, 'acceptance'),
        shipment_ratio: getCheckRatio(company, 'ownership'),
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
    getBlockTotal,
    getCheckRatio,
    getCompletionStatus,
    hasAbnormal,
    metrics,
    loadAll,
    persistAll,
    buildPayload,
  }
}
