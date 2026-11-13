/**
 * 公式版本时间轴的操作人显示姓名，不显示用户 id（2026-11-09 浏览器走查发现原样显示 UUID）。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get } = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))

import FormulaTimelinePanel from '@/components/formula/FormulaTimelinePanel.vue'

const UID_A = 'b6f8e8d0-8b64-47ab-bbc3-bfaed2b51e98'
const UID_B = '11111111-2222-3333-4444-555555555555'

describe('公式时间轴：操作人', () => {
  it('有姓名显示姓名，没解析出姓名显示「未知用户」，均不露出用户 id', async () => {
    get.mockResolvedValue({
      events: [
        { type: 'formula_changed', timestamp: '2026-11-09T15:49:00Z', summary: '公式变更 · report', user_id: UID_A, user_name: '张三' },
        { type: 'formula_changed', timestamp: '2026-11-09T15:48:00Z', summary: '公式变更 · report', user_id: UID_B },
      ],
      event_types: {},
      unavailable_sources: [],
    })
    const w = mount(FormulaTimelinePanel, { props: { projectId: 'p1', year: 2025 }, global: { plugins: [ElementPlus] } })
    await flushPromises()
    const text = w.text()
    expect(text).toContain('操作人：张三')
    expect(text).toContain('操作人：未知用户')
    expect(text).not.toContain(UID_A)
    expect(text).not.toContain(UID_B)
    w.unmount()
  })
})
