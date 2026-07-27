/**
 * useAdjudicationAdjustmentPull — 从集中登记按科目拉取调整分录，供审定表(X-1)带入 AJE/RJE
 *
 * spec: adjustment-collaboration-and-propagation (审定表带入增强 / K12 试点)
 *
 * 与 useAdjustmentDetailPropagation(明细行按行科目码匹配)不同：审定表按科目(subject)拉取——
 * 整张审定表对应一个科目(K12=6301)，集中调整分录中命中该科目前缀的行按分录组聚合净发生额，
 * 供审定表按目标分类行分配到 AJE/RJE 列。带入后审定数变化 → 既有 substantive:adjudicated
 * 链自动推到披露表 + 附注。
 *
 * 方向语义：
 *  - direction='credit'（损益贷方/负债/权益增益）：净额 = Σ(credit - debit)
 *  - direction='debit' （资产/损益借方增益）：      净额 = Σ(debit - credit)
 */
import { ref, type Ref } from 'vue'
import { listAdjustments } from '@/services/auditPlatformApi'

export interface AdjudicationAdjMatch {
  entry_group_id: string
  adjustment_no: string
  description?: string
  /** 分录组类型：aje→带入审定表 AJE 列 / rje→RJE 列 */
  adjustment_type: 'aje' | 'rje'
  source_wp_code?: string
  origin?: string
  /** 该分录组中命中 subject 科目的净发生额（按 direction 计算，损益贷方增益为正） */
  net: number
  /** 命中的科目名（用于目标分类行的智能猜测） */
  accountNames: string[]
}

function unwrap<T>(v: Ref<T> | (() => T) | T): T {
  if (typeof v === 'function') return (v as () => T)()
  if (v && typeof v === 'object' && 'value' in (v as any)) return (v as Ref<T>).value
  return v as T
}

export interface UseAdjudicationAdjustmentPullOptions {
  projectId: Ref<string> | (() => string) | string
  year: Ref<number> | (() => number) | number
  /** 科目码前缀（如 '6301'）；可多个 */
  subjectPrefix: string | string[]
  /** 净发生额方向；默认 'credit'（损益贷方/负债/权益） */
  direction?: 'credit' | 'debit'
}

export function useAdjudicationAdjustmentPull(opts: UseAdjudicationAdjustmentPullOptions) {
  const matches = ref<AdjudicationAdjMatch[]>([])
  const loading = ref(false)

  async function load(): Promise<void> {
    const pid = unwrap(opts.projectId)
    const yr = unwrap(opts.year)
    if (!pid || !yr) return
    const prefixes = Array.isArray(opts.subjectPrefix) ? opts.subjectPrefix : [opts.subjectPrefix]
    const direction = opts.direction ?? 'credit'
    loading.value = true
    try {
      const data: any = await listAdjustments(pid, yr, { page_size: 200 })
      const items: any[] = Array.isArray(data) ? data : (data?.items || [])
      const out: AdjudicationAdjMatch[] = []
      for (const g of items) {
        let debit = 0
        let credit = 0
        const names: string[] = []
        for (const li of (g.line_items || [])) {
          const code = String(li.standard_account_code || '')
          if (code && prefixes.some((p) => code.startsWith(p))) {
            debit += Number(li.debit_amount) || 0
            credit += Number(li.credit_amount) || 0
            if (li.account_name) names.push(String(li.account_name))
          }
        }
        if (debit === 0 && credit === 0) continue
        const net = direction === 'debit' ? debit - credit : credit - debit
        out.push({
          entry_group_id: g.entry_group_id,
          adjustment_no: g.adjustment_no,
          description: g.description,
          adjustment_type: String(g.adjustment_type || 'aje').toLowerCase() === 'rje' ? 'rje' : 'aje',
          source_wp_code: g.source_ref ? String(g.source_ref).split(':')[0] : undefined,
          origin: g.origin,
          net: Math.round(net * 100) / 100,
          accountNames: names,
        })
      }
      matches.value = out
    } catch {
      matches.value = []
    } finally {
      loading.value = false
    }
  }

  return { matches, loading, load }
}

/**
 * 智能猜测目标审定表行 rowKey（纯函数，可单测）：
 *  1. 分录摘要/科目名 与 某分类行名 互相包含 → 该行；
 *  2. 否则含"其他"的行；
 *  3. 否则最后一行。
 */
export function guessTargetRowKey(
  match: Pick<AdjudicationAdjMatch, 'description' | 'accountNames'>,
  rows: Array<{ rowKey: string; name: string }>,
): string {
  if (!rows.length) return ''
  const hay = `${match.description || ''} ${(match.accountNames || []).join(' ')}`.trim()
  if (hay) {
    for (const r of rows) {
      const n = (r.name || '').trim()
      if (n && (hay.includes(n) || n.includes(hay))) return r.rowKey
    }
  }
  const other = rows.find((r) => (r.name || '').includes('其他'))
  return other ? other.rowKey : rows[rows.length - 1].rowKey
}

export default useAdjudicationAdjustmentPull
