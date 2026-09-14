/**
 * G6-11 其他债权投资三阶段划分。
 * 负责检查项维护、阶段判定、明细导入及持久化兼容。
 */
import { computed, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { determineStage } from '@/composables/useG6EclFormulaEngine'

export interface CheckItemDef {
  label: string
  hint: string
}

export const SECTION_ONE_ITEMS: readonly CheckItemDef[] = [
  {
    label: '内部价格指标是否发生显著变化',
    hint: '关注信用风险变化引起的内部定价、收益率或信用利差显著变化。',
  },
  {
    label: '信用利差是否显著变动',
    hint: '比较初始确认日与报告日信用利差及同类工具市场水平。',
  },
  {
    label: '利率或其他合同条款是否发生不利变化',
    hint: '关注新发行时可能要求的更高利率、更严条款或更多增信措施。',
  },
  {
    label: '外部市场指标（如信用违约互换价格）是否恶化',
    hint: '关注信用违约互换价格、公允价值及其他市场信用指标。',
  },
  {
    label: '外部信用评级是否实际或预期下调',
    hint: '结合外部评级及内部评级的实际或预期下调情况判断。',
  },
  {
    label: '借款人经营成果是否实际或预期发生显著不利变化',
    hint: '关注收入、利润、现金流、杠杆及流动性等经营财务指标。',
  },
  {
    label: '所处监管/经济/技术环境是否发生显著不利变化',
    hint: '评估行业政策、宏观经济、地域或技术环境的不利影响。',
  },
  {
    label: '担保物价值或第三方担保质量是否显著下降',
    hint: '评估抵押物价值、担保人能力及其他信用增级的有效性。',
  },
  {
    label: '借款人预期还款行为是否发生显著变化',
    hint: '关注延期、最低还款、资金安排及其他履约行为变化。',
  },
  {
    label: '贷款管理方法是否发生变化（如放宽标准）',
    hint: '关注信用监控、催收、风险分类及管理策略的变化。',
  },
  {
    label: '是否逾期超过30天',
    hint: '逾期达到30日通常推定信用风险显著增加，但可用充分证据反驳。',
  },
  {
    label: '同一借款人其他金融工具是否已发生违约',
    hint: '关注同一发行人或借款人的其他债务违约及交叉违约影响。',
  },
  {
    label: '其他表明信用风险显著增加的信息',
    hint: '记录未被前述项目覆盖但能够支持信用风险显著增加的证据。',
  },
] as const

export const SECTION_TWO_ITEMS: readonly CheckItemDef[] = [
  {
    label: '违约风险较低（如外部评级为投资级）',
    hint: '投资级评级可作参考，但不能仅凭担保物价值较高认定低风险。',
  },
  {
    label: '借款人短期内履行合同义务的能力很强',
    hint: '评估报告日短期偿付能力及可获得的流动性支持。',
  },
  {
    label: '即使经济形势和经营环境存在不利变化也未必降低履约能力',
    hint: '评估较长期不利变化下借款人持续履约能力，三项须同时满足。',
  },
] as const

export const SECTION_THREE_ITEMS: readonly CheckItemDef[] = [
  {
    label: '发行方或债务人发生重大财务困难',
    hint: '关注持续亏损、流动性危机、资不抵债等重大财务困难。',
  },
  {
    label: '债务人违反合同（如偿付利息或本金违约或逾期）',
    hint: '关注本金、利息未按合同约定支付或其他重大违约。',
  },
  {
    label: '债权人出于与债务人财务困难有关的经济或合同考虑给予让步',
    hint: '识别正常情况下不会作出的展期、减免或合同条件修改。',
  },
  {
    label: '债务人很可能破产或进行其他财务重组',
    hint: '关注破产申请、债务重组、接管或类似程序。',
  },
  {
    label: '发行方或债务人财务困难导致该金融资产的活跃市场消失',
    hint: '确认市场消失源于发行人财务困难而非一般市场流动性。',
  },
  {
    label: '以大幅折扣购买或源生一项金融资产（反映了发生信用损失的事实）',
    hint: '判断交易折价是否已反映发行人发生信用损失。',
  },
  {
    label: '债务人经营活动产生的现金流量不足以偿付到期债务',
    hint: '分析经营现金流对到期本金、利息及其他债务的覆盖能力。',
  },
  {
    label: '其他表明已发生信用减值的客观证据',
    hint: '记录未被前述项目覆盖的其他可观察信用减值证据。',
  },
] as const

/** 兼容旧调用方的标签数组导出。 */
export const SECTION_ONE_LABELS: readonly string[] = SECTION_ONE_ITEMS.map(item => item.label)
export const SECTION_TWO_LABELS: readonly string[] = SECTION_TWO_ITEMS.map(item => item.label)
export const SECTION_THREE_LABELS: readonly string[] = SECTION_THREE_ITEMS.map(item => item.label)
export const SECTION_ONE_COUNT = SECTION_ONE_ITEMS.length
export const SECTION_TWO_COUNT = SECTION_TWO_ITEMS.length
export const SECTION_THREE_COUNT = SECTION_THREE_ITEMS.length

export type SectionOneCheckValue = '是' | '否' | '不适用' | ''
export type SectionTwoBoolValue = '是' | '否' | ''
export type StageType = 'Stage1' | 'Stage2' | 'Stage3'
export type SectionKey = 'significantIncrease' | 'lowCreditRisk' | 'creditImpairment'

export interface SectionOneCheck extends CheckItemDef {
  value: SectionOneCheckValue
}

export interface SectionTwoCheck extends CheckItemDef {
  value: SectionTwoBoolValue
}

export interface SectionThreeCheck extends CheckItemDef {
  value: SectionTwoBoolValue
}

export interface SectionAnalysisConclusions {
  significantIncrease: string
  lowCreditRisk: string
  creditImpairment: string
}

export interface StageClassificationRow {
  id: string
  seq: number
  investProject: string
  /** 跨表稳定投资 ID（与 G6-12/G6-13 匹配） */
  crossSheetInvestmentId?: string
  bookBalance: number
  sectionOneChecks: SectionOneCheck[]
  sectionTwoChecks: SectionTwoCheck[]
  sectionThreeChecks: SectionThreeCheck[]
  sectionConclusions: SectionAnalysisConclusions
  hasSignificantIncrease: boolean
  hasLowCreditRisk: boolean
  hasCreditImpairment: boolean
  companyStage: StageType
  auditStage: StageType
  auditStageManualOverride?: boolean
  isConsistent: boolean
  discrepancyNote: string
  indexRef: string
}

export interface ColumnarSourceData {
  columnHeaders: string[]
  sectionOneMatrix: string[][]
  sectionTwoMatrix: string[][]
  sectionThreeMatrix: string[][]
  companyStages?: string[]
}

export interface StageClassificationSummary {
  stage1Count: number
  stage2Count: number
  stage3Count: number
  inconsistentCount: number
  total: number
}

export interface DetailImportResult {
  added: number
  refreshed: number
  prefilledOverdue: number
  /** 逾期≥90日预填已减值/违约推定项数 */
  prefilledDefault: number
}

function newId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `g6-stage-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function emptyConclusions(): SectionAnalysisConclusions {
  return { significantIncrease: '', lowCreditRisk: '', creditImpairment: '' }
}

export function normalizeSectionOneValue(
  raw: string | undefined | null,
): SectionOneCheckValue {
  const value = String(raw ?? '').trim()
  if (!value) return ''
  if (value === '是' || /^(y|yes|1|true)$/i.test(value)) return '是'
  if (value === '不适用' || /^(n\/a|na)$/i.test(value)) return '不适用'
  return '否'
}

export function normalizeBoolValue(
  raw: string | undefined | null,
): SectionTwoBoolValue {
  const value = String(raw ?? '').trim()
  if (!value) return ''
  if (value === '是' || /^(y|yes|1|true)$/i.test(value)) return '是'
  return '否'
}

export function normalizeStage(raw: string | undefined | null): StageType {
  const value = String(raw ?? '').trim().toLowerCase()
  if (value.includes('3') || value.includes('三')) return 'Stage3'
  if (value.includes('2') || value.includes('二')) return 'Stage2'
  return 'Stage1'
}

function buildSectionOne(values?: Array<string | undefined | null>): SectionOneCheck[] {
  return SECTION_ONE_ITEMS.map((item, index) => ({
    ...item,
    value: normalizeSectionOneValue(values?.[index]),
  }))
}

function buildSectionTwo(values?: Array<string | undefined | null>): SectionTwoCheck[] {
  return SECTION_TWO_ITEMS.map((item, index) => ({
    ...item,
    value: normalizeBoolValue(values?.[index]),
  }))
}

function buildSectionThree(values?: Array<string | undefined | null>): SectionThreeCheck[] {
  return SECTION_THREE_ITEMS.map((item, index) => ({
    ...item,
    value: normalizeBoolValue(values?.[index]),
  }))
}

function savedValues(checks: unknown): Array<string | undefined> {
  if (!Array.isArray(checks)) return []
  return checks.map((check) => {
    if (typeof check === 'string') return check
    if (check && typeof check === 'object') {
      return String((check as { value?: unknown }).value ?? '')
    }
    return undefined
  })
}

function toFiniteNumber(value: unknown): number {
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function calcOverdueDays(
  maturityDate: unknown,
  asOfDate?: string | null,
): number {
  if (!maturityDate) return 0
  const maturity = new Date(String(maturityDate))
  const asOf = asOfDate ? new Date(asOfDate) : new Date()
  if (Number.isNaN(maturity.getTime()) || Number.isNaN(asOf.getTime())) return 0
  return Math.max(0, Math.floor((asOf.getTime() - maturity.getTime()) / 86400000))
}

export function getValidColumnIndices(
  headers: string[],
  sectionOne: string[][],
  sectionTwo: string[][],
  sectionThree: string[][],
): number[] {
  const indices: number[] = []
  for (let column = 0; column < headers.length; column += 1) {
    if (headers[column]?.trim()) {
      indices.push(column)
      continue
    }
    const hasData = [sectionOne, sectionTwo, sectionThree]
      .some(matrix => matrix?.some(row => row?.[column]?.trim()))
    if (hasData) indices.push(column)
  }
  return indices
}

export function useG6EclStageClassification(_opts?: unknown) {
  const rows = ref<StageClassificationRow[]>([])
  const conclusion = ref('')
  const expandedRowIds = ref<Set<string>>(new Set())

  function calcHasSignificantIncrease(checks: SectionOneCheck[]): boolean {
    return checks.some(check => check.value === '是')
  }

  function calcHasLowCreditRisk(checks: SectionTwoCheck[]): boolean {
    return checks.length === 3 && checks.every(check => check.value === '是')
  }

  function calcHasCreditImpairment(checks: SectionThreeCheck[]): boolean {
    return checks.some(check => check.value === '是')
  }

  function hasIncompleteChecks(row: StageClassificationRow): boolean {
    return [
      ...row.sectionOneChecks,
      ...row.sectionTwoChecks,
      ...row.sectionThreeChecks,
    ].some(check => check.value === '')
  }

  function recalcRow(row: StageClassificationRow): void {
    row.hasSignificantIncrease = calcHasSignificantIncrease(row.sectionOneChecks)
    row.hasLowCreditRisk = calcHasLowCreditRisk(row.sectionTwoChecks)
    row.hasCreditImpairment = calcHasCreditImpairment(row.sectionThreeChecks)
    if (!row.auditStageManualOverride) {
      row.auditStage = determineStage(
        row.hasSignificantIncrease,
        row.hasLowCreditRisk,
        row.hasCreditImpairment,
      )
    }
    row.isConsistent = row.companyStage === row.auditStage
  }

  function recalcAll(): void {
    rows.value.forEach(recalcRow)
  }

  const summary = computed<StageClassificationSummary>(() => {
    let stage1Count = 0
    let stage2Count = 0
    let stage3Count = 0
    let inconsistentCount = 0
    for (const row of rows.value) {
      if (row.auditStage === 'Stage1') stage1Count += 1
      else if (row.auditStage === 'Stage2') stage2Count += 1
      else stage3Count += 1
      if (!row.isConsistent) inconsistentCount += 1
    }
    return {
      stage1Count,
      stage2Count,
      stage3Count,
      inconsistentCount,
      total: rows.value.length,
    }
  })

  const inconsistentRows = computed(() => rows.value.filter(row => !row.isConsistent))
  const incompleteRows = computed(() => rows.value.filter(hasIncompleteChecks))

  function validateConsistency(): StageClassificationRow[] {
    return rows.value.filter(row => !row.isConsistent && !row.discrepancyNote.trim())
  }

  function canSave(): boolean {
    return validateConsistency().length === 0
  }

  function toggleExpand(rowId: string): void {
    const next = new Set(expandedRowIds.value)
    if (next.has(rowId)) next.delete(rowId)
    else next.add(rowId)
    expandedRowIds.value = next
  }

  function isExpanded(rowId: string): boolean {
    return expandedRowIds.value.has(rowId)
  }

  function expandAll(): void {
    expandedRowIds.value = new Set(rows.value.map(row => row.id))
  }

  function collapseAll(): void {
    expandedRowIds.value = new Set()
  }

  function createEmptyRow(investProject: string): StageClassificationRow {
    const id = newId()
    return {
      id,
      seq: rows.value.length + 1,
      investProject,
      crossSheetInvestmentId: id,
      bookBalance: 0,
      sectionOneChecks: buildSectionOne(),
      sectionTwoChecks: buildSectionTwo(),
      sectionThreeChecks: buildSectionThree(),
      sectionConclusions: emptyConclusions(),
      hasSignificantIncrease: false,
      hasLowCreditRisk: false,
      hasCreditImpairment: false,
      companyStage: 'Stage1',
      auditStage: 'Stage1',
      auditStageManualOverride: false,
      isConsistent: true,
      discrepancyNote: '',
      indexRef: '',
    }
  }

  function transposeToRows(source: ColumnarSourceData): StageClassificationRow[] {
    const {
      columnHeaders,
      sectionOneMatrix,
      sectionTwoMatrix,
      sectionThreeMatrix,
      companyStages,
    } = source
    if (!columnHeaders?.length) return []
    const validIndices = getValidColumnIndices(
      columnHeaders,
      sectionOneMatrix,
      sectionTwoMatrix,
      sectionThreeMatrix,
    )
    return validIndices.map((column, index) => {
      const row = createEmptyRow(columnHeaders[column]?.trim() || `投资${index + 1}`)
      row.seq = index + 1
      row.sectionOneChecks = buildSectionOne(
        SECTION_ONE_ITEMS.map((_, item) => sectionOneMatrix?.[item]?.[column]),
      )
      row.sectionTwoChecks = buildSectionTwo(
        SECTION_TWO_ITEMS.map((_, item) => sectionTwoMatrix?.[item]?.[column]),
      )
      row.sectionThreeChecks = buildSectionThree(
        SECTION_THREE_ITEMS.map((_, item) => sectionThreeMatrix?.[item]?.[column]),
      )
      row.companyStage = normalizeStage(companyStages?.[column])
      recalcRow(row)
      return row
    })
  }

  async function addRow(investProject?: string): Promise<void> {
    let name = investProject?.trim()
    if (!name) {
      try {
        const result = await ElMessageBox.prompt(
          '请输入投资项目名称',
          '新增投资项目',
          { confirmButtonText: '确定', cancelButtonText: '取消' },
        )
        name = result.value?.trim()
      } catch {
        return
      }
    }
    if (name) rows.value.push(createEmptyRow(name))
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(row => row.id !== id)
    rows.value.forEach((row, index) => { row.seq = index + 1 })
    const next = new Set(expandedRowIds.value)
    next.delete(id)
    expandedRowIds.value = next
  }

  function loadRows(data: StageClassificationRow[]): void {
    if (!Array.isArray(data)) {
      rows.value = []
      return
    }
    rows.value = data.map((saved, index) => {
      const source = (saved ?? {}) as Partial<StageClassificationRow>
      const manualOverride = Boolean(source.auditStageManualOverride)
      const row: StageClassificationRow = {
        id: source.id || newId(),
        seq: index + 1,
        investProject: source.investProject || `投资${index + 1}`,
        crossSheetInvestmentId: source.crossSheetInvestmentId || source.id || '',
        bookBalance: toFiniteNumber(source.bookBalance),
        sectionOneChecks: buildSectionOne(savedValues(source.sectionOneChecks)),
        sectionTwoChecks: buildSectionTwo(savedValues(source.sectionTwoChecks)),
        sectionThreeChecks: buildSectionThree(savedValues(source.sectionThreeChecks)),
        sectionConclusions: {
          significantIncrease: source.sectionConclusions?.significantIncrease ?? '',
          lowCreditRisk: source.sectionConclusions?.lowCreditRisk ?? '',
          creditImpairment: source.sectionConclusions?.creditImpairment ?? '',
        },
        hasSignificantIncrease: false,
        hasLowCreditRisk: false,
        hasCreditImpairment: false,
        companyStage: normalizeStage(source.companyStage),
        auditStage: manualOverride ? normalizeStage(source.auditStage) : 'Stage1',
        auditStageManualOverride: manualOverride,
        isConsistent: true,
        discrepancyNote: source.discrepancyNote ?? '',
        indexRef: source.indexRef ?? '',
      }
      if (!row.crossSheetInvestmentId) row.crossSheetInvestmentId = row.id
      recalcRow(row)
      return row
    })
  }

  function loadFromColumnar(source: ColumnarSourceData): void {
    rows.value = transposeToRows(source)
  }

  function updateCheckValue(
    rowId: string,
    section: SectionKey,
    checkIndex: number,
    value: SectionOneCheckValue | SectionTwoBoolValue,
  ): void {
    const row = rows.value.find(item => item.id === rowId)
    if (!row) return
    if (section === 'significantIncrease' && row.sectionOneChecks[checkIndex]) {
      row.sectionOneChecks[checkIndex].value = value as SectionOneCheckValue
    } else if (section === 'lowCreditRisk' && row.sectionTwoChecks[checkIndex]) {
      row.sectionTwoChecks[checkIndex].value = value as SectionTwoBoolValue
    } else if (section === 'creditImpairment' && row.sectionThreeChecks[checkIndex]) {
      row.sectionThreeChecks[checkIndex].value = value as SectionTwoBoolValue
    }
    recalcRow(row)
  }

  function updateCompanyStage(rowId: string, stage: StageType): void {
    const row = rows.value.find(item => item.id === rowId)
    if (!row) return
    row.companyStage = stage
    row.isConsistent = row.companyStage === row.auditStage
  }

  function updateAuditStage(rowId: string, stage: StageType): void {
    const row = rows.value.find(item => item.id === rowId)
    if (!row) return
    row.auditStage = stage
    row.auditStageManualOverride = true
    row.isConsistent = row.companyStage === row.auditStage
  }

  function clearAuditStageOverride(rowId: string): void {
    const row = rows.value.find(item => item.id === rowId)
    if (!row) return
    row.auditStageManualOverride = false
    recalcRow(row)
  }

  function updateDiscrepancyNote(rowId: string, note: string): void {
    const row = rows.value.find(item => item.id === rowId)
    if (row) row.discrepancyNote = note
  }

  function updateSectionConclusion(
    rowId: string,
    section: keyof SectionAnalysisConclusions,
    text: string,
  ): void {
    const row = rows.value.find(item => item.id === rowId)
    if (row) row.sectionConclusions[section] = text
  }

  function updateIndexRef(rowId: string, value: string): void {
    const row = rows.value.find(item => item.id === rowId)
    if (row) row.indexRef = value
  }

  function importFromDetailRows(
    rawRows: unknown[],
    opts?: { asOfDate?: string | null },
  ): DetailImportResult {
    if (!Array.isArray(rawRows) || rawRows.length === 0) {
      return { added: 0, refreshed: 0, prefilledOverdue: 0, prefilledDefault: 0 }
    }
    const byProject = new Map(rows.value.map(row => [row.investProject.trim(), row]))
    let added = 0
    let refreshed = 0
    let prefilledOverdue = 0
    let prefilledDefault = 0

    for (const raw of rawRows) {
      if (!raw || typeof raw !== 'object') continue
      const detail = raw as Record<string, unknown>
      const investProject = String(detail.investProject ?? '').trim()
      if (!investProject) continue

      let row = byProject.get(investProject)
      if (!row) {
        row = createEmptyRow(investProject)
        rows.value.push(row)
        byProject.set(investProject, row)
        added += 1
      } else {
        refreshed += 1
      }

      row.bookBalance = toFiniteNumber(
        detail.closingAudited
        ?? detail.closingSubtotal
        ?? detail.amortizedCost
        ?? detail.bookBalance,
      )
      row.companyStage = normalizeStage(
        String(detail.stageClassification ?? detail.companyStage ?? 'Stage1'),
      )

      const explicitOverdue = toFiniteNumber(detail.overdueDays)
      const overdueDays = explicitOverdue > 0
        ? explicitOverdue
        : calcOverdueDays(detail.maturityDate, opts?.asOfDate)
      if (overdueDays >= 30) {
        const overdueCheck = row.sectionOneChecks.find(check => check.label.includes('逾期'))
        if (overdueCheck && overdueCheck.value !== '是') {
          overdueCheck.value = '是'
          prefilledOverdue += 1
        }
        if (!row.sectionConclusions.significantIncrease.includes('【预填】')) {
          const prompt = `【预填】该项目已逾期${Math.floor(overdueDays)}日（≥30日），请复核是否可反驳信用风险显著增加推定`
          row.sectionConclusions.significantIncrease = [
            prompt,
            row.sectionConclusions.significantIncrease,
          ].filter(Boolean).join('；')
        }
      }
      if (overdueDays >= 90) {
        const defaultCheck = row.sectionThreeChecks.find(
          check => check.label.includes('违反合同') || check.label.includes('逾期'),
        )
        if (defaultCheck && defaultCheck.value !== '是') {
          defaultCheck.value = '是'
          prefilledDefault += 1
        }
        if (!row.sectionConclusions.creditImpairment.includes('【预填】')) {
          const tip = `【预填】已逾期${Math.floor(overdueDays)}日（≥90日通常推定违约/Stage3，可反驳）；请复核是否有合理依据支持更长违约时点`
          row.sectionConclusions.creditImpairment = [
            tip,
            row.sectionConclusions.creditImpairment,
          ].filter(Boolean).join('；')
        }
      }
      recalcRow(row)
    }

    rows.value.forEach((row, index) => { row.seq = index + 1 })
    return { added, refreshed, prefilledOverdue, prefilledDefault }
  }

  function toSaveData() {
    return {
      rows: rows.value,
      summary: summary.value,
      conclusion: conclusion.value,
    }
  }

  function init(htmlData: Record<string, any> | null): void {
    if (!htmlData) return
    const stageData = htmlData.stageClassification ?? htmlData
    if (Array.isArray(stageData?.rows)) loadRows(stageData.rows)
    if (typeof stageData?.conclusion === 'string') conclusion.value = stageData.conclusion
  }

  return {
    rows,
    conclusion,
    expandedRowIds,
    summary,
    inconsistentRows,
    incompleteRows,
    calcHasSignificantIncrease,
    calcHasLowCreditRisk,
    calcHasCreditImpairment,
    hasIncompleteChecks,
    recalcRow,
    recalcAll,
    addRow,
    removeRow,
    loadRows,
    loadFromColumnar,
    createEmptyRow,
    importFromDetailRows,
    transposeToRows,
    getValidColumnIndices,
    normalizeSectionOneValue,
    normalizeBoolValue,
    normalizeStage,
    validateConsistency,
    canSave,
    toggleExpand,
    expandAll,
    collapseAll,
    isExpanded,
    init,
    updateCheckValue,
    updateCompanyStage,
    updateAuditStage,
    clearAuditStageOverride,
    updateDiscrepancyNote,
    updateSectionConclusion,
    updateIndexRef,
    toSaveData,
  }
}

export default useG6EclStageClassification
