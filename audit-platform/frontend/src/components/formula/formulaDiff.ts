/**
 * 公式字符级 diff 工具（基于 LCS 算法，纯前端无外部依赖）。
 * 从 FormulaHistoryTab.vue 提取，供单测覆盖。
 */

export function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** 最长公共子序列（O(n*m)，公式通常短于 200 字符不必优化） */
export function lcs(a: string, b: string): string {
  const m = a.length; const n = b.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] + 1 : Math.max(dp[i - 1][j], dp[i][j - 1])
  let i = m; let j = n; const chars: string[] = []
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) { chars.push(a[i - 1]); i--; j-- }
    else if (dp[i - 1][j] >= dp[i][j - 1]) i--
    else j--
  }
  return chars.reverse().join('')
}

/** 旧公式高亮：被删除的字符加删除线红底 */
export function diffOld(old: string | null, cur: string | null): string {
  if (!old) return ''
  if (!cur || old === cur) return escHtml(old)
  const common = lcs(old, cur)
  let ci = 0; const parts: string[] = []
  for (const ch of old) {
    if (ci < common.length && ch === common[ci]) { parts.push(escHtml(ch)); ci++ }
    else parts.push(`<span class="gt-fh-del">${escHtml(ch)}</span>`)
  }
  return parts.join('')
}

/** 新公式高亮：新增的字符加绿底 */
export function diffNew(old: string | null, cur: string | null): string {
  if (!cur) return ''
  if (!old || old === cur) return escHtml(cur)
  const common = lcs(old, cur)
  let ci = 0; const parts: string[] = []
  for (const ch of cur) {
    if (ci < common.length && ch === common[ci]) { parts.push(escHtml(ch)); ci++ }
    else parts.push(`<span class="gt-fh-add">${escHtml(ch)}</span>`)
  }
  return parts.join('')
}

/** 内联 diff：同一行展示删除（红）和新增（绿） */
export function diffInline(old: string | null, cur: string | null): string {
  if (!old && !cur) return ''
  if (!old) return `<span class="gt-fh-add">${escHtml(cur!)}</span>`
  if (!cur) return `<span class="gt-fh-del">${escHtml(old)}</span>`
  const common = lcs(old, cur)
  let oi = 0; let ci = 0; let li = 0; const parts: string[] = []
  while (oi < old.length || ci < cur.length) {
    let del = ''
    while (oi < old.length && (li >= common.length || old[oi] !== common[li])) { del += old[oi]; oi++ }
    let add = ''
    while (ci < cur.length && (li >= common.length || cur[ci] !== common[li])) { add += cur[ci]; ci++ }
    if (del) parts.push(`<span class="gt-fh-del">${escHtml(del)}</span>`)
    if (add) parts.push(`<span class="gt-fh-add">${escHtml(add)}</span>`)
    if (li < common.length && oi < old.length && ci < cur.length) {
      parts.push(escHtml(common[li]))
      oi++; ci++; li++
    }
  }
  return parts.join('')
}
