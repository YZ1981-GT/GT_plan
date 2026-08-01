/**
 * useK1DisclosureListed — 其他应收款附注披露（上市公司）
 *
 * 对齐 Excel「附注披露信息（上市公司）」+ note_template_listed §五、8：
 * ① 按账龄  ② 按款项性质  ③ ECL 三阶段  ④ 坏账变动  ⑤ 转回/核销  ⑥ 前五名 …
 * - 账龄段枚举：THREE_YEAR / FIVE_YEAR / CUSTOM（useAgingConfig）
 * - 从 K1-1 / K1-2 / K1-3 / K1-9 自动取数
 * - sync-from-workpaper → 附注模块
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useAgingConfig } from '@/composables/useAgingConfig'
import {
  K1_DISC_NOTE_KEY,
  K1_DISC_STORAGE_KEY,
  autoFillFromK1Sources,
  calcAgingTieOut,
  calcMovementTieOut,
  calcNatureTieOut,
  calcPriorProvisionTieOut,
  calcSummaryTieOut,
  calcTop5ProportionCheck,
  calcWithinOneYearTieOut,
  emptyK1ListedPayload,
  parseK1ListedPayload,
  readAdjudicationTotals,
  readK1SummaryFigures,
  recomputeStageEclRows,
  serializeK1ListedPayload,
  stageBlocksProvisionTotal,
  summarizeContinuedInvolvement,
  summarizeNatureRows,
  type K1AgingDisclosureRow,
  type K1ContinuedInvolvementRow,
  type K1GovGrantRow,
  type K1ListedDisclosurePayloadV2,
  type K1NatureDisclosureRow,
  type K1ReversalDisclosureRow,
  type K1StageEclDisclosureRow,
  type K1Top5DisclosureRow,
  type K1TransferRow,
  type K1WriteoffDisclosureRow,
} from './k1DisclosureModel'
import { buildK1ListedSyncPayloads } from './k1DisclosureSyncPayload'
import {
  K1_ACCOUNT_CODE,
  K1_NOTE_SECTION,
  isK1DisclosureApplicable,
  resolveK1NoteSectionTarget,
} from './k1NoteSectionMap'
import type { K1StageMovementRow } from './useK1BadDebt'

function uid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function useK1DisclosureListed(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: unknown) => void
  applicableStandards?: Ref<readonly string[] | null | undefined> | (() => readonly string[] | null | undefined)
}) {
  const { wpId, projectId, allResponses, isReadonly, onSave } = opts
  const agingConfig = useAgingConfig(projectId, 'K1')
  const isSyncing = ref(false)
  const lastSyncHint = ref('')
  const noteText = ref('')

  const payload = ref<K1ListedDisclosurePayloadV2>(emptyK1ListedPayload())

  const noteTarget = computed(() => resolveK1NoteSectionTarget('listed'))
  const isApplicable = computed(() =>
    isK1DisclosureApplicable('listed', _standards()),
  )
  const adjudication = computed(() => readAdjudicationTotals(allResponses.value))

  const agingRows = computed(() => payload.value.agingRows)
  const natureRows = computed(() => payload.value.natureRows)
  const natureTotal = computed(() => summarizeNatureRows(payload.value.natureRows))
  const stage1Rows = computed(() => payload.value.stage1Rows)
  const stage2Rows = computed(() => payload.value.stage2Rows)
  const stage3Rows = computed(() => payload.value.stage3Rows)
  const priorStage1Rows = computed(() => payload.value.priorStage1Rows)
  const priorStage2Rows = computed(() => payload.value.priorStage2Rows)
  const priorStage3Rows = computed(() => payload.value.priorStage3Rows)
  const stageMovements = computed(() => payload.value.stageMovements)
  const top5Rows = computed(() => payload.value.top5Rows)
  const reversalRows = computed(() => payload.value.reversalRows)
  // ⑧⑨⑩ 三块（源模板 A136-A159）—— 2026-07-31 起也进 §五、8，需暴露给自动同步 watch
  const govGrantRows = computed(() => payload.value.govGrantRows)
  const transferRows = computed(() => payload.value.transferRows)
  const continuedInvolvementRows = computed(() => payload.value.continuedInvolvementRows)
  const continuedInvolvementTotals = computed(() =>
    summarizeContinuedInvolvement(payload.value.continuedInvolvementRows),
  )

  const agingTieOut = computed(() =>
    calcAgingTieOut(payload.value.agingRows, adjudication.value.receivableEnd),
  )
  const natureTieOut = computed(() =>
    calcNatureTieOut(payload.value.natureRows, adjudication.value.receivableEnd),
  )
  /** T3：1 年以内月度细分合计 = 1 年以内 */
  const withinOneYearTieOut = computed(() => calcWithinOneYearTieOut(payload.value.agingRows))
  /** F8-48：汇总表三明细行之和 = 合计行 */
  const summaryFigures = computed(() => readK1SummaryFigures(allResponses.value))
  const summaryTieOut = computed(() => calcSummaryTieOut(summaryFigures.value))

  /** 期末三阶段坏账合计（③ 三张表 total 行之和） */
  const endStageProvisionTotal = computed(() =>
    stageBlocksProvisionTotal(
      payload.value.stage1Rows,
      payload.value.stage2NoneEnd ? [] : payload.value.stage2Rows,
      payload.value.stage3Rows,
    ),
  )
  /** 上年年末三阶段坏账合计 */
  const priorStageProvisionTotal = computed(() =>
    stageBlocksProvisionTotal(
      payload.value.priorStage1Rows,
      payload.value.stage2NonePrior ? [] : payload.value.priorStage2Rows,
      payload.value.priorStage3Rows,
    ),
  )

  /** T4：账龄表「减：坏账准备」期末 = 期末三阶段坏账合计 */
  const provisionTieOut = computed(() => {
    const agingProv = payload.value.agingRows.find((r) => r.kind === 'provision')?.endAmount ?? 0
    const diff = Math.round((agingProv - endStageProvisionTotal.value) * 100) / 100
    return {
      agingProvision: agingProv,
      stageClosing: endStageProvisionTotal.value,
      diff,
      matched: Math.abs(diff) < 0.01,
    }
  })
  /** T4prior：账龄表「减：坏账准备」上年年末 = 上年年末三阶段坏账合计 */
  const priorProvisionTieOut = computed(() =>
    calcPriorProvisionTieOut(payload.value.agingRows, priorStageProvisionTotal.value),
  )
  /** T5/T6/T7：④ 变动表 ↔ ③ 三阶段快照 ↔ ⑤ 核销汇总 */
  const movementTieOut = computed(() =>
    calcMovementTieOut(
      payload.value.stageMovements,
      endStageProvisionTotal.value,
      priorStageProvisionTotal.value,
      payload.value.writeoffSummaryAmount,
    ),
  )
  /** T12：前五名占比合计 ≤ 100% */
  const top5Check = computed(() => calcTop5ProportionCheck(payload.value.top5Rows))

  function _standards(): readonly string[] | null | undefined {
    const s = opts.applicableStandards
    if (!s) return undefined
    return typeof s === 'function' ? s() : s.value
  }

  function persistPayload(): void {
    if (isReadonly.value) return
    onSave?.(K1_DISC_STORAGE_KEY, serializeK1ListedPayload(payload.value))
  }

  function persistNote(): void {
    if (isReadonly.value) return
    onSave?.(K1_DISC_NOTE_KEY, noteText.value)
    try {
      window.dispatchEvent(
        new CustomEvent('disclosure:note-text-updated', {
          detail: {
            wpCode: 'K1',
            accountCode: K1_ACCOUNT_CODE,
            section: 'listed',
            projectId: projectId.value,
            sectionIds: [K1_NOTE_SECTION.listed],
            text: noteText.value,
          },
        }),
      )
    } catch {
      /* silent */
    }
  }

  function loadPersisted(): void {
    const raw = allResponses.value.get(K1_DISC_STORAGE_KEY)?.remark
      ?? allResponses.value.get(K1_DISC_STORAGE_KEY)?.value
    payload.value = parseK1ListedPayload(raw, agingConfig.segments.value)
    const note = allResponses.value.get(K1_DISC_NOTE_KEY)?.remark
    if (note != null) noteText.value = String(note)
  }

  watch(
    () => allResponses.value.get(K1_DISC_STORAGE_KEY)?.remark,
    () => loadPersisted(),
    { immediate: true },
  )

  watch(
    () => agingConfig.segments.value,
    (segs) => {
      if (!segs.length) return
      if (!payload.value.agingRows.length) {
        payload.value = parseK1ListedPayload(
          serializeK1ListedPayload(payload.value),
          segs,
        )
      }
    },
  )

  function refreshFromSources(force = false): void {
    if (isReadonly.value && !force) return
    payload.value = autoFillFromK1Sources(
      { ...payload.value },
      allResponses.value,
      agingConfig.segments.value,
      { force },
    )
    lastSyncHint.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    persistPayload()
    ElMessage.success(force ? '已强制从源底稿覆盖取数' : '已从 K1-1/K1-2/K1-3/K1-9 同步取数')
  }

  function updateAgingRow(rowId: string, field: 'endAmount' | 'priorAmount', value: number): void {
    if (isReadonly.value) return
    payload.value.agingRows = payload.value.agingRows.map((r) => {
      if (r.rowId !== rowId || !r.editable) return r
      return { ...r, [field]: value, autoFilled: false }
    })
    recalcAgingDerived()
    persistPayload()
  }

  /** 1 年以内月度细分行标签可改（源模板「其中：0-X个月」的 X/Y 由项目自定） */
  function updateAgingRowLabel(rowId: string, label: string): void {
    if (isReadonly.value) return
    payload.value.agingRows = payload.value.agingRows.map((r) =>
      r.rowId === rowId && r.labelEditable ? { ...r, label } : r,
    )
    persistPayload()
  }

  function recalcAgingDerived(): void {
    const rows = payload.value.agingRows
    const dataRows = rows.filter((r) => r.kind === 'data')
    const subtotalEnd = dataRows.reduce((s, r) => s + r.endAmount, 0)
    const subtotalPrior = dataRows.reduce((s, r) => s + r.priorAmount, 0)
    const prov = rows.find((r) => r.kind === 'provision')
    const provEnd = prov?.endAmount ?? 0
    const provPrior = prov?.priorAmount ?? 0
    const within1 = rows.find((r) => r.kind === 'data' && r.segmentKey === 'within1')
    payload.value.agingRows = rows.map((r) => {
      if (r.kind === 'subtotal') return { ...r, endAmount: subtotalEnd, priorAmount: subtotalPrior }
      // 「1年以内小计：」始终跟随「1年以内」行（源模板 R12 = R8）
      if (r.kind === 'subtotal1y') {
        return { ...r, endAmount: within1?.endAmount ?? 0, priorAmount: within1?.priorAmount ?? 0 }
      }
      if (r.kind === 'total') {
        return {
          ...r,
          endAmount: subtotalEnd - provEnd,
          priorAmount: subtotalPrior - provPrior,
        }
      }
      return r
    })
  }

  function updateNatureRow(
    rowId: string,
    field: keyof Pick<K1NatureDisclosureRow, 'label' | 'endGross' | 'endProvision' | 'priorGross' | 'priorProvision'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.natureRows = payload.value.natureRows.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, [field]: value, autoFilled: false }
      next.endBookValue = next.endGross - next.endProvision
      next.priorBookValue = next.priorGross - next.priorProvision
      return next
    })
    persistPayload()
  }

  function addNatureRow(label = ''): void {
    if (isReadonly.value) return
    payload.value.natureRows.push({
      rowId: uid('nature'),
      label,
      endGross: 0,
      endProvision: 0,
      endBookValue: 0,
      priorGross: 0,
      priorProvision: 0,
      priorBookValue: 0,
      editable: true,
    })
    persistPayload()
  }

  function removeNatureRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.natureRows = payload.value.natureRows.filter((r) => r.rowId !== rowId)
    persistPayload()
  }

  type StageBlockKey =
    | 'stage1Rows' | 'stage2Rows' | 'stage3Rows'
    | 'priorStage1Rows' | 'priorStage2Rows' | 'priorStage3Rows'

  function stageBlockKey(stage: 1 | 2 | 3, period: 'end' | 'prior'): StageBlockKey {
    const suffix = stage === 1 ? '1Rows' : stage === 2 ? '2Rows' : '3Rows'
    return (period === 'end' ? `stage${suffix}` : `priorStage${suffix}`) as StageBlockKey
  }

  function updateStageRow(
    stage: 1 | 2 | 3,
    rowId: string,
    field: keyof Pick<K1StageEclDisclosureRow, 'balance' | 'eclRate' | 'provision' | 'reason' | 'label'>,
    value: string | number | null,
    period: 'end' | 'prior' = 'end',
  ): void {
    if (isReadonly.value) return
    const key = stageBlockKey(stage, period)
    payload.value[key] = recomputeStageEclRows(
      payload.value[key].map((r) =>
        r.rowId === rowId && r.editable ? { ...r, [field]: value ?? 0, autoFilled: false } : r,
      ),
    )
    persistPayload()
  }

  /** 【或】不存在处于第二阶段（源模板 R49 / R80） */
  function toggleStage2None(period: 'end' | 'prior', value: boolean): void {
    if (isReadonly.value) return
    if (period === 'end') payload.value.stage2NoneEnd = value
    else payload.value.stage2NonePrior = value
    persistPayload()
  }

  function updateTop5Row(
    rowId: string,
    field: keyof Pick<K1Top5DisclosureRow, 'unitName' | 'nature' | 'endBalance' | 'aging' | 'provision'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.top5Rows = payload.value.top5Rows.map((r) =>
      r.rowId === rowId ? { ...r, [field]: value, autoFilled: false } : r,
    )
    recalcTop5Proportions()
    persistPayload()
  }

  function recalcTop5Proportions(): void {
    const total = payload.value.top5Rows.reduce((s, r) => s + r.endBalance, 0) || 1
    payload.value.top5Rows = payload.value.top5Rows.map((r) => ({
      ...r,
      proportionPct: Math.round((r.endBalance / total) * 10000) / 100,
    }))
  }

  function addTop5Row(): void {
    if (isReadonly.value) return
    payload.value.top5Rows.push({
      rowId: uid('top5'),
      unitName: '',
      nature: '',
      endBalance: 0,
      aging: '',
      proportionPct: 0,
      provision: 0,
    })
    persistPayload()
  }

  function updateReversalRow(
    rowId: string,
    field: keyof Pick<K1ReversalDisclosureRow, 'unitName' | 'reason' | 'method' | 'basis' | 'amount'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.reversalRows = payload.value.reversalRows.map((r) =>
      r.rowId === rowId ? { ...r, [field]: value } : r,
    )
    persistPayload()
  }

  function addReversalRow(): void {
    if (isReadonly.value) return
    payload.value.reversalRows.push({
      rowId: uid('rev'),
      unitName: '',
      reason: '',
      method: '',
      basis: '',
      amount: 0,
    })
    persistPayload()
  }

  function updateWriteoffRow(
    rowId: string,
    field: keyof Pick<K1WriteoffDisclosureRow, 'unitName' | 'nature' | 'amount' | 'reason' | 'procedure' | 'relatedParty'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.writeoffDetailRows = payload.value.writeoffDetailRows.map((r) =>
      r.rowId === rowId ? { ...r, [field]: value } : r,
    )
    payload.value.writeoffSummaryAmount = payload.value.writeoffDetailRows.reduce((s, r) => s + r.amount, 0)
    persistPayload()
  }

  function addWriteoffRow(): void {
    if (isReadonly.value) return
    payload.value.writeoffDetailRows.push({
      rowId: uid('wof'),
      unitName: '',
      nature: '',
      amount: 0,
      reason: '',
      procedure: '',
      relatedParty: '',
    })
    persistPayload()
  }

  function updateGovGrantRow(
    rowId: string,
    field: keyof Pick<K1GovGrantRow, 'unitName' | 'projectName' | 'endBalance' | 'aging' | 'expectedCollection'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.govGrantRows = payload.value.govGrantRows.map((r) =>
      r.rowId === rowId ? { ...r, [field]: value } : r,
    )
    persistPayload()
  }

  function addGovGrantRow(): void {
    if (isReadonly.value) return
    payload.value.govGrantRows.push({
      rowId: uid('gov'),
      unitName: '',
      projectName: '',
      endBalance: 0,
      aging: '',
      expectedCollection: '',
    })
    persistPayload()
  }

  function updateTransferRow(
    rowId: string,
    field: keyof Pick<K1TransferRow, 'item' | 'method' | 'derecognizedAmount' | 'gainLoss'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.transferRows = payload.value.transferRows.map((r) =>
      r.rowId === rowId ? { ...r, [field]: value } : r,
    )
    persistPayload()
  }

  function addTransferRow(): void {
    if (isReadonly.value) return
    payload.value.transferRows.push({
      rowId: uid('tr'),
      item: '',
      method: '',
      derecognizedAmount: 0,
      gainLoss: 0,
    })
    persistPayload()
  }

  function updateFundCentralization(field: 'amount' | 'note', value: number | string): void {
    if (isReadonly.value) return
    if (field === 'amount') payload.value.fundCentralizationAmount = Number(value) || 0
    else payload.value.fundCentralizationNote = String(value)
    persistPayload()
  }

  function removeTransferRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.transferRows = payload.value.transferRows.filter((r) => r.rowId !== rowId)
    persistPayload()
  }

  function removeGovGrantRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.govGrantRows = payload.value.govGrantRows.filter((r) => r.rowId !== rowId)
    persistPayload()
  }

  function addContinuedInvolvementRow(side: 'asset' | 'liability'): void {
    if (isReadonly.value) return
    payload.value.continuedInvolvementRows.push({
      rowId: uid('ci'),
      side,
      item: '',
      amount: 0,
    })
    persistPayload()
  }

  function updateContinuedInvolvementRow(
    rowId: string,
    field: keyof Pick<K1ContinuedInvolvementRow, 'item' | 'amount'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.continuedInvolvementRows = payload.value.continuedInvolvementRows.map((r) =>
      r.rowId === rowId ? { ...r, [field]: value } : r,
    )
    persistPayload()
  }

  function removeContinuedInvolvementRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.continuedInvolvementRows = payload.value.continuedInvolvementRows.filter(
      (r) => r.rowId !== rowId,
    )
    persistPayload()
  }

  function updateNoteSection(key: string, text: string): void {
    payload.value.notes = { ...payload.value.notes, [key]: text }
    persistPayload()
  }

  function noteSection(key: string): string {
    return payload.value.notes?.[key] ?? ''
  }

  function getSyncSnapshot(): K1ListedDisclosurePayloadV2 {
    return JSON.parse(serializeK1ListedPayload(payload.value))
  }

  async function syncToNotes(): Promise<void> {
    if (isSyncing.value || !projectId.value || isReadonly.value) return
    const payloads = buildK1ListedSyncPayloads(
      wpId.value,
      _standards(),
      getSyncSnapshot(),
      noteText.value,
      readK1SummaryFigures(allResponses.value),
    )
    if (!payloads.length) {
      ElMessage.warning('当前项目准则不适用上市附注同步')
      return
    }
    isSyncing.value = true
    try {
      let rows = 0
      for (const p of payloads) {
        const result: any = await api.post(
          `/api/projects/${projectId.value}/disclosure-notes/sync-from-workpaper`,
          p,
        )
        const data = result?.data ?? result
        rows += Number(data?.rows_synced ?? 0)
      }
      ElMessage.success(`已同步 ${rows} 行到附注模块「${noteTarget.value.sectionId} 其他应收款」`)
    } catch {
      ElMessage.warning('同步附注失败，请稍后重试')
    } finally {
      isSyncing.value = false
    }
  }

  function handleAdjudicated(e: Event): void {
    const d = (e as CustomEvent<{ accountCode?: string; wpCode?: string }>).detail
    if (d?.accountCode !== K1_ACCOUNT_CODE && d?.wpCode !== 'K1') return
    refreshFromSources(false)
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
    const hasData = !!allResponses.value.get(K1_DISC_STORAGE_KEY)?.remark
    if (!hasData) refreshFromSources(true)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  })

  return {
    agingConfig,
    noteTarget,
    isApplicable,
    isSyncing,
    lastSyncHint,
    noteText,
    persistNote,
    adjudication,
    agingRows,
    natureRows,
    natureTotal,
    stage1Rows,
    stage2Rows,
    stage3Rows,
    priorStage1Rows,
    priorStage2Rows,
    priorStage3Rows,
    stageMovements,
    top5Rows,
    reversalRows,
    govGrantRows,
    transferRows,
    continuedInvolvementRows,
    continuedInvolvementTotals,
    agingTieOut,
    natureTieOut,
    withinOneYearTieOut,
    summaryFigures,
    summaryTieOut,
    provisionTieOut,
    priorProvisionTieOut,
    movementTieOut,
    top5Check,
    endStageProvisionTotal,
    priorStageProvisionTotal,
    refreshFromSources,
    updateAgingRow,
    updateAgingRowLabel,
    updateNatureRow,
    addNatureRow,
    removeNatureRow,
    updateStageRow,
    toggleStage2None,
    updateTop5Row,
    addTop5Row,
    updateReversalRow,
    addReversalRow,
    updateWriteoffRow,
    addWriteoffRow,
    updateGovGrantRow,
    addGovGrantRow,
    removeGovGrantRow,
    updateTransferRow,
    addTransferRow,
    removeTransferRow,
    updateFundCentralization,
    addContinuedInvolvementRow,
    updateContinuedInvolvementRow,
    removeContinuedInvolvementRow,
    updateNoteSection,
    noteSection,
    getSyncSnapshot,
    syncToNotes,
    payload,
  }
}

export type { K1AgingDisclosureRow, K1StageMovementRow }
