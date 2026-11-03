/**
 * A30 电子底稿归档检查表「按项目底稿建议」（spec attachment-archive-and-a-class-evidence 需求 8.2、8.3）。
 *
 * 后端按项目里有没有该编码的未删除底稿给出「是 / 否」；这里只填空项（走核对表现有的自动保存），
 * 已填且与建议相反的列出提示、不覆盖（填「不适用」是人工判断，不算冲突）。只读时不可用。
 */
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

export const ARCHIVE_INDEX_CHECKLIST_CODES = new Set(['A30'])

interface SuggestionsResponse {
  suggestions: Record<string, '是' | '否'>
  total: number
  present: number
}

export interface SuggestConflict {
  itemId: string
  current: string
  suggested: string
}

export interface UseArchiveChecklistSuggestOptions {
  projectId: () => string
  wpId: () => string
  wpCode: () => string
  readonly: () => boolean
  getResponse: (itemId: string) => { conclusion?: string | null }
  updateConclusion: (itemId: string, value: string) => void
  /** 冲突项显示名（编码 + 名称） */
  itemLabel?: (itemId: string) => string
}

export function suggestionsPath(projectId: string, wpId: string): string {
  return `/api/projects/${projectId}/workpapers/${wpId}/archive-checklist/suggestions`
}

/** 纯函数：哪些空项要填、哪些已填项与建议相反（便于单测） */
export function planSuggestions(
  suggestions: Record<string, string>,
  current: (itemId: string) => string,
): { fill: Array<[string, string]>; conflicts: SuggestConflict[] } {
  const fill: Array<[string, string]> = []
  const conflicts: SuggestConflict[] = []
  for (const [itemId, suggested] of Object.entries(suggestions)) {
    const now = (current(itemId) || '').trim()
    if (!now) fill.push([itemId, suggested])
    else if ((now === '是' || now === '否') && now !== suggested) conflicts.push({ itemId, current: now, suggested })
  }
  return { fill, conflicts }
}

export function useArchiveChecklistSuggest(opts: UseArchiveChecklistSuggestOptions) {
  const available = computed(
    () => ARCHIVE_INDEX_CHECKLIST_CODES.has(opts.wpCode()) && !opts.readonly() && !!opts.projectId() && !!opts.wpId(),
  )
  const applying = ref(false)

  async function applySuggestions(): Promise<{ filled: number; conflicts: SuggestConflict[] } | null> {
    if (!available.value || applying.value) return null
    applying.value = true
    try {
      const data = await api.get<SuggestionsResponse>(suggestionsPath(opts.projectId(), opts.wpId()))
      const { fill, conflicts } = planSuggestions(
        data?.suggestions || {}, (id) => String(opts.getResponse(id).conclusion ?? ''),
      )
      for (const [itemId, value] of fill) opts.updateConclusion(itemId, value)
      if (conflicts.length) {
        const label = opts.itemLabel || ((id: string) => id)
        const lines = conflicts.slice(0, 15).map(
          (c) => `${label(c.itemId)}：已填「${c.current}」，项目底稿显示「${c.suggested}」`,
        )
        const more = conflicts.length > 15 ? `\n……共 ${conflicts.length} 项` : ''
        ElMessageBox.alert(`${lines.join('\n')}${more}`, `已填 ${fill.length} 项；${conflicts.length} 项与建议不一致，未改动`, {
          confirmButtonText: '知道了',
          customStyle: { whiteSpace: 'pre-line' },
        }).catch(() => undefined)
      } else {
        ElMessage.success(fill.length ? `已按项目底稿填入 ${fill.length} 项` : '没有需要填写的空项')
      }
      return { filled: fill.length, conflicts }
    } catch (err: any) {
      handleApiError(err, '获取归档检查建议')
      return null
    } finally {
      applying.value = false
    }
  }

  return { available, applying, applySuggestions }
}
