/**
 * useG4SppiReconciliation — G4-8 盘点倒轧表（3区段Tab + 行同步 + 差异高亮）
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 7.3
 * Requirements: 5.1~5.10, 6.3~6.8
 *
 * 职责：
 * - 管理 ReconciliationItem[] 响应式数据（18个字段）
 * - 3区段Tab: 盘点日实存(6列) / 增减变动(2列) / 报表日实存+差异(10列)
 * - activeTab ref 控制当前Tab
 * - selectedRowIndex ref 跨Tab行同步
 * - 公式: calcInventoryTotal / calcReportDateQuantity / calcReportDateTotal / calcReconciliationVariance
 * - 差异高亮: isReconciliationBalanced → |variance|>0 → 红色+备注必填
 * - 合计行: calcSumColumn
 * - 动态行增删（ElMessageBox.prompt 输入证券名称）
 * - Tab切换时保持 selectedRowIndex（超范围重置为0）
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcInventoryTotal,
  calcReportDateQuantity,
  calcReportDateTotal,
  calcReconciliationVariance,
  isReconciliationBalanced,
  calcSumColumn,
  parseNum,
} from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ReconciliationTab = 'countDate' | 'changes' | 'reportDate'

export interface ReconciliationItem {
  id: string
  seq: number
  // ══ 区段1: 盘点日实存(6列) ══
  securitiesName: string
  countQuantity: number
  countFaceValue: number
  countTotal: number              // 公式: 面值 × 数量 (2dp)
  countCouponRate: number
  countMaturityDate: string
  // ══ 区段2: 增减变动(2列) ══
  changeQuantity: number          // 正=增加，负=减少
  changeFaceValueTotal: number
  // ══ 区段3: 报表日实存+差异(10列) ══
  reportQuantity: number          // 公式: 盘点日数量 + 增减数量
  reportFaceValue: number
  reportTotal: number             // 公式: 报表日面值 × 报表日数量 (2dp)
  reportCouponRate: number
  reportMaturityDate: string
  bookQuantity: number
  bookFaceValue: number
  bookTotal: number
  variance: number                // 公式: 报表日总计 - 账面结存总计 (2dp)
  remark: string                  // |差异|>0 时必填
}

export interface ReconciliationSummary {
  // 盘点日实存合计
  countQuantityTotal: number
  countFaceValueTotal: number
  countTotalTotal: number
  // 增减变动合计
  changeQuantityTotal: number
  changeFaceValueTotalTotal: number
  // 报表日合计
  reportQuantityTotal: number
  reportFaceValueTotal: number
  reportTotalTotal: number
  bookQuantityTotal: number
  bookFaceValueTotal: number
  bookTotalTotal: number
  varianceTotal: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY_ITEMS = 'G4-8-items'
const STORAGE_KEY_AUDIT_CONCLUSION = 'G4-8-audit-conclusion'

const MAX_ROWS = 200

export const TAB_OPTIONS: Array<{ key: ReconciliationTab; label: string }> = [
  { key: 'countDate', label: '盘点日实存' },
  { key: 'changes', label: '增减变动' },
  { key: 'reportDate', label: '报表日实存+差异' },
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
    changeQuantity: 0,
    changeFaceValueTotal: 0,
    reportQuantity: 0,
    reportFaceValue: 0,
    reportTotal: 0,
    reportCouponRate: 0,
    reportMaturityDate: '',
    bookQuantity: 0,
    bookFaceValue: 0,
    bookTotal: 0,
    variance: 0,
    remark: '',
  }
}

/** 公式链求解：一次性计算所有派生字段 */
function enrichItem(item: ReconciliationItem): ReconciliationItem {
  const countTotal = calcInventoryTotal(item.countFaceValue, item.countQuantity)
  const reportQuantity = calcReportDateQuantity(item.countQuantity, item.changeQuantity)
  const reportTotal = calcReportDateTotal(item.reportFaceValue, reportQuantity)
  const variance = calcReconciliationVariance(reportTotal, item.bookTotal)

  return {
    ...item,
    countTotal,
    reportQuantity,
    reportTotal,
    variance,
  }
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

  // ─── 3区段Tab ────────────────────────────────────────────────────────────
  const activeTab = ref<ReconciliationTab>('countDate')

  // ─── 行同步 ──────────────────────────────────────────────────────────────
  const selectedRowIndex = ref(0)

  // ─── 数据 ────────────────────────────────────────────────────────────────
  const items = ref<ReconciliationItem[]>([enrichItem(createEmptyItem('', 1))])

  // ─── 审计结论 ────────────────────────────────────────────────────────────
  const auditConclusion = ref('')

  // ─── 合计行（computed） ──────────────────────────────────────────────────
  const summary = computed<ReconciliationSummary>(() => ({
    // 盘点日实存
    countQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.countQuantity))),
    countFaceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.countFaceValue))),
    countTotalTotal: calcSumColumn(items.value.map((i) => i.countTotal)),
    // 增减变动
    changeQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.changeQuantity))),
    changeFaceValueTotalTotal: calcSumColumn(items.value.map((i) => parseNum(i.changeFaceValueTotal))),
    // 报表日实存+差异
    reportQuantityTotal: calcSumColumn(items.value.map((i) => i.reportQuantity)),
    reportFaceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.reportFaceValue))),
    reportTotalTotal: calcSumColumn(items.value.map((i) => i.reportTotal)),
    bookQuantityTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookQuantity))),
    bookFaceValueTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookFaceValue))),
    bookTotalTotal: calcSumColumn(items.value.map((i) => parseNum(i.bookTotal))),
    varianceTotal: calcSumColumn(items.value.map((i) => i.variance)),
  }))

  /** 差异高亮标志（每行） */
  const varianceHighlights = computed<boolean[]>(() =>
    items.value.map((item) => !isReconciliationBalanced(item.reportTotal, item.bookTotal)),
  )

  // ─── 从 allResponses 加载 ────────────────────────────────────────────────

  function loadFromResponses(): void {
    const itemsResp = allResponses.value.get(STORAGE_KEY_ITEMS)
    const parsed = safeParseJson<ReconciliationItem[]>(itemsResp?.remark)
    if (parsed && Array.isArray(parsed) && parsed.length > 0) {
      items.value = parsed.map(enrichItem)
    }

    const concResp = allResponses.value.get(STORAGE_KEY_AUDIT_CONCLUSION)
    auditConclusion.value = concResp?.remark || ''
  }

  // allResponses 异步加载完成后回填
  watch(
    () => allResponses.value.get(STORAGE_KEY_ITEMS)?.remark,
    () => loadFromResponses(),
    { immediate: true },
  )

  // ─── Tab切换时保持行索引 ──────────────────────────────────────────────────

  watch(activeTab, () => {
    // 切换Tab后若行索引超范围则重置为0
    if (selectedRowIndex.value >= items.value.length) {
      selectedRowIndex.value = 0
    }
  })

  // ─── 持久化 ──────────────────────────────────────────────────────────────

  function persistItems(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_ITEMS, { remark: JSON.stringify(items.value) })
  }

  function persistAuditConclusion(): void {
    if (isReadonly.value) return
    debouncedSave(STORAGE_KEY_AUDIT_CONCLUSION, { remark: auditConclusion.value })
  }

  // ─── 操作 ────────────────────────────────────────────────────────────────

  function updateItem(id: string, patch: Partial<ReconciliationItem>): void {
    if (isReadonly.value) return
    items.value = items.value.map((item) => {
      if (item.id !== id) return item
      const updated = { ...item, ...patch }
      return enrichItem(updated)
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
      const { value: name } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增倒轧行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
        },
      )
      const seq = items.value.length + 1
      items.value = [...items.value, enrichItem(createEmptyItem(name, seq))]
      // 选中新增的行
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
    // 调整选中行索引
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

  return {
    // Tab
    activeTab,
    selectedRowIndex,
    // 数据
    items,
    summary,
    varianceHighlights,
    auditConclusion,
    // 操作
    updateItem,
    selectRow,
    switchTab,
    addItem,
    removeItem,
    setAuditConclusion,
    // 加载
    loadFromResponses,
    // 持久化
    persistItems,
  }
}

export default useG4SppiReconciliation
