/**
 * useLedgerBalance - 科目余额表域逻辑
 *
 * 从 LedgerPenetration.vue 拆分而来，包含：
 * - 余额数据加载
 * - 筛选（关键词/条件/级次）
 * - 树形结构构建
 * - 科目方向判定
 * - 余额行样式
 * - 导出 Excel
 *
 * @domain ledger-balance
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { fmtAmount } from '@/utils/formatters'

// ─── 类型 ───
export type BalanceFilter =
  | 'all' | 'closing' | 'opening' | 'both' | 'all_nonzero'
  | 'changed' | 'debit' | 'credit' | 'level1'

export interface BalanceRow {
  account_code: string
  account_name: string
  opening_balance: string | number | null
  closing_balance: string | number | null
  debit_amount: string | number | null
  credit_amount: string | number | null
  opening_direction?: string
  closing_direction?: string
  direction?: string
  level?: number
  children?: BalanceRow[]
  _isAncestor?: boolean
  [key: string]: any
}

// ─── 工具函数 ───
function num(v: any): number { return Number(v) || 0 }

/** 获取科目级次 */
export function getLevel(row: BalanceRow): number {
  if (row.level != null && row.level > 0) return row.level
  const code = row.account_code || ''
  if (code.includes('.')) return code.split('.').length
  if (code.length <= 4) return 1
  if (code.length <= 6) return 2
  return 3
}

/** 获取科目的父编码 */
export function getParentCode(code: string): string | null {
  if (code.includes('.')) {
    const lastDot = code.lastIndexOf('.')
    if (lastDot <= 0) return null
    return code.substring(0, lastDot)
  }
  if (code.length > 6) return code.substring(0, 6)
  if (code.length > 4) return code.substring(0, 4)
  return null
}

/**
 * 余额方向判定（显示用）
 */
export function resolveDir(row: any, period: 'opening' | 'closing'): string {
  const dirField = row[`${period}_direction`]
  if (dirField === 'credit') return '贷'
  if (dirField === 'debit') return '借'
  const code = String(row.account_code || '')
  const firstChar = code.charAt(0)
  const creditCategory = firstChar === '2' || firstChar === '3' || firstChar === '4'
  const bal = row[`${period}_balance`] ?? 0
  if (creditCategory) {
    return bal >= 0 ? '贷' : '借'
  }
  return bal >= 0 ? '借' : '贷'
}

/**
 * 余额负值含义说明（悬停提示）
 */
export function balanceTip(row: any, period: 'opening' | 'closing'): string {
  const bal = num(row[`${period}_balance`])
  if (bal >= 0) return ''
  const dir = resolveDir(row, period)
  const periodLabel = period === 'opening' ? '期初' : '期末'
  const absStr = fmtAmount(Math.abs(bal))
  const normalDir = dir === '贷' ? '借' : '贷'
  return `${periodLabel}实际为${dir}方余额 ${absStr} 元。该科目正常为${normalDir}方，出现${dir}方余额属异常方向（如红字冲销/多收退款等），负号仅表示与科目正常方向相反，金额绝对值即为${dir}方实际余额。`
}

// ─── composable ───
export function useLedgerBalance(
  projectId: Ref<string> | ComputedRef<string>,
  year: Ref<number> | ComputedRef<number>,
) {
  const balanceData = ref<BalanceRow[]>([])
  const loading = ref(false)
  const searchKeyword = ref('')
  const balanceFilter = ref<BalanceFilter>('all')
  const treeMode = ref(false)
  const balanceTableRef = ref<any>(null)
  const allExpanded = ref(false)
  const selectedRows = ref<BalanceRow[]>([])

  // ─── 筛选 ───
  const filteredBalance = computed(() => {
    let rows = balanceData.value

    if (searchKeyword.value) {
      const kw = searchKeyword.value.toLowerCase()
      rows = rows.filter(r =>
        (r.account_code || '').toLowerCase().includes(kw) ||
        (r.account_name || '').toLowerCase().includes(kw),
      )
    }

    const f = balanceFilter.value
    if (f === 'closing') {
      rows = rows.filter(r => num(r.closing_balance) !== 0)
    } else if (f === 'opening') {
      rows = rows.filter(r => num(r.opening_balance) !== 0)
    } else if (f === 'both') {
      rows = rows.filter(r => num(r.opening_balance) !== 0 && num(r.closing_balance) !== 0)
    } else if (f === 'all_nonzero') {
      rows = rows.filter(r => {
        const hasMovement = num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0
        const code = String(r.account_code || '')
        const isIncomeExpense = code.startsWith('5') || code.startsWith('6')
        if (isIncomeExpense) return hasMovement
        return num(r.opening_balance) !== 0 && hasMovement && num(r.closing_balance) !== 0
      })
    } else if (f === 'changed') {
      rows = rows.filter(r => num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0)
    } else if (f === 'debit') {
      rows = rows.filter(r => num(r.debit_amount) !== 0)
    } else if (f === 'credit') {
      rows = rows.filter(r => num(r.credit_amount) !== 0)
    } else if (f === 'level1') {
      rows = rows.filter(r => getLevel(r) === 1)
    }

    return rows
  })

  const filteredFlatCount = computed(() => filteredBalance.value.length)

  // ─── 树形构建 ───
  const treeBalance = computed(() => {
    if (!treeMode.value) return []
    const rows = filteredBalance.value
    if (rows.length === 0) return []
    if (balanceFilter.value === 'level1') return rows

    const map = new Map<string, any>()
    const roots: any[] = []

    for (const row of rows) {
      map.set(row.account_code, { ...row, children: [] })
    }

    for (const row of rows) {
      const node = map.get(row.account_code)!
      const pc = getParentCode(row.account_code)
      if (pc && map.has(pc)) {
        map.get(pc)!.children.push(node)
      } else {
        roots.push(node)
      }
    }

    for (const [, node] of map) {
      if (node.children.length === 0) delete node.children
    }

    return roots.length > 0 ? roots : rows
  })

  // ─── 行样式 ───
  function balanceRowStyle({ row }: { row: any }) {
    const level = getLevel(row)
    const style: Record<string, string> = {}
    if (level === 1) {
      style.fontWeight = '600'
      style.background = '#f8f5fc'
    }
    if (row._isAncestor) {
      style.color = '#999'
      style.fontStyle = 'italic'
    }
    return style
  }

  // ─── 展开/折叠 ───
  function toggleExpandAll() {
    allExpanded.value = !allExpanded.value
    if (balanceTableRef.value) {
      const rows = filteredBalance.value
      for (const row of rows) {
        balanceTableRef.value.toggleRowExpansion(row, allExpanded.value)
      }
    }
  }

  // ─── 滚动定位到科目 ───
  function scrollToAccount(accountCode: string) {
    let retries = 0
    const maxRetries = 10

    function tryScroll() {
      retries++
      const tableEl = balanceTableRef.value
      if (!tableEl || !filteredBalance.value.length) {
        if (retries < maxRetries) setTimeout(tryScroll, 300)
        return
      }

      const rows = filteredBalance.value
      let targetIdx = rows.findIndex((r: any) => r.account_code === accountCode)
      if (targetIdx < 0) {
        targetIdx = rows.findIndex((r: any) => r.account_code?.startsWith(accountCode))
      }
      if (targetIdx < 0) {
        if (retries < maxRetries) setTimeout(tryScroll, 300)
        return
      }

      tableEl.setCurrentRow(rows[targetIdx])

      setTimeout(() => {
        const tbody = tableEl.$el?.querySelector('.el-table__body-wrapper')
        const rowEls = tbody?.querySelectorAll('tr.el-table__row')
        const rowEl = rowEls?.[targetIdx]
        if (rowEl) {
          rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' })
          rowEl.style.transition = 'background 0.3s'
          rowEl.style.background = '#fff3cd'
          setTimeout(() => { rowEl.style.background = '' }, 4000)
        }
      }, 100)
    }

    setTimeout(tryScroll, 500)
  }

  function onSelectionChange(rows: BalanceRow[]) {
    selectedRows.value = rows
  }

  return {
    // 数据
    balanceData,
    loading,
    searchKeyword,
    balanceFilter,
    treeMode,
    balanceTableRef,
    allExpanded,
    selectedRows,
    // computed
    filteredBalance,
    filteredFlatCount,
    treeBalance,
    // 方法
    balanceRowStyle,
    toggleExpandAll,
    scrollToAccount,
    onSelectionChange,
    // 工具（re-export for template use）
    resolveDir,
    balanceTip,
    getLevel,
    getParentCode,
    num,
  }
}
