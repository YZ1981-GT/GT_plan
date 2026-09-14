/**
 * G 循环截止样本 → 各 sheet 行映射与 merge 工具
 */
import { parseNum } from './useG12FormulaEngine'
import type { ExtractedVoucher, FillMode } from './useCutoffAutoSampling'
import type { G12VoucherRow } from './useG12VoucherCheck'
import type { G13AdjustmentRow } from './useG13Adjustment'
import type { G14AdjustmentRow } from './useG14Adjustment'
import type { G8AdjustmentEntry } from './useG8Adjustment'
import type { G9AdjustmentEntry } from './useG9Adjustment'
import type { G8VoucherRow } from './useG8VoucherCheck'
import type { G9VoucherRow } from './useG9VoucherCheck'
import type { G11VoucherCheckRow } from './useG11VoucherCheck'
import { createEmptyG13AdjustmentRow } from './useG13Adjustment'
import { createEmptyG14AdjustmentRow } from './useG14Adjustment'

function parseDecimal(v: string | number | null | undefined): number {
  if (v == null || v === '') return 0
  return parseNum(typeof v === 'string' ? parseFloat(v) : v)
}

function genVoucherId(): string {
  return `g12v-cut-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function mapCutoffToG12Voucher(v: ExtractedVoucher, seq: number): G12VoucherRow {
  const forceAbnormal = v.cutoffStatus === '可能跨期'
  return {
    rowId: genVoucherId(),
    seq,
    voucherDate: v.voucherDate ?? '',
    voucherNo: v.voucherNo ?? '',
    businessContent: v.summary ?? '',
    hedgeRelationId: '',
    counterAccount: v.counterpartAccount ?? '',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    attachment: '',
    supportingDocDesc: '',
    check1OriginalComplete: null,
    check2Authorization: null,
    check3Accounting: null,
    check4HedgeDesignation: null,
    check5HedgeAccounting: null,
    check6FVValuation: null,
    indexNo: '',
    isAbnormal: forceAbnormal,
    forceAbnormal,
    abnormalDesc: forceAbnormal ? (v.remark || '截止测试：可能跨期') : '',
    riskLevel: forceAbnormal ? 'high' : 'medium',
    remark: `[截止提取] ${v.remark ?? ''}`.trim(),
    source: '截止',
  }
}

export function mapCutoffToG13Adjustment(v: ExtractedVoucher): G13AdjustmentRow {
  const row = createEmptyG13AdjustmentRow()
  return {
    ...row,
    rowId: `g13a-cut-${Date.now().toString(36)}`,
    date: v.voucherDate ?? '',
    description: v.summary ?? '截止测试样本',
    category: '账项调整',
    entryType: 'AJE',
    accountCode: v.accountCode || '6101',
    accountName: v.accountName || '公允价值变动收益',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    indexRef: v.voucherNo || 'G13-3',
    remark: `[截止:${v.cutoffStatus}] ${v.remark ?? ''}`.trim(),
  }
}

export function mapCutoffToG14Adjustment(v: ExtractedVoucher): G14AdjustmentRow {
  const row = createEmptyG14AdjustmentRow()
  return {
    ...row,
    rowId: `g14a-cut-${Date.now().toString(36)}`,
    description: v.summary ?? '截止测试样本',
    category: '账项调整',
    accountCode: v.accountCode || '6702',
    accountName: v.accountName || '信用减值损失',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    indexRef: v.voucherNo ?? '',
    remark: `[截止:${v.cutoffStatus}] ${v.remark ?? ''}`.trim(),
  }
}

function genG8AdjId(): string {
  return `g8a-cut-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function genG8VoucherId(): string {
  return `g8v-cut-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function genG9AdjId(): string {
  return `g9a-cut-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

function genG9VoucherId(): string {
  return `g9v-cut-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

export function mapCutoffToG8Adjustment(v: ExtractedVoucher, seq: number): G8AdjustmentEntry {
  return {
    rowId: genG8AdjId(),
    seq,
    entryType: 'AJE',
    date: v.voucherDate ?? '',
    summary: v.summary ?? '截止测试样本',
    accountCode: v.accountCode || '1503',
    accountName: v.accountName || '其他权益工具投资',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    preparedBy: '',
    remark: `[截止:${v.cutoffStatus}] ${v.remark ?? ''}`.trim(),
  }
}

export function mapCutoffToG8Voucher(v: ExtractedVoucher, seq: number): G8VoucherRow {
  const crossPeriod = v.cutoffStatus === '可能跨期'
  return {
    rowId: genG8VoucherId(),
    seq,
    voucherDate: v.voucherDate ?? '',
    voucherNo: v.voucherNo ?? '',
    businessContent: v.summary ?? '',
    counterAccount: v.counterpartAccount ?? '',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    attachment: '',
    supportingDocDesc: '',
    // 抽凭/截止回填默认未测，避免未核对却显示全✓
    check1OriginalComplete: null,
    check2Authorization: null,
    check3Accounting: null,
    check4FairValueCorrect: null,
    check5OCICorrect: null,
    indexNo: '',
    isAbnormal: crossPeriod,
    forceAbnormal: crossPeriod,
    abnormalType: crossPeriod ? 'qualitative' : 'none',
    abnormalDesc: crossPeriod ? (v.remark || '截止测试：可能跨期') : '',
    riskLevel: crossPeriod ? 'high' : 'medium',
    remark: `[截止提取] ${v.remark ?? ''}`.trim(),
    source: '截止',
    detailRowId: '',
    investeeName: '',
  }
}

export function mapCutoffToG9Adjustment(v: ExtractedVoucher, seq: number): G9AdjustmentEntry {
  return {
    rowId: genG9AdjId(),
    seq,
    entryType: 'AJE',
    date: v.voucherDate ?? '',
    summary: v.summary ?? '截止测试样本',
    accountCode: v.accountCode || '1504',
    accountName: v.accountName || '其他非流动金融资产',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    preparedBy: '',
    remark: `[截止:${v.cutoffStatus}] ${v.remark ?? ''}`.trim(),
  }
}

export function mapCutoffToG9Voucher(v: ExtractedVoucher, seq: number): G9VoucherRow {
  const crossPeriod = v.cutoffStatus === '可能跨期'
  return {
    rowId: genG9VoucherId(),
    seq,
    voucherDate: v.voucherDate ?? '',
    voucherNo: v.voucherNo ?? '',
    businessContent: v.summary ?? '',
    counterAccount: v.counterpartAccount ?? '',
    debitAmount: parseDecimal(v.debitAmount),
    creditAmount: parseDecimal(v.creditAmount),
    attachmentRef: '',
    supportDoc: '',
    // 截止回填默认未测，避免未核对却显示全✓
    checkOriginal: null,
    checkAuthorized: null,
    checkAccounting: null,
    checkClassification: null,
    checkFairValue: null,
    checkImpairment: null,
    indexRef: '',
    isAbnormal: crossPeriod,
    forceAbnormal: crossPeriod,
    abnormalType: crossPeriod ? 'qualitative' : 'none',
    abnormalDesc: crossPeriod ? (v.remark || '截止测试：可能跨期') : '',
    riskLevel: crossPeriod ? 'high' : 'medium',
    suggestion: '',
    remark: `[截止提取] ${v.remark ?? ''}`.trim(),
    source: '截止',
    detailRowId: '',
    assetName: '',
  }
}

function genG11VoucherId(): string {
  return `g11v-cut-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

/** G11-5 截止样本 → 凭证检查行（贷方为主；默认未测；跨期强制异常） */
export function mapCutoffToG11Voucher(v: ExtractedVoucher, seq: number): G11VoucherCheckRow {
  const crossPeriod = v.cutoffStatus === '可能跨期'
  const credit = parseDecimal(v.creditAmount) || parseDecimal(v.debitAmount)
  return {
    id: genG11VoucherId(),
    seq,
    voucherDate: v.voucherDate ?? '',
    voucherNo: v.voucherNo ?? '',
    businessContent: v.summary ?? '',
    counterAccount: v.counterpartAccount ?? '',
    counterDetail: '',
    creditAmount: credit,
    attachment: null,
    supportingDocDesc: '',
    check1: null,
    check2: null,
    check3: null,
    check4: null,
    check5: null,
    indexNo: '',
    isAbnormal: crossPeriod,
    forceAbnormal: crossPeriod,
    abnormalDesc: crossPeriod ? (v.remark || '截止测试：可能跨期') : '',
    riskLevel: crossPeriod ? 'high' : 'medium',
    remark: `[截止提取] ${v.remark ?? ''}`.trim(),
    source: '截止',
  }
}

export function mergeByFillMode<T>(
  existing: T[],
  incoming: T[],
  fillMode: FillMode,
  getKey: (row: T) => string,
): T[] {
  if (fillMode === 'replace') return incoming
  if (fillMode === 'merge') {
    const keys = new Set(existing.map(getKey).filter(Boolean))
    return [...existing, ...incoming.filter((r) => !keys.has(getKey(r)) || !getKey(r))]
  }
  return [...existing, ...incoming]
}

export type GCycleCutoffCode = 'g8' | 'g9' | 'g11' | 'g12' | 'g13' | 'g14'

export const GCYCLE_CUTOFF_EVENT: Record<GCycleCutoffCode, string> = {
  g8: 'g8:cutoff-filled',
  g9: 'g9:cutoff-filled',
  g11: 'g11:cutoff-filled',
  g12: 'g12:cutoff-filled',
  g13: 'g13:cutoff-filled',
  g14: 'g14:cutoff-filled',
}

export function dispatchGCycleCutoffFilled(
  cycle: GCycleCutoffCode,
  payload: { samples: ExtractedVoucher[]; fillMode: FillMode },
): void {
  window.dispatchEvent(new CustomEvent(GCYCLE_CUTOFF_EVENT[cycle], { detail: payload }))
}

export interface GCycleCutoffFilledDetail {
  samples: ExtractedVoucher[]
  fillMode: FillMode
}
