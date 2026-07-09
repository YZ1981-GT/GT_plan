/**
 * useI4Detail — I4-2 长期待摊费用明细表 composable（25列3区段Tab）
 *
 * 25列宽表拆分为3区段Tab：
 *   Section 0 "基础区段"：项目名称/发生日期/费用类型/原始金额/科目分类/合同编号/起始日/结束日
 *   Section 1 "摊销区段"：摊销方法/期限(月)/已摊月数/累计摊销/本期摊销/月摊销额(公式)/摊销起始月/上期余额
 *   Section 2 "余额区段"：期初/本期增加/本期减少/期末(公式)/剩余月数(公式)/摊销进度%(公式)/备注/索引号/状态
 *
 * 核心功能：
 * - Tab切换时保持行同步（activeRowIndex统一）
 * - 公式自动计算（调用 useI4FormulaEngine + useI4AmortizationEngine）：
 *   · 月摊销额 = calcStraightLineAmort(原始金额, 期限月数) — 直线法
 *   · 期末 = calcAssetEndBalance(期初, 本期增加, 本期摊销, 本期减少)
 *   · 剩余月数 = calcRemainingMonths(期限月数, 已摊月数)
 *   · 摊销进度% = calcAmortizationRate(已摊月数, 期限月数)
 * - 合计行联动审定表I4-1（calcSubtotal）
 * - 动态行添加：ElMessageBox.prompt输入项目名称
 * - 持久化：rows JSON → checklist_responses item_id "I4-2-rows"
 * - 导入导出：importRows / exportRows
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 3.4
 * Requirements: 3.1-3.3
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcAssetEndBalance, calcSubtotal } from './useI4FormulaEngine'
import {
  calcStraightLineAmort,
  calcRemainingMonths,
  calcAmortizationRate,
} from './useI4AmortizationEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I4-2 明细行完整结构（25列拆分到3区段） */
export interface I4DetailRow {
  rowId: string

  // ── Section 0 基础区段（8列）──
  projectName: string           // 项目名称
  occurDate: string             // 发生日期（YYYY-MM-DD）
  expenseType: string           // 费用类型（装修费/开办费/租赁改良/其他）
  originalAmount: number        // 原始金额
  accountCategory: string       // 科目分类
  contractNo: string            // 合同编号
  startDate: string             // 起始日（YYYY-MM-DD）
  endDate: string               // 结束日（YYYY-MM-DD）

  // ── Section 1 摊销区段（8列）──
  amortizationMethod: string    // 摊销方法（直线法/工作量法）
  totalMonths: number           // 期限（月）
  elapsedMonths: number         // 已摊月数
  accAmortization: number       // 累计摊销
  currentAmortization: number   // 本期摊销
  monthlyAmortization: number   // 月摊销额（公式：直线法=原始金额÷期限月数）
  amortizationStartMonth: string // 摊销起始月（YYYY-MM）
  priorBalance: number          // 上期余额

  // ── Section 2 余额区段（9列）──
  beginBalance: number          // 期初
  currentIncrease: number       // 本期增加
  currentDecrease: number       // 本期减少
  endBalance: number            // 期末（公式：期初+增加-摊销-减少）
  remainingMonths: number       // 剩余月数（公式：期限-已摊月数）
  amortizationProgress: number  // 摊销进度%（公式：已摊月数÷期限月数）
  remark: string                // 备注
  indexNo: string               // 索引号
  status: string                // 状态（正常/已到期/提前终止）
}

/** 3区段Tab索引 */
export type I4DetailSection = 0 | 1 | 2

/** 3区段Tab标签 */
export const I4_DETAIL_SECTION_LABELS = ['基础', '摊销', '余额'] as const

/** 合计行结构（所有numeric列的SUM） */
export interface I4DetailSubtotals {
  // Section 0
  originalAmount: number
  // Section 1
  totalMonths: number
  elapsedMonths: number
  accAmortization: number
  currentAmortization: number
  monthlyAmortization: number
  priorBalance: number
  // Section 2
  beginBalance: number
  currentIncrease: number
  currentDecrease: number
  endBalance: number
  remainingMonths: number
}

/** 列定义 */
export interface I4DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'date' | 'month' | 'select' | 'formula'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'I4-2-rows'

const EXPENSE_TYPE_OPTIONS = ['装修费', '开办费', '租赁改良', '低值易耗品', '其他']
const AMORTIZATION_METHOD_OPTIONS = ['直线法', '工作量法']
const STATUS_OPTIONS = ['正常', '已到期', '提前终止']

// ─── Column Definitions ──────────────────────────────────────────────────────

/** Section 0 基础区段列定义（8列） */
const BASIC_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 180, editable: true, type: 'text' },
  { key: 'occurDate', label: '发生日期', width: 120, editable: true, type: 'date' },
  { key: 'expenseType', label: '费用类型', width: 120, editable: true, type: 'select', options: EXPENSE_TYPE_OPTIONS },
  { key: 'originalAmount', label: '原始金额', width: 130, editable: true, type: 'number' },
  { key: 'accountCategory', label: '科目分类', width: 120, editable: true, type: 'text' },
  { key: 'contractNo', label: '合同编号', width: 130, editable: true, type: 'text' },
  { key: 'startDate', label: '起始日', width: 120, editable: true, type: 'date' },
  { key: 'endDate', label: '结束日', width: 120, editable: true, type: 'date' },
]

/** Section 1 摊销区段列定义（8列，含1公式列） */
const AMORTIZATION_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 180, editable: false, type: 'text' },
  { key: 'amortizationMethod', label: '摊销方法', width: 110, editable: true, type: 'select', options: AMORTIZATION_METHOD_OPTIONS },
  { key: 'totalMonths', label: '期限(月)', width: 100, editable: true, type: 'number' },
  { key: 'elapsedMonths', label: '已摊月数', width: 100, editable: true, type: 'number' },
  { key: 'accAmortization', label: '累计摊销', width: 130, editable: true, type: 'number' },
  { key: 'currentAmortization', label: '本期摊销', width: 120, editable: true, type: 'number' },
  { key: 'monthlyAmortization', label: '月摊销额', width: 120, editable: false, type: 'formula', tooltip: '月摊销额=原始金额÷摊销期限(月)' },
  { key: 'amortizationStartMonth', label: '摊销起始月', width: 120, editable: true, type: 'month' },
  { key: 'priorBalance', label: '上期余额', width: 120, editable: true, type: 'number' },
]

/** Section 2 余额区段列定义（9列，含3公式列） */
const BALANCE_COLUMNS: I4DetailColumn[] = [
  { key: 'projectName', label: '项目名称', width: 180, editable: false, type: 'text' },
  { key: 'beginBalance', label: '期初', width: 120, editable: true, type: 'number' },
  { key: 'currentIncrease', label: '本期增加', width: 120, editable: true, type: 'number' },
  { key: 'currentDecrease', label: '本期减少', width: 120, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末', width: 120, editable: false, type: 'formula', tooltip: '期末=期初+增加-摊销-减少' },
  { key: 'remainingMonths', label: '剩余月数', width: 110, editable: false, type: 'formula', tooltip: '剩余月数=期限(月)-已摊月数' },
  { key: 'amortizationProgress', label: '摊销进度%', width: 110, editable: false, type: 'formula', tooltip: '摊销进度=已摊月数÷期限(月)' },
  { key: 'remark', label: '备注', width: 150, editable: true, type: 'text' },
  { key: 'indexNo', label: '索引号', width: 100, editable: true, type: 'text' },
  { key: 'status', label: '状态', width: 100, editable: true, type: 'select', options: STATUS_OPTIONS },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4Detail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    /** 审定表小计（用于交叉验证） */
    adjBeginSubtotal?: Ref<number>
    adjEndSubtotal?: Ref<number>
    adjAmortizationSubtotal?: Ref<number>
    /** 保存回调 */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 明细行数据 */
  const rows = ref<I4DetailRow[]>([])

  /** 当前激活的区段Tab（0=基础, 1=摊销, 2=余额） */
  const activeSection = ref<I4DetailSection>(0)

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

  function _normalizeRow(raw: any): I4DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      // Section 0 基础
      projectName: raw.projectName ?? '',
      occurDate: raw.occurDate ?? '',
      expenseType: raw.expenseType ?? '',
      originalAmount: Number(raw.originalAmount) || 0,
      accountCategory: raw.accountCategory ?? '',
      contractNo: raw.contractNo ?? '',
      startDate: raw.startDate ?? '',
      endDate: raw.endDate ?? '',
      // Section 1 摊销
      amortizationMethod: raw.amortizationMethod ?? '直线法',
      totalMonths: Number(raw.totalMonths) || 0,
      elapsedMonths: Number(raw.elapsedMonths) || 0,
      accAmortization: Number(raw.accAmortization) || 0,
      currentAmortization: Number(raw.currentAmortization) || 0,
      monthlyAmortization: Number(raw.monthlyAmortization) || 0,
      amortizationStartMonth: raw.amortizationStartMonth ?? '',
      priorBalance: Number(raw.priorBalance) || 0,
      // Section 2 余额
      beginBalance: Number(raw.beginBalance) || 0,
      currentIncrease: Number(raw.currentIncrease) || 0,
      currentDecrease: Number(raw.currentDecrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      remainingMonths: Number(raw.remainingMonths) || 0,
      amortizationProgress: Number(raw.amortizationProgress) || 0,
      remark: raw.remark ?? '',
      indexNo: raw.indexNo ?? '',
      status: raw.status ?? '正常',
    }
  }

  // ─── Formula Recalculation ─────────────────────────────────────────────────

  /**
   * 对指定行重算所有公式列：
   * - monthlyAmortization = calcStraightLineAmort(originalAmount, totalMonths)
   * - endBalance = calcAssetEndBalance(beginBalance, currentIncrease, currentAmortization, currentDecrease)
   * - remainingMonths = calcRemainingMonths(totalMonths, elapsedMonths)
   * - amortizationProgress = calcAmortizationRate(elapsedMonths, totalMonths)
   */
  function _recalcRow(row: I4DetailRow): void {
    // 月摊销额：直线法 = 原始金额 ÷ 期限月数
    row.monthlyAmortization = calcStraightLineAmort(row.originalAmount, row.totalMonths)

    // 期末 = 期初 + 增加 - 摊销 - 减少（资产类1801）
    row.endBalance = calcAssetEndBalance(
      row.beginBalance,
      row.currentIncrease,
      row.currentAmortization,
      row.currentDecrease,
    )

    // 剩余月数 = 总月数 - 已摊月数
    row.remainingMonths = calcRemainingMonths(row.totalMonths, row.elapsedMonths)

    // 摊销进度 = 已摊月数 / 总月数
    row.amortizationProgress = calcAmortizationRate(row.elapsedMonths, row.totalMonths)
  }

  /** 对所有行重算公式 */
  function recalcAll(): void {
    for (const row of rows.value) {
      _recalcRow(row)
    }
  }

  // ─── Computed: 合计行（Req 3.2 合计行联动审定表）───────────────────────────

  const subtotals: ComputedRef<I4DetailSubtotals> = computed(() => {
    const r = rows.value
    return {
      // Section 0
      originalAmount: calcSubtotal(r.map((x) => x.originalAmount)),
      // Section 1
      totalMonths: 0, // 期限不做SUM
      elapsedMonths: 0, // 已摊月数不做SUM
      accAmortization: calcSubtotal(r.map((x) => x.accAmortization)),
      currentAmortization: calcSubtotal(r.map((x) => x.currentAmortization)),
      monthlyAmortization: calcSubtotal(r.map((x) => x.monthlyAmortization)),
      priorBalance: calcSubtotal(r.map((x) => x.priorBalance)),
      // Section 2
      beginBalance: calcSubtotal(r.map((x) => x.beginBalance)),
      currentIncrease: calcSubtotal(r.map((x) => x.currentIncrease)),
      currentDecrease: calcSubtotal(r.map((x) => x.currentDecrease)),
      endBalance: calcSubtotal(r.map((x) => x.endBalance)),
      remainingMonths: 0, // 剩余月数不做SUM
    }
  })

  // ─── Section 切换 + 行同步 ─────────────────────────────────────────────────

  function switchSection(section: I4DetailSection): void {
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
        '请输入待摊费用项目名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：办公室装修摊销',
          inputValidator: (val) => {
            if (!val || !val.trim()) return '项目名称不能为空'
            return true
          },
        },
      )

      if (!name?.trim()) return

      const newRow: I4DetailRow = {
        rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        // Section 0 基础
        projectName: name.trim(),
        occurDate: '',
        expenseType: '',
        originalAmount: 0,
        accountCategory: '',
        contractNo: '',
        startDate: '',
        endDate: '',
        // Section 1 摊销
        amortizationMethod: '直线法',
        totalMonths: 0,
        elapsedMonths: 0,
        accAmortization: 0,
        currentAmortization: 0,
        monthlyAmortization: 0,
        amortizationStartMonth: '',
        priorBalance: 0,
        // Section 2 余额
        beginBalance: 0,
        currentIncrease: 0,
        currentDecrease: 0,
        endBalance: 0,
        remainingMonths: 0,
        amortizationProgress: 0,
        remark: '',
        indexNo: '',
        status: '正常',
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

  // ─── importRows / exportRows（供 useI4ImportExport 调用）───────────────────

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
  function exportRows(): I4DetailRow[] {
    return [...rows.value]
  }

  // ─── segments: 3区段Tab列配置 ──────────────────────────────────────────────

  const segments = {
    basic: BASIC_COLUMNS,
    amortization: AMORTIZATION_COLUMNS,
    balance: BALANCE_COLUMNS,
  }

  /** 3区段Tab定义 */
  const sections = [
    { key: 0 as I4DetailSection, label: '基础', columns: BASIC_COLUMNS },
    { key: 1 as I4DetailSection, label: '摊销', columns: AMORTIZATION_COLUMNS },
    { key: 2 as I4DetailSection, label: '余额', columns: BALANCE_COLUMNS },
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

export default useI4Detail
