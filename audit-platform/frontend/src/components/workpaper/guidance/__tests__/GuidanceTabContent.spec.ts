import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GuidanceTabContent from '../GuidanceTabContent.vue'
import { useGuidancePanelStore, type GuidanceResponse } from '@/stores/guidancePanelStore'

function guidance(overrides: Partial<GuidanceResponse> = {}): GuidanceResponse {
  return {
    wp_code: 'D0-4b',
    wp_name: '函证',
    requested_sheet_code: 'D0-4b',
    requested_sheet_name: 'D0-4b',
    resolved_wp_code: 'D0-4b',
    inherited_from_parent: false,
    resolution_status: 'exact',
    resolution_reason: 'child_exact_static',
    source: 'docx_instructions',
    complexity: 'high',
    guidance_version: 'guidance-v2-safe',
    source_digest: 'b'.repeat(64),
    generated_at: '2026-09-07T00:00:00+00:00',
    missing_sections: [],
    ai_enabled: false,
    guidance: {
      sections: [{
        key: 'purpose',
        title: '编制目的',
        items: ['核对 D0-4b <script>window.__guidanceXss=1</script><img src=x onerror="window.__guidanceXss=2"><a href="javascript:alert(1)">危险链接</a>'],
        source_refs: [{
          kind: 'docx',
          path: '<img src=x onerror="window.__sourceRefXss=1">',
          anchor: 'before_first_table',
        }],
      }],
      raw_text: '核对 D0-4b',
    },
    recommended_questions: ['是否已取得证据？'],
    ...overrides,
  }
}

const stubs = {
  'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-collapse': { template: '<div><slot /></div>' },
  'el-collapse-item': { template: '<section><slot /></section>' },
  'el-input': { template: '<textarea />' },
}

describe('GuidanceTabContent — 状态、来源与 XSS fail-closed', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    ;(window as any).__guidanceXss = 0
    ;(window as any).__sourceRefXss = 0
  })

  it('覆盖 docx source、resolution/version/source_ref 并保留复合 wp code chip', () => {
    const wrapper = mount(GuidanceTabContent, {
      props: { guidanceData: guidance() },
      global: { plugins: [createPinia()], stubs },
    })

    expect(wrapper.text()).toContain('Word 编制说明')
    expect(wrapper.text()).toContain('精确说明')
    expect(wrapper.text()).toContain('guidance-v2-safe')
    expect(wrapper.text()).toContain('before_first_table')
    expect(wrapper.find('.gt-guidance-wp-chip').text()).toBe('D0-4b')
  })

  it('分层展示 primary/overlays/extraction 与 completion 三轴', () => {
    const wrapper = mount(GuidanceTabContent, {
      props: {
        guidanceData: guidance({
          completion_status: 'partial',
          resolution_status: 'parent_inherited',
          resolution_reasons: ['child_missing_sections', 'using_parent_publication'],
          exact_blockers: ['missing_source_refs'],
          provenance: {
            primary: { kind: 'primary', source: 'static_json', path: 'backend/data/wp_guidance/D0.json' },
            overlays: [{ kind: 'overlay', source: 'template_header' }],
            extraction: [{ kind: 'extraction', source: 'template_sheet' }],
          },
        }),
      },
      global: { plugins: [createPinia()], stubs },
    })

    expect(wrapper.find('[data-testid="guidance-completion-badge"]').text()).toContain('部分完整')
    const provenance = wrapper.find('[data-testid="guidance-provenance"]')
    expect(provenance.text()).toContain('主来源')
    expect(provenance.text()).toContain('标准方法论')
    expect(provenance.text()).toContain('叠加层')
    expect(provenance.text()).toContain('模板页眉')
    expect(provenance.text()).toContain('抽取候选')
    expect(provenance.text()).toContain('模板说明页')
    expect(wrapper.text()).toContain('child_missing_sections')
    expect(wrapper.text()).toContain('missing_source_refs')
  })

  it('script、事件属性、javascript URL 与恶意 source_ref 均不能进入可执行 DOM', () => {
    const wrapper = mount(GuidanceTabContent, {
      props: { guidanceData: guidance() },
      global: { plugins: [createPinia()], stubs },
    })

    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('[onerror]').exists()).toBe(false)
    expect(wrapper.find('a[href^="javascript:"]').exists()).toBe(false)
    expect(wrapper.find('img').exists()).toBe(false)
    expect((window as any).__guidanceXss).toBe(0)
    expect((window as any).__sourceRefXss).toBe(0)
  })

  it('整册/继承/missing 显示中文阻断提示与九段缺口', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useGuidancePanelStore()
    store.$patch({
      wpContext: {
        wpId: 'wp', wpCode: 'D0', wpName: '函证', componentType: 'onlyoffice',
        projectId: 'project', year: 2025, sheetCode: null, sheetName: '',
        host: 'onlyoffice', wholeWorkbook: true,
      },
    })

    const wrapper = mount(GuidanceTabContent, {
      props: {
        guidanceData: guidance({
          resolved_wp_code: 'D0',
          inherited_from_parent: true,
          resolution_status: 'parent_inherited',
          missing_sections: ['purpose', 'evidence'],
        }),
      },
      global: { plugins: [pinia], stubs },
    })

    expect(wrapper.text()).toContain('当前为整册编辑')
    expect(wrapper.text()).toContain('显示 D0 父级说明')
    expect(wrapper.text()).toContain('待补齐')
    expect(wrapper.text()).toContain('编制目的')
    expect(wrapper.text()).toContain('审计证据')
  })

  it('stale 同时伴随整册和继承时仍优先显示来源失效阻断提示', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useGuidancePanelStore()
    store.$patch({
      wpContext: {
        wpId: 'wp', wpCode: 'D0', wpName: '函证', componentType: 'onlyoffice',
        projectId: 'project', year: 2025, sheetCode: null, sheetName: '',
        host: 'onlyoffice', wholeWorkbook: true,
      },
    })

    const wrapper = mount(GuidanceTabContent, {
      props: {
        guidanceData: guidance({
          resolved_wp_code: 'D0',
          inherited_from_parent: true,
          resolution_status: 'stale',
          runtime_guidance_status: 'stale',
          stale_reasons: ['source_facts_changed'],
        }),
      },
      global: { plugins: [pinia], stubs },
    })

    expect(wrapper.text()).toContain('说明来源已变化')
    expect(wrapper.text()).toContain('重新发布后才能作为完成依据')
    expect(wrapper.text()).not.toContain('当前为整册编辑')
    expect(wrapper.text()).not.toContain('沿用 D0 编制说明')
  })
})
