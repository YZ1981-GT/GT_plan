/**
 * 税务底稿「有 / 无」标记与「隐藏标记为无」开关的存取（移植自 CITAR workpaper-marks.ts）。
 *
 * 本期存 localStorage，按项目分键：某张底稿有没有是具体项目的审核事实。
 * 读写收在这一个模块里，以后改存后端只动这里。
 */

/** 三态：不在映射里 = 空白（尚未判断），与「无」在审核上不是一回事 */
export type TaxWorkpaperMark = 'present' | 'absent'

export type TaxWorkpaperMarkMap = Record<string, TaxWorkpaperMark>

const MARKS_PREFIX = 'gt.tax-workpaper-marks.'
const HIDE_PREFIX = 'gt.tax-workpaper-hide-absent.'

/** 读某项目的全部标记；存储被写坏时当作空，不让页面崩掉 */
export function loadMarks(projectId: string): TaxWorkpaperMarkMap {
  try {
    const raw = localStorage.getItem(MARKS_PREFIX + projectId)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null) return {}
    const result: TaxWorkpaperMarkMap = {}
    for (const [code, mark] of Object.entries(parsed as Record<string, unknown>)) {
      if (mark === 'present' || mark === 'absent') result[code] = mark
    }
    return result
  } catch {
    return {}
  }
}

/** 整组写回 */
export function saveMarks(projectId: string, marks: TaxWorkpaperMarkMap): void {
  try {
    localStorage.setItem(MARKS_PREFIX + projectId, JSON.stringify(marks))
  } catch {
    // 存储满或被禁用：标记丢失不阻断审核工作
  }
}

export function loadHideAbsent(projectId: string): boolean {
  try {
    return localStorage.getItem(HIDE_PREFIX + projectId) === '1'
  } catch {
    return false
  }
}

export function saveHideAbsent(projectId: string, hide: boolean): void {
  try {
    localStorage.setItem(HIDE_PREFIX + projectId, hide ? '1' : '0')
  } catch {
    // 同上
  }
}

/** 单击循环：空白 → 有 → 无 → 空白 */
export function nextMark(current: TaxWorkpaperMark | undefined): TaxWorkpaperMark | undefined {
  if (current === undefined) return 'present'
  if (current === 'present') return 'absent'
  return undefined
}
