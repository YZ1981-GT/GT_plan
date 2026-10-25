import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const src = (name: string) => readFileSync(resolve(process.cwd(), `src/components/workpaper/j3/${name}`), 'utf8')

describe('J3 持久化与目录键真实可达', () => {
  it('目录只读真实生产键，不再读 J3-detail/J3-check 幽灵键', () => {
    const code = src('core/J3TabIndex.vue')
    expect(code).toContain("progressKeys: ['J3-1-']")
    expect(code).toContain("progressKeys: ['J3-2-']")
    expect(code).not.toContain("'J3-detail'")
    expect(code).not.toContain("'J3-check'")
  })

  it('J3 Tab 不直接 PUT checklist，统一由父宿主 saveImmediate/persistence 写', () => {
    const detail = src('core/J3TabDetail.vue')
    expect(detail).not.toMatch(/(?:http|api)\.put\([^)]*checklist-responses/s)
    expect(detail).toContain('props.saveImmediate?.([')
  })

  it('真实生产边 useJ3ImportExport 保留且被 J3TabDetail 深链引用', () => {
    const detail = src('core/J3TabDetail.vue')
    expect(detail).toContain("@/composables/workpaper/j3/useJ3ImportExport")
  })
})
