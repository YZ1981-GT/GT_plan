/**
 * G7 处置 / 后续计量凭证抽查样本（Task 5.1）。
 *
 * G7-10/G7-11/G7-12 是处置与后续计量的**测算表**（无凭证明细行），故抽凭引擎
 * 回填目标是本模块定义的独立「凭证抽查」行模型（而非把凭证号/借贷映射到测算字段，
 * 避免臆造死接线）。抽凭样本按 `voucherNo` 去重（Property 14）。
 */

import { expandMultiAccountVouchers } from './expandMultiAccountVouchers'

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
  return arr.map((raw: Record<string, unknown>, i: number) => ({
    ...createG7VoucherSampleRow(i + 1),
    ...raw,
    id: String(raw?.id || uid()),
    seq: i + 1,
    debitAmount: num(raw?.debitAmount),
    creditAmount: num(raw?.creditAmount),
  }))
}

/**
 * 纯函数：把抽凭样本映射为凭证抽查行并按 `voucherNo` 去重后追加到既有行（Property 14）。
 *
 * - 已存在的 `voucherNo`（既有行或本批已加）跳过（skipped，按样本计）；
 * - 空 `voucherNo` 的样本无法去重，一律追加（added，不进去重集）；
 * - 多科目凭证按对方分录展开为多行（added 按行计）。🔴 去重必须在**展开前**按样本做：
 *   展开后同一张凭证的多行凭证号相同，若逐行去重会把第 2 行起全部当重复丢掉；
 * - 借方优先取 `debitAmount ?? amount`；有 `creditAmount` 则贷方独立取。
 *
 * @returns 追加后的新行数组 + 统计（不改传入的 existing）。
 */
export function mergeVoucherSamples(
  existing: G7VoucherSampleRow[],
  samples: G7VoucherSample[],
): { rows: G7VoucherSampleRow[]; added: number; skipped: number } {
  const seen = new Set<string>()
  for (const r of existing) {
    const no = String(r.voucherNo || '').trim()
    if (no) seen.add(no)
  }
  const out = [...existing]
  let added = 0
  let skipped = 0
  for (const sample of samples) {
    const no = String(sample.voucherNo || '').trim()
    if (no && seen.has(no)) {
      skipped += 1
      continue
    }
    for (const s of expandMultiAccountVouchers([sample] as any[])) {
      const row = createG7VoucherSampleRow(out.length + 1)
      row.voucherDate = (s as any).voucherDate || ''
      row.voucherNo = no
      row.businessContent = (s as any).summary || ''
      row.counterAccount = (s as any).counterpartAccount ?? (s as any).counterAccount ?? ''
      const debit = num((s as any).debitAmount ?? (s as any).amount)
      const credit = num((s as any).creditAmount)
      if (credit) {
        row.creditAmount = credit
        row.debitAmount = num((s as any).debitAmount)
      } else {
        row.debitAmount = debit
        row.creditAmount = 0
      }
      row.source = '抽凭'
      out.push(row)
      added += 1
    }
    if (no) seen.add(no)
  }
  out.forEach((r, i) => { r.seq = i + 1 })
  return { rows: out, added, skipped }
}
