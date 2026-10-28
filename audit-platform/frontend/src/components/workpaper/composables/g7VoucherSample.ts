/**
 * G7 处置 / 后续计量凭证抽查样本（Task 5.1）。
 *
 * G7-10/G7-11/G7-12 是处置与后续计量的**测算表**（无凭证明细行），故抽凭引擎
 * 回填目标是本模块定义的独立「凭证抽查」行模型（而非把凭证号/借贷映射到测算字段，
 * 避免臆造死接线）。抽凭回填 / 撤销走共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 11）：
 * 一个对方科目一行（后端配对），按分录指纹去重，行元数据 `_gt` 随行 JSON 落库；原来按 `voucherNo` 去重
 * （Property 14，同号不同分录被当重复丢掉）、经 expandMultiAccountVouchers 展开，已删除。
 */

import { ref, toValue, type MaybeRefOrGetter } from 'vue'
import {
  counterpartText, useVoucherCheckFill, withRowMeta,
  type PreparedItem, type SamplePairing,
} from './shared/voucherCheckFill'

export interface G7VoucherSampleRow {
  id: string
  seq: number
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  conclusion: string
  remark: string
  source: string
}

/** 抽凭引擎 @filled 的样本形状（与 GtVoucherSamplingEngine 一致） */
export interface G7VoucherSample {
  summary?: string
  amount?: number
  debitAmount?: number
  creditAmount?: number
  voucherDate?: string
  voucherNo?: string
  counterAccount?: string
  counterpartAccount?: string
  counterpartAccountName?: string
  voucherEntries?: Array<{ account_code: string; account_name: string; debit_amount: string | null; credit_amount: string | null; summary: string }>
  /** 后端多借多贷配对结果（voucher-identity-writeback-and-audit-phase 需求 3）：展开按它 */
  pairing?: SamplePairing | null
}

function num(v: unknown): number {
  if (v == null || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function uid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `g7vs-${crypto.randomUUID()}`
  }
  return `g7vs-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function createG7VoucherSampleRow(seq: number): G7VoucherSampleRow {
  return {
    id: uid(),
    seq,
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    conclusion: '',
    remark: '',
    source: '',
  }
}

/** 解析持久化的行（容错：非数组返回空） */
export function parseG7VoucherSampleRows(payload: unknown): G7VoucherSampleRow[] {
  const arr = Array.isArray(payload)
    ? payload
    : Array.isArray((payload as any)?.rows)
      ? (payload as any).rows
      : []
  return arr.map((raw: Record<string, unknown>, i: number) => withRowMeta({
    ...createG7VoucherSampleRow(i + 1),
    ...raw,
    id: String(raw?.id || uid()),
    seq: i + 1,
    debitAmount: num(raw?.debitAmount),
    creditAmount: num(raw?.creditAmount),
  }, raw))
}

/** 共享回填函数的待写入项 → 凭证抽查行：金额在样本自己的借贷栏，对方科目取后端配对（编码 + 名称，配不上写「多科目」） */
export function mapPreparedToG7VoucherSampleRow(item: PreparedItem, seq: number): G7VoucherSampleRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null }
  const row = createG7VoucherSampleRow(seq)
  row.voucherDate = s.voucherDate || ''
  row.voucherNo = s.voucherNo || ''
  row.businessContent = s.summary || ''
  row.counterAccount = counterpartText(item)
  row.debitAmount = num(item.debitAmount)
  row.creditAmount = num(item.creditAmount)
  row.source = item.meta.src.includes('attach') ? '挂凭' : '抽凭'
  return row
}

/** 行上已填检查结论或备注（替换与撤销抽凭时据此先确认） */
export function hasG7VoucherSampleContent(r: G7VoucherSampleRow): boolean {
  return [r.conclusion, r.remark].some(v => String(v ?? '').trim() !== '')
}

/**
 * 凭证抽查区块的行与回填（G7VoucherSampleSection 用）：读入、增删、保存，抽凭回填 / 挂凭导入 / 撤销走共享回填函数
 * （一个对方科目一行，按分录指纹去重；年审阶段预审行只读，保存时按读入版本写回）。
 */
export function useG7VoucherSampleRows(opts: {
  projectId: MaybeRefOrGetter<string | null | undefined>
  readonly?: MaybeRefOrGetter<boolean>
  /** 保存行 JSON（宿主写进 checklist_responses） */
  save: (json: string) => void
}) {
  const rows = ref<G7VoucherSampleRow[]>([])
  const voucherFill = useVoucherCheckFill<G7VoucherSampleRow>({
    projectId: opts.projectId,
    tables: rows,
    mapSampleToRow: item => mapPreparedToG7VoucherSampleRow(item, rows.value.length + 1),
    persist: () => persist(),
    hasUserContent: hasG7VoucherSampleContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    readonly: opts.readonly,
  })
  function load(payload: unknown): void {
    rows.value = parseG7VoucherSampleRows(payload)
    voucherFill.markLoaded()
  }
  function persist(): void {
    if (toValue(opts.readonly)) return
    opts.save(JSON.stringify(voucherFill.guardPersist(rows.value)))
  }
  function addRow(): void {
    if (toValue(opts.readonly)) return
    rows.value.push(createG7VoucherSampleRow(rows.value.length + 1))
    persist()
  }
  function removeRow(index: number): void {
    const row = rows.value[index]
    if (toValue(opts.readonly) || !row || voucherFill.isRowLocked(row)) return
    rows.value.splice(index, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    persist()
  }
  return {
    rows,
    load,
    persist,
    addRow,
    removeRow,
    onEngineFilled: voucherFill.onEngineFilled,
    onAttachImported: voucherFill.onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}
