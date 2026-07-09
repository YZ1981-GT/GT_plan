/**
 * useK7Detail — K7-2 明细表 composable（41行×32列，21公式patterns）
 *
 * Spec: .kiro/specs/k7-deferred-income/
 * Task: 3.4
 * Requirements: 3.1-3.5
 *
 * 职责：
 * - 32列拆为3区段Tab：
 *   基础(序号/补助项目/批文号/补助类型/与资产或收益相关/收到金额/收到日期)
 *   分摊(分摊方法/分摊期/期初/本期分摊/期末)
 *   检查(计入科目/凭证/结论/备注)
 * - 期末=期初+收到-分摊（负债类！per row）
 * - Subtotal rows: calcSubtotal for each group
 * - Cross-verify with K7-4: detailVsCalc
 * - Dynamic rows: add via ElMessageBox.prompt
 * - Import/export support (K7-2 is importable sheet)
 * - JSON打包存储到 checklist_responses "K7-2-rows"
 * - 41行虚拟滚动
 *
 * 科目：2401 递延收益（**贷方/负债类**）
 * ⚠️ 负债类！收到=贷方增加；分摊=借方减少
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcLiabilityEndBalance, calcSubtotal } from './useK7FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K7DetailRow {
  rowId: string
  // 区段0 基础
  seqNo: number
  project: string              // 补助项目名称
  docRef: string               // 批文号
  grantType: string            // 补助类型（财政拨款/税收返还/其他）
  relatedType: '与资产相关' | '与收益相关'
  receivedAmount: number       // 收到金额
  receivedDate: string         // 收到日期
  // 区段1 分摊
  method: string               // 分摊方法（直线法/工作量法/一次性计入）
  period: number               // 分摊期（月数）
  beginBalance: number         // 期初余额
  currentAmort: number         // 本期分摊
  endBalance: number           // 期末余额（公式：期初+收到-分摊）
  // 区段2 检查
  accountTo: string            // 计入科目（其他收益/营业外收入）
  voucher: string              // 凭证号
  conclusion: string           // 结论
  remark: string
}

export type K7DetailSection = 0 | 1 | 2

export const K7_DETAIL_SECTION_LABELS = ['基础', '分摊', '检查'] as const

export interface K7DetailSubtotals {
  receivedAmount: number
  beginBalance: number
  currentAmort: number
  endBalance: number
  count: number
}

export interface K7DetailColumn {
  key: string
  label: string
  width: number
  editable: boolean
  type: 'text' | 'number' | 'formula' | 'select' | 'date'
  options?: string[]
  tooltip?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_ROWS = 'K7-2-rows'

const GRANT_TYPE_OPTIONS = ['财政拨款', '税收返还', '无偿划拨', '其他']
const RELATED_TYPE_OPTIONS = ['与资产相关', '与收益相关']
const METHOD_OPTIONS = ['直线法', '工作量法', '一次性计入']
const ACCOUNT_TO_OPTIONS = ['其他收益', '营业外收入']
const CONCLUSION_OPTIONS = ['正常', '异常', '需调整', '待确认']

/** 区段0 基础列 */
const BASIC_COLUMNS: K7DetailColumn[] = [
  { key: 'seqNo', label: '序号', width: 60, editable: false, type: 'number' },
  { key: 'project', label: '补助项目', width: 180, editable: true, type: 'text' },
  { key: 'docRef', label: '批文号', width: 150, editable: true, type: 'text' },
  { key: 'grantType', label: '补助类型', width: 120, editable: true, type: 'select', options: GRANT_TYPE_OPTIONS },
  { key: 'relatedType', label: '相关类型', width: 120, editable: true, type: 'select', options: RELATED_TYPE_OPTIONS },
  { key: 'receivedAmount', label: '收到金额', width: 130, editable: true, type: 'number' },
  { key: 'receivedDate', label: '收到日期', width: 120, editable: true, type: 'date' },
]

/** 区段1 分摊列 */
const AMORT_COLUMNS: K7DetailColumn[] = [
  { key: 'project', label: '补助项目', width: 180, editable: false, type: 'text' },
  { key: 'method', label: '分摊方法', width: 120, editable: true, type: 'select', options: METHOD_OPTIONS },
  { key: 'period', label: '分摊期(月)', width: 100, editable: true, type: 'number' },
  { key: 'beginBalance', label: '期初余额', width: 130, editable: true, type: 'number' },
  { key: 'currentAmort', label: '本期分摊', width: 130, editable: true, type: 'number' },
  { key: 'endBalance', label: '期末余额', width: 130, editable: false, type: 'formula', tooltip: '期末=期初+收到-分摊（负债类）' },
]

/** 区段2 检查列 */
const CHECK_COLUMNS: K7DetailColumn[] = [
  { key: 'project', label: '补助项目', width: 180, editable: false, type: 'text' },
  { key: 'accountTo', label: '计入科目', width: 130, editable: true, type: 'select', options: ACCOUNT_TO_OPTIONS },
  { key: 'voucher', label: '凭证号', width: 120, editable: true, type: 'text' },
  { key: 'conclusion', label: '结论', width: 110, editable: true, type: 'select', options: CONCLUSION_OPTIONS },
  { key: 'remark', label: '备注', width: 200, editable: true, type: 'text' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK7Detail(params: {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
}) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const detailRows = ref<K7DetailRow[]>([])
  const activeSection = ref<K7DetailSection>(0)

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

  function _normalizeRow(raw: any, idx?: number): K7DetailRow {
    const row: K7DetailRow = {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? (idx != null ? idx + 1 : 1),
      project: raw.project ?? '',
      docRef: raw.docRef ?? '',
      grantType: raw.grantType ?? '',
      relatedType: raw.relatedType ?? '与资产相关',
      receivedAmount: Number(raw.receivedAmount) || 0,
      receivedDate: raw.receivedDate ?? '',
      method: raw.method ?? '',
      period: Number(raw.period) || 0,
      beginBalance: Number(raw.beginBalance) || 0,
      currentAmort: Number(raw.currentAmort) || 0,
      endBalance: 0,
      accountTo: raw.accountTo ?? '',
      voucher: raw.voucher ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
    _recalcRow(row)
    return row
  }

  // ─── Recalc ────────────────────────────────────────────────────────────────

  function _recalcRow(row: K7DetailRow): void {
    // 负债类期末=期初+收到-分摊
    row.endBalance = calcLiabilityEndBalance(row.beginBalance, row.receivedAmount, row.currentAmort)
  }

  function recalcAll(): void {
    for (const row of detailRows.value) _recalcRow(row)
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const subtotals: ComputedRef<K7DetailSubtotals> = computed(() => {
    const r = detailRows.value
    return {
      receivedAmount: calcSubtotal(r.map(x => x.receivedAmount)),
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      currentAmort: calcSubtotal(r.map(x => x.currentAmort)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      count: r.length,
    }
  })

  /** 按 relatedType 分组小计 */
  const assetRelatedSubtotal: ComputedRef<K7DetailSubtotals> = computed(() => {
    const r = detailRows.value.filter(x => x.relatedType === '与资产相关')
    return {
      receivedAmount: calcSubtotal(r.map(x => x.receivedAmount)),
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      currentAmort: calcSubtotal(r.map(x => x.currentAmort)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      count: r.length,
    }
  })

  const incomeRelatedSubtotal: ComputedRef<K7DetailSubtotals> = computed(() => {
    const r = detailRows.value.filter(x => x.relatedType === '与收益相关')
    return {
      receivedAmount: calcSubtotal(r.map(x => x.receivedAmount)),
      beginBalance: calcSubtotal(r.map(x => x.beginBalance)),
      currentAmort: calcSubtotal(r.map(x => x.currentAmort)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      count: r.length,
    }
  })

  // ─── Section Switching ─────────────────────────────────────────────────────

  function switchSection(section: K7DetailSection): void {
    activeSection.value = section
  }

  const activeColumns = computed(() => {
    switch (activeSection.value) {
      case 0: return BASIC_COLUMNS
      case 1: return AMORT_COLUMNS
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

  // ─── Dynamic Row Add (Req 3.3: ElMessageBox.prompt输入补助项目) ─────────────

  async function addRow(project?: string): Promise<void> {
    let name = project
    if (!name) {
      try {
        const { value } = await ElMessageBox.prompt(
          '请输入补助项目名称',
          '新增明细行',
          {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPlaceholder: '例如：XX设备购置补助',
            inputValidator: (val) => (!val?.trim() ? '补助项目不能为空' : true),
          },
        )
        name = value?.trim()
      } catch {
        return // 用户取消
      }
    }
    if (!name) return

    const newRow: K7DetailRow = {
      rowId: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: detailRows.value.length + 1,
      project: name,
      docRef: '',
      grantType: '',
      relatedType: '与资产相关',
      receivedAmount: 0,
      receivedDate: '',
      method: '直线法',
      period: 0,
      beginBalance: 0,
      currentAmort: 0,
      endBalance: 0,
      accountTo: '其他收益',
      voucher: '',
      conclusion: '',
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

  /** 明细表期末合计（供跨Sheet勾稽） */
  function getDetailEndTotal(): number {
    return subtotals.value.endBalance
  }

  /** 企业分摊合计（供 K7-2 vs K7-4 交叉验证） */
  function getAmortTotal(): number {
    return subtotals.value.currentAmort
  }

  // ─── Persist（JSON打包存储） ────────────────────────────────────────────────

  function _persist(): void {
    saveResponse(ITEM_ID_ROWS, { remark: JSON.stringify(detailRows.value) })
    // 同步跨sheet数据到allResponses供computed链使用
    saveResponse('K7-2-detail-end-total', { remark: String(getDetailEndTotal()) })
    saveResponse('K7-2-amort-total', { remark: String(getAmortTotal()) })
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    detailRows,
    activeSection,
    subtotals,
    assetRelatedSubtotal,
    incomeRelatedSubtotal,
    activeColumns,
    sections: [
      { key: 0 as K7DetailSection, label: '基础', columns: BASIC_COLUMNS },
      { key: 1 as K7DetailSection, label: '分摊', columns: AMORT_COLUMNS },
      { key: 2 as K7DetailSection, label: '检查', columns: CHECK_COLUMNS },
    ],
    switchSection,
    updateCell,
    recalcAll,
    addRow,
    removeRow,
    importRows,
    getDetailEndTotal,
    getAmortTotal,
  }
}
