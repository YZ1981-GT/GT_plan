/**
 * WpTemplateTab.initialSearch.spec.ts — 底稿模板页签的初始搜索（advanced-query-linkage-closure 任务 32；ADR-AQL-17，R7.4）
 *
 * 「跳模板溯源」带来的底稿编码种入搜索框（不等防抖即生效）并标出该底稿；已在本页时换了编码也重新种入。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: apiMocks, default: apiMocks }))

import ElementPlus from 'element-plus'
import WpTemplateTab from '../WpTemplateTab.vue'

const TEMPLATES = [
  { wp_code: 'A1', wp_name: '财务报告程序表', cycle: 'A', cycle_name: 'A 报表' },
  { wp_code: 'A10', wp_name: '报表附注', cycle: 'A', cycle_name: 'A 报表' },
  { wp_code: 'E1', wp_name: '货币资金', cycle: 'E', cycle_name: 'E 货币资金' },
]

let wrapper: VueWrapper<any> | null = null
async function mountTab(props: Record<string, unknown>) {
  wrapper = mount(WpTemplateTab, { props: { projectId: 'p1', ...props }, global: { plugins: [ElementPlus] } }) as unknown as VueWrapper<any>
  await flushPromises()
  return wrapper
}

beforeEach(() => { apiMocks.get.mockReset().mockResolvedValue(TEMPLATES) })
afterEach(() => { wrapper?.unmount(); wrapper = null })

describe('WpTemplateTab 初始搜索', () => {
  it('种入编码：立即按它筛选并标出该底稿', async () => {
    const w = await mountTab({ initialSearch: 'E1' })
    expect(w.vm.searchInput).toBe('E1')
    expect(w.vm.filteredCount).toBe(1)
    expect(w.vm.selectedWpCode).toBe('E1')
    expect(w.find('.gt-tree-selected').text()).toContain('E1')
  })

  it('没有初始搜索：显示全部；换了编码重新种入', async () => {
    const w = await mountTab({})
    expect(w.vm.searchInput).toBe('')
    expect(w.vm.filteredCount).toBe(3)
    await w.setProps({ initialSearch: 'A1' })
    expect(w.vm.searchInput).toBe('A1')
    expect(w.vm.selectedWpCode).toBe('A1')
  })
})
