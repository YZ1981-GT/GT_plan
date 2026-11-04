/**
 * 项目「审计抽样」页（任务 17 需求 8.3；spec voucher-workflow-linkage-lineage-closure R4.4 / R4.5）
 *
 * - 年度只取项目审计年度：没填时提示去填，各页签不查询；年度上限不写死；账龄基准日默认审计期末；
 * - 抽凭概览切到页签才加载（默认页签是截止测试，原先挂载即查）；失败显示后端原因与「重试」；
 * - 行上打开底稿；被多张底稿抽取的凭证列出来，有科目的可打开序时账里的这张凭证。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'project-1' }, query: {} }),
  useRouter: () => ({ push }),
}))
vi.mock('@/services/commonApi', () => ({ cutoffTest: vi.fn(), agingAnalysis: vi.fn(), monthlyDetail: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))
const phase = vi.hoisted(() => ({ fetch: vi.fn() }))
vi.mock('@/composables/useProjectAuditPhase', () => ({ fetchProjectAuditPhase: phase.fetch }))

import http from '@/utils/http'
import { useProjectStore } from '@/stores/project'
import SamplingEnhanced from '../SamplingEnhanced.vue'

const get = (http as unknown as { get: ReturnType<typeof vi.fn> }).get
const COVERAGE = '/api/projects/project-1/sampling/voucher-coverage'
const FY_KEY = JSON.stringify(['2025', '001', '2025-01-07', 'FY', '0003'])

function coverage(over: Record<string, unknown> = {}) {
  return { data: { data: {
    year: 2025, active_dataset_id: 'dataset-12345678',
    duplicated: [
      { voucher_key: FY_KEY, voucher_no: '0003', voucher_date: '2025-01-07', voucher_type: 'FY', account_code: '1122',
        workpaper_count: 2, legacy: false },
      { voucher_key: null, voucher_no: '0012', voucher_date: null, voucher_type: null, account_code: null,
        workpaper_count: 3, legacy: true },
    ],
    by_workpaper: [
      { working_paper_id: 'wp-1', wp_code: 'J1', wp_name: '应付职工薪酬检查', batch_count: 2, sample_count: 5,
        interim_survival_unacked: 2, interim_survival_counts: { unchanged: 1, modified: 1, renumbered: 1, deleted: 0 } },
      { working_paper_id: 'wp-2', wp_code: 'E1', wp_name: '货币资金检查', batch_count: 1, sample_count: 3,
        interim_survival_unacked: 0, interim_survival_counts: { unchanged: 3, modified: 0, renumbered: 0, deleted: 0 } },
    ],
    ...over,
  } } }
}

const coverageCalls = () => get.mock.calls.filter(c => c[0] === COVERAGE)

beforeEach(() => {
  vi.clearAllMocks()
  useProjectStore().year = 2025
  phase.fetch.mockResolvedValue({ auditPeriodEnd: '2025-12-31' })
  get.mockResolvedValue(coverage())
})

async function page(): Promise<VueWrapper> {
  const w = mount(SamplingEnhanced, {
    global: {
      plugins: [ElementPlus],
      stubs: { GtPageHeader: { template: '<div>审计抽样</div>' } },
      directives: { permission: () => undefined },
    },
  })
  await flushPromises()
  return w
}

async function openTab(w: VueWrapper, label: string) {
  await w.findAll('.el-tabs__item').find(x => x.text().includes(label))!.trigger('click')
  await flushPromises()
}

const button = (w: VueWrapper, text: string) => w.findAll('button').find(b => b.text().trim() === text)

describe('抽凭概览：切到页签才加载', () => {
  it('默认页签不查；切到抽凭概览按项目审计年度查一次，再切回来不重复查', async () => {
    const w = await page()
    expect(coverageCalls()).toHaveLength(0)
    await openTab(w, '抽凭概览')
    expect(coverageCalls()).toHaveLength(1)
    expect(coverageCalls()[0][1]).toEqual(expect.objectContaining({ params: { year: 2025 }, _silent: true, _dedupe: false }))
    await openTab(w, '截止性测试')
    await openTab(w, '抽凭概览')
    expect(coverageCalls()).toHaveLength(1)
  })

  it('表格显示未确认变化与四类计数；行上打开底稿', async () => {
    const w = await page()
    await openTab(w, '抽凭概览')
    const text = w.text()
    expect(text).toContain('当前账套 dataset-')
    expect(text).toContain('J1')
    expect(text).toContain('2 条变化未确认')
    expect(text).toContain('未变 1 / 已改 1 / 疑似改号 1 / 已删 0')
    expect(text).toContain('已核对，无待确认变化')
    await w.findAll('button').filter(b => b.text().trim() === '打开底稿')[0].trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'WorkpaperEditor', params: { projectId: 'project-1', wpId: 'wp-1' }, query: {} })
  })

  it('被多张底稿抽取的凭证逐张列出；有科目的打开序时账凭证层，旧登记说明原因', async () => {
    const w = await page()
    await openTab(w, '抽凭概览')
    const dup = w.get('[data-testid="sampling-overview-duplicated"]')
    expect(w.text()).toContain('另有 2 张凭证被多张底稿抽取')
    expect(dup.text()).toContain('2025-01-07 FY-0003')
    expect(dup.text()).toContain('旧登记没有凭证日期')
    const ledger = dup.findAll('button').filter(b => b.text().trim() === '序时账')
    expect(ledger).toHaveLength(1)
    await ledger[0].trigger('click')
    const target = push.mock.calls.at(-1)![0]
    expect(target).toMatchObject({ name: 'LedgerPenetration', params: { projectId: 'project-1' } })
    expect(target.query).toEqual({
      year: '2025', level: 'voucher', account: '1122', voucher: '0003', voucherDate: '2025-01-07',
      voucherType: 'FY', voucherCompany: '001',
    })
  })

  it('读取失败显示后端原因与重试；重试成功后清掉错误', async () => {
    get.mockRejectedValueOnce({ response: { status: 500, data: { detail: '数据库连接超时' } } })
    const w = await page()
    await openTab(w, '抽凭概览')
    const error = w.get('[data-testid="sampling-overview-error"]')
    expect(error.text()).toContain('抽凭概览读取失败：数据库连接超时')
    await button(w, '重试')!.trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="sampling-overview-error"]').exists()).toBe(false)
    expect(w.text()).toContain('J1')
    expect(coverageCalls()).toHaveLength(2)
  })

  it('改年度后读取失败：不留上一次（别的年度）的行，表格说明读取失败', async () => {
    const w = await page()
    await openTab(w, '抽凭概览')
    expect(w.get('[data-testid="sampling-overview-table"]').text()).toContain('J1')
    ;(w.vm as unknown as { voucherYear: number }).voucherYear = 2024
    get.mockRejectedValueOnce({ response: { status: 500, data: { detail: '数据库连接超时' } } })
    await button(w, '刷新')!.trigger('click')
    await flushPromises()
    expect(coverageCalls().at(-1)![1]).toEqual(expect.objectContaining({ params: { year: 2024 } }))
    const table = w.get('[data-testid="sampling-overview-table"]')
    expect(table.text()).not.toContain('J1')
    expect(table.text()).toContain('读取失败，点「重试」重新读取')
    expect(w.find('[data-testid="sampling-overview-duplicated"]').exists()).toBe(false)
    expect(w.text()).not.toContain('当前账套 dataset-')
  })

  it('没有后端原因时按状态说明（无权限 / 断网）', async () => {
    get.mockRejectedValueOnce({ response: { status: 403, data: {} } })
    const w = await page()
    await openTab(w, '抽凭概览')
    expect(w.get('[data-testid="sampling-overview-error"]').text()).toContain('没有本项目的查看权限')
    get.mockRejectedValueOnce(new Error('Network Error'))
    await button(w, '重试')!.trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="sampling-overview-error"]').text()).toContain('网络连接失败')
  })
})

describe('年度与基准日来自项目', () => {
  it('项目未填审计年度：提示去填，切到概览也不查，各页签按钮禁用', async () => {
    // 后端审计年度已按「年度 → 审计期末 → 审计期初 → 项目名」解析，store 为空时审计期末也是空
    useProjectStore().year = null
    phase.fetch.mockResolvedValue({ auditPeriodEnd: null })
    const w = await page()
    expect(w.find('[data-testid="sampling-year-missing"]').exists()).toBe(true)
    await openTab(w, '抽凭概览')
    expect(coverageCalls()).toHaveLength(0)
    expect(button(w, '刷新')!.attributes('disabled')).toBeDefined()
    expect(button(w, '执行')!.attributes('disabled')).toBeDefined()
    expect(button(w, '分析')!.attributes('disabled')).toBeDefined()
    expect(button(w, '查询')!.attributes('disabled')).toBeDefined()
    await button(w, '去填写审计年度')!.trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'ProjectSettingsCenter', params: { projectId: 'project-1' }, query: { tab: 'standard' } })
  })

  it('各页签年度取项目审计年度（不是 2025 写死）；年度上限 = 审计年度与今年取大再加一', async () => {
    useProjectStore().year = 2031
    const w = await page()
    const vm = w.vm as unknown as { cutoffForm: { year: number }; monthlyForm: { year: number }; voucherYear: number }
    expect([vm.cutoffForm.year, vm.monthlyForm.year, vm.voucherYear]).toEqual([2031, 2031, 2031])
    const maxes = w.findAllComponents({ name: 'ElInputNumber' }).map(n => n.props('max'))
    expect(maxes).toContain(Math.max(2031, new Date().getFullYear()) + 1)
    expect(maxes).not.toContain(2030)
  })

  it('账龄基准日默认审计期末；审计期末与年度不同年时按年度 12-31', async () => {
    phase.fetch.mockResolvedValue({ auditPeriodEnd: '2025-06-30' })
    let w = await page()
    expect((w.vm as unknown as { agingForm: { base_date: string } }).agingForm.base_date).toBe('2025-06-30')
    w.unmount()
    phase.fetch.mockResolvedValue({ auditPeriodEnd: '2024-12-31' })
    w = await page()
    expect((w.vm as unknown as { agingForm: { base_date: string } }).agingForm.base_date).toBe('2025-12-31')
  })

  it('审计期末晚到时不覆盖用户已改的基准日', async () => {
    let resolve!: (v: unknown) => void
    phase.fetch.mockReturnValue(new Promise(r => { resolve = r }))
    const w = await page()
    const vm = w.vm as unknown as { agingForm: { base_date: string } }
    expect(vm.agingForm.base_date).toBe('2025-12-31')
    vm.agingForm.base_date = '2025-03-31'
    resolve({ auditPeriodEnd: '2025-06-30' })
    await flushPromises()
    expect(vm.agingForm.base_date).toBe('2025-03-31')
  })
})
