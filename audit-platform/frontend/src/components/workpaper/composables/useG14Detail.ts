/**
 * useG14Detail — G14-2 明细表（固定行 + 合计，减值准备滚动勾稽 + 试算期末对账）
 *
 * 损益侧（本期数）与资产侧（减值准备滚动）双向勾稽：审定数 = 计入损益 = 计提 − 转回
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { G14_LINE_ITEMS } from './g14Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcProvisionRollForward,
  calcNetImpairmentLoss,
  calcSubtotal,
  isRollForwardBalanced,
  isReconciled,
  migrateReversalToPositive,
  calcVariance,
} from './useG14FormulaEngine'
import {
  fetchG14ProvisionClosingsFromTb,
  isClosingReconciledWithTb,
  type G14ProvisionTbResult,
} from './g14ProvisionTb'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
import type { ChecklistResponse } from './useF1FormData'

export interface G14DetailRow {
  rowKey: string
  label: string
  provisionAccount: string
  currentUnadjusted: number
  currentAdjustment: number
  currentAudited: number
  openingProvision: number
  currentProvision: number
  currentReversal: number
  currentWriteoff: number
  /** 合并转入/转出、重分类等不影响损益的准备变动 */
  otherMovement: number
  closingProvision: number
  /** 公式推算期末（期初+计提−转回−转销+其他） */
  closingComputed: number
  /** 推算期末 − 录入期末 */
  rollForwardVariance: number
  /** 试算准备期末（取数结果；null=未取到） */
  tbClosing: number | null
  /** 录入期末与试算期末是否一致（无试算数时视为通过） */
  tbClosingMatched: boolean
  /** 录入期末 − 试算期末 */
  tbClosingVariance: number | null
  profitLoss: number
  reconciled: boolean
  rollForwardBalanced: boolean
  indexRef: string
}

const ITEM_ID_ROWS = 'G14-detail-rows'
const ITEM_ID_TB = 'G14-detail-provision-tb'

function createDefaultRows(tb: G14ProvisionTbResult = {}): G14DetailRow[] {
  return G14_LINE_ITEMS.map((def) => enrichRow({ ...def }, tb[def.rowKey] ?? null))
}

function enrichRow(
  raw: Partial<G14DetailRow> & { rowKey: string },
  tbClosing: number | null = null,
): G14DetailRow {
  const def = G14_LINE_ITEMS.find((d) => d.rowKey === raw.rowKey)
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const currentAdjustment = parseNum(raw.currentAdjustment)
  const openingProvision = parseNum(raw.openingProvision)
  const currentProvision = parseNum(raw.currentProvision)
  const currentReversal = migrateReversalToPositive(raw.currentReversal)
  const currentWriteoff = parseNum(raw.currentWriteoff)
  const otherMovement = parseNum(raw.otherMovement)
  const closingProvision = parseNum(raw.closingProvision)
  const currentAudited = calcAdjustedAmount(currentUnadjusted, currentAdjustment)
  const profitLoss = calcNetImpairmentLoss(currentProvision, currentReversal)
  const closingComputed = calcProvisionRollForward(
    openingProvision,
    currentProvision,
    currentReversal,
    currentWriteoff,
    otherMovement,
  )
  const tb = tbClosing != null && !Number.isNaN(tbClosing) ? tbClosing : null
  return {
    rowKey: raw.rowKey,
    label: def?.label ?? raw.label ?? raw.rowKey,
    provisionAccount: def?.provisionAccount ?? raw.provisionAccount ?? '',
    currentUnadjusted,
    currentAdjustment,
    currentAudited,
    openingProvision,
    currentProvision,
    currentReversal,
    currentWriteoff,
    otherMovement,
    closingProvision,
    closingComputed,
    rollForwardVariance: calcVariance(closingComputed, closingProvision),
    tbClosing: tb,
    tbClosingMatched: isClosingReconciledWithTb(closingProvision, tb),
    tbClosingVariance: tb == null ? null : calcVariance(closingProvision, tb),
    profitLoss,
    reconciled: isReconciled(currentAudited, profitLoss),
    rollForwardBalanced: isRollForwardBalanced(
      openingProvision,
      currentProvision,
      currentReversal,
      currentWriteoff,
      closingProvision,
      otherMovement,
    ),
    indexRef: raw.indexRef ?? '',
  }
}

function parseStoredRows(json: string | null | undefined, tb: G14ProvisionTbResult): G14DetailRow[] {
  if (!json) return createDefaultRows(tb)
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return createDefaultRows(tb)
    const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
    return G14_LINE_ITEMS.map((def) =>
      enrichRow({ ...def, ...(byKey.get(def.rowKey) ?? {}) }, tb[def.rowKey] ?? null),
    )
  } catch {
    return createDefaultRows(tb)
  }
}

function parseTbCache(json: string | null | undefined): G14ProvisionTbResult {
  if (!json) return {}
  try {
    const parsed = JSON.parse(json)
    if (!parsed || typeof parsed !== 'object') return {}
    const out: G14ProvisionTbResult = {}
    for (const [k, v] of Object.entries(parsed)) {
      if (v == null) out[k] = null
      else out[k] = parseNum(v)
    }
    return out
  } catch {
    return {}
  }
}

export interface UseG14DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}

export function useG14Detail(options: UseG14DetailOptions) {
  const auditYear = useWorkpaperAuditYear()
  const tbClosingByKey = ref<G14ProvisionTbResult>({})
  const tbLoading = ref(false)
  const rows = ref<G14DetailRow[]>(createDefaultRows())

  function reenrichAll(): void {
    rows.value = rows.value.map((r) =>
      enrichRow(r, tbClosingByKey.value[r.rowKey] ?? null),
    )
  }

  watch(
    () => options.allResponses.value.get(ITEM_ID_TB)?.remark,
    (json) => {
      tbClosingByKey.value = parseTbCache(json)
      reenrichAll()
    },
    { immediate: true },
  )

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => {
      rows.value = parseStoredRows(json, tbClosingByKey.value)
    },
    { immediate: true },
  )

  function persist(): void {
    const payload = rows.value.map((r) => ({
      rowKey: r.rowKey,
      currentUnadjusted: r.currentUnadjusted,
      currentAdjustment: r.currentAdjustment,
      openingProvision: r.openingProvision,
      currentProvision: r.currentProvision,
      currentReversal: r.currentReversal,
      currentWriteoff: r.currentWriteoff,
      otherMovement: r.otherMovement,
      closingProvision: r.closingProvision,
      indexRef: r.indexRef,
    }))
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(payload) })
    window.dispatchEvent(new CustomEvent('g14:detail-updated'))
  }

  function persistTbCache(): void {
    options.debouncedSave(ITEM_ID_TB, { remark: JSON.stringify(tbClosingByKey.value) })
  }

  function updateCell(rowKey: string, field: keyof G14DetailRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    const raw = { ...rows.value[idx], [field]: value }
    const next = [...rows.value]
    next[idx] = enrichRow(raw, tbClosingByKey.value[rowKey] ?? null)
    rows.value = next
    persist()
  }

  function fillClosingFromRollForward(): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      enrichRow({ ...r, closingProvision: r.closingComputed }, tbClosingByKey.value[r.rowKey] ?? null),
    )
    persist()
  }

  function fillUnauditedFromProfitLoss(): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.map((r) =>
      enrichRow({ ...r, currentUnadjusted: r.profitLoss }, tbClosingByKey.value[r.rowKey] ?? null),
    )
    persist()
  }

  /** 从试算表取各行对应准备/OCI/预计负债期末，写入对账列 */
  async function fetchProvisionClosingFromTb(manual = false): Promise<boolean> {
    const projectId = options.projectId?.value
    const year = auditYear.value
    if (!projectId || year == null) {
      if (manual) ElMessage.warning('无法取数：缺少项目或审计年度')
      return false
    }
    tbLoading.value = true
    try {
      const result = await fetchG14ProvisionClosingsFromTb(projectId, year)
      tbClosingByKey.value = result
      reenrichAll()
      persistTbCache()
      const hitCount = Object.values(result).filter((v) => v != null).length
      if (manual) {
        if (hitCount === 0) ElMessage.info('试算表未匹配到减值准备相关科目，请检查科目映射或手工录入期末')
        else ElMessage.success(`已取数对账 ${hitCount} 行准备/OCI/预计负债期末`)
      }
      return hitCount > 0
    } catch {
      if (manual) ElMessage.error('试算取数失败，请稍后重试')
      return false
    } finally {
      tbLoading.value = false
    }
  }

  /** 将试算期末写入「期末余额」（仅覆盖已取到数的行） */
  function applyTbClosingToProvision(): void {
    if (options.isReadonly.value) return
    let n = 0
    rows.value = rows.value.map((r) => {
      const tb = tbClosingByKey.value[r.rowKey]
      if (tb == null) return enrichRow(r, null)
      n += 1
      return enrichRow({ ...r, closingProvision: tb }, tb)
    })
    if (n === 0) {
      ElMessage.info('尚无试算期末数据，请先「取数对账」')
      return
    }
    persist()
    ElMessage.success(`已将 ${n} 行试算期末写入期末余额`)
  }

  const dataRows = computed(() => rows.value)
  const totalRow = computed(() => {
    const r = rows.value
    return enrichRow({
      rowKey: 'total',
      label: '合计',
      provisionAccount: '',
      currentUnadjusted: calcSubtotal(r.map((x) => x.currentUnadjusted)),
      currentAdjustment: calcSubtotal(r.map((x) => x.currentAdjustment)),
      openingProvision: calcSubtotal(r.map((x) => x.openingProvision)),
      currentProvision: calcSubtotal(r.map((x) => x.currentProvision)),
      currentReversal: calcSubtotal(r.map((x) => x.currentReversal)),
      currentWriteoff: calcSubtotal(r.map((x) => x.currentWriteoff)),
      otherMovement: calcSubtotal(r.map((x) => x.otherMovement)),
      closingProvision: calcSubtotal(r.map((x) => x.closingProvision)),
      indexRef: '',
    }, null)
  })

  const grandTotalAudited = computed(() => totalRow.value.currentAudited)
  const detailTotalMismatch = computed(() =>
    !isReconciled(totalRow.value.currentAudited, totalRow.value.profitLoss),
  )
  const anyRollForwardUnbalanced = computed(() =>
    rows.value.some((r) => !r.rollForwardBalanced),
  )
  const anyTbClosingMismatch = computed(() =>
    rows.value.some((r) => r.tbClosing != null && !r.tbClosingMatched),
  )

  return {
    rows: dataRows,
    totalRow,
    grandTotalAudited,
    detailTotalMismatch,
    anyRollForwardUnbalanced,
    anyTbClosingMismatch,
    tbLoading,
    updateCell,
    fillClosingFromRollForward,
    fillUnauditedFromProfitLoss,
    fetchProvisionClosingFromTb,
    applyTbClosingToProvision,
    persist,
    ITEM_ID_ROWS,
  }
}
