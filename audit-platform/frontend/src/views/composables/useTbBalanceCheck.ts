/**
 * useTbBalanceCheck - 试算平衡计算域逻辑
 *
 * 从 TrialBalance.vue 拆分而来，包含：
 * - 资产 / 负债 / 权益分组汇总
 * - 损益类（收入 - 成本 - 费用 = 净利润）
 * - 完整试算平衡（全科目借贷合计）
 * - 借贷平衡指示器
 * - 科目方向判定与切换
 * - 分组行（小计/合计）插入
 *
 * @domain tb-balance-check
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'

// ─── 类型 ───
export interface DisplayRow {
  standard_account_code: string
  account_name: string
  unadjusted_amount: string | number | null
  aje_adjustment: string | number | null
  rje_adjustment: string | number | null
  audited_amount: string | number | null
  direction?: string
  row_code?: string
  wp_consistency?: { status: string; diff_amount?: number }
  _isSubtotal?: boolean
  _isTotal?: boolean
  _cat?: string
  [key: string]: any
}

type DecimalOp = (a: number | string, b: number | string) => number

export function useTbBalanceCheck(
  projectId: Ref<string> | ComputedRef<string>,
  year: Ref<number> | ComputedRef<number>,
  rows: Ref<DisplayRow[]>,
  decAdd: DecimalOp,
  decSub: DecimalOp,
) {
  // ─── 数据新鲜度 ───
  const lastRecalcAt = ref<string | null>(null)
  const latestAdjustmentAt = ref<string | null>(null)
  const staleAccountCodes = ref<Set<string>>(new Set())

  const isStale = computed(() => {
    if (!lastRecalcAt.value || !latestAdjustmentAt.value) return false
    return new Date(latestAdjustmentAt.value) > new Date(lastRecalcAt.value)
  })

  const freshnessText = computed(() => {
    if (!lastRecalcAt.value) return ''
    const d = new Date(lastRecalcAt.value)
    const now = new Date()
    const diff = Math.round((now.getTime() - d.getTime()) / 60000)
    if (diff < 1) return '刚刚'
    if (diff < 60) return `${diff}分钟前`
    if (diff < 1440) return `${Math.round(diff / 60)}小时前`
    return `${Math.round(diff / 1440)}天前`
  })

  // ─── 科目分类 ───
  function getActualCat(r: any): string {
    const code = String(r.standard_account_code || '')
    const firstChar = code.charAt(0)
    if (firstChar === '1') return 'asset'
    if (firstChar === '2') return 'liability'
    if (firstChar === '3') return 'equity'
    if (firstChar === '4' || firstChar === '5') return 'income_expense'
    if (firstChar === '6') return 'expense'
    return 'other'
  }

  // ─── 分组行构建 ───
  const groupedRows = computed(() => {
    if (rows.value.length === 0) return []

    const result: DisplayRow[] = []
    let currentCat = ''
    let catRows: DisplayRow[] = []

    function flushCat() {
      if (catRows.length === 0) return
      result.push(...catRows)
      // 插入小计行
      const subtotal: DisplayRow = {
        standard_account_code: '',
        account_name: `${getCatLabel(currentCat)} 小计`,
        unadjusted_amount: sumField(catRows, 'unadjusted_amount'),
        aje_adjustment: sumField(catRows, 'aje_adjustment'),
        rje_adjustment: sumField(catRows, 'rje_adjustment'),
        audited_amount: sumField(catRows, 'audited_amount'),
        _isSubtotal: true,
        _cat: currentCat,
      }
      result.push(subtotal)
      catRows = []
    }

    for (const r of rows.value) {
      const cat = getActualCat(r)
      if (cat !== currentCat && currentCat) {
        flushCat()
      }
      currentCat = cat
      catRows.push(r)
    }
    flushCat()

    return result
  })

  function getCatLabel(cat: string): string {
    const labels: Record<string, string> = {
      asset: '资产',
      liability: '负债',
      equity: '所有者权益',
      income_expense: '损益',
      expense: '费用',
      other: '其他',
    }
    return labels[cat] || cat
  }

  function sumField(items: DisplayRow[], field: string): number {
    return items.reduce((sum, r) => {
      const v = Number((r as any)[field]) || 0
      return decAdd(sum, v) as number
    }, 0)
  }

  // ─── 借贷平衡 ───
  const isBalanced = computed(() => {
    const totalDebit = rows.value.reduce((sum, r) => {
      const unadj = Number(r.unadjusted_amount) || 0
      // 借方科目(1/5)的正数在借方
      const cat = getActualCat(r)
      if (cat === 'asset' || cat === 'expense') return decAdd(sum, Math.max(0, unadj)) as number
      return sum
    }, 0)
    const totalCredit = rows.value.reduce((sum, r) => {
      const unadj = Number(r.unadjusted_amount) || 0
      const cat = getActualCat(r)
      if (cat === 'liability' || cat === 'equity' || cat === 'income_expense') return decAdd(sum, Math.max(0, unadj)) as number
      return sum
    }, 0)
    return Math.abs(totalDebit - totalCredit) < 0.01
  })

  const balanceTooltip = computed(() => {
    return isBalanced.value
      ? '全科目借方合计 = 贷方合计'
      : '借方合计 ≠ 贷方合计，请检查数据完整性'
  })

  // ─── 方向判定 ───
  function getDirection(row: any): string {
    if (row.direction === 'credit' || row.direction === '贷') return '贷'
    if (row.direction === 'debit' || row.direction === '借') return '借'
    const code = String(row.standard_account_code || '')
    const firstChar = code.charAt(0)
    if (firstChar === '2' || firstChar === '3' || firstChar === '4') return '贷'
    return '借'
  }

  function getDirectionClass(row: any): string {
    const dir = getDirection(row)
    return dir === '贷' ? 'gt-dir-credit' : 'gt-dir-debit'
  }

  function toggleDirection(row: any) {
    row.direction = getDirection(row) === '借' ? 'credit' : 'debit'
  }

  // ─── 行样式 ───
  function rowClassName({ row }: { row: DisplayRow }) {
    const classes: string[] = []
    if (row._isSubtotal) classes.push('gt-tb-subtotal-row')
    if (row._isTotal) classes.push('gt-tb-total-row')
    if (staleAccountCodes.value.has(row.standard_account_code)) classes.push('gt-tb-stale-row')
    return classes.join(' ')
  }

  // ─── 加载新鲜度数据 ───
  async function loadLatestAdjustmentTime() {
    try {
      const data = await api.get(
        `/api/projects/${projectId.value}/adjustments/latest-time`,
        { params: { year: year.value } },
      )
      latestAdjustmentAt.value = data?.latest_at || null
    } catch { /* ignore */ }
  }

  return {
    // 状态
    lastRecalcAt,
    latestAdjustmentAt,
    staleAccountCodes,
    // computed
    isStale,
    freshnessText,
    groupedRows,
    isBalanced,
    balanceTooltip,
    // 方法
    getActualCat,
    getDirection,
    getDirectionClass,
    toggleDirection,
    rowClassName,
    loadLatestAdjustmentTime,
  }
}
