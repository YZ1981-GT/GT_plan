/**
 * useG6SppiTest — G6-8 合同现金流量特征分析（SPPI测试，80行六section）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 8.1
 * Requirements: 5.1, 5.2, 5.4, 5.5
 *
 * 职责：
 * - SppiTestData / SppiSection / SppiItem 数据模型
 * - 六section管理：本金定义/利息定义/修改时间价值/提前还款条款/合同关联工具/综合判断
 * - SPPI_METHODOLOGY 方法论映射（CAS22/CAS37合同现金流量特征）
 * - 综合结论推导：任一section的item isSPPISatisfied='no' → sectionConclusion='fail'
 *   任一section sectionConclusion='fail' → overallConclusion='fail', hasFailedSection=true
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

/** 每个section的默认检查项 */
const DEFAULT_SECTION_ITEMS: Record<string, Array<{ checkArea: string; checkItem: string }>> = {
  principal: [
    { checkArea: '本金确认', checkItem: '初始确认时公允价值是否等于实际支付对价' },
    { checkArea: '本金确认', checkItem: '是否存在重大折溢价导致本金与面值差异显著' },
    { checkArea: '本金变动', checkItem: '本金金额是否仅因正常还款而变化' },
    { checkArea: '本金变动', checkItem: '是否存在非正常还款导致本金变化的条款' },
    { checkArea: '本金变动', checkItem: '本金偿还安排是否明确且可预期' },
  ],
  interest: [
    { checkArea: '货币时间价值', checkItem: '利率是否反映货币时间价值的基本对价' },
    { checkArea: '货币时间价值', checkItem: '利息计算基础是否为未偿付本金金额' },
    { checkArea: '信用风险', checkItem: '利率中是否包含对信用风险的合理补偿' },
    { checkArea: '信用风险', checkItem: '信用风险溢价是否与债务人信用状况匹配' },
    { checkArea: '流动性风险', checkItem: '是否包含对流动性风险的合理对价' },
    { checkArea: '管理成本', checkItem: '利率是否包含对贷款管理成本的补偿' },
    { checkArea: '利润率', checkItem: '利润率是否合理且不含杠杆成分' },
    { checkArea: '综合评估', checkItem: '利息各组成部分是否均为基本贷款安排的对价' },
  ],
  modified_time_value: [
    { checkArea: '计息期匹配', checkItem: '利率重置频率是否与计息期匹配' },
    { checkArea: '计息期匹配', checkItem: '重置频率与计息期不匹配时差异是否显著' },
    { checkArea: '基准利率', checkItem: '浮动利率基准是否为公开市场利率' },
    { checkArea: '基准利率', checkItem: '利率上下限(Cap/Floor)是否影响SPPI特征' },
    { checkArea: '修改评估', checkItem: '修改后的货币时间价值是否仍代表基本贷款对价' },
    { checkArea: '修改评估', checkItem: '是否需要进行基准测试(benchmark test)' },
    { checkArea: '修改评估', checkItem: '基准测试结果是否表明差异不显著' },
  ],
  prepayment: [
    { checkArea: '提前偿付', checkItem: '是否包含提前偿付条款' },
    { checkArea: '提前偿付', checkItem: '提前偿付金额是否基本代表未偿付本金及利息' },
    { checkArea: '提前偿付', checkItem: '提前偿付补偿金额是否合理' },
    { checkArea: '提前偿付', checkItem: '提前偿付是否可能导致负补偿（对贷方不利）' },
    { checkArea: '延期权', checkItem: '是否包含展期/延期选择权' },
    { checkArea: '延期权', checkItem: '延期期间现金流量是否仍满足SPPI' },
    { checkArea: '延期权', checkItem: '延期条款是否包含非基本贷款安排的对价' },
  ],
  contractual_linked: [
    { checkArea: '结构评估', checkItem: '是否存在优先/次级分层结构' },
    { checkArea: '结构评估', checkItem: '标的资产池中每项资产是否均满足SPPI' },
    { checkArea: '结构评估', checkItem: '信用增级措施是否影响合同现金流量特征' },
    { checkArea: '信用风险', checkItem: '本层级信用风险敞口是否等于或低于标的池' },
    { checkArea: '信用风险', checkItem: '是否存在使现金流量加速或延迟的触发条件' },
    { checkArea: '穿透分析', checkItem: '穿透至底层资产后现金流量特征是否满足SPPI' },
  ],
  comprehensive: [
    { checkArea: '综合评估', checkItem: '合同现金流量是否仅为对本金和利息的支付' },
    { checkArea: '综合评估', checkItem: '是否存在导致合同现金流量不满足SPPI的条款' },
    { checkArea: '综合评估', checkItem: '各section分析结论是否一致支持最终结论' },
    { checkArea: '最终结论', checkItem: 'SPPI测试最终结论：满足/不满足' },
    { checkArea: '最终结论', checkItem: '如不满足SPPI，是否需要重新分类金融资产' },
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
 * - 所有section均为'pass'或'na' → 'pass'
 * - 有section未完成(null) → null
 */
export function deriveOverallConclusion(sections: SppiSection[]): 'pass' | 'fail' | null {
  if (!sections.length) return null

  let hasFail = false
  let hasNull = false

  for (const section of sections) {
    if (section.sectionConclusion === 'fail') hasFail = true
    else if (section.sectionConclusion === null) hasNull = true
    // 'pass' 和 'na' 不阻断
  }

  if (hasFail) return 'fail'
  if (hasNull) return null
  return 'pass'
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

  // watch items 变化时自动重算结论
  watch(
    () => sections.value.map(s => s.items.map(i => i.isSPPISatisfied)),
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
    // 重算综合结论
    overallConclusion.value = deriveOverallConclusion(sections.value)
  }

  /** 手动设置综合结论 */
  function setOverallConclusion(value: 'pass' | 'fail' | null): void {
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
