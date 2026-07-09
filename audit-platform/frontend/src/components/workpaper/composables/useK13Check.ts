/**
 * useK13Check — K13-4 检查表逻辑（营业外支出逐项检查）
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 逐项检查：真实性/依据合规/审批完整/分类正确性(与日常活动无关)/期间归属/税前扣除性
 * - Per-item conclusion: 合规/不合规/不适用（三态）
 * - 税前扣除性选项：可全额扣除/限额扣除(12%)/不可扣除/需备案后扣除
 * - 行级抽凭 sampling integration（GtVoucherSamplingEngine）
 * - 行级OCR（📎附件列 POST contract-ocr → ElMessageBox确认 → merge）
 * - 红色警告 when any item is "不合规"
 *
 * 分类正确性核对（ADR-3）：
 *   营业外支出(6711) = 与日常活动无关的损失
 *   管理费用/销售费用(6602/6601) = 与日常活动相关的费用
 *   检查项确认支出是否正确分类
 *
 * 税前扣除性核对（K13特有）：
 *   捐赠支出 → 公益性捐赠限额扣除(年度利润12%)
 *   罚款滞纳金 → 行政罚款不可扣除
 *   资产损失 → 需税务备案后扣除
 *
 * Item IDs: "K13-4-check-rows", "K13-4-conclusion", "K13-4-voucher-{rowKey}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 合规判断三态 */
export type ComplianceState = '合规' | '不合规' | '不适用'

/** 税前扣除性选项（K13特有） */
export type TaxDeductibility = '可全额扣除' | '限额扣除(12%)' | '不可扣除' | '需备案后扣除'

/** K13-4 检查行 */
export interface K13CheckRow {
  rowKey: string
  /** 序号 */
  index: number
  /** 检查项名称 */
  checkItem: string
  /** 检查内容描述 */
  description: string
  // ─── 六大检查维度 ───
  /** 真实性 */
  truthfulness: ComplianceState | null
  /** 依据合规 */
  compliance: ComplianceState | null
  /** 审批完整 */
  approval: ComplianceState | null
  /** 分类正确性（与日常活动无关） */
  classification: ComplianceState | null
  /** 期间归属 */
  periodAttribution: ComplianceState | null
  /** 税前扣除性 */
  taxDeductibility: TaxDeductibility | null
  // ─── 抽凭/OCR ───
  /** 凭证号（抽凭sampling结果） */
  voucherNumber: string
  /** OCR附件路径 */
  ocrAttachment: string
  /** 检查结果/审计证据 */
  checkResult: string
  /** 备注 */
  remark: string
}

/** 不合规摘要 */
export interface K13NonComplianceSummary {
  /** 不合规项数量 */
  count: number
  /** 不合规项详情 */
  items: Array<{ label: string; field: string; index: number }>
  /** 是否存在不合规项（红色警告标记） */
  hasNonCompliance: boolean
}

export interface UseK13CheckParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K13-4-check-rows'
const ITEM_PREFIX = 'K13-4'

/** 六大检查维度字段名 */
export const CHECK_DIMENSIONS: Array<{ field: keyof K13CheckRow; label: string }> = [
  { field: 'truthfulness', label: '真实性' },
  { field: 'compliance', label: '依据合规' },
  { field: 'approval', label: '审批完整' },
  { field: 'classification', label: '分类正确性' },
  { field: 'periodAttribution', label: '期间归属' },
]

/** 税前扣除性选项 */
export const TAX_DEDUCTIBILITY_OPTIONS: TaxDeductibility[] = [
  '可全额扣除',
  '限额扣除(12%)',
  '不可扣除',
  '需备案后扣除',
]

/** 合规三态选项 */
export const COMPLIANCE_OPTIONS: ComplianceState[] = ['合规', '不合规', '不适用']

/** K13-4 默认检查项（按支出类别/逐项检查） */
const DEFAULT_CHECK_ITEMS: Array<{ checkItem: string; description: string }> = [
  // ─── 真实性检查 ───
  { checkItem: '交易真实性', description: '检查营业外支出是否有真实的经济业务基础，是否存在虚增支出' },
  { checkItem: '支出确认依据', description: '检查支出确认是否有充分的原始凭证支持（法院判决/行政处罚决定/报废审批/盘亏报告等）' },
  { checkItem: '对方单位核实', description: '核实受赠方/收款方是否真实存在，交易对手方信息是否完整' },
  // ─── 依据合规 ───
  { checkItem: '捐赠支出凭证', description: '检查公益性捐赠是否有省级以上民政/财政部门出具的捐赠票据' },
  { checkItem: '罚款滞纳金通知', description: '检查罚款/滞纳金是否有行政处罚决定书/税务缴款通知书等法定文书' },
  { checkItem: '资产报废审批', description: '检查非流动资产处置/报废是否经过完整的资产处置审批流程' },
  // ─── 分类正确性 ───
  { checkItem: '与日常活动无关', description: '确认该支出与日常活动无关（日常活动相关应计入管理费用6602/销售费用6601，非营业外支出6711）' },
  { checkItem: '损失vs费用区分', description: '确认营业外支出为"损失"性质（偶发性/非经常性），非日常经营"费用"' },
  // ─── 期间归属 ───
  { checkItem: '支出确认时点', description: '检查支出是否在满足确认条件的当期确认，无提前/延后确认' },
  { checkItem: '跨期核对', description: '检查期末支出确认是否存在跨期问题（尤其处罚决定日期与付款日期不一致）' },
  // ─── 税前扣除性（K13特有） ───
  { checkItem: '捐赠支出扣除', description: '公益性捐赠：年度利润总额12%以内部分准予扣除，超出部分结转3年（企业所得税法第9条）' },
  { checkItem: '罚款滞纳金扣除', description: '行政罚款/税收滞纳金不得税前扣除（企业所得税法第10条）；经营性违约金可扣除' },
  { checkItem: '资产损失扣除', description: '资产损失需按规定向税务机关备案后方可税前扣除（国家税务总局公告2011年第25号）' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK13Check(params: UseK13CheckParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K13CheckRow[]>([])
  const checkConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      rows.value = raw.map((r: any, idx: number) => _normalizeRow(r, idx))
    } else {
      rows.value = _buildDefaultRows()
    }
    checkConclusion.value = _getString(`${ITEM_PREFIX}-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any, idx: number): K13CheckRow {
    return {
      rowKey: raw.rowKey ?? `check-${idx}`,
      index: idx + 1,
      checkItem: raw.checkItem ?? '',
      description: raw.description ?? '',
      truthfulness: raw.truthfulness ?? null,
      compliance: raw.compliance ?? null,
      approval: raw.approval ?? null,
      classification: raw.classification ?? null,
      periodAttribution: raw.periodAttribution ?? null,
      taxDeductibility: raw.taxDeductibility ?? null,
      voucherNumber: raw.voucherNumber ?? '',
      ocrAttachment: raw.ocrAttachment ?? '',
      checkResult: raw.checkResult ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _buildDefaultRows(): K13CheckRow[] {
    return DEFAULT_CHECK_ITEMS.map((item, idx) => ({
      rowKey: `check-${idx}`,
      index: idx + 1,
      checkItem: item.checkItem,
      description: item.description,
      truthfulness: null,
      compliance: null,
      approval: null,
      classification: null,
      periodAttribution: null,
      taxDeductibility: null,
      voucherNumber: '',
      ocrAttachment: '',
      checkResult: '',
      remark: '',
    }))
  }

  // ─── Computed: 不合规摘要（红色警告） ──────────────────────────────────────

  const nonComplianceSummary: ComputedRef<K13NonComplianceSummary> = computed(() => {
    const items: K13NonComplianceSummary['items'] = []
    const complianceFields: Array<{ field: keyof K13CheckRow; label: string }> = [
      { field: 'truthfulness', label: '真实性' },
      { field: 'compliance', label: '依据合规' },
      { field: 'approval', label: '审批完整' },
      { field: 'classification', label: '分类正确性' },
      { field: 'periodAttribution', label: '期间归属' },
    ]

    for (const row of rows.value) {
      for (const dim of complianceFields) {
        if (row[dim.field] === '不合规') {
          items.push({
            label: `${row.checkItem} - ${dim.label}`,
            field: dim.field,
            index: row.index,
          })
        }
      }
    }

    return {
      count: items.length,
      items,
      hasNonCompliance: items.length > 0,
    }
  })

  /** 便捷 computed: 是否存在任何不合规项 */
  const hasNonCompliant: ComputedRef<boolean> = computed(() => {
    return nonComplianceSummary.value.hasNonCompliance
  })

  // ─── Computed: 检查进度 ────────────────────────────────────────────────────

  const checkProgress: ComputedRef<{ total: number; completed: number; rate: number }> = computed(() => {
    const total = rows.value.length
    // 至少有一个维度被填写视为完成
    const completed = rows.value.filter(r =>
      r.truthfulness != null ||
      r.compliance != null ||
      r.approval != null ||
      r.classification != null ||
      r.periodAttribution != null ||
      r.taxDeductibility != null
    ).length
    return { total, completed, rate: total > 0 ? completed / total : 0 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCompliance(rowKey: string, field: string, state: ComplianceState): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = state
    isChanged.value = true
    _persist()
  }

  function updateTaxDeductibility(rowKey: string, value: TaxDeductibility): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.taxDeductibility = value
    isChanged.value = true
    _persist()
  }

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = value
    isChanged.value = true
    _persist()
  }

  // ─── 行级抽凭 sampling ────────────────────────────────────────────────────

  /**
   * 抽凭结果回填（GtVoucherSamplingEngine回调）
   * @param rowKey 检查项行key
   * @param voucherNumber 凭证编号
   * @param checkResult 检查结果文本
   */
  function setSamplingResult(rowKey: string, voucherNumber: string, checkResult: string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.voucherNumber = voucherNumber
    if (checkResult) {
      row.checkResult = row.checkResult
        ? `${row.checkResult}\n[抽凭] ${checkResult}`
        : `[抽凭] ${checkResult}`
    }
    isChanged.value = true
    _persist()
  }

  // ─── 行级OCR 附件 ─────────────────────────────────────────────────────────

  /**
   * OCR识别结果回填（📎附件列 POST contract-ocr → 确认后merge）
   * @param rowKey 检查项行key
   * @param attachment 附件路径/URL
   * @param ocrResult OCR识别内容（merge到checkResult）
   */
  function setOcrResult(rowKey: string, attachment: string, ocrResult: string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.ocrAttachment = attachment
    // OCR内容追加到检查结果
    if (ocrResult) {
      row.checkResult = row.checkResult
        ? `${row.checkResult}\n[OCR识别] ${ocrResult}`
        : `[OCR识别] ${ocrResult}`
    }
    isChanged.value = true
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
  }

  function saveConclusion(text: string): void {
    checkConclusion.value = text
    onSave?.(`${ITEM_PREFIX}-conclusion`, text)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    checkConclusion,
    isChanged,
    nonComplianceSummary,
    hasNonCompliant,
    checkProgress,
    updateCompliance,
    updateTaxDeductibility,
    updateCell,
    setSamplingResult,
    setOcrResult,
    saveConclusion,
    initFromResponses,
  }
}

export default useK13Check
