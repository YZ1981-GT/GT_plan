/**
 * 签字决策页的一致性卡片按五态计数与说明（spec formula-hub-integrity-closure 阶段 D 缺陷 D-3，需求 16.5）。
 *
 * 原状：「一致性 n/m 通过」按 passed 计数，点开的说明只分 ✓ / ✗，原因读 details?.message（后端 details 是字符串，恒为空）。
 * 本文件挂载整页（子面板打桩），从渲染出的卡片读计数、点卡片读弹出的说明。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, ref } from 'vue'
import ElementPlus from 'element-plus'

const { get, message, stub } = vi.hoisted(() => {
  const fn: any = vi.fn()
  fn.info = vi.fn(); fn.warning = vi.fn(); fn.success = vi.fn(); fn.error = vi.fn()
  // vi.mock 工厂被提升到导入之前执行：子面板桩必须在 hoisted 里定义（顶层 const 此时尚未初始化）
  const stub = (name: string) => ({ default: { name, render: () => null } })
  return { get: vi.fn(), message: fn, stub }
})
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return { ...actual, ElMessage: message }
})
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1', year: '2025' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/services/signatureApi', () => ({
  getSignReadinessV2: vi.fn().mockResolvedValue(null), signDocument: vi.fn(),
}))
vi.mock('@/composables/useStaleSummaryFull', () => ({
  useStaleSummaryFull: () => ({
    workpapers: ref({ total: 0, stale: 0, inconsistent: 0 }), reports: ref({ total: 0, stale: 0 }),
    notes: ref({ total: 0, stale: 0 }), misstatements: ref({ total: 0, recheck_needed: 0 }),
    anyStale: computed(() => false),
  }),
}))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 'u1', role: 'partner', username: 'p' } }) }))
vi.mock('@/utils/passwordConfirm', () => ({ requestConfirmationToken: vi.fn() }))
vi.mock('@/utils/confirm', () => ({ confirmSignature: vi.fn(), confirmSign: vi.fn() }))
vi.mock('@/utils/feedback', () => ({ feedback: { success: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/components/common/GtPageHeader.vue', () => stub('GtPageHeader'))
vi.mock('@/components/gate/GateReadinessPanel.vue', () => stub('GateReadinessPanel'))
vi.mock('@/components/common/SignoffChecklist.vue', () => stub('SignoffChecklist'))

import PartnerSignDecision from '@/views/PartnerSignDecision.vue'

const CHECKS = [
  { check_name: '试算平衡', passed: true, status: 'passed', reason: '', details: '借贷平衡', severity: 'blocking' },
  { check_name: '报表平衡', passed: false, status: 'failed', reason: '资产≠负债+权益，差额 10.00', details: '',
    severity: 'blocking' },
  // passed 与 status 故意不一致（改造前跳过出口一律 passed=true）：页面只能按 status 计数
  { check_name: 'D4勾稽:营业收入合计=主营+其他', passed: true, status: 'not_executed',
    reason: '数据不完整，跳过检查', details: '', severity: 'blocking' },
  { check_name: '附注完整性', passed: false, status: 'not_applicable', reason: '底稿已裁剪', details: '',
    severity: 'warning' },
  { check_name: 'E1现金流', passed: false, status: 'error', reason: '检查异常：RuntimeError：boom', details: '',
    severity: 'warning' },
]

const RISK = {
  high_findings: [], unresolved_comments: [], material_misstatements: [], unconverted_rejected_aje: [], ai_flags: [],
  budget_overrun: false, sla_breached: [], going_concern_flag: false,
  summary: { total_blockers: 0, total_warnings: 0, can_sign: true },
}

function mountPage() {
  return mount(PartnerSignDecision, {
    global: { plugins: [ElementPlus], directives: { permission: {} } },
  })
}

function consistencyCard(w: ReturnType<typeof mountPage>) {
  return w.findAll('.gt-psd-stale-card').find(c => c.find('.gt-psd-stale-card-label').text() === '一致性')
}

describe('签字决策页一致性卡片（五态）', () => {
  beforeEach(() => {
    get.mockReset(); message.mockReset()
    get.mockImplementation(async (url: string) => {
      if (url.includes('/workflow/consistency-check')) return { checks: CHECKS }
      if (url.includes('risk')) return RISK
      return {}
    })
  })

  it('请求一致性检查展示端点（带页面年度），计数只算「通过」', async () => {
    const w = mountPage()
    await flushPromises()
    expect(get.mock.calls.some(([url]) => url === '/api/projects/p1/workflow/consistency-check?year=2025')).toBe(true)
    const card = consistencyCard(w)
    expect(card, '找不到「一致性」卡片').toBeTruthy()
    expect(card!.find('.gt-psd-stale-card-value').text()).toBe('1/5') // 未执行 / 不适用 / 异常不算通过
    w.unmount()
  })

  it('点卡片：非通过项写五态标签与原因，不只分 ✓ / ✗', async () => {
    const w = mountPage()
    await flushPromises()
    await consistencyCard(w)!.trigger('click')
    expect(message).toHaveBeenCalledTimes(1)
    const lines = String(message.mock.calls[0][0].message).split('\n')
    expect(lines).toEqual([
      '✓ 试算平衡【通过】：借贷平衡',
      '✗ 报表平衡【失败】：资产≠负债+权益，差额 10.00',
      '✗ D4勾稽:营业收入合计=主营+其他【未执行（数据缺失）】：数据不完整，跳过检查',
      '✗ 附注完整性【不适用】：底稿已裁剪',
      '✗ E1现金流【检查异常】：检查异常：RuntimeError：boom',
    ])
    w.unmount()
  })

  it('接口没给出检查状态：不按 passed 记通过', async () => {
    get.mockImplementation(async (url: string) => {
      if (url.includes('/workflow/consistency-check')) return { checks: [{ check_name: '试算平衡', passed: true }] }
      if (url.includes('risk')) return RISK
      return {}
    })
    const w = mountPage()
    await flushPromises()
    expect(consistencyCard(w)!.find('.gt-psd-stale-card-value').text()).toBe('0/1')
    await consistencyCard(w)!.trigger('click')
    expect(String(message.mock.calls[0][0].message)).toBe('✗ 试算平衡【检查异常】：接口未返回检查状态')
    w.unmount()
  })
})
