import { computed, toValue, type MaybeRefOrGetter } from 'vue'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

export interface PreferredFixedColumnsOptions {
  /** 稳定页面/表身份；动态表必须把 table / mode 身份放进 key，不能跨表误用。 */
  pageKey: MaybeRefOrGetter<string>
  /** 只含叶子列的稳定 key；分组父列与右侧业务操作列不传。 */
  allowedColumns: MaybeRefOrGetter<readonly string[]>
  /** 身份列等强制左固定列，用户不可取消。 */
  mandatoryColumns?: MaybeRefOrGetter<readonly string[]>
}

function uniqueValid(values: readonly string[]): string[] {
  return [...new Set(values.filter((key) => typeof key === 'string' && key.length > 0 && key.length <= 100))]
}

/**
 * 当前账号固定列策略的唯一实现（platform-global-display-settings-closure §4.3）。
 *
 * 不变量：``effective = mandatory ∪ (saved ∩ allowed)``；未知/重复 key 不生效，
 * ``fixedFor`` 只返回 ``left`` 或 ``false``，绝不覆盖业务自身的右固定操作列。
 */
export function usePreferredFixedColumns(options: PreferredFixedColumnsOptions) {
  const prefs = useDisplayPrefsStore()
  const pageKey = computed(() => toValue(options.pageKey).trim())
  const allowedKeys = computed(() => uniqueValid(toValue(options.allowedColumns)))
  const mandatoryKeys = computed(() => {
    const allowed = new Set(allowedKeys.value)
    return uniqueValid(toValue(options.mandatoryColumns ?? [])).filter((key) => allowed.has(key))
  })
  const savedKeys = computed(() => {
    // 没有稳定页面身份的旧 wrapper 不启用固定列，也不要求其测试替身具备新 store API。
    // 这不是降级保存：真实可保存路径仍由 GtTableDisplaySettings 拒绝空 pageKey。
    if (!pageKey.value) return []
    return prefs.getFixedColumns(pageKey.value)
  })
  const staleKeys = computed(() => {
    const allowed = new Set(allowedKeys.value)
    return uniqueValid(savedKeys.value).filter((key) => !allowed.has(key))
  })
  const effectiveKeys = computed(() => {
    const mandatory = new Set(mandatoryKeys.value)
    const saved = new Set(savedKeys.value)
    return allowedKeys.value.filter((key) => mandatory.has(key) || saved.has(key))
  })

  function fixedFor(key: string): 'left' | false {
    return effectiveKeys.value.includes(key) ? 'left' : false
  }

  function save(keys: readonly string[]): boolean {
    const allowed = new Set(allowedKeys.value)
    const mandatory = new Set(mandatoryKeys.value)
    const selected = new Set(uniqueValid(keys).filter((key) => allowed.has(key)))
    for (const key of mandatory) selected.add(key)
    const normalized = allowedKeys.value.filter((key) => selected.has(key))
    return prefs.setFixedColumns(pageKey.value, normalized)
  }

  return { pageKey, allowedKeys, mandatoryKeys, savedKeys, staleKeys, effectiveKeys, fixedFor, save }
}
