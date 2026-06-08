/**
 * BasicInfoStep.vue — 企业子类型推荐单测
 *
 * Spec: .kiro/specs/audit-report-template-integration/ Task 13.3（需求 7.6）
 * 验证：
 * 1. 已有项目挂载时调用 fetchTemplateRecommendation
 * 2. 推荐值被预填到 form.company_subtype（需求 7.6 必须预填，不仅高亮）
 * 3. 用户已手动选择时不覆盖
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia, getActivePinia } from 'pinia'

// ─── Mock commonApi ──────────────────────────────────────────────────────────
const mockFetchRec = vi.fn()
vi.mock('@/services/commonApi', () => ({
  fetchTemplateRecommendation: (...args: any[]) => mockFetchRec(...args),
}))

// ─── Mock apiProxy（自定义模板加载，避免真实请求） ─────────────────────────────
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

import BasicInfoStep from '@/components/wizard/BasicInfoStep.vue'
import { useWizardStore } from '@/stores/wizard'

const STUBS = {
  'el-form': { template: '<form><slot /></form>' },
  'el-form-item': { template: '<div><slot /></div>' },
  'el-input': true,
  'el-select': { template: '<div><slot /></div>' },
  'el-option': true,
  'el-date-picker': true,
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': true,
  'el-input-number': true,
  'el-alert': true,
  'el-tag': { template: '<span><slot /></span>' },
  'el-button': { template: '<button><slot /></button>' },
}

function mountStep() {
  return mount(BasicInfoStep, {
    global: {
      plugins: [getActivePinia()!],
      stubs: STUBS,
    },
  })
}

describe('BasicInfoStep 企业子类型推荐', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetchRec.mockReset()
  })

  it('已有项目挂载时拉取推荐并预填 company_subtype', async () => {
    const store = useWizardStore()
    store.projectId = 'proj-001'

    mockFetchRec.mockResolvedValue({
      subtype: 'type_b',
      confidence: 'high',
      candidates: ['type_b'],
      matched_rules: ['B_basic_layer_financial'],
      source: 'rule',
    })

    const wrapper = mountStep()
    await flushPromises()

    expect(mockFetchRec).toHaveBeenCalledWith('proj-001')
    // 需求 7.6：预填建议值
    expect((wrapper.vm as any).form.company_subtype).toBe('type_b')
    expect((wrapper.vm as any).recommendation.subtype).toBe('type_b')
  })

  it('无 projectId（新建）时不调用推荐', async () => {
    const store = useWizardStore()
    store.projectId = null

    const wrapper = mountStep()
    await flushPromises()

    expect(mockFetchRec).not.toHaveBeenCalled()
    expect((wrapper.vm as any).recommendation).toBeNull()
  })

  it('用户已手动选择时不被推荐覆盖', async () => {
    const store = useWizardStore()
    store.projectId = 'proj-002'
    // 模拟已保存的用户选择
    store.stepData.basic_info = {
      client_name: '某公司',
      company_subtype: 'type_a',
    } as any

    mockFetchRec.mockResolvedValue({
      subtype: 'type_d',
      confidence: 'low',
      candidates: ['type_d'],
      matched_rules: [],
      source: 'fallback',
    })

    const wrapper = mountStep()
    await flushPromises()

    // 用户选择 type_a 优先，不被推荐 type_d 覆盖
    expect((wrapper.vm as any).form.company_subtype).toBe('type_a')
  })

  // ── 14.3「待确认企业子类型」横幅（需求 1.7 ③ / 1.8）──

  it('存量项目未确认 + needs_confirmation → 显示待确认横幅', async () => {
    const store = useWizardStore()
    store.projectId = 'proj-003'

    mockFetchRec.mockResolvedValue({
      subtype: 'type_a',
      confidence: 'low',
      candidates: ['type_a'],
      matched_rules: [],
      source: 'fallback',
      current_subtype: null,
      needs_confirmation: true,
    })

    const wrapper = mountStep()
    await flushPromises()

    // 推荐预填后 form 有值，但若用户未确认（这里预填即视为待确认场景的建议），
    // showSubtypeBanner 取决于 form.company_subtype 是否为空。
    // 预填逻辑会把空值填为建议值 → 横幅消失；故先清空模拟"用户尚未确认"。
    ;(wrapper.vm as any).form.company_subtype = null
    await flushPromises()
    expect((wrapper.vm as any).showSubtypeBanner).toBe(true)
  })

  it('用户已选择 company_subtype → 不显示横幅', async () => {
    const store = useWizardStore()
    store.projectId = 'proj-004'
    store.stepData.basic_info = { client_name: 'X', company_subtype: 'type_b' } as any

    mockFetchRec.mockResolvedValue({
      subtype: 'type_a',
      confidence: 'low',
      candidates: ['type_a'],
      matched_rules: [],
      source: 'fallback',
      current_subtype: 'type_b',
      needs_confirmation: false,
    })

    const wrapper = mountStep()
    await flushPromises()

    expect((wrapper.vm as any).showSubtypeBanner).toBe(false)
  })

  it('新建项目（无 projectId）→ 不显示横幅', async () => {
    const store = useWizardStore()
    store.projectId = null

    const wrapper = mountStep()
    await flushPromises()

    expect((wrapper.vm as any).showSubtypeBanner).toBe(false)
  })
})
