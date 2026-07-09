/**
 * useH1AdditionCheck — H1-7 增加检查表 composable
 *
 * AdditionRow 24列 + 抽样参数 + 汇总统计
 * 集成voucher-sampling-engine + OCR端点
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.9
 * Requirements: 8.1-8.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AdditionRow {
  rowId: string
  seq: number                    // 序号
  name: string                   // 资产名称
  assetNo: string                // 资产编号
  acquisitionDate: string        // 入账日期
  originalCost: number           // 原值
  // 凭证核对
  contractRef: string            // 合同编号
  contractAmount: number         // 合同金额
  invoiceRef: string             // 发票号
  invoiceAmount: number          // 发票金额
  acceptanceRef: string          // 验收单号
  paymentRef: string             // 付款凭证号
  paymentAmount: number          // 付款金额
  // 资本化判断
  capitalizationBasis: string    // 资本化依据
  expenseOrCapital: string       // 费用/资本化
  accountCode: string            // 入账科目
  depStartDate: string           // 折旧起算日
  // OCR + 附件
  attachmentUrl: string          // 附件URL
  ocrResult: string              // OCR识别结果
  // 审计结论
  checkResult: string            // 检查结果(无异常/有异常)
  conclusion: string             // 审计结论
  remark: string                 // 备注
  indexRef: string               // 索引引用
  voucherSampleId: string        // 抽凭引擎样本ID
}

/** 抽样参数 */
export interface SamplingParams {
  totalPopulation: number        // 测试总体金额
  samplingMethod: string         // 抽样方法
  sampleSize: number             // 样本量
  coverageRate: number           // 覆盖率(%)
}

/** 汇总统计 */
export interface AdditionSummary {
  checkedCount: number           // 已检查笔数
  checkedAmount: number          // 检查金额合计
  coverageRate: number           // 覆盖率(%)
  anomalyCount: number           // 发现异常笔数
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-7'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1AdditionCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    totalAdditionAmount?: Ref<number>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<AdditionRow[]>([])
  const samplingParams = ref<SamplingParams>({
    totalPopulation: 0,
    samplingMethod: '货币单元抽样',
    sampleSize: 0,
    coverageRate: 0,
  })
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const rowItem = allResponses.value.get(`${ITEM_PREFIX}-rows`)
    if (rowItem?.remark) {
      try {
        const parsed = JSON.parse(rowItem.remark)
        rows.value = Array.isArray(parsed) ? parsed.map(_normalizeRow) : []
      } catch { rows.value = [] }
    } else { rows.value = [] }

    const paramItem = allResponses.value.get(`${ITEM_PREFIX}-sampling-params`)
    if (paramItem?.remark) {
      try {
        const p = JSON.parse(paramItem.remark)
        samplingParams.value = {
          totalPopulation: Number(p.totalPopulation) || 0,
          samplingMethod: p.samplingMethod ?? '货币单元抽样',
          sampleSize: Number(p.sampleSize) || 0,
          coverageRate: Number(p.coverageRate) || 0,
        }
      } catch { /* keep defaults */ }
    }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any, idx: number): AdditionRow {
    return {
      rowId: raw.rowId ?? `add-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      acquisitionDate: raw.acquisitionDate ?? '',
      originalCost: Number(raw.originalCost) || 0,
      contractRef: raw.contractRef ?? '',
      contractAmount: Number(raw.contractAmount) || 0,
      invoiceRef: raw.invoiceRef ?? '',
      invoiceAmount: Number(raw.invoiceAmount) || 0,
      acceptanceRef: raw.acceptanceRef ?? '',
      paymentRef: raw.paymentRef ?? '',
      paymentAmount: Number(raw.paymentAmount) || 0,
      capitalizationBasis: raw.capitalizationBasis ?? '',
      expenseOrCapital: raw.expenseOrCapital ?? '资本化',
      accountCode: raw.accountCode ?? '',
      depStartDate: raw.depStartDate ?? '',
      attachmentUrl: raw.attachmentUrl ?? '',
      ocrResult: raw.ocrResult ?? '',
      checkResult: raw.checkResult ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      indexRef: raw.indexRef ?? '',
      voucherSampleId: raw.voucherSampleId ?? '',
    }
  }

  // ─── Computed: 汇总 ────────────────────────────────────────────────────────

  const summary = computed<AdditionSummary>(() => {
    const checkedCount = rows.value.length
    const checkedAmount = calcSubtotal(rows.value.map((r) => r.originalCost))
    const totalAdd = options?.totalAdditionAmount?.value ?? samplingParams.value.totalPopulation
    const coverageRate = totalAdd > 0 ? (checkedAmount / totalAdd * 100) : 0
    const anomalyCount = rows.value.filter((r) => r.checkResult === '有异常').length
    return { checkedCount, checkedAmount, coverageRate, anomalyCount }
  })

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(): void {
    const newRow: AdditionRow = {
      rowId: `add-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      name: '', assetNo: '', acquisitionDate: '', originalCost: 0,
      contractRef: '', contractAmount: 0, invoiceRef: '', invoiceAmount: 0,
      acceptanceRef: '', paymentRef: '', paymentAmount: 0,
      capitalizationBasis: '', expenseOrCapital: '资本化', accountCode: '',
      depStartDate: '', attachmentUrl: '', ocrResult: '',
      checkResult: '', conclusion: '', remark: '', indexRef: '', voucherSampleId: '',
    }
    rows.value.push(newRow)
    _persist()
  }

  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.value.splice(idx, 1)
      rows.value.forEach((r, i) => { r.seq = i + 1 })
      _persist()
    }
  }

  function updateCell(rowId: string, field: keyof AdditionRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persist()
  }

  /** OCR结果填入指定行 */
  function mergeOcrResult(rowId: string, ocrData: Record<string, any>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (ocrData.contractRef) row.contractRef = ocrData.contractRef
    if (ocrData.contractAmount) row.contractAmount = Number(ocrData.contractAmount) || 0
    if (ocrData.invoiceRef) row.invoiceRef = ocrData.invoiceRef
    if (ocrData.invoiceAmount) row.invoiceAmount = Number(ocrData.invoiceAmount) || 0
    row.ocrResult = JSON.stringify(ocrData)
    _persist()
  }

  function updateSamplingParams(params: Partial<SamplingParams>): void {
    Object.assign(samplingParams.value, params)
    options?.onSave?.(`${ITEM_PREFIX}-sampling-params`, samplingParams.value)
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    options?.onSave?.(`${ITEM_PREFIX}-rows`, rows.value)
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    samplingParams,
    auditNote,
    auditConclusion,
    summary,
    addRow,
    removeRow,
    updateCell,
    mergeOcrResult,
    updateSamplingParams,
    saveNote,
    saveConclusion,
  }
}

export default useH1AdditionCheck
