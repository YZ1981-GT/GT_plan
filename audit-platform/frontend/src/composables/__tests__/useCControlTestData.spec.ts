/**
 * useCControlTestData unit tests
 *
 * Spec: .kiro/specs/c-control-test-refresh/
 * Task: 3.3
 * Requirements: 8.1, 8.2, 8.3, 2.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useCControlTestData, extractCycleNumber } from '../useCControlTestData'
import type { ChecklistResponseItem } from '../useCControlTestData'

// ─── Mock api ────────────────────────────────────────────────────────────────

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))

// ─── Test helpers ────────────────────────────────────────────────────────────

function createComposable(wpCode = 'C5', readonly = false) {
  const wpId = ref('wp-test-1')
  const projectId = ref('proj-1')
  const wpCodeRef = ref(wpCode)
  const isReadonly = ref(readonly)
  return {
    ...useCControlTestData(wpId, projectId, wpCodeRef, isReadonly),
    wpId, projectId, wpCodeRef, isReadonly,
  }
}

/** Build summary responses for C5 with `rowCount` rows */
function buildSummaryResponses(rowCount = 2): ChecklistResponseItem[] {
  const items: ChecklistResponseItem[] = []
  for (let m = 1; m <= rowCount; m++) {
    items.push({ item_id: `C5-sum-${m}-subProcess`, conclusion: null, remark: `子流程${m}` })
    items.push({ item_id: `C5-sum-${m}-controlId`, conclusion: null, remark: `CTRL-${m}` })
    items.push({ item_id: `C5-sum-${m}-controlName`, conclusion: null, remark: `控制${m}` })
    items.push({ item_id: `C5-sum-${m}-description`, conclusion: null, remark: `描述${m}` })
    items.push({ item_id: `C5-sum-${m}-affectedItems`, conclusion: null, remark: `账户${m}` })
    items.push({ item_id: `C5-sum-${m}-assertion`, conclusion: '完整性', remark: null })
    items.push({ item_id: `C5-sum-${m}-attribute`, conclusion: '人工', remark: null })
    items.push({ item_id: `C5-sum-${m}-frequency`, conclusion: '每月', remark: null })
    items.push({ item_id: `C5-sum-${m}-relatedRisk`, conclusion: null, remark: `风险${m}` })
    items.push({ item_id: `C5-sum-${m}-testMethod`, conclusion: '检查', remark: null })
    items.push({ item_id: `C5-sum-${m}-sampleSize`, conclusion: '10', remark: null })
    items.push({ item_id: `C5-sum-${m}-hasDeviation`, conclusion: '否', remark: null })
    items.push({ item_id: `C5-sum-${m}-remediation`, conclusion: null, remark: '' })
    items.push({ item_id: `C5-sum-${m}-defect`, conclusion: null, remark: '' })
    items.push({ item_id: `C5-sum-${m}-indexRef`, conclusion: null, remark: `C5-1-${m}` })
  }
  return items
}

/** Build ctrl page responses for C5 */
function buildCtrlPageResponses(rowCount = 2, samplesPerPage = 2): ChecklistResponseItem[] {
  const items: ChecklistResponseItem[] = []
  for (let m = 1; m <= rowCount; m++) {
    items.push({ item_id: `C5-ctrl-${m}-attribute`, conclusion: '人工', remark: null })
    items.push({ item_id: `C5-ctrl-${m}-frequency`, conclusion: '每月', remark: null })
    items.push({ item_id: `C5-ctrl-${m}-relatedRisk`, conclusion: '高', remark: null })
    items.push({ item_id: `C5-ctrl-${m}-testMethod`, conclusion: '检查', remark: null })
    items.push({ item_id: `C5-ctrl-${m}-testProcedure`, conclusion: null, remark: `程序${m}` })
    items.push({ item_id: `C5-ctrl-${m}-populationDef`, conclusion: null, remark: `总体${m}` })
    items.push({ item_id: `C5-ctrl-${m}-populationSource`, conclusion: null, remark: `来源${m}` })
    items.push({ item_id: `C5-ctrl-${m}-sampleSize`, conclusion: '10', remark: null })
    items.push({ item_id: `C5-ctrl-${m}-samplingMethod`, conclusion: null, remark: '随机' })
    items.push({ item_id: `C5-ctrl-${m}-samplingProcess`, conclusion: null, remark: `过程${m}` })
    items.push({ item_id: `C5-ctrl-${m}-deviationDef`, conclusion: null, remark: `偏差定义${m}` })
    for (let s = 1; s <= samplesPerPage; s++) {
      items.push({ item_id: `C5-ctrl-${m}-sample-${s}-description`, conclusion: null, remark: `样本${m}-${s}` })
      items.push({ item_id: `C5-ctrl-${m}-sample-${s}-result`, conclusion: s === 1 ? '有效' : '偏差', remark: null })
    }
  }
  return items
}

/** Build deviation state responses for C5 */
function buildDeviationResponses(rowCount = 2): ChecklistResponseItem[] {
  const items: ChecklistResponseItem[] = []
  for (let m = 1; m <= rowCount; m++) {
    items.push({ item_id: `C5-dev-${m}-step1`, conclusion: '是', remark: null })
    items.push({ item_id: `C5-dev-${m}-step2`, conclusion: '随机性偏差', remark: null })
    items.push({ item_id: `C5-dev-${m}-step3`, conclusion: '扩大样本量', remark: null })
    items.push({ item_id: `C5-dev-${m}-step4`, conclusion: '否', remark: null })
    items.push({ item_id: `C5-dev-${m}-step6`, conclusion: null, remark: null })
    items.push({ item_id: `C5-dev-${m}-conclusion`, conclusion: '控制有效', remark: null })
  }
  return items
}

function buildCycleConclusionResponse(): ChecklistResponseItem[] {
  return [{ item_id: 'C5-cycle-conclusion', conclusion: '控制总体有效', remark: null }]
}

function buildAllResponses(): ChecklistResponseItem[] {
  return [
    ...buildSummaryResponses(2),
    ...buildCtrlPageResponses(2, 2),
    ...buildDeviationResponses(2),
    ...buildCycleConclusionResponse(),
  ]
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useCControlTestData', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('extractCycleNumber', () => {
    it('从 wpCode 提取循环编号', () => {
      expect(extractCycleNumber('C2')).toBe(2)
      expect(extractCycleNumber('C10')).toBe(10)
      expect(extractCycleNumber('C15')).toBe(15)
    })

    it('无效 wpCode 返回 0', () => {
      expect(extractCycleNumber('')).toBe(0)
      expect(extractCycleNumber('D1')).toBe(0)
      expect(extractCycleNumber('ABC')).toBe(0)
    })
  })

  describe('selfLoad', () => {
    it('加载汇总表数据并还原 summaryRows', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(2))
      const { selfLoad, state, loading } = createComposable('C5')

      await selfLoad()

      expect(loading.value).toBe(false)
      expect(state.value.cycleNumber).toBe(5)
      expect(state.value.summaryRows).toHaveLength(2)
      expect(state.value.summaryRows[0].subProcess).toBe('子流程1')
      expect(state.value.summaryRows[0].controlId).toBe('CTRL-1')
      expect(state.value.summaryRows[0].assertion).toBe('完整性')
      expect(state.value.summaryRows[0].attribute).toBe('人工')
      expect(state.value.summaryRows[0].frequency).toBe('每月')
      expect(state.value.summaryRows[0].sampleSize).toBe(10)
      expect(state.value.summaryRows[0].hasDeviation).toBe('否')
    })

    it('加载子页数据含样本', async () => {
      mockGet.mockResolvedValue(buildCtrlPageResponses(1, 3))
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.controlPages).toHaveLength(1)
      expect(state.value.controlPages[0].testProcedure).toBe('程序1')
      expect(state.value.controlPages[0].sampleSize).toBe(10)
      expect(state.value.controlPages[0].samples).toHaveLength(3)
      expect(state.value.controlPages[0].samples[0].description).toBe('样本1-1')
      expect(state.value.controlPages[0].samples[0].result).toBe('有效')
      expect(state.value.controlPages[0].samples[1].result).toBe('偏差')
    })

    it('加载偏差决策树数据', async () => {
      mockGet.mockResolvedValue(buildDeviationResponses(2))
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.deviationStates).toHaveLength(2)
      expect(state.value.deviationStates[0].step1).toBe('是')
      expect(state.value.deviationStates[0].step2).toBe('随机性偏差')
      expect(state.value.deviationStates[0].step3).toBe('扩大样本量')
      expect(state.value.deviationStates[0].step4).toBe('否')
      expect(state.value.deviationStates[0].step6).toBeNull()
    })

    it('加载循环结论', async () => {
      mockGet.mockResolvedValue(buildCycleConclusionResponse())
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.cycleConclusion).toBe('控制总体有效')
    })

    it('综合加载所有数据保持一致性', async () => {
      mockGet.mockResolvedValue(buildAllResponses())
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.summaryRows).toHaveLength(2)
      expect(state.value.controlPages).toHaveLength(2)
      expect(state.value.deviationStates).toHaveLength(2)
      expect(state.value.cycleConclusion).toBe('控制总体有效')
    })

    it('加载失败时显示警告但不崩溃', async () => {
      mockGet.mockRejectedValue(new Error('network error'))
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.summaryRows).toHaveLength(0)
      expect(state.value.controlPages).toHaveLength(0)
    })

    it('空响应保持默认空状态', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.summaryRows).toHaveLength(0)
      expect(state.value.cycleConclusion).toBe('')
    })

    it('不同循环编号只解析匹配前缀', async () => {
      const items: ChecklistResponseItem[] = [
        { item_id: 'C5-sum-1-controlName', conclusion: null, remark: '正确' },
        { item_id: 'C3-sum-1-controlName', conclusion: null, remark: '错误循环' },
      ]
      mockGet.mockResolvedValue(items)
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.summaryRows).toHaveLength(1)
      expect(state.value.summaryRows[0].controlName).toBe('正确')
    })
  })

  describe('debounceSave (Req 8.2)', () => {
    it('文本字段编辑 2s 后触发 PUT', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, updateSummaryText } = createComposable('C5')
      await selfLoad()

      updateSummaryText(0, 'description', '新描述')

      expect(mockPut).not.toHaveBeenCalled()
      vi.advanceTimersByTime(2000)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
      expect(mockPut).toHaveBeenCalledWith(
        '/api/workpapers/wp-test-1/checklist-responses',
        expect.objectContaining({ project_id: 'proj-1' }),
      )
    })

    it('连续编辑重置 debounce 计时器', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, updateSummaryText } = createComposable('C5')
      await selfLoad()

      updateSummaryText(0, 'description', '第一次')
      vi.advanceTimersByTime(1000)
      updateSummaryText(0, 'description', '第二次')
      vi.advanceTimersByTime(1500)

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  describe('saveImmediate (Req 8.2)', () => {
    it('枚举变更即时触发 PUT', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, updateSummaryEnum } = createComposable('C5')
      await selfLoad()

      updateSummaryEnum(0, 'assertion', '存在')
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('决策树步骤变更即时保存', async () => {
      mockGet.mockResolvedValue(buildDeviationResponses(1))
      const { selfLoad, updateDeviationStep } = createComposable('C5')
      await selfLoad()

      updateDeviationStep(0, 'step1', '否')
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('循环结论变更即时保存', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, updateCycleConclusion } = createComposable('C5')
      await selfLoad()

      updateCycleConclusion('控制失效')
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('即时保存取消挂起的 debounce', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, updateSummaryText, updateSummaryEnum } = createComposable('C5')
      await selfLoad()

      updateSummaryText(0, 'description', '新描述')
      vi.advanceTimersByTime(1000)
      updateSummaryEnum(0, 'attribute', '自动')
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  describe('addControlPoint / removeControlPoint (Req 2.3)', () => {
    it('addControlPoint 增加新控制点并即时保存', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, addControlPoint, state } = createComposable('C5')
      await selfLoad()

      addControlPoint('新控制点')
      await vi.runAllTimersAsync()

      expect(state.value.summaryRows).toHaveLength(1)
      expect(state.value.summaryRows[0].controlName).toBe('新控制点')
      expect(state.value.controlPages).toHaveLength(1)
      expect(state.value.deviationStates).toHaveLength(1)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('addControlPoint 空名称不生效', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, addControlPoint, state } = createComposable('C5')
      await selfLoad()

      addControlPoint('')
      addControlPoint('   ')

      expect(state.value.summaryRows).toHaveLength(0)
      expect(mockPut).not.toHaveBeenCalled()
    })

    it('removeControlPoint 删除控制点并即时保存', async () => {
      mockGet.mockResolvedValue(buildAllResponses())
      const { selfLoad, removeControlPoint, state } = createComposable('C5')
      await selfLoad()

      expect(state.value.summaryRows).toHaveLength(2)
      removeControlPoint(0)
      await vi.runAllTimersAsync()

      expect(state.value.summaryRows).toHaveLength(1)
      expect(state.value.controlPages).toHaveLength(1)
      expect(state.value.deviationStates).toHaveLength(1)
      expect(state.value.summaryRows[0].controlId).toBe('CTRL-2')
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('removeControlPoint 无效索引不操作', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(2))
      const { selfLoad, removeControlPoint, state } = createComposable('C5')
      await selfLoad()

      removeControlPoint(-1)
      removeControlPoint(99)
      await vi.runAllTimersAsync()

      expect(state.value.summaryRows).toHaveLength(2)
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  describe('readonly guard (Req 8.3)', () => {
    it('readonly 时 debounceSave 不触发 PUT', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, updateSummaryText } = createComposable('C5', true)
      await selfLoad()

      updateSummaryText(0, 'description', '不该保存')
      vi.advanceTimersByTime(3000)
      await vi.runAllTimersAsync()

      expect(mockPut).not.toHaveBeenCalled()
    })

    it('readonly 时 addControlPoint 不生效', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, addControlPoint, state } = createComposable('C5', true)
      await selfLoad()

      addControlPoint('不该添加')
      expect(state.value.summaryRows).toHaveLength(0)
    })

    it('readonly 时 removeControlPoint 不生效', async () => {
      mockGet.mockResolvedValue(buildAllResponses())
      const { selfLoad, removeControlPoint, state } = createComposable('C5', true)
      await selfLoad()

      removeControlPoint(0)
      expect(state.value.summaryRows).toHaveLength(2)
    })

    it('readonly 时 updateDeviationStep 不生效', async () => {
      mockGet.mockResolvedValue(buildDeviationResponses(1))
      const { selfLoad, updateDeviationStep, state } = createComposable('C5', true)
      await selfLoad()

      updateDeviationStep(0, 'step1', '否')
      expect(state.value.deviationStates[0].step1).toBe('是')
    })
  })

  describe('flushPendingSaves', () => {
    it('flush 触发挂起的保存', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, updateSummaryText, flushPendingSaves } = createComposable('C5')
      await selfLoad()

      updateSummaryText(0, 'description', '挂起')
      flushPendingSaves()
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('无挂起时 flush 不触发 PUT', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, flushPendingSaves } = createComposable('C5')
      await selfLoad()

      flushPendingSaves()
      await vi.runAllTimersAsync()

      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  describe('serializeAll 往返一致性 (Req 8.1)', () => {
    it('序列化后包含所有 C5- 前缀 item_id', async () => {
      mockGet.mockResolvedValue(buildAllResponses())
      const { selfLoad, serializeAll } = createComposable('C5')
      await selfLoad()

      const items = serializeAll()

      // All items should be C5- prefixed
      expect(items.every(i => i.item_id.startsWith('C5-'))).toBe(true)

      // Check summary items: 2 rows × 15 fields = 30
      const sumItems = items.filter(i => i.item_id.match(/^C5-sum-/))
      expect(sumItems).toHaveLength(30)

      // Check ctrl items exist
      const ctrlItems = items.filter(i => i.item_id.match(/^C5-ctrl-/))
      expect(ctrlItems.length).toBeGreaterThan(0)

      // Check deviation items: 2 × (5 steps + 1 conclusion) = 12
      const devItems = items.filter(i => i.item_id.match(/^C5-dev-/))
      expect(devItems).toHaveLength(12)

      // Check cycle conclusion
      const cycleItem = items.find(i => i.item_id === 'C5-cycle-conclusion')
      expect(cycleItem).toBeDefined()
      expect(cycleItem!.conclusion).toBe('控制总体有效')
    })

    it('汇总表枚举字段存 conclusion，文本存 remark', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      const { selfLoad, serializeAll } = createComposable('C5')
      await selfLoad()

      const items = serializeAll()
      const assertionItem = items.find(i => i.item_id === 'C5-sum-1-assertion')
      expect(assertionItem?.conclusion).toBe('完整性')
      expect(assertionItem?.remark).toBeNull()

      const descItem = items.find(i => i.item_id === 'C5-sum-1-description')
      expect(descItem?.conclusion).toBeNull()
      expect(descItem?.remark).toBe('描述1')
    })

    it('样本结果正确序列化', async () => {
      mockGet.mockResolvedValue(buildCtrlPageResponses(1, 2))
      const { selfLoad, serializeAll } = createComposable('C5')
      await selfLoad()

      const items = serializeAll()
      const sampleResult = items.find(i => i.item_id === 'C5-ctrl-1-sample-1-result')
      expect(sampleResult?.conclusion).toBe('有效')

      const sampleDesc = items.find(i => i.item_id === 'C5-ctrl-1-sample-1-description')
      expect(sampleDesc?.remark).toBe('样本1-1')
    })
  })

  describe('sample management', () => {
    it('addSample 添加新样本行', async () => {
      mockGet.mockResolvedValue(buildCtrlPageResponses(1, 1))
      const { selfLoad, addSample, state } = createComposable('C5')
      await selfLoad()

      expect(state.value.controlPages[0].samples).toHaveLength(1)
      addSample(0)
      await vi.runAllTimersAsync()

      expect(state.value.controlPages[0].samples).toHaveLength(2)
      expect(state.value.controlPages[0].samples[1].result).toBeNull()
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('removeSample 删除样本行', async () => {
      mockGet.mockResolvedValue(buildCtrlPageResponses(1, 3))
      const { selfLoad, removeSample, state } = createComposable('C5')
      await selfLoad()

      removeSample(0, 1) // 删除第 2 个样本
      await vi.runAllTimersAsync()

      expect(state.value.controlPages[0].samples).toHaveLength(2)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('updateSampleResult 即时保存', async () => {
      mockGet.mockResolvedValue(buildCtrlPageResponses(1, 2))
      const { selfLoad, updateSampleResult, state } = createComposable('C5')
      await selfLoad()

      updateSampleResult(0, 0, '偏差')
      await vi.runAllTimersAsync()

      expect(state.value.controlPages[0].samples[0].result).toBe('偏差')
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  describe('error handling (Req 8.6)', () => {
    it('PUT 失败时显示错误但保留本地状态', async () => {
      mockGet.mockResolvedValue(buildSummaryResponses(1))
      mockPut.mockRejectedValue(new Error('500 Internal Server Error'))
      const { selfLoad, updateCycleConclusion, state } = createComposable('C5')
      await selfLoad()

      updateCycleConclusion('新结论')
      await vi.runAllTimersAsync()

      expect(state.value.cycleConclusion).toBe('新结论')
    })

    it('请求取消(ERR_CANCELED)不显示错误', async () => {
      mockGet.mockResolvedValue([])
      const cancelErr = new Error('canceled')
      ;(cancelErr as any).code = 'ERR_CANCELED'
      mockPut.mockRejectedValue(cancelErr)
      const { selfLoad, updateCycleConclusion } = createComposable('C5')
      await selfLoad()

      const { ElMessage } = await import('element-plus')
      ;(ElMessage.error as any).mockClear()

      updateCycleConclusion('新结论')
      await vi.runAllTimersAsync()

      expect(ElMessage.error).not.toHaveBeenCalled()
    })
  })

  describe('C{n}- backward compatibility (Req 1.5, 8.1)', () => {
    it('旧格式 C{n}-ctrl-{i}-* 数据正确解析到 controlPages', async () => {
      // Old format uses same ctrl pattern
      const oldItems: ChecklistResponseItem[] = [
        { item_id: 'C5-ctrl-1-testProcedure', conclusion: null, remark: '旧程序' },
        { item_id: 'C5-ctrl-1-populationDef', conclusion: null, remark: '旧总体' },
        { item_id: 'C5-ctrl-1-attribute', conclusion: '自动', remark: null },
      ]
      mockGet.mockResolvedValue(oldItems)
      const { selfLoad, state } = createComposable('C5')

      await selfLoad()

      expect(state.value.controlPages).toHaveLength(1)
      expect(state.value.controlPages[0].testProcedure).toBe('旧程序')
      expect(state.value.controlPages[0].populationDef).toBe('旧总体')
      expect(state.value.controlPages[0].attribute).toBe('自动')
    })
  })
})
