/**
 * useG11DetailAnalysis — G11-2 明细分析表
 *
 * 编制逻辑：
 * 1. 按 G11-1 同口径 18 类投资收益项目骨架列示本期/上期未审·调整·审定及占比
 * 2. 审定=未审+调整；占比=审定/合计；变动额/率对照上期审定
 * 3. |变动率|>20% 高亮，须填变动原因/索引
 * 4. G11-3 账项调整按分项回写本期调整列（与 G11-1 同步）
 * 5. 合计应与 G11-1 审定合计勾稽
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcAdjustedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  isChangeRateExceeding,
} from './useG11FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  G11_ADJUDICATION_ITEMS,
  G11_CHANGE_RATE_THRESHOLD,
} from './g11Constants'
import type { G11AdjustmentWritebackMap } from './g11AdjStorage'
import {
  loadG714EquityIncomeSeeds,
  mergeG714SeedsIntoDetailRows,
  fetchG11LedgerIncomeSeeds,
  mergeLedgerSeedsIntoDetailRows,
} from './g11CrossHelpers'
import {
  buildG714SuggestedG11Adjustments,
  pushSuggestedAdjustmentsFromG714Seeds,
} from './g11EquityMethodPushG113'
import { isG11TradingDisposeDetailRow, type G11TradingDisposeSuffix } from './g11SchemaRows'

export type G11TradingDisposeSubtype = G11TradingDisposeSuffix

export interface G11DetailRow {
  id: string
  seq: number
  /** 与 G11-1 rowKey 对齐，便于分项回写与勾稽 */
  rowKey: string
  itemName: string
  investeeName: string
  /** 处置交易性 → 上市附注子表子类（可选，优先于文本推断） */
  tradingDisposeSubtype?: G11TradingDisposeSubtype | ''
  group: string
  currentUnadjusted: number
  currentAdjustment: number
  currentAudited: number
  currentShare: number | null
  priorUnadjusted: number
  priorAdjustment: number
  priorAudited: number
  priorShare: number | null
  changeAmount: number
  changeRate: number | null
  reasonIndex: string
  changeRateHighlight: boolean
  reasonRequired: boolean
  /** 骨架行不可删 */
  isSkeleton: boolean
}

const ITEM_ID_ROWS = 'G11-detail-rows'
const ITEM_ID_PROFIT = 'G11-detail-profit-total'

function generateId(): string {
  return `g11d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function resolveGroup(itemName: string, rowKey?: string): string {
  if (rowKey) {
    const byKey = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === rowKey)
    if (byKey?.group) return byKey.group
  }
  const hit = G11_ADJUDICATION_ITEMS.find(
    (d) => d.label === itemName || itemName.includes(d.label.slice(0, 6)),
  )
  return hit?.group ?? '其他'
}

function resolveRowKey(itemName: string, existing?: string): string {
  if (existing && G11_ADJUDICATION_ITEMS.some((d) => d.rowKey === existing)) return existing
  const hit = G11_ADJUDICATION_ITEMS.find(
    (d) => d.label === itemName || itemName.includes(d.label.slice(0, 8)),
  )
  return hit?.rowKey ?? ''
}

function buildSkeletonRows(): G11DetailRow[] {
  return G11_ADJUDICATION_ITEMS.map((def, i) =>
    enrichRow(
      {
        id: `g11d-sk-${def.rowKey}`,
        rowKey: def.rowKey,
        itemName: def.label,
        group: def.group ?? '其他',
        isSkeleton: true,
      },
      i + 1,
    ),
  )
}

function enrichRow(
  raw: Partial<G11DetailRow> & { id?: string },
  seq: number,
  totals?: { current: number; prior: number },
): G11DetailRow {
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const currentAdjustment = parseNum(raw.currentAdjustment)
  const priorUnadjusted = parseNum(raw.priorUnadjusted)
  const priorAdjustment = parseNum(raw.priorAdjustment)
  const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  const priorAudited = calcAdjustedAmount(priorUnadjusted, priorAdjustment)
  const changeRate = calcChangeRate(priorAudited, currentAudited)
  const reasonRequired = isChangeRateExceeding(changeRate, G11_CHANGE_RATE_THRESHOLD)
  const currentShare =
    totals && totals.current !== 0
      ? currentAudited / totals.current
      : (raw.currentShare ?? null)
  const priorShare =
    totals && totals.prior !== 0
      ? priorAudited / totals.prior
      : (raw.priorShare ?? null)
  const itemName = raw.itemName ?? ''
  const rowKey = resolveRowKey(itemName, raw.rowKey)
  return {
    id: raw.id ?? generateId(),
    seq,
    rowKey,
    itemName,
    investeeName: raw.investeeName ?? '',
    tradingDisposeSubtype: raw.tradingDisposeSubtype ?? '',
    group: raw.group ?? resolveGroup(itemName, rowKey),
    currentUnadjusted,
    currentAdjustment,
    currentAudited,
    currentShare: currentShare != null ? parseNum(currentShare) : null,
    priorUnadjusted,
    priorAdjustment,
    priorAudited,
    priorShare: priorShare != null ? parseNum(priorShare) : null,
    changeAmount: calcChangeAmount(currentAudited, priorAudited),
    changeRate,
    reasonIndex: raw.reasonIndex ?? '',
    changeRateHighlight: reasonRequired,
    reasonRequired,
    isSkeleton: !!raw.isSkeleton,
  }
}

function parseRows(json: string | null | undefined): G11DetailRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => enrichRow(r, i + 1))
  } catch {
    return []
  }
}

/** 空表或仅无有效金额时，用审定表骨架预填 */
function ensureSkeleton(parsed: G11DetailRow[]): G11DetailRow[] {
  if (parsed.length === 0) return buildSkeletonRows()
  const hasSkeletonKeys = parsed.some((r) =>
    G11_ADJUDICATION_ITEMS.some((d) => d.rowKey === r.rowKey),
  )
  if (hasSkeletonKeys) return parsed
  // 旧数据无 rowKey：尽量映射后返回
  return parsed.map((r, i) => enrichRow(r, i + 1))
}

export function useG11DetailAnalysis(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
  htmlData?: Ref<Record<string, unknown> | null | undefined> | ComputedRef<Record<string, unknown> | null | undefined>
}) {
  const rows = ref<G11DetailRow[]>([])
  const profitTotal = ref(0)
  const g714ImportMsg = ref('')
  const ledgerImportMsg = ref('')

  function resolveAuditYear(): number {
    const raw =
      opts.htmlData?.value?.project_context
      ?? opts.htmlData?.value?.projectContext
    const y = (raw as any)?.audit_year ?? (raw as any)?.auditYear ?? opts.htmlData?.value?.audit_year
    const n = Number(y)
    return Number.isFinite(n) && n > 0 ? n : new Date().getFullYear() - 1
  }

  function recomputeAll(): void {
    const currentTotal = calcSubtotal(
      rows.value.map((r) =>
        calcAdjustedAmount(parseNum(r.currentUnadjusted), parseNum(r.currentAdjustment)),
      ),
    )
    const priorTotal = calcSubtotal(
      rows.value.map((r) =>
        calcAdjustedAmount(parseNum(r.priorUnadjusted), parseNum(r.priorAdjustment)),
      ),
    )
    rows.value = rows.value.map((r, i) =>
      enrichRow(r, i + 1, { current: currentTotal, prior: priorTotal }),
    )
  }

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      const parsed = ensureSkeleton(parseRows(json))
      rows.value = parsed
      recomputeAll()
    },
    { immediate: true },
  )

  watch(
    () => opts.allResponses.value.get(ITEM_ID_PROFIT)?.remark,
    (v) => { profitTotal.value = parseNum(v) },
    { immediate: true },
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
  }

  function reseq(): void {
    rows.value = rows.value.map((r, i) => ({ ...r, seq: i + 1 }))
  }

  const totalRow = computed(() => {
    const currentAudited = calcSubtotal(rows.value.map((r) => r.currentAudited))
    const priorAudited = calcSubtotal(rows.value.map((r) => r.priorAudited))
    const currentUnadjusted = calcSubtotal(rows.value.map((r) => r.currentUnadjusted))
    const currentAdjustment = calcSubtotal(rows.value.map((r) => r.currentAdjustment))
    const priorUnadjusted = calcSubtotal(rows.value.map((r) => r.priorUnadjusted))
    const priorAdjustment = calcSubtotal(rows.value.map((r) => r.priorAdjustment))
    return {
      currentUnadjusted,
      currentAdjustment,
      currentAudited,
      priorUnadjusted,
      priorAdjustment,
      priorAudited,
      changeAmount: calcChangeAmount(currentAudited, priorAudited),
      changeRate: calcChangeRate(priorAudited, currentAudited),
      shareOfProfit:
        profitTotal.value !== 0 ? currentAudited / profitTotal.value : null,
    }
  })

  const highlightCount = computed(
    () => rows.value.filter((r) => r.changeRateHighlight).length,
  )

  const missingReasonCount = computed(
    () => rows.value.filter((r) => r.reasonRequired && !r.reasonIndex.trim()).length,
  )

  const hasTradingDisposeRows = computed(() =>
    rows.value.some((r) => isG11TradingDisposeDetailRow(r)),
  )

  const groupedRows = computed(() => {
    const map = new Map<string, G11DetailRow[]>()
    for (const row of rows.value) {
      const g = row.group || '其他'
      if (!map.has(g)) map.set(g, [])
      map.get(g)!.push(row)
    }
    return [...map.entries()].map(([groupName, groupRows]) => ({
      groupName,
      rows: groupRows,
      subtotal: {
        currentAudited: calcSubtotal(groupRows.map((r) => r.currentAudited)),
        priorAudited: calcSubtotal(groupRows.map((r) => r.priorAudited)),
      },
    }))
  })

  /** @deprecated 全额堆「其他」；保留兼容旧调用 */
  function applyOtherAdjustment(net: number): void {
    applyAdjustmentByRow({ other: net })
  }

  /** G11-3 分项回写本期调整（覆盖式：出现在 map 中的 rowKey） */
  function applyAdjustmentByRow(byRow: G11AdjustmentWritebackMap): void {
    if (opts.isReadonly.value) return
    let changed = false
    const next = rows.value.map((r) => {
      if (!r.rowKey || !(r.rowKey in byRow)) return r
      const adj = parseNum(byRow[r.rowKey])
      if (r.currentAdjustment === adj) return r
      changed = true
      return { ...r, currentAdjustment: adj }
    })
    // map 中有键但明细尚无对应行时，补到「其他」或新建
    for (const [key, net] of Object.entries(byRow)) {
      if (Math.abs(parseNum(net)) < 0.005) continue
      if (next.some((r) => r.rowKey === key)) continue
      const def = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === key)
      next.push(
        enrichRow(
          {
            rowKey: key,
            itemName: def?.label ?? key,
            group: def?.group ?? '其他',
            currentAdjustment: parseNum(net),
            isSkeleton: !!def,
          },
          next.length + 1,
        ),
      )
      changed = true
    }
    if (!changed) return
    rows.value = next
    recomputeAll()
    persist()
  }

  function updateRow(id: string, patch: Partial<G11DetailRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      const merged = { ...r, ...patch }
      if (patch.itemName != null && !r.isSkeleton) {
        merged.rowKey = resolveRowKey(patch.itemName, merged.rowKey)
        merged.group = resolveGroup(patch.itemName, merged.rowKey)
      }
      if (patch.rowKey != null || patch.itemName != null) {
        if (merged.rowKey !== 'trading_dispose' && !/处置交易性/.test(merged.itemName)) {
          merged.tradingDisposeSubtype = ''
        }
      }
      return merged
    })
    recomputeAll()
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目/项目名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      if (!value?.trim()) return
      const name = value.trim()
      rows.value = [
        ...rows.value,
        enrichRow(
          { itemName: name, rowKey: resolveRowKey(name), isSkeleton: false },
          rows.value.length + 1,
        ),
      ]
      recomputeAll()
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    const target = rows.value.find((r) => r.id === id)
    if (target?.isSkeleton) return
    rows.value = rows.value.filter((r) => r.id !== id)
    reseq()
    recomputeAll()
    persist()
  }

  function resetToSkeleton(): void {
    if (opts.isReadonly.value) return
    rows.value = buildSkeletonRows()
    recomputeAll()
    persist()
  }

  function updateProfitTotal(v: number): void {
    if (opts.isReadonly.value) return
    profitTotal.value = parseNum(v)
    opts.debouncedSave(ITEM_ID_PROFIT, { remark: String(profitTotal.value) })
  }

  function loadRows(data: Partial<G11DetailRow>[]): void {
    rows.value = ensureSkeleton(data.map((r, i) => enrichRow(r as G11DetailRow, i + 1)))
    recomputeAll()
    persist()
  }

  function reloadFromStore(): void {
    const json = opts.allResponses.value.get(ITEM_ID_ROWS)?.remark
    rows.value = ensureSkeleton(parseRows(json))
    recomputeAll()
  }

  function tableRowClassName({ row }: { row: G11DetailRow }): string {
    if (row.changeRateHighlight) return 'change-rate-alert'
    return ''
  }

  async function importFromG714(mode: 'empty_only' | 'overwrite' = 'empty_only'): Promise<number> {
    if (opts.isReadonly.value) return 0
    const projectId = opts.projectId?.value
    if (!projectId) {
      g714ImportMsg.value = '缺少项目 ID，无法定位 G7-14'
      return 0
    }
    g714ImportMsg.value = '正在读取 G7-14…'
    try {
      const { seeds, sourceWpIds } = await loadG714EquityIncomeSeeds({
        projectId,
        htmlData: opts.htmlData?.value ?? null,
      })
      if (!seeds.length) {
        g714ImportMsg.value = '未找到 G7-14 权益法测算数据（请确认项目已编制 G7-14）'
        return 0
      }
      const merged = mergeG714SeedsIntoDetailRows(rows.value, seeds, mode)
      rows.value = merged.map((r, i) => enrichRow(r as G11DetailRow, i + 1))
      recomputeAll()
      persist()
      g714ImportMsg.value = `已从 G7-14 带入 ${seeds.length} 户（${sourceWpIds.length} 个底稿）`
      return seeds.length
    } catch {
      g714ImportMsg.value = 'G7-14 带入失败，请稍后重试'
      return 0
    }
  }

  async function prefillUnreviewedFromLedger(
    mode: 'empty_only' | 'overwrite' = 'empty_only',
  ): Promise<number> {
    if (opts.isReadonly.value) return 0
    const projectId = opts.projectId?.value
    if (!projectId) {
      ledgerImportMsg.value = '缺少项目 ID，无法读取序时账'
      return 0
    }
    ledgerImportMsg.value = '正在读取 TB/序时账…'
    try {
      const { seeds, source, error } = await fetchG11LedgerIncomeSeeds({
        projectId,
        year: resolveAuditYear(),
      })
      if (!seeds.length) {
        ledgerImportMsg.value = error || '未找到 6111 分项发生额'
        return 0
      }
      const merged = mergeLedgerSeedsIntoDetailRows(rows.value, seeds, mode)
      rows.value = merged.map((r, i) => enrichRow(r as G11DetailRow, i + 1))
      recomputeAll()
      persist()
      ledgerImportMsg.value = `已从${source}预填 ${seeds.length} 项未审数`
      return seeds.length
    } catch {
      ledgerImportMsg.value = 'TB/序时账预填失败，请稍后重试'
      return 0
    }
  }

  function countG714DiffSuggestions(seeds: Awaited<ReturnType<typeof loadG714EquityIncomeSeeds>>['seeds']): number {
    return buildG714SuggestedG11Adjustments(seeds).length
  }

  function pushG714DiffToAdjustment(
    seeds: Awaited<ReturnType<typeof loadG714EquityIncomeSeeds>>['seeds'],
  ): ReturnType<typeof pushSuggestedAdjustmentsFromG714Seeds> {
    return pushSuggestedAdjustmentsFromG714Seeds({
      responses: opts.allResponses.value,
      debouncedSave: opts.debouncedSave,
      seeds,
      applyAdjustmentToDetail: (byRow) => applyAdjustmentByRow(byRow),
    })
  }

  async function loadG714SeedsForPush(): Promise<
    Awaited<ReturnType<typeof loadG714EquityIncomeSeeds>>
  > {
    const projectId = opts.projectId?.value
    if (!projectId) {
      return { seeds: [], sourceWpIds: [] }
    }
    return loadG714EquityIncomeSeeds({
      projectId,
      htmlData: opts.htmlData?.value ?? null,
    })
  }

  return {
    rows,
    totalRow,
    groupedRows,
    profitTotal,
    highlightCount,
    missingReasonCount,
    hasTradingDisposeRows,
    g714ImportMsg,
    ledgerImportMsg,
    updateRow,
    addRow,
    removeRow,
    loadRows,
    reloadFromStore,
    applyOtherAdjustment,
    applyAdjustmentByRow,
    resetToSkeleton,
    updateProfitTotal,
    tableRowClassName,
    importFromG714,
    prefillUnreviewedFromLedger,
    countG714DiffSuggestions,
    pushG714DiffToAdjustment,
    loadG714SeedsForPush,
    CHANGE_RATE_THRESHOLD: G11_CHANGE_RATE_THRESHOLD,
  }
}
