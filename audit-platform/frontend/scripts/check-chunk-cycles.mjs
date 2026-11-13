#!/usr/bin/env node
// 检查构建产物入口可达的 chunk 静态 import 图是否有环（动态 import 不算）。
// 用法：node scripts/check-chunk-cycles.mjs --dir dist
import { readdirSync, readFileSync } from 'node:fs'
import { join, basename } from 'node:path'

// 只匹配顶层静态写法：import ... from "./x.js" / import "./x.js" / export ... from "./x.js"
const STATIC_IMPORT = /(?:^|[;\n}])\s*(?:import|export)\s*(?:[^'"()]*?\sfrom\s*)?["'](\.{1,2}\/[^"']+\.js)["']/g

export function parseStaticImports(source) {
  const result = new Set()
  for (const match of source.matchAll(STATIC_IMPORT)) result.add(basename(match[1]))
  return [...result]
}

/** graph: Map<string, string[]>，返回所有包含环的强连通分量（Tarjan）。 */
export function findCycles(graph) {
  let index = 0
  const stack = []
  const onStack = new Set()
  const idx = new Map()
  const low = new Map()
  const cycles = []
  const visit = (node) => {
    idx.set(node, index)
    low.set(node, index)
    index += 1
    stack.push(node)
    onStack.add(node)
    for (const next of graph.get(node) ?? []) {
      if (!graph.has(next)) continue
      if (!idx.has(next)) {
        visit(next)
        low.set(node, Math.min(low.get(node), low.get(next)))
      } else if (onStack.has(next)) {
        low.set(node, Math.min(low.get(node), idx.get(next)))
      }
    }
    if (low.get(node) === idx.get(node)) {
      const component = []
      let top
      do {
        top = stack.pop()
        onStack.delete(top)
        component.push(top)
      } while (top !== node)
      const selfLoop = component.length === 1 && (graph.get(node) ?? []).includes(node)
      if (component.length > 1 || selfLoop) cycles.push(component.reverse())
    }
  }
  for (const node of graph.keys()) if (!idx.has(node)) visit(node)
  return cycles
}

export function buildGraph(assetsDir) {
  const graph = new Map()
  for (const file of readdirSync(assetsDir)) {
    if (!file.endsWith('.js')) continue
    graph.set(file, parseStaticImports(readFileSync(join(assetsDir, file), 'utf8')))
  }
  return graph
}

if (import.meta.url === `file://${process.argv[1].replace(/\\/g, '/')}` || process.argv[1]?.endsWith('check-chunk-cycles.mjs')) {
  const dirIndex = process.argv.indexOf('--dir')
  const dir = dirIndex > -1 ? process.argv[dirIndex + 1] : 'dist'
  const graph = buildGraph(join(dir, 'assets'))
  const strict = process.argv.includes('--strict')
  const cycles = findCycles(graph)
  // 首屏白屏只由 vendor-* 参与的环触发；懒加载业务块之间的环只警告，--strict 时一律失败。
  const fatal = cycles.filter((cycle) => strict || cycle.some((name) => name.startsWith('vendor-')))
  for (const cycle of cycles) {
    const level = fatal.includes(cycle) ? '错误' : '警告'
    console.error(`[${level}] chunk 静态 import 环：${cycle.join(' -> ')}`)
  }
  if (fatal.length) process.exit(1)
  console.log(`chunk 静态 import 图无环（${graph.size} 个块）`)
}
