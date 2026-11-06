/**
 * 显示偏好面板（spec platform-global-display-settings-closure R2 / R3 / AC-07）：
 * 顶栏「Aa」（compact）、`/display-settings` 与管理员系统设置共用同一个组件，只读写 displayPrefs store。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({
  getDisplayPreferences: vi.fn(),
  patchDisplayPreferences: vi.fn(),
}))

vi.mock('@/services/displayPreferencesApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/displayPreferencesApi')>()
  return { ...actual, getDisplayPreferences: api.getDisplayPreferences, patchDisplayPreferences: api.patchDisplayPreferences }
})

import DisplayPreferencesPanel from '../DisplayPreferencesPanel.vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useProjectStore } from '@/stores/project'
import { createDefaultDisplayPreferences } from '@/utils/displayPreferencesNormalizer'

function serverState(revision = 1) {
  return { ...createDefaultDisplayPreferences(), revision }
}

function mountPanel(compact = false) {
  return mount(DisplayPreferencesPanel, { props: { compact }, global: { plugins: [ElementPlus] } })
}

function radio(wrapper: ReturnType<typeof mountPanel>, testId: string, label: string) {
  const button = wrapper.find(`[data-testid="${testId}"]`).findAll('label').find((l) => l.text() === label)
  expect(button, `${testId} 里找不到「${label}」`).toBeTruthy()
  return button!
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  api.getDisplayPreferences.mockReset().mockResolvedValue(serverState())
  api.patchDisplayPreferences.mockReset().mockImplementation(async () => serverState(2))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('DisplayPreferencesPanel', () => {
  it('未登录：默认标准字号、跟随项目单位，并提示设置不会保存', () => {
    const wrapper = mountPanel()
    expect(radio(wrapper, 'dp-font-size', '标准').find('input').element.checked).toBe(true)
    expect(radio(wrapper, 'dp-amount-unit', '跟随项目').find('input').element.checked).toBe(true)
    expect(wrapper.get('[data-testid="dp-amount-unit-hint"]').text()).toBe('当前未进入项目，按元显示')
    expect(wrapper.get('[data-testid="dp-sync-status"]').text()).toContain('未登录，设置不会保存')
  })

  it('点选字号 / 单位即改 store；「跟随项目」清除个人单位', async () => {
    const wrapper = mountPanel()
    const prefs = useDisplayPrefsStore()
    await radio(wrapper, 'dp-font-size', '大字').find('input').setValue(true)
    expect(prefs.fontSize).toBe('lg')
    await radio(wrapper, 'dp-amount-unit', '万元').find('input').setValue(true)
    expect(prefs.amountUnitOverride).toBe('wan')
    expect(wrapper.get('[data-testid="dp-amount-unit-hint"]').text()).toBe('当前按个人设置显示：万元')
    await radio(wrapper, 'dp-amount-unit', '跟随项目').find('input').setValue(true)
    expect(prefs.amountUnitOverride).toBeNull()
  })

  it('跟随项目时提示写出项目默认单位', async () => {
    const project = useProjectStore()
    project.projectId = 'p1'
    project.projectAmountUnit = 'qian'
    const wrapper = mountPanel()
    expect(wrapper.get('[data-testid="dp-amount-unit-hint"]').text()).toBe('当前跟随项目默认单位：千元')
    project.projectAmountUnit = null
    await flushPromises()
    expect(wrapper.get('[data-testid="dp-amount-unit-hint"]').text()).toBe('项目默认单位尚未读取，暂按元显示')
  })

  it('紧凑形态不列固定列；完整形态列出已保存的固定列并可清除', async () => {
    expect(mountPanel(true).find('[data-testid="dp-fixed-empty"]').exists()).toBe(false)
    const prefs = useDisplayPrefsStore()
    const wrapper = mountPanel()
    expect(wrapper.find('[data-testid="dp-fixed-empty"]').exists()).toBe(true)
    prefs.setFixedColumns('trial-balance:detail', ['code', 'name'])
    await flushPromises()
    const rows = wrapper.findAll('[data-testid="dp-fixed-entry"]')
    expect(rows).toHaveLength(1)
    expect(rows[0].text()).toContain('trial-balance:detail')
    expect(rows[0].text()).toContain('2 列')
    await rows[0].get('button').trigger('click')
    expect(wrapper.findAll('[data-testid="dp-fixed-entry"]')).toHaveLength(0)
  })

  it('同步失败显示离线原因与「重试同步」，点击后重新提交', async () => {
    vi.useFakeTimers()
    const prefs = useDisplayPrefsStore()
    await prefs.loadForUser('u1')
    const wrapper = mountPanel()
    expect(wrapper.get('[data-testid="dp-sync-status"]').text()).toContain('已同步到账号')

    api.patchDisplayPreferences.mockRejectedValueOnce(new Error('Network Error'))
    prefs.setFontSize('md')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(prefs.syncState).toBe('offline')
    expect(wrapper.get('[data-testid="dp-sync-status"]').text()).toContain('显示偏好暂未同步')

    const retry = wrapper.get('[data-testid="dp-sync-retry"]')
    await retry.trigger('click')
    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()
    expect(api.patchDisplayPreferences).toHaveBeenCalledTimes(2)
    expect(prefs.syncState).not.toBe('offline')
    expect(wrapper.find('[data-testid="dp-sync-retry"]').exists()).toBe(false)
  })
})
