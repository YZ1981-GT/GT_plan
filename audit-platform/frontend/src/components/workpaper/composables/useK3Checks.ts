/**
 * useK3Checks — K3-5长期挂账 + K3-6关联方 + K3-7综合检查（含反向截止）
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Task: 3.4
 * Requirements: 5.1-5.4, 6.1-6.5, 7.2
 *
 * 职责：
 * - K3-5 长期挂账检查：3年以上未偿付款项评估（是否转销/转营业外收入）
 * - K3-6 关联方及交易检查：是否公允/是否披露/资金占用
 * - K3-7 综合检查：逐项"合规/不合规/不适用" + 反向截止测试（期后偿付倒查未入账负债）
 * - 不合规红色摘要
 * - 行级抽凭（GtVoucherSamplingEngine）+ 行级OCR
 *
 * 科目：2241 其他应付款（**贷方/负债类**）
 * ⚠️ 完整性认定为主（负债易少计）+ 反向截止
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ComplianceState = '合规' | '不合规' | '不适用' | '需处理'

/** K3-5 长期挂账行 */
export interface K3LongOutstandingRow {
  rowId: string
  seqNo: number
  counterparty: string         // 往来对象
  amount: number               // 挂账金额
  outstandingDate: string      // 挂账时间
  aging: string                // 账龄
  formationReason: string      // 形成原因
  repaymentPlan: string        // 偿付计划
  needTransfer: '是' | '否' | '待评估'  // 是否需转营业外收入
  conclusion: ComplianceState | null
  voucherRef: string           // 抽凭引用
  remark: string
}

/** K3-6 关联方行 */
export interface K3RelatedPartyRow {
  rowId: string
  seqNo: number
  counterparty: string         // 关联方名称
  relationship: string         // 关联关系
  amount: number               // 往来金额
  isFair: '是' | '否' | '待评估'       // 是否公允
  isDisclosed: '是' | '否' | '不适用'  // 是否披露
  capitalOccupation: '是' | '否'       // 资金占用
  conclusion: ComplianceState | null
  remark: string
}

/** K3-7 综合检查项 */
export interface K3CheckItem {
  id: string
  seq: number
  label: string                // 检查项
  description: string          // 检查内容/标准
  compliance: ComplianceState | null
  evidence: string             // 审计证据
  remark: string
}

/** K3-7 反向截止行（期后偿付检查，完整性认定） */
export interface K3CutoffRow {
  rowId: string
  seqNo: number
  counterparty: string         // 付款对象
  paymentDate: string          // 期后偿付日期
  amount: number               // 偿付金额
  invoiceDate: string          // 发票/负债确认日期
  belongsToPrior: '是' | '否' | '待定'  // 是否属期前负债
  isRecorded: '是' | '否'      // 期末是否已入账
  conclusion: string           // 结论
  remark: string
}

export interface K3NonComplianceSummary {
  count: number
  items: Array<{ source: string; label: string; detail: string }>
}

export interface UseK3ChecksParams {
  allResponses: Ref<Map<string, any>>
  saveResponse: Function
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_LONG_OUTSTANDING = 'K3-5-rows'
const ITEM_ID_RELATED_PARTY = 'K3-6-rows'
const ITEM_ID_CHECK_ITEMS = 'K3-7-check-items'
const ITEM_ID_CUTOFF_ROWS = 'K3-7-cutoff-rows'

// ─── Default K3-7 检查项模板 ──────────────────────────────────────────────────

const DEFAULT_CHECK_ITEMS: Omit<K3CheckItem, 'compliance' | 'evidence' | 'remark'>[] = [
  { id: 'K3-7-01', seq: 1, label: '期末余额核对', description: '其他应付款期末余额与明细表/总账/报表一致' },
  { id: 'K3-7-02', seq: 2, label: '大额异常核查', description: '大额其他应付款形成原因合理、有充分支持凭证' },
  { id: 'K3-7-03', seq: 3, label: '长期挂账处理', description: '3年以上挂账项目已评估转销必要性' },
  { id: 'K3-7-04', seq: 4, label: '关联方完整性', description: '关联方其他应付款已充分识别并披露' },
  { id: 'K3-7-05', seq: 5, label: '反向截止测试', description: '期后偿付倒查未入账负债（完整性认定）' },
  { id: 'K3-7-06', seq: 6, label: '分类恰当性', description: '其他应付款科目分类恰当、未混入应付账款等' },
  { id: 'K3-7-07', seq: 7, label: '计价准确性', description: '外币其他应付款汇率换算正确、报告期末已调汇' },
  { id: 'K3-7-08', seq: 8, label: '披露充分性', description: '附注披露完整（按性质/按账龄/大额说明）' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK3Checks(params: UseK3ChecksParams) {
  const { allResponses, saveResponse } = params

  // ─── State ─────────────────────────────────────────────────────────────────

  const longOutstandingRows = ref<K3LongOutstandingRow[]>([])
  const relatedPartyRows = ref<K3RelatedPartyRow[]>([])
  const checkItems = ref<K3CheckItem[]>([])
  const reverseCutoffRows = ref<K3CutoffRow[]>([])

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadJSON<T>(itemId: string, normalizer: (raw: any, i: number) => T): T[] {
    const item = allResponses.value.get(itemId)
    const raw = item?.remark ?? item?.conclusion ?? null
    if (!raw) return []
    try {
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? parsed.map(normalizer) : []
    } catch {
      return []
    }
  }

  function initFromResponses(): void {
    // K3-5 长期挂账
    longOutstandingRows.value = _loadJSON(ITEM_ID_LONG_OUTSTANDING, _normalizeLongOutstanding)

    // K3-6 关联方
    relatedPartyRows.value = _loadJSON(ITEM_ID_RELATED_PARTY, _normalizeRelatedParty)

    // K3-7 检查项
    const loadedChecks = _loadJSON(ITEM_ID_CHECK_ITEMS, _normalizeCheckItem)
    checkItems.value = loadedChecks.length > 0 ? loadedChecks : DEFAULT_CHECK_ITEMS.map((t): K3CheckItem => ({
      ...t, compliance: null, evidence: '', remark: '',
    }))

    // K3-7 反向截止
    reverseCutoffRows.value = _loadJSON(ITEM_ID_CUTOFF_ROWS, _normalizeCutoffRow)
  }

  // ─── Normalizers ───────────────────────────────────────────────────────────

  function _normalizeLongOutstanding(raw: any, idx: number): K3LongOutstandingRow {
    return {
      rowId: raw.rowId ?? `lo-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? idx + 1,
      counterparty: raw.counterparty ?? '',
      amount: Number(raw.amount) || 0,
      outstandingDate: raw.outstandingDate ?? '',
      aging: raw.aging ?? '',
      formationReason: raw.formationReason ?? '',
      repaymentPlan: raw.repaymentPlan ?? '',
      needTransfer: raw.needTransfer ?? '待评估',
      conclusion: raw.conclusion ?? null,
      voucherRef: raw.voucherRef ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeRelatedParty(raw: any, idx: number): K3RelatedPartyRow {
    return {
      rowId: raw.rowId ?? `rp-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? idx + 1,
      counterparty: raw.counterparty ?? '',
      relationship: raw.relationship ?? '',
      amount: Number(raw.amount) || 0,
      isFair: raw.isFair ?? '待评估',
      isDisclosed: raw.isDisclosed ?? '不适用',
      capitalOccupation: raw.capitalOccupation ?? '否',
      conclusion: raw.conclusion ?? null,
      remark: raw.remark ?? '',
    }
  }

  function _normalizeCheckItem(raw: any, idx: number): K3CheckItem {
    return {
      id: raw.id ?? `K3-7-${String(idx + 1).padStart(2, '0')}`,
      seq: raw.seq ?? idx + 1,
      label: raw.label ?? '',
      description: raw.description ?? '',
      compliance: raw.compliance ?? null,
      evidence: raw.evidence ?? '',
      remark: raw.remark ?? '',
    }
  }

  function _normalizeCutoffRow(raw: any, idx: number): K3CutoffRow {
    return {
      rowId: raw.rowId ?? `ct-${Math.random().toString(36).slice(2, 10)}`,
      seqNo: raw.seqNo ?? idx + 1,
      counterparty: raw.counterparty ?? '',
      paymentDate: raw.paymentDate ?? '',
      amount: Number(raw.amount) || 0,
      invoiceDate: raw.invoiceDate ?? '',
      belongsToPrior: raw.belongsToPrior ?? '待定',
      isRecorded: raw.isRecorded ?? '否',
      conclusion: raw.conclusion ?? '',
      remark: raw.remark ?? '',
    }
  }

  // ─── 不合规摘要 (Req 6.5) ──────────────────────────────────────────────────

  const nonComplianceSummary: ComputedRef<K3NonComplianceSummary> = computed(() => {
    const items: K3NonComplianceSummary['items'] = []

    // K3-5 长期挂账不合规
    for (const row of longOutstandingRows.value) {
      if (row.conclusion === '不合规' || row.conclusion === '需处理') {
        items.push({ source: 'K3-5 长期挂账', label: row.counterparty, detail: `挂账${row.aging}，金额${row.amount}` })
      }
    }

    // K3-6 关联方不合规
    for (const row of relatedPartyRows.value) {
      if (row.conclusion === '不合规') {
        items.push({ source: 'K3-6 关联方', label: row.counterparty, detail: `金额${row.amount}，关系${row.relationship}` })
      }
    }

    // K3-7 检查项不合规
    for (const item of checkItems.value) {
      if (item.compliance === '不合规') {
        items.push({ source: 'K3-7 综合检查', label: item.label, detail: item.evidence })
      }
    }

    return { count: items.length, items }
  })

  // ─── 操作方法 ──────────────────────────────────────────────────────────────

  /** 更新K3-5行结论 */
  function updateLongOutstandingConclusion(rowId: string, conclusion: ComplianceState): void {
    const row = longOutstandingRows.value.find(r => r.rowId === rowId)
    if (row) row.conclusion = conclusion
  }

  /** 更新K3-6行结论 */
  function updateRelatedPartyConclusion(rowId: string, conclusion: ComplianceState): void {
    const row = relatedPartyRows.value.find(r => r.rowId === rowId)
    if (row) row.conclusion = conclusion
  }

  /** 更新K3-7检查项合规状态 */
  function updateCheckCompliance(itemId: string, compliance: ComplianceState): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) item.compliance = compliance
  }

  /** 更新K3-7检查项证据 */
  function updateCheckEvidence(itemId: string, evidence: string): void {
    const item = checkItems.value.find(i => i.id === itemId)
    if (item) item.evidence = evidence
  }

  /** 新增反向截止行 */
  function addCutoffRow(): void {
    reverseCutoffRows.value.push({
      rowId: `ct-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: reverseCutoffRows.value.length + 1,
      counterparty: '',
      paymentDate: '',
      amount: 0,
      invoiceDate: '',
      belongsToPrior: '待定',
      isRecorded: '否',
      conclusion: '',
      remark: '',
    })
  }

  /** 移除反向截止行 */
  function removeCutoffRow(rowId: string): void {
    reverseCutoffRows.value = reverseCutoffRows.value.filter(r => r.rowId !== rowId)
    reverseCutoffRows.value.forEach((r, i) => { r.seqNo = i + 1 })
  }

  // ─── 不合规项计数 ─────────────────────────────────────────────────────────

  /** 获取全部"不合规"项数（跨K3-5/K3-6/K3-7） */
  function getIncompliantCount(): number {
    return nonComplianceSummary.value.count
  }

  // ─── 序列化保存 ────────────────────────────────────────────────────────────

  function saveAll(): void {
    saveResponse(ITEM_ID_LONG_OUTSTANDING, { remark: JSON.stringify(longOutstandingRows.value) })
    saveResponse(ITEM_ID_RELATED_PARTY, { remark: JSON.stringify(relatedPartyRows.value) })
    saveResponse(ITEM_ID_CHECK_ITEMS, { remark: JSON.stringify(checkItems.value) })
    saveResponse(ITEM_ID_CUTOFF_ROWS, { remark: JSON.stringify(reverseCutoffRows.value) })
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    longOutstandingRows,
    relatedPartyRows,
    checkItems,
    reverseCutoffRows,
    nonComplianceSummary,
    initFromResponses,
    getIncompliantCount,
    updateLongOutstandingConclusion,
    updateRelatedPartyConclusion,
    updateCheckCompliance,
    updateCheckEvidence,
    addCutoffRow,
    removeCutoffRow,
    saveAll,
  }
}
