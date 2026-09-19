/**
 * Sticky section navigation with IntersectionObserver highlight.
 */
import { onMounted, onUnmounted, ref, type Ref } from 'vue'

export interface StickyNavItem {
  id: string
  label: string
}

export function useStickySectionNav(
  items: StickyNavItem[] | Ref<StickyNavItem[]>,
  opts?: { rootMargin?: string },
) {
  const list = (): StickyNavItem[] => (Array.isArray(items) ? items : items.value)
  const activeId = ref(list()[0]?.id ?? '')

  function scrollTo(id: string): void {
    activeId.value = id
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  let observer: IntersectionObserver | null = null

  onMounted(() => {
    const navItems = list()
    if (!navItems.length) return
    activeId.value = navItems[0].id
    observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        const id = (visible?.target as HTMLElement | undefined)?.id
        if (id) activeId.value = id
      },
      {
        rootMargin: opts?.rootMargin ?? '-20% 0px -55% 0px',
        threshold: [0.1, 0.35, 0.6],
      },
    )
    for (const item of navItems) {
      const el = document.getElementById(item.id)
      if (el) observer.observe(el)
    }
  })

  onUnmounted(() => {
    observer?.disconnect()
    observer = null
  })

  return { activeId, scrollTo }
}
