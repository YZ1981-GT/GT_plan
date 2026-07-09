/**
 * useK8Checks — K8-5/K8-8 检查表逻辑
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.4
 * Requirements: 6.1-6.4
 *
 * 职责：
 * - K8-5 合同检查表：检查重大费用合同（广告/推广/运输）的真实性/金额匹配/审批
 * - K8-8 销售费用综合检查表：逐项"合规/不合规/不适用"判断
 * - Per-row compliance judgment: 合规/不合规/不适用
 * - 不合规项红色摘要
 * - 支持行级抽凭+行级OCR
 *
 * Item IDs: "K8-5-row-{idx}-{field}" / "K8-8-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 合规判断三态 */
export type ComplianceState = '合规' | '不合规' | '不适用'

/** 检查表sheet标识 */
export type K8CheckSheetId = 'K8-5' | 'K8-8'

/** K8-5 合同检查行 */
export interface K8ContractCheckRow {
  rowKey: string
  /** 序号 */
  index: number
  /** 合同名称 */
  contractName: string
  /** 合同类型（广告/推广/运输/其他） */
  contractType: string
  /** 合同金额 */
  contractAmount: number
  /** 实际支付金额 */
  paidAmount: number
  /** 金额匹配判断（公式：|合同金额-实际支付|<允差） */
  amountMatched: boolean
  /** 审批是否完整 */
  approvalComplete: ComplianceState | null
  /** 真实性判断 */
  authenticity: ComplianceState | null
  /** 综合合规判断 */
  compliance: ComplianceState | null
  /** 审计证据/说明 */
  evidence: string
  /** 附件（OCR识别后） */
  attachment: string
  /** 备注 */
  remark: string
}

/** K8-8 综合检查行 */
export interface K8SellingCheckRow {
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
  /** 附件 */
  attachment: string
  /** 备注 */
  remark: string
}

/** 不合规摘要 */
export interface K8NonComplianceSummary {
  /** 不合规项数量 */
  count: number
  /** 不合规项详情 */
  items: Array<{ sheetId: K8CheckSheetId; label: string; evidence: string }>
}

export interface UseK8ChecksParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** K8-8 默认检查项 */
const DEFAULT_SELLING_CHECKS = [
  { checkItem: '费用归属期间', description: '检查销售费用是否归入正确的会计期间' },
  { checkItem: '费用分类', description: '检查费用分类是否正确（是否混入管理费用/研发费用）' },
  { checkItem: '关联方交易', description: '检查是否存在未披露的关联方销售费用交易' },
  { checkItem: '大额异常支出', description: '检查是否存在无合理商业理由的大额支出' },
  { checkItem: '会计政策一致性', description: '检查销售费用会计政策是否与上期一致' },
  { checkItem: '税前扣除合规', description: '检查广告费、招待费等是否超出税前扣除限额' },
  { checkItem: '凭证附件完整', description: '检查重大费用是否有完整的原始凭证支持' },
  { checkItem: '审批流程合规', description: '检查大额费用是否经过适当审批' },
]

/** 金额匹配容差（元） */
const AMOUNT_TOLERANCE = 100

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK8Checks(params: UseK8ChecksParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const contractRows = ref<K8ContractCheckRow[]>([])
  const sellingCheckRows = ref<K8SellingCheckRow[]>([])
  const contractConclusion = ref('')
  const sellingConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    // K8-5 合同检查
    const rawContract = _getJson('K8-5-contract-rows')
    if (Array.isArray(rawContract) && rawContract.length > 0) {
      contractRows.value = rawContract.map((r: any, idx: number) => _normalizeContractRow(r, idx))
    } else {
      contractRows.value = []
    }
    contractConclusion.value = _getString('K8-5-conclusion')

    // K8-8 综合检查
    const rawSelling = _getJson('K8-8-check-rows')
    if (Array.isArray(rawSelling) && rawSelling.length > 0) {
      sellingCheckRows.value = rawSelling.map((r: any, idx: number) => _normalizeSellingRow(r, idx))
    } else {
      sellingCheckRows.value = _buildDefaultSellingRows()
    }
    sellingConclusion.value = _getString('K8-8-conclusion')
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

  function _normalizeContractRow(raw: any, idx: number): K8ContractCheckRow {
    const contractAmount = Number(raw.contractAmount) || 0
    const paidAmount = Number(raw.paidAmount) || 0
    const amountMatched = Math.abs(contractAmount - paidAmount) <= AMOUNT_TOLERANCE

    return {
      rowKey: raw.rowKey ?? `contract-${idx}`,
      index: idx + 1,
      contractName: raw.contractName ?? '',
      contractType: raw.contractType ?? '',
      contractAmount,
      paidAmount,
      amountMatched,
      approvalComplete: raw.approvalComplete ?? null,
      authenticity: raw.authenticity ?? null,
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      attachment: raw.attachment ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeSellingRow(raw: any, idx: number): K8SellingCheckRow {
    return {
      rowKey: raw.rowKey ?? `selling-${idx}`,
      index: idx + 1,
      checkItem: raw.checkItem ?? '',
      description: raw.description ?? '',
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      attachment: raw.attachment ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _buildDefaultSellingRows(): K8SellingCheckRow[] {
    return DEFAULT_SELLING_CHECKS.map((item, idx) => ({
      rowKey: `selling-${idx}`,
      index: idx + 1,
      checkItem: item.checkItem,
      description: item.description,
      compliance: null,
      evidence: '',
      attachment: '',
      remark: '',
    }))
  }

  // ─── Computed: 不合规摘要（红色汇总） ──────────────────────────────────────

  const nonComplianceSummary: ComputedRef<K8NonComplianceSummary> = computed(() => {
    const items: K8NonComplianceSummary['items'] = []

    // K8-5 合同检查不合规项
    for (const row of contractRows.value) {
      if (row.compliance === '不合规') {
        items.push({ sheetId: 'K8-5', label: row.contractName || `合同${row.index}`, evidence: row.evidence })
      }
    }

    // K8-8 综合检查不合规项
    for (const row of sellingCheckRows.value) {
      if (row.compliance === '不合规') {
        items.push({ sheetId: 'K8-8', label: row.checkItem, evidence: row.evidence })
      }
    }

    return { count: items.length, items }
  })

  // ─── K8-5 合同检查操作 ─────────────────────────────────────────────────────

  function addContractRow(contractName: string): void {
    if (isReadonly?.value) return
    const idx = contractRows.value.length
    contractRows.value.push({
      rowKey: `contract-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      index: idx + 1,
      contractName,
      contractType: '',
      contractAmount: 0, paidAmount: 0, amountMatched: true,
      approvalComplete: null, authenticity: null, compliance: null,
      evidence: '', attachment: '', remark: '',
    })
    isChanged.value = true
    _persistContract()
  }

  function removeContractRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = contractRows.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      contractRows.value.splice(idx, 1)
      isChanged.value = true
      _persistContract()
    }
  }

  function updateContractCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = contractRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = value

    // 自动重算金额匹配
    if (field === 'contractAmount' || field === 'paidAmount') {
      row.amountMatched = Math.abs(row.contractAmount - row.paidAmount) <= AMOUNT_TOLERANCE
    }

    isChanged.value = true
    _persistContract()
  }

  // ─── K8-8 综合检查操作 ─────────────────────────────────────────────────────

  function updateSellingCheckCompliance(rowKey: string, state: ComplianceState): void {
    if (isReadonly?.value) return
    const row = sellingCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.compliance = state
    isChanged.value = true
    _persistSelling()
  }

  function updateSellingCheckEvidence(rowKey: string, evidence: string): void {
    if (isReadonly?.value) return
    const row = sellingCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.evidence = evidence
    isChanged.value = true
    _persistSelling()
  }

  function updateSellingCheckCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = sellingCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = value
    isChanged.value = true
    _persistSelling()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistContract(): void {
    if (!onSave) return
    onSave('K8-5-contract-rows', contractRows.value)
  }

  function _persistSelling(): void {
    if (!onSave) return
    onSave('K8-8-check-rows', sellingCheckRows.value)
  }

  function saveContractConclusion(text: string): void {
    contractConclusion.value = text
    onSave?.('K8-5-conclusion', text)
  }

  function saveSellingConclusion(text: string): void {
    sellingConclusion.value = text
    onSave?.('K8-8-conclusion', text)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // K8-5 合同检查
    contractRows,
    contractConclusion,
    addContractRow,
    removeContractRow,
    updateContractCell,
    saveContractConclusion,
    // K8-8 综合检查
    sellingCheckRows,
    sellingConclusion,
    updateSellingCheckCompliance,
    updateSellingCheckEvidence,
    updateSellingCheckCell,
    saveSellingConclusion,
    // 汇总
    nonComplianceSummary,
    isChanged,
    initFromResponses,
  }
}

export default useK8Checks
