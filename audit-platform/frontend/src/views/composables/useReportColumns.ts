import { computed, type ComputedRef, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ReportRow } from '@/services/auditPlatformApi'

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportColumnsOptions {
  isConsolidated: ComputedRef<boolean>
  activeTab: Ref<string>
  rows: Ref<ReportRow[]>
  /** 附注有内容的 section 集合（从 notes-tree has_data=true 获取） */
  noteHasDataSections?: Ref<Set<string>>
  /** 是否显示金额=0但附注有内容的行 */
  showZeroWithNote?: Ref<boolean>
  /** 动态 row_code→section_code 映射（从后端 report_row_note_mapping.json 按变体加载） */
  rowNoteMapping?: Ref<Record<string, string>>
  /** 后端返回的全局连续附注序号 row_code→seq（跨报表类型连续编排） */
  rowNoteSeqMap?: Ref<Record<string, number>>
  /** 资产负债表 tab 实际显示的附注序号数（供其他 tab 接续编号） */
  bsNoteCount?: Ref<number>
  /** 利润表 tab 实际显示的附注序号数（供现金流量表接续编号） */
  isNoteCount?: Ref<number>
}

export interface UseReportColumnsReturn {
  // Equity columns
  eqColumns: ComputedRef<{ key: string; label: string }[]>
  eqTotalCols: ComputedRef<number>
  equitySpanMethod: (params: { row: any; column: any; rowIndex: number; columnIndex: number }) => { rowspan: number; colspan: number }
  eqRowClassName: (params: { row: any }) => string
  eqCellVal: (row: any, colKey: string, yearKey?: 'current_year' | 'prior_year') => any

  // Impairment columns
  impIncCols: { key: string; label: string }[]
  impDecCols: { key: string; label: string }[]
  impRowClassName: (params: { row: any }) => string

  // Shared helpers
  getRowType: (row: ReportRow) => string
  rowClassName: (params: { row: ReportRow }) => string
  compareRowClassName: (params: { row: any }) => string
  formatReportAmount: (value: any) => { text: string; isNegative: boolean }
  getNoteSection: (rowCode: string) => string | null
  /** 获取动态附注序号（五、N）—— 仅需要披露的行才有序号，连续编排 */
  getNoteLabel: (rowCode: string) => string | null
  goToNote: (rowCode: string) => void
}

// ─── Standalone pure functions (module-level exports) ────────────────────────

/**
 * Row type detection (6 types): header / total / special / manual / zero / data
 * Pure function — no Vue reactivity needed.
 */
export function getRowType(row: ReportRow): string {
  if (row.row_name && (row.row_name.includes('：') || row.row_name.includes(':'))) return 'header'
  if (row.is_total_row) return 'total'
  if (row.row_name && (row.row_name.startsWith('△') || row.row_name.startsWith('▲'))) return 'special'
  if (!row.formula_used && row.current_period_amount === '0') return 'manual'
  if (parseFloat(row.current_period_amount || '0') === 0 && !row.current_period_amount?.includes('.')) return 'zero'
  return 'data'
}

/**
 * Amount formatting — thousands separator + negative brackets.
 * Pure function — no Vue reactivity needed.
 */
export function formatReportAmount(value: any): { text: string; isNegative: boolean } {
  if (value === null || value === undefined || value === '') return { text: '', isNegative: false }
  const num = typeof value === 'string' ? parseFloat(value) : Number(value)
  if (isNaN(num)) return { text: String(value), isNegative: false }
  if (num === 0) return { text: '0.00', isNegative: false }
  const isNeg = num < 0
  const abs = Math.abs(num)
  const parts = abs.toFixed(2).split('.')
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const formatted = parts.join('.')
  const text = isNeg ? `(${formatted})` : formatted
  return { text, isNegative: isNeg }
}

/**
 * Equity span-method — merges category row cells across all equity columns.
 * Pure function — eqColumnsCount is passed as parameter instead of closure.
 */
export function equitySpanMethod(
  { row, columnIndex }: { row: any; column: any; rowIndex: number; columnIndex: number },
  eqColumnsCount: number,
): { rowspan: number; colspan: number } {
  if (row.indent_level === 0 && !row.is_total_row && columnIndex === 0) {
    return { rowspan: 1, colspan: 1 + eqColumnsCount * 2 }
  }
  if (row.indent_level === 0 && !row.is_total_row && columnIndex > 0) {
    return { rowspan: 0, colspan: 0 }
  }
  return { rowspan: 1, colspan: 1 }
}

// ─── Implementation ─────────────────────────────────────────────────────────

const eqColumnsBase = [
  { key: 'paid_in_capital', label: '实收资本' },
  { key: 'other_equity_preferred', label: '优先股' },
  { key: 'other_equity_perpetual', label: '永续债' },
  { key: 'other_equity_other', label: '其他' },
  { key: 'capital_reserve', label: '资本公积' },
  { key: 'treasury_stock', label: '减：库存股' },
  { key: 'oci', label: '其他综合收益' },
  { key: 'special_reserve', label: '专项储备' },
  { key: 'surplus_reserve', label: '盈余公积' },
  { key: 'general_risk', label: '一般风险准备' },
  { key: 'retained_earnings', label: '未分配利润' },
]

const eqConsolExtra = [
  { key: 'subtotal', label: '小计' },
  { key: 'minority', label: '少数股东权益' },
]

const impIncCols = [
  { key: 'provision', label: '本期计提额' },
  { key: 'merge_add', label: '合并增加额' },
  { key: 'other_add', label: '其他原因增加额' },
  { key: 'add_total', label: '合计' },
]

const impDecCols = [
  { key: 'reversal', label: '转回额' },
  { key: 'writeoff', label: '转销额' },
  { key: 'merge_dec', label: '合并减少额' },
  { key: 'other_dec', label: '其他原因减少额' },
  { key: 'dec_total', label: '合计' },
]

/** 前端列键 → 后端 eq_matrix / {{eq:}} 列键 */
const EQ_UI_TO_BACKEND_COL: Record<string, string> = {
  paid_in_capital: 'share_capital',
  other_equity_preferred: 'preferred_stock',
  other_equity_perpetual: 'perpetual_bond',
  other_equity_other: 'other_equity_instrument',
  oci: 'other_comprehensive_income',
  general_risk: 'general_risk_reserve',
  subtotal: 'subtotal',
  minority: 'minority_interest',
  total: 'total_equity',
}

function resolveEqMatrixValue(
  sourceAccounts: Record<string, unknown>,
  colKey: string,
  yearKey: 'current_year' | 'prior_year' = 'current_year',
): unknown {
  const matrix = sourceAccounts.eq_matrix
  if (!matrix || typeof matrix !== 'object') return undefined
  const yearBlock = (matrix as Record<string, unknown>)[yearKey]
  if (!yearBlock || typeof yearBlock !== 'object') return undefined
  const backendKey = EQ_UI_TO_BACKEND_COL[colKey] ?? colKey
  return (yearBlock as Record<string, unknown>)[backendKey]
}

// ─── 报表行→附注 动态序号映射 ─────────────────────────────────────────────
// 附注序号不再固定（五、1=货币资金），而是按实际需要披露的行从 1 连续编排。
// 需要披露条件：(金额≠0) || (金额=0 但附注模块有对应内容)

/**
 * 报表行 row_code → 附注模板 section（用于跳转）的固定映射。
 * 这是"哪些报表行理论上可以有附注"的声明，序号在运行时动态分配。
 */
const _ROW_NOTE_SECTION_MAP: Record<string, string> = {
  // 流动资产
  'BS-002': '五、1',   // 货币资金
  'BS-003': '五、2',   // 交易性金融资产
  'BS-004': '五、3',   // 衍生金融资产
  'BS-005': '五、4',   // 应收票据
  'BS-006': '五、5',   // 应收账款
  'BS-007': '五、6',   // 应收款项融资
  'BS-008': '五、7',   // 预付款项
  'BS-009': '五、8',   // 其他应收款
  'BS-010': '五、9',   // 存货
  'BS-011': '五、10',  // 合同资产
  'BS-012': '五、11',  // 持有待售资产
  'BS-013': '五、12',  // 一年内到期的非流动资产
  'BS-014': '五、13',  // 其他流动资产
  // 非流动资产
  'BS-021': '五、14',  // 债权投资
  'BS-022': '五、15',  // 其他债权投资
  'BS-023': '五、16',  // 长期应收款
  'BS-024': '五、18',  // 长期股权投资
  'BS-025': '五、19',  // 其他权益工具投资
  'BS-026': '五、20',  // 其他非流动金融资产
  'BS-027': '五、21',  // 投资性房地产
  'BS-028': '五、22',  // 固定资产
  'BS-029': '五、23',  // 在建工程
  'BS-030': '五、24',  // 生产性生物资产
  'BS-031': '五、25',  // 使用权资产
  'BS-032': '五、26',  // 无形资产
  'BS-033': '五、27',  // 开发支出
  'BS-034': '五、28',  // 商誉
  'BS-035': '五、29',  // 长期待摊费用
  'BS-036': '五、30',  // 递延所得税资产
  'BS-037': '五、31',  // 其他非流动资产
  // 流动负债
  'BS-041': '五、33',  // 短期借款
  'BS-042': '五、34',  // 交易性金融负债
  'BS-043': '五、35',  // 衍生金融负债
  'BS-044': '五、36',  // 应付票据
  'BS-045': '五、37',  // 应付账款
  'BS-046': '五、38',  // 预收款项
  'BS-047': '五、39',  // 合同负债
  'BS-048': '五、40',  // 应付职工薪酬
  'BS-049': '五、41',  // 应交税费
  'BS-050': '五、42',  // 其他应付款
  'BS-052': '五、43',  // 一年内到期的非流动负债
  'BS-053': '五、44',  // 其他流动负债
  // 非流动负债
  'BS-061': '五、45',  // 长期借款
  'BS-062': '五、46',  // 应付债券
  'BS-063': '五、47',  // 租赁负债
  'BS-064': '五、48',  // 长期应付款
  'BS-065': '五、50',  // 预计负债
  'BS-066': '五、51',  // 递延收益
  'BS-067': '五、30',  // 递延所得税负债（与资产共用章节）
  'BS-068': '五、52',  // 其他非流动负债
  // 所有者权益
  'BS-081': '五、53',  // 实收资本（或股本）
  'BS-082': '五、54',  // 其他权益工具
  'BS-083': '五、55',  // 资本公积
  'BS-084': '五、56',  // 减：库存股
  'BS-085': '五、57',  // 其他综合收益
  'BS-086': '五、58',  // 专项储备
  'BS-087': '五、59',  // 盈余公积
  'BS-088': '五、61',  // 未分配利润
  // 利润表
  'IS-001': '五、62',  // 营业收入（与营业成本合并章节）
  'IS-002': '五、62',  // 营业成本（与营业收入合并章节）
  'IS-003': '五、63',  // 税金及附加
  'IS-004': '五、64',  // 销售费用
  'IS-005': '五、65',  // 管理费用
  'IS-006': '五、66',  // 研发费用
  'IS-007': '五、67',  // 财务费用
  'IS-008': '五、68',  // 其他收益
  'IS-010': '五、68',  // 其他收益（listed 为 IS-010）
  'IS-011': '五、69',  // 投资收益
  'IS-014': '五、70',  // 净敞口套期收益
  'IS-015': '五、71',  // 公允价值变动收益
  'IS-016': '五、72',  // 信用减值损失
  'IS-017': '五、73',  // 资产减值损失
  'IS-018': '五、74',  // 资产处置收益
  'IS-020': '五、75',  // 营业外收入
  'IS-021': '五、76',  // 营业外支出
  // 现金流量表（其他项）
  'CFS-004': '五、77',  // 收到其他与经营活动有关的现金
  'CFS-009': '五、78',  // 支付其他与经营活动有关的现金
  'CFS-017': '五、79',  // 收到其他与投资活动有关的现金
  'CFS-024': '五、80',  // 收到其他与投资活动有关的现金
  'CFS-028': '五、81',  // 支付其他与投资活动有关的现金
  'CFS-035': '五、82',  // 支付其他与筹资活动有关的现金
  'CFS-043': '五、83',  // 收到其他与筹资活动有关的现金
  'CFS-047': '五、84',  // 支付其他与筹资活动有关的现金
}

/** 判断报表行是否有对应附注映射 */
export function hasNoteMappingForRow(rowCode: string): boolean {
  return rowCode in _ROW_NOTE_SECTION_MAP
}

/** 获取跳转目标 section（用于 router.push 到附注模块） */
export function getNoteSectionForJump(rowCode: string): string | null {
  return _ROW_NOTE_SECTION_MAP[rowCode] || null
}

export function useReportColumns(options: UseReportColumnsOptions): UseReportColumnsReturn {
  const { isConsolidated, activeTab, rows, noteHasDataSections, showZeroWithNote, rowNoteMapping, rowNoteSeqMap, bsNoteCount, isNoteCount } = options
  const router = useRouter()

  // ─── Equity columns (computed) ──────────────────────────────────────────────
  const eqColumns = computed(() => {
    const base = [...eqColumnsBase]
    if (isConsolidated.value) {
      base.push(...eqConsolExtra)
    }
    base.push({ key: 'total', label: '所有者权益合计' })
    return base
  })

  const eqTotalCols = computed(() => eqColumns.value.length)

  // ─── Equity span-method (wraps standalone function with closure eqColumns count) ──
  function _equitySpanMethod(params: { row: any; column: any; rowIndex: number; columnIndex: number }) {
    return equitySpanMethod(params, eqColumns.value.length)
  }

  // ─── Equity row class ───────────────────────────────────────────────────────
  function eqRowClassName({ row }: { row: any }) {
    if (row.is_total_row) return 'gt-rv-eq-total-row'
    if (row.indent_level === 0) return 'gt-rv-eq-category'
    return ''
  }

  // ─── Equity cell value ──────────────────────────────────────────────────────
  function eqCellVal(
    row: any,
    colKey: string,
    yearKey: 'current_year' | 'prior_year' = 'current_year',
  ): any {
    if (!row) return 0
    const sa = row.source_accounts
    if (!sa || typeof sa !== 'object' || Array.isArray(sa)) {
      if (colKey === 'total') {
        return yearKey === 'prior_year'
          ? (row.prior_period_amount ?? 0)
          : (row.current_period_amount ?? 0)
      }
      return 0
    }
    if (yearKey === 'current_year') {
      const flat = (sa as Record<string, unknown>)[colKey]
      if (flat != null) return flat
    }
    const fromMatrix = resolveEqMatrixValue(sa as Record<string, unknown>, colKey, yearKey)
    if (fromMatrix != null) return fromMatrix
    if (colKey === 'total') {
      return yearKey === 'prior_year'
        ? (row.prior_period_amount ?? 0)
        : (row.current_period_amount ?? 0)
    }
    return 0
  }

  // ─── Impairment row class ───────────────────────────────────────────────────
  function impRowClassName({ row }: { row: any }) {
    if (row.is_total_row) return 'gt-rv-eq-total-row'
    return ''
  }

  // ─── Row type detection (delegates to module-level export) ───────────────────

  // ─── Row class name ─────────────────────────────────────────────────────────
  function rowClassName({ row }: { row: ReportRow }) {
    const type = getRowType(row)
    return `report-row--${type}`
  }

  // ─── Compare row class name ─────────────────────────────────────────────────
  function compareRowClassName({ row }: { row: any }) {
    const type = getRowType(row)
    if (row.adjustment && row.adjustment !== 0) return `report-row--${type} diff-row`
    return `report-row--${type}`
  }

  // ─── Amount formatting (delegates to module-level export) ────────────────────

  // ─── Note section mapping (dynamic sequential numbering) ─────────────────
  /**
   * 动态附注序号映射表：按实际需要披露的行从 五、1 连续编排。
   * 需要披露条件：
   * - 该 row_code 在 _ROW_NOTE_SECTION_MAP 中有映射（理论上可有附注）
   * - 且 (本期金额≠0 或 上期金额≠0) || (金额=0 但 noteHasDataSections 含该 section 且 showZeroWithNote=true)
   */
  /**
   * 全局附注序号映射：row_code→seq 按映射表完整顺序（BS→IS→CFS→EQ→CFSS）全局连续编排。
   * 序号不受当前 tab 切换影响，利润表接续资产负债表的序号。
   * 仅有金额或有附注内容的行才分配序号（跳过零额且无内容的行），
   * 但保持全局连续（不因切 tab 重新从 1 开始）。
   *
   * 当后端 rowNoteSeqMap 有数据时直接使用后端全局 seq（最权威），否则按硬编码 map 排列。
   */
  const noteSequenceMap = computed(() => {
    const map = new Map<string, { seq: number; section: string }>()

    // 优先使用后端全局 seq（跨 tab 连续，后端已按有数据行编号）
    const backendSeq = rowNoteSeqMap?.value || {}
    const backendMapping = rowNoteMapping?.value || {}
    if (Object.keys(backendSeq).length > 0) {
      for (const row of rows.value) {
        if (!row.row_code) continue
        const seq = backendSeq[row.row_code]
        const section = backendMapping[row.row_code]
        if (!seq || !section) continue
        map.set(row.row_code, { seq, section })
      }
      return map
    }

    // 回退：按当前报表数据实际情况，仅有金额的行从 1 连续编号（不跳号）
    // 注：跨 tab 接续需后端 row-note-mapping API 就绪后生效
    const sectionMap = (rowNoteMapping?.value && Object.keys(rowNoteMapping.value).length > 0)
      ? rowNoteMapping.value
      : _ROW_NOTE_SECTION_MAP
    const hasDataSet = noteHasDataSections?.value || new Set<string>()
    const showZero = showZeroWithNote?.value ?? true

    let seq = 0
    for (const row of rows.value) {
      if (!row.row_code) continue
      const section = sectionMap[row.row_code]
      if (!section) continue

      const currentAmt = Math.abs(parseFloat(row.current_period_amount || '0') || 0)
      const priorAmt = Math.abs(parseFloat(row.prior_period_amount || '0') || 0)
      const hasAmount = currentAmt > 0.005 || priorAmt > 0.005

      // 只有实际有金额的行才分配附注序号（金额为 0 不编号）
      if (hasAmount) {
        seq++
        map.set(row.row_code, { seq, section })
      }
    }
    return map
  })

  /** 获取动态附注序号标签（五、N）—— 使用后端全局连续序号（跨报表类型接续），无则不显示 */
  function getNoteLabel(rowCode: string): string | null {
    // 优先使用后端返回的 section_code（真实附注章节号）
    const backendMapping = rowNoteMapping?.value || {}
    if (Object.keys(backendMapping).length > 0) {
      const sectionCode = backendMapping[rowCode]
      if (sectionCode) return sectionCode
      return null
    }

    // 回退：按实际有金额的行动态编号，跨 tab 接续
    const entry = noteSequenceMap.value.get(rowCode)
    if (!entry) return null

    const currentTab = activeTab?.value || ''
    const maxSeqInTab = Math.max(...Array.from(noteSequenceMap.value.values()).map(e => e.seq), 0)

    if (currentTab === 'balance_sheet') {
      if (bsNoteCount && maxSeqInTab > 0) bsNoteCount.value = maxSeqInTab
      return `五、${entry.seq}`
    }

    if (currentTab === 'income_statement') {
      const bsOffset = bsNoteCount?.value || 0
      if (isNoteCount && maxSeqInTab > 0) isNoteCount.value = maxSeqInTab
      return `五、${bsOffset + entry.seq}`
    }

    // 现金流量表及其他：接续 BS + IS
    const totalOffset = (bsNoteCount?.value || 0) + (isNoteCount?.value || 0)
    return `五、${totalOffset + entry.seq}`
  }

  /** 获取跳转目标 section（兼容旧调用方） */
  function getNoteSection(rowCode: string): string | null {
    const entry = noteSequenceMap.value.get(rowCode)
    if (!entry) return null
    return entry.section
  }

  function goToNote(rowCode: string) {
    const section = getNoteSection(rowCode)
    if (section) {
      router.push({ path: `/projects/${router.currentRoute.value.params.projectId}/disclosure-notes`, query: { section } })
    }
  }

  return {
    eqColumns,
    eqTotalCols,
    equitySpanMethod: _equitySpanMethod,
    eqRowClassName,
    eqCellVal,
    impIncCols,
    impDecCols,
    impRowClassName,
    getRowType,
    rowClassName,
    compareRowClassName,
    formatReportAmount,
    getNoteSection,
    getNoteLabel,
    goToNote,
  }
}
