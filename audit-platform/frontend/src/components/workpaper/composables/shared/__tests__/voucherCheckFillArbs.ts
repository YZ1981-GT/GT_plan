/**
 * 凭证检查行的 fast-check 生成器（共享回填函数的属性测试用；不是 spec 文件，vitest 不单独跑）
 */
import * as fc from 'fast-check'
import type { AuditPhase } from '@/composables/useProjectAuditPhase'
import type { RowSource, VoucherRowMeta } from '../voucherCheckFill'

export interface FillRow {
  voucherNo: string
  voucherDate: string
  debitAmount: string | null
  creditAmount: string | null
  checkResult: string
  _gt: VoucherRowMeta
}

export const SOURCE_SETS: RowSource[][] = [['engine'], ['attach'], ['manual'], ['engine', 'attach']]

/** 一行凭证检查行，`_gt` 带分录指纹；phase / sources 不给就随机 */
export function fillRowArb(opts: { phase?: AuditPhase | null; sources?: RowSource[][] } = {}): fc.Arbitrary<FillRow> {
  return fc.record({
    lfp: fc.uuid(),
    voucherNo: fc.stringMatching(/^[A-Z]{2}-\d{4}$/),
    voucherDate: fc.constantFrom('2025-01-07', '2025-06-30', '2025-12-31'),
    amount: fc.integer({ min: 1, max: 9_999_999 }),
    credit: fc.boolean(),
    checkResult: fc.constantFrom('', 'Y', 'N', '异常'),
    ph: opts.phase !== undefined
      ? fc.constant(opts.phase)
      : fc.constantFrom<AuditPhase | null>('preliminary', 'final', null),
    src: fc.constantFrom(...(opts.sources ?? SOURCE_SETS)),
  }).map(r => ({
    voucherNo: r.voucherNo,
    voucherDate: r.voucherDate,
    debitAmount: r.credit ? null : `${r.amount}.00`,
    creditAmount: r.credit ? `${r.amount}.00` : null,
    checkResult: r.checkResult,
    _gt: { vk: null, lfp: r.lfp, ph: r.ph, b: null, src: [...r.src], pr: 'paired', cp: null },
  }))
}

/** 分录指纹互不相同的若干行 */
export function fillRowsArb(
  opts: { phase?: AuditPhase | null; sources?: RowSource[][] } = {}, minLength = 0, maxLength = 8,
): fc.Arbitrary<FillRow[]> {
  return fc.uniqueArray(fillRowArb(opts), { minLength, maxLength, selector: r => r._gt.lfp as string })
}

/** 互不重叠（分录指纹不同）的两组行 */
export function disjoint(a: FillRow[], b: FillRow[]): FillRow[] {
  const seen = new Set(a.map(r => r._gt.lfp))
  return b.filter(r => !seen.has(r._gt.lfp))
}

export const lfpsOf = (rows: FillRow[]) => rows.map(r => r._gt.lfp as string)
