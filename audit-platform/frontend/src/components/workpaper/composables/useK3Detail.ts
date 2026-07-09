/**
 * useK3Detail — K3-2 明细表 composable（27列3区段Tab+账龄）
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责：
 * - 27列拆为3区段Tab：
 *   基础(序号/往来对象/性质/关联关系/期初/期末)
 *   账龄(1年内/1-2年/2-3年/3年以上/账龄合计)
 *   检查(形成原因/预计偿付时间/凭证号/结论/备注)
 * - 期末=期初+增加(贷)-减少(借)（负债类！增加在贷方）
 * - 账龄合计与期末勾稽
 * - 动态行新增（ElMessageBox.prompt输入往来对象）+导入导出
 * - 3年以上账龄行标记橙色背景（长期挂账风险）
 * - 底部统计：往来笔数/期末合计/3年以上占比
 * - JSON打包存储到 checklist_responses "K3-2-rows"
 *
 * 科目：2241 其他应付款（**贷方/负债类**）
 * ⚠️ 负债类！增加=贷方发生；减少=借方发生
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useK3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K3DetailRow {
  rowId: string
  // 区段0 基础
  seqNo: number
  counterparty: string         // 往来对象
  nature: string               // 性质（保证金/往来款/代收代付/其他）
  relatedParty: string         // 关联关系（非关联/控股子公司/联营合营/...）
  beginBalance: number         // 期初余额
  increase: number             // 本期增加（贷方发生）
  decrease: number             // 本期减少（借方发生）
  endBalance: number           // 期末余额（公式：期初+贷-借，负债类）
  // 区段1 账龄
  agingWithin1Y: number        // 1年以内
  aging1To2Y: number           // 1-2年
  aging2To3Y: number           // 2-3年
  agingOver3Y: number          // 3年以上
  agingTotal: number           // 账龄合计（应=期末余额）
  // 区段2 检查
  formationReason: string      // 形成原因
  repaymentDate: string        // 预计偿付时间
  voucherRef: string           // 凭证号
  checkConclusion: string      // 结论
  suspectedUnrecorded: boolean // 疑似未入账 (Req 7.4)
  remark: string
}

export type K3DetailSection = 0 | 1 | 2

export const K3_DETAIL_SECTION_LABELS = ['基础', '账龄', '检查'] as const

export interface K3DetailSubtotals {
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  agingWithin1Y: number
  aging1To2Y: number
  aging2To3Y: number
  agingOver3Y: number
  count: number
}

export interface K3DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select' | 'checkbox'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K3-2-rows'

const NATURE_OPTIONS = ['保证金及押金', '往来款', '代收代付', '其他']
const RELATED_PARTY_OPTIONS = ['非关联', '控股子公司', '联营/合营企业', '关键管理人员', '关联自然人', '其他关联方']
const CONCLUSION_OPTIONS = ['正常', '异常', '长期挂账', '待确认']

/** 区段0 基础列 */
const BASIC_COLUMNS: K3DetailColumn[] = [
  { key: 'seqNo', label: '序号', width: 60, editable: false, type: 'number' },
  { key: 'counterparty', label: '往来对象', width: 180, editable: true, type: 'text' },
  { key: 'nature', label: '性质', width: 120, editable: true, type: 'select', options: NATURE_OPTIONS },
  { key: 'relatedParty', label: '关联关系', width: 130, editable: true, type: 'select', options: RELATED_PARTY_OPTIONS },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'increase', label: '本期增加(贷方)', width: 130, editable: true, type: 'number' },
  { key: 'decrease', label: '本期减少(借方)', width: 130, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+贷方-借方（负债类）' },
]

/** 区段1 账龄列 */
const AGING_COLUMNS: K3DetailColumn[] = [
  { key: 'counterparty', label: '往来对象', width: 180, editable: false, type: 'text' },
  { key: 'agingWithin1Y', label: '1年以内', width: 120, editable: true, type: 'number' },
  { key: 'aging1To2Y', label: '1-2年', width: 110, editable: true, type: 'number' },
  { key: 'aging2To3Y', label: '2-3年', width: 110, editable: true, type: 'number' },
  { key: 'agingOver3Y', label: '3年以上', width: 110, editable: true, type: 'number' },
  { key: 'agingTotal', label: '账龄合计', width: 120, editable: false, type: 'formula', tooltip: '=1年内+1-2年+2-3年+3年以上' },
  { key: 'endBalance', label: '期末余额', width: 120, editable: false, type: 'formula', tooltip: '勾稽：账龄合计应=期末余额' },
]

/** 区段2 检查列 */
const CHECK_COLUMNS: K3DetailColumn[] = [
  { key: 'counterparty', label: '往来对象', width: 180, editable: false, type: 'text' },
  { key: 'formationReason', label: '形成原因', width: 200, editable: true, type: 'text' },
  { key: 'repaymentDate', label: '预计偿付时间', width: 130, editable: true, type: 'text' },
  { key: 'voucherRef', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'checkConclusion', label: '结论', width: 110, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'suspectedUnrecorded', label: '疑似未入账', width: 100, editable: true, type: 'checkbox' },
  { key: 'remark', label: '备注', width: 200, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK3Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
}) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const detailRows = ref<K3DetailRow[]>([])
  const activeSection = ref<K3DetailSection>(0)

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

  function _normalizeRow(raw: any, idx?: number): K3DetailRow {
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      counterparty: raw.counterparty ?? '',
      nature: raw.nature ?? '',
      relatedParty: raw.relatedParty ?? '',
      beginBalance: Number(raw.beginBalance) || 0,
      increase: Number(raw.increase) || 0,
      decrease: Number(raw.decrease) || 0,
      endBalance: Number(raw.endBalance) || 0,
      agingWithin1Y: Number(raw.agingWithin1Y) || 0,
      aging1To2Y: Number(raw.aging1To2Y) || 0,
      aging2To3Y: Number(raw.aging2To3Y) || 0,
      agingOver3Y: Number(raw.agingOver3Y) || 0,
      agingTotal: Number(raw.agingTotal) || 0,
      formationReason: raw.formationReason ?? '',
      repaymentDate: raw.repaymentDate ?? '',
      voucherRef: raw.voucherRef ?? '',
      checkConclusion: raw.checkConclusion ?? '',
      suspectedUnrecorded: Boolean(raw.suspectedUnrecorded),
      remark: raw.remark ?? '',
    }
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K3DetailRow): void {
    // 负债类期末=期初+贷方(增加)-借方(减少)
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.increase, row.decrease)
    // 账龄合计
    row.agingTotal = row.agingWithin1Y + row.aging1To2Y + row.aging2To3Y + row.agingOver3Y
  }

  function recalcAll(): void {
    for (const row of detailRows.value) _recalcRow(row)
  }

  // ─── Subtotals (Req 3.6 底部统计) ─────────────────────────────────────────

  const subtotals: ComputedRef<K3DetailSubtotals> = computed(() => {
    const r = detailRows.value
    return {
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      increase: calcSubtotal(r.map(x => x.increase)),
      decrease: calcSubtotal(r.map(x => x.decrease)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      agingWithin1Y: calcSubtotal(r.map(x => x.agingWithin1Y)),
      aging1To2Y: calcSubtotal(r.map(x => x.aging1To2Y)),
      aging2To3Y: calcSubtotal(r.map(x => x.aging2To3Y)),
      agingOver3Y: calcSubtotal(r.map(x => x.agingOver3Y)),
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K3DetailSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    switch (activeSection.value) {
      case 0: return BASIC_COLUMNS
      case 1: return AGING_COLUMNS
      case 2: return CHECK_COLUMNS
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

  // ─── Dynamic Row Add (Req 3.4: ElMessageBox.prompt输入往来对象) ──────────────

  async function addRow(counterparty?: string): Promise<void> {
    let name = counterparty
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入往来对象名称',
          '新增明细行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX公司',
            inputValidator: (val) => (!val?.trim() ? '往来对象不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return // 用户取消
      }
    }
    if (!name) return

    const newRow: K3DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: detailRows.value.length + 1,
      counterparty: name,
      nature: '',
      relatedParty: '非关联',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      agingWithin1Y: 0,
      aging1To2Y: 0,
      aging2To3Y: 0,
      agingOver3Y: 0,
      agingTotal: 0,
      formationReason: '',
      repaymentDate: '',
      voucherRef: '',
      checkConclusion: '',
      suspectedUnrecorded: false,
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

  /** 明细表期末合计 */
  function getDetailTotal(): number {
    return subtotals.value.endBalance
  }

  /** 3年以上账龄行数 */
  function getAgingOver3YCount(): number {
    return detailRows.value.filter(r => r.agingOver3Y > 0).length
  }

  /** 3年以上账龄金额合计 */
  function getAgingOver3YTotal(): number {
    return calcSubtotal(detailRows.value.map(r => r.agingOver3Y))
  }

  /** 获取超过阈值的大额项目 (Req 4.4 联动K3-4) */
  function getLargeAmountItems(threshold: number): K3DetailRow[] {
    return detailRows.value
      .filter(r => Math.abs(r.endBalance) >= threshold)
      .sort((a, b) => Math.abs(b.endBalance) - Math.abs(a.endBalance))
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(detailRows.value) })
    // 同步跨sheet数据到allResponses供computed链使用
    saveResponse('K3-2-detail-total', { remark: String(getDetailTotal()) })
    saveResponse('K3-2-aging-over3y-count', { remark: String(getAgingOver3YCount()) })
    saveResponse('K3-2-aging-over3y-total', { remark: String(getAgingOver3YTotal()) })
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
      { key: 0 as K3DetailSection, label: '基础', columns: BASIC_COLUMNS },
      { key: 1 as K3DetailSection, label: '账龄', columns: AGING_COLUMNS },
      { key: 2 as K3DetailSection, label: '检查', columns: CHECK_COLUMNS },
    ],
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getDetailTotal,
    getAgingOver3YCount,
    getAgingOver3YTotal,
    getLargeAmountItems,
  }
}
