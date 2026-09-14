/**
 * useB50OoSheetMap — B50 双模式 per-tab 源子底稿解析
 *
 * B50 的 5 个 Tab 对应 5 个独立源 xlsx（程序表=B50、风险因素=B50-1、报表层次=B50-2、
 * 认定层次=B50-3、特别风险=B50-4）。OnlyOffice 视图须按当前 Tab 打开对应源子底稿的
 * 源 xlsx tab（sheet-name 与源模板 tab 名完全一致）。
 *
 * 源 sheet 映射为固定常量（前端自持），wp_id 经 /api/custom-query/wp-id-by-code 解析并缓存。
 * 未实例化的子底稿 → ooSourceWpId=null（前端显示降级提示，不崩）。
 *
 * Spec: .kiro/specs/b50-workpaper-rework/ Task 6
 */
import { ref, computed, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export interface OoSheetEntry {
  source_wp_code: string
  oo_sheet_name: string
}

/** tab key → 源子底稿 wp_code + 源 xlsx tab 名（与源模板完全一致）。 */
export const B50_OO_SHEET_MAP: Record<string, OoSheetEntry> = {
  program: { source_wp_code: 'B50', oo_sheet_name: 'B50 汇总风险评估结果' },
  tab1: { source_wp_code: 'B50-1', oo_sheet_name: 'B50-1 汇总识别出的风险因素' },
  tab2: { source_wp_code: 'B50-2', oo_sheet_name: 'B50-2 财务报表层次风险' },
  tab3: { source_wp_code: 'B50-3', oo_sheet_name: 'B50-3认定层次风险评估' },
  tab4: { source_wp_code: 'B50-4', oo_sheet_name: 'B50-4 特别风险' },
}

export function useB50OoSheetMap(options: {
  projectId: Ref<string>
  activeTab: Ref<string>
  /** B50 主底稿自身 wp_id（program tab 直接用，无需解析） */
  selfWpId: Ref<string>
}) {
  const { projectId, activeTab, selfWpId } = options

  // wp_code → wp_id 解析缓存（null=已解析但未实例化）
  const wpIdCache = ref<Map<string, string | null>>(new Map())
  const resolving = ref(false)

  async function resolveSourceWpId(wpCode: string): Promise<string | null> {
    if (wpIdCache.value.has(wpCode)) return wpIdCache.value.get(wpCode) ?? null
    resolving.value = true
    try {
      const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
        params: { project_id: projectId.value, wp_code: wpCode },
        _silent: true,
      } as any)
      const wpId = (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id ?? null
      wpIdCache.value.set(wpCode, wpId)
      return wpId
    } catch {
      wpIdCache.value.set(wpCode, null)
      return null
    } finally {
      resolving.value = false
    }
  }

  const ooEntry = computed<OoSheetEntry | null>(() => B50_OO_SHEET_MAP[activeTab.value] ?? null)
  const ooSheetName = computed<string>(() => ooEntry.value?.oo_sheet_name ?? '')

  // 当前 Tab 对应源子底稿 wp_id（program 用 self，其余解析；未实例化→null）
  const ooSourceWpId = ref<string | null>(null)

  async function refreshSourceWpId(): Promise<void> {
    const entry = ooEntry.value
    if (!entry) { ooSourceWpId.value = null; return }
    if (entry.source_wp_code === 'B50') {
      ooSourceWpId.value = selfWpId.value || null
      return
    }
    ooSourceWpId.value = await resolveSourceWpId(entry.source_wp_code)
  }

  return {
    ooSheetName,
    ooSourceWpId,
    resolving,
    refreshSourceWpId,
    resolveSourceWpId,
  }
}

export default useB50OoSheetMap
