/**
 * dCycleAccountScope.spec.ts — D 循环科目视图守卫（Property 12 / 15）
 *
 * spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
 *       Requirements 3.1, 3.2, 3.3, 3.5, 4.4, 4.6
 *
 * 三条判据来源与已登记的坑：
 *
 * 1. **交叉锁死后端** —— 读 `d_account_resolver.py` 源码比对槽键 / 报表行 / 兜底码。
 *    🔴 必须锁 `D_ACCOUNT_SPECS`（render 真实消费的），**不是** `four_table/d_cycle_specs.py`
 *    （它自己 docstring 就写着「当前不接线」）。实测两者对 D5 的 gross 兜底不同：
 *    前者 `('1124',)`、后者 `()` —— 锁错模块就是 memory 已登记的「守卫导入错模块」，
 *    平台的 `test_cycle_specs_row_code_evidence.py` 正是这么漏掉 D2~D7 的。
 *
 * 2. **剥注释 + 剥 docstring** —— D5 的兜底码上方有长注释解释「曾一度留空」并写出了
 *    反例 `fallback_gross=()`，只剥 `#` 不够（Python 的 `"""` 块注释同样含反例）。
 *
 * 3. **三态语义** —— `render 未下发 ⇒ false`（未知不等于无）。禁 `Number(null)===0`。
 */
import { describe, expect, it } from 'vitest'
import fs from 'fs'
import path from 'path'

import {
  D_CYCLE_SCOPES,
  D_LIABILITY_CYCLES,
  D_PL_CYCLES,
  D_SLOT_GROSS,
  D_SLOT_PROVISION,
  type DTbSourceCodes,
  dCycleBasisLabel,
  dCycleScope,
  dDroppedCodes,
  dSlotAccountCode,
  dSlotClosing,
  dSlotOpening,
  dSlotPrefixMismatch,
  dSlotQueryCodes,
  dSlotStateLabel,
  dSlotStateTagType,
  hasDPrefixMismatch,
  isDAccountAbsent,
  isDPlCycle,
  normalizeDSlots,
  pickDTbSourceCodes,
} from '../dCycleAccountScope'

// 🔴 `composables/__tests__/` 下回退 **7 级**（照抄 gCycleAccountScope/hCycleAccountScope
//    的既有范式，不自己数）。`workpaper/__tests__/` 下是 6 级，照抄那边会 ENOENT
//    且表现为「文件级失败」而非断言失败，极易被当噪声跳过。
const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const BACKEND_RESOLVER = path.join(
  REPO_ROOT,
  'backend/app/services/d_cycle_extraction/d_account_resolver.py',
)
const BACKEND_D1 = path.join(
  REPO_ROOT,
  'backend/app/services/d_cycle_extraction/d1_account_resolver.py',
)
const NOT_WIRED_SPEC = path.join(
  REPO_ROOT,
  'backend/app/services/four_table/d_cycle_specs.py',
)

/**
 * 剥掉 Python 的 `#` 注释与 `"""` docstring。
 *
 * 🔴 两者都要剥：被读的源码在注释**与** docstring 里都如实写着反例
 * （D5 的「曾一度刻意留空 `fallback_gross=()`」、D2 的「不能写成『应收』」）。
 */
function stripPy(src: string): string {
  const out: string[] = []
  let inDoc = false
  let quote = ''
  for (const line of src.split('\n')) {
    const s = line.trim()
    if (inDoc) {
      if (s.includes(quote)) inDoc = false
      continue
    }
    if (s.startsWith('"""') || s.startsWith("'''")) {
      quote = s.startsWith('"""') ? '"""' : "'''"
      const body = s.slice(3)
      if (!body.includes(quote)) inDoc = true
      continue
    }
    if (s.startsWith('#')) continue
    out.push(line)
  }
  return out.join('\n')
}

/** 从后端源码抽某个 `ReportLineAccountSpec` 块的字段（按圆括号配对，不用非贪婪正则） */
function backendSpecBlock(src: string, name: string): string {
  const anchor = `${name} = ReportLineAccountSpec(`
  const i = src.indexOf(anchor)
  if (i < 0) return ''
  let depth = 1
  let j = i + anchor.length
  while (j < src.length && depth > 0) {
    if (src[j] === '(') depth += 1
    else if (src[j] === ')') depth -= 1
    j += 1
  }
  return src.slice(i, j)
}

function tupleItems(block: string, field: string): string[] {
  const m = new RegExp(`${field}\\s*=\\s*\\(([^)]*)\\)`).exec(block)
  if (!m) return []
  return (m[1].match(/["']([^"']+)["']/g) || []).map((s) => s.replace(/["']/g, ''))
}

function rowCodeOf(block: string): string {
  const m = /row_code\s*=\s*["']([^"']+)["']/.exec(block)
  return m ? m[1] : ''
}

const RESOLVER_SRC = stripPy(fs.readFileSync(BACKEND_RESOLVER, 'utf-8'))
const D1_SRC = stripPy(fs.readFileSync(BACKEND_D1, 'utf-8'))

/** 槽载荷构造器（对齐后端 `SlotAmounts.as_dict()` 的实测键集） */
function slot(over: Record<string, unknown> = {}) {
  return {
    key: D_SLOT_GROSS,
    found: true,
    state: 'ok',
    query_codes: ['1122'],
    tb_rows_count: 4,
    prefix_mismatch: false,
    opening: 100,
    closing: 200,
    dropped: [],
    warnings: [],
    ...over,
  }
}

function payload(slots: Record<string, unknown>, extra: Record<string, unknown> = {}) {
  return { slots, ...extra } as DTbSourceCodes
}

// ───────────────── 反向自检：路径解析正确（防断言空转）─────────────────

describe('守卫自身有效性', () => {
  it('REPO_ROOT 与后端源码路径解析正确', () => {
    expect(fs.existsSync(BACKEND_RESOLVER)).toBe(true)
    expect(fs.existsSync(BACKEND_D1)).toBe(true)
    expect(RESOLVER_SRC.length).toBeGreaterThan(500)
    expect(RESOLVER_SRC).toContain('D_ACCOUNT_SPECS')
  })

  it('stripPy 确实剥掉了 docstring 与注释里的反例', () => {
    const raw = fs.readFileSync(BACKEND_RESOLVER, 'utf-8')
    // 原文里有「曾一度刻意留空 fallback_gross=()」这句说明
    expect(raw).toContain('fallback_gross=()')
    // 剥离后不应再有那个反例（真实声明是 fallback_gross=("1124",)）
    expect(stripPy(raw)).not.toContain('fallback_gross=()')
    // 但真实代码必须还在（防剥离过度把整段吃掉）
    expect(stripPy(raw)).toContain('D_ACCOUNT_SPECS')
  })

  it('fixture 里 stripPy 能正确处理单行 docstring', () => {
    const fixture = 'a = 1\n"""one-line doc"""\nb = 2\n'
    const got = stripPy(fixture)
    expect(got).toContain('a = 1')
    expect(got).toContain('b = 2')
    expect(got).not.toContain('one-line doc')
  })
})

// ───────────────── Property 12：与后端交叉锁死 ─────────────────

describe('Property 12: 前后端科目声明交叉锁死', () => {
  it.each([
    ['D2', 'BS-006', ['1122'], ['1231-02']],
    ['D3', 'BS-046', ['2203'], []],
    ['D5', 'BS-007', ['1124'], []],
    ['D6', 'BS-011', ['1141'], ['1142', '1231-05']],
    ['D7', 'BS-047', ['2205'], []],
  ] as const)('%s 的报表行与兜底码与后端一致', (wp, rowCode, gross, provision) => {
    const block = backendSpecBlock(RESOLVER_SRC, `${wp}_SPEC`)
    expect(block, `后端未找到 ${wp}_SPEC —— 常量名或结构变了`).not.toBe('')
    expect(rowCodeOf(block)).toBe(rowCode)
    expect(tupleItems(block, 'fallback_gross')).toEqual(gross)
    expect(tupleItems(block, 'fallback_provision')).toEqual(provision)

    const scope = dCycleScope(wp)!
    expect(scope, `前端未登记 ${wp}`).toBeTruthy()
    expect(scope.spec.reportRowCode).toBe(rowCode)
    expect(scope.spec.slots[0].fallback).toBe(gross[0])
    if (provision.length) {
      const prov = scope.spec.slots.find((s) => s.key === D_SLOT_PROVISION)
      expect(prov, `${wp} 前端缺备抵槽`).toBeTruthy()
      // 后端两个候选码时前端只展示第一个（展示用，运行态取 render 下发值）
      expect(provision).toContain(prov!.fallback)
    }
  })

  it('D1 的报表行与兜底码与其薄壳一致（零回归红线）', () => {
    expect(/D1_REPORT_ROW_CODE\s*=\s*["']BS-005["']/.test(D1_SRC)).toBe(true)
    expect(/D1_FALLBACK_GROSS\s*=\s*["']1121["']/.test(D1_SRC)).toBe(true)
    expect(/D1_FALLBACK_PROVISION\s*=\s*["']1231-01["']/.test(D1_SRC)).toBe(true)

    const scope = dCycleScope('D1')!
    expect(scope.spec.reportRowCode).toBe('BS-005')
    expect(scope.spec.slots[0].fallback).toBe('1121')
    expect(scope.spec.slots.find((s) => s.key === D_SLOT_PROVISION)!.fallback).toBe('1231-01')
  })

  it('🔴 锁的是 D_ACCOUNT_SPECS 而非未接线的 d_cycle_specs', () => {
    // 实证两者对 D5 的 gross 兜底不同 —— 锁错模块 = 守卫导入错模块
    const notWired = stripPy(fs.readFileSync(NOT_WIRED_SPEC, 'utf-8'))
    expect(fs.existsSync(NOT_WIRED_SPEC)).toBe(true)
    // 未接线那份对 D5 是 fallback_standard_codes=()（空）
    expect(notWired).toMatch(/fallback_standard_codes=\(\)/)
    // 而本守卫读的那份对 D5 是 ('1124',)
    expect(tupleItems(backendSpecBlock(RESOLVER_SRC, 'D5_SPEC'), 'fallback_gross')).toEqual([
      '1124',
    ])
    // 前端取的是后者
    expect(dCycleScope('D5')!.spec.slots[0].fallback).toBe('1124')
  })

  it('备抵关键词与后端 D_SUBJECT_KEYWORDS 一致且粒度足够', () => {
    // D2 只能是「应收账款」——「应收」会让过滤空转（错映射那条名叫「坏账准备_长期应收款」）
    expect(RESOLVER_SRC).toMatch(/"D2":\s*\("应收账款",\)/)
    expect(RESOLVER_SRC).toMatch(/"D6":\s*\("合同资产",\)/)
    expect(RESOLVER_SRC).not.toMatch(/"D2":\s*\("应收",\)/)
  })

  it('D1/D4 在后端有意不纳入 D_ACCOUNT_SPECS 且登记了去处', () => {
    expect(RESOLVER_SRC).toContain('NOT_IN_SCOPE')
    expect(RESOLVER_SRC).toMatch(/"D1":\s*"[^"]{10,}"/)
    expect(RESOLVER_SRC).toMatch(/"D4":\s*"[^"]{10,}"/)
    // 前端仍登记 D1/D4（它们有自己的取数路径，界面照样要展示口径）
    expect(dCycleScope('D1')).toBeTruthy()
    expect(dCycleScope('D4')).toBeTruthy()
  })

  it('7 个循环全部登记，无多无少', () => {
    expect(Object.keys(D_CYCLE_SCOPES).sort()).toEqual([
      'D1',
      'D2',
      'D3',
      'D4',
      'D5',
      'D6',
      'D7',
    ])
  })
})

// ───────────────── Property 15：三态语义与取值守卫 ─────────────────

describe('Property 15: 三态互不混淆', () => {
  it('render 未下发该槽 ⇒ 未知，不判「无此科目」', () => {
    expect(isDAccountAbsent(payload({}))).toBe(false)
    expect(isDAccountAbsent(null)).toBe(false)
    expect(isDAccountAbsent(undefined)).toBe(false)
    expect(dSlotClosing(payload({}))).toBeNull()
  })

  it('found=false ⇒ 本项目无此科目', () => {
    const p = payload({ gross: slot({ found: false, state: 'no_account', query_codes: [], closing: null }) })
    expect(isDAccountAbsent(p)).toBe(true)
    expect(dSlotClosing(p)).toBeNull()
    expect(dSlotStateLabel(p)).toBe('本项目无此科目')
  })

  it('found=true 且四表无数据 ⇒ 不算无此科目，金额为 null', () => {
    const p = payload({
      gross: slot({ state: 'no_data', tb_rows_count: 0, closing: null, opening: null }),
    })
    expect(isDAccountAbsent(p)).toBe(false)
    expect(dSlotClosing(p)).toBeNull()
    expect(dSlotStateLabel(p)).toBe('科目表有此科目，四表无数据行')
  })

  it('🔴 余额确实为 0 与「无数据」必须可区分', () => {
    const zero = payload({ gross: slot({ closing: 0, opening: 0 }) })
    const none = payload({ gross: slot({ state: 'no_data', tb_rows_count: 0, closing: null }) })
    expect(dSlotClosing(zero)).toBe(0)
    expect(dSlotClosing(none)).toBeNull()
    expect(dSlotClosing(zero)).not.toBe(dSlotClosing(none))
    // 反向自检：Number(null) === 0 会把两者混为一谈
    expect(Number(null)).toBe(0)
    expect(Number(null) === dSlotClosing(zero)).toBe(true) // 正是要避免的写法
  })

  it('非法/空串金额一律返 null 而非 NaN', () => {
    for (const bad of ['', 'abc', undefined, null]) {
      const p = payload({ gross: slot({ closing: bad as never }) })
      expect(dSlotClosing(p)).toBeNull()
    }
  })

  it('opening 同口径', () => {
    expect(dSlotOpening(payload({ gross: slot({ opening: 0 }) }))).toBe(0)
    expect(dSlotOpening(payload({ gross: slot({ opening: null }) }))).toBeNull()
  })

  it('state → tag type：无科目/无数据用 info，不用 danger', () => {
    expect(dSlotStateTagType(payload({ gross: slot({ state: 'no_account' }) }))).toBe('info')
    expect(dSlotStateTagType(payload({ gross: slot({ state: 'no_data' }) }))).toBe('info')
    expect(dSlotStateTagType(payload({ gross: slot({ state: 'prefix_mismatch' }) }))).toBe('warning')
    expect(dSlotStateTagType(payload({ gross: slot({ state: 'ok' }) }))).toBe('success')
  })
})

describe('Property 15: 查询口径与前缀不匹配', () => {
  it('运行态取 query_codes；未下发时回退兜底码', () => {
    const p = payload({ gross: slot({ query_codes: ['1122', '1122.01'] }) })
    expect(dSlotQueryCodes('D2', p)).toEqual(['1122', '1122.01'])
    // 未下发 → 回退声明的兜底码
    expect(dSlotQueryCodes('D2', null)).toEqual(['1122'])
    expect(dSlotAccountCode('D2', p)).toBe('1122')
  })

  it('未登记的循环返空，绝不凭空造前缀', () => {
    expect(dSlotQueryCodes('XX', null)).toEqual([])
    expect(dSlotAccountCode('XX', null)).toBe('')
  })

  it('prefix_mismatch 逐槽与汇总标志', () => {
    const p = payload({
      gross: slot(),
      provision: slot({ key: D_SLOT_PROVISION, state: 'prefix_mismatch', prefix_mismatch: true, tb_rows_count: 0, closing: null }),
    })
    expect(dSlotPrefixMismatch(p, D_SLOT_PROVISION)).toBe(true)
    expect(dSlotPrefixMismatch(p, D_SLOT_GROSS)).toBe(false)
    expect(hasDPrefixMismatch(p)).toBe(true)
    expect(hasDPrefixMismatch(payload({ gross: slot() }))).toBe(false)
  })

  it('dropped 逐条可取（溯源面板要展示剔除了什么）', () => {
    const p = payload({
      provision: slot({
        key: D_SLOT_PROVISION,
        dropped: [{ code: '1231.05', name: '坏账准备_长期应收款', reason: '名称不含本循环主体关键词（应收账款）' }],
      }),
    })
    const d = dDroppedCodes(p)
    expect(d).toHaveLength(1)
    expect(d[0].code).toBe('1231.05')
    expect(String(d[0].reason)).toContain('应收账款')
  })
})

// ───────────────── 载荷落点与形态归一 ─────────────────

describe('落点两套并存都要读', () => {
  it('html_data 顶层（D1/D2/D3/D5/D6/D7 的实际落点）', () => {
    const hd = { tb_source_codes: payload({ gross: slot() }) }
    expect(pickDTbSourceCodes(hd)).toBeTruthy()
  })

  it('project_context（D4 的实际落点）', () => {
    const hd = { project_context: { tb_source_codes: payload({ gross: slot() }) } }
    expect(pickDTbSourceCodes(hd)).toBeTruthy()
  })

  it('两处都没有 ⇒ null（不编造空对象）', () => {
    expect(pickDTbSourceCodes({})).toBeNull()
    expect(pickDTbSourceCodes(null)).toBeNull()
    expect(pickDTbSourceCodes('x')).toBeNull()
  })

  it('🔴 只读一层会漏掉另一批循环（反向自检）', () => {
    const onlyTop = { tb_source_codes: payload({ gross: slot() }) }
    const onlyPc = { project_context: { tb_source_codes: payload({ gross: slot() }) } }
    // 朴素实现（只读 project_context）会对 6 个循环返 null
    expect((onlyTop as never as { project_context?: unknown }).project_context).toBeUndefined()
    // 本模块两层都读，故两种都拿得到
    expect(pickDTbSourceCodes(onlyTop)).toBeTruthy()
    expect(pickDTbSourceCodes(onlyPc)).toBeTruthy()
  })
})

describe('槽形态归一（供共享工厂消费）', () => {
  it('query_codes 投影为 codes 与 standard_codes', () => {
    const n = normalizeDSlots(payload({ gross: slot({ query_codes: ['1122', '1122.01'] }) }))!
    const g = n.slots!.gross as Record<string, unknown>
    expect(g.codes).toEqual(['1122', '1122.01'])
    expect(g.standard_codes).toEqual(['1122', '1122.01'])
    // 原字段保留（溯源仍要展示 query_codes）
    expect(g.query_codes).toEqual(['1122', '1122.01'])
  })

  it('已有 codes/standard_codes 时不覆盖（将来换语义解析器的形态）', () => {
    const n = normalizeDSlots(
      payload({
        gross: { ...slot(), codes: ['A'], standard_codes: ['B'] } as never,
      }),
    )!
    const g = n.slots!.gross as Record<string, unknown>
    expect(g.codes).toEqual(['A'])
    expect(g.standard_codes).toEqual(['B'])
  })

  it('🔴 不归一会让共享工厂把有数据的槽误判成无此科目（反向自检）', () => {
    // 后端槽载荷没有 codes / standard_codes 字段
    const raw = slot() as Record<string, unknown>
    expect(raw.codes).toBeUndefined()
    expect(raw.standard_codes).toBeUndefined()
    // 归一后两者都有 → 工厂的 codes 双空判定不会误触发
    const n = normalizeDSlots(payload({ gross: slot() }))!
    const g = n.slots!.gross as Record<string, unknown>
    expect((g.codes as string[]).length).toBeGreaterThan(0)
  })

  it('无 slots 时原样返回，不炸', () => {
    expect(normalizeDSlots({} as DTbSourceCodes)).toEqual({})
    expect(normalizeDSlots(null)).toBeNull()
  })
})

// ───────────────── 口径分类 ─────────────────

describe('损益类与负债类分类', () => {
  it('只有 D4 是损益类（取本期发生额）', () => {
    expect([...D_PL_CYCLES]).toEqual(['D4'])
    expect(isDPlCycle('D4')).toBe(true)
    expect(isDPlCycle('d4')).toBe(true)
    for (const wp of ['D1', 'D2', 'D3', 'D5', 'D6', 'D7']) {
      expect(isDPlCycle(wp), wp).toBe(false)
    }
  })

  it('取数口径中文标签', () => {
    expect(dCycleBasisLabel('D4')).toBe('本期发生额')
    expect(dCycleBasisLabel('D2')).toBe('期末余额')
  })

  it('D3/D7 是负债类，且与后端 is_liability 一致', () => {
    expect([...D_LIABILITY_CYCLES].sort()).toEqual(['D3', 'D7'])
    for (const wp of ['D3', 'D7']) {
      expect(backendSpecBlock(RESOLVER_SRC, `${wp}_SPEC`)).toContain('is_liability=True')
    }
    for (const wp of ['D2', 'D5', 'D6']) {
      expect(backendSpecBlock(RESOLVER_SRC, `${wp}_SPEC`)).not.toContain('is_liability=True')
    }
  })
})
