/**
 * D4 IPO 取数公式真源覆盖面守卫 —— IPO_FORMULA_PRESETS 单一真源。
 *
 * spec: d4-ipo-checklist-dual-mode-writeback-and-formula · Wave 1 · Task 3
 *
 * 判据（Property 11-16 / 37）：
 *   - 每条 sheet_code ∈ {D4-25,D4-26,D4-27,D4-28}
 *   - 每条 column_key 在该 sheet 列规格 key 集合内
 *   - category='inter_sheet' 的 resolver 存在于后端 @auto_resolver 注册名（跨语言契约）
 *   - category='intra_sheet' 的 dependsOn 全为该 sheet 列 key
 *   - 派生列（derived:true）集合 == intra_sheet 公式的 column_key 集合（双向锁死）
 *   - source_ref 非空
 *   - 四个 .vue 组件内零公式字面量（只引用真源模块）
 *
 * 🔴 Wave 1 阶段必须先红：ipoChecklistSchema.ts / 后端 resolver 尚不存在。
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'

import * as schema from '../ipoChecklistSchema'

const SHEET_CODES = ['D4-25', 'D4-26', 'D4-27', 'D4-28'] as const
const RESOLVER_DIR = resolve(
  __dirname,
  '..', '..', '..', '..', '..', '..', '..', '..',
  'backend', 'app', 'services', 'auto_data_resolvers',
)
const IPO_DIR = resolve(__dirname, '..')
const TAB_FILES = ['D4TabDealer.vue', 'D4TabOverseas.vue', 'D4TabUndisclosedRp.vue', 'D4TabCustomerChecklist.vue']

/** 扫后端 auto_data_resolvers/*.py 里所有 @auto_resolver("name") 的注册名。 */
function scanBackendResolverNames(): Set<string> {
  const names = new Set<string>()
  if (!existsSync(RESOLVER_DIR)) return names
  for (const f of readdirSync(RESOLVER_DIR)) {
    if (!f.endsWith('.py')) continue
    const src = readFileSync(resolve(RESOLVER_DIR, f), 'utf-8')
    for (const m of src.matchAll(/@auto_resolver\(\s*['"]([^'"]+)['"]\s*\)/g)) {
      names.add(m[1])
    }
  }
  return names
}

function keysOf(sheetCode: string): Set<string> {
  const spec = schema.SHEET_SPECS[sheetCode]
  return new Set(spec.columns.map((c: any) => c.key))
}

const PRESETS = () => schema.IPO_FORMULA_PRESETS as any[]

describe('公式真源模块存在', () => {
  it('导出 IPO_FORMULA_PRESETS 数组', () => {
    expect(Array.isArray(schema.IPO_FORMULA_PRESETS)).toBe(true)
    expect(schema.IPO_FORMULA_PRESETS.length).toBeGreaterThan(0)
  })
})

describe('Property 11：sheet_code 全部 ∈ 四张 IPO 表', () => {
  it('无外部 sheet 混入', () => {
    for (const p of PRESETS()) {
      expect(SHEET_CODES).toContain(p.sheetCode)
    }
  })
})

describe('Property 12：column_key 都在该 sheet 列规格内', () => {
  it('无越界列', () => {
    for (const p of PRESETS()) {
      const keys = keysOf(p.sheetCode)
      expect(keys.has(p.columnKey), `${p.sheetCode}.${p.columnKey} 不在列规格内`).toBe(true)
    }
  })
})

describe('Property 13：inter_sheet 的 resolver 存在于后端 @auto_resolver（跨语言契约）', () => {
  const backend = scanBackendResolverNames()
  it('后端扫描到 resolver 名（非空）', () => {
    expect(backend.size).toBeGreaterThan(0)
  })
  it('每条 inter_sheet 公式的 resolver 已注册', () => {
    for (const p of PRESETS()) {
      if (p.category !== 'inter_sheet') continue
      expect(p.resolver, `${p.sheetCode}.${p.columnKey} inter_sheet 缺 resolver`).toBeTruthy()
      expect(
        backend.has(p.resolver),
        `resolver ${p.resolver} 未在后端 @auto_resolver 注册（拼错=fail-open最贵一类）`,
      ).toBe(true)
    }
  })
})

describe('Property 14：intra_sheet 的 dependsOn 全为该 sheet 列 key', () => {
  it('无越界依赖', () => {
    for (const p of PRESETS()) {
      if (p.category !== 'intra_sheet') continue
      const keys = keysOf(p.sheetCode)
      for (const dep of p.dependsOn) {
        expect(keys.has(dep), `${p.sheetCode}.${p.columnKey} 依赖 ${dep} 不在列规格内`).toBe(true)
      }
      expect(p.expression, `${p.sheetCode}.${p.columnKey} intra_sheet 缺 expression`).toBeTruthy()
    }
  })
})

describe('Property 15：派生列集合 == intra_sheet 公式的 column_key 集合（双向锁死）', () => {
  it.each(SHEET_CODES)('%s derived 列 == intra_sheet 公式列', (code) => {
    const spec = schema.SHEET_SPECS[code]
    const derivedKeys = new Set(spec.columns.filter((c: any) => c.derived).map((c: any) => c.key))
    const intraKeys = new Set(
      PRESETS().filter((p) => p.sheetCode === code && p.category === 'intra_sheet').map((p) => p.columnKey),
    )
    expect([...derivedKeys].sort()).toEqual([...intraKeys].sort())
  })
})

describe('Property 16：source_ref 非空', () => {
  it('每条公式都有审计依据锚点', () => {
    for (const p of PRESETS()) {
      expect(p.sourceRef, `${p.sheetCode}.${p.columnKey} 缺 sourceRef`).toBeTruthy()
    }
  })
})

describe('Property 3.9：四个 .vue 组件内零公式字面量（只引用真源模块）', () => {
  it.each(TAB_FILES)('%s 不自定义 IPO_FORMULA_PRESETS / 公式表达式常量', (file) => {
    const path = resolve(IPO_DIR, file)
    if (!existsSync(path)) {
      // Wave 1 阶段组件尚未改写；文件存在时才断言。这里用存在性推进（改写后转真断言）。
      expect(existsSync(path)).toBe(true)
      return
    }
    const src = readFileSync(path, 'utf-8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/.*$/gm, '$1')
    // 组件不得自己声明公式预设常量
    expect(src).not.toMatch(/const\s+\w*FORMULA\w*\s*=/)
    expect(src).not.toContain('IPO_FORMULA_PRESETS =')
    // 允许 import 引用真源
  })
})

// ── 反向自检：后端扫描 / keysOf 真在承重 ─────────────────────────────────────
describe('守卫自检（防恒真）', () => {
  it('scanBackendResolverNames 抓到已知 d4 resolver（如 d4_tb_unadjusted）', () => {
    const backend = scanBackendResolverNames()
    expect(backend.has('d4_tb_unadjusted')).toBe(true)
    expect(backend.has('__definitely_not_a_resolver__')).toBe(false)
  })
})
