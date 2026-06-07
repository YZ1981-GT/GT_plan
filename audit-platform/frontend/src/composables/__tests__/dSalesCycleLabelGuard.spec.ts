/**
 * dSalesCycleLabelGuard.spec.ts — D 销售循环底稿标签防错配测试
 *
 * Spec: workpaper-account-package-d1-d2-pilot Task 8.3
 *
 * 防止 D1/D2/D4 标签再次被错误映射：
 * - D1 = 应收票据（不是营业收入）
 * - D2 = 应收账款
 * - D4 = 营业收入/收入审定（不是应收票据）
 *
 * Validates: Requirements 5.5
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// ─── 工作台 coreWps 标签测试 ──────────────────────────────────────────────

describe('WorkpaperWorkbenchView D 循环 coreWps 标签', () => {
  const filePath = resolve(
    __dirname,
    '../../views/workpaper-list/WorkpaperWorkbenchView.vue'
  )
  const content = readFileSync(filePath, 'utf-8')

  it('D1 对应"应收票据"而非"营业收入"', () => {
    // D1 coreWps entry should reference 应收票据
    const d1Match = content.match(/code:\s*'D1'[^}]*name:\s*'([^']+)'/)
    expect(d1Match).not.toBeNull()
    expect(d1Match![1]).toContain('应收票据')
    expect(d1Match![1]).not.toContain('营业收入')
  })

  it('D2 对应"应收账款"', () => {
    const d2Match = content.match(/code:\s*'D2'[^}]*name:\s*'([^']+)'/)
    expect(d2Match).not.toBeNull()
    expect(d2Match![1]).toContain('应收账款')
  })

  it('D4 对应"营业收入"或"收入审定"', () => {
    const d4Match = content.match(/code:\s*'D4'[^}]*name:\s*'([^']+)'/)
    expect(d4Match).not.toBeNull()
    const d4Name = d4Match![1]
    expect(
      d4Name.includes('营业收入') || d4Name.includes('收入审定')
    ).toBe(true)
  })

  it('D1 不包含"营业收入"关键词', () => {
    // 更严格：在 D1 code 后直到下一个 code 之间不应出现 "营业收入"
    const d1Section = content.match(
      /code:\s*'D1'[^]*?(?=code:\s*'D[2-9]'|$)/
    )
    if (d1Section) {
      // 在 D1 块内的 name 和 detail 不应有 "营业收入"
      const nameInD1 = d1Section[0].match(/name:\s*'([^']+)'/)
      if (nameInD1) {
        expect(nameInD1[1]).not.toContain('营业收入')
      }
    }
  })
})

// ─── 公式编辑器 D1 标签测试 ─────────────────────────────────────────────────

describe('FormulaEditDialog D1 标签', () => {
  const filePath = resolve(
    __dirname,
    '../../components/formula/FormulaEditDialog.vue'
  )
  const content = readFileSync(filePath, 'utf-8')

  it('D1 引用标签为"应收票据"而非"营业收入"', () => {
    // Find the D1 reference row
    const d1Line = content
      .split('\n')
      .find((l) => l.includes("'wp', 'D1'") || l.includes('"wp", "D1"'))
    expect(d1Line).toBeDefined()
    expect(d1Line!).toContain('应收票据')
    expect(d1Line!).not.toContain('营业收入')
  })

  it('D2 引用标签为"应收账款"', () => {
    const d2Line = content
      .split('\n')
      .find((l) => l.includes("'wp', 'D2'") || l.includes('"wp", "D2"'))
    expect(d2Line).toBeDefined()
    expect(d2Line!).toContain('应收账款')
  })
})
