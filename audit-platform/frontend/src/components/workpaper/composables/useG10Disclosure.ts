/**
 * useG10Disclosure — 附注披露（上市/国企）
 *
 * 结构对齐 Excel：
 * - 上市：变动表(期初/增加/减少/期末) + 指定明细 + 信用风险拆分 + 衍生负债
 * - 国企：余额表(期末/期初) + 信用风险拆分
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G10_ACCOUNT_CODE } from './g10Constants'
import {
  G10_ADJUDICATED_KEY,
  G10_ADJ_ROWS_KEY,
  G10_CROSS_TOLERANCE,
  computeG10ListedDisclosurePull,
  computeG10SoeDisclosurePull,
  defaultG10ListedDiscStore,
  defaultG10SoeDiscStore,
  movementClosingSum,
  soeCurrentSum,
  type G10DiscListedStore,
  type G10DiscSoeStore,
  type G10DiscMovementPair,
} from './g10DisclosureFromAdj'
import {
  G10_DISCLOSURE_COL_LABELS,
  G10_DISCLOSURE_TOTAL_LABEL,
  G10_LISTED_MOVEMENT_ROWS,
  G10_SOE_BALANCE_ROWS,
  G10_LISTED_DESIGNATED_SEED_LABEL,
  G10_FV_CREDIT_SEED_LABEL,
  g10MaturityDiffPlaceholder,
} from './g10SchemaRows'
import { parseNum, calcSubtotal } from './useG10FormulaEngine'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
import type { ChecklistResponse } from './useF1FormData'
import {
  buildG10DisclosureCrossChecks,
  buildG10MovementCrossChecks,
} from './g10DisclosureCross'
import {
  buildG10DisclosureProcedureSummary,
  G10A_DISCLOSURE_MARK_KEY,
  G10A_DISCLOSURE_PROGRAM_NOS,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { G10_NOTE_SECTION, fetchG10CentralNoteText } from './g10NoteSectionMap'
import type { G10ListedSyncSnapshot, G10SoeSyncSnapshot } from './g10DisclosureSyncPayload'

type Variant = 'listed' | 'soe'

function itemId(variant: Variant): string {
  return variant === 'listed' ? 'G10-disclosure-listed' : 'G10-disclosure-soe'
}

function noteItemId(variant: Variant): string {
  return `${itemId(variant)}-note`
}

function nextRowKey(prefix: string, existing: string[]): string {
  let n = existing.length + 1
  while (existing.includes(`${prefix}_${n}`)) n += 1
  return `${prefix}_${n}`
}

function resolveDiscLabel(rowKey: string, stored: string | undefined, seed: string): string {
  if (stored?.trim()) return stored.trim()
  if (rowKey.endsWith('_1')) return seed
  return rowKey
}

function calcClosingFromMovement(row: G10DiscMovementPair): number {
  return row.openingAmount + row.increaseAmount - row.decreaseAmount
}

function enrichMovement(row: G10DiscMovementPair): G10DiscMovementPair {
  return {
    ...row,
    closingAmount: calcClosingFromMovement(row),
  }
}

function parentMovementSum(
  childKeys: string[],
  movement: Record<string, G10DiscMovementPair>,
): G10DiscMovementPair {
  const rows = childKeys.map((k) => movement[k] ?? {
    openingAmount: 0,
    increaseAmount: 0,
    decreaseAmount: 0,
    closingAmount: 0,
  })
  return {
    openingAmount: calcSubtotal(rows.map((r) => r.openingAmount)),
    increaseAmount: calcSubtotal(rows.map((r) => r.increaseAmount)),
    decreaseAmount: calcSubtotal(rows.map((r) => r.decreaseAmount)),
    closingAmount: calcSubtotal(rows.map((r) => r.closingAmount)),
  }
}

function parentBalanceSum(
  childKeys: string[],
  balance: Record<string, { currentAmount: number; priorAmount: number }>,
): { currentAmount: number; priorAmount: number } {
  return {
    currentAmount: calcSubtotal(childKeys.map((k) => balance[k]?.currentAmount ?? 0)),
    priorAmount: calcSubtotal(childKeys.map((k) => balance[k]?.priorAmount ?? 0)),
  }
}

export function useG10Disclosure(opts: {
  variant: Variant
  wpId: Ref<string>
  projectId?: Ref<string> | ComputedRef<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const auditYear = useWorkpaperAuditYear()
  const listedStore = ref<G10DiscListedStore>(defaultG10ListedDiscStore())
  const soeStore = ref<G10DiscSoeStore>(defaultG10SoeDiscStore())
  const adjudicatedAmount = ref<number | null>(null)
  const noteText = ref('')
  const aiLoading = ref(false)
  const lastPulledAdjAmount = ref<number | null>(null)
  const pullSummary = ref('')
  const lastPullUsedResidual = ref(false)
  const procedureMarking = ref(false)

  const title = computed(() =>
    opts.variant === 'listed' ? '附注披露信息（上市公司）' : '附注披露信息（国企）',
  )

  const colLabels = computed(() => {
    const year = auditYear.value
    if (opts.variant === 'listed') {
      return {
        movement: G10_DISCLOSURE_COL_LABELS.listed.movement,
        designated: G10_DISCLOSURE_COL_LABELS.listed.designated,
        fvCredit: G10_DISCLOSURE_COL_LABELS.listed.fvCredit(year),
        derivative: G10_DISCLOSURE_COL_LABELS.listed.derivative,
      }
    }
    return {
      balance: G10_DISCLOSURE_COL_LABELS.soe.balance,
      fvCredit: G10_DISCLOSURE_COL_LABELS.soe.fvCredit(year),
    }
  })

  function loadStore(): void {
    const raw = opts.allResponses.value.get(itemId(opts.variant))?.remark
    try {
      const parsed = raw ? JSON.parse(raw) : null
      if (parsed?.version === 2) {
        if (opts.variant === 'listed') {
          listedStore.value = { ...defaultG10ListedDiscStore(), ...parsed }
        } else {
          soeStore.value = { ...defaultG10SoeDiscStore(), ...parsed }
        }
      }
    } catch {
      if (opts.variant === 'listed') listedStore.value = defaultG10ListedDiscStore()
      else soeStore.value = defaultG10SoeDiscStore()
    }
    noteText.value = opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion ?? ''
    const adj = opts.allResponses.value.get(G10_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
  }

  watch(() => opts.allResponses.value.get(itemId(opts.variant))?.remark, loadStore, { immediate: true })
  watch(() => opts.allResponses.value.get(noteItemId(opts.variant))?.conclusion, (v) => {
    noteText.value = v ?? ''
  }, { immediate: true })
  watch(() => opts.allResponses.value.get(G10_ADJUDICATED_KEY)?.conclusion, (v) => {
    if (v != null && v !== '') adjudicatedAmount.value = parseNum(v)
  })

  const listedMovementRows = computed(() => {
    const mv = listedStore.value.movement
    const tradingChildren = ['mv_trading_bond', 'mv_derivative', 'mv_other']
    const designatedChildren = ['mv_designated_bond', 'mv_hybrid_tool', 'mv_designated_other']
    return G10_LISTED_MOVEMENT_ROWS.map((def) => {
      let row = mv[def.rowKey] ?? {
        openingAmount: 0,
        increaseAmount: 0,
        decreaseAmount: 0,
        closingAmount: 0,
      }
      if (def.isParent) {
        row = parentMovementSum(
          def.rowKey === 'mv_trading' ? tradingChildren : designatedChildren,
          mv,
        )
      } else {
        row = enrichMovement(row)
      }
      return { ...def, ...row, isTotal: false as const }
    })
  })

  const listedMovementTotal = computed(() => {
    const trading = listedMovementRows.value.find((r) => r.rowKey === 'mv_trading')
    const designated = listedMovementRows.value.find((r) => r.rowKey === 'mv_designated')
    return {
      rowKey: 'mv_total',
      label: G10_DISCLOSURE_TOTAL_LABEL,
      openingAmount: (trading?.openingAmount ?? 0) + (designated?.openingAmount ?? 0),
      increaseAmount: (trading?.increaseAmount ?? 0) + (designated?.increaseAmount ?? 0),
      decreaseAmount: (trading?.decreaseAmount ?? 0) + (designated?.decreaseAmount ?? 0),
      closingAmount: (trading?.closingAmount ?? 0) + (designated?.closingAmount ?? 0),
      isTotal: true as const,
    }
  })

  const listedMovementDisplay = computed(() => [
    ...listedMovementRows.value,
    listedMovementTotal.value,
  ])

  const soeBalanceRows = computed(() => {
    const bal = soeStore.value.balance
    const tradingChildren = ['soe_trading_bond', 'soe_derivative', 'soe_other']
    const designatedChildren = ['soe_hybrid_tool', 'soe_designated_other']
    return G10_SOE_BALANCE_ROWS.map((def) => {
      let row = bal[def.rowKey] ?? { currentAmount: 0, priorAmount: 0 }
      if (def.isParent) {
        row = parentBalanceSum(
          def.rowKey === 'soe_trading' ? tradingChildren : designatedChildren,
          bal,
        )
      }
      return { ...def, ...row, isTotal: false as const }
    })
  })

  const soeBalanceTotal = computed(() => ({
    rowKey: 'soe_total',
    label: G10_DISCLOSURE_TOTAL_LABEL,
    currentAmount: calcSubtotal(soeBalanceRows.value.filter((r) => !r.isParent).map((r) => r.currentAmount)),
    priorAmount: calcSubtotal(soeBalanceRows.value.filter((r) => !r.isParent).map((r) => r.priorAmount)),
    isTotal: true as const,
  }))

  const soeBalanceDisplay = computed(() => [...soeBalanceRows.value, soeBalanceTotal.value])

  const disclosureClosingSum = computed(() =>
    opts.variant === 'listed'
      ? movementClosingSum(listedStore.value)
      : soeCurrentSum(soeStore.value),
  )

  const adjCrossVariance = computed(() => {
    if (adjudicatedAmount.value == null) return null
    return disclosureClosingSum.value - adjudicatedAmount.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > G10_CROSS_TOLERANCE,
  )

  const adjChangedSincePull = computed(() => {
    if (lastPulledAdjAmount.value == null || adjudicatedAmount.value == null) return false
    return Math.abs(adjudicatedAmount.value - lastPulledAdjAmount.value) > G10_CROSS_TOLERANCE
  })

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_DISCLOSURE_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_DISCLOSURE_MARK_KEY)?.conclusion === 'completed',
  )

  const crossChecks = computed(() => [
    ...buildG10DisclosureCrossChecks(opts.allResponses.value),
    ...(opts.variant === 'listed'
      ? buildG10MovementCrossChecks(listedStore.value.movement)
      : []),
  ])

  const maturityDiffPlaceholder = computed(() =>
    g10MaturityDiffPlaceholder(auditYear.value),
  )

  function persist(): void {
    const year = auditYear.value ?? undefined
    const payload = opts.variant === 'listed'
      ? { ...listedStore.value, auditYear: year }
      : { ...soeStore.value, auditYear: year }
    opts.debouncedSave(itemId(opts.variant), { remark: JSON.stringify(payload) })
    publishNoteUpdate()
  }

  function updateListedMovement(
    rowKey: string,
    field: keyof G10DiscMovementPair,
    value: unknown,
  ): void {
    if (opts.isReadonly.value) return
    const def = G10_LISTED_MOVEMENT_ROWS.find((r) => r.rowKey === rowKey)
    if (!def || def.isParent) return
    const cur = listedStore.value.movement[rowKey] ?? {
      openingAmount: 0,
      increaseAmount: 0,
      decreaseAmount: 0,
      closingAmount: 0,
    }
    const next = { ...cur, [field]: parseNum(value) }
    const stored = field === 'closingAmount'
      ? {
          ...next,
          decreaseAmount: Math.max(0, next.openingAmount + next.increaseAmount - next.closingAmount),
        }
      : enrichMovement(next)
    listedStore.value = {
      ...listedStore.value,
      movement: {
        ...listedStore.value.movement,
        [rowKey]: stored,
      },
    }
    persist()
  }

  function updateSoeBalance(
    rowKey: string,
    field: 'currentAmount' | 'priorAmount',
    value: unknown,
  ): void {
    if (opts.isReadonly.value) return
    const def = G10_SOE_BALANCE_ROWS.find((r) => r.rowKey === rowKey)
    if (!def || def.isParent) return
    const cur = soeStore.value.balance[rowKey] ?? { currentAmount: 0, priorAmount: 0 }
    soeStore.value = {
      ...soeStore.value,
      balance: {
        ...soeStore.value.balance,
        [rowKey]: { ...cur, [field]: parseNum(value) },
      },
    }
    persist()
  }

  function updateDesignatedDetail(
    rowKey: string,
    field: 'label' | 'openingAmount' | 'closingAmount' | 'designationReason',
    value: unknown,
  ): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    const cur = listedStore.value.designatedDetail[rowKey] ?? {
      label: '',
      openingAmount: 0,
      closingAmount: 0,
      designationReason: '',
    }
    listedStore.value = {
      ...listedStore.value,
      designatedDetail: {
        ...listedStore.value.designatedDetail,
        [rowKey]: {
          ...cur,
          [field]: field === 'designationReason' || field === 'label'
            ? String(value ?? '')
            : parseNum(value),
        },
      },
    }
    persist()
  }

  function addDesignatedRow(): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    const keys = Object.keys(listedStore.value.designatedDetail)
    const rowKey = nextRowKey('designated', keys)
    listedStore.value = {
      ...listedStore.value,
      designatedDetail: {
        ...listedStore.value.designatedDetail,
        [rowKey]: { label: '', openingAmount: 0, closingAmount: 0, designationReason: '' },
      },
    }
    persist()
  }

  function removeDesignatedRow(rowKey: string): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    const keys = Object.keys(listedStore.value.designatedDetail)
    if (keys.length <= 1) return
    const next = { ...listedStore.value.designatedDetail }
    delete next[rowKey]
    listedStore.value = { ...listedStore.value, designatedDetail: next }
    persist()
  }

  function updateFvCredit(
    rowKey: string,
    field: 'label' | 'fvChangeAmount' | 'creditRiskCurrent' | 'creditRiskCumulative',
    value: unknown,
  ): void {
    if (opts.isReadonly.value) return
    const store = opts.variant === 'listed' ? listedStore.value : soeStore.value
    const cur = store.fvCreditRisk[rowKey] ?? {
      label: '',
      fvChangeAmount: 0,
      creditRiskCurrent: 0,
      creditRiskCumulative: 0,
    }
    const patch = {
      ...cur,
      [field]: field === 'label' ? String(value ?? '') : parseNum(value),
    }
    if (opts.variant === 'listed') {
      listedStore.value = {
        ...listedStore.value,
        fvCreditRisk: { ...listedStore.value.fvCreditRisk, [rowKey]: patch },
      }
    } else {
      soeStore.value = {
        ...soeStore.value,
        fvCreditRisk: { ...soeStore.value.fvCreditRisk, [rowKey]: patch },
      }
    }
    persist()
  }

  function addFvCreditRow(): void {
    if (opts.isReadonly.value) return
    const store = opts.variant === 'listed' ? listedStore.value : soeStore.value
    const keys = Object.keys(store.fvCreditRisk)
    const rowKey = nextRowKey('fv', keys)
    const patch = { label: '', fvChangeAmount: 0, creditRiskCurrent: 0, creditRiskCumulative: 0 }
    if (opts.variant === 'listed') {
      listedStore.value = {
        ...listedStore.value,
        fvCreditRisk: { ...listedStore.value.fvCreditRisk, [rowKey]: patch },
      }
    } else {
      soeStore.value = {
        ...soeStore.value,
        fvCreditRisk: { ...soeStore.value.fvCreditRisk, [rowKey]: patch },
      }
    }
    persist()
  }

  function removeFvCreditRow(rowKey: string): void {
    if (opts.isReadonly.value) return
    const store = opts.variant === 'listed' ? listedStore.value : soeStore.value
    const keys = Object.keys(store.fvCreditRisk)
    if (keys.length <= 1) return
    const next = { ...store.fvCreditRisk }
    delete next[rowKey]
    if (opts.variant === 'listed') {
      listedStore.value = { ...listedStore.value, fvCreditRisk: next }
    } else {
      soeStore.value = { ...soeStore.value, fvCreditRisk: next }
    }
    persist()
  }

  function addDerivativeRow(): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    const n = listedStore.value.derivativeRows.length + 1
    listedStore.value = {
      ...listedStore.value,
      derivativeRows: [
        ...listedStore.value.derivativeRows,
        { rowKey: `deriv_${n}`, label: '', currentAmount: 0, priorAmount: 0 },
      ],
    }
    persist()
  }

  function removeDerivativeRow(rowKey: string): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    listedStore.value = {
      ...listedStore.value,
      derivativeRows: listedStore.value.derivativeRows.filter((r) => r.rowKey !== rowKey),
    }
    persist()
  }

  function updateDerivativeRow(
    rowKey: string,
    field: 'label' | 'currentAmount' | 'priorAmount',
    value: unknown,
  ): void {
    if (opts.isReadonly.value || opts.variant !== 'listed') return
    listedStore.value = {
      ...listedStore.value,
      derivativeRows: listedStore.value.derivativeRows.map((r) =>
        r.rowKey === rowKey
          ? { ...r, [field]: field === 'label' ? String(value ?? '') : parseNum(value) }
          : r,
      ),
    }
    persist()
  }

  function updateTextField(
    field: 'derivativeNote' | 'maturityDiffNote',
    value: string,
  ): void {
    if (opts.isReadonly.value) return
    if (opts.variant === 'listed') {
      listedStore.value = { ...listedStore.value, [field]: value }
    } else {
      soeStore.value = { ...soeStore.value, maturityDiffNote: value }
    }
    persist()
  }

  function updateNoteText(value: string): void {
    if (opts.isReadonly.value) return
    noteText.value = value
    opts.debouncedSave(noteItemId(opts.variant), { conclusion: value })
    publishNoteUpdate()
  }

  function pullFromAdjudication(): void {
    if (opts.isReadonly.value) return
    const adj = opts.allResponses.value.get(G10_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)

    if (opts.variant === 'listed') {
      const listed = computeG10ListedDisclosurePull(
        opts.allResponses.value,
        listedStore.value,
        auditYear.value,
      )
      listedStore.value = listed.next
      lastPullUsedResidual.value = listed.usedResidual
      pullSummary.value = listed.summary
    } else {
      const soe = computeG10SoeDisclosurePull(
        opts.allResponses.value,
        soeStore.value,
        auditYear.value,
      )
      soeStore.value = soe.next
      lastPullUsedResidual.value = soe.usedResidual
      pullSummary.value = soe.summary
    }

    lastPulledAdjAmount.value = adjudicatedAmount.value
    persist()

    if (lastPullUsedResidual.value) {
      ElMessage.warning(pullSummary.value)
    } else {
      ElMessage.success(`已从 G10-1/G10-2 分项带入：${pullSummary.value}`)
    }
  }

  function pullLatestAdjudicated(writeCategories = false): void {
    const adj = opts.allResponses.value.get(G10_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') adjudicatedAmount.value = parseNum(adj)
    if (writeCategories) pullFromAdjudication()
  }

  /** 从中央附注模块带入主章节叙述文本（附注 → 底稿） */
  async function pullNoteTextFromCentral(optsPull?: { overwrite?: boolean }): Promise<string | null> {
    if (opts.isReadonly.value) return null
    const pid = opts.projectId?.value || ''
    const year = auditYear.value
    if (!pid || year == null) {
      ElMessage.warning('缺少项目或审计年度，无法从附注模块取数')
      return null
    }
    try {
      const text = await fetchG10CentralNoteText(
        api.get.bind(api) as (url: string, config?: Record<string, unknown>) => Promise<unknown>,
        pid,
        year,
        opts.variant,
      )
      if (!text) {
        ElMessage.info(`附注模块「${G10_NOTE_SECTION[opts.variant].trading}」暂无文本`)
        return null
      }
      const existing = noteText.value.trim()
      if (existing && existing !== text && !optsPull?.overwrite) {
        try {
          await ElMessageBox.confirm(
            '将用附注模块文本覆盖当前披露说明，是否继续？',
            '从附注带入文本',
            { type: 'warning', confirmButtonText: '覆盖', cancelButtonText: '取消' },
          )
        } catch {
          return null
        }
      }
      updateNoteText(text)
      ElMessage.success(`已从附注「${G10_NOTE_SECTION[opts.variant].trading}」带入文本`)
      return text
    } catch {
      ElMessage.warning('从附注模块取数失败，请稍后重试')
      return null
    }
  }

  function publishNoteUpdate(): void {
    try {
      const sections = G10_NOTE_SECTION[opts.variant]
      const sectionIds = [sections.trading]
      if (opts.variant === 'listed') {
        const hasDeriv = listedStore.value.derivativeRows.some(
          (r) => Math.abs(r.currentAmount) > 0.005 || Math.abs(r.priorAmount) > 0.005,
        ) || Boolean(listedStore.value.derivativeNote?.trim())
        if (hasDeriv) sectionIds.push(sections.derivative)
      }
      eventBus.emit('disclosure:note-text-updated', {
        wpCode: 'G10',
        accountCode: G10_ACCOUNT_CODE,
        projectId: opts.projectId?.value ?? '',
        wpId: opts.wpId.value,
        variant: opts.variant,
        section: opts.variant,
        sectionId: sections.trading,
        sectionIds,
        text: noteText.value,
        timestamp: Date.now(),
      })
    } catch { /* silent */ }
  }

  function getSyncSnapshot(auditNote = ''): G10ListedSyncSnapshot | G10SoeSyncSnapshot {
    const year = auditYear.value
    if (opts.variant === 'listed') {
      return {
        store: { ...listedStore.value, auditYear: year ?? undefined },
        auditNote,
        auditYear: year,
      }
    }
    return {
      store: { ...soeStore.value, auditYear: year ?? undefined },
      auditNote,
      auditYear: year,
    }
  }

  function onAdjudicated(ev: Event): void {
    const detail = (ev as CustomEvent).detail
    if (detail?.accountCode !== G10_ACCOUNT_CODE) return
    adjudicatedAmount.value = parseNum(detail.adjudicatedAmount)
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (Math.abs(disclosureClosingSum.value) < 0.005) {
      ElMessage.warning('请先编制附注披露（可从 G10-1/G10-2 分项带入）')
      return -1
    }
    if (hasAdjCrossMismatch.value) {
      try {
        await ElMessageBox.confirm(
          `附注合计与 G10-1 审定差异 ${adjCrossVariance.value?.toFixed(2) ?? '—'}，是否仍标记 G10A 列报披露程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG10DisclosureProcedureSummary({
        variant: opts.variant,
        closingSum: disclosureClosingSum.value,
        adjudicated: adjudicatedAmount.value,
        crossVariance: adjCrossVariance.value,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        programNos: [...G10A_DISCLOSURE_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: opts.variant === 'listed' ? '附注上市' : '附注国企',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_DISCLOSURE_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          variant: opts.variant,
          summary,
          programNos: [...G10A_DISCLOSURE_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_DISCLOSURE_PROGRAM_NOS].join('/')}（列报披露）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  async function generateAiConclusion(): Promise<void> {
    if (opts.isReadonly.value) return
    aiLoading.value = true
    try {
      const res = await api.post(
        `/api/workpapers/${opts.wpId.value}/g10/ai/adjudication-analysis`,
        {
          variant: opts.variant,
          adjudicatedAmount: adjudicatedAmount.value,
          disclosureSum: disclosureClosingSum.value,
        },
        { _silent: true } as any,
      )
      const text = res?.data?.content ?? res?.content ?? ''
      if (text) updateNoteText(text)
    } catch { /* AI optional */ }
    finally { aiLoading.value = false }
  }

  function onDetailToAdjudication(): void {
    const adj = opts.allResponses.value.get(G10_ADJUDICATED_KEY)?.conclusion
    if (adj != null && adj !== '') {
      adjudicatedAmount.value = parseNum(adj)
      if (lastPulledAdjAmount.value != null) {
        lastPulledAdjAmount.value = null
      }
    }
  }

  function onDisclosurePulled(ev: Event): void {
    const detail = (ev as CustomEvent<{ usedResidual?: boolean; summary?: string }>).detail
    if (detail?.summary) pullSummary.value = detail.summary
    if (detail?.usedResidual != null) lastPullUsedResidual.value = detail.usedResidual
    loadStore()
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', onAdjudicated)
    window.addEventListener('g10:detail-to-adjudication', onDetailToAdjudication)
    window.addEventListener('g10:disclosure-pulled', onDisclosurePulled)
    pullLatestAdjudicated(false)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', onAdjudicated)
    window.removeEventListener('g10:detail-to-adjudication', onDetailToAdjudication)
    window.removeEventListener('g10:disclosure-pulled', onDisclosurePulled)
  })

  const designatedDetailRows = computed(() => {
    const entries = Object.entries(listedStore.value.designatedDetail)
    if (entries.length === 0) {
      return [{
        rowKey: 'designated_1',
        label: G10_LISTED_DESIGNATED_SEED_LABEL,
        openingAmount: 0,
        closingAmount: 0,
        designationReason: '',
      }]
    }
    return entries.map(([rowKey, v]) => ({
      rowKey,
      label: resolveDiscLabel(rowKey, v.label, G10_LISTED_DESIGNATED_SEED_LABEL),
      ...v,
    }))
  })

  const fvCreditRows = computed(() => {
    const store = opts.variant === 'listed' ? listedStore.value : soeStore.value
    const entries = Object.entries(store.fvCreditRisk)
    if (entries.length === 0) {
      return [{
        rowKey: 'fv_1',
        label: G10_FV_CREDIT_SEED_LABEL,
        fvChangeAmount: 0,
        creditRiskCurrent: 0,
        creditRiskCumulative: 0,
      }]
    }
    return entries.map(([rowKey, v]) => ({
      rowKey,
      label: resolveDiscLabel(rowKey, v.label, G10_FV_CREDIT_SEED_LABEL),
      ...v,
    }))
  })

  const fvCreditTotal = computed(() => ({
    rowKey: 'fv_total',
    label: G10_DISCLOSURE_TOTAL_LABEL,
    fvChangeAmount: calcSubtotal(fvCreditRows.value.map((r) => r.fvChangeAmount)),
    creditRiskCurrent: calcSubtotal(fvCreditRows.value.map((r) => r.creditRiskCurrent)),
    creditRiskCumulative: calcSubtotal(fvCreditRows.value.map((r) => r.creditRiskCumulative)),
    isTotal: true as const,
  }))

  const derivativeDisplay = computed(() => {
    const rows = listedStore.value.derivativeRows
    const total = {
      rowKey: 'deriv_total',
      label: G10_DISCLOSURE_TOTAL_LABEL,
      currentAmount: calcSubtotal(rows.map((r) => r.currentAmount)),
      priorAmount: calcSubtotal(rows.map((r) => r.priorAmount)),
      isTotal: true as const,
    }
    return [...rows, total]
  })

  return {
    title,
    colLabels,
    noteText,
    adjudicatedAmount,
    disclosureClosingSum,
    adjCrossVariance,
    hasAdjCrossMismatch,
    adjChangedSincePull,
    procedureMarking,
    procedureMarked,
    crossChecks,
    maturityDiffPlaceholder,
    pullSummary,
    lastPullUsedResidual,
    aiLoading,
    listedMovementDisplay,
    soeBalanceDisplay,
    designatedDetailRows,
    fvCreditRows,
    fvCreditTotal,
    derivativeDisplay,
    derivativeNote: computed(() => listedStore.value.derivativeNote),
    maturityDiffNote: computed(() =>
      opts.variant === 'listed'
        ? listedStore.value.maturityDiffNote
        : soeStore.value.maturityDiffNote,
    ),
    updateListedMovement,
    updateSoeBalance,
    updateDesignatedDetail,
    addDesignatedRow,
    removeDesignatedRow,
    updateFvCredit,
    addFvCreditRow,
    removeFvCreditRow,
    updateDerivativeRow,
    addDerivativeRow,
    removeDerivativeRow,
    updateTextField,
    updateNoteText,
    pullFromAdjudication,
    pullLatestAdjudicated,
    pullNoteTextFromCentral,
    clearPullSummary: () => { pullSummary.value = '' },
    generateAiConclusion,
    markProcedureComplete,
    getSyncSnapshot,
  }
}
