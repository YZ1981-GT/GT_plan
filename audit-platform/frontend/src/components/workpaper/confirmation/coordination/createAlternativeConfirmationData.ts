/**
 * createAlternativeConfirmationData.ts — 函证替代程序数据 Shared_Core 工厂
 *
 * 背景（confirmation-alternative-factory-convergence spec）：
 * 函证替代程序模块存在八套近乎逐字重复的数据 composable
 * （useAlternative{D05,D06,F05,F06,H05,K05,K06,L05}Data）。本工厂吸收八套
 * **逐字相同**的 Shared_Core（公司/区块 CRUD、区块合计、通用比例、完成度、
 * 异常检测、看板 metrics、init/watch 骨架、buildPayload 骨架），差异经
 * AltConfig 纯数据声明；无法配置化的异质面（命名比例方法别名、构造签名变体、
 * K06 http load/persist、importFromSummary、balanceSummary 等）由每套薄适配器旁挂。
 *
 * 逐字来源：alternativeD05/composables/useAlternativeData.ts
 * 设计参考：design.md §3 工厂 API、§Data Models、Correctness Properties P1-P10
 *
 * 零回归约束：本工厂不新增任何错误处理路径或数值语义，所有行为与八套现状逐字一致。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type {
  AlternativeCompany,
  AlternativeD05Metrics,
  CheckRow,
  BlockType,
} from '../alternativeD05/alternativeD05Types'

// ─── ID 生成工具（逐字对齐 D05） ─────────────────────────────────────────────

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
}

/** 精确小数（避免浮点漂移） */
function precise(n: number): number {
  return Math.round(n * 100) / 100
}

/** 默认数值解析：Number()＋NaN→0（与各套 getBlockTotal 逐字等价） */
function defaultParseNum(v: any): number {
  const n = Number(v)
  return isNaN(n) ? 0 : n
}

/** 默认合计：纯求和 */
function defaultCalcTotal(amounts: number[]): number {
  return amounts.reduce((sum, n) => sum + n, 0)
}

/** 默认比例：num / den */
function defaultCalcRatio(num: number, den: number): number {
  return num / den
}

// ─── 配置模型 ────────────────────────────────────────────────────────────────

/** 单条比例规则（Check_Ratio 的数据化声明） */
export interface RatioRule {
  /** 逻辑比例名，如 'receipt' | 'payment' | 'ownership' | 'postPayment' */
  key: string
  /** 求和目标区块 */
  block: BlockType
  /**
   * 求和字段优先级：取第一个"存在于 total 且非 undefined"的 total 值
   * （对照各套 `totals.a ?? totals.b ?? 0` 语义）
   */
  fields: string[]
  /** 写回 balance 的字段名，如 'receipt_check_ratio' */
  payloadKey: string
  /** per-rule 覆盖比例算法（L05 repayment 用 calcRepaymentRatio） */
  calcRatio?: (num: number, den: number) => number
}

export interface AltConfig {
  /** payload _format 串 */
  format: string
  /** 区块合计字段来源函数 */
  getSumFields: (blockType: string) => string[]
  /** 新增/导入公司时的默认 balance（函数避免共享引用） */
  defaultBalance: () => Record<string, any>
  /** 比例分母基数（各自回退顺序封装于此） */
  baseAmount: (company: AlternativeCompany) => number
  /** 比例规则（通常两条） */
  ratios: RatioRule[]
  /** 基数为 0/缺失时比例返回（默认 'null'；L05='zero'） */
  emptyBase?: 'null' | 'zero'
  /** metrics.ratio_distribution 映射到哪两个 ratio key */
  metricRatioKeys: { receipt: string; shipment: string }
  /** 可注入 FormulaEngine 的合计（默认纯 sum） */
  calcTotal?: (amounts: number[]) => number
  /** 可注入 FormulaEngine 的比例（默认 num/den） */
  calcRatio?: (num: number, den: number) => number
  /** 可注入的数值解析（默认 Number()＋NaN→0） */
  parseNum?: (v: any) => number
  /** 提供则工厂做 init+watch(deep)；不传则不 init（K06 自管 loadAll） */
  htmlData?: () => any
}

// ─── 返回接口 ────────────────────────────────────────────────────────────────

export interface AltCoreReturn {
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
  getRatio: (company: AlternativeCompany, key: string) => number | null
  getCompletionStatus: (company: AlternativeCompany) => { completed: number; total: number; rate: number }
  hasAbnormal: (company: AlternativeCompany) => boolean

  // 看板
  metrics: ComputedRef<AlternativeD05Metrics>

  // 持久化
  buildPayload: () => { _format: string; companies: AlternativeCompany[] }

  // 内部工具暴露给适配器复用
  _getBlockRows: (company: AlternativeCompany, blockType: BlockType) => CheckRow[]
  _ensureCompanyId: (company: AlternativeCompany) => AlternativeCompany
  _ensureRowId: (row: CheckRow) => CheckRow
  _generateId: () => string
  _precise: (n: number) => number
  _initFromHtmlData: (data: any) => void
}

// ─── 工厂主体 ────────────────────────────────────────────────────────────────

export function createAlternativeConfirmationData(config: AltConfig): AltCoreReturn {
  const emptyBase = config.emptyBase ?? 'null'
  const parseNum = config.parseNum ?? defaultParseNum
  const calcTotal = config.calcTotal ?? defaultCalcTotal
  const calcRatio = config.calcRatio ?? defaultCalcRatio

  const companies = ref<AlternativeCompany[]>([])
  const isDirty = ref(false)
  const selectedCompanyId = ref<string | null>(null)

  // ─── 从 htmlData 初始化 ──────────────────────────────────────────────────

  function initFromHtmlData(data: any) {
    if (!data || data._format !== config.format) {
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

  // ─── Companies CRUD ────────────────────────────────────────────────────────

  function addCompany(partial?: Partial<AlternativeCompany>): AlternativeCompany {
    const maxSeq = companies.value.reduce((max, c) => Math.max(max, c.seq ?? 0), 0)
    const newCompany: AlternativeCompany = {
      _company_id: generateId(),
      seq: maxSeq + 1,
      entity_name: '',
      _source: 'manual',
      sampling: {},
      balance: config.defaultBalance(),
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
    // 按 confirm_index 去重
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
        balance: { ...config.defaultBalance(), ...(item.balance || {}) },
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

  // ─── 计算：区块合计 ───────────────────────────────────────────────────────

  function getBlockTotal(company: AlternativeCompany, blockType: BlockType): Record<string, number> {
    const rows = getBlockRows(company, blockType)
    const fields = config.getSumFields(blockType)
    const totals: Record<string, number> = {}
    for (const field of fields) {
      const amounts = rows.map((row) => parseNum(row[field]))
      totals[field] = precise(calcTotal(amounts))
    }
    return totals
  }

  // ─── 计算：检查比例（通用，按 config.ratios[key]） ────────────────────────

  function getRatio(company: AlternativeCompany, key: string): number | null {
    const rule = config.ratios.find((r) => r.key === key)
    if (!rule) return null
    const t = getBlockTotal(company, rule.block)
    // 字段回退：取 fields 中第一个在 total 里有值（非 undefined）的
    const sum = rule.fields.reduce<number | undefined>(
      (acc, f) => (acc !== undefined ? acc : t[f]),
      undefined
    ) ?? 0
    const base = config.baseAmount(company)
    if (!base || base === 0) return emptyBase === 'zero' ? 0 : null
    const fn = rule.calcRatio || calcRatio
    return precise(fn(sum, base) * 100)
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
        receipt_ratio: getRatio(company, config.metricRatioKeys.receipt),
        shipment_ratio: getRatio(company, config.metricRatioKeys.shipment),
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

  function buildPayload(): { _format: string; companies: AlternativeCompany[] } {
    return {
      _format: config.format,
      companies: companies.value.map((company) => {
        const ratioPatch: Record<string, number | null> = {}
        for (const rule of config.ratios) {
          ratioPatch[rule.payloadKey] = getRatio(company, rule.key)
        }
        return {
          ...company,
          balance: {
            ...company.balance,
            ...ratioPatch,
          },
        }
      }),
    }
  }

  // ─── init + watch（K06 不传 htmlData → 自管 loadAll） ────────────────────

  if (config.htmlData) {
    initFromHtmlData(config.htmlData())
    watch(() => config.htmlData!(), (newData) => { initFromHtmlData(newData) }, { deep: true })
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
    getRatio,
    getCompletionStatus,
    hasAbnormal,

    metrics,
    buildPayload,

    _getBlockRows: getBlockRows,
    _ensureCompanyId: ensureCompanyId,
    _ensureRowId: ensureRowId,
    _generateId: generateId,
    _precise: precise,
    _initFromHtmlData: initFromHtmlData,
  }
}
