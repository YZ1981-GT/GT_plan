// WorkpaperWorkbench 折叠 DOM 与近线性树（runtime-performance-and-reload-hardening-followup R6.4）。
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { buildWorkpaperTree } from '../workpaperTree'

interface Row { id: string; wp_code: string }

/** 改前冻结算法：测试 oracle，不被生产实现复用。 */
function oldBuildTree(items: Row[]) {
  const codes = items.map(i => i.wp_code)
  const parentCodes = new Set<string>()
  for (const code of codes) {
    if (codes.some(c => c !== code && c.startsWith(code + '-'))) parentCodes.add(code)
  }
  const childOf = new Map<string, string>()
  for (const item of items) {
    let bestParent = ''
    for (const p of parentCodes) {
      if (item.wp_code.startsWith(p + '-') && p.length > bestParent.length) bestParent = p
    }
    if (bestParent) childOf.set(item.wp_code, bestParent)
  }
  const result: Array<{ row: Row; children: Row[] }> = []
  const childMap = new Map<string, Row[]>()
  for (const item of items) {
    const parent = childOf.get(item.wp_code)
    if (parent) {
      const children = childMap.get(parent) ?? []
      children.push(item)
      childMap.set(parent, children)
    } else result.push({ row: item, children: [] })
  }
  for (const node of result) node.children = childMap.get(node.row.wp_code) ?? []
  return result
}

function shape(nodes: Array<{ row: Row; children: Row[] }>) {
  return nodes.map(node => ({ row: node.row.id, children: node.children.map(child => child.id) }))
}

function rows(codes: string[]): Row[] {
  return codes.map((wp_code, index) => ({ id: `${index}:${wp_code}`, wp_code }))
}

describe('buildWorkpaperTree', () => {
  it.each([
    ['基础父子', ['A1', 'A1-1', 'A1-2', 'A2']],
    ['最长真实父', ['A1', 'A1-1', 'A1-1-1', 'A1-2', 'A17', 'A17-1']],
    ['没有父码不折叠', ['D2-1', 'D2-2', 'D3']],
    ['连字符边界', ['A1', 'A10-1', 'A1x-1', 'A1-1']],
    ['重复编码', ['B1', 'B1', 'B1-1', 'B1-1']],
    ['中文与空码', ['', '专项', '专项-1', '?', '?-1']],
  ])('%s 与旧算法逐项相同', (_name, codes) => {
    const input = rows(codes as string[])
    expect(shape(buildWorkpaperTree(input))).toEqual(shape(oldBuildTree(input)))
  })

  it('200组确定性组合与旧算法逐项对拍', () => {
    for (let seed = 0; seed < 200; seed++) {
      const codes: string[] = []
      for (let i = 0; i < 30; i++) {
        const root = `${String.fromCharCode(65 + ((seed + i) % 14))}${(i % 9) + 1}`
        const kind = (seed * 17 + i * 7) % 5
        codes.push(kind === 0 ? root : kind === 1 ? `${root}-${i % 4}` : kind === 2 ? `${root}-${i % 4}-${i % 3}` : `${root}X`)
      }
      const input = rows(codes)
      expect(shape(buildWorkpaperTree(input))).toEqual(shape(oldBuildTree(input)))
    }
  })

  it('生产算法不含每行 codes.some / 遍历 parentCodes 的二次扫描', () => {
    const source = fs.readFileSync(path.resolve(__dirname, '../workpaperTree.ts'), 'utf-8')
    expect(source).toContain('const codes = new Set')
    expect(source).toContain("code.lastIndexOf('-')")
    expect(source).not.toContain('codes.some(')
    expect(source).not.toMatch(/for\s*\(const\s+p\s+of\s+parentCodes/)
  })

  it('模板折叠用 v-if 且只读预计算 group.tree', () => {
    const source = fs.readFileSync(path.resolve(__dirname, '../WorkpaperWorkbenchView.vue'), 'utf-8')
    expect(source).toContain('v-if="expandedCycleGroups[group.code]"')
    expect(source).not.toContain('v-show="expandedCycleGroups[group.code]"')
    expect(source).toContain('v-for="node in group.tree"')
    expect(source).not.toContain('v-for="node in buildTree(group.items)"')
    expect(source).toContain('tree: buildWorkpaperTree(items)')
  })
})
