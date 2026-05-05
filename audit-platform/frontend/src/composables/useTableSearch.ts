/**
 * 表格内搜索替换 composable
 *
 * 类似 WPS/Excel 的 Ctrl+F / Ctrl+H 功能。
 * 搜索表格数据中的匹配项，高亮显示，支持上下跳转和替换。
 *
 * 用法：
 * ```ts
 * const search = useTableSearch(tableData, ['account_name', 'description'])
 *
 * // 模板中
 * <el-input v-model="search.keyword.value" @keyup.enter="search.nextMatch" />
 * <span>{{ search.matchInfo }}</span>
 *
 * // 单元格 class 绑定
 * :class="search.cellMatchClass(rowIndex, colIndex)"
 * ```
 */
import { ref, computed, watch, type Ref } from 'vue'

export interface SearchMatch {
  row: number
  col: number
  field: string
  value: string
}

export function useTableSearch(
  data: Ref<any[]>,
  searchableColumns: string[],
) {
  const keyword = ref('')
  const replaceText = ref('')
  const matches = ref<SearchMatch[]>([])
  const currentIndex = ref(-1)
  const isVisible = ref(false)
  const caseSensitive = ref(false)

  // 当前匹配项
  const currentMatch = computed(() => {
    if (currentIndex.value < 0 || currentIndex.value >= matches.value.length) return null
    return matches.value[currentIndex.value]
  })

  // 匹配信息文本
  const matchInfo = computed(() => {
    if (!keyword.value) return ''
    if (!matches.value.length) return '无匹配'
    return `${currentIndex.value + 1} / ${matches.value.length}`
  })

  // 搜索
  function search() {
    const kw = keyword.value.trim()
    if (!kw) {
      matches.value = []
      currentIndex.value = -1
      return
    }

    const results: SearchMatch[] = []
    const kwLower = caseSensitive.value ? kw : kw.toLowerCase()

    for (let ri = 0; ri < data.value.length; ri++) {
      const row = data.value[ri]
      for (let ci = 0; ci < searchableColumns.length; ci++) {
        const field = searchableColumns[ci]
        const val = String(row[field] ?? '')
        const valCompare = caseSensitive.value ? val : val.toLowerCase()
        if (valCompare.includes(kwLower)) {
          results.push({ row: ri, col: ci, field, value: val })
        }
      }
    }

    matches.value = results
    currentIndex.value = results.length > 0 ? 0 : -1
  }

  // 下一个匹配
  function nextMatch() {
    if (!matches.value.length) return
    currentIndex.value = (currentIndex.value + 1) % matches.value.length
  }

  // 上一个匹配
  function prevMatch() {
    if (!matches.value.length) return
    currentIndex.value = (currentIndex.value - 1 + matches.value.length) % matches.value.length
  }

  // 替换当前匹配
  function replaceOne(): boolean {
    const m = currentMatch.value
    if (!m || !replaceText.value) return false

    const row = data.value[m.row]
    if (!row) return false

    const oldVal = String(row[m.field] ?? '')
    const kw = keyword.value
    const replacement = caseSensitive.value
      ? oldVal.replace(kw, replaceText.value)
      : oldVal.replace(new RegExp(escapeRegex(kw), 'i'), replaceText.value)

    row[m.field] = replacement
    search() // 重新搜索
    return true
  }

  // 替换全部
  function replaceAll(): number {
    if (!keyword.value || !replaceText.value) return 0

    let count = 0
    const kw = keyword.value
    const regex = new RegExp(escapeRegex(kw), caseSensitive.value ? 'g' : 'gi')

    for (const row of data.value) {
      for (const field of searchableColumns) {
        const val = String(row[field] ?? '')
        if (regex.test(val)) {
          row[field] = val.replace(regex, replaceText.value)
          count++
        }
        regex.lastIndex = 0
      }
    }

    search() // 重新搜索
    return count
  }

  /**
   * 判断某单元格是否匹配（用于 cell-class-name）
   * 返回 CSS 类名
   */
  function cellMatchClass(rowIndex: number, colIndex: number): string {
    if (!keyword.value || !matches.value.length) return ''

    const isMatch = matches.value.some(m => m.row === rowIndex && m.col === colIndex)
    if (!isMatch) return ''

    const isCurrent = currentMatch.value?.row === rowIndex && currentMatch.value?.col === colIndex
    return isCurrent ? 'gt-search-match gt-search-match--current' : 'gt-search-match'
  }

  // 打开/关闭搜索栏
  function open() { isVisible.value = true }
  function close() {
    isVisible.value = false
    keyword.value = ''
    replaceText.value = ''
    matches.value = []
    currentIndex.value = -1
  }
  function toggle() { isVisible.value ? close() : open() }

  // keyword 变化时自动搜索（debounce）
  let searchTimer: ReturnType<typeof setTimeout> | null = null
  watch(keyword, () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(search, 200)
  })

  return {
    keyword,
    replaceText,
    matches,
    currentIndex,
    currentMatch,
    matchInfo,
    isVisible,
    caseSensitive,
    search,
    nextMatch,
    prevMatch,
    replaceOne,
    replaceAll,
    cellMatchClass,
    open,
    close,
    toggle,
  }
}

function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')  // 标准正则转义
}
