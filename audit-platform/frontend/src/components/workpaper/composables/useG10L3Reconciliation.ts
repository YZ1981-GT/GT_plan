/**
 * useG10L3Reconciliation — G10-6 第三层次公允价值调节表（负债方向：新增/终止）
 *
 * 联动：从 G10-2 Level3 明细 / G10-5 Level3 公允测试带入；与 G10-5 合计勾稽
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { parseNum, calcL3Reconciliation, calcSubtotal } from './useG10FormulaEngine'
import { matchG10LiabilityKey } from './g10AccountMatch'
import { G10_DETAIL_ROWS_KEY, G10_FV_DIFF_THRESHOLD, parseG10DetailRows } from './g10CrossHelpers'
import { G10_FV_KEY, G10A_FV_MARK_KEY, G10A_FV_PROGRAM_NOS, isG10AProcedureMarkDone, markG10AProcedureSteps } from './g10FvCrossHelpers'
import {
  buildG10L3ProcedureSummary,
  listG10Fv5VsG96AssetMismatches,
  pushG10L3VarianceToAdjustment,
  selectG10L3VarianceTargets,
} from './g10L3CrossHelpers'
import type { ChecklistResponse } from './useF1FormData'

export interface G10L3Row {
  rowId: string
  seq: number
  liabilityName: string
  openingBalance: number
  currentNew: number
  currentTerminated: number
  transferIntoL3: number
  transferOutOfL3: number
  fairValueChange: number
  interestExpense: number
  otherChanges: number
  closingBalance: number
  reportedClosing: number
  variance: number
  remark: string
}

const ITEM_ID = 'G10-l3-rows'

function genId() { return `g10l3-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}` }

function isLevel3(level: unknown): boolean {
  return String(level ?? '').trim() === 'Level3'
}

export function enrichG10L3Row(raw: Partial<G10L3Row> & { rowId: string }): G10L3Row {
  const opening = parseNum(raw.openingBalance)
  const currentNew = parseNum(raw.currentNew)
  const currentTerminated = parseNum(raw.currentTerminated)
  const transferIntoL3 = parseNum(raw.transferIntoL3)
  const transferOutOfL3 = parseNum(raw.transferOutOfL3)
  const fairValueChange = parseNum(raw.fairValueChange)
  const interestExpense = parseNum(raw.interestExpense)
  const otherChanges = parseNum(raw.otherChanges)
  const closingBalance = calcL3Reconciliation(
    opening, currentNew, currentTerminated,
    transferIntoL3, transferOutOfL3, fairValueChange, interestExpense, otherChanges,
  )
  const reportedClosing = parseNum(raw.reportedClosing ?? raw.closingBalance)
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    liabilityName: raw.liabilityName ?? '',
    openingBalance: opening,
    currentNew,
    currentTerminated,
    transferIntoL3,
    transferOutOfL3,
    fairValueChange,
    interestExpense,
    otherChanges,
    closingBalance,
    reportedClosing,
    variance: reportedClosing - closingBalance,
    remark: raw.remark ?? '',
  }
}

function emptyRow(name: string, seq: number, rowId?: string): G10L3Row {
  return enrichG10L3Row({ rowId: rowId ?? genId(), seq, liabilityName: name })
}

function toPersistable(rows: G10L3Row[]) {
  return rows.map((r, i) => {
    const enriched = enrichG10L3Row({ ...r, seq: i + 1 })
    return {
      rowId: enriched.rowId,
      seq: enriched.seq,
      liabilityName: enriched.liabilityName,
      openingBalance: enriched.openingBalance,
      currentNew: enriched.currentNew,
      currentTerminated: enriched.currentTerminated,
      transferIntoL3: enriched.transferIntoL3,
      transferOutOfL3: enriched.transferOutOfL3,
      fairValueChange: enriched.fairValueChange,
      interestExpense: enriched.interestExpense,
      otherChanges: enriched.otherChanges,
      reportedClosing: enriched.reportedClosing,
      remark: enriched.remark,
    }
  })
}

function parseFvRows(json: string | null | undefined): Array<Record<string, unknown>> {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function useG10L3Reconciliation(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  auditYear?: Ref<number | null | undefined> | ComputedRef<number | null | undefined>
}) {
  const rows = ref<G10L3Row[]>([])
  const procedureMarked = ref(false)

  watch(
    () => [opts.projectId?.value, opts.allResponses.value] as const,
    () => {
      const pid = opts.projectId?.value
      procedureMarked.value = pid
        ? isG10AProcedureMarkDone(opts.allResponses.value, G10A_FV_MARK_KEY)
        : false
    },
    { immediate: true, deep: true },
  )

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    try {
      rows.value = j
        ? JSON.parse(j).map((r: any, i: number) => enrichG10L3Row({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }))
        : []
    } catch { rows.value = [] }
  }, { immediate: true })

  const varianceRows = computed(() => rows.value.filter((r) => Math.abs(r.variance) > G10_FV_DIFF_THRESHOLD))

  const totals = computed(() => ({
    openingBalance: calcSubtotal(rows.value.map((r) => r.openingBalance)),
    currentNew: calcSubtotal(rows.value.map((r) => r.currentNew)),
    currentTerminated: calcSubtotal(rows.value.map((r) => r.currentTerminated)),
    fairValueChange: calcSubtotal(rows.value.map((r) => r.fairValueChange)),
    interestExpense: calcSubtotal(rows.value.map((r) => r.interestExpense)),
    closingBalance: calcSubtotal(rows.value.map((r) => r.closingBalance)),
    reportedClosing: calcSubtotal(rows.value.map((r) => r.reportedClosing)),
    variance: calcSubtotal(rows.value.map((r) => r.variance)),
  }))

  const fvL3AuditedTotal = computed(() => {
    const list = parseFvRows(opts.allResponses.value.get(G10_FV_KEY)?.remark)
    return calcSubtotal(
      list
        .filter((r) => isLevel3(r.fairValueLevel))
        .map((r) => parseNum(r.closingAuditedFV)),
    )
  })

  const fvCrossVariance = computed(() => totals.value.reportedClosing - fvL3AuditedTotal.value)

  const hasFvCrossMismatch = computed(() =>
    rows.value.length > 0
    && fvL3AuditedTotal.value > G10_FV_DIFF_THRESHOLD
    && Math.abs(fvCrossVariance.value) > G10_FV_DIFF_THRESHOLD,
  )

  const assetMismatches = computed(() =>
    listG10Fv5VsG96AssetMismatches(opts.allResponses.value),
  )

  /** G10-6 行 → G10-2 / G10-5 逐行链接状态 */
  const linkByRowId = computed(() => {
    const map = new Map<string, { hasDetail: boolean; hasFv: boolean }>()
    const detailByKey = new Map(
      parseG10DetailRows(opts.allResponses.value.get(G10_DETAIL_ROWS_KEY)?.remark)
        .filter((d) => isLevel3(d.fairValueLevel) && d.liabilityName.trim())
        .map((d) => [matchG10LiabilityKey(d.liabilityName), d]),
    )
    const fvByKey = new Map(
      parseFvRows(opts.allResponses.value.get(G10_FV_KEY)?.remark)
        .filter((r) => isLevel3(r.fairValueLevel) && String(r.liabilityName ?? '').trim())
        .map((r) => [matchG10LiabilityKey(String(r.liabilityName)), r]),
    )
    for (const row of rows.value) {
      const key = matchG10LiabilityKey(row.liabilityName)
      map.set(row.rowId, {
        hasDetail: detailByKey.has(key),
        hasFv: fvByKey.has(key),
      })
    }
    return map
  })

  function persist(list: G10L3Row[] = rows.value): void {
    opts.debouncedSave(ITEM_ID, { remark: JSON.stringify(toPersistable(list)) })
  }

  function mergeByLiabilityName(incoming: G10L3Row[], sourceLabel: string): void {
    const byName = new Map(rows.value.map((r) => [matchG10LiabilityKey(r.liabilityName), r]))
    let added = 0
    let filled = 0
    const next: G10L3Row[] = toPersistable(rows.value)

    for (const src of incoming) {
      const name = src.liabilityName.trim()
      if (!name) continue
      const key = matchG10LiabilityKey(name)
      const existing = byName.get(key)
      if (!existing) {
        next.push(enrichG10L3Row({ ...src, seq: next.length + 1, remark: src.remark || `自 ${sourceLabel} 带入` }))
        byName.set(key, src)
        added += 1
        continue
      }
      const idx = next.findIndex((r) => matchG10LiabilityKey(r.liabilityName) === key)
      if (idx < 0) continue
      const cur = next[idx]
      const merged = enrichG10L3Row({ ...cur })
      let changed = false
      const numericKeys: (keyof G10L3Row)[] = [
        'openingBalance', 'currentNew', 'currentTerminated', 'transferIntoL3', 'transferOutOfL3',
        'fairValueChange', 'interestExpense', 'otherChanges', 'reportedClosing',
      ]
      for (const k of numericKeys) {
        if (Math.abs(parseNum(cur[k])) < 0.005 && Math.abs(parseNum(src[k])) > 0.005) {
          ;(merged as any)[k] = src[k]
          changed = true
        }
      }
      if (!merged.remark && src.remark) {
        merged.remark = src.remark
        changed = true
      }
      if (changed) {
        next[idx] = enrichG10L3Row(merged)
        filled += 1
      }
    }

    rows.value = next.map((r, i) => enrichG10L3Row({ ...r, seq: i + 1 }))
    persist()
    if (added === 0 && filled === 0) {
      ElMessage.info(`${sourceLabel} 无可带入的 Level3 项目，或已全部存在`)
    } else {
      ElMessage.success(`自 ${sourceLabel}：新增 ${added} 行，补填 ${filled} 行`)
    }
  }

  function updateCell(rowId: string, field: keyof G10L3Row, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrichG10L3Row({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('负债名称', '新增L3调节行', { inputPattern: /\S+/ })
      const row = enrichG10L3Row({ rowId: genId(), seq: rows.value.length + 1, liabilityName: value ?? '' })
      rows.value = [...rows.value, row]
      persist()
    } catch { /* cancel */ }
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichG10L3Row({ ...r, seq: i + 1 }))
    persist()
  }

  function reloadFromStore(): void {
    const j = opts.allResponses.value.get(ITEM_ID)?.remark
    try {
      rows.value = j
        ? JSON.parse(j).map((r: any, i: number) => enrichG10L3Row({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }))
        : []
    } catch { rows.value = [] }
  }

  /**
   * 从 G10-2 明细带入 Level3 行。
   * 映射：期初审定→期初；本期初始确认→新增；本期减少→终止；FV变动/利息；期末审定→企业期末。
   */
  function pullFromDetail(): void {
    if (opts.isReadonly.value) return
    const list = parseG10DetailRows(opts.allResponses.value.get(G10_DETAIL_ROWS_KEY)?.remark)
    const l3 = list.filter((r) => isLevel3(r.fairValueLevel) && r.liabilityName.trim())
    if (!l3.length) {
      ElMessage.info('G10-2 中暂无公允价值层次为 Level3 的项目')
      return
    }
    const mapped: G10L3Row[] = l3.map((src, i) => enrichG10L3Row({
      ...emptyRow(src.liabilityName, i + 1, src.rowId ? `d2-${src.rowId}` : undefined),
      openingBalance: parseNum(src.openingAdjusted) || parseNum(src.openingFairValue),
      currentNew: parseNum(src.movementInitialAmount),
      currentTerminated: parseNum(src.currentDecrease),
      fairValueChange: parseNum(src.movementFvChange),
      interestExpense: parseNum(src.interestExpense),
      reportedClosing: parseNum(src.closingAdjusted) || parseNum(src.closingBalance),
      remark: '自 G10-2 Level3 带入',
    }))
    mergeByLiabilityName(mapped, 'G10-2')
  }

  /** 从 G10-5 公允价值测试带入 Level3 审定期末，用于勾稽「企业期末」 */
  function pullFromFairValueTest(): void {
    if (opts.isReadonly.value) return
    const list = parseFvRows(opts.allResponses.value.get(G10_FV_KEY)?.remark)
    const l3 = list.filter((r) => isLevel3(r.fairValueLevel) && String(r.liabilityName ?? '').trim())
    if (!l3.length) {
      ElMessage.info('G10-5 中暂无 Level3 项目')
      return
    }
    const mapped: G10L3Row[] = l3.map((src, i) => enrichG10L3Row({
      ...emptyRow(String(src.liabilityName), i + 1, src.rowId ? `fv-${src.rowId}` : undefined),
      reportedClosing: parseNum(src.closingAuditedFV),
      remark: '自 G10-5 Level3 带入',
    }))
    mergeByLiabilityName(mapped, 'G10-5')
  }

  async function pushVarianceToAdjustment(): Promise<number> {
    if (opts.isReadonly.value) return 0
    const targets = selectG10L3VarianceTargets(rows.value)
    if (!targets.length) {
      ElMessage.info('无超阈值 L3 调节差异，无需推送')
      return 0
    }
    try {
      await ElMessageBox.confirm(
        `将 ${targets.length} 项 L3 调节差异（企业期末≠公式期末）推送至 G10-3？`,
        '推送差异至 G10-3',
        { type: 'warning', confirmButtonText: '推送', cancelButtonText: '取消' },
      )
    } catch {
      return 0
    }
    const n = pushG10L3VarianceToAdjustment(
      opts.allResponses.value,
      opts.debouncedSave,
      targets,
    )
    if (n > 0) ElMessage.success(`已推送 ${n} 项 L3 调节差异至 G10-3，并回写 G10-1`)
    else ElMessage.info('差异可能已推送过，或未超过阈值')
    return n
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (!rows.value.length) {
      ElMessage.warning('请先编制 G10-6 L3 调节表')
      return -1
    }
    if (varianceRows.value.length || assetMismatches.value.length) {
      try {
        await ElMessageBox.confirm(
          [
            varianceRows.value.length ? `${varianceRows.value.length} 行调节差异未消除` : '',
            assetMismatches.value.length ? `${assetMismatches.value.length} 项与 G10-5 逐笔勾稽差异` : '',
          ].filter(Boolean).join('；') + '，是否仍标记 G10A L3 程序为已完成？',
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }
    const summary = buildG10L3ProcedureSummary({
      rowCount: rows.value.length,
      varianceRows: varianceRows.value.length,
      fvCrossVariance: fvCrossVariance.value,
      assetMismatchCount: assetMismatches.value.length,
    })
    const n = await markG10AProcedureSteps({
      projectId: pid,
      year: opts.auditYear?.value ?? undefined,
      programNos: G10A_FV_PROGRAM_NOS,
      linkedWorkpapers: 'G10-5,G10-6',
      executionSummary: summary,
    })
    if (n > 0) {
      procedureMarked.value = true
      ElMessage.success(`已回填 G10A 程序 seq ${G10A_FV_PROGRAM_NOS.join('/')}（L3 调节）`)
    }
    return n
  }

  return {
    rows,
    varianceRows,
    totals,
    fvL3AuditedTotal,
    fvCrossVariance,
    hasFvCrossMismatch,
    assetMismatches,
    linkByRowId,
    procedureMarked,
    updateCell,
    addRow,
    removeRow,
    reloadFromStore,
    pullFromDetail,
    pullFromFairValueTest,
    pushVarianceToAdjustment,
    markProcedureComplete,
    persist,
    ITEM_ID,
  }
}
