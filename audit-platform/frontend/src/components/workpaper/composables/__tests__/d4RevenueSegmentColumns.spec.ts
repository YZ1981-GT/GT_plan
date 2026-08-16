/**
 * D4（4）分解信息表动态列守卫。
 *
 * Property 24: D4 动态列键稳定且不复用序号
 * Property 25: D4 分解信息表无硬编码行业名
 *
 * spec: d-cycle-four-table-extraction-and-disclosure-completion (Task 23)
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */

import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import * as fc from 'fast-check'

import {
  D4_SEGMENT_KEY_PREFIX,
  D4_SEGMENT_KEY_RE,
  D4_LEGACY_LABEL_MARK,
  allocateSegment,
  appendSegment,
  removeSegment,
  migrateSegments,
  parseSegmentState,
  type D4SegmentState,
} from '../d4RevenueSegmentColumns'
import { buildD4TransposeColumns, D4_DEFAULT_CATEGORIES } from '../d4DisclosureModel'

// ─────────────────────────────────────────────────────── 仓库根（双哨兵）

function repoRoot(): string {
  const sentinels = [
    path.join('backend', 'data', 'note_template_listed.json'),
    path.join('audit-platform', 'frontend', 'package.json'),
  ]
  let cur = __dirname
  for (let i = 0; i < 12; i += 1) {
    if (sentinels.every((s) => fs.existsSync(path.join(cur, s)))) return cur
    const parent = path.dirname(cur)
    if (parent === cur) break
    cur = parent
  }
  throw new Error('未能定位仓库根（双哨兵均需存在）')
}

const ROOT = repoRoot()
const COMPOSABLES = path.join(
  ROOT,
  'audit-platform',
  'frontend',
  'src',
  'components',
  'workpaper',
  'composables',
)

function readSrc(rel: string): string {
  const p = path.join(COMPOSABLES, rel)
  expect(fs.existsSync(p), `源文件缺失：${p}`).toBe(true)
  return fs.readFileSync(p, 'utf-8')
}

/** 剥注释（守卫判据必须落在真实代码上；说明文字里会写反例）。 */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function emptyState(cats: Array<{ key: string; label: string }>): D4SegmentState {
  return { categories: cats.map((c) => ({ ...c })), cells: {}, seqCounter: cats.length }
}

// ══════════════════════════════════════════════════════════════════════
// Property 24: 键稳定且不复用序号
// ══════════════════════════════════════════════════════════════════════

describe('Property 24: D4 动态列键稳定且不复用序号', () => {
  it('键形如 cat_\\d+ 且不含中文', () => {
    let s = emptyState([])
    for (const label of ['批发', '零售', '物流']) {
      s = appendSegment(s, label)
    }
    expect(s.categories).toHaveLength(3)
    for (const c of s.categories) {
      expect(c.key).toMatch(D4_SEGMENT_KEY_RE)
      expect(/[\u4e00-\u9fa5]/.test(c.key)).toBe(false)
    }
  })

  it('🔴 删除中间列再新增，新 key 严格大于历史最大值（不复用已删序号）', () => {
    let s = emptyState([
      { key: 'cat_1', label: '批发' },
      { key: 'cat_2', label: '零售' },
      { key: 'cat_3', label: '物流' },
    ])
    // 在 cat_3 里录一笔数
    s = { ...s, cells: { ...s.cells, cat_3_0_revenue: 1000 } }

    s = removeSegment(s, 'cat_3')
    expect(s.categories.map((c) => c.key)).toEqual(['cat_1', 'cat_2'])
    // 关联单元格已清理
    expect(Object.keys(s.cells)).not.toContain('cat_3_0_revenue')

    s = appendSegment(s, '医疗收入')
    const added = s.categories[s.categories.length - 1]
    expect(added.key).toBe('cat_4')
    expect(added.key).not.toBe('cat_3')
  })

  it('🔴 反向自检：按「现有最大 seq + 1」分配会复用已删序号', () => {
    // 复现旧 `nextD4CategoryKey` 的实现（只看 categories，不看计数器）
    const naiveNext = (cats: ReadonlyArray<{ key: string }>): string => {
      let max = 0
      for (const c of cats) {
        const n = Number(c.key.slice(D4_SEGMENT_KEY_PREFIX.length))
        if (Number.isFinite(n) && n > max) max = n
      }
      return `${D4_SEGMENT_KEY_PREFIX}${max + 1}`
    }
    const after = [
      { key: 'cat_1', label: '批发' },
      { key: 'cat_2', label: '零售' },
    ]
    // 朴素实现给出 cat_3 —— 与刚删掉的那列同名（这正是缺陷）
    expect(naiveNext(after)).toBe('cat_3')
    // 正确实现给出 cat_4
    expect(allocateSegment(after, 3).key).toBe('cat_4')
  })

  it('seqCounter 在删除时不回退', () => {
    let s = emptyState([{ key: 'cat_1', label: 'A' }])
    s = appendSegment(s, 'B')
    expect(s.seqCounter).toBe(2)
    s = removeSegment(s, 'cat_2')
    expect(s.seqCounter).toBe(2)
    s = appendSegment(s, 'C')
    expect(s.categories[s.categories.length - 1].key).toBe('cat_3')
  })

  it('历史数据无 seqCounter 时不与既有列撞键', () => {
    const legacy: D4SegmentState = {
      categories: [
        { key: 'cat_1', label: 'A' },
        { key: 'cat_5', label: 'B' },
      ],
      cells: {},
    }
    expect(allocateSegment(legacy.categories, legacy.seqCounter).key).toBe('cat_6')
  })

  it('拒绝无名列（空 label 原样返回）', () => {
    const s = emptyState([])
    expect(appendSegment(s, '')).toBe(s)
    expect(appendSegment(s, '   ')).toBe(s)
  })

  it('PBT：任意增删序列下 key 恒唯一且单调递增', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.oneof(
            fc.record({ op: fc.constant('add' as const), label: fc.string({ minLength: 1, maxLength: 6 }) }),
            fc.record({ op: fc.constant('del' as const), idx: fc.nat({ max: 8 }) }),
          ),
          { minLength: 1, maxLength: 30 },
        ),
        (ops) => {
          let s = emptyState([])
          const everSeen = new Set<string>()
          for (const op of ops) {
            if (op.op === 'add') {
              const before = s.categories.length
              s = appendSegment(s, op.label)
              if (s.categories.length > before) {
                const k = s.categories[s.categories.length - 1].key
                // 从未出现过的 key（含已删除的）
                expect(everSeen.has(k)).toBe(false)
                everSeen.add(k)
              }
            } else if (s.categories.length > 0) {
              const target = s.categories[op.idx % s.categories.length]
              s = removeSegment(s, target.key)
            }
            // 当前列表内 key 恒唯一
            const keys = s.categories.map((c) => c.key)
            expect(new Set(keys).size).toBe(keys.length)
          }
          return true
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ══════════════════════════════════════════════════════════════════════
// Property 24（续）: 旧列迁移（裁决门 A = ② 按列名迁移 + legacy 保留）
// ══════════════════════════════════════════════════════════════════════

describe('Property 24（续）: 旧列按列名迁移且未匹配者保留', () => {
  it('同名列的单元格搬到新 key', () => {
    const old: D4SegmentState = {
      categories: [
        { key: 'cat_1', label: '消费品' },
        { key: 'cat_2', label: '批发' },
      ],
      cells: { cat_1_0_revenue: 100, cat_2_0_revenue: 200, cat_2_1_cost: 50 },
      seqCounter: 2,
    }
    const r = migrateSegments(old, ['批发', '零售'])
    expect(r.changed).toBe(true)

    const wholesale = r.state.categories.find((c) => c.label === '批发')!
    expect(wholesale.key).toMatch(D4_SEGMENT_KEY_RE)
    expect(r.state.cells[`${wholesale.key}_0_revenue`]).toBe(200)
    expect(r.state.cells[`${wholesale.key}_1_cost`]).toBe(50)
    expect(r.migrated).toBe(2)
  })

  it('🔴 未匹配的历史列保留为 legacy 且数据不丢', () => {
    const old: D4SegmentState = {
      categories: [{ key: 'cat_1', label: '消费品' }],
      cells: { cat_1_0_revenue: 999 },
      seqCounter: 1,
    }
    const r = migrateSegments(old, ['批发'])
    expect(r.legacyKeys).toHaveLength(1)

    const legacy = r.state.categories.find((c) => c.isLegacy)!
    expect(legacy.label).toContain(D4_LEGACY_LABEL_MARK)
    expect(legacy.label).toContain('消费品')
    // 🔴 数据零丢失红线
    expect(r.state.cells[`${legacy.key}_0_revenue`]).toBe(999)
  })

  it('目标板块在历史里没有 ⇒ 建空列，不填 0', () => {
    const old: D4SegmentState = { categories: [], cells: {}, seqCounter: 0 }
    const r = migrateSegments(old, ['批发', '零售'])
    expect(r.state.categories.map((c) => c.label)).toEqual(['批发', '零售'])
    // 没有任何单元格被凭空填 0
    expect(Object.keys(r.state.cells)).toHaveLength(0)
  })

  it('targetLabels 为空 ⇒ 原样返回（防误清空）', () => {
    const old: D4SegmentState = {
      categories: [{ key: 'cat_1', label: '消费品' }],
      cells: { cat_1_0_revenue: 1 },
      seqCounter: 1,
    }
    const r = migrateSegments(old, [])
    expect(r.changed).toBe(false)
    expect(r.state).toBe(old)
  })

  it('列名归一只去空白与全角括号，不做模糊匹配', () => {
    const old: D4SegmentState = {
      categories: [{ key: 'cat_1', label: '物业与租赁（含转租）' }],
      cells: { cat_1_0_revenue: 7 },
      seqCounter: 1,
    }
    // 全角括号写法差异应命中
    const hit = migrateSegments(old, ['物业与租赁(含转租)'])
    expect(hit.legacyKeys).toHaveLength(0)
    expect(hit.migrated).toBe(1)

    // 而「相近但不同」的名字必须**不**命中（宁缺勿造，交人工归并）
    const miss = migrateSegments(old, ['物业'])
    expect(miss.legacyKeys).toHaveLength(1)
  })

  it('迁移幂等：对已迁移结果再迁一次不再改变', () => {
    const old: D4SegmentState = {
      categories: [{ key: 'cat_1', label: '批发' }],
      cells: { cat_1_0_revenue: 5 },
      seqCounter: 1,
    }
    const first = migrateSegments(old, ['批发'])
    const second = migrateSegments(first.state, ['批发'])
    expect(second.state.categories).toEqual(first.state.categories)
    expect(second.state.cells).toEqual(first.state.cells)
  })

  it('legacy 列再迁一次不会重复叠加标记', () => {
    const old: D4SegmentState = {
      categories: [{ key: 'cat_1', label: '消费品' }],
      cells: {},
      seqCounter: 1,
    }
    const first = migrateSegments(old, ['批发'])
    const second = migrateSegments(first.state, ['批发'])
    const legacy = second.state.categories.filter((c) => c.isLegacy)
    expect(legacy).toHaveLength(1)
    const marks = legacy[0].label.split(D4_LEGACY_LABEL_MARK).length - 1
    expect(marks).toBe(1)
  })
})

// ══════════════════════════════════════════════════════════════════════
// parseSegmentState 容错
// ══════════════════════════════════════════════════════════════════════

describe('parseSegmentState 容错与 key 补齐', () => {
  it('空/非法输入回退默认类别', () => {
    for (const raw of [null, undefined, '', 'not-json', 42, { categories: [] }]) {
      const s = parseSegmentState(raw as unknown)
      expect(s.categories.length).toBe(D4_DEFAULT_CATEGORIES.length)
    }
  })

  it('🔴 模板 seed 的 cat0 形态（无下划线）被规整并搬移单元格', () => {
    const s = parseSegmentState(
      JSON.stringify({
        categories: [{ key: 'cat0', label: '批发' }],
        cells: { cat0_0_revenue: 11 },
      }),
    )
    expect(s.categories[0].key).toMatch(D4_SEGMENT_KEY_RE)
    const k = s.categories[0].key
    expect(s.cells[`${k}_0_revenue`]).toBe(11)
    // 旧键不残留（否则同一笔钱在两列各显示一次）
    expect(s.cells.cat0_0_revenue).toBeUndefined()
  })

  it('重复 key 被重新分配且不互相覆盖', () => {
    const s = parseSegmentState({
      categories: [
        { key: 'cat_1', label: 'A' },
        { key: 'cat_1', label: 'B' },
      ],
      cells: {},
    })
    const keys = s.categories.map((c) => c.key)
    expect(new Set(keys).size).toBe(2)
  })

  it('缺 seqCounter 时按现有最大 seq 补齐', () => {
    const s = parseSegmentState({
      categories: [{ key: 'cat_7', label: 'A' }],
      cells: {},
    })
    expect(s.seqCounter).toBe(7)
    expect(allocateSegment(s.categories, s.seqCounter).key).toBe('cat_8')
  })
})

// ══════════════════════════════════════════════════════════════════════
// Property 25: 无硬编码行业名（列定义与映射侧）
// ══════════════════════════════════════════════════════════════════════

describe('Property 25: D4 分解信息表列定义无硬编码行业名', () => {
  const INDUSTRY_LITERALS = ['汽车', '消费品', '能源']

  it('🔴 d4NoteSectionMap.ts 不含行业名字面量', () => {
    const src = stripComments(readSrc('d4NoteSectionMap.ts'))
    for (const lit of INDUSTRY_LITERALS) {
      expect(src, `d4NoteSectionMap.ts 出现行业名字面量 ${lit}`).not.toContain(lit)
    }
  })

  it('🔴 本模块（键分配与迁移）不含行业名字面量', () => {
    const src = stripComments(readSrc('d4RevenueSegmentColumns.ts'))
    for (const lit of INDUSTRY_LITERALS) {
      expect(src, `d4RevenueSegmentColumns.ts 出现行业名字面量 ${lit}`).not.toContain(lit)
    }
  })

  it('列由入参生成：换一组板块名，列头逐个跟随', () => {
    const cats = [
      { key: 'cat_1', label: '批发' },
      { key: 'cat_2', label: '零售' },
    ]
    const cols = buildD4TransposeColumns(cats)
    const groups = cols.map((c) => (c as { group?: string }).group).filter(Boolean)
    expect(groups).toContain('批发')
    expect(groups).toContain('零售')
    for (const lit of INDUSTRY_LITERALS) {
      expect(groups).not.toContain(lit)
    }
  })

  it('列 key 由类别 key 派生（收入/成本两叶子），不用 label 作 key', () => {
    const cols = buildD4TransposeColumns([{ key: 'cat_9', label: '其他' }])
    const keys = cols.map((c) => c.key)
    expect(keys).toContain('cat_9_revenue')
    expect(keys).toContain('cat_9_cost')
    // label 不得进 key（H7 已实证 label 作键会撞）
    expect(keys.some((k) => /[\u4e00-\u9fa5]/.test(k))).toBe(false)
  })

  it('两级分组齐备：每个类别列都声明 group（收入/成本为叶子）', () => {
    const cols = buildD4TransposeColumns([{ key: 'cat_1', label: '批发' }])
    const catCols = cols.filter((c) => c.key.startsWith('cat_1_'))
    expect(catCols).toHaveLength(2)
    for (const c of catCols) {
      expect((c as { group?: string }).group).toBe('批发')
      expect(['收入', '成本']).toContain(c.label)
    }
  })

  it('🔴 反向自检：D4_DEFAULT_CATEGORIES 仍带源模板示例名（兜底/展示用）', () => {
    // 这不是缺陷 —— 源模板 B46:I46 就是这四个示例，与 F2 `_F2_CATEGORIES[].account`
    // 「兜底/展示用」同性质。Property 25 的禁令对象是**映射与列定义**，不是默认值。
    // 一旦它被清空，动态列在「历史无数据」时会渲染成零列 ⇒ 必须留着。
    expect(D4_DEFAULT_CATEGORIES.length).toBeGreaterThan(0)
    const labels = D4_DEFAULT_CATEGORIES.map((c) => c.label)
    expect(labels).toContain('消费品')
    for (const c of D4_DEFAULT_CATEGORIES) {
      expect(c.key).toMatch(D4_SEGMENT_KEY_RE)
    }
  })
})

// ══════════════════════════════════════════════════════════════════════
// 接线：composable 必须走本模块的分配器（防旧 nextD4CategoryKey 回退）
// ══════════════════════════════════════════════════════════════════════

describe('接线锁死：useD4Disclosure 走持久化计数器', () => {
  it('🔴 useD4Disclosure 引用本模块的 allocateSegment（而非旧 nextD4CategoryKey）', () => {
    const src = stripComments(readSrc('useD4Disclosure.ts'))
    expect(src).toContain('d4RevenueSegmentColumns')
    expect(src).toMatch(/allocateSegment\s*\(/)
  })

  it('🔴 useD4Disclosure 不再调用旧的 nextD4CategoryKey', () => {
    const src = stripComments(readSrc('useD4Disclosure.ts'))
    expect(
      /nextD4CategoryKey\s*\(/.test(src),
      '仍在调用 nextD4CategoryKey ⇒ 删列后会复用已删序号，历史单元格串列',
    ).toBe(false)
  })

  it('🔴 persist 时带上 seqCounter（否则计数器不落库、下次加载即回退）', () => {
    const src = stripComments(readSrc('useD4Disclosure.ts'))
    expect(src).toMatch(/seqCounter/)
  })

  it('反向自检：stripComments 确实生效', () => {
    const sample = '/* 注释里写 nextD4CategoryKey( 不算调用 */\nconst a = 1\n'
    expect(stripComments(sample)).not.toContain('nextD4CategoryKey')
    expect(stripComments(sample)).toContain('const a = 1')
  })
})
