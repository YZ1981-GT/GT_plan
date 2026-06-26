/**
 * useB23ProcessControl — B23 业务流程与控制了解表 主 composable
 *
 * Spec: .kiro/specs/b23-process-control/
 * Task: 2.2
 *
 * 职责：
 * - 8 流程卡片管理（展开/收起/适用性）
 * - 控制点 CRUD（per process）
 * - 穿行测试记录管理
 * - Process_Conclusion 自动建议（30% 阈值算法）
 * - 仪表盘统计（dashboardStats）
 * - Entity_Level_Context（B22A 上下文接收）
 * - Linkage_Panel 联动信息
 * - EventBus 事件发布
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse, ProcessNumber } from './useB23FormData'

// ─── Constants (exported for testing) ────────────────────────────────────────

/** 8 标准流程配置 */
export const STANDARD_PROCESSES: readonly { num: ProcessNumber; name: string; code: string; targetCycle: string }[] = [
  { num: 1, name: '采购与付款循环', code: 'P1', targetCycle: 'DA' },
  { num: 2, name: '销售与收款循环', code: 'P2', targetCycle: 'EA' },
  { num: 3, name: '资金管理循环', code: 'P3', targetCycle: 'FA' },
  { num: 4, name: '生产与存货循环', code: 'P4', targetCycle: 'GA' },
  { num: 5, name: '薪酬与人力循环', code: 'P5', targetCycle: 'HA' },
  { num: 6, name: '固定资产循环', code: 'P6', targetCycle: 'IA' },
  { num: 7, name: '投资循环', code: 'P7', targetCycle: 'JA' },
  { num: 8, name: '其他流程', code: 'P8', targetCycle: 'KA' },
]

/** 流程结论→颜色映射 */
export const PROCESS_CONCLUSION_COLOR_MAP: Record<string, { color: string; bg: string; label: string }> = {
  '设计有效且已实施':     { color: '#52c41a', bg: '#f6ffed', label: '有效' },
  '设计有效但未有效实施': { color: '#faad14', bg: '#fffbe6', label: '部分有效' },
  '设计无效':            { color: '#ff4d4f', bg: '#fff2f0', label: '无效' },
  '不适用':              { color: '#bfbfbf', bg: '#fafafa', label: '不适用' },
  '待测试':              { color: '#1890ff', bg: '#e6f7ff', label: '待测试' },
}

/** 流程结论→B50 控制风险影响 */
export const CONCLUSION_TO_B50_IMPACT: Record<string, string> = {
  '设计有效且已实施':     '控制风险=低',
  '设计有效但未有效实施': '控制风险=中',
  '设计无效':            '控制风险=高',
  '不适用':              '不影响控制风险评估',
}

// ─── Types ───────────────────────────────────────────────────────────────────

/** 流程结论 */
export type ProcessConclusion = '设计有效且已实施' | '设计有效但未有效实施' | '设计无效' | '不适用'

/** 穿行测试结论（控制点级） */
export type WalkthroughConclusion = '控制有效运行' | '控制未有效运行' | '未执行穿行' | '不适用'

/** 了解方法（多选） */
export type UnderstandingMethod = '询问' | '观察' | '检查文件' | '穿行测试' | '重新执行'

/** 控制频率 */
export type ControlFrequency = '每笔' | '每日' | '每周' | '每月' | '每季' | '每年' | '不定期'

/** 控制点字段 */
export type ControlPointField = 'objective' | 'description' | 'frequency' | 'executor' | 'methods' | 'conclusion' | 'remark'

/** 穿行测试字段 */
export type WalkthroughField = 'sample' | 'path' | 'finding' | 'reference'

/** 控制点 */
export interface ControlPoint {
  index: number
  objective: string
  description: string
  frequency: ControlFrequency | null
  executor: string
  methods: UnderstandingMethod[]
  conclusion: WalkthroughConclusion | null
  remark: string
  isPreset: boolean
}

/** 穿行测试记录（单笔样本） */
export interface WalkthroughRecord {
  sampleIndex: number
  sample: string
  path: string
  finding: string
  reference: string
}

/** 穿行测试摘要 */
export interface WalkthroughSummary {
  testedCount: number
  totalCount: number
  completionRate: number
}

/** 流程卡片 */
export interface ProcessCard {
  num: ProcessNumber
  name: string
  applicable: boolean
  conclusion: ProcessConclusion | null
  suggestedConclusion: ProcessConclusion | null
  conclusionOverridden: boolean
  overrideReason: string
  controlPoints: ControlPoint[]
  walkthroughComplete: boolean
  completionRatio: string
}

/** 状态仪表盘统计 */
export interface DashboardStats {
  completionDistribution: {
    completed: number
    inProgress: number
    notStarted: number
    notApplicable: number
  }
  effectivenessDistribution: {
    effective: number
    partiallyEffective: number
    ineffective: number
    notApplicable: number
  }
  pendingWalkthroughCount: number
}

/** B22A 实体层面上下文（只读） */
export interface EntityLevelContext {
  elementScores: Record<number, string | null>
  overallConclusion: string | null
  completed: boolean
}

/** 联动信息 */
export interface LinkageInfo {
  processNum: ProcessNumber
  processName: string
  conclusion: ProcessConclusion | null
  b50Impact: string
  targetCycle: string
  targetCycleName: string
  needsExtendedProcedures: boolean
}

/** EventBus: control:conclusion-changed 载荷（来自 B22A） */
export interface ControlConclusionPayload {
  elementScores: Record<number, string | null>
  itDependency: string
  itgcConclusion: string | null
  overallConclusion: string | null
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Pure Functions (exported for testing) ───────────────────────────────────

/**
 * 自动建议流程级结论（30% 阈值算法）
 * - 排除 conclusion=null 和"不适用"后：
 *   (a) 全部为"控制有效运行" → "设计有效且已实施"
 *   (b) 存在"控制未有效运行"且占比≤30% → "设计有效但未有效实施"
 *   (c) 占比>30% → "设计无效"
 *   (d) 无已评估控制点 → null
 */
export function suggestProcessConclusion(controlPoints: ControlPoint[]): ProcessConclusion | null {
  const evaluated = controlPoints.filter(
    cp => cp.conclusion !== null && cp.conclusion !== '不适用'
  )
  if (evaluated.length === 0) return null

  const ineffective = evaluated.filter(cp => cp.conclusion === '控制未有效运行')
  if (ineffective.length === 0) {
    return '设计有效且已实施'
  }

  const ineffectiveRatio = ineffective.length / evaluated.length
  if (ineffectiveRatio <= 0.3) {
    return '设计有效但未有效实施'
  }
  return '设计无效'
}

/**
 * 生成 item_id
 * - 流程适用性: B23-P{n}-applicability
 * - 控制点字段: B23-P{n}-ctrl-{m}-{field}
 * - 穿行测试: B23-P{n}-wt-{m}-{s}-{field}
 * - 控制点数量: B23-P{n}-ctrl-count
 * - 穿行样本数量: B23-P{n}-wt-{m}-count
 * - 流程结论: B23-P{n}-process-conclusion
 * - 手动覆盖标记: B23-P{n}-conclusion-override
 */
export function generateItemId(
  processNum: ProcessNumber,
  type: 'applicability' | 'ctrl' | 'wt' | 'ctrl-count' | 'wt-count' | 'process-conclusion' | 'conclusion-override',
  ctrlIndex?: number,
  sampleIndex?: number,
  field?: string
): string {
  const prefix = `B23-P${processNum}`
  switch (type) {
    case 'applicability':
      return `${prefix}-applicability`
    case 'ctrl':
      return `${prefix}-ctrl-${ctrlIndex}-${field}`
    case 'wt':
      return `${prefix}-wt-${ctrlIndex}-${sampleIndex}-${field}`
    case 'ctrl-count':
      return `${prefix}-ctrl-count`
    case 'wt-count':
      return `${prefix}-wt-${ctrlIndex}-count`
    case 'process-conclusion':
      return `${prefix}-process-conclusion`
    case 'conclusion-override':
      return `${prefix}-conclusion-override`
  }
}

// ─── Main Composable ─────────────────────────────────────────────────────────

export function useB23ProcessControl(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveImmediate: SaveFn
) {
  // ─── Expand/Collapse Management ──────────────────────────────────────────

  const expandedProcesses = ref<Set<ProcessNumber>>(new Set([1, 2, 3, 4, 5, 6, 7, 8]))

  function toggleProcess(num: ProcessNumber): void {
    const s = new Set(expandedProcesses.value)
    if (s.has(num)) s.delete(num)
    else s.add(num)
    expandedProcesses.value = s
  }

  function expandAll(): void {
    expandedProcesses.value = new Set([1, 2, 3, 4, 5, 6, 7, 8])
  }

  function collapseAll(): void {
    expandedProcesses.value = new Set()
  }

  // ─── Helper: read/write response fields ──────────────────────────────────

  function getResponseValue(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }

  function setResponseLocal(itemId: string, conclusion: string | null, remark: string | null = null, wpRef: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark, wp_ref: wpRef }
    allResponses.value.set(itemId, item)
    return item
  }

  // ─── Applicability ───────────────────────────────────────────────────────

  function getApplicability(num: ProcessNumber): ComputedRef<boolean> {
    return computed(() => {
      const id = generateItemId(num, 'applicability')
      const r = getResponseValue(id)
      return r.conclusion !== 'N'
    })
  }

  function setApplicability(num: ProcessNumber, applicable: boolean): void {
    const applicabilityId = generateItemId(num, 'applicability')
    const conclusionId = generateItemId(num, 'process-conclusion')
    const overrideId = generateItemId(num, 'conclusion-override')

    const items: ChecklistItem[] = []

    if (!applicable) {
      // Mark not applicable → auto-set conclusion to "不适用"
      items.push(setResponseLocal(applicabilityId, 'N'))
      items.push(setResponseLocal(conclusionId, '不适用'))
      items.push(setResponseLocal(overrideId, null, null))
      // Collapse the card
      const s = new Set(expandedProcesses.value)
      s.delete(num)
      expandedProcesses.value = s
    } else {
      // Restore applicable → clear auto conclusion
      items.push(setResponseLocal(applicabilityId, 'Y'))
      items.push(setResponseLocal(conclusionId, null))
      items.push(setResponseLocal(overrideId, null, null))
      // Expand the card
      const s = new Set(expandedProcesses.value)
      s.add(num)
      expandedProcesses.value = s
    }

    saveImmediate(items)
  }

  // ─── Control Points ──────────────────────────────────────────────────────

  function getControlPointCount(num: ProcessNumber): number {
    const id = generateItemId(num, 'ctrl-count')
    const r = getResponseValue(id)
    const count = parseInt(r.remark || '0', 10)
    return isNaN(count) ? 0 : count
  }

  function getControlPoints(num: ProcessNumber): ComputedRef<ControlPoint[]> {
    return computed(() => {
      const count = getControlPointCount(num)
      const points: ControlPoint[] = []
      for (let m = 1; m <= count; m++) {
        points.push(readControlPoint(num, m))
      }
      return points
    })
  }

  function readControlPoint(num: ProcessNumber, m: number): ControlPoint {
    const objective = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'objective')).remark || ''
    const description = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'description')).remark || ''
    const frequencyVal = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'frequency')).conclusion
    const executor = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'executor')).remark || ''
    const methodsRaw = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'methods')).remark || ''
    const conclusion = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'conclusion')).conclusion as WalkthroughConclusion | null
    const remark = getResponseValue(generateItemId(num, 'ctrl', m, undefined, 'remark')).remark || ''

    const methods: UnderstandingMethod[] = methodsRaw
      ? (methodsRaw.split(',').filter(Boolean) as UnderstandingMethod[])
      : []

    return {
      index: m,
      objective,
      description,
      frequency: frequencyVal as ControlFrequency | null,
      executor,
      methods,
      conclusion,
      remark,
      isPreset: m <= 3, // First 3 are preset by convention
    }
  }

  function addControlPoint(num: ProcessNumber): void {
    const currentCount = getControlPointCount(num)
    if (currentCount >= 20) return // Max 20 per process

    const newCount = currentCount + 1
    const countId = generateItemId(num, 'ctrl-count')
    const items: ChecklistItem[] = [
      setResponseLocal(countId, null, String(newCount)),
    ]
    saveImmediate(items)
  }

  function removeControlPoint(num: ProcessNumber, index: number): void {
    const currentCount = getControlPointCount(num)
    if (index < 1 || index > currentCount) return

    // Shift all items after the removed index down by 1
    const items: ChecklistItem[] = []
    const fields: string[] = ['objective', 'description', 'frequency', 'executor', 'methods', 'conclusion', 'remark']

    for (let m = index; m < currentCount; m++) {
      // Copy from m+1 to m
      for (const field of fields) {
        const sourceId = generateItemId(num, 'ctrl', m + 1, undefined, field)
        const targetId = generateItemId(num, 'ctrl', m, undefined, field)
        const source = getResponseValue(sourceId)
        items.push(setResponseLocal(targetId, source.conclusion, source.remark, source.wp_ref))
      }
      // Also shift walkthrough records
      const wtCountId = generateItemId(num, 'wt-count', m + 1)
      const wtCount = parseInt(getResponseValue(wtCountId).remark || '0', 10) || 0
      const wtTargetCountId = generateItemId(num, 'wt-count', m)
      items.push(setResponseLocal(wtTargetCountId, null, String(wtCount)))

      for (let s = 1; s <= wtCount; s++) {
        const wtFields: WalkthroughField[] = ['sample', 'path', 'finding', 'reference']
        for (const wf of wtFields) {
          const sId = generateItemId(num, 'wt', m + 1, s, wf)
          const tId = generateItemId(num, 'wt', m, s, wf)
          const sv = getResponseValue(sId)
          items.push(setResponseLocal(tId, sv.conclusion, sv.remark, sv.wp_ref))
        }
      }
    }

    // Clear the last slot
    for (const field of fields) {
      const lastId = generateItemId(num, 'ctrl', currentCount, undefined, field)
      items.push(setResponseLocal(lastId, null, null))
    }
    const lastWtCountId = generateItemId(num, 'wt-count', currentCount)
    items.push(setResponseLocal(lastWtCountId, null, '0'))

    // Update count
    const countId = generateItemId(num, 'ctrl-count')
    items.push(setResponseLocal(countId, null, String(currentCount - 1)))

    saveImmediate(items)
  }

  function setControlPointField(num: ProcessNumber, index: number, field: ControlPointField, value: any): void {
    const itemId = generateItemId(num, 'ctrl', index, undefined, field)
    let item: ChecklistItem

    if (field === 'frequency' || field === 'conclusion') {
      // Store in conclusion column
      item = setResponseLocal(itemId, value as string | null)
    } else if (field === 'methods') {
      // Store as comma-separated in remark
      const methods = value as UnderstandingMethod[]
      item = setResponseLocal(itemId, null, methods.join(','))
    } else {
      // Text fields: objective, description, executor, remark → store in remark
      item = setResponseLocal(itemId, null, value as string)
    }

    saveImmediate([item])
  }

  // ─── Walkthrough Records ─────────────────────────────────────────────────

  function getWalkthroughSampleCount(num: ProcessNumber, ctrlIndex: number): number {
    const id = generateItemId(num, 'wt-count', ctrlIndex)
    const r = getResponseValue(id)
    const count = parseInt(r.remark || '0', 10)
    return isNaN(count) ? 0 : count
  }

  function getWalkthroughRecords(num: ProcessNumber, ctrlIndex: number): ComputedRef<WalkthroughRecord[]> {
    return computed(() => {
      const count = getWalkthroughSampleCount(num, ctrlIndex)
      const records: WalkthroughRecord[] = []
      for (let s = 1; s <= count; s++) {
        records.push({
          sampleIndex: s,
          sample: getResponseValue(generateItemId(num, 'wt', ctrlIndex, s, 'sample')).remark || '',
          path: getResponseValue(generateItemId(num, 'wt', ctrlIndex, s, 'path')).remark || '',
          finding: getResponseValue(generateItemId(num, 'wt', ctrlIndex, s, 'finding')).remark || '',
          reference: getResponseValue(generateItemId(num, 'wt', ctrlIndex, s, 'reference')).remark || '',
        })
      }
      return records
    })
  }

  function addWalkthroughSample(num: ProcessNumber, ctrlIndex: number): void {
    const currentCount = getWalkthroughSampleCount(num, ctrlIndex)
    if (currentCount >= 5) return // Max 5 samples per control point

    const newCount = currentCount + 1
    const countId = generateItemId(num, 'wt-count', ctrlIndex)
    const items: ChecklistItem[] = [
      setResponseLocal(countId, null, String(newCount)),
    ]
    saveImmediate(items)
  }

  function setWalkthroughField(num: ProcessNumber, ctrlIndex: number, sampleIndex: number, field: WalkthroughField, value: string): void {
    const itemId = generateItemId(num, 'wt', ctrlIndex, sampleIndex, field)
    const item = setResponseLocal(itemId, null, value)
    saveImmediate([item])
  }

  // ─── Walkthrough Completion ──────────────────────────────────────────────

  function isWalkthroughComplete(num: ProcessNumber): ComputedRef<boolean> {
    return computed(() => {
      const points = getControlPoints(num).value
      // Only consider control points that have "穿行测试" in methods
      const needsWalkthrough = points.filter(cp => cp.methods.includes('穿行测试'))
      if (needsWalkthrough.length === 0) return true
      return needsWalkthrough.every(cp => cp.conclusion !== null)
    })
  }

  function walkthroughSummary(num: ProcessNumber): ComputedRef<WalkthroughSummary> {
    return computed(() => {
      const points = getControlPoints(num).value
      const needsWalkthrough = points.filter(cp => cp.methods.includes('穿行测试'))
      const totalCount = needsWalkthrough.length
      const testedCount = needsWalkthrough.filter(cp => cp.conclusion !== null).length
      const completionRate = totalCount === 0 ? 1 : testedCount / totalCount
      return { testedCount, totalCount, completionRate }
    })
  }

  // ─── Process Conclusion ──────────────────────────────────────────────────

  function suggestConclusion(num: ProcessNumber): ComputedRef<ProcessConclusion | null> {
    return computed(() => {
      const points = getControlPoints(num).value
      return suggestProcessConclusion(points)
    })
  }

  function getConclusion(num: ProcessNumber): ComputedRef<ProcessConclusion | null> {
    return computed(() => {
      const id = generateItemId(num, 'process-conclusion')
      const r = getResponseValue(id)
      return (r.conclusion as ProcessConclusion | null) || null
    })
  }

  function setConclusion(num: ProcessNumber, conclusion: ProcessConclusion, overrideReason?: string): void {
    const conclusionId = generateItemId(num, 'process-conclusion')
    const overrideId = generateItemId(num, 'conclusion-override')

    const oldConclusion = getConclusion(num).value
    const suggested = suggestConclusion(num).value
    const isOverride = suggested !== null && conclusion !== suggested

    const items: ChecklistItem[] = [
      setResponseLocal(conclusionId, conclusion),
    ]

    if (isOverride && overrideReason) {
      items.push(setResponseLocal(overrideId, 'Y', overrideReason))
    } else if (!isOverride) {
      items.push(setResponseLocal(overrideId, null, null))
    }

    saveImmediate(items)

    // Publish EventBus event if conclusion changed
    if (oldConclusion !== conclusion) {
      publishProcessConcluded(num, oldConclusion, conclusion)
    }
  }

  function isConclusionOverridden(num: ProcessNumber): ComputedRef<boolean> {
    return computed(() => {
      const id = generateItemId(num, 'conclusion-override')
      const r = getResponseValue(id)
      return r.conclusion === 'Y'
    })
  }

  function getOverrideReason(num: ProcessNumber): ComputedRef<string> {
    return computed(() => {
      const id = generateItemId(num, 'conclusion-override')
      const r = getResponseValue(id)
      return r.remark || ''
    })
  }

  // ─── Processes (computed card list) ──────────────────────────────────────

  const processes: ComputedRef<ProcessCard[]> = computed(() => {
    return STANDARD_PROCESSES.map((sp) => {
      const num = sp.num
      const applicable = getApplicability(num).value
      const conclusion = getConclusion(num).value
      const suggested = suggestConclusion(num).value
      const overridden = isConclusionOverridden(num).value
      const overrideReason = getOverrideReason(num).value
      const points = getControlPoints(num).value
      const wtComplete = isWalkthroughComplete(num).value

      // Completion ratio: control points with conclusion / total
      const withConclusion = points.filter(cp => cp.conclusion !== null).length
      const completionRatio = `${withConclusion}/${points.length}`

      return {
        num,
        name: sp.name,
        applicable,
        conclusion,
        suggestedConclusion: suggested,
        conclusionOverridden: overridden,
        overrideReason,
        controlPoints: points,
        walkthroughComplete: wtComplete,
        completionRatio,
      }
    })
  })

  // ─── Dashboard Stats ─────────────────────────────────────────────────────

  const dashboardStats: ComputedRef<DashboardStats> = computed(() => {
    const cards = processes.value
    let completed = 0
    let inProgress = 0
    let notStarted = 0
    let notApplicable = 0

    let effective = 0
    let partiallyEffective = 0
    let ineffective = 0
    let effectNA = 0

    let pendingWalkthroughCount = 0

    for (const card of cards) {
      if (!card.applicable) {
        notApplicable++
        effectNA++
        continue
      }

      // Completion
      if (card.conclusion) {
        completed++
      } else if (card.controlPoints.length > 0) {
        inProgress++
      } else {
        notStarted++
      }

      // Effectiveness
      switch (card.conclusion) {
        case '设计有效且已实施':
          effective++
          break
        case '设计有效但未有效实施':
          partiallyEffective++
          break
        case '设计无效':
          ineffective++
          break
        default:
          break
      }

      // Pending walkthrough: control points with "穿行测试" method but no conclusion
      for (const cp of card.controlPoints) {
        if (cp.methods.includes('穿行测试') && cp.conclusion === null) {
          pendingWalkthroughCount++
        }
      }
    }

    return {
      completionDistribution: { completed, inProgress, notStarted, notApplicable },
      effectivenessDistribution: {
        effective,
        partiallyEffective,
        ineffective,
        notApplicable: effectNA,
      },
      pendingWalkthroughCount,
    }
  })

  // ─── Entity Level Context (B22A reference, readonly) ─────────────────────

  const entityLevelContext = ref<EntityLevelContext | null>(null)

  function onControlConclusionChanged(payload: ControlConclusionPayload): void {
    entityLevelContext.value = {
      elementScores: { ...payload.elementScores },
      overallConclusion: payload.overallConclusion,
      completed: payload.overallConclusion !== null,
    }
  }

  // ─── Linkage Info ────────────────────────────────────────────────────────

  const linkageInfo: ComputedRef<LinkageInfo[]> = computed(() => {
    return STANDARD_PROCESSES.map((sp) => {
      const conclusion = getConclusion(sp.num).value
      const b50Impact = conclusion ? (CONCLUSION_TO_B50_IMPACT[conclusion] || '') : ''
      const needsExtendedProcedures = conclusion === '设计无效'

      return {
        processNum: sp.num,
        processName: sp.name,
        conclusion,
        b50Impact,
        targetCycle: sp.targetCycle,
        targetCycleName: `${sp.targetCycle} 循环程序表`,
        needsExtendedProcedures,
      }
    })
  })

  // ─── EventBus Publish ────────────────────────────────────────────────────

  function publishProcessConcluded(num: ProcessNumber, oldConclusion: ProcessConclusion | null, newConclusion: ProcessConclusion): void {
    if (oldConclusion === newConclusion) return
    const processInfo = STANDARD_PROCESSES.find(p => p.num === num)
    if (!processInfo) return

    try {
      // EventBus publish — fire and forget, do not block save
      window.dispatchEvent(new CustomEvent('process:control-concluded', {
        detail: {
          processNum: num,
          processName: processInfo.name,
          oldConclusion,
          newConclusion,
        },
      }))
    } catch {
      // EventBus publish failure is non-critical
      console.warn('[B23] EventBus publish process:control-concluded failed')
    }
  }

  function publishWalkthroughCompleted(num: ProcessNumber): void {
    const processInfo = STANDARD_PROCESSES.find(p => p.num === num)
    if (!processInfo) return

    const points = getControlPoints(num).value
    const needsWalkthrough = points.filter(cp => cp.methods.includes('穿行测试'))
    const effectiveCount = needsWalkthrough.filter(cp => cp.conclusion === '控制有效运行').length
    const effectiveRate = needsWalkthrough.length === 0 ? 1 : effectiveCount / needsWalkthrough.length

    try {
      window.dispatchEvent(new CustomEvent('process:walkthrough-completed', {
        detail: {
          processNum: num,
          controlPointCount: needsWalkthrough.length,
          effectiveRate,
        },
      }))
    } catch {
      console.warn('[B23] EventBus publish process:walkthrough-completed failed')
    }
  }

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    // 流程卡片管理
    processes,
    expandedProcesses,
    toggleProcess,
    expandAll,
    collapseAll,
    // 适用性
    setApplicability,
    getApplicability,
    // 控制点管理
    getControlPoints,
    addControlPoint,
    removeControlPoint,
    setControlPointField,
    // 穿行测试
    getWalkthroughRecords,
    addWalkthroughSample,
    setWalkthroughField,
    isWalkthroughComplete,
    walkthroughSummary,
    // Process_Conclusion
    suggestConclusion,
    getConclusion,
    setConclusion,
    isConclusionOverridden,
    getOverrideReason,
    // Status Dashboard
    dashboardStats,
    // Entity Level Context
    entityLevelContext,
    onControlConclusionChanged,
    // Linkage Panel
    linkageInfo,
    // EventBus 发布
    publishProcessConcluded,
    publishWalkthroughCompleted,
  }
}

export default useB23ProcessControl
