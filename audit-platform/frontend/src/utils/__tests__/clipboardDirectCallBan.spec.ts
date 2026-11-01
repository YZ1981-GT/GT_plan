/**
 * AST 守卫：禁止在生产代码中直接调用 navigator.clipboard。
 *
 * 非安全上下文（内网 http + 非 localhost）没有 navigator.clipboard，裸调会 TypeError 或静默失败。
 * 全仓统一用 utils/clipboard.ts 的 copyText() / copyRichText() / readText()。
 *
 * spec: lan-http-insecure-context-compat R2.3
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..', '..')

/** 允许出现 navigator.clipboard 的文件（回退实现本身） */
const ALLOWED = new Set(['utils/clipboard.ts'])

/** errorHandler.ts 里 onclick HTML 字符串内的 navigator.clipboard 豁免（无法 import，且该操作本身就是最佳努力） */
const EXEMPTED_FILES = new Set(['utils/errorHandler.ts'])

function walk(dir: string, out: string[] = []): string[] {
  for (const ent of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, ent.name)
    if (ent.isDirectory()) {
      if (ent.name === 'node_modules' || ent.name === '__tests__' || ent.name === '.vite') continue
      walk(full, out)
    } else if (/\.(ts|vue)$/.test(ent.name) && !ent.name.includes('.spec.') && !ent.name.includes('.test.')) {
      out.push(full)
    }
  }
  return out
}

describe('navigator.clipboard 禁止裸调', () => {
  it('生产代码（非测试）中不出现 navigator.clipboard，只允许 clipboard.ts 和豁免文件', () => {
    const violations: string[] = []
    for (const file of walk(SRC)) {
      const rel = relative(SRC, file).replace(/\\/g, '/')
      if (ALLOWED.has(rel) || EXEMPTED_FILES.has(rel)) continue
      const text = readFileSync(file, 'utf-8')
      const lines = text.split('\n')
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim()
        if (line.startsWith('//') || line.startsWith('*') || line.startsWith('/**')) continue
        if (line.includes('navigator.clipboard')) {
          violations.push(`${rel}:${i + 1}: ${line.slice(0, 120)}`)
        }
      }
    }
    expect(violations, `navigator.clipboard 应统一用 clipboard.ts，以下文件违规：\n${violations.join('\n')}`).toEqual([])
  })

  // 反向断言：豁免名单不得变成死条目。
  // 本守卫原先只查「有没有多出裸调」，不查「该有的还在不在」。他会话的批量替换把
  // errorHandler.ts 内联 onclick 串里的 navigator.clipboard.writeText( 换成了
  // await copyText(（内联处理器里既不能 await、也拿不到模块作用域的 copyText ⇒ 运行时必失败），
  // 守卫照绿、缺陷长期不可见。
  it('豁免名单无失效条目：每个豁免文件仍确实裸调 navigator.clipboard', () => {
    const stale: string[] = []
    for (const rel of EXEMPTED_FILES) {
      if (!readFileSync(join(SRC, rel), 'utf-8').includes('navigator.clipboard')) stale.push(rel)
    }
    expect(stale, `以下文件已不再裸调 navigator.clipboard，应从 EXEMPTED_FILES 移除：\n${stale.join('\n')}`).toEqual([])
  })
})
