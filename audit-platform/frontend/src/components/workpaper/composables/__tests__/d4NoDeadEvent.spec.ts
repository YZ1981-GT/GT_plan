/**
 * d4NoDeadEvent 守卫 —— 防"发了无人听的 CustomEvent"死代码回归
 *
 * Spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Requirements 1.5, 6.2
 *
 * 背景：D4 曾有 `d4:sync-row`（syncProductRowToAdjudication/syncOtherItemRowToAdjudication）
 * 只发不听的死代码。本守卫静态断言：
 *  1. `d4:sync-row` 已彻底移除（无任何 dispatch/emit 残留）。
 *  2. 新增的 `d4:price-abnormal` 既有发送端（emit）也有接收端（eventBus.on），非死代码。
 *
 * 变异：删 useD4PriceWriteback 的 eventBus.on('d4:price-abnormal') → 本守卫必红。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

const WORKPAPER_DIR = resolve(__dirname, '../..')

/** 递归收集 .ts/.vue 文件（排除 __tests__ 自身） */
function collectSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === '__tests__' || entry.name === 'node_modules') continue
    const full = resolve(dir, entry.name)
    if (entry.isDirectory()) collectSourceFiles(full, out)
    else if (/\.(ts|vue)$/.test(entry.name)) out.push(full)
  }
  return out
}

const FILES = collectSourceFiles(WORKPAPER_DIR)
const CONTENTS = new Map(FILES.map(f => [f, readFileSync(f, 'utf-8')]))

function anyFileMatches(re: RegExp): string[] {
  const hits: string[] = []
  for (const [f, c] of CONTENTS) if (re.test(c)) hits.push(f)
  return hits
}

describe('d4NoDeadEvent — 死代码防回归', () => {
  it('确认扫到了 D4 源码（防空转）', () => {
    expect(FILES.some(f => /useD4CrossSheet\.ts$/.test(f))).toBe(true)
    expect(FILES.some(f => /useD4PriceWriteback\.ts$/.test(f))).toBe(true)
  })

  it('d4:sync-row 死代码已彻底移除（无 dispatch/emit，注释除外）', () => {
    // 只查真实事件字符串出现（dispatchEvent/emit 中的 'd4:sync-row'），注释里的说明不算
    const re = /(dispatchEvent|\.emit)\s*\([^)]*['"]d4:sync-row['"]/
    const hits = anyFileMatches(re)
    expect(hits, `残留 d4:sync-row 发送端: ${hits.join(', ')}`).toHaveLength(0)
  })

  it('syncProductRowToAdjudication / syncOtherItemRowToAdjudication 死函数已删（除注释）', () => {
    // 断言无函数定义 `function syncProductRowToAdjudication`
    const reDef = /function\s+sync(Product|OtherItem)\w*Adjudication/
    const hits = anyFileMatches(reDef)
    expect(hits, `残留死函数定义: ${hits.join(', ')}`).toHaveLength(0)
  })

  it('d4:price-abnormal 既有发送端(emit)也有接收端(eventBus.on) — 非死代码', () => {
    const emitHits = anyFileMatches(/\.emit\s*\(\s*['"]d4:price-abnormal['"]/)
    const onHits = anyFileMatches(/eventBus\.on\s*\(\s*['"]d4:price-abnormal['"]/)
    expect(emitHits.length, '缺 d4:price-abnormal 发送端').toBeGreaterThan(0)
    expect(onHits.length, '缺 d4:price-abnormal 接收端（死代码！）').toBeGreaterThan(0)
    // 发送端应含 D4-10/D4-11 组件
    expect(emitHits.some(f => /D4TabCustomerPrice\.vue$/.test(f))).toBe(true)
    expect(emitHits.some(f => /D4TabProductPrice\.vue$/.test(f))).toBe(true)
    // 接收端应在 useD4PriceWriteback
    expect(onHits.some(f => /useD4PriceWriteback\.ts$/.test(f))).toBe(true)
  })

  it('宿主 GtD4OperatingRevenue 必须 provide d4CrossSheet 且挂载 useD4PriceWriteback', () => {
    const hostPath = FILES.find(f => /GtD4OperatingRevenue\.vue$/.test(f))
    expect(hostPath, '找不到 GtD4OperatingRevenue.vue').toBeTruthy()
    const src = CONTENTS.get(hostPath!)!
    expect(src).toMatch(/provide\s*\(\s*['"]d4CrossSheet['"]/)
    expect(src).toMatch(/useD4PriceWriteback\s*\(/)
  })
})
