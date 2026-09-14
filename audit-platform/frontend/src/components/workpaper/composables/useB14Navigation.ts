/**
 * useB14Navigation — B1-4 尽职调查报告 章节导航 scrollspy + 完成状态 + 进度
 *
 * Spec: .kiro/specs/b1-4-due-diligence-report/
 * Task: 3.2
 *
 * 职责：
 * - IntersectionObserver scrollspy 跟踪 13 章可见性
 * - activeChapter ref (ch1~ch13) updated by observer
 * - scrollToChapter smooth scroll
 * - completionStatus computed (per chapter fill state)
 * - overallProgress percentage (filled visible chapters / total visible chapters × 100)
 */
import { ref, computed, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { B14ChapterData } from './useB14DueDiligence'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseB14NavOptions {
  chapters: Ref<Record<string, B14ChapterData>>
  variant: Ref<'standard' | 'simplified'>
}

export interface UseB14NavReturn {
  activeChapter: Ref<string>
  scrollToChapter: (chapterId: string) => void
  completionStatus: ComputedRef<Record<string, boolean>>
  overallProgress: ComputedRef<number> // 0~100
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** All chapter ids in order */
const ALL_CHAPTER_IDS = Array.from({ length: 13 }, (_, i) => `ch${i + 1}`)

/**
 * Get DOM element id for a chapter card.
 * Convention: `b14-chapter-{chapterId}` (e.g., `b14-chapter-ch1`)
 */
function getChapterElementId(chapterId: string): string {
  return `b14-chapter-${chapterId}`
}

/**
 * Determine if a chapter is "complete" based on its data:
 * - textarea type: has non-empty, non-null content
 * - table type: has ≥1 row in rows array
 * - mixed type: has ≥1 non-empty section (any section with content or ≥1 row)
 */
export function isChapterComplete(chapter: B14ChapterData): boolean {
  switch (chapter.type) {
    case 'textarea':
      return !!chapter.content && chapter.content.trim().length > 0
    case 'table':
      return Array.isArray(chapter.rows) && chapter.rows.length > 0
    case 'mixed':
      if (!Array.isArray(chapter.sections) || chapter.sections.length === 0) return false
      return chapter.sections.some((section) => {
        if (section.type === 'textarea') {
          return !!section.content && section.content.trim().length > 0
        }
        if (section.type === 'table') {
          return Array.isArray(section.rows) && section.rows.length > 0
        }
        return false
      })
    default:
      return false
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB14Navigation(options: UseB14NavOptions): UseB14NavReturn {
  const { chapters, variant } = options

  const activeChapter = ref<string>('ch1')

  let observer: IntersectionObserver | null = null
  const visibleInViewport = new Map<string, boolean>()

  function updateActive() {
    // Pick the first (lowest-numbered) chapter currently visible in viewport
    for (const chId of ALL_CHAPTER_IDS) {
      if (visibleInViewport.get(chId)) {
        activeChapter.value = chId
        return
      }
    }
  }

  function scrollToChapter(chapterId: string) {
    const el = document.getElementById(getChapterElementId(chapterId))
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      activeChapter.value = chapterId
    }
  }

  onMounted(() => {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.id
          const match = id.match(/b14-chapter-(ch\d+)/)
          if (match) {
            visibleInViewport.set(match[1], entry.isIntersecting)
          }
        }
        updateActive()
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0 },
    )

    // Observe all chapter card elements
    for (const chId of ALL_CHAPTER_IDS) {
      const el = document.getElementById(getChapterElementId(chId))
      if (el) observer.observe(el)
    }
  })

  onBeforeUnmount(() => {
    if (observer) {
      observer.disconnect()
      observer = null
    }
  })

  // ─── Completion Status ───
  const completionStatus = computed<Record<string, boolean>>(() => {
    const status: Record<string, boolean> = {}
    for (const chId of ALL_CHAPTER_IDS) {
      const ch = chapters.value[chId]
      if (!ch) {
        status[chId] = false
        continue
      }
      status[chId] = isChapterComplete(ch)
    }
    return status
  })

  // ─── Overall Progress ───
  // (count of completed VISIBLE chapters / total VISIBLE chapters × 100), rounded
  const overallProgress = computed<number>(() => {
    let visibleCount = 0
    let completedCount = 0

    for (const chId of ALL_CHAPTER_IDS) {
      const ch = chapters.value[chId]
      if (!ch || !ch.visible) continue
      visibleCount++
      if (completionStatus.value[chId]) {
        completedCount++
      }
    }

    if (visibleCount === 0) return 0
    return Math.round((completedCount / visibleCount) * 100)
  })

  return {
    activeChapter,
    scrollToChapter,
    completionStatus,
    overallProgress,
  }
}
