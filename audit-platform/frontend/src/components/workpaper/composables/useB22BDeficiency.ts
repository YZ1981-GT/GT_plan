/**
 * useB22BDeficiency — B22B 缺陷条目同步/评价逻辑/严重程度建议/整体结论/EventBus发布
 *
 * Spec: .kiro/specs/b22b-deficiency-evaluation/
 * Task: 2.2
 *
 * 职责：
 * - 缺陷条目同步：监听 control:deficiency-changed 事件 + 从 B22A 加载现有缺陷
 * - 评价维度设置：分类/影响报表项目/潜在错报金额/补偿性控制/纠正措施
 * - 严重程度评定：自动建议算法 + 手动覆盖
 * - 重要性水平对比：金额 vs B15 重要性水平
 * - 整体评价结论：max-severity 规则
 * - EventBus 发布：deficiency:severity-evaluated 事件
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB22BFormData'
import type { DeficiencyItem } from './useB22AControlMatrix'
import { eventBus } from '@/utils/eventBus'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 缺陷分类 */
export type DeficiencyCategory = '设计缺陷' | '运行缺陷'

/** 严重程度 */
export type SeverityLevel = '重大缺陷' | '重要缺陷' | '一般缺陷'

/** 整体评价结论 */
export type OverallConclusion = '存在重大缺陷' | '存在重要缺陷' | '仅存在一般缺陷' | '未发现控制缺陷'

/** 报表项目 */
export type FinancialStatementItem = '资产' | '负债' | '所有者权益' | '收入' | '费用'

/** 重要性对比结果 */
export interface MaterialityComparison {
  exceeds: boolean
  difference: number | null
  color: 'red' | 'green'
}

/** 评价条目（单条缺陷的完整评价数据） */
export interface EvaluationItem {
  source: DeficiencyItem
  category: DeficiencyCategory | null
  affectedAccounts: FinancialStatementItem[]
  potentialMisstatement: number | null
  hasCompensatingControl: boolean | null
  compensatingControlDesc: string
  hasCorrectiveAction: boolean | null
  correctiveActionDesc: string
  severity: SeverityLevel | null
  severityOverridden: boolean
  overrideReason: string
  eliminated: boolean
}

/** 严重程度统计 */
export interface SeverityStats {
  material: number
  significant: number
  general: number
  total: number
}

/** EventBus 发布载荷：deficiency:severity-evaluated */
export interface SeverityEvaluatedPayload {
  severities: { index: number; severity: SeverityLevel }[]
  overallConclusion: OverallConclusion
  materialCount: number
  significantCount: number
  impactsAuditOpinion: boolean
  requiresExtendedProcedures: boolean
}

/** EventBus 接收载荷：control:deficiency-changed（来自 B22A） */
export interface DeficiencyChangePayload {
  added: DeficiencyItem[]
  removed: DeficiencyItem[]
  total: number
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Constants ───────────────────────────────────────────────────────────────

export const SEVERITY_LEVELS: SeverityLevel[] = ['重大缺陷', '重要缺陷', '一般缺陷']

export const DEFICIENCY_CATEGORIES: DeficiencyCategory[] = ['设计缺陷', '运行缺陷']

export const FINANCIAL_STATEMENT_ITEMS: FinancialStatementItem[] = [
  '资产', '负债', '所有者权益', '收入', '费用',
]

export const SEVERITY_COLOR_MAP: Record<SeverityLevel, { bg: string; text: string }> = {
  '重大缺陷': { bg: '#FEE2E2', text: '#DC2626' },
  '重要缺陷': { bg: '#FEF3C7', text: '#D97706' },
  '一般缺陷': { bg: '#D1FAE5', text: '#059669' },
}

// ─── Pure Functions (exported for testing) ───────────────────────────────────

/** 缺陷分类默认映射 */
export function defaultCategory(deficiencyType: '设计无效' | '未实施'): DeficiencyCategory {
  return deficiencyType === '设计无效' ? '设计缺陷' : '运行缺陷'
}

/** 严重程度建议算法 */
export function suggestSeverity(
  potentialMisstatement: number | null,
  materialityLevel: number | null,
  hasCompensatingControl: boolean | null,
  hasCorrectiveAction: boolean | null
): SeverityLevel | null {
  if (potentialMisstatement === null || materialityLevel === null) return null

  const exceedsMateriality = potentialMisstatement > materialityLevel

  if (exceedsMateriality && !hasCompensatingControl && !hasCorrectiveAction) {
    return '重大缺陷'
  }
  if (exceedsMateriality && (hasCompensatingControl || hasCorrectiveAction)) {
    return '重要缺陷'
  }
  return '一般缺陷'
}

/** 整体评价结论计算 */
export function computeOverallConclusion(items: EvaluationItem[]): OverallConclusion {
  const activeItems = items.filter(i => !i.eliminated && i.severity !== null)

  if (activeItems.length === 0) return '未发现控制缺陷'
  if (activeItems.some(i => i.severity === '重大缺陷')) return '存在重大缺陷'
  if (activeItems.some(i => i.severity === '重要缺陷')) return '存在重要缺陷'
  return '仅存在一般缺陷'
}

/** 重要性水平对比 */
export function compareMateriality(amount: number, materialityLevel: number | null): MaterialityComparison {
  if (materialityLevel === null || materialityLevel <= 0) {
    return { exceeds: false, difference: null, color: 'green' }
  }
  const exceeds = amount > materialityLevel
  return {
    exceeds,
    difference: exceeds ? amount - materialityLevel : null,
    color: exceeds ? 'red' : 'green',
  }
}

/** 缺陷数量统计 */
export function computeSeverityStats(items: EvaluationItem[]): SeverityStats {
  const activeItems = items.filter(i => !i.eliminated)
  const material = activeItems.filter(i => i.severity === '重大缺陷').length
  const significant = activeItems.filter(i => i.severity === '重要缺陷').length
  const general = activeItems.filter(i => i.severity === '一般缺陷').length
  return { material, significant, general, total: material + significant + general }
}

/** 生成 B22B item_id */
export function generateItemId(
  idx: number,
  field: 'category' | 'accounts' | 'amount' | 'compensating' | 'corrective' | 'severity' | 'override' | 'source' | 'eliminated'
): string {
  return `B22B-def-${idx}-${field}`
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22BDeficiency(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  materialityLevel: Ref<number | null>,
  saveImmediate: SaveFn
) {
  const deficiencyItems = ref<EvaluationItem[]>([])
  const eliminatedItems = ref<EvaluationItem[]>([])
  const overallNote = ref<string>('')

  // ─── Sync from EventBus ────────────────────────────────────────────────

  function syncFromEvent(payload: DeficiencyChangePayload): void {
    // Process added items
    for (const added of payload.added) {
      // Check if already exists (avoid duplicates)
      const exists = deficiencyItems.value.some(
        item => item.source.tab === added.tab &&
          item.source.subPanel === added.subPanel &&
          item.source.index === added.index
      )
      if (!exists) {
        deficiencyItems.value.push(createEvaluationItem(added))
      }
    }

    // Process removed items
    for (const removed of payload.removed) {
      const idx = deficiencyItems.value.findIndex(
        item => item.source.tab === removed.tab &&
          item.source.subPanel === removed.subPanel &&
          item.source.index === removed.index
      )
      if (idx !== -1) {
        const item = deficiencyItems.value[idx]
        item.eliminated = true
        eliminatedItems.value.push(item)
        deficiencyItems.value.splice(idx, 1)
      }
    }

    persistAll()
  }

  /** 从 B22A checklist_responses 加载现有缺陷 */
  function loadFromB22A(b22aResponses: ChecklistResponse[]): void {
    // Extract deficiency items from B22A responses
    // These are items where conclusion = '设计无效' or '未实施'
    const deficiencies: DeficiencyItem[] = []

    for (const r of b22aResponses) {
      if (!r.item_id.includes('-conclusion')) continue
      if (r.conclusion !== '设计无效' && r.conclusion !== '未实施') continue

      // Parse item_id to extract tab/index/subPanel
      // Format: B22A-T{tab}-item-{index}-conclusion or B22A-T{tab}-IT-{subPanel}-{index}-conclusion
      const itMatch = r.item_id.match(/^B22A-T(\d)-IT-(\w+)-(\d+)-conclusion$/)
      const normalMatch = r.item_id.match(/^B22A-T(\d)-item-(\d+)-conclusion$/)

      if (itMatch) {
        const tab = parseInt(itMatch[1], 10) as 1 | 2 | 3 | 4 | 5
        const subPanel = itMatch[2] as any
        const index = parseInt(itMatch[3], 10)
        // Try to get control point from corresponding -point item
        const pointId = r.item_id.replace('-conclusion', '-point')
        const pointItem = b22aResponses.find(x => x.item_id === pointId)
        deficiencies.push({
          tab,
          subPanel,
          index,
          controlPoint: pointItem?.remark || '',
          deficiencyType: r.conclusion as '设计无效' | '未实施',
          elementName: getElementName(tab, subPanel),
        })
      } else if (normalMatch) {
        const tab = parseInt(normalMatch[1], 10) as 1 | 2 | 3 | 4 | 5
        const index = parseInt(normalMatch[2], 10)
        const pointId = r.item_id.replace('-conclusion', '-point')
        const pointItem = b22aResponses.find(x => x.item_id === pointId)
        deficiencies.push({
          tab,
          subPanel: null,
          index,
          controlPoint: pointItem?.remark || '',
          deficiencyType: r.conclusion as '设计无效' | '未实施',
          elementName: getElementName(tab, null),
        })
      }
    }

    // Merge with already-saved B22B data
    for (const def of deficiencies) {
      const exists = deficiencyItems.value.some(
        item => item.source.tab === def.tab &&
          item.source.subPanel === def.subPanel &&
          item.source.index === def.index
      )
      if (!exists) {
        deficiencyItems.value.push(createEvaluationItem(def))
      }
    }

    // Restore saved evaluation data from allResponses
    restoreFromSavedData()
  }

  // ─── Internal helpers ──────────────────────────────────────────────────

  function getElementName(tab: number, subPanel: string | null): string {
    const TAB_NAMES: Record<number, string> = {
      1: '控制环境',
      2: '风险评估过程',
      3: '信息系统与沟通',
      4: '控制活动',
      5: '监督',
    }
    const base = TAB_NAMES[tab] || `要素${tab}`
    if (subPanel) return `${base} - ${subPanel}`
    return base
  }

  function createEvaluationItem(source: DeficiencyItem): EvaluationItem {
    return {
      source,
      category: defaultCategory(source.deficiencyType),
      affectedAccounts: [],
      potentialMisstatement: null,
      hasCompensatingControl: null,
      compensatingControlDesc: '',
      hasCorrectiveAction: null,
      correctiveActionDesc: '',
      severity: null,
      severityOverridden: false,
      overrideReason: '',
      eliminated: false,
    }
  }

  /** Restore evaluation data from saved B22B- items in allResponses */
  function restoreFromSavedData(): void {
    // Read def count
    const countItem = allResponses.value.get('B22B-def-count')
    const savedCount = parseInt(countItem?.remark || '0', 10)

    for (let idx = 1; idx <= savedCount; idx++) {
      // Find matching deficiency item by index
      const itemIndex = idx - 1
      if (itemIndex >= deficiencyItems.value.length) break

      const item = deficiencyItems.value[itemIndex]

      // Restore category
      const catItem = allResponses.value.get(generateItemId(idx, 'category'))
      if (catItem?.conclusion) {
        item.category = catItem.conclusion as DeficiencyCategory
      }

      // Restore affected accounts
      const accItem = allResponses.value.get(generateItemId(idx, 'accounts'))
      if (accItem?.remark) {
        item.affectedAccounts = accItem.remark.split(',').filter(Boolean) as FinancialStatementItem[]
      }

      // Restore potential misstatement
      const amtItem = allResponses.value.get(generateItemId(idx, 'amount'))
      if (amtItem?.remark) {
        const parsed = parseFloat(amtItem.remark)
        if (!isNaN(parsed)) item.potentialMisstatement = parsed
      }

      // Restore compensating control
      const compItem = allResponses.value.get(generateItemId(idx, 'compensating'))
      if (compItem?.conclusion) {
        item.hasCompensatingControl = compItem.conclusion === 'Y'
        item.compensatingControlDesc = compItem.remark || ''
      }

      // Restore corrective action
      const corrItem = allResponses.value.get(generateItemId(idx, 'corrective'))
      if (corrItem?.conclusion) {
        item.hasCorrectiveAction = corrItem.conclusion === 'Y'
        item.correctiveActionDesc = corrItem.remark || ''
      }

      // Restore severity
      const sevItem = allResponses.value.get(generateItemId(idx, 'severity'))
      if (sevItem?.conclusion) {
        item.severity = sevItem.conclusion as SeverityLevel
      }

      // Restore override
      const ovrItem = allResponses.value.get(generateItemId(idx, 'override'))
      if (ovrItem?.conclusion === 'Y') {
        item.severityOverridden = true
        item.overrideReason = ovrItem.remark || ''
      }

      // Restore eliminated
      const elimItem = allResponses.value.get(generateItemId(idx, 'eliminated'))
      if (elimItem?.conclusion === 'Y') {
        item.eliminated = true
        // Move to eliminated list
        eliminatedItems.value.push(item)
        deficiencyItems.value.splice(itemIndex, 1)
      }
    }

    // Restore overall note
    const noteItem = allResponses.value.get('B22B-overall-note')
    if (noteItem?.remark) {
      overallNote.value = noteItem.remark
    }
  }

  // ─── Evaluation Operations ─────────────────────────────────────────────

  function setCategory(index: number, category: DeficiencyCategory): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    deficiencyItems.value[index].category = category

    const idx = index + 1
    const item: ChecklistItem = {
      item_id: generateItemId(idx, 'category'),
      conclusion: category,
      remark: null,
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function setAffectedAccounts(index: number, accounts: FinancialStatementItem[]): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    deficiencyItems.value[index].affectedAccounts = accounts

    const idx = index + 1
    const item: ChecklistItem = {
      item_id: generateItemId(idx, 'accounts'),
      conclusion: null,
      remark: accounts.join(','),
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function setPotentialMisstatement(index: number, amount: number): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    deficiencyItems.value[index].potentialMisstatement = amount

    const idx = index + 1
    const item: ChecklistItem = {
      item_id: generateItemId(idx, 'amount'),
      conclusion: null,
      remark: String(amount),
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function setCompensatingControl(index: number, hasControl: boolean, description: string): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    deficiencyItems.value[index].hasCompensatingControl = hasControl
    deficiencyItems.value[index].compensatingControlDesc = description

    const idx = index + 1
    const item: ChecklistItem = {
      item_id: generateItemId(idx, 'compensating'),
      conclusion: hasControl ? 'Y' : 'N',
      remark: description || null,
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function setCorrectiveAction(index: number, hasAction: boolean, description: string): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    deficiencyItems.value[index].hasCorrectiveAction = hasAction
    deficiencyItems.value[index].correctiveActionDesc = description

    const idx = index + 1
    const item: ChecklistItem = {
      item_id: generateItemId(idx, 'corrective'),
      conclusion: hasAction ? 'Y' : 'N',
      remark: description || null,
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function setSeverity(index: number, severity: SeverityLevel): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    deficiencyItems.value[index].severity = severity
    deficiencyItems.value[index].severityOverridden = false
    deficiencyItems.value[index].overrideReason = ''

    const idx = index + 1
    const sevItem: ChecklistItem = {
      item_id: generateItemId(idx, 'severity'),
      conclusion: severity,
      remark: null,
      wp_ref: null,
    }
    // Clear override if previously set
    const ovrItem: ChecklistItem = {
      item_id: generateItemId(idx, 'override'),
      conclusion: null,
      remark: null,
      wp_ref: null,
    }
    allResponses.value.set(sevItem.item_id, sevItem)
    allResponses.value.set(ovrItem.item_id, ovrItem)
    saveImmediate([sevItem, ovrItem])

    // Publish event after severity change
    publishSeverityEvent()
  }

  function setSeverityOverride(index: number, severity: SeverityLevel, reason: string): void {
    if (index < 0 || index >= deficiencyItems.value.length) return
    if (!reason.trim()) return // Require reason

    deficiencyItems.value[index].severity = severity
    deficiencyItems.value[index].severityOverridden = true
    deficiencyItems.value[index].overrideReason = reason.trim()

    const idx = index + 1
    const sevItem: ChecklistItem = {
      item_id: generateItemId(idx, 'severity'),
      conclusion: severity,
      remark: null,
      wp_ref: null,
    }
    const ovrItem: ChecklistItem = {
      item_id: generateItemId(idx, 'override'),
      conclusion: 'Y',
      remark: reason.trim(),
      wp_ref: null,
    }
    allResponses.value.set(sevItem.item_id, sevItem)
    allResponses.value.set(ovrItem.item_id, ovrItem)
    saveImmediate([sevItem, ovrItem])

    // Publish event after severity change
    publishSeverityEvent()
  }

  // ─── Computed Properties ───────────────────────────────────────────────

  /** 整体评价结论 */
  const overallConclusionComputed: ComputedRef<OverallConclusion> = computed(() => {
    return computeOverallConclusion(deficiencyItems.value)
  })

  /** 严重程度统计 */
  const severityStats: ComputedRef<SeverityStats> = computed(() => {
    return computeSeverityStats(deficiencyItems.value)
  })

  /** 全部已评价（canReview 前置条件） */
  const allEvaluated: ComputedRef<boolean> = computed(() => {
    const activeItems = deficiencyItems.value.filter(i => !i.eliminated)
    if (activeItems.length === 0) return true
    return activeItems.every(i => i.severity !== null)
  })

  /** 审计影响醒目提示 */
  const showAuditImpactWarning: ComputedRef<boolean> = computed(() => {
    const conclusion = overallConclusionComputed.value
    return conclusion === '存在重大缺陷' || conclusion === '存在重要缺陷'
  })

  // ─── EventBus Publish ──────────────────────────────────────────────────

  function publishSeverityEvent(): void {
    try {
      const conclusion = overallConclusionComputed.value
      const stats = severityStats.value
      const severities = deficiencyItems.value
        .filter(i => !i.eliminated && i.severity !== null)
        .map((item, idx) => ({ index: idx, severity: item.severity! }))

      const payload: SeverityEvaluatedPayload = {
        severities,
        overallConclusion: conclusion,
        materialCount: stats.material,
        significantCount: stats.significant,
        impactsAuditOpinion: conclusion === '存在重大缺陷',
        requiresExtendedProcedures: conclusion === '存在重大缺陷' || conclusion === '存在重要缺陷',
      }

      eventBus.emit('deficiency:severity-evaluated' as any, payload)
    } catch {
      // EventBus 发布失败仅 console.warn，不影响本组件保存
      console.warn('[B22B] EventBus publish failed')
    }
  }

  // ─── Persist All ───────────────────────────────────────────────────────

  function persistAll(): void {
    const items: ChecklistItem[] = []

    // Save def count
    items.push({
      item_id: 'B22B-def-count',
      conclusion: null,
      remark: String(deficiencyItems.value.length + eliminatedItems.value.length),
      wp_ref: null,
    })

    // Save overall conclusion
    items.push({
      item_id: 'B22B-overall-conclusion',
      conclusion: overallConclusionComputed.value,
      remark: null,
      wp_ref: null,
    })

    // Save overall note
    if (overallNote.value) {
      items.push({
        item_id: 'B22B-overall-note',
        conclusion: null,
        remark: overallNote.value,
        wp_ref: null,
      })
    }

    // Save each deficiency item
    const allItems = [...deficiencyItems.value, ...eliminatedItems.value]
    for (let i = 0; i < allItems.length; i++) {
      const idx = i + 1
      const item = allItems[i]

      // Source
      items.push({
        item_id: generateItemId(idx, 'source'),
        conclusion: null,
        remark: JSON.stringify({
          tab: item.source.tab,
          subPanel: item.source.subPanel,
          index: item.source.index,
          controlPoint: item.source.controlPoint,
          deficiencyType: item.source.deficiencyType,
          elementName: item.source.elementName,
        }),
        wp_ref: null,
      })

      // Category
      if (item.category) {
        items.push({
          item_id: generateItemId(idx, 'category'),
          conclusion: item.category,
          remark: null,
          wp_ref: null,
        })
      }

      // Severity
      if (item.severity) {
        items.push({
          item_id: generateItemId(idx, 'severity'),
          conclusion: item.severity,
          remark: null,
          wp_ref: null,
        })
      }

      // Eliminated
      if (item.eliminated) {
        items.push({
          item_id: generateItemId(idx, 'eliminated'),
          conclusion: 'Y',
          remark: null,
          wp_ref: null,
        })
      }
    }

    // Update local allResponses
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }

    saveImmediate(items)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 缺陷列表
    deficiencyItems,
    eliminatedItems,
    // 同步
    syncFromEvent,
    loadFromB22A,
    // 评价操作
    setCategory,
    setAffectedAccounts,
    setPotentialMisstatement,
    setCompensatingControl,
    setCorrectiveAction,
    setSeverity,
    setSeverityOverride,
    // 计算属性
    overallConclusion: overallConclusionComputed,
    severityStats,
    allEvaluated,
    showAuditImpactWarning,
    // 整体评价说明
    overallNote,
    // EventBus 发布
    publishSeverityEvent,
  }
}

export default useB22BDeficiency
