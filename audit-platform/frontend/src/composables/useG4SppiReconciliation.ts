/**
 * useG4SppiReconciliation — G4-8 有价证券盘点倒轧表
 *
 * 对齐致同 Excel「有价证券盘点倒轧表」：
 *   盘点日实存 → 资产负债表日至盘点日增减 → 报表日推算实存 → 账面结存 → 差异
 *
 * 公式：
 *   报表日数量 = 盘点日数量 − 增加 + 减少
 *   报表日总计 = 报表日面值 × 报表日数量
 *   差异数量/金额 = 报表日 − 账面
 *
 * 相对原版改进：
 *   1. 增减拆分为增加/减少，倒轧方向与致同模板一致
 *   2. 票面利率/到期日以盘点日为准自动继承，去掉报表日冗余录入
 *   3. 增减证据索引 + 账面摊余成本参照列
 *   4. 数量差异与面值差异双勾稽；差异行强制填备注
 *   5. 兼容旧字段 changeQuantity / changeFaceValueTotal / reportCouponRate 等
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  calcInventoryTotal,
  calcReportDateQuantity,
  calcReportDateTotal,
  calcReconciliationVariance,
  calcQuantityVariance,
  isReconciliationFullyBalanced,
  calcSumColumn,
  parseNum,
} from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ReconciliationTab = 'countDate' | 'changes' | 'reportDate'

export interface ReconciliationItem {
  id: string
  seq: number
  securitiesName: string
  // ══ 区段1: 盘点日实存 ══
  countQuantity: number
  countFaceValue: number
  countTotal: number
  countCouponRate: number
  countMaturityDate: string
  // ══ 区段2: 资产负债表日→盘点日增减 ══
  increaseQuantity: number
  increaseFaceTotal: number
  decreaseQuantity: number
  decreaseFaceTotal: number
  /** 增减变动证据索引（交割单/对账单/日记账等） */
  changeEvidenceRef: string
  // ══ 区段3: 报表日推算 + 账面 + 差异 ══
  reportQuantity: number
  reportFaceValue: number
  reportTotal: number
  /** 继承自盘点日，只读展示 */
  reportCouponRate: number
  reportMaturityDate: string
  bookQuantity: number
  bookFaceValue: number
  bookTotal: number
  /** 账面摊余成本/账面价值（参照，不参与面值倒轧公式） */
  bookCarryingAmount: number
  varianceQuantity: number
  variance: number
  remark: string
  // 兼容旧字段（持久化时仍写出，便于旧导入回读）
  changeQuantity?: number
  changeFaceValueTotal?: number
}

export interface ReconciliationHeader {
  /** 盘点日 */
  countDate: string
  /** 资产负债表日 / 截止日 */
  balanceSheetDate: string
}

export interface ReconciliationSummary {
  countQuantityTotal: number
  countFaceValueTotal: number
  countTotalTotal: number
  increaseQuantityTotal: number
  increaseFaceTotalTotal: number
  decreaseQuantityTotal: number
  decreaseFaceTotalTotal: number
  reportQuantityTotal: number
  reportFaceValueTotal: number
  reportTotalTotal: number
  bookQuantityTotal: number
  bookFaceValueTotal: number
  bookTotalTotal: number
  bookCarryingAmountTotal: number
  varianceQuantityTotal: number
  varianceTotal: number
}

export interface ReconciliationStats {
  total: number
  withDiff: number
  missingRemark: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_ITEMS = 'G4-8-items'
const STORAGE_KEY_AUDIT_CONCLUSION = 'G4-8-audit-conclusion'
const STORAGE_KEY_HEADER = 'G4-8-header'

const MAX_ROWS = 200

export const TAB_OPTIONS: Array<{ key: ReconciliationTab; label: string }> = [
  { key: 'countDate', label: '盘点日实存有价证券' },
  { key: 'changes', label: '资产负债表日到盘点日增减' },
  { key: 'reportDate', label: '报表日实存+账面差异' },
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `g4rec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyItem(name: string, seq: number): ReconciliationItem {
  return {
    id: generateId(),
    seq,
    securitiesName: name,
    countQuantity: 0,
    countFaceValue: 0,
    countTotal: 0,
    countCouponRate: 0,
    countMaturityDate: '',
    increaseQuantity: 0,
    increaseFaceTotal: 0,
    decreaseQuantity: 0,
    decreaseFaceTotal: 0,
    changeEvidenceRef: '',
    reportQuantity: 0,
    reportFaceValue: 0,
    reportTotal: 0,
    reportCouponRate: 0,
    reportMaturityDate: '',
    bookQuantity: 0,
    bookFaceValue: 0,
    bookTotal: 0,
    bookCarryingAmount: 0,
    varianceQuantity: 0,
    variance: 0,
    remark: '',
  }
}

/** 公式链求解：一次性计算所有派生字段 */
function enrichItem(item: ReconciliationItem): ReconciliationItem {
  const countTotal = calcInventoryTotal(item.countFaceValue, item.countQuantity)
  const reportQuantity = calcReportDateQuantity(
    item.countQuantity,
    item.increaseQuantity,
    item.decreaseQuantity,
  )
  // 报表日面值默认继承盘点日；用户可覆盖
  const reportFaceValue = parseNum(item.reportFaceValue) || parseNum(item.countFaceValue)
  const reportTotal = calcReportDateTotal(reportFaceValue, reportQuantity)
  // 票面利率/到期日以盘点日为准（同一种证券条款不变）
  const reportCouponRate = parseNum(item.countCouponRate)
  const reportMaturityDate = item.countMaturityDate || ''

  const bookFaceValue = parseNum(item.bookFaceValue)
  const bookQuantity = parseNum(item.bookQuantity)
  const bookTotal =
    bookFaceValue > 0
      ? calcInventoryTotal(bookFaceValue, bookQuantity)
      : parseNum(item.bookTotal)

  const varianceQuantity = calcQuantityVariance(reportQuantity, bookQuantity)
  const variance = calcReconciliationVariance(reportTotal, bookTotal)

  // 兼容字段：净增加（资产负债表日→盘点日）
  const changeQuantity = parseNum(item.increaseQuantity) - parseNum(item.decreaseQuantity)
  const changeFaceValueTotal =
    parseNum(item.increaseFaceTotal) - parseNum(item.decreaseFaceTotal)

  return {
    ...item,
    countTotal,
    reportQuantity,
    reportFaceValue,
    reportTotal,
    reportCouponRate,
    reportMaturityDate,
    bookTotal,
    varianceQuantity,
    variance,
    changeQuantity,
    changeFaceValueTotal,
  }
}

/**
 * 旧数据迁移：
 * - changeQuantity 曾用「盘点日+增减=报表日」错误口径；迁移时保数值连续：
 *     change≥0 → decrease = change；change<0 → increase = |change|
 * - 亦支持旧模板直接写 increase/decrease
 */
export function migrateLegacyItem(
  raw: Record<string, unknown>,
  index: number,
): ReconciliationItem {
  const base = createEmptyItem(String(raw.securitiesName ?? ''), Number(raw.seq) || index + 1)
  if (raw.id) base.id = String(raw.id)

  base.countQuantity = parseNum(raw.countQuantity)
  base.countFaceValue = parseNum(raw.countFaceValue)
  base.countCouponRate = parseNum(raw.countCouponRate)
  base.countMaturityDate = String(raw.countMaturityDate ?? '')

  const hasSplit =
    raw.increaseQuantity != null ||
    raw.decreaseQuantity != null ||
    raw.increaseFaceTotal != null ||
    raw.decreaseFaceTotal != null

  if (hasSplit) {
    base.increaseQuantity = parseNum(raw.increaseQuantity)
    base.increaseFaceTotal = parseNum(raw.increaseFaceTotal)
    base.decreaseQuantity = parseNum(raw.decreaseQuantity)
    base.decreaseFaceTotal = parseNum(raw.decreaseFaceTotal)
  } else {
    // 旧单一增减列：保留报表日推算结果连续（旧公式 report=count+change）
    const legacyChange = parseNum(raw.changeQuantity)
    const legacyFace = parseNum(raw.changeFaceValueTotal)
    if (legacyChange >= 0) {
      base.decreaseQuantity = legacyChange
      base.decreaseFaceTotal = Math.max(0, legacyFace)
      base.increaseFaceTotal = legacyFace < 0 ? Math.abs(legacyFace) : 0
    } else {
      base.increaseQuantity = Math.abs(legacyChange)
      base.increaseFaceTotal = legacyFace <= 0 ? Math.abs(legacyFace) : legacyFace
      base.decreaseFaceTotal = legacyFace > 0 ? 0 : 0
    }
  }

  base.changeEvidenceRef = String(raw.changeEvidenceRef ?? raw.evidenceRef ?? '')
  base.reportFaceValue = parseNum(raw.reportFaceValue ?? raw.countFaceValue)
  base.bookQuantity = parseNum(raw.bookQuantity)
  base.bookFaceValue = parseNum(raw.bookFaceValue)
  base.bookTotal = parseNum(raw.bookTotal)
  base.bookCarryingAmount = parseNum(raw.bookCarryingAmount ?? raw.carryingAmount)
  base.remark = String(raw.remark ?? '')

  return enrichItem(base)
}

function safeParseJson<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as T
  } catch {
    return null
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseG4SppiReconciliationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export function useG4SppiReconciliation(opts: UseG4SppiReconciliationOptions) {
  const { allResponses, debouncedSave, isReadonly } = opts

  const activeTab = ref<ReconciliationTab>('countDate')
  const selectedRowIndex = ref(0)
  const items = ref<ReconciliationItem[]>([enrichItem(createEmptyItem('', 1))])
  const auditConclusion = ref('')
  const header = ref<ReconciliationHeader>({
    countDate: '',
    balanceSheetDate: '',
  })

  const summary = computed<ReconciliationSummary>(() => ({
    countQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.countQuantity))),
    countFaceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.countFaceValue))),
    countTotalTotal: calcSumColumn(items.value.map((i) => i.countTotal)),
    increaseQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.increaseQuantity))),
    increaseFaceTotalTotal: calcSumColumn(items.value.map((i) => parseNum(i.increaseFaceTotal))),
    decreaseQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.decreaseQuantity))),
    decreaseFaceTotalTotal: calcSumColumn(items.value.map((i) => parseNum(i.decreaseFaceTotal))),
    reportQuantityTotal: calcSumColumn(items.value.map((i) => i.reportQuantity)),
    reportFaceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.reportFaceValue))),
    reportTotalTotal: calcSumColumn(items.value.map((i) => i.reportTotal)),
    bookQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookQuantity))),
    bookFaceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookFaceValue))),
    bookTotalTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookTotal))),
    bookCarryingAmountTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookCarryingAmount))),
    varianceQuantityTotal: calcSumColumn(items.value.map((i) => i.varianceQuantity)),
    varianceTotal: calcSumColumn(items.value.map((i) => i.variance)),
  }))

  /** 差异高亮：数量或面值总额任一侧不平衡 */
  const varianceHighlights = computed<boolean[]>(() =>
    items.value.map(
      (item) =>
        !isReconciliationFullyBalanced(
          item.reportQuantity,
          item.bookQuantity,
          item.reportTotal,
          item.bookTotal,
        ),
    ),
  )

  const stats = computed<ReconciliationStats>(() => {
    const withDiff = varianceHighlights.value.filter(Boolean).length
    const missingRemark = items.value.filter(
      (item, idx) => varianceHighlights.value[idx] && !(item.remark || '').trim(),
    ).length
    return { total: items.value.length, withDiff, missingRemark }
  })

  function readStoredRaw(itemId: string): string | null {
    const item = allResponses.value.get(itemId)
    const c = item?.conclusion
    if (c != null && String(c).trim() !== '') return String(c)
    const r = item?.remark
    if (r != null && String(r).trim() !== '') return String(r)
    return null
  }

  function loadFromResponses(): void {
    const parsed = safeParseJson<Record<string, unknown>[]>(readStoredRaw(STORAGE_KEY_ITEMS))
    if (parsed && Array.isArray(parsed) && parsed.length > 0) {
      items.value = parsed.map((p, i) => migrateLegacyItem(p, i))
    }

    auditConclusion.value = readStoredRaw(STORAGE_KEY_AUDIT_CONCLUSION) || ''

    const headerParsed = safeParseJson<Partial<ReconciliationHeader>>(readStoredRaw(STORAGE_KEY_HEADER))
    if (headerParsed) {
      header.value = {
        countDate: String(headerParsed.countDate ?? ''),
        balanceSheetDate: String(headerParsed.balanceSheetDate ?? ''),
      }
    }
  }

  watch(
    () => readStoredRaw(STORAGE_KEY_ITEMS),
    () => loadFromResponses(),
    { immediate: true },
  )

  watch(activeTab, () => {
    if (selectedRowIndex.value >= items.value.length) {
      selectedRowIndex.value = 0
    }
  })

  function persistItems(): void {
    if (isReadonly.value) return
    const json = JSON.stringify(items.value)
    debouncedSave(STORAGE_KEY_ITEMS, { conclusion: json, remark: json })
  }

  function persistAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_CONCLUSION, { conclusion: null, remark: auditConclusion.value })
  }

  function persistHeader(): void {
    if (isReadonly.value) return
    const json = JSON.stringify(header.value)
    debouncedSave(STORAGE_KEY_HEADER, { conclusion: json, remark: json })
  }

  function updateHeader(patch: Partial<ReconciliationHeader>): void {
    if (isReadonly.value) return
    header.value = { ...header.value, ...patch }
    persistHeader()
  }

  function updateItem(id: string, patch: Partial<ReconciliationItem>): void {
    if (isReadonly.value) return
    items.value = items.value.map((item) => {
      if (item.id !== id) return item
      return enrichItem({ ...item, ...patch })
    })
    persistItems()
  }

  function selectRow(index: number): void {
    if (index >= 0 && index < items.value.length) {
      selectedRowIndex.value = index
    }
  }

  function switchTab(tab: ReconciliationTab): void {
    activeTab.value = tab
  }

  async function addItem(): Promise<void> {
    if (isReadonly.value) return
    if (items.value.length >= MAX_ROWS) {
      ElMessageBox.alert(`行数已达上限（${MAX_ROWS}行），无法继续新增。`, '提示')
      return
    }
    try {
      const { value: name } = await ElMessageBox.prompt('请输入证券名称', '新增倒轧行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '证券名称不能为空',
      })
      const seq = items.value.length + 1
      items.value = [...items.value, enrichItem(createEmptyItem(name, seq))]
      selectedRowIndex.value = items.value.length - 1
      persistItems()
    } catch {
      /* cancelled */
    }
  }

  function removeItem(id: string): void {
    if (isReadonly.value || items.value.length <= 1) return
    const idx = items.value.findIndex((i) => i.id === id)
    items.value = items.value
      .filter((item) => item.id !== id)
      .map((item, i) => ({ ...item, seq: i + 1 }))
    if (selectedRowIndex.value >= items.value.length) {
      selectedRowIndex.value = items.value.length - 1
    } else if (idx <= selectedRowIndex.value && selectedRowIndex.value > 0) {
      selectedRowIndex.value--
    }
    persistItems()
  }

  function setAuditConclusion(value: string): void {
    if (isReadonly.value) return
    auditConclusion.value = value
    persistAuditConclusion()
  }

  /**
   * 从 G4-7 盘点表一键带出：证券名称/面值/数量/利率/到期日 → 盘点日实存区段
   * 同时尽量带出盘点日期头信息。
   */
  function importFromInventory(): void {
    if (isReadonly.value) return
    const invResp = allResponses.value.get('G4-7-items')
    const invParsed = safeParseJson<
      Array<{
        securitiesName?: string
        faceValue?: number
        quantity?: number
        couponRate?: number
        maturityDate?: string
      }>
    >(invResp?.remark)
    if (!invParsed || !Array.isArray(invParsed) || invParsed.length === 0) {
      ElMessageBox.alert('未找到 G4-7 盘点表数据，请先编制有价证券盘点表。', '提示')
      return
    }

    const filled = invParsed
      .filter((r) => (r.securitiesName || '').trim())
      .map((r, idx) =>
        enrichItem({
          ...createEmptyItem(String(r.securitiesName || '').trim(), idx + 1),
          countFaceValue: parseNum(r.faceValue),
          countQuantity: parseNum(r.quantity),
          countCouponRate: parseNum(r.couponRate),
          countMaturityDate: String(r.maturityDate || ''),
          reportFaceValue: parseNum(r.faceValue),
          bookFaceValue: parseNum(r.faceValue),
        }),
      )

    if (filled.length === 0) {
      ElMessageBox.alert('G4-7 中没有有效的证券名称行。', '提示')
      return
    }

    // 尝试同步盘点日
    const invHeader = safeParseJson<{ countDate?: string }>(
      allResponses.value.get('G4-7-header')?.remark,
    )
    if (invHeader?.countDate && !header.value.countDate) {
      header.value = { ...header.value, countDate: String(invHeader.countDate) }
      persistHeader()
    }

    items.value = filled
    selectedRowIndex.value = 0
    activeTab.value = 'countDate'
    persistItems()
    ElMessage.success(`已从 G4-7 带出 ${filled.length} 行盘点日实存`)
  }

  return {
    activeTab,
    selectedRowIndex,
    items,
    summary,
    stats,
    varianceHighlights,
    auditConclusion,
    header,
    updateHeader,
    updateItem,
    selectRow,
    switchTab,
    addItem,
    removeItem,
    setAuditConclusion,
    importFromInventory,
    loadFromResponses,
    persistItems,
  }
}

export default useG4SppiReconciliation
