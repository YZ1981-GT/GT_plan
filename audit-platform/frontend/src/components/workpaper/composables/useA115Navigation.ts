/**
 * useA115Navigation — A1-15 章节导航 + section-based lazy rendering
 *
 * Spec: .kiro/specs/a1-15-disclosure-checklist/
 * Task: 3.2
 *
 * 职责：
 * - activeSectionId: IntersectionObserver 驱动高亮（当前可视区最靠上的章节）
 * - visibleSections: Set<string>（当前 ±1 章节渲染，其余占位 div）
 * - scrollToSection(sectionId): 先设 visible 再 scrollIntoView(smooth)
 * - initObserver(): 绑定各章节 sentinel（[data-section-id]）
 * - destroyObserver(): 清理 IntersectionObserver
 * - isSectionVisible(sectionId): 查询可见性
 *
 * 性能策略：
 * - 500+ 条目不能一次性全部渲染 DOM
 * - 仅渲染当前可视章节 ± 1 个缓冲章节（IntersectionObserver 触发）
 * - 非可视章节渲染为占位 div（高度预估 = items.length × 80px）
 * - 搜索/筛选时由 caller 控制 visibleSections（全部展开）
 */
import { ref, nextTick, type Ref } from 'vue'
import type { A115Section } from './useA115Checklist'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA115Navigation(
  sections: Ref<A115Section[]>,
  containerRef: Ref<HTMLElement | null>,
) {
  const activeSectionId = ref<string | null>(null)
  const visibleSections = ref<Set<string>>(new Set())

  let observer: IntersectionObserver | null = null

  // ─── initObserver ────────────────────────────────────────────────────────

  /**
   * 初始化 IntersectionObserver，监视各章节的 sentinel 元素（[data-section-id]）。
   * 当 sentinel 进入 viewport → 将该章节及 ±1 邻居加入 visibleSections。
   * activeSectionId 更新为当前可视区最靠上的章节。
   */
  function initObserver(): void {
    destroyObserver()

    const root = containerRef.value
    if (!root) {
      // Fallback: 如果 DOM 容器不可用，默认显示前 3 个章节
      const sectionsList = sections.value
      for (let i = 0; i < Math.min(3, sectionsList.length); i++) {
        visibleSections.value.add(sectionsList[i].id)
      }
      if (sectionsList.length > 0) {
        activeSectionId.value = sectionsList[0].id
      }
      return
    }

    // 初始化：默认显示前 3 个章节
    if (sections.value.length > 0 && visibleSections.value.size === 0) {
      const sectionsList = sections.value
      for (let i = 0; i < Math.min(3, sectionsList.length); i++) {
        visibleSections.value.add(sectionsList[i].id)
      }
      activeSectionId.value = sectionsList[0].id
    }

    observer = new IntersectionObserver(
      (entries) => {
        // 收集所有 intersecting 的 section id
        const intersectingIds: string[] = []

        for (const entry of entries) {
          const sectionId = (entry.target as HTMLElement).dataset.sectionId
          if (!sectionId) continue

          if (entry.isIntersecting) {
            addWithNeighbors(sectionId)
            intersectingIds.push(sectionId)
          }
        }

        // 更新 activeSectionId：选择所有 intersecting 中在 sections 中顺序最靠前的
        if (intersectingIds.length > 0) {
          updateActiveSection(intersectingIds)
        }
      },
      {
        root,
        // 提前触发：上下各 200px buffer 让切换更平滑
        rootMargin: '200px 0px 200px 0px',
        threshold: 0,
      },
    )

    // 观察所有 sentinel 元素
    const sentinels = root.querySelectorAll<HTMLElement>('[data-section-id]')
    sentinels.forEach((el) => observer!.observe(el))
  }

  // ─── scrollToSection ─────────────────────────────────────────────────────

  /**
   * 导航到指定章节：
   * 1. 先将目标章节 + 邻居加入 visibleSections（确保 DOM 已渲染）
   * 2. nextTick 后 scrollIntoView(smooth)
   */
  function scrollToSection(sectionId: string): void {
    // 1. 确保目标章节及邻居可见（触发 DOM 渲染）
    addWithNeighbors(sectionId)
    activeSectionId.value = sectionId

    // 2. 等 DOM 更新后滚动
    nextTick(() => {
      const root = containerRef.value
      if (!root) return

      const sentinel = root.querySelector<HTMLElement>(`[data-section-id="${sectionId}"]`)
      if (sentinel) {
        sentinel.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    })
  }

  // ─── isSectionVisible ────────────────────────────────────────────────────

  function isSectionVisible(sectionId: string): boolean {
    return visibleSections.value.has(sectionId)
  }

  // ─── destroyObserver ─────────────────────────────────────────────────────

  function destroyObserver(): void {
    if (observer) {
      observer.disconnect()
      observer = null
    }
  }

  // ─── Internal helpers ────────────────────────────────────────────────────

  /**
   * 将 sectionId 及其 ±1 邻居加入 visibleSections
   */
  function addWithNeighbors(sectionId: string): void {
    const sectionsList = sections.value
    const idx = sectionsList.findIndex((s) => s.id === sectionId)
    if (idx === -1) return

    visibleSections.value.add(sectionId)

    // 前一个邻居
    if (idx > 0) {
      visibleSections.value.add(sectionsList[idx - 1].id)
    }
    // 后一个邻居
    if (idx < sectionsList.length - 1) {
      visibleSections.value.add(sectionsList[idx + 1].id)
    }
  }

  /**
   * 从 intersecting section ids 中选择 sections 列表中最靠前的作为 active
   */
  function updateActiveSection(intersectingIds: string[]): void {
    const sectionsList = sections.value
    let minIdx = Infinity
    let activeId: string | null = null

    for (const id of intersectingIds) {
      const idx = sectionsList.findIndex((s) => s.id === id)
      if (idx !== -1 && idx < minIdx) {
        minIdx = idx
        activeId = id
      }
    }

    if (activeId !== null) {
      activeSectionId.value = activeId
    }
  }

  return {
    activeSectionId,
    visibleSections,
    initObserver,
    scrollToSection,
    isSectionVisible,
    destroyObserver,
  }
}

export default useA115Navigation
