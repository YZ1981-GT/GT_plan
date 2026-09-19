/**
 * G10-7 凭证检查 ↔ G10-3 调整 / G10A 程序
 */
import { G10_VOUCHER_CHECK_DEFS } from './g10VoucherConstants'
import { G10_ACCOUNT_CODE } from './g10Constants'
import { inferG10AdjudicationRowKey } from './g10AccountMatch'
import {
  aggregateG10AdjustmentAjeRjeByRow,
} from './g10AdjStorage'
import { commitG10AdjustmentWritebackFromRows } from './g10CrossHelpers'
import { G10_ADJ_KEY, G10_FV_DIFF_THRESHOLD } from './g10FvCrossHelpers'
import { parseNum } from './useG10FormulaEngine'
import type { G10VoucherCheckRow } from './useG10VoucherCheck'
import type { ChecklistResponse } from './useF1FormData'

export type G10VoucherAdjKind = 'fv' | 'interest' | 'cost' | 'generic'

export interface G10VoucherPushItem {
  summary: string
  kind: G10VoucherAdjKind
  /** 负债方向净额：贷方 − 借方；正数表示负债上升 */
  netLiability: number
  amount: number
  indexRef: string
  remark: string
  voucherNo: string
  counterAccount: string
}

/** 识别 G10-7 推送至 G10-3 的调整行 */
export function isFromG107(row: {
  summary?: string
  remark?: string
  indexRef?: string
}): boolean {
  const indexRef = String(row.indexRef || '')
  if (indexRef === 'G10-7' || indexRef.includes('G10-7')) return true
  const summary = String(row.summary || '')
  if (/^G10-7\s*凭证异常/.test(summary)) return true
  if (/来自 G10-7/.test(String(row.remark || ''))) return true
  return false
}

export function describeG10FailedChecks(row: G10VoucherCheckRow): string {
  const failed = G10_VOUCHER_CHECK_DEFS
    .filter((d) => row[d.key as keyof G10VoucherCheckRow] === false)
    .map((d) => d.label)
  return failed.join('、') || '异常'
}

/** 有金额且存在金额相关核对失败的异常行 */
export function isG10QuantitativeVoucherAbnormal(row: G10VoucherCheckRow): boolean {
  if (!row.isAbnormal) return false
  const amt = Math.max(parseNum(row.creditAmount), parseNum(row.debitAmount))
  if (amt <= G10_FV_DIFF_THRESHOLD) return false
  return !row.check4InitialCost || !row.check5Interest || !row.check6FairValueCorrect
}

export function resolveG10VoucherAdjKind(row: G10VoucherCheckRow): G10VoucherAdjKind {
  if (!row.check6FairValueCorrect) return 'fv'
  if (!row.check5Interest) return 'interest'
  if (!row.check4InitialCost) return 'cost'
  return 'generic'
}

function parseCounterAccount(code: string): { code: string; name: string } | null {
  const m = String(code || '').trim().match(/^(\d{4})\s*(.*)$/)
  if (!m) return null
  return { code: m[1], name: m[2]?.trim() || '对方科目' }
}

export function buildG10VoucherPushItems(rows: G10VoucherCheckRow[]): G10VoucherPushItem[] {
  const items: G10VoucherPushItem[] = []
  for (const row of rows) {
    if (!isG10QuantitativeVoucherAbnormal(row)) continue
    const net = parseNum(row.creditAmount) - parseNum(row.debitAmount)
    const amount = Math.abs(net) || Math.max(parseNum(row.creditAmount), parseNum(row.debitAmount))
    if (amount <= G10_FV_DIFF_THRESHOLD) continue
    const voucherNo = row.voucherNo?.trim() || row.id
    const failed = describeG10FailedChecks(row)
    items.push({
      summary: `G10-7 凭证异常：${voucherNo} ${row.businessContent || ''}`.trim(),
      kind: resolveG10VoucherAdjKind(row),
      netLiability: net,
      amount,
      indexRef: 'G10-7',
      remark: [
        `来自 G10-7 凭证检查；未通过：${failed}`,
        row.abnormalDesc ? `说明：${row.abnormalDesc}` : '',
      ].filter(Boolean).join('；'),
      voucherNo,
      counterAccount: row.counterAccount || '',
    })
  }
  return items
}

function buildAdjPair(
  item: G10VoucherPushItem,
  base: Record<string, unknown>,
  seq: number,
  idSuffix: string,
): Record<string, unknown>[] {
  const amt = item.amount
  const liabilityUp = item.netLiability >= 0
  const counter = parseCounterAccount(item.counterAccount)

  if (item.kind === 'fv') {
    const isIncrease = liabilityUp
    return [
      {
        ...base,
        rowId: `g10vc-adj-${idSuffix}a`,
        seq,
        summary: item.summary,
        accountCode: '6101',
        accountName: '公允价值变动损益',
        debitAmount: isIncrease ? amt : 0,
        creditAmount: isIncrease ? 0 : amt,
      },
      {
        ...base,
        rowId: `g10vc-adj-${idSuffix}b`,
        seq: seq + 1,
        summary: `${item.summary}（公允变动）`,
        accountCode: G10_ACCOUNT_CODE,
        accountName: '交易性金融负债',
        debitAmount: isIncrease ? 0 : amt,
        creditAmount: isIncrease ? amt : 0,
      },
    ]
  }

  if (item.kind === 'interest') {
    return [
      {
        ...base,
        rowId: `g10vc-adj-${idSuffix}a`,
        seq,
        summary: item.summary,
        accountCode: '6603',
        accountName: '财务费用',
        debitAmount: amt,
        creditAmount: 0,
      },
      {
        ...base,
        rowId: `g10vc-adj-${idSuffix}b`,
        seq: seq + 1,
        summary: `${item.summary}（利息）`,
        accountCode: G10_ACCOUNT_CODE,
        accountName: '交易性金融负债',
        debitAmount: 0,
        creditAmount: amt,
      },
    ]
  }

  const counterCode = counter?.code || '1002'
  const counterName = counter?.name || '银行存款'
  if (item.kind === 'cost' && liabilityUp) {
    return [
      {
        ...base,
        rowId: `g10vc-adj-${idSuffix}a`,
        seq,
        summary: item.summary,
        accountCode: G10_ACCOUNT_CODE,
        accountName: '交易性金融负债',
        debitAmount: 0,
        creditAmount: amt,
      },
      {
        ...base,
        rowId: `g10vc-adj-${idSuffix}b`,
        seq: seq + 1,
        summary: `${item.summary}（成本）`,
        accountCode: counterCode,
        accountName: counterName,
        debitAmount: amt,
        creditAmount: 0,
      },
    ]
  }

  return [
    {
      ...base,
      rowId: `g10vc-adj-${idSuffix}a`,
      seq,
      summary: item.summary,
      accountCode: '6101',
      accountName: '公允价值变动损益',
      debitAmount: liabilityUp ? amt : 0,
      creditAmount: liabilityUp ? 0 : amt,
    },
    {
      ...base,
      rowId: `g10vc-adj-${idSuffix}b`,
      seq: seq + 1,
      summary: `${item.summary}（待复核）`,
      accountCode: G10_ACCOUNT_CODE,
      accountName: '交易性金融负债',
      debitAmount: liabilityUp ? 0 : amt,
      creditAmount: liabilityUp ? amt : 0,
    },
  ]
}

/** 推送 G10-7 金额类异常至 G10-3，并回写 G10-1 */
export function pushG10VoucherAbnormalToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  rows: G10VoucherCheckRow[],
): { pushed: number; skipped: number } {
  const items = buildG10VoucherPushItems(rows)
  if (!items.length) return { pushed: 0, skipped: 0 }

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G10_ADJ_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const summaries = new Set(
    existing.map((r) => String(r.summary || '').trim()).filter(Boolean),
  )
  const toPush = items.filter((it) => !summaries.has(it.summary.trim()))
  const skipped = items.length - toPush.length
  if (!toPush.length) return { pushed: 0, skipped }

  const added: Record<string, unknown>[] = []
  let seqBase = existing.length
  toPush.forEach((it, i) => {
    const rowKey = inferG10AdjudicationRowKey({ summary: it.summary })
    const base = {
      date: new Date().toISOString().slice(0, 10),
      entryType: 'AJE',
      preparedBy: '',
      indexRef: it.indexRef,
      adjudicationRowKey: rowKey,
      remark: it.remark,
    }
    const pair = buildAdjPair(it, base, seqBase + added.length + 1, `${Date.now().toString(36)}-${i}`)
    added.push(...pair)
    seqBase = existing.length + added.length
  })

  const merged = [...existing, ...added]
  debouncedSave(G10_ADJ_KEY, { remark: JSON.stringify(merged) })

  commitG10AdjustmentWritebackFromRows(responses, debouncedSave, merged as Parameters<typeof aggregateG10AdjustmentAjeRjeByRow>[0], {
    source: 'G10-7',
    offerDisclosurePull: toPush.length > 0,
  })

  return { pushed: toPush.length, skipped }
}
