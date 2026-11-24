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

describe('公式引用标签 D1/D2 语义（跨文件扫描）', () => {
  // 🔴 2026-11-24 勘误：守卫原来只扫 FormulaEditDialog.vue 里 `'wp', 'D1'`
  // 字面行 —— 该引用清单已搬到 WorkpaperWorkbenchView.vue 的 coreWps
  //（code/name 字段），FormulaEditDialog 里不再有这种写法 ⇒ 守卫恒红
  //（expected undefined to be defined，两例）。
  // 修法 = 扫「底稿工作台 + 公式组件」两个文件的 D1/D2 标签行，语义断言不变：
  // 任何出现 D1 标签的地方都必须是「应收票据」、D2 必须是「应收账款」。
  const FILES = [
    resolve(__dirname, '../../views/workpaper-list/WorkpaperWorkbenchView.vue'),
    resolve(__dirname, '../../components/formula/FormulaEditDialog.vue'),
  ]

  function linesWithD1(): { file: string; line: string }[] {
    return FILES.flatMap((f) =>
      readFileSync(f, 'utf-8')
        .split('\n')
        // 🔴 只认 coreWps 形态（`role:` 字段是底稿条目的标志）：
        // 同文件还有 wpLinks 的 `{ code: 'D1', name: '收入循环总控台' }` ——
        // 那是循环总览链接不是底稿标签，name 语义本就不同，混进分母会把
        // 守卫变成文本侦探（实测：首轮把它当 D1 行报「应收票据缺失」）。
        .filter((l) => /code:\s*['"]D1['"]/.test(l) && /role\s*:/.test(l))
        .map((line) => ({ file: f, line })),
    )
  }

  function linesWithD2(): { file: string; line: string }[] {
    return FILES.flatMap((f) =>
      readFileSync(f, 'utf-8')
        .split('\n')
        .filter((l) => /code:\s*['"]D2['"]/.test(l) && /role\s*:/.test(l))
        .map((line) => ({ file: f, line })),
    )
  }

  it('D1 引用标签为"应收票据"而非"营业收入"（分母非空）', () => {
    const hits = linesWithD1()
    // 🔴 分母非空断言：两文件都没有 D1 标签行 = 守卫空转（文件再次搬家/改名要在这里报）
    expect(hits.length).toBeGreaterThan(0)
    for (const { file, line } of hits) {
      expect(`${file}: ${line}`).toContain('应收票据')
      expect(`${file}: ${line}`).not.toContain('营业收入')
    }
  })

  it('D2 引用标签为"应收账款"（分母非空）', () => {
    const hits = linesWithD2()
    expect(hits.length).toBeGreaterThan(0)
    for (const { file, line } of hits) {
      expect(`${file}: ${line}`).toContain('应收账款')
    }
  })
})
