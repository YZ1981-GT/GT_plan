/**
 * useI5Detail — I5-2 其他非流动资产明细表 composable（26列3区段Tab，63行）
 *
 * 26列宽表拆分为3区段Tab：
 *   Section 0 "基础"：项目名称/资产类型/发生日期/到期日期/摘要/合同编号/对方单位/索引号
 *   Section 1 "金额"：期初余额/本期增加/本期减少/期末余额(公式)/增加原因/减少原因/原始金额/累计金额/净值
 *   Section 2 "检查"：凭证号/凭证日期/检查方法/检查结果/结论/是否异常/备注/复核标记/状态
 *
 * 核心功能：
 * - Tab切换时保持行同步（activeRowIndex统一）
 * - 公式自动计算（调用 useI5FormulaEngine）：
 *   · 期末 = calcAssetEndBalance(期初, 增加, 减少) — 标准资产类
 * - 合计行联动审定表I5-1（calcSubtotal → useI5CrossSheet）
 * - 动态行CRUD（添加/删除）：ElMessageBox.prompt输入项目名称
 * - 持久化：rows JSON → checklist_responses item_id "I5-2-rows"
 * - 导入导出：importRows / exportRows
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 3.3
 * Requirements: 3.1-3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcAssetEndBalance, calcSubtotal } from './useI5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I5-2 明细行完整结构（26列拆分到3区段） */
export interface I5DetailRow {
  rowId: string

  // ── Section 0 基础区段（8列）──
  name: string                  // 项目名称
  category: string              // 资产类型
  incurredDate: string          // 发生日期（YYYY-MM-DD）
  maturityDate: string          // 到期日期（YYYY-MM-DD）
  summary: string               // 摘要
  contractNo: string            // 合同编号
  counterparty: string          // 对方单位
  indexNo: string               // 索引号

  // ── Section 1 金额区段（9列，含1公式列）──
  beginBalance: number          // 期初余额
  increase: number              // 本期增加
  decrease: number              // 本期减少
  endBalance: number            // 期末余额（公式：期初+增加-减少）
  increaseReason: string        // 增加原因
  decreaseReason: string        // 减少原因
  originalAmount: number        // 原始金额
  accumulatedAmount: number     // 累计金额
  netValue: number              // 净值

  // ── Section 2 检查区段（9列）──
  voucherRef: string            // 凭证号
  voucherDate: string           // 凭证日期（YYYY-MM-DD）
  checkMethod: string           // 检查方法
  checkResult: string           // 检查结果
  conclusion: string            // 结论（正常/异常/待确认）
  isAbnormal: boolean           // 是否异常
  remark: string                // 备注
  reviewMark: string            // 复核标记
  status: string                // 状态（已检查/未检查/部分检查）
}

/** 3区段Tab索引 */
export type I5DetailSection = 0 | 1 | 2

/** 3区段Tab标签 */
export const I5_DETAIL_SECTION_LABELS = ['基础', '金额', '检查'] as const

/** 合计行结构（数值列的SUM） */
export interface I5DetailSubtotals {
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  originalAmount: number
  accumulatedAmount: number
  netValue: number
}

/** 列定义 */
export interface I5DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'date' | 'select' | 'formula' | 'boolean'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I5-2-rows'

const CATEGORY_OPTIONS = ['预付款项', '待抵扣税额', '合同资产', '押金保证金', '其他']
const CONCLUSION_OPTIONS = ['正常', '异常', '待确认']
const STATUS_OPTIONS = ['已检查', '未检查', '部分检查']
const CHECK_METHOD_OPTIONS = ['函证', '检查原始凭证', '检查合同', '分析性程序', '其他']

// ─── Column Definitions ──────────────────────────────────────────────────────

/** Section 0 基础区段列定义（8列） */
const BASIC_COLUMNS: I5DetailColumn[] = [
  { key: 'name', label: '项目名称', width: 180, editable: true, type: 'text' },
  { key: 'category', label: '资产类型', width: 120, editable: true, type: 'select', options: CATEGORY_OPTIONS },
  { key: 'incurredDate', label: '发生日期', width: 120, editable: true, type: 'date' },
  { key: 'maturityDate', label: '到期日期', width: 120, editable: true, type: 'date' },
  { key: 'summary', label: '摘要', width: 180, editable: true, type: 'text' },
  { key: 'contractNo', label: '合同编号', width: 130, editable: true, type: 'text' },
  { key: 'counterparty', label: '对方单位', width: 150, editable: true, type: 'text' },
  { key: 'indexNo', label: '索引号', width: 100, editable: true, type: 'text' },
]

/** Section 1 金额区段列定义（9列，含1公式列） */
const AMOUNT_COLUMNS: I5DetailColumn[] = [
  { key: 'name', label: '项目名称', width: 180, editable: false, type: 'text' },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'increase', label: '本期增加', width: 120, editable: true, type: 'number' },
  { key: 'decrease', label: '本期减少', width: 120, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+增加-减少' },
  { key: 'increaseReason', label: '增加原因', width: 150, editable: true, type: 'text' },
  { key: 'decreaseReason', label: '减少原因', width: 150, editable: true, type: 'text' },
  { key: 'originalAmount', label: '原始金额', width: 130, editable: true, type: 'number' },
  { key: 'accumulatedAmount', label: '累计金额', width: 130, editable: true, type: 'number' },
  { key: 'netValue', label: '净值', width: 120, editable: true, type: 'number' },
]

/** Section 2 检查区段列定义（9列） */
const CHECK_COLUMNS: I5DetailColumn[] = [
  { key: 'name', label: '项目名称', width: 180, editable: false, type: 'text' },
  { key: 'voucherRef', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'voucherDate', label: '凭证日期', width: 120, editable: true, type: 'date' },
  { key: 'checkMethod', label: '检查方法', width: 130, editable: true, type: 'select', options: CHECK_METHOD_OPTIONS },
  { key: 'checkResult', label: '检查结果', width: 180, editable: true, type: 'text' },
  { key: 'conclusion', label: '结论', width: 100, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'isAbnormal', label: '是否异常', width: 90, editable: true, type: 'boolean' },
  { key: 'remark', label: '备注', width: 180, editable: true, type: 'text' },
  { key: 'reviewMark', label: '复核标记', width: 100, editable: true, type: 'text' },
  { key: 'status', label: '状态', width: 100, editable: true, type: 'select', options: STATUS_OPTIONS },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5Detail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    /** 审定表小计（用于交叉验证） */
    adjBeginSubtotal?: Ref<number>
    adjEndSubtotal?: Ref<number>
    /** 保存回调 */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 明细行数据 */
  const rows = ref<I5DetailRow[]>([])

  /** 当前激活的区段Tab（0=基础, 1=金额, 2=检查） */
  const activeSection = ref<I5DetailSection>(0)

  /** 当前选中行索引（跨Tab同步） */
  const activeRowIndex = ref<number>(-1)

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) {
      rows.value = []
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows.value = parsed.map(_normalizeRow)
      } else {
        rows.value = []
      }
    } catch {
      rows.value = []
    }
  }

  function _normalizeRow(raw: any): I5DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      // Section 0 基础
      name: raw.name ?? '',
      category: raw.category ?? '',
      incurredDate: raw.incurredDate ?? '',
      maturityDate: raw.maturityDate ?? '',
      summary: raw.summary ?? '',
      contractNo: raw.contractNo ?? '',
      counterparty: raw.counterparty ?? '',
      indexNo: raw.indexNo ?? '',
      // Section 1 金额
      beginBalance: Number(raw.beginBalance) || 0,
      increase: Number(raw.increase) || 0,
      decrease: Number(raw.decrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      increaseReason: raw.increaseReason ?? '',
      decreaseReason: raw.decreaseReason ?? '',
      originalAmount: Number(raw.originalAmount) || 0,
      accumulatedAmount: Number(raw.accumulatedAmount) || 0,
      netValue: Number(raw.netValue) || 0,
      // Section 2 检查
      voucherRef: raw.voucherRef ?? '',
      voucherDate: raw.voucherDate ?? '',
      checkMethod: raw.checkMethod ?? '',
      checkResult: raw.checkResult ?? '',
      conclusion: raw.conclusion ?? '',
      isAbnormal: raw.isAbnormal === true,
      remark: raw.remark ?? '',
      reviewMark: raw.reviewMark ?? '',
      status: raw.status ?? '未检查',
    }
  }

  // ─── Formula Recalculation ─────────────────────────────────────────────────

  /**
   * 对指定行重算公式列：
   * - endBalance = calcAssetEndBalance(beginBalance, increase, decrease)
   */
  function _recalcRow(row: I5DetailRow): void {
    row.endBalance = calcAssetEndBalance(row.beginBalance, row.increase, row.decrease)
  }

  /** 对所有行重算公式 */
  function recalcAll(): void {
    for (const row of rows.value) {
      _recalcRow(row)
    }
  }

  // ─── Computed: 合计行（Req 3.2 合计行联动审定表）───────────────────────────

  const subtotals: ComputedRef<I5DetailSubtotals> = computed(() => {
    const r = rows.value
    return {
      beginBalance: calcSubtotal(r.map((x) => x.beginBalance)),
      increase: calcSubtotal(r.map((x) => x.increase)),
      decrease: calcSubtotal(r.map((x) => x.decrease)),
      endBalance: calcSubtotal(r.map((x) => x.endBalance)),
      originalAmount: calcSubtotal(r.map((x) => x.originalAmount)),
      accumulatedAmount: calcSubtotal(r.map((x) => x.accumulatedAmount)),
      netValue: calcSubtotal(r.map((x) => x.netValue)),
    }
  })

  // ─── Section 切换 + 行同步 ─────────────────────────────────────────────────

  function switchSection(section: I5DetailSection): void {
    activeSection.value = section
  }

  function setActiveRow(index: number): void {
    activeRowIndex.value = index
  }

  // ─── updateCell: 编辑单元格 ────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return

    // 设置值
    ;(row as any)[field] = value

    // 重算公式列
    _recalcRow(row)

    // 持久化
    _persist()
  }

  // ─── addRow: 动态行添加（Req 3.3 动态行+导入导出）─────────────────────────

  /**
   * 添加动态行：先弹 ElMessageBox.prompt 输入项目名称确认后创建。
   */
  async function addRow(): Promise<void> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入其他非流动资产项目名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：预付购房款-XX项目',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      if (!name?.trim()) return

      const newRow: I5DetailRow = {
        rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        // Section 0 基础
        name: name.trim(),
        category: '',
        incurredDate: '',
        maturityDate: '',
        summary: '',
        contractNo: '',
        counterparty: '',
        indexNo: '',
        // Section 1 金额
        beginBalance: 0,
        increase: 0,
        decrease: 0,
        endBalance: 0,
        increaseReason: '',
        decreaseReason: '',
        originalAmount: 0,
        accumulatedAmount: 0,
        netValue: 0,
        // Section 2 检查
        voucherRef: '',
        voucherDate: '',
        checkMethod: '',
        checkResult: '',
        conclusion: '',
        isAbnormal: false,
        remark: '',
        reviewMark: '',
        status: '未检查',
      }

      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
    } catch {
      // 用户取消
    }
  }

  // ─── removeRow: 删除行 ─────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  // ─── importRows / exportRows（供 useI5ImportExport 调用）───────────────────

  /**
   * 批量导入行数据（覆盖现有行），自动重算公式并持久化。
   */
  function importRows(importedData: any[]): void {
    rows.value = importedData.map((raw) => {
      const row = _normalizeRow(raw)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  /** 获取当前行数据（供导出使用） */
  function exportRows(): I5DetailRow[] {
    return [...rows.value]
  }

  // ─── segments: 3区段Tab列配置 ──────────────────────────────────────────────

  const segments = {
    basic: BASIC_COLUMNS,
    amount: AMOUNT_COLUMNS,
    check: CHECK_COLUMNS,
  }

  /** 3区段Tab定义 */
  const sections = [
    { key: 0 as I5DetailSection, label: '基础', columns: BASIC_COLUMNS },
    { key: 1 as I5DetailSection, label: '金额', columns: AMOUNT_COLUMNS },
    { key: 2 as I5DetailSection, label: '检查', columns: CHECK_COLUMNS },
  ]

  /** 当前Section对应的列配置 */
  const activeColumns = computed(() => {
    return sections.find((s) => s.key === activeSection.value)?.columns ?? BASIC_COLUMNS
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    activeSection,
    activeRowIndex,

    // Computed
    subtotals,
    activeColumns,

    // Segment column definitions
    segments,
    sections,

    // Actions — Section & Row同步
    switchSection,
    setActiveRow,

    // Actions — Cell编辑
    updateCell,
    recalcAll,

    // Actions — 动态行
    addRow,
    removeRow,

    // Actions — 导入导出
    importRows,
    exportRows,
  }
}

export default useI5Detail
