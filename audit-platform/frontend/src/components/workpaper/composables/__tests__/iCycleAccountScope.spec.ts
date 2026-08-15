/**
 * I 循环科目口径单一真源守卫（Task 16, Property 2 / Requirements 9.1 / 2.3）
 *
 * 🔴 **本守卫读后端源码做交叉锁死，不在前端抄第二份字面量**。
 * 后端真源 = `backend/app/services/four_table/i_cycle_accounts.py`
 * （`I_CYCLE_ROW_CODES` / `I_CYCLE_SEGMENTS` / `SEGMENT_*`）。
 *
 * 为什么必须交叉锁死：改造前六个 `i{n}AccountScope.ts` 里 12 个报表行取值有 **11 个错**，
 * 而当时的守卫只校验「函数在有溯源时返回溯源值、无溯源时返回本文件自己的常量」——
 * 常量错了照样全绿（守卫把错值当基线锁死）。故本守卫一律拿后端源码当期望值。
 *
 * 覆盖：
 * - Property 26：行编码 / 段键 / 段中文名 / 兜底码 与后端逐项一致
 * - Property 27：运行态 `segments` 优先于兜底常量；字段名是 `standard`/`original`
 * - Property 28：「本项目无此科目」三态（未下发 / 下发但空 / 有码）
 * - Property 29：空兜底段绝不凭空造前缀（I3.impairment / I5.cost）
 * - Property 2 ：六个审定表 + 12 个披露 Tab 源码不得硬编码错误科目码
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

import {
  I_CYCLE_ACCOUNT_SPECS,
  I_SEGMENT_AMORTIZATION,
  I_SEGMENT_COST,
  I_SEGMENT_EXPENSE,
  I_SEGMENT_IMPAIRMENT,
  iCycleAccountAbsent,
  iCycleAccountCode,
  iCycleMatchesSegment,
  iCycleOriginalCodes,
  iCyclePrimarySegment,
  iCycleQueryCodes,
  iCycleRowCode,
  iCycleSegment,
  iCycleSegmentLabels,
  iCycleSegmentOrder,
  iCycleSpec,
  type ICycleWpCode,
} from '../iCycleAccountScope'

// ─── 仓库根：双哨兵向上查找（禁写死回退级数） ────────────────────────────────

function findRepoRoot(start: string): string {
  let cur = start
  for (let i = 0; i < 12; i++) {
    if (existsSync(join(cur, 'backend')) && existsSync(join(cur, 'audit-platform'))) return cur
    const parent = dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  throw new Error('找不到仓库根（缺 backend/ + audit-platform/ 双哨兵）')
}

const REPO_ROOT = findRepoRoot(__dirname)
const BE_ACCOUNTS = resolve(REPO_ROOT, 'backend/app/services/four_table/i_cycle_accounts.py')

const WP_CODES: ICycleWpCode[] = ['I1', 'I2', 'I3', 'I4', 'I5', 'I6']

/** 后端源码（一次读取，多处解析） */
const beSrc = readFileSync(BE_ACCOUNTS, 'utf-8')

/**
 * 抽出后端 `I_CYCLE_ROW_CODES`：`"I1": {"listed": "BS-032", "soe": "BS-032"}`。
 *
 * 用花括号配对截块（不用固定字符窗口）：先定位赋值号后的第一个 `{`，再配对到闭合。
 */
function beRowCodes(): Record<string, { listed: string; soe: string }> {
  const anchor = 'I_CYCLE_ROW_CODES: dict[str, dict[str, str]] = '
  const at = beSrc.indexOf(anchor)
  expect(at, `后端锚点 ${anchor} 未命中 → 守卫失效（可能已改名）`).toBeGreaterThan(-1)
  const open = beSrc.indexOf('{', at + anchor.length)
  let depth = 0
  let end = -1
  for (let i = open; i < beSrc.length; i++) {
    if (beSrc[i] === '{') depth++
    else if (beSrc[i] === '}') {
      depth--
      if (depth === 0) { end = i; break }
    }
  }
  expect(end, '花括号未配对 → 守卫解析失败').toBeGreaterThan(open)
  const block = beSrc.slice(open, end + 1)
  const out: Record<string, { listed: string; soe: string }> = {}
  const re = /"(I[1-6])":\s*\{\s*"listed":\s*"([^"]*)"\s*,\s*"soe":\s*"([^"]*)"\s*\}/g
  let m: RegExpExecArray | null
  while ((m = re.exec(block)) !== null) out[m[1]] = { listed: m[2], soe: m[3] }
  return out
}

/**
 * 抽出后端 `I_CYCLE_SEGMENTS` 的每段 `(segment常量名, label, fallback元组)`。
 *
 * 后端形如：
 * ```python
 * "I1": (
 *     ISegmentSpec(
 *         segment=SEGMENT_COST,
 *         label="账面原值",
 *         fallback=("1701",),
 *         ...
 * ```
 */
interface BeSegment { segment: string; label: string; fallback: string[]; absolute: boolean; occurrence: boolean }

function beSegments(): Record<string, BeSegment[]> {
  const anchor = 'I_CYCLE_SEGMENTS: dict[str, tuple[ISegmentSpec, ...]] = '
  const at = beSrc.indexOf(anchor)
  expect(at, `后端锚点 ${anchor} 未命中 → 守卫失效`).toBeGreaterThan(-1)
  const open = beSrc.indexOf('{', at + anchor.length)
  let depth = 0
  let end = -1
  for (let i = open; i < beSrc.length; i++) {
    if (beSrc[i] === '{') depth++
    else if (beSrc[i] === '}') {
      depth--
      if (depth === 0) { end = i; break }
    }
  }
  const block = beSrc.slice(open, end + 1)

  // 段键常量名 → 实际值（后端 `SEGMENT_COST = "cost"`）
  const constMap: Record<string, string> = {}
  const cre = /^(SEGMENT_[A-Z_]+)\s*=\s*"([^"]+)"/gm
  let cm: RegExpExecArray | null
  while ((cm = cre.exec(beSrc)) !== null) constMap[cm[1]] = cm[2]

  const out: Record<string, BeSegment[]> = {}
  // 逐循环切块：`"I1": (` 到下一个 `"Ix": (` 或块尾
  const cycleRe = /"(I[1-6])":\s*\(/g
  const starts: Array<[string, number]> = []
  let m: RegExpExecArray | null
  while ((m = cycleRe.exec(block)) !== null) starts.push([m[1], m.index])
  for (let i = 0; i < starts.length; i++) {
    const [code, from] = starts[i]
    const to = i + 1 < starts.length ? starts[i + 1][1] : block.length
    const chunk = block.slice(from, to)
    const segs: BeSegment[] = []
    // 每个 ISegmentSpec(...) 一段
    const specRe = /ISegmentSpec\(([\s\S]*?)\n\s{8}\)/g
    let sm: RegExpExecArray | null
    while ((sm = specRe.exec(chunk)) !== null) {
      const body = sm[1]
      const segM = /segment=(SEGMENT_[A-Z_]+)/.exec(body)
      const labM = /label="([^"]*)"/.exec(body)
      const fbM = /fallback=\(([^)]*)\)/.exec(body)
      const fallback = fbM
        ? (fbM[1].match(/"([^"]+)"/g) || []).map((s) => s.replace(/"/g, ''))
        : []
      segs.push({
        segment: segM ? constMap[segM[1]] || segM[1] : '',
        label: labM ? labM[1] : '',
        fallback,
        absolute: /absolute=True/.test(body),
        occurrence: /occurrence=True/.test(body),
      })
    }
    out[code] = segs
  }
  return out
}

const BE_ROW_CODES = beRowCodes()
const BE_SEGMENTS = beSegments()

// ═══════════════════════════════════════════════════════════════════
// 反向自检：解析器本身必须真的抽到东西（否则下面全部空转恒绿）
// ═══════════════════════════════════════════════════════════════════

describe('反向自检 — 后端源码解析有效', () => {
  it('后端文件存在且非空', () => {
    expect(existsSync(BE_ACCOUNTS), `后端真源不存在：${BE_ACCOUNTS}`).toBe(true)
    expect(beSrc.length).toBeGreaterThan(2000)
  })

  it('解析出 6 个循环的行编码，且形如 BS-xxx / IS-xxx', () => {
    expect(Object.keys(BE_ROW_CODES).sort()).toEqual([...WP_CODES])
    for (const code of WP_CODES) {
      expect(BE_ROW_CODES[code].listed, `${code} listed 行编码为空`).toMatch(/^(BS|IS)-\d+$/)
      expect(BE_ROW_CODES[code].soe, `${code} soe 行编码为空`).toMatch(/^(BS|IS)-\d+$/)
    }
  })

  it('解析出 6 个循环的段声明，段键均为已知常量值', () => {
    expect(Object.keys(BE_SEGMENTS).sort()).toEqual([...WP_CODES])
    const known = [I_SEGMENT_COST, I_SEGMENT_AMORTIZATION, I_SEGMENT_IMPAIRMENT, I_SEGMENT_EXPENSE]
    for (const code of WP_CODES) {
      expect(BE_SEGMENTS[code].length, `${code} 段声明为空 ⇒ 解析器失效`).toBeGreaterThan(0)
      for (const s of BE_SEGMENTS[code]) {
        expect(known, `${code} 段键 ${s.segment} 不是已知常量（解析器可能没展开 SEGMENT_*）`)
          .toContain(s.segment)
        expect(s.label, `${code}.${s.segment} 段中文名为空 ⇒ 解析器失效`).toBeTruthy()
      }
    }
  })

  it('后端段数分布 = I1:3 / I3:2 / 其余各 1（结构基线）', () => {
    const counts = Object.fromEntries(WP_CODES.map((c) => [c, BE_SEGMENTS[c].length]))
    expect(counts).toEqual({ I1: 3, I2: 1, I3: 2, I4: 1, I5: 1, I6: 1 })
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 26：前端声明 ≡ 后端真源（逐项交叉锁死）
// ═══════════════════════════════════════════════════════════════════

describe('Property 26 — 前端声明与后端 i_cycle_accounts.py 逐项一致', () => {
  it.each(WP_CODES)('%s 报表行编码 listed/soe 均等于后端', (code) => {
    const fe = I_CYCLE_ACCOUNT_SPECS[code]
    expect(fe.rowCode.listed, `${code} listed 行编码与后端不一致（改造前 11/12 个是错的）`)
      .toBe(BE_ROW_CODES[code].listed)
    expect(fe.rowCode.soe, `${code} soe 行编码与后端不一致`).toBe(BE_ROW_CODES[code].soe)
  })

  it('I 类四准则同码（listed === soe），防被按 J1 范式「修正」成两码', () => {
    for (const code of WP_CODES) {
      expect(BE_ROW_CODES[code].listed, `后端 ${code} 两侧应同码`).toBe(BE_ROW_CODES[code].soe)
      const fe = I_CYCLE_ACCOUNT_SPECS[code]
      expect(fe.rowCode.listed, `前端 ${code} 两侧应同码`).toBe(fe.rowCode.soe)
    }
  })

  it.each(WP_CODES)('%s 段键与顺序等于后端声明顺序（= 审定表展示顺序）', (code) => {
    expect(iCycleSegmentOrder(code)).toEqual(BE_SEGMENTS[code].map((s) => s.segment))
  })

  it.each(WP_CODES)('%s 段中文名逐字等于后端 label（源模板层标题）', (code) => {
    const feLabels = iCycleSegmentLabels(code)
    for (const s of BE_SEGMENTS[code]) {
      expect(feLabels[s.segment], `${code}.${s.segment} 段中文名与后端不一致`).toBe(s.label)
    }
  })

  it.each(WP_CODES)('%s 兜底码逐项等于后端 fallback（含空 tuple）', (code) => {
    const fe = I_CYCLE_ACCOUNT_SPECS[code]
    for (const be of BE_SEGMENTS[code]) {
      const feSeg = fe.segments.find((s) => s.segment === be.segment)!
      expect(feSeg, `${code} 缺段 ${be.segment}`).toBeDefined()
      expect([...feSeg.fallback], `${code}.${be.segment} 兜底码与后端不一致`).toEqual(be.fallback)
    }
  })

  it.each(WP_CODES)('%s 备抵/损益标记等于后端 absolute / occurrence', (code) => {
    const fe = I_CYCLE_ACCOUNT_SPECS[code]
    for (const be of BE_SEGMENTS[code]) {
      const feSeg = fe.segments.find((s) => s.segment === be.segment)!
      expect(!!feSeg.isProvision, `${code}.${be.segment} isProvision 与后端 absolute 不一致`)
        .toBe(be.absolute)
      expect(!!feSeg.isOccurrence, `${code}.${be.segment} isOccurrence 与后端 occurrence 不一致`)
        .toBe(be.occurrence)
    }
  })

  it('🔴 兜底码不得含实证不存在的码（1717 / 1911 / 6602 / 1712）', () => {
    const banned = ['1717', '1911', '6602', '1712']
    const bad: string[] = []
    for (const code of WP_CODES) {
      for (const s of I_CYCLE_ACCOUNT_SPECS[code].segments) {
        for (const f of s.fallback) {
          if (banned.includes(f)) bad.push(`${code}.${s.segment}=${f}`)
        }
      }
    }
    expect(bad, '1717/1911 全库不存在、6602 是管理费用、1712 不是 I 类科目').toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 27：运行态优先于兜底；字段名是 standard / original
// ═══════════════════════════════════════════════════════════════════

describe('Property 27 — render 下发值优先于兜底常量', () => {
  it('有 segments → 取下发的 standard（不是兜底码）', () => {
    const src = { segments: [{ segment: 'cost', standard: ['PRJ-1701-A'] }] }
    expect(iCycleQueryCodes(src, 'I1')).toEqual(['PRJ-1701-A'])
    expect(iCycleAccountCode(src, 'I1')).toBe('PRJ-1701-A')
  })

  it('I1 三段各自独立取下发值（二分 gross/provision 装不下三段）', () => {
    const src = {
      segments: [
        { segment: 'cost', standard: ['C1'] },
        { segment: 'amortization', standard: ['A1'] },
        { segment: 'impairment', standard: ['M1'] },
      ],
    }
    expect(iCycleQueryCodes(src, 'I1', 'cost')).toEqual(['C1'])
    expect(iCycleQueryCodes(src, 'I1', 'amortization')).toEqual(['A1'])
    expect(iCycleQueryCodes(src, 'I1', 'impairment')).toEqual(['M1'])
  })

  it('未指定段键 → 落到主段（segments[0]）', () => {
    expect(iCyclePrimarySegment('I1')).toBe('cost')
    expect(iCyclePrimarySegment('I6')).toBe('expense')
    const src = { segments: [{ segment: 'expense', standard: ['E9'] }] }
    expect(iCycleQueryCodes(src, 'I6')).toEqual(['E9'])
  })

  it('🔴 字段名必须是 standard/original —— 写成语义槽的 standard_codes 读不到', () => {
    const wrong = { segments: [{ segment: 'cost', standard_codes: ['X'] } as never] }
    // 用错字段名 ⇒ 退化到兜底码（这正是「静默读到 undefined」的表现）
    expect(iCycleQueryCodes(wrong, 'I1')).toEqual(['1701'])
  })

  it('originalCodes 优先 original，缺失时退回标准码集', () => {
    const withOrig = { segments: [{ segment: 'cost', standard: ['1701'], original: ['170101'] }] }
    expect(iCycleOriginalCodes(withOrig, 'I1')).toEqual(['170101'])
    const noOrig = { segments: [{ segment: 'cost', standard: ['1701'] }] }
    expect(iCycleOriginalCodes(noOrig, 'I1')).toEqual(['1701'])
  })

  it('render 未下发 → 回退兜底码（界面不空）', () => {
    expect(iCycleQueryCodes(null, 'I1')).toEqual(['1701'])
    expect(iCycleQueryCodes({}, 'I2')).toEqual(['1704'])
    expect(iCycleQueryCodes(undefined, 'I6')).toEqual(['6604'])
  })

  it('空白/空串码被过滤（不产出空前缀）', () => {
    const src = { segments: [{ segment: 'cost', standard: ['', '  ', '1701'] }] }
    expect(iCycleQueryCodes(src, 'I1')).toEqual(['1701'])
  })

  it('行编码按适用准则选边（soe* → soe 编号）', () => {
    for (const code of WP_CODES) {
      expect(iCycleRowCode(code, ['soe_standalone'])).toBe(BE_ROW_CODES[code].soe)
      expect(iCycleRowCode(code, ['listed_consolidated'])).toBe(BE_ROW_CODES[code].listed)
      expect(iCycleRowCode(code, null)).toBe(BE_ROW_CODES[code].listed)
    }
  })

  it('未知 wp_code 一律安全返回空，不抛异常', () => {
    expect(iCycleSpec('I9')).toBeUndefined()
    expect(iCycleRowCode('I9')).toBe('')
    expect(iCycleQueryCodes(null, 'I9')).toEqual([])
    expect(iCycleSegment(null, 'I9')).toBeNull()
    expect(iCycleSegmentOrder('I9')).toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 28：「本项目无此科目」三态
// ═══════════════════════════════════════════════════════════════════

describe('Property 28 — 「无此科目」与「余额为 0」必须区分', () => {
  it('render 未下发 ≠ 无此科目（返 false，表示未知）', () => {
    expect(iCycleAccountAbsent(null, 'I1'), 'render 未下发被误判成「无此科目」').toBe(false)
    expect(iCycleAccountAbsent({}, 'I3', 'impairment')).toBe(false)
    expect(iCycleAccountAbsent({ segments: [] }, 'I5')).toBe(false)
  })

  it('下发了该段但两个码集皆空 → true（后端宁缺勿造）', () => {
    const src = { segments: [{ segment: 'impairment', standard: [], original: [] }] }
    expect(iCycleAccountAbsent(src, 'I3', 'impairment')).toBe(true)
  })

  it('下发了码 → false（有科目，金额 0 是另一回事）', () => {
    const src = { segments: [{ segment: 'cost', standard: ['1701'] }] }
    expect(iCycleAccountAbsent(src, 'I1')).toBe(false)
  })

  it('只有 original 没有 standard 也算「有科目」', () => {
    const src = { segments: [{ segment: 'cost', standard: [], original: ['170101'] }] }
    expect(iCycleAccountAbsent(src, 'I1')).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 29：空兜底段绝不凭空造前缀
// ═══════════════════════════════════════════════════════════════════

describe('Property 29 — 无兜底码声明的段返空，不造假前缀', () => {
  it('后端确实把 I3.impairment 与 I5.cost 声明为空 tuple（锚点有效）', () => {
    const i3imp = BE_SEGMENTS.I3.find((s) => s.segment === 'impairment')!
    const i5cost = BE_SEGMENTS.I5.find((s) => s.segment === 'cost')!
    expect(i3imp.fallback, '后端 I3 减值段兜底不再为空 ⇒ 本守卫需重新对账').toEqual([])
    expect(i5cost.fallback, '后端 I5 原值段兜底不再为空 ⇒ 本守卫需重新对账').toEqual([])
  })

  it('I3 商誉减值准备：render 未下发 → 空数组（account_chart 无此科目）', () => {
    expect(iCycleQueryCodes(null, 'I3', 'impairment')).toEqual([])
    expect(iCycleAccountCode(null, 'I3', 'impairment')).toBe('')
  })

  it('I5 其他非流动资产：render 未下发 → 空数组（1911 全库不存在）', () => {
    expect(iCycleQueryCodes(null, 'I5')).toEqual([])
    expect(iCycleOriginalCodes({}, 'I5')).toEqual([])
    expect(iCycleAccountCode(undefined, 'I5')).toBe('')
  })

  it('空口径下 matchesSegment 恒 false（不会误命中任何码）', () => {
    expect(iCycleMatchesSegment('1911', null, 'I5')).toBe(false)
    expect(iCycleMatchesSegment('1711', null, 'I3', 'impairment')).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════
// matchesSegment 点号边界
// ═══════════════════════════════════════════════════════════════════

describe('iCycleMatchesSegment — 严格点号边界', () => {
  const src = { segments: [{ segment: 'cost', standard: ['1701'], original: ['1701'] }] }

  it('等值命中 / 点号子科目命中', () => {
    expect(iCycleMatchesSegment('1701', src, 'I1')).toBe(true)
    expect(iCycleMatchesSegment('1701.01', src, 'I1')).toBe(true)
  })

  it('🔴 无点号的更长码不得命中（17010 是另一个科目）', () => {
    expect(iCycleMatchesSegment('17010', src, 'I1')).toBe(false)
    expect(iCycleMatchesSegment('170101', src, 'I1')).toBe(false)
  })

  it('空码 / 非字符串一律 false', () => {
    expect(iCycleMatchesSegment('', src, 'I1')).toBe(false)
    expect(iCycleMatchesSegment(null, src, 'I1')).toBe(false)
    expect(iCycleMatchesSegment(undefined, src, 'I1')).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 2：审定表 / 披露 Tab 不得硬编码错误科目码
// ═══════════════════════════════════════════════════════════════════

describe('Property 2 — I 类审定表/披露 Tab 禁止硬编码错误科目码', () => {
  const WORKPAPER_DIR = resolve(__dirname, '..', '..')

  function findFile(dir: string, name: string): string[] {
    const out: string[] = []
    let entries: ReturnType<typeof readdirSync>
    try {
      entries = readdirSync(dir, { withFileTypes: true }) as never
    } catch {
      return out
    }
    for (const e of entries as Array<{ name: string; isDirectory(): boolean; isFile(): boolean }>) {
      const full = join(dir, e.name)
      if (e.isDirectory() && !e.name.startsWith('.') && e.name !== 'node_modules') {
        out.push(...findFile(full, name))
      } else if (e.isFile() && e.name === name) {
        out.push(full)
      }
    }
    return out
  }

  /** 去注释（防「注释里提到 1717」被误判） */
  function stripComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
  }

  const targets: string[] = []
  for (const n of [1, 2, 3, 4, 5, 6]) {
    for (const f of [
      `I${n}TabAdjudication.vue`,
      `I${n}TabDisclosureListed.vue`,
      `I${n}TabDisclosureSoe.vue`,
    ]) {
      targets.push(...findFile(WORKPAPER_DIR, f))
    }
  }

  it('反向自检：至少找到 18 个 I 类 Tab 文件（找不到=扫了空气）', () => {
    expect(targets.length, `只找到 ${targets.length} 个 ⇒ 路径或命名变了，守卫在空转`)
      .toBeGreaterThanOrEqual(18)
  })

  it('去注释后不得出现实证不存在/错误的科目码字面量', () => {
    // 1717 / 1911 全库两张科目表都不存在；6602 是管理费用（研发费用是 6604）
    const banned = [/['"]1717['"]/, /['"]1911['"]/, /['"]6602['"]/, /['"]1712['"]/]
    const bad: string[] = []
    for (const p of targets) {
      const cleaned = stripComments(readFileSync(p, 'utf-8'))
      for (const re of banned) {
        if (re.test(cleaned)) bad.push(`${p.split(/[\\/]/).pop()}: ${re.source}`)
      }
    }
    expect(bad, '硬编码错误科目码 ⇒ 取数恒空或取到别的科目族').toEqual([])
  })
})

// ═══════════════════════════════════════════════════════════════════
// Property 2（续）：溯源面板配置不得成为行编码的第三份副本
// ═══════════════════════════════════════════════════════════════════

describe('Property 2 — useICycleFourTableSource 的 fallbackRowCode 必须派生自单一真源', () => {
  const CONFIG_FILE = resolve(__dirname, '..', 'useICycleFourTableSource.ts')
  //  循环键取自被测真源自身的键集（不另抄一份 ['I1'..'I6']，抄了就是第 N 份副本）
  const CYCLES = Object.keys(I_CYCLE_ACCOUNT_SPECS) as ICycleWpCode[]

  /** 去注释（防注释里举例的旧错码被判成硬编码） */
  function stripComments(src: string): string {
    return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
  }

  it('反向自检：配置文件存在且导出 getICycleSourceConfig（找不到=扫了空气）', () => {
    expect(existsSync(CONFIG_FILE), `${CONFIG_FILE} 不存在 ⇒ 路径变了，守卫在空转`).toBe(true)
    const src = readFileSync(CONFIG_FILE, 'utf-8')
    expect(src).toContain('export function getICycleSourceConfig')
  })

  it('🔴 去注释后不得出现 BS-/IS- 行编码字面量（否则又是一份可回退的副本）', () => {
    const cleaned = stripComments(readFileSync(CONFIG_FILE, 'utf-8'))
    const hits = cleaned.match(/['"](?:BS|IS)-\d+['"]/g) || []
    expect(
      hits,
      '行编码只能由 iCycleRowCode() 派生 —— 写字面量会让它成为第三份真源，' +
        '而改造前那份 6 个里 5 个是错位旧值（直接渲染进溯源面板「报表行」tag）',
    ).toEqual([])
  })

  it('必须 import iCycleRowCode（结构性证明派生关系真实存在，非注释承诺）', () => {
    const cleaned = stripComments(readFileSync(CONFIG_FILE, 'utf-8'))
    expect(cleaned).toMatch(/import\s*\{[^}]*\biCycleRowCode\b[^}]*\}\s*from\s*['"]\.\/iCycleAccountScope['"]/)
  })

  it('六循环 fallbackRowCode 逐项等于 iCycleRowCode（行为级锁死，不看字符串）', async () => {
    const { getICycleSourceConfig } = await import('../useICycleFourTableSource')
    for (const wp of CYCLES) {
      expect(getICycleSourceConfig(wp).fallbackRowCode, `${wp} 溯源面板行编码与真源不一致`)
        .toBe(iCycleRowCode(wp))
    }
  })

  it('未知 wp_code 时文案与行编码派生自同一 effective key（不得自相矛盾）', async () => {
    const { getICycleSourceConfig } = await import('../useICycleFourTableSource')
    const unknown = getICycleSourceConfig('IX')
    const i4 = getICycleSourceConfig('I4')
    expect(unknown.grossLabel).toBe(i4.grossLabel)
    expect(unknown.fallbackRowCode).toBe(i4.fallbackRowCode)
  })

  it('六循环行编码均非空且形如 BS-xxx / IS-xxx（防派生成空串静默失效）', async () => {
    const { getICycleSourceConfig } = await import('../useICycleFourTableSource')
    for (const wp of CYCLES) {
      expect(getICycleSourceConfig(wp).fallbackRowCode).toMatch(/^(?:BS|IS)-\d+$/)
    }
  })
})
