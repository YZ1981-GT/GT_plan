/**
 * useG5DisclosureSoe — G5 附注披露（国企）结构化编制
 *
 * 共享上市逻辑：性质 / 坏账概况 / 单项 / 组合账龄 / 取数勾稽 / 组合政策一致性
 * 国企专有：终止确认、继续涉入、坏账方法说明红区；账龄块支持「……」动态插段
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import type { ChecklistResponse } from './useF1FormData'
import { G5_ACCOUNT_CODE } from './g5Constants'
import { parseG5AdjStore } from './g5AdjudicationItems'
import { readCanonicalRaw } from './g5StorageContract'
import {
  bookValue,
  classifyNatureFromDetail,
  computeNatureMethodTieOut,
  createEmptyCustomNature,
  createEmptyIndividualDetail,
  createEmptyPortfolio,
  extractAdjCell,
  extractBadDebtForDisclosure,
  extractPolicyGroupNames,
  fmtRate,
  insertAgingBand,
  recomputeAgingTotals,
  recomputeMethodTotals,
  recomputeNatureDerived,
  removeAgingBand,
  safeRate,
  syncPortfoliosByNames,
  type G5AgingBandRow,
  type G5IndividualDetailRow,
  type G5MethodRow,
  type G5PeriodAmt,
} from './g5ListedDisclosureRows'
import {
  buildDefaultSoeState,
  createEmptyDerecogRow,
  parseSoeDisclosure,
  serializeSoeDisclosure,
  type G5ContinuingInvolvement,
  type G5DerecogRow,
  type G5SoeDisclosureState,
} from './g5SoeDisclosureRows'

const ITEM_ROWS = 'G5-note-soe-rows'
const ITEM_NOTE = 'G5-note-soe-note'
const ITEM_NOTE_LEGACY = 'G5-disclosure-soe-text'
const ITEM_ADJ = 'G5-1-rows'
const ITEM_DETAIL = 'G5-2-rows'
const ITEM_BAD = 'G5-3-rows'
const ITEM_POLICY = 'G5-8-policy'

export function useG5DisclosureSoe(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const { allResponses, debouncedSave, isReadonly } = opts

  const state = ref<G5SoeDisclosureState>(buildDefaultSoeState())
  const noteText = ref('')
  const adjudicatedAmount = ref<number | null>(null)
  const lastSyncHint = ref('')
  const policyGroupNames = ref<string[]>([])

  function persistRows() {
    if (isReadonly.value) return
    const json = serializeSoeDisclosure(state.value)
    debouncedSave(ITEM_ROWS, { remark: json, conclusion: json })
  }

  function refreshPolicyNames() {
    policyGroupNames.value = extractPolicyGroupNames(
      readCanonicalRaw(allResponses.value.get(ITEM_POLICY)),
    )
  }

  function loadPersisted() {
    const parsed = parseSoeDisclosure(readCanonicalRaw(allResponses.value.get(ITEM_ROWS)))
    if (parsed) state.value = parsed
    const note =
      allResponses.value.get(ITEM_NOTE)?.remark
      ?? allResponses.value.get(ITEM_NOTE_LEGACY)?.remark
    if (note != null) noteText.value = note
    refreshPolicyNames()
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
          detail: { accountCode: G5_ACCOUNT_CODE, section: 'soe', text: val },
        }),
      )
    } catch {
      /* silent */
    }
  })

  const natureDisplayRows = computed(() => recomputeNatureDerived(state.value.natureRows))
  const methodDisplayRows = computed(() => recomputeMethodTotals(state.value.methodRows))
  const tieOut = computed(() =>
    computeNatureMethodTieOut(state.value.natureRows, state.value.methodRows),
  )

  const portfolioConsistency = computed(() => {
    const disclosed = state.value.portfolios.map((p) => p.name.trim()).filter(Boolean)
    const policy = policyGroupNames.value.map((n) => n.trim()).filter(Boolean)
    if (!policy.length) {
      return {
        status: 'unknown' as const,
        message: '未读取到 G5-8 组合政策名称；请确认组合与会计政策披露一致。',
      }
    }
    const pSet = new Set(policy)
    const dSet = new Set(disclosed)
    const missing = policy.filter((n) => !dSet.has(n))
    const extra = disclosed.filter((n) => !pSet.has(n))
    const ok = !missing.length && !extra.length
    return {
      status: ok ? ('matched' as const) : ('mismatch' as const),
      message: ok
        ? '组合名称与 G5-8 会计政策检查项一致。'
        : [
            missing.length ? `政策有、披露缺：${missing.join('、')}` : '',
            extra.length ? `披露有、政策缺：${extra.join('、')}` : '',
          ]
            .filter(Boolean)
            .join('；'),
    }
  })

  function patchNature(
    id: string,
    patch: Partial<{ label: string; endDiscountRate: string; priorDiscountRate: string }> & {
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
      natureRows: recomputeNatureDerived(state.value.natureRows.filter((r) => r.id !== id)),
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
      individualDetails: [...state.value.individualDetails, createEmptyIndividualDetail(name)],
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
    state.value = {
      ...state.value,
      portfolios: [
        ...state.value.portfolios,
        createEmptyPortfolio(name || `组合${state.value.portfolios.length + 1}`),
      ],
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
        return {
          ...p,
          agingRows: recomputeAgingTotals(
            p.agingRows.map((a) =>
              a.id === bandId && a.kind === 'band'
                ? { ...a, [field]: Number(value) || 0 }
                : a,
            ),
          ),
        }
      }),
    }
    persistRows()
  }

  function addAgingBand(portfolioId: string, label = '其他账龄段') {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      portfolios: state.value.portfolios.map((p) =>
        p.id === portfolioId
          ? { ...p, agingRows: insertAgingBand(p.agingRows, label) }
          : p,
      ),
    }
    persistRows()
  }

  function removeAgingBandRow(portfolioId: string, bandId: string) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      portfolios: state.value.portfolios.map((p) =>
        p.id === portfolioId
          ? { ...p, agingRows: removeAgingBand(p.agingRows, bandId) }
          : p,
      ),
    }
    persistRows()
  }

  function addDerecogRow() {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      derecogRows: [...state.value.derecogRows, createEmptyDerecogRow()],
    }
    persistRows()
  }

  function removeDerecogRow(id: string) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      derecogRows: state.value.derecogRows.filter((r) => r.id !== id),
    }
    persistRows()
  }

  function patchDerecog(id: string, patch: Partial<G5DerecogRow>) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      derecogRows: state.value.derecogRows.map((r) =>
        r.id === id ? { ...r, ...patch } : r,
      ),
    }
    persistRows()
  }

  function patchContinuing(patch: Partial<G5ContinuingInvolvement>) {
    if (isReadonly.value) return
    state.value = {
      ...state.value,
      continuing: { ...state.value.continuing, ...patch },
    }
    persistRows()
  }

  function setProvisionMethodNote(text: string) {
    if (isReadonly.value) return
    state.value = { ...state.value, provisionMethodNote: text }
    persistRows()
  }

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

  function refreshFromSources(force = false) {
    if (isReadonly.value && !force) return
    const adjStore = parseG5AdjStore(readCanonicalRaw(allResponses.value.get(ITEM_ADJ)))
    const net = extractAdjCell(adjStore, 'net__row')
    adjudicatedAmount.value = net.closing || null

    const classified = classifyNatureFromDetail(
      readCanonicalRaw(allResponses.value.get(ITEM_DETAIL)),
    )
    const bad = extractBadDebtForDisclosure(readCanonicalRaw(allResponses.value.get(ITEM_BAD)))

    let natureRows = state.value.natureRows.map((r) => {
      const pack = classified[r.rowKey]
      if (pack && r.kind === 'preset') {
        return {
          ...r,
          end: { balance: pack.end.balance, provision: r.end.provision },
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

    let individualDetails = state.value.individualDetails
    if (bad.individual.length && (force || individualDetails.length === 0)) {
      individualDetails = bad.individual
    }

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

    state.value = {
      ...state.value,
      natureRows: recomputeNatureDerived(natureRows),
      methodRows,
      individualDetails,
      portfolios,
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
    addAgingBand,
    removeAgingBandRow,
    addDerecogRow,
    removeDerecogRow,
    patchDerecog,
    patchContinuing,
    setProvisionMethodNote,
    syncPortfoliosFromSources,
    refreshFromSources,
    loadPersisted,
    persistRows,
  }
}
