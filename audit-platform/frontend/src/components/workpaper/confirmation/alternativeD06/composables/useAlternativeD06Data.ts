/**
 * useAlternativeD06Data — D0-6 应收及销售替代程序数据核心 composable
 *
 * 薄封装：复用 D0-5 的 useAlternativeData 全部逻辑，
 * 仅覆盖 _format = 'alternative-d06-v1' 和 D06 专属列配置。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../../alternativeD05/alternativeD05Types'
import type { AlternativeD06Payload } from '../alternativeD06Types'
import { getSumFieldsD06 } from '../blockColumnConfigsD06'

// ─── ID 生成工具 ─────────────────────────────────────────────────────────────

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

/** 精确小数（避免浮点漂移） */
function precise(n: number): number {
  return Math.round(n * 100) / 100
}

// ─── Props 接口 ──────────────────────────────────────────────────────────────

export interface UseAlternativeD06DataProps {
  htmlData: () => any
  readonly: boolean
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface UseAlternativeD06DataReturn {
  companies: Ref<AlternativeCompany[]>
  isDirty: Ref<boolean>
  selectedCompanyId: Ref<string | null>

  // CRUD
  addCompany: (partial?: Partial<AlternativeCompany>) => AlternativeCompany
  deleteCompany: (companyId: string) => void
  updateCompany: (companyId: string, field: string, value: any) => void
  importCompanies: (items: Partial<AlternativeCompany>[]) => void

  // 区块行操作
  addBlockRow: (companyId: string, blockType: BlockType) => CheckRow | undefined
  deleteBlockRow: (companyId: string, blockType: BlockType, rowId: string) => void
  updateBlockField: (companyId: string, blockType: BlockType, rowId: string, field: string, value: any) => void

  // 计算
  getBlockTotal: (company: AlternativeCompany, blockType: BlockType) => Record<string, number>
  getCheckRatio: (company: AlternativeCompany, type: 'receipt' | 'shipment') => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean

  // 看板
  metrics: ComputedRef<AlternativeD05Metrics>

  // 持久化
  buildPayload: () => AlternativeD06Payload
}

// ─── Composable 主体 ─────────────────────────────────────────────────────────

export function useAlternativeD06Data(props: UseAlternativeD06DataProps): UseAlternativeD06DataReturn {
  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)

  // ─── 从 htmlData 初始化 ──────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || data._format !== 'alternative-d06-v1') {
      companies.value = []
      return
    }
    companies.value = Array.isArray(data.companies)
      ? data.companies.map(ensureCompanyId)
      : []
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

  // 初始加载
  initFromHtmlData(props.htmlData())

  // 监听 htmlData 变化
  watch(() => props.htmlData(), (newData) => { initFromHtmlData(newData) }, { deep: true })

  // ─── Companies CRUD ────────────────────────────────────────────────────────

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {},
      balance: {},
      block1_rows: [],
      block2_rows: [],
      block3_rows: [],
      block4_rows: [],
      conclusion: {},
      ...partial,
    }
    if (!newCompany._company_id) newCompany._company_id = generateId()
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
    const existingIndexes = new Set(
      companies.value.map((c) => c.confirm_index).filter(Boolean)
    )
    const deduped = items.filter(
      (item) => !item.confirm_index || !existingIndexes.has(item.confirm_index)
    )
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    deduped.forEach((item, i) => {
      const company: AlternativeCompany = {
        _company_id: generateId(),
        seq: maxSeq + i + 1,
        entity_name: item.entity_name || '',
        confirm_index: item.confirm_index,
        _source: item._source || 'auto',
        sampling: item.sampling || {},
        balance: item.balance || {},
        block1_rows: [],
        block2_rows: [],
        block3_rows: [],
        block4_rows: [],
        conclusion: {},
      }
      companies.value.push(company)
    })
    isDirty.value = true
  }

  // ─── 区块行操作 ───────────────────────────────────────────────────────────

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
    const rows = getBlockRows(company, blockType).filter((r) => r._row_id !== rowId)
    setBlockRows(company, blockType, rows)
    isDirty.value = true
  }

  function updateBlockField(companyId: string, blockType: BlockType, rowId: string, field: string, value: any) {
    const company = companies.value.find((c) => c._company_id === companyId)
    if (!company) return
    const rows = getBlockRows(company, blockType)
    const row = rows.find((r) => r._row_id === rowId)
    if (!row) return
    row[field] = value
    isDirty.value = true
  }

  // ─── 计算：区块合计（使用 D06 列配置） ────────────────────────────────────

  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = getSumFieldsD06(blockType)
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

  // ─── 计算：检查比例 ───────────────────────────────────────────────────────

  function getCheckRatio(company: AlternativeCompany, type: 'receipt' | 'shipment'): number | null {
    const salesAmount = company.balance?.sales_amount
    if (!salesAmount || salesAmount === 0) return null

    if (type === 'receipt') {
      // D0-6 区块④ 收款金额合计 / 本期销售额
      const totals = getBlockTotal(company, 'block4')
      const receiptSum = totals['receipt_amount'] ?? 0
      return precise((receiptSum / salesAmount) * 100)
    } else {
      // D0-6 区块③ 出库金额合计 / 本期销售额
      const totals = getBlockTotal(company, 'block3')
      const shipmentSum = totals['product_amount'] ?? 0
      return precise((shipmentSum / salesAmount) * 100)
    }
  }

  // ─── 计算：完成状态 ───────────────────────────────────────────────────────

  function getCompletionStatus(company: AlternativeCompany): { completed: number; total: number; rate: number } {
    const blocks: BlockType[] = ['block1', 'block2', 'block3', 'block4']
    let completed = 0
    for (const bt of blocks) {
      if (getBlockRows(company, bt).length > 0) completed++
    }
    return {
      completed,
      total: 4,
      rate: Math.round((completed / 4) * 100),
    }
  }

  // ─── 计算：是否有异常 ─────────────────────────────────────────────────────

  function hasAbnormal(company: AlternativeCompany): boolean {
    const allBlocks: BlockType[] = ['block1', 'block2', 'block3', 'block4']
    for (const bt of allBlocks) {
      const rows = getBlockRows(company, bt)
      if (rows.some((r) => r.is_abnormal === '是')) return true
    }
    return false
  }

  // ─── 看板指标 ──────────────────────────────────────────────────────────────

  const metrics = computed<AlternativeD05Metrics>(() => {
    const total = companies.value.length
    let completedCount = 0
    let abnormalCount = 0
    const ratioDistribution: AlternativeD05Metrics['ratio_distribution'] = []

    for (const company of companies.value) {
      const status = getCompletionStatus(company)
      if (status.completed === 4) completedCount++
      if (hasAbnormal(company)) abnormalCount++

      ratioDistribution.push({
        entity_name: company.entity_name || '未命名',
        receipt_ratio: getCheckRatio(company, 'receipt'),
        shipment_ratio: getCheckRatio(company, 'shipment'),
      })
    }

    return {
      total_companies: total,
      completed_companies: completedCount,
      abnormal_companies: abnormalCount,
      ratio_distribution: ratioDistribution,
      completion_rate: total > 0 ? Math.round((completedCount / total) * 100) : 0,
    }
  })

  // ─── buildPayload ──────────────────────────────────────────────────────────

  function buildPayload(): AlternativeD06Payload {
    return {
      _format: 'alternative-d06-v1',
      companies: companies.value.map((company) => ({
        ...company,
        balance: {
          ...company.balance,
          receipt_check_ratio: getCheckRatio(company, 'receipt'),
          shipment_check_ratio: getCheckRatio(company, 'shipment'),
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
