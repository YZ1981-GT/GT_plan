/**
 * useSEstimateDisclosureEventBus — S 类 EventBus 联动 composable 单元测试
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 5.2
 * Requirements: 7.3, 8.1, 8.2, 8.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// Mock http
vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn().mockResolvedValue({ data: { text: 'AI generated text' } }),
    get: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// Mock eventBus
const mockEmit = vi.fn()
const mockOn = vi.fn()
const mockOff = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (...args: any[]) => mockEmit(...args),
    on: (...args: any[]) => mockOn(...args),
    off: (...args: any[]) => mockOff(...args),
  },
}))

import {
  useSEstimateDisclosureEventBus,
  S_ESTIMATE_ACCOUNT_CODES,
} from '../useSEstimateDisclosureEventBus'

// ─── Setup / Teardown ────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
})

afterEach(() => {
  vi.useRealTimers()
})

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useSEstimateDisclosureEventBus', () => {
  describe('S_ESTIMATE_ACCOUNT_CODES', () => {
    it('包含 S3/S15/S20/S21 四个映射', () => {
      expect(S_ESTIMATE_ACCOUNT_CODES).toHaveProperty('S15')
      expect(S_ESTIMATE_ACCOUNT_CODES).toHaveProperty('S20')
      expect(S_ESTIMATE_ACCOUNT_CODES).toHaveProperty('S3')
      expect(S_ESTIMATE_ACCOUNT_CODES).toHaveProperty('S21')
    })
  })

  describe('publishWorkpaperSaved（Req 7.3）', () => {
    it('保存后发布 substantive:adjudicated 事件', async () => {
      const { publishWorkpaperSaved } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-123',
        projectId: 'proj-456',
      })

      await publishWorkpaperSaved({ auditedAmount: 1000 })

      expect(mockEmit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({
          wpCode: 'S15',
          accountCode: '6901',
          auditedAmount: 1000,
        }),
      )
    })

    it('相同 payload 在 2s 内去重', async () => {
      const { publishWorkpaperSaved } = useSEstimateDisclosureEventBus({
        wpCode: 'S20',
        wpId: 'wp-1',
        projectId: 'proj-1',
      })

      await publishWorkpaperSaved({ auditedAmount: 500 })
      await publishWorkpaperSaved({ auditedAmount: 500 })

      // 只发一次
      expect(mockEmit).toHaveBeenCalledTimes(1)
    })

    it('不同 payload 不去重', async () => {
      const { publishWorkpaperSaved } = useSEstimateDisclosureEventBus({
        wpCode: 'S3',
        wpId: 'wp-2',
        projectId: 'proj-2',
      })

      await publishWorkpaperSaved({ auditedAmount: 100 })
      await publishWorkpaperSaved({ auditedAmount: 200 })

      expect(mockEmit).toHaveBeenCalledTimes(2)
    })
  })

  describe('publishDisclosureNoteUpdated（Req 8.2）', () => {
    it('防抖发布 disclosure:note-text-updated CustomEvent', () => {
      const dispatchSpy = vi.spyOn(window, 'dispatchEvent')

      const { publishDisclosureNoteUpdated } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-1',
        projectId: 'proj-1',
      })

      publishDisclosureNoteUpdated('roe-section', '测试文本')

      // 未超时前不发
      expect(dispatchSpy).not.toHaveBeenCalled()

      // 超时后发
      vi.advanceTimersByTime(2100)

      expect(dispatchSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'disclosure:note-text-updated',
        }),
      )

      const event = dispatchSpy.mock.calls[0][0] as CustomEvent
      expect(event.detail.wpCode).toBe('S15')
      expect(event.detail.section).toBe('roe-section')
      expect(event.detail.text).toBe('测试文本')

      dispatchSpy.mockRestore()
    })
  })

  describe('onDisclosureTextChange', () => {
    it('更新 disclosureText ref 并触发发布', () => {
      const { disclosureText, onDisclosureTextChange } = useSEstimateDisclosureEventBus({
        wpCode: 'S20',
        wpId: 'wp-1',
        projectId: 'proj-1',
      })

      onDisclosureTextChange('新的披露文本')

      expect(disclosureText.value).toBe('新的披露文本')
    })
  })

  describe('substantive:adjudicated 订阅（Req 8.3）', () => {
    it('subscribe() 调用后订阅 EventBus', () => {
      const { subscribe, unsubscribe } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-1',
        projectId: 'proj-1',
      })

      // 手动订阅（测试环境无组件 setup context，onMounted 不生效）
      subscribe()

      expect(mockOn).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.any(Function),
      )

      unsubscribe()
    })

    it('onRefresh 在收到事件时被调用', () => {
      const onRefresh = vi.fn()
      const { subscribe, unsubscribe } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-1',
        projectId: 'proj-1',
        onRefresh,
      })

      subscribe()

      // 获取注册的回调并手动调用
      const handler = mockOn.mock.calls[0][1]
      handler({ accountCode: '6901', auditedAmount: 1000 })

      expect(onRefresh).toHaveBeenCalled()
      unsubscribe()
    })

    it('非相关科目事件时不刷新', () => {
      const onRefresh = vi.fn()
      const { subscribe, unsubscribe } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-1',
        projectId: 'proj-1',
        onRefresh,
      })

      subscribe()

      const handler = mockOn.mock.calls[0][1]
      // S15 的 accountCode 是 '6901'，传入不同科目
      handler({ accountCode: '2201', auditedAmount: 500 })

      expect(onRefresh).not.toHaveBeenCalled()
      unsubscribe()
    })
  })

  describe('generateDisclosureWithAi（Req 8.1）', () => {
    it('调用 AI 端点生成文本并更新 disclosureText', async () => {
      const http = (await import('@/utils/http')).default
      ;(http.post as any).mockResolvedValue({ data: { text: '自动生成披露内容' } })

      const { generateDisclosureWithAi, disclosureText } = useSEstimateDisclosureEventBus({
        wpCode: 'S3',
        wpId: 'wp-ai',
        projectId: 'proj-ai',
        isReadonly: ref(false),
      })

      const result = await generateDisclosureWithAi('policy-change')

      expect(http.post).toHaveBeenCalledWith(
        '/api/workpapers/wp-ai/ai/generate',
        expect.objectContaining({
          section: 'policy-change',
          wp_code: 'S3',
        }),
      )
      expect(result).toBe('自动生成披露内容')
      expect(disclosureText.value).toBe('自动生成披露内容')
    })

    it('readonly 时不调用 AI', async () => {
      const http = (await import('@/utils/http')).default

      const { generateDisclosureWithAi } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-ro',
        projectId: 'proj-ro',
        isReadonly: ref(true),
      })

      const result = await generateDisclosureWithAi()

      expect(result).toBeNull()
      expect(http.post).not.toHaveBeenCalled()
    })

    it('AI 调用失败时 aiLoading 恢复 false', async () => {
      const http = (await import('@/utils/http')).default
      ;(http.post as any).mockRejectedValue(new Error('network error'))

      const { generateDisclosureWithAi, aiLoading } = useSEstimateDisclosureEventBus({
        wpCode: 'S20',
        wpId: 'wp-fail',
        projectId: 'proj-fail',
        isReadonly: ref(false),
      })

      const result = await generateDisclosureWithAi()

      expect(result).toBeNull()
      expect(aiLoading.value).toBe(false)
    })
  })

  describe('saveAndPublish', () => {
    it('调用后端 save 端点后发布事件', async () => {
      const http = (await import('@/utils/http')).default
      ;(http.post as any).mockResolvedValue({ success: true })

      const { saveAndPublish } = useSEstimateDisclosureEventBus({
        wpCode: 'S21',
        wpId: 'wp-save',
        projectId: 'proj-save',
      })

      const result = await saveAndPublish({ auditedAmount: 999 })

      expect(result).toBe(true)
      expect(http.post).toHaveBeenCalledWith(
        '/api/workpapers/wp-save/save',
        { auditedAmount: 999 },
      )
      expect(mockEmit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({ wpCode: 'S21' }),
      )
    })

    it('保存失败时返回 false', async () => {
      const http = (await import('@/utils/http')).default
      ;(http.post as any).mockRejectedValue(new Error('save failed'))

      const { saveAndPublish } = useSEstimateDisclosureEventBus({
        wpCode: 'S15',
        wpId: 'wp-err',
        projectId: 'proj-err',
      })

      const result = await saveAndPublish()

      expect(result).toBe(false)
    })
  })
})
