/**
 * useCControlTest — C 类控制测试主 composable
 *
 * Spec: .kiro/specs/c-control-test-component/
 * Task: 2.2
 *
 * 职责：
 * - 控制点卡片管理（展开/收起/CRUD）
 * - 测试方法多选
 * - 样本 CRUD + 批量添加
 * - 偏差率自动计算
 * - Control_Point_Conclusion 自动建议
 * - Cycle_Conclusion 汇总建议
 * - B23 控制点引用
 * - EventBus 发布 control:test-concluded
 * - 复核签字 + Amendment
 * - 联动信息
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useCControlTestData'

// ─── Types (exported) ────────────────────────────────────────────────────────

export type TestMethod = '询问' | '观察' | '检查' | '重新执行'
export type SampleResult = '有效' | '偏差' | '不适用'
export type ControlPointConclusion = '控制有效运行' | '控制存在偏差但可接受' | '控制无效'
export type CycleConclusion = '全部有效' | '部分偏差' | '控制失效'

export interface SampleItem {
  index: number
  voucherNo: string
  date: string
  amount: string
  result: SampleResult | null
  deviationDesc: string
}

export interface BatchSampleInput {
  startVoucherNo: string
  endVoucherNo: string
}

export interface DeviationStats {
  totalSamples: number
  effectiveSamples: number
  deviationCount: number
  deviationRate: number | null
  exceedsTolerable: boolean
}

export interface ControlPointTest {
  index: number
  controlId: string
  objective: string
  testMethods: TestMethod[]
  samples: SampleItem[]
  deviationStats: DeviationStats
  conclusion: ControlPointConclusion | null
  suggestedConclusion: ControlPointConclusion | null
  conclusionOverridden: boolean
  overrideReason: string
  isFromB23: boolean
}

export interface B23ControlPointRef {
  controlId: string
  objective: string
  description: string
  processName: string
}

export interface CControlLinkageInfo {
  b23WpCode: string
  b23ProcessNum: number
  b50WpCode: string
  targetCycleCode: string
  targetCycleName: string
  needsExtendedProcedures: boolean
}

export interface TestConcludedPayload {
  wpCode: string
  cycleName: string
  conclusion: CycleConclusion
  deviationSummary: {
    totalControlPoints: number
    effectiveCount: number
    deviationAcceptableCount: number
    ineffectiveCount: number
    maxDeviationRate: number
  }
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Constants (exported for testing) ────────────────────────────────────────

export const CYCLE_CONFIG: Record<number, { name: string; b23ProcessNum: number; targetCycle: string; targetCycleName: string }> = {
  2:  { name: '采购与付款循环', b23ProcessNum: 1, targetCycle: 'DA', targetCycleName: '采购与付款' },
  3:  { name: '销售与收款循环', b23ProcessNum: 2, targetCycle: 'EA', targetCycleName: '销售与收款' },
  4:  { name: '资金管理循环', b23ProcessNum: 3, targetCycle: 'FA', targetCycleName: '资金管理' },
  5:  { name: '生产与存货循环', b23ProcessNum: 4, targetCycle: 'GA', targetCycleName: '生产与存货' },
  6:  { name: '薪酬与人力循环', b23ProcessNum: 5, targetCycle: 'HA', targetCycleName: '薪酬与人力' },
  7:  { name: '固定资产循环', b23ProcessNum: 6, targetCycle: 'IA', targetCycleName: '固定资产' },
  8:  { name: '投资循环', b23ProcessNum: 7, targetCycle: 'JA', targetCycleName: '投资' },
  9:  { name: '其他流程', b23ProcessNum: 8, targetCycle: 'KA', targetCycleName: '其他' },
  10: { name: '收入确认循环', b23ProcessNum: 2, targetCycle: 'EA', targetCycleName: '收入确认' },
  11: { name: '关联方交易循环', b23ProcessNum: 8, targetCycle: 'KA', targetCycleName: '关联方交易' },
  12: { name: '估计与判断循环', b23ProcessNum: 8, targetCycle: 'KA', targetCycleName: '估计与判断' },
  13: { name: '期末财务报告循环', b23ProcessNum: 8, targetCycle: 'KA', targetCycleName: '期末财务报告' },
  14: { name: '信息技术一般控制', b23ProcessNum: 8, targetCycle: 'KA', targetCycleName: 'ITGC' },
  15: { name: '其他特殊控制', b23ProcessNum: 8, targetCycle: 'KA', targetCycleName: '其他特殊' },
}

export const CONTROL_TEST_COLORS: Record<string, { color: string; bg: string }> = {
  '控制有效运行': { color: '#52c41a', bg: '#f6ffed' },
  '控制存在偏差但可接受': { color: '#faad14', bg: '#fffbe6' },
  '控制无效': { color: '#ff4d4f', bg: '#fff2f0' },
  '全部有效': { color: '#52c41a', bg: '#f6ffed' },
  '部分偏差': { color: '#faad14', bg: '#fffbe6' },
  '控制失效': { color: '#ff4d4f', bg: '#fff2f0' },
  '有效': { color: '#52c41a', bg: '#f6ffed' },
  '偏差': { color: '#ff4d4f', bg: '#fff2f0' },
  '不适用': { color: '#bfbfbf', bg: '#fafafa' },
}

// ─── Pure Functions (exported for testing) ───────────────────────────────────

/**
 * 偏差率计算
 * deviationRate = 偏差数 ÷ (总样本 - 不适用样本)
 * 分母=0 时返回 null
 */
export function calculateDeviationStats(samples: SampleItem[], tolerableRate: number = 0.1): DeviationStats {
  const totalSamples = samples.length
  const notApplicable = samples.filter(s => s.result === '不适用').length
  const effectiveSamples = totalSamples - notApplicable
  const deviationCount = samples.filter(s => s.result === '偏差').length
  const deviationRate = effectiveSamples > 0 ? deviationCount / effectiveSamples : null
  const exceedsTolerable = deviationRate !== null && deviationRate > tolerableRate

  return { totalSamples, effectiveSamples, deviationCount, deviationRate, exceedsTolerable }
}

/**
 * 控制点结论自动建议
 * 0 → 有效；≤容忍 → 可接受；>容忍 → 无效；null → null
 */
export function suggestControlPointConclusion(
  deviationRate: number | null,
  tolerableRate: number
): ControlPointConclusion | null {
  if (deviationRate === null) return null
  if (deviationRate === 0) return '控制有效运行'
  if (deviationRate <= tolerableRate) return '控制存在偏差但可接受'
  return '控制无效'
}

/**
 * 循环结论汇总建议
 * 全有效→全部有效；有偏差无无效→部分偏差；有无效→控制失效；全null→null
 */
export function suggestCycleConclusion(
  pointConclusions: (ControlPointConclusion | null)[]
): CycleConclusion | null {
  const evaluated = pointConclusions.filter(c => c !== null) as ControlPointConclusion[]
  if (evaluated.length === 0) return null
  if (evaluated.some(c => c === '控制无效')) return '控制失效'
  if (evaluated.some(c => c === '控制存在偏差但可接受')) return '部分偏差'
  return '全部有效'
}

/**
 * 生成 item_id
 */
export function generateCControlItemId(
  cycleNum: number,
  type: 'ctrl-count' | 'ctrl' | 'sample-count' | 'sample' | 'cycle-conclusion' | 'cycle-conclusion-override' | 'tolerable-rate' | 'review-sign' | 'amend',
  ctrlIndex?: number,
  sampleIndex?: number,
  field?: string,
  amendRound?: number
): string {
  const prefix = `C${cycleNum}`
  switch (type) {
    case 'ctrl-count':
      return `${prefix}-ctrl-count`
    case 'ctrl':
      return `${prefix}-ctrl-${ctrlIndex}-${field}`
    case 'sample-count':
      return `${prefix}-ctrl-${ctrlIndex}-sample-count`
    case 'sample':
      return `${prefix}-ctrl-${ctrlIndex}-sample-${sampleIndex}-${field}`
    case 'cycle-conclusion':
      return `${prefix}-cycle-conclusion`
    case 'cycle-conclusion-override':
      return `${prefix}-cycle-conclusion-override`
    case 'tolerable-rate':
      return `${prefix}-tolerable-rate`
    case 'review-sign':
      return `${prefix}-review-sign`
    case 'amend':
      return `${prefix}-amend-${amendRound}-reason`
  }
}

// ─── Main Composable ─────────────────────────────────────────────────────────

export function useCControlTest(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  cycleNum: Ref<number>,
  wpCode: Ref<string>,
  saveImmediate: SaveFn,
  externalReadonly: Ref<boolean>
) {
  // ─── Helpers ─────────────────────────────────────────────────────────────

  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }

  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null, wpRef: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark, wp_ref: wpRef }
    allResponses.value.set(itemId, item)
    return item
  }

  // ─── Expand/Collapse ─────────────────────────────────────────────────────

  const expandedCards = ref<Set<number>>(new Set())

  function toggleCard(index: number): void {
    const s = new Set(expandedCards.value)
    if (s.has(index)) s.delete(index)
    else s.add(index)
    expandedCards.value = s
  }

  function expandAll(): void {
    const count = getControlPointCount()
    const s = new Set<number>()
    for (let i = 1; i <= count; i++) s.add(i)
    expandedCards.value = s
  }

  function collapseAll(): void {
    expandedCards.value = new Set()
  }

  // ─── Control Point Count ─────────────────────────────────────────────────

  function getControlPointCount(): number {
    const id = generateCControlItemId(cycleNum.value, 'ctrl-count')
    const r = getVal(id)
    const count = parseInt(r.remark || '0', 10)
    return isNaN(count) ? 0 : count
  }

  function addControlPoint(): void {
    const currentCount = getControlPointCount()
    if (currentCount >= 30) return
    const newCount = currentCount + 1
    const countId = generateCControlItemId(cycleNum.value, 'ctrl-count')
    const items: ChecklistItem[] = [setLocal(countId, null, String(newCount))]
    // Expand the new card
    const s = new Set(expandedCards.value)
    s.add(newCount)
    expandedCards.value = s
    saveImmediate(items)
  }

  function removeControlPoint(index: number): void {
    const currentCount = getControlPointCount()
    if (index < 1 || index > currentCount) return

    const items: ChecklistItem[] = []
    const ctrlFields = ['id', 'objective', 'methods', 'conclusion', 'override']

    // Shift all items after the removed index down by 1
    for (let m = index; m < currentCount; m++) {
      for (const field of ctrlFields) {
        const sourceId = generateCControlItemId(cycleNum.value, 'ctrl', m + 1, undefined, field)
        const targetId = generateCControlItemId(cycleNum.value, 'ctrl', m, undefined, field)
        const source = getVal(sourceId)
        items.push(setLocal(targetId, source.conclusion, source.remark, source.wp_ref))
      }
      // Shift samples
      const srcSampleCountId = generateCControlItemId(cycleNum.value, 'sample-count', m + 1)
      const tgtSampleCountId = generateCControlItemId(cycleNum.value, 'sample-count', m)
      const sampleCount = parseInt(getVal(srcSampleCountId).remark || '0', 10) || 0
      items.push(setLocal(tgtSampleCountId, null, String(sampleCount)))

      const sampleFields = ['voucher', 'date', 'amount', 'result', 'deviation']
      for (let s = 1; s <= sampleCount; s++) {
        for (const sf of sampleFields) {
          const sId = generateCControlItemId(cycleNum.value, 'sample', m + 1, s, sf)
          const tId = generateCControlItemId(cycleNum.value, 'sample', m, s, sf)
          const sv = getVal(sId)
          items.push(setLocal(tId, sv.conclusion, sv.remark, sv.wp_ref))
        }
      }
    }

    // Clear last slot
    for (const field of ctrlFields) {
      const lastId = generateCControlItemId(cycleNum.value, 'ctrl', currentCount, undefined, field)
      items.push(setLocal(lastId, null, null))
    }
    const lastSampleCountId = generateCControlItemId(cycleNum.value, 'sample-count', currentCount)
    items.push(setLocal(lastSampleCountId, null, '0'))

    // Update count
    const countId = generateCControlItemId(cycleNum.value, 'ctrl-count')
    items.push(setLocal(countId, null, String(currentCount - 1)))

    saveImmediate(items)
  }

  // ─── Test Methods ──────────────────────────────────────────────────────────

  function setTestMethods(ctrlIndex: number, methods: TestMethod[]): void {
    const itemId = generateCControlItemId(cycleNum.value, 'ctrl', ctrlIndex, undefined, 'methods')
    const item = setLocal(itemId, methods.join(','))
    saveImmediate([item])
  }

  // ─── Sample Management ─────────────────────────────────────────────────────

  function getSampleCount(ctrlIndex: number): number {
    const id = generateCControlItemId(cycleNum.value, 'sample-count', ctrlIndex)
    const r = getVal(id)
    const count = parseInt(r.remark || '0', 10)
    return isNaN(count) ? 0 : count
  }

  function getSamples(ctrlIndex: number): ComputedRef<SampleItem[]> {
    return computed(() => {
      const count = getSampleCount(ctrlIndex)
      const samples: SampleItem[] = []
      for (let s = 1; s <= count; s++) {
        samples.push({
          index: s,
          voucherNo: getVal(generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s, 'voucher')).remark || '',
          date: getVal(generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s, 'date')).remark || '',
          amount: getVal(generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s, 'amount')).remark || '',
          result: (getVal(generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s, 'result')).conclusion as SampleResult | null),
          deviationDesc: getVal(generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s, 'deviation')).remark || '',
        })
      }
      return samples
    })
  }

  function addSample(ctrlIndex: number, sample: Partial<SampleItem>): void {
    const currentCount = getSampleCount(ctrlIndex)
    if (currentCount >= 50) return
    const newCount = currentCount + 1
    const countId = generateCControlItemId(cycleNum.value, 'sample-count', ctrlIndex)
    const items: ChecklistItem[] = [setLocal(countId, null, String(newCount))]

    if (sample.voucherNo) {
      const id = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, newCount, 'voucher')
      items.push(setLocal(id, null, sample.voucherNo))
    }
    if (sample.date) {
      const id = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, newCount, 'date')
      items.push(setLocal(id, null, sample.date))
    }
    if (sample.amount) {
      const id = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, newCount, 'amount')
      items.push(setLocal(id, null, sample.amount))
    }
    saveImmediate(items)
  }

  function removeSample(ctrlIndex: number, sampleIndex: number): void {
    const currentCount = getSampleCount(ctrlIndex)
    if (sampleIndex < 1 || sampleIndex > currentCount) return

    const items: ChecklistItem[] = []
    const sampleFields = ['voucher', 'date', 'amount', 'result', 'deviation']

    // Shift down
    for (let s = sampleIndex; s < currentCount; s++) {
      for (const f of sampleFields) {
        const srcId = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s + 1, f)
        const tgtId = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, s, f)
        const src = getVal(srcId)
        items.push(setLocal(tgtId, src.conclusion, src.remark, src.wp_ref))
      }
    }
    // Clear last
    for (const f of sampleFields) {
      const lastId = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, currentCount, f)
      items.push(setLocal(lastId, null, null))
    }
    // Update count
    const countId = generateCControlItemId(cycleNum.value, 'sample-count', ctrlIndex)
    items.push(setLocal(countId, null, String(currentCount - 1)))
    saveImmediate(items)
  }

  function addBatchSamples(ctrlIndex: number, batch: BatchSampleInput): void {
    const startNum = parseInt(batch.startVoucherNo, 10)
    const endNum = parseInt(batch.endVoucherNo, 10)
    if (isNaN(startNum) || isNaN(endNum) || endNum < startNum) return
    const count = Math.min(endNum - startNum + 1, 50 - getSampleCount(ctrlIndex))
    for (let i = 0; i < count; i++) {
      addSample(ctrlIndex, { voucherNo: String(startNum + i) })
    }
  }

  function setSampleResult(ctrlIndex: number, sampleIndex: number, result: SampleResult): void {
    const id = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, sampleIndex, 'result')
    const item = setLocal(id, result)
    saveImmediate([item])
  }

  function setDeviationDescription(ctrlIndex: number, sampleIndex: number, desc: string): void {
    const id = generateCControlItemId(cycleNum.value, 'sample', ctrlIndex, sampleIndex, 'deviation')
    const item = setLocal(id, null, desc)
    allResponses.value.set(id, item)
    // This is a text field — caller should use saveDebouncedText
  }

  // ─── Deviation Stats ───────────────────────────────────────────────────────

  function getDeviationStats(ctrlIndex: number): ComputedRef<DeviationStats> {
    return computed(() => {
      const samples = getSamples(ctrlIndex).value
      return calculateDeviationStats(samples, tolerableDeviationRate.value)
    })
  }

  // ─── Tolerable Deviation Rate ──────────────────────────────────────────────

  const tolerableDeviationRate = computed({
    get: () => {
      const id = generateCControlItemId(cycleNum.value, 'tolerable-rate')
      const r = getVal(id)
      const val = parseFloat(r.remark || '10')
      return isNaN(val) ? 0.1 : val / 100
    },
    set: () => { /* use setTolerableRate */ },
  })

  function setTolerableRate(rate: number): void {
    const id = generateCControlItemId(cycleNum.value, 'tolerable-rate')
    const percentVal = Math.round(rate * 100)
    const item = setLocal(id, null, String(percentVal))
    saveImmediate([item])
  }

  // ─── Control Point Conclusion ──────────────────────────────────────────────

  function suggestPointConclusion(ctrlIndex: number): ComputedRef<ControlPointConclusion | null> {
    return computed(() => {
      const stats = getDeviationStats(ctrlIndex).value
      return suggestControlPointConclusion(stats.deviationRate, tolerableDeviationRate.value)
    })
  }

  function getPointConclusion(ctrlIndex: number): ComputedRef<ControlPointConclusion | null> {
    return computed(() => {
      const id = generateCControlItemId(cycleNum.value, 'ctrl', ctrlIndex, undefined, 'conclusion')
      return (getVal(id).conclusion as ControlPointConclusion | null) || null
    })
  }

  function isPointConclusionOverridden(ctrlIndex: number): ComputedRef<boolean> {
    return computed(() => {
      const id = generateCControlItemId(cycleNum.value, 'ctrl', ctrlIndex, undefined, 'override')
      return getVal(id).conclusion === 'Y'
    })
  }

  function setPointConclusion(ctrlIndex: number, conclusion: ControlPointConclusion, overrideReason?: string): void {
    const conclusionId = generateCControlItemId(cycleNum.value, 'ctrl', ctrlIndex, undefined, 'conclusion')
    const overrideId = generateCControlItemId(cycleNum.value, 'ctrl', ctrlIndex, undefined, 'override')
    const suggested = suggestPointConclusion(ctrlIndex).value
    const isOverride = suggested !== null && conclusion !== suggested

    const items: ChecklistItem[] = [setLocal(conclusionId, conclusion)]
    if (isOverride && overrideReason) {
      items.push(setLocal(overrideId, 'Y', overrideReason))
    } else if (!isOverride) {
      items.push(setLocal(overrideId, null, null))
    }
    saveImmediate(items)
  }

  // ─── Cycle Conclusion ──────────────────────────────────────────────────────

  const suggestCycleConclusionComputed: ComputedRef<CycleConclusion | null> = computed(() => {
    const count = getControlPointCount()
    const conclusions: (ControlPointConclusion | null)[] = []
    for (let m = 1; m <= count; m++) {
      conclusions.push(getPointConclusion(m).value)
    }
    return suggestCycleConclusion(conclusions)
  })

  const cycleConclusion: ComputedRef<CycleConclusion | null> = computed(() => {
    const id = generateCControlItemId(cycleNum.value, 'cycle-conclusion')
    return (getVal(id).conclusion as CycleConclusion | null) || null
  })

  const isCycleConclusionOverridden: ComputedRef<boolean> = computed(() => {
    const id = generateCControlItemId(cycleNum.value, 'cycle-conclusion-override')
    return getVal(id).conclusion === 'Y'
  })

  function setCycleConclusion(conclusion: CycleConclusion, overrideReason?: string): void {
    const conclusionId = generateCControlItemId(cycleNum.value, 'cycle-conclusion')
    const overrideId = generateCControlItemId(cycleNum.value, 'cycle-conclusion-override')
    const suggested = suggestCycleConclusionComputed.value
    const isOverride = suggested !== null && conclusion !== suggested

    const oldConclusion = cycleConclusion.value
    const items: ChecklistItem[] = [setLocal(conclusionId, conclusion)]
    if (isOverride && overrideReason) {
      items.push(setLocal(overrideId, 'Y', overrideReason))
    } else if (!isOverride) {
      items.push(setLocal(overrideId, null, null))
    }
    saveImmediate(items)

    // EventBus publish
    if (oldConclusion !== conclusion) {
      publishTestConcluded(oldConclusion, conclusion)
    }
  }

  // ─── B23 Reference ─────────────────────────────────────────────────────────

  const b23ControlPoints = ref<B23ControlPointRef[]>([])

  async function loadB23Reference(): Promise<void> {
    // B23 control points are loaded from B23 data
    // For now, provide empty — can be filled from API or cross-workpaper reference
    b23ControlPoints.value = []
  }

  // ─── Review ────────────────────────────────────────────────────────────────

  const isReviewed: ComputedRef<boolean> = computed(() => {
    const id = generateCControlItemId(cycleNum.value, 'review-sign')
    return getVal(id).conclusion === 'Y'
  })

  const isReadonly: ComputedRef<boolean> = computed(() => {
    return externalReadonly.value || isReviewed.value
  })

  const canReview: ComputedRef<boolean> = computed(() => {
    const count = getControlPointCount()
    if (count === 0) return false
    // All control points must have a conclusion
    for (let m = 1; m <= count; m++) {
      if (!getPointConclusion(m).value) return false
    }
    // Cycle conclusion must be set
    if (!cycleConclusion.value) return false
    return true
  })

  const pendingItems: ComputedRef<string[]> = computed(() => {
    const items: string[] = []
    const count = getControlPointCount()
    for (let m = 1; m <= count; m++) {
      if (!getPointConclusion(m).value) {
        items.push(`控制点 ${m}: 需填写结论`)
      }
    }
    if (!cycleConclusion.value) {
      items.push('需选择循环级整体结论')
    }
    return items
  })

  const reviewInfo: ComputedRef<{ reviewer: string; date: string } | null> = computed(() => {
    const id = generateCControlItemId(cycleNum.value, 'review-sign')
    const r = getVal(id)
    if (r.conclusion !== 'Y') return null
    return { reviewer: r.remark || '', date: r.wp_ref || '' }
  })

  async function doReview(): Promise<void> {
    if (!canReview.value) return
    const id = generateCControlItemId(cycleNum.value, 'review-sign')
    const now = new Date().toISOString().slice(0, 10)
    const item = setLocal(id, 'Y', '现场经理', now)
    await saveImmediate([item])
  }

  async function startAmendment(reason: string): Promise<void> {
    if (!reason.trim()) return
    // Clear review sign
    const reviewId = generateCControlItemId(cycleNum.value, 'review-sign')
    const items: ChecklistItem[] = [setLocal(reviewId, null, null, null)]
    // Record amendment reason (find next round number)
    let round = 1
    while (getVal(generateCControlItemId(cycleNum.value, 'amend', undefined, undefined, undefined, round)).remark) {
      round++
    }
    const amendId = generateCControlItemId(cycleNum.value, 'amend', undefined, undefined, undefined, round)
    items.push(setLocal(amendId, null, reason))
    await saveImmediate(items)
  }

  // ─── EventBus ──────────────────────────────────────────────────────────────

  function publishTestConcluded(oldConclusion: CycleConclusion | null, newConclusion: CycleConclusion): void {
    if (oldConclusion === newConclusion) return
    const config = CYCLE_CONFIG[cycleNum.value]
    if (!config) return

    const count = getControlPointCount()
    let effectiveCount = 0
    let deviationAcceptableCount = 0
    let ineffectiveCount = 0
    let maxDeviationRate = 0
    for (let m = 1; m <= count; m++) {
      const c = getPointConclusion(m).value
      if (c === '控制有效运行') effectiveCount++
      else if (c === '控制存在偏差但可接受') deviationAcceptableCount++
      else if (c === '控制无效') ineffectiveCount++
      const stats = getDeviationStats(m).value
      if (stats.deviationRate !== null && stats.deviationRate > maxDeviationRate) {
        maxDeviationRate = stats.deviationRate
      }
    }

    const payload: TestConcludedPayload = {
      wpCode: wpCode.value,
      cycleName: config.name,
      conclusion: newConclusion,
      deviationSummary: {
        totalControlPoints: count,
        effectiveCount,
        deviationAcceptableCount,
        ineffectiveCount,
        maxDeviationRate,
      },
    }

    try {
      window.dispatchEvent(new CustomEvent('control:test-concluded', { detail: payload }))
    } catch {
      console.warn('[CControlTest] EventBus publish control:test-concluded failed')
    }
  }

  // ─── Linkage Info ──────────────────────────────────────────────────────────

  const linkageInfo: ComputedRef<CControlLinkageInfo> = computed(() => {
    const config = CYCLE_CONFIG[cycleNum.value] || CYCLE_CONFIG[2]
    return {
      b23WpCode: 'B23',
      b23ProcessNum: config.b23ProcessNum,
      b50WpCode: 'B50',
      targetCycleCode: config.targetCycle,
      targetCycleName: config.targetCycleName,
      needsExtendedProcedures: cycleConclusion.value === '控制失效',
    }
  })

  const cycleName: ComputedRef<string> = computed(() => {
    const config = CYCLE_CONFIG[cycleNum.value]
    return config?.name || `循环 ${cycleNum.value}`
  })

  const targetProcedureCycle: ComputedRef<string> = computed(() => {
    const config = CYCLE_CONFIG[cycleNum.value]
    return config?.targetCycle || ''
  })

  // ─── Control Points (computed card list) ───────────────────────────────────

  const controlPoints: ComputedRef<ControlPointTest[]> = computed(() => {
    const count = getControlPointCount()
    const points: ControlPointTest[] = []
    for (let m = 1; m <= count; m++) {
      const ctrlId = getVal(generateCControlItemId(cycleNum.value, 'ctrl', m, undefined, 'id')).remark || `ctrl-${m}`
      const objective = getVal(generateCControlItemId(cycleNum.value, 'ctrl', m, undefined, 'objective')).remark || ''
      const methodsRaw = getVal(generateCControlItemId(cycleNum.value, 'ctrl', m, undefined, 'methods')).conclusion || ''
      const testMethods: TestMethod[] = methodsRaw ? (methodsRaw.split(',').filter(Boolean) as TestMethod[]) : []
      const samples = getSamples(m).value
      const stats = calculateDeviationStats(samples, tolerableDeviationRate.value)
      const conclusion = getPointConclusion(m).value
      const suggested = suggestControlPointConclusion(stats.deviationRate, tolerableDeviationRate.value)
      const overrideId = generateCControlItemId(cycleNum.value, 'ctrl', m, undefined, 'override')
      const overrideVal = getVal(overrideId)
      const conclusionOverridden = overrideVal.conclusion === 'Y'
      const overrideReason = overrideVal.remark || ''

      points.push({
        index: m,
        controlId: ctrlId,
        objective,
        testMethods,
        samples,
        deviationStats: stats,
        conclusion,
        suggestedConclusion: suggested,
        conclusionOverridden,
        overrideReason,
        isFromB23: m <= b23ControlPoints.value.length,
      })
    }
    return points
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // B23 reference
    b23ControlPoints,
    loadB23Reference,
    // Control point card management
    controlPoints,
    expandedCards,
    toggleCard,
    expandAll,
    collapseAll,
    addControlPoint,
    removeControlPoint,
    // Test methods
    setTestMethods,
    // Sample management
    getSamples,
    addSample,
    removeSample,
    addBatchSamples,
    // Sample results
    setSampleResult,
    setDeviationDescription,
    // Deviation stats
    getDeviationStats,
    // Control point conclusion
    suggestPointConclusion,
    getPointConclusion,
    isPointConclusionOverridden,
    setPointConclusion,
    // Tolerable rate
    tolerableDeviationRate,
    setTolerableRate,
    // Cycle conclusion
    suggestCycleConclusion: suggestCycleConclusionComputed,
    cycleConclusion,
    isCycleConclusionOverridden,
    setCycleConclusion,
    // Review
    isReviewed,
    isReadonly,
    canReview,
    pendingItems,
    reviewInfo,
    doReview,
    startAmendment,
    // EventBus
    publishTestConcluded,
    // Linkage
    linkageInfo,
    cycleName,
    targetProcedureCycle,
  }
}

export default useCControlTest
