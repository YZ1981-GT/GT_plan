/**
 * 序时账没有专列的字段（辅助核算、币种）：取导入时保留的额外列（extra_fields）里表头名匹配的那一列。
 * 序时账页与凭证明细弹窗共用。
 */

export const AUX_KEYS = ['辅助核算', '核算维度', '辅助项', '辅助']
export const CURRENCY_KEYS = ['币种', '币别', '货币']

export interface LedgerExtraRow {
  extra_fields?: Record<string, unknown> | null
}

/** 表头名含 keys 之一的那一列的值（没有这一列返回空串） */
export function pickExtra(r: LedgerExtraRow, keys: string[]): string {
  const extra = r.extra_fields || {}
  for (const k of Object.keys(extra)) {
    if (keys.some(key => k.includes(key))) {
      const v = extra[k]
      return v === null || v === undefined ? '' : String(v)
    }
  }
  return ''
}

/** 取自导入文件里没映射的哪一列（表头名） */
export function pickExtraHeader(r: LedgerExtraRow, keys: string[]): string {
  return Object.keys(r.extra_fields || {}).find(k => keys.some(key => k.includes(key))) ?? ''
}
