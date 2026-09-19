/**
 * useK9Checks — K9-5 合同检查 + K9-8 综合检查逻辑
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.4
 * Requirements: 6.1-6.4
 *
 * 职责：
 * - K9-5 合同检查表：检查重大费用合同（中介服务/咨询/租赁）的真实性/金额匹配/审批
 * - K9-8 管理费用综合检查表：逐项"合规/不合规/不适用"判断
 * - Per-row compliance judgment: 合规/不合规/不适用
 * - 不合规项红色摘要
 * - 支持行级抽凭+行级OCR
 *
 * Item IDs: "K9-5-row-{idx}-{field}" / "K9-8-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 合规判断三态 */
export type ComplianceState = '合规' | '不合规' | '不适用'

/** 检查表sheet标识 */
export type K9CheckSheetId = 'K9-5' | 'K9-8'

/** K9-5 合同检查行 */
export interface K9ContractCheckRow {
  rowKey: string
  /** 序号 */
  index: number
  /** 合同名称 */
  contractName: string
  /** 合同类型（中介服务/咨询/租赁/其他） */
  contractType: string
  /** 合同金额 */
  contractAmount: number
  /** 实际支付金额 */
  paidAmount: number
  /** 金额匹配判断（公式：|合同金额-实际支付|<允差） */
  amountMatched: boolean
  /** 合同期限起始日 */
  startDate: string
  /** 合同期限截止日 */
  endDate: string
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

/** K9-8 综合检查行 */
export interface K9AdminCheckRow {
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
export interface K9NonComplianceSummary {
  count: number
  items: Array<{ sheetId: K9CheckSheetId; label: string; evidence: string }>
}

export interface UseK9ChecksParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** K9-8 默认检查项（管理费用专属） */
const DEFAULT_ADMIN_CHECKS = [
  { checkItem: '费用归属期间', description: '检查管理费用是否归入正确的会计期间' },
  { checkItem: '费用分类', description: '检查费用分类是否正确（是否混入销售费用/研发费用）' },
  { checkItem: '关联方交易', description: '检查是否存在未披露的关联方管理费用交易' },
  { checkItem: '大额异常支出', description: '检查是否存在无合理商业理由的大额管理支出' },
  { checkItem: '会计政策一致性', description: '检查管理费用会计政策是否与上期一致' },
  { checkItem: '税前扣除合规', description: '检查咨询费、招待费等是否超出税前扣除限额' },
  { checkItem: '凭证附件完整', description: '检查重大费用是否有完整的原始凭证支持' },
  { checkItem: '审批流程合规', description: '检查大额费用是否经过适当审批' },
  { checkItem: '研发费用划分', description: '检查研发费用是否正确从管理费用中划分' },
  { checkItem: '折旧摊销合理性', description: '检查折旧和摊销计提是否合理一致' },
]

/** 金额匹配容差（元） */
const AMOUNT_TOLERANCE = 100

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK9Checks(params: UseK9ChecksParams) {
  const { allResponses, projectId, wpId, isReadonly, onSave } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const contractRows = ref<K9ContractCheckRow[]>([])
  const adminCheckRows = ref<K9AdminCheckRow[]>([])
  const contractConclusion = ref('')
  const adminConclusion = ref('')
  const isChanged = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    // K9-5 合同检查
    const rawContract = _getJson('K9-5-contract-rows')
    if (Array.isArray(rawContract) && rawContract.length > 0) {
      contractRows.value = rawContract.map((r: any, idx: number) => _normalizeContractRow(r, idx))
    } else {
      contractRows.value = []
    }
    contractConclusion.value = _getString('K9-5-conclusion')

    // K9-8 综合检查
    const rawAdmin = _getJson('K9-8-check-rows')
    if (Array.isArray(rawAdmin) && rawAdmin.length > 0) {
      adminCheckRows.value = rawAdmin.map((r: any, idx: number) => _normalizeAdminRow(r, idx))
    } else {
      adminCheckRows.value = _buildDefaultAdminRows()
    }
    adminConclusion.value = _getString('K9-8-conclusion')
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

  function _normalizeContractRow(raw: any, idx: number): K9ContractCheckRow {
    const contractAmount = Number(raw.contractAmount) || 0
    const paidAmount = Number(raw.paidAmount) || 0
    const amountMatched = Math.abs(contractAmount - paidAmount) <= AMOUNT_TOLERANCE

    return {
      rowKey: raw.rowKey ?? `contract-${idx}`,
      index: idx + 1,
      contractName: raw.contractName ?? '',
      contractType: raw.contractType ?? '',
      contractAmount, paidAmount, amountMatched,
      startDate: raw.startDate ?? '',
      endDate: raw.endDate ?? '',
      approvalComplete: raw.approvalComplete ?? null,
      authenticity: raw.authenticity ?? null,
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      attachment: raw.attachment ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeAdminRow(raw: any, idx: number): K9AdminCheckRow {
    return {
      rowKey: raw.rowKey ?? `admin-${idx}`,
      index: idx + 1,
      checkItem: raw.checkItem ?? '',
      description: raw.description ?? '',
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      attachment: raw.attachment ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _buildDefaultAdminRows(): K9AdminCheckRow[] {
    return DEFAULT_ADMIN_CHECKS.map((item, idx) => ({
      rowKey: `admin-${idx}`,
      index: idx + 1,
      checkItem: item.checkItem,
      description: item.description,
      compliance: null,
      evidence: '', attachment: '', remark: '',
    }))
  }

  // ─── Computed: 不合规摘要（红色汇总） ──────────────────────────────────────

  const nonComplianceSummary: ComputedRef<K9NonComplianceSummary> = computed(() => {
    const items: K9NonComplianceSummary['items'] = []

    for (const row of contractRows.value) {
      if (row.compliance === '不合规') {
        items.push({ sheetId: 'K9-5', label: row.contractName || `合同${row.index}`, evidence: row.evidence })
      }
    }

    for (const row of adminCheckRows.value) {
      if (row.compliance === '不合规') {
        items.push({ sheetId: 'K9-8', label: row.checkItem, evidence: row.evidence })
      }
    }

    return { count: items.length, items }
  })

  // ─── K9-5 合同检查操作 ─────────────────────────────────────────────────────

  function addContractRow(contractName: string): void {
    if (isReadonly?.value) return
    const idx = contractRows.value.length
    contractRows.value.push({
      rowKey: `contract-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      index: idx + 1,
      contractName, contractType: '',
      contractAmount: 0, paidAmount: 0, amountMatched: true,
      startDate: '', endDate: '',
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

  // ─── K9-8 综合检查操作 ─────────────────────────────────────────────────────

  function updateAdminCheckCompliance(rowKey: string, state: ComplianceState): void {
    if (isReadonly?.value) return
    const row = adminCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.compliance = state
    isChanged.value = true
    _persistAdmin()
  }

  function updateAdminCheckEvidence(rowKey: string, evidence: string): void {
    if (isReadonly?.value) return
    const row = adminCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    row.evidence = evidence
    isChanged.value = true
    _persistAdmin()
  }

  function updateAdminCheckCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = adminCheckRows.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = value
    isChanged.value = true
    _persistAdmin()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistContract(): void {
    if (!onSave) return
    onSave('K9-5-contract-rows', contractRows.value)
  }

  function _persistAdmin(): void {
    if (!onSave) return
    onSave('K9-8-check-rows', adminCheckRows.value)
  }

  function saveContractConclusion(text: string): void {
    contractConclusion.value = text
    onSave?.('K9-5-conclusion', text)
  }

  function saveAdminConclusion(text: string): void {
    adminConclusion.value = text
    onSave?.('K9-8-conclusion', text)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // K9-5 合同检查
    contractRows,
    contractConclusion,
    addContractRow,
    removeContractRow,
    updateContractCell,
    saveContractConclusion,
    // K9-8 综合检查
    adminCheckRows,
    adminConclusion,
    updateAdminCheckCompliance,
    updateAdminCheckEvidence,
    updateAdminCheckCell,
    saveAdminConclusion,
    // 汇总
    nonComplianceSummary,
    isChanged,
    initFromResponses,
  }
}

export default useK9Checks
