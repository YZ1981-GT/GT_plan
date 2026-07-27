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
  calcNatureTieOut,
  emptyK1ListedPayload,
  parseK1ListedPayload,
  readAdjudicationTotals,
  recomputeStageEclRows,
  serializeK1ListedPayload,
  summarizeNatureRows,
  type K1AgingDisclosureRow,
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
  const stageMovements = computed(() => payload.value.stageMovements)
  const top5Rows = computed(() => payload.value.top5Rows)
  const reversalRows = computed(() => payload.value.reversalRows)

  const agingTieOut = computed(() =>
    calcAgingTieOut(payload.value.agingRows, adjudication.value.receivableEnd),
  )
  const natureTieOut = computed(() =>
    calcNatureTieOut(payload.value.natureRows, adjudication.value.receivableEnd),
  )

  const stage1Closing = computed(() =>
    payload.value.stage1Rows.find((r) => r.rowKey === 'total')?.provision ?? 0,
  )
  const provisionTieOut = computed(() => {
    const agingProv = payload.value.agingRows.find((r) => r.kind === 'provision')?.endAmount ?? 0
    const diff = Math.round((agingProv - stage1Closing.value) * 100) / 100
    return { agingProvision: agingProv, stageClosing: stage1Closing.value, diff, matched: Math.abs(diff) < 0.01 }
  })

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

  function updateStageRow(
    stage: 1 | 2 | 3,
    rowId: string,
    field: keyof Pick<K1StageEclDisclosureRow, 'balance' | 'eclRate' | 'provision' | 'reason' | 'label'>,
    value: string | number | null,
  ): void {
    if (isReadonly.value) return
    const key = stage === 1 ? 'stage1Rows' : stage === 2 ? 'stage2Rows' : 'stage3Rows'
    payload.value[key] = recomputeStageEclRows(
      payload.value[key].map((r) =>
        r.rowId === rowId && r.editable ? { ...r, [field]: value ?? 0, autoFilled: false } : r,
      ),
    )
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

  function updateContinuedInvolvement(field: 'assets' | 'liabilities', value: number): void {
    if (isReadonly.value) return
    if (field === 'assets') payload.value.continuedInvolvementAssets = value
    else payload.value.continuedInvolvementLiabilities = value
    persistPayload()
  }

  function updateNoteSection(key: string, text: string): void {
    payload.value.notes = { ...payload.value.notes, [key]: text }
    persistPayload()
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
    stageMovements,
    top5Rows,
    reversalRows,
    agingTieOut,
    natureTieOut,
    provisionTieOut,
    refreshFromSources,
    updateAgingRow,
    updateNatureRow,
    addNatureRow,
    removeNatureRow,
    updateStageRow,
    updateTop5Row,
    addTop5Row,
    updateReversalRow,
    addReversalRow,
    updateWriteoffRow,
    addWriteoffRow,
    updateGovGrantRow,
    addGovGrantRow,
    updateTransferRow,
    addTransferRow,
    updateFundCentralization,
    updateContinuedInvolvement,
    updateNoteSection,
    getSyncSnapshot,
    syncToNotes,
    payload,
  }
}

export type { K1AgingDisclosureRow, K1StageMovementRow }
