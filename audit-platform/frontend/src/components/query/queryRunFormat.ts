/**
 * 分量与范围的显示格式（AQF §8.1 queryRunFormat）。
 * 依据说明、北京时间、千分位、过期原因排版；表名用分量自带的 label。
 */

/** 北京时间偏移（+8）*/
const TZ_OFFSET_MS = 8 * 60 * 60 * 1000

/** 服务端 UTC ISO 字符串 → 北京时间显示 */
export function fmtBeijingTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const bj = new Date(d.getTime() + TZ_OFFSET_MS)
    return bj.toISOString().replace('T', ' ').slice(0, 19) + ' (北京时间)'
  } catch {
    return iso
  }
}

/** 数字加千分位 */
export function fmtRows(n: number | null | undefined): string {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN')
}

/** 依据类型的中文说明 */
export function basisLabel(basis: string): string {
  const map: Record<string, string> = {
    dataset: '账套数据集',
    content: '内容摘要',
    row_version: '行版本',
    timestamp: '更新时间（弱判据）',
    scope: '查询范围',
  }
  return map[basis] ?? basis
}

/** 单个分量的摘要显示（8 字符前缀）*/
export function shortDigest(digest: string | null | undefined): string {
  return digest ? digest.slice(0, 8) : '—'
}

/** 版本摘要前 16 字符 */
export function shortVectorHash(hash: string | null | undefined): string {
  return hash ? hash.slice(0, 16) : '—'
}

/** 时效状态文本 */
export function freshnessLabel(status: string, weak?: boolean): string {
  const base: Record<string, string> = {
    current: '未变化',
    stale: '已过期',
    unknown: '无法判定',
  }
  let text = base[status] ?? status
  if (weak && status === 'current') text += '（弱判据）'
  return text
}

/** current 状态的说明文字（R3.4）*/
export function currentMessage(weak: boolean): string {
  let msg = '自查询开始以来未检测到来源变化'
  if (weak) msg += '；部分来源仅按更新时间判断，未写更新时间的改动可能检测不到'
  return msg
}

/** 过期原因摘要（取第一条）*/
export function staleReason(changes: ReadonlyArray<{ reason?: string }>): string {
  return changes?.[0]?.reason ?? '来源数据已变化'
}
