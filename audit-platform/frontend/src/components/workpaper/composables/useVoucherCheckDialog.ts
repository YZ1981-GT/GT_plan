/**
 * useVoucherCheckDialog — F2 凭证级「逐笔核对」弹窗公共状态
 *
 * 负责：打开时 clone 行、异常/正确结论 override、保存时拼 patch。
 * 字段布局与勾稽函数仍由各 sheet Dialog SFC 负责。
 */
import { ref, watch, type Ref } from 'vue'

export type VoucherOverrideChoice = 'auto' | 'yes' | 'no'

export interface UseVoucherCheckDialogOptions<T extends { id: string }> {
  modelValue: Ref<boolean>
  row: Ref<T | null>
  /** 从行读出当前 override；null/undefined = 自动 */
  getOverride?: (row: T) => boolean | null | undefined
  /** 写入 patch 的 override 字段名，默认 abnormalOverride；设为 false 则不写 override */
  overrideKey?: string | false
}

export function useVoucherCheckDialog<T extends { id: string }>(
  options: UseVoucherCheckDialogOptions<T>,
) {
  const form = ref<T | null>(null) as Ref<T | null>
  const overrideChoice = ref<VoucherOverrideChoice>('auto')
  const overrideKey = options.overrideKey === false ? false : (options.overrideKey ?? 'abnormalOverride')

  function hydrate(row: T) {
    form.value = { ...row }
    if (overrideKey === false) {
      overrideChoice.value = 'auto'
      return
    }
    const ov = options.getOverride
      ? options.getOverride(row)
      : ((row as Record<string, unknown>)[overrideKey] as boolean | null | undefined)
    overrideChoice.value = ov === null || ov === undefined ? 'auto' : (ov ? 'yes' : 'no')
  }

  watch(
    [options.modelValue, options.row],
    ([visible, row]) => {
      if (visible && row) hydrate(row)
    },
    { immediate: true },
  )

  function resolveOverride(): boolean | null {
    if (overrideChoice.value === 'auto') return null
    return overrideChoice.value === 'yes'
  }

  /** 组装保存 patch（含 id；可选 override 字段） */
  function buildSavePatch(): (Partial<T> & { id: string }) | null {
    if (!form.value) return null
    if (overrideKey === false) {
      return { ...form.value }
    }
    return {
      ...form.value,
      [overrideKey]: resolveOverride(),
    } as Partial<T> & { id: string }
  }

  return {
    form,
    /** 兼容旧名 abnormalChoice */
    overrideChoice,
    abnormalChoice: overrideChoice,
    resolveOverride,
    buildSavePatch,
  }
}

export default useVoucherCheckDialog
