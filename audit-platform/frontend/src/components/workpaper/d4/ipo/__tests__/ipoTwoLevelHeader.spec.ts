/**
 * D4-26/D4-28 两级表头渲染层判据 —— 父组必须在 DOM 中真渲染并跨 5 列。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 5 · Task 12/13 · Property 24/25/32
 *
 * 🔴 判据落到 DOM（el-table 的分组表头 colspan），不是只查声明里有 group ——
 *    「声明对齐而 DOM 从未渲染」的死代码会假绿（G7 实测教训）。
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ElementPlus from 'element-plus'

import D4TabOverseas from '../D4TabOverseas.vue'
import D4TabCustomerChecklist from '../D4TabCustomerChecklist.vue'

// stub 平台重依赖（sync bridge / OO host / http / import-export），只验渲染层。
vi.mock('@/utils/http', () => ({ default: { get: vi.fn().mockRejectedValue(new Error('no ai')), post: vi.fn() } }))
vi.mock('../../../sync/WorkpaperSyncEditorHost.vue', () => ({ default: { name: 'WorkpaperSyncEditorHost', render: () => null } }))
vi.mock('../../../sync/workpaperSyncApi', () => ({ readStoreProjection: vi.fn() }))
vi.mock('../../../sync/workpaperSyncCapability', () => ({ capabilityForEntry: () => 'bidirectional' }))
vi.mock('../../../sync/useWorkpaperSyncBridge', () => ({
  WP_BRIDGE_IN_FLIGHT_STATES: [],
  useWorkpaperSyncBridge: () => ({
    mode: { value: 'html' }, state: { value: 'html_idle' }, descriptor: { value: null },
    feedback: { value: { kind: 'idle', message: '' } },
    switchToHtml: vi.fn(), switchToOnlyOffice: vi.fn(),
  }),
}))
vi.mock('../../../composables/useD4ImportExport', async () => {
  const { ref } = await import('vue')
  return {
    useD4ImportExport: () => ({
      exportTemplate: vi.fn(), exportData: vi.fn(), importData: vi.fn(), importing: ref(false),
    }),
  }
})

function mountTab(comp: any) {
  return mount(comp, {
    global: { plugins: [ElementPlus] },
    props: { wpId: 'wp1', projectId: 'p1', allResponses: new Map<string, any>(), isReadonly: false },
  })
}

async function findGroupColspan(wrapper: any, groupLabel: string): Promise<number> {
  await nextTick()
  await nextTick()
  const ths = wrapper.findAll('.el-table__header th, .el-table__header-wrapper th')
  for (const th of ths) {
    if (th.text().trim() === groupLabel) {
      const cs = th.attributes('colspan')
      return cs ? Number(cs) : 1
    }
  }
  return -1
}

describe('D4-26 两级表头（Property 24/25）', () => {
  it('父组「核查程序执行情况」在 DOM 中跨 5 列', async () => {
    const w = mountTab(D4TabOverseas)
    const span = await findGroupColspan(w, '核查程序执行情况')
    expect(span).toBe(5)
  })
})

describe('D4-28 两级表头（Property 32）', () => {
  it('父组「核查方式（√）」在 DOM 中跨 5 列', async () => {
    const w = mountTab(D4TabCustomerChecklist)
    const span = await findGroupColspan(w, '核查方式（√）')
    expect(span).toBe(5)
  })
})
