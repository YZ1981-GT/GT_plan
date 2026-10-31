/**
 * 就绪页上的一致性门禁提示（spec formula-hub-integrity-closure 第 2 轮 S1 / D-4，需求 16.4、16.5）。
 *
 * 后端原先把门禁枚举 str() 后输出（'GateSeverity.warning'），分组状态停在「通过」、默认折叠，严重级标签显示原文。
 * 本文件挂载两个真实就绪页（签字决策页 / 归档向导第 1 步，GateReadinessPanel 不打桩），接口返回后端端点用例
 * test_consistency_gate_endpoints_pg.py 写下的同一份规整快照（「一致性规则是唯一信号」时的真实响应），断言：
 * 提示所在分组「其他门禁规则」展开、分组与提示的标签是中文（警告 / 阻断），提示原文可见，页面没有「GateSeverity.」等原文。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { computed, ref } from 'vue'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const REPO = resolve(__dirname, '../../../../../..')
function snapshot(gate: 'sign_off' | 'export_package', mode: 'observe' | 'enforce') {
  const file = resolve(REPO, `backend/tests/formula_hub/_snapshots/readiness_${gate}_${mode}.json`)
  return JSON.parse(readFileSync(file, 'utf-8'))
}

const { get, signReadiness, archiveReadiness, stub } = vi.hoisted(() => ({
  get: vi.fn(), signReadiness: vi.fn(), archiveReadiness: vi.fn(),
  stub: (name: string) => ({ default: { name, render: () => null } }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p1', year: '2025' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('@/services/signatureApi', () => ({ getSignReadinessV2: signReadiness, signDocument: vi.fn() }))
vi.mock('@/services/archiveApi', () => ({
  getArchiveReadiness: archiveReadiness, startArchiveOrchestrate: vi.fn(), getArchiveJob: vi.fn(),
  retryArchiveJob: vi.fn(), downloadArchivePackage: vi.fn(),
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
vi.mock('@/composables/useApiError', () => ({ showApiError: vi.fn(), parseApiError: vi.fn() }))
vi.mock('@/components/common/GtPageHeader.vue', () => stub('GtPageHeader'))
vi.mock('@/components/common/SignoffChecklist.vue', () => stub('SignoffChecklist'))

import PartnerSignDecision from '@/views/PartnerSignDecision.vue'
import ArchiveWizard from '@/views/ArchiveWizard.vue'
import GateReadinessPanel from '@/components/gate/GateReadinessPanel.vue'

const RAW = ['GateSeverity.', 'GateDecisionResult.', 'GateType.']
const LABEL = { observe: '警告', enforce: '阻断' } as const
// 签字决策页右栏风险摘要（与本条无关，给空摘要让整页渲染）
const RISK = {
  high_findings: [], unresolved_comments: [], material_misstatements: [], unconverted_rejected_aje: [], ai_flags: [],
  budget_overrun: false, sla_breached: [], going_concern_flag: false,
  summary: { total_blockers: 0, total_warnings: 0, can_sign: true },
}

function miscItem(w: VueWrapper) {
  const panel = w.findComponent(GateReadinessPanel)
  expect(panel.exists(), '就绪页没有挂 GateReadinessPanel').toBe(true)
  const item = panel.findAll('.el-collapse-item').find(i => i.text().includes('其他门禁规则'))
  expect(item, '没有「其他门禁规则」分组').toBeTruthy()
  return item!
}

function assertHint(w: VueWrapper, mode: 'observe' | 'enforce') {
  const item = miscItem(w)
  expect(item.classes(), '提示所在分组应默认展开（非通过组）').toContain('is-active')
  expect(item.find('.gt-gate-group-title .el-tag').text()).toBe(LABEL[mode])
  const finding = item.find('.gt-gate-finding')
  expect(finding.find('.el-tag').text()).toBe(LABEL[mode])
  expect(finding.find('.gt-gate-finding-msg').text()).toMatch(
    mode === 'observe' ? /一致性检查有 N 项未通过或未执行（当前为只提示模式）/ : /请补齐数据后重新检查/,
  )
  for (const raw of RAW) expect(w.html()).not.toContain(raw)
}

describe('就绪页一致性门禁提示（后端真实响应快照）', () => {
  beforeEach(() => {
    get.mockReset(); signReadiness.mockReset(); archiveReadiness.mockReset()
    get.mockImplementation(async (url: string) => {
      if (url.includes('completeness')) return { categories: [], can_proceed: true, generated_at: '' }
      if (url.includes('risk')) return RISK
      return {}
    })
  })

  it.each(['observe', 'enforce'] as const)('签字决策页（sign_off，%s）', async (mode) => {
    signReadiness.mockResolvedValue(snapshot('sign_off', mode))
    const w = mount(PartnerSignDecision, { global: { plugins: [ElementPlus], directives: { permission: {} } } })
    await flushPromises()
    expect(signReadiness).toHaveBeenCalledWith('p1')
    assertHint(w, mode)
    w.unmount()
  })

  it.each(['observe', 'enforce'] as const)('归档向导第 1 步（export_package，%s）', async (mode) => {
    archiveReadiness.mockResolvedValue(snapshot('export_package', mode))
    const w = mount(ArchiveWizard, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(archiveReadiness).toHaveBeenCalledWith('p1')
    assertHint(w, mode)
    w.unmount()
  })
})
