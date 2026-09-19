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

// ═══════════════════════════════════════════════════════════════════════════
// Property 13b：inter_sheet 的 resolverField 必须真实存在于该 resolver 的返回体
//
// 🔴 补这条的原因（复盘实证）：Property 13 只校验「resolver **名字**在后端注册表里」，
//    名字对得上就绿 —— 于是「声明了 resolver 却从没人调用它取数」和「调用了但取错
//    字段名」两类缺陷全部漏网。真实发生过的就是前者：7 条 inter_sheet 声明齐全、
//    Property 13 全绿，但前端运行时零调用，金额列永远是 null。
//    字段名尤其容易错：后端返 **snake_case**（`sales_amount`），前端列 key 是
//    **camelCase**（`salesAmount`），靠推导必错，必须逐条声明 + 跨语言校验。
// ═══════════════════════════════════════════════════════════════════════════

/** 抽取某个 `@auto_resolver("name")` 装饰的函数体（到下一个顶层 @auto_resolver 或文件尾）。 */
function resolverBodyOf(resolverName: string): string {
  if (!existsSync(RESOLVER_DIR)) return ''
  for (const f of readdirSync(RESOLVER_DIR)) {
    if (!f.endsWith('.py')) continue
    const src = readFileSync(resolve(RESOLVER_DIR, f), 'utf-8')
    const marker = new RegExp(`@auto_resolver\\(\\s*['"]${resolverName}['"]\\s*\\)`)
    const hit = marker.exec(src)
    if (!hit) continue
    const rest = src.slice(hit.index + hit[0].length)
    const next = /@auto_resolver\(/.exec(rest)
    return next ? rest.slice(0, next.index) : rest
  }
  return ''
}

describe('Property 13b：inter_sheet 的 resolverField 在后端返回体里真实存在（跨语言字段契约）', () => {
  it('每条 inter_sheet 都声明了 resolverField（缺了前端无从知道取返回体哪个字段）', () => {
    for (const p of PRESETS()) {
      if (p.category !== 'inter_sheet') continue
      expect(
        p.resolverField,
        `${p.sheetCode}.${p.columnKey} inter_sheet 缺 resolverField —— 取数无法回填`,
      ).toBeTruthy()
    }
  })

  it('resolverField 字面量出现在对应 resolver 的返回体中（snake_case 拼错必红）', () => {
    const interPresets = PRESETS().filter((p) => p.category === 'inter_sheet')
    expect(interPresets.length, 'inter_sheet 预设不该为空').toBeGreaterThan(0)
    for (const p of interPresets) {
      const body = resolverBodyOf(p.resolver)
      expect(body, `未定位到 resolver ${p.resolver} 的函数体`).not.toBe('')
      expect(
        new RegExp(`['"]${p.resolverField}['"]\\s*:`).test(body),
        `resolver ${p.resolver} 的返回体里没有键 "${p.resolverField}"`
          + `（${p.sheetCode}.${p.columnKey} 会永远取不到值）`,
      ).toBe(true)
    }
  })

  it('反向自检：不存在的字段名必须判否（否则本判据是假绿）', () => {
    const body = resolverBodyOf('d4_25_dealer_sales')
    expect(body).not.toBe('')
    expect(/['"]sales_amount['"]\s*:/.test(body)).toBe(true)
    expect(/['"]__definitely_not_a_field__['"]\s*:/.test(body)).toBe(false)
  })
})

describe('Property 13c：取数计划按 resolver 去重分组，且覆盖全部 inter_sheet 列', () => {
  it('interSheetFetchPlans 的 targets 并集 == 该 sheet 的 inter_sheet columnKey 集合', () => {
    for (const code of SHEET_CODES) {
      const declared = new Set(
        PRESETS().filter((p) => p.sheetCode === code && p.category === 'inter_sheet').map((p) => p.columnKey),
      )
      const planned = new Set((schema as any).interSheetColumnKeys(code) as string[])
      expect(planned, `${code} 取数计划与声明不一致`).toEqual(declared)
    }
  })

  it('同一 resolver 只出现一个计划条目（避免同查询重复打后端）', () => {
    for (const code of SHEET_CODES) {
      const plans = (schema as any).interSheetFetchPlans(code) as Array<{ resolver: string }>
      const names = plans.map((p) => p.resolver)
      expect(new Set(names).size, `${code} 的取数计划里有重复 resolver`).toBe(names.length)
    }
  })

  it('D4-28 的三列由同一个 resolver 一次取回（N:1 的真实形态）', () => {
    const plans = (schema as any).interSheetFetchPlans('D4-28') as Array<{
      resolver: string
      targets: Array<{ columnKey: string }>
    }>
    const plan = plans.find((p) => p.resolver === 'd4_28_customer_balances')
    expect(plan).toBeTruthy()
    expect(plan!.targets.map((t) => t.columnKey).sort()).toEqual(
      ['arBalance', 'contractLiabBalance', 'salesAmount'],
    )
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
