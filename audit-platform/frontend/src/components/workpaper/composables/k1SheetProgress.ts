/** K1 各 sheet 完成度 — 按实际 storage key 前缀统计 */

export interface K1SheetProgressDef {
  prefixes: string[]
  /** 达到 100% 所需最少字段数 */
  completeAt: number
  /** 视为「进行中」的最少字段数 */
  startedAt?: number
}

export const K1_SHEET_PROGRESS: Record<string, K1SheetProgressDef> = {
  K1A: { prefixes: ['K1A-'], completeAt: 3, startedAt: 1 },
  'K1-1': { prefixes: ['K1-1-'], completeAt: 12, startedAt: 3 },
  'K1-2': { prefixes: ['K1-2-'], completeAt: 8, startedAt: 2 },
  'K1-3': { prefixes: ['K1-3-'], completeAt: 4, startedAt: 1 },
  'K1-4': { prefixes: ['K1-4-'], completeAt: 3, startedAt: 1 },
  'K1-5': { prefixes: ['K1-5-'], completeAt: 5, startedAt: 2 },
  'K1-6': { prefixes: ['K1-6-', 'K1-k2-'], completeAt: 6, startedAt: 2 },
  'K1-7': { prefixes: ['K1-7-'], completeAt: 6, startedAt: 2 },
  'K1-8': { prefixes: ['K1-8-'], completeAt: 6, startedAt: 2 },
  'K1-9': { prefixes: ['K1-9-'], completeAt: 4, startedAt: 1 },
  'K1-10': { prefixes: ['K1-10-'], completeAt: 4, startedAt: 1 },
  'K1-11': { prefixes: ['K1-11-'], completeAt: 4, startedAt: 1 },
  'K1-12': { prefixes: ['K1-12-'], completeAt: 5, startedAt: 2 },
  '附注上市': { prefixes: ['K1-note-listed-', 'K1-disclosure-listed-'], completeAt: 3, startedAt: 1 },
  '附注国企': { prefixes: ['K1-note-soe-', 'K1-disclosure-soe-'], completeAt: 3, startedAt: 1 },
}

export function calcK1SheetProgress(
  allResponses: Map<string, any>,
  code: string,
): number {
  if (code === 'K1') return 100
  const def = K1_SHEET_PROGRESS[code]
  if (!def || !allResponses?.size) return 0

  let count = 0
  for (const key of allResponses.keys()) {
    if (def.prefixes.some((p) => key.startsWith(p))) count++
  }
  const started = def.startedAt ?? 1
  if (count < started) return 0
  if (count >= def.completeAt) return 100
  return Math.min(Math.round((count / def.completeAt) * 100), 99)
}
