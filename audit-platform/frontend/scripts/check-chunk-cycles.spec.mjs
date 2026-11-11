import { test, expect } from 'vitest'
import { findCycles, parseStaticImports } from './check-chunk-cycles.mjs'

test('无环图不报', () => {
  const graph = new Map([['a.js', ['b.js']], ['b.js', ['c.js']], ['c.js', []]])
  expect(findCycles(graph)).toEqual([])
})

test('两块互相静态引用报环', () => {
  const graph = new Map([['vendor-core.js', ['index.js']], ['index.js', ['vendor-core.js']]])
  const cycles = findCycles(graph)
  expect(cycles).toHaveLength(1)
  expect([...cycles[0]].sort()).toEqual(['index.js', 'vendor-core.js'])
})

test('自引用报环', () => {
  expect(findCycles(new Map([['a.js', ['a.js']]]))).toHaveLength(1)
})

test('解析静态 import，忽略动态 import', () => {
  const source = [
    'import { a as b } from "./vendor-core-1.js";',
    'import "./side-2.js";',
    'export { x } from "./re-3.js";',
    'const m = () => import("./lazy-4.js");',
  ].join('\n')
  expect(parseStaticImports(source).sort()).toEqual(['re-3.js', 'side-2.js', 'vendor-core-1.js'])
})
