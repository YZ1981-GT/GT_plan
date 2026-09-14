/**
 * useG13Detail — G13-2 明细表（动态行 + 损益审定 + 对应科目FV勾稽）
 * 对齐致同模板：成本 + 累计FV = 公允价值；计入损益 ↔ 审定数；FV变动 ↔ 审定数
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { G13_BELONG_ACCOUNTS, G13_BELONG_ACCOUNT_LABELS, mapBelongToAdjRow, G13_SOURCE_INDEX_BY_BELONG, detailRowMatchesCategory } from './g13Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcFVChange,
  calcSubtotal,
  isFvReconciled,
  calcFairValueFromParts,
  isBsFvReconciled,
  isPlReconciled,
} from './useG13FormulaEngine'
import {
  buildG13CategorySkeleton,
  buildG13CategoryTotalRow,
  aggregateDesignatedOfWhich,
} from './g13CategorySkeleton'
import { fetchG13SourcePullSeeds, mergeG13SourceSeeds } from './g13SourceDetailPull'
import type { ChecklistResponse } from './useF1FormData'

export type G13CrossVerification = 'consistent' | 'inconsistent' | 'pending'

export interface G13DetailRow {
  rowId: string
  seq: number
  instrumentName: string
  belongAccount: string
  instrumentType: string
  openingFairValue: number
  closingFairValue: number
  fvChange: number
  currentUnadjusted: number
  adjustment: number
  currentAudited: number
  /** 对应科目 — 成本 */
  cost: number
  /** 对应科目 — 本期公允价值变动（未填时回退为期末−期初） */
  periodFvChange: number
  /** 对应科目 — 累计公允价值变动 */
  cumulativeFvChange: number
  /** 对应科目 — 公允价值（未填时回退为 成本+累计） */
  fairValue: number
  /** 对应科目 — 计入损益（未填时回退为本期FV变动） */
  amountInPl: number
  sourceIndex: string
  crossVerification: G13CrossVerification
  remark: string
  /** FV变动(期末−期初) ↔ 审定数 */
  fvReconciled: boolean
  /** 成本 + 累计FV = 公允价值 */
  bsReconciled: boolean
  /** 计入损益 ↔ 审定数 */
  plReconciled: boolean
  /** 三项勾稽均通过 */
  allReconciled: boolean
}

const ITEM_ID_ROWS = 'G13-detail-rows'

function generateRowId(): string {
  return `g13d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function enrichRow(raw: Partial<G13DetailRow> & { rowId: string }): G13DetailRow {
  const openingFairValue = parseNum(raw.openingFairValue)
  const closingFairValue = parseNum(raw.closingFairValue)
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const adjustment = parseNum(raw.adjustment)
  const fvChange = calcFVChange(openingFairValue, closingFairValue)
  const currentAudited = calcAdjustedAmount(currentUnadjusted, adjustment)

  const cost = parseNum(raw.cost)
  // 显式填 0 保留 0；未存字段时回退为期末−期初
  const periodFvResolved = raw.periodFvChange === undefined || raw.periodFvChange === null
    ? fvChange
    : parseNum(raw.periodFvChange)

  const cumulativeFvChange = parseNum(raw.cumulativeFvChange)
  const fairValueExplicit = raw.fairValue !== undefined && raw.fairValue !== null
  // 未存公允价值：有成本/累计则用恒等式，否则回退期末 FV（仅展示，不强制 BS 勾稽）
  const fairValue = fairValueExplicit
    ? parseNum(raw.fairValue)
    : (cost !== 0 || cumulativeFvChange !== 0
      ? calcFairValueFromParts(cost, cumulativeFvChange)
      : closingFairValue)

  const amountInPlExplicit = raw.amountInPl !== undefined && raw.amountInPl !== null
  const amountInPl = amountInPlExplicit ? parseNum(raw.amountInPl) : periodFvResolved

  // 仅在对应侧已填时才校验，避免旧数据/空行误红
  const bsSideFilled = cost !== 0 || cumulativeFvChange !== 0 || fairValueExplicit
  const bsReconciled = !bsSideFilled || isBsFvReconciled(cost, cumulativeFvChange, fairValue)

  const plSideFilled = amountInPlExplicit || currentAudited !== 0 || periodFvResolved !== 0
  const plReconciled = !plSideFilled || isPlReconciled(amountInPl, currentAudited)

  const fvSideFilled = fvChange !== 0 || currentAudited !== 0
  const fvReconciled = !fvSideFilled || isFvReconciled(fvChange, currentAudited)

  const allReconciled = fvReconciled && bsReconciled && plReconciled

  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    instrumentName: raw.instrumentName ?? '',
    belongAccount: raw.belongAccount ?? '',
    instrumentType: raw.instrumentType ?? '',
    openingFairValue,
    closingFairValue,
    fvChange,
    currentUnadjusted,
    adjustment,
    currentAudited,
    cost,
    periodFvChange: periodFvResolved,
    cumulativeFvChange,
    fairValue,
    amountInPl,
    sourceIndex: raw.sourceIndex ?? '',
    crossVerification: (raw.crossVerification as G13CrossVerification) ?? 'pending',
    remark: raw.remark ?? '',
    fvReconciled,
    bsReconciled,
    plReconciled,
    allReconciled,
  }
}

export function createEmptyG13DetailRow(seq: number): G13DetailRow {
  return enrichRow({ rowId: generateRowId(), seq, instrumentName: '' })
}

function parseStoredRows(json: string | null | undefined): G13DetailRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => enrichRow({ ...r, rowId: r.rowId || generateRowId(), seq: r.seq ?? i + 1 }))
  } catch {
    return []
  }
}

export interface UseG13DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}

export function useG13Detail(options: UseG13DetailOptions) {
  const rows = ref<G13DetailRow[]>([])
  const searchQuery = ref('')

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseStoredRows(json) },
    { immediate: true },
  )

  function persist(): void {
    const payload = rows.value.map((r) => ({
      rowId: r.rowId,
      seq: r.seq,
      instrumentName: r.instrumentName,
      belongAccount: r.belongAccount,
      instrumentType: r.instrumentType,
      openingFairValue: r.openingFairValue,
      closingFairValue: r.closingFairValue,
      currentUnadjusted: r.currentUnadjusted,
      adjustment: r.adjustment,
      cost: r.cost,
      periodFvChange: r.periodFvChange,
      cumulativeFvChange: r.cumulativeFvChange,
      fairValue: r.fairValue,
      amountInPl: r.amountInPl,
      sourceIndex: r.sourceIndex,
      crossVerification: r.crossVerification,
      remark: r.remark,
    }))
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(payload) })
    window.dispatchEvent(new CustomEvent('g13:detail-updated'))
  }

  function updateCell(rowId: string, field: keyof G13DetailRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const raw = { ...rows.value[idx], [field]: value } as Partial<G13DetailRow> & { rowId: string }
    if (field === 'belongAccount' && typeof value === 'string') {
      if (!raw.sourceIndex && G13_SOURCE_INDEX_BY_BELONG[value]) {
        raw.sourceIndex = G13_SOURCE_INDEX_BY_BELONG[value]
      }
    }
    // 改成本/累计且公允价值仍等于旧派生值时，自动重算公允价值
    if (field === 'cost' || field === 'cumulativeFvChange') {
      const prev = rows.value[idx]
      const oldDerived = calcFairValueFromParts(prev.cost, prev.cumulativeFvChange)
      if (Math.abs(prev.fairValue - oldDerived) <= 0.01) {
        const nextCost = field === 'cost' ? parseNum(value) : prev.cost
        const nextCum = field === 'cumulativeFvChange' ? parseNum(value) : prev.cumulativeFvChange
        raw.fairValue = calcFairValueFromParts(nextCost, nextCum)
      }
    }
    // 改本期FV且计入损益仍等于旧本期FV时，同步计入损益
    if (field === 'periodFvChange') {
      const prev = rows.value[idx]
      if (Math.abs(prev.amountInPl - prev.periodFvChange) <= 0.01) {
        raw.amountInPl = parseNum(value)
      }
    }
    const next = [...rows.value]
    next[idx] = enrichRow(raw)
    rows.value = next
    persist()
  }

  async function addRow(): Promise<void> {
    if (options.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入金融工具名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, enrichRow({ rowId: generateRowId(), seq, instrumentName: value ?? '' })]
      persist()
    } catch { /* cancelled */ }
  }

  /**
   * 按所属科目确保存在可回写的明细行（G13-3 确认调整时调用，无匹配行则自动占位）
   */
  function ensureBelongRow(belongAccount: string, instrumentName?: string): G13DetailRow {
    const match = rows.value.find((r) => {
      if (belongAccount === 'other' || !belongAccount) {
        return !r.belongAccount || r.belongAccount === 'other'
      }
      return r.belongAccount === belongAccount
    })
    if (match) return match

    const label = belongAccount
      ? (G13_BELONG_ACCOUNT_LABELS[belongAccount] ?? belongAccount)
      : '其他'
    const seq = rows.value.length + 1
    const row = enrichRow({
      rowId: generateRowId(),
      seq,
      instrumentName: instrumentName || `${label}（G13-3 回写占位）`,
      belongAccount: belongAccount === 'other' ? '' : belongAccount,
      sourceIndex: belongAccount && G13_SOURCE_INDEX_BY_BELONG[belongAccount]
        ? G13_SOURCE_INDEX_BY_BELONG[belongAccount]
        : '',
    })
    rows.value = [...rows.value, row]
    persist()
    return row
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichRow({ ...r, seq: i + 1 }))
    persist()
  }

  const dataRows = computed(() => rows.value)

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter((r) => {
      const belongLabel = G13_BELONG_ACCOUNT_LABELS[r.belongAccount] ?? r.belongAccount
      return (
        r.instrumentName.toLowerCase().includes(q)
        || r.instrumentType.toLowerCase().includes(q)
        || belongLabel.toLowerCase().includes(q)
        || r.sourceIndex.toLowerCase().includes(q)
      )
    })
  })

  const groupSubtotals = computed(() => {
    const groups: Record<string, {
      label: string
      currentAudited: number
      fvChange: number
      amountInPl: number
      fairValue: number
    }> = {}
    for (const acct of G13_BELONG_ACCOUNTS) {
      groups[acct] = {
        label: G13_BELONG_ACCOUNT_LABELS[acct] ?? `${acct} 小计`,
        currentAudited: 0,
        fvChange: 0,
        amountInPl: 0,
        fairValue: 0,
      }
    }
    groups.other = { label: '其他', currentAudited: 0, fvChange: 0, amountInPl: 0, fairValue: 0 }
    for (const r of rows.value) {
      const key = G13_BELONG_ACCOUNTS.includes(r.belongAccount as any) ? r.belongAccount : 'other'
      groups[key].currentAudited += r.currentAudited
      groups[key].fvChange += r.fvChange
      groups[key].amountInPl += r.amountInPl
      groups[key].fairValue += r.fairValue
    }
    return groups
  })

  const totalRow = computed((): G13DetailRow => {
    const r = rows.value
    const currentUnadjusted = calcSubtotal(r.map((x) => x.currentUnadjusted))
    const adjustment = calcSubtotal(r.map((x) => x.adjustment))
    const currentAudited = calcSubtotal(r.map((x) => x.currentAudited))
    const fvChange = calcSubtotal(r.map((x) => x.fvChange))
    const cost = calcSubtotal(r.map((x) => x.cost))
    const periodFvChange = calcSubtotal(r.map((x) => x.periodFvChange))
    const cumulativeFvChange = calcSubtotal(r.map((x) => x.cumulativeFvChange))
    const fairValue = calcSubtotal(r.map((x) => x.fairValue))
    const amountInPl = calcSubtotal(r.map((x) => x.amountInPl))
    const openingFairValue = calcSubtotal(r.map((x) => x.openingFairValue))
    const closingFairValue = calcSubtotal(r.map((x) => x.closingFairValue))
    return enrichRow({
      rowId: 'total',
      seq: 0,
      instrumentName: '合计',
      currentUnadjusted,
      adjustment,
      currentAudited,
      fvChange,
      cost,
      periodFvChange,
      cumulativeFvChange,
      fairValue,
      amountInPl,
      openingFairValue,
      closingFairValue,
    })
  })

  const grandTotalAudited = computed(() => totalRow.value.currentAudited)
  const hasFvMismatch = computed(() => rows.value.some((r) => !r.allReconciled))
  const mismatchSummary = computed(() => {
    const fv = rows.value.filter((r) => !r.fvReconciled).length
    const bs = rows.value.filter((r) => !r.bsReconciled).length
    const pl = rows.value.filter((r) => !r.plReconciled).length
    const parts: string[] = []
    if (fv) parts.push(`FV变动↔审定 ${fv} 行`)
    if (bs) parts.push(`成本+累计≠公允价值 ${bs} 行`)
    if (pl) parts.push(`计入损益↔审定 ${pl} 行`)
    return parts.join('；')
  })

  function aggregateByAdjRowKey(): Record<string, { unadjusted: number; adjustment: number; audited: number }> {
    const acc: Record<string, { unadjusted: number; adjustment: number; audited: number }> = {}
    for (const r of rows.value) {
      const key = mapBelongToAdjRow(r.belongAccount, r.instrumentType)
      if (!acc[key]) acc[key] = { unadjusted: 0, adjustment: 0, audited: 0 }
      acc[key].unadjusted += r.currentUnadjusted
      acc[key].adjustment += r.adjustment
      acc[key].audited += r.currentAudited
    }
    return acc
  }

  const categoryRows = computed(() => buildG13CategorySkeleton(rows.value))
  const categoryTotalRow = computed(() => buildG13CategoryTotalRow(categoryRows.value))
  const categoryDisplayRows = computed(() => [...categoryRows.value, categoryTotalRow.value])

  const designatedOfWhichAgg = computed(() => aggregateDesignatedOfWhich(rows.value))

  const ITEM_ID_PRIOR = 'G13-adj-prior'

  /** 将指定类明细汇总写入 G13-1「其中」备忘行（不计入合计） */
  function syncDesignatedOfWhich(opts?: { silent?: boolean }): number {
    if (options.isReadonly.value) return 0
    const agg = designatedOfWhichAgg.value
    const keys = Object.keys(agg)
    if (!keys.length) {
      if (!opts?.silent) ElMessage.info('明细中暂无「指定FVTPL」类工具（类型/备注含「指定」）')
      return 0
    }
    let prior: Record<string, Record<string, unknown>> = {}
    try {
      const raw = options.allResponses.value.get(ITEM_ID_PRIOR)?.remark
      if (raw) prior = JSON.parse(raw)
    } catch { prior = {} }
    for (const [key, v] of Object.entries(agg)) {
      prior[key] = {
        ...(prior[key] ?? {}),
        currentUnadjusted: v.unadjusted,
        currentAdjustment: v.adjustment,
      }
    }
    options.debouncedSave(ITEM_ID_PRIOR, { remark: JSON.stringify(prior) })
    if (!opts?.silent) ElMessage.success(`已同步 ${keys.length} 条「其中：指定」备忘行至 G13-1`)
    return keys.length
  }

  const pullLoading = ref(false)

  /** 从同项目 G1/G8/G9/G10/H3 明细带入成本/累计FV/计入损益 */
  async function pullFromSourceDetails(projectId: string): Promise<void> {
    if (options.isReadonly.value || !projectId) return
    pullLoading.value = true
    try {
      const { seeds, bySource, missing } = await fetchG13SourcePullSeeds(projectId)
      if (!seeds.length) {
        ElMessage.warning(
          missing.length
            ? `未取到源明细（缺底稿：${missing.join('、')}）`
            : '源科目明细为空，请先编制 G1-2 / G8-2 / G9-2 / G10-2 / H3-2',
        )
        return
      }
      if (rows.value.length) {
        try {
          await ElMessageBox.confirm(
            `将合并 ${seeds.length} 条源明细（空字段才覆盖，并自动交叉验证）。按来源：${Object.entries(bySource).map(([k, n]) => `${k}:${n}`).join('，')}`,
            '从源科目带入',
            { confirmButtonText: '合并带入', cancelButtonText: '取消', type: 'info' },
          )
        } catch {
          return
        }
      }
      const result = mergeG13SourceSeeds(rows.value, seeds, enrichRow, generateRowId, { markCrossVerification: true })
      rows.value = result.rows
      persist()

      const touched = result.rows.filter((r) => result.touchedRowIds.includes(r.rowId))
      const consistent = touched.filter((r) => r.crossVerification === 'consistent').length
      const inconsistent = touched.filter((r) => r.crossVerification === 'inconsistent').length
      const designatedN = syncDesignatedOfWhich({ silent: true })

      const missHint = missing.length ? `；未找到底稿 ${missing.join('、')}` : ''
      const verifyHint = `；交叉验证 一致${consistent}/不符${inconsistent}`
      const ofWhichHint = designatedN ? `；已同步「其中」${designatedN} 行` : ''
      ElMessage.success(`带入完成：新增 ${result.added}、更新 ${result.updated}${verifyHint}${ofWhichHint}${missHint}`)
    } catch (e: any) {
      ElMessage.error(e?.message || '源科目带入失败')
    } finally {
      pullLoading.value = false
    }
  }

  /** 按分类骨架 rowKey 筛选工具明细 */
  function rowsMatchingCategory(categoryRowKey: string): G13DetailRow[] {
    if (!categoryRowKey || categoryRowKey === 'total') return rows.value
    return rows.value.filter((r) => detailRowMatchesCategory(r, categoryRowKey))
  }

  return {
    rows: dataRows,
    filteredRows,
    searchQuery,
    totalRow,
    groupSubtotals,
    grandTotalAudited,
    hasFvMismatch,
    mismatchSummary,
    categoryRows,
    categoryTotalRow,
    categoryDisplayRows,
    designatedOfWhichAgg,
    syncDesignatedOfWhich,
    pullFromSourceDetails,
    pullLoading,
    rowsMatchingCategory,
    updateCell,
    addRow,
    ensureBelongRow,
    removeRow,
    persist,
    aggregateByAdjRowKey,
    ITEM_ID_ROWS,
    G13_BELONG_ACCOUNTS,
  }
}
