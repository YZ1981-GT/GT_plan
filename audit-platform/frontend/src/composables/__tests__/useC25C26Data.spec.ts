/**
 * useC25C26Data unit tests
 *
 * Spec: .kiro/specs/c25-c26-internal-audit-info-control/
 * Task: 3.1
 * Requirements: 6.1, 6.2, 6.3, 6.4, 3.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { useC25C26Data } from '../useC25C26Data'

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

function createComposable(readonly = false) {
  const wpId = ref('wp-test-1')
  const projectId = ref('proj-1')
  const isReadonly = ref(readonly)
  return { ...useC25C26Data(wpId, projectId, isReadonly), wpId, projectId, isReadonly }
}

function buildC25Responses() {
  const items: any[] = []
  for (let n = 1; n <= 10; n++) {
    items.push({ item_id: `C25-step-${n}-applicable`, conclusion: n <= 5 ? '是' : '否', remark: null })
    items.push({ item_id: `C25-step-${n}-executor`, conclusion: null, remark: `执行人${n}` })
    items.push({ item_id: `C25-step-${n}-result`, conclusion: null, remark: `说明${n}` })
    items.push({ item_id: `C25-step-${n}-indexRef`, conclusion: null, remark: `A${n}` })
  }
  items.push({ item_id: 'C25-reliance-conclusion', conclusion: '可以利用内部审计工作', remark: null })
  items.push({ item_id: 'C25-reliance-remark', conclusion: null, remark: '利用程度高' })
  return items
}

function buildC26Responses(rowCount = 3) {
  const items: any[] = []
  for (let m = 1; m <= rowCount; m++) {
    items.push({ item_id: `C26-ctrl-${m}-category`, conclusion: '与销售循环相关的控制', remark: null })
    items.push({ item_id: `C26-ctrl-${m}-indexNo`, conclusion: null, remark: `IT-R&R-0${m}` })
    items.push({ item_id: `C26-ctrl-${m}-purpose`, conclusion: null, remark: `测试目的${m}` })
    items.push({ item_id: `C26-ctrl-${m}-plannedTest`, conclusion: null, remark: `计划测试${m}` })
    items.push({ item_id: `C26-ctrl-${m}-walkthrough`, conclusion: null, remark: `穿行${m}` })
    items.push({ item_id: `C26-ctrl-${m}-controlTest`, conclusion: null, remark: `控制测试${m}` })
    items.push({ item_id: `C26-ctrl-${m}-testResult`, conclusion: '未发现例外', remark: null })
    items.push({ item_id: `C26-ctrl-${m}-clientFeedback`, conclusion: null, remark: `反馈${m}` })
    items.push({ item_id: `C26-ctrl-${m}-conclusion`, conclusion: '有效', remark: null })
    items.push({ item_id: `C26-ctrl-${m}-evidence`, conclusion: null, remark: `D2-${m}` })
    items.push({ item_id: `C26-ctrl-${m}-elements`, conclusion: '完整性,准确性', remark: null })
  }
  return items
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useC25C26Data', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockGet.mockReset()
    mockPut.mockReset()
    mockPut.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('selfLoad', () => {
    it('加载 C25 前缀数据并还原 10 步结构', async () => {
      mockGet.mockResolvedValue(buildC25Responses())
      const { selfLoad, c25, loading } = createComposable()

      await selfLoad()

      expect(loading.value).toBe(false)
      expect(c25.value.steps).toHaveLength(10)
      expect(c25.value.steps[0].applicable).toBe('是')
      expect(c25.value.steps[0].executor).toBe('执行人1')
      expect(c25.value.steps[0].result).toBe('说明1')
      expect(c25.value.steps[0].indexRef).toBe('A1')
      expect(c25.value.steps[5].applicable).toBe('否')
      expect(c25.value.conclusion).toBe('可以利用内部审计工作')
      expect(c25.value.remark).toBe('利用程度高')
    })

    it('加载 C26 前缀数据并还原动态行', async () => {
      mockGet.mockResolvedValue(buildC26Responses(3))
      const { selfLoad, c26 } = createComposable()

      await selfLoad()

      expect(c26.value.rows).toHaveLength(3)
      expect(c26.value.rows[0].category).toBe('与销售循环相关的控制')
      expect(c26.value.rows[0].indexNo).toBe('IT-R&R-01')
      expect(c26.value.rows[0].testResult).toBe('未发现例外')
      expect(c26.value.rows[0].conclusion).toBe('有效')
      expect(c26.value.rows[0].elements).toEqual(['完整性', '准确性'])
      expect(c26.value.rows[2].indexNo).toBe('IT-R&R-03')
    })

    it('加载失败时显示警告但不崩溃', async () => {
      mockGet.mockRejectedValue(new Error('network error'))
      const { selfLoad, c25, c26 } = createComposable()

      await selfLoad()

      // State stays at defaults
      expect(c25.value.steps).toHaveLength(10)
      expect(c26.value.rows).toHaveLength(0)
    })

    it('空响应数组时保持默认空状态', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, c25, c26 } = createComposable()

      await selfLoad()

      expect(c25.value.steps[0].applicable).toBeNull()
      expect(c26.value.rows).toHaveLength(0)
    })
  })

  describe('debounceSave (Req 6.2)', () => {
    it('文本字段编辑 2s 后触发 PUT', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, updateC25StepText } = createComposable()
      await selfLoad()

      updateC25StepText(0, 'result', '新说明')

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
      mockGet.mockResolvedValue([])
      const { selfLoad, updateC25StepText } = createComposable()
      await selfLoad()

      updateC25StepText(0, 'result', '第一次')
      vi.advanceTimersByTime(1000)
      updateC25StepText(0, 'result', '第二次')
      vi.advanceTimersByTime(1500)

      expect(mockPut).not.toHaveBeenCalled()

      vi.advanceTimersByTime(500)
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  describe('saveImmediate (Req 6.3)', () => {
    it('枚举变更即时触发 PUT', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, updateC25StepApplicable } = createComposable()
      await selfLoad()

      updateC25StepApplicable(0, '是')
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('C25 结论变更即时保存', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, updateC25Conclusion } = createComposable()
      await selfLoad()

      updateC25Conclusion('不能利用内部审计工作')
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('C26 四要素变更即时保存', async () => {
      mockGet.mockResolvedValue(buildC26Responses(1))
      const { selfLoad, updateC26RowElements } = createComposable()
      await selfLoad()

      updateC26RowElements(0, ['完整性', '授权'])
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('即时保存取消挂起的 debounce', async () => {
      mockGet.mockResolvedValue(buildC26Responses(1))
      const { selfLoad, updateC26RowText, updateC26RowEnum } = createComposable()
      await selfLoad()

      // Start debounce
      updateC26RowText(0, 'purpose', '新目的')
      vi.advanceTimersByTime(1000)

      // Immediate save should cancel debounce and fire PUT
      updateC26RowEnum(0, 'conclusion', '无效')
      await vi.runAllTimersAsync()

      // Should fire once (immediate), not twice (debounce + immediate)
      expect(mockPut).toHaveBeenCalledTimes(1)
    })
  })

  describe('C26 addRow / removeRow (Req 3.3)', () => {
    it('addRow 增加新行并即时保存', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, addRow, c26 } = createComposable()
      await selfLoad()

      addRow('IT-R&R-NEW')
      await vi.runAllTimersAsync()

      expect(c26.value.rows).toHaveLength(1)
      expect(c26.value.rows[0].indexNo).toBe('IT-R&R-NEW')
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('removeRow 删除指定行并即时保存', async () => {
      mockGet.mockResolvedValue(buildC26Responses(3))
      const { selfLoad, removeRow, c26 } = createComposable()
      await selfLoad()

      expect(c26.value.rows).toHaveLength(3)
      removeRow(1) // 删除第2行
      await vi.runAllTimersAsync()

      expect(c26.value.rows).toHaveLength(2)
      expect(c26.value.rows[0].indexNo).toBe('IT-R&R-01')
      expect(c26.value.rows[1].indexNo).toBe('IT-R&R-03')
      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('removeRow 无效索引不操作', async () => {
      mockGet.mockResolvedValue(buildC26Responses(2))
      const { selfLoad, removeRow, c26 } = createComposable()
      await selfLoad()

      removeRow(-1)
      removeRow(99)
      await vi.runAllTimersAsync()

      expect(c26.value.rows).toHaveLength(2)
      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  describe('readonly guard', () => {
    it('readonly 时 debounceSave 不触发 PUT', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, updateC25StepText } = createComposable(true)
      await selfLoad()

      updateC25StepText(0, 'result', '不该保存')
      vi.advanceTimersByTime(3000)
      await vi.runAllTimersAsync()

      expect(mockPut).not.toHaveBeenCalled()
    })

    it('readonly 时 addRow 不生效', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, addRow, c26 } = createComposable(true)
      await selfLoad()

      addRow('不该添加')
      expect(c26.value.rows).toHaveLength(0)
    })

    it('readonly 时 removeRow 不生效', async () => {
      mockGet.mockResolvedValue(buildC26Responses(2))
      const { selfLoad, removeRow, c26 } = createComposable(true)
      await selfLoad()

      removeRow(0)
      expect(c26.value.rows).toHaveLength(2)
    })
  })

  describe('flushPendingSaves', () => {
    it('flush 触发挂起的保存', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, updateC25StepText, flushPendingSaves } = createComposable()
      await selfLoad()

      updateC25StepText(0, 'result', '挂起')
      // Don't advance timers — pending
      flushPendingSaves()
      await vi.runAllTimersAsync()

      expect(mockPut).toHaveBeenCalledTimes(1)
    })

    it('无挂起时 flush 不触发 PUT', async () => {
      mockGet.mockResolvedValue([])
      const { selfLoad, flushPendingSaves } = createComposable()
      await selfLoad()

      flushPendingSaves()
      await vi.runAllTimersAsync()

      expect(mockPut).not.toHaveBeenCalled()
    })
  })

  describe('serializeAll 往返一致性', () => {
    it('序列化后包含所有 C25 item_id', async () => {
      mockGet.mockResolvedValue(buildC25Responses())
      const { selfLoad, serializeAll } = createComposable()
      await selfLoad()

      const items = serializeAll()
      const c25Items = items.filter(i => i.item_id.startsWith('C25-'))

      // 10 steps × 4 fields + conclusion + remark = 42
      expect(c25Items).toHaveLength(42)
      expect(c25Items.find(i => i.item_id === 'C25-step-1-applicable')?.conclusion).toBe('是')
      expect(c25Items.find(i => i.item_id === 'C25-reliance-conclusion')?.conclusion).toBe('可以利用内部审计工作')
    })

    it('序列化后包含所有 C26 item_id', async () => {
      mockGet.mockResolvedValue(buildC26Responses(2))
      const { selfLoad, serializeAll } = createComposable()
      await selfLoad()

      const items = serializeAll()
      const c26Items = items.filter(i => i.item_id.startsWith('C26-'))

      // 2 rows × 11 fields = 22
      expect(c26Items).toHaveLength(22)
      expect(c26Items.find(i => i.item_id === 'C26-ctrl-1-category')?.conclusion).toBe('与销售循环相关的控制')
      expect(c26Items.find(i => i.item_id === 'C26-ctrl-1-elements')?.conclusion).toBe('完整性,准确性')
    })
  })

  describe('error handling (Req 6.5)', () => {
    it('PUT 失败时显示错误但保留本地状态', async () => {
      mockGet.mockResolvedValue(buildC25Responses())
      mockPut.mockRejectedValue(new Error('500 Internal Server Error'))
      const { selfLoad, updateC25Conclusion, c25 } = createComposable()
      await selfLoad()

      updateC25Conclusion('不能利用内部审计工作')
      await vi.runAllTimersAsync()

      // Local state preserved
      expect(c25.value.conclusion).toBe('不能利用内部审计工作')
    })

    it('请求取消(ERR_CANCELED)不显示错误', async () => {
      mockGet.mockResolvedValue([])
      const cancelErr = new Error('canceled')
      ;(cancelErr as any).code = 'ERR_CANCELED'
      mockPut.mockRejectedValue(cancelErr)
      const { selfLoad, updateC25Conclusion } = createComposable()
      await selfLoad()

      // Reset mock call count before the action under test
      const { ElMessage } = await import('element-plus')
      ;(ElMessage.error as any).mockClear()

      updateC25Conclusion('可以部分利用内部审计工作')
      await vi.runAllTimersAsync()

      expect(ElMessage.error).not.toHaveBeenCalled()
    })
  })
})
