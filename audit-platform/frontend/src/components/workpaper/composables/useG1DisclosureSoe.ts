/**
 * useG1DisclosureSoe — 交易性金融资产附注披露（国企）
 *
 * 对齐 Excel「附注披露信息（国企）」+ note_template_soe §八、2 / §八、3：
 * - 交易性金融资产：分类/指定 × 品种层级 + 公允价值确认依据
 * - 衍生金融资产：前十大明细 + 合计
 * - 从 G1-1（G1-1-rows）自动取 carrying 审定数
 * - 发布 disclosure:note-text-updated；支持 sync-from-workpaper 写入附注模块
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { parseNum } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { G1_ACCOUNT_CODE } from './g1NoteSectionMap'
import {
  buildDefaultTradingRows,
  createEmptyDerivativeRow,
  extractSoeAmountsFromAdjStore,
  parseSoePersisted,
  recomputeCategoryTotals,
  serializeSoeRows,
  tradingTotal,
  type G1SoeDerivativeRow,
  type G1SoeTradingRow,
} from './g1SoeDisclosureRows'
import type { G1SoeSyncSnapshot } from './g1DisclosureSyncPayload'

const ITEM_ROWS = 'G1-note-soe-rows'
const ITEM_NOTE = 'G1-note-soe-note'
const ITEM_FV_BASIS = 'G1-note-soe-fv-basis'
const ITEM_DERIV_TIP = 'G1-note-soe-derivative-tip'
const ITEM_ADJ_ROWS = 'G1-1-rows'

const DEFAULT_FV_HINT = '（注：应披露公允价值确认依据。）'
const DEFAULT_DERIV_HINT = '【提示：披露金额较大的前十项及其产生的原因，其余汇总填列。】'

export function useG1DisclosureSoe(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const { allResponses, debouncedSave, isReadonly } = opts

  const tradingRows = ref<G1SoeTradingRow[]>(buildDefaultTradingRows())
  const derivativeRows = ref<G1SoeDerivativeRow[]>([])
  const fvBasisNote = ref(DEFAULT_FV_HINT)
  const derivativeTipNote = ref(DEFAULT_DERIV_HINT)
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const adjudicatedPrior = ref<number | null>(null)
  const lastSyncHint = ref('')

  function persistRows() {
    if (isReadonly.value) return
    debouncedSave(ITEM_ROWS, {
      remark: serializeSoeRows(tradingRows.value, derivativeRows.value),
    })
  }

  function loadPersisted() {
    const parsed = parseSoePersisted(allResponses.value.get(ITEM_ROWS)?.remark)
    if (parsed) {
      tradingRows.value = parsed.trading
      derivativeRows.value = parsed.derivative
    }
    const fv = allResponses.value.get(ITEM_FV_BASIS)?.remark
    if (fv != null && fv !== '') fvBasisNote.value = fv
    const tip = allResponses.value.get(ITEM_DERIV_TIP)?.remark
    if (tip != null && tip !== '') derivativeTipNote.value = tip
    const note = allResponses.value.get(ITEM_NOTE)?.remark
    if (note != null) noteText.value = note
  }

  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    () => loadPersisted(),
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_FV_BASIS)?.remark,
    (v) => { if (v != null && v !== '' && !fvBasisNote.value) fvBasisNote.value = v },
  )
  watch(
    () => allResponses.value.get(ITEM_DERIV_TIP)?.remark,
    (v) => { if (v != null && v !== '' && !derivativeTipNote.value) derivativeTipNote.value = v },
  )
  watch(
    () => allResponses.value.get(ITEM_NOTE)?.remark,
    (v) => { if (v != null && !noteText.value) noteText.value = v },
  )

  const tradingDisplayRows = computed(() => {
    const total = tradingTotal(tradingRows.value)
    return [
      ...tradingRows.value,
      {
        rowKey: 'total',
        label: '合计',
        kind: 'total' as const,
        indent: 0,
        endAmount: total.endAmount,
        priorAmount: total.priorAmount,
        autoFilled: false,
        editable: false,
      },
    ]
  })

  const derivativeTotal = computed(() => ({
    endAmount: derivativeRows.value.reduce((s, r) => s + r.endAmount, 0),
    priorAmount: derivativeRows.value.reduce((s, r) => s + r.priorAmount, 0),
  }))

  function publishNoteText(extra?: Record<string, unknown>) {
    try {
      window.dispatchEvent(
        new CustomEvent('disclosure:note-text-updated', {
          detail: {
            wpCode: 'G1',
            accountCode: G1_ACCOUNT_CODE,
            type: 'soe',
            sectionIds: ['八、2', '八、3'],
            text: noteText.value,
            fvBasisNote: fvBasisNote.value,
            derivativeTipNote: derivativeTipNote.value,
            tradingTotal: tradingTotal(tradingRows.value),
            derivativeTotal: derivativeTotal.value,
            ...extra,
          },
        }),
      )
    } catch { /* silent */ }
  }

  function updateTradingAmount(rowKey: string, field: 'endAmount' | 'priorAmount', value: unknown) {
    if (isReadonly.value) return
    const defEditable = tradingRows.value.find((r) => r.rowKey === rowKey)?.editable
    if (!defEditable) return
    tradingRows.value = recomputeCategoryTotals(
      tradingRows.value.map((r) =>
        r.rowKey === rowKey
          ? { ...r, [field]: parseNum(value), autoFilled: false }
          : r,
      ),
    )
    persistRows()
    publishNoteText()
  }

  function addDerivativeRow() {
    if (isReadonly.value) return
    derivativeRows.value = [...derivativeRows.value, createEmptyDerivativeRow()]
    persistRows()
  }

  function removeDerivativeRow(rowId: string) {
    if (isReadonly.value) return
    derivativeRows.value = derivativeRows.value.filter((r) => r.rowId !== rowId)
    persistRows()
    publishNoteText()
  }

  function updateDerivativeField(
    rowId: string,
    field: 'label' | 'endAmount' | 'priorAmount' | 'reason',
    value: unknown,
  ) {
    if (isReadonly.value) return
    derivativeRows.value = derivativeRows.value.map((r) => {
      if (r.rowId !== rowId) return r
      if (field === 'endAmount' || field === 'priorAmount') {
        return { ...r, [field]: parseNum(value), autoFilled: false }
      }
      return { ...r, [field]: String(value ?? ''), autoFilled: false }
    })
    persistRows()
    publishNoteText()
  }

  watch(fvBasisNote, (val) => {
    if (isReadonly.value) return
    debouncedSave(ITEM_FV_BASIS, { remark: val })
    publishNoteText()
  })

  watch(derivativeTipNote, (val) => {
    if (isReadonly.value) return
    debouncedSave(ITEM_DERIV_TIP, { remark: val })
    publishNoteText()
  })

  watch(noteText, (val) => {
    if (isReadonly.value) return
    debouncedSave(ITEM_NOTE, { remark: val })
    publishNoteText()
  })

  /** 从 G1-1 审定表回填披露金额（覆盖未手工改写的自动格） */
  function refreshFromAdjudication(force = false) {
    const raw = allResponses.value.get(ITEM_ADJ_ROWS)?.remark
    const amounts = extractSoeAmountsFromAdjStore(raw)
    const nextTrading = buildDefaultTradingRows(amounts)
    if (!force) {
      // 保留用户手工改过的明细（autoFilled=false）
      const prevByKey = new Map(tradingRows.value.map((r) => [r.rowKey, r]))
      for (const row of nextTrading) {
        if (!row.editable) continue
        const prev = prevByKey.get(row.rowKey)
        if (prev && !prev.autoFilled && (prev.endAmount !== 0 || prev.priorAmount !== 0)) {
          row.endAmount = prev.endAmount
          row.priorAmount = prev.priorAmount
          row.autoFilled = false
        }
      }
      tradingRows.value = recomputeCategoryTotals(nextTrading)
    } else {
      tradingRows.value = nextTrading
    }

    const deriv = amounts.derivative
    adjudicatedAmount.value = tradingTotal(tradingRows.value).endAmount + (deriv?.endAmount ?? 0)
    adjudicatedPrior.value = tradingTotal(tradingRows.value).priorAmount + (deriv?.priorAmount ?? 0)

    // 衍生：若无明细行且审定有衍生余额，插入汇总行
    if (
      derivativeRows.value.length === 0
      && deriv
      && (deriv.endAmount !== 0 || deriv.priorAmount !== 0)
    ) {
      derivativeRows.value = [
        createEmptyDerivativeRow({
          label: '衍生金融资产（审定汇总）',
          endAmount: deriv.endAmount,
          priorAmount: deriv.priorAmount,
          autoFilled: true,
        }),
      ]
    } else if (force && deriv) {
      const autoIdx = derivativeRows.value.findIndex((r) => r.autoFilled)
      if (autoIdx >= 0) {
        const next = [...derivativeRows.value]
        next[autoIdx] = {
          ...next[autoIdx],
          endAmount: deriv.endAmount,
          priorAmount: deriv.priorAmount,
          autoFilled: true,
        }
        derivativeRows.value = next
      }
    }

    persistRows()
    lastSyncHint.value = new Date().toLocaleTimeString('zh-CN')
    publishNoteText({ source: 'adjudication' })
  }

  function onAdjudicated(e: Event) {
    const detail = (e as CustomEvent).detail
    if (detail?.accountCode !== G1_ACCOUNT_CODE && detail?.wpCode !== 'G1') return
    if (typeof detail.auditedAmount === 'number') {
      adjudicatedAmount.value = detail.auditedAmount
    }
    if (typeof detail.priorAudited === 'number') {
      adjudicatedPrior.value = detail.priorAudited
    }
    refreshFromAdjudication(false)
  }

  function getSyncSnapshot(): G1SoeSyncSnapshot {
    return {
      tradingRows: tradingRows.value.map((r) => ({ ...r })),
      derivativeRows: derivativeRows.value.map((r) => ({ ...r })),
      fvBasisNote: fvBasisNote.value,
      derivativeTipNote: derivativeTipNote.value,
      auditNote: noteText.value,
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', onAdjudicated)
    // 首次进入：若无持久化明细则尝试从审定表灌数
    const hasSaved = !!parseSoePersisted(allResponses.value.get(ITEM_ROWS)?.remark)
    if (!hasSaved) refreshFromAdjudication(true)
    else {
      const raw = allResponses.value.get(ITEM_ADJ_ROWS)?.remark
      const amounts = extractSoeAmountsFromAdjStore(raw)
      const t = tradingTotal(tradingRows.value)
      adjudicatedAmount.value = t.endAmount + (amounts.derivative?.endAmount ?? 0)
      adjudicatedPrior.value = t.priorAmount + (amounts.derivative?.priorAmount ?? 0)
    }
  })

  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', onAdjudicated)
  })

  return {
    tradingRows,
    tradingDisplayRows,
    derivativeRows,
    derivativeTotal,
    fvBasisNote,
    derivativeTipNote,
    noteText,
    adjudicatedAmount,
    adjudicatedPrior,
    lastSyncHint,
    updateTradingAmount,
    addDerivativeRow,
    removeDerivativeRow,
    updateDerivativeField,
    refreshFromAdjudication,
    getSyncSnapshot,
    persistRows,
  }
}

export default useG1DisclosureSoe
