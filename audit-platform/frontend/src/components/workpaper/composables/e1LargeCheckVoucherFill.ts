/**
 * E1-23 货币资金收支检查：抽凭 / 挂凭回填的行映射（spec voucher-identity-writeback-and-audit-phase 任务 10）
 *
 * 宿主 E1TabLargeCheck 经 useE1IpoSpecial 的 voucherFill 接入共享回填函数（policy=expand：一个对方科目一行，
 * 金额是该对方科目对应的那部分；配不上的整张凭证一行「多科目」）。原实现按凭证号去重、按对方分录展开并
 * 把金额取成对方分录金额，已删除。
 */
import { createEmptyRow, type IpoRow } from './useE1IpoSpecial'
import { parseNum } from './useE1FormulaEngine'
import { legacyIdentity, type PreparedItem } from './shared/voucherCheckFill'

/** 抽凭引擎标异常时预填的异常说明（不算审计师已录入的内容） */
export const ENGINE_ABNORMAL_ISSUE = '抽凭引擎标记异常，待核查'

/** 科目编码 → 所属科目名称（1001 现金 / 1002 银行存款 / 1012 其他货币资金） */
export function moneyAccountName(code: string): string {
  const c = String(code || '')
  if (c.startsWith('1001')) return '现金'
  if (c.startsWith('1002')) return '银行存款'
  if (c.startsWith('1012')) return '其他货币资金'
  return c
}

/** 待写入项 → 收支检查行：借方 = 收（现金流入）、贷方 = 支（现金流出） */
export function mapSampleToLargeCheckRow(item: PreparedItem): IpoRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null; accountCode?: string; abnormal?: boolean }
  const debit = parseNum(item.debitAmount)
  const credit = parseNum(item.creditAmount)
  const row = createEmptyRow('E1-23')
  row.direction = debit > 0 ? '收' : credit > 0 ? '支' : ''
  row.accountName = moneyAccountName(String(s.accountCode ?? ''))
  row.date = String(s.voucherDate ?? '')
  row.voucherNo = String(s.voucherNo ?? '')
  row.content = String(s.summary ?? '')
  row.counterAccount = item.counterpartAccount
  row.counterSubAccount = item.counterpartAccountName === item.counterpartAccount ? '' : item.counterpartAccountName
  row.amount = debit || credit
  if (s.abnormal) {
    row.isAbnormal = true
    row.issue = ENGINE_ABNORMAL_ISSUE
  }
  return row
}

/** 行上是否已录入银行回单 / 支持性文件 / 索引 / 异常说明（替换 / 撤销前先确认） */
export function hasLargeCheckContent(r: IpoRow): boolean {
  return [r.bankReceiptDate, r.bankReceiptParty, r.otherDoc, r.indexNo].some(v => String(v ?? '').trim() !== '')
    || parseNum(r.bankReceiptAmount as number) !== 0
    || (String(r.issue ?? '').trim() !== '' && r.issue !== ENGINE_ABNORMAL_ISSUE)
}

/** 旧行（没有 `_gt`）的身份：凭证编号 + 日期 + 金额 */
export function largeCheckLegacyKey(r: IpoRow): string | null {
  return legacyIdentity({ voucherNo: r.voucherNo, voucherDate: r.date, amount: r.amount })
}
