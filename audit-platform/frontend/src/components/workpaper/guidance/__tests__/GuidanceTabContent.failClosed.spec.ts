import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GuidanceTabContent from '../GuidanceTabContent.vue'
import type { GuidanceResponse } from '@/stores/guidancePanelStore'

vi.mock('@/composables/useSanitize', () => ({
  useSanitize: () => ({
    sanitizeHtml: () => {
      throw new Error('sanitize boom')
    },
  }),
}))

const stubs = {
  'el-tag': { template: '<span><slot /></span>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-collapse': { template: '<div><slot /></div>' },
  'el-collapse-item': { template: '<section><slot /></section>' },
  'el-input': { template: '<textarea />' },
}

function guidance(): GuidanceResponse {
  return {
    wp_code: 'D0-5',
    wp_name: '替代程序',
    requested_sheet_code: 'D0-5',
    resolved_wp_code: 'D0-5',
    inherited_from_parent: false,
    resolution_status: 'exact',
    resolution_reason: 'child_exact_static',
    source: 'static_json',
    complexity: 'high',
    guidance_version: 'guidance-v2-fail-closed',
    source_digest: 'e'.repeat(64),
    generated_at: '2026-09-07T00:00:00+00:00',
    missing_sections: [],
    ai_enabled: false,
    guidance: {
      sections: [{
        key: 'purpose',
        title: '编制目的',
        items: [
          '可读文字 <script>window.__guidanceFailClosed=1</script>'
          + '<img src=x onerror="window.__guidanceFailClosed=2">'
          + '<a href="javascript:alert(1)">危险链接</a>',
        ],
        source_refs: [{
          kind: 'xlsx',
          path: '<img src=x onerror="window.__sourceRefFailClosed=1">',
        }],
      }],
      raw_text: '',
    },
    recommended_questions: [],
  }
}

describe('GuidanceTabContent — sanitizer 异常纯文本 fail-closed', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    ;(window as any).__guidanceFailClosed = 0
    ;(window as any).__sourceRefFailClosed = 0
  })

  it('sanitize 抛错时保留可读文本但不创建任何可执行 DOM', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const wrapper = mount(GuidanceTabContent, {
      props: { guidanceData: guidance() },
      global: { plugins: [createPinia()], stubs },
    })

    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining('sanitize failed'),
      expect.any(Error),
    )
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.find('[onerror]').exists()).toBe(false)
    expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('可读文字 <script>window.__guidanceFailClosed=1</script>')
    expect(wrapper.text()).toContain('<img src=x onerror="window.__sourceRefFailClosed=1">')
    expect((window as any).__guidanceFailClosed).toBe(0)
    expect((window as any).__sourceRefFailClosed).toBe(0)
  })
})
