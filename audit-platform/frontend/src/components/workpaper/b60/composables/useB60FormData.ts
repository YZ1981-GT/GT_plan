/**
 * useB60FormData — B60 章节内容持久化 composable
 *
 * 职责：
 * - chapterContents Map<string, string> 管理各章节内容
 * - 800ms 防抖调用 PUT /api/workpapers/{wpId}/checklist-responses
 * - payload: { items: [{ item_id: chapter_id, conclusion: null, remark: 章节内容文本 }] }
 * - 成功后调用 scheduleAutoSnapshot()
 * - 连续失败 3 次停止重试 + ElMessage.warning("保存失败，请检查网络后重试")
 * - onMounted 从 responsesSnapshot 初始化各章节内容
 *
 * Spec: .kiro/specs/b60-dedicated-component/
 * Requirements: 6.1, 6.2, 6.3, 6.4, 11.2
 */
import { ref, watch, onMounted, onScopeDispose, type Ref } from 'vue'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useWorkpaperVersionToolbar } from '@/components/workpaper/composables/useWorkpaperVersionToolbar'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface ChapterDefinition {
  chapter_id: string
  title: string
  level: 1 | 2 | 3
  required: boolean
  hint: string
  data_source: { label: string; wp_code: string } | null
}

export interface UseB60FormDataOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  chapterDefinitions: Ref<ChapterDefinition[]>
  responsesSnapshot: Ref<Record<string, { conclusion: string | null; remark: string | null }>>
}

export interface UseB60FormDataReturn {
  chapterContents: Ref<Map<string, string>>
  saveStatus: Ref<'saved' | 'saving' | 'unsaved'>
  updateChapter: (chapterId: string, content: string) => void
  flushPendingSaves: () => Promise<void>
  consecutiveFailures: Ref<number>
}

// ─── Composable ───────────────────────────────────────────────────────────────

export function useB60FormData(options: UseB60FormDataOptions): UseB60FormDataReturn {
  const { wpId, projectId, chapterDefinitions, responsesSnapshot } = options

  // ── State ───────────────────────────────────────────────────────────────────
  const chapterContents = ref<Map<string, string>>(new Map())
  const saveStatus = ref<'saved' | 'saving' | 'unsaved'>('saved')
  const consecutiveFailures = ref(0)

  // ── Version toolbar for scheduleAutoSnapshot ────────────────────────────────
  const { scheduleAutoSnapshot } = useWorkpaperVersionToolbar({ wpId, projectId })

  // ── Internal debounce state ─────────────────────────────────────────────────
  let _debounceTimer: ReturnType<typeof setTimeout> | null = null
  const _pendingChapterIds = new Set<string>()
  const MAX_CONSECUTIVE_FAILURES = 3

  // ── Initialize from responsesSnapshot ───────────────────────────────────────

  function _populateFromSnapshot(): void {
    const snapshot = responsesSnapshot.value
    if (!snapshot || typeof snapshot !== 'object') return

    const definitions = chapterDefinitions.value
    if (!definitions || definitions.length === 0) return

    // Build a set of valid chapter_ids for matching
    const validChapterIds = new Set(definitions.map((d) => d.chapter_id))

    for (const [itemId, entry] of Object.entries(snapshot)) {
      // Only match B60-CH-* items that correspond to chapter definitions
      if (validChapterIds.has(itemId) && entry?.remark) {
        chapterContents.value.set(itemId, entry.remark)
      }
    }
  }

  // ── Save logic ──────────────────────────────────────────────────────────────

  async function _doSave(): Promise<void> {
    if (!wpId.value || _pendingChapterIds.size === 0) return
    if (consecutiveFailures.value >= MAX_CONSECUTIVE_FAILURES) return

    // Snapshot the pending items to save
    const chapterIdsToSave = [..._pendingChapterIds]
    _pendingChapterIds.clear()

    saveStatus.value = 'saving'

    const items = chapterIdsToSave.map((chapterId) => ({
      item_id: chapterId,
      conclusion: null,
      remark: chapterContents.value.get(chapterId) ?? '',
    }))

    try {
      await http.put(`/api/workpapers/${wpId.value}/checklist-responses`, { items })
      consecutiveFailures.value = 0
      saveStatus.value = 'saved'
      // 成功后触发自动版本快照
      scheduleAutoSnapshot()
    } catch (err: any) {
      consecutiveFailures.value++
      saveStatus.value = 'unsaved'

      if (consecutiveFailures.value >= MAX_CONSECUTIVE_FAILURES) {
        ElMessage.warning('保存失败，请检查网络后重试')
      } else {
        // Re-add pending items for next attempt
        for (const id of chapterIdsToSave) {
          _pendingChapterIds.add(id)
        }
      }
    }
  }

  function _scheduleSave(): void {
    if (_debounceTimer) clearTimeout(_debounceTimer)
    _debounceTimer = setTimeout(() => {
      _debounceTimer = null
      void _doSave()
    }, 800)
  }

  // ── Public methods ──────────────────────────────────────────────────────────

  /**
   * 更新章节内容并触发 800ms 防抖保存
   */
  function updateChapter(chapterId: string, content: string): void {
    chapterContents.value.set(chapterId, content)
    _pendingChapterIds.add(chapterId)
    saveStatus.value = 'unsaved'
    _scheduleSave()
  }

  /**
   * 立即保存所有待保存内容（供模式切换/组件卸载时调用）
   */
  async function flushPendingSaves(): Promise<void> {
    if (_debounceTimer) {
      clearTimeout(_debounceTimer)
      _debounceTimer = null
    }
    if (_pendingChapterIds.size > 0) {
      await _doSave()
    }
  }

  // ── Lifecycle ───────────────────────────────────────────────────────────────

  onMounted(() => {
    _populateFromSnapshot()
  })

  // Watch for responsesSnapshot changes (e.g., reload after mode switch)
  watch(responsesSnapshot, () => {
    _populateFromSnapshot()
  }, { deep: true })

  onScopeDispose(() => {
    if (_debounceTimer) {
      clearTimeout(_debounceTimer)
      _debounceTimer = null
    }
    // Best-effort flush on dispose (fire-and-forget)
    if (_pendingChapterIds.size > 0) {
      void _doSave()
    }
  })

  return {
    chapterContents,
    saveStatus,
    updateChapter,
    flushPendingSaves,
    consecutiveFailures,
  }
}
