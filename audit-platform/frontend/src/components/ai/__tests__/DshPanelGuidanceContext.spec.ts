import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import DshPanel from '../DshPanel.vue'
import {
  useGuidancePanelStore,
  type GuidanceResponse,
  type WpContext,
} from '@/stores/guidancePanelStore'

const PROJECT_ID = '22222222-2222-2222-2222-222222222222'
const WP_ID = '11111111-1111-1111-1111-111111111111'

vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: {
      projectId: '22222222-2222-2222-2222-222222222222',
      wpId: '11111111-1111-1111-1111-111111111111',
    },
    query: {},
  }),
}))

vi.mock('@/composables/useAiHostContext', () => ({
  buildAmbientHost: () => ({
    available: true,
    host: {
      type: 'workpaper',
      id: '11111111-1111-1111-1111-111111111111',
      projectId: '22222222-2222-2222-2222-222222222222',
      year: '2025',
    },
    label: '当前底稿',
    projectToolsEnabled: true,
  }),
}))

const PlatformAiChatPanelStub = defineComponent({
  name: 'PlatformAiChatPanel',
  props: {
    host: { type: Object, required: true },
    visible: { type: Boolean, default: false },
    sheetName: { type: String, default: undefined },
  },
  template: '<div class="chat-stub">{{ sheetName || "NO_SHEET" }}</div>',
})

function context(overrides: Partial<WpContext> = {}): WpContext {
  return {
    wpId: WP_ID,
    wpCode: 'D0',
    wpName: '函证',
    componentType: 'confirmation-hub',
    projectId: PROJECT_ID,
    year: 2025,
    sheetCode: 'D0-4b',
    sheetName: '询证函控制表D0-4b',
    host: 'html',
    wholeWorkbook: false,
    ...overrides,
  }
}

function response(): GuidanceResponse {
  return {
    wp_code: 'D0-4b',
    wp_name: '函证',
    requested_sheet_code: 'D0-4b',
    resolved_wp_code: 'D0-4b',
    inherited_from_parent: false,
    resolution_status: 'exact',
    resolution_reason: 'child_exact_static',
    source: 'static_json',
    complexity: 'high',
    guidance_version: 'guidance-v2-dsh',
    source_digest: 'd'.repeat(64),
    generated_at: '2026-09-07T00:00:00+00:00',
    missing_sections: [],
    ai_enabled: true,
    guidance: { sections: [], raw_text: '' },
    recommended_questions: [],
  }
}

function mountPanel() {
  return mount(DshPanel, {
    props: { modelValue: true },
    global: {
      stubs: {
        ElIcon: true,
        ElTooltip: { template: '<div><slot /></div>' },
        Transition: { template: '<div><slot /></div>' },
        PlatformAiChatPanel: PlatformAiChatPanelStub,
      },
    },
  })
}

describe('DshPanel — 消费当前底稿 guidance context', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('同 project/wp 时展示版本化状态并把当前 sheet 交给统一 AI 宿主', async () => {
    const store = useGuidancePanelStore()
    store.$patch({ wpContext: context(), guidanceData: response(), aiEnabled: true })

    const wrapper = mountPanel()
    await flushPromises()

    const chat = wrapper.findComponent(PlatformAiChatPanelStub)
    expect(chat.props('sheetName')).toBe('询证函控制表D0-4b')
    expect(wrapper.find('.dsh-panel-guidance-context').text()).toContain('询证函控制表D0-4b')
    expect(wrapper.find('.dsh-panel-guidance-context').text()).toContain('精确说明 · D0-4b')
    expect(wrapper.find('.dsh-panel-guidance-context').text()).toContain('guidance-v2-dsh')
    expect(wrapper.find('.dsh-panel-guidance-context').attributes('title')).toContain('d'.repeat(64))
  })

  it('宿主不匹配或整册语义时 fail-closed，不伪造 sheetName', async () => {
    const store = useGuidancePanelStore()
    store.$patch({
      wpContext: context({ projectId: '33333333-3333-3333-3333-333333333333' }),
      guidanceData: response(),
      aiEnabled: true,
    })
    const mismatch = mountPanel()
    await flushPromises()
    expect(mismatch.findComponent(PlatformAiChatPanelStub).props('sheetName')).toBeUndefined()
    expect(mismatch.find('.dsh-panel-guidance-context').exists()).toBe(false)
    mismatch.unmount()

    store.$patch({
      wpContext: context({ sheetCode: null, sheetName: '', host: 'onlyoffice', wholeWorkbook: true }),
      guidanceData: response(),
      aiEnabled: true,
    })
    const whole = mountPanel()
    await flushPromises()
    expect(whole.findComponent(PlatformAiChatPanelStub).props('sheetName')).toBeUndefined()
    expect(whole.find('.dsh-panel-guidance-context').text()).toContain('整册说明')
  })
})
