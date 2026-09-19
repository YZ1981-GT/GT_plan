/**
 * useAdjustmentDetailPropagation — 调整分录 → 明细表联动（读时匹配，无持久化）
 *
 * spec: adjustment-collaboration-and-propagation (Part B)
 *
 * 明细表明细行按标准科目读时匹配集中登记调整分录明细行：
 *  - 标注"受 N 笔调整影响" + 跳转到集中调整页。
 *  - 供带入弹窗列出可带入的调整明细行。
 * 数据源复用既有 `GET /adjustments`（返回 line_items 含 standard_account_code）。
 * 标注为读时计算，随调整变更下次加载自动刷新（无 drift）。
 */
import { ref, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { listAdjustments } from '@/services/auditPlatformApi'

export interface AdjustmentLineMatch {
  entry_group_id: string
  adjustment_no: string
  adjustment_type: string           // 'aje' | 'rje'
  description?: string
  source_wp_code?: string
  origin?: string
  standard_account_code: string
  /** 明细/二级科目码（V127）：有则优先用于精确匹配底稿明细行；NULL 时回退 standard_account_code。 */
  detail_account_code?: string | null
  account_name?: string
  debit_amount: number
  credit_amount: number
}

function unwrap<T>(v: Ref<T> | (() => T) | T): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as any)) return (v as Ref<T>).value
  return v as T
}

/** 明细行科目是否匹配某调整明细行标准科目（精确 或 明细子科目上卷到该标准科目）。 */
export function accountMatches(rowStdCode: string, adjStdCode: string): boolean {
  const a = (rowStdCode || '').trim()
  const b = (adjStdCode || '').trim()
  if (!a || !b) return false
  return a === b || a.startsWith(b) || b.startsWith(a)
}

export interface UseAdjustmentDetailPropagationOptions {
  projectId: Ref<string> | (() => string) | string
  year: Ref<number> | (() => number) | number
}

export function useAdjustmentDetailPropagation(opts: UseAdjustmentDetailPropagationOptions) {
  const allLines = ref<AdjustmentLineMatch[]>([])
  const loaded = ref(false)

  async function load(): Promise<void> {
    const projectId = unwrap(opts.projectId)
    const year = unwrap(opts.year)
    if (!projectId || !year) return
    try {
      const data: any = await listAdjustments(projectId, year, { page_size: 200 })
      const items: any[] = Array.isArray(data) ? data : (data?.items || [])
      const flat: AdjustmentLineMatch[] = []
      for (const g of items) {
        for (const li of (g.line_items || [])) {
          flat.push({
            entry_group_id: g.entry_group_id,
            adjustment_no: g.adjustment_no,
            adjustment_type: String(g.adjustment_type || '').toLowerCase(),
            description: g.description,
            source_wp_code: g.source_ref ? String(g.source_ref).split(':')[0] : undefined,
            origin: g.origin,
            standard_account_code: li.standard_account_code,
            detail_account_code: li.detail_account_code ?? null,
            account_name: li.account_name,
            debit_amount: Number(li.debit_amount) || 0,
            credit_amount: Number(li.credit_amount) || 0,
          })
        }
      }
      allLines.value = flat
      loaded.value = true
    } catch {
      allLines.value = []
      loaded.value = true
    }
  }

  /**
   * 匹配某标准科目的全部调整明细行（金额非零）。
   * 优先用调整行的 detail_account_code（明细码）做精确/上卷匹配，使调整精确对应到
   * 审计师选定的明细行；detail_account_code 为空时回退 standard_account_code（历史零回归）。
   */
  function matchByAccount(stdCode: string): AdjustmentLineMatch[] {
    if (!stdCode) return []
    return allLines.value.filter((l) => {
      const effectiveCode = (l.detail_account_code || l.standard_account_code)
      return accountMatches(stdCode, effectiveCode)
        && ((l.debit_amount || 0) !== 0 || (l.credit_amount || 0) !== 0)
    })
  }

  /** "受 N 笔调整影响" 计数。 */
  function countForRow(stdCode: string): number {
    return matchByAccount(stdCode).length
  }

  const router = useRouter()
  function jumpToAdjustment(entryGroupId: string): void {
    const projectId = unwrap(opts.projectId)
    router.push({
      name: 'Adjustments',
      params: { projectId },
      query: { group: entryGroupId },
    }).catch(() => { /* 导航异常允许 */ })
  }

  return { allLines, loaded, load, matchByAccount, countForRow, jumpToAdjustment }
}

export default useAdjustmentDetailPropagation
