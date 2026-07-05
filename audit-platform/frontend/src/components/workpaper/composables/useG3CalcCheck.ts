/**
 * useG3CalcCheck — G3-4 测算及检查表（18列 → 2区段Tab）
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 5.2
 *
 * 职责：
 * - 18列拆为2区段（股利测算9列 / 凭证检查9列），区段间行同步
 * - 公式链：
 *     应收股利(测算) = 持股数量 × 每股股利           (calcDividend)
 *     测算差异       = 应收股利(测算) - 企业入账金额  (calculatedDividend - bookedAmount)
 * - |测算差异| > 100 橙色高亮
 * - 抽凭引擎集成：fillFromSamples(samples) 填入凭证检查区段
 * - 已抽凭行 samplingSource tooltip "来源: 抽凭引擎"
 * - 动态行增删（ElMessageBox.prompt 输入被投资方名称）
 * - 底部合计（calculatedDividend / bookedAmount / calcVariance / amount）
 * - 存储到 allResponses 'G3-4-calccheck-rows' key
 * - auditConclusion textarea + AI 按钮支持
 *
 * Requirements: 7.1~7.10
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcDividend,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** G3-4 测算及检查行（18列分2区段） */
export interface CalcCheckRow {
  id: string
  seq: number
  // 股利测算区段(9列)
  investeeName: string
  sharesHeld: number
  dps: number
  calculatedDividend: number      // 公式 = 持股 × 每股股利
  declarationDate: string
  recordDate: string
  dividendDocNo: string
  bookedAmount: number            // 企业入账金额
  calcVariance: number            // 测算差异 = calculatedDividend - bookedAmount
  // 凭证检查区段(9列)
  voucherDate: string
  voucherNo: string
  summary: string
  counterAccount: string
  amount: number
  receivingBank: string
  receiptDate: string
  reconciliationResult: string
  auditConclusion: string
  // 来源标记
  samplingSource?: string         // 抽凭引擎来源tooltip
}

export interface CalcCheckColumn {
  prop: keyof CalcCheckRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date'
}

export interface CalcCheckSegment {
  key: string
  label: string
  columns: CalcCheckColumn[]
}

// ─── Column Constants ────────────────────────────────────────────────────────

/** 股利测算区段(9列) */
export const SEGMENT_CALC: CalcCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, formula: true },
  { prop: 'investeeName', label: '被投资方', width: 160, type: 'text' },
  { prop: 'sharesHeld', label: '持股数量', width: 120, type: 'number' },
  { prop: 'dps', label: '每股股利', width: 110, type: 'number' },
  { prop: 'calculatedDividend', label: '应收股利(测算)', width: 140, type: 'number', formula: true },
  { prop: 'declarationDate', label: '宣告日', width: 120, type: 'date' },
  { prop: 'recordDate', label: '权利日', width: 120, type: 'date' },
  { prop: 'dividendDocNo', label: '分红文件编号', width: 140, type: 'text' },
  { prop: 'calcVariance', label: '测算差异', width: 120, type: 'number', formula: true },
]

/** 凭证检查区段(9列) */
export const SEGMENT_VOUCHER: CalcCheckColumn[] = [
  { prop: 'voucherDate', label: '凭证日期', width: 120, type: 'date' },
  { prop: 'voucherNo', label: '凭证编号', width: 120, type: 'text' },
  { prop: 'summary', label: '摘要', width: 160, type: 'text' },
  { prop: 'counterAccount', label: '对方科目', width: 120, type: 'text' },
  { prop: 'amount', label: '金额', width: 120, type: 'number' },
  { prop: 'receivingBank', label: '收款银行', width: 130, type: 'text' },
  { prop: 'receiptDate', label: '到账日期', width: 120, type: 'date' },
  { prop: 'reconciliationResult', label: '核对结果', width: 120, type: 'text' },
  { prop: 'auditConclusion', label: '审计结论', width: 140, type: 'text' },
]

/** 2区段Tab配置 */
export const G3_CALCCHECK_SEGMENTS: CalcCheckSegment[] = [
  { key: 'calc', label: '股利测算', columns: SEGMENT_CALC },
  { key: 'voucher', label: '凭证检查', columns: SEGMENT_VOUCHER },
]

// ─── Storage Key ─────────────────────────────────────────────────────────────

const DATA_KEY = 'G3-4-calccheck-rows'

// ─── Subtotal Fields ─────────────────────────────────────────────────────────

const SUM_FIELDS = [
  'calculatedDividend',
  'bookedAmount',
  'calcVariance',
  'amount',
] as const

export type CalcCheckTotals = Record<(typeof SUM_FIELDS)[number], number>

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `cc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRow(id: string, seq: number): CalcCheckRow {
  return {
    id,
    seq,
    // 股利测算区段
    investeeName: '',
    sharesHeld: 0,
    dps: 0,
    calculatedDividend: 0,
    declarationDate: '',
    recordDate: '',
    dividendDocNo: '',
    bookedAmount: 0,
    calcVariance: 0,
    // 凭证检查区段
    voucherDate: '',
    voucherNo: '',
    summary: '',
    counterAccount: '',
    amount: 0,
    receivingBank: '',
    receiptDate: '',
    reconciliationResult: '',
    auditConclusion: '',
    // 来源标记
    samplingSource: undefined,
  }
}

/** 公式链求解 — 区段间行同步核心 */
function enrich(r: CalcCheckRow): CalcCheckRow {
  const sharesHeld = parseNum(r.sharesHeld)
  const dps = parseNum(r.dps)
  const bookedAmount = parseNum(r.bookedAmount)

  // 应收股利(测算) = 持股数量 × 每股股利
  const calculatedDividend = calcDividend(sharesHeld, dps)

  // 测算差异 = 应收股利(测算) - 企业入账金额
  const calcVariance = calculatedDividend - bookedAmount

  return {
    ...r,
    calculatedDividend,
    calcVariance,
  }
}

function loadRows(map: Map<string, ChecklistResponse>): CalcCheckRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [enrich(emptyRow(generateId(), 1))]
  try {
    const parsed = JSON.parse(raw) as Partial<CalcCheckRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) {
      return [enrich(emptyRow(generateId(), 1))]
    }
    return parsed.map((p, i) =>
      enrich({ ...emptyRow(p.id ?? generateId(), p.seq ?? i + 1), ...p }),
    )
  } catch {
    return [enrich(emptyRow(generateId(), 1))]
  }
}

function sumRows(list: CalcCheckRow[]): CalcCheckTotals {
  const out = {} as CalcCheckTotals
  for (const f of SUM_FIELDS) {
    out[f] = calcSubtotal(list.map((r) => parseNum(r[f] as number)))
  }
  return out
}

/** 判断行差异是否超过阈值（|差异| > 100 → 橙色高亮） */
export function isVarianceExceeding(row: CalcCheckRow, threshold = 100): boolean {
  return Math.abs(row.calcVariance) > threshold
}

/** 判断行是否来自抽凭引擎 */
export function isSamplingRow(row: CalcCheckRow): boolean {
  return !!row.samplingSource
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3CalcCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const rows = ref<CalcCheckRow[]>(loadRows(opts.allResponses.value))
  /** 当前区段 */
  const segment = ref<string>(G3_CALCCHECK_SEGMENTS[0].key)

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
  }

  // allResponses 异步加载完成后回填
  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) rows.value = loadRows(opts.allResponses.value)
    },
  )

  /** 总计行 */
  const totals = computed<CalcCheckTotals>(() => sumRows(rows.value))

  function persistAll() {
    if (!opts.isReadonly.value) {
      opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
    }
  }

  function updateRow(id: string, patch: Partial<CalcCheckRow>) {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrich({ ...r, ...patch }) : r))
    persistAll()
  }

  async function addRow() {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增测算行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '被投资方名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [
        ...rows.value,
        enrich({ ...emptyRow(generateId(), seq), investeeName: value }),
      ]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || rows.value.length <= 1) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  /**
   * 抽凭引擎集成 — 将样本批量填入凭证检查区段
   * 样本通过 GtVoucherSamplingEngine (科目1131) 返回后调用此方法
   * 自动填充 voucherDate/voucherNo/summary/counterAccount/amount 等字段
   * 并标记 samplingSource = '抽凭引擎'
   */
  function fillFromSamples(samples: Partial<CalcCheckRow>[]) {
    if (opts.isReadonly.value || !samples.length) return

    // 优先填入已有行中凭证区段为空的行，否则追加新行
    const updated = [...rows.value]
    let nextSeq = updated.length + 1

    for (const sample of samples) {
      // 查找凭证区段为空的行（可填入）
      const emptySlot = updated.find(
        (r) => !r.voucherNo && !r.voucherDate && !r.samplingSource,
      )

      if (emptySlot) {
        // 填入已有行的凭证检查区段
        const idx = updated.indexOf(emptySlot)
        updated[idx] = enrich({
          ...emptySlot,
          voucherDate: sample.voucherDate ?? '',
          voucherNo: sample.voucherNo ?? '',
          summary: sample.summary ?? '',
          counterAccount: sample.counterAccount ?? '',
          amount: parseNum(sample.amount),
          receivingBank: sample.receivingBank ?? '',
          receiptDate: sample.receiptDate ?? '',
          reconciliationResult: sample.reconciliationResult ?? '',
          samplingSource: '抽凭引擎',
        })
      } else {
        // 追加新行
        const newRow = enrich({
          ...emptyRow(generateId(), nextSeq),
          investeeName: sample.investeeName ?? '',
          voucherDate: sample.voucherDate ?? '',
          voucherNo: sample.voucherNo ?? '',
          summary: sample.summary ?? '',
          counterAccount: sample.counterAccount ?? '',
          amount: parseNum(sample.amount),
          receivingBank: sample.receivingBank ?? '',
          receiptDate: sample.receiptDate ?? '',
          reconciliationResult: sample.reconciliationResult ?? '',
          samplingSource: '抽凭引擎',
        })
        updated.push(newRow)
        nextSeq++
      }
    }

    rows.value = updated
    persistAll()
  }

  return {
    segments: G3_CALCCHECK_SEGMENTS,
    segment,
    rows,
    totals,
    loadAll,
    persistAll,
    updateRow,
    addRow,
    removeRow,
    fillFromSamples,
    isVarianceExceeding,
    isSamplingRow,
  }
}

export default useG3CalcCheck
