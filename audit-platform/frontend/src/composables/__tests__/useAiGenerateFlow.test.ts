/**
 * useAiGenerateFlow 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 9.3, 9.4, 9.5, 9.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useAiGenerateFlow } from '../useAiGenerateFlow'
import { buildAiContext } from '../buildAiContext'

describe('useAiGenerateFlow', () => {
  const mockHttpPost = vi.fn()

  function createFlow(initialContent = '') {
    const wpId = ref('wp-123')
    const targetModel = ref(initialContent)
    return {
      flow: useAiGenerateFlow({
        wpId,
        targetModel,
        section: 'test-section',
        httpPost: mockHttpPost,
      }),
      wpId,
      targetModel,
    }
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('状态机', () => {
    it('初始阶段为 IDLE', () => {
      const { flow } = createFlow()
      expect(flow.phase.value).toBe('IDLE')
      expect(flow.isGenerating.value).toBe(false)
      expect(flow.isPreviewing.value).toBe(false)
    })

    it('generate 转换到 GENERATING 再到 PREVIEWING', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: 'AI结果' } } })
      const { flow } = createFlow()

      const generatePromise = flow.generate(buildAiContext('D2'))

      // 应立即进入 GENERATING
      expect(flow.phase.value).toBe('GENERATING')
      expect(flow.isGenerating.value).toBe(true)

      await generatePromise

      // 生成完成进入 PREVIEWING
      expect(flow.phase.value).toBe('PREVIEWING')
      expect(flow.isPreviewing.value).toBe(true)
      expect(flow.generatedContent.value).toBe('AI结果')
    })

    it('confirm 从 PREVIEWING 转换到 CONFIRMED', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: '结论内容' } } })
      const { flow, targetModel } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.phase.value).toBe('PREVIEWING')

      flow.confirm()
      expect(flow.phase.value).toBe('CONFIRMED')
      expect(targetModel.value).toBe('结论内容')
    })

    it('cancel 从任意阶段回到 IDLE', async () => {
      mockHttpPost.mockResolvedValue({ data: { content: 'test' } })
      const { flow } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.phase.value).toBe('PREVIEWING')

      flow.cancel()
      expect(flow.phase.value).toBe('IDLE')
      expect(flow.generatedContent.value).toBe('')
    })

    it('生成失败回到 IDLE', async () => {
      mockHttpPost.mockRejectedValue(new Error('网络错误'))
      const { flow } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.phase.value).toBe('IDLE')
      expect(flow.error.value).toBe('网络错误')
    })
  })

  describe('Req 9.4: 确认后立即填入无额外延迟', () => {
    it('confirm 同步更新 targetModel', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: '新内容' } } })
      const { flow, targetModel } = createFlow('旧内容')

      await flow.generate(buildAiContext('D2'))
      flow.confirm()

      // 同步检查：立即生效，无 nextTick / setTimeout
      expect(targetModel.value).toBe('新内容')
    })
  })

  describe('Req 9.5: diff 预览不覆盖已填内容', () => {
    it('生成期间 targetModel 保持原值', async () => {
      mockHttpPost.mockImplementation(() =>
        new Promise(resolve => setTimeout(() => resolve({ data: { content: 'AI新内容' } }), 50))
      )
      const { flow, targetModel } = createFlow('用户已填内容')

      const p = flow.generate(buildAiContext('D2'))
      // GENERATING 阶段 targetModel 不变
      expect(targetModel.value).toBe('用户已填内容')

      await p
      // PREVIEWING 阶段 targetModel 仍不变
      expect(targetModel.value).toBe('用户已填内容')
      expect(flow.generatedContent.value).toBe('AI新内容')
    })

    it('目标区有内容时 hasDiff 为 true', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: '不同内容' } } })
      const { flow } = createFlow('已有内容')

      await flow.generate(buildAiContext('D2'))
      expect(flow.hasDiff.value).toBe(true)
      expect(flow.originalContent.value).toBe('已有内容')
    })

    it('目标区无内容时 hasDiff 为 false', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: '新内容' } } })
      const { flow } = createFlow('')

      await flow.generate(buildAiContext('D2'))
      expect(flow.hasDiff.value).toBe(false)
    })

    it('取消时不修改 targetModel', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: 'AI输出' } } })
      const { flow, targetModel } = createFlow('原始内容')

      await flow.generate(buildAiContext('D2'))
      flow.cancel()

      expect(targetModel.value).toBe('原始内容')
    })

    it('只有 confirm 才真正写入 targetModel', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: '生成结果' } } })
      const { flow, targetModel } = createFlow('c0')

      await flow.generate(buildAiContext('D2'))

      // PREVIEWING 阶段 model 仍为 c0
      expect(targetModel.value).toBe('c0')

      // 确认
      flow.confirm()
      expect(targetModel.value).toBe('生成结果')
    })
  })

  describe('Req 9.6: 生成完成先展示 diff 预览', () => {
    it('生成完成自动进入 PREVIEWING 而非直接 CONFIRMED', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { content: '内容' } } })
      const { flow } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.phase.value).toBe('PREVIEWING')
      expect(flow.phase.value).not.toBe('CONFIRMED')
    })
  })

  describe('regenerate', () => {
    it('重新生成回到 GENERATING 再到 PREVIEWING', async () => {
      mockHttpPost
        .mockResolvedValueOnce({ data: { data: { content: '第一次' } } })
        .mockResolvedValueOnce({ data: { data: { content: '第二次' } } })

      const { flow } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.generatedContent.value).toBe('第一次')

      await flow.regenerate(buildAiContext('D2'))
      expect(flow.generatedContent.value).toBe('第二次')
      expect(flow.phase.value).toBe('PREVIEWING')
    })
  })

  describe('edge cases', () => {
    it('wpId 为空时不调用 API', async () => {
      const wpId = ref('')
      const targetModel = ref('')
      const flow = useAiGenerateFlow({
        wpId,
        targetModel,
        section: 'test',
        httpPost: mockHttpPost,
      })

      await flow.generate(buildAiContext('D2'))
      expect(mockHttpPost).not.toHaveBeenCalled()
      expect(flow.error.value).toBe('缺少底稿 ID')
    })

    it('非 PREVIEWING 阶段调用 confirm 无效', () => {
      const { flow, targetModel } = createFlow('原始')
      flow.confirm() // IDLE 阶段
      expect(targetModel.value).toBe('原始')
    })

    it('API 返回多层嵌套数据正确提取', async () => {
      mockHttpPost.mockResolvedValue({ data: { data: { text: '通过 text 字段' } } })
      const { flow } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.generatedContent.value).toBe('通过 text 字段')
    })

    it('API 返回扁平数据正确提取', async () => {
      mockHttpPost.mockResolvedValue({ data: { content: '扁平结构' } })
      const { flow } = createFlow()

      await flow.generate(buildAiContext('D2'))
      expect(flow.generatedContent.value).toBe('扁平结构')
    })

    it('无 httpPost 时使用 fallback', async () => {
      const wpId = ref('wp-1')
      const targetModel = ref('')
      const flow = useAiGenerateFlow({
        wpId,
        targetModel,
        section: 'my-section',
      })

      await flow.generate(buildAiContext('D2'))
      expect(flow.generatedContent.value).toContain('my-section')
      expect(flow.phase.value).toBe('PREVIEWING')
    })
  })
})
