/**
 * GtI1IntangibleAssets — sheetName 分发测试
 *
 * Spec: .kiro/specs/i1-intangible-assets/ Task 7.3
 * Validates: Requirements 1.2 (sheetName prop v-if 分发到对应子组件)
 *
 * 验证 GtI1IntangibleAssets.vue 根据 sheetName prop 正确分发到各子组件。
 * 使用 mount + stubs 模式检查哪个异步子组件被渲染。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

// ─── Mock http (selfLoad / TB 取数) ──────────────────────────────────────────
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { data: { sheets: [] } } }),
    put: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// ─── Mock composables ────────────────────────────────────────────────────────
vi.mock('../composables/useI1DualMode', () => ({
  useI1DualMode: () => ({
    currentMode: { value: 'html' },
    isOoAvailable: { value: false },
    checking: { value: false },
    modeOptions: [
      { label: '结构化视图', value: 'html' },
      { label: '在线编辑', value: 'onlyoffice' },
    ],
    onModeChange: vi.fn(),
  }),
}))

vi.mock('../composables/useVersionTrail', () => ({
  default: () => ({
    versions: { value: [] },
    isLoading: { value: false },
    loadVersions: vi.fn(),
    createSnapshot: vi.fn(),
  }),
}))

// ─── Stub components ─────────────────────────────────────────────────────────
// Each stub renders a unique data-testid so we can assert which one is shown

const makeStub = (name: string) =>
  defineComponent({
    name,
    template: `<div data-testid="${name}" />`,
  })

const stubs: Record<string, ReturnType<typeof defineComponent>> = {
  // core
  I1TabIndex: makeStub('I1TabIndex'),
  I1TabAdjudication: makeStub('I1TabAdjudication'),
  I1TabDetail: makeStub('I1TabDetail'),
  I1TabAdjustment: makeStub('I1TabAdjustment'),
  I1TabDisclosureListed: makeStub('I1TabDisclosureListed'),
  I1TabDisclosureSoe: makeStub('I1TabDisclosureSoe'),
  // inspection
  I1TabPolicyCheck: makeStub('I1TabPolicyCheck'),
  I1TabAdditionCheck: makeStub('I1TabAdditionCheck'),
  I1TabDisposalCheck: makeStub('I1TabDisposalCheck'),
  I1TabUsefulLifeCheck: makeStub('I1TabUsefulLifeCheck'),
  I1TabTitleCheck: makeStub('I1TabTitleCheck'),
  // amortization
  I1TabAmortizationAlloc: makeStub('I1TabAmortizationAlloc'),
  I1TabAmortizationNoImpair: makeStub('I1TabAmortizationNoImpair'),
  I1TabAmortizationWithImpair: makeStub('I1TabAmortizationWithImpair'),
  // impairment
  I1TabImpairmentTest: makeStub('I1TabImpairmentTest'),
  I1TabRecoverableTest: makeStub('I1TabRecoverableTest'),
  // shared / fallback
  CycleTabProcedure: makeStub('CycleTabProcedure'),
  GtOnlyOfficeSheet: makeStub('GtOnlyOfficeSheet'),
  // Element Plus stubs
  'el-skeleton': makeStub('el-skeleton'),
  'el-segmented': makeStub('el-segmented'),
  'el-tag': makeStub('el-tag'),
}

// ─── Helper ──────────────────────────────────────────────────────────────────

import GtI1IntangibleAssets from '../GtI1IntangibleAssets.vue'

async function mountWithSheet(sheetName: string) {
  const wrapper = mount(GtI1IntangibleAssets, {
    props: {
      wpId: 'wp-001',
      projectId: 'proj-001',
      sheetName,
    },
    global: {
      stubs,
    },
  })
  // Wait for onMounted selfLoad to complete
  await nextTick()
  await nextTick()
  return wrapper
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('GtI1IntangibleAssets sheetName 分发', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // 1. I1-2 → I1TabDetail
  it('sheetName 包含 "I1-2" → 渲染 I1TabDetail', async () => {
    const wrapper = await mountWithSheet('I1-2 无形资产明细表')
    expect(wrapper.find('[data-testid="I1TabDetail"]').exists()).toBe(true)
  })

  // 2. I1-3 → I1TabAdjustment
  it('sheetName 包含 "I1-3" → 渲染 I1TabAdjustment', async () => {
    const wrapper = await mountWithSheet('I1-3 调整分录汇总表')
    expect(wrapper.find('[data-testid="I1TabAdjustment"]').exists()).toBe(true)
  })

  // 3. I1-4 → I1TabPolicyCheck
  it('sheetName 包含 "I1-4" → 渲染 I1TabPolicyCheck', async () => {
    const wrapper = await mountWithSheet('I1-4 摊销减值政策检查表')
    expect(wrapper.find('[data-testid="I1TabPolicyCheck"]').exists()).toBe(true)
  })

  // 4. I1-5 → I1TabAdditionCheck
  it('sheetName 包含 "I1-5" → 渲染 I1TabAdditionCheck', async () => {
    const wrapper = await mountWithSheet('I1-5 无形资产增加检查表')
    expect(wrapper.find('[data-testid="I1TabAdditionCheck"]').exists()).toBe(true)
  })

  // 5. I1-6 → I1TabDisposalCheck
  it('sheetName 包含 "I1-6" → 渲染 I1TabDisposalCheck', async () => {
    const wrapper = await mountWithSheet('I1-6 无形资产减少明细表')
    expect(wrapper.find('[data-testid="I1TabDisposalCheck"]').exists()).toBe(true)
  })

  // 6. I1-7 → I1TabUsefulLifeCheck
  it('sheetName 包含 "I1-7" → 渲染 I1TabUsefulLifeCheck', async () => {
    const wrapper = await mountWithSheet('I1-7 使用寿命检查表')
    expect(wrapper.find('[data-testid="I1TabUsefulLifeCheck"]').exists()).toBe(true)
  })

  // 7. I1-8 → I1TabTitleCheck
  it('sheetName 包含 "I1-8" → 渲染 I1TabTitleCheck', async () => {
    const wrapper = await mountWithSheet('I1-8 无形资产权属检查表')
    expect(wrapper.find('[data-testid="I1TabTitleCheck"]').exists()).toBe(true)
  })

  // 8. I1-9 → I1TabAmortizationAlloc
  it('sheetName 包含 "I1-9" → 渲染 I1TabAmortizationAlloc', async () => {
    const wrapper = await mountWithSheet('I1-9 摊销分配分析表')
    expect(wrapper.find('[data-testid="I1TabAmortizationAlloc"]').exists()).toBe(true)
  })

  // 9. I1-10 → 分支选择器 (默认 noImpair → I1TabAmortizationNoImpair)
  it('sheetName 包含 "I1-10" → 渲染摊销分支选择器(默认不含减值)', async () => {
    const wrapper = await mountWithSheet('I1-10 摊销测算表（不含减值）')
    expect(wrapper.find('[data-testid="I1TabAmortizationNoImpair"]').exists()).toBe(true)
  })

  // 10. I1-11 → 分支选择器 (withImpair → I1TabAmortizationWithImpair)
  it('sheetName 包含 "I1-11" → 渲染摊销分支选择器(含减值)', async () => {
    const wrapper = await mountWithSheet('I1-11 摊销测算表（含减值）')
    expect(wrapper.find('[data-testid="I1TabAmortizationWithImpair"]').exists()).toBe(true)
  })

  // 11. I1-12 → I1TabImpairmentTest
  it('sheetName 包含 "I1-12" → 渲染 I1TabImpairmentTest', async () => {
    const wrapper = await mountWithSheet('I1-12 减值准备测试表')
    expect(wrapper.find('[data-testid="I1TabImpairmentTest"]').exists()).toBe(true)
  })

  // 12. I1-13 → I1TabRecoverableTest
  it('sheetName 包含 "I1-13" → 渲染 I1TabRecoverableTest', async () => {
    const wrapper = await mountWithSheet('I1-13 可收回金额测试')
    expect(wrapper.find('[data-testid="I1TabRecoverableTest"]').exists()).toBe(true)
  })

  // 13. "I1" (无后缀) → I1TabIndex
  it('sheetName 为 "I1" (无后缀) → 渲染 I1TabIndex', async () => {
    const wrapper = await mountWithSheet('I1 底稿目录')
    expect(wrapper.find('[data-testid="I1TabIndex"]').exists()).toBe(true)
  })

  // 14. "I1A" → CycleTabProcedure (程序表)
  it('sheetName 包含 "I1A" → 渲染 CycleTabProcedure (程序表)', async () => {
    const wrapper = await mountWithSheet('I1A 实质性程序表')
    expect(wrapper.find('[data-testid="CycleTabProcedure"]').exists()).toBe(true)
  })

  // 15. "附注上市" → I1TabDisclosureListed
  it('sheetName 包含 "附注上市" → 渲染 I1TabDisclosureListed', async () => {
    const wrapper = await mountWithSheet('附注披露信息（上市公司）')
    expect(wrapper.find('[data-testid="I1TabDisclosureListed"]').exists()).toBe(true)
  })

  // 16. "附注国企" → I1TabDisclosureSoe
  it('sheetName 包含 "附注国企" → 渲染 I1TabDisclosureSoe', async () => {
    const wrapper = await mountWithSheet('附注披露信息（国企）')
    expect(wrapper.find('[data-testid="I1TabDisclosureSoe"]').exists()).toBe(true)
  })

  // ─── 边界情况 ──────────────────────────────────────────────────────────────

  it('未匹配的 sheetName → 渲染 GtOnlyOfficeSheet fallback', async () => {
    const wrapper = await mountWithSheet('一些未知的sheet名称')
    expect(wrapper.find('[data-testid="GtOnlyOfficeSheet"]').exists()).toBe(true)
  })

  it('I1-1 审定表 → 渲染 I1TabAdjudication', async () => {
    const wrapper = await mountWithSheet('I1-1 审定表')
    expect(wrapper.find('[data-testid="I1TabAdjudication"]').exists()).toBe(true)
  })
})
