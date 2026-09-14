/**
 * useL2Disclosure — L2 应付利息附注披露（上市/国企）共享逻辑 composable
 *
 * 对齐致同源模板「附注披露信息」结构（2026-07 复盘）：
 * - 分类表固定行（源模板 5 类 + 优先股/永续债[工具1/工具2] + 其他 + 合计）
 * - 数据 SUMIF 等价从 L2-2 明细按类别聚合：
 *   期末余额 = Σ 明细审定期末(audited)；上年年末/期初余额 = Σ 明细审定期初(adjustedBegin)
 * - 重要的逾期未付利息表（借款单位/逾期金额/逾期原因）
 *
 * 上市版列头「上年年末余额」，国企版列头「期初余额」，数据同源（审定期初）。
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisclosureRow {
  rowKey: string
  label: string
  isSub: boolean
  isTotal: boolean
  /** 期末余额（审定期末合计） */
  endAmount: number
  /** 上年年末 / 期初余额（审定期初合计） */
  priorAmount: number
}

export interface OverdueDisclosureRow {
  borrower: string
  overdueAmount: number
  overdueReason: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_DETAIL_ROWS = 'L2-L2-2-rows'

/** 附注分类固定行（对齐源模板 A8~A14） */
const DISCLOSURE_ROWS = [
  { rowKey: 'long-term-loan', label: '分期付息到期还本的长期借款利息', isSub: false },
  { rowKey: 'corporate-bond', label: '企业债券利息', isSub: false },
  { rowKey: 'short-term-loan', label: '短期借款应付利息', isSub: false },
  { rowKey: 'preferred-perpetual', label: '划分为金融负债的优先股/永续债利息', isSub: false },
  { rowKey: 'tool1', label: '其中：工具1', isSub: true },
  { rowKey: 'tool2', label: '工具2', isSub: true },
  { rowKey: 'other', label: '其他', isSub: false },
] as const

/** 参与合计的主行（源模板 =SUM(B8:B11,B14)） */
const TOTAL_KEYS = ['long-term-loan', 'corporate-bond', 'short-term-loan', 'preferred-perpetual', 'other']
const PREFERRED_SUB_KEYS = ['tool1', 'tool2']

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 明细类别 → 附注 rowKey 关键词映射 */
function detailSourceToRowKey(source: string): string {
  const s = source || ''
  if (s.includes('长期借款') || s.includes('分期付息')) return 'long-term-loan'
  if (s.includes('债券')) return 'corporate-bond'
  if (s.includes('短期借款')) return 'short-term-loan'
  if (s.includes('工具1')) return 'tool1'
  if (s.includes('工具2')) return 'tool2'
  if (s.includes('优先股') || s.includes('永续债')) return 'preferred-perpetual'
  if (s.includes('其他')) return 'other'
  return 'other'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL2Disclosure(allResponses: Ref<Map<string, ChecklistResponse>>) {
  /** 从 L2-2 明细按类别聚合（审定期末 + 审定期初） */
  const aggByCategory = computed<Record<string, { end: number; prior: number }>>(() => {
    const raw = allResponses.value.get(ITEM_DETAIL_ROWS)?.remark
    const agg: Record<string, { end: number; prior: number }> = {}
    if (!raw) return agg
    let rows: any[] = []
    try {
      const p = JSON.parse(raw)
      rows = Array.isArray(p) ? p : []
    } catch {
      return agg
    }
    for (const r of rows) {
      const key = detailSourceToRowKey(r.source)
      if (!agg[key]) agg[key] = { end: 0, prior: 0 }
      // 审定期末优先取 audited，回退 endBalance；审定期初取 adjustedBegin
      agg[key].end += (r.audited != null ? parseNum(r.audited) : parseNum(r.endBalance))
      agg[key].prior += parseNum(r.adjustedBegin)
    }
    return agg
  })

  const disclosureRows: ComputedRef<DisclosureRow[]> = computed(() => {
    const agg = aggByCategory.value

    // 优先股/永续债汇总 = 工具1 + 工具2
    const preferredEnd = PREFERRED_SUB_KEYS.reduce((s, k) => s + (agg[k]?.end ?? 0), 0)
    const preferredPrior = PREFERRED_SUB_KEYS.reduce((s, k) => s + (agg[k]?.prior ?? 0), 0)

    const rows: DisclosureRow[] = DISCLOSURE_ROWS.map(def => {
      let end = agg[def.rowKey]?.end ?? 0
      let prior = agg[def.rowKey]?.prior ?? 0
      if (def.rowKey === 'preferred-perpetual') {
        end = preferredEnd
        prior = preferredPrior
      }
      return {
        rowKey: def.rowKey,
        label: def.label,
        isSub: def.isSub,
        isTotal: false,
        endAmount: end,
        priorAmount: prior,
      }
    })
    return rows
  })

  const totalRow: ComputedRef<DisclosureRow> = computed(() => {
    const rows = disclosureRows.value.filter(r => TOTAL_KEYS.includes(r.rowKey))
    return {
      rowKey: '__total__',
      label: '合计',
      isSub: false,
      isTotal: true,
      endAmount: rows.reduce((s, r) => s + r.endAmount, 0),
      priorAmount: rows.reduce((s, r) => s + r.priorAmount, 0),
    }
  })

  /** 分类表全部行（含合计） */
  const disclosureTableData: ComputedRef<DisclosureRow[]> = computed(() => [
    ...disclosureRows.value,
    totalRow.value,
  ])

  /** 重要的逾期未付利息（从明细 isOverdue 行提取） */
  const overdueRows: ComputedRef<OverdueDisclosureRow[]> = computed(() => {
    const raw = allResponses.value.get(ITEM_DETAIL_ROWS)?.remark
    if (!raw) return []
    let rows: any[] = []
    try {
      const p = JSON.parse(raw)
      rows = Array.isArray(p) ? p : []
    } catch {
      return []
    }
    return rows
      .filter(r => Boolean(r.isOverdue) || parseNum(r.overdueMonths) > 0)
      .map(r => ({
        borrower: r.creditor || r.contractName || '-',
        overdueAmount: (r.audited != null ? parseNum(r.audited) : parseNum(r.endBalance)),
        overdueReason: r.overdueReason || '-',
      }))
  })

  return {
    disclosureRows,
    totalRow,
    disclosureTableData,
    overdueRows,
  }
}

export default useL2Disclosure
