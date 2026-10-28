/**
 * G7-18 长期股权投资凭证检查表的行：空行、旧字段迁移、异常判定，以及抽凭 / 挂凭回填
 * （spec voucher-identity-writeback-and-audit-phase 任务 11）
 *
 * 宿主 G7TabVoucherCheck 原来内联这些函数；回填改走共享回填函数 `useVoucherCheckFill`：一个对方科目一行
 * （后端配对），按分录指纹去重，行元数据 `_gt` 随行 JSON 落库，年审阶段预审行只读。原实现按凭证分录展开
 * 多科目凭证（行金额取对方分录的金额）、不去重，已删除。
 */
import { toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import { parseNum } from './useG7SubFormulaEngine'
import { counterpartText, useVoucherCheckFill, withRowMeta, type PreparedItem } from './shared/voucherCheckFill'

export type G7CheckRow = Record<string, any>

export function createG7CheckRow(seq: number): G7CheckRow {
  return {
    id: `g18-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    seq,
    voucherDate: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    attachment: '',
    supportingDoc: '',
    check1Original: false,
    check2Authorization: false,
    check3Accounting: false,
    check4Amount: false,
    check5Classification: false,
    check6InvestmentIncome: false,
    indexRef: '',
    isAbnormal: false,
    abnormalNote: '',
    riskLevel: '',
    remark: '',
  }
}

/** 有凭证号或金额、且六项核对没有全部通过 = 异常 */
export function isG7CheckRowAbnormal(row: G7CheckRow): boolean {
  if (!row.voucherNo && !parseNum(row.debitAmount) && !parseNum(row.creditAmount)) return false
  return !(
    row.check1Original
    && row.check2Authorization
    && row.check3Accounting
    && row.check4Amount
    && row.check5Classification
    && row.check6InvestmentIncome
  )
}

/** 兼容旧前端字段名 → 后端 IE 字段；行元数据 `_gt` 透传 */
export function normalizeG7CheckRow(raw: G7CheckRow, index: number): G7CheckRow {
  const row: G7CheckRow = {
    ...createG7CheckRow(index + 1),
    ...raw,
    id: raw.id || `g18-${Date.now()}-${index}`,
    seq: index + 1,
  }
  if (raw.check1OriginalComplete != null && raw.check1Original == null) {
    row.check1Original = !!raw.check1OriginalComplete
  }
  if (raw.check4AmountCorrect != null && raw.check4Amount == null) {
    row.check4Amount = !!raw.check4AmountCorrect
  }
  if (raw.supportingDocDesc != null && !raw.supportingDoc) {
    row.supportingDoc = raw.supportingDocDesc
  }
  if (raw.abnormalDesc != null && !raw.abnormalNote) {
    row.abnormalNote = raw.abnormalDesc
  }
  if (raw.indexNo != null && !raw.indexRef) {
    row.indexRef = raw.indexNo
  }
  row.debitAmount = parseNum(row.debitAmount)
  row.creditAmount = parseNum(row.creditAmount)
  row.isAbnormal = isG7CheckRowAbnormal(row)
  return withRowMeta(row, raw)
}

export function parseG7CheckRows(raw: unknown): G7CheckRow[] {
  const source = Array.isArray(raw)
    ? raw
    : (raw && typeof raw === 'object' && Array.isArray((raw as any).rows) ? (raw as any).rows : [])
  return source.map((r: any, i: number) => normalizeG7CheckRow(r || {}, i))
}

/** 共享回填函数的待写入项 → 检查行：金额在样本自己的借贷栏，对方科目取后端配对（编码 + 名称，配不上写「多科目」） */
export function mapPreparedToG7CheckRow(item: PreparedItem, seq: number): G7CheckRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null }
  const row = createG7CheckRow(seq)
  row.voucherDate = s.voucherDate || ''
  row.voucherNo = s.voucherNo || ''
  row.businessContent = s.summary || ''
  row.counterAccount = counterpartText(item)
  row.debitAmount = parseNum(item.debitAmount)
  row.creditAmount = parseNum(item.creditAmount)
  row.source = item.meta.src.includes('attach') ? '挂凭' : '抽凭'
  row.isAbnormal = isG7CheckRowAbnormal(row)
  return row
}

/** 行上已勾核对项或已填附件、支持性文件、索引、异常说明 / 风险、备注（替换与撤销抽凭时据此先确认） */
export function hasG7CheckRowContent(r: G7CheckRow): boolean {
  return [r.check1Original, r.check2Authorization, r.check3Accounting, r.check4Amount, r.check5Classification,
    r.check6InvestmentIncome].some(Boolean)
    || [r.attachment, r.supportingDoc, r.indexRef, r.abnormalNote, r.riskLevel, r.remark].some(v => String(v ?? '').trim() !== '')
}

/** 宿主接入共享回填函数：回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读；保存用 rowsToPersist */
export function useG7VoucherCheckFill(opts: {
  projectId: MaybeRefOrGetter<string | null | undefined>
  rows: Ref<G7CheckRow[]>
  /** 回填 / 撤销改完行之后保存（宿主的 persistRows） */
  persist: () => unknown
  readonly?: MaybeRefOrGetter<boolean>
}) {
  const voucherFill = useVoucherCheckFill<G7CheckRow>({
    projectId: opts.projectId,
    tables: opts.rows,
    mapSampleToRow: item => mapPreparedToG7CheckRow(item, opts.rows.value.length + 1),
    persist: opts.persist,
    hasUserContent: hasG7CheckRowContent,
    afterChange: (_key, list) => { list.forEach((r, i) => { r.seq = i + 1 }) },
    readonly: opts.readonly,
  })
  return {
    ...voucherFill,
    /** 保存用的行：年审阶段预审行按读入版本写回 */
    rowsToPersist: () => voucherFill.guardPersist(opts.rows.value),
    /** 删行（年审阶段预审行只读不可删）；删后重排序号并保存 */
    removeRow: (id: string): void => {
      const idx = opts.rows.value.findIndex(r => r.id === id)
      if (idx < 0 || toValue(opts.readonly) || voucherFill.isRowLocked(opts.rows.value[idx])) return
      opts.rows.value.splice(idx, 1)
      opts.rows.value.forEach((r, i) => { r.seq = i + 1 })
      void opts.persist()
    },
  }
}
