/**
 * useG6SppiReconciliation — G6-10 盘点倒轧表（18列→2区段Tab）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 10.3
 * Requirements: 6.2, 6.3, 6.4
 *
 * 职责：
 * - ReconciliationItem / ChangeDetailItem 行数据模型管理
 * - 2区段Tab行同步（activeTab + selectedRowIndex）
 *   - Tab1: 倒轧计算(10列)
 *   - Tab2: 增减明细(8列)
 * - calcInventoryRollForward / calcInventoryVariance 公式调用
 * - 差异必填校验：|差异|>0 时差异原因必填
 * - 动态行增删（ElMessageBox.prompt 输入证券名称）
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { calcInventoryRollForward, calcInventoryVariance, parseNum } from '@/composables/useG6SppiFormulaEngine'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

/** Tab1: 倒轧计算行（10列） */
export interface ReconciliationItem {
  id: string
  seq: number
  securitiesName: string
  countDateQuantity: number       // 盘点日数量
  changeQuantity: number          // 盘点日→基准日增减
  reportDateQuantity: number      // 基准日数量（公式: countDateQuantity + changeQuantity）
  bookQuantity: number            // 账面数量
  variance: number                // 差异（公式: reportDateQuantity - bookQuantity）
  varianceReason: string          // 差异原因（|差异|>0必填）
  varianceConclusion: string      // 差异结论
  indexRef: string                // 索引
  remark: string                  // 备注
}

/** Tab2: 增减明细行（8列） */
export interface ChangeDetailItem {
  id: string
  securitiesName: string          // 证券名称
  date: string                    // 日期
  transactionType: 'buy' | 'sell' | 'mature' | 'transfer' | ''  // 交易类型
  quantity: number                // 数量
  amount: number                  // 金额
  voucherNo: string               // 凭证号
  handler: string                 // 经办人
  remark: string                  // 备注
}

/** 完整数据结构 */
export interface ReconciliationData {
  activeTab: 'rollForward' | 'changeDetail'
  selectedRowIndex: number
  items: ReconciliationItem[]
  changeDetails: ChangeDetailItem[]
  auditConclusion: string
}

// ─── 交易类型选项 ────────────────────────────────────────────────────────────

export const TRANSACTION_TYPE_OPTIONS = [
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
  { value: 'mature', label: '到期' },
  { value: 'transfer', label: '转让' },
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiReconciliation() {
  const items = ref<ReconciliationItem[]>([])
  const changeDetails = ref<ChangeDetailItem[]>([])
  const activeTab = ref<'rollForward' | 'changeDetail'>('rollForward')
  const selectedRowIndex = ref(0)
  const auditConclusion = ref('')

  // ─── 公式计算 ──────────────────────────────────────────────────────────────

  /** 重算指定行的公式列 */
  function recalcRow(row: ReconciliationItem): void {
    row.reportDateQuantity = calcInventoryRollForward(
      parseNum(row.countDateQuantity),
      parseNum(row.changeQuantity),
    )
    row.variance = calcInventoryVariance(
      row.reportDateQuantity,
      parseNum(row.bookQuantity),
    )
  }

  // watch items 变化时自动重算公式
  watch(items, (newItems) => {
    for (const row of newItems) {
      recalcRow(row)
    }
  }, { deep: true })

  // ─── 差异高亮逻辑 ─────────────────────────────────────────────────────────

  /** 判断行是否有差异需高亮（|variance| > 0） */
  function hasVariance(row: ReconciliationItem): boolean {
    return Math.abs(parseNum(row.variance)) > 0
  }

  /** 获取差异列样式（红色高亮） */
  function getVarianceCellStyle(row: ReconciliationItem): Record<string, string> {
    if (hasVariance(row)) {
      return { backgroundColor: '#fef2f2', color: '#dc2626', fontWeight: '600' }
    }
    return {}
  }

  // ─── 差异必填校验 ──────────────────────────────────────────────────────────

  /** 判断行差异原因是否缺失（|差异|>0 时差异原因必填） */
  function isVarianceReasonMissing(row: ReconciliationItem): boolean {
    return hasVariance(row) && !row.varianceReason.trim()
  }

  /** 全表差异必填校验 */
  const varianceValidationErrors = computed(() => {
    const issues: Array<{ row: ReconciliationItem; index: number }> = []
    for (let i = 0; i < items.value.length; i++) {
      if (isVarianceReasonMissing(items.value[i])) {
        issues.push({ row: items.value[i], index: i })
      }
    }
    return issues
  })

  /** 是否通过差异校验（无差异必填缺失） */
  const isVarianceValid = computed(() => varianceValidationErrors.value.length === 0)

  // ─── 行 CRUD（Tab1: 倒轧计算） ────────────────────────────────────────────

  async function addItem(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增倒轧计算行',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
        },
      )
      if (!value?.trim()) return

      const newItem: ReconciliationItem = {
        id: `recon-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        seq: items.value.length + 1,
        securitiesName: value.trim(),
        countDateQuantity: 0,
        changeQuantity: 0,
        reportDateQuantity: 0,
        bookQuantity: 0,
        variance: 0,
        varianceReason: '',
        varianceConclusion: '',
        indexRef: '',
        remark: '',
      }
      items.value.push(newItem)
      selectedRowIndex.value = items.value.length - 1
      ElMessage.success(`已新增"${value.trim()}"`)
    } catch {
      // 用户取消
    }
  }

  async function removeItem(id: string): Promise<void> {
    const row = items.value.find(r => r.id === id)
    if (!row) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${row.securitiesName}"？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      items.value = items.value.filter(r => r.id !== id)
      items.value.forEach((r, i) => { r.seq = i + 1 })
      if (selectedRowIndex.value >= items.value.length) {
        selectedRowIndex.value = Math.max(0, items.value.length - 1)
      }
      ElMessage.success(`已删除"${row.securitiesName}"`)
    } catch {
      // 用户取消
    }
  }

  // ─── 行 CRUD（Tab2: 增减明细） ─────────────────────────────────────────────

  async function addChangeDetail(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入证券名称',
        '新增增减明细',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '证券名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
        },
      )
      if (!value?.trim()) return

      const newDetail: ChangeDetailItem = {
        id: `cd-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        securitiesName: value.trim(),
        date: '',
        transactionType: '',
        quantity: 0,
        amount: 0,
        voucherNo: '',
        handler: '',
        remark: '',
      }
      changeDetails.value.push(newDetail)
      ElMessage.success(`已新增增减明细"${value.trim()}"`)
    } catch {
      // 用户取消
    }
  }

  async function removeChangeDetail(id: string): Promise<void> {
    const detail = changeDetails.value.find(r => r.id === id)
    if (!detail) return
    try {
      await ElMessageBox.confirm(
        `确认删除"${detail.securitiesName}"的增减明细？`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      changeDetails.value = changeDetails.value.filter(r => r.id !== id)
      ElMessage.success(`已删除增减明细"${detail.securitiesName}"`)
    } catch {
      // 用户取消
    }
  }

  // ─── 行同步 ───────────────────────────────────────────────────────────────

  /** 选中行（Tab1同步） */
  function selectRow(index: number): void {
    if (index >= 0 && index < items.value.length) {
      selectedRowIndex.value = index
    }
  }

  // ─── Tab 切换 ──────────────────────────────────────────────────────────────

  function switchTab(tab: 'rollForward' | 'changeDetail'): void {
    activeTab.value = tab
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  function loadData(data: ReconciliationData | null): void {
    if (!data) {
      items.value = []
      changeDetails.value = []
      auditConclusion.value = ''
      activeTab.value = 'rollForward'
      selectedRowIndex.value = 0
      return
    }

    items.value = (data.items || []).map((r, i) => {
      const item: ReconciliationItem = {
        id: r.id || `recon-${Date.now()}-${i}`,
        seq: i + 1,
        securitiesName: r.securitiesName || '',
        countDateQuantity: parseNum(r.countDateQuantity),
        changeQuantity: parseNum(r.changeQuantity),
        reportDateQuantity: 0,
        bookQuantity: parseNum(r.bookQuantity),
        variance: 0,
        varianceReason: r.varianceReason || '',
        varianceConclusion: r.varianceConclusion || '',
        indexRef: r.indexRef || '',
        remark: r.remark || '',
      }
      recalcRow(item)
      return item
    })

    changeDetails.value = (data.changeDetails || []).map((d, i) => ({
      id: d.id || `cd-${Date.now()}-${i}`,
      securitiesName: d.securitiesName || '',
      date: d.date || '',
      transactionType: d.transactionType || '',
      quantity: parseNum(d.quantity),
      amount: parseNum(d.amount),
      voucherNo: d.voucherNo || '',
      handler: d.handler || '',
      remark: d.remark || '',
    }))

    auditConclusion.value = data.auditConclusion || ''
    activeTab.value = data.activeTab || 'rollForward'
    selectedRowIndex.value = data.selectedRowIndex || 0
  }

  function toJSON(): ReconciliationData {
    return {
      activeTab: activeTab.value,
      selectedRowIndex: selectedRowIndex.value,
      items: items.value.map(r => ({ ...r })),
      changeDetails: changeDetails.value.map(d => ({ ...d })),
      auditConclusion: auditConclusion.value,
    }
  }

  // ─── 汇总统计 ──────────────────────────────────────────────────────────────

  /** 有差异的行数 */
  const varianceCount = computed(() => items.value.filter(hasVariance).length)

  /** 增减明细总数 */
  const changeDetailCount = computed(() => changeDetails.value.length)

  return {
    // State
    items,
    changeDetails,
    activeTab,
    selectedRowIndex,
    auditConclusion,
    // Computed
    varianceValidationErrors,
    isVarianceValid,
    varianceCount,
    changeDetailCount,
    // Methods
    recalcRow,
    hasVariance,
    getVarianceCellStyle,
    isVarianceReasonMissing,
    addItem,
    removeItem,
    addChangeDetail,
    removeChangeDetail,
    selectRow,
    switchTab,
    loadData,
    toJSON,
  }
}

export default useG6SppiReconciliation
