/**
 * useChecklistSearch — 核对表搜索/高亮/跳转（spec workpaper-frontend-large-component-split, Req 2）
 *
 * 从 GtChecklistTable.vue 抽出：
 * - searchQuery / searchActive state
 * - searchResults computed（actionable 条目按 content/standard_ref/child 匹配）
 * - highlightText / jumpToSearchResult / clearSearch
 *
 * 铁律：行为零变更、保响应式（ref/computed）；依赖单向；composable 之间不互相 import
 *       （sections 由主组件以 getter 传入；跳转需联动的 activeSection/expandedItems 由主组件持有传入）。
 */
import { ref, computed, type Ref } from 'vue'
import type { ChecklistSection, SearchMatch } from '@/components/workpaper/checklistTypes'

export function useChecklistSearch(options: {
  /** 章节列表取值（getter，保持响应式） */
  sections: () => ChecklistSection[]
  /** 当前激活章节（主组件持有，跳转时写回） */
  activeSection: Ref<string>
  /** 展开条目集合（主组件持有，子项匹配时展开） */
  expandedItems: Ref<Set<string>>
}) {
  const { activeSection, expandedItems } = options

  // ─── State ───
  const searchQuery = ref('')
  const searchActive = ref(false)

  // ─── Computed: Search results ───
  const searchResults = computed<SearchMatch[]>(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return []
    const results: SearchMatch[] = []
    for (const section of options.sections()) {
      for (const item of section.items) {
        if (item.type !== 'actionable') continue
        if (item.content.toLowerCase().includes(q) || item.standard_ref.toLowerCase().includes(q)) {
          results.push({ sectionId: section.id, sectionTitle: section.title, item, matchField: item.standard_ref.toLowerCase().includes(q) ? 'standard_ref' : 'content' })
        } else if (item.children?.some(c => c.content.toLowerCase().includes(q) || c.standard_ref.toLowerCase().includes(q))) {
          results.push({ sectionId: section.id, sectionTitle: section.title, item, matchField: 'child' })
        }
      }
    }
    return results
  })

  // ─── Methods ───
  function highlightText(text: string, query: string): string {
    if (!query) return text
    const q = query.trim()
    if (!q) return text
    const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const re = new RegExp(`(${escaped})`, 'gi')
    return text.replace(re, '<mark class="search-highlight">$1</mark>')
  }

  function jumpToSearchResult(result: SearchMatch) {
    activeSection.value = result.sectionId
    searchActive.value = false
    // Expand the item's children if match was in child
    if (result.matchField === 'child') {
      expandedItems.value.add(result.item.id)
    }
  }

  function clearSearch() {
    searchQuery.value = ''
    searchActive.value = false
  }

  return {
    // state
    searchQuery,
    searchActive,
    // computed
    searchResults,
    // methods
    highlightText,
    jumpToSearchResult,
    clearSearch,
  }
}
