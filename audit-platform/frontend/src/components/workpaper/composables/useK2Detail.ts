/**
 * useK2Detail — K2-2 明细表 composable（18列2区段Tab）
 *
 * 管理动态行明细项目：
 *   区段0 "基础"：序号/项目名称/性质/期初余额/期末余额(公式)
 *   区段1 "检查"：增减原因/凭证号/核查结论/备注
 *
 * 核心功能：
 * - 期末=期初+增加-减少（资产类公式）
 * - 动态行新增（ElMessageBox.prompt输入名称确认后创建）
 * - 底部统计：项目数/期末合计
 * - JSON打包存储到 checklist_responses "K2-2-rows"
 * - 合计行联动审定表K2-1
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 3.4
 * Requirements: 3.1-3.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcAssetEndBalance, calcSubtotal } from './useK2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K2DetailRow {
  rowId: string
  // Section 0 基础
  seqNo: number
  name: string
  nature: string           // 性质（预付/待摊/保证金等）
  beginBalance: number     // 期初余额
  increase: number         // 本期增加
  decrease: number         // 本期减少
  endBalance: number       // 期末余额（公式：期初+增加-减少）
  // Section 1 检查
  increaseReason: string   // 增减原因
  voucherRef: string       // 凭证号
  checkConclusion: string  // 核查结论
  remark: string           // 备注
}

export type K2DetailSection = 0 | 1

export const K2_DETAIL_SECTION_LABELS = ['基础', '检查'] as const

export interface K2DetailSubtotals {
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  count: number
}

export interface K2DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K2-2-rows'

const NATURE_OPTIONS = ['预付款项', '待摊费用', '合同取得成本', '待抵扣税额', '押金保证金', '其他']
const CONCLUSION_OPTIONS = ['正常', '异常', '待确认']

/** Section 0 基础区段列定义 */
const BASIC_COLUMNS: K2DetailColumn[] = [
  { key: 'seqNo', label: '序号', width: 60, editable: false, type: 'number' },
  { key: 'name', label: '项目名称', width: 180, editable: true, type: 'text' },
  { key: 'nature', label: '性质', width: 120, editable: true, type: 'select', options: NATURE_OPTIONS },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'increase', label: '本期增加', width: 120, editable: true, type: 'number' },
  { key: 'decrease', label: '本期减少', width: 120, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+增加-减少' },
]

/** Section 1 检查区段列定义 */
const CHECK_COLUMNS: K2DetailColumn[] = [
  { key: 'name', label: '项目名称', width: 180, editable: false, type: 'text' },
  { key: 'increaseReason', label: '增减原因', width: 180, editable: true, type: 'text' },
  { key: 'voucherRef', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'checkConclusion', label: '核查结论', width: 120, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'remark', label: '备注', width: 200, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK2Detail(
  allResponses: Ref<Map<string, any>>,
  options?: {
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K2DetailRow[]>([])
  const activeSection = ref<K2DetailSection>(0)
  const activeRowIndex = ref<number>(-1)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { rows.value = []; return }
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

  function _normalizeRow(raw: any, idx?: number): K2DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      name: raw.name ?? '',
      nature: raw.nature ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      increase: Number(raw.increase) || 0,
      decrease: Number(raw.decrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      increaseReason: raw.increaseReason ?? '',
      voucherRef: raw.voucherRef ?? '',
      checkConclusion: raw.checkConclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K2DetailRow): void {
    row.endBalance = calcAssetEndBalance(row.beginBalance, row.increase, row.decrease)
  }

  function recalcAll(): void {
    for (const row of rows.value) _recalcRow(row)
  }

  // ─── Computed: Subtotals (Req 3.4 底部统计) ────────────────────────────────

  const subtotals: ComputedRef<K2DetailSubtotals> = computed(() => {
    const r = rows.value
    return {
      beginBalance: calcSubtotal(r.map((x) => x.beginBalance)),
      increase: calcSubtotal(r.map((x) => x.increase)),
      decrease: calcSubtotal(r.map((x) => x.decrease)),
      endBalance: calcSubtotal(r.map((x) => x.endBalance)),
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K2DetailSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    return activeSection.value === 0 ? BASIC_COLUMNS : CHECK_COLUMNS
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add (Req 3.3) ─────────────────────────────────────────────

  async function addRow(): Promise<void> {
    try {
      const { value: name } = await ElMessageBox.prompt(
        '请输入其他流动资产明细项目名称',
        '新增明细行',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：预付XX费用',
          inputValidator: (val) => (!val?.trim() ? '项目名称不能为空' : true),
        },
      )
      if (!name?.trim()) return

      const newRow: K2DetailRow = {
        rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        seqNo: rows.value.length + 1,
        name: name.trim(),
        nature: '',
        beginBalance: 0,
        increase: 0,
        decrease: 0,
        endBalance: 0,
        increaseReason: '',
        voucherRef: '',
        checkConclusion: '',
        remark: '',
      }

      rows.value.push(newRow)
      activeRowIndex.value = rows.value.length - 1
      _persist()
    } catch {
      // 用户取消
    }
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    // 重新编号
    rows.value.forEach((r, i) => { r.seqNo = i + 1 })
    if (activeRowIndex.value >= rows.value.length) {
      activeRowIndex.value = rows.value.length - 1
    }
    _persist()
  }

  // ─── Import / Export ───────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    rows.value = data.map((raw, i) => {
      const row = _normalizeRow(raw, i)
      _recalcRow(row)
      return row
    })
    activeRowIndex.value = rows.value.length > 0 ? 0 : -1
    _persist()
  }

  function exportRows(): K2DetailRow[] {
    return [...rows.value]
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(ITEM_ID_ROWS, JSON.stringify(rows.value))
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    activeSection,
    activeRowIndex,
    subtotals,
    activeColumns,
    sections: [
      { key: 0 as K2DetailSection, label: '基础', columns: BASIC_COLUMNS },
      { key: 1 as K2DetailSection, label: '检查', columns: CHECK_COLUMNS },
    ],
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    exportRows,
  }
}
