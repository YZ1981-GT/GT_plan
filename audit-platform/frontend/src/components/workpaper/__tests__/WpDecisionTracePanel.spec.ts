import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import WpDecisionTracePanel from '../WpDecisionTracePanel.vue'
import type { RenderDecisionWire } from '@/types/renderConfig'

const sampleTrace: RenderDecisionWire[] = [
  {
    sheet_key: '审定表',
    chosen_component_type: 'audit-sheet',
    candidate_sources: ['registry', 'fallback'],
    winning_source: 'registry',
    override_hit: false,
    redirect_applied: false,
  },
  {
    sheet_key: '程序表',
    chosen_component_type: 'univer',
    candidate_sources: ['fallback'],
    winning_source: 'fallback',
    override_hit: true,
    redirect_applied: false,
    fallback_reason: 'schema missing',
  },
]

describe('WpDecisionTracePanel', () => {
  it('shows empty state when trace is null or empty', () => {
    const nullWrap = mount(WpDecisionTracePanel, { props: { trace: null } })
    expect(nullWrap.text()).toContain('暂无裁决轨迹')

    const emptyWrap = mount(WpDecisionTracePanel, { props: { trace: [] } })
    expect(emptyWrap.text()).toContain('暂无裁决轨迹')
  })

  it('renders decision rows with core fields', () => {
    const wrapper = mount(WpDecisionTracePanel, { props: { trace: sampleTrace } })
    expect(wrapper.text()).toContain('审定表')
    expect(wrapper.text()).toContain('audit-sheet')
    expect(wrapper.text()).toContain('registry')
    expect(wrapper.text()).toContain('程序表')
    expect(wrapper.text()).toContain('override')
    expect(wrapper.findAll('.gt-wp-decision-trace__item')).toHaveLength(2)
  })

  it('shows fallback_reason when present', () => {
    const wrapper = mount(WpDecisionTracePanel, { props: { trace: sampleTrace } })
    expect(wrapper.find('.gt-wp-decision-trace__fallback').text()).toContain('schema missing')
  })
})
