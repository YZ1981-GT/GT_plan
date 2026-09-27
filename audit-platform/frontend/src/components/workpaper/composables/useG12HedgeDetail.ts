/**
 * useG12HedgeDetail — G12-2 净敞口套期收益明细表（对齐 Excel 明细表 G12-2）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  calcFvAllocationCheck,
  calcNetHedgePnl,
  summarizeG12NetHedgeDetailRows,
  type G12NetHedgeDetailRowKind,
} from './g12NetHedgeDetailCalc'
import { G12_NET_HEDGE_DETAIL_SEED } from './g12NetHedgeDetailSeed'
import {
  extractAmortizationFromFvTest,
  extractAmortizationFromVouchers,
  planG12NetPositionSync,
  type G12AmortizationCandidate,
} from './g12NetHedgePositionSync'
import type { G12NetExposureRow } from './useG12NetExposure'
import { parseNum } from './useG12FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export interface G12HedgeDetailRow {
  rowId: string
  seq: number
  item: string
  netPosition: string
  hedgingInstrument: string
  rowKind: G12NetHedgeDetailRowKind
  instrumentFvCumulative: number
  salesPortion: number
  purchasePortion: number
  /**
   * G 列「校验」：`销售部分 + 采购部分 ≈ 套期工具累计公允价值变动`。
   *
   * 🔴 spec `g-cycle-single-region-detail-lanes` Task 13 起进入行模型并**落库**：
   * 模板 `明细表G12-2` 的 `G` 列只在 **R9 一格**有公式（`=D9=SUM(E9:F9)`），R10-R13 是空格
   * ⇒ 后端判 `formula` 会在那四格抛 `ProtectedRegionWriteError`，只能判 `editable`；
   * 而 `editable` 要求前端有对应字段可回写。单一真源仍是 `calcFvAllocationCheck()`，
   * 这里只是把它的结果放进行模型（`rowCalcs` 改为从本字段读，对外 API 不变）。
   *
   * 🔴 字段位置就是**模板列序**（G 在 H 之前）—— 判据
   * `test_frontend_field_order_matches_excel_column_order` 逐位比对，挪动会打红。
   */
  fvCheck: boolean
  hedgeAdjAmortization: number
  /**
   * I 列「净敞口套期损益」：FV 分配行取销售部分、摊销行取套期调整摊销。
   *
   * 🔴 同 `fvCheck`：模板 `I` 列只在 **R9/R10 两格**有公式（`=E9+H9` / `=E10+H10`），
   * R11-R13 空 ⇒ 判 `editable` + 落库，否则用户新增的第 3 行在 Excel 里看不到本列的数。
   * 单一真源是 `calcNetHedgePnl()`。
   */
  netHedgePnl: number
  indexRef: string
  remark: string
}

const ITEM_ID = 'G12-hedge-detail-rows'

function genId() {
  return `g12h-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function isLegacyHedgeRow(raw: Record<string, unknown>): boolean {
  return Boolean(raw.hedgeRelationId) && !raw.item
}

function migrateLegacyRow(raw: Record<string, unknown>, seq: number): G12HedgeDetailRow {
  return enrich({
    rowId: String(raw.rowId ?? genId()),
    seq,
    item: String(raw.hedgedItem ?? raw.hedgeRelationId ?? ''),
    netPosition: '',
    hedgingInstrument: String(raw.hedgingInstrument ?? ''),
    rowKind: 'fv_allocation',
    instrumentFvCumulative: parseNum(raw.instrumentFVChange ?? raw.instrumentFvCumulative),
    salesPortion: parseNum(raw.profitLossAmount ?? raw.salesPortion),
    purchasePortion: parseNum(raw.itemFVChange != null ? -parseNum(raw.itemFVChange) : raw.purchasePortion),
    hedgeAdjAmortization: 0,
    indexRef: String(raw.indexRef ?? raw.hedgeRelationId ?? ''),
    remark: String(raw.remark ?? ''),
  })
}

function rowFromSeed(seed: (typeof G12_NET_HEDGE_DETAIL_SEED)[number], seq: number): G12HedgeDetailRow {
  return enrich({
    rowId: genId(),
    seq,
    item: seed.item,
    netPosition: seed.netPosition ?? '',
    hedgingInstrument: seed.hedgingInstrument ?? '',
    rowKind: seed.rowKind,
    instrumentFvCumulative: seed.rowKind === 'fv_allocation' ? parseNum(seed.instrumentFvCumulative) : 0,
    salesPortion: seed.rowKind === 'fv_allocation' ? parseNum(seed.salesPortion) : 0,
    purchasePortion: seed.rowKind === 'fv_allocation' ? parseNum(seed.purchasePortion) : 0,
    hedgeAdjAmortization: seed.rowKind === 'amortization' ? parseNum(seed.hedgeAdjAmortization) : 0,
    indexRef: seed.indexRef ?? '',
    remark: seed.remark ?? '',
  })
}

function defaultRows(): G12HedgeDetailRow[] {
  return G12_NET_HEDGE_DETAIL_SEED.map((s, i) => rowFromSeed(s, i + 1))
}

function enrich(raw: Partial<G12HedgeDetailRow> & { rowId: string }): G12HedgeDetailRow {
  const rowKind: G12NetHedgeDetailRowKind = raw.rowKind === 'amortization' ? 'amortization' : 'fv_allocation'
  const instrumentFvCumulative = rowKind === 'fv_allocation' ? parseNum(raw.instrumentFvCumulative) : 0
  const salesPortion = rowKind === 'fv_allocation' ? parseNum(raw.salesPortion) : 0
  const purchasePortion = rowKind === 'fv_allocation' ? parseNum(raw.purchasePortion) : 0
  const hedgeAdjAmortization = rowKind === 'amortization' ? parseNum(raw.hedgeAdjAmortization) : 0
  // 🔴 G/I 两列由纯函数现算后进入行模型（Task 13：模板公式覆盖不全 ⇒ 判 editable 需要可回写字段）
  const calcInput = {
    rowKind,
    instrumentFvCumulative,
    salesPortion,
    purchasePortion,
    hedgeAdjAmortization,
  }
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    item: raw.item ?? '',
    netPosition: raw.netPosition ?? '',
    hedgingInstrument: raw.hedgingInstrument ?? '',
    rowKind,
    instrumentFvCumulative,
    salesPortion,
    purchasePortion,
    // 摊销行没有 FV 三分量可校验 ⇒ 恒真（与改造前 `rowCalcs` 的口径逐字一致）
    fvCheck: rowKind === 'amortization'
      || calcFvAllocationCheck(instrumentFvCumulative, salesPortion, purchasePortion),
    hedgeAdjAmortization,
    netHedgePnl: calcNetHedgePnl(calcInput),
    indexRef: raw.indexRef ?? '',
    remark: raw.remark ?? '',
  }
}

function parse(json: string | null | undefined): G12HedgeDetailRow[] {
  if (!json) return defaultRows()
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr) || !arr.length) return defaultRows()
    if (isLegacyHedgeRow(arr[0] as Record<string, unknown>)) {
      return arr.map((r: Record<string, unknown>, i: number) =>
        migrateLegacyRow(r, parseNum(r.seq) || i + 1),
      )
    }
    return arr.map((r: Partial<G12HedgeDetailRow> & { rowId?: string }, i: number) =>
      enrich({ ...r, rowId: r.rowId || genId(), seq: r.seq ?? i + 1 }),
    )
  } catch {
    return defaultRows()
  }
}

function resequence(rows: G12HedgeDetailRow[]): G12HedgeDetailRow[] {
  return rows.map((r, i) => enrich({ ...r, seq: i + 1 }))
}

export function useG12HedgeDetail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}) {
  const rows = ref<G12HedgeDetailRow[]>(defaultRows())

  watch(() => opts.allResponses.value.get(ITEM_ID)?.remark, (j) => {
    rows.value = parse(j)
  }, { immediate: true })

  function persist() {
    opts.debouncedSave(ITEM_ID, {
      remark: JSON.stringify(rows.value.map((r) => ({
        rowId: r.rowId, seq: r.seq, item: r.item, netPosition: r.netPosition,
        hedgingInstrument: r.hedgingInstrument, rowKind: r.rowKind,
        instrumentFvCumulative: r.instrumentFvCumulative, salesPortion: r.salesPortion,
        purchasePortion: r.purchasePortion,
        // 🔴 G/I 两列落库（Task 13 受管面）—— 值由 enrich 现算，读回时会被重算覆盖，
        //    因此它们是「快照」而非第二真源；模板 R11-R13 缺公式，靠这两格补齐。
        //    顺序按模板列序 G→H→I。
        fvCheck: r.fvCheck, hedgeAdjAmortization: r.hedgeAdjAmortization,
        netHedgePnl: r.netHedgePnl,
        indexRef: r.indexRef, remark: r.remark,
      }))),
    })
    window.dispatchEvent(new CustomEvent('g12:hedge-detail-updated'))
  }

  function updateCell(rowId: string, field: keyof G12HedgeDetailRow, value: unknown) {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const next = [...rows.value]
    next[idx] = enrich({ ...next[idx], [field]: value })
    rows.value = next
    persist()
  }

  function addRow(kind: G12NetHedgeDetailRowKind = 'fv_allocation') {
    if (opts.isReadonly.value) return
    rows.value = resequence([
      ...rows.value,
      enrich({
        rowId: genId(),
        seq: rows.value.length + 1,
        rowKind: kind,
        item: kind === 'amortization' ? '套期调整摊销' : '',
      }),
    ])
    persist()
  }

  function removeRow(rowId: string) {
    if (opts.isReadonly.value) return
    if (rows.value.length <= 1) {
      ElMessage.warning('至少保留一行明细')
      return
    }
    rows.value = resequence(rows.value.filter((r) => r.rowId !== rowId))
    persist()
  }

  // 🔴 改为从行模型读（`enrich` 已用同一批纯函数算好）—— 对外 API 与字段名不变，
  //    消费方 `G12TabHedgeDetail.vue` 的 `rowCalcMap` 无需改动。
  const rowCalcs = computed(() =>
    rows.value.map((r) => ({
      rowId: r.rowId,
      fvCheckOk: r.fvCheck,
      netHedgePnl: r.netHedgePnl,
    })),
  )

  const totals = computed(() => summarizeG12NetHedgeDetailRows(rows.value))

  function aggregateForAdjudication() {
    const t = totals.value
    return {
      instrument_fv: { unadjusted: t.instrumentFvCumulative, adjustment: 0, audited: t.instrumentFvCumulative },
      item_fv: { unadjusted: t.purchasePortion, adjustment: 0, audited: t.purchasePortion },
      ineffectiveness: { unadjusted: 0, adjustment: 0, audited: 0 },
      net_hedge: { unadjusted: t.netHedgePnl, adjustment: 0, audited: t.netHedgePnl },
    } as Record<string, { unadjusted: number; adjustment: number; audited: number }>
  }

  function importFromNetExposure(neRows: Array<{
    item: string
    netPosition: string
    hedgingInstrument: string
    indexRef: string
  }>) {
    if (opts.isReadonly.value) return 0
    let added = 0
    for (const n of neRows) {
      if (!n.item.trim() && !n.hedgingInstrument.trim()) continue
      const exists = rows.value.some(
        (r) => r.rowKind === 'fv_allocation'
          && r.item === n.item
          && r.hedgingInstrument === n.hedgingInstrument,
      )
      if (exists) continue
      rows.value = resequence([
        ...rows.value,
        enrich({
          rowId: genId(),
          seq: rows.value.length + 1,
          item: n.item,
          netPosition: n.netPosition,
          hedgingInstrument: n.hedgingInstrument,
          rowKind: 'fv_allocation',
          indexRef: n.indexRef ? `G12-5/${n.indexRef}` : 'G12-5',
        }),
      ])
      added += 1
    }
    if (added) persist()
    return added
  }

  /** G12-5 → G12-2：同步已匹配行的净头寸 */
  function syncNetPositionFromG12_5(neRows: G12NetExposureRow[]): number {
    if (opts.isReadonly.value) return 0
    const plan = planG12NetPositionSync('g12-5', rows.value, neRows)
    if (!plan.detailUpdates.length) return 0
    const next = rows.value.map((r) => {
      const hit = plan.detailUpdates.find((u) => u.rowId === r.rowId)
      return hit ? enrich({ ...r, netPosition: hit.netPosition }) : r
    })
    rows.value = next
    persist()
    return plan.syncedCount
  }

  function importAmortizationCandidates(candidates: G12AmortizationCandidate[]): number {
    if (opts.isReadonly.value || !candidates.length) return 0
    let added = 0
    for (const c of candidates) {
      const dup = rows.value.some(
        (r) => r.rowKind === 'amortization'
          && r.indexRef === c.indexRef
          && Math.abs(r.hedgeAdjAmortization - c.amount) < 0.01,
      )
      if (dup) continue
      rows.value = resequence([
        ...rows.value,
        enrich({
          rowId: genId(),
          seq: rows.value.length + 1,
          item: c.label,
          hedgingInstrument: c.hedgingInstrument,
          rowKind: 'amortization',
          hedgeAdjAmortization: c.amount,
          indexRef: c.indexRef,
          remark: `自 ${c.source} 带入`,
        }),
      ])
      added += 1
    }
    if (added) persist()
    return added
  }

  function importAmortizationFromResponses(allResponses: Map<string, { remark?: string | null }>) {
    const fvRaw = allResponses.get('G12-fv-test-rows')?.remark
    const vchRaw = allResponses.get('G12-voucher-rows')?.remark
    let fvRows: any[] = []
    let vchRows: any[] = []
    try { if (fvRaw) fvRows = JSON.parse(fvRaw) } catch { /* ignore */ }
    try { if (vchRaw) vchRows = JSON.parse(vchRaw) } catch { /* ignore */ }
    return importAmortizationCandidates([
      ...extractAmortizationFromFvTest(fvRows),
      ...extractAmortizationFromVouchers(vchRows),
    ])
  }

  return {
    rows,
    rowCalcs,
    totals,
    updateCell,
    addRow,
    removeRow,
    persist,
    aggregateForAdjudication,
    importFromNetExposure,
    syncNetPositionFromG12_5,
    importAmortizationCandidates,
    importAmortizationFromResponses,
    ITEM_ID,
  }
}

export function mapG12HedgeDetailForFvCross(rows: G12HedgeDetailRow[]) {
  return rows
    .filter((r) => r.rowKind === 'fv_allocation')
    .map((r) => ({
      hedgeRelationId: r.indexRef || r.hedgingInstrument || r.item,
      instrumentFVChange: r.instrumentFvCumulative,
      itemFVChange: -r.purchasePortion,
      hedgingInstrument: r.hedgingInstrument,
      hedgedItem: r.item,
      indexRef: r.indexRef,
    }))
}
