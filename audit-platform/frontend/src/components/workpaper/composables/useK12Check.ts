/**
 * useK12Check — K12-4 检查表逻辑（31行×17列）
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Task: 3.4
 * Requirements: 2~6 全部
 *
 * 职责：
 * - 逐项检查：真实性/依据合规/分类正确性(与日常活动无关，非其他收益6117)/期间归属/税务处理
 * - Per-item conclusion: 合规/不合规/不适用
 * - 行级抽凭 sampling integration（GtVoucherSamplingEngine）
 * - 行级OCR（📎附件列 POST contract-ocr → ElMessageBox确认 → merge）
 * - 红色警告 when any item is "不合规"
 *
 * 分类正确性核对（ADR-3）：
 *   营业外收入(6301) = 与日常活动无关的利得
 *   其他收益(6117/K10) = 与日常活动相关的收益
 *   检查项确认收入是否正确分类
 *
 * Item IDs: "K12-4-check-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 合规判断三态 */
export type ComplianceState = '合规' | '不合规' | '不适用'

/** K12-4 检查行 */
export interface K12CheckRow {
  rowKey: string
  /** 序号 */
  index: number
  /** 检查项名称 */
  checkItem: string
  /** 检查内容描述 */
  description: string
  /** 合规判断 */
  compliance: ComplianceState | null
  /** 审计证据/说明 */
  evidence: string
  /** 附件路径（OCR识别后） */
  attachment: string
  /** 凭证号（抽凭sampling结果） */
  voucherRef: string
  /** 抽凭样本ID */
  sampleId: string
  /** 备注 */
  remark: string
}

/** 不合规摘要 */
export interface K12NonComplianceSummary {
  /** 不合规项数量 */
  count: number
  /** 不合规项详情 */
  items: Array<{ label: string; evidence: string; index: number }>
  /** 是否存在不合规项（红色警告标记） */
  hasNonCompliance: boolean
}

export interface UseK12CheckParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ROWS_KEY = 'K12-4-check-rows'
const ITEM_PREFIX = 'K12-4'

/** K12-4 默认检查项（5大类检查维度） */
const DEFAULT_CHECK_ITEMS: Array<{ checkItem: string; description: string }> = [
  // ─── 真实性检查 ───
  { checkItem: '交易真实性', description: '检查营业外收入是否有真实的经济业务基础，是否存在虚构收入' },
  { checkItem: '收入确认依据', description: '检查收入确认是否有充分的原始凭证支持（政府文件/法院判决/合同等）' },
  { checkItem: '对方单位核实', description: '核实对方单位是否真实存在，交易对手方信息是否完整' },
  // ─── 依据合规 ───
  { checkItem: '政府补助文件', description: '检查政府补助是否有拨款文件/批复/到账通知等完整依据' },
  { checkItem: '债务重组协议', description: '检查债务重组是否有正式的重组协议/法院裁定/债权人同意书' },
  { checkItem: '资产盘盈审批', description: '检查资产盘盈是否经过盘点程序并有管理层审批记录' },
  // ─── 分类正确性（ADR-3核心） ───
  { checkItem: '与日常活动无关', description: '确认该收入与日常活动无关（日常活动相关应计入其他收益6117/K10，非营业外收入6301）' },
  { checkItem: '非其他收益范畴', description: '确认该收入不属于其他收益（6117）的核算范围（政府补助中与日常活动相关部分应归K10）' },
  { checkItem: '利得vs收入区分', description: '确认营业外收入为"利得"性质，非经常性/持续性"收入"' },
  // ─── 期间归属 ───
  { checkItem: '收入确认时点', description: '检查收入是否在满足确认条件的当期确认，无提前/延后确认' },
  { checkItem: '跨期核对', description: '检查期末收入确认是否存在跨期问题（尤其政府补助到账与拨款文件日期）' },
  // ─── 税务处理 ───
  { checkItem: '增值税处理', description: '检查营业外收入的增值税处理是否正确（部分营业外收入免税/不征税）' },
  { checkItem: '企业所得税处理', description: '检查是否正确区分应税收入/免税收入/不征税收入（如符合条件的政府补助）' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK12Check(params: UseK12CheckParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<K12CheckRow[]>([])
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

  function _normalizeRow(raw: any, idx: number): K12CheckRow {
    return {
      rowKey: raw.rowKey ?? `check-${idx}`,
      index: idx + 1,
      checkItem: raw.checkItem ?? '',
      description: raw.description ?? '',
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      attachment: raw.attachment ?? '',
      voucherRef: raw.voucherRef ?? '',
      sampleId: raw.sampleId ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _buildDefaultRows(): K12CheckRow[] {
    return DEFAULT_CHECK_ITEMS.map((item, idx) => ({
      rowKey: `check-${idx}`,
      index: idx + 1,
      checkItem: item.checkItem,
      description: item.description,
      compliance: null,
      evidence: '',
      attachment: '',
      voucherRef: '',
      sampleId: '',
      remark: '',
    }))
  }

  // ─── Computed: 不合规摘要（红色警告） ──────────────────────────────────────

  const nonComplianceSummary: ComputedRef<K12NonComplianceSummary> = computed(() => {
    const items: K12NonComplianceSummary['items'] = []

    for (const row of rows.value) {
      if (row.compliance === '不合规') {
        items.push({
          label: row.checkItem,
          evidence: row.evidence,
          index: row.index,
        })
      }
    }

    return {
      count: items.length,
      items,
      hasNonCompliance: items.length > 0,
    }
  })

  // ─── Computed: 检查进度 ────────────────────────────────────────────────────

  const checkProgress: ComputedRef<{ total: number; completed: number; rate: number }> = computed(() => {
    const total = rows.value.length
    const completed = rows.value.filter(r => r.compliance != null).length
    return { total, completed, rate: total > 0 ? completed / total : 0 }
  })

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCompliance(rowKey: string, state: ComplianceState): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.compliance = state
    isChanged.value = true
    _persist()
  }

  function updateEvidence(rowKey: string, evidence: string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.evidence = evidence
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
   * @param voucherRef 凭证编号
   * @param sampleId 抽凭样本ID
   */
  function setSamplingResult(rowKey: string, voucherRef: string, sampleId: string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.voucherRef = voucherRef
    row.sampleId = sampleId
    isChanged.value = true
    _persist()
  }

  // ─── 行级OCR 附件 ─────────────────────────────────────────────────────────

  /**
   * OCR识别结果回填（📎附件列 POST contract-ocr → 确认后merge）
   * @param rowKey 检查项行key
   * @param attachment 附件路径/URL
   * @param ocrResult OCR识别内容（merge到evidence）
   */
  function setOcrResult(rowKey: string, attachment: string, ocrResult: string): void {
    if (isReadonly?.value) return
    const row = rows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.attachment = attachment
    // OCR内容追加到审计证据
    if (ocrResult) {
      row.evidence = row.evidence
        ? `${row.evidence}\n[OCR识别] ${ocrResult}`
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
    checkProgress,
    updateCompliance,
    updateEvidence,
    updateCell,
    setSamplingResult,
    setOcrResult,
    saveConclusion,
    initFromResponses,
  }
}

export default useK12Check
