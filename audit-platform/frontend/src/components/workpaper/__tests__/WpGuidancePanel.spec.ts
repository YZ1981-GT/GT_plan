import { beforeEach, describe, expect, it, vi } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { api } from '@/services/apiProxy'
import WpGuidancePanel from '../WpGuidancePanel.vue'
import {
  buildGuidanceContextIdentity,
  useGuidancePanelStore,
  type GuidanceResponse,
} from '@/stores/guidancePanelStore'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn() } }))

const payload: GuidanceResponse = {
  wp_code: 'D0-1', wp_name: '函证结果汇总', requested_sheet_code: 'D0-1',
  requested_sheet_name: 'D0-1', resolved_wp_code: 'D0-1', inherited_from_parent: false,
  resolution_status: 'exact', resolution_reason: 'child_exact_static',
  source: 'static_json', complexity: 'high', guidance_version: 'guidance-v2-panel',
  source_digest: 'c'.repeat(64), generated_at: '2026-09-07T00:00:00+00:00',
  missing_sections: [], ai_enabled: true,
  guidance: { sections: [], raw_text: '说明' }, recommended_questions: [],
}

const baseProps = {
  wpId: '11111111-1111-1111-1111-111111111111',
  wpCode: 'D0',
  wpName: '函证',
  componentType: 'confirmation-hub',
  projectId: '22222222-2222-2222-2222-222222222222',
  year: 2025,
  sheetCode: 'D0-1',
  sheetName: '函证结果汇总 D0-1',
  host: 'html' as const,
  wholeWorkbook: false,
}

describe('WpGuidancePanel — 单一 fetch owner 与统一 AI 承载', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    vi.clearAllMocks()
    setActivePinia(createPinia())
    vi.mocked(api.get).mockResolvedValue(payload)
  })

  it('mount 与同 context 重渲染不产生双请求，切 sheet 仅新增一次请求', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = shallowMount(WpGuidancePanel, {
      props: baseProps,
      global: {
        plugins: [pinia],
        stubs: { 'el-icon': true, 'el-button': true, 'el-skeleton': true },
      },
    })

    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(1))
    await wrapper.setProps({ wpName: '函证（重渲染）' })
    expect(api.get).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ sheetCode: 'D0-2', sheetName: '询证函控制 D0-2' })
    await vi.waitFor(() => expect(api.get).toHaveBeenCalledTimes(2))
    expect(vi.mocked(api.get).mock.calls[1][0]).toContain('sheet_code=D0-2')
  })

  it('不再挂载旧 AI 对话 Tab，折叠触发器属于布局流而非 fixed 宿主', () => {
    const wrapper = shallowMount(WpGuidancePanel, {
      props: baseProps,
      global: {
        plugins: [createPinia()],
        stubs: { 'el-icon': true, 'el-button': true, 'el-skeleton': true },
      },
    })
    expect(wrapper.text()).not.toContain('AI 对话')
    expect(wrapper.find('.gt-guidance-trigger').exists()).toBe(true)
  })

  it('卸载只清理自己拥有的 context，不会误清另一个面板的新 context', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = shallowMount(WpGuidancePanel, {
      props: baseProps,
      global: {
        plugins: [pinia],
        stubs: { 'el-icon': true, 'el-button': true, 'el-skeleton': true },
      },
    })
    const store = useGuidancePanelStore()
    await vi.waitFor(() => expect(store.wpContext?.sheetCode).toBe('D0-1'))

    const newerContext = {
      ...store.wpContext!,
      sheetCode: 'D0-2',
      sheetName: '询证函控制 D0-2',
    }
    store.setWpContext(newerContext)
    const newerIdentity = buildGuidanceContextIdentity(newerContext)
    await vi.waitFor(() => expect(store.contextIdentity).toBe(newerIdentity))

    wrapper.unmount()
    expect(store.contextIdentity).toBe(newerIdentity)
    expect(store.wpContext?.sheetCode).toBe('D0-2')
  })
})
