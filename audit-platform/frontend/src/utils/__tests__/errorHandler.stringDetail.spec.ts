/**
 * handleApiError —— 字符串 detail 必须原样展示
 *
 * 后端业务 `HTTPException(status, "中文原因")` 经 `normaliseErrorEnvelope` 归一后，
 * `response.data.detail` 是**字符串**。旧实现只读 `detail?.message`，于是 409/422/503
 * 的中文根因全部被兜底文案吞掉（2026-09-29 知识库实测：「项目组权限的文件夹须包含你参与的
 * 项目」只显示成「请求参数有误，请检查输入」，用户无从知道为什么建不了）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
  ElNotification: vi.fn(),
}))

import { ElMessage, ElNotification } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'

function shown(): string {
  const parts: string[] = []
  for (const c of (ElMessage.warning as any).mock.calls) parts.push(String(c[0] ?? ''))
  for (const c of (ElMessage.error as any).mock.calls) parts.push(String(c[0] ?? ''))
  for (const c of (ElNotification as any).mock.calls) parts.push(`${c[0]?.title ?? ''} ${c[0]?.message ?? ''}`)
  return parts.join(' | ')
}

const err = (status: number, detail: unknown) => ({ response: { status, data: { detail } } })

describe('handleApiError 展示后端字符串 detail', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each([400, 409, 422, 503])('%i + 字符串 detail → 提示含原因', (status) => {
    const reason = '项目组权限的文件夹须包含你参与的项目'
    handleApiError(err(status, reason), '创建')
    expect(shown()).toContain(reason)
  })

  it('dict detail 仍取 message', () => {
    handleApiError(err(422, { message: '科目缺失' }), '保存')
    expect(shown()).toContain('科目缺失')
  })

  it('FastAPI 字段校验数组 detail → 兜底文案（不把英文结构体甩给用户）', () => {
    handleApiError(err(422, [{ loc: ['body', 'name'], msg: 'field required' }]), '保存')
    expect(shown()).toContain('请求参数有误')
    expect(shown()).not.toContain('field required')
  })

  it('空白字符串 detail → 兜底文案', () => {
    handleApiError(err(409, '   '), '保存')
    expect(shown()).toContain('数据冲突')
  })

  it('422 特化 error_code 分派不受影响', () => {
    handleApiError(err(422, { error_code: 'AI_CONTENT_NOT_CONFIRMED' }), '提交')
    expect(shown()).toContain('未确认的 AI 内容')
  })
})
