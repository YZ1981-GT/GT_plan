/**
 * useH1DisposalCheck — H1-8 减少检查表 composable
 *
 * DisposalRow 27列 + 处置损益公式 + 汇总
 * 集成voucher-sampling-engine + EventBus联动H10
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.10
 * Requirements: 9.1-9.11
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcSubtotal, calcNetValue } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisposalRow {
  rowId: string
  seq: number                     // 序号
  name: string                    // 资产名称
  assetNo: string                 // 资产编号
  disposalDate: string            // 处置日期
  disposalMethod: string          // 处置方式(出售/报废/捐赠/盘亏)
  // 借方区
  originalCost: number            // 原值
  accDep: number                  // 累计折旧
  impairment: number              // 减值准备
  disposalIncome: number          // 处置收入
  // 贷方区
  netValue: number                // 净值（公式）
  disposalCost: number            // 处置费用
  disposalGainLoss: number        // 处置损益（公式）
  // 检查列
  approvalDoc: string             // 审批文件
  evaluationReport: string        // 评估报告
  paymentVoucher: string          // 收款凭证
  isRelatedParty: string          // 是否关联方(Y/N)
  relatedPartyName: string        // 关联方名称
  pricingBasis: string            // 定价依据
  taxTreatment: string            // 税务处理
  accountEntry: string            // 会计分录
  // 审计
  checkResult: string             // 检查结果
  conclusion: string              // 审计结论
  remark: string                  // 备注
  indexRef: string                // 索引引用
  voucherSampleId: string         // 抽凭引擎样本ID
  attachmentUrl: string           // 附件
}

/** 抽样参数 */
export interface DisposalSamplingParams {
  totalPopulation: number
  samplingMethod: string
  sampleSize: number
  coverageRate: number
}

/** 汇总统计 */
export interface DisposalSummary {
  checkedCount: number
  disposalAmountTotal: number     // 处置金额(原值)合计
  gainLossTotal: number           // 处置损益合计
  coverageRate: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H1-8'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1DisposalCheck(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    totalDecreaseAmount?: Ref<number>
    onSave?: (itemId: string, value: any) => void
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<DisposalRow[]>([])
  const samplingParams = ref<DisposalSamplingParams>({
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

  function _normalizeRow(raw: any, idx: number): DisposalRow {
    const row: DisposalRow = {
      rowId: raw.rowId ?? `disp-${Math.random().toString(36).slice(2, 10)}`,
      seq: raw.seq ?? idx + 1,
      name: raw.name ?? '',
      assetNo: raw.assetNo ?? '',
      disposalDate: raw.disposalDate ?? '',
      disposalMethod: raw.disposalMethod ?? '',
      originalCost: Number(raw.originalCost) || 0,
      accDep: Number(raw.accDep) || 0,
      impairment: Number(raw.impairment) || 0,
      disposalIncome: Number(raw.disposalIncome) || 0,
      netValue: 0,
      disposalCost: Number(raw.disposalCost) || 0,
      disposalGainLoss: 0,
      approvalDoc: raw.approvalDoc ?? '',
      evaluationReport: raw.evaluationReport ?? '',
      paymentVoucher: raw.paymentVoucher ?? '',
      isRelatedParty: raw.isRelatedParty ?? 'N',
      relatedPartyName: raw.relatedPartyName ?? '',
      pricingBasis: raw.pricingBasis ?? '',
      taxTreatment: raw.taxTreatment ?? '',
      accountEntry: raw.accountEntry ?? '',
      checkResult: raw.checkResult ?? '',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
      indexRef: raw.indexRef ?? '',
      voucherSampleId: raw.voucherSampleId ?? '',
      attachmentUrl: raw.attachmentUrl ?? '',
    }
    _recalcRow(row)
    return row
  }

  /** 重算公式列：净值 + 处置损益 */
  function _recalcRow(row: DisposalRow): void {
    row.netValue = calcNetValue(row.originalCost, row.accDep, row.impairment)
    // 处置损益 = 处置收入 - 净值 - 处置费用
    row.disposalGainLoss = row.disposalIncome - row.netValue - row.disposalCost
  }

  // ─── Computed: 汇总 ────────────────────────────────────────────────────────

  const summary = computed<DisposalSummary>(() => {
    const checkedCount = rows.value.length
    const disposalAmountTotal = calcSubtotal(rows.value.map((r) => r.originalCost))
    const gainLossTotal = calcSubtotal(rows.value.map((r) => r.disposalGainLoss))
    const totalDec = options?.totalDecreaseAmount?.value ?? samplingParams.value.totalPopulation
    const coverageRate = totalDec > 0 ? (disposalAmountTotal / totalDec * 100) : 0
    return { checkedCount, disposalAmountTotal, gainLossTotal, coverageRate }
  })

  /** 处置收入合计 */
  const incomeTotal = computed(() => calcSubtotal(rows.value.map((r) => r.disposalIncome)))
  /** 处置损益合计 */
  const gainLossTotal = computed(() => calcSubtotal(rows.value.map((r) => r.disposalGainLoss)))

  // ─── CRUD ──────────────────────────────────────────────────────────────────

  function addRow(name = ''): void {
    const newRow: DisposalRow = {
      rowId: `disp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      seq: rows.value.length + 1,
      name, assetNo: '', disposalDate: '', disposalMethod: '',
      originalCost: 0, accDep: 0, impairment: 0, disposalIncome: 0,
      netValue: 0, disposalCost: 0, disposalGainLoss: 0,
      approvalDoc: '', evaluationReport: '', paymentVoucher: '',
      isRelatedParty: 'N', relatedPartyName: '', pricingBasis: '',
      taxTreatment: '', accountEntry: '',
      checkResult: '', conclusion: '', remark: '', indexRef: '',
      voucherSampleId: '', attachmentUrl: '',
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

  function updateCell(rowId: string, field: keyof DisposalRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _recalcRow(row)
    _persist()
  }

  // ─── EventBus: 处置完成联动H10 ────────────────────────────────────────────

  function publishDisposalCompleted(): void {
    options?.onPublishEvent?.('h1:disposal-completed', {
      wp_code: 'H1',
      rows: rows.value.map((r) => ({
        name: r.name,
        assetNo: r.assetNo,
        disposalMethod: r.disposalMethod,
        disposalDate: r.disposalDate,
        originalCost: r.originalCost,
        netValue: r.netValue,
        disposalGainLoss: r.disposalGainLoss,
      })),
      totalGainLoss: summary.value.gainLossTotal,
    })
  }

  function updateSamplingParams(params: Partial<DisposalSamplingParams>): void {
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
    incomeTotal,
    gainLossTotal,
    addRow,
    removeRow,
    updateCell,
    publishDisposalCompleted,
    updateSamplingParams,
    saveNote,
    saveConclusion,
  }
}

export default useH1DisposalCheck
