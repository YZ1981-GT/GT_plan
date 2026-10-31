/**
 * 一致性门禁面板按五态显示（spec formula-hub-integrity-closure 阶段 D 缺陷 D-3，需求 16.5）。
 *
 * 原状：面板请求 /consistency-gate/check（后端不存在，恒 404）；映射时只拷 passed / severity / details，
 * 五态标签分支走不到；接口没返回 D4 结果时自补 passed: true「数据不完整，跳过检查」。
 * 本文件挂载组件后读渲染出的标签与原因（不读内部状态），并经真实 CrossCheckPanel 挂载核对请求路径与年度
 * —— 宿主链 WorkpaperEditor → WorkpaperSidePanel → CrossCheckPanel 的年度由 workpaperSidePanelYear.spec.ts 守。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const REPO = resolve(__dirname, '../../../../../..')
/** 后端端点用例 test_consistency_display_snapshots.py 经 HTTP 写下的 consistency-check 真实响应（字段名以它为准） */
const CHECK_SNAPSHOT = JSON.parse(
  readFileSync(resolve(REPO, 'backend/tests/formula_hub/_snapshots/consistency_check.json'), 'utf-8'),
)

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
// CrossCheckPanel 自己的跨科目校验数据与显示偏好：与门禁面板无关，给空结果
vi.mock('@/composables/useCrossCheck', async () => {
  const { ref, computed } = await import('vue')
  return {
    useCrossCheck: () => ({
      results: ref([]), rules: ref([]), loading: ref(false), executing: ref(false),
      summary: computed(() => ({ total: 0, passed: 0, failed: 0, skipped: 0 })),
      passRate: computed(() => 0), hasBlockingFailures: computed(() => false),
      execute: vi.fn(), fetchResults: vi.fn().mockResolvedValue(undefined), fetchRules: vi.fn().mockResolvedValue(undefined),
    }),
  }
})
vi.mock('@/stores/displayPrefs', () => ({ useDisplayPrefsStore: () => ({ fmt: String, fmtDateTime: String }) }))

import ConsistencyGatePanel from '@/components/workpaper/ConsistencyGatePanel.vue'
import CrossCheckPanel from '@/components/workpaper/CrossCheckPanel.vue'
import { checkReasonOf, checkStatusLabel, checkStatusOf } from '@/utils/consistencyCheckStatus'

const CHECK_PATH = '/api/projects/p1/workflow/consistency-check'

function mountPanel() {
  return mount(ConsistencyGatePanel, {
    props: { projectId: 'p1', year: 2025 },
    global: { plugins: [ElementPlus] },
  })
}

function labels(w: ReturnType<typeof mountPanel>): string[] {
  return w.findAll('[data-testid="gate-status-label"]').map(n => n.text())
}

function reasons(w: ReturnType<typeof mountPanel>): string[] {
  return w.findAll('[data-testid="gate-status-reason"]').map(n => n.text())
}

const D4 = (suffix: string) => `D4勾稽:${suffix}`

describe('ConsistencyGatePanel 五态（挂载后读渲染结果）', () => {
  beforeEach(() => get.mockReset())

  it('经真实 CrossCheckPanel 挂载：请求一致性检查展示端点并带宿主的年度（不是不存在的 /consistency-gate/check）', async () => {
    get.mockResolvedValue({ checks: [] })
    const w = mount(CrossCheckPanel, { props: { projectId: 'p1', year: 2024 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(w.findComponent(ConsistencyGatePanel).exists()).toBe(true)
    expect(get).toHaveBeenCalledWith(CHECK_PATH, { params: { year: 2024 } })
    expect(get.mock.calls.some(([url]) => String(url).includes('/consistency-gate/check'))).toBe(false)
    w.unmount()
  })

  it('按 status / reason 显示：未执行（数据缺失）/ 不适用 / 检查异常各有标签与原因，不显示「通过」', async () => {
    get.mockResolvedValue({
      checks: [
        { check_name: D4('营业收入合计=主营+其他'), passed: false, status: 'not_executed',
          reason: '数据不完整，跳过检查', severity: 'blocking', details: '' },
        { check_name: D4('应收增长率vs收入增长率'), passed: false, status: 'not_applicable',
          reason: '底稿已裁剪', severity: 'warning', details: '' },
        { check_name: D4('毛利率波动<5%'), passed: false, status: 'error',
          reason: '检查异常：RuntimeError：boom', severity: 'warning', details: '' },
        { check_name: '试算平衡', passed: true, status: 'passed', reason: '', severity: 'blocking', details: '' },
      ],
    })
    const w = mountPanel()
    await flushPromises()
    expect(get).toHaveBeenCalledWith(CHECK_PATH, { params: { year: 2025 } })
    expect(labels(w)).toEqual(['未执行（数据缺失）', '不适用', '检查异常'])
    expect(reasons(w)).toEqual(['数据不完整，跳过检查', '底稿已裁剪', '检查异常：RuntimeError：boom'])
    expect(w.text()).toContain('0 通过、1 未执行、1 不适用、1 检查异常')
    expect(w.text()).not.toContain('存在阻断级差异') // 未执行不是阻断级差异
    w.unmount()
  })

  it('接口没有 D4 结果：4 条都显示「未执行」并写明原因，不自补「通过」', async () => {
    get.mockResolvedValue({ checks: [{ check_name: '试算平衡', passed: true, status: 'passed' }] })
    const w = mountPanel()
    await flushPromises()
    expect(labels(w)).toEqual(Array(4).fill('未执行（数据缺失）'))
    expect(reasons(w)).toEqual(Array(4).fill('一致性检查未返回该项结果，未执行'))
    expect(w.text()).toContain('0 通过、4 未执行') // 原先自补通过时为「4/4 通过」
    expect(w.text()).not.toContain('4/4 通过')
    w.unmount()
  })

  it('接口没给出检查状态：按「检查异常」显示并写明原因，不按 passed 推断成「通过」', async () => {
    get.mockResolvedValue({ checks: [{ check_name: D4('营业收入合计=主营+其他'), passed: true, severity: 'blocking' }] })
    const w = mountPanel()
    await flushPromises()
    expect(labels(w)).toEqual(['检查异常'])
    expect(reasons(w)).toEqual(['接口未返回检查状态'])
    expect(w.text()).not.toContain('1/1 通过')
    w.unmount()
  })

  it('只有「失败 ∧ 阻断级」才提示阻断', async () => {
    get.mockResolvedValue({
      checks: [{ check_name: D4('营业收入合计=主营+其他'), passed: false, status: 'failed',
        reason: '差额 10.00', severity: 'blocking', details: '' }],
    })
    const w = mountPanel()
    await flushPromises()
    expect(labels(w)).toEqual(['失败'])
    expect(reasons(w)).toEqual(['差额 10.00'])
    expect(w.text()).toContain('存在阻断级差异')
    w.unmount()
  })

  it('读后端真实响应快照 consistency_check.json：D4 项按后端的 status / reason 字段显示（不靠手写夹具）', async () => {
    const d4 = CHECK_SNAPSHOT.checks.filter((c: { check_name: string }) => c.check_name.startsWith('D4勾稽'))
    // 判据不空转：快照里恰有一条 D4 项、一条失败、阻断级，原因与明细不同（读错字段会退回明细文字）。
    // 这里不读 status / reason 字段本身：后端改了字段名时要红在下面的显示断言上
    expect(d4).toHaveLength(1)
    expect([CHECK_SNAPSHOT.failed_count, d4[0].severity]).toEqual([1, 'blocking'])
    expect(d4[0].details).not.toBe('差额 10.00')
    get.mockResolvedValue(CHECK_SNAPSHOT)
    const w = mountPanel()
    await flushPromises()
    expect(get).toHaveBeenCalledWith(CHECK_PATH, { params: { year: 2025 } })
    expect(labels(w)).toEqual(['失败'])
    expect(reasons(w)).toEqual(['差额 10.00'])
    expect(w.text()).toContain('存在阻断级差异')
    w.unmount()
  })

  it('共用读法：status 优先；缺失或认不出 ⇒ 检查异常 + 原因；通过项没有原因', () => {
    expect(checkStatusOf({ passed: true, status: 'not_executed' })).toBe('not_executed')
    expect(checkStatusOf({ passed: true })).toBe('error')
    expect(checkStatusOf({ passed: false, status: 'weird' })).toBe('error')
    expect(checkStatusLabel({ status: 'error' })).toBe('检查异常')
    expect(checkReasonOf({ passed: true })).toBe('接口未返回检查状态')
    expect(checkReasonOf({ status: 'passed', details: '平衡' })).toBe('')
    expect(checkReasonOf({ status: 'failed', reason: '', details: '差额 5' })).toBe('差额 5')
  })
})
