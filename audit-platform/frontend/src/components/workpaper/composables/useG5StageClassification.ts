/**
 * useG5StageClassification — G5-9 长期应收款三阶段划分（列式→行式转换 + Stage判定 + 一致性比对）
 *
 * Spec: .kiro/specs/g5-long-term-receivable/ Task 11.1
 * Requirements: 12.1~12.10
 *
 * 职责：
 * - 列式→行式转换：解析源模板列式数据（债务人1~N各占一列），转为行式reactive数组
 * - 三区块综合判定逻辑：
 *   (一) 13项任一为"是" → hasSignificantIncrease=true
 *   (二) 3项全为"是"   → hasLowCreditRisk=true
 *   (三) 8项任一为"是" → hasCreditImpairment=true
 * - Stage判定（调用 determineStage）
 * - 一致性比对（companyStage === auditStage）
 * - 汇总统计（stage1Count / stage2Count / stage3Count / inconsistentCount）
 * - 16384列智能解析（仅取有数据列，忽略空列）
 * - 展开/折叠切换逻辑
 *
 * 与G4-9的差异：字段名"投资项目"→"债务人"，引用G5自己的FormulaEngine
 */
import { ref, computed, type Ref } from 'vue'
import { determineStage } from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

// ═══ 三区块检查项标签常量 ═══

/** (一) 信用风险是否显著增加 — 13项考虑因素 */
export const SECTION_ONE_LABELS: readonly string[] = [
  '内部价格指标是否发生显著变化',
  '信用利差是否显著变动',
  '利率或其他合同条款是否发生不利变化',
  '外部市场指标（如信用违约互换价格）是否恶化',
  '外部信用评级是否实际或预期下调',
  '债务人经营成果是否实际或预期发生显著不利变化',
  '所处监管/经济/技术环境是否发生显著不利变化',
  '担保物价值或第三方担保质量是否显著下降',
  '债务人预期还款行为是否发生显著变化',
  '贷款管理方法是否发生变化（如放宽标准）',
  '是否逾期超过30天',
  '同一债务人其他金融工具是否已发生违约',
  '其他表明信用风险显著增加的信息',
] as const

/** (二) 是否具有较低信用风险 — 3项同时满足条件 */
export const SECTION_TWO_LABELS: readonly string[] = [
  '违约风险较低（如外部评级为投资级）',
  '债务人短期内履行合同义务的能力很强',
  '即使经济形势和经营环境存在不利变化也未必降低履约能力',
] as const

/** (三) 已发生信用减值的评估 — 8项可观察信息 */
export const SECTION_THREE_LABELS: readonly string[] = [
  '债务人发生重大财务困难',
  '债务人违反合同（如偿付利息或本金违约或逾期）',
  '债权人出于与债务人财务困难有关的经济或合同考虑给予让步',
  '债务人很可能破产或进行其他财务重组',
  '债务人财务困难导致该金融资产的活跃市场消失',
  '以大幅折扣购买或源生一项金融资产（反映了发生信用损失的事实）',
  '债务人经营活动产生的现金流量不足以偿付到期债务',
  '其他表明已发生信用减值的客观证据',
] as const

// ═══ 类型定义 ═══

export type SectionOneCheckValue = '是' | '否' | '不适用'
export type SectionTwoBoolValue = '是' | '否'
export type StageType = 'Stage1' | 'Stage2' | 'Stage3'

export interface SectionOneCheck {
  label: string
  value: SectionOneCheckValue
}

export interface SectionTwoCheck {
  label: string
  value: SectionTwoBoolValue
}

export interface SectionThreeCheck {
  label: string
  value: SectionTwoBoolValue
}

/** G5-9 三阶段划分行数据模型 */
export interface G5StageClassificationRow {
  id: string
  seq: number
  debtor: string // G5用"债务人"(区别于G4的"投资项目")
  // 三区块检查明细
  sectionOneChecks: SectionOneCheck[]       // 13项
  sectionTwoChecks: SectionTwoCheck[]       // 3项
  sectionThreeChecks: SectionThreeCheck[]   // 8项
  // 综合判定
  hasSignificantIncrease: boolean   // (一)任一为"是"
  hasLowCreditRisk: boolean         // (二)全部为"是"
  hasCreditImpairment: boolean      // (三)任一为"是"
  companyStage: StageType           // 企业划分阶段(下拉)
  auditStage: StageType             // 审计判断阶段(公式建议)
  isConsistent: boolean             // companyStage === auditStage
  discrepancyNote: string           // 差异说明(不一致时必填)
  indexRef: string                  // 索引
}

/** 列式源数据结构（源模板格式/导入） */
export interface ColumnarSourceData {
  /** 列头：各债务人名称 */
  columnHeaders: string[]
  /** (一) 13行×N列矩阵 */
  sectionOneMatrix: string[][]
  /** (二) 3行×N列矩阵 */
  sectionTwoMatrix: string[][]
  /** (三) 8行×N列矩阵 */
  sectionThreeMatrix: string[][]
  /** 企业划分阶段（N列） */
  companyStages?: string[]
}

export interface G5StageClassificationSummary {
  stage1Count: number
  stage2Count: number
  stage3Count: number
  inconsistentCount: number
  total: number
}

// ═══ Composable ═══

export function useG5StageClassification(_opts?: any) {
  // ─── 核心状态 ──────────────────────────────────────────────────────────────

  const rows = ref<G5StageClassificationRow[]>([])
  const conclusion = ref('')
  const expandedRowIds = ref<Set<string>>(new Set())

  // ─── 三区块综合判定逻辑 ────────────────────────────────────────────────────

  /** (一) 13项任一为"是" → hasSignificantIncrease=true */
  function calcHasSignificantIncrease(checks: SectionOneCheck[]): boolean {
    return checks.some(c => c.value === '是')
  }

  /** (二) 3项全为"是" → hasLowCreditRisk=true */
  function calcHasLowCreditRisk(checks: SectionTwoCheck[]): boolean {
    return checks.length === 3 && checks.every(c => c.value === '是')
  }

  /** (三) 8项任一为"是" → hasCreditImpairment=true */
  function calcHasCreditImpairment(checks: SectionThreeCheck[]): boolean {
    return checks.some(c => c.value === '是')
  }

  // ─── 行级重算 ─────────────────────────────────────────────────────────────

  /** 重算单行综合判定 + auditStage + 一致性 */
  function recalcRow(row: G5StageClassificationRow): void {
    row.hasSignificantIncrease = calcHasSignificantIncrease(row.sectionOneChecks)
    row.hasLowCreditRisk = calcHasLowCreditRisk(row.sectionTwoChecks)
    row.hasCreditImpairment = calcHasCreditImpairment(row.sectionThreeChecks)
    row.auditStage = determineStage(
      row.hasSignificantIncrease,
      row.hasLowCreditRisk,
      row.hasCreditImpairment,
    )
    row.isConsistent = row.companyStage === row.auditStage
  }

  /** 重算所有行 */
  function recalcAll(): void {
    rows.value.forEach(recalcRow)
  }

  // ─── 汇总统计 ─────────────────────────────────────────────────────────────

  const summary = computed<G5StageClassificationSummary>(() => {
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

  // ─── 展开/折叠切换 ────────────────────────────────────────────────────────

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

  // ─── 16384列智能解析（列式→行式转换）────────────────────────────────────────

  function parseColumnarData(source: ColumnarSourceData): G5StageClassificationRow[] {
    const { columnHeaders, sectionOneMatrix, sectionTwoMatrix, sectionThreeMatrix, companyStages } = source
    if (!columnHeaders?.length) return []

    const validIndices = getValidColumnIndices(columnHeaders, sectionOneMatrix, sectionTwoMatrix, sectionThreeMatrix)

    return validIndices.map((colIdx, arrIdx) => {
      const debtor = (columnHeaders[colIdx] ?? '').trim()

      const sectionOneChecks: SectionOneCheck[] = SECTION_ONE_LABELS.map((label, rowIdx) => ({
        label,
        value: normalizeSectionOneValue(sectionOneMatrix?.[rowIdx]?.[colIdx]),
      }))

      const sectionTwoChecks: SectionTwoCheck[] = SECTION_TWO_LABELS.map((label, rowIdx) => ({
        label,
        value: normalizeBoolValue(sectionTwoMatrix?.[rowIdx]?.[colIdx]),
      }))

      const sectionThreeChecks: SectionThreeCheck[] = SECTION_THREE_LABELS.map((label, rowIdx) => ({
        label,
        value: normalizeBoolValue(sectionThreeMatrix?.[rowIdx]?.[colIdx]),
      }))

      const row: G5StageClassificationRow = {
        id: crypto.randomUUID(),
        seq: arrIdx + 1,
        debtor: debtor || `债务人${arrIdx + 1}`,
        sectionOneChecks,
        sectionTwoChecks,
        sectionThreeChecks,
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

  /** 智能检测有效列索引 */
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

  /** 标准化(一)区检查值 */
  function normalizeSectionOneValue(raw: string | undefined | null): SectionOneCheckValue {
    const val = (raw ?? '').trim()
    if (val === '是' || val === 'Y' || val === 'Yes' || val === '1' || val === 'true') return '是'
    if (val === '不适用' || val === 'N/A' || val === 'NA' || val === 'n/a') return '不适用'
    return '否'
  }

  /** 标准化(二)(三)区检查值 */
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

  // ─── 行CRUD ───────────────────────────────────────────────────────────────

  /** 创建空行 */
  function createEmptyRow(debtor: string): G5StageClassificationRow {
    return {
      id: crypto.randomUUID(),
      seq: rows.value.length + 1,
      debtor,
      sectionOneChecks: SECTION_ONE_LABELS.map(label => ({ label, value: '否' as SectionOneCheckValue })),
      sectionTwoChecks: SECTION_TWO_LABELS.map(label => ({ label, value: '否' as SectionTwoBoolValue })),
      sectionThreeChecks: SECTION_THREE_LABELS.map(label => ({ label, value: '否' as SectionTwoBoolValue })),
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

  /** 新增债务人（直接传名称或弹 ElMessageBox.prompt） */
  async function addRow(debtor?: string): Promise<void> {
    let name = debtor?.trim()
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入债务人名称',
          '新增债务人',
          { confirmButtonText: '确定', cancelButtonText: '取消' },
        )
        if (!value?.trim()) return
        name = value.trim()
      } catch {
        return
      }
    }
    const row = createEmptyRow(name)
    rows.value.push(row)
  }

  /** 删除行 */
  function removeRow(id: string): void {
    rows.value = rows.value.filter(r => r.id !== id)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    const next = new Set(expandedRowIds.value)
    next.delete(id)
    expandedRowIds.value = next
  }

  // ─── 数据加载 ─────────────────────────────────────────────────────────────

  /** 从已保存行式数据恢复 */
  function loadRows(data: G5StageClassificationRow[]): void {
    rows.value = data.map((r, i) => {
      const row: G5StageClassificationRow = {
        ...r,
        id: r.id || crypto.randomUUID(),
        seq: i + 1,
        sectionOneChecks: r.sectionOneChecks?.length === 13
          ? r.sectionOneChecks
          : SECTION_ONE_LABELS.map((label, idx) => ({
              label,
              value: r.sectionOneChecks?.[idx]?.value ?? '否',
            })),
        sectionTwoChecks: r.sectionTwoChecks?.length === 3
          ? r.sectionTwoChecks
          : SECTION_TWO_LABELS.map((label, idx) => ({
              label,
              value: r.sectionTwoChecks?.[idx]?.value ?? '否',
            })),
        sectionThreeChecks: r.sectionThreeChecks?.length === 8
          ? r.sectionThreeChecks
          : SECTION_THREE_LABELS.map((label, idx) => ({
              label,
              value: r.sectionThreeChecks?.[idx]?.value ?? '否',
            })),
      }
      recalcRow(row)
      return row
    })
  }

  /** 从列式源数据加载 */
  function loadFromColumnar(source: ColumnarSourceData): void {
    rows.value = parseColumnarData(source)
  }

  // ─── 序列化 ───────────────────────────────────────────────────────────────

  function toSaveData() {
    return {
      rows: rows.value,
      summary: summary.value,
      conclusion: conclusion.value,
    }
  }

  // ─── Vue组件适配方法 ──────────────────────────────────────────────────────

  /** 初始化数据（从htmlData或已保存数据） */
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

  /** 更新检查项值 */
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

  /** 更新企业划分阶段 */
  function updateCompanyStage(rowId: string, stage: StageType): void {
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.companyStage = stage
    row.isConsistent = row.companyStage === row.auditStage
  }

  /** 更新审计判断阶段 */
  function updateAuditStage(rowId: string, stage: StageType): void {
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.auditStage = stage
    row.isConsistent = row.companyStage === row.auditStage
  }

  /** 更新差异说明 */
  function updateDiscrepancyNote(rowId: string, note: string): void {
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    row.discrepancyNote = note
  }

  return {
    // State
    rows,
    conclusion,
    expandedRowIds,
    // Computed
    summary,
    // 判定函数
    calcHasSignificantIncrease,
    calcHasLowCreditRisk,
    calcHasCreditImpairment,
    // 行操作
    recalcRow,
    recalcAll,
    addRow,
    removeRow,
    loadRows,
    loadFromColumnar,
    createEmptyRow,
    // 列式解析
    parseColumnarData,
    getValidColumnIndices,
    normalizeSectionOneValue,
    normalizeBoolValue,
    normalizeStage,
    // 展开/折叠
    toggleExpand,
    expandAll,
    collapseAll,
    isExpanded,
    // Vue组件适配
    init,
    updateCheckValue,
    updateCompanyStage,
    updateAuditStage,
    updateDiscrepancyNote,
    // 序列化
    toSaveData,
  }
}

export default useG5StageClassification
