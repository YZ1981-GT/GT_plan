import { computed, effectScope, watch, type ComputedRef, type EffectScope } from 'vue'
import { getActivePinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const DENSITY_METRICS = {
  compact: { rowHeight: '32px', paddingX: '8px', paddingY: '4px' },
  default: { rowHeight: '40px', paddingX: '12px', paddingY: '8px' },
  comfortable: { rowHeight: '48px', paddingX: '16px', paddingY: '12px' },
} as const

type FontStyle = Record<'--wp-font-size', string>

type RuntimeHandle = {
  scope: EffectScope
  fontStyle: ComputedRef<FontStyle>
}

const runtimes = new WeakMap<object, RuntimeHandle>()

function applyRootVariables(fontSize: string, density: keyof typeof DENSITY_METRICS): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  const metrics = DENSITY_METRICS[density]
  root.style.setProperty('--gt-display-font-size', fontSize)
  root.style.setProperty('--wp-font-size', fontSize)
  root.style.setProperty('--gt-table-row-height', metrics.rowHeight)
  root.style.setProperty('--gt-table-cell-padding-x', metrics.paddingX)
  root.style.setProperty('--gt-table-cell-padding-y', metrics.paddingY)
  root.dataset.gtFontSize = fontSize
  root.dataset.gtDensity = density
}

/**
 * 安装一次当前 Pinia 的账号偏好运行时。
 * 此 composable 只负责状态同步和根变量；页面布局/表格重排由后续公共层任务接线。
 */
export function useDisplayPreferencesRuntime() {
  const pinia = getActivePinia()
  if (!pinia) throw new Error('显示偏好运行时需要已激活的 Pinia')
  const existing = runtimes.get(pinia)
  if (existing) return existing

  const prefs = useDisplayPrefsStore()
  const auth = useAuthStore()
  const fontStyle = computed<FontStyle>(() => ({
    '--wp-font-size': prefs.fontConfig.tableFont,
  }))
  const scope = effectScope(true)
  scope.run(() => {
    watch(
      () => auth.userId,
      (userId) => { void prefs.loadForUser(userId || null) },
      { immediate: true },
    )
    watch(
      [() => prefs.fontConfig.tableFont, () => prefs.density],
      ([fontSize, density]) => applyRootVariables(fontSize, density),
      { immediate: true },
    )
  })

  const handle = { scope, fontStyle }
  runtimes.set(pinia, handle)
  return handle
}

export { applyRootVariables, DENSITY_METRICS }
