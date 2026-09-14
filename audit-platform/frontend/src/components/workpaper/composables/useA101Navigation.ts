/**
 * useA101Navigation — A10-1 与治理层沟通函 章节导航 scrollspy
 *
 * Spec: .kiro/specs/a10-1-governance-communication/
 * Task: 2.2
 *
 * 职责：
 * - IntersectionObserver scrollspy 跟踪 16+ sections 可见性
 * - activeChapter ref (0=header, 1-16=chapters, 17=sign, 18=tip)
 * - scrollToChapter smooth scroll
 */
import { ref, onMounted, onBeforeUnmount, type Ref } from 'vue'

export interface UseA101NavigationReturn {
  activeChapter: Ref<number>
  scrollToChapter: (index: number) => void
}

/**
 * Section ID naming convention:
 * - `a101-section-0` = header (recipient + intro)
 * - `a101-section-1` ~ `a101-section-16` = chapters
 * - `a101-section-17` = signing
 * - `a101-section-18` = guidance tip
 */
function getSectionId(index: number): string {
  return `a101-section-${index}`
}

export function useA101Navigation(): UseA101NavigationReturn {
  const activeChapter = ref<number>(0)

  let observer: IntersectionObserver | null = null
  const visibleSections = new Map<number, boolean>()

  function updateActive() {
    // Pick the lowest-numbered visible section
    for (let i = 0; i <= 18; i++) {
      if (visibleSections.get(i)) {
        activeChapter.value = i
        return
      }
    }
  }

  function scrollToChapter(index: number) {
    const el = document.getElementById(getSectionId(index))
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
      activeChapter.value = index
    }
  }

  onMounted(() => {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.id
          const match = id.match(/a101-section-(\d+)/)
          if (match) {
            const idx = parseInt(match[1], 10)
            visibleSections.set(idx, entry.isIntersecting)
          }
        }
        updateActive()
      },
      { rootMargin: '-80px 0px -60% 0px', threshold: 0 },
    )

    // Observe all sections
    for (let i = 0; i <= 18; i++) {
      const el = document.getElementById(getSectionId(i))
      if (el) observer.observe(el)
    }
  })

  onBeforeUnmount(() => {
    if (observer) {
      observer.disconnect()
      observer = null
    }
  })

  return {
    activeChapter,
    scrollToChapter,
  }
}
