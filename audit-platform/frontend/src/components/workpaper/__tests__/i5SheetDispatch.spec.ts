/**
 * I5 其他非流动资产 — sheetName 分发逻辑测试
 * 提取 GtI5OtherNoncurrentAssets.vue 的 currentSheet computed 正则逻辑，独立测试
 * Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 7.2
 * Requirements: 1.2, 1.3
 */
import { describe, it, expect } from 'vitest'

/**
 * 从 GtI5OtherNoncurrentAssets.vue 提取的 sheetName → currentSheet 分发逻辑
 * 保持与组件内 computed 一致
 */
function resolveCurrentSheet(sheetName: string): string {
  const name = sheetName || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'I5'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 I5A
  if (/I5A/.test(name)) return 'I5A'
  // I5-N 编码（I5-1 到 I5-4）
  const m = name.match(/(I5-\d+)/)
  if (m) return m[1]
  // 底稿目录 I5（无后缀）
  if (/\bI5\b/.test(name) && !/I5-/.test(name) && !/I5A/.test(name)) return 'I5'
  return ''
}

// ═══════════════════════════════════════════════════════════════════════════════
// sheetName 分发测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('I5 sheetName 分发逻辑 (resolveCurrentSheet)', () => {
  // ─── 底稿目录 (Tab_Index) → I5TabIndex ────────────────────────────────────
  it('"底稿目录" → "I5" (I5TabIndex)', () => {
    expect(resolveCurrentSheet('底稿目录')).toBe('I5')
  })

  it('含 "I5" 无后缀 → "I5" (I5TabIndex)', () => {
    expect(resolveCurrentSheet('其他非流动资产I5')).toBe('I5')
  })

  // ─── I5-1 审定表 → I5TabAdjudication ──────────────────────────────────────
  it('"审定表I5-1" → "I5-1" (I5TabAdjudication)', () => {
    expect(resolveCurrentSheet('审定表I5-1')).toBe('I5-1')
  })

  it('"I5-1 审定汇总" → "I5-1" (I5TabAdjudication)', () => {
    expect(resolveCurrentSheet('I5-1 审定汇总')).toBe('I5-1')
  })

  // ─── I5-2 明细表 → I5TabDetail ────────────────────────────────────────────
  it('"明细表I5-2" → "I5-2" (I5TabDetail)', () => {
    expect(resolveCurrentSheet('明细表I5-2')).toBe('I5-2')
  })

  it('"I5-2 资产明细" → "I5-2" (I5TabDetail)', () => {
    expect(resolveCurrentSheet('I5-2 资产明细')).toBe('I5-2')
  })

  // ─── I5-3 调整分录 → I5TabAdjustment ──────────────────────────────────────
  it('"调整分录I5-3" → "I5-3" (I5TabAdjustment)', () => {
    expect(resolveCurrentSheet('调整分录I5-3')).toBe('I5-3')
  })

  it('"I5-3 调整分录汇总" → "I5-3" (I5TabAdjustment)', () => {
    expect(resolveCurrentSheet('I5-3 调整分录汇总')).toBe('I5-3')
  })

  // ─── I5-4 针对性检查 → I5TabTargetedCheck ─────────────────────────────────
  it('"针对性检查I5-4" → "I5-4" (I5TabTargetedCheck)', () => {
    expect(resolveCurrentSheet('针对性检查I5-4')).toBe('I5-4')
  })

  it('"I5-4 针对性检查表" → "I5-4" (I5TabTargetedCheck)', () => {
    expect(resolveCurrentSheet('I5-4 针对性检查表')).toBe('I5-4')
  })

  // ─── 附注上市 → I5TabDisclosureListed ─────────────────────────────────────
  it('"附注披露信息（上市公司）" → "附注上市" (I5TabDisclosureListed)', () => {
    expect(resolveCurrentSheet('附注披露信息（上市公司）')).toBe('附注上市')
  })

  it('"附注-上市" → "附注上市" (I5TabDisclosureListed)', () => {
    expect(resolveCurrentSheet('附注-上市')).toBe('附注上市')
  })

  // ─── 附注国企 → I5TabDisclosureSoe ────────────────────────────────────────
  it('"附注披露信息（国有企业）" → "附注国企" (I5TabDisclosureSoe)', () => {
    expect(resolveCurrentSheet('附注披露信息（国有企业）')).toBe('附注国企')
  })

  it('"附注-国企" → "附注国企" (I5TabDisclosureSoe)', () => {
    expect(resolveCurrentSheet('附注-国企')).toBe('附注国企')
  })

  // ─── I5A 程序表 → CycleTabProcedure ──────────────────────────────────────
  it('"其他非流动资产实质性程序表I5A" → "I5A"', () => {
    expect(resolveCurrentSheet('其他非流动资产实质性程序表I5A')).toBe('I5A')
  })

  // ─── 未匹配 → 空字符串 (OnlyOffice fallback) ──────────────────────────────
  it('无匹配字符串 → "" (OnlyOffice fallback)', () => {
    expect(resolveCurrentSheet('随机名称')).toBe('')
  })

  it('空字符串 → "" (OnlyOffice fallback)', () => {
    expect(resolveCurrentSheet('')).toBe('')
  })
})
