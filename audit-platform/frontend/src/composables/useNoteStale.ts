/**
 * useNoteStale — 附注章节级 stale 状态追踪（R2.1 前端联动）
 *
 * Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 3 Task 3.6
 * Design: D6 联动事件总线
 * Reqs:   R2.1 验收：章节列表红点 + tooltip + dismiss
 *
 * 职责：
 * - 维护当前项目下"上游已变更，建议重算"的章节集合（按 note_section 字面）
 * - 订阅 eventBus 'sse:sync-event'，从后端 3 个新事件中提取 note_section 加入集合：
 *   - LEDGER_DATASET_ACTIVATED → 全部章节标 stale
 *   - WORKPAPER_REVIEW_PASSED  → 全部章节标 stale
 *   - ADJUSTMENT_BATCH_COMMITTED → 全部章节标 stale
 *   payload.extra.affected_note_sections 若存在则只标对应章节，否则全标。
 * - 提供 markStale / dismissStale / dismissAll 三个本地操作。
 * - dismissStale 仅本地状态：后端 `POST /disclosure-notes/{id}/dismiss-stale`
 *   端点尚未实现，留 TODO + console.info 提示后续 Sprint 接入。
 *
 * 使用：
 * ```ts
 * const noteStale = useNoteStale(projectId)
 * // 模板里：v-if="noteStale.staleSections.value.has(note_section)"
 * await noteStale.markStale('五、6')
 * await noteStale.dismissStale('五、6')   // 本地清掉红点
 * ```
 *
 * Note: pattern mirrors useStaleStatus.ts.
 */
import { ref, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'

/**
 * 与后端 3 个新事件对齐（snake_case + 大写常量都接受，留 robust 兼容）：
 * - LEDGER_DATASET_ACTIVATED   ← `ledger.dataset_activated`（现有 SSE）
 * - WORKPAPER_REVIEW_PASSED    ← `workpaper.review_passed`
 * - ADJUSTMENT_BATCH_COMMITTED ← `adjustment.batch_committed`
 */
const NOTE_STALE_EVENT_TYPES: ReadonlyArray<string> = Object.freeze([
  'ledger.dataset_activated',
  'workpaper.review_passed',
  'adjustment.batch_committed',
  // 旧式大写写法（兼容直接 emit EventType.* 的本地测试）
  'LEDGER_DATASET_ACTIVATED',
  'WORKPAPER_REVIEW_PASSED',
  'ADJUSTMENT_BATCH_COMMITTED',
])

/** 占位标记：表示"全部章节都视为 stale"。当后端没显式给章节列表时使用。 */
export const NOTE_STALE_ALL = '__ALL__'

export interface UseNoteStaleApi {
  /** 当前 stale 章节号集合（含 NOTE_STALE_ALL 时表示"全部 stale"） */
  staleSections: Ref<Set<string>>
  /** 是否任意章节 stale（含全标） */
  hasAny: Ref<boolean>
  /** 给某章节贴 stale 标记 */
  markStale: (sectionNumber: string) => void
  /** 移除某章节的 stale 标记（仅本地，不调后端） */
  dismissStale: (sectionNumber: string) => void
  /** 移除全部 stale 标记 */
  dismissAll: () => void
  /** 判定指定章节是否处于 stale（兼容"全部 stale"语义） */
  isStale: (sectionNumber: string | undefined | null) => boolean
}

export function useNoteStale(projectId: Ref<string>): UseNoteStaleApi {
  const staleSections = ref<Set<string>>(new Set())
  const hasAny = ref(false)

  function _refreshHasAny() {
    hasAny.value = staleSections.value.size > 0
  }

  function markStale(sectionNumber: string) {
    if (!sectionNumber) return
    if (!staleSections.value.has(sectionNumber)) {
      staleSections.value = new Set([...staleSections.value, sectionNumber])
      _refreshHasAny()
    }
  }

  function dismissStale(sectionNumber: string) {
    if (!sectionNumber) return
    if (!staleSections.value.has(sectionNumber)) return
    const next = new Set(staleSections.value)
    next.delete(sectionNumber)
    staleSections.value = next
    _refreshHasAny()
    // TODO(Sprint 4+): 后端端点 POST /api/disclosure-notes/{id}/dismiss-stale 尚未实现。
    // 该端点落地后此处需根据 noteId 调用 api.post 持久化"已忽略"语义。
    // 现阶段仅维护前端会话级状态。
    // eslint-disable-next-line no-console
    console.info(
      '[useNoteStale] dismissStale local-only (backend endpoint pending):',
      sectionNumber,
    )
  }

  function dismissAll() {
    if (staleSections.value.size === 0) return
    staleSections.value = new Set()
    _refreshHasAny()
    // eslint-disable-next-line no-console
    console.info('[useNoteStale] dismissAll local-only (backend endpoint pending)')
  }

  function isStale(sectionNumber: string | undefined | null): boolean {
    if (!sectionNumber) return false
    if (staleSections.value.has(NOTE_STALE_ALL)) return true
    return staleSections.value.has(sectionNumber)
  }

  /**
   * 从 SSE payload 取章节列表：
   * - payload.extra.affected_note_sections (string[]) → 精确章节集
   * - payload.note_section (string)                   → 单章节
   * - 其他                                              → ['__ALL__']
   */
  function _extractSections(payload: SyncEventPayload): string[] {
    const affected = (payload?.extra as any)?.affected_note_sections
    if (Array.isArray(affected) && affected.length) {
      return affected.filter(s => typeof s === 'string' && s.length > 0)
    }
    const single = (payload as any)?.note_section
    if (typeof single === 'string' && single.length) {
      return [single]
    }
    return [NOTE_STALE_ALL]
  }

  function _onSSEEvent(payload: SyncEventPayload) {
    if (!payload || !payload.event_type) return
    // 仅处理与当前项目相关的事件（payload.project_id 缺失视为全局，仍处理）
    if (payload.project_id && projectId.value && payload.project_id !== projectId.value) {
      return
    }
    if (!NOTE_STALE_EVENT_TYPES.includes(String(payload.event_type))) return

    const sections = _extractSections(payload)
    let mutated = false
    const next = new Set(staleSections.value)
    for (const sec of sections) {
      if (!next.has(sec)) {
        next.add(sec)
        mutated = true
      }
    }
    if (mutated) {
      staleSections.value = next
      _refreshHasAny()
    }
  }

  onMounted(() => {
    eventBus.on('sse:sync-event', _onSSEEvent)
  })

  onUnmounted(() => {
    eventBus.off('sse:sync-event', _onSSEEvent)
  })

  // projectId 切换 → 清空当前项目的 stale 状态（避免跨项目串台）
  watch(projectId, () => {
    if (staleSections.value.size === 0) return
    staleSections.value = new Set()
    _refreshHasAny()
  })

  return {
    staleSections,
    hasAny,
    markStale,
    dismissStale,
    dismissAll,
    isStale,
  }
}

export default useNoteStale
