/**
 * useG1Disclosure — G1 附注披露逻辑（上市 198行虚拟滚动 / 国企 32行）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 4.3
 *
 * 职责：
 * - 上市附注(198行×12列，>50行启用虚拟滚动) + 国企附注(32行×5列)
 * - 结构化行数据（label / endAmount / priorAmount / remark）+ 动态行增删 + 合计
 * - 附注说明 textarea 持久化（debounce）
 * - subscribe EventBus `substantive:adjudicated`(accountCode='1501') 自动刷新审定数
 * - publish EventBus `disclosure:note-text-updated` 联动附注模块
 *
 * Requirements: 4.1~4.5, 14.3
 */
import { ref, computed, watch, onScopeDispose, type Ref } from 'vue'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type G1DisclosureVariant = 'listed' | 'soe'

export interface G1DisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
  remark?: string
}

/** 科目：交易性金融资产 */
export const G1_ACCOUNT_CODE = '1501'

/** 虚拟滚动阈值（行数 > 50 启用） */
export const G1_VIRTUAL_SCROLL_THRESHOLD = 50

/** 各变体最大行数（模板参考） */
export const G1_DISCLOSURE_MAX_ROWS: Record<G1DisclosureVariant, number> = {
  listed: 198,
  soe: 32,
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : Date.now().toString(36) + Math.random().toString(36).slice(2)
  }`
}

function safeParseRows(jsonStr: string | null | undefined): G1DisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function createEmptyRow(): G1DisclosureRow {
  return { rowId: generateRowId(), label: '', endAmount: 0, priorAmount: 0, remark: '' }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG1Disclosure(opts: {
  variant: G1DisclosureVariant
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const { variant, allResponses, debouncedSave, isReadonly } = opts

  const PREFIX = `G1-note-${variant}-`
  const ITEM_ROWS = `${PREFIX}rows`
  const ITEM_NOTE = `${PREFIX}note`

  // ─── 行数据 ──────────────────────────────────────────────────────────

  const rows = ref<G1DisclosureRow[]>(safeParseRows(allResponses.value.get(ITEM_ROWS)?.remark))

  // allResponses 异步加载完成后回填（用户未编辑时）
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (jsonStr) => {
      const parsed = safeParseRows(jsonStr)
      if (parsed.length) rows.value = parsed
    },
  )

  const subtotal = computed<G1DisclosureRow>(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(rows.value.map((r) => r.priorAmount)),
  }))

  /** >50行启用虚拟滚动（上市198行） */
  const enableVirtualScroll = computed(() => rows.value.length > G1_VIRTUAL_SCROLL_THRESHOLD)

  const maxRows = G1_DISCLOSURE_MAX_ROWS[variant]

  function persistRows() {
    if (isReadonly.value) return
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function addRow() {
    if (isReadonly.value || rows.value.length >= maxRows) return
    rows.value = [...rows.value, createEmptyRow()]
    persistRows()
  }

  function removeRow(rowId: string) {
    if (isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: keyof G1DisclosureRow, value: unknown) {
    if (isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows.value[idx] }
    if (field === 'endAmount' || field === 'priorAmount') {
      row[field] = parseNum(value as string | number)
    } else {
      ;(row as Record<string, unknown>)[field] = value
    }
    const next = [...rows.value]
    next[idx] = row
    rows.value = next
    persistRows()
  }

  // ─── 附注说明 textarea ──────────────────────────────────────────────

  const noteText = ref(allResponses.value.get(ITEM_NOTE)?.remark ?? '')

  watch(
    () => allResponses.value.get(ITEM_NOTE)?.remark,
    (v) => {
      if (!noteText.value && v) noteText.value = v
    },
  )

  watch(noteText, (val) => {
    if (isReadonly.value) return
    debouncedSave(ITEM_NOTE, { remark: val })
    // publish 联动附注模块
    try {
      window.dispatchEvent(
        new CustomEvent('disclosure:note-text-updated', {
          detail: { wpCode: 'G1', accountCode: G1_ACCOUNT_CODE, type: variant, text: val },
        }),
      )
    } catch {
      /* silent */
    }
  })

  // ─── EventBus: subscribe substantive:adjudicated(1501) ──────────────

  /** 最近一次收到的审定数（供组件展示/刷新提示） */
  const adjudicatedAmount = ref<number | null>(null)
  /** 审定刷新计数（组件可 watch 触发刷新提示） */
  const adjudicatedRefreshTick = ref(0)

  function onAdjudicated(e: Event) {
    const detail = (e as CustomEvent).detail
    if (detail?.accountCode === G1_ACCOUNT_CODE) {
      if (typeof detail.auditedAmount === 'number') {
        adjudicatedAmount.value = detail.auditedAmount
      } else if (typeof detail.adjudicatedAmount === 'number') {
        adjudicatedAmount.value = detail.adjudicatedAmount
      }
      adjudicatedRefreshTick.value += 1
    }
  }

  window.addEventListener('substantive:adjudicated', onAdjudicated)

  onScopeDispose(() => {
    window.removeEventListener('substantive:adjudicated', onAdjudicated)
  })

  return {
    variant,
    maxRows,
    rows,
    subtotal,
    enableVirtualScroll,
    noteText,
    adjudicatedAmount,
    adjudicatedRefreshTick,
    addRow,
    removeRow,
    updateCell,
    persistRows,
  }
}

export default useG1Disclosure
