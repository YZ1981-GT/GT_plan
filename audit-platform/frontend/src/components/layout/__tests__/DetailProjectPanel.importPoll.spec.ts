/**
 * 项目概览面板的导入进度轮询（spec procedure-chain-hardening-and-java-contracts R17）：
 * 没有导入任务 30 秒查一次（原先固定 5 秒）、有任务 5 秒；提交导入事件立即查；卸载后不再查。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), resolve: vi.fn(() => ({ href: '' })) }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElNotification: vi.fn(),
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/utils/confirm', () => ({ confirmForceReset: vi.fn(), confirmDangerous: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/composables/useNavigationStack', () => ({ useNavigationStack: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({ useDisplayPrefsStore: () => ({ fmt: (v: number) => String(v) }) }))
vi.mock('@/utils/openLedgerWindow', () => ({ openLedgerWindow: vi.fn() }))
vi.mock('@/components/layout/PlatformUserGuideDialog.vue', () => ({ default: { name: 'PlatformUserGuideDialog', render: () => null } }))
vi.mock('@/components/wizard/TeamAssignmentStep.vue', () => ({ default: { name: 'TeamAssignmentStep', render: () => null } }))

import DetailProjectPanel from '../DetailProjectPanel.vue'
import { eventBus } from '@/utils/eventBus'

let processing = false
const activeJobCalls = () => api.get.mock.calls.filter(([url]) => String(url).endsWith('/ledger-import/active-job'))

beforeEach(() => {
  processing = false
  api.get.mockReset().mockImplementation(async (url: string) => {
    if (String(url).endsWith('/ledger-import/active-job')) {
      return processing ? { status: 'processing', phase: 'writing', progress: 40 } : { status: 'idle' }
    }
    return null
  })
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
})
afterEach(() => {
  vi.useRealTimers()
})

const mountPanel = () => shallowMount(DetailProjectPanel, { props: { project: { id: 'p1', name: '【测试】甲', audit_year: 2025 } } })

describe('DetailProjectPanel 导入进度轮询', () => {
  it('没有导入任务：挂载查一次，5 秒内不再查，30 秒再查', async () => {
    const w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    expect(activeJobCalls()).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(5_000)
    expect(activeJobCalls()).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(25_000)
    expect(activeJobCalls()).toHaveLength(2)
    w.unmount()
  })

  it('有进行中的导入：每 5 秒；显示进度', async () => {
    processing = true
    const w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(5_000)
    expect(activeJobCalls()).toHaveLength(2)
    expect((w.vm as any).importStatus?.progress).toBe(40)
    w.unmount()
  })

  it('本项目提交导入：立即查（不等 30 秒）；别的项目的提交不查；卸载后不再查', async () => {
    const w = mountPanel()
    await vi.advanceTimersByTimeAsync(0)
    eventBus.emit('ledger-import:submitted', { projectId: 'p2' })
    await vi.advanceTimersByTimeAsync(0)
    expect(activeJobCalls()).toHaveLength(1)
    processing = true
    eventBus.emit('ledger-import:submitted', { projectId: 'p1' })
    await vi.advanceTimersByTimeAsync(0)
    expect(activeJobCalls()).toHaveLength(2)
    w.unmount()
    eventBus.emit('ledger-import:submitted', { projectId: 'p1' })
    await vi.advanceTimersByTimeAsync(60_000)
    expect(activeJobCalls()).toHaveLength(2)
  })
})
