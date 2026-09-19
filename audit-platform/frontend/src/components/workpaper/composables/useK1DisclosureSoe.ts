/**
 * useK1DisclosureSoe — 其他应收款附注披露（国有企业）
 *
 * 对齐 Excel「附注披露信息（国企）」+ note_template_soe §八、9：
 * 账龄 / 计提方法 / 单项明细 / 组合账龄 / ECL三阶段 / 转回核销 / 前五名 / 政府补助 / 转移
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useAgingConfig } from '@/composables/useAgingConfig'
import {
  K1_SOE_DISC_NOTE_KEY,
  K1_SOE_DISC_STORAGE_KEY,
  autoFillSoeFromK1Sources,
  calcAgingTieOut,
  calcIndividualSplitTieOut,
  calcMethodTieOut,
  calcBalanceStageTieOut,
  calcPortfolioSplitTieOut,
  calcTop5ProportionCheck,
  emptyK1SoePayload,
  parseK1SoePayload,
  recomputeMethodRows,
  recomputeOtherPortfolioRows,
  serializeK1SoePayload,
  summarizeContinuedInvolvement,
  type K1ContinuedInvolvementRow,
  type K1GovGrantRow,
  type K1IndividualDetailRow,
  type K1MethodDisclosureRow,
  type K1OtherPortfolioRow,
  type K1PortfolioAgingRow,
  type K1ReversalDisclosureRow,
  type K1SoeDisclosurePayloadV2,
  type K1Top5DisclosureRow,
  type K1TransferRow,
  type K1WriteoffDisclosureRow,
  calcSummaryTieOut,
  readAdjudicationTotals,
  readK1SummaryFigures,
} from './k1DisclosureModel'
import { buildK1SoeSyncPayloads } from './k1DisclosureSyncPayload'
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

export function useK1DisclosureSoe(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  onSave?: (itemId: string, value: unknown) => void
  applicableStandards?: Ref<readonly string[] | null | undefined>
}) {
  const { wpId, projectId, allResponses, isReadonly, onSave } = opts
  const agingConfig = useAgingConfig(projectId, 'K1')
  const isSyncing = ref(false)
  const lastSyncHint = ref('')
  const noteText = ref('')

  const payload = ref<K1SoeDisclosurePayloadV2>(emptyK1SoePayload())

  const noteTarget = computed(() => resolveK1NoteSectionTarget('soe'))
  const isApplicable = computed(() => isK1DisclosureApplicable('soe', _standards()))
  const adjudication = computed(() => readAdjudicationTotals(allResponses.value))

  const agingRows = computed(() => payload.value.agingRows)
  const methodRows = computed(() => payload.value.methodRows)
  const individualDetailRows = computed(() => payload.value.individualDetailRows)
  const portfolioAgingRows = computed(() => payload.value.portfolioAgingRows)
  const otherPortfolioRows = computed(() => payload.value.otherPortfolioRows)
  const continuedInvolvementRows = computed(() => payload.value.continuedInvolvementRows)
  const continuedInvolvementTotals = computed(() =>
    summarizeContinuedInvolvement(payload.value.continuedInvolvementRows),
  )
  const stageMovements = computed(() => payload.value.stageMovements)
  const balanceStageMovements = computed(() => payload.value.balanceStageMovements)
  const top5Rows = computed(() => payload.value.top5Rows)
  const reversalRows = computed(() => payload.value.reversalRows)
  const writeoffDetailRows = computed(() => payload.value.writeoffDetailRows)
  const govGrantRows = computed(() => payload.value.govGrantRows)
  const transferRows = computed(() => payload.value.transferRows)

  const agingTieOut = computed(() =>
    calcAgingTieOut(payload.value.agingRows, adjudication.value.receivableEnd),
  )
  const methodTieOut = computed(() =>
    calcMethodTieOut(payload.value.methodRows, adjudication.value.receivableEnd),
  )
  const balanceStageTieOut = computed(() =>
    calcBalanceStageTieOut(payload.value.balanceStageMovements, adjudication.value.receivableEnd),
  )
  /** F8-48：汇总表三明细行之和 = 合计行 */
  const summaryFigures = computed(() => readK1SummaryFigures(allResponses.value))
  const summaryTieOut = computed(() => calcSummaryTieOut(summaryFigures.value))

  const eclClosingTotal = computed(() => {
    const closing = payload.value.stageMovements.find((r) => r.key === 'closing')
    if (!closing) return 0
    return (closing.stage1 || 0) + (closing.stage2 || 0) + (closing.stage3 || 0)
  })

  const provisionTieOut = computed(() => {
    const agingProv = payload.value.agingRows.find((r) => r.kind === 'provision')?.endAmount ?? 0
    const diff = Math.round((agingProv - eclClosingTotal.value) * 100) / 100
    return { agingProvision: agingProv, eclClosing: eclClosingTotal.value, diff, matched: Math.abs(diff) < 0.01 }
  })

  /** T9：单项明细合计 = 方法表「单项计提」行 */
  const individualTieOut = computed(() =>
    calcIndividualSplitTieOut(payload.value.individualDetailRows, payload.value.methodRows),
  )
  /** T10：账龄组合坏账 + 其他组合坏账 = 方法表「组合计提」行坏账 */
  const portfolioSplitTieOut = computed(() =>
    calcPortfolioSplitTieOut(
      payload.value.portfolioAgingRows,
      payload.value.otherPortfolioRows,
      payload.value.methodRows,
    ),
  )
  /** T12：前五名占比合计 ≤ 100% */
  const top5Check = computed(() => calcTop5ProportionCheck(payload.value.top5Rows))

  function _standards(): readonly string[] | null | undefined {
    return opts.applicableStandards?.value
  }

  function persistPayload(): void {
    if (isReadonly.value) return
    onSave?.(K1_SOE_DISC_STORAGE_KEY, serializeK1SoePayload(payload.value))
  }

  function persistNote(): void {
    if (isReadonly.value) return
    onSave?.(K1_SOE_DISC_NOTE_KEY, noteText.value)
    try {
      window.dispatchEvent(
        new CustomEvent('disclosure:note-text-updated', {
          detail: {
            wpCode: 'K1',
            accountCode: K1_ACCOUNT_CODE,
            section: 'soe',
            projectId: projectId.value,
            sectionIds: [K1_NOTE_SECTION.soe],
            text: noteText.value,
          },
        }),
      )
    } catch { /* silent */ }
  }

  function loadPersisted(): void {
    const raw = allResponses.value.get(K1_SOE_DISC_STORAGE_KEY)?.remark
      ?? allResponses.value.get(K1_SOE_DISC_STORAGE_KEY)?.value
    payload.value = parseK1SoePayload(raw, agingConfig.segments.value, allResponses.value)
    const note = allResponses.value.get(K1_SOE_DISC_NOTE_KEY)?.remark
    if (note != null) noteText.value = String(note)
  }

  watch(
    () => allResponses.value.get(K1_SOE_DISC_STORAGE_KEY)?.remark,
    () => loadPersisted(),
    { immediate: true },
  )

  function refreshFromSources(force = false): void {
    if (isReadonly.value && !force) return
    payload.value = autoFillSoeFromK1Sources(
      { ...payload.value },
      allResponses.value,
      agingConfig.segments.value,
      { force },
    )
    lastSyncHint.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    persistPayload()
    ElMessage.success(force ? '已强制从源底稿覆盖取数' : '已从 K1-1/K1-2/K1-3/K1-7/K1-9 同步取数')
  }

  function recalcAgingDerived(): void {
    const dataRows = payload.value.agingRows.filter((r) => r.kind === 'data')
    const subtotalEnd = dataRows.reduce((s, r) => s + r.endAmount, 0)
    const subtotalPrior = dataRows.reduce((s, r) => s + r.priorAmount, 0)
    const prov = payload.value.agingRows.find((r) => r.kind === 'provision')
    const provEnd = prov?.endAmount ?? 0
    const provPrior = prov?.priorAmount ?? 0
    payload.value.agingRows = payload.value.agingRows.map((r) => {
      if (r.kind === 'subtotal') return { ...r, endAmount: subtotalEnd, priorAmount: subtotalPrior }
      if (r.kind === 'total') {
        return { ...r, endAmount: subtotalEnd - provEnd, priorAmount: subtotalPrior - provPrior }
      }
      return r
    })
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

  function updateMethodRow(
    rowKey: K1MethodDisclosureRow['rowKey'],
    field: keyof Pick<K1MethodDisclosureRow, 'endBalance' | 'endProvision' | 'priorBalance' | 'priorProvision'>,
    value: number,
  ): void {
    if (isReadonly.value) return
    payload.value.methodRows = recomputeMethodRows(
      payload.value.methodRows.map((r) =>
        r.rowKey === rowKey && r.editable ? { ...r, [field]: value, autoFilled: false } : r,
      ),
    )
    persistPayload()
  }

  function updateIndividualRow(
    rowId: string,
    field: keyof Pick<K1IndividualDetailRow, 'debtorName' | 'balance' | 'provision' | 'reason'>,
    value: string | number,
  ): void {
    if (isReadonly.value) return
    payload.value.individualDetailRows = payload.value.individualDetailRows.map((r) => {
      if (r.rowId !== rowId) return r
      const next = { ...r, [field]: value, autoFilled: false }
      next.eclRate = next.balance > 0 ? Math.round((next.provision / next.balance) * 10000) / 100 : null
      return next
    })
    persistPayload()
  }

  function updatePortfolioRow(
    rowId: string,
    field: keyof Pick<K1PortfolioAgingRow, 'endBalance' | 'endProvision' | 'priorBalance' | 'priorProvision'>,
    value: number,
  ): void {
    if (isReadonly.value) return
    payload.value.portfolioAgingRows = payload.value.portfolioAgingRows.map((r) =>
      r.rowId === rowId && r.editable ? { ...r, [field]: value, autoFilled: false } : r,
    )
    persistPayload()
  }

  // ─── 其他组合（源模板 R56-R61 / 附注「采用余额百分比法或其他组合方法…」）────
  function addOtherPortfolioRow(label: string): void {
    if (isReadonly.value) return
    payload.value.otherPortfolioRows.push({
      rowId: uid('oport'),
      label,
      endBalance: 0,
      endRatePct: null,
      endProvision: 0,
      priorBalance: 0,
      priorRatePct: null,
      priorProvision: 0,
      editable: true,
    })
    persistPayload()
  }

  function updateOtherPortfolioRow(
    rowId: string,
    field: keyof Pick<K1OtherPortfolioRow,
      'label' | 'endBalance' | 'endRatePct' | 'endProvision' | 'priorBalance' | 'priorRatePct' | 'priorProvision'>,
    value: string | number | null,
  ): void {
    if (isReadonly.value) return
    payload.value.otherPortfolioRows = recomputeOtherPortfolioRows(
      payload.value.otherPortfolioRows.map((r) =>
        r.rowId === rowId ? { ...r, [field]: value } : r,
      ),
    )
    persistPayload()
  }

  function removeOtherPortfolioRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.otherPortfolioRows = payload.value.otherPortfolioRows.filter((r) => r.rowId !== rowId)
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

  /** 占比分母：其他应收款项账面余额合计（账龄小计），无值时退回前五名合计 */
  function recalcTop5Proportions(): void {
    const subtotal = payload.value.agingRows.find((r) => r.kind === 'subtotal')?.endAmount ?? 0
    const fallback = payload.value.top5Rows.reduce((s, r) => s + (r.endBalance || 0), 0)
    const base = subtotal || fallback || 1
    payload.value.top5Rows = payload.value.top5Rows.map((r) => ({
      ...r,
      proportionPct: Math.round((r.endBalance / base) * 10000) / 100,
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

  function removeTop5Row(rowId: string): void {
    if (isReadonly.value) return
    payload.value.top5Rows = payload.value.top5Rows.filter((r) => r.rowId !== rowId)
    recalcTop5Proportions()
    persistPayload()
  }

  function updateReversalRow(
    rowId: string,
    field: keyof Pick<K1ReversalDisclosureRow,
      'unitName' | 'reason' | 'method' | 'basis' | 'amount' | 'cumulativeProvision'>,
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
      cumulativeProvision: 0,
    })
    persistPayload()
  }

  function removeReversalRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.reversalRows = payload.value.reversalRows.filter((r) => r.rowId !== rowId)
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

  function removeWriteoffRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.writeoffDetailRows = payload.value.writeoffDetailRows.filter((r) => r.rowId !== rowId)
    payload.value.writeoffSummaryAmount = payload.value.writeoffDetailRows.reduce((s, r) => s + r.amount, 0)
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

  function removeGovGrantRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.govGrantRows = payload.value.govGrantRows.filter((r) => r.rowId !== rowId)
    persistPayload()
  }

  /** 国企源模板 R111 转移表列为「债务人名称 | 终止确认金额 | 利得或损失」，无「转移方式」列 */
  function updateTransferRow(
    rowId: string,
    field: keyof Pick<K1TransferRow, 'item' | 'derecognizedAmount' | 'gainLoss'>,
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

  function removeTransferRow(rowId: string): void {
    if (isReadonly.value) return
    payload.value.transferRows = payload.value.transferRows.filter((r) => r.rowId !== rowId)
    persistPayload()
  }

  // ─── 继续涉入（源模板 R117-R123：资产：/资产小计/负债：/负债小计）──────────
  function addContinuedInvolvementRow(side: 'asset' | 'liability'): void {
    if (isReadonly.value) return
    payload.value.continuedInvolvementRows.push({ rowId: uid('ci'), side, item: '', amount: 0 })
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

  function getSyncSnapshot(): K1SoeDisclosurePayloadV2 {
    return JSON.parse(serializeK1SoePayload(payload.value))
  }

  async function syncToNotes(): Promise<void> {
    if (isSyncing.value || !projectId.value || isReadonly.value) return
    const payloads = buildK1SoeSyncPayloads(
      wpId.value,
      _standards(),
      getSyncSnapshot(),
      noteText.value,
      readK1SummaryFigures(allResponses.value),
    )
    if (!payloads.length) {
      ElMessage.warning('当前项目准则不适用国企附注同步')
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
    const hasData = !!allResponses.value.get(K1_SOE_DISC_STORAGE_KEY)?.remark
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
    methodRows,
    individualDetailRows,
    portfolioAgingRows,
    otherPortfolioRows,
    continuedInvolvementRows,
    continuedInvolvementTotals,
    stageMovements,
    balanceStageMovements,
    top5Rows,
    reversalRows,
    writeoffDetailRows,
    govGrantRows,
    transferRows,
    agingTieOut,
    methodTieOut,
    balanceStageTieOut,
    summaryFigures,
    summaryTieOut,
    provisionTieOut,
    individualTieOut,
    portfolioSplitTieOut,
    top5Check,
    refreshFromSources,
    updateAgingRow,
    updateMethodRow,
    updateIndividualRow,
    updatePortfolioRow,
    addOtherPortfolioRow,
    updateOtherPortfolioRow,
    removeOtherPortfolioRow,
    updateTop5Row,
    addTop5Row,
    removeTop5Row,
    updateReversalRow,
    addReversalRow,
    removeReversalRow,
    updateWriteoffRow,
    addWriteoffRow,
    removeWriteoffRow,
    updateGovGrantRow,
    addGovGrantRow,
    removeGovGrantRow,
    updateTransferRow,
    addTransferRow,
    removeTransferRow,
    addContinuedInvolvementRow,
    updateContinuedInvolvementRow,
    removeContinuedInvolvementRow,
    updateNoteSection,
    noteSection,
    syncToNotes,
    payload,
  }
}

export type { K1StageMovementRow }
