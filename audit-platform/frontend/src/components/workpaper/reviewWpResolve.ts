/**
 * A21~A25 程序表 chip 子码解析 — 与 GtAProgramConsole 逻辑一致
 */
export function isReviewRoleRef(ref: string): boolean {
  return /^A2[1-5](-\d)?$/i.test((ref || '').trim())
}

export function resolveReviewWpCode(
  ref: string,
  templates: Record<string, { applicable: boolean; mandatory: boolean }>,
): string {
  const r = (ref || '').trim().toUpperCase()
  if (/^A2[1-5]-\d$/.test(r)) {
    const info = templates[r]
    if (info?.applicable !== false) return r
  }
  const parent = r.match(/^(A2[1-5])/)?.[1]
  if (!parent) return r
  const candidates = Object.keys(templates)
    .filter(k => k.startsWith(`${parent}-`))
    .sort()
  for (const c of candidates) {
    if (templates[c]?.applicable) return c
  }
  return candidates[0] || r
}
