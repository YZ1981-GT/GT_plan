/**
 * useG2DisclosureListed — 应收利息附注披露（上市公司）
 *
 * 对齐 Excel「附注披露信息（上市公司）」+ note_template_listed §五、8：
 * ① 应收利息分类  ② 重要逾期利息  ③ 坏账准备计提情况（ECL 三阶段）
 * - 从 G2-1 / G2-2 自动取数；表③期末合计应与表①「减：坏账准备」勾稽
 * - Excel「详见 M1-1」→ 平台 wp:K1-1 + Note:五、8
 * - 发布 disclosure:note-text-updated；支持 sync-from-workpaper 写入附注模块
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistResponse } from './useF1FormData'
import { G2_ACCOUNT_CODE } from './g2NoteSectionMap'
import {
  buildDefaultClassRows,
  buildDefaultEclRows,
  classifyDetailAmounts,
  createEmptyOverdueRow,
  eclRowTotal,
  extractAdjAmounts,
  extractOverdueFromG26,
  overdueTotal,
  parseSoeDisclosure,
  recomputeClassDerived,
  recomputeEclClosing,
  serializeSoeDisclosure,
  type G2SoeClassRow,
  type G2SoeEclRow,
  type G2SoeOverdueRow,
} from './g2SoeDisclosureRows'
import type { G2SoeSyncSnapshot } from './g2DisclosureSyncPayload'

const ITEM_ROWS = 'G2-note-listed-rows'
const ITEM_NOTE = 'G2-note-listed-note'
/** 兼容旧 stub 文本持久化 */
const ITEM_NOTE_LEGACY = 'G2-disclosure-listed-text'
const ITEM_ADJ = 'G2-1-rows'
const ITEM_ADJ_LEGACY = 'G2-1-adj-rows'
const ITEM_DETAIL = 'G2-2-detail-rows'
const ITEM_OVERDUE = 'G2-6-overdue-rows'

export function useG2DisclosureListed(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const { allResponses, debouncedSave, isReadonly } = opts

  const classRows = ref<G2SoeClassRow[]>(buildDefaultClassRows())
  const overdueRows = ref<G2SoeOverdueRow[]>([])
  const eclRows = ref<G2SoeEclRow[]>(buildDefaultEclRows())
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const adjudicatedPrior = ref<number | null>(null)
  const lastSyncHint = ref('')

  function persistRows() {
    if (isReadonly.value) return
    debouncedSave(ITEM_ROWS, {
      remark: serializeSoeDisclosure({
        classRows: classRows.value,
        overdueRows: overdueRows.value,
        eclRows: eclRows.value,
      }),
    })
  }

  function loadPersisted() {
    const parsed = parseSoeDisclosure(allResponses.value.get(ITEM_ROWS)?.remark)
    if (parsed) {
      classRows.value = parsed.classRows
      overdueRows.value = parsed.overdueRows
      eclRows.value = parsed.eclRows
    }
    const note =
      allResponses.value.get(ITEM_NOTE)?.remark
      ?? allResponses.value.get(ITEM_NOTE_LEGACY)?.remark
    if (note != null) noteText.value = note
  }

  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    () => loadPersisted(),
    { immediate: true },
  )
  watch(
    () => [
      allResponses.value.get(ITEM_NOTE)?.remark,
      allResponses.value.get(ITEM_NOTE_LEGACY)?.remark,
    ],
    () => {
      const note =
        allResponses.value.get(ITEM_NOTE)?.remark
        ?? allResponses.value.get(ITEM_NOTE_LEGACY)?.remark
      if (note != null && note !== noteText.value) noteText.value = note
    },
  )

  watch(noteText, (val) => {
    if (isReadonly.value) return
    debouncedSave(ITEM_NOTE, { remark: val })
    try {
      window.dispatchEvent(
        new CustomEvent('disclosure:note-text-updated', {
          detail: { accountCode: G2_ACCOUNT_CODE, section: 'listed', text: val },
        }),
      )
    } catch {
      /* silent */
    }
  })

  const classDisplayRows = computed(() => recomputeClassDerived(classRows.value))
  const eclDisplayRows = computed(() => recomputeEclClosing(eclRows.value))

  const overdueEndTotal = computed(() => overdueTotal(overdueRows.value))

  const eclClosingTotal = computed(() => {
    const closing = eclDisplayRows.value.find((r) => r.rowKey === 'closing')
    return closing ? eclRowTotal(closing) : 0
  })

  const classProvisionEnd = computed(() => {
    const row = classDisplayRows.value.find((r) => r.rowKey === 'provision')
    return Number(row?.endAmount) || 0
  })

  /** 表③期末坏账合计 vs 表①「减：坏账准备」 */
  const provisionTieOut = computed(() => {
    const a = classProvisionEnd.value
    const b = eclClosingTotal.value
    const diff = Math.round((a - b) * 100) / 100
    return { classProvision: a, eclClosing: b, diff, matched: Math.abs(diff) < 0.01 }
  })

  function updateClassAmount(
    rowKey: string,
    field: 'endAmount' | 'priorAmount',
    value: number | null | undefined,
  ) {
    if (isReadonly.value) return
    const v = Number(value) || 0
    classRows.value = recomputeClassDerived(
      classRows.value.map((r) => (r.rowKey === rowKey && r.editable ? { ...r, [field]: v } : r)),
    )
    persistRows()
  }

  function updateEclAmount(
    rowKey: string,
    stage: 'stage1' | 'stage2' | 'stage3',
    value: number | null | undefined,
  ) {
    if (isReadonly.value) return
    const v = Number(value) || 0
    eclRows.value = recomputeEclClosing(
      eclRows.value.map((r) => (r.rowKey === rowKey && r.editable ? { ...r, [stage]: v } : r)),
    )
    persistRows()
  }

  function addOverdueRow() {
    if (isReadonly.value) return
    overdueRows.value = [...overdueRows.value, createEmptyOverdueRow()]
    persistRows()
  }

  function removeOverdueRow(id: string) {
    if (isReadonly.value) return
    overdueRows.value = overdueRows.value.filter((r) => r.id !== id)
    persistRows()
  }

  function updateOverdueField(
    id: string,
    field: keyof G2SoeOverdueRow,
    value: string | number,
  ) {
    if (isReadonly.value) return
    overdueRows.value = overdueRows.value.map((r) =>
      r.id === id ? { ...r, [field]: value } : r,
    )
    persistRows()
  }

  /** 从 G2-6 长期未收回灌入②重要逾期（默认覆盖） */
  function pullOverdueFromG26(replace = true): { pulled: number } {
    if (isReadonly.value) return { pulled: 0 }
    const pulled = extractOverdueFromG26(allResponses.value.get(ITEM_OVERDUE)?.remark)
    if (!pulled.length) return { pulled: 0 }
    if (replace || overdueRows.value.length === 0) {
      overdueRows.value = pulled
    } else {
      const existing = new Set(overdueRows.value.map((r) => r.borrower))
      overdueRows.value = [
        ...overdueRows.value,
        ...pulled.filter((r) => !existing.has(r.borrower)),
      ]
    }
    persistRows()
    return { pulled: pulled.length }
  }

  /** 从 G2-1 / G2-2 取数填充分类与坏账 */
  function refreshFromSources(force = false) {
    if (isReadonly.value && !force) return
    const adjRaw =
      allResponses.value.get(ITEM_ADJ)?.remark
      ?? allResponses.value.get(ITEM_ADJ_LEGACY)?.remark
    const adj = extractAdjAmounts(adjRaw)
    adjudicatedAmount.value = adj.netEnd
    adjudicatedPrior.value = adj.netPrior

    const classified = classifyDetailAmounts(allResponses.value.get(ITEM_DETAIL)?.remark)
    const hasDetail = Object.values(classified).some((v) => v.endAmount !== 0)

    classRows.value = recomputeClassDerived(
      classRows.value.map((r) => {
        if (r.rowKey === 'provision') {
          return {
            ...r,
            endAmount: adj.provisionEnd,
            priorAmount: adj.provisionPrior,
            autoFilled: true,
          }
        }
        if (r.kind === 'data' && hasDetail) {
          const amt = classified[r.rowKey]
          if (!amt) return r
          return {
            ...r,
            endAmount: amt.endAmount,
            priorAmount: force || r.priorAmount === 0 ? amt.priorAmount : r.priorAmount,
            autoFilled: true,
          }
        }
        if (r.rowKey === 'other' && !hasDetail && (adj.grossEnd || adj.grossPrior)) {
          return {
            ...r,
            endAmount: adj.grossEnd,
            priorAmount: adj.grossPrior,
            autoFilled: true,
          }
        }
        return r
      }),
    )

    const eclEmpty = eclRows.value
      .filter((r) => r.editable)
      .every((r) => !r.stage1 && !r.stage2 && !r.stage3)
    if (eclEmpty && (adj.provisionEnd || adj.provisionPrior)) {
      eclRows.value = recomputeEclClosing(
        eclRows.value.map((r) => {
          if (r.rowKey === 'opening') {
            return { ...r, stage1: adj.provisionPrior, stage2: 0, stage3: 0 }
          }
          if (r.rowKey === 'provision' && adj.provisionEnd !== adj.provisionPrior) {
            const delta = adj.provisionEnd - adj.provisionPrior
            return {
              ...r,
              stage1: delta > 0 ? delta : 0,
              stage2: 0,
              stage3: 0,
            }
          }
          if (r.rowKey === 'reversal' && adj.provisionEnd < adj.provisionPrior) {
            return {
              ...r,
              stage1: adj.provisionPrior - adj.provisionEnd,
              stage2: 0,
              stage3: 0,
            }
          }
          return r
        }),
      )
    }

    lastSyncHint.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    persistRows()
  }

  function handleAdjudicated(e: Event): void {
    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount?: number }>).detail
    if (d?.accountCode !== G2_ACCOUNT_CODE) return
    if (typeof d.adjudicatedAmount === 'number') {
      adjudicatedAmount.value = d.adjudicatedAmount
    }
    refreshFromSources(false)
  }

  function getSyncSnapshot(): G2SoeSyncSnapshot {
    return {
      classRows: classDisplayRows.value,
      overdueRows: overdueRows.value,
      eclRows: eclDisplayRows.value,
      auditNote: noteText.value,
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
    const hasRows = !!allResponses.value.get(ITEM_ROWS)?.remark
    if (!hasRows) refreshFromSources(true)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  })

  return {
    classRows,
    classDisplayRows,
    overdueRows,
    eclRows,
    eclDisplayRows,
    noteText,
    adjudicatedAmount,
    adjudicatedPrior,
    lastSyncHint,
    overdueEndTotal,
    eclClosingTotal,
    provisionTieOut,
    updateClassAmount,
    updateEclAmount,
    addOverdueRow,
    removeOverdueRow,
    updateOverdueField,
    pullOverdueFromG26,
    refreshFromSources,
    getSyncSnapshot,
    eclRowTotal,
  }
}
