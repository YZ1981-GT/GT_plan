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

  it('已精编静态说明(missing)显示中性提示，不显示负面横幅与待补齐红标', () => {
    setActivePinia(createPinia())
    const wrapper = mount(GuidanceTabContent, {
      props: {
        guidanceData: guidance({
          resolved_wp_code: 'D4-7',
          resolution_status: 'missing',
          source: 'static_json',
          missing_sections: ['materials', 'evidence', 'completion', 'steps', 'common_errors'],
          guidance: {
            sections: [
              { key: 'purpose', title: '一、编制目的', items: ['按产品分析主营业务收入的结构、单价、单位成本与毛利率的本期/上期变动。'], source_refs: [] },
              { key: 'data_sources', title: '二、数据来源', items: ['从 D4-2 主营明细按产品汇总收入，从对应成本科目汇总成本。'], source_refs: [] },
              { key: 'formulas', title: '三、计算公式', items: ['毛利率 = 毛利 / 收入（收入为0返0）。'], source_refs: [] },
              { key: 'judgments', title: '四、审计关注点', items: ['毛利率变动超过5个百分点的产品须重点分析原因。'], source_refs: [] },
            ],
            raw_text: '按产品分析',
          },
        }),
      },
      global: { plugins: [createPinia()], stubs },
    })
    // 中性提示，且不出现负面横幅
    expect(wrapper.text()).toContain('以下为本底稿编制说明，供编制时参考')
    expect(wrapper.text()).not.toContain('尚未达到九段与来源引用完整标准')
    expect(wrapper.text()).not.toContain('待补齐')
    // 状态标签改为中性"编制说明"，不显示红色"内容待补齐"
    expect(wrapper.text()).not.toContain('内容待补齐')
    // 正文内容正常渲染
    expect(wrapper.text()).toContain('毛利率')
  })
})
