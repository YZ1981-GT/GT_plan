import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { ref } from 'vue'

vi.mock('@/services/displayPreferencesApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/displayPreferencesApi')>()),
  getDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
  patchDisplayPreferences: vi.fn().mockRejectedValue(new Error('offline')),
}))

import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { usePreferredFixedColumns } from '@/composables/usePreferredFixedColumns'

beforeEach(async () => {
  localStorage.clear()
  setActivePinia(createPinia())
  await useDisplayPrefsStore().loadForUser('fixed-user')
})

describe('usePreferredFixedColumns', () => {
  it('effective = mandatory ∪ (saved ∩ allowed)，顺序由当前 allowed 决定', () => {
    const prefs = useDisplayPrefsStore()
    expect(prefs.setFixedColumns('table-x', ['unknown', 'amount'])).toBe(true)
    const fixed = usePreferredFixedColumns({
      pageKey: 'table-x', allowedColumns: ['code', 'name', 'amount'], mandatoryColumns: ['code', 'name'],
    })
    expect(fixed.effectiveKeys.value).toEqual(['code', 'name', 'amount'])
    expect(fixed.staleKeys.value).toEqual(['unknown'])
    expect(fixed.fixedFor('code')).toBe('left')
    expect(fixed.fixedFor('unknown')).toBe(false)
  })

  it('save 过滤未知/重复键并恢复 mandatory，fixedFor 只返回 left|false', () => {
    const fixed = usePreferredFixedColumns({
      pageKey: 'table-x', allowedColumns: ['code', 'name', 'amount'], mandatoryColumns: ['code'],
    })
    expect(fixed.save(['amount', 'amount', 'unknown'])).toBe(true)
    expect(fixed.savedKeys.value).toEqual(['code', 'amount'])
    expect(new Set(['left', false])).toContain(fixed.fixedFor('amount'))
    expect(fixed.fixedFor('name')).toBe(false)
  })

  it('表 X 的保存不泄漏到表 Y；切回 X 仍生效', () => {
    const pageKey = ref('disclosure:table-x')
    const fixed = usePreferredFixedColumns({ pageKey, allowedColumns: ['label', 'c1'], mandatoryColumns: ['label'] })
    fixed.save(['c1'])
    expect(fixed.effectiveKeys.value).toEqual(['label', 'c1'])
    pageKey.value = 'disclosure:table-y'
    expect(fixed.effectiveKeys.value).toEqual(['label'])
    fixed.save([])
    pageKey.value = 'disclosure:table-x'
    expect(fixed.effectiveKeys.value).toEqual(['label', 'c1'])
  })

  it('normal / compare 模式身份互不影响', () => {
    const prefs = useDisplayPrefsStore()
    prefs.setFixedColumns('report-view:normal', ['note'])
    prefs.setFixedColumns('report-view:compare', ['variance'])
    expect(prefs.getFixedColumns('report-view:normal')).toEqual(['note'])
    expect(prefs.getFixedColumns('report-view:compare')).toEqual(['variance'])
  })
})
