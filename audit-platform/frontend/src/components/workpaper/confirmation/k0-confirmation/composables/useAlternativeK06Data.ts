/**
 * useAlternativeK06Data — K0-6 其他应付款替代程序数据 composable
 *
 * Master-Detail（债权人公司→4 区块检查表）
 * - loadAll / persistAll（item_id 前缀 K0-6-alt-{entity}-block{N}-rows）
 * - importFromSummary（K0-1 未回函，对标 D0-1→D0-6）
 * - 四区块 CRUD + 合计 + 检查比例
 *
 * 4区块：
 * ① 期后付款检查
 * ② 期末余额支持性证据
 * ③ 本期发生额检查
 * ④ 往来对账/协议证据
 *
 * Requirements: 3.1~3.10, 4.2
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import {
  calcCheckRatio as calcRatio,
  calcBlockTotal as calcTotal,
  parseNum,
} from './useK0FormulaEngine'
import http from '@/utils/http'

// ─── Constants ──────────────────────────────────────────────────────────────

const FORMAT_VERSION = 'alternative-k06-v1' as const
const ITEM_NAME = '其他应付款'

// ─── K0-6 Block 1 列配置（期后付款检查） ────────────────────────────────────

/** K0-6 区块①期后付款检查 需求和的字段 */
const BLOCK1_SUM_FIELDS = ['amount', 'paymentAmount']

/** K0-6 区块②期末余额支持性证据 需求和的字段 */
const BLOCK2_SUM_FIELDS = ['amount']

/** K0-6 区块③本期发生额 需求和的字段 */
const BLOCK3_SUM_FIELDS = ['amount']

/** K0-6 区块④往来对账/协议证据 需求和的字段 */
const BLOCK4_SUM_FIELDS = ['amount']

const SUM_FIELDS_MAP: Record<string, string[]> = {
  block1: BLOCK1_SUM_FIELDS,
  block2: BLOCK2_SUM_FIELDS,
  block3: BLOCK3_SUM_FIELDS,
  block4: BLOCK4_SUM_FIELDS,
}

export const BLOCK_TITLES_K06: Record<BlockType, string> = {
  block1: '①期后付款检查',
  block2: '②期末余额支持性证据',
  block3: '③本期发生额检查',
  block4: '④往来对账/协议证据',
}


// ─── Types ──────────────────────────────────────────────────────────────────

export interface AlternativeK06Payload {
  _format: typeof FORMAT_VERSION
  companies: AlternativeCompany[]
}

export interface K01UnrepliedEntity {
  entity_name: string
  confirm_index?: string
  confirm_amount?: number
  unreplied_reason?: string
}

export interface AlternativeK06Summary {
  /** 函证项目（其他应付款） */
  investmentType: string
  /** 年初余额 */
  openingBalance: number
  /** 借方发生额 */
  debitAmount: number
  /** 贷方发生额 */
  creditAmount: number
  /** 期末余额 */
  closingBalance: number
  /** 期后付款检查比例 */
  postCheckRatio: number
  /** 往来对账比例 */
  reconcileRatio: number
}


// ─── Helpers ────────────────────────────────────────────────────────────────

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function precise(n: number): number {
  return Math.round(n * 100) / 100
}

export function getSumFieldsK06(blockType: string): string[] {
  return SUM_FIELDS_MAP[blockType] ?? []
}

// ─── Composable ─────────────────────────────────────────────────────────────

export interface UseAlternativeK06DataReturn {
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
  getPostPaymentRatio: (company: AlternativeCompany) => number | null
  getReconcileRatio: (company: AlternativeCompany) => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  loadAll: () => void
  persistAll: () => AlternativeK06Payload
  buildPayload: () => AlternativeK06Payload
}


export default function useAlternativeK06Data(wpId: string, projectId: string): UseAlternativeK06DataReturn {
  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)
  const loading = ref(false)

  // ─── Load / Persist ─────────────────────────────────────────────────────

  function loadAll() {
    loading.value = true
    http
      .get(`/api/workpapers/${wpId}/render-config`)
      .then((res) => {
        const data = res.data?.data ?? res.data
        const sheets = data?.sheets ?? []
        const sheet = sheets.find((s: any) => s.sheet_name?.includes('K0-6'))
        const htmlData = sheet?.html_data
        if (htmlData && htmlData._format === FORMAT_VERSION) {
          companies.value = Array.isArray(htmlData.companies)
            ? htmlData.companies.map(ensureCompanyId)
            : []
        } else {
          companies.value = []
        }
        isDirty.value = false
      })
      .catch(() => {
        companies.value = []
      })
      .finally(() => {
        loading.value = false
      })
  }

  function persistAll(): AlternativeK06Payload {
    const payload = buildPayload()
    // Persist each company's block rows with item_id prefix pattern
    for (const company of companies.value) {
      const entityKey = company._company_id || company.entity_name || 'unknown'
      const blocks: BlockType[] = ['block1', 'block2', 'block3', 'block4']
      for (let i = 0; i < blocks.length; i++) {
        const itemId = `K0-6-alt-${entityKey}-block${i + 1}-rows`
        const rows = getBlockRows(company, blocks[i])
        http.post(`/api/workpapers/${wpId}/checklist-responses`, {
          item_id: itemId,
          remark: JSON.stringify(rows),
        }).catch(() => { /* silent */ })
      }
    }
    isDirty.value = false
    return payload
  }


  function buildPayload(): AlternativeK06Payload {
    return {
      _format: FORMAT_VERSION,
      companies: companies.value.map((company) => ({
        ...company,
        balance: {
          ...company.balance,
          receipt_check_ratio: getPostPaymentRatio(company),
          shipment_check_ratio: getReconcileRatio(company),
        },
      })),
    }
  }

  // ─── ID helpers ─────────────────────────────────────────────────────────

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

  // ─── Company CRUD ───────────────────────────────────────────────────────

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {},
      balance: { item_name: ITEM_NAME },
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
    const existingIndexes = new Set(
      companies.value.map((c) => c.confirm_index).filter(Boolean),
    )
    const deduped = items.filter(
      (item) => !item.confirm_index || !existingIndexes.has(item.confirm_index),
    )
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    deduped.forEach((item, i) => {
      companies.value.push({
        _company_id: generateId(),
        seq: maxSeq + i + 1,
        entity_name: item.entity_name || '',
        confirm_index: item.confirm_index,
        _source: item._source || 'auto',
        sampling: item.sampling || {},
        balance: { item_name: ITEM_NAME, ...(item.balance || {}) },
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
   * 从 K0-1 函证汇总表带入未回函公司（对标 D0-1→D0-6 模式）
   * 调用后端 API 获取 K0-1 未回函列表，按 confirm_index 去重后插入
   * @returns 新增公司数量
   */
  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get<K01UnrepliedEntity[]>(
        `/api/workpapers/${wpId}/k0/unreplied-entities`,
        { params: { sheet: 'K0-6' } },
      )
      const entities: K01UnrepliedEntity[] = res.data?.data ?? res.data ?? []
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
            item_name: ITEM_NAME,
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


  // ─── Block Row CRUD ─────────────────────────────────────────────────────

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
    const newRow: CheckRow = {
      _row_id: generateId(),
      seq: maxSeq + 1,
      _source: 'manual',
      is_abnormal: '否',
    }
    rows.push(newRow)
    setBlockRows(company, blockType, rows)
    isDirty.value = true
    return newRow
  }

  function deleteBlockRow(companyId: string, blockType: BlockType, rowId: string) {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    setBlockRows(
      company,
      blockType,
      getBlockRows(company, blockType).filter((r) => r._row_id !== rowId),
    )
    isDirty.value = true
  }

  function updateBlockField(
    companyId: string,
    blockType: BlockType,
    rowId: string,
    field: string,
    value: any,
  ) {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    const row = getBlockRows(company, blockType).find((r) => r._row_id === rowId)
    if (!row) return
    row[field] = value
    isDirty.value = true
  }


  // ─── Computed: totals & ratios ──────────────────────────────────────────

  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = getSumFieldsK06(blockType)
    const totals: Record<string, number> = {}
    for (const field of fields) {
      const amounts = rows.map((r) => parseNum(r[field]))
      totals[field] = precise(calcTotal(amounts))
    }
    return totals
  }

  function getClosingBalance(company: AlternativeCompany): number {
    return parseNum(
      company.balance?.closing_balance ?? company.balance?.credit_amount ?? 0,
    )
  }

  /**
   * 期后付款检查比例 = 区块①付款金额合计 / 期末余额
   */
  function getPostPaymentRatio(company: AlternativeCompany): number | null {
    const closing = getClosingBalance(company)
    if (!closing) return null
    const totals = getBlockTotal(company, 'block1')
    const sum = totals.paymentAmount ?? 0
    return precise(calcRatio(sum, closing) * 100)
  }

  /**
   * 往来对账比例 = 区块④对账覆盖金额合计 / 期末余额
   */
  function getReconcileRatio(company: AlternativeCompany): number | null {
    const closing = getClosingBalance(company)
    if (!closing) return null
    const totals = getBlockTotal(company, 'block4')
    const sum = totals.amount ?? 0
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


  // ─── Metrics ────────────────────────────────────────────────────────────

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
        receipt_ratio: getPostPaymentRatio(company),
        shipment_ratio: getReconcileRatio(company),
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

  // ─── Init ───────────────────────────────────────────────────────────────

  loadAll()

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
    getPostPaymentRatio,
    getReconcileRatio,
    getCompletionStatus,
    hasAbnormal,
    metrics,
    loadAll,
    persistAll,
    buildPayload,
  }
}
