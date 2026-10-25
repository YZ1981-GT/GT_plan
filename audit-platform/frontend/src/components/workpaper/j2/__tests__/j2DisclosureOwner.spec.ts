import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const root = resolve(process.cwd(), 'src/components/workpaper')
const read = (rel: string) => readFileSync(resolve(root, rel), 'utf8')
const keyValues = (source: string) => {
  const body = source.match(/const KEY\s*=\s*\{([^}]*)\}/)?.[1] ?? ''
  return [...body.matchAll(/:\s*'([^']+)'/g)].map(m => m[1])
}

describe('J2/J3 disclosure 键 owner 边界', () => {
  it('J2 两个披露 Tab 分别拥有 11/9 个语义键，namespace 不交叉', () => {
    const listed = keyValues(read('j2/J2TabDisclosureListed.vue'))
    const soe = keyValues(read('j2/J2TabDisclosureSoe.vue'))
    expect(listed).toHaveLength(11)
    expect(soe).toHaveLength(9)
    expect(listed.every(k => k.startsWith('J2-listed-'))).toBe(true)
    expect(soe.every(k => k.startsWith('J2-soe-'))).toBe(true)
    expect(listed.filter(k => soe.includes(k))).toEqual([])
  })

  it('目录页只消费 allResponses，不声明第二份 KEY 真源', () => {
    expect(read('j2/J2TabIndex.vue')).not.toMatch(/const KEY\s*=/)
    expect(read('j3/core/J3TabIndex.vue')).not.toMatch(/const KEY\s*=/)
  })

  it('J3 真实 owner 的键按 sheet namespace 分离', () => {
    const detail = keyValues(read('j3/core/J3TabDetail.vue'))
    const check = keyValues(read('j3/core/J3TabCheck.vue'))
    const ipo = keyValues(read('j3/core/J3TabIpoFocus.vue'))
    expect(detail).toHaveLength(6)
    expect(check).toHaveLength(4)
    expect(ipo).toEqual(['J3-IPO-note'])
    expect(detail.every(k => k.startsWith('J3-1-'))).toBe(true)
    expect(check.every(k => k.startsWith('J3-2-'))).toBe(true)
  })
})
