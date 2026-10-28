/**
 * A3 合并流程中控台（仅合并项目生成）。
 * 🔴 2026-10-02（26e5ef994）起 setup 调 useWorkpaperSyncBridge / capabilityForEntry / readStoreProjection 却没有 import
 *    ⇒ 挂载即 ReferenceError、整页空白，程序表改不了（真库 0 个合并项目，所以一直没人碰到）。
 * 执行说明写字段覆盖：scope 以 render-config 回传为准、年度取项目审计年度（spec audit-year-calendar-fallback-ratchet R0）。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const hoisted = vi.hoisted(() => ({ bridgeOptions: [] as any[], get: vi.fn(), post: vi.fn(), readStore: vi.fn() }))
vi.mock('../sync/workpaperSyncApi', () => ({ readStoreProjection: hoisted.readStore }))
vi.mock('../sync/useWorkpaperSyncBridge', async () => {
  const { ref } = await import('vue')
  return {
    WP_BRIDGE_IN_FLIGHT_STATES: [],
    useWorkpaperSyncBridge: (options: any) => {
      hoisted.bridgeOptions.push(options)
      return { mode: ref('html'), descriptor: ref(null), dirty: ref(false), lastError: ref(''),
        switchToOnlyOffice: vi.fn(), switchToHtml: vi.fn() }
    },
  }
})
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'p-a3' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/services/workpaperApi', () => ({ getWpIndex: vi.fn().mockResolvedValue([]) }))
vi.mock('@/services/apiProxy', () => ({ api: { get: hoisted.get, post: hoisted.post } }))

import GtA3ConsolidationConsole from '../GtA3ConsolidationConsole.vue'

const PROGRAMS = [
  { id: 'r1', program_no: 1, program_desc: '确定合并范围', program_category: '', status: 'pending' },
  { id: 'r2', program_no: 2, program_desc: '编制合并抵销分录', program_category: '', status: 'pending' },
]

function mountConsole() {
  return shallowMount(GtA3ConsolidationConsole, {
    // wpCode 与回传 scope 的表码不同：旧写法（编码拼 scope）就会写到读取方看不到的位置
    props: { wpId: 'wp-a3', sheetName: '合并流程程序表A3', schema: {}, projectId: 'p-a3', wpCode: 'A3C',
      htmlData: { programs: PROGRAMS, trim_decisions: [], override_scope: 'procedure_table:A3' } },
    global: { renderStubDefaultSlot: true, directives: { permission: {}, loading: {} } },
  })
}

describe('GtA3ConsolidationConsole', () => {
  it('挂载不抛错：同步桥按 A3 entry 建立', async () => {
    const wrapper = mountConsole()
    await flushPromises()
    expect(wrapper.exists()).toBe(true)
    const options = hoisted.bridgeOptions.at(-1)
    expect(options.entryId.value).toBe('xlsx/gt-a3-consolidation-console')
    expect(options.capability).toBeTruthy()
    // 切在线编辑前交给桥的投影：读不到时内部吞掉异常 ⇒ 漏 import 也只会静默变成空投影，这里钉住真读到了
    hoisted.readStore.mockResolvedValue({ expectedRevision: 7, projection: { rows: 2 } })
    await expect(options.flushHtml()).resolves.toEqual(
      { expectedRevision: 7, projection: { rows: 2 }, sheetKey: 'a3consolidationconsole-managed' })
    expect(hoisted.readStore).toHaveBeenCalledWith(
      { projectId: 'p-a3', wpId: 'wp-a3', entryId: 'xlsx/gt-a3-consolidation-console' })
  })

  it('改执行说明 ⇒ 按回传 scope 与项目审计年度写字段覆盖', async () => {
    hoisted.get.mockResolvedValue({ audit_year: 2025 })
    hoisted.post.mockResolvedValue({})
    const wrapper = mountConsole()
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.saveExecution({ ...PROGRAMS[1], execution_summary: '已复核抵销分录' })
    await flushPromises()
    expect(hoisted.post).toHaveBeenCalledWith('/api/workpapers/field-overrides', expect.objectContaining({
      project_id: 'p-a3', year: 2025, scope: 'procedure_table:A3', item_key: '2',
      field: 'execution_summary', value: '已复核抵销分录',
    }))
  })
})
