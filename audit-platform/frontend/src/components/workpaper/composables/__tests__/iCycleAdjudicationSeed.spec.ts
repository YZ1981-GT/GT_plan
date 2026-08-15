/**
 * iCycleAdjudicationSeed 守卫（Task 17 / Requirements 9.2, 9.3, 9.4）
 *
 * 🔴 **本守卫读后端源码 + 各 composable 源码做交叉锁死，不在测试里抄第二份字面量。**
 *
 * 三类锁死：
 * 1. 段键与后端 `i1_asset_categories.SEGMENT_*` / `i_cycle_accounts` 逐字一致
 *    （`amortization` → `amort` 的翻译必须存在，否则累计摊销段静默丢失）
 * 2. 声明的列字段名 / 标签字段名必须在对应 composable 的行模型里真实存在
 *    （传不存在的字段 = 静默不写入，四层检查都查不出 —— 平台已记铁律）
 * 3. 「无此科目 ≠ 为 0」/「未命中不兜底」两条口径的行为级断言
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'

import {
  I1_SEGMENT_TO_BLOCK,
  I_CYCLE_SEED_SPECS,
  buildICycleSeedCells,
  extractICyclePrefill,
  iCycleSeedSpec,
  iSegmentToBlock,
  normalizeSeedLabel,
  type IAdjudicationPrefill,
  type ISeedExistingRow,
} from '../iCycleAdjudicationSeed'
import { planAdjudicationPrefill, resolveAdjPrefillWrites } from '../shared/adjudicationPrefillPlan'
import { I_CYCLE_ACCOUNT_SPECS, type ICycleWpCode } from '../iCycleAccountScope'

// ─── 仓库根：双哨兵向上查找（禁写死回退级数） ────────────────────────────────

function findRepoRoot(start: string): string {
  let cur = resolve(start)
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(cur, 'backend')) && existsSync(join(cur, 'audit-platform'))) return cur
    const up = dirname(cur)
    if (up === cur) break
    cur = up
  }
  throw new Error(`未找到仓库根（双哨兵 backend/ + audit-platform/），起点 ${start}`)
}

const REPO_ROOT = findRepoRoot(__dirname)
const BACKEND = join(REPO_ROOT, 'backend', 'app', 'services', 'four_table')
const COMPOSABLES = resolve(__dirname, '..')

const CYCLES = Object.keys(I_CYCLE_SEED_SPECS) as ICycleWpCode[]

/** 去注释（TS/JS 行注释与块注释） */
function stripTs(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(?<![:'"\w])\/\/[^\n]*/g, '')
}

/** 去 Python 注释与 docstring */
function stripPy(src: string): string {
  let out = src.replace(/"""[\s\S]*?"""/g, '""').replace(/'''[\s\S]*?'''/g, '""')
  out = out.replace(/^\s*#[^\n]*/gm, '')
  return out
}

// ═══════════════════════════════════════════════════════════════════
// 反向自检：源文件可读（找不到 = 后续断言全在空转）
// ═══════════════════════════════════════════════════════════════════

describe('反向自检 — 交叉锁死的源文件均可读', () => {
  it('后端 i1_asset_categories.py 存在且含三个 SEGMENT_* 常量', () => {
    const p = join(BACKEND, 'i1_asset_categories.py')
    expect(existsSync(p), `${p} 不存在`).toBe(true)
    const src = stripPy(readFileSync(p, 'utf-8'))
    for (const name of ['SEGMENT_COST', 'SEGMENT_AMORTIZATION', 'SEGMENT_IMPAIRMENT']) {
      expect(src, `后端缺 ${name}`).toMatch(new RegExp(`${name}\\s*=\\s*"`))
    }
  })

  it('后端 i_cycle_prefill.py 存在且产 mode/segments/unmapped 三键', () => {
    const p = join(BACKEND, 'i_cycle_prefill.py')
    expect(existsSync(p)).toBe(true)
    const src = stripPy(readFileSync(p, 'utf-8'))
    expect(src).toContain('"mode"')
    expect(src).toContain('"segments"')
    expect(src).toContain('"unmapped"')
    // 两种 mode 都得在
    expect(src).toContain('"category"')
    expect(src).toContain('"leaf"')
  })

  it('六个审定表 composable 均可读', () => {
    for (const wp of CYCLES) {
      const p = join(COMPOSABLES, `use${wp}Adjudication.ts`)
      expect(existsSync(p), `${p} 不存在 ⇒ 字段名锁死在空转`).toBe(true)
    }
  })

  it('声明覆盖六个循环，且与 iCycleAccountScope 的循环集一致', () => {
    expect(CYCLES.length).toBe(6)
    expect(CYCLES.slice().sort()).toEqual(Object.keys(I_CYCLE_ACCOUNT_SPECS).slice().sort())
  })
})

// ═══════════════════════════════════════════════════════════════════
// 段键与后端逐字一致 + amortization→amort 翻译
// ═══════════════════════════════════════════════════════════════════

describe('段键与后端交叉锁死', () => {
  const py = stripPy(readFileSync(join(BACKEND, 'i1_asset_categories.py'), 'utf-8'))

  function backendSegment(name: string): string {
    const m = py.match(new RegExp(`${name}\\s*=\\s*"([^"]+)"`))
    if (!m) throw new Error(`后端未声明 ${name}`)
    return m[1]
  }

  it('后端段键实测值 = cost / amortization / impairment（锚点有效性）', () => {
    expect(backendSegment('SEGMENT_COST')).toBe('cost')
    expect(backendSegment('SEGMENT_AMORTIZATION')).toBe('amortization')
    expect(backendSegment('SEGMENT_IMPAIRMENT')).toBe('impairment')
  })

  it('🔴 翻译表的键 = 后端段键（不是前端 block 键）', () => {
    expect(Object.keys(I1_SEGMENT_TO_BLOCK).slice().sort()).toEqual(
      ['amortization', 'cost', 'impairment'],
    )
  })

  it('🔴 amortization 必须翻译成 amort —— 不翻译则累计摊销段整段静默丢失', () => {
    expect(iSegmentToBlock('I1', 'amortization')).toBe('amort')
    // 前端 I1BlockType 实测值（读 composable 源码，不抄字面量）
    const src = stripTs(readFileSync(join(COMPOSABLES, 'useI1Adjudication.ts'), 'utf-8'))
    const m = src.match(/I1BlockType\s*=\s*([^\n]+)/)
    expect(m, '未找到 I1BlockType 声明 ⇒ 锚点失效').toBeTruthy()
    const declared = m![1]
    for (const block of Object.values(I1_SEGMENT_TO_BLOCK)) {
      expect(declared, `I1BlockType 不含 '${block}'`).toContain(`'${block}'`)
    }
    // 反向：不得出现「后端段键原样当 block 用」
    expect(declared).not.toContain("'amortization'")
  })

  it('非 I1 循环无 block 概念（返 undefined，不误落 I1 的 block）', () => {
    for (const wp of CYCLES.filter((c) => c !== 'I1')) {
      for (const slot of I_CYCLE_SEED_SPECS[wp].slots) {
        expect(iSegmentToBlock(wp, slot.segment)).toBeUndefined()
      }
    }
  })

  it('每个循环声明的段键 ⊆ iCycleAccountScope 该循环的段键集（防声明漂移）', () => {
    for (const wp of CYCLES) {
      const known = new Set(I_CYCLE_ACCOUNT_SPECS[wp].segments.map((s) => s.segment))
      for (const slot of I_CYCLE_SEED_SPECS[wp].slots) {
        expect(known.has(slot.segment), `${wp} 声明了未知段键 ${slot.segment}`).toBe(true)
      }
    }
  })

  it('每个循环的段数与顺序 == iCycleAccountScope 声明（审定表展示顺序）', () => {
    for (const wp of CYCLES) {
      expect(
        I_CYCLE_SEED_SPECS[wp].slots.map((s) => s.segment),
        `${wp} 段顺序与科目口径真源不一致`,
      ).toEqual(I_CYCLE_ACCOUNT_SPECS[wp].segments.map((s) => s.segment))
    }
  })
})

// ═══════════════════════════════════════════════════════════════════
// 列字段名 / 标签字段名必须真实存在
// ═══════════════════════════════════════════════════════════════════

describe('列字段名与行模型交叉锁死（传不存在的字段 = 静默不写入）', () => {
  /** 读该循环相关源码（composable + 同名 model 文件，若存在） */
  function modelSource(wp: ICycleWpCode): string {
    let merged = stripTs(readFileSync(join(COMPOSABLES, `use${wp}Adjudication.ts`), 'utf-8'))
    const model = join(COMPOSABLES, `${wp.toLowerCase()}AdjudicationModel.ts`)
    if (existsSync(model)) merged += stripTs(readFileSync(model, 'utf-8'))
    return merged
  }

  /** 字段名是否以「声明 / 属性访问 / 索引」形态出现 */
  function hasField(src: string, field: string): boolean {
    const esc = field.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    return new RegExp(`(?:^|[\\s{,;(])${esc}\\s*[?:]|\\.${esc}\\b|\\['${esc}'\\]`, 'm').test(src)
  }

  for (const wp of CYCLES) {
    it(`${wp} 的 labelField 与全部列字段在行模型里真实存在`, () => {
      const spec = I_CYCLE_SEED_SPECS[wp]
      const src = modelSource(wp)
      expect(hasField(src, spec.labelField), `${wp} labelField=${spec.labelField} 不在行模型里`).toBe(true)
      for (const slot of spec.slots) {
        expect(
          hasField(src, slot.closingField),
          `${wp}/${slot.segment} closingField=${slot.closingField} 不在行模型里`,
        ).toBe(true)
        if (slot.openingField) {
          expect(
            hasField(src, slot.openingField),
            `${wp}/${slot.segment} openingField=${slot.openingField} 不在行模型里`,
          ).toBe(true)
        }
      }
    })
  }

  // ─────────────────────────────────────────────────────────────────────────
  // 🔴 强判据：labelField 必须 == 该审定表 SFC 既有 `bringInRows` 里的行标签字段
  //
  // 上面那条「字段名在行模型里存在」是**弱判据** —— 2026-08-12 实测踩到：
  // I3 的行标签是 `investee`，但把 labelField 误写成 `projectName` 时守卫照样绿，
  // 因为 `projectName` 确实出现在 `normalizeI3AdjudicationRow` 的**读取兼容别名**里
  // （`raw?.investee || raw?.projectName`）。归一后的行上只有 `investee`，
  // 于是全部行标签取空串 → 每行都匹配不上 → 整循环带入静默失效。
  //
  // `bringInRows` 的 `name: r.X` 是**已在生产中跑通**的行标签字段（「带入调整」靠它
  // 显示行名），拿它当期望值即可把「哪个字段才是标签」锁死，而不只是「字段存在」。
  // ─────────────────────────────────────────────────────────────────────────
  describe('labelField == SFC 既有 bringInRows 的行标签字段（强判据）', () => {
    const SFC: Record<ICycleWpCode, string> = {
      I1: join(COMPOSABLES, '..', 'i1', 'core', 'I1TabAdjudication.vue'),
      I2: join(COMPOSABLES, '..', 'i2', 'core', 'I2TabAdjudication.vue'),
      I3: join(COMPOSABLES, '..', 'i3', 'core', 'I3TabAdjudication.vue'),
      I4: join(COMPOSABLES, '..', 'i4', 'core', 'I4TabAdjudication.vue'),
      I5: join(COMPOSABLES, '..', 'i5', 'core', 'I5TabAdjudication.vue'),
      I6: join(COMPOSABLES, '..', 'i6', 'core', 'I6TabAdjudication.vue'),
    }

    /** 从 SFC 抽 `bringInRows` 里的 `name: r.X` 字段名（X 可含中文） */
    function bringInLabelField(wp: ICycleWpCode): string | null {
      const src = stripTs(readFileSync(SFC[wp], 'utf-8'))
      const m = src.match(/name:\s*r\.([A-Za-z_$\u4e00-\u9fa5][\w$\u4e00-\u9fa5]*)/)
      return m ? m[1] : null
    }

    it('反向自检：六个 SFC 都能抽出 bringInRows 的行标签字段（抽不到=判据空转）', () => {
      const missing = CYCLES.filter((wp) => !bringInLabelField(wp))
      expect(missing, `以下循环抽不到 name: r.X ⇒ 强判据对它们空转：${missing}`).toEqual([])
    })

    for (const wp of CYCLES) {
      it(`${wp} labelField 与 bringInRows 一致`, () => {
        const expected = bringInLabelField(wp)
        expect(expected, `${wp} 抽不到行标签字段`).toBeTruthy()
        expect(
          I_CYCLE_SEED_SPECS[wp].labelField,
          `${wp} labelField 写成 ${I_CYCLE_SEED_SPECS[wp].labelField}，`
            + `而该审定表的行标签字段实为 ${expected} ⇒ 全部行标签取空串、带入静默失效`,
        ).toBe(expected)
      })
    }

    it('🔴 I3 的行标签是 investee（不是 projectName —— 后者只是读取兼容别名）', () => {
      expect(I_CYCLE_SEED_SPECS.I3.labelField).toBe('investee')
    })
  })

  it('反向自检：hasField 对确实不存在的字段必须返 false', () => {
    const src = modelSource('I4')
    expect(hasField(src, 'unadjusted')).toBe(true)
    for (const fake of ['zzzNotAField', 'unadjustedXyz', '完全不存在的字段']) {
      expect(hasField(src, fake), `hasField 误判 ${fake} 存在 ⇒ 判据空转`).toBe(false)
    }
  })

  it('I6 用中文字段名（本期未审 / 类别）—— 不得被「英文化」成不存在的字段', () => {
    expect(I_CYCLE_SEED_SPECS.I6.labelField).toBe('类别')
    expect(I_CYCLE_SEED_SPECS.I6.slots[0].closingField).toBe('本期未审')
  })

  it('只有 I2 声明期初列（双期结构），其余单期', () => {
    const withOpening = CYCLES.filter((wp) =>
      I_CYCLE_SEED_SPECS[wp].slots.some((s) => !!s.openingField),
    )
    expect(withOpening).toEqual(['I2'])
  })

  it('每个循环 defaults 恒为空数组（宁缺勿造，正向断言而非「源码没这字段」）', () => {
    for (const wp of CYCLES) {
      expect(I_CYCLE_SEED_SPECS[wp].defaults, `${wp} defaults 非空 ⇒ 会兜底`).toEqual([])
    }
  })
})

// ═══════════════════════════════════════════════════════════════════
// 行为：无此科目 ≠ 为 0 / 未命中不兜底 / 幂等
// ═══════════════════════════════════════════════════════════════════

function prefill(segments: IAdjudicationPrefill['segments'], unmapped: string[] = []): IAdjudicationPrefill {
  return { mode: 'leaf', segments, unmapped }
}

function row(label: string, rowId = `r-${label}`): ISeedExistingRow {
  return { rowId, label }
}

describe('「本项目无此科目」与「为 0」必须区分', () => {
  it('render 未下发（null）→ 全部段进 absentSlots，cells 为空（不写 0）', () => {
    const res = buildICycleSeedCells(null, 'I3', [row('商誉A')])
    expect(res.cells).toEqual([])
    expect(res.absentSlots.map((s) => s.slotKey)).toEqual(['cost', 'impairment'])
  })

  it('段存在但 rows 为空 → 该段进 absentSlots', () => {
    const res = buildICycleSeedCells(
      prefill([{ segment: 'cost', label: '商誉账面原值', rows: [] }]),
      'I3',
      [row('商誉A')],
    )
    expect(res.absentSlots.map((s) => s.slotKey).sort()).toEqual(['cost', 'impairment'])
  })

  it('I3 减值段缺失时只有它进 absentSlots，原值段照常出格', () => {
    const res = buildICycleSeedCells(
      prefill([
        {
          segment: 'cost',
          label: '商誉账面原值',
          rows: [{ key: '1711', label: '商誉A', codes: ['1711.01'], opening: 1, closing: 2, increase: 1, decrease: 0 }],
        },
      ]),
      'I3',
      [row('商誉A')],
    )
    expect(res.absentSlots.map((s) => s.slotKey)).toEqual(['impairment'])
    expect(res.cells).toHaveLength(1)
    expect(res.cells[0]).toMatchObject({ rowKey: 'r-商誉A', field: 'unadjusted', amount: 2 })
  })

  it('I5 恒无标准科目（1911 全库不存在）→ 未下发时如实进 absentSlots', () => {
    const res = buildICycleSeedCells(null, 'I5', [row('项目一')])
    expect(res.absentSlots).toEqual([{ slotKey: 'cost', label: '其他非流动资产' }])
    expect(res.cells).toEqual([])
  })

  it('金额确实为 0（有行有码）→ 出格且 amount=0，不进 absentSlots', () => {
    const res = buildICycleSeedCells(
      prefill([
        {
          segment: 'cost',
          label: '长期待摊费用',
          rows: [{ key: '1801', label: '装修费', codes: ['1801.01'], opening: 0, closing: 0, increase: 0, decrease: 0 }],
        },
      ]),
      'I4',
      [row('装修费')],
    )
    expect(res.absentSlots).toEqual([])
    expect(res.cells).toHaveLength(1)
    expect(res.cells[0].amount).toBe(0)
  })
})

describe('未命中现有行不兜底', () => {
  it('后端有行但前端无同名行 → 进 unclassified，不产 cell、不塞「其他」', () => {
    const res = buildICycleSeedCells(
      prefill([
        {
          segment: 'cost',
          label: '长期待摊费用',
          rows: [
            { key: '1801.01', label: '装修费', codes: ['1801.01'], opening: 1, closing: 2, increase: 1, decrease: 0 },
            { key: '1801.99', label: '未知项', codes: ['1801.99'], opening: 3, closing: 4, increase: 1, decrease: 0 },
          ],
        },
      ]),
      'I4',
      [row('装修费'), row('其他')],
    )
    expect(res.cells.map((c) => c.label)).toEqual(['装修费'])
    expect(res.unclassified).toHaveLength(1)
    expect(res.unclassified[0]).toMatchObject({ code: '1801.99', amount: 4, opening: 3 })
    // 绝不落到「其他」行
    expect(res.cells.some((c) => c.rowKey === 'r-其他')).toBe(false)
  })

  it('prefill.unmapped 的科目码一并进 unclassified', () => {
    const res = buildICycleSeedCells(prefill([], ['1701.88', '1701.99']), 'I4', [row('装修费')])
    expect(res.unclassified.map((u) => u.code)).toEqual(['1701.88', '1701.99'])
  })

  it('空串 / 空白 unmapped 项被过滤（不产空科目码条目）', () => {
    const res = buildICycleSeedCells(prefill([], ['', '  ', '1701.1']), 'I4', [row('装修费')])
    expect(res.unclassified.map((u) => u.code)).toEqual(['1701.1'])
  })
})

describe('标签匹配与归一化', () => {
  it('标签含空白也能匹配（源模板「项  目」双空格很常见）', () => {
    expect(normalizeSeedLabel('项  目')).toBe('项目')
    const res = buildICycleSeedCells(
      prefill([
        {
          segment: 'cost',
          label: '长期待摊费用',
          rows: [{ key: 'k', label: '装 修 费', codes: [], opening: 0, closing: 5, increase: 0, decrease: 0 }],
        },
      ]),
      'I4',
      [row('装修费', 'row-1')],
    )
    expect(res.cells).toHaveLength(1)
    expect(res.cells[0].rowKey).toBe('row-1')
  })

  it('同名行只取第一个（不重复写同一标签的多行）', () => {
    const res = buildICycleSeedCells(
      prefill([
        {
          segment: 'cost',
          label: '长期待摊费用',
          rows: [{ key: 'k', label: '装修费', codes: [], opening: 0, closing: 5, increase: 0, decrease: 0 }],
        },
      ]),
      'I4',
      [row('装修费', 'first'), row('装修费', 'second')],
    )
    expect(res.cells.map((c) => c.rowKey)).toEqual(['first'])
  })

  it('未知 wp_code 一律安全返回空结果，不抛异常', () => {
    const res = buildICycleSeedCells(prefill([]), 'ZZ', [row('x')])
    expect(res).toEqual({ cells: [], unclassified: [], absentSlots: [], blockOf: {} })
  })
})

describe('I2 双期：期末 + 期初各出一格', () => {
  it('声明了 openingField ⇒ 同一行产 2 格，且期间标签不同', () => {
    const res = buildICycleSeedCells(
      prefill([
        {
          segment: 'cost',
          label: '开发支出',
          rows: [{ key: '1704.1', label: '项目甲', codes: ['1704.1'], opening: 10, closing: 20, increase: 10, decrease: 0 }],
        },
      ]),
      'I2',
      [row('项目甲', 'rid')],
    )
    expect(res.cells).toHaveLength(2)
    expect(res.cells.map((c) => c.field).sort()).toEqual(['beginUnadj', 'endUnadj'])
    expect(res.cells.find((c) => c.field === 'endUnadj')!.amount).toBe(20)
    expect(res.cells.find((c) => c.field === 'beginUnadj')!.amount).toBe(10)
    expect(new Set(res.cells.map((c) => c.periodLabel)).size).toBe(2)
  })
})

describe('I1 三段 × 类别，blockOf 逐段给出前端 block', () => {
  const threeSegments: IAdjudicationPrefill = {
    mode: 'category',
    unmapped: [],
    segments: [
      {
        segment: 'cost',
        label: '账面原值',
        rows: [{ key: 'land', label: '土地使用权', codes: ['1701.01'], opening: 1, closing: 2, increase: 1, decrease: 0 }],
      },
      {
        segment: 'amortization',
        label: '累计摊销',
        rows: [{ key: 'land', label: '土地使用权', codes: ['1702.01'], opening: 3, closing: 4, increase: 1, decrease: 0 }],
      },
      {
        segment: 'impairment',
        label: '减值准备',
        rows: [{ key: 'land', label: '土地使用权', codes: ['1703.01'], opening: 5, closing: 6, increase: 1, decrease: 0 }],
      },
    ],
  }

  it('三段各出一格，blockOf 把 amortization 映到 amort', () => {
    const res = buildICycleSeedCells(threeSegments, 'I1', [row('土地使用权', 'cat-land')])
    expect(res.cells).toHaveLength(3)
    expect(res.blockOf).toEqual({ cost: 'cost', amortization: 'amort', impairment: 'impairment' })
  })

  it('三段的 periodLabel 互不相同（否则冲突清单分不清是哪一段）', () => {
    const res = buildICycleSeedCells(threeSegments, 'I1', [row('土地使用权', 'cat-land')])
    expect(new Set(res.cells.map((c) => c.periodLabel)).size).toBe(3)
  })

  it('同一 rowKey + 同一 field 在三段间重复 —— 调用方必须靠 blockOf 区分', () => {
    const res = buildICycleSeedCells(threeSegments, 'I1', [row('土地使用权', 'cat-land')])
    expect(new Set(res.cells.map((c) => `${c.rowKey}/${c.field}`)).size).toBe(1)
    expect(res.cells.every((c) => c.field === 'unadjusted')).toBe(true)
  })
})

describe('与平台共享件 planAdjudicationPrefill 串通', () => {
  const p = prefill([
    {
      segment: 'cost',
      label: '长期待摊费用',
      rows: [
        { key: 'a', label: '装修费', codes: ['1801.01'], opening: 0, closing: 100, increase: 0, decrease: 0 },
        { key: 'b', label: '租入改良', codes: ['1801.02'], opening: 0, closing: 200, increase: 0, decrease: 0 },
      ],
    },
  ])
  const existing = [row('装修费', 'r1'), row('租入改良', 'r2')]

  it('空值 → writes；已相同 → identical（幂等）；不同 → conflicts（手工优先）', () => {
    const { cells } = buildICycleSeedCells(p, 'I4', existing)
    const current: Record<string, number | ''> = { r1: '', r2: 200 }
    const plan = planAdjudicationPrefill(cells, (c) => current[c.rowKey])
    expect(plan.writes.map((c) => c.rowKey)).toEqual(['r1'])
    expect(plan.identical).toBe(1)
    expect(plan.conflicts).toEqual([])
  })

  it('已有值且不同 → 进 conflicts，默认 fill-blank 不覆盖', () => {
    const { cells } = buildICycleSeedCells(p, 'I4', existing)
    const plan = planAdjudicationPrefill(cells, () => 999)
    expect(plan.conflicts).toHaveLength(2)
    expect(resolveAdjPrefillWrites(plan)).toEqual([])
    expect(resolveAdjPrefillWrites(plan, 'overwrite')).toHaveLength(2)
  })

  it('absentSlots / unclassified 原样透传进 plan（界面据此如实说明）', () => {
    const res = buildICycleSeedCells(prefill([], ['9999']), 'I4', existing)
    const plan = planAdjudicationPrefill(res.cells, () => '', {
      unclassified: res.unclassified,
      absentSlots: res.absentSlots,
    })
    expect(plan.absentSlots).toEqual([{ slotKey: 'cost', label: '长期待摊费用' }])
    expect(plan.unclassified.map((u) => u.code)).toEqual(['9999'])
  })
})

describe('extractICyclePrefill 形态校验', () => {
  it('合法载荷正常解出', () => {
    const got = extractICyclePrefill({ adjudication_prefill: { mode: 'leaf', segments: [], unmapped: ['x'] } })
    expect(got).toEqual({ mode: 'leaf', segments: [], unmapped: ['x'] })
  })

  it('camelCase 键也接受（与既有循环兼容）', () => {
    expect(extractICyclePrefill({ adjudicationPrefill: { mode: 'category', segments: [] } })).toMatchObject({
      mode: 'category',
    })
  })

  it('🔴 非法 mode / 数组 / 缺键 / null 一律返 null（不产半截载荷）', () => {
    expect(extractICyclePrefill(null)).toBeNull()
    expect(extractICyclePrefill({})).toBeNull()
    expect(extractICyclePrefill({ adjudication_prefill: [] })).toBeNull()
    expect(extractICyclePrefill({ adjudication_prefill: { mode: 'bogus', segments: [] } })).toBeNull()
    expect(extractICyclePrefill({ adjudication_prefill: { segments: [] } })).toBeNull()
  })

  it('segments / unmapped 非数组时归一为空数组（不让下游崩）', () => {
    const got = extractICyclePrefill({
      adjudication_prefill: { mode: 'leaf', segments: 'oops', unmapped: 42 },
    })
    expect(got).toEqual({ mode: 'leaf', segments: [], unmapped: [] })
  })
})

describe('后端载荷键名与前端契约逐字一致（防契约漂移）', () => {
  const py = stripPy(readFileSync(join(BACKEND, 'i_cycle_prefill.py'), 'utf-8'))

  it('行结构六个键在后端源码里都能找到', () => {
    for (const key of ['key', 'label', 'codes', 'opening', 'closing', 'increase', 'decrease']) {
      expect(py, `后端行结构缺 "${key}"`).toContain(`"${key}"`)
    }
  })

  it('段结构键 segment / label / rows 在后端源码里都能找到', () => {
    for (const key of ['segment', 'label', 'rows']) {
      expect(py).toContain(`"${key}"`)
    }
  })

  it('后端在全空时返 None（render 据此不写键）—— 对应前端 null 分支', () => {
    expect(py).toMatch(/return None/)
  })
})

describe('iCycleSeedSpec 取值', () => {
  it('大小写不敏感，未知返 undefined', () => {
    expect(iCycleSeedSpec('i4')?.cycle).toBe('I4')
    expect(iCycleSeedSpec('I4')?.cycle).toBe('I4')
    expect(iCycleSeedSpec('X9')).toBeUndefined()
    expect(iCycleSeedSpec('')).toBeUndefined()
  })

  it('每个循环的 cycle 字段与其键一致（防复制粘贴漏改）', () => {
    for (const wp of CYCLES) {
      expect(I_CYCLE_SEED_SPECS[wp].cycle, `${wp} 的 cycle 字段写错`).toBe(wp)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════
// 六个审定表 SFC 的接线锁死（防 dead output 复发 + 模板引用未定义变量）
// ═══════════════════════════════════════════════════════════════════

describe('六个审定表 SFC 必须真消费 adjudication_prefill（防 dead output 复发）', () => {
  const SFC_PATHS: Record<ICycleWpCode, string> = {
    I1: resolve(COMPOSABLES, '..', 'i1', 'core', 'I1TabAdjudication.vue'),
    I2: resolve(COMPOSABLES, '..', 'i2', 'core', 'I2TabAdjudication.vue'),
    I3: resolve(COMPOSABLES, '..', 'i3', 'core', 'I3TabAdjudication.vue'),
    I4: resolve(COMPOSABLES, '..', 'i4', 'core', 'I4TabAdjudication.vue'),
    I5: resolve(COMPOSABLES, '..', 'i5', 'core', 'I5TabAdjudication.vue'),
    I6: resolve(COMPOSABLES, '..', 'i6', 'core', 'I6TabAdjudication.vue'),
  }

  /** 拆出 <template> 与 <script> 两段（模板变量必须在 script 里有定义） */
  function splitSfc(src: string): { template: string; script: string } {
    const t = src.match(/<template>([\s\S]*)<\/template>/)
    const s = src.match(/<script[^>]*>([\s\S]*?)<\/script>/)
    return { template: t ? t[1] : '', script: s ? s[1] : '' }
  }

  it('反向自检：六个 SFC 都存在且能拆出 template + script', () => {
    for (const wp of CYCLES) {
      expect(existsSync(SFC_PATHS[wp]), `${SFC_PATHS[wp]} 不存在`).toBe(true)
      const { template, script } = splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8'))
      expect(template.length, `${wp} 抽不出 template`).toBeGreaterThan(100)
      expect(script.length, `${wp} 抽不出 script`).toBeGreaterThan(100)
    }
  })

  /** 抽 `useICycleAdjudicationSeeding({ … })` 的调用体（不含外层大括号） */
  function seedingCallBody(script: string): string | null {
    const m = script.match(/useICycleAdjudicationSeeding\(\{([\s\S]*?)\n\}\)/)
    return m ? m[1] : null
  }

  for (const wp of CYCLES) {
    it(`${wp} 已接 useICycleAdjudicationSeeding 且 wpCode 传对`, () => {
      const script = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      expect(script, `${wp} 未 import useICycleAdjudicationSeeding ⇒ 后端载荷仍是 dead output`)
        .toContain('useICycleAdjudicationSeeding')
      // 🔴 wpCode 必须在**调用体内**判（2026-08-12 变异检验 W2 补强）：
      //    全文 grep `wpCode: 'I5'` 会被同文件里 `useAdjudicationBringIn({ wpCode: 'I5' })`
      //    满足 —— 把 seeding 的 wpCode 改成 'I4'（于是拿错循环的段声明与列字段）照样绿。
      const body = seedingCallBody(script)
      expect(body, `${wp} 抽不到 useICycleAdjudicationSeeding 调用体`).toBeTruthy()
      expect(body!, `${wp} 的 wpCode 传错（复制粘贴漏改会让它拿别的循环的段声明）`).toMatch(
        new RegExp(`wpCode:\\s*['"]${wp}['"]`),
      )
    })

    it(`${wp} 模板里的四个绑定在 script 里都有定义`, () => {
      const { template, script } = splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8'))
      const tpl = template.replace(/<!--[\s\S]*?-->/g, '')
      const scr = stripTs(script)
      // 🔴 Vue 模板引用未定义变量 = 静默渲染空/按钮永久禁用，
      //    get_diagnostics 与 vitest 都查不出，只有浏览器挂载才暴露。
      for (const name of ['fourTableHint', 'hasFourTablePrefill', 'fourTableSeeding', 'pullFromFourTable']) {
        expect(tpl, `${wp} 模板未绑定 ${name}`).toContain(name)
        expect(scr, `${wp} 模板用了 ${name} 但 script 未定义 ⇒ 静默失效`).toMatch(
          new RegExp(`\\b${name}\\b`),
        )
      }
    })

    it(`${wp} 传给 composable 的键全在 UseICycleSeedingOptions 内`, () => {
      const script = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      const call = script.match(/useICycleAdjudicationSeeding\(\{([\s\S]*?)\n\}\)/)
      expect(call, `${wp} 抽不到 useICycleAdjudicationSeeding 调用体`).toBeTruthy()
      const passed = new Set(
        Array.from(call![1].matchAll(/^\s{2}([a-zA-Z][\w]*)\s*:/gm)).map((m) => m[1]),
      )
      const allowed = new Set(['wpCode', 'htmlData', 'rows', 'isReadonly', 'readCell', 'applyCell'])
      const illegal = [...passed].filter((k) => !allowed.has(k))
      expect(illegal, `${wp} 传了不存在的选项键 ${illegal} ⇒ 静默忽略`).toEqual([])
      // 六个必填键一个不能少
      for (const k of allowed) {
        expect(passed.has(k), `${wp} 缺必填选项 ${k}`).toBe(true)
      }
    })

    it(`${wp} readCell 把 0 当未填（否则对初始化为 0 的新行带入完全无效）`, () => {
      const script = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      expect(script, `${wp} readCell 未把 0 视为未填`).toMatch(/v\s*===?\s*0/)
    })

    // 🔴 2026-08-12 变异检验 W10 补强：上面的「labelField 强判据」只锁**声明层**，
    //    SFC 完全可以绕过声明自己写死一个字段名（实测把 I3 改成硬编码 'projectName'
    //    后守卫仍全绿 —— 而那正是会让整循环带入静默失效的写法）。故此处要求消费方
    //    必须**从 iCycleSeedSpec() 取**，让声明层的锁死真正传导到 SFC。
    it(`${wp} 的 labelField 必须取自 iCycleSeedSpec（不得在 SFC 里写死字段名）`, () => {
      const script = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      if (wp === 'I1') {
        // I1 是三段 × 类别行，标签字段固定为行模型的 `category`，
        // 由 `i1SeedRows` 里 `r.category` 直接给出（不经 labelField 变量）。
        expect(script, 'I1 未用 r.category 作行标签').toMatch(/label:\s*String\(r\.category/)
        return
      }
      expect(
        script,
        `${wp} 未从 iCycleSeedSpec 取 labelField ⇒ 声明层的锁死传导不到 SFC`,
      ).toMatch(new RegExp(`iCycleSeedSpec\\(\\s*['"]${wp}['"]\\s*\\)\\?\\.labelField`))
    })

    // 拆成独立 it：与上一条同放一个 it 时，变异检验无法区分打红的是哪条断言
    it(`${wp} 取到的 labelField 必须真的用于读行标签（取了不用 = 死代码）`, () => {
      const script = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      if (wp === 'I1') {
        expect(script).toMatch(/label:\s*String\(r\.category/)
        return
      }
      expect(script, `${wp} 取了 labelField 却没用它读行标签`).toMatch(
        /label:\s*String\(\s*\(r as unknown as Record<string, unknown>\)\[\s*\w+SeedLabelField\s*\]/,
      )
    })
  }

  /**
   * 抽出 `applyCell: (…) => { … }` 的函数体。
   *
   * 🔴 必须限定在 applyCell 体内判断，不能全文 grep `updateCell(block` ——
   * 2026-08-12 变异检验 W6 实测：I1 文件里另有 `onCellChange(block, …)` 会调
   * `updateCell(block, …)`，全文判据被它满足 ⇒ 把 applyCell 里的 block 换成
   * 写死的 `'cost'`（三段全落原值段）守卫照样绿。
   */
  function applyCellBody(script: string): string {
    const i = script.indexOf('applyCell:')
    if (i < 0) return ''
    // 从 applyCell: 起做括号配对，直到该属性结束（遇到同层的 `,` 或 `}`）
    let depthParen = 0
    let depthBrace = 0
    for (let j = i; j < script.length; j += 1) {
      const ch = script[j]
      if (ch === '(') depthParen += 1
      else if (ch === ')') depthParen -= 1
      else if (ch === '{') depthBrace += 1
      else if (ch === '}') {
        if (depthBrace === 0) return script.slice(i, j)
        depthBrace -= 1
      } else if (ch === ',' && depthParen === 0 && depthBrace === 0) {
        return script.slice(i, j)
      }
    }
    return script.slice(i)
  }

  it('反向自检：applyCellBody 能抽出非空体且不吞掉整个 script', () => {
    for (const wp of CYCLES) {
      const scr = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      const body = applyCellBody(scr)
      expect(body.length, `${wp} 抽不到 applyCell 体`).toBeGreaterThan(20)
      expect(body.length, `${wp} applyCell 体抽overshoot（吞了后续代码）`).toBeLessThan(400)
      expect(body.startsWith('applyCell:')).toBe(true)
    }
  })

  it('🔴 只有 I1 用四参 updateCell 传 block；其余五个不得传 block', () => {
    const i1 = stripTs(splitSfc(readFileSync(SFC_PATHS.I1, 'utf-8')).script)
    const i1Body = applyCellBody(i1)
    // I1 必须把 block 用上（三段 rowKey+field 相同，只有 block 能区分）
    expect(i1).toMatch(/applyCell:\s*\(cell,\s*block\)/)
    expect(i1Body, 'I1 的 applyCell 未把 block 传给 updateCell ⇒ 后两段静默覆盖第一段').toMatch(
      /updateCell\(\s*block\b/,
    )
    // 反向：applyCell 体内不得出现写死的 block 字面量
    for (const lit of ["'cost'", "'amort'", "'impairment'"]) {
      expect(
        i1Body.includes(lit),
        `I1 的 applyCell 写死了 block=${lit} ⇒ 三段全落同一 block`,
      ).toBe(false)
    }
    // I1 必须在 block 反查失败时拒绝写入（不猜段）
    expect(i1, 'I1 缺「block 缺失即不写」的保护').toMatch(/if\s*\(!block\)\s*return/)

    for (const wp of CYCLES.filter((c) => c !== 'I1')) {
      const scr = stripTs(splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).script)
      const m = scr.match(/applyCell:\s*\(([^)]*)\)/)
      expect(m, `${wp} 抽不到 applyCell 签名`).toBeTruthy()
      expect(
        m![1].includes('block'),
        `${wp} 是单/双段循环，applyCell 不该收 block（收了说明照抄了 I1）`,
      ).toBe(false)
    }
  })

  it('六个 SFC 的 data-testid 各不相同（浏览器实测要能唯一定位）', () => {
    const ids = CYCLES.map((wp) => {
      const tpl = splitSfc(readFileSync(SFC_PATHS[wp], 'utf-8')).template
      const m = tpl.match(/data-testid="(i\d-pull-four-table)"/)
      return m ? m[1] : null
    })
    expect(ids.filter(Boolean)).toHaveLength(6)
    expect(new Set(ids).size).toBe(6)
  })

  it('后端六个 render 策略确实下发该键（消费侧不能对着空气接线）', () => {
    const strategies: Record<ICycleWpCode, string> = {
      I1: '_i1_intangible_assets.py',
      I2: '_i2_development_expenditure.py',
      I3: '_i3_goodwill.py',
      I4: '_i4_long_term_prepaid.py',
      I5: '_i5_other_noncurrent_assets.py',
      I6: '_i6_research_development_expense.py',
    }
    const dir = join(REPO_ROOT, 'backend', 'app', 'routers', 'wp_render_strategies')
    for (const wp of CYCLES) {
      const p = join(dir, strategies[wp])
      expect(existsSync(p), `${p} 不存在`).toBe(true)
      const src = stripPy(readFileSync(p, 'utf-8'))
      expect(src, `${wp} 的 render 策略未下发 adjudication_prefill`).toContain(
        'payload["adjudication_prefill"]',
      )
    }
  })
})
