/**
 * 公式历史一键回滚带当前版本号（spec formula-hub-integrity-closure 阶段 D 缺陷 D-2，需求 13.1、13.3）。
 *
 * 原状：onRollback 的请求体只有 row_code / module / source_log_id，后端缺 expected_version 恒 428，
 * 界面恒提示「回滚需要提供版本号」。既有守卫只扫源码（请求体不含 target_formula），看不到缺版本号。
 * 本文件完整挂载组件，点渲染出来的「一键回滚」按钮（经模板的 @click 走真实 onRollback），断言请求体。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get, post, msg, confirm } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), confirm: vi.fn(),
  msg: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: msg, ElMessageBox: { confirm } }
})
vi.mock('@/services/apiProxy', () => ({ api: { get, post } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { role: 'partner' } }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import FormulaHistoryTab from '@/components/formula/FormulaHistoryTab.vue'

const LIST_PATH = '/api/formula-audit-log/p1/2025'
const ROLLBACK_PATH = '/api/formula-audit-log/p1/2025/rollback'
const ENTRY = {
  id: 'log-1', module: 'report', row_code: 'BS-001', action: 'update', old_formula: "TB('1001','期末余额')",
  new_formula: "ROW('BS-009')", result_value: null, trace: null, created_at: null, operation: 'adapt',
  rollbackable: true, rollback_blocked_reason: null,
}

function mountTab() {
  return mount(FormulaHistoryTab, {
    props: { projectId: 'p1', year: 2025 },
    global: { plugins: [ElementPlus] },
  })
}

function rollbackButtons(w: ReturnType<typeof mountTab>) {
  return w.findAll('button').filter(b => b.text().includes('一键回滚'))
}

describe('公式历史回滚：点按钮发出的请求带 expected_version', () => {
  beforeEach(() => {
    get.mockReset(); post.mockReset(); confirm.mockReset()
    Object.values(msg).forEach((f) => f.mockReset())
    confirm.mockResolvedValue('confirm')
  })

  it('请求体带条目给出的当前版本号', async () => {
    get.mockResolvedValue([{ ...ENTRY, current_version: 3 }])
    post.mockResolvedValue({ ok: true, restored_formula: ENTRY.old_formula })
    const w = mountTab()
    await flushPromises()
    expect(get).toHaveBeenCalledWith(LIST_PATH, { params: { limit: 200 } })
    const [btn] = rollbackButtons(w)
    expect(btn, '可回滚条目应渲染「一键回滚」按钮').toBeTruthy()
    await btn.trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][0]).toBe(ROLLBACK_PATH)
    expect(post.mock.calls[0][1]).toEqual({
      row_code: 'BS-001', module: 'report', source_log_id: 'log-1', expected_version: 3,
    })
    expect(msg.success).toHaveBeenCalled()
    w.unmount()
  })

  it('当前版本 0（本项目无适配）也照样带上', async () => {
    get.mockResolvedValue([{ ...ENTRY, current_version: 0 }])
    post.mockResolvedValue({ ok: true })
    const w = mountTab()
    await flushPromises()
    await rollbackButtons(w)[0].trigger('click')
    await flushPromises()
    expect(post.mock.calls[0][1].expected_version).toBe(0)
    w.unmount()
  })

  it('条目没有当前版本：不发请求、提示刷新', async () => {
    get.mockResolvedValue([{ ...ENTRY }])
    const w = mountTab()
    await flushPromises()
    await rollbackButtons(w)[0].trigger('click')
    await flushPromises()
    expect(post).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
    expect(msg.warning).toHaveBeenCalledWith('无法确定该公式的当前版本，请刷新后重试')
    w.unmount()
  })

  it('不可回滚条目不渲染按钮（只看服务端 rollbackable，需求 13.3）', async () => {
    get.mockResolvedValue([{ ...ENTRY, id: 'log-2', rollbackable: false, rollback_blocked_reason: '人工补记不可回滚',
      current_version: null }])
    const w = mountTab()
    await flushPromises()
    expect(w.text()).toContain('BS-001')
    expect(rollbackButtons(w)).toHaveLength(0)
    w.unmount()
  })
})
