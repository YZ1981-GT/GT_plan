/**
 * 合并附注「📤 下推模板」（spec consol-note-template-push-to-subsidiaries）。
 *
 * 原实现把下推地址拼成 `reaggregate(...).replace('/reaggregate', '/push-template')`，
 * 且年度读的是函数里不存在的 `context.year`（点击即 ReferenceError，被 catch 成「下推失败」）。
 * 现在：地址走 apiPaths、年度取组件 props；本文件钉住请求地址 / 请求体与三种结果提示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const h = vi.hoisted(() => ({
  confirm: vi.fn(),
  alert: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  post: vi.fn(),
  bindings: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: h.warning, success: h.success, error: h.error },
  ElMessageBox: { confirm: h.confirm, alert: h.alert },
}))
vi.mock('@/services/apiProxy', () => ({ api: { post: h.post } }))
vi.mock('@/services/consolidationApi', () => ({ getDetailTemplateBindings: h.bindings }))

import { pushConsolNoteTemplate, pushFailureLines, pushIssueLines } from '../composables/consolNoteTemplatePush'

const PID = 'p-1'

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.confirm.mockResolvedValue('confirm')
  h.alert.mockResolvedValue('confirm')
  h.bindings.mockResolvedValue([{ section_id: '五-1', template_version_id: 'tv-1' }])
})

describe('pushConsolNoteTemplate', () => {
  it('没选章节：提示、不弹确认、不发请求', async () => {
    const busy = ref(false)
    await pushConsolNoteTemplate(PID, 2025, undefined, busy)
    expect(h.warning).toHaveBeenCalledWith('请先选择附注章节')
    expect(h.confirm).not.toHaveBeenCalled()
    expect(h.post).not.toHaveBeenCalled()
  })

  it('取消确认：不取绑定、不下推', async () => {
    h.confirm.mockRejectedValue('cancel')
    await pushConsolNoteTemplate(PID, 2025, '五-1', ref(false))
    expect(h.bindings).not.toHaveBeenCalled()
    expect(h.post).not.toHaveBeenCalled()
  })

  it('章节未绑定模板：提示去绑定、不下推，busy 复位', async () => {
    h.bindings.mockResolvedValue([{ section_id: '五-2', template_version_id: 'tv-2' }])
    const busy = ref(false)
    await pushConsolNoteTemplate(PID, 2025, '五-1', busy)
    expect(h.warning).toHaveBeenCalledWith(expect.stringContaining('未绑定明细模板'))
    expect(h.post).not.toHaveBeenCalled()
    expect(busy.value).toBe(false)
  })

  it('全部成功：按项目审计年度发到 push-template，带模板版本与本章节', async () => {
    const busy = ref(false)
    let busyDuringRequest = false
    h.post.mockImplementation(async () => {
      busyDuringRequest = busy.value
      return { total_success: 3, total_failure: 0, results: [] }
    })
    await pushConsolNoteTemplate(PID, 2024, '五-1', busy)
    expect(h.post).toHaveBeenCalledWith('/api/consolidation/notes/p-1/2024/push-template', {
      template_version_id: 'tv-1',
      section_ids: ['五-1'],
    }, { _silent: true })
    expect(busyDuringRequest).toBe(true)
    expect(busy.value).toBe(false)
    expect(h.success).toHaveBeenCalledWith('下推成功：3 家子企业已按集团模板对齐行')
    expect(h.alert).not.toHaveBeenCalled()
  })

  it('部分失败：弹窗逐家列出失败原因；关闭弹窗不算下推失败', async () => {
    h.post.mockResolvedValue({
      total_success: 1,
      total_failure: 1,
      results: [{ entities: [
        { status: 'success', company_name: '甲' },
        { status: 'failed', company_name: '乙', reason: '附注未生成' },
      ] }],
    })
    h.alert.mockRejectedValue('close')
    await pushConsolNoteTemplate(PID, 2025, '五-1', ref(false))
    await Promise.resolve()
    expect(h.alert).toHaveBeenCalledWith(
      '成功 1 家，失败 1 家：\n乙：附注未生成', '下推结果', { type: 'warning' },
    )
    expect(h.error).not.toHaveBeenCalled()
  })

  it('只有跳过、没有失败：同样不报成功，弹窗写明跳过原因', async () => {
    h.post.mockResolvedValue({
      total_success: 1, total_failure: 0, total_skipped: 1,
      results: [{ entities: [
        { status: 'success', company_name: '甲' },
        { status: 'skipped', company_name: '丁', reason: '子企业附注 八、1 由底稿披露表同步，行结构以底稿为准' },
      ] }],
    })
    await pushConsolNoteTemplate(PID, 2025, '五-1', ref(false))
    expect(h.success).not.toHaveBeenCalled()
    expect(h.alert).toHaveBeenCalledWith(
      '成功 1 家，跳过 1 家：\n丁：子企业附注 八、1 由底稿披露表同步，行结构以底稿为准', '下推结果', { type: 'warning' },
    )
  })

  it('有跳过的企业：不报成功，弹窗写明跳过原因（失败在前）', async () => {
    h.post.mockResolvedValue({
      total_success: 1,
      total_failure: 1,
      total_skipped: 2,
      results: [{ entities: [
        { status: 'skipped', company_name: '丁', reason: '子企业附注未生成章节 八、1（先在子企业生成附注再下推）' },
        { status: 'success', company_name: '甲' },
        { status: 'skipped', node_key: 'n-9', reason: '权限不足' },
        { status: 'failed', company_name: '乙', reason: '写入失败：x' },
      ] }],
    })
    await pushConsolNoteTemplate(PID, 2025, '五-1', ref(false))
    expect(h.success).not.toHaveBeenCalled()
    expect(h.alert).toHaveBeenCalledWith(
      '成功 1 家，跳过 2 家，失败 1 家：\n乙：写入失败：x\n丁：子企业附注未生成章节 八、1（先在子企业生成附注再下推）\nn-9：权限不足',
      '下推结果', { type: 'warning' },
    )
  })

  it('请求失败：显示后端原因', async () => {
    h.post.mockRejectedValue({ response: { data: { message: '无编辑权限' } } })
    const busy = ref(false)
    await pushConsolNoteTemplate(PID, 2025, '五-1', busy)
    expect(h.error).toHaveBeenCalledWith('无编辑权限')
    expect(busy.value).toBe(false)
  })
})

describe('pushFailureLines', () => {
  it('只列失败的企业，没有公司名时用节点键', () => {
    expect(pushFailureLines({ results: [{ entities: [
      { status: 'failed', node_key: 'n-1', reason: '锁定中' },
      { status: 'success', company_name: '丙' },
    ] }] })).toBe('n-1：锁定中')
    expect(pushFailureLines(null)).toBe('')
  })

  it('pushIssueLines：失败在前、跳过在后，成功不列', () => {
    expect(pushIssueLines({ results: [{ entities: [
      { status: 'skipped', company_name: '甲', reason: '标为本期无此情形' },
      { status: 'success', company_name: '乙' },
      { status: 'failed', company_name: '丙', reason: '写入失败' },
    ] }] })).toBe('丙：写入失败\n甲：标为本期无此情形')
  })
})
