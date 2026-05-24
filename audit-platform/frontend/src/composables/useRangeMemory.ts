/**
 * useRangeMemory — 选区记忆持久化 composable
 *
 * 按 (userId, wpCode, sheetName) 维度记录最后选区表达式，
 * LRU 淘汰策略保证单用户最多 50 条记忆。
 *
 * Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5
 * Feature: advanced-query-enhancements-p1p2
 */

export const MAX_ENTRIES = 50

export const STORAGE_KEY = (userId: string) => `gt:cqd:range-memory:${userId}`

export interface RangeMemoryEntry {
  rangeExpr: string
  ts: number
}

export type RangeMemoryStore = Record<string, RangeMemoryEntry>

/**
 * 保存选区记忆。LRU 淘汰超过 MAX_ENTRIES 的最旧条目。
 */
export function saveRangeMemory(
  userId: string,
  wpCode: string,
  sheetName: string,
  rangeExpr: string
): void {
  const storageKey = STORAGE_KEY(userId)
  const key = `${wpCode}:${sheetName}`
  const store: RangeMemoryStore = JSON.parse(
    localStorage.getItem(storageKey) || '{}'
  )
  store[key] = { rangeExpr, ts: Date.now() }
  // LRU 淘汰：按时间戳降序排列，只保留前 MAX_ENTRIES 条
  const entries = Object.entries(store).sort(
    (a, b) => b[1].ts - a[1].ts
  )
  const pruned = Object.fromEntries(entries.slice(0, MAX_ENTRIES))
  localStorage.setItem(storageKey, JSON.stringify(pruned))
}

/**
 * 加载选区记忆。返回 null 表示无记忆。
 */
export function loadRangeMemory(
  userId: string,
  wpCode: string,
  sheetName: string
): string | null {
  const storageKey = STORAGE_KEY(userId)
  const store: RangeMemoryStore = JSON.parse(
    localStorage.getItem(storageKey) || '{}'
  )
  const key = `${wpCode}:${sheetName}`
  return store[key]?.rangeExpr ?? null
}

/**
 * 清除指定 (wpCode, sheetName) 的记忆条目。
 */
export function clearRangeMemory(
  userId: string,
  wpCode: string,
  sheetName: string
): void {
  const storageKey = STORAGE_KEY(userId)
  const store: RangeMemoryStore = JSON.parse(
    localStorage.getItem(storageKey) || '{}'
  )
  const key = `${wpCode}:${sheetName}`
  delete store[key]
  localStorage.setItem(storageKey, JSON.stringify(store))
}

/**
 * 清除用户所有选区记忆。
 */
export function clearAllRangeMemory(userId: string): void {
  localStorage.removeItem(STORAGE_KEY(userId))
}

/**
 * 解析 cell range 表达式为行列边界。
 * 支持 A1:B10 / A1:B10,C1:C5 多区域语法。
 * 返回 { minRow, maxRow, minCol, maxCol } 表示整体边界。
 */
export function parseRangeBounds(rangeExpr: string): {
  minRow: number
  maxRow: number
  minCol: number
  maxCol: number
} | null {
  const cellPattern = /([A-Z]{1,3})(\d{1,7})/g
  const matches = [...rangeExpr.matchAll(cellPattern)]
  if (matches.length === 0) return null

  let minRow = Infinity
  let maxRow = -Infinity
  let minCol = Infinity
  let maxCol = -Infinity

  for (const m of matches) {
    const col = colLetterToNumber(m[1])
    const row = parseInt(m[2], 10)
    if (row < minRow) minRow = row
    if (row > maxRow) maxRow = row
    if (col < minCol) minCol = col
    if (col > maxCol) maxCol = col
  }

  return { minRow, maxRow, minCol, maxCol }
}

/**
 * 将列字母转为数字（A=1, B=2, ..., Z=26, AA=27）
 */
export function colLetterToNumber(letters: string): number {
  let result = 0
  for (let i = 0; i < letters.length; i++) {
    result = result * 26 + (letters.charCodeAt(i) - 64)
  }
  return result
}

/**
 * 将列数字转为字母（1=A, 2=B, ..., 26=Z, 27=AA）
 */
export function colNumberToLetter(num: number): string {
  let result = ''
  while (num > 0) {
    const remainder = (num - 1) % 26
    result = String.fromCharCode(65 + remainder) + result
    num = Math.floor((num - 1) / 26)
  }
  return result
}

/**
 * 越界 clamp：将选区表达式 clamp 到 [1, sheetMaxRow] × [1, sheetMaxCol]。
 * 返回 { clampedExpr, wasClamped }。
 */
export function clampRange(
  rangeExpr: string,
  sheetMaxRow: number,
  sheetMaxCol: number
): { clampedExpr: string; wasClamped: boolean } {
  let wasClamped = false

  const clampedExpr = rangeExpr.replace(
    /([A-Z]{1,3})(\d{1,7})/g,
    (_match, colStr: string, rowStr: string) => {
      let col = colLetterToNumber(colStr)
      let row = parseInt(rowStr, 10)

      if (row > sheetMaxRow) {
        row = sheetMaxRow
        wasClamped = true
      }
      if (row < 1) {
        row = 1
        wasClamped = true
      }
      if (col > sheetMaxCol) {
        col = sheetMaxCol
        wasClamped = true
      }
      if (col < 1) {
        col = 1
        wasClamped = true
      }

      return `${colNumberToLetter(col)}${row}`
    }
  )

  return { clampedExpr, wasClamped }
}

/**
 * Vue composable 封装，提供响应式 API。
 */
export function useRangeMemory(userId: string) {
  return {
    save: (wpCode: string, sheetName: string, rangeExpr: string) =>
      saveRangeMemory(userId, wpCode, sheetName, rangeExpr),
    load: (wpCode: string, sheetName: string) =>
      loadRangeMemory(userId, wpCode, sheetName),
    clear: (wpCode: string, sheetName: string) =>
      clearRangeMemory(userId, wpCode, sheetName),
    clearAll: () => clearAllRangeMemory(userId),
    clampRange,
  }
}
