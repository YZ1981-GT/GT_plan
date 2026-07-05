/**
 * useG1VoucherCheck - G1-13 检查表（48行凭证核对 + 抽凭引擎集成）
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 5.6
 *
 * Responsibilities:
 * - 48行凭证核对检查表数据结构（17列）
 * - 抽凭引擎样本填入接口预留（applySamplingResults / mergeSamples）
 * - 已抽凭行显示来源tooltip（sampleSource 字段）
 * - 动态行增删 + loadAll/persistAll
 *
 * Requirements: 12.7~12.9
 */
import { ref, computed, watch, type Ref } from 'vue'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'

// --- Types ---

/** G1-13 检查表行（凭证核对，17列） */
export interface G1VoucherCheckRow {
  id: string
  seq: number
  voucherDate: string // 凭证日期
  voucherNo: string // 凭证号
  summary: string // 摘要
  securityName: string // 证券名称
  investType: string // 投资类型
  amount: number // 金额
  counterAccount: string // 对方科目
  contractCheck: string // 合同核对
  settlementCheck: string // 结算单核对
  quoteCheck: string // 报价/估值核对
  approvalCheck: string // 授权审批核对
  bookkeepingCheck: string // 账务处理核对
  auditConclusion: string // 审计结论
  attachment: string // 附件（OCR用）
  remark: string // 备注
  sampleSource: string // 抽凭来源（tooltip）
}

export interface G1VoucherCheckColumn {
  prop: keyof G1VoucherCheckRow
  label: string
  width: number
  type: 'text' | 'number'
}

export const G1_VOUCHER_CHECK_COLUMNS: G1VoucherCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'voucherDate', label: '凭证日期', width: 120, type: 'text' },
  { prop: 'voucherNo', label: '凭证号', width: 110, type: 'text' },
  { prop: 'summary', label: '摘要', width: 160, type: 'text' },
  { prop: 'securityName', label: '证券名称', width: 150, type: 'text' },
  { prop: 'investType', label: '投资类型', width: 110, type: 'text' },
  { prop: 'amount', label: '金额', width: 120, type: 'number' },
  { prop: 'counterAccount', label: '对方科目', width: 130, type: 'text' },
  { prop: 'contractCheck', label: '合同核对', width: 110, type: 'text' },
  { prop: 'settlementCheck', label: '结算单核对', width: 120, type: 'text' },
  { prop: 'quoteCheck', label: '报价/估值核对', width: 130, type: 'text' },
  { prop: 'approvalCheck', label: '授权审批核对', width: 130, type: 'text' },
  { prop: 'bookkeepingCheck', label: '账务处理核对', width: 130, type: 'text' },
  { prop: 'auditConclusion', label: '审计结论', width: 140, type: 'text' },
  { prop: 'remark', label: '备注', width: 140, type: 'text' },
]

const DATA_KEY = 'G1-13-rows'
const CONCLUSION_KEY = 'G1-13-conclusion'

// --- Helpers ---

function generateRowId(): string {
  return `g1v-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): G1VoucherCheckRow {
  return {
    id: generateRowId(),
    seq,
    voucherDate: '',
    voucherNo: '',
    summary: '',
    securityName: '',
    investType: '',
    amount: 0,
    counterAccount: '',
    contractCheck: '',
    settlementCheck: '',
    quoteCheck: '',
    approvalCheck: '',
    bookkeepingCheck: '',
    auditConclusion: '',
    attachment: '',
    remark: '',
    sampleSource: '',
  }
}

function loadRows(map: Map<string, ChecklistResponse>): G1VoucherCheckRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow(1)]
  try {
    const parsed = JSON.parse(raw) as Partial<G1VoucherCheckRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyRow(1)]
    return parsed.map((p, i) => ({ ...emptyRow(p.seq ?? i + 1), ...p, id: p.id ?? generateRowId() }))
  } catch {
    return [emptyRow(1)]
  }
}

// --- Composable ---

export function useG1VoucherCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<G1VoucherCheckRow[]>(loadRows(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  const total = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.amount))))
  const abnormalCount = computed(
    () => rows.value.filter((r) => r.auditConclusion && r.auditConclusion !== '无异常').length,
  )
  const sampledCount = computed(() => rows.value.filter((r) => !!r.sampleSource).length)

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateRow(id: string, patch: Partial<G1VoucherCheckRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    const seq = rows.value.length + 1
    rows.value = [...rows.value, emptyRow(seq)]
    persistAll()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id).map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  // --- 抽凭引擎集成接口 ---

  /** 将抽凭引擎样本映射为检查表行 */
  function mapVoucherToRow(v: SampledVoucher, seq: number): G1VoucherCheckRow {
    const debit = v.debitAmount ? parseNum(v.debitAmount) : 0
    const credit = v.creditAmount ? parseNum(v.creditAmount) : 0
    return {
      ...emptyRow(seq),
      voucherDate: v.voucherDate || '',
      voucherNo: v.voucherNo || '',
      summary: v.summary || '',
      amount: Math.max(debit, credit),
      counterAccount: v.counterpartAccount || '',
      sampleSource: '抽凭引擎',
    }
  }

  /** 样本填入（append 追加） */
  function mergeSamples(vouchers: SampledVoucher[]) {
    if (opts.isReadonly.value) return
    const mapped = vouchers.map((v, i) => mapVoucherToRow(v, rows.value.length + i + 1))
    rows.value = [...rows.value, ...mapped].map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  /** GtVoucherSamplingEngine @filled 处理（支持 append/replace/merge） */
  function applySamplingResults(vouchers: SampledVoucher[], fillMode: FillMode) {
    if (opts.isReadonly.value) return
    if (fillMode === 'replace') {
      rows.value = vouchers.length
        ? vouchers.map((v, i) => mapVoucherToRow(v, i + 1))
        : [emptyRow(1)]
      persistAll()
      return
    }
    if (fillMode === 'merge') {
      const existingNos = new Set(rows.value.map((r) => r.voucherNo).filter(Boolean))
      const deduped = vouchers.filter((v) => !v.voucherNo || !existingNos.has(v.voucherNo))
      mergeSamples(deduped)
      return
    }
    mergeSamples(vouchers)
  }

  return {
    columns: G1_VOUCHER_CHECK_COLUMNS,
    rows,
    auditConclusion,
    total,
    abnormalCount,
    sampledCount,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    mergeSamples,
    applySamplingResults,
    mapVoucherToRow,
  }
}

export default useG1VoucherCheck
