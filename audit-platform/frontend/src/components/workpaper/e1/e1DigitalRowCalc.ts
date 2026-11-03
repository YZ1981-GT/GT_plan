/**
 * E1-4 数字货币明细表 —— 行计算（纯函数，组件与对拍守卫共用）。
 *
 * 公式按权威模板「数字货币明细表E1-4」逐列：
 *   H 期末余额(原币) = E + F − G；I 期末余额(本位币) = H × D；
 *   K 期末审定数(原币) = H + J；L 期末审定数(人民币) = K × D；
 *   N 期末账面余额与银行查询余额的差异 = M − K
 */
import { calcCashBalance, calcFxConvert, parseNum } from '../composables/useE1FormulaEngine'

export interface E1DigitalRow {
  id: string
  /** 序号（按位置编号） */
  seq: number
  bankName: string
  currency: string
  fxRate: number
  opening: number
  increase: number
  decrease: number
  /** 公式：opening + increase − decrease */
  endingFc: number
  /** 公式：endingFc × fxRate */
  endingRmb: number
  /** 账项调整(原币) */
  adjustment: number
  /** 公式：endingFc + adjustment */
  auditedFc: number
  /** 公式：auditedFc × fxRate */
  auditedRmb: number
  /** 期末银行查询余额 */
  queryBalance: number
  /** 公式：queryBalance − auditedFc */
  diff: number
  /** 差异非零时必填 */
  diffReason: string
  /** 银行余额索引号 */
  indexNo: string
  /** 银行询证函索引号 */
  confirmationIndexNo: string
  note: string
}

export function newE1DigitalRowId(): string {
  return `digi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function recalcE1DigitalRow(row: E1DigitalRow): E1DigitalRow {
  const endingFc = calcCashBalance(row.opening, row.increase, row.decrease)
  const endingRmb = calcFxConvert(endingFc, row.fxRate)
  const auditedFc = endingFc + row.adjustment
  const auditedRmb = calcFxConvert(auditedFc, row.fxRate)
  const diff = row.queryBalance - auditedFc
  return { ...row, endingFc, endingRmb, auditedFc, auditedRmb, diff }
}

export function createEmptyE1DigitalRow(seq: number): E1DigitalRow {
  return recalcE1DigitalRow({
    id: newE1DigitalRowId(), seq, bankName: '', currency: '人民币', fxRate: 1,
    opening: 0, increase: 0, decrease: 0, endingFc: 0, endingRmb: 0,
    adjustment: 0, auditedFc: 0, auditedRmb: 0, queryBalance: 0, diff: 0,
    diffReason: '', indexNo: '', confirmationIndexNo: '', note: '',
  })
}

/**
 * 存库行 → 算好公式列的一行（载入与对拍守卫共用）。
 * 汇率缺省（旧数据没存）按 1；录入的 0 照用 —— 原先 `parseNum(fxRate) || 1` 把 0 改成 1，
 * 在线编辑里汇率填 0 时两侧本位币金额不同（spec oo-writeback-template-parity-closure R3）。
 */
export function normalizeE1DigitalRow(r: Record<string, unknown>, index: number): E1DigitalRow {
  const rawRate = r.fxRate
  return recalcE1DigitalRow({
    id: String(r.id || newE1DigitalRowId()), seq: index + 1, bankName: String(r.bankName || ''),
    currency: String(r.currency || ''),
    fxRate: rawRate === undefined || rawRate === null || rawRate === '' ? 1 : parseNum(rawRate),
    opening: parseNum(r.opening), increase: parseNum(r.increase), decrease: parseNum(r.decrease),
    endingFc: 0, endingRmb: 0, adjustment: parseNum(r.adjustment),
    auditedFc: 0, auditedRmb: 0, queryBalance: parseNum(r.queryBalance), diff: 0,
    diffReason: String(r.diffReason || ''), indexNo: String(r.indexNo || ''),
    confirmationIndexNo: String(r.confirmationIndexNo || ''), note: String(r.note || ''),
  })
}
