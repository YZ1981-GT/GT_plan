/**
 * useG6SppiTest — G6-8 合同现金流量特征分析（SPPI测试，六section）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 8.1
 * Requirements: 5.1, 5.2, 5.4, 5.5
 *
 * 职责：
 * - SppiTestData / SppiSection / SppiItem 数据模型
 * - 六section管理：本金定义/利息定义/修改时间价值/提前还款条款/合同关联工具/综合判断
 * - SPPI_METHODOLOGY 方法论映射（CAS22/CAS37合同现金流量特征）
 * - 检查项措辞为「合规陈述」：是=满足SPPI、否=不满足SPPI、不适用=本项不适用
 * - 综合结论推导：任一section的item isSPPISatisfied='no' → sectionConclusion='fail'
 *   任一section sectionConclusion='fail' → overallConclusion='fail', hasFailedSection=true
 * - 整体通过前须填合同条款摘要与判断依据（证据完整性闸门）
 * - 初始化六section默认items骨架
 */
import { ref, computed, watch } from 'vue'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

/** SPPI测试单行检查项 */
export interface SppiItem {
  id: string
  seq: number
  checkArea: string                    // 检查区域
  checkItem: string                    // 检查项目
  casRequirement: string               // CAS要求（只读方法论）
  contractTermSummary: string          // 企业合同条款摘要（textarea）
  isSPPISatisfied: 'yes' | 'no' | 'na' | null  // 是否满足SPPI
  judgmentBasis: string                // 判断依据（textarea）
  riskLevel: 'high' | 'medium' | 'low' | null  // 风险等级
  indexRef: string                     // 索引
  remark: string                       // 备注
}

/** SPPI测试section */
export interface SppiSection {
  id: string
  title: string
  items: SppiItem[]
  sectionConclusion: 'pass' | 'fail' | 'na' | null
}

/** 完整SPPI测试数据 */
export interface SppiTestData {
  sections: SppiSection[]
  overallConclusion: 'pass' | 'fail' | null
  hasFailedSection: boolean
}

// ─── 方法论映射（六section CAS引用） ─────────────────────────────────────────

export const SPPI_METHODOLOGY: Record<string, string> = {
  principal: '本金是指金融资产在初始确认时的公允价值。本金金额可能因还款而在整个存续期内变化。',
  interest: '利息包括对货币时间价值、信用风险、流动性风险、管理成本的对价以及利润率。',
  modified_time_value: '如果利率重置与计息期不匹配，需评估合同现金流量差异是否仅代表货币时间价值的对价。',
  prepayment: '如提前偿付金额基本代表未偿付本金及利息（含合理补偿），则仍可满足SPPI。',
  contractual_linked: '优先/次级结构中需评估标的池每项资产是否满足SPPI条件。',
  comprehensive: '结合以上各项分析，整体评估合同现金流量特征是否满足SPPI。',
}

/** Section定义（id, title, methodologyKey） */
export const SECTION_DEFINITIONS: Array<{ id: string; title: string; methodologyKey: string }> = [
  { id: 'principal', title: '(一) 本金定义：初始确认时的公允价值', methodologyKey: 'principal' },
  { id: 'interest', title: '(二) 利息定义：货币时间价值+信用风险+流动性风险+管理成本+利润', methodologyKey: 'interest' },
  { id: 'modified_time_value', title: '(三) 修改时间价值：期限错配/利率重置不匹配', methodologyKey: 'modified_time_value' },
  { id: 'prepayment', title: '(四) 提前还款条款：提前还款/延期权', methodologyKey: 'prepayment' },
  { id: 'contractual_linked', title: '(五) 合同关联工具：优先/次级结构', methodologyKey: 'contractual_linked' },
  { id: 'comprehensive', title: '(六) 综合判断：是否满足SPPI', methodologyKey: 'comprehensive' },
]

// ─── 默认检查项骨架 ──────────────────────────────────────────────────────────

/**
 * 每个section的默认检查项（合规陈述，非事实性是/否问句）。
 * 「是否满足SPPI」列：是=本项满足SPPI；否=本项不满足；不适用=本项与合同无关。
 */
const DEFAULT_SECTION_ITEMS: Record<string, Array<{ checkArea: string; checkItem: string }>> = {
  principal: [
    { checkArea: '本金确认', checkItem: '初始确认时的本金等于实际支付对价（公允价值），无重大非现金对价扭曲' },
    { checkArea: '本金确认', checkItem: '折溢价属正常市场定价，不导致本金定义偏离基本借贷安排' },
    { checkArea: '本金变动', checkItem: '本金金额仅因正常还款而变化，无不与本金/利息相关的调整条款' },
    { checkArea: '本金变动', checkItem: '不存在导致本金非正常增减的或有/杠杆/权益挂钩条款' },
    { checkArea: '本金变动', checkItem: '本金偿还安排明确、可预期，现金流可按本金基础计量' },
  ],
  interest: [
    { checkArea: '货币时间价值', checkItem: '合同利率反映货币时间价值的基本对价' },
    { checkArea: '货币时间价值', checkItem: '利息以未偿付本金金额为基础计算' },
    { checkArea: '信用风险', checkItem: '利率中的信用风险补偿合理且与债务人信用状况匹配' },
    { checkArea: '信用风险', checkItem: '信用风险溢价不引入与基本借贷安排无关的其他风险敞口' },
    { checkArea: '流动性风险', checkItem: '流动性风险对价（如有）属基本借贷安排的合理组成部分' },
    { checkArea: '管理成本', checkItem: '管理成本补偿合理，不构成对非借贷服务的额外对价' },
    { checkArea: '利润率', checkItem: '利润率合理且不含杠杆、权益或商品价格挂钩成分' },
    { checkArea: '综合评估', checkItem: '利息各组成部分均为基本贷款安排的对价，无非SPPI成分' },
  ],
  modified_time_value: [
    { checkArea: '计息期匹配', checkItem: '利率重置频率与计息期匹配，或不存在修改时间价值问题' },
    { checkArea: '计息期匹配', checkItem: '若重置频率与计息期不匹配，合同现金流与基准现金流差异不显著' },
    { checkArea: '基准利率', checkItem: '浮动利率基准为公开市场利率或可观察基准，不引入无关风险' },
    { checkArea: '基准利率', checkItem: '利率上下限(Cap/Floor)（如有）不使合同现金流特征偏离SPPI' },
    { checkArea: '修改评估', checkItem: '修改后的货币时间价值仍代表基本贷款对价' },
    { checkArea: '修改评估', checkItem: '需做基准测试时已执行，且结论支持差异不显著/可忽略' },
    { checkArea: '修改评估', checkItem: '不存在因修改时间价值导致应判定不满足SPPI的情形' },
  ],
  prepayment: [
    { checkArea: '提前偿付', checkItem: '无提前偿付条款，或提前偿付金额基本代表未偿付本金及应计利息（含合理补偿）' },
    { checkArea: '提前偿付', checkItem: '提前偿付补偿金额合理，不引入与基本借贷无关的额外回报' },
    { checkArea: '提前偿付', checkItem: '不存在对贷方不利的负补偿条款（或已评估仍满足SPPI例外）' },
    { checkArea: '提前偿付', checkItem: '提前偿付选择权的行使不导致合同现金流含非本金/利息成分' },
    { checkArea: '延期权', checkItem: '无展期/延期选择权，或延期期间现金流量仍仅为对本金和利息的支付' },
    { checkArea: '延期权', checkItem: '延期条款不含与基本借贷安排无关的对价或风险敞口' },
    { checkArea: '延期权', checkItem: '展期利率重置（如有）仍满足SPPI利息定义' },
  ],
  contractual_linked: [
    { checkArea: '结构评估', checkItem: '不存在优先/次级分层结构，或虽存在但本层级及标的池均满足穿透SPPI条件' },
    { checkArea: '结构评估', checkItem: '标的资产池中每项资产（或充分样本）均满足SPPI' },
    { checkArea: '结构评估', checkItem: '信用增级措施不改变本层级合同现金流量的SPPI特征' },
    { checkArea: '信用风险', checkItem: '本层级信用风险敞口等于或低于标的资产池整体敞口' },
    { checkArea: '信用风险', checkItem: '不存在使现金流量加速或延迟且引入非SPPI特征的触发条件' },
    { checkArea: '穿透分析', checkItem: '穿透至底层资产后，现金流量特征仍满足仅本金和利息' },
  ],
  comprehensive: [
    { checkArea: '综合评估', checkItem: '合同现金流量整体仅为对本金和以未偿付本金为基础的利息的支付' },
    { checkArea: '综合评估', checkItem: '合同中不存在导致不满足SPPI的嵌入衍生、杠杆或权益/商品挂钩条款' },
    { checkArea: '综合评估', checkItem: '各section分析结论一致，共同支持最终SPPI判断' },
    { checkArea: '最终结论', checkItem: '综合判断：本合同/本组合满足SPPI条件' },
    { checkArea: '最终结论', checkItem: '若不满足SPPI，已识别需重分类为FVTPL（或其他恰当分类）的处理路径' },
  ],
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `sppi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 创建单个SppiItem */
function createSppiItem(seq: number, checkArea: string, checkItem: string, casRequirement: string): SppiItem {
  return {
    id: generateId(),
    seq,
    checkArea,
    checkItem,
    casRequirement,
    contractTermSummary: '',
    isSPPISatisfied: null,
    judgmentBasis: '',
    riskLevel: null,
    indexRef: '',
    remark: '',
  }
}

/** 创建一个section含默认items */
function createSection(def: { id: string; title: string; methodologyKey: string }): SppiSection {
  const methodology = SPPI_METHODOLOGY[def.methodologyKey] || ''
  const defaultItems = DEFAULT_SECTION_ITEMS[def.id] || []

  return {
    id: def.id,
    title: def.title,
    items: defaultItems.map((item, idx) =>
      createSppiItem(idx + 1, item.checkArea, item.checkItem, methodology),
    ),
    sectionConclusion: null,
  }
}

/** 初始化六section完整默认骨架 */
function createDefaultSections(): SppiSection[] {
  return SECTION_DEFINITIONS.map(def => createSection(def))
}

// ─── Section结论推导逻辑 ─────────────────────────────────────────────────────

/**
 * 推导单个section的结论
 * - 任一item isSPPISatisfied='no' → 'fail'
 * - 所有item均为'yes'或'na'（且至少有一个'yes'） → 'pass'
 * - 所有item均为'na' → 'na'
 * - 有item未填(null) → null（未完成）
 */
export function deriveSectionConclusion(items: SppiItem[]): 'pass' | 'fail' | 'na' | null {
  if (!items.length) return null

  let hasNo = false
  let hasYes = false
  let hasNull = false

  for (const item of items) {
    if (item.isSPPISatisfied === 'no') hasNo = true
    else if (item.isSPPISatisfied === 'yes') hasYes = true
    else if (item.isSPPISatisfied === null) hasNull = true
    // 'na' 不影响判断
  }

  // 任一"否" → fail
  if (hasNo) return 'fail'
  // 有未填项 → 未完成
  if (hasNull) return null
  // 全为na → na
  if (!hasYes) return 'na'
  // 全部yes/na（且有yes） → pass
  return 'pass'
}

/**
 * 推导综合结论
 * - 任一section sectionConclusion='fail' → 'fail'
 * - 所有section均为'pass'或'na' → 'pass'（但须通过证据完整性闸门）
 * - 有section未完成(null) → null
 * - 证据不完整时不得给出 'pass'（返回 null，由 UI 提示补全）
 */
export function deriveOverallConclusion(
  sections: SppiSection[],
  options?: { requireEvidence?: boolean },
): 'pass' | 'fail' | null {
  if (!sections.length) return null

  let hasFail = false
  let hasNull = false
  let hasPass = false

  for (const section of sections) {
    if (section.sectionConclusion === 'fail') hasFail = true
    else if (section.sectionConclusion === null) hasNull = true
    else if (section.sectionConclusion === 'pass') hasPass = true
    // 'na' 不阻断
  }

  if (hasFail) return 'fail'
  if (hasNull) return null
  // 全部为 na、无任何有效 pass → 不可视为整体通过
  if (!hasPass) return null

  const requireEvidence = options?.requireEvidence !== false
  if (requireEvidence && findEvidenceGaps(sections).length > 0) return null

  return 'pass'
}

/** 已作答（yes/no）但缺少合同摘要或判断依据的检查项 */
export interface SppiEvidenceGap {
  sectionId: string
  sectionTitle: string
  itemId: string
  checkItem: string
  missing: Array<'contractTermSummary' | 'judgmentBasis' | 'indexRef'>
}

export function findEvidenceGaps(sections: SppiSection[]): SppiEvidenceGap[] {
  const gaps: SppiEvidenceGap[] = []
  for (const section of sections) {
    for (const item of section.items) {
      if (item.isSPPISatisfied !== 'yes' && item.isSPPISatisfied !== 'no') continue
      const missing: SppiEvidenceGap['missing'] = []
      if (!item.contractTermSummary?.trim()) missing.push('contractTermSummary')
      if (!item.judgmentBasis?.trim()) missing.push('judgmentBasis')
      // 判定为“否”或高风险时，索引必填以便复核追溯
      if (
        (item.isSPPISatisfied === 'no' || item.riskLevel === 'high') &&
        !item.indexRef?.trim()
      ) {
        missing.push('indexRef')
      }
      if (missing.length) {
        gaps.push({
          sectionId: section.id,
          sectionTitle: section.title,
          itemId: item.id,
          checkItem: item.checkItem,
          missing,
        })
      }
    }
  }
  return gaps
}

/** 供 AI / 审计结论使用的精简失败项摘要 */
export function summarizeFailedItems(sections: SppiSection[]): Array<{
  sectionTitle: string
  checkItem: string
  contractTermSummary: string
  judgmentBasis: string
  riskLevel: string | null
}> {
  const rows: Array<{
    sectionTitle: string
    checkItem: string
    contractTermSummary: string
    judgmentBasis: string
    riskLevel: string | null
  }> = []
  for (const section of sections) {
    for (const item of section.items) {
      if (item.isSPPISatisfied !== 'no') continue
      rows.push({
        sectionTitle: section.title,
        checkItem: item.checkItem,
        contractTermSummary: item.contractTermSummary || '',
        judgmentBasis: item.judgmentBasis || '',
        riskLevel: item.riskLevel,
      })
    }
  }
  return rows
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiTest() {
  const sections = ref<SppiSection[]>(createDefaultSections())
  const overallConclusion = ref<'pass' | 'fail' | null>(null)

  // ─── 计算属性 ────────────────────────────────────────────────────────────

  /** 是否存在失败section（任一section conclusion='fail'） */
  const hasFailedSection = computed(() => {
    return sections.value.some(s => s.sectionConclusion === 'fail')
  })

  /** 获取失败的section列表（用于红色高亮） */
  const failedSections = computed(() => {
    return sections.value.filter(s => s.sectionConclusion === 'fail')
  })

  /** 证据缺口（已作答但缺摘要/依据/索引） */
  const evidenceGaps = computed(() => findEvidenceGaps(sections.value))

  /** 证据是否完整（整体通过的前提之一） */
  const evidenceComplete = computed(() => evidenceGaps.value.length === 0)

  /** 失败检查项摘要（供 AI） */
  const failedItemSummaries = computed(() => summarizeFailedItems(sections.value))

  /** 所有items平铺（用于虚拟滚动80行渲染） */
  const allItems = computed(() => {
    const result: Array<SppiItem & { sectionId: string; sectionTitle: string }> = []
    let globalSeq = 1
    for (const section of sections.value) {
      for (const item of section.items) {
        result.push({
          ...item,
          seq: globalSeq++,
          sectionId: section.id,
          sectionTitle: section.title,
        })
      }
    }
    return result
  })

  /** 总行数 */
  const totalRows = computed(() => allItems.value.length)

  // ─── 自动推导结论 ──────────────────────────────────────────────────────────

  /** 重算所有section结论 + 综合结论 */
  function recalcConclusions(): void {
    for (const section of sections.value) {
      section.sectionConclusion = deriveSectionConclusion(section.items)
    }
    overallConclusion.value = deriveOverallConclusion(sections.value)
  }

  // watch items 变化时自动重算结论（含证据字段，以便闸门生效）
  watch(
    () =>
      sections.value.map(s =>
        s.items.map(i => [
          i.isSPPISatisfied,
          i.contractTermSummary,
          i.judgmentBasis,
          i.indexRef,
          i.riskLevel,
        ]),
      ),
    () => {
      recalcConclusions()
    },
    { deep: true },
  )

  // ─── Item操作 ──────────────────────────────────────────────────────────────

  /** 更新某个item字段 */
  function updateItem(sectionId: string, itemId: string, field: keyof SppiItem, value: any): void {
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    const item = section.items.find(i => i.id === itemId)
    if (!item) return
    ;(item as any)[field] = value
  }

  /** 新增检查项到指定section */
  function addItem(sectionId: string, checkArea?: string, checkItem?: string): void {
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return

    const methodology = SPPI_METHODOLOGY[sectionId] || ''
    const seq = section.items.length + 1
    const newItem = createSppiItem(
      seq,
      checkArea || '',
      checkItem || '',
      methodology,
    )
    section.items.push(newItem)
  }

  /** 删除检查项 */
  function removeItem(sectionId: string, itemId: string): void {
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    section.items = section.items.filter(i => i.id !== itemId)
    // 重排序号
    section.items.forEach((item, idx) => {
      item.seq = idx + 1
    })
  }

  /** 手动设置section结论（覆盖自动推导） */
  function setSectionConclusion(sectionId: string, value: 'pass' | 'fail' | 'na' | null): void {
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    section.sectionConclusion = value
    // 重算综合结论（仍受证据闸门约束）
    overallConclusion.value = deriveOverallConclusion(sections.value)
  }

  /** 手动设置综合结论（仍受证据闸门：证据不全时不可强制 pass） */
  function setOverallConclusion(value: 'pass' | 'fail' | null): void {
    if (value === 'pass' && findEvidenceGaps(sections.value).length > 0) {
      overallConclusion.value = null
      return
    }
    overallConclusion.value = value
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  function loadData(data: SppiTestData | null): void {
    if (!data?.sections?.length) {
      sections.value = createDefaultSections()
      overallConclusion.value = null
      return
    }

    // 加载已有数据，保持section结构完整性
    sections.value = SECTION_DEFINITIONS.map(def => {
      const existingSection = data.sections.find(s => s.id === def.id)
      if (existingSection) {
        return {
          id: def.id,
          title: def.title,
          items: existingSection.items.map((item, idx) => ({
            id: item.id || generateId(),
            seq: idx + 1,
            checkArea: item.checkArea || '',
            checkItem: item.checkItem || '',
            casRequirement: item.casRequirement || SPPI_METHODOLOGY[def.methodologyKey] || '',
            contractTermSummary: item.contractTermSummary || '',
            isSPPISatisfied: item.isSPPISatisfied ?? null,
            judgmentBasis: item.judgmentBasis || '',
            riskLevel: item.riskLevel ?? null,
            indexRef: item.indexRef || '',
            remark: item.remark || '',
          })),
          sectionConclusion: existingSection.sectionConclusion ?? null,
        }
      }
      // section不存在 → 用默认骨架
      return createSection(def)
    })

    overallConclusion.value = data.overallConclusion ?? null
    // 确保结论一致性
    recalcConclusions()
  }

  function toJSON(): SppiTestData {
    return {
      sections: sections.value.map(s => ({
        id: s.id,
        title: s.title,
        items: s.items.map(i => ({ ...i })),
        sectionConclusion: s.sectionConclusion,
      })),
      overallConclusion: overallConclusion.value,
      hasFailedSection: hasFailedSection.value,
    }
  }

  /** 重置为默认骨架 */
  function reset(): void {
    sections.value = createDefaultSections()
    overallConclusion.value = null
  }

  /** 获取section的方法论文本 */
  function getSectionMethodology(sectionId: string): string {
    return SPPI_METHODOLOGY[sectionId] || ''
  }

  /** 获取section定义信息 */
  function getSectionDef(sectionId: string) {
    return SECTION_DEFINITIONS.find(d => d.id === sectionId) || null
  }

  return {
    // State
    sections,
    overallConclusion,
    // Computed
    hasFailedSection,
    failedSections,
    evidenceGaps,
    evidenceComplete,
    failedItemSummaries,
    allItems,
    totalRows,
    // Methods
    recalcConclusions,
    updateItem,
    addItem,
    removeItem,
    setSectionConclusion,
    setOverallConclusion,
    loadData,
    toJSON,
    reset,
    getSectionMethodology,
    getSectionDef,
  }
}

export default useG6SppiTest
