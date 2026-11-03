/**
 * TemplateLibraryMgmt.deeplink.spec.ts — 模板库读 `?tab=` / `?wp_code=`（advanced-query-linkage-closure 任务 32；ADR-AQL-17，R7.4）
 *
 * 高级查询结果右键「跳模板溯源」落到 `/template-library?tab=wp-template&wp_code=<编码>`：页面按 `?tab` 选页签（原先恒停在
 * 底稿模板、且后端给的页签名 workpaper 页面认不出），把 `?wp_code` 作为底稿模板页签的初始搜索；已在本页时再次跳入也切换。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'

const { stubModule } = vi.hoisted(() => ({
  stubModule: async (name: string, props: string[] = []) => {
    const { defineComponent, h } = await import('vue')
    return { default: defineComponent({ name, props, setup: () => () => h('div', { class: `stub-${name}` }) }) }
  },
}))
vi.mock('vue-router', async () => {
  const { reactive } = await import('vue')
  const route = reactive({ params: {} as Record<string, string>, query: {} as Record<string, string> })
  return { useRoute: () => route, useRouter: () => ({ push: vi.fn() }), __route: route }
})
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}) } }))
vi.mock('@/components/template-library/WpTemplateTab.vue', () => stubModule('WpTemplateTab', ['projectId', 'initialSearch']))
vi.mock('@/components/template-library/FormulaTab.vue', () => stubModule('FormulaTab'))
vi.mock('@/components/template-library/AuditReportTab.vue', () => stubModule('AuditReportTab'))
vi.mock('@/components/template-library/NoteTemplateTab.vue', () => stubModule('NoteTemplateTab'))
vi.mock('@/components/template-library/GtCodingTab.vue', () => stubModule('GtCodingTab', ['projectId']))
vi.mock('@/components/template-library/ReportConfigTab.vue', () => stubModule('ReportConfigTab'))
vi.mock('@/components/template-library/EnumDictTab.vue', () => stubModule('EnumDictTab'))
vi.mock('@/components/template-library/CustomQueryTab.vue', () => stubModule('CustomQueryTab'))
vi.mock('@/components/template-library/SeedLoaderPanel.vue', () => stubModule('SeedLoaderPanel'))
vi.mock('@/components/template-library/WpTemplateDetail.vue', () => stubModule('WpTemplateDetail', ['wpCode', 'projectId']))
vi.mock('@/components/template-library/VersionHistoryDialog.vue', () => stubModule('VersionHistoryDialog'))
vi.mock('@/components/template-library/TemplateLibraryManualDialog.vue', () => stubModule('TemplateLibraryManualDialog'))

import ElementPlus from 'element-plus'
import * as vueRouter from 'vue-router'
import TemplateLibraryMgmt from '../TemplateLibraryMgmt.vue'

const route = (vueRouter as unknown as { __route: { query: Record<string, string> } }).__route
let wrapper: VueWrapper<any> | null = null
async function mountPage(query: Record<string, string>) {
  route.query = query
  wrapper = mount(TemplateLibraryMgmt, { global: { plugins: [ElementPlus] } }) as unknown as VueWrapper<any>
  await flushPromises()
  return wrapper
}

beforeEach(() => { route.query = {} })
afterEach(() => { wrapper?.unmount(); wrapper = null })

describe('模板库按路由选页签（ADR-AQL-17）', () => {
  it('?tab=wp-template&wp_code=A1：底稿模板页签，搜索种入 A1', async () => {
    const w = await mountPage({ tab: 'wp-template', wp_code: 'A1' })
    expect(w.vm.activeTab).toBe('wp-template')
    expect(w.findComponent({ name: 'WpTemplateTab' }).props('initialSearch')).toBe('A1')
  })

  it('?tab=report-config / note-template：打开对应页签', async () => {
    const w = await mountPage({ tab: 'report-config', report_type: 'balance_sheet' })
    expect(w.vm.activeTab).toBe('report-config')
    expect(w.findComponent({ name: 'ReportConfigTab' }).exists()).toBe(true)
    expect(w.findComponent({ name: 'WpTemplateTab' }).exists()).toBe(false)
    wrapper!.unmount()
    const n = await mountPage({ tab: 'note-template' })
    expect(n.vm.activeTab).toBe('note-template')
  })

  it('不是本页页签名（含旧后端给的 workpaper）：停在底稿模板，不带搜索', async () => {
    const w = await mountPage({ tab: 'workpaper' })
    expect(w.vm.activeTab).toBe('wp-template')
    expect(w.findComponent({ name: 'WpTemplateTab' }).props('initialSearch')).toBe('')
  })

  it('已在本页时再次跳入（?tab 变了）：切到对应页签', async () => {
    const w = await mountPage({})
    expect(w.vm.activeTab).toBe('wp-template')
    route.query = { tab: 'note-template', section_id: '五-1-1' }
    await nextTick()
    expect(w.vm.activeTab).toBe('note-template')
  })
})
