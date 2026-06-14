/**
 * useWorkpaperGenerate + 裁剪预选逻辑单测
 *
 * 验证：
 * - triggerGenerate 打开弹窗
 * - onTrimConfirm 调用 API 并传 selected_templates
 * - 空选择列表 warning 不调 API
 *
 * Requirements: 3.3
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), error: vi.fn() },
}))

import { useWorkpaperGenerate } from '@/composables/useWorkpaperGenerate'
import { api } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

beforeEach(() => {
  vi.clearAllMocks()
  ;(api.post as any).mockResolvedValue({ count: 5 })
})

describe('useWorkpaperGenerate', () => {
  it('triggerGenerate 设置 showTrimDialog=true', () => {
    const { showTrimDialog, triggerGenerate } = useWorkpaperGenerate({
      projectId: 'p1',
      templateSetId: 'ts1',
      year: 2025,
    })
    expect(showTrimDialog.value).toBe(false)
    triggerGenerate()
    expect(showTrimDialog.value).toBe(true)
  })

  it('onTrimConfirm 空列表不调 API', async () => {
    const { onTrimConfirm } = useWorkpaperGenerate({
      projectId: 'p1',
      templateSetId: 'ts1',
      year: 2025,
    })
    await onTrimConfirm([])
    expect(api.post).not.toHaveBeenCalled()
    expect(ElMessage.warning).toHaveBeenCalledWith('请至少选择一项底稿')
  })

  it('onTrimConfirm 调用 API 并传 selected_templates', async () => {
    const onSuccess = vi.fn()
    const { onTrimConfirm } = useWorkpaperGenerate({
      projectId: 'p1',
      templateSetId: 'ts1',
      year: 2025,
      onSuccess,
    })
    await onTrimConfirm(['E1', 'E1-1', 'D0'])
    expect(api.post).toHaveBeenCalledWith(
      '/api/projects/p1/working-papers/generate',
      {
        template_set_id: 'ts1',
        year: 2025,
        selected_templates: ['E1', 'E1-1', 'D0'],
      },
    )
    expect(onSuccess).toHaveBeenCalledWith(5)
  })

  it('API 失败时显示 error', async () => {
    ;(api.post as any).mockRejectedValue(new Error('网络错误'))
    const { onTrimConfirm } = useWorkpaperGenerate({
      projectId: 'p1',
      templateSetId: 'ts1',
      year: 2025,
    })
    await onTrimConfirm(['E1'])
    expect(ElMessage.error).toHaveBeenCalled()
  })
})
