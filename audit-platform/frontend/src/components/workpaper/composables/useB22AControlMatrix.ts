/**
 * useB22AControlMatrix — B22A 检查项CRUD/结论评估/Element_Score自动计算/缺陷追踪/IT依赖/续审继承/业务规则警告
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Task: 2.2
 *
 * 职责：
 * - 检查项 CRUD（per tab / per IT subPanel）
 * - Conclusion 设置含即时保存 + 缺陷标记
 * - Understanding_Method 多选存储（remark 逗号分隔）
 * - Element_Score 自动计算（有效/部分有效/无效规则）
 * - 手动覆盖 Element_Score（需理由）
 * - IT_Dependency 依赖程度控制
 * - ITGC 结论传递 + 警告
 * - 缺陷清单自动收集
 * - 汇总统计 + Tab完成状态
 * - 续审继承（priorYearData / markNoChange）
 * - 业务规则警告（控制环境薄弱 / IT控制薄弱）
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB22AFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type TabNumber = 1 | 2 | 3 | 4 | 5
export type Conclusion = '设计有效' | '设计无效' | '已实施' | '未实施' | '不适用'
export type UnderstandingMethod = '询问' | '观察' | '检查文件' | '穿行测试'
export type ElementScore = '有效' | '部分有效' | '无效'
export type ITDependency = '高' | '中' | '低'
export type ITSubPanel = 'env' | 'itgc' | 'app' | 'change' | 'access' | 'sod'
export type TabStatus = 'empty' | 'partial' | 'complete'

export interface CheckItem {
  index: number
  controlPoint: string
  description: string
  methods: UnderstandingMethod[]
  conclusion: Conclusion | null
  reference: string
  isPreset: boolean
  isDeficiency: boolean
  priorYearConclusion: Conclusion | null
  noChangeConfirmed: boolean
  noChangeConfirmer: string | null
  noChangeDate: string | null
}

export interface ElementStat {
  total: number
  effective: number
  deficient: number
  notApplicable: number
  incomplete: number
}

export interface DeficiencyItem {
  tab: TabNumber
  subPanel: ITSubPanel | null
  index: number
  controlPoint: string
  deficiencyType: '设计无效' | '未实施'
  elementName: string
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Constants (exported for tests and components) ───────────────────────────

export const CONCLUSIONS: Conclusion[] = ['设计有效', '设计无效', '已实施', '未实施', '不适用']

export const UNDERSTANDING_METHODS: UnderstandingMethod[] = ['询问', '观察', '检查文件', '穿行测试']

export const SCORE_COLOR_MAP: Record<ElementScore | '不适用', { bg: string; text: string }> = {
  '有效':     { bg: '#D1FAE5', text: '#059669' },
  '部分有效': { bg: '#FEF3C7', text: '#D97706' },
  '无效':     { bg: '#FEE2E2', text: '#DC2626' },
  '不适用':   { bg: '#F3F4F6', text: '#6B7280' },
}

export const IT_SUB_PANELS: { key: ITSubPanel; label: string }[] = [
  { key: 'env', label: 'IT环境了解' },
  { key: 'itgc', label: 'IT通用控制(ITGC)' },
  { key: 'app', label: 'IT应用控制' },
  { key: 'change', label: '变更管理' },
  { key: 'access', label: '访问安全' },
  { key: 'sod', label: '职责分离' },
]

export const COSO_TABS: { tab: TabNumber; label: string; code: string }[] = [
  { tab: 1, label: '控制环境', code: 'T1' },
  { tab: 2, label: '风险评估过程', code: 'T2' },
  { tab: 3, label: '信息系统与沟通', code: 'T3' },
  { tab: 4, label: '控制活动', code: 'T4' },
  { tab: 5, label: '监督', code: 'T5' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Generate item_id for regular check items */
export function generateItemId(
  tab: TabNumber,
  index: number,
  field: 'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange',
  subPanel?: ITSubPanel
): string {
  if (subPanel) {
    return `B22A-T${tab}-IT-${subPanel}-${index}-${field}`
  }
  return `B22A-T${tab}-item-${index}-${field}`
}

/** Generate count item_id */
function countItemId(tab: TabNumber, subPanel?: ITSubPanel): string {
  if (subPanel) {
    return `B22A-T${tab}-IT-${subPanel}-count`
  }
  return `B22A-T${tab}-count`
}

/** Generate score item_id */
function scoreItemId(tab: TabNumber): string {
  return `B22A-T${tab}-score`
}

/** Compute auto element score from check items */
export function computeAutoScore(items: CheckItem[]): ElementScore {
  const applicable = items.filter(i => i.conclusion && i.conclusion !== '不适用')
  if (applicable.length === 0) return '有效'

  const deficient = applicable.filter(
    i => i.conclusion === '设计无效' || i.conclusion === '未实施'
  )

  if (deficient.length === 0) return '有效'
  if (deficient.length / applicable.length <= 0.2) return '部分有效'
  return '无效'
}

/** Compute tab status from check items */
export function computeTabStatus(items: CheckItem[]): TabStatus {
  if (items.length === 0) return 'empty'
  const withConclusion = items.filter(i => i.conclusion !== null)
  if (withConclusion.length === 0) return 'empty'
  if (withConclusion.length === items.length) return 'complete'
  return 'partial'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22AControlMatrix(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveImmediate: SaveFn
) {
  const priorYearData = ref<Map<string, ChecklistResponse>>(new Map())
  const itDependency = ref<ITDependency>('中')
  const overallConclusion = ref<ElementScore | null>(null)

  // ─── Internal helpers ──────────────────────────────────────────────────

  function getResponseValue(itemId: string): ChecklistResponse | undefined {
    return allResponses.value.get(itemId)
  }

  function getCount(tab: TabNumber, subPanel?: ITSubPanel): number {
    const item = getResponseValue(countItemId(tab, subPanel))
    const n = parseInt(item?.remark || '0', 10)
    return isNaN(n) ? 0 : n
  }

  function buildCheckItem(tab: TabNumber, index: number, subPanel?: ITSubPanel): CheckItem {
    const pointItem = getResponseValue(generateItemId(tab, index, 'point', subPanel))
    const descItem = getResponseValue(generateItemId(tab, index, 'desc', subPanel))
    const methodItem = getResponseValue(generateItemId(tab, index, 'method', subPanel))
    const conclusionItem = getResponseValue(generateItemId(tab, index, 'conclusion', subPanel))
    const refItem = getResponseValue(generateItemId(tab, index, 'ref', subPanel))
    const nochangeItem = getResponseValue(generateItemId(tab, index, 'nochange', subPanel))

    const conclusion = (conclusionItem?.conclusion as Conclusion | null) || null
    const methods: UnderstandingMethod[] = methodItem?.remark
      ? (methodItem.remark.split(',').filter(m => UNDERSTANDING_METHODS.includes(m as UnderstandingMethod)) as UnderstandingMethod[])
      : []

    // Prior year conclusion
    const priorItemId = generateItemId(tab, index, 'conclusion', subPanel)
    const priorItem = priorYearData.value.get(priorItemId)
    const priorYearConclusion = (priorItem?.conclusion as Conclusion | null) || null

    return {
      index,
      controlPoint: pointItem?.remark || '',
      description: descItem?.remark || '',
      methods,
      conclusion,
      reference: refItem?.remark || '',
      isPreset: false, // preset detection handled by component layer
      isDeficiency: conclusion === '设计无效' || conclusion === '未实施',
      priorYearConclusion,
      noChangeConfirmed: nochangeItem?.conclusion === 'Y',
      noChangeConfirmer: nochangeItem?.remark || null,
      noChangeDate: nochangeItem?.wp_ref || null,
    }
  }

  // ─── Check Items CRUD ──────────────────────────────────────────────────

  function getCheckItems(tab: TabNumber, subPanel?: ITSubPanel): CheckItem[] {
    const count = getCount(tab, subPanel)
    const items: CheckItem[] = []
    for (let i = 1; i <= count; i++) {
      items.push(buildCheckItem(tab, i, subPanel))
    }
    return items
  }

  function addCheckItem(tab: TabNumber, subPanel?: ITSubPanel): void {
    const currentCount = getCount(tab, subPanel)
    const newCount = currentCount + 1
    const countId = countItemId(tab, subPanel)

    allResponses.value.set(countId, {
      item_id: countId,
      conclusion: null,
      remark: String(newCount),
      wp_ref: null,
    })

    saveImmediate([{ item_id: countId, conclusion: null, remark: String(newCount), wp_ref: null }])
  }

  function removeCheckItem(tab: TabNumber, index: number, subPanel?: ITSubPanel): void {
    const currentCount = getCount(tab, subPanel)
    if (index < 1 || index > currentCount) return

    // Shift items down: move index+1..count into index..count-1
    const itemsToSave: ChecklistItem[] = []
    const fields: Array<'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange'> = ['point', 'desc', 'method', 'conclusion', 'ref', 'nochange']

    for (let i = index; i < currentCount; i++) {
      for (const field of fields) {
        const srcId = generateItemId(tab, i + 1, field, subPanel)
        const dstId = generateItemId(tab, i, field, subPanel)
        const srcItem = getResponseValue(srcId)
        const newItem: ChecklistItem = {
          item_id: dstId,
          conclusion: srcItem?.conclusion ?? null,
          remark: srcItem?.remark ?? null,
          wp_ref: srcItem?.wp_ref ?? null,
        }
        allResponses.value.set(dstId, newItem)
        itemsToSave.push(newItem)
      }
    }

    // Clear last row
    for (const field of fields) {
      const lastId = generateItemId(tab, currentCount, field, subPanel)
      allResponses.value.delete(lastId)
      itemsToSave.push({ item_id: lastId, conclusion: null, remark: null, wp_ref: null })
    }

    // Update count
    const newCount = currentCount - 1
    const countId = countItemId(tab, subPanel)
    allResponses.value.set(countId, {
      item_id: countId,
      conclusion: null,
      remark: String(newCount),
      wp_ref: null,
    })
    itemsToSave.push({ item_id: countId, conclusion: null, remark: String(newCount), wp_ref: null })

    saveImmediate(itemsToSave)
  }

  // ─── Conclusion ────────────────────────────────────────────────────────

  function setConclusion(tab: TabNumber, index: number, conclusion: Conclusion, subPanel?: ITSubPanel): void {
    const itemId = generateItemId(tab, index, 'conclusion', subPanel)
    const item: ChecklistItem = {
      item_id: itemId,
      conclusion,
      remark: null,
      wp_ref: null,
    }
    allResponses.value.set(itemId, item)
    saveImmediate([item])
  }

  // ─── Understanding Method ──────────────────────────────────────────────

  function setUnderstandingMethod(tab: TabNumber, index: number, methods: UnderstandingMethod[], subPanel?: ITSubPanel): void {
    const itemId = generateItemId(tab, index, 'method', subPanel)
    const item: ChecklistItem = {
      item_id: itemId,
      conclusion: null,
      remark: methods.join(','),
      wp_ref: null,
    }
    allResponses.value.set(itemId, item)
    saveImmediate([item])
  }

  // ─── Element Score ─────────────────────────────────────────────────────

  function computeElementScore(tab: TabNumber): ElementScore {
    const items = getCheckItems(tab)
    return computeAutoScore(items)
  }

  function overrideElementScore(tab: TabNumber, score: ElementScore, reason: string): void {
    if (!reason.trim()) return // require reason

    const scoreId = scoreItemId(tab)
    const overrideId = `B22A-T${tab}-score-override`

    const scoreItem: ChecklistItem = {
      item_id: scoreId,
      conclusion: score,
      remark: null,
      wp_ref: null,
    }
    const overrideItem: ChecklistItem = {
      item_id: overrideId,
      conclusion: 'Y',
      remark: reason.trim(),
      wp_ref: null,
    }

    allResponses.value.set(scoreId, scoreItem)
    allResponses.value.set(overrideId, overrideItem)
    saveImmediate([scoreItem, overrideItem])
  }

  function isScoreOverridden(tab: TabNumber): boolean {
    const overrideId = `B22A-T${tab}-score-override`
    const item = getResponseValue(overrideId)
    return item?.conclusion === 'Y'
  }

  function getEffectiveScore(tab: TabNumber): ElementScore | null {
    const scoreId = scoreItemId(tab)
    const item = getResponseValue(scoreId)
    if (item?.conclusion) return item.conclusion as ElementScore
    // Auto-compute
    const items = getCheckItems(tab)
    if (items.length === 0) return null
    return computeAutoScore(items)
  }

  // ─── IT Dependency ─────────────────────────────────────────────────────

  function initITDependency(): void {
    const item = getResponseValue('B22A-T4-IT-dependency')
    if (item?.conclusion) {
      itDependency.value = item.conclusion as ITDependency
    }
  }

  function setITDependency(level: ITDependency): void {
    itDependency.value = level
    const item: ChecklistItem = {
      item_id: 'B22A-T4-IT-dependency',
      conclusion: level,
      remark: null,
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  // ─── ITGC Conclusion ──────────────────────────────────────────────────

  const itgcConclusion: ComputedRef<ElementScore | null> = computed(() => {
    const item = getResponseValue('B22A-T4-IT-itgc-score')
    if (item?.conclusion) return item.conclusion as ElementScore
    // Auto-compute from itgc check items
    const items = getCheckItems(4, 'itgc')
    if (items.length === 0) return null
    return computeAutoScore(items)
  })

  const isITGCInvalid: ComputedRef<boolean> = computed(() => {
    return itgcConclusion.value === '无效'
  })

  // ─── Deficiency List ───────────────────────────────────────────────────

  const deficiencyList: ComputedRef<DeficiencyItem[]> = computed(() => {
    const deficiencies: DeficiencyItem[] = []

    for (const cosoTab of COSO_TABS) {
      const tab = cosoTab.tab
      const items = getCheckItems(tab)
      for (const item of items) {
        if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
          deficiencies.push({
            tab,
            subPanel: null,
            index: item.index,
            controlPoint: item.controlPoint,
            deficiencyType: item.conclusion as '设计无效' | '未实施',
            elementName: cosoTab.label,
          })
        }
      }

      // IT sub-panels (Tab 4 only)
      if (tab === 4) {
        for (const panel of IT_SUB_PANELS) {
          const itItems = getCheckItems(4, panel.key)
          for (const item of itItems) {
            if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
              deficiencies.push({
                tab: 4,
                subPanel: panel.key,
                index: item.index,
                controlPoint: item.controlPoint,
                deficiencyType: item.conclusion as '设计无效' | '未实施',
                elementName: `${cosoTab.label} - ${panel.label}`,
              })
            }
          }
        }
      }
    }

    return deficiencies
  })

  // ─── Element Stats ─────────────────────────────────────────────────────

  const elementStats: ComputedRef<Record<TabNumber, ElementStat>> = computed(() => {
    const stats = {} as Record<TabNumber, ElementStat>

    for (const cosoTab of COSO_TABS) {
      const tab = cosoTab.tab
      const items = getCheckItems(tab)

      let effective = 0
      let deficient = 0
      let notApplicable = 0
      let incomplete = 0

      for (const item of items) {
        if (item.conclusion === null) {
          incomplete++
        } else if (item.conclusion === '不适用') {
          notApplicable++
        } else if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
          deficient++
        } else {
          effective++
        }
      }

      stats[tab] = {
        total: items.length,
        effective,
        deficient,
        notApplicable,
        incomplete,
      }
    }

    return stats
  })

  // ─── Overall Conclusion ────────────────────────────────────────────────

  function initOverallConclusion(): void {
    const item = getResponseValue('B22A-SUM-overall')
    if (item?.conclusion) {
      overallConclusion.value = item.conclusion as ElementScore
    }
  }

  // ─── Tab Status ────────────────────────────────────────────────────────

  function tabStatus(tab: TabNumber): TabStatus {
    const items = getCheckItems(tab)
    return computeTabStatus(items)
  }

  // ─── Completed Element Count ───────────────────────────────────────────

  const completedElementCount: ComputedRef<number> = computed(() => {
    let count = 0
    for (const cosoTab of COSO_TABS) {
      const score = getEffectiveScore(cosoTab.tab)
      if (score !== null) count++
    }
    return count
  })

  // ─── Prior Year: markNoChange ──────────────────────────────────────────

  function markNoChange(tab: TabNumber, index: number, confirmer: string, subPanel?: ITSubPanel): void {
    const today = new Date()
    const dateStr = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-')

    const itemId = generateItemId(tab, index, 'nochange', subPanel)
    const item: ChecklistItem = {
      item_id: itemId,
      conclusion: 'Y',
      remark: confirmer,
      wp_ref: dateStr,
    }
    allResponses.value.set(itemId, item)

    // Also carry forward prior year conclusion if available
    const conclusionId = generateItemId(tab, index, 'conclusion', subPanel)
    const priorConclusionItem = priorYearData.value.get(conclusionId)
    const itemsToSave: ChecklistItem[] = [item]

    if (priorConclusionItem?.conclusion && !getResponseValue(conclusionId)?.conclusion) {
      const carryItem: ChecklistItem = {
        item_id: conclusionId,
        conclusion: priorConclusionItem.conclusion,
        remark: null,
        wp_ref: null,
      }
      allResponses.value.set(conclusionId, carryItem)
      itemsToSave.push(carryItem)
    }

    saveImmediate(itemsToSave)
  }

  // ─── Business Rule Warnings ────────────────────────────────────────────

  const controlEnvWeakWarning: ComputedRef<boolean> = computed(() => {
    const tab1Score = getEffectiveScore(1)
    if (tab1Score !== '无效' && tab1Score !== '部分有效') return false

    // Check if critical items (management integrity / governance independence) are deficient
    const items = getCheckItems(1)
    const hasCriticalDeficiency = items.some(
      item => item.conclusion === '设计无效' &&
        (item.controlPoint.includes('诚信') || item.controlPoint.includes('独立性') || item.controlPoint.includes('治理'))
    )
    return hasCriticalDeficiency
  })

  const itControlWeakWarning: ComputedRef<boolean> = computed(() => {
    return itDependency.value === '高' && itgcConclusion.value === '无效'
  })

  // ─── Initialization ────────────────────────────────────────────────────

  function initialize(): void {
    initITDependency()
    initOverallConclusion()
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // Check items CRUD
    getCheckItems,
    addCheckItem,
    removeCheckItem,
    setConclusion,
    setUnderstandingMethod,
    // Element Score
    computeElementScore,
    overrideElementScore,
    isScoreOverridden,
    getEffectiveScore,
    // IT dependency
    itDependency,
    setITDependency,
    itgcConclusion,
    isITGCInvalid,
    // Deficiency
    deficiencyList,
    // Stats
    elementStats,
    overallConclusion,
    completedElementCount,
    // Tab status
    tabStatus,
    // Prior year
    priorYearData,
    markNoChange,
    // Business warnings
    controlEnvWeakWarning,
    itControlWeakWarning,
    // Init
    initialize,
  }
}

export default useB22AControlMatrix
