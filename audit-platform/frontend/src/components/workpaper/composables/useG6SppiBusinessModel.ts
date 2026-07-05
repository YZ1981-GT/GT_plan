/**
 * useG6SppiBusinessModel — G6-7 业务模式分析（三section问卷式）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 7.1
 * Requirements: 4.1, 4.2, 4.3
 *
 * 职责：
 * - BusinessModelData/BusinessModelSection/BusinessModelItem数据模型
 * - 三section数据管理：(一)业务模式确定 / (二)出售情况分析 / (三)综合判断
 * - 综合判断逻辑：根据section1+section2的isSatisfied推导finalConclusion
 *   - 全部满足 → 'hold_collect'（持有以收取合同现金流量）
 *   - 存在出售但可接受 → 'hold_and_sell'（兼有）
 *   - 其他 → 'other'
 * - 字段更新方法（managementExplanation, isSatisfied, auditConclusion, riskLevel, indexRef）
 */
import { ref, computed, watch } from 'vue'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

/** 单个检查项 */
export interface BusinessModelItem {
  id: string
  seq: number
  checkItem: string                    // 检查项目
  auditRequirement: string             // 审计要求
  managementExplanation: string        // 管理层说明(textarea)
  isSatisfied: boolean | null          // 是否满足(下拉)
  auditConclusion: string              // 审计结论(textarea)
  riskLevel: 'high' | 'medium' | 'low' | null  // 风险评级
  indexRef: string                     // 索引号
}

/** section结构 */
export interface BusinessModelSection {
  items: BusinessModelItem[]
  sectionConclusion: string
}

/** 完整业务模式分析数据 */
export interface BusinessModelData {
  section1: BusinessModelSection       // (一) 业务模式确定
  section2: BusinessModelSection       // (二) 出售情况分析
  finalConclusion: 'hold_collect' | 'hold_and_sell' | 'other' | null
  finalAnalysis: string
}

// ─── 默认检查项模板 ─────────────────────────────────────────────────────────

/** (一) 业务模式确定 — 默认检查项 */
const SECTION1_DEFAULT_ITEMS: Array<{ checkItem: string; auditRequirement: string }> = [
  {
    checkItem: '管理金融资产的目标是否为收取合同现金流量',
    auditRequirement: '了解企业管理层对该金融资产组合的管理目标，是否以收取合同现金流量为主要目标',
  },
  {
    checkItem: '日常出售金融资产的频率和金额',
    auditRequirement: '检查本期及前期是否存在出售行为，出售频率和金额是否影响业务模式判断',
  },
  {
    checkItem: '业绩评价方式是否基于公允价值',
    auditRequirement: '了解管理层对该金融资产组合的业绩评价方式，是基于合同现金流量还是公允价值',
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

/** (二) 出售情况分析 — 默认检查项 */
const SECTION2_DEFAULT_ITEMS: Array<{ checkItem: string; auditRequirement: string }> = [
  {
    checkItem: '本期出售的频率和金额',
    auditRequirement: '获取本期出售金融资产的明细，分析出售频率和金额占比',
  },
  {
    checkItem: '出售原因是否表明业务模式变更',
    auditRequirement: '了解出售原因，是否为信用恶化、临近到期、偶发性出售等可接受原因',
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

function createSectionItems(
  templates: Array<{ checkItem: string; auditRequirement: string }>,
): BusinessModelItem[] {
  return templates.map((t, i) => ({
    id: generateId(),
    seq: i + 1,
    checkItem: t.checkItem,
    auditRequirement: t.auditRequirement,
    managementExplanation: '',
    isSatisfied: null,
    auditConclusion: '',
    riskLevel: null,
    indexRef: '',
  }))
}

function createDefaultSection(
  templates: Array<{ checkItem: string; auditRequirement: string }>,
): BusinessModelSection {
  return {
    items: createSectionItems(templates),
    sectionConclusion: '',
  }
}

// ─── 综合判断逻辑 ───────────────────────────────────────────────────────────

/**
 * 根据两个section的回答推导业务模式最终结论
 *
 * 规则：
 * - section1全部满足 + section2无不可接受出售 → 'hold_collect'（持有以收取合同现金流量）
 * - section1存在不满足或section2表明有出售且可接受 → 'hold_and_sell'（既收取又出售）
 * - section1明确不以收取为目标 或 section2表明出售为主 → 'other'（其他）
 * - 存在未回答项 → null（未完成）
 */
export function deriveBusinessModelConclusion(
  section1: BusinessModelSection,
  section2: BusinessModelSection,
): 'hold_collect' | 'hold_and_sell' | 'other' | null {
  // 检查是否所有项都已回答
  const s1Answered = section1.items.every(item => item.isSatisfied !== null)
  const s2Answered = section2.items.every(item => item.isSatisfied !== null)

  // 任何一个section未完整回答，返回null
  if (!s1Answered || !s2Answered) return null

  // section1: 业务模式确定
  const s1AllSatisfied = section1.items.every(item => item.isSatisfied === true)
  const s1AnyUnsatisfied = section1.items.some(item => item.isSatisfied === false)

  // section2: 出售情况分析
  const s2AllSatisfied = section2.items.every(item => item.isSatisfied === true)
  const s2AnyUnsatisfied = section2.items.some(item => item.isSatisfied === false)

  // 判定逻辑：
  // 1. section1全满足(以收取为目标) + section2全满足(出售不影响) → 持有收取
  if (s1AllSatisfied && s2AllSatisfied) {
    return 'hold_collect'
  }

  // 2. section1有不满足（非纯收取目标）+ section2有不满足（出售有影响）→ 其他
  if (s1AnyUnsatisfied && s2AnyUnsatisfied) {
    return 'other'
  }

  // 3. 介于两者之间 → 兼有（既收取合同现金流量又出售）
  return 'hold_and_sell'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiBusinessModel() {
  // ─── 响应式数据 ──────────────────────────────────────────────────────────

  const section1 = ref<BusinessModelSection>(createDefaultSection(SECTION1_DEFAULT_ITEMS))
  const section2 = ref<BusinessModelSection>(createDefaultSection(SECTION2_DEFAULT_ITEMS))
  const finalConclusion = ref<'hold_collect' | 'hold_and_sell' | 'other' | null>(null)
  const finalAnalysis = ref('')

  // ─── 综合判断自动推导 ────────────────────────────────────────────────────

  /** 自动判断是否已设置手动结论，如未设置则自动推导 */
  const derivedConclusion = computed(() => {
    return deriveBusinessModelConclusion(section1.value, section2.value)
  })

  // watch两个section变化，自动推导结论（仅当用户未手动设置时）
  watch(
    [
      () => section1.value.items.map(i => i.isSatisfied),
      () => section2.value.items.map(i => i.isSatisfied),
    ],
    () => {
      // 自动推导结论
      const derived = deriveBusinessModelConclusion(section1.value, section2.value)
      // 仅在用户未手动覆盖时自动更新
      if (derived !== null) {
        finalConclusion.value = derived
      }
    },
    { deep: true },
  )

  // ─── section1 状态计算 ──────────────────────────────────────────────────

  /** section1完成度 */
  const section1CompletionRate = computed(() => {
    const total = section1.value.items.length
    if (total === 0) return 0
    const answered = section1.value.items.filter(i => i.isSatisfied !== null).length
    return Math.round((answered / total) * 100)
  })

  /** section2完成度 */
  const section2CompletionRate = computed(() => {
    const total = section2.value.items.length
    if (total === 0) return 0
    const answered = section2.value.items.filter(i => i.isSatisfied !== null).length
    return Math.round((answered / total) * 100)
  })

  /** 是否所有section都已完成 */
  const isComplete = computed(() => {
    return section1CompletionRate.value === 100 && section2CompletionRate.value === 100
  })

  /** 高风险项数量 */
  const highRiskCount = computed(() => {
    const s1High = section1.value.items.filter(i => i.riskLevel === 'high').length
    const s2High = section2.value.items.filter(i => i.riskLevel === 'high').length
    return s1High + s2High
  })

  // ─── 结论标签映射 ──────────────────────────────────────────────────────

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

  // ─── 字段更新方法 ──────────────────────────────────────────────────────

  /** 更新section中item的管理层说明 */
  function updateManagementExplanation(sectionKey: 'section1' | 'section2', itemId: string, value: string): void {
    const section = sectionKey === 'section1' ? section1.value : section2.value
    const item = section.items.find(i => i.id === itemId)
    if (item) {
      item.managementExplanation = value
    }
  }

  /** 更新section中item的是否满足 */
  function updateIsSatisfied(sectionKey: 'section1' | 'section2', itemId: string, value: boolean | null): void {
    const section = sectionKey === 'section1' ? section1.value : section2.value
    const item = section.items.find(i => i.id === itemId)
    if (item) {
      item.isSatisfied = value
    }
  }

  /** 更新section中item的审计结论 */
  function updateAuditConclusion(sectionKey: 'section1' | 'section2', itemId: string, value: string): void {
    const section = sectionKey === 'section1' ? section1.value : section2.value
    const item = section.items.find(i => i.id === itemId)
    if (item) {
      item.auditConclusion = value
    }
  }

  /** 更新section中item的风险等级 */
  function updateRiskLevel(sectionKey: 'section1' | 'section2', itemId: string, value: 'high' | 'medium' | 'low' | null): void {
    const section = sectionKey === 'section1' ? section1.value : section2.value
    const item = section.items.find(i => i.id === itemId)
    if (item) {
      item.riskLevel = value
    }
  }

  /** 更新section中item的索引号 */
  function updateIndexRef(sectionKey: 'section1' | 'section2', itemId: string, value: string): void {
    const section = sectionKey === 'section1' ? section1.value : section2.value
    const item = section.items.find(i => i.id === itemId)
    if (item) {
      item.indexRef = value
    }
  }

  /** 更新section结论 */
  function updateSectionConclusion(sectionKey: 'section1' | 'section2', value: string): void {
    const section = sectionKey === 'section1' ? section1.value : section2.value
    section.sectionConclusion = value
  }

  /** 设置最终结论（手动覆盖） */
  function setFinalConclusion(value: 'hold_collect' | 'hold_and_sell' | 'other' | null): void {
    finalConclusion.value = value
  }

  /** 设置综合分析说明 */
  function setFinalAnalysis(value: string): void {
    finalAnalysis.value = value
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  function loadData(data: BusinessModelData | null): void {
    if (!data) {
      section1.value = createDefaultSection(SECTION1_DEFAULT_ITEMS)
      section2.value = createDefaultSection(SECTION2_DEFAULT_ITEMS)
      finalConclusion.value = null
      finalAnalysis.value = ''
      return
    }

    // 加载section1
    if (data.section1?.items?.length) {
      section1.value = {
        items: data.section1.items.map((item, i) => ({
          id: item.id || generateId(),
          seq: item.seq || i + 1,
          checkItem: item.checkItem || '',
          auditRequirement: item.auditRequirement || '',
          managementExplanation: item.managementExplanation || '',
          isSatisfied: item.isSatisfied ?? null,
          auditConclusion: item.auditConclusion || '',
          riskLevel: item.riskLevel || null,
          indexRef: item.indexRef || '',
        })),
        sectionConclusion: data.section1.sectionConclusion || '',
      }
    } else {
      section1.value = createDefaultSection(SECTION1_DEFAULT_ITEMS)
    }

    // 加载section2
    if (data.section2?.items?.length) {
      section2.value = {
        items: data.section2.items.map((item, i) => ({
          id: item.id || generateId(),
          seq: item.seq || i + 1,
          checkItem: item.checkItem || '',
          auditRequirement: item.auditRequirement || '',
          managementExplanation: item.managementExplanation || '',
          isSatisfied: item.isSatisfied ?? null,
          auditConclusion: item.auditConclusion || '',
          riskLevel: item.riskLevel || null,
          indexRef: item.indexRef || '',
        })),
        sectionConclusion: data.section2.sectionConclusion || '',
      }
    } else {
      section2.value = createDefaultSection(SECTION2_DEFAULT_ITEMS)
    }

    finalConclusion.value = data.finalConclusion ?? null
    finalAnalysis.value = data.finalAnalysis || ''
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
    }
  }

  return {
    // State
    section1,
    section2,
    finalConclusion,
    finalAnalysis,
    // Computed
    derivedConclusion,
    section1CompletionRate,
    section2CompletionRate,
    isComplete,
    highRiskCount,
    conclusionLabel,
    // Methods
    updateManagementExplanation,
    updateIsSatisfied,
    updateAuditConclusion,
    updateRiskLevel,
    updateIndexRef,
    updateSectionConclusion,
    setFinalConclusion,
    setFinalAnalysis,
    loadData,
    toJSON,
  }
}

export default useG6SppiBusinessModel
