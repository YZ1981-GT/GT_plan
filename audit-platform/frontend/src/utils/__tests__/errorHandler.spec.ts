/**
 * errorHandler.spec.ts — V3 Req 8.5.2
 *
 * 验证 handleApiError 扩展：
 * - 423 PROJECT_ARCHIVED 中文映射
 * - 422 AI_CONTENT_NOT_CONFIRMED 中文映射
 * - 422 CROSS_MODULE_CONFLICT_UNRESOLVED 中文映射
 * - 既有行为不变（网络错误/401/403/404/409/5xx/普通 422）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock element-plus — factory 不引用外部变量
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
  ElNotification: vi.fn(),
}))

// Mock getLastTraceId
vi.mock('@/utils/http', () => ({
  getLastTraceId: () => '',
}))

import { ElMessage, ElNotification } from 'element-plus'
import { handleApiError } from '../errorHandler'

describe('handleApiError', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── 423 PROJECT_ARCHIVED ──
  it('423 → 项目已归档中文提示', () => {
    const err = { response: { status: 423, data: {} } }
    handleApiError(err, '保存底稿')
    expect(ElMessage.warning).toHaveBeenCalledWith(
      '保存底稿：项目已归档（只读），无法执行此操作',
    )
  })

  // ── 422 AI_CONTENT_NOT_CONFIRMED ──
  it('422 + AI_CONTENT_NOT_CONFIRMED → AI 内容未确认中文提示', () => {
    const err = {
      response: {
        status: 422,
        data: { detail: { error_code: 'AI_CONTENT_NOT_CONFIRMED' } },
      },
    }
    handleApiError(err, '提交签字')
    expect(ElMessage.warning).toHaveBeenCalledWith(
      '提交签字：存在未确认的 AI 内容，请先确认后再操作',
    )
  })

  // ── 422 CROSS_MODULE_CONFLICT_UNRESOLVED ──
  it('422 + CROSS_MODULE_CONFLICT_UNRESOLVED → 跨模块冲突中文提示', () => {
    const err = {
      response: {
        status: 422,
        data: { detail: { error_code: 'CROSS_MODULE_CONFLICT_UNRESOLVED' } },
      },
    }
    handleApiError(err, '保存调整')
    expect(ElMessage.warning).toHaveBeenCalledWith(
      '保存调整：存在未调解的跨模块冲突，请先调解后再操作',
    )
  })

  // ── 422 error_code 在顶层 data 中（兼容另一种后端格式）──
  it('422 + error_code 在 response.data 顶层也能识别', () => {
    const err = {
      response: {
        status: 422,
        data: { error_code: 'AI_CONTENT_NOT_CONFIRMED', detail: {} },
      },
    }
    handleApiError(err, '操作')
    expect(ElMessage.warning).toHaveBeenCalledWith(
      '操作：存在未确认的 AI 内容，请先确认后再操作',
    )
  })

  // ── 普通 422（无特殊 error_code）──
  it('422 无特殊 error_code → 通用参数校验提示', () => {
    const err = {
      response: { status: 422, data: { detail: { message: '金额不能为负' } } },
    }
    handleApiError(err, '创建分录')
    expect(ElMessage.warning).toHaveBeenCalledWith(
      '创建分录：金额不能为负',
    )
  })

  // ── 既有行为回归 ──
  it('网络错误（无 status）→ 网络不通提示', () => {
    handleApiError({}, '加载数据')
    expect(ElMessage.error).toHaveBeenCalledWith(
      '加载数据：网络不通，请检查连接',
    )
  })

  it('401 → 静默（不弹消息）', () => {
    const err = { response: { status: 401 } }
    handleApiError(err, '操作')
    expect(ElMessage.error).not.toHaveBeenCalled()
    expect(ElMessage.warning).not.toHaveBeenCalled()
    expect(ElNotification).not.toHaveBeenCalled()
  })

  it('403 → 无权操作', () => {
    const err = { response: { status: 403, data: {} } }
    handleApiError(err, '删除项目')
    expect(ElMessage.warning).toHaveBeenCalledWith('删除项目：无权操作')
  })

  it('404 → 资源不存在', () => {
    const err = { response: { status: 404, data: {} } }
    handleApiError(err, '查看底稿')
    expect(ElMessage.warning).toHaveBeenCalledWith('查看底稿：资源不存在')
  })

  it('409 → 冲突通知', () => {
    const err = {
      response: { status: 409, data: { detail: { message: '版本冲突' } } },
    }
    handleApiError(err, '保存')
    expect(ElNotification).toHaveBeenCalledWith(
      expect.objectContaining({ title: '操作冲突', message: '版本冲突', type: 'warning' }),
    )
  })

  it('500 → 系统错误通知', () => {
    const err = { response: { status: 500, data: {} } }
    handleApiError(err, '导出报表')
    expect(ElNotification).toHaveBeenCalledWith(
      expect.objectContaining({ title: '导出报表失败', type: 'error' }),
    )
  })
})
