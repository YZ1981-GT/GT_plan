/**
 * useG10Detail — G10-2 明细表（对齐 Excel：类别/项目 + 期初·变动·期末三段 roll-forward）
 *
 * 编制逻辑：
 * 1. 期初/期末均分解为 (一)初始确认 + (二)累计公允价值变动 = (三)公允价值；审定 = 公允价值 + 调整
 * 2. 本期变动：初始确认、公允价值变动、计入财务费用利息、减少（清偿/终止）
 * 3. 期末余额 roll-forward = 期初审定 + 变动 − 减少；与 (一)+(二) 分解勾稽
 * 4. 可按负债类型汇总回写 G10-1 各分项未审数
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  G10_LIABILITY_TYPE_OPTIONS,
  G10_LIABILITY_CATEGORY_OPTIONS,
  G10_FV_LEVEL_OPTIONS,
  G10_VALUATION_METHOD_OPTIONS,
  G10_CONFIRMATION_OPTIONS,
} from './g10Constants'
import {
  pushG10DetailToAdjudication,
  calcBookSectionTotal,
  G10_ADJ_ROWS_KEY,
  fetchG10AuxLiabilitySeeds,
  seedG10DetailRowFromAux,
} from './g10CrossHelpers'
import {
  isG10DerivativeDetailRow,
  parseG10DerivativeDetailLinks,
  G10_DERIVATIVE_DETAIL_LINKS_KEY,
} from './g10DerivativeCross'
import {
  buildG10DetailProcedureSummary,
  G10A_DETAIL_MARK_KEY,
  G10A_DETAIL_PROGRAM_NOS,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'
import { parseG10AdjStore } from './g10AdjStorage'
import { offerG10DisclosurePull } from './g10DisclosureSync'
import { pullG10DetailFromAdjudicationResponses } from './g10DetailFromAdjudication'
import { matchG10LiabilityKey } from './g10AccountMatch'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
import {
  parseNum,
  calcAdjustedAmount,
  calcSubtotal,
  calcBookFromParts,
  calcG10DetailClosingBalance,
} from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G10DetailRow {
  rowId: string
  seq: number
  /** 类别：指定类 / 交易类 */
  liabilityCategory: string
  liabilityName: string
  liabilityType: string
  counterparty: string
  contractDate: string
  maturityDate: string
  couponRate: string
  accruedInterest: number
  issuanceDocIndex: string
  /** 期初 — (一)初始确认金额 */
  openingInitialAmount: number
  /** 期初 — (二)累计公允价值变动 */
  openingFvAccum: number
  /** 期初 — (三)公允价值 */
  openingFairValue: number
  openingAdjustment: number
  openingAdjusted: number
  /** 本期变动 */
  movementInitialAmount: number
  movementFvChange: number
  interestExpense: number
  currentDecrease: number
  /** 期末 — (一)(二)(三)分解 */
  closingInitialAmount: number
  closingFvAccum: number
  closingFairValue: number
  closingBalance: number
  closingAdjustment: number
  closingAdjusted: number
  /** 兼容/辅助 */
  initialAmount: number
  openingBalance: number
  currentIncrease: number
  fairValueLevel: string
  valuationMethod: string
  profitLossAmount: number
  isDerivative: boolean
  hostContractDesc: string
  embeddedDerivativeJudgment: string
  confirmationStatus: string
  remark: string
}

export interface G10DetailRowIssue {
  rowId: string
  liabilityName: string
  field: string
  message: string
  variance?: number
}

const ITEM_ID_ROWS = 'G10-detail-rows'
const DIFF_TOLERANCE = 0.01

function genId(): string {
  return `g10d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function enrichG10DetailRow(raw: Partial<G10DetailRow> & { rowId: string }, seq: number): G10DetailRow {
  const openingInitialAmount = parseNum(raw.openingInitialAmount ?? raw.initialAmount)
  const openingBalanceLegacy = parseNum(raw.openingBalance)
  let openingFvAccum: number
  if (raw.openingFvAccum != null && String(raw.openingFvAccum).trim() !== '') {
    openingFvAccum = parseNum(raw.openingFvAccum)
  } else if (raw.openingBalance != null && String(raw.openingBalance).trim() !== '') {
    openingFvAccum = openingBalanceLegacy - openingInitialAmount
  } else {
    openingFvAccum = 0
  }
  const openingFairValue = calcBookFromParts(openingInitialAmount, openingFvAccum)
  let openingAdjustment = parseNum(raw.openingAdjustment)
  if (!raw.openingAdjustment && raw.openingAdjusted != null && Math.abs(openingBalanceLegacy) > 0.005) {
    openingAdjustment = parseNum(raw.openingAdjusted) - openingFairValue
  }
  const openingAdjusted = calcAdjustedAmount(openingFairValue, openingAdjustment)

  const movementInitialAmount = parseNum(raw.movementInitialAmount ?? raw.currentIncrease)
  const movementFvChange = parseNum(raw.movementFvChange ?? raw.profitLossAmount)
  const interestExpense = parseNum(raw.interestExpense)
  const currentDecrease = parseNum(raw.currentDecrease)

  const closingInitialAmount = openingInitialAmount + movementInitialAmount
  const closingFvAccum = openingFvAccum + movementFvChange
  const closingFairValue = calcBookFromParts(closingInitialAmount, closingFvAccum)
  const closingBalance = calcG10DetailClosingBalance(
    openingAdjusted,
    movementInitialAmount,
    movementFvChange,
    interestExpense,
    currentDecrease,
  )
  const closingAdjustment = parseNum(raw.closingAdjustment)
  const closingAdjusted = calcAdjustedAmount(closingBalance, closingAdjustment)

  return {
    rowId: raw.rowId,
    seq,
    liabilityCategory: raw.liabilityCategory ?? G10_LIABILITY_CATEGORY_OPTIONS[0],
    liabilityName: raw.liabilityName ?? '',
    liabilityType: raw.liabilityType ?? G10_LIABILITY_TYPE_OPTIONS[0],
    counterparty: raw.counterparty ?? '',
    contractDate: raw.contractDate ?? '',
    maturityDate: raw.maturityDate ?? '',
    couponRate: raw.couponRate ?? '',
    accruedInterest: parseNum(raw.accruedInterest),
    issuanceDocIndex: raw.issuanceDocIndex ?? '',
    openingInitialAmount,
    openingFvAccum,
    openingFairValue,
    openingAdjustment,
    openingAdjusted,
    movementInitialAmount,
    movementFvChange,
    interestExpense,
    currentDecrease,
    closingInitialAmount,
    closingFvAccum,
    closingFairValue,
    closingBalance,
    closingAdjustment,
    closingAdjusted,
    initialAmount: closingInitialAmount,
    openingBalance: openingFairValue,
    currentIncrease: movementInitialAmount,
    fairValueLevel: raw.fairValueLevel ?? 'Level2',
    valuationMethod: raw.valuationMethod ?? '',
    profitLossAmount: movementFvChange,
    isDerivative: !!raw.isDerivative,
    hostContractDesc: raw.hostContractDesc ?? '',
    embeddedDerivativeJudgment: raw.embeddedDerivativeJudgment ?? '',
    confirmationStatus: raw.confirmationStatus ?? '',
    remark: raw.remark ?? '',
  }
}

export function scanG10DetailIntegrity(rows: G10DetailRow[]): G10DetailRowIssue[] {
  const issues: G10DetailRowIssue[] = []
  for (const r of rows) {
    const name = r.liabilityName?.trim() || `第${r.seq}行`
    if (!r.liabilityName?.trim() && Math.abs(r.closingAdjusted) > DIFF_TOLERANCE) {
      issues.push({ rowId: r.rowId, liabilityName: name, field: 'liabilityName', message: '有审定余额但项目名称为空' })
    }
    if (r.fairValueLevel === 'Level3' && !r.valuationMethod?.trim()) {
      issues.push({ rowId: r.rowId, liabilityName: name, field: 'valuationMethod', message: 'Level3 须填估值方法' })
    }
    const openDecompDiff = r.openingFairValue - calcBookFromParts(r.openingInitialAmount, r.openingFvAccum)
    if (Math.abs(openDecompDiff) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'openingFairValue',
        message: '期初 (一)+(二) ≠ (三)公允价值',
        variance: openDecompDiff,
      })
    }
    const closeDecompDiff = r.closingFairValue - calcBookFromParts(r.closingInitialAmount, r.closingFvAccum)
    if (Math.abs(closeDecompDiff) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'closingFairValue',
        message: '期末 (一)+(二) ≠ (三)公允价值',
        variance: closeDecompDiff,
      })
    }
    const rollDiff = r.closingBalance - r.closingFairValue
    if (Math.abs(rollDiff) > DIFF_TOLERANCE && Math.abs(r.closingBalance) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'closingBalance',
        message: 'roll-forward 期末余额与 (一)+(二) 分解不一致（请核对本期减少/利息拆分）',
        variance: rollDiff,
      })
    }
    if (
      Math.abs(r.movementFvChange) > DIFF_TOLERANCE
      && Math.abs(r.profitLossAmount - r.movementFvChange) > DIFF_TOLERANCE
    ) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'movementFvChange',
        message: '本期 FV 变动与计入损益金额应一致（FVTPL）',
        variance: r.profitLossAmount - r.movementFvChange,
      })
    }
  }
  return issues
}

function parseRows(json: string | null | undefined): G10DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG10DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1))
  } catch {
    return []
  }
}

export function useG10Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const auditYearRef = useWorkpaperAuditYear()
  const rows = ref<G10DetailRow[]>([])
  const activeTab = ref<'basic' | 'movement' | 'closing'>('basic')
  const activeRowIndex = ref(0)
  const auxLoading = ref(false)
  const procedureMarking = ref(false)

  const FV_ROWS_KEY = 'G10-fv-test-rows'

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  const currentRowKey = computed(() => rows.value[activeRowIndex.value]?.rowId ?? '')

  const totals = computed(() => ({
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    movementInitialAmount: calcSubtotal(rows.value.map((r) => r.movementInitialAmount)),
    movementFvChange: calcSubtotal(rows.value.map((r) => r.movementFvChange)),
    interestExpense: calcSubtotal(rows.value.map((r) => r.interestExpense)),
    currentDecrease: calcSubtotal(rows.value.map((r) => r.currentDecrease)),
    closingBalance: calcSubtotal(rows.value.map((r) => r.closingBalance)),
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
  }))

  const typeSubtotals = computed(() => {
    const result: Record<string, number> = {}
    for (const t of G10_LIABILITY_TYPE_OPTIONS) {
      result[t] = calcSubtotal(rows.value.filter((r) => r.liabilityType === t).map((r) => r.closingAdjusted))
    }
    result['总计'] = totals.value.closingAdjusted
    return result
  })

  const adjudicationClosingTotal = computed(() => {
    const store = parseG10AdjStore(opts.allResponses.value.get(G10_ADJ_ROWS_KEY)?.remark)
    const total = calcBookSectionTotal(store)
    return total > 0.005 || Object.keys(store).length > 0 ? total : null
  })

  const adjCrossVariance = computed(() => {
    if (adjudicationClosingTotal.value == null || !rows.value.length) return null
    return totals.value.closingAdjusted - adjudicationClosingTotal.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )

  const integrityIssues = computed(() => scanG10DetailIntegrity(rows.value))

  const level3MissingMethodCount = computed(() =>
    integrityIssues.value.filter((i) => i.field === 'valuationMethod').length,
  )

  /** G10-2 行 → G10-5 匹配（按项目名称） */
  const fvLinkByRowId = computed(() => {
    const map = new Map<string, { fvRowId: string; variance: number }>()
    let fvRows: any[] = []
    try {
      const json = opts.allResponses.value.get(FV_ROWS_KEY)?.remark
      if (json) fvRows = JSON.parse(json)
    } catch { /* silent */ }
    if (!Array.isArray(fvRows)) return map
    const fvByKey = new Map(
      fvRows
        .filter((r) => String(r.liabilityName ?? '').trim())
        .map((r) => [matchG10LiabilityKey(String(r.liabilityName)), r]),
    )
    for (const row of rows.value) {
      const fv = fvByKey.get(matchG10LiabilityKey(row.liabilityName))
      if (!fv) continue
      map.set(row.rowId, {
        fvRowId: String(fv.rowId ?? ''),
        variance: row.closingAdjusted - parseNum(fv.closingAuditedFV),
      })
    }
    return map
  })

  const unmatchedFvDetailCount = computed(() =>
    rows.value.filter((r) => r.liabilityName.trim() && !fvLinkByRowId.value.has(r.rowId)).length,
  )

  /** G10-2 衍生行 → G10-8 链接（链接清单或备注含 G10-8） */
  const derivativeLinkByRowId = computed(() => {
    const map = new Map<string, { linked: boolean; viaG108: boolean }>()
    const links = parseG10DerivativeDetailLinks(
      opts.allResponses.value.get(G10_DERIVATIVE_DETAIL_LINKS_KEY)?.remark,
    )
    const linkedIds = new Set(links.map((l) => l.detailRowId))
    for (const row of rows.value) {
      if (!isG10DerivativeDetailRow(row)) continue
      const viaG108 = linkedIds.has(row.rowId)
        || String(row.embeddedDerivativeJudgment ?? '').includes('G10-8')
        || String(row.remark ?? '').includes('G10-8')
      map.set(row.rowId, { linked: viaG108, viaG108 })
    }
    return map
  })

  const derivativeDetailCount = computed(() =>
    rows.value.filter((r) => isG10DerivativeDetailRow(r)).length,
  )

  const unmatchedDerivativeDetailCount = computed(() =>
    rows.value.filter((r) =>
      isG10DerivativeDetailRow(r) && !derivativeLinkByRowId.value.get(r.rowId)?.linked,
    ).length,
  )

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_DETAIL_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_DETAIL_MARK_KEY)?.conclusion === 'completed',
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    try {
      window.dispatchEvent(new CustomEvent('g10:detail-updated'))
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<G10DetailRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r, i) =>
      r.rowId === rowId ? enrichG10DetailRow({ ...r, ...patch, rowId }, i + 1) : r,
    )
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入负债项目名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：短期融资券',
      })
      if (!value?.trim()) return
      rows.value = [
        ...rows.value,
        enrichG10DetailRow({ rowId: genId(), liabilityName: value.trim() }, rows.value.length + 1),
      ]
      persist()
    } catch { /* cancelled */ }
  }

  async function removeRow(rowId: string): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await ElMessageBox.confirm('确认删除该明细行？', '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      rows.value = rows.value
        .filter((r) => r.rowId !== rowId)
        .map((r, i) => enrichG10DetailRow(r, i + 1))
      if (activeRowIndex.value >= rows.value.length) {
        activeRowIndex.value = Math.max(0, rows.value.length - 1)
      }
      persist()
    } catch { /* cancelled */ }
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  function setActiveRowIndex(index: number): void {
    activeRowIndex.value = index
  }

  const totalRow = computed(() => totals.value)

  function pushTotalsToAdjudication(): void {
    if (opts.isReadonly.value || !rows.value.length) return
    void (async () => {
      const n = pushG10DetailToAdjudication(
        opts.allResponses.value,
        opts.debouncedSave,
        rows.value,
      )
      if (n <= 0) {
        ElMessage.warning('无可回写的明细合计')
        return
      }
      ElMessage.success(`已按分项回写 G10-1 ${n} 组（(一)(二)(三)）`)
      await offerG10DisclosurePull(
        opts.allResponses.value,
        opts.debouncedSave,
        auditYearRef.value,
        'G10-1 审定表已更新。是否同步更新附注披露（上市/国企）分项金额？',
      )
    })()
  }

  async function pullFromAdjudication(): Promise<void> {
    if (opts.isReadonly.value) return
    let mode: 'fill-empty' | 'overwrite' = 'fill-empty'
    const hasExisting = rows.value.some(
      (r) => r.liabilityName.trim() && Math.abs(r.closingFairValue) > 0.005,
    )
    if (hasExisting) {
      try {
        await ElMessageBox.confirm(
          '已有明细数据。选择「覆盖同类别」将按 G10-1 分项更新匹配行的期初/期末分解；「仅填空行」保留已有项目金额。',
          '从 G10-1 带入',
          {
            type: 'info',
            confirmButtonText: '覆盖同类别',
            cancelButtonText: '仅填空行',
            distinguishCancelAndClose: true,
          },
        )
        mode = 'overwrite'
      } catch (action) {
        if (action !== 'cancel') return
      }
    }

    const result = pullG10DetailFromAdjudicationResponses(
      opts.allResponses.value,
      rows.value,
      genId,
      mode,
    )
    if (result.filled <= 0) {
      ElMessage.warning('G10-1 无可带入的分项金额（请先编制审定表 (三) 账面余额分项）')
      return
    }
    rows.value = result.rows
    persist()
    ElMessage.success(
      `已从 G10-1 带入 ${result.filled} 个分项（新增 ${result.added} 行，更新 ${result.updated} 行）`,
    )
  }

  async function seedAuxAndPushToAdjudication(): Promise<void> {
    if (opts.isReadonly.value) return
    const r = await seedFromAuxBalance()
    if (r.error || (r.added === 0 && r.updated === 0)) return
    if (!rows.value.length) {
      ElMessage.warning('取数后仍无明细行，无法回写 G10-1')
      return
    }
    pushTotalsToAdjudication()
  }

  async function seedFromAuxBalance(): Promise<{ added: number; updated: number; dimType: string; error?: string }> {
    if (opts.isReadonly.value) return { added: 0, updated: 0, dimType: '', error: '只读' }
    const projectId = opts.projectId?.value ?? ''
    if (!projectId) return { added: 0, updated: 0, dimType: '', error: '缺少项目 ID' }
    auxLoading.value = true
    try {
      const { seeds, dimType, error } = await fetchG10AuxLiabilitySeeds(projectId)
      if (error || !seeds.length) {
        ElMessage.warning(error || '无辅助核算数据')
        return { added: 0, updated: 0, dimType, error: error || '无数据' }
      }
      const byName = new Map(
        rows.value.filter((r) => r.liabilityName.trim()).map((r) => [matchG10LiabilityKey(r.liabilityName), r]),
      )
      let added = 0
      let updated = 0
      const next: G10DetailRow[] = []
      let seq = 1
      for (const seed of seeds) {
        const key = matchG10LiabilityKey(seed.liabilityName)
        const prev = byName.get(key)
        if (prev) {
          updated += 1
          next.push(seedG10DetailRowFromAux(seed, seq++, prev))
          byName.delete(key)
        } else {
          added += 1
          next.push(seedG10DetailRowFromAux(seed, seq++))
        }
      }
      for (const r of rows.value) {
        if (!byName.has(matchG10LiabilityKey(r.liabilityName))) continue
        next.push(enrichG10DetailRow(r, seq++))
      }
      rows.value = next
      persist()
      ElMessage.success(`辅助核算取数完成：新增 ${added} 行，更新 ${updated} 行（维度：${dimType}）`)
      return { added, updated, dimType }
    } finally {
      auxLoading.value = false
    }
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (!rows.value.length) {
      ElMessage.warning('请先编制 G10-2 明细表')
      return -1
    }
    if (integrityIssues.value.length) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${integrityIssues.value.length} 项校验未通过，是否仍标记 G10A 明细程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG10DetailProcedureSummary({
        rowCount: rows.value.length,
        closingAdjustedTotal: totals.value.closingAdjusted,
        integrityErrors: integrityIssues.value.length,
        derivativeCount: derivativeDetailCount.value,
        linkedG10A: !hasAdjCrossMismatch.value && adjudicationClosingTotal.value != null,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        programNos: [...G10A_DETAIL_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-2/G10-1',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_DETAIL_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G10A_DETAIL_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_DETAIL_PROGRAM_NOS].join('/')}（明细编制）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    currentRowKey,
    totalRow,
    totals,
    typeSubtotals,
    adjudicationClosingTotal,
    adjCrossVariance,
    hasAdjCrossMismatch,
    integrityIssues,
    level3MissingMethodCount,
    fvLinkByRowId,
    unmatchedFvDetailCount,
    derivativeLinkByRowId,
    derivativeDetailCount,
    unmatchedDerivativeDetailCount,
    auxLoading,
    procedureMarking,
    procedureMarked,
    G10_LIABILITY_TYPE_OPTIONS,
    G10_LIABILITY_CATEGORY_OPTIONS,
    G10_FV_LEVEL_OPTIONS,
    G10_VALUATION_METHOD_OPTIONS,
    G10_CONFIRMATION_OPTIONS,
    updateRow,
    addRow,
    removeRow,
    reloadFromStore,
    setActiveRowIndex,
    pushTotalsToAdjudication,
    pullFromAdjudication,
    seedFromAuxBalance,
    seedAuxAndPushToAdjudication,
    markProcedureComplete,
    ITEM_ID_ROWS,
  }
}
