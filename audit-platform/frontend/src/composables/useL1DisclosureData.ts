/**
 * useL1DisclosureData — L1 附注披露信息核对 共享数据 composable（2026-07 复盘重建）
 *
 * 对齐致同源模板「附注披露信息核对（上市公司/国企）」：
 * - (1) 短期借款分类：4 类（信用/抵押/保证/质押）× 期末余额 / 上年年末（年初）余额
 *   源模板 SUMIF('明细表L1-2'!B:B, 类别, 审定期末/期初)；本实现从审定表 L1-1 各分类审定数派生
 *   （审定表本身即按类型 SUMIF 明细，故披露 → 审定 → 明细 链一致，且为审定后金额）。
 * - (2) 逾期借款情况：借款单位/期末余额/借款利率（+ 上市版 逾期时间/逾期利率）
 *   审计师录入（可从 L1-7 逾期检查带入），存 JSON。
 *
 * ⚠️ 旧版披露为 bank-level 手工录入 + 死链交叉校验（读 L1-detail-total-end，从不写 → 恒"一致"）。
 *    本次重建为源模板 category-level 自派生 + 真实合计。
 *
 * 依赖父入口 provide 的共享 useL1FormData（allResponses 与审定表共享 → 审定变更自动反映）。
 */
import { computed, ref, watch, onUnmounted, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { useL1FormData } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface L1DisclosureCategoryRow {
  category: string      // 信用借款/抵押借款/保证借款/质押借款
  beginBalance: number  // 上年年末（年初）余额 = 审定期初
  endBalance: number    // 期末余额 = 审定期末
}

export interface L1DisclosureOverdueRow {
  borrower: string      // 借款单位/债权单位
  endBalance: number    // 期末余额
  rate: number          // 借款利率
  overdueTime: string   // 逾期时间（上市版）
  penaltyRate: number   // 逾期利率（上市版）
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 审定表 L1-1 分类顺序（与 useL1FormData DEFAULT_CATEGORIES 一致：信用/抵押/保证/质押） */
const CATEGORIES = ['信用借款', '抵押借款', '保证借款', '质押借款'] as const
const OVERDUE_ROWS_KEY = 'L1-disclosure-overdue-rows'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL1DisclosureData(
  formData: ReturnType<typeof useL1FormData>,
  opts: { variant: 'listed' | 'soe'; isReadonly: Ref<boolean> },
) {
  const { getItemValue, debounceSave } = formData

  // allResponses 为普通 Map，saveImmediate 的 .set() 不触发 ref 追踪；
  // 审定表保存后经 eventBus 通知 → 递增 refreshTick 强制分类表 computed 从最新 Map 重算。
  const refreshTick = ref(0)
  const _onAdjChange = () => { refreshTick.value++ }
  eventBus.on('substantive:adjudicated', _onAdjChange)
  eventBus.on('adjustment:created', _onAdjChange)
  onUnmounted(() => {
    eventBus.off('substantive:adjudicated', _onAdjChange)
    eventBus.off('adjustment:created', _onAdjChange)
  })

  // ─── (1) 分类表：从审定表 L1-1 各分类审定数派生 ─────────────────────────

  function _num(itemId: string): number {
    const v = getItemValue(itemId)
    return v != null ? (Number(v) || 0) : 0
  }

  const categoryRows: ComputedRef<L1DisclosureCategoryRow[]> = computed(() => {
    void refreshTick.value // 依赖刷新tick
    return CATEGORIES.map((name, i) => {
      const n = i + 1
      const beginAudited = _num(`L1-adj-${n}-beginUnadjusted`) + _num(`L1-adj-${n}-beginAje`) + _num(`L1-adj-${n}-beginRje`)
      const endAudited = _num(`L1-adj-${n}-endUnadjusted`) + _num(`L1-adj-${n}-endAje`) + _num(`L1-adj-${n}-endRje`)
      return { category: name, beginBalance: beginAudited, endBalance: endAudited }
    })
  })

  const categoryTotal: ComputedRef<{ begin: number; end: number }> = computed(() => ({
    begin: categoryRows.value.reduce((s, r) => s + r.beginBalance, 0),
    end: categoryRows.value.reduce((s, r) => s + r.endBalance, 0),
  }))

  // ─── (2) 逾期借款表：审计师录入（JSON 持久化） ─────────────────────────

  const overdueRows = ref<L1DisclosureOverdueRow[]>([])

  function _hydrateOverdue(): void {
    const raw = getItemValue(OVERDUE_ROWS_KEY)
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) overdueRows.value = parsed
    } catch { /* ignore */ }
  }
  _hydrateOverdue()
  // 异步 selfLoad 返回后二次水合
  watch(() => getItemValue(OVERDUE_ROWS_KEY), (v) => {
    if (v && overdueRows.value.length === 0) _hydrateOverdue()
  })

  function _persistOverdue(): void {
    if (opts.isReadonly.value) return
    debounceSave([{ item_id: OVERDUE_ROWS_KEY, conclusion: null, remark: JSON.stringify(overdueRows.value) }])
  }

  function addOverdueRow(): void {
    overdueRows.value.push({ borrower: '', endBalance: 0, rate: 0, overdueTime: '', penaltyRate: 0 })
    _persistOverdue()
  }
  function removeOverdueRow(index: number): void {
    if (index < 0 || index >= overdueRows.value.length) return
    overdueRows.value.splice(index, 1)
    _persistOverdue()
  }
  function updateOverdueRow(index: number, field: keyof L1DisclosureOverdueRow, value: string | number): void {
    if (index < 0 || index >= overdueRows.value.length) return
    ;(overdueRows.value[index] as any)[field] = value
    _persistOverdue()
  }

  const overdueTotal: ComputedRef<number> = computed(() =>
    overdueRows.value.reduce((s, r) => s + (Number(r.endBalance) || 0), 0),
  )

  /** 从 L1-7 逾期检查带入（读逾期检查行；仅当逾期检查有数据时） */
  function importFromOverdueCheck(): number {
    const rows = (formData as any).overdueCheckRows?.value as any[] | undefined
    if (!rows || rows.length === 0) return 0
    const mapped: L1DisclosureOverdueRow[] = rows
      .filter(r => (Number(r.overdueAmount) || 0) > 0)
      .map(r => ({
        borrower: r.contractNo || '',
        endBalance: Number(r.overdueAmount) || 0,
        rate: 0,
        overdueTime: r.overdueDays ? `${r.overdueDays}天` : '',
        penaltyRate: 0,
      }))
    if (mapped.length === 0) return 0
    overdueRows.value = mapped
    _persistOverdue()
    return mapped.length
  }

  // ─── 说明 / 结论 ────────────────────────────────────────────────────────

  const noteKey = `L1-disclosure-${opts.variant}-note`
  const conclusionKey = `L1-disclosure-${opts.variant}-conclusion`
  const noteText = ref(getItemValue(noteKey) ?? '')
  const conclusionText = ref(getItemValue(conclusionKey) ?? '')

  watch(() => getItemValue(noteKey), (v) => { if (v != null && !noteText.value) noteText.value = v })
  watch(() => getItemValue(conclusionKey), (v) => { if (v != null && !conclusionText.value) conclusionText.value = v })

  function updateNote(v: string): void {
    noteText.value = v
    if (opts.isReadonly.value) return
    debounceSave([{ item_id: noteKey, conclusion: null, remark: v || null }])
  }
  function updateConclusion(v: string): void {
    conclusionText.value = v
    if (opts.isReadonly.value) return
    debounceSave([{ item_id: conclusionKey, conclusion: null, remark: v || null }])
  }

  return {
    categoryRows,
    categoryTotal,
    overdueRows,
    overdueTotal,
    addOverdueRow,
    removeOverdueRow,
    updateOverdueRow,
    importFromOverdueCheck,
    noteText,
    conclusionText,
    updateNote,
    updateConclusion,
  }
}

export default useL1DisclosureData
