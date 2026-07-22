/**
 * H10 明细 — 口径守卫：投房/金融工具/长投不应进 6115
 */
export interface H10ExcludedClassHit {
  rowId: string
  assetName: string
  matched: string
  accountHint: string
  wpHint: string
}

const RULES: Array<{ re: RegExp; label: string; accountHint: string; wpHint: string }> = [
  {
    re: /投资性房地产|投房|\bH3\b/,
    label: '投资性房地产',
    accountHint: '其他业务收入/成本',
    wpHint: 'H3',
  },
  {
    re: /长期股权投资|长投|\bG7\b/,
    label: '长期股权投资',
    accountHint: '投资收益',
    wpHint: 'G7',
  },
  {
    re: /交易性金融|其他债权投资|其他权益工具|金融负债|金融工具|\bG1\b|\bG4\b|\bG8\b|\bG9\b|\bG10\b|\bG11\b/,
    label: '金融工具',
    accountHint: '投资收益/公允价值变动',
    wpHint: 'G循环',
  },
]

export function detectH10ExcludedClassText(text: string): {
  matched: string
  accountHint: string
  wpHint: string
} | null {
  const s = String(text ?? '')
  if (!s.trim()) return null
  for (const rule of RULES) {
    if (rule.re.test(s)) {
      return { matched: rule.label, accountHint: rule.accountHint, wpHint: rule.wpHint }
    }
  }
  return null
}

export function scanH10ExcludedClassRows(
  rows: Array<{ id: string; assetName?: string; assetType?: string; sourceWp?: string; remark?: string }>,
): H10ExcludedClassHit[] {
  const hits: H10ExcludedClassHit[] = []
  for (const row of rows) {
    const blob = [row.assetName, row.assetType, row.sourceWp, row.remark].filter(Boolean).join(' ')
    const hit = detectH10ExcludedClassText(blob)
    if (!hit) continue
    hits.push({
      rowId: row.id,
      assetName: row.assetName || row.id,
      matched: hit.matched,
      accountHint: hit.accountHint,
      wpHint: hit.wpHint,
    })
  }
  return hits
}

export function summarizeH10ExcludedHits(hits: H10ExcludedClassHit[]): string | null {
  if (!hits.length) return null
  const parts = hits.map((h) => `${h.assetName || '未命名'}（${h.matched}→应计${h.accountHint}）`)
  return `发现 ${hits.length} 行疑似不应计入 6115：${parts.join('；')}`
}
