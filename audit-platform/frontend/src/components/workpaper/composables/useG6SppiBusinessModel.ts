/**
 * useG6SppiBusinessModel — G6-7 业务模式分析（三section问卷式）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 7.1
 * Requirements: 4.1, 4.2, 4.3
 */
import { ref, computed, watch } from 'vue'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

/** 单个检查项 */
export interface BusinessModelItem {
  id: string
  seq: number
  checkItem: string
  auditRequirement: string
  managementExplanation: string
  isSatisfied: boolean | null
  auditConclusion: string
  riskLevel: 'high' | 'medium' | 'low' | null
  indexRef: string
  /** 关键检查项：为「否」时推导更倾向 other */
  critical?: boolean
}

/** section结构 */
export interface BusinessModelSection {
  items: BusinessModelItem[]
  sectionConclusion: string
}

export type BusinessModelConclusion = 'hold_collect' | 'hold_and_sell' | 'other' | null

/** 完整业务模式分析数据 */
export interface BusinessModelData {
  section1: BusinessModelSection
  section2: BusinessModelSection
  finalConclusion: BusinessModelConclusion
  finalAnalysis: string
  /** 用户是否手动覆盖了自动推导结论 */
  manualOverride?: boolean
}

type ItemTemplate = {
  checkItem: string
  auditRequirement: string
  critical?: boolean
}

// ─── 默认检查项模板 ─────────────────────────────────────────────────────────

const SECTION1_DEFAULT_ITEMS: ItemTemplate[] = [
  {
    checkItem: '管理金融资产的目标是否为收取合同现金流量',
    auditRequirement: '了解企业管理层对该金融资产组合的管理目标，是否以收取合同现金流量为主要目标',
    critical: true,
  },
  {
    checkItem: '日常出售金融资产的频率和金额',
    auditRequirement: '检查本期及前期是否存在出售行为，出售频率和金额是否影响业务模式判断',
  },
  {
    checkItem: '业绩评价方式是否基于公允价值',
    auditRequirement: '了解管理层对该金融资产组合的业绩评价方式，是基于合同现金流量还是公允价值',
    critical: true,
  },
  {
    checkItem: '管理层薪酬是否与公允价值变动挂钩',
    auditRequirement: '了解管理层薪酬机制是否基于所管理资产的公允价值变动',
  },
  {
    checkItem: '资产组合的风险管理策略',
    auditRequirement: '了解企业对该组合的风险管理方法，是否侧重信用风险管理而非交易性管理',
  },
]

const SECTION2_DEFAULT_ITEMS: ItemTemplate[] = [
  {
    checkItem: '本期出售的频率和金额',
    auditRequirement: '获取本期出售金融资产的明细，分析出售频率和金额占比',
  },
  {
    checkItem: '出售原因是否表明业务模式变更',
    auditRequirement: '了解出售原因，是否为信用恶化、临近到期、偶发性出售等可接受原因',
    critical: true,
  },
  {
    checkItem: '出售时间距到期日的远近',
    auditRequirement: '分析出售发生时距资产到期日的时间，临近到期的出售通常不影响业务模式',
  },
  {
    checkItem: '未来出售的预期和计划',
    auditRequirement: '了解管理层对未来期间是否有出售金融资产的计划或预期',
  },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `bm-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createItemFromTemplate(t: ItemTemplate, seq: number): BusinessModelItem {
  return {
    id: generateId(),
    seq,
    checkItem: t.checkItem,
    auditRequirement: t.auditRequirement,
    managementExplanation: '',
    isSatisfied: null,
    auditConclusion: '',
    riskLevel: null,
    indexRef: '',
    critical: Boolean(t.critical),
  }
}

function createSectionItems(templates: ItemTemplate[]): BusinessModelItem[] {
  return templates.map((t, i) => createItemFromTemplate(t, i + 1))
}

function createDefaultSection(templates: ItemTemplate[]): BusinessModelSection {
  return {
    items: createSectionItems(templates),
    sectionConclusion: '',
  }
}

function normalizeItem(item: Partial<BusinessModelItem>, i: number): BusinessModelItem {
  return {
    id: item.id || generateId(),
    seq: item.seq || i + 1,
    checkItem: item.checkItem || '',
    auditRequirement: item.auditRequirement || '',
    managementExplanation: item.managementExplanation || '',
    isSatisfied: item.isSatisfied ?? null,
    auditConclusion: item.auditConclusion || '',
    riskLevel: item.riskLevel || null,
    indexRef: item.indexRef || '',
    critical: Boolean(item.critical),
  }
}

function resequence(items: BusinessModelItem[]): void {
  items.forEach((item, i) => {
    item.seq = i + 1
  })
}

function defaultRiskForUnsatisfied(critical: boolean): 'high' | 'medium' {
  return critical ? 'high' : 'medium'
}

/** 推断默认关键标记（兼容旧数据无 critical 字段） */
export function inferCriticalFlag(checkItem: string): boolean {
  const t = checkItem || ''
  return (
    t.includes('管理目标') ||
    t.includes('收取合同现金流量') ||
    t.includes('业绩评价') ||
    t.includes('出售原因')
  )
}

// ─── 综合判断逻辑 ───────────────────────────────────────────────────────────

/**
 * 根据两个section的回答推导业务模式最终结论（含关键项加权）
 *
 * - 全部满足 → hold_collect
 * - 任一关键项为「否」→ other
 * - 两区均存在非关键「否」→ other
 * - 其余完整回答 → hold_and_sell
 * - 存在未回答 → null
 */
export function deriveBusinessModelConclusion(
  section1: BusinessModelSection,
  section2: BusinessModelSection,
): BusinessModelConclusion {
  const allItems = [...section1.items, ...section2.items]
  if (!allItems.length) return null
  if (allItems.some(item => item.isSatisfied === null)) return null

  const allSatisfied = allItems.every(item => item.isSatisfied === true)
  if (allSatisfied) return 'hold_collect'

  const criticalFailed = allItems.some(
    item => (item.critical || inferCriticalFlag(item.checkItem)) && item.isSatisfied === false,
  )
  if (criticalFailed) return 'other'

  const s1AnyUnsatisfied = section1.items.some(item => item.isSatisfied === false)
  const s2AnyUnsatisfied = section2.items.some(item => item.isSatisfied === false)
  if (s1AnyUnsatisfied && s2AnyUnsatisfied) return 'other'

  return 'hold_and_sell'
}

export type SppiOverallConclusion = 'pass' | 'fail' | null

export interface G67G68ConsistencyResult {
  level: 'ok' | 'info' | 'warning' | null
  message: string
  expectedClassification: string | null
}

export function evaluateG67G68Consistency(
  businessModel: BusinessModelConclusion,
  sppiOverall: SppiOverallConclusion,
): G67G68ConsistencyResult {
  if (!businessModel || !sppiOverall) {
    return { level: null, message: '', expectedClassification: null }
  }

  if (sppiOverall === 'fail') {
    return {
      level: 'warning',
      message:
        'G6-8 SPPI 测试未通过：即使业务模式为持有收取/兼有，通常仍应分类为 FVTPL，与「其他债权投资」(FVOCI) 科目定位可能不一致，请复核分类或调整入账科目。',
      expectedClassification: 'FVTPL',
    }
  }

  if (businessModel === 'other') {
    return {
      level: 'warning',
      message:
        '业务模式为「其他」：即使 SPPI 通过，通常仍应分类为 FVTPL，与「其他债权投资」(FVOCI) 科目定位可能不一致。',
      expectedClassification: 'FVTPL',
    }
  }

  if (businessModel === 'hold_and_sell') {
    return {
      level: 'ok',
      message: '业务模式为兼有且 SPPI 通过：符合以公允价值计量且其变动计入其他综合收益（FVOCI-Debt）的分类条件。',
      expectedClassification: 'FVOCI-Debt',
    }
  }

  return {
    level: 'info',
    message:
      '业务模式为持有收取且 SPPI 通过：可分类为摊余成本（AC）或以公允价值计量且其变动计入其他综合收益（FVOCI-Debt，视管理层选择/科目定位）。当前底稿科目为「其他债权投资」时，请确认是否存在 FVOCI 选择权或应调整至债权投资(AC)。',
    expectedClassification: 'AC 或 FVOCI-Debt',
  }
}

export interface BusinessModelAiSummaryItem {
  section: string
  checkItem: string
  isSatisfied: boolean | null
  riskLevel: string | null
  critical: boolean
  auditConclusion: string
  managementExplanation: string
  indexRef: string
}

/** 供 AI 的检查项摘要（优先不满足/高风险，最多 12 条） */
export function buildBusinessModelAiSummary(data: BusinessModelData): {
  unsatisfiedOrHighRisk: BusinessModelAiSummaryItem[]
  section1Conclusion: string
  section2Conclusion: string
  finalConclusion: BusinessModelConclusion
} {
  const collect = (sectionKey: string, section: BusinessModelSection) =>
    section.items
      .filter(
        i =>
          i.isSatisfied === false ||
          i.riskLevel === 'high' ||
          (i.critical && i.isSatisfied !== true),
      )
      .map(i => ({
        section: sectionKey,
        checkItem: i.checkItem,
        isSatisfied: i.isSatisfied,
        riskLevel: i.riskLevel,
        critical: Boolean(i.critical || inferCriticalFlag(i.checkItem)),
        auditConclusion: (i.auditConclusion || '').slice(0, 200),
        managementExplanation: (i.managementExplanation || '').slice(0, 200),
        indexRef: (i.indexRef || '').slice(0, 80),
      }))

  const items = [
    ...collect('(一)业务模式确定', data.section1),
    ...collect('(二)出售情况分析', data.section2),
  ].slice(0, 12)

  return {
    unsatisfiedOrHighRisk: items,
    section1Conclusion: data.section1.sectionConclusion || '',
    section2Conclusion: data.section2.sectionConclusion || '',
    finalConclusion: data.finalConclusion,
  }
}

export const BM_CONCLUSION_LABELS: Record<string, string> = {
  hold_collect: '持有以收取合同现金流量',
  hold_and_sell: '既以收取合同现金流量又以出售为目标',
  other: '其他（以交易为目的等）',
}

export interface G6ClassificationInstrumentInput {
  id: string
  name: string
  overallConclusion: SppiOverallConclusion
}

/** 组合层摘要 + 可选项目级矩阵（业务模式复用组合结论） */
export function buildG6ClassificationSummary(opts: {
  businessModel: BusinessModelConclusion
  sppiOverall: SppiOverallConclusion
  instruments?: G6ClassificationInstrumentInput[]
  source: string
}): {
  businessModel: BusinessModelConclusion
  businessModelLabel: string | null
  sppiOverall: SppiOverallConclusion
  expectedClassification: string | null
  level: 'ok' | 'info' | 'warning' | null
  message: string
  accountConflict: boolean
  updatedAt: string
  source: string
  instruments?: Array<{
    instrumentId: string
    instrumentName: string
    businessModel: BusinessModelConclusion
    businessModelLabel: string | null
    sppiOverall: SppiOverallConclusion
    expectedClassification: string | null
    level: 'ok' | 'info' | 'warning' | null
    message: string
    accountConflict: boolean
  }>
} {
  const check = evaluateG67G68Consistency(opts.businessModel, opts.sppiOverall)
  const businessModelLabel = opts.businessModel
    ? (BM_CONCLUSION_LABELS[opts.businessModel] || null)
    : null
  const instruments = (opts.instruments || []).map((inst) => {
    const itemCheck = evaluateG67G68Consistency(opts.businessModel, inst.overallConclusion)
    return {
      instrumentId: inst.id,
      instrumentName: inst.name,
      businessModel: opts.businessModel,
      businessModelLabel,
      sppiOverall: inst.overallConclusion,
      expectedClassification: itemCheck.expectedClassification,
      level: itemCheck.level,
      message: itemCheck.message,
      accountConflict:
        itemCheck.level === 'warning' && itemCheck.expectedClassification === 'FVTPL',
    }
  })
  return {
    businessModel: opts.businessModel,
    businessModelLabel,
    sppiOverall: opts.sppiOverall,
    expectedClassification: check.expectedClassification,
    level: check.level,
    message: check.message,
    accountConflict: check.level === 'warning' && check.expectedClassification === 'FVTPL',
    updatedAt: new Date().toISOString(),
    source: opts.source,
    ...(instruments.length ? { instruments } : {}),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiBusinessModel() {
  const section1 = ref<BusinessModelSection>(createDefaultSection(SECTION1_DEFAULT_ITEMS))
  const section2 = ref<BusinessModelSection>(createDefaultSection(SECTION2_DEFAULT_ITEMS))
  const finalConclusion = ref<BusinessModelConclusion>(null)
  const finalAnalysis = ref('')
  const manualOverride = ref(false)

  const derivedConclusion = computed(() =>
    deriveBusinessModelConclusion(section1.value, section2.value),
  )

  watch(
    [
      () => section1.value.items.map(i => [i.isSatisfied, i.critical]),
      () => section2.value.items.map(i => [i.isSatisfied, i.critical]),
    ],
    () => {
      if (manualOverride.value) return
      const derived = deriveBusinessModelConclusion(section1.value, section2.value)
      if (derived !== null) {
        finalConclusion.value = derived
      }
    },
    { deep: true },
  )

  const section1CompletionRate = computed(() => {
    const total = section1.value.items.length
    if (total === 0) return 0
    const answered = section1.value.items.filter(i => i.isSatisfied !== null).length
    return Math.round((answered / total) * 100)
  })

  const section2CompletionRate = computed(() => {
    const total = section2.value.items.length
    if (total === 0) return 0
    const answered = section2.value.items.filter(i => i.isSatisfied !== null).length
    return Math.round((answered / total) * 100)
  })

  const unansweredCount = computed(() => {
    const all = [...section1.value.items, ...section2.value.items]
    return all.filter(i => i.isSatisfied === null).length
  })

  const isComplete = computed(() => unansweredCount.value === 0 && (
    section1.value.items.length + section2.value.items.length > 0
  ))

  const highRiskCount = computed(() => {
    const s1High = section1.value.items.filter(i => i.riskLevel === 'high').length
    const s2High = section2.value.items.filter(i => i.riskLevel === 'high').length
    return s1High + s2High
  })

  const overrideDiffersFromDerived = computed(() => {
    return (
      manualOverride.value &&
      derivedConclusion.value !== null &&
      finalConclusion.value !== null &&
      finalConclusion.value !== derivedConclusion.value
    )
  })

  const CONCLUSION_LABELS: Record<string, { label: string; type: 'success' | 'primary' | 'warning' | 'info' }> = {
    hold_collect: { label: '以收取合同现金流量为目标', type: 'success' },
    hold_and_sell: { label: '既以收取合同现金流量又以出售为目标', type: 'primary' },
    other: { label: '其他（以交易为目的等）', type: 'warning' },
  }

  const conclusionLabel = computed(() => {
    if (!finalConclusion.value) {
      return { label: '请完成所有检查项', type: 'info' as const }
    }
    return CONCLUSION_LABELS[finalConclusion.value] || { label: '未知', type: 'info' as const }
  })

  function getSection(sectionKey: 'section1' | 'section2'): BusinessModelSection {
    return sectionKey === 'section1' ? section1.value : section2.value
  }

  function updateManagementExplanation(sectionKey: 'section1' | 'section2', itemId: string, value: string): void {
    const item = getSection(sectionKey).items.find(i => i.id === itemId)
    if (item) item.managementExplanation = value
  }

  function updateIsSatisfied(sectionKey: 'section1' | 'section2', itemId: string, value: boolean | null): void {
    const item = getSection(sectionKey).items.find(i => i.id === itemId)
    if (!item) return
    item.isSatisfied = value
    // 选「否」且尚未评级时给默认风险建议
    if (value === false && item.riskLevel === null) {
      item.riskLevel = defaultRiskForUnsatisfied(
        Boolean(item.critical || inferCriticalFlag(item.checkItem)),
      )
    }
  }

  function updateAuditConclusion(sectionKey: 'section1' | 'section2', itemId: string, value: string): void {
    const item = getSection(sectionKey).items.find(i => i.id === itemId)
    if (item) item.auditConclusion = value
  }

  function updateRiskLevel(
    sectionKey: 'section1' | 'section2',
    itemId: string,
    value: 'high' | 'medium' | 'low' | null,
  ): void {
    const item = getSection(sectionKey).items.find(i => i.id === itemId)
    if (item) item.riskLevel = value
  }

  function updateIndexRef(sectionKey: 'section1' | 'section2', itemId: string, value: string): void {
    const item = getSection(sectionKey).items.find(i => i.id === itemId)
    if (item) item.indexRef = value
  }

  function updateSectionConclusion(sectionKey: 'section1' | 'section2', value: string): void {
    getSection(sectionKey).sectionConclusion = value
  }

  function toggleCritical(sectionKey: 'section1' | 'section2', itemId: string, value: boolean): void {
    const item = getSection(sectionKey).items.find(i => i.id === itemId)
    if (item) item.critical = value
  }

  function addItem(sectionKey: 'section1' | 'section2', checkItem = '新增检查项', auditRequirement = ''): void {
    const section = getSection(sectionKey)
    section.items.push(
      createItemFromTemplate({ checkItem, auditRequirement, critical: false }, section.items.length + 1),
    )
  }

  function removeItem(sectionKey: 'section1' | 'section2', itemId: string): boolean {
    const section = getSection(sectionKey)
    if (section.items.length <= 1) return false
    const idx = section.items.findIndex(i => i.id === itemId)
    if (idx < 0) return false
    section.items.splice(idx, 1)
    resequence(section.items)
    return true
  }

  function setFinalConclusion(value: BusinessModelConclusion): void {
    finalConclusion.value = value
    if (value === null) {
      manualOverride.value = false
      const derived = deriveBusinessModelConclusion(section1.value, section2.value)
      if (derived !== null) finalConclusion.value = derived
    } else {
      manualOverride.value = true
    }
  }

  function clearManualOverride(): void {
    manualOverride.value = false
    finalConclusion.value = deriveBusinessModelConclusion(section1.value, section2.value)
  }

  function setFinalAnalysis(value: string): void {
    finalAnalysis.value = value
  }

  /** 将出售规模草稿写入匹配「出售…频率/金额」且说明为空的检查项 */
  function applySaleDraft(draft: string, force = false): number {
    if (!draft) return 0
    let applied = 0
    for (const section of [section1.value, section2.value]) {
      for (const item of section.items) {
        const name = item.checkItem || ''
        const isSaleFreq =
          (name.includes('出售') && (name.includes('频率') || name.includes('金额'))) ||
          name.includes('日常出售')
        if (!isSaleFreq) continue
        if (!force && item.managementExplanation.trim()) continue
        item.managementExplanation = draft
        applied++
      }
    }
    return applied
  }

  function loadData(data: BusinessModelData | null): void {
    if (!data) {
      section1.value = createDefaultSection(SECTION1_DEFAULT_ITEMS)
      section2.value = createDefaultSection(SECTION2_DEFAULT_ITEMS)
      finalConclusion.value = null
      finalAnalysis.value = ''
      manualOverride.value = false
      return
    }

    if (data.section1?.items?.length) {
      section1.value = {
        items: data.section1.items.map((item, i) => {
          const n = normalizeItem(item, i)
          if (item.critical === undefined) n.critical = inferCriticalFlag(n.checkItem)
          return n
        }),
        sectionConclusion: data.section1.sectionConclusion || '',
      }
    } else {
      section1.value = createDefaultSection(SECTION1_DEFAULT_ITEMS)
    }

    if (data.section2?.items?.length) {
      section2.value = {
        items: data.section2.items.map((item, i) => {
          const n = normalizeItem(item, i)
          if (item.critical === undefined) n.critical = inferCriticalFlag(n.checkItem)
          return n
        }),
        sectionConclusion: data.section2.sectionConclusion || '',
      }
    } else {
      section2.value = createDefaultSection(SECTION2_DEFAULT_ITEMS)
    }

    finalAnalysis.value = data.finalAnalysis || ''
    const derived = deriveBusinessModelConclusion(section1.value, section2.value)
    const savedConclusion = data.finalConclusion ?? null
    manualOverride.value = Boolean(
      data.manualOverride ||
      (savedConclusion !== null && derived !== null && savedConclusion !== derived),
    )
    finalConclusion.value = savedConclusion ?? derived
  }

  function toJSON(): BusinessModelData {
    return {
      section1: {
        items: section1.value.items.map(i => ({ ...i })),
        sectionConclusion: section1.value.sectionConclusion,
      },
      section2: {
        items: section2.value.items.map(i => ({ ...i })),
        sectionConclusion: section2.value.sectionConclusion,
      },
      finalConclusion: finalConclusion.value,
      finalAnalysis: finalAnalysis.value,
      manualOverride: manualOverride.value,
    }
  }

  return {
    section1,
    section2,
    finalConclusion,
    finalAnalysis,
    manualOverride,
    derivedConclusion,
    section1CompletionRate,
    section2CompletionRate,
    unansweredCount,
    isComplete,
    highRiskCount,
    overrideDiffersFromDerived,
    conclusionLabel,
    updateManagementExplanation,
    updateIsSatisfied,
    updateAuditConclusion,
    updateRiskLevel,
    updateIndexRef,
    updateSectionConclusion,
    toggleCritical,
    addItem,
    removeItem,
    setFinalConclusion,
    clearManualOverride,
    setFinalAnalysis,
    applySaleDraft,
    loadData,
    toJSON,
  }
}

export default useG6SppiBusinessModel
