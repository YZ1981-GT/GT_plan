/**
 * useVoucherCheckDialog — 打开 clone / override / save patch
 */
import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import { useVoucherCheckDialog } from '../useVoucherCheckDialog'

describe('useVoucherCheckDialog', () => {
  it('clones row on open and maps override to auto/yes/no', async () => {
    const modelValue = ref(false)
    const row = ref<{ id: string; qty: number; abnormalOverride: boolean | null } | null>(null)
    const dlg = useVoucherCheckDialog({ modelValue, row })

    row.value = { id: 'r1', qty: 10, abnormalOverride: null }
    modelValue.value = true
    await nextTick()
    expect(dlg.form.value?.qty).toBe(10)
    expect(dlg.overrideChoice.value).toBe('auto')

    dlg.form.value!.qty = 99
    expect(row.value.qty).toBe(10) // 不回写父行

    dlg.overrideChoice.value = 'yes'
    const patch = dlg.buildSavePatch()
    expect(patch).toEqual({ id: 'r1', qty: 99, abnormalOverride: true })
  })

  it('supports isCorrectOverride key for cutoff-style rows', async () => {
    const modelValue = ref(true)
    const row = ref({ id: 'c1', isCorrectOverride: false as boolean | null })
    const dlg = useVoucherCheckDialog({
      modelValue,
      row,
      overrideKey: 'isCorrectOverride',
      getOverride: (r) => r.isCorrectOverride,
    })
    await nextTick()
    expect(dlg.overrideChoice.value).toBe('no')
    dlg.overrideChoice.value = 'auto'
    expect(dlg.buildSavePatch()?.isCorrectOverride).toBeNull()
  })
})
