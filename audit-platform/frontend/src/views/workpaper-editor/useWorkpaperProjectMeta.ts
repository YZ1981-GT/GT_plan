/**
 * 底稿编辑页的项目信息：场景 / 外币 / 计量模式 + 审计年度（从 WorkpaperEditor.vue 抽出）。
 *
 * 年度缺失时整页不渲染底稿（spec audit-year-calendar-fallback-ratchet），所以「没取到」不能当成「没填」：
 * - 请求不参与 GET 去重：同页别的组件也会取 `/api/projects/{id}`，去重会取消先发的那一个，被取消方进 catch。
 *   原写法 catch 里只给场景默认值、年度留空 ⇒ 后端一慢就整页「未设置审计年度」（2026-10-26 浏览器实测：重药安徽 J1A）。
 * - 不再 `validateStatus: s < 600`：4xx / 5xx 原先当成功解析，年度取不到同样显示成「未设置」。
 * - 取失败给 `projectMetaFailed`，页面显示「读取失败」和重试；`_silent`：错误由页面自己说，不再弹全局提示。
 */
import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import { api } from '@/services/apiProxy'
import { resolveAuditYearFromProject } from '@/utils/resolveAuditYear'

export interface WorkpaperProjectMeta {
  scenario: string
  has_foreign_currency: boolean
  measurement_model?: string
}

export function useWorkpaperProjectMeta(projectId: MaybeRefOrGetter<string>) {
  const projectMeta = ref<WorkpaperProjectMeta | null>(null)
  const projectYear = ref<number | null>(null)
  const projectMetaFailed = ref(false)
  let seq = 0 // 重试时只认最后一次请求的结果

  async function loadProjectMeta(): Promise<void> {
    const mine = ++seq
    projectMetaFailed.value = false
    try {
      const proj: any = await api.get(`/api/projects/${toValue(projectId)}`, { _dedupe: false, _silent: true } as any)
      if (mine !== seq) return
      projectMeta.value = {
        scenario: proj?.scenario || 'normal',
        has_foreign_currency: !!proj?.has_foreign_currency,
        measurement_model: proj?.measurement_model || 'cost',
      }
      projectYear.value = resolveAuditYearFromProject(proj) // 与后端同一口径：审计年度 → 审计期末 → 期初 → 项目名后缀
    } catch {
      if (mine === seq) projectMetaFailed.value = true
    }
  }

  return { projectMeta, projectYear, projectMetaFailed, loadProjectMeta }
}
