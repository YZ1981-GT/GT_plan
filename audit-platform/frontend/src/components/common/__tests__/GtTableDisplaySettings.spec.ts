import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

vi.mock('@/services/displayPreferencesApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/displayPreferencesApi')>()),
  getDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
  patchDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
}))

import GtTableDisplaySettings from '../GtTableDisplaySettings.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

beforeEach(async () => {
  localStorage.clear()
  setActivePinia(createPinia())
  await useDisplayPrefsStore().loadForUser('fixed-user')
})

describe('GtTableDisplaySettings', () => {
  it('无稳定 pageKey 时禁用设置入口', () => {
    const wrapper = mount(GtTableDisplaySettings, {
      props: { pageKey: '', columns: [{ key: 'code', label: '编码' }] }, global: { plugins: [ElementPlus] },
    })
    expect(wrapper.get('[data-testid="table-display-settings"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="table-display-settings"]').attributes('title')).toContain('缺少稳定身份')
  })

  it('旧表的失效固定列显示中文提示，mandatory 不可取消', async () => {
    useDisplayPrefsStore().setFixedColumns('table-x', ['gone', 'amount'])
    const wrapper = mount(GtTableDisplaySettings, {
      attachTo: document.body,
      props: {
        pageKey: 'table-x',
        columns: [{ key: 'code', label: '编码' }, { key: 'amount', label: '金额' }],
        mandatoryKeys: ['code'],
      },
      global: { plugins: [ElementPlus] },
    })
    await wrapper.get('[data-testid="table-display-settings"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(document.body.textContent).toContain('部分已固定列在当前表中不存在，已忽略')
    const required = document.body.querySelector('[data-mandatory="true"]')
    expect(required?.classList.contains('is-disabled')).toBe(true)
    wrapper.unmount()
  })
})
