/**
 * useA171Navigation — A17-1 重大事项概要汇总 章节导航 scrollspy + 完成状态
 *
 * Spec: .kiro/specs/a17-1-audit-summary/
 * Task: 2.2
 *
 * 职责：
 * - IntersectionObserver scrollspy 跟踪 16 章可见性
 * - activeChapter ref (1-16) updated by observer
 * - scrollToChapter smooth scroll
 * - completionStatus computed (per chapter completion based on content)
 * - chapterRefs for observer targets
 */
import { ref, computed, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChapterData, TextareaChapter, TableChapter, YnChapter } from './useA171AuditSummary'

export interface UseA171NavReturn {
  activeChapter: Ref<number>
  chapterRefs: Ref<HTMLElement[]>
  scrollToChapter: (num: number) => void
  completionStatus: ComputedRef<Record<number, boolean>>
}

/**
 * Section ID naming convention:
 * - `a171-chapter-1` ~ `a171-chapter-16` = chapter cards
 */
function getChapterSectionId(num: number): string {
  return `a171-chapter-${num}`
}

export function useA171Navigation(
  chapters: Ref<Record<string, ChapterData>>,
): UseA171NavReturn {
  const activeChapter = ref<number>(1)
  const chapterRefs = ref<HTMLElement[]>([])

  let observer: IntersectionObserver | null = null
  const visibleChapters = new Map<number, boolean>()

  function updateActive() {
    // Pick the lowest-numbered visible chapter
    for (let i = 1; i <= 16; i++) {
      if (visibleChapters.get(i)) {
        activeChapter.value = i
        return
      }
    }
  }

  function scrollToChapter(num: number) {
    const el = document.getElementById(getChapterSectionId(num))
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      activeChapter.value = num
    }
  }

  onMounted(() => {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.id
          const match = id.match(/a171-chapter-(\d+)/)
          if (match) {
            const num = parseInt(match[1], 10)
            visibleChapters.set(num, entry.isIntersecting)
          }
        }
        updateActive()
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0 },
    )

    // Observe all chapter sections
    for (let i = 1; i <= 16; i++) {
      const el = document.getElementById(getChapterSectionId(i))
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
  const completionStatus = computed<Record<number, boolean>>(() => {
    const status: Record<number, boolean> = {}
    for (let i = 1; i <= 16; i++) {
      const ch = chapters.value[String(i)]
      if (!ch) {
        status[i] = false
        continue
      }
      switch (ch.type) {
        case 'textarea':
          status[i] = !!(ch as TextareaChapter).content
          break
        case 'table':
          status[i] = (ch as TableChapter).rows.length > 0
          break
        case 'yn':
          status[i] = (ch as YnChapter).answer !== null
          break
        default:
          status[i] = false
      }
    }
    return status
  })

  return {
    activeChapter,
    chapterRefs,
    scrollToChapter,
    completionStatus,
  }
}
