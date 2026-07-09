/**
 * useAlternativeK05Data — K0-5 其他应收款替代程序数据 composable
 *
 * Master-Detail（公司→4 区块检查表）
 * - loadAll / persistAll（_format: alternative-k05-v1）
 * - importFromSummary（K0-1 未回函，对标 D0-1→D0-5）
 * - 四区块 CRUD + 合计 + 检查比例 + 对账差异
 *
 * 4区块：
 *   ① 期后收款检查
 *   ② 期末余额支持性证据
 *   ③ 本期发生额检查（借方+贷方合并）
 *   ④ 往来对账/协议证据
 *
 * Requirements: 2.1~2.10, 4.1
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import {
  calcBlockTotal,
  calcCheckRatio,
  calcReconcileDiff,
  parseNum,
} from './useK0FormulaEngine'
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface AlternativeK05Payload {
  _format: 'alternative-k05-v1'
  companies: AlternativeCompany[]
}

export interface K01UnrepliedEntity {
  /** 被询证单位名称 */
  entity_name: string
  /** 函证索引号 */
  confirm_index?: string
  /** 函证金额 */
  confirm_amount?: number
  /** 未回函原因 */
  unreplied_reason?: string
}

export interface AlternativeK05Summary {
  /** 函证项目（其他应收款） */
  investmentType: string
  /** 年初余额 */
  openingBalance: number
  /** 借方发生额 */
  debitAmount: number
  /** 贷方发生额 */
  creditAmount: number
  /** 期末余额 = 年初 + 借方 - 贷方 */
  closingBalance: number
  /** 本期发生额 */
  currentAmount: number
  /** 期后收款检查比例 */
  postCheckRatio: number
  /** 往来对账比例 */
  reconcileRatio: number
}

export interface UseAlternativeK05DataProps {
  wpId: string
  projectId: string
  htmlData: () => any
  readonly: boolean
}

export interface UseAlternativeK05DataReturn {
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
  getCheckRatio: (company: AlternativeCompany, type: 'post_receipt' | 'reconcile') => number | null
  getReconcileDiff: (row: CheckRow) => number
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean
  metrics: ComputedRef<AlternativeD05Metrics>
  balanceSummary: ComputedRef<AlternativeK05Summary>
  loadAll: () => void
  persistAll: () => AlternativeK05Payload
  buildPayload: () => AlternativeK05Payload
}

// ─── 4 区块列配置（Sum字段定义）───────────────────────────────────────────────

/** 各区块需要合计的数值字段 */
const SUM_FIELDS: Record<string, string[]> = {
  block1: ['voucher_amount', 'receipt_amount'],
  block2: ['voucher_amount', 'agreement_amount'],
  block3: ['voucher_amount', 'approval_amount'],
  block4: ['voucher_amount', 'other_balance', 'self_balance'],
}

export function getSumFieldsK05(blockType: string): string[] {
  return SUM_FIELDS[blockType] || []
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

function precise(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Composable ─────────────────────────────────────────────────────────────

export default function useAlternativeK05Data(wpId: string, projectId: string): UseAlternativeK05DataReturn
export default function useAlternativeK05Data(props: UseAlternativeK05DataProps): UseAlternativeK05DataReturn
export default function useAlternativeK05Data(
  wpIdOrProps: string | UseAlternativeK05DataProps,
  projectId?: string,
): UseAlternativeK05DataReturn {
  // Normalize props
  const props: UseAlternativeK05DataProps =
    typeof wpIdOrProps === 'string'
      ? { wpId: wpIdOrProps, projectId: projectId!, htmlData: () => null, readonly: false }
      : wpIdOrProps

  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)
  const loading = ref(false)

  // ─── Load / Persist ─────────────────────────────────────────────────────

  function loadAll() {
    initFromHtmlData(props.htmlData())
  }

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'alternative-k05-v1') {
      companies.value = []
      return
    }
    companies.value = Array.isArray(data.companies) ? data.companies.map(ensureCompanyId) : []
    isDirty.value = false
  }

  function persistAll(): AlternativeK05Payload {
    return buildPayload()
  }

  function buildPayload(): AlternativeK05Payload {
    return {
      _format: 'alternative-k05-v1',
      companies: companies.value.map((company) => ({
        ...company,
        balance: {
          ...company.balance,
          receipt_check_ratio: getCheckRatio(company, 'post_receipt'),
          reconcile_check_ratio: getCheckRatio(company, 'reconcile'),
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

  // ─── Init ───────────────────────────────────────────────────────────────

  loadAll()
  watch(() => props.htmlData(), () => { loadAll() }, { deep: true })

  // ─── Company CRUD ───────────────────────────────────────────────────────

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {},
      balance: { item_name: '其他应收款' },
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
        balance: { item_name: '其他应收款', ...(item.balance || {}) },
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
   * 从 K0-1 函证汇总表带入未回函公司（反向联动）
   * 调用后端 API 获取 K0-1 未回函列表，按 confirm_index 去重后插入
   * @returns 新增公司数量
   */
  async function importFromSummary(): Promise<number> {
    loading.value = true
    try {
      const res = await http.get<K01UnrepliedEntity[]>(
        `/api/workpapers/${props.wpId}/k0/unreplied-entities`,
        { params: { sheet: 'K0-5' } },
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
            item_name: '其他应收款',
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

  // ─── Computed: totals & ratios ──────────────────────────────────────────

  /**
   * 计算指定区块的合计行（按 SUM_FIELDS 配置的数值字段求和）
   */
  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = getSumFieldsK05(blockType)
    const totals: Record<string, number> = {}
    for (const field of fields) {
      const amounts = rows.map((r) => parseNum(r[field]))
      totals[field] = precise(calcBlockTotal(amounts))
    }
    return totals
  }

  function getClosingBalance(company: AlternativeCompany): number {
    return parseNum(company.balance?.closing_balance ?? 0)
  }

  /**
   * 检查比例计算（调用 useK0FormulaEngine.calcCheckRatio）
   * - post_receipt: 区块①期后收款合计(receipt_amount) / 期末余额
   * - reconcile: 区块④对账覆盖合计(self_balance) / 期末余额
   */
  function getCheckRatio(company: AlternativeCompany, type: 'post_receipt' | 'reconcile'): number | null {
    const closing = getClosingBalance(company)
    if (!closing) return null
    if (type === 'post_receipt') {
      const totals = getBlockTotal(company, 'block1')
      const sum = totals.receipt_amount ?? 0
      return precise(calcCheckRatio(sum, closing) * 100)
    }
    // reconcile: block4 self_balance 总和
    const totals = getBlockTotal(company, 'block4')
    const sum = totals.self_balance ?? 0
    return precise(calcCheckRatio(sum, closing) * 100)
  }

  /**
   * 计算对账差异（区块④每行：本方余额 - 对方余额）
   */
  function getReconcileDiff(row: CheckRow): number {
    return calcReconcileDiff(parseNum(row.self_balance), parseNum(row.other_balance))
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

  // ─── Balance Summary (余额汇总区 computed) ──────────────────────────────

  const balanceSummary = computed<AlternativeK05Summary>(() => {
    // 汇总所有公司余额
    let openingBalance = 0
    let debitAmount = 0
    let creditAmount = 0
    let postReceiptTotal = 0
    let reconcileTotal = 0

    for (const company of companies.value) {
      openingBalance += parseNum(company.balance?.opening_balance)
      debitAmount += parseNum(company.balance?.debit_amount)
      creditAmount += parseNum(company.balance?.credit_amount)
      // 期后收款合计（block1 receipt_amount）
      const b1Totals = getBlockTotal(company, 'block1')
      postReceiptTotal += b1Totals.receipt_amount ?? 0
      // 往来对账合计（block4 self_balance）
      const b4Totals = getBlockTotal(company, 'block4')
      reconcileTotal += b4Totals.self_balance ?? 0
    }

    const closingBalance = precise(openingBalance + debitAmount - creditAmount)
    const currentAmount = precise(debitAmount + creditAmount)
    const postCheckRatio = closingBalance > 0 ? precise(calcCheckRatio(postReceiptTotal, closingBalance) * 100) : 0
    const reconcileRatio = closingBalance > 0 ? precise(calcCheckRatio(reconcileTotal, closingBalance) * 100) : 0

    return {
      investmentType: '其他应收款',
      openingBalance: precise(openingBalance),
      debitAmount: precise(debitAmount),
      creditAmount: precise(creditAmount),
      closingBalance,
      currentAmount,
      postCheckRatio,
      reconcileRatio,
    }
  })

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
        receipt_ratio: getCheckRatio(company, 'post_receipt'),
        shipment_ratio: getCheckRatio(company, 'reconcile'),
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
    getReconcileDiff,
    getCompletionStatus,
    hasAbnormal,
    metrics,
    balanceSummary,
    loadAll,
    persistAll,
    buildPayload,
  }
}
