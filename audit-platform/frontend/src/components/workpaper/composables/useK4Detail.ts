/**
 * useK4Detail — K4-2 明细表 composable（25行×18列，2区段Tab）
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Task: 3.4
 * Requirements: 3.1-3.4
 *
 * 职责：
 * - 动态行（new row via ElMessageBox.prompt 输入项目名称）
 * - 18列拆为2区段Tab：
 *   基础(序号/项目/性质/期初/期末)
 *   检查(增减原因/凭证号/核查结论/备注)
 * - 使用 calcLiabilityEndBalance：期末=期初+增(贷)-减(借)
 * - calcSubtotal for 合计行
 * - Save with prefix "K4-2-"
 * - Emits total to crossSheet (K4-2-detail-total)
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 * ⚠️ 负债类！增加=贷方发生；减少=借方发生
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useK4FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K4DetailRow {
  rowId: string
  // 区段0 基础
  seqNo: number
  projectName: string          // 项目名称
  nature: string               // 性质（预提/待转/代扣/其他）
  beginBalance: number         // 未审期初余额
  increase: number             // 未审本期增加（贷方发生）
  decrease: number             // 未审本期减少（借方发生）
  endBalance: number           // 未审期末余额（公式：期初+贷-借，负债类）
  // 区段2 调整（对齐源模板 K4-2：期初调整/账项调整增减/重分类调整增减/审定）
  openingAdjust: number        // 期初调整
  ajeIncrease: number          // 账项调整-本期增加
  ajeDecrease: number          // 账项调整-本期减少
  rjeIncrease: number          // 重分类调整-本期增加
  rjeDecrease: number          // 重分类调整-本期减少
  auditedBegin: number         // 审定期初（=未审期初+期初调整）
  auditedIncrease: number      // 审定本期增加
  auditedDecrease: number      // 审定本期减少
  auditedEnd: number           // 审定期末
  // 区段1 检查
  increaseReason: string       // 增减原因
  voucherRef: string           // 凭证号
  checkConclusion: string      // 核查结论
  remark: string               // 备注
}

export type K4DetailSection = 0 | 1 | 2

export const K4_DETAIL_SECTION_LABELS = ['基础', '检查', '调整'] as const

export interface K4DetailSubtotals {
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  openingAdjust: number
  ajeIncrease: number
  ajeDecrease: number
  rjeIncrease: number
  rjeDecrease: number
  auditedEnd: number
  count: number
}

export interface K4DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K4-2-rows'

const NATURE_OPTIONS = ['预提费用', '待转销项税额', '代扣代缴', '短期融资', '其他']
const CONCLUSION_OPTIONS = ['正常', '异常', '需关注', '待确认']

/** 区段0 基础列 */
const BASIC_COLUMNS: K4DetailColumn[] = [
  { key: 'seqNo', label: '序号', width: 60, editable: false, type: 'number' },
  { key: 'projectName', label: '项目', width: 200, editable: true, type: 'text' },
  { key: 'nature', label: '性质', width: 120, editable: true, type: 'select', options: NATURE_OPTIONS },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'increase', label: '本期增加(贷方)', width: 140, editable: true, type: 'number' },
  { key: 'decrease', label: '本期减少(借方)', width: 140, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+贷方-借方（负债类）' },
]

/** 区段1 检查列 */
const CHECK_COLUMNS: K4DetailColumn[] = [
  { key: 'projectName', label: '项目', width: 200, editable: false, type: 'text' },
  { key: 'increaseReason', label: '增减原因', width: 220, editable: true, type: 'text' },
  { key: 'voucherRef', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'checkConclusion', label: '核查结论', width: 120, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'remark', label: '备注', width: 200, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK4Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
}) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const detailRows = ref<K4DetailRow[]>([])
  const activeSection = ref<K4DetailSection>(0)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadRows(): void {
    const item = allResponses.value.get(ITEM_ID_ROWS)
    const raw = item?.remark ?? item?.conclusion ?? (typeof item === 'string' ? item : null)
    if (!raw) { detailRows.value = []; return }
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed.map(_normalizeRow)
      } else {
        detailRows.value = []
      }
    } catch {
      detailRows.value = []
    }
  }

  function _normalizeRow(raw: any, idx?: number): K4DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      projectName: raw.projectName ?? '',
      nature: raw.nature ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      increase: Number(raw.increase) || 0,
      decrease: Number(raw.decrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      openingAdjust: Number(raw.openingAdjust) || 0,
      ajeIncrease: Number(raw.ajeIncrease) || 0,
      ajeDecrease: Number(raw.ajeDecrease) || 0,
      rjeIncrease: Number(raw.rjeIncrease) || 0,
      rjeDecrease: Number(raw.rjeDecrease) || 0,
      auditedBegin: 0,
      auditedIncrease: 0,
      auditedDecrease: 0,
      auditedEnd: 0,
      increaseReason: raw.increaseReason ?? '',
      voucherRef: raw.voucherRef ?? '',
      checkConclusion: raw.checkConclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K4DetailRow): void {
    // 负债类期末=期初+贷方(增加)-借方(减少)
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.increase, row.decrease)
    // 审定列（对齐源模板：未审 + 期初调整 + 账项调整 + 重分类调整）
    row.auditedBegin = row.beginBalance + row.openingAdjust
    row.auditedIncrease = row.increase + row.ajeIncrease + row.rjeIncrease
    row.auditedDecrease = row.decrease + row.ajeDecrease + row.rjeDecrease
    row.auditedEnd = row.auditedBegin + row.auditedIncrease - row.auditedDecrease
  }

  function recalcAll(): void {
    for (const row of detailRows.value) _recalcRow(row)
  }

  // ─── Subtotals (Req 3.4 底部统计：项目数/期末合计) ─────────────────────────

  const subtotals: ComputedRef<K4DetailSubtotals> = computed(() => {
    const r = detailRows.value
    return {
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      increase: calcSubtotal(r.map(x => x.increase)),
      decrease: calcSubtotal(r.map(x => x.decrease)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      openingAdjust: calcSubtotal(r.map(x => x.openingAdjust)),
      ajeIncrease: calcSubtotal(r.map(x => x.ajeIncrease)),
      ajeDecrease: calcSubtotal(r.map(x => x.ajeDecrease)),
      rjeIncrease: calcSubtotal(r.map(x => x.rjeIncrease)),
      rjeDecrease: calcSubtotal(r.map(x => x.rjeDecrease)),
      auditedEnd: calcSubtotal(r.map(x => x.auditedEnd)),
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K4DetailSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    switch (activeSection.value) {
      case 0: return BASIC_COLUMNS
      case 1: return CHECK_COLUMNS
      default: return BASIC_COLUMNS
    }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    const row = detailRows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── Dynamic Row Add (Req 3.3: ElMessageBox.prompt输入项目名称) ─────────────

  async function addRow(projectName?: string): Promise<void> {
    let name = projectName
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入项目名称',
          '新增明细行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：预提XX费用',
            inputValidator: (val) => (!val?.trim() ? '项目名称不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return // 用户取消
      }
    }
    if (!name) return

    const newRow: K4DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: detailRows.value.length + 1,
      projectName: name,
      nature: '',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      openingAdjust: 0,
      ajeIncrease: 0,
      ajeDecrease: 0,
      rjeIncrease: 0,
      rjeDecrease: 0,
      auditedBegin: 0,
      auditedIncrease: 0,
      auditedDecrease: 0,
      auditedEnd: 0,
      increaseReason: '',
      voucherRef: '',
      checkConclusion: '',
      remark: '',
    }

    detailRows.value.push(newRow)
    _persist()
  }

  // ─── Remove Row ────────────────────────────────────────────────────────────

  function removeRow(idx: number): void {
    if (idx < 0 || idx >= detailRows.value.length) return
    detailRows.value.splice(idx, 1)
    detailRows.value.forEach((r, i) => { r.seqNo = i + 1 })
    _persist()
  }

  // ─── Import ────────────────────────────────────────────────────────────────

  function importRows(data: any[]): void {
    detailRows.value = data.map((raw, i) => {
      const row = _normalizeRow(raw, i)
      _recalcRow(row)
      return row
    })
    _persist()
  }

  // ─── 统计方法 ──────────────────────────────────────────────────────────────

  /** 明细表期末合计（供跨sheet交叉验证） */
  function getDetailTotal(): number {
    return subtotals.value.endBalance
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(detailRows.value) })
    // 同步跨sheet数据：K4-2-detail-total
    saveResponse('K4-2-detail-total', { remark: String(getDetailTotal()) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    detailRows,
    activeSection,
    subtotals,
    activeColumns,
    sections: [
      { key: 0 as K4DetailSection, label: '基础', columns: BASIC_COLUMNS },
      { key: 1 as K4DetailSection, label: '检查', columns: CHECK_COLUMNS },
    ],
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getDetailTotal,
  }
}
