/**
 * useG4EclStageClassification — G4-9 三阶段划分（列式→行式转换 + Stage判定 + 一致性比对）
 *
 * 对齐源模板《债权投资三阶段划分G4-9》（致同 2025 修订）：
 * - (一) 14 项 SICR 考虑因素（含逾期≥30日可反驳推定）
 * - (二) 3 项较低信用风险条件（须同时满足方可豁免）
 * - (三) 9 项已发生信用减值可观察信息（含债权投资特有：回售/丧失清偿能力/其他债券违约）
 *
 * 判定优先级：Stage3（已减值）> Stage2（SICR 且未适用低风险豁免）> Stage1
 */
import { ref, computed } from 'vue'
import { determineStage, isStageConsistent } from '@/composables/useG4EclFormulaEngine'
import { ElMessageBox } from 'element-plus'

// ═══ 三区块检查项（对齐源模板原文） ═══

export interface CheckItemDef {
  label: string
  hint: string
}

/** (一) 信用风险是否显著增加 — 14 项（源表 R10–R23） */
export const SECTION_ONE_ITEMS: readonly CheckItemDef[] = [
  {
    label: '信用风险变化所导致的内部价格指标的显著变化',
    hint: '债券信用利差和价格的重大不利变化。例如，同一金融工具或具有相同条款及相同交易对手的类似金融工具，在最近期间发行时的信用利差相对于过去发行时的变化。',
  },
  {
    label: '金融工具的利率或其他条款将发生的显著变化',
    hint: '若现有金融工具在报告日作为新金融工具源生或发行，该金融工具的利率或其他条款将发生的显著变化（如更严格的合同条款、增加抵押品或担保物或者更高的收益率等）；增信措施的有效性发生重大不利变化。',
  },
  {
    label: '类似金融工具的信用风险的外部市场指标的显著变化',
    hint: '包括：①信用利差；②针对借款人的信用违约互换价格；③金融资产的公允价值小于其摊余成本的时间长短和程度；④与发行人相关的其他市场信息（如发行人债务/权益工具的价格变动）。',
  },
  {
    label: '外部信用评级、内部信用评级下调',
    hint: '境外：初始确认 BBB-（含）以上下调至 BBB- 以下；或初始确认已低于 BBB- 的再下调。境内：初始确认 AA（含）以上下调至 AA 以下；或初始确认已低于 AA 的再下调。含对发行人实际或预期的内部评级下调。',
  },
  {
    label: '发行人业务、财务或外部经济状况的不利变化',
    hint: '预期将导致发行人履行偿债义务能力发生显著变化的业务、财务或外部经济状况不利变化（如利率/失业率上升、有息及或有负债增长较快、主要资产权利受限、控股股东/实控人/治理结构重大不利变化、失信惩戒或重大处罚等）。',
  },
  {
    label: '发行人经营成果实际或预期的显著变化',
    hint: '例如收入或毛利率下降、经营风险增加、营运资金短缺、资产质量下降、杠杆率上升、流动比率下降、管理出现问题、业务范围或组织结构变更等。',
  },
  {
    label: '发行人所处的监管、经济或技术环境的显著不利变化',
    hint: '发行人所处行业环境或政策、地域环境的重大不利变化。例如技术变革导致对发行人产品的需求下降。',
  },
  {
    label: '其他金融工具的信用风险的不利变化',
    hint: '同一发行人发行的其他金融工具信用风险显著增加；未按规定履行信息披露义务或募集说明书承诺、未按约定用途使用募集资金等对偿债能力产生重大不利影响。',
  },
  {
    label: '担保或信用增级质量的显著变化',
    hint: '作为债务抵押的担保物价值或第三方担保/信用增级质量的显著变化，预期将降低按约定期限还款的经济动机或影响违约概率。',
  },
  {
    label: '发行人履约还款的经济动机的显著变化',
    hint: '预期将降低借款人按合同约定期限还款经济动机的显著变化（如母公司或其他关联方财务支持减少、信用增级质量变化）；应考虑担保人财务状况、次级权益能否吸收预期信用损失等。',
  },
  {
    label: '发行合同的预期变更',
    hint: '包括预计违反合同可能导致的合同义务免除或修订、给予免息期、利率跳升、要求追加抵押品或担保，或对金融工具合同框架做出其他变更。',
  },
  {
    label: '发行人预期表现和还款行为的显著变化',
    hint: '例如一组贷款资产中延期还款数量或金额增加、接近授信额度或每月最低还款额的持有人预期数量增加。',
  },
  {
    label: '企业对金融工具信用管理方法的变化',
    hint: '例如信用风险管理实务预计将变得更为积极或对该金融工具更加侧重，包括更密切监控/控制、对借款人实施特别干预。',
  },
  {
    label: '逾期信息（逾期≥30日可反驳推定）',
    hint: '合同付款逾期超过（含）30日，通常推定信用风险显著增加；除非以合理成本可获得合理且有依据的信息，证明即使逾期超过30日信用风险仍未显著增加（如管理疏忽而非财务困难，或历史数据表明违约风险上升与逾期>30日无相关性）。',
  },
] as const

/** (二) 是否具有较低信用风险 — 3 项须同时满足（源表 R29–R31） */
export const SECTION_TWO_ITEMS: readonly CheckItemDef[] = [
  {
    label: '金融工具的违约风险较低',
    hint: '通常“投资级”以上外部信用评级可作为参考；不能仅因担保物价值较高，或相对于其他工具/地区风险较低，即视为较低信用风险。',
  },
  {
    label: '借款人在短期内履行其支付合同现金流量义务的能力很强',
    hint: '资产负债表日对短期履约能力的评估结论应可验证。',
  },
  {
    label: '即使较长时期内经济形势和经营环境存在不利变化，也不一定会降低借款人履行其支付合同现金流量义务的能力',
    hint: '满足三项后，企业可选择直接假定信用风险自初始确认后未显著增加（不必与初始确认时比较）。',
  },
] as const

/** (三) 已发生信用减值 — 9 项可观察信息（源表 R37–R45，含债投特有项） */
export const SECTION_THREE_ITEMS: readonly CheckItemDef[] = [
  {
    label: '发行人或债务人发生重大财务困难',
    hint: '对金融资产预期未来现金流量具有不利影响的一项或多项事件发生时，该资产成为已发生信用减值的金融资产。',
  },
  {
    label: '发行人违反合同，如偿付利息或本金违约或逾期等',
    hint: '中证协指引：发行人不能按期偿付本金或利息（1–3项情形可给予不超过30天宽限期）。',
  },
  {
    label: '发行人不能履行回售义务',
    hint: '债权投资特有：回售条款下发行人未能履行回售义务。',
  },
  {
    label: '发行人丧失清偿能力、被法院指定管理人或已开始相关的诉讼程序',
    hint: '中证协客观减值证据之一。',
  },
  {
    label: '债权人出于与债务人财务困难有关的经济或合同考虑，给予债务人在任何其他情况下都不会做出的让步',
    hint: 'CAS 22 标准信用减值迹象。',
  },
  {
    label: '发行人很可能破产或进行其他财务重组',
    hint: '中证协客观减值证据之一。',
  },
  {
    label: '发行人的其他债券违约',
    hint: '债权投资特有：同一发行人其他债券已违约。',
  },
  {
    label: '发行方或债务人财务困难导致该金融资产的活跃市场消失',
    hint: '因财务困难（而非流动性等原因）导致活跃市场消失。',
  },
  {
    label: '以大幅折扣购买或源生一项金融资产，该折扣反映了发生信用损失的事实',
    hint: '购买/源生折扣本身已反映信用损失。',
  },
] as const

/** 兼容旧导出：仅标签数组 */
export const SECTION_ONE_LABELS: readonly string[] = SECTION_ONE_ITEMS.map(i => i.label)
export const SECTION_TWO_LABELS: readonly string[] = SECTION_TWO_ITEMS.map(i => i.label)
export const SECTION_THREE_LABELS: readonly string[] = SECTION_THREE_ITEMS.map(i => i.label)

export const SECTION_ONE_COUNT = SECTION_ONE_ITEMS.length // 14
export const SECTION_TWO_COUNT = SECTION_TWO_ITEMS.length // 3
export const SECTION_THREE_COUNT = SECTION_THREE_ITEMS.length // 9

/** 底部/侧栏编制参考（对齐源模板蓝色提示精要） */
export const G4_9_GUIDANCE = {
  sicrCsrc: [
    '宏观经济环境的重大不利变化',
    '发行人所处行业环境或政策、地域环境的重大不利变化',
    '境内外评级下调达到指引阈值（境外跨 BBB- / 境内跨 AA 或投资级以下再下调）',
    '合并口径主要经营或财务指标重大不利变化（EBITDA利息保障倍数、经营现金流、净利润、资产负债率等）',
    '控股股东、实际控制人或治理结构（董监高）重大不利变化',
    '有息及或有负债快速增长、主要资产权利受限',
    '未履行信息披露义务/募集资金用途违规等对偿债能力有重大不利影响',
    '内部评级下调、增信有效性下降、失信惩戒、重大处罚、债券利差与价格重大不利变化等',
  ],
  overdue30:
    '逾期≥30日：通常推定信用风险显著增加（可反驳）；反驳须有合理成本可获的合理且有依据信息。',
  overdue90:
    '逾期≥90日：通常推定已发生违约/进入第三阶段（可反驳）；违约时点不应迟于逾期90日，除非有合理可支持信息表明更长期间更恰当。',
  lowRisk:
    '资产负债表日具有较低信用风险的，可选用简化处理：不必与初始确认时比较，直接假定信用风险未显著增加。投资级外部评级常作为参考，但不能仅凭担保物价值高认定低风险。',
  priority:
    '判定优先级：已发生信用减值（Stage3）＞ 显著增加且未适用低风险豁免（Stage2）＞ 其余（Stage1，含低风险豁免）。',
} as const

// ═══ 类型定义 ═══

export type SectionOneCheckValue = '是' | '否' | '不适用'
export type SectionTwoBoolValue = '是' | '否'
export type StageType = 'Stage1' | 'Stage2' | 'Stage3'

export interface SectionOneCheck {
  label: string
  hint: string
  value: SectionOneCheckValue
}

export interface SectionTwoCheck {
  label: string
  hint: string
  value: SectionTwoBoolValue
}

export interface SectionThreeCheck {
  label: string
  hint: string
  value: SectionTwoBoolValue
}

export interface SectionAnalysisConclusions {
  significantIncrease: string
  lowCreditRisk: string
  creditImpairment: string
}

/** G4-9 三阶段划分行数据模型 */
export interface StageClassificationRow {
  id: string
  seq: number
  investProject: string
  /** 来自 G4-2 的审定账面余额（同步至 G4-10 用） */
  bookBalance: number
  sectionOneChecks: SectionOneCheck[]
  sectionTwoChecks: SectionTwoCheck[]
  sectionThreeChecks: SectionThreeCheck[]
  /** 各区块分析结论（对齐源表「分析结论」行） */
  sectionConclusions: SectionAnalysisConclusions
  hasSignificantIncrease: boolean
  hasLowCreditRisk: boolean
  hasCreditImpairment: boolean
  companyStage: StageType
  auditStage: StageType
  isConsistent: boolean
  discrepancyNote: string
  indexRef: string
}

/** (一) 逾期信息项下标（0-based，第 14 项） */
export const OVERDUE_CHECK_INDEX = SECTION_ONE_COUNT - 1

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

// ═══ 内部工具 ═══

function emptyConclusions(): SectionAnalysisConclusions {
  return { significantIncrease: '', lowCreditRisk: '', creditImpairment: '' }
}

function buildSectionOne(values?: Array<SectionOneCheckValue | string | undefined>): SectionOneCheck[] {
  return SECTION_ONE_ITEMS.map((item, idx) => ({
    label: item.label,
    hint: item.hint,
    value: normalizeSectionOneValue(values?.[idx]),
  }))
}

function buildSectionTwo(values?: Array<SectionTwoBoolValue | string | undefined>): SectionTwoCheck[] {
  return SECTION_TWO_ITEMS.map((item, idx) => ({
    label: item.label,
    hint: item.hint,
    value: normalizeBoolValue(values?.[idx]),
  }))
}

function buildSectionThree(values?: Array<SectionTwoBoolValue | string | undefined>): SectionThreeCheck[] {
  return SECTION_THREE_ITEMS.map((item, idx) => ({
    label: item.label,
    hint: item.hint,
    value: normalizeBoolValue(values?.[idx]),
  }))
}

/** 标准化(一)区检查值（支持"不适用"） */
function normalizeSectionOneValue(raw: string | undefined | null): SectionOneCheckValue {
  const val = (raw ?? '').trim()
  if (val === '是' || val === 'Y' || val === 'Yes' || val === '1' || val === 'true') return '是'
  if (val === '不适用' || val === 'N/A' || val === 'NA' || val === 'n/a') return '不适用'
  return '否'
}

/** 标准化(二)(三)区检查值（仅是/否） */
function normalizeBoolValue(raw: string | undefined | null): SectionTwoBoolValue {
  const val = (raw ?? '').trim()
  if (val === '是' || val === 'Y' || val === 'Yes' || val === '1' || val === 'true') return '是'
  return '否'
}

/** 标准化Stage值 */
function normalizeStage(raw: string | undefined | null): StageType {
  const val = (raw ?? '').trim().toLowerCase()
  if (val.includes('3') || val.includes('三')) return 'Stage3'
  if (val.includes('2') || val.includes('二')) return 'Stage2'
  return 'Stage1'
}

/**
 * 从旧版 13/8 项检查数组迁移到 14/9。
 * 策略：按索引尽量保留已填值；新增项默认「否」。
 */
function migrateCheckValues<T extends string>(
  saved: Array<{ value?: T } | T> | undefined,
  targetLen: number,
  normalize: (v: string | undefined) => T,
): T[] {
  const out: T[] = []
  for (let i = 0; i < targetLen; i++) {
    const raw = saved?.[i]
    const val = typeof raw === 'string' ? raw : raw?.value
    out.push(normalize(val))
  }
  return out
}

// ═══ Composable ═══

export function useG4EclStageClassification(_opts?: any) {
  const rows = ref<StageClassificationRow[]>([])
  const conclusion = ref('')
  const expandedRowIds = ref<Set<string>>(new Set())

  function calcHasSignificantIncrease(checks: SectionOneCheck[]): boolean {
    return checks.some(c => c.value === '是')
  }

  function calcHasLowCreditRisk(checks: SectionTwoCheck[]): boolean {
    return checks.length === SECTION_TWO_COUNT && checks.every(c => c.value === '是')
  }

  function calcHasCreditImpairment(checks: SectionThreeCheck[]): boolean {
    return checks.some(c => c.value === '是')
  }

  function recalcRow(row: StageClassificationRow): void {
    row.hasSignificantIncrease = calcHasSignificantIncrease(row.sectionOneChecks)
    row.hasLowCreditRisk = calcHasLowCreditRisk(row.sectionTwoChecks)
    row.hasCreditImpairment = calcHasCreditImpairment(row.sectionThreeChecks)
    row.auditStage = determineStage(
      row.hasSignificantIncrease,
      row.hasLowCreditRisk,
      row.hasCreditImpairment,
    )
    row.isConsistent = isStageConsistent(row.companyStage, row.auditStage)
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
      if (row.auditStage === 'Stage1') stage1Count++
      else if (row.auditStage === 'Stage2') stage2Count++
      else stage3Count++
      if (!row.isConsistent) inconsistentCount++
    }
    return { stage1Count, stage2Count, stage3Count, inconsistentCount, total: rows.value.length }
  })

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
    expandedRowIds.value = new Set(rows.value.map(r => r.id))
  }

  function collapseAll(): void {
    expandedRowIds.value = new Set()
  }

  function getValidColumnIndices(
    headers: string[],
    s1: string[][],
    s2: string[][],
    s3: string[][],
  ): number[] {
    const indices: number[] = []
    for (let col = 0; col < headers.length; col++) {
      if (headers[col]?.trim()) {
        indices.push(col)
        continue
      }
      const hasData =
        s1?.some(row => row?.[col]?.trim()) ||
        s2?.some(row => row?.[col]?.trim()) ||
        s3?.some(row => row?.[col]?.trim())
      if (hasData) indices.push(col)
    }
    return indices
  }

  function parseColumnarData(source: ColumnarSourceData): StageClassificationRow[] {
    const { columnHeaders, sectionOneMatrix, sectionTwoMatrix, sectionThreeMatrix, companyStages } = source
    if (!columnHeaders?.length) return []

    const validIndices = getValidColumnIndices(columnHeaders, sectionOneMatrix, sectionTwoMatrix, sectionThreeMatrix)

    return validIndices.map((colIdx, arrIdx) => {
      const investProject = (columnHeaders[colIdx] ?? '').trim()
      const s1vals = SECTION_ONE_ITEMS.map((_, rowIdx) => sectionOneMatrix?.[rowIdx]?.[colIdx])
      const s2vals = SECTION_TWO_ITEMS.map((_, rowIdx) => sectionTwoMatrix?.[rowIdx]?.[colIdx])
      const s3vals = SECTION_THREE_ITEMS.map((_, rowIdx) => sectionThreeMatrix?.[rowIdx]?.[colIdx])

      const row: StageClassificationRow = {
        id: crypto.randomUUID(),
        seq: arrIdx + 1,
        investProject: investProject || `投资${arrIdx + 1}`,
        bookBalance: 0,
        sectionOneChecks: buildSectionOne(s1vals),
        sectionTwoChecks: buildSectionTwo(s2vals),
        sectionThreeChecks: buildSectionThree(s3vals),
        sectionConclusions: emptyConclusions(),
        hasSignificantIncrease: false,
        hasLowCreditRisk: false,
        hasCreditImpairment: false,
        companyStage: normalizeStage(companyStages?.[colIdx]),
        auditStage: 'Stage1',
        isConsistent: true,
        discrepancyNote: '',
        indexRef: '',
      }
      recalcRow(row)
      return row
    })
  }

  function createEmptyRow(investProject: string): StageClassificationRow {
    return {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      investProject,
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
      isConsistent: true,
      discrepancyNote: '',
      indexRef: '',
    }
  }

  async function addRow(investProject?: string): Promise<void> {
    let name = investProject?.trim()
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入投资项目名称',
          '新增投资项目',
          { confirmButtonText: '确定', cancelButtonText: '取消' },
        )
        if (!value?.trim()) return
        name = value.trim()
      } catch {
        return
      }
    }
    rows.value.push(createEmptyRow(name))
  }

  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    const next = new Set(expandedRowIds.value)
    next.delete(id)
    expandedRowIds.value = next
  }

  function loadRows(data: StageClassificationRow[]): void {
    rows.value = data.map((r, i) => {
      const s1vals = migrateCheckValues(
        r.sectionOneChecks as any,
        SECTION_ONE_COUNT,
        normalizeSectionOneValue,
      )
      const s2vals = migrateCheckValues(
        r.sectionTwoChecks as any,
        SECTION_TWO_COUNT,
        normalizeBoolValue,
      )
      const s3vals = migrateCheckValues(
        r.sectionThreeChecks as any,
        SECTION_THREE_COUNT,
        normalizeBoolValue,
      )
      const row: StageClassificationRow = {
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
        investProject: r.investProject || `投资${i + 1}`,
        bookBalance: Number(r.bookBalance) || 0,
        sectionOneChecks: buildSectionOne(s1vals),
        sectionTwoChecks: buildSectionTwo(s2vals),
        sectionThreeChecks: buildSectionThree(s3vals),
        sectionConclusions: {
          significantIncrease: r.sectionConclusions?.significantIncrease ?? '',
          lowCreditRisk: r.sectionConclusions?.lowCreditRisk ?? '',
          creditImpairment: r.sectionConclusions?.creditImpairment ?? '',
        },
        hasSignificantIncrease: false,
        hasLowCreditRisk: false,
        hasCreditImpairment: false,
        companyStage: normalizeStage(r.companyStage),
        auditStage: 'Stage1',
        isConsistent: true,
        discrepancyNote: r.discrepancyNote ?? '',
        indexRef: r.indexRef ?? '',
      }
      recalcRow(row)
      return row
    })
  }

  function loadFromColumnar(source: ColumnarSourceData): void {
    rows.value = parseColumnarData(source)
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
    if (stageData?.rows && Array.isArray(stageData.rows)) {
      loadRows(stageData.rows)
    }
    if (stageData?.conclusion) {
      conclusion.value = stageData.conclusion
    }
  }

  function updateCheckValue(
    rowId: string,
    section: 'significantIncrease' | 'lowCreditRisk' | 'creditImpairment',
    checkIndex: number,
    value: SectionOneCheckValue | SectionTwoBoolValue,
  ): void {
    const row = rows.value.find(r => r.id === rowId)
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
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.companyStage = stage
    row.isConsistent = isStageConsistent(row.companyStage, row.auditStage)
  }

  function updateAuditStage(rowId: string, stage: StageType): void {
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.auditStage = stage
    row.isConsistent = isStageConsistent(row.companyStage, row.auditStage)
  }

  function updateDiscrepancyNote(rowId: string, note: string): void {
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.discrepancyNote = note
  }

  function updateSectionConclusion(
    rowId: string,
    section: keyof SectionAnalysisConclusions,
    text: string,
  ): void {
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.sectionConclusions[section] = text
  }

  const inconsistentRows = computed(() => rows.value.filter(r => !r.isConsistent))

  /**
   * 从 G4-2 明细带入投资项目：
   * - 新增缺失项目；已有项目刷新余额/企业阶段
   * - 逾期≥30日自动预填第14项 SICR=「是」并写入分析结论提示
   */
  function importFromDetailRows(
    rawRows: unknown[],
    opts?: { asOfDate?: string | null },
  ): { added: number; refreshed: number; prefilledOverdue: number } {
    if (!Array.isArray(rawRows) || !rawRows.length) {
      return { added: 0, refreshed: 0, prefilledOverdue: 0 }
    }

    const byName = new Map(rows.value.map(r => [r.investProject.trim(), r]))
    let added = 0
    let refreshed = 0
    let prefilledOverdue = 0

    for (const raw of rawRows) {
      const r = raw as Record<string, any>
      const name = String(r.investProject || '').trim()
      if (!name) continue

      const bal = Number(r.closingAudited ?? r.amortizedCost ?? r.bookBalance ?? 0) || 0
      const companyStage = normalizeStage(r.stageClassification ?? r.companyStage)
      const overdueDays = Number(r.overdueDays) > 0
        ? Number(r.overdueDays)
        : calcOverdueDaysLocal(r.maturityDate, opts?.asOfDate)

      let row = byName.get(name)
      if (!row) {
        row = createEmptyRow(name)
        rows.value.push(row)
        byName.set(name, row)
        added += 1
      } else {
        refreshed += 1
      }

      row.bookBalance = bal
      row.companyStage = companyStage

      if (overdueDays >= 30 && bal > 0) {
        const check = row.sectionOneChecks[OVERDUE_CHECK_INDEX]
        if (check && check.value !== '是') {
          check.value = '是'
          prefilledOverdue += 1
          const tip = `【预填】合同付款相对基准日已逾期${overdueDays}日（≥30日推定SICR，可反驳）`
          if (!row.sectionConclusions.significantIncrease.includes('【预填】')) {
            row.sectionConclusions.significantIncrease = [
              tip,
              row.sectionConclusions.significantIncrease,
            ].filter(Boolean).join('；')
          }
        }
      }

      recalcRow(row)
    }

    rows.value.forEach((r, i) => { r.seq = i + 1 })
    return { added, refreshed, prefilledOverdue }
  }

  function calcOverdueDaysLocal(maturityDate: unknown, asOfDate?: string | null): number {
    if (!maturityDate) return 0
    const mat = new Date(String(maturityDate))
    const asOf = asOfDate ? new Date(asOfDate) : new Date()
    if (Number.isNaN(mat.getTime()) || Number.isNaN(asOf.getTime())) return 0
    const days = Math.round((asOf.getTime() - mat.getTime()) / 86400000)
    return days > 0 ? days : 0
  }

  return {
    rows,
    conclusion,
    expandedRowIds,
    summary,
    inconsistentRows,
    calcHasSignificantIncrease,
    calcHasLowCreditRisk,
    calcHasCreditImpairment,
    recalcRow,
    recalcAll,
    addRow,
    removeRow,
    loadRows,
    loadFromColumnar,
    createEmptyRow,
    importFromDetailRows,
    parseColumnarData,
    getValidColumnIndices,
    normalizeSectionOneValue,
    normalizeBoolValue,
    normalizeStage,
    toggleExpand,
    expandAll,
    collapseAll,
    isExpanded,
    init,
    updateCheckValue,
    updateCompanyStage,
    updateAuditStage,
    updateDiscrepancyNote,
    updateSectionConclusion,
    toSaveData,
  }
}

export default useG4EclStageClassification
