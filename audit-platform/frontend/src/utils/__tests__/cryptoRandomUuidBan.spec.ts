/**
 * AST 守卫：禁止在生产代码中直接调用 crypto.randomUUID()。
 *
 * 非安全上下文（内网 http + 非 localhost）没有 crypto.randomUUID，裸调会 TypeError。
 * 全仓统一用 utils/uuid.ts 的 newUuid()（已有 getRandomValues → Math.random 两级回退）。
 *
 * spec: lan-http-insecure-context-compat R1.2
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..', '..')

/** 允许出现 crypto.randomUUID 的文件（回退实现本身） */
const ALLOWED = new Set(['utils/uuid.ts', 'utils/clientInstance.ts'])

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

describe('crypto.randomUUID 禁止裸调', () => {
  it('生产代码（非测试）中不出现 crypto.randomUUID，只允许 uuid.ts 和 clientInstance.ts', () => {
    const violations: string[] = []
    for (const file of walk(SRC)) {
      const rel = relative(SRC, file).replace(/\\/g, '/')
      if (ALLOWED.has(rel)) continue
      const text = readFileSync(file, 'utf-8')
      // 跳过纯注释行
      const lines = text.split('\n')
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim()
        if (line.startsWith('//') || line.startsWith('*') || line.startsWith('/**')) continue
        if (line.includes('crypto.randomUUID')) {
          violations.push(`${rel}:${i + 1}: ${line.slice(0, 120)}`)
        }
      }
    }
    expect(violations, `crypto.randomUUID 应统一用 newUuid()（utils/uuid.ts），以下文件违规：\n${violations.join('\n')}`).toEqual([])
  })
})
