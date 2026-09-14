/**
 * B2 流程总览 — 函件状态台账 + 催函提示 + 适用性过滤（Wave4 Task13/16）
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), put: vi.fn() } }))
// Stub GtIndexChip（避免 router/route 注入噪声）
vi.mock('../GtIndexChip.vue', () => ({
  default: { name: 'GtIndexChip', props: ['value', 'validate'], template: '<span class="chip">{{ value }}</span>' },
}))

import GtB2FlowOverview from '../GtB2FlowOverview.vue'

const APPLIC_ALL = { firstEngagement: true, reviewPredecessorWp: true, ipoReaudit: true }

function mountFO(props: any = {}) {
  return mount(GtB2FlowOverview, {
    props: {
      wpIdMap: { 'B2-1': 'id1', 'B2-3': 'id3' },
      applicability: APPLIC_ALL,
      letterStatus: {},
      ...props,
    },
    global: { plugins: [ElementPlus] },
  })
}

describe('B2 流程总览', () => {
  it('三场景泳道渲染 + 适用性过滤', () => {
    const w = mountFO()
    expect(w.text()).toContain('① 接受委托前沟通')
    expect(w.text()).toContain('② 接受委托后底稿查阅')
    expect(w.text()).toContain('③ 重新审计 / IPO')

    const w2 = mountFO({ applicability: { ...APPLIC_ALL, reviewPredecessorWp: false } })
    expect(w2.text()).not.toContain('② 接受委托后底稿查阅')
    // 程序表/其他场景不受影响
    expect(w2.text()).toContain('① 接受委托前沟通')
  })

  it('未生成底稿点击 → 提示（不 emit open）', async () => {
    const w = mountFO({ wpIdMap: {} })  // 全部未生成
    // B2-1 名称可点击
    const name = w.findAll('.gt-b2-flow__name').find((n) => n.text().includes('向被审计单位'))
    await name!.trigger('click')
    expect(w.emitted('open')).toBeFalsy()
  })

  it('修改函件状态 → emit updateStatus（含合并已有状态）', async () => {
    const w = mountFO({ letterStatus: { 'B2-1': { sentDate: '2025-01-05' } } })
    // 第一个状态下拉即 B2-1
    const sel = w.findAllComponents({ name: 'ElSelect' })[0]
    await sel.vm.$emit('update:model-value', '已发函')
    const ev = w.emitted('updateStatus') as any[]
    expect(ev).toBeTruthy()
    expect(ev[0][0]).toBe('B2-1')
    // 合并已有 sentDate + 新 status
    expect(ev[0][1]).toMatchObject({ status: '已发函', sentDate: '2025-01-05' })
  })

  it('催函提示：B2-3 已发函 >14 天无回函 → 提示', () => {
    const oldDate = new Date(Date.now() - 20 * 86400000).toISOString().slice(0, 10)
    const w = mountFO({
      letterStatus: { 'B2-3': { status: '已发函', sentDate: oldDate } },
    })
    expect(w.text()).toContain('建议发第二封催函')
  })

  it('催函提示：B2-3 已回函 → 不提示', () => {
    const oldDate = new Date(Date.now() - 20 * 86400000).toISOString().slice(0, 10)
    const w = mountFO({
      letterStatus: { 'B2-3': { status: '已回函', sentDate: oldDate, replyDate: '2025-01-01' } },
    })
    expect(w.text()).not.toContain('建议发第二封催函')
  })
})
