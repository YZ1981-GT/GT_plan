/**
 * 凭证检查行的结论判定（spec voucher-workflow-linkage-lineage-closure design §8.2，ADR-VWL-05）。
 *
 * 只认白名单字段、按固定取值表判；不在表内的一律「未判定」。与后端
 * `backend/data/voucher_check_verdict_vocab.json`（`app/services/voucher_row_index.py` 读它）逐值相同，
 * 契约测试 `voucherVerdict.spec.ts` 读那份 JSON 对拍。
 * `conclusion` 不进白名单：它同时是程序表结论（Y / completed / 设计无效），在凭证行上含义不定。
 */
export type VoucherVerdict = 'abnormal' | 'normal' | 'unknown'

type Option = string | boolean

export const VOUCHER_VERDICT_VOCAB: Readonly<Record<string, { abnormal: readonly Option[]; normal: readonly Option[] }>> = {
  isAbnormal: { abnormal: ['是', 'Y', '异常', true], normal: ['否', 'N', false] },
  abnormal: { abnormal: ['是', 'Y', '异常', true], normal: ['否', 'N', false] },
  checkResult: {
    abnormal: ['ERR', '不一致', '异常', '有异常', '×', '不符'],
    normal: ['OK', '一致', '无异常', '正常', '√', '相符'],
  },
  checkConclusion: { abnormal: ['不符', '有异常', '未取得权证'], normal: ['相符', '无异常'] },
  auditConclusion: { abnormal: ['需调整', '差异需调整'], normal: ['无差异', '差异可接受', '无异常'] },
  isConsistent: { abnormal: ['不一致', '否', false], normal: ['一致', '是', true] },
}

function matches(value: unknown, options: readonly Option[]): boolean {
  if (typeof value === 'boolean') return options.some(o => typeof o === 'boolean' && o === value)
  if (typeof value === 'string') {
    const text = value.trim()
    return options.some(o => typeof o === 'string' && o === text)
  }
  return false
}

/** 一行的结论：任一白名单字段为异常即异常；否则任一为正常即正常；否则未判定（与后端 `row_verdict` 相同）。 */
export function rowVerdict(row: unknown): VoucherVerdict {
  if (!row || typeof row !== 'object') return 'unknown'
  const r = row as Record<string, unknown>
  let normal = false
  for (const [field, options] of Object.entries(VOUCHER_VERDICT_VOCAB)) {
    if (!(field in r)) continue
    if (matches(r[field], options.abnormal)) return 'abnormal'
    if (matches(r[field], options.normal)) normal = true
  }
  return normal ? 'normal' : 'unknown'
}

export const VOUCHER_VERDICT_LABEL: Readonly<Record<VoucherVerdict, string>> = {
  abnormal: '异常', normal: '正常', unknown: '未判定',
}
