/**
 * 结构化错误只显示中文说明，原因码不进正文（spec procedure-chain-hardening-and-java-contracts R10）。
 * 按模板 AST 查插值（注释、属性绑定都不算），原因码留在 data-reason-code 属性里供排查。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse } from 'vue/compiler-sfc'

const SRC = readFileSync(resolve(__dirname, '../WorkpaperCapabilityShell.vue'), 'utf-8')

function interpolations(node: any, out: string[] = []): string[] {
  if (node?.type === 5) out.push(String(node.content?.content ?? '').trim()) // NodeTypes.INTERPOLATION
  for (const child of node?.children ?? []) interpolations(child, out)
  return out
}

describe('WorkpaperCapabilityShell 错误条', () => {
  it('正文只插值中文说明，不插值原因码', () => {
    const { descriptor } = parse(SRC)
    const texts = interpolations(descriptor.template!.ast)
    expect(texts).toContain('shellError.zhMessage')
    expect(texts.filter((t) => t.includes('reasonCode'))).toEqual([])
    expect(descriptor.template!.content).toContain(':data-reason-code="shellError.reasonCode"')
  })
})
