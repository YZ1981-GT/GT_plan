/**
 * spec excel-style-table-editing R1 / R8.2 / R11：编辑方式持久化、全局快捷键与承接框、
 * 编辑中 Ctrl+S 先提交、切换在线编辑前（待写盘）先提交。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp } from 'vue'
import { createPinia, setActivePinia } from 'pinia'

// 偏好改为绑账号 + 分区缓存（spec platform-global-display-settings-closure R2/R3）后，
// loadForUser 会真发一次 GET；这里只测本机持久化，服务端按不可用处理。
vi.mock('@/services/displayPreferencesApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/displayPreferencesApi')>()),
  getDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
  patchDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
}))

import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DISPLAY_PREFERENCES_CACHE_PREFIX } from '@/utils/displayPreferencesNormalizer'
import { isInputFocused, shortcutManager } from '@/utils/shortcuts'
import { flushPendingWrites } from '@/components/workpaper/sync/pendingWrites'
import { gridPlugin } from '../plugin'
import { activeInput, cell, click, key, mountGrid, settle, sink, typeInSink, unmountAll } from './gridHarness'

afterEach(() => unmountAll())

describe('编辑方式设置（R1）', () => {
  it('默认 Excel；切换后持久化到本账号分区；非法值忽略；读到非法存档回到默认', async () => {
    const prefs = useDisplayPrefsStore()
    expect(prefs.gridEditMode).toBe('excel')

    await prefs.loadForUser('u-grid')
    prefs.setGridEditMode('click')
    const key = `${DISPLAY_PREFERENCES_CACHE_PREFIX}u-grid`
    const cached = JSON.parse(localStorage.getItem(key)!)
    expect(cached.pendingScalars.gridEditMode.value).toBe('click')

    prefs.setGridEditMode('bogus' as never)
    expect(prefs.gridEditMode, '非法值必须忽略，不能回落默认把当前选择清掉').toBe('click')

    localStorage.setItem(key, JSON.stringify({
      version: 3, prefs: { grid_edit_mode: 'nope' }, revision: 1, cachedAt: Date.now(),
    }))
    setActivePinia(createPinia())
    const reloaded = useDisplayPrefsStore()
    await reloaded.loadForUser('u-grid')
    expect(reloaded.gridEditMode).toBe('excel')
    expect(reloaded.gridEditModeOptions.map((o) => o.label)).toEqual(['Excel', '单击编辑', '经典'])
  })

  it('未登录不落盘（偏好绑账号）', () => {
    localStorage.clear()
    const prefs = useDisplayPrefsStore()
    prefs.setGridEditMode('classic')
    expect(prefs.gridEditMode).toBe('classic')
    expect(Object.keys(localStorage).filter((k) => k.startsWith(DISPLAY_PREFERENCES_CACHE_PREFIX))).toEqual([])
  })
})

const TABLE = `
<el-table :data="rows">
  <el-table-column label="名称"><template #default="{ row }"><el-input :model-value="row.name" @change="(v) => row.name = v" /></template></el-table-column>
</el-table>`

describe('全局快捷键（R8.2）', () => {
  it('承接框不算输入框：选中格时 Ctrl+S 等全局快捷键照常', async () => {
    const w = await mountGrid(TABLE, () => ({ rows: [{ name: '甲' }] }))
    click(cell(w, 0, 0))
    const ev = new KeyboardEvent('keydown', { key: 's', ctrlKey: true })
    Object.defineProperty(ev, 'target', { value: sink(w) })
    expect(isInputFocused(ev)).toBe(false)
  })

  it('编辑中 Ctrl+S：先提交这一格，再执行保存', async () => {
    const w = await mountGrid(TABLE, () => ({ rows: [{ name: '甲' }] }))
    const data = (w.vm as unknown as { rows: Array<{ name: string }> }).rows
    const seen: string[] = []
    const prev = shortcutManager.getAll().find((s) => s.key === 'Ctrl+S')
    shortcutManager.register('Ctrl+S', () => { seen.push(data[0].name) }, '测试')
    try {
      click(cell(w, 0, 0))
      typeInSink(sink(w), '乙')
      await settle()
      const input = activeInput(w)
      const ev = new KeyboardEvent('keydown', { key: 's', ctrlKey: true, bubbles: true, cancelable: true })
      Object.defineProperty(ev, 'target', { value: input })
      shortcutManager.handleKeydown(ev)
      expect(seen).toEqual(['乙'])
    } finally {
      if (prev) shortcutManager.register(prev.key, prev.handler, prev.description, prev.scope)
      else shortcutManager.unregister('Ctrl+S')
    }
  })

  it('输入框里（非表格）仍按原规则忽略全局快捷键', () => {
    const input = document.createElement('input')
    document.body.appendChild(input)
    const ev = new KeyboardEvent('keydown', { key: 's', ctrlKey: true })
    Object.defineProperty(ev, 'target', { value: input })
    expect(isInputFocused(ev)).toBe(true)
  })
})

describe('切换在线编辑前提交（R11）', () => {
  it('插件登记待写盘：flushPendingWrites 提交表格里正在编辑的格', async () => {
    createApp({}).use(gridPlugin)
    const w = await mountGrid(TABLE, () => ({ rows: [{ name: '甲' }] }))
    const data = (w.vm as unknown as { rows: Array<{ name: string }> }).rows
    click(cell(w, 0, 0))
    typeInSink(sink(w), '改')
    await settle()
    expect(data[0].name).toBe('甲')
    await flushPendingWrites()
    await settle()
    expect(data[0].name).toBe('改')
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })

  it('切到经典方式时先提交正在编辑的格', async () => {
    const w = await mountGrid(TABLE, () => ({ rows: [{ name: '甲' }] }))
    const data = (w.vm as unknown as { rows: Array<{ name: string }> }).rows
    click(cell(w, 0, 0))
    typeInSink(sink(w), '丙')
    await settle()
    useDisplayPrefsStore().setGridEditMode('classic')
    await settle()
    expect(data[0].name).toBe('丙')
  })

  it('Esc 在选中态交还页面（弹窗照常可关）', async () => {
    const w = await mountGrid(TABLE, () => ({ rows: [{ name: '甲' }] }))
    const docEsc = vi.fn()
    document.addEventListener('keydown', docEsc)
    click(cell(w, 0, 0))
    key(sink(w), 'Escape')
    document.removeEventListener('keydown', docEsc)
    expect(docEsc).toHaveBeenCalledTimes(1)
  })
})
