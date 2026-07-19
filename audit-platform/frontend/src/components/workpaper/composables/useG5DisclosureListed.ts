/**
 * useG5DisclosureListed — G5 附注披露（上市公司）结构化编制
 *
 * - 对齐 Excel：性质分类 / 坏账计提（单项·组合）/ 组合账龄块 / 变动 / 补充披露
 * - 动态插行：性质自定义行、单项明细、组合块 均可无限增删
 * - 组合一致性：从 G5-3 组合名 / G5-8 政策候选同步，并提示与会计政策一致
 * - 从 G5-1/G5-2/G5-3 取数；比例防 #DIV/0!；性质合计↔坏账合计勾稽
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistResponse } from './useF1FormData'
import { G5_ACCOUNT_CODE } from './g5Constants'
import { parseG5AdjStore } from './g5AdjudicationItems'
import { readCanonicalRaw } from './g5StorageContract'
import {
  remapDisclosureAgingRows,
  resolveG5AgingSegments,
  validateCustomAgingLabels,
  type G5AgingPreset,
} from './g5AgingScheme'
import { ElMessage } from 'element-plus'
import {
  bookValue,
  buildDefaultListedState,
  classifyNatureFromDetail,
  computeNatureMethodTieOut,
  createEmptyCustomNature,
  createEmptyIndividualDetail,
  createEmptyLeaseMlp,
  createEmptyPortfolio,
  createEmptyWriteoff,
  extractAdjCell,
  extractBadDebtForDisclosure,
  extractPolicyGroupNames,
  fmtRate,
  parseListedDisclosure,
  recomputeAgingTotals,
  recomputeMethodTotals,
  recomputeMovementClosing,
  recomputeNatureDerived,
  safeRate,
  serializeListedDisclosure,
  syncPortfoliosByNames,
  type G5AgingBandRow,
  type G5IndividualDetailRow,
  type G5ListedDisclosureState,
  type G5MethodRow,
  type G5MovementRow,
  type G5NatureRow,
  type G5PeriodAmt,
  type G5PortfolioBlock,
  type G5WriteoffRow,
  type G5LeaseMlpRow,
} from './g5ListedDisclosureRows'

const ITEM_ROWS = 'G5-note-listed-rows'
const ITEM_NOTE = 'G5-note-listed-note'
/** 兼容旧 stub 文本持久化 */
const ITEM_NOTE_LEGACY = 'G5-disclosure-listed-text'
const ITEM_ADJ = 'G5-1-rows'
const ITEM_DETAIL = 'G5-2-rows'
const ITEM_BAD = 'G5-3-rows'
const ITEM_POLICY = 'G5-8-policy'

export function useG5DisclosureListed(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const { allResponses, debouncedSave, isReadonly } = opts

  const state = ref<G5ListedDisclosureState>(buildDefaultListedState())
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const lastSyncHint = ref('')
  const policyGroupNames = ref<string[]>([])

  function persistRows() {
    if (isReadonly.value) return
    const json = serializeListedDisclosure(state.value)
    debouncedSave(ITEM_ROWS, { remark: json, conclusion: json })
  }

  function loadPersisted() {
    const parsed = parseListedDisclosure(readCanonicalRaw(allResponses.value.get(ITEM_ROWS)))
    if (parsed) state.value = parsed
    const note =
      allResponses.value.get(ITEM_NOTE)?.remark
      ?? allResponses.value.get(ITEM_NOTE_LEGACY)?.remark
    if (note != null) noteText.value = note
    refreshPolicyNames()
  }

  function refreshPolicyNames() {
    policyGroupNames.value = extractPolicyGroupNames(
      readCanonicalRaw(allResponses.value.get(ITEM_POLICY)),
    )
  }

  watch(
    () => readCanonicalRaw(allResponses.value.get(ITEM_ROWS)),
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
          detail: { accountCode: G5_ACCOUNT_CODE, section: 'listed', text: val },
        }),
      )
    } catch {
      /* silent */
    }
  })

  const natureDisplayRows = computed(() => recomputeNatureDerived(state.value.natureRows))
  const methodDisplayRows = computed(() => recomputeMethodTotals(state.value.methodRows))
  const movementDisplayRows = computed(() =>
    recomputeMovementClosing(state.value.movementRows),
  )

  const tieOut = computed(() =>
    computeNatureMethodTieOut(state.value.natureRows, state.value.methodRows),
  )

  /** 组合名 vs 政策披露一致性 */
  const portfolioConsistency = computed(() => {
    const disclosed = state.value.portfolios.map((p) => p.name.trim()).filter(Boolean)
    const policy = policyGroupNames.value.map((n) => n.trim()).filter(Boolean)
    if (!policy.length) {
      return {
        status: 'unknown' as const,
        missingInDisclosure: [] as string[],
        extraInDisclosure: [] as string[],
        message: '未读取到 G5-8 组合政策名称；请确认组合与会计政策披露一致。',
      }
    }
    const pSet = new Set(policy)
    const dSet = new Set(disclosed)
    const missingInDisclosure = policy.filter((n) => !dSet.has(n))
    const extraInDisclosure = disclosed.filter((n) => !pSet.has(n))
    const ok = missingInDisclosure.length === 0 && extraInDisclosure.length === 0
    return {
      status: ok ? ('matched' as const) : ('mismatch' as const),
      missingInDisclosure,
      extraInDisclosure,
      message: ok
        ? '组合名称与 G5-8 会计政策检查项一致。'
        : [
            missingInDisclosure.length
              ? `政策有、披露缺：${missingInDisclosure.join('、')}`
              : '',
            extraInDisclosure.length
              ? `披露有、政策缺：${extraInDisclosure.join('、')}`
              : '',
          ]
            .filter(Boolean)
            .join('；'),
    }
  })

  function patchNature(
    id: string,
    patch: Partial<Pick<G5NatureRow, 'label' | 'endDiscountRate' | 'priorDiscountRate'>> & {
      end?: Partial<G5PeriodAmt>
      prior?: Partial<G5PeriodAmt>
    },
  ) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      natureRows: recomputeNatureDerived(
        state.value.natureRows.map((r) => {
          if (r.id !== id || !r.editable) return r
          return {
            ...r,
            label: patch.label ?? r.label,
            endDiscountRate: patch.endDiscountRate ?? r.endDiscountRate,
            priorDiscountRate: patch.priorDiscountRate ?? r.priorDiscountRate,
            end: { ...r.end, ...patch.end },
            prior: { ...r.prior, ...patch.prior },
          }
        }),
      ),
    }
    persistRows()
  }

  function addNatureRow(label = '') {
    if (isReadonly.value) return
    const custom = createEmptyCustomNature(label || '其他项目')
    const rows = [...state.value.natureRows]
    const subIdx = rows.findIndex((r) => r.kind === 'subtotal')
    if (subIdx >= 0) rows.splice(subIdx, 0, custom)
    else rows.push(custom)
    state.value = { ...state.value, natureRows: recomputeNatureDerived(rows) }
    persistRows()
  }

  function removeNatureRow(id: string) {
    if (isReadonly.value) return
    const target = state.value.natureRows.find((r) => r.id === id)
    if (!target || target.kind !== 'custom') return
    state.value = {
      ...state.value,
      natureRows: recomputeNatureDerived(
        state.value.natureRows.filter((r) => r.id !== id),
      ),
    }
    persistRows()
  }

  function patchMethod(
    id: string,
    patch: { end?: Partial<G5PeriodAmt>; prior?: Partial<G5PeriodAmt>; label?: string },
  ) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      methodRows: recomputeMethodTotals(
        state.value.methodRows.map((r) => {
          if (r.id !== id || !r.editable) return r
          return {
            ...r,
            label: patch.label ?? r.label,
            end: { ...r.end, ...patch.end },
            prior: { ...r.prior, ...patch.prior },
          }
        }),
      ),
    }
    persistRows()
  }

  function addIndividualDetail(name = '') {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      individualDetails: [
        ...state.value.individualDetails,
        createEmptyIndividualDetail(name),
      ],
    }
    persistRows()
  }

  function removeIndividualDetail(id: string) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      individualDetails: state.value.individualDetails.filter((r) => r.id !== id),
    }
    persistRows()
  }

  function patchIndividualDetail(id: string, patch: Partial<G5IndividualDetailRow>) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      individualDetails: state.value.individualDetails.map((r) =>
        r.id === id ? { ...r, ...patch } : r,
      ),
    }
    persistRows()
  }

  function addPortfolio(name = '') {
    if (isReadonly.value) return
    const preset = (state.value.agingPreset || 'THREE_YEAR') as G5AgingPreset
    const segs = resolveG5AgingSegments(preset, state.value.customAgingLabels || [])
    const pf = createEmptyPortfolio(name || `组合${state.value.portfolios.length + 1}`)
    pf.agingRows = remapDisclosureAgingRows([], segs)
    state.value = {
      ...state.value,
      portfolios: [...state.value.portfolios, pf],
    }
    persistRows()
  }

  function removePortfolio(id: string) {
    if (isReadonly.value) return
    if (state.value.portfolios.length <= 1) return
    state.value = {
      ...state.value,
      portfolios: state.value.portfolios.filter((p) => p.id !== id),
    }
    persistRows()
  }

  function patchPortfolioName(id: string, name: string) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      portfolios: state.value.portfolios.map((p) =>
        p.id === id ? { ...p, name, fromPolicy: false } : p,
      ),
    }
    persistRows()
  }

  function patchAgingCell(
    portfolioId: string,
    bandId: string,
    field: keyof Pick<
      G5AgingBandRow,
      'endBalance' | 'endProvision' | 'priorBalance' | 'priorProvision'
    >,
    value: number,
  ) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      portfolios: state.value.portfolios.map((p) => {
        if (p.id !== portfolioId) return p
        const agingRows = recomputeAgingTotals(
          p.agingRows.map((a) =>
            a.id === bandId && a.kind === 'band'
              ? { ...a, [field]: Number(value) || 0 }
              : a,
          ),
        )
        return { ...p, agingRows }
      }),
    }
    persistRows()
  }

  function setAgingPreset(preset: G5AgingPreset, customLabels?: string[]): boolean {
    if (isReadonly.value) return false
    let labels = state.value.customAgingLabels || []
    if (preset === 'CUSTOM') {
      labels = (customLabels || labels).map((l) => l.trim()).filter(Boolean)
      const err = validateCustomAgingLabels(labels)
      if (err) {
        ElMessage.warning(err)
        return false
      }
    } else {
      labels = []
    }
    const segs = resolveG5AgingSegments(preset, labels)
    state.value = {
      ...state.value,
      agingPreset: preset,
      customAgingLabels: labels,
      portfolios: state.value.portfolios.map((p) => ({
        ...p,
        agingRows: remapDisclosureAgingRows(p.agingRows, segs),
      })),
    }
    persistRows()
    return true
  }

  function patchMovement(
    rowKey: string,
    field: 'gross' | 'provision',
    value: number,
  ) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      movementRows: recomputeMovementClosing(
        state.value.movementRows.map((r) =>
          r.rowKey === rowKey && r.editable
            ? { ...r, [field]: Number(value) || 0 }
            : r,
        ),
      ),
    }
    persistRows()
  }

  function addWriteoff() {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      writeoffRows: [...state.value.writeoffRows, createEmptyWriteoff()],
    }
    persistRows()
  }

  function removeWriteoff(id: string) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      writeoffRows: state.value.writeoffRows.filter((r) => r.id !== id),
    }
    persistRows()
  }

  function patchWriteoff(id: string, patch: Partial<G5WriteoffRow>) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      writeoffRows: state.value.writeoffRows.map((r) =>
        r.id === id ? { ...r, ...patch } : r,
      ),
    }
    persistRows()
  }

  function patchLeaseMlp(id: string, patch: Partial<G5LeaseMlpRow>) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      leaseMlpRows: state.value.leaseMlpRows.map((r) =>
        r.id === id ? { ...r, ...patch } : r,
      ),
    }
    persistRows()
  }

  function addLeaseMlp() {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      leaseMlpRows: [...state.value.leaseMlpRows, createEmptyLeaseMlp('其他期间')],
    }
    persistRows()
  }

  function removeLeaseMlp(id: string) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      leaseMlpRows: state.value.leaseMlpRows.filter((r) => r.id !== id),
    }
    persistRows()
  }

  function setUnrealizedNote(text: string) {
    if (isReadonly.value) return
    state.value = { ...state.value, unrealizedNote: text }
    persistRows()
  }

  /** 从 G5-3 / G5-8 同步组合块名称 */
  function syncPortfoliosFromSources(preferPolicy = true) {
    if (isReadonly.value) return { count: 0 }
    refreshPolicyNames()
    const bad = extractBadDebtForDisclosure(readCanonicalRaw(allResponses.value.get(ITEM_BAD)))
    const names = preferPolicy && policyGroupNames.value.length
      ? policyGroupNames.value
      : bad.groupNames.length
        ? bad.groupNames
        : policyGroupNames.value
    if (!names.length) return { count: 0 }
    state.value = {
      ...state.value,
      portfolios: syncPortfoliosByNames(state.value.portfolios, names, {
        removeMissing: false,
        markFromPolicy: true,
      }),
    }
    persistRows()
    return { count: names.length }
  }

  /** 从 G5-1 / G5-2 / G5-3 取数 */
  function refreshFromSources(force = false) {
    if (isReadonly.value && !force) return
    const adjStore = parseG5AdjStore(readCanonicalRaw(allResponses.value.get(ITEM_ADJ)))
    const net = extractAdjCell(adjStore, 'net__row')
    adjudicatedAmount.value = net.closing || null

    const classified = classifyNatureFromDetail(
      readCanonicalRaw(allResponses.value.get(ITEM_DETAIL)),
    )
    const bad = extractBadDebtForDisclosure(readCanonicalRaw(allResponses.value.get(ITEM_BAD)))

    // 性质表
    let natureRows = state.value.natureRows.map((r) => {
      const pack = classified[r.rowKey]
      if (pack && (r.kind === 'preset')) {
        return {
          ...r,
          end: {
            balance: pack.end.balance,
            provision: r.end.provision,
          },
          prior: {
            balance: force || r.prior.balance === 0 ? pack.prior.balance : r.prior.balance,
            provision: r.prior.provision,
          },
        }
      }
      if (r.kind === 'subrow' && r.parentKey) {
        const parent = classified[r.parentKey]
        if (parent) {
          return {
            ...r,
            end: { balance: parent.unrealizedEnd, provision: 0 },
            prior: {
              balance:
                force || r.prior.balance === 0
                  ? parent.unrealizedPrior
                  : r.prior.balance,
              provision: 0,
            },
          }
        }
      }
      // 一年内 / 报表列示从 G5-1
      if (r.rowKey === 'one-year') {
        const g = extractAdjCell(adjStore, 'gross-one-year')
        const p = extractAdjCell(adjStore, 'provision-one-year')
        return {
          ...r,
          end: { balance: g.closing, provision: p.closing },
          prior: { balance: g.opening, provision: p.opening },
        }
      }
      return r
    })

    // 若明细无坏账拆分，用审定坏账灌入「其他」或按方法表
    const grossRep = extractAdjCell(adjStore, 'gross-reportable')
    const provRep = extractAdjCell(adjStore, 'provision-reportable')
    const hasNatureData = natureRows.some(
      (r) => (r.kind === 'preset' || r.kind === 'custom') && r.end.balance !== 0,
    )
    if (!hasNatureData && (grossRep.closing || grossRep.opening)) {
      natureRows = natureRows.map((r) =>
        r.rowKey === 'other'
          ? {
              ...r,
              end: { balance: grossRep.closing, provision: provRep.closing },
              prior: { balance: grossRep.opening, provision: provRep.opening },
            }
          : r,
      )
    }

    // 方法表：单项/组合
    const indG = extractAdjCell(adjStore, 'gross-individual')
    const indP = extractAdjCell(adjStore, 'provision-individual')
    const colBizG = extractAdjCell(adjStore, 'gross-collective-business')
    const colBizP = extractAdjCell(adjStore, 'provision-collective-business')
    const colCustG = extractAdjCell(adjStore, 'gross-collective-customer')
    const colCustP = extractAdjCell(adjStore, 'provision-collective-customer')

    const methodRows: G5MethodRow[] = recomputeMethodTotals(
      state.value.methodRows.map((r) => {
        if (r.rowKey === 'individual') {
          const fromBad = bad.individualTotals.end.balance !== 0
          return {
            ...r,
            end: {
              balance: fromBad ? bad.individualTotals.end.balance : indG.closing,
              provision: fromBad ? bad.individualTotals.end.provision : indP.closing,
            },
            prior: {
              balance: indG.opening,
              provision: fromBad
                ? bad.individualTotals.prior.provision
                : indP.opening,
            },
          }
        }
        if (r.rowKey === 'collective') {
          const fromBad = bad.groupTotals.end.balance !== 0
          return {
            ...r,
            end: {
              balance: fromBad
                ? bad.groupTotals.end.balance
                : colBizG.closing + colCustG.closing,
              provision: fromBad
                ? bad.groupTotals.end.provision
                : colBizP.closing + colCustP.closing,
            },
            prior: {
              balance: colBizG.opening + colCustG.opening,
              provision: fromBad
                ? bad.groupTotals.prior.provision
                : colBizP.opening + colCustP.opening,
            },
          }
        }
        return r
      }),
    )

    // 单项明细
    let individualDetails = state.value.individualDetails
    if (bad.individual.length && (force || individualDetails.length === 0)) {
      individualDetails = bad.individual
    }

    // 组合名同步（不删用户已加块）
    let portfolios = state.value.portfolios
    const syncNames =
      policyGroupNames.value.length > 0
        ? policyGroupNames.value
        : bad.groupNames
    if (syncNames.length) {
      portfolios = syncPortfoliosByNames(portfolios, syncNames, {
        removeMissing: false,
        markFromPolicy: true,
      })
    }

    // 变动期末灌入审定
    let movementRows = state.value.movementRows.map((r) => {
      if (r.rowKey === 'opening') {
        return {
          ...r,
          gross: grossRep.opening,
          provision: provRep.opening,
        }
      }
      return r
    })
    movementRows = recomputeMovementClosing(movementRows)

    state.value = {
      ...state.value,
      natureRows: recomputeNatureDerived(natureRows),
      methodRows,
      individualDetails,
      portfolios,
      movementRows,
    }
    lastSyncHint.value = new Date().toLocaleTimeString()
    persistRows()
  }

  function handleAdjudicated(e: Event) {
    const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
    if (d?.accountCode === G5_ACCOUNT_CODE && d.adjudicatedAmount != null) {
      adjudicatedAmount.value = d.adjudicatedAmount
      noteText.value = noteText.value.replace(/\[审定金额\]/g, String(d.adjudicatedAmount))
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', handleAdjudicated)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  })

  return {
    state,
    noteText,
    adjudicatedAmount,
    lastSyncHint,
    policyGroupNames,
    natureDisplayRows,
    methodDisplayRows,
    movementDisplayRows,
    tieOut,
    portfolioConsistency,
    bookValue,
    safeRate,
    fmtRate,
    patchNature,
    addNatureRow,
    removeNatureRow,
    patchMethod,
    addIndividualDetail,
    removeIndividualDetail,
    patchIndividualDetail,
    addPortfolio,
    removePortfolio,
    patchPortfolioName,
    patchAgingCell,
    setAgingPreset,
    patchMovement,
    addWriteoff,
    removeWriteoff,
    patchWriteoff,
    patchLeaseMlp,
    addLeaseMlp,
    removeLeaseMlp,
    setUnrealizedNote,
    syncPortfoliosFromSources,
    refreshFromSources,
    loadPersisted,
    persistRows,
  }
}

export type {
  G5NatureRow,
  G5MethodRow,
  G5IndividualDetailRow,
  G5PortfolioBlock,
  G5AgingBandRow,
  G5MovementRow,
  G5WriteoffRow,
  G5LeaseMlpRow,
}
