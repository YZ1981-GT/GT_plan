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
})
