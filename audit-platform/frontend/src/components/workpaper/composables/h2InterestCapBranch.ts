/**
 * H2 利息资本化分支解析（纯函数）
 * H2-10（无专门借款）与 H2-11（有专门借款）互斥。
 */
export type InterestCapBranch = 'noBorrow' | 'withBorrow'

export const H2_INTEREST_BRANCH_KEY = 'H2-interest-cap-branch'
export const H2_10_CAP_RESULT_KEY = 'H2-10-cap-result'
export const H2_11_CAP_RESULT_KEY = 'H2-11-cap-result'

export interface InterestCapResultLike {
  totalCap?: number
  branch?: InterestCapBranch
  byProject?: Record<string, number>
  capRate?: number
}

function _parseRemark(raw: unknown): InterestCapResultLike | null {
  if (raw == null) return null
  if (typeof raw === 'object' && !Array.isArray(raw)) return raw as InterestCapResultLike
  if (typeof raw !== 'string' || !raw.trim()) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

function _getRemark(map: Map<string, any>, key: string): unknown {
  return map.get(key)?.remark
}

/** 读取已选分支；无显式选择时根据 cap-result 推断 */
export function resolveInterestCapBranch(responses: Map<string, any>): InterestCapBranch | null {
  const stored = String(_getRemark(responses, H2_INTEREST_BRANCH_KEY) || '').trim()
  if (stored === 'withBorrow' || stored === 'noBorrow') return stored

  const r10 = _parseRemark(_getRemark(responses, H2_10_CAP_RESULT_KEY))
  const r11 = _parseRemark(_getRemark(responses, H2_11_CAP_RESULT_KEY))

  if (r10?.branch === 'noBorrow' && r11?.branch !== 'withBorrow') return 'noBorrow'
  if (r11?.branch === 'withBorrow' && r10?.branch !== 'noBorrow') return 'withBorrow'
  if (r10 && !r11) return 'noBorrow'
  if (r11 && !r10) return 'withBorrow'
  return null
}

/** 按互斥分支取活跃资本化结果（避免 H2-10 非零结果抢占 H2-11） */
export function resolveActiveInterestCapResult(
  responses: Map<string, any>,
): InterestCapResultLike | null {
  const branch = resolveInterestCapBranch(responses)
  const r10 = _parseRemark(_getRemark(responses, H2_10_CAP_RESULT_KEY))
  const r11 = _parseRemark(_getRemark(responses, H2_11_CAP_RESULT_KEY))

  if (branch === 'withBorrow') return r11
  if (branch === 'noBorrow') return r10

  if (r10?.branch === 'noBorrow') return r10
  if (r11?.branch === 'withBorrow') return r11
  if (r10 && Number(r10.totalCap) !== 0) return r10
  return r11 ?? r10
}

/** 切换分支时需清空的非活跃结果 key */
export function inactiveInterestCapResultKey(active: InterestCapBranch): string {
  return active === 'noBorrow' ? H2_11_CAP_RESULT_KEY : H2_10_CAP_RESULT_KEY
}

export function activeInterestCapResultKey(active: InterestCapBranch): string {
  return active === 'noBorrow' ? H2_10_CAP_RESULT_KEY : H2_11_CAP_RESULT_KEY
}
